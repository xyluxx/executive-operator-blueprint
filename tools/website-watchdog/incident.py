#!/usr/bin/env python3
"""Lease and close Website Watchdog incident files."""
from __future__ import annotations

import argparse
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from watchdog import _update_incident_locked, incident_lock, load_json, probe


def now():
    return datetime.now(timezone.utc)


def mutate(path, command, worker=None, evidence=None, lease_seconds=900, now_fn=None,
           lease_token=None):
    clock = now_fn or now
    path = Path(path)
    with incident_lock(path):
        incident = load_json(path, {})
        status = incident.get("status")
        if command == "lease":
            if not worker:
                raise ValueError("worker is required")
            current_time = clock()
            if status == "leased":
                expiry = datetime.fromisoformat(incident["lease_expires_at"])
                if expiry > current_time:
                    raise RuntimeError("incident already leased")
                _update_incident_locked(path, "queued", reason="expired_lease_reclaimed")
            check = probe(incident["site"])
            if check["ok"]:
                return _update_incident_locked(path, "resolved", reason="healthy_before_worker", recovery_evidence=check)
            return _update_incident_locked(
                path, "leased", worker_id=worker, leased_at=current_time.isoformat(),
                lease_expires_at=(current_time + timedelta(seconds=lease_seconds)).isoformat(),
                lease_token=secrets.token_urlsafe(32), pre_action_probe=check,
            )
        current_time = clock()
        expiry_text = incident.get("lease_expires_at")
        active = bool(
            status == "leased" and incident.get("worker_id") == worker
            and lease_token and secrets.compare_digest(str(incident.get("lease_token", "")), str(lease_token))
            and expiry_text and datetime.fromisoformat(str(expiry_text)) > current_time
        )
        if not active:
            raise PermissionError("only the matching owner of an unexpired fenced lease may mutate this incident")
        if command == "resolve":
            check = probe(incident["site"])
            if not check.get("ok"):
                raise RuntimeError("post-repair health verification failed")
            return _update_incident_locked(
                path, "resolved", resolution_evidence=evidence,
                post_repair_probe=check,
            )
        if command == "fail":
            return _update_incident_locked(path, "failed", failure_evidence=evidence)
        if command == "release":
            return _update_incident_locked(path, "queued", reason="worker_released", release_evidence=evidence)
        raise ValueError(command)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["lease", "resolve", "fail", "release"])
    parser.add_argument("--incident", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--evidence")
    parser.add_argument("--lease-seconds", type=int, default=900)
    parser.add_argument("--lease-token", help="fencing token returned by lease")
    args = parser.parse_args(argv)
    result = mutate(args.incident, args.command, args.worker, args.evidence, args.lease_seconds,
                    lease_token=args.lease_token)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
