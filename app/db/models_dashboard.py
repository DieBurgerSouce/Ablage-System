# -*- coding: utf-8 -*-
"""
Dashboard-Builder Datenbankmodelle fuer Ablage-System.

Phase 7.3: Dashboard-Builder

Modelle:
- DashboardConfig: Benutzerdefinierte Dashboard-Konfigurationen mit Grid-Layout
- DashboardBuilderWidget: Widget-Instanzen auf Dashboard-Konfigurationen

Widget-Typen:
  invoice_status, cashflow_chart, ocr_queue, kpi_cards, anomaly_summary,
  recent_documents, open_tasks, integration_health, active_learning_stats

Rollen-basierte Standard-Dashboards:
  buchhaltung    -> invoice_status, cashflow_chart, open_tasks
  management     -> kpi_cards, cashflow_chart, anomaly_summary
  sachbearbeitung-> ocr_queue, recent_documents, active_learning_stats
  admin          -> integration_health, ocr_queue, kpi_cards

Feinpoliert und durchdacht - Enterprise Dashboard-Builder.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# Enums
# =============================================================================


class WidgetTypeEnum(str, Enum):
    """Verfuegbare Widget-Typen im Dashboard-Builder."""

    INVOICE_STATUS = "invoice_status"
    """Rechnungsstatus-Uebersicht (offene, ueberfaellige Rechnungen)."""

    CASHFLOW_CHART = "cashflow_chart"
    """Cashflow-Diagramm mit Prognose."""

    OCR_QUEUE = "ocr_queue"
    """OCR-Warteschlange mit Status und Fortschritt."""

    KPI_CARDS = "kpi_cards"
    """KPI-Karten-Raster mit Trendanzeige."""

    ANOMALY_SUMMARY = "anomaly_summary"
    """Anomalie-Zusammenfassung mit Schweregrad-Verteilung."""

    RECENT_DOCUMENTS = "recent_documents"
    """Zuletzt verarbeitete Dokumente."""

    OPEN_TASKS = "open_tasks"
    """Offene Aufgaben und Genehmigungen."""

    INTEGRATION_HEALTH = "integration_health"
    """Status aller Integrationen (DATEV, Lexware, etc.)."""

    ACTIVE_LEARNING_STATS = "active_learning_stats"
    """Active-Learning-Pipeline Statistiken."""


# Erlaubte Widget-Typ-Werte fuer CheckConstraint
_VALID_WIDGET_TYPES = (
    "invoice_status, cashflow_chart, ocr_queue, kpi_cards, anomaly_summary, "
    "recent_documents, open_tasks, integration_health, active_learning_stats"
)


# =============================================================================
# DashboardConfig
# =============================================================================


class DashboardConfig(Base):
    """
    Benutzerdefinierte Dashboard-Konfiguration.

    Jeder Benutzer kann mehrere Dashboards anlegen und eines als Standard
    markieren. Dashboards koennen firmen-intern geteilt werden (is_shared).

    Das Grid-Layout wird als JSON-Array gespeichert:
      [{"widget_id": "uuid", "x": 0, "y": 0, "w": 6, "h": 4}, ...]

    Attribute:
        id:          Eindeutige UUID des Dashboards.
        company_id:  Mandanten-Zuordnung (Multi-Tenant).
        user_id:     Eigentuemerbenutzer.
        name:        Anzeigename (max. 255 Zeichen).
        description: Optionale Beschreibung.
        layout:      Grid-Layout-Konfiguration als JSONB-Array.
        is_default:  Standarddashboard des Benutzers (je User max. 1).
        is_shared:   Freigabe fuer andere Benutzer derselben Firma.
        created_at:  Erstellungszeitpunkt.
        updated_at:  Letzter Aenderungszeitpunkt.
    """

    __tablename__ = "dashboard_builder_configs"

    # -------------------------------------------------------------------------
    # Primaerschluessel
    # -------------------------------------------------------------------------

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige Dashboard-ID",
    )

    # -------------------------------------------------------------------------
    # Multi-Tenant / Besitzer
    # -------------------------------------------------------------------------

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung (RESTRICT verhindert versehentliches Loeschen)",
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Eigentuemer-Benutzer",
    )

    # -------------------------------------------------------------------------
    # Metadaten
    # -------------------------------------------------------------------------

    name = Column(
        String(255),
        nullable=False,
        comment="Anzeigename des Dashboards",
    )
    description = Column(
        Text,
        nullable=True,
        comment="Optionale Beschreibung",
    )

    # -------------------------------------------------------------------------
    # Layout-Konfiguration
    # -------------------------------------------------------------------------

    layout = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment=(
            "Grid-Layout als JSONB-Array: "
            '[{"widget_id": "uuid", "x": 0, "y": 0, "w": 6, "h": 4}]'
        ),
    )

    # -------------------------------------------------------------------------
    # Status-Flags
    # -------------------------------------------------------------------------

    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Standarddashboard des Benutzers (je User max. 1 aktives)",
    )
    is_shared = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Firmenweit freigegeben (alle Benutzer der Company koennen lesen)",
    )

    # -------------------------------------------------------------------------
    # Zeitstempel
    # -------------------------------------------------------------------------

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Erstellungszeitpunkt",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Letzter Aenderungszeitpunkt",
    )

    # -------------------------------------------------------------------------
    # Beziehungen
    # -------------------------------------------------------------------------

    company = relationship(
        "Company",
        backref="dashboard_builder_configs",
    )
    user = relationship(
        "User",
        backref="dashboard_builder_configs",
        foreign_keys=[user_id],
    )
    widgets = relationship(
        "DashboardBuilderWidget",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="DashboardBuilderWidget.created_at",
    )

    # -------------------------------------------------------------------------
    # Tabellenargumente / Constraints / Indexes
    # -------------------------------------------------------------------------

    __table_args__ = (
        Index(
            "ix_dashboard_builder_configs_company_user",
            "company_id",
            "user_id",
        ),
        Index(
            "ix_dashboard_builder_configs_company_shared",
            "company_id",
            "is_shared",
        ),
    )

    # -------------------------------------------------------------------------
    # Hilfsmethoden
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Konvertiert die Dashboard-Konfiguration zu einem Dictionary."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "user_id": str(self.user_id),
            "name": self.name,
            "description": self.description,
            "layout": self.layout or [],
            "is_default": self.is_default,
            "is_shared": self.is_shared,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "widgets": [w.to_dict() for w in self.widgets] if self.widgets else [],
        }

    def __repr__(self) -> str:
        return (
            f"<DashboardConfig(id={self.id}, name={self.name!r}, "
            f"company={self.company_id}, user={self.user_id})>"
        )


# =============================================================================
# DashboardBuilderWidget
# =============================================================================


class DashboardBuilderWidget(Base):
    """
    Widget-Instanz auf einem Dashboard-Builder-Dashboard.

    Jedes Widget hat einen Typ, Titel, eine widget-spezifische Konfiguration
    und eine Datenquelle, die bestimmt, welcher Service die Daten liefert.

    Widget-Typen (WidgetTypeEnum):
      invoice_status      - InvoiceTracking-Service
      cashflow_chart      - Cashflow-Predictor-Service
      ocr_queue           - OCR-Backend-Manager / ProcessingJob
      kpi_cards           - Smart-Dashboard-Service (Echtzeit-KPIs)
      anomaly_summary     - Anomalie-Erkennungs-Service
      recent_documents    - Dokument-CRUD-Service
      open_tasks          - Approval-/Task-Service
      integration_health  - Integration-Status-Service
      active_learning_stats - Active-Learning-Service

    Attribute:
        id:                       Eindeutige Widget-ID.
        dashboard_id:             Zugehoerige Dashboard-Konfiguration (CASCADE).
        widget_type:              Widget-Typ (aus WidgetTypeEnum).
        title:                    Anzeigename des Widgets.
        config:                   Widget-spezifische Einstellungen als JSONB.
        data_source:              Service/Endpunkt fuer Datenbeschaffung.
        refresh_interval_seconds: Aktualisierungsintervall (Standard: 300 s).
        created_at:               Erstellungszeitpunkt.
    """

    __tablename__ = "dashboard_builder_widgets"

    # -------------------------------------------------------------------------
    # Primaerschluessel
    # -------------------------------------------------------------------------

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige Widget-ID",
    )

    # -------------------------------------------------------------------------
    # Fremdschluessel zum Dashboard
    # -------------------------------------------------------------------------

    dashboard_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dashboard_builder_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Zugehoerige Dashboard-Konfiguration (wird beim Loeschen mitgeloescht)",
    )

    # -------------------------------------------------------------------------
    # Widget-Definition
    # -------------------------------------------------------------------------

    widget_type = Column(
        String(50),
        nullable=False,
        comment="Widget-Typ (invoice_status, cashflow_chart, ...)",
    )
    title = Column(
        String(255),
        nullable=False,
        comment="Anzeigename des Widgets (deutsch)",
    )
    config = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment=(
            "Widget-spezifische Einstellungen als JSONB "
            "(Farbe, Zeitraum, Schwellwerte, etc.)"
        ),
    )

    # -------------------------------------------------------------------------
    # Datenquelle und Aktualisierung
    # -------------------------------------------------------------------------

    data_source = Column(
        String(100),
        nullable=False,
        comment=(
            "Interne Bezeichnung des Service/Endpunkts der Daten liefert "
            "(z. B. 'invoice_tracking', 'cashflow_predictor')"
        ),
    )
    refresh_interval_seconds = Column(
        Integer,
        nullable=False,
        default=300,
        comment="Aktualisierungsintervall in Sekunden (Standard: 300, Minimum: 30)",
    )

    # -------------------------------------------------------------------------
    # Zeitstempel
    # -------------------------------------------------------------------------

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Erstellungszeitpunkt",
    )

    # -------------------------------------------------------------------------
    # Beziehungen
    # -------------------------------------------------------------------------

    dashboard = relationship(
        "DashboardConfig",
        back_populates="widgets",
        foreign_keys=[dashboard_id],
    )

    # -------------------------------------------------------------------------
    # Tabellenargumente / Constraints / Indexes
    # -------------------------------------------------------------------------

    __table_args__ = (
        CheckConstraint(
            "widget_type IN ("
            "'invoice_status', 'cashflow_chart', 'ocr_queue', "
            "'kpi_cards', 'anomaly_summary', 'recent_documents', "
            "'open_tasks', 'integration_health', 'active_learning_stats'"
            ")",
            name="ck_dashboard_builder_widget_type",
        ),
        CheckConstraint(
            "refresh_interval_seconds >= 30",
            name="ck_dashboard_builder_widget_refresh_min",
        ),
        Index(
            "ix_dashboard_builder_widgets_dashboard",
            "dashboard_id",
        ),
        Index(
            "ix_dashboard_builder_widgets_type",
            "dashboard_id",
            "widget_type",
        ),
    )

    # -------------------------------------------------------------------------
    # Hilfsmethoden
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Konvertiert das Widget zu einem Dictionary."""
        return {
            "id": str(self.id),
            "dashboard_id": str(self.dashboard_id),
            "widget_type": self.widget_type,
            "title": self.title,
            "config": self.config or {},
            "data_source": self.data_source,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<DashboardBuilderWidget(id={self.id}, type={self.widget_type!r}, "
            f"dashboard={self.dashboard_id})>"
        )
