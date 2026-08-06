# ADR-0008: Widen BC-06 (Media) intake to admit video, and tighten the image size cap

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-08-04

**Author**: Claude Sonnet 5, at the explicit direction of the repository owner (business
requirement: legal-entity landing pages need to publish both photos and video), after
surfacing that this contradicts a frozen, four-layer-deep architectural decision (DEC-10)
rather than silently reinterpreting it.

## Context

DEC-10 ("images only") is not an informal convention — it is stated as the resolution of a
documented conflict between an original brief (which apparently mentioned "Videos, PDFs") and
the approved spec, and it is enforced identically in four independent places:

1. `contracts/openapi.yaml`'s own `info.description` — *"Media: images only (DEC-10). Video and
   PDF are out of scope for v1."*
2. `media/domain/value_objects.py`'s `ContentType` enum — exactly three members
   (`image/jpeg|png|webp`).
3. `media/infrastructure/persistence/models.py`'s `ck_media_asset_content_type` CHECK constraint
   — DB-level enforcement of the same three values.
4. `media/infrastructure/malware_scan.py`'s magic-byte signature table, keyed on the same three
   content types, plus `media/infrastructure/image_processing.py`'s Pillow-based
   `ImageProcessingPort` adapter, which assumes every asset it receives is Pillow-openable.

This is therefore exactly the kind of "governed document requiring an ADR before an agent
touches it" case the repository's own Playbook §18 process exists for (the same process
ADR-0001/ADR-0002/ADR-0007 already followed for their own frozen-contract changes).

The concrete business need: legal-entity ("business profile") landing pages must let a company
publish both photos and short video clips (e.g. a walkthrough of a project, a manufacturing
line) in their public portfolio gallery. `profiles.BusinessProfile.portfolio` already stores
each item as a bare `media_asset_id` reference with no type restriction of its own
(`PortfolioItem` in `contracts/openapi.yaml` has no `contentType`-shaped constraint) — the only
place video is actually rejected today is BC-06 itself.

