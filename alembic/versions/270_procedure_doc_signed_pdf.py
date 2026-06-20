"""procedure_documentation_versions: signiertes, persistiertes PDF-Artefakt (GoBD).

Additive Spalten fuer das signierte, WORM-persistierte, versionierte PDF der GoBD-
Verfahrensdokumentation. Das PDF liegt in MinIO (Object-Lock/WORM); die Signatur wird
mit der internen CA erzeugt (kein externes Zertifikat/kein Cloud-Dienst noetig). Alle
Spalten nullable -> Bestandszeilen bleiben gueltig (das PDF wird on-demand erzeugt).

Idempotent (ADD COLUMN IF NOT EXISTS). Downgrade entfernt die Spalten wieder.

Revision ID: 270
Revises: 269
Create Date: 2026-06-20
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "270"
down_revision = "269"
branch_labels = None
depends_on = None

_COLS = [
    ("pdf_object_key", "VARCHAR(512)"),
    ("pdf_sha256", "VARCHAR(64)"),
    ("pdf_signature", "TEXT"),
    ("pdf_signature_alg", "VARCHAR(40)"),
    ("pdf_signing_cert_serial", "VARCHAR(64)"),
    ("pdf_signed_at", "TIMESTAMP WITH TIME ZONE"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for name, typ in _COLS:
        bind.execute(sa.text(
            f"ALTER TABLE procedure_documentation_versions "
            f"ADD COLUMN IF NOT EXISTS {name} {typ}"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    for name, _typ in _COLS:
        bind.execute(sa.text(
            f"ALTER TABLE procedure_documentation_versions "
            f"DROP COLUMN IF EXISTS {name}"
        ))
