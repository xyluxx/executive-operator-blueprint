# 11. Native Integrations and Extensions

## Operator control

`plugins/operator-control` is a small disabled by default reference. Enable it only with a separately administered broker or equivalent managed policy service and explicitly supported write adapters. Hooks provide early denial; the authoritative decision remains inside the supported write handler. Installation, update, backup, and rollback inventory includes `plugins/` through `distribution_owned`; there is no general uninstall command, and active-profile decommissioning remains a reviewed native procedure. This reference does not cover arbitrary terminal/browser writes or provide a Kanban pre-transition gate.

A flexible operator must be able to grow. Flexibility does not mean inventing a second framework beside Hermes or letting the agent change itself without controls.

## Native first

Before writing custom code, check whether Hermes already owns the capability.

| Need | Native Hermes home |
|---|---|
| Model and provider | `hermes model`, `config.yaml`, provider settings |
| Fallback models | Hermes fallback providers |
| Multiple keys and OAuth tokens | Credential pools and `auth.json` |
| API keys and bot tokens | `.env` or supported secret source |
| SaaS tools | MCP configuration and `hermes mcp` |
| Procedures | Skills |
| Lifecycle capabilities | Plugins and hooks |
| Recurring work | Cron jobs, loops, or heartbeats |
| Parallel specialists | Delegation, Bots, or Kanban workers |
| Conversation history | Sessions and session search |
| Durable personal knowledge | Memory provider and memory files |
| Project instructions | `AGENTS.md`, `.hermes.md`, or project context files |
| Messaging | Hermes gateway adapters |
| External events | Hermes webhooks or a domain webhook adapter |
| Shareable agent | Profile export or profile distribution |

Custom code should handle domain records and deterministic workflows that Hermes does not natively model. It should not duplicate Hermes model selection, secrets, MCP discovery, memory, cron, sessions, or gateway state.

## Integration registry

Every external integration needs one canonical metadata record. The record contains no secret value.

Required fields:

1. Stable ID and display name.
2. Capability group.
3. Native integration type: MCP, Hermes provider, skill, plugin, webhook, messaging adapter, or domain adapter.
4. Hermes config path, MCP server name, or secret variable name.
5. Authentication method: OAuth, API key, service account, or provider-hosted authorization.
6. Credential status.
7. Scope and permissions.
8. Supported operations.
9. Prohibited operations.
10. Cost model and budget limit.
11. Rate limits.
12. Priority and fallback order.
13. Health and last contract test.
14. Lifecycle: proposed, configured, credential blocked, testing, active, degraded, paused, or retired.
15. Owner, source, and evidence.

The registry says where a credential belongs. Hermes or the selected secret backend stores the value.

## Capability routing and fallbacks

Route work by capability, not by hard-coded vendor name.

Example capability groups:

1. Candidate discovery.
2. Contact enrichment.
3. Email delivery.
4. Scheduling.
5. Background screening.
6. Web research.
7. CRM or ATS records.
8. Document processing.

A routing policy defines:

1. Approved providers.
2. Priority order.
3. Eligibility conditions.
4. Cost and rate limits.
5. Retry policy.
6. Fallback behavior.
7. Stop conditions.
8. Required readback.
9. Coverage-gap reporting.

If the primary provider fails, the agent may continue only through an approved fallback. It must record what source was missed and never silently substitute an unapproved source.

## Extension registry

The extension registry governs changes the agent can propose or make.

Extension types:

1. New record field.
2. New workflow step.
3. New duty.
4. New report.
5. New source adapter.
6. New automation.
7. New skill.
8. New plugin.
9. New MCP connection.
10. New domain object.

Every extension records:

1. Purpose and triggering need.
2. Scope.
3. Type and version.
4. Schema or configuration.
5. Risk level.
6. Approval policy.
7. Migration plan.
8. Rollback plan.
9. Tests.
10. Lifecycle.
11. Audit history.
12. Adoption evidence.

## Safe autonomy levels

### Level 1: automatic internal change

Allowed when the change is reversible, internal, has no new credential, sends nothing, spends nothing, changes no access, and is covered by tests. Examples include adding an internal report view or proposing a reusable structured field.

### Level 2: proposal and approval

Required for a new external connector, new recurring automation, new workflow decision, new data retention rule, or a change that affects principal-visible behavior.

### Level 3: exact action approval

Required for external messages, invitations, spending, screening orders, offers, adverse action, access changes, credential changes, destructive merges, deletions, and production deployment where the target is not already approved.

## Extension sequence

1. Detect a repeated gap or new duty.
2. Search existing Hermes capabilities, skills, MCPs, plugins, and domain objects.
3. Reuse or extend the existing capability when possible.
4. Write the proposed extension record.
5. Classify risk and approval level.
6. Write a failing test for the new behavior.
7. Implement the smallest extension.
8. Run unit, integration, security, migration, and rollback tests.
9. Activate within the approved scope.
10. Verify real output.
11. Record adoption, cost, and result.
12. Retire unused extensions cleanly.

## Credential gate pattern

Precredential work should finish everything that does not require secret material:

1. Register the integration metadata.
2. Install the native MCP or adapter in a disabled state.
3. Define required environment variable or OAuth destination.
4. Build capability and contract tests with provider sandboxes or mocked transport.
5. Verify that missing credentials fail closed.
6. Document the exact authorization step.
7. Stop at the credential gate.

After credentials arrive:

1. Store them through Hermes or the supported secret backend.
2. Test authentication.
3. Test the narrowest required read.
4. Test one safe write when authorized.
5. Read back the result.
6. Enable the integration.
7. Record scopes and evidence.

## Avoiding duplicated state

A domain database may store business objects and integration mechanics. It should store safe references to Hermes resources, not copies of them.

Do store:

1. MCP server name.
2. Secret variable name.
3. Provider connection ID.
4. Safe external record ID.
5. Contract-test status.
6. Capability and routing metadata.

Do not store:

1. API keys.
2. OAuth tokens.
3. Full Hermes configuration.
4. Session transcripts.
5. Personal memory copies.
6. Duplicate cron definitions.
7. Duplicate model fallback state.

## Verification checklist

1. Native Hermes capability search completed before custom build.
2. No secrets appear in domain records, logs, prompts, or exports.
3. Missing credentials fail closed.
4. Every active integration passed a real contract test.
5. Every external write has idempotency and readback.
6. Fallbacks are approved, tested, and cost bounded.
7. Extensions have migration and rollback paths.
8. The canonical record can explain why each capability is active.
9. Disabled or retired integrations are excluded automatically.
10. A profile export strips credentials and private memory.
