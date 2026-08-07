"""Demo listing content seed (post-taxonomy content pass): populates a representative slice of
the category taxonomy (`configuration/infrastructure/seed.py`) with real, publicly-visible
listings, through the exact same `ListingUseCases`/`MediaIntakeUseCases`/`MediaProcessingUseCases`
real domain layer production traffic uses -- never a raw `INSERT` (same discipline as
`tests/performance/seed.py`, whose `_CategoryReaderBridge`/`_ConfigurationBridge` this module
copies verbatim).

Demo content: every listing's description is prefixed with `_DEMO_MARKER` ("Namuna e'lon") so it
reads honestly as placeholder content, not real inventory -- a swap point for real seller-
submitted listings once the marketplace has actual sellers (this session's own "demo-data-with-
swap-point" convention). Images are real, openly-licensed stock photography (Unsplash,
unsplash.com/license -- free for any use, no permission required), driven through the REAL media
intake pipeline (MinIO storage + ClamAV scan + Pillow EXIF-strip/variant generation) so they are
genuine `MediaAsset` rows a browser can actually load -- there is no sanctioned way to attach a
bare external URL to a `Listing` (X-06: "catalog holds `MediaAssetRef` only").

Idempotent: skips entirely once the demo seller account already owns >= `len(DEMO_LISTINGS)`
listings, so a redeploy does not re-download images or re-publish. Invoked by
`scripts/server-deploy.sh` right after the category seed.

Invocable directly: `python -m catalog.infrastructure.seed_demo_listings` (needs the same
POSTGRES_*/REDIS_*/MINIO_*/CLAMAV_*/MEDIA_CDN_BASE_URL environment as every other backbone
entrypoint, plus outbound HTTPS to images.unsplash.com).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from backbone.persistence import make_engine, make_session_factory, redis_url
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.listing_use_cases import ListingUseCases
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.configuration_adapter import (
    ConfigurationCategoryFormAdapter,
    ConfigurationPlatformSettingsAdapter,
)
from catalog.infrastructure.media_adapter import MediaAssetReaderAdapter
from catalog.infrastructure.persistence.models import ListingRow
from catalog.infrastructure.persistence.models import OutboxEventRow as CatalogOutboxEventRow
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from configuration.application.category_read import CategoryReadUseCases
from configuration.domain import ConfigEntityType
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.repository import SqlalchemyConfigHeadRepository
from configuration.interfaces.dto import ConfigurationHeadPage, ConfigurationVersion, PageInfo
from configuration.interfaces.routers import _head_to_dto, _version_to_dto
from identity.domain.user_account import UserAccount
from identity.domain.value_objects import PhoneNumber
from identity.infrastructure.persistence.repository import SqlalchemyUserAccountRepository
from media.application.intake_use_cases import MediaIntakeUseCases
from media.application.processing_use_cases import MediaProcessingUseCases
from media.domain.value_objects import OwnerContextType
from media.infrastructure.image_processing import PillowImageProcessingAdapter
from media.infrastructure.malware_scan import ClamAvMalwareScanAdapter
from media.infrastructure.object_storage import MinioStorageAdapter
from media.infrastructure.persistence.models import OutboxEventRow as MediaOutboxEventRow
from media.infrastructure.persistence.repository import SqlalchemyMediaAssetRepository
from media.interfaces.routers import _asset_to_dto
from shared_kernel import GeoLocation, MediaAssetId, Money, UserId

logger = logging.getLogger(__name__)

NOW = datetime.now(UTC)
DEMO_SELLER_PHONE = "+998901234567"
_DEMO_MARKER = "Namuna e'lon"

# Tashkent-ish bounding box (WGS-84), reused from tests/performance/seed.py for consistency.
_LAT_RANGE = (41.20, 41.40)
_LON_RANGE = (69.10, 69.40)

_UNSPLASH_BASE = "https://images.unsplash.com/photo-"


@dataclass(frozen=True)
class DemoListing:
    category_path: str
    listing_type: ListingType
    title: str
    description: str
    price_amount: int
    attributes: dict[str, object]
    image_id: str
    """Unsplash photo id (the `photo-<id>` segment) -- downloaded at seed time, never bundled."""


DEMO_LISTINGS: tuple[DemoListing, ...] = (
    # -- Qurilish materiallari (GOODS) ---------------------------------------------------------
    DemoListing(
        "/qurilish-materiallari", ListingType.PRODUCT,
        "Portlandcement M400, 50 kg qop",
        "Qurilish ob'ektlari uchun yuqori sifatli portlandcement, 50 kg qop.",
        45_000, {"brand": "Bekabodcement", "condition": "new", "delivery_available": "true"},
        "1541888946425-d81bb19240f5",
    ),
    DemoListing(
        "/qurilish-materiallari", ListingType.PRODUCT,
        "Metall cherepitsa, tom yopish uchun",
        "Zanglamaydigan qoplamali metall cherepitsa, kvadrat metriga hisoblanadi.",
        95_000, {"brand": "RuukkiStyle", "condition": "new", "delivery_available": "true"},
        "1587582423116-ec07293f0395",
    ),
    # -- Mebel materiallari (GOODS -- furniture form: material+condition required) -------------
    DemoListing(
        "/mebel-materiallari", ListingType.PRODUCT,
        "Divan uchun mebel matosi, metrga",
        "Yumshoq mebel ishlab chiqarish uchun zich to'quv mato, keng rang tanlovi.",
        38_000, {"material": "fabric", "condition": "new", "brand": "TurkTekstil"},
        "1567016432779-094069958ea5",
    ),
    DemoListing(
        "/mebel-materiallari", ListingType.PRODUCT,
        "Eman yog'och taxta, mebel uchun",
        "Quritilgan eman taxta, shkaf va stol ishlab chiqarish uchun mos.",
        220_000, {"material": "wood", "condition": "new", "brand": "AgroYogoch"},
        "1595428774223-ef52624120d2",
    ),
    # -- Maishiy texnikalar (GOODS) -------------------------------------------------------------
    DemoListing(
        "/maishiy-texnikalar", ListingType.PRODUCT,
        "Samsung muzlatgich, 350 litr, Side-by-Side",
        "Ikki eshikli, No Frost tizimli zamonaviy muzlatgich, kafolat bilan.",
        8_900_000, {"brand": "Samsung", "condition": "new", "warranty_months": "24", "delivery_available": "true"},
        "1484154218962-a197022b5858",
    ),
    DemoListing(
        "/maishiy-texnikalar", ListingType.PRODUCT,
        "Bosch mikroto'lqinli pech, 25L",
        "Grill funksiyali, raqamli boshqaruvli mikroto'lqinli pech.",
        1_650_000, {"brand": "Bosch", "condition": "new", "warranty_months": "12", "delivery_available": "true"},
        "1556910103-1c02745aae4d",
    ),
    # -- Uy bezaklari (GOODS) --------------------------------------------------------------------
    DemoListing(
        "/uy-bezaklari", ListingType.PRODUCT,
        "Devor soati, yog'och ramkali",
        "Minimalistik dizayndagi yog'och devor soati, jim mexanizm.",
        185_000, {"brand": "NordicHome", "condition": "new", "delivery_available": "true"},
        "1533090161767-e6ffed986c88",
    ),
    DemoListing(
        "/uy-bezaklari", ListingType.PRODUCT,
        "Dekorativ yostiq va gilamcha to'plami",
        "Mehmonxona uchun uyg'un dekorativ yostiq va kichik gilamcha to'plami.",
        320_000, {"brand": "HomeStyle", "condition": "new", "delivery_available": "true"},
        "1616486338812-3dadae4b4ace",
    ),
    # -- Uniforma va maxsus kiyimlar (GOODS) -----------------------------------------------------
    DemoListing(
        "/uniforma-va-maxsus-kiyimlar", ListingType.PRODUCT,
        "Payvandchi uchun himoya kostyumi",
        "Olovbardosh mato, to'liq himoya to'plami (kostyum + niqob + qo'lqop).",
        780_000, {"brand": "SafeWork", "condition": "new", "delivery_available": "true"},
        "1504328345606-18bbc8c9d7d1",
    ),
    DemoListing(
        "/uniforma-va-maxsus-kiyimlar", ListingType.PRODUCT,
        "Qurilish ishchisi formasi (kombinezon)",
        "Chidamli matodan tikilgan kombinezon, ko'p cho'ntakli, barcha o'lchamlarda.",
        265_000, {"brand": "ProWear", "condition": "new", "delivery_available": "true"},
        "1441986300917-64674bd600d8",
    ),
    # -- Mebel salonlari (GOODS/business directory) ----------------------------------------------
    DemoListing(
        "/mebel-salonlari", ListingType.ADVERTISEMENT,
        "Zamonaviy mehmonxona to'plami (divan + kreslo)",
        "Salon namunasi: 3+1+1 divan-kreslo to'plami, buyurtma asosida rang tanlash mumkin.",
        12_500_000, {"address": "Toshkent, Chilonzor", "work_hours": "09:00-19:00", "brands": "ItalDesign"},
        "1560448204-e02f11c3d0e2",
    ),
    DemoListing(
        "/mebel-salonlari", ListingType.ADVERTISEMENT,
        "Sariq kreslo va yorug'lik to'plami",
        "Salon namunasi: aksent kreslo + floor lampa, kichik xonalar uchun ideal.",
        3_400_000, {"address": "Toshkent, Yunusobod", "work_hours": "09:00-19:00", "brands": "ComfortLine"},
        "1586023492125-27b2c045efd7",
    ),
    # -- Dam olish maskanlari (VENUE) -------------------------------------------------------------
    DemoListing(
        "/dam-olish-maskanlari", ListingType.ADVERTISEMENT,
        "Hovuzli dam olish majmuasi",
        "Ochiq basseyn, yashil hudud va dam olish zonalariga ega premium maskan.",
        450_000, {"venue_type": "pool", "capacity": "80", "price_unit": "per_person", "open_hours": "08:00-22:00"},
        "1520250497591-112f2f40a3f4",
    ),
    DemoListing(
        "/dam-olish-maskanlari", ListingType.ADVERTISEMENT,
        "To'yxona va bazm zali",
        "Zamonaviy interyerli, 300 kishilik to'yxona, to'liq banket xizmati bilan.",
        25_000_000, {"venue_type": "event_hall", "capacity": "300", "price_unit": "fixed", "open_hours": "10:00-24:00"},
        "1519167758481-83f550bb49b3",
    ),
    # -- Hostel (VENUE) -----------------------------------------------------------------------------
    DemoListing(
        "/hostel", ListingType.ADVERTISEMENT,
        "Talabalar uchun byudjet xona",
        "Universitetga yaqin, umumiy oshxonali, arzon narxdagi hostel xonasi.",
        90_000, {"room_capacity": "4", "amenities": ["wifi"], "price_unit": "per_night"},
        "1595526114035-0d45ed16cfbf",
    ),
    DemoListing(
        "/hostel", ListingType.ADVERTISEMENT,
        "Premium xususiy xona (Private Room)",
        "Shaxsiy hammomli, konditsionerli qulay xona, shahar markazida.",
        220_000, {"room_capacity": "2", "amenities": ["wifi", "ac", "breakfast"], "price_unit": "per_night"},
        "1571508601891-ca5e7a713859",
    ),
    # -- Mexmonxona (VENUE) --------------------------------------------------------------------------
    DemoListing(
        "/mexmonxona", ListingType.ADVERTISEMENT,
        "5 yulduzli kurort mehmonxonasi",
        "Basseyn, SPA va restoranga ega premium kurort mehmonxonasi.",
        1_800_000, {"room_capacity": "2", "amenities": ["wifi", "breakfast", "parking", "ac"], "price_unit": "per_night"},
        "1520250497591-112f2f40a3f4",
    ),
    DemoListing(
        "/mexmonxona", ListingType.ADVERTISEMENT,
        "Business Hotel, markaziy hududda",
        "Konferensiya zali va biznes xizmatlariga ega qulay mehmonxona.",
        950_000, {"room_capacity": "2", "amenities": ["wifi", "breakfast", "parking"], "price_unit": "per_night"},
        "1416331108676-a22ccb276e35",
    ),
    # -- Landshaft dizayni (SERVICE) ---------------------------------------------------------------
    DemoListing(
        "/landshaft-dizayni", ListingType.SERVICE,
        "Bog' loyihalash va obodonlashtirish xizmati",
        "Hovli va bog' hududlarini professional loyihalash, ekish va yoritish ishlari.",
        350_000, {"experience_years": "7", "specialization": "Bog' loyihalash", "rate_type": "per_job", "available_now": "true"},
        "1416879595882-3373a0480b5b",
    ),
    DemoListing(
        "/landshaft-dizayni", ListingType.SERVICE,
        "Avtomatik sug'orish tizimini o'rnatish",
        "Hovli va bog'lar uchun avtomatik tomchilatib sug'orish tizimini loyihalash va o'rnatish.",
        280_000, {"experience_years": "5", "specialization": "Sug'orish tizimlari", "rate_type": "per_job", "available_now": "true"},
        "1466692476868-aef1dfb1e735",
    ),
    # -- Ko'p qavatli binolar (PROPERTY) -----------------------------------------------------------
    DemoListing(
        "/kop-qavatli-binolar", ListingType.ADVERTISEMENT,
        "3 xonali zamonaviy kvartira",
        "Yangi uy-joy majmuasida, mukammal rejalashtirilgan 3 xonali kvartira.",
        620_000_000, {"rooms": "3", "area_sqm": "82", "floor": "7", "total_floors": "16", "condition": "new", "deal_type": "sale"},
        "1518005020951-eccb494ad742",
    ),
    DemoListing(
        "/kop-qavatli-binolar", ListingType.ADVERTISEMENT,
        "Yangi qurilish, 1 xonali studiya",
        "Shahar markaziga yaqin, yangi binoda ixcham studiya-kvartira.",
        280_000_000, {"rooms": "1", "area_sqm": "38", "floor": "4", "total_floors": "12", "condition": "new", "deal_type": "sale"},
        "1522708323590-d24dbb6b0267",
    ),
    # -- Bo'sh yerlar (LAND) -------------------------------------------------------------------------
    DemoListing(
        "/bosh-yerlar", ListingType.ADVERTISEMENT,
        "Qishloq xo'jaligi uchun 20 sotix yer",
        "Sug'orish suvi mavjud, dehqonchilik uchun qulay tekislik yer.",
        140_000_000, {"area_sotix": "20", "land_purpose": "agriculture", "has_documents": "true"},
        "1500382017468-9049fed747ef",
    ),
    DemoListing(
        "/bosh-yerlar", ListingType.ADVERTISEMENT,
        "Qurilish uchun 6 sotix yer",
        "Kommunikatsiyalarga yaqin, uy qurish uchun tayyor yer uchastkasi.",
        320_000_000, {"area_sotix": "6", "land_purpose": "construction", "has_documents": "true"},
        "1466692476868-aef1dfb1e735",
    ),
    # -- Noturar binolar (PROPERTY) -------------------------------------------------------------------
    DemoListing(
        "/noturar-binolar", ListingType.ADVERTISEMENT,
        "Biznes-markazda ofis xonasi",
        "Zamonaviy biznes-markazda, resepshn va avtoturargohli ofis maydoni.",
        45_000_000, {"rooms": "1", "area_sqm": "60", "floor": "5", "total_floors": "9", "condition": "new", "deal_type": "rent"},
        "1487958449943-2429e8be8625",
    ),
    DemoListing(
        "/noturar-binolar", ListingType.ADVERTISEMENT,
        "Savdo maydoni ijaraga",
        "Yo'l bo'yida joylashgan, katta vitrinali savdo/do'kon maydoni.",
        38_000_000, {"rooms": "1", "area_sqm": "95", "floor": "1", "total_floors": "1", "condition": "good", "deal_type": "rent"},
        "1497366216548-37526070297c",
    ),
    # -- Hovlilar (PROPERTY) ----------------------------------------------------------------------------
    DemoListing(
        "/hovlilar", ListingType.ADVERTISEMENT,
        "Zamonaviy hovli, katta bog' bilan",
        "Keng yer maydoniga ega, zamonaviy arxitekturadagi shinam hovli.",
        1_450_000_000, {"rooms": "5", "area_sqm": "240", "condition": "new", "deal_type": "sale"},
        "1600585154340-be6161a56a0c",
    ),
    DemoListing(
        "/hovlilar", ListingType.ADVERTISEMENT,
        "Shinam oilaviy uy, ayvon bilan",
        "Oilaviy turmush uchun qulay, keng ayvonli ikki qavatli hovli.",
        780_000_000, {"rooms": "4", "area_sqm": "160", "condition": "good", "deal_type": "sale"},
        "1560184897-ae75f418493e",
    ),
    # -- Kotejlar (PROPERTY) -----------------------------------------------------------------------------
    DemoListing(
        "/kotejlar", ListingType.ADVERTISEMENT,
        "Tabiat qo'ynidagi kotedj",
        "Shahar shovqinidan uzoq, tabiat qo'ynida joylashgan dam olish kotteji.",
        980_000_000, {"rooms": "4", "area_sqm": "180", "condition": "new", "deal_type": "sale"},
        "1449844908441-8829872d2607",
    ),
    DemoListing(
        "/kotejlar", ListingType.ADVERTISEMENT,
        "Basseynli premium villa",
        "Xususiy basseyn va keng terrassaga ega hashamatli villa-kotedj.",
        2_100_000_000, {"rooms": "6", "area_sqm": "320", "condition": "new", "deal_type": "sale"},
        "1512917774080-9991f1c4c750",
    ),
    # -- Dala hovlilar (PROPERTY) -------------------------------------------------------------------------
    DemoListing(
        "/dala-hovlilar", ListingType.ADVERTISEMENT,
        "Dam olish uchun dala hovlisi (kunlik ijara)",
        "Hafta oxiri dam olish uchun barbekyu zonali qulay dala hovlisi.",
        550_000, {"rooms": "3", "area_sqm": "120", "condition": "good", "deal_type": "rent"},
        "1560448204-e02f11c3d0e2",
    ),
    DemoListing(
        "/dala-hovlilar", ListingType.ADVERTISEMENT,
        "Ko'l bo'yidagi dala hovlisi",
        "Ko'l manzarali, tinch va sokin hududda joylashgan dam olish uyi.",
        1_100_000_000, {"rooms": "3", "area_sqm": "110", "condition": "good", "deal_type": "sale"},
        "1416331108676-a22ccb276e35",
    ),
    # -- Ish o'rni (SERVICE -- CV shape, employer requirement) ---------------------------------------------
    DemoListing(
        "/ish-orni", ListingType.SERVICE,
        "Frontend dasturchi qidirilmoqda",
        "React/TypeScript tajribasiga ega frontend dasturchi lavozimiga tanlov e'lon qilinadi.",
        8_000_000, {"experience_years": "2", "specialization": "Frontend (React)", "rate_type": "per_job", "available_now": "true"},
        "1581094794329-c8112a89af12",
    ),
    DemoListing(
        "/ish-orni", ListingType.SERVICE,
        "Arxitektor / loyihachi",
        "Qurilish kompaniyasiga tajribali arxitektor-loyihachi talab qilinadi.",
        10_000_000, {"experience_years": "4", "specialization": "Arxitektura", "rate_type": "per_job", "available_now": "true"},
        "1503387762-592deb58ef4e",
    ),
    # -- Xizmat ko'rsatish (SERVICE -- CV shape) -------------------------------------------------------------
    DemoListing(
        "/xizmat-korsatish", ListingType.SERVICE,
        "Malakali ta'mirchi xizmatlari",
        "Kvartira va ofislarda kosmetik hamda kapital ta'mirlash ishlari.",
        400_000, {"experience_years": "8", "specialization": "Kvartira ta'miri", "rate_type": "daily", "available_now": "true"},
        "1558618666-fcd25c85cd64",
    ),
    DemoListing(
        "/xizmat-korsatish", ListingType.SERVICE,
        "Payvandchi xizmati",
        "Metall konstruksiyalar va darvoza payvandlash bo'yicha professional xizmat.",
        250_000, {"experience_years": "6", "specialization": "Payvandchilik", "rate_type": "per_job", "available_now": "true"},
        "1504328345606-18bbc8c9d7d1",
    ),
)


def _default_for_field(field: dict[str, object]) -> object:
    """A safe, generic value for a required field DEMO_LISTINGS didn't anticipate -- a category's
    bound form can be edited (or entirely replaced) via the owner-admin panel at any time after
    this script was written, independent of `configuration/infrastructure/seed.py`'s own field
    shapes; a required field this script has no opinion about must still get *something*, not
    fail the whole listing."""
    field_type = field.get("field_type")
    options = field.get("options") or []
    if field_type == "boolean":
        return "false"
    if field_type == "number":
        return "1"
    if field_type in ("select", "multiselect") and options:
        first = options[0]
        value = first.get("value") if isinstance(first, dict) else first
        return [value] if field_type == "multiselect" else value
    return "-"


def _resolve_attributes(
    form_fields: list[dict[str, object]], intended: dict[str, object]
) -> dict[str, object]:
    """Builds the final attribute set from the category's ACTUAL currently-bound form (never
    DEMO_LISTINGS's own guess in isolation): keeps `intended` values only for fields the form
    still declares, and fills any other required field with `_default_for_field`. Silently drops
    `intended` keys the form no longer has -- `validate_attribute_set` rejects unknown keys
    outright (`catalog/domain/policies.py`: "not a field of the bound form")."""
    resolved: dict[str, object] = {}
    for field in form_fields:
        code = str(field.get("code"))
        if code in intended:
            resolved[code] = intended[code]
        elif field.get("required"):
            resolved[code] = _default_for_field(field)
    return resolved


def _demo_lat_lon(index: int) -> tuple[float, float]:
    lat = _LAT_RANGE[0] + (index % 97) / 97 * (_LAT_RANGE[1] - _LAT_RANGE[0])
    lon = _LON_RANGE[0] + (index % 89) / 89 * (_LON_RANGE[1] - _LON_RANGE[0])
    return lat, lon


class _ConfigurationBridge:
    """Reproduces `composition_root._ConfigurationPortBridge`'s two methods -- copied verbatim
    from `tests/performance/seed.py::_ConfigurationBridge`, the proven-working precedent for
    calling `ListingUseCases` from a standalone script."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
    ) -> None:
        self._session_factory = session_factory
        self._redis_client = redis_client

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage:
        page_limit = limit or 20
        async with self._session_factory() as session:
            repo = SqlalchemyConfigHeadRepository(session)
            cache = RedisSnapshotCache(self._redis_client)
            uc = CategoryReadUseCases(repo, cache)
            # CategoryReadUseCases has no list_heads; use the repo directly (mirrors
            # ConfigurationUseCases.list_heads, which ListingUseCases's bridge never needs beyond
            # this narrow slice -- category/form lookups go through get_category/get_category_form).
            del uc
            heads, next_cursor = await repo.list_heads(
                ConfigEntityType(entity_type), cursor=cursor, limit=page_limit
            )
            return ConfigurationHeadPage(
                items=[_head_to_dto(h) for h in heads],
                page=PageInfo(limit=page_limit, next_cursor=next_cursor),
            )

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        async with self._session_factory() as session:
            repo = SqlalchemyConfigHeadRepository(session)
            version = await repo.get_version(ConfigEntityType(entity_type), head_id, version_id)
            return _version_to_dto(version)


