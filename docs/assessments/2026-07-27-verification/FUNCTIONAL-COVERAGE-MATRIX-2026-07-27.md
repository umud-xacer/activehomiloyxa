# Active Home v1 — Functional Coverage Matrix (2026-07-27)

Every documented functionality, whether or not it was tested. Baseline `origin/main` @ `e1ec08b`.
Evidence refs are files in `docs/assessments/2026-07-27-verification/evidence/`; `res_*.json` entries carry the check id,
the cited document, the expected result and the raw observed response.

Classification: **WORKS** · **BUG** · **BROKEN** · **MISSING** · **DEVIATES** · **UNSPECIFIED** ·
**NEEDS-HUMAN** · **OUT-OF-SCOPE** · **NOT-TESTED**.

## Summary

| | Count |
|---|---|
| Functional requirements in SRS §5 | 89 |
| Tested behaviourally | 77 (87 %) |
| Not tested | 12 (13 %) |
| Further `FR-`prefixed ids in SRS §6 (non-functional mirrors: `FR-SEC-*`, `FR-PERF-*`, `FR-SCALE-*`, `FR-REL-*`, `FR-ACC-001`, `FR-AVAIL-001`, `FR-BAK-001`, `FR-LOG-001`, `FR-MAINT-001`, `FR-PRIV-001`, `FR-REC-001`, `FR-USE-001`) | 19 — NOT-TESTED, out of scope for a functional verification |
| Invariants (I-01…I-24) exercised | 14 |
| Doc-cited checks executed | 245 (223 passed) |

---

## 1. Authentication (FR-AUTH)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-AUTH-001 Registration via phone | partial | NEEDS-HUMAN | DEF-016 | `res_identity.json` `AUTH-001-*` — OTP request reaches Eskiz and is rejected on placeholder credentials; invalid code rejected `422`. Real SMS delivery needs credentials |
| FR-AUTH-002 Registration via email | yes | **MISSING** (acceptance 1) / BUG (acceptance 2) | DEF-005, DEF-003 | `AUTH-002-*` — account created `ACTIVE`, no redemption endpoint exists; duplicate inside the async window returns 500 not 409 |
| FR-AUTH-003 Federated sign-in (Google) | partial | NEEDS-HUMAN | — | `AUTH-003-google-bad-token` — invalid token refused `422`; success path needs real OAuth credentials |
| FR-AUTH-004 Authentication (login) | yes | WORKS | — | `AUTH-004-*` — valid `200`; wrong password and unknown account both `401 AUTHENTICATION_INVALID` |
| FR-AUTH-005 Session management | yes | WORKS | — | `AUTH-005-*` — `/me`, `/me/sessions` `200`; logout `204`; session dead `401` after |
| FR-AUTH-006 Credential recovery | yes | WORKS | — | `AUTH-006-*` — `202` for known and unknown alike (enumeration-safe) |

## 2. User & Account Management (FR-USER)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-USER-001 Manage personal profile | yes | **BUG** | DEF-003 | `USER-001-*` — `PATCH /me` `200` echoing the new value, but 8/10 immediate re-reads return the previous one |
| FR-USER-002 Multiple business profiles + switch | yes | WORKS | — | `res_profiles.json` `USER-002-*` — 8 profiles held; switch `200`; acting context reflected. ~2 s outbox propagation window noted, not a defect |
| FR-USER-003 Privacy settings (contact visibility) | yes | WORKS | — | `USER-003-privacy`; enforced end-to-end in `res_messaging.json` `I-18-*` |
| FR-USER-004 Manage favorites | yes | WORKS | — | `res_catalog.json` `USER-004-*` — add `201`, list, remove `204`; `FAVORITE_ADDED` metric emitted |
| FR-USER-005 Account closure & data request | partial | WORKS (closure) / NOT-TESTED (export) | — | `USER-005-*` — closure `204`, account then `401`. Data export not exercised |

## 3. Company Profiles & Verification (FR-PROF)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-PROF-001 Create business profile (8 types) | yes | WORKS | — | `res_profiles.json` `PROF-001-eight-types` — all 8 created |
| FR-PROF-002 Company page & portfolio | yes | WORKS | — | `PROF-002-*` — public page, edit, portfolio list; non-owner edit `403` |
| FR-PROF-003 Submit verification documents | yes | WORKS | — | `res_e2e.json` — image documents accepted via `VERIFICATION_DOCUMENT` presigned upload; non-image refused at the media boundary |
| FR-PROF-004 Request verification | yes | WORKS | — | `PROF-004-*` — gated on a `VERIFICATION_ELIGIBILITY` entitlement; case created `201` with an SLA due date |
| FR-PROF-005 Process verification (reviewer) | yes | WORKS | — | `PROF-005-*` — approval `200`; re-deciding a terminal case refused `409` |
| FR-PROF-006 Display verified badge | yes | WORKS | — | `PROF-006-badge` — `badge_status='VALID'` with `badge_valid_until` set |
| FR-PROF-007 Re-verification on expiry | no | NOT-TESTED | — | Badge validity is 30 days; needs time travel or a shortened term |
| — Team roster operations | yes | **MISSING** | DEF-007 | `PROF-team-endpoint` — `404`; 3 contract operations unimplemented |

