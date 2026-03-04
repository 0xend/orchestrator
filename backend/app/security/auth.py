from __future__ import annotations

from dataclasses import dataclass

from fastapi import Cookie, Header, HTTPException, Query, status

from app.config import get_settings


@dataclass(slots=True)
class AuthenticatedUser:
    id: str


def _parse_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
    orchestrator_user: str | None = Cookie(default=None),
    token: str | None = Query(default=None),
    user: str | None = Query(default=None),
) -> AuthenticatedUser:
    settings = get_settings()

    if not settings.api_auth_required:
        return AuthenticatedUser(id=x_dev_user or orchestrator_user or user or "dev-user")

    bearer_token = _parse_bearer_token(authorization)
    effective_token = bearer_token or token
    if effective_token != settings.dev_bearer_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    return AuthenticatedUser(id=x_dev_user or orchestrator_user or user or "dev-user")
