"""Verification-side migration runner: upgrade every module's Alembic branch to head.

Lives outside the repo on purpose (P-VERIFY Rule 1: no product-code writes). The repo ships no
db-migrate.sh (scripts/README.md says so explicitly), so bring-up needs this.
"""

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
