# ADR-0002: Correct BC-02 `ProfileType` vocabulary to match SRS §4 / DDD §5.2

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-07-13

**Author**: Claude Sonnet 5, drafting under Task P-11 (Business Profiles & Verification) at the
explicit direction of the repository owner, after surfacing the conflict below rather than
silently resolving it.

## Context

Task P-11 requires implementing `BusinessProfile.profile_type` as "the closed set of the eight
[approved business-profile] types" (DDD Domain Model §5.2, `AR: BusinessProfile [P]`, VO
`ProfileType [P]`). Two approved documents disagree on what that eight-value set actually is:

- **SRS v1.0 §4 (User Classes)** enumerates them by name: Construction Company, Manufacturer,
  Builder, Supplier, Contractor, Architect, Interior Designer, Service Provider. SRS §2.3 and §4
  both state this explicitly, and §4's own preamble notes the template's generic user-class list
  "omits two of the eight approved business-profile types (Interior Designer, Service
  Provider)" — i.e. SRS is deliberately precise that these eight, by name, are the approved set.
- **`docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`** (frozen verbatim into
  `contracts/openapi.yaml` under Task P-01), on `BusinessProfile.profileType` /
  `BusinessProfileCreateRequest.profileType` / the `listBusinessProfiles` `profileType` query
  parameter, instead enumerated: `INDIVIDUAL_SELLER`, `CONSTRUCTION_COMPANY`,
  `REAL_ESTATE_AGENCY`, `DEVELOPER`, `MATERIALS_SUPPLIER`, `SERVICE_PROVIDER`,
  `ARCHITECT_DESIGNER`, `PROPERTY_MANAGER`.

These two lists are not a naming/casing mismatch — they describe different taxonomies.
`INDIVIDUAL_SELLER` (an individual, not a business, per SRS §2.3/§4's own "Registered User
(Individual)" vs. "Business User" split), `REAL_ESTATE_AGENCY`, `DEVELOPER`, and
`PROPERTY_MANAGER` are real-estate-brokerage concepts absent from SRS §4's construction-services
list; conversely SRS's `Manufacturer`, `Builder`, `Supplier`, and `Contractor` have no
counterpart in the OpenAPI enum at all. No other approved document (BRD, Vision & Scope,
Enterprise Technical Task, Configuration & Metadata Framework) uses the OpenAPI spec's wording,
and no prior ADR addressed the discrepancy — `contracts/README.md`'s "One remaining documented
gap, and one resolved by ADR" section (Task P-01/P-06) did not know about this one.

Task P-11's own brief is explicit that the SRS list is authoritative ("read the exact eight from
the documents (the SRS covers all eight approved business-profile types, including Interior
Designer and Service Provider; do not omit any and do not invent a ninth)"), and DDD §5.2 cites
"the eight types below" from the same SRS §4 table, not the OpenAPI spec's. The OpenAPI spec's
enum appears to have been drafted against an earlier or differently-scoped (real-estate-flavored)
version of this taxonomy that was never reconciled with SRS §4/DDD §5.2 once those were finalised.

Surfaced to the repository owner rather than resolved unilaterally (per this repo's standing
orders and Playbook AIR-19, "AI operates inside frozen contracts; humans change the contracts");
the owner directed: follow SRS/DDD naming and amend the OpenAPI contract via this ADR.

## Decision

Correct `profileType`'s enum, in all three locations it appears (`BusinessProfile`,
`BusinessProfileCreateRequest`, `listBusinessProfiles`'s query parameter), in both
`docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml` (the approved source) and
`contracts/openapi.yaml` (its byte-identical copy, per `contracts/README.md`'s amendment-process
rule 3: "if the source itself needs to change, that change happens in the approved document
first... and this copy follows" — both edited together here since, unlike the immutable `.docx`
documents, this source file is version-controlled text within this same change), to:

```
CONSTRUCTION_COMPANY, MANUFACTURER, BUILDER, SUPPLIER, CONTRACTOR, ARCHITECT,
INTERIOR_DESIGNER, SERVICE_PROVIDER
```

Codes are the `UPPER_SNAKE_CASE` form of SRS §4's own names, following the same code-from-name
convention the corrected-away enum itself used (`CONSTRUCTION_COMPANY`, `SERVICE_PROVIDER` are
unchanged because they already matched both lists).

`apps/backend/src/profiles/interfaces/dto.py` and `interfaces/ports.py` (the P-01-derived stubs,
implemented for real under this same P-11 task) are updated to the corrected `Literal` values in
the same change, per amendment-process rule 4 ("every module that consumes the changed shape
updates in the same PR").

## Alternatives considered

1. **Keep the OpenAPI enum as-is, treat SRS §4's naming as descriptive prose only.** Rejected:
   P-11's own task brief, DDD §5.2, and SRS §4's own explicit callout ("this SRS covers all eight
   approved business-profile types... including Interior Designer and Service Provider") all
   converge on the SRS list being the intended business taxonomy; the OpenAPI enum's
   real-estate-agency-flavored set has no supporting document anywhere in `docs/`.
2. **Add all fourteen values (union of both lists) as a superset.** Rejected: DDD §5.2 and
   Physical DB Design both call this "the closed set of the eight types" — a fourteen-value union
   directly contradicts "eight," and would let a profile be created as `INDIVIDUAL_SELLER` (not a
   business at all, per SRS's own user-class split) or `REAL_ESTATE_AGENCY` (a type this
   platform's approved scope, per Baseline §4-B and SRS §5.3, never mentions).
3. **Leave unresolved, block P-11's domain work until the repository owner rules out-of-band.**
   Considered and offered to the owner as an option; not chosen — the owner instead directed
   resolution via this ADR so P-11 can proceed.

## Consequences

- `contracts/openapi.yaml`, `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`,
  `apps/backend/src/profiles/interfaces/dto.py`, and `apps/backend/src/profiles/interfaces/
  ports.py` are all touched in the same change as P-11's implementation — an interface-change
  event per Playbook §18, which is why this ADR exists rather than a silent edit.
- No other module's `interfaces/` or `contracts/events/` referenced the old enum values (verified
  by repo-wide search before this change), so no other module requires a corresponding edit.
- This ADR does **not** itself edit `Active-Home-SRS-v1.0.docx` or `Active-Home-Domain-Model-
  v1.0.docx` (those are immutable source documents outside version control here, per Playbook
  §18's governance note) — both already state the corrected vocabulary; only the OpenAPI spec
  was out of step with them. This ADR is the durable record of why `contracts/` changed.

## Approved-document references touched

- `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml` / `contracts/openapi.yaml`
  (`BusinessProfile.profileType`, `BusinessProfileCreateRequest.profileType`,
  `listBusinessProfiles` query parameter).
- SRS v1.0 §2.3, §4 (User Classes — the authoritative eight-type naming, unchanged).
- DDD Domain Model v1.0 §5.2 (BC-02 `ProfileType [P]`, unchanged — this ADR conforms code to it).
