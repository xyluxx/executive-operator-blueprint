"""Adapter-level managed-team controls backed by live native Kanban reads.

This module deliberately stores no task, claim, run, heartbeat, or lifecycle
state.  Callers inject a reader for the canonical native board and invoke the
checks immediately before protected dispatch/effects.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections import namedtuple
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, cast


class ManagedDenied(PermissionError):
    """A managed-team invariant was not satisfied."""


ModeDecision = namedtuple("ModeDecision", "mode reasons prerequisites")
Fence = namedtuple("Fence", "board task_id run_id claim_lock task_version context_digest")
Lease = namedtuple("Lease", "target owner token expires_at generation")


def select_mode(needs: Mapping[str, Any]) -> ModeDecision:
    managed_reasons = (
        "recurring_independent_lanes", "sustained_concurrency", "distinct_identities",
        "dedicated_credentials", "separate_schedules", "strong_data_boundaries", "another_host",
    )
    reasons = tuple(name for name in managed_reasons if needs.get(name))
    if reasons:
        return ModeDecision("managed-team", reasons, ("deployment-conformance",))
    return ModeDecision("single-operator", ("mixed-or-occasional-work",), ("deployment-conformance",))


_CONTROL_FIELDS = frozenset({"approval", "approval_id", "policy", "policy_digest", "authority",
                             "claim_lock", "run_id", "credential_scope", "acceptance", "signature"})


def validate_untrusted_context(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _CONTROL_FIELDS:
                raise ManagedDenied("untrusted context contains control field")
            validate_untrusted_context(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_untrusted_context(child)


class ManagedGate:
    """CAS-style guard over the canonical native Kanban snapshot."""

    def __init__(self, kanban_reader: Callable[[str, str], Mapping[str, Any]]):
        self._read = kanban_reader

    def check_current(self, envelope: Mapping[str, Any]) -> Mapping[str, Any]:
        # This fresh read is intentionally inside every check, directly before use.
        live = self._read(str(envelope.get("board")), str(envelope.get("task_id")))
        if live.get("board") != envelope.get("board"):
            raise ManagedDenied("board boundary mismatch")
        if live.get("task_id") != envelope.get("task_id"):
            raise ManagedDenied("task id mismatch")
        checks = {"client": "client", "profile": "profile", "workspace": "workspace"}
        for field, label in checks.items():
            if live.get(field) != envelope.get(field):
                raise ManagedDenied(f"{label} boundary mismatch")
        if envelope.get("credential_scope") not in (live.get("credential_scopes") or []):
            raise ManagedDenied("credential scope boundary mismatch")
        if live.get("cancelled"):
            raise ManagedDenied("task is cancelled")
        if live.get("status") != "running":
            raise ManagedDenied("task is not in a protected running run")
        if live.get("version") != envelope.get("task_version"):
            raise ManagedDenied("stale task version")
        if live.get("current_run_id") != envelope.get("run_id") or live.get("claim_lock") != envelope.get("claim_lock"):
            raise ManagedDenied("stale run or claim lock")
        if live.get("assignee") != envelope.get("actor"):
            raise ManagedDenied("actor is not current assignee")
        return live

    def fence(self, envelope: Mapping[str, Any]) -> Fence:
        live = self.check_current(envelope)
        return Fence(str(envelope["board"]), str(envelope["task_id"]), str(envelope["run_id"]),
                     str(envelope["claim_lock"]), int(envelope["task_version"]), self._context_digest(live))

    @staticmethod
    def _context_digest(live: Mapping[str, Any]) -> str:
        fields = ("assignee", "profile", "client", "workspace", "credential_scopes",
                  "requirement_version", "policy_version", "environment", "dependencies",
                  "acceptances", "children", "parent_acceptance", "parent_budget")
        return hashlib.sha256(json.dumps({key: live.get(key) for key in fields}, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()

    def check_fence(self, fence: Fence) -> Mapping[str, Any]:
        live = self._read(fence.board, fence.task_id)
        if (live.get("current_run_id"), live.get("claim_lock"), live.get("version")) != (
                fence.run_id, fence.claim_lock, fence.task_version):
            raise ManagedDenied("stale fencing token")
        if live.get("cancelled") or live.get("status") != "running":
            raise ManagedDenied("stale fencing token")
        if self._context_digest(live) != fence.context_digest:
            raise ManagedDenied("stale fencing token")
        return live


class TargetLeaseRegistry:
    """Thread-safe exact-target lease for one adapter process.

    Cross-process/provider routes must use their provider conditional write or
    OS lock; coverage remains Blocked otherwise.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock, self._lock, self._leases, self._used = clock, threading.Lock(), {}, set()

    def acquire(self, target: str, owner: str, ttl_seconds: float) -> Lease:
        if not target or ttl_seconds <= 0:
            raise ManagedDenied("exact target and positive lease duration required")
        with self._lock:
            now = self._clock(); current = self._leases.get(target)
            if current and current.expires_at > now:
                raise ManagedDenied("protected target already has a writer lease")
            token = secrets.token_urlsafe(32)
            lease = Lease(target, owner, token, now + ttl_seconds, 1)
            self._leases[target] = lease
            return lease

    def release(self, token: str, owner: str) -> None:
        with self._lock:
            matches = [lease for lease in self._leases.values()
                       if hmac.compare_digest(lease.token, token)]
            if len(matches) != 1 or matches[0].owner != owner:
                raise ManagedDenied("stale callback or fencing token")
            del self._leases[matches[0].target]

    def consume(self, token: str, owner: str) -> dict[str, object]:
        with self._lock:
            if token in self._used:
                raise ManagedDenied("duplicate callback")
            matches = [lease for lease in self._leases.values() if hmac.compare_digest(lease.token, token)]
            if len(matches) != 1 or matches[0].owner != owner or matches[0].expires_at <= self._clock():
                raise ManagedDenied("stale callback or fencing token")
            lease = matches[0]; self._used.add(token); del self._leases[lease.target]
            return {"accepted": True, "target": lease.target, "owner": owner}


