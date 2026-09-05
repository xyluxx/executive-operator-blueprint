import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "plugins" / "operator-control" / "corrections.py"
SCHEMA_PATH = ROOT / "templates" / "correction-record.schema.json"


def load_corrections():
    spec = importlib.util.spec_from_file_location("operator_control_corrections", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AuthorityAdapter:
    """Persistent test adapter standing in for an existing authority."""

    def __init__(self, name, events=None):
        self.name = name
        self.claims = {}
        self.events = events if events is not None else []
        self.writes = []

    def seed(self, target, claim_id="claim-old", content="old", version=1):
        self.claims[target] = {
            "claim_id": claim_id,
            "content": content,
            "version": version,
            "superseded_by": None,
        }

    def current_claim(self, target):
        return deepcopy(self.claims.get(target))

    def apply_correction(self, record):
        key = record["target"]["authority_id"]
        self.events.append(f"authority:{self.name}")
        self.writes.append(deepcopy(record))
        old = self.claims.get(key)
        if old:
            old["superseded_by"] = record["replacement"]["claim_id"]
        self.claims[key] = {
            "claim_id": record["replacement"]["claim_id"],
            "content": record["replacement"]["content"],
            "version": record["prior_claim"]["version"] + 1,
            "superseded_by": None,
            "correction_id": record["correction_id"],
            "source": deepcopy(record["source"]),
            "recorded_at": record["recorded_at"],
            "effective_at": record["effective_at"],
            "field": record["target"]["field"],
            "reason": record["reason"],
            "source_event_id": record["source_event_id"],
        }
        return {"authority": self.name, "version": self.claims[key]["version"]}

    def retract_correction(self, record):
        key = record["target"]["authority_id"]
        self.events.append(f"retract:{self.name}")
        self.writes.append(deepcopy(record))
        current = self.claims[key]
        current["superseded_by"] = record["replacement"]["claim_id"]
        self.claims[key] = {
            "claim_id": record["replacement"]["claim_id"],
            "content": record["replacement"]["content"],
            "version": current["version"] + 1,
            "superseded_by": None,
            "correction_id": record["correction_id"],
            "source_event_id": record["source_event_id"],
            "source": deepcopy(record["source"]),
            "recorded_at": record["recorded_at"],
            "effective_at": record["effective_at"],
            "field": record["target"]["field"],
            "reason": record["reason"],
        }
        return {"authority": self.name, "version": self.claims[key]["version"]}


class ImpactAdapter:
    def __init__(self, items=(), events=None):
        self.items = list(items)
        self.actions = []
        self.events = events if events is not None else []

    def active_items(self, *, client_id, scope):
        return deepcopy([item for item in self.items if item["client_id"] == client_id])

    def apply_impact(self, impact, *, correction_id):
        self.events.append(f"impact:{impact['kind']}:{impact['entity_id']}")
        self.actions.append((correction_id, deepcopy(impact)))


class ApprovalBroker(AuthorityAdapter):
    def prepare_withdrawal(self, record):
        self.events.append("approval-prepared")
        self.prepared = deepcopy(record)
        return {"intent_id": "intent-1"}

    def commit_withdrawal(self, record, preparation):
        self.events.append("approval-withdrawn")
        self.withdrawals = getattr(self, "withdrawals", set())
        self.withdrawals.add((record["target"]["authority_id"], record["correction_id"]))

    def cancel_withdrawal(self, record, preparation):
        self.events.append("approval-cancelled")

    def apply_correction(self, record):
        return super().apply_correction(record)

    def rollback_correction(self, record, prior):
        self.claims[record["target"]["authority_id"]] = deepcopy(prior)

    def verify_withdrawal(self, authority_id, correction_id):
        return (authority_id, correction_id) in getattr(self, "withdrawals", set())


def correction(destination="task_requirement", **updates):
    value = {
        "schema_version": 1,
        "correction_id": "corr-001",
        "source_event_id": "evt-001",
        "operation": "correct",
        "destination": destination,
        "durability": "durable",
        "explicit": True,
        "confirmed": True,
        "recorded_at": "2026-09-05T12:00:00Z",
        "effective_at": "2026-09-05T12:00:00Z",
        "client_id": "client-a",
        "source": {
            "kind": "authenticated_user",
            "source_id": "message-42",
            "authenticated_subject": "principal-a",
        },
        "scope": {"project_id": "project-a", "lane": "delivery"},
        "target": {
            "authority_id": "task-7",
            "field": "requirement.location",
            "exact_scope": "task-7.requirement.location",
        },
        "prior_claim": {"claim_id": "claim-old", "version": 1},
        "replacement": {"claim_id": "claim-new", "content": "Austin office"},
        "reason": "Principal corrected the location.",
        "privacy": {"contains_secret": False},
    }
    value.update(updates)
    return value


def service(*, task=None, project=None, memory=None, voice=None, approval=None, impact=None, ledger=None):
    module = load_corrections()
    return module.CorrectionService(
        authorities={
            "task_requirement": task or AuthorityAdapter("kanban"),
            "project_fact": project or AuthorityAdapter("project-registry"),
            "principal_preference": memory or AuthorityAdapter("profile-memory"),
            "voice": voice or AuthorityAdapter("voice-profile"),
            "approval": approval or ApprovalBroker("approval-broker"),
        },
        impact_adapter=impact or ImpactAdapter(),
        idempotency=ledger if ledger is not None else {},
    )


def test_schema_requires_provenance_prior_claim_exact_scope_and_target():
    schema = json.loads(SCHEMA_PATH.read_text())
    assert schema["$id"] == "https://raw.githubusercontent.com/xyluxx/executive-operator-blueprint/main/templates/correction-record.schema.json"
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(correction(), schema, format_checker=jsonschema.FormatChecker())
    for path in (("source", "source_id"), ("prior_claim", "claim_id"), ("target", "exact_scope")):
        invalid = correction()
        del invalid[path[0]][path[1]]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


def test_routes_each_durable_kind_to_existing_authority_and_session_clarification_nowhere():
    adapters = {name: AuthorityAdapter(name) for name in ("task_requirement", "project_fact", "principal_preference", "voice", "approval")}
    adapters["approval"] = ApprovalBroker("approval")
    impact = ImpactAdapter()
    module = load_corrections()
    engine = module.CorrectionService(authorities=adapters, impact_adapter=impact, idempotency={})
    for index, destination in enumerate(adapters):
        record = correction(destination, correction_id=f"corr-{index}", source_event_id=f"evt-{index}")
        adapters[destination].seed("task-7")
        engine.record(record)
        assert len(adapters[destination].writes) == 1
    before = sum(len(adapter.writes) for adapter in adapters.values())
    result = engine.record(correction("session_clarification", correction_id="session-1", source_event_id="session-event", durability="session"))
    assert result["durable"] is False
    assert sum(len(adapter.writes) for adapter in adapters.values()) == before
    assert not impact.actions


def test_ambiguous_or_implicit_durable_correction_requires_explicit_confirmation():
    engine = service()
    with pytest.raises(ValueError, match="explicit confirmation"):
        engine.record(correction(confirmed=False))
    with pytest.raises(ValueError, match="explicit correction"):
        engine.record(correction(explicit=False))


def test_idempotent_by_correction_id_and_source_event_and_conflict_is_monotonic():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    ledger = {}
    engine = service(task=task, ledger=ledger)
    first = engine.record(correction())
    assert engine.record(correction()) == first
    replay = correction(correction_id="corr-replay")
    with pytest.raises(ValueError, match="replay payload"):
        engine.record(replay)
    assert len(task.writes) == 1

    newer = correction(
        correction_id="corr-002",
        source_event_id="evt-002",
        recorded_at="2026-09-05T13:00:00Z",
        effective_at="2026-09-05T13:00:00Z",
        prior_claim={"claim_id": "claim-new", "version": 2},
        replacement={"claim_id": "claim-newer", "content": "Dallas office"},
    )
    engine.record(newer)
    current = task.current_claim("task-7")
    assert current and current["content"] == "Dallas office"
    stale = correction(correction_id="corr-stale", source_event_id="evt-stale")
    with pytest.raises(ValueError, match="stale prior claim"):
        engine.record(stale)
    current = task.current_claim("task-7")
    assert current and current["content"] == "Dallas office"


def test_impacts_only_consumers_of_contradicted_claim_across_all_work_kinds():
    items = []
    expected = {}
    for kind in ("task", "criterion", "evidence", "approval", "schedule", "dependency", "worker"):
        entity_id = f"{kind}-affected"
        items.append({"entity_id": entity_id, "kind": kind, "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": ["claim-old"], "active": True})
        expected[entity_id] = "cancel" if kind == "approval" else ("rebrief" if kind == "worker" else "block")
    items += [
        {"entity_id": "unrelated", "kind": "task", "client_id": "client-a", "claim_refs": ["other"], "active": True},
        {"entity_id": "inactive", "kind": "task", "client_id": "client-a", "claim_refs": ["claim-old"], "active": False},
        {"entity_id": "other-client", "kind": "task", "client_id": "client-b", "claim_refs": ["claim-old"], "active": True},
    ]
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    impact = ImpactAdapter(items)
    result = service(task=task, impact=impact).record(correction())
    assert {entry["entity_id"]: entry["action"] for entry in result["impacts"]} == expected
    assert {entry[1]["entity_id"] for entry in impact.actions} == set(expected)


def test_approval_withdrawal_reaches_broker_before_affected_work_can_act():
    events = []
    approval = ApprovalBroker("approval-broker", events)
    approval.seed("task-7")
    impact = ImpactAdapter([
        {"entity_id": "queued-action", "kind": "approval", "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": ["claim-old"], "active": True}
    ], events)
    service(approval=approval, impact=impact).record(correction("approval"))
    assert events.index("approval-prepared") < events.index("impact:approval:queued-action")
    assert events.index("impact:approval:queued-action") < events.index("approval-withdrawn")


def test_failed_approval_impact_cancels_preparation_without_revoking_broker():
    class FailingImpact(ImpactAdapter):
        def apply_impact(self, impact, *, correction_id):
            raise RuntimeError("impact failed")
        def rollback_impact(self, impact, *, correction_id):
            pass
    events = []
    approval = ApprovalBroker("approval-broker", events)
    approval.seed("task-7")
    impact = FailingImpact([{"entity_id": "queued-action", "kind": "approval", "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": ["claim-old"], "active": True}], events)

    with pytest.raises(RuntimeError, match="impact failed"):
        service(approval=approval, impact=impact).record(correction("approval"))
    assert "approval-cancelled" in events
    assert "approval-withdrawn" not in events
    claim = approval.current_claim("task-7")
    assert claim is not None
    assert claim["claim_id"] == "claim-old"


def test_post_commit_readback_failure_never_rolls_back_claim_away_from_revocation():
    class UnreadableAfterCommit(ApprovalBroker):
        def verify_withdrawal(self, authority_id, correction_id):
            return False
    approval = UnreadableAfterCommit("approval-broker")
    approval.seed("task-7")
    with pytest.raises(RuntimeError, match="irreversible"):
        service(approval=approval).record(correction("approval"))
    claim = approval.current_claim("task-7")
    assert claim is not None
    assert claim["claim_id"] == "claim-new"
    assert ("task-7", "corr-001") in approval.withdrawals


def test_correction_retraction_is_versioned_and_supersedes_only_corrected_claim():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    engine = service(task=task)
    engine.record(correction())
    retract = correction(
        correction_id="corr-003",
        source_event_id="evt-003",
        operation="retract",
        recorded_at="2026-09-05T14:00:00Z",
        effective_at="2026-09-05T14:00:00Z",
        prior_claim={"claim_id": "claim-new", "version": 2},
        replacement={"claim_id": "claim-restored", "content": "old"},
    )
    result = engine.record(retract)
    assert result["version"] == 3
    current = task.current_claim("task-7")
    assert current and current["claim_id"] == "claim-restored"


def test_fresh_service_retrieval_returns_corrected_claim_and_stale_claim_cannot_resurface():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    shared_ledger = {}
    service(task=task, ledger=shared_ledger).record(correction())
    reopened = service(task=task, ledger=shared_ledger)
    assert reopened.retrieve("task_requirement", "task-7")["claim_id"] == "claim-new"
    assert reopened.retrieve("task_requirement", "task-7")["content"] == "Austin office"
    assert task.claims["task-7"]["superseded_by"] is None


def test_cross_client_scope_isolation_and_no_global_memory_pollution():
    memory = AuthorityAdapter("profile-memory")
    memory.seed("preference-a")
    impact = ImpactAdapter([
        {"entity_id": "client-b-task", "kind": "task", "client_id": "client-b", "claim_refs": ["claim-old"], "active": True}
    ])
    record = correction(
        "principal_preference",
        target={"authority_id": "preference-a", "field": "writing.tone", "exact_scope": "principal-a/writing.tone"},
        scope={"profile_id": "principal-a", "lane": "business"},
    )
    service(memory=memory, impact=impact).record(record)
    assert not impact.actions
    assert memory.writes[0]["scope"] == {"profile_id": "principal-a", "lane": "business"}
    assert "global" not in json.dumps(memory.writes).lower()


def test_rejects_secret_bearing_records_and_exposes_no_second_task_authority():
    engine = service()
    secret = correction(privacy={"contains_secret": True}, replacement={"claim_id": "claim-new", "content": "fixture-secret-value"})  # pragma: allowlist secret
    with pytest.raises(ValueError, match="secret"):
        engine.record(secret)
    source = MODULE_PATH.read_text().lower()
    for forbidden in ("sqlite", "task_status", "set_status", "create_task"):
        assert forbidden not in source


def test_mutated_replay_is_rejected_even_when_an_id_matches():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    engine = service(task=task, ledger={})
    engine.record(correction())
    for mutated in (
        correction(client_id="client-b"),
        correction(replacement={"claim_id": "claim-evil", "content": "elsewhere"}),
        correction(correction_id="different", target={"authority_id": "other", "field": "x", "exact_scope": "other.x"}),
    ):
        with pytest.raises(ValueError, match="replay payload"):
            engine.record(mutated)


def test_cross_client_or_scope_target_authority_is_denied():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    task.claims["task-7"].update(client_id="client-a", scope={"project_id": "project-a", "lane": "delivery"}, exact_scope="task-7.requirement.location")
    with pytest.raises(ValueError, match="client"):
        service(task=task).record(correction(client_id="client-b", correction_id="cross", source_event_id="cross-event"))
    with pytest.raises(ValueError, match="scope"):
        service(task=task).record(correction(scope={"project_id": "project-other", "lane": "delivery"}, correction_id="scope", source_event_id="scope-event"))


def test_missing_or_non_exact_candidate_scope_fails_closed():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    impact = ImpactAdapter([
        {"entity_id": "missing", "kind": "task", "client_id": "client-a", "claim_refs": ["claim-old"], "active": True},
        {"entity_id": "wrong", "kind": "task", "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "other", "claim_refs": ["claim-old"], "active": True},
        {"entity_id": "exact", "kind": "task", "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": ["claim-old"], "active": True},
    ])
    result = service(task=task, impact=impact).record(correction())
    assert [x["entity_id"] for x in result["impacts"]] == ["exact"]


def test_secret_shape_is_rejected_despite_false_privacy_flag():
    engine = service()
    for content in (  # pragma: allowlist secret -- synthetic rejection fixtures
        "sk_" + "live_" + ("A" * 24),  # pragma: allowlist secret
        "password" + "=CorrectHorseBatteryStaple",  # pragma: allowlist secret
        "-----BEGIN " + "PRIVATE KEY-----\nabc",  # pragma: allowlist secret
    ):
        with pytest.raises(ValueError, match="secret"):
            engine.record(correction(replacement={"claim_id": "claim-new", "content": content}))


def test_bearer_jwt_api_key_and_high_entropy_secrets_are_rejected_without_false_positives():
    engine = service()
    secrets = (
        "Authorization: " + "Bearer " + "abcdefghijklmnopqrstuvwxyz0123456789",  # pragma: allowlist secret
        "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",  # pragma: allowlist secret
        "api" + "-key: " + "7a9C2dE4fG6hJ8kL0mN2pQ4rS6tU8vW0",  # pragma: allowlist secret
        "token" + "_" + "7a9C2dE4fG6hJ8kL0mN2pQ4rS6tU8vW0xY2zA4bC6",  # pragma: allowlist secret
    )
    for index, content in enumerate(secrets):
        with pytest.raises(ValueError, match="secret"):
            engine.record(correction(correction_id=f"secret-{index}", source_event_id=f"secret-event-{index}", replacement={"claim_id": f"claim-{index}", "content": content}))
    for index, content in enumerate(("Austin office", "Use the documented API key rotation process", "bearer plants tolerate drought", "issue abcdefghijklmnopqrstuvwxyz0123456789 is public")):
        task = AuthorityAdapter("kanban")
        task.seed("task-7")
        service(task=task).record(correction(correction_id=f"safe-{index}", source_event_id=f"safe-event-{index}", replacement={"claim_id": f"safe-claim-{index}", "content": content}))


def test_authoritative_claim_retains_full_correction_provenance():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    service(task=task).record(correction())
    claim = task.current_claim("task-7")
    assert claim is not None
    assert {key: claim[key] for key in ("effective_at", "field", "reason", "recorded_at", "source", "source_event_id")} == {
        "effective_at": "2026-09-05T12:00:00Z", "field": "requirement.location",
        "reason": "Principal corrected the location.", "recorded_at": "2026-09-05T12:00:00Z",
        "source": correction()["source"], "source_event_id": "evt-001",
    }


def test_committed_replay_is_rejected_after_authority_has_advanced():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    ledger = {}
    engine = service(task=task, ledger=ledger)
    old = correction()
    engine.record(old)
    engine.record(correction(correction_id="corr-002", source_event_id="evt-002", prior_claim={"claim_id": "claim-new", "version": 2}, replacement={"claim_id": "claim-newer", "content": "Dallas office"}))
    with pytest.raises(ValueError, match="stale replay"):
        engine.record(old)
    claim = task.current_claim("task-7")
    assert claim is not None
    assert claim["claim_id"] == "claim-newer"


def test_impact_failure_rolls_authority_back_and_retry_can_succeed():
    class FailingImpact(ImpactAdapter):
        def __init__(self, items):
            super().__init__(items)
            self.fail = True
        def apply_impact(self, impact, *, correction_id):
            if self.fail:
                self.fail = False
                raise RuntimeError("impact failed")
            super().apply_impact(impact, correction_id=correction_id)
        def rollback_impact(self, impact, *, correction_id):
            self.actions = [a for a in self.actions if a != (correction_id, impact)]
        def verify_impact(self, impact, *, correction_id):
            return (correction_id, impact) in self.actions
    class TxAuthority(AuthorityAdapter):
        def rollback_correction(self, record, prior):
            self.claims[record["target"]["authority_id"]] = deepcopy(prior)
        def superseded_claim(self, target, claim_id):
            return {"claim_id": claim_id, "superseded_by": self.claims[target]["claim_id"]}
    task = TxAuthority("kanban")
    task.seed("task-7")
    impact = FailingImpact([{"entity_id": "affected", "kind": "task", "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": ["claim-old"], "active": True}])
    engine = service(task=task, impact=impact, ledger={})
    with pytest.raises(RuntimeError, match="impact failed"):
        engine.record(correction())
    claim = task.current_claim("task-7")
    assert claim is not None
    assert claim["claim_id"] == "claim-old"
    assert engine.record(correction())["version"] == 2


def test_private_profile_authority_survives_fresh_instances_and_preserves_unrelated_state(tmp_path):
    path = ROOT / "plugins" / "operator-control" / "correction_adapters.py"
    spec = importlib.util.spec_from_file_location("correction_adapters", path)
    assert spec and spec.loader
    adapters = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapters)
    authority_path = tmp_path / "private" / "project-lanes.json"
    journal_path = tmp_path / "private" / "journal.json"
    authority = adapters.ProjectLaneAuthority(authority_path)
    authority.seed_claim("task-7", {"claim_id": "claim-old", "content": "old", "version": 1, "superseded_by": None})
    authority.seed_claim("unrelated", {"claim_id": "other", "content": "keep", "version": 4, "superseded_by": None})
    engine = service(project=authority, impact=ImpactAdapter(), ledger=adapters.DurableCorrectionJournal(journal_path))
    engine.record(correction("project_fact"))
    reopened_authority = adapters.ProjectLaneAuthority(authority_path)
    reopened = service(project=reopened_authority, impact=ImpactAdapter(), ledger=adapters.DurableCorrectionJournal(journal_path))
    assert reopened.record(correction("project_fact"))["version"] == 2
    assert reopened.retrieve("project_fact", "task-7")["content"] == "Austin office"
    assert reopened_authority.superseded_claim("task-7", "claim-old")["superseded_by"] == "claim-new"
    assert reopened.retrieve("project_fact", "unrelated")["content"] == "keep"
    assert not (tmp_path / "memory.json").exists()


def test_native_kanban_adapter_uses_real_board_and_fresh_process_readback(tmp_path, monkeypatch):
    path = ROOT / "plugins" / "operator-control" / "correction_adapters.py"
    spec = importlib.util.spec_from_file_location("native_correction_adapters", path)
    assert spec and spec.loader
    adapters = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapters)
    home, board = tmp_path / "hermes", "corrections"
    env = os.environ.copy()
    env["HERMES_HOME"] = str(home)
    for key in ("HERMES_DELEGATED_CHILD_CONTEXT", "HERMES_KANBAN_TASK", "HERMES_KANBAN_BOARD"):
        env.pop(key, None)
        monkeypatch.delenv(key, raising=False)
    subprocess.run(["hermes", "kanban", "boards", "create", board], env=env, check=True, capture_output=True, text=True)
    marker = adapters.kanban_claim_marker({"claim_id": "claim-old", "content": "old", "version": 1, "superseded_by": None, "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": ["claim-old"], "kind": "task", "active": True})
    created = subprocess.run(["hermes", "kanban", "--board", board, "create", "Canonical task", "--body", marker, "--json"], env=env, check=True, capture_output=True, text=True)
    task_id = json.loads(created.stdout)["id"]
    authority = adapters.NativeKanbanAuthority(hermes_home=home, board=board)
    value = correction(target={"authority_id": task_id, "field": "requirement.location", "exact_scope": "task-7.requirement.location"})
    impact = adapters.NativeKanbanImpactAdapter(hermes_home=home, board=board)
    service(task=authority, impact=impact, ledger={}).record(value)
    fresh = subprocess.run([sys.executable, "-c", f"import importlib.util,json; s=importlib.util.spec_from_file_location('a',{str(path)!r}); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps(m.NativeKanbanAuthority(hermes_home={str(home)!r},board={board!r}).current_claim({task_id!r})))"], check=True, capture_output=True, text=True)
    claim = json.loads(fresh.stdout)
    assert claim["claim_id"] == "claim-new"
    assert claim["source_event_id"] == "evt-001"
    assert not (home / "kanban.json").exists()
    assert not (home / "native-work.json").exists()


