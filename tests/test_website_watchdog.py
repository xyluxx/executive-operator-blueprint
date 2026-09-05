import importlib.util
import json
import multiprocessing
import sys
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema

MODULE_PATH = Path(__file__).parents[1] / "tools" / "website-watchdog" / "watchdog.py"
SPEC = importlib.util.spec_from_file_location("watchdog", MODULE_PATH)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)
TOOL_DIR = MODULE_PATH.parent
sys.path.insert(0, str(TOOL_DIR))
INCIDENT_SPEC = importlib.util.spec_from_file_location("incident_tool", TOOL_DIR / "incident.py")
assert INCIDENT_SPEC and INCIDENT_SPEC.loader
incident_tool = importlib.util.module_from_spec(INCIDENT_SPEC)
INCIDENT_SPEC.loader.exec_module(incident_tool)


def config(path):
    path.write_text(json.dumps({"sites": [{
        "id": "site", "name": "Site", "url": "https://site.test/health",
        "attempts": 1, "failure_cycles": 2,
    }]}))


def sequence(values):
    items = iter(values)
    return lambda site: next(items)


def result(ok, code=200, error=None):
    return {"ok": ok, "status": code, "kind": "healthy" if ok else (error or "timeout"), "final_url": "https://site.test/health", "latency_ms": 10}


def lease_in_process(path, worker, start, output):
    start.wait()
    try:
        output.put((worker, incident_tool.mutate(path, "lease", worker)["status"]))
    except Exception as exc:
        output.put((worker, type(exc).__name__))


def test_healthy_run_is_silent(tmp_path):
    cfg = tmp_path / "sites.json"; config(cfg)
    events = watchdog.run(cfg, tmp_path / "state.json", tmp_path / "incidents", probe_fn=sequence([result(True)]))
    assert events == []
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["sites"]["site"]["status"] == "healthy"


