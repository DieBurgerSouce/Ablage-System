"""Report Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Text, Float, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import desc
from app.db.models_base import Base, CrossDBJSON


class ReportTemplate(Base):
    """Report-Template Definition.

    Speichert die Konfiguration eines benutzerdefinierten Reports.
    """
    __tablename__ = "report_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Basis-Informationen
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Report-Typ und Datenquelle
    report_type = Column(String(50), nullable=False, index=True)  # document|finance|ocr|custom
    data_source = Column(String(50), nullable=False)  # documents|invoices|entities|ocr_results
    default_format = Column(String(20), nullable=False, default="excel")  # pdf|excel|csv|json

    # Sichtbarkeit
    is_public = Column(Boolean, nullable=False, default=False, index=True)

    # Zeitplan-Konfiguration
    is_scheduled = Column(Boolean, nullable=False, default=False, index=True)
    schedule_config = Column(CrossDBJSON, nullable=True)  # {cron, timezone, recipients}

    # Layout-Konfiguration
    layout_config = Column(CrossDBJSON, nullable=True)  # {orientation, margins, header, footer}

    # Sortierung und Gruppierung
    sort_config = Column(CrossDBJSON, nullable=True)  # [{field, direction}]
    group_by_config = Column(CrossDBJSON, nullable=True)  # [field_paths]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="report_templates")
    company = relationship("Company", backref="report_templates")
    columns = relationship("ReportColumn", back_populates="template", cascade="all, delete-orphan", order_by="ReportColumn.sort_order")
    filters = relationship("ReportFilter", back_populates="template", cascade="all, delete-orphan", order_by="ReportFilter.sort_order")
    charts = relationship("ReportChart", back_populates="template", cascade="all, delete-orphan", order_by="ReportChart.sort_order")
    executions = relationship("ReportExecution", back_populates="template", cascade="all, delete-orphan", order_by="desc(ReportExecution.created_at)")
    shares = relationship("ReportShare", back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "Report-Template Definitionen für Report Builder"}
    )

    def __repr__(self) -> str:
        return f"<ReportTemplate '{self.name}' type={self.report_type}>"


class ReportColumn(Base):
    """Spalten-Konfiguration für Report-Templates.

    Definiert welche Felder im Report angezeigt werden und wie.
    """
    __tablename__ = "report_columns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)

    # Feld-Definition
    field_path = Column(String(255), nullable=False)  # z.B. "extracted_data.invoice_number"
    display_name = Column(String(255), nullable=False)  # z.B. "Rechnungsnummer"
    data_type = Column(String(50), nullable=False)  # string|number|date|currency|boolean

    # Formatierung
    format_pattern = Column(String(100), nullable=True)  # z.B. "#,##0.00 EUR"
    width = Column(Integer, nullable=True)  # Spaltenbreite

    # Reihenfolge und Sichtbarkeit
    sort_order = Column(Integer, nullable=False, default=0)
    is_visible = Column(Boolean, nullable=False, default=True)

    # Aggregation
    aggregation = Column(String(20), nullable=True)  # none|sum|avg|count|min|max

    # Bedingte Formatierung
    conditional_format = Column(CrossDBJSON, nullable=True)  # [{condition, style}]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="columns")

    __table_args__ = (
        Index("ix_report_columns_sort_order", "template_id", "sort_order"),
        {"comment": "Spalten-Konfiguration für Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportColumn '{self.display_name}' path={self.field_path}>"


class ReportFilter(Base):
    """Filter-Bedingungen für Report-Templates.

    Definiert Filterbedingungen die auf die Daten angewendet werden.
    """
    __tablename__ = "report_filters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)

    # Filter-Definition
    field_path = Column(String(255), nullable=False)  # z.B. "status"
    operator = Column(String(50), nullable=False)  # eq|ne|gt|lt|gte|lte|contains|in|between|is_null
    value = Column(CrossDBJSON, nullable=True)  # Wert(e) je nach Operator

    # Logische Verknüpfung
    logic_operator = Column(String(10), nullable=False, default="AND")  # AND|OR
    group_id = Column(Integer, nullable=True)  # Für verschachtelte Gruppen

    # Reihenfolge
    sort_order = Column(Integer, nullable=False, default=0)

    # Dynamische Werte
    is_dynamic = Column(Boolean, nullable=False, default=False)
    dynamic_source = Column(String(100), nullable=True)  # z.B. "current_user", "today", "last_30_days"

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="filters")

    __table_args__ = (
        {"comment": "Filter-Bedingungen für Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportFilter {self.field_path} {self.operator} {self.value}>"


class ReportChart(Base):
    """Chart-Konfiguration für Report-Templates.

    Definiert Visualisierungen die im Report angezeigt werden.
    """
    __tablename__ = "report_charts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)

    # Chart-Typ
    chart_type = Column(String(50), nullable=False)  # bar|line|pie|area|scatter
    title = Column(String(255), nullable=True)

    # Daten-Mapping
    x_axis_field = Column(String(255), nullable=True)  # Kategorie/X-Achse
    y_axis_fields = Column(CrossDBJSON, nullable=False)  # Liste von Feldern für Y-Achse
    group_by_field = Column(String(255), nullable=True)  # Optional: Gruppierung

    # Styling
    colors = Column(CrossDBJSON, nullable=True)  # Benutzerdefinierte Farben
    show_legend = Column(Boolean, nullable=False, default=True)
    show_labels = Column(Boolean, nullable=False, default=False)

    # Position
    position = Column(String(20), nullable=False, default="bottom")  # top|bottom|separate_sheet
    width_percent = Column(Integer, nullable=False, default=100)
    height_px = Column(Integer, nullable=False, default=300)

    # Reihenfolge
    sort_order = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="charts")

    __table_args__ = (
        {"comment": "Chart-Konfiguration für Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportChart '{self.title}' type={self.chart_type}>"


class ReportExecution(Base):
    """Ausführungs-Historie für Report-Templates.

    Speichert wann ein Report ausgeführt wurde und das Ergebnis.
    """
    __tablename__ = "report_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    executed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Ausführung
    status = Column(String(50), nullable=False, default="pending", index=True)  # pending|running|completed|failed
    format = Column(String(20), nullable=False)  # pdf|excel|csv|json
    trigger_type = Column(String(50), nullable=False)  # manual|scheduled|api

    # Ergebnis
    row_count = Column(Integer, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    file_path = Column(String(500), nullable=True)  # MinIO Pfad
    download_url = Column(String(1000), nullable=True)  # Signierte URL
    download_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Fehler-Details
    error_message = Column(Text, nullable=True)
    error_details = Column(CrossDBJSON, nullable=True)

    # Filter-Snapshot
    filter_snapshot = Column(CrossDBJSON, nullable=True)

    # Performance-Metriken
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    template = relationship("ReportTemplate", back_populates="executions")
    executed_by = relationship("User", backref="report_executions")

    __table_args__ = (
        {"comment": "Ausführungs-Historie für Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportExecution status={self.status} rows={self.row_count}>"


class ReportShare(Base):
    """Freigaben für Report-Templates.

    Ermöglicht das Teilen von Reports mit anderen Benutzern.
    """
    __tablename__ = "report_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_with_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    shared_with_group_id = Column(UUID(as_uuid=True), nullable=True)  # Falls Gruppen-Support existiert

    # Berechtigungen
    can_view = Column(Boolean, nullable=False, default=True)
    can_execute = Column(Boolean, nullable=False, default=True)
    can_edit = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)

    # Wer hat geteilt
    shared_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="shares")
    shared_with_user = relationship("User", foreign_keys=[shared_with_user_id], backref="shared_reports")
    shared_by = relationship("User", foreign_keys=[shared_by_id], backref="reports_shared_by_me")

    __table_args__ = (
        Index("uq_report_shares_template_user", "template_id", "shared_with_user_id", unique=True),
        {"comment": "Freigaben für Report-Templates"}
    )
