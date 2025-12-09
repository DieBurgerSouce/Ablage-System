"""
Alembic Environment Configuration.

Supports both online (live database) and offline (SQL script) migrations.
Created: 2024-11-25
"""
import asyncio
import os
from logging.config import fileConfig

# Load .env file for local development
from dotenv import load_dotenv
load_dotenv()

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models here for autogenerate to work
try:
    from app.db.models import Base
    target_metadata = Base.metadata
except ImportError as e:
    # Fallback to None if models not yet available
    # This allows alembic commands to run even without full app setup
    import logging
    logging.warning(f"Could not import models: {e}. Autogenerate will not work.")
    target_metadata = None

# Database URL MUSS aus Umgebungsvariable kommen (Sicherheit!)
# Unterstützt: ABLAGE_DATABASE_URL oder DATABASE_URL
database_url = os.getenv("ABLAGE_DATABASE_URL") or os.getenv("DATABASE_URL")
if not database_url:
    raise ValueError(
        "Datenbank-URL nicht gesetzt! "
        "Bitte ABLAGE_DATABASE_URL oder DATABASE_URL als Umgebungsvariable setzen. "
        "Beispiel: export DATABASE_URL='postgresql+asyncpg://user:pass@localhost:5433/ablage_system'"
    )
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
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


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with database connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with async engine.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