class SQLiteLeaseRegistry:
    """Transactional exact-target leases shared by profile processes."""
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self.path, self._clock = Path(path), clock
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        con = sqlite3.connect(self.path)
        con.execute("CREATE TABLE IF NOT EXISTS managed_leases(target TEXT PRIMARY KEY,owner TEXT NOT NULL,token TEXT NOT NULL UNIQUE,expires_at REAL NOT NULL,generation INTEGER NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS managed_lease_generations(target TEXT PRIMARY KEY,generation INTEGER NOT NULL)")
        con.commit(); con.close()
        if os.name == "posix": os.chmod(self.path, 0o600)

    def acquire(self, target: str, owner: str, ttl_seconds: float) -> Lease:
        if not target or not owner or ttl_seconds <= 0: raise ManagedDenied("exact target, owner, and positive lease duration required")
        con=sqlite3.connect(self.path,isolation_level=None,timeout=30)
        try:
            con.execute("BEGIN IMMEDIATE"); now=self._clock()
            row=con.execute("SELECT expires_at FROM managed_leases WHERE target=?",(target,)).fetchone()
            if row and float(row[0]) > now: raise ManagedDenied("protected target already has a writer lease")
            prior=con.execute("SELECT generation FROM managed_lease_generations WHERE target=?",(target,)).fetchone()
            generation=(int(prior[0]) if prior else 0)+1; token=secrets.token_urlsafe(32); expires=now+ttl_seconds
            con.execute("INSERT INTO managed_lease_generations VALUES(?,?) ON CONFLICT(target) DO UPDATE SET generation=excluded.generation",(target,generation))
            con.execute("INSERT INTO managed_leases VALUES(?,?,?,?,?) ON CONFLICT(target) DO UPDATE SET owner=excluded.owner,token=excluded.token,expires_at=excluded.expires_at,generation=excluded.generation",(target,owner,token,expires,generation))
            con.execute("COMMIT"); return Lease(target,owner,token,expires,generation)
        except Exception:
            try: con.execute("ROLLBACK")
            except sqlite3.Error: pass
            raise
        finally: con.close()

    def current(self,target: str) -> Lease | None:
        con=sqlite3.connect(self.path)
        try: row=con.execute("SELECT target,owner,token,expires_at,generation FROM managed_leases WHERE target=?",(target,)).fetchone()
        finally: con.close()
        return Lease(*row) if row else None

    def _delete(self,token: str,owner: str,generation: int,consume: bool):
        con=sqlite3.connect(self.path,isolation_level=None,timeout=30)
        try:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("SELECT target,expires_at FROM managed_leases WHERE token=? AND owner=? AND generation=?",(token,owner,generation)).fetchone()
            if not row or (consume and float(row[1]) <= self._clock()): raise ManagedDenied("stale callback or fencing token")
            con.execute("DELETE FROM managed_leases WHERE token=? AND owner=? AND generation=?",(token,owner,generation)); con.execute("COMMIT")
            return {"accepted":True,"target":row[0],"owner":owner}
        except Exception:
            try: con.execute("ROLLBACK")
            except sqlite3.Error: pass
            raise
        finally: con.close()

    def release(self,token: str,owner: str,generation: int) -> None: self._delete(token,owner,generation,False)
    def consume(self,token: str,owner: str,generation: int) -> dict[str,object]: return self._delete(token,owner,generation,True)

    def replace(self,target: str,old_owner: str,new_owner: str,ttl_seconds: float, *, provider_generation: int) -> Lease:
        """Install a replacement lease only after its provider fence exists."""
        con=sqlite3.connect(self.path,isolation_level=None,timeout=30)
        try:
            con.execute("BEGIN IMMEDIATE"); now=self._clock()
            row=con.execute("SELECT owner,generation FROM managed_leases WHERE target=?",(target,)).fetchone()
            if not row or row[0] != old_owner: raise ManagedDenied("active action lease owner mismatch")
            generation=int(row[1])+1
            if int(provider_generation) != generation: raise ManagedDenied("provider fence was not atomically invalidated")
            token=secrets.token_urlsafe(32); expires=now+ttl_seconds
            con.execute("UPDATE managed_lease_generations SET generation=? WHERE target=?",(generation,target))
            con.execute("UPDATE managed_leases SET owner=?,token=?,expires_at=?,generation=? WHERE target=?",
                        (new_owner,token,expires,generation,target)); con.execute("COMMIT")
            return Lease(target,new_owner,token,expires,generation)
        except Exception:
            try: con.execute("ROLLBACK")
            except sqlite3.Error: pass
            raise
        finally: con.close()

    def detect_direct_reassignment(self,target: str,*,observed_owner: str) -> None:
        current=self.current(target)
        if current and current.owner != observed_owner:
            raise ManagedDenied("direct native reassignment is unsupported/Blocked; reconcile through controlled fence invalidation")


