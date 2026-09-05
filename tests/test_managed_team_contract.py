import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "operator-control"


def load_managed():
    spec = importlib.util.spec_from_file_location("operator_control_managed_contract", PLUGIN / "managed.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_specialist_contract_requires_least_context_and_strong_boundaries():
    schema = json.loads((ROOT / "templates/specialist-contract.schema.json").read_text())
    valid = {
        "schema_version": 1, "specialist_id": "bot:research", "mode": "managed-team",
        "main_operator": "profile:main", "lane": "client-research", "profile": "research",
        "board": "/boards/client-a.db", "client": "client-a", "workspace": "/work/client-a",
        "credential_scope": ["credential:research-a"], "schedule_ids": ["cron:research-a"],
        "brief": {"version": 4, "requirement_version": 7, "included_context": ["task:t1", "artifact:a1"],
                  "excluded_context": ["operator-memory", "client-b"], "input_versions": {"artifact:a1": "sha256:abc"}},
        "permissions": ["web.read"], "protected_targets": ["client-a/report"],
        "budget": {"total": 100, "verification_reserve": 20}, "retirement_condition": "lane ends"
    }
    jsonschema.validate(valid, schema)
    invalid = dict(valid); invalid["brief"] = {"version": 4, "requirement_version": 7, "included_context": ["all-memory"], "excluded_context": [], "input_versions": {}}
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(invalid, schema)


def test_retirement_contract_requires_disable_revoke_transfer_preserve_and_resume():
    schema = json.loads((ROOT / "templates/specialist-retirement.schema.json").read_text())
    valid = {"schema_version": 1, "specialist_id": "bot:r", "main_operator": "profile:main",
             "effective_at": "2026-09-05T12:00:00Z", "schedule_ids": ["cron:r"],
             "credential_references": ["credential:r"], "task_ids": ["t1"], "evidence_references": ["attachment:e1"],
             "actions": {"disable_schedules": True, "revoke_credentials": True, "transfer_ownership": True,
                         "preserve_evidence": True, "main_operator_resume_test": True}}
    jsonschema.validate(valid, schema)
    valid["actions"]["revoke_credentials"] = False
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(valid, schema)


def test_mode_selection_has_no_mandatory_single_operator_trial():
    managed = load_managed()
    decision = managed.select_mode({"recurring_independent_lanes": True})
    assert decision.mode == "managed-team"
    assert "trial" not in decision.prerequisites
    assert managed.select_mode({"mixed_work": True}).mode == "single-operator"
