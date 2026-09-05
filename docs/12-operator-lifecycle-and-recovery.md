# 12 — Operator Lifecycle, Audit, and Kill Switch

A reusable operator needs a full lifecycle. Provisioning is only the beginning.

## 1. Onboarding

1. Name the principal, organization, purpose, and isolation requirement.
2. Create a dedicated Hermes profile or machine.
3. Install the foundation distribution.
4. Author the private `SOUL.md` and principal memory.
5. Define duties, work objects, source authority, and approval policy.
6. Configure the working directory and tool isolation.
7. Register integrations in a disabled state.
8. Configure memory, persistence, monitoring, backups, and restore.
9. Run synthetic concurrent-work, approval, fallback, privacy, and recovery tests.
10. Add credentials one integration at a time and run live contract tests.
11. Complete a fresh-session identity and duty test.
12. Record handoff evidence and credential ownership.

## 2. Operation

Every operator should maintain:

1. Current projects, duties, commitments, tasks, obligations, and waiting items.
2. Dated activity and approval history.
3. Integration capability, credential, health, cost, and contract-test metadata.
4. Extension lifecycle and rollback evidence.
5. Scheduled job ownership and next run.
6. Provider and model usage by capability or workstream.
7. Backup, restore, crash recovery, and reboot evidence.
8. Memory integrity, fact count, retrieval quality, and contradiction review.

## 3. Cost attribution

Track costs at the narrowest practical level without exposing secret values:

1. Model and provider.
2. Operator profile.
3. Workstream or duty.
4. External integration.
5. Scheduled job.
6. Source run or campaign.
7. Human-approved budget.

A provider budget should stop work before exceeding its limit. A cost dashboard is useful only when the underlying usage and attribution are verified.

## 4. Audit trail

Consequential actions should record:

1. Actor and principal.
2. Approval reference.
3. Duty and work item.
4. Provider or tool.
5. Exact action and target.
6. Time and timezone.
7. Idempotency reference.
8. Result and readback evidence.
9. Error, retry, or rollback.
10. Related external record ID.

Do not store secret values or sensitive provider payloads in the audit trail.

## 5. Health and self-checks

Use deterministic checks before spending model tokens:

1. Gateway and service health.
2. Database integrity and migration level.
3. Credential presence and expiration metadata.
4. MCP discovery and allowed tool count.
5. Provider contract status and rate limits.
6. Cron next-run and last-result state.
7. Memory database integrity and retrieval smoke test.
8. Backup freshness and restore-test age.
9. Dead letters, retry storms, and budget warnings.
10. Profile distribution version and local override drift.

Healthy checks remain silent. Repeated transient failures become degradation rather than disappearing.

## 6. Kill switch

Every operator needs a known stop path.

### Communication kill switch

Disable messaging and outbound provider capabilities while keeping local inspection available.

### Automation kill switch

Pause cron jobs, loops, goals, Kanban dispatch, and domain workers without deleting state.

### Provider kill switch

Disable one integration or capability route and prevent fallback to an unapproved provider.

### Agent kill switch

Stop the gateway and domain services. Preserve state and evidence for investigation.

### Credential compromise

1. Disable the affected integration.
2. Revoke or rotate the credential at the provider.
3. Update Hermes secret storage.
4. Invalidate sessions when required.
5. Inspect audit history.
6. Run a clean contract test.
7. Re-enable only after readback.

## 7. Brain recovery

When the operator behaves incorrectly, distinguish the layer:

1. **Session problem**: start a fresh session or repair routing.
2. **Identity problem**: inspect `SOUL.md`, project context, and threat-scanner logs.
3. **Memory problem**: back up, run integrity and contradiction checks, repair vectors, test retrieval.
4. **Model problem**: pin or roll back the model and verify the fallback chain.
5. **Skill problem**: disable or revert the changed skill, then refresh the skill snapshot.
6. **Plugin problem**: disable the plugin and restart cleanly.
7. **Domain migration problem**: restore a database snapshot or run the tested downgrade.
8. **Filesystem problem**: use Hermes checkpoints or a protected backup where applicable.

Recovery is complete only when a fresh session performs one safe duty correctly.

## 8. Offboarding

1. Pause external communication and scheduled work.
2. Export required principal-owned records.
3. Revoke provider credentials, OAuth grants, bot tokens, and webhook secrets.
4. Remove or transfer external application ownership.
5. Archive or delete the profile according to the retention agreement.
6. Purge domain data and backups when required.
7. Remove gateway and domain services.
8. Verify DNS, webhooks, cron, MCP, and provider callbacks no longer target the operator.
9. Record completion evidence without retaining secrets.

Offboarding is not complete because a service stopped. Access, credentials, automations, callbacks, data, and backups must all reconcile.

No generic batch-retirement callback is trusted. Before any retirement mutation, every credential must advertise reversible disable and restore, and each credential must pass disable/readback/restore/readback preflight. Final revocation is serial with compensation and readback; otherwise retirement remains Blocked before schedules or tasks are changed.
