# -*- coding: utf-8 -*-
"""Morning Briefing Service - Tägliches Cockpit-Briefing.

Generiert strukturierte Tages-Briefings für das Morning Briefing Cockpit:
- Finanzielle Lage (Skonto-Fristen, Cashflow, offene Rechnungen)
- Compliance-Status (GoBD, Archivierungspflichten)
- Workflow-Übersicht (OCR-Queue, unbearbeitete Dokumente)
- Datenqualität (fehlende Felder, Duplikate)

Das Briefing wird einmal täglich generiert und gecacht.
Stale-Briefings (älter als CACHE_TTL_HOURS) werden automatisch neu generiert.

Feinpoliert und durchdacht - Enterprise Morning Intelligence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import (
    Document,
    InvoiceTracking,
    ProcessingStatus,
)
from app.services.banking.skonto_service import SkontoService
from app.services.data_quality_service import DataQualityService
from app.services.gobd_compliance_service import GoBDComplianceService

logger = structlog.get_logger(__name__)

# Briefing-Konfiguration
CACHE_TTL_HOURS: int = 4  # Briefing ist 4 Stunden gültig
SKONTO_WARN_DAYS: int = 3  # Warnung bei Skonto-Ablauf in <= 3 Tagen
INVOICE_OVERDUE_WARN_DAYS: int = 14  # Warnung bei Rechnungen älter als 14 Tage
OCR_QUEUE_WARN_COUNT: int = 20  # Warnung ab 20 Dokumenten in der Queue
MAX_ALERTS_PER_SECTION: int = 10  # Maximale Alerts pro Sektion


# =============================================================================
# Enums und Datenklassen
# =============================================================================


class AlertSeverity(str, Enum):
    """Schweregrad eines Briefing-Alerts."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class BriefingSection(str, Enum):
    """Sektionen des Morning Briefings."""
    FINANCIAL = "financial"
    COMPLIANCE = "compliance"
    WORKFLOW = "workflow"
    DATA_QUALITY = "data_quality"


@dataclass
class BriefingAlert:
    """Einzelner Alert im Morning Briefing."""
    alert_id: str
    alert_type: str
    severity: AlertSeverity
    title: str
    description: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert den Alert als Dictionary."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "action_url": self.action_url,
            "action_label": self.action_label,
            "metadata": self.metadata,
        }


@dataclass
class BriefingSectionResult:
    """Ergebnis einer Briefing-Sektion."""
    section: BriefingSection
    title: str
    alerts: List[BriefingAlert] = field(default_factory=list)
    summary: str = ""
    score: Optional[float] = None  # 0-100: Gesundheitsscore der Sektion

    @property
    def critical_count(self) -> int:
        """Anzahl kritischer Alerts."""
        return sum(1 for a in self.alerts if a.severity == AlertSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        """Anzahl Warnungen."""
        return sum(1 for a in self.alerts if a.severity == AlertSeverity.WARNING)

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert die Sektion als Dictionary."""
        return {
            "section": self.section.value,
            "title": self.title,
            "summary": self.summary,
            "score": self.score,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "alerts": [a.to_dict() for a in self.alerts],
        }


@dataclass
class MorningBriefingResult:
    """Vollständiges Morning Briefing Ergebnis."""
    company_id: UUID
    briefing_date: date
    generated_at: datetime
    sections: List[BriefingSectionResult] = field(default_factory=list)
    overall_score: float = 100.0  # 0-100: Gesamtgesundheitsscore

    @property
    def total_critical(self) -> int:
        """Gesamt-kritische Alerts."""
        return sum(s.critical_count for s in self.sections)

    @property
    def total_warnings(self) -> int:
        """Gesamt-Warnungen."""
        return sum(s.warning_count for s in self.sections)

    @property
    def has_critical_issues(self) -> bool:
        """Gibt an, ob kritische Probleme vorliegen."""
        return self.total_critical > 0

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert das komplette Briefing als Dictionary für JSONB-Speicherung."""
        return {
            "company_id": str(self.company_id),
            "briefing_date": self.briefing_date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "overall_score": self.overall_score,
            "total_critical": self.total_critical,
            "total_warnings": self.total_warnings,
            "has_critical_issues": self.has_critical_issues,
            "sections": [s.to_dict() for s in self.sections],
        }


# =============================================================================
# Morning Briefing Service
# =============================================================================


class MorningBriefingService:
    """Service für das tägliche Morning Briefing Cockpit.

    Aggregiert Daten aus verschiedenen Services und erstellt ein
    priorisiertes, strukturiertes Tages-Briefing für Unternehmen.

    Verwendete Services:
    - SkontoService: Fristenüberwachung
    - GoBDComplianceService: Archivierungsstatus
    - DataQualityService: Datenqualität
    - Direkte DB-Abfragen: OCR-Queue, offene Rechnungen
    """

    def __init__(self) -> None:
        """Initialisiert den Morning Briefing Service."""
        self._skonto_service = SkontoService()
        self._gobd_service = GoBDComplianceService()

    async def generate_briefing(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> MorningBriefingResult:
        """Generiert das tägliche Morning Briefing für eine Firma.

        Sammelt Daten aus allen relevanten Bereichen und erstellt
        ein priorisiertes, strukturiertes Briefing.

        Args:
            db: Async-Datenbank-Session
            company_id: Firmen-ID für Mandantenisolierung

        Returns:
            MorningBriefingResult mit allen Sektionen und Alerts

        Raises:
            Exception: Bei schwerwiegenden Datenbankfehlern
        """
        today = date.today()
        now = utc_now()

        logger.info(
            "morning_briefing_generierung_gestartet",
            company_id=str(company_id),
            briefing_date=today.isoformat(),
        )

        # Alle Sektionen parallel sammeln (einzeln mit Fehlerbehandlung)
        sections: List[BriefingSectionResult] = []

        financial_section = await self._collect_financial_section(db, company_id, today)
        sections.append(financial_section)

        compliance_section = await self._collect_compliance_section(db, company_id, today)
        sections.append(compliance_section)

        workflow_section = await self._collect_workflow_section(db, company_id)
        sections.append(workflow_section)

        data_quality_section = await self._collect_data_quality_section(db, company_id)
        sections.append(data_quality_section)

        # Gesamtscore berechnen (gewichteter Durchschnitt der Sektions-Scores)
        overall_score = self._calculate_overall_score(sections)

        briefing = MorningBriefingResult(
            company_id=company_id,
            briefing_date=today,
            generated_at=now,
            sections=sections,
            overall_score=overall_score,
        )

        logger.info(
            "morning_briefing_generiert",
            company_id=str(company_id),
            overall_score=overall_score,
            total_critical=briefing.total_critical,
            total_warnings=briefing.total_warnings,
        )

        return briefing

    # =========================================================================
    # Sektion: Finanzen
    # =========================================================================

    async def _collect_financial_section(
        self,
        db: AsyncSession,
        company_id: UUID,
        today: date,
    ) -> BriefingSectionResult:
        """Sammelt finanzielle Alerts für das Briefing.

        Prüft:
        - Ablaufende Skonto-Fristen
        - Überfällige Rechnungen
        - Cashflow-Warnungen

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            today: Heutiges Datum

        Returns:
            BriefingSectionResult mit finanziellen Alerts
        """
        section = BriefingSectionResult(
            section=BriefingSection.FINANCIAL,
            title="Finanzielle Lage",
        )

        try:
            # Skonto-Fristen prüfen
            skonto_alerts = await self._check_skonto_deadlines(db, company_id, today)
            section.alerts.extend(skonto_alerts)

            # Überfällige Rechnungen prüfen
            overdue_alerts = await self._check_overdue_invoices(db, company_id, today)
            section.alerts.extend(overdue_alerts)

            # Alerts nach Priorität sortieren (kritisch zuerst)
            section.alerts = self._sort_alerts_by_priority(section.alerts)
            section.alerts = section.alerts[:MAX_ALERTS_PER_SECTION]

            # Zusammenfassung generieren
            section.summary = self._generate_financial_summary(section.alerts)
            section.score = self._calculate_section_score(section.alerts)

        except Exception as exc:
            logger.error(
                "morning_briefing_finanz_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )
            section.summary = "Finanzdaten konnten nicht geladen werden."
            section.score = None

        return section

    async def _check_skonto_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        today: date,
    ) -> List[BriefingAlert]:
        """Prüft ablaufende Skonto-Fristen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            today: Heutiges Datum

        Returns:
            Liste von Briefing-Alerts für Skonto-Fristen
        """
        alerts: List[BriefingAlert] = []

        try:
            # Skonto-Alerts vom SkontoService laden
            skonto_alert_list = await self._skonto_service.get_upcoming_skonto_deadlines(
                db=db,
                company_id=company_id,
                days_ahead=SKONTO_WARN_DAYS,
            )

            for skonto_alert in skonto_alert_list:
                # Nur Alerts für die nächsten SKONTO_WARN_DAYS Tage
                if not hasattr(skonto_alert, "days_remaining"):
                    continue
                if skonto_alert.days_remaining is None:
                    continue
                if skonto_alert.days_remaining > SKONTO_WARN_DAYS:
                    continue

                if skonto_alert.days_remaining <= 0:
                    severity = AlertSeverity.CRITICAL
                    title = "Skonto-Frist abgelaufen"
                    desc = f"Skonto-Frist für {skonto_alert.days_remaining * -1} Tage überschritten."
                elif skonto_alert.days_remaining <= 1:
                    severity = AlertSeverity.CRITICAL
                    title = "Skonto-Frist läuft heute ab"
                    desc = "Sofort zahlen, um Skonto zu sichern."
                else:
                    severity = AlertSeverity.WARNING
                    title = f"Skonto läuft in {skonto_alert.days_remaining} Tagen ab"
                    desc = f"Skonto-Berechtigung endet in {skonto_alert.days_remaining} Tagen."

                alerts.append(BriefingAlert(
                    alert_id=f"skonto_{uuid.uuid4().hex[:8]}",
                    alert_type="skonto_deadline",
                    severity=severity,
                    title=title,
                    description=desc,
                    action_url="/rechnungen?filter=skonto_pending",
                    action_label="Zur Rechnung",
                    metadata={
                        "days_remaining": skonto_alert.days_remaining,
                    },
                ))

        except Exception as exc:
            logger.warning(
                "morning_briefing_skonto_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )

        return alerts

    async def _check_overdue_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
        today: date,
    ) -> List[BriefingAlert]:
        """Prüft überfällige Rechnungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            today: Heutiges Datum

        Returns:
            Liste von Briefing-Alerts für überfällige Rechnungen
        """
        alerts: List[BriefingAlert] = []

        try:
            cutoff_date = today - timedelta(days=INVOICE_OVERDUE_WARN_DAYS)

            # Überfällige offene Rechnungen zählen
            stmt = (
                select(func.count(InvoiceTracking.id))
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["open", "partial"]),
                        InvoiceTracking.due_date < today,
                    )
                )
            )
            result = await db.execute(stmt)
            total_overdue_count = result.scalar_one_or_none() or 0

            # Kritisch überfällige Rechnungen (> INVOICE_OVERDUE_WARN_DAYS Tage)
            stmt_critical = (
                select(func.count(InvoiceTracking.id))
                .where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["open", "partial"]),
                        InvoiceTracking.due_date < cutoff_date,
                    )
                )
            )
            result_critical = await db.execute(stmt_critical)
            critical_count = result_critical.scalar_one_or_none() or 0

            if critical_count > 0:
                alerts.append(BriefingAlert(
                    alert_id=f"overdue_critical_{uuid.uuid4().hex[:8]}",
                    alert_type="invoice_overdue_critical",
                    severity=AlertSeverity.CRITICAL,
                    title=f"{critical_count} Rechnung(en) stark überfällig",
                    description=(
                        f"{critical_count} Rechnung(en) sind mehr als "
                        f"{INVOICE_OVERDUE_WARN_DAYS} Tage überfällig und erfordern "
                        "sofortige Maßnahmen."
                    ),
                    action_url="/rechnungen?filter=overdue_critical",
                    action_label="Überfällige anzeigen",
                    metadata={"overdue_count": critical_count},
                ))
            elif total_overdue_count > 0:
                alerts.append(BriefingAlert(
                    alert_id=f"overdue_warn_{uuid.uuid4().hex[:8]}",
                    alert_type="invoice_overdue",
                    severity=AlertSeverity.WARNING,
                    title=f"{total_overdue_count} offene Rechnung(en) fällig",
                    description=(
                        f"{total_overdue_count} Rechnung(en) haben das Fälligkeitsdatum "
                        "überschritten und sollten zeitnah bearbeitet werden."
                    ),
                    action_url="/rechnungen?filter=overdue",
                    action_label="Offene Rechnungen",
                    metadata={"overdue_count": total_overdue_count},
                ))

        except Exception as exc:
            logger.warning(
                "morning_briefing_rechnungen_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )

        return alerts

    # =========================================================================
    # Sektion: Compliance
    # =========================================================================

    async def _collect_compliance_section(
        self,
        db: AsyncSession,
        company_id: UUID,
        today: date,
    ) -> BriefingSectionResult:
        """Sammelt Compliance-Alerts für das Briefing.

        Prüft GoBD-Archivierungsstatus und Aufbewahrungsfristen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            today: Heutiges Datum

        Returns:
            BriefingSectionResult mit Compliance-Alerts
        """
        section = BriefingSectionResult(
            section=BriefingSection.COMPLIANCE,
            title="GoBD & Compliance",
        )

        try:
            # GoBD-Bericht abrufen
            compliance_report = await self._gobd_service.generate_compliance_report(
                db=db,
                company_id=company_id,
                report_date=today,
                include_details=False,
            )

            # Compliance-Score als Sektion-Score verwenden
            compliance_score = compliance_report.get("overall_score", 100.0)
            section.score = float(compliance_score) if compliance_score is not None else None

            # Fehlende Archivierungen
            unarchived_count = compliance_report.get("unarchived_count", 0)
            if isinstance(unarchived_count, int) and unarchived_count > 0:
                severity = AlertSeverity.CRITICAL if unarchived_count > 10 else AlertSeverity.WARNING
                section.alerts.append(BriefingAlert(
                    alert_id=f"gobd_archive_{uuid.uuid4().hex[:8]}",
                    alert_type="gobd_missing_archive",
                    severity=severity,
                    title=f"{unarchived_count} Dokument(e) nicht archiviert",
                    description=(
                        f"{unarchived_count} steuerrelevante Dokument(e) sind noch nicht "
                        "GoBD-konform archiviert. Archivierung ist gesetzlich vorgeschrieben."
                    ),
                    action_url="/dokumente?filter=not_archived",
                    action_label="Jetzt archivieren",
                    metadata={"unarchived_count": unarchived_count},
                ))

            # Aufbewahrungsfristen-Warnungen
            expiring_count = compliance_report.get("expiring_soon_count", 0)
            if isinstance(expiring_count, int) and expiring_count > 0:
                section.alerts.append(BriefingAlert(
                    alert_id=f"gobd_retention_{uuid.uuid4().hex[:8]}",
                    alert_type="gobd_retention_expiring",
                    severity=AlertSeverity.WARNING,
                    title=f"{expiring_count} Aufbewahrungsfrist(en) laufen bald ab",
                    description=(
                        f"{expiring_count} Dokument(e) erreichen bald das Ende ihrer "
                        "gesetzlichen Aufbewahrungspflicht."
                    ),
                    action_url="/compliance/aufbewahrung",
                    action_label="Fristen prüfen",
                    metadata={"expiring_count": expiring_count},
                ))

            # Alerts sortieren
            section.alerts = self._sort_alerts_by_priority(section.alerts)
            section.alerts = section.alerts[:MAX_ALERTS_PER_SECTION]

            # Zusammenfassung
            if section.score is not None and section.score >= 95:
                section.summary = "GoBD-Compliance in gutem Zustand."
            elif not section.alerts:
                section.summary = "Keine offenen Compliance-Probleme."
            else:
                critical_n = section.critical_count
                warn_n = section.warning_count
                parts: List[str] = []
                if critical_n:
                    parts.append(f"{critical_n} kritische Probleme")
                if warn_n:
                    parts.append(f"{warn_n} Warnungen")
                section.summary = "Compliance: " + ", ".join(parts) + " zu bearbeiten."

        except Exception as exc:
            logger.error(
                "morning_briefing_compliance_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )
            section.summary = "Compliance-Daten konnten nicht geladen werden."
            section.score = None

        return section

    # =========================================================================
    # Sektion: Workflow
    # =========================================================================

    async def _collect_workflow_section(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> BriefingSectionResult:
        """Sammelt Workflow-Alerts für das Briefing.

        Prüft OCR-Queue-Status und unbearbeitete Dokumente.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            BriefingSectionResult mit Workflow-Alerts
        """
        section = BriefingSectionResult(
            section=BriefingSection.WORKFLOW,
            title="Workflow & OCR-Queue",
        )

        try:
            # OCR-Queue: Pending und processing Dokumente
            stmt_queue = (
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.status.in_([
                            ProcessingStatus.PENDING.value,
                            ProcessingStatus.QUEUED.value,
                            ProcessingStatus.PROCESSING.value,
                        ]),
                    )
                )
            )
            result_queue = await db.execute(stmt_queue)
            queue_count = result_queue.scalar_one_or_none() or 0

            if queue_count >= OCR_QUEUE_WARN_COUNT:
                severity = (
                    AlertSeverity.CRITICAL
                    if queue_count >= OCR_QUEUE_WARN_COUNT * 3
                    else AlertSeverity.WARNING
                )
                section.alerts.append(BriefingAlert(
                    alert_id=f"ocr_queue_{uuid.uuid4().hex[:8]}",
                    alert_type="ocr_queue_backlog",
                    severity=severity,
                    title=f"{queue_count} Dokument(e) in OCR-Queue",
                    description=(
                        f"{queue_count} Dokument(e) warten auf OCR-Verarbeitung. "
                        "Der Rückstand sollte zeitnah abgebaut werden."
                    ),
                    action_url="/admin/ocr-queue",
                    action_label="Queue anzeigen",
                    metadata={"queue_count": queue_count},
                ))
            elif queue_count > 0:
                section.alerts.append(BriefingAlert(
                    alert_id=f"ocr_queue_info_{uuid.uuid4().hex[:8]}",
                    alert_type="ocr_queue_active",
                    severity=AlertSeverity.INFO,
                    title=f"{queue_count} Dokument(e) in Verarbeitung",
                    description=f"{queue_count} Dokument(e) werden gerade verarbeitet.",
                    action_url="/admin/ocr-queue",
                    action_label="Queue anzeigen",
                    metadata={"queue_count": queue_count},
                ))

            # Fehlgeschlagene Verarbeitungen (letzte 24h)
            yesterday = utc_now() - timedelta(hours=24)
            stmt_failed = (
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.status == ProcessingStatus.FAILED.value,
                        Document.updated_at >= yesterday,
                    )
                )
            )
            result_failed = await db.execute(stmt_failed)
            failed_count = result_failed.scalar_one_or_none() or 0

            if failed_count > 0:
                severity = AlertSeverity.CRITICAL if failed_count > 5 else AlertSeverity.WARNING
                section.alerts.append(BriefingAlert(
                    alert_id=f"ocr_failed_{uuid.uuid4().hex[:8]}",
                    alert_type="ocr_processing_failed",
                    severity=severity,
                    title=f"{failed_count} OCR-Verarbeitung(en) fehlgeschlagen (letzte 24h)",
                    description=(
                        f"{failed_count} Dokument(e) konnten in den letzten 24 Stunden "
                        "nicht verarbeitet werden und erfordern Aufmerksamkeit."
                    ),
                    action_url="/dokumente?filter=failed",
                    action_label="Fehler anzeigen",
                    metadata={"failed_count": failed_count, "timeframe_hours": 24},
                ))

            # Alerts sortieren
            section.alerts = self._sort_alerts_by_priority(section.alerts)
            section.alerts = section.alerts[:MAX_ALERTS_PER_SECTION]

            # Score berechnen
            section.score = self._calculate_section_score(section.alerts)

            # Zusammenfassung
            if not section.alerts or (section.alerts and section.alerts[0].severity == AlertSeverity.INFO):
                section.summary = f"OCR-Queue läuft stabil ({queue_count} Dokument(e) in Verarbeitung)."
            else:
                section.summary = (
                    f"Workflow-Status: {section.critical_count} kritisch, "
                    f"{section.warning_count} Warnungen."
                )

        except Exception as exc:
            logger.error(
                "morning_briefing_workflow_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )
            section.summary = "Workflow-Daten konnten nicht geladen werden."
            section.score = None

        return section

    # =========================================================================
    # Sektion: Datenqualität
    # =========================================================================

    async def _collect_data_quality_section(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> BriefingSectionResult:
        """Sammelt Datenqualitäts-Alerts für das Briefing.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            BriefingSectionResult mit Datenqualitäts-Alerts
        """
        section = BriefingSectionResult(
            section=BriefingSection.DATA_QUALITY,
            title="Datenqualität",
        )

        try:
            # DataQualityService benötigt die db-Session im Konstruktor
            data_quality_service = DataQualityService(db=db)
            quality_report = await data_quality_service.get_quality_report(
                company_id=company_id,
            )

            # Score aus dem Bericht übernehmen
            section.score = quality_report.overall_score

            # Issues als Alerts umwandeln
            for issue in quality_report.issues:
                if issue.count == 0:
                    continue

                # Severity mapping: DataQuality nutzt strings "info/warning/critical"
                try:
                    severity = AlertSeverity(issue.severity)
                except ValueError:
                    severity = AlertSeverity.INFO

                section.alerts.append(BriefingAlert(
                    alert_id=f"dq_{issue.category.value}_{uuid.uuid4().hex[:8]}",
                    alert_type=f"data_quality_{issue.category.value}",
                    severity=severity,
                    title=issue.title,
                    description=f"{issue.description} ({issue.count} betroffene Einträge)",
                    action_url=issue.action_endpoint,
                    action_label=issue.action_label,
                    metadata={
                        "category": issue.category.value,
                        "count": issue.count,
                    },
                ))

            # Alerts sortieren und begrenzen
            section.alerts = self._sort_alerts_by_priority(section.alerts)
            section.alerts = section.alerts[:MAX_ALERTS_PER_SECTION]

            # Zusammenfassung
            if quality_report.overall_score >= 90:
                section.summary = (
                    f"Datenqualität sehr gut (Score: {quality_report.overall_score:.0f}/100)."
                )
            elif quality_report.overall_score >= 70:
                section.summary = (
                    f"Datenqualität gut (Score: {quality_report.overall_score:.0f}/100). "
                    f"Trend: {quality_report.trend}."
                )
            else:
                section.summary = (
                    f"Datenqualität verbesserungswürdig (Score: {quality_report.overall_score:.0f}/100). "
                    f"{len(quality_report.issues)} Problem(e) identifiziert."
                )

        except Exception as exc:
            logger.error(
                "morning_briefing_datenqualitaet_fehler",
                **safe_error_log(exc),
                company_id=str(company_id),
            )
            section.summary = "Datenqualitäts-Daten konnten nicht geladen werden."
            section.score = None

        return section

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def _sort_alerts_by_priority(self, alerts: List[BriefingAlert]) -> List[BriefingAlert]:
        """Sortiert Alerts nach Priorität (kritisch > warnung > info).

        Args:
            alerts: Unsortierte Alert-Liste

        Returns:
            Priorisiert sortierte Alert-Liste
        """
        priority_map: Dict[AlertSeverity, int] = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.WARNING: 1,
            AlertSeverity.INFO: 2,
        }
        return sorted(alerts, key=lambda a: priority_map.get(a.severity, 99))

    def _calculate_section_score(self, alerts: List[BriefingAlert]) -> float:
        """Berechnet den Gesundheitsscore einer Sektion.

        Scoring-Logik:
        - 100 = keine Alerts
        - -20 pro kritischem Alert (min 0)
        - -5 pro Warnung (min 0)

        Args:
            alerts: Liste der Sektion-Alerts

        Returns:
            Score zwischen 0 und 100
        """
        score = 100.0
        for alert in alerts:
            if alert.severity == AlertSeverity.CRITICAL:
                score -= 20.0
            elif alert.severity == AlertSeverity.WARNING:
                score -= 5.0
        return max(0.0, score)

    def _calculate_overall_score(self, sections: List[BriefingSectionResult]) -> float:
        """Berechnet den gewichteten Gesamtscore.

        Gewichtung:
        - Finanzen: 35%
        - Compliance: 30%
        - Workflow: 20%
        - Datenqualität: 15%

        Args:
            sections: Alle Briefing-Sektionen

        Returns:
            Gesamtscore zwischen 0 und 100
        """
        section_weights: Dict[BriefingSection, float] = {
            BriefingSection.FINANCIAL: 0.35,
            BriefingSection.COMPLIANCE: 0.30,
            BriefingSection.WORKFLOW: 0.20,
            BriefingSection.DATA_QUALITY: 0.15,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for section in sections:
            if section.score is None:
                continue
            weight = section_weights.get(section.section, 0.1)
            weighted_sum += section.score * weight
            total_weight += weight

        if total_weight == 0.0:
            return 100.0

        return round(weighted_sum / total_weight, 1)

    def _generate_financial_summary(self, alerts: List[BriefingAlert]) -> str:
        """Generiert eine Textzusammenfassung für die Finanz-Sektion.

        Args:
            alerts: Finanz-Alerts

        Returns:
            Deutsche Zusammenfassung als String
        """
        if not alerts:
            return "Keine dringenden finanziellen Aktionen erforderlich."

        critical_count = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)
        warning_count = sum(1 for a in alerts if a.severity == AlertSeverity.WARNING)

        parts: List[str] = []
        if critical_count:
            parts.append(f"{critical_count} kritische Finanzaktion(en)")
        if warning_count:
            parts.append(f"{warning_count} Finanzwarnung(en)")

        return "Finanzielle Lage: " + ", ".join(parts) + " zu bearbeiten."


# =============================================================================
# Factory
# =============================================================================

_morning_briefing_service: Optional[MorningBriefingService] = None


def get_morning_briefing_service() -> MorningBriefingService:
    """Gibt eine Singleton-Instanz des MorningBriefingService zurück.

    Returns:
        MorningBriefingService-Instanz
    """
    global _morning_briefing_service
    if _morning_briefing_service is None:
        _morning_briefing_service = MorningBriefingService()
    return _morning_briefing_service
