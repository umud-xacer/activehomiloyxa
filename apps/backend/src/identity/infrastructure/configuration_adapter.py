"""Reads published RoleDefinition and PlatformSettings snapshots from `configuration` via its
`interfaces/` package only -- never `configuration.domain`/`application`/`infrastructure`
(`cross-module-identity`, tools/importlinter.cfg). The concrete reader instance is built at the
composition root (apps/backend/src/composition_root.py), the one place allowed to see both
modules' internals to wire this bridge; this adapter only ever calls the narrow `_ConfigReader`
Protocol below -- the two `configuration.interfaces.ports.ConfigurationPort` methods it actually
needs, not that Protocol's entire fifteen-operation surface (DIP: depend on the shape you use).
Any object satisfying the full `ConfigurationPort` (or a purpose-built bridge exposing just these
two) structurally satisfies `_ConfigReader` too.

`ConfigurationPort` has no "get head by code" operation (only list+filter, Config Framework Sec
7.2's own consumer-facing surface is snapshot-shaped, not code-indexed) -- `resolve_by_code`/
`get_identity_settings` page through `list_config_heads` and match on `code` client-side, exactly
as `configuration`'s own seed data is keyed (`super-admin`, `administrator`,
`platform-settings-global`)."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from configuration.interfaces.dto import ConfigurationHeadPage, ConfigurationVersion
from identity.application.exceptions import RoleDefinitionNotFoundError
from identity.application.ports import IdentityPlatformSettings, ResolvedRoleDefinition

_PLATFORM_SETTINGS_CODE = "platform-settings-global"

_EntityType = Literal["role-definition", "platform-settings"]


class _ConfigReader(Protocol):
    """The narrow slice of `ConfigurationPort` this module actually calls."""

    async def list_config_heads(
        self, entity_type: _EntityType, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage: ...

    async def get_config_version(
        self, entity_type: _EntityType, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion: ...


class ConfigurationRoleDefinitionAdapter:
    """Implements `identity.application.ports.RoleDefinitionReaderPort`."""

    def __init__(self, configuration: _ConfigReader) -> None:
        self._configuration = configuration

    async def resolve_by_code(self, code: str) -> ResolvedRoleDefinition:
        cursor: str | None = None
        while True:
            page = await self._configuration.list_config_heads(
                "role-definition", cursor=cursor, limit=50
            )
            for head in page.items:
                if head.code == code and head.current_version_id is not None:
                    version = await self._configuration.get_config_version(
                        "role-definition", head.id, head.current_version_id
                    )
                    if version.status != "PUBLISHED" or version.snapshot is None:
                        raise RoleDefinitionNotFoundError(code)
                    permission_keys = frozenset(version.snapshot.get("permission_keys", []))
                    return ResolvedRoleDefinition(
                        head_id=head.id,
                        version_id=version.id,
                        code=head.code,
                        permission_keys=permission_keys,
                    )
            cursor = page.page.next_cursor
            if cursor is None:
                raise RoleDefinitionNotFoundError(code)

    async def get_permission_keys(self, *, head_id: UUID, version_id: UUID) -> frozenset[str]:
        version = await self._configuration.get_config_version(
            "role-definition", head_id, version_id
        )
        if version.snapshot is None:
            return frozenset()
        return frozenset(version.snapshot.get("permission_keys", []))


class ConfigurationPlatformSettingsAdapter:
    """Implements `identity.application.ports.PlatformSettingsReaderPort` (DEC-21: never
    hardcode a configurable value)."""

    def __init__(self, configuration: _ConfigReader) -> None:
        self._configuration = configuration

    async def get_identity_settings(self) -> IdentityPlatformSettings:
        cursor: str | None = None
        while True:
            page = await self._configuration.list_config_heads(
                "platform-settings", cursor=cursor, limit=50
            )
            for head in page.items:
                if head.code == _PLATFORM_SETTINGS_CODE and head.current_version_id is not None:
                    version = await self._configuration.get_config_version(
                        "platform-settings", head.id, head.current_version_id
                    )
                    settings = (version.snapshot or {}).get("settings", {})
                    return IdentityPlatformSettings(
                        otp_expiry_minutes=int(settings["otp.expiry_minutes"]),
                        session_expiry_hours=int(settings["session.expiry_hours"]),
                        # `.get(..., default)`, not a direct index like the two keys above:
                        # these are new (Security Sec 3.1 login-lockout task) and a published
                        # `platform-settings-global` version from before this task predates them
                        # -- an environment that hasn't re-published since must still authenticate
                        # rather than 500 on every login. `seed.py`'s idempotent backfill sets the
                        # real values on the next deploy; these defaults match its own (4 attempts
                        # / 15 minutes) so behaviour is identical either way.
                        login_lockout_max_attempts=int(
                            settings.get("login_lockout.max_attempts", 4)
                        ),
                        login_lockout_block_minutes=int(
                            settings.get("login_lockout.block_minutes", 15)
                        ),
                    )
            cursor = page.page.next_cursor
            if cursor is None:
                raise LookupError(
                    f"no published platform-settings head with code {_PLATFORM_SETTINGS_CODE!r}"
                )
