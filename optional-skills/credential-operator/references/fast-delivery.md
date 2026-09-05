# Fast Credential Delivery

Use this path only for a known stored credential and an authorized recipient.

## Direct path

1. Resolve the exact service ID.
2. Read safe vault metadata.
3. Confirm owner scope and recipient authority.
4. Verify the stored secret through a safe local or provider verifier when required.
5. Create a submitted one time recipient link from the vault.
6. Verify submitted state without revealing it.
7. Return only the link and expiration.
8. Record delivery evidence after the selected channel confirms it.

The direct path should not rebuild the credential service, search unrelated files, or reset a credential that already verifies.

## Stop conditions

1. More than one account matches.
2. Recipient authority is unclear.
3. Stored status is expired or revoked.
4. Client or external ownership prohibits delivery.
5. MFA or hardware approval changes the workflow.
6. The one time link cannot be verified.

## Performance target

After the vault, registry, and Secure Drop are configured, a valid approved request should require one metadata lookup, one optional verifier, one drop creation, and one submitted-state check.

Measure total time and investigate repeated delay. Security does not require unnecessary rediscovery.

## Verification

1. Correct account selected.
2. No reset occurred.
3. Secret appeared in no ordinary output.
4. Link is submitted and unconsumed.
5. Recipient link expires.
6. Second reveal fails.