def test_transient_then_confirmed_failure_creates_one_incident(tmp_path):
    cfg = tmp_path / "sites.json"; config(cfg)
    state = tmp_path / "state.json"; incidents = tmp_path / "incidents"
    first = watchdog.run(cfg, state, incidents, probe_fn=sequence([result(False, 0, "timeout")]))
    assert [event["kind"] for event in first] == ["transient_failure"]
    assert not incidents.exists()

    second = watchdog.run(cfg, state, incidents, probe_fn=sequence([result(False, 0, "timeout")]))
    assert [event["kind"] for event in second] == ["confirmed_failure"]
    files = list(incidents.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert payload["status"] == "queued"
    incident_id = payload["incident_id"]

    third = watchdog.run(cfg, state, incidents, probe_fn=sequence([result(False, 0, "timeout")]))
    assert third == []
    assert len(list(incidents.glob("*.json"))) == 1
    assert json.loads(state.read_text())["sites"]["site"]["incident_id"] == incident_id


def test_recovery_closes_current_incident_state(tmp_path):
    cfg = tmp_path / "sites.json"; config(cfg)
    state = tmp_path / "state.json"; incidents = tmp_path / "incidents"
    watchdog.run(cfg, state, incidents, probe_fn=sequence([result(False)]))
    watchdog.run(cfg, state, incidents, probe_fn=sequence([result(False)]))
    recovered = watchdog.run(cfg, state, incidents, probe_fn=sequence([result(True)]))
    assert [event["kind"] for event in recovered] == ["recovered"]
    saved = json.loads(state.read_text())["sites"]["site"]
    assert saved["status"] == "healthy"
    assert saved["incident_id"] is None
    incident = json.loads(list(incidents.glob("*.json"))[0].read_text())
    assert incident["status"] == "resolved"
    assert incident["reason"] == "recovered_before_ai"


def test_disabled_site_is_not_probed(tmp_path):
    cfg = tmp_path / "sites.json"
    cfg.write_text(json.dumps({"sites": [{"id": "site", "name": "Site", "url": "https://site.test", "enabled": False}]}))
    events = watchdog.run(cfg, tmp_path / "state.json", tmp_path / "incidents", probe_fn=lambda site: (_ for _ in ()).throw(AssertionError("called")))
    assert events == []


def test_duplicate_ids_and_url_credentials_are_rejected(tmp_path):
    cfg = tmp_path / "sites.json"
    cfg.write_text(json.dumps({"sites": [
        {"id": "same", "name": "One", "url": "https://site.test"},
        {"id": "same", "name": "Two", "url": "https://user:password@example.test"},  # pragma: allowlist secret
    ]}))
    try:
        watchdog.run(cfg, tmp_path / "state.json", tmp_path / "incidents")
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate ID should fail")


def test_example_configuration_matches_schema():
    root = Path(__file__).parents[1] / "tools" / "website-watchdog"
    schema = json.loads((root / "sites.schema.json").read_text())
    example = json.loads((root / "sites.example.json").read_text())
    jsonschema.validate(example, schema)


def test_private_networks_are_blocked_by_default(monkeypatch):
    monkeypatch.setattr(watchdog, "resolve_addresses", lambda host: {"127.0.0.1"})
    try:
        watchdog.validate_target_url("https://internal.example.test", False)
    except ValueError as exc:
        assert "disallowed" in str(exc)
    else:
        raise AssertionError("private target should fail")


def test_incident_requires_lease_owner_to_resolve(tmp_path, monkeypatch):
    path = tmp_path / "incident.json"
    payload = {
        "schema_version": 1, "status": "queued", "incident_id": "00000000-0000-4000-8000-000000000000",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        "site": {"id": "site", "name": "Site", "url": "https://example.test"}, "evidence": {},
    }
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(incident_tool, "probe", lambda site: result(False))
    leased = incident_tool.mutate(path, "lease", "worker-one")
    assert leased["status"] == "leased"
    try:
        incident_tool.mutate(path, "resolve", "worker-two", "wrong worker")
    except PermissionError:
        pass
    else:
        raise AssertionError("wrong worker should fail")
    monkeypatch.setattr(incident_tool, "probe", lambda site: result(True))
    resolved = incident_tool.mutate(path, "resolve", "worker-one", "verified recovery", lease_token=leased["lease_token"])
    assert resolved["status"] == "resolved"


def test_transport_pins_the_address_from_its_only_dns_lookup(monkeypatch):
    lookups = []

    def resolve(host):
        lookups.append(host)
        return {"93.184.216.34"}

    monkeypatch.setattr(watchdog, "resolve_addresses", resolve)
    handler = watchdog.PinnedHTTPHandler()
    captured = {}

    def do_open(factory, request):
        connection = factory(request.host, timeout=3)
        captured["ip"] = connection._validated_ip
        captured["host"] = connection.host
        return object()

    monkeypatch.setattr(handler, "do_open", do_open)
    handler.http_open(watchdog.urllib.request.Request("http://site.test/health"))
    assert lookups == ["site.test"]
    assert captured == {"ip": "93.184.216.34", "host": "site.test"}


def test_redirect_validates_and_pins_every_hop(monkeypatch):
    answers = iter([{"93.184.216.34"}, {"127.0.0.1"}])
    monkeypatch.setattr(watchdog, "resolve_addresses", lambda host: next(answers))
    handler = watchdog.SafeRedirect("site.test", ["site.test"], False)
    request = watchdog.urllib.request.Request("https://site.test/start")
    watchdog.validate_target_url(request.full_url, False)
    try:
        handler.redirect_request(request, None, 302, "Found", {}, "https://site.test/private")
    except ValueError as exc:
        assert "disallowed" in str(exc)
    else:
        raise AssertionError("redirect rebinding to private IP should fail")


def test_incident_lock_rejects_symlink_without_truncating_target(tmp_path):
    target = tmp_path / "target"
    target.write_text("do-not-truncate")
    lock = tmp_path / "incident.json.lock"
    lock.symlink_to(target)
    try:
        with watchdog.incident_lock(tmp_path / "incident.json"):
            pass
    except OSError:
        pass
    else:
        raise AssertionError("symlink lock should be rejected")
    assert target.read_text() == "do-not-truncate"


def test_collector_does_not_close_or_cancel_an_active_lease(tmp_path, monkeypatch):
    cfg = tmp_path / "sites.json"; config(cfg)
    state = tmp_path / "state.json"; incidents = tmp_path / "incidents"
    watchdog.run(cfg, state, incidents, probe_fn=sequence([result(False)]))
    watchdog.run(cfg, state, incidents, probe_fn=sequence([result(False)]))
    path = next(incidents.glob("*.json"))
    monkeypatch.setattr(incident_tool, "probe", lambda site: result(False))
    incident_tool.mutate(path, "lease", "worker")

    watchdog.run(cfg, state, incidents, probe_fn=sequence([result(True)]))
    assert json.loads(path.read_text())["status"] == "leased"

    cfg.write_text(json.dumps({"sites": []}))
    watchdog.run(cfg, state, incidents)
    assert json.loads(path.read_text())["status"] == "leased"


def test_https_pin_preserves_hostname_for_sni_and_cert_check(monkeypatch):
    wrapped = {}
    context = type("Context", (), {
        "verify_mode": watchdog.ssl.CERT_REQUIRED,
        "check_hostname": True,
        "wrap_socket": lambda self, sock, server_hostname: wrapped.update(host=server_hostname) or sock,
    })()
    connection = watchdog._PinnedHTTPSConnection("site.test", validated_ip="93.184.216.34", context=context)
    monkeypatch.setattr(watchdog.socket, "create_connection", lambda address, *args: wrapped.update(address=address) or object())
    connection.connect()
    assert wrapped == {"address": ("93.184.216.34", 443), "host": "site.test"}


def test_expired_lease_is_reprobed_then_released_to_new_worker(tmp_path, monkeypatch):
    path = tmp_path / "incident.json"
    payload = {
        "schema_version": 1, "status": "leased", "incident_id": "00000000-0000-4000-8000-000000000000",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        "lease_expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "worker_id": "old", "site": {"id": "site", "name": "Site", "url": "https://example.test"}, "evidence": {},
    }
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(incident_tool, "probe", lambda site: result(False))
    leased = incident_tool.mutate(path, "lease", "new")
    assert leased["status"] == "leased"
    assert leased["worker_id"] == "new"


def test_multiprocess_workers_cannot_both_lease_one_incident(tmp_path, monkeypatch):
    if "fork" not in multiprocessing.get_all_start_methods():
        return
    path = tmp_path / "incident.json"
    path.write_text(json.dumps({
        "schema_version": 1, "status": "queued", "incident_id": "00000000-0000-4000-8000-000000000000",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        "site": {"id": "site", "name": "Site", "url": "https://example.test"}, "evidence": {},
    }))
    monkeypatch.setattr(incident_tool, "probe", lambda site: result(False))
    context = multiprocessing.get_context("fork")
    start, output = context.Event(), context.Queue()
    workers = [context.Process(target=lease_in_process, args=(path, name, start, output)) for name in ("one", "two")]
    for worker in workers: worker.start()
    start.set()
    for worker in workers: worker.join(10)
    outcomes = sorted(output.get(timeout=2)[1] for _ in workers)
    assert outcomes == ["RuntimeError", "leased"]
    assert all(worker.exitcode == 0 for worker in workers)


def test_proxy_configuration_is_rejected_instead_of_bypassing_ssrf_controls():
    try:
        watchdog.validate_sites([{
            "id": "site", "name": "Site", "url": "https://site.test",
            "proxy_url": "http://proxy.corp:8080",
        }])
    except ValueError as exc:
        assert "proxy" in str(exc).lower()
    else:
        raise AssertionError("an unsupported proxy must not be silently ignored")


def test_deadman_reports_fresh_and_stale_collector_state(tmp_path):
    script = TOOL_DIR / "deadman.py"
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat()}))
    fresh = subprocess.run(
        [sys.executable, str(script), "--state", str(state), "--max-age-seconds", "60"],
        capture_output=True, text=True,
    )
    assert fresh.returncode == 0
    assert fresh.stdout == ""

    state.write_text(json.dumps({"checked_at": "2020-01-01T00:00:00+00:00"}))
    stale = subprocess.run(
        [sys.executable, str(script), "--state", str(state), "--max-age-seconds", "60"],
        capture_output=True, text=True,
    )
    assert stale.returncode == 2
    assert json.loads(stale.stdout)["kind"] == "watchdog_stale"
