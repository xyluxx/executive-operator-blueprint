import copy
import importlib.util
import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "templates" / "daily-brief-routine.schema.json"
RECORD_SCHEMA_PATH = ROOT / "templates" / "delivery-record.schema.json"
EXAMPLE_PATH = ROOT / "templates" / "daily-brief-routine.example.yaml"
MODULE_PATH = ROOT / "tools" / "operator-state" / "daily_use.py"
SPEC = importlib.util.spec_from_file_location("daily_use_brief", MODULE_PATH)
assert SPEC and SPEC.loader
brief = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(brief)


def load_contract():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    example = yaml.safe_load(EXAMPLE_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return schema, example, validator


def task(section="todays-commitments", text="Approve budget"):
    return {"task_id": "task-1", "section": section, "summary": text, "status": "ready"}


def test_daily_brief_example_and_delivery_record_schemas_validate():
    _, example, validator = load_contract()
    assert not list(validator.iter_errors(example))
    assert example["schedule"]["enabled"] is False
    assert example["empty_policy"] == "stay-silent"
    assert example["delivery"]["deduplication"]["key_fields"] == [
        "routine_id", "scheduled_occurrence", "channel", "recipient"
    ]
    record_schema = json.loads(RECORD_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator.check_schema(record_schema)


def test_engine_reads_canonical_kanban_and_only_approved_sources_without_mutation():
    fixture = [task()]
    before = copy.deepcopy(fixture)
    kanban = brief.FakeKanbanAdapter(fixture)
    sources = brief.FakeSourceAdapter({"approved-calendar": [task("decisions-waiting", "Choose slot")]})
    delivery = brief.FakeDeliveryAdapter()
    engine = brief.DailyBriefEngine(kanban, sources, delivery)
    result = engine.run("weekday-executive-brief", "2026-09-08T07:30:00-05:00", "chat", "principal-1", ["approved-calendar"])
    assert result["state"] == "confirmed-success"
    assert kanban.read_count == 1
    assert sources.read_names == ["approved-calendar"]
    assert fixture == before == kanban.tasks


def test_empty_run_is_quiet_and_writes_no_delivery_record():
    delivery = brief.FakeDeliveryAdapter()
    engine = brief.DailyBriefEngine(brief.FakeKanbanAdapter([]), brief.FakeSourceAdapter({}), delivery)
    result = engine.run("weekday-executive-brief", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    assert result == {"state": "suppressed-empty"}
    assert delivery.send_count == 0
    assert delivery.records == {}


def test_dedup_key_is_content_independent_and_record_is_written_and_read_back():
    kanban = brief.FakeKanbanAdapter([task(text="Version one")])
    delivery = brief.FakeDeliveryAdapter()
    engine = brief.DailyBriefEngine(kanban, brief.FakeSourceAdapter({}), delivery)
    first = engine.run("weekday-executive-brief", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    kanban.tasks[0]["summary"] = "Changed content"
    second = engine.run("weekday-executive-brief", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    assert second["state"] == "deduplicated"
    assert second["operation_key"] == first["operation_key"]
    assert delivery.send_count == 1
    record = delivery.read_record(first["operation_key"])
    assert record == first
    schema = json.loads(RECORD_SCHEMA_PATH.read_text())
    jsonschema.validate(record, schema, format_checker=jsonschema.FormatChecker())


def test_channel_or_recipient_changes_operation_identity():
    delivery = brief.FakeDeliveryAdapter()
    engine = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery)
    occurrence = "2026-09-08T07:30:00-05:00"
    one = engine.run("routine", occurrence, "chat", "principal-1", [])
    two = engine.run("routine", occurrence, "email", "principal-1", [])
    three = engine.run("routine", occurrence, "chat", "principal-2", [])
    assert len({one["operation_key"], two["operation_key"], three["operation_key"]}) == 3


def test_unknown_delivery_is_reconciled_without_blind_retry():
    delivery = brief.FakeDeliveryAdapter(unknown_once=True, persist_before_unknown=True)
    engine = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery)
    result = engine.run("routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    assert result["state"] == "confirmed-success"
    assert result["reconciliation"] == "found-after-unknown"
    assert delivery.send_count == 1
    unresolved = brief.FakeDeliveryAdapter(unknown_once=True, persist_before_unknown=False)
    result = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), unresolved).run(
        "routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", []
    )
    assert result["state"] == "unknown"
    assert unresolved.send_count == 1
    retry = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), unresolved).run(
        "routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", []
    )
    assert retry["state"] == "unknown"
    assert unresolved.send_count == 1


