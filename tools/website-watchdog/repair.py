#!/usr/bin/env python3
"""Provider-neutral bounded repair executor with canonical target binding."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from watchdog import atomic_json, load_json

PREREQUISITES = ("worker", "credential", "approval", "notification", "enforcement")
SECRET_NAMES = {"password", "plaintext_password", "secret", "secret_value", "api_key", "access_token", "credential_value"}


def dispatch_decision(contract):
    if not contract.get("dispatch_enabled", False):
        return {"dispatch": False, "status": "planned", "reason": "dispatch_not_configured"}
    for name in PREREQUISITES:
        status = contract.get(name, {}).get("status", "planned")
        if status != "configured":
            return {"dispatch": False, "status": "blocked" if status == "blocked" else "planned", "reason": f"{name}_{status}"}
    if not contract.get("notification", {}).get("route"):
        return {"dispatch": False, "status": "blocked", "reason": "notification_missing"}
    if not contract.get("credential_reference"):
        return {"dispatch": False, "status": "blocked", "reason": "credential_missing"}
    if not contract.get("approval_reference"):
        return {"dispatch": False, "status": "blocked", "reason": "approval_missing"}
    return {"dispatch": True, "status": "configured", "reason": "bounded_handoff_ready"}


def _url(value):
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port
    authority = host if port is None else f"{host}:{port}"
    return urlunparse((parsed.scheme.lower(), authority, parsed.path or "/", "", "", ""))


def _contains_secret_field(value):
    if isinstance(value, dict):
        return any(str(key).lower() in SECRET_NAMES or _contains_secret_field(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret_field(item) for item in value)
    return False


def validate_binding(contract, incident, registry_site, approval, task):
    """Fail closed unless all mutable authority records describe one operation."""
    if _contains_secret_field(contract) or _contains_secret_field(incident):
        raise PermissionError("repair binding contains a forbidden secret-bearing field")
    site = incident.get("site", {})
    operation_key = contract.get("operation_key")
    checks = (
        contract.get("incident_id") == incident.get("incident_id"),
        contract.get("site_id") == site.get("id") == registry_site.get("id"),
        str(contract.get("host", "")).lower().rstrip(".") == str(site.get("host", registry_site.get("host", ""))).lower().rstrip(".") == str(registry_site.get("host", "")).lower().rstrip("."),
        _url(contract.get("acceptance", {}).get("health_url", "")) == _url(site.get("url", "")) == _url(registry_site.get("health_url", "")),
        contract.get("acceptance", {}).get("healthy_codes") == registry_site.get("healthy_codes", [200]),
        contract.get("credential_reference") == site.get("credential_reference") == registry_site.get("credential_reference"),
        contract.get("credential_principal") == site.get("credential_principal") == registry_site.get("credential_principal"),
        contract.get("allowed_action") == registry_site.get("repair_policy") == site.get("repair_policy"),
        contract.get("allowed_action") in site.get("allowed_repairs", registry_site.get("allowed_repairs", [])),
        contract.get("approval_reference") == approval.get("reference") == site.get("approval_reference"),
        contract.get("approval_version") == approval.get("version") == site.get("approval_version"),
        approval.get("status") == "approved",
        approval.get("operation_key") == operation_key,
        approval.get("site_id") == contract.get("site_id"),
        contract.get("operator_task_reference") == approval.get("task_reference") == task.get("reference") == site.get("operator_task_reference"),
        contract.get("task_version") == approval.get("task_version") == task.get("version") == site.get("task_version"),
        contract.get("requirement_version") == task.get("requirement_version") == site.get("requirement_version"),
        operation_key == site.get("operation_key"),
        task.get("status") == "in_progress",
        isinstance(operation_key, str) and bool(operation_key),
    )
    if not all(checks):
        raise PermissionError("repair binding does not match canonical incident, registry, approval and task state")
    return {
        "site_id": registry_site["id"], "host": registry_site["host"],
        "health_url": _url(registry_site["health_url"]),
        "healthy_codes": list(registry_site.get("healthy_codes", [200])),
        "credential_reference": registry_site["credential_reference"],
        "credential_principal": registry_site["credential_principal"],
        "action": registry_site["repair_policy"], "operation_key": operation_key,
    }


def run_synthetic(contract, site_id, credential_reference, action, apply_action, probe_fn, now_ms,
                  *, incident, registry_site, approval, task, incident_path,
                  incident_readback_fn, registry_readback_fn, approval_readback_fn,
                  task_readback_fn, broker_readback_fn, worker_id, lease_token):
    """Execute one fenced repair while re-reading every authority at each effect boundary."""
    from watchdog import incident_lock

    decision = dispatch_decision(contract)
    if not decision["dispatch"]:
        return decision
    if site_id != contract.get("site_id") or credential_reference != contract.get("credential_reference") or action != contract.get("allowed_action"):
        raise PermissionError("repair request exceeds exact handoff scope")
    resolvers = (incident_readback_fn, registry_readback_fn, approval_readback_fn,
                 task_readback_fn, broker_readback_fn)
    if not all(callable(item) for item in resolvers):
        raise TypeError("all incident, registry, approval, task and broker readback resolvers are required")

    def authoritative():
        current_incident = incident_readback_fn()
        current_registry = registry_readback_fn()
        current_approval = approval_readback_fn()
        current_task = task_readback_fn()
        current_broker = broker_readback_fn(contract.get("operation_key"))
        if current_broker != {"operation_key": contract.get("operation_key"), "authorized": True}:
            raise PermissionError("broker authorization readback mismatch")
        if (current_incident.get("worker_id"), current_incident.get("lease_token")) != (worker_id, lease_token):
            raise PermissionError("incident repair lease fencing mismatch")
        if current_incident.get("status") != "leased" or not current_incident.get("lease_expires_at"):
            raise PermissionError("incident repair requires an active lease")
        lease_expiry = datetime.fromisoformat(str(current_incident["lease_expires_at"]).replace("Z", "+00:00"))
        if lease_expiry <= datetime.now(timezone.utc):
            raise PermissionError("incident repair lease expired")
        return current_incident, validate_binding(contract, current_incident, current_registry,
                                                  current_approval, current_task)

    path = Path(incident_path)
    maximum = int(contract["limits"]["max_attempts"])
    elapsed_limit = int(contract["limits"]["max_elapsed_seconds"]) * 1000
    with incident_lock(path):
        saved_incident, canonical = authoritative()
        progress = dict(saved_incident.get("repair_state") or {})
        current = now_ms()
        if not progress:
            progress = {"attempts": 0, "started_ms": current, "deadline_ms": current + elapsed_limit,
                        "operation_key": canonical["operation_key"]}
            saved_incident["repair_state"] = progress
            atomic_json(path, saved_incident)
        elif progress.get("operation_key") != canonical["operation_key"]:
            raise PermissionError("persisted repair operation key does not match")

        def expired():
            return now_ms() > int(progress["deadline_ms"])

        if expired():
            return {"status": "failed", "attempts": progress["attempts"], "reason": "repair_deadline_exceeded"}
        _, canonical = authoritative()
        last = probe_fn({"health_url": canonical["health_url"], "healthy_codes": canonical["healthy_codes"]})
        if expired():
            return {"status": "failed", "attempts": progress["attempts"], "post_repair_health": last, "reason": "repair_deadline_exceeded"}
        if last.get("ok"):
            return {"status": "resolved", "attempts": progress["attempts"], "reason": "healthy_before_repair", "post_repair_health": last}

        while int(progress["attempts"]) < maximum:
            if expired():
                return {"status": "failed", "attempts": progress["attempts"], "post_repair_health": last, "reason": "repair_deadline_exceeded"}
            saved_incident, canonical = authoritative()
            persisted = saved_incident.get("repair_state") or progress
            if persisted != progress:
                progress = dict(persisted)
            progress["attempts"] = int(progress["attempts"]) + 1
            saved_incident["repair_state"] = progress
            atomic_json(path, saved_incident)
            apply_action(canonical)
            if expired():
                return {"status": "failed", "attempts": progress["attempts"], "post_repair_health": last, "reason": "repair_deadline_exceeded"}
            _, canonical = authoritative()
            last = probe_fn({"health_url": canonical["health_url"], "healthy_codes": canonical["healthy_codes"]})
            if expired():
                return {"status": "failed", "attempts": progress["attempts"], "post_repair_health": last, "reason": "repair_deadline_exceeded"}
            if last.get("ok"):
                return {"status": "resolved", "attempts": progress["attempts"], "post_repair_health": last,
                        "acceptance_evidence": {"health_url": canonical["health_url"], "healthy_codes": canonical["healthy_codes"]},
                        "operation_key": canonical["operation_key"]}
        return {"status": "failed", "attempts": progress["attempts"], "post_repair_health": last,
                "reason": "bounded_repair_exhausted"}