## 4. Advertisements / Listings (FR-ADV)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-ADV-001 Create listing | yes | WORKS | — | `res_catalog.json` `ADV-001-*` |
| FR-ADV-002 Attach images (≤10) | yes | WORKS | — | `res_e2e.json` `ADV-002-image-limit` — 10 attached, 11th `422` (**I-04**) |
| FR-ADV-003 Save draft | yes | WORKS | — | `ADV-003-*` — draft `404` to anonymous, `200` to owner (**I-06**) |
| FR-ADV-004 Publish (post-publication moderation) | yes | WORKS | — | `ADV-004-*` — publishes and is immediately public |
| FR-ADV-005 Edit listing → Edited | yes | WORKS | — | `ADV-005-*` — state becomes `EDITED`; non-owner `403` |
| FR-ADV-006 Lifecycle transitions | yes | WORKS | — | `ADV-006-*`, `I-05-illegal-transition` — illegal transition `409`, all transitions recorded |
| FR-ADV-007 Expiry & renewal | no | NOT-TESTED | — | Needs a shortened expiry period |
| FR-ADV-008 Quotas & limits | yes | WORKS | — | `res_e2e.json` `I-08-quota` — 2 created under a 2-listing plan, 3rd `409` |
| FR-ADV-009 Duplicate detection | yes | WORKS | — | `ADV-009-*` — duplicates raise moderation cases |
| FR-ADV-010 View listing detail + view metric | yes | **MISSING** (metric) | DEF-008 | Detail renders; `LISTING_VIEWED` never emitted — `res_ops.json` `ANALYTICS-001-coverage`, and `/admin/reports` shows `"LISTING_VIEWED": 0` |

## 5. Categories & Dynamic Forms (FR-CAT, FR-FORM)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-CAT-001 Browse categories | yes | WORKS | — | `GET /categories` serves the authored taxonomy; also verified in the UI |
| FR-CAT-002 Category-field association | yes | WORKS | — | `GET /categories/{id}/form` returns the bound form |
| FR-FORM-001 Render dynamic form | yes | WORKS | — | Form served with all four locales, validators, camelCase; rendered in the wizard (`res_ui_auth.json` `UI-FORM-001-dynamic-fields`) |
| FR-FORM-002 Validate submissions | yes | **BUG** | DEF-002, DEF-010 | Required/`numeric_range` enforced correctly; but `option_membership` rejects configured options, and unknown attributes are accepted |

## 6. Search (FR-SRCH) & Maps (FR-MAP)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-SRCH-001 Full-text search | yes | WORKS | — | `res_search.json` `SRCH-001-fulltext` |
| FR-SRCH-002 Faceted filtering | yes | WORKS | — | `SRCH-002-*` — facets come from the published search-configuration |
| FR-SRCH-003 Sorting | partial | **DEVIATES** | DEF-013 | `RELEVANCE`/`PRICE_ASC`/`PRICE_DESC` work; the configurable `NEWEST` is refused `422` (API wants `RECENCY`) |
| FR-SRCH-004 Cross-script matching | yes | WORKS | — | `SRCH-004-*` — both directions, incl. `oʻ`/`gʻ`; and from the UI (`res_ui.json` `UI-SRCH-004-crossscript`) |
| FR-SRCH-005 Promoted labelling & capping | yes | WORKS | — | `res_promo.json` — `"promoted":{"kind":"PREMIUM"}` within the cap of 3 |
| FR-MAP-001 Set listing location | yes | WORKS | — | Location stored and returned on the listing and the search hit |
| FR-MAP-002 Map display (Yandex) | no | NEEDS-HUMAN | — | Needs a real `YANDEX_MAPS_API_KEY` |
| FR-MAP-003 Radius search | yes | **BUG** | DEF-006 | `MAP-003-radius` — identical results at 1/5/50/500 km and with no radius; Samarkand returned at `radiusKm=1` from Tashkent |

