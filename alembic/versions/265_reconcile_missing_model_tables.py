"""Reconcile: nie-migrierte Modell-Tabellen idempotent nachziehen.

Mehrere Modell-Tabellen wurden NIE per Migration angelegt - weder from-scratch
noch in der realen DB (z.B. budgets/budget_*, batch_jobs, gdpr_breach_logs,
gdpr_consent_logs, kostenstellen, document_tasks, notification_preferences,
password_reset_tokens, privat_contracts, ...). `alembic upgrade head` lief zwar
durch, erzeugte aber ein gegenueber den ORM-Modellen unvollstaendiges Schema.

Diese Migration schliesst die Luecke modell-treu und idempotent:
``Base.metadata.create_all(checkfirst=True)`` legt NUR Tabellen an, die noch nicht
existieren (inkl. deren Indizes/Enums), und laesst bestehende voellig unangetastet.
Damit produziert `alembic upgrade head` das vollstaendige Modell-Schema - und beim
naechsten Migrationslauf der realen DB werden die dort fehlenden Tabellen ebenso
nachgezogen, ohne Bestand anzufassen.

Revision ID: 265
Revises: 264
Create Date: 2026-06-07
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "265"
down_revision = "264"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alle Mapped-Klassen registrieren (kein app.main noetig), dann fehlende
    # Tabellen modell-treu anlegen. checkfirst=True -> nur Fehlendes wird erzeugt.
    import app.db.all_models  # noqa: F401  - registriert das gesamte Modell-Set
    from sqlalchemy.orm import configure_mappers

    configure_mappers()
    from app.db.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # Bewusst No-op: create_all laesst sich nicht sicher rueckabwickeln, ohne
    # legitime (auch anderweitig angelegte) Tabellen zu gefaehrden.
    pass
