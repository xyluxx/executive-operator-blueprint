import importlib.util, json, sqlite3, sys, threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1]; PLUGIN=ROOT/'plugins/operator-control'; TOOLS=ROOT/'tools/operator-control'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); assert spec is not None and spec.loader; m=importlib.util.module_from_spec(spec); sys.modules[name]=m; spec.loader.exec_module(m); return m
schemas=load('operator_control_schemas',PLUGIN/'schemas.py'); policy=load('operator_control_policy',PLUGIN/'policy.py'); store=load('operator_control_store',TOOLS/'store.py'); broker_mod=load('remaining_broker',TOOLS/'broker.py'); acceptance=load('remaining_acceptance',TOOLS/'acceptance.py')
def seed(b,table,record_id,value):
 con=store.connect(b.db_path); con.execute(broker_mod.INSERT_RECORD_SQL[table],(record_id,json.dumps(value,sort_keys=True,separators=(',',':')),b._signature(value))); con.close()
def utc(n=0): return (datetime.now(timezone.utc)+timedelta(seconds=n)).isoformat().replace('+00:00','Z')
def auth(context):
 return {'authenticated':True,'subject':('human:acceptor' if context.get('session')=='acceptance' else 'human:real'),'authority_source':'webauthn:real','issuance_channel':'console:trusted'} if context.get('session') in {'trusted','acceptance'} else False
def identities(_): return {'authenticated':True,'roles':{'requester':'agent:real','executor':'adapter:mail','credential_principal':'mailbox:a','recipient':'person:alice','approver':'human:real','evidence_collector':'collector:ci','reviewer':'human:reviewer','accepter':'human:acceptor','exception_authority':'human:risk'}}
def make(tmp_path):
 p=tmp_path/'policy'; p.mkdir(); (p/'policy.json').write_text('{"version":1}')
 return broker_mod.ActionBroker(tmp_path/'private/control.db',policy_root=p,supported_routes={'message.send'},signing_key=b'x'*32,authenticate_approver=auth,resolve_identities=identities)
def intent(key='op',acceptance_id=None):
 x={'schema_version':1,'operation_key':key,'action_class':'message.send','requester':{'role':'requester','subject':'forged'},'executor':{'role':'executor','subject':'forged'},'credential_principal':{'role':'credential_principal','subject':'forged'},'recipient':{'role':'recipient','subject':'forged'},'account':'mailbox:a','target':'person:alice','material_payload':{'body':'hello'},'limits':{'max_cost_usd':0},'task_id':'t','task_version':2,'requirement_version':3,'artifact_id':'art','artifact_version':'1','target_version':'1','environment':{'name':'prod','version':'1'},'policy_digest':'f'*64}
 if acceptance_id: x['acceptance_id']=acceptance_id
 return x
def approval(i): return {'schema_version':1,'approval_id':'ap','authority_type':'one_off','approver':{'role':'authenticated_approver','subject':'human:forged'},'authority_source':'fake','issuance_channel':'fake','non_transferable':True,'action_class':i['action_class'],'account':i['account'],'target':i['target'],'payload_digest':schemas.material_payload_digest(i['material_payload']),'limits':i['limits'],'task_id':'t','task_version':2,'requirement_version':3,'policy_digest':'f'*64,'operation_key':i['operation_key'],'issued_at':utc(-2),'expires_at':utc(300),'cancelled':False}
def readback(b,i): return {'account':i['account'],'target':i['target'],'payload_digest':schemas.material_payload_digest(i['material_payload']),'task_version':2,'requirement_version':3,'policy_digest':b._current_policy_digest(),'operation_key':i['operation_key']}
def accepted(b,i):
 record={'acceptance_id':'ac','status':'accepted','task_id':'t','task_version':2,'requirement_version':3,'artifact_id':'art','artifact_version':'1','target_id':'person:alice','target_version':'1','environment':{'name':'prod','version':'1'},'policy_digest':b._current_policy_digest(),'accepter_id':'human:acceptor','criteria_digest':'sha256:'+'a'*64,'evidence_digest':'sha256:'+'b'*64,'issued_at':utc(-1),'expires_at':utc(300)}
 seed(b,'acceptances','ac',record); i['acceptance_id']='ac'
