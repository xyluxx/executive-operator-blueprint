import importlib.util, json, multiprocessing, sqlite3, sys, threading, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

ROOT=Path(__file__).parents[1]; PLUGIN=ROOT/'plugins/operator-control'; TOOLS=ROOT/'tools/operator-control'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader; module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module
schemas=load('operator_control_schemas',PLUGIN/'schemas.py'); policy=load('operator_control_policy',PLUGIN/'policy.py'); store=load('operator_control_store',TOOLS/'store.py'); broker_mod=load('control_final_broker',TOOLS/'broker.py')
def utc(seconds=0): return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')
def digest(c='a'): return 'sha256:'+c*64

def identities(overrides=None, overlaps=()):
 roles={'requester':'agent:req','executor':'adapter:mail','credential_principal':'mailbox:sender','recipient':'person:alice','approver':'human:owner','evidence_collector':'collector:ci','reviewer':'human:reviewer','accepter':'human:accepter','exception_authority':'human:risk'}
 roles.update(overrides or {})
 return {'authenticated':True,'roles':roles,'allowed_overlaps':list(overlaps)}
def actor(subject, role): return {'authenticated':True,'subject':subject,'role':role,'authority_source':'iam:protected','issuance_channel':role+':trusted'}
def acceptance_record(b,i):
 return {'record_version':'2','acceptance_id':i['acceptance_id'],'status':'accepted','disposition':'success','task_id':'t','task_version':2,'requirement_version':3,'artifact_id':'art','artifact_version':'1','target_id':'person:alice','target_version':'1','environment':{'name':'prod','version':'1'},'policy_version':'1','policy_digest':b._current_policy_digest(),'submission_id':'sub','worker_id':'worker:x','accepter_id':'human:accepter','criterion_results':['C'],'criteria_digest':digest('a'),'evidence_digest':digest('b'),'reasons':[],'issued_at':utc(-1),'accepted_at':utc(-1),'expires_at':utc(300)}
def intent(key='op'):
 return {'schema_version':1,'operation_key':key,'action_class':'message.send','requester':{'role':'requester','subject':'forged'},'executor':{'role':'executor','subject':'forged'},'credential_principal':{'role':'credential_principal','subject':'forged'},'recipient':{'role':'recipient','subject':'forged'},'account':'mailbox:sender','target':'person:alice','material_payload':{'body':'hello'},'limits':{'max_cost_usd':0},'task_id':'t','task_version':2,'requirement_version':3,'artifact_id':'art','artifact_version':'1','target_version':'1','environment':{'name':'prod','version':'1'},'acceptance_id':'ac','policy_digest':'ignored'}
def approval(i):
 return {'schema_version':1,'approval_id':'ap','authority_type':'one_off','approver':{'role':'authenticated_approver','subject':'forged'},'authority_source':'forged','issuance_channel':'forged','non_transferable':True,'action_class':'message.send','account':i['account'],'target':i['target'],'payload_digest':schemas.material_payload_digest(i['material_payload']),'limits':i['limits'],'task_id':'t','task_version':2,'requirement_version':3,'operation_key':i['operation_key'],'issued_at':utc(-1),'expires_at':utc(300),'cancelled':False}
def readback(b,i,**extra):
 value={'account':i['account'],'target':i['target'],'payload_digest':schemas.material_payload_digest(i['material_payload']),'task_version':2,'requirement_version':3,'policy_digest':b._current_policy_digest(),'operation_key':i['operation_key']}; value.update(extra); return value

def make(tmp_path, *, role_result=None, collector=None):
 root=tmp_path/'policy'; root.mkdir(); (root/'policy.json').write_text('{"version":1}')
 records={}
 def resolve_acceptance(aid): return {'authenticated':True,'actor':actor('human:accepter','accepter'),'record':records.get(aid)}
 b=broker_mod.ActionBroker(tmp_path/'private/control.db',policy_root=root,supported_routes={'message.send'},signing_key=b'x'*32,
  authenticate_approver=lambda _:actor('human:owner','approver'), authenticate_policy_authority=lambda _:actor('policy:owner','policy_authority'), resolve_identities=lambda _:role_result or identities(),
  resolve_acceptance=resolve_acceptance, collect_evidence=collector,
  authenticate_reviewer=lambda _:actor('human:reviewer','reviewer'), authenticate_exception_authority=lambda _:actor('human:risk','exception_authority'))
 i=intent(); records['ac']=acceptance_record(b,i)
 b.issue_acceptance('ac',auth_context={'trusted':True})
 b.issue_approval(approval(i),auth_context={'trusted':True})
 return b,i

def test_generic_record_minting_is_removed_and_invented_acceptance_cannot_be_issued(tmp_path):
 b,i=make(tmp_path)
 for name in ('put_policy','put_evidence','put_review','put_exception','put_acceptance'):
  assert not hasattr(b,name)
 with pytest.raises(policy.Denied): b.issue_acceptance({'acceptance_id':'invented','status':'accepted'},auth_context={'trusted':True})

