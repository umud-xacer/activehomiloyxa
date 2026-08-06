#!/usr/bin/env bash
# Full, reproducible bring-up of the verification stack from an empty database.
set -euo pipefail
T=/home/ameer/.claude/jobs/06393b27/tmp
source "$T/env.verify.sh"
PY=/home/ameer/extra/work/umidjon/active-home-platform/active-home-platform/.venv/bin/python
export PGPASSWORD="$POSTGRES_PASSWORD"

echo "== drop/recreate database =="
psql -h localhost -U active_home -d postgres -qc "DROP DATABASE IF EXISTS active_home_verify WITH (FORCE);" \
                                              -c "CREATE DATABASE active_home_verify OWNER active_home;"

echo "== create per-module schemas (DEF-001 workaround) =="
for s in admin ads analytics billing catalog configuration identity media messaging moderation notifications profiles search; do
  psql -h localhost -U active_home -d active_home_verify -qc "CREATE SCHEMA IF NOT EXISTS \"$s\";"
done

echo "== alembic upgrade head (13 modules) =="
"$PY" "$T/migrate_all.py" "$REPO/apps/backend/src" | tail -2

echo "== configuration seed =="
"$PY" -m configuration.infrastructure.seed

echo "== reset OpenSearch index =="
curl -s -X DELETE "http://localhost:9201/listing_search" >/dev/null || true

echo "== restart API =="
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1
nohup "$PY" -m uvicorn main:app --app-dir "$REPO/apps/backend/src" \
  --host 127.0.0.1 --port 8100 > "$T/api.log" 2>&1 &
for i in $(seq 1 40); do
  sleep 0.5
  if curl -sf http://127.0.0.1:8100/health >/dev/null; then break; fi
done
echo "  /health  -> $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8100/health)"
echo "  /ready   -> $(curl -s http://127.0.0.1:8100/ready)"

echo "== bootstrap operators =="
"$PY" "$T/bootstrap_admin.py" | tail -3

echo "== author configuration =="
"$PY" "$T/seed_config.py" 2>&1 | tail -30
