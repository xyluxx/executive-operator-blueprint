import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
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


def modules():
    schemas = load("operator_control_schemas", ROOT / "plugins/operator-control/schemas.py")
    load("operator_control_policy", ROOT / "plugins/operator-control/policy.py")
    load("operator_control_store", ROOT / "tools/operator-control/store.py")
    managed = load("operator_control_managed", ROOT / "plugins/operator-control/managed.py")
    broker = load("operator_control_broker_integration", ROOT / "tools/operator-control/broker.py")
    return schemas, managed, broker


def live(**changes):
    value = {"board": "b", "task_id": "t", "status": "running", "version": 2,
             "current_run_id": "r1", "claim_lock": "c1", "assignee": "worker", "profile": "worker",
             "client": "client", "workspace": "/w", "credential_scopes": ["cred"], "cancelled": False,
             "requirement_version": 1, "policy_version": "p1", "environment": "prod",
             "dependencies": [], "acceptances": [], "parent_budget": {"total": 10, "spent": 0, "verification_reserve": 2}}
    value.update(changes)
    return value


def envelope(**changes):
    value = {"board": "b", "task_id": "t", "run_id": "r1", "claim_lock": "c1", "task_version": 2,
             "actor": "worker", "profile": "worker", "client": "client", "workspace": "/w",
             "credential_scope": "cred", "target": "provider:item", "budget_amount": 3,
             "requirement_version": 1, "policy_version": "p1", "environment": "prod"}
    value.update(changes)
    return value


def action(schemas, **changes):
    payload = {"body": "x"}
    value = {"schema_version": 1, "operation_key": "op", "action_class": "message.send",
             "requester": {"role": "requester", "subject": "r"},
             "executor": {"role": "executor", "subject": "e"},
             "credential_principal": {"role": "credential_principal", "subject": "c"},
             "recipient": {"role": "recipient", "subject": "to"}, "account": "a", "target": "provider:item",
             "material_payload": payload, "limits": {"max_cost_usd": 3}, "task_id": "t", "task_version": 2,
             "requirement_version": 1, "artifact_id": "managed-output", "artifact_version": "v1", "target_version": "v1",
             "environment": {"name": "prod", "version": "1"}, "acceptance_id": "managed-acceptance", "policy_digest": "caller", "managed_envelope": envelope()}
    value.update(changes)
    return value


def approval(schemas, policy_digest):
    now = datetime.now(timezone.utc)
    return {"schema_version": 1, "approval_id": "ap", "authority_type": "one_off",
            "approver": {"role": "authenticated_approver", "subject": "owner"}, "authority_source": "test",
            "issuance_channel": "test", "non_transferable": True, "action_class": "message.send", "account": "a",
            "target": "provider:item", "payload_digest": schemas.material_payload_digest({"body": "x"}),
            "limits": {"max_cost_usd": 3}, "task_id": "t", "task_version": 2, "requirement_version": 1,
            "operation_key": "op", "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(),
            "cancelled": False, "policy_digest": policy_digest}


def make_broker(tmp_path, current, *, managed_mode=True, controller=True):
    schemas, managed, broker = modules()
    assets = tmp_path / "assets"; assets.mkdir(); (assets / "p.json").write_text('{"v":1}')
    ledger = managed.SQLiteBudgetLedger(tmp_path / "budget" / "managed.db")
    registry = managed.protected_local_adapter_registry(tmp_path / "provider" / "local.db") if controller else None
    ctl = managed.ManagedController(lambda *_: current[0], acceptance_verifier=lambda record: record.get("signature") == "ok",
                                    budget_ledger=ledger, adapter_registry=registry) if controller else None
    holder = {}
    roles = {"requester": "r", "executor": "e", "credential_principal": "c", "recipient": "to", "approver": "owner", "evidence_collector": "collector", "reviewer": "reviewer", "accepter": "accepter", "exception_authority": "risk"}
    resolver = lambda _: {"authenticated": True, "roles": roles}
    acceptance_resolver = lambda aid: {"authenticated": True, "record": holder[aid], "actor": {"authenticated": True, "role": "accepter", "subject": "accepter", "authority_source": "test", "issuance_channel": "test"}}
    b = broker.ActionBroker(tmp_path / "db" / "control.db", policy_root=assets,
                            supported_routes={"message.send"}, signing_key=b"z" * 32,
                            authenticate_approver=lambda _: {"authenticated": True, "subject": "owner", "authority_source": "test", "issuance_channel": "test"}, resolve_identities=resolver, resolve_acceptance=acceptance_resolver, managed_mode=managed_mode, managed_controller=ctl)
    now = datetime.now(timezone.utc)
    holder["managed-acceptance"] = {"record_version": "2", "acceptance_id": "managed-acceptance", "status": "accepted", "disposition": "success", "task_id": "t", "task_version": 2, "requirement_version": 1, "artifact_id": "managed-output", "artifact_version": "v1", "target_id": "provider:item", "target_version": "v1", "environment": {"name": "prod", "version": "1"}, "policy_version": 1, "policy_digest": b._current_policy_digest(), "submission_id": "managed-submission", "worker_id": "worker", "accepter_id": "accepter", "criterion_results": [], "criteria_digest": "sha256:" + "a"*64, "evidence_digest": "sha256:" + "b"*64, "reasons": [], "issued_at": now.isoformat(), "accepted_at": now.isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat()}
    b.issue_acceptance("managed-acceptance", auth_context={})
    b.issue_approval(approval(schemas, b._current_policy_digest()), auth_context={})
    return schemas, managed, b


