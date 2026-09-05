import importlib.util
import json
import multiprocessing
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def managed():
    return load("operator_control_managed_hardening", ROOT / "plugins/operator-control/managed.py")


def _lease_racer(module_path, db_path, start, output, owner):
    m = load(f"managed_child_{owner}", Path(module_path))
    leases = m.SQLiteLeaseRegistry(db_path)
    start.wait()
    try:
        lease = leases.acquire("provider:one", owner, 20)
        output.put(("won", owner, lease.generation))
    except m.ManagedDenied:
        output.put(("lost", owner, None))


def test_sqlite_lease_allows_exactly_one_controller_and_reclaim_increments_generation(tmp_path):
    db = tmp_path / "control" / "managed.db"
    ctx = multiprocessing.get_context("spawn")
    start, output = ctx.Event(), ctx.Queue()
    ps = [ctx.Process(target=_lease_racer, args=(str(ROOT / "plugins/operator-control/managed.py"), str(db), start, output, x)) for x in ("a", "b")]
    for p in ps: p.start()
    start.set()
    results = [output.get(timeout=10) for _ in ps]
    for p in ps: p.join(10); assert p.exitcode == 0
    assert [r[0] for r in results].count("won") == 1
    m = managed(); leases = m.SQLiteLeaseRegistry(db, clock=lambda: 100.0)
    con = sqlite3.connect(db); con.execute("UPDATE managed_leases SET expires_at=0"); con.commit(); con.close()
    reclaimed = leases.acquire("provider:one", "c", 20)
    assert reclaimed.generation == 2


def test_release_from_stale_generation_cannot_delete_reclaimed_lease(tmp_path):
    m = managed(); now = [1.0]; leases = m.SQLiteLeaseRegistry(tmp_path / "c.db", clock=lambda: now[0])
    old = leases.acquire("x", "a", 1); now[0] = 3
    current = leases.acquire("x", "b", 10)
    with pytest.raises(m.ManagedDenied, match="stale"):
        leases.release(old.token, "a", old.generation)
    assert leases.current("x").generation == current.generation


def test_adapter_capability_is_not_self_attested_and_local_sqlite_fence_is_atomic(tmp_path):
    m = managed()
    class Liar:
        supports_managed_fencing = True
        def dispatch_managed(self, *args, **kwargs): return {}
    with pytest.raises(m.ManagedDenied, match="conformance"):
        m.ManagedController.validate_adapter(Liar())
    registry = m.protected_local_adapter_registry(tmp_path / "provider.db")
    adapter = registry.adapter("local-sqlite")
    assert m.ManagedController.validate_adapter(adapter, registry) is None
    adapter.arm_fence(target="x", fencing_generation=2)
    assert adapter.mutate({"value": 1}, target="x", operation_key="op", fencing_generation=2)["provider_id"]
    adapter.arm_fence(target="x", fencing_generation=3)
    with pytest.raises(m.ManagedDenied, match="stale provider fence"):
        adapter.mutate({"value": 2}, target="x", operation_key="other", fencing_generation=1)
    assert adapter.read("x")["payload"] == {"value": 1}


def test_exact_registered_adapter_identity_rejects_subclass_and_tampered_instance(tmp_path):
    m = managed()
    registry = m.protected_local_adapter_registry(tmp_path / "provider.db")
    adapter = registry.adapter("local-sqlite")
    m.ManagedController.validate_adapter(adapter, registry)

    class Malicious(type(adapter)):
        pass

    with pytest.raises(m.ManagedDenied, match="protected adapter registry"):
        m.ManagedController.validate_adapter(Malicious(tmp_path / "evil.db"), registry)
    adapter.atomic_fencing_conformance = "managed-write-v1"
    with pytest.raises(m.ManagedDenied, match="protected adapter registry"):
        m.ManagedController.validate_adapter(adapter, registry)


