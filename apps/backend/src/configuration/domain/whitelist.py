"""WhitelistRegistry -- the code-owned catalogue of Platform Capability [P] vocabularies that
Business Configuration [C] may compose from, and nothing else (DDD Sec 5.4 "WhitelistRegistry
[P] -- the code-owned catalogue of FieldTypes, ValidatorTypes, PermissionKeys, ProductTypes,
EventKeys"; Config Framework Sec 9 "Whitelist membership"; I-16). This is a security boundary,
not a validation nicety (Security Architecture Sec 4.1) -- configuration can compose instances
from these closed sets, and can never add a new value outside them without a code release.

Deliberately domain-pure (no import of `contracts` or any other module): Clean Architecture rule
1 restricts `domain/` to `shared_kernel` only. Every set below is therefore a literal, hand-kept
copy of the authoritative source cited in its comment, not an import of it -- drift is caught by
a dedicated unit test that imports the authoritative source at test scope (permitted; only
`domain/` itself is restricted) and asserts equality.

Some vocabularies below are named by every source document but never enumerated with exact
values (sort options, banner page/zone descriptors, rendering hints, the platform-settings key
schema, SEO page types). Config Framework Sec 2.8 explicitly frames whitelist *scope* as "a
release-time, ADR-controlled decision", not something requiring a document amendment -- so each
such set here is a conservative, clearly-flagged v1 seed (`# PLACEHOLDER`), extendable later
without touching the generic machinery. See `configuration/README.md` for the full list.
"""

from __future__ import annotations

import re

# Frozen at Task P-01 in `configuration/interfaces/dto.py` (`FormField.field_type` Literal),
# itself derived from DDD Sec 5.4/8.2 and Config Framework Sec 5.1's repeated worked examples.
FIELD_TYPES: frozenset[str] = frozenset(
    {"text", "number", "select", "multiselect", "boolean", "date", "range", "location", "file"}
)

# Frozen at Task P-01 in `configuration/interfaces/dto.py` (`ValidatorBinding.validator_type`
# Literal), derived from DDD Sec 5.4/8.2 and Config Framework Sec 3.7/5.1.
VALIDATOR_TYPES: frozenset[str] = frozenset(
    {
        "required",
        "length",
        "numeric_range",
        "pattern_safe",
        "option_membership",
        "image_count",
    }
)

# Frozen at Task P-01 (`FormFieldConditionalVisibility.operator` Literal) -- Config Framework
# Sec 5.1 "a bounded, declarative condition vocabulary [P] ... from a closed set".
CONDITION_OPERATORS: frozenset[str] = frozenset(
    {"EQUALS", "NOT_EQUALS", "IN", "NOT_IN", "GREATER_THAN", "LESS_THAN"}
)

# Physical DB Sec 2.4 `product_definition_version.product_type` CHECK -- the closed six
# (BR-BILL-01).
PRODUCT_TYPES: frozenset[str] = frozenset(
    {
        "SUBSCRIPTION",
        "PREMIUM",
        "FEATURED",
        "TOP_PLACEMENT",
        "VERIFICATION",
        "BANNER_PLACEMENT",
    }
)

# Physical DB Sec 2.4 `notification_template_version.channel` CHECK (DEC-18 fixed providers).
NOTIFICATION_CHANNELS: frozenset[str] = frozenset({"EMAIL", "WEB_PUSH", "SMS"})