def reviewed_adapter(broker):
    return broker.managed_controller.adapter_registry.adapter("local-sqlite")


def test_managed_mode_fails_closed_without_controller_or_native_reader(tmp_path):
    schemas, managed, broker = modules()
    assets = tmp_path / "a"; assets.mkdir(); (assets / "p").write_text("x")
    with pytest.raises(ValueError, match="managed controller"):
        broker.ActionBroker(tmp_path / "d" / "x.db", policy_root=assets, supported_routes={"message.send"},
                            signing_key=b"x" * 32, managed_mode=True)
    with pytest.raises(ValueError, match="native reader"):
        managed.ManagedController(None)


def test_managed_mode_cannot_be_downgraded_by_intent_and_generic_handler_is_blocked(tmp_path):
    current = [live()]; schemas, managed, b = make_broker(tmp_path, current)
    intent = action(schemas); intent["managed_mode"] = False
    with pytest.raises(Exception): b.execute(intent, "ap", lambda _: {})
    intent.pop("managed_mode")
    with pytest.raises(Exception, match="managed provider adapter"):
        b.execute(intent, "ap", lambda _: {})


def test_managed_envelope_cannot_execute_through_unmanaged_broker(tmp_path):
    current = [live()]; schemas, managed, b = make_broker(tmp_path, current, managed_mode=False, controller=False)
    with pytest.raises(Exception, match="managed controller"):
        b.execute(action(schemas), "ap", lambda _: {})


def test_broker_reaches_atomic_adapter_with_lease_budget_and_current_fence(tmp_path):
    current = [live()]; schemas, managed, b = make_broker(tmp_path, current)
    intent = action(schemas); adapter = reviewed_adapter(b)
    result = b.execute(intent, "ap", adapter)
    assert result["effect"] == "confirmed-success" and adapter.read("provider:item") is not None
    assert b.managed_controller.budget_spent("b", "t") == 3


def test_same_worker_cannot_reacquire_exact_target_until_release_or_expiry():
    _, managed, _ = modules(); now = [1.0]; leases = managed.TargetLeaseRegistry(clock=lambda: now[0])
    first = leases.acquire("x", "same", 10)
    with pytest.raises(managed.ManagedDenied, match="already"):
        leases.acquire("x", "same", 10)
    leases.release(first.token, "same")
    leases.acquire("x", "same", 10)
    now[0] = 20
    leases.acquire("x", "same", 10)


def test_broker_rejects_revoked_or_version_stale_upstream_acceptance(tmp_path):
    accepted = {"task_id": "up", "requirement_version": 4, "artifact_id": "a", "artifact_version": "v2",
                "outcome_id": "o", "outcome_version": 3, "policy_version": "p2", "environment": "prod",
                "accepted": True, "revoked": True, "signature": "ok"}
    current = [live(dependencies=[dict(accepted)], acceptances=[dict(accepted)])]
    schemas, managed, b = make_broker(tmp_path, current); adapter = reviewed_adapter(b)
    with pytest.raises(Exception, match="upstream"):
        b.execute(action(schemas), "ap", adapter)


def test_broker_blocks_cancelled_task_and_unaccepted_parent_before_operation(tmp_path):
    current = [live(cancelled=True)]; schemas, managed, b = make_broker(tmp_path, current)
    adapter = reviewed_adapter(b)
    with pytest.raises(Exception, match="cancelled"):
        b.execute(action(schemas), "ap", adapter)
    current[0] = live(children=[{"accepted": True}], parent_acceptance=None)
    with pytest.raises(Exception, match="integrated parent"):
        b.execute(action(schemas), "ap", adapter)


def test_unreviewed_callback_adapter_is_blocked(tmp_path):
    current = [live()]; schemas, managed, b = make_broker(tmp_path, current)
    class DuplicateAdapter:
        supports_managed_fencing = True
    with pytest.raises(Exception, match="conformance"):
        b.execute(action(schemas), "ap", DuplicateAdapter())


def test_native_kanban_reader_reads_current_task_run_metadata(tmp_path):
    _, managed, _ = modules(); db = tmp_path / "kanban.db"; con = sqlite3.connect(db)
    con.executescript("CREATE TABLE tasks(id TEXT PRIMARY KEY,status TEXT,assignee TEXT,workspace_path TEXT,claim_lock TEXT,current_run_id INTEGER,tenant TEXT); CREATE TABLE task_runs(id INTEGER PRIMARY KEY,task_id TEXT,profile TEXT,status TEXT,claim_lock TEXT,metadata TEXT); CREATE TABLE task_events(id INTEGER PRIMARY KEY,task_id TEXT,kind TEXT,payload TEXT);")
    metadata = {"client": "client", "credential_scopes": ["cred"], "requirement_version": 1, "policy_version": "p1", "environment": "prod", "dependencies": [], "acceptances": [], "parent_budget": {"total": 10, "spent": 0, "verification_reserve": 2}}
    con.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?)", ("t", "running", "worker", "/w", "c1", 7, "client"))
    con.execute("INSERT INTO task_runs VALUES(?,?,?,?,?,?)", (7, "t", "worker", "running", "c1", json.dumps(metadata)))
    con.execute("INSERT INTO task_events VALUES(2,'t','claimed','{}')"); con.commit(); con.close()
    snap = managed.NativeKanbanReader(db, board="b").read("b", "t")
    assert snap["current_run_id"] == "7" and snap["version"] == 2 and snap["credential_scopes"] == ["cred"]
