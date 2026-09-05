import base64
import concurrent.futures
import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import stat
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

TOOL_ROOT = Path(__file__).parents[1] / "tools" / "secure-credentials"
sys.path.insert(0, str(TOOL_ROOT))

from secure_credentials import app as app_module  # noqa: E402
from secure_credentials import crypto, store, vault  # noqa: E402


def master_key_worker(arguments):
    _, path = arguments
    os.environ.pop("SECURE_CREDENTIALS_MASTER_KEY", None)
    return crypto.master_key(path)


def encrypted_payload(public_key_b64, plaintext):
    public = serialization.load_der_public_key(base64.b64decode(public_key_b64))
    assert isinstance(public, rsa.RSAPublicKey)
    aes = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ciphertext = AESGCM(aes).encrypt(iv, plaintext.encode(), None)
    wrapped = public.encrypt(
        aes,
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return tuple(base64.b64encode(item).decode() for item in (ciphertext, iv, wrapped))


def configure(tmp_path, monkeypatch):
    db = tmp_path / "drops.db"
    key = tmp_path / "master.key"
    outbox = tmp_path / "outbox"
    vault_db = tmp_path / "vault.db"
    monkeypatch.setenv("SECURE_CREDENTIALS_MASTER_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SECURE_CREDENTIALS_DROP_DB", str(db))
    monkeypatch.setenv("SECURE_CREDENTIALS_VAULT", str(vault_db))
    monkeypatch.setenv("SECURE_CREDENTIALS_KEY_FILE", str(key))
    monkeypatch.setenv("SECURE_CREDENTIALS_OUTBOX", str(outbox))
    monkeypatch.setenv("SECURE_CREDENTIALS_BASE_URL", "https://credentials.test")
    monkeypatch.delenv("SECURE_CREDENTIALS_PREFIX", raising=False)
    monkeypatch.setenv("SECURE_CREDENTIALS_EXPOSURE", "private")
    return db, vault_db, outbox


def test_readiness_checks_storage_key_https_and_private_exposure(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    importlib.reload(app_module)
    client = TestClient(app_module.create_app())
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "exposure": "private"}

    monkeypatch.setenv("SECURE_CREDENTIALS_BASE_URL", "http://credentials.test")
    importlib.reload(app_module)
    response = TestClient(app_module.create_app()).get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_public_exposure_is_explicitly_unsupported(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    monkeypatch.setenv("SECURE_CREDENTIALS_EXPOSURE", "public")
    importlib.reload(app_module)
    response = TestClient(app_module.create_app()).get("/readyz")
    assert response.status_code == 503
    assert "private" in response.json()["reason"]


def test_bearer_routes_are_rate_limited(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    monkeypatch.setenv("SECURE_CREDENTIALS_RATE_LIMIT", "2")
    importlib.reload(app_module)
    client = TestClient(app_module.create_app())
    drop = store.create_drop(db, "https://credentials.test", 3600)
    assert client.get(f"/d/{drop['sender_token']}").status_code == 200
    assert client.get(f"/d/{drop['sender_token']}").status_code == 200
    limited = client.get(f"/d/{drop['sender_token']}")
    assert limited.status_code == 429
    assert limited.headers["retry-after"]


def test_browser_submit_and_explicit_reveal_once(tmp_path, monkeypatch):
    db, _, outbox = configure(tmp_path, monkeypatch)
    importlib.reload(app_module)
    client = TestClient(app_module.create_app())
    drop = store.create_drop(db, "https://credentials.test", 3600)

    sender = client.get(f"/d/{drop['sender_token']}")
    assert sender.status_code == 200
    assert sender.headers["cache-control"] == "no-store"
    assert "Encrypted in this browser" in sender.text

    ciphertext, iv, wrapped = encrypted_payload(drop["public_key_b64"], "password: example-secret")  # pragma: allowlist secret
    saved = client.post(
        f"/api/drop/{drop['sender_token']}",
        json={"ciphertext": ciphertext, "iv": iv, "wrapped_key": wrapped},
    )
    assert saved.status_code == 200
    assert saved.json()["delivery"] == "delivered"
    retry = client.post(
        f"/api/drop/{drop['sender_token']}",
        json={"ciphertext": ciphertext, "iv": iv, "wrapped_key": wrapped},
    )
    assert retry.status_code == 200
    assert retry.json()["already_submitted"] is True
    assert b"example-secret" not in db.read_bytes()  # pragma: allowlist secret
    assert list(outbox.glob("*.json"))
    assert "example-secret" not in list(outbox.glob("*.json"))[0].read_text()  # pragma: allowlist secret
    con = sqlite3.connect(db)
    assert con.execute("SELECT recipient_token_enc FROM drops").fetchone()[0] is None
    con.close()

    preview = client.get(f"/r/{drop['recipient_token']}")
    assert preview.status_code == 200
    assert "example-secret" not in preview.text  # pragma: allowlist secret
    assert client.get(f"/r/{drop['recipient_token']}").status_code == 200

    revealed = client.post(f"/r/{drop['recipient_token']}")
    assert revealed.status_code == 200
    assert "example-secret" in revealed.text  # pragma: allowlist secret
    assert client.post(f"/r/{drop['recipient_token']}").status_code == 410


def test_concurrent_reveal_has_one_winner(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_submitted_drop(db, "https://credentials.test", "one winner", 3600)

    def reveal(_):
        return store.take_for_recipient(db, drop["recipient_token"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reveal, range(16)))
    assert results.count("one winner") == 1
    assert results.count(None) == 15


def test_concurrent_submission_has_one_winner(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_drop(db, "https://credentials.test", 3600)
    ciphertext, iv, wrapped = encrypted_payload(drop["public_key_b64"], "one submission")

    def submit(_):
        return store.submit_once(db, drop["sender_token"], ciphertext, iv, wrapped)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(16)))
    assert all(item and item["accepted"] for item in results)
    assert sum(not item["already_submitted"] for item in results) == 1
    assert sum(item["already_submitted"] for item in results) == 15


def test_agent_consume_writes_exact_owner_only_file(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_submitted_drop(db, "https://credentials.test", "TOKEN=protected", 3600)
    destination = tmp_path / "provider.env"
    assert store.consume_to_file(db, drop["agent_token"], destination)
    assert destination.read_text() == "TOKEN=protected"
    if os.name != "nt":
        assert oct(destination.stat().st_mode & 0o777) == "0o600"
    assert not store.consume_to_file(db, drop["agent_token"], destination)


def test_exact_agent_claim_can_recover_link_before_outbox_ack(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_drop(db, "https://credentials.test", 3600)
    ciphertext, iv, wrapped = encrypted_payload(drop["public_key_b64"], "recoverable")
    store.submit_once(db, drop["sender_token"], ciphertext, iv, wrapped)
    link = store.recipient_link_for_agent(db, drop["agent_token"], "https://credentials.test")
    assert link == drop["recipient_url"]
    store.clear_recipient_token(db, drop["id"])
    assert store.recipient_link_for_agent(db, drop["agent_token"], "https://credentials.test") is None


def test_vault_encrypts_and_safe_list_omits_secret(tmp_path, monkeypatch):
    _, vault_db, _ = configure(tmp_path, monkeypatch)
    vault.put("service", "https://service.test", "owner", "vault-secret", authorized_principals=["owner"], path=vault_db)  # pragma: allowlist secret
    assert b"vault-secret" not in vault_db.read_bytes()  # pragma: allowlist secret
    assert vault.get_for_operator("service", "owner", path=vault_db)["secret"] == "vault-secret"  # pragma: allowlist secret
    listing = vault.safe_list(vault_db)
    assert len(listing) == 1
    assert "secret" not in listing[0]
    assert "encrypted_secret" not in listing[0]


def test_vault_can_create_submitted_delivery_link(tmp_path, monkeypatch):
    db, vault_db, _ = configure(tmp_path, monkeypatch)
    vault.put("service", "https://service.test", "owner", "deliver-me", authorized_principals=["owner"], authorized_recipients=["owner"], path=vault_db)
    item = vault.get_for_operator("service", "owner", path=vault_db)
    payload = f"Service: {item['service']}\nURL: {item['url']}\nLogin: {item['login']}\nSecret: {item['secret']}"
    drop = store.create_submitted_drop(db, "https://credentials.test", payload, 3600)
    assert drop["recipient_url"].startswith("https://credentials.test/r/")
    assert b"deliver-me" not in db.read_bytes()
    result = store.take_for_recipient(db, drop["recipient_token"])
    assert result is not None
    assert "deliver-me" in result


def test_vault_rejects_wrong_recipient(tmp_path, monkeypatch):
    _, vault_db, _ = configure(tmp_path, monkeypatch)
    vault.put(
        "service", "https://service.test", "owner", "vault-secret",  # pragma: allowlist secret
        authorized_principals=["owner"], authorized_recipients=["finance"], path=vault_db,
    )
    try:
        vault.get_for_operator("service", "intruder", path=vault_db)
    except PermissionError:
        pass
    else:
        raise AssertionError("unauthorized recipient should fail")


def test_operator_vault_access_does_not_trust_caller_principal(tmp_path, monkeypatch):
    _, vault_db, _ = configure(tmp_path, monkeypatch)
    vault.put(
        "service", "https://service.test", "owner", "vault-secret",  # pragma: allowlist secret
        authorized_principals=["legacy-label"], authorized_recipients=["finance"], path=vault_db,
    )
    item = vault.get_for_operator("service", "finance", path=vault_db)
    assert item["secret"] == "vault-secret"  # pragma: allowlist secret
    try:
        vault.get_for_operator("service", "intruder", path=vault_db)
    except PermissionError:
        pass
    else:
        raise AssertionError("recipient policy should still fail closed")


def test_secure_credentials_has_standalone_package_and_bootstrap():
    pyproject = (TOOL_ROOT / "pyproject.toml").read_text()
    assert "secure-credentials" in pyproject
    assert (TOOL_ROOT / "bootstrap.py").is_file()
    assert (TOOL_ROOT / "secure_credentials" / "static" / "crypto.js").is_file()


def test_expired_drop_is_deleted(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_drop(db, "https://credentials.test", 60)
    con = sqlite3.connect(db)
    con.execute("UPDATE drops SET expires_at=0 WHERE id=?", (drop["id"],))
    con.commit(); con.close()
    assert store.sender_record(db, drop["sender_token"]) is None
    assert store.cleanup_expired(db) == 1
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM drops").fetchone()[0] == 0
    con.close()


def test_cleanup_removes_expired_outbox_capability(tmp_path, monkeypatch):
    db, _, outbox = configure(tmp_path, monkeypatch)
    drop = store.create_drop(db, "https://credentials.test", 60)
    con = sqlite3.connect(db)
    con.execute("UPDATE drops SET expires_at=0 WHERE id=?", (drop["id"],))
    con.commit(); con.close()
    outbox.mkdir(mode=0o700)
    record = outbox / f"{drop['id']}.json"
    record.write_text(json.dumps({"recipient_url": drop["recipient_url"]}))
    assert record.exists()
    assert store.cleanup_expired(db, outbox) == 1
    assert not record.exists()


def test_http_body_limit_rejects_large_request(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    importlib.reload(app_module)
    client = TestClient(app_module.create_app())
    response = client.post("/api/drop/unknown", content=b"x" * 100001, headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_corrupt_payload_does_not_consume_drop(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_submitted_drop(db, "https://credentials.test", "protected", 3600)
    con = sqlite3.connect(db)
    con.execute("UPDATE drops SET ciphertext='not-base64' WHERE id=?", (drop["id"],))
    con.commit(); con.close()
    try:
        store.take_for_recipient(db, drop["recipient_token"])
    except Exception:
        pass
    else:
        raise AssertionError("corrupt ciphertext should fail")
    con = sqlite3.connect(db)
    assert con.execute("SELECT state FROM drops WHERE id=?", (drop["id"],)).fetchone()[0] == "submitted"
    con.close()


def test_claim_recovery_finalizes_file_delivered_before_crash(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_submitted_drop(db, "https://credentials.test", "recover-after-crash", 3600)
    destination = tmp_path / "secret.env"

    def crash():
        raise RuntimeError("simulated crash boundary")

    try:
        store.consume_to_file(db, drop["agent_token"], destination, after_delivery=crash)
    except RuntimeError:
        pass
    else:
        raise AssertionError("fault injection should raise")
    assert destination.read_text() == "recover-after-crash"
    assert store.recover_claims(db, stale_after=0) == {"finalized": 1, "released": 0}
    assert not store.consume_to_file(db, drop["agent_token"], tmp_path / "second.env")


def test_symlink_destination_is_rejected_without_consumption(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    drop = store.create_submitted_drop(db, "https://credentials.test", "stay-safe", 3600)
    real = tmp_path / "real"
    real.write_text("existing")
    link = tmp_path / "link"
    link.symlink_to(real)
    try:
        store.consume_to_file(db, drop["agent_token"], link)
    except PermissionError:
        pass
    else:
        raise AssertionError("symlink should fail")
    assert store.take_for_recipient(db, drop["recipient_token"]) == "stay-safe"


def test_master_key_and_parent_are_private_under_hostile_umask(tmp_path, monkeypatch):
    monkeypatch.delenv("SECURE_CREDENTIALS_MASTER_KEY", raising=False)
    path = tmp_path / "private" / "master.key"
    old = os.umask(0)
    try:
        key = crypto.master_key(path)
    finally:
        os.umask(old)
    assert key
    if os.name == "posix":
        assert oct(path.parent.stat().st_mode & 0o777) == "0o700"
        assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_master_key_refuses_symlink(tmp_path, monkeypatch):
    monkeypatch.delenv("SECURE_CREDENTIALS_MASTER_KEY", raising=False)
    target = tmp_path / "target"
    target.write_text("not-a-key")
    link = tmp_path / "link.key"
    link.symlink_to(target)
    try:
        crypto.master_key(link)
    except PermissionError:
        pass
    else:
        raise AssertionError("symlink key should fail")


def test_master_key_concurrent_first_use_returns_one_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SECURE_CREDENTIALS_MASTER_KEY", raising=False)
    path = tmp_path / "private" / "master.key"

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        keys = list(pool.map(lambda _: crypto.master_key(path), range(24)))

    assert len(set(keys)) == 1
    assert Fernet(keys[0])


def test_master_key_concurrent_process_first_use_returns_one_key(tmp_path, monkeypatch):
    if os.name != "posix":
        import pytest
        pytest.skip("POSIX key policy")
    monkeypatch.delenv("SECURE_CREDENTIALS_MASTER_KEY", raising=False)
    path = tmp_path / "process-private" / "master.key"
    arguments = [(str(TOOL_ROOT), str(path)) for _ in range(16)]

    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(master_key_worker, arguments))

    assert len(set(keys)) == 1


def test_master_key_refuses_hard_linked_file(tmp_path, monkeypatch):
    if os.name != "posix":
        import pytest
        pytest.skip("hard-link policy is POSIX specific")
    monkeypatch.delenv("SECURE_CREDENTIALS_MASTER_KEY", raising=False)
    path = tmp_path / "private" / "master.key"
    crypto.master_key(path)
    alias = tmp_path / "master.alias"
    os.link(path, alias)

    try:
        crypto.master_key(path)
    except PermissionError:
        pass
    else:
        raise AssertionError("hard-linked key should fail")


def test_browser_webcrypto_payload_decrypts_in_python(tmp_path, monkeypatch):
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("Node.js is not installed")
    configure(tmp_path, monkeypatch)
    public, private_enc = crypto.generate_drop_keys()
    runner = Path(__file__).with_name("browser_crypto_runner.js")
    script = TOOL_ROOT / "secure_credentials" / "static" / "crypto.js"
    result = subprocess.run([node, str(runner), str(script), public, "browser-secret"], capture_output=True, text=True, timeout=30)  # pragma: allowlist secret
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert crypto.decrypt_payload(private_enc, payload["wrapped_key"], payload["iv"], payload["ciphertext"]) == "browser-secret"  # pragma: allowlist secret


def test_browser_successful_submission_clears_plaintext_and_replaces_panel(tmp_path, monkeypatch):
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("Node.js is not installed")
    configure(tmp_path, monkeypatch)
    public, _ = crypto.generate_drop_keys()
    runner = Path(__file__).with_name("browser_submit_runner.js")
    script = TOOL_ROOT / "secure_credentials" / "static" / "crypto.js"
    result = subprocess.run([node, str(runner), str(script), public], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["textarea"] == ""
    assert "Saved securely" in output["panel"]
    assert "browser-fixture-value" not in output["panel"]
    assert output["disabled"] is True


def test_outbox_failure_keeps_submission_recoverable(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    importlib.reload(app_module)
    monkeypatch.setattr(app_module, "flush_delivery_outbox", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk")))
    client = TestClient(app_module.create_app())
    drop = store.create_drop(db, "https://credentials.test", 3600)
    ciphertext, iv, wrapped = encrypted_payload(drop["public_key_b64"], "outbox-secret")  # pragma: allowlist secret
    response = client.post(
        f"/api/drop/{drop['sender_token']}",
        json={"ciphertext": ciphertext, "iv": iv, "wrapped_key": wrapped},
    )
    assert response.status_code == 200
    assert response.json()["delivery"] == "queued"
    assert store.recipient_link_for_agent(db, drop["agent_token"], "https://credentials.test") == drop["recipient_url"]


def test_documented_environment_paths_are_defaults(tmp_path, monkeypatch):
    key = tmp_path / "configured.key"
    vault_db = tmp_path / "configured-vault.db"
    monkeypatch.setenv("SECURE_CREDENTIALS_KEY_FILE", str(key))
    monkeypatch.setenv("SECURE_CREDENTIALS_VAULT", str(vault_db))
    assert crypto.default_key_path() == key
    assert vault.default_vault_path() == vault_db


def test_sender_page_has_replaceable_panel_and_script_clears_plaintext(tmp_path, monkeypatch):
    db, _, _ = configure(tmp_path, monkeypatch)
    importlib.reload(app_module)
    drop = store.create_drop(db, "https://credentials.test", 3600)
    response = TestClient(app_module.create_app()).get(f"/d/{drop['sender_token']}")
    script = (TOOL_ROOT / "secure_credentials" / "static" / "crypto.js").read_text()
    assert 'class="panel-inner"' in response.text
    assert "textarea.value = '';" in script


def test_existing_unsafe_database_is_rejected_before_sqlite_mutates_it(tmp_path, monkeypatch):
    if os.name != "posix":
        import pytest
        pytest.skip("POSIX ownership and mode policy")
    configure(tmp_path, monkeypatch)
    db = tmp_path / "unsafe.db"
    db.write_bytes(b"not sqlite")
    db.chmod(0o644)
    before = db.read_bytes()
    try:
        store.connect(db)
    except PermissionError:
        pass
    else:
        raise AssertionError("unsafe database should be rejected")
    assert db.read_bytes() == before
    assert stat.S_IMODE(db.stat().st_mode) == 0o644


def test_initial_drop_schema_and_version_are_atomic(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    db = tmp_path / "atomic.db"
    monkeypatch.setattr(store, "SCHEMA", store.SCHEMA + "\nTHIS IS NOT SQL;")
    try:
        store.connect(db)
    except sqlite3.Error:
        pass
    else:
        raise AssertionError("faulted migration should fail")
    con = sqlite3.connect(db)
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0
        assert con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    finally:
        con.close()


def test_initial_vault_schema_and_version_are_atomic(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    db = tmp_path / "atomic-vault.db"
    monkeypatch.setattr(vault, "SCHEMA", vault.SCHEMA + "\nTHIS IS NOT SQL;")
    try:
        vault.connect(db)
    except sqlite3.Error:
        pass
    else:
        raise AssertionError("faulted migration should fail")
    con = sqlite3.connect(db)
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0
        assert con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    finally:
        con.close()
