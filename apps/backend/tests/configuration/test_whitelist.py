"""`WhitelistRegistry` -- the BoundedConfigurationPolicy membership half (I-16). One test per
closed vocabulary: a whitelisted value passes, a non-member is refused."""

from __future__ import annotations

import pytest

from configuration.domain.whitelist import WhitelistRegistry, WhitelistViolationError


@pytest.fixture
def registry() -> WhitelistRegistry:
    return WhitelistRegistry()


@pytest.mark.parametrize(
    "checker_name,valid_value,invalid_value",
    [
        ("check_field_type", "text", "rich_html"),
        ("check_validator_type", "required", "arbitrary_regex"),
        ("check_condition_operator", "EQUALS", "MATCHES_REGEX"),
        ("check_product_type", "SUBSCRIPTION", "CRYPTO_PAYMENT"),
        ("check_notification_channel", "EMAIL", "CARRIER_PIGEON"),
        ("check_event_key", "ListingPublished", "SomethingNeverCatalogued"),
        (
            "check_permission_key",
            "config:category:manage",
            "config:category:delete-everything",
        ),
        ("check_sort_option", "RELEVANCE", "RANDOM"),
        ("check_page_zone", "HOMEPAGE_HERO", "ADMIN_BACKDOOR"),
        ("check_rendering_hint", "DROPDOWN", "AUTO_EXECUTE_JS"),
        ("check_static_page_key", "PRIVACY_POLICY", "SECRET_INTERNAL_PAGE"),
        ("check_seo_page_type", "CATEGORY", "ADMIN"),
    ],
)
def test_I16_whitelist_accepts_member_rejects_non_member(
    registry: WhitelistRegistry, checker_name: str, valid_value: str, invalid_value: str
) -> None:
    checker = getattr(registry, checker_name)
    checker(valid_value)  # does not raise
    with pytest.raises(WhitelistViolationError):
        checker(invalid_value)


def test_I16_settings_key_enforces_declared_type(registry: WhitelistRegistry) -> None:
    registry.check_settings_key("otp.expiry_minutes", 5)
    with pytest.raises(WhitelistViolationError):
        registry.check_settings_key("otp.expiry_minutes", "five")  # wrong type
    with pytest.raises(WhitelistViolationError):
        registry.check_settings_key("not.a.real.key", 5)  # unknown key


def test_manage_and_approve_permission_key_format(registry: WhitelistRegistry) -> None:
    assert registry.manage_permission_key("category") == "config:category:manage"
    assert registry.approve_permission_key("category") == "config:category:approve"


def test_I16_event_key_whitelist_has_zero_drift_from_frozen_event_catalogue() -> None:
    """`domain/whitelist.py`'s own docstring commits to this check: EVENT_KEYS is "a literal,
    hand-kept copy" of `contracts/events/*.py`'s 47-event catalogue (Task P-01), and any drift
    between the two must be caught here, at test scope -- `domain/` itself may not import
    `contracts` (Clean Architecture rule 1)."""
    from configuration.domain.whitelist import EVENT_KEYS
    from contracts.events import EVENT_CATALOGUE

    assert frozenset(EVENT_CATALOGUE.keys()) == EVENT_KEYS


def test_I16_permission_keys_are_colon_namespaced() -> None:
    """I-16: every catalogue entry is a fixed, code-defined `<module>:<resource>:<verb>` key.
    `config:*` keys are further constrained to the maker/checker manage/approve shape (Config
    Framework Sec 2.3); other modules (identity P-05, ...) extend the catalogue with their own
    verbs per this file's own comment ("designed to be extended, not exhaustive")."""
    from configuration.domain.whitelist import PERMISSION_KEYS

    for key in PERMISSION_KEYS:
        parts = key.split(":")
        assert len(parts) == 3 and all(parts)
        if parts[0] == "config":
            assert parts[2] in ("manage", "approve")
