# ADR-0003: Extend BC-11's closed `Subject`/`ResolutionAction` vocabularies to cover BC-02

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-07-13

**Author**: Claude Sonnet 5, drafting under Task P-12 (Moderation) at the explicit direction of
the repository owner, after surfacing the conflict below rather than silently resolving it.

## Context

Task P-12's own brief directs: "badge revocation / profile archival → profiles' moderation
command port (built in P-11)" — i.e. `ModerationActionService` should be able to invoke
`profiles.interfaces.moderation_port.ProfileModerationPort` (`revoke_badge`/`archive_profile`) as
a third command target alongside catalog (BC-03) and identity (BC-01).

DDD Domain Model §5.11 (BC-11's own aggregate section — "the authoritative" definition of this
context's closed vocabularies, both marked `[P]`, "fixed/closed and changeable only by release +
ADR") does not support this:

- **`Subject`** (what a `ModerationCase` is opened about): `ListingRef / ConversationRef /
  UserRef` — three ref types, no fourth for a business profile.
- **`ResolutionAction`** (the closed verb set, BR-MOD-02): `Hide / Reject / Suspend /
  RequestCorrection / Remove / SuspendAccount / Dismiss` — seven verbs, none badge- or
  profile-related.
- **`ModerationActionService`**'s own text: "issuing commands to BC-03 (listing state) or BC-01
  (account suspension)" — BC-02 is never named as a target.

SRS FR-MOD-003 ("hide, reject, suspend, request correction of, or remove content") and Baseline
§4-K/DEC-14 ("hide/reject/suspend/correct/remove actions") both independently corroborate the
same five-verb-plus-`SuspendAccount` content/account-only scope — this is not an isolated gap in
one document, all three (SRS, DDD, Baseline) agree with each other and exclude BC-02.
`contracts/openapi.yaml`'s `ModerationCase.subjectType`/`resolutionAction` and
`ModerationActionRequest.action` (frozen since Task P-01) mirror the same closed sets, so the
gap is present in the frozen contract too, not just the prose documents.

This is therefore not a stale-vs-current-document conflict like ADR-0002's `ProfileType` case
(where two documents disagreed and one was simply out of date) — it is the P-12 task brief
introducing a capability three unanimous approved documents do not describe. Surfaced to the
repository owner rather than resolved unilaterally (per this repo's standing orders and Playbook
AIR-19); the owner directed extending the model via this ADR: add a `PROFILE` subject type and
`RevokeBadge`/`ArchiveProfile` verbs, and wire profiles as a third command target.

## Decision

Extend BC-11's closed vocabularies:

- **`Subject`** gains a fourth ref type: `ProfileRef` (a `BusinessProfileId`), wire code
  `PROFILE`, alongside `LISTING`/`CONVERSATION`/`USER`.
- **`ResolutionAction`** gains two verbs: `RevokeBadge` (wire code `REVOKE_BADGE`) and
  `ArchiveProfile` (wire code `ARCHIVE_PROFILE`) — one verb per `ProfileModerationPort` method,
  matching the existing one-verb-per-target-transition granularity (`Suspend` vs
  `SuspendAccount` are already two distinct verbs for two distinct targets/transitions, not one
  generic "suspend" verb overloaded across contexts).
- **`ModerationActionService`** gains a third command target: BC-02 (profiles), invoked through
  `profiles.interfaces.moderation_port.ProfileModerationPort` exactly as it invokes catalog's
  `ListingModerationPort` and identity's account-suspension surface — a runtime command through
  the target's own `interfaces/` package, never a static import (SAD §8.1's own moderation row
  is unaffected: "shared_kernel (issues runtime commands via targets' interfaces)" already covers
  a third such target as much as the first two).

`contracts/openapi.yaml`, `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`, and
`docs/frontend_docs/`'s copy are updated in the same change: `PROFILE` added to
`ReportCreateRequest.subjectType`, `listModerationQueue`'s `subjectType` query parameter, and
`ModerationCase.subjectType`; `REVOKE_BADGE`/`ARCHIVE_PROFILE` added to
`ModerationCase.resolutionAction` and `ModerationActionRequest.action`.
`apps/backend/src/moderation/interfaces/{dto,ports}.py` (the P-01-derived stubs, implemented for
real under this same P-12 task) are updated to the corrected `Literal` values in the same change.

## Alternatives considered

1. **Follow SRS/DDD/Baseline exactly; do not wire profiles as a moderation target in this task**
   (leave `profiles.interfaces.moderation_port` unwired, as P-11 already documented it). Offered
   to the repository owner as the recommended, lowest-risk option; not chosen — the owner instead
   directed the extension so BC-11 can fully invoke the command port P-11 built for exactly this
   purpose.
2. **Reuse an existing verb** (e.g. treat `Suspend` as polymorphic across listings/profiles, or
   `Remove` for profile archival) instead of adding two new ones. Rejected: every existing verb
   in the closed set already maps to exactly one target/transition (`Suspend` → catalog's
   `Listing.suspend`, `SuspendAccount` → identity's account suspension) — overloading `Suspend`
   or `Remove` to also mean "revoke this profile's badge" would make the verb's meaning
   context-dependent on `subjectType`, a weaker, more error-prone design than one verb per
   transition, and inconsistent with the precedent the existing seven verbs already set.
3. **A single combined `ModerateProfile` verb** instead of two (`RevokeBadge`/`ArchiveProfile`
   separately). Rejected: `ProfileModerationPort` itself exposes two distinct, independently
   invocable commands (a badge can be revoked without archiving the profile, and vice versa) —
   collapsing them into one verb would lose that distinction and force
   `ModerationActionService` to guess which underlying command a moderator meant.

## Consequences

- `contracts/openapi.yaml`, `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`,
  `docs/frontend_docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`, and
  `apps/backend/src/moderation/interfaces/{dto,ports}.py` are all touched in the same change as
  P-12's implementation — an interface-change event per Playbook §18, which is why this ADR
  exists rather than a silent edit.
- `ModerationActionService`'s own implementation (Task P-12) must route `REVOKE_BADGE`/
  `ARCHIVE_PROFILE` to a `ProfileModerationCommandPort` (moderation's own narrow application-layer
  Protocol, mirroring the existing catalog/identity command-port shape), wired at the composition
  root against `profiles.interfaces.moderation_port.ProfilesModerationAdapter` — never a static
  `import profiles` inside `moderation/` itself (SAD §8.1, `cross-module-moderation` contract).
- This ADR does **not** itself edit `Active-Home-SRS-v1.0.docx`, `Active-Home-Domain-Model-
  v1.0.docx`, or `Active-Home-Approved-Baseline-v1.1.docx` (immutable source documents outside
  version control here, per Playbook §18's governance note) — this ADR is the durable record of
  why `contracts/` and this module now differ from those currently-published documents, pending
  their own re-versioning as a separate, human-owned governance step.

## Approved-document references touched

- DDD Domain Model v1.0 §5.11 (BC-11 `Subject`/`ResolutionAction` VOs, `ModerationActionService`).
- SRS v1.0 FR-MOD-003 (moderator actions), FR-MOD-004 (account suspension).
- Approved Baseline v1.1 §4-K, DEC-14.
- `contracts/openapi.yaml` (`ReportCreateRequest.subjectType`, `listModerationQueue`'s
  `subjectType` parameter, `ModerationCase.subjectType`/`resolutionAction`,
  `ModerationActionRequest.action`).
