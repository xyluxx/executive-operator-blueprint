# 09. Roadmap and Honesty
<!-- capability-status-contract: {"authority":"contracts/capability-status.yaml","statuses":["Native","Blueprint","Bundled","Configured","Verified","Optional","Planned","Blocked"]} -->

This repository separates platform availability, bundled assets, private configuration, real verification, and future work.

## Status vocabulary

1. **Native:** Hermes supplies the feature in the required version.
2. **Blueprint:** this repository documents the behavior or implementation contract.
3. **Bundled:** this repository ships the asset.
4. **Configured:** the installer selected and connected it.
5. **Verified:** a real contract test passed.
6. **Optional:** the owner may enable it.
7. **Planned:** documented but not installed or proven.
8. **Blocked:** a named dependency, permission, decision, or test prevents use.

[`contracts/capability-status.yaml`](../contracts/capability-status.yaml) is the sole normative authority for these labels.

## Native Hermes examples

Subject to the installed version and platform:

1. CLI and TUI
2. Desktop
3. Profiles and distributions
4. Sessions and session search
5. Memory framework and providers
6. Skills
7. Plugins and hooks
8. MCP client
9. Gateway channels
10. Cron and background work
11. Delegation
12. Bot Mode
13. Backups, imports, exports, and checkpoints

Native availability still requires setup and testing.

## Bundled and tested in this repository

1. Public installation and onboarding contracts
2. Generic operating `SOUL.md`
3. Six reviewed provider-neutral core skills
4. Machine readable core and optional-pack catalogs
5. Integration and credential metadata schemas
6. Operator State reference tool
7. Secure Credentials reference toolkit
8. Website Watchdog deterministic collector
9. Repository validation and unit tests
10. AI installer and human installation guides

These assets are not proof that any private provider account or production service is connected.

## Optional setup

1. Model provider and fallback
2. Messaging channels
3. Remote Desktop backend
4. Email and calendar provider
5. Meeting transcript provider
6. CRM
7. Marketing and SEO data
8. PR sources and sending account
9. Secret manager
10. Coding harness
11. Website targets and recovery policy
12. Managed specialist profiles or Bots

All optional integrations default to disabled or credential blocked until verified.

## Blueprint extensions

The repository describes patterns that may require further implementation in a specific deployment:

1. Guaranteed automatic message intake into business state
2. Runtime reference resolution across every channel
3. Automatic business approval enforcement beyond native command gates
4. Production AI website repair workers
5. Cross provider CRM and marketing adapters not included as code
6. Organization specific workflows and data objects
7. Regulated environment controls
8. Multi tenant administration

A skill or document can define the contract without claiming the extension is deployed.

## Claims that require live proof

1. A channel can send and receive.
2. A model and fallback work.
3. A credential is valid.
4. A CRM write landed once.
5. An email was sent.
6. A calendar invitation has the correct attendee and time.
7. A transcript is complete.
8. A marketing total uses the right account and definition.
9. A website is healthy from the required vantage.
10. A restart preserves service.
11. A backup can restore.
12. A Bot has the correct memory and tools.

## Public privacy rule

Never publish:

1. Private names or client data
2. Real credentials or token shaped examples
3. Private domains, IPs, account IDs, or local paths
4. Onboarding answers
5. Session exports or memory
6. CRM objects
7. Incident history
8. Provider payloads that reveal private configuration
9. Private implementation plans

## Roadmap process

1. Identify a repeated need.
2. Search current Hermes capabilities.
3. Decide whether it is configuration, skill, plugin, MCP, adapter, tool, or domain state.
4. Write the smallest contract and tests.
5. Review privacy, security, cost, and approval impact.
6. Implement in a private deployment.
7. Verify with real output.
8. Generalize only after removing private data.
9. Version and publish the reusable part.
10. Keep unverified ideas labeled Planned.

Honesty is part of the product. A repository becomes impressive by being complete, testable, and clear about what is real.
