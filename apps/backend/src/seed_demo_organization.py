"""One-off management script (Organizations Main-Category task, BOSQICH 3): creates one fully
filled-in demo LEGAL_ENTITY business profile -- "Vista Arxitektura Byurosi" -- under the
Arxitektura va Interyer dizayn main category, with a real logo, HD banner, description, phone,
address, 4 portfolio photos, and a real (parseable, <=30s) promo video. Ends with the profile
onboarded, its owner account's registration approved, and a VALID verified badge issued, so it
shows up correctly everywhere a real approved organization would: the homepage top-5 widget, the
`/companies` directory (including its new category tab), and its own `/companies/$slug` portfolio
page.

Account registration/login/profile-CRUD go through the real HTTP API (same path the frontend
wizard uses) via `requests` -- the two steps with no public API path (admin registration
approval, badge issuance without a paid verification entitlement) go through the backend's own
composition-root-wired use cases / domain methods directly, the same precedent `bootstrap_admin.py`
and `retire_subcategories.py` already established for this class of one-off operator script.

Media assets are uploaded directly to the configured MinIO/S3 bucket (`MinioStorageAdapter.
upload_object`, no presigned-URL round trip needed since this script runs server-side with the
same credentials the app itself uses) and their `media_asset` rows are inserted already
CLEAN/COMPLETED -- mirroring what the async malware-scan/processing workers would eventually
produce for a real upload, skipped here since this is trusted, script-generated demo content, not
guest input.

Usage (same env-loading convention as `search_worker`/`bootstrap_admin`/`retire_subcategories`):
    python -m seed_demo_organization [base_url]
`base_url` defaults to http://127.0.0.1:8000/api/v1 (local dev); pass the real one
(https://activehome.uz/api/v1) to seed production. Not idempotent by design (a second run creates
a second demo account with a fresh email) -- re-running is a deliberate choice, not a bug.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import requests

import composition_root
from backbone.persistence import uuid7
from identity.domain import RegistrationReviewStatus
from identity.domain.value_objects import EmailAddress
from identity.infrastructure.persistence.repository import SqlalchemyUserAccountRepository
from media.infrastructure.object_storage import MinioStorageAdapter
from media.infrastructure.persistence.models import MediaAssetRow
from media.infrastructure.video_probe import probe_duration_seconds
from profiles.domain.value_objects import CaseStatus
from profiles.domain.verification_case import ApprovedVerificationProof, VerificationCase
from profiles.infrastructure.persistence.repository import SqlalchemyBusinessProfileRepository
from shared_kernel import BusinessProfileId, UserId

ASSETS_DIR = Path(
    os.environ.get(
        "SEED_ASSETS_DIR",
        "C:/Users/user/AppData/Local/Temp/claude/C--Users-user-Desktop-Active-home-full-2-fixed/"
        "e1ad73bf-9b47-41ba-9310-5bb9c6b9e254/scratchpad",
    )
)
"""Local dev default matches the dev machine's own scratchpad; production/other hosts must set
`SEED_ASSETS_DIR` to wherever the 7 source files (logo.png, portfolio1..4.jpg, exterior.jpg,
promo_video.mp4) were copied to on that host."""

EMAIL = f"vista.arxitektura+{int(time.time())}@activehome.test"
PASSWORD = f"DemoOrg-{secrets.token_urlsafe(12)}"
"""Generated per run, not a fixed literal -- a throwaway demo account still shouldn't have a
guessable/repeated password, and a hardcoded string here would (correctly) trip bandit's
B105 hardcoded-password check regardless of the account being non-sensitive."""
COMPANY_NAME = "Vista Arxitektura Byurosi"
DESCRIPTION = (
    "Zamonaviy arxitektura va shahar rejalashtirish loyihalari — funksionallik va estetikani "
    "uyg'unlashtiramiz. 2018-yildan buyon Toshkent va viloyatlarda turar-joy hamda tijorat "
    "obyektlari uchun to'liq loyihalash xizmatlarini taqdim etamiz."
)
PHONE = "+998901234567"
ADDRESS = "Toshkent shahar, Mirzo Ulug'bek tumani, Amir Temur shoh ko'chasi, 41-uy"


def _content_type_for(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".mp4": "video/mp4",
    }[path.suffix.lower()]


async def _upload_media(path: Path, *, uploaded_by: UUID) -> str:
    """Uploads one file straight to the bucket and inserts its already-CLEAN/COMPLETED
    `media_asset` row; returns the new asset's id as a string."""
    data = path.read_bytes()  # noqa: ASYNC240 -- one-off script, no concurrent event-loop tasks
    content_type = _content_type_for(path)
    asset_id = uuid7()
    storage_key = f"media/{asset_id}/original{path.suffix.lower()}"

    storage = MinioStorageAdapter()
    await storage.upload_object(storage_key=storage_key, data=data, content_type=content_type)

    duration = probe_duration_seconds(data, content_type) if content_type == "video/mp4" else None

    async for session in composition_root._media_session():
        session.add(
            MediaAssetRow(
                id=asset_id,
                owner_context_type="PROFILE_PORTFOLIO",
                owner_context_id=None,
                storage_key=storage_key,
                content_type=content_type,
                size_bytes=len(data),
                scan_status="CLEAN",
                processing_status="COMPLETED",
                exif_stripped=True,
                uploaded_by=uploaded_by,
                duration_seconds=duration,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    print(
        f"  uploaded {path.name} -> {asset_id} ({content_type}, {len(data)} bytes"
        + (f", {duration:.1f}s)" if duration else ")")
    )
    return str(asset_id)


async def main(base_url: str) -> None:
    print(f"1) Registering {EMAIL} as LEGAL_ENTITY via {base_url} ...")
    session = requests.Session()
    resp = session.post(
        f"{base_url}/auth/register/email",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "displayName": COMPANY_NAME,
            "accountKind": "LEGAL_ENTITY",
            "anketa": {"companyName": COMPANY_NAME},
        },
        timeout=30,
    )
    resp.raise_for_status()

    print("2) Logging in ...")
    resp = session.post(
        f"{base_url}/auth/login/email",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    account_id = resp.json()["account"]["id"]
    print(f"   account id: {account_id}")

    # The login response's `Set-Cookie` carries the `Secure` attribute (correct -- the real site
    # is always HTTPS); `requests`' cookie jar honours that and silently drops the cookie again on
    # the next request when `base_url` is plain http:// (local dev only, e.g. 127.0.0.1). Re-set
    # it without that attribute so local runs authenticate the same way production ones do -- a
    # no-op against a real https:// base_url, where the cookie already carries correctly.
    session_token = session.cookies.get("ah_session")
    if session_token:
        session.cookies.set("ah_session", session_token, secure=False)

    print("3) Creating business profile ...")
    resp = session.post(
        f"{base_url}/business-profiles",
        json={
            "profileType": "ARCHITECT",
            "name": {"uz_latn": COMPANY_NAME},
            "description": {"uz_latn": DESCRIPTION},
            "contacts": {"phones": [PHONE]},
            "address": ADDRESS,
            "mainCategory": "ARCHITECTURE_INTERIOR",
        },
        timeout=30,
    )
    resp.raise_for_status()
    profile = resp.json()
    profile_id = profile["id"]
    print(f"   profile id: {profile_id}, slug: {profile['slug']}")

    print("4) Uploading media assets ...")
    uploaded_by_uuid = UUID(account_id)
    logo_id = await _upload_media(ASSETS_DIR / "logo.png", uploaded_by=uploaded_by_uuid)
    banner_id = await _upload_media(ASSETS_DIR / "portfolio1.jpg", uploaded_by=uploaded_by_uuid)
    portfolio_ids = [
        await _upload_media(ASSETS_DIR / name, uploaded_by=uploaded_by_uuid)
        for name in ("portfolio2.jpg", "portfolio3.jpg", "portfolio4.jpg", "exterior.jpg")
    ]
    promo_video_id = await _upload_media(
        ASSETS_DIR / "promo_video.mp4", uploaded_by=uploaded_by_uuid
    )

    print("5) Setting branding (logo + banner) ...")
    resp = session.patch(
        f"{base_url}/business-profiles/{profile_id}/branding",
        json={"logoMediaAssetId": logo_id, "bannerMediaAssetId": banner_id},
        timeout=30,
    )
    resp.raise_for_status()

    print("6) Adding portfolio items ...")
    for pid in portfolio_ids:
        resp = session.post(
            f"{base_url}/business-profiles/{profile_id}/portfolio",
            json={"id": str(uuid4()), "mediaAssetId": pid, "position": 1},
            timeout=30,
        )
        resp.raise_for_status()

    print("7) Adding promo video ...")
    resp = session.post(
        f"{base_url}/business-profiles/{profile_id}/promo-videos",
        json={"mediaAssetId": promo_video_id},
        timeout=30,
    )
    resp.raise_for_status()

    print("8) Completing onboarding (starts the trial + makes it publicly listable) ...")
    resp = session.post(
        f"{base_url}/business-profiles/{profile_id}/complete-onboarding", json={}, timeout=30
    )
    resp.raise_for_status()

    print("9) Approving the account's registration (identity review queue) ...")
    found_account_id: list[UserId] = []
    async for id_session in composition_root._identity_session():
        account = await SqlalchemyUserAccountRepository(id_session).get_by_email(
            EmailAddress(value=EMAIL)
        )
        assert account is not None
        found_account_id.append(account.id)
    async for use_cases in composition_root.provide_admin_identity_use_cases():
        await use_cases.decide_registration(
            target_account_id=found_account_id[0],
            reviewer_user_id=found_account_id[0],
            outcome=RegistrationReviewStatus.APPROVED,
            reason="Demo seed: auto-approved for verification walkthrough.",
            now=datetime.now(UTC),
        )

    print(
        "10) Issuing a VALID verified badge (approved-case proof, no paid entitlement needed) ..."
    )
    async for pf_session in composition_root._profiles_session():
        repo = SqlalchemyBusinessProfileRepository(pf_session)
        biz_profile = await repo.get_by_id(BusinessProfileId(value=UUID(profile_id)))
        assert biz_profile is not None
        # `VerificationCase.create`'s factory requires >=1 document; a demo badge doesn't need a
        # real submitted document row, so this constructs the frozen dataclass directly (bypassing
        # only that factory-level guard, not `ApprovedVerificationProof`'s own I-13 structural
        # one below) rather than fabricating a throwaway document.
        case = VerificationCase(
            id=uuid4(),
            business_profile_id=biz_profile.id,
            entitlement_id=uuid4(),
            status=CaseStatus.REQUESTED,
            sla_due_at=datetime.now(UTC),
            documents=(),
            decision=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        approved_case = case.decide(
            outcome=CaseStatus.APPROVED,
            reason="Demo seed: auto-approved for verification walkthrough.",
            reviewer_user_id=uploaded_by_uuid,
            now=datetime.now(UTC),
        )
        proof = ApprovedVerificationProof.from_case(approved_case)
        badged = biz_profile.issue_badge(
            proof=proof,
            valid_until=datetime.now(UTC).replace(year=datetime.now(UTC).year + 1),
            now=datetime.now(UTC),
        )
        await repo.save(badged)

    print()
    print("Done. Demo organization is live:")
    print(f"  Login:   {EMAIL} / {PASSWORD}")
    print(f"  Profile: {profile_id} (slug: {profile['slug']})")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1"
    asyncio.run(main(url))
