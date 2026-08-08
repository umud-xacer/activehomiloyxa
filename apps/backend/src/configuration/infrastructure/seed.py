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
import re
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
            "admin.owner_panel_slug": "owner-admin",
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
    repo: SqlalchemyConfigHeadRepository,
    *,
    form_definition_id: UUID,
    now: datetime,
) -> UUID:
    """The "Mebel materiallari" (Furniture) top-level category, bound to the form above -- the
    exact path the frontend already hardcodes (`CategoryCarousel.tsx`'s `ICON_BY_PATH["/mebel-
    materiallari"]` and the `/furniture` route's `CATEGORY_PATH`), so both the homepage category
    rail and the dedicated furniture page resolve to real data once this has run. Returns the
    head id either way (fresh or pre-existing) so callers can seed a subtree under it."""
    code = "mebel-materiallari"
    definition = {
        "descriptor": {
            "name": {"uz_latn": "Mebel materiallari", "ru": "Мебель", "en": "Furniture"},
            "metadata": {"listingKind": "GOODS"},
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
        existing = await repo.get_head_by_code(ConfigEntityType.CATEGORY, code)
        assert existing is not None, f"seed marker {code!r} vanished between check and lookup"
        await _backfill_listing_kind(
            use_cases, repo, head_id=existing.id, current_version_id=existing.current_version_id,
            listing_kind="GOODS", now=now,
        )
        return existing.id

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
    return head.id


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
    listing_kind: str | None = None,
) -> UUID:
    """Generic `Category` seeder. Always returns the head id (creating it, or looking it up by
    code if already seeded) -- unlike a bare "skip on duplicate", child categories below need a
    real parent id back even on a re-run against an already-seeded database.

    `listing_kind` (PROPERTY/GOODS/SERVICE/VENUE) lands in `descriptor.metadata.listingKind` --
    the sanctioned inert key-value extension slot (`content.py`'s `ConfigDescriptor.metadata`
    docstring) -- which `lib/listing-kind.ts#listingKindOf` reads to pick a category's rendering
    shape. Omit (None) for the PROPERTY default (real estate), matching the frontend's own
    documented fallback."""
    descriptor: dict[str, object] = {"name": {"uz_latn": name}}
    if listing_kind is not None:
        descriptor["metadata"] = {"listingKind": listing_kind}
    definition = {
        "descriptor": descriptor,
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
        await _backfill_listing_kind(
            use_cases, repo, head_id=existing.id, current_version_id=existing.current_version_id,
            listing_kind=listing_kind, now=now,
        )
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


async def _backfill_listing_kind(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    head_id: UUID,
    current_version_id: UUID | None,
    listing_kind: str | None,
    now: datetime,
) -> None:
    """Self-heal for a category that already existed (e.g. seeded in an earlier session/deploy
    before `listing_kind` existed) and so was skipped by `_seed_category`'s `DuplicateCodeError`
    branch without ever getting the metadata. Publishes a new version -- same maker-checker flow
    as a fresh category -- only when the stored `listingKind` doesn't already match, so this is a
    no-op on every subsequent run once it's caught up (true idempotency, not just duplicate-skip)."""
    if listing_kind is None or current_version_id is None:
        return
    current = await repo.get_version(ConfigEntityType.CATEGORY, head_id, current_version_id)
    if current is None:
        return
    current_descriptor = dict(current.definition_document.get("descriptor") or {})
    current_metadata = dict(current_descriptor.get("metadata") or {})
    if current_metadata.get("listingKind") == listing_kind:
        return

    new_metadata = {**current_metadata, "listingKind": listing_kind}
    new_descriptor = {**current_descriptor, "metadata": new_metadata}
    new_document = {**current.definition_document, "descriptor": new_descriptor}

    new_version = await use_cases.create_version_draft(
        ConfigEntityType.CATEGORY, head_id, definition=new_document, actor_id=SEED_MAKER_ID, now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY, head_id, new_version.id,
        actor_id=SEED_MAKER_ID, actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: backfill listingKind metadata", now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY, head_id, step1.id,
            actor_id=SEED_CHECKER_ID, actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: backfill listingKind metadata approval", now=now,
        )


_TOP_LEVEL_CATEGORY_HERO_THEMES: dict[str, dict[str, str]] = {
    "qurilish-materiallari": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/7903_40537885803_294ee51e0e_h_1280_720_nofilter.jpg",
        "heroTagline": "Har bir qurilish uchun ishonchli materiallar",
        "accentColor": "#EA580C",
    },
    "ish-orni": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_52906947696_b92bd08840_h_1280_720_nofilter.jpg",
        "heroTagline": "Ko'chmas mulk va qurilish sohasidagi eng yaxshi ish o'rinlari",
        "accentColor": "#2563EB",
    },
    "dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54398734359_27a6e8545f_h_1280_720_nofilter.jpg",
        "heroTagline": "Shahar shovqinidan uzoqlashing, tabiat qo'ynida dam oling",
        "accentColor": "#16A34A",
    },
    "uniforma-va-maxsus-kiyimlar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54384001542_d84c09c6e2_h_1280_720_nofilter.jpg",
        "heroTagline": "Professional ish uchun ishonchli himoya kiyimlari",
        "accentColor": "#F59E0B",
    },
    "mebel-materiallari": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54000294184_43e3e8e164_h_1280_720_nofilter.jpg",
        "heroTagline": "Mebel yaratish uchun sifatli materiallar",
        "accentColor": "#92400E",
    },
    "dam-olish-maskanlari": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54088010610_9fa068dfa2_k_1280_720_nofilter.jpg",
        "heroTagline": "Eng yaxshi dam olish maskanlarini shu yerdan toping",
        "accentColor": "#0D9488",
    },
    "hovlilar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54452293698_3c3f2b3cc5_h_1280_720_nofilter.jpg",
        "heroTagline": "O'zingizni uyda his qiladigan hovlingizni toping",
        "accentColor": "#059669",
    },
    "landshaft-dizayni": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54511310790_b631dd27f8_h_1280_720_nofilter.jpg",
        "heroTagline": "Hovlingizni professional dizayn bilan bezating",
        "accentColor": "#22C55E",
    },
    "kop-qavatli-binolar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54396383676_3b2122fddd_h_1280_720_nofilter.jpg",
        "heroTagline": "Zamonaviy shahar hayoti uchun yangi uy",
        "accentColor": "#334155",
    },
    "bosh-yerlar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_49834685981_790d3f8602_h_1280_720_nofilter.jpg",
        "heroTagline": "Kelajakdagi qurilishingiz uchun ishonchli yer",
        "accentColor": "#B45309",
    },
    "mebel-salonlari": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/7058_6890528665_0debdf43c1_1280_720_nofilter.jpg",
        "heroTagline": "Uyingiz uchun premium mebel kolleksiyalari",
        "accentColor": "#7C3AED",
    },
    "noturar-binolar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54391974673_95f2178994_h_1280_720_nofilter.jpg",
        "heroTagline": "Biznesingiz uchun professional makon",
        "accentColor": "#1E3A8A",
    },
    "uy-bezaklari": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_54584305864_c2326e33eb_k_1280_720_nofilter.jpg",
        "heroTagline": "Uyingizga did va zavq qo'shing",
        "accentColor": "#DB2777",
    },
    "hostel": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/4871_46940671922_cf1af5497e_h_1280_720_nofilter.jpg",
        "heroTagline": "Qulay va arzon tunash joylarini toping",
        "accentColor": "#0891B2",
    },
    "mexmonxona": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_53700417322_b2ee24338f_h_1280_720_nofilter.jpg",
        "heroTagline": "Hashamat va qulaylik bir joyda",
        "accentColor": "#CA8A04",
    },
    "xizmat-korsatish": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/5457_30488745703_2cea8a2808_h_1280_720_nofilter.jpg",
        "heroTagline": "Ishonchli ustalar va tezkor xizmat",
        "accentColor": "#DC2626",
    },
    "kotejlar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/65535_49957301776_2f894d8375_h_1280_720_nofilter.jpg",
        "heroTagline": "Tabiat qo'ynidagi hashamatli dam olish",
        "accentColor": "#15803D",
    },
    "maishiy-texnikalar": {
        "heroImageUrl": "https://loremflickr.com/cache/resized/380_32272111690_58649f2aa7_h_1280_720_nofilter.jpg",
        "heroTagline": "Uyingiz uchun zamonaviy texnikalar",
        "accentColor": "#0284C7",
    },
}
"""One themed hero per top-level category (Task: category mini-platform redesign) -- images from
`loremflickr.com` (keyless, topic-tagged real photos, no API key/rate-limit like the Google/
Mapbox/Yandex-JS-key services this codebase has already deliberately avoided elsewhere, see
`feedback-technical-preferences` memory). `accentColor` values are spread across the palette so
no two top-level categories read as visually identical. Consumed by `_backfill_category_theme`
below, which is the only thing that ever reads this table.

URLs point directly at loremflickr's `/cache/resized/...jpg` path rather than its
`/{w}/{h}/{tags}` endpoint: the latter is a redirector (302 to the former) and that extra hop
alone measured ~0.9-1.4s on top of the actual image fetch -- confirmed live, reported by the user
as "kategoriyalarni fon rasmi sekin yuklanyapti" (category hero backgrounds loading slowly).
Skipping it roughly halves hero load time (~2s -> ~0.8-1.1s per image, measured). Each URL was
resolved once by requesting the original `{w}/{h}/{tags}` endpoint and reading its `Location`
header -- if loremflickr ever retires a cached file this hero silently falls back to no image
(PageHeader's plain gradient), not a broken page, so this is a safe optimization to hand-pin."""


