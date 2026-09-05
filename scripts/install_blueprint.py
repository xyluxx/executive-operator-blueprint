#!/usr/bin/env python3
"""Idempotent wrapper around native Hermes profile installation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANSWERS = ROOT / "templates" / "install.answers.example.yaml"
ANSWERS_SCHEMA = ROOT / "templates" / "install.answers.schema.json"
PROFILE_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")
COMPLETE_STATES = {"planned", "verified", "rolled_back"}
BLOCKED_STATES = {"dependency_blocked", "credential_blocked", "verification_blocked", "failed"}
AUTHORITY_MAP = ROOT / "contracts" / "authority-map.yaml"


def compatibility_contract():
    return yaml.safe_load(AUTHORITY_MAP.read_text(encoding="utf-8"))["compatibility"]


_COMPATIBILITY = compatibility_contract()
TESTED_HERMES_RANGE = _COMPATIBILITY["semantic_range"]
TESTED_HERMES_BUILD = _COMPATIBILITY["tested_upstream_build"]


def now():
    return datetime.now(timezone.utc).isoformat()


def hermes_home():
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def load_manifest():
    data = yaml.safe_load((ROOT / "distribution.yaml").read_text())
    if not isinstance(data, dict):
        raise ValueError("invalid distribution manifest")
    return data


def distribution_version():
    return str(load_manifest()["version"])


def source_commit():
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=15)  # nosec B603 B607
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


GENERATED_CACHE_DIRECTORIES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _is_generated_cache_artifact(path):
    relative_path = path.relative_to(ROOT)
    return (
        any(part in GENERATED_CACHE_DIRECTORIES for part in relative_path.parts)
        or path.suffix.lower() in {".pyc", ".pyo"}
    )


def generated_distribution_artifacts():
    artifacts = []
    for relative in load_manifest().get("distribution_owned") or []:
        source = ROOT / relative.rstrip("/")
        candidates = [source]
        if source.is_dir():
            candidates.extend(source.rglob("*"))
        for candidate in candidates:
            if _is_generated_cache_artifact(candidate):
                artifacts.append(candidate.relative_to(ROOT).as_posix())
    return sorted(set(artifacts))


def distribution_source_files():
    files = []

    for relative in load_manifest().get("distribution_owned") or []:
        source = ROOT / relative.rstrip("/")
        if _is_generated_cache_artifact(source):
            continue
        if source.is_symlink():
            raise RuntimeError(f"distribution source contains a symlink: {relative}")
        if source.is_dir():
            for item in source.rglob("*"):
                if _is_generated_cache_artifact(item):
                    continue
                if item.is_symlink():
                    raise RuntimeError(f"distribution source contains a symlink: {item.relative_to(ROOT)}")
                if item.is_file():
                    files.append(item)
        elif source.is_file():
            files.append(source)
        else:
            raise RuntimeError(f"distribution-owned source is missing: {relative}")
    return sorted(set(files), key=lambda item: item.relative_to(ROOT).as_posix())


def _git_tree_modes(commit: str) -> dict[str, str] | None:
    result = run_command(["git", "-C", str(ROOT), "ls-tree", "-r", "-z", commit], timeout=15)
    if result.returncode != 0:
        return None
    modes: dict[str, str] = {}
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        try:
            metadata, relative = entry.split("\t", 1)
            mode, object_type, _ = metadata.split(" ", 2)
        except ValueError:
            return None
        if object_type == "blob":
            modes[relative] = mode
    return modes


def source_tree_sha256(git_modes: dict[str, str] | None = None):
    if os.name != "posix" and git_modes is None:
        commit = source_commit()
        git_modes = _git_tree_modes(commit) if commit else None
    digest = hashlib.sha256()
    for path in distribution_source_files():
        relative_text = path.relative_to(ROOT).as_posix()
        relative = relative_text.encode()
        if os.name == "posix":
            source_mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        else:
            source_mode = (git_modes or {}).get(relative_text)
            if source_mode not in {"100644", "100755"}:
                raise RuntimeError(f"distribution source mode is not reproducible: {relative_text}")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(source_mode.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _git_tree_matches(commit: str) -> bool:
    modes = _git_tree_modes(commit)
    if modes is None:
        return False
    for path in distribution_source_files():
        relative = path.relative_to(ROOT).as_posix()
        mode = modes.get(relative)
        if mode not in {"100644", "100755"}:
            return False
        if os.name == "posix" and bool(path.stat().st_mode & 0o111) != (mode == "100755"):
            return False
    return True


def source_identity():
    """Bind the install to a clean commit and complete distribution-tree digest."""
    commit = source_commit()
    remote = run_command(["git", "-C", str(ROOT), "remote", "get-url", "origin"], timeout=15)
    status = run_command(["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"], timeout=15)
    remote_url = remote.stdout.strip() if remote.returncode == 0 else None
    clean = status.returncode == 0 and not status.stdout.strip()
    commit_text = commit or ""
    advertised = run_command(["git", "-C", str(ROOT), "ls-remote", "origin"], timeout=30) if remote_url and commit_text else None
    remote_commit_advertised = bool(
        advertised
        and advertised.returncode == 0
        and any(line.split()[0].lower() == commit_text.lower() for line in advertised.stdout.splitlines() if line.split())
    )
    generated_artifacts = generated_distribution_artifacts()
    git_modes = _git_tree_modes(commit_text) if commit_text else None
    git_tree_matches = _git_tree_matches(commit_text) if commit_text else False
    try:
        tree_sha256 = source_tree_sha256(git_modes)
    except RuntimeError:
        tree_sha256 = None
    return {
        "path": str(ROOT),
        "commit": commit,
        "clean": clean,
        "distribution_tree_sha256": tree_sha256,
        "generated_cache_artifacts": generated_artifacts,
        "remote_commit_advertised": remote_commit_advertised,
        "git_tree_matches": git_tree_matches,
        "immutable": bool(clean and remote_url and commit and tree_sha256 and remote_commit_advertised and git_tree_matches and not generated_artifacts),
        "recommended_reproducible_checkout": (
            f"git clone --no-checkout {remote_url} executive-operator-blueprint && "
            f"git -C executive-operator-blueprint checkout --detach {commit}"
            if remote_url and commit and remote_commit_advertised and git_tree_matches else None
        ),
    }


def run_command(args, timeout=300):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)  # nosec B603
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(args, 127, "", f"missing executable: {exc.filename}")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "command timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 126, "", f"command failed: {type(exc).__name__}")


def parse_version(text):
    match = re.search(r"\bv?(\d+)\.(\d+)\.(\d+)\b", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def version_compatible(version, semantic_range=None):
    if version is None:
        return False
    semantic_range = semantic_range or compatibility_contract()["semantic_range"]
    for clause in semantic_range.split(","):
        match = re.fullmatch(r"\s*(>=|<=|>|<|==)\s*(\d+\.\d+\.\d+)\s*", clause)
        if not match:
            raise ValueError(f"unsupported semantic range clause: {clause}")
        operator, expected_text = match.groups()
        expected = tuple(int(part) for part in expected_text.split("."))
        if not {">=": version >= expected, "<=": version <= expected, ">": version > expected,
                "<": version < expected, "==": version == expected}[operator]:
            return False
    return True


def upstream_build(text):
    match = re.search(r"\bupstream\s+([0-9a-f]{8,40})\b", text or "", re.I)
    return match.group(1).lower() if match else None


def process_start(pid):
    """Return a Linux process birth token so PID reuse cannot inherit a lock."""
    try:
        return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None


def process_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, ValueError, OverflowError):
        return False


def hermes_version():
    result = run_command(["hermes", "--version"], timeout=30)
    text = (result.stdout or result.stderr).splitlines()
    return text[0] if result.returncode == 0 and text else None


def dependency_status():
    version_text = hermes_version()
    parsed = parse_version(version_text)
    semantic_compatible = version_compatible(parsed)
    build_validated = semantic_compatible and upstream_build(version_text) == TESTED_HERMES_BUILD
    missing = []
    if not shutil.which("hermes"):
        missing.append("Hermes executable")
    elif not semantic_compatible:
        missing.append(f"Hermes {TESTED_HERMES_RANGE}")
    elif not build_validated:
        missing.append(f"Hermes upstream build {TESTED_HERMES_BUILD} (mutating install/update and Verified claims require revalidation on other builds)")
    if sys.version_info < (3, 10):
        missing.append("Python >=3.10")
    return {
        "hermes_version": version_text or "unavailable",
        "hermes_semantic_compatible": semantic_compatible,
        "hermes_build_validated": build_validated,
        "hermes_compatible": bool(build_validated),
        "read_only_inspection_allowed": True,
        "python_supported": sys.version_info >= (3, 10),
        "missing": missing,
    }


def load_answers(path):
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("answers must be a YAML mapping")
    schema = json.loads(ANSWERS_SCHEMA.read_text())
    jsonschema.validate(data, schema)
    name = str(data.get("profile_name") or "")
    if not PROFILE_RE.fullmatch(name):
        raise ValueError("profile_name must be lowercase letters, numbers, or hyphens")
    return data


def profile_exists(name):
    return run_command(["hermes", "profile", "show", name], timeout=30).returncode == 0


def profile_root(name):
    result = run_command(["hermes", "profile", "show", name], timeout=30)
    if result.returncode == 0:
        match = re.search(r"^Path:\s+(.+)$", result.stdout, re.MULTILINE)
        if match:
            return Path(match.group(1).strip())
    return hermes_home() / "profiles" / name


def requested_packs(answers):
    packs = answers.get("capability_packs") or {}
    return sorted(name for name, state in packs.items() if state == "requested")


def credential_gates(answers):
    return sorted({str(item) for item in answers.get("credential_gates", [])})


def kanban_selected(answers):
    task_system = answers.get("task_system") or {}
    return bool(task_system.get("enabled") and task_system.get("canonical_store") == "hermes-kanban")


def kanban_commands(answers):
    if not kanban_selected(answers):
        return []
    board = str((answers.get("task_system") or {}).get("board") or "default")
    commands = [
        ["hermes", "kanban", "init"],
        ["hermes", "kanban", "boards", "list"],
    ]
    if board != "default":
        commands.append(["hermes", "kanban", "boards", "switch", board])
        commands.append(["hermes", "kanban", "--board", board, "stats"])
    else:
        commands.append(["hermes", "kanban", "stats"])
    return commands


def configure_kanban(answers):
    checks = []
    if not kanban_selected(answers):
        return checks, []
    for command in kanban_commands(answers):
        result = run_command(command, timeout=60)
        label = " ".join(command[2:])
        checks.append({"check": f"kanban {label}", "passed": result.returncode == 0, "exit_code": result.returncode})
        if result.returncode != 0:
            return checks, []
    board = str((answers.get("task_system") or {}).get("board") or "default")
    return checks, [f"native:hermes-kanban:{board}"]


def audit_profile(name):
    """Discover an install without reading private file contents or writing."""
    if not profile_exists(name):
        return {"discovery": "fresh-install", "profile_root": str(profile_root(name)), "preserved_user_state": []}
    root = profile_root(name)
    manifest_path = root / "distribution.yaml"
    manifest = {}
    try:
        manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.is_file() else {}
    except (OSError, yaml.YAMLError):
        pass
    private_names = (".env", "auth.json", "memories", "sessions", "logs", "state.db", "cron", "local", "workspace")
    preserved = [item for item in private_names if (root / item).exists() or (root / item).is_symlink()]
    return {
        "discovery": "existing-install",
        "profile_root": str(root),
        "distribution_name": manifest.get("name") if isinstance(manifest, dict) else None,
        "distribution_version": str(manifest.get("version")) if isinstance(manifest, dict) and manifest.get("version") is not None else None,
        "recorded_source": manifest.get("source") if isinstance(manifest, dict) else None,
        "preserved_user_state": preserved,
    }


def plan(answers):
    name = answers["profile_name"]
    exists = profile_exists(name)
    if answers.get("install_mode") == "update-profile":
        command = ["hermes", "profile", "update", name, "--yes"]
    else:
        command = ["hermes", "profile", "install", str(ROOT), "--name", name, "--alias", "--yes"]
    deps = dependency_status()
    source = source_identity()
    warnings = [f"Missing dependency: {item}" for item in deps["missing"]]
    if not source["immutable"]:
        warnings.append("Source checkout is uncommitted, dirty, contains generated or ignored-untracked files, differs from its platform-verifiable Git tree mode, lacks a remote-advertised exact commit, or is incomplete. Apply is blocked until the distribution tree is clean and reproducible.")
    return {
        "state": "planned" if not deps["missing"] else "dependency_blocked",
        "profile": name,
        "profile_exists": exists,
        "command": command,
        "post_install_commands": kanban_commands(answers),
        "requested_capability_packs": requested_packs(answers),
        "resolved_capability_packs": [],
        "writes": [f"Hermes profile {name}", "config.yaml permission hardening to 0600"],
        "preserves": ["credentials", "memory", "sessions", "logs", "runtime databases", "unrelated profiles"],
        "credential_gates": credential_gates(answers),
        "audit": audit_profile(name),
        "tested_hermes_range": TESTED_HERMES_RANGE,
        "tested_hermes_build": TESTED_HERMES_BUILD,
        "source": source,
        "warnings": warnings,
        "next": "Review this plan. Capability selections remain requested until onboarding configures and verifies them.",
    }


def default_report_path():
    run = f"install-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}.json"
    return hermes_home() / "install-state" / run


def report_path(value):
    return Path(value) if value else default_report_path()


def _secure_parent(path):
    path = Path(path)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise PermissionError(f"report directory is unsafe: {path}")
        if os.name == "posix" and (
            info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise PermissionError(f"report directory is not private: {path}")
        return
    path.mkdir(parents=True, mode=0o700)
    if os.name == "posix":
        info = path.lstat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise PermissionError(f"report directory is not private: {path}")


def write_report(path, data):
    path = Path(path)
    _secure_parent(path.parent)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(tmp, flags, 0o600)
    try:
        payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    if os.name == "posix":
        os.chmod(path, 0o600)


def normalized_report(result, answers):
    deps = dependency_status()
    standard_keys = {
        "state", "profile", "applied_assets", "credential_gates", "verification", "warnings",
        "rollback_point", "created_by_this_run", "run_id", "backup", "source_commit", "source_tree_sha256",
        "requested_capability_packs", "resolved_capability_packs", "profile_fingerprint",
    }
    return {
        "state": result.get("state", "failed"),
        "distribution_version": distribution_version(),
        "source_commit": result.get("source_commit") or source_commit(),
        "source_tree_sha256": result.get("source_tree_sha256") or source_identity().get("distribution_tree_sha256"),
        "hermes_version": deps["hermes_version"],
        "native_hermes_requirement": str(load_manifest().get("hermes_requires") or ""),
        "tested_hermes_range": TESTED_HERMES_RANGE,
        "tested_hermes_build": TESTED_HERMES_BUILD,
        "capability_status_authority": "contracts/capability-status.yaml",
        "capability_statuses": yaml.safe_load((ROOT / "contracts" / "capability-status.yaml").read_text(encoding="utf-8"))["statuses"],
        "platform": platform.platform(),
        "profile": result.get("profile") or answers.get("profile_name", "executive-operator"),
        "run_id": result.get("run_id"),
        "requested_capability_packs": result.get("requested_capability_packs", requested_packs(answers)),
        "resolved_capability_packs": result.get("resolved_capability_packs", []),
        "applied_assets": result.get("applied_assets", []),
        "dependencies": deps,
        "credential_gates": result.get("credential_gates", credential_gates(answers)),
        "verification": result.get("verification", []),
        "warnings": result.get("warnings", []),
        "rollback_point": result.get("rollback_point"),
        "created_by_this_run": bool(result.get("created_by_this_run", False)),
        "backup": result.get("backup"),
        "profile_fingerprint": result.get("profile_fingerprint"),
        "details": {key: value for key, value in result.items() if key not in standard_keys},
    }


@contextmanager
def profile_lock(name):
    directory = hermes_home() / "install-state"
    _secure_parent(directory)
    path = directory / f"profile-{name}.lock"
    payload = {"pid": os.getpid(), "process_start": process_start(os.getpid()), "created_at": now()}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or (os.name == "posix" and before.st_uid != os.geteuid()):
                raise RuntimeError(f"profile operation already locked: {name}")
            current = json.loads(path.read_text())
            pid = int(current["pid"])
            token = current.get("process_start")
            live_token = process_start(pid)
            alive = process_alive(pid)
            if alive and (live_token is None or token is None or str(live_token) == str(token)):
                raise RuntimeError(f"profile operation already locked: {name}")
            after = path.lstat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise RuntimeError(f"profile operation already locked: {name}")
            path.unlink()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except RuntimeError:
            raise
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as stale_exc:
            raise RuntimeError(f"profile operation already locked: {name}") from stale_exc
    try:
        os.write(fd, (json.dumps(payload, sort_keys=True) + "\n").encode())
        os.fsync(fd)
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def _backup_profile(name, run_id):
    directory = hermes_home() / "install-state" / "backups"
    _secure_parent(directory)
    staging = Path(tempfile.mkdtemp(prefix=f".{name}-{run_id}-", dir=directory))
    if os.name == "posix":
        os.chmod(staging, 0o700)
    path = staging / "profile.tar.gz"
    try:
        result = run_command(["hermes", "profile", "export", name, "--output", str(path)], timeout=300)
        if path.is_symlink() or not path.exists():
            raise RuntimeError("pre-update backup destination is missing or unsafe")
        current = os.lstat(path)
        if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
            raise RuntimeError("pre-update backup destination is not a regular file or has a hard link")
        if os.name == "posix" and current.st_uid != os.geteuid():
            raise RuntimeError("pre-update backup destination has the wrong owner")
        if result.returncode != 0 or current.st_size == 0:
            raise RuntimeError("pre-update Hermes profile export failed")

        os.chmod(path, 0o600)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise RuntimeError("pre-update backup changed before verification")
            os.fsync(fd)
        finally:
            os.close(fd)
        for parent in (staging, directory):
            directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        try:
            with tarfile.open(path, "r:gz") as archive:
                members = archive.getmembers()
                if not members:
                    raise RuntimeError("pre-update Hermes profile export is empty")
                for member in members:
                    parts = Path(member.name).parts
                    if member.name.startswith("/") or ".." in parts or member.issym() or member.islnk() or member.isdev():
                        raise RuntimeError("pre-update Hermes profile export contains an unsafe entry")
        except tarfile.TarError as exc:
            raise RuntimeError("pre-update Hermes profile export is not a valid archive") from exc
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def _profile_fingerprint(name):
    root = profile_root(name)
    manifest = root / "distribution.yaml"
    return {
        "profile_root": str(root),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None,
        "distribution_version": distribution_version(),
        "source_commit": source_commit(),
    }


def _write_install_marker(name, run_id, fingerprint):
    marker = profile_root(name) / "local" / "executive-operator-install.json"
    write_report(marker, {"run_id": run_id, "profile": name, "fingerprint": fingerprint, "created_at": now()})
    return marker


def _profile_is_pristine(name, run_id=None):
    """Return true only when a new profile contains distribution-owned data."""
    root = profile_root(name)
    manifest = root / "distribution.yaml"
    if not root.is_dir() or root.is_symlink() or not manifest.is_file() or manifest.is_symlink():
        return False
    owned = [
        Path(".env.EXAMPLE") if item.rstrip("/") == ".env.template" else Path(item.rstrip("/"))
        for item in (load_manifest().get("distribution_owned") or [])
    ]
    marker_relative = Path("local/executive-operator-install.json")
    bootstrap_directories = [
        Path(name) for name in (
            "memories", "sessions", "skins", "logs", "plans", "workspace", "cron", "home",
            "pairing", "audio_cache", "image_cache", "hooks",
        )
    ]
    native_bootstrap_files = {Path("logs/agent.log"), Path("logs/errors.log")}
    allowed = owned + bootstrap_directories + list(native_bootstrap_files) + ([marker_relative] if run_id else [])
    try:
        for path in root.rglob("*"):
            if path.is_symlink():
                return False
            relative = path.relative_to(root)
            if not any(relative == item or item in relative.parents or relative in item.parents for item in allowed):
                return False
            if path.is_file() and relative in native_bootstrap_files:
                continue
            if path.is_file() and relative != marker_relative:
                if relative == Path("distribution.yaml"):
                    installed_manifest = yaml.safe_load(path.read_text())
                    expected_manifest = load_manifest()
                    checked_fields = (
                        "version", "description", "author", "license", "hermes_requires",
                    )
                    if not isinstance(installed_manifest, dict):
                        return False
                    if installed_manifest.get("name") != name:
                        return False
                    if any(installed_manifest.get(field) != expected_manifest.get(field) for field in checked_fields):
                        return False
                    installed_owned = [str(item).rstrip("/") for item in installed_manifest.get("distribution_owned", [])]
                    expected_owned = [str(item).rstrip("/") for item in expected_manifest.get("distribution_owned", [])]
                    if installed_owned != expected_owned:
                        return False
                    if (installed_manifest.get("env_requires") or []) != (expected_manifest.get("env_requires") or []):
                        return False
                    source = installed_manifest.get("source")
                    if not source or Path(source).resolve() != ROOT.resolve():
                        return False
                    continue
                source = ROOT / (Path(".env.template") if relative == Path(".env.EXAMPLE") else relative)
                if not source.is_file() or source.is_symlink():
                    return False
                if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
                    return False
            elif not path.is_dir() and relative != marker_relative:
                return False
        if run_id:
            marker = root / marker_relative
            marker_data = json.loads(marker.read_text())
            if marker_data.get("run_id") != run_id or marker_data.get("profile") != name:
                return False
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return True


def _harden_config_permissions(path):
    """Set a trusted profile config owner-only through its open descriptor."""
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise PermissionError("config.yaml must be a regular file with one link")
    if os.name == "posix" and before.st_uid != os.geteuid():
        raise PermissionError("config.yaml has the wrong owner")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise PermissionError("config.yaml opened descriptor is unsafe or changed")
        if os.name == "posix":
            if opened.st_uid != os.geteuid():
                raise PermissionError("config.yaml opened descriptor has the wrong owner")
            os.fchmod(fd, 0o600)
            verified = os.fstat(fd)
            if verified.st_uid != os.geteuid() or stat.S_IMODE(verified.st_mode) != 0o600 or verified.st_nlink != 1:
                raise PermissionError("config.yaml permission hardening did not verify")
        os.fsync(fd)
    finally:
        os.close(fd)


def _secure_config_digest(path, *, parse=False):
    """Digest one owner-only regular config through a stable descriptor."""
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise PermissionError("config.yaml must be a regular file with one link")
    if os.name == "posix" and (before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) & 0o077):
        raise PermissionError("config.yaml must be owner-only")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        descriptor_safe = stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
        if os.name == "posix":
            descriptor_safe = descriptor_safe and opened.st_uid == os.geteuid() and not (stat.S_IMODE(opened.st_mode) & 0o077)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or not descriptor_safe:
            raise PermissionError("config.yaml opened descriptor is unsafe or changed")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    payload = b"".join(chunks)
    if parse:
        value = yaml.safe_load(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("config.yaml must parse as a mapping")
    return hashlib.sha256(payload).hexdigest()


def _distribution_checks(name, preserved_digests=None, *, owner_config_override=False):
    """Verify installed assets; updates may preserve owner-modified config."""
    preserved_digests = preserved_digests or {}
    show = run_command(["hermes", "profile", "show", name], timeout=30)
    info = run_command(["hermes", "profile", "info", name], timeout=30)
    root = profile_root(name)
    owned = load_manifest().get("distribution_owned") or []
    checks = [
        {"check": "profile show", "passed": show.returncode == 0},
        {"check": "distribution info", "passed": info.returncode == 0},
        {"check": "distribution version", "passed": distribution_version() in info.stdout},
    ]
    installed = []
    for relative in owned:
        clean = relative.rstrip("/")
        source = ROOT / clean
        installed_clean = ".env.EXAMPLE" if clean == ".env.template" else clean
        path = root / installed_clean
        if clean == "config.yaml" and owner_config_override:
            try:
                _secure_config_digest(path, parse=True)
                safe = True
            except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
                safe = False
            checks.append({"check": "config.yaml owner override safety", "passed": safe})
            native = run_command(["hermes", "-p", name, "config", "check"], timeout=60)
            checks.append({"check": "config.yaml native check", "passed": safe and native.returncode == 0})
            if safe:
                installed.append(installed_clean)
            continue
        passed = path.exists() and not path.is_symlink()
        checks.append({"check": installed_clean, "passed": passed})
        if not passed:
            continue
        installed.append(installed_clean)
        source_files = sorted(item for item in source.rglob("*") if item.is_file()) if source.is_dir() else ([source] if source.is_file() else [])
        for source_file in source_files:
            relative_file = source_file.relative_to(ROOT)
            target_relative = Path(".env.EXAMPLE") if relative_file == Path(".env.template") else relative_file
            target_file = root / target_relative
            same = target_file.is_file() and not target_file.is_symlink()
            preserved_digest = preserved_digests.get(target_relative.as_posix())
            if same and preserved_digest is not None:
                try:
                    same = _secure_config_digest(target_file, parse=True) == preserved_digest
                except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
                    same = False
            elif same and relative_file != Path("distribution.yaml"):
                same = hashlib.sha256(source_file.read_bytes()).digest() == hashlib.sha256(target_file.read_bytes()).digest()
            suffix = "preserved sha256" if preserved_digest is not None else "sha256"
            checks.append({"check": f"{target_relative.as_posix()} {suffix}", "passed": same})
    return checks, installed


def apply(answers, yes=False):
    if not yes:
        raise RuntimeError("apply requires --yes after plan review")
    deps = dependency_status()
    name = answers["profile_name"]
    if deps["missing"]:
        return {"state": "dependency_blocked", "profile": name, "warnings": [f"Missing dependency: {x}" for x in deps["missing"]]}
    source = source_identity()
    if not source["immutable"]:
        return {
            "state": "verification_blocked",
            "profile": name,
            "source_commit": source.get("commit"),
            "source_tree_sha256": source.get("distribution_tree_sha256"),
            "warnings": ["Apply requires a clean committed checkout whose exact commit is advertised by its remote, whose paths and platform-verifiable executable bits match that Git tree, with no generated or ignored-untracked artifacts and a complete distribution-tree digest."],
        }
    run_id = secrets.token_urlsafe(18)
    with profile_lock(name):
        existed = profile_exists(name)
        mode = answers.get("install_mode")
        if existed and mode != "update-profile":
            return {
                "state": "verification_blocked", "profile": name, "run_id": run_id,
                "created_by_this_run": False,
                "warnings": ["Profile already exists. Select update-profile only after review."],
            }
        if not existed and mode == "update-profile":
            return {"state": "verification_blocked", "profile": name, "run_id": run_id, "created_by_this_run": False, "warnings": ["Cannot update a missing profile."]}
        backup = _backup_profile(name, run_id) if existed else None
        preserved_digests = {}
        if existed:
            config_path = profile_root(name) / "config.yaml"
            if config_path.exists() or config_path.is_symlink():
                try:
                    _harden_config_permissions(config_path)
                    preserved_digests["config.yaml"] = _secure_config_digest(config_path, parse=True)
                except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
                    return {
                        "state": "verification_blocked", "profile": name, "run_id": run_id,
                        "backup": backup, "rollback_point": (backup or {}).get("path"),
                        "created_by_this_run": False,
                        "verification": [{"check": "pre-update config safety", "passed": False}],
                        "warnings": [f"Pre-update config safety validation failed: {type(exc).__name__}. No update was attempted."],
                    }
        command = ["hermes", "profile", "update", name, "--yes"] if existed else [
            "hermes", "profile", "install", str(ROOT), "--name", name, "--alias", "--yes"
        ]
        result = run_command(command)
        config_hardening_checks = []
        if result.returncode != 0:
            return {
                "state": "failed", "profile": name, "run_id": run_id, "backup": backup,
                "warnings": ["Native Hermes profile command failed."],
                "verification": [{"check": "profile command", "passed": False, "exit_code": result.returncode}],
            }
        if not existed:
            config_path = profile_root(name) / "config.yaml"
            if config_path.exists() or config_path.is_symlink():
                try:
                    _harden_config_permissions(config_path)
                    config_hardening_checks.append({"check": "config.yaml permission hardening", "passed": True})
                except (OSError, ValueError) as exc:
                    config_hardening_checks.append({"check": "config.yaml permission hardening", "passed": False, "error": type(exc).__name__})
        if preserved_digests:
            checks, installed = _distribution_checks(name, preserved_digests)
        else:
            checks, installed = _distribution_checks(name)
        checks = config_hardening_checks + checks
        if not all(item["passed"] for item in checks):
            if existed and backup:
                return {
                    "state": "verification_blocked", "profile": name, "run_id": run_id, "backup": backup,
                    "verification": checks,
                    "warnings": [
                        "Update verification failed. Stop using this profile and prepare a reviewed restore from the verified profile export. Automatic in-place restoration is intentionally not attempted."
                    ],
                    "created_by_this_run": False, "rollback_point": backup["path"],
                }
            if not _profile_is_pristine(name):
                return {
                    "state": "verification_blocked", "profile": name, "run_id": run_id,
                    "backup": backup, "verification": checks,
                    "warnings": [
                        "Distribution verification failed, but the new profile is not pristine. Automatic deletion was refused; preserve and review it manually."
                    ],
                    "created_by_this_run": False,
                }
            removed = run_command(["hermes", "profile", "delete", name, "--yes"], timeout=120)
            checks.append({"check": "automatic rollback of pristine profile", "passed": removed.returncode == 0})
            return {
                "state": "failed", "profile": name, "run_id": run_id, "backup": backup,
                "verification": checks, "warnings": ["Distribution verification failed after apply."],
                "created_by_this_run": False,
            }
        kanban_checks, kanban_assets = configure_kanban(answers)
        checks.extend(kanban_checks)
        if kanban_checks and not all(item["passed"] for item in kanban_checks):
            return {
                "state": "verification_blocked", "profile": name, "run_id": run_id, "backup": backup,
                "verification": checks,
                "warnings": ["Native Hermes Kanban initialization or readback failed. The profile remains preserved for review."],
                "created_by_this_run": not existed,
            }
        installed.extend(kanban_assets)
        fingerprint = _profile_fingerprint(name)
        marker = _write_install_marker(name, run_id, fingerprint) if not existed else None
        gates = credential_gates(answers)
        return {
            "state": "credential_blocked" if gates else "verified", "profile": name, "run_id": run_id,
            "created_by_this_run": not existed, "backup": backup, "profile_fingerprint": fingerprint,
            "source_commit": source["commit"], "source_tree_sha256": source["distribution_tree_sha256"],
            "applied_assets": installed, "resolved_capability_packs": [],
            "credential_gates": gates,
            "verification": checks,
            "warnings": ["The native Kanban task board is initialized. Other capability packs remain requested until onboarding and live tests."],
            "rollback_point": str(marker) if marker else (backup or {}).get("path"),
        }


def verify(answers):
    name = answers["profile_name"]
    deps = dependency_status()
    if deps["missing"]:
        return {"state": "dependency_blocked", "profile": name, "warnings": [f"Missing dependency: {x}" for x in deps["missing"]]}
    checks, installed = _distribution_checks(name, owner_config_override=True)
    kanban_checks, kanban_assets = configure_kanban(answers)
    checks.extend(kanban_checks)
    installed.extend(kanban_assets)
    passed = all(item["passed"] for item in checks)
    gates = credential_gates(answers)
    state = "verification_blocked" if not passed else ("credential_blocked" if gates else "verified")
    return {
        "state": state, "profile": name, "verification": checks, "credential_gates": gates,
        "applied_assets": installed, "resolved_capability_packs": [],
        "profile_fingerprint": _profile_fingerprint(name) if passed else None,
        "warnings": [] if passed else ["One or more distribution checks failed."],
    }


def rollback(answers, report, yes=False):
    if not yes:
        raise RuntimeError("rollback requires --yes")
    if not report:
        raise RuntimeError("rollback requires the exact protected apply report")
    data = json.loads(Path(report).read_text())
    name = answers["profile_name"]
    run_id = data.get("run_id")
    if data.get("profile") != name or not data.get("created_by_this_run") or not run_id:
        raise RuntimeError("refusing rollback without matching creation evidence")
    with profile_lock(name):
        root = profile_root(name)
        marker = root / "local" / "executive-operator-install.json"
        if not marker.is_file():
            raise RuntimeError("install marker missing")
        marker_data = json.loads(marker.read_text())
        if marker_data.get("run_id") != run_id or marker_data.get("profile") != name:
            raise RuntimeError("install marker does not match report")
        current = _profile_fingerprint(name)
        expected = data.get("profile_fingerprint")
        if expected and current.get("manifest_sha256") != expected.get("manifest_sha256"):
            raise RuntimeError("profile distribution identity changed after installation")
        if not _profile_is_pristine(name, run_id):
            raise RuntimeError("refusing rollback because the profile is not pristine; user or runtime data may exist")
        result = run_command(["hermes", "profile", "delete", name, "--yes"])
    return {"state": "rolled_back" if result.returncode == 0 else "failed", "profile": name, "run_id": run_id}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "plan", "apply", "verify", "verify-installed", "rollback"])
    parser.add_argument("--answers", default=str(DEFAULT_ANSWERS))
    parser.add_argument("--report")
    parser.add_argument("--yes", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        answers = load_answers(args.answers)
        if args.command == "inspect":
            deps = dependency_status()
            result = {
                "state": "planned" if not deps["missing"] else "dependency_blocked",
                "profile": answers["profile_name"], "audit": audit_profile(answers["profile_name"]), "plan": plan(answers),
                "warnings": [f"Missing dependency: {x}" for x in deps["missing"]],
            }
        elif args.command == "plan":
            result = plan(answers)
        elif args.command == "apply":
            result = apply(answers, args.yes)
        elif args.command in {"verify", "verify-installed"}:
            result = verify(answers)
        else:
            result = rollback(answers, args.report, args.yes)
        normalized = normalized_report(result, answers)
    except Exception as exc:
        answers = {"profile_name": "unknown", "capability_packs": {}, "credential_gates": []}
        normalized = normalized_report({"state": "failed", "warnings": [f"{type(exc).__name__}: {exc}"]}, answers)
    output = report_path(args.report)
    write_report(output, normalized)
    print(json.dumps({"state": normalized["state"], "report": str(output)}, sort_keys=True))
    if normalized["state"] in {"planned", "verified", "rolled_back"}:
        return 0
    if normalized["state"] in {"dependency_blocked", "credential_blocked", "verification_blocked"}:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
