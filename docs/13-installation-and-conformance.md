# 13. Installation and Conformance

This repository is an implementation-grade blueprint and independent third-party Hermes profile distribution. It is not a Nous Research first-party product, a fork, a new framework, or a mandatory plugin.

## Normative authority and compatibility

`contracts/authority-map.yaml`, validated by `templates/authority-map.schema.json`, identifies one normative home for each cross-cutting concept. Explanatory documents may link to those homes but must not silently redefine their enumerations or guarantees.

This release supports read-only inspection on any build. Mutating profile installation, profile update, and Verified claims require both Hermes `>=0.21.0,<0.22.0` and exact tested upstream build `b51c055a`. A missing or different build identity is a compatibility mismatch, even when the semantic version matches. Revalidation requires the complete release gate: repository validator and tests, static/security/dependency checks, native clean install, update, backup/restore/rollback, and applicable capability conformance. Update the compatibility contract only after all pass.

The root `mcp.json` is deliberately absent. Disposable native profile installs against build `b51c055a` succeeded with `{}` present and with the file absent; therefore it was proven redundant and removed from `distribution_owned`. `templates/mcp.example.json` is a disabled illustrative template—not a configured MCP server. Populate only a privately reviewed server after selecting it; never ship speculative servers.

## Two readers

### Human owner

Start with `README.md`, choose an installation path in `INSTALL.md`, and answer the conversational questions in `ONBOARDING.md`.

### AI installer

Read `AI-INSTALL.md` first. It defines the complete read-only audit, fresh and existing-install paths, truth labels, privacy boundary, capability-discovery loop, approval gates, tests, and handoff. The installer may be Hermes, Codex, Claude Code, or another capable agent.

## Fresh-profile base installation

1. Install Hermes from its current official documentation.
2. Run `hermes doctor` and `hermes config check`.
3. Review the manifest and install this distribution into a separate profile.
4. Select a model provider and one tested fallback.
5. Complete onboarding.
6. Enable only the selected capability packs.
7. Receive credentials through a protected channel.
8. Test every enabled connector.
9. Configure persistence and backups.
10. Complete conformance before describing any selected capability as ready.

## Existing-install adaptation

Before changing an existing Hermes installation, audit version, install method, configuration, every profile, memory, sessions, skills, plugins, MCP, Kanban, cron, channels, credentials, local modifications, services, backups, and private data. Create an integrity-checked backup and prove isolated restore. Diff every distribution-owned path and classify each conflict as preserve, merge, replace, disable, or blocked. Obtain approval for the exact target and change set, then apply one reversible layer at a time. Never overwrite runtime state with bundled files.

## Capability discovery gate

For each outcome: inspect native and current tools; read current official docs; search skills and plugins; review candidate source, license, dependencies, permissions, and data handling; propose viable routes; configure only the selected route; test synthetic cases; test approved real examples with readback; and capture the verified procedure as a reusable lane. A route that fails remains Planned or Blocked.

## Truth labels

Every setup report uses:

1. Native
2. Bundled
3. Configured
4. Verified
5. Optional
6. Planned
7. Blueprint
8. Blocked

A native feature can still be unconfigured. A bundled skill can still be disabled. A credential can exist while the connector is broken. A passing mocked test is not a live contract test.

## Base conformance

A base installation must prove:

1. Correct profile identity in a fresh session
2. Main and fallback model routes
3. Memory write, recall, correction, and removal
4. Session search
5. Working stack and save point behavior
6. Task return after a fresh session
7. Correct owner, waiting, hold, and completion states
8. File creation as a real file
9. Approval blocking for one consequential action
10. No secret values in logs, chat, or public files
11. Backup creation and isolated restore
12. Service persistence after restart when always on hosting is selected

## Capability conformance

Each enabled capability adds its own live contract tests.

Examples:

