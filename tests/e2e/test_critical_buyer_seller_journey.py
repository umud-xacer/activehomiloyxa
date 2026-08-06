"""THE CRITICAL END-TO-END JOURNEY (P-20), driven entirely through REAL HTTP requests against
`main.create_app()` -- the real, fully-composed FastAPI app, real PostgreSQL/Redis/OpenSearch,
real `composition_root` wiring -- not direct use-case calls (those are already proven module-by-
module and cross-module in `tests/integration/`). One sequential test walks the whole chain:

register (seller, phone OTP) -> authenticate -> create business profile -> create listing ->
attach an image -> publish -> listing appears in search -> a buyer registers, favorites the
listing, starts a conversation, reveals the phone -> the seller purchases a PREMIUM promotion for
their listing -> an admin confirms the offline payment -> the entitlement activates -> the
listing shows PROMOTED in both search AND catalog's own detail view -> the FavoriteAdded metric
lands in analytics -> the owner sees it reflected in their own listing statistics.

No background worker processes run in this test environment -- every outbox hop is drained
manually, in-process, using the SAME real handler-building functions/closures `composition_root`
attaches to its own dispatchers in production (imported directly, not reproduced), mirroring
`tests/integration/test_billing_promotion_to_catalog_and_search.py`'s own established precedent:
only the SPECIFIC outbox row relevant to each hop is drained (never a blanket `OutboxDispatcher.
drain_once()` over an entire table), so branches this journey doesn't exercise (email/SMS
notification dispatch, moderation, ads) are never touched and never need their own real
credentials.

## Scoped-down steps (disclosed, not silently skipped)

- **OTP delivery**: `identity`'s real Eskiz SMS adapter is swapped, at the `OtpSmsProviderPort`
  boundary only (DEC-18 -- the port exists specifically so this seam can be swapped), for a
  fake that captures the code instead of sending it over a real network. Every other step of
  registration/login (session issuance, RBAC, cookie handling) is the real code path.
- **Image upload**: the real `initMediaUpload` HTTP endpoint issues a real presigned MinIO URL,
  but this test does not actually PUT bytes to MinIO or wait for a real virus-scan/thumbnail
  worker (none runs in this environment; ClamAV is not part of this environment's docker stack).
  A real `MediaAsset` domain object is seeded directly via media's own real repository instead --
  `catalog`'s own `_attach_verified_image` performs an EXISTENCE-only check regardless (already
  proven in `tests/degradation/test_catalog_publish_not_blocked_by_media_lag.py`), so this does
  not weaken what `attachListingImage`'s real HTTP call actually proves.

## A genuine, confirmed integration defect found while building this suite -- FIXED

`identity.domain.user_account.UserAccount` had **no code path, anywhere, sync or async, that
ever added a profile to `owned_profile_ids`** after `profiles.createBusinessProfile` succeeded --
confirmed by reading every reference to `owned_profile_ids` in the identity module (it was only
ever read, never appended to). Since `identity.domain.session.Session.switch_acting_profile` (the
real `switchActingProfile` operation, FR-USER-002) rejects any `acting_profile_id` not already in
`owned_profile_ids`, a real user could never legitimately switch their session to act as a
business profile they just created -- which transitively blocked every acting-profile-gated
operation downstream (e.g. `billing.createOrder`/`getOrderInvoice`). Fixed: `UserAccount.
link_owned_profile` (idempotent) + `AccountUseCases.link_owned_profile` + identity's first-ever
inbound event consumer, `identity.infrastructure.event_projection.handle_profiles_event`, wired
as `make_profiles_notification_projection_handler`'s fourth route (`composition_root.py`) --
reacting to the ALREADY-published `profiles.BusinessProfileCreated` event, no contract change, the
same "new route on an existing dispatcher" pattern this session used repeatedly (e.g. `catalog.
infrastructure.event_projection.handle_identity_event` for `AccountSuspended`). Proven twice: this
E2E journey now drains the real event through the real composition-root closure (see
`_drain_business_profile_created` below) instead of bridging around the gap, and a dedicated
eventual-consistency test (`tests/integration/
test_profiles_creation_links_identity_owned_profile.py`) proves it in isolation, including
redelivery idempotency.

## A second genuine defect found -- FIXED here (same class as an already-established repo-wide fix)

`billing.infrastructure.persistence.repository.SqlalchemyOrderRepository.add()` never flushed --
`OrderUseCases.create_order`'s own real call sequence (`add(order)`, then, once the invoice is
issued, `save(order)` in the SAME transaction) always raised `LookupError` on a real database,
because this repository's session runs with `autoflush=False`
(`backbone.persistence.engine.make_session_factory`) and `save()`'s own `session.get()` cannot see
the still-pending `add()`. No existing test (unit or integration) exercised this exact
add-then-save sequence against real Postgres before this suite did. Fixed with an immediate
`await self._session.flush()` at the end of `add()` -- the identical fix already applied this
session to `search.infrastructure.persistence.repository.SqlalchemyFallbackIndexRepository.
upsert_document()` for the same root cause.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from analytics.application.metric_use_cases import MetricUseCases
from analytics.infrastructure.event_projection import handle_catalog_event
from analytics.infrastructure.persistence.base import AnalyticsBase
from analytics.infrastructure.persistence.repository import (
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)
from backbone.outbox import OutboxWriter
from backbone.persistence import make_engine, make_session_factory
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from configuration.application.use_cases import ConfigurationUseCases
from configuration.domain import ConfigEntityType
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.base import ConfigurationBase
from configuration.infrastructure.persistence.models import (
    OutboxEvent as ConfigOutboxEvent,
)
from configuration.infrastructure.persistence.repository import (
    SqlalchemyConfigHeadRepository,
)
from identity.domain.value_objects import PhoneNumber
from identity.infrastructure.persistence.base import IdentityBase
from identity.infrastructure.persistence.repository import (
    SqlalchemyUserAccountRepository,
)
from media.domain.media_asset import MediaAsset
from media.domain.value_objects import OwnerContextType
from media.infrastructure.persistence.base import MediaBase
from media.infrastructure.persistence.repository import SqlalchemyMediaAssetRepository
from messaging.infrastructure.event_projection import handle_listing_created
from messaging.infrastructure.persistence.base import MessagingBase
from profiles.infrastructure.persistence.base import ProfilesBase
from search.infrastructure.event_projection import make_search_event_handler
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from shared_kernel import EventEnvelope, MediaAssetId, UserId
from tests.integration.conftest import (
    ensure_analytics_schema_via_migration,
    ensure_clean_schema,
)

from billing.infrastructure.persistence.base import BillingBase  # isort:skip

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
"""Real current time -- `analytics.metric_event` is RANGE-partitioned by month (see
`tests/integration/test_catalog_metrics_to_analytics.py` for why this must not be a fixed date)."""

OPENSEARCH_AVAILABLE = bool(os.environ.get("OPENSEARCH_HOST"))
_INDEX_NAME = "listing_search_content_e2e"
MAKER = uuid4()
CHECKER = uuid4()


@pytest.fixture(autouse=True)
def _skip_without_opensearch() -> None:
    if not OPENSEARCH_AVAILABLE:
        pytest.skip("OPENSEARCH_HOST not set -- no real OpenSearch cluster to test against")


@pytest.fixture(scope="session", autouse=True)
def _analytics_schema_migrated() -> None:
    ensure_analytics_schema_via_migration()


@pytest_asyncio.fixture(autouse=True)
async def _every_touched_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "identity", IdentityBase)
    await ensure_clean_schema(engine, "profiles", ProfilesBase)
    await ensure_clean_schema(engine, "catalog", CatalogBase)
    await ensure_clean_schema(engine, "media", MediaBase)
    await ensure_clean_schema(engine, "messaging", MessagingBase)
    await ensure_clean_schema(engine, "billing", BillingBase)
    await ensure_clean_schema(engine, "configuration", ConfigurationBase)
    await ensure_clean_schema(engine, "analytics", AnalyticsBase)


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


class _CapturingSmsProvider:
    """Swaps `identity.application.ports.OtpSmsProviderPort` at the port boundary (DEC-18) --
    the only thing faked is SMS *delivery*; OTP generation/hashing/verification, session
    issuance, and every RBAC check downstream are all the real code paths."""

    def __init__(self) -> None:
        self.sent_codes: dict[str, str] = {}

    async def send_otp(self, *, phone: PhoneNumber, code: str) -> None:
        self.sent_codes[phone.value] = code


@pytest.fixture
def sms_provider() -> _CapturingSmsProvider:
    return _CapturingSmsProvider()


@pytest.fixture
def app(sms_provider: _CapturingSmsProvider) -> Any:
    for key, value in {
        "SESSION_COOKIE_NAME": "ah_session",
        "SESSION_SIGNING_KEY": "e2e-test-signing-key-not-a-real-secret",
        "ESKIZ_API_BASE_URL": "https://example.invalid/eskiz",
        "ESKIZ_EMAIL": "e2e-test@example.invalid",
        "ESKIZ_PASSWORD": "unused-e2e-test-value",
        "ESKIZ_SENDER_NICKNAME": "unused-e2e-test-value",
        "SMTP_HOST": "example.invalid",
        "SMTP_PORT": "587",
        "SMTP_USER": "unused-e2e-test-value",
        "SMTP_PASSWORD": "unused-e2e-test-value",
        "WEB_PUSH_VAPID_PUBLIC_KEY": "unused-e2e-test-value",
        "WEB_PUSH_VAPID_PRIVATE_KEY": "unused-e2e-test-value",
        "GOOGLE_OAUTH_CLIENT_ID": "unused-e2e-test-value",
        "GOOGLE_OAUTH_CLIENT_SECRET": "unused-e2e-test-value",
        "YANDEX_MAPS_API_KEY": "unused-e2e-test-value",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ROOT_USER": "active_home",
        "MINIO_ROOT_PASSWORD": "active_home_local_dev_only",
        "MINIO_MEDIA_BUCKET": "active-home-media",
        "MINIO_USE_TLS": "false",
        "MEDIA_CDN_BASE_URL": "http://localhost:8080/media",
        "MEDIA_PRESIGN_EXPIRY_SECONDS": "900",
        "CLAMAV_HOST": "localhost",
        "CLAMAV_PORT": "3310",
    }.items():
        os.environ.setdefault(key, value)

    import composition_root
    from identity.application import AuthenticationUseCases
    from identity.infrastructure import RedisSessionRepository as _SessionRepo
    from identity.infrastructure import (
        SqlalchemyOtpChallengeRepository as _OtpChallengeRepo,
    )
    from identity.infrastructure import (
        SqlalchemyOtpChallengeUnitOfWork as _OtpChallengeUnitOfWork,
    )
    from identity.infrastructure.persistence.models import (
        OutboxEventRow as _IdentityOutboxEventRow,
    )
    from identity.interfaces.di import get_authentication_use_cases
    from main import create_app

    real_app = create_app()

    async def provide_authentication_use_cases_with_fake_sms() -> AsyncIterator[
        AuthenticationUseCases
    ]:
        async for session in composition_root._identity_session():
            yield AuthenticationUseCases(
                accounts=SqlalchemyUserAccountRepository(session),
                sessions=_SessionRepo(composition_root._identity_redis_client()),
                otp_challenges=_OtpChallengeRepo(session),
                otp_challenge_unit_of_work=_OtpChallengeUnitOfWork(
                    composition_root._identity_session_factory()
                ),
                outbox=OutboxWriter(session, _IdentityOutboxEventRow),
                otp_sms_provider=sms_provider,
                email_provider=composition_root._email_provider(),
                google_provider=composition_root._google_provider(),
                password_hasher=composition_root._password_hasher(),
                otp_code_generator=composition_root._otp_code_generator(),
                session_token_generator=composition_root._session_token_generator(),
                platform_settings=composition_root._platform_settings_reader(),
            )

    real_app.dependency_overrides[get_authentication_use_cases] = (
        provide_authentication_use_cases_with_fake_sms
    )
    return real_app


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    """MUST be entered as a context manager (`with`) -- without it, Starlette's `TestClient`
    spins up a brand-new anyio portal/event loop PER REQUEST (`_portal_factory`'s own fallback
    branch when `self.portal` was never set by `__enter__`), which breaks the module-level
    `@lru_cache`d asyncpg engine/pool `composition_root` shares across every request in the real
    app (`RuntimeError: ... attached to a different loop`). One persistent portal for the whole
    test's HTTP traffic avoids this entirely."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


