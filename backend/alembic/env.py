"""
Alembic async migration environment for the Road Intelligence Platform.

Uses asyncio + asyncpg so that SQLAlchemy async models are compatible with
Alembic's migration runner.  This file is loaded by the ``alembic`` CLI.

References
----------
- https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import the application's declarative Base so Alembic can autogenerate diffs
# ---------------------------------------------------------------------------
# We import Base from the backend package.  When running ``alembic`` from
# inside the ``backend/`` directory (or with PYTHONPATH set) these imports
# resolve correctly.
try:
    from database import Base          # noqa: F401 — registers metadata
    import models                      # noqa: F401 — registers all ORM models
    target_metadata = Base.metadata
except ImportError:
    # Fallback: allow alembic --autogenerate to run without full app installed
    # (offline mode).  Metadata will be empty; migrations won't auto-detect models.
    target_metadata = None

# ---------------------------------------------------------------------------
# Override sqlalchemy.url from DATABASE_URL environment variable if set.
# The env var uses asyncpg; Alembic's offline mode replaces it with psycopg2
# for synchronous SQL emission.
# ---------------------------------------------------------------------------
_env_db_url = os.getenv("DATABASE_URL")
if _env_db_url:
    # Alembic offline mode needs a sync driver — swap asyncpg → psycopg2
    _sync_url = _env_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    config.set_main_option("sqlalchemy.url", _sync_url)


# ---------------------------------------------------------------------------
# Helper: derive async URL from whatever is currently in config
# ---------------------------------------------------------------------------
def _async_url() -> str:
    url = config.get_main_option("sqlalchemy.url", "")
    # If a sync URL was stored, convert back to asyncpg for the async engine
    return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)


# ---------------------------------------------------------------------------
# OFFLINE mode — emit SQL to stdout / file without a live DB connection
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.  Calls to
    context.execute() emit the SQL to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# ONLINE mode — run migrations against a live database using asyncio
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Include PostGIS schemas when autogenerating
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    # Build config section for the engine using the asyncpg URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _async_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