# DDD Sec 8.1: "the EventKey vocabulary for notification templates is a subset of [the domain
# event catalogue]" -- no narrower subset is enumerated anywhere, so the v1 whitelist is the
# full frozen catalogue (`contracts/events/*.py` `event_type` Literals; 56 events as of ADR-0005,
# docs/adr/0005-analytics-missing-metric-events.md -- previously 53 as of ADR-0001,
# docs/adr/0001-media-asset-status-events.md). `tests/configuration/test_whitelist.py` asserts
# this set has zero drift against `contracts.events` by importing it at test scope.
EVENT_KEYS: frozenset[str] = frozenset(
    {
        "AccountClosed",
        "AccountSuspended",
        "AuditEntryRecorded",
        "BannerCampaignEnded",
        "BannerCampaignScheduled",
        "BannerCampaignStarted",
        "BannerClickRecorded",
        "BannerImpressionRecorded",
        "BusinessProfileCreated",
        "BusinessVerified",
        "CategoryChanged",
        "CategoryCreated",
        "CategoryRetired",
        "ChatInitiated",
        "ConfigurationChanged",
        "ContactButtonClicked",
        "ContentReported",
        "EntitlementActivated",
        "EntitlementExpired",
        "EntitlementRevoked",
        "FavoriteAdded",
        "FavoriteRemoved",
        "FormDefinitionPublished",
        "InvoiceIssued",
        "ListingArchived",
        "ListingCreated",
        "ListingDeleted",
        "ListingDraftSaved",
        "ListingEdited",
        "ListingExpired",
        "ListingFlagged",
        "ListingPublished",
        "ListingRenewed",
        "ListingSuspended",
        "ListingViewed",
        "MediaAssetAccepted",
        "MediaAssetReady",
        "MediaAssetRejected",
        "MessageSent",
        "MetricEventCaptured",
        "ModerationActionTaken",
        "NotificationTemplateChanged",
        "OrderPlaced",
        "PaymentConfirmed",
        "PhoneRevealed",
        "PlacementSlotDefined",
        "PlatformSettingsChanged",
        "PremiumListingStat",
        "ProductDefinitionChanged",
        "RoleDefinitionChanged",
        "SearchConfigurationChanged",
        "UserBlocked",
        "UserRegistered",
        "VerificationRejected",
        "VerificationRequested",
        "VerifiedBadgeExpired",
    }
)

