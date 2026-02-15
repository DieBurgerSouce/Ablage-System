# -*- coding: utf-8 -*-
"""
Ad-Hoc Report database models for Ablage-System.

Self-Service Reporting: Daten frei kombinieren, filtern,
gruppieren und exportieren - ohne IT-Hilfe.

- Report-Definitionen (Spalten, Filter, Gruppierung, Aggregation)
- Report-Ausfuehrungen mit Metriken
- Report-Sharing zwischen Nutzern
- Geplante Report-Ausfuehrungen (Email-Versand)

Feinpoliert und durchdacht - Enterprise-grade Ad-Hoc Reporting.
"""

import uuid
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# Enums
# =============================================================================


class DataSourceType(str, Enum):
    """Verfuegbare Datenquellen fuer Ad-Hoc Reports."""
    INVOICES = "invoices"            # Rechnungen
    DOCUMENTS = "documents"          # Dokumente
    SUPPLIERS = "suppliers"          # Lieferanten
    CUSTOMERS = "customers"          # Kunden
    TRANSACTIONS = "transactions"    # Banktransaktionen
    APPROVALS = "approvals"          # Genehmigungen
    WORKFLOWS = "workflows"          # Workflow-Ausfuehrungen


class AggregationType(str, Enum):
    """Verfuegbare Aggregationstypen."""
    SUM = "sum"
    COUNT = "count"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    GROUP_BY = "group_by"


class AdHocExportFormat(str, Enum):
    """Unterstuetzte Export-Formate."""
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"


