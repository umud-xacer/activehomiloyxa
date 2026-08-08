# identity -- module charter

STATUS (Task P-05): fully implemented across all four layers -- accounts, phone-OTP/email/Google
authentication, server-side sessions, the multi-profile acting-context, configurable
roles/permissions consumed from `configuration`, and the default-deny `AuthorizationService`.
This README is the module's public charter -- read it before working in this module (Playbook
Sec 13). See `TRACEABILITY.md` for the requirement -> code -> test matrix.

## Bounded context

- **Module**: `identity` (BC-01, Generic domain per DDD/SAD classification)
- **Responsibilities**: Accounts, phone-OTP/email/Google auth, sessions, multi-profile acting-context, authorization enforcement (default-deny, per-acting-profile scoped).

## Owned aggregates / entities (DDD Sec 5.1)

- **`UserAccount` [P]** -- registration (phone/email/Google), lifecycle (Active <-> Suspended -> Closed, closure = anonymise + retain, never hard-delete), privacy/notification preferences, owned business-profile ids. Owns two entities inside its own aggregate boundary (one repository, one unit of work):
  - **`AuthenticationMethod`** -- one per channel (`PHONE_OTP`/`EMAIL`/`GOOGLE`).
  - **`RoleAssignment` [C-ref]** -- DDD Sec 5.1 places this *inside* `UserAccount`, not as its own aggregate root (a deliberate deviation from an earlier looser reading of the P-05 prompt's wording -- the authoritative Domain Model document wins per CLAUDE.md). Pins the identity + the exact published `RoleDefinition` head/version at assignment time (Config Framework Sec 7.2); reassignment is required to pick up a newer published version.
- **`Session` [P]** -- server-side only, Redis-backed (Security Sec 3.2). No JWT, no refresh token anywhere in this module (SDR-01) -- the opaque token is hashed at rest, and the raw value never leaves the composition root / this module's own request handling.
- **`OtpChallenge` [P]** -- single-use, expiring, throttled (NFR-SEC-004).
- **`AuthorizationService` [P]** (domain policy, not a persisted aggregate) -- the four-gate default-deny evaluator (Security Sec 4.2). This is the single Critical-risk piece named in the Baseline; see "AuthorizationService public contract" below.

## AuthorizationService public contract

Exposed via `identity.interfaces.ports.AuthorizationPort`, backed at the composition root by
`identity.infrastructure.public_port_adapters.AuthorizationPortAdapter`:

- `authorize(*, session_token: str, required_permission: str, owner_account_id: UserId | None = None, owner_profile_id: BusinessProfileId | None = None) -> UserId` -- the full four-gate check (authenticated, acting context resolved, permission held [default-deny, I-11], ownership/scope matches [I-10]). Raises on denial; returns the resolved account id on success.
- `get_effective_permissions(*, session_token: str) -> frozenset[str]` -- "reflect-permissions": the acting context's flattened permission set, for capability-based UI.

Every parameter/return type is a `shared_kernel` type or a primitive -- `identity.domain` types
never cross this boundary (AIR-02). Callers pass the **raw** session token (from the cookie/
header they hold); hashing happens entirely inside identity's infrastructure, so the pepper never
leaves this module.

`identity.interfaces.ports.ContactPolicyPort.get_phone_reveal_mode(account_id) -> Literal["ALWAYS","ON_REQUEST","NEVER"]`
is the second public port (FR-USER-003/BRULE-13), for messaging's privacy-gated phone reveal --
fails closed (`"NEVER"`) for an unknown account.

## Events published (DDD Sec 6 -- exactly these three, `contracts/events/identity.py`)

- `UserRegistered` -- any registration method.
- `AccountSuspended` -- operator suspension (`AdminIdentityUseCases.change_user_status`).
- `AccountClosed` -- user-initiated closure (`AccountUseCases.close_account`).

## Events consumed (P-20 fix -- identity's first-ever inbound event consumer)

`infrastructure/event_projection.py::handle_profiles_event` reacts to `profiles.
BusinessProfileCreated` by calling `AccountUseCases.link_owned_profile` (idempotent --
`UserAccount.link_owned_profile`), keeping `owned_profile_ids` in sync so `switchActingProfile`
(FR-USER-002) can legitimately recognise a profile the instant it's created. Confirmed integration
defect found while building P-20's E2E critical-journey suite: before this fix, NOTHING ever
appended to `owned_profile_ids` after profile creation, so a real user could never switch to a
business profile they just created -- blocking every acting-profile-gated operation downstream
(e.g. `billing.createOrder`). Wired as a fourth route on `composition_root.
make_profiles_notification_projection_handler` -- reacting to an already-published event is not
a contract change, the same pattern this task used repeatedly for other modules. Needed its own
`processed_event` idempotency ledger (a new, purely additive migration, `f1a2b3c4d5e6`) since
this module never consumed an event before. Proven by `tests/
integration/test_profiles_creation_links_identity_owned_profile.py` (including redelivery
idempotency) and by the E2E suite itself.

## Public interface (`interfaces/`)

`AuthenticationPort`, `AuthorizationPort`, `ContactPolicyPort`, `ActingIdentityQueryPort`
(acting-identity queries). The `interfaces/` package is this module's *only* importable surface
(AIR-02). Nothing in `application/`, `domain/`, or `infrastructure/` may be imported by another
module, ever.

## Routers (`interfaces/routers.py`) -- exactly the 15 Authentication + Users operations

`requestOtp`, `verifyOtp`, `registerEmail`, `loginEmail`, `loginGoogle`, `logout`,
`startRecovery`, `getMe`, `updateMe`, `changePassword`, `updatePreferences`, `closeAccount`,
`listSessions`, `revokeSession`, `switchActingProfile`. No more, no less (QG-06 contract
conformance).

`adminListUsers`/`adminChangeUserStatus`/`assignRole`/`revokeRole` are tagged `Administration` in
`contracts/openapi.yaml`, not `Authentication`/`Users` -- mounted on a separate router
(`admin_users_router`) in this same file as of Task P-16 (`assignRole`/`revokeRole` new via
ADR-0006), gated by `identity:account:manage_status`/`identity:role:assign` respectively. Per
`contracts/README.md`'s own P-01 tag-routing rule, an `Administration`-tagged operation belongs
to the module owning the underlying aggregate -- `RoleAssignment` is an entity inside identity's
own `UserAccount` (DDD Sec 5.1) -- so this stays here rather than moving to `admin`'s own router.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: **shared_kernel, configuration** (its `interfaces/` package only, in every
layer including `identity.infrastructure`).

