import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "website-watchdog"
sys.path.insert(0, str(TOOL))


def load(name):
    spec = importlib.util.spec_from_file_location(f"hardening_{name}", TOOL / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def registry_site(**changes):
    value = {
        "id": "store-prod", "name": "Store", "enabled": True,
        "host": "store.example.test", "environment": "production",
        "health_url": "https://store.example.test/health",
        "credential_reference": "vault://websites/store-prod/deploy",
        "credential_principal": "deploy-store-prod", "owner": "web-operations",
        "repair_policy": "restart-known-service", "notification_route": "web-urgent",
        "status": "configured", "healthy_codes": [200], "timeout_seconds": 10,
        "attempts": 1, "retry_delay_seconds": 0, "failure_cycles": 2,
        "max_body_bytes": 65536, "allow_private_networks": False,
        "allowed_redirect_hosts": [], "allowed_repairs": ["restart-known-service"],
    }
    value.update(changes)
    return value


def registry(*sites):
    return {"schema_version": 1, "sites": list(sites or [registry_site()])}


def targets(module, source=None):
    return module.build_targets(source or registry())


def outcome(kind, ok=False):
    return {"ok": ok, "kind": kind, "status": 200 if ok else None,
            "final_url": "https://store.example.test/health", "latency_ms": 1}


def test_monitor_path_has_separate_health_and_never_advances_target_failure():
    watchdog = load("watchdog")
    site = {"id": "site", "failure_cycles": 2}
    first, event = watchdog.observe(site, {}, [outcome("monitor_path")], now="2026-01-01T00:00:00+00:00")
    second, event2 = watchdog.observe(site, first, [outcome("monitor_path")], now="2026-01-01T00:01:00+00:00")
    assert first["monitor_path"]["failure_cycles"] == 1
    assert second["monitor_path"]["failure_cycles"] == 2
    assert second["failure_cycles"] == 0 and second["status"] == "unknown"
    assert event is None and event2 is None


def test_shared_dns_failure_suppresses_mass_site_incidents(tmp_path):
    watchdog = load("watchdog")
    cfg = tmp_path / "targets.json"
    cfg.write_text(json.dumps({"sites": [
        {"id": "one", "name": "One", "url": "https://one.test", "attempts": 1, "failure_cycles": 1},
        {"id": "two", "name": "Two", "url": "https://two.test", "attempts": 1, "failure_cycles": 1},
    ]}))
    events = watchdog.run(cfg, tmp_path / "state.json", tmp_path / "incidents", probe_fn=lambda _: outcome("dns"))
    saved = json.loads((tmp_path / "state.json").read_text())
    assert events == [] and not (tmp_path / "incidents").exists()
    assert saved["monitor_path"]["kind"] == "shared_dns"
    assert all(site["failure_cycles"] == 0 for site in saved["sites"].values())


def test_registry_rejects_duplicate_canonical_ids():
    module = load("registry")
    with pytest.raises(ValueError, match="duplicate"):
        module.reconcile(registry(registry_site(), registry_site()), targets(module))


def test_registry_reports_missing_extra_duplicate_and_each_stale_policy_separately():
    module = load("registry")
    source = registry(registry_site(), registry_site(id="docs-prod", host="docs.example.test", health_url="https://docs.example.test/health", credential_reference="vault://websites/docs-prod/deploy", credential_principal="deploy-docs-prod"))
    good = targets(module, source)["sites"]
    assert module.reconcile(source, {"sites": [good[0]]})["missing"] == ["docs-prod"]
    assert module.reconcile(source, {"sites": good + [{**good[0], "id": "extra-prod"}]})["extra"] == ["extra-prod"]
    assert module.reconcile(source, {"sites": good + [good[0]]})["duplicates"] == ["store-prod"]
    for field, value in (("healthy_codes", [500]), ("timeout_seconds", 11), ("repair_policy", "other"), ("credential_principal", "other-principal")):
        changed = [dict(item) for item in good]; changed[0][field] = value
        assert field in module.reconcile(source, {"sites": changed})["stale"]["store-prod"]


def test_registry_semantics_bind_host_to_health_url():
    module = load("registry")
    with pytest.raises(ValueError, match="host"):
        module.reconcile(registry(registry_site(health_url="https://evil.test/health")), targets(module))


def test_occurrence_is_claimed_before_effects_and_replay_cannot_duplicate(tmp_path, monkeypatch):
    watchdog = load("watchdog")
    cfg = tmp_path / "targets.json"
    cfg.write_text(json.dumps({"sites": [{"id": "site", "name": "Site", "url": "https://site.test", "attempts": 1, "failure_cycles": 1}]}))
    original = watchdog.atomic_json
    crashed = {"done": False}
    def crash_state(path, data, mode=0o600):
        if Path(path).name == "state.json" and not crashed["done"]:
            crashed["done"] = True
            raise RuntimeError("crash after effects")
        return original(path, data, mode)
    monkeypatch.setattr(watchdog, "atomic_json", crash_state)
    with pytest.raises(RuntimeError):
        watchdog.run(cfg, tmp_path / "state.json", tmp_path / "incidents", probe_fn=lambda _: outcome("timeout"), occurrence_id="occ-1")
    monkeypatch.setattr(watchdog, "atomic_json", original)
    watchdog.run(cfg, tmp_path / "state.json", tmp_path / "incidents", probe_fn=lambda _: outcome("timeout"), occurrence_id="occ-1")
    assert len(list((tmp_path / "incidents").glob("*.json"))) == 1
    lines = (tmp_path / "state.json.events.jsonl").read_text().splitlines()
    assert len(lines) == 1


def incident_payload(expiry, token="token-one"):
    return {
        "schema_version": 1, "status": "leased", "incident_id": "incident-1",
        "worker_id": "worker", "lease_token": token,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        "lease_expires_at": expiry, "site": {"id": "store-prod", "name": "Store", "url": "https://store.example.test/health"},
        "evidence": {}
    }


def test_expired_or_stale_fencing_token_cannot_close_incident(tmp_path, monkeypatch):
    incident = load("incident"); path = tmp_path / "incident.json"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    path.write_text(json.dumps(incident_payload((now - timedelta(seconds=1)).isoformat())))
    monkeypatch.setattr(incident, "probe", lambda _: outcome("healthy", True))
    with pytest.raises(PermissionError, match="lease"):
        incident.mutate(path, "resolve", "worker", "evidence", lease_token="token-one", now_fn=lambda: now)
    path.write_text(json.dumps(incident_payload((now + timedelta(seconds=60)).isoformat(), "new-token")))
    with pytest.raises(PermissionError, match="lease"):
        incident.mutate(path, "resolve", "worker", "evidence", lease_token="old-token", now_fn=lambda: now)


def test_lease_issues_unique_fencing_token_and_requires_it_for_release(tmp_path, monkeypatch):
    incident = load("incident"); path = tmp_path / "incident.json"
    payload = incident_payload("2025-01-01T00:00:00+00:00"); payload["status"] = "queued"
    for field in ("worker_id", "lease_token", "lease_expires_at"): payload.pop(field, None)
    path.write_text(json.dumps(payload)); monkeypatch.setattr(incident, "probe", lambda _: outcome("timeout"))
    leased = incident.mutate(path, "lease", "worker")
    assert leased["lease_token"] and leased["lease_token"] != "worker"
    with pytest.raises(PermissionError): incident.mutate(path, "release", "worker", lease_token="wrong")


def test_repair_binding_rejects_cross_host_and_stale_approval():
    repair = load("repair")
    contract = repair_contract()
    canonical = repair_context()
    bad = json.loads(json.dumps(contract)); bad["acceptance"]["health_url"] = "https://evil.test/health"
    with pytest.raises(PermissionError, match="binding"):
        repair.validate_binding(bad, **canonical)
    stale = json.loads(json.dumps(canonical["approval"])); stale["version"] = 6
    with pytest.raises(PermissionError, match="binding"):
        repair.validate_binding(contract, canonical["incident"], canonical["registry_site"], stale, canonical["task"])


def repair_contract():
    return {
        "schema_version": 1, "handoff_id": "handoff-1", "incident_id": "incident-1", "site_id": "store-prod",
        "host": "store.example.test", "checkpoint": "confirmed-unhealthy", "credential_reference": "vault://websites/store-prod/deploy",
        "credential_principal": "deploy-store-prod", "allowed_action": "restart-known-service",
        "approval_reference": "approval://operator-control/apr-1", "approval_version": 7,
        "operator_task_reference": "kanban://task/task-1", "task_version": 3, "requirement_version": 2,
        "operation_key": "incident-1:restart-known-service:v2", "limits": {"max_attempts": 2, "max_elapsed_seconds": 1},
        "acceptance": {"health_url": "https://store.example.test/health", "healthy_codes": [200]},
        "worker": {"status": "configured", "id": "worker"}, "credential": {"status": "configured"},
        "approval": {"status": "configured"}, "notification": {"status": "configured", "route": "web-urgent"},
        "enforcement": {"status": "configured"}, "dispatch_enabled": True,
    }


def repair_context():
    return {
        "incident": {"incident_id": "incident-1", "status": "leased", "worker_id": "worker", "lease_token": "fencing-token-0001", "lease_expires_at": "2099-01-01T00:00:00+00:00", "site": {"id": "store-prod", "host": "store.example.test", "url": "https://store.example.test/health", "credential_reference": "vault://websites/store-prod/deploy", "credential_principal": "deploy-store-prod", "allowed_repairs": ["restart-known-service"], "repair_policy": "restart-known-service", "approval_reference": "approval://operator-control/apr-1", "approval_version": 7, "operator_task_reference": "kanban://task/task-1", "task_version": 3, "requirement_version": 2, "operation_key": "incident-1:restart-known-service:v2"}},
        "registry_site": registry_site(),
        "approval": {"reference": "approval://operator-control/apr-1", "version": 7, "status": "approved", "operation_key": "incident-1:restart-known-service:v2", "task_reference": "kanban://task/task-1", "task_version": 3, "site_id": "store-prod"},
        "task": {"reference": "kanban://task/task-1", "version": 3, "requirement_version": 2, "status": "in_progress"},
    }


def test_repair_budget_and_deadline_persist_and_check_after_action(tmp_path):
    repair = load("repair"); path = tmp_path / "incident.json"
    context = repair_context(); path.write_text(json.dumps(context["incident"]))
    ticks = iter([0, 0, 0, 0, 1500])
    result = repair.run_synthetic(repair_contract(), "store-prod", "vault://websites/store-prod/deploy", "restart-known-service", lambda _: None, lambda _: {"ok": False}, lambda: next(ticks), incident_path=path, **context, **execution_context(path, context))
    assert result["status"] == "failed" and result["reason"] == "repair_deadline_exceeded"
    saved = json.loads(path.read_text())["repair_state"]
    assert saved["attempts"] == 1 and saved["started_ms"] == 0 and saved["deadline_ms"] == 1000


def test_credential_delivery_requires_bound_opaque_handle_and_positive_readback(tmp_path):
    delivery = load("credential_delivery"); service = action_broker(tmp_path)
    ticks = iter([0, 2, 5])
    binding = delivery_binding(); reference = binding.pop("credential_reference")
    record, _ = delivery.measure(reference, service,
        lambda protected: {"provider_id": "delivery-1", "confirmed": True, "readback": protected},
        lambda: next(ticks), "test", 10, **binding)
    assert record["delivery_status"] == "confirmed" and record["threshold_met"] is True
    bad = delivery_binding(); reference = bad.pop("credential_reference")
    with pytest.raises(RuntimeError, match="confirmed"):
        delivery.measure(reference, service, lambda _: {"provider_id": "delivery-2", "confirmed": False},
                         lambda: 0, "test", 10, **bad)


def test_data_writes_reject_symlink_hardlink_and_symlink_parent(tmp_path):
    watchdog = load("watchdog")
    victim = tmp_path / "victim"; victim.write_text("safe")
    event = tmp_path / "events"; event.symlink_to(victim)
    with pytest.raises(OSError): watchdog.append_event(event, {"kind": "x"})
    assert victim.read_text() == "safe"
    hard = tmp_path / "hard"; os.link(victim, hard)
    with pytest.raises(PermissionError): watchdog.append_event(hard, {"kind": "x"})
    real = tmp_path / "real"; real.mkdir(); linked = tmp_path / "linked"; linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError): watchdog.atomic_json(linked / "state.json", {})


