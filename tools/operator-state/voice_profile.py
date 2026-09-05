"""High-assurance, local-only private voice-profile lifecycle.

Profile envelopes use authenticated encryption supplied by an explicitly approved
external key provider. Raw sources are accepted only through disposable handles.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

import jsonschema
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "templates" / "voice-profile.schema.json").read_text(encoding="utf-8"))
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_KEY_PURPOSE = "voice-profile-envelope-v1"


@runtime_checkable
class VoiceProfileKeyProvider(Protocol):
    """Approved key boundary; implementations must keep keys outside this store."""

    approved_for_voice_profiles: bool

    def get_key(self, purpose: str) -> bytes:
        """Return a 256-bit key for the named purpose, or fail."""
        raise NotImplementedError


@runtime_checkable
class DisposableVoiceSource(Protocol):
    """Owner-approved source whose destruction can be verified by readback."""

    source_id: str
    approved: bool

    def dispose(self) -> None: ...

    def readback(self) -> object | None: ...


class VoiceProfileStore:
    """Owner-private encrypted store with durable disposal evidence."""

    def __init__(self, root, key_provider: VoiceProfileKeyProvider | None):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise NotImplementedError("high-assurance voice storage requires POSIX dir-fd operations")
        if key_provider is None or getattr(key_provider, "approved_for_voice_profiles", False) is not True:
            raise PermissionError("an approved key provider is required")
        try:
            key = key_provider.get_key(_KEY_PURPOSE)
        except Exception as exc:
            raise PermissionError("approved key provider did not supply a key") from exc
        if not isinstance(key, bytes) or len(key) != 32:
            raise PermissionError("approved key provider must supply a 256-bit key")
        self._key = key
        self.root = Path(os.path.abspath(os.fspath(root)))
        self._root_fd: int = self._open_private_root(self.root)

    def __del__(self):
        fd = getattr(self, "_root_fd", None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


    @staticmethod
    def _validate_parent(info: os.stat_result, component: str) -> None:
        if not stat.S_ISDIR(info.st_mode):
            raise PermissionError(f"voice profile parent is not a directory: {component}")
        mode = stat.S_IMODE(info.st_mode)
        owner_ok = info.st_uid in (0, os.geteuid())
        sticky_root = info.st_uid == 0 and bool(mode & stat.S_ISVTX)
        if not owner_ok or ((mode & 0o022) and not sticky_root):
            raise PermissionError(f"unsafe voice profile parent permissions: {component}")

    @classmethod
    def _open_private_root(cls, root: Path) -> int:
        parts = root.parts
        if not root.is_absolute() or not parts or parts[0] != os.sep:
            raise PermissionError("voice profile root must be absolute")
        current = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            cls._validate_parent(os.fstat(current), os.sep)
            for index, component in enumerate(parts[1:]):
                final = index == len(parts[1:]) - 1
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                        dir_fd=current,
                    )
                except FileNotFoundError:
                    try:
                        os.mkdir(component, 0o700, dir_fd=current)
                    except FileExistsError:
                        pass
                    try:
                        child = os.open(
                            component,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                            dir_fd=current,
                        )
                    except OSError as exc:
                        raise PermissionError("unsafe voice profile path component") from exc
                except OSError as exc:
                    raise PermissionError("unsafe voice profile path component") from exc
                info = os.fstat(child)
                cls._validate_parent(info, component)
                if final and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
                    os.close(child)
                    raise PermissionError("voice profile root must be owner-only mode 0700")
                os.close(current)
                current = child
            return current
        except Exception:
            os.close(current)
            raise

    @staticmethod
    def _identifier(value: object, label: str) -> str:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError(f"unsafe {label} identifier")
        return value

    def _owner_digest(self, owner_id: str) -> str:
        return hmac.new(self._key, b"owner\0" + owner_id.encode(), hashlib.sha256).hexdigest()

    def _profile_name(self, owner_id: str) -> str:
        return f"{self._owner_digest(owner_id)}.profile"

    def _safe_existing(self, name: str) -> os.stat_result:
        try:
            info = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
        except FileNotFoundError:
            raise
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PermissionError("profile state must be a real regular file with one link")
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise PermissionError("profile state must be owner-only mode 0600")
        return info

    def _exists(self, name: str) -> bool:
        try:
            os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def _read_bytes(self, name: str) -> bytes:
        checked = self._safe_existing(name)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self._root_fd)
        except OSError as exc:
            raise PermissionError("unsafe profile state file") from exc
        try:
            opened = os.fstat(fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino)
            ):
                raise PermissionError("unsafe profile state file")
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(fd)

    def _atomic_bytes(self, name: str, value: bytes) -> None:
        if self._exists(name):
            self._safe_existing(name)
        temporary = f".voice-{os.getpid()}-{os.urandom(12).hex()}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        fd = os.open(temporary, flags, 0o600, dir_fd=self._root_fd)
        try:
            view = memoryview(value)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(temporary, name, src_dir_fd=self._root_fd, dst_dir_fd=self._root_fd)
            os.fsync(self._root_fd)
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=self._root_fd)
            except FileNotFoundError:
                pass

    def _atomic_json(self, name: str, value: object) -> None:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self._atomic_bytes(name, encoded)

    def _state(self) -> dict:
        name = ".lifecycle.json"
        if not self._exists(name):
            return {"revoked": [], "audit": [], "disposed_sources": [], "transactions": {}, "active_profiles": {}}
        state = json.loads(self._read_bytes(name).decode())
        state.setdefault("disposed_sources", [])
        state.setdefault("transactions", {})
        state.setdefault("active_profiles", {})
        return state

    def _event(self, action: str, owner_digest: str, source_evidence=None) -> None:
        state = self._state()
        state["audit"].append({
            "action": action,
            "owner_digest": owner_digest,
            "at": datetime.now(timezone.utc).isoformat(),
            "source_evidence": source_evidence or [],
            "raw_messages_persisted": False,
        })
        self._atomic_json(".lifecycle.json", state)

    @staticmethod
    def _source_handles(sources) -> tuple[list, list[str]]:
        handles, digests = [], []
        for source in sources:
            if not isinstance(source, DisposableVoiceSource):
                raise TypeError("voice source must implement the disposable source-handle protocol")
            if source.approved is not True:
                raise PermissionError("voice source is not owner approved")
            source_id = VoiceProfileStore._identifier(source.source_id, "source")
            handles.append(source)
            digests.append(hashlib.sha256(source_id.encode()).hexdigest())
        if len(set(digests)) != len(digests):
            raise ValueError("duplicate voice source identifier")
        return handles, digests

    @staticmethod
    def _identity_digest(value: object) -> str | None:
        """Digest stable source metadata/content without persisting raw material."""
        if value is None:
            return None
        if isinstance(value, bytes):
            encoded = value
        elif isinstance(value, str):
            encoded = value.encode()
        else:
            try:
                encoded = json.dumps(
                    value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            except (TypeError, ValueError):
                return None
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _source_generation_digest(cls, source) -> str | None:
        for attribute in ("source_generation", "generation", "version"):
            if hasattr(source, attribute):
                return cls._identity_digest(getattr(source, attribute))
        return None

    def _encrypt_profile(self, owner_id: str, envelope: dict) -> dict:
        nonce = os.urandom(12)
        aad = f"{_KEY_PURPOSE}:{self._owner_digest(owner_id)}".encode()
        plaintext = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, aad)
        return {
            "format": _KEY_PURPOSE,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def _decrypt_profile(self, owner_id: str, encrypted: dict) -> dict:
        try:
            if encrypted.get("format") != _KEY_PURPOSE:
                raise ValueError
            nonce = base64.b64decode(encrypted["nonce"], validate=True)
            ciphertext = base64.b64decode(encrypted["ciphertext"], validate=True)
            aad = f"{_KEY_PURPOSE}:{self._owner_digest(owner_id)}".encode()
            plaintext = AESGCM(self._key).decrypt(nonce, ciphertext, aad)
            return json.loads(plaintext)
        except (InvalidTag, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("profile envelope authentication failed") from exc

    def save(self, profile, approved_sources) -> None:
        jsonschema.validate(profile, SCHEMA, format_checker=jsonschema.FormatChecker())
        owner_id = self._identifier(profile["owner_id"], "owner")
        handles, source_digests = self._source_handles(approved_sources)
        owner_digest = self._owner_digest(owner_id)
        binding = hmac.new(
            self._key,
            b"save\0" + json.dumps(
                {"profile": profile, "sources": source_digests},
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
            hashlib.sha256,
        ).hexdigest()
        transaction_id = binding
        pending_name = f".{owner_digest}.{transaction_id}.pending"
        now = datetime.now(timezone.utc)
        envelope = {
            "profile": copy.deepcopy(profile),
            "saved_at": now.isoformat(),
            "expires_at": (now + timedelta(days=profile["lifecycle_policy"]["retention_days"])).isoformat(),
            "transaction_id": transaction_id,
        }
        state = self._state()
        transaction = state["transactions"].get(owner_digest)
        published = False
        profile_name = self._profile_name(owner_id)
        if transaction and self._exists(profile_name):
            current = self._decrypt_profile(owner_id, json.loads(self._read_bytes(profile_name).decode()))
            published = state["active_profiles"].get(owner_digest) == current.get("transaction_id") == transaction["binding"]
        if transaction and transaction["binding"] != binding and not published:
            raise RuntimeError("an incomplete voice profile transaction must be reconciled first")
        if not transaction or transaction["binding"] != binding:
            self._atomic_json(pending_name, self._encrypt_profile(owner_id, envelope))
            transaction = {
                "binding": binding,
                "status": "disposing",
                "sources": [{"id_digest": digest, "status": "intent"} for digest in source_digests],
            }
            state["transactions"][owner_digest] = transaction
            self._atomic_json(".lifecycle.json", state)
        elif not published and not self._exists(pending_name) and transaction.get("status") != "published":
            self._atomic_json(pending_name, self._encrypt_profile(owner_id, envelope))

        evidence = []
        for source, source_state in zip(handles, transaction["sources"]):
            digest = source_state["id_digest"]
            try:
                remaining = source.readback()
            except Exception as exc:
                raise RuntimeError("source disposal verification failed") from exc
            generation_digest = self._source_generation_digest(source)
            content_digest = self._identity_digest(remaining)
            if remaining is not None:
                # Prior source-id evidence never authorizes skipping a current effect.
                # Persist the current generation/content intent before destruction.
                source_state.update({
                    "status": "intent",
                    "generation_digest": generation_digest,
                    "content_digest": content_digest,
                })
                self._atomic_json(".lifecycle.json", state)
                try:
                    source.dispose()
                    remaining = source.readback()
                except Exception as exc:
                    raise RuntimeError("source disposal verification failed") from exc
            if remaining is not None:
                raise RuntimeError("source disposal verification failed")
            source_state.update({
                "status": "verified",
                "generation_digest": generation_digest,
                "content_digest": content_digest,
            })
            if digest not in state["disposed_sources"]:
                state["disposed_sources"].append(digest)
            self._atomic_json(".lifecycle.json", state)
            evidence.append({"id_digest": digest, "disposed": True})

        if any(item["status"] != "verified" for item in transaction["sources"]):
            raise RuntimeError("source disposal verification incomplete")
        if published:
            return
        if owner_digest in state["revoked"]:
            state["revoked"].remove(owner_digest)
        transaction["status"] = "committed"
        state["active_profiles"][owner_digest] = transaction_id
        state["audit"].append({
            "action": "saved",
            "owner_digest": owner_digest,
            "at": datetime.now(timezone.utc).isoformat(),
            "source_evidence": evidence,
            "raw_messages_persisted": False,
        })
        self._atomic_json(".lifecycle.json", state)
        os.replace(pending_name, self._profile_name(owner_id), src_dir_fd=self._root_fd, dst_dir_fd=self._root_fd)
        os.fsync(self._root_fd)

    def load(self, owner_id):
        owner_id = self._identifier(owner_id, "owner")
        owner_digest = self._owner_digest(owner_id)
        state = self._state()
        if owner_digest in state["revoked"]:
            return None
        name = self._profile_name(owner_id)
        if not self._exists(name):
            return None
        envelope = self._decrypt_profile(owner_id, json.loads(self._read_bytes(name).decode()))
        if state["active_profiles"].get(owner_digest) != envelope.get("transaction_id"):
            return None
        if datetime.fromisoformat(envelope["expires_at"]) <= datetime.now(timezone.utc):
            self.delete(owner_id)
            return None
        self._event("accessed", owner_digest)
        return copy.deepcopy(envelope["profile"])

    def revoke(self, owner_id):
        owner_id = self._identifier(owner_id, "owner")
        owner_digest = self._owner_digest(owner_id)
        state = self._state()
        if owner_digest not in state["revoked"]:
            state["revoked"].append(owner_digest)
        self._atomic_json(".lifecycle.json", state)
        self._event("revoked", owner_digest)

    def delete(self, owner_id):
        owner_id = self._identifier(owner_id, "owner")
        owner_digest = self._owner_digest(owner_id)
        name = self._profile_name(owner_id)
        if self._exists(name):
            self._safe_existing(name)
            os.unlink(name, dir_fd=self._root_fd)
            os.fsync(self._root_fd)
        if self._exists(name):
            raise RuntimeError("profile deletion verification failed")
        self._event("deleted", owner_digest)

    def public_export_manifest(self):
        """Private profiles are unconditionally excluded from public exports."""
        return []

    def audit_events(self):
        return copy.deepcopy(self._state()["audit"])

    def disposed_sources(self):
        return list(self._state()["disposed_sources"])