class ManagedWriteAdapter(ABC):
    """Reviewed contract whose mutation enforces provider fencing atomically."""
    atomic_fencing_conformance="managed-write-v1"
    @abstractmethod
    def arm_fence(self, *, target: str, fencing_generation: int) -> None: raise NotImplementedError
    @abstractmethod
    def mutate(self,payload: Mapping[str,Any],*,target: str,operation_key: str,fencing_generation: int) -> Mapping[str,Any]: raise NotImplementedError


class LocalSQLiteManagedWriteAdapter(ManagedWriteAdapter):
    """Concrete local provider whose fence CAS and effect share one database."""
    def __init__(self,path: str | Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        con=sqlite3.connect(self.path); con.execute("CREATE TABLE IF NOT EXISTS effects(target TEXT PRIMARY KEY,payload TEXT NOT NULL,operation_key TEXT NOT NULL UNIQUE,generation INTEGER NOT NULL)"); con.execute("CREATE TABLE IF NOT EXISTS provider_fences(target TEXT PRIMARY KEY,generation INTEGER NOT NULL)"); con.commit(); con.close()
    def arm_fence(self,*,target,fencing_generation):
        con=sqlite3.connect(self.path,isolation_level=None)
        try:
            con.execute("BEGIN IMMEDIATE"); row=con.execute("SELECT generation FROM provider_fences WHERE target=?",(target,)).fetchone()
            if row and int(row[0]) >= int(fencing_generation): raise ManagedDenied("stale provider fence")
            con.execute("INSERT INTO provider_fences VALUES(?,?) ON CONFLICT(target) DO UPDATE SET generation=excluded.generation",(target,int(fencing_generation))); con.execute("COMMIT")
        except Exception:
            try: con.execute("ROLLBACK")
            except sqlite3.Error: pass
            raise
        finally: con.close()
    def mutate(self,payload,*,target,operation_key,fencing_generation):
        con=sqlite3.connect(self.path,isolation_level=None)
        try:
            con.execute("BEGIN IMMEDIATE")
            duplicate=con.execute("SELECT payload FROM effects WHERE operation_key=?",(operation_key,)).fetchone()
            if duplicate: con.execute("COMMIT"); return {"provider_id":operation_key,"payload":json.loads(duplicate[0])}
            fence=con.execute("SELECT generation FROM provider_fences WHERE target=?",(target,)).fetchone()
            if not fence or int(fence[0]) != int(fencing_generation): raise ManagedDenied("stale provider fence")
            con.execute("INSERT INTO effects VALUES(?,?,?,?) ON CONFLICT(target) DO UPDATE SET payload=excluded.payload,operation_key=excluded.operation_key,generation=excluded.generation",(target,json.dumps(payload,sort_keys=True),operation_key,int(fencing_generation)))
            con.execute("COMMIT"); return {"provider_id":operation_key,"payload":dict(payload)}
        except Exception:
            try: con.execute("ROLLBACK")
            except sqlite3.Error: pass
            raise
        finally: con.close()
    def invalidate_for_replacement(self,*,target,expected_generation,new_generation):
        con=sqlite3.connect(self.path,isolation_level=None)
        try:
            con.execute("BEGIN IMMEDIATE")
            changed=con.execute("UPDATE provider_fences SET generation=? WHERE target=? AND generation=?",
                                (int(new_generation),target,int(expected_generation))).rowcount
            if changed != 1: raise ManagedDenied("stale provider fence")
            con.execute("COMMIT"); return int(new_generation)
        except Exception:
            try: con.execute("ROLLBACK")
            except sqlite3.Error: pass
            raise
        finally: con.close()
    def read(self,target):
        con=sqlite3.connect(self.path); row=con.execute("SELECT payload,generation,operation_key FROM effects WHERE target=?",(target,)).fetchone(); con.close()
        return {"payload":json.loads(row[0]),"generation":row[1],"operation_key":row[2]} if row else None


AdapterRegistryRecord = namedtuple("AdapterRegistryRecord",
    "name implementation_identity code_digest provider_capability public_key conformance_receipt")


def _implementation_digest(cls: type) -> str:
    """Digest executable adapter methods, including constants and names."""
    pieces=[]
    for name in ("__init__","arm_fence","mutate","invalidate_for_replacement","read"):
        code=getattr(cls,name).__code__
        pieces.append({"name":name,"bytecode":code.co_code.hex(),"constants":repr(code.co_consts),
                       "names":code.co_names,"variables":code.co_varnames})
    return hashlib.sha256(json.dumps(pieces,sort_keys=True,default=list).encode()).hexdigest()


class ProtectedAdapterRegistry:
    """Process-owned allowlist binding exact instances to reviewed implementation code."""
    def __init__(self, entries: Mapping[str, tuple[object, AdapterRegistryRecord]]):
        self._entries=MappingProxyType(dict(entries))
        self._instance_state={name: MappingProxyType(dict(vars(adapter))) for name,(adapter,_) in entries.items()}
    def adapter(self,name: str) -> object: return self._entries[name][0]
    def validate(self,adapter: object) -> None:
        found=[(name,record) for name,(candidate,record) in self._entries.items() if candidate is adapter]
        if len(found) != 1: raise ManagedDenied("managed provider adapter lacks protected adapter registry conformance")
        name,record=found[0]
        if type(adapter) is not LocalSQLiteManagedWriteAdapter or vars(adapter) != dict(self._instance_state[name]):
            raise ManagedDenied("adapter identity differs from protected adapter registry")
        identity=f"{type(adapter).__module__}.{type(adapter).__qualname__}"
        digest=_implementation_digest(type(adapter))
        capability=dict(record.provider_capability); receipt=dict(record.conformance_receipt)
        signature=str(receipt.pop("signature",""))
        signed={"name":record.name,"implementation_identity":record.implementation_identity,
                "code_digest":record.code_digest,"provider_capability":capability,"public_key":record.public_key,
                "receipt":receipt}
        expected=hashlib.sha256((json.dumps(signed,sort_keys=True,separators=(",",":"))+record.public_key).encode()).hexdigest()
        if (identity != record.implementation_identity or digest != record.code_digest
                or capability.get("atomic_fencing") is not True or capability.get("idempotency_key") is not True
                or not record.public_key or receipt.get("contract") != "managed-write-v1"
                or not hmac.compare_digest(signature,expected)):
            raise ManagedDenied("adapter record or conformance receipt invalid in protected adapter registry")


def protected_local_adapter_registry(path: str | Path) -> ProtectedAdapterRegistry:
    adapter=LocalSQLiteManagedWriteAdapter(path)
    identity=f"{LocalSQLiteManagedWriteAdapter.__module__}.{LocalSQLiteManagedWriteAdapter.__qualname__}"
    digest=_implementation_digest(LocalSQLiteManagedWriteAdapter)
    capability=MappingProxyType({"provider":"local-sqlite","atomic_fencing":True,"idempotency_key":True})
    public_key="local-conformance-root-v1"
    receipt={"contract":"managed-write-v1","suite":"tests/test_managed_adapter_integration.py"}
    signed={"name":"local-sqlite","implementation_identity":identity,"code_digest":digest,
            "provider_capability":dict(capability),"public_key":public_key,"receipt":receipt}
    receipt=dict(receipt,signature=hashlib.sha256((json.dumps(signed,sort_keys=True,separators=(",",":"))+public_key).encode()).hexdigest())
    record=AdapterRegistryRecord("local-sqlite",identity,digest,capability,public_key,MappingProxyType(receipt))
    return ProtectedAdapterRegistry({"local-sqlite":(adapter,record)})


class DependencyGraph:
    def __init__(self, parents: Mapping[str, list[str]] | None = None):
        self.parents = {node: list(edges) for node, edges in (parents or {}).items()}
        self._assert_acyclic()

    def add_dependency(self, task: str, parent: str) -> None:
        old = list(self.parents.get(task, [])); self.parents.setdefault(task, []).append(parent)
        try: self._assert_acyclic()
        except Exception:
            self.parents[task] = old
            raise

    def _assert_acyclic(self) -> None:
        visiting, visited = set(), set()
        def visit(node: str) -> None:
            if node in visiting: raise ManagedDenied("dependency cycle rejected")
            if node in visited: return
            visiting.add(node)
            for parent in self.parents.get(node, []): visit(parent)
            visiting.remove(node); visited.add(node)
        for node in tuple(self.parents): visit(node)


class AcceptanceSigner:
    def __init__(self, key: bytes):
        if len(key) < 32: raise ValueError("acceptance signing key must be at least 32 bytes")
        self.key = key

    @staticmethod
    def _bytes(value: Mapping[str, Any]) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, payload: Mapping[str, Any]) -> dict[str, object]:
        record = deepcopy(dict(payload)); record["algorithm"] = "hmac-sha256"
        record["signature"] = hmac.new(self.key, self._bytes(record), hashlib.sha256).hexdigest()
        return record

    def verify(self, record: Mapping[str, Any]) -> bool:
        unsigned = dict(record); signature = str(unsigned.pop("signature", ""))
        return bool(signature) and hmac.compare_digest(signature, hmac.new(self.key, self._bytes(unsigned), hashlib.sha256).hexdigest())