def test_runtime_schemas_are_closed_and_reject_secret_fields_and_cross_host():
    incident_schema = json.loads((TOOL / "incident.schema.json").read_text())
    payload = incident_payload("2099-01-01T00:00:00+00:00"); payload["plaintext_password"] = "bad"
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(payload, incident_schema)
    repair = load("repair")
    with pytest.raises(PermissionError): repair.validate_binding({**repair_contract(), "plaintext_password": "bad"}, **repair_context())


def test_generated_incident_copies_complete_canonical_repair_snapshot_and_binds(tmp_path):
    watchdog = load("watchdog"); repair = load("repair")
    source = registry_site(
        approval_reference="approval://operator-control/apr-1", approval_version=7,
        operator_task_reference="kanban://task/task-1", task_version=3,
        requirement_version=2, operation_key="incident-1:restart-known-service:v2", failure_cycles=1,
    )
    target = load("registry").build_targets(registry(source))["sites"][0]
    cfg = tmp_path / "targets.json"; cfg.write_text(json.dumps({"sites": [target]}))
    watchdog.run(cfg, tmp_path / "state.json", tmp_path / "incidents",
                 probe_fn=lambda _: outcome("timeout"), occurrence_id="incident-generation")
    generated = json.loads(next((tmp_path / "incidents").glob("*.json")).read_text())
    site = generated["site"]
    assert site["host"] == "store.example.test"
    for field in ("credential_reference", "credential_principal", "healthy_codes",
                  "approval_reference", "approval_version", "operator_task_reference",
                  "task_version", "requirement_version", "operation_key", "repair_policy"):
        assert site[field] == target[field]
    contract = repair_contract(); contract["incident_id"] = generated["incident_id"]
    contract["operation_key"] = target["operation_key"]
    context = repair_context(); context["incident"] = generated
    repair.validate_binding(contract, **context)


