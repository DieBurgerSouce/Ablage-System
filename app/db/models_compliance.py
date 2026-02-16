# -*- coding: utf-8 -*-
"""
GoBD Compliance Check Models für Ablage-System (Vision 2026).

Compliance-Tracking mit:
- GoBDComplianceCheck: Prüfungen nach GoBD-Kriterien
- GoBDComplianceHistory: Prüfverlauf (Audit-Trail)
- GoBDComplianceReport: Export-faehige Berichte

Erweitert bestehende GoBD-Infrastruktur (DocumentArchive, DocumentAccessLog).

Phase 1 der Vision 2026 Feature-Roadmap (Q1-Q2 2026).
"""

from datetime import datetime, date
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    Date,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class GoBDCheckType(str, Enum):
    """GoBD-Prüfungstypen nach deutschem Recht.

    Basierend auf den GoBD-Grundsätzen:
    - Nachvollziehbarkeit
    - Nachprüfbarkeit
    - Unveränderbarkeit
    - Vollständigkeit
    - Ordnung
    - Zeitgerechte Buchung
    - Aufbewahrung
    - Maschinelle Auswertbarkeit
    """
    NACHVOLLZIEHBARKEIT = "nachvollziehbarkeit"      # Audit-Trail vorhanden
    NACHPRUEFBARKEIT = "nachprüfbarkeit"            # Daten überprüfbar
    UNVERAENDERBARKEIT = "unveränderbarkeit"       # Keine Manipulation
    VOLLSTAENDIGKEIT = "vollständigkeit"           # Keine Lücken
    ORDNUNG = "ordnung"                             # Systematische Ablage
    ZEITGERECHTE_BUCHUNG = "zeitgerechte_buchung"   # Fristgerecht
    AUFBEWAHRUNG = "aufbewahrung"                   # 10 Jahre
    MASCHINELLE_AUSWERTBARKEIT = "maschinelle_auswertbarkeit"  # Export möglich
    VERFAHRENSDOKUMENTATION = "verfahrensdokumentation"       # Doku aktuell
    DATENSICHERUNG = "datensicherung"               # Backup vorhanden
    ZUGANGSKONTROLLE = "zugangskontrolle"           # Berechtigungen


class ComplianceStatus(str, Enum):
    """Status einer Compliance-Prüfung."""
    PENDING = "pending"             # Ausstehend
    RUNNING = "running"             # Läuft
    PASSED = "passed"               # Bestanden
    FAILED = "failed"               # Nicht bestanden
    WARNING = "warning"             # Warnung (teilweise bestanden)
    NOT_APPLICABLE = "not_applicable"  # Nicht anwendbar


class ComplianceReportType(str, Enum):
    """Typ des Compliance-Berichts."""
    FULL = "full"           # Vollständiger Bericht
    SUMMARY = "summary"     # Zusammenfassung
    AUDIT = "audit"         # Für Steuerprüfer
    QUARTERLY = "quarterly" # Quartalsweise
    ANNUAL = "annual"       # Jährlich
    CUSTOM = "custom"       # Benutzerdefiniert


# ============================================================================
# GoBD Compliance Check Model
# ============================================================================


