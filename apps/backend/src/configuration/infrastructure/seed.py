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
    if sorted(current.definition_document.get("permission_keys") or []) == sorted(
        permission_keys
    ):
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


async def _seed_platform_settings(
    use_cases: ConfigurationUseCases, *, now: datetime
) -> None:
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

    approve_key = _registry.approve_permission_key(
        ConfigEntityType.PLATFORM_SETTINGS.value
    )
    manage_key = _registry.manage_permission_key(
        ConfigEntityType.PLATFORM_SETTINGS.value
    )
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
        k: v
        for k, v in _PLATFORM_SETTINGS_ADDITIVE_DEFAULTS.items()
        if k not in current_settings
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
    manage_key = _registry.manage_permission_key(
        ConfigEntityType.PLATFORM_SETTINGS.value
    )
    approve_key = _registry.approve_permission_key(
        ConfigEntityType.PLATFORM_SETTINGS.value
    )
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


_SEARCH_CONFIGURATION_ADDITIVE_FACETS: dict[str, str] = {
    "brand": "Brend",
    "material": "Material",
    "condition": "Holati",
    "delivery_available": "Yetkazib berish mavjud",
    "rooms": "Xonalar soni",
    "area_sqm": "Maydon (m2)",
    "floor": "Qavat",
    "total_floors": "Binodagi qavatlar soni",
    "district": "Tuman",
    "building_type": "Bino turi",
    "has_basement": "Podval / Yerto'la",
    "balcony": "Balkon",
    "lot_size_sotix": "Yer maydoni (sotix)",
    "has_attic": "Mansarda",
    "basement_type": "Podval turi",
    "utilities": "Kommunikatsiya",
    "commercial_floor": "Bino joylashgan qavat",
    "building_position_type": "Bino turi / Joylashuvi",
    "sewage_water": "Kanalizatsiya va Suv",
    "power_capacity": "Elektr quvvati",
    "parking": "Avtoturargoh",
    "resort_area": "Hudud / Yo'nalish",
    "guest_capacity": "Sig'im (Odam soni)",
    "pool_type": "Basseyn turi",
    "sauna_type": "Sauna / Hammom",
    "billiards_tennis_ps": "Bilyard / Tennis / PlayStation",
    "tapchan_summer_kitchen": "Tapchan va Yozgi oshxona",
    "playground": "Bolalar maydonchasi",
    "ownership_type": "Mulkchilik / Hujjat turi",
    "location_condition": "Yer joylashuvi / Sharoiti",
    "terrain_shape": "Yer shakli / Relyefi",
    "gas_supply": "Gaz ta'minoti",
    "electricity_supply": "Elektr energiyasi",
    "water_supply": "Suv ta'minoti",
    "seller_type": "Sotuvchi turi",
    "sale_unit": "Sotish hajmi / Birlik",
    "delivery": "Yetkazib berish (Dostavka)",
    "payment_method": "To'lov shakli",
    "appliance_brand": "Brend / Markasi",
    "warranty": "Kafolat (Garantiya)",
    "delivery_install": "Yetkazib berish va O'rnatish",
    "style": "Dizayn uslubi (Stil)",
    "size": "O'lcham (Size)",
    "season": "Mavsumiylik (Mavsum)",
    "gender": "Jins (Kim uchun)",
    "deal_type": "Bitim turi",
    "area_sotix": "Maydon (sotix)",
    "land_purpose": "Yer maqsadi",
    "has_documents": "Hujjatlari bor",
    "room_capacity": "Xona sig'imi (kishi)",
    "amenities": "Qulayliklar",
    "venue_type": "Maskan turi",
    "capacity": "Sig'imi (kishi)",
    "experience_years": "Tajriba (yil)",
    "specialization": "Mutaxassislik",
    "rate_type": "Narx turi",
    "available_now": "Hozir band emas",
}
"""Every `field_code` marked `facet=True` in this file's own `_property_fields`/`_goods_fields`/
etc helpers (source of truth: `code`/`facet` args passed to `_field(...)` throughout this module),
kept in sync by hand whenever a helper's field list changes -- `floor`/`total_floors`/`district`/
`building_type`/`has_basement`/`balcony` were added alongside `_property_fields()` itself
(2026-08-22, in response to a real ask: the listing-creation form and the filter panel must cover
the identical field set, or a filter shows up with nothing to actually filter). The rest were
collected live via `GET /categories/{id}/form` across all 18 top-level categories when this dict
was first written. `search.domain.query.SearchQuery.filters` term-matches
against `attributes.<code>`, always alongside a `category_id` filter in the same query
(`search/infrastructure/opensearch_index.py`'s `_build_query_body`), so one shared global list is
safe: a code from category A's form simply never matches category B's documents, which don't
carry that attribute at all. Without this, `filters[code]=value` is silently a no-op for every
code not in the currently-published `global-search` config's `facets` list (confirmed live: real
estate's `filters[condition]=<any value, even nonexistent>` returned the identical result count
as no filter at all) -- the field being real and `facetEligible: true` on its own form is a
precondition, not the actual enforcement; only being in a published `SearchConfiguration.facets`
list is."""


