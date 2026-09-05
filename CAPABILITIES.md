# Capability catalog
<!-- capability-status-contract: {"authority":"contracts/capability-status.yaml","statuses":["Native","Blueprint","Bundled","Configured","Verified","Optional","Planned","Blocked"]} -->

The **Executive Operator Blueprint for Hermes** keeps capabilities modular: the outcome and safety contract stay stable while providers and implementation routes can change. Max is one private instance, not the public product name.

## How to read this catalog

1. **Native** means the tested Hermes version or host surface supplies the feature. `Built-in` is not a second status; use the canonical label Native.
2. **Blueprint** means this repository documents the behavior or implementation contract.
3. **Bundled** means this repository ships the skill, tool, template, schema, or profile asset.
4. **Configured** means a private deployment selected and configured a route.
5. **Verified** means its end-to-end contract passed, including required readback.
6. **Optional** means it is not required for the base executive operator.
7. **Planned** means it is documented but not configured and verified.
8. **Blocked** means a named dependency, permission, decision, or test prevents use.

These eight case-sensitive labels are the only capability statuses; [`contracts/capability-status.yaml`](contracts/capability-status.yaml) is normative. A Native or Bundled capability is not automatically Configured. A Configured capability is not Verified until its real contract test passes. No external account is connected by this catalog.

## Mandatory capability-discovery loop

Run this before selecting a provider or writing custom code:

1. Define the outcome, source of truth, authority, data class, and acceptance evidence.
2. Inspect native Hermes and current tools, providers, skills, plugins, MCP servers, CLIs, APIs, and approved browser routes.
3. Read current official Hermes and provider documentation and verify commands with live help.
4. Search installed, bundled, and available skills and plugins.
5. Inspect candidate source, provenance, license, maintenance, dependencies, permissions, network access, secret handling, data storage and retention, telemetry, cost, limits, and revocation.
6. Propose viable native/current, extension, custom-gap, and do-not-enable options with tradeoffs.
7. Configure only the approved route with minimal scopes, approval policy, budget, fallback, notification, disable, and rollback.
8. Test synthetic success and failure cases first.
9. Test the narrowest approved real examples and read back consequential writes.
10. Capture the verified procedure as a reusable skill, adapter contract, routine, or private operating note.

If no route passes, label the capability Planned or Blocked. Do not imply turnkey connected accounts.

## Core operating capabilities

| Capability | What the owner experiences | Delivery | Setup and proof |
| --- | --- | --- | --- |
| Natural task intake | Speak normally without filling a form | Bundled operator contract | Test new work, correction, hold, completion, and return language |
| Working stack | Current focus, active work, parked work, waiting, holds, done, and superseded work stay distinct | Native Hermes Kanban plus bundled continuity skill | Resume a parked item from its existing card without creating a duplicate |
| Save points | Partial work keeps completed steps, remaining steps, current artifact, owner, and next action | Kanban comments and metadata plus bundled continuity rules | Verify the same card resumes after a fresh session |
| Source authority | Current correction and live evidence beat old memory | Bundled foundation | Inject a contradiction and prove the correct source wins |
| Selective memory | Stable preferences stay available without loading every project | Native memory plus bundled policy | Fresh session recall and contradiction tests |
| Searchable history | Recover exact prior conversations and artifacts | Native sessions and session search | Find and open a known historical message |
| Evidence based completion | A task remains open until every stated criterion is verified | Bundled foundation | Try to close a task with one missing criterion |
| Automatic task reconciliation | Conversations, meetings, email, calendar, files, CRM, and automation evidence update the existing task | Native Kanban, bundled procedure, and selected source adapters | Replay an event, prove no duplicate, verify partial versus full completion, then confirm the current list immediately |
| Visual task board | View and manually edit triage, todo, ready, running, blocked, scheduled, review, done, and archived work | Native Hermes Kanban by default | Prove unassigned cards remain manual, assigned cards dispatch correctly, and every surface reads the same board |
| Learning loop | Repeated procedures can become reviewed skills | Native skills plus bundled extension policy | Create, validate, disable, and roll back a private test skill |

