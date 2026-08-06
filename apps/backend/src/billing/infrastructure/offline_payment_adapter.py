"""`OfflineManualPaymentAdapter` -- the ONLY `PaymentProviderPort` implementation registered in v1
(BRULE-15, FR-BILL-004: "the billing capability SHALL be structured so online providers can be
added in v2 without changing business logic"). No external gateway call, no I/O, no provider SDK
of any kind: in an offline flow, the operator's own HTTP-level attestation (`PaymentConfirmation
Request.confirmed`) IS the confirmation -- there is nothing else to verify it against. A v2
online-provider adapter (Click/Payme/Uzum/Freedom Pay/Stripe) would instead call out to that
provider's own API here to verify a referenced transaction; this task builds none of them
(explicitly out of scope) -- this file is the seam they attach to, proven empty on purpose.
"""

from __future__ import annotations

from uuid import UUID


class OfflineManualPaymentAdapter:
    """Implements `billing.application.ports.PaymentProviderPort`."""

    async def confirm(
        self, *, invoice_id: UUID, confirmed: bool, operator_account_id: UUID, note: str | None
    ) -> bool:
        return confirmed
