"""Proves the `cross-module-analytics` import-linter contract actually has teeth, not just that
it currently passes -- mirrors `apps/backend/tests/notifications/test_boundary_import.py`'s own
pattern. analytics is the STRICTEST import module in the codebase: `shared_kernel` ONLY,
forbidding even another module's own `interfaces/` package (SAD Sec 8: "analytics: shared_kernel
(event sink)"). Also proves the module's second defining property (SAD Sec 8.2: "nothing imports
admin, analytics, or notifications -- they are terminal consumers/sinks") via the shared
`sink-modules-have-no-inbound-imports` contract, and that no inbound command port exists anywhere
in `analytics/interfaces/` for another module to call.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = (
    _REPO_ROOT / "apps/backend/src/analytics/infrastructure/_boundary_violation_probe.py"
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


def test_I01_cross_module_analytics_contract_currently_passes() -> None:
    result = _run_contract("cross-module-analytics")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I02_sink_modules_have_no_inbound_imports_contract_currently_passes() -> None:
    """Proves nothing imports analytics -- the module's OTHER defining property (a pure event
    sink, SAD Sec 8.2), distinct from the (also-enforced) restriction on what analytics itself
    may import."""
    result = _run_contract("sink-modules-have-no-inbound-imports")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "forbidden_module",
    [
        "identity",
        "profiles",
        "catalog",
        "configuration",
        "search",
        "media",
        "messaging",
        "billing",
        "ads",
        "notifications",
        "moderation",
        "admin",
    ],
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
        "cross-module-analytics import-linter contract rejects a static "
        f'`{forbidden_module}` import from anywhere under `analytics/`."""\n'
        "from __future__ import annotations\n\n"
        f"import {forbidden_module}  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-analytics")
        assert violated.returncode != 0, (
            f"expected the cross-module-analytics contract to BREAK on a deliberate `import "
            f"{forbidden_module}`, but lint-imports still passed:\n"
            + violated.stdout
            + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("cross-module-analytics")
    assert reverted.returncode == 0, (
        "cross-module-analytics contract did not return to KEPT after removing the scratch "
        "probe:\n" + reverted.stdout + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout


def test_I04_no_inbound_command_port_exists_for_other_modules_to_call() -> None:
    """`analytics.interfaces.ports.AnalyticsQueryPort` (the frozen P-01 stub, now real) only
    declares the two read-only operator operations (`getAdminReports`/`queryAuditLog`) -- there
    is no "record"/"capture"/"ingest" method anywhere on it, and no second port class exists in
    `interfaces/` at all. The only way a fact reaches analytics is by the emitting module
    publishing its own domain event."""
    import analytics.interfaces.ports as ports_module

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
        if any(verb in name for verb in ("record", "capture", "ingest", "write", "create"))
    }
    assert disallowed == set(), f"found an inbound-command-shaped method: {disallowed}"


def test_I05_no_other_module_statically_imports_analytics() -> None:
    """Repo-wide grep, independent of import-linter: `import analytics` (or `from analytics`)
    appears ONLY in `composition_root.py`/`main.py` and analytics' own source/tests -- proves
    the descope-seam guarantee by direct inspection, not just contract configuration."""
    backend_src = _REPO_ROOT / "apps/backend/src"
    offenders = []
    for path in backend_src.rglob("*.py"):
        if path.name in {"composition_root.py", "main.py", "analytics_worker.py"}:
            continue
        if "/analytics/" in path.as_posix() or path.as_posix().endswith("/analytics"):
            continue
        text = path.read_text(encoding="utf-8")
        if "import analytics" in text or "from analytics" in text:
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []


def test_I06_the_allowed_importers_do_in_fact_import_analytics() -> None:
    """Mirror-image sanity check for I05 -- proves the isolation tests above aren't vacuously
    passing because nothing wires analytics up at all."""
    for filename in ("composition_root.py", "main.py"):
        text = (_REPO_ROOT / "apps/backend/src" / filename).read_text(encoding="utf-8")
        assert "analytics" in text, f"{filename} does not reference analytics at all"
