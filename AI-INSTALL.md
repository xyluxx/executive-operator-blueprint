# AI implementation contract

This is the operational contract for any AI implementing the **Executive Operator Blueprint for Hermes**. The installer may be Hermes, Codex, Claude Code, or another capable agent. This is an independent third-party Hermes profile distribution—not a Nous Research product, Hermes fork, new framework, or required plugin. Max is one private instance, not the public product name.

## Outcome and truth

Implement one private main executive operator that preserves unfinished work, uses only approved capabilities, and verifies consequential results. Persistent specialist Bots are optional.

Label each capability **Blueprint**, **Native**, **Bundled**, **Configured**, **Verified**, **Optional**, **Planned**, or **Blocked**. Only Verified means its end-to-end contract—including required external readback—passed. A checkout, manifest, credential, connection indicator, mocked test, or synthetic test alone is not live verification.

## Start read-only

Before any change, audit and preserve:

1. Hermes version, install method, update state, diagnostics, CLI behavior, active processes, and service manager.
2. Every profile, alias, resolved Hermes home, manifest, ownership, permissions, configuration, and local modification.
3. Memory providers and stores, retention/deletion behavior, sessions, transcripts, routing, and private project state.
4. Installed and available skills; plugins and hooks; MCP servers and transports; their versions, provenance, permissions, dependencies, and data access.
5. Kanban boards, cards, assignment and dispatch policy, subscribers, and automatic behavior.
6. Cron, loops, webhooks, workers, schedules, timezones, delivery routes, and failure state.
7. Channels, gateways, pairing/allowlists, administrators, account identities, and inbound/outbound state.
8. Credential and OAuth locations, inherited CLI/browser authentication, scopes and expiry metadata—never secret values.
9. Services, supervisors, containers, service users, network listeners, remote backends, and restart behavior.
10. Backups, retention, encryption, integrity, restore evidence, private data locations, symlinks, untracked files, and regulated or contract-restricted data.

If an area cannot be inspected, mark it Blocked. Absence of access is not proof that nothing exists. Use current official Hermes documentation and live CLI help. Do not hand-edit live config or runtime databases.

Read-only inspection is permitted on an untested Hermes build. This release's mutation boundary is semantic range `>=0.21.0,<0.22.0` **and** exact tested upstream build `b51c055a`. If either differs or the build identity is unavailable, do not run profile install/update and do not issue Verified claims until the complete release gate passes and `contracts/authority-map.yaml` is revalidated.

## Choose one path

### Fresh profile — recommended

1. Verify plain Hermes first: diagnostics, safe chat, session resume, and backup inspection.
2. Review `distribution.yaml`.
3. Create a separate `executive-operator` profile, or use the owner’s chosen private name.
4. Install only public distribution assets.
5. Verify profile identity and manifest.
6. Configure and test one primary model; add a fallback only after separate testing.
7. Use native Kanban as the sole task lifecycle authority. Import existing systems as migration inputs or expose them as derived/reference integrations only.
8. Complete onboarding privately and enable only selected outcomes.
9. Prove backup and isolated restore; prove restart persistence where applicable.

```bash
git clone --branch v1.1.0 --depth 1 https://github.com/xyluxx/executive-operator-blueprint.git
cd executive-operator-blueprint
hermes profile install . --name executive-operator --alias
```

This command does not connect external accounts or establish readiness.

The distribution intentionally omits root `mcp.json`: native profile installation succeeds without it, and an empty object configures no server. Retain `templates/mcp.example.json` only as a disabled illustrative template; never prepopulate the distribution with speculative servers.

### Existing installation — audit-first adaptation

1. Finish the complete audit.
2. Create a protected integrity-checked backup and prove restore under a separate recovery name or isolated target.
3. Diff distribution-owned paths against the current profile.
4. Classify every conflict as **preserve**, **merge**, **replace**, **disable**, or **blocked**.
5. Map existing capabilities to truth labels and keep proven native/current routes instead of duplicating them.
6. Present exact commands, file changes, permission changes, service restarts, migrations, tests, rollback, and private data preserved.
7. Obtain explicit approval naming the target profile and change set.
8. Apply one reversible layer at a time and verify before continuing.
9. Never overwrite memory, sessions, credentials, Kanban, cron, gateway, or plugin state with bundled files.
10. Preserve the original until conformance and the private-data plan pass.

