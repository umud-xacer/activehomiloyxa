"""Proves contracts/events/ covers exactly the Domain Model Sec 6 event catalogue, as amended by
ADR-0001 and ADR-0005 -- no event missing, no event invented (P-01 validation checklist).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from contracts.events import EVENT_CATALOGUE
from shared_kernel import EventEnvelope

# Transcribed directly from DDD Sec 6's table (Context | Event | Emitted when | Principal
# consumers), enumerating every "/"-separated event name in the "Event" column, PLUS the three
# BC-06 events ADR-0001 (docs/adr/0001-media-asset-status-events.md) adds: DDD Sec 6's published
# table has no BC-06 row at all (a gap `contracts/README.md` recorded explicitly under Task
# P-01); ADR-0001 resolves it, pending the human-governance re-versioning step Playbook Sec 18
# describes ("agents may draft, never ratify"). This is the independent oracle the generated
# registry is checked against.
DDD_SEC_6_EVENT_NAMES = {
    # BC-01
    "UserRegistered",
    "AccountSuspended",
    "AccountClosed",
    # BC-02
    "BusinessProfileCreated",
    "VerificationRequested",
    "BusinessVerified",
    "VerificationRejected",
    "VerifiedBadgeExpired",
    # BC-03
    "ListingCreated",
    "ListingDraftSaved",
    "ListingPublished",
    "ListingEdited",
    "ListingSuspended",
    "ListingArchived",
    "ListingDeleted",
    "ListingExpired",
    "ListingRenewed",
    "ListingFlagged",
    "FavoriteAdded",
    "FavoriteRemoved",
    # BC-03 (ADR-0005 -- absent from DDD Sec 6's published table despite Sec 5.13's own 8-key
    # closed metric vocabulary naming them; no real producer wired yet)
    "ListingViewed",
    "ContactButtonClicked",
    "PremiumListingStat",
    # BC-06 (ADR-0001 -- absent from DDD Sec 6's published table)
    "MediaAssetAccepted",
    "MediaAssetReady",
    "MediaAssetRejected",
    # BC-04
    "ConfigurationChanged",
    "CategoryCreated",
    "CategoryChanged",
    "CategoryRetired",
    "FormDefinitionPublished",
    "ProductDefinitionChanged",
    "PlacementSlotDefined",
    "RoleDefinitionChanged",
    "SearchConfigurationChanged",
    "NotificationTemplateChanged",
    "PlatformSettingsChanged",
    # BC-08
    "OrderPlaced",
    "InvoiceIssued",
    "PaymentConfirmed",
    "EntitlementActivated",
    "EntitlementExpired",
    "EntitlementRevoked",
    # BC-09
    "BannerCampaignScheduled",
    "BannerCampaignStarted",
    "BannerCampaignEnded",
    "BannerImpressionRecorded",
    "BannerClickRecorded",
    # BC-07
    "ChatInitiated",
    "MessageSent",
    "UserBlocked",
    "PhoneRevealed",
    # BC-07 / BC-03
    "ContentReported",
    # BC-11
    "ModerationActionTaken",
    # BC-13 (sink)
    "MetricEventCaptured",
    "AuditEntryRecorded",
}


def test_I01_event_catalogue_matches_ddd_sec_6_exactly() -> None:
    """# enforces DDD Sec 6 "the authoritative v1 event catalogue", as amended by ADR-0001 and
    ADR-0005."""
    assert set(EVENT_CATALOGUE.keys()) == DDD_SEC_6_EVENT_NAMES
    assert len(DDD_SEC_6_EVENT_NAMES) == 56


def test_I02_every_event_class_pins_its_own_event_type() -> None:
    for name, cls in EVENT_CATALOGUE.items():
        assert cls.model_fields["event_type"].default == name


def test_I03_every_event_class_carries_the_full_shared_envelope() -> None:
    """# enforces DDD Sec 5.14 (event id, type, occurred-at, actor, aggregate ref, version)."""
    envelope_fields = set(EventEnvelope.model_fields.keys())
    assert envelope_fields == {
        "event_id",
        "event_type",
        "occurred_at",
        "actor",
        "aggregate_type",
        "aggregate_id",
        "aggregate_version",
        "payload",
    }
    for cls in EVENT_CATALOGUE.values():
        assert envelope_fields.issubset(cls.model_fields.keys())


def test_I04_event_instantiates_with_only_envelope_fields() -> None:
    """A representative event from each family constructs with nothing but envelope data --
    proves there is no invented, undocumented required payload field."""
    for cls in EVENT_CATALOGUE.values():
        # every concrete member of the catalogue pins its own default for `event_type` (proven
        # by test_I02 above); mypy can't see that through the generic `type[EventEnvelope]`
        # value type, since the base class itself declares `event_type` as required.
        instance = cls(  # type: ignore[call-arg]
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            aggregate_type="TestAggregate",
            aggregate_id=uuid4(),
            payload={},
        )
        assert instance.actor is None
        assert instance.aggregate_version is None
