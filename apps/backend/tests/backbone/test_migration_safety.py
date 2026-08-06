"""tools/check_migration_safety.py (QG-09; AIR-14: "an applied migration is never edited";
DevSecOps Sec 7). Runs the real script as a subprocess against a throwaway git repository built
fresh for each test -- never against this actual repository's history."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
CHECKER = REPO_ROOT / "tools" / "check_migration_safety.py"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True
    )


def _run_checker(cwd: Path, base_ref: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--base-ref", base_ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "test")

    migrations_dir = repo / "modx" / "infrastructure" / "migrations" / "versions"
    migrations_dir.mkdir(parents=True)
    (migrations_dir / "0001_init.py").write_text('revision = "0001"\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def test_I10_clean_new_migration_passes(scratch_repo: Path) -> None:
    """# enforces AIR-14 negatively: a well-formed *new* migration is not itself a problem."""
    migrations_dir = scratch_repo / "modx" / "infrastructure" / "migrations" / "versions"
    (migrations_dir / "0002_add_table.py").write_text(
        'revision = "0002"\n\ndef upgrade():\n    op.create_table("thing")\n'
    )
    _git(scratch_repo, "add", "-A")
    _git(scratch_repo, "commit", "-q", "-m", "add table")

    result = _run_checker(scratch_repo, "HEAD~1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "QG-09 OK" in result.stdout


def test_I10_editing_an_applied_migration_is_rejected(scratch_repo: Path) -> None:
    """# enforces AIR-14: "an applied migration is never edited; corrections are new migrations"."""
    migrations_dir = scratch_repo / "modx" / "infrastructure" / "migrations" / "versions"
    (migrations_dir / "0001_init.py").write_text('revision = "0001"  # edited\n')
    _git(scratch_repo, "add", "-A")
    _git(scratch_repo, "commit", "-q", "-m", "edit applied migration")

    result = _run_checker(scratch_repo, "HEAD~1")
    assert result.returncode == 1
    assert "modified an existing migration file" in result.stdout


def test_I11_unmarked_destructive_operation_is_rejected(scratch_repo: Path) -> None:
    migrations_dir = scratch_repo / "modx" / "infrastructure" / "migrations" / "versions"
    (migrations_dir / "0002_bad.py").write_text(
        'revision = "0002"\n\ndef upgrade():\n    op.drop_table("legacy_thing")\n'
    )
    _git(scratch_repo, "add", "-A")
    _git(scratch_repo, "commit", "-q", "-m", "add bad migration")

    result = _run_checker(scratch_repo, "HEAD~1")
    assert result.returncode == 1
    assert "destructive operation without an" in result.stdout


def test_I11_marked_destructive_operation_is_accepted(scratch_repo: Path) -> None:
    migrations_dir = scratch_repo / "modx" / "infrastructure" / "migrations" / "versions"
    (migrations_dir / "0002_good.py").write_text(
        'revision = "0002"\n\n'
        "def upgrade():\n"
        '    op.drop_table("legacy_thing")  # approved-destructive: replaced by new_thing, no readers remain\n'
    )
    _git(scratch_repo, "add", "-A")
    _git(scratch_repo, "commit", "-q", "-m", "add approved destructive migration")

    result = _run_checker(scratch_repo, "HEAD~1")
    assert result.returncode == 0, result.stdout + result.stderr
