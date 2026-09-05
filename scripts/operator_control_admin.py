#!/usr/bin/env python3
"""Human/admin-only operator-control issuance CLI.

This program is intentionally not imported or registered by the model-facing
plugin. Authentication is a private owner-only token file plus a separately
supplied token; successful records are HMAC signed into protected local state.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping


def authenticate_admin(token_file: Path, supplied: str | None) -> bytes:
    info=token_file.stat()
    if os.name == "posix" and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise PermissionError("admin token file must be owner-owned mode 0600")
    expected=token_file.read_bytes().strip()
    if len(expected) < 32 or supplied is None or not hmac.compare_digest(expected,supplied.encode()):
        raise PermissionError("authenticated human administrator required")
    return expected


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("record must be a JSON object")
    return value


def _signed(kind: str, record: Mapping[str, Any], key: bytes) -> dict[str, Any]:
    value={"kind":kind,"record":dict(record),"algorithm":"hmac-sha256"}
    raw=json.dumps(value,sort_keys=True,separators=(",",":")).encode()
    value["signature"]=hmac.new(key,raw,hashlib.sha256).hexdigest()
    return value


def issue(kind: str, record: Mapping[str, Any], *, state_root: Path, key: bytes) -> Path:
    if kind not in {"policy","approval","evidence","acceptance"}: raise ValueError("unsupported admin record")
    identifier=str(record.get(f"{kind}_id") or record.get("id") or "")
    if not identifier or "/" in identifier or ".." in identifier: raise ValueError(f"{kind} identifier required")
    directory=state_root/kind; directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    destination=directory/f"{identifier}.json"
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    fd=os.open(destination,flags,0o600)
    try:
        os.write(fd,(json.dumps(_signed(kind,record,key),sort_keys=True)+"\n").encode())
        os.fsync(fd)
    finally: os.close(fd)
    return destination


def main(argv: list[str] | None=None) -> int:
    parser=argparse.ArgumentParser(description="Human/admin-only policy and issuance control")
    parser.add_argument("kind",choices=["policy","approval","evidence","acceptance"])
    parser.add_argument("record",type=Path)
    parser.add_argument("--state-root",type=Path,required=True)
    parser.add_argument("--token-file",type=Path,required=True)
    parser.add_argument("--admin-token",help="Prefer OPERATOR_CONTROL_ADMIN_TOKEN to avoid shell history")
    args=parser.parse_args(argv)
    supplied=args.admin_token or os.environ.get("OPERATOR_CONTROL_ADMIN_TOKEN")
    try:
        key=authenticate_admin(args.token_file,supplied)
        destination=issue(args.kind,_load(args.record),state_root=args.state_root,key=key)
    except (OSError,ValueError,PermissionError,json.JSONDecodeError) as exc:
        print(json.dumps({"success":False,"error":str(exc)}),file=sys.stderr); return 2
    print(json.dumps({"success":True,"kind":args.kind,"path":str(destination)})); return 0


if __name__ == "__main__":
    raise SystemExit(main())
