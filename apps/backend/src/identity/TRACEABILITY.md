# identity -- requirement traceability matrix (Task P-05)

Maps each requirement/invariant this module satisfies to its implementing code and the named
test that proves it. First matrix of this kind in the repo -- later modules add their own file in
the same shape rather than inventing a different format.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-AUTH-001 | Phone-OTP registration | `identity.application.AuthenticationUseCases.request_otp`/`verify_otp`; `identity.domain.OtpChallenge` | `test_otp_challenge.py`, `test_auth_use_cases.py::test_verify_otp_registration_creates_new_account` |
| FR-AUTH-002 | Email registration | `AuthenticationUseCases.register_email`; `UserAccount.register_via_email` | `test_auth_use_cases.py::test_register_email_creates_account`, `test_register_email_duplicate_raises` |
| FR-AUTH-003 | Google federated sign-in, link not duplicate (I-09) | `AuthenticationUseCases.login_google`; `UserAccount.register_via_google`/`link_google_identity` | `test_auth_use_cases.py::test_login_google_creates_account_when_none_exists`, `test_login_google_links_existing_account_by_verified_email` |
| FR-AUTH-004 | Authenticate a registered user via any method | `AuthenticationUseCases.verify_otp`/`login_email`/`login_google` | `test_auth_use_cases.py` (login success/failure cases) |
| FR-AUTH-005 | Session management, logout terminates | `identity.domain.Session`; `AuthenticationUseCases.logout` | `test_session.py`, `test_auth_use_cases.py::test_logout_deletes_session` |
| FR-AUTH-006 | Credential recovery via verified phone/email | `AuthenticationUseCases.start_recovery` | `test_auth_use_cases.py::test_start_recovery_*` (see README "Known gaps" #2 for the email-completion gap) |
| FR-USER-001 | View/edit personal profile | `AccountUseCases.get_me`/`update_me` | `test_account_use_cases.py::test_get_me_returns_account`, `test_update_me_changes_display_name` |
| FR-USER-002 | Multiple business profiles, switch acting context | `identity.domain.Session.switch_acting_profile`; `AccountUseCases.switch_acting_profile` | `test_session.py::test_switch_acting_profile_*`, `test_account_use_cases.py::test_switch_acting_profile_*` |
| FR-USER-003 | Phone-reveal privacy control (BRULE-13) | `identity.domain.PrivacySettings`; `AccountUseCases.update_preferences`; `ContactPolicyPortAdapter` | `test_account_use_cases.py::test_update_preferences_changes_privacy_and_notifications`, `test_public_port_adapters.py::test_contact_policy_*` |
| FR-USER-005 | Account closure = anonymise + retain | `UserAccount.close`; `AccountUseCases.close_account` | `test_user_account.py::test_close_anonymises_pii_and_sets_closed_status`, `test_account_use_cases.py::test_close_account_anonymises_and_revokes_sessions` |

## Non-functional / business rules

| Requirement | Summary | Code | Test |
|---|---|---|---|
| NFR-SEC-001 | Default-deny authorization | `identity.domain.AuthorizationService.authorize` | `test_authorization.py::test_I10_default_deny_operation_with_zero_permissions_is_denied` |
| NFR-SEC-004 | OTP throttled per-phone/per-IP | `identity.domain.policies.OtpThrottlePolicy` | `test_policies.py::test_I_otp_throttle_denies_when_phone_request_count_at_limit`, `test_auth_use_cases.py::test_I_otp_throttle_request_otp_denies_after_limit` |
| BRULE-13 | Phone-reveal gating modes | `identity.domain.value_objects.PhoneRevealMode` | `test_value_objects.py`, `test_public_port_adapters.py` |
| Security Sec 3.1 | OTP single-use | `OtpChallenge.verify` (consumed_at guard) | `test_otp_challenge.py::test_I_otp_single_use_second_verify_against_consumed_challenge_raises`, `test_auth_use_cases.py::test_I_otp_single_use_verify_otp_rejects_second_attempt_with_same_code` |
| Security Sec 3.1 | Argon2id password hashing | `identity.infrastructure.security.Argon2PasswordHasherAdapter` | `test_security.py` |
| Security Sec 3.2 | Server-side sessions, no JWT (SDR-01) | `identity.domain.Session`; `identity.infrastructure.session_store.RedisSessionRepository` | `test_session.py`, `integration/test_session_store_live.py` |
| Security Sec 12 | No secrets/PII in logs | No logger call in this module ever receives a raw OTP code, password, or session token (see `identity.domain.otp_challenge` module docstring) | Verified by code inspection; `backbone.logging.redaction` covers structured `extra=` keys |

## Domain invariants (DDD Sec 9)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-09 | Phone/email unique platform-wide; Google links, never duplicates | `identity.domain.exceptions.DuplicateContactError`; partial unique indexes (`user_account.phone`/`.email`); `UserAccount.link_google_identity` | `test_auth_use_cases.py::test_register_email_duplicate_raises`, `test_user_account.py::test_link_google_identity_adds_method_to_existing_account_without_duplicating`, `integration/test_repository_live.py::test_partial_unique_constraint_on_phone` |
| I-10 | Cross-profile access denied by default | `AuthorizationService.authorize` (owner_profile_id/owner_account_id gate) | `test_authorization.py::test_I10_*` (four tests) |
| I-11 | Permission scoped to acting profile, no leakage; permission semantics immutable at runtime (no escalation) | `AuthorizationService.authorize`; `ApplicationAuthorizationService.effective_permissions` | `test_authorization.py::test_I11_*` (four tests), `test_authorization_service.py::test_effective_permissions_excludes_other_profile_scoped_roles` |

## Validation checklist cross-reference (P-05 prompt)

| Checklist item | Evidence |
|---|---|
| Default-deny proven (structural, not accidental) | `test_authorization.py::test_I10_default_deny_operation_with_zero_permissions_is_denied` -- `AuthorizationService.authorize` has exactly one success path; every other branch raises |
| Per-acting-profile scoping proven | `test_authorization.py::test_I11_permission_granted_under_profile_a_denied_when_acting_as_profile_b` |
| Escalation attempt blocked | `test_authorization.py::test_I11_escalation_attempt_via_unrelated_granted_key_is_blocked` |
| OTP single-use | `test_otp_challenge.py::test_I_otp_single_use_*`, `test_auth_use_cases.py::test_I_otp_single_use_*` |
| OTP throttle | `test_policies.py::test_I_otp_throttle_*`, `test_auth_use_cases.py::test_I_otp_throttle_*` |
| Sessions server-side only, no JWT | `identity.domain.session.py` module docstring; grep of this module for `jwt`/`JWT` returns nothing outside comments explaining its absence |
| No OTP/token/password/PII in logs | No `logging`/`logger` call in `identity/` interpolates a raw secret (code inspection); `backbone.logging.redaction` backstops structured fields |
| Eskiz/Google SDK types confined to infrastructure/ | `provider-sdk-confined-to-infrastructure` import-linter contract (KEPT); `identity.infrastructure.providers.{eskiz,google_oauth}.py` are the only files touching `httpx` calls to those providers |
| identity imports only shared_kernel + configuration | `cross-module-identity` import-linter contract (KEPT) |
| Every Authentication/Users operation implemented, no drift | `tools/check_contract_drift.py` (fixed for FastAPI 0.139's lazy router wrapping -- see README "Known gaps" #5); zero identity routes reported as drift |
| Authorization matrix harness exists, extensible | `tests/authorization_matrix.py` + `tests/test_authorization_matrix.py`; `tests/README.md` updated |
| Coverage floors | `scripts/coverage.sh` -- 92%+ overall, 90%+ every domain/application file (QG-04 passed) |
| mypy --strict / ruff / import-linter clean | See README "Coverage / quality gates" |