async def _backfill_category_theme(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    hero_image_url: str,
    hero_tagline: str,
    accent_color: str,
    now: datetime,
) -> None:
    """Self-heal for a top-level category seeded before hero content existed (or before this
    theme table gained an entry for it) -- same publish-a-new-version pattern as
    `_backfill_listing_kind`, merged into the same `descriptor.metadata` slot the owner-admin
    panel's own hero-editing form already writes to. No-op once the stored values already match
    exactly, so this is safe (and cheap) to re-run on every deploy; a super-admin who has since
    hand-edited a category's hero from the panel keeps their own values only if they happen to
    match this table -- otherwise this backfill will overwrite them back to the table's defaults
    on the next deploy, same as `_backfill_listing_kind` already does for `listingKind`."""
    head = await repo.get_head_by_code(ConfigEntityType.CATEGORY, code)
    if head is None or head.current_version_id is None:
        return
    current = await repo.get_version(ConfigEntityType.CATEGORY, head.id, head.current_version_id)
    if current is None:
        return
    current_descriptor = dict(current.definition_document.get("descriptor") or {})
    current_metadata = dict(current_descriptor.get("metadata") or {})
    desired = {
        "heroImageUrl": hero_image_url,
        "heroTagline": hero_tagline,
        "accentColor": accent_color,
    }
    if all(current_metadata.get(k) == v for k, v in desired.items()):
        return

    new_metadata = {**current_metadata, **desired}
    new_descriptor = {**current_descriptor, "metadata": new_metadata}
    new_document = {**current.definition_document, "descriptor": new_descriptor}

    new_version = await use_cases.create_version_draft(
        ConfigEntityType.CATEGORY, head.id, definition=new_document, actor_id=SEED_MAKER_ID, now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY, head.id, new_version.id,
        actor_id=SEED_MAKER_ID, actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: backfill hero theme metadata", now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY, head.id, step1.id,
            actor_id=SEED_CHECKER_ID, actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: backfill hero theme metadata approval", now=now,
        )


