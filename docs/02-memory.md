# 02. Memory and Context

Memory is useful only when it is selective, correctable, private, and subordinate to current evidence.

## Native Hermes layers

Hermes supplies:

1. Session persistence
2. Session search
3. Core memory files
4. User profile memory
5. Configurable memory providers
6. Profile scoping
7. Context compression
8. Project context files

Exact retention, extraction, trust scoring, contradiction handling, and deletion depend on the selected provider and configuration.

## Blueprint operating layers

### Stable principal context

Confirmed preferences, identity, communication style, and long term rules.

### Current structured work

Workstreams, commitments, owners, attention, save points, approvals, waiting, blockers, current artifacts, and evidence.

### Project context

Facts, files, decisions, and history for one client, project, personal area, or program.

### Searchable sessions

Exact prior conversations when historical wording or provenance matters.

### Live sources

Email, calendar, meetings, CRM, websites, providers, and other systems that own current external facts.

## Authority order

1. Current principal correction
2. Current live source
3. Agreed structured state
4. Stable profile
5. Dated activity history
6. Generated summary
7. Session history
8. Durable memory
9. Temporary scratch work

If sources conflict, reconcile them. Do not merge contradictory claims into a confident answer.

## Selective loading

Do not place every transcript or client detail in every prompt.

Load:

1. The current work item
2. The current save point
3. Relevant corrections
4. Relevant project context
5. Current evidence requirements
6. Only the historical details needed for this request

This reduces noise and cross project mistakes.

## Correction and deletion

A conforming deployment lets authorized users:

1. Inspect remembered information
2. Correct it
3. Mark old claims superseded
4. Remove it according to retention policy
5. Verify the corrected state in a fresh session

Automatic extraction must never turn raw secrets, transient tool errors, generated wrappers, or unresolved guesses into durable facts.

### Durable correction routing

`templates/correction-record.schema.json` is the correction contract. A correction keeps its authenticated source identity, source event, recorded and effective timestamps, client and project/profile lane, exact field and target, and prior claim ID/version. Ambiguous statements require explicit confirmation before any durable write. Session-only clarification is used in the current response and written nowhere durable.

The coordinator in `plugins/operator-control/corrections.py` is stateless except for an injected idempotency adapter and owns no facts or task state. It routes each correction to the authority that already owns the claim:

1. Task or requirement → native Kanban card metadata and activity.
2. Project fact → selected private project lane or registry.
3. Stable principal preference → selected private profile/memory provider, scoped to that principal and overlay rather than global memory.
4. Voice rule → private voice-profile overlay.
5. Approval withdrawal or change → protected approval broker before affected actions proceed.

The authority atomically rejects stale prior versions, increments the affected version once, and marks only the named prior claim superseded. Correction IDs and source-event IDs are idempotency keys at that authority. Retraction is another explicit, versioned correction; history is not erased or silently restored.

After persistence, the coordinator reads active native work and selects only records that consumed the contradicted claim in the same client and scope. Affected tasks, criteria, evidence, schedules, and dependencies block; affected workers receive a new brief; affected approvals are cancelled. Unrelated or inactive work remains valid. The resulting actions are applied through existing Kanban, scheduler, worker, and broker adapters—never a correction-owned task table. Adapters must support readback, restart-safe idempotency, and private storage; correction content containing a secret is rejected.

## Memory provider choice

Holographic memory is the recommended configured option in this distribution because it supports structured retrieval and reasoning. It is still an implementation choice. Another Hermes supported provider can replace it if recall, correction, deletion, privacy, backup, and restore tests pass.

## Healthy headroom

Always loaded memory should remain compact. Detailed work belongs in project and structured state. Configure thresholds according to model and workload, then monitor growth.

Do not promise that nothing can ever be lost. Prove preservation through backups, searchable history, structured checkpoints, and restore tests.

## Verification

1. Add a synthetic preference and recall it in a fresh session.
2. Store two similar entities and retrieve the correct one.
3. Apply a correction and prove the old claim no longer appears as current.
4. Delete an approved test memory and verify removal.
5. Search a known historical session.
6. Restore memory into an isolated profile.
7. Ask about one project and verify another project’s context is absent.
8. Confirm secrets and raw transient events were not extracted.
9. Reopen with a fresh service/session and prove current-authority retrieval returns the replacement while stale history cannot become current.
10. Replay both the correction ID and source-event ID; prove neither persistence nor impact actions repeat.
11. Correct one client/project lane and prove another lane remains unchanged.
