# moderation -- requirement traceability matrix (Task P-12)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `profiles/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-MOD-001 | Any user may report a listing/conversation/account; the report enters the moderation queue | `ModerationUseCases.submit_report`; `ModerationCase.open_from_report` | `test_moderation_case.py::test_open_from_report_produces_open_with_user_report_origin`; `test_moderation_use_cases.py::test_submit_report_opens_a_new_case`; `integration/test_event_projection_live.py::test_content_reported_redelivery_opens_the_case_exactly_once` |
| FR-MOD-002 | Automated validation rules flag content at or after publication | `ModerationUseCases.auto_flag`; `ModerationCase.open_from_flag` | `test_moderation_case.py::test_open_from_flag_produces_open_with_automated_flag_origin`; `test_moderation_use_cases.py::test_auto_flag_opens_a_new_case_from_automated_flag`; `integration/test_event_projection_live.py::test_listing_flagged_redelivery_opens_the_case_exactly_once` |
| FR-MOD-003 | A moderator claims a case from the queue | `ModerationUseCases.claim_case`; `ModerationCase.claim` | `test_moderation_case.py::test_claim_from_open_advances_to_in_review`, `test_claim_twice_is_illegal`; `test_moderation_use_cases.py::test_claim_case_advances_to_in_review` |
| FR-MOD-004 | A moderator resolves a case with one action from the closed verb set; each action changes content state and is auditable | `ModerationUseCases.resolve_case`; `ModerationCase.resolve`; `ModerationActionService.execute` | `test_moderation_case.py::test_resolve_from_open_directly_is_legal`; `test_moderation_use_cases.py::test_resolve_case_persists_resolution_publishes_event_and_dispatches_action`; `test_action_service.py` (all verbs); `test_api.py::test_apply_moderation_action_resolves_case_and_dispatches_command` |
| FR-MOD-005 | The moderation work queue, filterable by status and subject type, is listed and actionable | `ModerationUseCases.list_queue`; `domain/policies.py::order_queue` | `test_moderation_use_cases.py::test_list_queue_filters_by_status_and_subject_type_and_orders_oldest_first`; `test_policies.py::test_order_queue_is_oldest_first`; `test_api.py::test_list_moderation_queue_allows_moderator`, `test_list_moderation_queue_filters_by_subject_type`; `integration/test_repository_live.py::test_list_queue_filters_and_orders_oldest_first` |

## Domain invariants (DDD Sec 9/10.3)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-24 | Moderation state changes are executed only by the owning context on command from Moderation, never by direct mutation | `ModerationActionService.execute` (dispatches ONLY through the three narrow command-port Protocols); `ModerationCase.resolve` (records the FACT, never the downstream state itself) | `test_action_service.py` (every verb calls exactly one command-port method); `test_boundary_import.py` (no static import of catalog/identity/profiles exists to bypass this) |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| BR-MOD-02 | The closed action-verb set, and which verbs are legal for which subject type | `domain/value_objects.py::ResolutionAction`, `ACTIONS_BY_SUBJECT_TYPE`; `ModerationCase.resolve` (raises `InvalidResolutionForSubjectError`) | `test_moderation_case.py::test_every_legal_subject_action_pairing_resolves`, `test_every_illegal_subject_action_pairing_raises` (both parametrized across all 4 subject types) |
| BRULE-17/DEC-14 | Content is visible on publication and reviewed afterwards, unless automated validation flags it first -- moderation never introduces a pre-publication gate | `domain/policies.py::POST_PUBLICATION_MODERATION` (documented constant, not a runtime predicate -- moderation has no mechanism to gate publication) | `test_policies.py::test_post_publication_policy_never_gates_publication` |
| Terminal-immutability (P-12 scope) | A `RESOLVED` case is terminal and immutable, retained permanently | `TerminalModerationCaseError`, guarded by every mutating `ModerationCase` method (checked FIRST, before any other validation) | `test_moderation_case.py::test_terminal_case_cannot_be_claimed`, `test_terminal_case_cannot_be_resolved_again`, `test_terminal_guard_fires_before_the_subject_action_guard` |
| "A report opens or attaches to a case" (P-12 scope) | A second report/flag against a subject that already has a non-terminal case attaches to it rather than opening a duplicate | `ModerationCaseRepository.get_open_or_in_review_for_subject`; `ModerationUseCases.submit_report`/`auto_flag` | `test_moderation_use_cases.py::test_second_report_against_same_open_subject_attaches_not_duplicates`, `test_auto_flag_against_already_open_subject_attaches`, `test_report_against_a_resolved_subject_opens_a_fresh_case`; `integration/test_repository_live.py::test_get_open_or_in_review_for_subject_ignores_resolved_cases` |
| X-04 ("compensations, not cascades") | Each target module performs its own state change and emits its own event; moderation never cascades a write | `ModerationActionService` (three narrow command ports, composition-root bridges only) | `test_action_service.py`; `integration/test_account_suspension_compensation_live.py` (catalog's OWN `LifecycleTransitionRecord`/`ListingSuspended` are produced by catalog's own code, never written by moderation) |
| DB Architecture Sec 14.4 worked example | Account suspension -> listings hidden by catalog's own transition | `composition_root._ModerationAccountSuspensionBridge` -> `AdminIdentityUseCases.change_user_status` -> `AccountSuspended` -> `composition_root.make_identity_account_status_projection_handler` -> `catalog.infrastructure.event_projection.handle_identity_event` -> `ListingUseCases.suspend_all_by_owner` | `integration/test_account_suspension_compensation_live.py::test_suspend_account_verb_suspends_every_visible_listing_via_catalogs_own_transition` (spans identity+catalog+moderation schemas against real Postgres/Redis) |
| DB Architecture Sec 1.3 (2nd sanctioned sync exception) | State transition + outbox event append commit in ONE transaction | `ModerationUseCases.resolve_case` appends `ModerationActionTaken` to `OutboxPort` inside the same session as the case's own save, BEFORE the separate `ModerationActionService.execute` dispatch | `integration/test_transactional_outbox_live.py::test_forced_failure_rolls_back_both_the_resolution_and_the_outbox_row`, `test_committed_resolution_and_outbox_row_both_persist` |

## ADR-0003 (Subject/ResolutionAction extension)