def _slugify(text: str) -> str:
    """Latin-Uzbek-aware slug matching the convention the hand-written codes above already use
    (apostrophes drop rather than transliterate, so "Ko'p qavatli binolar" -> "kop-qavatli-
    binolar", same as the existing `kop-qavatli-binolar` top-level code)."""
    text = text.replace("'", "").replace("’", "").replace("‘", "")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug


Node = str | tuple[str, list["Node"]]
"""A subcategory-tree node: a bare name (leaf) or `(name, children)` (branch). Recursion depth
is whatever the source taxonomy needs -- `_seed_subtree` below doesn't cap it."""


async def _seed_subtree(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    nodes: list[Node],
    *,
    parent_id: UUID,
    parent_path: str,
    form_definition_id: UUID,
    now: datetime,
    listing_kind: str | None = None,
) -> None:
    """Recursively seeds a nested-category subtree under `parent_id` (TZ-04 taxonomy expansion:
    every top-level category's subcategories, and their own subcategories, as literal Uzbek
    names transcribed from the spec). Reuses the parent's form -- these are all still the same
    "direction" as their top-level parent, just a finer tree position, not a new attribute shape.
    `code` is derived from the full path (not the bare name) so two branches can both have a
    same-named leaf (e.g. "2 xonali" under both `/hovlilar/sotuvdagi-hovlilar` and elsewhere)
    without a `DuplicateCodeError`. `listing_kind` propagates to every node in the subtree -- a
    subcategory renders through the same shape (`lib/listing-kind.ts`) as its top-level ancestor,
    same as the flat map this replaced did implicitly for every path under a given prefix."""
    for node in nodes:
        name, children = node if isinstance(node, tuple) else (node, [])
        path = f"{parent_path}/{_slugify(name)}"
        code = _slugify(path.lstrip("/"))
        head_id = await _seed_category(
            use_cases, repo, code=code, name=name, path=path,
            parent_category_id=parent_id, form_definition_id=form_definition_id, now=now,
            listing_kind=listing_kind,
        )
        if children:
            await _seed_subtree(
                use_cases, repo, children, parent_id=head_id, parent_path=path,
                form_definition_id=form_definition_id, now=now, listing_kind=listing_kind,
            )


def _kop_qavatli_binolar_tree() -> list[Node]:
    return [
        (
            "Yangi qurilishlar",
            ["1 xonali", "2 xonali", "3 xonali", "4+ xonali", "Family", "Duplex", "Loft", "Smart Apartment"],
        ),
        "Ikkilamchi bozor",
        ("Premium turar joylar", ["Sky Residence", "Penthouse", "Terrace Apartment", "Smart Home", "Designer Interior"]),
        "Biznes klass",
        "Komfort klass",
        "Ekonom klass",
        "Penthouse",
        "Studio",
        ("Investitsiya uchun", ["Erta bosqich", "Qurilish jarayonida", "Tayyor loyiha", "Yuqori daromadli", "Tijorat uchun mos"]),
        "Ipotekali uylar",
        "Qurilishi davom etayotgan loyihalar",
        "Tayyor topshirilgan loyihalar",
    ]


