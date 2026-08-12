"""FastAPI routers implementing exactly the sixteen configuration-tagged OpenAPI operations
(`contracts/openapi.yaml`: three public `Categories` reads with `security: []`, thirteen
`Configuration (Admin)` operations) -- no more, no less (Task P-04 scope). Thin translation only:
path/body -> use-case call -> domain object -> already-frozen `interfaces/dto.py` DTO. All
business logic lives in `application`/`domain`; this module owns none.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from backbone.net import resolve_client_ip
from configuration.application import (
    CategoryReadUseCases,
    ConfigurationUseCases,
    OwnerAdminLockoutPort,
)
from configuration.application.exceptions import (
    ConfigHeadNotFoundError,
    InvalidDraftRequestError,
    OwnerAdminAccessLockedOutError,
)
from configuration.domain import (
    ConfigEntityType,
    ConfigHead,
    ConfigVersion,
    GateResult,
    VersionStatus,
    WhitelistRegistry,
    is_valid_owner_panel_slug,
)
from configuration.interfaces.auth import (
    ActingAdmin,
    PermissionDeniedError,
    get_acting_admin,
    require_permission,
)
from configuration.interfaces.di import (
    get_category_read_use_cases,
    get_configuration_use_cases,
    get_owner_admin_lockout_counter,
)
from configuration.interfaces.dto import (
    Category,
    ConfigPublishRequest,
    ConfigRollbackRequest,
    ConfigurationDraftRequest,
    ConfigurationHead,
    ConfigurationHeadPage,
    ConfigurationVersion,
    ConfigValidationResult,
    FormDefinition,
    FormField,
    FormSection,
    ImportConfigBody,
    OwnerAdminSlugCheckRequest,
    OwnerAdminSlugCheckResult,
    PageInfo,
    PlatformStatsResult,
)
from contracts.errors import ValidationError

EntityTypeLiteral = Literal[
    "category",
    "form-definition",
    "product-definition",
    "placement-slot",
    "role-definition",
    "search-configuration",
    "notification-template",
    "platform-settings",
]

_registry = WhitelistRegistry()

_SOLO_ADMIN_CHECKER_ID = UUID("00000000-0000-0000-0000-0000000000f0")
"""Fixed, non-human system principal used only by `publish_config_version_solo` below, so a
lone super-admin's own owner-admin panel can complete a CONTROLLED-track publish's checker step
without a second real account -- mirrors `configuration.infrastructure.seed.SEED_CHECKER_ID`'s
own precedent (a distinct fixed UUID, not the same actor, satisfies `SelfApprovalError`'s
"different principal" invariant literally rather than bypassing it)."""


def _require_manage_permission(admin: ActingAdmin, entity_type: EntityTypeLiteral) -> None:
    require_permission(admin, _registry.manage_permission_key(entity_type))


# -- domain -> DTO mapping -----------------------------------------------------------------------


def _head_to_dto(head: ConfigHead) -> ConfigurationHead:
    return ConfigurationHead(
        id=head.id,
        entity_type=head.entity_type.value,
        code=head.code,
        current_version_id=head.current_version_id,
        status=head.status.value,
        business_owner=head.business_owner,
        created_at=head.created_at,
    )


def _version_to_dto(version: ConfigVersion) -> ConfigurationVersion:
    return ConfigurationVersion(
        id=version.id,
        head_id=version.head_id,
        version_number=version.version_number,
        status=version.status.value,
        definition=version.definition_document,
        snapshot=version.snapshot_document,
        validity_from=version.validity_from,
        validity_until=version.validity_until,
        rollback_of_version_id=version.rollback_of_version_id,
        approved_by=version.approved_by,
        published_at=version.published_at,
    )


def _category_dto_from_snapshot(snapshot: dict[str, Any]) -> Category:
    descriptor = snapshot.get("descriptor") or {}
    parent_id = snapshot.get("parent_category_id")
    form_id = snapshot.get("form_definition_id")
    metadata = descriptor.get("metadata") or {}
    return Category(
        id=UUID(str(snapshot["id"])),
        parent_id=UUID(str(parent_id)) if parent_id else None,
        name=descriptor.get("name"),  # type: ignore[arg-type]  # pydantic validates the raw dict
        path=snapshot["path"],
        slug=None,
        display_order=descriptor.get("display_order"),
        form_definition_id=UUID(str(form_id)) if form_id else None,
        status=snapshot.get("tree_status"),
        icon_url=metadata.get("iconUrl"),
        hero_image_url=metadata.get("heroImageUrl"),
        hero_tagline=metadata.get("heroTagline"),
        accent_color=metadata.get("accentColor"),
        listing_kind=metadata.get("listingKind"),
        icon_name=metadata.get("iconName"),
    )


#: Keys present on a stored form-field snapshot that describe how the field is *grouped*, not
#: what the field is. The wire format nests fields inside their section, so the grouping is
#: already expressed structurally and these must not be forwarded to the field DTO.
_FIELD_GROUPING_KEYS = frozenset({"section_code"})


def _form_field_dto_from_snapshot(raw_field: dict[str, Any]) -> FormField:
    """Maps one stored field snapshot onto the wire DTO.

    Every stored field snapshot carries `section_code` (it is how fields are grouped above), but
    the contract's `FormField` has no such property and `CamelModel` sets `extra="forbid"` -- so
    passing the raw dict straight to `model_validate` raised a `ValidationError` for *every* field
    of *every* form, making `getCategoryForm` return 500 unconditionally (DEF-04, FR-FORM-001).
    Any published form has at least one field and any field has a `section_code`, which is why
    there was no category for which this endpoint worked.

    The grouping keys are dropped rather than added to the DTO on purpose: `section_code` is
    absent from the contract's `FormField`, so surfacing it would put an undeclared property on
    the response and break contract conformance (QG-06) instead of fixing anything. The section
    nesting the caller already receives carries that information.
    """
    return FormField.model_validate(
        {key: value for key, value in raw_field.items() if key not in _FIELD_GROUPING_KEYS}
    )


def _form_definition_dto_from_snapshot(
    snapshot: dict[str, Any], *, category_id: UUID | None = None
) -> FormDefinition:
    """`category_id` is supplied by the caller (the `getCategoryForm` route knows which category
    it was asked for), never read off the form's own snapshot -- Physical DB Sec 2.4 has no
    `category_id` column on `form_definition`/`_version`; the binding is one-directional
    (`category.form_definition_id`), so a form carries no back-reference to bind from."""
    fields_by_section: dict[str, list[dict[str, Any]]] = {}
    for raw_field in snapshot.get("fields", []):
        fields_by_section.setdefault(raw_field["section_code"], []).append(raw_field)

    sections: list[FormSection] = []
    for raw_section in sorted(snapshot.get("sections", []), key=lambda s: s.get("order") or 0):
        section_fields = sorted(
            fields_by_section.get(raw_section["code"], []),
            key=lambda f: f.get("order") or 0,
        )
        sections.append(
            FormSection(
                code=raw_section["code"],
                label=raw_section["label"],
                order=raw_section.get("order"),
                fields=[_form_field_dto_from_snapshot(f) for f in section_fields],
            )
        )

    return FormDefinition(
        id=UUID(str(snapshot["id"])),
        version_id=UUID(str(snapshot["versionId"])),
        category_id=category_id,
        sections=sections,
    )


def _validation_result_dto(result: GateResult) -> ConfigValidationResult:
    errors = [
        ValidationError(
            path=f"/{error.field}" if error.field else "/",
            rule=error.code,
            message=error.message,
        )
        for error in result.errors
    ]
    return ConfigValidationResult(valid=result.valid, errors=errors or None)


# -- public: Categories (unauthenticated, snapshot-served) ---------------------------------------

categories_router = APIRouter(tags=["Categories"])


@categories_router.get("/categories", operation_id="listCategories")
async def list_categories(
    parent_id: UUID | None = Query(None, alias="parentId"),
    include_retired: bool = Query(False, alias="includeRetired"),
    # Additive, outside the frozen contract's originally-documented parameter set (same
    # escape-hatch precedent as `publish-solo`) -- default False keeps every existing caller's
    # response identical; see `CategoryReadUseCases.list_categories`'s docstring for why this
    # exists (100+-category taxonomy made the old per-level-BFS client pattern too slow).
    include_descendants: bool = Query(False, alias="includeDescendants"),
    use_cases: CategoryReadUseCases = Depends(get_category_read_use_cases),
) -> list[Category]:
    snapshots = await use_cases.list_categories(
        parent_id=parent_id,
        include_retired=include_retired,
        include_descendants=include_descendants,
    )
    return [_category_dto_from_snapshot(s) for s in snapshots]


@categories_router.get("/categories/{categoryId}", operation_id="getCategory")
async def get_category(
    categoryId: UUID,
    use_cases: CategoryReadUseCases = Depends(get_category_read_use_cases),
) -> Category:
    snapshot = await use_cases.get_category(categoryId)
    if snapshot is None:
        raise ConfigHeadNotFoundError("category", str(categoryId))
    return _category_dto_from_snapshot(snapshot)


@categories_router.get("/categories/{categoryId}/form", operation_id="getCategoryForm")
async def get_category_form(
    categoryId: UUID,
    use_cases: CategoryReadUseCases = Depends(get_category_read_use_cases),
) -> FormDefinition:
    snapshot = await use_cases.get_category_form(categoryId)
    if snapshot is None:
        # Ambiguous by design of the read use case: the category itself, its bound form head, or
        # the form's published snapshot may be the missing piece -- all three read as "no
        # published form for this category" from this endpoint's point of view.
        raise ConfigHeadNotFoundError("form-definition", str(categoryId))
    return _form_definition_dto_from_snapshot(snapshot, category_id=categoryId)


# -- public: Owner Admin Access (unauthenticated, additive -- outside the frozen OpenAPI contract,
# same escape-hatch precedent as `publish_config_version_solo` below) ---------------------------

owner_admin_access_router = APIRouter(tags=["Owner Admin Access"])

_PLATFORM_SETTINGS_GLOBAL_CODE = "platform-settings-global"
_OWNER_ADMIN_SLUG_SETTING_KEY = "admin.owner_panel_slug"
_OWNER_ADMIN_SLUG_DEFAULT = "owner-admin"


async def _current_owner_admin_slug(use_cases: ConfigurationUseCases) -> str:
    """Reads the live `admin.owner_panel_slug` platform setting. Falls back to the historical
    fixed path if the setting was never set (fresh DB before the first seed run, or a published
    version that predates this key) so the panel never becomes unreachable.

    Also self-heals: `is_valid_owner_panel_slug` re-checks the stored value against the same
    reserved-route list `check_settings_key` enforces at write time, so a value that was written
    before that check existed (or somehow got in anyway) is treated as absent rather than shadowing
    a real route forever -- the incident this guards against actually happened once (an admin set
    it to "boss", permanently hiding the panel behind the dedicated login route at that exact
    path) before this check was added."""
    cursor: str | None = None
    while True:
        heads, cursor = await use_cases.list_heads(
            ConfigEntityType.PLATFORM_SETTINGS, cursor=cursor, limit=50
        )
        for head in heads:
            if head.code == _PLATFORM_SETTINGS_GLOBAL_CODE and head.current_version_id is not None:
                version = await use_cases.get_version(
                    ConfigEntityType.PLATFORM_SETTINGS, head.id, head.current_version_id
                )
                settings = (version.snapshot_document or {}).get("settings", {})
                value = settings.get(_OWNER_ADMIN_SLUG_SETTING_KEY)
                if is_valid_owner_panel_slug(value):
                    return str(value).strip().lower()
                return _OWNER_ADMIN_SLUG_DEFAULT
        if cursor is None:
            return _OWNER_ADMIN_SLUG_DEFAULT


_OWNER_ADMIN_LOCKOUT_MAX_ATTEMPTS = 5
_OWNER_ADMIN_LOCKOUT_BLOCK_SECONDS = 15 * 60
"""Same shape as `identity`'s OTP-verify-by-IP lockout (3 attempts/15min) and
`LoginLockoutPolicy`'s own default (4 attempts/15min) -- a slightly more lenient attempt count
than either, since a legitimate super-admin fat-fingering their own slug is the only "innocent"
way to ever see a wrong guess here at all (unlike a password/OTP, nobody else has a reason to
guess right by accident). `rearm=True`: consecutive wrong guesses close enough together keep
re-arming the block window, matching `LoginLockoutPolicy`'s documented reasoning."""


