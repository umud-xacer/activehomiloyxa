# media -- requirement traceability matrix (Task P-06)

Maps each requirement/invariant this module satisfies to its implementing code and the named
test that proves it. Mirrors `identity/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-MEDIA-001 | Accept image uploads, validate type/size/count | `media.domain.MediaAsset.initiate` (type+size); count is `Listing`'s own I-04 invariant, out of this module's scope (README "Known gaps") | `test_media_asset.py::test_initiate_accepts_every_whitelisted_content_type`, `test_initiate_accepts_exactly_the_size_cap` |
| FR-MEDIA-002 | Reject video/PDF and any non-image format | `media.domain.exceptions.UnsupportedMediaTypeError`; `ContentType` whitelist enum | `test_media_asset.py::test_initiate_rejects_non_image_content_type`, `test_api.py::test_init_media_upload_rejects_non_image_with_422` |
| FR-MEDIA-003 | Strip EXIF/GPS metadata | `media.infrastructure.image_processing.PillowImageProcessingAdapter._strip_and_reencode` | `test_image_processing.py::test_FR_MEDIA_003_process_strips_gps_exif_from_the_stripped_original` |
| FR-MEDIA-004 | Malware scanning, quarantine/reject detected threats | `media.infrastructure.malware_scan.ClamAvMalwareScanAdapter`; `MediaAsset.quarantine` | `test_malware_scan.py`, `test_processing_use_cases.py::test_I20_run_scan_batch_quarantines_infected_asset_and_publishes_rejected` |
| FR-MEDIA-005 | Deliver optimised images + thumbnails | `PillowImageProcessingAdapter._resized_variant`; `MediaAsset.complete_processing` | `test_image_processing.py::test_FR_MEDIA_005_process_returns_thumbnail_and_optimized_variants` |

## Non-functional / business rules

| Requirement | Summary | Code | Test |
|---|---|---|---|
| NFR-SEC-003 | Contain the image-upload attack surface (validation, scanning, EXIF/GPS strip, isolation before delivery) | `MediaAsset.initiate`/`quarantine`/`complete_processing`; `is_delivery_available` | `test_media_asset.py::test_I20_*` |
| Security Sec 7 T-6 | Type + MIME + magic-byte verification, quarantine on failure | `media.infrastructure.malware_scan._matches_declared_type` | `test_malware_scan.py::test_matches_declared_type_*` |
| Security Sec 7 | Presigned, scoped, expiring upload URLs | `media.infrastructure.object_storage.MinioStorageAdapter.generate_presigned_upload`; `MEDIA_PRESIGN_EXPIRY_SECONDS` | `test_intake_use_cases.py::test_init_media_upload_persists_asset_and_returns_presigned_url` |
| Security Sec 7 | Storage keys opaque, never exposed as identity | `media.domain.media_asset._storage_key_for`; `interfaces/routers.py::_cdn_url_for` (the only place a key is read in `interfaces/`) | `test_media_asset.py::test_initiate_derives_storage_key_from_the_assets_own_public_id`; `interfaces/dto.py` has no `storage_key` field at all |
| BRULE-12 | EXIF/GPS stripped before any variant is stored | `MediaAsset.complete_processing` (sets `exif_stripped=True` and `variants` atomically, same call) | `test_media_asset.py::test_complete_processing_sets_exif_stripped_and_variants_together`, `test_processing_use_cases.py::test_BRULE_12_*` |
| QR-05 | Processing failure never blocks; non-blocking | `MediaProcessingUseCases._process_one` (catches, marks `FAILED`, never re-raises); `MediaIntakeUseCases.init_media_upload` returns before scan/process ever run | `test_processing_use_cases.py::test_NonBlockingPolicy_*` |
| Security Sec 7 D-4 | Size caps enforced at intake and by the presigned policy | `MediaAsset.initiate` (`OversizeMediaError`); `StoragePort.object_size` re-verification | `test_media_asset.py::test_initiate_rejects_oversize_upload`, `test_api.py::test_init_media_upload_rejects_oversize_with_422` |

## Domain invariants (DDD Sec 9)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-20 | A stored MediaAsset is image-typed, malware-clean, and EXIF/GPS-free; quarantined assets are never delivered | `MediaAsset.is_delivery_available`/`require_delivery_available` | `test_media_asset.py::test_I20_*` (5 tests), `test_processing_use_cases.py::test_I20_run_scan_batch_quarantines_infected_asset_and_publishes_rejected` |

## Validation checklist cross-reference (P-06 prompt)

| Checklist item | Evidence |
|---|---|
| Presigned direct-upload intake behind an object-storage port | `media.application.ports.StoragePort`; `MinioStorageAdapter`; `test_intake_use_cases.py` |
| No MinIO/boto3 SDK type crosses infrastructure/ | `provider-sdk-confined-to-infrastructure` import-linter contract (KEPT); `boto3`/`botocore` imports appear only in `object_storage.py` |
| Intake pipeline is an async worker, no inbound API surface | `media.infrastructure.worker.MediaIntakeWorker`; `contracts/openapi.yaml` has no scan/process operation; `media_worker.py` entrypoint has no FastAPI app |
| Delivery references opaque, never raw storage keys | See "Storage keys opaque" row above |
| Asset-status events via outbox | `MediaIntakeUseCases.init_media_upload`/`MediaProcessingUseCases._publish_ready`/`_publish_rejected` all call `OutboxPort.append` in the same transaction as the state change (DEC-09) |
| API routers for exactly the media-tagged operations | `media_router` -- `initMediaUpload`/`getMedia`/`deleteMedia`, verified via `main.app.openapi()` reporting exactly `/media/uploads` and `/media/{mediaId}` |
| Alembic migrations | `infrastructure/migrations/versions/61c1c4e76ca8_...py`; parity-tested by `test_models.py` |
| MediaAsset aggregate with ImageVariant child entities | `media.domain.MediaAsset`/`ImageVariant`; one repository (`SqlalchemyMediaAssetRepository`), one unit of work |
| media imports only shared_kernel | `cross-module-media` import-linter contract (KEPT) |
| Every Media operation implemented, no drift | `tools/check_contract_drift.py` reports zero drift for media's own three routes (see README "Known gaps" #5 for the pre-existing, unrelated `configuration` drift already documented in `identity/README.md`) |
| Coverage floors | `scripts/coverage.sh` -- domain/application files at 95-100% (QG-04 passed) |
| mypy --strict / ruff / import-linter clean | See README "Coverage / quality gates" |
