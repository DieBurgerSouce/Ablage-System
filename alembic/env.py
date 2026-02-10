"""
Alembic Environment Configuration.

Supports both online (live database) and offline (SQL script) migrations.
Created: 2024-11-25
"""
import asyncio
import os
import re
import sys
from logging.config import fileConfig

# Load .env file for local development
from dotenv import load_dotenv
load_dotenv()

from alembic import context
from sqlalchemy import pool, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Only load heavy models for autogenerate (saves ~2-3GB RAM for upgrade/downgrade)
_needs_metadata = any(cmd in sys.argv for cmd in ("--autogenerate", "revision"))

if _needs_metadata:
    try:
        from app.db.models import Base
        # Import GoBD compliance models so Alembic detects them
        from app.db.bpmn_models.gobd import (
            AuditChainEntry,
            RetentionPolicy,
            ArchiveIntegrityCheck,
            TimestampAuthorityConfig,
            RetentionDeletionRequest,
        )
        # Import OCR Self-Learning models
        from app.db.models_ocr_feedback import (
            OCRCorrectionFeedback,
            OCRBackendPerformance,
        )
        # Import PO-Matching models
        from app.db.models_po_matching import (
            PurchaseOrderMatch,
            MatchDiscrepancy,
        )
        # Import Recurring Invoice models
        from app.db.models_recurring_invoice import (
            RecurringInvoice,
            RecurringInvoiceOccurrence,
        )
        target_metadata = Base.metadata
    except ImportError as e:
        import logging
        logging.warning(f"Could not import models: {e}. Autogenerate will not work.")
        target_metadata = None
else:
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


# --- asyncpg multi-statement workaround ---
# asyncpg cannot execute multiple SQL statements in a single execute() call.
# Many migrations use op.execute("stmt1; stmt2; ...") which breaks with asyncpg.
# This hook splits multi-statement strings into individual statements.

def _split_sql_statements(sql_text: str) -> list:
    """Split SQL text into individual statements, respecting $$ blocks and functions."""
    # If no semicolons at all, return as-is
    if ";" not in sql_text:
        return [sql_text.strip()]

    # If it contains $$ (PL/pgSQL function bodies), don't split - it's a single statement
    if "$$" in sql_text:
        # Check if there are multiple top-level statements (semicolons outside $$)
        # by removing $$ blocks first
        cleaned = re.sub(r'\$\$.*?\$\$', '', sql_text, flags=re.DOTALL)
        semicolons = [m.start() for m in re.finditer(r';', cleaned)]
        # If only one semicolon (the statement terminator), return as-is
        if len(semicolons) <= 1:
            return [sql_text.strip()]

    # Split on semicolons, but filter empty ones
    parts = sql_text.split(";")
    statements = []
    for part in parts:
        stripped = part.strip()
        if stripped and not stripped.startswith("--"):
            statements.append(stripped)
    return statements


@event.listens_for(Connection, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context_obj, executemany):
    """Intercept multi-statement SQL and split for asyncpg compatibility."""
    pass  # We handle this at a higher level


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
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
    # Monkey-patch the connection's execute to handle multi-statement SQL
    original_execute = connection.execute

    def patched_execute(stmt, *args, **kwargs):
        # Only intercept string/text statements that contain multiple statements
        if hasattr(stmt, 'text'):
            sql_str = stmt.text
        elif isinstance(stmt, str):
            sql_str = stmt
        else:
            return original_execute(stmt, *args, **kwargs)

        statements = _split_sql_statements(sql_str)
        if len(statements) <= 1:
            return original_execute(stmt, *args, **kwargs)

        # Execute each statement individually
        result = None
        for single_stmt in statements:
            result = original_execute(text(single_stmt), *args, **kwargs)
        return result

    connection.execute = patched_execute

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
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
