# 17. Autopilot, Monitoring, and Recovery

Autopilot should reduce noise, not turn every check into an AI conversation.

## The default pattern

1. Deterministic collector
2. Durable state and deduplication
3. Confirmed event or incident
4. AI only when judgment is needed
5. Bounded action under explicit policy
6. Real verification
7. Failure only escalation
8. Retirement when the duty ends

## Website example

`tools/website-watchdog/` implements the deterministic part of a three stage website reliability system.

### Stage 1

A script checks approved targets without model tokens. Healthy operation is silent.

### Stage 2

Repeated evidence creates one incident and one queued recovery item. Brief failures and monitor path problems are not declared global outages.

### Stage 3

A deployment may add an AI worker that audits the exact target, applies only approved repairs, verifies public and local state, and records the result. The owner is notified only when policy requires it, especially when recovery fails.

This repository bundles Stage 1, the incident-file part of Stage 2, exact registry reconciliation, and a synthetic Stage 3 contract runner. The synthetic runner proves target scoping, prerequisite blocking, retry/time limits, and mandatory post-repair health evidence without touching infrastructure. A live worker, credential boundary, notification adapter, schedules, and site inventory remain Planned or Blocked until privately configured and verified.

The canonical inventory is `templates/website-registry.schema.json`; it contains credential references only. `registry.py` must report an exact one-to-one match before monitoring is enabled. Repair handoffs reference operator-control approval and native Kanban task identity rather than duplicating either authority. Credential lookup-to-direct-recipient delivery measurements record an explicit environment and threshold; the model sees metadata only.

## Other useful autopilot duties

1. Inbox relevance and follow up checks
2. Calendar preparation
3. Meeting action reconciliation
4. CRM hygiene and stale opportunity review
5. Competitor and industry monitoring
6. PR opportunity monitoring
7. Price and procurement monitoring
8. Backup freshness and restore testing
9. Credential expiration warnings
10. Deployment and release verification
11. Scheduled executive briefs
12. Data pipeline freshness

## Routine contract

Every routine defines:

1. Purpose
2. Trigger or schedule
3. Timezone
4. Source
5. Owner
6. State and deduplication
7. Automatic actions
8. Approval actions
9. Budget
10. Output
11. Silence behavior
12. Failure route
13. Retry and lease
14. Retirement condition

The daily-brief routine adds strict defaults: native Hermes cron owns the job; timezone and delivery must be selected before enablement; empty output is silent; delivery is deduplicated and read back; and the routine has no authority to mutate canonical task truth. Retirement disables the schedule, revokes source access, and verifies that no future run remains.

## AI boundary

Use AI for interpretation, diagnosis, drafting, prioritization, and ambiguous recovery.

Use deterministic code for polling, checksums, comparison, counting, rate limits, exact state transitions, idempotency, and simple retries.

A model call on every unchanged poll is usually a design failure.

## Notifications

Ask during onboarding where each class goes.

Recommended default:

1. Decision and approval to the primary human channel
2. Failed recovery to the urgent route
3. Material reply or opportunity to the business route
4. Healthy, unchanged, duplicate, false alarm, and successful routine recovery remain silent

## Recovery

1. Detect the failing layer.
2. Preserve the original evidence.
3. Acquire one worker lease.
4. Check whether a previous attempt already succeeded.
5. Apply only bounded repair.
6. Verify the real outcome.
7. Restore the previous known state when verification fails.
8. Escalate with the smallest useful decision.

## Edge cases

1. Several sites fail from one monitor: investigate DNS or route before declaring many outages.
2. An external write times out: read the target before retry.
3. A worker dies: reclaim only after its lease expires.
4. The owner approved one change: suppress only that exact expected event.
5. An old alert is queued: recheck live state before delivery.
6. A routine outlives its project: retire it instead of leaving permanent noise.
7. A notification channel fails: preserve the commitment and use the approved fallback.

## Verification

1. Healthy run is silent.
2. Duplicate event is suppressed.
3. Confirmed event creates one worker.
4. Worker retry is bounded.
5. Approved change suppression is exact.
6. Failed recovery reaches the chosen route once.
7. Successful recovery records evidence.
8. Scheduler survives restart.
9. One time routine retires.
10. Cost and rate limits stop work.

## Interrupted managed work

Native run, claim, heartbeat, reclaim, and attempt records determine worker liveness. After disappearance, reclaim through native Kanban; a replacement receives a new run ID and claim lock. Protected adapters reject the old worker's return and duplicate callbacks. Replanning validates the dependency graph again, binds each run to consumed input versions, invalidates only descendants affected by changed inputs, and preserves all prior run and repair evidence.
