"""The release-blocking authorization allow/deny matrix suite (tests/README.md: "belongs here",
TEST-02, QG-08). Runs every module's contributed `AuthorizationScenario` list through the shared
harness at `tests/authorization/matrix.py`. Identity (P-05) seeded the first scenarios; P-20
consolidates every module's own accumulated list (catalog, billing, profiles, moderation, ads,
analytics, admin) into this ONE suite, covering every permission key that is checked through
`identity.domain.AuthorizationService.authorize` (`matrix.py`'s own module docstring explains the
two permission-key families this suite deliberately does NOT cover, and why).
"""

from __future__ import annotations

from tests.authorization.matrix import (
    ADMIN_MATRIX,
    ADS_MATRIX,
    ANALYTICS_MATRIX,
    BILLING_MATRIX,
    CATALOG_MATRIX,
    IDENTITY_MATRIX,
    MODERATION_MATRIX,
    PROFILES_MATRIX,
    run_authorization_matrix,
)

SCENARIOS = [
    *IDENTITY_MATRIX,
    *CATALOG_MATRIX,
    *BILLING_MATRIX,
    *PROFILES_MATRIX,
    *MODERATION_MATRIX,
    *ADS_MATRIX,
    *ANALYTICS_MATRIX,
    *ADMIN_MATRIX,
]
"""Every permission key checked via `identity.domain.AuthorizationService.authorize` anywhere in
`composition_root.py` -- cross-checked exhaustively by
`test_every_authorization_service_call_site_permission_key_is_covered` below."""


def test_authorization_allow_deny_matrix() -> None:
    run_authorization_matrix(SCENARIOS)


def test_every_authorization_service_call_site_permission_key_is_covered() -> None:
    """P-20's own consolidation proof: greps `composition_root.py` for every literal permission
    key passed to `AuthorizationService().authorize(context, "...")` and asserts each one has at
    least one scenario in `SCENARIOS` above -- so a future module that wires a NEW permission key
    through this same mechanism, but forgets to extend the matrix, fails this test instead of
    silently shipping an unverified gate."""
    import re
    from pathlib import Path

    composition_root = (
        Path(__file__).resolve().parents[2] / "apps/backend/src/composition_root.py"
    ).read_text(encoding="utf-8")
    called_keys = set(
        re.findall(
            r'AuthorizationService\(\)\.authorize\(\s*context,\s*"([^"]+)"', composition_root
        )
    )
    assert called_keys, "no AuthorizationService().authorize(...) call sites found -- regex broken?"

    covered_keys = {scenario.required_permission for scenario in SCENARIOS}
    missing = called_keys - covered_keys
    assert not missing, (
        f"composition_root.py checks these permission keys via AuthorizationService.authorize "
        f"but no AuthorizationScenario in tests/authorization/matrix.py covers them: {missing}"
    )