async def _backfill_search_configuration_facets(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    now: datetime,
) -> None:
    """Adds any `_SEARCH_CONFIGURATION_ADDITIVE_FACETS` entry missing from the published
    `global-search` head's `facets` list. Additive-only, same convention as
    `_backfill_platform_settings_defaults` above -- never removes or reorders an already-published
    facet, so a future owner-admin panel edit to this list is never silently reverted by a later
    deploy re-running this seed."""
    head = await repo.get_head_by_code(
        ConfigEntityType.SEARCH_CONFIGURATION, "global-search"
    )
    if head is None or head.current_version_id is None:
        return
    current = await repo.get_version(
        ConfigEntityType.SEARCH_CONFIGURATION, head.id, head.current_version_id
    )
    if current is None:
        return
    current_facets: list[dict[str, object]] = list(
        current.definition_document.get("facets") or []
    )
    existing_codes = {f.get("field_code") for f in current_facets}
    missing = {
        code: label
        for code, label in _SEARCH_CONFIGURATION_ADDITIVE_FACETS.items()
        if code not in existing_codes
    }
    if not missing:
        return

    new_facets = current_facets + [
        {
            "field_code": code,
            "label": {"uz_latn": label},
            "order": len(current_facets) + i,
        }
        for i, (code, label) in enumerate(missing.items())
    ]
    new_document = {**current.definition_document, "facets": new_facets}
    new_version = await use_cases.create_version_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = _registry.manage_permission_key(
        ConfigEntityType.SEARCH_CONFIGURATION.value
    )
    approve_key = _registry.approve_permission_key(
        ConfigEntityType.SEARCH_CONFIGURATION.value
    )
    step1 = await use_cases.publish(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: backfill missing search-configuration facets",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="seed: backfill missing search-configuration facets approval",
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
            raise RuntimeError(
                f"seed marker {code!r} vanished between check and lookup"
            ) from None
        return existing.id

    manage_key = _registry.manage_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    approve_key = _registry.approve_permission_key(
        ConfigEntityType.FORM_DEFINITION.value
    )
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
            raise RuntimeError(
                f"seed marker {code!r} vanished between check and lookup"
            ) from None
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
        field["options"] = [
            {"value": v, "label": {"uz_latn": lbl}} for v, lbl in options
        ]
    if default is not None:
        field["default_value"] = default
    return field


_TASHKENT_DISTRICTS: list[tuple[str, str]] = [
    ("bektemir", "Bektemir"),
    ("chilonzor", "Chilonzor"),
    ("yashnobod", "Yashnobod"),
    ("mirobod", "Mirobod"),
    ("mirzo-ulugbek", "Mirzo Ulug'bek"),
    ("olmazor", "Olmazor"),
    ("sergeli", "Sergeli"),
    ("shayxontohur", "Shayxontohur"),
    ("uchtepa", "Uchtepa"),
    ("yakkasaroy", "Yakkasaroy"),
    ("yunusobod", "Yunusobod"),
]
"""Tashkent's 11 real administrative districts -- almost every seeded property listing's
coordinates fall inside Tashkent city, and these are the actual district names (not invented
options), used wherever a real-estate category needs a "Tuman" facet."""

_TASHKENT_REGION_DISTRICTS: list[tuple[str, str]] = [
    ("bekobod-tumani", "Bekobod tumani"),
    ("bostonliq", "Bo'stonliq tumani"),
    ("qibray", "Qibray tumani"),
    ("ohangaron-tumani", "Ohangaron tumani"),
    ("oqqorgon", "Oqqo'rg'on tumani"),
    ("parkent", "Parkent tumani"),
    ("piskent", "Piskent tumani"),
    ("chinoz", "Chinoz tumani"),
    ("quyi-chirchiq", "Quyi Chirchiq tumani"),
    ("orta-chirchiq", "O'rta Chirchiq tumani"),
    ("yuqori-chirchiq", "Yuqori Chirchiq tumani"),
    ("yangiyol-tumani", "Yangiyo'l tumani"),
    ("zangiota", "Zangiota tumani"),
]
"""Toshkent viloyati's real tumanlari (13) -- appended onto the shared `_property_fields()`
"district" field's existing Tashkent-*city*-only options via `_backfill_form_definition_field_
options` (2026-08-23, "Kotejlar" TZ: cottages are disproportionately located in the region, not
the city). Deliberately excludes cities of regional subordination (Angren/Olmaliq/Chirchiq-shahar/
etc.) and doesn't attempt "Toshkent tumani" -- kept to the well-established tuman list to avoid
guessing at administrative-division edge cases."""


def _property_fields() -> list[dict[str, object]]:
    """Ko'p qavatli binolar / kotejlar / hovlilar / noturar binolar / dala hovlilar -- the
    residential/commercial-building direction.

    `order` (2026-08-23 UX rewrite) follows a real ask: the filter grid must read row-by-row as
    search intent actually narrows -- location/room-count first, then building/lot specs, then
    amenities -- not whatever order fields happened to get added to this file in. Subcategory and
    price aren't `_field()` entries at all (`CategoryFilterPanel` renders both ahead of `fields`
    unconditionally -- see that component's own docstring), so `district`/`rooms` at order 1-2
    land as the grid's 3rd/4th cell, completing row 1. `deal_type`/`floor`/`building_type`/
    `has_basement` get pushed past the requested 12-field grid (order 90+) rather than removed --
    Kotejlar's new subcategories now cover "sale vs rental" and `basement_type` supersedes
    `has_basement`'s coarser yes/no, but `deal_type`/`has_basement` are still the ONLY signal the
    other 4 categories sharing this form have for those facts, and `floor`/`building_type` are
    still real, useful facets -- deliberately kept, just deprioritized rather than deleted."""
    return [
        _field(
            "district",
            "asosiy",
            "Tuman",
            "select",
            facet=True,
            order=1,
            options=_TASHKENT_DISTRICTS,
        ),
        _field("rooms", "asosiy", "Xonalar soni", "number", facet=True, order=2),
        _field(
            "lot_size_sotix",
            "asosiy",
            "Yer maydoni (sotix)",
            "number",
            facet=True,
            order=3,
        ),
        _field("area_sqm", "asosiy", "Maydon (m2)", "number", facet=True, order=4),
        _field(
            "total_floors",
            "asosiy",
            "Binodagi qavatlar soni",
            "number",
            facet=True,
            order=5,
        ),
        _field(
            "condition",
            "asosiy",
            "Holati",
            "select",
            facet=True,
            order=6,
            options=[
                ("new", "Yangi ta'mirlangan"),
                ("good", "O'rtacha holatda"),
                ("needs_repair", "Ta'mir talab"),
            ],
        ),
        _field(
            "basement_type",
            "asosiy",
            "Podval turi",
            "select",
            facet=True,
            order=7,
            options=[
                ("none", "Yo'q"),
                ("livable", "Bor (Turar joy qilingan)"),
                ("storage", "Bor (Omborxona/Texnik)"),
            ],
        ),
        _field(
            "has_attic",
            "asosiy",
            "Mansarda",
            "boolean",
            facet=True,
            order=8,
            default=False,
        ),
        _field(
            "balcony",
            "asosiy",
            "Balkon",
            "select",
            facet=True,
            order=9,
            options=[
                ("none", "Yo'q"),
                ("one", "Bor"),
                ("two_plus", "2 va undan ortiq"),
            ],
        ),
        _field(
            "amenities",
            "asosiy",
            "Qulayliklar",
            "multiselect",
            facet=True,
            order=10,
            options=[
                ("pool_outdoor", "Basseyn (ochiq)"),
                ("pool_indoor", "Basseyn (yopiq)"),
                ("sauna", "Sauna / Hammom"),
                ("garage", "Garaj / Avtoturargoh"),
                ("summer_kitchen", "Yozgi oshxona"),
                ("terrace", "Terrasa"),
                ("utilities_uninterrupted", "Gaz, suv, elektr (uzliksiz)"),
                ("sewage", "Kanalizatsiya tizimi"),
            ],
        ),
        _field(
            "utilities",
            "asosiy",
            "Kommunikatsiya",
            "multiselect",
            facet=True,
            order=11,
            options=[
                ("gas", "Gaz"),
                ("water", "Suv"),
                ("electricity", "Elektr"),
                ("sewage_line", "Kanalizatsiya"),
                ("internet", "Internet"),
            ],
        ),
        _field("floor", "asosiy", "Qavat", "number", facet=True, order=90),
        _field(
            "building_type",
            "asosiy",
            "Bino turi",
            "select",
            facet=True,
            order=91,
            options=[
                ("brick", "G'ishtli"),
                ("panel", "Panel"),
                ("monolith", "Monolit"),
                ("block", "Blok"),
            ],
        ),
        _field(
            "has_basement",
            "asosiy",
            "Podval / Yerto'la",
            "boolean",
            facet=True,
            order=92,
            default=False,
        ),
        _field(
            "deal_type",
            "asosiy",
            "Bitim turi",
            "select",
            required=True,
            facet=True,
            order=93,
            options=[("sale", "Sotish"), ("rent", "Ijaraga berish")],
        ),
    ]


def _commercial_fields() -> list[dict[str, object]]:
    """Noturar binolar (tijorat ko'chmas mulki) -- 2026-08-23 split off from the shared
    `_property_fields()` residential form into its own `FormDefinition` ("tijorat-mulk-form").
    Two reasons, not one: (a) commercial listings need fields with no residential equivalent
    (floor-*type* select, not a numeric floor; building-position-type; power capacity; parking),
    and (b) the real reason for a full split rather than just adding fields -- `order` lives on
    the FIELD, shared by every category on one form, so `deal_type`/`district`/`condition`
    (fields this direction DOES share with residential) needed a genuinely different priority
    order than Kotejlar/Hovlilar's already-confirmed one. A dedicated form gives this direction
    its own independent order sequence, same principle as `_land_fields()` already being separate
    from `_property_fields()`. `district` reuses the same real option lists (Tashkent city +
    region) rather than re-typing them."""
    return [
        _field(
            "district",
            "asosiy",
            "Tuman",
            "select",
            facet=True,
            order=1,
            options=_TASHKENT_DISTRICTS + _TASHKENT_REGION_DISTRICTS,
        ),
        _field(
            "deal_type",
            "asosiy",
            "Bitim turi",
            "select",
            required=True,
            facet=True,
            order=2,
            options=[
                ("sale", "Sotiladi"),
                ("rent", "Ijaraga beriladi (Uzoq muddatli)"),
                ("daily_rent", "Sutkalik ijara"),
            ],
        ),
        _field(
            "area_sqm", "asosiy", "Umumiy maydon (m2)", "number", facet=True, order=3
        ),
        _field(
            "commercial_floor",
            "asosiy",
            "Bino joylashgan qavat",
            "select",
            facet=True,
            order=4,
            options=[
                ("basement", "Cokol (Yerto'la qavati)"),
                ("floor_1", "1-qavat"),
                ("floor_2", "2-qavat"),
                ("floor_3_plus", "3+ qavat"),
                ("whole_building", "Butun bino"),
            ],
        ),
        _field(
            "building_position_type",
            "asosiy",
            "Bino turi / Joylashuvi",
            "select",
            facet=True,
            order=5,
            options=[
                ("business_center", "Biznes markazida"),
                ("residential_ground_floor", "Turar joy binosining 1-qavatida"),
                ("standalone", "Alohida turgan bino"),
            ],
        ),
        _field(
            "condition",
            "asosiy",
            "Ta'mir holati",
            "select",
            facet=True,
            order=6,
            options=[
                ("euro_renovation", "Evrota'mir"),
                ("designer_project", "Mualliflik dizayni"),
                ("good", "O'rtacha"),
                ("shell_no_renovation", "Ta'mirsiz (Shell & Core / Korobka)"),
            ],
        ),
        _field(
            "sewage_water",
            "asosiy",
            "Kanalizatsiya va Suv",
            "select",
            facet=True,
            order=7,
            options=[("yes", "Bor"), ("no", "Yo'q")],
        ),
        _field(
            "power_capacity",
            "asosiy",
            "Elektr quvvati",
            "select",
            facet=True,
            order=8,
            options=[
                ("220v", "220V (Standart)"),
                ("380v", "380V (Sanoat/Yuqori quvvat)"),
            ],
        ),
        _field(
            "parking",
            "asosiy",
            "Avtoturargoh",
            "select",
            facet=True,
            order=9,
            options=[
                ("own", "Bor (Alohida/Shaxsiy)"),
                ("shared", "Bor (Umumiy)"),
                ("none", "Yo'q"),
            ],
        ),
        _field(
            "amenities",
            "asosiy",
            "Qulayliklar",
            "multiselect",
            facet=True,
            order=10,
            options=[
                ("air_conditioner", "Konditsioner"),
                ("security_camera", "Signalizatsiya/Kamera"),
                ("fiber_internet", "Internet (Optika)"),
                ("freight_elevator", "Yuk lifti"),
                ("separate_entrance", "Alohida kirish joyi"),
            ],
        ),
    ]


def _dacha_fields() -> list[dict[str, object]]:
    """Dala hovlilar (dacha / vacation-rental direction) -- 2026-08-23 split off from the shared
    residential form for the same two reasons as `_commercial_fields()` above (see that function's
    docstring): fields with no residential equivalent (guest capacity, pool/sauna type, tapchan,
    playground), and a genuinely different priority order for `district`-like/`price`-adjacent
    fields than Kotejlar/Hovlilar's already-confirmed one. `resort_area` is real Tashkent-region
    dacha destinations (Bo'stonliq's Chorvoq/Chimyon/Burchmulla/Hojikent are real places within
    it), not administrative tumanlar, so it doesn't reuse `_TASHKENT_REGION_DISTRICTS`."""
    return [
        _field(
            "resort_area",
            "asosiy",
            "Hudud / Yo'nalish",
            "select",
            facet=True,
            order=1,
            options=[
                ("bostonliq", "Bo'stonliq (Chorvoq/Chimyon/Burchmulla/Hojikent)"),
                ("qibray", "Qibray"),
                ("zangiota", "Zangiota"),
                ("parkent", "Parkent"),
                ("yangiobod", "Yangiobod"),
                ("other", "Boshqa hududlar"),
            ],
        ),
        _field(
            "guest_capacity",
            "asosiy",
            "Sig'im (Odam soni)",
            "select",
            facet=True,
            order=2,
            options=[
                ("up_to_4", "4 kishigacha"),
                ("up_to_6", "6 kishigacha"),
                ("up_to_10", "10 kishigacha"),
                ("15_plus", "15+ kishi"),
            ],
        ),
        _field(
            "rooms",
            "asosiy",
            "Xonalar soni",
            "select",
            facet=True,
            order=3,
            options=[
                ("1", "1 xonali"),
                ("2", "2 xonali"),
                ("3", "3 xonali"),
                ("4", "4 xonali"),
                ("5", "5 xonali"),
                ("6_plus", "6+ xonali"),
            ],
        ),
        _field(
            "lot_size_sotix",
            "asosiy",
            "Yer maydoni (sotix)",
            "number",
            facet=True,
            order=4,
        ),
        _field(
            "pool_type",
            "asosiy",
            "Basseyn turi",
            "select",
            facet=True,
            order=5,
            options=[
                ("outdoor", "Ochiq (Yozgi)"),
                ("indoor_heated", "Yopiq (Isitiladigan/Zimniy)"),
                ("both", "Ikkala tur ham bor"),
                ("none", "Yo'q"),
            ],
        ),
        _field(
            "sauna_type",
            "asosiy",
            "Sauna / Hammom",
            "select",
            facet=True,
            order=6,
            options=[
                ("finnish", "Fin saunasi"),
                ("turkish", "Turk hammomi"),
                ("steam", "Parovoy"),
                ("none", "Yo'q"),
            ],
        ),
        _field(
            "billiards_tennis_ps",
            "asosiy",
            "Bilyard / Tennis / PlayStation",
            "select",
            facet=True,
            order=7,
            options=[("yes", "Bor"), ("no", "Yo'q")],
        ),
        _field(
            "tapchan_summer_kitchen",
            "asosiy",
            "Tapchan va Yozgi oshxona",
            "select",
            facet=True,
            order=8,
            options=[("yes", "Bor (Ochoq/Mangal bilan)"), ("no", "Yo'q")],
        ),
        _field(
            "playground",
            "asosiy",
            "Bolalar maydonchasi",
            "select",
            facet=True,
            order=9,
            options=[("yes", "Bor"), ("no", "Yo'q")],
        ),
        _field(
            "amenities",
            "asosiy",
            "Qulayliklar",
            "multiselect",
            facet=True,
            order=10,
            options=[
                ("air_conditioner", "Konditsioner"),
                ("karaoke_sound_system", "Karaoke / Sanoat kalonkasi"),
                ("wifi", "Wi-Fi / Internet"),
                ("winter_heating", "Qishki isitish tizimi (Otopleniye)"),
                ("parking", "Avtoturargoh"),
            ],
        ),
    ]


def _land_fields() -> list[dict[str, object]]:
    """Bo'sh yerlar (yer uchastkalari) -- always its own `FormDefinition` ("bosh-yer-form"),
    never shared with `_property_fields()`. `order` (2026-08-23 UX rewrite) follows the requested
    row-by-row sequence: `district`/`deal_type` land right before/after the (virtual-order) price
    control, matching the "Kichik kategoriya / Tuman / Narx / Bitim turi" row exactly. `land_
    purpose` and `has_documents` are now superseded by the 5 new subcategories (Uy qurish/Tijorat/
    Qishloq xo'jaligi/Sanoat/Dacha) and the richer `ownership_type` field respectively -- kept
    (additive-only: never remove an already-published field) but deprioritized to the end rather
    than deleted."""
    return [
        _field(
            "district",
            "asosiy",
            "Tuman",
            "select",
            facet=True,
            order=1,
            options=_TASHKENT_DISTRICTS + _TASHKENT_REGION_DISTRICTS,
        ),
        _field(
            "deal_type",
            "asosiy",
            "Bitim turi",
            "select",
            required=True,
            facet=True,
            order=2,
            options=[
                ("sale", "Sotiladi"),
                ("rent", "Uzoq muddatli ijaraga beriladi / Arenda"),
            ],
        ),
        _field(
            "area_sotix",
            "asosiy",
            "Yer maydoni (sotix/gektar)",
            "number",
            required=True,
            facet=True,
            order=3,
        ),
        _field(
            "ownership_type",
            "asosiy",
            "Mulkchilik / Hujjat turi",
            "select",
            facet=True,
            order=4,
            options=[
                ("private_property", "Xususiylashtirilgan (Chastnaya sobstvennost)"),
                ("cadastre", "Egalik huquqi (Kadastr)"),
                ("lease_49y", "Ijara huquqi (49 yil)"),
                ("farmer_land", "Dehqon xo'jaligi"),
            ],
        ),
        _field(
            "location_condition",
            "asosiy",
            "Yer joylashuvi / Sharoiti",
            "select",
            facet=True,
            order=5,
            options=[
                ("roadside", "Yo'l bo'yida (1-liniya)"),
                ("settlement", "Aholi yashash punktida"),
                ("outskirts", "Shahar tashqarisida"),
                ("industrial_zone", "Sanoat zonasida"),
            ],
        ),
        _field(
            "terrain_shape",
            "asosiy",
            "Yer shakli / Relyefi",
            "select",
            facet=True,
            order=6,
            options=[
                ("flat", "Tekis yer"),
                ("hilly", "Tepalik / Adir"),
                ("corner_lot", "Chekka (Ugolovoy) uchastka"),
            ],
        ),
        _field(
            "gas_supply",
            "asosiy",
            "Gaz ta'minoti",
            "select",
            facet=True,
            order=7,
            options=[
                ("connected", "Bor (Ulangan)"),
                ("nearby", "Yonidan o'tgan"),
                ("none", "Yo'q"),
            ],
        ),
        _field(
            "electricity_supply",
            "asosiy",
            "Elektr energiyasi",
            "select",
            facet=True,
            order=8,
            options=[
                ("connected", "Bor (220V/380V)"),
                ("nearby", "Yonida bor"),
                ("none", "Yo'q"),
            ],
        ),
        _field(
            "water_supply",
            "asosiy",
            "Suv ta'minoti",
            "select",
            facet=True,
            order=9,
            options=[
                ("drinking_network", "Ichimlik suvi (Ichki tarmoq)"),
                ("irrigation", "Sug'orish suvi (Arik/Kanal)"),
                ("artesian_well", "Artezian quduq"),
                ("none", "Yo'q"),
            ],
        ),
        _field(
            "amenities",
            "asosiy",
            "Qulayliklar",
            "multiselect",
            facet=True,
            order=10,
            options=[
                ("sewage", "Kanalizatsiya"),
                ("asphalt_road", "Asfalt yo'l kirgan"),
                ("fenced", "O'ralgan (Zabor/Devor bor)"),
                ("foundation", "Poydevor (Fundament) quyilgan"),
            ],
        ),
        _field(
            "land_purpose",
            "asosiy",
            "Yer maqsadi",
            "select",
            facet=True,
            order=90,
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
            order=91,
            default=False,
        ),
    ]


def _goods_fields() -> list[dict[str, object]]:
    """Maishiy texnikalar / uy bezaklari / uniforma -- anything sold as a physical unit, same
    shape as the furniture ("Mebel materiallari") form seeded above. Qurilish materiallari used to
    share this too, but was split off (2026-08-23) into its own `_building_materials_fields()` --
    see that function's docstring."""
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


def _building_materials_fields() -> list[dict[str, object]]:
    """Qurilish materiallari -- 2026-08-23 split off from `_goods_fields()` into its own
    "building-materials-form", same reason as `_commercial_fields()`/`_dacha_fields()` above: a
    genuinely different, more detailed field set (seller type, sale unit, delivery, payment
    method) and a different priority order for `district`/`condition` than what's shared elsewhere.
    `district` reuses the same real Tashkent city+region option lists as the real-estate forms."""
    return [
        _field(
            "district",
            "asosiy",
            "Tuman",
            "select",
            facet=True,
            order=1,
            options=_TASHKENT_DISTRICTS + _TASHKENT_REGION_DISTRICTS,
        ),
        _field(
            "condition",
            "asosiy",
            "Mahsulot holati",
            "select",
            required=True,
            facet=True,
            order=2,
            options=[
                ("new_factory", "Yangi (Zavoddan)"),
                ("new_warehouse", "Yangi (Ombordan)"),
                ("leftover", "Qolgan/Ortgan materiallar"),
                ("used", "Ishlatilgan (B/U)"),
            ],
        ),
        _field(
            "seller_type",
            "asosiy",
            "Sotuvchi turi",
            "select",
            facet=True,
            order=3,
            options=[
                ("manufacturer", "Ishlab chiqaruvchi (Zavod)"),
                ("dealer_store", "Rasmiy diler / Do'kon"),
                ("individual", "Jismoniy shaxs (Shaxsiy)"),
            ],
        ),
        _field(
            "sale_unit",
            "asosiy",
            "Sotish hajmi / Birlik",
            "select",
            facet=True,
            order=4,
            options=[
                ("wholesale", "Ulgurji (Optom)"),
                ("retail", "Dona / Chakana (Roznitsa)"),
                ("sqm", "Kvadrat metr (m2)"),
                ("cbm", "Kub metr (m3)"),
                ("ton_sack", "Tonna / Qop"),
            ],
        ),
        _field(
            "delivery",
            "asosiy",
            "Yetkazib berish (Dostavka)",
            "select",
            facet=True,
            order=5,
            options=[
                ("free", "Bor (Bepul)"),
                ("paid", "Bor (Alohida to'lovli)"),
                ("pickup", "Olib ketish (Samovivoz)"),
            ],
        ),
        _field(
            "payment_method",
            "asosiy",
            "To'lov shakli",
            "select",
            facet=True,
            order=6,
            options=[
                ("cash", "Naqd pul"),
                ("bank_transfer", "Pul o'tkazish (Perechisleniye/NDS)"),
                ("app_payment", "Ilova orqali (Click/Payme)"),
            ],
        ),
    ]


def _home_appliances_fields() -> list[dict[str, object]]:
    """Maishiy texnikalar -- 2026-08-23 split off from `_goods_fields()` into its own
    "home-appliances-form", same reason as `_building_materials_fields()` above. `brand` here is
    a closed `select` (real brands sold in this market), not the generic goods form's free-text
    `brand` field -- a genuinely different field, not a reuse."""
    return [
        _field(
            "district",
            "asosiy",
            "Tuman",
            "select",
            facet=True,
            order=1,
            options=_TASHKENT_DISTRICTS + _TASHKENT_REGION_DISTRICTS,
        ),
        _field(
            "condition",
            "asosiy",
            "Mahsulot holati",
            "select",
            required=True,
            facet=True,
            order=2,
            options=[
                ("new", "Yangi (Qadoqda/Yupka)"),
                ("ideal", "Ideal (Kam ishlatilgan)"),
                ("average", "O'rtacha (Ishlatilgan B/U)"),
                ("for_parts", "Zapchastga / Ta'mirtalab"),
            ],
        ),
        _field(
            "appliance_brand",
            "asosiy",
            "Brend / Markasi",
            "select",
            facet=True,
            order=3,
            options=[
                ("samsung", "Samsung"),
                ("lg", "LG"),
                ("artel", "Artel"),
                ("bosch", "Bosch"),
                ("whirlpool", "Whirlpool"),
                ("midea", "Midea"),
                ("hofmann", "Hofmann"),
                ("other", "Boshqa brendlar"),
            ],
        ),
        _field(
            "warranty",
            "asosiy",
            "Kafolat (Garantiya)",
            "select",
            facet=True,
            order=4,
            options=[
                ("official", "Rasmiy kafolat bor (Zavod/Do'kon)"),
                ("seller_1_3_months", "Sotuvchidan kafolat (1-3 oy)"),
                ("none_expired", "Kafolat muddati tugagan / Yo'q"),
            ],
        ),
        _field(
            "seller_type",
            "asosiy",
            "Sotuvchi turi",
            "select",
            facet=True,
            order=5,
            options=[
                ("store_salon", "Do'kon / Maishiy texnika saloni"),
                ("individual", "Jismoniy shaxs (Shaxsiy buyum)"),
            ],
        ),
        _field(
            "delivery_install",
            "asosiy",
            "Yetkazib berish va O'rnatish",
            "select",
            facet=True,
            order=6,
            options=[
                ("free_delivery_install", "Yetkazib berish va o'rnatish bepul"),
                ("delivery_only", "Faqat yetkazib berish bor"),
                ("pickup", "Olib ketish (Samovivoz)"),
            ],
        ),
    ]


def _home_decor_fields() -> list[dict[str, object]]:
    """Uy bezaklari -- 2026-08-23 split off from `_goods_fields()` into its own "home-decor-form",
    same reason as `_building_materials_fields()`/`_home_appliances_fields()` above."""
    return [
        _field(
            "district",
            "asosiy",
            "Tuman",
            "select",
            facet=True,
            order=1,
            options=_TASHKENT_DISTRICTS + _TASHKENT_REGION_DISTRICTS,
        ),
        _field(
            "condition",
            "asosiy",
            "Mahsulot holati",
            "select",
            required=True,
            facet=True,
            order=2,
            options=[
                ("new", "Yangi (Qadoqda)"),
                ("ideal", "Ideal holatda"),
                ("average", "O'rtacha (B/U)"),
                ("antique_showroom", "Antikvariat / Do'kon ekspozitsiyasi"),
            ],
        ),
        _field(
            "style",
            "asosiy",
            "Dizayn uslubi (Stil)",
            "select",
            facet=True,
            order=3,
            options=[
                ("modern_hitech", "Zamonaviy (Modern/Hi-Tech)"),
                ("classic", "Klassik"),
                ("neoclassic", "Neoklassika"),
                ("loft_minimalism", "Loft / Minimalizm"),
                ("national_oriental", "Milliy / Sharqona uslub"),
            ],
        ),
        _field(
            "seller_type",
            "asosiy",
            "Sotuvchi turi",
            "select",
            facet=True,
            order=4,
            options=[
                ("official_store_showroom", "Rasmiy do'kon / Shou-rum"),
                ("handmade_master", "Qo'l mehnati ustasi (Handmade)"),
                ("individual", "Jismoniy shaxs"),
            ],
        ),
        _field(
            "delivery",
            "asosiy",
            "Yetkazib berish (Dostavka)",
            "select",
            facet=True,
            order=5,
            options=[
                ("free", "Bor (Bepul)"),
                ("paid", "Bor (Alohida to'lovli)"),
                ("pickup", "Olib ketish (Samovivoz)"),
            ],
        ),
        _field(
            "payment_method",
            "asosiy",
            "To'lov shakli",
            "select",
            facet=True,
            order=6,
            options=[
                ("cash", "Naqd pul"),
                ("bank_transfer", "Pul o'tkazish (Perechisleniye)"),
                ("app_payment", "Ilova orqali (Click/Payme)"),
            ],
        ),
    ]


def _uniform_fields() -> list[dict[str, object]]:
    """Uniforma va maxsus kiyimlar -- 2026-08-23 split off from `_goods_fields()` into its own
    "uniform-form", same reason as `_building_materials_fields()`/`_home_appliances_fields()`
    above."""
    return [
        _field(
            "district",
            "asosiy",
            "Tuman",
            "select",
            facet=True,
            order=1,
            options=_TASHKENT_DISTRICTS + _TASHKENT_REGION_DISTRICTS,
        ),
        _field(
            "condition",
            "asosiy",
            "Mahsulot holati",
            "select",
            required=True,
            facet=True,
            order=2,
            options=[
                ("new_packaged", "Yangi (Qadoqda)"),
                ("new_tailored", "Yangi (Tiktirib beriladi)"),
                ("lightly_used", "Kam ishlatilgan (B/U)"),
            ],
        ),
        _field(
            "size",
            "asosiy",
            "O'lcham (Size)",
            "select",
            required=True,
            facet=True,
            order=3,
            options=[
                ("s", "S"),
                ("m", "M"),
                ("l", "L"),
                ("xl", "XL"),
                ("2xl", "2XL"),
                ("3xl", "3XL"),
                ("4xl_plus", "4XL+"),
                ("universal", "Standart (Univeral)"),
            ],
        ),
        _field(
            "season",
            "asosiy",
            "Mavsumiylik (Mavsum)",
            "select",
            facet=True,
            order=4,
            options=[
                ("summer", "Yozgi"),
                ("winter_insulated", "Qishki (Isitilgan/Uteplyonniy)"),
                ("demi_season", "Demisezon (Bahor/Kuz)"),
                ("all_season", "Barcha mavsumlar uchun"),
            ],
        ),
        _field(
            "gender",
            "asosiy",
            "Jins (Kim uchun)",
            "select",
            facet=True,
            order=5,
            options=[
                ("men", "Erkaklar uchun"),
                ("women", "Ayollar uchun"),
                ("unisex", "Uniseks (Barchaga)"),
            ],
        ),
        _field(
            "seller_type",
            "asosiy",
            "Sotuvchi turi / Xizmat",
            "select",
            facet=True,
            order=6,
            options=[
                ("ready_made_store", "Tayyor mahsulot (Do'kon)"),
                ("custom_tailoring", "Buyurtmaga tikib berish (Atele/Fabrika)"),
                ("individual", "Jismoniy shaxs"),
            ],
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


def _service_cv_fields(
    *, extra: list[dict[str, object]] | None = None
) -> list[dict[str, object]]:
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
        _field(
            "specialization", "asosiy", "Mutaxassislik", "text", facet=True, order=2
        ),
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
        "sections": [
            {"code": section_code, "label": {"uz_latn": section_name}, "order": 1}
        ],
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
            raise RuntimeError(
                f"seed marker {code!r} vanished between check and lookup"
            ) from None
        return existing.id

    manage_key = _registry.manage_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    approve_key = _registry.approve_permission_key(
        ConfigEntityType.FORM_DEFINITION.value
    )
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


async def _backfill_form_definition_fields(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    fields: list[dict[str, object]],
    force_facet_eligible: frozenset[str] = frozenset(),
    force_order: dict[str, int] | None = None,
    now: datetime,
) -> None:
    """Adds any field from `fields` missing (by `code`) from the published `FormDefinition` head
    looked up by `code`. Additive-only, same convention as `_backfill_platform_settings_defaults`/
    `_backfill_search_configuration_facets` above -- an already-published field is left exactly as
    published (its options, required-ness, etc. untouched) even if this function's own `fields`
    table now describes it differently, so a future owner-admin panel edit is never silently
    reverted by a later deploy re-running this seed. `_seed_form`'s own `DuplicateCodeError`
    early-return means it never touches an already-existing head again -- this is the only thing
    that actually pushes new fields onto one that's already live in production.

    `force_facet_eligible` and `force_order` are the two deliberate exceptions to "additive-only":
    named, narrow sets of ALREADY-published field codes whose `facet_eligible` flag (one direction
    only, never back to `False`) or `order` value gets overridden even though the field itself
    isn't new. Everything else about a forced field (options, label, required-ness) stays exactly
    as published. `force_facet_eligible` exists because `_property_fields()`'s own `floor`/
    `total_floors` genuinely needed that correction (2026-08-22); `force_order` because
    `CategoryFilterPanel.tsx` never sorted `fields` by `order` (a real bug -- `DynamicCategoryForm.
    tsx` did, which is why the listing-creation form was always right and only the filter grid
    read "jumbled" -- fixed alongside this), so every already-published field on this form needed
    its `order` reassigned to the row-by-row sequence a 2026-08-23 UX ask specified, not just the
    newly-added ones. Neither is meant as a general update mechanism."""
    head = await repo.get_head_by_code(ConfigEntityType.FORM_DEFINITION, code)
    if head is None or head.current_version_id is None:
        return
    current = await repo.get_version(
        ConfigEntityType.FORM_DEFINITION, head.id, head.current_version_id
    )
    if current is None:
        return
    current_fields: list[dict[str, object]] = list(
        current.definition_document.get("fields") or []
    )
    existing_codes = {f.get("code") for f in current_fields}
    missing = [f for f in fields if f.get("code") not in existing_codes]
    order_overrides = force_order or {}

    def _apply_force(f: dict[str, object]) -> dict[str, object]:
        code_ = f.get("code")
        result = f
        if code_ in force_facet_eligible and result.get("facet_eligible") is not True:
            result = {**result, "facet_eligible": True}
        if code_ in order_overrides and result.get("order") != order_overrides[code_]:
            result = {**result, "order": order_overrides[code_]}
        return result

    forced = [_apply_force(f) for f in current_fields]
    if not missing and forced == current_fields:
        return

    new_document = {**current.definition_document, "fields": forced + missing}
    new_version = await use_cases.create_version_draft(
        ConfigEntityType.FORM_DEFINITION,
        head.id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    approve_key = _registry.approve_permission_key(
        ConfigEntityType.FORM_DEFINITION.value
    )
    step1 = await use_cases.publish(
        ConfigEntityType.FORM_DEFINITION,
        head.id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note=f"seed: backfill missing fields for {code}",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.FORM_DEFINITION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note=f"seed: backfill missing fields for {code} approval",
            now=now,
        )


async def _backfill_form_definition_field_options(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    field_options: dict[str, list[tuple[str, str]]],
    now: datetime,
) -> None:
    """Appends new option VALUES onto already-published fields' `options` lists, matched by field
    `code`. Additive-only in the same one-directional sense as `_backfill_form_definition_fields`
    above: an option value already present (matched by its `value`, not its label) is left
    untouched, existing options are never reordered or removed, and a field whose `code` isn't a
    key in `field_options` isn't touched at all. Exists for the narrow, real case (2026-08-23,
    "Kotejlar" TZ) of an already-published SHARED field (`deal_type`/`condition`/`district` on
    `_property_fields()`) needing new enum values that a *different* category cares about than the
    one the field was first written for -- adding a whole new field code would be wrong (it's
    still fundamentally "Bitim turi"/"Holati"/"Tuman"), and `_backfill_form_definition_fields`
    can't reach it since the field's `code` already exists on the published head."""
    head = await repo.get_head_by_code(ConfigEntityType.FORM_DEFINITION, code)
    if head is None or head.current_version_id is None:
        return
    current = await repo.get_version(
        ConfigEntityType.FORM_DEFINITION, head.id, head.current_version_id
    )
    if current is None:
        return
    current_fields: list[dict[str, object]] = list(
        current.definition_document.get("fields") or []
    )
    changed = False
    new_fields: list[dict[str, object]] = []
    for f in current_fields:
        additions = field_options.get(str(f.get("code")))
        if not additions:
            new_fields.append(f)
            continue
        raw_options = f.get("options")
        existing_options: list[dict[str, object]] = (
            list(raw_options) if isinstance(raw_options, list) else []
        )
        existing_values = {o.get("value") for o in existing_options}
        to_add = [
            {"value": v, "label": {"uz_latn": lbl}}
            for v, lbl in additions
            if v not in existing_values
        ]
        if not to_add:
            new_fields.append(f)
            continue
        changed = True
        new_fields.append({**f, "options": existing_options + to_add})
    if not changed:
        return

    new_document = {**current.definition_document, "fields": new_fields}
    new_version = await use_cases.create_version_draft(
        ConfigEntityType.FORM_DEFINITION,
        head.id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = _registry.manage_permission_key(ConfigEntityType.FORM_DEFINITION.value)
    approve_key = _registry.approve_permission_key(
        ConfigEntityType.FORM_DEFINITION.value
    )
    step1 = await use_cases.publish(
        ConfigEntityType.FORM_DEFINITION,
        head.id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note=f"seed: backfill new option values for {code}",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.FORM_DEFINITION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note=f"seed: backfill new option values for {code} approval",
            now=now,
        )


async def _backfill_category_form_definition(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    *,
    code: str,
    form_definition_id: UUID,
    now: datetime,
) -> None:
    """Repoints an already-published `Category` head's `form_definition_id` to a different
    `FormDefinition` -- the one-off counterpart to `_seed_category`'s own creation-time binding,
    needed when a category's field shape has outgrown its original shared form (2026-08-23,
    "Noturar binolar" split off `_property_fields()`/"ko-chmas-mulk-form" into its own
    `_commercial_fields()`/"tijorat-mulk-form" -- see that function's docstring for why).
    Idempotent: a no-op once the category already points at the given form."""
    head = await repo.get_head_by_code(ConfigEntityType.CATEGORY, code)
    if head is None or head.current_version_id is None:
        return
    current = await repo.get_version(
        ConfigEntityType.CATEGORY, head.id, head.current_version_id
    )
    if current is None:
        return
    definition = dict(current.definition_document)
    if definition.get("form_definition_id") == str(form_definition_id):
        return

    definition["form_definition_id"] = str(form_definition_id)
    new_version = await use_cases.create_version_draft(
        ConfigEntityType.CATEGORY,
        head.id,
        definition=definition,
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
        approval_note=f"seed: repoint {code} to new form_definition_id",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note=f"seed: repoint {code} to new form_definition_id approval",
            now=now,
        )


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
    descriptor: dict[str, object] = {
        "name": {"uz_latn": name},
        "display_order": display_order,
    }
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
            raise RuntimeError(
                f"seed marker {code!r} vanished between check and lookup"
            ) from None
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
    current = await repo.get_version(
        ConfigEntityType.CATEGORY, head_id, current_version_id
    )
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
    current = await repo.get_version(
        ConfigEntityType.CATEGORY, head_id, current_version_id
    )
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
    current = await repo.get_version(
        ConfigEntityType.CATEGORY, head.id, head.current_version_id
    )
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
    """Flat, real-market-aligned list (2026-08-23 rewrite) -- replaces a deep, artificial
    daraxt (Oilaviy/Premium/Tog' kotejlari branches with invented leaves like "Ekstremal turizm
    uchun") that didn't map to how O'zbekiston cottage listings/OLX are actually browsed. Kept
    flat (no grandchildren) on purpose: `CategoryPicker` (`routes/list/index.tsx`) and
    `CategoryFilterPanel`'s `subcategory` select (both already fully generic over whatever the
    category tree contains, zero frontend change needed) read best as one flat choice, not another
    drill-down level."""
    return [
        "Sotuvdagi kotejlar",
        "Sutkalik ijaraga beriladigan kotejlar",
        "Uzoq muddatli ijaraga beriladigan kotejlar",
        "Tog' va tabiat bag'ridagi kotejlar",
        "Townhouse va Buxobloklar",
        "Villalar va Luxe kotejlar",
    ]


def _hovlilar_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Premium/Hovuzli/Smart Home hovlilar branches) that didn't map
    to how hovli listings are actually browsed. List order IS the site's real `display_order`
    (`_seed_subtree` numbers siblings by `enumerate`, not alphabetically), matching the exact
    sequence asked for."""
    return [
        "Sotuvdagi hovlilar / Uchastkalar",
        "Uzoq muddatli ijaraga beriladigan hovlilar",
        "Sutkalik ijaraga beriladigan hovlilar",
        "Buzib tashlanadigan / Yer o'rnida sotiladigan hovlilar",
        "Hovli qismi (Eski shahar / Obshiy dvor)",
    ]


def _noturar_binolar_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Ofis binolari/Savdo markazlari/Omborxonalar branches, plus
    leaves like "Zavod va fabrikalar"/"Ko'ngilochar markazlar" not really distinct commercial-
    listing categories) with 7 real ones covering how tijorat ko'chmas mulk is actually browsed."""
    return [
        "Ofis va Biznes markazlar",
        "Do'kon, Shop-room va Savdo maydonlari",
        "Omborxona va Ishlab chiqarish joylari (Baza/Sklad)",
        "Restoran, Kafe va Umumiy ovqatlanish joylari",
        "Avtoservis, Moyka va Garaj majmualari",
        "Alohida turgan tijorat binosi / Bino qismi",
        "Boshqa tijorat ob'ektlari",
    ]


def _dala_hovlilar_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Kunlik ijara/Premium villalar/Hovuzli dala hovlilar branches)
    with 5 real ones covering how dacha listings are actually browsed."""
    return [
        "Sutkalik ijaraga beriladigan dachalar (Oila va Dam olish uchun)",
        "Sutkalik ijaraga beriladigan dachalar (Ulfatlar / Tadbirlar uchun)",
        "Sotuvdagi dacha va dala hovlilar",
        "Uzoq muddatli (Mavsumiy) ijaraga beriladigan dachalar",
        "Azo / Klub tipidagi dacha majmualari",
    ]


def _bosh_yerlar_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Turar joy/Tijorat/Qishloq xo'jaligi branches with invented
    leaves like "Auksion orqali sotilayotgan yerlar") with 5 real ones matching what `land_
    purpose` used to distinguish as a FIELD -- the subcategory now covers that distinction."""
    return [
        "Uy va hovli qurish uchun yerlar (IJB / ЖСЗ)",
        "Tijorat va biznes uchun yerlar (Tadbirkorlik)",
        "Qishloq xo'jaligi va dehqonchilik yerlari",
        "Sanoat va omborxona qurish uchun yerlar",
        "Dacha va dam olish zonasi uchun yerlar",
    ]


def _qurilish_materiallari_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Elektr mahsulotlari/Bo'yoqlar/Mahkamlash mahsulotlari
    branches) with 8 real ones grouped by material category rather than by product type."""
    return [
        "Poydevor va g'isht mahsulotlari (G'isht, Blok, Sement, Qum)",
        "Tom va yopqich materiallari (Profnastil, Cherepitsa, Slate)",
        "Pardozlash va ta'mir materiallari (Gipsokarton, Bo'yoq, Suvok, Plitka)",
        "Yog'och va yog'och mahsulotlari (Balkalar, Doska, Fanera)",
        "Santexnika, Quvurlar va Isitish tizimlari",
        "Elektrik va yoritish mahsulotlari (Kabel, Avtomat, Rozetka)",
        "Izolyatsiya va izolyatsiya materiallari (Penoplast, Minvata)",
        "Boshqa qurilish mahsulotlari",
    ]


def _maishiy_texnikalar_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Muzlatgichlar/Kir yuvish mashinalari/Oshxona texnikalari
    branches) with 7 real ones grouped by appliance category."""
    return [
        "Oshxona texnikalari (Muzlatgich, Plita, Mikrotolqinli pech, Idish yuvish mashinasi)",
        "Kirim va yuvish texnikasi (Kir yuvish mashinasi, Dazmol, Quritgich)",
        "Iqlim texnikasi (Konditsioner, Isitgich, Ventilyator, Suv isitgich/Kotel)",
        "Uy tozalash texnikasi (Changyutgich, Paroochistitel)",
        "Audio va Video texnika (Televizor, Akustika, Tyuner)",
        "Kichik va shaxsiy parvarish texnikalari (Fen, Britva, Vesy)",
        "Boshqa maishiy texnikalar",
    ]


def _uy_bezaklari_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Devor bezaklari/Pardalar va jalyuzilar/Dekorativ yoritish
    branches) with 7 real ones grouped by decor category."""
    return [
        "Gilamlar va poyandozlar (Gilam, Kovrolin, Dorojka)",
        "Pardalar, jaluzi va tyullar",
        "Uy tekstili (O'rin-ko'rpa to'plamlari, Yastik, Plad, Dasturxon)",
        "Yoritish vositalari (Lyustra, Svetilnik, Torsher, LED)",
        "Devor bezaklari (Soat, Kartina, Panno, Ko'zgular/Zerkalo)",
        "Vazalar, haykalchalar va suvenir dekorlar",
        "Boshqa uy bezaklari",
    ]


def _uniforma_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Qurilish kiyimlari/Ish poyabzallari/Himoya vositalari
    branches) with 7 real ones grouped by profession/use case."""
    return [
        "Qurilish va sanoat ishchi kiyimlari (Spetsovka, Kombinezon)",
        "Tibbiyot xodimlari kiyimlari (Xalat, Kostyum)",
        "Oshpaz va xizmat ko'rsatish sohasi uniformasi (Povar, Ofitsiant)",
        "Harbiylashtirilgan va qo'riqlash kiyimlari (Oxrana, Kamuflyaj)",
        "Maktab va korporativ kiyimlar (Forma, Jilet, Galstuk)",
        "Maxsus poyabzallar (Spetsobuv, Bersi, Rezinoviy botinki)",
        "Boshqa maxsus kiyimlar va aksessuarlar",
    ]


def _mebel_materiallari_tree() -> list[Node]:
    """Flat, real-market-aligned list (2026-08-23 rewrite, same rationale as `_kotejlar_tree()`
    above) -- replaces a deep tree (Yog'och materiallari/Mebel furnituralari/Mato va charm
    qoplamalar branches) with 7 real ones grouped by material category."""
    return [
        "Yog'och va yog'och-plitka materiallari (Laminat, MDF, DVP, DSP, Fanera)",
        "Mebel furnituralari va mexanizmlari (Petli, Napravlyayushchiye, Zamoklar)",
        "Mebel fasadlari va profillari (Aluminiy, MDF fasadlar, Kromka)",
        "Matalo va shpon mahsulotlari (Mebel matolari, Teri, Porolon)",
        "Mebel aksessuarlari va ruchkalari",
        "Mebel yelim va kimyoviy vositalari (Yelim, Lak, Kraska)",
        "Boshqa mebel ehtiyot qismlari",
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
    await _backfill_form_definition_fields(
        use_cases,
        repo,
        code="ko-chmas-mulk-form",
        fields=_property_fields(),
        force_facet_eligible=frozenset({"floor", "total_floors"}),
        force_order={
            "district": 1,
            "rooms": 2,
            "lot_size_sotix": 3,
            "area_sqm": 4,
            "total_floors": 5,
            "condition": 6,
            "basement_type": 7,
            "has_attic": 8,
            "balcony": 9,
            "amenities": 10,
            "floor": 90,
            "building_type": 91,
            "has_basement": 92,
            "deal_type": 93,
        },
        now=now,
    )
    await _backfill_form_definition_field_options(
        use_cases,
        repo,
        code="ko-chmas-mulk-form",
        field_options={
            "deal_type": [("daily_rent", "Sutkalik ijara (Dam olish uchun)")],
            "condition": [
                ("euro_renovation", "Evrota'mir"),
                ("designer_project", "Mualliflik loyihasi"),
                ("shell_no_renovation", "Ta'mirsiz (Korobka)"),
                ("old_worn", "Eskirgan"),
            ],
            "district": _TASHKENT_REGION_DISTRICTS,
            "amenities": [("furnished", "Mebelli")],
        },
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

    # -- Commercial real estate (own form, split off `re_form_id` 2026-08-23 -- see
    # `_commercial_fields()`'s docstring for why).
    commercial_form_id = await _seed_form(
        use_cases,
        repo,
        code="tijorat-mulk-form",
        name="Tijorat ko'chmas mulki",
        fields=_commercial_fields(),
        now=now,
    )
    await _backfill_category_form_definition(
        use_cases,
        repo,
        code="noturar-binolar",
        form_definition_id=commercial_form_id,
        now=now,
    )
    noturar_binolar_head_id = await _seed_category(
        use_cases,
        repo,
        code="noturar-binolar",
        name="Noturar binolar",
        path="/noturar-binolar",
        parent_category_id=None,
        form_definition_id=commercial_form_id,
        now=now,
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _noturar_binolar_tree(),
        parent_id=noturar_binolar_head_id,
        parent_path="/noturar-binolar",
        form_definition_id=commercial_form_id,
        now=now,
    )

    # -- Dala hovlilar / dachas (own form, split off `re_form_id` 2026-08-23 -- see
    # `_dacha_fields()`'s docstring for why).
    dacha_form_id = await _seed_form(
        use_cases,
        repo,
        code="dacha-form",
        name="Dala hovlilar",
        fields=_dacha_fields(),
        now=now,
    )
    await _backfill_category_form_definition(
        use_cases,
        repo,
        code="dala-hovlilar",
        form_definition_id=dacha_form_id,
        now=now,
    )
    dala_hovlilar_head_id = await _seed_category(
        use_cases,
        repo,
        code="dala-hovlilar",
        name="Dala hovlilar",
        path="/dala-hovlilar",
        parent_category_id=None,
        form_definition_id=dacha_form_id,
        now=now,
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _dala_hovlilar_tree(),
        parent_id=dala_hovlilar_head_id,
        parent_path="/dala-hovlilar",
        form_definition_id=dacha_form_id,
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
    await _backfill_form_definition_fields(
        use_cases,
        repo,
        code="bosh-yer-form",
        fields=_land_fields(),
        force_order={
            "area_sotix": 3,
            "land_purpose": 90,
            "has_documents": 91,
        },
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

    # -- Qurilish materiallari (own form, split off "mahsulot-form" 2026-08-23 -- see
    # `_building_materials_fields()`'s docstring for why).
    building_materials_form_id = await _seed_form(
        use_cases,
        repo,
        code="building-materials-form",
        name="Qurilish materiallari",
        fields=_building_materials_fields(),
        now=now,
    )
    await _backfill_category_form_definition(
        use_cases,
        repo,
        code="qurilish-materiallari",
        form_definition_id=building_materials_form_id,
        now=now,
    )
    qurilish_materiallari_head_id = await _seed_category(
        use_cases,
        repo,
        code="qurilish-materiallari",
        name="Qurilish materiallari",
        path="/qurilish-materiallari",
        parent_category_id=None,
        form_definition_id=building_materials_form_id,
        now=now,
        listing_kind="GOODS",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _qurilish_materiallari_tree(),
        parent_id=qurilish_materiallari_head_id,
        parent_path="/qurilish-materiallari",
        form_definition_id=building_materials_form_id,
        now=now,
        listing_kind="GOODS",
    )

    # -- Maishiy texnikalar (own form, split off "mahsulot-form" 2026-08-23 -- see
    # `_home_appliances_fields()`'s docstring for why).
    home_appliances_form_id = await _seed_form(
        use_cases,
        repo,
        code="home-appliances-form",
        name="Maishiy texnikalar",
        fields=_home_appliances_fields(),
        now=now,
    )
    await _backfill_category_form_definition(
        use_cases,
        repo,
        code="maishiy-texnikalar",
        form_definition_id=home_appliances_form_id,
        now=now,
    )
    maishiy_texnikalar_head_id = await _seed_category(
        use_cases,
        repo,
        code="maishiy-texnikalar",
        name="Maishiy texnikalar",
        path="/maishiy-texnikalar",
        parent_category_id=None,
        form_definition_id=home_appliances_form_id,
        now=now,
        listing_kind="GOODS",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _maishiy_texnikalar_tree(),
        parent_id=maishiy_texnikalar_head_id,
        parent_path="/maishiy-texnikalar",
        form_definition_id=home_appliances_form_id,
        now=now,
        listing_kind="GOODS",
    )

    # -- Uy bezaklari (own form, split off "mahsulot-form" 2026-08-23 -- see
    # `_home_decor_fields()`'s docstring for why).
    home_decor_form_id = await _seed_form(
        use_cases,
        repo,
        code="home-decor-form",
        name="Uy bezaklari",
        fields=_home_decor_fields(),
        now=now,
    )
    await _backfill_category_form_definition(
        use_cases,
        repo,
        code="uy-bezaklari",
        form_definition_id=home_decor_form_id,
        now=now,
    )
    uy_bezaklari_head_id = await _seed_category(
        use_cases,
        repo,
        code="uy-bezaklari",
        name="Uy bezaklari",
        path="/uy-bezaklari",
        parent_category_id=None,
        form_definition_id=home_decor_form_id,
        now=now,
        listing_kind="GOODS",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _uy_bezaklari_tree(),
        parent_id=uy_bezaklari_head_id,
        parent_path="/uy-bezaklari",
        form_definition_id=home_decor_form_id,
        now=now,
        listing_kind="GOODS",
    )

    # -- Uniforma va maxsus kiyimlar (own form, split off "mahsulot-form" 2026-08-23 -- see
    # `_uniform_fields()`'s docstring for why). This was the last category still on the shared
    # goods form -- `_goods_fields()`/"mahsulot-form" is no longer referenced by anything, kept
    # only because it's already published (harmless orphan, per the additive-only convention).
    uniform_form_id = await _seed_form(
        use_cases,
        repo,
        code="uniform-form",
        name="Uniforma va maxsus kiyimlar",
        fields=_uniform_fields(),
        now=now,
    )
    await _backfill_category_form_definition(
        use_cases,
        repo,
        code="uniforma-va-maxsus-kiyimlar",
        form_definition_id=uniform_form_id,
        now=now,
    )
    uniforma_head_id = await _seed_category(
        use_cases,
        repo,
        code="uniforma-va-maxsus-kiyimlar",
        name="Uniforma va maxsus kiyimlar",
        path="/uniforma-va-maxsus-kiyimlar",
        parent_category_id=None,
        form_definition_id=uniform_form_id,
        now=now,
        listing_kind="GOODS",
        display_order=next(top_level_order),
    )
    await _seed_subtree(
        use_cases,
        repo,
        _uniforma_tree(),
        parent_id=uniforma_head_id,
        parent_path="/uniforma-va-maxsus-kiyimlar",
        form_definition_id=uniform_form_id,
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
                await _backfill_search_configuration_facets(use_cases, repo, now=now)

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
                # 2026-08-23 TZ: same field shape (district/condition/seller_type/sale_unit/
                # delivery/payment_method) as `_building_materials_fields()`, applied here as a
                # backfill rather than a rewrite of `_seed_furniture_form`'s own raw-dict
                # definition above (already published; a rewrite there wouldn't reach production
                # -- see `_backfill_form_definition_fields`'s own docstring).
                await _backfill_form_definition_fields(
                    use_cases,
                    repo,
                    code="mebel-materiallari-form",
                    fields=[
                        _field(
                            "district",
                            "asosiy",
                            "Tuman",
                            "select",
                            facet=True,
                            order=1,
                            options=_TASHKENT_DISTRICTS + _TASHKENT_REGION_DISTRICTS,
                        ),
                        _field(
                            "seller_type",
                            "asosiy",
                            "Sotuvchi turi",
                            "select",
                            facet=True,
                            order=3,
                            options=[
                                ("dealer_store", "Rasmiy diler / Do'kon"),
                                ("manufacturer", "Ishlab chiqaruvchi"),
                                ("individual", "Jismoniy shaxs"),
                            ],
                        ),
                        _field(
                            "sale_unit",
                            "asosiy",
                            "O'lchov birligi / Sotish hajmi",
                            "select",
                            facet=True,
                            order=4,
                            options=[
                                ("piece", "Dona"),
                                ("sqm", "Kvadrat metr (m2)"),
                                ("linear_m", "Pogonny metr (p/m)"),
                                ("sheet_slab", "List / Plita"),
                                ("sack_liter", "Qop / Litr"),
                                ("wholesale", "Optom (Ulgurji)"),
                            ],
                        ),
                        _field(
                            "delivery",
                            "asosiy",
                            "Yetkazib berish (Dostavka)",
                            "select",
                            facet=True,
                            order=5,
                            options=[
                                ("free", "Bor (Bepul)"),
                                ("paid", "Bor (Alohida to'lovli)"),
                                ("pickup", "Olib ketish (Samovivoz)"),
                            ],
                        ),
                        _field(
                            "payment_method",
                            "asosiy",
                            "To'lov shakli",
                            "select",
                            facet=True,
                            order=6,
                            options=[
                                ("cash", "Naqd pul"),
                                ("bank_transfer", "Pul o'tkazish (Perechisleniye/NDS)"),
                                ("app_payment", "Ilova orqali (Click/Payme)"),
                            ],
                        ),
                    ],
                    force_order={
                        "condition": 2,
                        "brand": 90,
                        "material": 91,
                        "color": 92,
                        "warranty_months": 93,
                        "delivery_available": 94,
                    },
                    now=now,
                )
                await _backfill_form_definition_field_options(
                    use_cases,
                    repo,
                    code="mebel-materiallari-form",
                    field_options={
                        "condition": [("leftover", "Qolgan/Ortiqcha material")],
                    },
                    now=now,
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
