-- Version 2 -> 3: drop arbitrary provider JSON and add signed authority records.
CREATE TABLE operations_v3 (
 operation_key TEXT PRIMARY KEY, intent_json TEXT NOT NULL, intent_fingerprint TEXT NOT NULL,
 approval_id TEXT, acceptance_id TEXT, state TEXT NOT NULL CHECK(state IN ('intent-recorded','dispatching','reconciling','completed','failed')),
 effect TEXT CHECK(effect IN ('confirmed-success','confirmed-failure','unknown')), result_json TEXT,
 provider_metadata_json TEXT, provider_receipt_digest TEXT, reconciliation_attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO operations_v3(operation_key,intent_json,intent_fingerprint,approval_id,state,effect,result_json,reconciliation_attempts,created_at,updated_at)
 SELECT operation_key,intent_json,intent_fingerprint,approval_id,state,effect,result_json,reconciliation_attempts,created_at,updated_at FROM operations;
DROP TABLE operations;
ALTER TABLE operations_v3 RENAME TO operations;
CREATE TABLE acceptances (record_id TEXT PRIMARY KEY,record_json TEXT NOT NULL,signature TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE evidence (record_id TEXT PRIMARY KEY,record_json TEXT NOT NULL,signature TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE reviews (record_id TEXT PRIMARY KEY,record_json TEXT NOT NULL,signature TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE policies (record_id TEXT PRIMARY KEY,record_json TEXT NOT NULL,signature TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE exceptions (record_id TEXT PRIMARY KEY,record_json TEXT NOT NULL,signature TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