_UPSTREAM_BINDINGS = ("task_id", "requirement_version", "artifact_id", "artifact_version",
                      "outcome_id", "outcome_version", "policy_version", "environment")


def require_upstreams(required: list[Mapping[str, Any]], records: list[Mapping[str, Any]], verify: Callable[[Mapping[str, Any]], bool]) -> None:
    for item in required:
        keys = tuple(k for k in _UPSTREAM_BINDINGS if k in item)
        matches = [record for record in records if all(record.get(k) == item.get(k) for k in keys)]
        if (len(matches) != 1 or matches[0].get("accepted") is not True
                or matches[0].get("revoked") is True or not verify(matches[0])):
            raise ManagedDenied("signed accepted upstream outcome and artifact version required")


class NativeKanbanReader:
    """Read-only adapter for the installed Hermes native Kanban SQLite schema."""

    def __init__(self, db_path: str | Path, *, board: str):
        self.db_path, self.board = Path(db_path), board

    def read(self, board: str, task_id: str) -> Mapping[str, Any]:
        if board != self.board:
            raise ManagedDenied("board boundary mismatch")
        uri = f"file:{self.db_path}?mode=ro"
        con = sqlite3.connect(uri, uri=True); con.row_factory = sqlite3.Row
        try:
            con.execute("BEGIN")
            task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                raise ManagedDenied("native Kanban task missing")
            run = None
            if task["current_run_id"] is not None:
                run = con.execute("SELECT * FROM task_runs WHERE id=? AND task_id=?",
                                  (task["current_run_id"], task_id)).fetchone()
            if not run:
                raise ManagedDenied("native Kanban current run missing")
            metadata = json.loads(run["metadata"] or "{}")
            event = con.execute("SELECT COALESCE(MAX(id),0) FROM task_events WHERE task_id=?", (task_id,)).fetchone()[0]
            result = dict(metadata)
            result.update({"board": board, "task_id": task_id, "status": task["status"],
                           "version": int(event), "current_run_id": str(task["current_run_id"]),
                           "claim_lock": task["claim_lock"], "assignee": task["assignee"],
                           "profile": run["profile"], "client": metadata.get("client", task["tenant"]),
                           "workspace": task["workspace_path"], "cancelled": bool(metadata.get("cancelled", False))})
            return result
        finally:
            con.close()

    __call__ = read


