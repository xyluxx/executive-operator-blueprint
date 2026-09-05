# Onboarding

The installer should conduct this as a conversation. Do not dump every question at once. Ask only what changes the setup, group independent choices together, and recommend a default when the risk is low.

Never request a secret in chat. When a connector reaches its credential gate, use the secure intake tool.

The operator-control pack is optional and disabled by default. Keep external writes manual until a selected adapter passes approval denial, exact identity/scope, digest, replay, broker-down, provider-readback, and reconciliation tests. Generic terminal/browser writes and direct Kanban transitions are not covered.

For high-impact credentials, choose a separate UID/container or managed secret service. Verify that Hermes cannot read key/vault files and can reach only ACL-restricted named-operation IPC. This distribution does not install that boundary; record it as `required-unconfigured` until independently demonstrated.

Before this conversation changes an existing Hermes installation, complete the read-only audit in `AI-INSTALL.md`, prove backup and isolated restore, and present a preserve/merge/replace/disable plan. For a fresh installation, recommend a separate profile.

## 1. Purpose and identity

1. What should the agent be called?
2. Is it personal, business, or both?
3. Who is the principal decision maker?
4. What outcomes should it own every week?
5. Which work must it never perform?
6. What tone should it use?
7. How short or detailed should normal answers be?

Recommended default: one direct, calm operating agent that gives the answer first and expands only when the work requires it.

## 2. Natural working style

1. Do you normally finish one task before switching, or move between several?
2. How should parked work return to your attention?
3. What should count as urgent?
4. Which items should stay hidden while on hold?
5. When should the agent ask a question rather than infer?
6. Do you want progress updates during long work, and how often?

Recommended default: preserve a save point whenever attention changes, keep holds out of current lists, and surface only actionable work, late follow ups, approaching deadlines, and required decisions.

### Task truth and visual board

1. Which conversations, meetings, email, calendars, files, CRM records, and automation events may update tasks?
2. What evidence must prove full completion versus partial progress?
3. Should verified personal progress receive a short acknowledgment and next useful task?
4. Which existing systems should feed migration input to or receive a derived/reference view from native Hermes Kanban, the sole task lifecycle authority?
5. How should parked work appear, given that Kanban has no native `parked` status?
6. Which people or specialist profiles may own cards?

Native Hermes Kanban is the sole task lifecycle authority. Manual work stays unassigned and cannot dispatch, assigned work can dispatch, parked work keeps a checkpoint in `todo`, automatic decomposition stays off, source events use idempotency keys, and brief encouragement follows only meaningful verified progress. Existing task systems are migration inputs or derived/reference integrations, never alternate lifecycle authorities.

### Corrections and scope

Select private adapters for project facts, stable principal preferences, voice overlays, and protected approvals. Task/requirement corrections always use native Kanban metadata/activity. Verify each adapter can preserve provenance, exact scope, prior claim/version, correction/source-event idempotency, supersession, retraction, and fresh-session readback. Test two clients and two overlays for isolation. Reject secret-bearing correction content and keep session-only clarification non-durable. Do not enable durable correction handling until an ambiguous statement causes a confirmation request and an approval withdrawal reaches the broker before a queued synthetic action.

## 3. Operating mode

Choose one:

### Single agent

Recommended for most people. One agent owns the complete picture and uses temporary specialists only for bounded work.

### Managed team

Use only for sustained high volume, distinct roles, separate credentials, or long running specialist programs. The principal still speaks to one main operator. The operator manages the specialist profiles and verifies their work.

Do not make the principal manually alternate between both modes.

## 4. Hosting and privacy

1. Local computer, always on VPS, private network server, or regulated environment?
2. Which countries may store or process data?
3. Is any data regulated or contract restricted?
4. What retention period is required?
5. Who may access memory, files, credentials, and logs?
6. What must be deleted on request?
7. What backup and restore expectations apply?

Recommended default for ordinary use: dedicated unprivileged profile, encrypted transport, owner only files, minimal connector scopes, tested backups, and no public backend without strong authentication.

## 5. Channels and devices

Select the channels actually used:

1. Desktop
2. Web
3. CLI or terminal
4. Telegram
5. Discord
6. Slack
7. WhatsApp or WhatsApp Cloud API
8. Signal
9. Email
10. SMS
11. Google Chat
12. Microsoft Teams
13. Mattermost or Matrix
14. LINE
15. iMessage through a supported bridge
16. Another webhook or API channel

For each channel ask:

1. Who may contact the agent?
2. Which users are administrators?
3. Are group messages allowed?
4. Are voice, files, images, threads, or reactions required?
5. Which channel is primary for decisions?
6. Which channel is only a mirror?
7. Where should failures and urgent alerts go?

Recommended default: one primary human channel, Desktop for visual work, and one separate failure route when practical.

