"""The true composition root (Playbook Sec 6: "the composition root wires adapters to ports;
callers above it never construct a concrete adapter") -- lives outside every bounded-context
module's own package tree so it is free to import a module's `infrastructure/` layer plus the
concrete ORM/cache/outbox types that back it (`tools/importlinter.cfg`'s `no-infra-inbound-*`
contracts forbid that import from inside a module's own interfaces/application/domain, precisely
so this wiring happens here instead).

`apps/backend/src/main.py` imports this module and installs the providers below via
`app.dependency_overrides[...]`, overriding the placeholder `NotImplementedError` functions each
module's `interfaces/di.py` declares as its stable `Depends(...)` target.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from fastapi import Cookie, Depends, Header
from opensearchpy import OpenSearch
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from admin.application import (
    AdminDashboardUseCases,
    OperatorSessionUseCases,
)
from admin.infrastructure import SqlalchemyOperatorSessionRepository
from admin.interfaces.auth import ActingOperator as AdminActingOperator
from ads.application import BannerServingUseCases, CampaignUseCases
from ads.infrastructure import (
    CampaignScheduleSweepWorker,
    ConfigurationPlacementSlotAdapter,
    MediaCreativeStatusAdapter,
    SqlalchemyBannerCampaignRepository,
    SqlalchemyEntitlementProjectionRepository,
)
from ads.infrastructure.event_projection import (
    handle_entitlement_event as handle_ads_entitlement_event,
)
from ads.infrastructure.event_projection import (
    handle_media_event as handle_ads_media_event,
)
from ads.infrastructure.persistence.models import (
    OutboxEventRow as AdsOutboxEventRow,
)
from ads.interfaces.auth import ActingOperator as AdsActingOperator
from analytics.application import AuditUseCases, MetricUseCases
from analytics.application import ReportUseCases as AnalyticsReportUseCases
from analytics.infrastructure import (
    PartitionPrecreateWorker,
    SqlalchemyAuditEntryRepository,
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)
from analytics.infrastructure.event_projection import (
    handle_ads_event as handle_ads_event_for_analytics,
)
from analytics.infrastructure.event_projection import (
    handle_billing_event as handle_billing_event_for_analytics,
)
from analytics.infrastructure.event_projection import (
    handle_catalog_event as handle_catalog_event_for_analytics,
)
from analytics.infrastructure.event_projection import (
    handle_configuration_event as handle_configuration_event_for_analytics,
)
from analytics.infrastructure.event_projection import (
    handle_identity_event as handle_identity_event_for_analytics,
)
from analytics.infrastructure.event_projection import (
    handle_messaging_event as handle_messaging_event_for_analytics,
)
from analytics.infrastructure.event_projection import (
    handle_moderation_event as handle_moderation_event_for_analytics,
)
from analytics.infrastructure.event_projection import (
    handle_profiles_event as handle_profiles_event_for_analytics,
)
from analytics.interfaces.auth import ActingOperator as AnalyticsActingOperator
from backbone.outbox import OutboxDispatcher, OutboxWriter
from backbone.persistence import (
    make_engine,
    make_session_factory,
    redis_url,
    session_scope,
)
from backbone.persistence.env import required_env
from backbone.rate_limit.tracker import RedisWindowCounter
from billing.application import EntitlementUseCases, OrderUseCases, PaymentUseCases
from billing.domain import InvoiceStatus
from billing.infrastructure import (
    ConfigurationProductDefinitionAdapter,
    EntitlementExpiryWorker,
    OfflineManualPaymentAdapter,
    SqlalchemyEntitlementRepository,
    SqlalchemyInvoiceRepository,
    SqlalchemyOrderRepository,
)
from billing.infrastructure.payment_gateway.click import ClickAdapter, ClickMerchantApi
from billing.infrastructure.payment_gateway.mock import MockAdapter, MockMerchantApi
from billing.infrastructure.payment_gateway.payme import PaymeAdapter, PaymeMerchantApi
from billing.infrastructure.payment_gateway.provider_transactions import (
    ProviderTransactionRepository,
)
from billing.infrastructure.persistence.models import (
    OutboxEventRow as BillingOutboxEventRow,
)
from billing.interfaces.auth import ActingOperator
from billing.interfaces.auth import ActingUser as BillingActingUser
from billing.interfaces.di import AdminGrantCreditsUseCases
from billing.interfaces.dto import PaymentProviderStatus
from catalog.application import FavoriteUseCases, ListingUseCases
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.quota_service import QuotaEnforcementService
from catalog.infrastructure import (
    CatalogExpiryWorker,
    ConfigurationCategoryFormAdapter,
    MediaAssetReaderAdapter,
    SqlalchemyFavoriteRepository,
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from catalog.infrastructure import (
    ConfigurationPlatformSettingsAdapter as CatalogPlatformSettingsAdapter,
)
from catalog.infrastructure.event_projection import (
    handle_entitlement_event,
    handle_identity_event,
    handle_listing_promotion_event,
    handle_listing_publication_event,
    handle_registration_approval_event,
    handle_subscription_visibility_event,
    handle_trial_subscription_event,
)
from catalog.infrastructure.event_projection import (
    handle_media_event as handle_catalog_media_event,
)
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.interfaces.auth import ActingOperator as CatalogActingOperator
from catalog.interfaces.auth import ActingUser as CatalogActingUser
from catalog.interfaces.moderation_port import CatalogListingModerationAdapter
from configuration.application import (
    CategoryReadUseCases,
    ConfigurationUseCases,
    GateFailedError,
    OwnerAdminLockoutPort,
)
from configuration.domain import ConfigEntityType
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.owner_admin_lockout import (
    RedisOwnerAdminLockoutCounter,
)
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import (
    SqlalchemyConfigHeadRepository,
)
from configuration.interfaces.auth import ActingAdmin as ConfigActingAdmin
from configuration.interfaces.dto import (
    ConfigurationHeadPage,
    ConfigurationVersion,
    PageInfo,
)
from configuration.interfaces.routers import _head_to_dto, _version_to_dto
from identity.application import (
    AccountUseCases,
    AdminIdentityUseCases,
    ApplicationAuthorizationService,
    AuthenticationUseCases,
    IdentityApplicationError,
    InvalidSessionTokenError,
)
from identity.domain import AuthorizationService, IdentityDomainError, UserAccount
from identity.infrastructure import (
    AppleOAuthProviderAdapter,
    Argon2PasswordHasherAdapter,
    ConfigurationPlatformSettingsAdapter,
    ConfigurationRoleDefinitionAdapter,
    ContactPolicyPortAdapter,
    EskizSmsProviderAdapter,
    GoogleOAuthProviderAdapter,
    OtpCodeGeneratorAdapter,
    RedisLoginAttemptTracker,
    RedisSessionRepository,
    SessionTokenGeneratorAdapter,
    SmtpEmailProviderAdapter,
    SqlalchemyOtpChallengeRepository,
    SqlalchemyOtpChallengeUnitOfWork,
    SqlalchemyUserAccountRepository,
)
from identity.infrastructure import (
    handle_profiles_event as handle_profiles_event_for_identity,
)
from identity.infrastructure.persistence.models import (
    OutboxEventRow as IdentityOutboxEventRow,
)
from identity.interfaces.auth import SESSION_COOKIE_NAME, AuthenticatedRequest
from identity.interfaces.auth import ActingOperator as IdentityActingOperator
from media.application import MediaIntakeUseCases
from media.infrastructure import (
    ClamAvMalwareScanAdapter,
    MediaIntakeWorker,
    MinioStorageAdapter,
    PillowImageProcessingAdapter,
    SqlalchemyMediaAssetRepository,
)
from media.infrastructure.persistence.models import (
    OutboxEventRow as MediaOutboxEventRow,
)
from media.interfaces.auth import ActingUser
from media.interfaces.routers import _asset_to_dto
from messaging.application import BlockUseCases, ConversationUseCases, ReportUseCases
from messaging.infrastructure import (
    RedisMessageSubscriber,
    RedisRealtimePublisherAdapter,
    SqlalchemyBlockRepository,
    SqlalchemyConversationRepository,
    SqlalchemyListingOwnerProjectionReader,
    handle_listing_created,
)
from messaging.infrastructure.persistence.models import (
    OutboxEventRow as MessagingOutboxEventRow,
)
from messaging.interfaces.auth import ActingUser as MessagingActingUser
from moderation.application import ModerationActionService, ModerationUseCases
from moderation.domain import CaseStatus as ModerationCaseStatus
from moderation.infrastructure import (
    SqlalchemyModerationCaseRepository,
    handle_content_reported,
    handle_listing_flagged,
)
from moderation.infrastructure.persistence.models import (
    OutboxEventRow as ModerationOutboxEventRow,
)
from moderation.interfaces.auth import ActingModerator
from notifications.application import (
    NotificationDispatchUseCases,
    NotificationUseCases,
    QueuedDispatch,
    RecipientSnapshot,
)
from notifications.infrastructure import (
    ConfigurationNotificationTemplateAdapter,
    SqlalchemyNotificationRepository,
    SqlalchemyOrderRecipientProjectionRepository,
    WebPushProviderAdapter,
    handle_billing_event,
    handle_messaging_event,
    handle_moderation_event,
    handle_profiles_event,
)
from notifications.infrastructure import (
    EskizSmsProviderAdapter as NotificationsEskizSmsProviderAdapter,
)
from notifications.infrastructure import (
    SmtpEmailProviderAdapter as NotificationsSmtpEmailProviderAdapter,
)
from notifications.infrastructure import (
    handle_catalog_event as handle_catalog_event_for_notifications,
)
from notifications.infrastructure import (
    handle_identity_event as handle_identity_event_for_notifications,
)
from notifications.interfaces.auth import ActingUser as NotificationsActingUser
from profiles.application import ProfileUseCases, VerificationUseCases
from profiles.domain import CaseStatus as ProfilesCaseStatus
from profiles.infrastructure import (
    BadgeExpiryWorker,
    SqlalchemyBusinessProfileRepository,
    SqlalchemySubscriptionEligibilityRepository,
    SqlalchemyVerificationCaseRepository,
    SqlalchemyVerificationEligibilityRepository,
    TrialExpiryWorker,
)
from profiles.infrastructure import (
    MediaAssetReaderAdapter as ProfilesMediaAssetReaderAdapter,
)
from profiles.infrastructure.event_projection import (
    handle_entitlement_event as handle_profiles_entitlement_event,
)
from profiles.infrastructure.event_projection import (
    handle_media_event as handle_profiles_media_event,
)
from profiles.infrastructure.event_projection import (
    handle_subscription_entitlement_event,
)
from profiles.infrastructure.persistence.models import (
    OutboxEventRow as ProfilesOutboxEventRow,
)
from profiles.interfaces.auth import (
    ActingProfileManager as ProfilesActingProfileManager,
)
from profiles.interfaces.auth import ActingReviewer as ProfilesActingReviewer
from profiles.interfaces.auth import ActingUser as ProfilesActingUser
from profiles.interfaces.moderation_port import ProfilesModerationAdapter
from search.application import SearchUseCases
from search.infrastructure import (
    ConfigurationSearchConfigurationAdapter,
    OpenSearchIndexAdapter,
    SqlalchemyFallbackIndexRepository,
    make_search_event_handler,
)
from shared_kernel import (
    BusinessProfileId,
    EventEnvelope,
    ListingId,
    MediaAssetId,
    UserId,
)


@lru_cache(maxsize=1)
def _configuration_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


@lru_cache(maxsize=1)
def _configuration_redis_client() -> Redis:
    return Redis.from_url(redis_url())


async def _configuration_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_configuration_session_factory()) as session:
        yield session


def _configuration_snapshot_cache() -> RedisSnapshotCache:
    return RedisSnapshotCache(_configuration_redis_client())


@lru_cache(maxsize=1)
def _owner_admin_lockout_counter() -> RedisOwnerAdminLockoutCounter:
    return RedisOwnerAdminLockoutCounter(
        RedisWindowCounter(
            # A real `Redis` client's methods are strict supersets of `_RedisCounterClient`'s
            # narrow surface (e.g. `delete`'s real signature is variadic) -- see that Protocol's
            # own docstring for why mypy's structural check still flags this as a mismatch.
            _configuration_redis_client(),  # type: ignore[arg-type]
            key_prefix="configuration:owner_admin_lockout",
        )
    )


async def provide_owner_admin_lockout_counter() -> OwnerAdminLockoutPort:
    return _owner_admin_lockout_counter()


async def provide_configuration_use_cases() -> AsyncIterator[ConfigurationUseCases]:
    """Deliberately does not delegate to `_configuration_session()`/`session_scope`: a
    `GateFailedError` raised by `ConfigurationUseCases.publish` carries an already-applied,
    intentional "revert this version to DRAFT" write (Config Framework Sec 2.6 -- the gate is
    re-run on every re-entry, including the checker's call, and a failure reverts the version
    for the maker to re-edit). `session_scope`'s generic "roll back on any exception" would
    silently discard that revert along with the exception it's reporting, leaving the version
    stuck in APPROVAL with no way to resubmit. A gate-failure outcome is a normal, intentional
    business result -- not a transaction-aborting error -- so it gets its own commit before the
    exception continues on to the router's error mapper; any other exception still rolls back."""
    session = _configuration_session_factory()()
    repo = SqlalchemyConfigHeadRepository(session)
    outbox = OutboxWriter(session, OutboxEvent)
    try:
        yield ConfigurationUseCases(repo, _configuration_snapshot_cache(), outbox)
    except GateFailedError:
        await session.commit()
        raise
    except BaseException:
        await session.rollback()
        raise
    else:
        await session.commit()
    finally:
        await session.close()


async def provide_category_read_use_cases() -> AsyncIterator[CategoryReadUseCases]:
    async for session in _configuration_session():
        repo = SqlalchemyConfigHeadRepository(session)
        yield CategoryReadUseCases(repo, _configuration_snapshot_cache())


# == identity (Task P-05) =========================================================================


