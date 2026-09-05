import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "audit_public_release.py"
SPEC = importlib.util.spec_from_file_location("audit_public_release", MODULE_PATH)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "validate_blueprint_for_public_audit",
    ROOT / "scripts" / "validate_blueprint.py",
)
assert VALIDATOR_SPEC and VALIDATOR_SPEC.loader
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)

SHA = "1" * 40
CONTENT_SHA = "c" * 64
ARCHIVE_SHA = "a" * 64


def policy(**updates):
    value = {
        "schema_version": 2,
        "repository": {"owner": "xyluxx", "name": "executive-operator-blueprint", "visibility": "public", "default_branch": "main"},
        "refs": {"branches": {"allowed": ["main"], "required": ["main"]}, "tags": {"allowed": ["v1.1.0"], "required": ["v1.1.0"]}, "releases": {"allowed": ["v1.1.0"], "required": ["v1.1.0"]}},
        "release": {"tag": "v1.1.0", "commit_count": {"mode": "baseline", "expected": 1}, "content_digest": {"algorithm": "sha256-path-mode-content-v1", "excluded_paths": ["contracts/public-release-policy.yaml"], "sha256": CONTENT_SHA}, "checksum_asset": "executive-operator-blueprint-1.1.0.tar.gz.sha256", "checksum_entry": "executive-operator-blueprint-v1.1.0-source.tar.gz"},
        "identities": {"allowed_contributors": ["xyluxx"], "allowed_collaborators": ["xyluxx"], "allowed_git_identities": [{"name": "Xyluxx", "email": "contributor@example.test"}]},
        "public_surface": {"readme": "README.md", "assets": ["assets/executive-operator.svg"]},
    }
    for key, item in updates.items():
        value[key] = item
    return value


class FakeClient:
    authenticated = True

    def __init__(self, **updates):
        self.data = {
            "repository": {"owner": {"login": "xyluxx"}, "name": "executive-operator-blueprint", "visibility": "public", "default_branch": "main"},
            "branches": ["main"], "branch_heads": {"main": SHA}, "tags": {"v1.1.0": SHA},
            "releases": {"v1.1.0": {"tag_name": "v1.1.0", "target_commitish": "main", "assets": {"executive-operator-blueprint-1.1.0.tar.gz.sha256": f"{ARCHIVE_SHA}  executive-operator-blueprint-v1.1.0-source.tar.gz\n"}}},
            "commits": [{"sha": SHA, "author": {"name": "Xyluxx", "email": "contributor@example.test"}, "committer": {"name": "Xyluxx", "email": "contributor@example.test"}}],
            "contributors": ["xyluxx"], "collaborators": ["xyluxx"], "invitations": [], "teams": [], "deploy_keys": [],
            "clone": True, "content_digest": CONTENT_SHA, "archive": ARCHIVE_SHA, "readme": True, "assets": {"assets/executive-operator.svg": True},
        }
        self.data.update(updates)

    def collect(self, _policy):
        return self.data


def findings(report):
    return {item["id"]: item for item in report["checks"]}


def test_clean_baseline_passes_and_report_matches_schema():
    report = AUDIT.audit(policy(), FakeClient())
    assert report["result"] == "pass"
    schema = json.loads((ROOT / "templates" / "public-release-audit-report.schema.json").read_text())
    jsonschema.validate(report, schema)


def test_cached_or_unrelated_contributor_fails():
    report = AUDIT.audit(policy(), FakeClient(contributors=["xyluxx", "cached-user"]))
    assert findings(report)["contributors.allowlist"]["status"] == "fail"


def test_extra_collaborator_fails():
    report = AUDIT.audit(policy(), FakeClient(collaborators=["xyluxx", "other"]))
    assert findings(report)["collaborators.allowlist"]["status"] == "fail"


def test_missing_auth_is_unverified_not_pass():
    client = FakeClient()
    client.authenticated = False
    report = AUDIT.audit(policy(), client)
    for check in ("collaborators.allowlist", "access.invitations", "access.teams", "access.deploy_keys"):
        assert findings(report)[check]["status"] == "unverified"
    assert report["result"] == "unverified"


def test_extra_commit_fails_normal_future_release_policy():
    report = AUDIT.audit(policy(), FakeClient(commits=[FakeClient().data["commits"][0], {**FakeClient().data["commits"][0], "sha": "2" * 40}]))
    assert findings(report)["release.commit_count"]["status"] == "fail"


