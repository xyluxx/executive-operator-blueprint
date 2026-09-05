import importlib.util
import hashlib
import json
import os
import stat
import tarfile
import subprocess
import sys
import shutil
from contextlib import contextmanager
from pathlib import Path

import jsonschema
import pytest
import yaml

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "install_blueprint.py"
SPEC = importlib.util.spec_from_file_location("install_blueprint", MODULE_PATH)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
ROOT = Path(__file__).parents[1]
REAL_SOURCE_IDENTITY = installer.source_identity


@pytest.fixture(autouse=True)
def clean_source_identity(monkeypatch):
    monkeypatch.setattr(installer, "source_identity", lambda: {
        "path": str(ROOT),
        "commit": "a" * 40,
        "clean": True,
        "distribution_tree_sha256": "b" * 64,
        "immutable": True,
        "recommended_reproducible_checkout": (
            "git clone --no-checkout https://example.test/repo.git executive-operator-blueprint && "
            "git -C executive-operator-blueprint checkout --detach " + "a" * 40
        ),
    })


def result(code=0, stdout="", stderr=""):
    return type("Result", (), {"returncode": code, "stdout": stdout, "stderr": stderr})()


def answers(tmp_path, mode="new-profile"):
    data = yaml.safe_load((ROOT / "templates" / "install.answers.example.yaml").read_text())
    data["profile_name"] = "test-agent"
    data["install_mode"] = mode
    path = tmp_path / "answers.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return installer.load_answers(path)


def compatible():
    return {"hermes_version": "Hermes Agent v0.21.0 · upstream b51c055a", "hermes_compatible": True, "hermes_build_validated": True, "python_supported": True, "missing": []}


def test_dependency_status_blocks_semantic_match_on_unvalidated_build(monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/bin/hermes")
    monkeypatch.setattr(installer, "hermes_version", lambda: "Hermes Agent v0.21.0 · upstream deadbeef")
    status = installer.dependency_status()
    assert status["hermes_semantic_compatible"] is True
    assert status["hermes_build_validated"] is False
    assert status["hermes_compatible"] is False
    assert any("upstream build b51c055a" in item for item in status["missing"])


@contextmanager
def unlocked(_name):
    yield


def good_distribution(_name):
    return ([{"check": "distribution", "passed": True}], ["SOUL.md"])


def kanban_commands():
    return [
        ["hermes", "kanban", "init"],
        ["hermes", "kanban", "boards", "list"],
        ["hermes", "kanban", "stats"],
    ]


def test_distribution_tree_digest_covers_owned_paths(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "distribution.yaml").write_text("name: test\ndistribution_owned: [distribution.yaml, SOUL.md]\n")
    (source / "SOUL.md").write_text("first\n")
    monkeypatch.setattr(installer, "ROOT", source)
    first = installer.source_tree_sha256()
    (source / "SOUL.md").write_text("second\n")
    second = installer.source_tree_sha256()
    assert len(first) == 64
    assert first != second


def test_source_identity_blocks_and_inventory_excludes_generated_cache_artifacts(tmp_path, monkeypatch):
    source = tmp_path / "source"
    remote = tmp_path / "remote.git"
    cache = source / "tools" / "sample" / "__pycache__"
    cache.mkdir(parents=True)
    (source / "distribution.yaml").write_text(
        "name: test\ndistribution_owned: [distribution.yaml, tools/]\n"
    )
    (source / "tools" / "sample" / "tool.py").write_text("value = 1\n")
    (source / ".gitignore").write_text("__pycache__/\n")
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=source, check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=source, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD:main"], cwd=source, check=True)
    (cache / "tool.cpython-311.pyc").write_bytes(b"generated")
    monkeypatch.setattr(installer, "ROOT", source)
    files = {path.relative_to(source).as_posix() for path in installer.distribution_source_files()}
    identity = REAL_SOURCE_IDENTITY()
    assert files == {"distribution.yaml", "tools/sample/tool.py"}
    assert identity["remote_commit_advertised"] is True
    assert identity["immutable"] is False
    assert identity["generated_cache_artifacts"] == ["tools/sample/__pycache__", "tools/sample/__pycache__/tool.cpython-311.pyc"]


def test_source_identity_requires_commit_advertised_by_remote(tmp_path, monkeypatch):
    source = tmp_path / "source"
    remote = tmp_path / "remote.git"
    source.mkdir()
    (source / "distribution.yaml").write_text(
        "name: test\ndistribution_owned: [distribution.yaml, SOUL.md]\n"
    )
    (source / "SOUL.md").write_text("first\n")
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=source, check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=source, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD:main"], cwd=source, check=True)
    (source / "SOUL.md").write_text("second\n")
    subprocess.run(["git", "commit", "-qam", "second"], cwd=source, check=True)
    monkeypatch.setattr(installer, "ROOT", source)
    unpublished = REAL_SOURCE_IDENTITY()
    assert unpublished["clean"] is True
    assert unpublished["remote_commit_advertised"] is False
    assert unpublished["immutable"] is False
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=source, check=True)
    published = REAL_SOURCE_IDENTITY()
    assert published["remote_commit_advertised"] is True
    assert published["immutable"] is True


