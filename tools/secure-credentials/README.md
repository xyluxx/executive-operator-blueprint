# Secure Credentials Toolkit

A provider neutral reference implementation for browser encrypted one time intake, one time reveal, agent consumption to an exact protected file, an encrypted reusable vault, and fast vault to link delivery.

## What it solves

1. A person can give the agent a secret without pasting it into chat.
2. An authorized person can receive a reusable stored credential through a one time link.
3. The agent can consume a submitted secret directly into an exact owner only file.
4. Safe inventory output contains metadata but no plaintext or ciphertext.
5. The sender’s browser encrypts before upload.

## Security model

1. A unique RSA OAEP key pair is created per drop.
2. The browser creates an AES 256 GCM key and encrypts the secret.
3. The AES key is wrapped by the drop’s public key.
4. The server stores ciphertext, IV, wrapped key, and an encrypted private key.
5. URL tokens are stored only as SHA 256 hashes.
6. Human retrieval requires an explicit POST so link previews cannot consume.
7. Agent consumption claims one database row, writes through a temporary owner only file, calls `fsync`, replaces the exact destination, and then finalizes consumption. Recovery verifies the destination checksum after an interrupted finalization.
8. Concurrent consumption has one winner.
9. Unused drops expire.
10. The one time database should not be backed up.

This reference tool reduces exposure but does not replace a full security review, host hardening, TLS, access control, audit policy, or a managed secret system when those are required.

## Install from a native profile

The utility is optional; installing the profile does not install or start a runtime. From the installed profile root:

```bash
python3 tools/secure-credentials/bootstrap.py
```

The command prints the absolute executable path. It creates a private venv under the active `HERMES_HOME`, installs the hash-locked dependencies, then installs the utility package. It does not depend on the source repository, `uv`, or the current directory.

## Configure

Set these in the private profile environment, not in the repository:

```text
SECURE_CREDENTIALS_BASE_URL=https://credentials.example.com
SECURE_CREDENTIALS_PREFIX=
SECURE_CREDENTIALS_DROP_DB=/protected/path/credential-drops.db
SECURE_CREDENTIALS_VAULT=/protected/path/credential-vault.db
SECURE_CREDENTIALS_KEY_FILE=/protected/path/secure-credentials.key
SECURE_CREDENTIALS_OUTBOX=/protected/path/credential-outbox
SECURE_CREDENTIALS_EXPOSURE=private
SECURE_CREDENTIALS_RATE_LIMIT=30
```

The key is generated automatically if missing and is never printed. Prefer platform secret injection through `SECURE_CREDENTIALS_MASTER_KEY`; otherwise keep the key outside database backups. POSIX deployments reject unsafe, symlinked, or hard-linked key files. Windows needs reviewed secret management or tested ACL enforcement.

## Start the browser service

Run through the `terminal` tool or a supervised service:

```bash
~/.hermes/runtime/secure-credentials-venv/bin/python -m uvicorn secure_credentials.app:app --host 127.0.0.1 --port 8787 --workers 1
```

Keep it on loopback behind HTTPS and a private VPN/tunnel or authenticated gateway. `SECURE_CREDENTIALS_EXPOSURE=private` is mandatory: this is not an unauthenticated public service. Bearer routes have a single-process per-client limit; use one worker. The gateway must add distributed abuse controls and suppress URL-token logs. `GET /livez` is process liveness; `GET /readyz` checks exposure, HTTPS configuration, rate limit, key, outbox, and SQLite access.

## Receive a secret for the agent

Create a sender link and protected claim file:

```bash
~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials create --claim-file /protected/path/request.claim.json
```

The command prints only the sender URL. Give it to the sender.

After submission, consume directly to the exact provider file:

```bash
~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials consume --claim-file /protected/path/request.claim.json --output /protected/path/provider.env
```

The command prints only success metadata. Validate the credential with one minimal provider request without printing it.

If the protected delivery outbox failed before it could save the human recipient link, recover that link through the exact claim file while the encrypted recipient capability still exists:

```bash
~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials recover-link --claim-file /protected/path/request.claim.json
```

Normal successful outbox delivery clears the server-side recoverable recipient capability.

## Store a reusable credential

Pipe the value through standard input so it does not appear in shell history:

