# profiles -- requirement traceability matrix (Task P-11)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `billing/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-PROF-001 | Business User creates a company profile of one of the eight supported types | `ProfileUseCases.create_profile`; `BusinessProfile.create` | `test_business_profile.py::test_all_eight_profile_types_can_be_created` (parametrized); `test_profile_use_cases.py::test_create_profile_activates_immediately_and_publishes_event`; `test_api.py::test_create_and_get_business_profile` |
| FR-PROF-002 | Maintain company details and upload a portfolio | `ProfileUseCases.update_profile`/`add_portfolio_item`/`remove_portfolio_item`; `BusinessProfile.update_details`/`add_portfolio_item`/`remove_portfolio_item` | `test_business_profile.py::test_add_portfolio_item_*`, `test_remove_portfolio_item_*`; `test_profile_use_cases.py::test_update_profile_*`; `test_api.py::test_portfolio_add_list_remove` |
| FR-PROF-003 | Submit verification documents as images; non-image files rejected | `SubmittedDocument` (media asset ref only, images-only enforced at media's own upload boundary -- see README); `VerificationCase.create` | `test_verification_case.py::test_I12_create_refuses_zero_documents` |
| FR-PROF-004 | Request verification, creating a case in the reviewer queue | `VerificationUseCases.request_verification` | `test_verification_use_cases.py::test_request_verification_succeeds_with_active_entitlement`; `test_api.py::test_request_verification_and_get_current_case` |
| FR-PROF-005 | Reviewer approves/rejects a case, recording the outcome; approval issues a badge | `VerificationUseCases.decide_verification`; `VerificationCase.decide` | `test_verification_case.py::test_decide_*`; `test_verification_use_cases.py::test_I13_decide_verification_approved_issues_badge_*`, `test_decide_verification_rejected_never_touches_the_badge`; `test_api.py::test_decide_verification_allows_reviewer_and_refuses_others` |
| FR-PROF-006 | Verified badge displays for the badge's validity period | `BusinessProfile.issue_badge`; `search.infrastructure.event_projection.handle_verified_badge_applied` (downstream) | `test_business_profile.py::test_I13_approving_a_case_issues_the_badge`; `integration/test_downstream_search_projection_live.py::test_business_verified_sets_the_verified_badge_flag_on_the_owners_listings` |
| FR-PROF-007 | Re-verification required when a badge's validity period ends | `ProfileUseCases.expire_badge`/`sweep_expired_badges`; `BusinessProfile.expire_badge` | `test_business_profile.py::test_expire_badge_from_valid`, `test_reverification_can_issue_a_fresh_badge_after_expiry`; `test_profile_use_cases.py::test_sweep_expired_badges_expires_all_due_and_publishes_events` |

## Domain invariants (DDD Sec 9)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-12 | A VerificationCase requires submitted image documents and an active VerificationEligibility entitlement before entering the queue | `VerificationCase.create` (documents half); `VerificationUseCases.request_verification` (entitlement half, via the local `VerificationEligibilityRepository` projection) | `test_verification_case.py::test_I12_create_refuses_zero_documents`; `test_verification_use_cases.py::test_I12_request_verification_refused_without_active_entitlement`, `test_I12_request_verification_refused_with_expired_entitlement` |
| I-13 | A VerifiedBadge exists only from an approved case, displays only within validity, and is withdrawn on expiry | `BusinessProfile.issue_badge` (requires `ApprovedVerificationProof`); `ApprovedVerificationProof.from_case` (the sole constructor, raises `BadgeNotIssuableWithoutApprovedCaseError` unless `APPROVED`) | `test_business_profile.py::test_I13_approving_a_case_issues_the_badge`, `test_I13_no_code_path_sets_a_badge_valid_without_an_approved_case`, `test_I13_issue_badge_refuses_a_proof_for_a_different_profile`; `test_verification_use_cases.py::test_I13_decide_verification_approved_issues_badge_with_entitlement_validity`; `integration/test_repository_live.py::test_I13_full_request_approve_badge_flow_survives_real_commit`, `test_I13_negative_direct_issue_badge_attempt_refused_after_reload` |
| I-10 | Every operation is scoped to the acting profile; cross-profile access is denied by default | `_check_owner` (`ProfileUseCases`); `NotProfileOwnerError` | `test_profile_use_cases.py::test_update_profile_refuses_non_owner`; `test_verification_use_cases.py::test_request_verification_refuses_non_owner`, `test_get_current_case_refuses_non_owner`; `test_api.py::test_update_business_profile_refuses_non_owner` |
| I-24 | Moderation state changes are executed only by the owning context on command from Moderation, never by direct mutation | `interfaces/moderation_port.py::ProfileModerationPort`/`ProfilesModerationAdapter` | `test_profile_use_cases.py::test_moderation_archive_profile_needs_no_ownership_check`, `test_moderation_revoke_badge_publishes_verified_badge_expired` |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| DEC-10 | Verification documents and portfolio images are images only, no PDF/video | Enforced at media's own upload boundary (`media.interfaces.dto.MediaUploadInitRequest.content_type`'s closed image whitelist) -- `SubmittedDocument`/`PortfolioItem` hold only an already-validated `media_asset_id` | `test_verification_case.py::test_I12_create_refuses_zero_documents` (documents structurally required); images-only itself is media's own contract, not re-tested here (AIR-01) |
| DEC-13 | Manual verification, reviewer queue, SLA, badge validity, re-verification | `VerificationCase` lifecycle; `domain/policies.py::VERIFICATION_SLA_HOURS`/`compute_sla_due_at`/`order_queue` | `test_verification_use_cases.py::test_list_queue_orders_by_sla_due_at_ascending` |
| BRULE-05 | Verification target SLA is defined and monitored (design phase sets the exact value) | `domain/policies.py::VERIFICATION_SLA_HOURS = 72` (this task's own design-phase value, a fixed platform constant since profiles cannot import `configuration`) | `test_verification_use_cases.py::test_list_queue_orders_by_sla_due_at_ascending` (SLA-ordered queue) |
| Terminal-immutability (P-11 scope) | Approved/Rejected cases are TERMINAL, IMMUTABLE, and RETAINED; re-verification creates a new case | `TerminalVerificationCaseError`, guarded by every mutating `VerificationCase` method | `test_verification_case.py::test_terminal_case_cannot_be_reopened`, `test_terminal_case_cannot_be_decided_again`, `test_terminal_case_document_removal_is_a_noop_not_an_edit`, `test_reverification_creates_a_new_case_never_mutates_the_old_one` |
| X-03 | Billing entitlement events applied reactively; no synchronous billing read | `infrastructure/event_projection.py::handle_entitlement_event`; `composition_root.make_billing_entitlement_fanout_handler` | `test_verification_use_cases.py::test_apply_entitlement_projection_upserts_by_entitlement_id`; `test_boundary_import.py` (no static billing import) |
| X-06 | Media asset-status events applied reactively; owners hold MediaAssetRef only | `infrastructure/event_projection.py::handle_media_event`; `BusinessProfile.remove_portfolio_item_for_media_asset`/`VerificationCase.remove_document_for_media_asset` | `test_profile_use_cases.py::test_apply_portfolio_media_rejection_removes_the_item`; `test_verification_use_cases.py::test_apply_document_media_rejection_removes_document` |
| DB Architecture Sec 1.3 (2nd sanctioned sync exception) | State transition + outbox event append commit in ONE transaction | Every use case appends to `OutboxPort` inside the same session as its repository save | `integration/test_transactional_outbox_live.py::test_forced_failure_rolls_back_both_the_profile_and_the_outbox_row`, `test_committed_decision_and_outbox_row_both_persist` |

## Cross-context event contract

| Concern | Code | Test |
|---|---|---|
| Badge event drives search's already-built verified-badge flag | `search.infrastructure.event_projection.handle_verified_badge_applied`/`handle_verified_badge_cleared` (unmodified) | `integration/test_downstream_search_projection_live.py::test_business_verified_sets_the_verified_badge_flag_on_the_owners_listings`, `test_verification_rejected_never_sets_the_badge` |
| Only `VERIFICATION_ELIGIBILITY`-typed `EntitlementActivated`/`Expired`/`Revoked` routed to profiles' projection | `composition_root.make_billing_entitlement_fanout_handler`; `_PROFILES_RELEVANT_ENTITLEMENT_EVENT_TYPES`/`_PROFILES_RELEVANT_ENTITLEMENT_TYPES` | `apps/backend/tests/billing/integration/test_downstream_catalog_projection_live.py` (proves catalog's own routing branch is unaffected by the broadened handler) |
| Profiles has no static dependency on billing/configuration/catalog (AIR-01/SAD Sec 8.1) | `tools/importlinter.cfg`'s `cross-module-profiles` contract | `test_boundary_import.py::test_I01_cross_module_profiles_contract_currently_passes`, `test_I02_a_deliberate_forbidden_import_breaks_the_contract_then_reverts` (parametrized: billing/configuration/catalog) |

