"""analytics/application -- `ReportUseCases` (FR-ADMIN-005, BRULE-20). Backs
`GET /admin/reports` (operationId `getAdminReports`). Every dataset is computed purely from
analytics' own two fact streams (`AuditEntry`/`MetricEvent`) -- analytics never dereferences a
ref by calling another module (Absolute Architecture Rule 1), so a report can only ever reflect
what those two streams actually carry.

The five report keys are `contracts/openapi.yaml`'s own already-frozen closed `report` enum
(`getAdminReports`'s `report` query parameter) -- this use case does not invent a sixth.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Literal

from analytics.application.exceptions import UnknownReportError
from analytics.application.ports import AuditEntryRepository, MetricEventRepository
from analytics.domain import MetricKey

ReportKey = Literal[
    "LISTINGS_OVERVIEW",
    "USER_GROWTH",
    "REVENUE",
    "VERIFICATION_SLA",
    "MODERATION_THROUGHPUT",
]

_LISTING_ENGAGEMENT_KEYS: tuple[MetricKey, ...] = (
    MetricKey.LISTING_VIEWED,
    MetricKey.CONTACT_BUTTON_CLICKED,
    MetricKey.PHONE_REVEALED,
    MetricKey.CHAT_INITIATED,
    MetricKey.FAVORITE_ADDED,
    MetricKey.PREMIUM_LISTING_STAT,
    # UNF-030: BRULE-20/BC-13 define a closed set of EIGHT metric keys; this tuple only ever
    # enumerated six, so LISTINGS_OVERVIEW silently omitted the two banner metrics from its
    # `counts` map even though `analytics/infrastructure/event_projection.py` already projects
    # both (`BannerImpressionRecorded`/`BannerClickRecorded`) into `MetricEvent` rows.
    MetricKey.BANNER_IMPRESSION_RECORDED,
    MetricKey.BANNER_CLICK_RECORDED,
)


class ReportUseCases:
    def __init__(
        self, *, audit_entries: AuditEntryRepository, metrics: MetricEventRepository
    ) -> None:
        self._audit_entries = audit_entries
        self._metrics = metrics

    async def get_admin_reports(
        self,
        *,
        report: str,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> dict[str, Any]:
        if report == "LISTINGS_OVERVIEW":
            return await self._listings_overview(occurred_from, occurred_to)
        if report == "USER_GROWTH":
            return self._user_growth(occurred_from, occurred_to)
        if report == "REVENUE":
            return await self._revenue(occurred_from, occurred_to)
        if report == "VERIFICATION_SLA":
            return await self._verification_sla(occurred_from, occurred_to)
        if report == "MODERATION_THROUGHPUT":
            return await self._moderation_throughput(occurred_from, occurred_to)
        raise UnknownReportError(report)

    async def _listings_overview(
        self, occurred_from: datetime | None, occurred_to: datetime | None
    ) -> dict[str, Any]:
        events = await self._metrics.list_for_report(
            metric_keys=_LISTING_ENGAGEMENT_KEYS,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        counts = Counter(event.metric_key.value for event in events)
        return {
            "report": "LISTINGS_OVERVIEW",
            "from": occurred_from.isoformat() if occurred_from else None,
            "to": occurred_to.isoformat() if occurred_to else None,
            "counts": {key.value: counts.get(key.value, 0) for key in _LISTING_ENGAGEMENT_KEYS},
            "total": len(events),
        }

    def _user_growth(
        self, occurred_from: datetime | None, occurred_to: datetime | None
    ) -> dict[str, Any]:
        """No data source: `UserRegistered` is neither an administrative/moderation/configuration
        action (I-22's own audit scope) nor one of the eight closed metric-vocabulary keys
        (I-23), so analytics never ingests it. Returns an honest empty dataset rather than a
        fabricated count -- see `analytics/README.md` "Known gaps"."""
        return {
            "report": "USER_GROWTH",
            "from": occurred_from.isoformat() if occurred_from else None,
            "to": occurred_to.isoformat() if occurred_to else None,
            "available": False,
            "reason": (
                "UserRegistered is not an audited administrative action (I-22) nor a closed-"
                "vocabulary metric (I-23); no data source exists for this report in v1"
            ),
        }

    async def _revenue(
        self, occurred_from: datetime | None, occurred_to: datetime | None
    ) -> dict[str, Any]:
        entries = await self._audit_entries.list_for_report(
            actions=("PaymentConfirmed",), occurred_from=occurred_from, occurred_to=occurred_to
        )
        totals: dict[str, float] = {}
        for entry in entries:
            amount = entry.payload.get("amount")
            currency = entry.payload.get("currency")
            if amount is None or currency is None:
                continue
            totals[currency] = totals.get(currency, 0.0) + float(amount)
        return {
            "report": "REVENUE",
            "from": occurred_from.isoformat() if occurred_from else None,
            "to": occurred_to.isoformat() if occurred_to else None,
            "confirmedPayments": len(entries),
            "totalsByCurrency": totals,
        }

    async def _verification_sla(
        self, occurred_from: datetime | None, occurred_to: datetime | None
    ) -> dict[str, Any]:
        """Decision throughput, not request-to-decision latency: `VerificationRequested` (the
        submission side) is a self-service profile-owner action, not an administrative one under
        I-22's own scope, so it is never an audited fact and no "time to decide" duration is
        computable from analytics' own data alone."""
        entries = await self._audit_entries.list_for_report(
            actions=("BusinessVerified", "VerificationRejected"),
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        approved = sum(1 for e in entries if e.action == "BusinessVerified")
        rejected = sum(1 for e in entries if e.action == "VerificationRejected")
        return {
            "report": "VERIFICATION_SLA",
            "from": occurred_from.isoformat() if occurred_from else None,
            "to": occurred_to.isoformat() if occurred_to else None,
            "decisions": len(entries),
            "approved": approved,
            "rejected": rejected,
        }

    async def _moderation_throughput(
        self, occurred_from: datetime | None, occurred_to: datetime | None
    ) -> dict[str, Any]:
        entries = await self._audit_entries.list_for_report(
            actions=("ModerationActionTaken",), occurred_from=occurred_from, occurred_to=occurred_to
        )
        by_verb = Counter(str(e.payload.get("action", "UNKNOWN")) for e in entries)
        return {
            "report": "MODERATION_THROUGHPUT",
            "from": occurred_from.isoformat() if occurred_from else None,
            "to": occurred_to.isoformat() if occurred_to else None,
            "actionsTaken": len(entries),
            "byVerb": dict(by_verb),
        }
