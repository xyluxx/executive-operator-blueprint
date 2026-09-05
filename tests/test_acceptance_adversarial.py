import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1]; P=ROOT/"tools/operator-control/acceptance.py"
spec=importlib.util.spec_from_file_location("hardened_acceptance",P); assert spec is not None; mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)

def policy():
 return {"policy_version":"p1","policy_digest":"protected","criteria":[{"criterion_id":"C1","required":True,"evidence_kinds":["test"],"verifier_kind":"deterministic"}],"consequential":False,"judgment_heavy":False,"_broker_table":"policies"}
def current(effect="confirmed-success"):
 return {"task_id":"t","task_version":"tv","requirement_version":"rv","artifact_id":"a","artifact_version":"av","target_id":"x","target_version":"xv","environment":{"name":"prod","version":"1"},"external_effects":effect,"authority_valid_at_action":True,"dependencies":[]}
def evidence():
 return {"evidence_id":"e","criterion_id":"C1","task_id":"t","task_version":"tv","requirement_version":"rv","artifact_id":"a","artifact_version":"av","target_id":"x","target_version":"xv","environment":{"name":"prod","version":"1"},"kind":"test","content_digest":"sha256:"+"a"*64,"collector_id":"collector","collected_at":"2026-09-05T12:00:00Z","expires_at":"2027-09-05T12:00:00Z","retention_until":"2028-09-05T12:00:00Z","policy_digest":"protected","result":"pass","verifier_kind":"deterministic","_broker_table":"evidence"}
def submission(): return {"submission_id":"s","task_id":"t","worker_id":"worker","policy_digest":"protected","results":[{"criterion_id":"C1","evidence_ids":["e"]}]}
def evaluator(p=None,e=None,reviews=None,exceptions=None,state=None):
 return mod.AcceptanceEvaluator(policy_loader=lambda task_id:p or policy(),state_loader=lambda task_id:state or current(),evidence_resolver=lambda eid:(e or evidence()) if eid=="e" else None,review_resolver=lambda rid:(reviews or {}).get(rid),exception_resolver=lambda xid:(exceptions or {}).get(xid),verify_record=lambda table,value: bool(value and value.get("_broker_table")==table),identity_resolver=lambda _:{"authenticated":True,"subject":"acceptor"},now=lambda:datetime(2026,9,5,13,tzinfo=timezone.utc))

def test_worker_policy_and_asserted_fake_uri_cannot_authorize():
 weak=policy(); weak["criteria"]=[]
 assert evaluator().evaluate(weak,submission(),current(),accepter_id="acceptor")["acceptance"]["status"]=="accepted"
 forged=submission(); forged["results"][0]={"criterion_id":"C1","evidence_ids":["fake://made-up"],"accessible":True,"relevant":True}
 assert evaluator().evaluate(policy(),forged,current(),accepter_id="acceptor")["acceptance"]["status"]=="blocked"
def test_duplicate_criteria_and_confirmed_failure_reject():
 dup=policy(); dup["criteria"]*=2
 with pytest.raises(ValueError,match="duplicate"): evaluator(p=dup).evaluate(dup,submission(),current(),accepter_id="acceptor")
 assert evaluator(state=current("confirmed-failure")).evaluate(policy(),submission(),current(),accepter_id="acceptor")["acceptance"]["status"]=="blocked"
def test_stale_or_wrong_bound_evidence_rejects():
 stale=evidence(); stale["expires_at"]="2026-09-05T12:30:00Z"
 assert evaluator(e=stale).evaluate(policy(),submission(),current(),accepter_id="acceptor")["acceptance"]["status"]=="blocked"
 bad=evidence(); bad["criterion_id"]="OTHER"
 assert evaluator(e=bad).evaluate(policy(),submission(),current(),accepter_id="acceptor")["acceptance"]["status"]=="blocked"
def test_signed_bound_review_and_three_way_separation_required():
 p=policy(); p["consequential"]=True; s=submission(); s["review_id"]="r"
 base={"review_id":"r","result":"pass","reviewer_id":"reviewer","task_id":"t","task_version":"tv","requirement_version":"rv","artifact_id":"a","artifact_version":"av","target_id":"x","target_version":"xv","environment":{"name":"prod","version":"1"},"policy_digest":"protected","evidence_digest":mod.canonical_digest([evidence()]),"expires_at":"2027-09-05T12:00:00Z","retention_until":"2028-09-05T12:00:00Z","_broker_table":"reviews"}
 assert evaluator(p=p,reviews={"r":base}).evaluate(p,s,current(),accepter_id="acceptor")["acceptance"]["status"]=="accepted"
 for actor in ("worker","acceptor"):
  bad=dict(base,reviewer_id=actor)
  assert evaluator(p=p,reviews={"r":bad}).evaluate(p,s,current(),accepter_id="acceptor")["acceptance"]["status"]=="blocked"
def test_unsigned_human_exception_does_not_close():
 s=submission(); s["results"]=[]; s["human_exception_id"]="x"
 assert evaluator(exceptions={"x":{"authenticated":False,"signature_valid":False}}).evaluate(policy(),s,current(),accepter_id="acceptor")["acceptance"]["status"]=="blocked"
