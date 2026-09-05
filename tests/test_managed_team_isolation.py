import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load_managed():
    spec = importlib.util.spec_from_file_location("operator_control_managed_isolation", ROOT / "plugins/operator-control/managed.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def envelope(**changes):
    value = {"board": "/boards/a.db", "task_id": "t1", "run_id": "r1", "claim_lock": "c1",
             "task_version": 3, "actor": "profile:worker-a", "profile": "worker-a", "client": "client-a",
             "workspace": "/work/a", "credential_scope": "credential:a", "target": "provider:a/item:1"}
    value.update(changes); return value


def snapshot(**changes):
    value = {"board": "/boards/a.db", "task_id": "t1", "status": "running", "version": 3,
             "current_run_id": "r1", "claim_lock": "c1", "assignee": "profile:worker-a", "profile": "worker-a",
             "client": "client-a", "workspace": "/work/a", "credential_scopes": ["credential:a"], "cancelled": False}
    value.update(changes); return value


@pytest.mark.parametrize("field,bad", [("board", "/boards/b.db"), ("client", "client-b"),
                                      ("profile", "worker-b"), ("workspace", "/work/b"),
                                      ("credential_scope", "credential:b")])
def test_cross_boundary_envelope_is_rejected(field, bad):
    managed = load_managed(); live = snapshot()
    gate = managed.ManagedGate(lambda board, task: live)
    with pytest.raises(managed.ManagedDenied, match=field.replace("_", " ")):
        gate.check_current(envelope(**{field: bad}))


def test_reader_is_called_immediately_for_every_protected_check():
    managed = load_managed(); calls = []
    gate = managed.ManagedGate(lambda board, task: calls.append((board, task)) or snapshot())
    gate.check_current(envelope()); gate.check_current(envelope())
    assert calls == [("/boards/a.db", "t1"), ("/boards/a.db", "t1")]


def test_retirement_executes_all_controls_and_main_operator_resumes(tmp_path):
    managed = load_managed(); calls = []
    retirement = {"specialist_id": "bot:r", "main_operator": "profile:main", "schedule_ids": ["s1", "s2"],
                  "credential_references": ["k1"], "task_ids": ["t1"], "evidence_references": ["e1"]}
    result = managed.retire_specialist(retirement,
        disable_schedule=lambda x: calls.append(("schedule", x)), revoke_credential=lambda x: calls.append(("credential", x)),
        transfer_task=lambda task, owner: calls.append(("transfer", task, owner)), preserve_evidence=lambda x: calls.append(("evidence", x)),
        resume_test=lambda owner, tasks: calls.append(("resume", owner, tuple(tasks))) or True,
        plan_path=tmp_path/"retirement.json", schedule_disabled=lambda _: True,
        task_owner=lambda _: "profile:main", credential_revoked=lambda _: True,
        evidence_preserved=lambda _: True, enable_schedule=lambda _: None,
        restore_task=lambda *_: None, restore_credential=lambda _: None,
        credential_restored=lambda _: True, credential_preflight=lambda _: True,
        credential_restore_preflight=lambda _: True,
        disable_credential=lambda _: None, credential_disabled=lambda _: True)
    assert result["retired"] and result["resumable"]
    assert calls == [("schedule", "s1"), ("schedule", "s2"), ("transfer", "t1", "profile:main"),
                     ("evidence", "e1"), ("resume", "profile:main", ("t1",)), ("credential", "k1")]
    assert (tmp_path/"retirement.json").exists()


def test_partial_retirement_compensates_reversible_steps_and_persists_reconciliation(tmp_path):
    managed = load_managed(); calls=[]; plan=tmp_path/"retirement.json"
    contract={"specialist_id":"bot:r","main_operator":"profile:main","schedule_ids":["s1"],
              "credential_references":["k1"],"task_ids":["t1"],"evidence_references":["e1"]}
    with pytest.raises(managed.ManagedDenied,match="partial retirement"):
        managed.retire_specialist(contract, plan_path=plan,
            disable_schedule=lambda x:calls.append(("off",x)), schedule_disabled=lambda _:True,
            enable_schedule=lambda x:calls.append(("on",x)), revoke_credential=lambda _:None,
            credential_revoked=lambda _:False, transfer_task=lambda t,o:(_ for _ in ()).throw(RuntimeError("down")),
            task_owner=lambda _:"bot:r", restore_task=lambda t,o:calls.append(("restore",t,o)),
            preserve_evidence=lambda _:None, evidence_preserved=lambda _:True, resume_test=lambda *_:True,
            restore_credential=lambda _:None, credential_restored=lambda _:True,
            credential_preflight=lambda _:True, credential_restore_preflight=lambda _:True,
            disable_credential=lambda _:None, credential_disabled=lambda _:True)
    state=__import__("json").loads(plan.read_text())
    assert state["status"]=="reconciliation-required" and calls==[("off","s1"),("on","s1")]
