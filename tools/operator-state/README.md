# Operator State

A small optional SQLite reference tool for the working stack described in the Executive Operator Blueprint for Hermes.

It stores no credentials and performs no external actions. It separates current attention from business lifecycle and preserves resumable checkpoints.

`daily_use.py` also provides provider-neutral synthetic calendar and daily-brief
engines. They journal exact intents before dispatch, preserve unknown outcomes,
block blind retries, and expose explicit reconciliation APIs. Supplying an
`OperationStore` path makes that journal atomic and durable across processes.

`voice_profile.py` provides the executable private `VoiceProfileStore`. It
stores authenticated encrypted envelopes in owner-only regular files using an
explicit approved external key provider and atomic directory-FD-relative
replacement. It fails closed without a key, rejects unsafe parent components,
symlinks, and hardlinks, and blocks its high-assurance mode on non-POSIX
platforms. Approved source handles must execute disposal and confirm it by
readback; only hashed durable disposal evidence survives restart. Profiles are
excluded from public export and retention, revocation, and deletion remain
enforced without persisting profile fields or source content in cleartext.

## What it stores

1. Workstreams
2. Commitments
3. Focus stack
4. Completed and remaining steps
5. Resume points
6. Current artifacts
7. Owners, blockers, waiting parties, and approvals
8. Append only activity events

## Quick start

```bash
python3 tools/operator-state/operator_state.py init
python3 tools/operator-state/operator_state.py workstream --id launch --name "Product launch"
python3 tools/operator-state/operator_state.py commitment --id pricing --workstream launch --outcome "Finalize pricing" --owner agent --next-action "Compare the accepted options"
python3 tools/operator-state/operator_state.py checkpoint --commitment pricing --completed '["Collected costs"]' --remaining '["Choose final price","Update proposal"]' --resume-point "Review the three pricing options"
python3 tools/operator-state/operator_state.py focus pricing
python3 tools/operator-state/operator_state.py list --view current
python3 tools/operator-state/operator_state.py validate
```

By default the database lives at `$HERMES_HOME/operations/operator.db`. Override it with `EXECUTIVE_OPERATOR_STATE_DB` or `--db`.

## Views

1. `current` includes focused, active, partial, waiting, and blocked work.
2. `attention` excludes outside waiting.
3. `parked` returns active work not currently receiving attention.
4. `all` includes holds and historical terminal states.

## Safety

1. The database is owner only where the operating system supports Unix permissions.
2. Writes use immediate transactions.
3. Foreign keys and lifecycle checks are enabled.
4. A checkpoint updates only the named commitment.
5. Focusing one commitment parks other focused work without closing it.
6. Terminal and held work cannot be focused accidentally.
7. Events use a hash chain and database triggers block normal update or deletion.
8. Focus positions are unique and validated.
9. `validate` opens the database read-only and rejects the wrong application identity or schema version, altered/missing tables, indexes, triggers, or foreign keys, broken focus invariants, relational errors, and event-chain tampering.
10. Existing database paths are rejected before SQLite opens them when the parent is unsafe or the target is a symlink, nonregular file, wrong-owner file, multi-link file, or non-private file.
11. Initial schema creation, application identity, and schema version are one transaction, so interrupted initialization cannot publish a partial database.

## Backup, export, and restore

```bash
python3 tools/operator-state/operator_state.py backup --output /protected/path/operator-backup.db
python3 tools/operator-state/operator_state.py export --output /protected/path/operator-export.json
python3 tools/operator-state/operator_state.py restore --backup /protected/path/operator-backup.db --yes
```

Restore first validates the candidate read-only, copies it into a private temporary database, fully validates that temporary database read-only, and only then atomically replaces the live path. It creates a pre-restore safety backup when a current database exists and restores that backup if post-replacement verification fails. Store backups outside the public checkout.

The schema declares version `1`. A future incompatible schema must ship a tested migration rather than relying on `CREATE TABLE IF NOT EXISTS`.

## Integration boundary

This CLI is not automatically called by Hermes. The `continuity` skill or another approved plugin must invoke it and pass fresh-session continuity tests before automatic task-stack behavior can be called Verified.

This is a reference implementation, not a replacement for a mature CRM or project system. An installer can replace it while preserving the same state and verification contract.
