# ADR-0004: Add BC-09 (Ad-Serving / Banners) operations to the frozen OpenAPI contract

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-07-13

**Author**: Claude Sonnet 5, drafting under Task P-14 (Ad-Serving / Banners) at the explicit
direction of the repository owner, after surfacing the conflict below rather than silently
resolving it.

## Context

`contracts/README.md` (written under Task P-01) documents a known, deliberate fact: `ads` has
zero v1 REST endpoints. `contracts/openapi.yaml`'s `tags:` list has no "Ads" entry, and a grep for
`campaigns`/`banners` across the whole file returns no matches. `apps/backend/src/ads/
interfaces/ports.py`'s own docstring repeats this verbatim: two unshaped marker ports, no DTOs,
"both stay this way until an ADR adds concrete ads endpoints to `contracts/openapi.yaml`."

Task P-14 now requires implementing `ads` for real: campaign creation/scheduling/targeting,
banner selection at serve time, and impression/click capture. Every one of these is a genuine,
approved-document-backed capability with no ambiguity about *whether* it belongs in v1:

- **FR-BANNER-002…005** (SRS) — schedule (start/end, priority), targeting (category/geo/
  language), serve scheduled banners in their placements, track impressions and clicks.
- **BR-BAN-02/03** (BRD §8.9) — same four capabilities, traced to **DEC-05** ("banner ad-serving
  is an approved v1 revenue source").
- **I-21** (DDD §9) — "A BannerCampaign serves only within its schedule, matching targeting, in
  its configured slot, while its booking entitlement is active" — a serve-time invariant that
  presupposes a serve operation exists to enforce it against.
- **DDD §5.9** — `BannerCampaign` is a first-class aggregate with `CampaignStatus` (Draft/
  Scheduled/Running/Ended/Paused) and three lifecycle events already frozen in
  `contracts/events/ads.py` (`BannerCampaignScheduled/Started/Ended`) plus two metric events
  (`BannerImpressionRecorded/ClickRecorded`) — none of these events has anywhere to be raised
  *from* without a command surface.

This is therefore not "inventing a new capability the documents never described" — every
operation this ADR adds is traceable to an existing FR/BR/invariant/event. The only artifact that
is silent is the OpenAPI contract itself, which — per `contracts/README.md`'s own P-01 note —
simply never had ads endpoints authored into it, unlike every other bounded context that reached
implementation. FR-BANNER-001 ("administrator defines banner inventory and placement slots") is
**not** included here: that capability is `PlacementSlotDefinition`, one of BC-04's eight
configuration entities (Configuration & Metadata Framework §3.4), already served generically by
the existing `/admin/config/{entityType}` Head+Version surface (`entityType=placement-slots`) —
adding a second, ads-owned path for the same capability would duplicate an existing operation
rather than fill a gap.

The repository owner was asked directly whether to (a) implement the module with no HTTP surface
and flag the gap for a future ADR, (b) block the whole task on a human-authored ADR, or (c)
proceed and add the needed operations now. The owner chose **(c)**: "you can change the
openapi.yaml, let's add needed APIs." This ADR is the durable record of that decision and its
reasoning, per Playbook §18's requirement that a contract change never be a silent edit.

## Decision

Add a new `Ads` tag and nine operations to `contracts/openapi.yaml`, following the same
conventions every other module's own aggregate-owning admin surface already uses (cf.
`Configuration (Admin)` tag on `/admin/config/{entityType}` — a module-owned aggregate surfaced
under `/admin/*` keeps its own tag rather than the generic `Administration` tag, which is reserved
for thin composition-context screens over *other* modules' aggregates):

**Operator campaign management** (`Ads` tag, session-cookie auth, default-deny permission-gated
like every other `/admin/*` operation):
- `GET /admin/campaigns` — `listCampaigns` (paginated, filter by status/slot)
- `POST /admin/campaigns` — `createCampaign` (→ `DRAFT`)
- `GET /admin/campaigns/{campaignId}` — `getCampaign`
- `PATCH /admin/campaigns/{campaignId}` — `updateCampaign` (mutable fields, `DRAFT` only)
- `POST /admin/campaigns/{campaignId}/schedule` — `scheduleCampaign` (`DRAFT` → `SCHEDULED`;
  emits `BannerCampaignScheduled`)
- `POST /admin/campaigns/{campaignId}/pause` — `pauseCampaign` (`SCHEDULED`/`RUNNING` →
  `PAUSED`; no event — the frozen catalogue has no "paused" event)
- `POST /admin/campaigns/{campaignId}/resume` — `resumeCampaign` (`PAUSED` → `SCHEDULED`/
  `RUNNING` depending on the current time vs. the schedule window; no event, same reason)
- `POST /admin/campaigns/{campaignId}/end` — `endCampaign` (operator early-stop → `ENDED`;
  emits `BannerCampaignEnded`)

**Public serving/engagement capture** (`Ads` tag, no session required — banners are shown to
anonymous visitors):
- `GET /banners/serve` — `serveBanner` (query: `slotKey`, optional `categoryId`/`geo`/
  `language` targeting context; returns the one eligible campaign's creative or 204)
- `POST /banners/{campaignId}/impressions` — `recordBannerImpression` (202, fire-and-forget;
  emits `BannerImpressionRecorded`)
- `POST /banners/{campaignId}/clicks` — `recordBannerClick` (202, fire-and-forget; emits
  `BannerClickRecorded`)

New schemas: `BannerCampaign`, `BannerCampaignCreateRequest`, `BannerCampaignUpdateRequest`,
`BannerServeView`. No new `ErrorCode` members are needed — `VALIDATION_FAILED`,
`BUSINESS_RULE_VIOLATION`, `ILLEGAL_STATE_TRANSITION`, `CONFLICT`, `RESOURCE_NOT_FOUND`,
`PERMISSION_DENIED` (all already in the closed vocabulary, `contracts/errors/problem.py`) cover
every ads-specific rejection: I-21/I-20 gate failures as `BUSINESS_RULE_VIOLATION`, an illegal
lifecycle transition attempt as `ILLEGAL_STATE_TRANSITION`.

Impression/click capture is modelled as two lightweight POSTs *separate* from `serveBanner`,
rather than recording an impression synchronously inside the serve call. Rationale: FR-BANNER-004
("serve") and FR-BANNER-005 ("track") are two distinct requirements; a served banner is not
guaranteed to actually render client-side, so tying the impression metric to the render/viewability
event the frontend fires (not to the fact a banner was *returned*) is the more accurate metric and
keeps the hot `serveBanner` read path free of a write.

## Alternatives considered

1. **Implement the module with no HTTP router at all**, documenting the missing-endpoints gap for
   a future ADR (the option this agent's own standing orders would default to absent an explicit
   owner decision). Rejected once the owner explicitly chose to add the endpoints now — this
   would have under-delivered against that instruction without cause.
2. **Route campaign management through the generic `/admin/config/{entityType}` surface**, i.e.
   register `BannerCampaign` itself as a ninth "configuration entity." Rejected: `BannerCampaign`
   is not one of the eight Head+Version configuration entities enumerated in the Configuration &
   Metadata Framework (§3) — it is a BC-09 aggregate with its own lifecycle/invariants (I-21),
   not admin-authored reference data. Conflating the two would misclassify a platform capability
   as configuration, which Design Principle 3 of that same framework explicitly forbids.
3. **Record impressions synchronously as part of `serveBanner`** (serve = impression). Rejected
   per the "public serving/engagement capture" rationale above — see Decision.
4. **Give paused/resumed their own domain events** (`BannerCampaignPaused`/`Resumed`). Rejected:
   `contracts/events/ads.py` is frozen to exactly the three lifecycle events + two metric events
   DDD §6 names; adding new event types is a separate, larger contract change than adding REST
   operations, and neither FR-BANNER nor I-21 requires an event on pause/resume — only the status
   column (Physical DB Design) needs to reflect it.

## Consequences

- `contracts/openapi.yaml` (tag list + 9 new operations + 4 new schemas) and `contracts/README.md`
  (removing the now-stale "ads has zero v1 REST endpoints" claim, pointing to this ADR) are both
  touched in the same change.
- `apps/backend/src/ads/interfaces/ports.py`'s docstring, which explicitly named this exact ADR as
  the trigger condition, is updated in the P-14 implementation work that follows this ADR.
- This ADR does **not** itself edit SRS v1.0, BRD v1.0, or DDD Domain Model v1.0 (those are
  immutable source documents outside version control here, per Playbook §18's governance note);
  it is the durable record of *why* `contracts/openapi.yaml` now has ads operations pending that
  re-versioning.

## Approved-document references touched

- SRS v1.0 FR-BANNER-002…005.
- BRD v1.0 §8.9 (BR-BAN-01…03, DEC-05).
- DDD Domain Model v1.0 §5.9 (`BannerCampaign`), §6 (event catalogue, unchanged — no new event
  types added), §9 (I-21, I-15, I-20).
- Configuration & Metadata Framework v1.0 §3.4 (`PlacementSlotDefinition` — confirmed FR-BANNER-001
  is already served by the existing configuration admin surface, not duplicated here).
- `contracts/README.md` ("ads has zero v1 REST endpoints" note, amendment process).
- `contracts/errors/problem.py` (confirmed no `ErrorCode` addition needed).
