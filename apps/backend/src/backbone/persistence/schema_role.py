"""Per-module PostgreSQL schema + role provisioning (Physical DB PD-06: "One PostgreSQL role
per module, granted USAGE + DML only on its own schema. Cross-module isolation (DEC-22) is
thereby enforced by the database itself, not only by CI linting."). Pure DDL generation -- no
connection, no execution -- so it is usable both from an Alembic migration (`op.execute(...)`
per statement) and from a bootstrap script run once against a fresh cluster.

Each module owns exactly one schema and one role scoped to it (SAD Sec 8 rule 5); this is the
generic convention every module task instantiates once for itself rather than hand-rolling.
"""

from __future__ import annotations

import re

_VALID_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidModuleNameError(ValueError):
    """Raised when a module name isn't a safe, lowercase SQL identifier -- refused outright
    rather than quoted/escaped, since a module name is always a fixed code-level constant
    (one of the 13 bounded contexts), never end-user input."""


def _validate(module_name: str) -> None:
    if not _VALID_IDENTIFIER.match(module_name):
        raise InvalidModuleNameError(
            f"{module_name!r} is not a valid schema/role identifier "
            "(must be lowercase, start with a letter, and contain only [a-z0-9_])"
        )


def schema_and_role_ddl(module_name: str, *, role_password_env_placeholder: str) -> list[str]:
    """DDL to provision `module_name`'s schema and its least-privilege role. The role's
    password is never embedded here -- `role_password_env_placeholder` is a literal marker
    (e.g. ``:role_password``) the caller substitutes via its own parameter-binding mechanism,
    so no credential ever appears in a migration file or this module's source (DevSecOps Sec 8:
    "no secret values appear in ... any repository").

    The placeholder is bound on a plain `SELECT set_config(...)` statement, not inlined into the
    `DO $$ ... $$` block that actually runs `CREATE ROLE`: PostgreSQL's extended query protocol
    (what asyncpg always uses) does not support bind parameters inside a `DO` block ("parameters
    are supported only in SELECT, INSERT, UPDATE, DELETE, MERGE and VALUES statements"). The `DO`
    block reads the value back via `current_setting()`, a session-local GUC set by the statement
    just before it -- the password is bound exactly once, never string-interpolated into SQL
    text. `CREATE ROLE ... PASSWORD` also only accepts a literal, not an arbitrary expression, so
    the block builds and runs the statement as dynamic SQL (`EXECUTE format(...)`, `%L` = a
    literal-safe, injection-safe substitution) rather than static DDL.
    """
    _validate(module_name)
    role = f"ah_{module_name}"
    schema = module_name
    # bandit B608 (manual sign-off, DevSecOps Sec 12): `role`/`schema` are f-string-interpolated
    # into DDL text below, which looks like the shape of a SQL-injection vector in isolation --
    # but both are derived from `module_name`, which `_validate()` above already restricted to
    # `_VALID_IDENTIFIER` (`^[a-z][a-z0-9_]*$`, refused outright otherwise) before either is
    # built. `module_name` is also never end-user input at any call site: it's always one of the
    # 13 fixed bounded-context names, a code-level constant supplied by a migration or bootstrap
    # script, never a request parameter. Safe by construction; the only actual bind parameter
    # here (the role password) already goes through `set_config`/`current_setting`, never
    # interpolated as text -- see this function's own docstring for why.
    return [
        f'CREATE SCHEMA IF NOT EXISTS "{schema}";',
        f"SELECT set_config('activehome.role_password', {role_password_env_placeholder}, false);",
        f"DO $$ "  # nosec B608 -- role/schema allowlist-validated above, see comment
        f"DECLARE pw text := current_setting('activehome.role_password'); "
        f"BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{role}') THEN "
        f"EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '{role}', pw); "
        f"END IF; END $$;",
        f'REVOKE ALL ON SCHEMA "{schema}" FROM PUBLIC;',
        f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}";',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{role}";',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}";',
        f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO "{role}";',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
        f'GRANT USAGE, SELECT ON SEQUENCES TO "{role}";',
    ]


def drop_schema_and_role_ddl(module_name: str) -> list[str]:
    """Reverses `schema_and_role_ddl` -- test/scratch teardown only (DELETE-a-whole-schema is
    never a production migration operation under expand/contract)."""
    _validate(module_name)
    role = f"ah_{module_name}"
    schema = module_name
    return [
        f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;',
        f'DROP ROLE IF EXISTS "{role}";',
    ]
