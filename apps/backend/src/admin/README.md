# admin -- module charter

STATUS: implemented (Task P-16) -- the last of the 13 bounded-context modules. Composition-only:
admin owns exactly one datum (`OperatorSessionContext`) and exactly one HTTP operation
(`getAdminDashboard`). This README is the module's public charter -- read it before working in
this module (Playbook Sec 13).

## Bounded context

- **Module**: `admin` (BC-12, thin composition context per SAD Sec 7.2)
- **Responsibilities**: the one operational KPI dashboard that maps to no single owning
  aggregate. Nothing else -- admin owns no marketplace aggregate, re-implements no other
  module's business logic, and makes no authorization decision another module doesn't already
  make for itself.

## The corrected scope: what "Administration"-tagged does NOT mean

`contracts/openapi.yaml` tags 14 operations `Administration`. Before writing any code, this task
enumerated them and checked, per operation, which module already serves it:

| operationId | Path | Owning router | Status before this task |
|---|---|---|---|
| `getAdminDashboard` | `GET /admin/dashboard` | **admin** (this module) | not yet mounted anywhere |
| `listModerationQueue` / `getModerationCase` / `applyModerationAction` | `/admin/moderation-queue...` | `moderation.interfaces.routers.admin_moderation_router` | already implemented and mounted (P-12) |
| `listVerificationQueue` / `decideVerification` | `/admin/verification-queue...` | `profiles.interfaces.routers.admin_profiles_router` | already implemented and mounted (P-11) |
| `adminListInvoices` / `confirmInvoicePayment` | `/admin/billing/invoices...` | `billing.interfaces.routers.admin_billing_router` | already implemented and mounted (P-09) |
| `queryAuditLog` / `getAdminReports` | `/admin/audit-log`, `/admin/reports` | `analytics.interfaces.routers.analytics_router` | already implemented and mounted (P-15) |
| `adminListUsers` / `adminChangeUserStatus` | `/admin/users...` | `identity.interfaces.routers.admin_users_router` | identity's own P-05 README explicitly deferred these to "a future admin-module task" -- **this task mounted them, on identity's own router** |
| `assignRole` / `revokeRole` | `/admin/users/{userId}/roles...` | `identity.interfaces.routers.admin_users_router` | did not exist in the frozen contract at all -- **ADR-0006**, added and mounted this task |

