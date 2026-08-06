"""Seed data (Task P-04 deliverable): the two bootstrap `RoleDefinition`s that reference the
permission-key catalogue, and default `PlatformSettings`. Run once against a fresh database
(idempotent -- skips any head whose code already exists).

Scope note: this seeds the *role definitions* (Config Framework Sec 2.1 "Roles ... Super
Administrator" is a configuration concern, owned by BC-04); it does not create a `UserAccount`
or assign a role to one -- that is identity's (BC-01) own bootstrap concern in its own task, not
yet implemented (Task P-04 excludes implementing other modules). "Super-Admin bootstrap path"
within this module's scope means: the `super-admin` role exists, Published, and ready for
identity to assign once it exists.

Also seeds one demo catalog category, "Mebel materiallari" (Furniture) at `/mebel-materiallari`,
plus its bound `FormDefinition` -- local/dev-only demo content (not a Task P-04 deliverable) so
that the frontend's `/furniture` route and the homepage `CategoryCarousel`'s furniture icon
(both of which already hardcode this exact path) resolve to real data instead of an empty
category list on a freshly seeded database. Follows the same maker/checker publish flow as
`_seed_role`/`_seed_platform_settings` above -- see `_seed_furniture_form`/
`_seed_furniture_category`.

Invocable directly: `python -m configuration.infrastructure.seed` (needs the same
POSTGRES_*/REDIS_* environment as every other backbone entrypoint).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from backbone.outbox import OutboxWriter
from backbone.persistence import make_engine, make_session_factory, redis_url, session_scope
from configuration.application import ConfigurationUseCases
from configuration.application.exceptions import GateFailedError
from configuration.domain import (
    SUPER_ADMIN_APPROVAL_ENTITIES,
    ConfigEntityType,
    DuplicateCodeError,
)
from configuration.domain.whitelist import PERMISSION_KEYS, WhitelistRegistry
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import SqlalchemyConfigHeadRepository

SEED_MAKER_ID = UUID("00000000-0000-0000-0000-000000000001")
"""Fixed system-actor id for the seed script's authoring step -- distinct from
`SEED_CHECKER_ID` so the maker-checker "different principal" rule (Config Framework Sec 2.3)
is satisfied even for bootstrap data, not bypassed for it."""
SEED_CHECKER_ID = UUID("00000000-0000-0000-0000-000000000002")

_registry = WhitelistRegistry()


def _administrator_permission_keys() -> list[str]:
    """Every catalogue key except the two Super-Admin-only approve keys (Config Framework
    Sec 2.3: "role and settings changes require Super-Administrator approval")."""
    super_admin_only = {
        _registry.approve_permission_key(entity_type.value)
        for entity_type in SUPER_ADMIN_APPROVAL_ENTITIES
    }
    return sorted(PERMISSION_KEYS - super_admin_only)


def _super_admin_permission_keys() -> list[str]:
    """The full catalogue (SRS Sec 4: "All Administrator rights plus role/permission management
    and platform settings")."""
    return sorted(PERMISSION_KEYS)


async def _seed_role(
    use_cases: ConfigurationUseCases,
    *,
    code: str,
    role_name: str,
    permission_keys: list[str],
    now: datetime,
) -> None:
    try:
        _head, version = await use_cases.create_draft(
            ConfigEntityType.ROLE_DEFINITION,
            code=code,
            business_owner="Super Administrator",
            definition={
                "descriptor": {"name": {"uz_latn": role_name}},
                "role_name": role_name,
                "permission_keys": permission_keys,
            },
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        return

    head = await use_cases.get_head(ConfigEntityType.ROLE_DEFINITION, version.head_id)
    # Bootstrap authority, not the *candidate* role's own grant -- defining the "administrator"
    # role does not itself carry role-definition:approve, but the operator running this seed
    # script (standing in for the platform bootstrap process) acts with full catalogue
    # authority regardless of which role is being authored.
    bootstrap_authority = frozenset(_super_admin_permission_keys())
    step1 = await use_cases.publish(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=bootstrap_authority,
        approval_note="seed: bootstrap role",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.ROLE_DEFINITION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=bootstrap_authority,
            approval_note="seed: bootstrap approval",
            now=now,
        )


async def _seed_platform_settings(use_cases: ConfigurationUseCases, *, now: datetime) -> None:
    definition = {
        "descriptor": {"name": {"uz_latn": "Default platform settings"}},
        "settings_scope": "GLOBAL",
        "settings": {
            "listing.default_expiry_days": 30,
            "feature_flag.banners_enabled": True,
            "feature_flag.messaging_enabled": True,
            "otp.expiry_minutes": 5,
            "session.expiry_hours": 720,
            "search.default_page_size": 20,
        },
        "homepage_zones": [],
        "navigation_items": [],
        "seo_templates": [],
        "static_pages": [],
    }
    try:
        _head, version = await use_cases.create_draft(
            ConfigEntityType.PLATFORM_SETTINGS,
            code="platform-settings-global",
            business_owner="Super Administrator",
            definition=definition,
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        return

    approve_key = _registry.approve_permission_key(ConfigEntityType.PLATFORM_SETTINGS.value)
    manage_key = _registry.manage_permission_key(ConfigEntityType.PLATFORM_SETTINGS.value)
    step1 = await use_cases.publish(
        ConfigEntityType.PLATFORM_SETTINGS,
        version.head_id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: bootstrap settings",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.PLATFORM_SETTINGS,
            version.head_id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({approve_key}),
            approval_note="seed: bootstrap settings approval",
            now=now,
        )


async def _seed_furniture_form(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    now: datetime,
) -> UUID:
    """Demo `FormDefinition` for the furniture ("Mebel materiallari") category -- gives the
    frontend's `/furniture` page (`catalog-client.ts` `listingsByCategoryPath("/mebel-materiallari")`)
    a real attribute form to bind to in local/dev environments, the same way `housing-form` does
    for the tests' `_publish_form_and_category` fixture. Idempotent -- returns the existing head's
    id (looked up by code) if this has already run against this database."""
    code = "mebel-materiallari-form"
    definition = {
        "descriptor": {"name": {"uz_latn": "Mebel mahsuloti"}},
        "sections": [
            {"code": "asosiy", "label": {"uz_latn": "Asosiy ma'lumotlar"}, "order": 1},
        ],
        "fields": [
            {
                "code": "brand",
                "section_code": "asosiy",
                "label": {"uz_latn": "Brend"},
                "field_type": "text",
                "required": False,
                "facet_eligible": True,
                "order": 1,
            },
            {
                "code": "material",
                "section_code": "asosiy",
                "label": {"uz_latn": "Material"},
                "field_type": "select",
                "required": True,
                "facet_eligible": True,
                "order": 2,
                "options": [
                    {"value": "wood", "label": {"uz_latn": "Yog'och"}},
                    {"value": "metal", "label": {"uz_latn": "Metall"}},
                    {"value": "fabric", "label": {"uz_latn": "Gazlama"}},
                    {"value": "plastic", "label": {"uz_latn": "Plastik"}},
                    {"value": "other", "label": {"uz_latn": "Boshqa"}},
                ],
            },
            {
                "code": "condition",
                "section_code": "asosiy",
                "label": {"uz_latn": "Holati"},
                "field_type": "select",
                "required": True,
                "facet_eligible": True,
                "order": 3,
                "options": [
                    {"value": "new", "label": {"uz_latn": "Yangi"}},
                    {"value": "used", "label": {"uz_latn": "Ishlatilgan"}},
                ],
            },
            {
                "code": "color",
                "section_code": "asosiy",
                "label": {"uz_latn": "Rang"},
                "field_type": "text",
                "required": False,
                "facet_eligible": False,
                "order": 4,
            },
            {
                "code": "warranty_months",
                "section_code": "asosiy",
                "label": {"uz_latn": "Kafolat (oy)"},
                "field_type": "number",
                "required": False,
                "facet_eligible": False,
                "order": 5,
            },
            {
                "code": "delivery_available",
                "section_code": "asosiy",
                "label": {"uz_latn": "Yetkazib berish mavjud"},
                "field_type": "boolean",
                "required": False,
                "facet_eligible": True,
                "order": 6,
                "default_value": False,
            },
        ],
    }
    try:
        head, version = await use_cases.create_draft(
            ConfigEntityType.FORM_DEFINITION,
            code=code,
            business_owner="Catalog Owner",
            definition=definition,
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        existing = await repo.get_head_by_code(ConfigEntityType.FORM_DEFINITION, code)
        assert existing is not None, f"seed marker {code!r} vanished between check and lookup"
        return existing.id

    manage_key = _registry.manage_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    step1 = await use_cases.publish(
        ConfigEntityType.FORM_DEFINITION,
        head.id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: bootstrap furniture form",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.FORM_DEFINITION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: bootstrap furniture form approval",
            now=now,
        )
    return head.id


async def _seed_furniture_category(
    use_cases: ConfigurationUseCases,
    *,
    form_definition_id: UUID,
    now: datetime,
) -> None:
    """The "Mebel materiallari" (Furniture) top-level category, bound to the form above -- the
    exact path the frontend already hardcodes (`CategoryCarousel.tsx`'s `ICON_BY_PATH["/mebel-
    materiallari"]` and the `/furniture` route's `CATEGORY_PATH`), so both the homepage category
    rail and the dedicated furniture page resolve to real data once this has run."""
    code = "mebel-materiallari"
    definition = {
        "descriptor": {
            "name": {"uz_latn": "Mebel materiallari", "ru": "Мебель", "en": "Furniture"},
        },
        "parent_category_id": None,
        "path": "/mebel-materiallari",
        "form_definition_id": str(form_definition_id),
        "tree_status": "ACTIVE",
    }
    try:
        head, version = await use_cases.create_draft(
            ConfigEntityType.CATEGORY,
            code=code,
            business_owner="Catalog Owner",
            definition=definition,
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        return

    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY,
        head.id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: bootstrap furniture category",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: bootstrap furniture category approval",
            now=now,
        )


def _field(
    code: str,
    section_code: str,
    label: str,
    field_type: str,
    *,
    required: bool = False,
    facet: bool = False,
    order: int = 0,
    options: list[tuple[str, str]] | None = None,
    default: object = None,
) -> dict[str, object]:
    """Terse `FormFieldContent`-dict builder (`content.py`) for the taxonomy below -- every
    category's form is built from these, so the boilerplate (label/field_type/required/...) only
    needs writing once per helper call, not once per key."""
    field: dict[str, object] = {
        "code": code,
        "section_code": section_code,
        "label": {"uz_latn": label},
        "field_type": field_type,
        "required": required,
        "facet_eligible": facet,
        "order": order,
    }
    if options:
        field["options"] = [{"value": v, "label": {"uz_latn": lbl}} for v, lbl in options]
    if default is not None:
        field["default_value"] = default
    return field


def _property_fields() -> list[dict[str, object]]:
    """Ko'p qavatli binolar / kotejlar / hovlilar / noturar binolar / dala hovlilar -- the
    residential/commercial-building direction."""
    return [
        _field("rooms", "asosiy", "Xonalar soni", "number", facet=True, order=1),
        _field("area_sqm", "asosiy", "Maydon (m2)", "number", facet=True, order=2),
        _field("floor", "asosiy", "Qavat", "number", order=3),
        _field("total_floors", "asosiy", "Binodagi qavatlar soni", "number", order=4),
        _field(
            "condition",
            "asosiy",
            "Holati",
            "select",
            facet=True,
            order=5,
            options=[
                ("new", "Yangi ta'mirlangan"),
                ("good", "O'rtacha holatda"),
                ("needs_repair", "Ta'mir talab"),
            ],
        ),
        _field(
            "deal_type",
            "asosiy",
            "Bitim turi",
            "select",
            required=True,
            facet=True,
            order=6,
            options=[("sale", "Sotish"), ("rent", "Ijaraga berish")],
        ),
    ]


def _land_fields() -> list[dict[str, object]]:
    return [
        _field("area_sotix", "asosiy", "Maydon (sotix)", "number", required=True, facet=True, order=1),
        _field(
            "land_purpose",
            "asosiy",
            "Yer maqsadi",
            "select",
            facet=True,
            order=2,
            options=[
                ("construction", "Qurilish uchun"),
                ("agriculture", "Qishloq xo'jaligi"),
                ("commercial", "Tijorat"),
            ],
        ),
        _field("has_documents", "asosiy", "Hujjatlari bor", "boolean", facet=True, order=3, default=False),
    ]


def _goods_fields() -> list[dict[str, object]]:
    """Qurilish materiallari / maishiy texnikalar / uy bezaklari / uniforma -- anything sold as
    a physical unit, same shape as the furniture ("Mebel materiallari") form seeded above."""
    return [
        _field("brand", "asosiy", "Brend", "text", facet=True, order=1),
        _field(
            "condition",
            "asosiy",
            "Holati",
            "select",
            required=True,
            facet=True,
            order=2,
            options=[("new", "Yangi"), ("used", "Ishlatilgan")],
        ),
        _field("warranty_months", "asosiy", "Kafolat (oy)", "number", order=3),
        _field("delivery_available", "asosiy", "Yetkazib berish mavjud", "boolean", facet=True, order=4, default=False),
    ]


def _hospitality_fields() -> list[dict[str, object]]:
    return [
        _field("room_capacity", "asosiy", "Xona sig'imi (kishi)", "number", facet=True, order=1),
        _field(
            "amenities",
            "asosiy",
            "Qulayliklar",
            "multiselect",
            facet=True,
            order=2,
            options=[
                ("wifi", "Wi-Fi"),
                ("breakfast", "Nonushta"),
                ("parking", "Avtoturargoh"),
                ("ac", "Konditsioner"),
            ],
        ),
        _field(
            "price_unit",
            "asosiy",
            "Narx birligi",
            "select",
            order=3,
            options=[("per_night", "Kechasiga"), ("per_person", "Kishi boshiga")],
        ),
    ]


def _business_fields() -> list[dict[str, object]]:
    """Mebel salonlari -- a business-directory listing (a showroom/company), not a single unit
    for sale."""
    return [
        _field("address", "asosiy", "Manzil", "text", order=1),
        _field("work_hours", "asosiy", "Ish vaqti", "text", order=2),
        _field("brands", "asosiy", "Brendlar", "text", order=3),
    ]


def _venue_fields() -> list[dict[str, object]]:
    """Dam olish maskanlari -- restaurants/parks/sports venues/event halls."""
    return [
        _field(
            "venue_type",
            "asosiy",
            "Maskan turi",
            "select",
            required=True,
            facet=True,
            order=1,
            options=[
                ("restaurant", "Restoran/kafe"),
                ("park", "Bog'/tabiat"),
                ("sport", "Sport maydoni"),
                ("pool", "Basseyn"),
                ("event_hall", "To'yxona/zal"),
                ("other", "Boshqa"),
            ],
        ),
        _field("capacity", "asosiy", "Sig'imi (kishi)", "number", facet=True, order=2),
        _field(
            "price_unit",
            "asosiy",
            "Narx birligi",
            "select",
            order=3,
            options=[
                ("per_person", "Kishi boshiga"),
                ("per_hour", "Soatiga"),
                ("per_day", "Kuniga"),
                ("fixed", "Belgilangan"),
            ],
        ),
        _field("open_hours", "asosiy", "Ish vaqti", "text", order=4),
    ]


def _service_cv_fields(*, extra: list[dict[str, object]] | None = None) -> list[dict[str, object]]:
    """The "CV" shape: a `SERVICE`-typed listing under `xizmat-korsatish` (or a trade-specific
    child of it) IS the person's public profile -- experience/specialization/coverage-area/rate,
    the same fields a hiring business or a household would actually filter on, browsable the
    exact same way any other category's listings are (`catalogClient.listingsByCategoryPath`).
    Deliberately reuses the existing catalog-listing machinery rather than a bespoke profile/CV
    bounded context -- that would be a real architecture decision (ADR), not this task's."""
    fields = [
        _field("experience_years", "asosiy", "Tajriba (yil)", "number", required=True, facet=True, order=1),
        _field("specialization", "asosiy", "Mutaxassislik", "text", facet=True, order=2),
        _field("service_regions", "asosiy", "Xizmat ko'rsatiladigan hududlar", "text", order=3),
        _field(
            "rate_type",
            "asosiy",
            "Narx turi",
            "select",
            facet=True,
            order=4,
            options=[("hourly", "Soatlik"), ("daily", "Kunlik"), ("per_job", "Ish uchun")],
        ),
        _field("available_now", "asosiy", "Hozir band emas", "boolean", facet=True, order=5, default=True),
    ]
    if extra:
        fields.extend(extra)
    return fields


async def _seed_form(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    name: str,
    fields: list[dict[str, object]],
    section_code: str = "asosiy",
    section_name: str = "Asosiy ma'lumotlar",
    now: datetime,
) -> UUID:
    """Generic `FormDefinition` seeder -- the taxonomy-wide counterpart of
    `_seed_furniture_form` above (kept separate/untouched since it already ran once). Idempotent:
    returns the existing head's id (by code) if this has already run against this database."""
    definition = {
        "descriptor": {"name": {"uz_latn": name}},
        "sections": [{"code": section_code, "label": {"uz_latn": section_name}, "order": 1}],
        "fields": fields,
    }
    try:
        head, version = await use_cases.create_draft(
            ConfigEntityType.FORM_DEFINITION,
            code=code,
            business_owner="Catalog Owner",
            definition=definition,
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        existing = await repo.get_head_by_code(ConfigEntityType.FORM_DEFINITION, code)
        assert existing is not None, f"seed marker {code!r} vanished between check and lookup"
        return existing.id

    manage_key = _registry.manage_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    step1 = await use_cases.publish(
        ConfigEntityType.FORM_DEFINITION,
        head.id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: bootstrap form",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.FORM_DEFINITION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: bootstrap form approval",
            now=now,
        )
    return head.id


async def _seed_category(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    name: str,
    path: str,
    parent_category_id: UUID | None,
    form_definition_id: UUID,
    now: datetime,
) -> UUID:
    """Generic `Category` seeder. Always returns the head id (creating it, or looking it up by
    code if already seeded) -- unlike a bare "skip on duplicate", child categories below need a
    real parent id back even on a re-run against an already-seeded database."""
    definition = {
        "descriptor": {"name": {"uz_latn": name}},
        "parent_category_id": str(parent_category_id) if parent_category_id else None,
        "path": path,
        "form_definition_id": str(form_definition_id),
        "tree_status": "ACTIVE",
    }
    try:
        head, version = await use_cases.create_draft(
            ConfigEntityType.CATEGORY,
            code=code,
            business_owner="Catalog Owner",
            definition=definition,
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        existing = await repo.get_head_by_code(ConfigEntityType.CATEGORY, code)
        assert existing is not None, f"seed marker {code!r} vanished between check and lookup"
        return existing.id

    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY,
        head.id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: bootstrap category",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: bootstrap category approval",
            now=now,
        )
    return head.id


async def _seed_catalog_taxonomy(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    now: datetime,
) -> None:
    """The broad demo taxonomy behind every top-level path `CategoryCarousel.tsx`'s offline
    fallback (`CATS`/`ICON_BY_PATH`) already advertises, plus two additions this session: a
    services CV/directory branch (repairman / driver / truck-driver, each browsable the same way
    any other category's listings are) and a recreation-venues category. Each "direction" gets
    its own field shape (`_property_fields`, `_goods_fields`, `_service_cv_fields`, ...) rather
    than one form for every category, so `catalogClient.listingsByCategoryPath` results are
    actually queryable/facetable by what that direction's audience cares about."""

    # -- Residential/commercial buildings (a single shared form -- these differ by neighbourhood/
    # type, not by attribute shape).
    re_form_id = await _seed_form(
        use_cases, repo, code="ko-chmas-mulk-form", name="Ko'chmas mulk", fields=_property_fields(), now=now
    )
    for code, name, path in [
        ("kop-qavatli-binolar", "Ko'p qavatli binolar", "/kop-qavatli-binolar"),
        ("kotejlar", "Kotejlar", "/kotejlar"),
        ("hovlilar", "Hovlilar", "/hovlilar"),
        ("noturar-binolar", "Noturar binolar", "/noturar-binolar"),
        ("dala-hovlilar", "Dala hovlilar", "/dala-hovlilar"),
    ]:
        await _seed_category(
            use_cases, repo, code=code, name=name, path=path,
            parent_category_id=None, form_definition_id=re_form_id, now=now,
        )

    # -- Land.
    land_form_id = await _seed_form(
        use_cases, repo, code="bosh-yer-form", name="Bo'sh yer", fields=_land_fields(), now=now
    )
    await _seed_category(
        use_cases, repo, code="bosh-yerlar", name="Bo'sh yerlar", path="/bosh-yerlar",
        parent_category_id=None, form_definition_id=land_form_id, now=now,
    )

    # -- Goods (physical-unit sales).
    goods_form_id = await _seed_form(
        use_cases, repo, code="mahsulot-form", name="Mahsulot", fields=_goods_fields(), now=now
    )
    for code, name, path in [
        ("qurilish-materiallari", "Qurilish materiallari", "/qurilish-materiallari"),
        ("maishiy-texnikalar", "Maishiy texnikalar", "/maishiy-texnikalar"),
        ("uy-bezaklari", "Uy bezaklari", "/uy-bezaklari"),
        ("uniforma-va-maxsus-kiyimlar", "Uniforma va maxsus kiyimlar", "/uniforma-va-maxsus-kiyimlar"),
    ]:
        await _seed_category(
            use_cases, repo, code=code, name=name, path=path,
            parent_category_id=None, form_definition_id=goods_form_id, now=now,
        )

    # -- Hospitality.
    hosp_form_id = await _seed_form(
        use_cases, repo, code="mehmonxona-form", name="Mehmonxona/Hostel", fields=_hospitality_fields(), now=now
    )
    for code, name, path in [
        ("hostel", "Hostel", "/hostel"),
        ("mexmonxona", "Mexmonxona", "/mexmonxona"),
    ]:
        await _seed_category(
            use_cases, repo, code=code, name=name, path=path,
            parent_category_id=None, form_definition_id=hosp_form_id, now=now,
        )

    # -- Business directory (showrooms, not units).
    business_form_id = await _seed_form(
        use_cases, repo, code="biznes-korxona-form", name="Biznes/korxona", fields=_business_fields(), now=now
    )
    await _seed_category(
        use_cases, repo, code="mebel-salonlari", name="Mebel salonlari", path="/mebel-salonlari",
        parent_category_id=None, form_definition_id=business_form_id, now=now,
    )

    # -- Recreation venues (new, per this session's request).
    venue_form_id = await _seed_form(
        use_cases, repo, code="dam-olish-maskani-form", name="Dam olish maskani", fields=_venue_fields(), now=now
    )
    await _seed_category(
        use_cases, repo, code="dam-olish-maskanlari", name="Dam olish maskanlari", path="/dam-olish-maskanlari",
        parent_category_id=None, form_definition_id=venue_form_id, now=now,
    )

    # -- Landshaft dizayni: a design SERVICE, not goods -- the base CV shape, no trade extras.
    landshaft_form_id = await _seed_form(
        use_cases, repo, code="landshaft-xizmati-form", name="Landshaft dizayni xizmati",
        fields=_service_cv_fields(), now=now,
    )
    await _seed_category(
        use_cases, repo, code="landshaft-dizayni", name="Landshaft dizayni", path="/landshaft-dizayni",
        parent_category_id=None, form_definition_id=landshaft_form_id, now=now,
    )

    # -- Ish o'rni (job postings) -- same CV shape; here `specialization`/`experience_years` read
    # as the employer's requirement rather than the applicant's own.
    ish_orni_form_id = await _seed_form(
        use_cases, repo, code="ish-orni-form", name="Ish o'rni", fields=_service_cv_fields(), now=now
    )
    await _seed_category(
        use_cases, repo, code="ish-orni", name="Ish o'rni", path="/ish-orni",
        parent_category_id=None, form_definition_id=ish_orni_form_id, now=now,
    )

    # -- Xizmat ko'rsatish: the services directory. A CV-shaped child category per trade so
    # someone hiring a repairman/driver/truck-driver browses candidates exactly like any other
    # category's listings -- new listing = new "CV" entry, searchable by specialization/region/
    # rate via the same `catalogClient.listingsByCategoryPath` every other category already uses.
    services_form_id = await _seed_form(
        use_cases, repo, code="xizmat-korsatish-form", name="Xizmat ko'rsatish", fields=_service_cv_fields(), now=now
    )
    services_head_id = await _seed_category(
        use_cases, repo, code="xizmat-korsatish", name="Xizmat ko'rsatish", path="/xizmat-korsatish",
        parent_category_id=None, form_definition_id=services_form_id, now=now,
    )

    tamirchi_form_id = await _seed_form(
        use_cases, repo, code="tamirchi-form", name="Ta'mirchi",
        fields=_service_cv_fields(
            extra=[
                _field(
                    "trade", "asosiy", "Yo'nalish", "select", required=True, facet=True, order=10,
                    options=[
                        ("santexnik", "Santexnik"),
                        ("elektrik", "Elektrik"),
                        ("mebel_ustasi", "Mebel ustasi"),
                        ("maishiy_texnika_ustasi", "Maishiy texnika ustasi"),
                        ("qurilish_ustasi", "Qurilish/ta'mir ustasi"),
                        ("boshqa", "Boshqa"),
                    ],
                ),
            ]
        ),
        now=now,
    )
    await _seed_category(
        use_cases, repo, code="tamirchi-xizmati", name="Ta'mirchi", path="/tamirchi",
        parent_category_id=services_head_id, form_definition_id=tamirchi_form_id, now=now,
    )

    haydovchi_form_id = await _seed_form(
        use_cases, repo, code="haydovchi-form", name="Mashina haydovchisi",
        fields=_service_cv_fields(
            extra=[
                _field(
                    "license_category", "asosiy", "Haydovchilik guvohnomasi toifasi", "select",
                    required=True, facet=True, order=10,
                    options=[("B", "B"), ("C", "C"), ("D", "D"), ("BE", "BE"), ("CE", "CE")],
                ),
                _field("own_vehicle", "asosiy", "O'z avtomobili bor", "boolean", facet=True, order=11, default=False),
            ]
        ),
        now=now,
    )
    await _seed_category(
        use_cases, repo, code="mashina-haydovchisi", name="Mashina haydovchisi", path="/haydovchi",
        parent_category_id=services_head_id, form_definition_id=haydovchi_form_id, now=now,
    )

    yuk_haydovchi_form_id = await _seed_form(
        use_cases, repo, code="yuk-haydovchi-form", name="Yuk mashina haydovchisi",
        fields=_service_cv_fields(
            extra=[
                _field(
                    "license_category", "asosiy", "Haydovchilik guvohnomasi toifasi", "select",
                    required=True, facet=True, order=10,
                    options=[("C", "C"), ("CE", "CE"), ("D", "D"), ("DE", "DE")],
                ),
                _field(
                    "vehicle_type", "asosiy", "Yuk mashina turi", "select", facet=True, order=11,
                    options=[
                        ("gazelle", "Gazel / kichik yuk"),
                        ("truck", "Yuk mashina"),
                        ("trailer", "Tirkamali yuk mashina"),
                        ("refrigerator", "Refrijerator"),
                    ],
                ),
                _field("cargo_capacity_tons", "asosiy", "Yuk ko'tarish sig'imi (tonna)", "number", facet=True, order=12),
            ]
        ),
        now=now,
    )
    await _seed_category(
        use_cases, repo, code="yuk-mashina-haydovchisi", name="Yuk mashina haydovchisi", path="/yuk-haydovchi",
        parent_category_id=services_head_id, form_definition_id=yuk_haydovchi_form_id, now=now,
    )


async def run_seed() -> None:
    engine = make_engine()
    session_factory = make_session_factory(engine)
    redis = Redis.from_url(redis_url())
    cache = RedisSnapshotCache(redis)
    now = datetime.now(UTC)

    try:
        async with session_scope(session_factory) as session:
            repo = SqlalchemyConfigHeadRepository(session)
            outbox = OutboxWriter(session, OutboxEvent)
            use_cases = ConfigurationUseCases(repo, cache, outbox)

            try:
                await _seed_role(
                    use_cases,
                    code="super-admin",
                    role_name="Super Administrator",
                    permission_keys=_super_admin_permission_keys(),
                    now=now,
                )
                await _seed_role(
                    use_cases,
                    code="administrator",
                    role_name="Administrator",
                    permission_keys=_administrator_permission_keys(),
                    now=now,
                )
                await _seed_platform_settings(use_cases, now=now)

                furniture_form_id = await _seed_furniture_form(use_cases, repo, now=now)
                await _seed_furniture_category(
                    use_cases, form_definition_id=furniture_form_id, now=now
                )

                await _seed_catalog_taxonomy(use_cases, repo, now=now)
            except GateFailedError as exc:
                raise RuntimeError(
                    f"seed data failed the validation gate: {exc.result.errors}"
                ) from exc
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run_seed())


if __name__ == "__main__":
    main()