def test_source_identity_rejects_file_mode_drift_hidden_by_git_config(tmp_path, monkeypatch):
    source = tmp_path / "source"
    remote = tmp_path / "remote.git"
    source.mkdir()
    (source / "distribution.yaml").write_text(
        "name: test\ndistribution_owned: [distribution.yaml, SOUL.md]\n"
    )
    soul = source / "SOUL.md"
    soul.write_text("operator\n")
    soul.chmod(0o644)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=source, check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=source, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD:main"], cwd=source, check=True)
    monkeypatch.setattr(installer, "ROOT", source)
    baseline = REAL_SOURCE_IDENTITY()
    subprocess.run(["git", "config", "core.filemode", "false"], cwd=source, check=True)
    soul.chmod(0o755)
    drifted = REAL_SOURCE_IDENTITY()
    assert drifted["clean"] is True
    assert drifted["remote_commit_advertised"] is True
    assert drifted["git_tree_matches"] is False
    assert drifted["immutable"] is False
    assert drifted["distribution_tree_sha256"] != baseline["distribution_tree_sha256"]


def test_non_posix_source_digest_uses_exact_git_tree_mode(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "distribution.yaml").write_text(
        "name: test\ndistribution_owned: [distribution.yaml, tool.py]\n"
    )
    tool = source / "tool.py"
    tool.write_text("print('ok')\n")
    monkeypatch.setattr(installer, "ROOT", source)
    monkeypatch.setattr(installer.os, "name", "nt")
    first = installer.source_tree_sha256({"distribution.yaml": "100644", "tool.py": "100755"})
    tool.chmod(0o644)
    second = installer.source_tree_sha256({"distribution.yaml": "100644", "tool.py": "100755"})
    assert first == second
    with pytest.raises(RuntimeError, match="mode is not reproducible"):
        installer.source_tree_sha256({"distribution.yaml": "100644"})


def test_plugin_files_participate_in_install_update_and_rollback_inventory():
    manifest = installer.load_manifest()
    assert "plugins/" in manifest["distribution_owned"]
    files = {path.relative_to(ROOT).as_posix() for path in installer.distribution_source_files()}
    assert "plugins/operator-control/plugin.yaml" in files
    assert "plugins/operator-control/policy.py" in files


def test_plan_is_read_only_and_uses_native_profile_install(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    output = installer.plan(answers(tmp_path))
    assert output["state"] == "planned"
    assert output["command"][0:3] == ["hermes", "profile", "install"]
    assert output["post_install_commands"] == kanban_commands()
    assert output["resolved_capability_packs"] == []
    assert "config.yaml permission hardening to 0600" in output["writes"]


def test_general_uninstall_is_not_exposed():
    with pytest.raises(SystemExit):
        installer.build_parser().parse_args(["uninstall"])


def test_apply_refuses_existing_new_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: True)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    output = installer.apply(answers(tmp_path), yes=True)
    assert output["state"] == "verification_blocked"
    assert output["created_by_this_run"] is False


