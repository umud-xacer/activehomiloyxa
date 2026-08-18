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
import itertools
import re
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from backbone.outbox import OutboxWriter
from backbone.persistence import (
    make_engine,
    make_session_factory,
    redis_url,
    session_scope,
)
from configuration.application import ConfigurationUseCases
from configuration.application.exceptions import GateFailedError
from configuration.domain import (
    SUPER_ADMIN_APPROVAL_ENTITIES,
    ConfigEntityType,
    DuplicateCodeError,
)
from configuration.domain.whitelist import (
    PERMISSION_KEYS,
    WhitelistRegistry,
    is_valid_owner_panel_slug,
)
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import (
    SqlalchemyConfigHeadRepository,
)

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
    repo: SqlalchemyConfigHeadRepository,
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
        await _backfill_role_permission_keys(
            use_cases,
            repo,
            code=code,
            role_name=role_name,
            permission_keys=permission_keys,
            now=now,
        )
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


async def _backfill_role_permission_keys(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    role_name: str,
    permission_keys: list[str],
    now: datetime,
) -> None:
    """Self-heal for a role definition seeded before `PERMISSION_KEYS` (whitelist.py) gained a
    new entry -- `_seed_role`'s own `create_draft` only ever runs once per code (`DuplicateCodeError`
    short-circuits every later deploy), so without this, a permission key added to the whitelist
    after go-live would sit in `PERMISSION_KEYS`/`_super_admin_permission_keys()` forever without
    ever reaching the actually-published role version an existing account's `RoleAssignment` is
    pinned to (Config Framework Sec 7.2: "role assignments pin identity + role version" -- no live
    pointer to "current"). Same publish-a-new-version-only-if-changed pattern as
    `_backfill_category_theme`, safe/cheap to re-run on every deploy."""
    head = await repo.get_head_by_code(ConfigEntityType.ROLE_DEFINITION, code)
    if head is None or head.current_version_id is None:
        return
    current = await repo.get_version(
        ConfigEntityType.ROLE_DEFINITION, head.id, head.current_version_id
    )
    if current is None:
        return
    if sorted(current.definition_document.get("permission_keys") or []) == sorted(permission_keys):
        return

    new_document = {**current.definition_document, "permission_keys": permission_keys}
    new_version = await use_cases.create_version_draft(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    bootstrap_authority = frozenset(_super_admin_permission_keys())
    step1 = await use_cases.publish(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=bootstrap_authority,
        approval_note=f"seed: backfill {role_name} permission_keys",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.ROLE_DEFINITION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=bootstrap_authority,
            approval_note=f"seed: backfill {role_name} permission_keys approval",
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
            "login_lockout.max_attempts": 4,
            "login_lockout.block_minutes": 15,
            "stats.cities": 380,
            "stats.partners": 12500,
            "stats.satisfaction_percent": 98,
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


_PLATFORM_SETTINGS_ADDITIVE_DEFAULTS: dict[str, object] = {
    "login_lockout.max_attempts": 4,
    "login_lockout.block_minutes": 15,
    "stats.cities": 380,
    "stats.partners": 12500,
    "stats.satisfaction_percent": 98,
}
"""Settings keys introduced by a task after `_seed_platform_settings` last ran against a given
database. That function's own `DuplicateCodeError` early-return means it never touches an
already-existing `platform-settings-global` head again, so a key added here without also being
backfilled would read back to `IdentityPlatformSettings`'s hardcoded fallback default forever on
any environment seeded before this task -- works, but silently never becomes admin-editable
(there's nothing in the published settings dict for the owner-admin panel's future settings UI to
show or a script to publish an override for). See `_backfill_platform_settings_defaults` below."""


async def _backfill_platform_settings_defaults(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    now: datetime,
) -> None:
    """Adds any `_PLATFORM_SETTINGS_ADDITIVE_DEFAULTS` key missing from the published
    `platform-settings-global` version. Deliberately additive-only -- an already-present key is
    left exactly as published, even if its value differs from the table here, so an admin's own
    in-panel edit (e.g. the owner-admin panel's `admin.owner_panel_slug`, changeable at will per
    its own task) is never silently reverted by a later deploy. Unlike `_backfill_category_theme`
    below (which intentionally always overwrites back to its table, since category hero content
    has no "admin edits it live and expects it to stick" use case), this one must not -- login
    lockout's own thresholds are exactly that kind of live-editable setting.

    Also sanitizes `admin.owner_panel_slug` if the currently-stored value would fail
    `check_settings_key`'s gate validation (real incident: an admin set it to "boss" before that
    validation existed; the read-side self-heal in `interfaces/routers.py` means the panel itself
    was never actually broken by this, but the stored value stayed invalid -- and the FIRST
    unrelated settings republish after the validation was added, i.e. this very function adding
    `login_lockout.*`, failed the whole seed run trying to carry it forward unchanged. Confirmed
    live.). Falls back to the owner-admin default, matching `interfaces/routers.py`'s own
    self-heal exactly, so this is a no-op from the panel's point of view -- just makes the
    correction permanent instead of read-time-only."""
    head = await repo.get_head_by_code(
        ConfigEntityType.PLATFORM_SETTINGS, "platform-settings-global"
    )
    if head is None or head.current_version_id is None:
        return
    current = await repo.get_version(
        ConfigEntityType.PLATFORM_SETTINGS, head.id, head.current_version_id
    )
    if current is None:
        return
    current_settings = dict(current.definition_document.get("settings") or {})
    missing = {
        k: v for k, v in _PLATFORM_SETTINGS_ADDITIVE_DEFAULTS.items() if k not in current_settings
    }
    stale_slug = current_settings.get("admin.owner_panel_slug")
    slug_fix = (
        {}
        if stale_slug is None or is_valid_owner_panel_slug(stale_slug)
        else {"admin.owner_panel_slug": "owner-admin"}
    )
    if not missing and not slug_fix:
        return

    new_document = {
        **current.definition_document,
        "settings": {**current_settings, **missing, **slug_fix},
    }
    new_version = await use_cases.create_version_draft(
        ConfigEntityType.PLATFORM_SETTINGS,
        head.id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.PLATFORM_SETTINGS.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.PLATFORM_SETTINGS.value)
    step1 = await use_cases.publish(
        ConfigEntityType.PLATFORM_SETTINGS,
        head.id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: backfill missing platform settings defaults",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.PLATFORM_SETTINGS,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: backfill missing platform settings defaults approval",
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
        if existing is None:
            raise RuntimeError(f"seed marker {code!r} vanished between check and lookup") from None
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
    display_order: int = 1,
) -> UUID:
    """The "Mebel materiallari" (Furniture) top-level category, bound to the form above -- the
    exact path the frontend already hardcodes (`CategoryCarousel.tsx`'s `ICON_BY_PATH["/mebel-
    materiallari"]` and the `/furniture` route's `CATEGORY_PATH`), so both the homepage category
    rail and the dedicated furniture page resolve to real data once this has run. Returns the
    head id either way (fresh or pre-existing) so callers can seed a subtree under it.

    `display_order` defaults to 1 (this category is seeded first, before `_seed_catalog_taxonomy`'s
    own 18 -- see `run_seed`'s call order) -- part of the same top-level sibling group as those, so
    it needs a value from that same sequence, not its own separate one."""
    code = "mebel-materiallari"
    definition = {
        "descriptor": {
            "name": {
                "uz_latn": "Mebel materiallari",
                "ru": "Мебель",
                "en": "Furniture",
            },
            "metadata": {"listingKind": "GOODS"},
            "display_order": display_order,
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
        if existing is None:
            raise RuntimeError(f"seed marker {code!r} vanished between check and lookup") from None
        await _backfill_listing_kind(
            use_cases,
            repo,
            head_id=existing.id,
            current_version_id=existing.current_version_id,
            listing_kind="GOODS",
            now=now,
        )
        await _backfill_display_order(
            use_cases,
            repo,
            head_id=existing.id,
            current_version_id=existing.current_version_id,
            display_order=display_order,
            now=now,
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
        _field(
            "area_sotix",
            "asosiy",
            "Maydon (sotix)",
            "number",
            required=True,
            facet=True,
            order=1,
        ),
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
        _field(
            "has_documents",
            "asosiy",
            "Hujjatlari bor",
            "boolean",
            facet=True,
            order=3,
            default=False,
        ),
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
        _field(
            "delivery_available",
            "asosiy",
            "Yetkazib berish mavjud",
            "boolean",
            facet=True,
            order=4,
            default=False,
        ),
    ]


def _hospitality_fields() -> list[dict[str, object]]:
    return [
        _field(
            "room_capacity",
            "asosiy",
            "Xona sig'imi (kishi)",
            "number",
            facet=True,
            order=1,
        ),
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
        _field(
            "experience_years",
            "asosiy",
            "Tajriba (yil)",
            "number",
            required=True,
            facet=True,
            order=1,
        ),
        _field("specialization", "asosiy", "Mutaxassislik", "text", facet=True, order=2),
        _field(
            "service_regions",
            "asosiy",
            "Xizmat ko'rsatiladigan hududlar",
            "text",
            order=3,
        ),
        _field(
            "rate_type",
            "asosiy",
            "Narx turi",
            "select",
            facet=True,
            order=4,
            options=[
                ("hourly", "Soatlik"),
                ("daily", "Kunlik"),
                ("per_job", "Ish uchun"),
            ],
        ),
        _field(
            "available_now",
            "asosiy",
            "Hozir band emas",
            "boolean",
            facet=True,
            order=5,
            default=True,
        ),
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
        if existing is None:
            raise RuntimeError(f"seed marker {code!r} vanished between check and lookup") from None
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
    display_order: int = 0,
) -> UUID:
    """Generic `Category` seeder. Always returns the head id (creating it, or looking it up by
    code if already seeded) -- unlike a bare "skip on duplicate", child categories below need a
    real parent id back even on a re-run against an already-seeded database.

    `listing_kind` (PROPERTY/GOODS/SERVICE/VENUE) lands in `descriptor.metadata.listingKind` --
    the sanctioned inert key-value extension slot (`content.py`'s `ConfigDescriptor.metadata`
    docstring) -- which `lib/listing-kind.ts#listingKindOf` reads to pick a category's rendering
    shape. Omit (None) for the PROPERTY default (real estate), matching the frontend's own
    documented fallback.

    `display_order` (1-based, scoped to this category's own sibling group -- every direct caller
    below numbers each sibling list itself; `_seed_subtree` does the same for every subtree it
    recurses through) fixes the "homepage category chips reshuffle on every refresh" bug:
    `CategoryReadUseCases.list_categories` sorts on this field precisely because
    `RedisSnapshotCache.list_current`'s own Redis-SET-backed iteration order is NOT stable across
    calls. Left at the domain's own default (0) only intentionally -- every caller here passes a
    real value."""
    descriptor: dict[str, object] = {"name": {"uz_latn": name}, "display_order": display_order}
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
        if existing is None:
            raise RuntimeError(f"seed marker {code!r} vanished between check and lookup") from None
        await _backfill_listing_kind(
            use_cases,
            repo,
            head_id=existing.id,
            current_version_id=existing.current_version_id,
            listing_kind=listing_kind,
            now=now,
        )
        await _backfill_display_order(
            use_cases,
            repo,
            head_id=existing.id,
            current_version_id=existing.current_version_id,
            display_order=display_order,
            now=now,
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
        ConfigEntityType.CATEGORY,
        head_id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY,
        head_id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: backfill listingKind metadata",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            head_id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: backfill listingKind metadata approval",
            now=now,
        )


async def _backfill_display_order(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    head_id: UUID,
    current_version_id: UUID | None,
    display_order: int,
    now: datetime,
) -> None:
    """Self-heal for a category seeded before `display_order` existed (every category already in
    production has it stuck at the domain default, 0) -- same pattern as `_backfill_listing_kind`
    just above: publish a new version only when the stored value doesn't already match, so this
    settles to a no-op once a deploy has caught every category up."""
    if current_version_id is None:
        return
    current = await repo.get_version(ConfigEntityType.CATEGORY, head_id, current_version_id)
    if current is None:
        return
    current_descriptor = dict(current.definition_document.get("descriptor") or {})
    if current_descriptor.get("display_order") == display_order:
        return

    new_descriptor = {**current_descriptor, "display_order": display_order}
    new_document = {**current.definition_document, "descriptor": new_descriptor}

    new_version = await use_cases.create_version_draft(
        ConfigEntityType.CATEGORY,
        head_id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY,
        head_id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: backfill display_order",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            head_id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: backfill display_order approval",
            now=now,
        )


_TOP_LEVEL_CATEGORY_HERO_THEMES: dict[str, dict[str, str]] = {
    "qurilish-materiallari": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/5/52/-2022-03-16_Construction_of_a_brick_and_flint_house%2C_Northrepps%2C_England_%281%29.JPG",
        "heroTagline": "Har bir qurilish uchun ishonchli materiallar",
        "accentColor": "#EA580C",
    },
    "ish-orni": {
        "heroImageUrl": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Ko'chmas mulk va qurilish sohasidagi eng yaxshi ish o'rinlari",
        "accentColor": "#2563EB",
    },
    "dala-hovlilar": {
        "heroImageUrl": "https://images.unsplash.com/photo-1449158743715-0a90ebb6d2d8?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Shahar shovqinidan uzoqlashing, tabiat qo'ynida dam oling",
        "accentColor": "#16A34A",
    },
    "uniforma-va-maxsus-kiyimlar": {
        "heroImageUrl": "https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Professional ish uchun ishonchli himoya kiyimlari",
        "accentColor": "#F59E0B",
    },
    "mebel-materiallari": {
        "heroImageUrl": "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Mebel yaratish uchun sifatli materiallar",
        "accentColor": "#92400E",
    },
    "dam-olish-maskanlari": {
        "heroImageUrl": "https://images.unsplash.com/photo-1519046904884-53103b34b206?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Eng yaxshi dam olish maskanlarini shu yerdan toping",
        "accentColor": "#0D9488",
    },
    "hovlilar": {
        "heroImageUrl": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "O'zingizni uyda his qiladigan hovlingizni toping",
        "accentColor": "#059669",
    },
    "landshaft-dizayni": {
        "heroImageUrl": "https://images.unsplash.com/photo-1558904541-efa843a96f01?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Hovlingizni professional dizayn bilan bezating",
        "accentColor": "#22C55E",
    },
    "kop-qavatli-binolar": {
        "heroImageUrl": "https://images.unsplash.com/photo-1460317442991-0ec209397118?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Zamonaviy shahar hayoti uchun yangi uy",
        "accentColor": "#334155",
    },
    "bosh-yerlar": {
        "heroImageUrl": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Kelajakdagi qurilishingiz uchun ishonchli yer",
        "accentColor": "#B45309",
    },
    "mebel-salonlari": {
        "heroImageUrl": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Uyingiz uchun premium mebel kolleksiyalari",
        "accentColor": "#7C3AED",
    },
    "noturar-binolar": {
        "heroImageUrl": "https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Biznesingiz uchun professional makon",
        "accentColor": "#1E3A8A",
    },
    "uy-bezaklari": {
        "heroImageUrl": "https://live.staticflickr.com/8471/8394526520_f43e5632b1_b.jpg",
        "heroTagline": "Uyingizga did va zavq qo'shing",
        "accentColor": "#DB2777",
    },
    "hostel": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/6/68/Hostel_Porto_Portugal.jpg",
        "heroTagline": "Qulay va arzon tunash joylarini toping",
        "accentColor": "#0891B2",
    },
    "mexmonxona": {
        "heroImageUrl": "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Hashamat va qulaylik bir joyda",
        "accentColor": "#CA8A04",
    },
    "xizmat-korsatish": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/4/4a/Electrician_-_Flickr_-_garryknight.jpg",
        "heroTagline": "Ishonchli ustalar va tezkor xizmat",
        "accentColor": "#DC2626",
    },
    "kotejlar": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/2/2a/Large_chalet_house%2C_Waimes%2C_2013.jpg",
        "heroTagline": "Tabiat qo'ynidagi hashamatli dam olish",
        "accentColor": "#15803D",
    },
    "maishiy-texnikalar": {
        "heroImageUrl": "https://images.unsplash.com/photo-1556909212-d5b604d0c90d?w=1600&q=80&auto=format&fit=crop",
        "heroTagline": "Uyingiz uchun zamonaviy texnikalar",
        "accentColor": "#0284C7",
    },
}
"""One themed hero per top-level category (Task: category mini-platform redesign) -- images from
`images.unsplash.com/photo-<id>` (same keyless direct-CDN pattern already used for demo listing
photos in `seed_demo_listings.py`). `accentColor` values are spread across
the palette so no two top-level categories read as visually identical. Consumed by
`_backfill_category_theme` below, which is the only thing that ever reads this table.

Previously these pointed at `loremflickr.com/cache/resized/...jpg` -- URLs hand-pinned to a
specific redirect target to skip loremflickr's `/{w}/{h}/{tags}` redirector hop (~0.9-1.4s
measured). That cache entry turned out not to be permanent: loremflickr evicted it and every one
of the 18 URLs started 404ing, which is exactly the failure this docstring used to warn about --
reported by the user as "kategoriyalarni orqasida rasmlar turishi kerak edi, kirganda ko'rinmay
qolgan" (category hero backgrounds should be there, went invisible after entering). Unsplash's
`/photo-<id>` path is the CDN's permanent asset address, not a resolved-once cache of a redirect,
so it doesn't carry the same eviction risk -- confirmed live (HTTP 200) for all 18 URLs below
before pinning them here. If a photo ever does go missing, PageHeader's plain gradient is still
the fallback, so this stays a safe optimization either way."""