class _CategoryReaderBridge:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
    ) -> None:
        self._session_factory = session_factory
        self._redis_client = redis_client

    async def get_category(self, category_id: UUID) -> dict[str, object] | None:
        async with self._session_factory() as session:
            uc = CategoryReadUseCases(
                SqlalchemyConfigHeadRepository(session), RedisSnapshotCache(self._redis_client)
            )
            return await uc.get_category(category_id)

    async def get_category_form(self, category_id: UUID) -> dict[str, object] | None:
        async with self._session_factory() as session:
            uc = CategoryReadUseCases(
                SqlalchemyConfigHeadRepository(session), RedisSnapshotCache(self._redis_client)
            )
            return await uc.get_category_form(category_id)


class _MediaReaderBridge:
    """Adapts `MediaIntakeUseCases.get_media` to the narrow `catalog.infrastructure.media_adapter.
    _MediaReader` shape, mirroring `composition_root._CatalogMediaReaderBridge` exactly (down to
    reusing the same private `_asset_to_dto` helper) so a seeded image resolves through the IDENTICAL
    code path a real listing's image does -- no shortcut DTO of this script's own invention."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], storage: MinioStorageAdapter
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    async def get_media(self, media_id: UUID) -> object:
        async with self._session_factory() as session:
            use_cases = MediaIntakeUseCases(
                assets=SqlalchemyMediaAssetRepository(session),
                storage=self._storage,
                outbox=OutboxWriter(session, MediaOutboxEventRow),
                presign_expiry_seconds=900,
            )
            asset = await use_cases.get_media(MediaAssetId(value=media_id))
            return _asset_to_dto(asset)


async def _category_path_to_id(redis_client: Redis) -> dict[str, UUID]:
    cache = RedisSnapshotCache(redis_client)
    snapshots = await cache.list_current(ConfigEntityType.CATEGORY)
    return {
        str(s["path"]): UUID(str(s["id"]))
        for s in snapshots
        if s.get("tree_status") != "RETIRED" and s.get("path")
    }


async def _download_image(client: httpx.AsyncClient, photo_id: str) -> bytes:
    response = await client.get(
        f"{_UNSPLASH_BASE}{photo_id}", params={"w": "1200", "q": "80", "fm": "jpg"}
    )
    response.raise_for_status()
    return response.content


async def _upload_demo_image(
    session_factory: async_sessionmaker[AsyncSession],
    storage: MinioStorageAdapter,
    scanner: ClamAvMalwareScanAdapter,
    processor: PillowImageProcessingAdapter,
    *,
    image_bytes: bytes,
    uploaded_by: UserId,
) -> UUID:
    """Drives one image through the REAL intake pipeline end to end (PENDING -> CLEAN ->
    COMPLETED), reusing the exact same use-case classes `media/infrastructure/worker.py`'s
    production poll loop calls -- only the trigger (called once, inline, instead of polled) differs."""
    async with session_factory() as session:
        intake = MediaIntakeUseCases(
            assets=SqlalchemyMediaAssetRepository(session),
            storage=storage,
            outbox=OutboxWriter(session, MediaOutboxEventRow),
            presign_expiry_seconds=900,
        )
        asset, _presigned = await intake.init_media_upload(
            content_type="image/jpeg",
            size_bytes=len(image_bytes),
            owner_context_type=OwnerContextType.LISTING.value,
            uploaded_by=uploaded_by,
            now=NOW,
        )
        await session.commit()

    await storage.upload_object(
        storage_key=asset.storage_key, data=image_bytes, content_type="image/jpeg"
    )

    async with session_factory() as session:
        processing = MediaProcessingUseCases(
            assets=SqlalchemyMediaAssetRepository(session),
            storage=storage,
            scanner=scanner,
            processor=processor,
            outbox=OutboxWriter(session, MediaOutboxEventRow),
        )
        await processing.run_scan_batch(now=NOW)
        await processing.run_processing_batch(now=NOW)
        await session.commit()

    return asset.id.value


async def _ensure_demo_seller(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    async with session_factory() as session:
        repo = SqlalchemyUserAccountRepository(session)
        existing = await repo.get_by_phone(PhoneNumber(DEMO_SELLER_PHONE))
        if existing is not None:
            return existing.id.value
        account = UserAccount.register_via_phone(
            account_id=UserId(value=uuid4()), phone=PhoneNumber(DEMO_SELLER_PHONE), now=NOW
        )
        await repo.add(account)
        await session.commit()
        return account.id.value


def _build_listing_use_cases(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    storage: MinioStorageAdapter,
) -> ListingUseCases:
    listings_repo = SqlalchemyListingRepository(session)
    return ListingUseCases(
        listings=listings_repo,
        categories=ConfigurationCategoryFormAdapter(
            _CategoryReaderBridge(session_factory, redis_client)
        ),
        settings=ConfigurationPlatformSettingsAdapter(
            _ConfigurationBridge(session_factory, redis_client)
        ),
        media=MediaAssetReaderAdapter(_MediaReaderBridge(session_factory, storage)),
        outbox=OutboxWriter(session, CatalogOutboxEventRow),
        quota=QuotaEnforcementService(
            subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
        ),
        duplicates=DuplicateDetectionService(listings=listings_repo),
    )


async def _existing_demo_listing_count(
    session_factory: async_sessionmaker[AsyncSession], owner_id: UUID
) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(ListingRow)
            .where(ListingRow.owner_user_id == owner_id)
        )
        return int(result.scalar_one())


async def seed_demo_listings() -> None:
    engine = make_engine()
    session_factory = make_session_factory(engine)
    redis_client = Redis.from_url(redis_url())
    storage = MinioStorageAdapter()
    scanner = ClamAvMalwareScanAdapter()
    processor = PillowImageProcessingAdapter()

    try:
        owner_id = await _ensure_demo_seller(session_factory)

        existing_count = await _existing_demo_listing_count(session_factory, owner_id)
        if existing_count >= len(DEMO_LISTINGS):
            logger.info(
                "seed_demo_listings: demo seller already owns %d listings (>= %d expected), skipping",
                existing_count,
                len(DEMO_LISTINGS),
            )
            return

        path_to_id = await _category_path_to_id(redis_client)
        category_reader = _CategoryReaderBridge(session_factory, redis_client)

        # Downloads each distinct image once and reuses the resulting media_asset_id across every
        # DEMO_LISTINGS entry that references the same Unsplash photo id.
        media_asset_by_image: dict[str, UUID] = {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            for photo_id in {d.image_id for d in DEMO_LISTINGS}:
                image_bytes = await _download_image(client, photo_id)
                media_asset_by_image[photo_id] = await _upload_demo_image(
                    session_factory,
                    storage,
                    scanner,
                    processor,
                    image_bytes=image_bytes,
                    uploaded_by=UserId(value=owner_id),
                )

        for index, demo in enumerate(DEMO_LISTINGS):
            if index < existing_count:
                continue
            category_id = path_to_id.get(demo.category_path)
            if category_id is None:
                logger.warning(
                    "seed_demo_listings: category path %r not found, skipping %r",
                    demo.category_path,
                    demo.title,
                )
                continue
            lat, lon = _demo_lat_lon(index)
            media_asset_id = media_asset_by_image[demo.image_id]

            form_snapshot = await category_reader.get_category_form(category_id)
            form_fields = list(form_snapshot.get("fields", [])) if form_snapshot else []
            attributes = _resolve_attributes(form_fields, demo.attributes)

            async with session_factory() as session:
                use_cases = _build_listing_use_cases(
                    session, session_factory, redis_client, storage
                )
                listing = await use_cases.create_listing(
                    owner_user_id=UserId(value=owner_id),
                    owner_profile_id=None,
                    listing_type=demo.listing_type,
                    category_id=category_id,
                    title=demo.title,
                    description=f"{_DEMO_MARKER}. {demo.description}",
                    attributes=attributes,
                    price=Money(amount=Decimal(demo.price_amount), currency="UZS"),
                    location=GeoLocation(latitude=lat, longitude=lon),
                    image_media_asset_ids=[media_asset_id],
                    publish=False,
                    now=NOW,
                )
                await session.commit()
                listing_id = listing.id

            async with session_factory() as session:
                use_cases = _build_listing_use_cases(
                    session, session_factory, redis_client, storage
                )
                await use_cases.publish_listing(
                    listing_id=listing_id, actor_user_id=UserId(value=owner_id), now=NOW
                )
                await session.commit()

        logger.info("seed_demo_listings: seeded %d demo listings", len(DEMO_LISTINGS))
    finally:
        await redis_client.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_demo_listings())


if __name__ == "__main__":
    main()
