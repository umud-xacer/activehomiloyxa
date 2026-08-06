# analytics -- requirement traceability matrix (Task P-15)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `ads/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-ANALYTICS-001 | Capture advertisement views, contact-button clicks, phone-reveal clicks, chat initiations, favorites, premium-ad statistics, banner impressions/clicks -- each metric recorded on its corresponding event | `application/metric_use_cases.py::record_metric`; `infrastructure/event_projection.py` (8 handler functions) | `test_value_objects.py::test_closed_vocabulary_accepts_exactly_the_eight_approved_keys`; `integration/test_event_projection_live.py::test_I23_*` (one per family) |
| FR-ANALYTICS-002 | Present basic performance statistics to listing owners | `application/metric_use_cases.py::get_listing_statistics`/`rebuild_listing_statistics` | `test_metric_use_cases.py::test_record_metric_advances_the_listing_statistics_projection`, `test_rebuild_listing_statistics_reconstructs_the_projection_identically` |
| FR-AUDIT-001 | Record an auditable entry (actor, action, target, time) for every administrative and moderation action | `domain/audit_entry.py::AuditEntry.create`; `application/audit_use_cases.py::record_audit_fact` | `test_audit_entry.py::test_create_populates_every_field`; `integration/test_event_projection_live.py::test_I22_*` (5 audit families) |
| FR-AUDIT-002 | Allow authorised administrators to view audit logs, viewable and filterable | `application/audit_use_cases.py::query_audit_log`; `interfaces/routers.py::query_audit_log` | `test_audit_use_cases.py::test_query_audit_log_filters_by_action`, `test_query_audit_log_filters_by_date_range`; `test_api.py::TestQueryAuditLog` |
| FR-ADMIN-005 | Provide administrators basic operational reports (activity and the v1 metric set) | `application/report_use_cases.py::get_admin_reports` (5 fixed report keys) | `test_report_use_cases.py` (all 5 reports); `test_api.py::TestGetAdminReports` |
| FR-ADV-010 | View listing detail records a view event | `contracts/events/catalog.py::ListingViewed` (ADR-0005); `infrastructure/event_projection.py::handle_catalog_event`'s `ListingViewed` route | `integration/test_event_projection_live.py::test_I23_listing_viewed_is_idempotent`; README "ADR-0005" for the producer-side gap |