def test_apply_refuses_dirty_or_unpinned_source(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "source_identity", lambda: {
        "path": str(ROOT), "commit": "a" * 40, "clean": False,
        "distribution_tree_sha256": "b" * 64, "immutable": False,
        "recommended_reproducible_checkout": None,
    })
    monkeypatch.setattr(installer, "run_command", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")))
    output = installer.apply(answers(tmp_path), yes=True)
    assert output["state"] == "verification_blocked"
    assert "clean committed checkout" in output["warnings"][0]


def test_apply_new_profile_records_identity(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "run_command", lambda args, timeout=300: calls.append(args) or result(0))
    monkeypatch.setattr(installer, "_distribution_checks", good_distribution)
    monkeypatch.setattr(installer, "_profile_fingerprint", lambda name: {"manifest_sha256": "abc"})
    monkeypatch.setattr(installer, "_write_install_marker", lambda name, run_id, fingerprint: tmp_path / "marker.json")
    output = installer.apply(answers(tmp_path), yes=True)
    assert output["state"] == "credential_blocked"
    assert output["created_by_this_run"] is True
    assert calls[0][0:3] == ["hermes", "profile", "install"]
    assert calls[1:] == [["hermes", "profile", "show", "test-agent"], *kanban_commands()]
    assert "native:hermes-kanban:default" in output["applied_assets"]


def test_existing_update_backs_up_and_is_noninteractive(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: True)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "_backup_profile", lambda name, run_id: {"path": "backup.zip", "sha256": "abc", "bytes": 1})
    monkeypatch.setattr(installer, "_profile_fingerprint", lambda name: {"manifest_sha256": "abc"})
    monkeypatch.setattr(installer, "_distribution_checks", good_distribution)
    monkeypatch.setattr(installer, "run_command", lambda args, timeout=300: calls.append(args) or result(0))
    output = installer.apply(answers(tmp_path, "update-profile"), yes=True)
    assert output["backup"]["path"] == "backup.zip"
    assert calls == [["hermes", "profile", "show", "test-agent"], ["hermes", "profile", "update", "test-agent", "--yes"], *kanban_commands()]


def test_kanban_initialization_failure_blocks_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "_distribution_checks", good_distribution)

    def run(args, timeout=300):
        if args == ["hermes", "kanban", "init"]:
            return result(1, stderr="kanban init failed")
        return result(0)

    monkeypatch.setattr(installer, "run_command", run)
    output = installer.apply(answers(tmp_path), yes=True)
    assert output["state"] == "verification_blocked"
    assert any(item["check"] == "kanban init" and not item["passed"] for item in output["verification"])


def test_profile_backup_uses_native_export_and_validates_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "hermes_home", lambda: tmp_path / "hermes")

    def export(command, timeout=300):
        assert command[0:4] == ["hermes", "profile", "export", "test-agent"]
        output = Path(command[command.index("--output") + 1])
        assert not output.exists()
        assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
        source = tmp_path / "source.txt"
        source.write_text("backup")
        with tarfile.open(output, "w:gz") as archive:
            archive.add(source, arcname="test-agent/source.txt")
        return result(0)

    monkeypatch.setattr(installer, "run_command", export)
    backup = installer._backup_profile("test-agent", "run-id")
    assert backup["path"].endswith(".tar.gz")
    assert backup["bytes"] > 0
    assert len(backup["sha256"]) == 64


def test_profile_backup_rejects_preexisting_symlink_without_export(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "hermes_home", lambda: tmp_path / "hermes")
    target = tmp_path / "private"
    target.write_text("do not overwrite")

    def export(command, timeout=300):
        output = Path(command[command.index("--output") + 1])
        output.symlink_to(target)
        return result(0)

    monkeypatch.setattr(installer, "run_command", export)
    try:
        installer._backup_profile("test-agent", "run-id")
    except RuntimeError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("backup should refuse a symlink collision")
    assert target.read_text() == "do not overwrite"


def test_profile_backup_rejects_export_replaced_with_hardlink(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "hermes_home", lambda: tmp_path / "hermes")
    other = tmp_path / "other.tar.gz"
    other.write_bytes(b"not an export")

    def export(command, timeout=300):
        output = Path(command[command.index("--output") + 1])
        os.link(other, output)
        return result(0)

    monkeypatch.setattr(installer, "run_command", export)
    try:
        installer._backup_profile("test-agent", "run-id")
    except RuntimeError as exc:
        assert "replaced" in str(exc) or "hard link" in str(exc)
    else:
        raise AssertionError("backup should refuse replacement or hard links")


def test_failed_new_profile_verification_is_removed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "_distribution_checks", lambda name: ([{"check": "distribution", "passed": False}], []))
    monkeypatch.setattr(installer, "_profile_is_pristine", lambda name, run_id=None: True)
    monkeypatch.setattr(installer, "run_command", lambda args, timeout=300: calls.append(args) or result(0))
    output = installer.apply(answers(tmp_path), yes=True)
    assert output["state"] == "failed"
    assert ["hermes", "profile", "delete", "test-agent", "--yes"] in calls


