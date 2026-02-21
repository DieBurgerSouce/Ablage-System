# -*- coding: utf-8 -*-
"""
Partitioning database models for Ablage-System.

Verwaltung der Tabellen-Partitionierung:
- PartitionManagement: Tracking aller Partitionen
- PartitionInterval: Enum fuer Partitionierungsintervalle

Feinpoliert und durchdacht - Enterprise-grade Table Partitioning.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    BigInteger,
    DateTime,
    Boolean,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.models import Base


class PartitionInterval(str, Enum):
    """Partitionierungsintervall-Typen."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


# Konfiguration der partitionierten Tabellen (Single Source of Truth)
PARTITIONED_TABLES_CONFIG = {
    "audit_logs_partitioned": {
        "source_table": "audit_logs",
        "partition_column": "created_at",
        "interval": PartitionInterval.QUARTERLY,
    },
    "document_access_logs_partitioned": {
        "source_table": "document_access_logs",
        "partition_column": "accessed_at",
        "interval": PartitionInterval.MONTHLY,
    },
    "document_lineage_events_partitioned": {
        "source_table": "document_lineage_events",
        "partition_column": "created_at",
        "interval": PartitionInterval.QUARTERLY,
    },
    "event_log_partitioned": {
        "source_table": "event_log",
        "partition_column": "created_at",
        "interval": PartitionInterval.MONTHLY,
    },
}


class PartitionManagement(Base):
    """Verwaltung und Tracking aller Tabellen-Partitionen.

    Jede Zeile repraesentiert eine einzelne Partition einer partitionierten
    Tabelle. Die Tabelle wird durch die Migration 239 erstellt und von
    den PostgreSQL-Funktionen create_time_partition() und
    archive_old_partitions() befuellt.

    Wird auch vom PartitionService und den Celery-Maintenance-Tasks
    fuer Monitoring und Statistiken verwendet.
    """

    __tablename__ = "partition_management"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tabellenname der partitionierten Parent-Tabelle
    table_name = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Name der partitionierten Parent-Tabelle",
    )

    # Eindeutiger Partitionsname (z.B. audit_logs_partitioned_p2026_01)
    partition_name = Column(
        String(150),
        nullable=False,
        unique=True,
        comment="Eindeutiger Name der Partition",
    )

    # Zeitbereich der Partition
    range_start = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Beginn des Partitionsbereichs (inklusive)",
    )
    range_end = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Ende des Partitionsbereichs (exklusiv)",
    )

    # Erstellungszeitpunkt
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Statistiken (werden periodisch aktualisiert)
    row_count = Column(
        BigInteger,
        default=0,
        comment="Ungefaehre Zeilenanzahl (periodisch aktualisiert)",
    )
    size_bytes = Column(
        BigInteger,
        default=0,
        comment="Speicherverbrauch in Bytes (periodisch aktualisiert)",
    )

    # Archivierungsstatus
    is_archived = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Partition wurde detached (nicht mehr in Abfragen)",
    )
    archived_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Archivierung",
    )

    __table_args__ = (
        Index("ix_partition_mgmt_table", "table_name"),
        Index("ix_partition_mgmt_archived", "table_name", "is_archived"),
        UniqueConstraint("partition_name", name="uq_partition_management_name"),
        {"comment": "Verwaltung und Tracking aller Tabellen-Partitionen (Phase 1.2)"},
    )

    def __repr__(self) -> str:
        return (
            f"<PartitionManagement {self.partition_name} "
            f"[{self.range_start} - {self.range_end}] "
            f"rows={self.row_count} archived={self.is_archived}>"
        )
