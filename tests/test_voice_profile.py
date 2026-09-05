import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "templates" / "voice-profile.schema.json"
MODULE_PATH = ROOT / "tools" / "operator-state" / "voice_profile.py"
SPEC = importlib.util.spec_from_file_location("voice_profile", MODULE_PATH)
assert SPEC and SPEC.loader
voice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(voice)


def schema_and_validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema, jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def valid_profile():
    return {
        "schema_version": "1.0",
        "owner_id": "principal-1",
        "private": True,
        "opt_in": {"approved": True, "approved_at": "2026-09-05T12:00:00Z"},
        "storage_policy": {
            "location": "private-profile-state",
            "access": "owner-and-authorized-operator-only",
            "encryption_at_rest_required": True,
            "public_export_excluded": True,
            "audit_access_required": True,
        },
        "lifecycle_policy": {
            "retention_days": 180,
            "delete_on_owner_request": True,
            "revoke_access_on_opt_out": True,
            "verify_deletion": True,
        },
        "source_policy": {
            "owner_approved_sent_messages_only": True,
            "retain_raw_messages": False,
            "raw_message_retention": "none",
            "dispose_source_after_extraction": True,
            "verify_source_disposal": True,
        },
        "base": {"directness": "direct", "paragraph_length": "short", "formality": "neutral", "warmth": "warm", "emoji_use": "none", "closing_style": "brief"},
        "overlays": {
            "business": {"directness": "direct", "paragraph_length": "short", "formality": "formal", "warmth": "neutral", "emoji_use": "none", "closing_style": "brief"},
            "personal": {"directness": "balanced", "paragraph_length": "short", "formality": "casual", "warmth": "warm", "emoji_use": "sparing", "closing_style": "warm"},
        },
        "review": {
            "owner_review_required": True,
            "paired_draft_test_required": True,
            "status": "pending",
        },
        "correction_policy": "update-relevant-overlay",
        "send_policy": "exact-approval-required",
    }


class MemoryKeyProvider:
    approved_for_voice_profiles = True

    def __init__(self, key=b"K" * 32):
        self.key = key

    def get_key(self, purpose):
        assert purpose == "voice-profile-envelope-v1"
        return self.key


class DisposableSource:
    approved = True

    def __init__(self, source_id, raw_message):
        self.source_id = source_id
        self.raw_message = raw_message
        self.dispose_calls = 0

    def dispose(self):
        self.dispose_calls += 1
        self.raw_message = None

    def readback(self):
        return self.raw_message


class VersionedDisposableSource(DisposableSource):
    def __init__(self, source_id, raw_message, source_generation):
        super().__init__(source_id, raw_message)
        self.source_generation = source_generation


def test_private_profile_has_enforceable_storage_and_lifecycle_contract():
    _, validator = schema_and_validator()
    assert not list(validator.iter_errors(valid_profile()))


def test_private_lifecycle_is_documented_for_operators():
    text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8").lower()
        for path in ("ONBOARDING.md", "docs/08-human-side.md")
    )
    for phrase in (
        "private profile state", "excluded from public", "owner and authorized operator",
        "encryption at rest", "retention", "deletion", "revocation", "source disposal",
    ):
        assert phrase in text


def test_profile_rejects_weak_privacy_lifecycle_and_source_disposal():
    _, validator = schema_and_validator()
    mutations = [
        lambda p: p["storage_policy"].update(location="public-profile"),
        lambda p: p["storage_policy"].update(public_export_excluded=False),
        lambda p: p["storage_policy"].update(encryption_at_rest_required=False),
        lambda p: p["storage_policy"].update(access="everyone"),
        lambda p: p["lifecycle_policy"].update(retention_days=0),
        lambda p: p["lifecycle_policy"].update(delete_on_owner_request=False),
        lambda p: p["lifecycle_policy"].update(revoke_access_on_opt_out=False),
        lambda p: p["source_policy"].update(dispose_source_after_extraction=False),
        lambda p: p["source_policy"].update(retain_raw_messages=True),
    ]
    for mutate in mutations:
        profile = copy.deepcopy(valid_profile())
        mutate(profile)
        assert list(validator.iter_errors(profile))


