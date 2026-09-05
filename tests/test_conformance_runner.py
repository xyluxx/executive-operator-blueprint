from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).parents[1]
MATRIX = ROOT / "contracts" / "executive-operator-conformance.json"
SCHEMA = ROOT / "templates" / "executive-operator-conformance.schema.json"
RUNNER = ROOT / "scripts" / "run_conformance.py"

EXPECTED_IDS = (
    {f"C{i:02d}" for i in range(1, 41)}
    | {
        "T15-RECONCILE", "T15-MANUAL-CARD", "T15-MEETING", "T15-RESTART",
        "T16-REGISTRY", "T16-FALSE-ALARM", "T16-CRASH-REPLAY", "T16-REPAIR", "T16-CREDENTIAL",
        "T17-FORMATS", "T17-PREVIEW", "T17-SHARE", "T17-STORAGE-LIFECYCLE",
        "T18-OFFICIAL-EVIDENCE", "T18-DISABLED", "T18-STATUS",
        "T19-CONTRIBUTOR", "T19-HERO", "T19-RELEASE", "PENDING-SOUL-AGENTS",
        "T16-FAST-CREDENTIAL", "T18-MODE-SELECTION", "T18-PROVIDER-NEUTRAL",
        "T19-CONTROLLED-EVOLUTION", "T19-PRODUCT-EXPERIENCE",
    }
)


def load():
    return json.loads(MATRIX.read_text()), json.loads(SCHEMA.read_text())


def test_matrix_schema_and_complete_unique_traceability():
    matrix, schema = load()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(matrix, schema)
    scenarios = matrix["scenarios"]
    ids = [item["id"] for item in scenarios]
    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_IDS
    for item in scenarios:
        assert (ROOT / item["authority"]).is_file(), item["id"]
        assert (ROOT / item["implementation_path"]).is_file(), item["id"]
        assert item["failure_path"].strip(), item["id"]
        assert item["evidence_test_node_ids"]
        assert len(item["evidence_test_node_ids"]) == len(set(item["evidence_test_node_ids"]))
        if item["required"]:
            assert item["expected_state"] == "reference-synthetic-pass"
        assert item["claim_scope"] != "live-provider"


def test_matrix_node_ids_are_exactly_collectable():
    matrix, _ = load()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    collected = {line.strip() for line in proc.stdout.splitlines() if "::" in line}
    for scenario in matrix["scenarios"]:
        for nodeid in scenario["evidence_test_node_ids"]:
            assert nodeid in collected, (scenario["id"], nodeid)


def test_json_runner_executes_required_scenarios_and_reports_evidence():
    proc = subprocess.run([sys.executable, str(RUNNER), "--json"], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["result"] == "PASS"
    assert report["claim_scope"] == "reference-synthetic"
    assert report["live_provider_claim"] is False
    assert report["summary"]["failed"] == 0
    assert report["summary"]["passed"] == 65
    assert report["summary"]["blocked"] == 0
    assert report["summary"]["missing_mapping"] == 0
    assert report["summary"]["duplicate_id"] == 0
    assert "::" not in report["diagnostics"]["collection"]
    assert "tests collected" in report["diagnostics"]["collection"]
    assert all(row["evidence_test_node_ids"] for row in report["scenarios"])
    protected = next(row for row in report["scenarios"] if row["id"] == "PENDING-SOUL-AGENTS")
    assert protected["state"] == "PASS"
    assert "reason" not in protected


def run_broken(tmp_path, matrix):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(matrix), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--json", "--matrix", str(path)],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert proc.returncode != 0
    return json.loads(proc.stdout)


@pytest.mark.parametrize("prefix", [
    "C", "T15-", "T16-", "T17-", "T18-", "T19-", "PENDING-",
    "T16-FAST-CREDENTIAL", "T18-MODE-SELECTION", "T18-PROVIDER-NEUTRAL",
    "T19-CONTROLLED-EVOLUTION", "T19-PRODUCT-EXPERIENCE",
])
def test_runner_rejects_removing_any_required_category(tmp_path, prefix):
    matrix, _ = load()
    matrix["scenarios"] = [row for row in matrix["scenarios"] if not row["id"].startswith(prefix)]
    report = run_broken(tmp_path, matrix)
    assert report["summary"]["missing_mapping"] > 0


@pytest.mark.parametrize("field,value", [
    ("authority", "contracts/not-real.yaml"),
    ("implementation_path", "tools/not-real.py"),
    ("failure_path", ""),
    ("evidence_test_node_ids", ["tests/test_not_real.py::test_not_real"]),
])
def test_runner_rejects_invalid_traceability_reference(tmp_path, field, value):
    matrix, _ = load()
    matrix["scenarios"][0][field] = value
    report = run_broken(tmp_path, matrix)
    assert report["summary"]["schema_errors"] + report["summary"]["missing_mapping"] > 0


def test_runner_rejects_missing_mapping_and_duplicate_id(tmp_path):
    matrix, _ = load()
    broken = dict(matrix)
    broken["scenarios"] = [dict(item) for item in matrix["scenarios"]]
    broken["scenarios"][0]["evidence_test_node_ids"] = []
    broken["scenarios"].append(dict(broken["scenarios"][1]))
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))
    proc = subprocess.run([sys.executable, str(RUNNER), "--json", "--matrix", str(path)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode != 0
    report = json.loads(proc.stdout)
    assert report["summary"]["missing_mapping"] >= 1
    assert report["summary"]["duplicate_id"] >= 1
