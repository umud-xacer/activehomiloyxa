# ads -- requirement traceability matrix (Task P-14)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `notifications/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-BANNER-001 | Define banner inventory/placement slots | NOT implemented here -- already served by `configuration`'s generic `/admin/config/{entityType}` operations (`entityType=placement-slot`), not `ads`'s own surface | README "ADR-0004" |
| FR-BANNER-002 | A banner campaign can be scheduled with start/end dates and priority; a campaign runs only within its schedule | `domain/value_objects.py::Schedule` (`__post_init__` ordering validation, `covers(now)`); `CampaignEligibilityPolicy.is_eligible_under_i21`'s schedule clause | `test_value_objects.py::test_schedule_rejects_end_before_start`, `test_schedule_covers_is_inclusive_start_exclusive_end`; `test_eligibility.py::test_I21_outside_schedule_window_is_not_eligible` |
| FR-BANNER-003 | Basic targeting by category, geography, and language; banners appear only in targeted contexts | `domain/value_objects.py::Targeting.matches`; `CampaignEligibilityPolicy.is_eligible_under_i21`'s targeting clause | `test_value_objects.py::test_category_targeting_requires_a_matching_category_id`, `test_geo_targeting_requires_an_exact_match`, `test_language_targeting_requires_membership`, `test_all_three_dimensions_must_match_simultaneously`; `test_eligibility.py::test_I21_targeting_mismatch_is_not_eligible` |
| FR-BANNER-004 | Serve scheduled banners in their placements; active banners display in their slots | `application/serve_use_cases.py::BannerServingUseCases.serve_banner` (highest-priority `is_servable` match) | `test_serve_use_cases.py::test_serve_banner_returns_the_single_eligible_campaign`, `test_serve_banner_selects_the_highest_priority_candidate`; `test_api.py::TestServeBanner` |
| FR-BANNER-005 | Record banner impressions and clicks | `application/serve_use_cases.py::record_impression`/`record_click` (metric events, no counters -- see README "No counters on the aggregate") | `test_serve_use_cases.py::test_record_impression_appends_a_metric_event_and_no_counter_mutation`, `test_record_click_appends_a_metric_event`; `test_api.py::TestImpressionAndClickCapture` |