class SQLiteBudgetLedger:
    """Cross-process admission ledger; stores budget reservations, not tasks."""

    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        con = sqlite3.connect(self.path)
        con.execute("CREATE TABLE IF NOT EXISTS reservations(board TEXT, task_id TEXT, operation_key TEXT PRIMARY KEY, amount REAL NOT NULL)")
        con.commit(); con.close()
        if os.name == "posix": os.chmod(self.path, 0o600)

    def reserve(self, board: str, task_id: str, operation_key: str, amount: float,
                *, total: float, spent: float, verification_reserve: float) -> None:
        con = sqlite3.connect(self.path, isolation_level=None)
        try:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT amount FROM reservations WHERE operation_key=?", (operation_key,)).fetchone()
            if existing:
                if float(existing[0]) != amount: raise ManagedDenied("operation budget reservation mismatch")
                con.execute("COMMIT"); return
            reserved = float(con.execute("SELECT COALESCE(SUM(amount),0) FROM reservations WHERE board=? AND task_id=?",
                                         (board, task_id)).fetchone()[0])
            if amount < 0 or spent + reserved + amount > total - verification_reserve:
                raise ManagedDenied("shared parent budget or verification reserve exceeded")
            con.execute("INSERT INTO reservations VALUES(?,?,?,?)", (board, task_id, operation_key, amount))
            con.execute("COMMIT")
        except Exception:
            try: con.execute("ROLLBACK")
            except sqlite3.Error: pass
            raise
        finally: con.close()

    def spent(self, board: str, task_id: str) -> float:
        con = sqlite3.connect(self.path)
        try:
            return float(con.execute("SELECT COALESCE(SUM(amount),0) FROM reservations WHERE board=? AND task_id=?",
                                     (board, task_id)).fetchone()[0])
        finally: con.close()


