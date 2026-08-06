"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/identity/configuration providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers all nine
Ads-tagged operations (seven operator, two public -- `serveBanner` folds in as a third public
GET). Mirrors `apps/backend/tests/billing/test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from ads.application.campaign_use_cases import CampaignUseCases
from ads.application.ports import EntitlementSnapshot
from ads.application.serve_use_cases import BannerServingUseCases
from ads.interfaces.auth import ActingOperator
from ads.interfaces.di import get_acting_operator, get_campaign_use_cases, get_serving_use_cases
from main import create_app
from shared_kernel import UserId

from .conftest import (
    FakeBannerCampaignRepository,
    FakeCreativeReaderPort,
    FakeEntitlementProjectionRepository,
    FakeOutbox,
    FakePlacementSlotReaderPort,
)

_OPERATOR_ACCOUNT = UserId(value=uuid4())
_OPERATOR_TOKENS = {"operator-token"}
_UNAUTHORIZED_TOKENS = {"unauthorized-token"}

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


@pytest.fixture
def client(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_outbox: FakeOutbox,
) -> Iterator[TestClient]:
    def _campaign_use_cases() -> CampaignUseCases:
        return CampaignUseCases(
            campaigns=fake_campaigns,
            slots=fake_slots,
            creatives=fake_creatives,
            entitlements=fake_entitlement_projection,
            outbox=fake_outbox,
        )

    def _serving_use_cases() -> BannerServingUseCases:
        return BannerServingUseCases(
            campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
        )

    async def acting_operator_override(
        authorization: str | None = Header(default=None),
    ) -> ActingOperator:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        if token in _OPERATOR_TOKENS:
            return ActingOperator(account_id=_OPERATOR_ACCOUNT)
        if token in _UNAUTHORIZED_TOKENS:
            raise HTTPException(status_code=403, detail="caller lacks ads:campaign:manage")
        raise HTTPException(status_code=401, detail="no valid session")

    app = create_app()
    app.dependency_overrides[get_campaign_use_cases] = _campaign_use_cases
    app.dependency_overrides[get_serving_use_cases] = _serving_use_cases
    app.dependency_overrides[get_acting_operator] = acting_operator_override

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_request(slot_key: str = "HOMEPAGE_TOP", **overrides: object) -> dict[str, object]:
    # Anchored to real wall-clock time (not the fixed `_NOW`) -- the routers schedule/pause/resume
    # against `datetime.now(UTC)`, so a window fixed to a stale past-`_NOW` constant would
    # eventually be overtaken by real time and make `resume()` legitimately transition straight to
    # RUNNING instead of the SCHEDULED this suite expects.
    request_now = datetime.now(UTC)
    body: dict[str, object] = {
        "slotKey": slot_key,
        "creativeMediaAssetId": str(uuid4()),
        "entitlementId": str(uuid4()),
        "scheduleStart": (request_now + timedelta(days=1)).isoformat(),
        "scheduleEnd": (request_now + timedelta(days=8)).isoformat(),
        "priority": 0,
    }
    body.update(overrides)
    return body


class TestCreateCampaign:
    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post("/api/v1/admin/campaigns", json=_create_request())
        assert response.status_code == 401

    def test_rejects_an_unauthorized_operator(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/admin/campaigns", json=_create_request(), headers=_auth("unauthorized-token")
        )
        assert response.status_code == 403

    def test_creates_a_draft_campaign(
        self, client: TestClient, fake_slots: FakePlacementSlotReaderPort
    ) -> None:
        fake_slots.seed("HOMEPAGE_TOP")
        response = client.post(
            "/api/v1/admin/campaigns", json=_create_request(), headers=_auth("operator-token")
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "DRAFT"
        assert body["slotKey"] == "HOMEPAGE_TOP"

    def test_returns_404_style_not_found_for_an_unknown_slot(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/admin/campaigns",
            json=_create_request(slot_key="NO_SUCH_SLOT"),
            headers=_auth("operator-token"),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "RESOURCE_NOT_FOUND"


class TestGetAndListCampaigns:
    def test_get_unknown_campaign_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/admin/campaigns/{uuid4()}", headers=_auth("operator-token"))
        assert response.status_code == 404

    def test_list_campaigns_returns_a_page(
        self, client: TestClient, fake_slots: FakePlacementSlotReaderPort
    ) -> None:
        fake_slots.seed("HOMEPAGE_TOP")
        create_response = client.post(
            "/api/v1/admin/campaigns", json=_create_request(), headers=_auth("operator-token")
        )
        assert create_response.status_code == 201
        response = client.get("/api/v1/admin/campaigns", headers=_auth("operator-token"))
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert "page" in body


class TestScheduleLifecycle:
    def _create_and_schedule(
        self,
        client: TestClient,
        fake_slots: FakePlacementSlotReaderPort,
        fake_entitlement_projection: FakeEntitlementProjectionRepository,
    ) -> str:
        slot = fake_slots.seed("HOMEPAGE_TOP")
        entitlement_id = uuid4()

        async def _seed() -> None:
            await fake_entitlement_projection.upsert(
                EntitlementSnapshot(
                    entitlement_id=entitlement_id,
                    target_id=slot.head_id,
                    valid_from=_NOW - timedelta(days=1),
                    valid_until=_NOW + timedelta(days=30),
                    activation_state="ACTIVE",
                )
            )

        import asyncio

        asyncio.run(_seed())
        create_response = client.post(
            "/api/v1/admin/campaigns",
            json=_create_request(entitlementId=str(entitlement_id)),
            headers=_auth("operator-token"),
        )
        campaign_id = str(create_response.json()["id"])
        schedule_response = client.post(
            f"/api/v1/admin/campaigns/{campaign_id}/schedule", headers=_auth("operator-token")
        )
        assert schedule_response.status_code == 200
        assert schedule_response.json()["status"] == "SCHEDULED"
        return campaign_id

    def test_schedule_then_pause_then_resume_then_end(
        self,
        client: TestClient,
        fake_slots: FakePlacementSlotReaderPort,
        fake_entitlement_projection: FakeEntitlementProjectionRepository,
    ) -> None:
        campaign_id = self._create_and_schedule(client, fake_slots, fake_entitlement_projection)

        pause_response = client.post(
            f"/api/v1/admin/campaigns/{campaign_id}/pause", headers=_auth("operator-token")
        )
        assert pause_response.status_code == 200
        assert pause_response.json()["status"] == "PAUSED"

        resume_response = client.post(
            f"/api/v1/admin/campaigns/{campaign_id}/resume", headers=_auth("operator-token")
        )
        assert resume_response.status_code == 200
        assert resume_response.json()["status"] == "SCHEDULED"

        end_response = client.post(
            f"/api/v1/admin/campaigns/{campaign_id}/end", headers=_auth("operator-token")
        )
        assert end_response.status_code == 200
        assert end_response.json()["status"] == "ENDED"


class TestServeBanner:
    def test_serve_banner_needs_no_authentication(self, client: TestClient) -> None:
        response = client.get("/api/v1/banners/serve", params={"slotKey": "HOMEPAGE_TOP"})
        assert response.status_code in (200, 204)

    def test_serve_banner_returns_204_when_nothing_is_eligible(self, client: TestClient) -> None:
        response = client.get("/api/v1/banners/serve", params={"slotKey": "HOMEPAGE_TOP"})
        assert response.status_code == 204


class TestImpressionAndClickCapture:
    def test_record_impression_needs_no_authentication_and_returns_202(
        self,
        client: TestClient,
        fake_campaigns: FakeBannerCampaignRepository,
        fake_slots: FakePlacementSlotReaderPort,
    ) -> None:
        fake_slots.seed("HOMEPAGE_TOP")
        create_response = client.post(
            "/api/v1/admin/campaigns", json=_create_request(), headers=_auth("operator-token")
        )
        campaign_id = create_response.json()["id"]
        response = client.post(f"/api/v1/banners/{campaign_id}/impressions")
        assert response.status_code == 202

    def test_record_impression_returns_404_for_an_unknown_campaign(
        self, client: TestClient
    ) -> None:
        response = client.post(f"/api/v1/banners/{uuid4()}/impressions")
        assert response.status_code == 404

    def test_record_click_returns_404_for_an_unknown_campaign(self, client: TestClient) -> None:
        response = client.post(f"/api/v1/banners/{uuid4()}/clicks")
        assert response.status_code == 404