def test_repair_requires_all_authoritative_readbacks_and_rereads_around_effect(tmp_path):
    repair = load("repair"); context = repair_context(); path = tmp_path / "incident.json"
    path.write_text(json.dumps(context["incident"])); contract = repair_contract()
    with pytest.raises(TypeError, match="readback"):
        repair.run_synthetic(contract, "store-prod", contract["credential_reference"],
                             contract["allowed_action"], lambda _: None,
                             lambda _: {"ok": False}, lambda: 0,
                             incident_path=path, **context)
    calls = []
    def resolver(name, value):
        def read(): calls.append(name); return json.loads(json.dumps(value))
        return read
    result = repair.run_synthetic(
        contract, "store-prod", contract["credential_reference"], contract["allowed_action"],
        lambda _: calls.append("apply"), lambda _: calls.append("probe") or {"ok": True}, lambda: 0,
        incident_path=path, incident=context["incident"], registry_site=context["registry_site"],
        approval=context["approval"], task=context["task"],
        incident_readback_fn=resolver("incident", context["incident"]),
        registry_readback_fn=resolver("registry", context["registry_site"]),
        approval_readback_fn=resolver("approval", context["approval"]),
        task_readback_fn=resolver("task", context["task"]),
        broker_readback_fn=lambda operation_key: calls.append("broker") or {"operation_key": operation_key, "authorized": True},
        worker_id="worker", lease_token="fencing-token-0001",
    )
    assert result["status"] == "resolved"
    assert calls[:5] == ["incident", "registry", "approval", "task", "broker"]
    assert calls[-6:] == ["incident", "registry", "approval", "task", "broker", "probe"]