## Domain invariants (DDD Sec 9/10.3)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-21 | "A BannerCampaign serves only within its schedule, matching targeting, in its configured slot, while its booking entitlement is active" -- exactly four clauses | `domain/eligibility.py::CampaignEligibilityPolicy.is_eligible_under_i21` | `test_eligibility.py::test_I21_all_four_clauses_satisfied_is_eligible`, `test_I21_outside_schedule_window_is_not_eligible`, `test_I21_targeting_mismatch_is_not_eligible`, `test_I21_wrong_slot_is_not_eligible`, `test_I21_inactive_entitlement_is_not_eligible` |
| I-20 | Media's own invariant ("quarantined assets are never delivered"), applied cross-context -- deliberately a SEPARATE gate from I-21, since I-21's own text says nothing about creative status | `domain/eligibility.py::CampaignEligibilityPolicy.is_eligible_under_i20` | `test_eligibility.py::test_I20_clean_creative_is_eligible`, `test_I20_quarantined_creative_is_not_eligible`, `test_I20_pending_creative_is_not_eligible`, `test_is_servable_fails_when_i21_holds_but_i20_does_not_even_with_active_entitlement` |
| I-23 | Engagement (impressions/clicks) is metric-event-only -- never a counter on the aggregate | `BannerCampaign` (no counter fields at all); `serve_use_cases.record_impression`/`record_click` (append-only, no state mutation) | `test_banner_campaign.py::test_no_impression_or_click_counter_fields_exist_on_the_aggregate`; `test_serve_use_cases.py::test_record_impression_appends_a_metric_event_and_no_counter_mutation` |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| BR-BAN-01 | Placements are defined and available for scheduling; active banners display in their slots | `SlotRef` (`placement_slot_id`/`placement_slot_version_id`/`slot_key`, identifier-only reference to `configuration`'s `PlacementSlotDefinition`) | `test_configuration_adapter.py` (all 3 cases) |
| BR-BAN-02 (FR-BANNER-002/003) | Campaign runs only within its schedule, with priority ordering; basic targeting | See FR-BANNER-002/003 rows above; `list_candidates_for_serve`'s priority-descending ordering | `test_serve_use_cases.py::test_serve_banner_selects_the_highest_priority_candidate` |
| BR-BAN-03/BR-ANALYTICS-01 | Impressions/clicks are counted -- via metric events consumed by `analytics` (BC-13, out of this module's scope), never a local counter | See I-23 row above | `test_banner_campaign.py::test_no_impression_or_click_counter_fields_exist_on_the_aggregate` |
| DEC-06/BRULE-20 | Physical DB Design's own correction of the SRS's counter phrasing -- `ads.banner_campaign` carries no counter columns | `infrastructure/persistence/models.py::BannerCampaignRow` (column list has no counter fields) | `test_banner_campaign.py::test_no_impression_or_click_counter_fields_exist_on_the_aggregate` (domain-level; schema-level verified by direct code review against the migration) |
| DEC-23 | `ads` is the fixed first descope candidate -- deleting it must break only its own tests/admin screens | The entire descope-seam boundary (see "Cross-context boundary" below) | `test_boundary_import.py` (all 6 tests) |
| X-06/SAD Sec 19 | Serve path is fast, never blocks on another bounded context | `BannerServingUseCases.__init__` (structurally 3 params only, no cross-module port) | `test_serve_use_cases.py::test_serve_banner_never_depends_on_a_cross_module_port` |
| ADR-0004 | `pause`/`resume` emit no domain event (not in the frozen catalogue); `end_campaign`'s operator-triggered end and the sweep worker's natural expiry emit the SAME `BannerCampaignEnded` | `domain/banner_campaign.py::pause`/`resume` (no event return); `application/campaign_use_cases.py::end_campaign`/`sweep_schedule_transitions` (both append `BannerCampaignEnded`) | `test_campaign_use_cases.py::test_pause_then_resume_before_schedule_start_returns_to_scheduled` (asserts event count unchanged), `test_end_campaign_emits_banner_campaign_ended`, `test_sweep_schedule_transitions_ends_a_due_campaign` |

## Cross-context boundary

| Concern | Code | Test |
|---|---|---|
| `ads` has no static dependency on `identity`/`profiles`/`catalog`/`search`/`messaging`/`billing`/`notifications`/`moderation`/`admin`/`analytics` -- only `shared_kernel`/`configuration`/`media` | `tools/importlinter.cfg`'s `cross-module-ads` contract | `test_boundary_import.py::test_I01_cross_module_ads_contract_currently_passes`, `test_I02_a_deliberate_billing_import_breaks_the_contract_then_reverts` |
| Nothing outside `ads` imports it -- proven distributively (every other module's own `cross-module-<module>` contract forbids `ads`), not by a single dedicated sink contract | `tools/importlinter.cfg` (every `cross-module-*` contract's forbidden-modules list; `billing-catalog-profiles-ads-no-cycle`) | `test_boundary_import.py::test_I03_billing_catalog_profiles_ads_no_cycle_contract_currently_passes`, `test_I05_no_other_module_statically_imports_ads` (repo-wide grep) |
| Clean Architecture layering (`interfaces -> application -> domain`) and no `infrastructure` inbound import | `tools/importlinter.cfg`'s `layers-ads`/`no-infra-inbound-ads` contracts | `test_boundary_import.py::test_I04_no_infra_inbound_ads_contract_currently_passes` |
| The two allowed importers (`composition_root.py`/`main.py`) do in fact import `ads` -- a mirror-image sanity check that the isolation tests above aren't vacuously passing | `composition_root.py`'s `# == ads (Task P-14) ==` section; `main.py`'s router registration | `test_boundary_import.py::test_I06_the_two_allowed_importers_do_in_fact_import_ads` |
| Billing entitlements are learned only through projected events, never a live cross-module call | `infrastructure/event_projection.py::handle_entitlement_event`; `infrastructure/persistence/models.py::EntitlementProjectionRow` | `integration/test_event_projection_live.py::test_entitlement_activated_projects_a_banner_slot_booking_entitlement`, `test_entitlement_activated_for_a_different_entitlement_type_is_ignored` |
| Only ONE dispatcher may safely drain billing's outbox -- the entitlement route is folded into the EXISTING combined handler, never a second dispatcher | `composition_root.make_billing_entitlement_fanout_handler` (extended with a 4th route, `ads_session_factory` param) | `integration/test_event_projection_live.py::test_entitlement_expired_marks_the_projection_expired`, `test_redelivering_the_same_activation_event_projects_it_exactly_once` |

## Serve-time performance discipline

| Concern | Code | Test |
|---|---|---|
| `serve_banner`/`record_impression`/`record_click` never depend on a `PlacementSlotReaderPort`/`CreativeReaderPort` -- structurally impossible for the hot path to grow a live cross-module call | `application/serve_use_cases.py::BannerServingUseCases.__init__` (3 params: `campaigns`/`entitlements`/`outbox` only) | `test_serve_use_cases.py::test_serve_banner_never_depends_on_a_cross_module_port` (via `inspect.signature`) |
| Entitlement-active and creative-clean checks at serve time read only locally cached data | `CampaignEligibilityPolicy.is_servable`, fed from `BannerCampaignRow`/`EntitlementProjectionRow` only | `test_serve_use_cases.py::test_serve_banner_returns_none_when_entitlement_is_inactive`, `test_serve_banner_returns_none_when_creative_is_quarantined` |

## Known-gap disclosures (not release-blocking, explicitly flagged)

| Concern | Rationale | Test / evidence |
|---|---|---|
| `handle_media_event` (creative-status projection) is built/tested but not wired to a live dispatcher | Media's `outbox_event` table already has no safe multi-consumer mechanism (catalog's/profiles' own equivalents are also unwired, pre-existing) -- out of this task's scope (AIR-01) | `integration/test_event_projection_live.py::test_media_asset_ready_marks_referencing_campaigns_clean`, `test_media_asset_rejected_marks_referencing_campaigns_quarantined` (both exercise the handler directly, not via a live dispatcher) |
| A pre-existing, repo-wide `MissingGreenlet` bug in `save()` across every module | Reproduced identically with `billing` alone, no `ads/` file present; already documented in `notifications/README.md` | README "Known gaps"; reproduction: `pytest apps/backend/tests/billing/integration/test_repository_live.py::test_order_save_persists_status_transitions` fails identically |
| `pytestmark` set in `conftest.py` does not propagate to sibling test files (a pytest limitation) | Reproduced identically in `billing/integration` and `notifications/integration` | README "Known gaps"; reproduction: `pytest apps/backend/tests/billing/integration -m "not integration" --collect-only` still collects all 11 tests |

## Validation checklist cross-reference (P-14 prompt)

| Checklist item | Evidence |
|---|---|
| `BannerCampaign` references slot/creative/entitlement by identifier only, never a foreign-module aggregate/row | `domain/banner_campaign.py` field list (`placement_slot_id`, `creative_media_asset_id`, `entitlement_id` -- all bare UUIDs); `tools/importlinter.cfg`'s `cross-module-ads` |
| I-21 implemented as exactly the four clauses quoted in DDD Sec 9, no invented/omitted gate | `domain/eligibility.py::is_eligible_under_i21`; `test_eligibility.py::test_I21_*` (one test per clause) |
| I-20 (creative cleanliness) enforced as a separate, correctly-attributed gate | `domain/eligibility.py::is_eligible_under_i20`; `test_eligibility.py::test_I20_*` |
| No impression/click counter anywhere -- metric events only | README "No counters on the aggregate"; `test_banner_campaign.py::test_no_impression_or_click_counter_fields_exist_on_the_aggregate`; `infrastructure/persistence/models.py` (no counter column) |
| `serveBanner` never blocks on another bounded context | `test_serve_use_cases.py::test_serve_banner_never_depends_on_a_cross_module_port` |
| Campaign lifecycle events emitted via outbox exactly as named in `contracts/events/ads.py` | `application/campaign_use_cases.py` (`BannerCampaignScheduled`/`Started`/`Ended`, all constructed from `contracts.events.ads`, no ad-hoc event shape) |
| API routers implement exactly the ads-tagged OpenAPI operations, no more/fewer | `interfaces/routers.py` (9 operations, one function per `operationId`); `test_api.py` (all 9 exercised) |
| Alembic migration for `ads.banner_campaign`, no counter columns | `infrastructure/migrations/versions/7e41075d53f8_*.py`; README "Migrations" |
| Descope seam: deleting `ads` breaks only its own tests/admin screens | `test_boundary_import.py` (all 6 tests); README "Dependencies" |
| Excluded: metric store/aggregation/reporting, billing mechanics, image processing, slot/inventory authoring, any counter column, any undocumented targeting dimension, analytics projections, admin portal | Not implemented anywhere in this module -- verified by absence, not a passing test |
| Missing OpenAPI endpoints surfaced as an architecture decision, not silently worked around | `docs/adr/0004-ads-openapi-endpoints.md`; README "ADR-0004" |
| Coverage floors met; mypy/ruff/import-linter clean | See README "Coverage / quality gates": domain/application both 100%, overall (full suite) 88.77%; mypy/ruff clean; 49/49 import-linter contracts kept |
