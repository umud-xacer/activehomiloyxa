#!/usr/bin/env bash
# Idempotent: brings up the Phase-1 datastore topology (Infra Sec 6). Safe to re-run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker compose -f deployment/compose/docker-compose.yml up -d
docker compose -f deployment/compose/docker-compose.yml ps
