"""Authoritative, type-specific record issuance and durable effect boundary."""
from __future__ import annotations
import base64, hashlib, hmac, json, re, secrets, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from policy import Denied, check  # pyright: ignore[reportMissingImports]
    from schemas import validate, canonical_json, material_payload_digest  # pyright: ignore[reportMissingImports]
    import store
else:
    try:
        from operator_control_policy import Denied, check
        from operator_control_schemas import validate, canonical_json, material_payload_digest
        import operator_control_store as store
    except ImportError:  # pragma: no cover
        raise RuntimeError("load operator-control modules from their distribution paths")

RECORD_TABLES=frozenset({'approvals','acceptances','evidence','reviews','policies','exceptions'})
INSERT_RECORD_SQL={t:f'INSERT INTO {t}(record_id,record_json,signature) VALUES(?,?,?)' for t in RECORD_TABLES}  # nosec B608 -- closed constant table set
SELECT_RECORD_SQL={t:f'SELECT record_json,signature,revoked FROM {t} WHERE record_id=?' for t in RECORD_TABLES}  # nosec B608 -- closed constant table set
SECRET_KEYS=('secret','password','passwd','token','api_key','apikey','authorization','credential','private_key','plaintext','recipient_url','link','url')
ALLOWED_PROVIDER_KEYS={'provider_status','status_code','attempt_count','retryable'}
READBACK_KEYS=('account','target','payload_digest','task_version','requirement_version','policy_digest','operation_key')
ALL_ROLES=('requester','executor','credential_principal','recipient','approver','evidence_collector','reviewer','accepter','exception_authority')
BINDINGS=('task_id','task_version','requirement_version','artifact_id','artifact_version','target_id','target_version','environment','policy_digest')

def _digest(value): return hashlib.sha256(canonical_json(value)).hexdigest()
def _sha(value): return 'sha256:'+hashlib.sha256(value).hexdigest()
def _parse(value):
 try:
  result=datetime.fromisoformat(str(value).replace('Z','+00:00')); return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
 except (TypeError,ValueError): raise Denied('invalid record time')
def _secret_like_value(value):
 if not isinstance(value,str): return False
 low=value.lower(); return ('sentinel' in low or 'bearer ' in low or '-----begin ' in low or low.startswith(('sk-','ghp_','xoxb-','akia')))
def reject_secret_material(value):
 if isinstance(value,dict):
  for key,child in value.items():
   if any(part in str(key).lower() for part in SECRET_KEYS): raise RuntimeError('secret-like provider key rejected')
   reject_secret_material(child)
 elif isinstance(value,(list,tuple)):
  for child in value: reject_secret_material(child)
 elif _secret_like_value(value): raise RuntimeError('secret-like provider value rejected')
def sanitize_provider_metadata(provider):
 if not isinstance(provider,dict): raise RuntimeError('provider result must be a metadata object')
 reject_secret_material(provider); clean={}
 for key in ALLOWED_PROVIDER_KEYS:
  if key not in provider: continue
  value=provider[key]
  if key in {'status_code','attempt_count'} and isinstance(value,int) and not isinstance(value,bool): clean[key]=value
  elif key=='retryable' and isinstance(value,bool): clean[key]=value
  elif key=='provider_status' and isinstance(value,str) and value in {'accepted','rejected','pending','delivered','failed'}: clean[key]=value
  else: raise RuntimeError('provider metadata has invalid type or value')
 return clean

def _strict(record, required, optional=()):
 if not isinstance(record,dict) or set(record)-set(required)-set(optional): raise Denied('record schema contains unknown fields')
 if any(k not in record or record[k] in (None,'',[]) for k in required): raise Denied('record schema is incomplete')
def _trusted_resolution(value: object, expected_role: str) -> tuple[dict,dict]:
 if not isinstance(value,dict) or value.get('authenticated') is not True or not isinstance(value.get('record'),dict): raise Denied(f'trusted {expected_role} resolver required')
 actor=value.get('actor')
 if not isinstance(actor,dict) or actor.get('authenticated') is not True or actor.get('role')!=expected_role: raise Denied(f'authenticated {expected_role} channel required')
 for key in ('subject','authority_source','issuance_channel'):
  if not isinstance(actor.get(key),str) or not actor[key]: raise Denied(f'incomplete {expected_role} identity')
 return json.loads(json.dumps(value['record'])),actor

