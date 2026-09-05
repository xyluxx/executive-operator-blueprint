"""Fail-closed policy used by hooks and authoritative adapters."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from operator_control_schemas import canonical_json, material_payload_digest  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - package loader path
    from .schemas import canonical_json, material_payload_digest


class Denied(PermissionError):
    pass


CONTROL_FIELDS = {"approval", "approval_id", "authority", "policy", "policy_digest", "objective", "criteria", "evaluator", "schema", "protected_tests", "permission"}
ROLES = {
    "requester": "requester",
    "approver": "authenticated_approver",
    "executor": "executor",
    "credential_principal": "credential_principal",
    "recipient": "recipient",
}


def validate_untrusted_payload(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in CONTROL_FIELDS:
                raise Denied("untrusted material payload contains control field")
            validate_untrusted_payload(child)
    elif isinstance(value, list):
        for child in value:
            validate_untrusted_payload(child)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def protected_policy_digest(directory: Path | str) -> str:
    """Hash relative names and canonical JSON; any non-JSON file is byte exact."""
    root = Path(directory)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        raw = path.read_bytes()
        try:
            raw = canonical_json(json.loads(raw))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        digest.update(hashlib.sha256(raw).digest())
    return digest.hexdigest()


def check(intent: dict, approval: dict | None, expected_policy_digest: str, used: bool = False, standing: bool = False) -> None:
    if approval is None:
        raise Denied("missing approval")
    validate_untrusted_payload(intent.get("material_payload"))
    if not isinstance(intent.get("acceptance_id"), str) or not intent["acceptance_id"]:
        raise Denied("broker-loaded signed acceptance ID is required for downstream action")
    for key, expected_role in ROLES.items():
        if key == "approver":
            identity = approval.get("approver")
        else:
            identity = intent.get(key)
        if not isinstance(identity, dict) or identity.get("role") != expected_role or not identity.get("subject"):
            raise Denied(f"invalid identity role: {key}")
    if approval.get("authority_type") not in {"one_off", "standing"}:
        raise Denied("authority type must be explicit")
    if approval.get("non_transferable") is not True:
        raise Denied("approval must be non-transferable")
    if approval.get("cancelled"):
        raise Denied("approval is cancelled")
    if _parse(approval["expires_at"]) <= datetime.now(timezone.utc):
        raise Denied("approval is expired")
    if intent.get("policy_digest") != expected_policy_digest or approval.get("policy_digest") != expected_policy_digest:
        raise Denied("policy digest mismatch")
    if used:
        raise Denied("approval replay blocked")
    fields = ("action_class", "account", "target", "limits", "task_id", "task_version", "requirement_version")
    for field in fields:
        if approval.get(field) != intent.get(field):
            raise Denied(f"{field.replace('_', ' ')} mismatch")
    if not standing and approval.get("operation_key") != intent.get("operation_key"):
        raise Denied("operation key mismatch")
    if standing and approval.get("operation_key") not in {"*", intent.get("operation_key")}:
        raise Denied("operation key outside standing scope")
    if approval.get("payload_digest") != material_payload_digest(intent.get("material_payload")):
        raise Denied("material payload digest mismatch")


def check_managed_boundary(gate, envelope: dict) -> dict:
    """Run the injected live-Kanban gate; never substitute cached task state."""
    if gate is None:
        raise Denied("managed boundary gate is unavailable")
    try:
        return dict(gate.check_current(envelope))
    except PermissionError as exc:
        raise Denied(str(exc)) from exc
