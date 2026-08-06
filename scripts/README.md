# scripts/

Idempotent dev/build/quality-gate helpers (Playbook Sec 2) -- safe to re-run. All assume the
repo root as the working directory and are runnable directly (`./scripts/<name>.sh`) once
`chmod +x` (already set) or via `bash scripts/<name>.sh`.

| Script | Does |
|---|---|
| `dev-install.sh` | Create/refresh `.venv`; install `requirements-dev.txt` + both Python packages editable |
| `dev-up.sh` / `dev-down.sh` | Start/stop the Phase-1 datastore topology (`deployment/compose/docker-compose.yml`) |
| `lint.sh` | QG-01 -- `ruff format --check` + `ruff check` |
| `typecheck.sh` | QG-02 -- `mypy --strict` |
| `test.sh` | QG-03 -- `pytest` |
| `coverage.sh` | QG-04 / COV-01 -- coverage run + both the 80% overall and 90% domain/application floors |
| `check-import-boundaries.sh` | QG-05 -- `import-linter` against `tools/importlinter.cfg` |
| `security-scan.sh` | QG-07 -- bandit (SAST) + pip-audit (SCA) + gitleaks (secret scan, if installed) |
| `bootstrap-admin.sh <email>` | UNF-012 -- grants an already-registered account `super-admin` (no API path can do this for the first administrator); idempotent |

Migration and seed helpers (`db-migrate.sh`, `db-seed.sh`) are not here yet -- there is no
Alembic environment or schema until the first module's persistence layer lands; adding them now
would be a stub with nothing to run (excluded from Task P-00's scope).
