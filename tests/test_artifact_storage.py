import hashlib
import importlib.util
import json
import os
import stat
import time
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

MODULE_PATH = Path(__file__).parents[1] / "tools" / "artifact-storage" / "artifact_storage.py"
SPEC = importlib.util.spec_from_file_location("artifact_storage", MODULE_PATH)
assert SPEC and SPEC.loader
artifacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifacts)


def _raw_public(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

def local_adapter(account: str | None = None, target: str | None = None, root: Path | None = None, *,
                  account_id: str | None = None, target_id: str | None = None):
    account = account or account_id; target = target or target_id
    assert account is not None and target is not None and root is not None
    key = Ed25519PrivateKey.generate()
    state = Path(root).parent / (Path(root).name + "-authority.json")
    decisions = {}
    resolver = artifacts.ProtectedPolicyResolver(state, _raw_public(key), issuer="test-storage")
    authority = artifacts.StoragePolicyAuthority(key, state, issuer="test-storage", trusted_policy_resolver=decisions.__getitem__)
    adapter = artifacts.LocalFilesystemAdapter(account, target, root, policy_provider=resolver)
    original = adapter.upload
    def upload(request, *args, **kwargs):
        object_id = hashlib.sha256((target + "/" + artifacts._safe_relative(request.object_name).as_posix()).encode()).hexdigest()[:24]
        decisions[request.idempotency_key] = {"object_id": object_id, "permission_scope": request.permission_scope, "retention": request.retention}
        authority.issue(request.idempotency_key)
        return original(request, *args, **kwargs)
    adapter.upload = upload
    return adapter

_synthetic_keys = {}
def synthetic_adapter(provider, account, target, journal_path):
    state = Path(journal_path).with_suffix(".authority.json"); key = _synthetic_keys.setdefault(str(state), Ed25519PrivateKey.generate()); decisions = {}
    resolver = artifacts.ProtectedPolicyResolver(state, _raw_public(key), issuer="test-storage")
    authority = artifacts.StoragePolicyAuthority(key, state, issuer="test-storage", trusted_policy_resolver=decisions.__getitem__)
    adapter = artifacts.SyntheticProviderAdapter(provider, account, target, journal_path=journal_path, policy_provider=resolver)
    original = adapter.upload
    def upload(request, *args, **kwargs):
        object_id = f"synthetic-{provider}-{hashlib.sha256((target + request.object_name).encode()).hexdigest()[:16]}"
        decisions[request.idempotency_key] = {"object_id": object_id, "permission_scope": request.permission_scope, "retention": request.retention}
        authority.issue(request.idempotency_key)
        return original(request, *args, **kwargs)
    adapter.upload = upload
    return adapter


class _TLSFixture:
    def __init__(self, _legacy_key, *, issuer):
        self._key = Ed25519PrivateKey.generate(); self._probes = {}; self._next = 0
        self._verifier = artifacts.TLSReceiptVerifier(_raw_public(self._key), issuer=issuer)
        self._authority = artifacts.TLSProbeAuthority(self._key, issuer=issuer, trusted_probe_resolver=self._probes.__getitem__)
    def verify(self, *args, **kwargs):
        return self._verifier.verify(*args, **kwargs)
    def issue(self, *, route, audience, auth_policy, expires_at, certificate_identity=None, tunnel_identity=None, collected_at=None):
        key = str(self._next); self._next += 1
        self._probes[key] = {"url": route, "host": (artifacts.urlsplit(route).hostname or "").lower().rstrip("."),
            "audience": audience, "auth_policy": auth_policy, "collected_at": collected_at or time.time(),
            "expires_at": expires_at, "certificate_identity": certificate_identity, "tunnel_identity": tunnel_identity, "revoked": False}
        return self._authority.issue(key)

def tls_fixture(key, *, issuer):
    return _TLSFixture(key, issuer=issuer)

SYNTHETIC = {
    "title": "Synthetic Quarterly Report",
    "columns": ["Region", "Units"],
    "rows": [["North", 12], ["South", 7]],
    "paragraphs": ["Synthetic content only.", "No customer data."],
}


def test_generate_real_office_files_and_reopen_expected_content(tmp_path):
    records = artifacts.generate_artifacts(SYNTHETIC, tmp_path / "out")
    assert {item["format"] for item in records} == {"csv", "xlsx", "docx", "pdf"}
    for item in records:
        path = Path(item["path"])
        assert path.is_file() and path.is_absolute()
        assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert item["verified"] is True
        assert "Synthetic Quarterly Report" in item["content"]
        assert item["mime"] == artifacts.MIME_TYPES[item["format"]]
    assert Path(next(x["path"] for x in records if x["format"] == "pdf")).read_bytes().startswith(b"%PDF-")
    for extension in ("xlsx", "docx"):
        path = Path(next(x["path"] for x in records if x["format"] == extension))
        assert zipfile.is_zipfile(path)


def test_preview_metadata_uses_local_media_and_never_claims_delivery(tmp_path):
    generated = artifacts.generate_artifacts(SYNTHETIC, tmp_path / "generated")
    path = Path(next(item["path"] for item in generated if item["format"] == "pdf"))
    preview = artifacts.local_preview(path, "application/pdf")
    assert preview == {
        "surface": "hermes-media",
        "media": f"MEDIA:{path.resolve()}",
        "path": str(path.resolve()),
        "mime": "application/pdf",
        "size": path.stat().st_size,
        "delivery_status": "prepared-local-not-sent",
    }


def test_local_adapter_contract_idempotency_readback_revoke_delete_disable(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("name,value\nsynthetic,1\n", encoding="utf-8")
    source.chmod(0o600)
    adapter = local_adapter(
        account_id="local-owner", target_id="artifact-vault", root=tmp_path / "vault"
    )
    request = artifacts.UploadRequest(
        source=source, object_name="reports/source.csv", idempotency_key="task-17-v1",
        permission_scope="owner-only", retention="delete-after-7d",
    )
    first = adapter.upload(request)
    second = adapter.upload(request)
    assert first == second
    assert first.provider == "local-filesystem"
    assert first.account_id == "local-owner" and first.target_id == "artifact-vault"
    readback = adapter.readback(first.object_id)
    assert readback.sha256 == first.sha256 and readback.version == first.version
    assert readback.permission_scope == "owner-only" and readback.retention == "delete-after-7d"
    adapter.revoke(first.object_id)
    assert adapter.readback(first.object_id).revoked is True
    adapter.delete(first.object_id)
    with pytest.raises(FileNotFoundError):
        adapter.readback(first.object_id)
    adapter.disable()
    with pytest.raises(artifacts.AdapterDisabled):
        adapter.upload(request)


def test_deletion_leaves_only_non_sensitive_audit_tombstone(tmp_path):
    source = tmp_path / "private-source.txt"
    source.write_text("private-content-sentinel", encoding="utf-8")
    source.chmod(0o600)

    compensating = local_adapter("compensating-account", "compensating-target", tmp_path / "compensating-vault")
    compensating_record = compensating.upload(artifacts.UploadRequest(
        source, "private/report.txt", "compensating-key", "owner-only", "delete-after-test"
    ))
    original_save = compensating._save_audit
    compensating._save_audit = lambda: (_ for _ in ()).throw(OSError("synthetic audit failure"))
    with pytest.raises(OSError, match="synthetic audit failure"):
        compensating.delete(compensating_record.object_id)
    assert compensating.readback(compensating_record.object_id).sha256 == compensating_record.sha256
    assert compensating.audit_events() == []
    compensating._save_audit = original_save

    local = local_adapter("local-account-sentinel", "local-target-sentinel", tmp_path / "vault")
    local_record = local.upload(artifacts.UploadRequest(
        source, "private/report.txt", "local-delete-key", "owner-only", "delete-after-test"
    ))
    local.delete(local_record.object_id)
    local_restarted = local_adapter("local-account-sentinel", "local-target-sentinel", tmp_path / "vault")
    local_event = local_restarted.audit_events()[-1]

    journal = tmp_path / "synthetic-journal.json"
    synthetic = synthetic_adapter("box", "cloud-account-sentinel", "cloud-target-sentinel", journal)
    synthetic_record = synthetic.upload(artifacts.UploadRequest(
        source, "private/report.txt", "cloud-delete-key", "private", "delete-after-test"
    ))
    synthetic.delete(synthetic_record.object_id)
    restarted = synthetic_adapter("box", "cloud-account-sentinel", "cloud-target-sentinel", journal)
    cloud_event = restarted.audit_events()[-1]

    expected_keys = {
        "action", "provider", "object_id_digest", "account_id_digest",
        "target_id_digest", "version", "recorded_at",
    }
    assert set(local_event) == expected_keys
    assert set(cloud_event) == expected_keys
    assert local_event["action"] == cloud_event["action"] == "artifact-deleted"
    assert local_event["provider"] == "local-filesystem"
    assert cloud_event["provider"] == "box"
    serialized = json.dumps([local_event, cloud_event], sort_keys=True)
    for sensitive_value in (
        str(source), "private-content-sentinel", local_record.object_id, synthetic_record.object_id,
        local_record.sha256, synthetic_record.sha256, "local-account-sentinel", "local-target-sentinel",
        "cloud-account-sentinel", "cloud-target-sentinel", "private/report.txt",
    ):
        assert sensitive_value not in serialized

    tampered = json.loads(journal.read_text(encoding="utf-8"))
    tampered["audit"][0]["path"] = "/private/path"
    journal.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="deletion audit"):
        synthetic_adapter("box", "cloud-account-sentinel", "cloud-target-sentinel", journal)


def test_local_adapter_rejects_traversal_symlink_overwrite_and_checksum_mismatch(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("safe", encoding="utf-8")
    source.chmod(0o600)
    adapter = local_adapter("owner", "vault", tmp_path / "vault")
    common = dict(source=source, idempotency_key="one", permission_scope="owner-only", retention="7d")
    with pytest.raises(ValueError):
        adapter.upload(artifacts.UploadRequest(object_name="../escape", **common))
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "vault" / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        adapter.upload(artifacts.UploadRequest(object_name="link/file.txt", **common))
    first = adapter.upload(artifacts.UploadRequest(object_name="same.txt", **common))
    other = tmp_path / "other.txt"
    other.write_text("different", encoding="utf-8")
    other.chmod(0o600)
    with pytest.raises(FileExistsError):
        adapter.upload(artifacts.UploadRequest(source=other, object_name="same.txt", idempotency_key="two", permission_scope="owner-only", retention="7d"))
    Path(first.path).write_text("tampered", encoding="utf-8")
    with pytest.raises(artifacts.ChecksumMismatch):
        adapter.readback(first.object_id)


@pytest.mark.parametrize("provider", ["google-drive", "onedrive", "dropbox", "box", "s3-compatible"])
def test_synthetic_provider_contracts_cover_identity_duplicate_unknown_effect_and_reconciliation(tmp_path, provider):
    source = tmp_path / f"{provider}.txt"
    source.write_text("synthetic", encoding="utf-8")
    source.chmod(0o600)
    adapter = synthetic_adapter(provider, "synthetic-account", "synthetic-target",
                                                 journal_path=tmp_path / f"{provider}-operations.json")
    request = artifacts.UploadRequest(source, "proof.txt", "stable-key", "private", "delete-after-test")
    first = adapter.upload(request)
    assert adapter.upload(request) == first
    with pytest.raises(artifacts.IdempotencyConflict):
        changed = artifacts.UploadRequest(source, "other.txt", "stable-key", "private", "delete-after-test")
        adapter.upload(changed)
    uncertain = artifacts.UploadRequest(source, "unknown.txt", "unknown-key", "private", "delete-after-test")
    with pytest.raises(artifacts.UnknownEffect) as effect:
        adapter.upload(uncertain, simulate_unknown_effect=True)
    reconciled = adapter.reconcile_unknown(effect.value.operation_id)
    assert reconciled.provider == provider and reconciled.object_id
    assert reconciled.account_id == "synthetic-account" and reconciled.target_id == "synthetic-target"
    assert reconciled.synthetic is True and reconciled.verified_status == "Optional"
    adapter.revoke(reconciled.object_id)
    adapter.delete(reconciled.object_id)
    adapter.disable()


def test_temporary_share_policy_is_disabled_and_denies_sensitive_or_incomplete_requests(tmp_path):
    public = tmp_path / "demo.pdf"
    public.write_bytes(b"%PDF-1.4\nsynthetic\n%%EOF\n")
    disabled = artifacts.TemporarySharePolicy()
    with pytest.raises(artifacts.ShareDenied):
        disabled.prepare(public, target="reviewer@example.test", auth_policy="signed-token", expires_in=60)
    enabled = artifacts.TemporarySharePolicy(enabled=True)
    for kwargs in [
        dict(target="reviewer@example.test", auth_policy="none", expires_in=60),
        dict(target="", auth_policy="signed-token", expires_in=60),
        dict(target="reviewer@example.test", auth_policy="signed-token", expires_in=0),
        dict(target="reviewer@example.test", auth_policy="signed-token", expires_in=60),
    ]:
        with pytest.raises(artifacts.ShareDenied):
            enabled.prepare(public, **kwargs)
    sensitive = tmp_path / "credentials.pdf"
    sensitive.write_bytes(b"%PDF-1.4\npassword: synthetic-secret\n%%EOF\n")
    with pytest.raises(artifacts.ShareDenied):
        enabled.prepare(sensitive, target="reviewer@example.test", auth_policy="signed-token", expires_in=60)


def test_temporary_share_expiration_revocation_cleanup_and_no_listener(tmp_path):
    path = tmp_path / "demo.csv"
    path.write_text("synthetic,only\n", encoding="utf-8")
    path.chmod(0o600)
    host = "demo.127.0.0.1.nip.io"
    verifier = tls_fixture(b"trusted-test-key", issuer="test-exposure")
    policy = artifacts.TemporarySharePolicy(enabled=True, staging_root=tmp_path / "shares", allowed_hosts={host}, tls_verifier=verifier)
    route = f"https://{host}/token?expires=1"
    receipt = verifier.issue(route=route, audience="reviewer@example.test", auth_policy="signed-token", expires_at=time.time() + 2, tunnel_identity="test-tunnel")
    share = policy.prepare(path, target="reviewer@example.test", auth_policy="signed-token", expires_in=1, route=route, verification_receipt=receipt)
    staged = Path(share["staged_path"])
    assert staged.exists() and share["status"] == "prepared-not-hosted"
    assert share["listener_started"] is False and share["route_kind"] == "allowlisted-https"
    policy.revoke(share["share_id"])
    assert policy.status(share["share_id"])["revoked"] is True
    assert not staged.exists()
    route2 = f"https://{host}/other-token?expires=1"
    receipt2 = verifier.issue(route=route2, audience="reviewer@example.test", auth_policy="signed-token", expires_at=time.time() + 2, tunnel_identity="test-tunnel")
    another = policy.prepare(path, target="reviewer@example.test", auth_policy="signed-token", expires_in=1, route=route2, verification_receipt=receipt2)
    time.sleep(1.05)
    assert policy.status(another["share_id"])["expired"] is True
    assert not Path(another["staged_path"]).exists()


def test_archive_privacy_rejects_artifacts_and_share_staging(tmp_path):
    (tmp_path / "artifact-output").mkdir()
    (tmp_path / "artifact-output" / "private.csv").write_text("private")
    (tmp_path / ".artifact-shares").mkdir()
    assert artifacts.archive_privacy_errors(tmp_path) == [
        "runtime artifact directory must not be archived: .artifact-shares",
        "runtime artifact directory must not be archived: artifact-output",
    ]


def test_storage_contract_schema_example_and_catalog_inventory():
    import jsonschema
    import yaml

    root = Path(__file__).parents[1]
    schema = json.loads((root / "templates" / "artifact-storage-contract.schema.json").read_text())
    example = yaml.safe_load((root / "templates" / "artifact-storage-contract.example.yaml").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(example, schema)
    assert example["status"] == "optional"
    assert example["connected"] is False
    assert set(example["adapters"]) == {
        "local-filesystem", "google-drive", "onedrive", "dropbox", "box", "s3-compatible"
    }
    catalog = yaml.safe_load((root / "capabilities.yaml").read_text())
    pack = catalog["capability_packs"]["artifact-storage"]
    assert "tools/artifact-storage" in pack["included_paths"]
    assert pack["cloud_adapters_status"] == "optional-unverified-synthetic-contracts"
    preflight_spec = importlib.util.spec_from_file_location("artifact_preflight", root / "scripts" / "preflight.py")
    assert preflight_spec and preflight_spec.loader
    preflight = importlib.util.module_from_spec(preflight_spec)
    preflight_spec.loader.exec_module(preflight)
    assert "tools/artifact-storage/artifact_storage.py" in preflight.REQUIRED
    assert "templates/artifact-storage-contract.schema.json" in preflight.REQUIRED