def test_profile_uses_bounded_attributes_not_free_text():
    _, validator = schema_and_validator()
    useful = valid_profile()
    useful["base"]["directness"] = "balanced"
    assert not list(validator.iter_errors(useful))
    profile = valid_profile()
    profile["base"]["patterns"] = ["Hello Sam, private response body"]
    assert list(validator.iter_errors(profile))


def test_profile_rejects_unknown_context_raw_messages_and_private_corpus_fields():
    schema, validator = schema_and_validator()
    assert schema["additionalProperties"] is False
    for field, value in (
        ("raw_messages", ["private mail body"]),
        ("message_bodies", ["body"]),
        ("private_corpus", ["archive"]),
        ("account_id", "provider-account"),
    ):
        profile = valid_profile()
        profile[field] = value
        assert list(validator.iter_errors(profile))
    profile = valid_profile()
    profile["overlays"]["social-media"] = profile["base"]
    assert list(validator.iter_errors(profile))


def test_private_voice_store_enforces_filesystem_lifecycle_and_never_persists_raw(tmp_path):
    root = tmp_path / "private"
    keys = MemoryKeyProvider()
    store = voice.VoiceProfileStore(root, keys)
    raw = "RAW-SENTINEL: Hello Sam, this must never persist"
    profile = valid_profile()
    source = DisposableSource("sent-1", raw)
    store.save(profile, approved_sources=[source])
    path = next(path for path in root.iterdir() if path.name.endswith(".profile"))
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.stat().st_nlink == 1
    assert root.stat().st_mode & 0o777 == 0o700
    assert store.load("principal-1")["base"] == profile["base"]
    assert path.name not in store.public_export_manifest()
    persisted = b"".join(p.read_bytes() for p in root.iterdir() if p.is_file())
    for secret in (raw, "principal-1", "directness", "business", "sent-1"):
        assert secret.encode() not in persisted
    assert source.dispose_calls == 1 and source.readback() is None
    saved_event = next(event for event in store.audit_events() if event["action"] == "saved")
    source_digest = hashlib.sha256(b"sent-1").hexdigest()
    assert saved_event["source_evidence"] == [{"id_digest": source_digest, "disposed": True}]
    assert saved_event["raw_messages_persisted"] is False
    assert store.disposed_sources() == [source_digest]
    assert voice.VoiceProfileStore(root, keys).disposed_sources() == [source_digest]
    store.revoke("principal-1")
    assert store.load("principal-1") is None
    store.delete("principal-1")
    assert not path.exists()


def test_private_voice_store_rejects_symlink_hardlink_permissions_and_unapproved_source(tmp_path):
    root = tmp_path / "private"
    store = voice.VoiceProfileStore(root, MemoryKeyProvider())
    profile = valid_profile()
    unapproved = DisposableSource("x", "secret")
    unapproved.approved = False
    with pytest.raises(PermissionError):
        store.save(profile, approved_sources=[unapproved])
    with pytest.raises(TypeError, match="source-handle protocol"):
        store.save(profile, approved_sources=[{"source_id": "x", "raw_message": "secret", "approved": True}])
    store.save(profile, approved_sources=[])
    path = next(path for path in root.iterdir() if path.name.endswith(".profile"))
    os.chmod(path, 0o644)
    with pytest.raises(PermissionError):
        store.load("principal-1")
    os.chmod(path, 0o600)
    link = root / "hardlink"
    os.link(path, link)
    with pytest.raises(PermissionError):
        store.load("principal-1")


def test_private_voice_store_fails_closed_without_approved_key(tmp_path):
    with pytest.raises(PermissionError, match="approved key provider"):
        voice.VoiceProfileStore(tmp_path / "missing", None)
    provider = MemoryKeyProvider()
    provider.approved_for_voice_profiles = False
    with pytest.raises(PermissionError, match="approved key provider"):
        voice.VoiceProfileStore(tmp_path / "unapproved", provider)


