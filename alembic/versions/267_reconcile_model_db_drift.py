"""Reconcile model<->DB drift (idempotent, additive).

Schliesst die historische *Model-ahead-of-Migrations*-Drift: Modell-Spalten und
-Tabellen, die nie einzeln migriert wurden (z.B. ``users.totp_failed_attempts``,
zahlreiche ``company_id``-Spalten, diverse DATEV-/GDPR-/Webhook-Tabellen), werden
idempotent ergaenzt - sowohl fuer den from-scratch-Pfad als auch fuer reale
Bestands-DBs, deren ``alembic_version`` weiter war als ihr tatsaechliches Schema.

Rein additiv: ``create_all(checkfirst=True)`` legt nur fehlende Tabellen an,
``ADD COLUMN IF NOT EXISTS`` nur fehlende Spalten. Es werden NIE Tabellen oder
Spalten entfernt. Neue Spalten werden nullable angelegt (NOT NULL auf
Bestandsdaten wuerde scheitern); die Modell-Nullability bleibt die Quelle der
Wahrheit fuer Neuanlagen.

Revision ID: 267
Revises: 266
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "267"
down_revision = "266"
branch_labels = None
depends_on = None


def _add_missing_columns(bind) -> None:
    """Idempotently add every model column missing from an existing table."""
    import app.db.all_models  # noqa: F401  registers the full ORM model graph
    from app.db.models_base import Base

    dialect = postgresql.dialect()
    rows = bind.execute(
        sa.text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
    ).fetchall()
    db_cols: dict = {}
    for table_name, column_name in rows:
        db_cols.setdefault(table_name, set()).add(column_name)

    for table in Base.metadata.sorted_tables:
        existing = db_cols.get(table.name)
        if existing is None:
            continue  # whole table was just created by create_all()
        for col in table.columns:
            if col.name in existing:
                continue
            type_sql = col.type.compile(dialect=dialect)
            default_sql = ""
            server_default = getattr(col, "server_default", None)
            if server_default is not None and getattr(server_default, "arg", None) is not None:
                try:
                    default_sql = " DEFAULT " + str(
                        server_default.arg.compile(
                            dialect=dialect, compile_kwargs={"literal_binds": True}
                        )
                    )
                except Exception:
                    default_sql = ""
            op.execute(
                f'ALTER TABLE "{table.name}" '
                f'ADD COLUMN IF NOT EXISTS "{col.name}" {type_sql}{default_sql}'
            )


def upgrade() -> None:
    import app.db.all_models  # noqa: F401
    from app.db.models_base import Base

    bind = op.get_bind()
    # 1) Create any missing model tables (existing tables are left untouched).
    Base.metadata.create_all(bind=bind, checkfirst=True)
    # 2) Add any model columns missing from pre-existing tables.
    _add_missing_columns(bind)


def downgrade() -> None:
    # Additive reconcile -> intentionally non-reversible.
    pass
