# Integration contract harness

`integration_contract.py` is a pure provider-neutral contract harness with an in-memory fake adapter. It proves ordering, payload/task/version/account/target-bound expiring approval, explicit operation-digest idempotency, exact readback, unknown-effect reconciliation, exact protected evidence authority, state-bound promotion, immediate proof invalidation, revocation, and disable behavior without accounts, credentials, SDKs, or network calls.

`EvidenceAuthorityResolver` exposes an integrity-pinned, read-only view of `contracts/evidence-authorities.json`. The model-facing `EvidenceReceiptVerifier` has only a pinned Ed25519 public key. A separately privileged `EvidenceFetchAuthority` holds the private key and can sign only after its trusted fetcher retrieves the exact registered URL with no redirect/canonical mismatch and validates the title, required assertions, timestamp, and fetched-content SHA-256 pin. Public hashes, caller assertions, substituted keys, and tampered receipts are not authority.

The bundled profile has no issuer, private key, or live fetch path. Google Sheets and Composio remain blocked from `Configured` and `Verified` until private onboarding supplies fresh trusted-fetch receipts.

It is test infrastructure and a reference adapter contract, not a configured integration. Run `pytest -q tests/test_integration_contracts.py` from the repository root.
