#!/usr/bin/env bash
# Idempotent: creates .venv if missing, (re)installs pinned dev tooling + all three Python
# packages editable. Safe to re-run any time.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements-dev.txt
pip install -e packages/shared
pip install -e contracts
pip install -e apps/backend

echo "dev environment ready: source .venv/bin/activate"
