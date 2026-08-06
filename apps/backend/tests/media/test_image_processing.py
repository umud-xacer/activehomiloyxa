"""Tests for `PillowImageProcessingAdapter` against real Pillow-encoded bytes (no live service
needed -- Pillow itself is the "real" dependency here, not a fake). Covers FR-MEDIA-003
(EXIF/GPS stripping, BRULE-12) and FR-MEDIA-005 (THUMBNAIL/OPTIMIZED variants)."""

from __future__ import annotations

import io

import piexif
import pytest
from PIL import Image

from media.infrastructure.image_processing import PillowImageProcessingAdapter


def _jpeg_with_gps_exif() -> bytes:
    """A JPEG carrying a GPS IFD (Security Sec 7 I-2 "location-disclosure vector") -- the exact
    hazard BRULE-12 requires stripping before any variant is stored."""
    image = Image.new("RGB", (800, 600), color=(10, 20, 30))
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: ((41, 1), (18, 1), (0, 1)),
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: ((69, 1), (14, 1), (0, 1)),
    }
    exif_bytes = piexif.dump({"GPS": gps_ifd})
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif_bytes)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _skip_without_piexif() -> None:
    pytest.importorskip("piexif")


async def test_FR_MEDIA_003_process_strips_gps_exif_from_the_stripped_original() -> None:
    source = _jpeg_with_gps_exif()
    with Image.open(io.BytesIO(source)) as check:
        assert check.info.get("exif")  # sanity: the fixture really carries EXIF

    adapter = PillowImageProcessingAdapter()
    result = await adapter.process(data=source, content_type="image/jpeg")

    with Image.open(io.BytesIO(result.stripped_original)) as stripped:
        assert not stripped.info.get("exif")
        exif_dict = piexif.load(result.stripped_original)
        assert exif_dict["GPS"] == {}


async def test_FR_MEDIA_005_process_returns_thumbnail_and_optimized_variants() -> None:
    source = _jpeg_with_gps_exif()
    adapter = PillowImageProcessingAdapter()
    result = await adapter.process(data=source, content_type="image/jpeg")

    kinds = {variant.variant_kind for variant in result.variants}
    assert kinds == {"THUMBNAIL", "OPTIMIZED"}
    for variant in result.variants:
        assert variant.width_px <= 800
        assert variant.height_px <= 600
        assert variant.width_px > 0 and variant.height_px > 0


async def test_process_never_upscales_a_smaller_source_image() -> None:
    small = Image.new("RGB", (50, 40), color=(1, 2, 3))
    buffer = io.BytesIO()
    small.save(buffer, format="PNG")

    adapter = PillowImageProcessingAdapter()
    result = await adapter.process(data=buffer.getvalue(), content_type="image/png")

    thumbnail = next(v for v in result.variants if v.variant_kind == "THUMBNAIL")
    assert thumbnail.width_px == 50
    assert thumbnail.height_px == 40


# --- ADR-0008: video passes through untouched, no Pillow, no variants -----------------------


async def test_process_passes_video_through_unchanged_with_no_variants() -> None:
    source = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00rest-of-a-fake-mp4-file"
    adapter = PillowImageProcessingAdapter()
    result = await adapter.process(data=source, content_type="video/mp4")

    assert result.stripped_original == source
    assert result.variants == ()
