"""make_module_base + AggregateMixin (Physical DB Sec 13: per-module MetaData/schema, PK
default is application-side (PD-01), version_id_col optimistic locking)."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backbone.persistence import AggregateMixin, make_module_base


def _demo_model(module_name: str, table_name: str) -> type[DeclarativeBase]:
    base = make_module_base(module_name)

    class DemoRow(base, AggregateMixin):  # type: ignore[misc,valid-type]
        __tablename__ = table_name
        name: Mapped[str] = mapped_column(String(50))

    return DemoRow


def test_table_is_scoped_to_the_module_schema() -> None:
    model = _demo_model("catalog", "demo_a")
    assert model.__table__.schema == "catalog"


def test_two_modules_get_independent_metadata() -> None:
    catalog_base = make_module_base("catalog")
    billing_base = make_module_base("billing")
    assert catalog_base.metadata is not billing_base.metadata
    assert catalog_base.metadata.schema == "catalog"
    assert billing_base.metadata.schema == "billing"


def test_aggregate_mixin_columns_present() -> None:
    model = _demo_model("catalog", "demo_b")
    columns = {c.name for c in model.__table__.columns}
    assert {"id", "created_at", "updated_at", "lock_version", "name"} <= columns


def test_primary_key_default_is_application_side_not_a_server_default() -> None:
    """# enforces PD-01: "no database-side PK default on business tables"."""
    model = _demo_model("catalog", "demo_c")
    id_column = model.__table__.c.id
    assert id_column.default is not None
    assert id_column.server_default is None


def test_version_id_col_is_lock_version() -> None:
    """# enforces Physical DB Sec 13: "version_id_col = lock_version for optimistic locking"."""
    model = _demo_model("catalog", "demo_d")
    assert model.__mapper__.version_id_col is model.__table__.c.lock_version


def test_naming_convention_matches_physical_db_sec_13() -> None:
    base = make_module_base("catalog")
    convention = base.metadata.naming_convention
    assert convention["ix"] == "ix_%(table_name)s_%(column_0_N_name)s"
    assert convention["uq"] == "ux_%(table_name)s_%(column_0_N_name)s"
    assert convention["ck"] == "ck_%(table_name)s_%(constraint_name)s"
    assert convention["fk"] == "fk_%(table_name)s_%(referred_table_name)s"
