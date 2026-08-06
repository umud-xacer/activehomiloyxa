"""media/application -- the async intake pipeline (`MediaIntakeService` scan step +
`ImageProcessingService`), invoked only by `infrastructure/worker.py`'s poll loop -- there is no
inbound API surface for this (`contracts/openapi.yaml` has no scan/process operation; SAD Sec
7.2's media "asset-status events" are the *output* of this pipeline, not a trigger for it).

`NonBlockingPolicy` (QR-05): a single asset's failure (scan or process) never raises out of a
batch method -- it is recorded on that asset (QUARANTINED / FAILED) and the batch continues with
the next candidate.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from contracts.events.media import MediaAssetReady, MediaAssetRejected
from media.application.ports import (
    ImageProcessingPort,
    MalwareScanPort,
    MalwareScanResult,
    MediaAssetRepository,
    StoragePort,
)
from media.domain import EXTENSION_BY_CONTENT_TYPE, ImageVariant, MediaAsset, VariantKind
from shared_kernel import OutboxPort


class MediaProcessingUseCases:
    def __init__(
        self,
        *,
        assets: MediaAssetRepository,
        storage: StoragePort,
        scanner: MalwareScanPort,
        processor: ImageProcessingPort,
        outbox: OutboxPort,
        batch_size: int = 50,
    ) -> None:
        self._assets = assets
        self._storage = storage
        self._scanner = scanner
        self._processor = processor
        self._outbox = outbox
        self._batch_size = batch_size

    async def run_scan_batch(self, *, now: datetime) -> int:
        """Malware scan + magic-byte verification (FR-MEDIA-004, Security Sec 7 T-6) for every
        `scan_status == PENDING` asset whose bytes have actually landed in storage. Returns the
        count actually scanned (candidates still awaiting the client's PUT are skipped, not
        counted -- they stay PENDING for a later poll)."""
        candidates = await self._assets.list_pending_scan(limit=self._batch_size)
        scanned = 0
        for asset in candidates:
            if not await self._storage.object_exists(asset.storage_key):
                continue
            await self._scan_one(asset, now=now)
            scanned += 1
        return scanned

    async def _scan_one(self, asset: MediaAsset, *, now: datetime) -> None:
        try:
            data = await self._storage.download_object(asset.storage_key)
            result = await self._scanner.scan(
                data=data, declared_content_type=asset.content_type.value
            )
        except Exception:
            result = MalwareScanResult.INFECTED
        if result is MalwareScanResult.INFECTED:
            updated = asset.quarantine(now=now)
            await self._assets.save(updated)
            await self._publish_rejected(updated, now=now)
        else:
            updated = asset.mark_scanned_clean(now=now)
            await self._assets.save(updated)

    async def run_processing_batch(self, *, now: datetime) -> int:
        """EXIF/GPS strip + variant generation (FR-MEDIA-003/005, BRULE-12) for every
        `scan_status == CLEAN AND processing_status == PENDING` asset."""
        candidates = await self._assets.list_pending_processing(limit=self._batch_size)
        for asset in candidates:
            await self._process_one(asset, now=now)
        return len(candidates)

    async def _process_one(self, asset: MediaAsset, *, now: datetime) -> None:
        try:
            data = await self._storage.download_object(asset.storage_key)
            processed = await self._processor.process(
                data=data, content_type=asset.content_type.value
            )
            await self._storage.upload_object(
                storage_key=asset.storage_key,
                data=processed.stripped_original,
                content_type=asset.content_type.value,
            )
            extension = EXTENSION_BY_CONTENT_TYPE[asset.content_type]
            variants = tuple(
                ImageVariant(
                    id=uuid4(),
                    variant_kind=VariantKind(generated.variant_kind),
                    storage_key=(
                        f"media/{asset.id.value}/{generated.variant_kind.lower()}{extension}"
                    ),
                    width_px=generated.width_px,
                    height_px=generated.height_px,
                    size_bytes=len(generated.data),
                    created_at=now,
                )
                for generated in processed.variants
            )
            for variant, generated in zip(variants, processed.variants, strict=True):
                await self._storage.upload_object(
                    storage_key=variant.storage_key,
                    data=generated.data,
                    content_type=asset.content_type.value,
                )
            updated = asset.complete_processing(variants=variants, now=now)
            await self._assets.save(updated)
            await self._publish_ready(updated, now=now)
        except Exception:
            updated = asset.fail_processing(now=now)
            await self._assets.save(updated)
            await self._publish_rejected(updated, now=now)

    async def _publish_ready(self, asset: MediaAsset, *, now: datetime) -> None:
        event = MediaAssetReady(
            event_id=uuid4(),
            occurred_at=now,
            actor=None,
            aggregate_type="MediaAsset",
            aggregate_id=asset.id.value,
            payload={"mediaAssetId": str(asset.id.value)},
        )
        await self._outbox.append(event)

    async def _publish_rejected(self, asset: MediaAsset, *, now: datetime) -> None:
        event = MediaAssetRejected(
            event_id=uuid4(),
            occurred_at=now,
            actor=None,
            aggregate_type="MediaAsset",
            aggregate_id=asset.id.value,
            payload={
                "mediaAssetId": str(asset.id.value),
                "scanStatus": asset.scan_status.value,
                "processingStatus": asset.processing_status.value,
            },
        )
        await self._outbox.append(event)
