"""Domain-layer invariant tests for `profiles.domain.business_profile.BusinessProfile`
(Task P-11). Named `test_I<nn>_*` for every invariant DDD Sec 9 assigns to profiles, mirroring
`apps/backend/tests/catalog/test_listing.py`'s own convention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from profiles.domain import (
    ApprovedVerificationProof,
    BadgeStatus,
    BusinessProfile,
    CaseStatus,
    IllegalBadgeTransitionError,
    IllegalProfileStatusTransitionError,
    PortfolioItemLimitExceededError,
    PortfolioItemNotFoundError,
    ProfileStatus,
    ProfileType,
    VerificationCase,
)
from profiles.domain.submitted_document import SubmittedDocument
from shared_kernel import BusinessProfileId, LocalizedText, UserId

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

ALL_EIGHT_TYPES = (
    ProfileType.CONSTRUCTION_COMPANY,
    ProfileType.MANUFACTURER,
    ProfileType.BUILDER,
    ProfileType.SUPPLIER,
    ProfileType.CONTRACTOR,
    ProfileType.ARCHITECT,
    ProfileType.INTERIOR_DESIGNER,
    ProfileType.SERVICE_PROVIDER,
)


def _new_profile(**overrides: object) -> BusinessProfile:
    defaults: dict[str, object] = {
        "profile_id": BusinessProfileId(value=uuid4()),
        "owner_user_id": UserId(value=uuid4()),
        "profile_type": ProfileType.CONSTRUCTION_COMPANY,
        "name": LocalizedText(uz_latn="Test Co", ru="Тест Ко"),
        "description": None,
        "contacts": None,
        "address": None,
        "slug": "test-co-123",
        "now": NOW,
    }
    defaults.update(overrides)
    return BusinessProfile.create(**defaults)  # type: ignore[arg-type]


def _approved_case(
    profile_id: BusinessProfileId, *, entitlement_id: UUID | None = None
) -> VerificationCase:
    case = VerificationCase.create(
        case_id=uuid4(),
        business_profile_id=profile_id,
        entitlement_id=entitlement_id or uuid4(),
        documents=(
            SubmittedDocument(
                id=uuid4(),
                media_asset_id=uuid4(),
                document_kind="license",
                position=1,
                created_at=NOW,
            ),
        ),
        sla_due_at=NOW + timedelta(hours=72),
        now=NOW,
    )
    return case.decide(outcome=CaseStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW)


# --- all-eight-types (closed vocabulary) ----------------------------------------------------


@pytest.mark.parametrize("profile_type", ALL_EIGHT_TYPES)
def test_all_eight_profile_types_can_be_created(profile_type: ProfileType) -> None:
    profile = _new_profile(profile_type=profile_type)
    assert profile.profile_type is profile_type
    assert profile.status is ProfileStatus.CREATED


def test_a_ninth_invalid_profile_type_is_refused() -> None:
    with pytest.raises(ValueError):
        ProfileType("REAL_ESTATE_AGENCY")


# --- lifecycle: Created -> Active -> Archived ------------------------------------------------


def test_create_produces_created_status() -> None:
    profile = _new_profile()
    assert profile.status is ProfileStatus.CREATED
    assert profile.badge is None


def test_activate_created_moves_to_active() -> None:
    profile = _new_profile().activate(now=NOW)
    assert profile.status is ProfileStatus.ACTIVE


def test_activate_twice_is_illegal() -> None:
    profile = _new_profile().activate(now=NOW)
    with pytest.raises(IllegalProfileStatusTransitionError):
        profile.activate(now=NOW)


def test_archive_active_moves_to_archived() -> None:
    profile = _new_profile().activate(now=NOW).archive(now=NOW)
    assert profile.status is ProfileStatus.ARCHIVED


def test_archive_created_is_illegal() -> None:
    with pytest.raises(IllegalProfileStatusTransitionError):
        _new_profile().archive(now=NOW)


def test_archive_archived_is_illegal() -> None:
    profile = _new_profile().activate(now=NOW).archive(now=NOW)
    with pytest.raises(IllegalProfileStatusTransitionError):
        profile.archive(now=NOW)


def test_update_details_refused_once_archived() -> None:
    profile = _new_profile().activate(now=NOW).archive(now=NOW)
    with pytest.raises(IllegalProfileStatusTransitionError):
        profile.update_details(name=LocalizedText(uz_latn="New"), now=NOW)


# --- I-13: a verified badge exists only from an approved case ---------------------------------


def test_I13_approving_a_case_issues_the_badge() -> None:
    profile = _new_profile().activate(now=NOW)
    case = _approved_case(profile.id)
    proof = ApprovedVerificationProof.from_case(case)
    badged = profile.issue_badge(proof=proof, valid_until=NOW + timedelta(days=365), now=NOW)
    assert badged.badge is not None
    assert badged.badge.status is BadgeStatus.VALID
    assert badged.badge.issued_at == NOW


def test_I13_no_code_path_sets_a_badge_valid_without_an_approved_case() -> None:
    """Negative half of I-13: attempting to construct the one and only "proof of approval" type
    from a non-approved case must refuse -- there is no other way to call
    `BusinessProfile.issue_badge`."""
    profile = _new_profile().activate(now=NOW)

    for status_case in (
        VerificationCase.create(
            case_id=uuid4(),
            business_profile_id=profile.id,
            entitlement_id=uuid4(),
            documents=(
                SubmittedDocument(
                    id=uuid4(),
                    media_asset_id=uuid4(),
                    document_kind="license",
                    position=1,
                    created_at=NOW,
                ),
            ),
            sla_due_at=NOW + timedelta(hours=72),
            now=NOW,
        ),
        VerificationCase.create(
            case_id=uuid4(),
            business_profile_id=profile.id,
            entitlement_id=uuid4(),
            documents=(
                SubmittedDocument(
                    id=uuid4(),
                    media_asset_id=uuid4(),
                    document_kind="license",
                    position=1,
                    created_at=NOW,
                ),
            ),
            sla_due_at=NOW + timedelta(hours=72),
            now=NOW,
        ).decide(outcome=CaseStatus.REJECTED, reason="bad docs", reviewer_user_id=uuid4(), now=NOW),
    ):
        from profiles.domain.exceptions import BadgeNotIssuableWithoutApprovedCaseError

        with pytest.raises(BadgeNotIssuableWithoutApprovedCaseError):
            ApprovedVerificationProof.from_case(status_case)


def test_I13_issue_badge_refuses_a_proof_for_a_different_profile() -> None:
    profile = _new_profile().activate(now=NOW)
    other_profile_id = BusinessProfileId(value=uuid4())
    case = _approved_case(other_profile_id)
    proof = ApprovedVerificationProof.from_case(case)
    with pytest.raises(IllegalBadgeTransitionError):
        profile.issue_badge(proof=proof, valid_until=NOW + timedelta(days=365), now=NOW)


# --- badge lifecycle: Valid -> Expired / Revoked -----------------------------------------------


def test_expire_badge_from_valid() -> None:
    profile = _new_profile().activate(now=NOW)
    case = _approved_case(profile.id)
    proof = ApprovedVerificationProof.from_case(case)
    badged = profile.issue_badge(proof=proof, valid_until=NOW, now=NOW)
    expired = badged.expire_badge(now=NOW + timedelta(days=1))
    assert expired.badge is not None
    assert expired.badge.status is BadgeStatus.EXPIRED


def test_expire_badge_without_a_badge_is_illegal() -> None:
    profile = _new_profile().activate(now=NOW)
    with pytest.raises(IllegalBadgeTransitionError):
        profile.expire_badge(now=NOW)


def test_revoke_badge_from_valid() -> None:
    profile = _new_profile().activate(now=NOW)
    case = _approved_case(profile.id)
    proof = ApprovedVerificationProof.from_case(case)
    badged = profile.issue_badge(proof=proof, valid_until=NOW + timedelta(days=365), now=NOW)
    revoked = badged.revoke_badge(now=NOW)
    assert revoked.badge is not None
    assert revoked.badge.status is BadgeStatus.REVOKED


def test_revoke_badge_without_a_valid_badge_is_illegal() -> None:
    profile = _new_profile().activate(now=NOW)
    with pytest.raises(IllegalBadgeTransitionError):
        profile.revoke_badge(now=NOW)

    case = _approved_case(profile.id)
    proof = ApprovedVerificationProof.from_case(case)
    expired = profile.issue_badge(proof=proof, valid_until=NOW, now=NOW).expire_badge(
        now=NOW + timedelta(days=1)
    )
    with pytest.raises(IllegalBadgeTransitionError):
        expired.revoke_badge(now=NOW)


def test_reverification_can_issue_a_fresh_badge_after_expiry() -> None:
    profile = _new_profile().activate(now=NOW)
    first_case = _approved_case(profile.id)
    proof1 = ApprovedVerificationProof.from_case(first_case)
    expired = profile.issue_badge(proof=proof1, valid_until=NOW, now=NOW).expire_badge(
        now=NOW + timedelta(days=1)
    )

    second_case = _approved_case(profile.id)
    proof2 = ApprovedVerificationProof.from_case(second_case)
    revalidated = expired.issue_badge(
        proof=proof2, valid_until=NOW + timedelta(days=365), now=NOW + timedelta(days=2)
    )
    assert revalidated.badge is not None
    assert revalidated.badge.status is BadgeStatus.VALID


# --- portfolio (ordered, <=50) -----------------------------------------------------------------


def test_add_portfolio_item_appends_with_sequential_position() -> None:
    profile = _new_profile().activate(now=NOW)
    profile = profile.add_portfolio_item(
        item_id=uuid4(), media_asset_id=uuid4(), caption=None, now=NOW
    )
    profile = profile.add_portfolio_item(
        item_id=uuid4(), media_asset_id=uuid4(), caption=None, now=NOW
    )
    assert [item.position for item in profile.portfolio] == [1, 2]


def test_remove_portfolio_item_renumbers_remaining() -> None:
    profile = _new_profile().activate(now=NOW)
    item_id_1, item_id_2 = uuid4(), uuid4()
    profile = profile.add_portfolio_item(
        item_id=item_id_1, media_asset_id=uuid4(), caption=None, now=NOW
    )
    profile = profile.add_portfolio_item(
        item_id=item_id_2, media_asset_id=uuid4(), caption=None, now=NOW
    )
    profile = profile.remove_portfolio_item(item_id_1, now=NOW)
    assert len(profile.portfolio) == 1
    assert profile.portfolio[0].id == item_id_2
    assert profile.portfolio[0].position == 1


def test_remove_nonexistent_portfolio_item_raises() -> None:
    profile = _new_profile().activate(now=NOW)
    with pytest.raises(PortfolioItemNotFoundError):
        profile.remove_portfolio_item(uuid4(), now=NOW)


def test_portfolio_item_limit_enforced() -> None:
    profile = _new_profile().activate(now=NOW)
    for _ in range(50):
        profile = profile.add_portfolio_item(
            item_id=uuid4(), media_asset_id=uuid4(), caption=None, now=NOW
        )
    with pytest.raises(PortfolioItemLimitExceededError):
        profile.add_portfolio_item(item_id=uuid4(), media_asset_id=uuid4(), caption=None, now=NOW)


def test_remove_portfolio_item_for_media_asset_is_noop_if_absent() -> None:
    profile = _new_profile().activate(now=NOW)
    unchanged = profile.remove_portfolio_item_for_media_asset(uuid4(), now=NOW)
    assert unchanged is profile