def test_controlled_replacement_invalidates_provider_fence_before_replacement_can_act(tmp_path):
    m = managed(); registry = m.protected_local_adapter_registry(tmp_path / "provider.db")
    adapter = registry.adapter("local-sqlite")
    leases = m.SQLiteLeaseRegistry(tmp_path / "leases.db", clock=lambda: 10.0)
    ctl = m.ManagedController(lambda *_: {}, budget_ledger=m.SQLiteBudgetLedger(tmp_path / "budget.db"),
                              leases=leases, adapter_registry=registry)
    old = leases.acquire("x", "old-run", 30)
    adapter.arm_fence(target="x", fencing_generation=old.generation)
    replacement = ctl.replace_active_run(target="x", old_owner="old-run", new_owner="new-run",
                                         adapter=adapter, ttl_seconds=30)
    assert replacement.generation > old.generation
    with pytest.raises(m.ManagedDenied, match="stale provider fence"):
        adapter.mutate({"value": "old"}, target="x", operation_key="old-op",
                       fencing_generation=old.generation)
    assert adapter.mutate({"value": "new"}, target="x", operation_key="new-op",
                          fencing_generation=replacement.generation)["provider_id"] == "new-op"


def test_direct_reassignment_is_detected_not_claimed_prevented_while_lease_active(tmp_path):
    m = managed(); leases = m.SQLiteLeaseRegistry(tmp_path / "leases.db", clock=lambda: 10.0)
    lease = leases.acquire("x", "old-run", 30)
    with pytest.raises(m.ManagedDenied, match="direct native reassignment.*Blocked"):
        leases.detect_direct_reassignment("x", observed_owner="new-run")
    assert leases.current("x") == lease


def test_effect_boundary_rereads_native_upstream_and_broker_acceptance_not_downstream_copy(tmp_path):
    m = managed(); calls = []
    task = {"board":"b","task_id":"t","status":"running","version":1,"current_run_id":"r","claim_lock":"c","assignee":"w","profile":"w","client":"x","workspace":"/w","credential_scopes":["cred"],"cancelled":False,"requirement_version":1,"policy_version":"p","environment":"prod","dependencies":[{"task_id":"up","requirement_version":4,"artifact_id":"a","artifact_version":"v2","outcome_id":"o","outcome_version":3,"policy_version":"p","environment":"prod"}],"parent_budget":{"total":5,"spent":0,"verification_reserve":1}}
    upstream = {"board":"b","task_id":"up","status":"done","version":9,"requirement_version":4,"artifact_id":"a","artifact_version":"v2","outcome_id":"o","outcome_version":3,"policy_version":"p","environment":"prod"}
    def reader(board, task_id): calls.append(task_id); return task if task_id == "t" else upstream
    accepted = dict(task["dependencies"][0], accepted=True, revoked=False, signature="ok")
    ctl = m.ManagedController(reader, acceptance_reader=lambda task_id: accepted, acceptance_verifier=lambda r:r.get("signature")=="ok", budget_ledger=m.SQLiteBudgetLedger(tmp_path/"budget.db"), leases=m.SQLiteLeaseRegistry(tmp_path/"lease.db"))
    intent={"target":"x","requirement_version":1,"managed_envelope":{"board":"b","task_id":"t","run_id":"r","claim_lock":"c","task_version":1,"actor":"w","profile":"w","client":"x","workspace":"/w","credential_scope":"cred","target":"x","policy_version":"p","environment":"prod"}}
    ctl.check_admission(intent); assert calls == ["t", "up"]
    upstream["artifact_version"] = "stale"
    with pytest.raises(m.ManagedDenied, match="upstream"):
        ctl.check_effect_boundary(intent)


def test_second_credential_failure_restores_first_before_reporting_blocked(tmp_path):
    m = managed(); state={"k1":"enabled","k2":"enabled"}; calls=[]
    def disable(k): calls.append(("disable",k)); state[k]="disabled"; 
    def restore(k): calls.append(("restore",k)); state[k]="enabled"
    with pytest.raises(m.ManagedDenied, match="compensated"):
        m.retire_specialist({"specialist_id":"s","main_operator":"m","credential_references":["k1","k2"]}, plan_path=tmp_path/"r.json",
            disable_schedule=lambda _:None, schedule_disabled=lambda _:True, enable_schedule=lambda _:None,
            revoke_credential=disable, credential_revoked=lambda k: state[k]=="disabled" and k!="k2",
            restore_credential=restore, credential_restored=lambda k: state[k]=="enabled",
            disable_credential=disable, credential_disabled=lambda k: state[k]=="disabled",
            credential_preflight=lambda _:True, credential_restore_preflight=lambda _:True,
            transfer_task=lambda *_:None, task_owner=lambda _:"m", restore_task=lambda *_:None,
            preserve_evidence=lambda _:None, evidence_preserved=lambda _:True, resume_test=lambda *_:True)
    assert state == {"k1":"enabled","k2":"enabled"}
    assert ("restore","k1") in calls