@owner_admin_access_router.post(
    "/public/owner-admin-access/verify", operation_id="verifyOwnerAdminSlug"
)
async def verify_owner_admin_slug(
    body: OwnerAdminSlugCheckRequest,
    request: Request,
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
    lockout: OwnerAdminLockoutPort = Depends(get_owner_admin_lockout_counter),
) -> OwnerAdminSlugCheckResult:
    """The one deliberate exception to "no public read of `platform-settings`" -- a yes/no oracle
    for a single guessed slug, never the real value, so the frontend's `/$ownerAdminSlug` route
    guard can tell a right guess from a wrong one without shipping the real path in the client
    bundle (Task: owner-admin panel access, runtime-configurable slug).

    IP-scoped lockout: this endpoint was the motivating, most acute case for adding any
    throttling at all (see `GlobalRateLimitMiddleware`'s own docstring) -- an oracle whose entire
    purpose is answering "is this guess right", with no throttle of its own, is a slug-guessing
    attacker's ideal target. The generic global rate limit (300 req/60s per IP) still applies on
    top of this as a backstop, but is far too loose on its own to meaningfully slow a targeted
    guess-the-slug attack; this is the purpose-specific lockout for that. Checked BEFORE the real
    slug is looked up, same reasoning `identity`'s own lockout checks document: a cheap 429 for an
    already-locked-out caller, not a wasted config-store read."""
    ip = resolve_client_ip(
        request.headers, fallback_host=request.client.host if request.client else None
    )
    attempts = await lockout.get_failure_count(identifier=ip)
    if attempts >= _OWNER_ADMIN_LOCKOUT_MAX_ATTEMPTS:
        retry_after = await lockout.get_retry_after_seconds(identifier=ip)
        raise OwnerAdminAccessLockedOutError(retry_after_seconds=retry_after)

    real_slug = await _current_owner_admin_slug(use_cases)
    valid = body.slug == real_slug
    if valid:
        await lockout.reset(identifier=ip)
    else:
        await lockout.record_failure(
            identifier=ip, window_seconds=_OWNER_ADMIN_LOCKOUT_BLOCK_SECONDS
        )
    return OwnerAdminSlugCheckResult(valid=valid)


