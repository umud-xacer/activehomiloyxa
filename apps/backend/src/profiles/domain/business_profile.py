"""profiles -- the `BusinessProfile` aggregate (DDD Sec 5.2 `AR: BusinessProfile [P]`). The
platform's company presence and the trust-badge holder (I-13). Persistence-ignorant, mirrors
`catalog.domain.listing.Listing`'s style: frozen dataclass, every transition returns a new
instance via `dataclasses.replace`, guarded by a typed exception raised before the replace.

I-13 ("A VerifiedBadge exists only from an approved case, displays only within validity, and is
withdrawn on expiry") is realised entirely by this class's own three badge methods: `issue_badge`
is the ONLY method that can set `badge.status` to `VALID`, and it REQUIRES a
`verification_case.ApprovedVerificationProof` -- a type that can itself only be constructed from
an approved `VerificationCase` (see that module). There is no setter, no alternate constructor
path, and no way to reach `VALID` by any other call on this class.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from profiles.domain.exceptions import (
    IllegalBadgeTransitionError,
    IllegalProfileStatusTransitionError,
    OnboardingAlreadyCompletedError,
    OnboardingIncompleteError,
    PortfolioItemLimitExceededError,
    PortfolioItemNotFoundError,
    PromoVideoLimitExceededError,
    PromoVideoNotFoundError,
    SubCategoryNotInMainCategoryError,
)
from profiles.domain.portfolio_item import PortfolioItem
from profiles.domain.value_objects import (
    SUB_CATEGORIES_BY_MAIN_CATEGORY,
    BadgeStatus,
    MainCategory,
    ProfileStatus,
    ProfileType,
    SubCategory,
    VerifiedBadge,
)
from profiles.domain.verification_case import ApprovedVerificationProof
from shared_kernel import BusinessProfileId, LocalizedText, UserId

MAX_PORTFOLIO_ITEMS = 50
"""Physical DB `ck (position BETWEEN 1 AND 50)` -- the literal spec number."""

MAX_PROMO_VIDEOS = 2
"""Landing-page promo-video business rule (additive, site-owner spec): at most 2 short
promotional videos per business profile, each independently capped to 30 seconds -- enforced at
attach-time by `application.ProfileUseCases.add_promo_video` (duration is a fact about the
referenced media asset, not something this aggregate can check on its own)."""


def _require_valid_sub_category(
    main_category: MainCategory | None, sub_category: SubCategory | None
) -> None:
    if sub_category is None:
        return
    allowed = SUB_CATEGORIES_BY_MAIN_CATEGORY.get(main_category) if main_category else None
    if not allowed or sub_category not in allowed:
        raise SubCategoryNotInMainCategoryError(
            sub_category.value, main_category.value if main_category else None
        )


@dataclass(frozen=True)
class BusinessProfile:
    id: BusinessProfileId
    owner_user_id: UserId
    profile_type: ProfileType
    """Fixed for life -- set once by `create`, appears as a parameter on no other method (I-01's
    "fixed for life" discipline, applied here the same way `catalog.domain.listing.Listing`
    documents for its own `category_id`/`owner_user_id`)."""
    name: LocalizedText
    description: LocalizedText | None
    contacts: dict[str, Any]
    """CompanyDetails VO (phones/emails/site) -- Physical DB `contacts jsonb NOT NULL DEFAULT
    '{}'`, no further shape mandated by any approved document."""
    address: str | None
    slug: str
    status: ProfileStatus
    badge: VerifiedBadge | None
    """`None` = never verified (Physical DB `ck_badge_shape`'s own reading)."""
    portfolio: tuple[PortfolioItem, ...]
    logo_media_asset_id: UUID | None
    """The B2B landing-page identity fields (Monetization/Landing-Page task): a single opaque
    media reference each, mirroring `PortfolioItem.media_asset_id`'s own convention (a reference,
    never a resolved URL -- `interfaces/` resolves the CDN URL at read time via `media`, the same
    indirection `catalog.domain.image_attachment.ImageAttachment` already uses). `None` = not set,
    the landing page falls back to a placeholder."""
    banner_media_asset_id: UUID | None
    onboarding_completed_at: datetime | None
    """ADR-0010: set once, by `complete_onboarding`, the moment the mandatory landing-page
    fields are all present. `None` = the owner has not yet finished the mandatory setup wizard
    (`requireOnboardedLegalEntity` on the frontend redirects there until this is set)."""
    trial_starts_at: datetime | None
    trial_ends_at: datetime | None
    """ADR-0010: the 5-day free-trial window, started atomically with
    `onboarding_completed_at` -- `(None, None)` before onboarding, both set together, never
    independently. Public visibility during the trial is decided by the
    `subscription_entitlement_projection` row `complete_onboarding` writes alongside this field,
    not by comparing `trial_ends_at` to `now` at every read site -- this pair exists for display
    ("N kun qoldi") and for the trial-expiry sweep worker's own query, not as a second source of
    truth for entitlement."""
    created_at: datetime
    updated_at: datetime
    lock_version: int = 0
    promo_video_media_asset_ids: tuple[UUID, ...] = ()
    """Additive (landing-page promo-video business rule): unlike `portfolio`, these have no
    caption/position -- just an ordered (append-order) list of media references, capped at
    `MAX_PROMO_VIDEOS`. `create()` does not list this explicitly; it uses this default, same as
    `lock_version` above."""
    main_category: MainCategory | None = None
    """Additive (Organizations Main-Category task): the sector tab this profile appears under on
    the public `/companies` directory. `None` on the handful of profiles that pre-date this field
    (never backfilled -- they simply appear in no category tab, per the field's own read-side
    filter). The onboarding wizard treats this as mandatory going forward
    (`complete_onboarding` below refuses to finish without it for any profile still `None`), but
    it is not a NOT NULL column -- see the migration's own docstring for why."""
    sub_category: SubCategory | None = None
    """Additive (Organizations Sub-Category task): a finer classification within `main_category`
    (`SUB_CATEGORIES_BY_MAIN_CATEGORY`), backing the public directory's secondary filter dropdown
    and card chip. Unlike `main_category`, always optional -- never required by onboarding, and
    `update_details` validates it against whatever `main_category` the profile has (current or
    newly-set in the same call), not the other way around."""
    finance_offer_details: LocalizedText | None = None
    """Additive (ADR-0012, B2B Directory professional-upgrade task, site-owner spec: "Bank/Finans
    bloki"): free-text ipoteka/kredit terms shown on the landing page, only ever rendered by
    `interfaces/` when `main_category is MainCategory.FINANCE_MORTGAGE` -- the domain layer does
    not itself enforce that restriction (a profile that later changes sector keeps whatever text
    it had, simply unrendered), matching `description`'s own "no cross-field validation" shape."""
    promo_video_youtube_url: str | None = None
    """Additive (ADR-0012): an external YouTube URL, alongside (not replacing) the existing
    uploaded `promo_video_media_asset_ids` -- host-validated by `application.ProfileUseCases.
    update_landing_extras` (a fact about the URL string, not something this aggregate re-checks),
    mirroring `add_promo_video`'s own "validation lives one layer up" split."""

    # --- factory (FR-PROF-001) ------------------------------------------------------------------

    @staticmethod
    def create(
        *,
        profile_id: BusinessProfileId,
        owner_user_id: UserId,
        profile_type: ProfileType,
        name: LocalizedText,
        description: LocalizedText | None,
        contacts: dict[str, Any] | None,
        address: str | None,
        slug: str,
        now: datetime,
        main_category: MainCategory | None = None,
        sub_category: SubCategory | None = None,
    ) -> BusinessProfile:
        """Always produces `CREATED` (see `value_objects.ProfileStatus`'s own docstring --
        `application.ProfileUseCases.create_profile` immediately composes `.submit_for_review()`,
        ADR-0012)."""
        _require_valid_sub_category(main_category, sub_category)
        return BusinessProfile(
            id=profile_id,
            owner_user_id=owner_user_id,
            profile_type=profile_type,
            name=name,
            description=description,
            contacts=contacts or {},
            address=address,
            slug=slug,
            status=ProfileStatus.CREATED,
            badge=None,
            portfolio=(),
            logo_media_asset_id=None,
            banner_media_asset_id=None,
            onboarding_completed_at=None,
            trial_starts_at=None,
            trial_ends_at=None,
            created_at=now,
            updated_at=now,
            main_category=main_category,
            sub_category=sub_category,
        )

    # --- lifecycle (Created -> PendingReview -> Active -> Archived; PendingReview <-> Rejected) ---

    def submit_for_review(self, *, now: datetime) -> BusinessProfile:
        """ADR-0012: `application.ProfileUseCases.create_profile` composes this immediately after
        `create()`, same "two recorded transitions, one request" shape the old `activate()` call
        used, but landing on `PENDING_REVIEW` instead of `ACTIVE` -- a new company is invisible on
        the public directory/landing page (see `ProfileUseCases.get_public_profile_by_slug`/
        `list_public_profiles`) until a reviewer decides it via `decide_registration`."""
        if self.status is not ProfileStatus.CREATED:
            raise IllegalProfileStatusTransitionError("submit_for_review", self.status.value)
        return replace(self, status=ProfileStatus.PENDING_REVIEW, updated_at=now)

    def approve(self, *, now: datetime) -> BusinessProfile:
        """ADR-0012: the reviewer's approval decision (`decide_registration`, outcome=APPROVED).
        Legal only from `PENDING_REVIEW` -- an already-`ACTIVE` profile, or one that was never
        submitted, cannot be approved again."""
        if self.status is not ProfileStatus.PENDING_REVIEW:
            raise IllegalProfileStatusTransitionError("approve", self.status.value)
        return replace(self, status=ProfileStatus.ACTIVE, updated_at=now)

    def reject(self, *, now: datetime) -> BusinessProfile:
        """ADR-0012: the reviewer's rejection decision (`decide_registration`, outcome=REJECTED).
        The rejection `reason` itself is not stored on the aggregate (mirrors
        `VerificationCase.decide`'s own `Decision` VO living on the *case*, not the profile) --
        it travels only in the `BusinessProfileRejected` event payload. Not terminal: editing a
        `REJECTED` profile (`update_details`) automatically resubmits it (`PENDING_REVIEW`)."""
        if self.status is not ProfileStatus.PENDING_REVIEW:
            raise IllegalProfileStatusTransitionError("reject", self.status.value)
        return replace(self, status=ProfileStatus.REJECTED, updated_at=now)

    def archive(self, *, now: datetime) -> BusinessProfile:
        """FR-PROF (moderation-invoked or owner-invoked archival). Legal from `ACTIVE` only --
        `ARCHIVED` is terminal (Database Architecture: "owner closure/suspension follow-through");
        an already-`ARCHIVED` profile archiving again, or archiving a still-`CREATED`/
        `PENDING_REVIEW`/`REJECTED` one, all raise."""
        if self.status is not ProfileStatus.ACTIVE:
            raise IllegalProfileStatusTransitionError("archive", self.status.value)
        return replace(self, status=ProfileStatus.ARCHIVED, updated_at=now)

    def update_details(
        self,
        *,
        name: LocalizedText | None = None,
        description: LocalizedText | None = None,
        contacts: dict[str, Any] | None = None,
        address: str | None = None,
        main_category: MainCategory | None = None,
        sub_category: SubCategory | None = None,
        now: datetime,
    ) -> BusinessProfile:
        """`updateBusinessProfile`: "profileType is immutable" (OpenAPI's own docstring) -- no
        parameter here can touch it. Refused once `ARCHIVED` (nothing to maintain on a closed
        profile); legal in `CREATED`, `PENDING_REVIEW`, `ACTIVE`, or `REJECTED`. `main_category`,
        like the others, is "unchanged if omitted" -- there is no way to clear it back to `None`
        once set, matching that it is a one-way mandatory-onboarding field, not a nullable
        preference. `sub_category` is validated against whichever `main_category` this call ends
        up with (the newly-passed one if given, else the profile's existing one).

        ADR-0012: editing a `REJECTED` profile automatically resubmits it (`PENDING_REVIEW`) --
        the owner's normal "fix what the reviewer flagged" edit is itself the resubmit action, no
        separate endpoint needed. Every other status is unaffected by this call."""
        if self.status is ProfileStatus.ARCHIVED:
            raise IllegalProfileStatusTransitionError("update_details", self.status.value)
        effective_main_category = main_category if main_category is not None else self.main_category
        effective_sub_category = sub_category if sub_category is not None else self.sub_category
        _require_valid_sub_category(effective_main_category, effective_sub_category)
        return replace(
            self,
            name=name if name is not None else self.name,
            description=description if description is not None else self.description,
            contacts=contacts if contacts is not None else self.contacts,
            address=address if address is not None else self.address,
            main_category=effective_main_category,
            sub_category=effective_sub_category,
            status=ProfileStatus.PENDING_REVIEW
            if self.status is ProfileStatus.REJECTED
            else self.status,
            updated_at=now,
        )

    def update_branding(
        self,
        *,
        logo_media_asset_id: UUID | None,
        banner_media_asset_id: UUID | None,
        now: datetime,
    ) -> BusinessProfile:
        """Sets the landing page's logo/banner. Unlike `update_details`, both parameters are
        plain optional values applied verbatim (not "unchanged if omitted") -- the owner clears
        one by sending `null`, mirroring `remove_portfolio_item`'s explicit-removal shape rather
        than `update_details`'s partial-patch one, since there is exactly one of each here (no
        list to add/remove from)."""
        if self.status is ProfileStatus.ARCHIVED:
            raise IllegalProfileStatusTransitionError("update_branding", self.status.value)
        return replace(
            self,
            logo_media_asset_id=logo_media_asset_id,
            banner_media_asset_id=banner_media_asset_id,
            updated_at=now,
        )

    def update_landing_extras(
        self,
        *,
        finance_offer_details: LocalizedText | None,
        promo_video_youtube_url: str | None,
        now: datetime,
    ) -> BusinessProfile:
        """ADR-0012: the finance/mortgage-terms block and the YouTube promo-video link -- verbatim
        apply (clears on `None`), mirroring `update_branding`'s shape exactly rather than
        `update_details`'s partial-patch one, for the same reason: one field each, no list to
        add/remove from."""
        if self.status is ProfileStatus.ARCHIVED:
            raise IllegalProfileStatusTransitionError("update_landing_extras", self.status.value)
        return replace(
            self,
            finance_offer_details=finance_offer_details,
            promo_video_youtube_url=promo_video_youtube_url,
            updated_at=now,
        )

    # --- badge lifecycle (I-13; FR-PROF-006/007) --------------------------------------------------

    def issue_badge(
        self, *, proof: ApprovedVerificationProof, valid_until: datetime, now: datetime
    ) -> BusinessProfile:
        """I-13's structural guard: `proof` can only exist if it was built from an `APPROVED`
        `VerificationCase` (`verification_case.ApprovedVerificationProof.from_case`) for THIS
        profile -- `NotProfileOwnerError`-shaped defence-in-depth against a caller passing a
        mismatched proof is `application.VerificationUseCases.decide_verification`'s job (it
        already only ever builds `proof` from the one case it just loaded for this exact
        profile); this method still checks the id match as a second, cheap guard. `valid_until`
        is supplied by the caller, computed from the entitlement's own validity window (DDD Sec
        5.2 `BadgeIssuanceService`: "computes validity period from the configured verification
        product terms" -- transitively, via the entitlement's `valid_until`, since profiles
        cannot import `configuration` directly, SAD Sec 8.1). Legal from ANY current badge
        state (`None`/`EXPIRED`/`REVOKED`/even `VALID`, re-verification while still valid) --
        re-verification's own constraint (never editing a terminal *case*) is enforced on
        `VerificationCase`, not here."""
        if proof.business_profile_id != self.id:
            raise IllegalBadgeTransitionError("issue_badge", "mismatched profile")
        badge = VerifiedBadge(status=BadgeStatus.VALID, issued_at=now, valid_until=valid_until)
        return replace(self, badge=badge, updated_at=now)

    def expire_badge(self, *, now: datetime) -> BusinessProfile:
        """FR-PROF-006/007: the expiry sweep worker's own transition. Legal only from `VALID`."""
        if self.badge is None or self.badge.status is not BadgeStatus.VALID:
            raise IllegalBadgeTransitionError(
                "expire_badge", self.badge.status.value if self.badge else None
            )
        badge = replace(self.badge, status=BadgeStatus.EXPIRED)
        return replace(self, badge=badge, updated_at=now)

    def revoke_badge(self, *, now: datetime) -> BusinessProfile:
        """The moderation-invoked command (P-11 scope: "e.g. following a moderation action");
        exposed via `interfaces/moderation_port.py`, mirroring `catalog.domain.listing.Listing.
        unflag`'s own "moderation command port's method" precedent. Legal only from `VALID` --
        an already-`EXPIRED`/`REVOKED`/never-issued badge cannot be revoked again."""
        if self.badge is None or self.badge.status is not BadgeStatus.VALID:
            raise IllegalBadgeTransitionError(
                "revoke_badge", self.badge.status.value if self.badge else None
            )
        badge = replace(self.badge, status=BadgeStatus.REVOKED)
        return replace(self, badge=badge, updated_at=now)

    # --- portfolio (FR-PROF-002; ordered, <=50) ---------------------------------------------------

    def add_portfolio_item(
        self,
        *,
        item_id: UUID,
        media_asset_id: UUID,
        caption: LocalizedText | None,
        now: datetime,
    ) -> BusinessProfile:
        if len(self.portfolio) >= MAX_PORTFOLIO_ITEMS:
            raise PortfolioItemLimitExceededError(MAX_PORTFOLIO_ITEMS)
        item = PortfolioItem(
            id=item_id,
            media_asset_id=media_asset_id,
            position=len(self.portfolio) + 1,
            caption=caption,
            created_at=now,
        )
        return replace(self, portfolio=(*self.portfolio, item), updated_at=now)

    def remove_portfolio_item(self, item_id: UUID, *, now: datetime) -> BusinessProfile:
        if not any(item.id == item_id for item in self.portfolio):
            raise PortfolioItemNotFoundError(item_id)
        remaining = tuple(item for item in self.portfolio if item.id != item_id)
        renumbered = tuple(
            replace(item, position=index + 1) for index, item in enumerate(remaining)
        )
        return replace(self, portfolio=renumbered, updated_at=now)

    # --- promo video (landing-page promo-video business rule, additive) ------------------------

    def add_promo_video(self, *, media_asset_id: UUID, now: datetime) -> BusinessProfile:
        """Content-type/duration/scan-status checks all happen one layer up
        (`application.ProfileUseCases.add_promo_video`, which alone has read access to the
        referenced media asset's facts) -- this method's own job is only the aggregate-local
        invariant: at most `MAX_PROMO_VIDEOS`, no duplicate id."""
        if len(self.promo_video_media_asset_ids) >= MAX_PROMO_VIDEOS:
            raise PromoVideoLimitExceededError(MAX_PROMO_VIDEOS)
        if media_asset_id in self.promo_video_media_asset_ids:
            return self
        return replace(
            self,
            promo_video_media_asset_ids=(*self.promo_video_media_asset_ids, media_asset_id),
            updated_at=now,
        )

    def remove_promo_video(self, media_asset_id: UUID, *, now: datetime) -> BusinessProfile:
        if media_asset_id not in self.promo_video_media_asset_ids:
            raise PromoVideoNotFoundError(media_asset_id)
        remaining = tuple(mid for mid in self.promo_video_media_asset_ids if mid != media_asset_id)
        return replace(self, promo_video_media_asset_ids=remaining, updated_at=now)

    # --- onboarding / trial (ADR-0010) --------------------------------------------------------

    def complete_onboarding(self, *, now: datetime, trial_days: int = 5) -> BusinessProfile:
        """One-time transition (see `OnboardingAlreadyCompletedError`'s own docstring): checks
        the mandatory landing-page fields are already present on the aggregate, then starts the
        free-trial window. Does not itself touch `subscription_entitlement_projection` -- that
        write is `application.ProfileUseCases.complete_onboarding`'s job, in the same
        transaction as this call, since profiles' domain layer has no repository access
        (Clean Architecture rule 4)."""
        if self.onboarding_completed_at is not None:
            raise OnboardingAlreadyCompletedError(self.id.value)
        if not self.contacts.get("phones"):
            raise OnboardingIncompleteError("contacts.phones")
        if self.logo_media_asset_id is None:
            raise OnboardingIncompleteError("logoMediaAssetId")
        if self.description is None:
            raise OnboardingIncompleteError("description")
        if not self.address:
            raise OnboardingIncompleteError("address")
        if not self.portfolio:
            raise OnboardingIncompleteError("portfolio")
        if self.main_category is None:
            raise OnboardingIncompleteError("mainCategory")
        trial_ends_at = now + timedelta(days=trial_days)
        return replace(
            self,
            onboarding_completed_at=now,
            trial_starts_at=now,
            trial_ends_at=trial_ends_at,
            updated_at=now,
        )

    def remove_portfolio_item_for_media_asset(
        self, media_asset_id: UUID, *, now: datetime
    ) -> BusinessProfile:
        """Applies media's `MediaAssetRejected` projection (X-06) -- a no-op if no portfolio item
        currently references this asset (redelivery-safe, mirrors `verification_case.
        VerificationCase.remove_document_for_media_asset`)."""
        if not any(item.media_asset_id == media_asset_id for item in self.portfolio):
            return self
        remaining = tuple(item for item in self.portfolio if item.media_asset_id != media_asset_id)
        renumbered = tuple(
            replace(item, position=index + 1) for index, item in enumerate(remaining)
        )
        return replace(self, portfolio=renumbered, updated_at=now)
