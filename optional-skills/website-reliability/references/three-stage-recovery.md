# Three Stage Recovery Worker

## Stage 1. Deterministic collector

1. Read active targets from a private registry.
2. Probe the narrow health definition.
3. Retry within policy.
4. Persist state.
5. Print nothing when healthy.

## Stage 2. Incident queue

1. Require configured failed cycles or independent evidence.
2. Create one incident ID.
3. Store target, ownership, hosting, allowed repairs, attempts, and evidence.
4. Acquire one lease before dispatch.
5. Requeue a stale worker only after lease expiry and below the retry limit.

## Stage 3. AI worker

1. Recheck the incident before acting.
2. Load only the target context.
3. Distinguish monitor path failure from target failure.
4. Diagnose root cause.
5. Apply only listed reversible repairs.
6. Verify public and local state, intended version, and persistence.
7. Record the result.
8. Stay silent after verified recovery when policy allows.
9. Escalate unresolved failure with the smallest useful decision.

## Control record

A worker result includes:

1. Incident ID
2. Diagnosis
3. Action
4. Result
5. Verification
6. Remaining risk
7. Next action
8. Notification state

## Required tests

1. One failed probe stays transient.
2. Sustained failure queues once.
3. Lease prevents duplicate workers.
4. Stale lease retries within bounds.
5. Recovered incident dismisses queued work.
6. Wrong target action is blocked.
7. Successful repair is verified.
8. Failed repair notifies once.
9. Restart preserves queue state.