def _kotejlar_tree() -> list[Node]:
    return [
        ("Oilaviy kotejlar", ["2 xonali", "3 xonali", "5+ xonali", "Bolalar maydonchali kotejlar"]),
        ("Premium kotejlar", ["Basseynli", "Sauna va SPA'li", "Panoramali", "VIP xizmatli kotejlar"]),
        "Luxury Villalar",
        ("Tog' kotejlari", ["Qishki dam olish uchun", "Yozgi dam olish uchun", "Ekstremal turizm uchun"]),
        "Ko'l bo'yidagi kotejlar",
        "O'rmon hududidagi kotejlar",
        "Shahar tashqarisidagi kotejlar",
        "Kunlik ijaraga beriladigan kotejlar",
        "Uzoq muddatli ijaradagi kotejlar",
        "Sotuvdagi kotejlar",
        "Smart kotejlar",
        "Eco kotejlar",
        "Resort villalar",
        "Investitsion kotejlar",
    ]


def _hovlilar_tree() -> list[Node]:
    return [
        ("Sotuvdagi hovlilar", ["2 xonali", "3 xonali", "4 xonali", "5+ xonali"]),
        "Ijaraga beriladigan hovlilar",
        "Yangi qurilgan hovlilar",
        "Ikkilamchi bozordagi hovlilar",
        ("Premium hovlilar", ["Zamonaviy villa", "Klassik villa", "Panoramali hovli", "Dizaynerlik interyeriga ega hovlilar"]),
        "Kottejlar",
        "Townhouse",
        ("Hovuzli hovlilar", ["Ochiq hovuz", "Yopiq hovuz", "Isitiladigan hovuz", "SPA zonali hovlilar"]),
        "Katta yer maydoniga ega hovlilar",
        "Shahar ichidagi hovlilar",
        "Shahar tashqarisidagi hovlilar",
        "Investitsiya uchun hovlilar",
        "Qurilishi tugallanmagan hovlilar",
        ("Smart Home hovlilar", ["Avtomatlashtirilgan xavfsizlik tizimi", "Aqlli yoritish", "Aqlli iqlim boshqaruvi"]),
    ]


def _noturar_binolar_tree() -> list[Node]:
    return [
        ("Ofis binolari", ["Business Center", "Coworking", "Premium Office", "Open Space", "Alohida ofislar"]),
        ("Savdo markazlari", ["Butiklar", "Supermarketlar", "Showroomlar", "Savdo pavilyonlari", "Food court joylari"]),
        "Do'kon va butiklar",
        "Restoran va kafelar",
        "Mehmonxonalar",
        ("Omborxonalar", ["Logistika omborlari", "Sovutkich omborlari", "Distribyutor markazlari", "Sanoat omborlari"]),
        "Ishlab chiqarish binolari",
        "Zavod va fabrikalar",
        "Tibbiyot markazlari",
        "Ta'lim muassasalari",
        "Avtoservis va avtosalonlar",
        "Sport va fitness markazlari",
        "Ko'ngilochar markazlar",
        "Investitsiya obyektlari",
    ]


def _dala_hovlilar_tree() -> list[Node]:
    return [
        "Sotuvdagi dala hovlilar",
        "Ijaraga beriladigan dala hovlilar",
        (
            "Kunlik ijara",
            ["2 kishilik", "Oilaviy", "Katta guruhlar uchun", "Korporativ dam olish uchun", "Bayram tadbirlari uchun"],
        ),
        "Haftalik va oylik ijara",
        ("Premium villalar", ["Smart Home", "VIP villa", "Panoramali villa", "Zamonaviy dizayndagi villalar"]),
        "Oilaviy dam olish hovlilari",
        "Tog' hududidagi dala hovlilar",
        "Ko'l yoki daryo bo'yidagi hovlilar",
        (
            "Hovuzli dala hovlilar",
            ["Ochiq hovuz", "Yopiq hovuz", "Isitiladigan hovuz", "Bolalar hovuzi", "Premium SPA zonali hovlilar"],
        ),
        "Barbekyu va yozgi oshxonali hovlilar",
        "Investitsiya uchun dala hovlilar",
        "Yangi qurilgan dala hovlilar",
    ]


def _bosh_yerlar_tree() -> list[Node]:
    return [
        (
            "Turar joy qurish uchun yerlar",
            ["2 sotixgacha", "2-4 sotix", "4-6 sotix", "6-10 sotix", "10 sotixdan katta"],
        ),
        (
            "Tijorat maqsadidagi yerlar",
            ["Savdo markazi uchun", "Ofis binosi uchun", "Omborxona uchun", "Mehmonxona uchun", "Restoran uchun"],
        ),
        "Sanoat hududlari",
        ("Qishloq xo'jaligi yerlari", ["Bog'dorchilik", "Issiqxona", "Chorvachilik", "Dehqonchilik"]),
        "Dala va bog' yerlari",
        "Fermer xo'jaligi yerlari",
        "Investitsiya uchun yerlar",
        "Kottej shaharchalari uchun yerlar",
        "Yangi massivlardagi yerlar",
        "Shahar ichidagi yerlar",
        "Shahar tashqarisidagi yerlar",
        "Auksion orqali sotilayotgan yerlar",
        "Yirik loyiha uchun yer maydonlari",
        "Kommunikatsiyaga tayyor yerlar",
    ]


