"""admin -- DTOs (Task P-01). Translated field-for-field from the OpenAPI operations tagged to
this module (contracts/openapi.yaml). Schema only: no aggregate type is exposed here, no
business behaviour.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from active_home_shared import CamelModel


class DashboardSummary(CamelModel):
    """Admin dashboard KPIs (rebuildable projections; FR-ADMIN-005)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")
    """OpenAPI `DashboardSummary` sets `additionalProperties: true` (unlike every other DTO in
    this codebase) -- it is a KPI projection, not a validated request/response shape, so extra
    fields are explicitly allowed rather than forbidden."""

    active_listings: int | None = None
    pending_moderation: int | None = None
    pending_verification: int | None = None
    pending_invoices: int | None = None
    new_users_7d: int | None = Field(default=None, alias="newUsers7d")
    """Explicit alias override: pydantic's own `to_camel("new_users_7d")` produces `newUsers7D`
    (capitalizes the letter immediately after a digit), which does not match the frozen
    `contracts/openapi.yaml` `DashboardSummary.newUsers7d` field name -- the one field in this
    DTO where the generic alias generator and the frozen contract disagree."""
