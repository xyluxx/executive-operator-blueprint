#!/usr/bin/env python3
"""Validate and reconcile the canonical website registry and watchdog targets."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_SCHEMA = ROOT / "templates" / "website-registry.schema.json"
TARGET_SCHEMA = Path(__file__).with_name("sites.schema.json")

IDENTITY_FIELDS = (
    "id", "name", "host", "environment", "credential_reference",
    "credential_principal", "owner", "repair_policy", "notification_route",
)
AUTHORITY_FIELDS = (
    "approval_reference", "approval_version", "operator_task_reference",
    "task_version", "requirement_version", "operation_key",
)
POLICY_FIELDS = (
    "healthy_codes", "content_contains", "timeout_seconds", "attempts",
    "retry_delay_seconds", "failure_cycles", "max_body_bytes",
    "allow_private_networks", "allowed_redirect_hosts", "allowed_repairs",
)


def _schema(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _ids(items, document):
    counts = Counter(item.get("id") for item in items if isinstance(item, dict))
    duplicates = sorted(str(key) for key, count in counts.items() if key is not None and count > 1)
    if duplicates:
        raise ValueError(f"duplicate site IDs in {document}: {', '.join(duplicates)}")


def _semantic_registry(registry):
    _ids(registry["sites"], "canonical registry")
    for site in registry["sites"]:
        parsed = urlparse(site["health_url"])
        if (parsed.hostname or "").lower().rstrip(".") != site["host"].lower().rstrip("."):
            raise ValueError(f"health_url host does not match host for {site['id']}")
        if site["repair_policy"] not in site.get("allowed_repairs", [site["repair_policy"]]):
            raise ValueError(f"repair_policy is not allowed for {site['id']}")


def validate_registry(registry):
    jsonschema.validate(registry, _schema(REGISTRY_SCHEMA))
    _semantic_registry(registry)


def validate_targets(targets):
    jsonschema.validate(targets, _schema(TARGET_SCHEMA))


def _target(site):
    result = {key: site[key] for key in IDENTITY_FIELDS}
    result.update({"enabled": True, "url": site["health_url"]})
    for key in POLICY_FIELDS:
        if key in site:
            result[key] = site[key]
    for key in AUTHORITY_FIELDS:
        if key in site:
            result[key] = site[key]
    return result


def build_targets(registry):
    validate_registry(registry)
    result = {"sites": [_target(site) for site in registry["sites"] if site["enabled"]]}
    validate_targets(result)
    return result


def reconcile(registry, targets):
    validate_registry(registry)
    validate_targets(targets)
    enabled_list = [site for site in registry["sites"] if site["enabled"]]
    enabled = {site["id"]: site for site in enabled_list}
    target_list = [site for site in targets["sites"] if site.get("enabled", True)]
    counts = Counter(site["id"] for site in target_list)
    indexed = {site["id"]: site for site in target_list if counts[site["id"]] == 1}
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    missing = sorted(set(enabled) - set(counts))
    extra = sorted(set(counts) - set(enabled))
    stale = {}
    for site_id in sorted(set(enabled) & set(indexed)):
        expected = _target(enabled[site_id])
        actual = indexed[site_id]
        drift = {}
        for target_field, expected_value in expected.items():
            if target_field == "enabled":
                continue
            source_field = "health_url" if target_field == "url" else target_field
            if actual.get(target_field) != expected_value:
                drift[source_field] = {"registry": expected_value, "target": actual.get(target_field)}
        if drift:
            stale[site_id] = drift
    return {"ok": not any((missing, extra, duplicates, stale)), "missing": missing,
            "extra": extra, "duplicates": duplicates, "stale": stale}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--write-targets", action="store_true")
    args = parser.parse_args(argv)
    source = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    target_path = Path(args.targets)
    validate_registry(source)
    if args.write_targets:
        target_path.write_text(json.dumps(build_targets(source), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = reconcile(source, json.loads(target_path.read_text(encoding="utf-8")))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