class _ConfigurationPortBridge:
    """Adapts `configuration.application.ConfigurationUseCases` (domain-typed) to the narrow
    `identity.infrastructure.configuration_adapter._ConfigReader` shape identity's RoleDefinition/
    PlatformSettings readers consume (DTO-typed). Lives here, not inside either module's own
    package tree, since only the composition root may see both modules' internals at once --
    exactly the reason this file exists (see its own module docstring). Each call opens its own
    short read-only unit of work; RoleDefinition/PlatformSettings reads have no cross-call
    consistency requirement (published configuration versions are immutable once published)."""

    async def list_config_heads(
        self,
        entity_type: str,
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> ConfigurationHeadPage:
        page_limit = limit or 20
        async for session in _configuration_session():
            repo = SqlalchemyConfigHeadRepository(session)
            use_cases = ConfigurationUseCases(
                repo,
                _configuration_snapshot_cache(),
                OutboxWriter(session, OutboxEvent),
            )
            heads, next_cursor = await use_cases.list_heads(
                ConfigEntityType(entity_type), cursor=cursor, limit=page_limit
            )
            return ConfigurationHeadPage(
                items=[_head_to_dto(h) for h in heads],
                page=PageInfo(limit=page_limit, next_cursor=next_cursor),
            )
        raise AssertionError("unreachable: _configuration_session always yields exactly once")

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        async for session in _configuration_session():
            repo = SqlalchemyConfigHeadRepository(session)
            use_cases = ConfigurationUseCases(
                repo,
                _configuration_snapshot_cache(),
                OutboxWriter(session, OutboxEvent),
            )
            version = await use_cases.get_version(
                ConfigEntityType(entity_type), head_id, version_id
            )
            return _version_to_dto(version)
        raise AssertionError("unreachable: _configuration_session always yields exactly once")


@lru_cache(maxsize=1)
def _identity_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


@lru_cache(maxsize=1)
def _identity_redis_client() -> Redis:
    return Redis.from_url(redis_url())


async def _identity_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_identity_session_factory()) as session:
        yield session


@lru_cache(maxsize=1)
def _role_definition_reader() -> ConfigurationRoleDefinitionAdapter:
    return ConfigurationRoleDefinitionAdapter(_ConfigurationPortBridge())


@lru_cache(maxsize=1)
def _platform_settings_reader() -> ConfigurationPlatformSettingsAdapter:
    return ConfigurationPlatformSettingsAdapter(_ConfigurationPortBridge())


@lru_cache(maxsize=1)
def _eskiz_provider() -> EskizSmsProviderAdapter:
    return EskizSmsProviderAdapter()


@lru_cache(maxsize=1)
def _email_provider() -> SmtpEmailProviderAdapter:
    return SmtpEmailProviderAdapter()


@lru_cache(maxsize=1)
def _google_provider() -> GoogleOAuthProviderAdapter:
    return GoogleOAuthProviderAdapter()


@lru_cache(maxsize=1)
def _apple_provider() -> AppleOAuthProviderAdapter:
    return AppleOAuthProviderAdapter()


@lru_cache(maxsize=1)
def _password_hasher() -> Argon2PasswordHasherAdapter:
    return Argon2PasswordHasherAdapter()


@lru_cache(maxsize=1)
def _otp_code_generator() -> OtpCodeGeneratorAdapter:
    return OtpCodeGeneratorAdapter()


@lru_cache(maxsize=1)
def _session_token_generator() -> SessionTokenGeneratorAdapter:
    return SessionTokenGeneratorAdapter()


@lru_cache(maxsize=1)
def _login_attempt_tracker() -> RedisLoginAttemptTracker:
    return RedisLoginAttemptTracker(_identity_redis_client())


async def provide_authentication_use_cases() -> AsyncIterator[AuthenticationUseCases]:
    async for session in _identity_session():
        yield AuthenticationUseCases(
            accounts=SqlalchemyUserAccountRepository(session),
            sessions=RedisSessionRepository(_identity_redis_client()),
            otp_challenges=SqlalchemyOtpChallengeRepository(session),
            otp_challenge_unit_of_work=SqlalchemyOtpChallengeUnitOfWork(
                _identity_session_factory()
            ),
            outbox=OutboxWriter(session, IdentityOutboxEventRow),
            otp_sms_provider=_eskiz_provider(),
            email_provider=_email_provider(),
            google_provider=_google_provider(),
            apple_provider=_apple_provider(),
            password_hasher=_password_hasher(),
            otp_code_generator=_otp_code_generator(),
            session_token_generator=_session_token_generator(),
            platform_settings=_platform_settings_reader(),
            login_attempts=_login_attempt_tracker(),
        )


def _build_account_use_cases(session: AsyncSession) -> AccountUseCases:
    return AccountUseCases(
        accounts=SqlalchemyUserAccountRepository(session),
        sessions=RedisSessionRepository(_identity_redis_client()),
        outbox=OutboxWriter(session, IdentityOutboxEventRow),
        password_hasher=_password_hasher(),
    )


async def provide_account_use_cases() -> AsyncIterator[AccountUseCases]:
    async for session in _identity_session():
        yield _build_account_use_cases(session)


async def provide_admin_identity_use_cases() -> AsyncIterator[AdminIdentityUseCases]:
    async for session in _identity_session():
        yield AdminIdentityUseCases(
            accounts=SqlalchemyUserAccountRepository(session),
            sessions=RedisSessionRepository(_identity_redis_client()),
            outbox=OutboxWriter(session, IdentityOutboxEventRow),
            role_reader=_role_definition_reader(),
        )


async def provide_configuration_acting_admin(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> ConfigActingAdmin:
    """Overrides `configuration.interfaces.auth.get_acting_admin`, replacing the P-04 stand-in
    that read the caller's identity and permission set straight from the client-supplied
    `X-Actor-Id` / `X-Permission-Keys` headers (DEF-01).

    That stand-in verified nothing: any caller could POST to any of the 14 `admin/config/*`
    operations with a freshly-invented UUID and `X-Permission-Keys: config:category:manage` and be
    authorized as an administrator, with no cookie and no token. Maker-checker was intact in shape
    but vacuous in effect -- two self-claimed UUIDs satisfy "two distinct principals" perfectly --
    and the audit trail recorded those forged ids as real actors.

    This resolves both fields the same way every other module already does: `ah_session` cookie (or
    Bearer) -> hashed -> identity's real `ApplicationAuthorizationService.resolve_acting_context`,
    which runs Security Sec 4.2's Gates 1-2 and returns the server-resolved
    `effective_permissions` for that exact acting scope.

    No `AuthorizationService().authorize(...)` call here, unlike the single-permission operators
    nearby: `configuration`'s routers each check their own entity-specific key via
    `require_permission`, and the maker-checker workflow needs the whole set rather than one
    pre-checked key. Gate 3 still runs -- it just runs per-operation, in the router, against a set
    that is now genuinely the server's rather than the caller's claim.
    """
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return ConfigActingAdmin(
            actor_id=account.id.value, permission_keys=context.effective_permissions
        )
    raise AssertionError("unreachable: _identity_session always yields exactly once")


async def _resolve_identity_acting_operator(
    ah_session: str | None, authorization: str | None, *, permission_key: str
) -> IdentityActingOperator:
    """Shared body for `provide_users_acting_operator`/`provide_roles_acting_operator` (Task
    P-16, ADR-0006) -- identical Gate-3 shape to `provide_ads_acting_operator`/`provide_audit_
    acting_operator`, just parameterised by which of the two permission keys this router's four
    operations need."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, permission_key)
        return IdentityActingOperator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


async def provide_users_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> IdentityActingOperator:
    """Overrides `identity.interfaces.di.get_users_acting_operator` -- backs `adminListUsers`/
    `adminChangeUserStatus`, gated by `identity:account:manage_status`."""
    return await _resolve_identity_acting_operator(
        ah_session, authorization, permission_key="identity:account:manage_status"
    )


async def provide_roles_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> IdentityActingOperator:
    """Overrides `identity.interfaces.di.get_roles_acting_operator` -- backs `assignRole`/
    `revokeRole` (ADR-0006), gated by `identity:role:assign` -- a DIFFERENT permission than
    `provide_users_acting_operator`'s."""
    return await _resolve_identity_acting_operator(
        ah_session, authorization, permission_key="identity:role:assign"
    )


async def provide_registration_reviewer(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> IdentityActingOperator:
    """Overrides `identity.interfaces.di.get_registration_reviewer` (ADR-0007) -- backs
    `listRegistrationQueue`/`decideRegistration`, gated by `identity:registration:review`."""
    return await _resolve_identity_acting_operator(
        ah_session, authorization, permission_key="identity:registration:review"
    )


def _raw_session_token(ah_session: str | None, authorization: str | None) -> str | None:
    if ah_session:
        return ah_session
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :].strip()
    return None


async def provide_authenticated_request(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> AuthenticatedRequest:
    """Overrides `identity.interfaces.di.get_authenticated_request` (Security Sec 4.2 Gates
    1-2). The stub in `identity/interfaces/di.py` takes no parameters; FastAPI's
    `dependency_overrides` resolves the *override's own* signature, not the original's, so this
    is free to declare the `Cookie`/`Header` params the real resolution needs."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, session_obj, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return AuthenticatedRequest(account=account, session=session_obj)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


# == media (Task P-06) ============================================================================


@lru_cache(maxsize=1)
def _media_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _media_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_media_session_factory()) as session:
        yield session


@lru_cache(maxsize=1)
def _minio_adapter() -> MinioStorageAdapter:
    return MinioStorageAdapter()


@lru_cache(maxsize=1)
def _clamav_adapter() -> ClamAvMalwareScanAdapter:
    return ClamAvMalwareScanAdapter()


@lru_cache(maxsize=1)
def _pillow_adapter() -> PillowImageProcessingAdapter:
    return PillowImageProcessingAdapter()


async def provide_media_intake_use_cases() -> AsyncIterator[MediaIntakeUseCases]:
    async for session in _media_session():
        yield MediaIntakeUseCases(
            assets=SqlalchemyMediaAssetRepository(session),
            storage=_minio_adapter(),
            outbox=OutboxWriter(session, MediaOutboxEventRow),
            presign_expiry_seconds=int(required_env("MEDIA_PRESIGN_EXPIRY_SECONDS")),
        )


async def provide_acting_user(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> ActingUser:
    """Overrides `media.interfaces.di.get_acting_user` (Security Sec 4.2 Gates 1-2). Reuses
    identity's own session/account resolution machinery (`_identity_session`,
    `ApplicationAuthorizationService.resolve_acting_context`, `_role_definition_reader`,
    `_session_token_generator`) -- media's *own* source never imports `identity`
    (`cross-module-media`, tools/importlinter.cfg); this composition-root function is the one
    place allowed to see both modules' internals and bridge them, exactly like
    `provide_authenticated_request` above does for identity's own routers. No permission check
    (Gates 3-4) -- media's self-service operations need only a resolved account id, see
    `media.interfaces.auth.ActingUser`'s docstring."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return ActingUser(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def provide_media_intake_worker() -> MediaIntakeWorker:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/media_worker.py`), which has no HTTP request/response cycle to hang a
    `Depends(...)` off of (Security Sec 7 "Background workers ... no inbound network surface")."""
    return MediaIntakeWorker(
        session_factory=_media_session_factory(),
        outbox_model=MediaOutboxEventRow,
        storage=_minio_adapter(),
        scanner=_clamav_adapter(),
        processor=_pillow_adapter(),
    )


# == catalog (Task P-07) ==========================================================================


@lru_cache(maxsize=1)
def _catalog_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _catalog_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_catalog_session_factory()) as session:
        yield session


class _CategoryReaderBridge:
    """Adapts `configuration.application.category_read.CategoryReadUseCases` (dict-snapshot
    typed) to the narrow `catalog.infrastructure.configuration_adapter._CategoryReader` shape
    catalog's own `ConfigurationCategoryFormAdapter` consumes -- see that module's own docstring
    for why this bridges to the read use case directly rather than the DTO-typed
    `ConfigurationPort`. Lives here, not inside either module's own package tree, for the same
    reason `_ConfigurationPortBridge` above does."""

    async def get_category(self, category_id: UUID) -> dict[str, Any] | None:
        async for session in _configuration_session():
            repo = SqlalchemyConfigHeadRepository(session)
            use_cases = CategoryReadUseCases(repo, _configuration_snapshot_cache())
            return await use_cases.get_category(category_id)
        raise AssertionError("unreachable: _configuration_session always yields exactly once")

    async def get_category_form(self, category_id: UUID) -> dict[str, Any] | None:
        async for session in _configuration_session():
            repo = SqlalchemyConfigHeadRepository(session)
            use_cases = CategoryReadUseCases(repo, _configuration_snapshot_cache())
            return await use_cases.get_category_form(category_id)
        raise AssertionError("unreachable: _configuration_session always yields exactly once")


class _CatalogMediaReaderBridge:
    """Adapts `media.application.MediaIntakeUseCases.get_media` to the narrow
    `catalog.infrastructure.media_adapter._MediaReader` shape, translating through `media.
    interfaces.routers._asset_to_dto` (the same private-helper reuse `_head_to_dto`/
    `_version_to_dto` already establish above) so catalog only ever sees the DTO shape
    `media.interfaces.ports.MediaIntakePort.get_media` itself would return."""

    async def get_media(self, media_id: UUID) -> object:
        async for session in _media_session():
            use_cases = MediaIntakeUseCases(
                assets=SqlalchemyMediaAssetRepository(session),
                storage=_minio_adapter(),
                outbox=OutboxWriter(session, MediaOutboxEventRow),
                presign_expiry_seconds=int(required_env("MEDIA_PRESIGN_EXPIRY_SECONDS")),
            )
            asset = await use_cases.get_media(MediaAssetId(value=media_id))
            return _asset_to_dto(asset)
        raise AssertionError("unreachable: _media_session always yields exactly once")


@lru_cache(maxsize=1)
def _catalog_category_form_adapter() -> ConfigurationCategoryFormAdapter:
    return ConfigurationCategoryFormAdapter(_CategoryReaderBridge())


@lru_cache(maxsize=1)
def _catalog_platform_settings_adapter() -> CatalogPlatformSettingsAdapter:
    return CatalogPlatformSettingsAdapter(_ConfigurationPortBridge())


@lru_cache(maxsize=1)
def _catalog_media_adapter() -> MediaAssetReaderAdapter:
    return MediaAssetReaderAdapter(_CatalogMediaReaderBridge())


class _CreditBalanceBridge:
    """Implements `catalog.application.ports.CreditBalancePort` directly (listing paywall Phase
    4, 2026-08-23) -- mirrors `_ConfigurationPortBridge`'s own in-process cross-module bridge
    shape (no separate narrow-Protocol-plus-adapter indirection needed here, unlike `media`'s own
    `_CatalogMediaReaderBridge` + `MediaAssetReaderAdapter` pair: `CreditBalancePort`'s one method
    already matches what this bridge needs to call). Opens its OWN billing session/transaction,
    committed independently BEFORE catalog's own `create_listing` transaction -- see
    `CreditBalancePort`'s own docstring for why that ordering matters."""

    async def consume_one_listing_credit(self, *, owner_profile_id: BusinessProfileId) -> bool:
        async for session in _billing_session():
            use_cases = EntitlementUseCases(
                entitlements=SqlalchemyEntitlementRepository(session),
                orders=SqlalchemyOrderRepository(session),
                outbox=OutboxWriter(session, BillingOutboxEventRow),
            )
            entitlement = await use_cases.consume_listing_credit(
                purchaser_profile_id=owner_profile_id, now=datetime.now(UTC)
            )
            return entitlement is not None
        raise AssertionError("unreachable: _billing_session always yields exactly once")


@lru_cache(maxsize=1)
def _catalog_credit_balance_port() -> _CreditBalanceBridge:
    return _CreditBalanceBridge()


def _build_listing_use_cases(session: AsyncSession) -> ListingUseCases:
    """Factored out of `provide_listing_use_cases`'s own former inline body (Task P-07) so
    moderation's listing-command bridge and identity's account-suspension projection handler
    (both Task P-12, below) can build the exact same real `ListingUseCases` against their own
    short-lived sessions, instead of re-deriving its constructor call a third time."""
    listings = SqlalchemyListingRepository(session)
    return ListingUseCases(
        listings=listings,
        categories=_catalog_category_form_adapter(),
        settings=_catalog_platform_settings_adapter(),
        media=_catalog_media_adapter(),
        outbox=OutboxWriter(session, CatalogOutboxEventRow),
        quota=QuotaEnforcementService(
            subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
        ),
        duplicates=DuplicateDetectionService(listings=listings),
        credit_balance=_catalog_credit_balance_port(),
    )


async def provide_listing_use_cases() -> AsyncIterator[ListingUseCases]:
    async for session in _catalog_session():
        yield _build_listing_use_cases(session)


async def provide_favorite_use_cases() -> AsyncIterator[FavoriteUseCases]:
    async for session in _catalog_session():
        yield FavoriteUseCases(
            favorites=SqlalchemyFavoriteRepository(session),
            listings=SqlalchemyListingRepository(session),
            outbox=OutboxWriter(session, CatalogOutboxEventRow),
        )


async def provide_catalog_acting_user(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> CatalogActingUser:
    """Overrides `catalog.interfaces.di.get_acting_user`. Reuses identity's own session/account
    resolution machinery exactly like `provide_acting_user` (media) does -- catalog's own source
    never imports `identity` (`cross-module-catalog`). Unlike media's `ActingUser`, this one also
    carries `acting_profile_id` straight off the resolved `Session` domain object (`session_obj.
    acting_profile_id`) -- catalog's create/quota paths need to know the acting business-profile
    context, not just the account id."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, session_obj, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return CatalogActingUser(
            account_id=account.id, acting_profile_id=session_obj.acting_profile_id
        )
    raise AssertionError("unreachable: _identity_session always yields exactly once")


async def provide_catalog_optional_acting_user(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> CatalogActingUser | None:
    """Overrides `catalog.interfaces.di.get_optional_acting_user` -- backs the three
    unauthenticated operations (`listListings`/`getListing`/`listListingImages`) that still want
    to know *if* a caller happens to be authenticated without *requiring* it. Returns `None`
    rather than raising for a missing or invalid session. `resolve_acting_context`'s own
    docstring documents both failure halves it can raise: `IdentityApplicationError`
    (`InvalidSessionTokenError`/`AccountNotFoundError` -- no session row, or the account it
    points at is gone) and the domain `IdentityDomainError` (`SessionExpiredError`/
    `SessionRevokedError`/`AccountNotActiveError` -- the session row exists but is no longer
    valid) -- both must degrade to anonymous here, or a merely-expired cookie would 401 a public
    browse endpoint instead of falling back gracefully, unlike `provide_catalog_acting_user`
    (which requires a session and is right to propagate either failure)."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        return None
    try:
        return await provide_catalog_acting_user(ah_session=ah_session, authorization=authorization)
    except (IdentityApplicationError, IdentityDomainError):
        return None


async def provide_catalog_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> CatalogActingOperator:
    """Overrides `catalog.interfaces.di.get_acting_operator` -- backs `adminListListings`
    (2026-08-24, `/admin/listings`). Runs the REAL Security Sec 4.2 Gate-3 check
    (`identity.domain.AuthorizationService.authorize`) against `catalog:listing:moderate`
    (already whitelisted, previously only ever DOCUMENTED as this module's admin-surface gate,
    never actually consulted by any real dependency until now -- catalog had no operator-gated
    route at all before this one), the same pattern `provide_billing_acting_operator`/
    `provide_ads_acting_operator` already establish."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "catalog:listing:moderate")
        return CatalogActingOperator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def provide_catalog_expiry_worker() -> CatalogExpiryWorker:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/catalog_worker.py`), same discipline as `provide_media_intake_worker`."""
    return CatalogExpiryWorker(
        session_factory=_catalog_session_factory(),
        outbox_model=CatalogOutboxEventRow,
        categories=_catalog_category_form_adapter(),
        settings=_catalog_platform_settings_adapter(),
        media=_catalog_media_adapter(),
    )


# == billing (Task P-09) ==========================================================================


@lru_cache(maxsize=1)
def _billing_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _billing_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_billing_session_factory()) as session:
        yield session


# == search (Task P-08) ===========================================================================


@lru_cache(maxsize=1)
def _search_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _search_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_search_session_factory()) as session:
        yield session