# Config Framework Sec 7.1: "the fixed PermissionKey catalogue [P], owned by the WhitelistRegistry
# in code" -- DDD Sec 5.4 places that registry inside BC-04/configuration. No document enumerates
# the literal key strings; the OpenAPI operation descriptions ("Requires the relevant
# manage-configuration permission key") are the one literal anchor available, naming exactly one
# manage key per entity type. This task derives, from that anchor, one `<entity>:manage` key per
# entity type (author/edit/publish that entity family) plus one `<entity>:approve` key for each
# of the six controlled-track entities (the maker-checker "different principal" requirement,
# Super-Admin-only for role-definition/platform-settings per CF Sec 2.3 -- enforced by seed data,
# not by a code branch). Other modules (identity, catalog, ...) extend this same catalogue with
# their own keys in their own tasks -- the registry is designed to be extended, not exhaustive.
# Task P-05 (identity/BC-01) extends the catalogue per the comment above, with the two keys its
# own admin-facing capabilities gate: `identity:account:manage_status` (suspend/reactivate,
# `AdminIdentityUseCases.change_user_status`) and `identity:role:assign`
# (`AdminIdentityUseCases.assign_role`/`revoke_role`). Both are now consulted for real as of Task
# P-16 (`identity.interfaces.routers.admin_users_router`, ADR-0006) via the exact same
# default-deny `AuthorizationService` mechanism as every other module's.
# Task P-07 (catalog/BC-03) extends the catalogue with the one key its moderation-invoked command
# surface gates: `catalog:listing:moderate` (`catalog.application.listing_use_cases.
# ListingUseCases.unflag_listing`, "the listing state-transition command port that moderation
# will later invoke", BC-11 -- out of this task's scope). The caller (moderation) is responsible
# for consulting `identity.interfaces.ports.AuthorizationPort.authorize` with this key before
# invoking catalog's port, mirroring how `AuthorizationPort` itself is "consulted in-process by
# every other module" without the callee re-validating (identity/interfaces/ports.py).
# Task P-09 (billing/BC-08) extends the catalogue with the one key its own admin-facing operation
# gates: `billing:invoice:confirm_payment` (`confirmInvoicePayment`, `POST /admin/billing/
# invoices/{invoiceId}/confirm-payment`, FR-BILL-002) -- unlike catalog's `catalog:listing:
# moderate` (declared but not yet consulted anywhere, pending a future moderation module),
# `billing:invoice:confirm_payment` IS wired end-to-end in this task:
# `composition_root.provide_billing_acting_operator` calls the real `identity.domain.
# AuthorizationService.authorize` against it before the router ever reaches `PaymentUseCases.
# confirm_payment`.
# Task P-11 (profiles/BC-02) extends the catalogue with two keys: `profiles:verification:review`
# gates the reviewer-only verification queue/decision surface (`listVerificationQueue`,
# `decideVerification`) -- wired end-to-end the same way `billing:invoice:confirm_payment` is
# (`composition_root.provide_profiles_acting_reviewer` calls the real `identity.domain.
# AuthorizationService.authorize` against it before the router reaches `VerificationUseCases`).
# `profiles:profile:moderate` gates the moderation-invoked command surface (`profiles.interfaces.
# moderation_port.ProfileModerationPort`'s `revoke_badge`/`archive_profile`).
# Task P-12 (moderation/BC-11) adds `moderation:case:review`, gating the reviewer-only queue/
# resolve surface (`listModerationQueue`, `getModerationCase`, `applyModerationAction`) -- wired
# end-to-end the same way (`composition_root.provide_moderation_acting_moderator` calls the real
# `identity.domain.AuthorizationService.authorize` against it). This task is also the first
# caller of `catalog:listing:moderate` and `profiles:profile:moderate` themselves (both previously
# "declared but not yet consulted anywhere" placeholders, as their own comments above say) --
# `composition_root.py`'s three moderation-target bridge adapters invoke catalog's/profiles' own
# moderation ports, which is a downstream command call, not an authorization check performed by
# moderation itself; the authorization gate for the whole action-application flow is the single
# `moderation:case:review` check at the router boundary (I-24: "the target module performs its
# own state change and emits its own event" -- authorization for the compensating command belongs
# to the moderator role that triggered the case resolution, not to a second check re-run inside
# catalog/profiles).
# Task P-14 (ads/BC-09) adds `ads:campaign:manage`, gating all seven `/admin/campaigns*` operator
# operations (ADR-0004) -- wired end-to-end the same way (`composition_root.
# provide_ads_acting_operator` calls the real `identity.domain.AuthorizationService.authorize`
# against it). `/banners/*` (public serving/engagement capture) needs no permission key at all.
# Task P-15 (analytics/BC-13) adds `analytics:audit:read` (gates `queryAuditLog`,
# `GET /admin/audit-log`) and `analytics:reports:read` (gates `getAdminReports`,
# `GET /admin/reports`) -- both operations were already frozen in `contracts/openapi.yaml` under
# the cross-cutting `Administration` tag (`contracts/README.md`'s own tag-routing rule sends them
# to `analytics`, the module that owns the underlying data) but had no permission key at all
# until this task; wired end-to-end the same way (`composition_root.
# provide_analytics_acting_operator` calls the real `identity.domain.AuthorizationService.
# authorize` against it).
# Task P-16 (admin/BC-12) adds `admin:dashboard:read`, gating `getAdminDashboard`
# (`GET /admin/dashboard`) -- the ONE operation that genuinely belongs to admin itself (DDD Sec
# 5.12: "maps to no single owning aggregate"), wired the same way
# (`composition_root.provide_admin_acting_operator`). Every OTHER composed operation admin's own
# application layer touches is gated by the OWNING module's already-existing permission key
# above (e.g. `identity:account:manage_status`, `moderation:case:review`) -- admin invents no
# permission key for capability it doesn't own (Absolute Architecture Rule 9/AIR-19).
PERMISSION_KEYS: frozenset[str] = frozenset(
    {
        "config:category:manage",
        "config:category:approve",
        "config:form-definition:manage",
        "config:form-definition:approve",
        "config:product-definition:manage",
        "config:product-definition:approve",
        "config:placement-slot:manage",
        "config:placement-slot:approve",
        "config:role-definition:manage",
        "config:role-definition:approve",
        "config:platform-settings:manage",
        "config:platform-settings:approve",
        "config:search-configuration:manage",
        "config:notification-template:manage",
        "identity:account:manage_status",
        "identity:role:assign",
        "identity:registration:review",
        "catalog:listing:moderate",
        "billing:invoice:confirm_payment",
        "profiles:verification:review",
        "profiles:profile:moderate",
        "moderation:case:review",
        "ads:campaign:manage",
        "analytics:audit:read",
        "analytics:reports:read",
        "admin:dashboard:read",
    }
)

