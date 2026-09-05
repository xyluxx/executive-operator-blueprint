# Twenty CRM Reference Adapter

Twenty is the recommended open source CRM reference for this blueprint. It is not mandatory.

## Why it fits

A Twenty workspace can represent:

1. People
2. Companies
3. Opportunities
4. Projects
5. Tasks
6. Notes
7. Messages and threads
8. Calendar events
9. Attachments
10. Timeline activity
11. Views and dashboards
12. Workflows
13. Custom objects and fields

Exact objects and fields vary by workspace. Discover live metadata before building filters or writes.

## Connection paths

1. MCP server
2. Twenty API
3. Webhooks
4. Approved browser automation only when a required action has no stable API path

Use the current provider documentation and Hermes MCP commands. Keep the connector disabled until credentials and scopes are verified.

## Discovery

1. Authenticate to the intended workspace.
2. List object metadata.
3. List field metadata for selected objects.
4. Record composite field shapes.
5. Map owner workflows and stages.
6. Identify read and write coverage.
7. Record unavailable features as gaps.

Do not assume a documented object exists in every workspace.

## Recommended agent operations

1. Find people and companies
2. Create or update records with stable deduplication
3. Track opportunities
4. Link projects and tasks
5. Store meeting or relationship notes
6. Build views and dashboards
7. Answer natural language questions from explicit filters
8. Create workflows after approval
9. Log email and meeting outcomes

## Approval defaults

Read only lookup can be automatic within approved scope. New records, bulk updates, deletes, schema changes, workflows, and messages follow the owner’s configured policy.

## Contract tests

1. Workspace identity
2. Metadata discovery
3. Known record read
4. Synthetic create
5. Idempotent retry
6. Narrow update and readback
7. Archive or delete semantics
8. Composite field filter
9. View or dashboard total reproduction
10. Credential disable

Record provider object IDs in the private integration registry only.
