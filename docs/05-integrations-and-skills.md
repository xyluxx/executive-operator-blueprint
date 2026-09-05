# 05. Integrations and Skills

The repository is not a closed application. It is a Hermes distribution with provider neutral capability contracts.

## Four layers

### Native Hermes

Platform features available in the installed Hermes version, such as profiles, sessions, memory framework, skills, plugins, MCP, gateway adapters, cron, delegation, Bots, Desktop, and backups.

Native does not mean configured or verified.

### Bundled here

This repository supplies:

1. Generic `SOUL.md`
2. Six reviewed core skills and seven disabled optional domain skills
3. Operator State reference tool
4. Secure Credentials reference toolkit
5. Website Watchdog deterministic collector
6. Capability and integration manifests
7. Onboarding and installation contracts
8. Tests and validation

Bundled does not mean enabled in a private profile.

### Optional connectors

Owner selected email, calendar, meeting, CRM, marketing, storage, channel, model, coding, and secret providers.

Optional connectors start disabled and credential blocked.

### Blueprint extensions

Custom business records, runtime hooks, workflows, policies, or adapters built for a proven need. Planned extensions must not be described as installed.

## Native first order

1. Hermes feature
2. Installed skill
3. MCP server
4. Plugin or gateway adapter
5. Provider API or webhook
6. Approved browser automation
7. Custom code

## Bundled skills

1. `continuity`
2. `integration-onboarding`
3. `inbox-triage`
4. `meeting-action-items`
5. `document-action-items`
6. `grounded-citations`

Domain procedures are install-on-demand packs in `optional-packs.yaml`, not core routing rules.

## Hermes skill ecosystem

Search the current catalog rather than relying on a frozen list.

```bash
hermes skills search <capability>
hermes skills inspect <identifier>
hermes skills install <identifier>
hermes skills audit
```

Useful current categories include documents, spreadsheets, PDF, presentations, Google Workspace, meeting actions, YouTube content, research, Airtable, Notion, Box, maps, GitHub, testing, and weekly reviews.

A skill can be bundled with Hermes, installed from a registry, local to a user, or local to a trusted project. Inspect its commands, network access, dependencies, platform support, and source before enabling it.

## Integration lifecycle

1. Proposed
2. Disabled
3. Credential blocked
4. Configured
5. Testing
6. Active after the separate capability status is Verified
7. Degraded
8. Paused
9. Retired

## Credential activation

1. Register safe metadata.
2. Define scopes and operations.
3. Keep connector disabled.
4. Build non-secret tests.
5. Receive credentials through a protected path.
6. Test authentication.
7. Test the narrowest read.
8. Test an approved safe write when applicable.
9. Read back the target.
10. Record evidence and enable.

## Executable onboarding order

1. Define the outcome and exact evidence.
2. Inspect current Hermes, tools, skills, plugins, MCP, and existing routes.
3. Read dated official documentation and inspect source, immutable version, license, dependencies, permissions, data path, and cost evidence.
4. Compare native, reviewed skill or plugin, MCP, direct API, browser or custom code, and `do-not-enable`.
5. Obtain selection approval and pin an immutable commit or digest.
6. Run synthetic proof through the fake adapter; make no live call.

Evidence authority is exact, not host-based. `contracts/evidence-authorities.json` is the integrity-pinned protected registry keyed by provider and evidence kind. Source evidence must identify the reviewed GitHub owner/repository and immutable commit path; documentation, scope, data-policy, and cost evidence must use the exact registered canonical URL and authority ID. A URL supplied by an onboarding caller—even one on an official host—does not establish authority. Mutable pages must be read by a trusted resolver that rejects redirects or canonical mismatches and returns timestamped signed metadata binding the registry identity, canonical URL, title, content digest, and required assertions. Registry integrity failure blocks promotion.
7. Request separate exact live approval, then run read, write, and exact-target readback.
8. Reconcile unknown effects before retry; test revoke, disable, fallback, and rollback.
9. Capture a reviewed reusable skill or lane only after removing private data.

The schema-backed lane matrix is [`contracts/business-lane-preservation.yaml`](../contracts/business-lane-preservation.yaml). Unselected lanes remain disabled.

## Examples, not limits

1. Google Meet native plugin or another meeting adapter
2. Fathom, Teams, Zoom, or another note source
3. Twenty or an existing CRM
4. Google Workspace, Graph, IMAP and SMTP, or another email provider
5. DataForSEO or another SEO data provider
6. Firecrawl, browser, search API, or public source
7. Direct marketing APIs or an aggregator
8. Bundled vault or another secret manager
9. Codex, Claude Code, OpenCode, or another harness

## Skill improvement

New procedures are not automatically safe or saved.

A repeated need can produce a proposed skill. Search first, write the smallest complete procedure, add tests, remove private data, review approval and provider assumptions, then enable and verify.

## Verification

1. Every claimed capability has a layer and lifecycle state.
2. Optional connectors default disabled.
3. No API availability claim is treated as implementation.
4. No secret value enters repository metadata.
5. Required skills load in the target profile.
6. Provider replacement preserves the capability contract.
7. Disabled and retired items disappear from active routing.