def _qurilish_materiallari_tree() -> list[Node]:
    return [
        "Sement va quruq aralashmalar",
        "G'isht va bloklar",
        "Armatura va metall mahsulotlari",
        "Yog'och mahsulotlari",
        "Tom yopish materiallari",
        "Issiqlik va gidroizolyatsiya",
        ("Elektr mahsulotlari", ["Kabel", "Rozetka", "Avtomat", "Yoritish", "Sensor"]),
        "Santexnika mahsulotlari",
        (
            "Bo'yoqlar va pardozlash materiallari",
            ["Ichki bo'yoq", "Tashqi bo'yoq", "Grunt", "Lak", "Emal", "Dekorativ qoplamalar"],
        ),
        "Pol qoplamalari",
        "Eshik va derazalar",
        ("Mahkamlash mahsulotlari", ["Mix", "Vint", "Shurup", "Bolt", "Gayka", "Shayba", "Dyubel", "Anker"]),
        "Qurilish asbob-uskunalari",
        "Maxsus texnika va jihozlar",
    ]


def _maishiy_texnikalar_tree() -> list[Node]:
    return [
        ("Muzlatgichlar", ["Ikki eshikli", "Side by Side", "Mini muzlatgichlar", "Smart muzlatgichlar"]),
        ("Kir yuvish mashinalari", ["Avtomatik", "Yarim avtomatik", "Quritish funksiyali", "Sanoat kir yuvish mashinalari"]),
        "Idish yuvish mashinalari",
        "Gaz plitalari va pechlar",
        "Mikroto'lqinli pechlar",
        "Changyutgichlar",
        "Konditsionerlar",
        "Televizorlar",
        "Suv isitkichlari",
        ("Oshxona texnikalari", ["Blenderlar", "Mikserlar", "Kofe mashinalari", "Multivarkalar", "Elektr choynaklar"]),
        "Kichik maishiy texnikalar",
        "Smart Home qurilmalari",
        "Iqlim texnikalari",
        "Premium texnikalar",
    ]


def _uy_bezaklari_tree() -> list[Node]:
    return [
        (
            "Devor bezaklari",
            ["3D panellar", "Dekorativ yog'och panellar", "Metall dekorlar", "Stikerlar", "Premium devor kompozitsiyalari"],
        ),
        "Rasmlar va kartinalar",
        "Ko'zgular",
        ("Pardalar va jalyuzilar", ["Zamonaviy", "Klassik", "Blackout", "Avtomatik", "Premium kolleksiyalar"]),
        "Gilam va pol qoplamalari",
        (
            "Dekorativ yoritish",
            ["LED yoritish", "Osma chiroqlar", "Tungi lampalar", "Dizayner lampalari", "Aqlli yoritish tizimlari"],
        ),
        "Gullar va dekorativ o'simliklar",
        "Vaza va haykallar",
        "Soatlar",
        "Shamdon va dekor aksessuarlari",
        "Oshxona bezaklari",
        "Yotoqxona dekorlari",
        "Hammom aksessuarlari",
        "Smart dekor mahsulotlari",
    ]


def _uniforma_tree() -> list[Node]:
    return [
        ("Qurilish kiyimlari", ["Kurtka", "Shim", "Kombinezon", "Jilet", "Yomg'ir kiyimi", "Termo kiyimlar"]),
        "Muhandis va texnik kiyimlari",
        "Elektrchilar uchun kiyimlar",
        "Payvandchilar uchun kiyimlar",
        "Santexnik va usta kiyimlari",
        "Xavfsizlik xodimlari formasi",
        "Tibbiyot kiyimlari",
        "Mehmonxona va servis formasi",
        "Restoran va oshpaz formasi",
        "Ofis formasi",
        "Maxsus himoya kiyimlari",
        (
            "Ish poyabzallari",
            ["Etik", "Botinka", "Yozgi poyabzal", "Qishki poyabzal", "Suv o'tkazmaydigan poyabzal", "Metall burunli poyabzal"],
        ),
        (
            "Himoya vositalari",
            ["Kaska", "Qo'lqop", "Ko'zoynak", "Respirator", "Niqob", "Quloqchin", "Xavfsizlik kamarlari"],
        ),
        "Mavsumiy ish kiyimlari",
    ]


def _mebel_materiallari_tree() -> list[Node]:
    return [
        ("Yog'och materiallari", ["Eman", "Qarag'ay", "Yong'oq", "Buk", "MDF", "DSP"]),
        "MDF va DSP plitalari",
        "Fanera va laminatlar",
        "Stoleshnitsalar",
        ("Mebel furnituralari", ["Ilgaklar", "Menteshalar", "Relslar", "Lift tizimlari", "Magnitlar", "Qulflar"]),
        "Tutqich va aksessuarlar",
        "Sharnir va rels tizimlari",
        "Mebel oyoqlari va tayanchlari",
        "Shisha va oyna mahsulotlari",
        "Yumshoq mebel materiallari",
        ("Mato va charm qoplamalar", ["Velyur", "Eko charm", "Tabiiy charm", "Mikrofiber"]),
        "Yelim va kimyoviy mahsulotlar",
        "Bo'yoq va laklar",
        "Mebel ishlab chiqarish asboblari",
    ]


