"""Cryptographic and protected-filesystem helpers."""
from __future__ import annotations

import base64
import fcntl
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def default_key_path() -> Path:
    return Path(os.environ.get(
        "SECURE_CREDENTIALS_KEY_FILE",
        hermes_home() / "secrets" / "secure-credentials.key",
    ))


def ensure_private_directory(path: Path | str) -> Path:
    path = Path(path)
    if path.exists() and path.is_symlink():
        raise PermissionError(f"refusing symlink directory: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        info = path.stat()
        if info.st_uid != os.getuid():
            raise PermissionError(f"directory is not owned by current user: {path}")
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.chmod(path, 0o700)
            if stat.S_IMODE(path.stat().st_mode) != 0o700:
                raise PermissionError(f"directory is not owner-only: {path}")
    return path


def ensure_private_file(path: Path | str) -> Path:
    path = Path(path)
    if path.is_symlink():
        raise PermissionError(f"refusing symlink file: {path}")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise PermissionError(f"not a regular file: {path}")
    if os.name == "posix":
        if info.st_nlink != 1:
            raise PermissionError(f"file has unexpected hard links: {path}")
        if info.st_uid != os.getuid():
            raise PermissionError(f"file is not owned by current user: {path}")
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.chmod(path, 0o600)
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise PermissionError(f"file is not owner-only: {path}")
    return path


def validate_sensitive_sqlite_path(path: Path | str) -> Path:
    """Reject unsafe existing SQLite paths without changing them."""
    path = Path(path)
    parent = path.parent
    if parent.exists():
        if parent.is_symlink() or not parent.is_dir():
            raise PermissionError(f"unsafe database parent: {parent}")
        if os.name == "posix":
            info = parent.stat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise PermissionError(f"database parent is not private: {parent}")
    else:
        ensure_private_directory(parent)
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.is_symlink():
            raise PermissionError(f"refusing symlink SQLite file: {candidate}")
        if not candidate.exists():
            continue
        info = candidate.stat()
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError(f"not a regular SQLite file: {candidate}")
        if os.name == "posix" and (
            info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise PermissionError(f"SQLite file is not private: {candidate}")
    return path


def fsync_directory(path: Path | str) -> None:
    if os.name != "posix":
        return
    fd = os.open(Path(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def master_key(path: Path | str | None = None) -> bytes:
    value = os.getenv("SECURE_CREDENTIALS_MASTER_KEY", "").strip()
    if value:
        key = value.encode()
        Fernet(key)
        return key

    key_path = Path(path or default_key_path())
    ensure_private_directory(key_path.parent)
    lock_path = key_path.with_name(f".{key_path.name}.lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    lock_fd = os.open(lock_path, flags, 0o600)
    try:
        ensure_private_file(lock_path)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if key_path.is_symlink():
            raise PermissionError(f"refusing symlink file: {key_path}")
        if not key_path.exists():
            create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                create_flags |= os.O_NOFOLLOW
            fd = os.open(key_path, create_flags, 0o600)
            try:
                generated = Fernet.generate_key() + b"\n"
                os.write(fd, generated)
                os.fsync(fd)
            finally:
                os.close(fd)
            fsync_directory(key_path.parent)
        ensure_private_file(key_path)
        key = key_path.read_bytes().strip()
        Fernet(key)
        return key
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def fernet(path=None) -> Fernet:
    return Fernet(master_key(path))


def secret_tier(deployment_tier: str, *, high_impact: bool) -> dict:
    """Classify a deployment without pretending same-process encryption is isolation."""
    allowed = not high_impact or deployment_tier in {"high-assurance", "managed"}
    return {
        "tier": deployment_tier,
        "high_impact": high_impact,
        "allowed": allowed,
        "requires_process_boundary": high_impact,
    }


def generate_drop_keys(key_path=None) -> tuple[str, bytes]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_der = private.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(public_der).decode(), fernet(key_path).encrypt(private_pem)


def encrypt_for_public_key(public_key_b64: str, plaintext: str) -> tuple[str, str, str]:
    public = serialization.load_der_public_key(base64.b64decode(public_key_b64, validate=True))
    if not isinstance(public, rsa.RSAPublicKey):
        raise TypeError("drop public key must be RSA")
    aes_key = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(iv, plaintext.encode(), None)
    wrapped = public.encrypt(
        aes_key,
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return (
        base64.b64encode(ciphertext).decode(),
        base64.b64encode(iv).decode(),
        base64.b64encode(wrapped).decode(),
    )


def decrypt_payload(private_key_enc: bytes, wrapped_b64: str, iv_b64: str, ciphertext_b64: str, key_path=None) -> str:
    private_pem = fernet(key_path).decrypt(private_key_enc)
    private = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private, rsa.RSAPrivateKey):
        raise TypeError("drop private key must be RSA")
    aes_key = private.decrypt(
        base64.b64decode(wrapped_b64, validate=True),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    plaintext = AESGCM(aes_key).decrypt(
        base64.b64decode(iv_b64, validate=True),
        base64.b64decode(ciphertext_b64, validate=True),
        None,
    )
    return plaintext.decode("utf-8")
