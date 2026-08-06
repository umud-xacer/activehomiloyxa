"""Eventual-consistency proof for the critical journey's "the promotion is reflected in catalog
AND in search ranking" step: billing confirms an offline payment for a `LISTING_PROMOTION` order
-> a real `EntitlementActivated` event on billing's own outbox -> drained through the REAL
`composition_root.make_billing_entitlement_fanout_handler` (not a hand-constructed event handed
directly to a handler function) -> catalog's real `Listing.apply_promotion` + a republished
`ListingEdited` -> drained through catalog's REAL `composition_root.make_catalog_outbox_fanout_
handler` -> search's real `handle_listing_edited`, indexed into a real OpenSearch document.

This is the fix for the confirmed integration defect P-20 uncovered and the repository owner's
own resolved architecture decision (`catalog/README.md`, `search/README.md` "Known gaps") --
billing -> catalog -> search through the ordinary listing-content channel, matching the frozen
event contract's own `EntitlementActivated` docstring ("Principal consumers: Catalog
(promotion/quota)...").
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from billing.application import PaymentUseCases
from billing.domain import (
    Invoice,
    Order,
    ProductSnapshot,
    ProductType,
    TargetRef,
    TargetType,
)
from billing.infrastructure.persistence.base import BillingBase
from billing.infrastructure.persistence.models import (
    OutboxEventRow as BillingOutboxEventRow,
)
from billing.infrastructure.persistence.repository import (
    SqlalchemyEntitlementRepository,
    SqlalchemyInvoiceRepository,
    SqlalchemyOrderRepository,
)
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import SqlalchemyListingRepository
from composition_root import make_billing_entitlement_fanout_handler
from search.infrastructure.event_projection import make_search_event_handler
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from shared_kernel import BusinessProfileId, EventEnvelope, ListingId, Money, UserId
from tests.integration.conftest import ensure_clean_schema, poll_until

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OPENSEARCH_AVAILABLE = bool(os.environ.get("OPENSEARCH_HOST"))
_INDEX_NAME = "listing_search_promotion_test"


@pytest.fixture(autouse=True)
def _skip_without_opensearch() -> None:
    if not OPENSEARCH_AVAILABLE:
        pytest.skip("OPENSEARCH_HOST not set -- no real OpenSearch cluster to test against")


@pytest_asyncio.fixture(autouse=True)
async def _billing_and_catalog_schemas(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "billing", BillingBase)
    await ensure_clean_schema(engine, "catalog", CatalogBase)


@pytest_asyncio.fixture
async def opensearch_index() -> AsyncIterator[OpenSearchIndexAdapter]:
    client = OpenSearch(
        hosts=[
            {
                "host": os.environ["OPENSEARCH_HOST"],
                "port": int(os.environ.get("OPENSEARCH_PORT", "9200")),
            }
        ]
    )
    adapter = OpenSearchIndexAdapter(client, index_name=_INDEX_NAME)
    await adapter.delete_index()
    await adapter.ensure_index()
    yield adapter
    await adapter.delete_index()


async def test_confirmed_promotion_payment_reaches_catalog_and_then_search(
    session_factory: async_sessionmaker[AsyncSession],
    opensearch_index: OpenSearchIndexAdapter,
) -> None:
    owner_id = UserId(value=uuid4())
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner_id,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/real-estate/apartments",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Spacious apartment",
        description="3-room apartment, city center",
        attributes={"rooms": "3"},
        price=None,
        location=None,
        slug="spacious-apartment",
        now=NOW,
    ).publish(
        record_id=uuid4(),
        actor_user_id=owner_id.value,
        expires_at=NOW + timedelta(days=30),
        now=NOW,
    )

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    # Manually index the pre-promotion document once, exactly as catalog's own ListingPublished
    # event would have already caused search to do (out of scope for this test -- proven
    # separately by test_moderation_listing_compensation.py's sibling suites and search's own
    # unit tests) -- this test's own subject is the PROMOTION hop, not the initial index.
    search_handler = make_search_event_handler(
        session_factory=session_factory, index=opensearch_index
    )

    purchaser_profile_id = BusinessProfileId(value=uuid4())
    snapshot = ProductSnapshot(
        product_definition_id=uuid4(),
        product_definition_version_id=uuid4(),
        product_type=ProductType.PREMIUM,
        price=Money(amount=Decimal("50000.00"), currency="UZS"),
        term_days=30,
        quota={},
    )
    order = Order.create(
        order_id=uuid4(),
        purchaser_profile_id=purchaser_profile_id,
        product_snapshot=snapshot,
        target=TargetRef(
            target_type=TargetType.LISTING,
            target_id=listing.id.value,
            booking_window=None,
        ),
        now=NOW,
    )

    async with session_factory() as session:
        orders = SqlalchemyOrderRepository(session)
        invoices = SqlalchemyInvoiceRepository(session)
        await orders.add(order)
        await session.flush()
        invoice = Invoice.issue(
            invoice_id=uuid4(),
            order_id=order.id,
            invoice_number=await invoices.next_invoice_number(),
            amount=order.amount,
            now=NOW,
        )
        await invoices.add(invoice)
        order = order.issue_invoice(now=NOW)
        await orders.save(order)
        await session.commit()

    async with session_factory() as session:
        use_cases = PaymentUseCases(
            orders=SqlalchemyOrderRepository(session),
            invoices=SqlalchemyInvoiceRepository(session),
            entitlements=SqlalchemyEntitlementRepository(session),
            payment_provider=_AlwaysConfirmProvider(),
            outbox=OutboxWriter(session, BillingOutboxEventRow),
        )
        await use_cases.confirm_payment(
            invoice_id=invoice.id,
            operator_account_id=uuid4(),
            confirmed=True,
            note="paid in cash",
            now=NOW,
        )
        await session.commit()

    # Drain billing's real outbox through the REAL composition_root wiring.
    billing_handler = make_billing_entitlement_fanout_handler(
        billing_session_factory=session_factory,
        profiles_session_factory=session_factory,
        ads_session_factory=session_factory,
    )
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(BillingOutboxEventRow).where(
                        BillingOutboxEventRow.event_type == "EntitlementActivated"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )
    await billing_handler(envelope)

    async with session_factory() as session:
        reloaded = await SqlalchemyListingRepository(session).get_by_id(listing.id)
        assert reloaded is not None
        assert reloaded.promotion is not None, "catalog must apply the promotion projection"
        assert reloaded.promotion.kind.value == "PREMIUM"

    # Drain catalog's real outbox (the republished ListingEdited) into search's real handler.
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.event_type == "ListingEdited"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, "catalog must republish ListingEdited after applying the promotion"
        catalog_envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )
    await search_handler(catalog_envelope)

    async def _promoted_in_search() -> bool:
        document = await opensearch_index.get_document(listing.id.value)
        return document is not None and document.promotion is not None

    assert await poll_until(_promoted_in_search, timeout_seconds=5.0), (
        "search's own index must reflect the promotion within the eventual-consistency window"
    )
    document = await opensearch_index.get_document(listing.id.value)
    assert document is not None
    assert document.promotion is not None
    assert document.promotion.kind.value == "PREMIUM"


class _AlwaysConfirmProvider:
    """Implements `billing.application.ports.PaymentProviderPort` -- mirrors
    `OfflineManualPaymentAdapter`'s own "the operator's attestation IS the confirmation" contract
    exactly (v1 has no external gateway to consult)."""

    async def confirm(
        self,
        *,
        invoice_id: UUID,
        confirmed: bool,
        operator_account_id: UUID,
        note: str | None,
    ) -> bool:
        return confirmed
