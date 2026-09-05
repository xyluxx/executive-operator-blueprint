import importlib.util
from pathlib import Path
from threading import Barrier, Thread

import pytest

ROOT=Path(__file__).parents[1]


def mod():
    spec=importlib.util.spec_from_file_location("operator_control_managed_edges",ROOT/"plugins/operator-control/managed.py")
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def test_dependency_cycles_rejected_before_dispatch_and_replan():
    m=mod()
    with pytest.raises(m.ManagedDenied,match="cycle"): m.DependencyGraph({"a":["b"],"b":["a"]})
    graph=m.DependencyGraph({"a":[]}); graph.add_dependency("b","a")
    with pytest.raises(m.ManagedDenied,match="cycle"): graph.add_dependency("a","b")


def test_signed_accepted_versioned_upstream_required_and_approval_not_inherited():
    m=mod(); signer=m.AcceptanceSigner(b"k"*32)
    record=signer.sign({"task_id":"up","outcome_id":"o1","artifact_id":"a1","artifact_version":"v2","accepted":True,"signer":"reviewer"})
    m.require_upstreams([{"task_id":"up","artifact_id":"a1","artifact_version":"v2"}],[record],signer.verify)
    with pytest.raises(m.ManagedDenied): m.require_upstreams([{"task_id":"up","artifact_id":"a1","artifact_version":"v3"}],[record],signer.verify)
    assert m.descendant_authority({"approval_id":"parent"})=={}


def test_parent_needs_integrated_acceptance_for_incompatible_children_and_merge_regression():
    m=mod(); children=[{"accepted":True,"interface":"v1"},{"accepted":True,"interface":"v2"}]
    with pytest.raises(m.ManagedDenied,match="integrated"): m.accept_parent(children,None)
    assert m.accept_parent(children,{"accepted":True,"integration_checks":{"compatibility":True,"merge_tests":True}})
    with pytest.raises(m.ManagedDenied,match="merge"):
        m.accept_parent([{"accepted":True,"interface":"v1"}],{"accepted":True,"integration_checks":{"compatibility":True,"merge_tests":False}})


def test_reassignment_preserves_total_budget_deadline_and_repair_history():
    m=mod(); old={"total_budget":100,"spent":31,"deadline":"2026-09-10T00:00:00Z","repair_history":["r1"]}
    new=m.reassign(old,"worker-2")
    assert new|{} == {**old,"assignee":"worker-2"}
    with pytest.raises(m.ManagedDenied): m.validate_reassignment(old,{**new,"spent":0})


def test_concurrent_admission_reserves_verification_budget():
    m=mod(); budget=m.BudgetGuard(total=100,verification_reserve=30); barrier=Barrier(2); admitted=[]
    def attempt():
        barrier.wait(); admitted.append(budget.admit(50))
    ts=[Thread(target=attempt) for _ in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(admitted)==[False,True]
    assert budget.available_for_work==20


def test_bounded_rework_keeps_unaffected_passing_results():
    m=mod(); prior={"a":{"result":"pass","input_versions":{"x":"1"}},"b":{"result":"pass","input_versions":{"y":"1"}}}
    out=m.invalidate_affected(prior,{"x":"2","y":"1"})
    assert "a" not in out and out["b"]==prior["b"]


def test_cancellation_blocks_dispatch_revokes_authority_and_reconciles_unknown():
    m=mod(); calls=[]
    task={"cancelled":True,"issued_effects":[{"operation_key":"o1","effect":"unknown"},{"operation_key":"o2","effect":"confirmed-success"}]}
    with pytest.raises(m.ManagedDenied,match="cancelled"): m.authorize_dispatch(task)
    result=m.cancel_task(task,revoke=lambda: calls.append("revoked"),reconcile=lambda k:calls.append(k) or "confirmed-success")
    assert calls==["revoked","o1"] and result["issued_effects"][0]["effect"]=="confirmed-success"


def test_uncertain_provider_result_blocks_blind_retry():
    m=mod()
    with pytest.raises(m.ManagedDenied,match="unknown"): m.retry_allowed({"effect":"unknown"},attempts=0,max_attempts=3)
    assert m.retry_allowed({"effect":"confirmed-failure"},attempts=1,max_attempts=3)


def test_cancellation_store_revokes_task_approvals_and_lists_unknown_effects(tmp_path):
    import json
    spec=importlib.util.spec_from_file_location("operator_control_store_edges",ROOT/"tools/operator-control/store.py")
    assert spec and spec.loader
    store=importlib.util.module_from_spec(spec); spec.loader.exec_module(store)
    db=tmp_path/"private"/"control.db"; con=store.connect(db)
    intent={"task_id":"t1"}
    con.execute("INSERT INTO approvals(approval_id,record_json,signature,authority_type) VALUES(?,?,?,?)",("a1",json.dumps(intent),"s","one_off"))
    con.execute("INSERT INTO operations(operation_key,intent_json,intent_fingerprint,state,effect) VALUES(?,?,?,?,?)",("o1",json.dumps(intent),"f","reconciling","unknown")); con.close()
    assert store.cancel_task_authority(db,"t1")==1
    assert store.unknown_effects_for_task(db,"t1")==["o1"]
