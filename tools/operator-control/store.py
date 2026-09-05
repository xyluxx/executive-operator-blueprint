"""Protected SQLite state for the action broker; never task truth."""
from __future__ import annotations
import os, shutil, sqlite3, stat, tempfile
from pathlib import Path

MIGRATIONS=Path(__file__).with_name("migrations")
SCHEMA_VERSION=4

def _private_parent(path:Path)->None:
    # Refuse every existing symlink component, not only the leaf directory.
    probe = path.absolute()
    for ancestor in (probe, *probe.parents):
        if ancestor.exists() and stat.S_ISLNK(os.lstat(ancestor).st_mode):
            raise PermissionError("store parent path cannot contain symlinks")
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    info=os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode): raise PermissionError("store parent must be a real directory")
    if os.name=="posix" and (info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700): raise PermissionError("operator-control store parent must be owned mode 0700")

def _validate_file(path:Path)->None:
    info=os.lstat(path)
    if not stat.S_ISREG(info.st_mode): raise PermissionError("operator-control store must be a regular file")
    if info.st_nlink!=1: raise PermissionError("operator-control store hardlink count must be one")
    if os.name=="posix" and (info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600): raise PermissionError("operator-control store must be owned mode 0600")

def connect(path, *, for_operation=False)->sqlite3.Connection:
    path=Path(path); _private_parent(path.parent)
    if path.exists() or path.is_symlink(): _validate_file(path)
    flags=os.O_RDWR|os.O_CREAT
    if hasattr(os,"O_NOFOLLOW"): flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600); os.close(fd); os.chmod(path,0o600); _validate_file(path)
    con=sqlite3.connect(path,isolation_level=None); con.row_factory=sqlite3.Row
    try:
        version=con.execute("PRAGMA user_version").fetchone()[0]
        if version>SCHEMA_VERSION: raise RuntimeError(f"unsupported operator-control schema version: {version}")
        if version==0:
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='operations'").fetchone(): raise RuntimeError("unversioned operator-control store requires explicit migration")
            con.executescript((MIGRATIONS/"001-initial.sql").read_text())
            con.execute("PRAGMA journal_mode=WAL")
        elif version<SCHEMA_VERSION: raise RuntimeError("schema migration requires migrate_atomic")
        if for_operation and con.execute("SELECT value FROM control_state WHERE key='operations_blocked'").fetchone()[0]=="1": raise RuntimeError("operations blocked for rollback")
        con.execute("PRAGMA synchronous=FULL"); return con
    except Exception: con.close(); raise

def backup_before_migration(path,backup_dir):
    source=Path(path); _validate_file(source); destination_dir=Path(backup_dir); _private_parent(destination_dir)
    c=sqlite3.connect(source); version=c.execute("PRAGMA user_version").fetchone()[0]; c.close()
    destination=destination_dir/f"{source.name}.v{version}.bak"
    if destination.exists(): raise FileExistsError(destination)
    shutil.copy2(source,destination); os.chmod(destination,0o600); _validate_file(destination)
    check=sqlite3.connect(destination)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise RuntimeError("backup integrity check failed")
    finally: check.close()
    return destination

def restore_backup(backup,destination):
    source=Path(backup); _validate_file(source); target=Path(destination); _private_parent(target.parent)
    if target.exists() or target.is_symlink(): raise FileExistsError(target)
    shutil.copy2(source,target); os.chmod(target,0o600); _validate_file(target); return target

def migrate_atomic(path,backup_dir,migration_sql,target_version):
    path=Path(path); backup=backup_before_migration(path,backup_dir)
    try:
        con=sqlite3.connect(path,isolation_level=None); con.executescript("BEGIN IMMEDIATE;\n"+migration_sql+f"\nPRAGMA user_version={int(target_version)};\nCOMMIT;"); con.close()
        check=sqlite3.connect(path)
        if check.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise RuntimeError("migration integrity check failed")
        check.close()
    except Exception:
        try: path.unlink()
        finally: restore_backup(backup,path)
        raise
    return backup

def prepare_rollback(path):
    con=connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        pending=con.execute("SELECT operation_key FROM operations WHERE effect='unknown' OR state IN ('dispatching','reconciling')").fetchall()
        if pending: con.execute("ROLLBACK"); raise RuntimeError("rollback blocked by pending or unknown external effects")
        con.execute("UPDATE control_state SET value='1' WHERE key='operations_blocked'"); con.execute("COMMIT")
        return {"operations_blocked":True,"pending":0}
    finally: con.close()


def cancel_task_authority(path, task_id):
    """Revoke approvals referencing a Kanban task; task truth stays in Kanban."""
    import json
    con=connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        rows=con.execute("SELECT approval_id,record_json FROM approvals WHERE revoked=0").fetchall()
        ids=[row["approval_id"] for row in rows if json.loads(row["record_json"]).get("task_id")==task_id]
        for approval_id in ids: con.execute("UPDATE approvals SET revoked=1 WHERE approval_id=?",(approval_id,))
        con.execute("COMMIT"); return len(ids)
    except Exception:
        con.execute("ROLLBACK"); raise
    finally: con.close()


def unknown_effects_for_task(path, task_id):
    """Return operation keys needing reconciliation after cancellation."""
    import json
    con=connect(path)
    try:
        rows=con.execute("SELECT operation_key,intent_json FROM operations WHERE effect='unknown' OR state IN ('dispatching','reconciling') ORDER BY created_at,operation_key").fetchall()
        return [row["operation_key"] for row in rows if json.loads(row["intent_json"]).get("task_id")==task_id]
    finally: con.close()
