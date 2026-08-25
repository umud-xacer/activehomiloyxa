# contracts/

STATUS: **FROZEN** (Task P-01). This is now the single source every module-implementation task
builds against. Changing anything in this directory is an architecture event, not a routine
edit alongside unrelated feature work (Playbook Sec 2, Sec 8 "freeze interfaces + event schema
before parallel work"; SAD "AI operates inside frozen contracts; humans change the contracts").

## What's here

| Path | Contents |
|---|---|
| `openapi.yaml` | Verbatim copy of `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml` -- byte-identical, not rewritten. The single source of API truth. |
| `errors/problem.py` | The Problem-style error envelope (`Problem`, `ValidationError`, the closed `ErrorCode` vocabulary) every module's ports use for their error path. |
| `events/` | The complete v1 domain-event catalogue (DDD Sec 6, as amended by ADR-0001) -- 53 events across 10 files, one per emitting bounded context. Every event carries the shared envelope (`shared_kernel.EventEnvelope`). See `events/__init__.py`'s `EVENT_CATALOGUE` registry and `tests/test_event_catalogue.py`, which asserts it covers DDD Sec 6 (as amended) exactly (no event missing, none invented). |
| `pyproject.toml` | Makes `errors/` and `events/` importable as `contracts.errors` / `contracts.events` (editable-installed alongside `active-home-shared` and `active-home-backend`). `openapi.yaml` and this README are plain files, not part of the installed package. |
| `tests/` | Proves the above at runtime, not just statically (event catalogue completeness, envelope shape, Problem round-trip). |

The per-module `interfaces/` stubs themselves live where they'll stay permanently --
`apps/backend/src/<module>/interfaces/{dto.py,ports.py,__init__.py}` -- not under `contracts/`.
This directory is what they were *derived from*, kept as the durable source of truth to
re-derive against, not a duplicate copy of the stubs.

## How the interface stubs were derived

Each of the 13 modules' `interfaces/dto.py` (Pydantic v2 models, `CamelModel`-based so the
Python attribute is snake_case and the wire field is the OpenAPI's camelCase) and `ports.py`
(`typing.Protocol` classes, `...`-bodied, zero logic) were generated from two inputs, per the
P-01 task brief:

1. **`contracts/openapi.yaml`'s operations**, grouped to a module by their tag -- except the
   `Administration` tag, which is a cross-cutting admin-surface grouping, not a bounded-context
   tag. Its operations were routed to the module that owns the underlying aggregate instead
   (SAD Sec 7.2 "Owns" column, cross-referenced against each operation's request/response
   schema): audit-log/reports -> `analytics`; invoices/payment-confirmation -> `billing`;
   moderation queue/case/action -> `moderation`; user list/status -> `identity`;
   verification queue/decision -> `profiles`. Only the dashboard composition endpoint
   (`getAdminDashboard`), which maps to no single owning aggregate, stayed on `admin`.
2. **SAD Sec 7.2's "Public interface (examples)" column**, for port *names* where a module has
   no HTTP surface at all yet: `identity.AuthorizationPort` / `ContactPolicyPort`,
   `billing.PaymentProviderPort`, `configuration.WhitelistRegistryPort`,
   `moderation.ModerationCommandTargetPort`, and both of `ads`'s ports. These are empty marker
   `Protocol`s with a docstring explaining exactly why -- see each one's module `ports.py`.

Shared component schemas were placed by what DDD Sec 5.14 actually sanctions: `LocalizedText`,
`Money`, and `GeoPoint` (-> `GeoLocation`) live in `shared_kernel/` (populated in this task,
alongside `EventEnvelope`) because the Domain Model names them as shared-kernel content and
multiple modules independently reference them; everything else that's module-specific
(`AttributeMap`, the synthesised `PageInfo`/`<X>Page` pagination wrappers for the 14
`CursorPage`-shaped list endpoints) is declared locally in each consuming module rather than
added to the shared kernel, since DDD doesn't sanction them there and duplicating a small DTO
keeps modules self-contained.

Query/path parameters that are pure transport concerns (`Idempotency-Key`, `Accept-Language`,
`X-Acting-Profile` -- all headers) are **not** modelled on port method signatures; they're
composition-root/FastAPI-dependency concerns, not business-facing inputs. Path parameters and
genuinely business-relevant query parameters (pagination cursor/limit, search filters, etc.)
are.

## Gaps resolved by ADR

- **FR-ADMIN-006's role-ASSIGNMENT half had no HTTP surface at all -- resolved by ADR-0006.**
  `identity.application.admin_use_cases.AdminIdentityUseCases.assign_role`/`revoke_role` (Task
  P-05) were real, complete use cases with no operation in `contracts/openapi.yaml` --
  `identity/README.md`'s own "Public interface" note and `configuration/domain/whitelist.py`'s own
  P-05 comment on `identity:role:assign` both explicitly earmarked this for "a future admin-module
  task." `docs/adr/0006-admin-role-assignment-endpoints.md` (Task P-16, Proposed -- drafted by an
  agent, pending human architect ratification per Playbook Sec 18, at the repository owner's
  explicit direction) resolves this by adding `assignRole`/`revokeRole`
  (`POST`/`DELETE /admin/users/{userId}/roles...`) and one new schema (`RoleAssignmentRequest`) --
  implemented in `identity`'s own router (not `admin`'s), mirroring exactly where the sibling
  `adminListUsers`/`adminChangeUserStatus` operations already live, gated by the already-existing
  `identity:role:assign` permission key (no new key invented).
