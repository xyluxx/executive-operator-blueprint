"""Executable contracts for optional integration onboarding and lanes."""
from __future__ import annotations

import importlib.util
import json
import hashlib
import base64

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "4dc2aeca2633476d3d497f2a4368ef91172b378e"  # pragma: allowlist secret
POLICY_DIGEST = "62f215f5a8fc7a44bdeaf0561b8ab33c2be477600ca396a973310bc4c58438ef"  # pragma: allowlist secret
MODULE_PATH = ROOT / "tools" / "integration-contract" / "integration_contract.py"
spec = importlib.util.spec_from_file_location("integration_contract", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

FakeAdapter = module.FakeAdapter
IntegrationHarness = module.IntegrationHarness
PromotionError = module.PromotionError
UnknownEffect = module.UnknownEffect
validate_capability_status = module.validate_capability_status
validate_integration_record = module.validate_integration_record
EvidenceFetchAuthority = module.EvidenceFetchAuthority
EvidenceReceiptVerifier = module.EvidenceReceiptVerifier

TEST_AUTHORITY_PRIVATE_KEY = bytes(range(32))  # deterministic test-only key; never an onboarding secret
setattr(module, "EVIDENCE_PUBLIC_KEY_B64", base64.b64encode(
    Ed25519PrivateKey.from_private_bytes(TEST_AUTHORITY_PRIVATE_KEY).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
).decode("ascii"))


def load_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_yaml(relative: str):
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def fetch_result_for(entry):
    content_by_id = {
        "google-source": b"a", "google-docs": b"b", "google-data-policy": b"c", "google-cost": b"d",
        "composio-pricing": b"e", "composio-plan": b"f", "composio-tool_limits": b"g",
        "composio-trigger_limits": b"h", "composio-scopes": b"i", "composio-data_policy": b"j",
        "composio-write_behavior": b"k",
    }
    return {"requested_url": entry["url"], "final_url": entry["url"], "title": entry["title"],
            "assertions": entry["required_assertions"], "content": content_by_id[entry["id"]]}


def current_evidence(now: datetime, *, private_key=TEST_AUTHORITY_PRIVATE_KEY, fetcher=None):
    authority = EvidenceFetchAuthority(private_key, fetcher or fetch_result_for, now=lambda: now)
    return {
        key: {"receipt": authority.issue("composio", key, f"composio-{key}", module.authority_url("composio", key)),
              "value": f"reviewed-{key}"}
        for key in ("pricing", "plan", "tool_limits", "trigger_limits", "scopes", "data_policy", "write_behavior")
    }


def google_receipts(now: datetime):
    authority = EvidenceFetchAuthority(TEST_AUTHORITY_PRIVATE_KEY, fetch_result_for, now=lambda: now)
    required = {"source": "google-source", "documentation": "google-docs",
                "data_policy": "google-data-policy", "cost": "google-cost"}
    return {kind: authority.issue("google", kind, authority_id, module.authority_url("google", kind))
            for kind, authority_id in required.items()}


def payload_digest(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def approve(harness, account, target, values, now=None, key_policy=None):
    harness.approve_live(
        account=account, operations=["read", "write", "readback"], target=target,
        material_payload_digest=payload_digest(values),
        operation_key_policy=key_policy or {"type": "prefix", "value": "op-"},
        task_id="task-1", requirement_version="req-v1", policy_digest=POLICY_DIGEST,
        expires_at=((now or datetime.now(timezone.utc)) + timedelta(hours=1)).isoformat(),
    )


def test_provider_neutral_harness_proves_synthetic_then_separate_live_read_write_readback():
    adapter = FakeAdapter(account_identity="sandbox@example.test", provider="google")
    harness = IntegrationHarness(adapter)
    harness.define(outcome="Preserve a known cell", evidence="exact readback")
    harness.record_discovery(["native", "skill", "plugin", "mcp", "direct-api", "do-not-enable"])
    harness.record_review(source=module.authority_url("google", "source"), version="commit:" + COMMIT, license="MIT", dependencies=["google-api-python-client==2.1.0"], permissions=["sheet.read", "sheet.write"], data_categories=["business-test-data"], data_policy="https://developers.google.com/terms/api-services-user-data-policy", cost_evidence="https://developers.google.com/sheets/api/limits")
    harness.select_route("direct-api", approved_by="owner@example.test")
    harness.pin_source("commit:" + COMMIT)

    synthetic = harness.run_synthetic()
    assert synthetic["result"] == "pass"
    assert adapter.live_calls == []
    with pytest.raises(PermissionError):
        harness.run_live_read_write_readback("Sheet1!A1", [["approved"]])

    approve(harness, "sandbox@example.test", "Sheet1!A1", [["approved"]], key_policy={"type": "exact", "value": "onboarding-live-write"})
    live = harness.run_live_read_write_readback("Sheet1!A1", [["approved"]], task_id="task-1", requirement_version="req-v1")
    assert live["readback"] == [["approved"]]
    assert adapter.live_calls == ["read", "write", "readback"]

    harness.record_recovery(fallback="disable integration", disable="revoke adapter", rollback="restore prior pinned config")
    captured = harness.capture_lane("reviewed-integration", reviewed=True, contains_private_data=False)
    assert captured["reusable"] is True


def test_onboarding_cannot_skip_do_not_enable_comparison_or_immutable_pin():
    harness = IntegrationHarness(FakeAdapter(provider="google"))
    harness.define(outcome="x", evidence="y")
    harness.record_discovery(["native", "direct-api"])
    harness.record_review(source=module.authority_url("google", "source"), version="commit:" + COMMIT, license="MIT", dependencies=["dep==1.0"], permissions=["read"], data_categories=["test"], data_policy="https://developers.google.com/terms/api-services-user-data-policy", cost_evidence="https://developers.google.com/sheets/api/limits")
    harness.select_route("direct-api", approved_by="owner")
    with pytest.raises(PromotionError, match="do-not-enable"):
        harness.run_synthetic()

    harness.record_discovery(["native", "direct-api", "do-not-enable"])
    with pytest.raises(PromotionError, match="immutable"):
        harness.run_synthetic()


def test_sheets_contract_exact_range_idempotency_unknown_reconciliation_revoke_disable():
    adapter = FakeAdapter(account_identity="sheets-sandbox@example.test")
    harness = IntegrationHarness(adapter)
    approve(harness, "sheets-sandbox@example.test", "Budget!B2:C2", [["Q1", 10]])

    first = harness.scoped_sheet_write("Budget!B2:C2", [["Q1", 10]], operation_key="op-1", task_id="task-1", requirement_version="req-v1")
    repeat = harness.scoped_sheet_write("Budget!B2:C2", [["Q1", 10]], operation_key="op-1", task_id="task-1", requirement_version="req-v1")
    assert first == repeat
    assert adapter.write_count == 1
    assert adapter.read_range("Budget!B2:C2") == [["Q1", 10]]
    with pytest.raises(PermissionError):
        harness.scoped_sheet_write("Budget!A1", [["wrong"]], operation_key="op-2", task_id="task-1", requirement_version="req-v1")

    with pytest.raises(PermissionError, match="payload"):
        harness.scoped_sheet_write("Budget!B2:C2", [["changed"]], operation_key="op-2", task_id="task-1", requirement_version="req-v1")
    with pytest.raises(PermissionError, match="task or requirement"):
        harness.scoped_sheet_write("Budget!B2:C2", [["Q1", 10]], operation_key="op-2", task_id="task-1", requirement_version="req-v2")
    with pytest.raises(PermissionError, match="operation digest"):
        harness.adapter.write_range("Budget!B2:C2", [["changed"]], operation_key="op-1")

    approve(harness, "sheets-sandbox@example.test", "Budget!B2:C2", [["Q2", 20]])
    adapter.timeout_after_next_write = True
    with pytest.raises(UnknownEffect):
        harness.scoped_sheet_write("Budget!B2:C2", [["Q2", 20]], operation_key="op-unknown", task_id="task-1", requirement_version="req-v1")
    assert harness.reconcile_unknown("op-unknown", "Budget!B2:C2", [["Q2", 20]]) == "confirmed-success"
    assert adapter.write_count == 2

    harness.revoke()
    harness.disable()
    assert adapter.revoked is True and adapter.enabled is False
    with pytest.raises(PermissionError):
        adapter.read_range("Budget!B2:C2")
    with pytest.raises(PromotionError, match="current enabled"):
        harness.promote("Verified")


def test_proof_is_invalidated_by_account_scope_policy_source_and_version_changes():
    values = [["ok"]]
    for change in ("account", "scope", "policy", "source", "version"):
        adapter = FakeAdapter(account_identity="sandbox@example.test")
        harness = IntegrationHarness(adapter)
        approve(harness, adapter.account_identity, "Sheet1!A1", values)
        harness.scoped_sheet_write("Sheet1!A1", values, "op-1", task_id="task-1", requirement_version="req-v1")
        assert harness.promote("Verified") == "Verified"
        if change == "account": adapter.account_identity = "other@example.test"
        elif change == "scope": adapter.scopes = ("other",)
        elif change == "policy": adapter.policy_digest = "fedcba9876543210" * 4  # pragma: allowlist secret
        elif change == "source": adapter.source_ref = "commit:" + "fedcba9876543210" * 2 + "fedcba98"  # pragma: allowlist secret
        else: adapter.version = "2.0.0"
        assert harness.live_contract_proof is None
        assert harness.status == "Blocked"
        with pytest.raises(PromotionError, match="current adapter"):
            harness.promote("Verified")


@pytest.mark.parametrize("field,value", [("tested_at", "not-a-date"), ("expires_at", "not-a-date")])
def test_runtime_malformed_proof_timestamp_is_controlled_denial(field, value):
    adapter = FakeAdapter(account_identity="sandbox@example.test")
    harness = IntegrationHarness(adapter)
    approve(harness, adapter.account_identity, "Sheet1!A1", [["ok"]])
    harness.scoped_sheet_write("Sheet1!A1", [["ok"]], "op-1", task_id="task-1", requirement_version="req-v1")
    harness.live_contract_proof[field] = value
    with pytest.raises(PromotionError, match="timestamp"):
        harness.promote("Verified")


def test_composio_stale_or_missing_official_evidence_blocks_promotion():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    harness = IntegrationHarness(FakeAdapter(provider="composio"), now=lambda: now)
    with pytest.raises(PromotionError, match="private onboarding trusted-fetch authority"):
        harness.promote("Configured", provider_evidence={})

    stale = current_evidence(now - timedelta(days=31))
    with pytest.raises(PromotionError, match="stale official evidence"):
        harness.promote("Configured", provider_evidence=stale)

    assert harness.promote("Configured", provider_evidence=current_evidence(now)) == "Configured"
    with pytest.raises(PromotionError, match="live contract proof"):
        harness.promote("Verified", provider_evidence=current_evidence(now))

    hostile = current_evidence(now)
    hostile["pricing"]["receipt"]["payload"]["canonical_url"] = "https://attacker.example/pricing"
    with pytest.raises(PromotionError, match="authenticated trusted-fetch receipt"):
        harness.promote("Configured", provider_evidence=hostile)
    malformed = current_evidence(now)
    malformed["plan"]["receipt"]["payload"]["retrieved_at"] = "not-a-date"
    with pytest.raises(PromotionError, match="authenticated trusted-fetch receipt"):
        harness.promote("Configured", provider_evidence=malformed)


@pytest.mark.parametrize("attack", [
    "https://github.com/attacker/repo/blob/4dc2aeca2633476d3d497f2a4368ef91172b378e/README.md",
    "https://docs.composio.dev/arbitrary/fake-pricing",
    "https://docs.composio.dev/docs/pricing/../arbitrary",
    "https://docs.composio.dev/docs/pricing/%2e%2e/arbitrary",
])
def test_allowlisted_host_wrong_path_and_path_confusion_never_prove_authority(attack):
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    evidence = current_evidence(now)
    evidence["pricing"]["receipt"]["payload"]["canonical_url"] = attack
    with pytest.raises(PromotionError, match="authenticated trusted-fetch receipt"):
        IntegrationHarness(FakeAdapter(provider="composio"), now=lambda: now).promote(
            "Configured", provider_evidence=evidence
        )


@pytest.mark.parametrize("field,value", [
    ("authority_id", "google-source"),
    ("source", "https://docs.composio.dev/docs/pricing/"),
    ("canonical_url", "https://docs.composio.dev/arbitrary/redirect-target"),
    ("provider", "google"),
    ("kind", "data_policy"),
])
def test_wrong_authority_identity_redirect_provider_or_kind_is_denied(field, value):
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    evidence = current_evidence(now)
    payload_field = "canonical_url" if field == "source" else field
    evidence["pricing"]["receipt"]["payload"][payload_field] = value
    with pytest.raises(PromotionError, match="authenticated trusted-fetch receipt"):
        IntegrationHarness(FakeAdapter(provider="composio"), now=lambda: now).promote(
            "Configured", provider_evidence=evidence
        )


def test_runtime_harness_has_only_pinned_verifier_and_no_issue_or_private_key_path():
    harness = IntegrationHarness(FakeAdapter(provider="composio"))
    assert isinstance(harness.evidence_verifier, EvidenceReceiptVerifier)
    assert not hasattr(harness.evidence_verifier, "issue")
    assert not hasattr(harness, "evidence_authority")
    assert not any("private" in name.lower() or "sign" in name.lower() for name in vars(harness.evidence_verifier))


@pytest.mark.parametrize("provider", ["google", "composio"])
def test_bundled_default_cannot_promote_sheets_or_composio_without_private_onboarding_receipts(provider):
    harness = IntegrationHarness(FakeAdapter(provider=provider))
    with pytest.raises(PromotionError, match="private onboarding trusted-fetch authority"):
        harness.promote("Configured")
    assert harness.status == "Optional"


def test_bundled_registry_metadata_cannot_claim_configured_without_private_receipts():
    record = load_json("templates/integration-registry.example.json")
    record["provider"] = "google"
    record["capability_status"] = "Configured"
    assert "private onboarding trusted-fetch authority receipts required" in validate_integration_record(record)


def test_public_hash_fabrication_caller_key_substitution_and_tampering_are_denied():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    valid = current_evidence(now)

    fabricated = json.loads(json.dumps(valid))
    receipt = fabricated["pricing"]["receipt"]
    receipt["signature"] = hashlib.sha256(json.dumps(receipt["payload"], sort_keys=True).encode()).hexdigest()
    with pytest.raises(PromotionError, match="authenticated trusted-fetch receipt"):
        IntegrationHarness(FakeAdapter(provider="composio"), now=lambda: now).promote("Configured", fabricated)

    foreign = current_evidence(now, private_key=bytes(reversed(range(32))))
    with pytest.raises(PromotionError, match="authenticated trusted-fetch receipt"):
        IntegrationHarness(FakeAdapter(provider="composio"), now=lambda: now).promote("Configured", foreign)

    tampered = json.loads(json.dumps(valid))
    tampered["pricing"]["receipt"]["payload"]["title"] = "caller supplied title"
    with pytest.raises(PromotionError, match="authenticated trusted-fetch receipt"):
        IntegrationHarness(FakeAdapter(provider="composio"), now=lambda: now).promote("Configured", tampered)


def test_authority_rejects_unavailable_fetch_redirect_and_fake_assertions():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    url = module.authority_url("composio", "pricing")
    with pytest.raises(PromotionError, match="trusted fetch unavailable"):
        EvidenceFetchAuthority(TEST_AUTHORITY_PRIVATE_KEY, lambda entry: None, now=lambda: now).issue(
            "composio", "pricing", "composio-pricing", url)

    def redirected(entry):
        result = fetch_result_for(entry); result["final_url"] = "https://attacker.example/redirect"; return result
    with pytest.raises(PromotionError, match="redirect"):
        EvidenceFetchAuthority(TEST_AUTHORITY_PRIVATE_KEY, redirected, now=lambda: now).issue(
            "composio", "pricing", "composio-pricing", url)

    def fake_assertions(entry):
        result = fetch_result_for(entry); result["assertions"] = ["caller says current pricing"]; return result
    with pytest.raises(PromotionError, match="assertions"):
        EvidenceFetchAuthority(TEST_AUTHORITY_PRIVATE_KEY, fake_assertions, now=lambda: now).issue(
            "composio", "pricing", "composio-pricing", url)


def test_registry_digests_are_documented_public_sha256_content_pins_not_secrets():
    registry = load_json("contracts/evidence-authorities.json")
    assert registry["digest_purpose"] == "public-sha256-content-integrity-pins"
    assert all(len(bytes.fromhex(entry["content_digest"])) == 32 for entry in registry["authorities"])
    baseline = load_json(".secrets.baseline")
    findings = baseline["results"]["contracts/evidence-authorities.json"]
    assert len(findings) == len(registry["authorities"]) == 11
    assert all(item["type"] == "Hex High Entropy String" and item["is_secret"] is False for item in findings)


def test_registry_tampering_is_fail_closed(tmp_path):
    registry = load_json("contracts/evidence-authorities.json")
    registry["authorities"][0]["url"] = "https://docs.composio.dev/arbitrary/fake"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(registry))
    with pytest.raises(PromotionError, match="integrity"):
        module.EvidenceAuthorityResolver(registry_path=path)


def test_github_source_requires_exact_reviewed_repo_and_immutable_commit_path():
    harness = IntegrationHarness(FakeAdapter(provider="google"))
    review = dict(source="https://github.com/attacker/repo", source_authority_id="google-source",
                  version="commit:" + COMMIT, license="Apache-2.0", dependencies=["dep==1.0"],
                  permissions=["read"], data_categories=["test"],
                  data_policy="https://developers.google.com/terms/api-services-user-data-policy",
                  data_policy_authority_id="google-data-policy",
                  cost_evidence="https://developers.google.com/sheets/api/limits",
                  cost_evidence_authority_id="google-cost")
    with pytest.raises(PromotionError, match="registered evidence authority"):
        harness.record_review(**review)


@pytest.mark.parametrize("field,value", [
    ("source", "https://attacker.example/code"), ("version", "commit:x"), ("version", "commit:" + "0" * 40),
    ("license", " "), ("dependencies", []), ("permissions", [""]),
    ("data_categories", []), ("data_policy", "placeholder"), ("cost_evidence", "unknown"),
])
def test_candidate_review_rejects_non_authoritative_placeholder_or_empty_fields(field, value):
    review = dict(source=module.authority_url("google", "source"), version="commit:" + COMMIT,
                  license="Apache-2.0", dependencies=["google-api-python-client==2.1.0"],
                  permissions=["spreadsheets.readonly"], data_categories=["sheet-values"],
                  data_policy="https://developers.google.com/terms/api-services-user-data-policy",
                  cost_evidence="https://developers.google.com/sheets/api/limits")
    review[field] = value
    with pytest.raises(PromotionError):
        IntegrationHarness(FakeAdapter()).record_review(**review)


def test_verified_registry_requires_current_bound_real_proof():
    schema = load_json("templates/integration-registry.schema.json")
    instance = load_json("templates/integration-registry.example.json")
    instance["capability_status"] = "Verified"
    for mutation in (lambda x: x.update(live_proof=None), lambda x: x.update(lifecycle="disabled")):
        candidate = json.loads(json.dumps(instance)); mutation(candidate)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(candidate)


def verified_record(now):
    record = load_json("templates/integration-registry.example.json")
    record.update({
        "provider": "google", "account_owner": "sandbox@example.test",
        "credential_reference": "credential:google-sandbox", "credential_status": "tested",
        "requested_scopes": ["spreadsheets.read", "spreadsheets.write"],
        "capability_status": "Verified", "enabled": True, "lifecycle": "active", "health": "healthy",
        "selection_approval": "approval:route-123", "approved_operations": ["read", "write", "readback"],
        "authority_receipts": google_receipts(now),
        "live_proof": {
            "result": "pass", "synthetic": False, "evidence": "provider response and authoritative readback",
            "approved": True, "approval_id": "approval:write-123", "tested_at": now.isoformat(),
            "account": "sandbox@example.test", "target": "Sheet1!A1", "source_ref": "commit:" + COMMIT,
            "version": "1.0.0", "policy_digest": POLICY_DIGEST, "payload_digest": payload_digest([["ok"]]),
            "scopes": ["spreadsheets.read", "spreadsheets.write"], "operations": ["read", "write", "readback"],
            "write_applicable": True, "write_passed": True, "readback_applicable": True,
            "readback_passed": True, "readback_matches_payload": True, "authoritative_read": True,
            "unresolved_unknown": False,
        },
    })
    state = {
        "provider": "google", "account": "sandbox@example.test", "enabled": True, "revoked": False,
        "credential_status": "tested", "health": "healthy", "scopes": record["requested_scopes"],
        "policy_digest": POLICY_DIGEST, "source_ref": "commit:" + COMMIT, "version": "1.0.0",
        "approval_id": "approval:write-123", "approval_protected": True, "approval_current": True,
        "payload_digest": record["live_proof"]["payload_digest"], "target": "Sheet1!A1",
    }
    return record, state


def test_semantic_validator_rejects_reviewers_fabricated_verified_record_and_each_field_mutation():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    record, state = verified_record(now)
    assert validate_integration_record(record, current_state=state, now=now) == []

    mutations = {
        "future tested_at": ("live_proof", "tested_at", "2999-01-01T00:00:00Z"),
        "stale tested_at": ("live_proof", "tested_at", "2020-01-01T00:00:00Z"),
        "unparseable tested_at": ("live_proof", "tested_at", "not-a-date"),
        "zero commit": ("live_proof", "source_ref", "commit:" + "0" * 40),
        "repeated digest": ("live_proof", "policy_digest", "a" * 64),
        "placeholder account": ("live_proof", "account", "unknown"),
        "placeholder scope": ("live_proof", "scopes", ["unselected"]),
        "placeholder target": ("live_proof", "target", "placeholder"),
        "missing write": ("live_proof", "operations", ["read"]),
        "no readback match": ("live_proof", "readback_matches_payload", False),
        "synthetic": ("live_proof", "synthetic", True),
    }
    for label, (container, field, value) in mutations.items():
        candidate = json.loads(json.dumps(record)); candidate[container][field] = value
        assert validate_integration_record(candidate, current_state=state, now=now), label


@pytest.mark.parametrize("field,value", [
    ("license", "unknown"), ("dependencies", ["unknown"]), ("permissions", ["placeholder"]),
    ("data_categories", ["unselected"]), ("data_policy", "https://attacker.example/policy"),
    ("cost_evidence", "https://attacker.example/pricing"),
])
def test_semantic_registry_review_rejects_superficial_evidence(field, value):
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    record, _ = verified_record(now)
    record["candidate_review"][field] = value
    assert validate_integration_record(record, now=now)


def test_capability_status_taxonomy_is_exact_and_rejects_synonyms_and_false_promotion():
    contract = load_yaml("contracts/capability-status.yaml")
    schema = load_json("templates/capability-status.schema.json")
    jsonschema.Draft202012Validator(schema).validate(contract)
    assert contract["statuses"] == ["Native", "Blueprint", "Bundled", "Configured", "Verified", "Optional", "Planned", "Blocked"]
    assert contract["forbidden_synonyms"]["Built-in"] == "Native"
    for status in contract["statuses"]:
        assert validate_capability_status(status) == status
    for drift in ("Built-in", "built-in", "native", "Active", "Enabled", "Ready"):
        with pytest.raises(ValueError):
            validate_capability_status(drift)
    with pytest.raises(PromotionError):
        IntegrationHarness(FakeAdapter()).promote("Verified", provider_evidence=None)


def test_lane_preservation_matrix_is_schema_backed_complete_and_disabled_by_default():
    matrix = load_yaml("contracts/business-lane-preservation.yaml")
    schema = load_json("templates/business-lane-preservation.schema.json")
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(matrix)
    expected = {"email", "calendar", "meetings", "crm", "marketing", "channels", "remote-desktop", "credentials", "documents", "storage", "website-reliability", "recovery"}
    assert set(matrix["lanes"]) == expected
    for lane in matrix["lanes"].values():
        assert lane["enabled"] is False
        assert lane["status"] in {"Blueprint", "Bundled", "Optional", "Planned", "Blocked"}
        assert all(lane[field] for field in ("account_identity", "permissions", "approval", "proof", "failure_behavior", "disable", "recovery"))


def test_optional_composio_and_sheets_are_inventoried_unconfigured_and_disabled():
    capabilities = load_yaml("capabilities.yaml")
    for name in ("composio-connectors", "google-sheets"):
        pack = capabilities["capability_packs"][name]
        assert pack["default_requested"] is False
        assert pack["configured"] is False
        assert pack["enabled"] is False
        assert pack["blueprint_status"] == "Optional"
    preflight = load_yaml("contracts/preflight-inventory.yaml")
    assert preflight["optional_integrations"]["composio"]["enabled"] is False
    assert preflight["optional_integrations"]["google-sheets"]["configured"] is False
