---
name: artifact-storage-operator
description: Use when storing or sharing approved artifacts.
version: 1.0.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [artifacts, files, cloud, storage, sharing]
    related_skills: [integration-onboarding, credential-operator]
---

# Artifact Storage Operator

## When to Use

Use when work must move between local disk, cloud drives, object storage, project workspaces, or a temporary preview URL.

## Capability Contract

The bundled executable reference is `tools/artifact-storage/artifact_storage.py`
and the machine-readable contract is
`templates/artifact-storage-contract.schema.json`. The local-filesystem adapter
is real. Google Drive, OneDrive, Dropbox, Box, and S3-compatible implementations
are synthetic fakes only: they are Optional, disconnected, and not Verified.

Every storage adapter defines:

1. Account and workspace
2. Data boundary
3. Read, write, list, version, share, and revoke support
4. Stable object ID
5. Destination folder or bucket
6. Conflict and overwrite policy
7. Maximum size and allowed types
8. Checksum support
9. Link visibility and expiration
10. Retention and deletion
11. Cost and rate limits
12. Contract test and evidence
13. Upload idempotency and unknown-effect reconciliation
14. Explicit disable path

## Provider Examples

1. Google Drive
2. OneDrive and SharePoint
3. Dropbox
4. Box
5. Nextcloud
6. Amazon S3
7. Cloudflare R2
8. DigitalOcean Spaces
9. Backblaze B2
10. Any compatible object or file API

These are examples. Use the owner’s existing provider when it satisfies the contract.

## Procedure

1. Resolve the exact artifact and accepted version.
2. Resolve the approved destination and data boundary.
3. Check the provider’s current documentation and connector.
4. Verify authorization and least-privilege scope.
5. Check for an existing object by stable ID or checksum.
6. Upload or update according to conflict policy.
7. Read back object ID, size, checksum, version, and permissions.
8. Create a share link only when requested or policy allows.
9. Verify link visibility and expiration without consuming one-time access.
10. Record the durable provider ID and evidence.
11. Revoke or retire stale links under the retention policy.

## Temporary Previews

Hermes can return local files directly through supported chat surfaces. Prepare
an absolute `MEDIA:` path and mark it `prepared-local-not-sent`; only the live
Hermes delivery surface may claim delivery. For browser previews, use a protected
temporary server, object-storage signed URL, or approved domain.

`nip.io` and `sslip.io` can map a hostname containing an IP address to that IP.
Temporary sharing is disabled by default and this bundle starts no listener or
network route. A separately approved exposure layer must provide an explicit
recipient, authentication, bounded expiry, verified HTTPS, revocation, and
cleanup. Sensitive content is always denied. These DNS services do not provide
authentication, privacy, hosting, or TLS. Prefer an owned domain for continuing
work.

## First Integration Rule

The first use of a provider is a setup task:

1. Read current documentation.
2. Define the adapter contract.
3. Test with synthetic content.
4. Test one real approved file.
5. Verify download, version, permission, and deletion or revocation.
6. Save the proven workflow as a provider reference or private skill.

## Approval Boundaries

Uploading private data, changing permissions, replacing files, creating public links, moving ownership, and deleting data require the configured policy for that destination.

## Verification

1. Object identity matches the intended artifact.
2. Checksum and size match.
3. Accepted version is current.
4. Permissions match the requested audience.
5. Public or signed link behavior is tested.
6. Another folder, bucket, or tenant remains unchanged.
7. Revocation works.
8. No credential appears in logs, metadata, or chat.