class ManagedController:
    """Authoritative managed admission and provider-adapter dispatch path."""

    def __init__(self, native_reader: Callable[[str, str], Mapping[str, Any]] | None, *,
                 acceptance_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
                 acceptance_reader: Callable[[str], Mapping[str, Any] | None] | None = None,
                 leases: SQLiteLeaseRegistry | None = None, budget_ledger: SQLiteBudgetLedger | None = None,
                 adapter_registry: ProtectedAdapterRegistry | None = None):
        if native_reader is None:
            raise ValueError("native reader is required in managed mode")
        if budget_ledger is None:
            raise ValueError("shared budget ledger is required in managed mode")
        self.gate = ManagedGate(native_reader)
        self.leases = leases or SQLiteLeaseRegistry(budget_ledger.path.with_name("managed-leases.db"))
        self.budget_ledger = budget_ledger
        self.verify_acceptance = acceptance_verifier or (lambda _record: False)
        self.read_acceptance = acceptance_reader or (lambda _task_id: None)
        self.adapter_registry = adapter_registry

    def budget_spent(self, board: str, task_id: str) -> float:
        return self.budget_ledger.spent(board, task_id)

    @staticmethod
    def validate_adapter(adapter: object, registry: ProtectedAdapterRegistry | None = None) -> None:
        if registry is None:
            raise ManagedDenied("managed provider adapter lacks protected adapter registry conformance")
        registry.validate(adapter)

    def replace_active_run(self,*,target: str,old_owner: str,new_owner: str,adapter: object,
                           ttl_seconds: float) -> Lease:
        self.validate_adapter(adapter,self.adapter_registry)
        current=self.leases.current(target)
        if current is None or current.owner != old_owner: raise ManagedDenied("active action lease owner mismatch")
        new_generation=current.generation+1
        provider_generation=cast(LocalSQLiteManagedWriteAdapter,adapter).invalidate_for_replacement(
            target=target,expected_generation=current.generation,new_generation=new_generation)
        return self.leases.replace(target,old_owner,new_owner,ttl_seconds,provider_generation=provider_generation)

    def _require_current_upstreams(self, live: Mapping[str, Any], board: str) -> None:
        for dependency in list(live.get("dependencies") or []):
            upstream = self.gate._read(board, str(dependency.get("task_id")))
            if any(upstream.get(k) != dependency.get(k) for k in _UPSTREAM_BINDINGS if k in dependency):
                raise ManagedDenied("current native upstream binding required")
            record = self.read_acceptance(str(dependency.get("task_id")))
            if not isinstance(record, Mapping):
                raise ManagedDenied("broker-owned signed upstream acceptance required")
            require_upstreams([dependency], [record], self.verify_acceptance)

    def check_admission(self, intent: Mapping[str, Any]) -> Mapping[str, Any]:
        envelope = intent.get("managed_envelope")
        if not isinstance(envelope, Mapping):
            raise ManagedDenied("managed envelope required")
        if envelope.get("target") != intent.get("target"):
            raise ManagedDenied("exact target mismatch")
        live = self.gate.check_current(envelope)
        if live.get("requirement_version") != intent.get("requirement_version"):
            raise ManagedDenied("stale requirement version")
        for field in ("policy_version", "environment"):
            if live.get(field) != envelope.get(field):
                raise ManagedDenied(f"stale {field.replace('_', ' ')}")
        self._require_current_upstreams(live, str(envelope["board"]))
        children = list(live.get("children") or [])
        if children:
            accept_parent(children, live.get("parent_acceptance"))
        return live

    def check_effect_boundary(self, intent: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.check_admission(intent)

    def dispatch(self, intent: Mapping[str, Any], adapter: object) -> Mapping[str, Any]:
        self.validate_adapter(adapter,self.adapter_registry)
        live = self.check_admission(intent)
        envelope = intent["managed_envelope"]
        amount = float(envelope.get("budget_amount", 0))
        budget = live.get("parent_budget") or {}
        self.budget_ledger.reserve(str(envelope["board"]), str(envelope["task_id"]), str(intent["operation_key"]), amount,
                                   total=float(budget.get("total", 0)), spent=float(budget.get("spent", 0)),
                                   verification_reserve=float(budget.get("verification_reserve", 0)))
        owner = f"{envelope['run_id']}:{envelope['claim_lock']}"
        lease = self.leases.acquire(str(envelope.get("target")), owner, float(envelope.get("lease_ttl_seconds", 30)))
        consumed = False
        try:
            cast(ManagedWriteAdapter, adapter).arm_fence(target=str(intent["target"]), fencing_generation=lease.generation)
            self.check_effect_boundary(intent)
            result = cast(ManagedWriteAdapter, adapter).mutate(intent["material_payload"], target=str(intent["target"]),
                                    operation_key=str(intent["operation_key"]), fencing_generation=lease.generation)
            result=dict(result)
            result["readback"]={"account":intent["account"],"target":intent["target"],
                "payload_digest":hashlib.sha256(json.dumps(intent["material_payload"],sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                "task_version":intent["task_version"],"requirement_version":intent["requirement_version"],
                "policy_digest":intent["policy_digest"],"operation_key":intent["operation_key"]}
            self.leases.consume(lease.token, owner, lease.generation); consumed = True
            return result
        finally:
            if not consumed:
                try: self.leases.release(lease.token, owner, lease.generation)
                except ManagedDenied: pass


def descendant_authority(_parent: Mapping[str, Any]) -> dict[str, object]:
    return {}  # approvals are deliberately non-inheritable


def accept_parent(children: list[Mapping[str, Any]], integrated: Mapping[str, Any] | None) -> bool:
    if not children or any(child.get("accepted") is not True for child in children):
        raise ManagedDenied("all children require acceptance")
    if not integrated or integrated.get("accepted") is not True:
        raise ManagedDenied("integrated parent acceptance required")
    checks = integrated.get("integration_checks") or {}
    if checks.get("compatibility") is not True: raise ManagedDenied("integrated compatibility failed")
    if checks.get("merge_tests") is not True: raise ManagedDenied("merge regression failed")
    return True


_PRESERVED = ("total_budget", "spent", "deadline", "repair_history")

def validate_reassignment(previous: Mapping[str, Any], replacement: Mapping[str, Any]) -> None:
    for field in _PRESERVED:
        if replacement.get(field) != previous.get(field):
            raise ManagedDenied(f"reassignment changed {field}")


def reassign(task: Mapping[str, Any], assignee: str) -> dict[str, object]:
    result = deepcopy(dict(task)); result["assignee"] = assignee; validate_reassignment(task, result); return result


class BudgetGuard:
    def __init__(self, total: float, verification_reserve: float):
        if total < 0 or verification_reserve < 0 or verification_reserve > total: raise ValueError("invalid budget")
        self.total, self.verification_reserve, self._work, self._verification = total, verification_reserve, 0.0, 0.0
        self._lock = threading.Lock()

    def admit(self, amount: float) -> bool:
        with self._lock:
            if amount < 0 or self._work + amount > self.total - self.verification_reserve: return False
            self._work += amount; return True

    @property
    def available_for_work(self) -> float:
        with self._lock: return self.total - self.verification_reserve - self._work


def invalidate_affected(results: Mapping[str, Mapping[str, Any]], current_inputs: Mapping[str, str]) -> dict[str, Mapping[str, Any]]:
    return {criterion: value for criterion, value in results.items()
            if all(current_inputs.get(name) == version for name, version in (value.get("input_versions") or {}).items())}


def authorize_dispatch(task: Mapping[str, Any]) -> bool:
    if task.get("cancelled"): raise ManagedDenied("task is cancelled; protected dispatch blocked")
    return True


def cancel_task(task: Mapping[str, Any], *, revoke: Callable[[], object], reconcile: Callable[[str], str]) -> dict[str, object]:
    result = deepcopy(dict(task)); result["cancelled"] = True; revoke()
    for effect in result.get("issued_effects", []):
        if effect.get("effect") == "unknown": effect["effect"] = reconcile(str(effect["operation_key"]))
    return result


def retry_allowed(result: Mapping[str, Any], *, attempts: int, max_attempts: int) -> bool:
    if result.get("effect") == "unknown": raise ManagedDenied("unknown external effect requires reconciliation before retry")
    return result.get("effect") == "confirmed-failure" and attempts < max_attempts


def retire_specialist(contract: Mapping[str, Any], *, plan_path: str | Path,
                      disable_schedule: Callable[[str], object], schedule_disabled: Callable[[str], bool],
                      revoke_credential: Callable[[str], object], credential_revoked: Callable[[str], bool],
                      transfer_task: Callable[[str, str], object], task_owner: Callable[[str], str],
                      preserve_evidence: Callable[[str], object], evidence_preserved: Callable[[str], bool],
                      resume_test: Callable[[str, list[str]], bool],
                      enable_schedule: Callable[[str], object] | None = None,
                      restore_task: Callable[[str, str], object] | None = None,
                      restore_credential: Callable[[str], object] | None = None,
                      credential_restored: Callable[[str], bool] | None = None,
                      disable_credential: Callable[[str], object] | None = None,
                      credential_disabled: Callable[[str], bool] | None = None,
                      credential_preflight: Callable[[str], bool] | None = None,
                      credential_restore_preflight: Callable[[str], bool] | None = None) -> dict[str, object]:
    """Execute and journal a reversible-first retirement plan.

    Credentials are the sole irreversible stage and are revoked only after
    every reversible stage has passed provider readback and resume testing.
    """
    path = Path(plan_path); path.parent.mkdir(parents=True, exist_ok=True)
    owner = str(contract["main_operator"]); old_owner = str(contract["specialist_id"])
    tasks = [str(x) for x in contract.get("task_ids", [])]
    schedules = [str(x) for x in contract.get("schedule_ids", [])]
    credentials = [str(x) for x in contract.get("credential_references", [])]
    # Refuse a plan before its first mutation unless every mutable stage has a rollback.
    if schedules and enable_schedule is None:
        raise ManagedDenied("retirement Blocked: schedule rollback unavailable")
    if tasks and restore_task is None:
        raise ManagedDenied("retirement Blocked: task rollback unavailable")
    if credentials:
        if not all((restore_credential, credential_restored, disable_credential, credential_disabled,
                    credential_preflight, credential_restore_preflight)):
            raise ManagedDenied("retirement Blocked: credential compensation unavailable")
        if any(not cast(Callable[[str],bool],credential_preflight)(item)
               or not cast(Callable[[str],bool],credential_restore_preflight)(item) for item in credentials):
            raise ManagedDenied("retirement Blocked: credential preflight failed")
        preflight_changed: list[str]=[]
        for item in credentials:
            try:
                cast(Callable[[str],object],disable_credential)(item); preflight_changed.append(item)
                if not cast(Callable[[str],bool],credential_disabled)(item): raise ManagedDenied("credential disable readback failed")
                cast(Callable[[str],object],restore_credential)(item)
                if not cast(Callable[[str],bool],credential_restored)(item): raise ManagedDenied("credential restore readback failed")
                preflight_changed.remove(item)
            except Exception as exc:
                compensation_failures=[]
                for preflight_item in reversed(preflight_changed):
                    try:
                        cast(Callable[[str],object],restore_credential)(preflight_item)
                        if not cast(Callable[[str],bool],credential_restored)(preflight_item):
                            compensation_failures.append(preflight_item)
                    except Exception:
                        compensation_failures.append(preflight_item)
                if compensation_failures:
                    raise ManagedDenied("retirement Blocked: credential preflight compensation failed") from exc
                raise ManagedDenied("retirement Blocked: credential preflight failed") from exc
    state: dict[str, Any] = {"version": 1, "status": "running", "contract": dict(contract), "completed": []}
    def persist() -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True)); os.replace(temporary, path)
    def done(stage: str, item: str) -> None:
        state["completed"].append({"stage": stage, "item": item}); persist()
    persist()
    try:
        for item in schedules:
            disable_schedule(item)
            if not schedule_disabled(item): raise ManagedDenied("schedule shutdown readback failed")
            done("schedule-disabled", item)
        for item in tasks:
            transfer_task(item, owner)
            if task_owner(item) != owner: raise ManagedDenied("task transfer readback failed")
            done("task-transferred", item)
        for raw in contract.get("evidence_references", []):
            item = str(raw); preserve_evidence(item)
            if not evidence_preserved(item): raise ManagedDenied("evidence preservation readback failed")
            done("evidence-preserved", item)
        if not resume_test(owner, tasks): raise ManagedDenied("main operator resume test failed")
        done("operator-resumed", owner)
        if credentials:
            changed: list[str] = []
            try:
                for item in credentials:
                    changed.append(item); revoke_credential(item)
                    if not credential_revoked(item): raise ManagedDenied("credential revocation readback failed")
                    done("credential-revoked", item)
            except Exception as credential_exc:
                failures=[]
                for item in reversed(changed):
                    try:
                        restore_credential(item)  # type: ignore[misc]
                        if not credential_restored(item): failures.append(item)  # type: ignore[misc]
                    except Exception: failures.append(item)
                if failures: raise ManagedDenied("credential compensation failed; manual reconciliation required") from credential_exc
                raise ManagedDenied("credential failure compensated; retirement Blocked") from credential_exc
    except Exception as exc:
        compensated = isinstance(exc, ManagedDenied) and "credential failure compensated" in str(exc)
        compensation_errors = []
        for step in reversed(state["completed"]):
            try:
                if step["stage"] == "task-transferred" and restore_task: restore_task(step["item"], old_owner)
                elif step["stage"] == "schedule-disabled" and enable_schedule: enable_schedule(step["item"])
            except Exception as compensation_exc:
                compensation_errors.append(type(compensation_exc).__name__)
        state.update({"status": "blocked-compensated" if compensated and not compensation_errors else "reconciliation-required", "failure": type(exc).__name__,
                      "compensation_errors": compensation_errors}); persist()
        if compensated and not compensation_errors:
            raise ManagedDenied("credential failure compensated; retirement Blocked") from exc
        raise ManagedDenied("partial retirement requires reconciliation") from exc
    state["status"] = "complete"; persist()
    return {"retired": True, "resumable": True, "owner": owner, "plan_path": str(path)}
