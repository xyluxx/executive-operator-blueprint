# 06. Guardrails, Security, and Recovery

Guardrails have several layers. Do not describe a prompt rule as an enforcement control.

## Protected action boundary reference

The optional operator-control plugin is disabled by default. When enabled, its production-registered `pre_tool_call` hook applies the tested strict allowlist, denying generic terminal/browser routes and unknown capabilities before dispatch. It remains defense in depth because callback exceptions can fail open. Authoritative approval is rechecked inside each supported write adapter immediately before its external effect. Missing, expired, cancelled, replayed, wrong-identity, wrong-account, wrong-target, changed-payload, wrong-policy, unsupported-route, or broker-down requests fail closed. Intent is recorded before dispatch; provider identity and exact-target readback are required; and possible-success timeouts remain `unknown` until reconciled.

Generic terminal writes and generic browser writes remain unsupported even though the registered hook denies them while enabled, because direct provider access and callback failure sit outside that defense-in-depth surface. Keep them interactive/manual or Blocked. Hermes 0.21 Kanban callbacks are observer-only and cannot veto direct dashboard or CLI transitions; a direct unaccepted `done` is recorded as an override/exception, while every supported downstream write adapter still requires signed acceptance. Native auto-release alone therefore cannot guarantee acceptance-sensitive dependencies.

Human issuance is separate from the model surface. Run `scripts/operator_control_admin.py` only from an authenticated administrator session with an owner-owned mode-0600 token file. It issues signed policy, approval, evidence, and acceptance records; the plugin exposes execution only and cannot issue authority.

## Identity and channel access

1. Configure pairing or explicit allowed identities.
2. Separate administrator and regular user permissions where supported.
3. Scope group and direct message behavior independently.
4. Verify unauthorized access fails.
5. Keep public gateway or Desktop backends behind appropriate authentication and network controls.

Open access is an explicit choice, not a safe default for an agent with files, credentials, or terminal tools.

## Tool and command safety

Hermes command approvals can protect dangerous terminal actions. Toolsets, plugin capabilities, MCP trust, terminal backends, containers, operating system users, and network boundaries provide additional controls.

Business approval is separate. Sending a message, spending money, changing access, publishing, modifying campaigns, creating invitations, deploying production, bulk updating CRM, or deleting data requires the configured policy even when the underlying command is technically allowed.

Enforce consequential policies through an adapter, plugin, or workflow gate when strong guarantees are required.

## Credentials

Use:

1. Hermes provider and environment configuration
2. OAuth and credential pools
3. Operating system keychains
4. External secret managers
5. The bundled Secure Credentials toolkit as a reference option

The integration registry stores credential references and status, not values.

Redaction reduces accidental exposure. It is not proof that a secret can never reach chat, logs, subprocesses, browser screenshots, provider payloads, or crash artifacts. Test the complete route.

## Approval record

An approval should name:

1. Actor
2. Target
3. Material payload or action
4. Allowed operation
5. Limit
6. Channel
7. Time and expiration
8. Idempotency key when applicable
9. Result and readback

Later corrections and withdrawal win.

## Uncertain external results

When a write times out or the process stops after dispatch:

1. Mark the outcome uncertain.
2. Block blind retry.
3. Read the target system.
4. Reconcile provider IDs and current state.
5. Retry only when the first action did not succeed and the request remains authorized.

## Isolation

A profile separates Hermes managed state. Stronger boundaries may require:

1. Dedicated operating system user
2. Restricted working directory
3. Container or sandbox
4. Separate browser profile
5. Separate external CLI credentials
6. Dedicated host
7. Network isolation
8. Separate backup and encryption keys

## Backups and recovery

Distinguish:

1. Full Hermes backup and import
2. Credential-free profile export and import
3. Filesystem checkpoints
4. Project Git history
5. Domain database backups
6. Provider-side export

Never back up short lived credential drops. A backup is not trusted until an isolated restore succeeds.

## Kill switches

A deployment should document exact paths to:

1. Stop the gateway
2. Stop the remote Desktop backend
3. Pause cron and background workers
4. Disable one plugin
5. Disable one MCP server
6. Disable one provider or channel
7. Pause a Bot or managed team
8. Revoke a credential
9. Restore the previous release
10. Preserve evidence for investigation

Use supported Hermes commands and the selected service manager. Do not kill unrelated system user managers.

## Recovery order

1. Preserve current evidence.
2. Run `hermes doctor` and configuration checks.
3. Inspect the exact profile, session, provider, plugin, MCP, gateway, or job.
4. Disable the narrow failing extension.
5. Use safe mode or a clean profile when needed.
6. Restore from a verified backup only when targeted repair is insufficient.
7. Run a fresh session and one safe real workflow.
8. Re-enable capabilities one at a time.

## Verification

1. Unauthorized channel user fails.
2. Dangerous command approval works.
3. Business action without approval is blocked by the selected enforcement layer.
4. Secret fixture stays out of logs and public output.
5. Uncertain external write is not duplicated.
6. Plugin and MCP disable paths work.
7. Gateway stop and restart work.
8. Full backup restores in isolation.
9. Profile export contains no credentials.
10. Revoked credentials cannot be used.

## Cancellation and concurrency boundary

Cancellation is a protected pre-dispatch and pre-effect gate, not an observer notification. It revokes unused action authority and sends every already-issued `unknown` effect to authenticated provider reconciliation; blind retry is denied. There is no claim of an atomic transaction across Hermes and a provider. Direct dashboard/CLI/database completion and native parent auto-promotion bypass plugin pre-tool hooks in Hermes 0.21.0, so they are observer-only limitations: protected downstream adapters still demand signed acceptance, and unsupported routes remain manual or `blocked`.
