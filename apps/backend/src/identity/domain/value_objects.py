"""identity -- value objects (DDD Sec 5.1: PhoneNumber, EmailAddress, AccountStatus,
PrivacySettings, NotificationPreferences). Pure data + construction-time validation only; no
I/O, no ORM, no framework dependency (Clean Architecture rule 1: domain/ imports shared_kernel
only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_E164_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidPhoneNumberError(ValueError):
    """Raised by `PhoneNumber` when the value is not a valid E.164 number."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(f"{value!r} is not a valid E.164 phone number")


class InvalidEmailAddressError(ValueError):
    """Raised by `EmailAddress` when the value is not a structurally valid address."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(f"{value!r} is not a valid email address")


@dataclass(frozen=True)
class PhoneNumber:
    """E.164 phone number (DDD Sec 5.1). Validates on construction -- never a bare `str` past the
    domain boundary."""

    value: str

    def __post_init__(self) -> None:
        if not _E164_PATTERN.match(self.value):
            raise InvalidPhoneNumberError(self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EmailAddress:
    """Email address (DDD Sec 5.1), case-normalised (lower-cased) so uniqueness checks and
    lookups are consistent regardless of how the caller typed it."""

    value: str

    def __post_init__(self) -> None:
        normalised = self.value.strip().lower()
        if not _EMAIL_PATTERN.match(normalised):
            raise InvalidEmailAddressError(self.value)
        object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value


class AccountStatus(StrEnum):
    """DDD Sec 5.1 `AccountStatus` VO. Closed set -- matches the frozen `Account`/`UserAdminView`
    DTO literal (contracts/openapi.yaml)."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class AccountKind(StrEnum):
    """ADR-0007 VO `AccountKind` -- the platform-facing role chosen at signup, orthogonal to
    `AccountStatus` (which stays ACTIVE/SUSPENDED/CLOSED, unchanged). Distinct from
    `profiles.ProfileType`: that enum is a closed, business-only vocabulary (ADR-0002 deliberately
    removed an individual-type value from it), so `INDIVIDUAL`/`INVESTOR` -- neither of which is a
    *business profile* type -- live here instead, on the account itself."""

    INDIVIDUAL = "INDIVIDUAL"
    LEGAL_ENTITY = "LEGAL_ENTITY"
    INVESTOR = "INVESTOR"


class RegistrationReviewStatus(StrEnum):
    """ADR-0007 VO `RegistrationReviewStatus` -- gates access to the account's role-specific
    workspace (not login itself, which `AccountStatus.ACTIVE` already governs unchanged). Mirrors
    `profiles.domain.value_objects.CaseStatus`'s terminal shape one level simpler (no IN_REVIEW
    step -- a human reviewer decides directly from PENDING, FR scope for this task)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


TERMINAL_REVIEW_STATUSES = frozenset(
    {RegistrationReviewStatus.APPROVED, RegistrationReviewStatus.REJECTED}
)


@dataclass(frozen=True)
class RegistrationDecision:
    """ADR-0007 VO `RegistrationDecision` (outcome, reason, reviewer id, timestamp) -- mirrors
    `profiles.domain.value_objects.Decision` exactly."""

    outcome: RegistrationReviewStatus
    """`APPROVED` or `REJECTED` only -- never `PENDING` (enforced by `UserAccount.decide_
    registration`'s own parameter type, not re-checked here)."""
    reason: str | None
    reviewer_user_id: UUID
    decided_at: datetime


class PhoneRevealMode(StrEnum):
    """BRULE-13 phone-reveal gating (FR-USER-003), matches `PrivacySettings.phoneRevealMode`."""

    ALWAYS = "ALWAYS"
    ON_REQUEST = "ON_REQUEST"
    NEVER = "NEVER"


class AuthMethodType(StrEnum):
    """DDD Sec 5.1 `AuthenticationMethod` entity kinds (FR-AUTH-001..003)."""

    PHONE_OTP = "PHONE_OTP"
    EMAIL = "EMAIL"
    GOOGLE = "GOOGLE"
    APPLE = "APPLE"


class OtpPurpose(StrEnum):
    """Matches `OtpRequest.purpose` / `OtpVerifyRequest.purpose` (contracts/openapi.yaml).
    LINK_PHONE is the one authenticated exception -- REGISTRATION/LOGIN/RECOVERY are all pre-auth,
    resolved purely from the phone; LINK_PHONE proves ownership of a phone for an *already
    signed-in* account (see `/me/phone/otp*`), so it's issued/consumed against an account_id, not
    a `get_by_phone` lookup."""

    REGISTRATION = "REGISTRATION"
    LOGIN = "LOGIN"
    RECOVERY = "RECOVERY"
    LINK_PHONE = "LINK_PHONE"


@dataclass(frozen=True)
class PrivacySettings:
    """DDD Sec 5.1 VO. Matches `PrivacySettings` DTO 1:1."""

    phone_reveal_mode: PhoneRevealMode = PhoneRevealMode.ON_REQUEST


@dataclass(frozen=True)
class NotificationPreferences:
    """DDD Sec 5.1 VO. OTP is always delivered via SMS regardless of `sms` (Security Sec 3.1
    OtpChannelPolicy) -- enforced by the OTP send path never consulting this VO, not by a flag
    here."""

    email: bool = True
    web_push: bool = False
    sms: bool = True
