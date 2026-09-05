import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "tools" / "operator-state" / "operator_state.py"
SPEC = importlib.util.spec_from_file_location("operator_state", MODULE_PATH)
assert SPEC and SPEC.loader
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def test_interrupted_work_resumes_without_duplicate(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "launch", "Launch")
    operator.upsert_commitment(db, "pricing", "launch", "Finalize pricing", "agent", next_action="Research")
    operator.add_checkpoint(db, "pricing", ["Research"], ["Choose", "Publish"], "Choose from three options", ["report.md"])
    operator.focus(db, "pricing")

    operator.upsert_commitment(db, "urgent", "launch", "Fix urgent issue", "agent", next_action="Inspect")
    operator.focus(db, "urgent")
    assert operator.show(db, "pricing")["status"] == "parked"

    operator.focus(db, "pricing")
    restored = operator.show(db, "pricing")
    assert restored["status"] == "focused"
    assert restored["checkpoint"]["completed_steps"] == ["Research"]
    assert restored["checkpoint"]["remaining_steps"] == ["Choose", "Publish"]
    assert restored["checkpoint"]["resume_point"] == "Choose from three options"
    assert len([row for row in operator.rows(db, "all") if row["id"] == "pricing"]) == 1


def test_partial_child_does_not_close_parent(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    operator.upsert_commitment(db, "item", "work", "Complete outcome", "agent")
    operator.add_checkpoint(db, "item", ["Draft"], ["Approve", "Send"], "Review draft")
    assert operator.show(db, "item")["status"] == "partial"
    assert operator.show(db, "item")["next_action"] == "Review draft"


def test_hold_and_waiting_stay_out_of_attention(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    operator.upsert_commitment(db, "held", "work", "Later", "agent", status="hold")
    operator.upsert_commitment(db, "wait", "work", "Reply", "outside", status="waiting", waiting_party="recipient")
    assert operator.rows(db, "attention") == []
    current = operator.rows(db, "current")
    assert [row["id"] for row in current] == ["wait"]


def test_validate_reports_clean_database(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    operator.upsert_commitment(db, "item", "work", "Outcome", "agent")
    result = operator.validate(db)
    assert result["quick_check"] == "ok"
    assert result["foreign_key_violations"] == []
    assert result["duplicate_active_outcomes"] == []
    assert result["schema_version"] == 1
    assert result["focus_order_valid"] is True
    assert result["event_chain_valid"] is True


def test_done_requires_evidence(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    operator.upsert_commitment(db, "item", "work", "Outcome", "agent")
    try:
        operator.set_status(db, "item", "done")
    except ValueError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("done without evidence should fail")
    operator.set_status(db, "item", "done", evidence="verified output")
    assert operator.show(db, "item")["status"] == "done"


def test_upsert_cannot_bypass_terminal_evidence_and_cleanup(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    for status in ("done", "superseded", "dropped"):
        try:
            operator.upsert_commitment(db, f"item-{status}", "work", "Outcome", "agent", status=status)
        except ValueError as exc:
            assert "set_status" in str(exc)
        else:
            raise AssertionError(f"upsert must not create a terminal commitment: {status}")


def test_event_history_is_append_only(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    con = operator.connect(db)
    try:
        try:
            con.execute("DELETE FROM events")
        except Exception as exc:
            assert "append only" in str(exc)
        else:
            raise AssertionError("event deletion should fail")
    finally:
        con.close()


def test_backup_export_and_restore(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    operator.upsert_commitment(db, "first", "work", "First", "agent")
    backup = tmp_path / "protected" / "operator-backup.db"
    exported = tmp_path / "protected" / "operator-export.json"
    assert operator.backup_database(db, backup)["bytes"] > 0
    assert operator.export_json(db, exported)["sha256"]
    operator.upsert_commitment(db, "second", "work", "Second", "agent")
    operator.restore_database(db, backup, yes=True)
    assert [row["id"] for row in operator.rows(db, "all")] == ["first"]


def test_focus_positions_stay_dense_and_unique(tmp_path):
    db = tmp_path / "operator.db"
    operator.upsert_workstream(db, "work", "Work")
    for item in ("one", "two", "three"):
        operator.upsert_commitment(db, item, "work", item, "agent")
        operator.focus(db, item)
    operator.focus(db, "one")
    assert operator.validate(db)["focus_order_valid"] is True


def test_restore_rejects_empty_sqlite_without_touching_live_database(tmp_path):
    live = tmp_path / "operator.db"
    operator.upsert_workstream(live, "live", "Live")
    before = live.read_bytes()
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    os.chmod(empty, 0o600)

    with pytest.raises(RuntimeError, match="schema|identity"):
        operator.restore_database(live, empty, yes=True)

    assert live.read_bytes() == before
    assert operator.rows(live, "all") == []


def test_restore_rejects_invalid_semantics_before_replacing_live_database(tmp_path):
    live = tmp_path / "operator.db"
    candidate = tmp_path / "candidate.db"
    operator.upsert_workstream(live, "live", "Live")
    operator.upsert_workstream(candidate, "candidate", "Candidate")
    operator.upsert_commitment(live, "live-item", "live", "Live item", "agent")
    con = sqlite3.connect(candidate)
    con.execute("DROP TRIGGER events_no_delete")
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="trigger"):
        operator.restore_database(live, candidate, yes=True)

    assert operator.show(live, "live-item")["outcome"] == "Live item"


def test_existing_database_safety_checks_run_before_sqlite_open(tmp_path):
    real = tmp_path / "real.db"
    real.write_bytes(b"not sqlite")
    link = tmp_path / "link.db"
    link.symlink_to(real)
    hard = tmp_path / "hard.db"
    os.link(real, hard)

    with pytest.raises(PermissionError):
        operator.connect(link)
    with pytest.raises(PermissionError, match="link"):
        operator.connect(hard)


@pytest.mark.skipif(os.name != "posix", reason="Unix ownership/mode safety")
def test_unsafe_existing_parent_is_rejected_not_repaired(tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o777)
    os.chmod(parent, 0o777)

    with pytest.raises(PermissionError, match="directory"):
        operator.connect(parent / "operator.db")

    assert parent.stat().st_mode & 0o077


def test_schema_initialization_is_atomic_on_interruption(tmp_path, monkeypatch):
    db = tmp_path / "operator.db"
    monkeypatch.setattr(operator, "SCHEMA", operator.SCHEMA + "\nTHIS IS NOT SQL;")

    with pytest.raises(sqlite3.DatabaseError):
        operator.connect(db)

    con = sqlite3.connect(db)
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0
        assert con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    finally:
        con.close()


def test_empty_database_left_by_failed_first_init_can_recover(tmp_path, monkeypatch):
    db = tmp_path / "operator.db"
    original = operator.SCHEMA
    monkeypatch.setattr(operator, "SCHEMA", original + "\nTHIS IS NOT SQL;")
    with pytest.raises(sqlite3.DatabaseError):
        operator.connect(db)

    monkeypatch.setattr(operator, "SCHEMA", original)
    operator.connect(db).close()
    assert operator.validate(db)["schema_version"] == operator.SCHEMA_VERSION


def test_restore_rolls_back_if_post_replace_verification_fails(tmp_path, monkeypatch):
    live = tmp_path / "operator.db"
    candidate = tmp_path / "candidate.db"
    operator.upsert_workstream(live, "live", "Live")
    operator.upsert_workstream(candidate, "candidate", "Candidate")
    operator.upsert_commitment(live, "live-item", "live", "Live item", "agent")
    real_validate = operator._validate_database_readonly
    calls = 0

    def fail_after_replace(path):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("simulated post-replace interruption")
        return real_validate(path)

    monkeypatch.setattr(operator, "_validate_database_readonly", fail_after_replace)
    with pytest.raises(RuntimeError, match="post-replace"):
        operator.restore_database(live, candidate, yes=True)

    assert operator.show(live, "live-item")["outcome"] == "Live item"
