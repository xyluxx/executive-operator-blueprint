#!/usr/bin/env python3
"""Fail closed when a learned skill exceeds its approved authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "templates" / "resolved-capability.schema.json"


def load_record(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("resolved capability must be a mapping")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(value, schema, format_checker=jsonschema.FormatChecker())
    return value


def authority_errors(approved: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    """Compare a candidate skill with an owner-approved resolution record."""
    errors: list[str] = []
    if approved.get("status") not in {"configured", "verified"}:
        errors.append("approved authority record is not active")

    approved_route = approved.get("selected_route") or {}
    candidate_route = candidate.get("selected_route") or {}
    if approved_route.get("kind") != "skill" or candidate_route.get("kind") != "skill":
        errors.append("skill authority gate accepts skill routes only")

    for field in ("capability_id", "owner", "account_identity", "credential_reference"):
        if candidate.get(field) != approved.get(field):
            errors.append(f"candidate changes protected {field}")

    if candidate_route.get("locator") != approved_route.get("locator"):
        errors.append("candidate changes the approved skill identity")

    approved_permissions = set(approved.get("permissions") or [])
    candidate_permissions = set(candidate.get("permissions") or [])
    expanded = sorted(candidate_permissions - approved_permissions)
    if expanded:
        errors.append("candidate expands permissions: " + ", ".join(expanded))

    if candidate.get("data_boundary") != approved.get("data_boundary"):
        errors.append("candidate changes the approved data boundary")
    if candidate.get("approval_policy") != approved.get("approval_policy"):
        errors.append("candidate changes the approved approval policy")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    try:
        approved = load_record(args.approved)
        candidate = load_record(args.candidate)
        errors = authority_errors(approved, candidate)
    except (OSError, ValueError, yaml.YAMLError, jsonschema.ValidationError) as exc:
        errors = [f"invalid authority input: {type(exc).__name__}"]
    report = {"result": "PASS" if not errors else "BLOCKED", "errors": errors}
    print(json.dumps(report, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