## 6. Notifications

Choose what should interrupt the principal:

1. Required decision or approval
2. Approaching deadline
3. Promised response now late
4. Confirmed service failure that automatic recovery could not fix
5. Material opportunity or reply
6. Security or credential problem
7. Scheduled daily or weekly briefing

Choose where each notification goes: primary chat, email, Slack, Teams, SMS, or another enabled channel.

Recommended default: healthy checks, unchanged work, false alarms, and successful automatic recovery stay silent.

## 7. Email and calendar

1. Which provider is used?
2. Which accounts may be read?
3. May the agent draft?
4. Does every send require approval?
5. May it create or modify calendar events?
6. Which calendars and timezones matter?
7. How should reminders and scheduling conflicts be handled?
8. Which messages should become CRM records or tasks?
9. For calendar work, what exact account/calendar IDs, attendee identities, IANA timezone, DST policy, recurrence scope, conflict policy, and approved write boundary apply?

Provider examples include Google Workspace, Microsoft 365 through Graph, Fastmail or another IMAP and SMTP provider. The capability is not tied to one vendor.

Recommended default: reading and private drafting may be automatic; sending, invitations, deletions, and account changes require exact approval.

Calendar procedure is bundled and provider-neutral; adapters stay optional and unverified until a separately approved live contract test confirms idempotency and exact provider readback.

### Private voice profile

Voice learning is opt-in and private. Use only owner-approved representative sent messages, extract bounded style attributes into a base plus separate business, personal, school, legal, or internal overlays, and retain no raw email corpus. The executable `VoiceProfileStore` stores the result only in owner-only private profile state, accessible only to the owner and authorized operator, with encryption at rest required, metadata-only access audit, atomic regular-file writes, symlink/hardlink rejection, and is excluded from public/profile exports. Apply bounded retention, revocation on opt-out, verified deletion on owner request, access revocation on opt-out, and verified source disposal immediately after extraction. Review paired drafts with the owner; corrections update only the relevant overlay. Sending still requires exact approval. Use `templates/voice-profile.schema.json`; do not place completed private profiles in this repository.

### Daily brief

Select the IANA timezone and delivery channel before enabling anything. Start from `templates/daily-brief-routine.example.yaml`, keep it disabled while testing, and let native Hermes cron own schedule and delivery. The brief reads Kanban and approved live sources, stays silent when empty, and requires delivery-record readback. Daily-brief identity is routine + scheduled occurrence + channel + recipient; content digest is evidence, not identity. It cannot create, close, or change task status. Retirement disables the schedule, revokes source access, and verifies no future runs.

## 8. Meetings and notes

1. Which meeting platforms are used?
2. Is live participation required or only post meeting notes?
3. Which note taker or recording provider is available?
4. Where should transcripts and summaries come from?
5. Which decisions and obligations should enter the CRM or task system?
6. How long should recordings and transcripts be retained?

Hermes has a native Google Meet plugin for supported live Meet workflows. Fathom, Teams transcripts, Zoom recorders, and other note takers can connect through their API, webhook, MCP server, email delivery, or export format.

Recommended default: use the existing provider rather than forcing a replacement. Keep the transcript as evidence, extract decisions and owners, and never invent absent notes.

## 9. CRM and relationships

1. Is there an existing CRM?
2. Which objects and pipelines are authoritative?
3. May the agent read, create, update, or delete each object type?
4. Which email and meeting events should be logged?
5. Which dashboards or summaries are useful?
6. What deduplication key identifies a person, company, or opportunity?
7. Who approves bulk changes?

Twenty CRM is the recommended open source reference because it supports people, companies, opportunities, projects, tasks, notes, views, dashboards, workflows, and extensible objects. Existing CRMs remain valid. The adapter should fit the owner’s system rather than forcing a migration.

## 10. Documents and knowledge

Select what the agent needs:

1. Word documents
2. Excel and CSV
3. PDFs and OCR
4. Presentations
5. Cloud drives
6. Notion, Airtable, Box, or another knowledge system
7. YouTube transcript and content analysis
8. Research with citations
9. Contract or policy review

Choose where accepted artifacts live:

1. Local or shared disk
2. Google Drive
3. OneDrive or SharePoint
4. Dropbox
5. Box
6. S3-compatible bucket
7. Another approved document provider

For temporary previews, decide whether disposable non-sensitive links are permitted and how quickly they expire. nip.io and sslip.io provide hostname mapping only, not hosting, privacy, or access control.

If several SaaS providers are needed, decide whether to use direct connectors, `do-not-enable`, or an optional layer such as Composio. Composio and Google Sheets are unconfigured and disabled by default. At setup time retrieve and timestamp current official provider evidence for plan, pricing, scopes, tool and trigger limits, write behavior, and data handling; stale or missing evidence blocks promotion. Run synthetic fake-adapter proof first. Any real read/write/readback requires a separate exact approval naming account, target, operations, payload, and rollback.