def test_forged_acceptance_and_approver_fields_never_authorize(tmp_path):
 b=make(tmp_path); i=intent(); i['acceptance']={'accepted':True,'task_id':'t','policy_digest':b._current_policy_digest()}
 with pytest.raises(Exception): b.issue_approval(approval(i),auth_context={})
 aid=b.issue_approval(approval(i),auth_context={'session':'trusted'}); row=b._load_approval(aid)
 assert row['approver']['subject']=='human:real' and row['authority_source']=='webauthn:real' and row['issuance_channel']=='console:trusted'
 with pytest.raises(policy.Denied,match='acceptance'): b.execute(i,aid,lambda _: {})
def test_signed_acceptance_required_and_all_roles_resolved(tmp_path):
 b=make(tmp_path); i=intent(); accepted(b,i); aid=b.issue_approval(approval(i),auth_context={'session':'trusted'})
 out=b.execute(i,aid,lambda _: {'provider_id':'ok','readback':readback(b,i)},identity_context={})
 assert out['effect']=='confirmed-success'; con=store.connect(b.db_path); saved=json.loads(con.execute("select intent_json from operations").fetchone()[0]); con.close()
 assert saved['requester']['subject']=='agent:real' and 'acceptance' not in saved

def test_unsigned_evidence_and_wrong_version_exception_are_rejected_and_rework_targeted(tmp_path):
 b=make(tmp_path); cur={'task_id':'t','task_version':'2','requirement_version':'3','artifact_id':'a','artifact_version':'1','target_id':'x','target_version':'1','environment':{'name':'prod','version':'1'},'external_effects':'confirmed-success','authority_valid_at_action':True,'dependencies':[]}
 pol={'policy_version':'1','policy_digest':'sha256:'+'c'*64,'criteria':[{'criterion_id':'C','required':True,'evidence_kinds':['test'],'verifier_kind':'deterministic'}],'consequential':False,'judgment_heavy':False}
 seed(b,'policies','t',dict(pol,task_id='t')); ev={**{k:cur[k] for k in acceptance.BINDINGS},'evidence_id':'e','criterion_id':'C','kind':'test','content_digest':'sha256:'+'d'*64,'collector_id':'collector','collected_at':utc(-5),'expires_at':utc(300),'retention_until':utc(600),'result':'pass','verifier_kind':'deterministic'}
 # Resolver dictionary is unsigned and must not pass.
 e=acceptance.AcceptanceEvaluator(policy_loader=lambda _:b.load_record('policies','t'),state_loader=lambda _:cur,evidence_resolver=lambda _:ev,review_resolver=lambda _:None,exception_resolver=lambda _:None,verify_record=b.verify_resolved_record,identity_resolver=lambda _:{'authenticated':True,'subject':'acceptor'})
 s={'submission_id':'s','task_id':'t','worker_id':'worker','policy_digest':pol['policy_digest'],'results':[{'criterion_id':'C','evidence_ids':['e']}]}
 result=e.evaluate({},s,{},accepter_id='acceptor'); assert result['acceptance']['status']=='blocked'; assert result['rework']['failed_criteria'][0]['criterion_id']=='C'