- **Three of the eight closed-vocabulary v1 metric events had no event class at all -- resolved
  by ADR-0005.** DDD Sec 5.13's own `ClosedVocabularyPolicy` names exactly eight metric keys, but
  `contracts/events/catalog.py` (frozen, Task P-01) defined event classes for only five of them
  (`FavoriteAdded`/`FavoriteRemoved`, plus `PhoneRevealed`/`ChatInitiated` in `messaging.py` and
  `BannerImpressionRecorded`/`BannerClickRecorded` in `ads.py`) -- `ListingViewed`,
  `ContactButtonClicked`, and `PremiumListingStat` had no class anywhere, and no module publishes
  them. `docs/adr/0005-analytics-missing-metric-events.md` (Task P-15, Proposed -- drafted by an
  agent, pending human architect ratification per Playbook Sec 18, at the repository owner's
  explicit direction) resolves this by adding all three to `contracts/events/catalog.py` (all
  catalog-owned: `ListingViewed` per DDD Sec 5.3's own `ViewRecordingPolicy`; the other two by the
  same listing-detail-page/`PromotionMarker` reasoning) and updating `EVENT_CATALOGUE`/
  `test_event_catalogue.py`'s oracle set (53 -> 56 entries) in the same change. No producer is
  wired -- `catalog`'s own use cases are untouched by this ADR; `analytics/infrastructure/
  event_projection.py`'s consumer for these three keys is built and tested against synthetic
  events only, mirroring ADR-0001's own media precedent.
- **The "Mark as Sold" feature's `ListingSold` event was never registered in the frozen catalogue
  -- resolved by ADR-0011.** Unlike the ADR-0001/ADR-0005 amendments above (both a previously-
  published-but-omitted DDD Sec 6 row), this is a genuinely new BC-03 event for a genuinely new
  capability with no DDD Sec 6 precedent at all: `catalog.domain.value_objects.LifecycleState`
  gained an eighth value (`SOLD`) and `contracts/events/catalog.py` gained the `ListingSold` class
  in the same feature change, and both `search`'s and `notifications`' own event-type sets were
  correctly wired to it -- but `EVENT_CATALOGUE`, `configuration/domain/whitelist.py`'s
  `EVENT_KEYS`, and `test_event_catalogue.py`'s `DDD_SEC_6_EVENT_NAMES` oracle were not, which left
  every "no event missing" drift check silently passing (all three omitted the same name).
  `docs/adr/0011-mark-as-sold-listing-lifecycle-state.md` (Proposed -- drafted by an agent, pending
  human architect ratification per Playbook Sec 18) resolves this by registering `ListingSold` in
  all three places (`EVENT_CATALOGUE`/oracle set 56 -> 57 entries) in the same change.
- **`ads` had zero v1 REST endpoints -- resolved by ADR-0004.** Under Task P-01, `docs/Active-
  Home-OpenAPI-3.1-Specification-v1.0.yaml` had no banner/campaign path at all; ads' only v1
  traces were a Billing `Product` type (`BANNER_PLACEMENT`/`TOP_PLACEMENT`), a Billing
  `Entitlement` kind (`BANNER_SLOT_BOOKING`), a Media purpose (`BANNER_CREATIVE`), and an
  admin-authored `PlacementSlotDefinition` via Configuration. `docs/adr/
  0004-ads-openapi-endpoints.md` (Task P-14, Proposed -- drafted by an agent, pending human
  architect ratification per Playbook Sec 18, at the repository owner's explicit direction)
  resolves this by adding an `Ads` tag and nine operations -- `/admin/campaigns` (list/create),
  `/admin/campaigns/{campaignId}` (get/update), `/admin/campaigns/{campaignId}/schedule`|`pause`|
  `resume`|`end`, `/banners/serve`, `/banners/{campaignId}/impressions`,
  `/banners/{campaignId}/clicks` -- and four schemas (`BannerCampaign`,
  `BannerCampaignCreateRequest`, `BannerCampaignUpdateRequest`, `BannerServeView`), traced to
  FR-BANNER-002...005/BR-BAN-02/03/I-21. FR-BANNER-001 (banner inventory/placement slots) is
  deliberately *not* duplicated here -- it is `PlacementSlotDefinition`, already served by the
  existing `/admin/config/{entityType}` surface. `docs/Active-Home-OpenAPI-3.1-Specification-
  v1.0.yaml` and `docs/frontend_docs/`'s copy were both updated identically in the same change;
  `ads/interfaces/{dto,ports}.py` follow in Task P-14's own implementation work.
- **`media`'s DDD-vs-SAD mismatch -- resolved by ADR-0001.** SAD Sec 7.2 describes media's public
  interface as "MediaIntakePort, **asset-status events**", but DDD Sec 6 -- explicitly "the
  authoritative v1 event catalogue" -- had no BC-06 row at all when this note was first written
  under Task P-01. `docs/adr/0001-media-asset-status-events.md` (Task P-06, Proposed -- drafted
  by an agent, pending human architect ratification per Playbook Sec 18) resolves the
  inconsistency in SAD's favor: `contracts/events/media.py` now defines `MediaAssetAccepted`,
  `MediaAssetReady`, and `MediaAssetRejected`, and `EVENT_CATALOGUE`/`test_event_catalogue.py`'s
  oracle set were both updated in the same change. The published DDD Sec 6 table itself is not
  edited here (that re-versioning is the separate, human-owned governance step the ADR
  describes) -- the ADR is the durable record of why `contracts/` now differs from it.
- **`profiles`' `ProfileType` enum vs. SRS Sec 4 / DDD Sec 5.2 -- resolved by ADR-0002.** The
  OpenAPI spec's `BusinessProfile.profileType` (and the two other locations it appears)
  originally enumerated `INDIVIDUAL_SELLER`/`REAL_ESTATE_AGENCY`/`DEVELOPER`/
  `MATERIALS_SUPPLIER`/`ARCHITECT_DESIGNER`/`PROPERTY_MANAGER` alongside
  `CONSTRUCTION_COMPANY`/`SERVICE_PROVIDER` -- a different taxonomy from SRS Sec 4's own eight
  named business-profile types (Construction Company, Manufacturer, Builder, Supplier,
  Contractor, Architect, Interior Designer, Service Provider), which DDD Sec 5.2's `ProfileType
  [P]` cites as "the eight types." `docs/adr/0002-business-profile-type-vocabulary-correction.md`
  (Task P-11, Proposed -- drafted by an agent, pending human architect ratification per Playbook
  Sec 18) resolves the inconsistency in SRS/DDD's favor: `docs/Active-Home-OpenAPI-3.1-
  Specification-v1.0.yaml`, `contracts/openapi.yaml`, and `docs/frontend_docs/`'s copy all now
  enumerate `CONSTRUCTION_COMPANY`/`MANUFACTURER`/`BUILDER`/`SUPPLIER`/`CONTRACTOR`/`ARCHITECT`/
  `INTERIOR_DESIGNER`/`SERVICE_PROVIDER`, and `profiles/interfaces/{dto,ports}.py` were updated
  in the same change.
- **`moderation`'s `Subject`/`ResolutionAction` vocabularies extended to cover BC-02 -- resolved
  by ADR-0003.** DDD Sec 5.11's own closed `Subject` (`ListingRef`/`ConversationRef`/`UserRef`)
  and `ResolutionAction` (`Hide`/`Reject`/`Suspend`/`RequestCorrection`/`Remove`/
  `SuspendAccount`/`Dismiss`) VOs, corroborated by SRS FR-MOD-003 and Baseline Sec 4-K/DEC-14,
  named only BC-03 (catalog) and BC-01 (identity) as `ModerationActionService` command targets --
  no ref type or verb for BC-02 (profiles). Task P-12's own brief directed wiring
  `profiles.interfaces.moderation_port.ProfileModerationPort` (badge revocation/profile
  archival) as a third target. `docs/adr/0003-moderation-profile-target-extension.md` (Task
  P-12, Proposed -- drafted by an agent, pending human architect ratification per Playbook Sec
  18) resolves this by extending both vocabularies: `docs/Active-Home-OpenAPI-3.1-Specification-
  v1.0.yaml`, `contracts/openapi.yaml`, and `docs/frontend_docs/`'s copy all now add `PROFILE` to
  every `subjectType` enum and `REVOKE_BADGE`/`ARCHIVE_PROFILE` to every `resolutionAction`/
  `action` enum, and `moderation/interfaces/{dto,ports}.py` were updated in the same change.

## Amendment process

Any change to `openapi.yaml`, `errors/problem.py`, `events/`, or a module's `interfaces/`
public surface is an interface-change event (Playbook Sec 8, Sec 18):

1. The change is justified against a specific approved-document id (a new FR, a corrected DEC,
   etc.) -- never made to unblock an unrelated task.
2. It ships with an ADR (`docs/adr/NNNN-title.md`) if it changes a public interface, the event
   schema, or introduces/removes a cross-module dependency (Playbook Sec 18's "When an ADR is
   required" list).
3. `openapi.yaml` is still copied verbatim from the approved source document -- if the source
   itself needs to change, that change happens in the approved document first (governance,
   Playbook Sec 18), and this copy follows.
4. Every module that consumes the changed shape updates in the same PR (DOC-01).

Routine implementation *inside* the frozen shapes here -- writing the actual domain/application/
infrastructure code behind a port -- is not an amendment and needs no ADR.
