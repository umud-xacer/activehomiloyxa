"""Migrations apply cleanly to a fresh database (checklist), and the Alembic version table
lives inside the owning module's own schema (Physical DB Sec 1.1). Builds a throwaway
migrations environment per test (mirroring what scripts/new-module-migrations.sh scaffolds for
a real module) against a scratch schema -- never a real module's migration history.

Deliberately synchronous tests: `alembic.command.upgrade()` calls `env.py`'s `run_migrations()`,
which internally does its own `asyncio.run(...)` (the standard Alembic async recipe, Sec
`backbone.migrations.env_support`) -- that cannot nest inside an already-running event loop, so
these tests (and the schema setup/teardown around them) stay plain sync functions using
`asyncio.run()` themselves, never `async def test_...`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from backbone.persistence import make_engine

REPO_ROOT = Path(__file__).resolve().parents[5]
TEMPLATES = REPO_ROOT / "apps" / "backend" / "src" / "backbone" / "migrations" / "templates"


@pytest.fixture
def scratch_migrations_env(tmp_path: Path) -> tuple[str, Path]:
    module_name = f"scratchmig{uuid.uuid4().hex[:8]}"
    env_dir = tmp_path / "migrations"
    versions_dir = env_dir / "versions"
    versions_dir.mkdir(parents=True)

    (env_dir / "env.py").write_text(
        "from backbone.migrations.env_support import run_migrations\n"
        "from sqlalchemy import MetaData\n\n"
        f'target_metadata = MetaData(schema="{module_name}")\n'
        f'run_migrations(module_name="{module_name}", target_metadata=target_metadata)\n'
    )
    (env_dir / "alembic.ini").write_text(
        (TEMPLATES / "alembic.ini.template")
        .read_text(encoding="utf-8")
        .replace("{module}", module_name)
    )
    (versions_dir / "0001_smoke_test.py").write_text(
        '"""smoke test\n\nRevision ID: 0001\nRevises:\nCreate Date: 2026-01-01\n"""\n'
        "from __future__ import annotations\n"
        "import sqlalchemy as sa\n"
        "from alembic import op\n\n"
        'revision = "0001"\n'
        "down_revision = None\n"
        f'branch_labels = ("{module_name}",)\n'
        "depends_on = None\n\n"
        "def upgrade() -> None:\n"
        "    op.create_table(\n"
        '        "smoke_row",\n'
        '        sa.Column("id", sa.Integer, primary_key=True),\n'
        '        sa.Column("note", sa.Text, nullable=False),\n'
        f'        schema="{module_name}",\n'
        "    )\n\n"
        "def downgrade() -> None:\n"
        f'    op.drop_table("smoke_row", schema="{module_name}")\n'
    )
    return module_name, env_dir


async def _create_schema(module_name: str) -> None:
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{module_name}"'))
    await engine.dispose()


async def _drop_schema(module_name: str) -> None:
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{module_name}" CASCADE'))
    await engine.dispose()


async def _tables_in_schema(module_name: str) -> set[str]:
    engine = make_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"),
            {"schema": module_name},
        )
        tables = {row[0] for row in result}
    await engine.dispose()
    return tables


async def _alembic_version(module_name: str) -> str | None:
    engine = make_engine()
    async with engine.begin() as conn:
        version = await conn.scalar(
            text(f'SELECT version_num FROM "{module_name}".alembic_version')
        )
    await engine.dispose()
    return cast("str | None", version)


@pytest.fixture
def scratch_module_schema(scratch_migrations_env: tuple[str, Path]) -> Iterator[str]:
    module_name, _ = scratch_migrations_env
    asyncio.run(_create_schema(module_name))
    try:
        yield module_name
    finally:
        asyncio.run(_drop_schema(module_name))


def test_I16_migration_applies_cleanly_to_a_fresh_database(
    scratch_migrations_env: tuple[str, Path], scratch_module_schema: str
) -> None:
    module_name, env_dir = scratch_migrations_env

    cfg = Config(str(env_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(env_dir))
    command.upgrade(cfg, "head")

    tables = asyncio.run(_tables_in_schema(module_name))
    assert "smoke_row" in tables


def test_I17_alembic_version_table_lives_inside_the_module_schema(
    scratch_migrations_env: tuple[str, Path], scratch_module_schema: str
) -> None:
    """# enforces Physical DB Sec 1.1: "Alembic version tables live per module branch inside
    the owning schema"."""
    module_name, env_dir = scratch_migrations_env

    cfg = Config(str(env_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(env_dir))
    command.upgrade(cfg, "head")

    tables = asyncio.run(_tables_in_schema(module_name))
    version = asyncio.run(_alembic_version(module_name))

    assert "alembic_version" in tables
    assert version == "0001"
