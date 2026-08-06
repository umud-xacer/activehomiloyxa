"""The value-conditional immutability guard for `configuration.<entity>_version` tables
(Physical DB Sec 2.4: "a guard trigger rejects any UPDATE to a row whose status = PUBLISHED
except the single status transition to DEPRECATED/ARCHIVED; DELETE is always rejected. Drafts
are mutable version rows attached to the head."). `backbone.migrations.guard_trigger_ddl`
explicitly does not cover this shape (its own docstring: "guards whose allowed UPDATE also
depends on the row's *current value* ... is built when the configuration module itself is
implemented") -- this is that implementation, kept in `configuration/infrastructure/` since it
is specific to this module's Head+Version pattern, not a generalisable backbone primitive.
"""

from __future__ import annotations

import re

_VALID_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidIdentifierError(ValueError):
    pass


def _validate(*names: str) -> None:
    for name in names:
        if not _VALID_IDENTIFIER.match(name):
            raise InvalidIdentifierError(f"{name!r} is not a valid identifier")


def version_guard_trigger_ddl(schema: str, table: str) -> list[str]:
    """DELETE is always rejected on `<table>`. UPDATE is unrestricted while `status <>
    'PUBLISHED'` (drafts/validation/approval rows are freely editable); once `status =
    'PUBLISHED'`, the only permitted UPDATE is `status` itself, and only to DEPRECATED or
    ARCHIVED -- everything else about a published version row is frozen forever."""
    _validate(schema, table)

    function_name = f"{schema}.fn_{table}_immutability"
    trigger_name = f"trg_{table}_immutability"

    function_sql = f"""
CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'immutability guard: % rows are never deleted', TG_TABLE_NAME;
  ELSIF TG_OP = 'UPDATE' THEN
    IF OLD.status = 'PUBLISHED' THEN
      IF NEW.status NOT IN ('DEPRECATED', 'ARCHIVED') THEN
        RAISE EXCEPTION
          'immutability guard: % published rows may only transition to DEPRECATED/ARCHIVED',
          TG_TABLE_NAME;
      END IF;
      IF (to_jsonb(NEW) - ARRAY['status']::text[]) IS DISTINCT FROM
         (to_jsonb(OLD) - ARRAY['status']::text[]) THEN
        RAISE EXCEPTION
          'immutability guard: % published rows are immutable except the status column',
          TG_TABLE_NAME;
      END IF;
    END IF;
    RETURN NEW;
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


def drop_version_guard_trigger_ddl(schema: str, table: str) -> list[str]:
    _validate(schema, table)
    trigger_name = f"trg_{table}_immutability"
    function_name = f"{schema}.fn_{table}_immutability"
    return [
        f'DROP TRIGGER IF EXISTS {trigger_name} ON "{schema}"."{table}";',
        f"DROP FUNCTION IF EXISTS {function_name}();",
    ]