def test_native_kanban_impacts_schedule_dependency_worker_and_preserve_unrelated(tmp_path, monkeypatch):
    path = ROOT / "plugins" / "operator-control" / "correction_adapters.py"
    spec = importlib.util.spec_from_file_location("native_impact_adapters", path)
    assert spec and spec.loader
    adapters = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapters)
    home, board = tmp_path / "hermes", "impact-board"
    env = os.environ.copy()
    env["HERMES_HOME"] = str(home)
    for key in ("HERMES_DELEGATED_CHILD_CONTEXT", "HERMES_KANBAN_TASK", "HERMES_KANBAN_BOARD"):
        env.pop(key, None)
        monkeypatch.delenv(key, raising=False)
    subprocess.run(["hermes", "kanban", "boards", "create", board], env=env, check=True, capture_output=True, text=True)
    ids = {}
    for kind in ("schedule", "dependency", "worker", "approval", "unrelated"):
        claim_refs = ["claim-old"] if kind != "unrelated" else ["other"]
        marker = adapters.kanban_claim_marker({"claim_id": f"claim-{kind}", "content": kind, "version": 1, "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": claim_refs, "kind": "task" if kind == "unrelated" else kind, "active": True})
        result = subprocess.run(["hermes", "kanban", "--board", board, "create", kind, "--body", marker, "--json"], env=env, check=True, capture_output=True, text=True)
        ids[kind] = json.loads(result.stdout)["id"]
    impact = adapters.NativeKanbanImpactAdapter(hermes_home=home, board=board)
    items = impact.active_items(client_id="client-a", scope={"project_id": "project-a", "lane": "delivery"})
    affected = {item["kind"]: item for item in items if "claim-old" in item["claim_refs"]}
    for kind, action in (("schedule", "block"), ("dependency", "block"), ("worker", "rebrief"), ("approval", "cancel")):
        request = {"entity_id": ids[kind], "kind": kind, "action": action}
        impact.apply_impact(request, correction_id="corr-native")
        assert impact.verify_impact(request, correction_id="corr-native")
    unrelated = subprocess.run(["hermes", "kanban", "--board", board, "show", ids["unrelated"], "--json"], env=env, check=True, capture_output=True, text=True)
    assert json.loads(unrelated.stdout)["task"]["status"] == "ready"
    assert set(affected) == {"schedule", "dependency", "worker", "approval"}


