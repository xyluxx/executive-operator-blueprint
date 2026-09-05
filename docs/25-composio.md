# 25. Composio as an Optional Connector Layer

Composio can be useful when an owner wants one connection layer for many SaaS providers. It is optional and does not replace native Hermes features, direct MCP servers, provider APIs, approval policy, or source authority.

## Why it can fit

Provider features, pricing, limits, scopes, write behavior, and data terms change. This repository intentionally carries no quota, free-plan, or cost claim. At setup time, the separately privileged `EvidenceFetchAuthority` must fetch each exact Composio URL registered in `contracts/evidence-authorities.json`, reject redirects/canonical mismatch, validate title and required assertions, hash the fetched bytes, and issue a current Ed25519 receipt. The runtime receives only the pinned-public-key verifier. Caller-selected paths, assertions, public-hash fabrications, substituted signing keys, and arbitrary paths on `docs.composio.dev` are not authority. The bundle has no issuer or live fetch, so missing, stale, mismatched, or tampered evidence blocks Configured and Verified promotion until private onboarding.

## Use it when

1. Several selected SaaS tools are supported.
2. The owner accepts the provider’s authentication and retention model.
3. The free or paid usage model fits the budget.
4. Direct connectors would create unnecessary repeated work.
5. The required operations and scopes can be narrowed.

## Prefer a direct connector when

1. The account needs a provider-specific feature Composio does not expose.
2. Data retention or residency requirements are incompatible.
3. A direct official MCP or API is simpler.
4. The owner already has a reliable private integration.
5. Cost, latency, or rate limits make the connector unsuitable.

## Setup contract

1. Read current official Composio and Hermes MCP documentation and timestamp each source.
2. Choose managed app or owner-supplied OAuth application.
3. Name exact accounts, tenants, scopes, and prohibited operations.
4. Register the connector as Optional and disabled.
5. Add credentials through the approved flow.
6. Discover actual tools for the authenticated account.
7. Allowlist the selected capabilities.
8. Run a narrow read.
9. Run one approved reversible write when needed.
10. Read back the target.
11. Test revoke, disable, and fallback.
12. Record current plan, pricing, limits, scopes, write behavior, retention, usage, and data-policy evidence without copying private payloads.

## Sheets and files

Composio can be one option for Google Sheets, Drive, OneDrive, Dropbox, and other supported providers. Direct Google Workspace, Microsoft Graph, provider MCP, or API integrations remain equally valid.

## Security and cost

1. Connected does not mean authorized for every operation.
2. Tool names do not prove account identity.
3. Free limits and managed-app allowances are different concepts.
4. Premium provider tools can carry separate charges.
5. Trigger events need idempotency.
6. Logs and payload retention must match policy.
7. ZDR, BAA, KMS, and IP controls require current verification.
8. A timed-out write requires target readback before retry.

## Current blueprint status

`composio-integration` is a Bundled operating skill. Composio itself is Optional, unconfigured, and disabled. No Composio account, connector, credential, or live proof is included.

## Official references

1. [Composio documentation](https://docs.composio.dev/)
2. [Composio pricing](https://composio.dev/pricing)

Recheck both during onboarding because provider behavior, limits, and commercial terms can change.