"""Every non-top-level category also gets a themed hero image now (Task: subcategory hero
images, 518 categories). Generated OFFLINE (not at seed-run time) from each category's own Uzbek
name -- translated word-by-word via a small curated dictionary, falling back to its top-level
ancestor's theme words when the leaf name alone translates to nothing useful -- then hand-reviewed
across all 518 entries for tag quality before being pasted in here as plain data, same as
`_TOP_LEVEL_CATEGORY_HERO_THEMES` above.

Uses loremflickr's LIVE tag redirector (`loremflickr.com/1600/900/{tags}`) directly as the stored
`heroImageUrl` -- deliberately NOT a pre-resolved/pinned cache URL. That is exactly the mistake
that broke all 18 top-level images earlier (see this file's docstring above
`_backfill_category_theme`): a hand-pinned resolved-cache target got evicted by loremflickr and
404'd everywhere at once. The redirector re-resolves fresh on every request instead, so there is
no equivalent eviction risk here -- the tradeoff is one extra redirect hop per image load (~1s)
that Unsplash's permanent `/photo-<id>` addresses don't pay, acceptable for the long tail of
subcategory pages this backs.

No `accentColor` here, matching `_backfill_category_theme`'s own documented convention for
depth>1 categories: they inherit the nearest themed ancestor's color via `resolveAccentColor`'s
ancestor walk (`lib/listing-kind.ts`) rather than each getting its own."""
_SUBCATEGORY_HERO_THEMES: dict[str, dict[str, str]] = {
    "bosh-yerlar-auksion-orqali-sotilayotgan-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/auction,for,sale",
        "heroTagline": "Auksion orqali sotilayotgan yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-dala-va-bog-yerlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/field,farm,garden",
        "heroTagline": "Dala va bog' yerlari bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-fermer-xojaligi-yerlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/farm,land,plot",
        "heroTagline": "Fermer xo'jaligi yerlari bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-investitsiya-uchun-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/investment,land,plot",
        "heroTagline": "Investitsiya uchun yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-kommunikatsiyaga-tayyor-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/utilities,ready,land",
        "heroTagline": "Kommunikatsiyaga tayyor yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-kottej-shaharchalari-uchun-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cottage,town,land",
        "heroTagline": "Kottej shaharchalari uchun yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-qishloq-xojaligi-yerlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/village,farm,land",
        "heroTagline": "Qishloq xo'jaligi yerlari bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-qishloq-xojaligi-yerlari-bogdorchilik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/gardening,land",
        "heroTagline": "Bog'dorchilik bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-qishloq-xojaligi-yerlari-chorvachilik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cattle,farm",
        "heroTagline": "Chorvachilik bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-qishloq-xojaligi-yerlari-dehqonchilik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/farming,land",
        "heroTagline": "Dehqonchilik bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-qishloq-xojaligi-yerlari-issiqxona": {
        "heroImageUrl": "https://loremflickr.com/1600/900/greenhouse,land",
        "heroTagline": "Issiqxona bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-sanoat-hududlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/industrial,zone",
        "heroTagline": "Sanoat hududlari bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-shahar-ichidagi-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/city,downtown,land",
        "heroTagline": "Shahar ichidagi yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-shahar-tashqarisidagi-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/city,countryside,land",
        "heroTagline": "Shahar tashqarisidagi yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-tijorat-maqsadidagi-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/commercial,land,plot",
        "heroTagline": "Tijorat maqsadidagi yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-tijorat-maqsadidagi-yerlar-mehmonxona-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hotel,land",
        "heroTagline": "Mehmonxona uchun bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-tijorat-maqsadidagi-yerlar-ofis-binosi-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,building",
        "heroTagline": "Ofis binosi uchun bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-tijorat-maqsadidagi-yerlar-omborxona-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/warehouse,land",
        "heroTagline": "Omborxona uchun bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-tijorat-maqsadidagi-yerlar-restoran-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/restaurant,land",
        "heroTagline": "Restoran uchun bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-tijorat-maqsadidagi-yerlar-savdo-markazi-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/shopping,center",
        "heroTagline": "Savdo markazi uchun bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-turar-joy-qurish-uchun-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/residential,housing,construction",
        "heroTagline": "Turar joy qurish uchun yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-turar-joy-qurish-uchun-yerlar-10-sotixdan-katta": {
        "heroImageUrl": "https://loremflickr.com/1600/900/large,land",
        "heroTagline": "10 sotixdan katta bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-turar-joy-qurish-uchun-yerlar-2-4-sotix": {
        "heroImageUrl": "https://loremflickr.com/1600/900/land,plot",
        "heroTagline": "2-4 sotix bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-turar-joy-qurish-uchun-yerlar-2-sotixgacha": {
        "heroImageUrl": "https://loremflickr.com/1600/900/land,plot",
        "heroTagline": "2 sotixgacha bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-turar-joy-qurish-uchun-yerlar-4-6-sotix": {
        "heroImageUrl": "https://loremflickr.com/1600/900/land,plot",
        "heroTagline": "4-6 sotix bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-turar-joy-qurish-uchun-yerlar-6-10-sotix": {
        "heroImageUrl": "https://loremflickr.com/1600/900/land,plot",
        "heroTagline": "6-10 sotix bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-yangi-massivlardagi-yerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/new,district,land",
        "heroTagline": "Yangi massivlardagi yerlar bo'yicha eng yaxshi takliflar",
    },
    "bosh-yerlar-yirik-loyiha-uchun-yer-maydonlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/large,project,land",
        "heroTagline": "Yirik loyiha uchun yer maydonlari bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-barbekyu-va-yozgi-oshxonali-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/barbecue,summer,kitchen",
        "heroTagline": "Barbekyu va yozgi oshxonali hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-haftalik-va-oylik-ijara": {
        "heroImageUrl": "https://loremflickr.com/1600/900/weekly,monthly,rental",
        "heroTagline": "Haftalik va oylik ijara bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-hovuzli-dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pool,field,farm",
        "heroTagline": "Hovuzli dala hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-hovuzli-dala-hovlilar-bolalar-hovuzi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kids,children,pool",
        "heroTagline": "Bolalar hovuzi bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-hovuzli-dala-hovlilar-isitiladigan-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/heated,pool",
        "heroTagline": "Isitiladigan hovuz bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-hovuzli-dala-hovlilar-ochiq-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/open,outdoor,pool",
        "heroTagline": "Ochiq hovuz bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-hovuzli-dala-hovlilar-premium-spa-zonali-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,spa",
        "heroTagline": "Premium SPA zonali hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-hovuzli-dala-hovlilar-yopiq-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/indoor,pool",
        "heroTagline": "Yopiq hovuz bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-ijaraga-beriladigan-dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/rental,field,farm",
        "heroTagline": "Ijaraga beriladigan dala hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-investitsiya-uchun-dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/investment,field,farm",
        "heroTagline": "Investitsiya uchun dala hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-kol-yoki-daryo-boyidagi-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lake,river,riverside",
        "heroTagline": "Ko'l yoki daryo bo'yidagi hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-kunlik-ijara": {
        "heroImageUrl": "https://loremflickr.com/1600/900/daily,rental",
        "heroTagline": "Kunlik ijara bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-kunlik-ijara-2-kishilik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/country,house",
        "heroTagline": "2 kishilik bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-kunlik-ijara-bayram-tadbirlari-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/festive,event",
        "heroTagline": "Bayram tadbirlari uchun bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-kunlik-ijara-katta-guruhlar-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/large,group",
        "heroTagline": "Katta guruhlar uchun bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-kunlik-ijara-korporativ-dam-olish-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/corporate,leisure,resort",
        "heroTagline": "Korporativ dam olish uchun bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-kunlik-ijara-oilaviy": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,country",
        "heroTagline": "Oilaviy bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-oilaviy-dam-olish-hovlilari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,leisure,resort",
        "heroTagline": "Oilaviy dam olish hovlilari bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-premium-villalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,villa",
        "heroTagline": "Premium villalar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-premium-villalar-panoramali-villa": {
        "heroImageUrl": "https://loremflickr.com/1600/900/panoramic,villa",
        "heroTagline": "Panoramali villa bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-premium-villalar-smart-home": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home",
        "heroTagline": "Smart Home bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-premium-villalar-vip-villa": {
        "heroImageUrl": "https://loremflickr.com/1600/900/vip,villa",
        "heroTagline": "VIP villa bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-premium-villalar-zamonaviy-dizayndagi-villalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/modern,design,villa",
        "heroTagline": "Zamonaviy dizayndagi villalar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-sotuvdagi-dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/for,sale,field",
        "heroTagline": "Sotuvdagi dala hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-tog-hududidagi-dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mountain,zone,field",
        "heroTagline": "Tog' hududidagi dala hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dala-hovlilar-yangi-qurilgan-dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/new,built,field",
        "heroTagline": "Yangi qurilgan dala hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-bolalar-kongilochar-markazlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kids,children,entertainment",
        "heroTagline": "Bolalar ko'ngilochar markazlari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-dala-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/field,farm,villa",
        "heroTagline": "Dala hovlilar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-hovuz-va-akvaparklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pool,waterpark",
        "heroTagline": "Hovuz va akvaparklar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-hovuz-va-akvaparklar-bolalar-akvaparki": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kids,children,waterpark",
        "heroTagline": "Bolalar akvaparki bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-hovuz-va-akvaparklar-family-zonalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,zone",
        "heroTagline": "Family zonalari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-hovuz-va-akvaparklar-ochiq-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/open,outdoor,pool",
        "heroTagline": "Ochiq hovuz bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-hovuz-va-akvaparklar-vip-zonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/vip,zone",
        "heroTagline": "VIP zonalar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-hovuz-va-akvaparklar-yopiq-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/indoor,pool",
        "heroTagline": "Yopiq hovuz bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-kol-va-daryo-boyidagi-maskanlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lake,river,riverside",
        "heroTagline": "Ko'l va daryo bo'yidagi maskanlar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-kottejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cottage,resort",
        "heroTagline": "Kottejlar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-kurort-va-sanatoriyalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/resort,sanatorium",
        "heroTagline": "Kurort va sanatoriyalar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-mehmonxonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hotel,resort",
        "heroTagline": "Mehmonxonalar bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-mehmonxonalar-3-yulduzli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/star,hotel",
        "heroTagline": "3 yulduzli bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-mehmonxonalar-4-yulduzli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/star,hotel",
        "heroTagline": "4 yulduzli bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-mehmonxonalar-5-yulduzli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/star,hotel",
        "heroTagline": "5 yulduzli bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-mehmonxonalar-boutique-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/boutique,hotel",
        "heroTagline": "Boutique Hotel bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-mehmonxonalar-business-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/business,hotel",
        "heroTagline": "Business Hotel bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-mehmonxonalar-family-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,hotel",
        "heroTagline": "Family Hotel bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-oilaviy-dam-olish-zonalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,leisure,resort",
        "heroTagline": "Oilaviy dam olish zonalari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-piknik-va-camping-hududlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/picnic,camping,zone",
        "heroTagline": "Piknik va Camping hududlari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-restoran-va-kafe-zonalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/restaurant,cafe,zone",
        "heroTagline": "Restoran va kafe zonalari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-sarguzasht-va-ekstremal-dam-olish-maskanlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/adventure,extreme,leisure",
        "heroTagline": "Sarguzasht va ekstremal dam olish maskanlari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-spa-va-wellness-markazlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/spa,wellness,centers",
        "heroTagline": "SPA va Wellness markazlari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-spa-va-wellness-markazlari-fitnes": {
        "heroImageUrl": "https://loremflickr.com/1600/900/fitness,gym",
        "heroTagline": "Fitnes bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-spa-va-wellness-markazlari-hammom": {
        "heroImageUrl": "https://loremflickr.com/1600/900/spa,bath",
        "heroTagline": "Hammom bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-spa-va-wellness-markazlari-massaj": {
        "heroImageUrl": "https://loremflickr.com/1600/900/massage,spa",
        "heroTagline": "Massaj bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-spa-va-wellness-markazlari-sauna": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sauna,resort",
        "heroTagline": "Sauna bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-spa-va-wellness-markazlari-soglomlashtirish-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/wellness,service",
        "heroTagline": "Sog'lomlashtirish xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-spa-va-wellness-markazlari-termal-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/thermal,pool",
        "heroTagline": "Termal hovuz bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-tog-dam-olish-maskanlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mountain,leisure,resort",
        "heroTagline": "Tog' dam olish maskanlari bo'yicha eng yaxshi takliflar",
    },
    "dam-olish-maskanlari-villalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/villa,resort",
        "heroTagline": "Villalar bo'yicha eng yaxshi takliflar",
    },
    "mashina-haydovchisi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/car,truck,driver",
        "heroTagline": "Mashina haydovchisi bo'yicha eng yaxshi takliflar",
    },
    "hostel-aeroportga-yaqin-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/airport,near,hostel",
        "heroTagline": "Aeroportga yaqin hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-ayollar-hosteli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/women,hostel",
        "heroTagline": "Ayollar hosteli bo'yicha eng yaxshi takliflar",
    },
    "hostel-backpacker-hostel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/backpacker,hostel",
        "heroTagline": "Backpacker Hostel bo'yicha eng yaxshi takliflar",
    },
    "hostel-business-hostel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/business,hostel",
        "heroTagline": "Business Hostel bo'yicha eng yaxshi takliflar",
    },
    "hostel-erkaklar-hosteli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/men,hostel",
        "heroTagline": "Erkaklar hosteli bo'yicha eng yaxshi takliflar",
    },
    "hostel-guest-house": {
        "heroImageUrl": "https://loremflickr.com/1600/900/guest,house",
        "heroTagline": "Guest House bo'yicha eng yaxshi takliflar",
    },
    "hostel-kapsula-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/capsule,pod,hostel",
        "heroTagline": "Kapsula hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-kapsula-hostellar-premium-kapsula": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,capsule",
        "heroTagline": "Premium kapsula bo'yicha eng yaxshi takliflar",
    },
    "hostel-kapsula-hostellar-smart-capsule": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,capsule",
        "heroTagline": "Smart Capsule bo'yicha eng yaxshi takliflar",
    },
    "hostel-kapsula-hostellar-standart-kapsula": {
        "heroImageUrl": "https://loremflickr.com/1600/900/standard,capsule,pod",
        "heroTagline": "Standart kapsula bo'yicha eng yaxshi takliflar",
    },
    "hostel-kunlik-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/daily,hostel",
        "heroTagline": "Kunlik hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-mini-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mini,hotel",
        "heroTagline": "Mini Hotel bo'yicha eng yaxshi takliflar",
    },
    "hostel-oilaviy-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,hostel",
        "heroTagline": "Oilaviy hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-premium-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,hostel",
        "heroTagline": "Premium hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-premium-hostellar-deluxe-room": {
        "heroImageUrl": "https://loremflickr.com/1600/900/deluxe,room",
        "heroTagline": "Deluxe Room bo'yicha eng yaxshi takliflar",
    },
    "hostel-premium-hostellar-family-room": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,room",
        "heroTagline": "Family Room bo'yicha eng yaxshi takliflar",
    },
    "hostel-premium-hostellar-private-room": {
        "heroImageUrl": "https://loremflickr.com/1600/900/private,room",
        "heroTagline": "Private Room bo'yicha eng yaxshi takliflar",
    },
    "hostel-premium-hostellar-suite": {
        "heroImageUrl": "https://loremflickr.com/1600/900/suite,hostel",
        "heroTagline": "Suite bo'yicha eng yaxshi takliflar",
    },
    "hostel-shahar-markazidagi-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/city,downtown,hostel",
        "heroTagline": "Shahar markazidagi hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-talabalar-hosteli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/student,hostel",
        "heroTagline": "Talabalar hosteli bo'yicha eng yaxshi takliflar",
    },
    "hostel-talabalar-hosteli-oylik-ijarali-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/monthly,rental,hostel",
        "heroTagline": "Oylik ijarali hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-talabalar-hosteli-umumiy-yashash-xonalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/shared,living,room",
        "heroTagline": "Umumiy yashash xonalari bo'yicha eng yaxshi takliflar",
    },
    "hostel-talabalar-hosteli-universitetlarga-yaqin-hostellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/university,near,hostel",
        "heroTagline": "Universitetlarga yaqin hostellar bo'yicha eng yaxshi takliflar",
    },
    "hostel-uzoq-muddatli-yashash-hostellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/long,term,living",
        "heroTagline": "Uzoq muddatli yashash hostellari bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-hovuzli-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pool,villa,yard",
        "heroTagline": "Hovuzli hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-hovuzli-hovlilar-isitiladigan-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/heated,pool",
        "heroTagline": "Isitiladigan hovuz bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-hovuzli-hovlilar-ochiq-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/open,outdoor,pool",
        "heroTagline": "Ochiq hovuz bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-hovuzli-hovlilar-spa-zonali-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/spa,zone,villa",
        "heroTagline": "SPA zonali hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-hovuzli-hovlilar-yopiq-hovuz": {
        "heroImageUrl": "https://loremflickr.com/1600/900/indoor,pool",
        "heroTagline": "Yopiq hovuz bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-ijaraga-beriladigan-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/rental,villa,yard",
        "heroTagline": "Ijaraga beriladigan hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-ikkilamchi-bozordagi-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/resale,market,villa",
        "heroTagline": "Ikkilamchi bozordagi hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-investitsiya-uchun-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/investment,villa,yard",
        "heroTagline": "Investitsiya uchun hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-katta-yer-maydoniga-ega-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/large,land,area",
        "heroTagline": "Katta yer maydoniga ega hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-kottejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cottage,villa",
        "heroTagline": "Kottejlar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-premium-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,villa",
        "heroTagline": "Premium hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-premium-hovlilar-dizaynerlik-interyeriga-ega-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/designer,interior,villa",
        "heroTagline": "Dizaynerlik interyeriga ega hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-premium-hovlilar-klassik-villa": {
        "heroImageUrl": "https://loremflickr.com/1600/900/classic,villa",
        "heroTagline": "Klassik villa bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-premium-hovlilar-panoramali-hovli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/panoramic,villa,yard",
        "heroTagline": "Panoramali hovli bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-premium-hovlilar-zamonaviy-villa": {
        "heroImageUrl": "https://loremflickr.com/1600/900/modern,villa",
        "heroTagline": "Zamonaviy villa bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-qurilishi-tugallanmagan-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/construction,unfinished,villa",
        "heroTagline": "Qurilishi tugallanmagan hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-shahar-ichidagi-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/city,downtown,villa",
        "heroTagline": "Shahar ichidagi hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-shahar-tashqarisidagi-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/city,countryside,villa",
        "heroTagline": "Shahar tashqarisidagi hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-smart-home-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,villa",
        "heroTagline": "Smart Home hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-smart-home-hovlilar-aqlli-iqlim-boshqaruvi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,climate,control",
        "heroTagline": "Aqlli iqlim boshqaruvi bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-smart-home-hovlilar-aqlli-yoritish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,lighting",
        "heroTagline": "Aqlli yoritish bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-smart-home-hovlilar-avtomatlashtirilgan-xavfsizlik-tizimi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/automated,security,system",
        "heroTagline": "Avtomatlashtirilgan xavfsizlik tizimi bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-sotuvdagi-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/for,sale,villa",
        "heroTagline": "Sotuvdagi hovlilar bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-sotuvdagi-hovlilar-2-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "2 xonali bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-sotuvdagi-hovlilar-3-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "3 xonali bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-sotuvdagi-hovlilar-4-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "4 xonali bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-sotuvdagi-hovlilar-5-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "5+ xonali bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-townhouse": {
        "heroImageUrl": "https://loremflickr.com/1600/900/townhouse,villa",
        "heroTagline": "Townhouse bo'yicha eng yaxshi takliflar",
    },
    "hovlilar-yangi-qurilgan-hovlilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/new,built,villa",
        "heroTagline": "Yangi qurilgan hovlilar bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-arxitektura-va-dizayn": {
        "heroImageUrl": "https://loremflickr.com/1600/900/architecture,design",
        "heroTagline": "Arxitektura va dizayn bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-boshqa-kasblar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/other,profession",
        "heroTagline": "Boshqa kasblar bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-haydovchilar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/driver,office",
        "heroTagline": "Haydovchilar bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-it-va-texnologiyalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/technology,office",
        "heroTagline": "IT va texnologiyalar bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-it-va-texnologiyalar-backend-dasturchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/programmer,coding",
        "heroTagline": "Backend dasturchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-it-va-texnologiyalar-frontend-dasturchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/programmer,coding",
        "heroTagline": "Frontend dasturchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-it-va-texnologiyalar-mobil-dasturchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mobile,app,programmer",
        "heroTagline": "Mobil dasturchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-it-va-texnologiyalar-system-administrator": {
        "heroImageUrl": "https://loremflickr.com/1600/900/server,admin",
        "heroTagline": "System Administrator bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-it-va-texnologiyalar-ui-ux-dizayner": {
        "heroImageUrl": "https://loremflickr.com/1600/900/designer,office",
        "heroTagline": "UI/UX dizayner bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-kochmas-mulk-agentlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/real,estate,agent",
        "heroTagline": "Ko'chmas mulk agentlari bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-menejment": {
        "heroImageUrl": "https://loremflickr.com/1600/900/management,office",
        "heroTagline": "Menejment bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-moliya-va-buxgalteriya": {
        "heroImageUrl": "https://loremflickr.com/1600/900/finance,accounting",
        "heroTagline": "Moliya va buxgalteriya bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-muhandislik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/engineering,office",
        "heroTagline": "Muhandislik bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-ofis-ishlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,work",
        "heroTagline": "Ofis ishlari bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-ombor-va-logistika": {
        "heroImageUrl": "https://loremflickr.com/1600/900/warehouse,logistics",
        "heroTagline": "Ombor va logistika bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-qurilish-ishlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/construction,work",
        "heroTagline": "Qurilish ishlari bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-qurilish-ishlari-armaturachi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/rebar,worker",
        "heroTagline": "Armaturachi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-qurilish-ishlari-betonchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/concrete,worker",
        "heroTagline": "Betonchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-qurilish-ishlari-gisht-teruvchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/brick,bricklayer",
        "heroTagline": "G'isht teruvchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-qurilish-ishlari-payvandchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/welder,office",
        "heroTagline": "Payvandchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-qurilish-ishlari-suvoqchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/plasterer,office",
        "heroTagline": "Suvoqchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-qurilish-ishlari-tom-yopuvchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/roof,roofer",
        "heroTagline": "Tom yopuvchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-sotuv-va-marketing": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sale,marketing",
        "heroTagline": "Sotuv va marketing bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-tozalash-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cleaning,service",
        "heroTagline": "Tozalash xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-usta-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/handyman,craftsman,service",
        "heroTagline": "Usta xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-usta-xizmatlari-boyoqchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/painter,office",
        "heroTagline": "Bo'yoqchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-usta-xizmatlari-elektrchi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/electrician,office",
        "heroTagline": "Elektrchi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-usta-xizmatlari-konditsioner-ustasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/air,conditioner,technician",
        "heroTagline": "Konditsioner ustasi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-usta-xizmatlari-mebel-ustasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/furniture,technician",
        "heroTagline": "Mebel ustasi bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-usta-xizmatlari-santexnik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/plumber,office",
        "heroTagline": "Santexnik bo'yicha eng yaxshi takliflar",
    },
    "ish-orni-xavfsizlik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/security,office",
        "heroTagline": "Xavfsizlik bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-biznes-klass": {
        "heroImageUrl": "https://loremflickr.com/1600/900/business,class",
        "heroTagline": "Biznes klass bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-ekonom-klass": {
        "heroImageUrl": "https://loremflickr.com/1600/900/economy,class",
        "heroTagline": "Ekonom klass bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-ikkilamchi-bozor": {
        "heroImageUrl": "https://loremflickr.com/1600/900/resale,market",
        "heroTagline": "Ikkilamchi bozor bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-investitsiya-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/investment,apartment",
        "heroTagline": "Investitsiya uchun bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-investitsiya-uchun-erta-bosqich": {
        "heroImageUrl": "https://loremflickr.com/1600/900/early,stage",
        "heroTagline": "Erta bosqich bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-investitsiya-uchun-qurilish-jarayonida": {
        "heroImageUrl": "https://loremflickr.com/1600/900/construction,in,progress",
        "heroTagline": "Qurilish jarayonida bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-investitsiya-uchun-tayyor-loyiha": {
        "heroImageUrl": "https://loremflickr.com/1600/900/ready,project",
        "heroTagline": "Tayyor loyiha bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-investitsiya-uchun-tijorat-uchun-mos": {
        "heroImageUrl": "https://loremflickr.com/1600/900/commercial,suitable",
        "heroTagline": "Tijorat uchun mos bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-investitsiya-uchun-yuqori-daromadli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/high,income",
        "heroTagline": "Yuqori daromadli bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-ipotekali-uylar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mortgage,houses",
        "heroTagline": "Ipotekali uylar bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-komfort-klass": {
        "heroImageUrl": "https://loremflickr.com/1600/900/comfort,class",
        "heroTagline": "Komfort klass bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-penthouse": {
        "heroImageUrl": "https://loremflickr.com/1600/900/penthouse,apartment",
        "heroTagline": "Penthouse bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-premium-turar-joylar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,residential",
        "heroTagline": "Premium turar joylar bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-premium-turar-joylar-designer-interior": {
        "heroImageUrl": "https://loremflickr.com/1600/900/designer,interior",
        "heroTagline": "Designer Interior bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-premium-turar-joylar-penthouse": {
        "heroImageUrl": "https://loremflickr.com/1600/900/penthouse,apartment",
        "heroTagline": "Penthouse bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-premium-turar-joylar-sky-residence": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sky,residence",
        "heroTagline": "Sky Residence bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-premium-turar-joylar-smart-home": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home",
        "heroTagline": "Smart Home bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-premium-turar-joylar-terrace-apartment": {
        "heroImageUrl": "https://loremflickr.com/1600/900/terrace,apartment",
        "heroTagline": "Terrace Apartment bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-qurilishi-davom-etayotgan-loyihalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/construction,ongoing,projects",
        "heroTagline": "Qurilishi davom etayotgan loyihalar bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-studio": {
        "heroImageUrl": "https://loremflickr.com/1600/900/studio,apartment",
        "heroTagline": "Studio bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-tayyor-topshirilgan-loyihalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/ready,delivered,projects",
        "heroTagline": "Tayyor topshirilgan loyihalar bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/new,construction",
        "heroTagline": "Yangi qurilishlar bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-1-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "1 xonali bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-2-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "2 xonali bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-3-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "3 xonali bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-4-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "4+ xonali bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-duplex": {
        "heroImageUrl": "https://loremflickr.com/1600/900/duplex,apartment",
        "heroTagline": "Duplex bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-family": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,apartment",
        "heroTagline": "Family bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-loft": {
        "heroImageUrl": "https://loremflickr.com/1600/900/loft,interior",
        "heroTagline": "Loft bo'yicha eng yaxshi takliflar",
    },
    "kop-qavatli-binolar-yangi-qurilishlar-smart-apartment": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,apartment",
        "heroTagline": "Smart Apartment bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-eco-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/eco,cottage",
        "heroTagline": "Eco kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-investitsion-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/investment,cottage",
        "heroTagline": "Investitsion kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-kol-boyidagi-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lake,riverside,cottage",
        "heroTagline": "Ko'l bo'yidagi kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-kunlik-ijaraga-beriladigan-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/daily,rental,cottage",
        "heroTagline": "Kunlik ijaraga beriladigan kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-luxury-villalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/luxury,villa",
        "heroTagline": "Luxury Villalar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-oilaviy-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,cottage",
        "heroTagline": "Oilaviy kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-oilaviy-kotejlar-2-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "2 xonali bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-oilaviy-kotejlar-3-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "3 xonali bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-oilaviy-kotejlar-5-xonali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/room,apartment",
        "heroTagline": "5+ xonali bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-oilaviy-kotejlar-bolalar-maydonchali-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kids,children,playground",
        "heroTagline": "Bolalar maydonchali kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-ormon-hududidagi-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/forest,zone,cottage",
        "heroTagline": "O'rmon hududidagi kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-premium-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,cottage",
        "heroTagline": "Premium kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-premium-kotejlar-basseynli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pool,cottage",
        "heroTagline": "Basseynli bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-premium-kotejlar-panoramali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/panoramic,cottage",
        "heroTagline": "Panoramali bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-premium-kotejlar-sauna-va-spali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sauna,spa",
        "heroTagline": "Sauna va SPA'li bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-premium-kotejlar-vip-xizmatli-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/vip,service,cottage",
        "heroTagline": "VIP xizmatli kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-resort-villalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/resort,villa",
        "heroTagline": "Resort villalar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-shahar-tashqarisidagi-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/city,countryside,cottage",
        "heroTagline": "Shahar tashqarisidagi kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-smart-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,cottage",
        "heroTagline": "Smart kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-sotuvdagi-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/for,sale,cottage",
        "heroTagline": "Sotuvdagi kotejlar bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-tog-kotejlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mountain,cottage",
        "heroTagline": "Tog' kotejlari bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-tog-kotejlari-ekstremal-turizm-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/extreme,adventure,tourism",
        "heroTagline": "Ekstremal turizm uchun bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-tog-kotejlari-qishki-dam-olish-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/winter,leisure,resort",
        "heroTagline": "Qishki dam olish uchun bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-tog-kotejlari-yozgi-dam-olish-uchun": {
        "heroImageUrl": "https://loremflickr.com/1600/900/summer,leisure,resort",
        "heroTagline": "Yozgi dam olish uchun bo'yicha eng yaxshi takliflar",
    },
    "kotejlar-uzoq-muddatli-ijaradagi-kotejlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/long,term,rental",
        "heroTagline": "Uzoq muddatli ijaradagi kotejlar bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-avtomatik-sugorish-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/automatic,irrigation,garden",
        "heroTagline": "Avtomatik sug'orish tizimlari bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-bog-loyihalash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/garden,orchard,design",
        "heroTagline": "Bog' loyihalash bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-bog-loyihalash-dekorativ-bog": {
        "heroImageUrl": "https://loremflickr.com/1600/900/decorative,garden,orchard",
        "heroTagline": "Dekorativ bog' bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-bog-loyihalash-klassik-bog": {
        "heroImageUrl": "https://loremflickr.com/1600/900/classic,garden,orchard",
        "heroTagline": "Klassik bog' bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-bog-loyihalash-mevali-bog": {
        "heroImageUrl": "https://loremflickr.com/1600/900/fruit,garden,orchard",
        "heroTagline": "Mevali bog' bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-bog-loyihalash-minimalistik-bog": {
        "heroImageUrl": "https://loremflickr.com/1600/900/minimalist,garden,orchard",
        "heroTagline": "Minimalistik bog' bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-bog-loyihalash-yapon-bogi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/japanese,garden",
        "heroTagline": "Yapon bog'i bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-bog-loyihalash-zamonaviy-bog": {
        "heroImageUrl": "https://loremflickr.com/1600/900/modern,garden,orchard",
        "heroTagline": "Zamonaviy bog' bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-daraxt-va-gul-ekish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/tree,planting,flower",
        "heroTagline": "Daraxt va gul ekish bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-dekorativ-tosh-va-yolaklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/decorative,stone,pathway",
        "heroTagline": "Dekorativ tosh va yo'laklar bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-favvora-va-suniy-suv-havzalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/fountain,artificial,pond",
        "heroTagline": "Favvora va sun'iy suv havzalari bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-gazon-va-maysa-ishlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lawn,grass,work",
        "heroTagline": "Gazon va maysa ishlari bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-hovli-dizayni": {
        "heroImageUrl": "https://loremflickr.com/1600/900/villa,yard,design",
        "heroTagline": "Hovli dizayni bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-landshaft-parvarishlash-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/landscape,garden,care",
        "heroTagline": "Landshaft parvarishlash xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-park-va-yashil-hududlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/park,green,zone",
        "heroTagline": "Park va yashil hududlar bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-pergola-va-ayvonlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pergola,gazebo,porch",
        "heroTagline": "Pergola va ayvonlar bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-dam-olish-zonalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/exterior,leisure,resort",
        "heroTagline": "Tashqi dam olish zonalari bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-dam-olish-zonalari-barbekyu-zonasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/barbecue,zone",
        "heroTagline": "Barbekyu zonasi bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-dam-olish-zonalari-bolalar-maydonchasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kids,children,playground",
        "heroTagline": "Bolalar maydonchasi bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-dam-olish-zonalari-gazebo": {
        "heroImageUrl": "https://loremflickr.com/1600/900/gazebo,garden",
        "heroTagline": "Gazebo bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-dam-olish-zonalari-ochiq-terassa": {
        "heroImageUrl": "https://loremflickr.com/1600/900/open,outdoor,terrace",
        "heroTagline": "Ochiq terassa bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-dam-olish-zonalari-pergola": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pergola,garden",
        "heroTagline": "Pergola bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-dam-olish-zonalari-yozgi-oshxona": {
        "heroImageUrl": "https://loremflickr.com/1600/900/summer,kitchen",
        "heroTagline": "Yozgi oshxona bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-yoritish-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/exterior,lighting,system",
        "heroTagline": "Tashqi yoritish tizimlari bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-yoritish-tizimlari-aqlli-yoritish-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,lighting,system",
        "heroTagline": "Aqlli yoritish tizimlari bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-yoritish-tizimlari-dekorativ-yoritish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/decorative,lighting",
        "heroTagline": "Dekorativ yoritish bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-yoritish-tizimlari-led-yoritish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/led,light,lighting",
        "heroTagline": "LED yoritish bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tashqi-yoritish-tizimlari-quyosh-energiyasida-ishlovchi-chiroqlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/solar,power,light",
        "heroTagline": "Quyosh energiyasida ishlovchi chiroqlar bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-tom-boglari-roof-garden": {
        "heroImageUrl": "https://loremflickr.com/1600/900/roof,garden",
        "heroTagline": "Tom bog'lari (Roof Garden) bo'yicha eng yaxshi takliflar",
    },
    "landshaft-dizayni-vertikal-boglar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/vertical,garden",
        "heroTagline": "Vertikal bog'lar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-changyutgichlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/vacuum,cleaner",
        "heroTagline": "Changyutgichlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-gaz-plitalari-va-pechlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/gas,stove,board",
        "heroTagline": "Gaz plitalari va pechlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-idish-yuvish-mashinalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/dishwasher,washing,machine",
        "heroTagline": "Idish yuvish mashinalari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-iqlim-texnikalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/climate,appliance",
        "heroTagline": "Iqlim texnikalari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-kichik-maishiy-texnikalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/small,household,appliance",
        "heroTagline": "Kichik maishiy texnikalar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-kir-yuvish-mashinalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/laundry,washing,machine",
        "heroTagline": "Kir yuvish mashinalari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-kir-yuvish-mashinalari-avtomatik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/automatic,home",
        "heroTagline": "Avtomatik bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-kir-yuvish-mashinalari-quritish-funksiyali": {
        "heroImageUrl": "https://loremflickr.com/1600/900/drying,function",
        "heroTagline": "Quritish funksiyali bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-kir-yuvish-mashinalari-sanoat-kir-yuvish-mashinalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/industrial,laundry,washing",
        "heroTagline": "Sanoat kir yuvish mashinalari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-kir-yuvish-mashinalari-yarim-avtomatik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/semi,automatic",
        "heroTagline": "Yarim avtomatik bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-konditsionerlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/air,conditioner",
        "heroTagline": "Konditsionerlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-mikrotolqinli-pechlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/microwave,oven",
        "heroTagline": "Mikroto'lqinli pechlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-muzlatgichlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/refrigerator,fridge",
        "heroTagline": "Muzlatgichlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-muzlatgichlar-ikki-eshikli": {
        "heroImageUrl": "https://loremflickr.com/1600/900/two,door,fridge",
        "heroTagline": "Ikki eshikli bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-muzlatgichlar-mini-muzlatgichlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mini,refrigerator,fridge",
        "heroTagline": "Mini muzlatgichlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-muzlatgichlar-side-by-side": {
        "heroImageUrl": "https://loremflickr.com/1600/900/side,by,fridge",
        "heroTagline": "Side by Side bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-muzlatgichlar-smart-muzlatgichlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,refrigerator",
        "heroTagline": "Smart muzlatgichlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-oshxona-texnikalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kitchen,appliance",
        "heroTagline": "Oshxona texnikalari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-oshxona-texnikalari-blenderlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/blender,home",
        "heroTagline": "Blenderlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-oshxona-texnikalari-elektr-choynaklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/electrical,kettle",
        "heroTagline": "Elektr choynaklar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-oshxona-texnikalari-kofe-mashinalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/coffee,machine",
        "heroTagline": "Kofe mashinalari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-oshxona-texnikalari-mikserlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mixer,home",
        "heroTagline": "Mikserlar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-oshxona-texnikalari-multivarkalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/slow,cooker",
        "heroTagline": "Multivarkalar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-premium-texnikalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,appliance",
        "heroTagline": "Premium texnikalar bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-smart-home-qurilmalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,device",
        "heroTagline": "Smart Home qurilmalari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-suv-isitkichlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/water,heater",
        "heroTagline": "Suv isitkichlari bo'yicha eng yaxshi takliflar",
    },
    "maishiy-texnikalar-televizorlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/television,home",
        "heroTagline": "Televizorlar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-boyoq-va-laklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/paint,lacquer,varnish",
        "heroTagline": "Bo'yoq va laklar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-fanera-va-laminatlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/plywood,laminate,flooring",
        "heroTagline": "Fanera va laminatlar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mato-va-charm-qoplamalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/fabric,leather,coating",
        "heroTagline": "Mato va charm qoplamalar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mato-va-charm-qoplamalar-eko-charm": {
        "heroImageUrl": "https://loremflickr.com/1600/900/eco,leather",
        "heroTagline": "Eko charm bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mato-va-charm-qoplamalar-mikrofiber": {
        "heroImageUrl": "https://loremflickr.com/1600/900/microfiber,fabric",
        "heroTagline": "Mikrofiber bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mato-va-charm-qoplamalar-tabiiy-charm": {
        "heroImageUrl": "https://loremflickr.com/1600/900/natural,leather",
        "heroTagline": "Tabiiy charm bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mato-va-charm-qoplamalar-velyur": {
        "heroImageUrl": "https://loremflickr.com/1600/900/velvet,fabric",
        "heroTagline": "Velyur bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mdf-va-dsp-plitalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mdf,board,chipboard",
        "heroTagline": "MDF va DSP plitalari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-furnituralari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/furniture,hardware",
        "heroTagline": "Mebel furnituralari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-furnituralari-ilgaklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hook,furniture",
        "heroTagline": "Ilgaklar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-furnituralari-lift-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lift,mechanism,system",
        "heroTagline": "Lift tizimlari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-furnituralari-magnitlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/magnet,furniture",
        "heroTagline": "Magnitlar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-furnituralari-menteshalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hinge,furniture",
        "heroTagline": "Menteshalar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-furnituralari-qulflar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lock,furniture",
        "heroTagline": "Qulflar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-furnituralari-relslar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/rail,slide",
        "heroTagline": "Relslar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-ishlab-chiqarish-asboblari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/furniture,factory,production",
        "heroTagline": "Mebel ishlab chiqarish asboblari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-mebel-oyoqlari-va-tayanchlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/furniture,legs,base",
        "heroTagline": "Mebel oyoqlari va tayanchlari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-sharnir-va-rels-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hinge,rail,slide",
        "heroTagline": "Sharnir va rels tizimlari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-shisha-va-oyna-mahsulotlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/glass,mirror,products",
        "heroTagline": "Shisha va oyna mahsulotlari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-stoleshnitsalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/countertop,furniture",
        "heroTagline": "Stoleshnitsalar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-tutqich-va-aksessuarlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/handle,accessories",
        "heroTagline": "Tutqich va aksessuarlar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yelim-va-kimyoviy-mahsulotlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/glue,adhesive,chemical",
        "heroTagline": "Yelim va kimyoviy mahsulotlar bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yogoch-materiallari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/wood,timber,materials",
        "heroTagline": "Yog'och materiallari bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yogoch-materiallari-buk": {
        "heroImageUrl": "https://loremflickr.com/1600/900/beech,wood",
        "heroTagline": "Buk bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yogoch-materiallari-dsp": {
        "heroImageUrl": "https://loremflickr.com/1600/900/chipboard,furniture",
        "heroTagline": "DSP bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yogoch-materiallari-eman": {
        "heroImageUrl": "https://loremflickr.com/1600/900/oak,wood",
        "heroTagline": "Eman bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yogoch-materiallari-mdf": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mdf,board",
        "heroTagline": "MDF bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yogoch-materiallari-qaragay": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pine,wood",
        "heroTagline": "Qarag'ay bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yogoch-materiallari-yongoq": {
        "heroImageUrl": "https://loremflickr.com/1600/900/walnut,wood",
        "heroTagline": "Yong'oq bo'yicha eng yaxshi takliflar",
    },
    "mebel-materiallari-yumshoq-mebel-materiallari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/upholstered,soft,furniture",
        "heroTagline": "Yumshoq mebel materiallari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-bog-va-tashqi-mebellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/garden,orchard,exterior",
        "heroTagline": "Bog' va tashqi mebellar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-bolalar-xonasi-mebellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kids,children,room",
        "heroTagline": "Bolalar xonasi mebellari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-buyurtma-asosida-tayyorlanadigan-mebellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/custom,order,made",
        "heroTagline": "Buyurtma asosida tayyorlanadigan mebellar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-dekor-va-interyer-aksessuarlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/decor,interior,accessories",
        "heroTagline": "Dekor va interyer aksessuarlari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-mebel-aksessuarlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/furniture,accessories",
        "heroTagline": "Mebel aksessuarlari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-mehmonxona-mebellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hotel,furniture",
        "heroTagline": "Mehmonxona mebellari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-ofis-mebellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,furniture",
        "heroTagline": "Ofis mebellari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-ofis-mebellari-ish-stollari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/work,office,table",
        "heroTagline": "Ish stollari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-ofis-mebellari-konferensiya-stollari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/conference,table,desk",
        "heroTagline": "Konferensiya stollari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-ofis-mebellari-ofis-stullari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,chair",
        "heroTagline": "Ofis stullari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-ofis-mebellari-resepsion-mebellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/reception,desk,furniture",
        "heroTagline": "Resepsion mebellari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-ofis-mebellari-shkaflar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/wardrobe,cabinet",
        "heroTagline": "Shkaflar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-oshxona-mebellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/kitchen,furniture",
        "heroTagline": "Oshxona mebellari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-oshxona-mebellari-klassik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/classic,furniture",
        "heroTagline": "Klassik bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-oshxona-mebellari-minimalistik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/minimalist,garden",
        "heroTagline": "Minimalistik bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-oshxona-mebellari-premium-oshxona-garniturlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,kitchen",
        "heroTagline": "Premium oshxona garniturlari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-oshxona-mebellari-zamonaviy": {
        "heroImageUrl": "https://loremflickr.com/1600/900/modern,furniture",
        "heroTagline": "Zamonaviy bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-premium-mebellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,furniture",
        "heroTagline": "Premium mebellar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-restoran-va-kafe-mebellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/restaurant,cafe,furniture",
        "heroTagline": "Restoran va kafe mebellari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-smart-mebellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,furniture",
        "heroTagline": "Smart mebellar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-yotoqxona-mebellari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/bedroom,furniture",
        "heroTagline": "Yotoqxona mebellari bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-yumshoq-mebellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/upholstered,soft,furniture",
        "heroTagline": "Yumshoq mebellar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-yumshoq-mebellar-burchak-divanlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/corner,sofa,couch",
        "heroTagline": "Burchak divanlar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-yumshoq-mebellar-divanlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sofa,couch",
        "heroTagline": "Divanlar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-yumshoq-mebellar-kreslolar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/armchair,furniture",
        "heroTagline": "Kreslolar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-yumshoq-mebellar-puflar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pouf,ottoman",
        "heroTagline": "Puflar bo'yicha eng yaxshi takliflar",
    },
    "mebel-salonlari-yumshoq-mebellar-transformatsiyalanuvchi-mebellar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sofa,bed,furniture",
        "heroTagline": "Transformatsiyalanuvchi mebellar bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-3-yulduzli-mehmonxonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/star,hotel",
        "heroTagline": "3 yulduzli mehmonxonalar bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-4-yulduzli-mehmonxonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/star,hotel",
        "heroTagline": "4 yulduzli mehmonxonalar bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-5-yulduzli-mehmonxonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/star,hotel",
        "heroTagline": "5 yulduzli mehmonxonalar bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-airport-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/airport,hotel",
        "heroTagline": "Airport Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-apart-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/apart,hotel",
        "heroTagline": "Apart Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-boutique-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/boutique,hotel",
        "heroTagline": "Boutique Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-business-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/business,hotel",
        "heroTagline": "Business Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-business-hotel-biznes-xizmatlariga-ega-mehmonxonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/business,service,hotel",
        "heroTagline": "Biznes xizmatlariga ega mehmonxonalar bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-business-hotel-coworking-zonalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/coworking,office,zone",
        "heroTagline": "Coworking zonalari bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-business-hotel-konferensiya-zallari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/conference,hall",
        "heroTagline": "Konferensiya zallari bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-city-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/city,hotel",
        "heroTagline": "City Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-eco-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/eco,hotel",
        "heroTagline": "Eco Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-family-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,hotel",
        "heroTagline": "Family Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-luxury-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/luxury,hotel",
        "heroTagline": "Luxury Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-luxury-hotel-deluxe-room": {
        "heroImageUrl": "https://loremflickr.com/1600/900/deluxe,room",
        "heroTagline": "Deluxe Room bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-luxury-hotel-executive-room": {
        "heroImageUrl": "https://loremflickr.com/1600/900/executive,room",
        "heroTagline": "Executive Room bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-luxury-hotel-presidential-suite": {
        "heroImageUrl": "https://loremflickr.com/1600/900/presidential,suite",
        "heroTagline": "Presidential Suite bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-luxury-hotel-royal-suite": {
        "heroImageUrl": "https://loremflickr.com/1600/900/royal,suite",
        "heroTagline": "Royal Suite bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-mountain-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mountain,hotel",
        "heroTagline": "Mountain Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-resort-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/resort,hotel",
        "heroTagline": "Resort Hotel bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-resort-hotel-beach-resort": {
        "heroImageUrl": "https://loremflickr.com/1600/900/beach,resort",
        "heroTagline": "Beach Resort bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-resort-hotel-family-resort": {
        "heroImageUrl": "https://loremflickr.com/1600/900/family,resort",
        "heroTagline": "Family Resort bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-resort-hotel-mountain-resort": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mountain,resort",
        "heroTagline": "Mountain Resort bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-resort-hotel-wellness-resort": {
        "heroImageUrl": "https://loremflickr.com/1600/900/wellness,spa,resort",
        "heroTagline": "Wellness Resort bo'yicha eng yaxshi takliflar",
    },
    "mexmonxona-spa-hotel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/spa,hotel",
        "heroTagline": "Spa Hotel bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-avtoservis-va-avtosalonlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/car,service,garage",
        "heroTagline": "Avtoservis va avtosalonlar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-dokon-va-butiklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/shop,store,boutique",
        "heroTagline": "Do'kon va butiklar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-investitsiya-obyektlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/investment,property",
        "heroTagline": "Investitsiya obyektlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-ishlab-chiqarish-binolari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/factory,production,building",
        "heroTagline": "Ishlab chiqarish binolari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-kongilochar-markazlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/entertainment,center",
        "heroTagline": "Ko'ngilochar markazlar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-mehmonxonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hotel,commercial",
        "heroTagline": "Mehmonxonalar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-ofis-binolari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,building",
        "heroTagline": "Ofis binolari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-ofis-binolari-alohida-ofislar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/private,office",
        "heroTagline": "Alohida ofislar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-ofis-binolari-business-center": {
        "heroImageUrl": "https://loremflickr.com/1600/900/business,center",
        "heroTagline": "Business Center bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-ofis-binolari-coworking": {
        "heroImageUrl": "https://loremflickr.com/1600/900/coworking,office",
        "heroTagline": "Coworking bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-ofis-binolari-open-space": {
        "heroImageUrl": "https://loremflickr.com/1600/900/open,space",
        "heroTagline": "Open Space bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-ofis-binolari-premium-office": {
        "heroImageUrl": "https://loremflickr.com/1600/900/premium,luxury,office",
        "heroTagline": "Premium Office bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-omborxonalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/warehouse,commercial",
        "heroTagline": "Omborxonalar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-omborxonalar-distribyutor-markazlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/distributor,centers",
        "heroTagline": "Distribyutor markazlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-omborxonalar-logistika-omborlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/logistics,warehouse",
        "heroTagline": "Logistika omborlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-omborxonalar-sanoat-omborlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/industrial,warehouse",
        "heroTagline": "Sanoat omborlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-omborxonalar-sovutkich-omborlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cold,storage,warehouse",
        "heroTagline": "Sovutkich omborlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-restoran-va-kafelar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/restaurant,cafe",
        "heroTagline": "Restoran va kafelar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-savdo-markazlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/shopping,centers",
        "heroTagline": "Savdo markazlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-savdo-markazlari-butiklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/boutique,shop",
        "heroTagline": "Butiklar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-savdo-markazlari-food-court-joylari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/food,court,hall",
        "heroTagline": "Food court joylari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-savdo-markazlari-savdo-pavilyonlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/shopping,pavilion",
        "heroTagline": "Savdo pavilyonlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-savdo-markazlari-showroomlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/showroom,commercial",
        "heroTagline": "Showroomlar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-savdo-markazlari-supermarketlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/supermarket,commercial",
        "heroTagline": "Supermarketlar bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-sport-va-fitness-markazlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sport,gym,fitness",
        "heroTagline": "Sport va fitness markazlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-talim-muassasalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/education,school,institution",
        "heroTagline": "Ta'lim muassasalari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-tibbiyot-markazlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/medical,clinic,centers",
        "heroTagline": "Tibbiyot markazlari bo'yicha eng yaxshi takliflar",
    },
    "noturar-binolar-zavod-va-fabrikalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/factory,commercial",
        "heroTagline": "Zavod va fabrikalar bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-armatura-va-metall-mahsulotlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/rebar,steel,metal",
        "heroTagline": "Armatura va metall mahsulotlari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-boyoqlar-va-pardozlash-materiallari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/paint,finishing,materials",
        "heroTagline": "Bo'yoqlar va pardozlash materiallari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-boyoqlar-va-pardozlash-materiallari-dekorativ-qoplamalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/decorative,coating",
        "heroTagline": "Dekorativ qoplamalar bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-boyoqlar-va-pardozlash-materiallari-emal": {
        "heroImageUrl": "https://loremflickr.com/1600/900/enamel,paint",
        "heroTagline": "Emal bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-boyoqlar-va-pardozlash-materiallari-grunt": {
        "heroImageUrl": "https://loremflickr.com/1600/900/primer,paint",
        "heroTagline": "Grunt bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-boyoqlar-va-pardozlash-materiallari-ichki-boyoq": {
        "heroImageUrl": "https://loremflickr.com/1600/900/interior,paint",
        "heroTagline": "Ichki bo'yoq bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-boyoqlar-va-pardozlash-materiallari-lak": {
        "heroImageUrl": "https://loremflickr.com/1600/900/varnish,paint",
        "heroTagline": "Lak bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-boyoqlar-va-pardozlash-materiallari-tashqi-boyoq": {
        "heroImageUrl": "https://loremflickr.com/1600/900/exterior,paint",
        "heroTagline": "Tashqi bo'yoq bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-elektr-mahsulotlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/electrical,products",
        "heroTagline": "Elektr mahsulotlari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-elektr-mahsulotlari-avtomat": {
        "heroImageUrl": "https://loremflickr.com/1600/900/circuit,breaker",
        "heroTagline": "Avtomat bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-elektr-mahsulotlari-kabel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cable,wire",
        "heroTagline": "Kabel bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-elektr-mahsulotlari-rozetka": {
        "heroImageUrl": "https://loremflickr.com/1600/900/electrical,socket",
        "heroTagline": "Rozetka bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-elektr-mahsulotlari-sensor": {
        "heroImageUrl": "https://loremflickr.com/1600/900/sensor,construction",
        "heroTagline": "Sensor bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-elektr-mahsulotlari-yoritish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lighting,construction",
        "heroTagline": "Yoritish bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-eshik-va-derazalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/door,window",
        "heroTagline": "Eshik va derazalar bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-gisht-va-bloklar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/brick,block",
        "heroTagline": "G'isht va bloklar bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-issiqlik-va-gidroizolyatsiya": {
        "heroImageUrl": "https://loremflickr.com/1600/900/thermal,insulation,waterproofing",
        "heroTagline": "Issiqlik va gidroizolyatsiya bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/fastener,hardware,products",
        "heroTagline": "Mahkamlash mahsulotlari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-anker": {
        "heroImageUrl": "https://loremflickr.com/1600/900/anchor,bolt",
        "heroTagline": "Anker bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-bolt": {
        "heroImageUrl": "https://loremflickr.com/1600/900/bolt,construction",
        "heroTagline": "Bolt bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-dyubel": {
        "heroImageUrl": "https://loremflickr.com/1600/900/dowel,construction",
        "heroTagline": "Dyubel bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-gayka": {
        "heroImageUrl": "https://loremflickr.com/1600/900/nut,bolt",
        "heroTagline": "Gayka bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-mix": {
        "heroImageUrl": "https://loremflickr.com/1600/900/nail,construction",
        "heroTagline": "Mix bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-shayba": {
        "heroImageUrl": "https://loremflickr.com/1600/900/washer,bolt",
        "heroTagline": "Shayba bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-shurup": {
        "heroImageUrl": "https://loremflickr.com/1600/900/screw,construction",
        "heroTagline": "Shurup bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-mahkamlash-mahsulotlari-vint": {
        "heroImageUrl": "https://loremflickr.com/1600/900/screw,bolt",
        "heroTagline": "Vint bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-maxsus-texnika-va-jihozlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/special,equipment,machinery",
        "heroTagline": "Maxsus texnika va jihozlar bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-pol-qoplamalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/floor,coating",
        "heroTagline": "Pol qoplamalari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-qurilish-asbob-uskunalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/construction,tools,equipment",
        "heroTagline": "Qurilish asbob-uskunalari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-santexnika-mahsulotlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/plumbing,products",
        "heroTagline": "Santexnika mahsulotlari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-sement-va-quruq-aralashmalar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cement,dry,mix",
        "heroTagline": "Sement va quruq aralashmalar bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-tom-yopish-materiallari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/roof,roofing,materials",
        "heroTagline": "Tom yopish materiallari bo'yicha eng yaxshi takliflar",
    },
    "qurilish-materiallari-yogoch-mahsulotlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/wood,timber,products",
        "heroTagline": "Yog'och mahsulotlari bo'yicha eng yaxshi takliflar",
    },
    "tamirchi-xizmati": {
        "heroImageUrl": "https://loremflickr.com/1600/900/repairman,handyman",
        "heroTagline": "Ta'mirchi bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-elektrchilar-uchun-kiyimlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/electrician,clothing,workwear",
        "heroTagline": "Elektrchilar uchun kiyimlar bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/protective,gear,equipment",
        "heroTagline": "Himoya vositalari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari-kaska": {
        "heroImageUrl": "https://loremflickr.com/1600/900/helmet,workwear",
        "heroTagline": "Kaska bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari-kozoynak": {
        "heroImageUrl": "https://loremflickr.com/1600/900/safety,glasses",
        "heroTagline": "Ko'zoynak bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari-niqob": {
        "heroImageUrl": "https://loremflickr.com/1600/900/mask,workwear",
        "heroTagline": "Niqob bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari-qolqop": {
        "heroImageUrl": "https://loremflickr.com/1600/900/gloves,workwear",
        "heroTagline": "Qo'lqop bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari-quloqchin": {
        "heroImageUrl": "https://loremflickr.com/1600/900/ear,protection",
        "heroTagline": "Quloqchin bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari-respirator": {
        "heroImageUrl": "https://loremflickr.com/1600/900/respirator,mask",
        "heroTagline": "Respirator bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-himoya-vositalari-xavfsizlik-kamarlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/security,safety,harness",
        "heroTagline": "Xavfsizlik kamarlari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ish-poyabzallari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/work,office,boots",
        "heroTagline": "Ish poyabzallari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ish-poyabzallari-botinka": {
        "heroImageUrl": "https://loremflickr.com/1600/900/boots,workwear",
        "heroTagline": "Botinka bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ish-poyabzallari-etik": {
        "heroImageUrl": "https://loremflickr.com/1600/900/boots,workwear",
        "heroTagline": "Etik bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ish-poyabzallari-metall-burunli-poyabzal": {
        "heroImageUrl": "https://loremflickr.com/1600/900/metal,steel,toe",
        "heroTagline": "Metall burunli poyabzal bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ish-poyabzallari-qishki-poyabzal": {
        "heroImageUrl": "https://loremflickr.com/1600/900/winter,boots,shoes",
        "heroTagline": "Qishki poyabzal bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ish-poyabzallari-suv-otkazmaydigan-poyabzal": {
        "heroImageUrl": "https://loremflickr.com/1600/900/water,waterproof,boots",
        "heroTagline": "Suv o'tkazmaydigan poyabzal bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ish-poyabzallari-yozgi-poyabzal": {
        "heroImageUrl": "https://loremflickr.com/1600/900/summer,boots,shoes",
        "heroTagline": "Yozgi poyabzal bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-mavsumiy-ish-kiyimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/seasonal,workwear,work",
        "heroTagline": "Mavsumiy ish kiyimlari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-maxsus-himoya-kiyimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/special,protective,gear",
        "heroTagline": "Maxsus himoya kiyimlari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-mehmonxona-va-servis-formasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/hotel,service,uniform",
        "heroTagline": "Mehmonxona va servis formasi bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-muhandis-va-texnik-kiyimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/engineer,technical,maintenance",
        "heroTagline": "Muhandis va texnik kiyimlari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-ofis-formasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,uniform",
        "heroTagline": "Ofis formasi bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-payvandchilar-uchun-kiyimlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/welder,clothing,workwear",
        "heroTagline": "Payvandchilar uchun kiyimlar bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-qurilish-kiyimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/construction,clothing",
        "heroTagline": "Qurilish kiyimlari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-qurilish-kiyimlari-jilet": {
        "heroImageUrl": "https://loremflickr.com/1600/900/vest,workwear",
        "heroTagline": "Jilet bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-qurilish-kiyimlari-kombinezon": {
        "heroImageUrl": "https://loremflickr.com/1600/900/coverall,workwear",
        "heroTagline": "Kombinezon bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-qurilish-kiyimlari-kurtka": {
        "heroImageUrl": "https://loremflickr.com/1600/900/jacket,workwear",
        "heroTagline": "Kurtka bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-qurilish-kiyimlari-shim": {
        "heroImageUrl": "https://loremflickr.com/1600/900/pants,workwear",
        "heroTagline": "Shim bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-qurilish-kiyimlari-termo-kiyimlar": {
        "heroImageUrl": "https://loremflickr.com/1600/900/thermal,workwear,clothing",
        "heroTagline": "Termo kiyimlar bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-qurilish-kiyimlari-yomgir-kiyimi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/raincoat,clothing",
        "heroTagline": "Yomg'ir kiyimi bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-restoran-va-oshpaz-formasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/restaurant,chef,uniform",
        "heroTagline": "Restoran va oshpaz formasi bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-santexnik-va-usta-kiyimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/plumber,handyman,craftsman",
        "heroTagline": "Santexnik va usta kiyimlari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-tibbiyot-kiyimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/medical,clinic,clothing",
        "heroTagline": "Tibbiyot kiyimlari bo'yicha eng yaxshi takliflar",
    },
    "uniforma-va-maxsus-kiyimlar-xavfsizlik-xodimlari-formasi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/security,staff,uniform",
        "heroTagline": "Xavfsizlik xodimlari formasi bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-dekorativ-yoritish": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/Geometric_white_pendant_lamp_chandelier.jpg/1920px-Geometric_white_pendant_lamp_chandelier.jpg",
        "heroTagline": "Dekorativ yoritish bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-dekorativ-yoritish-aqlli-yoritish-tizimlari": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/Geometric_white_pendant_lamp_chandelier.jpg/1920px-Geometric_white_pendant_lamp_chandelier.jpg",
        "heroTagline": "Aqlli yoritish tizimlari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-dekorativ-yoritish-dizayner-lampalari": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/Geometric_white_pendant_lamp_chandelier.jpg/1920px-Geometric_white_pendant_lamp_chandelier.jpg",
        "heroTagline": "Dizayner lampalari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-dekorativ-yoritish-led-yoritish": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/Geometric_white_pendant_lamp_chandelier.jpg/1920px-Geometric_white_pendant_lamp_chandelier.jpg",
        "heroTagline": "LED yoritish bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-dekorativ-yoritish-osma-chiroqlar": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/Geometric_white_pendant_lamp_chandelier.jpg/1920px-Geometric_white_pendant_lamp_chandelier.jpg",
        "heroTagline": "Osma chiroqlar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-dekorativ-yoritish-tungi-lampalar": {
        "heroImageUrl": "https://live.staticflickr.com/4110/5103679082_799c8f2ccd_b.jpg",
        "heroTagline": "Tungi lampalar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-devor-bezaklari": {
        "heroImageUrl": "https://live.staticflickr.com/8007/7647610132_017e4750e7_b.jpg",
        "heroTagline": "Devor bezaklari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-devor-bezaklari-3d-panellar": {
        "heroImageUrl": "https://live.staticflickr.com/8007/7647610132_017e4750e7_b.jpg",
        "heroTagline": "3D panellar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-devor-bezaklari-dekorativ-yogoch-panellar": {
        "heroImageUrl": "https://live.staticflickr.com/3481/3470286741_92802e06f6_b.jpg",
        "heroTagline": "Dekorativ yog'och panellar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-devor-bezaklari-metall-dekorlar": {
        "heroImageUrl": "https://live.staticflickr.com/62/154160164_6ceb2fa49e_b.jpg",
        "heroTagline": "Metall dekorlar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-devor-bezaklari-premium-devor-kompozitsiyalari": {
        "heroImageUrl": "https://live.staticflickr.com/8007/7647610132_017e4750e7_b.jpg",
        "heroTagline": "Premium devor kompozitsiyalari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-devor-bezaklari-stikerlar": {
        "heroImageUrl": "https://live.staticflickr.com/8007/7647610132_017e4750e7_b.jpg",
        "heroTagline": "Stikerlar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-gilam-va-pol-qoplamalari": {
        "heroImageUrl": "https://images.rawpixel.com/editor_1024/cHJpdmF0ZS9sci9pbWFnZXMvd2Vic2l0ZS8yMDIyLTEyL2FpYzE1NjYwNC1pbWFnZS5qcGc.jpg",
        "heroTagline": "Gilam va pol qoplamalari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-gullar-va-dekorativ-osimliklar": {
        "heroImageUrl": "https://live.staticflickr.com/2907/14197390872_75bb66c861_b.jpg",
        "heroTagline": "Gullar va dekorativ o'simliklar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-hammom-aksessuarlari": {
        "heroImageUrl": "https://live.staticflickr.com/3065/2814824081_181c4615d8_b.jpg",
        "heroTagline": "Hammom aksessuarlari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-kozgular": {
        "heroImageUrl": "https://live.staticflickr.com/65535/54297290632_165f766a5c_b.jpg",
        "heroTagline": "Ko'zgular bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-oshxona-bezaklari": {
        "heroImageUrl": "https://live.staticflickr.com/136/329995787_98fa39c23d_b.jpg",
        "heroTagline": "Oshxona bezaklari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-pardalar-va-jalyuzilar": {
        "heroImageUrl": "https://live.staticflickr.com/5516/10589144656_b1d3a4445b_b.jpg",
        "heroTagline": "Pardalar va jalyuzilar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-pardalar-va-jalyuzilar-avtomatik": {
        "heroImageUrl": "https://live.staticflickr.com/5516/10589144656_b1d3a4445b_b.jpg",
        "heroTagline": "Avtomatik bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-pardalar-va-jalyuzilar-blackout": {
        "heroImageUrl": "https://live.staticflickr.com/4310/36268144316_e3049c5e97_b.jpg",
        "heroTagline": "Blackout bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-pardalar-va-jalyuzilar-klassik": {
        "heroImageUrl": "https://live.staticflickr.com/7196/6859957080_8f1ca6d839_b.jpg",
        "heroTagline": "Klassik bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-pardalar-va-jalyuzilar-premium-kolleksiyalar": {
        "heroImageUrl": "https://live.staticflickr.com/8623/15917081098_b3f1e0d311_b.jpg",
        "heroTagline": "Premium kolleksiyalar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-pardalar-va-jalyuzilar-zamonaviy": {
        "heroImageUrl": "https://live.staticflickr.com/7196/6859957080_8f1ca6d839_b.jpg",
        "heroTagline": "Zamonaviy bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-rasmlar-va-kartinalar": {
        "heroImageUrl": "https://live.staticflickr.com/7151/6854099213_b643011688_b.jpg",
        "heroTagline": "Rasmlar va kartinalar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-shamdon-va-dekor-aksessuarlari": {
        "heroImageUrl": "https://images.rawpixel.com/editor_1024/czNmcy1wcml2YXRlL3Jhd3BpeGVsX2ltYWdlcy93ZWJzaXRlX2NvbnRlbnQvbHIvZnJjYW5kbGVzdGlja19jYW5kbGVfc3VuX2Z1c2lvbi1pbWFnZS1reWJlNGV1aS5qcGc.jpg",
        "heroTagline": "Shamdon va dekor aksessuarlari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-smart-dekor-mahsulotlari": {
        "heroImageUrl": "https://upload.wikimedia.org/wikipedia/commons/e/e6/Amazon_Echo_Plus_02.jpg",
        "heroTagline": "Smart dekor mahsulotlari bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-soatlar": {
        "heroImageUrl": "https://live.staticflickr.com/4005/5146431359_758816d2d1_b.jpg",
        "heroTagline": "Soatlar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-vaza-va-haykallar": {
        "heroImageUrl": "https://images.rawpixel.com/editor_1024/cHJpdmF0ZS9sci9pbWFnZXMvd2Vic2l0ZS8yMDIyLTA5L21ldDQ3MzcwLWltYWdlLmpwZw.jpg",
        "heroTagline": "Vaza va haykallar bo'yicha eng yaxshi takliflar",
    },
    "uy-bezaklari-yotoqxona-dekorlari": {
        "heroImageUrl": "https://live.staticflickr.com/6183/6050427981_85a212629f_b.jpg",
        "heroTagline": "Yotoqxona dekorlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-dizayn-va-loyiha-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/design,project,service",
        "heroTagline": "Dizayn va loyiha xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-elektrik-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/electrical,service",
        "heroTagline": "Elektrik xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-elektrik-xizmatlari-avariya-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/emergency,repair,service",
        "heroTagline": "Avariya xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-elektrik-xizmatlari-elektr-qalqonlarini-ornatish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/electrical,panel,installation",
        "heroTagline": "Elektr qalqonlarini o'rnatish bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-elektrik-xizmatlari-sim-tortish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/wiring,handyman",
        "heroTagline": "Sim tortish bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-elektrik-xizmatlari-smart-home-elektr-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/smart,home,electrical",
        "heroTagline": "Smart Home elektr tizimlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-elektrik-xizmatlari-yoritish-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/lighting,system",
        "heroTagline": "Yoritish tizimlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-kochirish-pereezd-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/moving,relocation,service",
        "heroTagline": "Ko'chirish (Pereezd) xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-konditsioner-va-ventilyatsiya": {
        "heroImageUrl": "https://loremflickr.com/1600/900/air,conditioner,ventilation",
        "heroTagline": "Konditsioner va ventilyatsiya bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-mebel-yigish-va-ornatish": {
        "heroImageUrl": "https://loremflickr.com/1600/900/furniture,assembly,installation",
        "heroTagline": "Mebel yig'ish va o'rnatish bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-qurilish-brigadalari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/construction,crew",
        "heroTagline": "Qurilish brigadalari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-santexnika-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/plumbing,service",
        "heroTagline": "Santexnika xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tamirlash-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/repair,renovation,service",
        "heroTagline": "Ta'mirlash xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tamirlash-xizmatlari-fasad-ishlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/facade,renovation,work",
        "heroTagline": "Fasad ishlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tamirlash-xizmatlari-kapital-tamirlash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/major,renovation,repair",
        "heroTagline": "Kapital ta'mirlash bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tamirlash-xizmatlari-kosmetik-tamirlash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cosmetic,renovation,repair",
        "heroTagline": "Kosmetik ta'mirlash bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tamirlash-xizmatlari-kvartira-tamiri": {
        "heroImageUrl": "https://loremflickr.com/1600/900/apartment,renovation",
        "heroTagline": "Kvartira ta'miri bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tamirlash-xizmatlari-ofis-tamiri": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,renovation",
        "heroTagline": "Ofis ta'miri bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tozalash-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cleaning,service",
        "heroTagline": "Tozalash xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tozalash-xizmatlari-general-tozalash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/deep,cleaning",
        "heroTagline": "General tozalash bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tozalash-xizmatlari-kimyoviy-tozalash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/chemical,cleaning",
        "heroTagline": "Kimyoviy tozalash bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tozalash-xizmatlari-kundalik-tozalash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/daily,cleaning",
        "heroTagline": "Kundalik tozalash bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tozalash-xizmatlari-ofis-tozalash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/office,cleaning",
        "heroTagline": "Ofis tozalash bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-tozalash-xizmatlari-qurilishdan-keyingi-tozalash": {
        "heroImageUrl": "https://loremflickr.com/1600/900/post,construction,cleaning",
        "heroTagline": "Qurilishdan keyingi tozalash bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-usta-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/handyman,craftsman,service",
        "heroTagline": "Usta xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-uy-boshqaruvi-va-texnik-xizmat": {
        "heroImageUrl": "https://loremflickr.com/1600/900/home,control,technical",
        "heroTagline": "Uy boshqaruvi va texnik xizmat bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-video-kuzatuv-va-smart-home": {
        "heroImageUrl": "https://loremflickr.com/1600/900/video,surveillance,camera",
        "heroTagline": "Video kuzatuv va Smart Home bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-xavfsizlik-tizimlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/security,system",
        "heroTagline": "Xavfsizlik tizimlari bo'yicha eng yaxshi takliflar",
    },
    "xizmat-korsatish-yuk-tashish-xizmatlari": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cargo,truck,transport",
        "heroTagline": "Yuk tashish xizmatlari bo'yicha eng yaxshi takliflar",
    },
    "yuk-mashina-haydovchisi": {
        "heroImageUrl": "https://loremflickr.com/1600/900/cargo,truck,car",
        "heroTagline": "Yuk mashina haydovchisi bo'yicha eng yaxshi takliflar",
    },
}


async def _backfill_category_theme(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    hero_image_url: str,
    hero_tagline: str,
    accent_color: str | None = None,
    now: datetime,
) -> None:
    """Self-heal for a category seeded before hero content existed (or before this theme table
    gained an entry for it) -- same publish-a-new-version pattern as `_backfill_listing_kind`,
    merged into the same `descriptor.metadata` slot the owner-admin panel's own hero-editing form
    already writes to. No-op once the stored values already match exactly, so this is safe (and
    cheap) to re-run on every deploy; a super-admin who has since hand-edited a category's hero
    from the panel keeps their own values only if they happen to match this table -- otherwise
    this backfill will overwrite them back to the table's defaults on the next deploy, same as
    `_backfill_listing_kind` already does for `listingKind`.

    `accent_color` is optional (unlike every top-level category, which gets one so no two of the
    18 read as visually identical) -- second-level-and-deeper categories deliberately omit it so
    `resolveAccentColor`'s ancestor-walk (`lib/listing-kind.ts`) keeps inheriting the nearest
    themed ancestor's color, the same "whole category family reads as one visual family" behavior
    that already existed before hero images reached this deep; only `heroImageUrl`/`heroTagline`
    are new at this depth."""
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
    }
    if accent_color is not None:
        desired["accentColor"] = accent_color
    if all(current_metadata.get(k) == v for k, v in desired.items()):
        return

    new_metadata = {**current_metadata, **desired}
    new_descriptor = {**current_descriptor, "metadata": new_metadata}
    new_document = {**current.definition_document, "descriptor": new_descriptor}

    new_version = await use_cases.create_version_draft(
        ConfigEntityType.CATEGORY,
        head.id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY,
        head.id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: backfill hero theme metadata",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: backfill hero theme metadata approval",
            now=now,
        )


def _slugify(text: str) -> str:
    """Latin-Uzbek-aware slug matching the convention the hand-written codes above already use
    (apostrophes drop rather than transliterate, so "Ko'p qavatli binolar" -> "kop-qavatli-
    binolar", same as the existing `kop-qavatli-binolar` top-level code)."""
    text = text.replace("'", "").replace("’", "").replace("‘", "")  # noqa: RUF001
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
    same as the flat map this replaced did implicitly for every path under a given prefix.

    `display_order` is assigned per sibling group via `enumerate` -- each recursive call gets its
    own fresh 1-based count over its own `nodes`, so a subtree's own children rank amongst
    themselves the same way `_seed_catalog_taxonomy` already ranks the top-level categories, and
    in the literal order the taxonomy data below already lists them in."""
    for order, node in enumerate(nodes, start=1):
        name, children = node if isinstance(node, tuple) else (node, [])
        path = f"{parent_path}/{_slugify(name)}"
        code = _slugify(path.lstrip("/"))
        head_id = await _seed_category(
            use_cases,
            repo,
            code=code,
            name=name,
            path=path,
            parent_category_id=parent_id,
            form_definition_id=form_definition_id,
            now=now,
            listing_kind=listing_kind,
            display_order=order,
        )
        if children:
            await _seed_subtree(
                use_cases,
                repo,
                children,
                parent_id=head_id,
                parent_path=path,
                form_definition_id=form_definition_id,
                now=now,
                listing_kind=listing_kind,
            )


def _kop_qavatli_binolar_tree() -> list[Node]:
    return [
        (
            "Yangi qurilishlar",
            [
                "1 xonali",
                "2 xonali",
                "3 xonali",
                "4+ xonali",
                "Family",
                "Duplex",
                "Loft",
                "Smart Apartment",
            ],
        ),
        "Ikkilamchi bozor",
        (
            "Premium turar joylar",
            [
                "Sky Residence",
                "Penthouse",
                "Terrace Apartment",
                "Smart Home",
                "Designer Interior",
            ],
        ),
        "Biznes klass",
        "Komfort klass",
        "Ekonom klass",
        "Penthouse",
        "Studio",
        (
            "Investitsiya uchun",
            [
                "Erta bosqich",
                "Qurilish jarayonida",
                "Tayyor loyiha",
                "Yuqori daromadli",
                "Tijorat uchun mos",
            ],
        ),
        "Ipotekali uylar",
        "Qurilishi davom etayotgan loyihalar",
        "Tayyor topshirilgan loyihalar",
    ]


def _kotejlar_tree() -> list[Node]:
    return [
        (
            "Oilaviy kotejlar",
            ["2 xonali", "3 xonali", "5+ xonali", "Bolalar maydonchali kotejlar"],
        ),
        (
            "Premium kotejlar",
            ["Basseynli", "Sauna va SPA'li", "Panoramali", "VIP xizmatli kotejlar"],
        ),
        "Luxury Villalar",
        (
            "Tog' kotejlari",
            [
                "Qishki dam olish uchun",
                "Yozgi dam olish uchun",
                "Ekstremal turizm uchun",
            ],
        ),
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
        (
            "Premium hovlilar",
            [
                "Zamonaviy villa",
                "Klassik villa",
                "Panoramali hovli",
                "Dizaynerlik interyeriga ega hovlilar",
            ],
        ),
        "Kottejlar",
        "Townhouse",
        (
            "Hovuzli hovlilar",
            ["Ochiq hovuz", "Yopiq hovuz", "Isitiladigan hovuz", "SPA zonali hovlilar"],
        ),
        "Katta yer maydoniga ega hovlilar",
        "Shahar ichidagi hovlilar",
        "Shahar tashqarisidagi hovlilar",
        "Investitsiya uchun hovlilar",
        "Qurilishi tugallanmagan hovlilar",
        (
            "Smart Home hovlilar",
            [
                "Avtomatlashtirilgan xavfsizlik tizimi",
                "Aqlli yoritish",
                "Aqlli iqlim boshqaruvi",
            ],
        ),
    ]


def _noturar_binolar_tree() -> list[Node]:
    return [
        (
            "Ofis binolari",
            [
                "Business Center",
                "Coworking",
                "Premium Office",
                "Open Space",
                "Alohida ofislar",
            ],
        ),
        (
            "Savdo markazlari",
            [
                "Butiklar",
                "Supermarketlar",
                "Showroomlar",
                "Savdo pavilyonlari",
                "Food court joylari",
            ],
        ),
        "Do'kon va butiklar",
        "Restoran va kafelar",
        "Mehmonxonalar",
        (
            "Omborxonalar",
            [
                "Logistika omborlari",
                "Sovutkich omborlari",
                "Distribyutor markazlari",
                "Sanoat omborlari",
            ],
        ),
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
            [
                "2 kishilik",
                "Oilaviy",
                "Katta guruhlar uchun",
                "Korporativ dam olish uchun",
                "Bayram tadbirlari uchun",
            ],
        ),
        "Haftalik va oylik ijara",
        (
            "Premium villalar",
            [
                "Smart Home",
                "VIP villa",
                "Panoramali villa",
                "Zamonaviy dizayndagi villalar",
            ],
        ),
        "Oilaviy dam olish hovlilari",
        "Tog' hududidagi dala hovlilar",
        "Ko'l yoki daryo bo'yidagi hovlilar",
        (
            "Hovuzli dala hovlilar",
            [
                "Ochiq hovuz",
                "Yopiq hovuz",
                "Isitiladigan hovuz",
                "Bolalar hovuzi",
                "Premium SPA zonali hovlilar",
            ],
        ),
        "Barbekyu va yozgi oshxonali hovlilar",
        "Investitsiya uchun dala hovlilar",
        "Yangi qurilgan dala hovlilar",
    ]


def _bosh_yerlar_tree() -> list[Node]:
    return [
        (
            "Turar joy qurish uchun yerlar",
            [
                "2 sotixgacha",
                "2-4 sotix",
                "4-6 sotix",
                "6-10 sotix",
                "10 sotixdan katta",
            ],
        ),
        (
            "Tijorat maqsadidagi yerlar",
            [
                "Savdo markazi uchun",
                "Ofis binosi uchun",
                "Omborxona uchun",
                "Mehmonxona uchun",
                "Restoran uchun",
            ],
        ),
        "Sanoat hududlari",
        (
            "Qishloq xo'jaligi yerlari",
            ["Bog'dorchilik", "Issiqxona", "Chorvachilik", "Dehqonchilik"],
        ),
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
            [
                "Ichki bo'yoq",
                "Tashqi bo'yoq",
                "Grunt",
                "Lak",
                "Emal",
                "Dekorativ qoplamalar",
            ],
        ),
        "Pol qoplamalari",
        "Eshik va derazalar",
        (
            "Mahkamlash mahsulotlari",
            ["Mix", "Vint", "Shurup", "Bolt", "Gayka", "Shayba", "Dyubel", "Anker"],
        ),
        "Qurilish asbob-uskunalari",
        "Maxsus texnika va jihozlar",
    ]


def _maishiy_texnikalar_tree() -> list[Node]:
    return [
        (
            "Muzlatgichlar",
            [
                "Ikki eshikli",
                "Side by Side",
                "Mini muzlatgichlar",
                "Smart muzlatgichlar",
            ],
        ),
        (
            "Kir yuvish mashinalari",
            [
                "Avtomatik",
                "Yarim avtomatik",
                "Quritish funksiyali",
                "Sanoat kir yuvish mashinalari",
            ],
        ),
        "Idish yuvish mashinalari",
        "Gaz plitalari va pechlar",
        "Mikroto'lqinli pechlar",
        "Changyutgichlar",
        "Konditsionerlar",
        "Televizorlar",
        "Suv isitkichlari",
        (
            "Oshxona texnikalari",
            [
                "Blenderlar",
                "Mikserlar",
                "Kofe mashinalari",
                "Multivarkalar",
                "Elektr choynaklar",
            ],
        ),
        "Kichik maishiy texnikalar",
        "Smart Home qurilmalari",
        "Iqlim texnikalari",
        "Premium texnikalar",
    ]


def _uy_bezaklari_tree() -> list[Node]:
    return [
        (
            "Devor bezaklari",
            [
                "3D panellar",
                "Dekorativ yog'och panellar",
                "Metall dekorlar",
                "Stikerlar",
                "Premium devor kompozitsiyalari",
            ],
        ),
        "Rasmlar va kartinalar",
        "Ko'zgular",
        (
            "Pardalar va jalyuzilar",
            ["Zamonaviy", "Klassik", "Blackout", "Avtomatik", "Premium kolleksiyalar"],
        ),
        "Gilam va pol qoplamalari",
        (
            "Dekorativ yoritish",
            [
                "LED yoritish",
                "Osma chiroqlar",
                "Tungi lampalar",
                "Dizayner lampalari",
                "Aqlli yoritish tizimlari",
            ],
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
        (
            "Qurilish kiyimlari",
            [
                "Kurtka",
                "Shim",
                "Kombinezon",
                "Jilet",
                "Yomg'ir kiyimi",
                "Termo kiyimlar",
            ],
        ),
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
            [
                "Etik",
                "Botinka",
                "Yozgi poyabzal",
                "Qishki poyabzal",
                "Suv o'tkazmaydigan poyabzal",
                "Metall burunli poyabzal",
            ],
        ),
        (
            "Himoya vositalari",
            [
                "Kaska",
                "Qo'lqop",
                "Ko'zoynak",
                "Respirator",
                "Niqob",
                "Quloqchin",
                "Xavfsizlik kamarlari",
            ],
        ),
        "Mavsumiy ish kiyimlari",
    ]


def _mebel_materiallari_tree() -> list[Node]:
    return [
        ("Yog'och materiallari", ["Eman", "Qarag'ay", "Yong'oq", "Buk", "MDF", "DSP"]),
        "MDF va DSP plitalari",
        "Fanera va laminatlar",
        "Stoleshnitsalar",
        (
            "Mebel furnituralari",
            [
                "Ilgaklar",
                "Menteshalar",
                "Relslar",
                "Lift tizimlari",
                "Magnitlar",
                "Qulflar",
            ],
        ),
        "Tutqich va aksessuarlar",
        "Sharnir va rels tizimlari",
        "Mebel oyoqlari va tayanchlari",
        "Shisha va oyna mahsulotlari",
        "Yumshoq mebel materiallari",
        (
            "Mato va charm qoplamalar",
            ["Velyur", "Eko charm", "Tabiiy charm", "Mikrofiber"],
        ),
        "Yelim va kimyoviy mahsulotlar",
        "Bo'yoq va laklar",
        "Mebel ishlab chiqarish asboblari",
    ]


def _mebel_salonlari_tree() -> list[Node]:
    return [
        (
            "Oshxona mebellari",
            ["Zamonaviy", "Klassik", "Minimalistik", "Premium oshxona garniturlari"],
        ),
        "Yotoqxona mebellari",
        "Mehmonxona mebellari",
        "Bolalar xonasi mebellari",
        (
            "Ofis mebellari",
            [
                "Ish stollari",
                "Ofis stullari",
                "Konferensiya stollari",
                "Shkaflar",
                "Resepsion mebellari",
            ],
        ),
        (
            "Yumshoq mebellar",
            [
                "Divanlar",
                "Burchak divanlar",
                "Kreslolar",
                "Puflar",
                "Transformatsiyalanuvchi mebellar",
            ],
        ),
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
        (
            "Mehmonxonalar",
            [
                "3 yulduzli",
                "4 yulduzli",
                "5 yulduzli",
                "Boutique Hotel",
                "Business Hotel",
                "Family Hotel",
            ],
        ),
        "Dala hovlilar",
        "Villalar",
        "Kottejlar",
        "Kurort va sanatoriyalar",
        (
            "Hovuz va akvaparklar",
            [
                "Ochiq hovuz",
                "Yopiq hovuz",
                "Bolalar akvaparki",
                "VIP zonalar",
                "Family zonalari",
            ],
        ),
        (
            "SPA va Wellness markazlari",
            [
                "Sauna",
                "Hammom",
                "Massaj",
                "Fitnes",
                "Termal hovuz",
                "Sog'lomlashtirish xizmatlari",
            ],
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
            [
                "Zamonaviy bog'",
                "Klassik bog'",
                "Yapon bog'i",
                "Minimalistik bog'",
                "Mevali bog'",
                "Dekorativ bog'",
            ],
        ),
        "Park va yashil hududlar",
        "Avtomatik sug'orish tizimlari",
        "Gazon va maysa ishlari",
        "Daraxt va gul ekish",
        "Dekorativ tosh va yo'laklar",
        "Favvora va sun'iy suv havzalari",
        (
            "Tashqi yoritish tizimlari",
            [
                "Quyosh energiyasida ishlovchi chiroqlar",
                "LED yoritish",
                "Dekorativ yoritish",
                "Aqlli yoritish tizimlari",
            ],
        ),
        "Pergola va ayvonlar",
        (
            "Tashqi dam olish zonalari",
            [
                "Yozgi oshxona",
                "Barbekyu zonasi",
                "Pergola",
                "Gazebo",
                "Ochiq terassa",
                "Bolalar maydonchasi",
            ],
        ),
        "Vertikal bog'lar",
        "Tom bog'lari (Roof Garden)",
        "Landshaft parvarishlash xizmatlari",
    ]


def _ish_orni_tree() -> list[Node]:
    return [
        (
            "Qurilish ishlari",
            [
                "Betonchi",
                "G'isht teruvchi",
                "Suvoqchi",
                "Armaturachi",
                "Payvandchi",
                "Tom yopuvchi",
            ],
        ),
        (
            "Usta xizmatlari",
            [
                "Elektrchi",
                "Santexnik",
                "Konditsioner ustasi",
                "Mebel ustasi",
                "Bo'yoqchi",
            ],
        ),
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
            [
                "Frontend dasturchi",
                "Backend dasturchi",
                "Mobil dasturchi",
                "UI/UX dizayner",
                "System Administrator",
            ],
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
            [
                "Kosmetik ta'mirlash",
                "Kapital ta'mirlash",
                "Ofis ta'miri",
                "Kvartira ta'miri",
                "Fasad ishlari",
            ],
        ),
        "Usta xizmatlari",
        (
            "Elektrik xizmatlari",
            [
                "Sim tortish",
                "Elektr qalqonlarini o'rnatish",
                "Yoritish tizimlari",
                "Smart Home elektr tizimlari",
                "Avariya xizmatlari",
            ],
        ),
        "Santexnika xizmatlari",
        "Konditsioner va ventilyatsiya",
        (
            "Tozalash xizmatlari",
            [
                "Kundalik tozalash",
                "General tozalash",
                "Ofis tozalash",
                "Qurilishdan keyingi tozalash",
                "Kimyoviy tozalash",
            ],
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
        (
            "Talabalar hosteli",
            [
                "Universitetlarga yaqin hostellar",
                "Oylik ijarali hostellar",
                "Umumiy yashash xonalari",
            ],
        ),
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
        (
            "Business Hotel",
            [
                "Konferensiya zallari",
                "Coworking zonalari",
                "Biznes xizmatlariga ega mehmonxonalar",
            ],
        ),
        (
            "Resort Hotel",
            ["Beach Resort", "Mountain Resort", "Wellness Resort", "Family Resort"],
        ),
        "Apart Hotel",
        "Family Hotel",
        "Spa Hotel",
        "Airport Hotel",
        "Mountain Hotel",
        "City Hotel",
        (
            "Luxury Hotel",
            ["Presidential Suite", "Royal Suite", "Deluxe Room", "Executive Room"],
        ),
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
    top_level_order = itertools.count(2)
    """One shared counter for every top-level (`parent_category_id=None`) category seeded below,
    regardless of which block/loop creates it -- they are all siblings in the SAME group, so they
    need one running sequence, not a fresh one per block. Starts at 2, not 1: `_seed_furniture_
    category` (called earlier in `run_seed`, also `parent_category_id=None`) already claims 1 --
    same top-level sibling group, same sequence. Assigns `display_order` in the exact order this
    function already lists them in (unchanged from before this fix), fixing the homepage
    category-chip reshuffle bug (`CategoryReadUseCases.list_categories` now sorts on this
    field)."""

    # -- Residential/commercial buildings (a single shared form -- these differ by neighbourhood/
    # type, not by attribute shape).
    re_form_id = await _seed_form(
        use_cases,
        repo,
        code="ko-chmas-mulk-form",
        name="Ko'chmas mulk",
        fields=_property_fields(),
        now=now,
    )
    for code, name, path, tree in [
        (
            "kop-qavatli-binolar",
            "Ko'p qavatli binolar",
            "/kop-qavatli-binolar",
            _kop_qavatli_binolar_tree(),
        ),
        ("kotejlar", "Kotejlar", "/kotejlar", _kotejlar_tree()),
        ("hovlilar", "Hovlilar", "/hovlilar", _hovlilar_tree()),
        (
            "noturar-binolar",
            "Noturar binolar",
            "/noturar-binolar",
            _noturar_binolar_tree(),
        ),
        ("dala-hovlilar", "Dala hovlilar", "/dala-hovlilar", _dala_hovlilar_tree()),
    ]:
        head_id = await _seed_category(
            use_cases,
            repo,
            code=code,
            name=name,
            path=path,
            parent_category_id=None,
            form_definition_id=re_form_id,
            now=now,
            display_order=next(top_level_order),
        )
        await _seed_subtree(
            use_cases,
            repo,
            tree,
            parent_id=head_id,
            parent_path=path,
            form_definition_id=re_form_id,
            now=now,
        )

    # -- Land.
    land_form_id = await _seed_form(
        use_cases,
        repo,
        code="bosh-yer-form",
        name="Bo'sh yer",
        fields=_land_fields(),
        now=now,
    )
    bosh_yerlar_head_id = await _seed_category(
        use_cases,
        repo,
        code="bosh-yerlar",
        name="Bo'sh yerlar",
        path="/bosh-yerlar",
        parent_category_id=None,
        form_definition_id=land_form_id,
        now=now,
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _bosh_yerlar_tree(),
        parent_id=bosh_yerlar_head_id,
        parent_path="/bosh-yerlar",
        form_definition_id=land_form_id,
        now=now,
    )

    # -- Goods (physical-unit sales).
    goods_form_id = await _seed_form(
        use_cases,
        repo,
        code="mahsulot-form",
        name="Mahsulot",
        fields=_goods_fields(),
        now=now,
    )
    for code, name, path, tree in [
        (
            "qurilish-materiallari",
            "Qurilish materiallari",
            "/qurilish-materiallari",
            _qurilish_materiallari_tree(),
        ),
        (
            "maishiy-texnikalar",
            "Maishiy texnikalar",
            "/maishiy-texnikalar",
            _maishiy_texnikalar_tree(),
        ),
        ("uy-bezaklari", "Uy bezaklari", "/uy-bezaklari", _uy_bezaklari_tree()),
        (
            "uniforma-va-maxsus-kiyimlar",
            "Uniforma va maxsus kiyimlar",
            "/uniforma-va-maxsus-kiyimlar",
            _uniforma_tree(),
        ),
    ]:
        head_id = await _seed_category(
            use_cases,
            repo,
            code=code,
            name=name,
            path=path,
            parent_category_id=None,
            form_definition_id=goods_form_id,
            now=now,
            listing_kind="GOODS",
            display_order=next(top_level_order),
        )
        await _seed_subtree(
            use_cases,
            repo,
            tree,
            parent_id=head_id,
            parent_path=path,
            form_definition_id=goods_form_id,
            now=now,
            listing_kind="GOODS",
        )

    # -- Hospitality.
    hosp_form_id = await _seed_form(
        use_cases,
        repo,
        code="mehmonxona-form",
        name="Mehmonxona/Hostel",
        fields=_hospitality_fields(),
        now=now,
    )
    for code, name, path, tree in [
        ("hostel", "Hostel", "/hostel", _hostel_tree()),
        ("mexmonxona", "Mexmonxona", "/mexmonxona", _mexmonxona_tree()),
    ]:
        head_id = await _seed_category(
            use_cases,
            repo,
            code=code,
            name=name,
            path=path,
            parent_category_id=None,
            form_definition_id=hosp_form_id,
            now=now,
            listing_kind="VENUE",
            display_order=next(top_level_order),
        )
        await _seed_subtree(
            use_cases,
            repo,
            tree,
            parent_id=head_id,
            parent_path=path,
            form_definition_id=hosp_form_id,
            now=now,
            listing_kind="VENUE",
        )

    # -- Business directory (showrooms, not units).
    business_form_id = await _seed_form(
        use_cases,
        repo,
        code="biznes-korxona-form",
        name="Biznes/korxona",
        fields=_business_fields(),
        now=now,
    )
    mebel_salonlari_head_id = await _seed_category(
        use_cases,
        repo,
        code="mebel-salonlari",
        name="Mebel salonlari",
        path="/mebel-salonlari",
        parent_category_id=None,
        form_definition_id=business_form_id,
        now=now,
        listing_kind="GOODS",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _mebel_salonlari_tree(),
        parent_id=mebel_salonlari_head_id,
        parent_path="/mebel-salonlari",
        form_definition_id=business_form_id,
        now=now,
        listing_kind="GOODS",
    )

    # -- Recreation venues (new, per this session's request).
    venue_form_id = await _seed_form(
        use_cases,
        repo,
        code="dam-olish-maskani-form",
        name="Dam olish maskani",
        fields=_venue_fields(),
        now=now,
    )
    dam_olish_head_id = await _seed_category(
        use_cases,
        repo,
        code="dam-olish-maskanlari",
        name="Dam olish maskanlari",
        path="/dam-olish-maskanlari",
        parent_category_id=None,
        form_definition_id=venue_form_id,
        now=now,
        listing_kind="VENUE",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _dam_olish_maskanlari_tree(),
        parent_id=dam_olish_head_id,
        parent_path="/dam-olish-maskanlari",
        form_definition_id=venue_form_id,
        now=now,
        listing_kind="VENUE",
    )

    # -- Landshaft dizayni: a design SERVICE, not goods -- the base CV shape, no trade extras.
    landshaft_form_id = await _seed_form(
        use_cases,
        repo,
        code="landshaft-xizmati-form",
        name="Landshaft dizayni xizmati",
        fields=_service_cv_fields(),
        now=now,
    )
    landshaft_head_id = await _seed_category(
        use_cases,
        repo,
        code="landshaft-dizayni",
        name="Landshaft dizayni",
        path="/landshaft-dizayni",
        parent_category_id=None,
        form_definition_id=landshaft_form_id,
        now=now,
        listing_kind="SERVICE",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _landshaft_tree(),
        parent_id=landshaft_head_id,
        parent_path="/landshaft-dizayni",
        form_definition_id=landshaft_form_id,
        now=now,
        listing_kind="SERVICE",
    )

    # -- Ish o'rni (job postings) -- same CV shape; here `specialization`/`experience_years` read
    # as the employer's requirement rather than the applicant's own.
    ish_orni_form_id = await _seed_form(
        use_cases,
        repo,
        code="ish-orni-form",
        name="Ish o'rni",
        fields=_service_cv_fields(),
        now=now,
    )
    ish_orni_head_id = await _seed_category(
        use_cases,
        repo,
        code="ish-orni",
        name="Ish o'rni",
        path="/ish-orni",
        parent_category_id=None,
        form_definition_id=ish_orni_form_id,
        now=now,
        listing_kind="SERVICE",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _ish_orni_tree(),
        parent_id=ish_orni_head_id,
        parent_path="/ish-orni",
        form_definition_id=ish_orni_form_id,
        now=now,
        listing_kind="SERVICE",
    )

    # -- Xizmat ko'rsatish: the services directory. A CV-shaped child category per trade so
    # someone hiring a repairman/driver/truck-driver browses candidates exactly like any other
    # category's listings -- new listing = new "CV" entry, searchable by specialization/region/
    # rate via the same `catalogClient.listingsByCategoryPath` every other category already uses.
    services_form_id = await _seed_form(
        use_cases,
        repo,
        code="xizmat-korsatish-form",
        name="Xizmat ko'rsatish",
        fields=_service_cv_fields(),
        now=now,
    )
    services_head_id = await _seed_category(
        use_cases,
        repo,
        code="xizmat-korsatish",
        name="Xizmat ko'rsatish",
        path="/xizmat-korsatish",
        parent_category_id=None,
        form_definition_id=services_form_id,
        now=now,
        listing_kind="SERVICE",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _xizmat_korsatish_tree(),
        parent_id=services_head_id,
        parent_path="/xizmat-korsatish",
        form_definition_id=services_form_id,
        now=now,
        listing_kind="SERVICE",
    )

    tamirchi_form_id = await _seed_form(
        use_cases,
        repo,
        code="tamirchi-form",
        name="Ta'mirchi",
        fields=_service_cv_fields(
            extra=[
                _field(
                    "trade",
                    "asosiy",
                    "Yo'nalish",
                    "select",
                    required=True,
                    facet=True,
                    order=10,
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
        use_cases,
        repo,
        code="tamirchi-xizmati",
        name="Ta'mirchi",
        path="/tamirchi",
        parent_category_id=services_head_id,
        form_definition_id=tamirchi_form_id,
        now=now,
        listing_kind="SERVICE",
        # 100+, not 1/2/3 -- these three are siblings of `_xizmat_korsatish_tree()`'s own nodes
        # (also parented under `services_head_id`), which already number themselves 1..N via
        # `_seed_subtree`'s own `enumerate`; a fixed high base keeps these three (seeded first,
        # historically) sorting after that tree without needing to know its size.
        display_order=100,
    )

    haydovchi_form_id = await _seed_form(
        use_cases,
        repo,
        code="haydovchi-form",
        name="Mashina haydovchisi",
        fields=_service_cv_fields(
            extra=[
                _field(
                    "license_category",
                    "asosiy",
                    "Haydovchilik guvohnomasi toifasi",
                    "select",
                    required=True,
                    facet=True,
                    order=10,
                    options=[
                        ("B", "B"),
                        ("C", "C"),
                        ("D", "D"),
                        ("BE", "BE"),
                        ("CE", "CE"),
                    ],
                ),
                _field(
                    "own_vehicle",
                    "asosiy",
                    "O'z avtomobili bor",
                    "boolean",
                    facet=True,
                    order=11,
                    default=False,
                ),
            ]
        ),
        now=now,
    )
    await _seed_category(
        use_cases,
        repo,
        code="mashina-haydovchisi",
        name="Mashina haydovchisi",
        path="/haydovchi",
        parent_category_id=services_head_id,
        form_definition_id=haydovchi_form_id,
        now=now,
        listing_kind="SERVICE",
        display_order=101,
    )

    yuk_haydovchi_form_id = await _seed_form(
        use_cases,
        repo,
        code="yuk-haydovchi-form",
        name="Yuk mashina haydovchisi",
        fields=_service_cv_fields(
            extra=[
                _field(
                    "license_category",
                    "asosiy",
                    "Haydovchilik guvohnomasi toifasi",
                    "select",
                    required=True,
                    facet=True,
                    order=10,
                    options=[("C", "C"), ("CE", "CE"), ("D", "D"), ("DE", "DE")],
                ),
                _field(
                    "vehicle_type",
                    "asosiy",
                    "Yuk mashina turi",
                    "select",
                    facet=True,
                    order=11,
                    options=[
                        ("gazelle", "Gazel / kichik yuk"),
                        ("truck", "Yuk mashina"),
                        ("trailer", "Tirkamali yuk mashina"),
                        ("refrigerator", "Refrijerator"),
                    ],
                ),
                _field(
                    "cargo_capacity_tons",
                    "asosiy",
                    "Yuk ko'tarish sig'imi (tonna)",
                    "number",
                    facet=True,
                    order=12,
                ),
            ]
        ),
        now=now,
    )
    await _seed_category(
        use_cases,
        repo,
        code="yuk-mashina-haydovchisi",
        name="Yuk mashina haydovchisi",
        path="/yuk-haydovchi",
        parent_category_id=services_head_id,
        form_definition_id=yuk_haydovchi_form_id,
        now=now,
        listing_kind="SERVICE",
        display_order=102,
    )

    # -- Every top-level category gets its own themed hero image/tagline/accent color (Task:
    # category mini-platform redesign) -- idempotent, safe to re-run every deploy.
    for code, theme in _TOP_LEVEL_CATEGORY_HERO_THEMES.items():
        await _backfill_category_theme(
            use_cases,
            repo,
            code=code,
            hero_image_url=theme["heroImageUrl"],
            hero_tagline=theme["heroTagline"],
            accent_color=theme["accentColor"],
            now=now,
        )

    # -- Every subcategory also gets a themed hero image now (Task: subcategory hero images) --
    # no accent_color, see _SUBCATEGORY_HERO_THEMES's own docstring for why. A code with no
    # matching head yet (a subtree not seeded in this environment) is a silent no-op --
    # _backfill_category_theme already returns early when the head doesn't exist.
    for code, theme in _SUBCATEGORY_HERO_THEMES.items():
        await _backfill_category_theme(
            use_cases,
            repo,
            code=code,
            hero_image_url=theme["heroImageUrl"],
            hero_tagline=theme["heroTagline"],
            now=now,
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
                    repo,
                    code="super-admin",
                    role_name="Super Administrator",
                    permission_keys=_super_admin_permission_keys(),
                    now=now,
                )
                await _seed_role(
                    use_cases,
                    repo,
                    code="administrator",
                    role_name="Administrator",
                    permission_keys=_administrator_permission_keys(),
                    now=now,
                )
                await _seed_platform_settings(use_cases, now=now)
                await _backfill_platform_settings_defaults(use_cases, repo, now=now)

                furniture_form_id = await _seed_furniture_form(use_cases, repo, now=now)
                furniture_head_id = await _seed_furniture_category(
                    use_cases, repo, form_definition_id=furniture_form_id, now=now
                )
                await _seed_subtree(
                    use_cases,
                    repo,
                    _mebel_materiallari_tree(),
                    parent_id=furniture_head_id,
                    parent_path="/mebel-materiallari",
                    form_definition_id=furniture_form_id,
                    now=now,
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