Prefer a new profile plus deliberate migration whenever ownership or state is ambiguous.

## Capability-discovery loop

Run this loop for every requested outcome:

1. **Define the outcome:** user-visible result, source of truth, acceptance evidence, authority, data class, frequency, and failure behavior.
2. **Inspect native/current tools:** installed Hermes features, toolsets, providers, skills, plugins, MCP, CLIs, APIs, and approved browser routes.
3. **Read current docs:** authoritative Hermes and provider documentation plus live command help.
4. **Search skills/plugins:** inspect installed, bundled, and available options before creating one.
5. **Inspect candidates:** source, provenance, license, maintenance, dependencies, install behavior, permissions, network access, secret handling, data sent/stored, retention, telemetry, cost, limits, and revocation.
6. **Propose options:** compare native/current, approved extension, custom work only for a proven gap, and “do not enable.”
7. **Configure the selected route:** exact account, minimal scopes, approval policy, budget, fallback, notification, disable, and rollback.
8. **Test synthetic examples:** success, denial, duplicate/idempotency, wrong target, timeout/failure, and redaction.
9. **Test approved real examples:** narrow real read and explicitly approved safe write when required; read back the exact target and clean up if approved.
10. **Write the resolution record:** validate the selected source, immutable ref or version, checksum when available, license, permissions, account boundary, tests, fallback, and disable path against `templates/resolved-capability.schema.json`.
11. **Capture a reusable lane:** triggers, inputs, source authority, procedure, permissions, approvals, outputs, evidence, recovery, tests, version, and owner in a skill, adapter contract, routine, or private operating note.

If review or testing fails, disable the route and label it Blocked or Planned. Do not silently substitute a provider.

## Safety and implementation rules

- Never request secrets in normal chat or write them to the repository, memory, tasks, logs, or reports.
- Do not assume existing browser or CLI authentication is authorized for the target profile.
- Use native Hermes commands and APIs for profiles, config, memory, sessions, Kanban, cron, gateway, plugins, MCP, and backups.
- Keep one main executive operator responsible for canonical context, specialist delegation, verification, follow-up, and the next action.
- Use specialist Bots only for justified recurring volume, distinct identities, dedicated credentials, or required separation. Bot output is not automatically canonical truth.
- Maintain native Hermes Kanban as the sole canonical task-lifecycle record; treat external task systems only as migration inputs or derived/reference integrations. Prove correction, parking, waiting ownership, partial completion, evidence-based completion, supersession, fresh-session resume, deduplication, and dispatch behavior.
- Test memory write, recall, correction, deletion, backup, and restore. Test session search and resume.
- Verify one authenticated inbound and outbound message on every enabled channel.
- Define purpose, owner, source, timezone, authority, idempotency, silence, failure route, budget, and retirement for every routine.
- Stop at ambiguous targets, missing permissions or approvals, untrusted backups, unclear extension provenance/data handling, uncertain writes, private-data risk, or service impact outside scope.

## Verification and handoff

Run repository checks from a trusted checkout:

```bash
python3 scripts/validate_blueprint.py
python3 -m pytest tests -q
python3 scripts/preflight.py --json
```

Then run base and selected capability tests in `docs/13-installation-and-conformance.md`. Repository tests verify bundled repository behavior, not private providers.

Return a protected machine-readable report and concise summary with: target and path; versions; audit coverage; preserved/merged/replaced/disabled items; backup and restore evidence; main operator and optional Bots; per-capability labels; providers/accounts/scopes without secrets; synthetic and approved-real evidence; task, memory, session, channel, cron, service, and restart results; approval boundaries; local modifications; limitations; and exact blockers or next decision.

## Reusable installer prompt

> Implement the Executive Operator Blueprint for Hermes. Start with a complete read-only audit of Hermes, profiles, configuration, memory, sessions, skills, plugins, MCP, Kanban, cron, channels, credentials, local modifications, services, backups, and private data. Recommend a fresh separate profile; adapt an existing profile only through preserve/merge/replace/disable planning and verified recovery. Keep one main executive operator and make specialist Bots optional. For each outcome, inspect native/current tools, read current docs, search skills/plugins, review source/license/dependencies/permissions/data handling, propose options, configure only the approved route, test synthetic and approved real examples with readback, and capture a reusable lane. Never ask for secrets in chat. Report evidence and limitations without claiming turnkey connected accounts.
