# -*- coding: utf-8 -*-
"""
Ad-Hoc Reporting satellite models.

Separate Modelle für Feature #12: Ad-Hoc Reporting.
Ermöglicht Nutzern, eigene Reports mit beliebigen Datenquellen zu erstellen.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
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
# ENUMS
# =============================================================================


class DataSourceType(str, Enum):
    """Verfügbare Datenquellen für Ad-Hoc Reports."""
    INVOICES = "invoices"
    DOCUMENTS = "documents"
    ENTITIES = "entities"
    TRANSACTIONS = "transactions"
    APPROVALS = "approvals"
    WORKFLOWS = "workflows"
    OCR_RESULTS = "ocr_results"
    CUSTOM_QUERY = "custom_query"


class AggregationType(str, Enum):
    """Aggregationstypen für Spalten."""
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    DISTINCT_COUNT = "distinct_count"


class ExportFormat(str, Enum):
    """Unterstützte Export-Formate."""
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"


class ScheduleFrequency(str, Enum):
    """Frequenz für geplante Reports."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# =============================================================================
# MODELS
# =============================================================================


class AdHocReport(Base):
    """Ad-Hoc Report Definition.

    Speichert die vollständige Konfiguration eines benutzerdefinierten
    Ad-Hoc Reports mit Datenquellen, Spalten, Filtern und Diagrammen.
    """
    __tablename__ = "adhoc_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung für Multi-Company Isolation",
    )
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Datenquellen-Konfiguration
    # Format: [{"source": "invoices", "alias": "inv", "join_on": {...}}]
    data_sources = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Liste der Datenquellen mit Join-Konfiguration",
    )

    # Spalten-Definition
    # Format: [{"name": "invoice_number", "source": "invoices", "alias": "Rechnungsnr.", "aggregation": null}]
    columns = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Spalten-Definitionen mit Name, Quelle, Alias und Aggregation",
    )

    # Filter-Bedingungen
    # Format: [{"column": "status", "operator": "eq", "value": "paid", "logic": "AND"}]
    filters = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Filter-Bedingungen für die Datenabfrage",
    )

    # Gruppierung
    # Format: ["entity_type", "status"]
    group_by = Column(
        CrossDBJSON,
        nullable=True,
        comment="Spalten für GROUP BY",
    )

    # Sortierung
    # Format: [{"column": "total_amount", "direction": "desc"}]
    order_by = Column(
        CrossDBJSON,
        nullable=True,
        comment="Sortierung mit Richtungsangabe",
    )

    # Limit
    limit_rows = Column(
        Integer,
        nullable=True,
        comment="Maximale Anzahl zurückgegebener Zeilen",
    )

    # Chart-Konfiguration
    # Format: {"chart_type": "bar", "x_axis": "entity_type", "y_axis": "total_amount", ...}
    chart_config = Column(
        CrossDBJSON,
        nullable=True,
        comment="Diagramm-Konfiguration (Typ, Achsen, Optionen)",
    )

    # Template / Sharing
    is_template = Column(Boolean, nullable=False, default=False)
    is_shared = Column(Boolean, nullable=False, default=False)
    shared_with_users = Column(
        CrossDBJSON,
        nullable=True,
        comment="Liste der User-IDs, mit denen geteilt wird",
    )

    # Execution-Tracking
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Soft-Delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", backref="adhoc_reports")
    created_by = relationship("User", backref="adhoc_reports", foreign_keys=[created_by_user_id])
    schedules = relationship(
        "ScheduledReport",
        back_populates="report",
        cascade="all, delete-orphan",
    )
    execution_logs = relationship(
        "ReportExecutionLog",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="desc(ReportExecutionLog.created_at)",
    )

    __table_args__ = (
        Index("ix_adhoc_reports_company_user", "company_id", "created_by_user_id"),
        Index("ix_adhoc_reports_is_shared", "company_id", "is_shared"),
        {"comment": "Ad-Hoc Report Definitionen für Feature #12"},
    )

    def __repr__(self) -> str:
        return f"<AdHocReport '{self.name}' id={self.id}>"


class ScheduledReport(Base):
    """Geplanter Report-Versand.

    Ermöglicht das automatische Ausführen und Versenden von
    Ad-Hoc Reports nach Zeitplan.
    """
    __tablename__ = "scheduled_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("adhoc_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Schedule-Konfiguration
    frequency = Column(String(20), nullable=False, comment="daily|weekly|monthly")
    day_of_week = Column(
        Integer,
        nullable=True,
        comment="0=Montag, 6=Sonntag (nur für weekly)",
    )
    day_of_month = Column(
        Integer,
        nullable=True,
        comment="1-28 (nur für monthly)",
    )
    time_of_day = Column(
        String(5),
        nullable=False,
        default="08:00",
        comment="Uhrzeit im Format HH:MM",
    )

    # Export-Konfiguration
    export_format = Column(String(10), nullable=False, default="excel")
    recipients = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Liste der E-Mail-Adressen",
    )

    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)
    next_send_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Audit
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    report = relationship("AdHocReport", back_populates="schedules")
    company = relationship("Company", backref="scheduled_reports")
    created_by = relationship("User", backref="scheduled_reports", foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index("ix_scheduled_reports_active_next", "is_active", "next_send_at"),
        {"comment": "Geplante Report-Ausführungen für Ad-Hoc Reports"},
    )

    def __repr__(self) -> str:
        return f"<ScheduledReport report_id={self.report_id} freq={self.frequency}>"


class ReportExecutionLog(Base):
    """Ausführungs-Protokoll für Ad-Hoc Reports.

    Protokolliert jede Ausführung eines Ad-Hoc Reports mit
    Performance-Metriken und optionalem Dateipfad.
    """
    __tablename__ = "adhoc_report_execution_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("adhoc_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    executed_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="NULL für geplante Ausführungen",
    )

    # Ergebnis
    export_format = Column(String(10), nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    execution_time_ms = Column(Integer, nullable=False, default=0)
    file_path = Column(
        String(500),
        nullable=True,
        comment="Pfad zur exportierten Datei",
    )
    error_message = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    report = relationship("AdHocReport", back_populates="execution_logs")
    executed_by = relationship("User", backref="adhoc_report_executions", foreign_keys=[executed_by_user_id])

    __table_args__ = (
        Index("ix_adhoc_exec_log_report_date", "report_id", "created_at"),
        {"comment": "Ausführungs-Protokoll für Ad-Hoc Reports"},
    )

    def __repr__(self) -> str:
        return f"<ReportExecutionLog report={self.report_id} rows={self.row_count}>"
