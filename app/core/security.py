"""Minimal API-token protection for administrative endpoints."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings


async def require_admin_token(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    expected = settings.api_auth_token
    if not expected:
        return

    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    token = x_api_key or bearer
    if token == expected:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API token",
    )