class GoBDComplianceCheck(Base):
    """GoBD-Compliance-Prüfung.

    Trackt den Compliance-Status für jedes GoBD-Kriterium:
    - Automatische Prüfungen nach Zeitplan
    - Manuelle Prüfungen durch Benutzer
    - Event-basierte Prüfungen (z.B. nach Änderungen)

    Dashboard-Features:
    - Ampel-Anzeige pro Check (Gruen/Gelb/Rot)
    - Trend über Zeit
    - Export für Steuerberater/Prüfer
    - Automatische Remediation-Vorschläge
    """
    __tablename__ = "gobd_compliance_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Check Type
    check_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ComplianceStatus.PENDING.value
    )

    # Timing
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_check_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Results
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-100
    issues_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(CrossDBJSON, default=dict)
    affected_documents: Mapped[List[str]] = mapped_column(CrossDBJSON, default=list)

    # Remediation
    remediation_steps: Mapped[List[str]] = mapped_column(CrossDBJSON, default=list)
    auto_remediated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remediation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Execution
    triggered_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    executed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    execution_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", backref="gobd_compliance_checks")
    executed_by = relationship("User")
    history = relationship(
        "GoBDComplianceHistory",
        back_populates="compliance_check",
        cascade="all, delete-orphan",
        order_by="desc(GoBDComplianceHistory.checked_at)"
    )

    __table_args__ = (
        Index("ix_gobd_checks_company_id", "company_id"),
        Index("ix_gobd_checks_type", "check_type"),
        Index("ix_gobd_checks_status", "status"),
        Index("ix_gobd_checks_company_type", "company_id", "check_type"),
        Index("ix_gobd_checks_next_check", "next_check_at"),
        Index("ix_gobd_checks_last_checked", "last_checked_at"),
    )

    @property
    def is_passed(self) -> bool:
        """Check if compliance check passed."""
        return self.status == ComplianceStatus.PASSED.value

    @property
    def is_critical(self) -> bool:
        """Check if compliance check failed critically."""
        return self.status == ComplianceStatus.FAILED.value

    @property
    def needs_attention(self) -> bool:
        """Check if compliance needs attention (warning or failed)."""
        return self.status in [
            ComplianceStatus.FAILED.value,
            ComplianceStatus.WARNING.value
        ]

    @property
    def status_color(self) -> str:
        """Get status color for UI."""
        if self.status == ComplianceStatus.PASSED.value:
            return "green"
        elif self.status == ComplianceStatus.WARNING.value:
            return "yellow"
        elif self.status == ComplianceStatus.FAILED.value:
            return "red"
        elif self.status == ComplianceStatus.NOT_APPLICABLE.value:
            return "gray"
        return "blue"  # pending/running

    def get_check_description(self) -> str:
        """Get German description for check type."""
        descriptions = {
            GoBDCheckType.NACHVOLLZIEHBARKEIT.value: "Audit-Trail Prüfung",
            GoBDCheckType.NACHPRUEFBARKEIT.value: "Datenintegrität",
            GoBDCheckType.UNVERAENDERBARKEIT.value: "Hash-Verifikation",
            GoBDCheckType.VOLLSTAENDIGKEIT.value: "Lückenlose Belegnummern",
            GoBDCheckType.ORDNUNG.value: "Systematische Ablage",
            GoBDCheckType.ZEITGERECHTE_BUCHUNG.value: "Fristgerechte Erfassung",
            GoBDCheckType.AUFBEWAHRUNG.value: "Aufbewahrungsfristen",
            GoBDCheckType.MASCHINELLE_AUSWERTBARKEIT.value: "Export-Fähigkeit",
            GoBDCheckType.VERFAHRENSDOKUMENTATION.value: "Verfahrensdoku aktuell",
            GoBDCheckType.DATENSICHERUNG.value: "Backup-Prüfung",
            GoBDCheckType.ZUGANGSKONTROLLE.value: "Berechtigungen",
        }
        return descriptions.get(self.check_type, self.check_type)

    def __repr__(self) -> str:
        return f"<GoBDComplianceCheck {self.check_type} status={self.status}>"


# ============================================================================
# GoBD Compliance History Model
# ============================================================================


class GoBDComplianceHistory(Base):
    """Historie von Compliance-Prüfungen - Immutables Audit-Log.

    Speichert jeden Prüfungslauf für:
    - Trend-Analyse über Zeit
    - Nachweis gegenüber Prüfern
    - Compliance-Reporting
    """
    __tablename__ = "gobd_compliance_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Reference to check
    compliance_check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gobd_compliance_checks.id", ondelete="CASCADE"),
        nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Snapshot of check result
    check_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    issues_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(CrossDBJSON, default=dict)

    # Execution
    triggered_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    executed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Immutable timestamp
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    compliance_check = relationship("GoBDComplianceCheck", back_populates="history")
    company = relationship("Company")
    executed_by = relationship("User")

    __table_args__ = (
        Index("ix_gobd_history_check_id", "compliance_check_id"),
        Index("ix_gobd_history_company_id", "company_id"),
        Index("ix_gobd_history_checked_at", "checked_at"),
        Index("ix_gobd_history_company_type", "company_id", "check_type"),
    )

    def __repr__(self) -> str:
        return f"<GoBDComplianceHistory {self.check_type} at {self.checked_at}>"


# ============================================================================
# GoBD Compliance Report Model
# ============================================================================


class GoBDComplianceReport(Base):
    """Compliance-Bericht für Export an Steuerberater/Prüfer.

    Generiert auf Anfrage oder automatisch (Quartal/Jahr).
    """
    __tablename__ = "gobd_compliance_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Report Details
    report_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ComplianceReportType.FULL.value
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Period
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Content
    summary: Mapped[dict] = mapped_column(CrossDBJSON, default=dict)
    check_results: Mapped[List[dict]] = mapped_column(CrossDBJSON, default=list)
    recommendations: Mapped[List[str]] = mapped_column(CrossDBJSON, default=list)

    # Overall Score
    overall_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overall_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")

    # Export
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_format: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Generated
    generated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Access (for auditors)
    is_exported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exported_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    company = relationship("Company", backref="gobd_compliance_reports")
    generated_by = relationship("User")

    __table_args__ = (
        Index("ix_gobd_reports_company_id", "company_id"),
        Index("ix_gobd_reports_generated_at", "generated_at"),
        Index("ix_gobd_reports_type", "report_type"),
    )

    @property
    def is_passing(self) -> bool:
        """Check if overall compliance is passing."""
        return self.overall_status in ["passed", "warning"]

    def __repr__(self) -> str:
        return f"<GoBDComplianceReport {self.report_type} score={self.overall_score}>"
