# 16. Secure Credentials

A useful operating agent needs fast access to approved credentials without putting secret values in chat, memory, CRM notes, project files, or logs.

## Assurance tiers

- **High assurance:** separate UID/container with key and vault unreadable by Hermes plus ACL-restricted Unix IPC for approved named operations only.
- **Managed:** KMS or managed vault using workload identity, independent policy, audit, and revocation.
- **Limited local:** same-account encrypted files or environment injection. This is useful exposure reduction but prohibited for high-impact credentials because the running model/agent process can access it.

The model-facing interface returns opaque operation or direct-delivery metadata only. It cannot return plaintext or a retrievable high-impact secret link. Broker failure never falls back to chat, environment output, or a weaker vault. The bundled code is a test-local reference and does not configure a separate UID, container, service, socket, KMS, or account.

## Three separate records

### Integration metadata

Safe information such as provider, capability, account, scopes, status, and credential reference.

### Reusable secret vault

Encrypted values for accounts the agent is authorized to operate.

### One time credential exchange

Short lived browser encrypted intake or one time delivery that destroys the drop after consumption.

Do not merge these layers.

## Bundled toolkit

`tools/secure-credentials/` provides a generic reference implementation for:

1. Browser encrypted sender links
2. Preview safe recipient pages
3. Explicit one time human reveal
4. Agent consumption to an exact protected file
5. Encrypted reusable credential vault
6. Safe metadata listing
7. Fast vault to one time delivery link
8. Expiration and cleanup

The toolkit is optional. Another secret manager may replace the vault if the complete contract passes.

Install it from a native profile with `python3 tools/secure-credentials/bootstrap.py`; profile installation itself neither installs dependencies nor starts a service. Bearer links authorize one drop operation. Local vault commands are operator access authenticated by the owner-only POSIX account, vault, and key—not by caller-supplied principal strings.

## Fast delivery goal

A request for a known approved credential should not trigger a broad system audit every time.

The direct path is:

1. Resolve exact service and recipient.
2. Read safe vault metadata.
3. Confirm ownership and delivery authority.
4. Verify the stored value through a safe local or provider check when required.
5. Create a submitted one time link directly from the vault.
6. Verify submitted state without opening the link.
7. Return only the link and expiration.

Slow research or reset happens only when the record is missing, ambiguous, unauthorized, or invalid.

## Secure intake goal

A provider secret intended for the agent should flow:

1. Create a sender link and exact protected claim file.
2. Sender encrypts in the browser before upload.
3. Agent consumes once into the named owner only destination.
4. Agent validates the credential with a narrow live request.
5. Drop becomes unavailable.
6. Integration metadata stores only the protected pointer and verification evidence.

## Ownership and reset

Every credential needs:

1. Owner
2. Account identity
3. Internal, personal, external, or client scope
4. Authorized consumers
5. Reset permission
6. MFA requirement
7. Last verification
8. Expiration or rotation policy

Technical access does not grant authority to reset a client or third party account.

## Delivery adapters

The one time link can be delivered through any approved channel: Telegram, Slack, email, SMS, Teams, another messenger, or a private local handoff.

The delivery adapter receives the link, not the secret. It disables previews when possible, records provider delivery, and removes the outbox record after confirmation.

## Mandatory tests

1. Plaintext never appears in vault or drop database bytes.
2. Safe listing never returns ciphertext or plaintext.
3. Sender submits once.
4. Recipient reveals once.
5. GET and preview do not consume.
6. Concurrent requests have one winner.
7. Agent writes to one exact protected path.
8. A second agent consume fails.
9. Expired drops are deleted.
10. Logs contain no fixture secret or URL token.
11. Fast vault delivery creates a submitted one time link.
12. Wrong owner and reset policy fail closed.
13. Service and key recover after an approved restart.

## Limitations

One time links are bearer capabilities. Protect their delivery route and expiration. The bundled service is private/loopback-only, has a single-process rate limiter, and refuses readiness for public exposure; it is not a public authentication service. A malicious host can still inspect process memory. Stronger threat models may require gateway IAM, distributed abuse controls, hardware backed keys, managed HSMs, enterprise secret managers, audited identity, and formal incident response.
