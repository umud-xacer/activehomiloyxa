# ADR-0009: Add `file` to the `FormField.fieldType` whitelist (BC-04 Configuration)

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-08-05

**Author**: Claude Sonnet 5, at the explicit direction of the repository owner (business
requirement: category-specific dynamic forms need to collect a document attachment — e.g. a
title deed, floor plan, or license scan — as a distinct field from a listing's photo gallery).

## Context

`FIELD_TYPES` (`configuration/domain/whitelist.py`) is a code-owned, closed [P] vocabulary
(DDD Sec 5.4) frozen at Task P-01 with eight members: `text`, `number`, `select`, `multiselect`,
`boolean`, `date`, `range`, `location`. It is hand-kept in three places that must agree:

1. `configuration/domain/whitelist.py` `FIELD_TYPES` (the enforcement copy, `WhitelistRegistry.
   check_field_type`).
2. `configuration/interfaces/dto.py` `FormField.field_type` `Literal[...]` (the wire-adjacent
   validation copy).
3. `contracts/openapi.yaml` `FormField.fieldType` `enum` (the frozen contract copy).

None of the eight existing values represent an attachment/document field. Listing photos are a
separate, already-modelled concept (`Listing.images`, BC-06 `MediaAsset`, the `image_count`
validator) — but category-authored dynamic forms (e.g. a "Commercial property" category asking
for a cadastral document, or a "Construction services" category asking for a license PDF/image
scan) have no field type that lets a Product Owner declare "collect one file here" the same way
they declare "collect one date here." Today the only workaround is misusing `text` for a
pasted URL, which bypasses BC-06's malware scan and asset-status lifecycle entirely.

## Decision

1. **`FIELD_TYPES` widens from eight values to nine**, adding `file`.
2. **A `file` field's value is a single BC-06 `MediaAssetId` (string), not raw bytes** — the
   dynamic form engine's existing upload flow (`media-client.ts`'s presigned
   `POST /media/uploads` → `PUT` → poll `GET /media/{id}` until `CLEAN`) is reused unchanged;
   the field's stored value in `Listing.attributes` is simply the resulting `mediaAssetId`,
   mirroring how `location` already stores a small structured value rather than inventing a new
   upload mechanism. `MediaOwnerContextType` is not widened — `file` fields use `"LISTING"`,
   the same context type listing photos already use, since both are attachments to a listing.
3. **No new `ValidatorType` is added.** `required` already covers "this attachment is
   mandatory"; a file-count or file-type validator is not requested by this task and would be
   speculative.
4. **No new `RenderingHint` is added.** `file` renders with the same default single-column
   layout every other field type gets absent a hint.
5. **`contracts/openapi.yaml` updated in the same change**: `FormField.fieldType.enum` gains
   `file`, per `contracts/README.md`'s "every module that consumes the changed shape updates in
   the same PR" rule.

## Alternatives considered

1. **Model file attachments as a `select`-like reference to a pre-existing media library
   entity.** Rejected — no media-library/asset-picker concept exists anywhere in the codebase;
   this would be new infrastructure, not a whitelist extension.
2. **Extend `multiselect`'s option value shape to carry file uploads.** Rejected — conflates two
   unrelated concepts (closed-option enumeration vs. open-ended user upload) and would make
   `multiselect`'s contract ambiguous for every existing consumer.
3. **Allow multiple files per field (an array of `MediaAssetId`).** Rejected for this task's
   scope: every request so far is "attach one document"; an array shape can be added later as a
   distinct field type (e.g. `file_list`) without touching this one, the same way `select`/
   `multiselect` are kept as two separate whitelist members rather than one field with a
   cardinality flag.

## Consequences

- `configuration/domain/whitelist.py`, `configuration/interfaces/dto.py` (already updated to
  include `"file"` in the `Literal` ahead of this ADR being ratified), `contracts/openapi.yaml`,
  `apps/frontend/src/lib/catalog-client.ts` (`FormField["fieldType"]`), the owner-admin field
  type picker (`apps/frontend/src/routes/owner-admin/index.tsx`), and the dynamic listing form
  renderer (`apps/frontend/src/features/listings/DynamicCategoryForm.tsx`) are all touched by
  this change.
- A `file` field's value round-trips through `Listing.attributes` as a plain string
  (`mediaAssetId`) — no new backend attribute-type validation is introduced beyond what already
  exists for `text`, since the whitelist only constrains `field_type`, not `default_value`'s
  runtime shape (Config Framework Sec 5.1 leaves attribute value typing to the field's own
  semantics, exactly as `location`'s `{lat, lng}` object already does without a dedicated
  schema).
- This ADR does **not** itself edit DDD Domain Model v1.0, SAD v1.0, or the Config Framework
  document (immutable source documents outside version control here, per Playbook §18's
  governance note) — it is the durable record of *why* `contracts/`/the codebase now differ from
  those documents' eight-member framing, pending human re-versioning of the approved documents.

## Approved-document references touched

- Config Framework Sec 5.1 (`FormField.field_type` worked examples) — the vocabulary grows by
  one member; the worked-example mechanism itself is unchanged.
- `contracts/openapi.yaml` (`FormField.fieldType`).
- `contracts/README.md` (amendment-process rule, applied here).