class ActionBroker:
 def __init__(self,db_path,*,policy_root=None,policy_digest=None,supported_routes,signing_key=None,authenticate_approver=None,authenticate_policy_authority=None,authenticate_reconciler=None,resolve_identities=None,max_reconciliation_attempts=3,resolve_policy=None,collect_evidence=None,resolve_review=None,authenticate_reviewer=None,resolve_exception=None,authenticate_exception_authority=None,resolve_acceptance=None,managed_gate=None,managed_mode=False,managed_controller=None):
  self.db_path=Path(db_path)
  if policy_root is None: raise ValueError('protected policy_root is required; caller digest is not authority')
  self.policy_root=Path(policy_root)
  self.supported_routes=frozenset(supported_routes); self._key=bytes(signing_key or b'')
  if len(self._key)<32: raise ValueError('record signing key must contain at least 32 bytes')
  self._authenticate_approver=authenticate_approver or (lambda _:False); self._authenticate_policy_authority=authenticate_policy_authority or (lambda _:False); self._authenticate_reconciler=authenticate_reconciler or (lambda x:bool(x.get('authenticated')) and str(x.get('subject','')).startswith('provider:'))
  if managed_mode and managed_controller is None: raise ValueError('managed controller is required in managed mode')
  self._resolve_identities=resolve_identities or (lambda _:False); self._resolve_policy=resolve_policy; self._collect_evidence=collect_evidence; self._resolve_review=resolve_review; self._authenticate_reviewer=authenticate_reviewer or (lambda _:False); self._resolve_exception=resolve_exception; self._authenticate_exception_authority=authenticate_exception_authority or (lambda _:False); self._resolve_acceptance=resolve_acceptance
  self.managed_gate=managed_gate; self.managed_mode=bool(managed_mode or managed_controller is not None); self.managed_controller=managed_controller
  self.__issuance_token=object()
  self.max_reconciliation_attempts=max_reconciliation_attempts; self._available=True
  con=store.connect(self.db_path)
  con.executescript("""CREATE TABLE IF NOT EXISTS broker_secrets(name TEXT PRIMARY KEY,value BLOB NOT NULL); CREATE TABLE IF NOT EXISTS credential_handles(handle_id TEXT PRIMARY KEY,binding_json TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS credential_receipts(receipt_id TEXT PRIMARY KEY,handle_id TEXT NOT NULL,binding_json TEXT NOT NULL,provider_id TEXT NOT NULL,confirmed INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS approval_revocation_preparations(intent_id TEXT PRIMARY KEY,approval_id TEXT NOT NULL,correction_id TEXT NOT NULL,predecessor_json TEXT NOT NULL,replacement_json TEXT NOT NULL,signature TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('prepared','cancelled','committed')),prepared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);""")
  if con.execute("SELECT 1 FROM broker_secrets WHERE name='credential-signing-key'").fetchone() is None: con.execute("INSERT INTO broker_secrets(name,value) VALUES('credential-signing-key',?)",(secrets.token_bytes(32),))
  con.close(); self._bootstrap_policy()
  self.policy_digest=self._current_policy_digest()
 def close(self): self._available=False
 _CREDENTIAL_FIELDS=frozenset({'approval_reference','approval_version','task_reference','task_version','requirement_version','site_id','credential_reference','credential_principal','recipient','allowed_action','operation_key'})
 _TOKEN=re.compile(r'^(ch|cr)_[0-9a-f]{32}\.[0-9a-f]{64}$')
 @classmethod
 def _safe_value(cls,value,path='binding'):
  if isinstance(value,dict):
   for key,item in value.items():
    if any(marker in str(key).lower() for marker in ('password','secret','api_key','access_token','private_key')): raise ValueError(f'secret-like field in {path}')
    cls._safe_value(item,f'{path}.{key}')
  elif isinstance(value,(list,tuple)):
   for index,item in enumerate(value): cls._safe_value(item,f'{path}[{index}]')
  elif isinstance(value,str) and any(marker in value.lower() for marker in ('password=','secret=','api_key=','access_token=','bearer ')): raise ValueError(f'secret-like value in {path}')
 def _credential_sign(self,prefix,nonce):
  con=self._connect(); key=bytes(con.execute("SELECT value FROM broker_secrets WHERE name='credential-signing-key'").fetchone()[0]); con.close(); stem=f'{prefix}_{nonce}'; return stem+'.'+hmac.new(key,stem.encode(),hashlib.sha256).hexdigest()
 def _verify_credential_token(self,token,prefix):
  if not isinstance(token,str) or not self._TOKEN.fullmatch(token) or not token.startswith(prefix+'_'): raise Denied('malformed broker credential token')
  stem,signature=token.rsplit('.',1); expected=self._credential_sign(prefix,stem.split('_',1)[1]).rsplit('.',1)[1]
  if not hmac.compare_digest(signature,expected): raise Denied('invalid broker credential token signature')
 def issue_credential_handle(self,binding):
  self._safe_value(binding)
  if not isinstance(binding,dict) or set(binding)!=self._CREDENTIAL_FIELDS or any(v in (None,'') for v in binding.values()): raise ValueError('credential handle requires exact nonblank authorization binding')
  handle=self._credential_sign('ch',secrets.token_hex(16)); con=self._connect(); con.execute('INSERT INTO credential_handles(handle_id,binding_json) VALUES(?,?)',(handle,json.dumps(binding,sort_keys=True))); con.close(); return handle
 def read_credential_handle(self,handle_id,expected_binding):
  self._verify_credential_token(handle_id,'ch'); self._safe_value(expected_binding); con=self._connect(); row=con.execute('SELECT binding_json FROM credential_handles WHERE handle_id=?',(handle_id,)).fetchone(); con.close()
  if row is None or json.loads(row['binding_json'])!=expected_binding: raise Denied('credential handle binding mismatch')
  return {'handle_id':handle_id,**expected_binding}
 def deliver_credential(self,handle_id,provider):
  self._verify_credential_token(handle_id,'ch'); con=self._connect(); row=con.execute('SELECT binding_json FROM credential_handles WHERE handle_id=?',(handle_id,)).fetchone(); con.close()
  if row is None: raise Denied('unknown credential handle')
  binding=json.loads(row['binding_json']); delivered=provider({'handle_id':handle_id,**binding}); self._safe_value(delivered,'provider receipt'); expected={**binding,'handle_id':handle_id}
  if not isinstance(delivered,dict) or not delivered.get('provider_id') or delivered.get('confirmed') is not True or delivered.get('readback')!=expected: raise RuntimeError('credential provider delivery was not positively confirmed by exact readback')
  receipt=self._credential_sign('cr',secrets.token_hex(16)); con=self._connect(); con.execute('INSERT INTO credential_receipts(receipt_id,handle_id,binding_json,provider_id,confirmed) VALUES(?,?,?,?,1)',(receipt,handle_id,json.dumps(binding,sort_keys=True),delivered['provider_id'])); con.close(); return receipt
 def read_credential_receipt(self,receipt_id,expected_binding):
  self._verify_credential_token(receipt_id,'cr'); self._safe_value(expected_binding); con=self._connect(); row=con.execute('SELECT * FROM credential_receipts WHERE receipt_id=?',(receipt_id,)).fetchone(); con.close()
  if row is None or json.loads(row['binding_json'])!=expected_binding or row['confirmed']!=1: raise Denied('credential receipt binding mismatch')
  return {'receipt_id':receipt_id,'handle_id':row['handle_id'],'provider_id':row['provider_id'],'confirmed':True,**expected_binding}
 def _connect(self,operation=False):
  if not self._available: raise Denied('broker unavailable')
  try:return store.connect(self.db_path,for_operation=operation)
  except (OSError,sqlite3.Error,RuntimeError,PermissionError) as exc: raise Denied('broker unavailable or operations blocked') from exc
 def _source_policy_record(self):
  files={}; digest=hashlib.sha256()
  for path in sorted(p for p in self.policy_root.rglob('*') if p.is_file()):
   raw=path.read_bytes()
   try: raw=canonical_json(json.loads(raw))
   except (UnicodeDecodeError,json.JSONDecodeError) as exc:
    if path.suffix.lower()=='.json': raise Denied('policy JSON source is invalid') from exc
   name=path.relative_to(self.policy_root).as_posix(); files[name]=base64.b64encode(raw).decode('ascii')
   digest.update(name.encode()+b'\0'); digest.update(hashlib.sha256(raw).digest())
  if not files: raise Denied('policy source is empty')
  return {'digest':digest.hexdigest(),'content':files}
 def _policy_from(self,con):
  row=con.execute("SELECT p.policy_id,p.version,p.digest,p.record_json,p.signature,p.revoked FROM policy_authority_versions p JOIN control_state c ON c.key='current_policy_id' AND c.value=p.policy_id").fetchone()
  if not row or row['revoked']: raise Denied('current policy authority unavailable')
  record=json.loads(row['record_json'])
  if record.get('policy_id')!=row['policy_id'] or record.get('version')!=row['version'] or record.get('digest')!=row['digest'] or not hmac.compare_digest(row['signature'],self._signature(record)): raise Denied('policy authority signature invalid')
  return record
 def _bootstrap_policy(self):
  con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE')
   if con.execute("SELECT value FROM control_state WHERE key='current_policy_id'").fetchone()[0]: con.execute('COMMIT'); return
   source=self._source_policy_record(); pid='policy_'+source['digest']; record=dict(source,policy_id=pid,version=1,status='active')
   con.execute('INSERT INTO policy_authority_versions(policy_id,version,digest,record_json,signature) VALUES(?,?,?,?,?)',(pid,1,source['digest'],json.dumps(record,sort_keys=True,separators=(',',':')),self._signature(record)))
   con.execute("UPDATE control_state SET value=? WHERE key='current_policy_id'",(pid,)); con.execute('COMMIT')
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally: con.close()
 def _current_policy_digest(self):
  con=self._connect()
  try:return self._policy_from(con)['digest']
  finally:con.close()
 def policy_id_for_digest(self,digest):
  con=self._connect(); row=con.execute('SELECT policy_id FROM policy_authority_versions WHERE digest=?',(digest,)).fetchone(); con.close(); return row['policy_id'] if row else None
 def import_policy(self,*,auth_context):
  self._trusted_actor(auth_context,self._authenticate_policy_authority,'policy_authority'); source=self._source_policy_record()
  if source['digest']!=self._current_policy_digest(): raise Denied('policy source differs from imported authority')
  return self.policy_id_for_digest(source['digest'])
 def publish_policy(self,*,auth_context):
  actor=self._trusted_actor(auth_context,self._authenticate_policy_authority,'policy_authority'); source=self._source_policy_record(); con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE'); current=self._policy_from(con)
   if source['digest']==current['digest']: con.execute('COMMIT'); return current['policy_id']
   version=con.execute('SELECT COALESCE(MAX(version),0)+1 FROM policy_authority_versions').fetchone()[0]; pid='policy_'+source['digest']; record=dict(source,policy_id=pid,version=version,status='active',authority_subject=actor['subject'])
   con.execute('INSERT INTO policy_authority_versions(policy_id,version,digest,record_json,signature) VALUES(?,?,?,?,?)',(pid,version,source['digest'],json.dumps(record,sort_keys=True,separators=(',',':')),self._signature(record)))
   con.execute("UPDATE control_state SET value=? WHERE key='current_policy_id'",(pid,)); con.execute('COMMIT'); self.policy_digest=source['digest']; return pid
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally:con.close()
 def update_policy(self,*,auth_context): return self.publish_policy(auth_context=auth_context)
 def revoke_policy(self,policy_id,*,auth_context):
  self._trusted_actor(auth_context,self._authenticate_policy_authority,'policy_authority'); con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE'); current=self._policy_from(con)
   if current['policy_id']==policy_id: raise Denied('current policy cannot be revoked; publish a replacement first')
   if con.execute('UPDATE policy_authority_versions SET revoked=1 WHERE policy_id=? AND revoked=0',(policy_id,)).rowcount!=1: raise Denied('policy missing or already revoked')
   con.execute('COMMIT')
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally:con.close()
 def _signature(self,record): return hmac.new(self._key,canonical_json(record),hashlib.sha256).hexdigest()
 def _trusted_actor(self,context,authenticator=None,expected_role='approver'):
  resolved=(authenticator or self._authenticate_approver)(context)
  if not isinstance(resolved,dict) or resolved.get('authenticated') is not True: raise Denied('authenticated trusted identity context required')
  if resolved.get('role') not in (None,expected_role): raise Denied(f'{expected_role} role required')
  for key in ('subject','authority_source','issuance_channel'):
   if not isinstance(resolved.get(key),str) or not resolved[key]: raise Denied('incomplete trusted identity context')
  return resolved
 def __persist_record(self,table,record_id,value,token):
  if token is not self.__issuance_token: raise Denied('record persistence requires a trusted issuer capability')
  if table not in RECORD_TABLES: raise ValueError('unsupported protected record table')
  con=self._connect()
  try: con.execute(INSERT_RECORD_SQL[table],(record_id,json.dumps(value,sort_keys=True,separators=(',',':')),self._signature(value)))
  except sqlite3.IntegrityError as exc: raise Denied('protected record identifier already exists') from exc
  finally: con.close()
  return record_id
 def load_record(self,table,record_id):
  if table not in RECORD_TABLES or not isinstance(record_id,str): return None
  con=self._connect(); row=con.execute(SELECT_RECORD_SQL[table],(record_id,)).fetchone(); con.close()
  if not row or row['revoked']: return None
  value=json.loads(row['record_json'])
  if not hmac.compare_digest(row['signature'],self._signature(value)): raise Denied(f'{table} signature invalid')
  return dict(value,_broker_signature=row['signature'],_broker_table=table)
 def verify_resolved_record(self,table,value):
  if not isinstance(value,dict): return False
  rid=value.get({'evidence':'evidence_id','reviews':'review_id','exceptions':'exception_id','policies':'task_id','acceptances':'acceptance_id'}.get(table,'record_id')); loaded=self.load_record(table,rid)
  return bool(loaded and all(loaded.get(k)==v for k,v in value.items() if not str(k).startswith('_')))
 def get_signed_record(self,table,record_id): return self._load_approval(record_id) if table=='approvals' else self.load_record(table,record_id)

 # Issuance APIs accept identifiers/requests only. Record bodies and identities come from protected, type-specific authorities.
 def issue_policy(self,task_id):
  if not isinstance(task_id,str) or not task_id: raise Denied('task ID required')
  if self._resolve_policy: record,actor=_trusted_resolution(self._resolve_policy(task_id),'policy_authority')
  else:
   path=self.policy_root/'acceptance'/f'{task_id}.json'
   try: record=json.loads(path.read_text())
   except (OSError,json.JSONDecodeError) as exc: raise Denied('protected policy asset unavailable') from exc
  validate('acceptance-policy',record); return self.__persist_record('policies',task_id,dict(record,task_id=task_id),self.__issuance_token)
 def issue_evidence(self,request):
  if not callable(self._collect_evidence): raise Denied('trusted evidence collector unavailable')
  _strict(request,('evidence_id','criterion_id',*BINDINGS))
  resolved=self._collect_evidence(json.loads(json.dumps(request)))
  if not isinstance(resolved,dict): raise Denied('trusted evidence collector returned an invalid result')
  record,actor=_trusted_resolution(resolved,'evidence_collector'); verifier=resolved.get('verifier_result')
  content=resolved.get('content')
  if resolved.get('opened') is not True or resolved.get('retention_authorized') is not True or not isinstance(content,bytes): raise Denied('evidence source was not opened and retained by trusted collector')
  if not isinstance(verifier,dict) or verifier.get('protected') is not True or verifier.get('criterion_id')!=request['criterion_id'] or verifier.get('result')!='pass' or verifier.get('relevant') is not True: raise Denied('protected criterion verifier did not pass')
  required=(*BINDINGS,'evidence_id','criterion_id','kind','source','reference','collected_at','expires_at','retention_until','result','verifier_kind')
  _strict(record,required)
  if any(record[k]!=request[k] for k in request) or record['result']!='pass' or record['verifier_kind']!=verifier.get('verifier_kind'): raise Denied('evidence binding or verifier mismatch')
  if not str(record['reference']).startswith(('file://','provider-receipt:')): raise Denied('evidence reference is not a trusted opened source')
  if _parse(record['collected_at'])>datetime.now(timezone.utc) or _parse(record['expires_at'])<=datetime.now(timezone.utc) or _parse(record['retention_until'])<_parse(record['expires_at']): raise Denied('evidence retention or time invalid')
  record.update(accessible=True,relevant=True,collector_id=actor['subject'],authority_source=actor['authority_source'],issuance_channel=actor['issuance_channel'],content_digest=_sha(content))
  return self.__persist_record('evidence',record['evidence_id'],record,self.__issuance_token)
 def issue_review(self,review_id,*,auth_context):
  if not isinstance(review_id,str) or not callable(self._resolve_review): raise Denied('trusted review resolver unavailable')
  actor=self._trusted_actor(auth_context,self._authenticate_reviewer,'reviewer'); record,resolved_actor=_trusted_resolution(self._resolve_review(review_id),'reviewer')
  if actor['subject']!=resolved_actor['subject']: raise Denied('reviewer channel identity mismatch')
  _strict(record,('review_id','result',*BINDINGS,'evidence_digest','issued_at','expires_at','retention_until'))
  record.update(reviewer_id=actor['subject'],authority_source=actor['authority_source'],issuance_channel=actor['issuance_channel']); return self.__persist_record('reviews',review_id,record,self.__issuance_token)
 def issue_exception(self,exception_id,*,auth_context):
  if not isinstance(exception_id,str) or not callable(self._resolve_exception): raise Denied('trusted exception resolver unavailable')
  actor=self._trusted_actor(auth_context,self._authenticate_exception_authority,'exception_authority'); record,resolved_actor=_trusted_resolution(self._resolve_exception(exception_id),'exception_authority')
  if actor['subject']!=resolved_actor['subject']: raise Denied('exception authority identity mismatch')
  _strict(record,('exception_id','reason','scope','issued_at','expires_at',*BINDINGS))
  if _parse(record['expires_at'])<=datetime.now(timezone.utc): raise Denied('exception is stale')
  record.update(actor_id=actor['subject'],authority_source=actor['authority_source'],issuance_channel=actor['issuance_channel']); return self.__persist_record('exceptions',exception_id,record,self.__issuance_token)
 def issue_acceptance(self,acceptance_id,*,auth_context):
  if not isinstance(acceptance_id,str) or not callable(self._resolve_acceptance): raise Denied('trusted acceptance resolver unavailable')
  record,actor=_trusted_resolution(self._resolve_acceptance(acceptance_id),'accepter')
  if record.get('acceptance_id')!=acceptance_id: raise Denied('acceptance resolver identifier mismatch')
  validate('acceptance-record',record)
  if record['status']!='accepted' or record['disposition']!='success' or record['accepter_id']!=actor['subject'] or record['reasons']: raise Denied('evaluator-issued accepted record required')
  if _parse(record['expires_at'])<=datetime.now(timezone.utc) or _parse(record['issued_at'])>datetime.now(timezone.utc): raise Denied('acceptance is stale')
  return self.__persist_record('acceptances',acceptance_id,record,self.__issuance_token)
 def issue_approval(self,record,*,auth_context):
  actor=self._trusted_actor(auth_context); value=json.loads(json.dumps(record)); value['policy_digest']=self._current_policy_digest(); value['approver']={'role':'authenticated_approver','subject':actor['subject']}; value['authority_source']=actor['authority_source']; value['issuance_channel']=actor['issuance_channel']; validate('approval-record',value)
  con=self._connect()
  try: con.execute('INSERT INTO approvals(approval_id,record_json,signature,authority_type,scope_version) VALUES(?,?,?,?,?)',(value['approval_id'],json.dumps(value,sort_keys=True),self._signature(value),value['authority_type'],int(value.get('scope_version',1))))
  except sqlite3.IntegrityError as exc: raise Denied('approval identifier already exists') from exc
  finally: con.close()
  return value['approval_id']
 def revoke_approval(self,approval_id,*,auth_context):
  self._trusted_actor(auth_context); con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE')
   if con.execute("SELECT 1 FROM operations WHERE approval_id=? AND state='dispatching'",(approval_id,)).fetchone(): raise Denied('revocation denied: effect dispatch is currently reserved')
   changed=con.execute('UPDATE approvals SET revoked=1,scope_version=scope_version+1 WHERE approval_id=? AND revoked=0',(approval_id,)).rowcount
   if changed!=1: raise Denied('approval missing or already revoked')
   con.execute('COMMIT')
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally: con.close()
 @staticmethod
 def _revoke_payload(approval_id,correction_id,predecessor,replacement): return json.dumps({'approval_id':approval_id,'correction_id':correction_id,'predecessor':predecessor,'replacement':replacement},sort_keys=True,separators=(',',':'))
 def prepare_approval_revocation(self,approval_id,*,correction_id,predecessor,replacement):
  con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE'); row=con.execute('SELECT revoked FROM approvals WHERE approval_id=?',(approval_id,)).fetchone()
   if not row or row['revoked']: raise Denied('approval missing or already revoked')
   if con.execute("SELECT 1 FROM operations WHERE approval_id=? AND state='dispatching'",(approval_id,)).fetchone(): raise Denied('revocation denied: effect dispatch is currently reserved')
   payload=self._revoke_payload(approval_id,correction_id,predecessor,replacement); signature=hmac.new(self._key,payload.encode(),hashlib.sha256).hexdigest(); existing=con.execute("SELECT * FROM approval_revocation_preparations WHERE approval_id=? AND correction_id=? AND state='prepared'",(approval_id,correction_id)).fetchone()
   if existing:
    if not hmac.compare_digest(existing['signature'],signature): raise Denied('approval preparation replay mismatch')
    intent_id=existing['intent_id']; signature=existing['signature']
   else:
    intent_id=secrets.token_urlsafe(24); con.execute("INSERT INTO approval_revocation_preparations(intent_id,approval_id,correction_id,predecessor_json,replacement_json,signature,state) VALUES(?,?,?,?,?,?,'prepared')",(intent_id,approval_id,correction_id,json.dumps(predecessor,sort_keys=True),json.dumps(replacement,sort_keys=True),signature))
   con.execute('COMMIT'); return {'intent_id':intent_id,'approval_id':approval_id,'correction_id':correction_id,'signature':signature}
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally: con.close()
 def commit_approval_revocation(self,preparation):
  con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE'); row=con.execute('SELECT * FROM approval_revocation_preparations WHERE intent_id=?',(preparation.get('intent_id'),)).fetchone()
   if not row or row['state']!='prepared': raise Denied('revocation preparation is not current')
   payload=self._revoke_payload(row['approval_id'],row['correction_id'],json.loads(row['predecessor_json']),json.loads(row['replacement_json'])); expected=hmac.new(self._key,payload.encode(),hashlib.sha256).hexdigest()
   if not hmac.compare_digest(expected,row['signature']) or not hmac.compare_digest(expected,preparation.get('signature','')): raise Denied('invalid revocation intent signature')
   if con.execute("SELECT 1 FROM operations WHERE approval_id=? AND state='dispatching'",(row['approval_id'],)).fetchone(): raise Denied('revocation denied: effect dispatch is currently reserved')
   if con.execute('UPDATE approvals SET revoked=1,scope_version=scope_version+1 WHERE approval_id=? AND revoked=0',(row['approval_id'],)).rowcount!=1: raise Denied('approval missing or already revoked')
   con.execute("UPDATE approval_revocation_preparations SET state='committed' WHERE intent_id=?",(row['intent_id'],)); con.execute('COMMIT'); approval_id=row['approval_id']
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally: con.close()
  return self.approval_status(approval_id)
 def cancel_approval_revocation(self,preparation):
  con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE'); row=con.execute('SELECT state FROM approval_revocation_preparations WHERE intent_id=?',(preparation.get('intent_id'),)).fetchone()
   if row and row['state']=='committed': raise Denied('committed revocation cannot be cancelled')
   if row: con.execute("UPDATE approval_revocation_preparations SET state='cancelled' WHERE intent_id=?",(preparation['intent_id'],))
   con.execute('COMMIT')
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally: con.close()
  return self.approval_status(preparation['approval_id'])
 def approval_status(self,approval_id):
  con=self._connect()
  try:
   approval=con.execute('SELECT revoked FROM approvals WHERE approval_id=?',(approval_id,)).fetchone()
   if approval is None: return {'approval_id':approval_id,'state':'missing'}
   if not approval['revoked']: return {'approval_id':approval_id,'state':'active'}
   result={'approval_id':approval_id,'state':'revoked'}
   prep=con.execute("SELECT correction_id,replacement_json,prepared_at FROM approval_revocation_preparations WHERE approval_id=? AND state='committed' ORDER BY prepared_at DESC LIMIT 1",(approval_id,)).fetchone()
   if prep:
    result.update(correction_id=prep['correction_id'],replacement=json.loads(prep['replacement_json']),revoked_at=prep['prepared_at'])
   return result
  finally: con.close()
 def _approval_from(self,con,approval_id):
  if not isinstance(approval_id,str): raise Denied('callers must pass an approval ID')
  row=con.execute('SELECT * FROM approvals WHERE approval_id=?',(approval_id,)).fetchone()
  if not row: raise Denied('missing approval')
  value=json.loads(row['record_json'])
  if not hmac.compare_digest(row['signature'],self._signature(value)): raise Denied('approval signature invalid')
  if row['revoked']: raise Denied('approval is cancelled or revoked')
  return value
 def _load_approval(self,approval_id):
  con=self._connect()
  try:return self._approval_from(con,approval_id)
  finally:con.close()
 def _resolve_roles(self,value,identity_context):
  trusted=self._resolve_identities(identity_context)
  if not isinstance(trusted,dict) or trusted.get('authenticated') is not True or not isinstance(trusted.get('roles'),dict): raise Denied('trusted action identity context required')
  roles=trusted['roles']
  if any(not isinstance(roles.get(n),str) or not roles[n] for n in ALL_ROLES): raise Denied('incomplete trusted role resolution')
  allowed=set()
  for pair in trusted.get('allowed_overlaps',[]):
   if not isinstance(pair,(list,tuple)) or len(pair)!=2 or any(x not in ALL_ROLES for x in pair): raise Denied('invalid policy role overlap')
   allowed.add(frozenset(pair))
  for pos,left in enumerate(ALL_ROLES):
   for right in ALL_ROLES[pos+1:]:
    if roles[left]==roles[right] and frozenset((left,right)) not in allowed: raise Denied(f'role separation required: {left}/{right}')
  for name in ('requester','executor','credential_principal','recipient'): value[name]={'role':name,'subject':roles[name]}
  value['_trusted_roles']=roles
  return value
 def _prepare(self,intent,identity_context=None,policy_digest=None):
  value=json.loads(json.dumps(intent))
  if 'acceptance' in value or not isinstance(value.get('acceptance_id'),str): raise Denied('persisted signed acceptance ID required; caller acceptance fields are forbidden')
  value=self._resolve_roles(value,identity_context); value['policy_digest']=policy_digest or self._current_policy_digest(); validate('action-intent',{k:v for k,v in value.items() if k!='_trusted_roles'})
  if value['action_class'] not in self.supported_routes: raise Denied('unsupported write route')
  return value
 def _check_acceptance(self,con,value):
  row=con.execute('SELECT record_json,signature,revoked FROM acceptances WHERE record_id=?',(value['acceptance_id'],)).fetchone()
  if not row or row['revoked']: raise Denied('current signed acceptance required')
  acc=json.loads(row['record_json'])
  if not hmac.compare_digest(row['signature'],self._signature(acc)): raise Denied('acceptance signature invalid')
  required={'task_id':value['task_id'],'task_version':value['task_version'],'requirement_version':value['requirement_version'],'artifact_id':value['artifact_id'],'artifact_version':value['artifact_version'],'target_id':value['target'],'target_version':value['target_version'],'environment':value['environment'],'policy_digest':value['policy_digest']}
  if acc.get('status')!='accepted' or any(acc.get(k)!=v for k,v in required.items()) or _parse(acc.get('expires_at'))<=datetime.now(timezone.utc): raise Denied('acceptance is stale or binding mismatch')
  roles=value['_trusted_roles']
  if acc.get('accepter_id')!=roles['accepter']: raise Denied('accepter identity mismatch')
  return acc
 def authorize(self,intent,approval_id,*,identity_context=None):
  value=self._prepare(intent,identity_context); con=self._connect()
  try:
   approval=self._approval_from(con,approval_id); acceptance=self._check_acceptance(con,value); roles=value['_trusted_roles']
   if approval.get('approver',{}).get('subject')!=roles['approver']: raise Denied('approver identity mismatch')
   used=approval['authority_type']=='one_off' and con.execute('SELECT 1 FROM approvals_used WHERE approval_id=?',(approval_id,)).fetchone() is not None
  finally:con.close()
  public={k:v for k,v in value.items() if k!='_trusted_roles'}; check(public,approval,public['policy_digest'],used=used,standing=approval['authority_type']=='standing'); return {'authorized':True,'operation_key':value['operation_key'],'intent':public}
 def _existing(self,key,fingerprint):
  con=self._connect(); row=con.execute('SELECT intent_fingerprint,effect,result_json FROM operations WHERE operation_key=?',(key,)).fetchone(); con.close()
  if not row:return None
  if row['intent_fingerprint']!=fingerprint: raise Denied('operation key intent mismatch')
  if row['effect']=='unknown': raise Denied('unknown effect requires reconciliation; retry blocked')
  return json.loads(row['result_json']) if row['result_json'] else None
 def _begin_reservation(self,value,approval_id,fingerprint):
  con=self._connect(True)
  try:
   con.execute('BEGIN IMMEDIATE')
   fresh=self._current_policy_digest()
   if fresh!=value['policy_digest']: raise Denied('protected policy changed before dispatch reservation')
   approval=self._approval_from(con,approval_id); acceptance=self._check_acceptance(con,value); roles=value['_trusted_roles']
   if approval.get('approver',{}).get('subject')!=roles['approver']: raise Denied('approver identity mismatch')
   used=approval['authority_type']=='one_off' and con.execute('SELECT 1 FROM approvals_used WHERE approval_id=?',(approval_id,)).fetchone() is not None
   public={k:v for k,v in value.items() if k!='_trusted_roles'}; check(public,approval,fresh,used=used,standing=approval['authority_type']=='standing')
   con.execute("INSERT INTO operations(operation_key,intent_json,intent_fingerprint,approval_id,acceptance_id,state) VALUES(?,?,?,?,?,'dispatching')",(value['operation_key'],json.dumps(public,sort_keys=True),fingerprint,approval_id,value['acceptance_id'])); con.execute('INSERT INTO approvals_used(approval_id,operation_key) VALUES(?,?)',(approval_id,value['operation_key'])); con.execute('COMMIT')
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   raise
  finally: con.close()
 def execute(self,intent,approval_id,handler,*,identity_context=None):
  """Reserve and commit the supported adapter effect under one SQLite writer transaction.

  Policy publication and revocation use the same writer lock, so an update before
  reservation is authoritative and an update after reservation is future-only.
  """
  if isinstance(intent,dict) and 'managed_envelope' in intent and not self.managed_mode: raise Denied('managed controller required for managed envelope')
  con=self._connect(True); effect_started=False
  try:
   con.execute('BEGIN IMMEDIATE'); authority=self._policy_from(con)
   value=self._prepare(intent,identity_context,authority['digest']); public={k:v for k,v in value.items() if k!='_trusted_roles'}; fingerprint=_digest(public)
   row=con.execute('SELECT intent_fingerprint,effect,result_json FROM operations WHERE operation_key=?',(value['operation_key'],)).fetchone()
   if row:
    if row['intent_fingerprint']!=fingerprint: raise Denied('operation key intent mismatch')
    if row['effect']=='unknown': raise Denied('unknown effect requires reconciliation; retry blocked')
    result=json.loads(row['result_json']) if row['result_json'] else None; con.execute('COMMIT'); return result
   approval=self._approval_from(con,approval_id); self._check_acceptance(con,value); roles=value['_trusted_roles']
   if approval.get('approver',{}).get('subject')!=roles['approver']: raise Denied('approver identity mismatch')
   used=approval['authority_type']=='one_off' and con.execute('SELECT 1 FROM approvals_used WHERE approval_id=?',(approval_id,)).fetchone() is not None
   check(public,approval,authority['digest'],used=used,standing=approval['authority_type']=='standing')
   con.execute("INSERT INTO operations(operation_key,intent_json,intent_fingerprint,approval_id,acceptance_id,state) VALUES(?,?,?,?,?,'dispatching')",(value['operation_key'],json.dumps(public,sort_keys=True),fingerprint,approval_id,value['acceptance_id'])); con.execute('INSERT INTO approvals_used(approval_id,operation_key) VALUES(?,?)',(approval_id,value['operation_key']))
   effect_started=True; effect='unknown'; metadata={}; receipt_digest=None; safe_readback=None
   try:
    if self.managed_mode:
     if self.managed_controller is None: raise Denied('managed controller unavailable')
     provider=self.managed_controller.dispatch(value,handler)
    else:
     if self.managed_gate is not None: self.managed_gate.check_current(value['managed_envelope'])
     provider=handler(value['material_payload'])
    if not isinstance(provider,dict): raise RuntimeError('provider result must be object')
    reject_secret_material(provider); metadata=sanitize_provider_metadata({k:v for k,v in provider.items() if k in ALLOWED_PROVIDER_KEYS})
    provider_id=provider.get('provider_id'); receipt_digest=_digest({'operation_key':value['operation_key'],'provider_id':provider_id}) if isinstance(provider_id,str) else None
    rb=provider.get('readback'); expected={'account':value['account'],'target':value['target'],'payload_digest':material_payload_digest(value['material_payload']),'task_version':value['task_version'],'requirement_version':value['requirement_version'],'policy_digest':value['policy_digest'],'operation_key':value['operation_key']}
    if isinstance(provider_id,str) and isinstance(rb,dict) and all(rb.get(k)==v for k,v in expected.items()): effect='confirmed-success'; safe_readback=expected
   except Exception:
    if self.managed_mode: raise
    metadata={}; receipt_digest=None; safe_readback=None
   receipt='opr_'+secrets.token_urlsafe(24); result={'schema_version':1,'operation_key':value['operation_key'],'effect':effect,'provider_id':receipt,'readback':safe_readback,'reconciliation_required':effect=='unknown'}; validate('action-result',result)
   con.execute('UPDATE operations SET state=?,effect=?,result_json=?,provider_metadata_json=?,provider_receipt_digest=?,updated_at=CURRENT_TIMESTAMP WHERE operation_key=?',('completed' if effect.startswith('confirmed') else 'reconciling',effect,json.dumps(result,sort_keys=True),json.dumps(metadata,sort_keys=True),receipt_digest,value['operation_key'])); con.execute('COMMIT'); return result
  except Exception:
   if con.in_transaction: con.execute('ROLLBACK')
   if self.managed_mode: raise
   if effect_started: raise RuntimeError('effect boundary failed before durable fence commit')
   raise
  finally:con.close()
 def reconcile(self,operation_key,readback,*,reconciler,effect='confirmed-success'):
  if not self._authenticate_reconciler(reconciler): raise Denied('authenticated reconciler required')
  if effect not in {'confirmed-success','confirmed-failure'}: raise Denied('invalid reconciliation effect')
  reject_secret_material(readback)
  con=self._connect(True); row=con.execute('SELECT * FROM operations WHERE operation_key=?',(operation_key,)).fetchone()
  if not row or row['effect']!='unknown':con.close(); raise Denied('operation is not reconcilable')
  if row['reconciliation_attempts']>=self.max_reconciliation_attempts:con.close(); raise Denied('reconciliation attempt limit reached')
  intent=json.loads(row['intent_json']); expected={'account':intent['account'],'target':intent['target'],'payload_digest':material_payload_digest(intent['material_payload']),'task_version':intent['task_version'],'requirement_version':intent['requirement_version'],'policy_digest':intent['policy_digest'],'operation_key':operation_key}
  if not isinstance(readback,dict) or set(readback)!=set(READBACK_KEYS) or readback!=expected:con.execute('UPDATE operations SET reconciliation_attempts=reconciliation_attempts+1 WHERE operation_key=?',(operation_key,)); con.close(); raise Denied('reconciliation readback mismatch')
  result={'schema_version':1,'operation_key':operation_key,'effect':effect,'provider_id':'opr_'+secrets.token_urlsafe(24),'readback':expected,'reconciliation_required':False}; con.execute("UPDATE operations SET state='completed',effect=?,result_json=?,reconciliation_attempts=reconciliation_attempts+1 WHERE operation_key=?",(effect,json.dumps(result,sort_keys=True),operation_key)); con.close(); return result
 def observe_kanban_transition(self,task_id,previous,current,*,acceptance):
  classification='unaccepted-direct-completion' if current=='done' and not acceptance else 'observed'; record={'task_id':task_id,'from':previous,'to':current,'classification':classification,'observer_only':True}; con=self._connect(); con.execute('INSERT INTO observations(record_json) VALUES(?)',(json.dumps(record,sort_keys=True),)); con.close(); return record
