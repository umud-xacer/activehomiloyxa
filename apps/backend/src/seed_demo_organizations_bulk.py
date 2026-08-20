"""One-off management script (Organizations Sub-Category detail-page task): tops every one of the
27 `SubCategory` leaves up to at least 2 demo organizations each, so `/organizations/$categorySlug/
$subCategorySlug` has real cards to render for design/QA instead of an empty state everywhere
except the 5 sub-categories `seed_demo_organization.py`'s flagship companies already cover.

Unlike `seed_demo_organization.py` (hand-curated real photography, 6 media assets/company, meant
as permanent showcase content), this script is deliberately lightweight test-seed data: each
company gets one procedurally generated logo (solid sector-accent tile with initials) and one
generated portfolio image (satisfies `BusinessProfile.complete_onboarding`'s `portfolio` and
`logoMediaAssetId` requirements, nothing more) -- no banner, no promo video, both optional. Same
real-HTTP-API-plus-direct-domain-calls pattern as `seed_demo_organization.py` for the two steps
with no public API path (registration approval, badge issuance); see that script's own docstring
for why.

Usage (same env-loading convention as `search_worker`/`bootstrap_admin`/`seed_demo_organization`):
    python -m seed_demo_organizations_bulk [base_url] [--per-subcategory N]
`base_url` defaults to http://127.0.0.1:8000/api/v1; `--per-subcategory` defaults to 2. Not
idempotent (a second run adds more companies, same as `seed_demo_organization.py`) -- only re-run
if genuinely more demo coverage is wanted.
"""

from __future__ import annotations

import asyncio
import io
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import requests
from PIL import Image, ImageDraw, ImageFont

import composition_root
from backbone.persistence import uuid7
from identity.domain import RegistrationReviewStatus
from identity.domain.value_objects import EmailAddress
from identity.infrastructure.persistence.repository import SqlalchemyUserAccountRepository
from media.infrastructure.object_storage import MinioStorageAdapter
from media.infrastructure.persistence.models import MediaAssetRow
from profiles.domain.value_objects import (
    SUB_CATEGORIES_BY_MAIN_CATEGORY,
    CaseStatus,
    MainCategory,
    SubCategory,
)
from profiles.domain.verification_case import ApprovedVerificationProof, VerificationCase
from profiles.infrastructure.persistence.repository import SqlalchemyBusinessProfileRepository
from shared_kernel import BusinessProfileId, UserId

# Same 6-sector accent palette as the frontend's `MAIN_CATEGORY_ACCENT` (business-profiles-client.ts)
# -- purely cosmetic, keeps generated logo tiles visually grouped by sector the same way the real
# site's cards/headers are.
_ACCENT_BY_MAIN_CATEGORY: dict[MainCategory, str] = {
    MainCategory.FINANCE_MORTGAGE: "#2563eb",
    MainCategory.CONSTRUCTION_CONTRACTORS: "#ea580c",
    MainCategory.MANUFACTURERS_MATERIALS: "#65a30d",
    MainCategory.ARCHITECTURE_INTERIOR: "#7c3aed",
    MainCategory.REPAIR_SERVICES: "#0891b2",
    MainCategory.REAL_ESTATE_AGENCIES: "#db2777",
}

