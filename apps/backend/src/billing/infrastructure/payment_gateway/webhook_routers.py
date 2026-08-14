"""billing/infrastructure/payment_gateway/webhook_routers.py -- ADR-0010. Thin HTTP envelopes
around `PaymeMerchantApi`/`ClickMerchantApi`: Basic-Auth/signature verification and wire-format
(JSON-RPC / form-encoded) parsing, nothing else -- all real protocol logic lives in
`payme.py`/`click.py`.

Not part of `contracts/openapi.yaml` -- every route here is `include_in_schema=False` and listed
in `tools/check_contract_drift.py`'s `NON_CONTRACT_PATHS`, the same precedent
`identity.interfaces.routers.apple_form_post_relay` set: this is each provider's OWN wire
protocol (Payme's JSON-RPC envelope, Click's form-encoded Prepare/Complete), not this app's JSON
API.

Lives in `infrastructure/`, not `interfaces/`, because these routes carry no `ActingUser`/
`ActingOperator` at all -- Payme/Click are unauthenticated HTTP callers verified by their own
protocol's signature (Payme: HTTP Basic against the merchant secret key; Click: an MD5
`sign_string` over the request fields), never this app's session/token auth.
`billing.interfaces`'s own `no-infra-inbound-billing` import-linter contract governs THIS app's
authenticated API surface, which these routes are not part of -- so the composition root wires
their dependencies the same way it wires everything else in `infrastructure/`, via plain
module-level override functions declared right here rather than in `billing.interfaces.di`."""

from __future__ import annotations

import base64
import binascii
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import FormData

from billing.infrastructure.payment_gateway.click import (
    ClickCompleteRequest,
    ClickError,
    ClickMerchantApi,
    ClickPrepareRequest,
    verify_complete_signature,
    verify_prepare_signature,
)
from billing.infrastructure.payment_gateway.payme import PaymeError, PaymeMerchantApi

payme_webhook_router = APIRouter(tags=["Payments"])
click_webhook_router = APIRouter(tags=["Payments"])


# == override points (composition-root wiring, mirrors billing.interfaces.di's own shape) =========


async def get_payme_merchant_api() -> PaymeMerchantApi:
    raise NotImplementedError(
        "get_payme_merchant_api was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_payme_merchant_key() -> str:
    raise NotImplementedError(
        "get_payme_merchant_key was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_click_merchant_api() -> ClickMerchantApi:
    raise NotImplementedError(
        "get_click_merchant_api was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_click_secret_key() -> str:
    raise NotImplementedError(
        "get_click_secret_key was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


# == Payme ==========================================================================================


def _payme_response(
    request_id: Any,
    *,
    result: dict[str, Any] | None = None,
    error: PaymeError | None = None,
) -> JSONResponse:
    if error is not None:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": error.code, "message": error.message},
            }
        )
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _verify_payme_auth(authorization: str | None, merchant_key: str) -> bool:
    """Payme's own Basic Auth convention: username is always the literal `"Paycom"`, password is
    the merchant's own secret key configured in the Payme cabinet."""
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization.removeprefix("Basic ")).decode()
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    return username == "Paycom" and password == merchant_key


@payme_webhook_router.post("/payments/payme/webhook", include_in_schema=False)
async def payme_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
    merchant_key: str = Depends(get_payme_merchant_key),
    api: PaymeMerchantApi = Depends(get_payme_merchant_api),
) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError:
        return _payme_response(None, error=PaymeError(-32700, "Parse error"))

    request_id = body.get("id") if isinstance(body, dict) else None
    if not _verify_payme_auth(authorization, merchant_key):
        return _payme_response(
            request_id, error=PaymeError(-32504, "Insufficient privilege")
        )

    method = body.get("method") if isinstance(body, dict) else None
    params = body.get("params") if isinstance(body, dict) else None
    if not isinstance(method, str):
        return _payme_response(request_id, error=PaymeError(-32600, "Invalid Request"))

    try:
        result = await api.dispatch(method, params if isinstance(params, dict) else {})
    except PaymeError as exc:
        return _payme_response(request_id, error=exc)
    return _payme_response(request_id, result=result)


