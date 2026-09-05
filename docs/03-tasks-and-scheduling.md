# 03 — Projects, Duties, Commitments, and Scheduling
<!-- lifecycle-contract: {"authority":"contracts/task-lifecycle.yaml","categories":{"human_states":["active","waiting","blocked","parked","partial","done"],"native_statuses":["triage","todo","ready","running","blocked","scheduled","review","done","archived"],"dispositions":["cancelled","superseded","dropped","exception-closed"],"verification_results":["pass","fail","blocked","inconclusive"],"external_effect_results":["confirmed-success","confirmed-failure","unknown"]},"mappings":{"active":{"native_statuses":["triage","todo","ready","running","scheduled","review"]},"waiting":{"native_status":"blocked","requires":["waiting_party","next_check"]},"blocked":{"native_status":"blocked","requires":["blocker","owner","wake_condition"]},"parked":{"native_status":"todo","requires":["checkpoint"]},"partial":{"native_statuses":["todo","ready","running","blocked","scheduled","review"],"requires":["satisfied_criteria","outstanding_criteria","resume_point"],"closes_task":false},"done":{"native_status":"done","requires":["acceptance"]},"dispositions":{"native_status":"archived","requires":["disposition","reason"]}}} -->

The classic failure of an operator is mixing many assignments. The foundation should make concurrent work normal rather than forcing every request into one rigid workflow.

## Work objects are separate

• A **project or workstream** is an outcome area.

• A **duty** is an ongoing responsibility with a defined operating contract.

• A **commitment** is a promised outcome with an owner and next action.

• A **task** is one executable step.

• An **obligation** is a required action created by a contract, policy, meeting, workflow, or dependency.

• A **waiting item** is owned by someone outside the principal until follow-up becomes due.

Do not use these words as synonyms. The separation is what keeps many jobs organized.

## Canonical structured state

Current projects, commitments, tasks, obligations, owners, statuses, next actions, blockers, deadlines, sources, evidence, and completion proof belong in one canonical structured store when the operator needs durable operations.

Readable profiles and dated logs remain important evidence and context. Dashboards and summary files are generated views, not competing sources of truth.

The temporary in-session task list is scratch space. It is not the durable business record.

Native Hermes Kanban is the sole task lifecycle authority and visual queue. An audit-first adaptation may import another existing system as migration input or expose it as a derived/reference integration, but may not retain it as an alternate lifecycle authority. Manual tasks can remain unassigned and inert. Assigned tasks can dispatch to the main operator or a specialist. `tools/operator-state/` remains an optional migration and reference tool rather than a second live task store.

Automatic task reconciliation and native Hermes Kanban behavior are defined in [Task Truth, Evidence, and Kanban](23-task-truth-and-kanban.md).

## Proportional task records

Use `templates/task-contract.schema.json`; examples show the Compact and Full forms. Every contract records a required machine-readable `work_class`, complete `consequences` booleans, and exactly corresponding `risk_flags`. The schema rejects contradictions and enforces each named class’s intrinsic consequences. Enforcement must also derive classification from the requested operation and trusted tool boundary; it must never accept a caller-supplied class or flags as proof that work is safe. These validated fields determine whether Compact is permitted. An **Ephemeral** disposable answer with no follow-up creates no durable task and is a closed class that accepts no task or consequential fields. A **Compact** task records outcome, owner, next action, artifact or source, resume point, and a minimal completion check. A **Full** task adds target, scope and exclusions, requirement version, criteria, authority, dependencies, limits, checkpoint, recovery, evidence method, reviewer, and return contract.

Escalate Compact work to Full as soon as it gains an external write, delegation, dependency, sensitive data, material cost, cancellation risk, or long-lived follow-up. These records are metadata on the canonical Kanban task, never another task store. Lifecycle terms and mappings are normative only in `contracts/task-lifecycle.yaml` and explained in [Task Truth](23-task-truth-and-kanban.md).

## Multiple concurrent work items

An operator may run many cases, campaigns, requisitions, projects, or investigations at once. Each work item keeps its own:

1. Goal and versioned requirements.
2. Owner and stakeholders.
3. Lifecycle and priority.
4. Workflow snapshot.
5. Tasks, obligations, and dependencies.
6. Sources and evidence.
7. Budget and approvals.
8. Activity timeline.
9. Completion evidence.

One person or record may relate to several work items without duplicating identity. Per-work-item status remains independent.

## Duty contracts

A duty is not active until it defines:

1. Purpose.
2. Trigger.
3. Inputs and source authority.
4. Classification and duplicate rules.
5. Allowed automatic actions.
6. Approval actions.
7. Escalations.
8. Failure behavior.
9. Output format.
10. Verification.

The principal can add, pause, modify, or retire duties without rewriting the operator foundation.

## Scheduling belongs to Hermes

Anything that must happen on a cadence should use the current Hermes cron and durable work options according to the behavior required. Confirm current command and platform support before enabling loops, heartbeats, or Kanban behavior.

• Cron owns calendar schedules and delivery.

• Loops may repeat inside an active session when supported and deliberately configured.

• Heartbeats may re-enter an idle session when supported and deliberately configured.

• Kanban can provide durable multi-agent work lanes when its gateway-hosted dispatcher is configured.

Do not duplicate schedules in a domain database. Store a safe Hermes job reference when domain records need to point to an automation.

## Cron discipline

1. Give every job one purpose, schedule, timezone, delivery target, and owner.
2. Load only the tools and skills it needs.
3. Pin the model and provider policy.
4. Use deterministic scripts for checks that need no reasoning.
5. Keep healthy operation silent.
6. Preserve continuity only when the job needs to deduplicate or build on prior outputs.
7. Verify schedule, next run, delivery, and failure behavior.
8. Remove or pause jobs when their governing lifecycle is no longer active.

## Daily executive brief

`templates/daily-brief-routine.schema.json` defines the contract and the adjacent example is disabled by default. Native Hermes cron owns schedule and delivery; configure it only after selecting an IANA timezone and delivery channel. Read canonical Kanban plus approved live sources for decisions waiting, today's commitments, due outside follow-ups, slipped or newly at-risk work, and unresolved consequential effects. Stay silent when empty and verify the provider delivery record. Daily-brief identity is routine + scheduled occurrence + channel + recipient; content digest is evidence, not identity. A brief is a read-only view: it cannot create, close, change, or otherwise distort task truth. Disable and retire the cron route when the duty ends.

Calendar operations use `skills/calendar-operations/SKILL.md`: resolve exact calendar and attendee identity, timezone/DST behavior, conflicts, recurrence scope, approval, idempotency, and provider readback. Calendar evidence may inform Kanban but never replaces it.

## The check, act, verify, log loop

For every commitment:

1. Pull current structured state, profile, log, and relevant live sources.
2. Execute within the active duty and approval policy.
3. Verify against real output.
4. Update canonical state and completion evidence.
5. Append a concise dated activity entry.
6. Deliver one clean result or remain silent when no human action is needed.

That loop turns many concurrent assignments into one coherent operating system.
