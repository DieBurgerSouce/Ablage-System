# -*- coding: utf-8 -*-
"""GoBD-Compliance Erweiterungen für Kasse-Modul.

- DB-Trigger für APPEND-ONLY (verhindert UPDATE/DELETE auf cash_entries)
- Audit Trail Felder für Stornierungen (cancelled_by_user_id, cancelled_at)
- Performance-Indizes (is_cancelled, fiscal_year, category_id)

Revision ID: 059_add_gobd_compliance
Revises: 058_add_cash_module
Create Date: 2024-12-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # 1. AUDIT TRAIL FELDER
    # ==========================================================================

    # Wer hat storniert?
    op.add_column(
        'cash_entries',
        sa.Column(
            'cancelled_by_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='User der die Stornierung durchgeführt hat'
        )
    )

    # Wann wurde storniert?
    op.add_column(
        'cash_entries',
        sa.Column(
            'cancelled_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Zeitpunkt der Stornierung (GoBD Audit Trail)'
        )
    )

    # ==========================================================================
    # 2. PERFORMANCE INDIZES
    # ==========================================================================

    # Index für Filter auf stornierte/aktive Einträge
    op.create_index(
        'ix_cash_entries_is_cancelled',
        'cash_entries',
        ['is_cancelled'],
        postgresql_where=sa.text('is_cancelled = false')  # Partial Index
    )

    # Index für Geschäftsjahr-Filterung (GoBD: Jahresabschluss)
    op.create_index(
        'ix_cash_entries_fiscal_year',
        'cash_entries',
        ['fiscal_year']
    )

    # Index für Kategorie-Aggregationen
    op.create_index(
        'ix_cash_entries_category_id',
        'cash_entries',
        ['category_id'],
        postgresql_where=sa.text('category_id IS NOT NULL')  # Partial Index
    )

    # Composite Index für häufige Abfragen
    op.create_index(
        'ix_cash_entries_register_year_active',
        'cash_entries',
        ['cash_register_id', 'fiscal_year', 'is_cancelled']
    )

    # ==========================================================================
    # 3. GoBD TRIGGER: APPEND-ONLY SCHUTZ
    # ==========================================================================

    # Trigger-Funktion: Verhindert unerlaubte UPDATEs
    op.execute("""
        CREATE OR REPLACE FUNCTION gobd_prevent_cash_entry_update()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Erlaubte Updates (Stornierung):
            -- 1. is_cancelled: false -> true
            -- 2. cancelled_by_entry_id: NULL -> UUID
            -- 3. cancelled_by_user_id: NULL -> UUID
            -- 4. cancelled_at: NULL -> Timestamp
            -- 5. cancellation_reason: NULL -> Text

            IF OLD.is_cancelled = FALSE AND NEW.is_cancelled = TRUE THEN
                -- Stornierung erlaubt - prüfe ob auch die anderen Felder korrekt gesetzt werden
                IF (NEW.cancelled_by_entry_id IS NOT NULL OR NEW.cancellation_reason IS NOT NULL) THEN
                    RETURN NEW;
                END IF;
            END IF;

            -- Setzen der Storno-Referenz erlaubt (separat von is_cancelled)
            IF OLD.cancelled_by_entry_id IS NULL AND NEW.cancelled_by_entry_id IS NOT NULL THEN
                RETURN NEW;
            END IF;

            -- Setzen des Audit-Trails erlaubt
            IF (OLD.cancelled_by_user_id IS NULL AND NEW.cancelled_by_user_id IS NOT NULL) OR
               (OLD.cancelled_at IS NULL AND NEW.cancelled_at IS NOT NULL) OR
               (OLD.cancellation_reason IS NULL AND NEW.cancellation_reason IS NOT NULL) THEN
                RETURN NEW;
            END IF;

            -- Alle anderen Updates sind verboten (GoBD)
            RAISE EXCEPTION 'GoBD-Verletzung: Kassenbucheinträge dürfen nicht geändert werden. Nutzen Sie die Stornofunktion.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Trigger auf cash_entries anwenden
    op.execute("""
        CREATE TRIGGER gobd_cash_entry_update_protection
        BEFORE UPDATE ON cash_entries
        FOR EACH ROW
        EXECUTE FUNCTION gobd_prevent_cash_entry_update();
    """)

    # Trigger-Funktion: Verhindert DELETE komplett
    op.execute("""
        CREATE OR REPLACE FUNCTION gobd_prevent_cash_entry_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'GoBD-Verletzung: Kassenbucheinträge dürfen nicht gelöscht werden. Nutzen Sie die Stornofunktion.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Trigger auf cash_entries anwenden
    op.execute("""
        CREATE TRIGGER gobd_cash_entry_delete_protection
        BEFORE DELETE ON cash_entries
        FOR EACH ROW
        EXECUTE FUNCTION gobd_prevent_cash_entry_delete();
    """)

    # ==========================================================================
    # 4. GoBD TRIGGER: BELEGNUMMERN-SCHUTZ
    # ==========================================================================

    # Trigger-Funktion: Stellt sicher dass entry_number nicht geändert wird
    op.execute("""
        CREATE OR REPLACE FUNCTION gobd_protect_entry_number()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.entry_number != NEW.entry_number THEN
                RAISE EXCEPTION 'GoBD-Verletzung: Belegnummern dürfen nicht geändert werden.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER gobd_entry_number_protection
        BEFORE UPDATE ON cash_entries
        FOR EACH ROW
        EXECUTE FUNCTION gobd_protect_entry_number();
    """)

    # ==========================================================================
    # 5. AUDIT LOG FÜR STORNIERUNGEN
    # ==========================================================================

    # Trigger für automatisches Audit-Logging bei Stornierungen
    op.execute("""
        CREATE OR REPLACE FUNCTION gobd_log_cancellation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.is_cancelled = FALSE AND NEW.is_cancelled = TRUE THEN
                -- Setze cancelled_at automatisch wenn nicht gesetzt
                IF NEW.cancelled_at IS NULL THEN
                    NEW.cancelled_at := NOW();
                END IF;

                -- Log in die Konsole (für Audit-Zwecke)
                RAISE NOTICE 'GoBD-Audit: CashEntry % storniert durch Entry %, User %, Grund: %',
                    OLD.id, NEW.cancelled_by_entry_id, NEW.cancelled_by_user_id, NEW.cancellation_reason;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER gobd_cancellation_audit
        BEFORE UPDATE ON cash_entries
        FOR EACH ROW
        EXECUTE FUNCTION gobd_log_cancellation();
    """)


def downgrade() -> None:
    # Trigger entfernen
    op.execute("DROP TRIGGER IF EXISTS gobd_cancellation_audit ON cash_entries")
    op.execute("DROP TRIGGER IF EXISTS gobd_entry_number_protection ON cash_entries")
    op.execute("DROP TRIGGER IF EXISTS gobd_cash_entry_delete_protection ON cash_entries")
    op.execute("DROP TRIGGER IF EXISTS gobd_cash_entry_update_protection ON cash_entries")

    # Trigger-Funktionen entfernen
    op.execute("DROP FUNCTION IF EXISTS gobd_log_cancellation()")
    op.execute("DROP FUNCTION IF EXISTS gobd_protect_entry_number()")
    op.execute("DROP FUNCTION IF EXISTS gobd_prevent_cash_entry_delete()")
    op.execute("DROP FUNCTION IF EXISTS gobd_prevent_cash_entry_update()")

    # Indizes entfernen
    op.drop_index('ix_cash_entries_register_year_active', table_name='cash_entries')
    op.drop_index('ix_cash_entries_category_id', table_name='cash_entries')
    op.drop_index('ix_cash_entries_fiscal_year', table_name='cash_entries')
    op.drop_index('ix_cash_entries_is_cancelled', table_name='cash_entries')

    # Spalten entfernen
    op.drop_column('cash_entries', 'cancelled_at')
    op.drop_column('cash_entries', 'cancelled_by_user_id')
