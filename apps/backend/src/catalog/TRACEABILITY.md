# catalog -- requirement traceability matrix (Task P-07)

Maps each requirement/invariant this module satisfies to its implementing code and the named
test that proves it. Mirrors `media/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-ADV-001 | Create a listing (draft or published) | `ListingUseCases.create_listing`; `Listing.create` | `test_listing_use_cases.py::test_create_listing_draft_does_not_publish`, `test_create_listing_with_publish_true_publishes_and_sets_expiry`; `test_api.py::test_create_listing_returns_201` |
| FR-ADV-002 | Attributes validated against the bound form version (I-07) | `catalog.domain.policies.validate_attribute_set`; `ListingUseCases.create_listing` | `test_policies.py::test_validate_attribute_set_*`; `test_listing_use_cases.py::test_create_listing_rejects_invalid_attributes` |
| FR-ADV-003 | Quota enforced at creation (I-08) | `QuotaEnforcementService.check_can_create` | `test_listing_use_cases.py::test_I08_*`; `test_quota_service.py` |
| FR-ADV-004 | First-time publication (DRAFT -> PUBLISHED) | `Listing.publish` | `test_listing.py::test_publish_twice_raises` (guard), `test_listing_use_cases.py::test_publish_listing_standalone_method` |
| FR-ADV-005 | Owner edit, transitions to EDITED, re-validates against the current form version | `Listing.edit_content`; `ListingUseCases.edit_listing` | `test_listing.py::test_I07_edit_rebinds_to_the_version_application_resolves_as_current`; `test_listing_use_cases.py::test_edit_listing_rebinds_to_current_form_version` |
| FR-ADV-006 | Configurable expiry period; scheduled expiry sweep | `CatalogExpiryWorker`; `ListingUseCases.sweep_expired`; `Listing.record_expiry` | `test_listing_use_cases.py::test_sweep_expired_publishes_exactly_once_across_two_polls`; `test_listing.py::test_record_expiry_is_idempotent_across_repeated_sweep_polls` |
| FR-ADV-007 | Renewal restores visibility, extends `expires_at` | `Listing.renew`; `ListingUseCases.change_status(action="RENEW")` | `test_listing.py::test_expiry_and_renewal_never_change_lifecycle_state`; `test_listing_use_cases.py::test_change_status_renew_extends_expiry` |
| FR-ADV-008 | Owner-permitted lifecycle transitions (suspend/archive/restore/delete), illegal transitions rejected | `Listing.suspend`/`archive`/`restore`/`delete`; `ListingUseCases.change_status` | `test_listing.py::test_I05_*`, `test_archive_*`, `test_restore_from_draft_raises`; `test_listing_use_cases.py::test_change_status_suspend_archive_restore` |
| FR-ADV-009 | Duplicate detection flags likely duplicates for moderation | `DuplicateDetectionService.is_likely_duplicate`; `catalog.domain.policies.normalize_title_for_duplicate_matching` | `test_policies.py::test_normalize_title_for_duplicate_matching_*`; `test_listing_use_cases.py::test_duplicate_detection_flags_a_repeat_title_same_owner_category` |
| FR-ADV-010 | Listing detail view (records a view metric, Analytics-owned) | `ListingUseCases.get_listing`; `interfaces/routers.py::get_listing` | `test_listing_use_cases.py::test_get_listing_not_found_raises`; `test_api.py::test_get_listing_draft_is_visible_to_its_owner` (view-metric recording itself is Analytics' own gap, see README "Known gaps" #3) |
| FR-USER-004 | Favorite a listing | `Favorite`; `FavoriteUseCases` | `test_favorite.py`; `test_favorite_use_cases.py`; `test_api.py::test_favorites_add_list_remove` |

## Domain invariants (DDD Sec 9)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-01 | `owner_user_id`/`owner_profile_id`/`category_id` fixed for life | `Listing` (no method touches them) | `test_listing.py::test_I01_owner_and_category_survive_every_transition_and_edit`, `test_I01_no_method_accepts_owner_or_category_as_a_parameter` |
| I-02 | One bound form per category | `CategoryFormPort` | `test_listing_use_cases.py::test_create_listing_no_bound_form_raises` |
| I-04 | At most 10 image attachments; quarantined assets never remain listed | `Listing.attach_image`/`update_image_status` | `test_listing.py::test_I04_eleventh_image_attachment_is_refused`, `test_I04_quarantined_asset_is_auto_detached_not_merely_flagged`, `test_I04_clean_status_update_keeps_the_attachment`, `test_I04_detach_renumbers_remaining_positions` |
| I-05 | Only legal transitions accepted; every transition recorded | Every transition method + `_record` | `test_listing.py::test_I05_illegal_transition_raises_and_leaves_state_unchanged`, `test_I05_every_transition_method_appends_exactly_one_record`, `test_I05_delete_is_terminal`, `test_I05_restore_republishes_from_suspended_or_archived` |
| I-06 | Public visibility = Published-or-Edited AND unflagged AND unexpired, one authoritative rule | `Listing.is_publicly_visible` | `test_listing.py::test_I06_*` (6 tests) |
| I-07 | Bound FormDefinitionVersion frozen at creation; edit rebinds to current | `Listing.form_definition_id`/`form_definition_version_id`; `edit_content` | `test_listing.py::test_I07_form_binding_is_fixed_at_creation`, `test_I07_edit_rebinds_to_the_version_application_resolves_as_current` |
| I-08 | Quota enforced from a locally projected subscription snapshot only; catalog never imports billing | `QuotaEnforcementService`; import-linter contracts | `test_listing_use_cases.py::test_I08_no_snapshot_means_unlimited`, `test_I08_quota_exceeded_blocks_creation`, `test_I08_personal_owner_is_never_quota_checked`; `lint-imports` (`billing-catalog-profiles-ads-no-cycle` KEPT) |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| BRULE-06 | At most 10 image attachments per listing | `catalog.domain.listing.MAX_IMAGE_ATTACHMENTS` | `test_listing.py::test_I04_eleventh_image_attachment_is_refused` |
| BRULE-07 | Listing creation beyond plan quota is refused | `QuotaEnforcementService.check_can_create` | `test_listing_use_cases.py::test_I08_quota_exceeded_blocks_creation` |
| BRULE-11 | The 11th image is rejected with 422 `IMAGE_COUNT_EXCEEDED` | `catalog.interfaces.errors.register_catalog_exception_mappings` (`ImageLimitExceededError` -> 422) | `test_listing.py::test_I04_eleventh_image_attachment_is_refused` (domain); mapping registered in `errors.py`, exercised via the same `ImageLimitExceededError` |
| BRULE-17 | Unflagged listing visible immediately on publish; flagged listing withheld | `Listing.publish` (fires regardless of `is_flagged`) + `is_publicly_visible` (I-06) | `test_listing.py::test_I06_flagged_published_listing_is_not_visible`; `test_listing_use_cases.py::test_duplicate_detection_flags_a_repeat_title_same_owner_category` |
| DEC-14 | Fixed seven-state lifecycle graph; Expired/Renewed as recorded transitions, not states | `catalog.domain.value_objects.LifecycleState`/`TransitionKind` | `test_listing.py::test_expiry_and_renewal_never_change_lifecycle_state` |
| DM-02 | AttributeSet is one typed JSONB document, EAV explicitly rejected | `ListingRow.attribute_document` (JSONB, no GIN index) | `test_models.py::test_DM02_no_eav_table_exists`, `test_no_gin_index_on_attribute_document` |
| DB Architecture Sec 1.3 | State transition + outbox write commit in one transaction (2nd sanctioned sync exception) | `SqlalchemyListingRepository.save` + `OutboxWriter.append`, same session | `integration/test_transactional_outbox_live.py::test_forced_failure_rolls_back_both_the_transition_and_the_outbox_row`, `test_successful_commit_persists_both_together` |
| Logical Sec 18 | Idempotent event consumption via ProcessedEvent ledger | `catalog.infrastructure.event_projection.handle_media_event`/`handle_entitlement_event` | `integration/test_event_projection_live.py::test_media_event_redelivery_applies_the_projection_once`, `test_entitlement_event_redelivery_upserts_the_snapshot_once` |

## Validation checklist cross-reference (P-07 prompt)

| Checklist item | Evidence |
|---|---|
| Full listing lifecycle working end-to-end (create -> publish -> edit -> transition -> expire/renew -> delete) | `test_listing_use_cases.py` (application-level), `test_api.py` (HTTP-level), `test_listing.py` (domain-level) |
| Every invariant with a passing named test | See "Domain invariants" table above |
| DM-02 rejected -- no EAV table anywhere | `test_models.py::test_DM02_no_eav_table_exists` |
| State-transition + outbox commit atomically | `integration/test_transactional_outbox_live.py` |
| AttributeSet validation engine executes configured rules only | `catalog.domain.policies.validate_attribute_set`; `test_policies.py` |
| I-04 image cap + quarantine auto-detach | `test_listing.py::test_I04_*` |
| I-06 single authoritative visibility rule | `Listing.is_publicly_visible`; `test_listing.py::test_I06_*` |
| I-07 frozen-at-creation, rebind-on-edit form binding | `test_listing.py::test_I07_*` |
| I-08 quota from projected snapshot only, no billing import | `QuotaEnforcementService`; `lint-imports` |
| BRULE-17/DEC-14 post-publication visibility | `test_listing.py::test_I06_flagged_published_listing_is_not_visible` |
| Duplicate detection flags for moderation | `test_listing_use_cases.py::test_duplicate_detection_flags_a_repeat_title_same_owner_category` |
| Favorite as a separate aggregate, unique per (user, listing) | `test_favorite.py`; `FavoriteRow.__table__` `ux_favorite_user_listing` (`test_models.py`) |
| Idempotent entitlement/media event consumers | `integration/test_event_projection_live.py` |
| API routers matching exactly the catalog-tagged OpenAPI operations | `tools/check_contract_drift.py` reports zero drift for catalog's fifteen routes |
| Alembic migrations, no GIN index on AttributeSet | `infrastructure/migrations/versions/c9f482b269ed_...py`; `test_models.py::test_no_gin_index_on_attribute_document` |
| Authorization matrix extended, not duplicated | `tests/authorization_matrix.py::CATALOG_MATRIX`; `tests/test_authorization_matrix.py::SCENARIOS = [*IDENTITY_MATRIX, *CATALOG_MATRIX]` |
| catalog imports only shared_kernel/configuration/identity/media, only their interfaces/ | `cross-module-catalog` import-linter contract (KEPT) |
| Coverage floors | `pytest --cov` -- domain 100%, application 99% (QG-04 passed; see README for the one defensible exception) |
| mypy --strict / ruff / import-linter clean | See README "Coverage / quality gates" |
