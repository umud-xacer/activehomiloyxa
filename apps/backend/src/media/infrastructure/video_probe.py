"""Dependency-free video duration probe for the two whitelisted video containers
(`media.domain.value_objects.ContentType.MP4`/`WEBM`). No ffmpeg/ffprobe binary exists in this
codebase's runtime (ADR-0008's own "video gets no server-side transcoding pipeline" -- see
`image_processing.PillowImageProcessingAdapter`'s docstring), so this reads just enough of each
container's own header structure -- MP4's `moov/mvhd` box, WebM's `Segment/Info` EBML element --
to recover the declared duration without decoding any video/audio payload.

Read-only, best-effort: `probe_duration_seconds` returns `None` (never raises) for anything it
cannot confidently parse -- a fragmented/streaming-style container, a muxer layout this parser
doesn't recognise, or truncated/corrupt bytes. Callers must decide their own fail-open/fail-closed
policy for `None` (see `profiles.application.profile_use_cases.ProfileUseCases.add_promo_video`'s
own docstring for why it fails closed specifically for the promo-video business rule, while the
general media pipeline that calls this treats `None` as "duration simply unknown").
"""

from __future__ import annotations

import struct


def probe_duration_seconds(data: bytes, content_type: str) -> float | None:
    try:
        if content_type == "video/mp4":
            return _mp4_duration_seconds(data)
        if content_type == "video/webm":
            return _webm_duration_seconds(data)
    except Exception:
        return None
    return None


# --- MP4 (ISO base media file format): walk top-level boxes for moov -> mvhd -------------------


def _mp4_duration_seconds(data: bytes) -> float | None:
    moov = _find_box(data, 0, len(data), b"moov")
    if moov is None:
        return None
    moov_start, moov_end = moov
    mvhd = _find_box(data, moov_start, moov_end, b"mvhd")
    if mvhd is None:
        return None
    mvhd_start, mvhd_end = mvhd
    body = data[mvhd_start:mvhd_end]
    if len(body) < 4:
        return None
    version = body[0]
    if version == 1:
        # version(1) + flags(3) + creation(8) + modification(8) + timescale(4) + duration(8)
        if len(body) < 32:
            return None
        timescale = struct.unpack(">I", body[20:24])[0]
        duration = struct.unpack(">Q", body[24:32])[0]
    else:
        # version(1) + flags(3) + creation(4) + modification(4) + timescale(4) + duration(4)
        if len(body) < 20:
            return None
        timescale = struct.unpack(">I", body[12:16])[0]
        duration = struct.unpack(">I", body[16:20])[0]
    if timescale <= 0:
        return None
    return float(duration) / float(timescale)


def _find_box(data: bytes, start: int, end: int, box_type: bytes) -> tuple[int, int] | None:
    """One level of ISO-BMFF box iteration in `data[start:end]` -- returns the matching box's
    (content_start, content_end), or `None`. `moov` is small (metadata only, no sample data), so
    this is only ever asked to search inside it or the top-level file, never a `mdat` payload."""
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        box_name = data[pos + 4 : pos + 8]
        header_size = 8
        if size == 1:
            if pos + 16 > end:
                return None
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header_size = 16
        elif size == 0:
            size = end - pos
        if size < header_size or pos + size > end:
            return None
        if box_name == box_type:
            return pos + header_size, pos + size
        pos += size
    return None


# --- WebM/Matroska (EBML): walk Segment -> Info for TimecodeScale + Duration --------------------

_ID_SEGMENT = b"\x18\x53\x80\x67"
_ID_INFO = b"\x15\x49\xa9\x66"
_ID_TIMECODE_SCALE = b"\x2a\xd7\xb1"
_ID_DURATION = b"\x44\x89"


def _webm_duration_seconds(data: bytes) -> float | None:
    segment = _find_ebml_element(data, 0, len(data), _ID_SEGMENT)
    if segment is None:
        return None
    seg_start, seg_end = segment
    info = _find_ebml_element(data, seg_start, seg_end, _ID_INFO)
    if info is None:
        return None
    info_start, info_end = info

    timecode_scale = 1_000_000  # EBML default (ns per tick) when TimecodeScale is omitted.
    scale_el = _find_ebml_element(data, info_start, info_end, _ID_TIMECODE_SCALE)
    if scale_el is not None:
        raw = data[scale_el[0] : scale_el[1]]
        if raw:
            timecode_scale = int.from_bytes(raw, "big")

    duration_el = _find_ebml_element(data, info_start, info_end, _ID_DURATION)
    if duration_el is None:
        return None
    raw = data[duration_el[0] : duration_el[1]]
    if len(raw) == 4:
        duration_ticks = struct.unpack(">f", raw)[0]
    elif len(raw) == 8:
        duration_ticks = struct.unpack(">d", raw)[0]
    else:
        return None
    if timecode_scale <= 0:
        return None
    return float(duration_ticks) * float(timecode_scale) / 1_000_000_000


def _read_vint(data: bytes, pos: int, end: int, *, keep_marker: bool) -> tuple[int, int] | None:
    """Reads one EBML variable-length integer (element ID or size) starting at `pos`. The number
    of leading zero bits in the first byte gives the total length; `keep_marker=True` (element
    IDs) keeps that leading marker bit as part of the value, `False` (sizes) masks it off."""
    if pos >= end:
        return None
    first = data[pos]
    if first == 0:
        return None
    length = 8 - first.bit_length() + 1
    if pos + length > end:
        return None
    raw = data[pos : pos + length]
    value = raw[0] if keep_marker else (raw[0] & (0xFF >> length))
    for b in raw[1:]:
        value = (value << 8) | b
    return value, pos + length


def _find_ebml_element(
    data: bytes, start: int, end: int, element_id: bytes
) -> tuple[int, int] | None:
    """One level of EBML element iteration in `data[start:end]` -- returns the matching element's
    (content_start, content_end), or `None`. Element IDs are matched by their raw encoded bytes
    (kept-marker form), exactly as the constants above are written."""
    pos = start
    target = int.from_bytes(element_id, "big")
    while pos < end:
        id_result = _read_vint(data, pos, end, keep_marker=True)
        if id_result is None:
            return None
        elem_id, pos_after_id = id_result
        size_result = _read_vint(data, pos_after_id, end, keep_marker=False)
        if size_result is None:
            return None
        size, content_start = size_result
        content_end = min(content_start + size, end)
        if elem_id == target:
            return content_start, content_end
        pos = content_end if size > 0 else pos_after_id + 1
        if pos <= pos_after_id:
            return None  # malformed / would loop forever
    return None
