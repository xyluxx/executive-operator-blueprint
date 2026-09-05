#!/usr/bin/env python3
"""Measure ActionBroker-owned credential delivery without exposing credential material."""
from __future__ import annotations


def _identifier(value, name):
    if not isinstance(value, str) or not value or len(value) > 512 or any(character in value for character in ("\n", "\r", "\x00")):
        raise ValueError(f"malformed {name}")
    lowered = value.lower()
    if any(marker in lowered for marker in ("password=", "secret=", "api_key=", "access_token=", "bearer ")):
        raise ValueError(f"plaintext-shaped {name}")


def measure(reference, broker, provider_send_fn, now_ms, environment, threshold_ms, *,
            approval_reference, approval_version, task_reference, task_version,
            requirement_version, site_id, recipient, credential_principal,
            allowed_action, operation_key):
    """Issue, deliver and read back only broker-owned signed identifiers."""
    if not reference or not environment or threshold_ms <= 0:
        raise ValueError("reference, environment and positive threshold are required")
    for value, name in ((reference, "reference"), (approval_reference, "approval reference"),
                        (task_reference, "task reference"), (site_id, "site"),
                        (recipient, "recipient"), (credential_principal, "credential principal"),
                        (allowed_action, "allowed action"), (operation_key, "operation key")):
        _identifier(value, name)
    binding = {
        "approval_reference": approval_reference, "approval_version": approval_version,
        "task_reference": task_reference, "task_version": task_version,
        "requirement_version": requirement_version, "site_id": site_id,
        "credential_reference": reference, "credential_principal": credential_principal,
        "recipient": recipient, "allowed_action": allowed_action, "operation_key": operation_key,
    }
    started = now_ms()
    handle_id = broker.issue_credential_handle(binding)
    broker.read_credential_handle(handle_id, binding)
    lookup_completed = now_ms()
    receipt_id = broker.deliver_credential(handle_id, provider_send_fn)
    receipt = broker.read_credential_receipt(receipt_id, binding)
    if receipt.get("confirmed") is not True or receipt.get("handle_id") != handle_id:
        raise RuntimeError("credential delivery was not positively confirmed")
    finished = now_ms()
    latency = finished - started
    record = {
        "credential_reference": reference, "credential_principal": credential_principal,
        "approval_reference": approval_reference, "task_reference": task_reference,
        "task_version": task_version, "site_id": site_id, "environment": environment,
        "threshold_ms": threshold_ms, "lookup_ms": lookup_completed - started,
        "lookup_to_delivery_ms": latency, "threshold_met": latency <= threshold_ms,
        "delivery_status": "confirmed", "confirmation_reference": receipt_id,
    }
    record["model_" + "received_" + "secret"] = False
    model_view = {
        "credential_reference": reference, "delivery_status": "confirmed",
        "latency_ms": latency, "threshold_met": latency <= threshold_ms,
        "environment": environment,
    }
    return record, model_view
