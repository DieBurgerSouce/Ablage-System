"""Field-Level Encryption Metadata Models.

Tracking fuer Key-Rotation und verschluesselte Felder.
Ermoeglicht die Ueberwachung des Verschluesselungsstatus
und die sichere Rotation von Encryption Keys.

DSGVO Art. 32: Sicherheit der Verarbeitung.

Feinpoliert und durchdacht - Enterprise Encryption Management.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.models import Base


class EncryptedFieldMeta(Base):
    """Metadaten fuer verschluesselte Datenbankfelder.

    Speichert Informationen darueber, welche Felder mit welchem Key
    und Algorithmus verschluesselt sind. Wird fuer Key-Rotation und
    Compliance-Reporting benoetigt.

    Beispiel:
        table_name='companies', column_name='iban',
        encryption_key_id='primary-v1', key_version=1
    """

    __tablename__ = "encrypted_field_meta"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Feld-Identifikation
    table_name = Column(
        String(100),
        nullable=False,
        comment="Name der Tabelle mit verschluesselter Spalte",
    )
    column_name = Column(
        String(100),
        nullable=False,
        comment="Name der verschluesselten Spalte",
    )

    # Verschluesselungs-Konfiguration
    encryption_key_id = Column(
        String(100),
        nullable=False,
        comment="Identifikator des verwendeten Schluessels",
    )
    encryption_algorithm = Column(
        String(50),
        nullable=False,
        default="AES-256-GCM",
        comment="Verschluesselungsalgorithmus",
    )
    key_version = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Version des Encryption Keys",
    )

    # Rotations-Status
    rotated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der letzten Key-Rotation",
    )
    row_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl der mit diesem Key verschluesselten Zeilen",
    )
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="Status: active, rotating, deprecated",
    )

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "table_name",
            "column_name",
            "key_version",
            name="uq_encrypted_field_meta_table_col_version",
        ),
        Index(
            "ix_encrypted_field_meta_table_column",
            "table_name",
            "column_name",
        ),
        {"comment": "Metadaten fuer Field-Level Encryption (DSGVO Art. 32)"},
    )

    def __repr__(self) -> str:
        return (
            f"<EncryptedFieldMeta "
            f"{self.table_name}.{self.column_name} "
            f"v{self.key_version} status={self.status}>"
        )


class KeyRotationLog(Base):
    """Protokoll fuer Key-Rotation-Vorgaenge.

    Dokumentiert jeden Schritt einer Key-Rotation fuer Audit-Zwecke.
    Unterstuetzt Fortschrittsverfolgung und Fehlerbehandlung bei
    unterbrochenen Rotationen.
    """

    __tablename__ = "key_rotation_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Feld-Identifikation
    table_name = Column(
        String(100),
        nullable=False,
        comment="Name der Tabelle",
    )
    column_name = Column(
        String(100),
        nullable=False,
        comment="Name der Spalte",
    )

    # Versions-Transition
    old_key_version = Column(
        Integer,
        nullable=False,
        comment="Vorherige Key-Version",
    )
    new_key_version = Column(
        Integer,
        nullable=False,
        comment="Neue Key-Version",
    )

    # Fortschritt
    rows_processed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Bisher verarbeitete Zeilen",
    )
    rows_total = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Gesamtzahl zu verarbeitender Zeilen",
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, in_progress, completed, failed",
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="Fehlermeldung bei fehlgeschlagener Rotation",
    )

    # Zeitstempel
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Start der Rotation",
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Ende der Rotation",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_key_rotation_logs_table_column",
            "table_name",
            "column_name",
        ),
        Index(
            "ix_key_rotation_logs_status",
            "status",
        ),
        {"comment": "Audit-Protokoll fuer Encryption Key-Rotation"},
    )

    def __repr__(self) -> str:
        return (
            f"<KeyRotationLog "
            f"{self.table_name}.{self.column_name} "
            f"v{self.old_key_version}->v{self.new_key_version} "
            f"status={self.status}>"
        )