```bash
printf '%s' "$SECRET_VALUE" | ~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials vault-put --service example --url https://service.example --login owner@example.com --owner-scope internal --principal owner --recipient owner
```

For interactive use, an installer should read from a protected prompt or file rather than export a long lived shell variable.

List safe metadata:

```bash
~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials vault-list
```

## Create a fast one time delivery link

```bash
~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials vault-link example --recipient owner --ttl 3600
```

The command decrypts only in process memory, creates a submitted encrypted drop, and prints the recipient URL. It does not reset the credential or print the secret.

Sender and recipient URLs are bearer capabilities, not authenticated operator sessions. `vault-link` is an operator-only local command: the POSIX account with access to the owner-only vault and key is the authentication boundary. It accepts no caller-supplied principal as authorization. `--recipient` is a delivery-policy check, not authentication; stored principal lists are legacy metadata. Use a dedicated account when operator separation is required.

## Production boundary

### High-impact secret mode

The existing same-account vault and one-time-link commands are **limited local** controls. They are prohibited for high-impact credentials (money movement, production root, registrar, primary-mail administration, cloud administration, identity recovery, or bulk destructive systems) because the Hermes process can read their key or invoke plaintext-returning local APIs.

High assurance requires a separately administered UID/container, or a managed secret service/KMS with workload identity. Key and vault files must be unreadable by the Hermes UID. Hermes gets only an owner/ACL-restricted Unix IPC capability for approved named operations. The broker decrypts internally, performs that operation, and returns an opaque provider receipt—never plaintext, ciphertext, a recipient URL, or a model-retrievable one-time link. Human delivery, when approved, goes directly to an authenticated recipient route; the model receives delivery metadata only. Broker failure has no fallback to chat, environment output, local vault, or link recovery.

This repository does not create the separate identity, install a service, or configure KMS/IPC. Until a private deployment proves that boundary, high-assurance mode is `required-unconfigured` and high-impact operations remain Blocked.

| Control | Bundled here | Deployment responsibility |
|---|---:|---|
| Browser encryption and one time state | Yes | Run the tests on the deployed version |
| Bearer sender/recipient links | Yes | Deliver through approved private routes |
| Local operator authentication | POSIX account/file boundary | Use dedicated account or reviewed IAM |
| TLS termination | No | Reverse proxy or private tunnel |
| Public user authentication | No | Gateway, proxy, VPN, or another reviewed layer |
| Rate and abuse limits | Single-process limiter | Gateway/distributed controls for broader exposure |
| Managed key protection | No | OS keyring, KMS, secret manager, or protected file |
| External notification delivery | No | Approved channel adapter reads the protected outbox |
| Central audit sink | No | Selected private logging or security system |
| Backup and key rotation | Documented requirement | Deployment specific |

Do not expose this bundle directly to the public internet. Broader deployment needs reviewed gateway authentication, distributed rate limiting, TLS, token-safe logging, key management, recovery, and a threat model.

## Cleanup and recovery

Run cleanup through a script-only Hermes cron job at the chosen retention interval:

```bash
~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials recover-claims
~/.hermes/runtime/secure-credentials-venv/bin/secure-credentials cleanup
```

`recover-claims` finalizes a delivered file after an interrupted database finalization or safely releases a stale claim whose file was never delivered. `cleanup` deletes expired database rows and matching protected outbox records. Notification workers should consume or archive delivered outbox records according to the private retention policy.

## Human delivery outbox

Browser submission writes a protected outbox record containing the exact recipient URL and drop ID, not the secret. A small approved adapter can deliver that link through Telegram, Slack, email, SMS, or another configured channel.

The adapter must:

1. Read one exact outbox record.
2. Send only the recipient URL.
3. Disable link previews when the channel supports it.
4. Record provider delivery evidence.
5. Remove the outbox record only after verified delivery.
6. Never read or reveal the credential.

## Provider replacement

1Password, Bitwarden, HashiCorp Vault, cloud secret managers, or another approved system can replace the bundled vault. Keep the metadata registry, exact ownership, safe listing, one time sharing, no plaintext output, and live verification contracts.

## Tests

From the repository root:

```bash
python3 -m pytest tests/test_secure_credentials.py -q
```

Required results include one submit, one reveal, preview safe GET, concurrent one winner, agent consume to mode protected file, encrypted vault bytes, safe listing, expiration, and vault to link delivery.
