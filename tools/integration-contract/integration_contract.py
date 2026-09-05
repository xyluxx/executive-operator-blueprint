"""Pure provider-neutral integration contract harness and fake adapter."""
from __future__ import annotations

import hashlib
import json
import re
import base64
import binascii
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

CAPABILITY_STATUSES = ("Native", "Blueprint", "Bundled", "Configured", "Verified", "Optional", "Planned", "Blocked")
COMPOSIO_EVIDENCE = ("pricing", "plan", "tool_limits", "trigger_limits", "scopes", "data_policy", "write_behavior")
MAX_EVIDENCE_AGE_DAYS = 30
AUTHORITY_REGISTRY_SHA256 = "d31e1bc3ec1dcb081b86f4d36be64f5b02c2740fabe19919a3196c6789edd2f0"  # pragma: allowlist secret
AUTHORITY_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "contracts" / "evidence-authorities.json"
EVIDENCE_PUBLIC_KEY_B64 = "CCK7ufdiEQtbymSIV0+u4G1MN43zYPVk5njzw50OygU="  # pragma: allowlist secret -- public verification key; private key is not bundled
PLACEHOLDERS = frozenset({"unknown", "unselected", "placeholder", "n/a", "none", "tbd", "todo"})
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
SPDX_LICENSES = frozenset({
    "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "GPL-2.0-only", "GPL-3.0-only",
    "ISC", "LGPL-2.1-only", "LGPL-3.0-only", "MIT", "MPL-2.0", "Unlicense",
})


class PromotionError(ValueError):
    """Raised when evidence is insufficient for a status promotion."""


class UnknownEffect(RuntimeError):
    """Raised when a write may have succeeded and must be reconciled."""


