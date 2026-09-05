import copy
import json
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_schema():
    schema = json.loads((ROOT / "templates" / "task-contract.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def test_core_contract_schemas_use_stable_project_ids():
    expected = "https://raw.githubusercontent.com/xyluxx/executive-operator-blueprint/main/templates/"
    for name in ("task-contract.schema.json", "task-lifecycle.schema.json"):
        schema = json.loads((ROOT / "templates" / name).read_text())
        assert schema["$id"] == expected + name


def errors(instance):
    return list(jsonschema.Draft202012Validator(load_schema()).iter_errors(instance))


def test_ephemeral_answer_creates_no_durable_task():
    schema = load_schema()
    jsonschema.validate({
        "contract_version": "1.0",
        "contract_class": "ephemeral",
        "durable_task": False,
        "work_class": "disposable-answer",
        "consequences": {
            "external_write": False, "delegated": False, "dependency": False,
            "sensitive_data": False, "material_cost": False,
            "cancellation_risk": False, "long_lived_follow_up": False,
        },
    }, schema)
    with __import__("pytest").raises(jsonschema.ValidationError):
        jsonschema.validate({"contract_class": "ephemeral", "durable_task": True}, schema)


def test_ephemeral_is_closed_against_every_durable_or_consequential_field():
    base = {
        "contract_version": "1.0", "contract_class": "ephemeral",
        "durable_task": False, "work_class": "disposable-answer",
        "consequences": {
            "external_write": False, "delegated": False, "dependency": False,
            "sensitive_data": False, "material_cost": False,
            "cancellation_risk": False, "long_lived_follow_up": False,
        },
    }
    for field, value in {
        "risk_flags": [], "outcome": "durable", "owner": "operator",
        "next_action": "follow up", "artifact_or_source": "file",
        "resume_point": "later", "completion_check": "check",
        "target": "production", "authority": "none",
    }.items():
        invalid = copy.deepcopy(base)
        invalid[field] = value
        assert errors(invalid), field

    for flag in base["consequences"]:
        invalid = copy.deepcopy(base)
        invalid["consequences"][flag] = True
        assert errors(invalid), flag


def test_compact_reversible_task_example_is_valid():
    example = yaml.safe_load((ROOT / "templates" / "task-contract.compact.example.yaml").read_text())
    jsonschema.validate(example, load_schema())
    assert set(example) == {
        "contract_version", "contract_class", "durable_task", "work_class", "consequences", "risk_flags", "outcome",
        "owner", "next_action", "artifact_or_source", "resume_point", "completion_check"
    }


def test_consequential_or_delegated_work_requires_full_contract():
    compact = yaml.safe_load((ROOT / "templates" / "task-contract.compact.example.yaml").read_text())
    validator = jsonschema.Draft202012Validator(load_schema())
    for risk in ("external-write", "delegated", "dependency", "sensitive-data", "material-cost", "cancellation-risk", "long-lived-follow-up"):
        invalid = copy.deepcopy(compact)
        invalid["risk_flags"] = [risk]
        assert list(validator.iter_errors(invalid)), risk


def test_named_consequential_work_classes_reject_compact_contracts():
    compact = yaml.safe_load((ROOT / "templates" / "task-contract.compact.example.yaml").read_text())
    for work_class in (
        "message-send", "invitation", "deployment", "purchase", "access-change",
        "credential-change", "production-action", "bulk-write", "deletion",
        "delegated-work", "durable-schedule",
    ):
        invalid = copy.deepcopy(compact)
        invalid["work_class"] = work_class
        assert errors(invalid), work_class


def test_each_consequence_requires_full_even_when_risk_flags_are_empty():
    compact = yaml.safe_load((ROOT / "templates" / "task-contract.compact.example.yaml").read_text())
    for consequence in (
        "external_write", "delegated", "dependency", "sensitive_data",
        "material_cost", "cancellation_risk", "long_lived_follow_up",
    ):
        invalid = copy.deepcopy(compact)
        invalid["consequences"][consequence] = True
        invalid["risk_flags"] = []
        assert errors(invalid), consequence


def test_classification_and_consequences_are_required_and_cannot_be_falsified():
    compact = yaml.safe_load((ROOT / "templates" / "task-contract.compact.example.yaml").read_text())
    for field in ("work_class", "consequences"):
        invalid = copy.deepcopy(compact)
        del invalid[field]
        assert errors(invalid), field
    invalid = copy.deepcopy(compact)
    invalid["work_class"] = "message-send"
    invalid["consequences"]["external_write"] = False
    assert errors(invalid)


def test_mixed_contract_class_fields_are_rejected():
    compact = yaml.safe_load((ROOT / "templates" / "task-contract.compact.example.yaml").read_text())
    compact["target"] = "production"
    assert errors(compact)


def test_blank_or_empty_critical_full_values_are_rejected():
    full = yaml.safe_load((ROOT / "templates" / "task-contract.full.example.yaml").read_text())
    for field in (
        "outcome", "owner", "next_action", "artifact_or_source", "resume_point",
        "completion_check", "target", "scope", "requirement_version", "authority",
        "checkpoint", "recovery", "evidence_method", "reviewer", "return_contract",
    ):
        invalid = copy.deepcopy(full)
        invalid[field] = "   "
        assert errors(invalid), field
    for field in ("criteria", "limits"):
        invalid = copy.deepcopy(full)
        invalid[field] = [] if field == "criteria" else {}
        assert errors(invalid), field


def test_full_contract_example_has_every_critical_field():
    example = yaml.safe_load((ROOT / "templates" / "task-contract.full.example.yaml").read_text())
    jsonschema.validate(example, load_schema())
    for field in (
        "target", "scope", "exclusions", "requirement_version", "criteria", "authority",
        "dependencies", "limits", "checkpoint", "recovery", "evidence_method", "reviewer", "return_contract"
    ):
        assert field in example


def test_partial_task_stays_open_with_minimal_resume_information():
    lifecycle = yaml.safe_load((ROOT / "contracts" / "task-lifecycle.yaml").read_text())
    partial = lifecycle["mappings"]["partial"]
    assert partial["closes_task"] is False
    assert partial["requires"] == ["satisfied_criteria", "outstanding_criteria", "resume_point"]


def test_blocked_lifecycle_requires_owner_blocker_and_wake_condition():
    lifecycle = yaml.safe_load((ROOT / "contracts" / "task-lifecycle.yaml").read_text())
    assert lifecycle["mappings"]["blocked"]["requires"] == ["blocker", "owner", "wake_condition"]


def test_full_contract_requires_flags_to_exactly_match_consequence_booleans():
    full = yaml.safe_load((ROOT / "templates" / "task-contract.full.example.yaml").read_text())
    flag_for = {key: key.replace("_", "-") for key in full["consequences"]}
    for consequence, flag in flag_for.items():
        invalid = copy.deepcopy(full)
        invalid["consequences"][consequence] = not invalid["consequences"][consequence]
        assert errors(invalid), consequence
        invalid = copy.deepcopy(full)
        invalid["risk_flags"] = ([item for item in invalid["risk_flags"] if item != flag]
                                 if flag in invalid["risk_flags"] else invalid["risk_flags"] + [flag])
        assert errors(invalid), flag


def test_each_named_work_class_enforces_intrinsic_consequences():
    full = yaml.safe_load((ROOT / "templates" / "task-contract.full.example.yaml").read_text())
    required = {
        "internal-read-only": [], "reversible-internal": [], "message-send": ["external_write"],
        "invitation": ["external_write"], "deployment": ["external_write"],
        "purchase": ["external_write", "material_cost"], "access-change": ["external_write"],
        "credential-change": ["external_write", "sensitive_data"], "production-action": ["external_write"],
        "bulk-write": ["external_write"], "deletion": ["external_write", "cancellation_risk"],
        "delegated-work": ["delegated"], "durable-schedule": ["dependency", "long_lived_follow_up"],
    }
    flag_for = {key: key.replace("_", "-") for key in full["consequences"]}
    for work_class, required_true in required.items():
        candidate = copy.deepcopy(full)
        candidate["work_class"] = work_class
        candidate["consequences"] = {key: key in required_true for key in candidate["consequences"]}
        candidate["risk_flags"] = [flag_for[key] for key in required_true]
        assert not errors(candidate), work_class
        if required_true:
            candidate["consequences"][required_true[0]] = False
            candidate["risk_flags"].remove(flag_for[required_true[0]])
            assert errors(candidate), work_class
    contradiction = copy.deepcopy(full)
    contradiction["work_class"] = "internal-read-only"
    contradiction["consequences"]["external_write"] = True
    contradiction["risk_flags"] = ["external-write"]
    assert errors(contradiction)
