# 23. Task Truth, Evidence, and Kanban
<!-- lifecycle-contract: {"authority":"contracts/task-lifecycle.yaml","categories":{"human_states":["active","waiting","blocked","parked","partial","done"],"native_statuses":["triage","todo","ready","running","blocked","scheduled","review","done","archived"],"dispositions":["cancelled","superseded","dropped","exception-closed"],"verification_results":["pass","fail","blocked","inconclusive"],"external_effect_results":["confirmed-success","confirmed-failure","unknown"]},"mappings":{"active":{"native_statuses":["triage","todo","ready","running","scheduled","review"]},"waiting":{"native_status":"blocked","requires":["waiting_party","next_check"]},"blocked":{"native_status":"blocked","requires":["blocker","owner","wake_condition"]},"parked":{"native_status":"todo","requires":["checkpoint"]},"partial":{"native_statuses":["todo","ready","running","blocked","scheduled","review"],"requires":["satisfied_criteria","outstanding_criteria","resume_point"],"closes_task":false},"done":{"native_status":"done","requires":["acceptance"]},"dispositions":{"native_status":"archived","requires":["disposition","reason"]}}} -->

A task reminder system is useful only when the agent updates it without being reminded to do so.

## Task truth contract

`contracts/task-lifecycle.yaml` is the sole normative lifecycle definition. Its schema rejects renamed, missing, reordered, or extra lifecycle values. Other documents explain the contract rather than defining competing lists.

Every meaningful owner or agent commitment records:

1. Outcome
2. Workstream
3. Owner
4. Status
5. Next action
6. Resume point
7. Deadline and timezone when present
8. Completion conditions
9. Evidence sources
10. Blocker or waiting party
11. Approval boundary
12. Completion evidence

A task is not complete because a message sounds finished. It is complete when its saved completion conditions agree with direct evidence.

## Sources that can update a task

1. Current owner correction
2. Calendar event
3. Meeting transcript or recording metadata
4. Sent email and provider readback
5. CRM change
6. File or artifact verification
7. Deployment or service result
8. Approved automation event
9. Manual owner confirmation

## Meeting example

A task says: meet a named person at a stated time and discuss three topics.

The meeting pipeline finds a matching event and transcript. The reconciler checks:

1. Identity or attendee match
2. Time window
3. Meeting actually occurred
4. Required topics were materially covered
5. No higher-authority correction changed the obligation

If every condition passes, the main agent marks the task done, records meeting evidence, and offers the next useful task. If only some topics were covered, it saves partial progress and keeps the remainder open. If identity or topic coverage is uncertain, it asks rather than closing the task.

## Native Hermes Kanban

Hermes Kanban is a durable SQLite-backed board with CLI, dashboard, and agent tool surfaces. It supports boards, tasks, assignees, triage, todo, ready, running, blocked, scheduled, review, done, archived, dependencies, comments, attachments, idempotency keys, runs, heartbeats, and worker dispatch.

Native Hermes Kanban is the sole task lifecycle authority. An audit-first existing installation may import another system as migration input or publish a derived/reference integration, but cannot retain another lifecycle authority. The same native board serves the dashboard, CLI, scripts, and authorized `kanban_*` agent tools, so a manual change and an agent change cannot create competing task lists.

### Canonical mapping

| Operating meaning | Kanban representation |
|---|---|
| Captured but not classified | `triage` |
| Planned or active but not executing | `todo` |
| Ready for the agent | `ready` |
| Being executed | `running` |
| Waiting on human input or external dependency | `blocked` with exact reason, owner, and wake condition |
| Waiting until a known time | `scheduled` |
| Work finished but not accepted | `review` |
| Verified completion | `done` with summary and evidence metadata |
| Historical record | `archived` |

Kanban does not have a native `parked` status. A blueprint must not pretend it does. Parked work remains `todo` with its checkpoint in the body or comment. External systems may mirror that representation as derived/reference views but cannot replace Kanban lifecycle truth.

The human view uses the labels defined by the canonical contract. `parked` maps to `todo` plus checkpoint metadata. `partial` stays in an open native status and preserves satisfied criteria, outstanding criteria, and a resume point. `done` maps to `done` only with acceptance metadata. A disposition is metadata on an `archived` task. Verification and external-effect results are result fields, not task statuses. Changing focus or attention never changes business lifecycle state.

## Proportional contracts

`templates/task-contract.schema.json` defines closed Ephemeral, Compact, and Full records. Required `work_class` and complete `consequences` fields enforce proportional escalation independently of `risk_flags`. Ephemeral answers create no task and cannot carry durable or consequential fields. Compact records keep small reversible, read-only, or internal work light. Full records are mandatory for message sends, invitations, deployments, purchases, access or credential changes, production actions, bulk writes, deletion, delegation, durable schedules, sensitive work, dependencies, material cost, cancellation risk, and long-lived follow-up. If Compact work gains any such property, escalate it before proceeding. The examples are schema-validated by the repository validator.

## Criterion-based acceptance

Successful `done` requires an `accepted` acceptance record for the current task, requirement, artifact, target, and environment versions. Every required criterion must pass; authority must have been valid at action time; dependencies must remain accepted and applicable; and external effects must be resolved. Worker completion claims and accepted child tasks are inputs to review, not acceptance of this task or its parent.

