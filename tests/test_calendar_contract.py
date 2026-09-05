import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "calendar-operations" / "SKILL.md"
MODULE_PATH = ROOT / "tools" / "operator-state" / "daily_use.py"
SPEC = importlib.util.spec_from_file_location("daily_use_calendar", MODULE_PATH)
assert SPEC and SPEC.loader
calendar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calendar)


def event(**overrides):
    value = {
        "event_id": "event-1",
        "calendar_id": "calendar-owner",
        "organizer_id": "owner-1",
        "attendee_ids": ["attendee-1"],
        "start": "2026-09-08T09:00:00-05:00",
        "end": "2026-09-08T09:30:00-05:00",
        "timezone": "America/Chicago",
        "status": "tentative",
        "recurrence_scope": "occurrence",
    }
    value.update(overrides)
    return value


def test_calendar_operations_is_provider_neutral_bundled_core():
    text = SKILL.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---\n", 2)[1])
    assert frontmatter["name"] == "calendar-operations"
    assert frontmatter["description"].startswith("Use when ")
    assert len(frontmatter["description"]) <= 60
    assert "## Behavioral Tests" in text
    assert "## Verification" in text
    assert "Completion criterion:" in text


def test_calendar_adapter_is_optional_and_unverified_until_live_tested():
    skill = SKILL.read_text(encoding="utf-8").lower()
    assert "optional" in skill and "unverified until" in skill and "live" in skill
    capabilities = yaml.safe_load((ROOT / "capabilities.yaml").read_text(encoding="utf-8"))
    assert "calendar-operations" in capabilities["capability_packs"]["core-operator"]["skills"]


def test_dst_nonexistent_and_ambiguous_times_require_resolution():
    engine = calendar.CalendarEngine(calendar.FakeCalendarAdapter())
    with pytest.raises(calendar.TimeResolutionError, match="nonexistent"):
        engine.resolve_local("2026-03-08T02:30:00", "America/Chicago")
    with pytest.raises(calendar.TimeResolutionError, match="ambiguous"):
        engine.resolve_local("2026-11-01T01:30:00", "America/Chicago")
    first = engine.resolve_local("2026-11-01T01:30:00", "America/Chicago", fold=0)
    second = engine.resolve_local("2026-11-01T01:30:00", "America/Chicago", fold=1)
    assert first.utcoffset() != second.utcoffset()


def test_conflicts_block_write_and_proposals_stay_tentative():
    adapter = calendar.FakeCalendarAdapter(events=[event(status="confirmed")])
    engine = calendar.CalendarEngine(adapter)
    overlapping = event(event_id="event-2", start="2026-09-08T09:15:00-05:00", end="2026-09-08T09:45:00-05:00")
    assert engine.propose(overlapping)["status"] == "conflict"
    with pytest.raises(calendar.CalendarConflict):
        engine.apply("create", overlapping, "create-2", approved=True)
    free = event(event_id="event-3", start="2026-09-08T10:00:00-05:00", end="2026-09-08T10:30:00-05:00")
    assert engine.propose(free)["status"] == "tentative"


def test_recurrence_scope_cancel_reschedule_and_approval_denial():
    adapter = calendar.FakeCalendarAdapter(events=[event(status="confirmed", series_id="series-1")])
    engine = calendar.CalendarEngine(adapter)
    with pytest.raises(calendar.ApprovalDenied):
        engine.apply("cancel", event(series_id="series-1"), "cancel-1", approved=False)
    cancelled = engine.apply("cancel", event(series_id="series-1"), "cancel-1", approved=True)
    assert cancelled["status"] == "cancelled"
    assert cancelled["recurrence_scope"] == "occurrence"
    moved = event(start="2026-09-08T11:00:00-05:00", end="2026-09-08T11:30:00-05:00", series_id="series-1", recurrence_scope="this-and-future")
    result = engine.apply("reschedule", moved, "move-1", approved=True)
    assert result["lineage_event_id"] == "event-1"
    assert result["recurrence_scope"] == "this-and-future"
    with pytest.raises(ValueError, match="recurrence scope"):
        engine.apply("reschedule", event(recurrence_scope="one-day"), "move-2", approved=True)


