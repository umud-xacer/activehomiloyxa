"""Registers billing's typed domain/application exceptions onto the shared
`backbone.errors.ExceptionMapper` (the same registry `identity.interfaces.errors`/`catalog.
interfaces.errors`/`search.interfaces.errors` extend). Called once from the composition root
(`apps/backend/src/main.py`).

Status/code choices follow `contracts/errors/problem.py`'s closed `ErrorCode` vocabulary and
`confirmInvoicePayment`'s own declared response set (`409` for a declined/already-settled
payment; `contracts/openapi.yaml`'s own `Conflict` response). `UnsupportedProductTypeError`/
`MissingTermError` map to `503 DEPENDENCY_DEGRADED`, mirroring `search.interfaces.errors`'s own
`NoSearchConfigurationPublishedError` mapping -- both represent "the referenced configuration
data isn't in the shape this module needs," not a caller mistake.
"""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from billing.application.exceptions import (
    EntitlementNotFoundError,
    InvoiceNotFoundError,
    NoActingProfileError,
    NotOrderPurchaserError,
    OrderNotFoundError,
    PaymentNotConfirmedError,
    ProductNotFoundError,
)
from billing.domain import (
    EntitlementActivationWithoutPaymentError,
    IllegalEntitlementStateTransitionError,
    IllegalInvoiceStateTransitionError,
    IllegalOrderStateTransitionError,
    InvalidTargetRefError,
    MissingTermError,
    TargetTypeMismatchError,
    UnsupportedProductTypeError,
)


def register_billing_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- validation (422) -----------------------------------------------------------------------
    mapper.register(
        NoActingProfileError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="An acting business profile is required"
        ),
    )
    mapper.register(
        InvalidTargetRefError,
        simple_problem_builder(status=422, code="VALIDATION_FAILED", title="Invalid order target"),
    )
    mapper.register(
        TargetTypeMismatchError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="Target type does not match the selected product",
        ),
    )

    # --- not found (404) -------------------------------------------------------------------------
    mapper.register(
        ProductNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Product not found"),
    )
    mapper.register(
        OrderNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Order not found"),
    )
    mapper.register(
        InvoiceNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Invoice not found"),
    )
    mapper.register(
        EntitlementNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Entitlement not found"
        ),
    )

    # --- authorization (403) --------------------------------------------------------------------
    mapper.register(
        NotOrderPurchaserError,
        simple_problem_builder(
            status=403, code="PERMISSION_DENIED", title="Caller does not own this order"
        ),
    )

    # --- conflict (409) -------------------------------------------------------------------------
    mapper.register(
        PaymentNotConfirmedError,
        simple_problem_builder(status=409, code="CONFLICT", title="Payment was not confirmed"),
    )
    mapper.register(
        IllegalOrderStateTransitionError,
        simple_problem_builder(
            status=409, code="ILLEGAL_STATE_TRANSITION", title="Order cannot make that transition"
        ),
    )
    mapper.register(
        IllegalInvoiceStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Invoice cannot make that transition",
        ),
    )
    mapper.register(
        IllegalEntitlementStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Entitlement cannot make that transition",
        ),
    )
    mapper.register(
        EntitlementActivationWithoutPaymentError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="An entitlement can only be activated for a paid order",
        ),
    )

    # --- dependency degraded (503) ----------------------------------------------------------------
    mapper.register(
        UnsupportedProductTypeError,
        simple_problem_builder(
            status=503, code="DEPENDENCY_DEGRADED", title="Unsupported product type"
        ),
    )
    mapper.register(
        MissingTermError,
        simple_problem_builder(
            status=503, code="DEPENDENCY_DEGRADED", title="Product has no configured term"
        ),
    )
