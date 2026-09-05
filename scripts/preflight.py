#!/usr/bin/env python3
"""Read-only preflight for the Executive Operator Blueprint and host."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import stat
import subprocess  # nosec B404
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANSWERS = ROOT / "templates" / "install.answers.example.yaml"
AUTHORITY_MAP = ROOT / "contracts" / "authority-map.yaml"
REQUIRED = [
    "README.md", "AGENTS.md", "AI-INSTALL.md", "INSTALL.md", "ONBOARDING.md", "CAPABILITIES.md",
    "SOUL.md", "distribution.yaml", "config.yaml", "capabilities.yaml", "optional-packs.yaml",
    "skills/continuity/SKILL.md", "skills/integration-onboarding/SKILL.md",
    "skills/inbox-triage/SKILL.md", "skills/meeting-action-items/SKILL.md",
    "skills/document-action-items/SKILL.md", "skills/grounded-citations/SKILL.md",
    "skills/calendar-operations/SKILL.md",
    "templates/voice-profile.schema.json", "templates/correction-record.schema.json",
    "plugins/operator-control/corrections.py", "templates/daily-brief-routine.schema.json",
    "templates/daily-brief-routine.example.yaml", "templates/delivery-record.schema.json",

    "tools/operator-state/operator_state.py", "tools/operator-state/daily_use.py",
    "tools/operator-state/voice_profile.py", "tools/secure-credentials/README.md",
    "tools/artifact-storage/artifact_storage.py", "tools/artifact-storage/README.md",
    "templates/artifact-storage-contract.schema.json", "templates/artifact-storage-contract.example.yaml",
    "templates/capability-status.schema.json", "templates/business-lane-preservation.schema.json",
    "contracts/capability-status.yaml", "contracts/business-lane-preservation.yaml", "contracts/preflight-inventory.yaml",
    "contracts/evidence-authorities.json", "templates/evidence-authorities.schema.json",
    "tools/integration-contract/integration_contract.py", "tools/integration-contract/README.md",
    "tools/task-reconciliation/reconcile.py", "tools/task-reconciliation/README.md",
    "templates/specialist-contract.schema.json", "templates/specialist-retirement.schema.json",
    "templates/enforcement-coverage.schema.json", "contracts/enforcement-coverage.yaml",
    "plugins/operator-control/managed.py",
    "tools/website-watchdog/watchdog.py", "scripts/install_blueprint.py", "scripts/validate_blueprint.py",
    "tools/website-watchdog/registry.py", "tools/website-watchdog/repair.py",
    "tools/website-watchdog/notifications.py", "tools/website-watchdog/credential_delivery.py",
    "templates/website-registry.schema.json", "templates/website-registry.example.json",
    "tools/website-watchdog/repair-handoff.schema.json", "tools/website-watchdog/repair-handoff.example.json",
    "scripts/audit_public_release.py", "scripts/validate_skill_authority.py", "contracts/public-release-policy.yaml",
    "templates/public-release-policy.schema.json", "templates/public-release-audit-report.schema.json",
]
PACK_IMPORTS = {
    "secure-credentials": ["fastapi", "cryptography", "pydantic", "uvicorn"],
}


def command_info(name, args, timeout=60):
    executable = shutil.which(name)
    if not executable:
        return {"available": False, "path": None, "exit_code": 127, "output": "missing"}
    try:
        proc = subprocess.run([executable, *args], capture_output=True, text=True, timeout=timeout)  # nosec B603
        output = (proc.stdout or proc.stderr).strip().splitlines()
        return {"available": True, "path": executable, "exit_code": proc.returncode, "output": output[0] if output else ""}
    except subprocess.TimeoutExpired:
        return {"available": True, "path": executable, "exit_code": 124, "output": "timed out"}
    except OSError as exc:
        return {"available": True, "path": executable, "exit_code": 126, "output": type(exc).__name__}


def parse_version(text):
    match = re.search(r"\bv?(\d+)\.(\d+)\.(\d+)\b", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def parse_hermes_identity(text):
    build = re.search(r"\bupstream\s+([0-9a-f]{8,40})\b", text or "", re.I)
    return {
        "version": parse_version(text),
        "upstream_build": build.group(1).lower() if build else None,
    }


def compatibility_contract():
    return yaml.safe_load(AUTHORITY_MAP.read_text(encoding="utf-8"))["compatibility"]


def capability_status_contract():
    return yaml.safe_load((ROOT / "contracts" / "capability-status.yaml").read_text(encoding="utf-8"))["statuses"]


def version_in_range(version, semantic_range):
    """Evaluate the authority map's comma-separated semantic comparator range."""
    if version is None:
        return False
    for clause in semantic_range.split(","):
        match = re.fullmatch(r"\s*(>=|<=|>|<|==)\s*(\d+\.\d+\.\d+)\s*", clause)
        if not match:
            raise ValueError(f"unsupported semantic range clause: {clause}")
        operator, expected_text = match.groups()
        expected = tuple(int(part) for part in expected_text.split("."))
        comparisons = {
            ">=": version >= expected, "<=": version <= expected,
            ">": version > expected, "<": version < expected, "==": version == expected,
        }
        if not comparisons[operator]:
            return False
    return True