# PLACEHOLDER -- named by FR-SRCH-003/Config Framework Sec 3.9/6.1 as "the [P] sort vocabulary"
# but never enumerated. Conservative v1 seed; extend via WhitelistRegistry, not a redesign.
# UNF-021: this spelled the recency option "NEWEST", but `search.domain.SortOption` and the
# already-frozen `contracts/openapi.yaml` `/search` operation both spell it "RECENCY" -- the
# wire contract was never wrong here, this internal whitelist just disagreed with it, so a
# configured "NEWEST" silently had no effect (`GET /search?sort=NEWEST` 422s; nothing downstream
# recognises the string). Renaming this constant is not a contract change -- it doesn't touch
# the wire shape, only which string an admin authoring a SearchConfiguration is offered -- so it
# needs no ADR, only agreement with what the contract already accepts.
SORT_OPTIONS: frozenset[str] = frozenset({"RELEVANCE", "RECENCY", "PRICE_ASC", "PRICE_DESC"})

# PLACEHOLDER -- Config Framework Sec 3.14 names four example homepage zones ("hero, featured
# categories, promoted listings, banners"); Sec 3.2/8.1 names a "page/zone descriptor [P
# vocabulary]" for banner placement slots without enumerating it. This v1 seed covers both uses.
PAGE_ZONES: frozenset[str] = frozenset(
    {
        "HOMEPAGE_HERO",
        "HOMEPAGE_FEATURED_CATEGORIES",
        "HOMEPAGE_PROMOTED_LISTINGS",
        "HOMEPAGE_BANNER",
        "CATEGORY_PAGE_TOP",
        "SEARCH_RESULTS_TOP",
        "LISTING_DETAIL_SIDEBAR",
    }
)

# PLACEHOLDER -- Config Framework Sec 5.1 "presentation hints ... drawn from a [P] hint
# vocabulary" without enumeration.
RENDERING_HINTS: frozenset[str] = frozenset(
    {
        "DEFAULT",
        "DROPDOWN",
        "RADIO",
        "CHECKBOX_GROUP",
        "SLIDER",
        "MAP_PICKER",
        "TEXTAREA",
    }
)

