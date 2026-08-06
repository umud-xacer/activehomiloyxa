"""Unit tests for `ConfigurationNotificationTemplateAdapter` against a fake of the narrow
`_ConfigurationReader` slice it actually calls -- no real Postgres needed. Mirrors
`apps/backend/tests/billing/test_configuration_adapter.py`'s pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from configuration.interfaces.dto import (
    ConfigurationHead,
    ConfigurationHeadPage,
    ConfigurationVersion,
    PageInfo,
)
from notifications.infrastructure.configuration_adapter import (
    ConfigurationNotificationTemplateAdapter,
)


@dataclass
class FakeConfigurationReader:
    """Implements `notifications.infrastructure.configuration_adapter._ConfigurationReader`."""

    heads: list[ConfigurationHead] = field(default_factory=list)
    versions: dict[UUID, ConfigurationVersion] = field(default_factory=dict)

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage:
        matching = [h for h in self.heads if h.entity_type == entity_type]
        return ConfigurationHeadPage(
            items=matching, page=PageInfo(limit=limit or 20, next_cursor=None)
        )

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        return self.versions[version_id]


def _head(*, code: str, version_id: UUID | None) -> ConfigurationHead:
    return ConfigurationHead(
        id=uuid4(),
        entity_type="notification-template",
        code=code,
        current_version_id=version_id,
        status="PUBLISHED",
    )


def _version(
    *, version_id: UUID, status: str = "PUBLISHED", snapshot: dict[str, Any] | None
) -> ConfigurationVersion:
    return ConfigurationVersion(
        id=version_id,
        head_id=uuid4(),
        version_number=1,
        status=status,  # type: ignore[arg-type]
        definition={},
        snapshot=snapshot,
    )


def _snapshot(
    *,
    event_key: str = "UserRegistered",
    channel: str = "EMAIL",
    subject: dict[str, str] | None = None,
    body: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "descriptor": {"name": {"uz_latn": "Welcome"}},
        "event_key": event_key,
        "channel": channel,
        "subject": subject if subject is not None else {"uz_latn": "Xush kelibsiz"},
        "body": body if body is not None else {"uz_latn": "Platformaga xush kelibsiz"},
    }


async def test_returns_the_matching_template_for_the_event_key() -> None:
    version_id = uuid4()
    head = _head(code="welcome-email", version_id=version_id)
    reader = FakeConfigurationReader(
        heads=[head],
        versions={version_id: _version(version_id=version_id, snapshot=_snapshot())},
    )
    adapter = ConfigurationNotificationTemplateAdapter(reader)

    templates = await adapter.list_templates_for_event("UserRegistered")

    assert len(templates) == 1
    assert templates[0].channel == "EMAIL"
    assert templates[0].subject is not None
    assert templates[0].subject.uz_latn == "Xush kelibsiz"
    assert templates[0].body.uz_latn == "Platformaga xush kelibsiz"


async def test_returns_empty_tuple_when_no_template_matches_the_event_key() -> None:
    version_id = uuid4()
    head = _head(code="welcome-email", version_id=version_id)
    reader = FakeConfigurationReader(
        heads=[head],
        versions={version_id: _version(version_id=version_id, snapshot=_snapshot())},
    )
    adapter = ConfigurationNotificationTemplateAdapter(reader)

    assert await adapter.list_templates_for_event("ListingPublished") == ()


async def test_skips_a_head_with_no_current_version() -> None:
    head = _head(code="draft-only", version_id=None)
    reader = FakeConfigurationReader(heads=[head])
    adapter = ConfigurationNotificationTemplateAdapter(reader)

    assert await adapter.list_templates_for_event("UserRegistered") == ()


async def test_skips_a_non_published_version() -> None:
    version_id = uuid4()
    head = _head(code="unpublished", version_id=version_id)
    reader = FakeConfigurationReader(
        heads=[head],
        versions={
            version_id: _version(version_id=version_id, status="DRAFT", snapshot=_snapshot())
        },
    )
    adapter = ConfigurationNotificationTemplateAdapter(reader)

    assert await adapter.list_templates_for_event("UserRegistered") == ()


async def test_lists_every_channel_a_published_template_exists_for() -> None:
    email_version = uuid4()
    sms_version = uuid4()
    heads = [
        _head(code="welcome-email", version_id=email_version),
        _head(code="welcome-sms", version_id=sms_version),
    ]
    reader = FakeConfigurationReader(
        heads=heads,
        versions={
            email_version: _version(version_id=email_version, snapshot=_snapshot(channel="EMAIL")),
            sms_version: _version(
                version_id=sms_version,
                snapshot=_snapshot(channel="SMS", subject=None, body={"uz_latn": "SMS body"}),
            ),
        },
    )
    adapter = ConfigurationNotificationTemplateAdapter(reader)

    templates = await adapter.list_templates_for_event("UserRegistered")

    assert {t.channel for t in templates} == {"EMAIL", "SMS"}


async def test_returns_none_for_a_snapshot_missing_a_required_field() -> None:
    version_id = uuid4()
    head = _head(code="malformed", version_id=version_id)
    malformed_snapshot = {"descriptor": {"name": {"uz_latn": "x"}}}  # no event_key/channel/body
    reader = FakeConfigurationReader(
        heads=[head],
        versions={version_id: _version(version_id=version_id, snapshot=malformed_snapshot)},
    )
    adapter = ConfigurationNotificationTemplateAdapter(reader)

    assert await adapter.list_templates_for_event("UserRegistered") == ()
