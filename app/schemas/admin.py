"""Schemas for the lightweight administrator session flow."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AdminLoginRequest(BaseModel):
    token: str = Field(..., min_length=1, description="管理员 API token。")

    @field_validator("token")
    @classmethod
    def token_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("token must not be blank")
        return cleaned


class AdminSessionResponse(BaseModel):
    authenticated: bool = Field(description="当前请求是否已通过管理员鉴权。")

