import importlib.util
import json
import shutil
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_blueprint", ROOT / "scripts" / "validate_blueprint.py")
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def test_authority_map_is_schema_valid_and_names_one_home_per_concept():
    contract = yaml.safe_load((ROOT / "contracts" / "authority-map.yaml").read_text())
    schema = json.loads((ROOT / "templates" / "authority-map.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(contract, schema)
    homes = [entry["normative_home"] for entry in contract["authorities"]]
    concepts = [entry["concept"] for entry in contract["authorities"]]
    assert len(concepts) == len(set(concepts))
    assert all((ROOT / home).is_file() for home in homes)
    status_authority = next(item for item in contract["authorities"] if item["concept"] == "capability-status-taxonomy")
    assert status_authority["normative_home"] == "contracts/capability-status.yaml"
    assert {
        "website-reliability", "secure-credential-delivery", "storage-and-preview-adapters",
        "operating-mode-selection", "controlled-skill-evolution", "provider-neutrality",
        "professional-executive-operator-experience",
    } <= set(concepts)


def test_compatibility_contract_records_range_build_and_mismatch_policy():
    contract = yaml.safe_load((ROOT / "contracts" / "authority-map.yaml").read_text())
    compatibility = contract["compatibility"]
    assert compatibility["semantic_range"] == ">=0.21.0,<0.22.0"
    assert compatibility["tested_upstream_build"] == "b51c055a"
    assert compatibility["mismatch_policy"] == {
        "read_only_inspection": "allowed",
        "install": "blocked_until_revalidated",
        "update": "blocked_until_revalidated",
        "verified_claims": "blocked_until_revalidated",
    }


def test_update_documentation_matches_owner_mutable_config_verification():
    text = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
    for phrase in (
        "owner-mutable", "preserved by default", "pre-update and post-update content",
        "other distribution-owned files", "safe regular file", "native config check",
        "permission hardening to `0600`", "approved plan",
    ):
        assert phrase in text


def test_mcp_json_is_not_required_or_distribution_owned():
    manifest = yaml.safe_load((ROOT / "distribution.yaml").read_text())
    assert "mcp.json" not in manifest["distribution_owned"]
    assert not (ROOT / "mcp.json").exists()
    example = json.loads((ROOT / "templates" / "mcp.example.json").read_text())
    assert example["mcp_servers"]
    assert all(server["enabled"] is False for server in example["mcp_servers"].values())


def test_every_schema_has_declared_test_coverage():
    contract = yaml.safe_load((ROOT / "contracts" / "authority-map.yaml").read_text())
    coverage = contract["schema_test_coverage"]
    schemas = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.schema.json")
        if ".git" not in path.parts
    }
    assert set(coverage) == schemas
    assert all(coverage[schema] for schema in schemas)
    assert all((ROOT / test).is_file() for tests in coverage.values() for test in tests)
    for relative in schemas:
        schema = json.loads((ROOT / relative).read_text())
        assert schema["$id"] == "https://raw.githubusercontent.com/xyluxx/executive-operator-blueprint/main/" + relative


def test_drift_checks_reject_each_required_class(tmp_path):
    fixture = tmp_path / "repo"
    shutil.copytree(ROOT, fixture, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    assert VALIDATOR.documentation_drift_errors(fixture) == []

    cases = {
        "task vocabulary": ("docs/23-task-truth-and-kanban.md", "`triage`", "`invented-state`"),
        "manifest claim": ("distribution.yaml", "  - README.md\n", "  - missing-bundle.md\n"),
        "capability proof": ("capabilities.yaml", "blueprint_status: Bundled", "blueprint_status: Verified"),
        "schema coverage": ("contracts/authority-map.yaml", "  templates/capabilities.schema.json:\n  - tests/test_blueprint.py\n", "  templates/not-covered.schema.json:\n  - tests/test_blueprint.py\n"),
        "broken link": ("README.md", "[Install](INSTALL.md)", "[Install](missing.md)"),
        "internal-generation label": ("README.md", "# Executive", "# V3 Executive"),
        "build mismatch": ("capabilities.yaml", 'reviewed_upstream_build: "b51c055a"', 'reviewed_upstream_build: "deadbeef"'),
        "capability status reference": ("README.md", '"Blocked"]} -->', '"Blocked","Ready"]} -->'),
        "capability matrix label": ("docs/00-capability-matrix.md", "| Remote Desktop | Optional |", "| Remote Desktop | Optional setup |"),
        "capability matrix official reference": ("docs/00-capability-matrix.md", "| [Desktop remote backend](https://hermes-agent.nousresearch.com/docs/user-guide/desktop#connecting-to-a-remote-backend) |", "|  |"),
    }
    for label, (relative, old, new) in cases.items():
        path = fixture / relative
        original = path.read_text()
        assert old in original, label
        path.write_text(original.replace(old, new, 1))
        errors = VALIDATOR.documentation_drift_errors(fixture)
        assert any(label in error for error in errors), (label, errors)
        path.write_text(original)

    empty_claim = fixture / "empty-config.yaml"
    empty_claim.write_text("status: configured\nservers: {}\n")
    assert any("empty config claim" in error for error in VALIDATOR.documentation_drift_errors(fixture))


def test_duplicate_local_documentation_links_are_reported(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("[one](guide.md) and [one](guide.md)\n")
    (tmp_path / "guide.md").write_text("ok\n")
    errors = VALIDATOR.documentation_link_errors(tmp_path, [path])
    assert any("duplicate documentation link" in error for error in errors)


def test_lifecycle_drift_rejects_declared_prose_terms_and_competing_mappings(tmp_path):
    contract_path = ROOT / "contracts" / "task-lifecycle.yaml"
    contract = yaml.safe_load(contract_path.read_text())
    reference = VALIDATOR.lifecycle_reference_block(
        {key: contract[key] for key in VALIDATOR.LIFECYCLE_CATEGORIES}, mappings=contract["mappings"])
    path = tmp_path / "consumer.md"
    for prose in ("Work is now `paused`.", "Human lifecycle state `held`.",
                  "Set status to `paused`.", "Statuses: active, waiting, held, done.",
                  "Mappings: waiting -> `todo`."):
        path.write_text(reference + prose + "\n")
        assert VALIDATOR.lifecycle_drift_errors(contract_path, [path]), prose


def test_lifecycle_drift_does_not_flag_ordinary_status_prose(tmp_path):
    contract_path = ROOT / "contracts" / "task-lifecycle.yaml"
    contract = yaml.safe_load(contract_path.read_text())
    path = tmp_path / "consumer.md"
    path.write_text(VALIDATOR.lifecycle_reference_block(
        {key: contract[key] for key in VALIDATOR.LIFECYCLE_CATEGORIES}, mappings=contract["mappings"]
    ) + "The deployment status page is paused during maintenance.\n")
    assert VALIDATOR.lifecycle_drift_errors(contract_path, [path]) == []


def test_alternate_task_authority_drift_rejects_prior_skill_architecture_wording(tmp_path):
    fixture = tmp_path / "repo"
    shutil.copytree(ROOT, fixture, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    path = fixture / "SKILL-ARCHITECTURE.md"
    current = (
        "An optional CRM adapter may write relationship activity to the selected CRM as a derived/reference "
        "integration or import CRM tasks as migration inputs, but native Hermes Kanban remains the sole "
        "task-lifecycle authority."
    )
    forbidden = (
        "An optional CRM adapter may write relationship activity to the selected CRM, but task ownership "
        "remains with the canonical task system unless onboarding explicitly selects that CRM as the one "
        "canonical task record."
    )
    source = path.read_text()
    assert current in source
    path.write_text(source.replace(current, forbidden, 1))

    errors = VALIDATOR.documentation_drift_errors(fixture)

    assert any("alternate task authority" in error and "SKILL-ARCHITECTURE.md" in error for error in errors), errors


def test_alternate_task_authority_drift_ignores_discussion_and_explicit_negation(tmp_path):
    path = tmp_path / "consumer.md"
    path.write_text(
        "Which CRM contains the project records?\n"
        "An external task system is not the canonical task record.\n"
        "Existing CRMs are never alternate lifecycle authorities.\n"
        "External project systems may only be migration inputs or derived/reference integrations.\n"
    )
    assert VALIDATOR.alternate_task_authority_errors(tmp_path, [path]) == []


def test_build_drift_checks_every_public_and_runtime_consumer(tmp_path):
    consumers = {
        "README.md": "b51c055a", "AI-INSTALL.md": "b51c055a",
        "docs/13-installation-and-conformance.md": "b51c055a",
        "scripts/preflight.py": "tested_upstream_build",
        "scripts/install_blueprint.py": "tested_upstream_build",
        "templates/install-report.schema.json": "b51c055a",
        "templates/install-report.template.md": "b51c055a", "capabilities.yaml": "b51c055a",
    }
    for index, (relative, token) in enumerate(consumers.items()):
        fixture = tmp_path / str(index)
        shutil.copytree(ROOT, fixture, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
        path = fixture / relative
        assert token in path.read_text(), relative
        path.write_text(path.read_text().replace(token, "deadbeef", 1))
        assert any("build mismatch" in error for error in VALIDATOR.documentation_drift_errors(fixture)), relative


def test_duplicate_local_documentation_links_across_lines_are_reported(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("[one](guide.md)\n\n[one](guide.md)\n")
    (tmp_path / "guide.md").write_text("ok\n")
    assert any("duplicate documentation link" in error for error in VALIDATOR.documentation_link_errors(tmp_path, [path]))


def test_any_internal_v2_or_later_generation_label_is_rejected(tmp_path):
    fixture = tmp_path / "repo"
    shutil.copytree(ROOT, fixture, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    readme = fixture / "README.md"
    readme.write_text(readme.read_text().replace("# Executive", "# V12 Executive", 1))
    assert any("internal-generation label" in error for error in VALIDATOR.documentation_drift_errors(fixture))
