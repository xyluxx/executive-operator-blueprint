# Artifact Storage Tool

Optional, provider-neutral artifact generation and storage contract reference.
It uses only bundled project dependencies and starts no listener or network
connection.

## Included behavior

- Generates valid CSV, XLSX, DOCX, and PDF files from structured synthetic data.
- Reopens each file, validates Office ZIP/XML relationships and content types or
  PDF xref/page/text structure, and returns exact Unicode content, absolute file
  paths, MIME types, byte sizes, and SHA-256 checksums.
- Prepares `MEDIA:/absolute/path` metadata for Hermes local delivery without
  claiming that chat delivery happened.
- Provides a real owner-private local-filesystem adapter.
- Provides in-memory synthetic contract fakes for Google Drive, OneDrive,
  Dropbox, Box, and S3-compatible storage. These are **not connected or
  Verified providers**.
- Defines disabled-by-default temporary-share staging. It starts no server,
  listener, DNS, TLS, or network route.

## Safety

Runtime outputs belong outside the repository. Use owner-private directories;
do not archive `artifact-output/` or `.artifact-shares/`. Temporary shares
require an explicit recipient, authenticated policy, bounded expiry, and an
Ed25519 receipt from a separate privileged TLS probe authority. That authority
accepts a trusted probe identifier rather than caller-supplied evidence; the
model-facing policy holds only a verifier pinned to its public key. Receipts bind
the exact HTTPS URL/host, certificate or tunnel identity, audience, access policy,
collection time, expiry, and revocation state. Caller booleans, substituted keys,
and modified receipts are rejected. Sources and roots cannot traverse symlinks;
hardlinked, wrong-owner, or group/other-accessible sources and sensitive content
anywhere in a bounded artifact are denied. Unknown-effect and idempotency state
can be persisted in an owner-only operation journal across adapter restarts and
remains blocked until explicit reconciliation. Permission and retention are
issued from a trusted decision resolver by a separate Ed25519 policy authority.
Adapters retain only a read-only resolver pinned to the authority public key, so
record/cache mutation or a caller key cannot forge `public`/`forever` readback.

Run `python3 -m pytest tests/test_artifact_storage.py -q` for synthetic contract
proof. Cloud verification additionally requires separately approved credentials,
exact account/target readback, live upload/readback, permission tests, cleanup,
and provider revocation evidence.