_SUB_CATEGORY_LABEL: dict[SubCategory, str] = {
    SubCategory.COMMERCIAL_BANK: "Tijorat banki",
    SubCategory.MORTGAGE_CENTER: "Ipoteka markazi",
    SubCategory.MICROFINANCE: "Mikromoliya tashkiloti",
    SubCategory.INSURANCE: "Sug'urta kompaniyasi",
    SubCategory.LEASING: "Lizing kompaniyasi",
    SubCategory.GENERAL_CONTRACTOR: "Bosh pudratchi",
    SubCategory.SUBCONTRACTOR: "Sub-pudratchi",
    SubCategory.CIVIL_ENGINEERING: "Muhandislik-qurilish",
    SubCategory.RENOVATION_CONTRACTOR: "Ta'mirlash pudratchisi",
    SubCategory.INFRASTRUCTURE_CONSTRUCTION: "Infratuzilma qurilishi",
    SubCategory.BUILDING_MATERIALS_MANUFACTURER: "Qurilish materiallari ishlab chiqaruvchi",
    SubCategory.FURNITURE_MANUFACTURER: "Mebel ishlab chiqaruvchi",
    SubCategory.METAL_PRODUCTS_MANUFACTURER: "Metall mahsulotlari ishlab chiqaruvchi",
    SubCategory.CONCRETE_CEMENT_MANUFACTURER: "Beton va sement ishlab chiqaruvchi",
    SubCategory.GLASS_ALUMINUM_MANUFACTURER: "Shisha va alyuminiy konstruksiyalar",
    SubCategory.ARCHITECTURE_STUDIO: "Arxitektura studiyasi",
    SubCategory.INTERIOR_DESIGN_STUDIO: "Interyer dizayn studiyasi",
    SubCategory.LANDSCAPE_DESIGN_STUDIO: "Landshaft dizayni studiyasi",
    SubCategory.ENGINEERING_DESIGN_STUDIO: "Muhandislik loyihalash",
    SubCategory.HOME_REPAIR_SERVICE: "Uy ta'mirlash xizmati",
    SubCategory.PLUMBING_ELECTRICAL_SERVICE: "Santexnika va elektr xizmati",
    SubCategory.CLEANING_SERVICE: "Tozalash xizmati",
    SubCategory.APPLIANCE_REPAIR_SERVICE: "Maishiy texnika ta'mirlash",
    SubCategory.RESIDENTIAL_AGENCY: "Turar-joy agentligi",
    SubCategory.COMMERCIAL_AGENCY: "Tijorat ko'chmas mulki agentligi",
    SubCategory.PROPERTY_MANAGEMENT: "Mulkni boshqarish",
    SubCategory.VALUATION_SERVICE: "Baholash xizmati",
}

_PROFILE_TYPE_BY_MAIN_CATEGORY: dict[MainCategory, str] = {
    MainCategory.FINANCE_MORTGAGE: "SERVICE_PROVIDER",
    MainCategory.CONSTRUCTION_CONTRACTORS: "CONSTRUCTION_COMPANY",
    MainCategory.MANUFACTURERS_MATERIALS: "MANUFACTURER",
    MainCategory.ARCHITECTURE_INTERIOR: "ARCHITECT",
    MainCategory.REPAIR_SERVICES: "SERVICE_PROVIDER",
    MainCategory.REAL_ESTATE_AGENCIES: "SERVICE_PROVIDER",
}

_NAME_PREFIXES = [
    "Bunyod",
    "Ishonch",
    "Aktiv",
    "Vodiy",
    "Farovon",
    "Kelajak",
    "Mustaqil",
    "Oltin",
    "Baraka",
    "Nur",
    "Tong",
    "Yulduz",
    "Marvarid",
    "Zamin",
    "Andijon",
    "Samarqand",
    "Buxoro",
    "Chorvoq",
    "Sharq",
    "G'alaba",
]

_DISTRICTS = [
    ("Yunusobod tumani", "Amir Temur shoh ko'chasi"),
    ("Chilonzor tumani", "Bunyodkor shoh ko'chasi"),
    ("Mirzo Ulug'bek tumani", "Buyuk Ipak Yo'li ko'chasi"),
    ("Shayxontohur tumani", "Navoiy ko'chasi"),
    ("Yakkasaroy tumani", "Shota Rustaveli ko'chasi"),
    ("Sergeli tumani", "Qatortol ko'chasi"),
    ("Mirobod tumani", "Mustaqillik shoh ko'chasi"),
    ("Uchtepa tumani", "Bog'ishamol ko'chasi"),
]


@dataclass(frozen=True)
class BulkCompanyConfig:
    email_prefix: str
    company_name: str
    profile_type: str
    main_category: MainCategory
    sub_category: SubCategory
    description: str
    phone: str
    address: str
    accent: str