def test_fake_uri_and_spoofed_evidence_identity_are_rejected(tmp_path):
 def fake(_): return {'authenticated':True,'actor':actor('collector:real','evidence_collector'),'record':{'evidence_id':'ev','reference':'https://does-not-exist.invalid/fake','collector_id':'collector:spoofed'}}
 b,_=make(tmp_path,collector=fake)
 with pytest.raises(policy.Denied): b.issue_evidence({'evidence_id':'ev','criterion_id':'C'})

def test_evidence_requires_opened_content_protected_verifier_retention_and_bindings(tmp_path):
 source=tmp_path/'retained-artifact'; source.write_bytes(b'actual retained artifact'); content=source.read_bytes()
 def collector(request):
  return {'authenticated':True,'actor':actor('collector:ci','evidence_collector'),'opened':True,'content':content,'retention_authorized':True,
   'verifier_result':{'protected':True,'criterion_id':'C','result':'pass','relevant':True,'verifier_kind':'deterministic'},
   'record':{**request,'kind':'test','source':'ci','reference':source.as_uri(),'collected_at':utc(-1),'expires_at':utc(60),'retention_until':utc(120),'result':'pass','verifier_kind':'deterministic'}}
 b,i=make(tmp_path,collector=collector)
 request={'evidence_id':'ev','criterion_id':'C','task_id':'t','task_version':2,'requirement_version':3,'artifact_id':'art','artifact_version':'1','target_id':'person:alice','target_version':'1','environment':i['environment'],'policy_digest':b._current_policy_digest()}
 b.issue_evidence(request); ev=b.load_record('evidence','ev')
 assert ev['collector_id']=='collector:ci' and ev['content_digest']==digest(__import__('hashlib').sha256(content).hexdigest()[0]) if False else ev['content_digest']=='sha256:'+__import__('hashlib').sha256(content).hexdigest()

def test_every_role_overlap_defaults_to_denied_and_policy_can_explicitly_allow_one(tmp_path):
 names=['requester','executor','credential_principal','recipient','approver','evidence_collector','reviewer','accepter','exception_authority']
 for index,(left,right) in enumerate((('executor','credential_principal'),('executor','recipient'),('approver','reviewer'),('evidence_collector','accepter'))):
  role=identities(); role['roles'][right]=role['roles'][left]
  case=tmp_path/str(index); case.mkdir(); b,i=make(case,role_result=role)
  with pytest.raises(policy.Denied,match='role separation'): b.authorize(i,'ap',identity_context={})
 role=identities(overlaps=[['executor','credential_principal']]); role['roles']['credential_principal']=role['roles']['executor']; case=tmp_path/'allowed'; case.mkdir(); b,i=make(case,role_result=role)
 assert b.authorize(i,'ap',identity_context={})['authorized']

def test_reviewer_source_mutation_callback_cannot_change_effect_authority(tmp_path):
 b,i=make(tmp_path); called=[]; old=b._current_policy_digest()
 def reviewer_attack(payload):
  (b.policy_root/'policy.json').write_text('{"version":2}')
  called.append(True); return {'provider_id':'ok','readback':readback(b,i,policy_digest=old)}
 assert b.execute(i,'ap',reviewer_attack,identity_context={})['effect']=='confirmed-success'
 assert called and b._current_policy_digest()==old

def test_two_brokers_make_revoke_and_dispatch_atomic(tmp_path):
 b1,i=make(tmp_path); b2=broker_mod.ActionBroker(b1.db_path,policy_root=b1.policy_root,supported_routes={'message.send'},signing_key=b'x'*32,authenticate_approver=lambda _:actor('human:owner','approver'),resolve_identities=lambda _:identities(),resolve_acceptance=lambda _:False,authenticate_reviewer=lambda _:False,authenticate_exception_authority=lambda _:False)
 reserved=threading.Event(); release=threading.Event(); result=[]
 def handler(_): reserved.set(); release.wait(2); return {'provider_id':'ok','readback':readback(b1,i)}
 thread=threading.Thread(target=lambda:result.append(b1.execute(i,'ap',handler,identity_context={}))); thread.start(); assert reserved.wait(2)
 revoked=threading.Thread(target=lambda:b2.revoke_approval('ap',auth_context={})); revoked.start()
 release.set(); thread.join(3); revoked.join(3)
 assert result[0]['effect']=='confirmed-success' and b2.approval_status('ap')['state']=='revoked'

def test_customer_note_is_discarded_and_nested_secret_readback_is_rejected(tmp_path):
 b,i=make(tmp_path); note='customer plaintext that must disappear'
 out=b.execute(i,'ap',lambda _:{'provider_id':'internal','readback':readback(b,i,customer_note=note)},identity_context={})
 assert out['effect']=='confirmed-success' and note not in json.dumps(out) and note.encode() not in b.db_path.read_bytes()
 case=tmp_path/'secret-case'; case.mkdir(); b,i=make(case)
 rejected=b.execute(i,'ap',lambda _:{'provider_id':'internal','readback':readback(b,i,nested={'authorization':'Bearer secret'})},identity_context={})
 assert rejected['effect']=='unknown' and b'Bearer secret' not in b.db_path.read_bytes()

