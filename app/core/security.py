"""Administrative endpoint authentication helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings


ADMIN_SESSION_COOKIE = "legal_rag_admin_session"


async def require_admin_token(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    if is_admin_authenticated(request, x_api_key=x_api_key, authorization=authorization):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API token",
    )


def is_admin_authenticated(
    request: Request,
    *,
    x_api_key: str | None = None,
    authorization: str | None = None,
) -> bool:
    expected = settings.api_auth_token
    if not expected:
        return True

    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    token = x_api_key or bearer
    if token and hmac.compare_digest(token, expected):
        return True

    session_token = request.cookies.get(ADMIN_SESSION_COOKIE)
    return bool(session_token and verify_admin_session(session_token))


def create_admin_session(now: int | None = None) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = {
        "iat": issued_at,
        "exp": issued_at + settings.admin_session_ttl_seconds,
        "role": "admin",
    }
    raw_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(raw_payload)
    return f"{raw_payload}.{signature}"


def verify_admin_session(token: str) -> bool:
    try:
        raw_payload, signature = token.split(".", 1)
    except ValueError:
        return False
    expected_signature = _sign(raw_payload)
    if not hmac.compare_digest(signature, expected_signature):
        return False
    try:
        payload = json.loads(_b64decode(raw_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return False
    expires_at = int(payload.get("exp") or 0)
    return payload.get("role") == "admin" and expires_at >= int(time.time())


def _sign(value: str) -> str:
    secret = settings.api_auth_token or "local-dev-admin-session"
    digest = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256)
    return _b64encode(digest.digest())


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
