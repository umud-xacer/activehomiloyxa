# configuration -- module charter

STATUS: implemented (Task P-04) -- the first real bounded-context module in the codebase. All
eight config entities (Category, FormDefinition, ProductDefinition, PlacementSlot,
RoleDefinition, SearchConfiguration, NotificationTemplate, PlatformSettings) are instantiations
of one generic Head+Version+snapshot+publish-transaction aggregate (`domain/head_version.py`,
`domain/lifecycle.py`), gated by a whitelist registry (`domain/whitelist.py`, I-16) and a
pre-activation validation gate (`domain/gate.py`, Config Framework Sec 9) before any version can
publish. STANDARD-track entities publish in one call; CONTROLLED-track entities
(category/form-definition/product-definition/placement-slot/role-definition/platform-settings)
require a maker's submit call followed by a distinct checker's approve call to the same
`publishConfigVersion` operation (Config Framework Sec 2.3/2.6) -- no separate approve endpoint.
All 16 frozen `contracts/openapi.yaml` operations are wired in `interfaces/routers.py`, backed by
real PostgreSQL persistence (`infrastructure/persistence/`) and a Redis snapshot cache
(`infrastructure/cache/`), with every publish writing its state change and its
`ConfigurationChanged` outbox event in the same transaction (DEC-09). Authorization is a P-04
stand-in (`interfaces/auth.py`'s header-based `ActingAdmin`) pending identity's (BC-01) real
session-based `AuthorizationService` -- see that file's docstring before assuming it is final.
This README is the module's public charter -- read it before working in this module (Playbook Sec 13).

## Bounded context

- **Module**: `configuration` (BC-04, Core domain per DDD/SAD classification)
- **Responsibilities**: Taxonomy, forms, validation composition, products/pricing, banner slots, role source, search config, templates, settings. The bounded-configurability hub.

## Owned aggregates / entities (from the Domain Model -- implemented, Task P-04)

Category, FormDefinition, ProductDefinition, RoleDefinition, SearchConfiguration, NotificationTemplate, PlatformSettings, PlacementSlotDefinition

Note: `Category.form_definition_id` binds a form to a category (I-02, "exactly one binding");
the reverse is not modelled -- `FormDefinition` carries no `category_id` (Physical DB Sec 2.4 has
no promoted column for it), so a form can be authored and published standalone before any
category references it.

## Public interface (`interfaces/`)

Config snapshots + ConfigurationChanged events; WhitelistRegistry

The `interfaces/` package is this module's *only* importable surface (AIR-02). Nothing in
`application/`, `domain/`, or `infrastructure/` may be imported by another module, ever.

## Interface surface (Task P-01 stubs, wired to real routers in P-04)

Ports (`apps/backend/src/configuration/interfaces/ports.py`): `ConfigurationPort`, `WhitelistRegistryPort`.

DTOs (`apps/backend/src/configuration/interfaces/dto.py`): `PageInfo`, `ConfigurationDraftRequest`, `ConfigurationVersion`, `Category`, `FormDefinition`, `FormSection`, `FormField`, `FormFieldOptions`, `ValidatorBinding`, `FormFieldConditionalVisibility`, `ConfigurationHead`, `ImportConfigBody`, `ConfigurationHeadPage`, `ConfigPublishRequest`, `ConfigRollbackRequest`, `ConfigValidationResult`.

Routers (`apps/backend/src/configuration/interfaces/routers.py`): `categories_router` (public,
unauthenticated -- `GET /categories`, `GET /categories/{id}`, `GET /categories/{id}/form`) and
`admin_config_router` (13 operations behind `ActingAdmin` + per-entity-type `manage`/`approve`
permission checks). `interfaces/di.py` declares only abstract `Depends(...)` override points
(no infrastructure import, per `no-infra-inbound-configuration`) -- the real wiring lives in
`apps/backend/src/composition_root.py`, outside every module's own package tree, and is
installed via `app.dependency_overrides[...]` in `apps/backend/src/main.py`.

## Testing

`apps/backend/tests/configuration/` (fast, fake-repository-backed: domain/application/API unit
tests) and `apps/backend/tests/configuration/integration/` (real PostgreSQL + Redis, marked
`@pytest.mark.integration`, needs `scripts/dev-up.sh`) -- see those directories' `conftest.py`
for fixture conventions (`minimal_content()` builds a gate-passing draft per entity type).

## Allowed static dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: shared_kernel only -- MUST stay leaf-free (the hub every other module conforms to)

MUST NOT import: every other module, with no exception

## Events

Publishes: ConfigurationChanged (all consumers react to new immutable versions).

## Layout

```
configuration/
|-- interfaces/       # PUBLIC surface: routers, published ports, event contracts
|-- application/      # use cases (commands/queries) + ports
|-- domain/           # aggregates, value objects, domain events, policies, invariants
|-- infrastructure/   # adapters: persistence, provider adapters, outbox
`-- README.md         # this file
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
