"""The immutability-guard trigger convention (Physical DB PD-07: "Immutability of published
configuration versions, audit entries, metric events, transitions, and terminal financial
records is enforced by row-level guard triggers (reject UPDATE/DELETE), in addition to
application discipline."; naming convention Sec 13: "guard triggers trg_<table>_immutability").

Pure DDL generation, parameterised by table and which columns (if any) remain mutable --
`op.execute(...)` each statement from a module's own Alembic migration. Covers the two
column-whitelist shapes the Physical DB document actually uses:

- Pure append-only (`mutable_columns=()`): analytics.audit_entry, analytics.metric_event,
  catalog.listing_transition -- "Guard trigger: no UPDATE, no DELETE, no exceptions."
- A narrow mutable subset (e.g. `mutable_columns=("delivered_at", "read_at")`):
  notifications.notification -- "Guard trigger permits UPDATE of delivered_at/read_at only."

Not covered: guards whose allowed UPDATE also depends on the row's *current value* (e.g.
configuration's head/version "reject any UPDATE to a row whose status = PUBLISHED except the
transition to DEPRECATED/ARCHIVED") -- that is a value-transition rule specific to the Head +
Version pattern (Physical DB Sec 2.4), explicitly out of scope for this task per the P-03 brief,
and is built when the configuration module itself is implemented.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_VALID_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidIdentifierError(ValueError):
    """Refused outright rather than quoted/escaped -- schema/table/column names are always
    fixed code-level constants, never end-user input."""


def _validate(*names: str) -> None:
    for name in names:
        if not _VALID_IDENTIFIER.match(name):
            raise InvalidIdentifierError(
                f"{name!r} is not a valid identifier (lowercase, starts with a letter, [a-z0-9_] only)"
            )


def guard_trigger_ddl(
    schema: str,
    table: str,
    *,
    mutable_columns: Sequence[str] = (),
) -> list[str]:
    """DELETE is always rejected. UPDATE is rejected unless every changed column is in
    `mutable_columns` (empty = pure append-only, no column may ever change)."""
    _validate(schema, table, *mutable_columns)

    function_name = f"{schema}.fn_{table}_immutability"
    trigger_name = f"trg_{table}_immutability"

    if mutable_columns:
        # This pure-DDL helper deliberately doesn't need the table's full column list -- it only
        # cares about the allowed set. PostgreSQL has no "which columns changed" primitive
        # without enumerating every column, so instead: strip the allowed keys from NEW and OLD
        # (as jsonb) and compare what's left. Any difference there means a disallowed column
        # changed.
        allowed_keys_array = ", ".join(f"'{c}'" for c in mutable_columns)
        update_guard = f"""
    IF (to_jsonb(NEW) - ARRAY[{allowed_keys_array}]::text[]) IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY[{allowed_keys_array}]::text[]) THEN
      RAISE EXCEPTION 'immutability guard: % only permits updates to {", ".join(mutable_columns)}', TG_TABLE_NAME;
    END IF;"""
    else:
        update_guard = """
    RAISE EXCEPTION 'immutability guard: % is append-only, no UPDATE permitted', TG_TABLE_NAME;"""

    function_sql = f"""
CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'immutability guard: % rows are never deleted', TG_TABLE_NAME;
  ELSIF TG_OP = 'UPDATE' THEN
    {update_guard}
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
""".strip()

    trigger_sql = f"""
CREATE TRIGGER {trigger_name}
  BEFORE UPDATE OR DELETE ON "{schema}"."{table}"
  FOR EACH ROW EXECUTE FUNCTION {function_name}();
""".strip()

    return [function_sql, trigger_sql]


def drop_guard_trigger_ddl(schema: str, table: str) -> list[str]:
    _validate(schema, table)
    trigger_name = f"trg_{table}_immutability"
    function_name = f"{schema}.fn_{table}_immutability"
    return [
        f'DROP TRIGGER IF EXISTS {trigger_name} ON "{schema}"."{table}";',
        f"DROP FUNCTION IF EXISTS {function_name}();",
    ]
