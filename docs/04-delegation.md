# 04. Delegation and Specialist Work
<!-- lifecycle-contract: {"authority":"contracts/task-lifecycle.yaml","categories":{"human_states":["active","waiting","blocked","parked","partial","done"],"native_statuses":["triage","todo","ready","running","blocked","scheduled","review","done","archived"],"dispositions":["cancelled","superseded","dropped","exception-closed"],"verification_results":["pass","fail","blocked","inconclusive"],"external_effect_results":["confirmed-success","confirmed-failure","unknown"]},"mappings":{"active":{"native_statuses":["triage","todo","ready","running","scheduled","review"]},"waiting":{"native_status":"blocked","requires":["waiting_party","next_check"]},"blocked":{"native_status":"blocked","requires":["blocker","owner","wake_condition"]},"parked":{"native_status":"todo","requires":["checkpoint"]},"partial":{"native_statuses":["todo","ready","running","blocked","scheduled","review"],"requires":["satisfied_criteria","outstanding_criteria","resume_point"],"closes_task":false},"done":{"native_status":"done","requires":["acceptance"]},"dispositions":{"native_status":"archived","requires":["disposition","reason"]}}} -->

Delegation adds capacity. It does not transfer accountability away from the main operator.

## Execution options

### Direct main agent

Use for conversation, judgment, approvals, small actions, and final verification.

### Temporary subagent

Use for bounded research, extraction, review, comparison, or coding that ends with one deliverable. The child receives explicit context and returns a provisional summary. It is not a durable scheduler and may not survive the parent process ending.

### Durable background work

Use a supervised process, Hermes cron, Kanban, or another durable worker when work must survive a restart or continue over time.

### Persistent profile or Bot

Use for a long lived specialist with separate memory, credentials, skills, routines, identity, or machine. Recommend this only when sustained work justifies maintenance.

### Coding harness

Hermes can operate Codex, Claude Code, OpenCode, or another approved harness. Authentication may use a supported subscription session or API route, subject to provider terms and the actual environment.

## Specialist brief

Delegation always requires the Full contract in `templates/task-contract.schema.json`; it cannot use the Compact path. The contract lives on or with the canonical Kanban card and does not create another task store.

Every assignment includes:

1. Exact goal
2. Relevant current context
3. Source authority
4. Latest corrections
5. Scope and exclusions
6. Working directory and branch
7. Allowed tools
8. Approval boundaries
9. Acceptance criteria
10. Required evidence
11. Expected output format
12. Next action ownership

## Coding coordination

1. Inspect the repository and current branch.
2. Use a separate branch or worktree when several writers may act.
3. Keep one writer per worktree.
4. Preserve uncommitted work.
5. Run the project’s tests.
6. Review the diff.
7. Verify the built artifact or live target when applicable.
8. Never accept a harness summary as proof.

## Manager loop

```text
Resolve context
→ assign bounded work
→ follow progress
→ receive result and evidence
→ verify independently
→ record current state
→ own follow up
→ report one clean answer
```

## Submission, review, and targeted rework

A worker may submit a deliverable and criterion results; submission moves Full work to `review` and never accepts it. The main operator evaluates the submission with the protected acceptance policy and current canonical Kanban record. Routine work may use deterministic checks or exact provider readback as independent verification. Consequential or judgment-heavy work additionally requires a reviewer who is not the worker.

Every required criterion must have a current `pass` with relevant, accessible evidence and a matching verifier result. A failed, blocked, inconclusive, missing, stale, or irrelevant result keeps the task open. Rework names the failed criteria and required actions while preserving unaffected passes. A human exception is recorded as `exception-closed`, not rewritten as successful acceptance.

The executable reference is `tools/operator-control/acceptance.py`; its records are defined by the five acceptance schemas under `templates/`. It reads task truth supplied from Kanban and creates no task database or scheduler.

## Bots

Bot Mode is a native Desktop option built on profiles. Bots can have their own chat, model, memory, skills, routines, avatar, direct messages, mentions, and groups.

Bot messages do not automatically merge memory or become canonical truth. Profiles do not automatically sandbox the whole filesystem.

The owner should normally interact with the main operator, not switch manually between the main agent and specialists.

## Authentication and cost

Before using a remote or unattended harness:

1. Verify a real headless prompt.
2. Confirm the authentication method is permitted and durable enough.
3. Pin the model and provider.
4. Set budget and timeout.
5. Confirm filesystem and network permissions.
6. Define cancellation and recovery.

An existing paid subscription is not a guarantee that remote unattended use is available.

## Failure behavior

1. Preserve partial output and tool evidence.
2. Name the failing layer.
3. Retry only when the failure is transient and the action is idempotent.
4. Read external targets before retrying uncertain writes.
5. Move durable work to a durable worker rather than repeatedly respawning temporary children.
6. Escalate missing authority, credentials, or judgment to the owner.

## Verification

1. Temporary worker receives no unrelated context.
2. Child cannot exceed its tool boundary.
3. Result remains provisional until verified.
4. Interrupted work retains a save point.
5. Two coding workers do not edit one worktree.
6. Tests and build outputs are real.
7. Persistent specialist has scope, credentials, routines, owner, and shutdown condition.
8. External actions remain approval controlled.

## Managed-team dispatch contract

Use native Kanban for durable queued work and native profiles/Bot Mode for durable identities; short bounded fan-out may use delegation. A versioned specialist brief contains only named inputs and explicit exclusions. Before protected work, the adapter reads the canonical board, task, run, and claim lock; it rejects foreign boundaries, cancellation, stale workers, and an occupied exact-target writer lease. Worker output is provisional. Dependencies release consequential effects only from a signed accepted outcome or artifact version, and parent completion requires separate integrated compatibility and merge acceptance. Approval never descends to children.
