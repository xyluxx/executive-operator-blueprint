---
name: website-reliability
description: Use when monitoring sites or confirmed failures.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Monitoring, Websites, Recovery, Cron]
    related_skills: [integration-onboarding, continuity]
---

# Website Reliability

Use this skill to monitor approved websites and services with cheap deterministic checks, confirm real incidents, invoke AI only when judgment is useful, and notify only when recovery fails or human action is needed.

Use `$HERMES_HOME/tools/website-watchdog/` as the bundled reference collector after native profile installation. In a trusted repository checkout, resolve the equivalent path from the repository root.

See `references/three-stage-recovery.md` for the collector, incident queue, and AI worker contract.

## Reference Tool

Run the bundled collector through `terminal` using its resolved profile path. Do not assume the terminal's current directory is the profile root:

```text
terminal(command="python3 \"$HERMES_HOME/tools/website-watchdog/watchdog.py\" --config <private-sites-json> --state <private-state-json> --incident-dir <private-incident-directory>")
```

Configure this as a script-only Hermes cron job after its dry run and silence behavior pass.

Schedule `deadman.py` from an independent scheduler or host to detect stale collector state. Generic forward proxies are unsupported because they defeat DNS pinning; use an approved egress host or fixed-target relay in proxy-only networks.

## When to Use

1. Add a website or endpoint to monitoring.
2. Create a silent availability check.
3. Separate brief network problems from sustained incidents.
4. Queue an AI diagnosis or bounded repair.
5. Verify recovery.
6. Audit false alerts, flapping, stale jobs, or failed notification.

## Onboarding Record

Every target needs:

1. Stable ID and public URL
2. Owner and data boundary
3. Health URL and success definition
4. Expected HTTP status, content, redirect, or JSON assertion
5. Check interval and timeout
6. Confirmation attempts and cycle threshold
7. Independent vantage requirement
8. Hosting and runtime metadata
9. Access availability
10. Allowed automatic repairs
11. Prohibited actions
12. Retry and lease limits
13. Failure notification route
14. Retirement condition
15. Live verification evidence

## Three Stage Design

### Stage 1. Deterministic collector

1. Fetch the narrow health target.
2. Record code, latency, final URL, and assertion result.
3. Retry within the configured policy.
4. Keep healthy output empty.
5. Persist a bounded state transition.

No model call is needed.

### Stage 2. Confirmed incident queue

1. Require failure across configured attempts and cycles.
2. Distinguish target failure from monitor DNS, route, or network degradation.
3. Create one incident ID.
4. Store the exact target context and evidence.
5. Acquire a lease before dispatching a worker.
6. Retry an interrupted worker only within the configured limit.

### Stage 3. AI recovery and escalation

This stage includes an inert synthetic contract worker only. It proves bounded dispatch and verification but performs no real repair. No live AI diagnosis or infrastructure worker is configured.

1. Load only the named target context.
2. Audit live public and local state.
3. Diagnose before changing anything.
4. Apply only approved bounded repairs.
5. Verify the public result, runtime, persistence, and intended version.
6. Record diagnosis, action, result, and evidence.
7. Stay silent after a successful approved recovery when policy says so.
8. Notify the owner if repair fails, scope is unclear, access is missing, or a consequential decision is required.
9. Keep dispatch Planned or Blocked when worker, credential reference, approval reference, notification route, or enforcement is absent.

Before monitoring, validate the canonical `templates/website-registry.example.json` shape and run `registry.py` against the watchdog targets. Any missing, extra, duplicate, or stale target blocks enablement. Preserve host, environment, health URL, credential reference, owner, repair policy, and notification route exactly; never put secret values in either file.

Repair handoffs use `repair-handoff.schema.json`. They carry narrow operator-control approval and Kanban task references only; those systems remain authoritative. Use `credential_delivery.py` only behind a protected lookup and direct-recipient transport: publish environment, threshold, and latency metadata, never the delivery link, recipient, or credential plaintext to the model.

## Repair Boundaries

Automatic repair authority must name exact actions. Examples may include restarting one known process or restoring one prior immutable release. It does not authorize arbitrary server changes, DNS changes, database mutation, credential rotation, spending, or deletion.

Before any infrastructure action, inspect the exact host and current state. Never restart a whole user session manager or unrelated foundation service.

## Alert Language

Say what the evidence proves.

1. “The monitor cannot reach the site” is not the same as “the site is down everywhere.”
2. “The monitor can reach it again” is not proof that an automatic repair fixed it.
3. Name verified repair actions only when they occurred.
4. Label delayed historical alerts.
5. Suppress stale incidents that are already resolved.

## Scheduling

Use Hermes cron for the collector and queue. The deterministic collector should run without an agent. The AI worker should wake only for a confirmed incident. The escalation route should deliver only unresolved failure or required human action.

## Pitfalls

1. Do not spend model tokens on every healthy check.
2. Do not declare an outage from rapid retries on one host.
3. Do not create a new incident every cycle.
4. Do not retry a possibly successful repair without reading current state.
5. Do not keep retired sites in active monitoring.
6. Do not hide monitor failure behind silence.
7. Do not let one target’s access authorize another target.
8. Do not alert on provider generated noise without material impact.

## Verification

1. Healthy target produces no alert.
2. One brief failure resolves as transient.
3. Sustained failure creates one incident.
4. Shared network failure is classified separately.
5. Queue lease prevents duplicate AI workers.
6. Interrupted worker retries within bounds.
7. Approved repair runs only on the named target.
8. Public and local recovery checks pass.
9. Failed recovery notifies once with evidence.
10. Successful recovery follows the selected silence policy.
11. Scheduler next run and failure behavior are verified.
12. Reboot preserves monitoring and state.
