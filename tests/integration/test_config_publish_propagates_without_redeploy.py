"""Eventual-consistency proof for NFR-MAINT-001 ("configuration changes take effect with no
redeploy"): a real `ConfigurationUseCases.publish` call (real Postgres, real Redis snapshot
cache) against `configuration`'s own schema, followed -- in the SAME process, no restart -- by a
real call through each consuming module's own real adapter class, proving the NEW value is
visible immediately. Every adapter reproduced here bridges to `configuration` through the exact
same two operations `composition_root._ConfigurationPortBridge` uses in production
(`list_config_heads`/`get_config_version`, or, for catalog's category/form leg,
`configuration.application.category_read.CategoryReadUseCases` reading the real Redis snapshot
cache directly) -- reproduced locally rather than imported, since `_ConfigurationPortBridge` is
composition-root-private (mirrors `test_moderation_listing_compensation.py`'s own established
"reproduce, don't import the private closure" precedent).

None of the five consuming-module adapters under test here touch their OWN module's database --
each is a pure `configuration`-reading translation adapter with no local persistence, so this
file only ever needs `configuration`'s own schema + Redis, unlike this suite's other files.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from apps.backend.tests.configuration.conftest import minimal_content
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from backbone.persistence import redis_url
from billing.infrastructure.configuration_adapter import (
    ConfigurationProductDefinitionAdapter,
)
from catalog.infrastructure.configuration_adapter import (
    ConfigurationCategoryFormAdapter,
)
from configuration.application.category_read import CategoryReadUseCases
from configuration.application.use_cases import ConfigurationUseCases
from configuration.domain import ConfigEntityType
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.base import ConfigurationBase
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import (
    SqlalchemyConfigHeadRepository,
)
from configuration.interfaces.dto import (
    ConfigurationHeadPage,
    ConfigurationVersion,
    PageInfo,
)
from configuration.interfaces.routers import _head_to_dto, _version_to_dto
from identity.infrastructure.configuration_adapter import (
    ConfigurationRoleDefinitionAdapter,
)
from notifications.infrastructure.configuration_adapter import (
    ConfigurationNotificationTemplateAdapter,
)
from search.infrastructure.configuration_adapter import (
    ConfigurationSearchConfigurationAdapter,
)
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
REDIS_AVAILABLE = bool(os.environ.get("REDIS_HOST"))
MAKER = uuid4()
CHECKER = uuid4()

type OpenUseCases = Callable[[], AbstractAsyncContextManager[ConfigurationUseCases]]


@pytest.fixture(autouse=True)
def _skip_without_redis() -> None:
    if not REDIS_AVAILABLE:
        pytest.skip("REDIS_HOST not set -- no real Redis to test the snapshot cache against")


@pytest_asyncio.fixture(autouse=True)
async def _configuration_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "configuration", ConfigurationBase)


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(redis_url())
    async for key in client.scan_iter("configuration:snapshot:*"):
        await client.delete(key)
    try:
        yield client
    finally:
        async for key in client.scan_iter("configuration:snapshot:*"):
            await client.delete(key)
        await client.aclose()


def _open_use_cases(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> OpenUseCases:
    """Mirrors `apps/backend/tests/configuration/integration/conftest.py::open_use_cases`
    exactly (one call = one real transaction, matching `composition_root.
    provide_configuration_use_cases`'s per-request session) -- reproduced locally rather than
    imported since it is a pytest fixture function there, not a plain helper."""

    @asynccontextmanager
    async def _open() -> AsyncIterator[ConfigurationUseCases]:
        session = session_factory()
        repo = SqlalchemyConfigHeadRepository(session)
        outbox = OutboxWriter(session, OutboxEvent)
        cache = RedisSnapshotCache(redis_client)
        try:
            yield ConfigurationUseCases(repo, cache, outbox)
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()
        finally:
            await session.close()

    return _open


async def _publish(
    open_use_cases: OpenUseCases,
    entity_type: ConfigEntityType,
    *,
    code: str,
    definition: dict[str, Any],
    controlled: bool,
) -> UUID:
    async with open_use_cases() as uc:
        head, version = await uc.create_draft(
            entity_type,
            code=code,
            business_owner="P-20 test",
            definition=definition,
            actor_id=MAKER,
            now=NOW,
        )
    manage_key = f"config:{entity_type.value}:manage"
    async with open_use_cases() as uc:
        await uc.publish(
            entity_type,
            head.id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({manage_key}),
            approval_note="maker submit" if controlled else None,
            now=NOW,
        )
    if controlled:
        approve_key = f"config:{entity_type.value}:approve"
        async with open_use_cases() as uc:
            await uc.publish(
                entity_type,
                head.id,
                version.id,
                actor_id=CHECKER,
                actor_permission_keys=frozenset({manage_key, approve_key}),
                approval_note="checker approve",
                now=NOW,
            )
    return head.id


async def _publish_edit(
    open_use_cases: OpenUseCases,
    entity_type: ConfigEntityType,
    head_id: UUID,
    *,
    definition: dict[str, Any],
    controlled: bool,
) -> None:
    async with open_use_cases() as uc:
        version = await uc.create_version_draft(
            entity_type, head_id, definition=definition, actor_id=MAKER, now=NOW
        )
    manage_key = f"config:{entity_type.value}:manage"
    async with open_use_cases() as uc:
        await uc.publish(
            entity_type,
            head_id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({manage_key}),
            approval_note="maker submit" if controlled else None,
            now=NOW,
        )
    if controlled:
        approve_key = f"config:{entity_type.value}:approve"
        async with open_use_cases() as uc:
            await uc.publish(
                entity_type,
                head_id,
                version.id,
                actor_id=CHECKER,
                actor_permission_keys=frozenset({manage_key, approve_key}),
                approval_note="checker approve",
                now=NOW,
            )


class _ConfigurationBridge:
    """Reproduces `composition_root._ConfigurationPortBridge`'s two methods exactly -- the SAME
    two operations every one of the four `list_config_heads`/`get_config_version`-based adapters
    under test actually calls in production."""

    def __init__(self, open_use_cases: OpenUseCases) -> None:
        self._open_use_cases = open_use_cases

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage:
        page_limit = limit or 20
        async with self._open_use_cases() as uc:
            heads, next_cursor = await uc.list_heads(
                ConfigEntityType(entity_type), cursor=cursor, limit=page_limit
            )
            return ConfigurationHeadPage(
                items=[_head_to_dto(h) for h in heads],
                page=PageInfo(limit=page_limit, next_cursor=next_cursor),
            )

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        async with self._open_use_cases() as uc:
            version = await uc.get_version(ConfigEntityType(entity_type), head_id, version_id)
            return _version_to_dto(version)


class _CategoryReaderBridge:
    """The narrow `_CategoryReader` Protocol `ConfigurationCategoryFormAdapter` actually calls in
    production, satisfied here by the REAL `CategoryReadUseCases` (reads the real Redis snapshot
    cache directly, not Postgres -- see that class's own docstring) against a fresh session per
    call, exactly as `composition_root._catalog_category_read_use_cases` does."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
    ) -> None:
        self._session_factory = session_factory
        self._redis_client = redis_client

    async def get_category(self, category_id: UUID) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            uc = CategoryReadUseCases(
                SqlalchemyConfigHeadRepository(session),
                RedisSnapshotCache(self._redis_client),
            )
            return await uc.get_category(category_id)

    async def get_category_form(self, category_id: UUID) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            uc = CategoryReadUseCases(
                SqlalchemyConfigHeadRepository(session),
                RedisSnapshotCache(self._redis_client),
            )
            return await uc.get_category_form(category_id)


async def test_catalog_category_and_form_propagate_without_redeploy(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    open_use_cases = _open_use_cases(session_factory, redis_client)
    form_id = await _publish(
        open_use_cases,
        ConfigEntityType.FORM_DEFINITION,
        code="apartments-form",
        definition=minimal_content("form-definition"),
        controlled=True,
    )
    category_id = await _publish(
        open_use_cases,
        ConfigEntityType.CATEGORY,
        code="apartments",
        definition=minimal_content(
            "category", form_definition_id=form_id, path="/housing/apartments"
        ),
        controlled=True,
    )

    adapter = ConfigurationCategoryFormAdapter(_CategoryReaderBridge(session_factory, redis_client))
    before = await adapter.get_category(category_id)
    assert before is not None
    assert before.path == "/housing/apartments"
    binding = await adapter.get_current_form_binding(category_id)
    assert binding is not None
    assert binding.form_definition_id == form_id

    await _publish_edit(
        open_use_cases,
        ConfigEntityType.CATEGORY,
        category_id,
        definition=minimal_content("category", form_definition_id=form_id, path="/housing/flats"),
        controlled=True,
    )

    after = await adapter.get_category(category_id)
    assert after is not None
    assert after.path == "/housing/flats", "category edit must propagate with no redeploy"


async def test_billing_product_definition_propagates_without_redeploy(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    open_use_cases = _open_use_cases(session_factory, redis_client)
    bridge = _ConfigurationBridge(open_use_cases)
    adapter = ConfigurationProductDefinitionAdapter(bridge)

    product_id = await _publish(
        open_use_cases,
        ConfigEntityType.PRODUCT_DEFINITION,
        code="premium-listing",
        definition=minimal_content("product-definition", price_amount="10.00"),
        controlled=True,
    )
    before = await adapter.get_product(product_id)
    assert before is not None
    assert before.price_amount == "10.00"

    await _publish_edit(
        open_use_cases,
        ConfigEntityType.PRODUCT_DEFINITION,
        product_id,
        definition=minimal_content("product-definition", price_amount="25.00"),
        controlled=True,
    )

    after = await adapter.get_product(product_id)
    assert after is not None
    assert after.price_amount == "25.00", "price edit must propagate with no redeploy"


async def test_search_configuration_propagates_without_redeploy(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    open_use_cases = _open_use_cases(session_factory, redis_client)
    bridge = _ConfigurationBridge(open_use_cases)
    adapter = ConfigurationSearchConfigurationAdapter(bridge)

    await _publish(
        open_use_cases,
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="global-search",
        definition=minimal_content("search-configuration", promotion_page_cap=5),
        controlled=False,
    )
    before = await adapter.get_search_configuration(None)
    assert before.promotion_page_cap == 5

    head_id = None
    async with open_use_cases() as uc:
        heads, _ = await uc.list_heads(ConfigEntityType.SEARCH_CONFIGURATION, cursor=None, limit=50)
        head_id = next(h.id for h in heads if h.code == "global-search")

    await _publish_edit(
        open_use_cases,
        ConfigEntityType.SEARCH_CONFIGURATION,
        head_id,
        definition=minimal_content("search-configuration", promotion_page_cap=9),
        controlled=False,
    )

    after = await adapter.get_search_configuration(None)
    assert after.promotion_page_cap == 9, "facet/cap edit must propagate with no redeploy"


async def test_notifications_template_propagates_without_redeploy(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    open_use_cases = _open_use_cases(session_factory, redis_client)
    bridge = _ConfigurationBridge(open_use_cases)
    adapter = ConfigurationNotificationTemplateAdapter(bridge)

    head_id = await _publish(
        open_use_cases,
        ConfigEntityType.NOTIFICATION_TEMPLATE,
        code="listing-published-email",
        definition=minimal_content("notification-template", body={"uz_latn": "Congratulations"}),
        controlled=False,
    )
    before = await adapter.list_templates_for_event("ListingPublished")
    assert len(before) == 1
    assert before[0].body.uz_latn == "Congratulations"

    await _publish_edit(
        open_use_cases,
        ConfigEntityType.NOTIFICATION_TEMPLATE,
        head_id,
        definition=minimal_content(
            "notification-template", body={"uz_latn": "Your listing is now live"}
        ),
        controlled=False,
    )

    after = await adapter.list_templates_for_event("ListingPublished")
    assert len(after) == 1
    assert after[0].body.uz_latn == "Your listing is now live", (
        "template wording edit must propagate with no redeploy"
    )


async def test_identity_role_definition_propagates_without_redeploy(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    open_use_cases = _open_use_cases(session_factory, redis_client)
    bridge = _ConfigurationBridge(open_use_cases)
    adapter = ConfigurationRoleDefinitionAdapter(bridge)

    await _publish(
        open_use_cases,
        ConfigEntityType.ROLE_DEFINITION,
        code="content-editor",
        definition=minimal_content(
            "role-definition", permission_keys=["config:notification-template:manage"]
        ),
        controlled=True,
    )
    before = await adapter.resolve_by_code("content-editor")
    assert before.permission_keys == frozenset({"config:notification-template:manage"})

    await _publish_edit(
        open_use_cases,
        ConfigEntityType.ROLE_DEFINITION,
        before.head_id,
        definition=minimal_content(
            "role-definition",
            permission_keys=[
                "config:notification-template:manage",
                "config:search-configuration:manage",
            ],
        ),
        controlled=True,
    )

    after = await adapter.resolve_by_code("content-editor")
    assert after.permission_keys == frozenset(
        {"config:notification-template:manage", "config:search-configuration:manage"}
    ), "role permission-key edit must propagate with no redeploy"