@lru_cache(maxsize=1)
def _billing_product_definition_adapter() -> ConfigurationProductDefinitionAdapter:
    """Reuses `_ConfigurationPortBridge` (identity's own section, above) unmodified -- the third
    reuse of that bridge (after identity's RoleDefinition/PlatformSettings readers and catalog's
    own `_catalog_platform_settings_adapter`): it already implements the exact narrow
    `list_config_heads`/`get_config_version` shape `billing.infrastructure.configuration_adapter.
    _ConfigurationReader` consumes, entity-type-agnostic by design."""
    return ConfigurationProductDefinitionAdapter(_ConfigurationPortBridge())


@lru_cache(maxsize=1)
def _billing_payment_provider() -> OfflineManualPaymentAdapter:
    """BRULE-15/FR-BILL-004: the sole `PaymentProviderPort` implementation registered in v1 --
    no online provider is wired, configured, or reachable anywhere in this composition root."""
    return OfflineManualPaymentAdapter()


async def provide_order_use_cases() -> AsyncIterator[OrderUseCases]:
    async for session in _billing_session():
        yield OrderUseCases(
            orders=SqlalchemyOrderRepository(session),
            invoices=SqlalchemyInvoiceRepository(session),
            products=_billing_product_definition_adapter(),
            outbox=OutboxWriter(session, BillingOutboxEventRow),
        )


async def provide_admin_grant_credits_use_cases() -> AsyncIterator[AdminGrantCreditsUseCases]:
    """Backs `admin_grant_listing_credits` (`POST /admin/billing/profiles/{id}/grant-credits`)
    only -- unlike `provide_order_use_cases`/`provide_payment_use_cases` (each its own independent
    `_billing_session()`, correct for every OTHER caller since a buyer's `createOrder` and a later
    `confirmInvoicePayment` are always two separate HTTP requests), this endpoint calls
    `create_order` then `confirm_payment` in the SAME request, so both use-case sets must share
    ONE session/transaction or the invoice `create_order` just added is invisible to
    `confirm_payment`'s own read (confirmed via a real 404 `InvoiceNotFoundError` in production
    before this provider existed, 2026-08-25)."""
    async for session in _billing_session():
        yield AdminGrantCreditsUseCases(
            orders=OrderUseCases(
                orders=SqlalchemyOrderRepository(session),
                invoices=SqlalchemyInvoiceRepository(session),
                products=_billing_product_definition_adapter(),
                outbox=OutboxWriter(session, BillingOutboxEventRow),
            ),
            payments=PaymentUseCases(
                orders=SqlalchemyOrderRepository(session),
                invoices=SqlalchemyInvoiceRepository(session),
                entitlements=SqlalchemyEntitlementRepository(session),
                payment_provider=_billing_payment_provider(),
                outbox=OutboxWriter(session, BillingOutboxEventRow),
            ),
        )


async def provide_payment_use_cases() -> AsyncIterator[PaymentUseCases]:
    """The sanctioned synchronous transaction's own composition (DB Architecture Sec 1.3;
    `billing.application.payment_use_cases.PaymentUseCases.confirm_payment`'s own module
    docstring): `SqlalchemyOrderRepository`/`SqlalchemyInvoiceRepository`/
    `SqlalchemyEntitlementRepository`/`OutboxWriter` are all constructed against the SAME
    `session` bound by this one `_billing_session()` iteration -- `confirm_payment`'s three
    aggregate saves and two outbox appends therefore commit or roll back together by
    construction, not by a shared-transaction convention a future edit could accidentally break."""
    async for session in _billing_session():
        yield PaymentUseCases(
            orders=SqlalchemyOrderRepository(session),
            invoices=SqlalchemyInvoiceRepository(session),
            entitlements=SqlalchemyEntitlementRepository(session),
            payment_provider=_billing_payment_provider(),
            outbox=OutboxWriter(session, BillingOutboxEventRow),
        )


@lru_cache(maxsize=1)
def _payme_merchant_key() -> str:
    """ADR-0010. Placeholder (`CHANGE_ME_IN_SECRETS_STORE`) in every env file until the repository
    owner registers a real Payme merchant account -- `required_env` (not eager at import time,
    only read when a Payme webhook request actually arrives via `provide_payme_merchant_key`)
    means a missing var 500s Payme's own webhook only, never the rest of billing, unlike the
    Apple-adapter eager-construction footgun this composition root already learned from once."""
    return required_env("PAYME_SECRET_KEY")


@lru_cache(maxsize=1)
def _click_secret_key() -> str:
    """ADR-0010. Same placeholder-until-real-credentials convention as `_payme_merchant_key`."""
    return required_env("CLICK_SECRET_KEY")


async def provide_payme_merchant_key() -> str:
    """Overrides `billing.infrastructure.payment_gateway.webhook_routers.get_payme_merchant_key`."""
    return _payme_merchant_key()


async def provide_click_secret_key() -> str:
    """Overrides `billing.infrastructure.payment_gateway.webhook_routers.get_click_secret_key`."""
    return _click_secret_key()


async def provide_payme_merchant_api() -> AsyncIterator[PaymeMerchantApi]:
    """ADR-0010. Overrides `webhook_routers.get_payme_merchant_api`. Same "one session backs
    everything" discipline as `provide_payment_use_cases` -- `PaymeMerchantApi`'s own
    `PaymentUseCases` is constructed here with `PaymeAdapter` as its `PaymentProviderPort`
    (never `OfflineManualPaymentAdapter`, never shared with `provide_payment_use_cases`'s own
    instance), so `PerformTransaction`'s provider-transaction update and its `confirm_payment`
    call commit or roll back together, and `confirm_payment`'s own `payment_provider.confirm(...)`
    call verifies a real `ProviderTransaction` row rather than trusting `confirmed=True` blindly."""
    async for session in _billing_session():
        transactions = ProviderTransactionRepository(session)
        payment_use_cases = PaymentUseCases(
            orders=SqlalchemyOrderRepository(session),
            invoices=SqlalchemyInvoiceRepository(session),
            entitlements=SqlalchemyEntitlementRepository(session),
            payment_provider=PaymeAdapter(transactions),
            outbox=OutboxWriter(session, BillingOutboxEventRow),
        )
        yield PaymeMerchantApi(
            invoices=SqlalchemyInvoiceRepository(session),
            transactions=transactions,
            payment_use_cases=payment_use_cases,
        )


async def provide_click_merchant_api() -> AsyncIterator[ClickMerchantApi]:
    """ADR-0010. Click sibling of `provide_payme_merchant_api` -- identical shape, `ClickAdapter`
    instead of `PaymeAdapter`."""
    async for session in _billing_session():
        transactions = ProviderTransactionRepository(session)
        payment_use_cases = PaymentUseCases(
            orders=SqlalchemyOrderRepository(session),
            invoices=SqlalchemyInvoiceRepository(session),
            entitlements=SqlalchemyEntitlementRepository(session),
            payment_provider=ClickAdapter(transactions),
            outbox=OutboxWriter(session, BillingOutboxEventRow),
        )
        yield ClickMerchantApi(
            invoices=SqlalchemyInvoiceRepository(session),
            transactions=transactions,
            payment_use_cases=payment_use_cases,
        )


def payment_provider_mode() -> str:
    """`.env` `PAYMENT_PROVIDER` (`mock|payme|click`, default `offline`) -- governs ONLY whether
    `main.py` mounts `mock_payment_router` (`POST /payments/mock/pay`). Payme/Click's own routes
    are always mounted regardless of this value (each protected by its own signature verification
    instead of an env gate) -- this variable exists solely to keep the unauthenticated,
    unverified mock instant-pay endpoint out of the ASGI app unless explicitly turned on."""
    return os.environ.get("PAYMENT_PROVIDER", "offline")


def provide_payment_provider_status() -> PaymentProviderStatus:
    """Overrides `billing.interfaces.di.get_payment_provider_status` (2026-08-24, `/admin/
    settings`'s read-only provider panel). Deliberately reports presence only (`bool`), never a
    key's value -- the admin-panel request that first prompted this endpoint also asked for the
    secrets themselves to be web-editable, which was turned down on a real security concern
    (payment secrets in a DB/web-form widen the attack surface, and this server's own security
    audit already flags fail2ban/UFW as not yet hardened) -- `.env` stays the only place a real
    `PAYME_SECRET_KEY`/`CLICK_SECRET_KEY` is ever written or read, exactly like every other secret
    this composition root reads via `os.environ` (mirrors `payment_provider_mode`'s own
    precedent, immediately above)."""
    return PaymentProviderStatus(
        payme_configured=bool(os.environ.get("PAYME_SECRET_KEY")),
        click_configured=bool(os.environ.get("CLICK_SECRET_KEY")),
        mock_enabled=payment_provider_mode() == "mock",
    )


