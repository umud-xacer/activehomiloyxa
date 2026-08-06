# backbone -- module charter

STATUS: implemented (Task P-03) -- persistence conventions, transactional outbox, idempotent
consumer ledger, migration framework + safety guard, immutability-guard trigger helper, error
envelope middleware, composition-root DI pattern (proof-of-wiring only, no real endpoint), and
structured JSON logging with secret redaction. No real business module (identity, catalog,
configuration, etc.) is implemented here or by this task.

## What this is, and why it exists here

`backbone` is not a bounded context (it owns no aggregate, publishes no domain event) and it is
not DDD value-object content (that is `shared_kernel`, DDD Sec 5.14, closed as of Task P-02). It
is the persistence/outbox/migration/error-handling/DI/logging plumbing that every one of the 13
modules' `infrastructure/` layers needs and would otherwise hand-roll thirteen times --
`SqlalchemyListingRepository`, `SqlalchemyOrderRepository`, etc. all sit on the same engine
factory, the same outbox writer/dispatcher shape, the same migration env, the same error
mapping.

It does not belong in `packages/shared`: Playbook Sec 2 restricts that package to the same
shared-kernel-sanctioned content (types, error envelope, logging), textually, not to "whatever
is cross-cutting" -- SQLAlchemy engines, Alembic environments, and FastAPI middleware are
infrastructure concerns, not DDD kernel content. It does not belong inside any one of the 13
modules either, since all 13 need it symmetrically and none of them may depend on another
module's `infrastructure/`. A new top-level package was the only placement consistent with the
module boundary rules -- confirmed via `AskUserQuestion` during Task P-03 rather than assumed.

Named `backbone`, not `platform` (Python's stdlib module of that name) -- a top-level package
literally named `platform` would shadow the stdlib module for every other import in the
interpreter, discovered the hard way on the first scratch import in this task.

## Public interface

Everything under `backbone/` is importable by any of the 13 modules' `infrastructure/` (and,
narrowly, `interfaces/` for the DI/error-middleware wiring in `main.py`) layers -- `backbone` has
no `interfaces/`/`application/`/`domain`/`infrastructure` split of its own because it is not a
bounded context. `tools/importlinter.cfg` enforces the boundary from both sides:

- `backbone` MAY import only `shared_kernel` (`backbone-imports-only-shared-kernel`) -- it never
  reaches into any of the 13 modules.
- Every module's `domain/` and `application/` layers MUST NOT import `backbone`
  (`backbone-confined-to-infrastructure-and-interfaces`) -- persistence/DI/logging machinery is
  an infrastructure concern; domain and application code stay ignorant of it (DIP).

## Contents

| Subpackage | Provides |
|---|---|
| `persistence/` | `uuid7()` (RFC 9562, application-side PK generation, PD-01); `make_module_base(module_name)` + `AggregateMixin` (per-module `DeclarativeBase`, optimistic locking via `lock_version`); `make_engine`/`make_session_factory`/`session_scope` (asyncpg engine, one DB transaction per unit of work); `schema_and_role_ddl`/`drop_schema_and_role_ddl` (PD-06 per-module schema + least-privilege role) |
| `outbox/` | `make_outbox_event_model(base)`; `OutboxWriter` (stages an event row in the same transaction as the state write -- DEC-09, never dual-write); `OutboxDispatcher` (`FOR UPDATE SKIP LOCKED` polling dispatcher, at-least-once delivery) |
| `idempotency/` | `make_processed_event_model(base)`; `idempotent_consume` (composite-PK `ON CONFLICT DO NOTHING` ledger -- turns at-least-once delivery into effectively-once application of effects) |
| `migrations/` | `guard_trigger_ddl`/`drop_guard_trigger_ddl` (PD-07 append-only/partial-mutable enforcement trigger); `env_support.run_migrations` (async Alembic env, `version_table_schema=<module>`, expand/contract discipline); `templates/` (per-module `alembic.ini`/`script.py.mako` scaffolding, used by `scripts/new-module-migrations.sh`) |
| `errors/` | `ExceptionMapper`/`simple_problem_builder` (maps exceptions to `contracts.errors.Problem`); `TraceIdMiddleware` + `install_error_handlers` (FastAPI wiring) |
| `logging/` | `configure_logging`, `JsonFormatter`, `RedactingFilter` (Playbook Sec 6 / Security Sec 12: never log secrets, OTP codes, session tokens, passwords) |
| `di/example.py` | Composition-root DI pattern demonstrated via a clearly-marked dummy `HealthCheckPort`/use case/router -- proof of wiring only, never mounted on the real app |

## Allowed static dependencies

MAY statically import: `shared_kernel` only.

MUST NOT import: any of the 13 bounded-context modules, in either direction from their
`domain`/`application` layers.

## Events

Publishes none, owns none. `outbox`/`idempotency` are the mechanism other modules use to
publish/consume their own domain events reliably -- the event *types* live in
`contracts/events/*` and each module's own `domain/events.py`, never here.

## Tests

`apps/backend/tests/backbone/` -- unit tests for every subpackage, plus
`apps/backend/tests/backbone/integration/` (`pytest.mark.integration`, requires real
PostgreSQL/Redis) proving: atomic state+outbox commit with rollback-on-failure, dispatcher
redelivery idempotency, migrations applying cleanly to a fresh database with the version table
inside the module's own schema, the immutability-guard trigger rejecting disallowed
UPDATE/DELETE against live PostgreSQL, and the schema/role convention producing no cross-schema
grants.