## Communication and device capabilities

| Capability | Native or flexible path | Notes |
| --- | --- | --- |
| Desktop | Native Hermes Desktop on macOS, Windows, and Linux | Files, previews, sessions, memory, settings, terminal, projects, and multiple profiles |
| Remote Desktop | Native remote gateway, SSH, Hermes Cloud, or local connection | Test both HTTP and WebSocket paths; protect internet reachable backends with appropriate authentication |
| Telegram | Native gateway adapter | Supports voice, images, files, threads, typing, and streaming according to current Hermes documentation |
| Discord | Native gateway adapter | Supports text and voice workflows, files, threads, reactions, and streaming |
| Slack | Native gateway adapter | Supports files, threads, reactions, voice messages, typing, and streaming |
| WhatsApp | Native personal bridge or WhatsApp Cloud API | Choose according to provider terms, account type, and desired reliability |
| Signal | Native gateway adapter | Requires its own local or remote setup |
| SMS | Native gateway adapter | Carrier, sender, cost, and regional compliance still apply |
| Email channel | Native gateway adapter | Separate from email account operations through IMAP, Graph, Google Workspace, or another API |
| Google Chat, Mattermost, Matrix, LINE, ntfy | Native gateway adapters | Enable only selected platforms and verify their actual media and thread features |
| Microsoft Teams and IRC | Optional gateway plugins | Install and verify the selected plugin before calling either channel available |
| iMessage | Native support through BlueBubbles or Photon adapters | Requires the bridge environment those systems need |
| Webhooks and API clients | Native webhooks and OpenAI compatible API surface | Useful for custom applications and events |

The same profile and backend can serve Desktop, CLI, web, and messaging. Each conversation can retain its own session. Shared memory and structured work connect the operating picture without claiming every channel is one identical transcript.

## Executive assistant pack

| Capability | Provider examples | What must be configured | Verification |
| --- | --- | --- | --- |
| Inbox triage | Google Workspace, Microsoft Graph, Fastmail, standard IMAP | Account, folders, relevance rules, safe read scope | Find a known thread without changing it |
| Email drafting | Any readable email provider | Voice, sender identity, recipients, approval policy | Draft remains unsent until approved |
| Email sending | Gmail, Outlook, Fastmail, SMTP, CRM mail | Exact sender, permission, approval, idempotency | Sent folder or provider ID readback |
| Calendar | Google Calendar, Microsoft 365, CalDAV | Calendars, timezone, create and update permissions | Read back attendee, time, reminders, and event ID |
| Meeting preparation | Calendar, CRM, email, prior notes | Preparation window and sources | Brief cites current meeting and relationship context |
| Reminders | Hermes cron, calendar, selected channel | Timezone, route, deduplication, retirement | Fire once at the correct local time |
| Daily or weekly brief | Structured work, calendar, inbox, meetings | Included sources and silence policy | No completed, held, or outside owned task appears incorrectly |

## Meetings and notes pack

Hermes supplies a Google Meet plugin for supported live Meet participation, captions, transcript access, and speech. That does not make Google Meet mandatory.

Other meeting and note providers can connect through an API, webhook, MCP server, email delivery, cloud drive, or export file. Examples include Fathom, Microsoft Teams transcripts, Zoom recording workflows, and other note takers.

The meeting contract remains the same:

1. Verify meeting identity and participants.
2. Acquire the transcript or notes from the real provider.
3. Preserve the source as evidence under the selected retention policy.
4. Extract decisions, owners, deadlines, and unresolved questions.
5. Match existing commitments before creating new ones.
6. Write approved relationship results to the selected CRM and lifecycle results to native Hermes Kanban; external task systems are migration inputs or derived/reference integrations only.
7. Never invent an absent transcript.

## CRM and relationship pack

