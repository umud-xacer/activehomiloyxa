"""guard_trigger_ddl / drop_guard_trigger_ddl (Physical DB PD-07). DDL generation only --
apps/backend/tests/backbone/integration/test_guard_trigger_live.py proves the generated SQL
actually enforces immutability against real PostgreSQL."""

from __future__ import annotations

import pytest

from backbone.migrations import InvalidIdentifierError, drop_guard_trigger_ddl, guard_trigger_ddl


def test_trigger_name_matches_naming_convention() -> None:
    """# enforces Physical DB Sec 13: "guard triggers trg_<table>_immutability"."""
    statements = guard_trigger_ddl("analytics", "audit_entry")
    assert any("trg_audit_entry_immutability" in s for s in statements)


def test_append_only_rejects_all_updates() -> None:
    statements = guard_trigger_ddl("analytics", "audit_entry")
    function_sql = statements[0]
    assert "no UPDATE permitted" in function_sql


def test_append_only_rejects_deletes() -> None:
    statements = guard_trigger_ddl("analytics", "audit_entry")
    assert "rows are never deleted" in statements[0]


def test_partial_mutable_names_the_allowed_columns() -> None:
    statements = guard_trigger_ddl(
        "notifications", "notification", mutable_columns=("delivered_at", "read_at")
    )
    assert "delivered_at" in statements[0]
    assert "read_at" in statements[0]


def test_trigger_fires_before_update_or_delete() -> None:
    statements = guard_trigger_ddl("analytics", "audit_entry")
    trigger_sql = statements[1]
    assert "BEFORE UPDATE OR DELETE" in trigger_sql
    assert '"analytics"."audit_entry"' in trigger_sql


@pytest.mark.parametrize("bad", ["Analytics", "audit-entry", "1x", "a b"])
def test_rejects_invalid_identifiers(bad: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        guard_trigger_ddl("analytics", bad)


def test_drop_ddl_removes_trigger_and_function() -> None:
    statements = drop_guard_trigger_ddl("analytics", "audit_entry")
    joined = " ".join(statements)
    assert "DROP TRIGGER IF EXISTS trg_audit_entry_immutability" in joined
    assert "DROP FUNCTION IF EXISTS analytics.fn_audit_entry_immutability" in joined
