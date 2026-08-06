"""The pre-activation validation gate (Config Framework Sec 9; I-16) -- one evaluator dispatched
across all eight entity types. Each test isolates exactly one check by starting from
`minimal_content` (already gate-passing) and breaking exactly one thing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from apps.backend.tests.configuration.conftest import minimal_content

from configuration.domain.gate import GateContext, PreActivationGate


def _ctx(**overrides: object) -> GateContext:
    defaults: dict[str, object] = {"entity_type": "category"}
    defaults.update(overrides)
    return GateContext(**defaults)  # type: ignore[arg-type]


def _publishable_form_ctx() -> tuple[GateContext, dict[str, Any]]:
    form_id = uuid4()
    ctx = _ctx(dependency_exists={f"form-definition:{form_id}": True})
    content = minimal_content("category", form_definition_id=form_id)
    return ctx, content


def test_gate_accepts_gate_passing_category() -> None:
    gate = PreActivationGate()
    ctx, content = _publishable_form_ctx()
    result = gate.evaluate("category", "housing", content, ctx)
    assert result.valid
    assert result.errors == ()


def test_duplicate_code_is_refused() -> None:
    gate = PreActivationGate()
    ctx, content = _publishable_form_ctx()
    ctx = GateContext(**{**ctx.__dict__, "existing_codes": frozenset({"housing"})})
    result = gate.evaluate("category", "housing", content, ctx)
    assert not result.valid
    assert result.errors[0].code == "DUPLICATE_CODE"


def test_missing_translation_is_refused() -> None:
    gate = PreActivationGate()
    ctx, content = _publishable_form_ctx()
    content["descriptor"]["name"] = {"ru": "Жилье"}  # no uz_latn
    result = gate.evaluate("category", "housing", content, ctx)
    assert not result.valid
    assert any(e.code == "MISSING_TRANSLATION" for e in result.errors)


def test_I16_category_missing_form_dependency_is_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("category", form_definition_id=uuid4())
    result = gate.evaluate("category", "housing", content, _ctx())  # no dependency_exists entry
    assert not result.valid
    assert result.errors[0].code == "MISSING_DEPENDENCY"
    assert result.errors[0].field == "form_definition_id"


def test_category_cycle_is_refused() -> None:
    gate = PreActivationGate()
    form_id = uuid4()
    parent_id = uuid4()
    content = minimal_content(
        "category", form_definition_id=form_id, parent_category_id=str(parent_id)
    )
    ctx = _ctx(
        dependency_exists={f"form-definition:{form_id}": True},
        ancestor_codes_of_parent=frozenset({"housing"}),
    )
    result = gate.evaluate("category", "housing", content, ctx)
    assert not result.valid
    assert any(e.code == "CIRCULAR_REFERENCE" for e in result.errors)


def test_I03_retiring_category_with_bound_listings_is_refused() -> None:
    gate = PreActivationGate()
    form_id = uuid4()
    content = minimal_content("category", form_definition_id=form_id, tree_status="RETIRED")
    ctx = _ctx(
        dependency_exists={f"form-definition:{form_id}": True},
        category_has_bound_listings=True,
    )
    result = gate.evaluate("category", "housing", content, ctx)
    assert not result.valid
    assert any(e.code == "ORPHANED_LISTINGS" for e in result.errors)


def test_I16_form_definition_whitelisted_field_type_accepted() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "area",
                "section_code": "main",
                "label": {"uz_latn": "Area"},
                "field_type": "number",
            }
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert result.valid


def test_I16_form_definition_file_field_type_accepted() -> None:
    """ADR-0009: `file` joins the FIELD_TYPES whitelist for document-attachment fields."""
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "title_deed",
                "section_code": "main",
                "label": {"uz_latn": "Title deed"},
                "field_type": "file",
            }
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert result.valid


def test_I16_form_definition_non_whitelisted_field_type_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "area",
                "section_code": "main",
                "label": {"uz_latn": "Area"},
                "field_type": "rich_html",  # not in FIELD_TYPES
            }
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_form_definition_duplicate_field_code_refused() -> None:
    gate = PreActivationGate()
    field = {
        "code": "area",
        "section_code": "main",
        "label": {"uz_latn": "Area"},
        "field_type": "number",
    }
    content = minimal_content("form-definition", fields=[field, dict(field)])
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert any(e.code == "DUPLICATE_FIELD_CODE" for e in result.errors)


def test_form_definition_field_referencing_unknown_section_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "area",
                "section_code": "no-such-section",
                "label": {"uz_latn": "Area"},
                "field_type": "number",
            }
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert any(
        e.code == "MISSING_DEPENDENCY" and e.field == "fields.area.section_code"
        for e in result.errors
    )


def test_I16_form_definition_non_whitelisted_validator_type_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "phone",
                "section_code": "main",
                "label": {"uz_latn": "Phone"},
                "field_type": "text",
                "validators": [{"validator_type": "arbitrary_regex", "params": {}}],
            }
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_form_definition_conditional_visibility_valid_reference_accepted() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "square_meters",
                "section_code": "main",
                "label": {"uz_latn": "Area"},
                "field_type": "number",
            },
            {
                "code": "unit_count",
                "section_code": "main",
                "label": {"uz_latn": "Units"},
                "field_type": "number",
                "conditional_visibility": {
                    "field_code": "square_meters",
                    "operator": "GREATER_THAN",
                    "value": 0,
                },
            },
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert result.valid


def test_form_definition_conditional_visibility_bad_operator_rejected_structurally() -> None:
    """`ConditionalVisibility.operator` is itself a closed Pydantic `Literal` (`content.py`), so
    a non-member value fails at `model_validate` (INVALID_STRUCTURE) before the gate's own
    `check_condition_operator` whitelist re-check (`gate.py` lines ~197-198) is ever reached with
    an invalid value -- that check is a redundant, structurally-unreachable defensive branch
    given the current content model, not a bug, but worth noting for the final report."""
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "unit_count",
                "section_code": "main",
                "label": {"uz_latn": "Units"},
                "field_type": "number",
                "conditional_visibility": {
                    "field_code": "unit_count",
                    "operator": "MATCHES_REGEX",
                    "value": 0,
                },
            },
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert result.errors[0].code == "INVALID_STRUCTURE"


def test_form_definition_conditional_visibility_unknown_field_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "unit_count",
                "section_code": "main",
                "label": {"uz_latn": "Units"},
                "field_type": "number",
                "conditional_visibility": {
                    "field_code": "no-such-field",
                    "operator": "EQUALS",
                    "value": 0,
                },
            },
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert any(
        e.code == "MISSING_DEPENDENCY" and e.field == "fields.unit_count.conditional_visibility"
        for e in result.errors
    )


def test_I16_form_definition_non_whitelisted_rendering_hint_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "notes",
                "section_code": "main",
                "label": {"uz_latn": "Notes"},
                "field_type": "text",
                "rendering_hint": "AUTO_EXECUTE_JS",
            }
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_I16_pattern_safe_validator_requires_safe_pattern_key() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "form-definition",
        fields=[
            {
                "code": "phone",
                "section_code": "main",
                "label": {"uz_latn": "Phone"},
                "field_type": "text",
                "validators": [{"validator_type": "pattern_safe", "params": {}}],
            }
        ],
    )
    result = gate.evaluate(
        "form-definition", "housing-form", content, _ctx(entity_type="form-definition")
    )
    assert not result.valid
    assert any(e.code == "UNSAFE_CONTENT" for e in result.errors)


def test_I16_product_definition_whitelisted_product_type_accepted() -> None:
    gate = PreActivationGate()
    content = minimal_content("product-definition")
    result = gate.evaluate(
        "product-definition", "premium", content, _ctx(entity_type="product-definition")
    )
    assert result.valid


def test_I16_product_definition_non_whitelisted_product_type_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("product-definition", product_type="CRYPTO_PAYMENT")
    result = gate.evaluate(
        "product-definition", "premium", content, _ctx(entity_type="product-definition")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_product_definition_negative_price_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("product-definition", price_amount="-5.00")
    result = gate.evaluate(
        "product-definition", "premium", content, _ctx(entity_type="product-definition")
    )
    assert not result.valid
    assert any(e.code == "CONFLICTING_RULE" for e in result.errors)


def test_I16_placement_slot_non_whitelisted_page_zone_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("placement-slot", page_zone="ADMIN_BACKDOOR")
    result = gate.evaluate("placement-slot", "hero-1", content, _ctx(entity_type="placement-slot"))
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_I16_role_definition_non_whitelisted_permission_key_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("role-definition", permission_keys=["config:category:delete-all"])
    result = gate.evaluate(
        "role-definition", "editor", content, _ctx(entity_type="role-definition")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_role_definition_missing_permission_group_dependency_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "role-definition", permission_keys=[], permission_group_codes=["moderators"]
    )
    result = gate.evaluate(
        "role-definition", "editor", content, _ctx(entity_type="role-definition")
    )
    assert not result.valid
    assert any(e.code == "MISSING_DEPENDENCY" for e in result.errors)


def test_role_definition_missing_parent_role_dependency_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "role-definition", permission_keys=[], parent_role_code="senior-editor"
    )
    result = gate.evaluate(
        "role-definition", "editor", content, _ctx(entity_type="role-definition")
    )
    assert not result.valid
    assert any(e.code == "MISSING_DEPENDENCY" for e in result.errors)


def test_role_definition_hierarchy_cycle_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "role-definition", permission_keys=[], parent_role_code="senior-editor"
    )
    ctx = _ctx(
        entity_type="role-definition",
        dependency_exists={"role-definition:senior-editor": True},
        ancestor_codes_of_parent_role=frozenset({"editor"}),
    )
    result = gate.evaluate("role-definition", "editor", content, ctx)
    assert not result.valid
    assert any(e.code == "CIRCULAR_REFERENCE" for e in result.errors)


def test_role_definition_with_no_permission_source_at_all_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("role-definition", permission_keys=[])
    result = gate.evaluate(
        "role-definition", "editor", content, _ctx(entity_type="role-definition")
    )
    assert not result.valid
    assert any(e.code == "CONFLICTING_RULE" for e in result.errors)


def test_I16_search_configuration_non_whitelisted_sort_option_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "search-configuration",
        sort_options=["QUANTUM_RANDOM"],
        default_sort="QUANTUM_RANDOM",
    )
    result = gate.evaluate(
        "search-configuration",
        "search-default",
        content,
        _ctx(entity_type="search-configuration"),
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_search_configuration_default_sort_must_be_enabled() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "search-configuration", sort_options=["RECENCY"], default_sort="RELEVANCE"
    )
    result = gate.evaluate(
        "search-configuration",
        "search-default",
        content,
        _ctx(entity_type="search-configuration"),
    )
    assert not result.valid
    assert any(e.code == "CONFLICTING_RULE" for e in result.errors)


def test_search_configuration_negative_promotion_cap_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("search-configuration", promotion_page_cap=-1)
    result = gate.evaluate(
        "search-configuration",
        "search-default",
        content,
        _ctx(entity_type="search-configuration"),
    )
    assert not result.valid
    assert any(e.code == "CONFLICTING_RULE" for e in result.errors)


def test_search_configuration_facet_on_non_facet_eligible_field_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "search-configuration",
        facets=[{"field_code": "internal_notes", "label": {"uz_latn": "Internal"}}],
    )
    ctx = _ctx(
        entity_type="search-configuration",
        dependency_exists={"facet-eligible-field:internal_notes": False},
    )
    result = gate.evaluate("search-configuration", "search-default", content, ctx)
    assert not result.valid
    assert any(e.code == "MISSING_DEPENDENCY" for e in result.errors)


def test_I16_notification_template_non_whitelisted_event_key_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("notification-template", event_key="TotallyMadeUpEvent")
    result = gate.evaluate(
        "notification-template",
        "listing-published",
        content,
        _ctx(entity_type="notification-template"),
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_I16_notification_template_non_whitelisted_channel_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("notification-template", channel="CARRIER_PIGEON")
    result = gate.evaluate(
        "notification-template",
        "listing-published",
        content,
        _ctx(entity_type="notification-template"),
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_notification_template_missing_translation_on_subject_and_body() -> None:
    gate = PreActivationGate()
    content = minimal_content("notification-template", subject={"ru": "..."}, body={"ru": "..."})
    result = gate.evaluate(
        "notification-template",
        "listing-published",
        content,
        _ctx(entity_type="notification-template"),
    )
    assert not result.valid
    codes_and_fields = {(e.code, e.field) for e in result.errors}
    assert ("MISSING_TRANSLATION", "subject") in codes_and_fields
    assert ("MISSING_TRANSLATION", "body") in codes_and_fields


def test_I16_platform_settings_non_whitelisted_settings_key_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("platform-settings", settings={"not.a.real.setting": True})
    result = gate.evaluate(
        "platform-settings", "global", content, _ctx(entity_type="platform-settings")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_platform_settings_wrong_value_type_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content("platform-settings", settings={"otp.expiry_minutes": "not-a-number"})
    result = gate.evaluate(
        "platform-settings", "global", content, _ctx(entity_type="platform-settings")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_I16_platform_settings_non_whitelisted_homepage_zone_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "platform-settings", homepage_zones=[{"zone": "ADMIN_BACKDOOR", "order": 1}]
    )
    result = gate.evaluate(
        "platform-settings", "global", content, _ctx(entity_type="platform-settings")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_I16_platform_settings_non_whitelisted_seo_page_type_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "platform-settings",
        seo_templates=[
            {"page_type": "ADMIN", "title": {"uz_latn": "Admin"}},
        ],
    )
    result = gate.evaluate(
        "platform-settings", "global", content, _ctx(entity_type="platform-settings")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_platform_settings_seo_template_missing_translation_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "platform-settings",
        seo_templates=[{"page_type": "HOME", "title": {"ru": "Главная"}}],
    )
    result = gate.evaluate(
        "platform-settings", "global", content, _ctx(entity_type="platform-settings")
    )
    assert not result.valid
    assert any(e.code == "MISSING_TRANSLATION" for e in result.errors)


def test_I16_platform_settings_non_whitelisted_static_page_key_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "platform-settings",
        static_pages=[{"page_key": "SECRET_INTERNAL_PAGE", "body": {"uz_latn": "..."}}],
    )
    result = gate.evaluate(
        "platform-settings", "global", content, _ctx(entity_type="platform-settings")
    )
    assert not result.valid
    assert any(e.code == "WHITELIST_VIOLATION" for e in result.errors)


def test_platform_settings_static_page_missing_translation_refused() -> None:
    gate = PreActivationGate()
    content = minimal_content(
        "platform-settings",
        static_pages=[{"page_key": "FAQ", "body": {"ru": "..."}}],
    )
    result = gate.evaluate(
        "platform-settings", "global", content, _ctx(entity_type="platform-settings")
    )
    assert not result.valid
    assert any(e.code == "MISSING_TRANSLATION" for e in result.errors)


def test_unknown_entity_type_is_refused() -> None:
    gate = PreActivationGate()
    result = gate.evaluate("not-a-real-entity", "x", {}, _ctx(entity_type="not-a-real-entity"))
    assert not result.valid
    assert result.errors[0].code == "UNKNOWN_ENTITY_TYPE"


def test_structurally_invalid_content_is_refused() -> None:
    gate = PreActivationGate()
    result = gate.evaluate("category", "housing", {"not": "even close"}, _ctx())
    assert not result.valid
    assert result.errors[0].code == "INVALID_STRUCTURE"


def test_invalid_validity_period_refused() -> None:
    gate = PreActivationGate()
    now = datetime.now(UTC)
    ctx, content = _publishable_form_ctx()
    ctx = GateContext(
        **{
            **ctx.__dict__,
            "validity_from": now,
            "validity_until": now - timedelta(days=1),
        }
    )
    result = gate.evaluate("category", "housing", content, ctx)
    assert not result.valid
    assert any(e.code == "INVALID_VALIDITY_PERIOD" for e in result.errors)


def test_conflicting_active_version_window_refused() -> None:
    gate = PreActivationGate()
    ctx, content = _publishable_form_ctx()
    ctx = GateContext(**{**ctx.__dict__, "conflicting_active_version_exists": True})
    result = gate.evaluate("category", "housing", content, ctx)
    assert not result.valid
    assert any(e.code == "INVALID_VALIDITY_PERIOD" for e in result.errors)
