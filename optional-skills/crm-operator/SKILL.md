---
name: crm-operator
description: Use when reading or writing CRM records safely.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [CRM, Relationships, Pipeline, Records]
    related_skills: [integration-onboarding, continuity]
---

# CRM Operator

Use this skill for people, companies, opportunities, projects, tasks, notes, communication history, dashboards, and workflows in an approved CRM.

Twenty CRM is the recommended open source reference, not a requirement. Adapt to the owner’s current CRM when it can satisfy the contract safely.

See `references/twenty.md` for the provider-specific reference adapter.

## When to Use

1. Find a relationship or account.
2. Create or update a CRM record.
3. Convert email or meetings into structured follow up.
4. Clean, deduplicate, or migrate records.
5. Build a view, dashboard, or workflow.
6. Answer a natural language question from CRM data.
7. Connect another CRM through MCP, API, webhook, database, or approved browser automation.

## Prerequisites

Record:

1. Provider and workspace
2. Authoritative objects and pipelines
3. Object and field map
4. Stable identity keys
5. Read and write permissions
6. Bulk action policy
7. Approval boundaries
8. Retention and deletion policy
9. Audit fields
10. Rate limits and cost
11. Contract test evidence

## Reference Object Model

A common business model includes:

1. People
2. Companies
3. Opportunities
4. Projects
5. Tasks
6. Notes
7. Messages and threads
8. Calendar events
9. Attachments
10. Activity timeline
11. Custom objects

Map these to the selected CRM rather than assuming exact provider names.

## Read Procedure

1. Resolve workspace and object.
2. Inspect live metadata or tool schemas before using unfamiliar fields.
3. Query by stable identity first.
4. Return source, freshness, and missing fields.
5. Keep provider errors separate from “not found.”

Completion criterion: the result identifies the real workspace, object, record ID, and freshness.

## Write Procedure

1. Search before creating.
2. Resolve duplicates using approved keys.
3. Build an explicit payload with every material field.
4. Show or obtain approval when policy requires it.
5. Use idempotency or upsert when supported.
6. Write the narrowest scope.
7. Read back the exact record.
8. Record the external ID and evidence.

Completion criterion: the intended record exists once and its material fields match.

## Email and Meeting Pipeline

1. Verify the source message or meeting.
2. Match person by approved identity key.
3. Match company by approved organization key.
4. Match an existing opportunity or project before creating one.
5. Extract decisions, tasks, owners, dates, and notes.
6. Propose or perform the approved CRM updates.
7. Link source evidence.
8. Preserve outside waiting separately from internal tasks.

## Dashboards and Natural Language

The agent may create views or summarize CRM data when authorized. Every total must define:

1. Object set
2. Filter
3. Time range
4. Timezone
5. Currency or unit
6. Missing data behavior
7. Query time

A dashboard is a generated view, not a competing source of truth.

## Migration

1. Back up source and destination.
2. Inventory objects, fields, relationships, enums, and files.
3. Map identities and deduplication.
4. Dry run with counts and exceptions.
5. Obtain approval for production mutation.
6. Migrate in bounded batches.
7. Reconcile counts and representative records.
8. Preserve rollback and source evidence.

## Approval Defaults

1. Reads within approved objects may proceed.
2. Private recommendations may proceed.
3. New records, bulk changes, deletions, schema changes, workflows, and outbound communication require the configured policy.
4. Sending from the CRM is still an external message action.

## Pitfalls

1. Do not make Twenty mandatory when an existing CRM works.
2. Do not guess nested or composite field syntax.
3. Do not create a second person because one email format differs.
4. Do not merge records without reversible evidence.
5. Do not treat a CRM total as complete when data coverage is unknown.
6. Do not store secrets in CRM notes or custom fields.
7. Do not let one client workspace enter another context.

## Verification

1. Metadata discovery works.
2. Known record read works.
3. Safe synthetic create and readback work when approved.
4. Retry does not duplicate.
5. Update changes only intended fields.
6. Delete or archive follows provider semantics.
7. Bulk dry run counts match production selection.
8. Email and meeting deduplication work.
9. Dashboard totals reproduce from the underlying query.
10. Disable or credential failure is reported honestly.
