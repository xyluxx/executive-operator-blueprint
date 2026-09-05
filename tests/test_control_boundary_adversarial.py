import importlib.util
import json
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "operator-control"
TOOLS = ROOT / "tools" / "operator-control"

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    assert spec and spec.loader; spec.loader.exec_module(module); return module

schemas = load("operator_control_schemas", PLUGIN / "schemas.py")
policy = load("operator_control_policy", PLUGIN / "policy.py")
store = load("operator_control_store", TOOLS / "store.py")
broker_mod = load("operator_control_broker", TOOLS / "broker.py")
service_mod = load("operator_control_service_hardened", TOOLS / "service.py")
tools_mod = load("operator_control_tools_hardened", PLUGIN / "tools.py")

def seed(b, table, record_id, value):
    con=store.connect(b.db_path)
    con.execute(broker_mod.INSERT_RECORD_SQL[table],(record_id,json.dumps(value,sort_keys=True,separators=(",",":")),b._signature(value)))
    con.close()

def utc(seconds=0):
    return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()

def intent(key="op-1", target="person:alice", payload=None):
    return {"schema_version":1,"operation_key":key,"action_class":"message.send",
      "requester":{"role":"requester","subject":"agent:r"},"executor":{"role":"executor","subject":"adapter:mail"},
      "credential_principal":{"role":"credential_principal","subject":"mailbox:a"},"recipient":{"role":"recipient","subject":target},
      "account":"mailbox:a","target":target,"material_payload":payload or {"body":"hello"},"limits":{"max_cost_usd":0},
      "task_id":"t1","task_version":2,"requirement_version":3,"artifact_id":"artifact-1","artifact_version":"1","target_version":"1","environment":{"name":"test","version":"1"},"acceptance_id":"acceptance-"+key,"policy_digest":"ignored-by-caller"}

def record(i, authority_type="one_off"):
    return {"schema_version":1,"approval_id":"a1","authority_type":authority_type,
      "approver":{"role":"authenticated_approver","subject":"human:owner"},"authority_source":"webauthn","issuance_channel":"console",
      "non_transferable":True,"action_class":i["action_class"],"account":i["account"],"target":i["target"],
      "payload_digest":schemas.material_payload_digest(i["material_payload"]),"limits":i["limits"],"task_id":i["task_id"],
      "task_version":i["task_version"],"requirement_version":i["requirement_version"],"operation_key":i["operation_key"],
      "issued_at":utc(-1),"expires_at":utc(300),"cancelled":False}

def make(tmp_path):
    assets=tmp_path/"assets"; assets.mkdir(); (assets/"policy.json").write_text('{"version":1}')
    b=broker_mod.ActionBroker(tmp_path/"db"/"control.db", policy_root=assets, supported_routes={"message.send"}, signing_key=b"x"*32,
        authenticate_approver=lambda context: ({"authenticated":True,"subject":("human:acceptor" if context == {"session":"acceptance"} else "human:owner"),"authority_source":"webauthn","issuance_channel":"console"} if context in ({"session":"valid"},{"session":"acceptance"}) else False),
        resolve_identities=lambda _: {"authenticated":True,"roles":{"requester":"agent:r","executor":"adapter:mail","credential_principal":"mailbox:a","recipient":"person:alice","approver":"human:owner","evidence_collector":"collector:ci","reviewer":"human:reviewer","accepter":"human:acceptor","exception_authority":"human:risk"}})
    return b

def sign_acceptance(b,i):
    value={"acceptance_id":i["acceptance_id"],"status":"accepted","task_id":i["task_id"],"task_version":i["task_version"],"requirement_version":i["requirement_version"],"artifact_id":i["artifact_id"],"artifact_version":i["artifact_version"],"target_id":i["target"],"target_version":i["target_version"],"environment":i["environment"],"policy_digest":b._current_policy_digest(),"accepter_id":"human:acceptor","criteria_digest":"sha256:"+"a"*64,"evidence_digest":"sha256:"+"b"*64,"issued_at":utc(-1),"expires_at":utc(300)}
    seed(b,"acceptances",value["acceptance_id"],value)

def bound_readback(i):
    return {"account":i["account"],"target":i["target"],"payload_digest":schemas.material_payload_digest(i["material_payload"]),
      "task_version":i["task_version"],"requirement_version":i["requirement_version"],"policy_digest":i["policy_digest"],"operation_key":i["operation_key"]}

