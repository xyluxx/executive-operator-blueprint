import importlib.util
import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins/operator-control"
TOOLS = ROOT / "tools/operator-control"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


schemas = load("operator_control_schemas", PLUGIN / "schemas.py")
policy = load("operator_control_policy", PLUGIN / "policy.py")
store = load("operator_control_store", TOOLS / "store.py")
broker_mod = load("operator_control_defect_broker", TOOLS / "broker.py")


def utc(seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def actor(subject, role="approver"):
    return {
        "authenticated": True,
        "subject": subject,
        "role": role,
        "authority_source": "iam:protected",
        "issuance_channel": "console:trusted",
    }


def identities():
    return {
        "authenticated": True,
        "roles": {
            "requester": "agent:req",
            "executor": "adapter:mail",
            "credential_principal": "mailbox:sender",
            "recipient": "person:alice",
            "approver": "human:owner",
            "evidence_collector": "collector:ci",
            "reviewer": "human:reviewer",
            "accepter": "human:accepter",
            "exception_authority": "human:risk",
        },
    }


def intent(key):
    return {
        "schema_version": 1,
        "operation_key": key,
        "action_class": "message.send",
        "requester": {"role": "requester", "subject": "forged"},
        "executor": {"role": "executor", "subject": "forged"},
        "credential_principal": {"role": "credential_principal", "subject": "forged"},
        "recipient": {"role": "recipient", "subject": "forged"},
        "account": "mailbox:sender",
        "target": "person:alice",
        "material_payload": {"body": "hello"},
        "limits": {"max_cost_usd": 0},
        "task_id": "t",
        "task_version": 2,
        "requirement_version": 3,
        "artifact_id": "art",
        "artifact_version": "1",
        "target_version": "1",
        "environment": {"name": "prod", "version": "1"},
        "acceptance_id": "ac",
        "policy_digest": "ignored",
    }


def acceptance_record(broker, action):
    return {
        "record_version": "2",
        "acceptance_id": "ac",
        "status": "accepted",
        "disposition": "success",
        "task_id": "t",
        "task_version": 2,
        "requirement_version": 3,
        "artifact_id": "art",
        "artifact_version": "1",
        "target_id": "person:alice",
        "target_version": "1",
        "environment": action["environment"],
        "policy_version": "1",
        "policy_digest": broker._current_policy_digest(),
        "submission_id": "sub",
        "worker_id": "worker:x",
        "accepter_id": "human:accepter",
        "criterion_results": ["C"],
        "criteria_digest": "sha256:" + "a" * 64,
        "evidence_digest": "sha256:" + "b" * 64,
        "reasons": [],
        "issued_at": utc(-1),
        "accepted_at": utc(-1),
        "expires_at": utc(300),
    }


def standing_approval(action):
    return {
        "schema_version": 1,
        "approval_id": "standing-ap",
        "authority_type": "standing",
        "approver": {"role": "authenticated_approver", "subject": "forged"},
        "authority_source": "forged",
        "issuance_channel": "forged",
        "non_transferable": True,
        "action_class": action["action_class"],
        "account": action["account"],
        "target": action["target"],
        "payload_digest": schemas.material_payload_digest(action["material_payload"]),
        "limits": action["limits"],
        "task_id": "t",
        "task_version": 2,
        "requirement_version": 3,
        "operation_key": "*",
        "issued_at": utc(-1),
        "expires_at": utc(300),
        "cancelled": False,
    }


def make_broker(tmp_path):
    policy_root = tmp_path / "policy"
    policy_root.mkdir()
    (policy_root / "policy.json").write_text('{"version":1}')
    records = {}

    def resolve_acceptance(acceptance_id):
        return {
            "authenticated": True,
            "actor": actor("human:accepter", "accepter"),
            "record": records.get(acceptance_id),
        }

    broker = broker_mod.ActionBroker(
        tmp_path / "private/control.db",
        policy_root=policy_root,
        supported_routes={"message.send"},
        signing_key=b"x" * 32,
        authenticate_approver=lambda _: actor("human:owner"),
        resolve_identities=lambda _: identities(),
        resolve_acceptance=resolve_acceptance,
    )
    first = intent("op-1")
    records["ac"] = acceptance_record(broker, first)
    broker.issue_acceptance("ac", auth_context={})
    broker.issue_approval(standing_approval(first), auth_context={})
    return broker, first


def readback(broker, action):
    return {
        "account": action["account"],
        "target": action["target"],
        "payload_digest": schemas.material_payload_digest(action["material_payload"]),
        "task_version": 2,
        "requirement_version": 3,
        "policy_digest": broker._current_policy_digest(),
        "operation_key": action["operation_key"],
    }


class Context:
    config = {}

    def __init__(self):
        self.tools = []
        self.hooks = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))


