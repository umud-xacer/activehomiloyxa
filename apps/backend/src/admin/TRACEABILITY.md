# admin -- requirement traceability matrix (Task P-16)

Maps each requirement/invariant this module satisfies to its implementing code and the named
test that proves it. Mirrors `ads/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-ADMIN-005 | Composed operational dashboard KPIs for operators | `application/dashboard_use_cases.py::AdminDashboardUseCases.get_dashboard` | `test_dashboard_use_cases.py::test_every_summary_field_is_honestly_null`, `test_get_dashboard_calls_all_four_owning_module_probes_for_real`; `test_api.py::TestGetAdminDashboard` |

Every other Administration-tagged requirement (moderation queue actioning, verification
decisions, invoice confirmation, user status/role management, audit log/reports) is satisfied
entirely by its owning module's own already-traced requirement rows (`moderation/TRACEABILITY.md`,
`profiles/TRACEABILITY.md`, `billing/TRACEABILITY.md`, `identity/TRACEABILITY.md`,
`analytics/TRACEABILITY.md`) -- see README "The corrected scope" for why admin declares no
duplicate row for any of them.

## Domain invariants (DDD Sec 10.3)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| "one context per operator" | `OperatorSessionContext` is upserted by `operator_user_id`, never duplicated (Physical DB Sec 2.12's own `UNIQUE` constraint) | `infrastructure/persistence/repository.py::SqlalchemyOperatorSessionRepository.upsert` | `integration/test_repository_live.py::test_upsert_is_one_row_per_operator_not_a_second_insert` |
| honest-null dashboard | Every `DashboardSummary` field admin cannot cheaply/honestly compute is `None`, never a fabricated or partial-page approximation | `application/dashboard_use_cases.py::AdminDashboardUseCases.get_dashboard` | `test_dashboard_use_cases.py::test_every_summary_field_is_honestly_null` |
| dead-code-free composition | `admin/` declares no wrapper use case for a capability another module's own router already serves end-to-end | Absence -- verified by the README's own operation-by-operation audit table, not a passing test | README "The corrected scope" |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| SAD Sec 7.2 | admin owns no marketplace aggregate; `OperatorSessionContext` is the sole exception | `domain/__init__.py::__all__` (exactly one entry) | `test_composition_only.py::test_composition_only_domain_has_exactly_one_entity` |
| Absolute Architecture Rule 4 | No side-effect modification of, or duplicate implementation for, another module's already-owned capability | Narrow local Protocols in `dashboard_use_cases.py`, never a full owning-module Protocol implementation | README "The narrow-Protocol-plus-composition-bridge pattern" |
| P-01 tag-routing rule (`contracts/README.md`) | An `Administration`-tagged operation is routed to its owning aggregate's module, not necessarily admin | README "The corrected scope" table (all 14 operations enumerated) | `test_composition_only.py::test_I05_no_other_module_statically_imports_admin` (admin has no static handle on the modules that serve the other 13 operations) |
| ADR-0006 | `assignRole`/`revokeRole` added to the frozen contract and implemented on identity's own router, never admin's | `identity/interfaces/routers.py::assign_role`/`revoke_role` | `identity`'s own test suite (`apps/backend/tests/identity/test_api.py`) |

## Cross-context boundary

| Concern | Code | Test |
|---|---|---|
| `admin` only statically imports `shared_kernel` and the `interfaces/` package of its allowed modules | `tools/importlinter.cfg`'s `cross-module-admin` contract | `test_composition_only.py::test_I01_cross_module_admin_contract_currently_passes`, `test_I04_a_deliberate_moderation_application_import_breaks_the_contract_then_reverts` |
| Clean Architecture layering (`interfaces -> application -> domain`) and no `infrastructure` inbound import | `tools/importlinter.cfg`'s `layers-admin`/`no-infra-inbound-admin` contracts | `test_composition_only.py::test_I02_layers_admin_contract_currently_passes`, `test_I03_no_infra_inbound_admin_contract_currently_passes` |
| Nothing outside `admin` imports it -- proven both by the dedicated sink contract and by direct repo-wide inspection | `tools/importlinter.cfg`'s `sink-modules-have-no-inbound-imports` contract | `test_composition_only.py::test_I05_no_other_module_statically_imports_admin` |
| The two allowed importers (`composition_root.py`/`main.py`) do in fact import `admin` -- a mirror-image sanity check that the isolation tests aren't vacuously passing | `composition_root.py`'s `# == admin (Task P-16) ==` section; `main.py`'s router registration | `test_composition_only.py::test_I06_the_two_allowed_importers_do_in_fact_import_admin` |

