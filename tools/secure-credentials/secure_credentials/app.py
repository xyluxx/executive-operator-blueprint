"""FastAPI browser flow for one-time encrypted credential intake."""
from __future__ import annotations

import asyncio
import base64
import html
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .crypto import ensure_private_directory, fernet
from .store import cleanup_expired, connect, flush_delivery_outbox, recipient_record, sender_record, submit_once, take_for_recipient

STATIC = Path(__file__).resolve().parent / "static"


def settings():
    home = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes")))
    prefix = os.getenv("SECURE_CREDENTIALS_PREFIX", "").strip()
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    prefix = prefix.rstrip("/")
    return {
        "db": Path(os.getenv("SECURE_CREDENTIALS_DROP_DB", str(home / "secrets" / "credential-drops.db"))),
        "base_url": os.getenv("SECURE_CREDENTIALS_BASE_URL", "https://credentials.example.com").rstrip("/"),
        "prefix": prefix,
        "outbox": Path(os.getenv("SECURE_CREDENTIALS_OUTBOX", str(home / "secrets" / "credential-outbox"))),
        "exposure": os.getenv("SECURE_CREDENTIALS_EXPOSURE", "private").strip().lower(),
        "rate_limit": int(os.getenv("SECURE_CREDENTIALS_RATE_LIMIT", "30")),
    }


def headers(response):
    response.headers.update({
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Expires": "0",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    })
    return response


def page(body, status=200):
    prefix = settings()["prefix"]
    static = f"{prefix}/static" if prefix else "/static"
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><title>Secure credentials</title><link rel="stylesheet" href="{static}/app.css"></head><body><main><div class="panel-inner">{body}</div></main></body></html>'''
    return HTMLResponse(document, status_code=status)


def wiped():
    return page("<h1>This credential is unavailable.</h1><p>It was consumed, expired, or closed.</p>", 410)


class Payload(BaseModel):
    ciphertext: str = Field(min_length=16, max_length=90000)
    iv: str = Field(min_length=16, max_length=32)
    wrapped_key: str = Field(min_length=100, max_length=1000)


def validate_payload(payload):
    ciphertext = base64.b64decode(payload.ciphertext, validate=True)
    iv = base64.b64decode(payload.iv, validate=True)
    wrapped = base64.b64decode(payload.wrapped_key, validate=True)
    if len(ciphertext) > 65536 or len(iv) != 12 or len(wrapped) != 256:
        raise ValueError("invalid payload")


def create_app():
    cfg = settings()
    prefix = cfg["prefix"]
    static_route = f"{prefix}/static" if prefix else "/static"

    @asynccontextmanager
    async def lifespan(_app):
        async def cleaner():
            while True:
                cleanup_expired(cfg["db"], cfg["outbox"])
                await asyncio.sleep(300)
        task = asyncio.create_task(cleaner())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.rate_windows = defaultdict(deque)
    app.mount(static_route, StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def security(request, call_next):
        length = request.headers.get("content-length")
        try:
            oversized = bool(length and int(length) > 100000)
        except ValueError:
            oversized = True
        if oversized:
            return headers(JSONResponse({"saved": False}, status_code=413))
        relative_path = request.url.path[len(prefix):] if prefix and request.url.path.startswith(prefix) else request.url.path
        if relative_path.startswith(("/d/", "/r/", "/api/drop/")):
            limit = cfg["rate_limit"]
            if not 1 <= limit <= 10000:
                return headers(JSONResponse({"status": "not_ready", "reason": "invalid rate limit"}, status_code=503))
            now = time.monotonic()
            client = request.client.host if request.client else "unknown"
            key = client
            if len(app.state.rate_windows) > 4096:
                for stale_key, stale_window in list(app.state.rate_windows.items()):
                    while stale_window and stale_window[0] <= now - 60:
                        stale_window.popleft()
                    if not stale_window:
                        del app.state.rate_windows[stale_key]
            window = app.state.rate_windows[key]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= limit:
                response = JSONResponse({"saved": False}, status_code=429)
                response.headers["Retry-After"] = "60"
                return headers(response)
            window.append(now)
        return headers(await call_next(request))

    @app.get(f"{prefix}/livez")
    def live():
        return {"status": "alive"}

    @app.get(f"{prefix}/readyz")
    def ready():
        try:
            if cfg["exposure"] != "private":
                raise RuntimeError("bundled service supports private exposure only")
            if not cfg["base_url"].startswith("https://"):
                raise RuntimeError("base URL must use HTTPS")
            if not 1 <= cfg["rate_limit"] <= 10000:
                raise RuntimeError("rate limit must be between 1 and 10000")
            fernet()
            ensure_private_directory(cfg["outbox"])
            con = connect(cfg["db"])
            try:
                con.execute("SELECT 1").fetchone()
            finally:
                con.close()
            return {"status": "ready", "exposure": cfg["exposure"]}
        except Exception as exc:
            return JSONResponse({"status": "not_ready", "reason": str(exc)}, status_code=503)

    @app.get(f"{prefix}/d/{{sender_token}}")
    def sender(sender_token: str):
        row = sender_record(cfg["db"], sender_token)
        if not row:
            return wiped()
        public = html.escape(row["public_key_b64"], quote=True)
        return page(
            f'<h1>Share credentials securely</h1><p>Encrypted in this browser before upload.</p><form id="drop" data-public-key="{public}" data-prefix="{html.escape(prefix, quote=True)}"><textarea id="credentials" required autofocus autocomplete="off" spellcheck="false" aria-label="Credentials"></textarea><button type="submit">Encrypt and save</button></form><script src="{static_route}/crypto.js" defer></script>'
        )

    @app.post(f"{prefix}/api/drop/{{sender_token}}")
    def submit(sender_token: str, payload: Payload):
        try:
            validate_payload(payload)
        except Exception:
            return JSONResponse({"saved": False}, status_code=400)
        result = submit_once(cfg["db"], sender_token, payload.ciphertext, payload.iv, payload.wrapped_key, base_url=cfg["base_url"])
        if not result:
            return JSONResponse({"saved": False}, status_code=410)
        delivery = "queued"
        try:
            written = flush_delivery_outbox(cfg["db"], cfg["outbox"])
            if any(path.stem == result["id"] for path in written):
                delivery = "delivered"
        except Exception:
            delivery = "queued"
        return {"saved": True, "delivery": delivery, "already_submitted": result["already_submitted"]}

    @app.get(f"{prefix}/r/{{recipient_token}}")
    def recipient(recipient_token: str):
        if not recipient_record(cfg["db"], recipient_token):
            return wiped()
        action = f"{prefix}/r/{recipient_token}" if prefix else f"/r/{recipient_token}"
        return page(f'<h1>One-time credential</h1><p>Reveal permanently consumes this drop.</p><form method="post" action="{html.escape(action, quote=True)}"><button type="submit">Reveal once</button></form>')

    @app.post(f"{prefix}/r/{{recipient_token}}")
    def reveal(recipient_token: str):
        secret = take_for_recipient(cfg["db"], recipient_token)
        if secret is None:
            return wiped()
        return page(f"<h1>Credential</h1><pre>{html.escape(secret)}</pre>")

    return app


app = create_app()
