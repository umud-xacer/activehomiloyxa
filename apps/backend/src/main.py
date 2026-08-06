"""The FastAPI app entrypoint (SAD Sec 10 request-lifecycle diagram: interfaces/ -> application/
-> domain/ -> infrastructure/). STATUS (Task P-16): all 13 bounded-context modules are mounted --
configuration, identity, media, catalog, billing, search, messaging, profiles, moderation,
notifications, ads, analytics, and now admin (`getAdminDashboard`, the one `Administration`-tagged
operation that is genuinely admin's own; every other `Administration`-tagged operation is mounted
on its owning module's own router per `contracts/README.md`'s tag-routing rule). Wires what every
module shares: trace-id correlation, the Problem
error envelope (extended per-module via `register_*_exception_mappings`), and the two infra-level
endpoints Infra Sec 6's container table specifies for the `api` container (`/health` liveness,
`/ready` readiness) -- neither is part of `contracts/openapi.yaml`'s business surface (they're
outside `/api/v1`, sanctioned by the Infrastructure document instead, the same way a container
orchestrator's probes always are).
"""

from __future__ import annotations

import asyncio
import os

import redis.asyncio as redis_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import composition_root
from admin.interfaces.di import get_acting_operator as get_admin_acting_operator
from admin.interfaces.di import get_dashboard_use_cases
from admin.interfaces.routers import admin_router
from ads.interfaces.di import (
    get_acting_operator as get_ads_acting_operator,
)
from ads.interfaces.di import (
    get_campaign_use_cases,
    get_serving_use_cases,
)
from ads.interfaces.errors import register_ads_exception_mappings
from ads.interfaces.routers import ads_admin_router, ads_public_router
from analytics.interfaces.di import (
    get_audit_acting_operator,
    get_audit_use_cases,
    get_reports_acting_operator,
)
from analytics.interfaces.di import get_report_use_cases as get_admin_report_use_cases
from analytics.interfaces.errors import register_analytics_exception_mappings
from analytics.interfaces.routers import analytics_router
from backbone.errors import (
    TraceIdMiddleware,
    default_exception_mapper,
    install_error_handlers,
)
from backbone.logging import configure_logging
from backbone.persistence.engine import MissingDatabaseConfigError, make_engine
from backbone.persistence.redis_client import redis_url
from billing.interfaces.di import (
    get_acting_operator,
    get_entitlement_use_cases,
    get_order_use_cases,
    get_payment_use_cases,
)
from billing.interfaces.di import (
    get_acting_user as get_billing_acting_user,
)
from billing.interfaces.errors import register_billing_exception_mappings
from billing.interfaces.routers import admin_billing_router, billing_router
from catalog.interfaces.di import (
    get_acting_user as get_catalog_acting_user,
)
from catalog.interfaces.di import (
    get_favorite_use_cases,
    get_listing_use_cases,
)
from catalog.interfaces.di import (
    get_optional_acting_user as get_catalog_optional_acting_user,
)
from catalog.interfaces.errors import register_catalog_exception_mappings
from catalog.interfaces.routers import catalog_router, favorites_router
from configuration.interfaces.auth import get_acting_admin as get_config_acting_admin
from configuration.interfaces.di import (
    get_category_read_use_cases,
    get_configuration_use_cases,
)
from configuration.interfaces.errors import register_configuration_exception_mappings
from configuration.interfaces.routers import admin_config_router, categories_router
from identity.interfaces.di import (
    get_account_use_cases,
    get_admin_identity_use_cases,
    get_authenticated_request,
    get_authentication_use_cases,
    get_registration_reviewer,
    get_roles_acting_operator,
    get_users_acting_operator,
)
from identity.interfaces.errors import register_identity_exception_mappings
from identity.interfaces.routers import admin_users_router, auth_router, users_router
from media.interfaces.di import get_acting_user, get_media_intake_use_cases
from media.interfaces.errors import register_media_exception_mappings
from media.interfaces.routers import media_router
from messaging.interfaces.di import (
    get_acting_user as get_messaging_acting_user,
)
from messaging.interfaces.di import (
    get_block_use_cases,
    get_conversation_use_cases,
    get_report_use_cases,
)
from messaging.interfaces.errors import register_messaging_exception_mappings
from messaging.interfaces.routers import messaging_router
from moderation.interfaces.di import get_acting_moderator, get_moderation_use_cases
from moderation.interfaces.errors import register_moderation_exception_mappings
from moderation.interfaces.routers import admin_moderation_router
from notifications.interfaces.di import (
    get_acting_user as get_notifications_acting_user,
)
from notifications.interfaces.di import get_notification_use_cases
from notifications.interfaces.errors import register_notifications_exception_mappings
from notifications.interfaces.routers import notifications_router
from profiles.interfaces.di import (
    get_acting_reviewer as get_profiles_acting_reviewer,
)
from profiles.interfaces.di import (
    get_acting_user as get_profiles_acting_user,
)
from profiles.interfaces.di import (
    get_profile_use_cases,
    get_verification_use_cases,
)
from profiles.interfaces.errors import register_profiles_exception_mappings
from profiles.interfaces.routers import admin_profiles_router, profiles_router
from search.interfaces.di import get_search_use_cases
from search.interfaces.errors import register_search_exception_mappings
from search.interfaces.routers import search_router


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Active Home Platform API")
    app.add_middleware(TraceIdMiddleware)
    # CORS_ALLOWED_ORIGINS is a comma-separated origin list (Infra Sec 11 twelve-factor
    # runtime setting, not business config). Frontend dev server and API run on different
    # ports (127.0.0.1:8080 vs 127.0.0.1:8000), so every browser request is cross-origin.
    # allow_credentials=True is required for the ah_session cookie flow, which means
    # allow_origins cannot be "*" (fetch spec forbids credentialed wildcard responses).
    allowed_origins = [
        origin.strip()
        for origin in os.environ.get(
            "CORS_ALLOWED_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080"
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    mapper = default_exception_mapper()
    register_configuration_exception_mappings(mapper)
    register_identity_exception_mappings(mapper)
    register_media_exception_mappings(mapper)
    register_catalog_exception_mappings(mapper)
    register_billing_exception_mappings(mapper)
    register_search_exception_mappings(mapper)
    register_messaging_exception_mappings(mapper)
    register_profiles_exception_mappings(mapper)
    register_moderation_exception_mappings(mapper)
    register_notifications_exception_mappings(mapper)
    register_ads_exception_mappings(mapper)
    register_analytics_exception_mappings(mapper)
    install_error_handlers(app, mapper)

    # Composition root (Playbook Sec 6): the module's own interfaces/di.py only declares the
    # Depends(...) target, never the concrete adapter -- wired here instead (DIP).
    app.dependency_overrides[get_configuration_use_cases] = (
        composition_root.provide_configuration_use_cases
    )
    # DEF-01: replaces configuration's P-04 header-trusting stand-in with the real
    # session-backed resolver. Without this override every admin/config/* operation is
    # authorizable by any caller who invents a UUID and a permission string.
    app.dependency_overrides[get_config_acting_admin] = (
        composition_root.provide_configuration_acting_admin
    )
    app.dependency_overrides[get_category_read_use_cases] = (
        composition_root.provide_category_read_use_cases
    )
    app.dependency_overrides[get_authentication_use_cases] = (
        composition_root.provide_authentication_use_cases
    )
    app.dependency_overrides[get_account_use_cases] = composition_root.provide_account_use_cases
    app.dependency_overrides[get_authenticated_request] = (
        composition_root.provide_authenticated_request
    )
    app.dependency_overrides[get_admin_identity_use_cases] = (
        composition_root.provide_admin_identity_use_cases
    )
    app.dependency_overrides[get_users_acting_operator] = (
        composition_root.provide_users_acting_operator
    )
    app.dependency_overrides[get_roles_acting_operator] = (
        composition_root.provide_roles_acting_operator
    )
    app.dependency_overrides[get_registration_reviewer] = (
        composition_root.provide_registration_reviewer
    )
    app.dependency_overrides[get_media_intake_use_cases] = (
        composition_root.provide_media_intake_use_cases
    )
    app.dependency_overrides[get_acting_user] = composition_root.provide_acting_user
    app.dependency_overrides[get_listing_use_cases] = composition_root.provide_listing_use_cases
    app.dependency_overrides[get_favorite_use_cases] = composition_root.provide_favorite_use_cases
    app.dependency_overrides[get_catalog_acting_user] = composition_root.provide_catalog_acting_user
    app.dependency_overrides[get_catalog_optional_acting_user] = (
        composition_root.provide_catalog_optional_acting_user
    )
    app.dependency_overrides[get_order_use_cases] = composition_root.provide_order_use_cases
    app.dependency_overrides[get_payment_use_cases] = composition_root.provide_payment_use_cases
    app.dependency_overrides[get_entitlement_use_cases] = (
        composition_root.provide_entitlement_use_cases
    )
    app.dependency_overrides[get_billing_acting_user] = composition_root.provide_billing_acting_user
    app.dependency_overrides[get_acting_operator] = composition_root.provide_billing_acting_operator
    app.dependency_overrides[get_search_use_cases] = composition_root.provide_search_use_cases
    app.dependency_overrides[get_messaging_acting_user] = (
        composition_root.provide_messaging_acting_user
    )
    app.dependency_overrides[get_conversation_use_cases] = (
        composition_root.provide_conversation_use_cases
    )
    app.dependency_overrides[get_block_use_cases] = composition_root.provide_block_use_cases
    app.dependency_overrides[get_report_use_cases] = composition_root.provide_report_use_cases
    app.dependency_overrides[get_profile_use_cases] = composition_root.provide_profile_use_cases
    app.dependency_overrides[get_verification_use_cases] = (
        composition_root.provide_verification_use_cases
    )
    app.dependency_overrides[get_profiles_acting_user] = (
        composition_root.provide_profiles_acting_user
    )
    app.dependency_overrides[get_profiles_acting_reviewer] = (
        composition_root.provide_profiles_acting_reviewer
    )
    app.dependency_overrides[get_moderation_use_cases] = (
        composition_root.provide_moderation_use_cases
    )
    app.dependency_overrides[get_acting_moderator] = (
        composition_root.provide_moderation_acting_moderator
    )
    app.dependency_overrides[get_notification_use_cases] = (
        composition_root.provide_notification_use_cases
    )
    app.dependency_overrides[get_notifications_acting_user] = (
        composition_root.provide_notifications_acting_user
    )
    app.dependency_overrides[get_campaign_use_cases] = composition_root.provide_campaign_use_cases
    app.dependency_overrides[get_serving_use_cases] = composition_root.provide_serving_use_cases
    app.dependency_overrides[get_ads_acting_operator] = composition_root.provide_ads_acting_operator
    app.dependency_overrides[get_audit_use_cases] = composition_root.provide_audit_use_cases
    app.dependency_overrides[get_admin_report_use_cases] = (
        composition_root.provide_admin_report_use_cases
    )
    app.dependency_overrides[get_audit_acting_operator] = (
        composition_root.provide_audit_acting_operator
    )
    app.dependency_overrides[get_reports_acting_operator] = (
        composition_root.provide_reports_acting_operator
    )
    app.dependency_overrides[get_dashboard_use_cases] = (
        composition_root.provide_admin_dashboard_use_cases
    )
    app.dependency_overrides[get_admin_acting_operator] = (
        composition_root.provide_admin_acting_operator
    )

    app.include_router(categories_router, prefix="/api/v1")
    app.include_router(admin_config_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(admin_users_router, prefix="/api/v1")
    app.include_router(media_router, prefix="/api/v1")
    app.include_router(catalog_router, prefix="/api/v1")
    app.include_router(favorites_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    app.include_router(admin_billing_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(messaging_router, prefix="/api/v1")
    app.include_router(profiles_router, prefix="/api/v1")
    app.include_router(admin_profiles_router, prefix="/api/v1")
    app.include_router(admin_moderation_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(ads_admin_router, prefix="/api/v1")
    app.include_router(ads_public_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness only -- the process is up and serving. No dependency checks (Infra Sec 6)."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        """Readiness -- PostgreSQL and Redis both reachable (Infra Sec 6: "GET /ready
        (readiness: DB/Redis reachable)"), so nginx does not route to a not-yet-ready replica.
        Built fresh on every call rather than cached at startup, deliberately: a connection
        that was fine at boot and later drops must flip this to unready."""
        checks: dict[str, bool] = {}

        try:
            engine = make_engine()
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                checks["postgres"] = True
            finally:
                await engine.dispose()
        except (MissingDatabaseConfigError, OSError, TimeoutError):
            checks["postgres"] = False

        try:
            client = redis_asyncio.from_url(redis_url())
            try:
                await asyncio.wait_for(client.ping(), timeout=3.0)
                checks["redis"] = True
            finally:
                await client.aclose()
        except (MissingDatabaseConfigError, OSError, TimeoutError):
            checks["redis"] = False

        healthy = all(checks.values())
        return JSONResponse(status_code=200 if healthy else 503, content=checks)

    return app


app = create_app()
