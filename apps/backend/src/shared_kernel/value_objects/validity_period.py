"""ValidityPeriod -- shared kernel value object (DDD Sec 5.14).

A time window with a required start and an open-ended-if-null end (used wherever something has
a validity window -- e.g. a verification badge, a configuration version, an entitlement term).
Field shape and the ordering constraint are the physical schema's own rule, carried up into the
value object (Physical DB Sec 2/2.4: `CHECK (valid_until > valid_from)`, `valid_until` nullable
-- e.g. `entitlement.valid_until`, `configuration_version.validity_until`), not invented here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class ValidityPeriod(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid_from: datetime
    valid_until: datetime | None = None
    """Null = open-ended (no expiry). When present, must be strictly after `valid_from`."""

    @model_validator(mode="after")
    def _validate_ordering(self) -> ValidityPeriod:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError(
                f"ValidityPeriod.valid_until ({self.valid_until}) must be strictly after "
                f"valid_from ({self.valid_from})"
            )
        return self

    def is_open_ended(self) -> bool:
        return self.valid_until is None

    def contains(self, instant: datetime) -> bool:
        """Whether `instant` falls within [valid_from, valid_until) -- intrinsic to what a
        "period" means, not a business rule."""
        if instant < self.valid_from:
            return False
        return self.valid_until is None or instant < self.valid_until
