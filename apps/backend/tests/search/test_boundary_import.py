"""Proves the `search-scope`/`cross-module-search` import-linter contracts (`tools/importlinter.
cfg`) actually have teeth, not just that they currently pass. P-08's own Validation Checklist:
"search imports ONLY shared_kernel+configuration (verified with import-linter + a
deliberate-violation-then-revert test)."

Writes a scratch module INSIDE `search/infrastructure/` (never an existing production file)
containing `import catalog`, runs `lint-imports` scoped to just the `search-scope` contract, and
asserts it now reports BROKEN -- then deletes the scratch file in a `finally` block so this test
never leaves the tree dirty, and re-runs the contract to confirm it is KEPT again afterward. This
is the module-level analogue of `test_event_projection.py`'s "the check would have caught it"
discipline, aimed at the CRITICAL BOUNDARY RULE itself rather than one handler.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = _REPO_ROOT / "apps/backend/src/search/infrastructure/_boundary_violation_probe.py"
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


def test_I01_search_scope_contract_currently_passes() -> None:
    result = _run_contract("search-scope")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I02_a_deliberate_catalog_import_breaks_the_search_scope_contract_then_reverts() -> None:
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite; a previous run of this test "
        "may have failed to clean up"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_boundary_import.py -- proves the search-scope import-'
        'linter contract rejects a static `catalog` import from anywhere under `search/`."""\n'
        "from __future__ import annotations\n\n"
        "import catalog  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("search-scope")
        assert violated.returncode != 0, (
            "expected the search-scope contract to BREAK on a deliberate `import catalog`, but "
            "lint-imports still passed:\n" + violated.stdout + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("search-scope")
    assert reverted.returncode == 0, (
        "search-scope contract did not return to KEPT after removing the scratch probe:\n"
        + reverted.stdout
        + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout
