"""Encrypted reusable credential vault with explicit delivery policy."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .crypto import ensure_private_file, fernet, validate_sensitive_sqlite_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    service TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    login TEXT,
    secret_enc BLOB NOT NULL,
    owner_scope TEXT NOT NULL,
    authorized_principals TEXT NOT NULL,
    authorized_recipients TEXT NOT NULL,
    reset_allowed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    source TEXT,
    last_verified_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def default_vault_path():
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return Path(os.environ.get("SECURE_CREDENTIALS_VAULT", home / "secrets" / "credential-vault.db"))


def connect(path=None):
    path = validate_sensitive_sqlite_path(path or default_vault_path())
    old_umask = os.umask(0o077) if os.name == "posix" else None
    try:
        con = sqlite3.connect(path, isolation_level=None)
    finally:
        if old_umask is not None:
            os.umask(old_umask)
    con.row_factory = sqlite3.Row
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        existing = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='credentials'").fetchone()
        if version == 0 and existing:
            raise RuntimeError("unversioned vault requires explicit migration")
        if version not in {0, 1}:
            raise RuntimeError(f"unsupported vault schema version: {version}")
        if version == 0:
            try:
                con.executescript(f"BEGIN IMMEDIATE;\n{SCHEMA}\nPRAGMA user_version=1;\nCOMMIT;")
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        ensure_private_file(path)
        return con
    except Exception:
        con.close()
        raise


def _normalize_identities(values):
    cleaned = sorted({str(value).strip() for value in values or [] if str(value).strip()})
    if not cleaned:
        raise ValueError("at least one authorized identity is required")
    return cleaned


def put(
    service,
    url,
    login,
    secret,
    owner_scope="internal",
    authorized_principals=None,
    authorized_recipients=None,
    reset_allowed=False,
    status="stored",
    source=None,
    path=None,
):
    if not secret:
        raise ValueError("secret is required")
    principals = _normalize_identities(authorized_principals)
    recipients = _normalize_identities(authorized_recipients or principals)
    if owner_scope != "internal":
        reset_allowed = False
    encrypted = fernet().encrypt(secret.encode())
    con = connect(path)
    try:
        con.execute(
            """INSERT INTO credentials(
               service,url,login,secret_enc,owner_scope,authorized_principals,
               authorized_recipients,reset_allowed,status,source)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(service) DO UPDATE SET
                 url=excluded.url,login=excluded.login,secret_enc=excluded.secret_enc,
                 owner_scope=excluded.owner_scope,authorized_principals=excluded.authorized_principals,
                 authorized_recipients=excluded.authorized_recipients,
                 reset_allowed=excluded.reset_allowed,status=excluded.status,
                 source=excluded.source,updated_at=CURRENT_TIMESTAMP""",
            (
                service, url, login, encrypted, owner_scope, json.dumps(principals),
                json.dumps(recipients), int(reset_allowed), status, source,
            ),
        )
        con.commit()
    finally:
        con.close()


def get_for_operator(service, recipient, path=None):
    """Read as the local OS operator and enforce recipient policy."""
    con = connect(path)
    try:
        row = con.execute("SELECT * FROM credentials WHERE service=?", (service,)).fetchone()
    finally:
        con.close()
    if not row:
        raise KeyError(service)
    recipients = json.loads(row["authorized_recipients"])
    if recipient not in recipients:
        raise PermissionError("recipient is not authorized for this credential")
    data = dict(row)
    data["secret"] = fernet().decrypt(data.pop("secret_enc")).decode()
    data["authorized_principals"] = json.loads(data["authorized_principals"])
    data["authorized_recipients"] = recipients
    return data


def safe_list(path=None):
    con = connect(path)
    try:
        rows = con.execute(
            """SELECT service,url,login,owner_scope,authorized_principals,
               authorized_recipients,reset_allowed,status,source,last_verified_at,updated_at
               FROM credentials ORDER BY service"""
        ).fetchall()
    finally:
        con.close()
    output = []
    for row in rows:
        item = dict(row)
        item["authorized_principals"] = json.loads(item["authorized_principals"])
        item["authorized_recipients"] = json.loads(item["authorized_recipients"])
        output.append(item)
    return output


def deployment_assurance(tier, *, owner_scope):
    if owner_scope == "high-impact" and tier not in {"high-assurance", "managed"}:
        return "prohibited"
    return tier


def perform_with_secret(service, operation, executor, path=None):
    """Decrypt only for a broker-owned callback; never return the secret."""
    con = connect(path)
    try:
        row = con.execute("SELECT * FROM credentials WHERE service=?", (service,)).fetchone()
    finally:
        con.close()
    if not row or row["status"] != "stored":
        raise KeyError(service)
    secret = fernet().decrypt(row["secret_enc"]).decode()
    try:
        result = executor(operation, secret)
    finally:
        secret = None
    if not isinstance(result, dict):
        raise RuntimeError("secret executor must return metadata")
    forbidden = {"secret", "plaintext", "recipient_url", "url", "link", "token", "password", "passwd", "api_key", "authorization", "credential", "private_key"}
    def reject(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if any(term in str(key).lower() for term in forbidden):
                    raise RuntimeError("secret executor attempted to return secret-capable data")
                reject(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                reject(child)
        elif isinstance(value, str) and ("sentinel" in value.lower() or value.lower().startswith(("sk-", "ghp_", "xoxb-", "akia")) or "bearer " in value.lower() or "-----begin " in value.lower()):
            raise RuntimeError("secret executor attempted to return secret-like plaintext")
    reject(result)
    allowed = {"provider_id", "provider_status", "status_code", "attempt_count", "retryable"}
    if set(result) - allowed:
        raise RuntimeError("secret executor returned non-allowlisted metadata")
    return result
