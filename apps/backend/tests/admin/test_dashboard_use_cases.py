"""`AdminDashboardUseCases` -- backs `getAdminDashboard`, the one operation genuinely admin's own
(`contracts/README.md`'s tag-routing rule). Covers the module's own documented, user-decided
design: every field admin cannot cheaply/honestly compute is `None`, and every reachable probe is
still called for real (proving the composition wiring is live) with its result unused.
"""

from __future__ import annotations

from admin.application.dashboard_use_cases import AdminDashboardUseCases

from .conftest import (
    FakeInvoiceQueueProbe,
    FakeModerationQueueProbe,
    FakeUserQueueProbe,
    FakeVerificationQueueProbe,
)


def _use_cases(
    moderation: FakeModerationQueueProbe,
    verification: FakeVerificationQueueProbe,
    orders: FakeInvoiceQueueProbe,
    users: FakeUserQueueProbe,
) -> AdminDashboardUseCases:
    return AdminDashboardUseCases(
        moderation=moderation, verification=verification, orders=orders, users=users
    )


async def test_every_summary_field_is_honestly_null(
    fake_moderation_probe: FakeModerationQueueProbe,
    fake_verification_probe: FakeVerificationQueueProbe,
    fake_invoice_probe: FakeInvoiceQueueProbe,
    fake_user_probe: FakeUserQueueProbe,
) -> None:
    use_cases = _use_cases(
        fake_moderation_probe, fake_verification_probe, fake_invoice_probe, fake_user_probe
    )

    summary = await use_cases.get_dashboard()

    assert summary == {
        "activeListings": None,
        "pendingModeration": None,
        "pendingVerification": None,
        "pendingInvoices": None,
        "newUsers7d": None,
    }


async def test_get_dashboard_calls_all_four_owning_module_probes_for_real(
    fake_moderation_probe: FakeModerationQueueProbe,
    fake_verification_probe: FakeVerificationQueueProbe,
    fake_invoice_probe: FakeInvoiceQueueProbe,
    fake_user_probe: FakeUserQueueProbe,
) -> None:
    """The connectivity/permission-check proof this module's docstring promises: not a dead code
    path, but a real call through each owning module's own port."""
    use_cases = _use_cases(
        fake_moderation_probe, fake_verification_probe, fake_invoice_probe, fake_user_probe
    )

    await use_cases.get_dashboard()

    assert fake_moderation_probe.calls == [("OPEN", 1)]
    assert fake_verification_probe.calls == [("REQUESTED", 1)]
    assert fake_invoice_probe.calls == [("ISSUED", 1)]
    assert fake_user_probe.calls == [("ACTIVE", 1)]