def test_broker_signed_evidence_passes_but_wrong_version_signed_exception_never_succeeds(tmp_path):
 b=make(tmp_path); cur={'task_id':'t','task_version':'2','requirement_version':'3','artifact_id':'a','artifact_version':'1','target_id':'x','target_version':'1','environment':{'name':'prod','version':'1'},'external_effects':'confirmed-success','authority_valid_at_action':True,'dependencies':[]}; pol={'policy_version':'1','policy_digest':'sha256:'+'c'*64,'criteria':[{'criterion_id':'C','required':True,'evidence_kinds':['test'],'verifier_kind':'deterministic'}],'consequential':False,'judgment_heavy':False}; seed(b,'policies','t',dict(pol,task_id='t'))
 ev={**{k:cur[k] for k in acceptance.BINDINGS},'evidence_id':'e','criterion_id':'C','policy_digest':pol['policy_digest'],'kind':'test','content_digest':'sha256:'+'d'*64,'collector_id':'collector','collected_at':utc(-5),'expires_at':utc(300),'retention_until':utc(600),'result':'pass','verifier_kind':'deterministic'}; seed(b,'evidence','e',ev)
 evaluator=acceptance.AcceptanceEvaluator(policy_loader=lambda _:b.load_record('policies','t'),state_loader=lambda _:cur,evidence_resolver=lambda eid:b.load_record('evidence',eid),review_resolver=lambda _:None,exception_resolver=lambda xid:b.load_record('exceptions',xid),verify_record=b.verify_resolved_record,identity_resolver=lambda _:{'authenticated':True,'subject':'acceptor'})
 s={'submission_id':'s','task_id':'t','worker_id':'worker','policy_digest':pol['policy_digest'],'results':[{'criterion_id':'C','evidence_ids':['e']}]}; assert evaluator.evaluate({},s,{},accepter_id='acceptor')['acceptance']['status']=='accepted'
 bad={**{k:cur[k] for k in acceptance.BINDINGS},'exception_id':'x','task_version':'WRONG','reason':'documented waiver','scope':['C'],'policy_digest':pol['policy_digest'],'issued_at':utc(-1),'expires_at':utc(300)}; seed(b,'exceptions','x',bad); s['results']=[]; s['human_exception_id']='x'; result=evaluator.evaluate({},s,{},accepter_id='acceptor'); assert result['acceptance']['status']=='blocked' and result['acceptance']['disposition']!='success'

def test_provider_plaintext_never_persisted_and_nested_secret_rejected(tmp_path):
 sentinel='SENTINEL-super-secret-987654321'; b=make(tmp_path); i=intent(); accepted(b,i); aid=b.issue_approval(approval(i),auth_context={'session':'trusted'})
 out=b.execute(i,aid,lambda _: {'provider_id':sentinel,'readback':readback(b,i),'nested':{'token':sentinel}},identity_context={}); assert sentinel not in json.dumps(out)
 raw=b.db_path.read_bytes(); assert sentinel.encode() not in raw
 with pytest.raises(RuntimeError): broker_mod.sanitize_provider_metadata({'nested':{'token':'x'}})

def test_provider_plaintext_string_is_converted_to_unknown_without_crash_or_persistence(tmp_path):
 sentinel='SENTINEL-crash-output-secret-123'; b=make(tmp_path); i=intent(); accepted(b,i); aid=b.issue_approval(approval(i),auth_context={'session':'trusted'})
 result=b.execute(i,aid,lambda _:sentinel,identity_context={})
 assert result['effect']=='unknown' and sentinel not in json.dumps(result) and sentinel.encode() not in b.db_path.read_bytes()

def test_revocation_cannot_interleave_after_atomic_reservation(tmp_path):
 b=make(tmp_path); i=intent(); accepted(b,i); aid=b.issue_approval(approval(i),auth_context={'session':'trusted'}); started=threading.Event(); release=threading.Event(); results=[]
 def handler(_): started.set(); release.wait(2); return {'provider_id':'ok','readback':readback(b,i)}
 effect=threading.Thread(target=lambda:results.append(b.execute(i,aid,handler,identity_context={}))); effect.start(); assert started.wait(2)
 withdrawal=threading.Thread(target=lambda:b.revoke_approval(aid,auth_context={'session':'trusted'})); withdrawal.start()
 release.set(); effect.join(3); withdrawal.join(3)
 assert results[0]['effect']=='confirmed-success' and b.approval_status(aid)['state']=='revoked'
