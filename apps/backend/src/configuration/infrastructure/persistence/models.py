"""The eight Head+Version table pairs (Physical DB Sec 2.4), each a small concrete class
combining `_HeadMixin`/`_VersionMixin` (all shared machinery) with its own promoted columns
(Physical DB Sec 2.4 "Per-entity promoted columns" table) -- the generic-machinery-instantiated-
eight-times pattern applied to the ORM layer. Plus `configuration.permission_group` (Physical DB
Sec 2.4: authoring-time convenience, not versioned, no v1 API surface) and the module's own
`outbox_event` (reusing `backbone.outbox.make_outbox_event_model` -- configuration has no
`processed_event`, since it is a leaf-free hub that consumes nothing, Physical DB Sec 2.4).

Every subclass that adds a CHECK constraint on top of `_VersionMixin.base_table_args()` must
redeclare `__table_args__` as a `@declared_attr.directive @classmethod` (not a plain class-body
tuple) -- `base_table_args()` reads `cls.__tablename__`/`cls.__head_table_name__`, which only
resolve correctly once `cls` is the concrete mapped subclass, not while the class body itself is
still being evaluated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import ARRAY, TIMESTAMP, CheckConstraint, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from backbone.outbox import make_outbox_event_model
from backbone.persistence import uuid7
from configuration.domain.whitelist import PRODUCT_TYPES
from configuration.infrastructure.persistence.base import ConfigurationBase
from configuration.infrastructure.persistence.mixins import _HeadMixin, _VersionMixin

_PRODUCT_TYPE_SQL = "(" + ",".join(f"'{t}'" for t in sorted(PRODUCT_TYPES)) + ")"


# -- category --------------------------------------------------------------------------------


class Category(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "category"


class CategoryVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "category"

    parent_category_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("category.id", name="fk_category_version_parent_category"),
        nullable=True,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    form_definition_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("form_definition.id"), nullable=True
    )
    """Nullable because this table holds DRAFTS. A category being authored before its form exists
    is ordinary work-in-progress, and Config Framework Sec 9 requires that it save -- I-02's
    "exactly one binding" is a rule about a *published* category, enforced by the gate against
    `definition_document`, which stays the source of truth. The promoted column is a
    denormalised index (Physical DB Sec 2.4); `SqlalchemyConfigHeadRepository._existing_uuid`
    leaves it NULL rather than writing a dangling reference, so the foreign key stays honest."""
    tree_status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            *cls.base_table_args(),
            CheckConstraint(
                "tree_status IN ('ACTIVE','RETIRED')", name="ck_category_version_tree_status"
            ),
            CheckConstraint(
                "parent_category_id <> head_id", name="ck_category_version_no_self_parent"
            ),
        )


# -- form_definition ---------------------------------------------------------------------------


class FormDefinition(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "form_definition"


class FormDefinitionVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "form_definition"

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            *cls.base_table_args(),
            CheckConstraint(
                "jsonb_typeof(definition_document->'fields') = 'array'",
                name="ck_form_definition_version_fields_array",
            ),
        )


# -- product_definition ------------------------------------------------------------------------


class ProductDefinition(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "product_definition"


class ProductDefinitionVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "product_definition"

    product_type: Mapped[str] = mapped_column(Text, nullable=False)
    price_amount: Mapped[Any] = mapped_column(Numeric(14, 2), nullable=False)
    price_currency: Mapped[str] = mapped_column(Text, nullable=False, default="UZS")
    term_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            *cls.base_table_args(),
            CheckConstraint(
                f"product_type IN {_PRODUCT_TYPE_SQL}", name="ck_product_definition_version_type"
            ),
            CheckConstraint("price_amount >= 0", name="ck_product_definition_version_price"),
        )


# -- placement_slot ----------------------------------------------------------------------------


class PlacementSlot(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "placement_slot"


class PlacementSlotVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "placement_slot"

    slot_key: Mapped[str] = mapped_column(Text, nullable=False)
    page_zone: Mapped[str] = mapped_column(Text, nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)


# -- role_definition ---------------------------------------------------------------------------


class RoleDefinition(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "role_definition"


class RoleDefinitionVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "role_definition"

    role_name: Mapped[str] = mapped_column(Text, nullable=False)
    permission_keys: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            *cls.base_table_args(),
            CheckConstraint(
                "cardinality(permission_keys) > 0",
                name="ck_role_definition_version_permission_keys",
            ),
        )


# -- search_configuration -----------------------------------------------------------------------


class SearchConfiguration(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "search_configuration"


class SearchConfigurationVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "search_configuration"

    scope_category_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("category.id"), nullable=True
    )
    promotion_page_cap: Mapped[int] = mapped_column(Integer, nullable=False)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            *cls.base_table_args(),
            CheckConstraint("promotion_page_cap >= 0", name="ck_search_configuration_version_cap"),
        )


# -- notification_template ----------------------------------------------------------------------


class NotificationTemplate(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "notification_template"


class NotificationTemplateVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "notification_template"

    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            *cls.base_table_args(),
            CheckConstraint(
                "channel IN ('EMAIL','WEB_PUSH','SMS')",
                name="ck_notification_template_version_channel",
            ),
        )


# -- platform_settings --------------------------------------------------------------------------


class PlatformSettings(ConfigurationBase, _HeadMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "platform_settings"


class PlatformSettingsVersion(ConfigurationBase, _VersionMixin):  # type: ignore[misc,valid-type]
    __head_table_name__ = "platform_settings"

    settings_scope: Mapped[str] = mapped_column(Text, nullable=False, default="GLOBAL")


# -- permission_group (Physical DB Sec 2.4: authoring-time convenience, not versioned) ----------


class PermissionGroup(ConfigurationBase):  # type: ignore[misc,valid-type]
    __tablename__ = "permission_group"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    permission_keys: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_by: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_by: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


OutboxEvent = make_outbox_event_model(ConfigurationBase)


HEAD_MODEL_BY_ENTITY_TYPE: dict[str, type[Any]] = {
    "category": Category,
    "form-definition": FormDefinition,
    "product-definition": ProductDefinition,
    "placement-slot": PlacementSlot,
    "role-definition": RoleDefinition,
    "search-configuration": SearchConfiguration,
    "notification-template": NotificationTemplate,
    "platform-settings": PlatformSettings,
}

VERSION_MODEL_BY_ENTITY_TYPE: dict[str, type[Any]] = {
    "category": CategoryVersion,
    "form-definition": FormDefinitionVersion,
    "product-definition": ProductDefinitionVersion,
    "placement-slot": PlacementSlotVersion,
    "role-definition": RoleDefinitionVersion,
    "search-configuration": SearchConfigurationVersion,
    "notification-template": NotificationTemplateVersion,
    "platform-settings": PlatformSettingsVersion,
}
