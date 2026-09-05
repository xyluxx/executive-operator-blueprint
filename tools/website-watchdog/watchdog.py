#!/usr/bin/env python3
"""Deterministic website checks with durable incident transitions."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import http.client
import ipaddress
import json
import os
import secrets
import socket
import ssl
import stat
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


def stamp():
    return datetime.now(timezone.utc).isoformat()


def _secure_parent(path):
    """Open a parent directory via a descriptor-relative no-symlink walk."""
    if os.name != "posix":
        raise OSError("website watchdog storage requires POSIX")
    path = Path(path).absolute()
    parts = path.parent.parts
    fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            info = os.fstat(child)
            if info.st_uid not in {0, os.geteuid()} or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
                os.close(child)
                raise PermissionError("unsafe storage parent")
            os.close(fd)
            fd = child
        if os.fstat(fd).st_uid == os.geteuid():
            os.fchmod(fd, 0o700)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _validate_data_fd(fd, writable=False):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
        raise PermissionError("unsafe data file")
    if stat.S_IMODE(info.st_mode) != 0o600:
        # The descriptor has already been proven owned, regular and single-link;
        # harden its mode without resolving the path again.
        os.fchmod(fd, 0o600)


def load_json(path, default):
    path = Path(path)
    parent_fd = _secure_parent(path)
    try:
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            return default
        try:
            _validate_data_fd(fd)
            return json.loads(os.read(fd, os.fstat(fd).st_size + 1).decode())
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def fsync_directory(path):
    fd = os.open(Path(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, data, mode=0o600):
    path = Path(path)
    parent_fd = _secure_parent(path)
    tmp_name = f".{path.name}.{secrets.token_hex(6)}.tmp"
    try:
        fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent_fd)
        try:
            os.write(fd, (json.dumps(data, indent=2, sort_keys=True) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            existing = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            try:
                _validate_data_fd(existing)
            finally:
                os.close(existing)
        os.replace(tmp_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name, dir_fd=parent_fd)
        raise
    finally:
        os.close(parent_fd)


def append_event(path, data):
    path = Path(path)
    parent_fd = _secure_parent(path)
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        try:
            _validate_data_fd(fd, writable=True)
            os.write(fd, (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _open_lock(path):
    """Open a trusted POSIX lock file without following or truncating it."""
    if os.name != "posix":
        raise OSError("website watchdog locking requires POSIX")
    path = Path(path)
    parent_fd = _secure_parent(path)
    flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    created = False
    try:
        fd = os.open(path.name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        fd = os.open(path.name, flags, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        if created:
            os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise PermissionError("unsafe lock file")
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextlib.contextmanager
def file_lock(lock_path, nonblocking=False):
    fd = _open_lock(lock_path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        yield
    finally:
        os.close(fd)


def incident_lock(path):
    path = Path(path)
    return file_lock(path.with_suffix(path.suffix + ".lock"))


def sanitized_url(value):
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path or "/", "", "", ""))


def resolve_addresses(host):
    return {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}


def address_allowed(address, allow_private=False):
    parsed = ipaddress.ip_address(address)
    if allow_private:
        return True
    return not (parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved or parsed.is_multicast)


def validated_target(value, allow_private=False):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("target must be an HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("credentials are not allowed in target URLs")
    addresses = resolve_addresses(parsed.hostname)
    if not addresses or any(not address_allowed(item, allow_private) for item in addresses):
        raise ValueError("target resolves to a disallowed private or special address")
    return parsed.hostname, tuple(sorted(addresses, key=lambda item: ipaddress.ip_address(item)))


def validate_target_url(value, allow_private=False):
    return validated_target(value, allow_private)[0]


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, original_host, allowed_hosts, allow_private):
        self.original_host = original_host
        self.allowed_hosts = set(allowed_hosts or []) | {original_host}
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host, addresses = validated_target(newurl, self.allow_private)
        if host not in self.allowed_hosts:
            raise urllib.error.HTTPError(newurl, 403, "redirect host not allowed", headers, fp)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            raise urllib.error.HTTPError(newurl, 403, "redirect could not be validated", headers, fp)
        setattr(redirected, "_validated_addresses", addresses)
        return redirected


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, *, validated_ip, **kwargs):
        self._validated_ip = validated_ip
        super().__init__(host, **kwargs)

    def connect(self):
        self.sock = socket.create_connection(
            (self._validated_ip, self.port), self.timeout, getattr(self, "source_address", None)
        )
        if getattr(self, "_tunnel_host", None):
            getattr(self, "_tunnel")()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, *, validated_ip, **kwargs):
        self._validated_ip = validated_ip
        super().__init__(host, **kwargs)

    def connect(self):
        sock = socket.create_connection(
            (self._validated_ip, self.port), self.timeout, getattr(self, "source_address", None)
        )
        if getattr(self, "_tunnel_host", None):
            self.sock = sock
            getattr(self, "_tunnel")()
            sock = self.sock
        # Keep the validated hostname for SNI and certificate verification.
        self.sock = getattr(self, "_context").wrap_socket(sock, server_hostname=self.host)


class PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, allow_private=False):
        super().__init__()
        self.allow_private = allow_private

    def http_open(self, req):
        addresses = getattr(req, "_validated_addresses", None)
        if addresses is None:
            _, addresses = validated_target(req.full_url, self.allow_private)
        return self.do_open(
            lambda host, **kwargs: _PinnedHTTPConnection(
                host, validated_ip=addresses[0], **kwargs
            ),
            req,
        )


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, allow_private=False, context=None):
        super().__init__(context=context)
        self.allow_private = allow_private

    def https_open(self, req):
        addresses = getattr(req, "_validated_addresses", None)
        if addresses is None:
            _, addresses = validated_target(req.full_url, self.allow_private)
        return self.do_open(
            lambda host, **kwargs: _PinnedHTTPSConnection(
                host, validated_ip=addresses[0], **kwargs
            ),
            req,
            context=getattr(self, "_context"),
            check_hostname=getattr(self, "_check_hostname"),
        )


def validate_sites(sites):
    if not isinstance(sites, list):
        raise ValueError("sites must be an array")
    seen = set()
    for site in sites:
        if "proxy_url" in site:
            raise ValueError("proxy_url is unsupported: proxy routing cannot preserve DNS pinning")
        site_id = site.get("id")
        if not site_id or site_id in seen:
            raise ValueError("site IDs must be nonempty and unique")
        seen.add(site_id)
        parsed = urlparse(site.get("url", ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"invalid HTTP URL for {site_id}")
        if parsed.username or parsed.password:
            raise ValueError(f"credentials are not allowed in URL for {site_id}")
        for field, low, high in (
            ("attempts", 1, 5), ("retry_delay_seconds", 0, 60), ("timeout_seconds", 1, 60),
            ("max_body_bytes", 256, 1048576), ("failure_cycles", 1, 10),
        ):
            value = int(site.get(field, low))
            if not low <= value <= high:
                raise ValueError(f"{field} out of range for {site_id}")
        codes = site.get("healthy_codes", [200])
        if not isinstance(codes, list) or not codes or any(not 100 <= int(code) <= 599 for code in codes):
            raise ValueError(f"invalid healthy_codes for {site_id}")
        if len(str(site.get("content_contains", ""))) > 2048:
            raise ValueError(f"content marker too long for {site_id}")


def probe(site, opener=None):
    started = time.monotonic()
    timeout = float(site.get("timeout_seconds", 10))
    maximum = int(site.get("max_body_bytes", 65536))
    safe_url = sanitized_url(site["url"])
    addresses = None
    try:
        if opener is None:
            allow_private = bool(site.get("allow_private_networks", False))
            original_host, addresses = validated_target(site["url"], allow_private)
            handler = SafeRedirect(original_host, site.get("allowed_redirect_hosts", []), allow_private)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), PinnedHTTPHandler(allow_private),
                PinnedHTTPSHandler(allow_private), handler,
            ).open
        request = urllib.request.Request(site["url"], headers={"User-Agent": "executive-operator-watchdog/3.0"})
        if addresses is not None:
            setattr(request, "_validated_addresses", addresses)
        with opener(request, timeout=timeout) as response:
            body = response.read(maximum + 1)
            code = int(response.getcode())
            final_url = sanitized_url(response.geturl())
        if len(body) > maximum:
            return {"ok": False, "kind": "body_limit", "status": code, "final_url": final_url, "latency_ms": round((time.monotonic()-started)*1000)}
        marker = site.get("content_contains")
        ok = code in site.get("healthy_codes", list(range(200, 400)))
        if marker is not None:
            ok = ok and str(marker).encode() in body
        return {"ok": ok, "kind": "healthy" if ok else ("content" if marker else "http"), "status": code, "final_url": final_url, "latency_ms": round((time.monotonic()-started)*1000)}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "kind": "http", "status": exc.code, "final_url": sanitized_url(exc.url or safe_url), "latency_ms": round((time.monotonic()-started)*1000)}
    except socket.gaierror:
        kind = "dns"
    except ssl.SSLError:
        kind = "tls"
    except (socket.timeout, TimeoutError):
        kind = "timeout"
    except Exception:
        kind = "monitor_path"
    return {"ok": False, "kind": kind, "status": None, "final_url": safe_url, "latency_ms": round((time.monotonic()-started)*1000)}


def observe(site, previous, attempts, now=None):
    now = now or stamp()
    last = attempts[-1]
    state: dict[str, Any] = dict(previous or {})
    state.setdefault("status", "unknown")
    state.setdefault("failure_cycles", 0)
    state.setdefault("incident_id", None)
    state.update({"last_checked_at": now, "last_attempts": attempts, "last_result_kind": last.get("kind")})
    event = None
    if last.get("kind") == "monitor_path":
        monitor = dict(state.get("monitor_path") or {})
        monitor.update({
            "status": "degraded", "failure_cycles": int(monitor.get("failure_cycles", 0)) + 1,
            "last_failure_at": now, "last_attempts": attempts,
        })
        state["monitor_path"] = monitor
        return state, None
    if last["ok"]:
        was_down = state["status"] == "down"
        prior_incident = state.get("incident_id")
        state.update({"status": "healthy", "failure_cycles": 0, "last_success_at": now, "incident_id": None})
        if was_down:
            event = {"kind": "recovered", "site_id": site["id"], "incident_id": prior_incident, "occurred_at": now, "evidence": attempts}
    else:
        state["failure_cycles"] = int(state.get("failure_cycles", 0)) + 1
        state["last_failure_at"] = now
        threshold = int(site.get("failure_cycles", 2))
        if state["failure_cycles"] >= threshold and state["status"] != "down":
            incident_id = str(uuid.uuid4())
            state.update({"status": "down", "incident_id": incident_id})
            event = {"kind": "confirmed_failure", "site_id": site["id"], "incident_id": incident_id, "occurred_at": now, "evidence": attempts}
        elif state["status"] != "down":
            state["status"] = "suspect"
            event = {"kind": "transient_failure", "site_id": site["id"], "occurred_at": now, "evidence": attempts}
    return state, event


def _stable_id(occurrence_id, site_id, kind):
    if not occurrence_id:
        return str(uuid.uuid4())
    seed = f"{occurrence_id or 'unscheduled'}:{site_id}:{kind}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def append_event_once(path, data):
    """Append an event only if its deterministic identity is absent."""
    path = Path(path)
    existing = load_json_lines(path)
    if any(item.get("event_id") == data.get("event_id") for item in existing):
        return
    append_event(path, data)


def load_json_lines(path):
    path = Path(path)
    parent_fd = _secure_parent(path)
    try:
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            return []
        try:
            _validate_data_fd(fd)
            raw = os.read(fd, os.fstat(fd).st_size + 1).decode()
            return [json.loads(line) for line in raw.splitlines() if line]
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def incident_site(site):
    snapshot = {
        "id": site["id"], "name": site.get("name", site["id"]), "url": sanitized_url(site["url"]),
        "host": (urlparse(site["url"]).hostname or "").lower().rstrip("."),
        "healthy_codes": site.get("healthy_codes", [200]), "content_contains": site.get("content_contains"),
        "allowed_repairs": site.get("allowed_repairs", []), "notification_route": site.get("notification_route"),
    }
    for field in ("credential_reference", "credential_principal", "repair_policy", "approval_reference",
                  "approval_version", "operator_task_reference", "task_version", "requirement_version",
                  "operation_key"):
        if field in site:
            snapshot[field] = site[field]
    return snapshot


def _update_incident_locked(path, status, **fields):
    path = Path(path)
    incident = load_json(path, {})
    allowed = {
        "queued": {"leased", "cancelled", "resolved"},
        "leased": {"resolved", "failed", "queued"},
        "failed": {"leased", "cancelled"},
    }
    current = str(incident.get("status") or "")
    if status not in allowed.get(current, set()):
        raise ValueError(f"invalid incident transition: {current} -> {status}")
    incident.update(fields)
    incident["status"] = status
    incident["updated_at"] = stamp()
    atomic_json(path, incident)
    return incident


def update_incident(path, status, **fields):
    with incident_lock(path):
        return _update_incident_locked(path, status, **fields)


def close_stale_incidents(configured_ids, state, incident_dir, event_path):
    for site_id, saved in list(state.get("sites", {}).items()):
        if site_id in configured_ids:
            continue
        incident_id = saved.get("incident_id")
        if incident_id:
            path = Path(incident_dir) / f"{incident_id}.json"
            with incident_lock(path):
                if path.exists() and load_json(path, {}).get("status") in {"queued", "failed"}:
                    _update_incident_locked(path, "cancelled", reason="site_removed_or_disabled")
        saved.update({"status": "retired", "incident_id": None, "retired_at": stamp()})
        append_event(event_path, {"kind": "site_retired", "site_id": site_id, "occurred_at": stamp()})


def run(config_path, state_path, incident_dir, probe_fn=probe, sleep_fn=time.sleep,
        now_fn=stamp, occurrence_id=None):
    config = load_json(config_path, {})
    sites = config.get("sites", [])
    validate_sites(sites)
    state: dict[str, Any] = load_json(state_path, {"sites": {}})
    state.setdefault("sites", {})
    claim_path = None
    if occurrence_id:
        claim_name = uuid.uuid5(uuid.NAMESPACE_URL, occurrence_id).hex + ".json"
        claim_path = Path(state_path).with_suffix(Path(state_path).suffix + ".occurrences") / claim_name
        claim = load_json(claim_path, {})
        if claim.get("status") == "completed":
            return []
        if not claim:
            atomic_json(claim_path, {"occurrence_id": occurrence_id, "status": "claimed", "claimed_at": now_fn()})
    event_path = Path(state_path).with_suffix(Path(state_path).suffix + ".events.jsonl")
    enabled_ids = {site["id"] for site in sites if site.get("enabled", True)}
    close_stale_incidents(enabled_ids, state, incident_dir, event_path)
    events = []
    observations = []
    for site in sites:
        if not site.get("enabled", True):
            continue
        attempts = []
        for index in range(int(site.get("attempts", 2))):
            attempts.append(probe_fn(site))
            if attempts[-1]["ok"]:
                break
            if index + 1 < int(site.get("attempts", 2)):
                sleep_fn(float(site.get("retry_delay_seconds", 1)))
        observations.append((site, attempts))

    infrastructure_kinds = {"dns", "monitor_path", "network_route", "route"}
    shared_failure = (
        len(observations) >= 2
        and all(not attempts[-1].get("ok") and attempts[-1].get("kind") in infrastructure_kinds
                for _, attempts in observations)
    )
    if shared_failure:
        kinds = {attempts[-1].get("kind") for _, attempts in observations}
        state["monitor_path"] = {
            "status": "degraded", "kind": "shared_dns" if kinds == {"dns"} else "shared_route",
            "last_failure_at": now_fn(), "affected_sites": sorted(site["id"] for site, _ in observations),
        }

    for site, attempts in observations:
        effective = attempts
        if shared_failure:
            effective = [{**item, "kind": "monitor_path"} for item in attempts]
        updated, event = observe(site, state["sites"].get(site["id"]), effective, now=now_fn())
        state["sites"][site["id"]] = updated
        if event:
            event["event_id"] = _stable_id(occurrence_id, site["id"], event["kind"])
            if event["kind"] == "confirmed_failure":
                event["incident_id"] = _stable_id(occurrence_id, site["id"], "incident")
                updated["incident_id"] = event["incident_id"]
            events.append(event)
            append_event_once(event_path, event)
            incident_path = Path(incident_dir) / f"{event.get('incident_id')}.json" if event.get("incident_id") else None
            if event["kind"] == "confirmed_failure":
                if incident_path is None:
                    raise RuntimeError("confirmed failure is missing an incident ID")
                incident = {
                    "schema_version": 1, "status": "queued", "incident_id": event["incident_id"],
                    "created_at": event["occurred_at"], "updated_at": event["occurred_at"],
                    "site": incident_site(site), "evidence": event,
                }
                with incident_lock(incident_path):
                    current = load_json(incident_path, {})
                    if current and current.get("incident_id") != incident["incident_id"]:
                        raise FileExistsError(incident_path)
                    if not current:
                        atomic_json(incident_path, incident)
            elif event["kind"] == "recovered" and incident_path and incident_path.exists():
                with incident_lock(incident_path):
                    current = load_json(incident_path, {})
                    if current.get("status") in {"queued", "failed"}:
                        _update_incident_locked(incident_path, "resolved", reason="recovered_before_ai", recovery_evidence=event)
    state["checked_at"] = now_fn()
    if occurrence_id:
        state["occurrence_id"] = occurrence_id
    atomic_json(state_path, state)
    if claim_path is not None:
        atomic_json(claim_path, {"occurrence_id": occurrence_id, "status": "completed", "completed_at": now_fn()})
    return events


def current_health(state_path, now_fn=stamp, max_age_seconds=900):
    """Read the persisted health view and state whether it is still fresh."""
    state = load_json(state_path, {})
    checked = state.get("checked_at")
    fresh = False
    if checked:
        current = datetime.fromisoformat(now_fn().replace("Z", "+00:00"))
        observed = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        fresh = 0 <= (current - observed).total_seconds() <= max_age_seconds
    return {
        "fresh": fresh, "checked_at": checked,
        "occurrence_id": state.get("occurrence_id"), "sites": state.get("sites", {}),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--incident-dir", required=True)
    parser.add_argument("--occurrence-id", help="stable scheduler occurrence identity")
    args = parser.parse_args(argv)
    lock_path = Path(args.state).with_suffix(Path(args.state).suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with file_lock(lock_path, nonblocking=True):
            events = run(args.config, args.state, args.incident_dir, occurrence_id=args.occurrence_id)
    except BlockingIOError:
        return 0
    material = [event for event in events if event["kind"] in {"confirmed_failure", "recovered"}]
    if material:
        print(json.dumps(material, separators=(",", ":")))
    return 1 if any(event["kind"] == "confirmed_failure" for event in material) else 0


if __name__ == "__main__":
    raise SystemExit(main())
