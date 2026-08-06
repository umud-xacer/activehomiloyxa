"""Proves the `cross-module-notifications` import-linter contract actually has teeth, not just
that it currently passes -- mirrors `apps/backend/tests/moderation/test_boundary_import.py`'s
own pattern (notifications, like moderation, is a STRICT-import module: `shared_kernel,
configuration` only, forbidding even the other modules' `interfaces/` packages). Also proves the
module's second defining property (SAD Sec 8.2: "nothing imports admin, analytics, or
notifications -- they are terminal consumers/sinks") via the separate `sink-modules-have-no-
inbound-imports` contract, and that no "send notification" port exists anywhere in
`notifications/interfaces/` for another module to call.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = (
    _REPO_ROOT / "apps/backend/src/notifications/infrastructure/_boundary_violation_probe.py"
)
_IMPORTLINTER_CONFIG = _REPO_ROOT / "tools/importlinter.cfg"
_LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")


def _run_contract(contract_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(_LINT_IMPORTS),
            "--config",
            str(_IMPORTLINTER_CONFIG),
            "--contract",
            contract_id,
            "--no-cache",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_I01_cross_module_notifications_contract_currently_passes() -> None:
    result = _run_contract("cross-module-notifications")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I02_sink_modules_have_no_inbound_imports_contract_currently_passes() -> None:
    """Proves nothing imports notifications -- the module's OTHER defining property (a pure
    event sink, SAD Sec 8.2), distinct from the (also-enforced) restriction on what notifications
    itself may import."""
    result = _run_contract("sink-modules-have-no-inbound-imports")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "forbidden_module",
    ["identity", "profiles", "catalog", "billing", "messaging", "moderation"],
)
def test_I03_a_deliberate_forbidden_import_breaks_the_contract_then_reverts(
    forbidden_module: str,
) -> None:
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite; a previous run of this test "
        "may have failed to clean up"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_boundary_import.py -- proves the '
        "cross-module-notifications import-linter contract rejects a static "
        f'`{forbidden_module}` import from anywhere under `notifications/`."""\n'
        "from __future__ import annotations\n\n"
        f"import {forbidden_module}  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-notifications")
        assert violated.returncode != 0, (
            f"expected the cross-module-notifications contract to BREAK on a deliberate `import "
            f"{forbidden_module}`, but lint-imports still passed:\n"
            + violated.stdout
            + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("cross-module-notifications")
    assert reverted.returncode == 0, (
        "cross-module-notifications contract did not return to KEPT after removing the scratch "
        "probe:\n" + reverted.stdout + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout


def test_I04_no_inbound_command_port_exists_for_other_modules_to_call() -> None:
    """`notifications.interfaces.ports.NotificationPort` (the frozen P-01 stub) only declares the
    3 user-facing read/read-status methods (`listNotifications`/`setNotificationRead`/
    `markAllNotificationsRead`) -- there is no "send"/"dispatch"/"notify" method anywhere on it,
    and no second port class exists in `interfaces/` at all. The only way another module's action
    reaches notifications is by publishing its own domain event."""
    import notifications.interfaces.ports as ports_module

    port_classes = [
        getattr(ports_module, name)
        for name in dir(ports_module)
        if name.endswith("Port") and not name.startswith("_")
    ]
    assert len(port_classes) == 1, "expected exactly one Protocol declared in interfaces/ports.py"

    method_names = {name for name in dir(port_classes[0]) if not name.startswith("_")}
    disallowed = {
        name
        for name in method_names
        if any(verb in name for verb in ("send", "dispatch", "notify", "trigger", "publish"))
    }
    assert disallowed == set(), f"found an inbound-command-shaped method: {disallowed}"


def test_I05_provider_sdk_confined_to_infrastructure_contract_currently_passes() -> None:
    """DEC-18: no provider SDK type (`httpx`, `smtplib`, `pywebpush`) may cross
    `notifications.interfaces`/`notifications.application`'s own boundary -- confined to
    `notifications.infrastructure.providers.*` only. This contract already covers every module;
    this test just asserts it explicitly for notifications' own three new provider adapters."""
    result = _run_contract("provider-sdk-confined-to-infrastructure")
    assert result.returncode == 0, result.stdout + result.stderr


def test_I06_no_provider_sdk_import_appears_outside_infrastructure_providers() -> None:
    """Direct source inspection, independent of import-linter: `httpx`/`smtplib`/`pywebpush`
    appear ONLY inside `notifications/infrastructure/providers/*.py` anywhere in this module."""
    notifications_src = _REPO_ROOT / "apps/backend/src/notifications"
    sdk_markers = (
        "import httpx",
        "import smtplib",
        "import pywebpush",
        "from pywebpush",
    )
    offenders = []
    for path in notifications_src.rglob("*.py"):
        if "infrastructure/providers" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in sdk_markers):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []
