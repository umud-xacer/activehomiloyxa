"""Domain-layer invariant tests for `profiles.domain.verification_case.VerificationCase`
(Task P-11) -- terminal-immutability, the reviewer workflow, and I-12's structural document guard.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from profiles.domain import CaseStatus, TerminalVerificationCaseError, VerificationCase
from profiles.domain.exceptions import (
    DuplicateDocumentPositionError,
    IllegalVerificationCaseStateTransitionError,
    NoDocumentsSubmittedError,
)
from profiles.domain.submitted_document import SubmittedDocument
from shared_kernel import BusinessProfileId

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _document(position: int, media_asset_id: UUID | None = None) -> SubmittedDocument:
    return SubmittedDocument(
        id=uuid4(),
        media_asset_id=media_asset_id or uuid4(),
        document_kind="business_license",
        position=position,
        created_at=NOW,
    )


def _new_case(**overrides: object) -> VerificationCase:
    defaults: dict[str, object] = {
        "case_id": uuid4(),
        "business_profile_id": BusinessProfileId(value=uuid4()),
        "entitlement_id": uuid4(),
        "documents": (_document(1),),
        "sla_due_at": NOW + timedelta(hours=72),
        "now": NOW,
    }
    defaults.update(overrides)
    return VerificationCase.create(**defaults)  # type: ignore[arg-type]


# --- I-12: requires submitted documents before entering the queue -----------------------------


def test_I12_create_refuses_zero_documents() -> None:
    with pytest.raises(NoDocumentsSubmittedError):
        _new_case(documents=())


def test_create_refuses_non_contiguous_document_positions() -> None:
    with pytest.raises(DuplicateDocumentPositionError):
        _new_case(documents=(_document(1), _document(3)))


def test_create_produces_requested_status() -> None:
    case = _new_case()
    assert case.status is CaseStatus.REQUESTED
    assert case.decision is None


# --- reviewer workflow (FR-PROF-005) ------------------------------------------------------------


def test_mark_in_review_from_requested() -> None:
    case = _new_case().mark_in_review(now=NOW)
    assert case.status is CaseStatus.IN_REVIEW


def test_mark_in_review_twice_is_illegal() -> None:
    case = _new_case().mark_in_review(now=NOW)
    with pytest.raises(IllegalVerificationCaseStateTransitionError):
        case.mark_in_review(now=NOW)


def test_decide_approved_from_requested_directly() -> None:
    case = _new_case().decide(
        outcome=CaseStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW
    )
    assert case.status is CaseStatus.APPROVED
    assert case.decision is not None
    assert case.decision.outcome is CaseStatus.APPROVED


def test_decide_approved_from_in_review() -> None:
    case = _new_case().mark_in_review(now=NOW)
    decided = case.decide(
        outcome=CaseStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW
    )
    assert decided.status is CaseStatus.APPROVED


def test_decide_rejected_records_reason() -> None:
    case = _new_case().decide(
        outcome=CaseStatus.REJECTED, reason="documents illegible", reviewer_user_id=uuid4(), now=NOW
    )
    assert case.status is CaseStatus.REJECTED
    assert case.decision is not None
    assert case.decision.reason == "documents illegible"


# --- terminal-immutability: Approved/Rejected are TERMINAL and IMMUTABLE ----------------------


@pytest.mark.parametrize("outcome", [CaseStatus.APPROVED, CaseStatus.REJECTED])
def test_terminal_case_cannot_be_reopened(outcome: CaseStatus) -> None:
    case = _new_case().decide(outcome=outcome, reason=None, reviewer_user_id=uuid4(), now=NOW)
    with pytest.raises(TerminalVerificationCaseError):
        case.mark_in_review(now=NOW)


@pytest.mark.parametrize("outcome", [CaseStatus.APPROVED, CaseStatus.REJECTED])
def test_terminal_case_cannot_be_decided_again(outcome: CaseStatus) -> None:
    case = _new_case().decide(outcome=outcome, reason=None, reviewer_user_id=uuid4(), now=NOW)
    with pytest.raises(TerminalVerificationCaseError):
        case.decide(outcome=CaseStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW)


@pytest.mark.parametrize("outcome", [CaseStatus.APPROVED, CaseStatus.REJECTED])
def test_terminal_case_document_removal_is_a_noop_not_an_edit(outcome: CaseStatus) -> None:
    """`remove_document_for_media_asset` (the media-status-rejection projection) must never edit
    a terminal case's own audit record -- a no-op, not an exception, matching the projection's
    own idempotent-consumer discipline."""
    media_asset_id = uuid4()
    case = _new_case(documents=(_document(1, media_asset_id),)).decide(
        outcome=outcome, reason=None, reviewer_user_id=uuid4(), now=NOW
    )
    unchanged = case.remove_document_for_media_asset(media_asset_id, now=NOW + timedelta(hours=1))
    assert unchanged is case
    assert len(unchanged.documents) == 1


def test_reverification_creates_a_new_case_never_mutates_the_old_one() -> None:
    profile_id = BusinessProfileId(value=uuid4())
    first_case = _new_case(business_profile_id=profile_id).decide(
        outcome=CaseStatus.REJECTED, reason="incomplete", reviewer_user_id=uuid4(), now=NOW
    )
    second_case = _new_case(business_profile_id=profile_id, entitlement_id=uuid4())

    assert second_case.id != first_case.id
    assert first_case.status is CaseStatus.REJECTED
    assert second_case.status is CaseStatus.REQUESTED


# --- non-terminal document removal (X-06 media-status projection) ------------------------------


def test_non_terminal_document_removal_renumbers_remaining() -> None:
    media_asset_id = uuid4()
    case = _new_case(documents=(_document(1, media_asset_id), _document(2)))
    updated = case.remove_document_for_media_asset(media_asset_id, now=NOW)
    assert len(updated.documents) == 1
    assert updated.documents[0].position == 1


def test_document_removal_for_absent_asset_is_a_noop() -> None:
    case = _new_case()
    unchanged = case.remove_document_for_media_asset(uuid4(), now=NOW)
    assert unchanged is case
