#!/usr/bin/env bash
# Idempotent: runs every module's Alembic branch to head (repo has one alembic.ini per DDD
# module under apps/backend/src/<module>/infrastructure/migrations/, no single shared env).
# Mirrors docs/assessments/2026-07-27-verification/evidence/harness/migrate_all.py (that copy
# lives outside the repo per P-VERIFY Rule 1; this is the same logic as a real product script
# for db-migrate.sh, which scripts/README.md flagged as not yet existing).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

python3 - "apps/backend/src" <<'PY'
import pathlib
import sys

from alembic import command
from alembic.config import Config

SRC = pathlib.Path(sys.argv[1])
mods = sorted(p for p in SRC.glob("*/infrastructure/migrations/alembic.ini"))
failed = []
for ini in mods:
    module = ini.parts[-4]
    try:
        cfg = Config(str(ini))
        cfg.set_main_option("script_location", str(ini.parent))
        command.upgrade(cfg, "head")
        print(f"OK   {module}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {module}: {type(exc).__name__}: {exc}")
        failed.append(module)
print(f"\n{len(mods) - len(failed)}/{len(mods)} module schemas migrated")
if failed:
    print("FAILED:", ", ".join(failed))
    sys.exit(1)
PY
