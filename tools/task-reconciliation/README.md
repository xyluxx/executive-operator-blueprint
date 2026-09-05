# Native Kanban task reconciliation

`reconcile.py` is a thin provider-neutral layer over Hermes Kanban. It does not
create another task database. Conversation, meeting, email, and calendar
adapters submit observations with stable source IDs, timezone-aware timestamps and
sequences, normalized principal, client/data-boundary, workstream and exact
target identities, canonical references, and evidence links. Empty scope or
reference values and naive or malformed timestamps fail closed. All timestamp
fields are normalized to UTC and freshness compares instants, not ISO strings.
Shared references never bridge targets or clients.

The reconciler stores durable checkpoints as structured Kanban comments and
uses native card idempotency keys. Replays update the same card, while manual
cards without reconciliation identity remain untouched and unassigned.

## Completion boundary

A source's policy, protected digests, `verified` flag, criterion results, and
authority fields are ignored as untrusted data. Completion requires a trusted
control resolver to load the protected current policy and exact task,
requirement, artifact and target versions from the current card/control store.
Meeting completion additionally requires an independent trusted adapter to
attest actual occurrence, the exact requested person, every requested topic,
and trusted evidence references. Invitations, source claims, stale evidence,
and delivery receipts cannot complete a card.

Partial observations preserve satisfied and outstanding criteria, artifact and
requirement versions, owner, next actor, blocker, wake condition, and exact
resume point. Per-field freshness prevents older events from regressing any
checkpoint while retaining their event identity for idempotent replay.
Accepted completion writes the acceptance record to native run
metadata, moves the same card to `done`, creates an optional idempotent next
recommended card, and persists one owner-acknowledgment intent per accepted
requirement/artifact version before dispatch. It is emitted only after exact
recipient/channel delivery readback; unknown effects remain reconcilable and
retry with the same operation key. Durable receipt comments bind that key to
the exact task/version, recipient, channel, content digest, and provider status.
They are reconciled before resend, including after a process crash between the
receipt write and final state checkpoint.

## Integration

Instantiate `NativeKanbanAdapter` in the intended isolated or configured
Hermes environment and pass `tools/operator-control/acceptance.py`'s
`evaluate_acceptance` function to `TaskReconciler`, together with trusted
control and source resolvers. Provider adapters should normalize observations
before this boundary but cannot supply protected control fields. The optional `event_hook` exposes
correction/event envelopes for a future correction-policy implementation; it
does not implement that policy.

The conformance tests use a disposable `HERMES_HOME` and the real native
`hermes kanban` CLI. They do not access live accounts, profiles, schedules, or
notification channels.
