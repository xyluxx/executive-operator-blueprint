"""Hermes hook and model-facing tools; not the authority."""
from __future__ import annotations

import importlib.util
from pathlib import Path

KNOWN_WRITE_TOOLS = frozenset({"operator_control_execute", "operator_control_secret_operation"})
GENERIC_WRITE_TOOLS = frozenset({"terminal", "browser", "browser_exec", "desktop_preview", "drive_preview"})
READ_ONLY_TOOLS = frozenset({"read_file", "search_files", "web_search", "web_extract", "vision_analyze"})


def _load_sibling(name):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"operator_control_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def durable_correction_service(*, state_dir, broker, hermes_home=None, kanban_board=None):
    """Build the supported profile-private/native correction integration."""
    state = Path(state_dir)
    adapters = _load_sibling("correction_adapters")
    corrections = _load_sibling("corrections")
    authorities = {
        "task_requirement": adapters.NativeKanbanAuthority(hermes_home=hermes_home, board=kanban_board),
        "project_fact": adapters.ProjectLaneAuthority(state / "project-lanes.json"),
        "principal_preference": adapters.SelectedMemoryAuthority(state / "selected-memory.json"),
        "voice": adapters.VoiceProfileAuthority(state / "voice-profile.json"),
        "approval": adapters.BrokerApprovalAuthority(state / "approval-claims.json", broker),
    }
    return corrections.CorrectionService(
        authorities=authorities,
        impact_adapter=adapters.NativeKanbanImpactAdapter(hermes_home=hermes_home, board=kanban_board),
        idempotency=adapters.DurableCorrectionJournal(state / "correction-journal.json"),
    )


def record_correction(record, *, service=None, state_dir=None, broker=None, hermes_home=None, kanban_board=None):
    """Record through an injected service or the supported durable adapters."""
    if service is None:
        if state_dir is None or broker is None:
            raise ValueError("state_dir and protected broker are required")
        service = durable_correction_service(state_dir=state_dir, broker=broker, hermes_home=hermes_home, kanban_board=kanban_board)
    return service.record(record)


def _argument_value(arguments, key):
    if key in arguments:
        return arguments.get(key)
    intent = arguments.get("intent")
    return intent.get(key) if isinstance(intent, dict) else None


def pre_tool_call(tool_name, arguments, *, enabled=False, managed_gate=None):
    """Defense in depth only; callback failures may fail open in Hermes 0.21."""
    if not enabled:
        return {"allowed": tool_name not in KNOWN_WRITE_TOOLS, "reason": "operator-control disabled"}
    if tool_name in GENERIC_WRITE_TOOLS:
        return {"allowed": False, "reason": "generic route is not covered; require human execution"}
    if tool_name in READ_ONLY_TOOLS:
        return {"allowed": True, "reason": "explicit read-only allowlist"}
    if tool_name not in KNOWN_WRITE_TOOLS:
        return {"allowed": False, "reason": "unknown capability fails closed while operator-control is enabled"}
    if not (_argument_value(arguments, "operation_key") and _argument_value(arguments, "approval_id")):
        return {"allowed": False, "reason": "operation key and approval are required"}
    if managed_gate is not None:
        try:
            intent = arguments.get("intent")
            if hasattr(managed_gate, "check_effect_boundary"):
                if not isinstance(intent, dict):
                    return {"allowed": False, "reason": "managed intent required"}
                managed_gate.check_effect_boundary(intent)
            else:
                envelope = _argument_value(arguments, "managed_envelope")
                if not isinstance(envelope, dict):
                    return {"allowed": False, "reason": "managed envelope required"}
                managed_gate.check_current(envelope)
        except PermissionError:
            return {"allowed": False, "reason": "managed authority is stale or unavailable"}
    return {"allowed": True, "reason": "authoritative adapter recheck still required"}


def observe_kanban_transition(event):
    """Record-only: Hermes 0.21 lifecycle callbacks cannot veto transitions."""
    return {"observer_only": True, "direct_done_override": event.get("to") == "done" and not event.get("acceptance_id")}
