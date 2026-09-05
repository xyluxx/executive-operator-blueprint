# 18. Single Operator or Managed Team

Both are first-class modes. Choose from workload and isolation needs; there is no mandatory single-operator trial.

## Single-operator fit

One main operator keeps the complete picture, uses temporary specialists for bounded work, and remains responsible for verification and follow up.

This has the lowest maintenance cost and the least risk of memory divergence.

Use it when:

1. Work volume is manageable by one operating context.
2. Credentials do not require separate identities.
3. Specialist work is occasional.
4. The owner wants one relationship and one conversation.

## Managed team option

Use persistent profiles or Bots only when the work justifies them.

Good reasons include:

1. Recurring high volume over weeks or months
2. Separate legal, privacy, or credential boundaries
3. A genuinely different identity or communication role
4. Distinct tools and routines
5. Dedicated specialist knowledge with continuing responsibility
6. Work that must run on another machine

A task, file, meeting, or short project is not enough reason by itself.

## One interaction model

The owner chooses one operating experience:

### Single agent experience

The main agent works directly and delegates temporarily when useful.

### Managed team experience

The owner still speaks to the main operator. Persistent specialists operate behind it. The owner does not have to switch manually between the main agent and Bots.

Direct specialist chats can exist for administration or exceptional cases, but they are not the normal task intake path.

## What Hermes provides

Hermes profiles can have separate configuration, models, memory, skills, credentials, sessions, cron jobs, and gateways.

Bot Mode provides a visual roster, one canonical chat per profile, routines, mentions, direct messages, and group chats. Bots can run across connected machines.

These are native platform capabilities. They do not automatically solve source authority, shared truth, manager accountability, or cross profile security.

## Main operator contract

Before delegation:

1. Resolve the correct workstream.
2. Retrieve current corrections and live source requirements.
3. Build a bounded brief.
4. Name acceptance criteria and approval limits.

During work:

1. Track the run and owner.
2. Resolve scope questions.
3. Preserve progress if interrupted.

After work:

1. Treat the specialist result as provisional.
2. Verify material claims and artifacts.
3. Update the agreed current record.
4. Preserve evidence.
5. Own the next action.
6. Report one clean answer to the owner.

## Memory model

Do not copy the main agent’s complete memory into every specialist.

Each specialist keeps focused working memory. Shared current facts live in a canonical store that the main operator controls. Messages between agents do not silently become shared truth.

## Isolation

Profiles isolate Hermes configuration and state, but do not automatically sandbox every local file a terminal can access. Use tool restrictions, separate operating system users, containers, or dedicated hosts when enforcement matters.

## Readiness for either deployed mode

1. The selected mode's task continuity passes.
2. Source authority and corrections work.
3. Delegation packets are current.
4. Specialist output is verified.
5. No unrelated context leaks in tests.
6. External actions remain approval controlled.
7. Every specialist has scope, tools, data boundary, routines, owner, and shutdown condition.
8. A read only or draft only shadow period passes.

## Exit path

A specialist can be paused or retired without losing canonical work. Disable routines, revoke credentials, preserve required evidence, update ownership, and confirm the main operator can resume the work.

## Enforceable managed execution

Native Kanban alone owns cards, dependencies, claims, runs, heartbeats, retry attempt history, and lifecycle events. The optional control adapter keeps no mirror task database. Immediately before protected dispatch and again before each external effect or callback it reads the exact board/card/current run and checks board, client, profile, workspace, credential scope, task version, run ID, claim lock, cancellation, policy digest, approval, and exact target lease.

Use one writer lease per exact protected target. Use separate worktrees or OS locks for shared files and provider idempotency or conditional writes for remote targets. A stale replacement return or duplicate callback fails its fence. If the route cannot provide a concrete gate, keep it manual or `blocked` in `contracts/enforcement-coverage.yaml`.

Managed writes admit only the exact `local-sqlite` instance created by the protected adapter registry. The registry binds implementation identity and executable-code digest to a provider capability record, public key, and conformance receipt. Subclasses, caller-created instances, self-attested flags, generic callbacks, and all external SaaS adapters are Blocked. Controlled run replacement first CAS-invalidates the active provider generation, then replaces the controller lease; direct CLI/dashboard reassignment is unsupported and is detected for reconciliation rather than falsely claimed as prevented.

Reassignment changes the worker, not the task's total budget, deadline, spend, repair history, evidence, or input versions. The main operator remains accountable for canonical context, accepted dependencies, integrated parent acceptance, and the next action. Specialist briefs use `templates/specialist-contract.schema.json`; retirement uses `templates/specialist-retirement.schema.json` and must disable schedules, revoke credentials, transfer cards, preserve evidence, and prove resume through the main operator.
