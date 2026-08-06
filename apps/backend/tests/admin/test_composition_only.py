"""P-16's own required, CI-verifiable proofs for admin's composition-only nature (SAD Sec 7.2:
"admin owns no marketplace aggregate"; Absolute Architecture Rule 4: "no side-effect modification
of other modules").

- `test_I01`/`test_I02`/`test_I03` prove the `cross-module-admin`/`layers-admin`/
  `no-infra-inbound-admin` import-linter contracts (`tools/importlinter.cfg`) currently pass.
- `test_I04` proves `cross-module-admin` actually rejects a deliberate forbidden import
  (`moderation.application`, a layer no module but moderation's own router may see), mirroring
  `apps/backend/tests/ads/test_boundary_import.py`'s own pattern exactly.
- `test_I05` is the "nothing imports admin" signature test: a static, repo-wide proof that no
  file outside `admin/` itself statically imports it, except the two files allowed to
  (`composition_root.py`, `main.py`) -- confirms `sink-modules-have-no-inbound-imports` holds by
  direct inspection, not merely by the import-linter contract never having a counter-example yet.
- `test_composition_only_domain_has_exactly_one_entity` is the module's own documented
  requirement (`admin/domain/__init__.py`'s own docstring): the domain package defines
  `OperatorSessionContext` and nothing else, ever -- admin owns no marketplace aggregate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import admin.domain as admin_domain_package

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRATCH_MODULE = _REPO_ROOT / "apps/backend/src/admin/infrastructure/_boundary_violation_probe.py"
_IMPORTLINTER_CONFIG = _REPO_ROOT / "tools/importlinter.cfg"
_LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")

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


def test_I01_cross_module_admin_contract_currently_passes() -> None:
    result = _run_contract("cross-module-admin")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I02_layers_admin_contract_currently_passes() -> None:
    result = _run_contract("layers-admin")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I03_no_infra_inbound_admin_contract_currently_passes() -> None:
    result = _run_contract("no-infra-inbound-admin")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 kept, 0 broken" in result.stdout


def test_I04_a_deliberate_moderation_application_import_breaks_the_contract_then_reverts() -> None:
    assert not _SCRATCH_MODULE.exists(), (
        f"{_SCRATCH_MODULE} already exists -- refusing to overwrite; a previous run of this "
        "test may have failed to clean up"
    )
    _SCRATCH_MODULE.write_text(
        '"""Scratch probe, deleted by test_composition_only.py -- proves the cross-module-admin '
        "import-linter contract rejects a static `moderation.application` import from anywhere "
        'under `admin/` (only moderation.interfaces is allowed).""" \n'
        "from __future__ import annotations\n\n"
        "import moderation.application  # noqa: F401  the deliberate violation under test\n"
    )
    try:
        violated = _run_contract("cross-module-admin")
        assert violated.returncode != 0, (
            "expected cross-module-admin to BREAK on a deliberate `import moderation.application`,"
            " but lint-imports still passed:\n" + violated.stdout + violated.stderr
        )
        assert "1 kept, 0 broken" not in violated.stdout
    finally:
        _SCRATCH_MODULE.unlink()

    reverted = _run_contract("cross-module-admin")
    assert reverted.returncode == 0, (
        "cross-module-admin did not return to KEPT after removing the scratch probe:\n"
        + reverted.stdout
        + reverted.stderr
    )
    assert "1 kept, 0 broken" in reverted.stdout


def _every_python_file_outside_admin() -> list[Path]:
    roots = [_REPO_ROOT / "apps/backend/src", _REPO_ROOT / "apps/backend/tests"]
    admin_src = _REPO_ROOT / "apps/backend/src/admin"
    admin_tests = _REPO_ROOT / "apps/backend/tests/admin"
    files = []
    for root in roots:
        for path in root.rglob("*.py"):
            if admin_src in path.parents or admin_tests in path.parents:
                continue
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_I05_no_other_module_statically_imports_admin() -> None:
    """Mirrors `sink-modules-have-no-inbound-imports` by direct repo-wide inspection: "nothing
    imports admin" (SAD's own module table) is asserted directly, not merely inferred from the
    import-linter contract never having failed yet."""
    offenders: dict[Path, list[str]] = {}
    for path in _every_python_file_outside_admin():
        if path in _ALLOWED_IMPORTERS:
            continue
        text = path.read_text(encoding="utf-8")
        matches = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("import admin")
            or line.strip().startswith("from admin.")
            or line.strip().startswith("from admin import")
        ]
        if matches:
            offenders[path] = matches

    assert not offenders, f"the following files outside admin/ statically import it: {offenders}"


def test_I06_the_two_allowed_importers_do_in_fact_import_admin() -> None:
    for path in _ALLOWED_IMPORTERS:
        text = path.read_text(encoding="utf-8")
        assert "admin" in text and (
            "from admin." in text or "from admin import" in text or "import admin" in text
        ), f"{path} was expected to import admin, but no such import was found"


def test_composition_only_domain_has_exactly_one_entity() -> None:
    """`admin/domain/__init__.py`'s own docstring: "the domain package defines
    `OperatorSessionContext` and nothing else, ever -- admin owns no marketplace aggregate." A
    second entity type appearing here would be admin quietly growing an owned aggregate, which
    SAD Sec 7.2 forbids."""
    assert admin_domain_package.__all__ == ["OperatorSessionContext"]
