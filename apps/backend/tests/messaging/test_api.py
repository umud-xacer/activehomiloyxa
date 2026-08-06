"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/identity providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers all ten
messaging-tagged operations, the participant/ownership 401/403 scenarios (I-19 at the API layer),
the PII discipline (a phone number never appears in a refused reveal's response), and the
stateless-HTTP-tier inspection (`main.py`'s own app mounts no WebSocket route at all). Mirrors
`apps/backend/tests/billing/test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from main import create_app
from messaging.application.block_use_cases import BlockUseCases
from messaging.application.conversation_use_cases import ConversationUseCases
from messaging.application.report_use_cases import ReportUseCases
from messaging.interfaces.auth import ActingUser
from messaging.interfaces.di import (
    get_acting_user,
    get_block_use_cases,
    get_conversation_use_cases,
    get_report_use_cases,
)
from shared_kernel import UserId

from .conftest import (
    FakeBlockRepository,
    FakeContactPolicyPort,
    FakeConversationRepository,
    FakeListingOwnerReaderPort,
    FakeOutbox,
    FakeRealtimePublisherPort,
)

_INITIATOR = UserId(value=uuid4())
_OWNER = UserId(value=uuid4())
_THIRD_PARTY = UserId(value=uuid4())

_TOKEN_TO_USER = {
    "initiator-token": _INITIATOR,
    "owner-token": _OWNER,
    "third-party-token": _THIRD_PARTY,
}


@pytest.fixture
def client(
    fake_conversations: FakeConversationRepository,
    fake_blocks: FakeBlockRepository,
    fake_listing_owners: FakeListingOwnerReaderPort,
    fake_publisher: FakeRealtimePublisherPort,
    fake_contact_policy: FakeContactPolicyPort,
    fake_outbox: FakeOutbox,
) -> Iterator[TestClient]:
    def _conversation_use_cases() -> ConversationUseCases:
        return ConversationUseCases(
            conversations=fake_conversations,
            blocks=fake_blocks,
            listing_owners=fake_listing_owners,
            publisher=fake_publisher,
            contact_policy=fake_contact_policy,
            outbox=fake_outbox,
        )

    def _block_use_cases() -> BlockUseCases:
        return BlockUseCases(blocks=fake_blocks, outbox=fake_outbox)

    def _report_use_cases() -> ReportUseCases:
        return ReportUseCases(outbox=fake_outbox)

    async def acting_user_override(authorization: str | None = Header(default=None)) -> ActingUser:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        account_id = _TOKEN_TO_USER.get(token or "")
        if account_id is None:
            raise HTTPException(status_code=401, detail="no valid session")
        return ActingUser(account_id=account_id)

    app = create_app()
    app.dependency_overrides[get_conversation_use_cases] = _conversation_use_cases
    app.dependency_overrides[get_block_use_cases] = _block_use_cases
    app.dependency_overrides[get_report_use_cases] = _report_use_cases
    app.dependency_overrides[get_acting_user] = acting_user_override
    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_conversation(
    client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
) -> dict[str, object]:
    listing_id = uuid4()
    fake_listing_owners.seed(listing_id, _OWNER)
    resp = client.post(
        "/api/v1/conversations",
        json={"listingId": str(listing_id), "message": "hello"},
        headers=_auth("initiator-token"),
    )
    assert resp.status_code == 201, resp.text
    result: dict[str, object] = resp.json()
    return result


class TestStartConversation:
    def test_returns_201_with_the_resolved_recipient(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        conversation = _seed_conversation(client, fake_listing_owners)
        assert conversation["recipientUserId"] == str(_OWNER.value)
        assert conversation["initiatorUserId"] == str(_INITIATOR.value)
        assert conversation["status"] == "ACTIVE"

    def test_unauthenticated_caller_gets_401(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/conversations", json={"listingId": str(uuid4()), "message": "hi"}
        )
        assert resp.status_code == 401

    def test_unknown_listing_owner_returns_503(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/conversations",
            json={"listingId": str(uuid4()), "message": "hi"},
            headers=_auth("initiator-token"),
        )
        assert resp.status_code == 503


class TestGetConversationAndMessages:
    def test_I19_third_party_gets_403(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        conversation = _seed_conversation(client, fake_listing_owners)
        resp = client.get(
            f"/api/v1/conversations/{conversation['id']}", headers=_auth("third-party-token")
        )
        assert resp.status_code == 403

    def test_participant_can_read(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        conversation = _seed_conversation(client, fake_listing_owners)
        resp = client.get(
            f"/api/v1/conversations/{conversation['id']}", headers=_auth("owner-token")
        )
        assert resp.status_code == 200

    def test_list_messages_returns_the_initial_message(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        conversation = _seed_conversation(client, fake_listing_owners)
        resp = client.get(
            f"/api/v1/conversations/{conversation['id']}/messages", headers=_auth("owner-token")
        )
        assert resp.status_code == 200
        assert resp.json()["items"][0]["body"] == "hello"


class TestSendMessage:
    def test_recipient_can_reply(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        conversation = _seed_conversation(client, fake_listing_owners)
        resp = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"body": "reply"},
            headers=_auth("owner-token"),
        )
        assert resp.status_code == 201

    def test_I19_third_party_gets_403(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        conversation = _seed_conversation(client, fake_listing_owners)
        resp = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"body": "intruder"},
            headers=_auth("third-party-token"),
        )
        assert resp.status_code == 403


class TestRevealPhone:
    def test_returns_allowed_true_and_the_number_when_permitted(
        self,
        client: TestClient,
        fake_listing_owners: FakeListingOwnerReaderPort,
        fake_contact_policy: FakeContactPolicyPort,
    ) -> None:
        fake_contact_policy.seed(_OWNER.value, "+998901234567")
        conversation = _seed_conversation(client, fake_listing_owners)
        resp = client.post(
            f"/api/v1/conversations/{conversation['id']}/phone-reveal",
            headers=_auth("initiator-token"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is True
        assert body["phoneNumber"] == "+998901234567"

    def test_PII_refused_reveal_never_exposes_a_phone_number(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        """`fake_contact_policy` was never seeded a phone for `_OWNER` -- the response must show
        `allowed: false` and `phoneNumber: null`, never a value (Security Sec 3.1 PII rule: not
        exposed in any API response unless the reveal gate passes)."""
        conversation = _seed_conversation(client, fake_listing_owners)
        resp = client.post(
            f"/api/v1/conversations/{conversation['id']}/phone-reveal",
            headers=_auth("initiator-token"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is False
        assert body["phoneNumber"] is None
        assert "998" not in resp.text
        assert "+" not in resp.text


class TestBlocks:
    def test_block_list_unblock_round_trip(self, client: TestClient) -> None:
        blocked = uuid4()
        create = client.post(
            "/api/v1/me/blocks",
            json={"blockedUserId": str(blocked)},
            headers=_auth("initiator-token"),
        )
        assert create.status_code == 201
        assert create.json()["blockedUserId"] == str(blocked)

        listed = client.get("/api/v1/me/blocks", headers=_auth("initiator-token"))
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        deleted = client.delete(f"/api/v1/me/blocks/{blocked}", headers=_auth("initiator-token"))
        assert deleted.status_code == 204

        listed_again = client.get("/api/v1/me/blocks", headers=_auth("initiator-token"))
        assert listed_again.json() == []

    def test_duplicate_block_returns_409(self, client: TestClient) -> None:
        blocked = uuid4()
        client.post(
            "/api/v1/me/blocks",
            json={"blockedUserId": str(blocked)},
            headers=_auth("initiator-token"),
        )
        resp = client.post(
            "/api/v1/me/blocks",
            json={"blockedUserId": str(blocked)},
            headers=_auth("initiator-token"),
        )
        assert resp.status_code == 409

    def test_I19_a_blocked_user_cannot_message_the_blocker(
        self, client: TestClient, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        listing_id = uuid4()
        fake_listing_owners.seed(listing_id, _OWNER)
        client.post(
            "/api/v1/me/blocks",
            json={"blockedUserId": str(_INITIATOR.value)},
            headers=_auth("owner-token"),
        )
        resp = client.post(
            "/api/v1/conversations",
            json={"listingId": str(listing_id), "message": "hello"},
            headers=_auth("initiator-token"),
        )
        assert resp.status_code == 403


class TestCreateReport:
    def test_returns_202(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/reports",
            json={"subjectType": "USER", "subjectId": str(uuid4()), "reason": "spam"},
            headers=_auth("initiator-token"),
        )
        assert resp.status_code == 202


def _all_mounted_paths(app: object) -> list[str | None]:
    """This FastAPI version wraps `include_router()` calls in `_IncludedRouter` objects rather
    than flattening routes into `app.router.routes` directly (confirmed in P-09) -- the real
    path list lives on each wrapper's own `.original_router.routes`."""
    routes = getattr(getattr(app, "router"), "routes")  # noqa: B009
    return [
        getattr(sub, "path", None)
        for r in routes
        if type(r).__name__ == "_IncludedRouter"
        for sub in getattr(r, "original_router").routes  # noqa: B009
    ]


class TestStatelessHttpTier:
    def test_the_http_tier_app_mounts_no_websocket_route(self) -> None:
        """DEC-11/Validation Checklist: "the HTTP API tier holds no connection state and remains
        horizontally scalable" -- verified here by inspection: `main.py`'s own app never includes
        `messaging.interfaces.ws.realtime_router`, only `messaging_router` (REST-only)."""
        assert "/ws/messaging" not in _all_mounted_paths(create_app())

    def test_the_realtime_app_does_mount_the_websocket_route(self) -> None:
        """The flip side of the test above -- proves the inspection technique actually
        distinguishes presence from absence, not just trivially passing either way."""
        import realtime_main

        assert "/ws/messaging" in _all_mounted_paths(realtime_main.create_realtime_app())

    def test_the_realtime_app_mounts_no_rest_business_routes(self) -> None:
        """DEC-11: the realtime gateway is a separate stateful tier holding ONLY the WS
        connection surface -- no `messaging_router` (or any other module's router) shares this
        process, so business logic is never duplicated between the two runtimes."""
        import realtime_main

        assert _all_mounted_paths(realtime_main.create_realtime_app()) == ["/ws/messaging"]
