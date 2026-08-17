"""`SqlalchemyConfigHeadRepository` -- the one repository adapter implementing
`application.ports.ConfigHeadRepository` for all eight entity types (DB Architecture Sec 18:
"exactly one repository per aggregate root" -- constructed once per entity type at the
composition root, sharing this single class). Maps ORM rows to/from the persistence-ignorant
`domain.ConfigHead`/`domain.ConfigVersion` dataclasses (DB Architecture Sec 18 "domain objects
are persistence-ignorant: mapping lives in infrastructure/").
"""

from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.domain import (
    ConfigEntityType,
    ConfigHead,
    ConfigVersion,
    HeadStatus,
    VersionStatus,
)
from configuration.infrastructure.persistence.models import (
    HEAD_MODEL_BY_ENTITY_TYPE,
    VERSION_MODEL_BY_ENTITY_TYPE,
    PermissionGroup,
)


def _head_to_domain(entity_type: ConfigEntityType, row: Any) -> ConfigHead:
    return ConfigHead(
        id=row.id,
        entity_type=entity_type,
        code=row.code,
        current_version_id=row.current_version_id,
        status=HeadStatus(row.status),
        business_owner=row.business_owner,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
        lock_version=row.lock_version,
    )


def _version_to_domain(row: Any) -> ConfigVersion:
    return ConfigVersion(
        id=row.id,
        head_id=row.head_id,
        version_number=row.version_number,
        status=VersionStatus(row.status),
        definition_document=row.definition_document,
        snapshot_document=row.snapshot_document,
        validity_from=row.validity_from,
        validity_until=row.validity_until,
        rollback_of_version_id=row.rollback_of_version_id,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        published_by=row.published_by,
        published_at=row.published_at,
        created_at=row.created_at,
        created_by=row.created_by,
    )


def _encode_cursor(created_at: Any, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Returns real `datetime`/`UUID` objects, not their string forms -- binding plain strings
    into the `row(created_at, id) > row($1, $2)` comparison below left both sides untyped from
    Postgres's perspective (`asyncpg` has no implicit `timestamptz > varchar`/`uuid > varchar`
    cast), which raised `UndefinedFunctionError` on every page past the first. `_encode_cursor`
    already starts from real `datetime`/`UUID` values -- this just inverts that back to them."""
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id_str = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id_str)


def _as_uuid(value: Any) -> UUID | None:
    """A `UUID` if `value` can be read as one, else `None` -- never raises.

    Promoted columns are a denormalised, indexable copy of `definition_document` (Physical DB
    Sec 2.4). A draft is allowed to hold a malformed value; only the gate judges correctness, so
    a bad value must degrade the *promotion*, not fail the save."""
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _as_text(value: Any) -> str:
    """A `str` for a NOT NULL promoted text column, `""` when absent or of the wrong JSON type --
    the same "safe sentinel" `path`/`role_name` already used, applied to the columns that were
    missing it and were therefore raising `NotNullViolation` on an incomplete draft."""
    return value if isinstance(value, str) else ""


def _as_int(value: Any, fallback: int | None) -> int | None:
    """An `int` for a promoted integer column, else `fallback`. `bool` is excluded deliberately:
    it is an `int` subclass in Python, and `True` promoted into a width/term column is a silent
    absurdity rather than an obvious one."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback


class SqlalchemyConfigHeadRepository:
    """One instance per request/unit-of-work, bound to a single `AsyncSession` (Playbook
    pattern: the session's transaction is the caller's -- this repository never commits)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _head_model(self, entity_type: ConfigEntityType) -> Any:
        return HEAD_MODEL_BY_ENTITY_TYPE[entity_type.value]

    def _version_model(self, entity_type: ConfigEntityType) -> Any:
        return VERSION_MODEL_BY_ENTITY_TYPE[entity_type.value]

    async def get_head(self, entity_type: ConfigEntityType, head_id: UUID) -> ConfigHead | None:
        model = self._head_model(entity_type)
        row = await self._session.get(model, head_id)
        return _head_to_domain(entity_type, row) if row is not None else None

    async def get_head_by_code(self, entity_type: ConfigEntityType, code: str) -> ConfigHead | None:
        model = self._head_model(entity_type)
        result = await self._session.execute(select(model).where(model.code == code))
        row = result.scalar_one_or_none()
        return _head_to_domain(entity_type, row) if row is not None else None

    async def list_heads(
        self, entity_type: ConfigEntityType, *, cursor: str | None, limit: int
    ) -> tuple[list[ConfigHead], str | None]:
        model = self._head_model(entity_type)
        stmt = select(model).order_by(model.created_at, model.id).limit(limit + 1)
        if cursor is not None:
            cursor_created_at, cursor_id = _decode_cursor(cursor)
            stmt = stmt.where(
                func.row(model.created_at, model.id) > func.row(cursor_created_at, cursor_id)
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)
        return [_head_to_domain(entity_type, r) for r in rows], next_cursor

    async def list_versions(
        self, entity_type: ConfigEntityType, head_id: UUID
    ) -> list[ConfigVersion]:
        model = self._version_model(entity_type)
        result = await self._session.execute(
            select(model).where(model.head_id == head_id).order_by(model.version_number)
        )
        return [_version_to_domain(r) for r in result.scalars().all()]

    async def get_version(
        self, entity_type: ConfigEntityType, head_id: UUID, version_id: UUID
    ) -> ConfigVersion | None:
        model = self._version_model(entity_type)
        result = await self._session.execute(
            select(model).where(model.id == version_id, model.head_id == head_id)
        )
        row = result.scalar_one_or_none()
        return _version_to_domain(row) if row is not None else None

    async def latest_version_number(self, entity_type: ConfigEntityType, head_id: UUID) -> int:
        model = self._version_model(entity_type)
        result = await self._session.execute(
            select(func.max(model.version_number)).where(model.head_id == head_id)
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else 0

    async def add_head(self, entity_type: ConfigEntityType, head: ConfigHead) -> None:
        model = self._head_model(entity_type)
        self._session.add(
            model(
                id=head.id,
                code=head.code,
                current_version_id=head.current_version_id,
                status=head.status.value,
                business_owner=head.business_owner,
                created_at=head.created_at,
                created_by=head.created_by,
                updated_at=head.updated_at,
                updated_by=head.updated_by,
                lock_version=head.lock_version,
            )
        )
        await self._session.flush()

    async def add_version(self, entity_type: ConfigEntityType, version: ConfigVersion) -> None:
        model = self._version_model(entity_type)
        extra = await self._extra_version_columns(entity_type, version.definition_document)
        self._session.add(
            model(
                id=version.id,
                head_id=version.head_id,
                version_number=version.version_number,
                status=version.status.value,
                definition_document=version.definition_document,
                snapshot_document=version.snapshot_document,
                validity_from=version.validity_from,
                validity_until=version.validity_until,
                rollback_of_version_id=version.rollback_of_version_id,
                approved_by=version.approved_by,
                approved_at=version.approved_at,
                published_by=version.published_by,
                published_at=version.published_at,
                created_at=version.created_at,
                created_by=version.created_by,
                **extra,
            )
        )
        await self._session.flush()

    async def _existing_uuid(self, referenced: ConfigEntityType, value: Any) -> UUID | None:
        """The promoted value as a `UUID`, but only if it is well-formed AND actually references
        an existing row of `model`; `None` otherwise.

        Both halves matter, and both were missing. A promoted UUID column that is malformed
        (`"not-a-uuid"`) reaches asyncpg as a bind parameter and raises `DataError`; one that is
        well-formed but references nothing violates the column's foreign key. Either way the
        whole draft save failed with a 500, which is exactly what this class's own
        `_extra_version_columns` docstring says must not happen -- "a maker can always save and
        get a precise rejection at validate/submit time".

        Resolving to `None` keeps the foreign key honest (no dangling reference is ever written)
        while letting the raw, possibly-wrong value stay in `definition_document`, which is the
        source of truth and what the gate reads. A category drafted against a form that does not
        exist yet is ordinary work-in-progress, not an error to reject at save time.
        """
        parsed = _as_uuid(value)
        if parsed is None:
            return None
        head_model = self._head_model(referenced)
        return parsed if await self._session.get(head_model, parsed) is not None else None

    @staticmethod
    def _is_non_negative_decimal(value: Any) -> bool:
        """`price_amount` arrives as whatever JSON type the request body used -- this codebase's
        convention for money fields is a decimal-as-string (`"10.00"`, see
        `apps/backend/tests/configuration/conftest.py`'s `minimal_content`) to avoid float
        precision loss, but a raw JSON number is equally valid input at draft-save time (the
        gate, not this promoted-column mapping, owns type/structure validation)."""
        if value is None:
            return False
        try:
            return Decimal(str(value)) >= 0
        except (TypeError, ValueError, ArithmeticError):
            return False

    async def _extra_version_columns(
        self, entity_type: ConfigEntityType, content: dict[str, Any]
    ) -> dict[str, Any]:
        """Physical DB Sec 2.4 "per-entity promoted columns": values extracted from the
        immutable `definition_document` at write time -- safe and indexable, never divergent
        because versions never change (Physical DB Sec 2.4).

        A handful of promoted columns carry a DB-level CHECK constraint that mirrors a gate
        rule (`domain/gate.py`); an out-of-range/missing value is clamped to a safe sentinel
        here so `create_draft`/`update_version` can always structurally save a draft (Config
        Framework Sec 9: a maker can always save and get a precise rejection at validate/submit
        time) -- the true, possibly-invalid value stays in `definition_document` for the gate
        to catch."""
        if entity_type is ConfigEntityType.CATEGORY:
            return {
                "parent_category_id": await self._existing_uuid(
                    ConfigEntityType.CATEGORY, content.get("parent_category_id")
                ),
                "path": _as_text(content.get("path")),
                "display_order": _as_int(content.get("descriptor", {}).get("display_order"), 0),
                "form_definition_id": await self._existing_uuid(
                    ConfigEntityType.FORM_DEFINITION, content.get("form_definition_id")
                ),
                "tree_status": content.get("tree_status") or "ACTIVE",
            }
        if entity_type is ConfigEntityType.PRODUCT_DEFINITION:
            price_amount = content.get("price_amount")
            return {
                "product_type": _as_text(content.get("product_type")),
                "price_amount": (
                    price_amount if self._is_non_negative_decimal(price_amount) else 0
                ),
                "price_currency": content.get("price_currency") or "UZS",
                "term_days": _as_int(content.get("term_days"), None),
            }
        if entity_type is ConfigEntityType.PLACEMENT_SLOT:
            return {
                "slot_key": _as_text(content.get("slot_key")),
                "page_zone": _as_text(content.get("page_zone")),
                "width_px": _as_int(content.get("width_px"), None),
                "height_px": _as_int(content.get("height_px"), None),
            }
        if entity_type is ConfigEntityType.ROLE_DEFINITION:
            return {
                "role_name": _as_text(content.get("role_name")),
                "permission_keys": content.get("permission_keys") or ["__draft__"],
            }
        if entity_type is ConfigEntityType.SEARCH_CONFIGURATION:
            promotion_page_cap = content.get("promotion_page_cap", 0)
            return {
                "scope_category_id": await self._existing_uuid(
                    ConfigEntityType.CATEGORY, content.get("scope_category_id")
                ),
                "promotion_page_cap": (
                    promotion_page_cap
                    if isinstance(promotion_page_cap, int) and promotion_page_cap >= 0
                    else 0
                ),
            }
        if entity_type is ConfigEntityType.NOTIFICATION_TEMPLATE:
            return {
                "event_key": _as_text(content.get("event_key")),
                "channel": content.get("channel") or "EMAIL",
            }
        if entity_type is ConfigEntityType.PLATFORM_SETTINGS:
            return {"settings_scope": content.get("settings_scope") or "GLOBAL"}
        return {}

    async def update_version(self, entity_type: ConfigEntityType, version: ConfigVersion) -> None:
        model = self._version_model(entity_type)
        row = await self._session.get(model, version.id)
        if row is None:
            raise LookupError(f"version {version.id} not found for update")
        row.status = version.status.value
        row.definition_document = version.definition_document
        row.snapshot_document = version.snapshot_document
        row.validity_from = version.validity_from
        row.validity_until = version.validity_until
        row.approved_by = version.approved_by
        row.approved_at = version.approved_at
        row.published_by = version.published_by
        row.published_at = version.published_at
        for key, value in (
            await self._extra_version_columns(entity_type, version.definition_document)
        ).items():
            setattr(row, key, value)
        await self._session.flush()

    async def update_head(self, entity_type: ConfigEntityType, head: ConfigHead) -> None:
        model = self._head_model(entity_type)
        row = await self._session.get(model, head.id)
        if row is None:
            raise LookupError(f"head {head.id} not found for update")
        row.current_version_id = head.current_version_id
        row.status = head.status.value
        row.business_owner = head.business_owner
        row.updated_at = head.updated_at
        row.updated_by = head.updated_by
        await self._session.flush()

    async def existing_codes(
        self, entity_type: ConfigEntityType, *, exclude_head_id: UUID | None
    ) -> frozenset[str]:
        model = self._head_model(entity_type)
        stmt = select(model.code)
        if exclude_head_id is not None:
            stmt = stmt.where(model.id != exclude_head_id)
        result = await self._session.execute(stmt)
        return frozenset(result.scalars().all())

    async def dependency_exists(self, kind: str, reference: str) -> bool:
        if kind == "permission-group":
            result = await self._session.execute(
                select(PermissionGroup.id).where(PermissionGroup.code == reference)
            )
            return result.scalar_one_or_none() is not None
        entity_type = ConfigEntityType(kind)
        try:
            ref_uuid = UUID(reference)
        except ValueError:
            head = await self.get_head_by_code(entity_type, reference)
        else:
            head = await self.get_head(entity_type, ref_uuid)
        return head is not None and head.current_version_id is not None

    async def category_has_bound_listings(self, category_head_id: UUID) -> bool:
        """I-03. Stub: `catalog.Listing` does not exist yet (Task P-04 excludes implementing
        other modules) -- always reports no bound listings. Replaced by a real adapter calling
        catalog's interface once catalog's own task lands."""
        return False

    async def ancestor_codes(self, entity_type: ConfigEntityType, of_code: str) -> frozenset[str]:
        head = await self.get_head_by_code(entity_type, of_code)
        if head is None or head.current_version_id is None:
            return frozenset()
        version = await self.get_version(entity_type, head.id, head.current_version_id)
        if version is None:
            return frozenset()

        parent_field = (
            "parent_category_id" if entity_type is ConfigEntityType.CATEGORY else "parent_role_code"
        )
        parent_ref = version.definition_document.get(parent_field)
        if not parent_ref:
            return frozenset({of_code})

        if entity_type is ConfigEntityType.CATEGORY:
            parent_head = await self.get_head(entity_type, UUID(str(parent_ref)))
            parent_code = parent_head.code if parent_head is not None else None
        else:
            parent_code = str(parent_ref)

        if parent_code is None:
            return frozenset({of_code})
        return frozenset({of_code}) | await self.ancestor_codes(entity_type, parent_code)

    async def permission_group_keys(self, codes: list[str]) -> dict[str, frozenset[str]]:
        if not codes:
            return {}
        result = await self._session.execute(
            select(PermissionGroup.code, PermissionGroup.permission_keys).where(
                PermissionGroup.code.in_(codes)
            )
        )
        return {code: frozenset(keys) for code, keys in result.all()}

    async def role_flattened_permission_keys(self, role_code: str) -> frozenset[str]:
        head = await self.get_head_by_code(ConfigEntityType.ROLE_DEFINITION, role_code)
        if head is None or head.current_version_id is None:
            return frozenset()
        version = await self.get_version(
            ConfigEntityType.ROLE_DEFINITION, head.id, head.current_version_id
        )
        if version is None:
            return frozenset()
        return frozenset(version.definition_document.get("permission_keys", []))

    async def conflicting_active_version_exists(
        self,
        entity_type: ConfigEntityType,
        head_id: UUID,
        *,
        validity_from: object,
        validity_until: object,
    ) -> bool:
        return False