def test_retry_reconciles_crash_after_authority_apply_instead_of_going_stale():
    task = AuthorityAdapter("kanban")
    task.seed("task-7")
    value = correction()
    task.apply_correction(value)  # external effect occurred before coordinator commit
    module = load_corrections()
    entry = {"state": "applying", "payload_digest": module.canonical_digest(value), "record": deepcopy(value),
             "prior_snapshot": {"claim_id": "claim-old", "content": "old", "version": 1, "superseded_by": "claim-new"}, "applied_impacts": []}
    ledger = {"correction:corr-001": deepcopy(entry), "source:evt-001": deepcopy(entry)}
    assert service(task=task, ledger=ledger).record(value)["version"] == 2
    assert len(task.writes) == 1


def test_rollback_failure_blocks_retry_for_reconciliation():
    class BrokenAuthority(AuthorityAdapter):
        def rollback_correction(self, record, prior):
            raise RuntimeError("rollback unavailable")
    class BrokenImpact(ImpactAdapter):
        def apply_impact(self, impact, *, correction_id):
            raise RuntimeError("impact unavailable")
    task = BrokenAuthority("kanban")
    task.seed("task-7")
    impact = BrokenImpact([{"entity_id": "affected", "kind": "task", "client_id": "client-a", "scope": {"project_id": "project-a", "lane": "delivery"}, "exact_scope": "task-7.requirement.location", "claim_refs": ["claim-old"], "active": True}])
    engine = service(task=task, impact=impact, ledger={})
    with pytest.raises(RuntimeError, match="rollback failed"):
        engine.record(correction())
    with pytest.raises(RuntimeError, match="blocked"):
        engine.record(correction())


def test_distribution_validator_preflight_and_plugin_expose_correction_contract():
    validator_source = (ROOT / "scripts" / "validate_blueprint.py").read_text()
    preflight_source = (ROOT / "scripts" / "preflight.py").read_text()
    tools = load_tools_module()
    assert "templates/correction-record.schema.json" in validator_source
    assert "tests/test_correction_persistence.py" in (ROOT / "contracts" / "authority-map.yaml").read_text()
    assert "plugins/operator-control/corrections.py" in preflight_source

    class Recorder:
        def record(self, value):
            return {"correction_id": value["correction_id"]}

    assert tools.record_correction(correction(), service=Recorder()) == {"correction_id": "corr-001"}


def load_tools_module():
    path = ROOT / "plugins" / "operator-control" / "tools.py"
    spec = importlib.util.spec_from_file_location("operator_control_tools_for_corrections", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
