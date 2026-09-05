#!/usr/bin/env python3
"""Run the offline Executive Operator conformance matrix."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess  # nosec B404 - fixed argv invokes pytest without a shell
import sys
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "contracts" / "executive-operator-conformance.json"
SCHEMA = ROOT / "templates" / "executive-operator-conformance.schema.json"
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


def _collect_test_nodes() -> tuple[set[str], str]:
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = proc.stdout.strip()
    nodes = {line.strip() for line in output.splitlines() if "::" in line}
    summary = output.splitlines()[-1] if output else "test collection produced no output"
    return (nodes if proc.returncode == 0 else set()), summary


def _report(matrix: dict[str, Any], matrix_path: Path) -> tuple[dict[str, Any], int]:
    rows = matrix.get("scenarios", []) if isinstance(matrix, dict) else []
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    duplicates = {key for key, count in Counter(ids).items() if count > 1}
    missing = [row.get("id", "<missing-id>") for row in rows if not row.get("evidence_test_node_ids")]
    present_ids = set(ids)
    missing_required = sorted(EXPECTED_IDS - present_ids)
    unexpected_ids = sorted(str(value) for value in present_ids - EXPECTED_IDS)

    schema_errors: list[str] = []
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(matrix)
    except (OSError, ValueError, jsonschema.ValidationError) as exc:
        schema_errors.append(str(exc).splitlines()[0])

    bad_paths: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in ("authority", "implementation_path"):
            value = row.get(field)
            if not isinstance(value, str) or not (ROOT / value).is_file():
                bad_paths.append(f"{row.get('id', '<missing-id>')}:{field}")

    referenced_nodes = {node for row in rows if isinstance(row, dict) for node in row.get("evidence_test_node_ids", [])}
    collected_nodes, collection_detail = _collect_test_nodes()
    missing_nodes = sorted(referenced_nodes - collected_nodes)
    missing.extend(bad_paths)
    missing.extend(missing_nodes)

    required_nodes = sorted({node for row in rows if row.get("required") for node in row.get("evidence_test_node_ids", [])})
    pytest_ok = False
    pytest_detail = "not run because matrix validation failed"
    structural_failure = bool(duplicates or missing or missing_required or unexpected_ids or schema_errors)
    if not structural_failure and required_nodes:
        proc = subprocess.run(  # nosec B603 - schema-constrained node IDs, shell=False
            [sys.executable, "-m", "pytest", "-q", *required_nodes],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        pytest_ok = proc.returncode == 0
        pytest_detail = proc.stdout.strip()

    scenario_reports = []
    for row in rows:
        expected = row.get("expected_state")
        if not row.get("required"):
            state = "Blocked" if expected == "deployment-specific-blocked" else "Unverified"
        elif structural_failure:
            state = "FAIL"
        else:
            state = "PASS" if pytest_ok else "FAIL"
        scenario_reports.append({
            "id": row.get("id"),
            "state": state,
            "claim_scope": row.get("claim_scope"),
            "evidence_test_node_ids": row.get("evidence_test_node_ids", []),
            **({"reason": row["reason"]} if row.get("reason") else {}),
        })

    failed = sum(row["state"] == "FAIL" for row in scenario_reports)
    result = "PASS" if not structural_failure and pytest_ok and failed == 0 else "FAIL"
    report = {
        "schema_version": 1,
        "result": result,
        "claim_scope": "reference-synthetic",
        "live_provider_claim": False,
        "matrix": str(matrix_path),
        "summary": {
            "scenarios": len(rows),
            "required": sum(bool(row.get("required")) for row in rows),
            "passed": sum(row["state"] == "PASS" for row in scenario_reports),
            "blocked": sum(row["state"] == "Blocked" for row in scenario_reports),
            "unverified": sum(row["state"] == "Unverified" for row in scenario_reports),
            "failed": failed,
            "missing_mapping": len(missing) + len(missing_required) + len(unexpected_ids),
            "duplicate_id": len(duplicates),
            "schema_errors": len(schema_errors),
        },
        "diagnostics": {
            "duplicate_ids": sorted(str(value) for value in duplicates),
            "missing_mapping_ids": missing + missing_required + unexpected_ids,
            "unexpected_ids": unexpected_ids,
            "collection": collection_detail,
            "schema_errors": schema_errors,
            "pytest": pytest_detail,
        },
        "scenarios": scenario_reports,
    }
    return report, 0 if result == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit one JSON report")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    args = parser.parse_args()
    try:
        matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
        report, code = _report(matrix, args.matrix)
    except (OSError, ValueError) as exc:
        report = {"schema_version": 1, "result": "FAIL", "claim_scope": "reference-synthetic", "live_provider_claim": False, "summary": {"scenarios": 0, "required": 0, "passed": 0, "blocked": 0, "unverified": 0, "failed": 1, "missing_mapping": 1, "duplicate_id": 0, "schema_errors": 1}, "diagnostics": {"error": str(exc)}, "scenarios": []}
        code = 1
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"{report['result']}: {report['summary']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
