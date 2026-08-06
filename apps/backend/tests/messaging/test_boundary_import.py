"""Proves the `cross-module-messaging` import-linter contract (`tools/importlinter.cfg`) actually
has teeth, not just that it currently passes. P-10's own Validation Checklist: "messaging imports
ONLY shared_kernel and identity -- import-linter enforces this and would catch a catalog import
(verify with a deliberate violation, then revert)."

Writes a scratch module INSIDE `messaging/infrastructure/` (never an existing production file)
containing `import catalog`, runs `lint-imports` scoped to just the `cross-module-messaging`
contract, and asserts it now reports BROKEN -- then deletes the scratch file in a `finally` block
so this test never leaves the tree dirty, and re-runs the contract to confirm it is KEPT again
afterward. Mirrors `apps/backend/tests/billing/test_boundary_import.py`'s own pattern exactly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = (
    _REPO_ROOT / "apps/backend/src/messaging/infrastructure/_boundary_violation_probe.py"
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


def test_I01_cross_module_messaging_contract_currently_passes() -> None:
    result = _run_contract("cross-module-messaging")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I02_a_deliberate_catalog_import_breaks_the_contract_then_reverts() -> None:
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite; a previous run of this test "
        "may have failed to clean up"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_boundary_import.py -- proves the cross-module-'
        "messaging import-linter contract rejects a static `catalog` import from anywhere under "
        '`messaging/`."""\n'
        "from __future__ import annotations\n\n"
        "import catalog  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-messaging")
        assert violated.returncode != 0, (
            "expected the cross-module-messaging contract to BREAK on a deliberate `import "
            "catalog`, but lint-imports still passed:\n" + violated.stdout + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("cross-module-messaging")
    assert reverted.returncode == 0, (
        "cross-module-messaging contract did not return to KEPT after removing the scratch "
        "probe:\n" + reverted.stdout + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout
