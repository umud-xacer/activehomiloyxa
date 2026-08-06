#!/usr/bin/env bash
# QG-02. Idempotent: read-only check, no side effects.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

mypy --config-file tools/mypy.ini apps/backend/src apps/backend/tests packages/shared/src packages/shared/tests contracts