## 7. Media (FR-MEDIA)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-MEDIA-001 Image upload & validation | yes | WORKS | — | `res_e2e.json` `MEDIA-001-*` — presigned `PUT` `200`; >10 MB refused |
| FR-MEDIA-002 Reject non-image media | yes | WORKS | — | `MEDIA-002-*` — `video/mp4` and `application/pdf` refused `422` |
| FR-MEDIA-003 Metadata stripping (EXIF/GPS) | no | NOT-TESTED | — | Needs an image with known GPS EXIF plus a stored-object re-read |
| FR-MEDIA-004 Malware scanning | no | NOT-TESTED | — | Needs an EICAR file through the full ClamAV path |
| FR-MEDIA-005 Image delivery (thumbnails) | no | NOT-TESTED | — | Derivative generation not driven to completion |

## 8. Messaging & Contact (FR-MSG)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-MSG-001 Initiate chat + metric | yes | WORKS | — | `res_messaging.json` `MSG-001-*` — conversation `201`, `CHAT_INITIATED` recorded |
| FR-MSG-002 Real-time messaging + persistence | yes | WORKS | — | `MSG-002-*` — WSS frame received; history persists; unauthenticated upgrade refused |
| FR-MSG-003 Phone reveal per privacy settings | yes | WORKS | — | `I-18-*` — `NEVER` → `allowed:false`; `ON_REQUEST` → `allowed:true` + number; `PHONE_REVEALED` recorded |
| FR-MSG-004 Block | yes | WORKS | — | `MSG-004-*`, `I-19-block-enforced` — blocked sender `403` |
| FR-MSG-005 Report conversation/user | yes | WORKS | — | `MSG-005-report` `202`; enters the moderation queue |

## 9. Notifications (FR-NOTIF)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-NOTIF-001 Email notifications | partial | WORKS (sink) / NEEDS-HUMAN (production SMTP) | — | `res_ops.json` `NOTIF-001-dispatched` — 50 rows; mail delivered to Mailpit |
| FR-NOTIF-002 Web-push | no | NEEDS-HUMAN | — | Needs a real VAPID pair and a browser subscription |
| FR-NOTIF-003 SMS OTP (Eskiz) | partial | NEEDS-HUMAN | DEF-016 | Provider boundary verified |
| FR-NOTIF-004 Notification preferences | yes | WORKS | — | `NOTIF-004-preferences` `200` |
| — Redelivery does not duplicate | no | NOT-TESTED | — | Idempotent redelivery not exercised |

## 10. Subscriptions, Billing (FR-SUBS, FR-BILL)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-SUBS-001 Browse products & plans | yes | WORKS | — | `res_e2e.json` — all six ProductTypes with configured pricing |
| FR-SUBS-002 Purchase request | yes | WORKS | — | Order created; `ProductSnapshot` frozen |
| FR-SUBS-003 Entitlement activation | yes | WORKS | — | Activates only on operator confirmation (**I-14**) |
| FR-SUBS-004 Entitlement expiry | no | NOT-TESTED | — | 30-day term; needs time travel |
| FR-BILL-001 Generate invoice | yes | WORKS | — | `INV-000003` issued with order details |
| FR-BILL-002 Confirm offline payment | yes | WORKS | — | Buyer self-confirm `403`; operator confirm → `PAID` |
| FR-BILL-003 Billing status & reconciliation | yes | WORKS | — | `/admin/billing/invoices` lists with status |
| FR-BILL-004 No online payment in v1 | yes | WORKS | — | All 109 live operations scanned; no gateway path |

## 11. Banner Ad-Serving (FR-BANNER)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-BANNER-001 Define inventory & slots | partial | WORKS | — | `placement-slot` authored and published; `/admin/campaigns` `200` |
| FR-BANNER-002 Schedule campaign | no | NOT-TESTED | — | Campaign creation needs a `BANNER_SLOT_BOOKING` entitlement chain not reached |
| FR-BANNER-003 Basic targeting | no | NOT-TESTED | — | Depends on FR-BANNER-002 |
| FR-BANNER-004 Serve banners | partial | UNSPECIFIED | — | `/banners/serve?slotKey=home-hero` → `204` with no active campaign; the contract does not state the empty-slot response |
| FR-BANNER-005 Track impressions & clicks | no | NOT-TESTED | — | Depends on FR-BANNER-002; the two banner metrics were never emitted (DEF-020) |

