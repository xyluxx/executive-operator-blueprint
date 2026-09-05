import copy
import importlib.util
import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_SPEC = importlib.util.spec_from_file_location(
    "validate_skill_authority", ROOT / "scripts" / "validate_skill_authority.py"
)
assert AUTHORITY_SPEC and AUTHORITY_SPEC.loader
SKILL_AUTHORITY = importlib.util.module_from_spec(AUTHORITY_SPEC)
AUTHORITY_SPEC.loader.exec_module(SKILL_AUTHORITY)
CORE_SKILLS = {
    "continuity",
    "integration-onboarding",
    "inbox-triage",
    "meeting-action-items",
    "document-action-items",
    "grounded-citations",
    "calendar-operations",
}
OPTIONAL_PACKS = {
    "operator-control",
    "executive-assistant",
    "documents-and-research",
    "artifact-storage",
    "secure-credentials",
    "crm",
    "marketing-and-seo",
    "composio-connectors",
    "google-sheets",
    "public-relations",
    "website-reliability",
    "infrastructure",
    "coding-specialists",
    "recruiting",
    "leadership-operations",
    "managed-agent-team",
    "travel",
    "finance-visibility",
    "design",
}


def load_skill(name: str) -> str:
    return (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_curated_core_contains_only_reviewed_executive_skills():
    actual = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
    assert actual == CORE_SKILLS
    assert not (ROOT / "skills" / "agency-foundation").exists()


def test_skill_evolution_authority_lists_core_and_requires_review_before_enablement():
    text = (ROOT / "docs" / "20-skills-and-self-evolution.md").read_text(encoding="utf-8")
    bundled = text.split("## Bundled skills", 1)[1].split("## Useful Hermes skills", 1)[0]
    listed = set(__import__("re").findall(r"`([a-z][a-z0-9-]+)`", bundled))
    assert listed == CORE_SKILLS
    learning = text.split("## Learning loop", 1)[1].split("## Provider neutral authoring", 1)[0]
    assert learning.index("Review privacy") < learning.index("Enable and verify")
    assert learning.index("Obtain approval") < learning.index("Enable and verify")


def test_every_core_skill_has_behavioral_contract_and_verification():
    for name in CORE_SKILLS:
        text = load_skill(name)
        assert "## Behavioral Tests" in text, name
        assert "## Verification" in text, name
        assert "Completion criterion:" in text, name
        assert "/home/" not in text and "C:\\Users\\" not in text, name


def test_core_skill_specific_behaviors():
    checks = {
        "continuity": ["resume", "duplicate", "save point"],
        "integration-onboarding": ["current tools", "authoritative documentation", "inspect", "install", "full-loop", "capture"],
        "inbox-triage": ["draft", "send", "approval", "thread"],
        "meeting-action-items": ["transcript", "owner", "decision", "citation"],
        "document-action-items": ["obligation", "deadline", "location", "citation"],
        "grounded-citations": ["claim", "source", "citation", "unsupported"],
        "calendar-operations": ["timezone", "conflict", "approval", "readback"],
    }
    for name, phrases in checks.items():
        lowered = load_skill(name).lower()
        for phrase in phrases:
            assert phrase in lowered, (name, phrase)


def test_optional_pack_catalog_matches_schema_and_required_domains():
    catalog = yaml.safe_load((ROOT / "optional-packs.yaml").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "templates" / "optional-packs.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(catalog, schema)
    assert set(catalog["packs"]) == OPTIONAL_PACKS
    capabilities = yaml.safe_load((ROOT / "capabilities.yaml").read_text(encoding="utf-8"))
    assert set(catalog["packs"]) == set(capabilities["capability_packs"]) - {"core-operator"}
    answers = yaml.safe_load((ROOT / "templates" / "install.answers.example.yaml").read_text(encoding="utf-8"))
    assert set(answers["capability_packs"]) == set(capabilities["capability_packs"])


def test_every_optional_pack_is_disabled_and_operationally_reviewable():
    catalog = yaml.safe_load((ROOT / "optional-packs.yaml").read_text(encoding="utf-8"))
    required = {
        "source", "trust", "license", "version_ref", "prerequisites",
        "permissions", "data_risk", "tests", "fallback", "disable_path",
    }
    for name, pack in catalog["packs"].items():
        assert pack["default_enabled"] is False, name
        assert required <= set(pack), name
        assert pack["tests"], name
        assert pack["disable_path"], name
        assert pack["source"]["kind"] in {"bundled", "official", "discovery-required"}, name
        if pack["source"]["kind"] == "bundled":
            assert (ROOT / pack["source"]["locator"] / "SKILL.md").is_file(), name
        else:
            assert pack["source"]["candidates"], name


def test_catalog_does_not_vendor_unreviewed_community_skills():
    catalog = yaml.safe_load((ROOT / "optional-packs.yaml").read_text(encoding="utf-8"))
    for name, pack in catalog["packs"].items():
        if pack["source"]["kind"] == "discovery-required":
            assert pack["source"]["locator"] is None, name
            assert pack["trust"] == "inspect-before-selection", name


def test_resolved_capability_record_is_schema_valid_and_fail_closed():
    schema = json.loads((ROOT / "templates" / "resolved-capability.schema.json").read_text(encoding="utf-8"))
    example = yaml.safe_load((ROOT / "templates" / "resolved-capability.example.yaml").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(example, schema, format_checker=jsonschema.FormatChecker())
    assert example["status"] == "blocked"
    assert example["selected_route"]["immutable_ref"] is None
    assert all(item["status"] != "passed" for item in example["tests"])


def test_verified_capability_requires_passing_tests_and_resolved_source():
    schema = json.loads((ROOT / "templates" / "resolved-capability.schema.json").read_text(encoding="utf-8"))
    base = yaml.safe_load((ROOT / "templates" / "resolved-capability.example.yaml").read_text(encoding="utf-8"))
    base["status"] = "verified"
    base["selected_route"].update(
        {
            "version": "1.2.3",
            "immutable_ref": "0123456789abcdef",
            "sha256": "a" * 64,
            "license": "MIT",
            "provenance": "reviewed source repository and signed release",
        }
    )
    for item in base["tests"]:
        item["status"] = "passed"
        item["evidence"] = "synthetic evidence"
    jsonschema.validate(base, schema, format_checker=jsonschema.FormatChecker())

    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for test_status in ("failed", "blocked"):
        invalid = json.loads(json.dumps(base))
        invalid["tests"][0]["status"] = test_status
        assert list(validator.iter_errors(invalid)), test_status

    for field in ("version", "immutable_ref", "sha256", "license"):
        invalid = json.loads(json.dumps(base))
        invalid["selected_route"][field] = None
        assert list(validator.iter_errors(invalid)), field

    invalid = json.loads(json.dumps(base))
    invalid["selected_route"]["provenance"] = "unresolved until source inspection"
    assert list(validator.iter_errors(invalid)), "unresolved provenance"

    invalid = json.loads(json.dumps(base))
    invalid["tests"][0]["evidence"] = None
    assert list(validator.iter_errors(invalid)), "missing verification evidence"

    for field in ("version", "immutable_ref", "license", "provenance"):
        invalid = json.loads(json.dumps(base))
        invalid["selected_route"][field] = " \t "
        assert list(validator.iter_errors(invalid)), f"blank {field}"

    invalid = json.loads(json.dumps(base))
    invalid["tests"][0]["evidence"] = " \t "
    assert list(validator.iter_errors(invalid)), "blank verification evidence"


def test_learned_skill_cannot_expand_authority_without_new_review():
    approved = yaml.safe_load((ROOT / "templates" / "resolved-capability.example.yaml").read_text(encoding="utf-8"))
    approved["status"] = "verified"
    approved["account_identity"] = "approved-account"
    approved["credential_reference"] = "vault:approved-reference"
    approved["selected_route"].update({
        "version": "1.0.0", "immutable_ref": "a" * 40, "sha256": "a" * 64,
        "license": "MIT", "provenance": "owner-reviewed immutable skill source",
    })
    for item in approved["tests"]:
        item.update(status="passed", evidence="reviewed synthetic evidence")
    candidate = copy.deepcopy(approved)
    candidate["selected_route"].update(version="1.1.0", immutable_ref="b" * 40, sha256="b" * 64)
    assert SKILL_AUTHORITY.authority_errors(approved, candidate) == []

    attacks = []
    expanded = copy.deepcopy(candidate)
    expanded["permissions"].append("send external messages")
    attacks.append(expanded)
    for field, value in (
        ("data_boundary", "all accounts"),
        ("approval_policy", "automatic external writes"),
        ("owner", "worker"),
        ("account_identity", "different-account"),
        ("credential_reference", "vault:different-reference"),
    ):
        changed = copy.deepcopy(candidate)
        changed[field] = value
        attacks.append(changed)
    changed_skill = copy.deepcopy(candidate)
    changed_skill["selected_route"]["locator"] = "different-skill"
    attacks.append(changed_skill)
    assert all(SKILL_AUTHORITY.authority_errors(approved, changed) for changed in attacks)

    newly_reviewed = copy.deepcopy(expanded)
    assert SKILL_AUTHORITY.authority_errors(newly_reviewed, expanded) == []


def test_foundation_is_not_loadable_and_policy_remains_in_soul():
    assert not (ROOT / "skills" / "agency-foundation").exists()
    soul = (ROOT / "SOUL.md").read_text(encoding="utf-8")
    for phrase in ("Source authority", "Consequential actions", "Done means", "Search installed"):
        assert phrase in soul


def test_continuity_uses_canonical_lifecycle_and_proportional_contracts():
    text = load_skill("continuity")
    assert "contracts/task-lifecycle.yaml" in text
    assert "templates/task-contract.schema.json" in text
    assert "Ephemeral" in text and "Compact" in text and "Full" in text
    assert "current, active, parked, waiting, held" not in text
