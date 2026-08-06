# ADR-0006: Add role-assignment operations to the frozen OpenAPI contract

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-07-14

**Author**: Claude Sonnet 5, drafting under Task P-16 (Administration) at the explicit direction
of the repository owner, after surfacing the conflict below rather than silently resolving it.

## Context

FR-ADMIN-006 (SRS): *"The system SHALL allow a Super Administrator to assign roles and
permissions within the fixed permission model... Acceptance: assignments take effect; permission
semantics cannot be redefined."* DDD §5.12: *"Role/permission management UI (FR-ADMIN-006) writes
RoleDefinitions in BC-04 and assignments in BC-01 — through their interfaces."*

The RoleDefinition-authoring half is already fully served: `configuration`'s generic
`/admin/config/{entityType}` CRUD surface (Task P-04) already covers `entityType=role-definition`,
including the controlled-track maker–checker approval flow (`config:role-definition:manage`/
`config:role-definition:approve`).

The assignment half has no HTTP surface at all. `identity.application.admin_use_cases.
AdminIdentityUseCases.assign_role`/`revoke_role` (Task P-05) are real, fully-implemented use
cases — domain method `UserAccount.assign_role`/`revoke_role` exists, the `RoleDefinitionReaderPort`
dependency they need is already wired — but `contracts/openapi.yaml` has no operation for them.
`identity/README.md`'s own "Public interface" section already names this exact gap explicitly:
*"`AdminIdentityUseCases.list_users`/`change_user_status`, plus `assign_role`/`revoke_role` which
have no OpenAPI operation at all yet) for a future `admin`-module task to mount the HTTP surface
over, without touching this module (AIR-01)."* `configuration.domain.whitelist.PERMISSION_KEYS`'s
own P-05 comment independently confirms the same thing: `identity:role:assign` was added in Task
P-05 specifically *"once a future admin-module task mounts the HTTP surface over those use
cases."* This task (P-16) is that future task.

Surfaced to the repository owner via three options (draft this ADR and add the operations now;
build the use case unmounted, matching the "known gap" precedent; skip role assignment entirely).
The owner's explicit direction: **draft this ADR and add the operations now**.

## Decision

Add two new operations to `contracts/openapi.yaml`, tagged `Administration` (matching
`adminListUsers`/`adminChangeUserStatus`, the two existing operations on the same resource
family) and implemented in `identity`'s own `interfaces/routers.py` — NOT in `admin` — mirroring
exactly where `adminListUsers`/`adminChangeUserStatus` already live (both, despite their
`Administration` tag, are identity's own router functions per `contracts/README.md`'s own
established P-01 tag-routing rule: an `Administration`-tagged operation belongs to the module
that owns the underlying aggregate, and `RoleAssignment` is a child entity of identity's own
`UserAccount`, DDD §5.1).

- **`POST /admin/users/{userId}/roles`** (operationId `assignRole`) — request body
  `RoleAssignmentRequest {roleCode: string, actingProfileId?: uuid|null}`; response `200` +
  `UserAdminView` (the same response shape `adminChangeUserStatus` already uses — no schema
  change needed for the response). Calls `AdminIdentityUseCases.assign_role` directly.
- **`DELETE /admin/users/{userId}/roles/{roleDefinitionHeadId}`** (operationId `revokeRole`) —
  query param `actingProfileId?: uuid`; response `200` + `UserAdminView`. Calls
  `AdminIdentityUseCases.revoke_role` directly.

Both gated by the already-existing `identity:role:assign` permission key (added in P-05,
unconsulted anywhere until now) — no new permission key invented, per Absolute Architecture Rule
9/AIR-19 ("permissions are fixed and composed from configuration — admin cannot invent one").

