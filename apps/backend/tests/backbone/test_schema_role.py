"""schema_and_role_ddl / drop_schema_and_role_ddl (Physical DB PD-06). DDL generation only --
apps/backend/tests/backbone/integration/test_schema_role_convention.py proves it actually works
against real PostgreSQL."""

from __future__ import annotations

import pytest

from backbone.persistence import (
    InvalidModuleNameError,
    drop_schema_and_role_ddl,
    schema_and_role_ddl,
)


def test_generates_create_schema_and_role() -> None:
    statements = schema_and_role_ddl("catalog", role_password_env_placeholder=":pw")
    joined = " ".join(statements)
    assert 'CREATE SCHEMA IF NOT EXISTS "catalog"' in joined
    assert '"ah_catalog"' in joined


def test_grants_are_scoped_to_the_module_schema_only() -> None:
    statements = schema_and_role_ddl("catalog", role_password_env_placeholder=":pw")
    joined = " ".join(statements)
    assert 'GRANT USAGE ON SCHEMA "catalog"' in joined
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "catalog"' in joined
    # PD-06: "granted USAGE + DML only on its own schema" -- no other schema name appears.
    assert "billing" not in joined


def test_public_is_revoked() -> None:
    statements = schema_and_role_ddl("catalog", role_password_env_placeholder=":pw")
    assert any("REVOKE ALL ON SCHEMA" in s and "FROM PUBLIC" in s for s in statements)


def test_password_placeholder_is_never_a_literal_secret() -> None:
    statements = schema_and_role_ddl("catalog", role_password_env_placeholder=":role_password")
    joined = " ".join(statements)
    assert ":role_password" in joined
    # nothing that looks like an actual embedded credential
    assert "PASSWORD '" not in joined


@pytest.mark.parametrize("bad_name", ["Catalog", "catalog-x", "1catalog", "cat alog", "cat;alog"])
def test_rejects_invalid_module_names(bad_name: str) -> None:
    with pytest.raises(InvalidModuleNameError):
        schema_and_role_ddl(bad_name, role_password_env_placeholder=":pw")


def test_drop_ddl_reverses_provisioning() -> None:
    statements = drop_schema_and_role_ddl("catalog")
    joined = " ".join(statements)
    assert 'DROP SCHEMA IF EXISTS "catalog" CASCADE' in joined
    assert 'DROP ROLE IF EXISTS "ah_catalog"' in joined