def test_daily_brief_explicit_reconcile_delayed_failure_and_still_unknown():
    delivery = brief.FakeDeliveryAdapter(unknown_once=True)
    engine = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery)
    unknown = engine.run("routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    key = unknown["operation_key"]
    assert engine.reconcile(key)["state"] == "unknown"
    delivery.persist_record(engine.store.get(key)["intent"])
    assert engine.reconcile(key)["state"] == "confirmed-success"
    failed_delivery = brief.FakeDeliveryAdapter(unknown_once=True)
    failed = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), failed_delivery)
    failed_key = failed.run("routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])["operation_key"]
    failed_delivery.mark_failed(failed_key)
    assert failed.reconcile(failed_key)["state"] == "confirmed-failure"


def test_daily_brief_unknown_journal_survives_engine_restart(tmp_path):
    journal = tmp_path / "brief-operations.json"
    delivery = brief.FakeDeliveryAdapter(unknown_once=True)
    args = ("routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery,
                           brief.OperationStore(journal)).run(*args)
    restarted = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery,
                                       brief.OperationStore(journal))
    assert restarted.run(*args)["state"] == "unknown"
    assert delivery.send_count == 1


def test_delivery_readback_mismatch_is_not_success():
    delivery = brief.FakeDeliveryAdapter(readback_overrides={"recipient": "wrong-recipient"})
    engine = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery)
    result = engine.run("routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    assert result["state"] == "unknown"
    assert result["reconciliation"] == "readback-mismatch"


def test_preexisting_provider_record_is_deduplicated_only_after_exact_readback():
    args = ("routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    delivery = brief.FakeDeliveryAdapter()
    seed = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery)
    first = seed.run(*args)
    restarted = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery,
                                      brief.OperationStore())
    result = restarted.run(*args)
    assert result == {"state": "deduplicated", "operation_key": first["operation_key"]}
    assert restarted.store.get(first["operation_key"])["result"]["state"] == "confirmed-success"
    assert delivery.send_count == 1


def test_preexisting_provider_mismatch_failure_and_unknown_never_report_success():
    args = ("routine", "2026-09-08T07:30:00-05:00", "chat", "principal-1", [])
    key = brief.DailyBriefEngine.operation_key(*args[:4])
    content = "[todays-commitments] Approve budget"
    base = {"schema_version":"1.0", "routine_id":args[0], "scheduled_occurrence":args[1],
            "operation_key":key, "channel":args[2], "recipient":args[3],
            "content_digest":__import__("hashlib").sha256(content.encode()).hexdigest(),
            "created_at":"2026-09-05T12:00:00Z", "provider_delivery_id":None, "delivered_at":None}
    for state, mutation in (
        ("confirmed-success", {"recipient": "attacker"}),
        ("confirmed-failure", {}),
        ("unknown", {}),
    ):
        delivery = brief.FakeDeliveryAdapter()
        delivery.records[key] = {**base, "state":state, "reconciliation":"provider-readback", **mutation}
        engine = brief.DailyBriefEngine(brief.FakeKanbanAdapter([task()]), brief.FakeSourceAdapter({}), delivery,
                                        brief.OperationStore())
        result = engine.run(*args)
        assert result["state"] != "deduplicated"
        assert result["state"] == ("unknown" if mutation or state == "unknown" else "confirmed-failure")
        assert delivery.send_count == 0