def test_failed_new_profile_verification_preserves_profile_with_runtime_data(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "_distribution_checks", lambda name: ([{"check": "distribution", "passed": False}], []))
    monkeypatch.setattr(installer, "_profile_is_pristine", lambda name, run_id=None: False)
    monkeypatch.setattr(installer, "run_command", lambda args, timeout=300: calls.append(args) or result(0))

    output = installer.apply(answers(tmp_path), yes=True)

    assert output["state"] == "verification_blocked"
    assert all(command[0:3] != ["hermes", "profile", "delete"] for command in calls)
    assert any("not pristine" in warning for warning in output["warnings"])


def test_pristine_profile_requires_distribution_manifest(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    root.mkdir()
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    assert installer._profile_is_pristine("test-agent") is False


def test_pristine_profile_allows_only_native_bootstrap_paths(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    root.mkdir()
    source_manifest = ROOT / "distribution.yaml"
    installed_manifest = yaml.safe_load(source_manifest.read_text())
    installed_manifest["name"] = "test-agent"
    installed_manifest["source"] = str(ROOT)
    installed_manifest["installed_at"] = "2026-01-01T00:00:00+00:00"
    (root / "distribution.yaml").write_text(yaml.safe_dump(installed_manifest, sort_keys=False))
    for name in (
        "memories", "sessions", "skins", "logs", "plans", "workspace", "cron", "home",
        "pairing", "audio_cache", "image_cache", "hooks",
    ):
        (root / name).mkdir()
    (root / "logs" / "agent.log").write_text("native bootstrap log\n")
    (root / "logs" / "errors.log").write_text("")
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    monkeypatch.setattr(installer, "load_manifest", lambda: yaml.safe_load(source_manifest.read_text()))

    assert installer._profile_is_pristine("test-agent") is True


def test_pristine_profile_rejects_runtime_data(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    root.mkdir()
    (root / "distribution.yaml").write_text("version: test\n")
    runtime = root / "sessions"
    runtime.mkdir()
    (runtime / "conversation.json").write_text("{}")
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    assert installer._profile_is_pristine("test-agent") is False


def test_pristine_profile_rejects_changed_distribution_owned_file(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    root.mkdir()
    (root / "distribution.yaml").write_text((ROOT / "distribution.yaml").read_text())
    (root / "SOUL.md").write_text("onboarding changed this distribution-owned file")
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    assert installer._profile_is_pristine("test-agent") is False


def test_failed_update_preserves_export_and_does_not_run_unsafe_restore(tmp_path, monkeypatch):
    calls = []
    backup = {"path": "backup.tar.gz", "sha256": "abc", "bytes": 1}
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: True)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "_backup_profile", lambda name, run_id: backup)
    monkeypatch.setattr(installer, "_distribution_checks", lambda name: ([{"check": "distribution", "passed": False}], []))
    monkeypatch.setattr(installer, "run_command", lambda args, timeout=300: calls.append(args) or result(0))

    output = installer.apply(answers(tmp_path, "update-profile"), yes=True)

    assert output["state"] == "verification_blocked"
    assert output["backup"] == backup
    assert output["rollback_point"] == "backup.tar.gz"
    assert calls == [["hermes", "profile", "show", "test-agent"], ["hermes", "profile", "update", "test-agent", "--yes"]]


def test_rollback_refuses_unowned_profile(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"profile": "test-agent", "created_by_this_run": False}))
    try:
        installer.rollback(answers(tmp_path), report, yes=True)
    except RuntimeError as exc:
        assert "creation evidence" in str(exc)
    else:
        raise AssertionError("rollback should refuse")


