"""`DashboardSummary`'s wire shape must match the frozen `contracts/openapi.yaml` exactly
(CLAUDE.md: "Never hand-write or guess a request/response shape"). `new_users_7d` needs an
explicit alias override: pydantic's own `to_camel` generator capitalizes the letter immediately
after a digit (`new_users_7d` -> `newUsers7D`), which drifts from the contract's `newUsers7d`.
"""

from __future__ import annotations

from admin.interfaces.dto import DashboardSummary


def test_new_users_7d_serializes_to_the_contracts_exact_field_name() -> None:
    summary = DashboardSummary(new_users_7d=5)
    assert summary.model_dump(by_alias=True)["newUsers7d"] == 5


def test_dashboard_summary_round_trips_from_a_null_projection_dict() -> None:
    summary = DashboardSummary.model_validate(
        {
            "activeListings": None,
            "pendingModeration": None,
            "pendingVerification": None,
            "pendingInvoices": None,
            "newUsers7d": None,
        }
    )
    assert summary.model_dump(by_alias=True) == {
        "activeListings": None,
        "pendingModeration": None,
        "pendingVerification": None,
        "pendingInvoices": None,
        "newUsers7d": None,
    }
