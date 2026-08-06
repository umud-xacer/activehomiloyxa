# configuration -- requirement traceability matrix (Task P-04)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `catalog/TRACEABILITY.md`/`billing/TRACEABILITY.md`'s shape exactly.

configuration is the one module that had no traceability file before this task (G-019) -- it is
also the oldest implemented module (P-04), which is why its `interfaces/routers.py` had drifted
from the frozen contract's camelCase path-parameter spelling (fixed in this same task; see
`docs/assessments/2026-07-24-audit/GAP-BACKLOG-2026-07-24.md` G-004).

Per the Domain Model's Scope column, configuration owns four of the 24 global invariants: I-02,
I-03, I-11, I-16. None of the four is literally named `test_I<nn>_*` in every covering test --
each row below cites the test(s) that were read and confirmed to assert the invariant's actual
content, not matched by number (the `test_I<nn>_*` naming convention is heavily overloaded across
this codebase for unrelated local numbering schemes; see
`docs/assessments/2026-07-24-audit/INVARIANT-COVERAGE-2026-07-24.md`'s caveat). Only I-16 happens to have several
literally-named `test_I16_*` tests (in `test_gate.py`/`test_whitelist.py`/`test_head_version.py`);
I-02, I-03, and I-11 are covered by tests named after what they assert instead.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-CFG-001 | Configure taxonomy (category tree: create/move/retire, no orphaned listings) | `taxonomy.creates_cycle`/`would_orphan_listings` (`domain/taxonomy.py`, plain domain-service functions); `ConfigurationUseCases` head/version lifecycle applied to `category` entity type | `test_taxonomy.py` (all three tests); `test_gate.py::test_I03_retiring_category_with_bound_listings_is_refused` |
| FR-CFG-002 | Configure forms & fields (dynamic `FormDefinition`, sections/fields, whitelisted field types only) | `configuration.domain.content.FormDefinitionContent`; `PreActivationGate` form-definition checks | `test_content_models.py` (`FormDefinitionContent` tests); `test_gate.py::test_I16_form_definition_whitelisted_field_type_accepted`, `test_I16_form_definition_non_whitelisted_field_type_refused` |
| FR-CFG-003 | Configure validation rule *selections*, filters, sorting from a whitelisted vocabulary; maker-checker publish workflow | `PreActivationGate.evaluate`; `ConfigVersion.move_to_awaiting_approval`/`approve_and_publish`/`publish_directly` | `test_head_version.py` (lifecycle transition tests); `test_gate.py::test_I16_form_definition_non_whitelisted_validator_type_refused`; `integration/test_maker_checker_live.py` |
| FR-CFG-004 | Configure commercial products (`ProductDefinition`, whitelisted product types) | `configuration.domain.content.ProductDefinitionContent` | `test_content_models.py::test_product_definition_price_amount_is_decimal`; `test_gate.py::test_I16_product_definition_whitelisted_product_type_accepted`, `test_I16_product_definition_non_whitelisted_product_type_refused` |
| FR-CFG-005 | Configure platform settings (whitelisted settings/homepage-zone/SEO-page/static-page keys) | `configuration.domain.content.PlatformSettingsContent` | `test_content_models.py::test_platform_settings_minimal_shape`; `test_gate.py::test_I16_platform_settings_non_whitelisted_*` (4 tests) |
| FR-CAT-001 | Browse categories (public, unauthenticated, snapshot-served) | `CategoryReadUseCases.list_categories`/`get_category`; `categories_router` | `test_category_read.py::test_list_categories_excludes_retired_by_default`, `test_list_categories_filters_by_parent`, `test_get_category_returns_published_snapshot` |
| FR-CAT-002 | Category-field association (a category names the one form it renders) | `CategoryContent.form_definition_id` (`domain/content.py`) | `test_content_models.py::test_category_requires_form_definition_id` |
| FR-FORM-001 | Render dynamic form (sections ordered, fields grouped by section, published snapshot only) | `CategoryReadUseCases.get_category_form`; `_form_definition_dto_from_snapshot` (`interfaces/routers.py`) | `test_category_read.py::test_get_category_form_resolves_the_one_directional_binding`; `test_api.py` (`getCategoryForm` route) |
| FR-FORM-002 | Validate submissions against whitelisted field/validator types only (never an arbitrary code path) | `PreActivationGate.evaluate` + `_ENTITY_CHECKS`; `WhitelistRegistry` | `test_gate.py` (18 `test_I16_*` whitelist-rejection tests, one per entity type/vocabulary) |
| FR-LOC-001 (partial) | Multilingual config content (`uz_latn`/`uz_cyrl`/`ru`/`en`) | `LocalizedText` (via `shared_kernel`, used throughout `domain/content.py`) | `test_content_models.py` (descriptor `name`/`label` fields exercised as `LocalizedText`) -- UI-facing half blocked on frontend, tracked separately (`docs/assessments/2026-07-24-acceptance/mapping.md` FR-LOC-001) |
| NFR-CFG-001 | Bounded configurability -- field types/validator types/permission keys/product types/event keys are a fixed, code-owned whitelist; configuration data can only compose from it | `WhitelistRegistry` (`domain/whitelist.py`) | `test_whitelist.py` (all 4 tests, including `test_I16_event_key_whitelist_has_zero_drift_from_frozen_event_catalogue`) |

## Domain invariants (DDD Sec 9)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-02 | Exactly one `FormDefinition` binding per `Category`, one-directional (`category.form_definition_id`; no back-reference from the form) | `CategoryContent.form_definition_id` required (`domain/content.py`); `FormDefinitionContent` carries no `category_id` field | `test_content_models.py::test_category_requires_form_definition_id` (binding is mandatory), `test_form_definition_has_no_category_id_field` (binding is one-directional, not literally `test_I02_*` but asserts I-02's exact content); `test_category_read.py::test_get_category_form_resolves_the_one_directional_binding` (application-level proof) |
| I-03 | Retiring or moving a `Category` must not silently orphan listings bound to it -- the taxonomy domain service requires an explicit remap or blocks the change | `taxonomy.would_orphan_listings` (`domain/taxonomy.py`); wired into `PreActivationGate`'s category check | `test_taxonomy.py::test_I03_retiring_category_with_bound_listings_orphans_them` (detection predicate -- despite its name, asserts the *detection* function returns `True`, not that orphaning is permitted; see README "Looks done but isn't" note in the audit), `test_I03_retiring_category_without_bound_listings_is_safe`, `test_I03_non_retiring_status_never_orphans_regardless_of_listings`; `test_gate.py::test_I03_retiring_category_with_bound_listings_is_refused` (the actual blocking gate, `GateError("ORPHANED_LISTINGS", ...)` at `domain/gate.py`) |
| I-11 | Permission semantics are immutable at runtime -- role permissions are flattened once at publish time (groups + parent-role inheritance resolved then), never re-resolved at request time | `flatten_role_permissions` (`domain/permissions.py`), called from `ConfigurationUseCases` when a `role-definition` version publishes | `test_permissions.py` (all 5 tests: direct keys, group expansion, parent-role merge, dedup/sort, unknown-group-is-inert) -- none is literally named `test_I11_*`, but the module docstring cites I-11 verbatim and the tests exercise exactly its "flattened once, no runtime inheritance" content |
| I-16 | Business Configuration `[C]` may only compose instances from the code-owned Platform Capability `[P]` whitelist (field types, validator types, permission keys, product types, event keys, ...); never a value outside it without a code release | `WhitelistRegistry` (`domain/whitelist.py`); `PreActivationGate` (`domain/gate.py`) dispatches every entity type's content through it | `test_whitelist.py` (4 tests); `test_gate.py` (18 `test_I16_*` tests, one per whitelisted vocabulary per entity type); `test_head_version.py::test_I16_self_approval_refused` (maker-checker: the approving admin may not be the same actor who drafted the version -- I-16's "no bypass of the code-owned control" read applied to the approval gate itself) |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| DEC-21 ("Bounded Configurability") | Categories/forms/plans/roles/settings are admin-authored data at runtime; field types/validator types/permission keys are a fixed, code-defined whitelist | `WhitelistRegistry`; `ConfigEntityType` (the closed 8-entity-type vocabulary) | `test_entity_types.py::test_eight_entity_types_exactly`; `test_whitelist.py` |
| Config Framework Sec 2.3 | Six of the eight entity types are on the "controlled" authoring track (super-admin approval required); two are "standard" | `authoring_track`/`requires_super_admin_approval` (`domain/entity_types.py`) | `test_entity_types.py::test_controlled_track_is_the_six_named_by_config_framework_sec_2_3`, `test_standard_track_is_the_remaining_two`, `test_super_admin_approval_is_narrower_than_controlled_track` |
| Config Framework Sec 9 ("maker-checker") | A controlled-track version requires validation, then approval by an admin other than its own drafter, before publish | `ConfigVersion.move_to_awaiting_approval`/`approve_and_publish` | `test_head_version.py::test_move_to_validation_then_awaiting_approval`, `test_approve_and_publish_stamps_checker_and_publisher_identically`, `test_I16_self_approval_refused`; `integration/test_maker_checker_live.py` |
| Config Framework Sec 9 ("pre-activation validation") | Every publish and rollback runs through the same `PreActivationGate`, standard and controlled tracks alike | `PreActivationGate.evaluate` | `test_gate.py` (all entity-type checks); `integration/test_gate_rejection_live.py`; `integration/test_rollback_live.py` |
| Physical DB Sec 13 / DB Architecture Sec 1.3 | Head+Version+snapshot publish commits atomically with its outbox `ConfigurationChanged` event | `ConfigurationUseCases.publish` + `OutboxWriter.append`, same session | `integration/test_publish_atomicity.py` |
| Config Framework Sec 2.8 | Whitelist *scope* (which vocabularies exist, not their contents) is a release-time, ADR-controlled decision; several v1 seed sets are conservative placeholders, extendable later without touching the generic gate machinery | `WhitelistRegistry` (`# PLACEHOLDER`-flagged sets, see module docstring) | `test_whitelist.py::test_I16_event_key_whitelist_has_zero_drift_from_frozen_event_catalogue` (the one whitelist with an authoritative external source to drift-check against) |

## Contract conformance (this task)

| Concern | Detail |
|---|---|
| Path-parameter casing | `interfaces/routers.py` registered `{entity_type}`/`{head_id}`/`{version_id}`/`{category_id}` (snake_case); `contracts/openapi.yaml` specifies `{entityType}`/`{headId}`/`{versionId}`/`{categoryId}` (camelCase) for the identical 15 routes. FastAPI matches routes structurally, not by parameter name, so this was a string-comparison drift-checker failure, not a functional bug -- fixed in this task by renaming the path templates and their bound handler parameters to camelCase; no route path, method, response model, or behaviour changed. |
| Remaining `check_contract_drift.py` scope | The script only checks one direction (routes registered on the app but absent from the spec) -- by its own docstring, a spec operation with no implementing route is deliberately not a failure mode it reports. The three Business Profiles team-management operations (`addTeamMember`/`listTeamMembers`/`removeTeamMember`, G-011) are genuinely unimplemented but do **not** make this script exit non-zero; they remain a real, separate gap requiring a human ADR (implement, or remove from `contracts/openapi.yaml`), tracked in `docs/assessments/2026-07-24-audit/GAP-BACKLOG-2026-07-24.md`, independent of this module. |
