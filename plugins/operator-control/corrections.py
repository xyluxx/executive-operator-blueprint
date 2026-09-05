"""Transactional routing of scoped corrections to their existing authorities."""
from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "templates" / "correction-record.schema.json"
DURABLE_DESTINATIONS = frozenset(
    {"task_requirement", "project_fact", "principal_preference", "voice", "approval"}
)
IMPACT_ACTIONS = {
    "task": "block", "criterion": "block", "evidence": "block",
    "approval": "cancel", "schedule": "block", "dependency": "block", "worker": "rebrief",
}
_SECRET_PATTERNS = tuple(re.compile(value, re.IGNORECASE) for value in (
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[:=]\s*\S{8,}",
    r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b",
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/=-]{20,}\b",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
    r"\b(?:api[-_ ]?key|token)\s*[:=_-]\s*[A-Za-z0-9+/=_-]{20,}\b",
))


class ConflictError(ValueError):
    """The correction was based on a claim that is no longer current."""


class ReconciliationRequired(RuntimeError):
    """A failed transaction could not be safely compensated."""


def canonical_digest(record: Mapping[str, Any]) -> str:
    """Bind both replay identifiers to every security/material field."""
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _contains_secret(value: Any) -> bool:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False)
    if any(pattern.search(serialized) for pattern in _SECRET_PATTERNS):
        return True
    # Catch unlabelled machine tokens without treating ordinary long words,
    # public issue ids, or prose as credentials.
    for token in re.findall(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{32,}(?![A-Za-z0-9])", serialized):
        classes = sum(bool(re.search(pattern, token)) for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[_+/=-]"))
        probabilities = [token.count(char) / len(token) for char in set(token)]
        entropy = -sum(p * math.log2(p) for p in probabilities)
        if classes >= 3 and entropy >= 4.0:
            return True
    return False


class CorrectionService:
    """Durable prepare/apply/readback/impact/commit coordinator.

    ``idempotency`` is a durable journal adapter (MutableMapping semantics), not
    a task store. Entries are written at prepare and retained through recovery.
    """

    def __init__(self, *, authorities: Mapping[str, Any], impact_adapter: Any,
                 idempotency: MutableMapping[str, dict[str, Any]]) -> None:
        missing = DURABLE_DESTINATIONS - set(authorities)
        if missing:
            raise ValueError(f"missing authority adapters: {sorted(missing)}")
        self._authorities = dict(authorities)
        self._impact = impact_adapter
        self._idempotency = idempotency
        self._validator = jsonschema.Draft202012Validator(
            json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=jsonschema.FormatChecker()
        )

    def retrieve(self, destination: str, authority_id: str) -> dict[str, Any] | None:
        if destination not in DURABLE_DESTINATIONS:
            return None
        value = self._authorities[destination].current_claim(authority_id)
        return deepcopy(value) if value is not None else None

    def _journal_keys(self, record: Mapping[str, Any]) -> tuple[str, str]:
        return f"correction:{record['correction_id']}", f"source:{record['source_event_id']}"

    def _write_entry(self, keys: tuple[str, str], entry: dict[str, Any]) -> None:
        for key in keys:
            self._idempotency[key] = deepcopy(entry)
        flush = getattr(self._idempotency, "flush", None)
        if flush:
            flush()

    def record(self, record: dict[str, Any]) -> dict[str, Any]:
        if record.get("privacy", {}).get("contains_secret") or _contains_secret(record.get("replacement")):
            raise ValueError("secret values cannot be stored in correction records")
        self._validator.validate(record)
        if record["destination"] == "session_clarification":
            return {"durable": False, "impacts": []}
        if not record["explicit"]:
            raise ValueError("durable write requires an explicit correction")
        if not record["confirmed"]:
            raise ValueError("ambiguous durable correction requires explicit confirmation")

        digest = canonical_digest(record)
        keys = self._journal_keys(record)
        found: list[dict[str, Any]] = []
        for key in keys:
            candidate = self._idempotency.get(key)
            if candidate is not None:
                found.append(candidate)
        if found:
            if any(existing.get("payload_digest") != digest for existing in found):
                raise ValueError("replay payload does not match bound correction/source event")
            entry = found[0]
            if entry.get("state") == "committed":
                adapter = self._authorities[record["destination"]]
                current = adapter.current_claim(record["target"]["authority_id"])
                expected = record["replacement"]
                if not current or current.get("claim_id") != expected["claim_id"] or current.get("version") != record["prior_claim"]["version"] + 1:
                    raise ConflictError("stale replay no longer names the current predecessor/version")
                return deepcopy(entry["receipt"])
            if entry.get("state") == "blocked":
                raise ReconciliationRequired("correction is blocked pending operator reconciliation")
            # Rolled-back and crash-pending entries are reconciled against truth below.
        else:
            entry = {"state": "prepared", "payload_digest": digest, "record": deepcopy(record), "applied_impacts": []}
            self._write_entry(keys, entry)
        adapter = self._authorities[record["destination"]]
        authority_id = record["target"]["authority_id"]
        prior = record["prior_claim"]
        current = adapter.current_claim(authority_id)
        replacement = record["replacement"]
        expected_version = prior["version"] + 1
        if current and current.get("client_id") is not None and current.get("client_id") != record["client_id"]:
            raise ConflictError("cross-client correction denied")
        if current and current.get("scope") is not None and current.get("scope") != record["scope"]:
            raise ConflictError("authority scope does not exactly match correction scope")
        if current and current.get("exact_scope") is not None and current.get("exact_scope") != record["target"]["exact_scope"]:
            raise ConflictError("authority exact scope does not match correction target")
        replacement_is_live = bool(current and current.get("claim_id") == replacement["claim_id"] and current.get("version") == expected_version)
        if not replacement_is_live:
            if current is None:
                raise ConflictError("target claim does not exist")
            if current.get("claim_id") != prior["claim_id"] or current.get("version") != prior["version"]:
                raise ConflictError("stale prior claim; retrieve current authority before correcting")

        impacts = self._calculate_impacts(record)
        applied: list[dict[str, str]] = list(entry.get("applied_impacts", []))
        preparation = entry.get("withdrawal_preparation")
        withdrawal_committed = False
        try:
            if record["destination"] == "approval" and preparation is None:
                prepare = getattr(adapter, "prepare_withdrawal", None)
                if prepare is None:
                    raise RuntimeError("approval authority lacks staged broker withdrawal API")
                preparation = prepare(deepcopy(record))
                entry["withdrawal_preparation"] = deepcopy(preparation)
                self._write_entry(keys, entry)
            if not replacement_is_live:
                entry.update(state="applying", prior_snapshot=deepcopy(current), impacts=deepcopy(impacts))
                self._write_entry(keys, entry)
                method = adapter.retract_correction if record["operation"] == "retract" else adapter.apply_correction
                method(deepcopy(record))

            readback = adapter.current_claim(authority_id)
            if not readback or readback.get("claim_id") != replacement["claim_id"] or readback.get("version") != expected_version or readback.get("content") != replacement["content"]:
                raise RuntimeError("authority readback did not confirm replacement and exact version")
            for impact in impacts:
                if impact in applied and self._impact_verified(impact, record["correction_id"]):
                    continue
                self._impact.apply_impact(deepcopy(impact), correction_id=record["correction_id"])
                applied.append(deepcopy(impact))
                entry.update(state="impacting", applied_impacts=deepcopy(applied))
                self._write_entry(keys, entry)
                if not self._impact_verified(impact, record["correction_id"]):
                    raise RuntimeError("impact readback failed")

            superseded = getattr(adapter, "superseded_claim", lambda *_: {"superseded_by": replacement["claim_id"]})(authority_id, prior["claim_id"])
            if not superseded or superseded.get("superseded_by") != replacement["claim_id"]:
                raise RuntimeError("prior claim supersession readback failed")
            if record["destination"] == "approval":
                adapter.commit_withdrawal(deepcopy(record), deepcopy(preparation))
                withdrawal_committed = True
                if not adapter.verify_withdrawal(authority_id, record["correction_id"]):
                    raise ReconciliationRequired("irreversible broker withdrawal readback failed")
            receipt = {"durable": True, "correction_id": record["correction_id"], "source_event_id": record["source_event_id"],
                       "destination": record["destination"], "authority_id": authority_id, "version": expected_version,
                       "payload_digest": digest, "impacts": impacts}
            entry.update(state="committed", receipt=deepcopy(receipt), applied_impacts=deepcopy(applied))
            self._write_entry(keys, entry)
            return receipt
        except Exception:
            if withdrawal_committed:
                entry.update(state="blocked", rollback_error="irreversible withdrawal committed")
                self._write_entry(keys, entry)
                raise ReconciliationRequired("irreversible broker withdrawal committed; reconciliation required")
            if record["destination"] == "approval" and preparation is not None:
                status = adapter.broker.approval_status(authority_id) if hasattr(adapter, "broker") else None
                if not status or status.get("state") != "revoked":
                    adapter.cancel_withdrawal(deepcopy(record), deepcopy(preparation))
            self._compensate(adapter, record, entry, applied, keys)
            raise

    def _impact_verified(self, impact: dict[str, str], correction_id: str) -> bool:
        verify = getattr(self._impact, "verify_impact", None)
        return True if verify is None else bool(verify(deepcopy(impact), correction_id=correction_id))

    def _compensate(self, adapter: Any, record: dict[str, Any], entry: dict[str, Any],
                    applied: list[dict[str, str]], keys: tuple[str, str]) -> None:
        try:
            rollback_impact = getattr(self._impact, "rollback_impact", None)
            for impact in reversed(applied):
                if rollback_impact:
                    rollback_impact(deepcopy(impact), correction_id=record["correction_id"])
            prior = entry.get("prior_snapshot")
            current = adapter.current_claim(record["target"]["authority_id"])
            if prior is not None and current and current.get("claim_id") == record["replacement"]["claim_id"]:
                rollback = getattr(adapter, "rollback_correction", None)
                if rollback is None:
                    raise RuntimeError("authority cannot compensate")
                rollback(deepcopy(record), deepcopy(prior))
            entry.update(state="rolled_back", applied_impacts=[])
            self._write_entry(keys, entry)
        except Exception as rollback_error:
            entry.update(state="blocked", rollback_error=str(rollback_error), applied_impacts=deepcopy(applied))
            self._write_entry(keys, entry)
            raise ReconciliationRequired("rollback failed; correction blocked for reconciliation") from rollback_error

    def _calculate_impacts(self, record: dict[str, Any]) -> list[dict[str, str]]:
        prior_claim_id, scope = record["prior_claim"]["claim_id"], record["scope"]
        exact_scope = record["target"]["exact_scope"]
        candidates = self._impact.active_items(client_id=record["client_id"], scope=deepcopy(scope))
        impacts = []
        for item in candidates:
            item_scope = item.get("scope")
            if (item.get("client_id") != record["client_id"] or not item.get("active") or
                    not isinstance(item_scope, dict) or set(item_scope) != set(scope) or item_scope != scope or
                    item.get("exact_scope") != exact_scope or prior_claim_id not in item.get("claim_refs", ())):
                continue
            action = IMPACT_ACTIONS.get(item.get("kind"))
            if action:
                impacts.append({"entity_id": str(item["entity_id"]), "kind": item["kind"], "action": action})
        return sorted(impacts, key=lambda value: (value["kind"], value["entity_id"]))