class ReportScheduleFrequency(str, Enum):
    """Frequenz fuer geplante Reports."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


# =============================================================================
# Models
# =============================================================================


class AdHocReport(Base):
    """
    Ad-Hoc Report Definition.

    Speichert die vollstaendige Report-Konfiguration:
    Datenquellen, Spalten, Filter, Gruppierung, Aggregation und Chart-Config.
    """
    __tablename__ = "ad_hoc_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Besitzer und Mandant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Report-Identifikation
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)

    # Report-Definition (JSON-Konfiguration)
    data_sources = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Liste der Datenquellen mit Join-Konfiguration",
    )
    columns = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Spalten: [{source, field, alias, visible, sort_order, sort_direction}]",
    )
    filters = Column(
        CrossDBJSON,
        default=list,
        comment="Filter: [{field, operator, value, logic}]",
    )
    grouping = Column(
        CrossDBJSON,
        default=list,
        comment="Gruppierung: [{field, aggregation}]",
    )
    aggregations = Column(
        CrossDBJSON,
        default=list,
        comment="Aggregationen: [{field, type, alias}]",
    )
    chart_config = Column(
        CrossDBJSON,
        nullable=True,
        comment="Chart: {type, x_field, y_field, ...}",
    )

    # Sichtbarkeit und Templates
    is_public = Column(Boolean, default=False, nullable=False)
    is_template = Column(Boolean, default=False, nullable=False)

    # Nutzungsstatistiken
    execution_count = Column(Integer, default=0, nullable=False)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="ad_hoc_reports")
    creator = relationship(
        "User",
        foreign_keys=[created_by],
        backref="created_ad_hoc_reports",
    )
    executions = relationship(
        "AdHocReportExecution",
        back_populates="report",
        cascade="all, delete-orphan",
    )
    shares = relationship(
        "AdHocReportShare",
        back_populates="report",
        cascade="all, delete-orphan",
    )
    schedules = relationship(
        "ReportSchedule",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_adhoc_reports_company_created", "company_id", "created_by"),
        Index("ix_adhoc_reports_public", "company_id", "is_public"),
        Index("ix_adhoc_reports_template", "is_template"),
    )

    def to_dict(self) -> dict:
        """Konvertiert Report zu Dictionary fuer API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "created_by": str(self.created_by),
            "name": self.name,
            "description": self.description,
            "data_sources": self.data_sources or [],
            "columns": self.columns or [],
            "filters": self.filters or [],
            "grouping": self.grouping or [],
            "aggregations": self.aggregations or [],
            "chart_config": self.chart_config,
            "is_public": self.is_public,
            "is_template": self.is_template,
            "execution_count": self.execution_count,
            "last_executed_at": (
                self.last_executed_at.isoformat() if self.last_executed_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AdHocReportExecution(Base):
    """
    Report-Ausfuehrungs-Protokoll.

    Zeichnet jede Ausfuehrung eines Ad-Hoc Reports auf:
    Zeitpunkt, Dauer, Ergebnisgroesse, Export-Format.
    """
    __tablename__ = "ad_hoc_report_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ad_hoc_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    executed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Ergebnis-Metriken
    row_count = Column(Integer, default=0, nullable=False)
    execution_time_ms = Column(Integer, default=0, nullable=False)

    # Export
    export_format = Column(String(20), nullable=True)
    export_path = Column(String(500), nullable=True)

    # Laufzeit-Parameter (Ueberschreibungen)
    parameters = Column(CrossDBJSON, nullable=True)

    # Fehler
    error_message = Column(Text, nullable=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    report = relationship("AdHocReport", back_populates="executions")
    executor = relationship(
        "User",
        foreign_keys=[executed_by],
    )

    __table_args__ = (
        Index("ix_adhoc_exec_report_created", "report_id", "created_at"),
        Index("ix_adhoc_exec_company", "company_id"),
    )


class AdHocReportShare(Base):
    """
    Report-Freigabe fuer andere Benutzer oder Rollen.

    Ermoeglicht das Teilen von Reports mit bestimmten Nutzern
    oder ganzen Rollen (z.B. 'buchhaltung', 'controlling').
    """
    __tablename__ = "ad_hoc_report_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ad_hoc_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shared_with_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    shared_with_role = Column(String(100), nullable=True)

    can_edit = Column(Boolean, default=False, nullable=False)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    report = relationship("AdHocReport", back_populates="shares")
    shared_user = relationship(
        "User",
        foreign_keys=[shared_with_user_id],
    )

    __table_args__ = (
        Index("ix_adhoc_share_report", "report_id"),
        Index("ix_adhoc_share_user", "shared_with_user_id"),
        CheckConstraint(
            "shared_with_user_id IS NOT NULL OR shared_with_role IS NOT NULL",
            name="ck_adhoc_share_target",
        ),
    )


class ReportSchedule(Base):
    """
    Geplanter Report-Versand.

    Konfiguriert automatische Report-Ausfuehrung und E-Mail-Versand
    nach festgelegtem Zeitplan.
    """
    __tablename__ = "ad_hoc_report_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ad_hoc_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitplan-Konfiguration
    frequency = Column(
        String(20),
        nullable=False,
        comment="daily, weekly, monthly, quarterly",
    )
    day_of_week = Column(
        Integer,
        nullable=True,
        comment="0=Montag fuer WEEKLY",
    )
    day_of_month = Column(
        Integer,
        nullable=True,
        comment="1-28 fuer MONTHLY/QUARTERLY",
    )
    time_of_day = Column(
        String(5),
        nullable=False,
        default="08:00",
        comment="Format HH:MM",
    )

    # Export-Einstellungen
    export_format = Column(
        String(20),
        nullable=False,
        default=AdHocExportFormat.EXCEL.value,
    )
    recipients = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Liste von E-Mail-Adressen",
    )

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=False)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    report = relationship("AdHocReport", back_populates="schedules")
    company = relationship("Company")

    __table_args__ = (
        Index("ix_adhoc_schedule_active", "is_active", "next_run_at"),
        Index("ix_adhoc_schedule_report", "report_id"),
        CheckConstraint(
            "frequency IN ('daily', 'weekly', 'monthly', 'quarterly')",
            name="ck_adhoc_schedule_frequency",
        ),
        CheckConstraint(
            "day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)",
            name="ck_adhoc_schedule_day_of_week",
        ),
        CheckConstraint(
            "day_of_month IS NULL OR (day_of_month >= 1 AND day_of_month <= 28)",
            name="ck_adhoc_schedule_day_of_month",
        ),
    )
