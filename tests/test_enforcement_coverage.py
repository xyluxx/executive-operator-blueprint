import json
from pathlib import Path

import jsonschema
import yaml

ROOT=Path(__file__).parents[1]


def test_enforcement_coverage_schema_and_contract_are_complete():
    schema=json.loads((ROOT/"templates/enforcement-coverage.schema.json").read_text())
    contract=yaml.safe_load((ROOT/"contracts/enforcement-coverage.yaml").read_text())
    jsonschema.Draft202012Validator.check_schema(schema); jsonschema.validate(contract,schema)
    required={"dependency-acceptance","cancellation","worker-fencing","duplicate-effect","uncertain-effect","budget-reservation","retirement"}
    entries={x["id"]:x for x in contract["guarantees"]}
    assert required <= entries.keys()
    for item in entries.values():
        assert item["owner"] and item["enforcement_point"] and item["tests"]
        if item["status"]=="verified":
            assert item["gate"]!="observer-only" and all((ROOT/t).is_file() for t in item["tests"])
    assert entries["direct-kanban-completion"]["status"]=="blocked"
    assert entries["native-parent-auto-promotion"]["status"]=="blocked"
    assert entries["unsupported-provider-atomic-fencing"]["status"]=="blocked"
    integrated={"dependency-acceptance","cancellation","worker-fencing","duplicate-effect","budget-reservation"}
    for guarantee in integrated:
        assert "tests/test_managed_adapter_integration.py" in entries[guarantee]["tests"]