## Reviewer authorization (`listVerificationQueue`/`decideVerification`)

| Concern | Code | Test |
|---|---|---|
| `profiles:verification:review` gates both reviewer-only operations, wired end-to-end | `composition_root.provide_profiles_acting_reviewer` -> `identity.domain.AuthorizationService.authorize` | `test_api.py::test_verification_queue_refuses_non_reviewer`, `test_verification_queue_allows_reviewer`, `test_decide_verification_allows_reviewer_and_refuses_others` |
| Scenarios contributed to the shared release-blocking authorization matrix (TEST-02/QG-08) | `tests/authorization_matrix.py::PROFILES_MATRIX` (`profiles:verification:review` operator-wide; `profiles:profile:moderate` profile-scoped) | `tests/test_authorization_matrix.py::test_authorization_allow_deny_matrix` (`SCENARIOS = [*IDENTITY_MATRIX, *CATALOG_MATRIX, *BILLING_MATRIX, *PROFILES_MATRIX]`) |

## Validation checklist cross-reference (P-11 prompt)

| Checklist item | Evidence |
|---|---|
| Verified badge issued ONLY from an Approved VerificationCase, proven both directions | `test_business_profile.py::test_I13_*`; `integration/test_repository_live.py::test_I13_*` |
| Approved/Rejected cases TERMINAL, IMMUTABLE, RETAINED; re-verification creates a new case | `test_verification_case.py::test_terminal_case_*`, `test_reverification_creates_a_new_case_never_mutates_the_old_one` |
| All EIGHT profile types supported; invalid type refused | `test_business_profile.py::test_all_eight_profile_types_can_be_created` (parametrized); `test_a_ninth_invalid_profile_type_is_refused` |
| Verification gated on paid entitlement learned from billing's EVENT; no static billing import (import-linter enforced, deliberate-violation-then-revert) | `test_verification_use_cases.py::test_I12_*`; `test_boundary_import.py` |
| profiles imports ONLY shared_kernel, identity, media (import-linter enforced) | `test_boundary_import.py::test_I01_cross_module_profiles_contract_currently_passes` (parametrized violation probe: billing/configuration/catalog) |
| Badge transitions are guarded methods, no setters; each emits its event via the outbox atomically | `test_business_profile.py::test_expire_badge_*`, `test_revoke_badge_*`; `integration/test_transactional_outbox_live.py` |
| Verification documents images-only, access-restricted to authorised reviewers | Images-only enforced at media's own boundary (see README); reviewer-only queue access proven by `test_api.py::test_verification_queue_refuses_non_reviewer` (documents are only ever returned via the reviewer-gated `listVerificationQueue`/owner-scoped `getVerificationCase`, never a third surface) |
| Badge event demonstrably drives search's verified-badge flag (eventual-consistency) | `integration/test_downstream_search_projection_live.py` |
| Entitlement-event and media-status-event consumers idempotent via ProcessedEvent | `infrastructure/event_projection.py` (`idempotent_consume` wraps both handlers); exercised via the `ProcessedEventRow` ledger in `integration/` fixtures (real Postgres `INSERT ... ON CONFLICT`) |
| Moderation command port exposed on profiles' interfaces/ | `interfaces/moderation_port.py::ProfileModerationPort`/`ProfilesModerationAdapter` |
| Every profiles OpenAPI operation implemented (except the 3 team-member ones, see README "Known gaps"); contract conformance green | `test_api.py` (all 12 implemented operations exercised end-to-end via `TestClient` + `main.create_app()`); routes confirmed via `/openapi.json` introspection |
| Authorization matrix (QG-08) extended with reviewer and profile-ownership scenarios, green | `tests/authorization_matrix.py::PROFILES_MATRIX`; `tests/test_authorization_matrix.py` |
| Coverage floors met; mypy --strict/ruff/import-linter clean | See README "Coverage / quality gates": domain/application all >= 97.5%, overall (scoped) 85.12%; mypy/ruff clean (one pre-existing, repo-wide `UP042` warning shared with every module); 49/49 import-linter contracts kept |
