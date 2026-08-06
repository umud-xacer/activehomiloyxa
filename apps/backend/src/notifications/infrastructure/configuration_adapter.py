"""Reads published `NotificationTemplate` snapshots from `configuration` -- never
`configuration.domain`/`application`/`infrastructure` (`cross-module-notifications`,
tools/importlinter.cfg; the ONE module notifications may import at all besides `shared_kernel`,
SAD Sec 8.1). Mirrors `billing.infrastructure.configuration_adapter.
ConfigurationProductDefinitionAdapter`'s own narrow-Protocol bridge pattern exactly -- a
`NotificationTemplate` version's own content model has no exact head `code` naming convention
documented, so this adapter lists every published `notification-template` head and reads each
one's current published version, filtering by `event_key`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol
from uuid import UUID

from notifications.application.ports import NotificationTemplateSnapshot
from shared_kernel import LocalizedText


class _ConfigurationReader(Protocol):
    """The narrow slice of `configuration.interfaces.ports.ConfigurationPort` this module
    actually calls."""

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> Any: ...

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> Any: ...


class ConfigurationNotificationTemplateAdapter:
    """Implements `notifications.application.ports.TemplateReaderPort`."""

    def __init__(self, configuration: _ConfigurationReader) -> None:
        self._configuration = configuration

    async def list_templates_for_event(
        self, event_key: str
    ) -> tuple[NotificationTemplateSnapshot, ...]:
        results: list[NotificationTemplateSnapshot] = []
        async for head, version in self._published_templates():
            snapshot = _to_snapshot(head, version)
            if snapshot is not None and snapshot.event_key == event_key:
                results.append(snapshot)
        return tuple(results)

    async def _published_templates(self) -> AsyncIterator[tuple[Any, Any]]:
        cursor: str | None = None
        while True:
            page = await self._configuration.list_config_heads(
                "notification-template", cursor=cursor, limit=50
            )
            for head in page.items:
                if head.current_version_id is None:
                    continue
                version = await self._configuration.get_config_version(
                    "notification-template", head.id, head.current_version_id
                )
                if version.status != "PUBLISHED" or version.snapshot is None:
                    continue
                yield head, version
            cursor = page.page.next_cursor
            if cursor is None:
                break


def _to_snapshot(head: Any, version: Any) -> NotificationTemplateSnapshot | None:
    raw = version.snapshot
    event_key = raw.get("event_key")
    channel = raw.get("channel")
    body_raw = raw.get("body")
    if event_key is None or channel is None or body_raw is None:
        return None
    subject_raw = raw.get("subject")
    return NotificationTemplateSnapshot(
        template_id=head.id,
        template_version_id=version.id,
        event_key=str(event_key),
        channel=str(channel),
        subject=LocalizedText(**subject_raw) if subject_raw else None,
        body=LocalizedText(**body_raw),
    )