def test_rollback_refuses_profile_changed_by_onboarding(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    marker = root / "local" / "executive-operator-install.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"run_id": "run-id", "profile": "test-agent"}))
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "profile": "test-agent", "created_by_this_run": True, "run_id": "run-id",
        "profile_fingerprint": {"manifest_sha256": "abc"},
    }))
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    monkeypatch.setattr(installer, "_profile_fingerprint", lambda name: {"manifest_sha256": "abc"})
    monkeypatch.setattr(installer, "_profile_is_pristine", lambda name, run_id=None: False)
    monkeypatch.setattr(installer, "run_command", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not delete")))

    try:
        installer.rollback(answers(tmp_path), report, yes=True)
    except RuntimeError as exc:
        assert "not pristine" in str(exc)
    else:
        raise AssertionError("rollback should preserve a profile with user/runtime data")


def test_write_report_is_owner_only(tmp_path):
    path = tmp_path / "private" / "report.json"
    installer.write_report(path, {"state": "planned"})
    assert json.loads(path.read_text())["state"] == "planned"
    if hasattr(path.stat(), "st_mode"):
        assert oct(path.stat().st_mode & 0o777) == "0o600"
        assert oct(path.parent.stat().st_mode & 0o777) == "0o700"


def test_write_report_rejects_existing_shared_parent_without_chmod(tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o755)
    os.chmod(parent, 0o755)

    try:
        installer.write_report(parent / "report.json", {"state": "planned"})
    except PermissionError as exc:
        assert "private" in str(exc)
    else:
        raise AssertionError("shared report parent should be rejected")

    assert stat.S_IMODE(parent.stat().st_mode) == 0o755
    assert not (parent / "report.json").exists()


def test_normalized_report_matches_public_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "source_commit", lambda: "abc")
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    data = installer.normalized_report(installer.plan(answers(tmp_path)), answers(tmp_path))
    schema = json.loads((ROOT / "templates" / "install-report.schema.json").read_text())
    jsonschema.validate(data, schema)
    assert data["capability_status_authority"] == "contracts/capability-status.yaml"
    assert data["capability_statuses"] == ["Native", "Blueprint", "Bundled", "Configured", "Verified", "Optional", "Planned", "Blocked"]


def test_missing_hermes_is_dependency_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "dependency_status", lambda: {
        "hermes_version": "unavailable", "hermes_compatible": False,
        "python_supported": True, "missing": ["Hermes executable"],
    })
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    output = installer.plan(answers(tmp_path))
    assert output["state"] == "dependency_blocked"


def test_stale_lock_from_dead_process_is_recovered(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "hermes_home", lambda: tmp_path)
    lock_dir = tmp_path / "install-state"
    lock_dir.mkdir(mode=0o700)
    lock = lock_dir / "profile-test-agent.lock"
    lock.write_text(json.dumps({"pid": 99999999, "process_start": "missing", "created_at": installer.now()}))
    os.chmod(lock, 0o600)
    with installer.profile_lock("test-agent"):
        assert lock.exists()
    assert not lock.exists()


def test_live_lock_is_never_recovered(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "hermes_home", lambda: tmp_path)
    lock_dir = tmp_path / "install-state"
    lock_dir.mkdir(mode=0o700)
    lock = lock_dir / "profile-test-agent.lock"
    lock.write_text(json.dumps({"pid": os.getpid(), "process_start": installer.process_start(os.getpid()), "created_at": installer.now()}))
    os.chmod(lock, 0o600)
    try:
        with installer.profile_lock("test-agent"):
            pass
    except RuntimeError as exc:
        assert "already locked" in str(exc)
    else:
        raise AssertionError("live lock must not be recovered")


def test_audit_existing_profile_reports_source_and_preserved_state(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    (root / "sessions").mkdir(parents=True)
    (root / "sessions" / "one.jsonl").write_text("{}\n")
    (root / ".env").write_text("SECRET=not-reported\n")
    (root / "distribution.yaml").write_text("name: test-agent\nversion: 1.0.0\nsource: github.com/example/blueprint@abc123\n")
    monkeypatch.setattr(installer, "profile_exists", lambda name: True)
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    audit = installer.audit_profile("test-agent")
    assert audit["discovery"] == "existing-install"
    assert audit["recorded_source"] == "github.com/example/blueprint@abc123"
    assert "sessions" in audit["preserved_user_state"]
    assert ".env" in audit["preserved_user_state"]
    assert "not-reported" not in json.dumps(audit)


def test_distribution_checks_hash_every_owned_file(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "skills" / "x").mkdir(parents=True)
    (target / "skills" / "x").mkdir(parents=True)
    (source / "skills" / "x" / "SKILL.md").write_text("expected\n")
    (target / "skills" / "x" / "SKILL.md").write_text("changed\n")
    (target / "distribution.yaml").write_text("name: test-agent\nversion: 1.0.0\n")
    monkeypatch.setattr(installer, "ROOT", source)
    monkeypatch.setattr(installer, "profile_root", lambda name: target)
    monkeypatch.setattr(installer, "load_manifest", lambda: {"version": "1.0.0", "distribution_owned": ["skills/"]})
    monkeypatch.setattr(installer, "run_command", lambda *args, **kwargs: result(0, stdout="1.0.0"))
    checks, _ = installer._distribution_checks("test-agent")
    assert any(item["check"] == "skills/x/SKILL.md sha256" and not item["passed"] for item in checks)


def test_distribution_checks_map_env_template_to_native_example(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "profile"
    source.mkdir(); target.mkdir()
    (source / ".env.template").write_text("OPTIONAL_KEY=\n")
    (target / ".env.EXAMPLE").write_text("OPTIONAL_KEY=\n")
    monkeypatch.setattr(installer, "ROOT", source)
    monkeypatch.setattr(installer, "profile_root", lambda name: target)
    monkeypatch.setattr(installer, "load_manifest", lambda: {"version": "1.0.0", "distribution_owned": [".env.template"]})
    monkeypatch.setattr(installer, "run_command", lambda *args, **kwargs: result(0, stdout="1.0.0"))
    checks, installed = installer._distribution_checks("test-agent")
    assert installed == [".env.EXAMPLE"]
    assert all(item["passed"] for item in checks)
    assert any(item["check"] == ".env.EXAMPLE sha256" for item in checks)


def test_update_checks_preserved_config_against_preupdate_digest(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "profile"
    source.mkdir(); target.mkdir()
    (source / "config.yaml").write_text("source: true\n")
    (target / "config.yaml").write_text("private: true\n")
    os.chmod(target / "config.yaml", 0o600)
    preserved = hashlib.sha256((target / "config.yaml").read_bytes()).hexdigest()
    monkeypatch.setattr(installer, "ROOT", source)
    monkeypatch.setattr(installer, "profile_root", lambda name: target)
    monkeypatch.setattr(installer, "load_manifest", lambda: {"version": "1.0.0", "distribution_owned": ["config.yaml"]})
    monkeypatch.setattr(installer, "run_command", lambda *args, **kwargs: result(0, stdout="1.0.0"))

    fresh_checks, _ = installer._distribution_checks("test-agent")
    update_checks, _ = installer._distribution_checks("test-agent", {"config.yaml": preserved})

    assert any(item["check"] == "config.yaml sha256" and not item["passed"] for item in fresh_checks)
    assert any(item["check"] == "config.yaml preserved sha256" and item["passed"] for item in update_checks)


def test_standalone_verify_accepts_safe_owner_config_override_but_fresh_check_does_not(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "profile"
    source.mkdir(); target.mkdir()
    (source / "config.yaml").write_text("toolsets: []\n")
    (target / "config.yaml").write_text("toolsets: [hermes-cli]\n")
    os.chmod(target / "config.yaml", 0o600)
    monkeypatch.setattr(installer, "ROOT", source)
    monkeypatch.setattr(installer, "profile_root", lambda name: target)
    monkeypatch.setattr(installer, "load_manifest", lambda: {"version": "1.0.0", "distribution_owned": ["config.yaml"]})
    monkeypatch.setattr(installer, "run_command", lambda *args, **kwargs: result(0, stdout="1.0.0"))

    fresh_checks, _ = installer._distribution_checks("test-agent")
    verify_checks, _ = installer._distribution_checks("test-agent", owner_config_override=True)

    assert any(item["check"] == "config.yaml sha256" and not item["passed"] for item in fresh_checks)
    assert all(item["passed"] for item in verify_checks), verify_checks


def test_owner_config_override_rejects_symlink_hardlink_shared_mode_and_invalid_yaml(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "profile"
    source.mkdir(); target.mkdir()
    (source / "config.yaml").write_text("toolsets: []\n")
    monkeypatch.setattr(installer, "ROOT", source)
    monkeypatch.setattr(installer, "profile_root", lambda name: target)
    monkeypatch.setattr(installer, "load_manifest", lambda: {"version": "1.0.0", "distribution_owned": ["config.yaml"]})
    monkeypatch.setattr(installer, "run_command", lambda *args, **kwargs: result(0, stdout="1.0.0"))

    outside = tmp_path / "outside.yaml"
    outside.write_text("toolsets: []\n")
    cases = []
    config = target / "config.yaml"
    config.symlink_to(outside)
    cases.append(installer._distribution_checks("test-agent", owner_config_override=True)[0])
    config.unlink(); os.link(outside, config)
    cases.append(installer._distribution_checks("test-agent", owner_config_override=True)[0])
    config.unlink(); config.write_text("toolsets: []\n"); os.chmod(config, 0o666)
    cases.append(installer._distribution_checks("test-agent", owner_config_override=True)[0])
    os.chmod(config, 0o600); config.write_text("invalid: [\n")
    cases.append(installer._distribution_checks("test-agent", owner_config_override=True)[0])
    assert all(any(not item["passed"] for item in checks if item["check"].startswith("config.yaml")) for checks in cases)


def test_secure_config_digest_revalidates_opened_descriptor_metadata(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("toolsets: []\n")
    os.chmod(config, 0o600)
    real_fstat = installer.os.fstat

    def raced(fd):
        current = real_fstat(fd)
        return type("RacedStat", (), {
            "st_dev": current.st_dev, "st_ino": current.st_ino,
            "st_mode": current.st_mode, "st_nlink": 2, "st_uid": current.st_uid,
        })()

    monkeypatch.setattr(installer.os, "fstat", raced)
    with pytest.raises(PermissionError, match="opened descriptor"):
        installer._secure_config_digest(config, parse=True)


def test_config_hardening_changes_only_mode_and_verifies_descriptor(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("toolsets: []\n")
    os.chmod(config, 0o644)
    before = config.read_bytes()
    installer._harden_config_permissions(config)
    assert config.read_bytes() == before
    assert stat.S_IMODE(config.stat().st_mode) == 0o600


def test_fresh_config_hardening_failure_uses_pristine_rollback_path(tmp_path, monkeypatch):
    calls = []
    root = tmp_path / "profile"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("untouched")
    (root / "config.yaml").symlink_to(outside)
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: False)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    monkeypatch.setattr(installer, "_distribution_checks", lambda name: ([{"check": "distribution", "passed": False}], []))
    monkeypatch.setattr(installer, "_profile_is_pristine", lambda name, run_id=None: True)
    monkeypatch.setattr(installer, "run_command", lambda args, timeout=300: calls.append(args) or result(0))
    output = installer.apply(answers(tmp_path), yes=True)
    assert output["state"] == "failed"
    assert ["hermes", "profile", "delete", "test-agent", "--yes"] in calls
    assert outside.read_text() == "untouched"


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink", "wrong-owner"])
def test_existing_unsafe_config_blocks_update_with_backup_and_real_profile(tmp_path, monkeypatch, unsafe_kind):
    calls = []
    root = tmp_path / "profile"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("toolsets: []\n")
    config = root / "config.yaml"
    if unsafe_kind == "symlink":
        config.symlink_to(outside)
    elif unsafe_kind == "hardlink":
        os.link(outside, config)
    else:
        config.write_text("toolsets: []\n")
        os.chmod(config, 0o600)
        monkeypatch.setattr(installer.os, "geteuid", lambda: config.stat().st_uid + 1)
    backup = {"path": "backup.tar.gz", "sha256": "abc", "bytes": 1}
    monkeypatch.setattr(installer, "dependency_status", compatible)
    monkeypatch.setattr(installer, "profile_exists", lambda name: True)
    monkeypatch.setattr(installer, "profile_lock", unlocked)
    monkeypatch.setattr(installer, "profile_root", lambda name: root)
    monkeypatch.setattr(installer, "_backup_profile", lambda name, run_id: backup)
    monkeypatch.setattr(installer, "run_command", lambda args, timeout=300: calls.append(args) or result(0))
    output = installer.apply(answers(tmp_path, "update-profile"), yes=True)
    assert output["state"] == "verification_blocked"
    assert output["profile"] == "test-agent" and output["backup"] == backup
    assert output["created_by_this_run"] is False
    assert not any(command[:3] == ["hermes", "profile", "update"] for command in calls)


def test_native_populated_profile_update_and_fresh_verify_accept_owner_config(tmp_path):
    real_hermes = shutil.which("hermes")
    if not real_hermes:
        pytest.skip("Hermes is required for the native update regression")
    home = tmp_path / "hermes"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "hermes"
    shim.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then echo 'Hermes Agent v0.21.0 · upstream b51c055a'; exit 0; fi\n"
        f"exec {real_hermes} \"$@\"\n"
    )
    os.chmod(shim, 0o700)
    name = "populated-update"
    source = tmp_path / "distribution"
    remote = tmp_path / "distribution.git"
    shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "build", "dist"))
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=source, check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=source, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD:main"], cwd=source, check=True)
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1", "PATH": f"{shim_dir}:{os.environ.get('PATH', '')}"}
    answer_data = yaml.safe_load((source / "templates" / "install.answers.example.yaml").read_text())
    answer_data.update(profile_name=name, install_mode="new-profile", credential_gates=[])
    answer_path = tmp_path / "answers.yaml"
    answer_path.write_text(yaml.safe_dump(answer_data, sort_keys=False))
    fresh_report = tmp_path / "fresh.json"
    fresh = subprocess.run(
        [sys.executable, str(source / "scripts" / "install_blueprint.py"), "apply", "--answers", str(answer_path), "--report", str(fresh_report), "--yes"],
        env=env, capture_output=True, text=True, timeout=180,
    )
    assert fresh.returncode == 0, fresh.stdout + fresh.stderr + fresh_report.read_text()
    profile = home / "profiles" / name
    config = profile / "config.yaml"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    fresh_verify_report = tmp_path / "fresh-verify.json"
    fresh_verify = subprocess.run(
        [sys.executable, str(source / "scripts" / "install_blueprint.py"), "verify", "--answers", str(answer_path), "--report", str(fresh_verify_report)],
        env=env, capture_output=True, text=True, timeout=180,
    )
    assert fresh_verify.returncode == 0, fresh_verify.stdout + fresh_verify.stderr + fresh_verify_report.read_text()

    config.write_text(config.read_text() + "\n# private owner customization\n")
    (profile / "sessions").mkdir(exist_ok=True)
    (profile / "sessions" / "populated.jsonl").write_text("{}\n")
    before = hashlib.sha256(config.read_bytes()).hexdigest()
    answer_data["install_mode"] = "update-profile"
    answer_path.write_text(yaml.safe_dump(answer_data, sort_keys=False))
    apply_report = tmp_path / "apply.json"

    apply = subprocess.run(
        [sys.executable, str(source / "scripts" / "install_blueprint.py"), "apply", "--answers", str(answer_path), "--report", str(apply_report), "--yes"],
        env=env, capture_output=True, text=True, timeout=180,
    )
    assert apply.returncode == 0, apply.stdout + apply.stderr + apply_report.read_text()
    assert hashlib.sha256(config.read_bytes()).hexdigest() == before
    assert any(item["check"] == "config.yaml preserved sha256" and item["passed"] for item in json.loads(apply_report.read_text())["verification"])

    config.write_text(config.read_text() + "# later valid owner change\n")
    os.chmod(config, 0o600)
    verify_report = tmp_path / "verify.json"
    verify = subprocess.run(
        [sys.executable, str(source / "scripts" / "install_blueprint.py"), "verify", "--answers", str(answer_path), "--report", str(verify_report)],
        env=env, capture_output=True, text=True, timeout=180,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr + verify_report.read_text()
    verification = json.loads(verify_report.read_text())["verification"]
    assert any(item["check"] == "config.yaml owner override safety" and item["passed"] for item in verification)
    assert any(item["check"] == "config.yaml native check" and item["passed"] for item in verification)


@pytest.mark.parametrize("root_mcp", [False, True])
def test_native_profile_install_with_or_without_root_mcp_and_profile_readback(tmp_path, root_mcp):
    if not shutil.which("hermes"):
        return
    home = tmp_path / "hermes"
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    name = f"native-mcp-{'with' if root_mcp else 'without'}"
    source = tmp_path / "distribution"
    shutil.copytree(
        ROOT,
        source,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "build", "dist"),
    )
    if root_mcp:
        (source / "mcp.json").write_text("{}\n")
    else:
        assert not (source / "mcp.json").exists()
    install = subprocess.run(
        ["hermes", "profile", "install", str(source), "--name", name, "--yes"],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    show = subprocess.run(
        ["hermes", "profile", "show", name], env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert show.returncode == 0, show.stdout + show.stderr
    assert str(home / "profiles" / name) in show.stdout
    check = subprocess.run(
        ["hermes", "-p", name, "config", "check"], env=env,
        capture_output=True, text=True, timeout=120,
    )
    output = check.stdout + check.stderr
    assert check.returncode == 0, output
    assert "v0" not in output
    assert "migration" not in output.lower()
    prompt_size = subprocess.run(
        ["hermes", "-p", name, "prompt-size"], env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert prompt_size.returncode == 0, prompt_size.stdout + prompt_size.stderr
    profile = home / "profiles" / name
    assert (profile / ".env.EXAMPLE").is_file()
    assert not (profile / ".env.template").exists()
    assert (profile / ".no-bundled-skills").is_file()
    assert {path.name for path in (profile / "skills").iterdir() if path.is_dir()} == {
        "calendar-operations",
        "continuity",
        "document-action-items",
        "grounded-citations",
        "inbox-triage",
        "integration-onboarding",
        "meeting-action-items",
    }
    assert (profile / "optional-skills" / "credential-operator" / "SKILL.md").is_file()
