"""Proves the descope seam (DEC-23) has teeth, not just that it currently holds -- the P-14
task's own explicit requirement: "deleting the ads/ module must break only its own tests and
admin screens... a CI-verifiable property that proves isolation is real" (the AI-Assisted-
Development-and-Engineering-Playbook's own wording).

`test_I01`/`test_I03`/`test_I04` prove the `cross-module-ads`/`billing-catalog-profiles-ads-no-
cycle`/`no-infra-inbound-ads` import-linter contracts (`tools/importlinter.cfg`) currently pass.
`test_I02` proves `cross-module-ads` actually rejects a deliberate forbidden import (billing),
mirroring `apps/backend/tests/billing/test_boundary_import.py`'s own pattern exactly.

`test_I05`/`test_I06` are the signature descope-isolation tests this task specifically requires:
a static, repo-wide proof that NO file outside `ads/` itself statically imports it, except the
two files that are allowed and expected to (`composition_root.py`, the one place every module's
internals may be wired together, and `main.py`, which mounts every module's router) -- i.e.
"nothing outside it depends on it" (SAD Sec 8.1) is asserted directly, not merely inferred from
the per-module contracts above never happening to list a counter-example.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = _REPO_ROOT / "apps/backend/src/ads/infrastructure/_boundary_violation_probe.py"
_IMPORTLINTER_CONFIG = _REPO_ROOT / "tools/importlinter.cfg"
_LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")

# Every file allowed to statically import `ads` -- the composition root (which is allowed to see
# every module's internals, by construction) and the FastAPI app entrypoint that mounts its
# router. Nothing else may appear here without this test failing.
_ALLOWED_IMPORTERS = {
    _REPO_ROOT / "apps/backend/src/composition_root.py",
    _REPO_ROOT / "apps/backend/src/main.py",
}


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


def test_I01_cross_module_ads_contract_currently_passes() -> None:
    result = _run_contract("cross-module-ads")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I02_a_deliberate_billing_import_breaks_the_contract_then_reverts() -> None:
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite; a previous run of this test "
        "may have failed to clean up"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_boundary_import.py -- proves the cross-module-ads '
        "import-linter contract rejects a static `billing` import from anywhere under "
        '`ads/`."""\n'
        "from __future__ import annotations\n\n"
        "import billing  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-ads")
        assert violated.returncode != 0, (
            "expected the cross-module-ads contract to BREAK on a deliberate `import billing`, "
            "but lint-imports still passed:\n" + violated.stdout + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("cross-module-ads")
    assert reverted.returncode == 0, (
        "cross-module-ads contract did not return to KEPT after removing the scratch probe:\n"
        + reverted.stdout
        + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout


def test_I03_billing_catalog_profiles_ads_no_cycle_contract_currently_passes() -> None:
    result = _run_contract("billing-catalog-profiles-ads-no-cycle")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I04_no_infra_inbound_ads_contract_currently_passes() -> None:
    """`ads.interfaces`/`ads.application`/`ads.domain` never import `ads.infrastructure` (DIP) --
    the composition root is the only place that wires the concrete adapters in."""
    result = _run_contract("no-infra-inbound-ads")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def _every_python_file_outside_ads() -> list[Path]:
    roots = [
        _REPO_ROOT / "apps/backend/src",
        _REPO_ROOT / "apps/backend/tests",
    ]
    files = []
    ads_src = _REPO_ROOT / "apps/backend/src/ads"
    ads_tests = _REPO_ROOT / "apps/backend/tests/ads"
    for root in roots:
        for path in root.rglob("*.py"):
            if ads_src in path.parents or ads_tests in path.parents:
                continue
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_I05_no_other_module_statically_imports_ads() -> None:
    """The descope-seam signature test: a repo-wide grep proving `import ads`/`from ads` appears
    in exactly the two files allowed to see it. If this test starts failing on a new file, that
    file is a new, undocumented static dependency on `ads` and must be removed -- deleting `ads/`
    would otherwise break more than "its own tests and admin screens" (Playbook's own wording)."""
    offenders: dict[Path, list[str]] = {}
    for path in _every_python_file_outside_ads():
        if path in _ALLOWED_IMPORTERS:
            continue
        text = path.read_text(encoding="utf-8")
        matches = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("import ads")
            or line.strip().startswith("from ads.")
            or line.strip().startswith("from ads import")
        ]
        if matches:
            offenders[path] = matches

    assert not offenders, (
        "the following files outside ads/ statically import it, breaking the descope seam "
        f"(DEC-23): {offenders}"
    )


def test_I06_the_two_allowed_importers_do_in_fact_import_ads() -> None:
    """The mirror-image check: `composition_root.py`/`main.py` are EXPECTED to import `ads` --
    confirms `_ALLOWED_IMPORTERS` isn't accidentally empty/stale and the wiring this task added is
    actually present, not merely absent everywhere by omission."""
    for path in _ALLOWED_IMPORTERS:
        text = path.read_text(encoding="utf-8")
        assert "ads" in text and (
            "from ads." in text or "from ads import" in text or "import ads" in text
        ), f"{path} was expected to import ads, but no such import was found"
