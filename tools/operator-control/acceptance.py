from __future__ import annotations
import hashlib,json,secrets
from datetime import datetime,timezone,timedelta
from typing import Any
DIGEST_FIELDS=('criteria','evaluator','schemas','protected_tests')
BINDINGS=('task_id','task_version','requirement_version','artifact_id','artifact_version','target_id','target_version','environment')
def _canonical(value:Any)->bytes:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def canonical_digest(value:Any)->str:
 protected=({k:v for k,v in value.items() if k not in {'policy_digest','_broker_signature','_broker_table'}} if isinstance(value,dict) else value)
 return 'sha256:'+hashlib.sha256(_canonical(protected)).hexdigest()
def invalidated_criteria(policy,changed_inputs):return [c['criterion_id'] for c in policy['criteria'] if changed_inputs.intersection(c.get('affected_by',[]))]
def _time(value):
 parsed=datetime.fromisoformat(str(value).replace('Z','+00:00')); return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
def _failure(cid,reason):return {'criterion_id':cid,'reason':reason,'required_action':f'Re-verify {cid}: {reason}'}
class AcceptanceEvaluator:
 def __init__(self,*,policy_loader,state_loader,evidence_resolver,review_resolver,exception_resolver,verify_record=None,acceptance_writer=None,identity_resolver=None,now=lambda:datetime.now(timezone.utc)):
  if verify_record is None or identity_resolver is None: raise ValueError('broker signature verifier and trusted identity resolver are required')
  self.policy_loader=policy_loader; self.state_loader=state_loader; self.evidence_resolver=evidence_resolver; self.review_resolver=review_resolver; self.exception_resolver=exception_resolver; self.verify_record=verify_record; self.acceptance_writer=acceptance_writer; self.identity_resolver=identity_resolver; self.now=now
 def _auth(self,table,value):
  try:return bool(value and self.verify_record(table,value))
  except Exception:return False
 def evaluate(self,_caller_policy,submission,_caller_current,*,accepter_id=None,identity_context=None):
  actor=self.identity_resolver(identity_context)
  if not isinstance(actor,dict) or actor.get('authenticated') is not True: raise ValueError('trusted accepter identity required')
  accepter_id=actor.get('subject')
  task_id=submission.get('task_id')
  if not isinstance(task_id,str) or not task_id:raise ValueError('submission must bind a task ID')
  policy=self.policy_loader(task_id); current=self.state_loader(task_id)
  if not self._auth('policies',policy): raise ValueError('signed broker-owned policy required')
  ids=[c.get('criterion_id') for c in policy.get('criteria',[])]
  if len(ids)!=len(set(ids)):raise ValueError('duplicate criterion IDs in protected policy')
  reasons=[]; failures=[]; passes=[]
  if submission.get('policy_digest')!=policy.get('policy_digest'):reasons.append('protected-policy-digest-mismatch')
  worker=submission.get('worker_id')
  if not worker or not accepter_id or accepter_id==worker:reasons.append('worker-cannot-accept-own-submission')
  if current.get('external_effects')!='confirmed-success':reasons.append('external-effect-not-confirmed-success')
  if not current.get('authority_valid_at_action'):reasons.append('authority-invalid-at-action')
  if any(not d.get('accepted') or not d.get('applicable') for d in current.get('dependencies',[])):reasons.append('dependency-not-accepted-applicable')
  by={}
  for claim in submission.get('results',[]):by.setdefault(claim.get('criterion_id'),[]).append(claim)
  resolved=[]
  for criterion in policy.get('criteria',[]):
   if not criterion.get('required'):continue
   cid=criterion['criterion_id']; claims=by.get(cid,[]); before=len(reasons)
   if len(claims)!=1:reasons.append(f'{cid}:missing-or-duplicate-result')
   else:
    eids=claims[0].get('evidence_ids',[])
    if not eids:reasons.append(f'{cid}:missing-evidence')
    for eid in eids:
     ev=self.evidence_resolver(eid)
     if not ev or not self._auth('evidence',ev):reasons.append(f'{cid}:unsigned-or-unresolved-evidence');continue
     if ev.get('criterion_id')!=cid or any(ev.get(k)!=current.get(k) for k in BINDINGS) or ev.get('policy_digest')!=policy.get('policy_digest'):reasons.append(f'{cid}:evidence-binding-mismatch');continue
     try:expires=_time(ev['expires_at']); collected=_time(ev['collected_at']); retained=_time(ev['retention_until'])
     except (KeyError,ValueError,TypeError):reasons.append(f'{cid}:invalid-evidence-time');continue
     if expires<=self.now() or collected>self.now() or retained<expires or retained<=self.now():reasons.append(f'{cid}:stale-or-unretained-evidence');continue
     digest=ev.get('content_digest') or ev.get('receipt_digest') or ''
     if not isinstance(digest,str) or not digest.startswith('sha256:') or len(digest)!=71 or not ev.get('collector_id'):reasons.append(f'{cid}:invalid-evidence-integrity');continue
     if ev.get('kind') not in criterion.get('evidence_kinds',[]) or ev.get('verifier_kind')!=criterion.get('verifier_kind') or ev.get('result')!='pass':reasons.append(f'{cid}:evidence-does-not-satisfy-criterion');continue
     resolved.append(ev)
   if len(reasons)>before:failures.append(_failure(cid,reasons[-1].split(':',1)[-1]))
   else:passes.append(cid)
  if policy.get('consequential') or policy.get('judgment_heavy'):
   review=self.review_resolver(submission.get('review_id')); valid=self._auth('reviews',review) and review.get('result')=='pass'
   valid=valid and review.get('reviewer_id') not in {None,worker,accepter_id} and review.get('policy_digest')==policy.get('policy_digest') and review.get('evidence_digest')==canonical_digest(resolved)
   valid=valid and all(review.get(k)==current.get(k) for k in BINDINGS)
   try:valid=valid and _time(review['expires_at'])>self.now() and _time(review['retention_until'])>=_time(review['expires_at'])
   except (KeyError,ValueError,TypeError):valid=False
   if not valid:reasons.append('independent-signed-bound-review-required'); failures.append(_failure('independent-review','signed-current-bound-review-required'))
  status,disposition=('accepted','success') if not reasons else ('blocked','open')
  xid=submission.get('human_exception_id')
  if reasons and xid:
   ex=self.exception_resolver(xid); valid=self._auth('exceptions',ex) and ex.get('actor_id') not in {None,worker,accepter_id}
   valid=valid and bool(ex.get('reason')) and bool(ex.get('scope')) and ex.get('policy_digest')==policy.get('policy_digest') and all(ex.get(k)==current.get(k) for k in BINDINGS)
   try:valid=valid and _time(ex['issued_at'])<=self.now()<_time(ex['expires_at'])
   except (KeyError,ValueError,TypeError):valid=False
   if valid:status,disposition='exception-closed','exception' # never success
   else:reasons.append('invalid-exception-authority'); failures.append(_failure('exception','valid-scoped-version-bound-exception-required'))
  now=self.now(); record={'record_version':'2','acceptance_id':'acc_'+secrets.token_urlsafe(18),'status':status,'disposition':disposition,**{k:current[k] for k in BINDINGS},'policy_version':policy['policy_version'],'policy_digest':policy['policy_digest'],'submission_id':submission['submission_id'],'worker_id':worker,'accepter_id':accepter_id,'criterion_results':ids,'criteria_digest':canonical_digest(policy.get('criteria',[])),'evidence_digest':canonical_digest(resolved),'reasons':reasons,'issued_at':now.isoformat().replace('+00:00','Z'),'accepted_at':now.isoformat().replace('+00:00','Z'),'expires_at':(now+timedelta(hours=1)).isoformat().replace('+00:00','Z')}
  if status=='accepted' and self.acceptance_writer:self.acceptance_writer(record,identity_context=identity_context)
  rework=None if not reasons else {'rework_version':'1','task_id':current['task_id'],'submission_id':submission['submission_id'],'failed_criteria':failures or [_failure('acceptance-gate',r) for r in reasons],'preserved_passes':passes}
  return {'acceptance':record,'rework':rework}
def evaluate_acceptance(*args,**kwargs):raise RuntimeError('AcceptanceEvaluator with protected resolvers is required')
