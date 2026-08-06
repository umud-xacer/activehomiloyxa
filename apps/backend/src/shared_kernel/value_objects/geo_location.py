"""GeoLocation -- shared kernel value object (DDD Sec 5.14; OpenAPI `GeoPoint`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GeoLocation(BaseModel):
    """A WGS-84 coordinate pair."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