def _build_companies(per_subcategory: int) -> list[BulkCompanyConfig]:
    companies: list[BulkCompanyConfig] = []
    counter = 0
    for main_category, sub_categories in SUB_CATEGORIES_BY_MAIN_CATEGORY.items():
        for sub_category in sub_categories:
            sub_label = _SUB_CATEGORY_LABEL[sub_category]
            for slot in range(per_subcategory):
                prefix = _NAME_PREFIXES[counter % len(_NAME_PREFIXES)]
                district, street = _DISTRICTS[counter % len(_DISTRICTS)]
                name = f"{prefix} {sub_label} MChJ"
                companies.append(
                    BulkCompanyConfig(
                        email_prefix=f"bulk.{main_category.value.lower()}.{sub_category.value.lower()}.{slot}",
                        company_name=name,
                        profile_type=_PROFILE_TYPE_BY_MAIN_CATEGORY[main_category],
                        main_category=main_category,
                        sub_category=sub_category,
                        description=(
                            f"{name} — {sub_label.lower()} yo'nalishida faoliyat yurituvchi "
                            "hamkor tashkilot. Mijozlarga sifatli xizmat va professional "
                            "yondashuvni taqdim etadi."
                        ),
                        phone=f"+998{90500000 + counter:08d}",
                        address=f"Toshkent shahar, {district}, {street}, {10 + counter}-uy",
                        accent=_ACCENT_BY_MAIN_CATEGORY[main_category],
                    )
                )
                counter += 1
    return companies


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _initials(name: str) -> str:
    words = [w for w in name.split(" ") if w and w[0].isalpha()]
    return "".join(w[0].upper() for w in words[:2]) or "AH"


