import importlib.util
import json
from pathlib import Path
import jsonschema
import pytest
ROOT=Path(__file__).parents[1]; MODULE_PATH=ROOT/"tools/operator-control/acceptance.py"
SCHEMAS=("criterion.schema.json","verification-result.schema.json","acceptance-record.schema.json","acceptance-policy.schema.json","rework-brief.schema.json")
def load_module():
 spec=importlib.util.spec_from_file_location("operator_acceptance_contract",MODULE_PATH); assert spec and spec.loader
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def test_all_five_schemas_are_valid_draft_2020_12():
 for name in SCHEMAS: jsonschema.Draft202012Validator.check_schema(json.loads((ROOT/"templates"/name).read_text()))
def test_canonical_digest_is_stable_and_excludes_claimed_digest():
 m=load_module(); a={"x":1}; first=m.canonical_digest(a); assert first==m.canonical_digest({"policy_digest":"forged","x":1}); assert first!=m.canonical_digest({"x":2})
def test_change_invalidation_is_scoped():
 m=load_module(); p={"criteria":[{"criterion_id":"a","affected_by":["artifact"]},{"criterion_id":"b","affected_by":["input"]}]}
 assert m.invalidated_criteria(p,{"artifact"})==["a"]
def test_legacy_caller_supplied_acceptance_api_fails_closed():
 m=load_module()
 with pytest.raises(RuntimeError,match="protected resolvers"):
  m.evaluate_acceptance({}, {}, {}, accepter_id="attacker")