# == Click ==========================================================================================


def _form_int(form: FormData, key: str, default: int) -> int:
    """`FormData.get` is typed `str | UploadFile | None` (a form field could in principle be a
    file upload) -- Click never sends one, but `int()` doesn't accept `UploadFile`, so every
    numeric field is coerced through `str` first regardless."""
    return int(str(form.get(key, default)))


def _click_response(
    *,
    click_trans_id: str,
    merchant_trans_id: str,
    error: int,
    error_note: str,
    **extra: object,
) -> dict[str, object]:
    return {
        "click_trans_id": click_trans_id,
        "merchant_trans_id": merchant_trans_id,
        "error": error,
        "error_note": error_note,
        **extra,
    }


@click_webhook_router.post("/payments/click/prepare", include_in_schema=False)
async def click_prepare(
    request: Request,
    secret_key: str = Depends(get_click_secret_key),
    api: ClickMerchantApi = Depends(get_click_merchant_api),
) -> dict[str, object]:
    form = await request.form()
    click_trans_id = str(form.get("click_trans_id", ""))
    merchant_trans_id = str(form.get("merchant_trans_id", ""))
    amount_raw = str(form.get("amount", ""))

    try:
        prepare_request = ClickPrepareRequest(
            click_trans_id=click_trans_id,
            service_id=str(form.get("service_id", "")),
            merchant_trans_id=merchant_trans_id,
            amount=Decimal(amount_raw),
            amount_raw=amount_raw,
            action=_form_int(form, "action", 0),
            sign_time=str(form.get("sign_time", "")),
            sign_string=str(form.get("sign_string", "")),
        )
    except (InvalidOperation, ValueError):
        return _click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            error=-8,
            error_note="Error in request from Click",
        )

    if not verify_prepare_signature(prepare_request, secret_key):
        return _click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            error=-1,
            error_note="SIGN CHECK FAILED",
        )

    try:
        result = await api.prepare(prepare_request)
    except ClickError as exc:
        return _click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            error=exc.code,
            error_note=exc.note,
        )
    return _click_response(
        click_trans_id=click_trans_id,
        merchant_trans_id=merchant_trans_id,
        error=0,
        error_note="Success",
        **result,
    )


@click_webhook_router.post("/payments/click/complete", include_in_schema=False)
async def click_complete(
    request: Request,
    secret_key: str = Depends(get_click_secret_key),
    api: ClickMerchantApi = Depends(get_click_merchant_api),
) -> dict[str, object]:
    form = await request.form()
    click_trans_id = str(form.get("click_trans_id", ""))
    merchant_trans_id = str(form.get("merchant_trans_id", ""))
    amount_raw = str(form.get("amount", ""))

    try:
        complete_request = ClickCompleteRequest(
            click_trans_id=click_trans_id,
            service_id=str(form.get("service_id", "")),
            merchant_trans_id=merchant_trans_id,
            merchant_prepare_id=str(form.get("merchant_prepare_id", "")),
            amount=Decimal(amount_raw),
            amount_raw=amount_raw,
            action=_form_int(form, "action", 1),
            error=_form_int(form, "error", 0),
            sign_time=str(form.get("sign_time", "")),
            sign_string=str(form.get("sign_string", "")),
        )
    except (InvalidOperation, ValueError):
        return _click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            error=-8,
            error_note="Error in request from Click",
        )

    if not verify_complete_signature(complete_request, secret_key):
        return _click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            error=-1,
            error_note="SIGN CHECK FAILED",
        )

    try:
        result = await api.complete(complete_request)
    except ClickError as exc:
        return _click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            error=exc.code,
            error_note=exc.note,
        )
    return _click_response(
        click_trans_id=click_trans_id,
        merchant_trans_id=merchant_trans_id,
        error=0,
        error_note="Success",
        **result,
    )
