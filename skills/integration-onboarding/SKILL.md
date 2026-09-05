---
name: integration-onboarding
description: Use when adding a new tool or capability safely.
version: 1.1.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [integrations, skills, plugins, discovery]
---

# Integration Onboarding

Close a capability gap with the smallest reviewed route. A new task can trigger this workflow; do not assume an integration or install from a catalog description.

## When to Use

- A task needs a tool, provider, skill, plugin, MCP server, or permission not already verified.
- An existing route is broken or no longer fits the data boundary.
- Do not replace a working native capability merely for novelty.

## Procedure

### 1. Inspect the current lane

Define the outcome and exact evidence before choosing a route. Inspect current tools and Hermes behavior, profile configuration, installed skills, plugins, MCP servers, credentials metadata, and verified routes. Do not run a live check during discovery.

Completion criterion: the gap is proven and no current verified route already satisfies it.

### 2. Research authoritative documentation

Read dated current official Hermes documentation and the provider's authoritative documentation. Record each source URL and retrieval time plus supported operations, authentication, scopes, limits, cost, data handling, write behavior, and disable path. A missing or stale provider fact blocks the related claim.

Completion criterion: current first-party sources establish feasibility and constraints.

### 3. Search and inspect candidates

Search native Hermes features first, then installed reviewed skills and plugins, MCP, direct APIs, browser automation, and custom code. Inspect candidate files, source repository, immutable version/ref, license, maintainership, dependencies, permissions, data path, tests, code, and cost before recommendation. Include `do-not-enable` as a real route. Never install or vendor a community skill based only on its description.

Completion criterion: each viable candidate has evidence sufficient for a trust and data-risk decision.

### 4. Recommend options

Present the preferred route, `do-not-enable`, and meaningful alternatives with coverage, trust, permissions, data risk, cost, maintenance, fallback, and uninstall consequences. Obtain explicit selection approval; it does not authorize a later live write.

Completion criterion: one option is selected with exact scope and approval.

### 5. Install and configure the selection

Pin an immutable commit or content digest; a mutable branch or floating version is insufficient. Install only into the intended isolated profile, keep it disabled until configured, request least privilege through the approved credential path, and record metadata without secret values.

Completion criterion: installed state, version, permissions, and owner match the approved option.

### 6. Run synthetic proof

Use a fake adapter and synthetic data to run the provider-neutral full-loop: narrow read, scoped write, exact target/value readback, expected failure, idempotency, unknown-effect reconciliation, revoke, fallback, disable, and rollback. Synthetic proof never establishes a private account as Verified.

Completion criterion: the provider-neutral contract passes without a provider account, network call, credential, or private data.

### 7. Request and run separate live proof

Only after synthetic proof, request separate exact approval naming account, operations, target, material payload, limits, and rollback. Run read first, then the approved reversible write, then exact-target readback. A timeout after dispatch is `unknown`; reconcile before retry. Without approval or credentials, remain Optional, Planned, Blocked, or Configured as supported by evidence.

Completion criterion: current deployment evidence proves the exact live route, or the record names the precise blocker without a Verified claim.

### 8. Resolve and capture the capability

Write a private resolution record that validates against `templates/resolved-capability.schema.json`, including selected source, immutable ref and checksum when available, license, provenance, permissions, data boundary, tests, fallback, disable, and rollback. Update the integration registry and relevant project lane. Capture a stable repeated procedure as a reviewed skill only after searching existing skills; remove account identities, payloads, secrets, and other private data before reusable capture.

Completion criterion: a fresh session can route the task, explain why this option is active, reproduce its resolved source, and disable it safely.

## Behavioral Tests

- Provide an already-capable native tool and confirm no installation occurs.
- Provide a community description without inspectable source and confirm it is not installed.
- Withhold approval or credentials and confirm the route remains blocked.
- Run synthetic proof first and confirm no live adapter call occurs.
- Withhold separate live-write approval and confirm the write is denied.
- Run the selected approved route through read, write/readback, unknown-effect reconciliation, revoke, fallback, disable, and rollback tests.
- Start a similar task in a fresh session and confirm the captured lane or skill is discovered.

## Pitfalls

- Configured is not Verified.
- Browser login state is not durable API authentication.
- Do not broaden scopes for hypothetical future work.
- Preserve upstream licenses and notices when approved code is copied.

## Verification

Confirm current-tool inspection, authoritative research, candidate inspection, explicit selection, pinned installation, full-loop evidence, registry readback, and a working disable path.
