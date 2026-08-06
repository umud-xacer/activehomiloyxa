"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/identity/configuration providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers all eight
billing-related operations (six `Billing`-tagged, two `Administration`-tagged), including the
admin `confirmInvoicePayment` operation's own authorization (only an authorised operator may
confirm payment -- QG-08 authorization matrix scenario). Mirrors `apps/backend/tests/catalog/
test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from billing.application.entitlement_use_cases import EntitlementUseCases
from billing.application.order_use_cases import OrderUseCases
from billing.application.payment_use_cases import PaymentUseCases
from billing.domain import ProductType
from billing.interfaces.auth import ActingOperator, ActingUser
from billing.interfaces.di import (
    get_acting_operator,
    get_acting_user,
    get_entitlement_use_cases,
    get_order_use_cases,
    get_payment_use_cases,
)
from main import create_app
from shared_kernel import BusinessProfileId, UserId

from .conftest import (
    FakeEntitlementRepository,
    FakeInvoiceRepository,
    FakeOrderRepository,
    FakeOutbox,
    FakePaymentProviderPort,
    FakeProductDefinitionReaderPort,
)

_PURCHASER_ACCOUNT = UserId(value=uuid4())
_PURCHASER_PROFILE = BusinessProfileId(value=uuid4())
_OPERATOR_ACCOUNT = UserId(value=uuid4())
_UNAUTHORIZED_ACCOUNT = UserId(value=uuid4())

_TOKEN_TO_USER = {"purchaser-token": _PURCHASER_ACCOUNT}
_OPERATOR_TOKENS = {"operator-token"}
_UNAUTHORIZED_OPERATOR_TOKENS = {"unauthorized-token"}


@pytest.fixture
def client(
    fake_orders: FakeOrderRepository,
    fake_invoices: FakeInvoiceRepository,
    fake_entitlements: FakeEntitlementRepository,
    fake_products: FakeProductDefinitionReaderPort,
    fake_payment_provider: FakePaymentProviderPort,
    fake_outbox: FakeOutbox,
) -> Iterator[TestClient]:
    def _order_use_cases() -> OrderUseCases:
        return OrderUseCases(
            orders=fake_orders, invoices=fake_invoices, products=fake_products, outbox=fake_outbox
        )

    def _payment_use_cases() -> PaymentUseCases:
        return PaymentUseCases(
            orders=fake_orders,
            invoices=fake_invoices,
            entitlements=fake_entitlements,
            payment_provider=fake_payment_provider,
            outbox=fake_outbox,
        )

    def _entitlement_use_cases() -> EntitlementUseCases:
        return EntitlementUseCases(
            entitlements=fake_entitlements, orders=fake_orders, outbox=fake_outbox
        )

    async def acting_user_override(authorization: str | None = Header(default=None)) -> ActingUser:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        account_id = _TOKEN_TO_USER.get(token or "")
        if account_id is None:
            raise HTTPException(status_code=401, detail="no valid session")
        return ActingUser(account_id=account_id, acting_profile_id=_PURCHASER_PROFILE)

    async def acting_operator_override(
        authorization: str | None = Header(default=None),
    ) -> ActingOperator:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        if token in _OPERATOR_TOKENS:
            return ActingOperator(account_id=_OPERATOR_ACCOUNT)
        if token in _UNAUTHORIZED_OPERATOR_TOKENS:
            raise HTTPException(
                status_code=403, detail="caller lacks billing:invoice:confirm_payment"
            )
        raise HTTPException(status_code=401, detail="no valid session")

    app = create_app()
    app.dependency_overrides[get_order_use_cases] = _order_use_cases
    app.dependency_overrides[get_payment_use_cases] = _payment_use_cases
    app.dependency_overrides[get_entitlement_use_cases] = _entitlement_use_cases
    app.dependency_overrides[get_acting_user] = acting_user_override
    app.dependency_overrides[get_acting_operator] = acting_operator_override

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_product(fake_products: FakeProductDefinitionReaderPort, **overrides: object) -> UUID:
    product = fake_products.seed(**overrides)
    return product.id


class TestListProducts:
    def test_I01_public_no_auth_required(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        fake_products.seed(product_type=ProductType.PREMIUM)
        response = client.get("/api/v1/products")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_I02_filters_by_product_type(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        fake_products.seed(product_type=ProductType.PREMIUM)
        fake_products.seed(product_type=ProductType.VERIFICATION)
        response = client.get("/api/v1/products", params={"productType": "VERIFICATION"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["productType"] == "VERIFICATION"


class TestCreateOrder:
    def test_I03_requires_authentication(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/orders", json={"productId": str(uuid4()), "targetType": "LISTING"}
        )
        assert response.status_code == 401

    def test_I04_creates_an_order_and_returns_it_invoiced(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        product_id = _seed_product(fake_products, product_type=ProductType.PREMIUM)
        response = client.post(
            "/api/v1/orders",
            json={"productId": str(product_id), "targetType": "LISTING", "targetId": str(uuid4())},
            headers=_auth("purchaser-token"),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "INVOICED"
        assert body["invoiceId"] is not None
        assert body["purchaserProfileId"] == str(_PURCHASER_PROFILE.value)

    def test_I05_unknown_product_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/orders",
            json={"productId": str(uuid4()), "targetType": "LISTING", "targetId": str(uuid4())},
            headers=_auth("purchaser-token"),
        )
        assert response.status_code == 404


class TestGetOrderAndInvoice:
    def test_I06_owner_can_read_their_own_order_and_invoice(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        product_id = _seed_product(fake_products, product_type=ProductType.PREMIUM)
        created = client.post(
            "/api/v1/orders",
            json={"productId": str(product_id), "targetType": "LISTING", "targetId": str(uuid4())},
            headers=_auth("purchaser-token"),
        ).json()
        order_id = created["id"]

        get_response = client.get(f"/api/v1/orders/{order_id}", headers=_auth("purchaser-token"))
        assert get_response.status_code == 200

        invoice_response = client.get(
            f"/api/v1/orders/{order_id}/invoice", headers=_auth("purchaser-token")
        )
        assert invoice_response.status_code == 200
        assert invoice_response.json()["orderId"] == order_id

    def test_I07_not_found_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/orders/{uuid4()}", headers=_auth("purchaser-token"))
        assert response.status_code == 404


class TestListMyOrders:
    def test_I08_lists_only_the_callers_own_orders(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        product_id = _seed_product(fake_products, product_type=ProductType.PREMIUM)
        client.post(
            "/api/v1/orders",
            json={"productId": str(product_id), "targetType": "LISTING", "targetId": str(uuid4())},
            headers=_auth("purchaser-token"),
        )
        response = client.get("/api/v1/orders", headers=_auth("purchaser-token"))
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1


class TestListMyEntitlements:
    def test_I09_returns_empty_list_with_no_entitlements(self, client: TestClient) -> None:
        response = client.get("/api/v1/me/entitlements", headers=_auth("purchaser-token"))
        assert response.status_code == 200
        assert response.json() == []


class TestAdminListInvoices:
    def test_I10_requires_operator_authorization(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/billing/invoices", headers=_auth("purchaser-token"))
        assert response.status_code == 401

    def test_I11_authorized_operator_can_list(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/billing/invoices", headers=_auth("operator-token"))
        assert response.status_code == 200


class TestConfirmInvoicePayment:
    def _create_invoice(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> str:
        product_id = _seed_product(fake_products, product_type=ProductType.PREMIUM)
        created = client.post(
            "/api/v1/orders",
            json={"productId": str(product_id), "targetType": "LISTING", "targetId": str(uuid4())},
            headers=_auth("purchaser-token"),
        ).json()
        order_id = created["id"]
        invoice = client.get(
            f"/api/v1/orders/{order_id}/invoice", headers=_auth("purchaser-token")
        ).json()
        return str(invoice["id"])

    def test_I12_unauthenticated_caller_gets_401(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        invoice_id = self._create_invoice(client, fake_products)
        response = client.post(
            f"/api/v1/admin/billing/invoices/{invoice_id}/confirm-payment",
            json={"confirmed": True},
        )
        assert response.status_code == 401

    def test_I13_unauthorized_operator_gets_403(
        self, client: TestClient, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        """Only an operator holding `billing:invoice:confirm_payment` may confirm payment --
        QG-08 authorization matrix scenario."""
        invoice_id = self._create_invoice(client, fake_products)
        response = client.post(
            f"/api/v1/admin/billing/invoices/{invoice_id}/confirm-payment",
            json={"confirmed": True},
            headers=_auth("unauthorized-token"),
        )
        assert response.status_code == 403

    def test_I14_authorized_operator_confirms_payment_and_activates_entitlement(
        self,
        client: TestClient,
        fake_products: FakeProductDefinitionReaderPort,
        fake_entitlements: FakeEntitlementRepository,
    ) -> None:
        invoice_id = self._create_invoice(client, fake_products)
        response = client.post(
            f"/api/v1/admin/billing/invoices/{invoice_id}/confirm-payment",
            json={"confirmed": True, "note": "cash received"},
            headers=_auth("operator-token"),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "PAID"
        assert len(fake_entitlements.entitlements) == 1

    def test_I14b_declined_payment_returns_409_and_activates_nothing(
        self,
        client: TestClient,
        fake_products: FakeProductDefinitionReaderPort,
        fake_entitlements: FakeEntitlementRepository,
    ) -> None:
        invoice_id = self._create_invoice(client, fake_products)
        response = client.post(
            f"/api/v1/admin/billing/invoices/{invoice_id}/confirm-payment",
            json={"confirmed": False},
            headers=_auth("operator-token"),
        )
        assert response.status_code == 409
        assert fake_entitlements.entitlements == {}
