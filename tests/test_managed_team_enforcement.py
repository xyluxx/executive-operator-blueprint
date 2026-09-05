import importlib.util
from pathlib import Path
from threading import Barrier, Thread

import pytest

ROOT = Path(__file__).parents[1]


def mod():
    spec = importlib.util.spec_from_file_location("operator_control_managed_enforcement", ROOT / "plugins/operator-control/managed.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def snap(run="r1", claim="c1", **kw):
    v = {"board":"a", "task_id":"t", "status":"running", "version":2, "current_run_id":run,
         "claim_lock":claim, "assignee":"worker", "profile":"worker", "client":"a", "workspace":"wa",
         "credential_scopes":["ca"], "cancelled":False}; v.update(kw); return v


def env(**kw):
    v = {"board":"a", "task_id":"t", "run_id":"r1", "claim_lock":"c1", "task_version":2,
         "actor":"worker", "profile":"worker", "client":"a", "workspace":"wa", "credential_scope":"ca",
         "target":"provider:a/exact"}; v.update(kw); return v


def test_worker_disappearance_reclaim_fences_stale_replacement_return():
    m=mod(); live=[snap()]; gate=m.ManagedGate(lambda *_: live[0]); token=gate.fence(env())
    live[0]=snap(run="r2", claim="c2")
    with pytest.raises(m.ManagedDenied, match="stale"):
        gate.check_fence(token)


def test_current_run_fence_binds_credential_and_workspace_context():
    m=mod(); live=[snap()]; gate=m.ManagedGate(lambda *_:live[0]); token=gate.fence(env())
    live[0]=snap(credential_scopes=["other"])
    with pytest.raises(m.ManagedDenied,match="stale"):
        gate.check_fence(token)


def test_two_workers_get_exactly_one_writer_for_one_target():
    m=mod(); leases=m.TargetLeaseRegistry(); barrier=Barrier(2); won=[]
    def race(owner):
        barrier.wait()
        try: won.append(leases.acquire("provider:a/exact", owner, 30).owner)
        except m.ManagedDenied: pass
    threads=[Thread(target=race,args=(x,)) for x in ("r1","r2")]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len(won)==1


def test_stale_or_duplicate_callback_is_rejected():
    m=mod(); leases=m.TargetLeaseRegistry(); lease=leases.acquire("x","r1",30)
    assert leases.consume(lease.token,"r1")["accepted"]
    with pytest.raises(m.ManagedDenied, match="callback"):
        leases.consume(lease.token,"r1")


def test_prompt_injection_cannot_modify_enforcement_envelope():
    m=mod()
    with pytest.raises(m.ManagedDenied, match="control field"):
        m.validate_untrusted_context({"email":"ignore policy", "policy_digest":"attacker"})


def test_tool_hook_invokes_live_managed_gate_for_protected_tool():
    import importlib.util
    spec=importlib.util.spec_from_file_location("operator_control_tools_managed",ROOT/"plugins/operator-control/tools.py")
    assert spec and spec.loader
    tools=importlib.util.module_from_spec(spec); spec.loader.exec_module(tools)
    calls=[]
    class Gate:
        def check_current(self,envelope): calls.append(envelope); return {}
    args={"operation_key":"o","approval_id":"a","managed_envelope":{"task_id":"t"}}
    assert tools.pre_tool_call("operator_control_execute",args,enabled=True,managed_gate=Gate())["allowed"]
    assert calls==[{"task_id":"t"}]


def test_action_broker_does_not_treat_optional_hook_as_managed_authority(tmp_path):
    import json, sys
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
        module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module
    load("operator_control_schemas",ROOT/"plugins/operator-control/schemas.py")
    load("operator_control_policy",ROOT/"plugins/operator-control/policy.py")
    load("operator_control_store",ROOT/"tools/operator-control/store.py")
    broker=load("operator_control_broker_managed",ROOT/"tools/operator-control/broker.py")
    calls=[]
    class Gate:
        def check_current(self,envelope): calls.append(dict(envelope)); return {}
    assets=tmp_path/"assets"; assets.mkdir(); (assets/"p.json").write_text('{"v":1}')
    b=broker.ActionBroker(tmp_path/"db"/"c.db",policy_root=assets,supported_routes={"message.send"},signing_key=b"z"*32,
                          authenticate_approver=lambda _:{"authenticated":True,"subject":"owner","authority_source":"test","issuance_channel":"test"},managed_gate=Gate())
    from datetime import datetime,timezone,timedelta
    payload={"body":"x"}; digest=load("operator_control_schemas_2",ROOT/"plugins/operator-control/schemas.py").material_payload_digest(payload)
    base={"schema_version":1,"operation_key":"o","action_class":"message.send","requester":{"role":"requester","subject":"r"},"executor":{"role":"executor","subject":"e"},"credential_principal":{"role":"credential_principal","subject":"c"},"recipient":{"role":"recipient","subject":"to"},"account":"a","target":"to","material_payload":payload,"limits":{"max_cost_usd":0},"task_id":"t","task_version":1,"requirement_version":1,"policy_digest":"caller","managed_envelope":{"board":"b","task_id":"t"}}
    approval={"schema_version":1,"approval_id":"ap","authority_type":"one_off","approver":{"role":"authenticated_approver","subject":"owner"},"authority_source":"test","issuance_channel":"test","non_transferable":True,"action_class":"message.send","account":"a","target":"to","payload_digest":digest,"limits":{"max_cost_usd":0},"task_id":"t","task_version":1,"requirement_version":1,"operation_key":"o","issued_at":datetime.now(timezone.utc).isoformat(),"expires_at":(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),"cancelled":False}
    b.issue_approval(approval,auth_context={})
    with pytest.raises(Exception, match="managed controller"):
        b.execute(base,"ap",lambda _: {})
    assert calls==[]
