#!/usr/bin/env bash
# Runs ON the production host (single EC2 box, DEC-16) after CI has rsynced the latest tree
# into ~/app. Not run locally -- see .github/workflows/deploy.yml, which is the only caller.
# Idempotent: safe to re-run (matches scripts/README.md's convention for everything else here).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# systemd's own EnvironmentFile= (see deployment/systemd/*.service) only applies to the units
# it starts -- this script runs over plain SSH, so POSTGRES_*/REDIS_*/etc. need loading here too,
# same pattern as scripts/dev-install.sh sourcing .env.local for local dev.
set -a
# shellcheck disable=SC1091
source deployment/env/.env.production
set +a

echo "==> backend deps"
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements-dev.txt -e packages/shared -e contracts -e apps/backend

echo "==> db migrations"
PYTHONPATH="apps/backend/src:packages/shared/src:." .venv/bin/python3 -c "
import pathlib, sys
from alembic import command
from alembic.config import Config
SRC = pathlib.Path('apps/backend/src')
mods = sorted(p for p in SRC.glob('*/infrastructure/migrations/alembic.ini'))
failed = []
for ini in mods:
    module = ini.parts[-4]
    try:
        cfg = Config(str(ini))
        cfg.set_main_option('script_location', str(ini.parent))
        command.upgrade(cfg, 'head')
        print(f'OK   {module}')
    except Exception as exc:
        print(f'FAIL {module}: {type(exc).__name__}: {exc}')
        failed.append(module)
print(f'{len(mods) - len(failed)}/{len(mods)} module schemas migrated')
if failed:
    print('FAILED:', ', '.join(failed))
    sys.exit(1)
"

echo "==> seed data (idempotent -- skips anything already seeded)"
PYTHONPATH="apps/backend/src:packages/shared/src:." .venv/bin/python3 -m configuration.infrastructure.seed

echo "==> frontend build"
cd apps/frontend
export NODE_OPTIONS="--max-old-space-size=1536"
# @lovable.dev/vite-tanstack-config's nitro/vite setup defaults to a Cloudflare Workers build
# target (own comment in vite.config.ts) -- this deployment runs the built server as a plain
# systemd/Node process (deployment/systemd/activehome-web.service's `node index.mjs`), so it
# needs Nitro's node-server preset instead, or the output is a Workers fetch-handler module that
# exits immediately when run with plain `node`.
export NITRO_PRESET=node-server
npm ci --legacy-peer-deps
npm run build
cd ../..

echo "==> restart services"
sudo systemctl restart activehome-api
sudo systemctl restart activehome-search-worker
sudo systemctl restart activehome-media-worker
sudo systemctl restart activehome-notifications-worker
sudo systemctl restart activehome-web

sleep 3
sudo systemctl is-active activehome-api activehome-web activehome-search-worker activehome-media-worker activehome-notifications-worker
curl -sf http://127.0.0.1/healthz && echo " -- healthz OK"
echo "==> deploy complete: $(date -u +%FT%TZ) $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
