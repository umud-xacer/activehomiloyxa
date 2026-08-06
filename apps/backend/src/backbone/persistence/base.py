"""Per-module SQLAlchemy declarative base + aggregate-root mixin (Physical DB Sec 13 "AI
Implementation Guidance"): "one MetaData per module with schema=\"<module>\" -- a shared
MetaData would invite cross-module joins."

Usage (in a module's own `infrastructure/models.py`, not here -- this module only provides the
factory):

    from backbone.persistence.base import make_module_base

    Base = make_module_base("catalog")

    class ListingRow(Base, AggregateMixin):
        __tablename__ = "listing"
        title: Mapped[str] = mapped_column(String(200))
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, Integer, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from backbone.persistence.uuid7 import uuid7

# Physical DB Sec 13: "indexes ix_<table>_<cols>, uniques ux_, checks ck_, FKs fk_<table>_<ref>".
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "ux_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def make_module_base(module_name: str) -> type[DeclarativeBase]:
    """One call per module, made once in that module's `infrastructure/models.py`. Returns a
    fresh `DeclarativeBase` bound to a `MetaData` scoped to that module's own PostgreSQL schema
    -- never shared across modules (that would invite the cross-schema joins DM-01 forbids)."""

    module_metadata = MetaData(schema=module_name, naming_convention=NAMING_CONVENTION)

    class ModuleBase(DeclarativeBase):
        # NOTE: must not be named the same as the enclosing local (`module_metadata`) -- a class
        # body does not close over an enclosing function's locals the way a nested function
        # does, so `metadata = metadata` here would NameError trying to resolve the RHS.
        metadata = module_metadata

    ModuleBase.__name__ = f"{module_name.title().replace('_', '')}Base"
    return ModuleBase


class AggregateMixin:
    """Columns every mutable aggregate-root table carries (Physical DB Sec 2 conventions, Sec
    13): a UUIDv7 primary key generated application-side (PD-01 -- no database-side PK default
    on business tables), audit timestamps, and an optimistic-locking version counter.

    Mix into a concrete `Base` subclass, not into `Base` itself: child entities (which have no
    repository of their own, Logical Sec 18.2) do not necessarily carry every one of these
    columns the same way, and applying it is a per-table decision made in each module's own
    `infrastructure/models.py`.
    """

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @declared_attr.directive
    @classmethod
    def __mapper_args__(cls) -> dict[str, object]:
        """`version_id_col = lock_version` (Physical DB Sec 13): SQLAlchemy raises
        `StaleDataError` on a lost update, which the application layer surfaces as the API's 409
        (AIR-15 "one aggregate = one transaction"; optimistic-locking floor under contention).

        `eager_defaults=True` (P-20 fix, a confirmed integration defect affecting every module
        that mixes in `AggregateMixin`): `created_at`/`updated_at`'s `server_default`/`onupdate`
        and the `version_id_col` bump are all server-computed values that SQLAlchemy must
        re-fetch after INSERT/UPDATE -- its default (lazy, on next synchronous attribute access)
        strategy requires the attribute access to happen inside an active greenlet context.
        Any later, plain attribute read on a repository's own already-returned domain object
        (e.g. `_order_to_domain(row)` reading `row.updated_at` right after `flush()`, with no
        surrounding `await`) raises `sqlalchemy.exc.MissingGreenlet` under the asyncio dialect --
        exactly the "pre-existing, repo-wide MissingGreenlet bug in save() across every module"
        multiple prior tasks' READMEs already flagged and left as out-of-scope. `eager_defaults`
        fetches these values via `RETURNING` as part of the same INSERT/UPDATE statement instead
        of deferring them, which is the fix SQLAlchemy's own asyncio documentation recommends for
        exactly this failure mode -- fixed once, here, for all eleven modules that mix in this
        class, rather than patched per-repository."""
        return {"version_id_col": cls.lock_version, "eager_defaults": True}
