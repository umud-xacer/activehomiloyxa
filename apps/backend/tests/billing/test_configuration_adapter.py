"""Unit tests for `ConfigurationProductDefinitionAdapter` against a fake of the narrow
`_ConfigurationReader` slice it actually calls -- no real Postgres needed. Mirrors
`apps/backend/tests/search/test_configuration_adapter.py`'s pattern."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from billing.domain import ProductType
from billing.infrastructure.configuration_adapter import ConfigurationProductDefinitionAdapter
from configuration.interfaces.dto import (
    ConfigurationHead,
    ConfigurationHeadPage,
    ConfigurationVersion,
    PageInfo,
)


@dataclass
class FakeConfigurationReader:
    """Implements `billing.infrastructure.configuration_adapter._ConfigurationReader`."""

    heads: list[ConfigurationHead] = field(default_factory=list)
    versions: dict[UUID, ConfigurationVersion] = field(default_factory=dict)

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage:
        matching = [h for h in self.heads if h.entity_type == entity_type]
        return ConfigurationHeadPage(
            items=matching, page=PageInfo(limit=limit or 20, next_cursor=None)
        )

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        return self.versions[version_id]


def _head(*, code: str, version_id: UUID | None) -> ConfigurationHead:
    return ConfigurationHead(
        id=uuid4(),
        entity_type="product-definition",
        code=code,
        current_version_id=version_id,
        status="PUBLISHED",
    )


def _version(
    *, version_id: UUID, status: str = "PUBLISHED", snapshot: dict[str, Any] | None
) -> ConfigurationVersion:
    return ConfigurationVersion(
        id=version_id,
        head_id=uuid4(),
        version_number=1,
        status=status,  # type: ignore[arg-type]
        definition={},
        snapshot=snapshot,
    )


def _snapshot(
    *,
    product_type: str = "PREMIUM",
    price_amount: str = "50000.00",
    price_currency: str = "UZS",
    term_days: int | None = 30,
    quota_set: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "descriptor": {"name": {"uz_latn": "Premium"}, "description": None},
        "product_type": product_type,
        "price_amount": price_amount,
        "price_currency": price_currency,
        "term_days": term_days,
        "quota_set": quota_set,
    }


class TestGetProduct:
    async def test_returns_the_matching_product_by_head_id(self) -> None:
        version_id = uuid4()
        head = _head(code="premium-30d", version_id=version_id)
        reader = FakeConfigurationReader(
            heads=[head],
            versions={version_id: _version(version_id=version_id, snapshot=_snapshot())},
        )
        adapter = ConfigurationProductDefinitionAdapter(reader)
        product = await adapter.get_product(head.id)
        assert product is not None
        assert product.code == "premium-30d"
        assert product.product_type is ProductType.PREMIUM
        assert product.price_amount == "50000.00"
        assert product.term_days == 30

    async def test_returns_none_when_no_head_matches(self) -> None:
        reader = FakeConfigurationReader(heads=[])
        adapter = ConfigurationProductDefinitionAdapter(reader)
        assert await adapter.get_product(uuid4()) is None

    async def test_skips_a_head_with_no_current_version(self) -> None:
        head = _head(code="draft-only", version_id=None)
        reader = FakeConfigurationReader(heads=[head])
        adapter = ConfigurationProductDefinitionAdapter(reader)
        assert await adapter.get_product(head.id) is None

    async def test_skips_a_non_published_version(self) -> None:
        version_id = uuid4()
        head = _head(code="unpublished", version_id=version_id)
        reader = FakeConfigurationReader(
            heads=[head],
            versions={
                version_id: _version(version_id=version_id, status="DRAFT", snapshot=_snapshot())
            },
        )
        adapter = ConfigurationProductDefinitionAdapter(reader)
        assert await adapter.get_product(head.id) is None

    async def test_carries_the_subscription_quota_set(self) -> None:
        version_id = uuid4()
        head = _head(code="subscription-basic", version_id=version_id)
        reader = FakeConfigurationReader(
            heads=[head],
            versions={
                version_id: _version(
                    version_id=version_id,
                    snapshot=_snapshot(
                        product_type="SUBSCRIPTION",
                        term_days=30,
                        quota_set={"max_active_listings": 20, "promotion_credits": None},
                    ),
                )
            },
        )
        adapter = ConfigurationProductDefinitionAdapter(reader)
        product = await adapter.get_product(head.id)
        assert product is not None
        assert product.quota == {"max_active_listings": 20}


class TestListProducts:
    async def test_lists_every_published_product(self) -> None:
        v1, v2 = uuid4(), uuid4()
        heads = [_head(code="premium", version_id=v1), _head(code="verification", version_id=v2)]
        reader = FakeConfigurationReader(
            heads=heads,
            versions={
                v1: _version(version_id=v1, snapshot=_snapshot(product_type="PREMIUM")),
                v2: _version(version_id=v2, snapshot=_snapshot(product_type="VERIFICATION")),
            },
        )
        adapter = ConfigurationProductDefinitionAdapter(reader)
        products = await adapter.list_products(product_type=None)
        assert len(products) == 2

    async def test_filters_by_product_type(self) -> None:
        v1, v2 = uuid4(), uuid4()
        heads = [_head(code="premium", version_id=v1), _head(code="verification", version_id=v2)]
        reader = FakeConfigurationReader(
            heads=heads,
            versions={
                v1: _version(version_id=v1, snapshot=_snapshot(product_type="PREMIUM")),
                v2: _version(version_id=v2, snapshot=_snapshot(product_type="VERIFICATION")),
            },
        )
        adapter = ConfigurationProductDefinitionAdapter(reader)
        products = await adapter.list_products(product_type=ProductType.VERIFICATION)
        assert len(products) == 1
        assert products[0].product_type is ProductType.VERIFICATION