Only `getAdminDashboard` maps to no single owning aggregate (`contracts/README.md`'s own P-01 tag
routing rule: *"an OpenAPI operation tagged Administration is NOT necessarily admin's own -- it's
routed to whichever module owns the underlying aggregate"*). Every other Administration-tagged
operation is, and remains, implemented on its owning module's own router. `admin/` therefore
declares no wrapper/bridge use case for moderation/verification/invoices/audit-log/reports --
building one would be a second, unreachable implementation of a capability the owning module
already exposes end-to-end (Absolute Architecture Rule 4), dead code with no router to call it.

This correction happened mid-task: an earlier pass built full `AdminModerationUseCases`/
`AdminVerificationUseCases`/`AdminBillingUseCases`/`AdminAuditReportUseCases`/`AdminUserUseCases`
wrapper classes and matching `composition_root.py` bridges for all of the above, before directly
inspecting each owning module's own router confirmed they already serve every one of those
operations for real. All of that was removed; only what genuinely required new code survived:
`getAdminDashboard` (this module) and the four identity user/role operations (ADR-0006, on
identity's own router).

## Owned aggregates / entities (DDD Sec 5.12)

- **`OperatorSessionContext`** (`domain/operator_session.py`) -- the operator's own work-session
  state: `id`, `operator_user_id` (xref identity, `UNIQUE`), opaque `context` (JSONB -- queue
  positions/filters the operator's own UI reads and writes back verbatim; admin has no business
  reason to interpret it), `updated_at`. One row per operator, upsert semantics, no invariant
  beyond "one context per operator." No OpenAPI operation reads or writes it in v1 -- it exists as
  a real, tested capability for a future frontend session to call in-process, not manufactured
  domain logic to fill out this layer. `test_composition_only.py` asserts this is the ONLY entity
  `admin/domain` will ever define.

## `getAdminDashboard`: the one thing admin genuinely composes

`DashboardSummary`'s five fields (`activeListings`, `pendingModeration`, `pendingVerification`,
`pendingInvoices`, `newUsers7d`) are none of them cheaply computable: no owning module's list
operation ever populates `CursorPage.page.total` (verified against every one of those modules'
own repositories -- none run a `COUNT(*)` alongside their cursor query), and `activeListings`
needs `catalog` (BC-03) data, which admin is not permitted to import at all (outside its allowed
BC-01/02/04/08/09/11/13 set, `tools/importlinter.cfg`'s `cross-module-admin`). Surfaced to the
repository owner; direction: return an honest `null` for every field (mirroring the established
precedent -- `catalog.getListingStatistics`'s own null analytics-owned fields, `analytics`'s own
`USER_GROWTH` "unavailable" report), while still making a real, `limit=1`, result-unused call
through each of the four reachable owning modules' own read ports (moderation/verification/
invoices/users) to prove the composition and permission-check wiring is genuinely live, not a
dead code path. `application/dashboard_use_cases.py` declares this in full, including why.

## The narrow-Protocol-plus-composition-bridge pattern (why `AdminDashboardUseCases` doesn't import any other module)

Every owning module's real application-layer use case has a DIFFERENT method name than its own
`interfaces/ports.py` Protocol would suggest (e.g. `moderation.application.ModerationUseCases.
list_queue`, not `list_moderation_queue`) -- confirmed by direct inspection across moderation/
profiles/billing/identity. No single object anywhere in the codebase structurally satisfies a
full owning-module Protocol end-to-end; only each module's OWN router performs that translation.
`AdminDashboardUseCases` therefore depends on four tiny, LOCAL Protocols declared next to it in
`application/dashboard_use_cases.py` (`_ModerationQueueProbe`/`_VerificationQueueProbe`/
`_InvoiceQueueProbe`/`_UserQueueProbe`, one method each, HTTP-shaped names) -- `admin/` itself
never imports `moderation`/`profiles`/`billing`/`identity` at all. `composition_root.py`'s
`_ModerationQueueProbe`/`_VerificationQueueProbe`/`_InvoiceQueueProbe`/`_UserQueueProbe` classes
(the only place allowed to see every module's internals at once) construct the owning module's
REAL use case against a short-lived session and call its real, differently-named method.

## ADR-0006: `assignRole`/`revokeRole`

`identity.application.admin_use_cases.AdminIdentityUseCases.assign_role`/`revoke_role` existed
since P-05 but had no OpenAPI operation. Per the P-01 tag-routing precedent, adding one is an
architecture decision (a new public operation), not a workaround -- drafted and user-authorized
as `docs/adr/0006-admin-role-assignment-endpoints.md`: `POST /admin/users/{userId}/roles` and
`DELETE /admin/users/{userId}/roles/{roleDefinitionHeadId}`, both gated by the already-existing
`identity:role:assign` permission key, implemented on **identity's own router** -- never admin's.

## Dependencies (SAD Sec 8.1; `tools/importlinter.cfg`'s `cross-module-admin`)

- **Allowed**: `shared_kernel` (unconditionally); the `interfaces/` package only of `identity`,
  `profiles`, `configuration`, `billing`, `ads`, `moderation`, `analytics` -- and even then, only
  `composition_root.py` (never `admin/` itself) actually imports them, for the dashboard's four
  probes.
- **Forbidden**: `catalog`, `search`, `media`, `messaging`, `notifications` entirely; every other
  allowed module's `domain`/`application`/`infrastructure` layer.
- **Nothing imports `admin`** -- it is a terminal composition context, proven both by
  `tools/importlinter.cfg`'s `sink-modules-have-no-inbound-imports` contract and by
  `test_composition_only.py`'s own repo-wide static grep.

## Permissions

- `admin:dashboard:read` -- the ONE permission key admin owns, gating `getAdminDashboard` only.
- Every other composed capability reuses the OWNING module's own existing permission key
  (`identity:account:manage_status`, `identity:role:assign`, `moderation:case:review`, etc.) --
  admin never invents a second, laxer check for a capability another module already gates.

## Migrations

Exactly one table: `admin.operator_session_context` (Physical DB Sec 2.12) --
`infrastructure/migrations/versions/5f292652bd4c_admin_create_operator_session_context.py`,
verified via `tools/check_migration_safety.py` (QG-09).

## Known gaps (not release-blocking, explicitly flagged)

- No OpenAPI operation reads or writes `OperatorSessionContext` in v1 -- built and tested as a
  real capability ahead of the frontend session that will call it, per this module's own charter.
- The dashboard's `di.py` placeholder `NotImplementedError` bodies are never exercised by a
  passing test (by construction -- they only fire if the composition root failed to override
  them), matching every other module's identical `interfaces/di.py` pattern.

## Coverage / quality gates

`apps/backend/tests/admin`: domain/application/infrastructure 100%, module overall 99% (the 2
uncovered lines are the never-exercised `di.py` `NotImplementedError` placeholder bodies, see
above). mypy --strict and ruff clean on every file this task touched. `cross-module-admin`,
`layers-admin`, `no-infra-inbound-admin`, and `sink-modules-have-no-inbound-imports` all KEPT.

## Layout

```
admin/
|-- interfaces/       # PUBLIC surface: admin_router (getAdminDashboard only), auth, di, dto, ports
|-- application/      # AdminDashboardUseCases, OperatorSessionUseCases, ports
|-- domain/           # OperatorSessionContext -- the only entity this module will ever define
|-- infrastructure/   # SqlalchemyOperatorSessionRepository, Alembic migration
`-- README.md         # this file
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