# PLACEHOLDER -- Config Framework Sec 3.18 "the closed set of typed platform/display/operational
# parameters" without enumeration. Each key's declared type is enforced at the gate.
SETTINGS_SCHEMA: dict[str, type] = {
    "listing.default_expiry_days": int,
    "feature_flag.banners_enabled": bool,
    "feature_flag.messaging_enabled": bool,
    "otp.expiry_minutes": int,
    "session.expiry_hours": int,
    "search.default_page_size": int,
    # URL segment for the secret owner-admin panel (frontend `/$ownerAdminSlug`) -- lives here
    # rather than as a build-time env var so a super-admin can change it from inside the panel
    # itself, at will, without a redeploy. Never served back verbatim to an unauthenticated
    # caller (see `verify_owner_admin_slug` in interfaces/routers.py, a yes/no oracle only).
    "admin.owner_panel_slug": str,
    # Security Sec 3.1 brute-force protection (`identity.domain.policies.LoginLockoutPolicy`) --
    # admin-tunable without a redeploy per that feature's own explicit requirement, unlike
    # OtpThrottlePolicy's hardcoded thresholds a few lines above this file's sibling constants.
    "login_lockout.max_attempts": int,
    "login_lockout.block_minutes": int,
    # Homepage "proof strip" marketing numbers (`getPlatformStats`, `interfaces/routers.py`) --
    # `stats.active_listings` is deliberately absent here: that number is a real, live count
    # (`GET /search?limit=1`'s own `page.total`, already public), never an admin-typed value, so
    # it has no settings key at all. These three have no live-computable source (there is no
    # "city"/"partner"/"satisfaction" concept anywhere else in the domain), so they stay
    # admin-edited, same rationale as `login_lockout.*` two lines up.
    "stats.cities": int,
    "stats.partners": int,
    "stats.satisfaction_percent": int,
}

# Every top-level static route the frontend already owns (`apps/frontend/src/routes/*.tsx`/`*/`),
# hand-kept in sync the same way every other vocabulary in this file is (see module docstring) --
# TanStack Router always resolves a static route ahead of the dynamic `/$ownerAdminSlug` one for
# the same path, so setting the owner-admin panel's slug to any of these would make that static
# page win forever and silently strand the panel behind an unreachable URL (confirmed incident:
# an admin set it to "boss", permanently shadowing the dedicated login route at that path -- ADR
# owner-admin-panel-access). Checked case-insensitively at both write time (`check_settings_key`
# below) and read time (`_current_owner_admin_slug` in interfaces/routers.py, so an already-bad
# stored value self-heals to the default on the very next read instead of staying broken).
#
# Deliberately does NOT include "owner-admin" itself: that was the panel's original fixed
# route (a real conflict back when the frontend still had a static `routes/owner-admin/`
# directory), but that directory no longer exists -- it's the dynamic `/$ownerAdminSlug`
# route's fallback DEFAULT value now (`_OWNER_ADMIN_SLUG_DEFAULT` here and in
# interfaces/routers.py, `OWNER_PANEL_SLUG_DEFAULT` in the frontend), which must stay a
# legal, assignable value or the very first settings republish after any unrelated key is
# added would fail gate validation trying to carry an "already invalid" default forward
# (confirmed live -- this was the exact second half of the same incident above).
RESERVED_OWNER_PANEL_SLUGS: frozenset[str] = frozenset(
    {
        "about",
        "ad-rules",
        "admin",
        "agents",
        "ai",
        "api",
        "appliances",
        "auth",
        "blog",
        "boss",
        "categories",
        "checkout",
        "companies",
        "compare",
        "construction",
        "contact",
        "dashboard",
        "faq",
        "favorites",
        "furniture",
        "health",
        "hostels",
        "hotels",
        "interior",
        "invest",
        "jobs",
        "landscape",
        "list",
        "listing",
        "maintenance",
        "map",
        "materials",
        "messages",
        "news",
        "notifications",
        "offer",
        "payments",
        "pricing",
        "privacy",
        "properties",
        "public-offer",
        "ready",
        "recreation",
        "refund",
        "refund-policy",
        "rules",
        "saved",
        "search",
        "security",
        "security-policy",
        "services",
        "settings",
        "sitemap.xml",
        "subscriptions",
        "support",
        "terms",
        "verification",
        "wallet",
    }
)

_OWNER_PANEL_SLUG_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")


def is_valid_owner_panel_slug(value: object) -> bool:
    """True only for a lowercase-slug-shaped string that doesn't collide with a reserved route.
    Shared by the write-side gate check and the read-side self-healing fallback so the two can
    never drift apart on what counts as safe."""
    if not isinstance(value, str) or not value:
        return False
    slug = value.strip().lower()
    return (
        bool(_OWNER_PANEL_SLUG_PATTERN.fullmatch(slug)) and slug not in RESERVED_OWNER_PANEL_SLUGS
    )


