"""Field-Level Encryption Infrastruktur.

Revision ID: 241
Revises: 240
Create Date: 2026-02-20

Erstellt die Infrastruktur fuer DSGVO-konforme Field-Level Encryption:
- encrypted_field_meta: Metadaten fuer verschluesselte Felder
- key_rotation_logs: Audit-Protokoll fuer Key-Rotation
- Spalten-Erweiterung: Verschluesselte Daten benoetigen mehr Platz
- Seed-Daten: Initiale Metadaten fuer alle zu verschluesselnden Felder

Die eigentliche Datenverschluesselung erfolgt ueber einen separaten
Celery-Task (encryption.migrate_field), da die Verschluesselung
in Python stattfindet und nicht auf DB-Ebene.

DSGVO Art. 32 - Sicherheit der Verarbeitung.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "241"
down_revision = "240"
branch_labels = None
depends_on = None


# Felder, die verschluesselt werden sollen
ENCRYPTED_FIELD_SEEDS = [
    ("companies", "iban", "companies.iban"),
    ("companies", "bic", "companies.bic"),
    ("companies", "vat_id", "companies.vat_id"),
    ("companies", "tax_number", "companies.tax_number"),
    ("business_entities", "iban", "business_entities.iban"),
    ("business_entities", "bic", "business_entities.bic"),
    ("business_entities", "vat_id", "business_entities.vat_id"),
    ("business_entities", "tax_number", "business_entities.tax_number"),
    ("bank_transactions", "counterparty_iban", "bank_transactions.counterparty_iban"),
    ("bank_transactions", "counterparty_bic", "bank_transactions.counterparty_bic"),
]

# Spalten, die erweitert werden muessen (verschluesselte Daten sind laenger)
COLUMN_WIDENING = [
    ("companies", "iban", sa.String(34)),
    ("companies", "bic", sa.String(11)),
    ("companies", "vat_id", sa.String(20)),
    ("companies", "tax_number", sa.String(50)),
    ("business_entities", "iban", sa.String(34)),
    ("business_entities", "bic", sa.String(11)),
    ("business_entities", "vat_id", sa.String(20)),
    ("business_entities", "tax_number", sa.String(30)),
    ("bank_transactions", "counterparty_iban", sa.String(34)),
    ("bank_transactions", "counterparty_bic", sa.String(11)),
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. encrypted_field_meta - Metadaten fuer verschluesselte Felder
    # ------------------------------------------------------------------
    op.create_table(
        "encrypted_field_meta",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_name", sa.String(100), nullable=False,
                  comment="Name der Tabelle mit verschluesselter Spalte"),
        sa.Column("column_name", sa.String(100), nullable=False,
                  comment="Name der verschluesselten Spalte"),
        sa.Column("encryption_key_id", sa.String(100), nullable=False,
                  comment="Identifikator des verwendeten Schluessels"),
        sa.Column("encryption_algorithm", sa.String(50), nullable=False,
                  server_default="AES-256-GCM",
                  comment="Verschluesselungsalgorithmus"),
        sa.Column("key_version", sa.Integer(), nullable=False,
                  server_default="1",
                  comment="Version des Encryption Keys"),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Zeitpunkt der letzten Key-Rotation"),
        sa.Column("row_count", sa.Integer(), nullable=False,
                  server_default="0",
                  comment="Anzahl der mit diesem Key verschluesselten Zeilen"),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="active",
                  comment="Status: active, rotating, deprecated"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "table_name", "column_name", "key_version",
            name="uq_encrypted_field_meta_table_col_version",
        ),
        comment="Metadaten fuer Field-Level Encryption (DSGVO Art. 32)",
    )
    op.create_index(
        "ix_encrypted_field_meta_table_column",
        "encrypted_field_meta",
        ["table_name", "column_name"],
    )

    # ------------------------------------------------------------------
    # 2. key_rotation_logs - Audit-Protokoll fuer Key-Rotation
    # ------------------------------------------------------------------
    op.create_table(
        "key_rotation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_name", sa.String(100), nullable=False,
                  comment="Name der Tabelle"),
        sa.Column("column_name", sa.String(100), nullable=False,
                  comment="Name der Spalte"),
        sa.Column("old_key_version", sa.Integer(), nullable=False,
                  comment="Vorherige Key-Version"),
        sa.Column("new_key_version", sa.Integer(), nullable=False,
                  comment="Neue Key-Version"),
        sa.Column("rows_processed", sa.Integer(), nullable=False,
                  server_default="0",
                  comment="Bisher verarbeitete Zeilen"),
        sa.Column("rows_total", sa.Integer(), nullable=False,
                  server_default="0",
                  comment="Gesamtzahl zu verarbeitender Zeilen"),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending",
                  comment="Status: pending, in_progress, completed, failed"),
        sa.Column("error_message", sa.Text(), nullable=True,
                  comment="Fehlermeldung bei fehlgeschlagener Rotation"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Start der Rotation"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Ende der Rotation"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        comment="Audit-Protokoll fuer Encryption Key-Rotation",
    )
    op.create_index(
        "ix_key_rotation_logs_table_column",
        "key_rotation_logs",
        ["table_name", "column_name"],
    )
    op.create_index(
        "ix_key_rotation_logs_status",
        "key_rotation_logs",
        ["status"],
    )

    # ------------------------------------------------------------------
    # 3. Spalten erweitern - verschluesselte Daten brauchen mehr Platz
    #    Base64(nonce + ciphertext + tag) ergibt ca. 4x Klartext-Laenge
    #    Wir nutzen Text statt varchar(1000) fuer maximale Flexibilitaet
    # ------------------------------------------------------------------
    for table_name, column_name, original_type in COLUMN_WIDENING:
        op.alter_column(
            table_name,
            column_name,
            type_=sa.Text(),
            existing_type=original_type,
            existing_nullable=True,
        )

    # ------------------------------------------------------------------
    # 4. Seed-Daten: Initiale Metadaten fuer verschluesselte Felder
    # ------------------------------------------------------------------
    encrypted_field_meta = sa.table(
        "encrypted_field_meta",
        sa.column("id", postgresql.UUID),
        sa.column("table_name", sa.String),
        sa.column("column_name", sa.String),
        sa.column("encryption_key_id", sa.String),
        sa.column("encryption_algorithm", sa.String),
        sa.column("key_version", sa.Integer),
        sa.column("row_count", sa.Integer),
        sa.column("status", sa.String),
    )

    for table_name, column_name, aad_context in ENCRYPTED_FIELD_SEEDS:
        op.execute(
            encrypted_field_meta.insert().values(
                id=sa.text("gen_random_uuid()"),
                table_name=table_name,
                column_name=column_name,
                encryption_key_id="primary",
                encryption_algorithm="AES-256-GCM",
                key_version=1,
                row_count=0,
                status="pending",
            )
        )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Spalten zurueck auf urspruengliche Groesse
    #    ACHTUNG: Verschluesselte Daten gehen verloren wenn sie nicht
    #    vorher entschluesselt wurden!
    # ------------------------------------------------------------------
    for table_name, column_name, original_type in reversed(COLUMN_WIDENING):
        op.alter_column(
            table_name,
            column_name,
            type_=original_type,
            existing_type=sa.Text(),
            existing_nullable=True,
        )

    # ------------------------------------------------------------------
    # 2. Tabellen entfernen
    # ------------------------------------------------------------------
    op.drop_index("ix_key_rotation_logs_status", table_name="key_rotation_logs")
    op.drop_index("ix_key_rotation_logs_table_column", table_name="key_rotation_logs")
    op.drop_table("key_rotation_logs")

    op.drop_index("ix_encrypted_field_meta_table_column", table_name="encrypted_field_meta")
    op.drop_table("encrypted_field_meta")