class _Actor:
    """A `Bearer <token>`-authenticated caller against ONE shared `TestClient`/portal (CLAUDE.md:
    "Bearer token for native clients" is an equally real session-auth path, not a workaround) --
    deliberately not one `TestClient` instance per actor: Starlette's `TestClient`, used without
    entering it as a context manager per call, spins up a FRESH anyio event loop per request,
    which breaks the module-level `@lru_cache`d asyncpg engine/pool `composition_root` shares
    across every request in the real app ("attached to a different loop" `RuntimeError`). One
    shared client/portal for the whole test sidesteps this entirely, and also sidesteps needing
    three separate cookie jars for three concurrent actors."""

    def __init__(self, client: TestClient, token: str) -> None:
        self._client = client
        self._token = token

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._client.get(url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._client.post(url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)


async def _register_via_phone(
    client: TestClient, sms_provider: _CapturingSmsProvider, *, phone: str
) -> _Actor:
    resp = client.post("/api/v1/auth/otp", json={"phoneNumber": phone, "purpose": "REGISTRATION"})
    assert resp.status_code == 202, resp.text
    code = sms_provider.sent_codes[phone]
    resp = client.post(
        "/api/v1/auth/otp/verify",
        json={"phoneNumber": phone, "code": code, "purpose": "REGISTRATION"},
    )
    assert resp.status_code == 200, resp.text
    return _Actor(client, resp.json()["sessionToken"])


def _account_id(actor: _Actor) -> UUID:
    resp = actor.get("/api/v1/me")
    assert resp.status_code == 200, resp.text
    return UUID(resp.json()["id"])


async def _drain_business_profile_created(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """P-20 fix: `identity.infrastructure.event_projection.handle_profiles_event` closes the
    `owned_profile_ids` gap this file's own docstring used to document as unfixed -- drains the
    real `BusinessProfileCreated` row through that real handler function directly, with a
    freshly-built `AccountUseCases` (not `composition_root.make_profiles_notification_projection_
    handler()`'s own `@lru_cache`d singletons, which are bound to whichever event loop first
    constructed them -- the real `TestClient`'s own anyio portal in this same test -- and raise
    `RuntimeError: ... attached to a different loop` if reused from the plain pytest-asyncio loop
    this function runs in; mirrors `tests/integration/
    test_profiles_creation_links_identity_owned_profile.py`'s own identical, already-proven-
    working pattern)."""
    from redis.asyncio import Redis

    from backbone.persistence import redis_url
    from identity.application.account_use_cases import AccountUseCases
    from identity.infrastructure.event_projection import handle_profiles_event
    from identity.infrastructure.persistence.models import (
        OutboxEventRow as IdentityOutboxEventRow,
    )
    from identity.infrastructure.security import Argon2PasswordHasherAdapter
    from identity.infrastructure.session_store import RedisSessionRepository
    from profiles.infrastructure.persistence.models import (
        OutboxEventRow as ProfilesOutboxEventRow,
    )

    profiles_session_factory = make_session_factory(make_engine())
    async with profiles_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ProfilesOutboxEventRow).where(
                        ProfilesOutboxEventRow.event_type == "BusinessProfileCreated"
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

    identity_session_factory = make_session_factory(make_engine())
    redis_client = Redis.from_url(redis_url())
    async with identity_session_factory() as session, session.begin():
        use_cases = AccountUseCases(
            accounts=SqlalchemyUserAccountRepository(session),
            sessions=RedisSessionRepository(redis_client),
            outbox=OutboxWriter(session, IdentityOutboxEventRow),
            password_hasher=Argon2PasswordHasherAdapter(),
        )
        await handle_profiles_event(session, envelope, use_cases=use_cases)
    await redis_client.aclose()


async def _bootstrap_admin_with_role(
    client: TestClient,
    sms_provider: _CapturingSmsProvider,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    phone: str,
    role_head_id: UUID,
    role_version_id: UUID,
    role_code: str,
) -> _Actor:
    """No HTTP path can grant the FIRST admin a permission (`assignRole` is itself an admin-only,
    permission-gated operation) -- this is an intrinsic bootstrap problem, not a defect. Registers
    the admin through the real OTP flow, then assigns the role directly via the real domain
    method + repository (the same "reproduce the exact call a real caller would make" precedent
    this suite already uses for `owned_profile_ids`), and returns an actor whose EXISTING real
    session immediately reflects it (`resolve_acting_context` re-reads the account fresh on every
    request)."""
    admin = await _register_via_phone(client, sms_provider, phone=phone)
    account_id = _account_id(admin)
    async with session_factory() as session:
        repo = SqlalchemyUserAccountRepository(session)
        account = await repo.get_by_id(UserId(value=account_id))
        assert account is not None
        updated = account.assign_role(
            role_definition_head_id=role_head_id,
            role_definition_version_id=role_version_id,
            role_code=role_code,
            acting_profile_id=None,
            assigned_by=account_id,
            now=NOW,
        )
        await repo.save(updated)
        await session.commit()
    return admin


def _open_configuration_use_cases(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Any
) -> Any:
    @asynccontextmanager
    async def _open() -> AsyncIterator[ConfigurationUseCases]:
        session = session_factory()
        repo = SqlalchemyConfigHeadRepository(session)
        outbox = OutboxWriter(session, ConfigOutboxEvent)
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


async def _publish_controlled(
    open_use_cases: Any,
    entity_type: ConfigEntityType,
    *,
    code: str,
    definition: dict[str, Any],
) -> tuple[UUID, UUID]:
    async with open_use_cases() as uc:
        head, version = await uc.create_draft(
            entity_type,
            code=code,
            business_owner="P-20 e2e test",
            definition=definition,
            actor_id=MAKER,
            now=NOW,
        )
    manage_key = f"config:{entity_type.value}:manage"
    approve_key = f"config:{entity_type.value}:approve"
    async with open_use_cases() as uc:
        await uc.publish(
            entity_type,
            head.id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({manage_key}),
            approval_note="maker submit",
            now=NOW,
        )
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
    return head.id, version.id


async def _publish_standard(
    open_use_cases: Any,
    entity_type: ConfigEntityType,
    *,
    code: str,
    definition: dict[str, Any],
) -> tuple[UUID, UUID]:
    """STANDARD-track entities (`SEARCH_CONFIGURATION`/`NOTIFICATION_TEMPLATE`, per `configuration/
    README.md`'s own track list) publish in ONE call -- a second call against the resulting
    already-PUBLISHED version would raise `VersionNotPublishableError`."""
    async with open_use_cases() as uc:
        head, version = await uc.create_draft(
            entity_type,
            code=code,
            business_owner="P-20 e2e test",
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
            approval_note=None,
            now=NOW,
        )
    return head.id, version.id


async def test_the_critical_buyer_seller_journey(
    session_factory: async_sessionmaker[AsyncSession],
    opensearch_index: OpenSearchIndexAdapter,
    client: TestClient,
    sms_provider: _CapturingSmsProvider,
) -> None:
    from redis.asyncio import Redis

    from backbone.persistence import redis_url

    redis_client = Redis.from_url(redis_url())
    open_config_use_cases = _open_configuration_use_cases(session_factory, redis_client)

    await _publish_controlled(
        open_config_use_cases,
        ConfigEntityType.PLATFORM_SETTINGS,
        code="platform-settings-global",
        definition={
            "descriptor": {"name": {"uz_latn": "Global settings"}},
            "settings_scope": "GLOBAL",
            "settings": {
                "otp.expiry_minutes": 5,
                "session.expiry_hours": 24,
                "listing.default_expiry_days": 30,
            },
        },
    )
    form_head_id, _ = await _publish_controlled(
        open_config_use_cases,
        ConfigEntityType.FORM_DEFINITION,
        code="e2e-apartments-form",
        definition={
            "descriptor": {"name": {"uz_latn": "Apartments form"}},
            "sections": [{"code": "main", "label": {"uz_latn": "Main"}, "order": 1}],
            "fields": [],
        },
    )
    category_head_id, _ = await _publish_controlled(
        open_config_use_cases,
        ConfigEntityType.CATEGORY,
        code="e2e-apartments",
        definition={
            "descriptor": {"name": {"uz_latn": "Apartments"}},
            "parent_category_id": None,
            "path": "/housing/apartments",
            "form_definition_id": str(form_head_id),
            "tree_status": "ACTIVE",
        },
    )
    product_head_id, _ = await _publish_controlled(
        open_config_use_cases,
        ConfigEntityType.PRODUCT_DEFINITION,
        code="e2e-premium-listing",
        definition={
            "descriptor": {"name": {"uz_latn": "Premium listing"}},
            "product_type": "PREMIUM",
            "price_amount": "50000.00",
            "price_currency": "UZS",
            "term_days": 30,
        },
    )
    role_head_id, role_version_id = await _publish_controlled(
        open_config_use_cases,
        ConfigEntityType.ROLE_DEFINITION,
        code="e2e-billing-admin",
        definition={
            "descriptor": {"name": {"uz_latn": "E2E Billing Admin"}},
            "role_name": "E2E Billing Admin",
            "permission_keys": ["billing:invoice:confirm_payment"],
        },
    )
    await _publish_standard(
        open_config_use_cases,
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="e2e-search-global",
        definition={
            "descriptor": {"name": {"uz_latn": "E2E global search"}},
            "scope_category_id": None,
            "facets": [],
            "sort_options": ["RELEVANCE", "RECENCY"],
            "default_sort": "RELEVANCE",
            "promotion_page_cap": 5,
        },
    )
    await redis_client.aclose()

    # -- register + authenticate (seller) ----------------------------------------------------
    seller = await _register_via_phone(client, sms_provider, phone="+998901112233")
    seller_account_id = _account_id(seller)

    # -- create business profile --------------------------------------------------------------
    resp = seller.post(
        "/api/v1/business-profiles",
        json={
            "profileType": "CONSTRUCTION_COMPANY",
            "name": {"uz_latn": "E2E Quality Builders"},
        },
    )
    assert resp.status_code == 201, resp.text
    profile_id = UUID(resp.json()["id"])

    await _drain_business_profile_created(session_factory)
    resp = seller.post(
        "/api/v1/me/sessions/switch-profile", json={"actingProfileId": str(profile_id)}
    )
    assert resp.status_code == 200, resp.text

    # -- create listing (draft) ---------------------------------------------------------------
    resp = seller.post(
        "/api/v1/listings",
        json={
            "listingType": "ADVERTISEMENT",
            "categoryId": str(category_head_id),
            "title": "Cozy two-room apartment",
            "description": "Renovated, near metro",
            "attributes": {},
            "publish": False,
        },
    )
    assert resp.status_code == 201, resp.text
    listing_id = UUID(resp.json()["id"])

    # -- drain catalog's ListingCreated into messaging's own listing-owner projection, exactly as
    # `make_catalog_outbox_fanout_handler`'s messaging route would (I-01: messaging only ever
    # needs a listing's FIRST event to learn its owner) -----------------------------------------
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.event_type == "ListingCreated"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        created_envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )
        await handle_listing_created(session, created_envelope)
        await session.commit()

    # -- attach an image (real HTTP call; the underlying MediaAsset is seeded directly, see this
    # file's own module docstring for why the presigned-upload/MinIO/virus-scan hop is scoped
    # down) ------------------------------------------------------------------------------------
    media_asset_id = uuid4()
    async with session_factory() as session:
        asset = MediaAsset.initiate(
            asset_id=MediaAssetId(value=media_asset_id),
            content_type_raw="image/png",
            size_bytes=1024,
            owner_context_type=OwnerContextType.LISTING,
            uploaded_by=UserId(value=seller_account_id),
            now=NOW,
        )
        await SqlalchemyMediaAssetRepository(session).add(asset)
        await session.commit()

    resp = seller.post(
        f"/api/v1/listings/{listing_id}/images",
        json={"mediaAssetId": str(media_asset_id), "position": 1},
    )
    assert resp.status_code == 201, resp.text

    # -- publish --------------------------------------------------------------------------------
    resp = seller.post(f"/api/v1/listings/{listing_id}/status", json={"action": "PUBLISH"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycleState"] == "PUBLISHED"

    # -- drain catalog's outbox into search's real indexing consumer, exactly as the (not
    # running in this test env) search_worker.py would ------------------------------------------
    search_handler = make_search_event_handler(
        session_factory=session_factory, index=opensearch_index
    )
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.event_type == "ListingPublished"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        publish_envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )
    await search_handler(publish_envelope)

    # -- listing appears in search --------------------------------------------------------------
    resp = seller.get("/api/v1/search", params={"q": "apartment"})
    assert resp.status_code == 200, resp.text
    assert str(listing_id) in {hit["listingId"] for hit in resp.json()["items"]}

    # -- a buyer registers, favorites the listing, starts a conversation, reveals the phone ------
    buyer = await _register_via_phone(client, sms_provider, phone="+998907776655")

    resp = buyer.post("/api/v1/me/favorites", json={"listingId": str(listing_id)})
    assert resp.status_code == 201, resp.text

    resp = buyer.post(
        "/api/v1/conversations",
        json={"listingId": str(listing_id), "message": "Is this still available?"},
    )
    assert resp.status_code == 201, resp.text
    conversation_id = UUID(resp.json()["id"])

    resp = buyer.post(f"/api/v1/conversations/{conversation_id}/phone-reveal")
    assert resp.status_code == 200, resp.text
    assert resp.json()["allowed"] is True

    # -- the seller purchases a PREMIUM promotion for their listing -------------------------------
    resp = seller.post(
        "/api/v1/orders",
        json={
            "productId": str(product_head_id),
            "targetType": "LISTING",
            "targetId": str(listing_id),
        },
    )
    assert resp.status_code == 201, resp.text
    order_id = UUID(resp.json()["id"])

    resp = seller.get(f"/api/v1/orders/{order_id}/invoice")
    assert resp.status_code == 200, resp.text
    invoice_id = UUID(resp.json()["id"])

    # -- an admin confirms the offline payment (bootstrap: see _bootstrap_admin_with_role's own
    # docstring for why this cannot itself go through an HTTP role-grant call) --------------------
    admin = await _bootstrap_admin_with_role(
        client,
        sms_provider,
        session_factory,
        phone="+998909998877",
        role_head_id=role_head_id,
        role_version_id=role_version_id,
        role_code="e2e-billing-admin",
    )
    resp = admin.post(
        f"/api/v1/admin/billing/invoices/{invoice_id}/confirm-payment",
        json={"confirmed": True, "note": "bank transfer received"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "PAID"

    # -- drain the entitlement into catalog's promotion projection, exactly the same real
    # composition-root closure production attaches to billing's own outbox dispatcher ------------
    import composition_root

    billing_session_factory = make_session_factory(make_engine())
    fanout_handler = composition_root.make_billing_entitlement_fanout_handler(
        billing_session_factory=billing_session_factory,
        profiles_session_factory=make_session_factory(make_engine()),
        ads_session_factory=make_session_factory(make_engine()),
    )
    async with billing_session_factory() as session:
        from billing.infrastructure.persistence.models import (
            OutboxEventRow as BillingOutboxEventRow,
        )

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
        entitlement_envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )
    await fanout_handler(entitlement_envelope)

    # -- catalog's own outbox now carries the republished ListingEdited -- drain it into search
    # too, closing the promotion loop -------------------------------------------------------------
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
        assert len(rows) == 1
        edited_envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )
    await search_handler(edited_envelope)

    # -- the listing shows PROMOTED in both catalog and search -------------------------------------
    resp = seller.get(f"/api/v1/listings/{listing_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["promotion"]["kind"] == "PREMIUM"

    resp = seller.get("/api/v1/search", params={"q": "apartment"})
    assert resp.status_code == 200, resp.text
    hit = next(h for h in resp.json()["items"] if h["listingId"] == str(listing_id))
    assert hit["promoted"]["kind"] == "PREMIUM"

    # -- the FavoriteAdded metric lands in analytics -----------------------------------------------
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.event_type == "FavoriteAdded"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        favorite_envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )
    async with session_factory() as session, session.begin():
        await handle_catalog_event(
            session,
            favorite_envelope,
            metric_use_cases=MetricUseCases(
                metrics=SqlalchemyMetricEventRepository(session),
                listing_statistics=SqlalchemyListingStatisticsProjectionRepository(session),
            ),
        )

    # -- the owner sees it reflected in their own listing statistics -------------------------------
    resp = seller.get(f"/api/v1/listings/{listing_id}/statistics")
    assert resp.status_code == 200, resp.text
    assert resp.json()["favorites"] == 1
