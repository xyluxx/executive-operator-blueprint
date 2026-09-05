# 10 — Reusable Operator Foundation and Capability Lanes

A serious agent should not be rebuilt from scratch for every client, department, or purpose. The right model is a stable Hermes operator foundation with a small overlay that defines the new agent's identity, duties, obligations, records, integrations, and approval boundaries.

## The two layers

### Layer 1: the reusable foundation

Every operator starts with the same operating kernel:

1. An isolated Hermes profile or dedicated machine.
2. Its own `HERMES_HOME`, configuration, secrets, sessions, memory, skills, cron jobs, plugins, and gateway.
3. A clear identity in `SOUL.md` and principal context in `USER.md`.
4. Tiered memory with session search and a structured memory provider.
5. Memory First retrieval before acting on known people, projects, or rules.
6. A source authority order that favors current corrections and live systems over summaries.
7. One commitments model with owner, status, next action, blocker, deadline, source, and evidence.
8. A distinction between the agent's work, the principal's work, and outside waiting.
9. Approval gates for external communication, spending, access, deletion, screening, offers, and other consequential actions.
10. Native Hermes configuration for models, fallback providers, credential pools, MCP servers, skills, plugins, cron, delegation, sessions, and messaging.
11. Persistence, backups, monitoring, recovery, and verified reboot behavior.
12. A governed extension process so the agent can improve safely instead of becoming rigid.

This layer stays almost identical across installations.

### Layer 2: the duty overlay

The overlay answers what this agent is responsible for:

1. Domain and purpose.
2. Principal and stakeholders.
3. Duties and triggers.
4. Records and source systems.
5. Tasks and obligations.
6. Domain-specific workflows.
7. Integrations and required capabilities.
8. Approval policy.
9. Escalation rules.
10. Reports and communication style.
11. Acceptance tests.
12. Credential gates.

Recruiting, executive support, research, operations, and marketing lanes share the same foundation. Only the lane-specific duties and permissions change.

## Identity, behavior, and duties are different things

Do not put every rule into one giant persona file.

• `SOUL.md` defines character, voice, truthfulness, judgment, and stable behavior.

• `USER.md` defines the principal and their confirmed preferences.

• A duty skill defines domain procedures, approval rules, sources, and verification.

• Project files define current work and readable context.

• A canonical domain database holds structured current state when the work requires it.

• Hermes sessions, memory, cron, MCP, models, and credentials stay in their native Hermes locations.

This separation lets duties change without rewriting the agent's identity.

## Flexible work, not a fixed form

A capable operator receives new assignments in conversation. It should be able to create multiple projects, cases, requisitions, campaigns, or investigations at once.

Each work item gets its own:

1. Goal and versioned requirements.
2. Owner and stakeholders.
3. Priority and lifecycle.
4. Workflow snapshot.
5. Tasks, obligations, and dependencies.
6. Sources and evidence.
7. Approvals and budget.
8. Activity history.
9. Result and verification.

Unknown fields do not prevent capture. They become explicit missing information and the agent asks only when the missing answer changes the next action.

## Source authority

Every operator should define a deterministic authority order. A safe default is:

1. The principal's current correction.
2. The live external source.
3. Canonical structured current state.
4. Stable profile.
5. Dated activity log.
6. Generated summary.
7. Session history.
8. Memory.
9. Temporary task scratchpad.

When sources conflict, the higher source wins and the lower claim is marked superseded.

## The commitment model

Every meaningful commitment should record:

1. Outcome.
2. Workstream or project.
3. Owner and owner type.
4. Status.
5. Priority.
6. Next action.
7. Blocker.
8. Waiting party.
9. Deadline and timezone.
10. Source and evidence.
11. Approval requirement.
12. Completion evidence.

Waiting on another person is not automatically a task for the principal.

## Provisioning sequence

1. Create or install an isolated Hermes profile or dedicated instance.
2. Configure models and verified fallback providers through Hermes.
3. Configure secrets through Hermes `.env`, OAuth, credential pools, or a supported secret backend.
4. Install the common foundation files and skills.
5. Configure holographic or another chosen memory provider and seed only verified facts.
6. Install the duty overlay.
7. Add native MCP servers through `hermes mcp add` or the dashboard.
8. Add domain code only for state or workflows Hermes does not natively own.
9. Configure persistence, backups, monitoring, and recovery.
10. Run a fresh-session identity test, synthetic duty test, credential-disabled test, and reboot test.
11. Enable each external integration only after a live contract test.
12. Export or publish the profile as a versioned distribution with secrets and personal memories excluded.

## Profile distribution model

Hermes profile distributions are the clean delivery mechanism for a reusable operator. A distribution carries the foundation, persona template, skills, cron definitions, plugins, and MCP configuration. Credentials, private memories, and sessions remain local to each installation.

This creates one versioned foundation that can improve without overwriting an operator's private context.

## Definition of ready before credentials

An operator is precredential ready when:

1. Identity and duty boundaries are installed.
2. Memory is configured and retrieval tested.
3. Domain state and workflows work with synthetic data.
4. Integrations are registered but disabled.
5. Credential metadata names the native Hermes destination for every secret or OAuth connection.
6. Fallback routing works with simulated provider failures.
7. External side effects remain blocked without credentials and approval.
8. Backups, restore, monitoring, and restart recovery pass.
9. The only remaining blockers are human authorization or provider credentials.

That is the point where adding credentials activates a tested system instead of starting a new build.
