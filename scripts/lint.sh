#!/usr/bin/env bash
# QG-01. Idempotent: read-only checks, no side effects.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

ruff format --check --config tools/ruff.toml apps/backend/src apps/backend/tests packages/shared/src packages/shared/tests contracts tools
ruff check --config tools/ruff.toml apps/backend/src apps/backend/tests packages/shared/src packages/shared/tests contracts tools