| Concern | Code | Test |
|---|---|---|
| `PROFILE` subject type; `REVOKE_BADGE`/`ARCHIVE_PROFILE` verbs | `domain/value_objects.py::SubjectType.PROFILE`, `ResolutionAction.REVOKE_BADGE`/`ARCHIVE_PROFILE`, `PROFILE_ACTIONS` | `test_moderation_case.py::test_every_legal_subject_action_pairing_resolves[PROFILE-*]`; `test_action_service.py::test_revoke_badge_verb_calls_exactly_the_profile_port`, `test_archive_profile_verb_calls_exactly_the_profile_port` |
| Contract amendment (`subjectType`/`resolutionAction`/`action` enums) | `contracts/openapi.yaml` (3 locations); `interfaces/dto.py`/`interfaces/ports.py` `Literal` types | `test_api.py::test_apply_moderation_action_resolves_case_and_dispatches_command` (`REVOKE_BADGE`/`ARCHIVE_PROFILE` accepted by the router's own DTO) |

## Cross-context boundary

| Concern | Code | Test |
|---|---|---|
| Moderation has no static dependency on ANY other module -- not even their `interfaces/` packages (stricter than every other module's own contract) | `tools/importlinter.cfg`'s `cross-module-moderation` contract | `test_boundary_import.py::test_I01_cross_module_moderation_contract_currently_passes`, `test_I02_a_deliberate_forbidden_import_breaks_the_contract_then_reverts` (parametrized: catalog/identity/profiles/configuration/billing), `test_I03_even_a_narrow_interfaces_only_import_breaks_the_contract` (parametrized: `catalog.interfaces`/`identity.interfaces`) |
| Catalog's outbox has exactly one combined dispatcher (search/messaging + moderation's `ListingFlagged` route) -- never a second, racing one | `composition_root.make_catalog_outbox_fanout_handler` (extended, not duplicated) | Verified structurally (no second `OutboxDispatcher` constructed against `CatalogOutboxEventRow` anywhere in `composition_root.py`); exercised via `integration/test_event_projection_live.py::test_listing_flagged_redelivery_opens_the_case_exactly_once` |
| Messaging's outbox gets its first-ever dispatcher, dedicated to moderation | `composition_root.make_messaging_report_projection_handler`/`provide_moderation_report_projection_dispatcher`; `moderation_worker.py` | `integration/test_event_projection_live.py::test_content_reported_redelivery_opens_the_case_exactly_once` |
| Identity's outbox gets its first-ever dispatcher, run by catalog's own worker (catalog is the consumer) | `composition_root.make_identity_account_status_projection_handler`/`provide_identity_account_status_projection_dispatcher`; `catalog_worker.py` (extended) | `integration/test_account_suspension_compensation_live.py` |

## Moderator authorization (`listModerationQueue`/`getModerationCase`/`applyModerationAction`)

| Concern | Code | Test |
|---|---|---|
| `moderation:case:review` gates all three operations, wired end-to-end | `composition_root.provide_moderation_acting_moderator` -> `identity.domain.AuthorizationService.authorize` | `test_api.py::test_list_moderation_queue_refuses_non_moderator`, `test_list_moderation_queue_allows_moderator`, `test_get_moderation_case_refuses_non_moderator`, `test_apply_moderation_action_refuses_non_moderator` |
| Scenarios contributed to the shared release-blocking authorization matrix (TEST-02/QG-08) | `tests/authorization_matrix.py::MODERATION_MATRIX` (`moderation:case:review`, operator-wide, no ownership scoping) | `tests/test_authorization_matrix.py::test_authorization_allow_deny_matrix` (`SCENARIOS = [*IDENTITY_MATRIX, *CATALOG_MATRIX, *BILLING_MATRIX, *PROFILES_MATRIX, *MODERATION_MATRIX]`) |

## Validation checklist cross-reference (P-12 prompt)

| Checklist item | Evidence |
|---|---|
| Fixed action-verb set; invalid verb refused | `domain/value_objects.py::ResolutionAction` (closed 9-value enum); no DTO/port accepts an arbitrary string -- `Literal` types throughout |
| interface-only-action guarantee: moderation never mutates another module's state directly | `test_action_service.py` (the module's most important test -- every verb reaches exactly one command-port method); `cross-module-moderation` import-linter contract (stricter than every other module) |
| Report intake + automated flagging both open/attach a ModerationCase, never duplicate | `test_moderation_use_cases.py::test_second_report_against_same_open_subject_attaches_not_duplicates`, `test_auto_flag_against_already_open_subject_attaches` |
| Post-publication moderation policy (BRULE-17) -- no pre-publication gate exists | `test_policies.py::test_post_publication_policy_never_gates_publication` |
| Automated flagging (FlaggingService) is reactive-only, since moderation cannot import configuration/catalog | See README "The FlaggingService is reactive-only"; `test_boundary_import.py` proves the import is structurally impossible |
| Account-suspension compensation demonstrably suspends every visible listing via catalog's OWN transition, not moderation's | `integration/test_account_suspension_compensation_live.py` (3-schema, real Postgres+Redis) |
| Moderation imports ONLY shared_kernel (import-linter enforced, deliberate-violation-then-revert, including the stricter "not even interfaces/" case) | `test_boundary_import.py` (all three test functions) |
| Every moderation OpenAPI operation implemented; contract conformance green | `test_api.py` (all 3 operations exercised end-to-end via `TestClient` + `main.create_app()`) |
| Authorization matrix (QG-08) extended with moderator scenarios, green | `tests/authorization_matrix.py::MODERATION_MATRIX`; `tests/test_authorization_matrix.py` |
| Outbox atomicity: case resolution + `ModerationActionTaken` commit together | `integration/test_transactional_outbox_live.py` |
| Idempotent event consumption via ProcessedEvent | `infrastructure/event_projection.py` (`idempotent_consume` wraps both handlers); `integration/test_event_projection_live.py` (real Postgres `INSERT ... ON CONFLICT`, redelivery applies once) |
| Coverage floors met; mypy --strict/ruff/import-linter clean | See README "Coverage / quality gates": domain/application all >= 95.8%, overall (full suite) 86.9%; mypy/ruff clean; 49/49 import-linter contracts kept |