# PLACEHOLDER -- Config Framework Sec 3.17 "a fixed set of named page keys" without enumeration.
STATIC_PAGE_KEYS: frozenset[str] = frozenset(
    {"TERMS_OF_SERVICE", "PRIVACY_POLICY", "ABOUT", "CONTACT", "FAQ"}
)

# PLACEHOLDER -- Config Framework Sec 3.16 "a closed page-type set" for SEO templates, without
# enumeration.
SEO_PAGE_TYPES: frozenset[str] = frozenset(
    {"HOME", "CATEGORY", "LISTING", "BUSINESS_PROFILE", "STATIC_PAGE"}
)


class WhitelistViolationError(ValueError):
    """Raised by `WhitelistRegistry` when a configuration draft references a value outside the
    closed set for its vocabulary -- I-16's operational form (Config Framework Sec 9 "Whitelist
    membership")."""

    def __init__(self, vocabulary: str, value: str) -> None:
        self.vocabulary = vocabulary
        self.value = value
        super().__init__(f"{value!r} is not a whitelisted {vocabulary}")


class WhitelistRegistry:
    """Stateless gate over the closed vocabularies above -- BoundedConfigurationPolicy's
    membership half (DDD Sec 5.4). No instance state; a class would work equally well, but an
    instance lets `application/` inject it through a port like any other collaborator rather
    than importing module-level functions directly (Playbook Sec 6)."""

    def check(self, vocabulary: str, value: str, allowed: frozenset[str]) -> None:
        if value not in allowed:
            raise WhitelistViolationError(vocabulary, value)

    def check_field_type(self, value: str) -> None:
        self.check("FieldType", value, FIELD_TYPES)

    def check_validator_type(self, value: str) -> None:
        self.check("ValidatorType", value, VALIDATOR_TYPES)

    def check_condition_operator(self, value: str) -> None:
        self.check("ConditionOperator", value, CONDITION_OPERATORS)

    def check_product_type(self, value: str) -> None:
        self.check("ProductType", value, PRODUCT_TYPES)

    def check_notification_channel(self, value: str) -> None:
        self.check("NotificationChannel", value, NOTIFICATION_CHANNELS)

    def check_event_key(self, value: str) -> None:
        self.check("EventKey", value, EVENT_KEYS)

    def check_permission_key(self, value: str) -> None:
        self.check("PermissionKey", value, PERMISSION_KEYS)

    def check_sort_option(self, value: str) -> None:
        self.check("SortOption", value, SORT_OPTIONS)

    def check_page_zone(self, value: str) -> None:
        self.check("PageZone", value, PAGE_ZONES)

    def check_rendering_hint(self, value: str) -> None:
        self.check("RenderingHint", value, RENDERING_HINTS)

    def check_static_page_key(self, value: str) -> None:
        self.check("StaticPageKey", value, STATIC_PAGE_KEYS)

    def check_seo_page_type(self, value: str) -> None:
        self.check("SeoPageType", value, SEO_PAGE_TYPES)

    def check_settings_key(self, key: str, value: object) -> None:
        if key not in SETTINGS_SCHEMA:
            raise WhitelistViolationError("SettingsKey", key)
        expected_type = SETTINGS_SCHEMA[key]
        if not isinstance(value, expected_type):
            raise WhitelistViolationError(
                "SettingsValueType",
                f"{key}={value!r} (expected {expected_type.__name__})",
            )
        if key == "admin.owner_panel_slug" and not is_valid_owner_panel_slug(value):
            raise WhitelistViolationError("OwnerPanelSlug", str(value))

    def manage_permission_key(self, entity_type_value: str) -> str:
        return f"config:{entity_type_value}:manage"

    def approve_permission_key(self, entity_type_value: str) -> str:
        return f"config:{entity_type_value}:approve"
