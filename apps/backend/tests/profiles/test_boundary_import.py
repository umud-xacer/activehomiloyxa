"""Proves the `cross-module-profiles` import-linter contract actually has teeth, not just that it
currently passes. P-11's own Validation Checklist: "profiles does NOT statically import billing;
import-linter enforces this (verify with a deliberate violation, then revert)." Also proves
`profiles` imports ONLY `shared_kernel, identity, media` (a `configuration` import breaks the same
contract). Mirrors `apps/backend/tests/billing/test_boundary_import.py`'s own pattern exactly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = (
    _REPO_ROOT / "apps/backend/src/profiles/infrastructure/_boundary_violation_probe.py"
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


def test_I01_cross_module_profiles_contract_currently_passes() -> None:
    result = _run_contract("cross-module-profiles")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


@pytest.mark.parametrize("forbidden_module", ["billing", "configuration", "catalog"])
def test_I02_a_deliberate_forbidden_import_breaks_the_contract_then_reverts(
    forbidden_module: str,
) -> None:
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite; a previous run of this test "
        "may have failed to clean up"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_boundary_import.py -- proves the cross-module-profiles '
        f"import-linter contract rejects a static `{forbidden_module}` import from anywhere under "
        '`profiles/`."""\n'
        "from __future__ import annotations\n\n"
        f"import {forbidden_module}  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-profiles")
        assert violated.returncode != 0, (
            f"expected the cross-module-profiles contract to BREAK on a deliberate `import "
            f"{forbidden_module}`, but lint-imports still passed:\n"
            + violated.stdout
            + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("cross-module-profiles")
    assert reverted.returncode == 0, (
        "cross-module-profiles contract did not return to KEPT after removing the scratch probe:\n"
        + reverted.stdout
        + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout
