"""Unit tests for `identity.infrastructure.security` -- the password/OTP/session-token
cryptography adapters. Real Argon2id (slow by design; a handful of calls only) plus the
peppered-SHA-256 OTP/token hashers. `SESSION_SIGNING_KEY` is required (fail-closed, Security Sec
14) -- set once here for the whole module."""

from __future__ import annotations

import pytest

from backbone.persistence.env import MissingInfraConfigError
from identity.infrastructure.security import (
    Argon2PasswordHasherAdapter,
    OtpCodeGeneratorAdapter,
    SessionTokenGeneratorAdapter,
)


@pytest.fixture(autouse=True)
def _signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SIGNING_KEY", "test-signing-key-not-a-real-secret")


def test_password_hasher_verifies_correct_password() -> None:
    hasher = Argon2PasswordHasherAdapter()
    hashed = hasher.hash_password("s3cret123")
    assert hasher.verify_password(password="s3cret123", password_hash=hashed) is True


def test_password_hasher_rejects_wrong_password() -> None:
    hasher = Argon2PasswordHasherAdapter()
    hashed = hasher.hash_password("s3cret123")
    assert hasher.verify_password(password="wrong", password_hash=hashed) is False


def test_password_hash_never_contains_the_plaintext_password() -> None:
    hasher = Argon2PasswordHasherAdapter()
    hashed = hasher.hash_password("s3cret123")
    assert "s3cret123" not in hashed


def test_otp_code_generator_produces_six_digit_codes() -> None:
    generator = OtpCodeGeneratorAdapter()
    for _ in range(20):
        code = generator.generate_code()
        assert len(code) == 6
        assert code.isdigit()


def test_otp_code_hash_is_deterministic_for_same_code_and_key() -> None:
    generator = OtpCodeGeneratorAdapter()
    assert generator.hash_code("123456") == generator.hash_code("123456")


def test_otp_code_hash_differs_for_different_codes() -> None:
    generator = OtpCodeGeneratorAdapter()
    assert generator.hash_code("123456") != generator.hash_code("654321")


def test_otp_code_hash_requires_session_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_SIGNING_KEY", raising=False)
    generator = OtpCodeGeneratorAdapter()
    with pytest.raises(MissingInfraConfigError):
        generator.hash_code("123456")


def test_session_token_generator_produces_unique_high_entropy_tokens() -> None:
    generator = SessionTokenGeneratorAdapter()
    tokens = {generator.generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 32 for t in tokens)


def test_session_token_hash_deterministic_for_same_token() -> None:
    generator = SessionTokenGeneratorAdapter()
    token = generator.generate_token()
    assert generator.hash_token(token) == generator.hash_token(token)


def test_otp_and_session_hashing_are_domain_separated() -> None:
    """Same raw value hashed via the OTP context vs the session context must differ -- proves
    the two peppered contexts don't collide even though they share one underlying key."""
    otp_gen = OtpCodeGeneratorAdapter()
    token_gen = SessionTokenGeneratorAdapter()
    value = "123456"
    assert otp_gen.hash_code(value) != token_gen.hash_token(value)
