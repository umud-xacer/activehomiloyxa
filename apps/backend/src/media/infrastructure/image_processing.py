"""Pillow-based `ImageProcessingPort` adapter (DDD Sec 5.6 `ImageProcessingService`; FR-MEDIA-003
EXIF/GPS stripping, FR-MEDIA-005 THUMBNAIL/OPTIMIZED variants). Pillow is the only place a PIL
type appears (`provider-sdk-confined-to-infrastructure`, tools/importlinter.cfg). Pillow's
decode/encode is CPU-bound sync work, run off the event loop via `asyncio.to_thread`.

Dimensions (300px thumbnail, 1600px optimized, both longest-edge, aspect-preserved, never
upscaled) are this task's own engineering choice -- neither `contracts/openapi.yaml` nor any
approved document specifies exact pixel bounds for `THUMBNAIL`/`OPTIMIZED`, only that they exist
(FR-MEDIA-005)."""

from __future__ import annotations

import asyncio
import io

from PIL import Image

from media.application.ports import GeneratedVariant, ProcessedImage
from media.infrastructure.video_probe import probe_duration_seconds

_PIL_FORMAT_BY_CONTENT_TYPE = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_THUMBNAIL_MAX_PX = 300
_OPTIMIZED_MAX_PX = 1600


def _strip_and_reencode(data: bytes, pil_format: str) -> tuple[bytes, Image.Image]:
    """Rebuilds the image from raw pixel data into a metadata-free `Image` (no EXIF, no ICC
    profile, no XMP) -- the reliable strip technique: a fresh `Image.new(...)` + `putdata(...)`
    carries no `.info` from the source at all, rather than trying to enumerate and clear every
    metadata key `save()` might otherwise propagate (BRULE-12, closing I-2's location-disclosure
    vector)."""
    with Image.open(io.BytesIO(data)) as original:
        original.load()
        mode = "RGB" if pil_format == "JPEG" else original.mode
        stripped = Image.new(mode, original.size)
        stripped.putdata(original.convert(mode).get_flattened_data())
    buffer = io.BytesIO()
    stripped.save(buffer, format=pil_format)
    return buffer.getvalue(), stripped


def _resized_variant(image: Image.Image, *, max_px: int, pil_format: str) -> bytes:
    resized = image.copy()
    resized.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    resized.save(buffer, format=pil_format)
    return buffer.getvalue()


def _process_sync(data: bytes, content_type: str) -> ProcessedImage:
    pil_format = _PIL_FORMAT_BY_CONTENT_TYPE[content_type]
    stripped_bytes, stripped_image = _strip_and_reencode(data, pil_format)

    thumbnail_bytes = _resized_variant(
        stripped_image, max_px=_THUMBNAIL_MAX_PX, pil_format=pil_format
    )
    optimized_bytes = _resized_variant(
        stripped_image, max_px=_OPTIMIZED_MAX_PX, pil_format=pil_format
    )

    with Image.open(io.BytesIO(thumbnail_bytes)) as thumb:
        thumb_width, thumb_height = thumb.size
    with Image.open(io.BytesIO(optimized_bytes)) as opt:
        opt_width, opt_height = opt.size

    return ProcessedImage(
        stripped_original=stripped_bytes,
        variants=(
            GeneratedVariant(
                variant_kind="THUMBNAIL",
                data=thumbnail_bytes,
                width_px=thumb_width,
                height_px=thumb_height,
            ),
            GeneratedVariant(
                variant_kind="OPTIMIZED",
                data=optimized_bytes,
                width_px=opt_width,
                height_px=opt_height,
            ),
        ),
    )


class PillowImageProcessingAdapter:
    """ADR-0008: also the `ImageProcessingPort` adapter for video content types, even though it
    does no Pillow work for them -- there is no ffmpeg/transcoding pipeline in this codebase, so
    a video asset gets no EXIF-equivalent stripping and no THUMBNAIL/OPTIMIZED variants; the
    original bytes pass through unchanged and `MediaAsset.complete_processing` still marks the
    asset delivery-available with an empty `variants` tuple. The frontend renders a native
    first-frame poster client-side via `<video preload="metadata">` instead of a server-generated
    thumbnail."""

    async def process(self, *, data: bytes, content_type: str) -> ProcessedImage:
        if content_type not in _PIL_FORMAT_BY_CONTENT_TYPE:
            duration = (
                await asyncio.to_thread(probe_duration_seconds, data, content_type)
                if content_type in ("video/mp4", "video/webm")
                else None
            )
            return ProcessedImage(stripped_original=data, variants=(), duration_seconds=duration)
        return await asyncio.to_thread(_process_sync, data, content_type)
