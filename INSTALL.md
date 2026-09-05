# Install the Executive Operator Blueprint for Hermes

This guide covers two paths: a recommended fresh profile and an audit-first adaptation of an existing Hermes installation. The repository is an independent third-party profile distribution. It does not install provider accounts, private data, credentials, or verified business integrations.

If an AI will perform the work, give it [AI-INSTALL.md](AI-INSTALL.md) and the repository. The installer may be Hermes, Codex, Claude Code, or another capable agent.

## Before choosing a path

Use the current [official Hermes installation documentation](https://hermes-agent.nousresearch.com/docs/getting-started/installation). Commands and supported versions can change; verify against current docs and live help rather than treating this file as a replacement for Hermes documentation.

Choose a host according to the real data and availability needs:

- **Local Desktop or CLI:** simplest private start while the computer is available.
- **Always-on host:** appropriate when channels, schedules, monitoring, or remote access must continue while personal devices are offline.
- **Reviewed sensitive or regulated environment:** required when contracts, residency, retention, identity, or compliance controls demand it.

A host, Hermes installation, or this blueprint does not itself establish compliance.

## Recommended path: fresh profile

A separate profile gives the blueprint a clear boundary and leaves other Hermes profiles intact.

### 1. Verify plain Hermes

Install Hermes through its current official route, then run the diagnostics supported by that version:

```bash
hermes --version
hermes doctor
hermes config check
```

Before adding the blueprint:

1. Start a plain safe chat and receive a normal response.
2. Resume that session.
3. Create a backup using the current native command.
4. Inspect the backup result and understand what it includes and omits.
5. Resolve the actual Hermes home and current profile.

Fix unexplained blocking diagnostics first.

### 2. Review and install the distribution

Review `distribution.yaml`, including the name, version, required Hermes version, and distribution-owned paths. Then install into a separate profile:

```bash
git clone --branch v1.1.0 --depth 1 https://github.com/xyluxx/executive-operator-blueprint.git
cd executive-operator-blueprint
hermes profile install . --name executive-operator --alias
hermes profile info executive-operator
```

`executive-operator` is a recommended profile name, not a required private identity. The owner may choose another name. Max is one private instance and is not the public product name.

Install the reviewed release tag, then confirm the resolved commit and distribution-tree SHA-256 in the installation report against the release record. The wrapper refuses `apply` from an uncommitted, dirty, remote-less, remotely unadvertised, generated-cache-bearing, ignored-untracked, file-mode-drifted, or incomplete source tree. The exact commit must be advertised by the recorded remote, and every installed path must match that Git tree. POSIX checkouts also verify working-tree executable bits; Windows checkouts bind the digest to the canonical Git modes because Windows does not preserve POSIX executable bits. This keeps the recommended detached checkout reproducible. Do not install or update from a moving branch when reproducibility matters. Native Hermes preserves only `hermes_requires: ">=0.21.0"` from the manifest, so the repository preflight and installation report enforce and disclose the narrower tested range `>=0.21.0,<0.22.0`.

The native installer copies public distribution assets. It does not supply API keys, OAuth grants, provider accounts, private memory, sessions, schedules, or connected business systems.

### 3. Select and test model routes

```bash
hermes -p executive-operator model
```

Choose one primary route based on reliability, tool use, privacy, latency, cost, and workload. Test it with a harmless real response. Add a fallback only after testing it independently; a configured fallback is not a verified fallback.

### 4. Initialize the canonical task record

For every profile, native Hermes Kanban is the sole task-lifecycle authority; existing external task systems may be imported as migration inputs or retained only as derived/reference integrations:

```bash
hermes -p executive-operator kanban init
hermes -p executive-operator kanban boards list
hermes -p executive-operator kanban stats
```

Confirm that unassigned cards remain manual, assignment dispatch follows the approved policy, automatic decomposition is off unless deliberately enabled, and parked work is represented as `todo` with a checkpoint.

### 5. Complete onboarding privately

```bash
hermes -p executive-operator chat
```

Say:

> Read ONBOARDING.md and guide me through the setup. Recommend low-risk defaults, ask only questions that change implementation, keep all answers private, and never request secrets in chat. Keep one main executive operator by default. Enable no external capability until its permissions, approval policy, and tests are agreed.

Onboarding establishes private identity, work style, data boundaries, task policy, memory, channels, notifications, capability outcomes, credentials, approvals, routines, backups, and optional specialist Bots.

### 6. Discover and add capabilities one outcome at a time

For each desired outcome:

1. Define acceptance evidence and source of truth.
2. Inspect native Hermes and current installed tools.
3. Read current official documentation.
4. Search installed, bundled, and available skills and plugins.
5. Inspect candidate source, license, dependencies, permissions, network behavior, secret handling, and data retention.
6. Compare viable native/current, extension, custom-gap, and do-not-enable routes.
7. Configure only the approved route with minimal scope.
8. Test synthetic success and failure cases.
9. Test the narrowest owner-approved real example and read back the result.
10. Capture the verified process as a reusable private lane.

See [CAPABILITIES.md](CAPABILITIES.md). Do not activate every pack merely because it is listed.

### 7. Add credentials through a protected route

Do not paste credentials into normal chat. Use an approved secret manager or protected exchange. The bundled Secure Credentials tool is an optional reference implementation and must itself be securely deployed and tested before use.

Confirm account identity, scopes, ownership, expiry, rotation, revocation, and data boundary. A stored credential remains Configured—not Verified—until its capability test passes.

### 8. Configure selected channels and routines

Use current native Hermes setup commands. For every channel, configure pairing or allowlists and verify one authenticated inbound and outbound message. For each recurring routine, define owner, source, schedule, timezone, permissions, approvals, idempotency, budget, quiet-success behavior, failure route, and retirement.

### 9. Verify and hand off

From a trusted repository checkout:

```bash
python3 scripts/validate_blueprint.py
python3 -m pytest tests -q
python3 scripts/preflight.py --json
```

Preflight performs read-only inspection and does not create or modify the install-state directory. If it reports that an existing install-state directory is not owner-only, first verify the resolved Hermes home and ownership, then change that exact directory to mode `0700` under the owner’s approved change plan. Do not apply a blanket permission change.

Then run the deployment-specific tests in [docs/13-installation-and-conformance.md](docs/13-installation-and-conformance.md). Prove an isolated restore and, for always-on installations, restart persistence. Report each capability as Blueprint, Native, Bundled, Configured, Verified, Optional, Planned, or Blocked.

## Audit-first path: existing Hermes installation

### Owner-mutable configuration during updates

Hermes treats `config.yaml` as owner-mutable and preserved by default so local overrides survive an update. The approved plan discloses permission hardening to `0600`. After the verified backup, the wrapper accepts only an owner-owned, safe regular file with one link, hardens its mode through an opened descriptor when needed, and compares pre-update and post-update content exactly; other distribution-owned files must refresh to the distribution versions and hashes.

A standalone verify does not require owner-modified `config.yaml` to match the distribution SHA. It requires safe regular file metadata, parseable YAML, and a passing native config check; it still verifies every other distribution-owned file exactly. Symlinks, hardlinks, wrong ownership, unsafe modes, malformed YAML, or a failed native check block verification.

Do not use the fresh install commands against an existing target profile until the audit and change plan are approved.

### 1. Perform a read-only audit

Inventory without exposing secret values:

- Hermes version, install method, update state, live CLI behavior, diagnostics, processes, and service manager;
- active and available profiles, aliases, resolved Hermes homes, manifests, permissions, owners, and configuration;
- identity and context files plus all local modifications, untracked files, symlinks, and generated state;
- memory providers, stores, policies, sessions, transcripts, active/background sessions, and private project data;
- skills, plugins, hooks, MCP servers, provenance, versions, dependencies, permissions, transports, and data handling;
- Kanban boards, cards, subscribers, assignment/dispatch policy, and automatic decomposition;
- cron, loops, webhooks, workers, schedules, timezones, delivery routes, last/next runs, and failure state;
- channels, gateways, pairing/allowlists, administrators, account identities, and round-trip status;
- credential and OAuth locations, external CLI/browser authentication, scope/expiry metadata, and owners;
- services, supervisors, containers, service users, ports, remote backends, and restart behavior;
- backups, encryption, retention, integrity, restore evidence, omissions, private-data locations, and regulated or contract restrictions.

Mark inaccessible areas Blocked. Do not infer “not present” from missing permission.

### 2. Create and prove recovery

Use current native export or backup commands. Store output in an owner-only protected destination and verify its integrity, ownership, and expected contents. Because exports may contain private profile state even when auth files are excluded, handle them as sensitive.

Import or restore under a separate recovery name or isolated target. Verify identity, configuration, task state, memory, and required assets. Do not delete or overwrite the original.

### 3. Produce a conflict-aware adaptation plan

Diff current files and state against the distribution. Classify each item:

- **Preserve:** private state, local behavior, or a proven current capability remains unchanged.
- **Merge:** compatible blueprint rules are incorporated into the existing source of truth.
- **Replace:** a named distribution-owned file is replaced with explicit approval.
- **Disable:** a conflicting capability is deliberately disabled with rollback.
- **Blocked:** ownership, effect, or recovery is uncertain.

The plan must list exact commands, paths, migrations, permission changes, service restarts, tests, private data preserved, and rollback. Existing working providers should not be replaced merely because a different example appears in this repository.

### 4. Approve and apply narrowly

Obtain approval that names the profile and change set. Apply one reversible layer at a time and verify it before proceeding. Never copy bundled files over live memory, session, auth, credential, Kanban, cron, gateway, or plugin databases.

Prefer a separate profile plus deliberate migration if identity, state, or ownership is ambiguous.

### 5. Re-run discovery and conformance

Map existing capabilities to the truth labels, then run the same capability-discovery loop used for a fresh profile. Test synthetic cases before approved real actions. Complete all base and selected capability conformance, isolated restore, and restart checks before cutover.

## Optional specialist Bots

The default is one main executive operator with the complete operating picture. Temporary specialists may handle bounded work. Add persistent Bots only for recurring high volume, separate identities, dedicated credentials, independent schedules, or enforced context separation. The main operator remains responsible for canonical state, reconciliation, verification, and follow-up.

## Repository checkout for validation and reference tools

The remote profile installer does not create a general working checkout. Clone separately if you need repository scripts or optional tools:

```bash
git clone --branch v1.1.0 --depth 1 https://github.com/xyluxx/executive-operator-blueprint.git
cd executive-operator-blueprint
uv venv .venv
source .venv/bin/activate
uv pip install --require-hashes -r requirements-dev.lock
```

On Windows PowerShell, activate with `.\.venv\Scripts\Activate.ps1`.

## Updating or removing

Treat an update as an existing-install adaptation: audit, protected backup, isolated restore proof, conflict diff, approval, apply, and conformance. Do not assume distribution files are unchanged or that private state is covered by an export.

Automatic rollback is safe only for a newly created, provably pristine profile. Once onboarding, memory, sessions, credentials, logs, runtime databases, schedules, or local modifications exist, use a reviewed recovery or native deletion procedure with explicit destructive approval.

## What “ready” means

A profile is ready only for the capabilities whose required tests passed. Optional unconfigured capabilities may remain Optional. Failed or unavailable work remains Blocked or Planned. A concise handoff must include versions, audit coverage, selected path, preserved and changed items, backup/restore evidence, capability labels, account and scope metadata without secrets, synthetic and approved-real evidence, approval boundaries, active services and routines, local modifications, limitations, and next decision.

For machine-readable evidence, `scripts/install_blueprint.py inspect` reports whether the target is fresh or existing, the recorded immutable distribution source and version, and the names—not contents—of private state classes that an update must preserve. Review that audit and a protected export before approving `update-profile`; after approval, `apply --yes` initializes and reads back native Kanban while leaving external integrations disabled.