def module_info(name):
    return {"available": importlib.util.find_spec(name) is not None}


def writable_directory(path, private=False):
    """Inspect whether a directory is usable without creating or modifying it."""
    path = Path(path)
    try:
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise PermissionError("unsafe directory")
            if private and os.name == "posix" and info.st_uid != os.geteuid():
                raise PermissionError("directory is not owned by the current user")
            mode = stat.S_IMODE(info.st_mode)
            if private and os.name == "posix" and mode != 0o700:
                return {
                    "writable": False,
                    "path": str(path),
                    "mode": oct(mode),
                    "reason": "private directory must be owner-only mode 0700",
                    "remediation": f"After verifying ownership, set mode 0700 on {path}",
                }
            return {
                "writable": bool(os.access(path, os.W_OK | os.X_OK)),
                "path": str(path),
                "mode": oct(mode),
                "would_create": False,
            }
        ancestor = path.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise PermissionError("unsafe parent directory")
        return {
            "writable": bool(os.access(ancestor, os.W_OK | os.X_OK)),
            "path": str(path),
            "would_create": True,
            "nearest_existing_parent": str(ancestor),
        }
    except OSError as exc:
        return {"writable": False, "path": str(path), "error": type(exc).__name__, "reason": str(exc)}


def readable_directory(path):
    """Inspect a directory without creating files or changing metadata."""
    path = Path(path)
    try:
        info = path.lstat()
        safe = stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
        return {"readable": bool(safe and os.access(path, os.R_OK | os.X_OK)), "path": str(path)}
    except OSError as exc:
        return {"readable": False, "path": str(path), "error": type(exc).__name__}


def load_requested(path):
    data = yaml.safe_load(Path(path).read_text())
    packs = data.get("capability_packs", {}) if isinstance(data, dict) else {}
    return sorted(name for name, state in packs.items() if state == "requested"), data if isinstance(data, dict) else {}


def integration_semantic_errors(path, state_path=None):
    if path is None:
        path = ROOT / "templates" / "integration-registry.example.json"
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        module_path = ROOT / "tools" / "integration-contract" / "integration_contract.py"
        spec = importlib.util.spec_from_file_location("preflight_integration_semantics", module_path)
        if not spec or not spec.loader:
            raise ImportError("semantic validator unavailable")
        module = importlib.util.module_from_spec(spec)
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
        current_state = json.loads(Path(state_path).read_text(encoding="utf-8")) if state_path else None
        return module.validate_integration_record(record, current_state=current_state)
    except (OSError, ValueError, TypeError, ImportError) as exc:
        return [f"integration registry could not be validated: {type(exc).__name__}: {exc}"]


