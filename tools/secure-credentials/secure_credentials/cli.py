"""Secure credentials command line interface."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import store, vault


def home():
    return Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes")))


def drop_db():
    return Path(os.getenv("SECURE_CREDENTIALS_DROP_DB", str(home() / "secrets" / "credential-drops.db")))


def base_url():
    return os.getenv("SECURE_CREDENTIALS_BASE_URL", "https://credentials.example.com")


def write_private(path, data):
    store.write_private_json(path, data, overwrite=False)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--ttl", type=int, default=86400)
    create.add_argument("--claim-file")
    consume = sub.add_parser("consume")
    consume.add_argument("--claim-file", required=True)
    consume.add_argument("--output", required=True)
    consume.add_argument("--overwrite", action="store_true")
    recover = sub.add_parser("recover-link")
    recover.add_argument("--claim-file", required=True)
    cleanup = sub.add_parser("cleanup")
    sub.add_parser("recover-claims")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("drop_id")
    put = sub.add_parser("vault-put")
    put.add_argument("--service", required=True); put.add_argument("--url", required=True)
    put.add_argument("--login", default=""); put.add_argument("--owner-scope", default="internal")
    put.add_argument("--principal", action="append", required=True)
    put.add_argument("--recipient", action="append")
    put.add_argument("--reset-allowed", action="store_true"); put.add_argument("--source")
    sub.add_parser("vault-list")
    link = sub.add_parser("vault-link")
    link.add_argument("service"); link.add_argument("--ttl", type=int, default=3600)
    link.add_argument("--recipient", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "create":
        result = store.create_drop(drop_db(), base_url(), args.ttl)
        if args.claim_file:
            write_private(args.claim_file, {"drop_id": result["id"], "agent_token": result["agent_token"]})
        print(result["sender_url"])
    elif args.command == "consume":
        claim = json.loads(Path(args.claim_file).read_text())
        if not store.consume_to_file(drop_db(), claim["agent_token"], args.output, overwrite=args.overwrite):
            raise SystemExit("drop unavailable")
        print(json.dumps({"consumed": True, "destination": str(Path(args.output)), "mode": "owner-only"}))
    elif args.command == "recover-link":
        claim = json.loads(Path(args.claim_file).read_text())
        link = store.recipient_link_for_agent(drop_db(), claim["agent_token"], base_url())
        if not link:
            raise SystemExit("recipient link unavailable")
        print(link)
    elif args.command == "cleanup":
        outbox = Path(os.getenv("SECURE_CREDENTIALS_OUTBOX", str(home() / "secrets" / "credential-outbox")))
        print(json.dumps({"expired_deleted": store.cleanup_expired(drop_db(), outbox)}))
    elif args.command == "recover-claims":
        print(json.dumps(store.recover_claims(drop_db()), sort_keys=True))
    elif args.command == "revoke":
        store.revoke(drop_db(), args.drop_id)
        print(json.dumps({"revoked": args.drop_id}))
    elif args.command == "vault-put":
        secret = sys.stdin.read()
        if not secret:
            raise SystemExit("secret required on stdin")
        vault.put(
            args.service, args.url, args.login, secret.rstrip("\n"), args.owner_scope,
            authorized_principals=args.principal, authorized_recipients=args.recipient,
            reset_allowed=args.reset_allowed, source=args.source,
        )
        print(json.dumps({"stored": args.service}))
    elif args.command == "vault-list":
        print(json.dumps(vault.safe_list(), indent=2))
    elif args.command == "vault-link":
        item = vault.get_for_operator(args.service, args.recipient)
        payload = f"Service: {item['service']}\nURL: {item['url']}\nLogin: {item.get('login') or ''}\nSecret: {item['secret']}"
        result = store.create_submitted_drop(drop_db(), base_url(), payload, args.ttl)
        print(result["recipient_url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
