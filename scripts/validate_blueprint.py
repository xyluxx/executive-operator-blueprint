#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from urllib.parse import unquote

import jsonschema
import yaml

REQUIRED_FILES = [
    "README.md", "AGENTS.md", "AI-INSTALL.md", "INSTALL.md", "ONBOARDING.md", "CAPABILITIES.md", "SOUL.md",
    "SECURITY.md", "CONTRIBUTING.md", "SUPPORT.md",
    "distribution.yaml", "config.yaml", "capabilities.yaml", "optional-packs.yaml", "contracts/authority-map.yaml", "requirements-dev.txt", "requirements-dev.lock",
    "contracts/capability-status.yaml", "contracts/business-lane-preservation.yaml", "contracts/preflight-inventory.yaml",
    "pyproject.toml", ".secrets.baseline",
    ".github/workflows/validate.yml", ".env.template", ".no-bundled-skills",
    "assets/executive-operator.svg", "assets/executive-operator-mobile.svg", "assets/README.md",
    "scripts/preflight.py", "scripts/install_blueprint.py", "scripts/validate_blueprint.py", "scripts/validate_skill_authority.py", "scripts/audit_public_release.py",
    "contracts/public-release-policy.yaml", "templates/public-release-policy.schema.json", "templates/public-release-audit-report.schema.json",
    "templates/integration-registry.schema.json", "templates/integration-registry.example.json",
    "contracts/evidence-authorities.json", "templates/evidence-authorities.schema.json",
    "templates/website-registry.schema.json", "templates/website-registry.example.json",
    "templates/extension-registry.schema.json", "templates/capability-selection.example.yaml",
    "templates/credential-requirements.schema.json", "templates/install-report.schema.json",
    "templates/install.answers.example.yaml", "templates/install.answers.schema.json", "templates/optional-packs.schema.json",
    "templates/resolved-capability.schema.json", "templates/resolved-capability.example.yaml",
    "templates/capabilities.schema.json", "templates/notification-policy.example.yaml",
    "templates/voice-profile.schema.json", "templates/correction-record.schema.json",
    "plugins/operator-control/corrections.py", "templates/daily-brief-routine.schema.json",
    "templates/daily-brief-routine.example.yaml", "templates/delivery-record.schema.json",
    "templates/capability-status.schema.json", "templates/business-lane-preservation.schema.json",
    "templates/pr-brief.template.yaml", "templates/crm-adapter.template.yaml",
    "templates/install-report.template.md", "templates/mcp.example.json",
    "contracts/task-lifecycle.yaml", "templates/task-lifecycle.schema.json",
    "templates/task-contract.schema.json", "templates/task-contract.compact.example.yaml",
    "templates/task-contract.full.example.yaml",
    "templates/criterion.schema.json", "templates/verification-result.schema.json",
    "templates/acceptance-record.schema.json", "templates/acceptance-policy.schema.json",
    "templates/rework-brief.schema.json", "tools/operator-control/acceptance.py",

    "tools/operator-state/operator_state.py", "tools/operator-state/daily_use.py",
    "tools/operator-state/voice_profile.py", "tools/operator-state/README.md",
    "templates/artifact-storage-contract.schema.json", "templates/artifact-storage-contract.example.yaml",
    "tools/artifact-storage/artifact_storage.py", "tools/artifact-storage/README.md",
    "tools/task-reconciliation/reconcile.py", "tools/task-reconciliation/README.md",
    "templates/specialist-contract.schema.json", "templates/specialist-retirement.schema.json",
    "templates/enforcement-coverage.schema.json", "contracts/enforcement-coverage.yaml",
    "plugins/operator-control/managed.py",
    "templates/authority-map.schema.json",
    "tools/secure-credentials/secure_credentials/app.py", "tools/secure-credentials/secure_credentials/store.py",
    "tools/secure-credentials/secure_credentials/vault.py", "tools/secure-credentials/secure_credentials/crypto.py",
    "tools/secure-credentials/secure_credentials/cli.py", "tools/secure-credentials/secure_credentials/static/crypto.js",
    "tools/secure-credentials/secure_credentials/static/app.css", "tools/secure-credentials/bootstrap.py",
    "tools/secure-credentials/pyproject.toml", "tools/secure-credentials/README.md",
    "tools/secure-credentials/requirements.txt", "tools/secure-credentials/requirements.lock",
    "tools/website-watchdog/watchdog.py", "tools/website-watchdog/deadman.py",
    "tools/website-watchdog/README.md",
    "tools/website-watchdog/incident.py", "tools/website-watchdog/sites.example.json",
    "tools/website-watchdog/sites.schema.json", "tools/website-watchdog/incident.schema.json",
    "tools/integration-contract/integration_contract.py", "tools/integration-contract/README.md",
    "tools/website-watchdog/registry.py", "tools/website-watchdog/repair.py",
    "tools/website-watchdog/notifications.py", "tools/website-watchdog/credential_delivery.py",
    "tools/website-watchdog/repair-handoff.schema.json", "tools/website-watchdog/repair-handoff.example.json",
]
REQUIRED_DOCS = [f"docs/{number:02d}-{slug}.md" for number, slug in [
    (0, "capability-matrix"), (1, "foundation"), (2, "memory"),
    (3, "tasks-and-scheduling"), (4, "delegation"), (5, "integrations-and-skills"),
    (6, "guardrails-and-recovery"), (7, "cost-and-efficiency"), (8, "human-side"),
    (9, "roadmap-and-honesty"), (10, "operator-foundation-and-lanes"),
    (11, "native-integrations-and-extensions"), (12, "operator-lifecycle-and-recovery"),
    (13, "installation-and-conformance"), (14, "channels-and-devices"),
    (15, "provider-adapters"), (16, "secure-credentials"), (17, "autopilot-and-recovery"),
    (18, "single-agent-and-managed-team"), (19, "business-capability-packs"),
    (20, "skills-and-self-evolution"), (21, "reference-deployment"),
    (22, "examples-and-edge-cases"),
    (23, "task-truth-and-kanban"), (24, "artifacts-and-storage"),
    (25, "composio"), (26, "persistence-recipes"),
]]
REQUIRED_SKILLS = [
    "continuity", "integration-onboarding", "inbox-triage",
    "meeting-action-items", "document-action-items", "grounded-citations",
    "calendar-operations",
]
REQUIRED_SCHEMAS = [
    "templates/authority-map.schema.json",
    "templates/action-intent.schema.json", "templates/action-result.schema.json",
    "templates/approval-record.schema.json",
    "templates/integration-registry.schema.json", "templates/extension-registry.schema.json",
    "templates/evidence-authorities.schema.json", "templates/executive-operator-conformance.schema.json",
    "templates/credential-requirements.schema.json", "templates/install-report.schema.json",
    "templates/install.answers.schema.json", "templates/capabilities.schema.json", "templates/optional-packs.schema.json",
    "templates/resolved-capability.schema.json", "templates/task-lifecycle.schema.json",
    "templates/task-contract.schema.json", "templates/criterion.schema.json",
    "templates/verification-result.schema.json", "templates/acceptance-record.schema.json",
    "templates/acceptance-policy.schema.json", "templates/rework-brief.schema.json",
    "templates/artifact-storage-contract.schema.json",
    "templates/voice-profile.schema.json", "templates/daily-brief-routine.schema.json",
    "templates/correction-record.schema.json",
    "templates/delivery-record.schema.json",
    "templates/specialist-contract.schema.json", "templates/specialist-retirement.schema.json",
    "templates/enforcement-coverage.schema.json",
    "templates/capability-status.schema.json", "templates/business-lane-preservation.schema.json",
    "templates/website-registry.schema.json",
    "templates/public-release-policy.schema.json", "templates/public-release-audit-report.schema.json",
    "tools/website-watchdog/sites.schema.json", "tools/website-watchdog/incident.schema.json",
    "tools/website-watchdog/repair-handoff.schema.json",
]
FORBIDDEN_BINARY_EXTENSIONS = {".pyc", ".db", ".sqlite", ".zip", ".tar", ".gz", ".key", ".pem"}
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "OpenAI style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "Stripe live key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "bearer token": re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "API key assignment": re.compile(r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"),
    "encoded private key": re.compile("LS0tLS1CRUdJTi" + "BQUklWQVRFIEtF"),
}
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
ABSOLUTE_PRIVATE_PATH_RE = re.compile(r"(?<![\w])/(?:home|Users|root|opt|srv|var/www|etc)/[^\s`\"']+")
WINDOWS_PRIVATE_PATH_RE = re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\s`\"']+")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_CANDIDATE_RE = re.compile(r"(?<![\w:])[0-9A-Fa-f:]*:[0-9A-Fa-f:]+(?![\w:])")
SENSITIVE_FILENAMES = {".env", "auth.json", "credentials.json", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
LOCAL_ARTIFACT_DIRS = {".venv", "venv", "build", "dist", ".tox", ".eggs", "node_modules"}
PUBLIC_EXAMPLE_IPV4 = {"93.184.216.34"}
FORBIDDEN_SCHEMA_KEYS = {"api_key", "token", "password", "secret_value", "credential_value"}
LIFECYCLE_CATEGORIES = (
    "human_states", "native_statuses", "dispositions",
    "verification_results", "external_effect_results",
)
LIFECYCLE_REFERENCE_RE = re.compile(r"<!-- lifecycle-contract: (\{.*?\}) -->")
CAPABILITY_STATUS_REFERENCE_RE = re.compile(r"<!-- capability-status-contract: (\{.*?\}) -->")


def integration_semantic_errors(root: Path, record: dict) -> list[str]:
    module_path = root / "tools" / "integration-contract" / "integration_contract.py"
    spec = importlib.util.spec_from_file_location("blueprint_integration_semantics", module_path)
    if not spec or not spec.loader:
        return ["integration semantic validator could not be loaded"]
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module.validate_integration_record(record)


def parse_manifest(path: Path):
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return value


def markdown_links(text: str):
    links = []
    for target in re.findall(r"(?<!!)[^\]]*\]\(([^)]+)\)", text):
        target = target.strip().split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        links.append(unquote(target))
    for target in re.findall(r"<img[^>]+src=[\"']([^\"']+)[\"']", text, flags=re.I):
        if not target.startswith(("http://", "https://")):
            links.append(unquote(target.split("#", 1)[0]))
    return links


def documentation_link_errors(root: Path, text_files: list[Path]) -> list[str]:
    errors = []
    for path in text_files:
        if path.suffix.lower() != ".md":
            continue
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        links = markdown_links(text)
        exact_links = re.findall(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)", text)
        normalized_links = [(label, unquote(target.strip())) for label, target in exact_links]
        for exact in sorted(set(normalized_links)):
            if exact[1] and normalized_links.count(exact) > 1:
                errors.append(f"duplicate documentation link in {relative}: {exact[1]}")
        for target in links:
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                errors.append(f"repository link escapes root in {relative}: {target}")
                continue
            if not resolved.exists():
                errors.append(f"broken link in {relative}: {target}")

    return errors


def _configured_empty(value) -> bool:
    if isinstance(value, dict):
        if str(value.get("status", "")).lower() == "configured" and any(child in ({}, []) for key, child in value.items() if key != "status"):
            return True
        return any(_configured_empty(child) for child in value.values())
    if isinstance(value, list):
        return any(_configured_empty(child) for child in value)
    return False


def documentation_drift_errors(root: Path) -> list[str]:
    """Validate cross-document claims against the authority contract."""
    errors = []
    try:
        authority = parse_manifest(root / "contracts" / "authority-map.yaml")
        schema = json.loads((root / "templates" / "authority-map.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(authority, schema)
    except Exception as exc:
        return [f"authority map validation failed: {exc}"]

    lifecycle_path = root / authority["task_vocabulary"]["normative_home"]
    lifecycle = parse_manifest(lifecycle_path)
    task_doc = (root / "docs" / "23-task-truth-and-kanban.md").read_text(encoding="utf-8")
    for status in lifecycle["native_statuses"]:
        if f"`{status}`" not in task_doc:
            errors.append(f"task vocabulary mismatch: native status {status} is absent from docs/23")

    distribution = parse_manifest(root / "distribution.yaml")
    for claimed in distribution.get("distribution_owned") or []:
        if not (root / claimed.rstrip("/")).exists():
            errors.append(f"manifest claim references missing bundled path: {claimed}")

    capabilities = parse_manifest(root / "capabilities.yaml")
    for name, pack in (capabilities.get("capability_packs") or {}).items():
        if pack.get("blueprint_status") == "Verified" and not pack.get("proof"):
            errors.append(f"capability proof missing for verified capability: {name}")

    status_contract = parse_manifest(root / "contracts" / "capability-status.yaml")
    canonical_statuses = status_contract.get("statuses")
    canonical_status_set = set(canonical_statuses or [])
    status_authorities = [item for item in authority["authorities"] if item.get("concept") == "capability-status-taxonomy"]
    if len(status_authorities) != 1 or status_authorities[0].get("normative_home") != "contracts/capability-status.yaml":
        errors.append("capability status authority must name contracts/capability-status.yaml exactly once")
    if capabilities.get("status_labels") != canonical_statuses:
        errors.append("capability status taxonomy drift")
    for name, pack in (capabilities.get("capability_packs") or {}).items():
        if pack.get("blueprint_status") not in canonical_statuses:
            errors.append(f"non-canonical capability status for {name}")
    for relative in ("README.md", "CAPABILITIES.md", "docs/09-roadmap-and-honesty.md"):
        references = CAPABILITY_STATUS_REFERENCE_RE.findall((root / relative).read_text(encoding="utf-8"))
        if len(references) != 1:
            errors.append(f"missing or duplicate capability status reference in {relative}")
            continue
        try:
            reference = json.loads(references[0])
        except json.JSONDecodeError:
            errors.append(f"invalid capability status reference in {relative}")
            continue
        if reference != {"authority": "contracts/capability-status.yaml", "statuses": canonical_statuses}:
            errors.append(f"capability status reference drift in {relative}")
    report_schema = json.loads((root / "templates" / "install-report.schema.json").read_text(encoding="utf-8"))
    if report_schema.get("properties", {}).get("capability_statuses", {}).get("const") != canonical_statuses:
        errors.append("capability status drift in installer report schema")
    preflight_source = (root / "scripts" / "preflight.py").read_text(encoding="utf-8")
    if '"capability_status_authority": "contracts/capability-status.yaml"' not in preflight_source or '"capability_statuses": capability_status_contract()' not in preflight_source:
        errors.append("capability status drift in preflight output")

    matrix_text = (root / "docs" / "00-capability-matrix.md").read_text(encoding="utf-8")
    matrix_section = matrix_text.split("| Capability |", 1)[1].split("## Classification rule", 1)[0]
    matrix_rows = [line for line in matrix_section.splitlines() if line.startswith("|")][1:]
    for row in matrix_rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if len(cells) != 7:
            errors.append("capability matrix row does not have seven columns")
            continue
        if cells[1] not in canonical_status_set:
            errors.append(f"capability matrix label is non-canonical: {cells[1] or '<blank>'}")
        if not cells[6] or not re.fullmatch(r"\[[^]]+\]\([^)]+\)", cells[6]):
            errors.append(f"capability matrix official reference is blank or malformed: {cells[0] or '<blank>'}")

    coverage = authority["schema_test_coverage"]
    schemas = {path.relative_to(root).as_posix() for path in root.rglob("*.schema.json")}
    if set(coverage) != schemas:
        errors.append("schema coverage map does not exactly match schema files")
    for schema_path, tests in coverage.items():
        if not (root / schema_path).is_file() or any(not (root / test).is_file() for test in tests):
            errors.append(f"schema coverage references missing schema or test: {schema_path}")

    text_files = [path for path in root.rglob("*.md") if ".git" not in path.parts]
    errors.extend(documentation_link_errors(root, text_files))
    errors.extend(alternate_task_authority_errors(root, text_files))

    for path in list(root.rglob("*.json")) + list(root.rglob("*.yaml")) + list(root.rglob("*.yml")):
        if ".git" in path.parts:
            continue
        try:
            value = json.loads(path.read_text()) if path.suffix == ".json" else yaml.safe_load(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError):
            continue
        if _configured_empty(value):
            errors.append(f"empty config claim represented as configured: {path.relative_to(root)}")

    internal_label = re.compile(r"(?i)(?:\bv(?:[2-9]|[1-9]\d+)(?:\.\d+(?:\.\d+)?)?\b|\b(?:[2-9]|[1-9]\d+)\.0\.x\b|internal[- ]generation)")
    for path in text_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if internal_label.search(text):
            errors.append(f"internal-generation label in public file: {path.relative_to(root)}")

    expected_range = authority["compatibility"]["semantic_range"]
    expected_build = authority["compatibility"]["tested_upstream_build"]
    consumers = authority["compatibility"]["consumers"]
    for relative, claims in consumers.items():
        source = (root / relative).read_text(encoding="utf-8")
        if claims.get("semantic_range") and expected_range not in source:
            errors.append(f"build mismatch in {relative}: semantic range")
        if claims.get("tested_upstream_build"):
            build_claims = set(re.findall(r"(?i)\b[0-9a-f]{8}\b", source))
            if expected_build not in source or any(value.lower() != expected_build.lower() for value in build_claims):
                errors.append(f"build mismatch in {relative}: tested upstream build")
        if claims.get("authority_loaded") and "tested_upstream_build" not in source:
            errors.append(f"build mismatch in {relative}: compatibility authority is not loaded")
    if capabilities.get("reviewed_with_hermes") != expected_range or capabilities.get("reviewed_upstream_build") != expected_build:
        errors.append("build mismatch between capabilities.yaml and compatibility authority")
    return errors


ALTERNATE_TASK_SYSTEM_RE = re.compile(
    r"\b(?:an?\s+|the\s+|that\s+|this\s+|existing\s+|selected\s+|external\s+|optional\s+)*"
    r"(?:CRM|project(?:\s+management)?\s+system|task\s+system|external\s+system)s?\b",
    re.I,
)
TASK_AUTHORITY_ROLE_RE = re.compile(
    r"\b(?:the\s+)?(?:one\s+|sole\s+)?(?:canonical\s+)?task(?:-lifecycle|\s+lifecycle)?\s+"
    r"(?:authority|record|system(?:\s+of\s+record)?)\b|\b(?:canonical|authoritative)\s+task\s+record\b",
    re.I,
)
AUTHORITY_ASSIGNMENT_RE = re.compile(
    r"\b(?:is|are|be|become|becomes|remain|remains|serve|serves|act|acts|select|selects|selected|"
    r"designate|designates|designated|make|makes|made|use|uses|used)\b",
    re.I,
)
EXPLICIT_AUTHORITY_NEGATION_RE = re.compile(
    r"\b(?:not|never|no)\b(?:\W+\w+){0,5}\W+(?:the\s+)?(?:one\s+|sole\s+)?(?:canonical\s+)?"
    r"task(?:-lifecycle|\s+lifecycle)?\s+(?:authority|record|system(?:\s+of\s+record)?)\b|"
    r"\b(?:not|never|no)\b(?:\W+\w+){0,5}\W+(?:alternate\s+)?lifecycle\s+authorit(?:y|ies)\b",
    re.I,
)
ALLOWED_EXTERNAL_ROLE_RE = re.compile(
    r"\b(?:may\s+)?only\s+be\s+(?:migration\s+inputs?|derived/reference\s+integrations?)\b|"
    r"\b(?:migration\s+inputs?|derived/reference\s+integrations?)\s+only\b",
    re.I,
)


def alternate_task_authority_errors(root: Path, documents: list[Path]) -> list[str]:
    """Reject prose that assigns task lifecycle authority to a non-native system."""
    errors = []
    for path in documents:
        text = path.read_text(encoding="utf-8")
        for statement in re.split(r"(?<=[.!?])\s+|\n+", text):
            if not statement.strip() or statement.rstrip().endswith("?"):
                continue
            systems = list(ALTERNATE_TASK_SYSTEM_RE.finditer(statement))
            roles = [
                role for role in TASK_AUTHORITY_ROLE_RE.finditer(statement)
                if not re.search(r"\bnative\s+(?:Hermes\s+)?Kanban\b", statement[max(0, role.start() - 100):role.start()], re.I)
            ]
            if not systems or not roles or not AUTHORITY_ASSIGNMENT_RE.search(statement):
                continue
            if EXPLICIT_AUTHORITY_NEGATION_RE.search(statement) or ALLOWED_EXTERNAL_ROLE_RE.search(statement):
                continue
            if any(abs(system.start() - role.start()) <= 240 for system in systems for role in roles):
                errors.append(f"alternate task authority in public file: {path.relative_to(root)}")
                break
    return errors


def nested_forbidden(value, path=""):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            current = f"{path}.{key}" if path else str(key)
            if str(key).lower() in FORBIDDEN_SCHEMA_KEYS:
                findings.append(current)
            findings.extend(nested_forbidden(child, current))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(nested_forbidden(child, f"{path}[{index}]"))
    return findings


def git(root: Path, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)  # nosec B603 B607


def scan_public_files(root: Path) -> tuple[list[str], list[Path]]:
    """Scan every UTF-8 regular file and every repository-relative filename."""
    errors: list[str] = []
    text_files: list[Path] = []
    for path in root.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in LOCAL_ARTIFACT_DIRS:
            continue
        if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} for part in path.parts):
            continue
        if path.is_symlink():
            errors.append(f"symlink is not allowed in release: {relative}")
            continue
        if path.suffix.lower() in FORBIDDEN_BINARY_EXTENSIONS:
            errors.append(f"runtime or sensitive artifact in repository: {relative}")
        relative_text = relative.as_posix()
        if path.name.lower() in SENSITIVE_FILENAMES or "Users" in relative.parts:
            label = "machine-specific Windows path in filename" if "Users" in relative.parts else "sensitive filename"
            errors.append(f"{label}: {relative_text}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        text_files.append(path)
        if text and not text.endswith("\n"):
            errors.append(f"missing trailing newline: {relative}")
        decoded_text = unquote(text)
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text) or (decoded_text != text and pattern.search(decoded_text)):
                errors.append(f"possible {label} in {relative}")
        for domain in EMAIL_RE.findall(text):
            if not (domain.endswith("example.com") or domain.endswith("example.test") or domain == "users.noreply.github.com"):
                errors.append(f"non-example email address in {relative}")
        if ABSOLUTE_PRIVATE_PATH_RE.search(decoded_text):
            errors.append(f"machine-specific absolute path in {relative}")
        if WINDOWS_PRIVATE_PATH_RE.search(decoded_text):
            errors.append(f"machine-specific Windows path in {relative}")
        for address in IPV4_RE.findall(text):
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if not (parsed.is_loopback or parsed.is_unspecified or parsed.is_private or parsed.is_reserved or address in PUBLIC_EXAMPLE_IPV4):
                errors.append(f"non-loopback IP address in {relative}")
        for candidate in IPV6_CANDIDATE_RE.findall(text):
            try:
                parsed = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if not (parsed.is_loopback or parsed.is_unspecified):
                errors.append(f"non-loopback IPv6 address in {relative}")
        if path.suffix.lower() == ".md":
            for target in markdown_links(text):
                resolved = (path.parent / target).resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    errors.append(f"repository link escapes root in {relative}: {target}")
                    continue
                if not resolved.exists():
                    errors.append(f"broken repository link in {relative}: {target}")
    return errors, text_files


def release_cache_directories(root: Path, name: str) -> list[Path]:
    """Find release caches, excluding root-local dependency/build trees."""
    found = []
    for path in root.rglob(name):
        relative = path.relative_to(root)
        if path.is_dir() and not (relative.parts and relative.parts[0] in LOCAL_ARTIFACT_DIRS):
            found.append(path)
    return sorted(found)


def lifecycle_reference_block(categories: dict[str, list[str]], authority="contracts/task-lifecycle.yaml", mappings=None) -> str:
    """Render the deterministic machine-readable documentation contract."""
    payload = {"authority": authority, "categories": categories}
    if mappings is not None:
        payload["mappings"] = mappings
    return f"<!-- lifecycle-contract: {json.dumps(payload, separators=(',', ':'))} -->\n"


def lifecycle_drift_errors(contract_path: Path, documents: list[Path], require_mappings=False) -> list[str]:
    """Validate explicit lifecycle declarations, avoiding guesses about ordinary prose."""
    contract = parse_manifest(contract_path)
    vocabulary = set().union(*(set(contract.get(category) or []) for category in LIFECYCLE_CATEGORIES))
    declaration_patterns = (
        re.compile(r"\b(?:native(?:\s+Kanban)?\s+)?(?:status|state)\s+(?:to\s+)?`([^`]+)`", re.I),
        re.compile(r"\bwork\s+is\s+now\s+`([^`]+)`", re.I),
        re.compile(r"\bstatuses\s*:\s*([^\n.]+)", re.I),
    )
    mapping_pattern = re.compile(r"\bmappings?\s*:\s*([a-z][a-z0-9-]*)\s*(?:->|=>|to)\s*`?([a-z][a-z0-9-]*)`?", re.I)
    errors = []
    for path in documents:
        text = path.read_text(encoding="utf-8")
        matches = LIFECYCLE_REFERENCE_RE.findall(text)
        if len(matches) != 1:
            errors.append(f"missing or duplicate structured lifecycle reference in {path.name}")
        else:
            try:
                reference = json.loads(matches[0])
            except json.JSONDecodeError as exc:
                errors.append(f"invalid structured lifecycle reference in {path.name}: {exc.msg}")
            else:
                if reference.get("authority") != "contracts/task-lifecycle.yaml":
                    errors.append(f"wrong lifecycle authority in {path.name}")
                categories = reference.get("categories")
                if not isinstance(categories, dict):
                    errors.append(f"invalid lifecycle categories in {path.name}")
                else:
                    for category in LIFECYCLE_CATEGORIES:
                        if categories.get(category) != contract.get(category):
                            errors.append(f"lifecycle category drift in {path.name}: {category}")
                    for category in set(categories) - set(LIFECYCLE_CATEGORIES):
                        errors.append(f"unknown lifecycle category in {path.name}: {category}")
                if require_mappings and "mappings" not in reference:
                    errors.append(f"missing lifecycle mappings in {path.name}")
                elif "mappings" in reference and reference.get("mappings") != contract.get("mappings"):
                    errors.append(f"lifecycle mapping drift in {path.name}")
        for pattern in declaration_patterns:
            for declaration in pattern.findall(text):
                terms = re.findall(r"[a-z][a-z0-9-]*", declaration.lower())
                for term in terms:
                    if term not in vocabulary:
                        errors.append(f"unmapped native lifecycle term in {path.name}: {term}")
        for human, native_status in mapping_pattern.findall(text):
            mapping = (contract.get("mappings") or {}).get(human)
            allowed = set(mapping.get("native_statuses", [])) if isinstance(mapping, dict) else set()
            if isinstance(mapping, dict) and mapping.get("native_status"):
                allowed.add(mapping["native_status"])
            if native_status not in allowed:
                errors.append(f"competing lifecycle mapping in {path.name}: {human} -> {native_status}")
    return errors


def validate(root: Path, release=False, initial_release=False) -> dict[str, object]:
    root = root.resolve()
    errors = []
    for relative in REQUIRED_FILES + REQUIRED_DOCS:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")
    for name in REQUIRED_SKILLS:
        if not (root / "skills" / name / "SKILL.md").is_file():
            errors.append(f"missing required skill: {name}")

    privacy_errors, text_files = scan_public_files(root)
    errors.extend(privacy_errors)
    lifecycle_docs = [
        root / "README.md", root / "SOUL.md", root / "skills" / "continuity" / "SKILL.md",
        root / "docs" / "03-tasks-and-scheduling.md", root / "docs" / "04-delegation.md",
        root / "docs" / "23-task-truth-and-kanban.md",
    ]
    try:
        # SOUL.md is protected during this integration slice; its structured
        # reference is added by the parent integration commit.
        structured_docs = [path for path in lifecycle_docs if path.name != "SOUL.md"]
        errors.extend(lifecycle_drift_errors(root / "contracts" / "task-lifecycle.yaml", structured_docs, require_mappings=True))
        errors.extend(
            error for error in lifecycle_drift_errors(
                root / "contracts" / "task-lifecycle.yaml", [root / "SOUL.md"]
            ) if not error.startswith("missing or duplicate structured lifecycle reference")
        )
    except Exception as exc:
        errors.append(f"lifecycle drift validation failed: {exc}")
    errors.extend(documentation_drift_errors(root))

    for name in REQUIRED_SKILLS:
        path = root / "skills" / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            errors.append(f"invalid skill frontmatter: {path.relative_to(root)}")
            continue
        front = text.split("---\n", 2)[1]
        data = yaml.safe_load(front)
        description = str(data.get("description") or "")
        if not description or len(description) > 60 or not description.endswith("."):
            errors.append(f"skill description contract failed in {path.relative_to(root)}")
        if data.get("name") != name:
            errors.append(f"skill name/path mismatch in {path.relative_to(root)}")
        if not data.get("platforms"):
            errors.append(f"skill platforms missing in {path.relative_to(root)}")

    schema_objects = {}
    for relative in REQUIRED_SCHEMAS:
        try:
            schema = json.loads((root / relative).read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(schema)
            schema_objects[relative] = schema
        except Exception as exc:
            errors.append(f"invalid JSON Schema {relative}: {exc}")
    examples = [
        ("templates/integration-registry.example.json", "templates/integration-registry.schema.json", "json"),
        ("contracts/evidence-authorities.json", "templates/evidence-authorities.schema.json", "json"),
        ("templates/install.answers.example.yaml", "templates/install.answers.schema.json", "yaml"),
        ("capabilities.yaml", "templates/capabilities.schema.json", "yaml"),
        ("optional-packs.yaml", "templates/optional-packs.schema.json", "yaml"),
        ("templates/resolved-capability.example.yaml", "templates/resolved-capability.schema.json", "yaml"),
        ("contracts/task-lifecycle.yaml", "templates/task-lifecycle.schema.json", "yaml"),
        ("contracts/capability-status.yaml", "templates/capability-status.schema.json", "yaml"),
        ("contracts/business-lane-preservation.yaml", "templates/business-lane-preservation.schema.json", "yaml"),
        ("templates/task-contract.compact.example.yaml", "templates/task-contract.schema.json", "yaml"),
        ("templates/task-contract.full.example.yaml", "templates/task-contract.schema.json", "yaml"),
        ("templates/daily-brief-routine.example.yaml", "templates/daily-brief-routine.schema.json", "yaml"),
        ("templates/artifact-storage-contract.example.yaml", "templates/artifact-storage-contract.schema.json", "yaml"),
        ("tools/website-watchdog/sites.example.json", "tools/website-watchdog/sites.schema.json", "json"),
    ]
    for example_path, schema_path, kind in examples:
        try:
            raw = (root / example_path).read_text(encoding="utf-8")
            instance = json.loads(raw) if kind == "json" else yaml.safe_load(raw)
            validator = jsonschema.Draft202012Validator(schema_objects[schema_path], format_checker=jsonschema.FormatChecker())
            for failure in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
                errors.append(f"example does not match schema: {example_path}: {failure.message}")
            if example_path == "templates/integration-registry.example.json":
                for failure in integration_semantic_errors(root, instance):
                    errors.append(f"integration semantic validation failed: {failure}")
        except Exception as exc:
            errors.append(f"example validation failed: {example_path}: {exc}")
    for relative, schema in schema_objects.items():
        for finding in nested_forbidden(schema.get("properties", {})):
            errors.append(f"secret-bearing nested schema key in {relative}: {finding}")

    try:
        distribution = parse_manifest(root / "distribution.yaml")
        capabilities = parse_manifest(root / "capabilities.yaml")
        distribution_name = distribution.get("name")
        distribution_version = str(distribution.get("version"))
        capabilities_version = str(capabilities.get("version"))
        if distribution_version != capabilities_version:
            errors.append("capabilities.yaml version does not match distribution.yaml")
        if distribution.get("hermes_requires") != ">=0.21.0":
            errors.append("distribution must use the single comparator supported by native Hermes")
        if "tested_with_hermes" in distribution:
            errors.append("native Hermes discards tested_with_hermes; record tested range in installer reports")
        if capabilities.get("recommended_mode") != "workload-selected":
            errors.append("capabilities.yaml must select mode by workload")
        owned = set(distribution.get("distribution_owned") or [])
        for item in ("SOUL.md", "contracts/", "skills/", "optional-skills/", "tools/", "capabilities.yaml", "optional-packs.yaml", "AGENTS.md", "AI-INSTALL.md", "ONBOARDING.md", "scripts/install_blueprint.py"):
            if item not in owned:
                errors.append(f"distribution does not own required path: {item}")
        manifest_packs = set((capabilities.get("capability_packs") or {}).keys())
        optional_catalog = parse_manifest(root / "optional-packs.yaml")
        optional_names = set((optional_catalog.get("packs") or {}).keys())
        if optional_names != manifest_packs - {"core-operator"}:
            errors.append("optional-packs.yaml names must exactly match non-core capabilities.yaml packs")
        for pack_name, pack in (optional_catalog.get("packs") or {}).items():
            source = pack.get("source") or {}
            if source.get("kind") == "bundled":
                locator = source.get("locator")
                if not locator or not (root / locator / "SKILL.md").is_file():
                    errors.append(f"bundled optional pack source is missing: {pack_name}")
            elif not source.get("candidates"):
                errors.append(f"discoverable optional pack needs candidate identifiers: {pack_name}")
        for label, path in (
            ("capability selection", root / "templates" / "capability-selection.example.yaml"),
            ("install answers", root / "templates" / "install.answers.example.yaml"),
        ):
            pack_names = set((parse_manifest(path).get("capability_packs") or {}).keys())
            if pack_names != manifest_packs:
                errors.append(f"{label} pack names do not match capabilities.yaml")
    except Exception as exc:
        distribution_name = distribution_version = capabilities_version = None
        errors.append(f"manifest validation failed: {exc}")

    for line in (root / ".env.template").read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped and stripped.split("=", 1)[1].strip():
            errors.append(f".env.template value must be blank: {stripped.split('=', 1)[0]}")

    required_ignores = {"/.env", "/auth.json", "/memories/", "/sessions/", "/state.db*", "/logs/", "/backups/", "*.db", "*.key", "*.pem"}
    ignored = set((root / ".gitignore").read_text().splitlines())
    private_runtime_paths_ignored = required_ignores.issubset(ignored)
    if not private_runtime_paths_ignored:
        errors.append(".gitignore does not cover required private runtime paths")

    if release or initial_release:
        for generated in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"):
            if release_cache_directories(root, generated):
                errors.append(f"release tree contains generated cache directory: {generated}")
        status = git(root, "status", "--porcelain")
        if status.returncode != 0 or status.stdout.strip():
            errors.append("release validation requires a clean Git tree")
        if initial_release:
            commits = git(root, "rev-list", "--count", "HEAD")
            if commits.returncode != 0 or commits.stdout.strip() != "1":
                errors.append("initial release history must contain exactly one commit")
        tracked = git(root, "ls-files", "-z")
        for name in tracked.stdout.split("\0"):
            if name and Path(name).suffix.lower() in FORBIDDEN_BINARY_EXTENSIONS:
                errors.append(f"tracked runtime or sensitive artifact: {name}")

    return {
        "errors": errors,
        "documents": len(list((root / "docs").glob("*.md"))),
        "skills": len(list((root / "skills").glob("*/SKILL.md"))),
        "tools": len([path for path in (root / "tools").iterdir() if path.is_dir()]),
        "schemas": len(schema_objects),
        "distribution_name": distribution_name,
        "distribution_version": distribution_version,
        "capabilities_version": capabilities_version,
        "private_runtime_paths_ignored": private_runtime_paths_ignored,
        "scanned_text_files": len(text_files),
        "release_mode": release,
        "initial_release_mode": initial_release,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--release", action="store_true")
    modes.add_argument("--initial-release", action="store_true")
    parser.add_argument("--public-release-audit", action="store_true", help="also run the explicit online, read-only GitHub release audit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = validate(root, release=args.release, initial_release=args.initial_release)
    if args.public_release_audit and not result["errors"]:
        remote = subprocess.run(
            [sys.executable, str(root / "scripts" / "audit_public_release.py")],
            cwd=root,
            capture_output=True,
            text=True,
        )  # nosec B603
        if remote.returncode:
            errors = result["errors"]
            if not isinstance(errors, list):
                raise TypeError("validator errors must be a list")
            errors.append("public release audit did not pass")
    print(json.dumps(result, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