def test_private_voice_store_rejects_tampered_ciphertext(tmp_path):
    store = voice.VoiceProfileStore(tmp_path / "private", MemoryKeyProvider())
    store.save(valid_profile(), [])
    path = next(path for path in (tmp_path / "private").iterdir() if path.name.endswith(".profile"))
    envelope = json.loads(path.read_text())
    envelope["ciphertext"] = envelope["ciphertext"][:-2] + "AA"
    path.write_text(json.dumps(envelope))
    os.chmod(path, 0o600)
    with pytest.raises(ValueError, match="authentication"):
        store.load("principal-1")


def test_private_voice_store_fails_closed_when_source_disposal_is_unconfirmed(tmp_path):
    class LyingSource(DisposableSource):
        def dispose(self):
            self.dispose_calls += 1

    store = voice.VoiceProfileStore(tmp_path / "private", MemoryKeyProvider())
    source = LyingSource("sent-1", "RAW-SENTINEL")
    with pytest.raises(RuntimeError, match="disposal verification failed"):
        store.save(valid_profile(), [source])
    assert store.load("principal-1") is None
    assert store.disposed_sources() == []


def test_disposal_evidence_survives_later_source_failure_and_restart(tmp_path):
    class LyingSource(DisposableSource):
        def dispose(self):
            self.dispose_calls += 1

    root = tmp_path / "private"
    keys = MemoryKeyProvider()
    first = DisposableSource("sent-1", "FIRST-RAW")
    second = LyingSource("sent-2", "SECOND-RAW")
    with pytest.raises(RuntimeError, match="disposal verification failed"):
        voice.VoiceProfileStore(root, keys).save(valid_profile(), [first, second])
    first_digest = hashlib.sha256(b"sent-1").hexdigest()
    restarted = voice.VoiceProfileStore(root, keys)
    assert restarted.disposed_sources() == [first_digest]
    assert restarted.load("principal-1") is None


def test_restart_rechecks_and_disposes_resurrected_raw_same_source_id(tmp_path):
    class LyingSource(DisposableSource):
        def dispose(self):
            self.dispose_calls += 1

    root = tmp_path / "private"
    keys = MemoryKeyProvider()
    first = DisposableSource("sent-1", "FIRST-RAW")
    failing = LyingSource("sent-2", "SECOND-RAW")

    with pytest.raises(RuntimeError, match="disposal verification failed"):
        voice.VoiceProfileStore(root, keys).save(valid_profile(), [first, failing])

    resurrected = DisposableSource("sent-1", "RESURRECTED-RAW")
    repaired_second = DisposableSource("sent-2", None)
    restarted = voice.VoiceProfileStore(root, keys)
    restarted.save(valid_profile(), [resurrected, repaired_second])

    assert resurrected.dispose_calls == 1
    assert resurrected.readback() is None
    assert restarted.load("principal-1") is not None
    lifecycle = json.loads((root / ".lifecycle.json").read_text())
    source_receipt = lifecycle["transactions"][restarted._owner_digest("principal-1")]["sources"][0]
    assert source_receipt["status"] == "verified"
    assert source_receipt["generation_digest"] is None
    assert source_receipt["content_digest"] == hashlib.sha256(b"RESURRECTED-RAW").hexdigest()
    assert b"RESURRECTED-RAW" not in (root / ".lifecycle.json").read_bytes()


def test_published_retry_still_rechecks_current_handle_and_disposes_raw(tmp_path):
    root = tmp_path / "private"
    keys = MemoryKeyProvider()
    voice.VoiceProfileStore(root, keys).save(
        valid_profile(), [VersionedDisposableSource("sent-1", "FIRST", "generation-1")]
    )
    resurrected = VersionedDisposableSource("sent-1", "RESURRECTED-RAW", "generation-2")

    voice.VoiceProfileStore(root, keys).save(valid_profile(), [resurrected])

    assert resurrected.dispose_calls == 1
    assert resurrected.readback() is None
    lifecycle = json.loads((root / ".lifecycle.json").read_text())
    owner_digest = voice.VoiceProfileStore(root, keys)._owner_digest("principal-1")
    receipt = lifecycle["transactions"][owner_digest]["sources"][0]
    assert receipt["generation_digest"] == hashlib.sha256(b"generation-2").hexdigest()
    assert receipt["content_digest"] == hashlib.sha256(b"RESURRECTED-RAW").hexdigest()