def _digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_hash(value: str, pattern) -> bool:
    if not pattern.fullmatch(value or ""):
        return False
    return not any(value == value[:size] * (len(value) // size) for size in range(1, len(value) // 2 + 1) if len(value) % size == 0)


class EvidenceAuthorityResolver:
    """Read-only, integrity-pinned registry lookup; it cannot issue receipts."""

    def __init__(self, registry_path=AUTHORITY_REGISTRY_PATH):
        raw = Path(registry_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != AUTHORITY_REGISTRY_SHA256:
            raise PromotionError("evidence authority registry integrity check failed")
        registry = json.loads(raw)
        self.signer = registry["signer"]
        entries = {}
        for source in registry["authorities"]:
            item = dict(source)
            if not SHA256_RE.fullmatch(item.get("content_digest", "")):
                raise PromotionError("evidence authority registry integrity check failed")
            item["required_assertions"] = tuple(item["required_assertions"])
            entries[item["id"]] = MappingProxyType(item)
        self.entries = MappingProxyType(entries)
        if len(self.entries) != len(registry["authorities"]):
            raise PromotionError("evidence authority registry integrity check failed")

    def resolve(self, provider: str, kind: str, authority_id: str, supplied_url: str):
        entry = self.entries.get(authority_id)
        if not entry or entry["provider"] != provider or entry["kind"] != kind or entry["url"] != supplied_url:
            raise PromotionError("exact registered evidence authority required")
        return entry


def _receipt_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class EvidenceReceiptVerifier:
    """Model-facing verifier pinned to the onboarding authority public key."""

    def __init__(self, registry=None):
        self.registry = registry or EvidenceAuthorityResolver()
        self._verification_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(EVIDENCE_PUBLIC_KEY_B64))

    def verify(self, receipt, provider: str, kind: str, authority_id: str, supplied_url: str, now: datetime):
        try:
            payload = receipt["payload"]
            signature = base64.b64decode(receipt["signature"], validate=True)
            self._verification_key.verify(signature, _receipt_bytes(payload))
            entry = self.registry.resolve(provider, kind, authority_id, supplied_url)
            expected = {
                "authority_id": entry["id"], "provider": entry["provider"], "kind": entry["kind"],
                "canonical_url": entry["url"], "title": entry["title"],
                "content_digest": entry["content_digest"], "assertions": list(entry["required_assertions"]),
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise PromotionError("authenticated trusted-fetch receipt required")
            retrieved = datetime.fromisoformat(payload["retrieved_at"].replace("Z", "+00:00"))
            if retrieved.tzinfo is None:
                raise ValueError
            age = now - retrieved
            if age.total_seconds() < 0 or age.total_seconds() > MAX_EVIDENCE_AGE_DAYS * 86400:
                raise PromotionError("stale official evidence for Composio setup")
            return payload
        except PromotionError:
            raise
        except (InvalidSignature, KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise PromotionError("authenticated trusted-fetch receipt required") from exc


class EvidenceFetchAuthority:
    """Privileged issuer: signs only exact, successful trusted fetch results."""

    def __init__(self, private_key: bytes, trusted_fetch: Callable, *, now=None, registry=None):
        self.__key = Ed25519PrivateKey.from_private_bytes(private_key)
        self.__fetch = trusted_fetch
        self.__now = now or (lambda: datetime.now(timezone.utc))
        self.__registry = registry or EvidenceAuthorityResolver()

    def issue(self, provider: str, kind: str, authority_id: str, supplied_url: str):
        entry = self.__registry.resolve(provider, kind, authority_id, supplied_url)
        try:
            fetched = self.__fetch(entry)
        except Exception as exc:
            raise PromotionError("trusted fetch unavailable") from exc
        if not isinstance(fetched, dict) or not isinstance(fetched.get("content"), bytes):
            raise PromotionError("trusted fetch unavailable")
        if fetched.get("requested_url") != entry["url"] or fetched.get("final_url") != entry["url"]:
            raise PromotionError("trusted fetch redirect or canonical URL mismatch")
        if fetched.get("title") != entry["title"]:
            raise PromotionError("trusted fetch title mismatch")
        if not isinstance(fetched.get("assertions"), (list, tuple)) or list(fetched["assertions"]) != list(entry["required_assertions"]):
            raise PromotionError("trusted fetch assertions mismatch")
        digest = hashlib.sha256(fetched["content"]).hexdigest()
        if digest != entry["content_digest"]:
            raise PromotionError("trusted fetch content digest mismatch")
        retrieved = self.__now()
        if not isinstance(retrieved, datetime) or retrieved.tzinfo is None:
            raise PromotionError("trusted fetch timestamp must be current and timezone-aware")
        payload = {
            "authority_id": entry["id"], "provider": entry["provider"], "kind": entry["kind"],
            "canonical_url": entry["url"], "title": entry["title"], "content_digest": digest,
            "assertions": list(entry["required_assertions"]),
            "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        }
        return {"payload": payload, "signature": base64.b64encode(self.__key.sign(_receipt_bytes(payload))).decode("ascii")}


_DEFAULT_RESOLVER = None


def default_authority_resolver():
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None:
        _DEFAULT_RESOLVER = EvidenceAuthorityResolver()
    return _DEFAULT_RESOLVER


def authority_url(provider: str, kind: str) -> str:
    entry = next((item for item in default_authority_resolver().entries.values()
                  if item["provider"] == provider and item["kind"] == kind), None)
    if not entry:
        raise PromotionError("exact registered evidence authority required")
    return entry["url"]


def _resolve_evidence(resolver, provider, kind, value, authority_id=None):
    if isinstance(value, dict):
        supplied_url = value.get("source")
        authority_id = value.get("authority_id")
    else:
        supplied_url = value
    authority_id = authority_id or next((item["id"] for item in resolver.entries.values()
                                         if item["provider"] == provider and item["kind"] == kind and item["url"] == supplied_url), None)
    resolved = resolver.resolve(provider, kind, authority_id, supplied_url)
    if isinstance(value, dict):
        for field in ("provider", "kind", "canonical_url", "signed_by", "signature", "content_digest", "title", "required_assertions"):
            if field in value and value[field] != resolved[field]:
                raise PromotionError("exact registered evidence authority required")
    return resolved


def _nonblank_list(value) -> bool:
    return isinstance(value, list) and bool(value) and all(_concrete(item) for item in value)


def _concrete(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized not in PLACEHOLDERS and not any(
        normalized == marker or normalized.startswith(marker + "-")
        for marker in ("unknown", "unselected", "placeholder", "todo", "tbd")
    )


def _immutable_ref(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if value.startswith("commit:"):
        return _valid_hash(value[7:], COMMIT_RE)
    if value.startswith("sha256:"):
        return _valid_hash(value[7:], SHA256_RE)
    if value.startswith("tag:"):
        return bool(VERSION_RE.fullmatch(value[4:]))
    if value.startswith("version:"):
        return bool(VERSION_RE.fullmatch(value[8:]))
    return False


def validate_capability_status(status: str) -> str:
    if status not in CAPABILITY_STATUSES:
        raise ValueError(f"non-canonical capability status: {status!r}")
    return status


def validate_integration_record(record, *, current_state=None, now=None, official_domains=None, authority_resolver=None):
    """Return controlled semantic errors JSON Schema cannot express."""
    errors = []
    try:
        resolver = authority_resolver or default_authority_resolver()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [f"evidence authority registry integrity failure: {exc}"]
    clock = now or datetime.now(timezone.utc)
    review = record.get("candidate_review") if isinstance(record, dict) else None
    if not isinstance(review, dict):
        return ["candidate_review must be an object"]
    provider = record.get("provider")
    if provider == "unselected":
        provider = "google"  # the shipped disabled example's reviewed candidate
    for field, kind in (("source", "source"), ("data_policy", "data_policy"), ("cost_evidence", "cost")):
        try:
            resolved = _resolve_evidence(resolver, provider, kind, review.get(field), review.get(field + "_authority_id"))
            if kind == "source" and resolved.get("immutable_ref") != review.get("version"):
                raise PromotionError("source version does not match registered immutable ref")
        except PromotionError:
            errors.append(f"candidate_review.{field} must use the exact registered evidence authority")
    for item in record.get("official_documentation") or []:
        try:
            _resolve_evidence(resolver, provider, "documentation", item)
        except PromotionError:
            errors.append("official_documentation must use the exact registered evidence authority")
    if not _immutable_ref(review.get("version")):
        errors.append("candidate_review.version must be a concrete immutable reference")
    license_value = review.get("license")
    reviewed_license = isinstance(license_value, str) and license_value.startswith("reviewed:") and _concrete(license_value[9:])
    if license_value not in SPDX_LICENSES and not reviewed_license:
        errors.append("candidate_review.license must be a valid SPDX identifier or concrete reviewed license")
    for field in ("dependencies", "permissions", "data_categories"):
        if not _nonblank_list(review.get(field)):
            errors.append(f"candidate_review.{field} requires concrete values")
    if not _immutable_ref(record.get("immutable_source")):
        errors.append("immutable_source must be a concrete non-placeholder pin")

    status = record.get("capability_status")
    if provider in {"google", "composio"} and status in {"Configured", "Verified"}:
        receipts = record.get("authority_receipts")
        receipt_map = receipts if isinstance(receipts, dict) else {}
        required = ({"source": "google-source", "documentation": "google-docs",
                     "data_policy": "google-data-policy", "cost": "google-cost"}
                    if provider == "google" else {kind: f"composio-{kind}" for kind in COMPOSIO_EVIDENCE})
        try:
            verifier = EvidenceReceiptVerifier(resolver)
            for kind, authority_id in required.items():
                verifier.verify(receipt_map[kind], provider, kind, authority_id, authority_url(provider, kind), clock)
        except (KeyError, TypeError, PromotionError):
            errors.append("private onboarding trusted-fetch authority receipts required")

    if status != "Verified":
        return errors
    for field in ("provider", "account_owner", "credential_reference", "selection_approval"):
        if not _concrete(record.get(field)):
            errors.append(f"Verified {field} must be concrete")
    if not _nonblank_list(record.get("requested_scopes")):
        errors.append("Verified requested_scopes requires concrete values")
    proof = record.get("live_proof")
    if not isinstance(proof, dict):
        return errors + ["Verified requires live_proof"]
    for field in ("evidence", "account", "target", "version", "approval_id"):
        if not _concrete(proof.get(field)):
            errors.append(f"live_proof.{field} must be concrete")
    for field in ("scopes", "operations"):
        if not _nonblank_list(proof.get(field)):
            errors.append(f"live_proof.{field} requires concrete values")
    if proof.get("synthetic") is not False or proof.get("result") != "pass":
        errors.append("Verified requires passing nonsynthetic live proof")
    try:
        tested = datetime.fromisoformat(proof.get("tested_at", "").replace("Z", "+00:00"))
        if tested.tzinfo is None:
            raise ValueError
        age = clock - tested
        if age.total_seconds() < 0:
            errors.append("live_proof.tested_at cannot be future")
        elif age.total_seconds() > MAX_EVIDENCE_AGE_DAYS * 86400:
            errors.append("live_proof.tested_at is stale")
    except (AttributeError, TypeError, ValueError):
        errors.append("live_proof.tested_at must be parseable and timezone-aware")
    if not _immutable_ref(proof.get("source_ref")):
        errors.append("live_proof.source_ref must be a concrete immutable reference")
    for field in ("policy_digest", "payload_digest"):
        if not _valid_hash(proof.get(field, ""), SHA256_RE):
            errors.append(f"live_proof.{field} must be a non-placeholder SHA-256 digest")

    declared = {str(item).lower() for item in record.get("approved_operations", [])}
    writes = "write" in str(record.get("capability", "")).lower() or any("write" in item for item in declared)
    operations = set(proof.get("operations") or [])
    if writes:
        required_flags = ("approved", "write_applicable", "write_passed", "readback_applicable", "readback_passed", "readback_matches_payload")
        if not {"write", "readback"} <= operations or not all(proof.get(key) is True for key in required_flags):
            errors.append("declared write capability requires exact approved write and matching provider readback")
    elif "read" not in operations or proof.get("authoritative_read") is not True:
        errors.append("read-only Verified route requires authoritative live read proof")
    if proof.get("unresolved_unknown") is not False:
        errors.append("Verified proof cannot have an unresolved external effect")

    if not isinstance(current_state, dict):
        errors.append("Verified requires current adapter and approval state")
        return errors
    expected = {
        "provider": record.get("provider"), "account": proof.get("account"),
        "credential_status": record.get("credential_status"), "health": record.get("health"),
        "scopes": proof.get("scopes"), "policy_digest": proof.get("policy_digest"),
        "source_ref": proof.get("source_ref"), "version": proof.get("version"),
        "approval_id": proof.get("approval_id"), "payload_digest": proof.get("payload_digest"),
        "target": proof.get("target"),
    }
    for field, value in expected.items():
        if current_state.get(field) != value:
            errors.append(f"current {field} does not match live proof")
    if current_state.get("enabled") is not True or current_state.get("revoked") is not False:
        errors.append("Verified requires a current enabled, nonrevoked adapter")
    if current_state.get("approval_protected") is not True or current_state.get("approval_current") is not True:
        errors.append("Verified requires current protected approval")
    return errors


class FakeAdapter:
    """In-memory adapter used to execute the provider-neutral contract."""

    _PROOF_BOUND_FIELDS = frozenset({"account_identity", "enabled", "revoked", "scopes", "policy_digest", "source_ref", "version"})

    def __setattr__(self, name, value):
        changed = name in self._PROOF_BOUND_FIELDS and name in self.__dict__ and self.__dict__[name] != value
        object.__setattr__(self, name, value)
        if changed:
            for listener in tuple(self.__dict__.get("_change_listeners", ())):
                listener(name)

    def __init__(self, account_identity: str = "fake@example.test", provider: str = "fake"):
        self._change_listeners = []
        self.account_identity = account_identity
        self.provider = provider
        self.enabled = True
        self.revoked = False
        self.scopes = ("read", "write", "readback")
        self.policy_digest = "62f215f5a8fc7a44bdeaf0561b8ab33c2be477600ca396a973310bc4c58438ef"  # pragma: allowlist secret
        self.source_ref = "commit:4dc2aeca2633476d3d497f2a4368ef91172b378e"  # pragma: allowlist secret
        self.version = "1.0.0"
        self.values = {}
        self.operation_results = {}
        self.operation_digests = {}
        self.pending_operations = {}
        self.write_count = 0
        self.live_calls = []
        self.timeout_after_next_write = False

    def state(self):
        return {
            "account": self.account_identity, "provider": self.provider,
            "enabled": self.enabled, "revoked": self.revoked,
            "scopes": list(self.scopes), "policy_digest": self.policy_digest,
            "source_ref": self.source_ref, "version": self.version,
        }

    def _available(self):
        if not self.enabled or self.revoked:
            raise PermissionError("adapter is disabled or revoked")

    def read_range(self, target: str, phase: Optional[str] = None):
        self._available()
        if phase:
            self.live_calls.append(phase)
        return self.values.get(target, [])

    def write_range(self, target: str, values, operation_key: str):
        self._available()
        operation_digest = _digest({"target": target, "values": values})
        if operation_key in self.operation_digests:
            if self.operation_digests[operation_key] != operation_digest:
                raise PermissionError("operation digest mismatch for idempotent replay")
            return self.operation_results[operation_key]
        self.operation_digests[operation_key] = operation_digest
        self.values[target] = values
        self.write_count += 1
        result = {"target": target, "values": values, "operation_key": operation_key, "operation_digest": operation_digest}
        self.operation_results[operation_key] = result
        if self.timeout_after_next_write:
            self.timeout_after_next_write = False
            self.pending_operations[operation_key] = result
            raise UnknownEffect(f"unknown external effect for {operation_key}; reconcile before retry")
        return result

    def revoke(self):
        self.revoked = True

    def disable(self):
        self.enabled = False


class IntegrationHarness:
    """Stateful proof runner; it contains no provider SDK or live credential path."""

    def __init__(self, adapter: FakeAdapter, now: Optional[Callable[[], datetime]] = None, official_domains=None, authority_resolver=None):
        self.adapter = adapter
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.authority_resolver = authority_resolver or default_authority_resolver()
        self.evidence_verifier = EvidenceReceiptVerifier(self.authority_resolver)
        self.outcome = self.evidence_definition = None
        self.routes = []
        self.review = self.selection = self.source_pin = self.live_approval = None
        self.live_contract_proof = None
        self.recovery = None
        self.status = "Optional"
        self.unknown = {}
        self.proof_invalidated_by = None
        self.adapter._change_listeners.append(self._adapter_changed)

    def _adapter_changed(self, field):
        if self.live_contract_proof is not None:
            self.live_contract_proof = None
            self.proof_invalidated_by = field
        if self.status == "Verified":
            self.status = "Blocked"

    def define(self, outcome: str, evidence: str):
        self.outcome, self.evidence_definition = outcome, evidence

    def record_discovery(self, routes):
        self.routes = list(routes)

    def record_review(self, **review):
        required = {"source", "version", "license", "dependencies", "permissions", "data_categories", "data_policy", "cost_evidence"}
        missing = required - review.keys()
        if missing:
            raise PromotionError(f"missing review fields: {sorted(missing)}")
        for field, kind in (("source", "source"), ("data_policy", "data_policy"), ("cost_evidence", "cost")):
            resolved = _resolve_evidence(self.authority_resolver, self.adapter.provider, kind, review[field], review.get(field + "_authority_id"))
            if kind == "source" and resolved.get("immutable_ref") != review.get("version"):
                raise PromotionError("candidate version must match the registered immutable source ref")
        if not _immutable_ref(review["version"]):
            raise PromotionError("candidate version must be a full immutable commit, digest, tag, or version")
        license_value = review["license"]
        reviewed_license = isinstance(license_value, str) and license_value.startswith("reviewed:") and _concrete(license_value[9:])
        if license_value not in SPDX_LICENSES and not reviewed_license:
            raise PromotionError("valid SPDX identifier or concrete reviewed license evidence required")
        for field in ("dependencies", "permissions", "data_categories"):
            if not _nonblank_list(review[field]):
                raise PromotionError(f"nonblank {field} evidence required")
        self.review = review

    def select_route(self, route: str, approved_by: str):
        if route not in self.routes:
            raise PromotionError("selected route was not discovered")
        if not _concrete(approved_by):
            raise PromotionError("route selection requires approval")
        self.selection = {"route": route, "approved_by": approved_by}

    def pin_source(self, source_ref: str):
        if not _immutable_ref(source_ref):
            raise PromotionError("source pin must be a full immutable commit, sha256, tag, or version")
        self.source_pin = source_ref

    def run_synthetic(self):
        if "do-not-enable" not in self.routes:
            raise PromotionError("route comparison must include do-not-enable")
        if not self.source_pin:
            raise PromotionError("immutable source pin required")
        if not all((self.outcome, self.evidence_definition, self.review, self.selection)):
            raise PromotionError("onboarding stages incomplete")
        return {"result": "pass", "provider": self.adapter.provider, "live": False}

    def approve_live(self, *, account: str, operations, target: str, material_payload_digest: str,
                     operation_key_policy: dict, task_id: str, requirement_version: str,
                     policy_digest: str, expires_at: str):
        if not _valid_hash(material_payload_digest, SHA256_RE) or not _valid_hash(policy_digest, SHA256_RE):
            raise PromotionError("approval digests must be SHA-256")
        if not all(_concrete(item) for item in (account, target, task_id, requirement_version)):
            raise PromotionError("approval binding fields must be nonblank")
        if not isinstance(operations, (list, tuple, set)) or not operations or not set(operations) <= {"read", "write", "readback"}:
            raise PromotionError("approval operations must be concrete supported operations")
        if operation_key_policy.get("type") not in {"exact", "prefix"} or not _concrete(operation_key_policy.get("value")):
            raise PromotionError("explicit operation key policy required")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError
        except (AttributeError, TypeError, ValueError) as exc:
            raise PromotionError("parseable timezone-aware approval expiry required") from exc
        if expiry <= self.now():
            raise PromotionError("approval expiry must be in the future")
        self.live_approval = {
            "account": account, "operations": set(operations), "target": target,
            "material_payload_digest": material_payload_digest,
            "operation_key_policy": dict(operation_key_policy), "task_id": task_id,
            "requirement_version": requirement_version, "policy_digest": policy_digest,
            "expires_at": expiry,
        }

    def _authorize(self, target: str, operations, values, operation_key: str, task_id=None, requirement_version=None):
        approval = self.live_approval
        if not approval or approval["account"] != self.adapter.account_identity or approval["target"] != target:
            raise PermissionError("exact account and target approval required")
        if not set(operations) <= approval["operations"]:
            raise PermissionError("operation is outside approval")
        if self.now() >= approval["expires_at"]:
            raise PermissionError("approval expired")
        if approval["material_payload_digest"] != _digest(values):
            raise PermissionError("material payload digest does not match approval")
        policy = approval["operation_key_policy"]
        allowed = operation_key == policy["value"] if policy["type"] == "exact" else operation_key.startswith(policy["value"])
        if not allowed:
            raise PermissionError("operation key is outside approval policy")
        if approval["policy_digest"] != self.adapter.policy_digest:
            raise PermissionError("current adapter policy differs from approval")
        if approval["task_id"] != task_id or approval["requirement_version"] != requirement_version:
            raise PermissionError("task or requirement version does not match approval")

    def _record_proof(self, target, values, operations):
        if self.live_approval is None:
            raise PromotionError("current live approval required to record proof")
        self.proof_invalidated_by = None
        self.live_contract_proof = {
            "result": "pass", "synthetic": False, "target": target,
            "payload_digest": _digest(values), "operations": sorted(operations),
            "adapter_state": self.adapter.state(),
            "approval": {key: value for key, value in self.live_approval.items() if key not in {"operations", "expires_at"}},
            "expires_at": self.live_approval["expires_at"].isoformat(),
            "tested_at": self.now().isoformat(),
        }

    def run_live_read_write_readback(self, target: str, values, *, task_id=None, requirement_version=None):
        operation_key = "onboarding-live-write"
        self._authorize(target, {"read", "write", "readback"}, values, operation_key, task_id, requirement_version)
        self.adapter.read_range(target, phase="read")
        self.adapter.live_calls.append("write")
        result = self.adapter.write_range(target, values, operation_key)
        readback = self.adapter.read_range(target, phase="readback")
        if readback != values:
            raise PromotionError("exact target/value readback failed")
        self._record_proof(target, values, {"read", "write", "readback"})
        return {"write": result, "readback": readback}

    def scoped_sheet_write(self, target: str, values, operation_key: str, *, task_id=None, requirement_version=None):
        self._authorize(target, {"write", "readback"}, values, operation_key, task_id, requirement_version)
        try:
            result = self.adapter.write_range(target, values, operation_key)
        except UnknownEffect:
            self.unknown[operation_key] = {"target": target, "values": values, "operation_digest": _digest({"target": target, "values": values})}
            raise
        if self.adapter.read_range(target) != values:
            raise PromotionError("exact range/value readback failed")
        self._record_proof(target, values, {"write", "readback"})
        return result

    def reconcile_unknown(self, operation_key: str, target: str, expected_values):
        expected = {"target": target, "values": expected_values, "operation_digest": _digest({"target": target, "values": expected_values})}
        if self.unknown.get(operation_key) != expected:
            return "confirmed-failure"
        if self.adapter.read_range(target) == expected_values:
            del self.unknown[operation_key]
            self._record_proof(target, expected_values, {"write", "readback"})
            return "confirmed-success"
        return "unknown"

    def _validate_composio_evidence(self, evidence):
        if not evidence or any(key not in evidence for key in COMPOSIO_EVIDENCE):
            raise PromotionError("missing current official evidence for Composio setup")
        now = self.now()
        for key in COMPOSIO_EVIDENCE:
            item = evidence[key]
            if not isinstance(item, dict):
                raise PromotionError("Composio evidence requires an authenticated trusted-fetch receipt")
            try:
                authority_id = f"composio-{key}"
                url = authority_url("composio", key)
                self.evidence_verifier.verify(item.get("receipt"), "composio", key, authority_id, url, now)
            except PromotionError as exc:
                if "stale" in str(exc):
                    raise
                raise PromotionError("Composio evidence requires an authenticated trusted-fetch receipt") from exc
            value = item.get("value")
            if not isinstance(value, str) or not value.strip() or value.strip().lower() in PLACEHOLDERS:
                raise PromotionError("missing current official evidence for Composio setup")


    def promote(self, status: str, provider_evidence=None):
        validate_capability_status(status)
        if self.adapter.provider in {"google", "composio"} and status in {"Configured", "Verified"} and not provider_evidence:
            raise PromotionError("private onboarding trusted-fetch authority receipts required")
        if self.adapter.provider == "composio" and status in {"Configured", "Verified"}:
            self._validate_composio_evidence(provider_evidence)
        if self.adapter.provider == "google" and status in {"Configured", "Verified"}:
            required = {"source": "google-source", "documentation": "google-docs",
                        "data_policy": "google-data-policy", "cost": "google-cost"}
            evidence = provider_evidence if isinstance(provider_evidence, dict) else {}
            try:
                for kind, authority_id in required.items():
                    self.evidence_verifier.verify(evidence[kind]["receipt"], "google", kind,
                                                  authority_id, authority_url("google", kind), self.now())
            except (KeyError, TypeError, PromotionError) as exc:
                raise PromotionError("private onboarding trusted-fetch authority receipts required") from exc
        if status == "Verified":
            if not self.adapter.enabled or self.adapter.revoked:
                raise PromotionError("current enabled, non-revoked adapter is required")
            if not self.live_contract_proof:
                if self.proof_invalidated_by:
                    raise PromotionError(f"current adapter state changed: {self.proof_invalidated_by}")
                raise PromotionError("live contract proof with exact readback is required")
            if self.live_contract_proof["adapter_state"] != self.adapter.state():
                raise PromotionError("current adapter state does not match bound live proof")
            try:
                expires_at = datetime.fromisoformat(self.live_contract_proof["expires_at"])
                tested_at = datetime.fromisoformat(self.live_contract_proof["tested_at"])
                if expires_at.tzinfo is None or tested_at.tzinfo is None:
                    raise ValueError
            except (KeyError, AttributeError, TypeError, ValueError) as exc:
                raise PromotionError("live proof timestamp must be parseable and timezone-aware") from exc
            if self.now() >= expires_at:
                raise PromotionError("current live proof approval has expired")
            age = self.now() - tested_at
            if age.total_seconds() < 0 or age.total_seconds() > MAX_EVIDENCE_AGE_DAYS * 86400:
                raise PromotionError("live proof timestamp is future or stale")
        self.status = status
        return status

    def record_recovery(self, fallback: str, disable: str, rollback: str):
        self.recovery = {"fallback": fallback, "disable": disable, "rollback": rollback}

    def capture_lane(self, name: str, reviewed: bool, contains_private_data: bool):
        if not self.recovery or not reviewed or contains_private_data:
            raise PromotionError("lane capture requires review, recovery, and no private data")
        return {"name": name, "reusable": True, "private_data": False}

    def revoke(self):
        self.adapter.revoke()
        self.live_contract_proof = None
        if self.status == "Verified": self.status = "Blocked"

    def disable(self):
        self.adapter.disable()
        self.live_contract_proof = None
        if self.status == "Verified": self.status = "Blocked"
