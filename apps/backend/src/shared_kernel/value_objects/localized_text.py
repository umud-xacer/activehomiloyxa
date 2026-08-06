"""LocalizedText -- shared kernel value object (DDD Sec 5.14; OpenAPI `LocalizedText`).

# enforces DEC-19 (uz_latn / uz_cyrl / ru / en)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LocalizedText(BaseModel):
    """User-visible text across the four locales. `uz_latn` is the canonical Uzbek; the others
    are optional depending on what was authored (OpenAPI `LocalizedText` -- no field is
    required there, matched here exactly)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uz_latn: str | None = None
    uz_cyrl: str | None = None
    ru: str | None = None
    en: str | None = None
