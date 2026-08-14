"""billing/infrastructure/payment_gateway -- ADR-0010. Payme/Click online-provider integration:
the v2 online-provider seam `billing.application.ports.PaymentProviderPort`'s own docstring
names ("A v2 online-provider adapter would instead verify a referenced provider transaction
here"). `PaymentUseCases.confirm_payment` itself is never modified -- a webhook handler that has
already walked the provider's own state machine to its "money captured" step calls it exactly the
way the admin-operator `confirmInvoicePayment` endpoint does today (FR-BILL-004's "without
changing business logic").

Not wired through `PaymentProviderPort`/`OfflineManualPaymentAdapter` at all: that Protocol
answers "should this confirm attempt succeed" for a caller that already knows it wants to
confirm -- the real protocol complexity here (Payme's `CheckPerformTransaction`/
`CreateTransaction`/`PerformTransaction`/`CancelTransaction`/`CheckTransaction`/`GetStatement`
state machine, Click's `Prepare`/`Complete` handshake) lives entirely in `payme.py`/`click.py`,
tracked in `provider_transactions.ProviderTransactionRepository` -- a provider transaction can
exist, or be cancelled, entirely without our own `Invoice` ever reaching `PAID`.
"""

from __future__ import annotations