Twenty CRM is the recommended open source reference implementation, not a requirement. It can support people, companies, opportunities, projects, tasks, notes, views, dashboards, workflows, and custom objects.

An existing CRM can be adapted through MCP, API, webhook, database integration, or approved browser automation. Examples may include Salesforce, HubSpot, Pipedrive, Zoho, Airtable, Notion, and industry specific systems.

A conforming CRM adapter defines:

1. Object and field map
2. Stable identity and deduplication keys
3. Allowed reads and writes
4. Approval rules for creation, deletion, bulk changes, and outreach
5. Source ownership
6. Audit and readback behavior
7. Rate and cost limits
8. Retry and idempotency
9. Data retention
10. Contract tests

Useful outcomes include relationship recall, follow up tracking, opportunity summaries, meeting notes, task creation, pipeline views, dashboards, and natural language questions over approved data.

## Documents and knowledge pack

Hermes skills can support:

1. Word documents
2. Excel workbooks and CSV files
3. PDFs, forms, and OCR
4. PowerPoint presentations
5. Cloud documents and drives
6. Notion, Airtable, and Box
7. Cited research
8. Document obligations and action items
9. YouTube transcripts, summaries, chapters, articles, and quoted takeaways
10. Images, audio, and other supported media

Each format still needs a real output check. Writing Markdown that looks like a document is not the same as producing the requested file.

## Research pack

Provider examples include Hermes web search and extraction, a local or hosted crawler, browser automation, public datasets, research APIs, and domain specific sources.

The agent should search when current or missing information matters. If the first route is blocked, it should try an approved alternative and state the remaining limitation. Research outputs distinguish source facts, analysis, and recommendations.

## Artifact storage and previews pack

Accepted files can stay local or move through an approved adapter to Google Drive, OneDrive, Dropbox, Box, S3-compatible storage, or another document system. Each artifact record keeps an ID, current version, checksum, destination, visibility, source work item, and verification evidence.

Temporary hosts such as nip.io or sslip.io only map an IP into a hostname. They do not supply hosting, privacy, access control, or a security review. Use them only for disposable, non-sensitive previews and remove the preview after handoff.

The bundled `artifact-storage-operator` skill defines upload, readback, link, revocation, conflict, and wrong-account tests. Provider accounts and connectors remain Optional.

## Optional connector layer

Composio can provide managed OAuth, connected accounts, triggers, tools, or MCP access for supported SaaS platforms. It is one option alongside direct APIs, native integrations, and provider-specific MCP servers.

The Bundled `composio-integration` skill requires setup-time retrieval of current official pricing, plan, tool-limit, trigger-limit, scope, write-behavior, and data-policy evidence with a timestamp and source. Missing or stale evidence blocks Configured and Verified promotion. No Composio account or credential is included, and this repository makes no current quota or cost claim.

Google Sheets is also Optional, unconfigured, and disabled. The fake-adapter contract tests exact range read, scoped write, exact value readback, idempotency, unknown-effect reconciliation, revoke, and disable. A selected live adapter remains unverified until separately approved provider read/write/readback proof passes.

## Marketing, analytics, and SEO pack

This is an intelligence layer over the owner’s approved accounts and providers.

Possible connectors include:

1. Direct ad platform APIs
2. Google Analytics 4
3. Search Console
4. Google Business Profile
5. DataForSEO for keyword and search data
6. Google Places for business and review data
7. Firecrawl or another crawler
8. A marketing data aggregator
9. CRM conversion and revenue records

Every metric must identify its account, source, time range, timezone, attribution definition, and freshness. The agent should not combine visits, leads, calls, booking clicks, and completed sales as though they are the same event.

Read and analysis can be automatic when approved. Spend, targeting, tracking, publishing, bidding, and campaign changes require the selected approval policy and provider readback.

## Public relations and outreach pack

The bundled PR operations skill turns a configured brief into a background workflow without sharing a private application.

