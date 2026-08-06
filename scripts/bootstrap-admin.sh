#!/usr/bin/env bash
# QG-N/A (ops helper, not a quality gate). Grants an already-registered account the
# super-admin role -- UNF-012: no API path can do this for the FIRST administrator
# (assignRole itself requires identity:role:assign, which nobody holds on a fresh install).
# Register the account first (POST /auth/register/email), then run this. Idempotent.
#
# Usage: scripts/bootstrap-admin.sh <email>
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ $# -ne 1 ]; then
  echo "usage: scripts/bootstrap-admin.sh <email>" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="apps/backend/src:packages/shared/src:."
(cd apps/backend/src && python -m bootstrap_admin "$1")