def test_operation_key_replay_is_stable_and_provider_readback_is_required():
    adapter = calendar.FakeCalendarAdapter()
    engine = calendar.CalendarEngine(adapter)
    created = engine.apply("create", event(), "stable-key", approved=True)
    replay = engine.apply("create", event(), "stable-key", approved=True)
    assert replay == created
    assert adapter.write_count == 1
    with pytest.raises(calendar.OperationBindingError):
        engine.apply("create", event(start="2026-09-09T09:00:00-05:00"), "stable-key", approved=True)
    with pytest.raises(calendar.OperationBindingError):
        engine.apply("cancel", event(), "stable-key", approved=True)
    bad = calendar.FakeCalendarAdapter(readback_overrides={"calendar_id": "wrong-calendar"})
    with pytest.raises(calendar.ReadbackMismatch):
        calendar.CalendarEngine(bad).apply("create", event(), "bad-readback", approved=True)


def test_unknown_effect_reconciles_before_retry_or_remains_unknown():
    persisted = calendar.FakeCalendarAdapter(unknown_once=True, persist_before_unknown=True)
    result = calendar.CalendarEngine(persisted).apply("create", event(), "unknown-1", approved=True)
    assert result["effect"] == "confirmed-success"
    assert result["reconciled"] is True
    assert persisted.write_count == 1
    unresolved = calendar.FakeCalendarAdapter(unknown_once=True, persist_before_unknown=False)
    engine = calendar.CalendarEngine(unresolved)
    result = engine.apply("create", event(), "unknown-2", approved=True)
    assert result == {"effect": "unknown", "operation_key": "unknown-2"}
    assert unresolved.write_count == 1
    retry = calendar.CalendarEngine(unresolved, engine.store).apply("create", event(), "unknown-2", approved=True)
    assert retry["effect"] == "unknown"
    assert unresolved.write_count == 1


def test_calendar_binding_covers_approval_version_identity_and_exact_readback():
    adapter = calendar.FakeCalendarAdapter()
    engine = calendar.CalendarEngine(adapter)
    kwargs = {"approved": True, "approval_reference": "approval-7", "requirement_version": "task-8.v3"}
    engine.apply("create", event(series_id="series-1"), "bound", **kwargs)
    for changed in (event(organizer_id="other", series_id="series-1"), event(attendee_ids=["attendee-2"], series_id="series-1"), event(status="confirmed", series_id="series-1"), event(series_id="series-2")):
        with pytest.raises(calendar.OperationBindingError):
            engine.apply("create", changed, "bound", **kwargs)
    with pytest.raises(calendar.OperationBindingError):
        engine.apply("create", event(series_id="series-1"), "bound", approved=True, approval_reference="approval-8", requirement_version="task-8.v3")
    for field, wrong in (("organizer_id", "other"), ("attendee_ids", ["other"]), ("status", "tentative"), ("series_id", "other"), ("action", "cancel")):
        bad = calendar.FakeCalendarAdapter(readback_overrides={field: wrong})
        with pytest.raises(calendar.ReadbackMismatch, match=field):
            calendar.CalendarEngine(bad).apply("create", event(series_id="series-1"), f"bad-{field}", **kwargs)


def test_calendar_explicit_reconcile_delayed_failure_and_still_unknown():
    adapter = calendar.FakeCalendarAdapter(unknown_once=True, persist_before_unknown=False)
    engine = calendar.CalendarEngine(adapter)
    payload = event()
    assert engine.apply("create", payload, "later", approved=True)["effect"] == "unknown"
    adapter.persist_operation("create", payload, "later")
    assert engine.reconcile("later")["effect"] == "confirmed-success"
    assert engine.reconcile("missing")["effect"] == "not-found"
    unresolved = calendar.FakeCalendarAdapter(unknown_once=True)
    other = calendar.CalendarEngine(unresolved)
    other.apply("create", payload, "still", approved=True)
    assert other.reconcile("still")["effect"] == "unknown"
    unresolved.mark_failed("still")
    assert other.reconcile("still")["effect"] == "confirmed-failure"


def test_calendar_unknown_journal_survives_engine_restart(tmp_path):
    journal = tmp_path / "calendar-operations.json"
    adapter = calendar.FakeCalendarAdapter(unknown_once=True)
    calendar.CalendarEngine(adapter, calendar.OperationStore(journal)).apply("create", event(), "durable", approved=True)
    restarted = calendar.CalendarEngine(adapter, calendar.OperationStore(journal))
    assert restarted.apply("create", event(), "durable", approved=True)["effect"] == "unknown"
    assert adapter.write_count == 1