async def provide_mock_merchant_api() -> AsyncIterator[MockMerchantApi]:
    """Listing paywall Phase 2 (2026-08-23). Mock sibling of `provide_payme_merchant_api`/
    `provide_click_merchant_api` -- identical shape, `MockAdapter` instead of `PaymeAdapter`/
    `ClickAdapter`. Registering this override is harmless even when `PAYMENT_PROVIDER != mock`
    (matches every other DI-override registration happening unconditionally in `main.py`'s
    `create_app()`); only the route's MOUNTING is env-gated, so an unmounted route can never
    reach this dependency in the first place."""
    async for session in _billing_session():
        transactions = ProviderTransactionRepository(session)
        payment_use_cases = PaymentUseCases(
            orders=SqlalchemyOrderRepository(session),
            invoices=SqlalchemyInvoiceRepository(session),
            entitlements=SqlalchemyEntitlementRepository(session),
            payment_provider=MockAdapter(transactions),
            outbox=OutboxWriter(session, BillingOutboxEventRow),
        )
        yield MockMerchantApi(
            invoices=SqlalchemyInvoiceRepository(session),
            transactions=transactions,
            payment_use_cases=payment_use_cases,
        )


async def provide_entitlement_use_cases() -> AsyncIterator[EntitlementUseCases]:
    async for session in _billing_session():
        yield EntitlementUseCases(
            entitlements=SqlalchemyEntitlementRepository(session),
            orders=SqlalchemyOrderRepository(session),
            outbox=OutboxWriter(session, BillingOutboxEventRow),
        )


