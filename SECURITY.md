# Security Policy

## Scope

This repository contains an agent blueprint, profile assets, documentation, skills, and reference tools. It does not provide provider accounts, production authentication, TLS termination, a compliance guarantee, or a managed service.

The Secure Credentials toolkit and Website Watchdog require deployment-specific controls before internet exposure or automatic repair.

## Supported release

The current supported blueprint release is `1.0.x`, reviewed with Hermes `>=0.21.0,<0.22.0`.

## Report a vulnerability

Do not place a secret, exploit payload, private hostname, token, or affected user data in a public issue.

Use GitHub private vulnerability reporting through the repository Security tab when available. If it is unavailable, open a public issue containing only a request for a private security contact.

Include:

1. Affected path and version
2. Impact
3. Reproduction using synthetic data
4. Expected safe behavior
5. Suggested mitigation when known

## Security boundaries

1. Prompt instructions are not enforcement.
2. A Hermes profile is not automatically a filesystem sandbox.
3. Encryption at rest does not protect against compromise of the same account and key.
4. Bearer links must be treated as temporary secrets.
5. Reference tools are not production services until their deployment controls and threat model pass.
6. No deployment is compliant because it installed this repository.

## Release gates

A release must pass repository validation, tests, static typing, security lint, dependency audit, privacy scan, clean-clone installation, and exact public readback. A passing test suite does not replace deployment-specific security review.
