#!/usr/bin/env bash
# QG-03. Idempotent: read-only check, no side effects. Integration/API suites additionally
# require the datastores from scripts/dev-up.sh to be running.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHONPATH="apps/backend/src:packages/shared/src:.${PYTHONPATH:+:$PYTHONPATH}" \
  pytest -c tools/pytest.ini --rootdir=. "$@"