1. Email: known thread read, unsent draft, approved synthetic send, sent readback
2. Calendar: timezone safe read and approved synthetic event readback
3. Meeting notes: real source acquisition and cited action extraction
4. CRM: metadata read, record identity, safe synthetic create, idempotent readback
5. Marketing: correct account, time range, metric definition, and source reproduction
6. Secure credentials: one submit, one reveal, exact protected agent consume, encrypted vault bytes
7. Website reliability: healthy silence, confirmed incident, one queued worker, verified recovery
8. Coding harness: authenticated live prompt, isolated branch, tests, and artifact verification
9. Channel: one authenticated inbound and outbound message
10. Remote Desktop: HTTP and WebSocket connection test
11. Artifacts: real CSV, XLSX, DOCX, and PDF creation, format inspection and
    content reopen; local `MEDIA:` preparation; selected-storage exact identity,
    idempotent upload, object ID, checksum/version/permission/retention readback,
    unknown-effect reconciliation, expiry, revocation, cleanup, and disable

## Explicit public release audit

Normal validation and repository-only preflight are offline and deterministic. Before publication, run the separate read-only public release audit explicitly:

```bash
python3 scripts/audit_public_release.py
python3 scripts/validate_blueprint.py --release --public-release-audit
python3 scripts/preflight.py --json --repository-only --public-release-audit
```

`contracts/public-release-policy.yaml` is the exact public identity, ref, release, contributor, collaborator, and Git identity allowlist for the single public `v1.1.0` release. The audit distinguishes public contributor attribution from authenticated collaborators. Missing permission for collaborators, invitations, teams, or deploy keys is `unverified`, never a pass. To avoid an impossible self-referential commit hash, the policy pins a SHA-256 over every tracked path, canonical Git mode, and blob except the policy file itself; the audit separately requires the tag, default branch, one audited commit, allowed Git identities, release archive, and published checksum asset to agree. Store dated audit output privately; never commit tokens, authentication output, or machine paths.

## Failure policy

If a test fails:

1. Keep the capability Configured, not Verified.
2. Name the failing layer.
3. Preserve evidence without secrets.
4. Disable external actions when the failure affects authority or idempotency.
5. Repair and rerun the exact test.
6. Do not substitute another provider silently.

## Distribution update recovery

Before an existing profile is updated, the reference wrapper creates a fresh owner-only staging directory inside protected backup storage and gives the native exporter a unique absent destination inside it. After export, it verifies a regular file with the expected owner and one link, enforces POSIX mode `0600`, validates the archive, and flushes the file and directories. Native export omits `auth/` and `.env`, but the remaining profile state is still private and must be handled as sensitive backup data. The wrapper then runs the noninteractive native update and verifies every distribution-owned path.

Run `inspect` before planning an update. It performs discovery without reading private values or changing the profile, distinguishes fresh from existing installs, and reports the recorded source and private state classes to preserve. Prefer a source pinned to the reviewed commit SHA. A local checkout path or moving branch is not immutable even when its current commit is recorded in a report.

If verification fails, further use is blocked and the export is preserved. The wrapper does not overwrite the live profile automatically. Import the export under a separate recovery name, verify it, then approve a deliberate cutover or repair.

Creation rollback is deliberately narrower than decommissioning an active profile. The wrapper exposes no general uninstall command. Automatic deletion is allowed only for a newly created, provably pristine profile containing unchanged copies of distribution-owned source paths and the exact matching install marker. Any user or runtime path, symlink, missing manifest, or changed marker blocks deletion. After onboarding or runtime use, first disable schedules, channels, connectors, credentials, and external routines; create and verify the required backup; inspect retained private state; then use a separately approved native profile deletion procedure.

## Installation report

The final report must list:

1. Profile and version
2. Host pattern
3. Operating mode
4. Selected capability packs
5. Native capabilities used
6. Configured connectors
7. Verified connectors
8. Remaining credential or permission gates
9. Active routines
10. Notification routes
11. Approval policy
12. Backup and restore evidence
13. Known limitations

This report contains references and status, never secret values.
