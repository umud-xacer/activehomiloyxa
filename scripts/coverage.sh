#!/usr/bin/env bash
# QG-04 / COV-01. Idempotent: overwrites .coverage and coverage.json in place, both gitignored.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# STATUS (Task P-01): shared_kernel/, contracts/, and the interface stubs are now real,
# coverable source -- this guard only still matters for a checkout that predates them (or if
# they were ever removed). TODO: remove entirely once every module also has domain/application
# content (the 90% domain/application floor below only bites once those exist).
# `-print -quit` (not `| grep -q .`): under `set -o pipefail`, grep -q closing the pipe after
# its first match SIGPIPEs `find`, so the pipeline's exit status was `find`'s (non-zero, from
# the signal) rather than grep's own success -- silently tripping this guard and skipping
# coverage entirely even with real coverable source present. `-print -quit` lets `find` itself
# stop after one match, so there is no pipe to SIGPIPE.
if [ -z "$(find apps/backend/src packages/shared/src contracts -name '*.py' ! -name '__init__.py' -print -quit)" ]; then
  echo "QG-04: no coverable source beyond __init__.py yet -- nothing to measure."
  exit 0
fi

export PYTHONPATH="apps/backend/src:packages/shared/src:.${PYTHONPATH:+:$PYTHONPATH}"
coverage run --rcfile=tools/coverage.ini -m pytest -c tools/pytest.ini --rootdir=.
coverage report --rcfile=tools/coverage.ini
coverage json --rcfile=tools/coverage.ini -o coverage.json
python3 tools/check_domain_coverage.py coverage.json
