import importlib.util
import json
import shutil
import subprocess
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_blueprint", ROOT / "scripts" / "validate_blueprint.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_repository_contract_is_valid():
    result = MODULE.validate(ROOT)
    assert result["errors"] == []
    assert result["documents"] == 27
    assert result["skills"] == len(list((ROOT / "skills").glob("*/SKILL.md")))
    assert result["tools"] == len(list((ROOT / "tools").glob("*/README.md")))
    assert result["schemas"] == len(list(ROOT.rglob("*.schema.json")))


def test_distribution_and_capability_versions_match():
    result = MODULE.validate(ROOT)
    assert result["distribution_name"] == "executive-operator-blueprint"
    assert result["distribution_version"] == "1.1.0"
    assert result["capabilities_version"] == "1.1.0"
    assert result["private_runtime_paths_ignored"]


def test_public_copy_uses_release_naming_without_internal_generations():
    documents = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
    forbidden = (
        "V" + "2",
        "V" + "3",
        "v" + "2.0.0",
        "v" + "3.0.0",
        "2.0." + "x",
        "3.0." + "x",
    )
    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in forbidden), path


def test_privacy_scan_ignores_only_root_local_build_trees(tmp_path):
    local = tmp_path / ".venv" / "lib"
    local.mkdir(parents=True)
    (local / "artifact.pem").write_text("-----BEGIN " + "PRIVATE KEY-----\n")  # pragma: allowlist secret
    public = tmp_path / "docs" / "build"
    public.mkdir(parents=True)
    (public / "published.md").write_text("Authorization: Bearer " + "x" * 24 + "\n")  # pragma: allowlist secret
    errors, files = MODULE.scan_public_files(tmp_path)
    assert not any("artifact.pem" in item for item in errors)
    assert any("published.md" in item for item in errors)
    assert all(".venv" not in path.parts for path in files)


def test_release_cache_detection_ignores_cache_inside_local_artifacts(tmp_path):
    inside = tmp_path / ".venv" / "lib" / "__pycache__"
    outside = tmp_path / "scripts" / "__pycache__"
    inside.mkdir(parents=True)
    outside.mkdir(parents=True)
    assert MODULE.release_cache_directories(tmp_path, "__pycache__") == [outside]


def test_native_manifest_uses_only_fields_that_survive_native_install():
    manifest = yaml.safe_load((ROOT / "distribution.yaml").read_text())
    assert manifest["hermes_requires"] == ">=0.21.0"
    assert "tested_with_hermes" not in manifest
    capabilities = yaml.safe_load((ROOT / "capabilities.yaml").read_text())
    assert capabilities["reviewed_with_hermes"] == ">=0.21.0,<0.22.0"
    assert capabilities["reviewed_upstream_build"] == "b51c055a"


def test_root_readme_is_the_single_public_front_door():
    text = (ROOT / "README.md").read_text()
    assert text.startswith("# Executive Operator Blueprint for Hermes")
    assert '<picture>' in text
    assert 'assets/executive-operator-mobile.svg' in text
    assert 'assets/executive-operator.svg' in text
    assert "Max is the name of one private instance" in text
    assert not (ROOT / "max" / "README.md").exists()
    for phrase in (
        "What the repository is", "What is actually included", "Operating model",
        "Fresh profile — recommended", "Existing Hermes installation — audit first",
        "Capability discovery: configuration before invention", "One main operator",
    ):
        assert phrase in text


def test_responsive_brand_assets_are_outlined_and_self_contained():
    expected = {
        "executive-operator.svg": ("1600", "680"),
        "executive-operator-mobile.svg": ("760", "800"),
    }
    for name, dimensions in expected.items():
        root = ET.parse(ROOT / "assets" / name).getroot()
        assert (root.attrib["width"], root.attrib["height"]) == dimensions
        tags = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}
        assert {"title", "desc", "path"} <= tags
        assert not ({"script", "text", "image", "foreignObject", "linearGradient", "radialGradient"} & tags)
        assert all(not any(key.endswith("href") for key in element.attrib) for element in root.iter())


