#!/usr/bin/env bash
# Idempotent (safe to re-run; refuses to overwrite an existing env.py/alembic.ini). Scaffolds
# apps/backend/src/<module>/infrastructure/migrations/ from backbone's shared templates
# (Physical DB Sec 13 "Migration organization"). Run once per module, the first time that
# module's task needs a migration.
#
# Usage: scripts/new-module-migrations.sh <module>
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

module="${1:?usage: scripts/new-module-migrations.sh <module>}"

target="apps/backend/src/${module}/infrastructure/migrations"
templates="apps/backend/src/backbone/migrations/templates"

if [ ! -d "apps/backend/src/${module}" ]; then
  echo "no such module: apps/backend/src/${module} does not exist" >&2
  exit 1
fi

if [ -f "${target}/env.py" ]; then
  echo "${target}/env.py already exists -- not overwriting." >&2
  exit 1
fi

mkdir -p "${target}/versions"

sed "s/{module}/${module}/g" "${templates}/alembic.ini.template" > "${target}/alembic.ini"
cp "${templates}/script.py.mako" "${target}/script.py.mako"

cat > "${target}/env.py" <<PYEOF
"""Alembic environment for the ${module} module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from ${module}.infrastructure.models import Base

run_migrations(module_name="${module}", target_metadata=Base.metadata)
PYEOF

touch "${target}/versions/.gitkeep"

echo "scaffolded ${target}/"
echo "next: define ${module}.infrastructure.models.Base (backbone.persistence.make_module_base(\"${module}\")), then:"
echo "  cd ${target} && alembic revision --branch-label ${module} -m \"${module}: <verb> <object>\""
