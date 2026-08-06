#!/usr/bin/env bash
# QG-05. Idempotent: read-only check, no side effects.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHONPATH="apps/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
  lint-imports --config tools/importlinter.cfg