async def provide_billing_acting_user(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> BillingActingUser:
    """Overrides `billing.interfaces.di.get_acting_user`. Reuses identity's own session/account
    resolution machinery exactly like `provide_catalog_acting_user` does -- billing's own source
    never imports `identity` (`cross-module-billing`), the same self-imposed discipline catalog
    already established even though SAD Sec 8.1's static table permits `billing -> identity`."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, session_obj, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return BillingActingUser(
            account_id=account.id, acting_profile_id=session_obj.acting_profile_id
        )
    raise AssertionError("unreachable: _identity_session always yields exactly once")


async def provide_billing_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> ActingOperator:
    """Overrides `billing.interfaces.di.get_acting_operator` -- backs `confirmInvoicePayment`,
    the one admin-facing operation billing owns. Unlike `provide_catalog_acting_user` (which only
    resolves *who* is acting, since none of catalog's own routes gate on a permission key today),
    this also runs the REAL Security Sec 4.2 Gate-3 check (`identity.domain.AuthorizationService.
    authorize`) against `billing:invoice:confirm_payment` (`configuration.domain.whitelist.
    PERMISSION_KEYS`'s own P-09 extension) -- the same default-deny mechanism identity's own
    admin capabilities and catalog's `catalog:listing:moderate` are documented to use, actually
    consulted here rather than merely declared."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "billing:invoice:confirm_payment")
        return ActingOperator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def provide_billing_entitlement_expiry_worker() -> EntitlementExpiryWorker:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/billing_worker.py`), same discipline as `provide_catalog_expiry_worker`."""
    return EntitlementExpiryWorker(
        session_factory=_billing_session_factory(), outbox_model=BillingOutboxEventRow
    )


_CATALOG_RELEVANT_ENTITLEMENT_EVENT_TYPES = {"EntitlementActivated"}
"""Deliberately excludes `EntitlementExpired`/`EntitlementRevoked`: catalog's own already-merged
`handle_entitlement_event` (`catalog/infrastructure/event_projection.py`) has no "withdraw this
profile's quota" code path -- it only ever upserts a `SubscriptionSnapshot` from whatever the
payload says, regardless of event_type. Routing an expiry/revocation event into it would silently
*reapply* the (now-stale) quota data rather than withdrawing it, actively worse than not routing
it at all. This is a confirmed, out-of-scope limitation of catalog's own P-07 code (flagged in
`billing/README.md` "Known gaps"), not something this task may fix (AIR-01)."""

_CATALOG_RELEVANT_ENTITLEMENT_TYPES = {"ACTIVE_SUBSCRIPTION"}
"""catalog's `handle_entitlement_event` only ever builds a `SubscriptionSnapshot` -- routing a
`LISTING_PROMOTION`/`VERIFICATION_ELIGIBILITY`/`BANNER_SLOT_BOOKING` `EntitlementActivated` event
into it would silently write bogus subscription-quota data for that profile."""

_CATALOG_PROMOTION_RELEVANT_ENTITLEMENT_EVENT_TYPES = {
    "EntitlementActivated",
    "EntitlementExpired",
    "EntitlementRevoked",
}
"""P-20: unlike the `ACTIVE_SUBSCRIPTION` route above (which has no withdrawal path, see its own
comment), `handle_listing_promotion_event` DOES have one (`ListingUseCases.
clear_promotion_projection`) -- all three event types are routed, keeping `Listing.promotion`
accurate rather than leaving a stale promotion marker after the entitlement actually
expired/was revoked."""

_CATALOG_PROMOTION_RELEVANT_ENTITLEMENT_TYPES = {"LISTING_PROMOTION"}

_CATALOG_PUBLICATION_RELEVANT_ENTITLEMENT_EVENT_TYPES = {"EntitlementActivated"}
"""Listing paywall Phase 3 (2026-08-23): unlike the promotion/subscription routes above,
`handle_listing_publication_event` has no withdrawal path by design (its own docstring) --
publishing a paid listing is permanent, not a lease that expires or gets revoked -- so only
`EntitlementActivated` is routed."""

_CATALOG_PUBLICATION_RELEVANT_ENTITLEMENT_TYPES = {"LISTING_PUBLICATION"}

_CATALOG_SUBSCRIPTION_VISIBILITY_RELEVANT_ENTITLEMENT_EVENT_TYPES = {
    "EntitlementActivated",
    "EntitlementExpired",
    "EntitlementRevoked",
}
"""Monetization: unlike `handle_entitlement_event`'s own `ACTIVE_SUBSCRIPTION` route above (quota
snapshot only, no withdrawal path -- see its own comment), `handle_subscription_visibility_event`
DOES have one (`ListingUseCases.suspend_all_by_owner_profile`/`reactivate_all_by_owner_profile`),
so -- like the promotion route just above it -- all three event types are routed, keeping a
legal-entity profile's listings hidden while its subscription has lapsed and visible again once
renewed. Reuses `_CATALOG_RELEVANT_ENTITLEMENT_TYPES` (`{"ACTIVE_SUBSCRIPTION"}`) for the
entitlement-type filter -- same slice of events as the quota route, routed to a second,
independent handler."""

_PROFILES_RELEVANT_ENTITLEMENT_EVENT_TYPES = {
    "EntitlementActivated",
    "EntitlementExpired",
    "EntitlementRevoked",
}
"""Unlike catalog's own handler (see above), profiles' `handle_entitlement_event` (Task P-11) DOES
have a withdrawal path: `VerificationEligibilityRepository.upsert` records `activation_state`
verbatim (`ACTIVE`/`EXPIRED`/`REVOKED`), so routing all three event types keeps the local
eligibility projection (I-12) accurate rather than leaving a stale `ACTIVE` row after the
entitlement actually expired/was revoked."""

_PROFILES_RELEVANT_ENTITLEMENT_TYPES = {"VERIFICATION_ELIGIBILITY"}

_PROFILES_SUBSCRIPTION_RELEVANT_ENTITLEMENT_TYPES = {"ACTIVE_SUBSCRIPTION"}
"""Monetization: reuses `_PROFILES_RELEVANT_ENTITLEMENT_EVENT_TYPES` above (already all three
event types) for a SECOND, independent route into `handle_subscription_entitlement_event` --
distinct from the `VERIFICATION_ELIGIBILITY` route just below, which `handle_profiles_
entitlement_event`'s own internal `entitlementType` check would otherwise silently reject."""

_BILLING_NOTIFICATION_EVENT_TYPES = {
    "OrderPlaced",
    "InvoiceIssued",
    "PaymentConfirmed",
    "EntitlementExpired",
    "EntitlementRevoked",
}
"""Task P-13's own EventKey subset from billing's outbox -- deliberately excludes
`EntitlementActivated` (the Domain Model Sec 6 event catalogue's own "Principal consumers"
column, mirrored verbatim in `contracts/events/billing.py`'s frozen docstrings, never lists
Notifications as a consumer of it)."""

_ADS_RELEVANT_ENTITLEMENT_EVENT_TYPES = {
    "EntitlementActivated",
    "EntitlementExpired",
    "EntitlementRevoked",
}
"""Task P-14's own route: ads' `handle_entitlement_event` DOES have a withdrawal path
(`EntitlementProjectionRepository.mark_state`, mirroring profiles' own I-12-style projection, not
catalog's stale-reapplication limitation), so -- like profiles -- all three event types are
routed, keeping the local `BANNER_SLOT_BOOKING` entitlement projection (I-15/I-21) accurate."""

_ADS_RELEVANT_ENTITLEMENT_TYPES = {"BANNER_SLOT_BOOKING"}


def make_billing_entitlement_fanout_handler(
    *,
    billing_session_factory: async_sessionmaker[AsyncSession],
    profiles_session_factory: async_sessionmaker[AsyncSession],
    ads_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[EventEnvelope], Awaitable[None]]:
    """Builds an `EventHandler`-shaped closure (`backbone.outbox.dispatcher.EventHandler =
    Callable[[EventEnvelope], Awaitable[None]]`, no session parameter) draining BILLING's own
    outbox and routing the `ACTIVE_SUBSCRIPTION` slice into catalog's `handle_entitlement_event`
    and the `VERIFICATION_ELIGIBILITY` slice into profiles' own -- resolving the exact same
    `EventHandler`-has-no-session gap `search.infrastructure.event_projection.
    make_search_event_handler`'s own docstring documents and resolves for search's side: opens
    and commits its OWN fresh session (against the RELEVANT module's own schema) per event,
    independent of `OutboxDispatcher.drain_once`'s own outer session. Lives here, not inside
    `catalog/`/`billing/`/`profiles/`, because wiring one module's outbox to another module's
    consumer is composition-root work by construction -- no two of those modules may import each
    other (`cross-module-billing`/`cross-module-catalog`/`cross-module-profiles`).

    ONE dispatcher, ONE handler, for BOTH consumers -- billing's `outbox_event` table can only be
    safely drained by a single `OutboxDispatcher` instance (`FOR UPDATE SKIP LOCKED` only protects
    against the SAME dispatcher's own concurrent workers, not two independent dispatcher
    instances racing to mark the same row `DISPATCHED`), the same reasoning `make_catalog_outbox_
    fanout_handler`'s own docstring documents for catalog's outbox (search+messaging).

    Task P-13 adds a THIRD route on this SAME handler for the SAME reason: notifications' real
    `OrderPlaced`/`InvoiceIssued`/`PaymentConfirmed`/`EntitlementExpired`/`EntitlementRevoked`
    consumer also drains billing's outbox -- a fourth independent `OutboxDispatcher` on this
    table would race this one exactly as the module docstring above describes.

    Task P-14 adds a FOURTH route, same reason: ads' `BANNER_SLOT_BOOKING` entitlement projection
    (I-15/I-21) also drains billing's outbox -- `billing` is fully forbidden by `cross-module-ads`
    (unlike `configuration`/`media`, which ads may import via their `interfaces/` packages
    directly), so this event-only channel is the ONLY way ads learns entitlement state at all.

    Task P-15 adds a FIFTH route, same reason: analytics' `PaymentConfirmed` audit-fact consumer
    (I-22 -- an operator's payment confirmation is an administrative action) also drains billing's
    outbox; `billing` is forbidden by `cross-module-analytics` too (analytics imports
    `shared_kernel` only), so this is the only channel analytics ever learns of a confirmed
    payment through.

    P-20 adds a SIXTH route, closing a confirmed integration defect: `LISTING_PROMOTION`
    `EntitlementActivated`/`EntitlementExpired`/`EntitlementRevoked` events were never routed
    anywhere at all (neither catalog's own `handle_entitlement_event`, which only ever handles
    `ACTIVE_SUBSCRIPTION`, nor any dispatcher for search's contract-only `handle_entitlement_
    activated`) -- so "the promotion is reflected in catalog AND in search ranking" (the critical
    journey) was silently non-functional. Fixed by routing into catalog's new `handle_listing_
    promotion_event`, per the frozen event contract's own `EntitlementActivated` docstring
    ("Principal consumers: Catalog (promotion/quota)...") -- catalog republishes `ListingEdited`,
    which search's ALREADY-WIRED catalog-outbox consumer (`make_catalog_outbox_fanout_handler`)
    already drains, closing the loop with no new dispatcher and no change to search's own code.

    Listing paywall Phase 3 adds a SEVENTH route, same reason: `LISTING_PUBLICATION`
    `EntitlementActivated` events route into catalog's new `handle_listing_publication_event`,
    which flips a held `DRAFT`+`awaiting_payment` listing live (`ListingUseCases.
    activate_after_payment`) -- unlike the promotion/subscription routes, only
    `EntitlementActivated` is routed (see `_CATALOG_PUBLICATION_RELEVANT_ENTITLEMENT_EVENT_TYPES`'s
    own docstring: this entitlement type has no withdrawal path)."""

    async def _handle(envelope: EventEnvelope) -> None:
        if envelope.event_type in _CATALOG_RELEVANT_ENTITLEMENT_EVENT_TYPES and (
            envelope.payload.get("entitlementType") in _CATALOG_RELEVANT_ENTITLEMENT_TYPES
        ):
            async with billing_session_factory() as session, session.begin():
                await handle_entitlement_event(session, envelope)
        if envelope.event_type in _CATALOG_PROMOTION_RELEVANT_ENTITLEMENT_EVENT_TYPES and (
            envelope.payload.get("entitlementType") in _CATALOG_PROMOTION_RELEVANT_ENTITLEMENT_TYPES
        ):
            async with billing_session_factory() as session, session.begin():
                await handle_listing_promotion_event(
                    session, envelope, _build_listing_use_cases(session)
                )
        if envelope.event_type in _CATALOG_PUBLICATION_RELEVANT_ENTITLEMENT_EVENT_TYPES and (
            envelope.payload.get("entitlementType")
            in _CATALOG_PUBLICATION_RELEVANT_ENTITLEMENT_TYPES
        ):
            async with billing_session_factory() as session, session.begin():
                await handle_listing_publication_event(
                    session, envelope, _build_listing_use_cases(session)
                )
        if (
            envelope.event_type in _CATALOG_SUBSCRIPTION_VISIBILITY_RELEVANT_ENTITLEMENT_EVENT_TYPES
            and (envelope.payload.get("entitlementType") in _CATALOG_RELEVANT_ENTITLEMENT_TYPES)
        ):
            async with billing_session_factory() as session, session.begin():
                await handle_subscription_visibility_event(
                    session, envelope, _build_listing_use_cases(session)
                )
        if envelope.event_type in _PROFILES_RELEVANT_ENTITLEMENT_EVENT_TYPES and (
            envelope.payload.get("entitlementType") in _PROFILES_RELEVANT_ENTITLEMENT_TYPES
        ):
            async with profiles_session_factory() as session, session.begin():
                profiles = SqlalchemyBusinessProfileRepository(session)
                use_cases = VerificationUseCases(
                    profiles=profiles,
                    cases=SqlalchemyVerificationCaseRepository(session),
                    eligibility=SqlalchemyVerificationEligibilityRepository(session),
                    media=_profiles_media_adapter(),
                    outbox=OutboxWriter(session, ProfilesOutboxEventRow),
                )
                await handle_profiles_entitlement_event(session, envelope, use_cases)
        if envelope.event_type in _PROFILES_RELEVANT_ENTITLEMENT_EVENT_TYPES and (
            envelope.payload.get("entitlementType")
            in _PROFILES_SUBSCRIPTION_RELEVANT_ENTITLEMENT_TYPES
        ):
            async with profiles_session_factory() as session, session.begin():
                profile_use_cases = ProfileUseCases(
                    profiles=SqlalchemyBusinessProfileRepository(session),
                    media=_profiles_media_adapter(),
                    outbox=OutboxWriter(session, ProfilesOutboxEventRow),
                    subscriptions=SqlalchemySubscriptionEligibilityRepository(session),
                )
                await handle_subscription_entitlement_event(session, envelope, profile_use_cases)
        if envelope.event_type in _BILLING_NOTIFICATION_EVENT_TYPES:
            async with _notifications_session_factory()() as session, session.begin():
                dispatches = await handle_billing_event(
                    session,
                    envelope,
                    use_cases=_build_notification_dispatch_use_cases(session),
                    recipients=_RecipientDirectoryBridge(),
                    order_projection=SqlalchemyOrderRecipientProjectionRepository(session),
                )
            await _dispatch_queued_notifications(dispatches)
        if envelope.event_type in _ADS_RELEVANT_ENTITLEMENT_EVENT_TYPES and (
            envelope.payload.get("entitlementType") in _ADS_RELEVANT_ENTITLEMENT_TYPES
        ):
            async with ads_session_factory() as session, session.begin():
                await handle_ads_entitlement_event(session, envelope)
        if envelope.event_type == "PaymentConfirmed":
            async with _analytics_session_factory()() as session, session.begin():
                await handle_billing_event_for_analytics(
                    session, envelope, audit_use_cases=_build_audit_use_cases(session)
                )

    return _handle


def provide_catalog_entitlement_projection_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/catalog_worker.py`, alongside `provide_catalog_expiry_worker`). Fills the
    gap `catalog/README.md`'s own "Known gaps" #1 flagged ("media event projection not wired into
    composition_root.py... a future task adding a second independent consumer... would need a
    different mechanism") -- this IS that second independent consumer (billing's outbox, not
    media's), so it gets its own `OutboxDispatcher` instance rather than reusing media's
    unwired one. Despite the name (kept stable for `catalog_worker.py`'s own import), the handler
    it builds now also feeds profiles' entitlement projection (Task P-11) -- see
    `make_billing_entitlement_fanout_handler`'s own docstring for why both consumers share this
    ONE dispatcher rather than each getting an independent one."""
    return OutboxDispatcher(
        _billing_session_factory(),
        BillingOutboxEventRow,
        make_billing_entitlement_fanout_handler(
            billing_session_factory=_billing_session_factory(),
            profiles_session_factory=_profiles_session_factory(),
            ads_session_factory=_ads_session_factory(),
        ),
    )


# == ads (Task P-14) ===============================================================================


@lru_cache(maxsize=1)
def _ads_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _ads_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_ads_session_factory()) as session:
        yield session


@lru_cache(maxsize=1)
def _ads_configuration_adapter() -> ConfigurationPlacementSlotAdapter:
    """Reuses `_ConfigurationPortBridge` (identity's own section, above) unmodified -- entity-type-
    agnostic by design, same reuse pattern as `_billing_product_definition_adapter`/
    `_search_configuration_adapter`. ads reads `placement-slot` heads/versions."""
    return ConfigurationPlacementSlotAdapter(_ConfigurationPortBridge())


@lru_cache(maxsize=1)
def _ads_media_adapter() -> MediaCreativeStatusAdapter:
    """Reuses `_CatalogMediaReaderBridge` (catalog's own section, above) unmodified -- it already
    returns the exact generic `media.interfaces.dto.MediaAsset`-shaped object
    `ads.infrastructure.media_adapter._MediaReader` needs (`.scan_status`), the same structural-
    typing reuse `_ads_configuration_adapter` applies to `_ConfigurationPortBridge`."""
    return MediaCreativeStatusAdapter(_CatalogMediaReaderBridge())


async def provide_campaign_use_cases() -> AsyncIterator[CampaignUseCases]:
    async for session in _ads_session():
        yield CampaignUseCases(
            campaigns=SqlalchemyBannerCampaignRepository(session),
            slots=_ads_configuration_adapter(),
            creatives=_ads_media_adapter(),
            entitlements=SqlalchemyEntitlementProjectionRepository(session),
            outbox=OutboxWriter(session, AdsOutboxEventRow),
        )


async def provide_serving_use_cases() -> AsyncIterator[BannerServingUseCases]:
    async for session in _ads_session():
        yield BannerServingUseCases(
            campaigns=SqlalchemyBannerCampaignRepository(session),
            entitlements=SqlalchemyEntitlementProjectionRepository(session),
            outbox=OutboxWriter(session, AdsOutboxEventRow),
        )


async def provide_ads_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> AdsActingOperator:
    """Overrides `ads.interfaces.di.get_acting_operator` -- backs all seven `/admin/campaigns*`
    operations. Runs the REAL Security Sec 4.2 Gate-3 check (`identity.domain.
    AuthorizationService.authorize`) against `ads:campaign:manage` (`configuration.domain.
    whitelist.PERMISSION_KEYS`'s own P-14 extension), the same pattern
    `provide_billing_acting_operator`/`provide_moderation_acting_moderator` already establish."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "ads:campaign:manage")
        return AdsActingOperator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def provide_ads_campaign_schedule_sweep_worker() -> CampaignScheduleSweepWorker:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/ads_worker.py`), mirroring `provide_billing_entitlement_expiry_worker`."""
    return CampaignScheduleSweepWorker(
        session_factory=_ads_session_factory(), outbox_model=AdsOutboxEventRow
    )


# == search (Task P-08) ===========================================================================


def _opensearch_client() -> OpenSearch:
    """P-21 fix (confirmed via the real benchmark harness): the default `opensearch-py` transport
    connection pool is far too small for this app's actual concurrency -- the benchmark's own
    logs showed `urllib3` warning "Connection pool is full, discarding connection... Connection
    pool size: 1" under concurrent search load, meaning requests were serialising on a SINGLE
    HTTP connection to OpenSearch rather than genuinely running in parallel, inflating p95/p99
    well beyond OpenSearch's own actual query time. `pool_maxsize` only changes how many
    concurrent connections THIS client is allowed to hold open -- it changes no query, no index
    mapping, no result, nothing behavioural; purely a client-side capacity fix. This client is a
    single `@lru_cache`d instance shared by the whole process (every request), so it must be
    sized for real concurrent load, not the connection-pool default meant for light, sequential
    scripting use."""
    return OpenSearch(
        hosts=[
            {
                "host": required_env("OPENSEARCH_HOST"),
                "port": int(required_env("OPENSEARCH_PORT")),
            }
        ],
        pool_maxsize=100,
    )


_SEARCH_INDEX_NAME = "listing_search"


@lru_cache(maxsize=1)
def _search_index_adapter() -> OpenSearchIndexAdapter:
    return OpenSearchIndexAdapter(_opensearch_client(), index_name=_SEARCH_INDEX_NAME)


@lru_cache(maxsize=1)
def _search_configuration_adapter() -> ConfigurationSearchConfigurationAdapter:
    """Reuses `_ConfigurationPortBridge` (identity's own section, above) unmodified -- it already
    implements the exact narrow `list_config_heads`/`get_config_version` shape `search.
    infrastructure.configuration_adapter._ConfigurationReader` consumes, the same way `catalog`'s
    `_catalog_category_form_adapter` reuses it via `_CategoryReaderBridge` instead. search reads
    `search-configuration` heads/versions, not `category`/`role-definition`/`platform-settings`
    ones -- the bridge itself is entity-type-agnostic (it forwards whatever `entity_type` string
    its caller passes), so no new bridge class is needed."""
    return ConfigurationSearchConfigurationAdapter(_ConfigurationPortBridge())


async def provide_search_use_cases() -> AsyncIterator[SearchUseCases]:
    async for session in _search_session():
        yield SearchUseCases(
            index=_search_index_adapter(),
            fallback=SqlalchemyFallbackIndexRepository(session),
            configuration=_search_configuration_adapter(),
        )


_CATALOG_LISTING_EVENT_TYPES_FOR_MESSAGING = {"ListingCreated"}
"""I-01: `owner_user_id` is fixed for life, so messaging's own `listing_owner_projection` only
ever needs to observe a listing's FIRST event -- no later lifecycle event changes the answer."""

_CATALOG_NOTIFICATION_EVENT_TYPES = {
    "ListingPublished",
    "ListingSuspended",
    "ListingArchived",
    "ListingDeleted",
    "ListingExpired",
    "ListingRenewed",
}
"""Task P-13's own EventKey subset from catalog's outbox (mirrored verbatim from
`contracts/events/catalog.py`'s frozen "Principal consumers" docstrings) -- deliberately excludes
`ListingCreated`/`ListingDraftSaved`/`ListingEdited`/`ListingFlagged`/`FavoriteAdded`/
`FavoriteRemoved`, none of which name Notifications as a consumer."""

_CATALOG_METRIC_EVENT_TYPES = {
    "FavoriteAdded",
    "ListingViewed",
    "ContactButtonClicked",
    "PremiumListingStat",
}
"""Task P-15's own closed-vocabulary subset from catalog's outbox -- mirrors
`analytics.infrastructure.event_projection._CATALOG_METRIC_KEYS`'s own key set.
`ListingViewed`/`ContactButtonClicked`/`PremiumListingStat` are frozen (ADR-0005) but have no
real producer in catalog's own code yet -- this route exists so the moment a future task adds the
`outbox.append(...)` call, analytics is already listening; until then it only ever sees
`FavoriteAdded` from this route in practice."""


def make_catalog_outbox_fanout_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """The ONE handler attached to catalog's own outbox dispatcher (Task P-10). Catalog's
    `outbox_event` table already had exactly one consumer (`search.infrastructure.worker.
    SearchIndexingWorker`'s own catalog dispatcher, Task P-08) -- `OutboxDispatcher.drain_once`
    claims rows by mutating a SHARED `dispatch_status` column (`FOR UPDATE SKIP LOCKED` only
    protects against double-processing the SAME row by concurrent workers of the SAME dispatcher,
    not against two DIFFERENT dispatcher instances each marking rows `DISPATCHED` after their own
    single pass) -- a second, independent `OutboxDispatcher` on the same table would race
    search's for every row, including `ListingCreated`, which search's own handler silently
    ignores but still marks `DISPATCHED` when it wins that race. `catalog/README.md`'s own "Known
    gaps" #1 already named this exact situation ("a future task adding a second independent
    consumer ... would need a different mechanism").

    The fix: ONE dispatcher, ONE handler, that does both jobs -- search's own `make_search_event_
    handler` (unmodified, imported from `search.infrastructure`) runs first, then messaging's own
    `handle_listing_created` (only for the one event type it cares about). Neither `search/` nor
    `catalog/` is edited to make this work -- only this composition-root wiring, and which worker
    entrypoint (`search_worker.py`) runs it.

    Task P-12 adds a third route on this SAME handler for the SAME reason: moderation's real
    `ListingFlagged` consumer (`moderation.infrastructure.event_projection.handle_listing_flagged`,
    FR-MOD-002) also drains catalog's outbox -- a fourth independent `OutboxDispatcher` on this
    table would race this one exactly as the module docstring above describes, so it is folded in
    here rather than given its own.

    Task P-13 adds a FOURTH route for the SAME reason: notifications' real `ListingPublished`/
    `Suspended`/`Archived`/`Deleted`/`Expired`/`Renewed` consumer also drains catalog's outbox.

    Task P-15 adds a FIFTH route, same reason: analytics' `MetricEvent` consumer
    (`FavoriteAdded`/`ListingViewed`/`ContactButtonClicked`/`PremiumListingStat`) also drains
    catalog's outbox."""
    search_handler = make_search_event_handler(
        session_factory=_search_session_factory(), index=_search_index_adapter()
    )

    async def _handle(envelope: EventEnvelope) -> None:
        await search_handler(envelope)
        if envelope.event_type in _CATALOG_LISTING_EVENT_TYPES_FOR_MESSAGING:
            async with _messaging_session_factory()() as session, session.begin():
                await handle_listing_created(session, envelope)
        if envelope.event_type == "ListingFlagged":
            async with _moderation_session_factory()() as session, session.begin():
                use_cases = ModerationUseCases(
                    cases=SqlalchemyModerationCaseRepository(session),
                    action_service=_build_moderation_action_service(),
                    outbox=OutboxWriter(session, ModerationOutboxEventRow),
                )
                await handle_listing_flagged(session, envelope, use_cases)
        if envelope.event_type in _CATALOG_NOTIFICATION_EVENT_TYPES:
            async with _notifications_session_factory()() as session, session.begin():
                dispatches = await handle_catalog_event_for_notifications(
                    session,
                    envelope,
                    use_cases=_build_notification_dispatch_use_cases(session),
                    recipients=_RecipientDirectoryBridge(),
                )
            await _dispatch_queued_notifications(dispatches)
        if envelope.event_type in _CATALOG_METRIC_EVENT_TYPES:
            async with _analytics_session_factory()() as session, session.begin():
                await handle_catalog_event_for_analytics(
                    session, envelope, metric_use_cases=_build_metric_use_cases(session)
                )

    return _handle


def provide_catalog_outbox_fanout_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/search_worker.py`). This is now the ONLY dispatcher draining catalog's
    `outbox_event` table -- `search_worker.py` no longer constructs `search.infrastructure.
    worker.SearchIndexingWorker` at all (its own `catalog_outbox_model` constructor parameter has
    no default, and passing one back in would recreate the exact two-dispatcher race this
    function exists to avoid) -- through `make_catalog_outbox_fanout_handler`'s combined
    routing."""
    return OutboxDispatcher(
        _catalog_session_factory(),
        CatalogOutboxEventRow,
        make_catalog_outbox_fanout_handler(),
    )


def make_identity_account_status_projection_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """Builds the `EventHandler`-shaped closure draining IDENTITY's own outbox and routing its
    real `AccountSuspended` event into catalog's already-built `handle_identity_event`
    (`catalog.infrastructure.event_projection`, DB Architecture Sec 14.4's own worked example:
    "account suspension -> listings hidden by catalog's own transition") -- left unwired through
    Task P-11 because nothing yet called `AdminIdentityUseCases.change_user_status` through a path
    any real caller exercised end-to-end (identity/README.md's own admin capabilities are built
    but not mounted on any router, per that module's own docstring). Task P-12's `SUSPEND_ACCOUNT`
    verb (`_ModerationAccountSuspensionBridge`, below) is the first real caller, which is what
    makes wiring this dispatcher meaningful now. The first (and, as of this task, only) consumer
    of identity's `outbox_event` table, so it gets its own dedicated `OutboxDispatcher` rather than
    needing the "one dispatcher, one handler, multiple routes" merge `make_catalog_outbox_fanout_
    handler`'s own docstring documents for catalog's already-multi-consumer outbox.

    Task P-13 adds a second route on this SAME handler for the SAME reason: notifications' real
    `UserRegistered`/`AccountSuspended`/`AccountClosed` consumer also drains identity's outbox --
    a second independent `OutboxDispatcher` on this table would race this one.

    Task P-15 adds a third route, same reason: analytics' `AccountSuspended`/`AccountClosed`
    audit-fact consumer (I-22) also drains identity's outbox. `UserRegistered` is deliberately
    NOT routed to analytics -- it is not an administrative action under I-22's own scope (see
    `analytics/README.md` "Known gaps")."""

    async def _handle(envelope: EventEnvelope) -> None:
        async with _catalog_session_factory()() as session, session.begin():
            use_cases = _build_listing_use_cases(session)
            await handle_identity_event(session, envelope, use_cases)
        async with _notifications_session_factory()() as session, session.begin():
            dispatches = await handle_identity_event_for_notifications(
                session,
                envelope,
                use_cases=_build_notification_dispatch_use_cases(session),
                recipients=_RecipientDirectoryBridge(),
            )
        await _dispatch_queued_notifications(dispatches)
        async with _analytics_session_factory()() as session, session.begin():
            await handle_identity_event_for_analytics(
                session, envelope, audit_use_cases=_build_audit_use_cases(session)
            )

    return _handle


def provide_identity_account_status_projection_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/catalog_worker.py`, extended in Task P-12). catalog is the CONSUMER here,
    so its own worker process runs the dispatcher -- the same precedent `provide_catalog_
    entitlement_projection_dispatcher` already establishes for billing's outbox, above."""
    return OutboxDispatcher(
        _identity_session_factory(),
        IdentityOutboxEventRow,
        make_identity_account_status_projection_handler(),
    )


# == messaging (Task P-10) ========================================================================


@lru_cache(maxsize=1)
def _messaging_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _messaging_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_messaging_session_factory()) as session:
        yield session


@lru_cache(maxsize=1)
def _messaging_redis_client() -> Redis:
    return Redis.from_url(redis_url())


@lru_cache(maxsize=1)
def _messaging_realtime_publisher() -> RedisRealtimePublisherAdapter:
    return RedisRealtimePublisherAdapter(_messaging_redis_client())


@lru_cache(maxsize=1)
def _messaging_message_subscriber() -> RedisMessageSubscriber:
    return RedisMessageSubscriber(_messaging_redis_client())


async def provide_conversation_use_cases() -> AsyncIterator[ConversationUseCases]:
    """`contact_policy` needs its own identity-schema session alongside messaging's own -- the
    SAME "one use case, two modules' sessions open together" shape `provide_payment_use_cases`
    (billing) never needed (billing chose not to import identity at all) but `provide_billing_
    acting_operator` already established for a single call; here it spans the whole use-case
    instance's lifetime since `reveal_phone` may be called at any point during the request."""
    async for messaging_session in _messaging_session():
        async for identity_session in _identity_session():
            yield ConversationUseCases(
                conversations=SqlalchemyConversationRepository(messaging_session),
                blocks=SqlalchemyBlockRepository(messaging_session),
                listing_owners=SqlalchemyListingOwnerProjectionReader(messaging_session),
                publisher=_messaging_realtime_publisher(),
                contact_policy=ContactPolicyPortAdapter(
                    SqlalchemyUserAccountRepository(identity_session)
                ),
                outbox=OutboxWriter(messaging_session, MessagingOutboxEventRow),
            )


async def provide_block_use_cases() -> AsyncIterator[BlockUseCases]:
    async for session in _messaging_session():
        yield BlockUseCases(
            blocks=SqlalchemyBlockRepository(session),
            outbox=OutboxWriter(session, MessagingOutboxEventRow),
        )


async def provide_report_use_cases() -> AsyncIterator[ReportUseCases]:
    async for session in _messaging_session():
        yield ReportUseCases(outbox=OutboxWriter(session, MessagingOutboxEventRow))


async def provide_messaging_acting_user(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> MessagingActingUser:
    """Overrides `messaging.interfaces.di.get_acting_user` -- shared verbatim by BOTH runtimes
    (`main.py`'s HTTP tier and `realtime_main.py`'s realtime gateway, DEC-11): FastAPI resolves
    `Cookie`/`Header` params identically from an HTTP request or a WebSocket handshake, so the
    exact same function authenticates both. Messaging carries no acting-profile context (purely
    per-user, unlike billing/catalog) -- simpler than `provide_billing_acting_user`."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return MessagingActingUser(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def provide_message_subscriber() -> RedisMessageSubscriber:
    """Overridden only by `realtime_main.py` -- the stateless HTTP tier's own `main.py` never
    overrides `get_message_subscriber` (nothing in `messaging_router` depends on it)."""
    return _messaging_message_subscriber()


# == profiles (Task P-11) =========================================================================


@lru_cache(maxsize=1)
def _profiles_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _profiles_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_profiles_session_factory()) as session:
        yield session


class _ProfilesMediaReaderBridge:
    """Adapts `media.application.MediaIntakeUseCases.get_media` to the narrow
    `profiles.infrastructure.media_adapter._MediaReader` shape, mirroring `_CatalogMediaReaderBridge`
    (catalog, above) exactly."""

    async def get_media(self, media_id: UUID) -> object:
        async for session in _media_session():
            use_cases = MediaIntakeUseCases(
                assets=SqlalchemyMediaAssetRepository(session),
                storage=_minio_adapter(),
                outbox=OutboxWriter(session, MediaOutboxEventRow),
                presign_expiry_seconds=int(required_env("MEDIA_PRESIGN_EXPIRY_SECONDS")),
            )
            asset = await use_cases.get_media(MediaAssetId(value=media_id))
            return _asset_to_dto(asset)
        raise AssertionError("unreachable: _media_session always yields exactly once")


@lru_cache(maxsize=1)
def _profiles_media_adapter() -> ProfilesMediaAssetReaderAdapter:
    return ProfilesMediaAssetReaderAdapter(_ProfilesMediaReaderBridge())


async def provide_profile_use_cases() -> AsyncIterator[ProfileUseCases]:
    async for session in _profiles_session():
        yield ProfileUseCases(
            profiles=SqlalchemyBusinessProfileRepository(session),
            media=_profiles_media_adapter(),
            outbox=OutboxWriter(session, ProfilesOutboxEventRow),
            subscriptions=SqlalchemySubscriptionEligibilityRepository(session),
        )


async def provide_verification_use_cases() -> AsyncIterator[VerificationUseCases]:
    async for session in _profiles_session():
        yield VerificationUseCases(
            profiles=SqlalchemyBusinessProfileRepository(session),
            cases=SqlalchemyVerificationCaseRepository(session),
            eligibility=SqlalchemyVerificationEligibilityRepository(session),
            media=_profiles_media_adapter(),
            outbox=OutboxWriter(session, ProfilesOutboxEventRow),
        )


async def provide_profiles_acting_user(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> ProfilesActingUser:
    """Overrides `profiles.interfaces.di.get_acting_user`. Reuses identity's own session/account
    resolution machinery exactly like `provide_catalog_acting_user` does -- profiles' own source
    never imports identity beyond its `interfaces/` package (`cross-module-profiles`)."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, session_obj, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return ProfilesActingUser(
            account_id=account.id, acting_profile_id=session_obj.acting_profile_id
        )
    raise AssertionError("unreachable: _identity_session always yields exactly once")


async def provide_profiles_acting_reviewer(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> ProfilesActingReviewer:
    """Overrides `profiles.interfaces.di.get_acting_reviewer` -- backs `listVerificationQueue`/
    `decideVerification`, the two reviewer-facing operations profiles owns. Runs the REAL
    Security Sec 4.2 Gate-3 check (`identity.domain.AuthorizationService.authorize`) against
    `profiles:verification:review` (`configuration.domain.whitelist.PERMISSION_KEYS`'s own P-11
    extension), mirroring `provide_billing_acting_operator`'s own "wired end-to-end" precedent
    exactly."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "profiles:verification:review")
        return ProfilesActingReviewer(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


async def provide_profiles_acting_profile_manager(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> ProfilesActingProfileManager:
    """Overrides `profiles.interfaces.di.get_acting_profile_manager` -- backs
    `adminListBusinessProfiles`/`adminArchiveBusinessProfile`, the owner-admin panel's direct
    company-management surface. Runs the REAL Security Sec 4.2 Gate-3 check against
    `profiles:profile:manage` (`configuration.domain.whitelist.PERMISSION_KEYS`'s 2026-08-13
    extension), mirroring `provide_profiles_acting_reviewer`'s own "wired end-to-end" precedent
    exactly."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "profiles:profile:manage")
        return ProfilesActingProfileManager(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def provide_profiles_badge_expiry_worker() -> BadgeExpiryWorker:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/profiles_worker.py`), same discipline as `provide_catalog_expiry_worker`."""
    return BadgeExpiryWorker(
        session_factory=_profiles_session_factory(),
        outbox_model=ProfilesOutboxEventRow,
        media=_profiles_media_adapter(),
    )


def provide_profiles_trial_expiry_worker() -> TrialExpiryWorker:
    """ADR-0010. Not a FastAPI dependency override -- called directly by the worker process
    entrypoint (`apps/backend/src/profiles_worker.py`), same discipline as
    `provide_profiles_badge_expiry_worker`."""
    return TrialExpiryWorker(
        session_factory=_profiles_session_factory(),
        outbox_model=ProfilesOutboxEventRow,
        media=_profiles_media_adapter(),
    )


def make_media_outbox_fanout_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """The ONE handler attached to media's own outbox dispatcher.

    Media's `outbox_event` table had no dispatcher draining it at all, for any consumer -- so
    `MediaAssetReady`/`MediaAssetRejected` accumulated `PENDING` forever and BOTH already-built
    consumers sat unwired: catalog's `handle_media_event` (image `asset_status_snapshot`, X-06)
    and profiles' (portfolio/verification-document cleanliness). The visible symptom was that an
    image attached to a listing stayed `PENDING` for the rest of its life: the interface filters
    to CLEAN-only, so a correctly scanned, perfectly good photo never appeared anywhere, and
    `SearchHit.thumbnailUrl` -- which only carries a CLEAN image -- stayed null on every card.

    All THREE consumers were unwired for the same reason, each deferring to the others:
    catalog's, profiles', and ads' creative scan-status projection (I-20), whose own module
    docstring names the missing fan-out mechanism explicitly as "a bigger structural change than
    this task's own scope". This is that change, so all three are routed rather than leaving a
    third racing dispatcher to be added later.

    Both `catalog/README.md`'s "Known gaps" #1 and `make_profiles_media_status_projection_
    handler`'s own docstring named this as deferred, and named the two questions to settle:
    which worker process owns the dispatcher, and whether the two consumers share one. They are
    settled here the way `make_catalog_outbox_fanout_handler` already settled the identical
    situation on catalog's table: ONE dispatcher, ONE handler, both routes. Two independent
    `OutboxDispatcher`s on one table race for every row -- `FOR UPDATE SKIP LOCKED` stops two
    workers of the SAME dispatcher double-processing a row, not two different dispatchers each
    marking rows `DISPATCHED` after their own pass -- so the loser silently never sees events
    the winner already consumed.

    Ownership goes to `media_worker.py`, the producing module's own worker, rather than to either
    consumer's. Catalog's and profiles' claims are symmetric; picking either would make one
    consumer's worker a hidden dependency of the other's projection, so that a deployment running
    only `profiles_worker` would silently stop updating catalog's image statuses.

    Each route opens its own session and commits independently. A failure in one is logged and
    re-raised by the dispatcher, which retries the whole envelope -- both handlers are guarded by
    `idempotent_consume` under their own handler names, so the already-applied side is a no-op on
    redelivery rather than a double-apply.
    """

    async def _handle(envelope: EventEnvelope) -> None:
        async with _catalog_session_factory()() as session, session.begin():
            await handle_catalog_media_event(session, envelope)
        async with _profiles_session_factory()() as session, session.begin():
            profiles_use_cases = ProfileUseCases(
                profiles=SqlalchemyBusinessProfileRepository(session),
                media=_profiles_media_adapter(),
                outbox=OutboxWriter(session, ProfilesOutboxEventRow),
            )
            verification_use_cases = VerificationUseCases(
                profiles=SqlalchemyBusinessProfileRepository(session),
                cases=SqlalchemyVerificationCaseRepository(session),
                eligibility=SqlalchemyVerificationEligibilityRepository(session),
                media=_profiles_media_adapter(),
                outbox=OutboxWriter(session, ProfilesOutboxEventRow),
            )
            await handle_profiles_media_event(
                session,
                envelope,
                profiles=profiles_use_cases,
                verifications=verification_use_cases,
            )
        async with _ads_session_factory()() as session, session.begin():
            await handle_ads_media_event(session, envelope)

    return _handle


def provide_media_outbox_fanout_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by `apps/backend/src/media_worker.py`.
    See `make_media_outbox_fanout_handler` for why media's own worker owns this rather than either
    consumer's."""
    return OutboxDispatcher(
        _media_session_factory(),
        MediaOutboxEventRow,
        make_media_outbox_fanout_handler(),
    )


# == moderation (Task P-12) =======================================================================


@lru_cache(maxsize=1)
def _moderation_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _moderation_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_moderation_session_factory()) as session:
        yield session


class _ModerationListingCommandBridge:
    """Implements moderation's own narrow `ListingModerationCommandPort` (`moderation.application.
    ports`) by delegating to catalog's `CatalogListingModerationAdapter` over a fresh, short-lived
    catalog session per call -- mirrors `_CatalogMediaReaderBridge`'s own per-call-session pattern
    (catalog's own section, above), pushed one level further out because moderation cannot import
    catalog at all (`moderation/application/ports.py`'s own docstring explains why)."""

    async def hide_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        async with _catalog_session_factory()() as session, session.begin():
            adapter = CatalogListingModerationAdapter(_build_listing_use_cases(session))
            await adapter.hide_listing(
                listing_id, moderator_user_id=moderator_user_id, reason=reason
            )

    async def reject_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        async with _catalog_session_factory()() as session, session.begin():
            adapter = CatalogListingModerationAdapter(_build_listing_use_cases(session))
            await adapter.reject_listing(
                listing_id, moderator_user_id=moderator_user_id, reason=reason
            )

    async def suspend_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        async with _catalog_session_factory()() as session, session.begin():
            adapter = CatalogListingModerationAdapter(_build_listing_use_cases(session))
            await adapter.suspend_listing(
                listing_id, moderator_user_id=moderator_user_id, reason=reason
            )

    async def remove_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        async with _catalog_session_factory()() as session, session.begin():
            adapter = CatalogListingModerationAdapter(_build_listing_use_cases(session))
            await adapter.remove_listing(
                listing_id, moderator_user_id=moderator_user_id, reason=reason
            )

    async def unflag_listing(self, listing_id: UUID, *, reason: str | None) -> None:
        async with _catalog_session_factory()() as session, session.begin():
            adapter = CatalogListingModerationAdapter(_build_listing_use_cases(session))
            await adapter.unflag_listing(listing_id, reason=reason)


class _ModerationAccountSuspensionBridge:
    """Implements moderation's own narrow `AccountSuspensionCommandPort` by delegating to
    identity's `AdminIdentityUseCases.change_user_status` over a fresh, short-lived identity
    session per call (FR-MOD-004: "suspend or ban an account") -- the same underlying transition
    `provide_identity_account_status_projection_dispatcher`'s own docstring notes had no real
    caller before this task."""

    async def suspend_account(self, account_id: UUID, *, reason: str | None) -> None:
        async for session in _identity_session():
            use_cases = AdminIdentityUseCases(
                accounts=SqlalchemyUserAccountRepository(session),
                sessions=RedisSessionRepository(_identity_redis_client()),
                outbox=OutboxWriter(session, IdentityOutboxEventRow),
                role_reader=_role_definition_reader(),
            )
            await use_cases.change_user_status(
                target_account_id=UserId(value=account_id),
                action="SUSPEND",
                reason=reason,
                now=datetime.now(UTC),
            )
            return
        raise AssertionError("unreachable: _identity_session always yields exactly once")


class _ModerationProfileCommandBridge:
    """Implements moderation's own narrow `ProfileModerationCommandPort` by delegating to
    profiles' `ProfilesModerationAdapter` over a fresh, short-lived profiles session per call
    (ADR-0003's badge-revocation/profile-archival verbs)."""

    async def revoke_badge(self, profile_id: UUID) -> None:
        async with _profiles_session_factory()() as session, session.begin():
            use_cases = ProfileUseCases(
                profiles=SqlalchemyBusinessProfileRepository(session),
                media=_profiles_media_adapter(),
                outbox=OutboxWriter(session, ProfilesOutboxEventRow),
            )
            await ProfilesModerationAdapter(use_cases).revoke_badge(profile_id)

    async def archive_profile(self, profile_id: UUID) -> None:
        async with _profiles_session_factory()() as session, session.begin():
            use_cases = ProfileUseCases(
                profiles=SqlalchemyBusinessProfileRepository(session),
                media=_profiles_media_adapter(),
                outbox=OutboxWriter(session, ProfilesOutboxEventRow),
            )
            await ProfilesModerationAdapter(use_cases).archive_profile(profile_id)


def _build_moderation_action_service() -> ModerationActionService:
    return ModerationActionService(
        listings=_ModerationListingCommandBridge(),
        accounts=_ModerationAccountSuspensionBridge(),
        profiles=_ModerationProfileCommandBridge(),
    )


async def provide_moderation_use_cases() -> AsyncIterator[ModerationUseCases]:
    async for session in _moderation_session():
        yield ModerationUseCases(
            cases=SqlalchemyModerationCaseRepository(session),
            action_service=_build_moderation_action_service(),
            outbox=OutboxWriter(session, ModerationOutboxEventRow),
        )


async def provide_moderation_acting_moderator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> ActingModerator:
    """Overrides `moderation.interfaces.di.get_acting_moderator` -- backs all three operations
    this module owns (`listModerationQueue`/`getModerationCase`/`applyModerationAction`). Runs the
    REAL Security Sec 4.2 Gate-3 check (`identity.domain.AuthorizationService.authorize`) against
    `moderation:case:review` (`configuration.domain.whitelist.PERMISSION_KEYS`'s own P-12
    extension), mirroring `provide_profiles_acting_reviewer`'s own "wired end-to-end" precedent
    exactly."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "moderation:case:review")
        return ActingModerator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def make_messaging_report_projection_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """Builds the `EventHandler`-shaped closure draining MESSAGING's own outbox and routing its
    real `ContentReported` event (Task P-10, `messaging.application.report_use_cases.
    ReportUseCases.create_report`) into moderation's `handle_content_reported` (FR-MOD-001/
    FR-MSG-005). The first (and, as of this task, only) consumer of messaging's `outbox_event`
    table, so it gets its own dedicated `OutboxDispatcher` rather than needing the "one
    dispatcher, one handler, multiple routes" merge `make_catalog_outbox_fanout_handler`'s own
    docstring documents for catalog's already-multi-consumer outbox.

    Task P-13 adds a second route on this SAME handler for the SAME reason: notifications' real
    `ChatInitiated`/`MessageSent` consumer also drains messaging's outbox.

    Task P-15 adds a third route, same reason: analytics' `MetricEvent` consumer
    (`PhoneRevealed`/`ChatInitiated`) also drains messaging's outbox."""

    async def _handle(envelope: EventEnvelope) -> None:
        async with _moderation_session_factory()() as session, session.begin():
            use_cases = ModerationUseCases(
                cases=SqlalchemyModerationCaseRepository(session),
                action_service=_build_moderation_action_service(),
                outbox=OutboxWriter(session, ModerationOutboxEventRow),
            )
            await handle_content_reported(session, envelope, use_cases)
        async with _notifications_session_factory()() as session, session.begin():
            dispatches = await handle_messaging_event(
                session,
                envelope,
                use_cases=_build_notification_dispatch_use_cases(session),
                recipients=_RecipientDirectoryBridge(),
            )
        await _dispatch_queued_notifications(dispatches)
        if envelope.event_type in {"PhoneRevealed", "ChatInitiated"}:
            async with _analytics_session_factory()() as session, session.begin():
                await handle_messaging_event_for_analytics(
                    session, envelope, metric_use_cases=_build_metric_use_cases(session)
                )

    return _handle


def provide_moderation_report_projection_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/moderation_worker.py`, new in this task), same discipline as
    `provide_catalog_entitlement_projection_dispatcher`."""
    return OutboxDispatcher(
        _messaging_session_factory(),
        MessagingOutboxEventRow,
        make_messaging_report_projection_handler(),
    )


# == notifications (Task P-13) ====================================================================


@lru_cache(maxsize=1)
def _notifications_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _notifications_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_notifications_session_factory()) as session:
        yield session


def _account_to_recipient_snapshot(account: UserAccount) -> RecipientSnapshot:
    prefs = account.notification_preferences
    return RecipientSnapshot(
        user_id=account.id.value,
        email=account.email.value if account.email else None,
        phone=account.phone.value if account.phone else None,
        web_push_subscription=None,
        email_enabled=prefs.email,
        web_push_enabled=prefs.web_push,
        sms_enabled=prefs.sms,
    )


class _RecipientDirectoryBridge:
    """Implements notifications' own narrow `RecipientDirectoryPort` (`notifications.
    application.ports`) by reading identity's/profiles'/catalog's real repositories directly over
    a fresh, short-lived session per call -- the one place allowed to see every module's
    internals at once. Mirrors `moderation.py`'s own three command-port bridges above, just for
    READS instead of commands."""

    async def resolve_recipient(self, user_id: UUID) -> RecipientSnapshot | None:
        async with _identity_session_factory()() as session:
            account = await SqlalchemyUserAccountRepository(session).get_by_id(
                UserId(value=user_id)
            )
            return _account_to_recipient_snapshot(account) if account is not None else None

    async def resolve_recipient_for_profile(self, profile_id: UUID) -> RecipientSnapshot | None:
        async with _profiles_session_factory()() as session:
            profile = await SqlalchemyBusinessProfileRepository(session).get_by_id(
                BusinessProfileId(value=profile_id)
            )
        if profile is None:
            return None
        return await self.resolve_recipient(profile.owner_user_id.value)

    async def resolve_recipient_for_listing(self, listing_id: UUID) -> RecipientSnapshot | None:
        async with _catalog_session_factory()() as session:
            listing = await SqlalchemyListingRepository(session).get_by_id(
                ListingId(value=listing_id)
            )
        if listing is None:
            return None
        return await self.resolve_recipient(listing.owner_user_id.value)


@lru_cache(maxsize=1)
def _notifications_template_adapter() -> ConfigurationNotificationTemplateAdapter:
    return ConfigurationNotificationTemplateAdapter(_ConfigurationPortBridge())


@lru_cache(maxsize=1)
def _notifications_email_adapter() -> NotificationsSmtpEmailProviderAdapter:
    return NotificationsSmtpEmailProviderAdapter()


@lru_cache(maxsize=1)
def _notifications_sms_adapter() -> NotificationsEskizSmsProviderAdapter:
    return NotificationsEskizSmsProviderAdapter()


@lru_cache(maxsize=1)
def _notifications_web_push_adapter() -> WebPushProviderAdapter:
    return WebPushProviderAdapter()


def _build_notification_dispatch_use_cases(
    session: AsyncSession,
) -> NotificationDispatchUseCases:
    return NotificationDispatchUseCases(
        notifications=SqlalchemyNotificationRepository(session),
        templates=_notifications_template_adapter(),
        email=_notifications_email_adapter(),
        sms=_notifications_sms_adapter(),
        web_push=_notifications_web_push_adapter(),
    )


async def _dispatch_queued_notifications(dispatches: list[QueuedDispatch]) -> None:
    """Called AFTER the caller's own DB transaction (the `queue_for_event` write) has already
    committed (Playbook Sec 6: "a transaction is never held open across a provider port call") --
    each queued dispatch gets its own fresh session for the provider call plus its own short
    follow-up transaction persisting the outcome (`mark_sent`/`mark_failed`)."""
    for dispatch in dispatches:
        async with _notifications_session_factory()() as session, session.begin():
            use_cases = _build_notification_dispatch_use_cases(session)
            await use_cases.dispatch_queued(dispatch, now=datetime.now(UTC))


async def provide_notification_use_cases() -> AsyncIterator[NotificationUseCases]:
    async for session in _notifications_session():
        yield NotificationUseCases(notifications=SqlalchemyNotificationRepository(session))


async def provide_notifications_acting_user(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> NotificationsActingUser:
    """Overrides `notifications.interfaces.di.get_acting_user`. Reuses identity's own
    session/account resolution machinery exactly like `provide_acting_user` (media) does --
    notifications' own source never imports `identity` (`cross-module-notifications`)."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return NotificationsActingUser(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def make_profiles_notification_projection_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """The FIRST dispatcher draining PROFILES' own outbox (Task P-13).

    Task P-15 adds a second route, same reason: analytics' `BusinessVerified`/
    `VerificationRejected` audit-fact consumer (I-22) also drains profiles' outbox.

    P-20 adds a THIRD route, closing a confirmed integration defect: search's own
    `handle_verified_badge_applied`/`handle_verified_badge_cleared` (Task P-08) were fully built
    and unit-tested but never wired to any dispatcher (`profiles/README.md`'s own "Known gaps"),
    so "a profiles badge event (approved verification) -> search verified-badge flag" was
    silently non-functional. `make_search_event_handler` is already generic over its producing
    module by construction (its own docstring: "the composition root can attach [it] to any
    producing module's own OutboxDispatcher") -- reused verbatim here, the same closure instance
    catalog's own outbox handler already attaches for `ListingPublished`/etc.

    P-20 adds a FOURTH route, closing a second confirmed integration defect (found by the E2E
    critical-journey suite): identity's `UserAccount.owned_profile_ids` was never appended to
    after `profiles.createBusinessProfile` succeeded -- no consumer reacted to
    `BusinessProfileCreated` for this purpose, so a freshly created business profile could never
    legitimately become a session's acting profile (`switchActingProfile` always raised
    `ProfileNotOwnedError`), which transitively blocked `billing.createOrder`/`getOrderInvoice`
    (both require an acting profile). `identity.infrastructure.event_projection.
    handle_profiles_event` closes this the same way every other P-20 fix in this file does: a new
    route on the ALREADY-existing dispatcher, no new event, no contract change.

    ADR-0010 adds a FIFTH route: catalog's own `handle_trial_subscription_event`, reacting to
    `TrialSubscriptionStarted`/`TrialSubscriptionEnded` -- catalog is the CONSUMER (same reason
    `handle_subscription_visibility_event` is routed off of BILLING's own outbox above; this is
    the profiles-outbox sibling of that route), and catalog must never run its own competing
    dispatcher against profiles' `outbox_event` table (this module's own `OutboxDispatcher`
    docstring: "only one dispatcher can safely claim a given row").

    ADR-0012 adds a SIXTH route: catalog's own `handle_registration_approval_event`, reacting to
    `BusinessProfileApproved`/`BusinessProfileRejected` -- the B2B Directory registration-approval
    gate's own visibility mechanism, structurally identical to the trial/subscription routes
    above but scoped to its own suspend/restore reason strings so the three gates never
    cross-contaminate each other's suspensions (see `ListingUseCases.
    reactivate_all_by_owner_profile`'s own docstring)."""

    search_handler = make_search_event_handler(
        session_factory=_search_session_factory(), index=_search_index_adapter()
    )

    async def _handle(envelope: EventEnvelope) -> None:
        async with _notifications_session_factory()() as session, session.begin():
            dispatches = await handle_profiles_event(
                session,
                envelope,
                use_cases=_build_notification_dispatch_use_cases(session),
                recipients=_RecipientDirectoryBridge(),
            )
        await _dispatch_queued_notifications(dispatches)
        if envelope.event_type in {"BusinessVerified", "VerificationRejected"}:
            async with _analytics_session_factory()() as session, session.begin():
                await handle_profiles_event_for_analytics(
                    session, envelope, audit_use_cases=_build_audit_use_cases(session)
                )
        if envelope.event_type in {
            "BusinessVerified",
            "VerificationRejected",
            "VerifiedBadgeExpired",
        }:
            await search_handler(envelope)
        if envelope.event_type == "BusinessProfileCreated":
            async with _identity_session_factory()() as session, session.begin():
                await handle_profiles_event_for_identity(
                    session, envelope, use_cases=_build_account_use_cases(session)
                )
        if envelope.event_type in {
            "TrialSubscriptionStarted",
            "TrialSubscriptionEnded",
        }:
            async with _catalog_session_factory()() as session, session.begin():
                await handle_trial_subscription_event(
                    session, envelope, _build_listing_use_cases(session)
                )
        if envelope.event_type in {
            "BusinessProfileApproved",
            "BusinessProfileRejected",
        }:
            async with _catalog_session_factory()() as session, session.begin():
                await handle_registration_approval_event(
                    session, envelope, _build_listing_use_cases(session)
                )

    return _handle


def provide_profiles_notification_projection_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/notifications_worker.py`, new in this task). notifications is the
    CONSUMER here, so its own worker process runs the dispatcher -- the same precedent
    `provide_identity_account_status_projection_dispatcher` already establishes."""
    return OutboxDispatcher(
        _profiles_session_factory(),
        ProfilesOutboxEventRow,
        make_profiles_notification_projection_handler(),
    )


def make_moderation_notification_projection_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """The FIRST dispatcher draining MODERATION's own outbox (Task P-13).

    Task P-15 adds a second route, same reason: analytics' `ModerationActionTaken` audit-fact
    consumer (I-22) also drains moderation's outbox."""

    async def _handle(envelope: EventEnvelope) -> None:
        async with _notifications_session_factory()() as session, session.begin():
            dispatches = await handle_moderation_event(
                session,
                envelope,
                use_cases=_build_notification_dispatch_use_cases(session),
                recipients=_RecipientDirectoryBridge(),
            )
        await _dispatch_queued_notifications(dispatches)
        async with _analytics_session_factory()() as session, session.begin():
            await handle_moderation_event_for_analytics(
                session, envelope, audit_use_cases=_build_audit_use_cases(session)
            )

    return _handle


def provide_moderation_notification_projection_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/notifications_worker.py`, new in this task). notifications is the
    CONSUMER here, so its own worker process runs the dispatcher."""
    return OutboxDispatcher(
        _moderation_session_factory(),
        ModerationOutboxEventRow,
        make_moderation_notification_projection_handler(),
    )


# == analytics (Task P-15) =========================================================================


@lru_cache(maxsize=1)
def _analytics_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _analytics_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_analytics_session_factory()) as session:
        yield session


def _build_audit_use_cases(session: AsyncSession) -> AuditUseCases:
    return AuditUseCases(entries=SqlalchemyAuditEntryRepository(session))


def _build_metric_use_cases(session: AsyncSession) -> MetricUseCases:
    return MetricUseCases(
        metrics=SqlalchemyMetricEventRepository(session),
        listing_statistics=SqlalchemyListingStatisticsProjectionRepository(session),
    )


async def provide_audit_use_cases() -> AsyncIterator[AuditUseCases]:
    async for session in _analytics_session():
        yield _build_audit_use_cases(session)


async def provide_admin_report_use_cases() -> AsyncIterator[AnalyticsReportUseCases]:
    async for session in _analytics_session():
        yield AnalyticsReportUseCases(
            audit_entries=SqlalchemyAuditEntryRepository(session),
            metrics=SqlalchemyMetricEventRepository(session),
        )


async def provide_audit_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> AnalyticsActingOperator:
    """Overrides `analytics.interfaces.di.get_audit_acting_operator` -- backs `queryAuditLog`.
    Runs the REAL Security Sec 4.2 Gate-3 check (`identity.domain.AuthorizationService.authorize`)
    against `analytics:audit:read` (`configuration.domain.whitelist.PERMISSION_KEYS`'s own P-15
    extension), the same pattern `provide_ads_acting_operator` already establishes."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "analytics:audit:read")
        return AnalyticsActingOperator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


async def provide_reports_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> AnalyticsActingOperator:
    """Overrides `analytics.interfaces.di.get_reports_acting_operator` -- backs
    `getAdminReports`, gated by a DIFFERENT permission (`analytics:reports:read`) than
    `queryAuditLog`'s -- see `provide_audit_acting_operator`."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "analytics:reports:read")
        return AnalyticsActingOperator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


def provide_analytics_partition_precreate_worker() -> PartitionPrecreateWorker:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/analytics_worker.py`). The partition-precreate scheduled job (Physical DB
    Sec 2/Sec 16) -- keeps `analytics.audit_entry`/`analytics.metric_event` a few months ahead of
    need, mirroring `provide_ads_campaign_schedule_sweep_worker`'s own "not a dependency override"
    discipline."""
    return PartitionPrecreateWorker(session_factory=_analytics_session_factory())


def make_configuration_audit_projection_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """The FIRST dispatcher draining CONFIGURATION's own outbox (Task P-15) -- no prior task
    wired one (every conforming context reads configuration SYNCHRONOUSLY via cached snapshots,
    X-01; `ConfigurationChanged` itself had no async consumer until now). Routes every
    specialisation `configuration.domain.events.resolve_configuration_changed_event_type` can
    produce into analytics' audit-fact consumer (I-22: "every configuration publish yields an
    immutable AuditEntry")."""

    async def _handle(envelope: EventEnvelope) -> None:
        async with _analytics_session_factory()() as session, session.begin():
            await handle_configuration_event_for_analytics(
                session, envelope, audit_use_cases=_build_audit_use_cases(session)
            )

    return _handle


def provide_analytics_configuration_projection_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/analytics_worker.py`). analytics is the CONSUMER here, so its own worker
    process runs the dispatcher -- the same precedent `provide_identity_account_status_
    projection_dispatcher` already establishes."""
    return OutboxDispatcher(
        _configuration_session_factory(),
        OutboxEvent,
        make_configuration_audit_projection_handler(),
    )


def make_ads_metric_projection_handler() -> Callable[[EventEnvelope], Awaitable[None]]:
    """The FIRST dispatcher draining ADS' own outbox (Task P-15) -- `BannerCampaignScheduled`/
    `Started`/`Ended` have no consumer anywhere yet (out of this task's scope; only the two
    closed-vocabulary metric events are routed here)."""

    async def _handle(envelope: EventEnvelope) -> None:
        async with _analytics_session_factory()() as session, session.begin():
            await handle_ads_event_for_analytics(
                session, envelope, metric_use_cases=_build_metric_use_cases(session)
            )

    return _handle


def provide_analytics_ads_projection_dispatcher() -> OutboxDispatcher:
    """Not a FastAPI dependency override -- called directly by the worker process entrypoint
    (`apps/backend/src/analytics_worker.py`)."""
    return OutboxDispatcher(
        _ads_session_factory(),
        AdsOutboxEventRow,
        make_ads_metric_projection_handler(),
    )


# == admin (Task P-16) =============================================================================


@lru_cache(maxsize=1)
def _admin_session_factory() -> async_sessionmaker[AsyncSession]:
    return make_session_factory(make_engine())


async def _admin_session() -> AsyncIterator[AsyncSession]:
    async with session_scope(_admin_session_factory()) as session:
        yield session


async def provide_operator_session_use_cases() -> AsyncIterator[OperatorSessionUseCases]:
    async for session in _admin_session():
        yield OperatorSessionUseCases(sessions=SqlalchemyOperatorSessionRepository(session))


async def provide_admin_acting_operator(
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> AdminActingOperator:
    """Overrides `admin.interfaces.di.get_acting_operator` -- backs `getAdminDashboard`, gated by
    `admin:dashboard:read` (the ONE permission key admin owns -- every other composed operation
    below is gated by the OWNING module's own permission key, checked by re-running the SAME
    resolution the owning module's own acting-operator provider runs, never a second, laxer
    check)."""
    raw_token = _raw_session_token(ah_session, authorization)
    if raw_token is None:
        raise InvalidSessionTokenError()

    async for session in _identity_session():
        accounts = SqlalchemyUserAccountRepository(session)
        sessions_repo = RedisSessionRepository(_identity_redis_client())
        authz = ApplicationAuthorizationService(
            session_repo=sessions_repo,
            account_repo=accounts,
            role_reader=_role_definition_reader(),
        )
        token_hash = _session_token_generator().hash_token(raw_token)
        account, _session_obj, context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        AuthorizationService().authorize(context, "admin:dashboard:read")
        return AdminActingOperator(account_id=account.id)
    raise AssertionError("unreachable: _identity_session always yields exactly once")


class _ModerationQueueProbe:
    """Backs `AdminDashboardUseCases`' `pendingModeration` connectivity probe only -- calls
    moderation's own `ModerationUseCases.list_queue` for real, result unused (see
    `admin/application/dashboard_use_cases.py`'s module docstring). Deliberately NOT a full
    `ModerationPort`-shaped bridge: moderation's OWN router already serves `listModerationQueue`/
    `getModerationCase`/`applyModerationAction` end-to-end (BC-11, P-12) -- admin re-implementing
    those would be a second, unreachable copy of a capability the owning module already exposes
    (Absolute Architecture Rule 4)."""

    async def list_moderation_queue(
        self, status: str | None = None, limit: int | None = 20
    ) -> object:
        async for session in _moderation_session():
            use_cases = ModerationUseCases(
                cases=SqlalchemyModerationCaseRepository(session),
                action_service=_build_moderation_action_service(),
                outbox=OutboxWriter(session, ModerationOutboxEventRow),
            )
            return await use_cases.list_queue(
                status=ModerationCaseStatus(status) if status else None,
                subject_type=None,
                cursor=None,
                limit=limit or 20,
            )
        raise AssertionError("unreachable: _moderation_session always yields exactly once")


class _VerificationQueueProbe:
    """Mirrors `_ModerationQueueProbe`'s own docstring exactly, for `profiles.application.
    VerificationUseCases.list_queue` -- profiles' own router already serves
    `listVerificationQueue`/`decideVerification` end-to-end (BC-02, P-11)."""

    async def list_verification_queue(
        self, status: str | None = None, limit: int | None = 20
    ) -> object:
        async for session in _profiles_session():
            use_cases = VerificationUseCases(
                profiles=SqlalchemyBusinessProfileRepository(session),
                cases=SqlalchemyVerificationCaseRepository(session),
                eligibility=SqlalchemyVerificationEligibilityRepository(session),
                media=_profiles_media_adapter(),
                outbox=OutboxWriter(session, ProfilesOutboxEventRow),
            )
            return await use_cases.list_queue(
                status=ProfilesCaseStatus(status) if status else None,
                cursor=None,
                limit=limit or 20,
            )
        raise AssertionError("unreachable: _profiles_session always yields exactly once")


class _InvoiceQueueProbe:
    """Mirrors `_ModerationQueueProbe`'s own docstring exactly, for `billing.application.
    payment_use_cases.PaymentUseCases.admin_list_invoices` -- billing's own router already serves
    `adminListInvoices`/`confirmInvoicePayment` end-to-end (BC-08, P-09)."""

    async def admin_list_invoices(
        self, status: str | None = None, limit: int | None = 20
    ) -> object:
        async for session in _billing_session():
            use_cases = PaymentUseCases(
                orders=SqlalchemyOrderRepository(session),
                invoices=SqlalchemyInvoiceRepository(session),
                entitlements=SqlalchemyEntitlementRepository(session),
                payment_provider=_billing_payment_provider(),
                outbox=OutboxWriter(session, BillingOutboxEventRow),
            )
            return await use_cases.admin_list_invoices(
                status=InvoiceStatus(status) if status else None,
                cursor=None,
                limit=limit or 20,
            )
        raise AssertionError("unreachable: _billing_session always yields exactly once")


class _UserQueueProbe:
    """Mirrors `_ModerationQueueProbe`'s own docstring exactly, for `identity.application.
    admin_use_cases.AdminIdentityUseCases.list_users` -- identity's own router already serves
    `adminListUsers`/`adminChangeUserStatus`/`assignRole`/`revokeRole` end-to-end (BC-01, P-16/
    ADR-0006)."""

    async def admin_list_users(self, status: str | None = None, limit: int | None = 20) -> object:
        async for session in _identity_session():
            use_cases = AdminIdentityUseCases(
                accounts=SqlalchemyUserAccountRepository(session),
                sessions=RedisSessionRepository(_identity_redis_client()),
                outbox=OutboxWriter(session, IdentityOutboxEventRow),
                role_reader=_role_definition_reader(),
            )
            return await use_cases.list_users(
                status=status, query=None, cursor=None, limit=limit or 20
            )
        raise AssertionError("unreachable: _identity_session always yields exactly once")


async def provide_admin_dashboard_use_cases(
    _operator: AdminActingOperator = Depends(provide_admin_acting_operator),
) -> AdminDashboardUseCases:
    """`_operator` is a gate-only dependency: `provide_admin_acting_operator` already ran the
    real `admin:dashboard:read` authorization check as its side effect (Security Sec 4.2 Gate-3);
    nothing below needs the resolved account id, since every probe below is read-only and
    unscoped to the caller."""
    return AdminDashboardUseCases(
        moderation=_ModerationQueueProbe(),
        verification=_VerificationQueueProbe(),
        orders=_InvoiceQueueProbe(),
        users=_UserQueueProbe(),
    )
