---
name: credential-operator
description: Use when receiving, storing, or sharing credentials.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Credentials, Vault, Security, Sharing]
    related_skills: [integration-onboarding]
---

# Credential Operator

Use this skill when a principal or teammate must provide a secret to the agent, retrieve an approved credential, or maintain a reusable credential registry.

Use `$HERMES_HOME/tools/secure-credentials/` as the bundled reference implementation after native profile installation. In a trusted repository checkout, resolve the equivalent path from the repository root. Another approved secret manager may replace it if the same safety contract passes.

The bundled file-permission implementation is currently for POSIX systems. On Windows, use a reviewed secret manager or add and test equivalent ACL enforcement before treating this skill as available.

See `references/fast-delivery.md` for the direct approved vault-to-link path.

## Reference Tool

Bootstrap once with `python3 "$HERMES_HOME/tools/secure-credentials/bootstrap.py"`, then use its printed executable path with standard input or protected files. Do not assume the terminal's current directory is the profile root:

```text
terminal(command="<secure-credentials-executable> create --claim-file <protected-claim-path>")
terminal(command="<secure-credentials-executable> consume --claim-file <protected-claim-path> --output <exact-secret-destination>")
terminal(command="<secure-credentials-executable> vault-list")
terminal(command="<secure-credentials-executable> vault-link <service-id> --recipient <recipient-id> --ttl 3600")
```

Do not pass secret values as command arguments.

Bearer drop links authorize exactly one submit or reveal. Operator commands instead rely on the owner-only vault/key and local OS account. Never treat a caller-provided principal label as authentication; use a dedicated account or reviewed IAM when operator separation is required.

## When to Use

1. Receive a password, API key, token, or recovery secret.
2. Store a reusable internal credential.
3. Give an authorized human a one time credential link.
4. Write an approved credential into an exact protected provider file.
5. Verify whether a stored credential still works.
6. Rotate an internal credential under explicit authority.
7. Inspect safe credential metadata.

## Separation Model

1. Integration registry stores capability and safe credential reference.
2. Credential registry stores service metadata and policy.
3. Encrypted vault stores reusable secret values.
4. Secure Drop stores one time ciphertext only.
5. Chat, memory, CRM, profiles, logs, and project files store no secret values.

## Ownership Policy

Every credential records:

1. Service and account identity
2. Internal, personal, external, or client owned scope
3. Principal and authorized recipients
4. Whether reset or rotation is allowed
5. Secret location
6. Last live verification
7. MFA requirement
8. Status and expiration

Access to a server does not create authority to reset an external client account.

## Receive a Secret

1. Identify the exact service, account, owner, and intended consumer.
2. Create a sender link with the bundled tool or approved replacement.
3. Return only the sender link.
4. The sender’s browser encrypts before upload.
5. For agent use, consume once into an exact mode protected destination.
6. Validate the credential with the narrowest live request.
7. Store only metadata and the protected pointer.
8. Verify the drop is consumed and cannot be read again.

Completion criterion: the intended protected destination contains the secret, the live check passes, and no plaintext appears in ordinary output.

## Fast Approved Delivery

1. Read the canonical vault metadata.
2. Confirm the requested account and recipient authorization.
3. Verify the stored secret without a browser login when the provider offers a safe local verifier.
4. Generate a submitted one time recipient link directly from the vault.
5. Verify submitted state without opening the link.
6. Return only the non previewed link and expiration.
7. The reveal consumes and deletes the drop.

Completion criterion: an approved stored credential becomes a verified one time link without reset, duplicate research, or plaintext chat.

## Rotation

1. Confirm exact account and authority.
2. Read the live account before changing it.
3. Use the application’s own hashing, API, or reset workflow.
4. Change only the named account.
5. Verify the new value through the provider.
6. Prove unrelated accounts are unchanged.
7. Update the encrypted vault immediately.
8. Record safe evidence without the value.

## Pitfalls

1. Do not send a secret in chat because the secure route is slower.
2. Do not open a one time human link merely to verify it.
3. Do not call a submitted drop received until the intended consumer can use it.
4. Do not select the newest drop when several are active; use an exact ID.
5. Do not back up the one time drop database.
6. Do not place the vault key beside an unprotected vault backup.
7. Do not print a secret through shell arguments or command history.
8. Do not reset external accounts under generic internal authority.

## Verification

1. Vault and key permissions meet platform policy.
2. Known plaintext is absent from vault database bytes.
3. Safe listing omits ciphertext and plaintext.
4. Sender link accepts one submission.
5. Recipient link reveals once.
6. Browser previews and GET requests do not consume.
7. Agent consume writes once to the exact protected file.
8. Concurrent reveals produce one winner.
9. Expired drops are removed.
10. Logs contain no secret or URL token.
11. Fast vault delivery reaches submitted state.
12. External reset policy fails closed.