## 12. Trust, Safety & Moderation (FR-MOD)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-MOD-001 Report listing | yes | WORKS | — | `res_ops.json` `MOD-001-report` |
| FR-MOD-002 Automated validation flags | partial | WORKS | — | Duplicate detection flags to the queue; other rule kinds not exercised |
| FR-MOD-003 Moderator actions | yes | WORKS | — | `MOD-003-*` — closed verb set enforced (`DELETE_EVERYTHING` `422`); `SUSPEND` applied and auditable |
| FR-MOD-004 Account suspension | yes | WORKS | — | `MOD-004-*` — account `401`, and its listings hidden (compensation) |
| FR-MOD-005 Moderation queue | yes | WORKS | — | `MOD-005-*` — lists; refused to ordinary users `403` |

## 13. Administration (FR-ADMIN)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-ADMIN-001 Manage users & companies | yes | WORKS | — | `ADMIN-001-users` — 20 users listed |
| FR-ADMIN-002 Manage verification queue | yes | WORKS | — | `ADMIN-002-*` — cases queued and processed to a decision |
| FR-ADMIN-003 Manage subscriptions & billing | yes | WORKS | — | `BILL-003-reconcile` |
| FR-ADMIN-004 Manage banner campaigns | partial | NOT-TESTED | — | Endpoint responds; lifecycle not exercised |
| FR-ADMIN-005 Reports | yes | **DEVIATES** | DEF-020 | `ADMIN-005-reports` `200`, but enumerates 6 of the 8 closed metrics |
| FR-ADMIN-006 Role & permission management | yes | WORKS | — | `ADMIN-006-*` — assignment takes effect; **I-16** verified in the negative |
| — `/admin` dashboard composition | yes | **BUG** | DEF-015 | Every field `null` |
| — `/admin` is not a privilege bypass | yes | WORKS | — | `ADMIN-not-bypass` — anonymous `401`, unprivileged `403` |

## 14. Configuration (FR-CFG)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-CFG-001 Configure taxonomy | yes | WORKS | DEF-011 | `CFG-001-no-redeploy` — categories 3 → 4 in the running process, visible in the UI |
| FR-CFG-002 Configure forms & fields | yes | WORKS (authoring) / see DEF-002 (runtime) | DEF-002, DEF-011 | Whitelisted field types only; publishing works |
| FR-CFG-003 Configure validation, filters, sorting | yes | **DEVIATES** | DEF-002, DEF-013 | Facets apply correctly; `option_membership` broken; `NEWEST` unusable |
| FR-CFG-004 Configure commercial products | yes | WORKS | — | All six product types authored, published and served with pricing |
| FR-CFG-005 Configure platform settings | partial | WORKS | — | Seeded and readable; a live settings change was not published |
| — Maker–checker | yes | WORKS | DEF-018 | Self-approval refused `403` |
| — Whitelist gate (I-16) | yes | WORKS | — | `WHITELIST_VIOLATION` on a non-catalogue PermissionKey and PageZone |
| — Rollback / import / export | no | NOT-TESTED | — | Operations served but not exercised |

## 15. Audit & Analytics (FR-AUDIT, FR-ANALYTICS)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-AUDIT-001 Administrative & moderation audit | yes | WORKS | — | 20+ entries with actor, action, target, time |
| FR-AUDIT-002 Audit review | yes | WORKS | — | `AUDIT-002-*` — viewable and filterable; refused to others |
| FR-ANALYTICS-001 Capture performance metrics | yes | **MISSING** (partial) | DEF-008, DEF-020 | Only 3 of 8 captured; `LISTING_VIEWED`, `CONTACT_BUTTON_CLICKED`, `PREMIUM_LISTING_STAT` and both banner metrics never observed. **Closed vocabulary respected** — nothing outside the eight was ever written |
| FR-ANALYTICS-002 Listing statistics to owners | yes | **BUG** | DEF-009 | Counts return `null` |
| — Append-only immutability | yes | WORKS | — | `UPDATE` on `analytics.audit_entry` affected no rows |

## 16. Localization (FR-LOC)

| Id | Tested | Class | Defect | Evidence |
|---|---|---|---|---|
| FR-LOC-001 Multilingual interface | yes | WORKS | — | `res_ui.json` `UI-LOC-001-*` — 4/4 distinct renderings, correct scripts per locale |
| FR-LOC-002 Any-language content | yes | WORKS | — | Listings authored in all four locales; served as authored |

## 17. Reviews & Ratings (§5.20)

| Id | Tested | Class | Evidence |
|---|---|---|---|
| Deferred to v2 per DEC-03 | yes (absence check) | OUT-OF-SCOPE — correctly absent | No operation, schema or UI found |

## 18. Invariants exercised

