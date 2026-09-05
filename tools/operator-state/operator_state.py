#!/usr/bin/env python3
"""Optional structured migration store for the Executive Operator Blueprint."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import stat
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

CURRENT = {"focused", "active", "parked", "waiting", "hold", "blocked", "partial"}
TERMINAL = {"done", "superseded", "dropped"}
STATUSES = CURRENT | TERMINAL
WORKSTREAM_STATUSES = {"active", "hold", "done", "dropped"}
SCHEMA_VERSION = 1
APPLICATION_ID = 0x4F505354  # "OPST"
REQUIRED_TABLES = {"workstreams", "commitments", "checkpoints", "focus_stack", "events"}
REQUIRED_INDEXES = {"idx_commitments_status", "idx_checkpoints_commitment"}
REQUIRED_TRIGGERS = {"events_no_update", "events_no_delete"}
REQUIRED_COLUMNS = {
    "workstreams": {"id", "name", "status", "source", "created_at", "updated_at"},
    "commitments": {"id", "workstream_id", "outcome", "owner", "status", "next_action", "blocker", "waiting_party", "approval_required", "current_artifact", "source", "created_at", "updated_at"},
    "checkpoints": {"id", "commitment_id", "created_at", "completed_steps", "remaining_steps", "resume_point", "evidence", "source"},
    "focus_stack": {"commitment_id", "position", "focused_at"},
    "events": {"id", "event_type", "entity_type", "entity_id", "occurred_at", "summary", "evidence", "previous_hash", "event_hash"},
}

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS workstreams (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','hold','done','dropped')),
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commitments (
  id TEXT PRIMARY KEY,
  workstream_id TEXT NOT NULL REFERENCES workstreams(id),
  outcome TEXT NOT NULL,
  owner TEXT NOT NULL,
  status TEXT NOT NULL,
  next_action TEXT,
  blocker TEXT,
  waiting_party TEXT,
  approval_required INTEGER NOT NULL DEFAULT 0,
  current_artifact TEXT,
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(status IN ('focused','active','parked','waiting','hold','blocked','partial','done','superseded','dropped'))
);
CREATE TABLE IF NOT EXISTS checkpoints (
  id TEXT PRIMARY KEY,
  commitment_id TEXT NOT NULL REFERENCES commitments(id),
  created_at TEXT NOT NULL,
  completed_steps TEXT NOT NULL,
  remaining_steps TEXT NOT NULL,
  resume_point TEXT NOT NULL,
  evidence TEXT NOT NULL,
  source TEXT
);
CREATE TABLE IF NOT EXISTS focus_stack (
  commitment_id TEXT PRIMARY KEY REFERENCES commitments(id),
  position INTEGER NOT NULL UNIQUE,
  focused_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  summary TEXT NOT NULL,
  evidence TEXT,
  previous_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_checkpoints_commitment ON checkpoints(commitment_id, created_at);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_db() -> Path:
    home = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes")))
    return Path(os.getenv("EXECUTIVE_OPERATOR_STATE_DB", str(home / "operations" / "operator.db")))


def secure_directory(path):
    path = Path(path)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise PermissionError(f"refusing unsafe directory: {path}")
        if os.name == "posix" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise PermissionError(f"directory is not private or owner-controlled: {path}")
        return
    path.mkdir(parents=True, mode=0o700)
    os.chmod(path, 0o700)


def secure_file(path):
    path = Path(path)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PermissionError(f"refusing unsafe file: {path}")
    if os.name == "posix":
        if info.st_uid != os.geteuid():
            raise PermissionError(f"file has wrong owner: {path}")
        if info.st_nlink != 1:
            raise PermissionError(f"refusing multi-link file: {path}")
        if info.st_mode & 0o077:
            raise PermissionError(f"file is not private: {path}")


def _create_private_file(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    secure_directory(path.parent)
    existed = path.exists() or path.is_symlink()
    if existed:
        secure_file(path)
    else:
        _create_private_file(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        application_id = con.execute("PRAGMA application_id").fetchone()[0]
        user_tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        existing = "workstreams" in user_tables
        if version == 0 and application_id == 0 and not user_tables:
            try:
                con.executescript(
                    "BEGIN IMMEDIATE;\n" + SCHEMA +
                    f"\nPRAGMA application_id={APPLICATION_ID};\nPRAGMA user_version={SCHEMA_VERSION};\nCOMMIT;"
                )
            except Exception:
                if con.in_transaction:
                    con.rollback()
                raise
        else:
            if version == 0 and existing:
                raise RuntimeError("unversioned operator database requires explicit migration")
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported operator schema version: {version}")
            if con.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise RuntimeError("database application identity mismatch")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
    except Exception:
        con.close()
        raise
    for suffix in ("-wal", "-shm"):
        related = Path(str(path) + suffix)
        if related.exists():
            secure_file(related)
    return con


@contextmanager
def transaction(path: Path | str):
    con = connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def event(con, kind: str, entity_type: str, entity_id: str, summary: str, evidence=None):
    occurred = now()
    previous = con.execute("SELECT event_hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
    previous_hash = previous["event_hash"] if previous else "0" * 64
    payload = json.dumps(
        {"event_type": kind, "entity_type": entity_type, "entity_id": entity_id,
         "occurred_at": occurred, "summary": summary, "evidence": evidence},
        sort_keys=True, separators=(",", ":"),
    )
    event_hash = hashlib.sha256((previous_hash + payload).encode()).hexdigest()
    con.execute(
        """INSERT INTO events(
           event_type,entity_type,entity_id,occurred_at,summary,evidence,previous_hash,event_hash)
           VALUES(?,?,?,?,?,?,?,?)""",
        (kind, entity_type, entity_id, occurred, summary, evidence, previous_hash, event_hash),
    )


def upsert_workstream(path, wid, name, status="active", source=None):
    if status not in WORKSTREAM_STATUSES:
        raise ValueError(f"invalid workstream status: {status}")
    stamp = now()
    with transaction(path) as con:
        con.execute(
            """INSERT INTO workstreams(id,name,status,source,created_at,updated_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
               name=excluded.name,status=excluded.status,
               source=COALESCE(excluded.source,workstreams.source),updated_at=excluded.updated_at""",
            (wid, name, status, source, stamp, stamp),
        )
        event(con, "workstream_upserted", "workstream", wid, name, source)


def upsert_commitment(path, cid, workstream, outcome, owner, status="active", next_action=None,
                      blocker=None, waiting_party=None, approval_required=False,
                      current_artifact=None, source=None):
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    if status in TERMINAL:
        raise ValueError("terminal commitment status must use set_status so evidence and focus cleanup are enforced")
    stamp = now()
    with transaction(path) as con:
        if not con.execute("SELECT 1 FROM workstreams WHERE id=?", (workstream,)).fetchone():
            raise KeyError(f"unknown workstream: {workstream}")
        existing = con.execute("SELECT created_at FROM commitments WHERE id=?", (cid,)).fetchone()
        created = existing["created_at"] if existing else stamp
        con.execute(
            """INSERT INTO commitments(
               id,workstream_id,outcome,owner,status,next_action,blocker,waiting_party,
               approval_required,current_artifact,source,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
               workstream_id=excluded.workstream_id,outcome=excluded.outcome,owner=excluded.owner,
               status=excluded.status,next_action=excluded.next_action,blocker=excluded.blocker,
               waiting_party=excluded.waiting_party,approval_required=excluded.approval_required,
               current_artifact=excluded.current_artifact,source=COALESCE(excluded.source,commitments.source),
               updated_at=excluded.updated_at""",
            (cid, workstream, outcome, owner, status, next_action, blocker, waiting_party,
             int(approval_required), current_artifact, source, created, stamp),
        )
        event(con, "commitment_upserted", "commitment", cid, outcome, source)


def add_checkpoint(path, cid, completed, remaining, resume_point, evidence=None, source=None):
    if not isinstance(completed, list) or not isinstance(remaining, list):
        raise TypeError("completed and remaining must be JSON arrays")
    if completed and not remaining and not evidence:
        raise ValueError("completion requires evidence")
    checkpoint_id = str(uuid.uuid4())
    stamp = now()
    with transaction(path) as con:
        row = con.execute("SELECT status FROM commitments WHERE id=?", (cid,)).fetchone()
        if not row:
            raise KeyError(cid)
        con.execute(
            "INSERT INTO checkpoints VALUES(?,?,?,?,?,?,?,?)",
            (checkpoint_id, cid, stamp, json.dumps(completed), json.dumps(remaining),
             resume_point, json.dumps(evidence or []), source),
        )
        status = row["status"]
        if status not in TERMINAL and status != "hold":
            status = "partial" if completed and remaining else ("done" if completed and not remaining else status)
        con.execute(
            "UPDATE commitments SET status=?,next_action=?,updated_at=? WHERE id=?",
            (status, resume_point if remaining else None, stamp, cid),
        )
        event(con, "checkpoint_saved", "commitment", cid, resume_point, source)
    return checkpoint_id


def focus(path, cid):
    stamp = now()
    with transaction(path) as con:
        row = con.execute("SELECT status FROM commitments WHERE id=?", (cid,)).fetchone()
        if not row:
            raise KeyError(cid)
        if row["status"] in TERMINAL | {"hold", "waiting", "blocked"}:
            raise ValueError(f"cannot focus commitment in state {row['status']}")
        current = [item["commitment_id"] for item in con.execute(
            "SELECT commitment_id FROM focus_stack ORDER BY position"
        ).fetchall() if item["commitment_id"] != cid]
        con.execute("DELETE FROM focus_stack WHERE commitment_id=?", (cid,))
        con.execute("UPDATE focus_stack SET position=-position-1000")
        for index, commitment_id in enumerate(current, start=2):
            con.execute("UPDATE focus_stack SET position=? WHERE commitment_id=?", (index, commitment_id))
            con.execute(
                "UPDATE commitments SET status='parked',updated_at=? WHERE id=? AND status IN ('focused','active','partial')",
                (stamp, commitment_id),
            )
        con.execute(
            "INSERT INTO focus_stack(commitment_id,position,focused_at) VALUES(?,1,?)",
            (cid, stamp),
        )
        con.execute("UPDATE commitments SET status='focused',updated_at=? WHERE id=?", (stamp, cid))
        event(con, "focused", "commitment", cid, "Moved to current focus")


def normalize_focus(con):
    ids = [row["commitment_id"] for row in con.execute(
        "SELECT commitment_id FROM focus_stack ORDER BY position"
    ).fetchall()]
    con.execute("UPDATE focus_stack SET position=-position-2000")
    for index, commitment_id in enumerate(ids, start=1):
        con.execute("UPDATE focus_stack SET position=? WHERE commitment_id=?", (index, commitment_id))
    if ids:
        con.execute("UPDATE commitments SET status='focused',updated_at=? WHERE id=? AND status='parked'", (now(), ids[0]))


def set_status(path, cid, status, next_action=None, blocker=None, waiting_party=None, evidence=None):
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    if status == "done" and not evidence:
        raise ValueError("done requires evidence")
    if status == "done":
        next_action = None
    stamp = now()
    with transaction(path) as con:
        if not con.execute("SELECT 1 FROM commitments WHERE id=?", (cid,)).fetchone():
            raise KeyError(cid)
        con.execute(
            "UPDATE commitments SET status=?,next_action=?,blocker=?,waiting_party=?,updated_at=? WHERE id=?",
            (status, next_action, blocker, waiting_party, stamp, cid),
        )
        if status != "focused":
            con.execute("DELETE FROM focus_stack WHERE commitment_id=?", (cid,))
            normalize_focus(con)
        event(con, "status_changed", "commitment", cid, status, evidence)


def rows(path, view="current"):
    con = connect(path)
    try:
        where = ""
        params = ()
        if view == "current":
            where = "WHERE c.status IN ('focused','active','partial','waiting','blocked')"
        elif view == "attention":
            where = "WHERE c.status IN ('focused','active','partial','blocked')"
        elif view == "parked":
            where = "WHERE c.status='parked'"
        elif view == "all":
            pass
        else:
            raise ValueError(view)
        result = con.execute(
            f"""SELECT c.*,w.name AS workstream_name,
                (SELECT resume_point FROM checkpoints p WHERE p.commitment_id=c.id ORDER BY p.created_at DESC LIMIT 1) AS resume_point
                FROM commitments c JOIN workstreams w ON w.id=c.workstream_id {where}
                ORDER BY CASE c.status WHEN 'focused' THEN 0 WHEN 'blocked' THEN 1 WHEN 'active' THEN 2 WHEN 'partial' THEN 3 WHEN 'waiting' THEN 4 ELSE 5 END,c.updated_at DESC""",  # nosec B608
            params,
        ).fetchall()
        return [dict(row) for row in result]
    finally:
        con.close()


def show(path, cid):
    con = connect(path)
    try:
        commitment = con.execute("SELECT * FROM commitments WHERE id=?", (cid,)).fetchone()
        if not commitment:
            raise KeyError(cid)
        checkpoint = con.execute(
            "SELECT * FROM checkpoints WHERE commitment_id=? ORDER BY created_at DESC LIMIT 1", (cid,)
        ).fetchone()
        result = dict(commitment)
        if checkpoint:
            result["checkpoint"] = dict(checkpoint)
            for field in ("completed_steps", "remaining_steps", "evidence"):
                result["checkpoint"][field] = json.loads(result["checkpoint"][field])
        return result
    finally:
        con.close()


def _readonly_connection(path):
    path = Path(path)
    secure_directory(path.parent)
    secure_file(path)
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _validate_database_readonly(path):
    con = _readonly_connection(path)
    try:
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            raise RuntimeError(f"database integrity failed: {quick}")
        application_id = con.execute("PRAGMA application_id").fetchone()[0]
        if application_id != APPLICATION_ID:
            raise RuntimeError("database application identity mismatch")
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise RuntimeError(f"unsupported operator schema version: {version}")
        objects = {}
        for row in con.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','index','trigger')"):
            objects.setdefault(row["type"], set()).add(row["name"])
        for kind, required in (("table", REQUIRED_TABLES), ("index", REQUIRED_INDEXES), ("trigger", REQUIRED_TRIGGERS)):
            missing = required - objects.get(kind, set())
            if missing:
                raise RuntimeError(f"missing required {kind}(s): {sorted(missing)}")
        reference = sqlite3.connect(":memory:")
        try:
            reference.executescript(SCHEMA)
            expected_sql = {
                (row[0], row[1]): " ".join(row[2].lower().split())
                for row in reference.execute(
                    "SELECT type,name,sql FROM sqlite_master WHERE name IN (?,?,?,?,?,?,?,?,?) AND sql IS NOT NULL",
                    tuple(sorted(REQUIRED_TABLES | REQUIRED_INDEXES | REQUIRED_TRIGGERS)),
                )
            }
        finally:
            reference.close()
        actual_sql = {
            (row[0], row[1]): " ".join(row[2].lower().split())
            for row in con.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE name IN (?,?,?,?,?,?,?,?,?) AND sql IS NOT NULL",
                tuple(sorted(REQUIRED_TABLES | REQUIRED_INDEXES | REQUIRED_TRIGGERS)),
            )
        }
        if actual_sql != expected_sql:
            raise RuntimeError("exact schema definition mismatch")
        for table, expected in REQUIRED_COLUMNS.items():
            actual = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
            if actual != expected:
                raise RuntimeError(f"schema mismatch for table {table}")
        foreign_keys = {
            "commitments": {("workstreams", "workstream_id", "id")},
            "checkpoints": {("commitments", "commitment_id", "id")},
            "focus_stack": {("commitments", "commitment_id", "id")},
        }
        for table, expected in foreign_keys.items():
            actual = {(row["table"], row["from"], row["to"]) for row in con.execute(f"PRAGMA foreign_key_list({table})")}
            if actual != expected:
                raise RuntimeError(f"foreign key schema mismatch for {table}")
        fk = [tuple(row) for row in con.execute("PRAGMA foreign_key_check")]
        if fk:
            raise RuntimeError(f"foreign key violations: {fk}")
        duplicates = con.execute(
            "SELECT outcome,workstream_id,COUNT(*) FROM commitments WHERE status IN ('focused','active','parked','waiting','hold','blocked','partial') GROUP BY outcome,workstream_id HAVING COUNT(*)>1"
        ).fetchall()
        positions = [row[0] for row in con.execute("SELECT position FROM focus_stack ORDER BY position")]
        focused = [row[0] for row in con.execute("SELECT id FROM commitments WHERE status='focused'")]
        top = con.execute("SELECT commitment_id FROM focus_stack WHERE position=1").fetchone()
        focus_ok = positions == list(range(1, len(positions) + 1))
        focus_ok = focus_ok and focused == ([] if top is None else [top[0]])
        stack_states = [(row[0], row[1]) for row in con.execute(
            "SELECT f.position,c.status FROM focus_stack f JOIN commitments c ON c.id=f.commitment_id ORDER BY f.position"
        )]
        focus_ok = focus_ok and all(
            status == ("focused" if position == 1 else "parked")
            for position, status in stack_states
        )
        previous = "0" * 64
        event_chain_ok = True
        for row in con.execute("SELECT * FROM events ORDER BY id"):
            payload = json.dumps(
                {"event_type": row["event_type"], "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                 "occurred_at": row["occurred_at"], "summary": row["summary"], "evidence": row["evidence"]},
                sort_keys=True, separators=(",", ":"),
            )
            expected = hashlib.sha256((previous + payload).encode()).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                event_chain_ok = False
                break
            previous = row["event_hash"]
        if not focus_ok:
            raise RuntimeError("focus invariant failed")
        if not event_chain_ok:
            raise RuntimeError("event chain validation failed")
        return {
            "quick_check": quick,
            "foreign_key_violations": fk,
            "duplicate_active_outcomes": [tuple(x) for x in duplicates],
            "schema_version": version,
            "focus_order_valid": focus_ok,
            "event_chain_valid": event_chain_ok,
        }
    finally:
        con.close()


def validate(path):
    return _validate_database_readonly(path)


def backup_database(path, output):
    path = Path(path); output = Path(output)
    secure_directory(output.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        source = connect(path)
        destination = sqlite3.connect(tmp)
        try:
            source.backup(destination)
        finally:
            destination.close(); source.close()
        check = sqlite3.connect(tmp)
        try:
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("backup integrity failed")
        finally:
            check.close()
        secure_file(tmp)
        os.replace(tmp, output)
        secure_file(output)
        return {"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "bytes": output.stat().st_size}
    finally:
        tmp.unlink(missing_ok=True)


def export_json(path, output):
    con = connect(path)
    try:
        data = {
            "schema_version": con.execute("PRAGMA user_version").fetchone()[0],
            "exported_at": now(),
            "workstreams": [dict(row) for row in con.execute("SELECT * FROM workstreams ORDER BY id")],
            "commitments": [dict(row) for row in con.execute("SELECT * FROM commitments ORDER BY id")],
            "checkpoints": [dict(row) for row in con.execute("SELECT * FROM checkpoints ORDER BY created_at")],
            "focus_stack": [dict(row) for row in con.execute("SELECT * FROM focus_stack ORDER BY position")],
            "events": [dict(row) for row in con.execute("SELECT * FROM events ORDER BY id")],
        }
    finally:
        con.close()
    output = Path(output)
    secure_directory(output.parent)
    tmp = output.with_name(f".{output.name}.{secrets.token_hex(6)}.tmp")
    _create_private_file(tmp)
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    secure_file(tmp)
    os.replace(tmp, output)
    secure_file(output)
    return {"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def restore_database(path, backup, yes=False):
    if not yes:
        raise RuntimeError("restore requires --yes")
    path = Path(path); backup = Path(backup)
    _validate_database_readonly(backup)
    secure_directory(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.restore.", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        source = _readonly_connection(backup)
        destination = sqlite3.connect(tmp)
        try:
            source.backup(destination)
        finally:
            source.close(); destination.close()
        _validate_database_readonly(tmp)
        safety = backup_database(path, path.with_name(f"{path.name}.pre-restore.db")) if path.exists() else None
        os.replace(tmp, path)
        try:
            _validate_database_readonly(path)
        except Exception:
            if safety:
                rollback = path.with_name(f".{path.name}.rollback.{secrets.token_hex(6)}")
                try:
                    shutil.copyfile(safety["path"], rollback)
                    os.chmod(rollback, 0o600)
                    _validate_database_readonly(rollback)
                    os.replace(rollback, path)
                finally:
                    rollback.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
            raise
        return {"restored": str(path), "safety_backup": safety}
    finally:
        tmp.unlink(missing_ok=True)


def json_arg(value):
    data = json.loads(value)
    if not isinstance(data, list):
        raise argparse.ArgumentTypeError("must be a JSON array")
    return data


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(default_db()))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    ws = sub.add_parser("workstream")
    ws.add_argument("--id", required=True); ws.add_argument("--name", required=True)
    ws.add_argument("--status", default="active", choices=sorted(WORKSTREAM_STATUSES)); ws.add_argument("--source")
    task = sub.add_parser("commitment")
    task.add_argument("--id", required=True); task.add_argument("--workstream", required=True)
    task.add_argument("--outcome", required=True); task.add_argument("--owner", required=True)
    task.add_argument("--status", default="active", choices=sorted(STATUSES))
    task.add_argument("--next-action"); task.add_argument("--blocker"); task.add_argument("--waiting-party")
    task.add_argument("--approval-required", action="store_true"); task.add_argument("--current-artifact"); task.add_argument("--source")
    cp = sub.add_parser("checkpoint")
    cp.add_argument("--commitment", required=True); cp.add_argument("--completed", type=json_arg, default=[])
    cp.add_argument("--remaining", type=json_arg, default=[]); cp.add_argument("--resume-point", required=True)
    cp.add_argument("--evidence", type=json_arg, default=[]); cp.add_argument("--source")
    fc = sub.add_parser("focus"); fc.add_argument("commitment")
    st = sub.add_parser("status"); st.add_argument("commitment"); st.add_argument("status", choices=sorted(STATUSES))
    st.add_argument("--next-action"); st.add_argument("--blocker"); st.add_argument("--waiting-party"); st.add_argument("--evidence")
    ls = sub.add_parser("list"); ls.add_argument("--view", choices=["current","attention","parked","all"], default="current")
    sh = sub.add_parser("show"); sh.add_argument("commitment")
    sub.add_parser("validate")
    backup = sub.add_parser("backup"); backup.add_argument("--output", required=True)
    export = sub.add_parser("export"); export.add_argument("--output", required=True)
    restore = sub.add_parser("restore"); restore.add_argument("--backup", required=True); restore.add_argument("--yes", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    path = Path(args.db)
    if args.command == "init":
        connect(path).close(); result = {"initialized": str(path)}
    elif args.command == "workstream":
        upsert_workstream(path, args.id, args.name, args.status, args.source); result = {"workstream": args.id}
    elif args.command == "commitment":
        upsert_commitment(path, args.id, args.workstream, args.outcome, args.owner, args.status, args.next_action,
                          args.blocker, args.waiting_party, args.approval_required, args.current_artifact, args.source)
        result = {"commitment": args.id}
    elif args.command == "checkpoint":
        result = {"checkpoint": add_checkpoint(path, args.commitment, args.completed, args.remaining, args.resume_point, args.evidence, args.source)}
    elif args.command == "focus":
        focus(path, args.commitment); result = {"focused": args.commitment}
    elif args.command == "status":
        set_status(path, args.commitment, args.status, args.next_action, args.blocker, args.waiting_party, args.evidence); result = {"status": args.status}
    elif args.command == "list":
        result = rows(path, args.view)
    elif args.command == "show":
        result = show(path, args.commitment)
    elif args.command == "backup":
        result = backup_database(path, args.output)
    elif args.command == "export":
        result = export_json(path, args.output)
    elif args.command == "restore":
        result = restore_database(path, args.backup, args.yes)
    else:
        result = validate(path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
