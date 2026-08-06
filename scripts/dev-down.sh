#!/usr/bin/env bash
# Idempotent: stops the datastore topology. Pass --volumes to also wipe local data volumes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker compose -f deployment/compose/docker-compose.yml down "$@"
