# 15. Provider Adapters and Contracts

The blueprint separates capabilities from vendors. Owners keep their current systems when those systems can satisfy the required contract.

## Adapter principle

A capability states the outcome and safety rules. An adapter states how one provider supplies it.

Examples:

1. Inbox capability can use Google Workspace, Microsoft Graph, IMAP and SMTP, or another mail API.
2. Meeting evidence can use the native Google Meet plugin, Fathom, Teams, Zoom, another note taker, email delivery, or file export.
3. CRM capability can use Twenty, Salesforce, HubSpot, Pipedrive, Zoho, Airtable, Notion, or a custom API.
4. SEO data can use DataForSEO or another search data provider.
5. Web acquisition can use a crawler, search API, browser, or approved dataset.
6. Secret storage can use the bundled vault, 1Password, Bitwarden, Vault, or a cloud secret manager.

## Adapter contract

Every adapter defines:

1. Capability and provider
2. Workspace or account owner
3. Authentication method
4. Credential reference
5. Required scopes
6. Supported reads
7. Supported writes
8. Prohibited operations
9. Data coverage and limitations
10. Cost and rate limits
11. Retry and idempotency
12. Fallback behavior
13. Retention
14. Disable and rollback
15. Last contract test
16. Evidence

## Integration routes

Use this order:

1. Native Hermes feature
2. Existing skill
3. MCP server
4. Hermes plugin or gateway adapter
5. Direct API or webhook
6. Approved browser automation
7. Custom code for a proven gap

Native first does not mean provider locked. It means reusing the correct Hermes extension point.

## Setup states

1. Proposed
2. Disabled
3. Credential blocked
4. Configured
5. Testing
6. Verified
7. Degraded
8. Paused
9. Retired

Configured is not Verified.

## Contract testing

1. Missing credential fails closed.
2. Authentication succeeds.
3. Narrow required read succeeds.
4. Approved safe write succeeds when applicable.
5. Exact target readback matches.
6. Retry does not duplicate.
7. Rate or budget limit stops work.
8. Provider failure produces a clear limitation.
9. Disable path works.
10. No secret appears in logs or records.

## Fallbacks

A fallback is approved separately. It must state:

1. When it may activate
2. Which coverage differs
3. Which permissions it needs
4. What it costs
5. Whether results can be compared
6. What the owner will be told

Never silently replace one data source with another and present the result as equivalent.

## Example: meetings

Google Meet has a native Hermes plugin for supported live workflows. It does not replace a note taker automatically and it does not make other providers incomplete.

If the owner already uses Fathom or another note system, connect it through its best available route. Preserve the same meeting identity, transcript evidence, action extraction, CRM logging, retention, and approval contract.

## Example: CRM

Twenty is the recommended open source reference because its object model is flexible and agent friendly. Existing CRMs remain valid.

Map people, companies, opportunities, projects, tasks, notes, messages, events, and custom objects. Preserve provider IDs and field types. Do not force migration merely to match this blueprint.

## Example: marketing

Direct platform APIs can offer the clearest account semantics. Aggregators can reduce connector work. Both must retain account ownership, metric definitions, time range, freshness, and coverage limits.

A marketing connector is not permission to change spend, targeting, tracking, or campaigns.
