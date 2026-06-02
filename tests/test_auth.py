from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from uuid import uuid4

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import RateLimiter, verify_request


def _request(secret: str = "test-secret") -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings={"auth": {"jwt_secret": secret}})))


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _token(secret: str, subject: str | None = None, rpm: int = 60) -> str:
    return jwt.encode(
        {
            "sub": subject or str(uuid4()),
            "iat": int(time.time()),
            "rpm": rpm,
        },
        secret,
        algorithm="HS256",
    )


class AuthTests(unittest.TestCase):
    def test_auth_disabled_without_secret(self) -> None:
        request = _request(secret="")

        self.assertIsNone(verify_request(request, None))

    def test_valid_token_returns_context(self) -> None:
        secret = "test-secret"
        subject = str(uuid4())
        token = _token(secret, subject=subject, rpm=5)

        context = verify_request(_request(secret), _credentials(token))

        self.assertIsNotNone(context)
        self.assertEqual(context.subject, subject)
        self.assertEqual(context.requests_per_minute, 5)
        self.assertTrue(context.token_id)

    def test_invalid_subject_is_rejected(self) -> None:
        secret = "test-secret"
        token = _token(secret, subject="not-a-uuid")

        with self.assertRaises(HTTPException) as raised:
            verify_request(_request(secret), _credentials(token))

        self.assertEqual(raised.exception.status_code, 401)

    def test_rate_limit_uses_rpm_claim(self) -> None:
        secret = "test-secret"
        subject = str(uuid4())
        token = _token(secret, subject=subject, rpm=1)
        request = _request(secret)
        credentials = _credentials(token)

        verify_request(request, credentials)
        with self.assertRaises(HTTPException) as raised:
            verify_request(request, credentials)

        self.assertEqual(raised.exception.status_code, 429)

    def test_rate_limit_is_per_token(self) -> None:
        secret = "test-secret"
        subject = str(uuid4())
        first_token = _token(secret, subject=subject, rpm=1)
        second_token = jwt.encode(
            {"sub": subject, "iat": int(time.time()), "rpm": 1, "nonce": "second"},
            secret,
            algorithm="HS256",
        )
        request = _request(secret)

        verify_request(request, _credentials(first_token))
        verify_request(request, _credentials(second_token))


class RateLimiterTests(unittest.TestCase):
    def test_rate_limiter_resets_each_minute(self) -> None:
        limiter = RateLimiter()
        subject = str(uuid4())

        limiter.check(subject, requests_per_minute=1, now=120)
        with self.assertRaises(HTTPException):
            limiter.check(subject, requests_per_minute=1, now=121)

        limiter.check(subject, requests_per_minute=1, now=180)


if __name__ == "__main__":
    unittest.main()
