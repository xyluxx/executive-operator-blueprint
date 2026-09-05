BEGIN IMMEDIATE;
CREATE TABLE operations (
 operation_key TEXT PRIMARY KEY, intent_json TEXT NOT NULL, intent_fingerprint TEXT NOT NULL,
 approval_id TEXT, acceptance_id TEXT, state TEXT NOT NULL CHECK(state IN ('intent-recorded','dispatching','reconciling','completed','failed')),
 effect TEXT CHECK(effect IN ('confirmed-success','confirmed-failure','unknown')), result_json TEXT,
 provider_metadata_json TEXT, provider_receipt_digest TEXT, reconciliation_attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE approvals (approval_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, signature TEXT NOT NULL, authority_type TEXT NOT NULL, scope_version INTEGER NOT NULL DEFAULT 1, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE approvals_used (approval_id TEXT NOT NULL, operation_key TEXT NOT NULL, used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(approval_id,operation_key));
CREATE TABLE acceptances (record_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, signature TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE evidence (record_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, signature TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE reviews (record_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, signature TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE policies (record_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, signature TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE policy_authority_versions (
 policy_id TEXT PRIMARY KEY, version INTEGER NOT NULL UNIQUE, digest TEXT NOT NULL UNIQUE,
 record_json TEXT NOT NULL, signature TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE exceptions (record_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, signature TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE control_state (key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO control_state(key,value) VALUES('operations_blocked','0');
INSERT INTO control_state(key,value) VALUES('current_policy_id','');
CREATE TABLE observations (id INTEGER PRIMARY KEY,record_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
PRAGMA user_version=4;
COMMIT;