def test_action_broker_owns_signed_persisted_credential_handles_and_receipts(tmp_path):
    import hashlib
    plugin = ROOT / "plugins" / "operator-control"; tools = ROOT / "tools" / "operator-control"
    schemas = load_external("operator_control_schemas", plugin / "schemas.py")
    load_external("operator_control_policy", plugin / "policy.py")
    load_external("operator_control_store", tools / "store.py")
    broker_module = load_external("operator_control_broker_final", tools / "broker.py")
    service = action_broker(tmp_path)
    binding = {
        "approval_reference": "approval://operator-control/apr-1", "approval_version": 7,
        "task_reference": "kanban://task/task-1", "task_version": 3, "requirement_version": 2,
        "site_id": "store-prod", "credential_reference": "vault://websites/store-prod/deploy",
        "credential_principal": "deploy-store-prod", "recipient": "ops@example.test",
        "allowed_action": "restart-known-service", "operation_key": "incident-1:restart-known-service:v2",
    }
    handle_id = service.issue_credential_handle(binding)
    assert handle_id.startswith("ch_") and "deploy" not in handle_id
    receipt_id = service.deliver_credential(handle_id, lambda protected: {
        "provider_id": "provider-delivery-1", "confirmed": True,
        "readback": {**binding, "handle_id": handle_id},
    })
    receipt = service.read_credential_receipt(receipt_id, binding)
    assert receipt["confirmed"] is True and receipt["handle_id"] == handle_id
    tampered = handle_id[:-1] + ("0" if handle_id[-1] != "0" else "1")
    with pytest.raises(PermissionError): service.read_credential_handle(tampered, binding)
    with pytest.raises(ValueError, match="secret"):
        service.issue_credential_handle({**binding, "metadata": {"nested": {"password": "bad"}}})  # pragma: allowlist secret
    with pytest.raises((PermissionError, RuntimeError)):
        service.deliver_credential(handle_id, lambda _: {"provider_id": "p", "confirmed": True,
                                                          "readback": {**binding, "recipient": "other"}})


