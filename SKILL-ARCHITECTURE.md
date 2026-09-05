# Skill and capability-pack architecture

## Review result

The distribution ships seven loadable executive core skills:

1. `continuity`
2. `integration-onboarding`
3. `inbox-triage`
4. `meeting-action-items`
5. `document-action-items`
6. `grounded-citations`
7. `calendar-operations`

The core is provider-neutral and complements native Hermes task, memory, tool, plugin, and skill discovery. It does not bundle a second framework.

## Skill disposition

| Previous bundled skill | Current disposition | Reason |
|---|---|---|
| `agency-foundation` | removed as a loadable skill | Its authority, approval, truth, and completion rules belong to `SOUL.md`, which already carries them. |
| `continuous-work-operator` | replaced by `continuity` | Smaller contract around checkpoints, reconciliation, and resume behavior. |
| `executive-assistant` | split into three core skills | Inbox and meeting behavior need independent triggers; document obligations were missing. |
| `integration-onboarding` | retained and rewritten | Now performs current-tool inspection through full-loop test and lane capture. |
| `credential-operator` | optional `secure-credentials` pack | High-risk capability needed only when the selected secret path is not native. |
| `crm-operator` | optional `crm` pack | Provider and workspace specific. |
| `growth-intelligence` | optional `marketing-and-seo` pack | Business-domain capability. |
| `pr-operator` | optional `public-relations` pack | Brand, sender, and approval specific. |
| `website-reliability` | optional `website-reliability` pack | Requires named sites and operational permissions. |
| `artifact-storage-operator` | optional `artifact-storage` pack | Storage provider and audience specific. |
| `composio-integration` | optional `composio-connectors` pack | External provider and OAuth boundary. |

No third-party code was copied. Existing repository-authored optional skills retain their MIT declarations and history under `optional-skills/`.

## Catalog review

The review considered the current Hermes capability surface and installed/official catalog areas for tasks and memory, email, meetings, documents, research and citations, credentials, CRM, storage, development harnesses, deployment, recruiting, travel/maps, finance/data analysis, and visual design. Existing capability names are discovery hints, not installation decisions. The package does not vendor community skills from descriptions.

`optional-packs.yaml` is the machine-readable selection catalog. Its identifiers exactly match every non-core pack in `capabilities.yaml` and the install-answer schema. Every pack is disabled by default and records source class, candidate identifiers, trust posture, license handling, version/ref policy, prerequisites, permissions, data risk, behavioral tests, fallback, and disable path. A `discovery-required` source deliberately has no selected locator until `integration-onboarding` inspects a real candidate and writes a validated resolved-capability record.

## Composition and write ownership

1. `continuity` owns canonical task search, deduplication, checkpoints, status, and completion evidence.
2. `inbox-triage`, `meeting-action-items`, and `document-action-items` extract source-linked candidates, then route task changes through `continuity` rather than writing duplicate commitments independently.
3. `grounded-citations` supports claim verification. It does not own tasks, CRM records, or external actions.
4. `integration-onboarding` owns capability discovery, extension review, configuration evidence, and disable paths. It does not own the business outcome that triggered discovery.
5. `calendar-operations` owns provider-neutral calendar semantics and reconciliation; optional adapters own provider I/O only and remain unverified until live contract tests pass.
6. An optional CRM adapter may write relationship activity to the selected CRM as a derived/reference integration or import CRM tasks as migration inputs, but native Hermes Kanban remains the sole task-lifecycle authority.
7. Growth, PR, research, and leadership packs may share sources, but each output retains one named owner and one target system. A source event is reconciled once before any downstream write.
8. When two skills match, the source-specific skill extracts evidence first, `continuity` reconciles work state second, and the selected provider adapter performs an approved external write last.

## Install-on-demand lifecycle

1. A real task exposes a capability gap.
2. `integration-onboarding` inspects native and currently configured routes.
3. It reads authoritative Hermes and provider documentation.
4. It searches and inspects candidate source, license, version, dependencies, permissions, and tests.
5. The operator recommends options; the principal selects and approves scope.
6. The selected route is pinned, installed disabled, configured least-privilege, and tested end to end.
7. Verified routing and the disable path are captured in the integration registry and task or project lane.

A pack remains optional or configured—not Verified—until its listed tests pass against the selected provider with readback.
