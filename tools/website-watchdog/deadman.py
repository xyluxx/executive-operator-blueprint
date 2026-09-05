#!/usr/bin/env python3
"""Fail visibly when the website collector has stopped checking."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--max-age-seconds", required=True, type=int)
    args = parser.parse_args(argv)
    if args.max_age_seconds < 1:
        parser.error("--max-age-seconds must be positive")
    try:
        state = json.loads(args.state.read_text())
        checked = datetime.fromisoformat(state["checked_at"])
        if checked.tzinfo is None:
            raise ValueError("checked_at lacks timezone")
        age = (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds()
        if age <= args.max_age_seconds:
            return 0
        kind = "watchdog_stale"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        age = None
        kind = "watchdog_state_unreadable"
    print(json.dumps({"kind": kind, "state": str(args.state), "age_seconds": age}, separators=(",", ":")))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
