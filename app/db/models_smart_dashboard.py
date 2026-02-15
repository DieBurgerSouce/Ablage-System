# -*- coding: utf-8 -*-
"""
Smart Dashboard database models for Ablage-System.

Modelle fuer Features #2 und #6:
- Smart Dashboard mit Tab-Struktur (Uebersicht, Finanzen, Dokumente, Workflows, System)
- Echtzeit-KPIs mit Trend-Berechnung
- Dokument-Fortschritts-Tracking (DHL-Stil)
- Batch-Fortschritts-Tracking
- Benutzerspezifische Widget-Layouts

Feinpoliert und durchdacht - Enterprise Smart Dashboard.
"""

import uuid
from enum import Enum

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
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# Enums
# =============================================================================


class DashboardTab(str, Enum):
    """Dashboard-Tab Auswahl."""
    OVERVIEW = "overview"           # Uebersicht
    FINANCE = "finance"             # Finanzen
    DOCUMENTS = "documents"         # Dokumente
    WORKFLOWS = "workflows"         # Workflows
    SYSTEM = "system"               # System


class WidgetType(str, Enum):
    """Widget-Typen fuer Dashboard."""
    KPI_CARD = "kpi_card"                  # Einzelne KPI-Karte
    CHART_LINE = "chart_line"              # Linien-Diagramm
    CHART_BAR = "chart_bar"               # Balken-Diagramm
    CHART_PIE = "chart_pie"               # Kreisdiagramm
    TABLE = "table"                        # Tabelle
    PROGRESS_LIST = "progress_list"        # Fortschrittsliste
    ACTIVITY_FEED = "activity_feed"        # Aktivitaets-Feed
    QUEUE_STATUS = "queue_status"          # Warteschlangen-Status
    ALERT_SUMMARY = "alert_summary"        # Alert-Zusammenfassung
    CASHFLOW_CHART = "cashflow_chart"      # Cashflow-Diagramm
    SYSTEM_HEALTH = "system_health"        # System-Gesundheit
    SPARKLINE = "sparkline"                # Sparkline-Miniatur
    GAUGE = "gauge"                        # Tacho-Anzeige
    STATUS = "status"                      # Status-Anzeige


# =============================================================================
# Smart Dashboard Config (benutzerspezifisch)
# =============================================================================


