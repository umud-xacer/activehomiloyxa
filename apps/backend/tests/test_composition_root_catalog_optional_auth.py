"""Regression test: `composition_root.provide_catalog_optional_acting_user` must degrade to
`None` for EITHER half of the failure modes `ApplicationAuthorizationService.resolve_acting_context`
documents itself as able to raise -- the application-layer `IdentityApplicationError`
(`InvalidSessionTokenError`/`AccountNotFoundError`) AND the domain `IdentityDomainError`
(`SessionExpiredError`/`SessionRevokedError`/`AccountNotActiveError`). An earlier version of this
function caught only `IdentityApplicationError`, so a merely-expired or revoked session cookie on
a public browse endpoint (`listListings`/`getListing`/`listListingImages`, `security: []`)
propagated uncaught instead of falling back to anonymous browsing -- the entire point of the
"optional" variant. Monkeypatches `provide_catalog_acting_user` directly rather than standing up
real Postgres/Redis sessions, since this test is only about the except clause's exception-type
coverage, not the session-resolution logic itself (covered elsewhere by identity's own tests).
"""

from __future__ import annotations

import pytest

import composition_root
from identity.application.exceptions import InvalidSessionTokenError
from identity.domain.exceptions import SessionExpiredError


async def test_application_error_degrades_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise_application_error(**_kwargs: object) -> None:
        raise InvalidSessionTokenError()

    monkeypatch.setattr(composition_root, "provide_catalog_acting_user", _raise_application_error)

    result = await composition_root.provide_catalog_optional_acting_user(ah_session="stale-token")
    assert result is None


async def test_domain_error_degrades_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug this test guards against: `SessionExpiredError` is an `IdentityDomainError`, a
    completely separate hierarchy from `IdentityApplicationError` (both subclass `Exception`
    directly) -- catching only the latter let this one through uncaught."""

    async def _raise_domain_error(**_kwargs: object) -> None:
        raise SessionExpiredError()

    monkeypatch.setattr(composition_root, "provide_catalog_acting_user", _raise_domain_error)

    result = await composition_root.provide_catalog_optional_acting_user(ah_session="expired-token")
    assert result is None


async def test_missing_token_degrades_to_none_without_calling_resolution() -> None:
    """`authorization=None` passed explicitly -- calling a FastAPI dependency function directly
    (not through the framework) leaves an unresolved `Header(...)` default marker object
    otherwise, an artifact of this test harness, not of production request handling."""
    result = await composition_root.provide_catalog_optional_acting_user(
        ah_session=None, authorization=None
    )
    assert result is None


async def test_unrelated_exception_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not overly broad: a genuine bug (e.g. a `TypeError`) must still surface as a 500, not be
    silently swallowed into a misleading "anonymous" fallback."""

    async def _raise_type_error(**_kwargs: object) -> None:
        raise TypeError("unrelated programming error")

    monkeypatch.setattr(composition_root, "provide_catalog_acting_user", _raise_type_error)

    with pytest.raises(TypeError):
        await composition_root.provide_catalog_optional_acting_user(ah_session="some-token")
