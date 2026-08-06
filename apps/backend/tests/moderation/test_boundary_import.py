"""Proves the `cross-module-moderation` import-linter contract actually has teeth, not just that
it currently passes. Unlike every other module's own `cross-module-*` contract (which permits
importing another module's `interfaces/` package), moderation's is the STRICT case (SAD Sec 8.1:
"MAY statically import: shared_kernel (issues runtime commands via targets' interfaces)") -- it
forbids ALL 12 other bounded-context modules outright, including their `interfaces/` packages, so
this test parametrizes over a representative sample of them rather than just one. Mirrors
`apps/backend/tests/profiles/test_boundary_import.py`'s pattern exactly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = (
    _REPO_ROOT / "apps/backend/src/moderation/infrastructure/_boundary_violation_probe.py"
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


def test_I01_cross_module_moderation_contract_currently_passes() -> None:
    result = _run_contract("cross-module-moderation")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


@pytest.mark.parametrize(
    "forbidden_module", ["catalog", "identity", "profiles", "configuration", "billing"]
)
def test_I02_a_deliberate_forbidden_import_breaks_the_contract_then_reverts(
    forbidden_module: str,
) -> None:
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite; a previous run of this test "
        "may have failed to clean up"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_boundary_import.py -- proves the '
        "cross-module-moderation import-linter contract rejects a static "
        f'`{forbidden_module}` import from anywhere under `moderation/`."""\n'
        "from __future__ import annotations\n\n"
        f"import {forbidden_module}  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-moderation")
        assert violated.returncode != 0, (
            f"expected the cross-module-moderation contract to BREAK on a deliberate `import "
            f"{forbidden_module}`, but lint-imports still passed:\n"
            + violated.stdout
            + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("cross-module-moderation")
    assert reverted.returncode == 0, (
        "cross-module-moderation contract did not return to KEPT after removing the scratch "
        "probe:\n" + reverted.stdout + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout


@pytest.mark.parametrize("forbidden_module", ["catalog.interfaces", "identity.interfaces"])
def test_I03_even_a_narrow_interfaces_only_import_breaks_the_contract(
    forbidden_module: str,
) -> None:
    """The distinguishing case versus every other module's own `cross-module-*` contract:
    moderation may not import even a target module's `interfaces/` package (its own narrow
    Protocols in `application/ports.py` exist precisely because this door is closed)."""
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_boundary_import.py."""\n'
        "from __future__ import annotations\n\n"
        f"import {forbidden_module}  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-moderation")
        assert violated.returncode != 0
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()