class SmartDashboardConfig(Base):
    """
    Benutzerspezifische Smart-Dashboard-Konfiguration.

    Speichert Tab-Praeferenzen, Widget-Layouts und
    Rollen-basierte Filterung pro Benutzer.
    """
    __tablename__ = "smart_dashboard_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firma und Benutzer
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tab-Konfiguration
    active_tab = Column(
        String(20),
        nullable=False,
        default=DashboardTab.OVERVIEW.value,
    )

    # Widget-Layout als JSON (pro Tab verschieden)
    widget_layout = Column(CrossDBJSON, default=dict)

    # Rollen-basierte Ansicht
    role_filter = Column(String(50), nullable=True)

    # Aktualisierungsintervall in Sekunden
    refresh_interval_seconds = Column(Integer, nullable=False, default=30)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="smart_dashboard_configs")
    user = relationship("User", backref="smart_dashboard_configs")

    __table_args__ = (
        Index("ix_smart_dashboard_company_user", "company_id", "user_id"),
        CheckConstraint(
            "active_tab IN ('overview', 'finance', 'documents', 'workflows', 'system')",
            name="ck_smart_dashboard_active_tab",
        ),
        CheckConstraint(
            "refresh_interval_seconds >= 5 AND refresh_interval_seconds <= 300",
            name="ck_smart_dashboard_refresh_interval",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert Konfiguration zu Dictionary."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "user_id": str(self.user_id),
            "active_tab": self.active_tab,
            "widget_layout": self.widget_layout or {},
            "role_filter": self.role_filter,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# Dashboard KPI Cache
# =============================================================================


class DashboardKPI(Base):
    """
    KPI-Werte fuer das Dashboard.

    Speichert berechnete KPI-Werte mit Trend-Informationen
    und historischen Vergleichswerten.
    """
    __tablename__ = "dashboard_kpis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firma
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # KPI-Identifikation
    kpi_key = Column(String(100), nullable=False, index=True)

    # Werte
    current_value = Column(Float, nullable=False, default=0.0)
    previous_value = Column(Float, nullable=True)

    # Einheit und Trend
    unit = Column(String(20), nullable=False, default="count")
    trend_direction = Column(String(10), nullable=False, default="stable")

    # Berechnet am
    calculated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Zusaetzliche Metadaten
    kpi_metadata = Column(CrossDBJSON, default=dict)

    # Relationships
    company = relationship("Company", backref="dashboard_kpis")

    __table_args__ = (
        Index("ix_dashboard_kpis_company_key", "company_id", "kpi_key"),
        Index("ix_dashboard_kpis_calculated_at", "calculated_at"),
        CheckConstraint(
            "trend_direction IN ('up', 'down', 'stable')",
            name="ck_dashboard_kpis_trend",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert KPI zu Dictionary."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "kpi_key": self.kpi_key,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "unit": self.unit,
            "trend_direction": self.trend_direction,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
            "metadata": self.kpi_metadata or {},
        }


# =============================================================================
# Dashboard Widget Definition (firmen-weite Widget-Templates)
# =============================================================================


class DashboardWidget(Base):
    """
    Widget-Definitionen fuer das Smart Dashboard.

    Firmen-weite Widget-Vorlagen mit:
    - Tab-Zuordnung
    - Rollen-basierte Sichtbarkeit
    - Standard-Positionierung
    - Datenquelle (Service-Methode)
    - Konfigurierbares Refresh-Intervall
    """
    __tablename__ = "smart_dashboard_widgets"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige Widget-ID",
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung",
    )
    tab = Column(
        String(30),
        nullable=False,
        index=True,
        comment="Dashboard-Tab: overview, finance, documents, workflows, system",
    )
    widget_type = Column(
        String(100),
        nullable=False,
        comment="Widget-Typ: kpi_card, chart_line, table, progress_list, etc.",
    )
    title = Column(
        String(200),
        nullable=False,
        comment="Anzeigename des Widgets (deutsch)",
    )
    config = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Widget-spezifische Konfiguration (Farbe, Icon, Einheit, etc.)",
    )

    # Grid-Position (12-Spalten-Grid)
    position_x = Column(Integer, nullable=False, default=0, comment="X-Position im Grid")
    position_y = Column(Integer, nullable=False, default=0, comment="Y-Position im Grid")
    position_w = Column(Integer, nullable=False, default=4, comment="Breite im Grid (Spalten)")
    position_h = Column(Integer, nullable=False, default=3, comment="Hoehe im Grid (Zeilen)")

    # Rollen-basierte Sichtbarkeit
    min_roles = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Minimale Rollen fuer Sichtbarkeit (leer = alle Rollen)",
    )

    # Status-Flags
    is_default = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Standard-Widget (wird bei neuem User automatisch angezeigt)",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Widget aktiv (deaktivierte Widgets werden nicht geladen)",
    )

    # Datenquelle und Refresh
    refresh_interval_seconds = Column(
        Integer,
        nullable=False,
        default=60,
        comment="Aktualisierungsintervall in Sekunden (0 = manuell)",
    )
    data_source = Column(
        String(200),
        nullable=True,
        comment="Service-Methode fuer Daten (z.B. 'get_realtime_kpis', 'get_finance_tab')",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_smart_widgets_company_tab", "company_id", "tab"),
        Index("ix_smart_widgets_active", "company_id", "is_active"),
    )

    def to_dict(self) -> dict:
        """Konvertiert Widget zu Dictionary."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "tab": self.tab,
            "widget_type": self.widget_type,
            "title": self.title,
            "config": self.config or {},
            "position": {
                "x": self.position_x,
                "y": self.position_y,
                "w": self.position_w,
                "h": self.position_h,
            },
            "min_roles": self.min_roles or [],
            "is_default": self.is_default,
            "is_active": self.is_active,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "data_source": self.data_source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# User-spezifisches Layout (Personalisierung)
# =============================================================================


class DashboardLayout(Base):
    """
    Benutzerspezifisches Dashboard-Layout.

    Speichert die individuelle Widget-Anordnung pro User und Tab.
    Ermoeglicht Drag-and-Drop Personalisierung.
    """
    __tablename__ = "smart_dashboard_layouts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Eindeutige Layout-ID",
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Benutzer-ID",
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung",
    )
    tab = Column(
        String(30),
        nullable=False,
        comment="Dashboard-Tab fuer dieses Layout",
    )
    widgets_config = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Persoenliche Widget-Positionen [{widget_id, x, y, w, h, visible}]",
    )
    is_custom = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True wenn User Layout manuell angepasst hat",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", "tab", name="uq_dashboard_layout_user_tab"),
        Index("ix_dashboard_layout_user_company", "user_id", "company_id"),
    )

    def to_dict(self) -> dict:
        """Konvertiert Layout zu Dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "company_id": str(self.company_id),
            "tab": self.tab,
            "widgets_config": self.widgets_config or [],
            "is_custom": self.is_custom,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# Document Progress Tracker (DHL-Style)
# =============================================================================


class DocumentProgressTracker(Base):
    """
    Dokument-Fortschritts-Tracker im DHL-Tracking-Stil.

    Zeigt Echtzeit-Status fuer jedes Dokument:
    Hochgeladen -> OCR laeuft -> Extraktion -> Validierung -> Fertig
    """
    __tablename__ = "document_progress_trackers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    # Firma
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Aktueller Schritt
    current_step = Column(
        String(100),
        nullable=False,
        default="hochgeladen",
    )

    # Abgeschlossene Schritte mit Zeitstempeln (JSON-Array)
    steps_completed = Column(
        CrossDBJSON,
        default=list,
        comment="[{name, status, started_at, completed_at, metadata}]",
    )

    # Fortschritt
    total_steps = Column(Integer, nullable=False, default=5)
    progress_percent = Column(Float, nullable=False, default=0.0)

    # Geschaetzte Fertigstellung
    estimated_completion = Column(DateTime(timezone=True), nullable=True)

    # Fehlernachricht (falls vorhanden)
    error_message = Column(Text, nullable=True)

    # Zeitstempel
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    document = relationship("Document", backref="progress_tracker")
    company = relationship("Company", backref="document_progress_trackers")

    __table_args__ = (
        Index("ix_doc_progress_company_step", "company_id", "current_step"),
        Index("ix_doc_progress_started_at", "started_at"),
    )

    def to_dict(self) -> dict:
        """Konvertiert Progress-Tracker zu Dictionary."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "company_id": str(self.company_id),
            "current_step": self.current_step,
            "steps_completed": self.steps_completed or [],
            "total_steps": self.total_steps,
            "progress_percent": self.progress_percent,
            "estimated_completion": (
                self.estimated_completion.isoformat()
                if self.estimated_completion else None
            ),
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# Batch Progress Tracker
# =============================================================================


class BatchProgressTracker(Base):
    """
    Fortschrittsanzeige fuer Stapelverarbeitungen.

    Trackt Gesamtfortschritt eines Batches mit:
    - Anzahl verarbeiteter/fehlgeschlagener Dokumente
    - Geschaetzte Restzeit
    - Name des aktuellen Dokuments
    """
    __tablename__ = "batch_progress_trackers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Batch-Identifikation
    batch_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
        comment="Batch-ID (aus ProcessingJob oder Celery Task)",
    )

    # Firma
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Fortschrittszaehler
    total_documents = Column(Integer, nullable=False, default=0)
    processed = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)

    # Aktuelles Dokument
    current_document_name = Column(String(500), nullable=True)

    # Berechneter Fortschritt
    progress_percent = Column(Float, nullable=False, default=0.0)

    # Zeitschaetzung
    estimated_remaining_seconds = Column(Integer, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_batch_progress_company", "company_id"),
    )

    def to_dict(self) -> dict:
        """Konvertiert Batch-Tracker zu Dictionary."""
        return {
            "id": str(self.id),
            "batch_id": str(self.batch_id),
            "company_id": str(self.company_id),
            "total_documents": self.total_documents,
            "processed": self.processed,
            "failed": self.failed,
            "current_document_name": self.current_document_name,
            "progress_percent": self.progress_percent,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
