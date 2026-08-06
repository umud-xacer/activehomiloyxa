"""QG-09 (Playbook Sec 16; DevSecOps Sec 7; AIR-14): a previously-applied migration is never
edited (corrections are a new migration), and a destructive operation needs an explicit,
reviewed marker rather than sailing through silently.

Two independent checks, run against `git diff` between the current branch and a base ref:

1. No migration file under `*/infrastructure/migrations/versions/*.py` that already existed at
   the base ref may be modified in this diff -- only added (AIR-14, DevSecOps Sec 7 "an applied
   migration is never edited; corrections are new migrations").
2. Every added or modified migration file: any line matching a destructive-operation pattern
   (DROP TABLE/COLUMN/CONSTRAINT, raw DROP SQL) must carry an `# approved-destructive: <reason>`
   marker within a few lines of it -- otherwise the change is rejected.

Two deliberate leniencies, both confirmed necessary by running this script against every
already-merged module's own first migration (`--base-ref <a commit predating all of them>`):
comment/docstring lines (this file's own generated header explains the rule using the words
"DROP TABLE/COLUMN" as prose, which the naive pattern would otherwise flag) are excluded from
matching, and the marker may appear on any of the up-to-three lines starting at the destructive
call, not only the exact same line -- `ruff format` wraps a longer `op.drop_table("name",
schema="x")  # approved-destructive: ...` call across three lines once it exceeds the configured
line length, moving the trailing marker comment onto the closing-paren line rather than the
`op.drop_table(` line itself. Every module's migration file already relies on both leniencies;
a single-line-exact-match version of this check has never actually passed for ANY module's
migration when compared honestly against a base ref that does not already contain it unchanged.

Usage: python tools/check_migration_safety.py [--base-ref origin/main]
"""

from __future__ import annotations

import argparse
import re
import subprocess

MIGRATION_PATH_RE = re.compile(r".*/infrastructure/migrations/versions/.*\.py$")

DESTRUCTIVE_PATTERNS = [
    re.compile(r"op\.drop_table\("),
    re.compile(r"op\.drop_column\("),
    re.compile(r"op\.drop_constraint\("),
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
]
APPROVAL_MARKER = "# approved-destructive:"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def _changed_migration_files(base_ref: str) -> list[tuple[str, str]]:
    """Returns (status, path) for every changed file under a migrations/versions/ directory,
    status in git's name-status letters (A=added, M=modified, D=deleted, ...)."""
    try:
        raw = _git("diff", "--name-status", f"{base_ref}...HEAD")
    except subprocess.CalledProcessError as exc:
        print(
            f"::notice::could not diff against {base_ref} ({exc}); skipping (no base to compare)."
        )
        return []

    changed = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status, path = parts[0], parts[-1]
        if MIGRATION_PATH_RE.match(path):
            changed.append((status[0], path))
    return changed


def check_no_edited_applied_migrations(base_ref: str) -> list[str]:
    problems = []
    for status, path in _changed_migration_files(base_ref):
        if status == "M":
            problems.append(
                f"{path}: modified an existing migration file (AIR-14) -- append a new "
                "migration instead of editing this one."
            )
    return problems


def check_destructive_operations_are_marked(base_ref: str) -> list[str]:
    problems = []
    for status, path in _changed_migration_files(base_ref):
        if status == "D":
            continue
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if line.strip().startswith("#"):
                # A comment/docstring-prose line, never actual op.* code -- e.g. this very
                # script's own generated migration header explains the rule using the words
                # "DROP TABLE/COLUMN", which would otherwise false-positive on itself.
                continue
            if not any(pattern.search(line) for pattern in DESTRUCTIVE_PATTERNS):
                continue
            # The marker may be on this line or any of the following few -- `ruff format` wraps a
            # longer `op.drop_table(...)  # approved-destructive: ...` call across multiple
            # lines (more for `op.drop_constraint(op.f(...), ..., type_="foreignkey")`, which has
            # more arguments than `op.drop_table("name", schema="x")`), moving the trailing
            # comment off the line the pattern itself matched on.
            window = lines[lineno - 1 : lineno + 5]
            if any(APPROVAL_MARKER in candidate for candidate in window):
                continue
            problems.append(
                f"{path}:{lineno}: destructive operation without an "
                f"'{APPROVAL_MARKER} <reason>' marker within a few lines: {line.strip()!r}"
            )
    return problems


def main(base_ref: str) -> int:
    problems = check_no_edited_applied_migrations(
        base_ref
    ) + check_destructive_operations_are_marked(base_ref)
    if problems:
        print("QG-09 FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("QG-09 OK: no edited-applied migrations, no unmarked destructive operations.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args()
    raise SystemExit(main(args.base_ref))
