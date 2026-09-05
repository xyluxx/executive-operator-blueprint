import importlib.util
import os
import stat
import json
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "preflight.py"
SPEC = importlib.util.spec_from_file_location("preflight", MODULE_PATH)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def test_version_parser_and_range():
    assert preflight.parse_version("Hermes Agent v0.21.0") == (0, 21, 0)
    assert preflight.parse_version("unavailable") is None
    assert preflight.version_in_range((0, 21, 0), ">=0.21.0,<0.22.0")
    assert not preflight.version_in_range((0, 22, 0), ">=0.21.0,<0.22.0")


def test_direct_preflight_inventory_covers_daily_use_contracts():
    assert {
        "skills/calendar-operations/SKILL.md",
        "templates/voice-profile.schema.json",
        "templates/daily-brief-routine.schema.json",
        "templates/daily-brief-routine.example.yaml",
        "templates/delivery-record.schema.json",
        "tools/operator-state/daily_use.py",
        "tools/task-reconciliation/reconcile.py",
        "tools/task-reconciliation/README.md",
    } <= set(preflight.REQUIRED)


def test_preflight_reports_operator_control_disabled_and_high_assurance_unconfigured():
    result = preflight.run(True, Path(__file__).parents[1] / "templates" / "install.answers.example.yaml")
    boundary = result["operator_control"]
    assert boundary["enabled"] is False
    assert result["operator_control"]["high_assurance_secret_boundary"] == "required-unconfigured"  # pragma: allowlist secret
    assert boundary["high_assurance_credential_boundary"] == "required-unconfigured"
    assert boundary["high_assurance_boundary"] == "required-unconfigured"
    assert boundary["generic_terminal_browser_coverage"] == "blocked"
    assert boundary["direct_kanban_transition_gate"] == "observer-only"
    assert result["capability_status_authority"] == "contracts/capability-status.yaml"
    assert result["capability_statuses"] == ["Native", "Blueprint", "Bundled", "Configured", "Verified", "Optional", "Planned", "Blocked"]


def test_hermes_identity_parses_semantic_version_and_upstream_build():
    identity = preflight.parse_hermes_identity(
        "Hermes Agent v0.21.0 (2026.8.31) · upstream b51c055a"
    )
    assert identity == {"version": (0, 21, 0), "upstream_build": "b51c055a"}


def test_build_mismatch_allows_inspection_but_blocks_mutation(monkeypatch):
    root = Path(__file__).parents[1]

    def command(name, args, timeout=60):
        if name == "hermes" and args == ["--version"]:
            return {
                "available": True,
                "path": "hermes",
                "exit_code": 0,
                "output": "Hermes Agent v0.21.0 · upstream deadbeef",
            }
        return {"available": True, "path": name, "exit_code": 0, "output": "ok"}

    monkeypatch.setattr(preflight, "command_info", command)
    monkeypatch.setattr(preflight, "writable_directory", lambda path, **kw: {"writable": True, "path": str(path)})
    result = preflight.run(False, root / "templates" / "install.answers.example.yaml")
    assert result["hermes_semantic_compatible"] is True
    assert result["hermes_build_validated"] is False
    assert result["read_only_inspection_allowed"] is True
    assert result["mutations_allowed"] is False
    assert any("upstream build" in item for item in result["blockers"])


def test_repository_only_skips_hermes_requirement(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "ROOT", Path(__file__).parents[1])
    monkeypatch.setattr(preflight, "writable_directory", lambda path, **kw: {"writable": True, "path": str(path)})
    result = preflight.run(True, Path(__file__).parents[1] / "templates" / "install.answers.example.yaml")
    assert result["state"] == "repository_ready"


def test_repository_only_never_probes_or_writes_runtime_paths(tmp_path, monkeypatch):
    root = Path(__file__).parents[1]
    home = tmp_path / "must-not-be-created"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(preflight, "ROOT", root)

    original = preflight.command_info
    def repository_command(name, args, timeout=60):
        assert name != "hermes"
        return original(name, args, timeout)

    monkeypatch.setattr(preflight, "command_info", repository_command)
    monkeypatch.setattr(
        preflight,
        "writable_directory",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("write probe called")),
    )
    result = preflight.run(True, root / "templates" / "install.answers.example.yaml")
    assert result["state"] == "repository_ready"
    assert not home.exists()
    assert result["paths"]["install_state"]["skipped"] is True


def test_incompatible_hermes_blocks_onboarding(monkeypatch):
    root = Path(__file__).parents[1]
    def command(name, args, timeout=60):
        if name == "hermes" and args == ["--version"]:
            return {"available": True, "path": "hermes", "exit_code": 0, "output": "Hermes Agent v0.20.0"}
        return {"available": True, "path": name, "exit_code": 0, "output": "ok"}
    monkeypatch.setattr(preflight, "command_info", command)
    monkeypatch.setattr(preflight, "writable_directory", lambda path, **kw: {"writable": True, "path": str(path)})
    result = preflight.run(False, root / "templates" / "install.answers.example.yaml")
    assert result["state"] == "dependency_blocked"
    assert any("compatible Hermes" in item for item in result["blockers"])


def test_private_writable_directory_reports_creation_without_writing(tmp_path):
    path = tmp_path / "install-state"
    result = preflight.writable_directory(path, private=True)
    assert result["writable"] is True
    assert result["would_create"] is True
    assert not path.exists()


def test_private_writable_directory_rejects_existing_shared_mode(tmp_path):
    path = tmp_path / "install-state"
    path.mkdir(mode=0o755)
    os.chmod(path, 0o755)
    result = preflight.writable_directory(path, private=True)
    assert result["writable"] is False
    assert "0700" in result["remediation"]
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o755


def test_preflight_blocks_semantically_fabricated_registry(tmp_path):
    registry = json.loads((Path(__file__).parents[1] / "templates" / "integration-registry.example.json").read_text())
    registry.update({"capability_status": "Verified", "enabled": True, "lifecycle": "active",
                     "credential_status": "tested", "health": "healthy"})
    registry["live_proof"] = {"tested_at": "2999-01-01T00:00:00Z"}
    path = tmp_path / "fabricated.json"
    path.write_text(json.dumps(registry))
    result = preflight.run(True, Path(__file__).parents[1] / "templates" / "install.answers.example.yaml", integration_registry=path)
    assert result["state"] == "dependency_blocked"
    assert result["integration_registry_errors"]