def load_external(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def action_broker(tmp_path):
    plugin = ROOT / "plugins" / "operator-control"; tools = ROOT / "tools" / "operator-control"
    load_external("operator_control_schemas", plugin / "schemas.py")
    load_external("operator_control_policy", plugin / "policy.py")
    load_external("operator_control_store", tools / "store.py")
    module = load_external("operator_control_broker_credentials", tools / "broker.py")
    assets = tmp_path / "broker-policy"; assets.mkdir(exist_ok=True); (assets / "policy.json").write_text('{"version":1}')
    return module.ActionBroker(tmp_path / "broker" / "control.db", policy_root=assets,
                               supported_routes=("website.repair",), signing_key=b"website-test-signing-key-32bytes")


def delivery_binding():
    return {"approval_reference": "approval://operator-control/apr-1", "approval_version": 7,
            "task_reference": "kanban://task/task-1", "task_version": 3, "requirement_version": 2,
            "site_id": "store-prod", "credential_reference": "vault://websites/store-prod/deploy",
            "credential_principal": "deploy-store-prod", "recipient": "ops@example.test",
            "allowed_action": "restart-known-service", "operation_key": "incident-1:restart-known-service:v2"}


def execution_context(path, context):
    return {"incident_readback_fn": lambda: json.loads(path.read_text()),
            "registry_readback_fn": lambda: context["registry_site"],
            "approval_readback_fn": lambda: context["approval"],
            "task_readback_fn": lambda: context["task"],
            "broker_readback_fn": lambda operation_key: {"operation_key": operation_key, "authorized": True},
            "worker_id": "worker", "lease_token": "fencing-token-0001"}


def test_registry_and_target_require_nonblank_credential_principal():
    registry_schema = json.loads((ROOT / "templates" / "website-registry.schema.json").read_text())
    target_schema = json.loads((TOOL / "sites.schema.json").read_text())
    for missing in (True, False):
        source = registry_site()
        if missing: source.pop("credential_principal")
        else: source["credential_principal"] = ""
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(registry(source), registry_schema)
        target = load("registry")._target(registry_site())
        if missing: target.pop("credential_principal")
        else: target["credential_principal"] = ""
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"sites": [target]}, target_schema)


def test_repair_rejects_expired_or_stale_lease_before_budget_mutation(tmp_path):
    repair = load("repair"); context = repair_context(); path = tmp_path / "incident.json"
    context["incident"]["lease_expires_at"] = "2020-01-01T00:00:00+00:00"
    context["incident"]["repair_state"] = {"attempts": 1, "started_ms": 0, "deadline_ms": 1000,
                                             "operation_key": "incident-1:restart-known-service:v2"}
    path.write_text(json.dumps(context["incident"])); before = path.read_text()
    with pytest.raises(PermissionError, match="lease"):
        repair.run_synthetic(repair_contract(), "store-prod", "vault://websites/store-prod/deploy",
                             "restart-known-service", lambda _: pytest.fail("stale worker acted"),
                             lambda _: {"ok": False}, lambda: 0, incident_path=path, **context,
                             **execution_context(path, context))
    assert path.read_text() == before