## Domain invariants (DDD Sec 9/10.3)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-22 | "Every administrative, moderation, and configuration action yields an immutable AuditEntry (actor, action, target, time)" | `domain/audit_entry.py::AuditEntry` (immutable, `__setattr__`/`__delattr__` override); `infrastructure/event_projection.py` (5 audit-producing handlers) | `test_audit_entry.py::test_I22_attribute_assignment_is_rejected`/`test_I22_attribute_deletion_is_rejected` (domain level); `integration/test_repository_live.py::test_I22_the_database_rejects_an_update_to_a_stored_audit_entry`/`test_I22_the_database_rejects_a_delete_of_a_stored_audit_entry` (DB level); `integration/test_event_projection_live.py::test_I22_*` (coverage, 5 families) |
| I-23 | "Only the closed v1 metric vocabulary is captured; each metric records exactly once per triggering event" | `domain/value_objects.py::ClosedVocabularyPolicy`/`MetricKey`; `domain/metric_event.py::MetricEvent` (immutable); `infrastructure/event_projection.py` (idempotent_consume, 3 metric-producing handlers covering 8 keys) | `test_value_objects.py::test_closed_vocabulary_rejects_anything_outside_the_eight_keys` (the module's signature test); `test_metric_event.py::test_I23_attribute_assignment_is_rejected`/`test_I23_attribute_deletion_is_rejected` (domain-level immutability); `integration/test_repository_live.py::test_I23_the_database_rejects_an_update_to_a_stored_metric_event`/`test_I23_the_database_rejects_a_delete_of_a_stored_metric_event` (DB-level immutability); `integration/test_event_projection_live.py::test_I23_*` (idempotency, all 8 families) |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| BRULE-20/DEC-06 | Advanced analytics/BI is out of scope for v1 -- the metric vocabulary is closed, not merely "the metrics we happen to capture today" | `domain/value_objects.py::MetricKey` (exactly 8 members); `application/report_use_cases.py` (exactly 5 fixed report keys, `UnknownReportError` on anything else) | `test_value_objects.py::test_closed_vocabulary_accepts_exactly_the_eight_approved_keys`; `test_report_use_cases.py::test_unknown_report_raises` |
| Physical DB Sec 3.12 (no counters on the fact stores) | `AuditEntry`/`MetricEvent` carry no counter fields at all -- counters live only in the separate, rebuildable `ListingStatistics` projection | `domain/audit_entry.py`/`domain/metric_event.py` (field lists have no counter) | Verified by direct inspection of the dataclass field lists; `infrastructure/persistence/models.py`'s own column lists mirror this |
| Physical DB Sec 2.13 (no `outbox_event` table for analytics) | `MetricEventCaptured`/`AuditEntryRecorded` are in-process ingestion signals, not outbox-dispatched events -- the projection update happens in the SAME call as the fact append, never a second async hop | `application/metric_use_cases.py::record_metric` (appends fact + advances projection in one call) | `test_metric_use_cases.py::test_record_metric_advances_the_listing_statistics_projection` |
| DB Architecture Sec 3.12 (projections are rebuildable, not aggregates) | Discard `ListingStatistics`, replay the `MetricEvent` stream, reconstruct identically | `application/metric_use_cases.py::rebuild_listing_statistics` | `test_metric_use_cases.py::test_rebuild_listing_statistics_reconstructs_the_projection_identically`, `test_rebuild_listing_statistics_on_an_empty_stream_leaves_no_rows` |
| Physical DB Sec 2/Sec 16 (time partitioning) | `audit_entry`/`metric_event` are monthly RANGE-partitioned; a partition-precreate job keeps future months ready | `infrastructure/migrations/versions/d8ee38154c92_*.py` (raw DDL, initial partitions); `infrastructure/partition_worker.py::PartitionPrecreateWorker`; `backbone/migrations/partitioning.py` (new, reusable DDL generator) | `integration/test_migration_smoke.py` (migration-time partitions + guard triggers exist); `integration/test_partition_worker_live.py` (worker creates a far-future month's partition, idempotently) |
| PD-07 (immutability guard triggers) | Guard triggers reject UPDATE/DELETE unconditionally on both fact tables | `infrastructure/migrations/versions/d8ee38154c92_*.py` (`backbone.migrations.guard_trigger_ddl` applied to both tables) | `integration/test_repository_live.py::test_I22_the_database_rejects_*`/`test_I23_the_database_rejects_*` |

## Cross-context boundary

| Concern | Code | Test |
|---|---|---|
| `analytics` has no static dependency on any other module -- `shared_kernel` ONLY, stricter than most modules | `tools/importlinter.cfg`'s `cross-module-analytics` contract (frozen since P-01) | `test_boundary_import.py::test_I01_cross_module_analytics_contract_currently_passes`, `test_I03_a_deliberate_forbidden_import_breaks_the_contract_then_reverts` (parametrized across all 12 forbidden modules) |
| Nothing imports analytics -- a terminal sink, same class as admin/notifications | `tools/importlinter.cfg`'s `sink-modules-have-no-inbound-imports` contract | `test_boundary_import.py::test_I02_sink_modules_have_no_inbound_imports_contract_currently_passes`, `test_I05_no_other_module_statically_imports_analytics` (repo-wide grep) |
| No inbound command port exists for another module to call ("record a metric") | `interfaces/ports.py::AnalyticsQueryPort` (2 read-only methods only) | `test_boundary_import.py::test_I04_no_inbound_command_port_exists_for_other_modules_to_call` |
| Analytics never dereferences a ref by calling another module -- every stored field comes from the triggering event's own payload | `infrastructure/event_projection.py` (all 8 handlers read only `envelope.payload`/`envelope.actor`) | Direct code inspection; `test_boundary_import.py`'s own import restriction makes a dereferencing call structurally impossible to write |
| Every already-multi-consumer outbox (billing/catalog/identity/messaging/profiles/moderation) gains an analytics route folded into its EXISTING combined dispatcher, never a second competing one | `composition_root.make_billing_entitlement_fanout_handler`/`make_catalog_outbox_fanout_handler`/`make_identity_account_status_projection_handler`/`make_messaging_report_projection_handler`/`make_profiles_notification_projection_handler`/`make_moderation_notification_projection_handler` (all extended, not duplicated) | `integration/test_event_projection_live.py` (per-emitting-module positive cases); README "Events" table |
| Configuration's and ads' own outboxes get their first-ever dispatcher, both dedicated to analytics | `composition_root.provide_analytics_configuration_projection_dispatcher`/`provide_analytics_ads_projection_dispatcher`; `analytics_worker.py` | `integration/test_event_projection_live.py::test_I22_a_configuration_publish_produces_an_audit_entry`, `test_I23_banner_impression_recorded_is_idempotent`/`test_I23_banner_click_recorded_is_idempotent` |
| Idempotent event consumption via `ProcessedEvent`, one handler name per emitting module | `infrastructure/event_projection.py` (`idempotent_consume` wraps each of the 8 handlers under a distinct name) | `integration/test_event_projection_live.py::test_I23_*`/`test_I22_*` (redelivery cases); `test_redelivering_the_same_event_across_different_handlers_is_independent` |

## `getListingStatistics` is deliberately NOT this module's endpoint

| Concern | Rationale | Evidence |
|---|---|---|
| `/listings/{listingId}/statistics` stays `catalog`'s own router, permanently partial | Tagged `Listings`, not `Administration` -- `contracts/README.md`'s P-01 tag-routing rule already assigned it to `catalog`; `catalog`'s router hardcodes `null` for the analytics-owned fields with no injection point at all; closing this needs a `catalog`-module change, out of P-15's declared scope (AIR-01) | README "Known gaps"; `catalog/interfaces/routers.py::get_listing_statistics` (unmodified by this task) |
| Owner-only access to a listing's own statistics IS already proven | `catalog`'s own, already-existing test | `apps/backend/tests/catalog/test_api.py::test_get_listing_statistics_owner_only` (pre-existing, not duplicated here) |

## Validation checklist cross-reference (P-15 prompt)

| Checklist item | Evidence |
|---|---|
| Exactly the 8 closed-vocabulary keys accepted; any other key rejected with a typed exception, never stored/dropped/bucketed | `test_value_objects.py::test_closed_vocabulary_rejects_anything_outside_the_eight_keys`; `integration/test_repository_live.py::test_closed_vocabulary_check_constraint_rejects_an_unknown_metric_key` |
| Metric writes idempotent on the triggering event id, proven for every metric family | `integration/test_event_projection_live.py::test_I23_listing_viewed_is_idempotent` through `test_I23_banner_click_recorded_is_idempotent` (8 tests) |
| AuditEntry/MetricEvent append-only and immutable -- UPDATE/DELETE rejected at BOTH domain and database level | `test_audit_entry.py`/`test_metric_event.py` (domain); `integration/test_repository_live.py::test_I22_the_database_rejects_*`/`test_I23_the_database_rejects_*` (database) |
| Every configuration publish audited; moderation actions, payment confirmations, verification decisions, account suspensions all produce audit facts | `integration/test_event_projection_live.py::test_I22_*` (5 tests, one per family) |
| Projections rebuildable from the fact streams, carry provenance | `test_metric_use_cases.py::test_rebuild_listing_statistics_reconstructs_the_projection_identically`; `ListingStatisticsSnapshot.as_of_position`/`analytics.projection_checkpoint` |
| analytics imports ONLY shared_kernel; nothing imports analytics (verified with a deliberate violation, then reverted) | `test_boundary_import.py::test_I01`/`test_I03` (parametrized deliberate-violation-then-revert) |
| Analytics never dereferences a ref by calling another module | README "No-dereference guarantee"; `infrastructure/event_projection.py` (payload-only field sourcing) |
| Audit payloads carry safe identifiers, not raw PII; no PII in logs | `domain/audit_entry.py::AuditEntry` (bare UUID/str fields only, no email/phone anywhere in any handler's payload construction); no logging statements exist anywhere in this module that could leak payload contents |
| Fact tables time-partitioned per the Physical DB Design; partition-precreate job runs | `integration/test_migration_smoke.py`; `integration/test_partition_worker_live.py` |
| No Phase-2 analytics dashboard or recommendation feature built | Not implemented anywhere in this module -- verified by absence, not a passing test |
| Every analytics OpenAPI operation implemented; authorization matrix extended (own-statistics-only is catalog's, not duplicated; operator-only audit/reports, two DIFFERENT permissions) | `test_api.py` (both operations, incl. the cross-permission-denial cases) |
| Coverage floors met; mypy --strict/ruff/import-linter clean | See README "Coverage / quality gates": domain 100%, application 96.9-100%, overall (full suite) 92.19%; mypy/ruff clean; 49/49 import-linter contracts kept |
