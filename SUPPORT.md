# Support and Version Policy

## Start here

1. Installation: `INSTALL.md`
2. AI implementation contract: `AI-INSTALL.md`
3. Onboarding: `ONBOARDING.md`
4. Capabilities: `CAPABILITIES.md`
5. Security: `SECURITY.md`

## Troubleshooting order

1. Run `hermes --version`.
2. Run `hermes doctor`.
3. Run `hermes config check`.
4. Run `python3 scripts/preflight.py --json` from a clean checkout.
5. Run `python3 scripts/validate_blueprint.py`.
6. Run the relevant tool test.
7. Inspect the exact profile, provider, connector, channel, or service.
8. Disable the narrow failing optional component.
9. Restore only from a verified backup.

## Compatibility

Release `1.0.x` is reviewed against Hermes `>=0.21.0,<0.22.0`.

A future Hermes minor release is not automatically supported. Update the compatibility range only after clean profile installation, configuration, session, memory, skill, tool, plugin, MCP, gateway, and backup tests pass.

## What support can determine

Repository maintainers can help with blueprint files, examples, skills, reference tools, and reproducible synthetic failures.

Provider accounts, hosting contracts, private data, custom connectors, legal compliance, and production incident response remain the responsibility of the deployment owner and selected vendors.

## Issues

Public issues must contain synthetic data only. Use private vulnerability reporting for security findings.