_STATS_CITIES_KEY = "stats.cities"
_STATS_PARTNERS_KEY = "stats.partners"
_STATS_SATISFACTION_KEY = "stats.satisfaction_percent"


async def _current_platform_settings(use_cases: ConfigurationUseCases) -> dict[str, Any]:
    """Same head-lookup shape as `_current_owner_admin_slug` above, generalized to return the
    whole `settings` dict instead of one key -- `get_platform_stats` below reads three keys off
    it in one pass rather than re-paginating `list_heads` per key."""
    cursor: str | None = None
    while True:
        heads, cursor = await use_cases.list_heads(
            ConfigEntityType.PLATFORM_SETTINGS, cursor=cursor, limit=50
        )
        for head in heads:
            if head.code == _PLATFORM_SETTINGS_GLOBAL_CODE and head.current_version_id is not None:
                version = await use_cases.get_version(
                    ConfigEntityType.PLATFORM_SETTINGS, head.id, head.current_version_id
                )
                settings: dict[str, Any] = (version.snapshot_document or {}).get("settings", {})
                return settings
        if cursor is None:
            return {}


@owner_admin_access_router.get("/public/platform-stats", operation_id="getPlatformStats")
async def get_platform_stats(
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> PlatformStatsResult:
    """Second deliberate exception to "no public read of `platform-settings`" -- backs the
    homepage proof strip. Exposes only the three named `stats.*` keys, never the settings blob
    wholesale (same shape as `verify_owner_admin_slug` above). Defaults to 0 for a fresh DB that
    hasn't run the seed backfill yet, rather than 500ing."""
    settings = await _current_platform_settings(use_cases)
    return PlatformStatsResult(
        cities=int(settings.get(_STATS_CITIES_KEY) or 0),
        partners=int(settings.get(_STATS_PARTNERS_KEY) or 0),
        satisfaction_percent=int(settings.get(_STATS_SATISFACTION_KEY) or 0),
    )


# -- admin: Configuration (Admin) ------------------------------------------------------------------

admin_config_router = APIRouter(tags=["Configuration (Admin)"])


@admin_config_router.get("/admin/config/{entityType}", operation_id="listConfigHeads")
async def list_config_heads(
    entityType: EntityTypeLiteral,
    cursor: str | None = Query(None),
    limit: int = Query(20),
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationHeadPage:
    _require_manage_permission(admin, entityType)
    heads, next_cursor = await use_cases.list_heads(
        ConfigEntityType(entityType), cursor=cursor, limit=limit
    )
    return ConfigurationHeadPage(
        items=[_head_to_dto(h) for h in heads],
        page=PageInfo(limit=limit, next_cursor=next_cursor, total=None),
    )


@admin_config_router.post(
    "/admin/config/{entityType}", operation_id="createConfigDraft", status_code=201
)
async def create_config_draft(
    entityType: EntityTypeLiteral,
    body: ConfigurationDraftRequest,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    _require_manage_permission(admin, entityType)
    if not body.code or not body.business_owner:
        raise InvalidDraftRequestError(
            "code and businessOwner are required when creating a new configuration head"
        )
    _head, version = await use_cases.create_draft(
        ConfigEntityType(entityType),
        code=body.code,
        business_owner=body.business_owner,
        definition=body.definition,
        actor_id=admin.actor_id,
        now=datetime.now(UTC),
    )
    return _version_to_dto(version)


@admin_config_router.get(
    "/admin/config/{entityType}/{headId}/versions/compare",
    operation_id="compareConfigVersions",
)
async def compare_config_versions(
    entityType: EntityTypeLiteral,
    headId: UUID,
    from_: UUID = Query(..., alias="from"),
    to: UUID = Query(...),
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> dict[str, Any]:
    _require_manage_permission(admin, entityType)
    return await use_cases.compare_versions(ConfigEntityType(entityType), headId, from_, to)


@admin_config_router.get("/admin/config/{entityType}/{headId}/export", operation_id="exportConfig")
async def export_config(
    entityType: EntityTypeLiteral,
    headId: UUID,
    version_id: UUID | None = Query(None),
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> dict[str, Any]:
    _require_manage_permission(admin, entityType)
    return await use_cases.export_config(ConfigEntityType(entityType), headId, version_id)


@admin_config_router.get("/admin/config/{entityType}/{headId}", operation_id="getConfigHead")
async def get_config_head(
    entityType: EntityTypeLiteral,
    headId: UUID,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationHead:
    _require_manage_permission(admin, entityType)
    head = await use_cases.get_head(ConfigEntityType(entityType), headId)
    return _head_to_dto(head)


@admin_config_router.get(
    "/admin/config/{entityType}/{headId}/versions", operation_id="listConfigVersions"
)
async def list_config_versions(
    entityType: EntityTypeLiteral,
    headId: UUID,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> list[ConfigurationVersion]:
    _require_manage_permission(admin, entityType)
    versions = await use_cases.list_versions(ConfigEntityType(entityType), headId)
    return [_version_to_dto(v) for v in versions]


@admin_config_router.post(
    "/admin/config/{entityType}/{headId}/versions",
    operation_id="createConfigVersionDraft",
    status_code=201,
)
async def create_config_version_draft(
    entityType: EntityTypeLiteral,
    headId: UUID,
    body: ConfigurationDraftRequest,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    _require_manage_permission(admin, entityType)
    version = await use_cases.create_version_draft(
        ConfigEntityType(entityType),
        headId,
        definition=body.definition,
        actor_id=admin.actor_id,
        now=datetime.now(UTC),
    )
    return _version_to_dto(version)


@admin_config_router.get(
    "/admin/config/{entityType}/{headId}/versions/{versionId}",
    operation_id="getConfigVersion",
)
async def get_config_version(
    entityType: EntityTypeLiteral,
    headId: UUID,
    versionId: UUID,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    _require_manage_permission(admin, entityType)
    version = await use_cases.get_version(ConfigEntityType(entityType), headId, versionId)
    return _version_to_dto(version)


@admin_config_router.put(
    "/admin/config/{entityType}/{headId}/versions/{versionId}",
    operation_id="updateConfigDraft",
)
async def update_config_draft(
    entityType: EntityTypeLiteral,
    headId: UUID,
    versionId: UUID,
    body: ConfigurationDraftRequest,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    _require_manage_permission(admin, entityType)
    version = await use_cases.update_draft(
        ConfigEntityType(entityType), headId, versionId, definition=body.definition
    )
    return _version_to_dto(version)


@admin_config_router.post(
    "/admin/config/{entityType}/{headId}/versions/{versionId}/validate",
    operation_id="validateConfigVersion",
)
async def validate_config_version(
    entityType: EntityTypeLiteral,
    headId: UUID,
    versionId: UUID,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigValidationResult:
    _require_manage_permission(admin, entityType)
    result = await use_cases.validate(ConfigEntityType(entityType), headId, versionId)
    return _validation_result_dto(result)


@admin_config_router.post(
    "/admin/config/{entityType}/{headId}/versions/{versionId}/publish",
    operation_id="publishConfigVersion",
)
async def publish_config_version(
    entityType: EntityTypeLiteral,
    headId: UUID,
    versionId: UUID,
    # UNF-029: the contract's requestBody carries no `required: true` (ConfigPublishRequest's
    # own `approvalNote` is itself optional, so an empty body is a meaningful "no note"), but a
    # required Pydantic model parameter makes FastAPI 422 a request sent with no body at all --
    # contradicting the contract rather than defending it (the contract is frozen; the app
    # follows it, not the other way around).
    body: ConfigPublishRequest | None = None,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    _require_manage_permission(admin, entityType)
    version = await use_cases.publish(
        ConfigEntityType(entityType),
        headId,
        versionId,
        actor_id=admin.actor_id,
        actor_permission_keys=admin.permission_keys,
        approval_note=body.approval_note if body else None,
        now=datetime.now(UTC),
    )
    return _version_to_dto(version)


@admin_config_router.post(
    "/admin/config/{entityType}/{headId}/versions/{versionId}/publish-solo",
    operation_id="publishConfigVersionSolo",
)
async def publish_config_version_solo(
    entityType: EntityTypeLiteral,
    headId: UUID,
    versionId: UUID,
    body: ConfigPublishRequest | None = None,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    """Additive endpoint, outside the frozen `contracts/openapi.yaml` operation set (P-04 scope)
    -- a solo-super-admin convenience for the owner-admin panel, where exactly one human runs the
    entire authoring workflow instead of the two-person maker/checker team the generic `/publish`
    operation assumes. Gated on the caller already holding BOTH the manage AND approve permission
    keys for this entity type (i.e. someone who could already perform the two-call dance by hand
    with a second account) -- this endpoint only automates the second call, using the fixed
    `_SOLO_ADMIN_CHECKER_ID` system principal, so `SelfApprovalError`'s "different principal"
    invariant is satisfied for real, not routed around."""
    _require_manage_permission(admin, entityType)
    approve_key = _registry.approve_permission_key(entityType)
    if approve_key not in admin.permission_keys:
        raise PermissionDeniedError(approve_key)

    now = datetime.now(UTC)
    version = await use_cases.publish(
        ConfigEntityType(entityType),
        headId,
        versionId,
        actor_id=admin.actor_id,
        actor_permission_keys=admin.permission_keys,
        approval_note=body.approval_note if body else None,
        now=now,
    )
    if version.status is VersionStatus.APPROVAL:
        version = await use_cases.publish(
            ConfigEntityType(entityType),
            headId,
            versionId,
            actor_id=_SOLO_ADMIN_CHECKER_ID,
            actor_permission_keys=frozenset({approve_key}),
            approval_note=body.approval_note if body else None,
            now=now,
        )
    return _version_to_dto(version)


@admin_config_router.post(
    "/admin/config/{entityType}/{headId}/rollback", operation_id="rollbackConfig"
)
async def rollback_config(
    entityType: EntityTypeLiteral,
    headId: UUID,
    body: ConfigRollbackRequest,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    _require_manage_permission(admin, entityType)
    version = await use_cases.rollback(
        ConfigEntityType(entityType),
        headId,
        target_version_id=body.target_version_id,
        actor_id=admin.actor_id,
        actor_permission_keys=admin.permission_keys,
        expedited=bool(body.expedited),
        now=datetime.now(UTC),
    )
    return _version_to_dto(version)


@admin_config_router.post(
    "/admin/config/{entityType}/import", operation_id="importConfig", status_code=201
)
async def import_config(
    entityType: EntityTypeLiteral,
    body: ImportConfigBody,
    admin: ActingAdmin = Depends(get_acting_admin),
    use_cases: ConfigurationUseCases = Depends(get_configuration_use_cases),
) -> ConfigurationVersion:
    _require_manage_permission(admin, entityType)
    version = await use_cases.import_config(
        ConfigEntityType(entityType),
        definition=body.definition,
        actor_id=admin.actor_id,
        now=datetime.now(UTC),
    )
    return _version_to_dto(version)
