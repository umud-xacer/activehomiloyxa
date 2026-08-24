"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/configuration/media/identity-bridge providers swapped for in-memory fakes
(`conftest.py`) via `app.dependency_overrides` -- same router/error-handler wiring as production.
Covers the fifteen catalog/favorites operationIds and the contract's declared error paths.
Mirrors `apps/backend/tests/media/test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.favorite_use_cases import FavoriteUseCases
from catalog.application.listing_use_cases import ListingUseCases
from catalog.application.quota_service import QuotaEnforcementService
from catalog.interfaces.auth import ActingUser
from catalog.interfaces.di import (
    get_acting_user,
    get_favorite_use_cases,
    get_listing_use_cases,
    get_optional_acting_user,
)
from main import create_app
from shared_kernel import BusinessProfileId, UserId

from .conftest import (
    FakeCategoryFormPort,
    FakeCreditBalancePort,
    FakeFavoriteRepository,
    FakeListingRepository,
    FakeMediaAssetReaderPort,
    FakeOutbox,
    FakePlatformSettingsReaderPort,
    FakeSubscriptionSnapshotRepository,
)

TEST_OWNER = UserId(value=uuid4())
TEST_OTHER = UserId(value=uuid4())
TEST_OWNER_WITH_PROFILE = UserId(value=uuid4())
TEST_OWNER_PROFILE_ID = BusinessProfileId(value=uuid4())
"""Listing paywall (2026-08-23): a second acting user WITH a business profile, distinct from
`TEST_OWNER` (profileless, matches every other pre-existing test's assumption) -- `create_listing`
only ever consumes a credit for a profile-bearing owner (`ListingUseCases.create_listing`'s own
`auto_compute_payment_requirement` docstring: an individual with no profile always falls through
to `requires_payment=True`, there is no way for them to hold a `LISTING_CREDIT_BALANCE`). Used
only by the two tests that need `publish=True` to actually publish immediately."""
_TOKEN_TO_USER = {
    "owner-token": TEST_OWNER,
    "other-token": TEST_OTHER,
    "owner-with-profile-token": TEST_OWNER_WITH_PROFILE,
}
_TOKEN_TO_PROFILE = {"owner-with-profile-token": TEST_OWNER_PROFILE_ID}


@pytest.fixture
def client(
    fake_listings: FakeListingRepository,
    fake_favorites: FakeFavoriteRepository,
    fake_categories: FakeCategoryFormPort,
    fake_settings: FakePlatformSettingsReaderPort,
    fake_media: FakeMediaAssetReaderPort,
    fake_subscriptions: FakeSubscriptionSnapshotRepository,
    fake_credit_balance: FakeCreditBalancePort,
    fake_outbox: FakeOutbox,
) -> Iterator[TestClient]:
    def _listing_use_cases() -> ListingUseCases:
        return ListingUseCases(
            listings=fake_listings,
            categories=fake_categories,
            settings=fake_settings,
            media=fake_media,
            outbox=fake_outbox,
            quota=QuotaEnforcementService(subscriptions=fake_subscriptions),
            duplicates=DuplicateDetectionService(listings=fake_listings),
            credit_balance=fake_credit_balance,
        )

    def _favorite_use_cases() -> FavoriteUseCases:
        return FavoriteUseCases(
            favorites=fake_favorites, listings=fake_listings, outbox=fake_outbox
        )

    async def acting_user_override(
        authorization: str | None = Header(default=None),
    ) -> ActingUser:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        account_id = _TOKEN_TO_USER.get(token or "")
        if account_id is None:
            raise HTTPException(status_code=401, detail="no valid session")
        return ActingUser(
            account_id=account_id, acting_profile_id=_TOKEN_TO_PROFILE.get(token or "")
        )

    async def optional_acting_user_override(
        authorization: str | None = Header(default=None),
    ) -> ActingUser | None:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        account_id = _TOKEN_TO_USER.get(token or "")
        if account_id is None:
            return None
        return ActingUser(
            account_id=account_id, acting_profile_id=_TOKEN_TO_PROFILE.get(token or "")
        )

    app = create_app()
    app.dependency_overrides[get_listing_use_cases] = _listing_use_cases
    app.dependency_overrides[get_favorite_use_cases] = _favorite_use_cases
    app.dependency_overrides[get_acting_user] = acting_user_override
    app.dependency_overrides[get_optional_acting_user] = optional_acting_user_override

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _auth_headers(token: str = "owner-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "listingType": "ADVERTISEMENT",
        "categoryId": str(uuid4()),
        "title": "Nice apartment",
        "attributes": {"rooms": 2},
        "publish": False,
    }
    body.update(overrides)
    return body


def test_create_listing_returns_201(client: TestClient) -> None:
    response = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    assert response.status_code == 201
    body = response.json()
    assert body["lifecycleState"] == "DRAFT"
    assert body["title"] == "Nice apartment"
    assert body["lockVersion"] is not None


def test_create_listing_without_session_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/listings", json=_create_body())
    assert response.status_code == 401


def test_create_listing_publish_true_is_immediately_visible(
    client: TestClient, fake_credit_balance: FakeCreditBalancePort
) -> None:
    """Listing paywall (2026-08-23): `publish=True` alone no longer guarantees immediate
    visibility -- `createListing` now always computes `requires_payment` for real
    (`auto_compute_payment_requirement=True`), so this exercises the "owner has an available
    listing credit" path (`owner-with-profile-token` + `fake_credit_balance.has_credit = True`),
    the one case where `publish=True` still results in an immediate `PUBLISHED`."""
    fake_credit_balance.has_credit = True
    response = client.post(
        "/api/v1/listings",
        headers=_auth_headers("owner-with-profile-token"),
        json=_create_body(publish=True),
    )
    assert response.status_code == 201
    listing_id = response.json()["id"]
    assert fake_credit_balance.consumed_for == [TEST_OWNER_PROFILE_ID.value]

    listed = client.get(f"/api/v1/listings/{listing_id}")
    assert listed.status_code == 200
    assert listed.json()["lifecycleState"] == "PUBLISHED"


def test_create_listing_publish_true_without_credit_awaits_payment(
    client: TestClient,
) -> None:
    """Listing paywall (2026-08-23): the new default path -- no business profile, no credit --
    `publish=True` is deferred, not honoured; the listing is created but held `DRAFT`+
    `awaitingPayment` rather than immediately visible."""
    response = client.post(
        "/api/v1/listings", headers=_auth_headers(), json=_create_body(publish=True)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["lifecycleState"] == "DRAFT"
    assert body["awaitingPayment"] is True


def test_get_listing_draft_is_hidden_from_anonymous_caller(client: TestClient) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}")
    assert response.status_code == 404


def test_get_listing_draft_is_visible_to_its_owner(client: TestClient) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}", headers=_auth_headers())
    assert response.status_code == 200


def test_list_listings_only_returns_public_visible_listings(
    client: TestClient, fake_credit_balance: FakeCreditBalancePort
) -> None:
    fake_credit_balance.has_credit = True
    client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body(publish=False))
    client.post(
        "/api/v1/listings",
        headers=_auth_headers("owner-with-profile-token"),
        json=_create_body(publish=True, title="Visible one"),
    )

    response = client.get("/api/v1/listings")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Visible one"


def test_update_listing_with_matching_lock_version_succeeds(client: TestClient) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]
    lock_version = created.json()["lockVersion"]

    response = client.put(
        f"/api/v1/listings/{listing_id}",
        headers=_auth_headers(),
        json={"title": "Updated title", "lockVersion": lock_version},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"
    assert response.json()["lifecycleState"] == "DRAFT"


def test_update_listing_with_stale_lock_version_returns_409(client: TestClient) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]

    response = client.put(
        f"/api/v1/listings/{listing_id}",
        headers=_auth_headers(),
        json={"title": "x", "lockVersion": 999},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_update_listing_by_non_owner_returns_403(client: TestClient) -> None:
    created = client.post(
        "/api/v1/listings", headers=_auth_headers("owner-token"), json=_create_body()
    )
    listing_id = created.json()["id"]

    response = client.put(
        f"/api/v1/listings/{listing_id}",
        headers=_auth_headers("other-token"),
        json={"title": "x", "lockVersion": created.json()["lockVersion"]},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_change_listing_status_publish(client: TestClient) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]

    response = client.post(
        f"/api/v1/listings/{listing_id}/status",
        headers=_auth_headers(),
        json={"action": "PUBLISH"},
    )
    assert response.status_code == 200
    assert response.json()["lifecycleState"] == "PUBLISHED"


def test_change_listing_status_illegal_transition_returns_409(
    client: TestClient,
) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]

    response = client.post(
        f"/api/v1/listings/{listing_id}/status",
        headers=_auth_headers(),
        json={"action": "SUSPEND"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ILLEGAL_STATE_TRANSITION"


def test_delete_listing_returns_204(client: TestClient) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]

    response = client.delete(f"/api/v1/listings/{listing_id}", headers=_auth_headers())
    assert response.status_code == 204


def test_attach_list_and_detach_listing_images(
    client: TestClient, fake_media: FakeMediaAssetReaderPort
) -> None:
    created = client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    listing_id = created.json()["id"]
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)

    attach = client.post(
        f"/api/v1/listings/{listing_id}/images",
        headers=_auth_headers(),
        json={"mediaAssetId": str(media_asset_id), "position": 1},
    )
    assert attach.status_code == 201
    image_id = attach.json()["id"]

    listed = client.get(f"/api/v1/listings/{listing_id}/images")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detach = client.delete(
        f"/api/v1/listings/{listing_id}/images/{image_id}", headers=_auth_headers()
    )
    assert detach.status_code == 204


def test_get_listing_statistics_owner_only(client: TestClient) -> None:
    created = client.post(
        "/api/v1/listings", headers=_auth_headers("owner-token"), json=_create_body()
    )
    listing_id = created.json()["id"]

    owner_response = client.get(
        f"/api/v1/listings/{listing_id}/statistics",
        headers=_auth_headers("owner-token"),
    )
    assert owner_response.status_code == 200
    assert owner_response.json()["favorites"] == 0

    other_response = client.get(
        f"/api/v1/listings/{listing_id}/statistics",
        headers=_auth_headers("other-token"),
    )
    assert other_response.status_code == 403


def test_list_my_listings(client: TestClient) -> None:
    client.post("/api/v1/listings", headers=_auth_headers(), json=_create_body())
    response = client.get("/api/v1/me/listings", headers=_auth_headers())
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_favorites_add_list_remove(client: TestClient) -> None:
    created = client.post(
        "/api/v1/listings", headers=_auth_headers(), json=_create_body(publish=True)
    )
    listing_id = created.json()["id"]

    add = client.post(
        "/api/v1/me/favorites", headers=_auth_headers(), json={"listingId": listing_id}
    )
    assert add.status_code == 201

    listed = client.get("/api/v1/me/favorites", headers=_auth_headers())
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    removed = client.delete(f"/api/v1/me/favorites/{listing_id}", headers=_auth_headers())
    assert removed.status_code == 204

    listed_after = client.get("/api/v1/me/favorites", headers=_auth_headers())
    assert listed_after.json()["items"] == []