One new schema, `RoleAssignmentRequest`. `UserAdminView` is unchanged — it does not surface role
assignments in its response body (an operator re-queries `GET /admin/users` for current state,
matching how `adminChangeUserStatus` doesn't echo back suspension history either).

This ADR does **not** touch `identity/domain/` or `identity/application/` — both are already
complete from Task P-05. Only `identity/interfaces/{dto,ports,routers}.py` gain the two new
methods/DTOs/route handlers, and `configuration/domain/whitelist.py`'s comment is updated to
record that `identity:role:assign` is now consulted (the permission key value itself is
unchanged — it already existed).

## Why this lives in `identity`, not `admin`

`admin` (BC-12) is a pure composition context that owns no marketplace aggregate (DDD §5.12) —
role assignment mutates `UserAccount.role_assignments`, an entity inside identity's own aggregate
boundary. Putting the router in `admin` would mean either (a) admin directly manipulating
identity's aggregate (violates Absolute Architecture Rule 2 — state transitions must live inside
the domain object guarded by its own invariant, reachable only through identity's own use case)
or (b) admin's router calling identity's already-built use case through a port — which is exactly
what putting the router in `identity` itself already achieves more directly, with one fewer
indirection layer, and matches the existing, already-shipped precedent
(`adminListUsers`/`adminChangeUserStatus`) exactly. `admin`'s own composition layer
(`AdminUserUseCases`, Task P-16) still calls through to this capability via identity's real
`interfaces/` port — proving the composition property this module exists to demonstrate — it
simply doesn't duplicate a second HTTP route for an operation identity's own router already
serves.

## Alternatives considered

1. **Put the router in `admin` instead of `identity`.** Rejected: would require admin to reach
   past identity's own port into `identity.application`/`identity.domain` directly (a
   `cross-module-admin` contract violation — admin may only import `interfaces/` packages) or
   would require identity to expose a bespoke second port just for admin's router to call,
   duplicating `ActingIdentityQueryPort`'s own shape for no benefit. Putting it directly on
   identity's own router (which already owns the sibling `adminListUsers`/`adminChangeUserStatus`
   operations) is the established pattern.
2. **Leave it as a known, unmounted gap** (this ADR's second considered option). Rejected by the
   repository owner's explicit direction — the use case, the permission key, and the domain
   method have all been ready and waiting since Task P-05 specifically for this task.
3. **Fold role assignment into `adminChangeUserStatus`'s existing request body** (add an optional
   `roleCode` field to `UserStatusChangeRequest`). Rejected: conflates two independently-permissioned
   actions (`identity:account:manage_status` vs `identity:role:assign`) into one endpoint, breaking
   the "one operation, one permission check" discipline every other admin-facing operation in this
   codebase already follows.

## Consequences

- `contracts/openapi.yaml` (two new operations, one new schema) and its two byte-identical copies
  (`docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`, `docs/frontend_docs/...`) are updated
  in the same change.
- `identity/interfaces/{dto,ports,routers}.py` gain the new DTO/port methods/route handlers.
  `identity/domain/`, `identity/application/` are untouched (already complete).
- `configuration/domain/whitelist.py`'s own P-05 comment is updated to record that
  `identity:role:assign` is now consulted for real (no new key added).
- `identity/README.md`'s own "Known gaps"/"Public interface" notes are updated to record this gap
  is now resolved (mirroring exactly how `catalog/README.md`'s/`ads/README.md`'s own equivalent
  notes were updated by ADR-0004/ADR-0005's own precedent).
- This ADR does **not** itself edit SRS v1.0 or the Domain Model v1.0 (immutable source documents
  outside version control here, per Playbook §18's governance note). This ADR is the durable
  record of why `contracts/` now differs from a purely-implicit reading of FR-ADMIN-006, pending
  that re-versioning.

## Approved-document references touched

- SRS v1.0 FR-ADMIN-006.
- DDD Domain Model v1.0 §5.1 (`RoleAssignment` entity), §5.12 (Administration's own composition
  framing — "writes... assignments in BC-01 — through their interfaces").
- Configuration & Metadata Framework §7.2 (role assignment pins identity + published version).
- `identity/README.md` ("Public interface", "Known gaps"), `configuration/domain/whitelist.py`
  (P-05 comment).
- Absolute Architecture Rule 9/AIR-19 (no new permission key invented — reuses the one Task P-05
  already added for exactly this purpose).
