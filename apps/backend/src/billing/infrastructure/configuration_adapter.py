"""Reads published `ProductDefinition` snapshots from `configuration` -- never
`configuration.domain`/`application`/`infrastructure` (`cross-module-billing`,
tools/importlinter.cfg; the ONE other module billing may import at all besides `identity`, SAD
Sec 8.1). Mirrors `catalog.infrastructure.configuration_adapter`/`search.infrastructure.
configuration_adapter`'s own narrow-Protocol bridge pattern -- a `ProductDefinition` version's
own content model has no exact head `code` naming convention documented (unlike
`platform-settings-global`'s own literal seeded code), so this adapter lists every published
`product-definition` head and reads each one's current published version.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol
from uuid import UUID

from billing.application.ports import ProductDefinitionSnapshot
from billing.domain import ProductType
from shared_kernel import LocalizedText


class _ConfigurationReader(Protocol):
    """The narrow slice of `configuration.interfaces.ports.ConfigurationPort` this module
    actually calls."""

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> Any: ...

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> Any: ...


class ConfigurationProductDefinitionAdapter:
    """Implements `billing.application.ports.ProductDefinitionReaderPort`."""

    def __init__(self, configuration: _ConfigurationReader) -> None:
        self._configuration = configuration

    async def get_product(self, product_id: UUID) -> ProductDefinitionSnapshot | None:
        async for head, version in self._published_products():
            if head.id == product_id:
                return _to_snapshot(head, version)
        return None

    async def list_products(
        self, *, product_type: ProductType | None
    ) -> tuple[ProductDefinitionSnapshot, ...]:
        results: list[ProductDefinitionSnapshot] = []
        async for head, version in self._published_products():
            snapshot = _to_snapshot(head, version)
            if product_type is None or snapshot.product_type is product_type:
                results.append(snapshot)
        return tuple(results)

    async def _published_products(self) -> AsyncIterator[tuple[Any, Any]]:
        cursor: str | None = None
        while True:
            page = await self._configuration.list_config_heads(
                "product-definition", cursor=cursor, limit=50
            )
            for head in page.items:
                if head.current_version_id is None:
                    continue
                version = await self._configuration.get_config_version(
                    "product-definition", head.id, head.current_version_id
                )
                if version.status != "PUBLISHED" or version.snapshot is None:
                    continue
                yield head, version
            cursor = page.page.next_cursor
            if cursor is None:
                break


def _to_snapshot(head: Any, version: Any) -> ProductDefinitionSnapshot:
    raw = version.snapshot
    descriptor = raw.get("descriptor", {})
    name_raw = descriptor.get("name") or {}
    description_raw = descriptor.get("description")
    quota_set = raw.get("quota_set")
    return ProductDefinitionSnapshot(
        id=head.id,
        version_id=version.id,
        code=head.code,
        product_type=ProductType(raw["product_type"]),
        name=LocalizedText(**name_raw),
        description=LocalizedText(**description_raw) if description_raw else None,
        price_amount=str(raw["price_amount"]),
        price_currency=raw.get("price_currency", "UZS"),
        term_days=raw.get("term_days"),
        quota=(
            {k: v for k, v in quota_set.items() if v is not None}
            if isinstance(quota_set, dict)
            else None
        ),
    )
