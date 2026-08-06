"""Unit tests for the `Session` aggregate (DDD Sec 5.1; Security Sec 3.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.domain import ProfileNotOwnedError, Session, SessionExpiredError, SessionRevokedError
from shared_kernel import BusinessProfileId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _issue_session(**overrides: object) -> Session:
    defaults: dict[str, object] = {
        "session_id": uuid4(),
        "account_id": UserId(value=uuid4()),
        "token_hash": "hash",
        "ip_address": "1.2.3.4",
        "user_agent": "pytest",
        "now": NOW,
        "expires_at": NOW + timedelta(hours=720),
    }
    defaults.update(overrides)
    return Session.issue(**defaults)  # type: ignore[arg-type]


def test_issue_creates_session_in_personal_context_by_default() -> None:
    session = _issue_session()
    assert session.acting_profile_id is None
    assert session.revoked_at is None


def test_require_valid_passes_for_unexpired_unrevoked_session() -> None:
    session = _issue_session()
    session.require_valid(now=NOW)  # does not raise


def test_require_valid_raises_session_expired_error_past_expiry() -> None:
    session = _issue_session(expires_at=NOW + timedelta(hours=1))
    with pytest.raises(SessionExpiredError):
        session.require_valid(now=NOW + timedelta(hours=2))


def test_require_valid_raises_session_revoked_error() -> None:
    session = _issue_session().revoke(now=NOW)
    with pytest.raises(SessionRevokedError):
        session.require_valid(now=NOW)


def test_switch_acting_profile_to_owned_profile_succeeds() -> None:
    profile = BusinessProfileId(value=uuid4())
    session = _issue_session()
    updated = session.switch_acting_profile(
        new_acting_profile_id=profile, owned_profile_ids=(profile,), now=NOW
    )
    assert updated.acting_profile_id == profile


def test_switch_acting_profile_to_personal_context_always_succeeds() -> None:
    profile = BusinessProfileId(value=uuid4())
    session = _issue_session(acting_profile_id=profile)
    updated = session.switch_acting_profile(
        new_acting_profile_id=None, owned_profile_ids=(profile,), now=NOW
    )
    assert updated.acting_profile_id is None


def test_switch_acting_profile_to_unowned_profile_raises() -> None:
    owned = BusinessProfileId(value=uuid4())
    other = BusinessProfileId(value=uuid4())
    session = _issue_session()
    with pytest.raises(ProfileNotOwnedError):
        session.switch_acting_profile(
            new_acting_profile_id=other, owned_profile_ids=(owned,), now=NOW
        )


def test_revoke_sets_revoked_at() -> None:
    session = _issue_session()
    revoked = session.revoke(now=NOW)
    assert revoked.revoked_at == NOW
