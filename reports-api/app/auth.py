from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import get_settings

API_KEY_HEADER_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def _matches(provided: str, expected: str) -> bool:
    left = provided.encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def require_api_key(
    x_api_key: str | None = Security(api_key_header),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    expected = (get_settings().api_secret_key or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_SECRET_KEY is not configured on the server.",
        )
    provided = (x_api_key or "").strip() or _extract_bearer(authorization)
    if not provided or not _matches(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key. Send header X-API-Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return provided
