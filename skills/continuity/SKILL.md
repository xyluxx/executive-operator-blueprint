---
name: continuity
description: Use when work pauses, switches, or resumes later.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [continuity, tasks, checkpoints]
---

<!-- lifecycle-contract: {"authority":"contracts/task-lifecycle.yaml","categories":{"human_states":["active","waiting","blocked","parked","partial","done"],"native_statuses":["triage","todo","ready","running","blocked","scheduled","review","done","archived"],"dispositions":["cancelled","superseded","dropped","exception-closed"],"verification_results":["pass","fail","blocked","inconclusive"],"external_effect_results":["confirmed-success","confirmed-failure","unknown"]},"mappings":{"active":{"native_statuses":["triage","todo","ready","running","scheduled","review"]},"waiting":{"native_status":"blocked","requires":["waiting_party","next_check"]},"blocked":{"native_status":"blocked","requires":["blocker","owner","wake_condition"]},"parked":{"native_status":"todo","requires":["checkpoint"]},"partial":{"native_statuses":["todo","ready","running","blocked","scheduled","review"],"requires":["satisfied_criteria","outstanding_criteria","resume_point"],"closes_task":false},"done":{"native_status":"done","requires":["acceptance"]},"dispositions":{"native_status":"archived","requires":["disposition","reason"]}}} -->

# Continuity

Keep unfinished executive work resumable without duplicating tasks or pretending a session transcript is canonical state.

## When to Use

- A task starts, pauses, changes subject, becomes blocked, or resumes.
- New evidence changes an existing commitment.
- Do not use for a disposable answer with no follow-up.

## Procedure

1. Search current tasks and project lanes for the same outcome, target, source identity, or external ID. Update an existing record when found.
2. Use `contracts/task-lifecycle.yaml` as the only lifecycle vocabulary and mapping authority. Human labels do not become native Kanban statuses.
3. Choose the proportional contract in `templates/task-contract.schema.json`: **Ephemeral** for a disposable answer with no follow-up and no task; **Compact** for small reversible, read-only, or internal durable work; **Full** for delegated, scheduled, sensitive, dependency-producing, costly, or externally consequential work.
4. Escalate Compact work to Full when it gains an external write, delegation, dependency, sensitive data, material cost, cancellation risk, or long-lived follow-up.
5. Before switching away, save only the contract-required checkpoint. A partial result records satisfied criteria, outstanding criteria, and the exact resume point and remains open.
6. On resume, re-read the canonical record and any live source changed since the save point. Reconcile conflicts using the source authority in `SOUL.md`.
7. After execution, update state and attach evidence. Keep unresolved work open; `done` requires acceptance metadata.
8. Normalize conversation, meeting, email, and calendar observations through `tools/task-reconciliation/reconcile.py` when automatic adapters are configured. Stable source IDs and principal/workstream/target identities resolve one native card; notification receipts remain separate delivery metadata.
9. A claimed email, meeting, or calendar invitation is not completion. Only current trusted evidence accepted for every required criterion may transition review to done. After accepted meaningful owner work, emit the optional owner acknowledgment once and preserve or create the idempotent recommended next card.
10. For an explicit correction, create the schema-backed record and route it to the existing authority named in `docs/02-memory.md`. Preserve source/event identity, timestamps, exact scope/target, and prior claim/version. Ask for confirmation if durability or scope is ambiguous; keep session-only clarification non-durable.
11. After the authority increments its version, inspect active native work for exact prior-claim consumers. Block affected task/criteria/evidence/schedule/dependency work, cancel affected authority, and rebrief affected workers through their existing adapters. Do not disturb unrelated work or create a task mirror.

Completion criterion: a fresh session can resume the exact next action, and duplicate search returns one canonical record.

## Behavioral Tests

- Pause mid-task, open a fresh session, and confirm the next action and artifact are recovered.
- Replay the same source event and confirm no duplicate task is created.
- Apply a current correction and confirm the stale claim is marked superseded.
- Complete only part of a request and confirm the task remains partial.

## Pitfalls

- Do not use memory as the sole record for current commitments.
- Do not infer completion from elapsed time or a worker's claim.
- Do not dispatch unassigned work automatically unless policy explicitly enables it.
- Do not save a project fact, voice rule, or client-specific preference in global memory.
- Do not retry correction persistence under a new ID after an uncertain result; read back the authority using the original correction/source-event keys.

## Verification

Verify one pause/resume round trip, duplicate suppression, conflict reconciliation, and evidence-backed completion in native Hermes Kanban, the sole task-lifecycle authority.
