import importlib.util
import hashlib
import os
import zipfile
import json
import re
import stat
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import pytest

MODULE_PATH = Path(__file__).parents[1] / "tools" / "artifact-storage" / "artifact_storage.py"
SPEC = importlib.util.spec_from_file_location("artifact_storage_hardening", MODULE_PATH)
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


def _public(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)



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

UNICODE = {
    "title": "Résumé — تقرير 📈",
    "columns": ["Région", "قيمة"],
    "rows": [["Zürich", "مرحباً"], ["東京", 7]],
    "paragraphs": ["Exact Unicode: café naïve ✓"],
}


def test_consumers_are_verifier_only_and_reject_caller_authority(tmp_path):
    trusted_key = Ed25519PrivateKey.generate()
    attacker_key = Ed25519PrivateKey.generate()
    route = "https://share.example.test/token?auth=abc&expires=60"
    probes = {"probe": {"url": route, "host": "share.example.test", "audience": "reviewer@example.test",
                        "auth_policy": "signed-token", "certificate_identity": "sha256:trusted-cert",
                        "tunnel_identity": None, "collected_at": time.time(), "expires_at": time.time() + 61,
                        "revoked": False}}
    verifier = artifacts.TLSReceiptVerifier(_public(trusted_key), issuer="approved-exposure")
    authority = artifacts.TLSProbeAuthority(trusted_key, issuer="approved-exposure", trusted_probe_resolver=probes.__getitem__)
    policy = artifacts.TemporarySharePolicy(enabled=True, staging_root=tmp_path / "shares",
                                            allowed_hosts={"share.example.test"}, tls_verifier=verifier)
    assert not hasattr(verifier, "issue") and not hasattr(policy, "tls_verifier")
    forged_authority = artifacts.TLSProbeAuthority(attacker_key, issuer="approved-exposure",
                                                   trusted_probe_resolver=probes.__getitem__)
    source = tmp_path / "safe.csv"
    source.write_text("safe,data\n")
    source.chmod(0o600)
    common = dict(target="reviewer@example.test", auth_policy="signed-token", expires_in=60, route=route)
    with pytest.raises(artifacts.ShareDenied, match="signature"):
        policy.prepare(source, verification_receipt=forged_authority.issue("probe"), **common)
    receipt = authority.issue("probe")
    tampered = dict(receipt)
    tampered["certificate_identity"] = "sha256:arbitrary-cert"
    with pytest.raises(artifacts.ShareDenied, match="signature"):
        policy.prepare(source, verification_receipt=tampered, **common)

    object_id = hashlib.sha256(b"target/proof.txt").hexdigest()[:24]
    decisions = {"upload": {"object_id": object_id, "permission_scope": "owner-only", "retention": "7d"}}
    provider = artifacts.ProtectedPolicyResolver(tmp_path / "policies.json", _public(trusted_key), issuer="storage")
    storage_authority = artifacts.StoragePolicyAuthority(trusted_key, provider.state_path, issuer="storage",
                                                         trusted_policy_resolver=decisions.__getitem__)
    storage_authority.issue("upload")
    assert not hasattr(provider, "set")
    adapter = artifacts.LocalFilesystemAdapter("owner", "target", tmp_path / "vault", policy_provider=provider)
    assert not hasattr(adapter, "policy_authority")
    stored = adapter.upload(artifacts.UploadRequest(source, "proof.txt", "upload", "owner-only", "7d"))
    adapter._records[object_id] = stored._replace(permission_scope="public", retention="forever")
    adapter._policies[object_id] = ("public", "forever")
    forged_decisions = {"upload": {"object_id": object_id, "permission_scope": "public", "retention": "forever"}}
    forged_authority = artifacts.StoragePolicyAuthority(attacker_key, provider.state_path, issuer="storage",
                                                        trusted_policy_resolver=forged_decisions.__getitem__)
    with pytest.raises(artifacts.ChecksumMismatch, match="existing authoritative policy signature"):
        forged_authority.issue("upload")
    with pytest.raises(artifacts.ChecksumMismatch, match="authoritative policy"):
        adapter.readback(object_id)