def test_registered_hook_is_the_strict_hook_and_fails_closed(monkeypatch):
    plugin = load("operator_control_plugin_registered_hook", PLUGIN / "__init__.py")

    class Gate:
        def __init__(self):
            self.calls = []

        def check_effect_boundary(self, value):
            self.calls.append(value)
            return {}

    gate = Gate()
    runtime = plugin.Runtime(True, gate, object(), {"local-sqlite": object()})
    monkeypatch.setattr(plugin, "configure", lambda _ctx: runtime)
    ctx = Context()
    plugin.register(ctx)
    hook = ctx.hooks[0][1]
    assert hook("terminal", {"command": "send"})["allow"] is False
    assert hook("browser_exec", {"code": "write"})["allow"] is False
    assert hook("future_plugin_tool", {})["allow"] is False
    assert hook("read_file", {"path": "README.md"})["allow"] is True
    assert hook("operator_control_execute", {"approval_id": "ap", "intent": {}})["allow"] is False
    valid = {"approval_id": "ap", "intent": {"operation_key": "op", "managed_envelope": {"task_id": "t"}}}
    assert hook("operator_control_execute", valid)["allow"] is True
    assert gate.calls == [valid["intent"]]


def configured_context(tmp_path, key_path):
    board = tmp_path / "kanban.db"
    sqlite3.connect(board).close()
    policy_root = tmp_path / "policy"
    policy_root.mkdir(exist_ok=True)
    (policy_root / "p.json").write_text('{"v":1}')
    ctx = Context()
    ctx.config = {
        "plugins": {
            "entries": {
                "operator-control": {
                    "managed_enabled": True,
                    "board": "default",
                    "kanban_db": str(board),
                    "policy_root": str(policy_root),
                    "signing_key_file": str(key_path),
                    "supported_routes": ["message.send"],
                    "managed_adapters": ["local-sqlite"],
                }
            }
        }
    }
    return ctx


def test_signing_key_is_hardened_and_unavailable_keys_disable_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    os.chmod(tmp_path, 0o700)
    plugin = load("operator_control_plugin_key_hardening", PLUGIN / "__init__.py")
    missing = plugin.configure(configured_context(tmp_path, tmp_path / "missing-key"))
    assert missing.enabled is False and missing.error == "signing key unavailable"

    target = tmp_path / "actual-key"
    target.write_bytes(b"k" * 32)
    os.chmod(target, 0o600)
    symlink = tmp_path / "linked-key"
    symlink.symlink_to(target)
    linked = plugin.configure(configured_context(tmp_path, symlink))
    assert linked.enabled is False and linked.error == "signing key unavailable"

    key = tmp_path / "mode-key"
    key.write_bytes(b"k" * 32)
    os.chmod(key, 0o644)
    runtime = plugin.configure(configured_context(tmp_path, key))
    assert runtime.enabled is True
    assert key.stat().st_mode & 0o777 == 0o600


def test_plugin_returns_fixed_error_and_logs_private_detail(monkeypatch, caplog):
    plugin = load("operator_control_plugin_error_redaction", PLUGIN / "__init__.py")

    class FailingBroker:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("private-path-sentinel")

    runtime = plugin.Runtime(True, None, FailingBroker(), {"local-sqlite": object()})
    monkeypatch.setattr(plugin, "configure", lambda _ctx: runtime)
    ctx = Context()
    plugin.register(ctx)
    result = json.loads(ctx.tools[0]["handler"]({"approval_id": "ap", "adapter": "local-sqlite", "intent": {}}))
    assert result == {"success": False, "error": "protected operation denied or failed"}
    assert "private-path-sentinel" not in json.dumps(result)
    assert "private-path-sentinel" in caplog.text


def test_standing_approval_revokes_after_completed_success_and_blocks_future_use(tmp_path):
    broker, first = make_broker(tmp_path)
    completed = broker.execute(first, "standing-ap", lambda _: {"provider_id": "ok", "readback": readback(broker, first)}, identity_context={})
    assert completed["effect"] == "confirmed-success"
    broker.revoke_approval("standing-ap", auth_context={})
    assert broker.approval_status("standing-ap")["state"] == "revoked"
    con = store.connect(broker.db_path)
    historical = json.loads(con.execute("SELECT result_json FROM operations WHERE operation_key='op-1'").fetchone()[0])
    con.close()
    assert historical == completed
    with pytest.raises(policy.Denied, match="revoked"):
        broker.execute(intent("op-2"), "standing-ap", lambda _: pytest.fail("future effect must not run"), identity_context={})


