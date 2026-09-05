# 07. Cost and Efficiency

The system should spend on useful work, not repeated context, healthy polling, or accidental provider routes.

## Cost sources

1. Main model input and output
2. Context length and cache behavior
3. Delegated models and coding harnesses
4. Scheduled agent jobs
5. Web, browser, search, and data APIs
6. Email, SMS, voice, and channel providers
7. CRM, marketing, and enrichment services
8. Hosting, storage, backups, and monitoring

Do not publish one universal monthly estimate. Workload and provider pricing vary.

## Model routing

1. Use one reliable main model.
2. Test a fallback with the same critical tools.
3. Use stronger models only for work that needs them.
4. Pin scheduled and delegated work explicitly.
5. Record which provider handled a material result.
6. Set budgets and stop conditions.

## Deterministic first

Use code instead of a model for:

1. Health polling
2. Checksums
3. Exact comparison
4. Counting
5. Deduplication
6. Rate limits
7. Simple retries
8. State transitions
9. Schedule evaluation

Wake AI for interpretation, diagnosis, drafting, prioritization, or ambiguous recovery.

## Context efficiency

1. Keep always loaded memory compact.
2. Load one relevant project lane.
3. Reference files instead of pasting them repeatedly.
4. Preserve save points so work does not restart.
5. Use session search for exact history.
6. Keep provider and model stable during a long cached conversation when practical.
7. Start fresh with a verified checkpoint when a lineage becomes unhealthy.

## Provider costs

Every integration record should include:

1. Pricing unit
2. Budget limit
3. Rate limit
4. Expected call volume
5. Fallback cost
6. Warning threshold
7. Stop behavior
8. Owner

A fallback can be more expensive or have different coverage. Approve it deliberately.

## Scheduled work

1. Healthy checks remain silent.
2. No-change polls should not call a model.
3. One event should produce one worker.
4. Retire jobs when the governing duty ends.
5. Use bounded retries and leases.
6. Avoid several jobs reading the same sources for the same outcome.

## Cost verification

1. Measure real usage by provider, profile, workstream, and job where supported.
2. Reconcile invoice or provider totals.
3. Test budget stops.
4. Test fallback routing.
5. Confirm disabled routines stop consuming resources.
6. Investigate sudden cost changes before changing the model or deleting useful context.

Efficiency is progress per cost, not simply the cheapest model or smallest memory.

## Aggregate budget and retries

A reassignment starts a new native run but does not reset total budget, deadline, spend, repair count, repair history, or consumed input versions. Concurrent admission is serialized against one aggregate ceiling and reserves the required verification amount before admitting work. Rework keeps unaffected passing criteria and spends from the same total. Retry only a confirmed transient failure within the configured total attempt limit; an `unknown` external effect must be reconciled first. Rate-limit and native worker retry details remain in Kanban run history.
