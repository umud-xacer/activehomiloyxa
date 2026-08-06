"""configuration -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from configuration.interfaces.dto import (
    Category,
    ConfigPublishRequest,
    ConfigRollbackRequest,
    ConfigurationDraftRequest,
    ConfigurationHead,
    ConfigurationHeadPage,
    ConfigurationVersion,
    ConfigValidationResult,
    FormDefinition,
    ImportConfigBody,
)


class ConfigurationPort(Protocol):
    """Derived from OpenAPI operations: `compareConfigVersions`, `createConfigDraft`, `createConfigVersionDraft`, `exportConfig`, `getCategory`, `getCategoryForm`, `getConfigHead`, `getConfigVersion`, `importConfig`, `listCategories`, `listConfigHeads`, `listConfigVersions`, `publishConfigVersion`, `rollbackConfig`, `updateConfigDraft`, `validateConfigVersion`."""

    async def compare_config_versions(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        from_: UUID,
        to: UUID,
    ) -> dict[str, Any]:
        """`GET /admin/config/{entityType}/{headId}/versions/compare` (operationId `compareConfigVersions`). Compare two versions"""
        ...

    async def create_config_draft(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        body: ConfigurationDraftRequest,
    ) -> ConfigurationVersion:
        """`POST /admin/config/{entityType}` (operationId `createConfigDraft`). Create a configuration entity (draft)"""
        ...

    async def create_config_version_draft(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        body: ConfigurationDraftRequest,
    ) -> ConfigurationVersion:
        """`POST /admin/config/{entityType}/{headId}/versions` (operationId `createConfigVersionDraft`). Create a new draft version"""
        ...

    async def export_config(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        version_id: UUID | None = None,
    ) -> dict[str, Any]:
        """`GET /admin/config/{entityType}/{headId}/export` (operationId `exportConfig`). Export a configuration definition"""
        ...

    async def get_category(self, category_id: UUID) -> Category:
        """`GET /categories/{categoryId}` (operationId `getCategory`). Get a category"""
        ...

    async def get_category_form(self, category_id: UUID) -> FormDefinition:
        """`GET /categories/{categoryId}/form` (operationId `getCategoryForm`). Get the dynamic form for a category"""
        ...

    async def get_config_head(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
    ) -> ConfigurationHead:
        """`GET /admin/config/{entityType}/{headId}` (operationId `getConfigHead`). Get a configuration head with its versions"""
        ...

    async def get_config_version(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        version_id: UUID,
    ) -> ConfigurationVersion:
        """`GET /admin/config/{entityType}/{headId}/versions/{versionId}` (operationId `getConfigVersion`). Get a configuration version"""
        ...

    async def import_config(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        body: ImportConfigBody,
    ) -> ConfigurationVersion:
        """`POST /admin/config/{entityType}/import` (operationId `importConfig`). Import a configuration definition"""
        ...

    async def list_categories(
        self, parent_id: UUID | None = None, include_retired: bool | None = False
    ) -> list[Category]:
        """`GET /categories` (operationId `listCategories`). List categories (taxonomy)"""
        ...

    async def list_config_heads(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> ConfigurationHeadPage:
        """`GET /admin/config/{entityType}` (operationId `listConfigHeads`). List configuration heads of a type"""
        ...

    async def list_config_versions(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
    ) -> list[ConfigurationVersion]:
        """`GET /admin/config/{entityType}/{headId}/versions` (operationId `listConfigVersions`). List versions of a configuration entity"""
        ...

    async def publish_config_version(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        version_id: UUID,
        body: ConfigPublishRequest,
    ) -> ConfigurationVersion:
        """`POST /admin/config/{entityType}/{headId}/versions/{versionId}/publish` (operationId `publishConfigVersion`). Publish a version"""
        ...

    async def rollback_config(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        body: ConfigRollbackRequest,
    ) -> ConfigurationVersion:
        """`POST /admin/config/{entityType}/{headId}/rollback` (operationId `rollbackConfig`). Roll back to a prior version"""
        ...

    async def update_config_draft(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        version_id: UUID,
        body: ConfigurationDraftRequest,
    ) -> ConfigurationVersion:
        """`PUT /admin/config/{entityType}/{headId}/versions/{versionId}` (operationId `updateConfigDraft`). Edit a draft version"""
        ...

    async def validate_config_version(
        self,
        entity_type: Literal[
            "category",
            "form-definition",
            "product-definition",
            "placement-slot",
            "role-definition",
            "search-configuration",
            "notification-template",
            "platform-settings",
        ],
        head_id: UUID,
        version_id: UUID,
    ) -> ConfigValidationResult:
        """`POST /admin/config/{entityType}/{headId}/versions/{versionId}/validate` (operationId `validateConfigVersion`). Validate a version (dry run)"""
        ...


class WhitelistRegistryPort(Protocol):
    """SAD Sec 7.2 lists this on configuration's public interface row: the fixed, code-defined
    whitelist of field types / validator types / permission keys / lifecycle semantics (DEC-21).
    No OpenAPI operation exposes it directly -- config authoring operations (ConfigurationPort)
    validate against it internally."""