def test_save_resumes_journaled_disposal_without_disposing_twice(tmp_path):
    root = tmp_path / "private"
    keys = MemoryKeyProvider()
    sources = [DisposableSource("sent-1", "FIRST"), DisposableSource("sent-2", "SECOND")]
    store = voice.VoiceProfileStore(root, keys)
    original = store._atomic_json
    writes = 0

    def crash_after_first_disposal(name, value):
        nonlocal writes
        original(name, value)
        if name == ".lifecycle.json" and hashlib.sha256(b"sent-1").hexdigest() in value.get("disposed_sources", []):
            writes += 1
            if writes == 1:
                raise RuntimeError("simulated crash")

    store._atomic_json = crash_after_first_disposal
    with pytest.raises(RuntimeError, match="simulated crash"):
        store.save(valid_profile(), sources)
    assert voice.VoiceProfileStore(root, keys).load("principal-1") is None
    voice.VoiceProfileStore(root, keys).save(valid_profile(), sources)
    assert sources[0].dispose_calls == 1
    assert sources[1].dispose_calls == 1
    assert voice.VoiceProfileStore(root, keys).load("principal-1") is not None


def test_failed_final_lifecycle_commit_never_publishes_new_profile(tmp_path):
    root = tmp_path / "private"
    keys = MemoryKeyProvider()
    store = voice.VoiceProfileStore(root, keys)
    original = store._atomic_json

    def fail_activation(name, value):
        if name == ".lifecycle.json" and value.get("active_profiles"):
            raise RuntimeError("lifecycle write failed")
        return original(name, value)

    store._atomic_json = fail_activation
    with pytest.raises(RuntimeError, match="lifecycle write failed"):
        store.save(valid_profile(), [DisposableSource("sent-1", "RAW")])
    assert voice.VoiceProfileStore(root, keys).load("principal-1") is None
    assert not list(root.glob("*.profile"))


def test_read_binds_opened_file_to_checked_inode(tmp_path, monkeypatch):
    root = tmp_path / "private"
    store = voice.VoiceProfileStore(root, MemoryKeyProvider())
    store.save(valid_profile(), [])
    profile = next(root.glob("*.profile"))
    replacement = root / "replacement"
    replacement.write_bytes(profile.read_bytes())
    replacement.chmod(0o600)
    real_open = voice.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == profile.name and not swapped:
            swapped = True
            os.replace(replacement, profile)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(voice.os, "open", racing_open)
    with pytest.raises(PermissionError, match="unsafe profile state file"):
        store.load("principal-1")


def test_read_rechecks_owner_mode_and_links_on_opened_descriptor(tmp_path, monkeypatch):
    root = tmp_path / "private"
    store = voice.VoiceProfileStore(root, MemoryKeyProvider())
    store.save(valid_profile(), [])
    profile = next(root.glob("*.profile"))
    real_open = voice.os.open

    def chmod_before_open(path, flags, *args, **kwargs):
        if path == profile.name:
            profile.chmod(0o644)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(voice.os, "open", chmod_before_open)
    with pytest.raises(PermissionError, match="unsafe profile state file"):
        store.load("principal-1")


@pytest.mark.skipif(os.name != "posix", reason="POSIX high-assurance path contract")
def test_private_voice_store_rejects_symlinked_parent(tmp_path):
    attacker = tmp_path / "attacker"
    attacker.mkdir(mode=0o700)
    link = tmp_path / "linked-parent"
    link.symlink_to(attacker, target_is_directory=True)
    with pytest.raises(PermissionError):
        voice.VoiceProfileStore(link / "private", MemoryKeyProvider())
    assert not (attacker / "private").exists()


def test_daily_brief_identity_is_content_independent_in_docs():
    onboarding = (ROOT / "ONBOARDING.md").read_text(encoding="utf-8").lower()
    scheduling = (ROOT / "docs/03-tasks-and-scheduling.md").read_text(encoding="utf-8").lower()
    for text in (onboarding, scheduling):
        assert "routine + scheduled occurrence + channel + recipient" in text
        assert "content digest is evidence, not identity" in text
