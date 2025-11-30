"""Extend totp_secret column for AES-256-GCM encrypted secrets

Revision ID: 016
Revises: 015
Create Date: 2025-11-30

Arbeitspaket 5: TOTP-Verschlüsselung

Die TOTP-Secrets werden nun mit AES-256-GCM verschlüsselt gespeichert.
Das verschlüsselte Format (Nonce + Ciphertext + Tag, Base64-encoded) benötigt
mehr Platz als der ursprüngliche Base32-encoded Secret.

Änderungen:
- totp_secret: String(32) -> String(256)

MIGRATION HINWEIS:
- Bestehende unverschlüsselte Secrets werden NICHT automatisch verschlüsselt
- Ein separates Migrationsskript muss ausgeführt werden um bestehende
  Secrets zu verschlüsseln (siehe: scripts/encrypt_existing_totp_secrets.py)
- Bis dahin funktioniert 2FA für bestehende Benutzer NICHT
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Erweitere totp_secret Spalte für verschlüsselte Daten.

    Verschlüsseltes Format:
    - Nonce: 12 Bytes
    - Ciphertext: ~32 Bytes (Base32 TOTP Secret)
    - Tag: 16 Bytes
    - Base64-encoded: ~80 Zeichen
    - Puffer für zukünftige Erweiterungen: 256 Zeichen
    """
    # SQLite unterstützt ALTER COLUMN nicht direkt
    # Daher verwenden wir batch_alter_table für Cross-DB-Kompatibilität
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'totp_secret',
            existing_type=sa.String(32),
            type_=sa.String(256),
            existing_nullable=True
        )


def downgrade() -> None:
    """
    WARNUNG: Downgrade LÖSCHT verschlüsselte Secrets!

    Bestehende verschlüsselte Secrets (>32 Zeichen) werden abgeschnitten
    und sind danach ungültig. Benutzer müssen 2FA neu einrichten.
    """
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'totp_secret',
            existing_type=sa.String(256),
            type_=sa.String(32),
            existing_nullable=True
        )