def test_human_and_ai_install_paths_exist():
    install = (ROOT / "INSTALL.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    onboarding = (ROOT / "ONBOARDING.md").read_text()
    assert "git clone --branch v1.1.0 --depth 1 https://github.com/xyluxx/executive-operator-blueprint.git" in install
    assert "hermes profile install . --name executive-operator --alias" in install
    assert "Required reading order" in agents
    assert "Start read-only" in (ROOT / "AI-INSTALL.md").read_text()
    assert "Never request a secret in chat" in onboarding
    assert "Single agent" in onboarding and "Managed team" in onboarding


def test_public_release_uses_consistent_v110_identity():
    distribution = yaml.safe_load((ROOT / "distribution.yaml").read_text(encoding="utf-8"))
    capabilities = yaml.safe_load((ROOT / "capabilities.yaml").read_text(encoding="utf-8"))
    packs = yaml.safe_load((ROOT / "optional-packs.yaml").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert distribution["version"] == capabilities["version"] == packs["version"] == "1.1.0"
    assert 'version = "1.1.0"' in pyproject
    clone = "git clone --branch v1.1.0 --depth 1 https://github.com/xyluxx/executive-operator-blueprint.git"
    for relative in ("README.md", "AI-INSTALL.md", "INSTALL.md", "docs/26-persistence-recipes.md"):
        assert clone in (ROOT / relative).read_text(encoding="utf-8"), relative
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 1.1.0" in changelog and "## 1.0.0" not in changelog
    assert "Initial public release" in changelog
    baseline = yaml.safe_load((ROOT / "contracts/public-release-policy.yaml").read_text(encoding="utf-8"))
    assert baseline["release"]["tag"] == "v1.1.0"
    assert baseline["refs"]["tags"] == {"allowed": ["v1.1.0"], "required": ["v1.1.0"]}
    assert baseline["refs"]["releases"] == {"allowed": ["v1.1.0"], "required": ["v1.1.0"]}
    release_doc = (ROOT / "docs/13-installation-and-conformance.md").read_text(encoding="utf-8")
    assert "single public `v1.1.0` release" in release_doc


def test_repository_map_rows_have_linked_paths_and_nonblank_purposes():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    table = readme.split("## Repository map", 1)[1].split("## License and provenance", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("|")]
    assert len(rows) > 2
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 2, row
        path_cell, purpose = cells
        assert path_cell and purpose, row
        assert path_cell.startswith("[") and "](" in path_cell and path_cell.endswith(")"), row

    assert "[AI-INSTALL.md](AI-INSTALL.md)" in table
    assert "[INSTALL.md](INSTALL.md)" in table


def test_capability_catalog_is_provider_neutral_and_honest():
    text = (ROOT / "CAPABILITIES.md").read_text()
    for phrase in (
        "Blueprint", "Native", "Bundled", "Configured", "Verified", "Optional", "Planned", "Blocked",
        "Mandatory capability-discovery loop",
        "Twenty CRM is the recommended open source reference", "Google Meet plugin",
        "Fathom", "DataForSEO", "Codex", "Claude Code", "YouTube",
    ):
        assert phrase in text
    assert "No external account is connected by this catalog" in text


def test_capability_matrix_uses_canonical_labels_and_complete_references():
    text = (ROOT / "docs" / "00-capability-matrix.md").read_text(encoding="utf-8")
    table = text.split("| Capability |", 1)[1].split("## Classification rule", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("|")][1:]
    canonical = {"Native", "Blueprint", "Bundled", "Configured", "Verified", "Optional", "Planned", "Blocked"}
    assert rows
    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 7, row
        assert cells[1] in canonical, row
        assert cells[6] and cells[6].startswith("[") and "](" in cells[6], row
    assert "| Memory | Native |" in table


def test_readme_reference_tool_count_matches_linked_tools():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "four inspectable reference tools" in readme
    reference_line = next(line for line in readme.splitlines() if line.startswith("Reference tool documentation:"))
    assert reference_line.count("tools/") == 8  # each of four tools appears in label and target


def test_machine_readable_catalog_selects_either_first_class_mode_by_need():
    catalog = yaml.safe_load((ROOT / "capabilities.yaml").read_text())
    assert catalog["recommended_mode"] == "workload-selected"
    assert catalog["modes"]["single-agent"]["status"] == "Bundled"
    assert catalog["modes"]["managed-team"]["status"] == "Bundled"
    assert "No mandatory single-operator trial" in catalog["modes"]["managed-team"]["selection_rule"]
    assert catalog["capability_packs"]["managed-agent-team"]["default_requested"] is False
    assert "tools/secure-credentials" in catalog["capability_packs"]["secure-credentials"]["included_paths"]
    assert catalog["capability_packs"]["artifact-storage"]["default_requested"] is False
    assert "microsoft-teams" not in catalog["channels"]["native_examples"]
    assert {"microsoft-teams", "irc"} <= set(catalog["channels"]["optional_plugin_examples"])
    assert catalog["capability_packs"]["composio-connectors"]["default_requested"] is False
    core = catalog["capability_packs"]["core-operator"]
    assert core["canonical_task_store"] == "hermes-kanban"
    assert core["unassigned_tasks_dispatch"] is False
    assert core["operator_state_role"] == "optional-migration-reference"


def test_fresh_profile_defaults_to_native_kanban_with_safe_manual_work():
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    assert config["toolsets"] == ["hermes-cli", "kanban"]
    assert config["kanban"]["auto_decompose"] is False
    assert config["kanban"]["auto_subscribe_on_create"] is False
    answers = yaml.safe_load((ROOT / "templates" / "install.answers.example.yaml").read_text())
    task_system = answers["task_system"]
    assert task_system["canonical_store"] == "hermes-kanban"
    assert task_system["manual_unassigned_tasks"] is True
    assert task_system["parked_mapping"] == "todo-with-checkpoint"


def test_install_answers_cannot_select_an_alternate_task_authority():
    schema = json.loads((ROOT / "templates" / "install.answers.schema.json").read_text())
    answers = yaml.safe_load((ROOT / "templates" / "install.answers.example.yaml").read_text())
    answers["task_system"]["canonical_store"] = "external"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(answers, schema)
    answers = yaml.safe_load((ROOT / "templates" / "install.answers.example.yaml").read_text())
    answers["task_system"]["parked_mapping"] = "external"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(answers, schema)
    for field, value in (("enabled", False), ("manual_unassigned_tasks", False), ("auto_decompose", True)):
        answers = yaml.safe_load((ROOT / "templates" / "install.answers.example.yaml").read_text())
        answers["task_system"][field] = value
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(answers, schema)


def test_task_truth_kanban_and_extension_skills_are_present():
    task_truth = (ROOT / "docs" / "23-task-truth-and-kanban.md").read_text()
    assert "updates it without being reminded" in task_truth
    assert "Kanban does not have a native `parked` status" in task_truth
    assert "verified meeting record" in task_truth
    assert "sole task lifecycle authority" in task_truth
    assert "Unassigned cards are manual work" in task_truth
    assert (ROOT / "optional-skills" / "artifact-storage-operator" / "SKILL.md").is_file()
    assert (ROOT / "optional-skills" / "composio-integration" / "SKILL.md").is_file()


def test_canonical_lifecycle_contract_preserves_native_hermes_statuses():
    contract = yaml.safe_load((ROOT / "contracts" / "task-lifecycle.yaml").read_text())
    schema = json.loads((ROOT / "templates" / "task-lifecycle.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(contract, schema)
    assert contract["native_statuses"] == [
        "triage", "todo", "ready", "running", "blocked", "scheduled", "review", "done", "archived"
    ]
    assert contract["human_states"] == ["active", "waiting", "blocked", "parked", "partial", "done"]
    assert contract["dispositions"] == ["cancelled", "superseded", "dropped", "exception-closed"]
    assert contract["verification_results"] == ["pass", "fail", "blocked", "inconclusive"]
    assert contract["external_effect_results"] == ["confirmed-success", "confirmed-failure", "unknown"]


def test_lifecycle_mapping_keeps_concepts_out_of_native_statuses():
    contract = yaml.safe_load((ROOT / "contracts" / "task-lifecycle.yaml").read_text())
    assert contract["mappings"]["parked"] == {"native_status": "todo", "requires": ["checkpoint"]}
    assert contract["mappings"]["partial"]["closes_task"] is False
    assert contract["mappings"]["partial"]["requires"] == ["satisfied_criteria", "outstanding_criteria", "resume_point"]
    assert contract["mappings"]["done"] == {"native_status": "done", "requires": ["acceptance"]}
    conceptual = set(contract["human_states"]) | set(contract["dispositions"]) | set(contract["verification_results"]) | set(contract["external_effect_results"])
    assert conceptual.isdisjoint(set(contract["native_statuses"]) - {"blocked", "done"})


def test_lifecycle_documentation_drift_fails_closed(tmp_path):
    lifecycle = ROOT / "contracts" / "task-lifecycle.yaml"
    bad = tmp_path / "bad.md"
    canonical = yaml.safe_load(lifecycle.read_text())
    categories = {name: canonical[name] for name in MODULE.LIFECYCLE_CATEGORIES}
    bad.write_text(
        MODULE.lifecycle_reference_block(categories) + "Work enters native status `paused`.\n",
        encoding="utf-8",
    )
    assert MODULE.lifecycle_drift_errors(lifecycle, [bad]) == [
        "unmapped native lifecycle term in bad.md: paused"
    ]


def test_lifecycle_references_fail_closed_for_every_vocabulary_category(tmp_path):
    lifecycle = ROOT / "contracts" / "task-lifecycle.yaml"
    categories = (
        "human_states", "native_statuses", "dispositions",
        "verification_results", "external_effect_results",
    )
    canonical = yaml.safe_load(lifecycle.read_text())
    for category in categories:
        bad = tmp_path / f"{category}.md"
        values = list(canonical[category]) + ["invented-term"]
        bad.write_text(MODULE.lifecycle_reference_block({category: values}), encoding="utf-8")
        assert any(category in error for error in MODULE.lifecycle_drift_errors(lifecycle, [bad]))


def test_lifecycle_reference_requires_authority_and_all_categories(tmp_path):
    lifecycle = ROOT / "contracts" / "task-lifecycle.yaml"
    bad = tmp_path / "bad.md"
    bad.write_text("No structured lifecycle reference.\n", encoding="utf-8")
    assert MODULE.lifecycle_drift_errors(lifecycle, [bad])


def test_native_kanban_unassigned_manual_edit_dispatch_and_focus_are_inert(tmp_path):
    home = tmp_path / "hermes-home"
    env = {**os.environ, "HERMES_HOME": str(home), "HOME": str(tmp_path)}
    env.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)
    env.pop("HERMES_KANBAN_TASK", None)

    def run(*args):
        result = subprocess.run(
            ["hermes", "kanban", *args], env=env, cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    run("init")
    created = json.loads(run("create", "Manual card", "--body", "before", "--json"))
    task_id = created["id"]
    before = json.loads(run("show", task_id, "--json"))
    run("comment", task_id, "manual edit")
    dispatch = json.loads(run("dispatch", "--json"))
    after_dispatch = json.loads(run("show", task_id, "--json"))
    (home / "focus.json").write_text(json.dumps({"task_id": "another-task"}))
    after_focus = json.loads(run("show", task_id, "--json"))

    assert before["task"]["assignee"] is None
    assert any(comment["body"] == "manual edit" for comment in after_dispatch["comments"])
    assert dispatch["spawned"] == []
    assert after_dispatch["task"]["status"] == before["task"]["status"]
    assert after_focus["task"]["status"] == before["task"]["status"]


def test_bundled_skill_descriptions_are_actionable_triggers():
    for path in (ROOT / "skills").glob("*/SKILL.md"):
        front = path.read_text().split("---\n", 2)[1]
        description = yaml.safe_load(front)["description"]
        assert description.startswith("Use when "), path
        assert len(description) <= 60, path


def test_registry_schema_and_example_never_store_secret_values():
    schema = json.loads((ROOT / "templates" / "integration-registry.schema.json").read_text())
    example = json.loads((ROOT / "templates" / "integration-registry.example.json").read_text())
    for key in ("api_key", "token", "password", "secret_value", "credential_value"):
        assert key not in schema["properties"]
        assert key not in example
    assert "credential_reference" in schema["properties"]
    assert example["credential_status"] == "missing"


def test_repository_validator_runs_integration_semantics(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    registry_path = root / "templates" / "integration-registry.example.json"
    registry = json.loads(registry_path.read_text())
    registry["candidate_review"]["permissions"] = ["unknown"]
    registry_path.write_text(json.dumps(registry))
    errors = MODULE.validate(root)["errors"]
    assert any("integration semantic validation" in error and "permissions" in error for error in errors)


def test_bundled_tools_are_documented():
    readme = (ROOT / "README.md").read_text()
    for path in ("operator-state", "secure-credentials", "website-watchdog", "task-reconciliation"):
        assert f"tools/{path}/" in readme
        assert (ROOT / "tools" / path / "README.md").is_file()


def test_public_bundle_contains_no_private_runtime_or_live_connection_state():
    tracked = set(MODULE.git(ROOT, "ls-files").stdout.splitlines())
    forbidden_names = {
        "auth.json", "connections.json", "credentials.json", "state.db",
        "memories", "sessions", "cron", "voice-profile.json",
    }
    assert not any(set(Path(name).parts) & forbidden_names for name in tracked)
    assert not (ROOT / "mcp.json").exists()
    mcp_example = json.loads((ROOT / "templates" / "mcp.example.json").read_text())
    assert mcp_example["mcp_servers"]
    assert all(not server["enabled"] for server in mcp_example["mcp_servers"].values())
    example = yaml.safe_load((ROOT / "templates" / "daily-brief-routine.example.yaml").read_text())
    assert example["schedule"]["enabled"] is False
    assert example["delivery"]["channel"] is None
    registry = json.loads((ROOT / "templates" / "integration-registry.example.json").read_text())
    assert registry["credential_status"] == "missing"
    assert registry.get("status") not in {"connected", "verified"}
    assert not any("voice-profile" in name and not name.startswith("templates/") for name in tracked)


def test_soul_enforces_continuity_truth_and_approval():
    soul = (ROOT / "SOUL.md").read_text()
    for phrase in (
        "The principal’s current correction",
        "Native Hermes Kanban is the sole task-lifecycle authority",
        "active`, `waiting`, `blocked`, `parked`, `partial`, and `done",
        "Ephemeral", "Compact", "Full",
        "Workers submit completed work for review",
        "Consequential actions require",
        "reviewed protected adapter",
        "There is no mandatory single-operator trial",
        "one receipt-backed acknowledgment",
        "Done means every requested criterion",
    ):
        assert phrase in soul
    assert "unless onboarding selects another verified system" not in soul
    assert "Active but parked" not in soul
    assert "Deliberate hold" not in soul


def test_agents_enforces_authority_compatibility_and_protected_boundaries():
    agents = (ROOT / "AGENTS.md").read_text()
    for phrase in (
        "contracts/authority-map.yaml",
        "contracts/task-lifecycle.yaml",
        "contracts/capability-status.yaml",
        ">=0.21.0,<0.22.0",
        "b51c055a",
        "Native Hermes Kanban is the sole task-lifecycle authority",
        "authenticated human or administrator path",
        "reviewed protected adapter",
        "templates/mcp.example.json",
        "execution-only",
    ):
        assert phrase in agents
    assert "when native Kanban is the selected canonical record" not in agents


def _privacy_errors(root: Path) -> list[str]:
    return MODULE.scan_public_files(root)[0]


def test_validator_scans_utf8_files_without_known_extensions(tmp_path):
    token = "gh" + "p_" + ("a" * 24)
    (tmp_path / "notes.custom").write_text(f"value={token}\n", encoding="utf-8")
    assert any("possible GitHub token in notes.custom" in error for error in _privacy_errors(tmp_path))


def test_validator_scans_filenames_for_private_paths(tmp_path):
    private_file = tmp_path / "Users" / "sample-person" / "notes.txt"
    private_file.parent.mkdir(parents=True)
    private_file.write_text("public fixture\n", encoding="utf-8")
    assert any("machine-specific Windows path in filename" in error for error in _privacy_errors(tmp_path))


def test_validator_finds_windows_paths_ipv6_and_key_headers(tmp_path):
    windows_path = "C:" + "\\" + "Users" + "\\" + "sample-person" + "\\" + "private.txt"
    ipv6 = "2001" + ":db8::1234"
    bearer = "Authorization: " + "Bearer " + ("z" * 32)  # pragma: allowlist secret
    (tmp_path / "privacy.data").write_text(
        f"{windows_path}\n{ipv6}\n{bearer}\n", encoding="utf-8"
    )
    errors = _privacy_errors(tmp_path)
    assert any("machine-specific Windows path in privacy.data" in error for error in errors)
    assert any("non-loopback IPv6 address in privacy.data" in error for error in errors)
    assert any("possible bearer token in privacy.data" in error for error in errors)


def test_validator_finds_encoded_private_markers(tmp_path):
    encoded_header = "LS0tLS1CRUdJTi" + "BQUklWQVRFIEtFWS0tLS0t"
    (tmp_path / "opaque").write_text(encoded_header + "\n", encoding="utf-8")
    assert any("possible encoded private key" in error for error in _privacy_errors(tmp_path))


def test_routine_release_does_not_require_single_commit(monkeypatch):
    def fake_git(root, *args):
        if args[:2] == ("status", "--porcelain"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ("ls-files", "-z"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ("rev-list", "--count", "HEAD"):
            return subprocess.CompletedProcess(args, 0, "7\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(MODULE, "git", fake_git)
    errors = MODULE.validate(ROOT, release=True)["errors"]
    assert "release history must contain exactly one commit" not in errors


def test_initial_release_requires_single_commit(monkeypatch):
    def fake_git(root, *args):
        if args[:2] == ("status", "--porcelain"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ("ls-files", "-z"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ("rev-list", "--count", "HEAD"):
            return subprocess.CompletedProcess(args, 0, "7\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(MODULE, "git", fake_git)
    errors = MODULE.validate(ROOT, initial_release=True)["errors"]
    assert "initial release history must contain exactly one commit" in errors


def test_ci_installs_and_audits_hashed_lock_and_runs_secret_scan():
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text()
    assert "pip install --require-hashes -r requirements-dev.lock" in workflow
    assert "pip-audit -r requirements-dev.lock" in workflow
    assert "detect-secrets-hook --baseline .secrets.baseline" in workflow
    lock = (ROOT / "requirements-dev.lock").read_text()
    assert "--hash=sha256:" in lock
    baseline = json.loads((ROOT / ".secrets.baseline").read_text())
    assert baseline["version"] == "1.5.0"
    assert all(
        finding.get("is_secret") is False
        for findings in baseline["results"].values()
        for finding in findings
    )