Onboarding captures:

1. Organization and offer
2. Approved representative
3. Pitch voice
4. Audience and opportunity criteria
5. Required introduction and positioning
6. Prohibited claims, topics, and industries
7. Approval and sending policy
8. CRM destination
9. Notification channel
10. Win definition

The agent can monitor approved sources, deduplicate opportunities, research fit, draft in the configured voice, queue approval, log each pitch, watch replies, and notify on material wins. Sending remains controlled by the owner’s policy.

## Credentials pack

The repository includes a generic secure credentials toolkit.

It separates:

1. A metadata registry that is safe to list
2. An encrypted reusable vault
3. Browser encrypted one time intake
4. One time human reveal
5. Agent intake into an exact protected file
6. Fast vault to one time link delivery

The toolkit is an optional reference implementation. Teams may replace it with 1Password, Bitwarden, Vault, a cloud secret manager, or another approved system while keeping the same interface and safety tests.

## Website reliability pack

The full pattern uses three stages:

1. Deterministic health checks with no model call
2. A durable incident queue after repeated confirmation
3. An AI recovery worker only for confirmed incidents

This repository currently bundles and tests the deterministic collector, failure-cycle state, incident-file queue, overlap lock, and recovery cancellation. The leased AI worker, repair executor, notification adapter, and full persistence service are documented patterns and remain Planned until a deployment implements and verifies them.

The owner selects sites, success definitions, independent confirmation, safe repairs, retry limits, and the failure notification route. Healthy checks, brief transients, false alarms, and verified successful recovery can stay silent. Failed recovery is escalated with evidence only after the optional worker and notification path are configured.

## Infrastructure and deployment pack

Skills can cover VPS provisioning, Docker, process supervision, reverse proxies, HTTPS, DNS, GitHub, backups, deployments, rollback, and service recovery.

A budget host may be suitable for ordinary workloads. Regulated or highly sensitive workloads require architecture and provider review. A process showing “online” is not proof that the public service works.

## Coding specialist pack

Hermes can operate approved coding harnesses such as Codex, Claude Code, and OpenCode. The main operator supplies scope and context, follows the run, tests the output, and retains the next action.

Subscriptions and API based routes are both possible. Authentication, model, cost, working directory, branch, permissions, and acceptance tests must be explicit.

## Automation and notification pack

Hermes cron, loops, heartbeats, background sessions, webhooks, and durable work systems can run approved recurring duties.

Every routine defines:

1. Trigger or schedule
2. Timezone
3. Source
4. Owner
5. Automatic actions
6. Approval actions
7. Silence behavior
8. Failure route
9. Deduplication
10. Retirement condition

Notification destinations can include any enabled channel, email account, webhook, or incident service. Ask during onboarding rather than assuming Telegram, email, or Slack.

## Single agent and managed team

### Recommended default: single agent

One main agent owns the complete operating picture. Temporary specialists handle bounded research, coding, review, or extraction and return their work to the main agent.

### Optional: managed team

Use persistent specialist profiles or Bots only when recurring work, separate identities, dedicated credentials, or context volume justify the maintenance cost.

The owner should choose one interaction model. In a managed team, the owner still speaks to the main operator rather than manually switching between the main agent and specialists. The main operator remains responsible for context, verification, records, and follow up.

Bot conversations and memories do not automatically become shared truth. Canonical work records remain authoritative.

## Business owner additions

Optional capability packs can also cover:

1. Competitive and industry monitoring
2. Vendor and contract obligations
3. Recruiting and candidate operations
4. Customer feedback and review response drafts
5. Sales pipeline and follow ups
6. KPI and board briefing preparation
7. Travel and event preparation
8. Price and procurement monitoring
9. Knowledge base maintenance
10. Incident and business continuity coordination
11. Team onboarding and operating procedures
12. Decision journal and unresolved decision tracking

These are patterns, not preauthorized actions. The owner selects the data, providers, budgets, and approval rules.
