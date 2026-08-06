"""identity/infrastructure -- password, OTP-code, and session-token cryptography. Argon2id for
passwords (Security Sec 3.1, named explicitly); OTP codes and session tokens use salted/peppered
SHA-256, a deliberately different (faster) primitive from Argon2id -- neither is a user-chosen
long-lived secret the way a password is: an OTP code is short-lived, high-entropy-enough-once
combined with the throttle+lockout policy, and a session token is generated with 256 bits of its
own entropy (`secrets.token_urlsafe`), not derived from anything guessable.

Both peppers derive from the single `SESSION_SIGNING_KEY` environment variable already declared
in `deployment/env/.env.*.example` ("Session auth (server-side sessions in Redis, not JWT)") --
domain-separated by a fixed HMAC context prefix per use, rather than inventing two new secret
env vars for the same underlying key material. Fail closed on a missing secret (Security Sec 14).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import VerifyMismatchError

from backbone.persistence.env import MissingInfraConfigError, required_env


class Argon2PasswordHasherAdapter:
    """Implements `identity.application.ports.PasswordHasherPort`."""

    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher()

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, *, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except VerifyMismatchError:
            return False


def _signing_key() -> bytes:
    return required_env("SESSION_SIGNING_KEY").encode()


class OtpCodeGeneratorAdapter:
    """Implements `identity.application.ports.OtpCodeGeneratorPort`. A 6-digit numeric code
    (fixed length, Security Sec 3.1) generated with `secrets.randbelow` (CSPRNG, not `random`)."""

    _CODE_LENGTH = 6
    _HMAC_CONTEXT = b"identity.otp:"

    def generate_code(self) -> str:
        value = secrets.randbelow(10**self._CODE_LENGTH)
        return str(value).zfill(self._CODE_LENGTH)

    def hash_code(self, code: str) -> str:
        return hmac.new(
            _signing_key(), self._HMAC_CONTEXT + code.encode(), hashlib.sha256
        ).hexdigest()


class SessionTokenGeneratorAdapter:
    """Implements `identity.application.ports.SessionTokenGeneratorPort`. The raw token (256
    bits of CSPRNG entropy) is what the client holds (cookie/Bearer); only its hash is ever
    persisted (Security Sec 3.2 `identity.session.token_hash`)."""

    _HMAC_CONTEXT = b"identity.session:"

    def generate_token(self) -> str:
        return secrets.token_urlsafe(32)

    def hash_token(self, token: str) -> str:
        return hmac.new(
            _signing_key(), self._HMAC_CONTEXT + token.encode(), hashlib.sha256
        ).hexdigest()


__all__ = [
    "Argon2PasswordHasherAdapter",
    "MissingInfraConfigError",
    "OtpCodeGeneratorAdapter",
    "SessionTokenGeneratorAdapter",
]
