"""Unit tests for `ConfigurationRoleDefinitionAdapter`/`ConfigurationPlatformSettingsAdapter`
against a fake `_ConfigReader` (the narrow slice of `configuration.interfaces.ports.ConfigurationPort`
these adapters actually call) -- no real Postgres needed."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from configuration.interfaces.dto import (
    ConfigurationHead,
    ConfigurationHeadPage,
    ConfigurationVersion,
    PageInfo,
)
from identity.application.exceptions import RoleDefinitionNotFoundError
from identity.infrastructure.configuration_adapter import (
    ConfigurationPlatformSettingsAdapter,
    ConfigurationRoleDefinitionAdapter,
)


@dataclass
class FakeConfigReader:
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


def _head(entity_type: str, code: str, version_id: UUID) -> ConfigurationHead:
    return ConfigurationHead(
        id=uuid4(),
        entity_type=entity_type,  # type: ignore[arg-type]
        code=code,
        current_version_id=version_id,
        status="PUBLISHED",
        business_owner="Super Administrator",
        created_at=None,
    )


def _version(head_id: UUID, version_id: UUID, snapshot: dict[str, object]) -> ConfigurationVersion:
    return ConfigurationVersion(
        id=version_id,
        head_id=head_id,
        version_number=1,
        status="PUBLISHED",
        definition={},
        snapshot=snapshot,
    )


async def test_resolve_by_code_returns_permission_keys() -> None:
    version_id = uuid4()
    head = _head("role-definition", "administrator", version_id)
    version = _version(head.id, version_id, {"permission_keys": ["identity:role:assign"]})
    reader = FakeConfigReader(heads=[head], versions={version_id: version})

    adapter = ConfigurationRoleDefinitionAdapter(reader)
    resolved = await adapter.resolve_by_code("administrator")
    assert resolved.head_id == head.id
    assert resolved.version_id == version_id
    assert resolved.permission_keys == frozenset({"identity:role:assign"})


async def test_resolve_by_code_unknown_code_raises() -> None:
    reader = FakeConfigReader()
    adapter = ConfigurationRoleDefinitionAdapter(reader)
    with pytest.raises(RoleDefinitionNotFoundError):
        await adapter.resolve_by_code("does-not-exist")


async def test_get_permission_keys_returns_empty_set_when_no_snapshot() -> None:
    version_id = uuid4()
    version = _version(uuid4(), version_id, {})
    version = version.model_copy(update={"snapshot": None})
    reader = FakeConfigReader(versions={version_id: version})

    adapter = ConfigurationRoleDefinitionAdapter(reader)
    keys = await adapter.get_permission_keys(head_id=uuid4(), version_id=version_id)
    assert keys == frozenset()


async def test_get_identity_settings_reads_otp_and_session_expiry() -> None:
    version_id = uuid4()
    head = _head("platform-settings", "platform-settings-global", version_id)
    version = _version(
        head.id,
        version_id,
        {"settings": {"otp.expiry_minutes": 5, "session.expiry_hours": 720}},
    )
    reader = FakeConfigReader(heads=[head], versions={version_id: version})

    adapter = ConfigurationPlatformSettingsAdapter(reader)
    settings = await adapter.get_identity_settings()
    assert settings.otp_expiry_minutes == 5
    assert settings.session_expiry_hours == 720


async def test_get_identity_settings_no_published_head_raises() -> None:
    reader = FakeConfigReader()
    adapter = ConfigurationPlatformSettingsAdapter(reader)
    with pytest.raises(LookupError):
        await adapter.get_identity_settings()
