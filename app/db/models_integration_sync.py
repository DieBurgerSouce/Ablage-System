# -*- coding: utf-8 -*-
"""Integrations-Sync Dashboard Models.

Speichert Konfiguration und Sync-Protokolle für alle externen Integrationen
(DATEV, Lexware, Banking, Slack, E-Mail).

Satellite-Modell - importiert Base und CrossDBJSON aus app.db.models.
"""

import uuid
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ---------------------------------------------------------------------------
# Gültige Werte (als Modul-Konstanten zur Wiederverwendung)
# ---------------------------------------------------------------------------

INTEGRATION_TYPES = ("datev", "lexware", "banking", "slack", "email")
"""Unterstützte Integrations-Typen."""

SYNC_STATUS_VALUES = ("success", "error", "partial")
"""Mögliche Synchronisations-Ergebnisse."""

SYNC_TYPE_VALUES = ("full", "incremental", "manual")
"""Synchronisations-Arten."""

SYNC_LOG_STATUS_VALUES = ("started", "success", "error", "partial")
"""Lebenszyklus-Status eines Sync-Laufs."""


# ---------------------------------------------------------------------------
# IntegrationConfig
# ---------------------------------------------------------------------------

class IntegrationConfig(Base):
    """Konfiguration und aktueller Status einer externen Integration.

    Speichert pro Mandant die Einstellungen für jede Integration sowie
    den zuletzt bekannten Sync-Status. Dient als zentrale Wahrheitsquelle
    für das Integrations-Dashboard.
    """

    __tablename__ = "integration_configs"

    # -----------------------------------------------------------------------
    # Primärschlüssel
    # -----------------------------------------------------------------------
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige Integrations-Konfigurations-ID",
    )

    # -----------------------------------------------------------------------
    # Multi-Tenant
    # -----------------------------------------------------------------------
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandant, zu dem diese Integration gehört",
    )

    # -----------------------------------------------------------------------
    # Integrations-Stammdaten
    # -----------------------------------------------------------------------
    integration_type = Column(
        String(50),
        nullable=False,
        comment="Typ der Integration: datev | lexware | banking | slack | email",
    )

    display_name = Column(
        String(255),
        nullable=False,
        comment="Anzeigename im Dashboard (z. B. 'DATEV Rechenzentrum')",
    )

    config = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment="Integrationsspezifische Konfigurationsdaten (ohne Geheimnisse)",
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Gibt an, ob die Integration aktiv synchronisieren soll",
    )

    # -----------------------------------------------------------------------
    # Letzter Sync-Status (Denormalisiert für schnelle Dashboard-Abfragen)
    # -----------------------------------------------------------------------
    last_sync_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der letzten abgeschlossenen Synchronisation",
    )

    last_sync_status = Column(
        String(20),
        nullable=True,
        comment="Ergebnis der letzten Synchronisation: success | error | partial",
    )

    last_error_message = Column(
        Text,
        nullable=True,
        comment="Fehlermeldung der letzten fehlgeschlagenen Synchronisation",
    )

    # -----------------------------------------------------------------------
    # Sync-Konfiguration
    # -----------------------------------------------------------------------
    sync_interval_minutes = Column(
        Integer,
        nullable=False,
        default=60,
        comment="Automatisches Sync-Intervall in Minuten (Standard: 60)",
    )

    # -----------------------------------------------------------------------
    # Zeitstempel
    # -----------------------------------------------------------------------
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Erstellungszeitpunkt",
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Letzter Änderungszeitpunkt",
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------
    company = relationship("Company", backref="integration_configs")
    sync_logs = relationship(
        "IntegrationSyncLog",
        back_populates="integration_config",
        lazy="dynamic",
        order_by="desc(IntegrationSyncLog.started_at)",
    )

    __table_args__ = (
        # Eindeutigkeit: Pro Mandant nur eine Konfiguration pro Typ
        # (enforced in DB, entspricht UX "eine DATEV-Konfiguration pro Firma")
        Index(
            "ix_integration_configs_company_type",
            "company_id",
            "integration_type",
        ),
        # Schnell-Filter auf aktive Integrationen
        Index(
            "ix_integration_configs_company_active",
            "company_id",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
    )

    def to_dict(self) -> dict:
        """Serialisiert die Konfiguration als Dictionary für API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "integration_type": self.integration_type,
            "display_name": self.display_name,
            "config": self.config or {},
            "is_active": self.is_active,
            "last_sync_at": (
                self.last_sync_at.isoformat() if self.last_sync_at else None
            ),
            "last_sync_status": self.last_sync_status,
            "last_error_message": self.last_error_message,
            "sync_interval_minutes": self.sync_interval_minutes,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at else None
            ),
        }


# ---------------------------------------------------------------------------
# IntegrationSyncLog
# ---------------------------------------------------------------------------

class IntegrationSyncLog(Base):
    """Detailliertes Protokoll eines einzelnen Synchronisations-Laufs.

    Jeder Sync-Vorgang erzeugt einen Log-Eintrag mit Start-/Endzeit,
    verarbeiteten Datensätzen und Fehlerdetails. Dient der
    Fehlerdiagnose und Performance-Analyse im Dashboard.
    """

    __tablename__ = "integration_sync_logs"

    # -----------------------------------------------------------------------
    # Primärschlüssel
    # -----------------------------------------------------------------------
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige Log-Eintrags-ID",
    )

    # -----------------------------------------------------------------------
    # Referenz auf Konfig (mit Cascade-Schutz)
    # -----------------------------------------------------------------------
    integration_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("integration_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Zugehörige Integrations-Konfiguration",
    )

    # -----------------------------------------------------------------------
    # Multi-Tenant (redundant für effiziente partitionierte Abfragen)
    # -----------------------------------------------------------------------
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandant - denormalisiert für direkte Mandanten-Abfragen",
    )

    # -----------------------------------------------------------------------
    # Sync-Art und -Status
    # -----------------------------------------------------------------------
    sync_type = Column(
        String(20),
        nullable=False,
        comment="Art der Synchronisation: full | incremental | manual",
    )

    status = Column(
        String(20),
        nullable=False,
        default="started",
        comment="Aktueller Status: started | success | error | partial",
    )

    # -----------------------------------------------------------------------
    # Verarbeitungsstatistiken
    # -----------------------------------------------------------------------
    items_processed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl erfolgreich verarbeiteter Datensätze",
    )

    items_failed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl fehlerhafter Datensätze",
    )

    items_total = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Gesamtanzahl der zur Verarbeitung vorgesehenen Datensätze",
    )

    error_details = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Strukturierte Fehlerdetails (Liste von Einzel-Fehlern)",
    )

    # -----------------------------------------------------------------------
    # Zeitsteuerung
    # -----------------------------------------------------------------------
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Startzeitpunkt des Sync-Laufs",
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Abschlusszeitpunkt (None wenn noch in Bearbeitung)",
    )

    duration_seconds = Column(
        Float,
        nullable=True,
        comment="Laufzeit in Sekunden (berechnet bei Abschluss)",
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------
    integration_config = relationship(
        "IntegrationConfig",
        back_populates="sync_logs",
    )
    company = relationship("Company", backref="integration_sync_logs")

    __table_args__ = (
        # Vollständige History eines Sync-Laufs nach Mandant + Typ + Zeit
        Index(
            "ix_sync_logs_company_config_time",
            "company_id",
            "integration_config_id",
            "started_at",
        ),
        # Schnell-Filter auf fehlgeschlagene Läufe (für Fehler-Dashboard)
        Index(
            "ix_sync_logs_company_status",
            "company_id",
            "status",
            "started_at",
            postgresql_where=text("status IN ('error', 'partial')"),
        ),
    )

    def to_dict(self) -> dict:
        """Serialisiert den Log-Eintrag als Dictionary für API-Responses."""
        return {
            "id": str(self.id),
            "integration_config_id": str(self.integration_config_id),
            "company_id": str(self.company_id),
            "sync_type": self.sync_type,
            "status": self.status,
            "items_processed": self.items_processed,
            "items_failed": self.items_failed,
            "items_total": self.items_total,
            "error_details": self.error_details or {},
            "started_at": (
                self.started_at.isoformat() if self.started_at else None
            ),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
        }
