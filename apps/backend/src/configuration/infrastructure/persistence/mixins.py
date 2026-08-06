"""The generic Head+Version SQLAlchemy mixins (Physical DB Sec 2.4: "the eight entities share
one physical pattern instantiated eight times"; DB Architecture Sec 18 "build the machinery
once"). Every column common to all eight Head tables lives in `_HeadMixin`; every column common
to all eight Version tables lives in `_VersionMixin`. Cross-table foreign keys
(`current_version_id`, `head_id`, `rollback_of_version_id`) are computed per concrete subclass
via `declared_attr`, reading the plain `__tablename__`/`__head_table_name__` class attributes
each concrete model sets -- the one piece that cannot be shared verbatim, since the FK target
table name differs per entity (`category_version.id` vs `product_definition_version.id`, ...).

`__table_args__` cannot itself be a mixin `declared_attr` here, because several concrete Version
subclasses need to *add* an extra CHECK constraint (e.g. Category's `tree_status` enum) on top
of the shared ones -- a subclass-defined `__table_args__` would silently override rather than
extend the mixin's. `_VersionMixin.base_table_args()` is a plain classmethod instead, called and
extended explicitly by any subclass that needs to.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from backbone.persistence import uuid7
from configuration.domain.lifecycle import HeadStatus, VersionStatus

_HEAD_STATUS_SQL = "(" + ",".join(f"'{s.value}'" for s in HeadStatus) + ")"
_VERSION_STATUS_SQL = "(" + ",".join(f"'{s.value}'" for s in VersionStatus) + ")"


class _HeadMixin:
    """`configuration.<entity>` (Physical DB Sec 2.4 "Head pattern")."""

    __tablename__: str
    """Set by each concrete subclass (plain string, not itself a `declared_attr`) -- read by
    this mixin's own `declared_attr` methods below. Declared here only so mypy --strict knows
    the attribute exists; SQLAlchemy's declarative metaclass provides the real one."""

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=HeadStatus.DRAFT.value)
    business_owner: Mapped[str] = mapped_column(Text, nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    @declared_attr.directive
    @classmethod
    def current_version_id(cls) -> Mapped[PyUUID | None]:
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{cls.__tablename__}_version.id", deferrable=True, initially="DEFERRED"),
            nullable=True,
        )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            UniqueConstraint("code", name=f"ux_{cls.__tablename__}_code"),
            CheckConstraint(f"status IN {_HEAD_STATUS_SQL}", name=f"ck_{cls.__tablename__}_status"),
        )


class _VersionMixin:
    """`configuration.<entity>_version` (Physical DB Sec 2.4 "Version pattern"). Immutability
    (PD-07) is enforced by a guard trigger applied in the migration, not by the ORM mapping."""

    __head_table_name__: str

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=VersionStatus.DRAFT.value
    )
    definition_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    validity_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    validity_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    approved_by: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    published_by: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    @declared_attr.directive
    @classmethod
    def __tablename__(cls) -> str:
        return f"{cls.__head_table_name__}_version"

    @declared_attr.directive
    @classmethod
    def head_id(cls) -> Mapped[PyUUID]:
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{cls.__head_table_name__}.id", ondelete="RESTRICT"),
            nullable=False,
        )

    @declared_attr.directive
    @classmethod
    def rollback_of_version_id(cls) -> Mapped[PyUUID | None]:
        return mapped_column(
            PGUUID(as_uuid=True), ForeignKey(f"{cls.__tablename__}.id"), nullable=True
        )

    @classmethod
    def base_table_args(cls) -> tuple[Any, ...]:
        return (
            UniqueConstraint(
                "head_id", "version_number", name=f"ux_{cls.__tablename__}_head_version"
            ),
            CheckConstraint(
                f"status IN {_VERSION_STATUS_SQL}", name=f"ck_{cls.__tablename__}_status"
            ),
            CheckConstraint(
                "validity_until IS NULL OR validity_until > validity_from",
                name=f"ck_{cls.__tablename__}_validity",
            ),
        )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.base_table_args()
