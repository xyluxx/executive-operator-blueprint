-- Version 3 -> 4: broker-owned immutable policy authority.
CREATE TABLE policy_authority_versions (
 policy_id TEXT PRIMARY KEY, version INTEGER NOT NULL UNIQUE, digest TEXT NOT NULL UNIQUE,
 record_json TEXT NOT NULL, signature TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO control_state(key,value) VALUES('current_policy_id','');
