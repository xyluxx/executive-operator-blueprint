import importlib.util
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "website-watchdog"
sys.path.insert(0, str(TOOL))


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOL / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def registry_site(**updates):
    site = {
        "id": "store-prod", "name": "Store", "enabled": True,
        "host": "store.example.test", "environment": "production",
        "health_url": "https://store.example.test/health",
        "credential_reference": "vault://websites/store-prod/deploy",
        "credential_principal": "deploy-store-prod",
        "owner": "web-operations", "repair_policy": "restart-known-service",
        "notification_route": "web-urgent", "status": "planned",
    }
    site.update(updates)
    return site


def target(**updates):
    item = {
        "id": "store-prod", "name": "Store", "enabled": True,
        "host": "store.example.test", "environment": "production",
        "url": "https://store.example.test/health",
        "credential_reference": "vault://websites/store-prod/deploy",
        "credential_principal": "deploy-store-prod",
        "owner": "web-operations", "repair_policy": "restart-known-service",
        "notification_route": "web-urgent",
    }
    item.update(updates)
    return item


def test_canonical_registry_example_validates_and_contains_references_only():
    schema = json.loads((ROOT / "templates" / "website-registry.schema.json").read_text())
    example = json.loads((ROOT / "templates" / "website-registry.example.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(example, schema)
    serialized = json.dumps(example).lower()
    assert "credential_reference" in serialized
    for forbidden in ("password", "secret_value", "credential_value", "api_key", "access_token"):
        assert forbidden not in serialized
    assert all(site["status"] in {"planned", "blocked", "configured"} for site in example["sites"])


def test_registry_reconciliation_is_exact_and_reports_all_drift_classes():
    module = load("registry")
    registry = {"schema_version": 1, "sites": [registry_site(), registry_site(id="docs-prod", host="docs.example.test", health_url="https://docs.example.test/health", credential_reference="vault://websites/docs-prod/deploy", credential_principal="deploy-docs-prod")]}
    targets = {"sites": [target(), target(), target(id="old-prod"), target(id="docs-prod", host="wrong.example.test", url="https://docs.example.test/health", credential_reference="vault://websites/docs-prod/deploy", credential_principal="deploy-docs-prod")]}
    report = module.reconcile(registry, targets)
    assert report["ok"] is False
    assert report["missing"] == []
    assert report["duplicates"] == ["store-prod"]
    assert report["extra"] == ["old-prod"]
    assert report["stale"] == {"docs-prod": {"host": {"registry": "docs.example.test", "target": "wrong.example.test"}}}


def test_registry_build_targets_preserves_contract_fields_exactly():
    module = load("registry")
    source = registry_site()
    built = module.build_targets({"schema_version": 1, "sites": [source, registry_site(id="off", enabled=False)]})
    assert built == {"sites": [target()]}
    assert module.reconcile({"schema_version": 1, "sites": [source]}, built)["ok"] is True


def test_scheduler_occurrence_is_idempotent_and_current_health_readback_uses_clock(tmp_path):
    watchdog = load("watchdog")
    cfg = tmp_path / "targets.json"
    cfg.write_text(json.dumps({"sites": [target(attempts=1, failure_cycles=2)]}))
    state = tmp_path / "state.json"
    clock = lambda: "2026-09-05T12:00:00+00:00"
    first = watchdog.run(cfg, state, tmp_path / "incidents", probe_fn=lambda _: {"ok": True, "kind": "healthy", "status": 200, "final_url": "https://store.example.test/health", "latency_ms": 4}, now_fn=clock, occurrence_id="cron:website-watchdog:2026-09-05T12:00:00Z")
    second = watchdog.run(cfg, state, tmp_path / "incidents", probe_fn=lambda _: (_ for _ in ()).throw(AssertionError("duplicate probed")), now_fn=clock, occurrence_id="cron:website-watchdog:2026-09-05T12:00:00Z")
    assert first == [] and second == []
    health = watchdog.current_health(state, now_fn=clock, max_age_seconds=60)
    assert health["fresh"] is True
    assert health["sites"]["store-prod"]["status"] == "healthy"
    assert health["occurrence_id"] == "cron:website-watchdog:2026-09-05T12:00:00Z"


def handoff(**updates):
    value = {
        "schema_version": 1, "handoff_id": "handoff-001", "incident_id": "incident-001",
        "site_id": "store-prod", "host": "store.example.test", "checkpoint": "confirmed-unhealthy",
        "credential_reference": "vault://websites/store-prod/deploy", "credential_principal": "deploy-store-prod", "allowed_action": "restart-known-service",
        "approval_reference": "approval://operator-control/apr-001", "approval_version": 1,
        "operator_task_reference": "kanban://task/task-001", "task_version": 1, "requirement_version": 1,
        "operation_key": "incident-001:restart-known-service:v1",
        "limits": {"max_attempts": 2, "max_elapsed_seconds": 60},
        "acceptance": {"health_url": "https://store.example.test/health", "healthy_codes": [200]},
        "worker": {"status": "configured", "id": "synthetic-worker"},
        "credential": {"status": "configured"}, "approval": {"status": "configured"},
        "notification": {"status": "configured", "route": "web-urgent"},
        "enforcement": {"status": "configured"}, "dispatch_enabled": True,
    }
    value.update(updates)
    return value


def repair_context(tmp_path):
    incident = {"incident_id": "incident-001", "status": "leased", "worker_id": "synthetic-worker",
                "lease_token": "fencing-token-0001", "lease_expires_at": "2099-01-01T00:00:00+00:00", "site": {
        "id": "store-prod", "host": "store.example.test", "url": "https://store.example.test/health",
        "credential_reference": "vault://websites/store-prod/deploy", "credential_principal": "deploy-store-prod",
        "allowed_repairs": ["restart-known-service"], "repair_policy": "restart-known-service",
        "approval_reference": "approval://operator-control/apr-001", "approval_version": 1,
        "operator_task_reference": "kanban://task/task-001", "task_version": 1,
        "requirement_version": 1, "operation_key": "incident-001:restart-known-service:v1",
    }}
    path = tmp_path / "incident.json"
    path.write_text(json.dumps(incident))
    context = {
        "incident": incident, "registry_site": registry_site(healthy_codes=[200], allowed_repairs=["restart-known-service"]),
        "approval": {"reference": "approval://operator-control/apr-001", "version": 1, "status": "approved",
                     "operation_key": "incident-001:restart-known-service:v1", "task_reference": "kanban://task/task-001",
                     "task_version": 1, "site_id": "store-prod"},
        "task": {"reference": "kanban://task/task-001", "version": 1, "requirement_version": 1, "status": "in_progress"},
        "incident_path": path, "worker_id": "synthetic-worker", "lease_token": "fencing-token-0001",
    }
    context.update({
        "incident_readback_fn": lambda: json.loads(path.read_text()),
        "registry_readback_fn": lambda: context["registry_site"],
        "approval_readback_fn": lambda: context["approval"],
        "task_readback_fn": lambda: context["task"],
        "broker_readback_fn": lambda operation_key: {"operation_key": operation_key, "authorized": True},
    })
    return context


def test_handoff_schema_and_example_validate():
    schema = json.loads((TOOL / "repair-handoff.schema.json").read_text())
    example = json.loads((TOOL / "repair-handoff.example.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(example, schema)


def test_dispatch_stays_honestly_blocked_or_planned_when_prerequisite_missing():
    repair = load("repair")
    assert repair.dispatch_decision(handoff(dispatch_enabled=False))["status"] == "planned"
    for field in ("worker", "credential", "approval", "notification", "enforcement"):
        item = handoff()
        item[field] = {"status": "blocked"}
        decision = repair.dispatch_decision(item)
        assert decision == {"dispatch": False, "status": "blocked", "reason": f"{field}_blocked"}


def test_synthetic_worker_enforces_target_scope_limits_and_verified_resolution(tmp_path):
    repair = load("repair")
    contract = handoff()
    calls = []
    checks = iter([{"ok": False}, {"ok": False}, {"ok": True, "status": 200}])
    context = repair_context(tmp_path)
    result = repair.run_synthetic(contract, "store-prod", "vault://websites/store-prod/deploy", "restart-known-service", lambda c: calls.append((c["site_id"], c["host"])), lambda _: next(checks), now_ms=lambda: 0, **context)
    assert result["status"] == "resolved"
    assert result["post_repair_health"]["ok"] is True
    assert calls == [("store-prod", "store.example.test"), ("store-prod", "store.example.test")]
    for bad in (("other", contract["credential_reference"], contract["allowed_action"]), (contract["site_id"], "vault://websites/other/deploy", contract["allowed_action"]), (contract["site_id"], contract["credential_reference"], "shell")):
        try:
            repair.run_synthetic(contract, *bad, lambda _: None, lambda _: {"ok": False}, now_ms=lambda: 0, **context)
        except PermissionError:
            pass
        else:
            raise AssertionError("cross-scope repair accepted")


def test_failed_bounded_repair_escalates_but_routine_success_is_quiet(tmp_path):
    repair = load("repair")
    notify = load("notifications")
    checks = iter([{"ok": False}, {"ok": False}, {"ok": False}])
    failed = repair.run_synthetic(handoff(), "store-prod", "vault://websites/store-prod/deploy", "restart-known-service", lambda _: None, lambda _: next(checks), now_ms=lambda: 0, **repair_context(tmp_path))
    assert failed["status"] == "failed" and failed["attempts"] == 2
    default = notify.evaluate("bounded_repair_failed", "web-urgent")
    assert default == {"notify": True, "route": "web-urgent", "reason": "bounded_repair_failed"}
    for event in ("healthy", "false_alarm", "routine_repair_succeeded"):
        assert notify.evaluate(event, "web-urgent")["notify"] is False
    assert notify.evaluate("routine_repair_succeeded", "web-urgent", {"routine_repair_succeeded": "notify"})["notify"] is True


def test_incident_cannot_resolve_without_post_repair_health_readback(tmp_path, monkeypatch):
    incident = load("incident")
    path = tmp_path / "incident.json"
    path.write_text(json.dumps({
        "schema_version": 1, "status": "leased", "incident_id": "incident-1",
        "worker_id": "worker", "lease_token": "fencing-token-0001", "created_at": "2026-09-05T00:00:00+00:00",
        "updated_at": "2026-09-05T00:00:00+00:00", "lease_expires_at": "2099-01-01T00:00:00+00:00",
        "site": {"id": "store-prod", "url": "https://store.example.test/health"}, "evidence": {},
    }))
    monkeypatch.setattr(incident, "probe", lambda _: {"ok": False, "kind": "http"})
    try:
        incident.mutate(path, "resolve", "worker", "claimed", lease_token="fencing-token-0001")
    except RuntimeError as exc:
        assert "health verification" in str(exc)
    else:
        raise AssertionError("unhealthy incident resolved")
    monkeypatch.setattr(incident, "probe", lambda _: {"ok": True, "kind": "healthy", "status": 200})
    resolved = incident.mutate(path, "resolve", "worker", "verified", lease_token="fencing-token-0001")
    assert resolved["status"] == "resolved"
    assert resolved["post_repair_probe"]["ok"] is True


def test_credential_delivery_latency_is_measured_without_model_secret_exposure():
    delivery = load("credential_delivery")
    ticks = iter([1000, 1012, 1020])
    seen = {}
    binding = {
        "approval_reference": "approval://operator-control/apr-001", "approval_version": 1,
        "task_reference": "kanban://task/task-001", "task_version": 1, "requirement_version": 1,
        "site_id": "store-prod", "credential_principal": "deploy-store-prod",
        "recipient": "ops@example.test", "allowed_action": "restart-known-service",
        "operation_key": "incident-001:restart-known-service:v1",
    }
    class BrokerDouble:
        def issue_credential_handle(self, actual):
            seen["binding"] = actual; return "broker-owned-handle"
        def read_credential_handle(self, handle_id, actual):
            assert actual == seen["binding"]; return {"handle_id": handle_id, **actual}
        def deliver_credential(self, handle_id, provider):
            protected = {"handle_id": handle_id, **seen["binding"]}; provider(protected)
            return "broker-owned-receipt"
        def read_credential_receipt(self, receipt_id, actual):
            return {"receipt_id": receipt_id, "handle_id": "broker-owned-handle", "confirmed": True, **actual}
    def direct_send(protected):
        seen["send"] = protected
        return {"provider_id": "delivery-1", "confirmed": True, "readback": protected}
    record, model_view = delivery.measure("vault://websites/store-prod/deploy", BrokerDouble(), direct_send,
        now_ms=lambda: next(ticks), environment="deterministic-local-fake", threshold_ms=25, **binding)
    assert record["lookup_to_delivery_ms"] == 20 and record["threshold_met"] is True
    assert record["environment"] == "deterministic-local-fake" and record["threshold_ms"] == 25
    assert seen["send"]["handle_id"] == "broker-owned-handle"
    serialized = json.dumps(model_view)
    assert "broker-owned-handle" not in serialized and "ops@example.test" not in serialized
    assert model_view == {"credential_reference": "vault://websites/store-prod/deploy", "delivery_status": "confirmed", "latency_ms": 20, "threshold_met": True, "environment": "deterministic-local-fake"}
