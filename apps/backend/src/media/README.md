# media -- module charter

STATUS (Task P-06): fully implemented across all four layers -- presigned direct-to-MinIO image
upload, an async intake worker (magic-byte + malware scan, EXIF/GPS strip, THUMBNAIL/OPTIMIZED
variant generation), opaque delivery references, and asset-status events. This README is the
module's public charter -- read it before working in this module (Playbook Sec 13). See
`TRACEABILITY.md` for the requirement -> code -> test matrix.

## Bounded context

- **Module**: `media` (BC-06, Generic domain per DDD/SAD classification)
- **Responsibilities**: Image/video intake, validation, malware scan, EXIF/GPS stripping + variants (images only), delivery refs. Images and video only (DEC-10, widened by ADR-0008 -- see that ADR for why video gets no server-side variant generation).

## Owned aggregates / entities (DDD Sec 5.6)

- **`MediaAsset` [P]** -- `owner_context_type`/`owner_context_id` (the latter always `None` in
  this task's scope, see "Known gaps" #1), `storage_key` (internal, opaque, never exposed),
  `content_type` (image whitelist only, BRULE-11), `size_bytes`, `scan_status`
  (`PENDING`/`CLEAN`/`QUARANTINED`, single-shot), `processing_status`
  (`PENDING`/`COMPLETED`/`FAILED`, single-shot, requires `scan_status=CLEAN` to start),
  `exif_stripped`, `uploaded_by`. Owns one child entity inside its own aggregate boundary (one
  repository, one unit of work):
  - **`ImageVariant`** -- `THUMBNAIL`/`OPTIMIZED`, own `id`, own `storage_key`.
- **`ImageOnlyPolicy` [P]** / **`ExifStrippingPolicy` [P]** -- pure predicates enforced inside
  `MediaAsset.initiate`/`complete_processing`.
- **`QuarantinePolicy`** / **`NonBlockingPolicy`** -- structural: `MediaAsset.is_delivery_available`
  makes "delivery available" unreachable except via `scan_status=CLEAN` **and**
  `processing_status=COMPLETED` (I-20); the intake API path never blocks on scan/processing
  completion (QR-05) -- `initMediaUpload` returns as soon as the presigned URL is issued, and the
  worker advances assets independently.

## I-20 QuarantinePolicy (the module's own Critical-risk invariant)

"A stored MediaAsset is image-typed, malware-clean, and EXIF/GPS-free; quarantined assets are
never delivered." Encoded as a state machine, not a runtime byte-level check: image-typed is
guaranteed by construction (`ImageOnlyPolicy` at `initiate`); malware-clean is
`scan_status=CLEAN`; EXIF/GPS-free is `processing_status=COMPLETED` (stripping happens during
processing, before any variant is stored, BRULE-12). `MediaAsset.is_delivery_available` gates
**both** the original and every variant on the full `CLEAN`+`COMPLETED` pair -- the stricter,
safer reading of `contracts/openapi.yaml`'s `MediaAsset.url` docstring ("only when CLEAN"), which
under-specifies relative to I-20's own wording. See `test_media_asset.py::test_I20_*`.

## Public interface (`interfaces/`)

`MediaIntakePort` (`deleteMedia`/`getMedia`/`initMediaUpload`, frozen since Task P-01) plus the
three asset-status events below. The `interfaces/` package is this module's *only* importable
surface (AIR-02). Nothing in `application/`, `domain/`, or `infrastructure/` may be imported by
another module, ever.

## Routers (`interfaces/routers.py`) -- exactly the three Media-tagged operations

`initMediaUpload` (`POST /media/uploads`), `getMedia` (`GET /media/{mediaId}`), `deleteMedia`
(`DELETE /media/{mediaId}`). `initMediaUpload`/`deleteMedia` are session-authenticated
(`contracts/openapi.yaml`'s global `security: [{sessionCookie: []}]`) -- see "Authentication
bridge" below. `getMedia` is deliberately public: the contract documents only 200/404 for it (no
401), and a listing/business-profile page has to render its photos for an anonymous visitor, not
only a logged-in one -- `_asset_to_dto` already gates `url`/`variants` on `is_delivery_available`
(CLEAN + processed only), so this discloses no bytes for a QUARANTINED/PENDING asset regardless
of caller. No more, no less (QG-06 contract conformance).

## Authentication bridge (media never imports identity)

`cross-module-media` (`tools/importlinter.cfg`) forbids every layer of this module from
importing `identity`. Media's own `interfaces/auth.py` declares a minimal `ActingUser(account_id:
UserId)` -- just enough for self-service, upload-your-own-assets semantics (no granted
`PermissionKey` is required; `deleteMedia`'s "ownership validated" is an equality check against
`MediaAsset.uploaded_by`, not an `AuthorizationPort` gate). `interfaces/di.py::get_acting_user` is
the usual `NotImplementedError`-stub `Depends(...)` target; the real resolution
(`composition_root.provide_acting_user`) reuses identity's own already-built session machinery
(`ApplicationAuthorizationService.resolve_acting_context`, `RedisSessionRepository`,
`SqlalchemyUserAccountRepository`) -- the composition root sits outside every module's package
tree and is exempt from `tools/importlinter.cfg`'s boundary contracts, exactly the same pattern
`provide_authenticated_request` already uses for identity's own routers.

## Events published (DDD Sec 6 as amended by ADR-0001, `contracts/events/media.py`)

DDD Sec 6's published table has no BC-06 row at all (a gap `contracts/README.md` recorded under
Task P-01); `docs/adr/0001-media-asset-status-events.md` (Proposed -- agent-drafted, pending
human-architect ratification per Playbook Sec 18) resolves it in SAD Sec 7.2's favor ("MediaIntakePort,
asset-status events"):

- `MediaAssetAccepted` -- `initMediaUpload` admits a type/size-valid upload to the pipeline.
- `MediaAssetReady` -- scan clean + processing completed; the asset becomes delivery-available.
- `MediaAssetRejected` -- scan quarantined the asset, or processing failed terminally.

Published via the transactional outbox (`backbone.outbox.OutboxWriter`), same transaction as the
state change that triggers each one -- never dual-write (DEC-09).

## The intake worker (`infrastructure/worker.py`, `apps/backend/src/media_worker.py`)

No inbound API surface (Security Sec 7: "Background workers ... no inbound network surface") --
a poll loop over `MediaAssetRepository`, mirroring `backbone.outbox.dispatcher.OutboxDispatcher`'s
own `session_factory`-per-batch shape (one fresh `AsyncSession` per batch, not one held open for
the worker's whole process lifetime). Two stages per `run_once()`:

1. **Scan** (`run_scan_batch`): for every `scan_status=PENDING` asset whose bytes have actually
   landed in storage (`StoragePort.object_exists`), downloads and runs magic-byte verification +
   `MalwareScanPort.scan` (self-hosted ClamAV, `infrastructure/malware_scan.py`, spoken over its
   native INSTREAM protocol via a raw `asyncio` socket -- no third-party ClamAV client library
   needed for a protocol this small). A magic-byte mismatch **or** a positive malware result both
   converge on `MediaAsset.quarantine` -- the frozen `ScanStatus` vocabulary has no separate
   "rejected" value (Security Sec 7 T-6).
2. **Process** (`run_processing_batch`): for every `scan_status=CLEAN AND
   processing_status=PENDING` asset, runs `ImageProcessingPort.process` (Pillow,
   `infrastructure/image_processing.py` -- rebuilds the image from raw pixel data into a fresh,
   metadata-free `Image` rather than trying to enumerate and clear EXIF/ICC/XMP keys individually,
   then generates THUMBNAIL [<=300px] / OPTIMIZED [<=1600px] variants, longest-edge,
   aspect-preserved, never upscaled -- both dimension caps are this task's own engineering choice,
   no approved document specifies exact pixel bounds). `NonBlockingPolicy`: a single asset's
   failure (scan or process) never raises out of a batch -- it is recorded on that asset
   (`QUARANTINED`/`FAILED`) and the batch continues with the next candidate.

Run: `python -m media_worker` (from `apps/backend/src`, matching how `main.py`/uvicorn is
invoked for the `api` process). No Dockerfile/compose service for the `worker` container itself
in this task -- see "Known gaps" #3.

## Delivery references (opaque, Security Sec 7)

`storage_key` is built from the asset's own already-public id
(`media/{asset_id}/original{ext}`/`media/{asset_id}/{variant}.{ext}`) -- never a separately
invented token, and never serialized to a DTO. `interfaces/routers.py::_cdn_url_for` is the only
place a `storage_key` is read in `interfaces/` at all, purely to build a URL string
(`{MEDIA_CDN_BASE_URL}/{storage_key}`, CDN fronting the same MinIO bucket 1:1, Infra Sec 4 "minio
-.origin.-> cdn"); the key itself is never assigned to a response field.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: **shared_kernel only** -- confirmed unchanged from the P-01 stub;
`cross-module-media` forbids every one of the other 12 modules, including `identity` (the
authentication bridge lives entirely in `composition_root.py`, see above).

## Configuration consumed (DEC-21: never hardcode a configurable value)

`MEDIA_PRESIGN_EXPIRY_SECONDS` (default 900s/15min), `MINIO_MEDIA_BUCKET`, `MINIO_USE_TLS`,
`MEDIA_CDN_BASE_URL`, `CLAMAV_HOST`/`CLAMAV_PORT` -- all environment variables
(`deployment/env/.env.*.example`), following the same precedent as `MINIO_ENDPOINT`/
`ESKIZ_API_BASE_URL` (infra/runtime tuning knobs, not `configuration`-module business settings --
presign expiry and bucket/CDN topology are security/infra parameters, not marketplace business
rules, unlike identity's `platform-settings-global.otp.expiry_minutes` precedent). The 1.2 MB
image / 30 MB video size caps and the five-way content-type whitelist (ADR-0008) are literal
`contracts/openapi.yaml`/Security Sec 7 spec constants (`media.domain.value_objects.
MAX_IMAGE_SIZE_BYTES`/`MAX_VIDEO_SIZE_BYTES`/`ContentType`), not runtime-configurable.

## Infra added this task (`deployment/`)

`clamav` service in `deployment/compose/docker-compose.yml` -- a backing service (like
postgres/redis/opensearch/minio, not an application container), named alongside MinIO/CDN as
infra to provision (Enterprise Technical Task Sec 4: "MinIO, malware scanner, CDN") but not yet
present (Task P-00 provisioned only the datastores its own scope covered).

## Migrations

`infrastructure/migrations/versions/61c1c4e76ca8_...py` creates `media.media_asset`,
`media.image_variant` (`ON DELETE CASCADE` from the parent), `media.outbox_event` --
`CheckConstraint`s mirror Physical DB Sec 2.6's column notes verbatim (image whitelist,
status enums, `size_bytes > 0`), the same discipline `configuration.infrastructure.persistence.models`
already applies. Hand-written, not `alembic revision --autogenerate` (see the migration file's
own docstring). Kept in sync with `infrastructure/persistence/models.py` by
`apps/backend/tests/media/test_models.py`'s static parity check.

## Known gaps (flagged, not silently worked around)

1. **`owner_context_id` association**: `contracts/openapi.yaml`'s `MediaUploadInitRequest` carries
   only `ownerContextType`, not an id -- no v1 operation associates an asset with a specific
   owning aggregate instance afterwards. Physical DB Sec 2.6 documents the column as "set on
   association; NULL while pending association"; that association step belongs to a future
   consuming-context task (catalog/profiles/ads), out of this task's explicit scope ("Do not
   implement any consuming context's use of media").
2. **Orphan/quarantine purge job**: Physical DB Sec 2.6 and Security Sec 7 both mention a
   scheduled job that purges quarantined/orphaned-Clean assets (deletes variant rows, asset row,
   and MinIO objects together) after a grace period. This task's scope enumerated exactly four
   worker responsibilities (validation, malware scan, EXIF strip, variant generation) -- the
   purge job is a distinct, separately-schedulable background job not among them. `deleteMedia`'s
   synchronous delete removes what it can reach immediately; the scheduled purge sweep is left as
   a well-specified follow-up.
3. **No `worker`/`api` container yet**: `deployment/compose/docker-compose.yml`'s own header
   comment already states no application containers exist yet (Task P-00 explicitly excluded
   them, still true for `api` despite P-04/P-05/P-06 building real API code behind it) -- adding
   one is a distinct infra task, not part of implementing the worker's own logic. `clamav` was
   added because it is a backing service in the same category as postgres/redis/opensearch/minio,
   not an application container.
4. **Idempotency-Key**: `initMediaUpload` accepts the header per the contract's parameter, but no
   request-level dedup store is implemented -- same accepted gap class as identity's own
   `verifyOtp`/`registerEmail` (see `identity/README.md` gap #3), lower stakes than an invariant.
5. **Pre-existing, unrelated**: running the full-repo `tools/check_contract_drift.py` reconfirms
   `identity/README.md`'s own already-documented gap #5 (`configuration`'s admin routers use
   snake_case path parameters where `contracts/openapi.yaml` specifies camelCase) -- media's own
   three routes (`{mediaId}`) match the spec exactly and report no drift; the `configuration`
   mismatch is unrelated to this task and was left untouched (AIR-01).

## Coverage / quality gates (Task P-06 run)

68 tests (`apps/backend/tests/media/` unit + integration + API), mypy --strict clean, ruff clean
(one pre-existing, codebase-wide style note carried over unchanged from identity's own precedent:
`UP042` "inherit from StrEnum" on every `(str, Enum)` value object -- kept for consistency with
`identity.domain.value_objects`'s identical, already-merged pattern rather than diverging), all 49
`tools/importlinter.cfg` contracts kept, domain/application coverage 95-100% per file (QG-04),
bandit SAST clean, pip-audit clean (Pillow pinned at 12.2.0, past the 12.0.0 CVEs pip-audit
flagged during this task). The MinIO/ClamAV adapters' own wire-protocol code is exercised by
`integration/` tests (magic-byte logic is unit-tested directly; the ClamAV INSTREAM socket half
and MinIO's boto3 calls need live services, out of this sandbox's reach, same class of gap as
identity's own un-mocked provider adapters).

## Layout

```
media/
|-- interfaces/       # PUBLIC surface: routers, published ports, DTOs, event contracts
|-- application/      # use cases (commands/queries) + ports
|-- domain/           # aggregates, value objects, domain events, policies, invariants
|-- infrastructure/   # adapters: persistence, MinIO/ClamAV/Pillow adapters, outbox, worker
|-- README.md         # this file
`-- TRACEABILITY.md    # requirement -> code -> test matrix
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
