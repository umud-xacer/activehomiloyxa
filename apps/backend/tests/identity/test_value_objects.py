from __future__ import annotations

import pytest

from identity.domain import (
    EmailAddress,
    InvalidEmailAddressError,
    InvalidPhoneNumberError,
    PhoneNumber,
)


def test_phone_number_accepts_valid_e164() -> None:
    assert PhoneNumber("+998901234567").value == "+998901234567"


@pytest.mark.parametrize(
    "value", ["998901234567", "+0901234567", "not-a-phone", "+1", "+9989012345678901"]
)
def test_phone_number_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvalidPhoneNumberError):
        PhoneNumber(value)


def test_email_address_normalises_case_and_whitespace() -> None:
    assert EmailAddress("  Test@Example.COM  ").value == "test@example.com"


@pytest.mark.parametrize("value", ["not-an-email", "missing-domain@", "@missing-local.com", ""])
def test_email_address_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvalidEmailAddressError):
        EmailAddress(value)
