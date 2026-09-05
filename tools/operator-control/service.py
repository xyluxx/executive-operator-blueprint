"""Reference process-boundary checks and secret-operation facade."""
from __future__ import annotations

import os
import stat
from pathlib import Path

SECURE_ROOT = Path(__file__).resolve().parents[1] / "secure-credentials"
import sys
if str(SECURE_ROOT) not in sys.path:
    sys.path.insert(0, str(SECURE_ROOT))
from secure_credentials import vault


class SecretBoundaryUnavailable(RuntimeError):
    pass


def _owned_by(path, uid):
    return Path(path).stat().st_uid == uid


def _unreadable_by_uid(path, uid):
    """Conservative local proof: mode has no group/other bits and owner differs."""
    info = Path(path).stat()
    return info.st_uid != uid and stat.S_IMODE(info.st_mode) & 0o077 == 0


def verify_high_assurance_boundary(*, hermes_uid, broker_uid, key_path, vault_path, socket_path,
                                   peer_auth_verified=False, acl_route_verified=False):
    if hermes_uid == broker_uid:
        raise RuntimeError("high assurance requires a separate UID, container, or managed service")
    if not all(_owned_by(path, broker_uid) for path in (key_path, vault_path)):
        raise RuntimeError("broker UID must own key and vault")
    if not all(_unreadable_by_uid(path, hermes_uid) for path in (key_path, vault_path)):
        raise RuntimeError("Hermes UID can read high-assurance secret material")
    socket = Path(socket_path)
    if not socket.exists() or socket.is_symlink() or not stat.S_ISSOCK(socket.stat().st_mode):
        raise RuntimeError("IPC path must be an actual Unix socket")
    # Filesystem modes alone cannot prove authenticated peer identity or an
    # authorized client route.  A deployment must supply and attest that
    # peer-credential/ACL check; otherwise assurance remains unverified.
    if peer_auth_verified and acl_route_verified:
        return {"assurance": "high", "boundary_verified": True,
                "ipc": "authenticated-peer-acl-unix-socket"}
    return {"assurance": "configured-not-verified", "boundary_verified": False,
            "ipc": "unix-socket-peer-authentication-not-verified"}


class SecretOperationService:
    """Secret facade: broker approval IDs in, broker-generated receipts out."""

    def __init__(self, *, vault_path, executor, action_broker):
        self.vault_path = Path(vault_path)
        self.executor = executor
        self.action_broker = action_broker

    def perform_named_operation(self, *, intent, approval_id, service, operation):
        if not isinstance(approval_id, str):
            raise PermissionError("callers must pass an approval ID")
        expected_class = f"secret.{operation}"
        if intent.get("action_class") != expected_class or intent.get("material_payload", {}).get("service") != service or intent.get("material_payload", {}).get("operation") != operation:
            raise PermissionError("named secret operation does not match protected intent")

        def dispatch(_payload):
            try:
                internal = vault.perform_with_secret(service, operation, self.executor, path=self.vault_path)
            except PermissionError:
                raise
            except Exception as exc:
                raise SecretBoundaryUnavailable("secret broker unavailable; no fallback") from exc
            if not internal.get("provider_id"):
                raise SecretBoundaryUnavailable("provider supplied no internal operation identifier")
            from operator_control_schemas import material_payload_digest  # type: ignore[import-not-found]
            readback = {"account": intent["account"], "target": intent["target"],
                        "payload_digest": material_payload_digest(intent["material_payload"]),
                        "task_version": intent["task_version"], "requirement_version": intent["requirement_version"],
                        "policy_digest": self.action_broker._current_policy_digest(),
                        "operation_key": intent["operation_key"]}
            return {"provider_id": internal["provider_id"], "readback": readback}

        result = self.action_broker.execute(intent, approval_id, dispatch)
        return {"status": result["effect"], "receipt": result["provider_id"],
                "operation": operation, "account": intent["account"], "task_id": intent["task_id"]}