def _mebel_salonlari_tree() -> list[Node]:
    return [
        ("Oshxona mebellari", ["Zamonaviy", "Klassik", "Minimalistik", "Premium oshxona garniturlari"]),
        "Yotoqxona mebellari",
        "Mehmonxona mebellari",
        "Bolalar xonasi mebellari",
        ("Ofis mebellari", ["Ish stollari", "Ofis stullari", "Konferensiya stollari", "Shkaflar", "Resepsion mebellari"]),
        ("Yumshoq mebellar", ["Divanlar", "Burchak divanlar", "Kreslolar", "Puflar", "Transformatsiyalanuvchi mebellar"]),
        "Premium mebellar",
        "Buyurtma asosida tayyorlanadigan mebellar",
        "Bog' va tashqi mebellar",
        "Restoran va kafe mebellari",
        "Dekor va interyer aksessuarlari",
        "Mebel aksessuarlari",
        "Smart mebellar",
    ]


def _dam_olish_maskanlari_tree() -> list[Node]:
    return [
        ("Mehmonxonalar", ["3 yulduzli", "4 yulduzli", "5 yulduzli", "Boutique Hotel", "Business Hotel", "Family Hotel"]),
        "Dala hovlilar",
        "Villalar",
        "Kottejlar",
        "Kurort va sanatoriyalar",
        ("Hovuz va akvaparklar", ["Ochiq hovuz", "Yopiq hovuz", "Bolalar akvaparki", "VIP zonalar", "Family zonalari"]),
        (
            "SPA va Wellness markazlari",
            ["Sauna", "Hammom", "Massaj", "Fitnes", "Termal hovuz", "Sog'lomlashtirish xizmatlari"],
        ),
        "Tog' dam olish maskanlari",
        "Ko'l va daryo bo'yidagi maskanlar",
        "Oilaviy dam olish zonalari",
        "Bolalar ko'ngilochar markazlari",
        "Restoran va kafe zonalari",
        "Piknik va Camping hududlari",
        "Sarguzasht va ekstremal dam olish maskanlari",
    ]


def _landshaft_tree() -> list[Node]:
    return [
        "Hovli dizayni",
        (
            "Bog' loyihalash",
            ["Zamonaviy bog'", "Klassik bog'", "Yapon bog'i", "Minimalistik bog'", "Mevali bog'", "Dekorativ bog'"],
        ),
        "Park va yashil hududlar",
        "Avtomatik sug'orish tizimlari",
        "Gazon va maysa ishlari",
        "Daraxt va gul ekish",
        "Dekorativ tosh va yo'laklar",
        "Favvora va sun'iy suv havzalari",
        (
            "Tashqi yoritish tizimlari",
            ["Quyosh energiyasida ishlovchi chiroqlar", "LED yoritish", "Dekorativ yoritish", "Aqlli yoritish tizimlari"],
        ),
        "Pergola va ayvonlar",
        (
            "Tashqi dam olish zonalari",
            ["Yozgi oshxona", "Barbekyu zonasi", "Pergola", "Gazebo", "Ochiq terassa", "Bolalar maydonchasi"],
        ),
        "Vertikal bog'lar",
        "Tom bog'lari (Roof Garden)",
        "Landshaft parvarishlash xizmatlari",
    ]


def _ish_orni_tree() -> list[Node]:
    return [
        ("Qurilish ishlari", ["Betonchi", "G'isht teruvchi", "Suvoqchi", "Armaturachi", "Payvandchi", "Tom yopuvchi"]),
        ("Usta xizmatlari", ["Elektrchi", "Santexnik", "Konditsioner ustasi", "Mebel ustasi", "Bo'yoqchi"]),
        "Muhandislik",
        "Arxitektura va dizayn",
        "Ko'chmas mulk agentlari",
        "Sotuv va marketing",
        "Ofis ishlari",
        "Haydovchilar",
        "Ombor va logistika",
        "Xavfsizlik",
        "Tozalash xizmatlari",
        (
            "IT va texnologiyalar",
            ["Frontend dasturchi", "Backend dasturchi", "Mobil dasturchi", "UI/UX dizayner", "System Administrator"],
        ),
        "Moliya va buxgalteriya",
        "Menejment",
        "Boshqa kasblar",
    ]


def _xizmat_korsatish_tree() -> list[Node]:
    """New service subcategories from TZ-04, seeded alongside the pre-existing tamirchi/
    haydovchi/yuk-haydovchi CV-shaped children (seeded separately, unchanged)."""
    return [
        (
            "Ta'mirlash xizmatlari",
            ["Kosmetik ta'mirlash", "Kapital ta'mirlash", "Ofis ta'miri", "Kvartira ta'miri", "Fasad ishlari"],
        ),
        "Usta xizmatlari",
        (
            "Elektrik xizmatlari",
            ["Sim tortish", "Elektr qalqonlarini o'rnatish", "Yoritish tizimlari", "Smart Home elektr tizimlari", "Avariya xizmatlari"],
        ),
        "Santexnika xizmatlari",
        "Konditsioner va ventilyatsiya",
        (
            "Tozalash xizmatlari",
            ["Kundalik tozalash", "General tozalash", "Ofis tozalash", "Qurilishdan keyingi tozalash", "Kimyoviy tozalash"],
        ),
        "Qurilish brigadalari",
        "Mebel yig'ish va o'rnatish",
        "Yuk tashish xizmatlari",
        "Ko'chirish (Pereezd) xizmatlari",
        "Xavfsizlik tizimlari",
        "Video kuzatuv va Smart Home",
        "Dizayn va loyiha xizmatlari",
        "Uy boshqaruvi va texnik xizmat",
    ]