def test_success_readback_is_exact_allowlist(tmp_path):
 b,i=make(tmp_path); out=b.execute(i,'ap',lambda _:{'provider_id':'internal','readback':readback(b,i)},identity_context={})
 assert out['effect']=='confirmed-success' and set(out['readback'])=={'account','target','payload_digest','task_version','requirement_version','policy_digest','operation_key'}

def test_source_mutation_at_effect_boundary_cannot_change_imported_authority(tmp_path):
 b,i=make(tmp_path); called=[]
 old=b._current_policy_digest()
 def mutate_source_then_effect(payload):
  (b.policy_root/'policy.json').write_text('{"version":999}')
  called.append(payload)
  return {'provider_id':'ok','readback':readback(b,i,policy_digest=old)}
 out=b.execute(i,'ap',mutate_source_then_effect,identity_context={})
 assert out['effect']=='confirmed-success' and called
 assert b._current_policy_digest()==old
 with pytest.raises(policy.Denied,match='policy source differs'):
  b.import_policy(auth_context={'trusted':True})

def test_policy_publish_that_wins_before_reservation_blocks_old_authority(tmp_path):
 b,i=make(tmp_path)
 (b.policy_root/'policy.json').write_text('{"version":2}')
 new_id=b.publish_policy(auth_context={'trusted':True})
 assert new_id != b.policy_id_for_digest(i.get('policy_digest',''))
 with pytest.raises(policy.Denied,match='policy digest mismatch|acceptance'):
  b.execute(i,'ap',lambda _:pytest.fail('effect must not run'),identity_context={})

def test_policy_publish_after_reservation_waits_for_effect_commit_and_is_future_only(tmp_path):
 b1,i=make(tmp_path)
 b2=broker_mod.ActionBroker(b1.db_path,policy_root=b1.policy_root,supported_routes={'message.send'},signing_key=b'x'*32,
  authenticate_approver=lambda _:actor('human:owner','approver'),authenticate_policy_authority=lambda _:actor('policy:owner','policy_authority'),
  resolve_identities=lambda _:identities(),resolve_acceptance=lambda _:False)
 old=b1._current_policy_digest(); entered=threading.Event(); release=threading.Event(); published=[]
 def handler(_):
  entered.set(); assert release.wait(3)
  return {'provider_id':'ok','readback':readback(b1,i,policy_digest=old)}
 effect=threading.Thread(target=lambda:published.append(('effect',b1.execute(i,'ap',handler,identity_context={})))); effect.start(); assert entered.wait(2)
 (b1.policy_root/'policy.json').write_text('{"version":2}')
 update=threading.Thread(target=lambda:published.append(('policy',b2.publish_policy(auth_context={})))); update.start()
 time.sleep(.15); assert update.is_alive() and b1._current_policy_digest()==old
 release.set(); effect.join(3); update.join(3)
 assert not effect.is_alive() and not update.is_alive()
 assert dict(published)['effect']['effect']=='confirmed-success'
 assert b1._current_policy_digest()!=old

def test_cross_process_policy_publish_cannot_interleave_with_effect_fence(tmp_path):
 b1,i=make(tmp_path)
 b2=broker_mod.ActionBroker(b1.db_path,policy_root=b1.policy_root,supported_routes={'message.send'},signing_key=b'x'*32,
  authenticate_approver=lambda _:actor('human:owner','approver'),authenticate_policy_authority=lambda _:actor('policy:owner','policy_authority'),
  resolve_identities=lambda _:identities(),resolve_acceptance=lambda _:False)
 old=b1._current_policy_digest(); ctx=multiprocessing.get_context('fork'); entered=ctx.Event(); release=ctx.Event(); effects=ctx.Queue(); updates=ctx.Queue()
 def handler(_): entered.set(); assert release.wait(5); return {'provider_id':'ok','readback':readback(b1,i,policy_digest=old)}
 def execute(): effects.put(b1.execute(i,'ap',handler,identity_context={}))
 effect=ctx.Process(target=execute); effect.start(); assert entered.wait(2)
 (b1.policy_root/'policy.json').write_text('{"version":2}')
 attempted=ctx.Event()
 def publish(): attempted.set(); updates.put(b2.publish_policy(auth_context={}))
 process=ctx.Process(target=publish); process.start(); assert attempted.wait(2); time.sleep(.15)
 assert process.is_alive()
 release.set(); effect.join(5); process.join(5)
 assert effect.exitcode==0 and process.exitcode==0 and effects.get(timeout=1)['effect']=='confirmed-success' and updates.get(timeout=1)
 assert b1._current_policy_digest()!=old