def test_fake_batch_retirement_callback_is_rejected_before_any_effect(tmp_path):
    m = managed(); calls=[]
    with pytest.raises(TypeError):
        m.retire_specialist({"specialist_id":"s","main_operator":"m","credential_references":["k1","k2"]},
            plan_path=tmp_path/"r.json", disable_schedule=lambda x:calls.append(x), schedule_disabled=lambda _:True,
            revoke_credential=lambda x:calls.append(x), credential_revoked=lambda _:True,
            transfer_task=lambda *_:None, task_owner=lambda _:"m", preserve_evidence=lambda _:None,
            evidence_preserved=lambda _:True, resume_test=lambda *_:True,
            batch_revoke_credentials=lambda _:calls.append("fake"))
    assert calls == []


def test_all_credentials_are_disable_restore_preflighted_before_first_effect(tmp_path):
    m = managed(); calls=[]
    with pytest.raises(m.ManagedDenied, match="preflight"):
        m.retire_specialist({"specialist_id":"s","main_operator":"m","schedule_ids":["sched"],"credential_references":["k1","k2"]},
            plan_path=tmp_path/"r.json", disable_schedule=lambda x:calls.append(("schedule",x)), schedule_disabled=lambda _:True,
            enable_schedule=lambda _:None, revoke_credential=lambda _:None, credential_revoked=lambda _:True,
            restore_credential=lambda _:None, credential_restored=lambda _:True,
            disable_credential=lambda k: calls.append(("credential",k)), credential_disabled=lambda k:k != "k2",
            credential_preflight=lambda k:k != "k2", credential_restore_preflight=lambda _:True,
            transfer_task=lambda *_:None, task_owner=lambda _:"m", restore_task=lambda *_:None,
            preserve_evidence=lambda _:None, evidence_preserved=lambda _:True, resume_test=lambda *_:True)
    assert calls == []


def test_plugin_registers_real_runtime_but_default_is_disabled_and_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    plugin = load("operator_control_plugin_hardening", ROOT / "plugins/operator-control/__init__.py")
    class Ctx:
        config = {}
        def __init__(self): self.tools=[]; self.hooks=[]
        def register_tool(self, **kw): self.tools.append(kw)
        def register_hook(self, name, fn): self.hooks.append((name, fn))
    ctx=Ctx(); runtime=plugin.register(ctx)
    assert runtime.enabled is False and runtime.controller is None and runtime.broker is None
    assert {x["name"] for x in ctx.tools} == {"operator_control_execute"}
    result=json.loads(ctx.tools[0]["handler"]({}))
    assert result["success"] is False and "disabled" in result["error"]


def test_plugin_config_constructs_native_reader_shared_controller_broker_and_reviewed_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path)); os = __import__("os"); os.chmod(tmp_path, 0o700)
    board=tmp_path/"kanban.db"; sqlite3.connect(board).close()
    policy=tmp_path/"policy"; policy.mkdir(); (policy/"p.json").write_text('{"v":1}')
    key=tmp_path/"key"; key.write_bytes(b"k"*32); os.chmod(key,0o600)
    plugin=load("operator_control_plugin_configured",ROOT/"plugins/operator-control/__init__.py")
    class Ctx:
        config={"plugins":{"entries":{"operator-control":{"managed_enabled":True,"board":"default","kanban_db":str(board),"policy_root":str(policy),"signing_key_file":str(key),"supported_routes":["message.send"],"managed_adapters":["local-sqlite"]}}}}
        def __init__(self): self.tools=[]; self.hooks=[]
        def register_tool(self,**kw): self.tools.append(kw)
        def register_hook(self,*args): self.hooks.append(args)
    runtime=plugin.register(Ctx())
    assert runtime.enabled and runtime.controller is not None and runtime.broker is not None
    assert set(runtime.adapters or {}) == {"local-sqlite"}
    registered=Ctx(); plugin.register(registered)
    assert "intent" in registered.tools[0]["schema"]["parameters"]["required"]