def test_revocation_after_confirmed_failure_preserves_history(tmp_path):
    broker, first = make_broker(tmp_path)
    unknown = broker.execute(first, "standing-ap", lambda _: "uncertain", identity_context={})
    assert unknown["effect"] == "unknown"
    failed = broker.reconcile("op-1", readback(broker, first), reconciler={"authenticated": True, "subject": "provider:mail"}, effect="confirmed-failure")
    broker.revoke_approval("standing-ap", auth_context={})
    assert broker.approval_status("standing-ap")["state"] == "revoked"
    assert failed["effect"] == "confirmed-failure"


def test_unknown_effect_can_reconcile_after_future_authority_is_revoked(tmp_path):
    broker, first = make_broker(tmp_path)
    assert broker.execute(first, "standing-ap", lambda _: "uncertain", identity_context={})["effect"] == "unknown"
    broker.revoke_approval("standing-ap", auth_context={})
    with pytest.raises(policy.Denied, match="unknown effect"):
        broker.execute(first, "standing-ap", lambda _: pytest.fail("blind retry"), identity_context={})
    reconciled = broker.reconcile("op-1", readback(broker, first), reconciler={"authenticated": True, "subject": "provider:mail"})
    assert reconciled["effect"] == "confirmed-success"
    assert broker.approval_status("standing-ap")["state"] == "revoked"


def test_approval_status_uses_canonical_approval_and_survives_restart(tmp_path):
    broker, _ = make_broker(tmp_path)
    assert broker.approval_status("standing-ap")["state"] == "active"
    assert broker.approval_status("missing-id")["state"] == "missing"
    broker.revoke_approval("standing-ap", auth_context={})
    assert broker.approval_status("standing-ap")["state"] == "revoked"
    reopened = broker_mod.ActionBroker(
        broker.db_path,
        policy_root=broker.policy_root,
        supported_routes={"message.send"},
        signing_key=b"x" * 32,
        authenticate_approver=lambda _: actor("human:owner"),
        resolve_identities=lambda _: identities(),
    )
    assert reopened.approval_status("standing-ap")["state"] == "revoked"
    assert reopened.approval_status("missing-id")["state"] == "missing"


def test_correction_driven_revocation_after_completed_effect_keeps_metadata_and_history(tmp_path):
    broker, first = make_broker(tmp_path)
    completed = broker.execute(first, "standing-ap", lambda _: {"provider_id": "ok", "readback": readback(broker, first)}, identity_context={})
    prepared = broker.prepare_approval_revocation(
        "standing-ap",
        correction_id="corr-1",
        predecessor={"claim_id": "standing", "version": 1},
        replacement={"claim_id": "withdrawn", "version": 2},
    )
    status = broker.commit_approval_revocation(prepared)
    assert status["state"] == "revoked"
    assert status["correction_id"] == "corr-1"
    assert status["replacement"] == {"claim_id": "withdrawn", "version": 2}
    con = store.connect(broker.db_path)
    historical = json.loads(con.execute("SELECT result_json FROM operations WHERE operation_key='op-1'").fetchone()[0])
    con.close()
    assert historical == completed


def test_dispatch_and_revocation_follow_writer_lock_order(tmp_path):
    broker, first = make_broker(tmp_path)
    started = threading.Event()
    release = threading.Event()
    completed = []
    revoked = []

    def handler(_):
        started.set()
        assert release.wait(3)
        return {"provider_id": "ok", "readback": readback(broker, first)}

    dispatch = threading.Thread(target=lambda: completed.append(broker.execute(first, "standing-ap", handler, identity_context={})))
    dispatch.start()
    assert started.wait(2)
    withdrawal = threading.Thread(target=lambda: revoked.append(broker.revoke_approval("standing-ap", auth_context={})))
    withdrawal.start()
    time.sleep(0.1)
    assert withdrawal.is_alive()
    release.set()
    dispatch.join(3)
    withdrawal.join(3)
    assert completed[0]["effect"] == "confirmed-success"
    assert broker.approval_status("standing-ap")["state"] == "revoked"
