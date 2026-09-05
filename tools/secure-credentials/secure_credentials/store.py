"""Atomic one-time drop storage and delivery state."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from .crypto import (
    decrypt_payload,
    encrypt_for_public_key,
    ensure_private_directory,
    ensure_private_file,
    fernet,
    fsync_directory,
    generate_drop_keys,
    validate_sensitive_sqlite_path,
)

MAX_TTL = 7 * 24 * 60 * 60
MAX_PLAINTEXT = 65536
TOKEN_FIELDS = {"sender_hash", "recipient_hash", "agent_hash"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS drops (
    id TEXT PRIMARY KEY,
    sender_hash TEXT UNIQUE NOT NULL,
    recipient_hash TEXT UNIQUE NOT NULL,
    agent_hash TEXT UNIQUE NOT NULL,
    recipient_token_enc BLOB,
    public_key_b64 TEXT NOT NULL,
    private_key_enc BLOB NOT NULL,
    ciphertext TEXT,
    iv TEXT,
    wrapped_key TEXT,
    state TEXT NOT NULL CHECK(state IN ('open','submitted','claimed','consumed','revoked')),
    created_at INTEGER NOT NULL,
    submitted_at INTEGER,
    expires_at INTEGER NOT NULL,
    claim_id TEXT,
    claimed_at INTEGER,
    claim_destination TEXT,
    payload_hash TEXT
);
CREATE TABLE IF NOT EXISTS delivery_outbox (
    drop_id TEXT PRIMARY KEY REFERENCES drops(id) ON DELETE CASCADE,
    recipient_url_enc BLOB NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('queued','delivered')),
    created_at INTEGER NOT NULL,
    delivered_at INTEGER
);
"""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _secure_db_family(path: Path) -> None:
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if candidate.exists():
            ensure_private_file(candidate)


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = validate_sensitive_sqlite_path(db_path)
    old_umask = os.umask(0o077) if os.name == "posix" else None
    try:
        con = sqlite3.connect(path, timeout=10, isolation_level=None)
    finally:
        if old_umask is not None:
            os.umask(old_umask)
    con.row_factory = sqlite3.Row
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        existing = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drops'").fetchone()
        if version == 0 and existing:
            raise RuntimeError("unversioned drop database requires explicit migration")
        if version not in {0, 1}:
            raise RuntimeError(f"unsupported drop database schema version: {version}")
        if version == 0:
            try:
                con.executescript(f"BEGIN IMMEDIATE;\n{SCHEMA}\nPRAGMA user_version=1;\nCOMMIT;")
            except Exception:
                _rollback_quietly(con)
                raise
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        _secure_db_family(path)
        return con
    except Exception:
        con.close()
        raise


def _rollback_quietly(con: sqlite3.Connection) -> None:
    try:
        con.execute("ROLLBACK")
    except sqlite3.Error:
        return


def _validate_ttl(ttl_seconds: int) -> None:
    if not 60 <= int(ttl_seconds) <= MAX_TTL:
        raise ValueError(f"TTL must be between 60 and {MAX_TTL} seconds")


def create_drop(db_path, base_url, ttl_seconds=3600, key_path=None) -> dict:
    _validate_ttl(ttl_seconds)
    sender = secrets.token_urlsafe(32)
    recipient = secrets.token_urlsafe(32)
    agent = secrets.token_urlsafe(32)
    public, private_enc = generate_drop_keys(key_path)
    stamp = int(time.time())
    drop_id = str(uuid.uuid4())
    con = connect(db_path)
    try:
        con.execute(
            """INSERT INTO drops(
               id,sender_hash,recipient_hash,agent_hash,recipient_token_enc,
               public_key_b64,private_key_enc,state,created_at,expires_at)
               VALUES(?,?,?,?,?,?,?,'open',?,?)""",
            (drop_id, token_hash(sender), token_hash(recipient), token_hash(agent),
             fernet(key_path).encrypt(recipient.encode()), public, private_enc,
             stamp, stamp + int(ttl_seconds)),
        )
    finally:
        con.close()
    base = base_url.rstrip("/")
    return {
        "id": drop_id,
        "sender_token": sender,
        "recipient_token": recipient,
        "agent_token": agent,
        "sender_url": f"{base}/d/{sender}",
        "recipient_url": f"{base}/r/{recipient}",
        "public_key_b64": public,
    }


def create_submitted_drop(db_path, base_url, plaintext, ttl_seconds=3600, key_path=None) -> dict:
    drop = create_drop(db_path, base_url, ttl_seconds, key_path)
    ciphertext, iv, wrapped = encrypt_for_public_key(drop["public_key_b64"], plaintext)
    saved = submit_once(db_path, drop["sender_token"], ciphertext, iv, wrapped, key_path)
    if not saved:
        raise RuntimeError("drop submission failed")
    clear_recipient_token(db_path, drop["id"])
    return drop


def _lookup(db_path, field, token, allowed_states):
    if field not in TOKEN_FIELDS:
        raise ValueError("invalid token field")
    con = connect(db_path)
    try:
        row = con.execute(f"SELECT * FROM drops WHERE {field}=?", (token_hash(token),)).fetchone()  # nosec B608
        if not row:
            return None
        if row["expires_at"] <= int(time.time()):
            return None
        if row["state"] not in allowed_states:
            return None
        return dict(row)
    finally:
        con.close()


def sender_record(db_path, token):
    return _lookup(db_path, "sender_hash", token, {"open"})


def recipient_record(db_path, token):
    return _lookup(db_path, "recipient_hash", token, {"submitted"})


def _validated_parts(ciphertext, iv, wrapped_key):
    parts = {}
    for name, value, max_encoded in (
        ("ciphertext", ciphertext, 90000), ("iv", iv, 32), ("wrapped_key", wrapped_key, 1024)
    ):
        if not isinstance(value, str) or len(value) > max_encoded:
            raise ValueError(f"invalid {name}")
        parts[name] = base64.b64decode(value, validate=True)
    if len(parts["iv"]) != 12 or len(parts["ciphertext"]) > MAX_PLAINTEXT + 16:
        raise ValueError("invalid encrypted payload dimensions")
    if not 128 <= len(parts["wrapped_key"]) <= 512:
        raise ValueError("invalid wrapped key")


def submit_once(db_path, sender_token, ciphertext, iv, wrapped_key, key_path=None, base_url=None):
    _validated_parts(ciphertext, iv, wrapped_key)
    stamp = int(time.time())
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM drops WHERE sender_hash=?", (token_hash(sender_token),)).fetchone()
        if not row or row["expires_at"] <= stamp:
            con.execute("ROLLBACK")
            return None
        if row["state"] in {"submitted", "claimed"}:
            con.execute("COMMIT")
            return {"id": row["id"], "accepted": True, "already_submitted": True}
        if row["state"] != "open":
            con.execute("ROLLBACK")
            return None

        # Validate the complete cryptographic payload before making submission final.
        plaintext = decrypt_payload(row["private_key_enc"], wrapped_key, iv, ciphertext, key_path)
        if len(plaintext.encode()) > MAX_PLAINTEXT:
            raise ValueError("plaintext is too large")
        del plaintext

        con.execute(
            """UPDATE drops SET ciphertext=?,iv=?,wrapped_key=?,state='submitted',submitted_at=?
               WHERE id=? AND state='open'""",
            (ciphertext, iv, wrapped_key, stamp, row["id"]),
        )
        recipient_token = fernet(key_path).decrypt(row["recipient_token_enc"]).decode()
        if base_url:
            link = f"{base_url.rstrip('/')}/r/{recipient_token}"
            con.execute(
                """INSERT INTO delivery_outbox(drop_id,recipient_url_enc,state,created_at)
                   VALUES(?,?,'queued',?)""",
                (row["id"], fernet(key_path).encrypt(link.encode()), stamp),
            )
        con.execute("COMMIT")
        return {
            "id": row["id"], "accepted": True, "already_submitted": False,
            "recipient_token": recipient_token if not base_url else None,
        }
    except Exception:
        _rollback_quietly(con)
        raise
    finally:
        con.close()


def _atomic_private_text(path: Path, text: str, overwrite=True) -> None:
    ensure_private_directory(path.parent)
    if path.is_symlink():
        raise PermissionError(f"refusing symlink destination: {path}")
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    tmp = Path(tmp_name)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)
            tmp.unlink()
        ensure_private_file(path)
        fsync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def write_private_json(path, data, overwrite=False):
    _atomic_private_text(Path(path), json.dumps(data, indent=2, sort_keys=True) + "\n", overwrite=overwrite)


def flush_delivery_outbox(db_path, outbox_dir, key_path=None) -> list[Path]:
    outbox = ensure_private_directory(outbox_dir)
    con = connect(db_path)
    written = []
    try:
        rows = con.execute("SELECT * FROM delivery_outbox WHERE state='queued' ORDER BY created_at").fetchall()
        for row in rows:
            url = fernet(key_path).decrypt(row["recipient_url_enc"]).decode()
            destination = outbox / f"{row['drop_id']}.json"
            _atomic_private_text(destination, json.dumps({"drop_id": row["drop_id"], "recipient_url": url}) + "\n")
            con.execute("BEGIN IMMEDIATE")
            current = con.execute("SELECT state FROM delivery_outbox WHERE drop_id=?", (row["drop_id"],)).fetchone()
            if current and current["state"] == "queued":
                con.execute(
                    "UPDATE delivery_outbox SET state='delivered',recipient_url_enc=?,delivered_at=? WHERE drop_id=?",
                    (fernet(key_path).encrypt(b"delivered"), int(time.time()), row["drop_id"]),
                )
                con.execute("UPDATE drops SET recipient_token_enc=NULL WHERE id=?", (row["drop_id"],))
            con.execute("COMMIT")
            written.append(destination)
        return written
    except Exception:
        _rollback_quietly(con)
        raise
    finally:
        con.close()


def clear_recipient_token(db_path, drop_id):
    con = connect(db_path)
    try:
        con.execute("UPDATE drops SET recipient_token_enc=NULL WHERE id=?", (drop_id,))
    finally:
        con.close()


def recipient_link_for_agent(db_path, agent_token, base_url, key_path=None):
    con = connect(db_path)
    try:
        row = con.execute("SELECT * FROM drops WHERE agent_hash=?", (token_hash(agent_token),)).fetchone()
        if not row or row["state"] not in {"submitted", "claimed"} or row["expires_at"] <= int(time.time()):
            return None
        encrypted = row["recipient_token_enc"]
        if encrypted is None:
            return None
        token = fernet(key_path).decrypt(encrypted).decode()
        return f"{base_url.rstrip('/')}/r/{token}"
    finally:
        con.close()


def _consume_row(con, field, token, key_path=None):
    if field not in TOKEN_FIELDS:
        raise ValueError("invalid token field")
    row = con.execute(f"SELECT * FROM drops WHERE {field}=?", (token_hash(token),)).fetchone()  # nosec B608
    if not row or row["state"] != "submitted" or row["expires_at"] <= int(time.time()):
        return None, None
    plaintext = decrypt_payload(row["private_key_enc"], row["wrapped_key"], row["iv"], row["ciphertext"], key_path)
    return row, plaintext


def _finalize_consumed(con, drop_id):
    con.execute(
        """UPDATE drops SET state='consumed',recipient_token_enc=NULL,private_key_enc=X'',
           ciphertext=NULL,iv=NULL,wrapped_key=NULL,claim_id=NULL,claim_destination=NULL,payload_hash=NULL
           WHERE id=?""",
        (drop_id,),
    )
    con.execute("DELETE FROM delivery_outbox WHERE drop_id=?", (drop_id,))


def take_once(db_path, field, token, key_path=None):
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        row, plaintext = _consume_row(con, field, token, key_path)
        if not row:
            con.execute("ROLLBACK")
            return None
        _finalize_consumed(con, row["id"])
        con.execute("COMMIT")
        return plaintext
    except Exception:
        _rollback_quietly(con)
        raise
    finally:
        con.close()


def take_for_recipient(db_path, token, key_path=None):
    return take_once(db_path, "recipient_hash", token, key_path)


def consume_to_file(db_path, agent_token, destination, key_path=None, overwrite=False, after_delivery=None):
    destination = Path(destination)
    if not _lookup(db_path, "agent_hash", agent_token, {"submitted"}):
        return False
    ensure_private_directory(destination.parent)
    if destination.is_symlink():
        raise PermissionError(f"refusing symlink destination: {destination}")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)

    claim_id = secrets.token_urlsafe(24)
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        row, plaintext = _consume_row(con, "agent_hash", agent_token, key_path)
        if not row:
            con.execute("ROLLBACK")
            return False
        if plaintext is None:
            raise RuntimeError("missing claimed plaintext")
        payload_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        con.execute(
            """UPDATE drops SET state='claimed',claim_id=?,claimed_at=?,claim_destination=?,payload_hash=?
               WHERE id=? AND state='submitted'""",
            (claim_id, int(time.time()), str(destination.resolve()), payload_hash, row["id"]),
        )
        con.execute("COMMIT")
    except Exception:
        _rollback_quietly(con)
        con.close()
        raise
    con.close()

    delivered = False
    try:
        _atomic_private_text(destination, plaintext, overwrite=overwrite)
        delivered = True
        if after_delivery:
            after_delivery()
        con = connect(db_path)
        try:
            con.execute("BEGIN IMMEDIATE")
            current = con.execute("SELECT * FROM drops WHERE id=?", (row["id"],)).fetchone()
            if not current or current["state"] != "claimed" or current["claim_id"] != claim_id:
                raise RuntimeError("claim ownership changed")
            _finalize_consumed(con, row["id"])
            con.execute("COMMIT")
        except Exception:
            _rollback_quietly(con)
            raise
        finally:
            con.close()
        return True
    except Exception:
        if not delivered:
            con = connect(db_path)
            try:
                con.execute(
                    """UPDATE drops SET state='submitted',claim_id=NULL,claimed_at=NULL,
                       claim_destination=NULL,payload_hash=NULL WHERE id=? AND state='claimed' AND claim_id=?""",
                    (row["id"], claim_id),
                )
            finally:
                con.close()
        raise


def recover_claims(db_path, stale_after=300):
    con = connect(db_path)
    finalized = 0
    released = 0
    try:
        rows = con.execute("SELECT * FROM drops WHERE state='claimed'").fetchall()
        for row in rows:
            destination = Path(row["claim_destination"] or "")
            if destination.is_file() and not destination.is_symlink():
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                if digest == row["payload_hash"]:
                    con.execute("BEGIN IMMEDIATE")
                    _finalize_consumed(con, row["id"])
                    con.execute("COMMIT")
                    finalized += 1
                    continue
            if row["claimed_at"] and row["claimed_at"] <= int(time.time()) - stale_after:
                con.execute(
                    """UPDATE drops SET state='submitted',claim_id=NULL,claimed_at=NULL,
                       claim_destination=NULL,payload_hash=NULL WHERE id=? AND state='claimed'""",
                    (row["id"],),
                )
                released += 1
        return {"finalized": finalized, "released": released}
    finally:
        con.close()


def revoke(db_path, drop_id):
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """UPDATE drops SET state='revoked',recipient_token_enc=NULL,private_key_enc=X'',
               ciphertext=NULL,iv=NULL,wrapped_key=NULL WHERE id=?""",
            (drop_id,),
        )
        con.execute("DELETE FROM delivery_outbox WHERE drop_id=?", (drop_id,))
        con.execute("COMMIT")
    except Exception:
        _rollback_quietly(con)
        raise
    finally:
        con.close()


def cleanup_expired(db_path, outbox_dir=None):
    con = connect(db_path)
    try:
        expires = int(time.time())
        rows = con.execute("SELECT id FROM drops WHERE expires_at<=? AND state!='claimed'", (expires,)).fetchall()
        con.execute("DELETE FROM drops WHERE expires_at<=? AND state!='claimed'", (expires,))
        if outbox_dir:
            for row in rows:
                (Path(outbox_dir) / f"{row['id']}.json").unlink(missing_ok=True)
        return len(rows)
    finally:
        con.close()