| Invariant | Class | Evidence |
|---|---|---|
| I-04 ≤10 images, clean image assets | WORKS | 10 attached, 11th `422` |
| I-05 Only legal transitions, all recorded | WORKS | Illegal `409`; 3 transition rows |
| I-06 Public only when Published/Edited, unflagged | WORKS | Draft `404`; suspended `404` |
| I-07 Listing binds an immutable form version | WORKS | `form_definition_version_id` stored |
| I-08 Creation beyond plan quota refused | WORKS | 3rd listing `409` under a 2-listing plan |
| I-13 Badge only from an approved case | WORKS | No badge before approval; `VALID` after |
| I-14 No entitlement without confirmed payment | WORKS | Self-confirm `403`; activation only after operator confirm |
| I-16 Configuration cannot widen access | WORKS | `WHITELIST_VIOLATION`; moderator refused billing |
| I-18 Phone revealed only per privacy settings | WORKS | Both directions + metric |
| I-19 Two participants; block enforced | WORKS | Third party `403` (read and write); blocked sender `403` |
| I-24 Moderation drives the owning context | WORKS | Catalog recorded its own transition |
| I-02 Exactly one form binding per category | WORKS (implicitly) | `form_definition_id` NOT NULL; publish gate checks the dependency |
| I-10 Role scoped to acting profile | partial | `actingProfileId: null` path verified; per-profile scoping not isolated |
| I-01, I-03, I-09, I-11, I-12, I-15, I-17, I-20…I-23 | NOT-TESTED | Not reachable through observable behaviour within this run, or dependent on untested areas (expiry, banners, media pipeline) |

## 19. Frontend flows (UI/UX Functional Specification)

| Flow | Tested | Class | Evidence |
|---|---|---|---|
| §1 Registration / login | yes | WORKS | `res_ui_auth.json` — email registration and login succeed; `ah_session` HttpOnly |
| §1.2 Acting-context switcher | partial | NOT-TESTED (UI) | Verified via API only |
| §2 Public surface (home, search, listing detail) | yes | WORKS | Renders in all four locales |
| §3 Account surface (dashboard, favorites, notifications, profile, settings) | yes | WORKS | All render authenticated content |
| §4 Business surface (company, portfolio, statistics) | partial | WORKS | `/dashboard/business` renders; portfolio upload not driven |
| §5 Product-Owner configuration portal | partial | WORKS | `/admin/config` and `/admin/config/category` render; Head+Version authoring, validation-error surfacing, maker–checker and rollback **not** driven through the UI |
| §6 Admin portal | yes | WORKS | 7 operator pages render; `/admin` itself near-empty (DEF-015) |
| §7 Moderation surface | yes | WORKS | `/admin/moderation` renders with data |
| §10 Realtime chat UI | no | NOT-TESTED (UI) | WSS verified at protocol level; the chat UI was not driven |
| §12 Dynamic form engine | yes | WORKS | Wizard renders configured fields |
| Image upload (presigned) from the UI | no | NOT-TESTED | Verified via API |
| Map / radius UI | no | NOT-TESTED | Needs a Yandex key |
| Accessibility WCAG 2.2 AA | yes | WORKS | 0 violations on 7 screens |
| Responsiveness (mobile-first) | yes | WORKS | No overflow at 375 px |
| Frontend enforces no authorization | yes | WORKS | `/admin` as a normal user → redirected to login |

## 20. Cross-cutting

| Item | Tested | Class | Evidence |
|---|---|---|---|
| NFR-MAINT-001 config change with no redeploy | yes | WORKS | Category published into a running process, visible in API and UI |
| Degradation: OpenSearch down → PostgreSQL fallback | yes | WORKS | 16 results with `"degraded": true`; recovers |
| Degradation: media lag does not block publishing | yes | WORKS | Listings publish before processing completes |
| Outbox durability under consumer outage | yes | **BUG** | DEF-012 — events reach `DEAD`, never retried |
| Eventual-consistency windows | yes | WORKS | ~2 s profiles→identity; ~10 s promotion→search |
| API contract conformance | yes | WORKS | 107/110 operations, 0 undocumented extras |
| Problem envelope & stable error codes | yes | WORKS | 9 distinct codes observed, all documented |
| Keep-alive behaviour on error paths | yes | **BUG** | DEF-004 |
| Read-after-write | yes | **BUG** | DEF-003 |
| Fresh-install migrations | yes | **BROKEN** | DEF-001 |
| Authorization by role (5 actor types) | yes | WORKS | Default deny; no widening; no `/admin` bypass |
| NFR-PERF-*, NFR-SCALE-* | no | NOT-TESTED | Load testing out of scope for functional verification |
| NFR-SEC-001/003/004/005 (crypto, headers, secrets) | no | NOT-TESTED | Belongs to a security review, not functional verification |
| NFR-BAK-001, NFR-REC-001 (backup/recovery) | no | NOT-TESTED | Requires an operational drill |
