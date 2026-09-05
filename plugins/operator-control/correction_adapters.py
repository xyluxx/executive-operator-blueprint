"""Correction adapters for canonical Hermes Kanban and private profile authorities."""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import MutableMapping
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

_MARKER = "[operator-control-claim:v1] "
_IMPACT_MARKER = "[operator-control-impact:v1] "


def _private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)


def _read(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    _private_parent(path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def kanban_claim_marker(claim: dict[str, Any]) -> str:
    """Encode correction metadata in a native card body/comment."""
    return _MARKER + json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decode_markers(text: str, prefix: str = _MARKER) -> list[dict[str, Any]]:
    values = []
    for line in (text or "").splitlines():
        if line.startswith(prefix):
            try:
                value = json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                values.append(value)
    return values


def _claim_from_record(record: dict[str, Any], version: int) -> dict[str, Any]:
    return {
        "claim_id": record["replacement"]["claim_id"],
        "content": deepcopy(record["replacement"]["content"]),
        "version": version,
        "superseded_by": None,
        "correction_id": record["correction_id"],
        "source_event_id": record["source_event_id"],
        "source": deepcopy(record["source"]),
        "recorded_at": record["recorded_at"],
        "effective_at": record["effective_at"],
        "field": record["target"]["field"],
        "reason": record["reason"],
        "client_id": record["client_id"],
        "scope": deepcopy(record["scope"]),
        "exact_scope": record["target"]["exact_scope"],
    }


class DurableCorrectionJournal(MutableMapping[str, dict[str, Any]]):
    """Atomic profile-private transaction journal; contains no lifecycle data."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _data(self) -> dict[str, dict[str, Any]]:
        return _read(self.path, {"entries": {}})["entries"]

    def __getitem__(self, key: str) -> dict[str, Any]:
        return deepcopy(self._data()[key])

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        data = _read(self.path, {"entries": {}})
        data["entries"][key] = deepcopy(value)
        _atomic_write(self.path, data)

    def __delitem__(self, key: str) -> None:
        data = _read(self.path, {"entries": {}})
        del data["entries"][key]
        _atomic_write(self.path, data)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def flush(self) -> None:
        """Writes are synchronously persisted."""


class JsonClaimAuthority:
    """Canonical private authority used only for profile memory/voice/project data."""

    authority_kind = "profile-private"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _document(self) -> dict[str, Any]:
        return _read(self.path, {"claims": {}, "superseded": {}, "activity": []})

    def seed_claim(self, authority_id: str, claim: dict[str, Any]) -> None:
        document = self._document()
        document["claims"][authority_id] = deepcopy(claim)
        _atomic_write(self.path, document)

    def current_claim(self, authority_id: str) -> dict[str, Any] | None:
        claim = self._document()["claims"].get(authority_id)
        return deepcopy(claim) if claim is not None else None

    def _apply(self, record: dict[str, Any]) -> dict[str, Any]:
        document = self._document()
        authority_id = record["target"]["authority_id"]
        old = document["claims"][authority_id]
        replacement = record["replacement"]
        document["superseded"][f"{authority_id}:{old['claim_id']}"] = {
            "claim_id": old["claim_id"], "version": old["version"],
            "superseded_by": replacement["claim_id"],
        }
        claim = _claim_from_record(record, old["version"] + 1)
        document["claims"][authority_id] = claim
        activity = deepcopy(claim)
        activity.update(type="correction", operation=record["operation"], authority_id=authority_id)
        document["activity"].append(activity)
        _atomic_write(self.path, document)
        return {"version": claim["version"]}

    def apply_correction(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._apply(record)

    def retract_correction(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._apply(record)

    def superseded_claim(self, authority_id: str, claim_id: str) -> dict[str, Any] | None:
        value = self._document()["superseded"].get(f"{authority_id}:{claim_id}")
        return deepcopy(value) if value else None

    def rollback_correction(self, record: dict[str, Any], prior: dict[str, Any]) -> None:
        document = self._document()
        authority_id = record["target"]["authority_id"]
        document["claims"][authority_id] = deepcopy(prior)
        document["superseded"].pop(f"{authority_id}:{prior['claim_id']}", None)
        document["activity"].append({"type": "correction-rollback", "correction_id": record["correction_id"]})
        _atomic_write(self.path, document)


class _HermesKanban:
    def __init__(self, *, hermes_home: str | Path | None = None, board: str | None = None,
                 hermes_command: str = "hermes") -> None:
        resolved = hermes_home or os.environ.get("HERMES_HOME")
        if not resolved:
            raise ValueError("resolved HERMES_HOME is required for native Kanban")
        self.hermes_home = Path(resolved)
        resolved_board = board or os.environ.get("HERMES_KANBAN_BOARD")
        if not resolved_board:
            raise ValueError("resolved Hermes Kanban board is required")
        self.board: str = resolved_board
        self.hermes_command = hermes_command

    def _run(self, *arguments: str, json_output: bool = False) -> Any:
        env = os.environ.copy()
        env["HERMES_HOME"] = str(self.hermes_home)
        env["HERMES_KANBAN_BOARD"] = self.board
        command = [self.hermes_command, "kanban", "--board", self.board, *arguments]
        if json_output:
            command.append("--json")
        result = subprocess.run(command, env=env, check=True, capture_output=True, text=True)
        return json.loads(result.stdout) if json_output else result.stdout

    def _show(self, task_id: str) -> dict[str, Any]:
        value = self._run("show", task_id, json_output=True)
        if not isinstance(value, dict):
            raise RuntimeError("native Kanban show returned a non-object")
        if isinstance(value.get("task"), dict):
            card = deepcopy(value["task"])
            card["comments"] = deepcopy(value.get("comments", []))
            card["events"] = deepcopy(value.get("events", []))
            return card
        return value

    @staticmethod
    def _texts(card: dict[str, Any]) -> list[str]:
        texts = [str(card.get("body") or "")]
        for comment in card.get("comments", ()):
            texts.append(str(comment.get("body") or comment.get("text") or ""))
        return texts


class NativeKanbanAuthority(_HermesKanban):
    """Native Hermes card authority; claims are card comments, never sidecar files."""

    authority_kind = "native-hermes-kanban"

    def _history(self, authority_id: str) -> list[dict[str, Any]]:
        card = self._show(authority_id)
        values: list[dict[str, Any]] = []
        for text in self._texts(card):
            values.extend(_decode_markers(text))
        return values

    def current_claim(self, authority_id: str) -> dict[str, Any] | None:
        history = self._history(authority_id)
        return deepcopy(history[-1]) if history else None

    def _apply(self, record: dict[str, Any]) -> dict[str, Any]:
        old = self.current_claim(record["target"]["authority_id"])
        if old is None:
            raise KeyError(record["target"]["authority_id"])
        claim = _claim_from_record(record, old["version"] + 1)
        self._run("comment", record["target"]["authority_id"], kanban_claim_marker(claim), "--author", "operator-control")
        return {"version": claim["version"]}

    def apply_correction(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._apply(record)

    def retract_correction(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._apply(record)

    def superseded_claim(self, authority_id: str, claim_id: str) -> dict[str, Any] | None:
        history = self._history(authority_id)
        for index, claim in enumerate(history[:-1]):
            if claim.get("claim_id") == claim_id:
                return {"claim_id": claim_id, "version": claim.get("version"), "superseded_by": history[index + 1].get("claim_id")}
        return None

    def rollback_correction(self, record: dict[str, Any], prior: dict[str, Any]) -> None:
        self._run("comment", record["target"]["authority_id"], kanban_claim_marker(prior), "--author", "operator-control-rollback")


class ProjectLaneAuthority(JsonClaimAuthority):
    authority_kind = "project-lane"


class SelectedMemoryAuthority(JsonClaimAuthority):
    authority_kind = "selected-profile-memory"


class VoiceProfileAuthority(JsonClaimAuthority):
    authority_kind = "voice-profile"


class NativeKanbanImpactAdapter(_HermesKanban):
    """Discover and impact native cards via supported Hermes Kanban CLI verbs."""

    def active_items(self, *, client_id: str, scope: dict[str, str]) -> list[dict[str, Any]]:
        listed = self._run("list", json_output=True)
        cards = listed.get("tasks", listed) if isinstance(listed, dict) else listed
        found = []
        for summary in cards:
            task_id = str(summary.get("id") or summary.get("task_id"))
            card = self._show(task_id)
            markers = []
            for text in self._texts(card):
                markers.extend(_decode_markers(text))
            if not markers:
                continue
            item = deepcopy(markers[-1])
            item["entity_id"] = task_id
            item.setdefault("kind", "task")
            item["active"] = card.get("status") not in {"done", "archived"} and item.get("active", True)
            if item.get("client_id") == client_id:
                found.append(item)
        return found

    def _impact_history(self, entity_id: str) -> list[dict[str, Any]]:
        values = []
        for text in self._texts(self._show(entity_id)):
            values.extend(_decode_markers(text, _IMPACT_MARKER))
        return values

    def apply_impact(self, impact: dict[str, str], *, correction_id: str) -> None:
        card = self._show(impact["entity_id"])
        marker = {"correction_id": correction_id, "action": impact["action"], "kind": impact["kind"], "prior_status": card.get("status"), "state": "applied"}
        text = _IMPACT_MARKER + json.dumps(marker, sort_keys=True, separators=(",", ":"))
        self._run("comment", impact["entity_id"], text, "--author", "operator-control")
        reason = f"Correction {correction_id}: {impact['action']} stale claim consumer"
        self._run("block", impact["entity_id"], reason, "--kind", "dependency")

    def verify_impact(self, impact: dict[str, str], *, correction_id: str) -> bool:
        history = self._impact_history(impact["entity_id"])
        matching = [entry for entry in history if entry.get("correction_id") == correction_id]
        return bool(matching and matching[-1].get("state") == "applied" and self._show(impact["entity_id"]).get("status") in {"blocked", "todo"})

    def rollback_impact(self, impact: dict[str, str], *, correction_id: str) -> None:
        history = self._impact_history(impact["entity_id"])
        matching = [entry for entry in history if entry.get("correction_id") == correction_id and entry.get("state") == "applied"]
        if not matching:
            return
        self._run("unblock", impact["entity_id"])
        marker = deepcopy(matching[-1])
        marker["state"] = "rolled_back"
        self._run("comment", impact["entity_id"], _IMPACT_MARKER + json.dumps(marker, sort_keys=True, separators=(",", ":")), "--author", "operator-control-rollback")


class BrokerApprovalAuthority(JsonClaimAuthority):
    """Private claim authority paired with the protected broker's staged API."""

    authority_kind = "operator-control-broker"

    def __init__(self, path: str | Path, broker: Any):
        super().__init__(path)
        self.broker = broker

    def prepare_withdrawal(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.broker.prepare_approval_revocation(
            record["target"]["authority_id"], correction_id=record["correction_id"],
            predecessor=deepcopy(record["prior_claim"]), replacement=deepcopy(record["replacement"]),
        )

    def commit_withdrawal(self, record: dict[str, Any], preparation: dict[str, Any]) -> dict[str, Any]:
        return self.broker.commit_approval_revocation(preparation)

    def cancel_withdrawal(self, record: dict[str, Any], preparation: dict[str, Any]) -> dict[str, Any]:
        return self.broker.cancel_approval_revocation(preparation)

    def verify_withdrawal(self, authority_id: str, correction_id: str) -> bool:
        result = self.broker.approval_status(authority_id)
        return result.get("state") == "revoked" and result.get("correction_id") == correction_id
