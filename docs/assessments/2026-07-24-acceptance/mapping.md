# Acceptance-pack mapping (Task P-20)

Maps every SRS `FR-*` requirement (and its 1:1-paired `TC-*` test case -- the SRS's own text traces each as `FR-XXX-NNN → TC-XXX-NNN`, confirmed for all 89 ids, no exceptions) and every `NFR-*` to the test(s) that cover it. See `gap_report.md` (sibling file) for the honest accounting of what this mapping found -- read that file first if you only have time for one.

**Status legend**: `NAME-TRACED` -- a test literally named `test_FR_<id>_*` per the Playbook's own convention. `FUNCTIONAL (best-effort)` -- a real, verified-to-exist test was found covering the requirement's behaviour, but not name-traced to the FR id (see the gap report's naming-convention finding). `PARTIAL` -- the backend half is tested but a UI-facing half of the requirement has nothing to test against yet (no frontend). `GAP` -- no plausible covering test found after a targeted search.

## Functional requirements (FR-* / TC-*)

| FR id | TC id | Requirement | Status | Covering test / note |
|---|---|---|---|---|
| FR-ADMIN-001 | TC-ADMIN-001 | Manage users & companies | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_admin_use_cases.py (`AdminIdentityUseCases` suspend/reactivate/list/role-assign -- admin's user-management operation delegates to identity's own router, P-16) |
| FR-ADMIN-002 | TC-ADMIN-002 | Manage verification queue | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/test_verification_use_cases.py (admin's decideVerification delegates to profiles' own decide_verification -- Task P-16 confirmed this operation lives on profiles' router, not admin's) |
| FR-ADMIN-003 | TC-ADMIN-003 | Manage subscriptions & billing | FUNCTIONAL (best-effort) | apps/backend/tests/billing/test_api.py (admin's billing/subscription views delegate to billing's own routers -- P-16) |
| FR-ADMIN-004 | TC-ADMIN-004 | Manage banner campaigns | FUNCTIONAL (best-effort) | apps/backend/tests/ads/test_campaign_use_cases.py (admin's banner-campaign management delegates to ads' own router -- P-16) |
| FR-ADMIN-005 | TC-ADMIN-005 | Reports | FUNCTIONAL (best-effort) | apps/backend/tests/analytics/test_report_use_cases.py (getAdminReports delegates to analytics' own use case -- P-16) |
| FR-ADMIN-006 | TC-ADMIN-006 | Role & permission management | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_admin_use_cases.py / test_authorization.py (role/permission management is identity+configuration's own surface -- P-16) |
| FR-ADV-001 | TC-ADV-001 | Create listing | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-ADV-002 | TC-ADV-002 | Attach images | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-ADV-003 | TC-ADV-003 | Save draft | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/integration/test_repository_live.py |
| FR-ADV-004 | TC-ADV-004 | Publish listing (post-publication moderation) | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-ADV-005 | TC-ADV-005 | Edit listing | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-ADV-006 | TC-ADV-006 | Lifecycle transitions | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing.py |
| FR-ADV-007 | TC-ADV-007 | Expiry & renewal | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-ADV-008 | TC-ADV-008 | Quotas & limits | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_quota_service.py |
| FR-ADV-009 | TC-ADV-009 | Duplicate detection | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-ADV-010 | TC-ADV-010 | View listing detail | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-ANALYTICS-001 | TC-ANALYTICS-001 | Capture performance metrics | FUNCTIONAL (best-effort) | apps/backend/tests/analytics/test_metric_event.py |
| FR-ANALYTICS-002 | TC-ANALYTICS-002 | Listing statistics to owners | FUNCTIONAL (best-effort) | apps/backend/tests/analytics/integration/test_repository_live.py |
| FR-AUDIT-001 | TC-AUDIT-001 | Administrative & moderation audit | FUNCTIONAL (best-effort) | apps/backend/tests/analytics/test_report_use_cases.py |
| FR-AUDIT-002 | TC-AUDIT-002 | Audit review | FUNCTIONAL (best-effort) | apps/backend/tests/analytics/integration/test_event_projection_live.py |
| FR-AUTH-001 | TC-AUTH-001 | Registration via phone | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_auth_use_cases.py |
| FR-AUTH-002 | TC-AUTH-002 | Registration via email | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_auth_use_cases.py |
| FR-AUTH-003 | TC-AUTH-003 | Federated sign-in (Google) | FUNCTIONAL (best-effort) | apps/backend/tests/identity/integration/test_repository_live.py |
| FR-AUTH-004 | TC-AUTH-004 | Authentication (login) | FUNCTIONAL (best-effort) | apps/backend/tests/identity/integration/test_repository_live.py |
| FR-AUTH-005 | TC-AUTH-005 | Session management | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_auth_use_cases.py |
| FR-AUTH-006 | TC-AUTH-006 | Credential recovery | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_auth_use_cases.py |
| FR-BANNER-001 | TC-BANNER-001 | Define banner inventory | FUNCTIONAL (best-effort) | apps/backend/tests/ads/test_campaign_use_cases.py |
| FR-BANNER-002 | TC-BANNER-002 | Schedule campaign | FUNCTIONAL (best-effort) | apps/backend/tests/ads/test_campaign_use_cases.py |
| FR-BANNER-003 | TC-BANNER-003 | Basic targeting | FUNCTIONAL (best-effort) | apps/backend/tests/ads/test_campaign_use_cases.py |
| FR-BANNER-004 | TC-BANNER-004 | Serve banners | FUNCTIONAL (best-effort) | apps/backend/tests/ads/integration/test_repository_live.py |
| FR-BANNER-005 | TC-BANNER-005 | Track impressions & clicks | FUNCTIONAL (best-effort) | apps/backend/tests/ads/test_banner_campaign.py, test_serve_use_cases.py (impression/click MetricEvent capture) |
| FR-BILL-001 | TC-BILL-001 | Generate invoice | FUNCTIONAL (best-effort) | apps/backend/tests/billing/integration/test_repository_live.py |
| FR-BILL-002 | TC-BILL-002 | Confirm offline payment | FUNCTIONAL (best-effort) | apps/backend/tests/billing/integration/test_repository_live.py |
| FR-BILL-003 | TC-BILL-003 | Billing status & reconciliation | FUNCTIONAL (best-effort) | apps/backend/tests/billing/test_entitlement.py, integration/test_repository_live.py |
| FR-BILL-004 | TC-BILL-004 | No online payment in v1 (constraint statement) | FUNCTIONAL (best-effort) | apps/backend/tests/billing/integration/test_repository_live.py |
| FR-CAT-001 | TC-CAT-001 | Browse categories | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_category_read.py |
| FR-CAT-002 | TC-CAT-002 | Category-field association | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_content_models.py |
| FR-CFG-001 | TC-CFG-001 | Configure taxonomy | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_taxonomy.py |
| FR-CFG-002 | TC-CFG-002 | Configure forms & fields | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_content_models.py (FormDefinition) |
| FR-CFG-003 | TC-CFG-003 | Configure validation, filters, sorting | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_head_version.py |
| FR-CFG-004 | TC-CFG-004 | Configure commercial products | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_entity_types.py (ProductDefinition) |
| FR-CFG-005 | TC-CFG-005 | Configure platform settings | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_content_models.py |
| FR-FORM-001 | TC-FORM-001 | Render dynamic form | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_content_models.py |
| FR-FORM-002 | TC-FORM-002 | Validate submissions | FUNCTIONAL (best-effort) | apps/backend/tests/configuration/test_content_models.py |
| FR-LOC-001 | TC-LOC-001 | Multilingual interface | PARTIAL | backend LocalizedText storage/validation tested (configuration/test_content_models.py); the UI-facing 'interface' half is blocked on no-frontend-yet -- same root cause as the AC-UI gap below, not a backend defect |
| FR-LOC-002 | TC-LOC-002 | Any-language content | FUNCTIONAL (best-effort) | apps/backend/tests/search/integration/test_opensearch_index_live.py |
| FR-MAP-001 | TC-MAP-001 | Set listing location | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_listing_use_cases.py |
| FR-MAP-002 | TC-MAP-002 | Map display | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_configuration_adapter.py |
| FR-MAP-003 | TC-MAP-003 | Radius search | FUNCTIONAL (best-effort) | apps/backend/tests/search/integration/test_opensearch_index_live.py |
| FR-MEDIA-001 | TC-MEDIA-001 | Image upload & validation | FUNCTIONAL (best-effort) | apps/backend/tests/media/integration/test_repository_live.py |
| FR-MEDIA-002 | TC-MEDIA-002 | Reject non-image media | FUNCTIONAL (best-effort) | apps/backend/tests/media/test_intake_use_cases.py |
| FR-MEDIA-003 | TC-MEDIA-003 | Metadata stripping | NAME-TRACED | apps/backend/tests (grep test_FR_MEDIA_003) |
| FR-MEDIA-004 | TC-MEDIA-004 | Malware scanning | FUNCTIONAL (best-effort) | apps/backend/tests/media/test_malware_scan.py |
| FR-MEDIA-005 | TC-MEDIA-005 | Image delivery | NAME-TRACED | apps/backend/tests (grep test_FR_MEDIA_005) |
| FR-MOD-001 | TC-MOD-001 | Report listing | FUNCTIONAL (best-effort) | apps/backend/tests/moderation/test_moderation_case.py |
| FR-MOD-002 | TC-MOD-002 | Automated validation flags | FUNCTIONAL (best-effort) | apps/backend/tests/moderation/test_moderation_case.py |
| FR-MOD-003 | TC-MOD-003 | Moderator actions | FUNCTIONAL (best-effort) | apps/backend/tests/moderation/test_api.py |
| FR-MOD-004 | TC-MOD-004 | Account suspension | FUNCTIONAL (best-effort) | apps/backend/tests/moderation/integration/test_account_suspension_compensation_live.py |
| FR-MOD-005 | TC-MOD-005 | Moderation queue | FUNCTIONAL (best-effort) | apps/backend/tests/moderation/test_api.py |
| FR-MSG-001 | TC-MSG-001 | Initiate chat | FUNCTIONAL (best-effort) | apps/backend/tests/messaging/test_conversation_use_cases.py |
| FR-MSG-002 | TC-MSG-002 | Real-time messaging | FUNCTIONAL (best-effort) | apps/backend/tests/messaging/test_api.py |
| FR-MSG-003 | TC-MSG-003 | Click-to-call / phone reveal | FUNCTIONAL (best-effort) | apps/backend/tests/messaging/test_api.py |
| FR-MSG-004 | TC-MSG-004 | Block | FUNCTIONAL (best-effort) | apps/backend/tests/messaging/integration/test_repository_live.py |
| FR-MSG-005 | TC-MSG-005 | Report conversation/user | FUNCTIONAL (best-effort) | apps/backend/tests/messaging/test_report_use_cases.py |
| FR-NOTIF-001 | TC-NOTIF-001 | Email notifications | FUNCTIONAL (best-effort) | apps/backend/tests/notifications/test_providers.py |
| FR-NOTIF-002 | TC-NOTIF-002 | Web-push notifications | FUNCTIONAL (best-effort) | apps/backend/tests/notifications/test_dispatch_use_cases.py |
| FR-NOTIF-003 | TC-NOTIF-003 | SMS OTP | FUNCTIONAL (best-effort) | apps/backend/tests/notifications/test_dispatch_use_cases.py |
| FR-NOTIF-004 | TC-NOTIF-004 | Notification preferences | FUNCTIONAL (best-effort) | apps/backend/tests/notifications/test_dispatch_use_cases.py |
| FR-PROF-001 | TC-PROF-001 | Create business profile | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/test_verification_case.py |
| FR-PROF-002 | TC-PROF-002 | Maintain company page & portfolio | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/test_business_profile.py, test_profile_use_cases.py |
| FR-PROF-003 | TC-PROF-003 | Submit verification documents | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/integration/test_downstream_search_projection_live.py |
| FR-PROF-004 | TC-PROF-004 | Request verification | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/integration/test_downstream_search_projection_live.py |
| FR-PROF-005 | TC-PROF-005 | Process verification (reviewer) | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/integration/test_downstream_search_projection_live.py |
| FR-PROF-006 | TC-PROF-006 | Display verified badge | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/integration/test_downstream_search_projection_live.py |
| FR-PROF-007 | TC-PROF-007 | Re-verification on expiry | FUNCTIONAL (best-effort) | apps/backend/tests/profiles/integration/test_downstream_search_projection_live.py |
| FR-SRCH-001 | TC-SRCH-001 | Full-text search | FUNCTIONAL (best-effort) | apps/backend/tests/search/integration/test_opensearch_index_live.py |
| FR-SRCH-002 | TC-SRCH-002 | Faceted filtering | FUNCTIONAL (best-effort) | apps/backend/tests/search/test_search_use_cases.py, test_opensearch_index.py (facets) |
| FR-SRCH-003 | TC-SRCH-003 | Sorting | FUNCTIONAL (best-effort) | apps/backend/tests/search/test_search_use_cases.py (SortOption) |
| FR-SRCH-004 | TC-SRCH-004 | Cross-script matching | FUNCTIONAL (best-effort) | apps/backend/tests/search/integration/test_opensearch_index_live.py |
| FR-SRCH-005 | TC-SRCH-005 | Promoted result labelling & capping | FUNCTIONAL (best-effort) | apps/backend/tests/search/integration/test_opensearch_index_live.py |
| FR-SUBS-001 | TC-SUBS-001 | Browse products & plans | FUNCTIONAL (best-effort) | apps/backend/tests/billing/test_entitlement.py |
| FR-SUBS-002 | TC-SUBS-002 | Purchase request | FUNCTIONAL (best-effort) | apps/backend/tests/billing/integration/test_repository_live.py |
| FR-SUBS-003 | TC-SUBS-003 | Entitlement activation | FUNCTIONAL (best-effort) | apps/backend/tests/billing/integration/test_repository_live.py |
| FR-SUBS-004 | TC-SUBS-004 | Entitlement expiry | FUNCTIONAL (best-effort) | apps/backend/tests/billing/integration/test_repository_live.py |
| FR-USER-001 | TC-USER-001 | Manage personal profile | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_session.py |
| FR-USER-002 | TC-USER-002 | Multiple business profiles | FUNCTIONAL (verified, cross-module) | tests/integration/test_profiles_creation_links_identity_owned_profile.py -- proves `switchActingProfile` against a business profile created moments earlier through the real `profiles.createBusinessProfile` -> `BusinessProfileCreated` -> `handle_profiles_event` chain (a real gap here was found and fixed during P-20, see gap_report.md Finding 5) |
| FR-USER-003 | TC-USER-003 | Privacy settings (contact visibility) | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_account_use_cases.py |
| FR-USER-004 | TC-USER-004 | Manage favorites | FUNCTIONAL (best-effort) | apps/backend/tests/catalog/test_favorite_use_cases.py -- NOTE: FR-USER-004 lives under the USER prefix but favorites are catalog's own aggregate (DDD Sec 5.3), a prefix/module mismatch worth flagging, not a coverage gap |
| FR-USER-005 | TC-USER-005 | Account closure & data request | FUNCTIONAL (best-effort) | apps/backend/tests/identity/test_auth_use_cases.py |

## Non-functional requirements (NFR-*)

The SRS does not pair NFR ids with a `TC-*` (they trace to `QR-*` source ids instead, not a
test-case id) -- each is listed with its own direct covering-test citation.

| NFR id | Requirement | Status | Covering test / note |
|---|---|---|---|
| NFR-PERF-001 | Search p95 ≤ 500ms | GAP | No load/perf harness exists yet -- explicitly P-21's scope (CLAUDE.md: "performance tuning (P-21)"), not this task's. |
| NFR-PERF-002 | Interactive p95 ≤ 300ms | GAP | Same as NFR-PERF-001 -- P-21 scope. |
| NFR-SCALE-001 | 10k users / 100k listings / 2k concurrent | GAP | Load-testing scope (P-21); `deployment/loadtest*` compose files exist but no assertion suite runs them as part of this task. |
| NFR-SCALE-002 | Growth headroom to 100k/1M/10k | GAP | Same as NFR-SCALE-001 -- a capacity-planning claim, not something a test proves. |
| NFR-AVAIL-001 | 99.x% availability target | GAP | Production monitoring/SLO concern, not a backend test-suite assertion. |
| NFR-REL-001 | RPO ≤15min / RTO ≤4h | GAP | DR-drill/infra concern (P-22/deployment scope). |
| NFR-REL-002 | Graceful degradation (search fallback, non-blocking media, chat→click-to-call) | **COVERED (P-20)** | `tests/degradation/test_search_opensearch_down_falls_back_to_postgres.py`, `tests/degradation/test_catalog_publish_not_blocked_by_media_lag.py`. Chat-unavailability→click-to-call degradation has no covering test -- see gap report. |
| NFR-MAINT-001 | Config changes take effect with no redeploy | **COVERED (P-20)** | `tests/integration/test_config_publish_propagates_without_redeploy.py` (catalog/billing/search/notifications/identity, all 5 proven in-process). |
| NFR-SEC-001 | Default-deny authorization | **COVERED (P-20)** | `tests/authorization/` (consolidated matrix + `test_no_route_grants_access.py`, 88 secured operations). |
| NFR-SEC-002 | Encryption in transit/at rest | GAP | TLS/infra config audit, not a backend test-suite assertion -- P-22 security-hardening scope. |
| NFR-SEC-003 | Upload validation, reject non-image/malicious files | FUNCTIONAL (best-effort) | `apps/backend/tests/media/test_malware_scan.py`, `test_intake_use_cases.py`. |
| NFR-SEC-004 | OTP throttling / rate-limiting | FUNCTIONAL (best-effort) | `apps/backend/tests/identity/test_auth_use_cases.py`, `test_policies.py`. |
| NFR-SEC-005 | Anti-scraping / bot mitigation | GAP | No implementation found (edge/nginx concern) -- P-22 scope. |
| NFR-USE-001 | First-time user completes registration→publish unassisted | PARTIAL | The backend-capability half is what the E2E critical-journey suite (`tests/e2e/`) is meant to prove; true "unassisted" usability needs a UI, which doesn't exist yet. |
| NFR-ACC-001 | WCAG 2.x accessibility | GAP | No frontend exists -- same root cause as AC-UI below. |
| NFR-LOC-001 | uz/ru/en operation + Uzbek Latin↔Cyrillic cross-script search | FUNCTIONAL (best-effort) | `apps/backend/tests/search/` cross-script matching tests, `configuration/test_content_models.py` (`LocalizedText`). UI-facing language-switching half not testable without a frontend. |
| NFR-BAK-001 | Automated backups + restorability tests | GAP | Infra/ops concern, not a backend test-suite assertion. |
| NFR-REC-001 | DR recovery within NFR-REL-001's RPO/RTO | GAP | Same as NFR-REL-001 -- infra/ops, not backend-testable. |
| NFR-LOG-001 | Structured logs + audit trail retention | FUNCTIONAL (best-effort) | `apps/backend/tests/backbone/` structured-logging tests (P-03); `apps/backend/tests/analytics/` `AuditEntry` immutability tests (P-15). |
| NFR-PRIV-001 | EXIF/GPS strip, contact-reveal gating, data-subject requests | FUNCTIONAL (best-effort) | `apps/backend/tests/media/` EXIF-strip tests; `apps/backend/tests/messaging/` phone-reveal gating tests; `apps/backend/tests/identity/test_auth_use_cases.py` (account closure/data export). |
| NFR-CFG-001 | Bounded configurability (whitelist-only field types/validators/permissions) | FUNCTIONAL (best-effort) | `apps/backend/tests/configuration/test_whitelist.py`. |

**NFR summary: 8 COVERED/FUNCTIONAL-plus-P-20, 2 PARTIAL, 11 GAP** -- every GAP here is an
infra/ops/load-testing/frontend concern explicitly out of this task's scope (P-21 performance
tuning, P-22 security hardening, or "no frontend scaffolded yet"), not a backend logic defect.

## Acceptance Criteria (ETT Sec 16/17) -- dimension-level, not per-id

The ETT does not define ~26 independent fine-grained AC ids. It defines **six generic dimensions**
(`AC-FUNC`/`AC-UI`/`AC-API`/`AC-TEST`/`AC-DOC`/`AC-DEPLOY`) applied once per module (13 modules ×
6 = 78 module-level instances), a platform-level dimension, and a separate `AC-1`..`AC-8` set that
is actually about the **SRS document's own quality** ("every requirement has a unique ID...",
ETT §16 cross-referencing SRS §12) -- not testable system behaviour, so excluded below.

| Dimension | Applies to | Status | Note |
|---|---|---|---|
| AC-FUNC | all 13 modules | MET | All 13 bounded contexts implemented (P-04..P-16); invariant (`I-nn`) tests exist per module. |
| AC-API | all 13 modules | MET | Every module's OpenAPI operations implemented; QG-06 contract-drift check + QG-08 consolidated authorization matrix both green. |
| AC-TEST | all 13 modules | MET (per-module) / **this task extends it cross-module** | Module-local unit/integration/API suites all green; P-20 adds the cross-cutting eventual-consistency/degradation/idempotency/E2E layer no single module's own suite could prove. |
| AC-DOC | all 13 modules | MET | Every module has a README (module charter); `tests/README.md`/`contracts/README.md` current. |
| AC-DEPLOY | all 13 modules | **NOT VERIFIED** | "Runs in staging within the full stack" -- no staging deployment/CD pipeline exists yet (only `.github/workflows/ci.yml`, no `cd.yml`). Ephemeral CI service containers (this task's `qg03b-full-stack-e2e` job) approximate the full-stack-runs claim but are not a staging deploy. |
| AC-UI | all 13 modules | **UNMET** | No frontend is scaffolded (`apps/frontend` is a placeholder, Task P-00) -- stated plainly, not hedged. Every module fails this dimension identically for the same reason. |
| Platform-level (NFR verifications, §5) | platform | PARTIAL | See the NFR table above -- 11 of 21 NFRs are GAP, mostly infra/load-testing/frontend concerns outside P-20's mandate. |