Separately, the repository owner also tightened the *image* cap in the same instruction: 1.2 MB
per image (down from the original 10 MB), and 30 MB per video. Both caps are simple upper
bounds on stored-object size/bandwidth cost, not a document-derived spec number (mirroring
ADR-0001's own image-processing dimension choices being "this task's own engineering choice").

**No transcoding/frame-extraction pipeline exists in this codebase** (no ffmpeg dependency, no
video-processing adapter of any kind) and building one is out of scope for this ADR — it would
require a new system dependency, a new async worker path, and a real design for
thumbnail-frame/poster extraction, none of which any approved document describes. This ADR
therefore also decides what "processed" means for a video asset in the absence of that
pipeline.

## Decision

1. **`ContentType` widens from three values to five**: adds `video/mp4` and `video/webm`
   (`media/domain/value_objects.py`). These are the two most broadly browser-playable
   container/codec combinations without requiring a proprietary licensing story, matching the
   same "pick the two-ish safe defaults" precedent `ContentType`'s original three image formats
   already set.
2. **Per-content-type size caps, not one flat constant**: `MAX_IMAGE_SIZE_BYTES` becomes
   1.2 MB (was 10 MB); a new `MAX_VIDEO_SIZE_BYTES` = 30 MB is added. `MediaAsset.initiate`
   looks the cap up by the declared `ContentType` (`max_size_bytes_for`) rather than checking
   against a single ceiling — the previous behavior (one cap for everything) is not preserved,
   by explicit instruction.
3. **Video gets no server-side processing** (`PillowImageProcessingAdapter.process` passes
   video bytes through unchanged, zero variants): there is no EXIF-equivalent metadata to strip
   for video in this codebase's scope, and no THUMBNAIL/OPTIMIZED variant generation without a
   new transcoding dependency this ADR deliberately does not introduce. A clean, scanned video
   asset becomes `is_delivery_available` with `variants=()`. The client renders a poster frame
   itself via `<video preload="metadata">`, which every target browser already supports without
   any server-side frame extraction.
4. **Malware scanning covers video too**: `ClamAvMalwareScanAdapter` already runs ClamAV's own
   INSTREAM byte scan regardless of declared type (unaffected by this ADR); its magic-byte
   cross-check (`_matches_declared_type`) gains MP4 (`ftyp` box marker at byte offset 4) and
   WebM (EBML magic number `1A 45 DF A3`) signatures, preserving the "declared type must match
   actual bytes" invariant DEC-10's own T-6 requirement established for images.
5. **DB CHECK constraint widened** via a new, purely additive migration (`9f2a7c15e4b0`) — no
   column type change, no backfill, since no existing row could already violate the wider set.
6. **`contracts/openapi.yaml` updated in the same change** (not a separate PR), per
   `contracts/README.md`'s own amendment-process rule: `MediaAsset.contentType`,
   `MediaUploadInitRequest.contentType`/`sizeBytes`, the `Media` tag description, the top-level
   `info.description` DEC-10 line, and the `initMediaUpload` operation description all now
   describe images-and-video with their respective caps instead of "images only."

## Alternatives considered

1. **Do nothing; keep video entirely out of scope, tell the business-profile feature to ship
   photo-only.** This was the initial recommendation (and was offered to the repository owner
   explicitly via a direct question before any code was touched), given the real cost of
   reopening a frozen, four-layer decision. Rejected because the repository owner explicitly
   chose to proceed with video support now rather than defer it.
2. **Build a real transcoding/thumbnail-extraction pipeline (ffmpeg-based worker, new
   `VariantKind` for a video poster frame) in the same change.** Rejected for this ADR's scope:
   it is a materially larger, separate piece of infrastructure (new system dependency, new
   async processing path, new failure modes to design for) that no approved document currently
   describes at all; bundling it here would make an already-large contract change also carry an
   unreviewed infrastructure design. It remains open as a natural follow-up task once this ADR
   is ratified, not foreclosed by this decision (nothing here prevents a later `VariantKind`
   addition for video posters).
3. **A single, larger flat size cap covering both images and video** (e.g. keep one
   `MAX_MEDIA_SIZE_BYTES`). Rejected per the repository owner's explicit, differentiated
   instruction (1.2 MB images / 30 MB video) — a shared cap would either be too small for video
   or too permissive for images.
4. **Reject video at the API layer only (Pydantic `Literal`) while leaving the domain
   `ContentType` enum image-only**, so a future task could add domain support separately.
   Rejected: DEC-10 is enforced at all four layers deliberately (defense in depth — a caller
   that somehow bypassed the DTO must still be stopped by the domain check, per
   `test_intake_use_cases.py`'s own "for callers that could bypass the DTO" precedent), so
   widening only the outermost layer would silently reintroduce the single-point-of-failure
   DEC-10 was designed to avoid.

## Consequences

- `media/domain/value_objects.py`, `media/domain/media_asset.py`, `media/domain/__init__.py`,
  `media/interfaces/dto.py`, `media/infrastructure/persistence/models.py`,
  `media/infrastructure/image_processing.py`, `media/infrastructure/malware_scan.py`, and
  `contracts/openapi.yaml` are all touched by this single change, per `contracts/README.md`'s
  "every module that consumes the changed shape updates in the same PR" rule.
- New migration `9f2a7c15e4b0` (media schema) must run before any video upload is attempted
  against a database still on the old CHECK constraint.
- Existing tests referencing `video/mp4` as an example of a *rejected* type
  (`test_intake_use_cases.py`, `test_api.py`) are updated to use `application/pdf` instead,
  since video is no longer the rejected example; `test_media_asset.py`,
  `test_malware_scan.py`, and `test_image_processing.py` gain new cases covering the video path
  directly (accepted content type, its own size cap, magic-byte matching, and the
  no-variants passthrough).
- No thumbnail/poster image exists for a video portfolio item; any frontend surface rendering
  one must use a native `<video>` element (or accept no visual preview at all) rather than
  expecting a `THUMBNAIL`-kind `MediaAssetVariants` entry, which video assets will never have
  under this decision.
- This ADR does **not** itself edit DDD Domain Model v1.0, SAD v1.0, or Security Architecture
  v1.0 (immutable source documents outside version control here, per Playbook §18's governance
  note) — it is the durable record of *why* `contracts/`/the codebase now differ from those
  documents' "images only" framing, pending human re-versioning of the approved documents.

## Approved-document references touched

- Security Architecture (Sec 7, T-6: "type + MIME + magic-byte verification") — the verification
  *mechanism* is unchanged, only the whitelist it checks against grows.
- `contracts/openapi.yaml` (`info.description`, `Media` tag, `MediaAsset`,
  `MediaUploadInitRequest`, `initMediaUpload` operation).
- `contracts/README.md` (amendment-process rule, applied here).
- The original brief's "Videos, PDFs" mention, which DEC-10 had walked back to zero and this ADR
  partially restores (video only; PDF remains explicitly out of scope).