def test_wrong_author_fails():
    commit = FakeClient().data["commits"][0]
    commit = {**commit, "author": {"name": "Wrong", "email": "wrong@example.test"}}
    report = AUDIT.audit(policy(), FakeClient(commits=[commit]))
    assert findings(report)["commits.identities"]["status"] == "fail"


def test_moved_tag_and_checksum_fail():
    report = AUDIT.audit(policy(), FakeClient(tags={"v1.1.0": "2" * 40}, archive="b" * 64, content_digest="d" * 64))
    checks = findings(report)
    assert checks["release.immutable_tag"]["status"] == "fail"
    assert checks["release.content_digest"]["status"] == "fail"
    assert checks["release.checksum_asset"]["status"] == "fail"


def test_private_repository_fails():
    repo = dict(FakeClient().data["repository"], visibility="private")
    assert findings(AUDIT.audit(policy(), FakeClient(repository=repo)))["repository.identity"]["status"] == "fail"


def test_broken_archive_fails():
    assert findings(AUDIT.audit(policy(), FakeClient(archive=None)))["public.archive"]["status"] == "fail"


def test_report_redacts_tokens_and_private_paths():
    private_path = "/" + "home/private/auth.json"
    report = AUDIT.audit(policy(), FakeClient(error="token ghp_" + "x" * 30 + " at " + private_path))
    encoded = json.dumps(report)
    assert "ghp_" not in encoded and private_path.rsplit("/", 1)[0] not in encoded
    assert "[REDACTED]" in encoded


def test_repository_policy_preserves_current_tag_without_future_tag():
    actual = yaml.safe_load((ROOT / "contracts" / "public-release-policy.yaml").read_text())
    assert actual["refs"]["tags"]["required"] == ["v1.1.0"]
    assert actual["refs"]["tags"]["allowed"] == ["v1.1.0"]
    assert actual["release"]["commit_count"] == {"mode": "baseline", "expected": 1}


def test_content_digest_covers_path_mode_and_content_but_excludes_policy(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repository, check=True)
    (repository / "contracts").mkdir()
    policy_path = repository / "contracts" / "public-release-policy.yaml"
    policy_path.write_text("self: first\n")
    tracked = repository / "tool.py"
    tracked.write_text("print('first')\n")
    tracked.chmod(0o644)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=repository, check=True)
    first = AUDIT.git_content_digest(repository, "HEAD", ["contracts/public-release-policy.yaml"])
    policy_path.write_text("self: second\n")
    subprocess.run(["git", "commit", "-qam", "policy only"], cwd=repository, check=True)
    assert AUDIT.git_content_digest(repository, "HEAD", ["contracts/public-release-policy.yaml"]) == first
    tracked.chmod(0o755)
    subprocess.run(["git", "add", "tool.py"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "mode"], cwd=repository, check=True)
    assert AUDIT.git_content_digest(repository, "HEAD", ["contracts/public-release-policy.yaml"]) != first


def test_public_audit_hooks_are_explicit_and_normal_validation_stays_offline():
    validator = (ROOT / "scripts" / "validate_blueprint.py").read_text()
    preflight = (ROOT / "scripts" / "preflight.py").read_text()
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text()
    assert "--public-release-audit" in validator
    assert "--public-release-audit" in preflight
    assert "audit_public_release.py" not in workflow
    assert "public release audit" in (ROOT / "docs" / "13-installation-and-conformance.md").read_text().lower()


def test_validator_captures_public_audit_output_and_emits_one_json(monkeypatch, capsys):
    observed = {}

    def fake_run(*args, **kwargs):
        observed.update(kwargs)
        if not kwargs.get("capture_output"):
            print('{"result":"unverified"}')
        return subprocess.CompletedProcess(args[0], 2, stdout='{"result":"unverified"}\n', stderr="")

    monkeypatch.setattr(VALIDATOR.subprocess, "run", fake_run)
    monkeypatch.setattr(VALIDATOR, "validate", lambda *args, **kwargs: {"errors": []})
    monkeypatch.setattr(sys, "argv", ["validate_blueprint.py", "--public-release-audit"])

    assert VALIDATOR.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {"errors": ["public release audit did not pass"]}
    assert observed["capture_output"] is True
    assert observed["text"] is True