## Authorization

| Concern | Code | Test |
|---|---|---|
| `getAdminDashboard` default-denies a caller without `admin:dashboard:read` | `composition_root.py::provide_admin_acting_operator` (`AuthorizationService().authorize(context, "admin:dashboard:read")`) | `test_api.py::TestGetAdminDashboard::test_requires_authentication`, `test_default_denies_a_caller_without_admin_dashboard_read` |
| Every composed dashboard probe reuses the OWNING module's own real use case/permission model, never a second, laxer check | `composition_root.py`'s `_ModerationQueueProbe`/`_VerificationQueueProbe`/`_InvoiceQueueProbe`/`_UserQueueProbe` (construct the real `ModerationUseCases`/`VerificationUseCases`/`PaymentUseCases`/`AdminIdentityUseCases`) | `test_dashboard_use_cases.py::test_get_dashboard_calls_all_four_owning_module_probes_for_real` |

## Contract fidelity

| Concern | Code | Test |
|---|---|---|
| `DashboardSummary`'s wire shape matches `contracts/openapi.yaml` exactly, including the one field (`newUsers7d`) where pydantic's generic `to_camel` alias generator would otherwise drift (`new_users_7d` -> `newUsers7D`) | `interfaces/dto.py::DashboardSummary.new_users_7d` (`Field(alias="newUsers7d")`) | `test_dto.py::test_new_users_7d_serializes_to_the_contracts_exact_field_name`, `test_dashboard_summary_round_trips_from_a_null_projection_dict` |

## Validation checklist cross-reference (P-16 prompt)

| Checklist item | Evidence |
|---|---|
| Composition-only test: `admin/domain` contains ONLY `OperatorSessionContext` | `test_composition_only.py::test_composition_only_domain_has_exactly_one_entity` |
| Interface-only-dependency test | `test_composition_only.py::test_I01_cross_module_admin_contract_currently_passes` + import-linter contract |
| No-cycle test: nothing imports `admin` | `test_composition_only.py::test_I05_no_other_module_statically_imports_admin` |
| Authorization default-deny test | `test_api.py::test_requires_authentication`, `test_default_denies_a_caller_without_admin_dashboard_read` |
| Maker-checker circumvention test | N/A -- admin composes no maker-checker-gated operation (config-authoring's own maker-checker rule lives entirely in `configuration`'s own already-mounted `admin_config_router`, P-04; role ASSIGNMENT, unlike role-DEFINITION publishing, carries no maker-checker requirement -- `identity.application.admin_use_cases.AdminIdentityUseCases.assign_role`/`revoke_role` are single-actor operations). See README "The corrected scope." |
| Delegation tests: the owning module performed and recorded the state change, not admin | Structural, not runtime: `admin/` holds no repository/outbox for any owning module's aggregate at all (`application/ports.py` declares only `OperatorSessionRepository`) -- there is no code path by which admin could perform the write itself. `test_composition_only.py::test_I01`/`test_composition_only_domain_has_exactly_one_entity` |
| Role-management test: writes land in `configuration`/`identity`, not `admin` | `identity`'s own test suite exercises `assign_role`/`revoke_role` against `identity`'s own repository; `admin.infrastructure`'s own migration adds no user/role table |
| Dashboard test: metrics only from reachable modules' closed read surfaces, honest null otherwise | `test_dashboard_use_cases.py` (both tests) |
| Full quality gate run: mypy --strict, ruff, import-linter, coverage floors | README "Coverage / quality gates" |
