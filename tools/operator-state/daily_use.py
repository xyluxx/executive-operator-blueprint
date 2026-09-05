"""Provider-neutral synthetic calendar and daily-brief engines.

The fake adapters perform no network I/O.  Engines durably journal intent when
an ``OperationStore`` path is supplied; fakes also retain the journal across
engine instances so uncertain effects can never be blindly repeated.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimeResolutionError(ValueError): pass
class CalendarConflict(RuntimeError): pass
class ApprovalDenied(PermissionError): pass
class ReadbackMismatch(RuntimeError): pass
class UnknownEffect(RuntimeError): pass
class OperationBindingError(RuntimeError): pass


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("calendar instants require an explicit UTC offset")
    return parsed.astimezone(timezone.utc)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class OperationStore:
    """Small atomic JSON journal; memory-only when no path is supplied."""
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.records = {}
        if self.path and self.path.exists():
            self.records = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, key):
        value = self.records.get(key)
        return copy.deepcopy(value) if value else None

    def put(self, key, value):
        self.records[key] = copy.deepcopy(value)
        if not self.path:
            return
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".operations-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.records, stream, sort_keys=True, separators=(",", ":"))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)


class FakeCalendarAdapter:
    def __init__(self, events=None, unknown_once=False, persist_before_unknown=False, readback_overrides=None):
        self.events = {item["event_id"]: copy.deepcopy(item) for item in (events or [])}
        self.operations, self.failures, self.attempted = {}, set(), {}
        self.unknown_once, self.persist_before_unknown = unknown_once, persist_before_unknown
        self.readback_overrides = readback_overrides or {}
        self.write_count = 0
        self._intent_store = OperationStore()

    def list_events(self, calendar_id):
        return [copy.deepcopy(v) for v in self.events.values() if v["calendar_id"] == calendar_id]

    def find_by_operation_key(self, key):
        if key in self.failures: return {"effect": "confirmed-failure", "operation_key": key}
        event_id = self.operations.get(key)
        return self.read_event(event_id) if event_id else None

    def read_event(self, event_id):
        item = self.events.get(event_id)
        if not item: return None
        result = copy.deepcopy(item); result.update(self.readback_overrides); return result

    def _result(self, action, payload, key):
        result = copy.deepcopy(payload)
        result.update(operation_key=key, action=action, effect="confirmed-success")
        result["status"] = "cancelled" if action == "cancel" else "confirmed"
        if action == "reschedule": result["lineage_event_id"] = payload["event_id"]
        return result

    def persist_operation(self, action, payload, key):
        payload = self.attempted.get(key, payload)
        result = self._result(action, payload, key)
        self.events[result["event_id"]] = result; self.operations[key] = result["event_id"]
        return copy.deepcopy(result)

    def mark_failed(self, key): self.failures.add(key)

    def write(self, action, payload, operation_key):
        if action not in {"create", "cancel", "reschedule"}: raise ValueError(f"unsupported calendar action: {action}")
        self.write_count += 1
        self.attempted[operation_key] = copy.deepcopy(payload)
        result = self._result(action, payload, operation_key)
        if not self.unknown_once or self.persist_before_unknown:
            self.persist_operation(action, payload, operation_key)
        if self.unknown_once:
            self.unknown_once = False; raise UnknownEffect("provider outcome unknown")
        return result


class CalendarEngine:
    RECURRENCE_SCOPES = {"occurrence", "this-and-future", "series"}
    BINDING_FIELDS = ("calendar_id", "organizer_id", "attendee_ids", "start", "end", "timezone", "status", "recurrence_scope", "series_id")

    def __init__(self, adapter, store=None):
        self.adapter = adapter
        self.store = store or getattr(adapter, "_intent_store", OperationStore())
        adapter._intent_store = self.store

    def resolve_local(self, local_value, timezone_name, fold=None):
        try: zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc: raise TimeResolutionError("unknown IANA timezone") from exc
        naive = datetime.fromisoformat(local_value)
        if naive.tzinfo is not None: raise TimeResolutionError("local time must not contain an offset")
        candidates = []
        for candidate_fold in (0, 1):
            candidate = naive.replace(tzinfo=zone, fold=candidate_fold)
            if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive: candidates.append(candidate)
        if not candidates: raise TimeResolutionError("nonexistent local time")
        ambiguous = len(candidates) == 2 and candidates[0].utcoffset() != candidates[1].utcoffset()
        if ambiguous and fold not in (0, 1): raise TimeResolutionError("ambiguous local time requires fold")
        return candidates[fold or 0] if ambiguous else candidates[0]

    def conflicts(self, payload):
        start, end = _instant(payload["start"]), _instant(payload["end"])
        if end <= start: raise ValueError("event end must be after start")
        matches, participants = [], {payload["organizer_id"], *payload.get("attendee_ids", [])}
        for item in self.adapter.list_events(payload["calendar_id"]):
            if item.get("status") == "cancelled" or item.get("event_id") == payload.get("event_id"): continue
            people = {item["organizer_id"], *item.get("attendee_ids", [])}
            if participants & people and start < _instant(item["end"]) and _instant(item["start"]) < end: matches.append(item["event_id"])
        return matches

    def propose(self, payload):
        conflicts = self.conflicts(payload)
        return {"status": "conflict", "conflicts": conflicts} if conflicts else {"status": "tentative", "event": copy.deepcopy(payload)}

    def _binding(self, action, payload, approval_reference, requirement_version):
        material = {field: copy.deepcopy(payload.get(field)) for field in self.BINDING_FIELDS}
        material.update(action=action, approval_reference=approval_reference, requirement_version=requirement_version)
        return _digest(material)

    def _verify(self, intent, actual):
        if not actual: raise ReadbackMismatch("provider readback missing")
        expected = intent["expected"]
        fields = ("event_id", "calendar_id", "organizer_id", "attendee_ids", "start", "end", "timezone", "status", "recurrence_scope", "series_id", "action", "operation_key", "approval_reference", "requirement_version", "operation_binding_digest")
        for field in fields:
            if actual.get(field) != expected.get(field): raise ReadbackMismatch(f"provider readback mismatch: {field}")
        if intent["action"] == "reschedule" and actual.get("lineage_event_id") != expected["event_id"]:
            raise ReadbackMismatch("provider readback mismatch: action semantics")
        return copy.deepcopy(actual)

    def apply(self, action, payload, operation_key, approved, approval_reference="legacy-approved", requirement_version="task-8"):
        if not approved: raise ApprovalDenied("exact calendar approval denied")
        if payload.get("recurrence_scope") not in self.RECURRENCE_SCOPES: raise ValueError("invalid recurrence scope")
        binding = self._binding(action, payload, approval_reference, requirement_version)
        prior = self.store.get(operation_key)
        if prior:
            if prior["binding_digest"] != binding: raise OperationBindingError("operation key is bound to a different exact approved request")
            return copy.deepcopy(prior["result"])
        if action in {"create", "reschedule"} and self.conflicts(payload): raise CalendarConflict("calendar conflict blocks write")
        expected = copy.deepcopy(payload)
        expected.update(operation_key=operation_key, action=action, approval_reference=approval_reference,
                        requirement_version=requirement_version, operation_binding_digest=binding,
                        status="cancelled" if action == "cancel" else "confirmed")
        intent = {"action": action, "binding_digest": binding, "expected": expected}
        unknown = {"effect": "unknown", "operation_key": operation_key}
        self.store.put(operation_key, {"binding_digest": binding, "intent": intent, "result": unknown})
        try:
            dispatched = self.adapter.write(action, expected, operation_key)
        except UnknownEffect:
            return self._reconcile_known(operation_key, intent)
        result = self._verify(intent, self.adapter.read_event(dispatched["event_id"]))
        self.store.put(operation_key, {"binding_digest": binding, "intent": intent, "result": result})
        return result

    def _reconcile_known(self, key, intent):
        actual = self.adapter.find_by_operation_key(key)
        if not actual: return {"effect": "unknown", "operation_key": key}
        if actual.get("effect") == "confirmed-failure":
            result = actual
        else:
            result = self._verify(intent, actual); result["reconciled"] = True
        self.store.put(key, {"binding_digest": intent["binding_digest"], "intent": intent, "result": result})
        return result

    def reconcile(self, operation_key):
        prior = self.store.get(operation_key)
        if not prior: return {"effect": "not-found", "operation_key": operation_key}
        if prior["result"].get("effect") != "unknown": return prior["result"]
        return self._reconcile_known(operation_key, prior["intent"])


class FakeKanbanAdapter:
    def __init__(self, tasks): self.tasks, self.read_count = copy.deepcopy(tasks), 0
    def read_tasks(self): self.read_count += 1; return copy.deepcopy(self.tasks)

class FakeSourceAdapter:
    def __init__(self, approved_sources): self.approved_sources, self.read_names = copy.deepcopy(approved_sources), []
    def read(self, name):
        if name not in self.approved_sources: raise PermissionError(f"source is not approved: {name}")
        self.read_names.append(name); return copy.deepcopy(self.approved_sources[name])

class FakeDeliveryAdapter:
    def __init__(self, unknown_once=False, persist_before_unknown=False, readback_overrides=None):
        self.records, self.attempted, self.failures, self.send_count = {}, {}, set(), 0
        self.unknown_once, self.persist_before_unknown = unknown_once, persist_before_unknown
        self.readback_overrides = readback_overrides or {}
        self._intent_store = OperationStore()
    def read_record(self, key):
        if key in self.failures:
            attempted = copy.deepcopy(self.attempted.get(key, {}))
            return {**attempted, "operation_key": key, "state": "confirmed-failure", "reconciliation": "provider-confirmed-failure"}
        value = self.records.get(key)
        if not value: return None
        result = copy.deepcopy(value); result.update(self.readback_overrides); return result
    def persist_record(self, record):
        stored = copy.deepcopy(record)
        stored.update(provider_delivery_id=f"synthetic-{max(1, self.send_count)}", state="confirmed-success", delivered_at="2026-09-05T12:00:00Z", reconciliation="not-required")
        self.records[record["operation_key"]] = stored; return copy.deepcopy(stored)
    def mark_failed(self, key): self.failures.add(key)
    def send(self, record, content):
        self.send_count += 1
        self.attempted[record["operation_key"]] = copy.deepcopy(record)
        stored = self.persist_record(record) if (not self.unknown_once or self.persist_before_unknown) else None
        if self.unknown_once: self.unknown_once = False; raise UnknownEffect("delivery outcome unknown")
        return stored


class DailyBriefEngine:
    SECTIONS = ("decisions-waiting", "todays-commitments", "due-outside-follow-ups", "slipped-or-newly-at-risk", "unresolved-consequential-effects")
    def __init__(self, kanban, sources, delivery, store=None):
        self.kanban, self.sources, self.delivery = kanban, sources, delivery
        self.store = store or getattr(delivery, "_intent_store", OperationStore()); delivery._intent_store = self.store
    @staticmethod
    def operation_key(routine_id, occurrence, channel, recipient): return _digest([routine_id, occurrence, channel, recipient])
    def _exact(self, intent, readback):
        return readback and all(readback.get(f) == intent[f] for f in ("routine_id", "scheduled_occurrence", "operation_key", "channel", "recipient", "content_digest"))
    def run(self, routine_id, occurrence, channel, recipient, approved_sources):
        items = self.kanban.read_tasks()
        for name in approved_sources: items.extend(self.sources.read(name))
        relevant = [i for i in items if i.get("section") in self.SECTIONS]
        if not relevant: return {"state": "suppressed-empty"}
        key = self.operation_key(routine_id, occurrence, channel, recipient)
        content = "\n".join(f"[{i['section']}] {i['summary']}" for i in relevant)
        record = {"schema_version":"1.0", "routine_id":routine_id, "scheduled_occurrence":occurrence, "operation_key":key,
                  "channel":channel, "recipient":recipient, "content_digest":hashlib.sha256(content.encode()).hexdigest(),
                  "state":"pending", "created_at":"2026-09-05T12:00:00Z", "provider_delivery_id":None,
                  "delivered_at":None, "reconciliation":"pending"}
        prior = self.store.get(key)
        if prior:
            state = prior["result"]["state"]
            return {"state": "deduplicated", "operation_key": key} if state == "confirmed-success" else prior["result"]
        provider_existing = self.delivery.read_record(key)
        if provider_existing:
            result = self._classify_readback(record, provider_existing, "provider-preexisting")
            self.store.put(key, {"intent": record, "result": result})
            if result["state"] == "confirmed-success":
                return {"state": "deduplicated", "operation_key": key}
            return result
        unknown = {**record, "state":"unknown", "reconciliation":"not-found-after-unknown"}
        self.store.put(key, {"intent": record, "result": unknown})
        try: self.delivery.send(record, content)
        except UnknownEffect: return self.reconcile(key)
        return self._reconcile_known(key, record, "not-required")
    def _reconcile_known(self, key, intent, success_label="found-after-unknown"):
        readback = self.delivery.read_record(key)
        if not readback:
            stored = self.store.get(key)
            return stored["result"] if stored else {"state":"not-found", "operation_key":key}
        result = self._classify_readback(intent, readback, success_label)
        self.store.put(key, {"intent": intent, "result": result}); return result
    def _classify_readback(self, intent, readback, success_label):
        if not self._exact(intent, readback):
            return {**intent, "state":"unknown", "reconciliation":"readback-mismatch"}
        state = readback.get("state")
        if state not in {"confirmed-success", "confirmed-failure", "unknown"}:
            return {**intent, "state":"unknown", "reconciliation":"readback-invalid-state"}
        result = copy.deepcopy(readback)
        result["reconciliation"] = success_label if state == "confirmed-success" else readback.get("reconciliation", "provider-readback")
        return result
    def reconcile(self, operation_key):
        prior = self.store.get(operation_key)
        if not prior: return {"state":"not-found", "operation_key":operation_key}
        if prior["result"]["state"] != "unknown": return prior["result"]
        return self._reconcile_known(operation_key, prior["intent"])
