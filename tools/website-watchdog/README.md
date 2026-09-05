# Website Watchdog

A provider-neutral, POSIX reliability reference with deterministic collector, registry reconciliation, bounded synthetic repair handoff, and notification and credential-delivery contracts.

## Bundled today

1. Explicit site registry with schema
2. HTTPS or HTTP health probes
3. Status, content, redirect, timeout, and body-size checks
4. Bounded retry attempts and failed scheduler cycles
5. Durable state and append-only transition events
6. One incident per confirmed outage
7. Process lock for overlapping scheduler runs
8. Recovery cancellation before delayed AI work
9. Incident lease and closure CLI
10. Private-network and redirect restrictions by default
11. Canonical registry schema plus exact executable target reconciliation
12. Scheduler occurrence identity and current-health readback
13. Bounded synthetic repair handoff with exact operator-control and Kanban references
14. Metadata-only credential-reference delivery latency measurement
15. Configurable failure-only notification policy

## Not bundled

The synthetic worker proves the contract but performs no infrastructure action. A live AI diagnosis worker, repair executor, credential boundary, notification connector, persistent service unit, site inventory, and vendor-specific deployment access remain Planned or Blocked until a private deployment proves each one. Do not call automated recovery active from this public repository.

## Registry reconciliation

`templates/website-registry.schema.json` is the canonical inventory format. It stores a credential reference, never a secret value. Generate or compare watchdog targets with:

```bash
python3 tools/website-watchdog/registry.py --registry <private-registry.json> --targets <private-targets.json>
```

Use `--write-targets` to derive enabled targets. Both documents are schema-validated before reconciliation, duplicate canonical IDs are rejected semantically, and host/health-URL equality is enforced. Reconciliation fails with exit `2` for missing, extra, duplicate, or stale targets and compares every generated identity, health, retry, redirect, repair, credential-principal, and notification-policy field exactly.

## Bounded repair handoff

`repair-handoff.schema.json` names the exact site, host, checkpoint, credential reference and principal, allowed action, approval and task versions, requirement version, operation key, limits, and acceptance evidence. The executor derives its action and probe target from the canonical incident and registry snapshot and re-reads operator-control approval and native Kanban state immediately around effects and readback. Attempts, start, deadline, and operation key persist in the incident before each effect. Dispatch stays Planned or Blocked unless the worker, credential, approval, notification route, enforcement, and dispatch switch are configured. Resolution requires a bound post-repair health check.

`credential_delivery.py` measures authorized lookup-to-confirmed direct delivery with an explicit environment and threshold. The protected broker must return a typed opaque handle bound to approval, task/version, site, recipient, and credential principal; only a matching positive typed receipt and readback count as delivery. The model-visible return contains metadata only, never a recipient address, link, handle, or plaintext credential. `notifications.py` defaults healthy checks, false alarms, and successful routine repairs to silence and escalates only bounded repair failure; deployments may supply another explicit policy.

## Configure

Copy `sites.example.json` into a private directory and validate it against `sites.schema.json`.

Every site can define:

1. Stable ID and name
2. Health URL without credentials
3. Healthy status codes
4. Optional content marker
5. Timeout and body limit
6. Attempts and delay inside one run
7. Failed scheduler cycles before incident
8. Allowed redirect hosts
9. Private-network approval
10. Allowed repairs for a later worker
11. Notification route

Private, loopback, link-local, reserved, and multicast targets are blocked unless `allow_private_networks` is explicitly true. Redirects are limited to the original host and `allowed_redirect_hosts`. Every hop is resolved and validated separately, then its connection is pinned to that validated address; HTTPS still uses the configured hostname for SNI and certificate verification.

## Run once

```bash
python3 tools/website-watchdog/watchdog.py \
  --config /protected/path/sites.json \
  --state /protected/path/watchdog-state.json \
  --incident-dir /protected/path/incidents
```

Exit codes:

1. `0` means no newly confirmed outage.
2. `1` means at least one outage was newly confirmed.
3. Invalid configuration or local collector failure raises an error and must be treated as monitor-path failure, not site failure.

The tool prints JSON only for a newly confirmed outage or recovery.

## Incident lifecycle

Incident files follow `incident.schema.json`.

States:

1. `queued`
2. `leased`
3. `resolved`
4. `failed`
5. `cancelled`

A worker must lease the exact incident before acting:

```bash
python3 tools/website-watchdog/incident.py lease --incident /protected/path/incidents/<id>.json --worker recovery-worker
```

The lease command rechecks the target first. A healthy target is resolved without repair.

After verified recovery:

```bash
python3 tools/website-watchdog/incident.py resolve --incident /protected/path/incidents/<id>.json --worker recovery-worker --lease-token '<token-returned-by-lease>' --evidence "verified health readback"
```

Use `fail` when bounded recovery fails and `release` when work must return to the queue. Resolve, fail, and release require the active owner, its unique fencing token, and an unexpired lease.

Collector recovery or site removal resolves/cancels only unleased incidents. An active lease remains owned by its worker, avoiding a concurrent collector transition while repair may be in progress. Expired leases are reclaimed under the same incident lock and the target is re-probed before a new worker lease is issued.

## Hermes scheduling

Create a script-only cron job after a manual dry run. The exact paths, interval, timezone, output policy, failure route, and retirement condition belong to the private deployment.

The deterministic job should run frequently and stay silent on healthy output. A separate optional agent job consumes only leased confirmed incidents.

Schedule this dead-man check from a different scheduler or host:

```bash
python3 /absolute/profile/tools/website-watchdog/deadman.py --state /protected/path/watchdog-state.json --max-age-seconds 900
```

It is silent with exit `0` while fresh and emits JSON with exit `2` when state is missing, unreadable, or stale. Route nonzero output to a human-visible monitor-of-monitor channel. Running it in the same failed scheduler is not independent coverage. Verify next-run timestamps, nonzero delivery, and reboot persistence.

## Proxy-only networks

The collector disables environment proxies and pins direct connections to validated public addresses. It rejects `proxy_url` rather than weakening DNS-rebinding/SSRF protection. In proxy-only networks, run it on an approved egress monitor host or use a narrow fixed-target relay. A generic proxy is out of scope unless it independently enforces the same destination and address policy and has dedicated tests.

## Required worker rules

1. Re-probe before repair.
2. Audit the exact named target.
3. Use only listed repairs.
4. Back up before configuration or deployment changes.
5. Keep attempts and cost bounded.
6. Read back public and local health.
7. Resolve or fail the exact incident.
8. Notify only through the selected route and policy.

## Safety boundaries

1. The registry is trusted configuration and must remain private.
2. Credentials and query tokens are rejected or stripped from persisted URLs.
3. Incident files contain an allowlisted site subset, not the complete private registry.
4. Exception text is reduced to typed failure categories.
5. Public monitoring does not authorize deployment access.
6. Internal targets require explicit approval.
7. A shared monitor failure must not be mistaken for many independent site outages.
8. This reference implementation requires POSIX `flock` and secure regular lock files owned by the effective user, mode `0600`, with one hard link. Lock files are opened without symlink following or truncation.
9. No AI diagnosis or repair worker ships here. Incident files are queue artifacts only.

## Verification

1. Schema accepts the example and rejects unknown or unsafe values.
2. Healthy runs are silent.
3. One failed cycle remains suspect.
4. Confirmed failure creates one incident.
5. Overlapping runs cannot race state.
6. Recovery resolves the incident before worker action.
7. Wrong worker cannot close an incident.
8. Removed or disabled sites cancel stale incidents.
9. Private targets and unapproved redirects fail closed.
10. State, incident, and event files survive interruption without truncated JSON.
