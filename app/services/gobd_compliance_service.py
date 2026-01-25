"""GoBD Compliance Report Service.

Service fuer die Generierung von GoBD-Compliance-Berichten:
- Archivierungsstatus
- Aufbewahrungsfristen-Compliance
- Audit-Trail-Vollstaendigkeit
- Integritaetspruefungen
- Zusammenfassender Compliance-Score

GoBD = Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung
       von Buechern, Aufzeichnungen und Unterlagen in elektronischer
       Form sowie zum Datenzugriff

Rechtliche Grundlagen:
- § 147 AO (Aufbewahrungspflicht)
- § 257 HGB (Aufbewahrungsfristen)
- § 14b UStG (Rechnungsaufbewahrung)
"""

import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    DocumentArchive,
    DocumentAccessLog,
    RetentionCategory,
    Company,
)

logger = structlog.get_logger(__name__)


class ComplianceStatus(str, Enum):
    """Status der GoBD-Compliance."""
    COMPLIANT = "compliant"
    WARNING = "warning"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


@dataclass
class ComplianceMetric:
    """Einzelne Compliance-Metrik."""
    name: str
    value: Any
    status: ComplianceStatus
    threshold: Optional[Any] = None
    description: str = ""
    recommendation: Optional[str] = None


class GoBDComplianceService:
    """Service fuer GoBD-Compliance-Berichte und -Pruefungen."""

    # Compliance Thresholds
    MIN_ARCHIVE_RATE = 0.95  # 95% der steuerrelevanten Dokumente archiviert
    MAX_VERIFICATION_AGE_DAYS = 90  # Max. Tage seit letzter Verifikation
    MIN_AUDIT_TRAIL_COVERAGE = 1.0  # 100% Audit-Trail fuer Zugriffe
    MAX_FAILED_VERIFICATIONS = 0  # Keine fehlgeschlagenen Verifikationen

    async def generate_compliance_report(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        report_date: Optional[date] = None,
        include_details: bool = True,
    ) -> Dict[str, Any]:
        """Generiert einen vollstaendigen GoBD-Compliance-Bericht.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            report_date: Stichtag (default: heute)
            include_details: Details einschliessen

        Returns:
            Dict mit Compliance-Bericht

        Raises:
            ValueError: Wenn company_id nicht gefunden
        """
        # Input-Validierung: Company muss existieren
        company = await db.get(Company, company_id)
        if not company:
            logger.warning(
                "gobd_compliance_company_not_found",
                company_id=str(company_id),
            )
            raise ValueError(f"Firma {company_id} nicht gefunden")

        report_date = report_date or date.today()

        # Sammle alle Compliance-Metriken
        archive_metrics = await self._check_archive_compliance(db, company_id)
        retention_metrics = await self._check_retention_compliance(db, company_id, report_date)
        audit_metrics = await self._check_audit_trail_compliance(db, company_id)
        integrity_metrics = await self._check_integrity_compliance(db, company_id)

        # Kombiniere alle Metriken
        all_metrics = archive_metrics + retention_metrics + audit_metrics + integrity_metrics

        # Berechne Gesamt-Score
        overall_score, overall_status = self._calculate_overall_score(all_metrics)

        # Erzeuge Empfehlungen
        recommendations = self._generate_recommendations(all_metrics)

        report = {
            "report_id": str(uuid.uuid4()),
            "company_id": str(company_id),
            "report_date": report_date.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status.value,
            "overall_score": overall_score,
            "score_description": self._get_score_description(overall_score),
            "summary": {
                "archive": self._summarize_metrics(archive_metrics),
                "retention": self._summarize_metrics(retention_metrics),
                "audit_trail": self._summarize_metrics(audit_metrics),
                "integrity": self._summarize_metrics(integrity_metrics),
            },
            "recommendations": recommendations,
            "legal_basis": [
                {"law": "§ 147 AO", "description": "Aufbewahrungspflicht Abgabenordnung"},
                {"law": "§ 257 HGB", "description": "Aufbewahrungsfristen Handelsgesetzbuch"},
                {"law": "§ 14b UStG", "description": "Rechnungsaufbewahrung Umsatzsteuergesetz"},
            ],
        }

        if include_details:
            report["details"] = {
                "archive_metrics": [self._metric_to_dict(m) for m in archive_metrics],
                "retention_metrics": [self._metric_to_dict(m) for m in retention_metrics],
                "audit_metrics": [self._metric_to_dict(m) for m in audit_metrics],
                "integrity_metrics": [self._metric_to_dict(m) for m in integrity_metrics],
            }

        logger.info(
            "gobd_compliance_report_generated",
            company_id=str(company_id),
            overall_score=overall_score,
            status=overall_status.value,
        )

        return report

    async def _check_archive_compliance(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ComplianceMetric]:
        """Prueft Archivierungs-Compliance."""
        metrics = []

        # Gesamtzahl Dokumente
        total_docs_result = await db.execute(
            select(func.count()).select_from(Document)
            .where(Document.company_id == company_id)
        )
        total_docs = total_docs_result.scalar() or 0

        # Archivierte Dokumente
        archived_docs_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(DocumentArchive.company_id == company_id)
        )
        archived_docs = archived_docs_result.scalar() or 0

        # Archivierungsrate
        archive_rate = archived_docs / total_docs if total_docs > 0 else 1.0
        archive_status = (
            ComplianceStatus.COMPLIANT if archive_rate >= self.MIN_ARCHIVE_RATE
            else ComplianceStatus.WARNING if archive_rate >= 0.8
            else ComplianceStatus.NON_COMPLIANT
        )

        metrics.append(ComplianceMetric(
            name="Archivierungsrate",
            value=f"{archive_rate * 100:.1f}%",
            status=archive_status,
            threshold=f"{self.MIN_ARCHIVE_RATE * 100:.0f}%",
            description=f"{archived_docs} von {total_docs} Dokumenten archiviert",
            recommendation="Nicht archivierte Dokumente pruefen und archivieren" if archive_status != ComplianceStatus.COMPLIANT else None,
        ))

        # Dokumente ohne Hash (nicht signiert)
        unsigned_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    or_(
                        DocumentArchive.content_hash.is_(None),
                        DocumentArchive.content_hash == "",
                    )
                )
            )
        )
        unsigned_docs = unsigned_result.scalar() or 0
        unsigned_status = (
            ComplianceStatus.COMPLIANT if unsigned_docs == 0
            else ComplianceStatus.NON_COMPLIANT
        )

        metrics.append(ComplianceMetric(
            name="Dokumente ohne Hash-Signatur",
            value=unsigned_docs,
            status=unsigned_status,
            threshold=0,
            description="Alle archivierten Dokumente benoetigen SHA-256 Hash",
            recommendation="Hash-Signatur fuer unsignierte Dokumente erstellen" if unsigned_docs > 0 else None,
        ))

        return metrics

    async def _check_retention_compliance(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        report_date: date,
    ) -> List[ComplianceMetric]:
        """Prueft Aufbewahrungsfristen-Compliance."""
        metrics = []

        # Abgelaufene Archive (Aufbewahrungsfrist ueberschritten, aber nicht geloescht)
        expired_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at < report_date,
                )
            )
        )
        expired_count = expired_result.scalar() or 0

        # Hinweis: Abgelaufene Dokumente sind NICHT automatisch non-compliant
        # Sie KOENNEN geloescht werden, muessen aber nicht sofort geloescht werden
        expired_status = (
            ComplianceStatus.COMPLIANT if expired_count == 0
            else ComplianceStatus.WARNING
        )

        metrics.append(ComplianceMetric(
            name="Abgelaufene Aufbewahrungsfristen",
            value=expired_count,
            status=expired_status,
            description="Dokumente deren Aufbewahrungsfrist abgelaufen ist",
            recommendation="Pruefen ob abgelaufene Dokumente geloescht werden koennen" if expired_count > 0 else None,
        ))

        # Bald ablaufende Archive (90 Tage)
        expiring_soon_date = report_date + timedelta(days=90)
        expiring_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at >= report_date,
                    DocumentArchive.retention_expires_at <= expiring_soon_date,
                )
            )
        )
        expiring_count = expiring_result.scalar() or 0

        metrics.append(ComplianceMetric(
            name="In 90 Tagen ablaufend",
            value=expiring_count,
            status=ComplianceStatus.COMPLIANT,  # Informativ
            description="Dokumente mit ablaufender Aufbewahrungsfrist",
        ))

        # Aufbewahrungsfristen nach Kategorie
        category_result = await db.execute(
            select(
                DocumentArchive.retention_category,
                func.count().label('count'),
                func.min(DocumentArchive.retention_expires_at).label('earliest_expiry'),
            )
            .where(DocumentArchive.company_id == company_id)
            .group_by(DocumentArchive.retention_category)
        )
        categories = category_result.all()

        for cat_row in categories:
            cat_name, count, earliest = cat_row
            cat_status = ComplianceStatus.COMPLIANT
            if earliest and earliest < report_date:
                cat_status = ComplianceStatus.WARNING

            metrics.append(ComplianceMetric(
                name=f"Kategorie: {cat_name}",
                value=count,
                status=cat_status,
                description=f"Fruehester Ablauf: {earliest.isoformat() if earliest else 'Unbekannt'}",
            ))

        return metrics

    async def _check_audit_trail_compliance(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ComplianceMetric]:
        """Prueft Audit-Trail-Compliance (Nachvollziehbarkeit)."""
        metrics = []

        # Dokumente mit Audit-Trail
        docs_with_audit_result = await db.execute(
            select(func.count(func.distinct(DocumentAccessLog.document_id)))
            .where(DocumentAccessLog.company_id == company_id)
        )
        docs_with_audit = docs_with_audit_result.scalar() or 0

        # Gesamtzahl archivierte Dokumente (die sollten Audit-Trail haben)
        archived_docs_result = await db.execute(
            select(func.count(func.distinct(DocumentArchive.document_id)))
            .where(DocumentArchive.company_id == company_id)
        )
        archived_docs = archived_docs_result.scalar() or 0

        # Coverage
        audit_coverage = docs_with_audit / archived_docs if archived_docs > 0 else 1.0
        coverage_status = (
            ComplianceStatus.COMPLIANT if audit_coverage >= self.MIN_AUDIT_TRAIL_COVERAGE
            else ComplianceStatus.WARNING if audit_coverage >= 0.9
            else ComplianceStatus.NON_COMPLIANT
        )

        metrics.append(ComplianceMetric(
            name="Audit-Trail-Abdeckung",
            value=f"{audit_coverage * 100:.1f}%",
            status=coverage_status,
            threshold="100%",
            description=f"{docs_with_audit} von {archived_docs} archivierten Dokumenten haben Zugriffsprotokoll",
            recommendation="Zugriffsprotokollierung fuer alle archivierten Dokumente aktivieren" if coverage_status != ComplianceStatus.COMPLIANT else None,
        ))

        # Sequenzluecken prufen
        null_seq_result = await db.execute(
            select(func.count())
            .where(
                and_(
                    DocumentAccessLog.company_id == company_id,
                    DocumentAccessLog.sequence_number.is_(None),
                )
            )
        )
        null_sequences = null_seq_result.scalar() or 0
        seq_status = (
            ComplianceStatus.COMPLIANT if null_sequences == 0
            else ComplianceStatus.NON_COMPLIANT
        )

        metrics.append(ComplianceMetric(
            name="Sequenzluecken im Audit-Trail",
            value=null_sequences,
            status=seq_status,
            threshold=0,
            description="Fehlende Sequenznummern (GoBD Vollstaendigkeit)",
            recommendation="Ursache fuer fehlende Sequenznummern untersuchen" if null_sequences > 0 else None,
        ))

        # Fehlgeschlagene Zugriffe
        failed_result = await db.execute(
            select(func.count())
            .where(
                and_(
                    DocumentAccessLog.company_id == company_id,
                    DocumentAccessLog.success == False,
                )
            )
        )
        failed_accesses = failed_result.scalar() or 0

        # Fehlgeschlagene Zugriffe sind nicht non-compliant, aber bemerkenswert
        metrics.append(ComplianceMetric(
            name="Fehlgeschlagene Zugriffe",
            value=failed_accesses,
            status=ComplianceStatus.COMPLIANT,  # Informativ
            description="Protokollierte fehlgeschlagene Zugriffsversuche",
        ))

        return metrics

    async def _check_integrity_compliance(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[ComplianceMetric]:
        """Prueft Integritaets-Compliance (Unveraenderbarkeit)."""
        metrics = []

        # Fehlgeschlagene Verifikationen
        failed_verif_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.is_verified == False,
                )
            )
        )
        failed_verifications = failed_verif_result.scalar() or 0
        verif_status = (
            ComplianceStatus.COMPLIANT if failed_verifications == 0
            else ComplianceStatus.NON_COMPLIANT
        )

        metrics.append(ComplianceMetric(
            name="Fehlgeschlagene Integritaetspruefungen",
            value=failed_verifications,
            status=verif_status,
            threshold=0,
            description="Dokumente deren Hash-Verifikation fehlgeschlagen ist",
            recommendation="Sofort pruefen - moegliche Manipulation!" if failed_verifications > 0 else None,
        ))

        # Verifikationen aelter als 90 Tage
        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
        old_verif_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    or_(
                        DocumentArchive.last_verification_at.is_(None),
                        DocumentArchive.last_verification_at < ninety_days_ago,
                    )
                )
            )
        )
        old_verifications = old_verif_result.scalar() or 0
        old_verif_status = (
            ComplianceStatus.COMPLIANT if old_verifications == 0
            else ComplianceStatus.WARNING
        )

        metrics.append(ComplianceMetric(
            name="Veraltete Verifikationen",
            value=old_verifications,
            status=old_verif_status,
            threshold=0,
            description=f"Archive ohne Verifikation in letzten {self.MAX_VERIFICATION_AGE_DAYS} Tagen",
            recommendation="Regelmaessige Integritaetspruefungen planen" if old_verifications > 0 else None,
        ))

        # Archive mit Verifikations-Fehlermeldung
        error_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.verification_failed_reason.isnot(None),
                )
            )
        )
        error_count = error_result.scalar() or 0

        if error_count > 0:
            metrics.append(ComplianceMetric(
                name="Archive mit Verifikationsfehlern",
                value=error_count,
                status=ComplianceStatus.NON_COMPLIANT,
                threshold=0,
                description="Archive mit dokumentierten Verifikationsfehlern",
                recommendation="Fehlerhafte Archive pruefen und korrigieren",
            ))

        return metrics

    def _calculate_overall_score(
        self,
        metrics: List[ComplianceMetric],
    ) -> tuple[float, ComplianceStatus]:
        """Berechnet den Gesamt-Compliance-Score.

        Returns:
            Tuple (score 0-100, overall_status)
        """
        if not metrics:
            return 100.0, ComplianceStatus.UNKNOWN

        # Gewichtung nach Status
        weights = {
            ComplianceStatus.COMPLIANT: 100,
            ComplianceStatus.WARNING: 70,
            ComplianceStatus.NON_COMPLIANT: 0,
            ComplianceStatus.UNKNOWN: 50,
        }

        total_score = sum(weights.get(m.status, 50) for m in metrics)
        avg_score = total_score / len(metrics)

        # Bestimme Overall-Status
        has_non_compliant = any(m.status == ComplianceStatus.NON_COMPLIANT for m in metrics)
        has_warning = any(m.status == ComplianceStatus.WARNING for m in metrics)

        if has_non_compliant:
            overall_status = ComplianceStatus.NON_COMPLIANT
        elif has_warning:
            overall_status = ComplianceStatus.WARNING
        else:
            overall_status = ComplianceStatus.COMPLIANT

        return round(avg_score, 1), overall_status

    def _get_score_description(self, score: float) -> str:
        """Gibt eine deutsche Beschreibung fuer den Score zurueck."""
        if score >= 95:
            return "Ausgezeichnet - Vollstaendige GoBD-Compliance"
        elif score >= 80:
            return "Gut - Geringfuegige Verbesserungen empfohlen"
        elif score >= 60:
            return "Verbesserungswuerdig - Mehrere Massnahmen erforderlich"
        elif score >= 40:
            return "Kritisch - Dringende Massnahmen erforderlich"
        else:
            return "Nicht compliant - Sofortiger Handlungsbedarf"

    def _summarize_metrics(
        self,
        metrics: List[ComplianceMetric],
    ) -> Dict[str, Any]:
        """Fasst Metriken zusammen."""
        if not metrics:
            return {"status": ComplianceStatus.UNKNOWN.value, "count": 0}

        compliant = sum(1 for m in metrics if m.status == ComplianceStatus.COMPLIANT)
        warning = sum(1 for m in metrics if m.status == ComplianceStatus.WARNING)
        non_compliant = sum(1 for m in metrics if m.status == ComplianceStatus.NON_COMPLIANT)

        if non_compliant > 0:
            status = ComplianceStatus.NON_COMPLIANT
        elif warning > 0:
            status = ComplianceStatus.WARNING
        else:
            status = ComplianceStatus.COMPLIANT

        return {
            "status": status.value,
            "total": len(metrics),
            "compliant": compliant,
            "warning": warning,
            "non_compliant": non_compliant,
        }

    def _generate_recommendations(
        self,
        metrics: List[ComplianceMetric],
    ) -> List[Dict[str, Any]]:
        """Generiert Handlungsempfehlungen basierend auf Metriken."""
        recommendations = []
        priority = 1

        # Sortiere nach Dringlichkeit (NON_COMPLIANT zuerst)
        for metric in sorted(
            metrics,
            key=lambda m: (
                0 if m.status == ComplianceStatus.NON_COMPLIANT
                else 1 if m.status == ComplianceStatus.WARNING
                else 2
            )
        ):
            if metric.recommendation and metric.status != ComplianceStatus.COMPLIANT:
                recommendations.append({
                    "priority": priority,
                    "severity": metric.status.value,
                    "metric": metric.name,
                    "recommendation": metric.recommendation,
                })
                priority += 1

        return recommendations

    def _metric_to_dict(self, metric: ComplianceMetric) -> Dict[str, Any]:
        """Konvertiert Metrik zu Dictionary."""
        return {
            "name": metric.name,
            "value": metric.value,
            "status": metric.status.value,
            "threshold": metric.threshold,
            "description": metric.description,
            "recommendation": metric.recommendation,
        }

    async def get_quick_compliance_status(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Gibt einen schnellen Compliance-Status zurueck (ohne Details).

        Fuer Dashboard-Widgets und Uebersichten.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant Isolation!)

        Returns:
            Dict mit Compliance-Status

        Raises:
            ValueError: Wenn company_id nicht gefunden
        """
        # Input-Validierung: Company muss existieren (Multi-Tenant!)
        company = await db.get(Company, company_id)
        if not company:
            logger.warning(
                "quick_compliance_company_not_found",
                company_id=str(company_id),
            )
            raise ValueError(f"Firma {company_id} nicht gefunden")

        # Schnelle Checks
        # 1. Fehlgeschlagene Verifikationen
        failed_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.is_verified == False,
                )
            )
        )
        failed_verifications = failed_result.scalar() or 0

        # 2. Sequenzluecken
        null_seq_result = await db.execute(
            select(func.count())
            .where(
                and_(
                    DocumentAccessLog.company_id == company_id,
                    DocumentAccessLog.sequence_number.is_(None),
                )
            )
        )
        null_sequences = null_seq_result.scalar() or 0

        # Bestimme Status
        if failed_verifications > 0 or null_sequences > 0:
            status = ComplianceStatus.NON_COMPLIANT
        else:
            status = ComplianceStatus.COMPLIANT

        return {
            "status": status.value,
            "failed_verifications": failed_verifications,
            "audit_trail_gaps": null_sequences,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # ==========================================================================
    # VERFAHRENSDOKUMENTATION (GoBD Prozessdokumentation)
    # ==========================================================================

    async def generate_verfahrensdokumentation(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        include_system_info: bool = True,
        include_user_roles: bool = True,
        include_change_history: bool = True,
    ) -> Dict[str, Any]:
        """Generiert die GoBD-konforme Verfahrensdokumentation.

        Die Verfahrensdokumentation ist Pflicht nach GoBD und muss enthalten:
        - Allgemeine Beschreibung des DV-Systems
        - Prozessbeschreibungen
        - Benutzer- und Rollenkonzept
        - Aenderungshistorie

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            include_system_info: System-Architektur einschliessen
            include_user_roles: Benutzer und Rollen einschliessen
            include_change_history: Aenderungshistorie einschliessen

        Returns:
            Dict mit vollstaendiger Verfahrensdokumentation
        """
        # Firmendaten laden
        company = await db.get(Company, company_id)
        if not company:
            raise ValueError(f"Firma {company_id} nicht gefunden")

        documentation = {
            "meta": {
                "document_type": "GoBD Verfahrensdokumentation",
                "version": "1.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "company_id": str(company_id),
                # WICHTIG: Firmennamen sind nicht PII im Sinne der DSGVO,
                # da sie oeffentliche Handelsdaten sind (Handelsregister)
                "company_name": company.name if company else "Unbekannt",
            },
            "rechtliche_grundlagen": self._get_legal_basis(),
            "system_beschreibung": await self._generate_system_description(db, company_id),
            "prozess_beschreibungen": await self._generate_process_descriptions(db, company_id),
        }

        if include_system_info:
            documentation["system_architektur"] = self._generate_system_architecture()

        if include_user_roles:
            documentation["benutzer_rollen"] = await self._generate_user_role_documentation(db, company_id)

        if include_change_history:
            documentation["aenderungshistorie"] = await self._generate_change_history(db, company_id)

        return documentation

    def _get_legal_basis(self) -> Dict[str, Any]:
        """Gibt die rechtlichen Grundlagen zurueck."""
        return {
            "gobd": {
                "name": "Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung von Buechern, Aufzeichnungen und Unterlagen in elektronischer Form sowie zum Datenzugriff",
                "kurzform": "GoBD",
                "herausgeber": "Bundesministerium der Finanzen",
                "version": "BMF-Schreiben vom 28.11.2019",
            },
            "aufbewahrungsfristen": [
                {"kategorie": "Handels- und Geschaeftsbriefe", "frist_jahre": 6, "rechtsgrundlage": "§ 257 Abs. 4 HGB"},
                {"kategorie": "Buchungsbelege", "frist_jahre": 10, "rechtsgrundlage": "§ 147 Abs. 3 AO"},
                {"kategorie": "Rechnungen", "frist_jahre": 10, "rechtsgrundlage": "§ 14b UStG"},
                {"kategorie": "Handels- und Geschaeftsbuecher", "frist_jahre": 10, "rechtsgrundlage": "§ 257 Abs. 4 HGB"},
            ],
            "kernprinzipien": [
                "Nachvollziehbarkeit und Nachpruefbarkeit",
                "Vollstaendigkeit",
                "Richtigkeit",
                "Zeitgerechte Buchung und Aufzeichnung",
                "Ordnung",
                "Unveraenderbarkeit",
            ],
        }

    async def _generate_system_description(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Generiert die allgemeine Systembeschreibung."""
        return {
            "name": "Ablage-System OCR",
            "beschreibung": (
                "Intelligentes Dokumentenmanagementsystem mit OCR-Verarbeitung, "
                "automatischer Klassifizierung und GoBD-konformer Archivierung."
            ),
            "einsatzzweck": [
                "Digitalisierung von Eingangsrechnungen und Geschaeftskorrespondenz",
                "Automatische Texterkennung (OCR) mit GPU-Beschleunigung",
                "Klassifizierung und Kategorisierung von Dokumenten",
                "Revisionssichere Archivierung nach GoBD-Anforderungen",
                "Aufbewahrungsfristen-Management",
                "DATEV-Export fuer Steuerberater",
            ],
            "datenarten": [
                {"art": "Eingangsrechnungen", "aufbewahrung": "10 Jahre"},
                {"art": "Ausgangsrechnungen", "aufbewahrung": "10 Jahre"},
                {"art": "Vertraege", "aufbewahrung": "10 Jahre (ab Vertragsende)"},
                {"art": "Geschaeftskorrespondenz", "aufbewahrung": "6 Jahre"},
                {"art": "Buchhaltungsbelege", "aufbewahrung": "10 Jahre"},
            ],
            "compliance_features": [
                "SHA-256 Hash-Signaturen fuer alle archivierten Dokumente",
                "Blockchain-aehnliche Audit-Chain fuer Nachvollziehbarkeit",
                "RFC 3161 Zeitstempel-Unterstuetzung (optional)",
                "Automatische Aufbewahrungsfristen nach Dokumenttyp",
                "Loeschsperre waehrend Aufbewahrungsfrist",
                "Integritaetspruefungen (automatisch und manuell)",
                "Vollstaendiger Audit-Trail aller Zugriffe",
            ],
        }

    def _generate_system_architecture(self) -> Dict[str, Any]:
        """Generiert die Systemarchitektur-Dokumentation."""
        return {
            "komponenten": [
                {
                    "name": "Backend API",
                    "technologie": "Python FastAPI",
                    "funktion": "REST-API fuer alle Geschaeftslogik",
                },
                {
                    "name": "Datenbank",
                    "technologie": "PostgreSQL 16",
                    "funktion": "Persistente Datenspeicherung mit JSONB-Unterstuetzung",
                },
                {
                    "name": "Objektspeicher",
                    "technologie": "MinIO (S3-kompatibel)",
                    "funktion": "Speicherung der Original-Dokumente",
                },
                {
                    "name": "Cache / Queue",
                    "technologie": "Redis",
                    "funktion": "Session-Cache und Task-Queue",
                },
                {
                    "name": "Task Processing",
                    "technologie": "Celery",
                    "funktion": "Asynchrone Verarbeitung (OCR, Exports, etc.)",
                },
                {
                    "name": "OCR Engine",
                    "technologie": "DeepSeek-Janus-Pro / GOT-OCR 2.0",
                    "funktion": "Texterkennung mit GPU-Beschleunigung",
                },
                {
                    "name": "Frontend",
                    "technologie": "React + TypeScript",
                    "funktion": "Benutzeroberflaeche",
                },
            ],
            "sicherheitsmerkmale": [
                "HTTPS/TLS fuer alle Verbindungen",
                "JWT-basierte Authentifizierung",
                "Bcrypt-Passwort-Hashing (Cost Factor 12)",
                "Multi-Tenant Isolation (Row Level Security)",
                "Rate Limiting (Login: 5/15min, API: 100/min)",
                "GDPR-konforme Datenhaltung",
                "AES-256-GCM Verschluesselung fuer sensible Daten",
            ],
            "datensicherung": [
                "Taegliche Datenbank-Backups (PostgreSQL)",
                "Inkrementelle MinIO-Backups",
                "30-Tage Backup-Retention",
                "Verschluesselte Backup-Speicherung",
            ],
        }

    async def _generate_process_descriptions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Generiert die Prozessbeschreibungen."""
        return [
            {
                "prozess_id": "P001",
                "name": "Dokumentenerfassung",
                "beschreibung": "Erfassung von Dokumenten ueber verschiedene Eingangskanaele",
                "schritte": [
                    "1. Dokument-Upload (manuell oder automatisch via Email/Folder-Import)",
                    "2. Format-Validierung (PDF, JPG, PNG, TIFF)",
                    "3. Vergabe einer eindeutigen Dokumenten-ID (UUID)",
                    "4. Speicherung im Objektspeicher (MinIO)",
                    "5. Erstellung des Metadaten-Eintrags in der Datenbank",
                    "6. Einreihung in OCR-Queue",
                ],
                "verantwortlich": "System (automatisch) oder Benutzer (manuell)",
            },
            {
                "prozess_id": "P002",
                "name": "OCR-Verarbeitung",
                "beschreibung": "Automatische Texterkennung und Datenextraktion",
                "schritte": [
                    "1. Dokument aus Queue entnehmen",
                    "2. Vorverarbeitung (Deskew, Binarisierung)",
                    "3. OCR mit konfigurierten Backend (DeepSeek/GOT-OCR)",
                    "4. Strukturierte Datenextraktion (Rechnungsnummer, Betrag, etc.)",
                    "5. Confidence-Score Berechnung",
                    "6. Speicherung der extrahierten Daten",
                    "7. Bei niedriger Confidence: Markierung zur manuellen Pruefung",
                ],
                "verantwortlich": "System (automatisch)",
            },
            {
                "prozess_id": "P003",
                "name": "GoBD-Archivierung",
                "beschreibung": "Revisionssichere Archivierung von Dokumenten",
                "schritte": [
                    "1. Dokumentkategorie bestimmen (Rechnung, Vertrag, etc.)",
                    "2. Aufbewahrungsfrist aus RetentionPolicy ermitteln",
                    "3. SHA-256 Hash des Dokuments berechnen",
                    "4. Optional: RFC 3161 Zeitstempel anfordern",
                    "5. Archiv-Eintrag mit Hash-Signatur erstellen",
                    "6. Eintrag in Audit-Chain hinzufuegen",
                    "7. Loeschsperre aktivieren bis Ablauf der Aufbewahrungsfrist",
                ],
                "verantwortlich": "System (automatisch) oder Benutzer (manuell)",
            },
            {
                "prozess_id": "P004",
                "name": "Integritaetspruefung",
                "beschreibung": "Regelmaessige Verifikation der Dokumentintegritaet",
                "schritte": [
                    "1. Geplante Pruefung via Celery-Task (taeglich/woechentlich)",
                    "2. Dokument aus Objektspeicher laden",
                    "3. SHA-256 Hash neu berechnen",
                    "4. Vergleich mit gespeichertem Hash",
                    "5. Bei Abweichung: Alarm und Protokollierung",
                    "6. Ergebnis in Audit-Chain protokollieren",
                    "7. last_verification_at aktualisieren",
                ],
                "verantwortlich": "System (automatisch)",
            },
            {
                "prozess_id": "P005",
                "name": "DATEV-Export",
                "beschreibung": "Export von Buchungsdaten fuer Steuerberater",
                "schritte": [
                    "1. Zeitraum und Dokumenttypen auswaehlen",
                    "2. Buchungsstapel gemaess DATEV-Format (Version 700) generieren",
                    "3. Vendor-Mapping anwenden (Lieferant -> Konto)",
                    "4. CSV-Export erstellen",
                    "5. Export in Historie protokollieren",
                    "6. Download bereitstellen",
                ],
                "verantwortlich": "Benutzer (manuell)",
            },
            {
                "prozess_id": "P006",
                "name": "Steuerberater-Zugang",
                "beschreibung": "Temporaerer Lesezugriff fuer Steuerberater",
                "schritte": [
                    "1. Administrator erstellt Einladung mit Gueltigkeitsdauer",
                    "2. Einladungs-Link per Email an Steuerberater",
                    "3. Steuerberater akzeptiert und setzt Passwort",
                    "4. Lesezugriff auf freigegebene Dokumente/Zeitraeume",
                    "5. Alle Zugriffe werden protokolliert",
                    "6. Automatische Deaktivierung nach Ablauf",
                ],
                "verantwortlich": "Administrator / System",
            },
        ]

    async def _generate_user_role_documentation(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Generiert die Benutzer- und Rollendokumentation.

        WICHTIG: Diese Methode gibt nur aggregierte Statistiken zurueck,
        keine individuellen User-Daten (PII-Schutz nach DSGVO).
        """
        from app.db.models import User

        # WICHTIG: Wir laden NUR die Rollen, KEINE User-Details (PII)!
        # Aggregierte Abfrage statt User-Objekte laden
        role_result = await db.execute(
            select(User.role, func.count(User.id).label('count'))
            .where(User.company_id == company_id)
            .group_by(User.role)
        )
        role_rows = role_result.all()

        role_counts = {}
        total_users = 0
        for row in role_rows:
            role_name = row[0] if row[0] else 'user'
            count = row[1]
            role_counts[role_name] = count
            total_users += count

        return {
            "rollendefinitionen": [
                {
                    "rolle": "admin",
                    "beschreibung": "Administrator mit vollen Zugriffsrechten",
                    "berechtigungen": [
                        "Alle Dokumente lesen, bearbeiten, loeschen",
                        "Benutzer verwalten",
                        "System-Einstellungen aendern",
                        "Aufbewahrungsfristen konfigurieren",
                        "DATEV-Export",
                        "Steuerberater-Zugang verwalten",
                        "Compliance-Berichte abrufen",
                    ],
                },
                {
                    "rolle": "editor",
                    "beschreibung": "Bearbeiter mit erweiterten Rechten",
                    "berechtigungen": [
                        "Dokumente lesen und bearbeiten",
                        "Dokumente hochladen",
                        "OCR-Ergebnisse korrigieren",
                        "Dokumente archivieren",
                    ],
                },
                {
                    "rolle": "viewer",
                    "beschreibung": "Leser mit eingeschraenkten Rechten",
                    "berechtigungen": [
                        "Zugewiesene Dokumente lesen",
                        "Keine Aenderungen moeglich",
                    ],
                },
                {
                    "rolle": "tax_advisor",
                    "beschreibung": "Steuerberater mit temporaerem Lesezugriff",
                    "berechtigungen": [
                        "Freigegebene Dokumente lesen",
                        "DATEV-Export (eingeschraenkt)",
                        "Keine Aenderungen moeglich",
                        "Zeitlich und inhaltlich begrenzt",
                    ],
                },
            ],
            "benutzerstatistik": {
                # NUR aggregierte Zahlen, KEINE individuellen User-Daten!
                "gesamt": total_users,
                "nach_rolle": role_counts,
                "stand": datetime.now(timezone.utc).isoformat(),
            },
        }

    async def _generate_change_history(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Generiert die Aenderungshistorie aus dem Audit-Trail.

        HINWEIS: Gibt nur technische Metadaten zurueck, keine PII.
        """
        # Input-Validierung: limit begrenzen (DoS-Schutz)
        if limit <= 0 or limit > 1000:
            limit = 50

        # Importiere AuditChainEntry falls vorhanden
        try:
            from app.db.bpmn_models.gobd import AuditChainEntry

            result = await db.execute(
                select(AuditChainEntry)
                .where(AuditChainEntry.company_id == company_id)
                .order_by(AuditChainEntry.sequence_number.desc())
                .limit(limit)
            )
            entries = result.scalars().all()

            history_entries = []
            for entry in entries:
                history_entries.append({
                    "sequence": entry.sequence_number,
                    "event_type": entry.event_type,
                    "timestamp": entry.created_at.isoformat() if entry.created_at else None,
                    # Nur Document-ID (UUID), keine Namen oder Inhalte (PII-Schutz)
                    "document_id": str(entry.document_id) if entry.document_id else None,
                    "verified": entry.is_verified,
                })

            return {
                "quelle": "GoBD Audit-Chain",
                "eintraege": history_entries,
                "gesamt_eintraege": len(history_entries),
                "abgerufen_am": datetime.now(timezone.utc).isoformat(),
            }
        except ImportError:
            # AuditChainEntry Model noch nicht vorhanden - erwarteter Zustand
            logger.info("change_history_model_not_available")
            return {
                "quelle": "GoBD Audit-Chain",
                "eintraege": [],
                "hinweis": "Audit-Chain Model noch nicht initialisiert",
                "abgerufen_am": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            # Unerwarteter Fehler - loggen aber nicht Details exponieren
            logger.error(
                "change_history_unexpected_error",
                error_type=type(e).__name__,
                # WICHTIG: Keine Details des Fehlers loggen (koennte PII enthalten)
            )
            return {
                "quelle": "GoBD Audit-Chain",
                "eintraege": [],
                "hinweis": "Fehler beim Abrufen der Audit-Chain",
                "abgerufen_am": datetime.now(timezone.utc).isoformat(),
            }


# Singleton-Instanz
gobd_compliance_service = GoBDComplianceService()
