"""`messaging.application.report_use_cases.ReportUseCases` -- FR-MSG-005. Publishes
`ContentReported` only -- no aggregate/repository of messaging's own (moderation case handling is
explicitly out of this task's scope)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from messaging.application.report_use_cases import ReportUseCases
from shared_kernel import UserId

from .conftest import FakeOutbox

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def use_cases(fake_outbox: FakeOutbox) -> ReportUseCases:
    return ReportUseCases(outbox=fake_outbox)


class TestCreateReport:
    async def test_emits_content_reported_with_the_right_shape(
        self, use_cases: ReportUseCases, fake_outbox: FakeOutbox
    ) -> None:
        reporter = UserId(value=uuid4())
        subject_id = uuid4()
        await use_cases.create_report(
            reporter_id=reporter,
            subject_type="CONVERSATION",
            subject_id=subject_id,
            reason="spam",
            now=_NOW,
        )
        assert len(fake_outbox.events) == 1
        event = fake_outbox.events[0]
        assert event.event_type == "ContentReported"
        assert event.payload["subjectType"] == "CONVERSATION"
        assert event.payload["subjectId"] == str(subject_id)
        assert event.payload["reporterUserId"] == str(reporter.value)
        assert event.payload["reason"] == "spam"

    @pytest.mark.parametrize("subject_type", ["LISTING", "CONVERSATION", "USER"])
    async def test_accepts_every_documented_subject_type(
        self, use_cases: ReportUseCases, subject_type: str
    ) -> None:
        await use_cases.create_report(
            reporter_id=UserId(value=uuid4()),
            subject_type=subject_type,  # type: ignore[arg-type]
            subject_id=uuid4(),
            reason="reason",
            now=_NOW,
        )
