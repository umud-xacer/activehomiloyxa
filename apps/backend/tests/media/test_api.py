"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real MinIO/Postgres/identity-bridge providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production, no real datastore
needed. Covers all three Media operationIds and the contract's declared error paths (422 on
non-image/oversize, 403 on delete-by-non-owner, 404 on unknown id).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from main import create_app
from media.application.intake_use_cases import MediaIntakeUseCases
from media.interfaces.auth import ActingUser
from media.interfaces.di import get_acting_user, get_media_intake_use_cases
from shared_kernel import UserId

from .conftest import FakeMediaAssetRepository, FakeOutbox, FakeStorage

TEST_UPLOADER = UserId(value=uuid4())
TEST_OTHER_USER = UserId(value=uuid4())
_TOKEN_TO_USER = {"uploader-token": TEST_UPLOADER, "other-user-token": TEST_OTHER_USER}


@pytest.fixture
def client(
    fake_assets: FakeMediaAssetRepository, fake_storage: FakeStorage, fake_outbox: FakeOutbox
) -> Iterator[TestClient]:
    def _media_intake_use_cases() -> MediaIntakeUseCases:
        return MediaIntakeUseCases(
            assets=fake_assets, storage=fake_storage, outbox=fake_outbox, presign_expiry_seconds=900
        )

    async def acting_user_override(authorization: str | None = Header(default=None)) -> ActingUser:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        account_id = _TOKEN_TO_USER.get(token or "")
        if account_id is None:
            raise HTTPException(status_code=401, detail="no valid session")
        return ActingUser(account_id=account_id)

    app = create_app()
    app.dependency_overrides[get_media_intake_use_cases] = _media_intake_use_cases
    app.dependency_overrides[get_acting_user] = acting_user_override

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _auth_headers(token: str = "uploader-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_init_media_upload_returns_201_with_presigned_url(client: TestClient) -> None:
    response = client.post(
        "/api/v1/media/uploads",
        headers=_auth_headers(),
        json={"contentType": "image/jpeg", "sizeBytes": 2048, "ownerContextType": "LISTING"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["mediaAssetId"]
    assert body["method"] == "PUT"
    assert body["uploadUrl"]
    assert body["expiresAt"]


def test_init_media_upload_without_session_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/media/uploads",
        json={"contentType": "image/jpeg", "sizeBytes": 2048, "ownerContextType": "LISTING"},
    )
    assert response.status_code == 401


def test_init_media_upload_rejects_non_image_with_422(client: TestClient) -> None:
    """`MediaUploadInitRequest.contentType` is already a closed `Literal` in the frozen DTO
    (`interfaces/dto.py`), so a non-whitelisted value is rejected by Pydantic's own request-body
    validation before the request ever reaches `MediaAsset.initiate`'s `ImageOnlyPolicy` check --
    a structural 422 `VALIDATION_FAILED`, not the domain-level `UNSUPPORTED_MEDIA_TYPE` (that
    path is exercised directly at the domain/use-case layer in `test_media_asset.py`/
    `test_intake_use_cases.py`, for callers that could bypass the DTO). ADR-0008 widened the
    whitelist to admit `video/mp4`/`video/webm`, so `application/pdf` is the rejected example now."""
    response = client.post(
        "/api/v1/media/uploads",
        headers=_auth_headers(),
        json={"contentType": "application/pdf", "sizeBytes": 2048, "ownerContextType": "LISTING"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_init_media_upload_rejects_oversize_with_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/media/uploads",
        headers=_auth_headers(),
        json={
            "contentType": "image/jpeg",
            "sizeBytes": 10 * 1024 * 1024 + 1,
            "ownerContextType": "LISTING",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_get_media_returns_asset_metadata_not_yet_deliverable(client: TestClient) -> None:
    init_response = client.post(
        "/api/v1/media/uploads",
        headers=_auth_headers(),
        json={"contentType": "image/png", "sizeBytes": 1024, "ownerContextType": "LISTING"},
    )
    asset_id = init_response.json()["mediaAssetId"]

    response = client.get(f"/api/v1/media/{asset_id}", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == asset_id
    assert body["scanStatus"] == "PENDING"
    assert body["processingStatus"] == "PENDING"
    assert body["url"] is None
    assert body["variants"] is None


def test_get_media_unknown_id_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/media/{uuid4()}", headers=_auth_headers())
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_delete_media_by_owner_returns_204(client: TestClient) -> None:
    init_response = client.post(
        "/api/v1/media/uploads",
        headers=_auth_headers(),
        json={"contentType": "image/jpeg", "sizeBytes": 1024, "ownerContextType": "LISTING"},
    )
    asset_id = init_response.json()["mediaAssetId"]

    response = client.delete(f"/api/v1/media/{asset_id}", headers=_auth_headers("uploader-token"))
    assert response.status_code == 204

    follow_up = client.get(f"/api/v1/media/{asset_id}", headers=_auth_headers())
    assert follow_up.status_code == 404


def test_delete_media_by_non_owner_returns_403(client: TestClient) -> None:
    init_response = client.post(
        "/api/v1/media/uploads",
        headers=_auth_headers("uploader-token"),
        json={"contentType": "image/jpeg", "sizeBytes": 1024, "ownerContextType": "LISTING"},
    )
    asset_id = init_response.json()["mediaAssetId"]

    response = client.delete(f"/api/v1/media/{asset_id}", headers=_auth_headers("other-user-token"))
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
