from __future__ import annotations

import time
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


AUTH_SCHEME = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    subject: str
    issued_at: int
    requests_per_minute: int
    token_id: str


class RateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._windows: dict[tuple[str, int], int] = {}

    def check(self, subject: str, requests_per_minute: int, now: int | None = None) -> None:
        current_time = int(time.time() if now is None else now)
        current_window = current_time // 60
        key = (subject, current_window)

        with self._lock:
            # Keep memory bounded without retaining old minute windows forever.
            stale_keys = [window_key for window_key in self._windows if window_key[1] < current_window]
            for stale_key in stale_keys:
                del self._windows[stale_key]

            used = self._windows.get(key, 0)
            if used >= requests_per_minute:
                retry_after = 60 - (current_time % 60)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            self._windows[key] = used + 1


rate_limiter = RateLimiter()


def _validate_claims(payload: dict[str, Any], token: str) -> AuthContext:
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing sub")
    try:
        UUID(subject)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT sub must be a UUID") from exc

    issued_at = payload.get("iat")
    if not isinstance(issued_at, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing integer iat")

    requests_per_minute = payload.get("rpm")
    if not isinstance(requests_per_minute, int) or requests_per_minute < 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing positive integer rpm")

    return AuthContext(
        subject=subject,
        issued_at=issued_at,
        requests_per_minute=requests_per_minute,
        token_id=sha256(token.encode("utf-8")).hexdigest(),
    )


def verify_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(AUTH_SCHEME),
) -> AuthContext | None:
    settings = getattr(request.app.state, "settings", {})
    auth_settings = settings.get("auth", {}) if isinstance(settings, dict) else {}
    secret = auth_settings.get("jwt_secret") or ""
    if not secret:
        return None

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    algorithms = auth_settings.get("jwt_algorithms", ["HS256"])
    try:
        payload = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=algorithms,
            options={"require": ["sub", "iat", "rpm"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc

    context = _validate_claims(payload, credentials.credentials)
    rate_limiter.check(context.token_id, context.requests_per_minute)
    return context
