"""Structural/type validation for the eight per-entity `definition_document` content models
(Physical DB Sec 2.4; Config Framework Sec 4). Each model is `extra="forbid"`: an unknown field
is a structural failure, not silently dropped."""

from __future__ import annotations

from uuid import uuid4

import pytest
from apps.backend.tests.configuration.conftest import minimal_content
from pydantic import ValidationError

from configuration.domain.content import (
    CONTENT_MODEL_BY_ENTITY_TYPE,
    CategoryContent,
    FormDefinitionContent,
    NotificationTemplateContent,
    PlacementSlotContent,
    PlatformSettingsContent,
    ProductDefinitionContent,
    RoleDefinitionContent,
    SearchConfigurationContent,
)


def test_content_model_registry_covers_all_eight_entity_types() -> None:
    assert set(CONTENT_MODEL_BY_ENTITY_TYPE) == {
        "category",
        "form-definition",
        "product-definition",
        "placement-slot",
        "role-definition",
        "search-configuration",
        "notification-template",
        "platform-settings",
    }


def _minimal(entity_type: str) -> dict[str, object]:
    if entity_type == "category":
        return minimal_content(entity_type, form_definition_id=uuid4())
    return minimal_content(entity_type)


@pytest.mark.parametrize("entity_type", list(CONTENT_MODEL_BY_ENTITY_TYPE))
def test_minimal_content_validates_for_every_entity_type(entity_type: str) -> None:
    model_type = CONTENT_MODEL_BY_ENTITY_TYPE[entity_type]
    model_type.model_validate(_minimal(entity_type))  # does not raise


@pytest.mark.parametrize("entity_type", list(CONTENT_MODEL_BY_ENTITY_TYPE))
def test_unknown_field_is_rejected_structurally(entity_type: str) -> None:
    model_type = CONTENT_MODEL_BY_ENTITY_TYPE[entity_type]
    content = _minimal(entity_type)
    content["totally_unexpected_field"] = "should not be accepted"
    with pytest.raises(ValidationError):
        model_type.model_validate(content)


def test_category_requires_form_definition_id() -> None:
    with pytest.raises(ValidationError):
        CategoryContent.model_validate(
            {
                "descriptor": {"name": {"uz_latn": "Housing"}},
                "path": "/housing",
            }
        )


def test_form_definition_has_no_category_id_field() -> None:
    """Regression test (this session): Physical DB Sec 2.4's Extra-columns table lists no
    promoted columns for `form_definition`/`_version` at all -- the binding is one-directional
    (`category.form_definition_id`, I-02). A form carrying `category_id` would make the two
    entities mutually dependent at the gate and unbootstrappable (neither could ever publish
    first)."""
    assert "category_id" not in FormDefinitionContent.model_fields
    with pytest.raises(ValidationError):
        FormDefinitionContent.model_validate(
            {
                "descriptor": {"name": {"uz_latn": "Housing form"}},
                "category_id": str(uuid4()),
                "sections": [],
                "fields": [],
            }
        )


def test_form_definition_field_section_code_is_free_text_not_cross_validated_at_this_layer() -> (
    None
):
    """Cross-field consistency (a field referencing a real section code) is the gate's job
    (`gate.py`), not the content model's -- Pydantic here only proves structural/type shape."""
    FormDefinitionContent.model_validate(
        {
            "descriptor": {"name": {"uz_latn": "Form"}},
            "sections": [{"code": "main", "label": {"uz_latn": "Main"}, "order": 1}],
            "fields": [
                {
                    "code": "area",
                    "section_code": "no-such-section",
                    "label": {"uz_latn": "Area"},
                    "field_type": "number",
                }
            ],
        }
    )  # does not raise -- structurally valid even though the gate would reject it


def test_product_definition_price_amount_is_decimal() -> None:
    content = ProductDefinitionContent.model_validate(
        minimal_content("product-definition", price_amount="19.99")
    )
    assert str(content.price_amount) == "19.99"


def test_placement_slot_minimal_shape() -> None:
    PlacementSlotContent.model_validate(minimal_content("placement-slot"))


def test_role_definition_minimal_shape() -> None:
    RoleDefinitionContent.model_validate(minimal_content("role-definition"))


def test_search_configuration_minimal_shape() -> None:
    SearchConfigurationContent.model_validate(minimal_content("search-configuration"))


def test_notification_template_minimal_shape() -> None:
    NotificationTemplateContent.model_validate(minimal_content("notification-template"))


def test_platform_settings_minimal_shape() -> None:
    PlatformSettingsContent.model_validate(minimal_content("platform-settings"))