Dispatch binds a run to the canonical serialization and immutable SHA-256 digest of its acceptance policy. The criteria, evaluator, schemas, and protected tests each have protected digests outside worker write authority. Any mismatch fails closed. Authorized policy or criterion changes create a new version; artifact or input changes invalidate only criteria whose `affected_by` declarations intersect the change.

`tools/operator-control/acceptance.py` is a pure thin contract layer over the current Kanban record. It does not own lifecycle, dispatch, scheduling, or task history. Native Kanban remains canonical; only a validated successful acceptance record authorizes the `review` to `done` transition in controlled workflows.

## Correction impact on task truth

Task and requirement corrections append native Kanban metadata/activity; no correction database owns status, owner, next action, schedule, dependency, or worker lifecycle. The correction names the exact prior claim and version. Only active records whose consumed-claim references include that contradicted claim, in the same client and scope, are invalidated. Their current Kanban/scheduler/broker adapters block, cancel, or rebrief them as appropriate. Passing criteria and evidence based on unrelated claims remain current. Approval withdrawal reaches the protected broker before queued affected work may act. See the normative routing and privacy contract in [Memory and Context](02-memory.md).

## Manual and unassigned work

Unassigned cards are manual work. Depending on the creation surface, they can appear in `ready` or `todo`, but the dispatcher skips them because no profile owns them. The owner or main operator can edit, assign, complete, block, schedule, or archive them through the native dashboard, CLI, slash command, or Kanban tools.

Assign a card only when an agent or specialist should execute it. Unassigned or unready cards must never dispatch automatically. Idempotency keys prevent conversation, meeting, email, and webhook replays from creating duplicates.

## Single agent use

The main operator can manage the same board directly. The fresh-profile defaults explicitly enable the native Kanban toolset and initialize the default board. Automatic triage decomposition is disabled, so captured ideas do not silently become AI work.

## Managed team use

Kanban is especially useful when persistent profiles work cards. The gateway-hosted dispatcher can assign a named profile, preserve run history, reclaim crashes, require heartbeats, route review, and store artifacts.

Workers use the native `kanban_*` tools. They do not shell out to the CLI from a task worker.

## Automatic reconciliation loop

1. Capture the source event with its provider ID.
2. Resolve the matching task or produce an ambiguity set.
3. Compare completion conditions.
4. Update only the exact task.
5. Attach evidence and a concise comment.
6. Change owner or waiting state when appropriate.
7. Read back the board or canonical store.
8. Notify the owner only when completion, a decision, a missed deadline, or failed automation deserves attention.

## Motivation without noise

When direct evidence proves the owner completed meaningful work, a short acknowledgment can help:

> Nice work. I marked the meeting task complete from the verified meeting record. The next useful item is the follow-up decision.

Do not congratulate after routine background system work, create guilt, or flood the owner with every state transition.

## Current blueprint status

1. Native Hermes Kanban is the sole task lifecycle authority; existing systems are migration inputs or derived/reference integrations only.
2. The reference installer initializes it and verifies the default board.
3. Unassigned cards remain manual and never dispatch automatically.
4. `continuity` provides the task-truth procedure, and `tools/task-reconciliation/reconcile.py` provides the bundled thin native-Kanban adapter and provider-neutral reconciliation path.
5. Operator State remains a Bundled migration and reference CLI, not a second live task store.
6. Synthetic cross-source, exact-resume, partial-evidence, meeting-acceptance, and acknowledgment-deduplication tests run against a disposable native board. Real conversation, meeting, email, and calendar adapters remain unconfigured until their provider contracts and live evidence tests pass.

## Conformance tests

Hermes Kanban has no persisted focus field. The disposable native-board test therefore creates and manually comments on a real unassigned card, runs a real dispatcher pass, changes an isolated external focus reference, and reads the card back after each operation. This proves dispatcher non-claim and status independence at the Kanban boundary; it does not claim a native focus-transition API exists.

1. A short task message is captured once.
2. A later correction updates rather than duplicates it.
3. An interrupted task retains a resume point.
4. A matching meeting closes only satisfied conditions.
5. Partial topic coverage leaves remaining work open.
6. Waiting belongs to the correct outside party.
7. Hold stays out of immediate attention.
8. Dashboard, CLI, scripts, and Kanban tools read the same task state.
9. Completed work is not reopened by stale history.
10. The owner can ask for the current list and receive the correct answer immediately.
11. A requirement correction increments the card version and supersedes only the cited prior claim.
12. A schedule or worker consuming that claim blocks or receives a new brief while unrelated work remains valid.

## Managed dependencies without a second task system

Native parent links remain the lifecycle ordering mechanism and reject cycles, but raw promotion or direct human completion is not accepted dependency proof for consequential work. Every protected downstream adapter re-reads the canonical card/run immediately before effect and verifies a signed acceptance for the exact upstream outcome or artifact version. Each run records consumed input versions; changes invalidate only affected descendants. Individually accepted children do not accept a parent: the main operator must separately accept integrated compatibility and merge tests.
