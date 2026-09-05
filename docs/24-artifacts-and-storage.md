# 24. Artifact Storage and Preview Delivery

Files should move with the work instead of becoming lost local paths.

## Supported storage shapes

1. Local disk
2. Hermes file attachments
3. Google Drive
4. OneDrive and SharePoint
5. Dropbox
6. Box
7. Nextcloud
8. Amazon S3
9. Cloudflare R2
10. DigitalOcean Spaces
11. Backblaze B2
12. Any compatible file or object API

A provider is selected during onboarding. The blueprint does not force migration from an existing approved storage system.

## Canonical artifact record

1. Artifact ID
2. Related task and workstream
3. Accepted version
4. Local or provider ID
5. File type and size
6. Checksum
7. Owner and data boundary
8. Visibility
9. Share-link status and expiry
10. Retention and deletion policy
11. Source and verification evidence

## Evidence bindings

Acceptance evidence is a structured reference, not an arbitrary note. Each item records an evidence ID and kind, source, resolvable reference, target, artifact version, environment name and version, collection time, accessibility, relevance, and retention policy. Its verification result also binds the criterion, task and requirement versions, artifact and target IDs and versions, evaluator identity and kind, outcome, and evaluation time.

Missing, inaccessible, irrelevant, wrong-target, wrong-version, or unverifiable evidence can produce only `blocked`, `inconclusive`, or `fail`; it cannot produce `pass`. Preserve evidence under its declared retention policy long enough to audit the acceptance record. When an artifact changes, retain unaffected checks and invalidate only criteria that declare the artifact as an input.

## Upload flow

1. Resolve the accepted artifact version.
2. Confirm destination and visibility.
3. Check for an existing object by ID or checksum.
4. Upload or version according to policy.
5. Read back provider ID, size, checksum, version, and permissions.
6. Create a share link only when requested or allowed.
7. Test the link as the intended audience.
8. Record the provider ID rather than copying the file repeatedly.

## Executable reference and status

`tools/artifact-storage/artifact_storage.py` is an optional standard-library
reference. It creates CSV, XLSX, DOCX, and PDF files, reopens their native
structures, verifies expected synthetic content, computes SHA-256, and returns
absolute file paths. `local_preview()` prepares Hermes-compatible `MEDIA:`
metadata with status `prepared-local-not-sent`; it does not touch live chat or
claim delivery.

The local-filesystem adapter is real and owner-private. The Google Drive,
OneDrive, Dropbox, Box, and S3-compatible adapters are in-memory synthetic
contract fakes. No cloud account is connected or Verified. Their common
machine-readable contract is
`templates/artifact-storage-contract.schema.json`.

## Provider-neutral adapter invariant

Every adapter binds the exact account and destination identity; upload
idempotency key; stable provider/object ID; checksum and version readback;
permission scope; retention; delete and revoke behavior; disable path; and
unknown-effect reconciliation. A duplicate key with changed content or policy
is rejected. Any unknown write outcome remains unresolved until reconciliation
returns the provider object or proves absence. Only separately approved live
provider proof may change a cloud adapter from Optional to Verified.

Deletion retains only a non-sensitive audit tombstone: action, provider, version,
time, and one-way digests of the object, account, and target identities. Tombstones
persist across adapter restart, and unexpected fields fail closed. The tombstone
must not retain the source path, object path, content, content checksum, raw
account or target identity, permission, retention value, or provider payload.

## Preview choices

### Hermes surfaces

Return local files through supported Hermes chat or Desktop file delivery when the recipient is the owner.

### Signed object link

Use an expiring signed URL for a selected cloud object when the storage provider supports it.

### Owned preview domain

Use a protected deployment or static host for continuing public work.

### nip.io or sslip.io

These public DNS services resolve hostnames containing an IP address to that address. They are useful only as route labels for disposable non-sensitive development previews.

Temporary sharing is disabled by default. Preparation requires a non-sensitive
regular file, explicit recipient, authenticated access policy, bounded expiry,
verified HTTPS, revocation, and cleanup. The bundled tool only stages an
owner-private copy and reports `prepared-not-hosted`; it never opens a listener,
changes DNS or firewall state, or claims that HTTPS exists. A separately
approved exposure layer must prove HTTPS and audience access before use.

These DNS services do not provide hosting, authentication, privacy, data protection, or wildcard certificates. Never expose credentials, admin pages, client data, or regulated documents through this path. An owned domain is better for continuing work.

## Provider adapter test

1. Authenticate the correct account.
2. Create a synthetic file.
3. Upload and read it back.
4. Compare checksum and size.
5. Create a private or expiring link.
6. Verify access and denial behavior.
7. Revoke the link.
8. Delete or retain under policy.
9. Confirm another folder, bucket, drive, or tenant stayed unchanged.
10. Save the proven procedure as a provider reference or private skill.

## Current blueprint status

`artifact-storage-operator` is Bundled. Provider connections are Optional and require setup. No cloud account is included.