MUST NOT import: every other module's internals -- only their `interfaces/` package, and only
where this table grants it (none here).

Cross-module reads: `identity.infrastructure.configuration_adapter` reads published
`role-definition`/`platform-settings` snapshots from `configuration` via a narrow `_ConfigReader`
Protocol (two of `ConfigurationPort`'s fifteen methods -- DIP: depend on the shape you use). The
concrete bridge from `configuration`'s own `ConfigurationUseCases` to that Protocol is built at
`apps/backend/src/composition_root.py`, the one place allowed to see both modules' internals.

## Configuration consumed (DEC-21: never hardcode a configurable value)

- `platform-settings-global.otp.expiry_minutes` -- `OtpChallenge.issue`'s expiry.
- `platform-settings-global.session.expiry_hours` -- `SessionExpiryPolicy`.
- `platform-settings-global.login_lockout.max_attempts` / `.login_lockout.block_minutes` --
  `LoginLockoutPolicy` (Security Sec 3.1 brute-force protection on `loginEmail`). Unlike OTP
  throttle just below, these ARE configuration-owned: the feature's own requirement explicitly
  calls for the lockout duration to be admin-tunable without a redeploy. Defaults (4 attempts /
  15 minutes) live in `configuration.infrastructure.seed`'s `_seed_platform_settings` (fresh DB)
  and `_backfill_platform_settings_defaults` (already-seeded DB, additive-only -- never overwrites
  an admin's own edit). `IdentityPlatformSettings`' reader falls back to the same two numbers if
  a published `platform-settings-global` version predates this task's seed backfill.
- Any published `role-definition` -- `RoleAssignment` pins its head+version; `AuthorizationService`
  evaluates the already-flattened `permission_keys` as-is (Config Framework Sec 7.2: identity
  never re-flattens or walks a hierarchy itself).

OTP throttle thresholds (`identity.domain.policies`: 3 requests per 15-minute window per phone
and, independently, per IP; 5 verify attempts before lockout) are **implementation-chosen
constants**, not configuration-owned -- no document gives literal numbers (only the qualitative
NFR-SEC-004 language), and `configuration`'s `SETTINGS_SCHEMA` whitelist had no throttle-specific
key until the login-lockout task above added one (scoped to `login_lockout.*` only -- OTP's own
thresholds were deliberately left as they were, not retrofitted onto the same mechanism, since
nothing in that task asked for OTP throttle to become admin-tunable too). Session/OTP-code
hashing peppers reuse the single `SESSION_SIGNING_KEY` environment variable (already declared in
`deployment/env/.env.*.example` under "Session auth"), domain-separated by a fixed HMAC context
prefix per use, rather than inventing new secret env vars for the same underlying key material.

Login-lockout counters themselves (the failure counts, not the thresholds) are Redis-backed,
same as sessions -- `identity.infrastructure.login_attempt_tracker.RedisLoginAttemptTracker`,
keyed `identity:login_lockout:{ip|account}:{identifier}`, one bare `INCR`-managed integer per
key whose own TTL doubles as both the failure-counting window and, once the threshold is
crossed, the remaining lockout duration (see the adapter's and `LoginLockoutPolicy`'s docstrings
for why one number serves both). Two independent scopes -- IP and (lowercased) email -- are
checked and recorded on every `loginEmail` call so that neither a single attacker sweeping many
accounts from one IP nor one attacker rotating IPs against one account escapes both nets, while
neither scope's lockout collaterally blocks traffic outside it (e.g. other legitimate users
behind the same NAT/office IP as an attacker targeting one victim account).

## Permission keys (this module's contribution to `configuration.domain.whitelist.PERMISSION_KEYS`)

`identity:account:manage_status` (suspend/reactivate), `identity:role:assign` (assign/revoke
role) -- added to the shared catalogue per that file's own comment inviting extension ("Other
modules ... extend this same catalogue with their own keys in their own tasks"). Consulted via
the exact same default-deny `AuthorizationService` mechanism as every other module's, once a
future admin-module task mounts the HTTP surface that actually gates on them.

## Migrations

`infrastructure/migrations/versions/3aec1ec32ea3_...py` creates `identity.user_account`,
`identity.authentication_method`, `identity.role_assignment`, `identity.otp_challenge`,
`identity.outbox_event` -- partial unique indexes on `user_account.phone`/`.email`
(`WHERE ... IS NOT NULL`, so anonymised/closed accounts with `NULL` never collide). Hand-written,
not `alembic revision --autogenerate` (see the migration file's own docstring for why: identity
and `configuration` share one dev database, and autogenerate with `include_schemas=True` diffs
against every schema it can see). Verified with `alembic upgrade head` / `alembic downgrade base`
against a real PostgreSQL instance; kept in sync with `infrastructure/persistence/models.py` by
`apps/backend/tests/identity/test_models.py`'s static parity check.

## Known gaps (flagged, not silently worked around)

1. **Email confirmation**: the Security Architecture doc describes a confirmation-link control
   ("a confirmation link activates the account"), and `registerEmail`'s own description says
   "Creates an account pending email confirmation" -- but `contracts/openapi.yaml` has no
   operation to consume a confirmation token, and the frozen `AccountStatus` enum has no `PENDING`
   value. Resolved (with explicit sign-off) as: the account is `ACTIVE` immediately;
   `AuthenticationMethod.verified_at` stays `None` for `EMAIL` (recorded for audit/forward
   compatibility) and a confirmation email is sent, but nothing in this task's scope can ever set
   `verified_at` afterward. A future task should either add a `confirmEmail` operation via ADR, or
   formally descope confirmation-gating for v1.
2. **Email-based account recovery**: `startRecovery` with a phone completes for real (it reuses
   the existing `requestOtp`/`verifyOtp(purpose=RECOVERY)` pair). `startRecovery` with an email has
   no completion endpoint either (no `resetPassword`/`completeRecovery` operation exists) -- a
   best-effort, enumeration-safe notice is sent, with no token/link, and no way to actually regain
   access via that path today. Same class of gap as (1), same recommended fix.
3. **Idempotency-Key**: `verifyOtp`/`registerEmail` accept the header per the contract's
   parameter, but no request-level dedup store is implemented -- out of this task's explicit
   validation checklist, and lower stakes than the two gaps above (a robustness nicety, not an
   invariant).
4. **`configuration.interfaces.auth.get_acting_admin`**: that module's own docstring says "a later
   task must replace `get_acting_admin` with a real session-cookie-backed dependency ... WITHOUT
   changing any router signature above it" -- `AuthorizationPort` now exists and is exactly what
   that replacement would call, but wiring it in was **not** done in this task: `configuration` is
   architecturally a leaf module (imports nothing but `shared_kernel`, `tools/importlinter.cfg`'s
   `configuration-leaf-free` contract), so the replacement must be a `configuration.interfaces`-
   declared Protocol overridden at the composition root (the same `Depends(...)`-stub pattern
   every other DI point already uses) -- not a direct `configuration -> identity` import. Doing
   this also means rewriting `configuration`'s existing header-based test fixtures
   (`test_api.py`'s `_auth_headers` helper) across its whole test suite, a footprint beyond this
   task's own deliverable boundary. Left as a small, well-specified, ready-to-execute follow-up.
5. **Contract drift outside this module's own routes**: fixing `tools/check_contract_drift.py`
   for FastAPI 0.139's lazy `_IncludedRouter` wrapping (a pre-existing bug that made QG-06
   silently report zero registered routes for every module, not just this one) surfaced that
   `configuration`'s own already-shipped routers use snake_case path parameters
   (`/admin/config/{entity_type}`) where `contracts/openapi.yaml` specifies camelCase
   (`{entityType}`). Identity's own 15 routes were fixed to match the spec exactly (only
   `revokeSession`'s `{sessionId}` had a path parameter); `configuration`'s pre-existing mismatch
   was left untouched (AIR-01 -- out of this task's scope to fix another module's shipped router).
6. **Outbound email**: `identity.infrastructure.providers.email.SmtpEmailProviderAdapter` reuses
   the `SMTP_HOST`/`PORT`/`USER`/`PASSWORD` environment variables already declared under
   "Notifications channels (Notifications module, template-based delivery)" for identity's own
   auth-critical transactional email (confirmation, recovery notice), rather than adding a second
   credential set. If a future Notifications-module task intends to be the *sole* sender of all
   outbound email via an event-driven flow, this adapter should be replaced accordingly.

## Coverage / quality gates (Task P-05 run)

533+ tests (`apps/backend/tests/identity/` unit + integration + API, plus
`tests/test_authorization_matrix.py`), mypy --strict clean, ruff clean, all 49
`tools/importlinter.cfg` contracts kept, overall coverage 92%+ (COV-01 80% floor), every
domain/application file at or above the 90% floor (QG-04). Provider adapters that make real
outbound HTTP calls (Eskiz, Google OAuth, SMTP) are intentionally not unit-mocked at the wire
level -- their mapping logic is simple and their coverage gap does not threaten either floor.

## Layout

```
identity/
|-- interfaces/       # PUBLIC surface: routers, published ports, DTOs, event contracts
|-- application/      # use cases (commands/queries) + ports
|-- domain/           # aggregates, value objects, domain events, policies, invariants
|-- infrastructure/   # adapters: persistence, Redis session store, provider adapters, outbox
|-- README.md         # this file
`-- TRACEABILITY.md    # requirement -> code -> test matrix
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/`/`interfaces/` declare and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
