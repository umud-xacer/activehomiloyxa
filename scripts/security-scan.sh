#!/usr/bin/env bash
# QG-07. Idempotent: read-only checks, no side effects. Requires gitleaks on PATH separately
# (not a pip package); bandit and pip-audit come from requirements-dev.txt.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "-- SAST (bandit) --"
bandit -c tools/security/bandit.yaml -r apps/backend/src packages/shared/src contracts

echo "-- SCA (pip-audit) --"
pip-audit -r requirements-dev.txt
# active-home-shared / active-home-contracts are local path packages, not on PyPI -- exclude
# them from the SCA scan (a lookup would either 404 or, worse, match an unrelated package).
pip-audit -r <(python3 -c "
import tomllib
d = tomllib.load(open('apps/backend/pyproject.toml', 'rb'))
for dep in d['project']['dependencies']:
    if not dep.startswith('active-home-'):
        print(dep)
")

if command -v gitleaks >/dev/null 2>&1; then
  echo "-- secret scan (gitleaks) --"
  gitleaks detect --config tools/security/gitleaks.toml --source . --no-banner
else
  echo "gitleaks not installed locally -- this runs in CI (QG-07); skipping here." >&2
fi