def _generate_logo_png(name: str, accent_hex: str) -> bytes:
    size = 512
    img = Image.new("RGB", (size, size), _hex_to_rgb(accent_hex))
    draw = ImageDraw.Draw(img)
    text = _initials(name)
    font = ImageFont.load_default(size=220)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        text,
        fill=(255, 255, 255),
        font=font,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _generate_portfolio_png(label: str, accent_hex: str) -> bytes:
    w, h = 1200, 800
    r, g, b = _hex_to_rgb(accent_hex)
    img = Image.new("RGB", (w, h), (r, g, b))
    # Simple two-tone diagonal-ish banding for visual texture, no external assets needed.
    overlay = Image.new("RGB", (w, h), (min(r + 25, 255), min(g + 25, 255), min(b + 25, 255)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(0, h), (w, 0), (w, h)], fill=140)
    img = Image.composite(overlay, img, mask)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=48)
    draw.text((40, h - 90), label, fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _upload_generated_png(data: bytes, *, uploaded_by: UUID) -> str:
    asset_id = uuid7()
    storage_key = f"media/{asset_id}/original.png"
    storage = MinioStorageAdapter()
    await storage.upload_object(storage_key=storage_key, data=data, content_type="image/png")

    async for session in composition_root._media_session():
        session.add(
            MediaAssetRow(
                id=asset_id,
                owner_context_type="PROFILE_PORTFOLIO",
                owner_context_id=None,
                storage_key=storage_key,
                content_type="image/png",
                size_bytes=len(data),
                scan_status="CLEAN",
                processing_status="COMPLETED",
                exif_stripped=True,
                uploaded_by=uploaded_by,
                duration_seconds=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    return str(asset_id)


async def _seed_company(base_url: str, config: BulkCompanyConfig, *, verify: bool) -> None:
    email = f"{config.email_prefix}+{int(time.time())}@activehome.test"
    password = f"DemoOrg-{secrets.token_urlsafe(12)}"

    session = requests.Session()
    resp = session.post(
        f"{base_url}/auth/register/email",
        json={
            "email": email,
            "password": password,
            "displayName": config.company_name,
            "accountKind": "LEGAL_ENTITY",
            "anketa": {"companyName": config.company_name},
        },
        timeout=30,
    )
    resp.raise_for_status()

    resp = session.post(
        f"{base_url}/auth/login/email", json={"email": email, "password": password}, timeout=30
    )
    resp.raise_for_status()
    account_id = resp.json()["account"]["id"]

    session_token = session.cookies.get("ah_session")
    if session_token:
        session.cookies.set("ah_session", session_token, secure=False)

    resp = session.post(
        f"{base_url}/business-profiles",
        json={
            "profileType": config.profile_type,
            "name": {"uz_latn": config.company_name},
            "description": {"uz_latn": config.description},
            "contacts": {"phones": [config.phone]},
            "address": config.address,
            "mainCategory": config.main_category.value,
            "subCategory": config.sub_category.value,
        },
        timeout=30,
    )
    resp.raise_for_status()
    profile = resp.json()
    profile_id = profile["id"]

    uploaded_by_uuid = UUID(account_id)
    logo_bytes = _generate_logo_png(config.company_name, config.accent)
    logo_id = await _upload_generated_png(logo_bytes, uploaded_by=uploaded_by_uuid)
    portfolio_bytes = _generate_portfolio_png(
        _SUB_CATEGORY_LABEL[config.sub_category], config.accent
    )
    portfolio_id = await _upload_generated_png(portfolio_bytes, uploaded_by=uploaded_by_uuid)

    resp = session.patch(
        f"{base_url}/business-profiles/{profile_id}/branding",
        json={"logoMediaAssetId": logo_id},
        timeout=30,
    )
    resp.raise_for_status()

    resp = session.post(
        f"{base_url}/business-profiles/{profile_id}/portfolio",
        json={"id": str(uuid4()), "mediaAssetId": portfolio_id, "position": 1},
        timeout=30,
    )
    resp.raise_for_status()

    resp = session.post(
        f"{base_url}/business-profiles/{profile_id}/complete-onboarding", json={}, timeout=30
    )
    resp.raise_for_status()

    found_account_id: list[UserId] = []
    async for id_session in composition_root._identity_session():
        account = await SqlalchemyUserAccountRepository(id_session).get_by_email(
            EmailAddress(value=email)
        )
        if account is None:
            raise RuntimeError(f"just-registered demo account {email!r} not found by email")
        found_account_id.append(account.id)
    async for use_cases in composition_root.provide_admin_identity_use_cases():
        await use_cases.decide_registration(
            target_account_id=found_account_id[0],
            reviewer_user_id=found_account_id[0],
            outcome=RegistrationReviewStatus.APPROVED,
            reason="Bulk demo seed: auto-approved for sub-category directory QA.",
            now=datetime.now(UTC),
        )

    if verify:
        async for pf_session in composition_root._profiles_session():
            repo = SqlalchemyBusinessProfileRepository(pf_session)
            biz_profile = await repo.get_by_id(BusinessProfileId(value=UUID(profile_id)))
            if biz_profile is None:
                raise RuntimeError(f"just-created demo business profile {profile_id!r} not found")
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
                reason="Bulk demo seed: auto-approved for sub-category directory QA.",
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

    print(f"  {config.company_name} ({config.sub_category.value}) -> profile {profile_id}")


async def main(base_url: str, per_subcategory: int) -> None:
    companies = _build_companies(per_subcategory)
    print(f"Seeding {len(companies)} demo organizations ({per_subcategory} per sub-category)...")
    for i, config in enumerate(companies):
        # Verify roughly 2 in 3 so the directory shows a realistic mix of verified/unverified cards.
        await _seed_company(base_url, config, verify=(i % 3 != 0))
    print("Done.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--per-subcategory")]
    per_arg = next((a for a in sys.argv[1:] if a.startswith("--per-subcategory")), None)
    per_value = int(per_arg.split("=")[1]) if per_arg and "=" in per_arg else 2
    url = args[0] if args else "http://127.0.0.1:8000/api/v1"
    asyncio.run(main(url, per_value))
