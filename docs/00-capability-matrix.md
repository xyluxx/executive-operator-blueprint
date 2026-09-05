# 00. Capability Matrix

Reviewed against Hermes Agent v0.21.0 documentation. Recheck the official documentation before installing against a newer release.

| Capability | Layer | Native home or repository asset | Prerequisite | Verification | Security boundary | Official reference |
| --- | --- | --- | --- | --- | --- | --- |
| CLI and TUI | Native | `hermes`, `hermes --tui` | Hermes install and model | Start a safe chat | Local user and enabled tools | [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation) |
| Desktop | Native | `hermes desktop` or Desktop installer | Supported OS | Open a session and file preview | Desktop user and active profile | [Desktop](https://hermes-agent.nousresearch.com/docs/user-guide/desktop) |
| Remote Desktop | Optional | Settings → Gateways and `hermes serve` | Reachable protected backend | HTTP and WebSocket test, reconnect | Backend auth, network, profile | [Desktop remote backend](https://hermes-agent.nousresearch.com/docs/user-guide/desktop#connecting-to-a-remote-backend) |
| Messaging channels | Native | `hermes gateway setup` | Platform account or bridge | One authenticated inbound and outbound message | Pairing, allowlist, admin scope | [Messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) |
| Profiles | Native | `hermes profile` | Hermes install | Create, show, use, export, import | Hermes managed profile state | [Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles) |
| Profile distribution | Bundled | `distribution.yaml` and this repository | Git and Hermes | Install into disposable profile | Installer excludes runtime secrets and state | [Profile distributions](https://hermes-agent.nousresearch.com/docs/user-guide/profile-distributions) |
| Sessions | Native | `hermes sessions`, `/sessions`, `/resume` | Active profile | Find and resume a known session | Chat origin and profile | [Messaging sessions](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/#session-management) |
| Working stack | Bundled | Hermes Kanban and `continuity`; Operator State is a migration reference | Fresh profile and initialized default board, or audited existing canonical system | Create an unassigned manual task, prove no dispatch, then resume the same task without a duplicate | Board, workstream, and profile policy | [Tasks guide](03-tasks-and-scheduling.md) |
| Memory | Native | Memory files and provider plugin | Retention and provider choice | Add, recall, correct, remove, restore | Profile and provider | [Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) |
| Skills | Bundled | `hermes skills`, `skills/` | Skill source and dependencies | Inspect, install, load, run, disable | Profile and skill capabilities | [Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) |
| Plugins and hooks | Native | `hermes plugins` | Trusted plugin | Doctor, enable, exercise, disable | Declared and granted capabilities | [Plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins) |
| MCP | Optional | `hermes mcp` | Server, transport, auth | Discover tools and run one safe call | Server trust, scopes, transport | [MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) |
| Cron and routines | Native | `hermes cron` | Running scheduler or gateway | Next run, execution, delivery, failure | Job profile, tools, delivery target | [Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) |
| Temporary delegation | Native | `delegate_task` | Main agent and available model | Bounded child result and parent verification | Supplied context and tools | [Delegation guide](04-delegation.md) |
| Durable work | Native | Cron, Kanban, supervised process | Persistence and state | Restart and resume test | Worker profile and host | [Background systems](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) |
| Bot Mode | Native | Profiles, Bot Chats, routines, mentions, groups | Desktop and profiles | Create disposable Bot, message, routine, remove | Profile state; filesystem needs separate enforcement | [Bot Mode](https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode) |
| Coding harnesses | Optional | Codex, Claude Code, OpenCode, ACP | Provider auth and repository | Live headless prompt, branch, tests | Harness sandbox and repository scope | [Codex runtime](https://hermes-agent.nousresearch.com/docs/user-guide/features/codex-app-server-runtime) |
| Secure credential exchange | Bundled | `tools/secure-credentials` | Python dependencies, TLS, protected host | One submit, reveal, agent consume, expiration | Token capability, vault key, host | [Secure credentials](16-secure-credentials.md) |
| Website watchdog | Bundled | `tools/website-watchdog` | Private site registry and scheduler | Healthy silence, confirmed incident, recovery | Named targets and approved repairs | [Autopilot](17-autopilot-and-recovery.md) |
| CRM | Optional | `crm-operator` and adapter | CRM account and object map | Metadata, read, approved write, readback | Workspace, object, field, action scope | [Provider adapters](15-provider-adapters.md) |
| Meetings and notes | Optional | Google Meet plugin or note provider adapter | Meeting account, consent, transcript source | Authorized test meeting or known recording | Meeting, participant, retention policy | [Capabilities](../CAPABILITIES.md#meetings-and-notes-pack) |
| Marketing and SEO | Optional | `growth-intelligence` | Approved accounts and data providers | Account, date, metric, source reproduction | Business and account boundary | [Capabilities](../CAPABILITIES.md#marketing-analytics-and-seo-pack) |
| Public relations | Optional | `pr-operator` | Completed PR brief, sources, CRM, sending policy | Qualification, draft, blocked send, CRM record | Representative, audience, sender, approval | [Capabilities](../CAPABILITIES.md#public-relations-and-outreach-pack) |
| Backup and restore | Native | `hermes backup`, `hermes import`, profile export | Protected destination | Isolated restore and safe workflow | Backup key, retention, owner | [Lifecycle](12-operator-lifecycle-and-recovery.md) |

## Classification rule

The matrix says where a capability belongs. It does not prove that a private installation enabled or verified it.
