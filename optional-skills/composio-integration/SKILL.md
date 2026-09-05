---
name: composio-integration
description: Use when connecting SaaS tools through Composio.
version: 1.1.0
author: xyluxx
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [composio, integrations, mcp, oauth, tools]
    related_skills: [integration-onboarding]
---

# Composio Integration

## When to Use

Use when an owner wants one optional connector layer across many SaaS accounts instead of configuring every direct API separately.

Composio is an optional provider, not a dependency and not a substitute for source authority, approval policy, or live verification.

## Current Positioning

Do not repeat plan, quota, feature, or cost figures from memory or this repository. At setup time, retrieve current official pricing, plan, tool limits, trigger limits, scopes, write behavior, and data-policy evidence. Store a timestamp and source URL for every category. Missing or older-than-policy evidence blocks both Configured and Verified promotion.

## Onboarding

1. Which capabilities are needed?
2. Which provider accounts and tenants are involved?
3. Does the owner use a Composio-managed app or their own OAuth application?
4. What scopes are required?
5. Which operations are prohibited?
6. Which triggers are needed?
7. What payloads may Composio retain?
8. Are data residency, ZDR, IP allowlisting, KMS, DPA, or BAA controls required?
9. What usage and premium-tool budget applies?
10. What direct connector remains available if Composio is degraded?

## Hermes Integration Pattern

1. Read current official Composio and Hermes MCP documentation and timestamp every source.
2. Register the connection as an Optional integration.
3. Store only the secret variable or OAuth reference in metadata.
4. Add the approved MCP or API route through native Hermes configuration.
5. Discover the actual tools available to the authenticated account.
6. Allowlist only the selected capability group.
7. Keep writes disabled until their individual contract tests and approvals pass.
8. Record provider, toolkit, account identity, scopes, and evidence without secret or private payload values.

## First Connection Test

1. Authenticate through the approved flow.
2. Identify the exact account or workspace.
3. List available tools without mutation.
4. Perform one narrow read against known data.
5. Perform one harmless or reversible write only with approval.
6. Read back the exact target.
7. Test revocation or disable behavior.
8. Confirm logs and retention match policy.
9. Record observed usage and cost only from the selected account's current official evidence; make no public quota claim.

## Failure Rules

1. Never silently substitute another account or provider.
2. Do not retry a timed-out write before target readback.
3. Treat missing scopes as a credential gate, not a reason to broaden access automatically.
4. Treat a missing tool as a coverage gap. Check direct API, another MCP, or a private adapter.
5. Stop when the selected privacy controls are unavailable.
6. Keep provider-specific lessons in a reference file or private skill after validation.

## Verification

1. Correct account and tenant
2. Exact scopes
3. Tool allowlist
4. Narrow read
5. Approved safe write and readback when applicable
6. Trigger deduplication
7. Revocation
8. Retention and privacy policy
9. Usage and premium cost
10. Fallback or disable path

Configured additionally requires fresh setup evidence for pricing, plan, tool limits, trigger limits, scopes, write behavior, and data policy. Verified additionally requires separately approved live read/write/readback proof. Synthetic tests alone satisfy neither promotion.
