import importlib.util
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

ROOT = Path(__file__).parents[1]
TOOLS = ROOT / "tools" / "operator-control"
SECURE = ROOT / "tools" / "secure-credentials"
sys.path.insert(0, str(SECURE))
from secure_credentials import crypto, vault  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service_module = load("operator_control_service", TOOLS / "service.py")
store_module = load("operator_control_secret_store", TOOLS / "store.py")


def test_high_assurance_rejects_same_uid_and_readable_secret_files(tmp_path, monkeypatch):
    key = tmp_path / "key"
    vault_file = tmp_path / "vault.db"
    key.write_text("key")
    vault_file.write_text("vault")
    with pytest.raises(RuntimeError, match="separate UID"):
        service_module.verify_high_assurance_boundary(
            hermes_uid=os.geteuid(), broker_uid=os.geteuid(), key_path=key,
            vault_path=vault_file, socket_path=tmp_path / "broker.sock",
        )


def test_high_assurance_requires_acl_restricted_unix_ipc(tmp_path, monkeypatch):
    socket = tmp_path / "broker.sock"
    socket.touch(mode=0o666)
    key = tmp_path / "key"; key.write_text("key")
    vault_file = tmp_path / "vault"; vault_file.write_text("vault")
    monkeypatch.setattr(service_module, "_owned_by", lambda path, uid: True)
    monkeypatch.setattr(service_module, "_unreadable_by_uid", lambda path, uid: True)
    with pytest.raises(RuntimeError, match="IPC"):
        service_module.verify_high_assurance_boundary(
            hermes_uid=1000, broker_uid=1001, key_path=key,
            vault_path=vault_file, socket_path=socket,
        )


class FakeActionBroker:
    def _current_policy_digest(self):
        return "f" * 64

    def execute(self, intent, approval_id, handler):
        assert approval_id == "approval-1"
        internal = handler(intent["material_payload"])
        assert internal["provider_id"]
        return {"effect": "confirmed-success", "provider_id": "opr_broker_generated"}


def secret_intent(operation="domain.lock"):
    return {"schema_version": 1, "operation_key": "op-secret", "action_class": f"secret.{operation}",
            "account": "registrar:primary", "target": "example.test", "task_id": "task-1",
            "task_version": 1, "requirement_version": 1, "policy_digest": "f" * 64,
            "material_payload": {"service": "registrar", "operation": operation}}


def test_model_api_never_returns_plaintext_or_retrievable_link(tmp_path, monkeypatch):
    fixture = "SECRET-FIXTURE-DO-NOT-LEAK"
    monkeypatch.setenv("SECURE_CREDENTIALS_MASTER_KEY", Fernet.generate_key().decode())
    db = tmp_path / "vault.db"
    vault.put("registrar", "https://registrar.test", "owner", fixture,
              owner_scope="high-impact", authorized_principals=["broker"],
              authorized_recipients=["owner"], path=db)
    api = service_module.SecretOperationService(vault_path=db, action_broker=FakeActionBroker(), executor=lambda operation, secret: {
        "provider_id": "opaque-provider-reference", "provider_status": "delivered",
    })
    result = api.perform_named_operation(intent=secret_intent(), approval_id="approval-1", service="registrar", operation="domain.lock")
    rendered = json.dumps(result)
    assert result["receipt"] == "opr_broker_generated"
    assert fixture not in rendered and "PLAINTEXT-HIGH-IMPACT" not in rendered
    assert "secret" not in rendered.lower() and "url" not in rendered.lower()
    assert not hasattr(api, "get_plaintext")


@pytest.mark.parametrize("field,value", [("action_class", "secret.domain.transfer"), ("service", "other"), ("operation", "domain.transfer")])
def test_wrong_scope_is_denied(tmp_path, monkeypatch, field, value):
    monkeypatch.setenv("SECURE_CREDENTIALS_MASTER_KEY", Fernet.generate_key().decode())
    db = tmp_path / "vault.db"
    vault.put("registrar", "https://registrar.test", "owner", "fixture", owner_scope="high-impact",
              authorized_principals=["broker"], authorized_recipients=["owner"], path=db)
    api = service_module.SecretOperationService(vault_path=db, executor=lambda *_: {}, action_broker=FakeActionBroker())
    request = secret_intent()
    if field == "action_class": request[field] = value
    else: request["material_payload"][field] = value
    with pytest.raises(PermissionError):
        api.perform_named_operation(intent=request, approval_id="approval-1", service="registrar", operation="domain.lock")


def test_broker_failure_has_no_weaker_fallback(tmp_path):
    class FailedBroker(FakeActionBroker):
        def execute(self, *args, **kwargs): raise service_module.SecretBoundaryUnavailable("down")
    api = service_module.SecretOperationService(vault_path=tmp_path / "missing.db", executor=lambda *_: {}, action_broker=FailedBroker())
    with pytest.raises(service_module.SecretBoundaryUnavailable):
        api.perform_named_operation(intent=secret_intent(), approval_id="approval-1", service="registrar", operation="domain.lock")


def test_versioned_store_backup_restore_and_unknown_safe_rollback(tmp_path):
    db = tmp_path / "control.db"
    con = store_module.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 4
    con.close()
    backup = store_module.backup_before_migration(db, tmp_path / "backups")
    con = sqlite3.connect(db)
    con.execute("UPDATE operations SET effect='unknown' WHERE 0")
    con.close()
    restored = tmp_path / "restored.db"
    store_module.restore_backup(backup, restored)
    assert sqlite3.connect(restored).execute("PRAGMA user_version").fetchone()[0] == 4
    con = store_module.connect(db)
    con.execute("INSERT INTO operations(operation_key,intent_json,intent_fingerprint,state,effect) VALUES('u','{}','digest','reconciling','unknown')")
    con.close()
    with pytest.raises(RuntimeError, match="unknown"):
        store_module.prepare_rollback(db)


def test_limited_local_vault_is_explicitly_not_high_assurance(tmp_path, monkeypatch):
    monkeypatch.setenv("SECURE_CREDENTIALS_MASTER_KEY", Fernet.generate_key().decode())
    assert crypto.secret_tier("limited-local", high_impact=True)["allowed"] is False
    assert vault.deployment_assurance("limited-local", owner_scope="high-impact") == "prohibited"
