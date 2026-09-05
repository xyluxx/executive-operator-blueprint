#!/usr/bin/env python3
"""Configurable notification policy for website reliability events."""

DEFAULT_POLICY = {
    "healthy": "silent",
    "false_alarm": "silent",
    "routine_repair_succeeded": "silent",
    "bounded_repair_failed": "notify",
}


def evaluate(event, route, policy=None):
    effective = dict(DEFAULT_POLICY)
    effective.update(policy or {})
    notify = effective.get(event, "silent") == "notify"
    return {"notify": notify, "route": route if notify else None, "reason": event}