def _hostel_tree() -> list[Node]:
    return [
        "Erkaklar hosteli",
        "Ayollar hosteli",
        "Oilaviy hostellar",
        ("Talabalar hosteli", ["Universitetlarga yaqin hostellar", "Oylik ijarali hostellar", "Umumiy yashash xonalari"]),
        ("Premium hostellar", ["Private Room", "Deluxe Room", "Family Room", "Suite"]),
        ("Kapsula hostellar", ["Standart kapsula", "Premium kapsula", "Smart Capsule"]),
        "Guest House",
        "Mini Hotel",
        "Uzoq muddatli yashash hostellari",
        "Kunlik hostellar",
        "Business Hostel",
        "Backpacker Hostel",
        "Shahar markazidagi hostellar",
        "Aeroportga yaqin hostellar",
    ]


def _mexmonxona_tree() -> list[Node]:
    return [
        "3 yulduzli mehmonxonalar",
        "4 yulduzli mehmonxonalar",
        "5 yulduzli mehmonxonalar",
        "Boutique Hotel",
        ("Business Hotel", ["Konferensiya zallari", "Coworking zonalari", "Biznes xizmatlariga ega mehmonxonalar"]),
        ("Resort Hotel", ["Beach Resort", "Mountain Resort", "Wellness Resort", "Family Resort"]),
        "Apart Hotel",
        "Family Hotel",
        "Spa Hotel",
        "Airport Hotel",
        "Mountain Hotel",
        "City Hotel",
        ("Luxury Hotel", ["Presidential Suite", "Royal Suite", "Deluxe Room", "Executive Room"]),
        "Eco Hotel",
    ]


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
    for code, name, path, tree in [
        ("kop-qavatli-binolar", "Ko'p qavatli binolar", "/kop-qavatli-binolar", _kop_qavatli_binolar_tree()),
        ("kotejlar", "Kotejlar", "/kotejlar", _kotejlar_tree()),
        ("hovlilar", "Hovlilar", "/hovlilar", _hovlilar_tree()),
        ("noturar-binolar", "Noturar binolar", "/noturar-binolar", _noturar_binolar_tree()),
        ("dala-hovlilar", "Dala hovlilar", "/dala-hovlilar", _dala_hovlilar_tree()),
    ]:
        head_id = await _seed_category(
            use_cases, repo, code=code, name=name, path=path,
            parent_category_id=None, form_definition_id=re_form_id, now=now,
        )
        await _seed_subtree(
            use_cases, repo, tree, parent_id=head_id, parent_path=path,
            form_definition_id=re_form_id, now=now,
        )

    # -- Land.
    land_form_id = await _seed_form(
        use_cases, repo, code="bosh-yer-form", name="Bo'sh yer", fields=_land_fields(), now=now
    )
    bosh_yerlar_head_id = await _seed_category(
        use_cases, repo, code="bosh-yerlar", name="Bo'sh yerlar", path="/bosh-yerlar",
        parent_category_id=None, form_definition_id=land_form_id, now=now,
    )
    await _seed_subtree(
        use_cases, repo, _bosh_yerlar_tree(), parent_id=bosh_yerlar_head_id, parent_path="/bosh-yerlar",
        form_definition_id=land_form_id, now=now,
    )

    # -- Goods (physical-unit sales).
    goods_form_id = await _seed_form(
        use_cases, repo, code="mahsulot-form", name="Mahsulot", fields=_goods_fields(), now=now
    )
    for code, name, path, tree in [
        ("qurilish-materiallari", "Qurilish materiallari", "/qurilish-materiallari", _qurilish_materiallari_tree()),
        ("maishiy-texnikalar", "Maishiy texnikalar", "/maishiy-texnikalar", _maishiy_texnikalar_tree()),
        ("uy-bezaklari", "Uy bezaklari", "/uy-bezaklari", _uy_bezaklari_tree()),
        ("uniforma-va-maxsus-kiyimlar", "Uniforma va maxsus kiyimlar", "/uniforma-va-maxsus-kiyimlar", _uniforma_tree()),
    ]:
        head_id = await _seed_category(
            use_cases, repo, code=code, name=name, path=path,
            parent_category_id=None, form_definition_id=goods_form_id, now=now,
            listing_kind="GOODS",
        )
        await _seed_subtree(
            use_cases, repo, tree, parent_id=head_id, parent_path=path,
            form_definition_id=goods_form_id, now=now, listing_kind="GOODS",
        )

    # -- Hospitality.
    hosp_form_id = await _seed_form(
        use_cases, repo, code="mehmonxona-form", name="Mehmonxona/Hostel", fields=_hospitality_fields(), now=now
    )
    for code, name, path, tree in [
        ("hostel", "Hostel", "/hostel", _hostel_tree()),
        ("mexmonxona", "Mexmonxona", "/mexmonxona", _mexmonxona_tree()),
    ]:
        head_id = await _seed_category(
            use_cases, repo, code=code, name=name, path=path,
            parent_category_id=None, form_definition_id=hosp_form_id, now=now,
            listing_kind="VENUE",
        )
        await _seed_subtree(
            use_cases, repo, tree, parent_id=head_id, parent_path=path,
            form_definition_id=hosp_form_id, now=now, listing_kind="VENUE",
        )

    # -- Business directory (showrooms, not units).
    business_form_id = await _seed_form(
        use_cases, repo, code="biznes-korxona-form", name="Biznes/korxona", fields=_business_fields(), now=now
    )
    mebel_salonlari_head_id = await _seed_category(
        use_cases, repo, code="mebel-salonlari", name="Mebel salonlari", path="/mebel-salonlari",
        parent_category_id=None, form_definition_id=business_form_id, now=now,
        listing_kind="GOODS",
    )
    await _seed_subtree(
        use_cases, repo, _mebel_salonlari_tree(), parent_id=mebel_salonlari_head_id, parent_path="/mebel-salonlari",
        form_definition_id=business_form_id, now=now, listing_kind="GOODS",
    )

    # -- Recreation venues (new, per this session's request).
    venue_form_id = await _seed_form(
        use_cases, repo, code="dam-olish-maskani-form", name="Dam olish maskani", fields=_venue_fields(), now=now
    )
    dam_olish_head_id = await _seed_category(
        use_cases, repo, code="dam-olish-maskanlari", name="Dam olish maskanlari", path="/dam-olish-maskanlari",
        parent_category_id=None, form_definition_id=venue_form_id, now=now,
        listing_kind="VENUE",
    )
    await _seed_subtree(
        use_cases, repo, _dam_olish_maskanlari_tree(), parent_id=dam_olish_head_id, parent_path="/dam-olish-maskanlari",
        form_definition_id=venue_form_id, now=now, listing_kind="VENUE",
    )

    # -- Landshaft dizayni: a design SERVICE, not goods -- the base CV shape, no trade extras.
    landshaft_form_id = await _seed_form(
        use_cases, repo, code="landshaft-xizmati-form", name="Landshaft dizayni xizmati",
        fields=_service_cv_fields(), now=now,
    )
    landshaft_head_id = await _seed_category(
        use_cases, repo, code="landshaft-dizayni", name="Landshaft dizayni", path="/landshaft-dizayni",
        parent_category_id=None, form_definition_id=landshaft_form_id, now=now,
        listing_kind="SERVICE",
    )
    await _seed_subtree(
        use_cases, repo, _landshaft_tree(), parent_id=landshaft_head_id, parent_path="/landshaft-dizayni",
        form_definition_id=landshaft_form_id, now=now, listing_kind="SERVICE",
    )

    # -- Ish o'rni (job postings) -- same CV shape; here `specialization`/`experience_years` read
    # as the employer's requirement rather than the applicant's own.
    ish_orni_form_id = await _seed_form(
        use_cases, repo, code="ish-orni-form", name="Ish o'rni", fields=_service_cv_fields(), now=now
    )
    ish_orni_head_id = await _seed_category(
        use_cases, repo, code="ish-orni", name="Ish o'rni", path="/ish-orni",
        parent_category_id=None, form_definition_id=ish_orni_form_id, now=now,
        listing_kind="SERVICE",
    )
    await _seed_subtree(
        use_cases, repo, _ish_orni_tree(), parent_id=ish_orni_head_id, parent_path="/ish-orni",
        form_definition_id=ish_orni_form_id, now=now, listing_kind="SERVICE",
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
        listing_kind="SERVICE",
    )
    await _seed_subtree(
        use_cases, repo, _xizmat_korsatish_tree(), parent_id=services_head_id, parent_path="/xizmat-korsatish",
        form_definition_id=services_form_id, now=now, listing_kind="SERVICE",
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
        listing_kind="SERVICE",
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
        listing_kind="SERVICE",
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
        listing_kind="SERVICE",
    )

    # -- Every top-level category gets its own themed hero image/tagline/accent color (Task:
    # category mini-platform redesign) -- idempotent, safe to re-run every deploy.
    for code, theme in _TOP_LEVEL_CATEGORY_HERO_THEMES.items():
        await _backfill_category_theme(
            use_cases, repo, code=code,
            hero_image_url=theme["heroImageUrl"], hero_tagline=theme["heroTagline"],
            accent_color=theme["accentColor"], now=now,
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
                furniture_head_id = await _seed_furniture_category(
                    use_cases, repo, form_definition_id=furniture_form_id, now=now
                )
                await _seed_subtree(
                    use_cases, repo, _mebel_materiallari_tree(), parent_id=furniture_head_id,
                    parent_path="/mebel-materiallari", form_definition_id=furniture_form_id, now=now,
                    listing_kind="GOODS",
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
