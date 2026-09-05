"""Canonical serialization and schema checks for operator control."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
from jsonschema.validators import validator_for
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = {
    name: ROOT / "templates" / f"{name}.schema.json"
    for name in ("approval-record", "action-intent", "action-result", "acceptance-policy", "acceptance-record", "verification-result", "correction-record")
}


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def material_payload_digest(payload) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def validate(name: str, document: dict) -> None:
    schema = json.loads(SCHEMAS[name].read_text())
    resources = []
    for path in (ROOT / "templates").glob("*.schema.json"):
        candidate = json.loads(path.read_text())
        if isinstance(candidate.get("$id"), str):
            resources.append((candidate["$id"], Resource.from_contents(candidate)))
    registry = Registry().with_resources(resources)
    validator = validator_for(schema)(schema, registry=registry)
    validator.validate(document)


def validate_document(name: str, schema: dict) -> None:
    """Validate a shipped schema itself, not an instance."""
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError(f"{name} is not JSON Schema 2020-12")
    jsonschema.Draft202012Validator.check_schema(schema)