def test_real_formats_reject_spoofed_truncated_and_malformed_packages(tmp_path):
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4\nxref\n%%EOF\n")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.inspect_artifact(bad_pdf, "pdf")

    for kind, required in (("xlsx", "xl/worksheets/sheet1.xml"), ("docx", "word/document.xml")):
        bad = tmp_path / f"bad.{kind}"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("[Content_Types].xml", "<broken")
            archive.writestr(required, "<broken")
        with pytest.raises(artifacts.ArtifactError):
            artifacts.inspect_artifact(bad, kind)

    spoof = tmp_path / "spoof.xlsx"
    spoof.write_bytes(b"PK not really a zip")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.inspect_artifact(spoof, "xlsx")


def test_unicode_generation_reopens_with_exact_text_and_sizes(tmp_path):
    records = artifacts.generate_artifacts(UNICODE, tmp_path / "out")
    expected = [UNICODE["title"], *UNICODE["paragraphs"], *UNICODE["columns"],
                *[str(cell) for row in UNICODE["rows"] for cell in row]]
    for record in records:
        assert record["size"] == Path(record["path"]).stat().st_size > 0
        assert all(value in record["content"] for value in expected)


def test_sources_and_roots_reject_links_and_symlinked_parent_components(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("safe", encoding="utf-8")
    hardlink = tmp_path / "hard.txt"
    os.link(source, hardlink)
    adapter = local_adapter("owner", "target", tmp_path / "vault")
    request = artifacts.UploadRequest(hardlink, "hard.txt", "hard", "owner-only", "delete-after-7d")
    with pytest.raises(ValueError, match="link"):
        adapter.upload(request)

    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        local_adapter("owner", "target", alias / "vault")
    with pytest.raises(artifacts.ShareDenied):
        artifacts.TemporarySharePolicy(enabled=True, staging_root=alias / "shares", allowed_hosts={"share.example.test"})


def test_unknown_effect_blocks_blind_retry_until_reconciliation_and_binds_context(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    source.chmod(0o600)
    adapter = synthetic_adapter("box", "acct", "target", journal_path=tmp_path / "operations.json")
    request = artifacts.UploadRequest(source, "proof.txt", "key", "private", "delete-after-test")
    with pytest.raises(artifacts.UnknownEffect) as effect:
        adapter.upload(request, simulate_unknown_effect=True)
    with pytest.raises(artifacts.UnknownEffect):
        adapter.upload(request)
    record = adapter.reconcile_unknown(effect.value.operation_id)
    assert record.size == source.stat().st_size
    assert adapter.upload(request) == record
    other = synthetic_adapter("box", "other-account", "target", journal_path=tmp_path / "other-operations.json")
    assert other.operation_key(request) != adapter.operation_key(request)


def test_policy_is_nonempty_independently_read_back_and_size_verified(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    source.chmod(0o600)
    adapter = local_adapter("owner", "target", tmp_path / "vault")
    for permission, retention in (("", "7d"), ("private", "")):
        with pytest.raises(ValueError, match="policy"):
            adapter.upload(artifacts.UploadRequest(source, "x.txt", permission + retention, permission, retention))
    record = adapter.upload(artifacts.UploadRequest(source, "ok.txt", "ok", "owner-only", "delete-after-7d"))
    assert adapter.readback(record.object_id).size == len(b"payload")
    Path(record.path).write_bytes(b"payload-longer")
    with pytest.raises(artifacts.ChecksumMismatch):
        adapter.readback(record.object_id)


def test_sensitive_scan_covers_entire_bounded_artifact(tmp_path):
    source = tmp_path / "late.txt"
    source.write_bytes(b"x" * (1024 * 1024 + 5) + b"\npassword=late-secret")
    source.chmod(0o600)
    verifier = tls_fixture(b"trusted-test-key", issuer="test-exposure")
    route = "https://share.example.test/token"
    receipt = verifier.issue(route=route, audience="reviewer@example.test", auth_policy="signed-token",
                             expires_at=time.time() + 61, certificate_identity="test-cert")
    policy = artifacts.TemporarySharePolicy(enabled=True, staging_root=tmp_path / "shares",
                                            allowed_hosts={"share.example.test"}, tls_verifier=verifier)
    with pytest.raises(artifacts.ShareDenied, match="sensitive"):
        policy.prepare(source, target="reviewer@example.test", auth_policy="signed-token", expires_in=60,
                       route=route, verification_receipt=receipt)


def test_share_url_is_parsed_and_must_be_https_allowlisted_and_authenticated(tmp_path):
    source = tmp_path / "safe.csv"
    source.write_text("safe,data\n", encoding="utf-8")
    source.chmod(0o600)
    verifier = tls_fixture(b"trusted-test-key", issuer="test-exposure")
    policy = artifacts.TemporarySharePolicy(enabled=True, staging_root=tmp_path / "shares",
                                            allowed_hosts={"share.example.test"}, tls_verifier=verifier)
    common = dict(target="reviewer@example.test", auth_policy="signed-token", expires_in=60)
    for route in ("http://share.example.test/token", "https://evil.example/token", "https://share.example.test/"):
        with pytest.raises(artifacts.ShareDenied):
            policy.prepare(source, route=route, verification_receipt={}, **common)
    route = "https://share.example.test/token?auth=abc&expires=60"
    receipt = verifier.issue(route=route, audience=common["target"], auth_policy=common["auth_policy"],
                             expires_at=time.time() + 61, certificate_identity="test-cert")
    share = policy.prepare(source, route=route, verification_receipt=receipt, **common)
    assert share["route"].startswith("https://") and share["https_verified"] is True
    policy.revoke(share["share_id"])
    assert policy.status(share["share_id"])["revoked"] is True


def test_preview_detects_mime_instead_of_trusting_caller(tmp_path):
    records = artifacts.generate_artifacts(UNICODE, tmp_path / "out")
    pdf = Path(next(item["path"] for item in records if item["format"] == "pdf"))
    with pytest.raises(ValueError, match="MIME"):
        artifacts.local_preview(pdf, "text/plain")
    assert artifacts.local_preview(pdf, "application/pdf")["size"] == pdf.stat().st_size


def test_storage_contract_declares_size_and_bound_unknown_operation_key():
    root = Path(__file__).parents[1]
    schema = json.loads((root / "templates" / "artifact-storage-contract.schema.json").read_text())
    required = schema["$defs"]["adapter"]["required"]
    assert "size_readback" in required
    assert "bound_operation_key" in required


def test_xlsx_requires_nonempty_sheets_and_resolved_worksheet_relationship(tmp_path):
    path = Path(next(r["path"] for r in artifacts.generate_artifacts(UNICODE, tmp_path / "out") if r["format"] == "xlsx"))
    broken = tmp_path / "no-sheets.xlsx"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(broken, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/workbook.xml":
                data = re.sub(b"<sheets>.*?</sheets>", b"<sheets/>", data)
            target.writestr(item, data)
    with pytest.raises(artifacts.ArtifactError):
        artifacts.inspect_artifact(broken, "xlsx")


@pytest.mark.parametrize("replacement", [b"<w:fake><w:t>forged</w:t></w:fake>", b""])
def test_docx_requires_body_and_wordprocessing_text_structure(tmp_path, replacement):
    path = Path(next(r["path"] for r in artifacts.generate_artifacts(UNICODE, tmp_path / "out") if r["format"] == "docx"))
    broken = tmp_path / "no-body.docx"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(broken, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                data = re.sub(b"<w:body>.*</w:body>", replacement, data)
            target.writestr(item, data)
    with pytest.raises(artifacts.ArtifactError):
        artifacts.inspect_artifact(broken, "docx")


def test_pdf_rejects_faux_font_resource_and_invalid_referenced_object_types(tmp_path):
    path = Path(next(r["path"] for r in artifacts.generate_artifacts(UNICODE, tmp_path / "out") if r["format"] == "pdf"))
    raw = path.read_bytes()
    broken = tmp_path / "faux-font.pdf"
    broken.write_bytes(raw.replace(b"/Type /Font", b"/Type /Faux", 1))
    with pytest.raises(artifacts.ArtifactError):
        artifacts.inspect_artifact(broken, "pdf")


def test_upload_share_and_preview_reject_group_or_other_accessible_sources(tmp_path):
    source = tmp_path / "public.csv"
    source.write_text("safe,data\n", encoding="utf-8")
    source.chmod(0o666)
    adapter = local_adapter("owner", "target", tmp_path / "vault")
    request = artifacts.UploadRequest(source, "public.csv", "mode-key", "owner-only", "7d")
    with pytest.raises(ValueError, match="mode"):
        adapter.upload(request)
    policy = artifacts.TemporarySharePolicy(enabled=True, staging_root=tmp_path / "shares", allowed_hosts={"share.example.test"})
    with pytest.raises(artifacts.ShareDenied):
        policy.prepare(source, target="reviewer@example.test", auth_policy="signed-token", expires_in=60,
                       route="https://share.example.test/token", verification_receipt={"https_verified": True})
    with pytest.raises(ValueError, match="mode"):
        artifacts.local_preview(source, "text/csv")


def test_unknown_effect_and_idempotency_survive_adapter_restart(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    source.chmod(0o600)
    journal = tmp_path / "state" / "operations.json"
    request = artifacts.UploadRequest(source, "proof.txt", "durable-key", "private", "7d")
    first = synthetic_adapter("box", "acct", "target", journal_path=journal)
    with pytest.raises(artifacts.UnknownEffect) as effect:
        first.upload(request, simulate_unknown_effect=True)
    restarted = synthetic_adapter("box", "acct", "target", journal_path=journal)
    with pytest.raises(artifacts.UnknownEffect) as repeated:
        restarted.upload(request)
    assert repeated.value.operation_id == effect.value.operation_id
    record = restarted.reconcile_unknown(effect.value.operation_id)
    again = synthetic_adapter("box", "acct", "target", journal_path=journal)
    assert again.upload(request) == record
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600


def test_tampered_record_and_policy_caches_cannot_forge_policy_readback(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    source.chmod(0o600)
    adapter = local_adapter("owner", "target", tmp_path / "vault")
    record = adapter.upload(artifacts.UploadRequest(source, "proof.txt", "key", "owner-only", "7d"))
    adapter._records[record.object_id] = record._replace(permission_scope="public", retention="forever")
    adapter._policies[record.object_id] = ("public", "forever")
    with pytest.raises(artifacts.ChecksumMismatch, match="authoritative policy"):
        adapter.readback(record.object_id)


def test_temporary_share_requires_trusted_url_audience_and_tls_receipt(tmp_path):
    source = tmp_path / "safe.csv"
    source.write_text("safe,data\n", encoding="utf-8")
    source.chmod(0o600)
    verifier = tls_fixture(b"trusted-test-key", issuer="approved-exposure")
    policy = artifacts.TemporarySharePolicy(enabled=True, staging_root=tmp_path / "shares",
                                            allowed_hosts={"share.example.test"}, tls_verifier=verifier)
    route = "https://share.example.test/token?auth=abc&expires=60"
    with pytest.raises(artifacts.ShareDenied):
        policy.prepare(source, target="reviewer@example.test", auth_policy="signed-token", expires_in=60,
                       route=route, verification_receipt={"https_verified": True})
    receipt = verifier.issue(route=route, audience="reviewer@example.test", auth_policy="signed-token",
                             certificate_identity="sha256:certificate", expires_at=time.time() + 60)
    forged = dict(receipt)
    forged["audience"] = "attacker@example.test"
    with pytest.raises(artifacts.ShareDenied):
        policy.prepare(source, target="reviewer@example.test", auth_policy="signed-token", expires_in=60,
                       route=route, verification_receipt=forged)
    share = policy.prepare(source, target="reviewer@example.test", auth_policy="signed-token", expires_in=60,
                           route=route, verification_receipt=receipt)
    assert share["verification_issuer"] == "approved-exposure"