def test_caller_cannot_forge_approval_and_signed_store_record_is_immutable(tmp_path):
    b=make(tmp_path); i=intent()
    with pytest.raises(policy.Denied): b.authorize(i, record(i))
    with pytest.raises(policy.Denied): b.issue_approval(record(i), auth_context={"session":"forged"})
    sign_acceptance(b,i); aid=b.issue_approval(record(i), auth_context={"session":"valid"})
    assert aid == "a1"; assert b.authorize(i, aid)["authorized"]
    con=store.connect(b.db_path); con.execute("UPDATE approvals SET record_json=replace(record_json,'alice','mallory') WHERE approval_id='a1'"); con.close()
    with pytest.raises(policy.Denied, match="signature"): b.authorize(i, aid)

def test_operation_key_reuse_requires_identical_complete_intent(tmp_path):
    b=make(tmp_path); i=intent(); i["policy_digest"]=b.policy_digest; sign_acceptance(b,i); b.issue_approval(record(i), auth_context={"session":"valid"})
    first=b.execute(i,"a1",lambda _:{"provider_id":"private","readback":bound_readback(i)})
    assert "private" not in json.dumps(first)
    with pytest.raises(policy.Denied, match="operation key intent mismatch"):
        b.execute(intent(target="person:bob"),"a1",lambda _: {})

def test_every_provider_exception_persists_unknown_and_can_be_boundedly_reconciled(tmp_path):
    b=make(tmp_path); i=intent(); i["policy_digest"]=b.policy_digest; sign_acceptance(b,i); b.issue_approval(record(i), auth_context={"session":"valid"})
    out=b.execute(i,"a1",lambda _: (_ for _ in ()).throw(ValueError("boom")))
    assert out["effect"]=="unknown"
    with pytest.raises(policy.Denied): b.reconcile(i["operation_key"], bound_readback(i), reconciler={"subject":"attacker"})
    resolved=b.reconcile(i["operation_key"], bound_readback(i), reconciler={"subject":"provider:mail","authenticated":True}, effect="confirmed-success")
    assert resolved["effect"]=="confirmed-success"

def test_readback_must_bind_every_protected_dimension(tmp_path):
    for field in ("account","target","payload_digest","task_version","requirement_version","policy_digest","operation_key"):
        case=tmp_path/field; case.mkdir(); b=make(case); i=intent(); i["policy_digest"]=b.policy_digest; sign_acceptance(b,i); b.issue_approval(record(i),auth_context={"session":"valid"})
        rb=bound_readback(i); rb[field]="wrong"
        assert b.execute(i,"a1",lambda _:{"provider_id":"internal", "readback":rb})["effect"]=="unknown"

def test_unknown_tools_fail_closed_and_only_explicit_reads_pass():
    assert not tools_mod.pre_tool_call("new_plugin_write",{},enabled=True)["allowed"]
    assert not tools_mod.pre_tool_call("terminal",{},enabled=True)["allowed"]
    assert tools_mod.pre_tool_call("read_file",{},enabled=True)["allowed"]

def test_store_rejects_hardlinks_and_persistent_rollback_block(tmp_path):
    db=tmp_path/"private"/"db"; con=store.connect(db); con.close()
    alias=tmp_path/"alias"; os.link(db,alias)
    with pytest.raises(PermissionError,match="hardlink"): store.connect(db)
    alias.unlink()
    assert store.prepare_rollback(db)["operations_blocked"]
    with pytest.raises(RuntimeError,match="blocked"): store.connect(db, for_operation=True)

def test_regular_file_never_counts_as_verified_unix_socket(tmp_path, monkeypatch):
    paths=[tmp_path/x for x in ("key","vault","sock")]
    for p in paths: p.write_text("x"); p.chmod(0o600)
    monkeypatch.setattr(service_mod,"_owned_by",lambda *_:True); monkeypatch.setattr(service_mod,"_unreadable_by_uid",lambda *_:True)
    with pytest.raises(RuntimeError,match="Unix socket"):
        service_mod.verify_high_assurance_boundary(hermes_uid=1,broker_uid=2,key_path=paths[0],vault_path=paths[1],socket_path=paths[2])