def run(repository_only=False, answers_path=DEFAULT_ANSWERS, integration_registry=None, integration_state=None):
    files = {relative: (ROOT / relative).is_file() for relative in REQUIRED}
    requested, answers = load_requested(answers_path)
    validator = command_info(sys.executable, [str(ROOT / "scripts" / "validate_blueprint.py")])
    git = command_info("git", ["--version"])
    hermes = {"available": False, "path": None, "exit_code": 127, "output": "not checked"}
    doctor = {"skipped": True}
    config = {"skipped": True}
    semantic_compatible = repository_only
    build_validated = repository_only
    compatible = repository_only
    compatibility = compatibility_contract()
    expected_build = compatibility["tested_upstream_build"]
    if not repository_only:
        hermes = command_info("hermes", ["--version"])
        identity = parse_hermes_identity(hermes["output"])
        semantic_compatible = bool(
            hermes["available"] and hermes["exit_code"] == 0
            and version_in_range(identity["version"], compatibility["semantic_range"])
        )
        build_validated = bool(semantic_compatible and identity["upstream_build"] == expected_build)
        compatible = semantic_compatible and build_validated
        if semantic_compatible:
            doctor = command_info("hermes", ["doctor"], timeout=120)
            config = command_info("hermes", ["config", "check"], timeout=120)
    dependencies = {"yaml": module_info("yaml"), "jsonschema": module_info("jsonschema")}
    for pack in requested:
        for module in PACK_IMPORTS.get(pack, []):
            dependencies[module] = module_info(module)
    profile_name = str(answers.get("profile_name") or "executive-operator")
    collision = False
    if not repository_only and compatible:
        collision = command_info("hermes", ["profile", "show", profile_name], timeout=30)["exit_code"] == 0
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    if repository_only:
        paths = {
            "repository": readable_directory(ROOT),
            "install_state": {"skipped": True, "path": str(home / "install-state")},
        }
    else:
        paths = {
            "repository": writable_directory(ROOT),
            "install_state": writable_directory(home / "install-state", private=True),
        }
    blockers = []
    registry_errors = integration_semantic_errors(integration_registry, integration_state)
    if registry_errors:
        blockers.append("Integration registry semantic validation failed.")
    if validator["exit_code"] != 0:
        blockers.append("Repository validation failed.")
    if not git["available"]:
        blockers.append("Install Git.")
    if sys.version_info < (3, 10):
        blockers.append("Use Python 3.10 or newer.")
    if not all(files.values()):
        blockers.append("Restore missing repository files.")
    for name, state in dependencies.items():
        if not state["available"]:
            blockers.append(f"Install Python dependency: {name}.")
    if repository_only:
        if not paths["repository"]["readable"]:
            blockers.append("Fix repository read permissions.")
    elif not all(item["writable"] for item in paths.values()):
        blockers.append("Fix repository or install-state write permissions.")
    if not repository_only:
        if not semantic_compatible:
            blockers.append(f"Install a compatible Hermes version: {compatibility['semantic_range']}.")
        elif not build_validated:
            blockers.append(f"Hermes upstream build must be {expected_build}; read-only inspection remains allowed, but installation, update, and Verified claims are blocked until revalidated.")
        elif doctor["exit_code"] != 0:
            blockers.append("Resolve Hermes doctor findings.")
        elif config["exit_code"] != 0:
            blockers.append("Resolve Hermes configuration findings.")
        if collision and answers.get("install_mode") == "new-profile":
            blockers.append(f"Profile {profile_name} already exists. Choose another name or review update mode.")
    state = "repository_ready" if repository_only and not blockers else ("ready_for_onboarding" if not blockers else "dependency_blocked")
    return {
        "state": state,
        "platform": platform.platform(),
        "python": {"version": platform.python_version(), "supported": sys.version_info >= (3, 10)},
        "git": git,
        "hermes": hermes,
        "hermes_compatible": compatible,
        "hermes_semantic_compatible": semantic_compatible,
        "hermes_build_validated": build_validated,
        "read_only_inspection_allowed": True,
        "mutations_allowed": bool(not repository_only and compatible),
        "doctor": doctor,
        "config_check": config,
        "requested_capability_packs": requested,
        "dependencies": dependencies,
        "profile_name": profile_name,
        "profile_collision": collision,
        "required_files": files,
        "paths": paths,
        "blockers": blockers,
        "integration_registry_errors": registry_errors,
        "repository_only": repository_only,
        "capability_status_authority": "contracts/capability-status.yaml",
        "capability_statuses": capability_status_contract(),
        "operator_control": {
            "enabled": False,
            "high_assurance_secret_boundary": "required-unconfigured",  # nosec B105  # pragma: allowlist secret -- status label
            "high_assurance_credential_boundary": "required-unconfigured",
            "high_assurance_boundary": "required-unconfigured",
            "generic_terminal_browser_coverage": "blocked",
            "direct_kanban_transition_gate": "observer-only",
        },
        "optional_integrations": {
            "composio": {"configured": False, "enabled": False},
            "google_sheets": {"configured": False, "enabled": False},
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repository-only", action="store_true")
    parser.add_argument("--answers", default=str(DEFAULT_ANSWERS))
    parser.add_argument("--integration-registry")
    parser.add_argument("--integration-state", help="read-only current adapter/approval state for Verified records")
    parser.add_argument("--public-release-audit", action="store_true", help="explicitly run the online, read-only GitHub release audit")
    args = parser.parse_args(argv)
    result = run(args.repository_only, args.answers, args.integration_registry, args.integration_state)
    if args.public_release_audit:
        audit = command_info(sys.executable, [str(ROOT / "scripts" / "audit_public_release.py")], timeout=180)
        result["public_release_audit"] = audit
        if audit["exit_code"] != 0:
            result["blockers"].append("Public release audit did not pass; inspect its standalone JSON report.")
            result["state"] = "dependency_blocked"
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("Executive Operator Blueprint Preflight")
        print(f"State: {result['state']}")
        for item in result["blockers"]:
            print(f"Blocker: {item}")
    return 0 if result["state"] in {"repository_ready", "ready_for_onboarding"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