Ask where source files live, who owns them, what may be edited, and which formats count as final.

## 11. Marketing, SEO, and growth

1. Which ad platforms and analytics sources are used?
2. Which accounts belong to which business?
3. Is the agent read only, advisory, or approved to make changes?
4. Which conversion definitions are authoritative?
5. Which SEO, keyword, review, and competitor data providers are available?
6. What budget and alert thresholds apply?
7. Which reports should be recurring?

Examples include direct advertising APIs, GA4, Search Console, GBP, DataForSEO, Google Places, Firecrawl, and marketing data aggregators. Every number must name its source, account, time range, and definition.

Recommended default: read and analyze first. Budget, tracking, targeting, publishing, and campaign changes require approval.

## 12. Public relations and outreach

1. What is the organization and offer?
2. Who is allowed to represent it?
3. What is the pitch voice?
4. Which audiences, publications, opportunities, or keywords qualify?
5. Which claims, industries, or topics are prohibited?
6. Does every pitch require approval?
7. Where should pitches, contacts, replies, and wins be recorded?
8. Which channel should report a material opportunity?

Recommended default: background monitoring and private drafting are automatic. Sending stays approval controlled. Every pitch and reply is logged to the chosen CRM or structured record.

## 13. Websites and infrastructure

1. Which websites and services are in scope?
2. Who owns each one?
3. Where is each hosted?
4. What access exists?
5. Which health URL and success definition apply?
6. What may be repaired automatically?
7. Which actions require approval?
8. Where should failed recovery alert?
9. How are backups and rollback tested?

Recommended default: deterministic checks first, repeated confirmation before incident creation, AI only for confirmed failures, bounded recovery, failure only alerts, and live verification after repair.

## 14. Coding and specialist harnesses

1. Which repositories are in scope?
2. Which coding assistants or subscriptions are available?
3. May the agent create branches and commits?
4. May it open pull requests?
5. May it merge or deploy?
6. Which tests define completion?

Hermes can operate Codex, Claude Code, OpenCode, or another approved harness. The main operator provides context, watches the run, verifies output, and retains responsibility.

## 15. Credentials

1. Which reusable accounts must the agent operate?
2. Which are internal, external, personal, or client owned?
3. Where should secret values live?
4. Who may retrieve them?
5. Which credentials may the agent rotate?
6. Which systems require MFA or hardware approval?
7. How fast should an approved one time delivery be?

Recommended default: central encrypted vault, metadata registry, one time browser encrypted intake and reveal, exact ownership policy, no plaintext chat, and a fast vault to one time link path.

## 16. Budgets and approvals

Define exact approval rules for:

1. Messages and invitations
2. Spending and purchases
3. Campaign changes
4. Publishing
5. CRM bulk writes
6. Access and credential changes
7. Production deployments
8. Data deletion
9. New recurring routines
10. New specialist profiles

An approval must name its target, scope, limit, channel, and expiration.

## 17. Learning and extension

1. May the agent propose new skills after repeated work?
2. May it create private draft skills automatically?
3. Who approves enabling a new skill, connector, routine, or data field?
4. Which changes may be contributed back publicly after privacy review?

Recommended default: allow private proposals and test creation; require approval before new credentials, external effects, retention changes, or production activation.

For every requested capability, first define the outcome; inspect native and current tools; read current documentation; search skills and plugins; review source, license, dependencies, permissions, and data handling; compare options; configure only the selected route; test synthetic and approved real examples; and capture the verified workflow as a reusable private lane.

## Onboarding completion record

The installer should finish with a private record of:

1. Identity and communication style
2. Operating mode
3. Hosting and privacy boundary
4. Enabled channels and administrators
5. Primary notification route
6. Selected capability packs
7. Configured integrations and permissions
8. Credential gates
9. Approval matrix
10. Active routines
11. Backup and recovery policy
12. Verification evidence
13. Known limitations
14. Next decision
15. Selected correction destinations, isolation test, and fresh-session readback evidence

Do not put the completed answers in this repository.

## Managed-team selection

Select managed-team mode immediately when recurring independent lanes, sustained concurrency, distinct identities, dedicated credentials, separate schedules, strong data boundaries, or another host justify it. Do not require a single-operator trial. Keep one main operator accountable and native Kanban as the sole task lifecycle authority. For every specialist, validate a least-context versioned brief, isolated board/client/profile/workspace/credential boundary, protected-target strategy, total and verification budget, schedule inventory, and retirement contract. Deployment conformance is still required for either mode; do not create profiles, Bots, credentials, schedules, or services merely by selecting the mode.
