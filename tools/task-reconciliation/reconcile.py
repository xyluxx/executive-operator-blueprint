"""Provider-neutral reconciliation over the native Hermes Kanban."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess  # nosec B404
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, cast

STATE_PREFIX = "task-reconciliation:v1 "
RECEIPT_PREFIX = "task-reconciliation-delivery:v1 "
ACK_INTENT_PREFIX = "task-reconciliation-ack-intent:v1 "
ACK_RECEIPT_PREFIX = "task-reconciliation-ack-receipt:v1 "
SOURCES = {"conversation", "meeting", "email", "calendar"}
OBSERVATION_FIELDS = {
    "observation_version", "source_kind", "source_id", "event_timestamp", "event_sequence",
    "event_type", "principal_id", "client_id", "workstream_id", "target_id",
    "canonical_references", "evidence_references", "title", "owner", "next_actor",
    "artifact_id", "artifact_version", "requirement_version", "satisfied_criteria",
    "outstanding_criteria", "blocker", "wake_condition", "resume_point",
    "completion_claim", "evidence_status", "requirement_effective_at",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _task_key(observation: dict[str, Any]) -> str:
    identity: list[Any] = [
        _normalized(observation[key])
        for key in ("principal_id", "client_id", "workstream_id", "target_id")
    ]
    identity.append(sorted(_normalized(item) for item in observation["canonical_references"]))
    return "task-reconciliation:" + hashlib.sha256(_canonical(identity).encode()).hexdigest()


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _parse_timestamp(value: Any, field: str) -> datetime:
    try:
        if not isinstance(value, str):
            raise TypeError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a timezone-aware ISO-8601 timestamp") from exc


def _utc_timestamp(value: Any, field: str) -> str:
    return _parse_timestamp(value, field).isoformat().replace("+00:00", "Z")


def _normalize_timestamps(value: Any, path: str = "observation") -> Any:
    """Validate and UTC-normalize every conventionally named timestamp field."""
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            field = f"{path}.{key}"
            if item is not None and (key == "event_timestamp" or key.endswith("_at")):
                normalized[key] = _utc_timestamp(item, field)
            else:
                normalized[key] = _normalize_timestamps(item, field)
        return normalized
    if isinstance(value, list):
        return [_normalize_timestamps(item, f"{path}[{index}]") for index, item in enumerate(value)]
    return deepcopy(value)


def _event_order(observation: dict[str, Any]) -> tuple[datetime, int]:
    return (_parse_timestamp(observation["event_timestamp"], "event_timestamp"), int(observation.get("event_sequence", 0)))


def _stored_order(value: Any) -> tuple[datetime, int]:
    if not value:
        return (datetime.min.replace(tzinfo=timezone.utc), -1)
    return (_parse_timestamp(value[0], "stored event order"), int(value[1]))


def _serialize_order(value: tuple[datetime, int]) -> list[Any]:
    return [value[0].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), value[1]]


class NativeKanbanAdapter:
    """Small CLI adapter; Hermes Kanban remains the only task database."""

    def __init__(self, *, env: dict[str, str] | None = None, board: str = "default") -> None:
        self.env = dict(env or os.environ)
        self.board = board
        self._run("init")

    def _run(self, *args: str) -> str:
        result = subprocess.run(  # nosec B603 B607
            ["hermes", "kanban", "--board", self.board, *args],
            env=self.env, capture_output=True, text=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout

    def list_tasks(self) -> list[dict[str, Any]]:
        value = json.loads(self._run("list", "--json"))
        return value if isinstance(value, list) else value.get("tasks", [])

    def show(self, task_id: str) -> dict[str, Any]:
        return json.loads(self._run("show", task_id, "--json"))

    def create(self, observation: dict[str, Any], key: str) -> tuple[str, bool]:
        before = {task["id"] for task in self.list_tasks()}
        body = "Reconciled source task. Durable state is stored in task-reconciliation comments."
        value = json.loads(self._run(
            "create", observation["title"], "--body", body,
            "--idempotency-key", key, "--created-by", "task-reconciler", "--json",
        ))
        task_id = value["id"]
        return task_id, task_id not in before

    def create_manual(self, title: str, body: str) -> tuple[str, bool]:
        before = {task["id"] for task in self.list_tasks()}
        value = json.loads(self._run("create", title, "--body", body, "--json"))
        task_id = value["id"]
        return task_id, task_id not in before

    def comment(self, task_id: str, body: str) -> None:
        self._run("comment", "--author", "task-reconciler", task_id, body)

    def schedule(self, task_id: str, reason: str) -> None:
        self._run("schedule", task_id, reason)

    def block(self, task_id: str, reason: str) -> None:
        self._run("block", task_id, reason)

    def unblock(self, task_id: str) -> None:
        self._run("unblock", task_id)

    def request_review(self, task_id: str, metadata: dict[str, Any]) -> None:
        status = self.show(task_id)["task"]["status"]
        if status in {"scheduled", "blocked"}:
            self._run("unblock", task_id)
        self._run(
            "request-review", task_id,
            "--summary", "Current evidence is ready for acceptance review.",
            "--metadata", _canonical(metadata),
        )

    def complete(self, task_id: str, summary: str, metadata: dict[str, Any]) -> None:
        self._run(
            "complete", task_id, "--result", summary, "--summary", summary,
            "--metadata", _canonical(metadata),
        )

    def edit_completed(self, task_id: str, result: str, summary: str, metadata: dict[str, Any]) -> None:
        self._run(
            "edit", task_id, "--result", result, "--summary", summary,
            "--metadata", _canonical(metadata),
        )

    def record_delivery_receipt(self, task_id: str, dedup_key: str, status: str) -> None:
        """Store delivery metadata separately; it never participates in task truth."""
        self.comment(task_id, RECEIPT_PREFIX + _canonical({"dedup_key": dedup_key, "status": status}))


class TaskReconciler:
    def __init__(
        self, kanban: NativeKanbanAdapter, acceptance_boundary=None, *, event_hook=None,
        control_resolver=None, meeting_resolver=None, acknowledgment_sender=None,
    ) -> None:
        self.kanban = kanban
        self.acceptance_boundary = acceptance_boundary
        self.event_hook = event_hook
        self.control_resolver = control_resolver
        self.meeting_resolver = meeting_resolver
        self.acknowledgment_sender = acknowledgment_sender

    def resume(self, task_id: str) -> dict[str, Any]:
        """Read the last durable reconciliation checkpoint from the card."""
        states = self._states(self.kanban.show(task_id))
        if not states:
            raise ValueError(f"task {task_id} has no reconciliation checkpoint")
        return deepcopy(states[-1])

    @staticmethod
    def _validate(observation: dict[str, Any]) -> None:
        required = {
            "source_kind", "source_id", "event_timestamp", "principal_id",
            "client_id", "workstream_id", "target_id", "canonical_references",
            "evidence_references", "title", "owner", "next_actor",
            "artifact_id", "artifact_version", "requirement_version",
            "satisfied_criteria", "outstanding_criteria", "resume_point",
        }
        missing = sorted(required - observation.keys())
        if missing:
            raise ValueError(f"missing observation fields: {', '.join(missing)}")
        if observation["source_kind"] not in SOURCES:
            raise ValueError("unsupported source_kind")
        for field in ("source_id", "principal_id", "client_id", "workstream_id", "target_id"):
            if not isinstance(observation[field], str) or not observation[field].strip():
                raise ValueError(f"{field} must be non-blank")
        _parse_timestamp(observation["event_timestamp"], "event_timestamp")
        references = observation["canonical_references"]
        if not isinstance(references, list) or not references or any(not isinstance(x, str) or not x.strip() for x in references):
            raise ValueError("canonical_references must contain non-blank references")
        evidence = observation["evidence_references"]
        if not isinstance(evidence, list) or any(not isinstance(x, str) or not x.strip() for x in evidence):
            raise ValueError("evidence_references must contain non-blank references")
        if observation.get("completion_claim") and not evidence:
            raise ValueError("evidence_references are required for completion claims")
        blocker = observation.get("blocker")
        if blocker is not None:
            if not isinstance(blocker, str) or not blocker.strip():
                raise ValueError("blocker must be non-blank when present")
            wake_condition = observation.get("wake_condition")
            if not isinstance(wake_condition, str) or not wake_condition.strip():
                raise ValueError("wake_condition must be non-blank for blocked work")

    @staticmethod
    def _states(card: dict[str, Any]) -> list[dict[str, Any]]:
        states = []
        for comment in card.get("comments", []):
            body = comment.get("body", "")
            if body.startswith(STATE_PREFIX):
                states.append(json.loads(body[len(STATE_PREFIX):]))
        return states

    @staticmethod
    def _ack_receipts(card: dict[str, Any]) -> list[dict[str, Any]]:
        receipts = []
        for comment in card.get("comments", []):
            body = comment.get("body", "")
            if body.startswith(ACK_RECEIPT_PREFIX):
                value = json.loads(body[len(ACK_RECEIPT_PREFIX):])
                if isinstance(value, dict):
                    receipts.append(value)
        return receipts

    def _resolve(self, observation: dict[str, Any], key: str) -> tuple[str, bool]:
        references = {_normalized(item) for item in observation["canonical_references"]}
        for task in self.kanban.list_tasks():
            card = self.kanban.show(task["id"])
            states = self._states(card)
            if not states:
                continue
            latest = states[-1]
            same_scope = (
                all(
                    _normalized(str(latest.get(field, ""))) == _normalized(observation[field])
                    for field in ("principal_id", "client_id", "workstream_id", "target_id")
                )
            )
            if latest.get("task_key") == key or (
                same_scope
                and references == {_normalized(item) for item in latest.get("canonical_references", [])}
            ):
                return task["id"], False
        return self.kanban.create(observation, key)

    def _acceptance_decision(
        self, task_id: str, card: dict[str, Any], state: dict[str, Any], accepter_id: str | None,
    ):
        # Every source payload is untrusted. Completion control comes only from
        # the current card/control store and a separately configured adapter.
        if not state.get("_current_event_fresh"):
            return None
        if not state.get("completion_claim") or state.get("source_kind") != "meeting":
            return None
        acceptance_boundary = self.acceptance_boundary
        control_resolver = self.control_resolver
        meeting_resolver = self.meeting_resolver
        if acceptance_boundary is None or control_resolver is None or meeting_resolver is None or accepter_id is None:
            return None
        contract = control_resolver(task_id, deepcopy(card))
        if not isinstance(contract, dict):
            return None
        contract = _normalize_timestamps(contract, "control")
        policy = deepcopy(contract.get("policy"))
        current = deepcopy(contract.get("current"))
        if not isinstance(policy, dict) or not isinstance(current, dict):
            return None
        required_bindings = {
            "task_id", "task_version", "requirement_version", "artifact_id", "artifact_version",
            "target_id", "target_version", "environment",
        }
        if required_bindings - current.keys() or current["task_id"] != task_id:
            return None
        if _normalized(str(current["target_id"])) != _normalized(state["target_id"]):
            return None
        attestation = meeting_resolver(deepcopy(state), deepcopy(current))
        if not isinstance(attestation, dict) or attestation.get("occurred") is not True:
            return None
        attestation = _normalize_timestamps(attestation, "attestation")
        if attestation.get("person_id") != current.get("requested_person_id"):
            return None
        requested_topics = set(current.get("requested_topics") or [])
        if not requested_topics or not requested_topics.issubset(set(attestation.get("topics") or [])):
            return None
        trusted_references = attestation.get("evidence_references") or []
        if not trusted_references or any(not str(item).startswith("trusted-") for item in trusted_references):
            return None
        effective = current.get("requirement_effective_at")
        if effective:
            effective_at = _parse_timestamp(effective, "requirement_effective_at")
            if _parse_timestamp(state.get("event_timestamp"), "event_timestamp") < effective_at:
                return None
            evidence = [
                item
                for result in attestation.get("criterion_results", [])
                for item in result.get("evidence", [])
            ]
            if not evidence or any(
                _parse_timestamp(item.get("collected_at"), "evidence.collected_at") < effective_at
                for item in evidence
            ):
                return None
        results = deepcopy(attestation.get("criterion_results", []))
        for result in results:
            result["task_id"] = task_id
        submission = {
            "submission_id": f"reconcile:{state['source_kind']}:{state['source_id']}",
            "worker_id": f"source:{state['source_kind']}",
            "worker_claim": "evidence-observed",
            "policy_digest": policy.get("policy_digest"),
            "protected_digests": deepcopy(policy.get("protected_digests", {})),
            "results": results,
        }
        decision = acceptance_boundary(policy, submission, current, accepter_id=accepter_id)
        decision["control_current"] = current
        return decision

    def _deliver_acknowledgment(
        self, task_id: str, state: dict[str, Any], decision: dict[str, Any], ack_key: str,
    ) -> dict[str, Any] | None:
        records = deepcopy(state.get("acknowledgments", []))
        state["acknowledgments"] = records
        record = next((item for item in records if item.get("dedup_key") == ack_key), None)
        if record and record.get("status") == "emitted":
            state["acknowledgments"] = records
            return None
        current = decision["control_current"]
        recipient = current.get("acknowledgment_recipient")
        channel = current.get("acknowledgment_channel")
        if not all(isinstance(item, str) and item.strip() for item in (recipient, channel)):
            return None
        text = current.get("acknowledgment_text", "Verified task completion.")
        intent = {
            "operation_key": ack_key, "dedup_key": ack_key,
            "task_id": task_id, "task_version": current["task_version"],
            "requirement_version": current["requirement_version"],
            "artifact_version": current["artifact_version"],
            "recipient": recipient, "channel": channel, "text": text,
            "content_digest": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
            "optional": True,
        }
        if record is None:
            record = {**intent, "status": "pending"}
            records.append(record)
            state["acknowledgments"] = records
            # Durable intent always precedes dispatch.
            self.kanban.comment(task_id, ACK_INTENT_PREFIX + _canonical(intent))
            self.kanban.comment(task_id, STATE_PREFIX + _canonical(state))
        # Receipt comments are a separate durable checkpoint. Reconstruct them
        # before dispatch so a process crash after receipt cannot cause resend.
        expected = {
            key: intent[key]
            for key in (
                "operation_key", "task_id", "task_version", "requirement_version",
                "artifact_version", "recipient", "channel", "content_digest",
            )
        }
        durable_receipt = next((
            item for item in reversed(self._ack_receipts(self.kanban.show(task_id)))
            if all(item.get(key) == value for key, value in expected.items())
            and item.get("provider_status") in {"delivered", "read"}
        ), None)
        if durable_receipt is not None:
            record.update({"status": "emitted", "receipt": deepcopy(durable_receipt)})
            emitted = state.setdefault("emitted_acknowledgments", [])
            if ack_key not in emitted:
                emitted.append(ack_key)
            return None
        if self.acknowledgment_sender is None:
            return None
        result = self.acknowledgment_sender(deepcopy(intent))
        receipt = result.get("receipt") if isinstance(result, dict) else None
        confirmed = (
            isinstance(receipt, dict)
            and result.get("effect") == "confirmed-success"
            and receipt.get("recipient") == recipient
            and receipt.get("channel") == channel
            and receipt.get("status") in {"delivered", "read"}
        )
        if confirmed:
            confirmed_receipt = cast(dict[str, Any], receipt)
            durable_receipt = {
                **expected, "provider_status": confirmed_receipt["status"],
                "provider_receipt": deepcopy(confirmed_receipt),
            }
            record["status"] = "emitted"
            record["receipt"] = deepcopy(durable_receipt)
            emitted = state.setdefault("emitted_acknowledgments", [])
            if ack_key not in emitted:
                emitted.append(ack_key)
            self.kanban.comment(task_id, ACK_RECEIPT_PREFIX + _canonical(durable_receipt))
            return {**intent, "receipt": deepcopy(receipt)}
        record["status"] = "unknown"
        return None

    def _create_recommendation(self, parent: dict[str, Any], recommendation: dict[str, Any]) -> dict[str, Any]:
        child = deepcopy(parent)
        child.update(recommendation)
        child["source_kind"] = "conversation"
        child["source_id"] = f"recommendation:{parent['target_id']}:{recommendation['target_id']}"
        child["target_id"] = recommendation["target_id"]
        child["canonical_references"] = [f"recommendation://{recommendation['target_id']}"]
        child["evidence_references"] = []
        child["satisfied_criteria"] = []
        child["outstanding_criteria"] = recommendation.get("outstanding_criteria", ["owner acceptance"])
        child["criterion_results"] = []
        child["completion_claim"] = False
        child.pop("next_recommended_task", None)
        child.pop("acceptance_policy", None)
        key = _task_key(child)
        task_id, _ = self._resolve(child, key)
        if not self._states(self.kanban.show(task_id)):
            child["task_key"] = key
            child["task_id"] = task_id
            child["observed_events"] = [f"conversation:{child['source_id']}"]
            self.kanban.comment(task_id, STATE_PREFIX + _canonical(child))
        return {**recommendation, "task_id": task_id}

    def reconcile(self, observation: dict[str, Any], *, accepter_id: str | None = None) -> dict[str, Any]:
        observation = _normalize_timestamps(observation)
        self._validate(observation)
        key = _task_key(observation)
        task_id, created = self._resolve(observation, key)
        card = self.kanban.show(task_id)
        states = self._states(card)
        prior = states[-1] if states else {}
        order = _event_order(observation)
        event_key = f"{observation['source_kind']}:{observation['source_id']}:{order[0]}:{order[1]}"
        if event_key in prior.get("observed_events", []):
            return {
                "task_id": task_id, "created": False, "deduplicated": True,
                "status": card["task"]["status"], "acknowledgment": None,
                "next_recommended_task": None,
            }

        state = deepcopy(prior)
        freshness = deepcopy(prior.get("field_freshness", {}))
        latest_order = _stored_order(prior.get("latest_event_order"))
        state["_current_event_fresh"] = order >= latest_order
        state["latest_event_order"] = _serialize_order(max(order, latest_order))
        for field, value in observation.items():
            if field not in OBSERVATION_FIELDS:
                continue
            previous_order = _stored_order(freshness.get(field))
            if order >= previous_order:
                state[field] = deepcopy(value)
                freshness[field] = _serialize_order(order)
        state["field_freshness"] = freshness
        state["task_key"] = key
        state["task_id"] = task_id
        state["observed_events"] = [*prior.get("observed_events", []), event_key]
        state["canonical_references"] = sorted(set(prior.get("canonical_references", [])) | set(observation["canonical_references"]))
        state["evidence_references"] = sorted(set(prior.get("evidence_references", [])) | set(observation["evidence_references"]))
        state["emitted_acknowledgments"] = list(prior.get("emitted_acknowledgments", []))
        decision = self._acceptance_decision(task_id, card, state, accepter_id)
        accepted = decision is not None and decision["acceptance"]["status"] == "accepted"
        acknowledgment = None
        recommendation = None
        if decision is not None and accepted:
            state["acceptance"] = decision["acceptance"]
            current = decision["control_current"]
            ack_key = f"owner-ack:{task_id}:{current['requirement_version']}:{current['artifact_version']}"
            acknowledgment = self._deliver_acknowledgment(task_id, state, decision, ack_key)
            trusted_recommendation = current.get("next_recommended_task")
            if trusted_recommendation:
                recommendation = self._create_recommendation(state, trusted_recommendation)
                state["next_recommended_task"] = recommendation
        self.kanban.comment(task_id, STATE_PREFIX + _canonical(state))
        if self.event_hook and state.get("event_type"):
            self.event_hook({
                "event_type": state["event_type"],
                "task_id": task_id,
                "source_id": state["source_id"],
            })
        if decision is not None and accepted and card["task"]["status"] != "done":
            self.kanban.request_review(task_id, {"acceptance": decision["acceptance"]})
            self.kanban.complete(task_id, "Accepted against current evidence and all required criteria.", {"acceptance": decision["acceptance"]})
            status = "done"
        elif accepted:
            status = "done"
        elif state.get("blocker"):
            if card["task"]["status"] != "blocked":
                self.kanban.block(task_id, str(state["blocker"]))
            status = "blocked"
        elif card["task"]["status"] == "blocked":
            self.kanban.unblock(task_id)
            status = self.kanban.show(task_id)["task"]["status"]
        else:
            status = card["task"]["status"]
        return {
            "task_id": task_id, "created": created, "deduplicated": False,
            "status": status, "state": state, "acceptance": decision,
            "acknowledgment": acknowledgment, "next_recommended_task": recommendation,
        }
