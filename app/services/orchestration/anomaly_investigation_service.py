# -*- coding: utf-8 -*-
"""
Anomaly Investigation Service.

Enterprise Feature: Automatisierte Untersuchung bei Betrugs- oder Anomalie-Erkennung.

Workflow bei Anomalie-Erkennung:
1. Alle zugehoerigen Dokumente sammeln
2. Entity-Timeline aufbauen
3. Relevante Transaktionen zusammentragen
4. Untersuchungsbericht generieren
5. Verantwortliche Person benachrichtigen
6. Alert im Alert Center erstellen

Feinpoliert und durchdacht - Enterprise Investigation Management.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.safe_errors import safe_error_log
from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    BankTransaction,
)
from app.db.models_alert import Alert, AlertCategory, AlertSeverity, AlertStatus

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class InvestigationStatus(str, Enum):
    """Status einer Untersuchung."""
    INITIATED = "initiated"
    COLLECTING_DATA = "collecting_data"
    ANALYZING = "analyzing"
    REPORT_GENERATED = "report_generated"
    NOTIFIED = "notified"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class AnomalyType(str, Enum):
    """Arten von Anomalien."""
    DUPLICATE_INVOICE = "duplicate_invoice"
    PRICE_DEVIATION = "price_deviation"
    UNUSUAL_TIMING = "unusual_timing"
    IBAN_CHANGE = "iban_change"
    PHANTOM_SUPPLIER = "phantom_supplier"
    CEO_FRAUD = "ceo_fraud"
    PATTERN_BREAK = "pattern_break"
    VOLUME_ANOMALY = "volume_anomaly"


class RiskAssessment(str, Enum):
    """Risikobewertung."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class TimelineEntry:
    """Ein Eintrag in der Entity-Timeline."""
    timestamp: datetime
    event_type: str
    description: str
    document_id: Optional[UUID] = None
    amount: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RelatedDocument:
    """Ein zugehoeriges Dokument."""
    document_id: UUID
    document_type: str
    created_at: datetime
    amount: Optional[Decimal] = None
    status: Optional[str] = None
    relevance_score: float = 1.0
    relevance_reason: str = ""


@dataclass
class RelatedTransaction:
    """Eine zugehoerige Transaktion."""
    transaction_id: UUID
    transaction_date: datetime
    amount: Decimal
    counterparty: Optional[str] = None
    description: Optional[str] = None
    relevance_score: float = 1.0


@dataclass
class InvestigationReport:
    """Ein Untersuchungsbericht."""
    id: UUID = field(default_factory=uuid4)
    investigation_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Kontext
    entity_id: Optional[UUID] = None
    document_id: Optional[UUID] = None
    anomaly_type: AnomalyType = AnomalyType.PATTERN_BREAK

    # Erkenntnisse
    summary: str = ""
    detailed_findings: List[str] = field(default_factory=list)
    risk_assessment: RiskAssessment = RiskAssessment.MEDIUM
    confidence: float = 0.75

    # Referenzen
    related_documents: List[RelatedDocument] = field(default_factory=list)
    related_transactions: List[RelatedTransaction] = field(default_factory=list)
    entity_timeline: List[TimelineEntry] = field(default_factory=list)

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)
    immediate_actions: List[str] = field(default_factory=list)

    # Metadaten
    data_collection_time_ms: int = 0
    analysis_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "investigation_id": str(self.investigation_id),
            "created_at": self.created_at.isoformat(),
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "document_id": str(self.document_id) if self.document_id else None,
            "anomaly_type": self.anomaly_type.value,
            "summary": self.summary,
            "detailed_findings": self.detailed_findings,
            "risk_assessment": self.risk_assessment.value,
            "confidence": self.confidence,
            "related_documents_count": len(self.related_documents),
            "related_transactions_count": len(self.related_transactions),
            "timeline_entries_count": len(self.entity_timeline),
            "recommendations": self.recommendations,
            "immediate_actions": self.immediate_actions,
            "data_collection_time_ms": self.data_collection_time_ms,
            "analysis_time_ms": self.analysis_time_ms,
        }


@dataclass
class Investigation:
    """Eine laufende Untersuchung."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Ausloeser
    trigger_type: str = ""  # "alert", "manual", "automated"
    trigger_id: Optional[UUID] = None
    anomaly_type: AnomalyType = AnomalyType.PATTERN_BREAK

    # Ziel
    entity_id: Optional[UUID] = None
    document_id: Optional[UUID] = None

    # Status
    status: InvestigationStatus = InvestigationStatus.INITIATED
    assigned_to_id: Optional[UUID] = None

    # Bericht
    report: Optional[InvestigationReport] = None
    alert_id: Optional[UUID] = None

    # Metadaten
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Anomaly Investigation Service
# =============================================================================


class AnomalyInvestigationService:
    """
    Service für automatisierte Anomalie-Untersuchungen.

    Koordiniert den gesamten Investigation-Workflow von der
    Datensammlung bis zur Alert-Erstellung.
    """

    _instance: Optional["AnomalyInvestigationService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "AnomalyInvestigationService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Active Investigations Cache
        self._active_investigations: Dict[UUID, Investigation] = {}
        self._investigations_lock = asyncio.Lock()

        # Konfiguration
        self._lookback_days = 90  # Tage für Timeline
        self._max_related_documents = 50
        self._max_related_transactions = 100

        logger.info("anomaly_investigation_service_initialized")

    # =========================================================================
    # Main Investigation Workflow
    # =========================================================================

    async def start_investigation(
        self,
        db: AsyncSession,
        company_id: UUID,
        anomaly_type: AnomalyType,
        entity_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        trigger_type: str = "automated",
        trigger_id: Optional[UUID] = None,
        assigned_to_id: Optional[UUID] = None,
    ) -> Investigation:
        """
        Startet eine neue Untersuchung.

        Args:
            db: Database Session
            company_id: Company ID
            anomaly_type: Art der Anomalie
            entity_id: Optional: Betroffene Entity
            document_id: Optional: Ausloesende Dokument
            trigger_type: Ausloeser-Typ (alert, manual, automated)
            trigger_id: ID des Ausloesers (z.B. Alert-ID)
            assigned_to_id: Zugewiesener Benutzer

        Returns:
            Investigation Objekt
        """
        investigation = Investigation(
            company_id=company_id,
            anomaly_type=anomaly_type,
            entity_id=entity_id,
            document_id=document_id,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            assigned_to_id=assigned_to_id,
            status=InvestigationStatus.INITIATED,
        )

        async with self._investigations_lock:
            self._active_investigations[investigation.id] = investigation

        logger.info(
            "investigation_started",
            investigation_id=str(investigation.id),
            anomaly_type=anomaly_type.value,
        )

        # Vollständige Untersuchung durchführen
        try:
            investigation = await self._run_investigation(db, investigation)
        except Exception as e:
            logger.error(
                "investigation_failed",
                investigation_id=str(investigation.id),
                **safe_error_log(e),
            )
            investigation.status = InvestigationStatus.ESCALATED
            investigation.metadata["error"] = str(e)

        return investigation

    async def _run_investigation(
        self,
        db: AsyncSession,
        investigation: Investigation,
    ) -> Investigation:
        """Führt die vollständige Untersuchung durch."""

        # Phase 1: Datensammlung
        investigation.status = InvestigationStatus.COLLECTING_DATA
        investigation.updated_at = datetime.now(timezone.utc)

        start_collection = datetime.now(timezone.utc)

        related_docs = await self._collect_related_documents(
            db, investigation.company_id, investigation.entity_id, investigation.document_id
        )

        entity_timeline = await self._build_entity_timeline(
            db, investigation.entity_id
        ) if investigation.entity_id else []

        related_transactions = await self._collect_related_transactions(
            db, investigation.company_id, investigation.entity_id
        )

        collection_time = int((datetime.now(timezone.utc) - start_collection).total_seconds() * 1000)

        # Phase 2: Analyse
        investigation.status = InvestigationStatus.ANALYZING
        investigation.updated_at = datetime.now(timezone.utc)

        start_analysis = datetime.now(timezone.utc)

        report = await self._generate_report(
            db,
            investigation,
            related_docs,
            entity_timeline,
            related_transactions,
        )

        report.data_collection_time_ms = collection_time
        report.analysis_time_ms = int((datetime.now(timezone.utc) - start_analysis).total_seconds() * 1000)

        investigation.report = report
        investigation.status = InvestigationStatus.REPORT_GENERATED
        investigation.updated_at = datetime.now(timezone.utc)

        # Phase 3: Alert erstellen
        alert_id = await self._create_investigation_alert(db, investigation)
        investigation.alert_id = alert_id
        investigation.status = InvestigationStatus.NOTIFIED

        logger.info(
            "investigation_completed",
            investigation_id=str(investigation.id),
            risk_assessment=report.risk_assessment.value,
            findings_count=len(report.detailed_findings),
        )

        return investigation

    # =========================================================================
    # Data Collection
    # =========================================================================

    async def _collect_related_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
        entity_id: Optional[UUID],
        source_document_id: Optional[UUID],
    ) -> List[RelatedDocument]:
        """Sammelt zugehoerige Dokumente."""
        related: List[RelatedDocument] = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self._lookback_days)

        # Dokumente der Entity
        if entity_id:
            query = (
                select(Document)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.business_entity_id == entity_id,
                        Document.created_at >= cutoff_date,
                        Document.deleted_at.is_(None),
                    )
                )
                .order_by(desc(Document.created_at))
                .limit(self._max_related_documents)
            )

            result = await db.execute(query)
            documents = result.scalars().all()

            for doc in documents:
                relevance = 1.0 if doc.id == source_document_id else 0.7
                related.append(RelatedDocument(
                    document_id=doc.id,
                    document_type=doc.document_type or "unknown",
                    created_at=doc.created_at,
                    amount=doc.extracted_amount,
                    relevance_score=relevance,
                    relevance_reason="Dokument der gleichen Entity",
                ))

        # Quell-Dokument hinzufuegen falls nicht bereits enthalten
        if source_document_id:
            doc_query = select(Document).where(Document.id == source_document_id)
            result = await db.execute(doc_query)
            source_doc = result.scalar_one_or_none()

            if source_doc and not any(r.document_id == source_document_id for r in related):
                related.insert(0, RelatedDocument(
                    document_id=source_doc.id,
                    document_type=source_doc.document_type or "unknown",
                    created_at=source_doc.created_at,
                    amount=source_doc.extracted_amount,
                    relevance_score=1.0,
                    relevance_reason="Ausloesende Dokument",
                ))

        return related

    async def _build_entity_timeline(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> List[TimelineEntry]:
        """Baut eine Timeline der Entity-Aktivitäten auf."""
        timeline: List[TimelineEntry] = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self._lookback_days)

        # Entity-Informationen
        entity_query = select(BusinessEntity).where(BusinessEntity.id == entity_id)
        result = await db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if entity and entity.created_at:
            timeline.append(TimelineEntry(
                timestamp=entity.created_at,
                event_type="entity_created",
                description="Geschäftspartner angelegt",
            ))

        # Dokumente der Entity
        docs_query = (
            select(Document)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    Document.created_at >= cutoff_date,
                    Document.deleted_at.is_(None),
                )
            )
            .order_by(Document.created_at)
        )
        result = await db.execute(docs_query)
        documents = result.scalars().all()

        for doc in documents:
            timeline.append(TimelineEntry(
                timestamp=doc.created_at,
                event_type="document_uploaded",
                description=f"Dokument hochgeladen: {doc.document_type or 'unbekannt'}",
                document_id=doc.id,
                amount=doc.extracted_amount,
            ))

        # Invoice-Tracking Events
        invoices_query = (
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    InvoiceTracking.created_at >= cutoff_date,
                )
            )
            .order_by(InvoiceTracking.created_at)
        )
        result = await db.execute(invoices_query)
        invoices = result.scalars().all()

        for inv in invoices:
            timeline.append(TimelineEntry(
                timestamp=inv.created_at,
                event_type=f"invoice_{inv.status}",
                description=f"Rechnung {inv.status}: {inv.invoice_number or 'ohne Nr.'}",
                document_id=inv.document_id,
                amount=inv.gross_amount,
            ))

            if inv.paid_at:
                timeline.append(TimelineEntry(
                    timestamp=inv.paid_at,
                    event_type="invoice_paid",
                    description=f"Zahlung eingegangen: {inv.invoice_number or 'ohne Nr.'}",
                    document_id=inv.document_id,
                    amount=inv.gross_amount,
                ))

        # Nach Zeitstempel sortieren
        timeline.sort(key=lambda x: x.timestamp)

        return timeline

    async def _collect_related_transactions(
        self,
        db: AsyncSession,
        company_id: UUID,
        entity_id: Optional[UUID],
    ) -> List[RelatedTransaction]:
        """Sammelt zugehoerige Bank-Transaktionen."""
        related: List[RelatedTransaction] = []

        if not entity_id:
            return related

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self._lookback_days)

        # Transaktionen mit verknüpfter Entity
        query = (
            select(BankTransaction)
            .where(
                and_(
                    BankTransaction.company_id == company_id,
                    BankTransaction.business_entity_id == entity_id,
                    BankTransaction.booking_date >= cutoff_date,
                )
            )
            .order_by(desc(BankTransaction.booking_date))
            .limit(self._max_related_transactions)
        )

        result = await db.execute(query)
        transactions = result.scalars().all()

        for tx in transactions:
            related.append(RelatedTransaction(
                transaction_id=tx.id,
                transaction_date=tx.booking_date,
                amount=tx.amount,
                counterparty=tx.counterparty_name,
                description=tx.purpose,
                relevance_score=1.0,
            ))

        return related

    # =========================================================================
    # Report Generation
    # =========================================================================

    async def _generate_report(
        self,
        db: AsyncSession,
        investigation: Investigation,
        related_docs: List[RelatedDocument],
        entity_timeline: List[TimelineEntry],
        related_transactions: List[RelatedTransaction],
    ) -> InvestigationReport:
        """Generiert den Untersuchungsbericht."""

        # Risikobewertung basierend auf Anomalie-Typ und Daten
        risk_assessment = self._assess_risk(
            investigation.anomaly_type,
            related_docs,
            related_transactions,
        )

        # Erkenntnisse sammeln
        findings = await self._analyze_findings(
            db,
            investigation,
            related_docs,
            entity_timeline,
            related_transactions,
        )

        # Zusammenfassung generieren
        summary = self._generate_summary(
            investigation.anomaly_type,
            risk_assessment,
            findings,
        )

        # Empfehlungen generieren
        recommendations, immediate_actions = self._generate_recommendations(
            investigation.anomaly_type,
            risk_assessment,
        )

        report = InvestigationReport(
            investigation_id=investigation.id,
            entity_id=investigation.entity_id,
            document_id=investigation.document_id,
            anomaly_type=investigation.anomaly_type,
            summary=summary,
            detailed_findings=findings,
            risk_assessment=risk_assessment,
            confidence=self._calculate_confidence(findings, related_docs),
            related_documents=related_docs,
            related_transactions=related_transactions,
            entity_timeline=entity_timeline,
            recommendations=recommendations,
            immediate_actions=immediate_actions,
        )

        return report

    def _assess_risk(
        self,
        anomaly_type: AnomalyType,
        related_docs: List[RelatedDocument],
        related_transactions: List[RelatedTransaction],
    ) -> RiskAssessment:
        """Bewertet das Risiko der Anomalie."""

        # Basis-Risiko nach Anomalie-Typ
        base_risk = {
            AnomalyType.CEO_FRAUD: RiskAssessment.CRITICAL,
            AnomalyType.IBAN_CHANGE: RiskAssessment.HIGH,
            AnomalyType.PHANTOM_SUPPLIER: RiskAssessment.HIGH,
            AnomalyType.DUPLICATE_INVOICE: RiskAssessment.MEDIUM,
            AnomalyType.PRICE_DEVIATION: RiskAssessment.MEDIUM,
            AnomalyType.VOLUME_ANOMALY: RiskAssessment.MEDIUM,
            AnomalyType.UNUSUAL_TIMING: RiskAssessment.LOW,
            AnomalyType.PATTERN_BREAK: RiskAssessment.LOW,
        }.get(anomaly_type, RiskAssessment.MEDIUM)

        # Erhöhen basierend auf Betragssumme
        total_amount = sum(
            t.amount for t in related_transactions
            if t.amount
        )

        if total_amount > Decimal("50000"):
            if base_risk == RiskAssessment.LOW:
                return RiskAssessment.MEDIUM
            elif base_risk == RiskAssessment.MEDIUM:
                return RiskAssessment.HIGH
        elif total_amount > Decimal("100000"):
            if base_risk != RiskAssessment.CRITICAL:
                return RiskAssessment.CRITICAL

        return base_risk

    async def _analyze_findings(
        self,
        db: AsyncSession,
        investigation: Investigation,
        related_docs: List[RelatedDocument],
        entity_timeline: List[TimelineEntry],
        related_transactions: List[RelatedTransaction],
    ) -> List[str]:
        """Analysiert und sammelt Erkenntnisse."""
        findings: List[str] = []

        # Basis-Erkenntnis
        findings.append(
            f"Anomalie vom Typ '{investigation.anomaly_type.value}' wurde erkannt"
        )

        # Dokumenten-Analyse
        if related_docs:
            findings.append(
                f"{len(related_docs)} zugehoerige Dokumente im Untersuchungszeitraum gefunden"
            )

            # Betraege
            total_doc_amount = sum(
                d.amount for d in related_docs
                if d.amount
            )
            if total_doc_amount > 0:
                findings.append(
                    f"Gesamtbetrag aus Dokumenten: {total_doc_amount:,.2f} EUR"
                )

        # Timeline-Analyse
        if entity_timeline:
            # Ungewoehnliche Aktivitätsmuster
            recent_events = [
                e for e in entity_timeline
                if e.timestamp > datetime.now(timezone.utc) - timedelta(days=7)
            ]
            if len(recent_events) > 10:
                findings.append(
                    f"Ungewoehnlich hohe Aktivität: {len(recent_events)} Events in den letzten 7 Tagen"
                )

        # Transaktions-Analyse
        if related_transactions:
            findings.append(
                f"{len(related_transactions)} zugehoerige Transaktionen gefunden"
            )

            # Ungewoehnliche Betraege
            amounts = [t.amount for t in related_transactions if t.amount]
            if amounts:
                avg_amount = sum(amounts) / len(amounts)
                max_amount = max(amounts)
                if max_amount > avg_amount * Decimal("3"):
                    findings.append(
                        f"Ausreisser-Transaktion erkannt: {max_amount:,.2f} EUR "
                        f"(Durchschnitt: {avg_amount:,.2f} EUR)"
                    )

        # Anomalie-spezifische Erkenntnisse
        if investigation.anomaly_type == AnomalyType.DUPLICATE_INVOICE:
            findings.append(
                "Mögliche Duplikat-Rechnung - manuelle Prüfung erforderlich"
            )
        elif investigation.anomaly_type == AnomalyType.IBAN_CHANGE:
            findings.append(
                "IBAN-Änderung erkannt - Verifizierung der neuen Bankdaten erforderlich"
            )
        elif investigation.anomaly_type == AnomalyType.CEO_FRAUD:
            findings.append(
                "KRITISCH: Möglicher CEO-Fraud erkannt - sofortige Eskalation empfohlen"
            )

        return findings

    def _generate_summary(
        self,
        anomaly_type: AnomalyType,
        risk_assessment: RiskAssessment,
        findings: List[str],
    ) -> str:
        """Generiert eine Zusammenfassung."""
        risk_text = {
            RiskAssessment.LOW: "geringem",
            RiskAssessment.MEDIUM: "mittlerem",
            RiskAssessment.HIGH: "hohem",
            RiskAssessment.CRITICAL: "kritischem",
        }[risk_assessment]

        anomaly_text = {
            AnomalyType.DUPLICATE_INVOICE: "Duplikat-Rechnung",
            AnomalyType.PRICE_DEVIATION: "Preisabweichung",
            AnomalyType.UNUSUAL_TIMING: "ungewoehnlichem Timing",
            AnomalyType.IBAN_CHANGE: "IBAN-Änderung",
            AnomalyType.PHANTOM_SUPPLIER: "unbekanntem Lieferanten",
            AnomalyType.CEO_FRAUD: "möglichem CEO-Betrug",
            AnomalyType.PATTERN_BREAK: "Musterbrechung",
            AnomalyType.VOLUME_ANOMALY: "Volumen-Anomalie",
        }.get(anomaly_type, "Anomalie")

        return (
            f"Untersuchungsbericht zu {anomaly_text} mit {risk_text} Risiko. "
            f"Es wurden {len(findings)} relevante Erkenntnisse identifiziert."
        )

    def _generate_recommendations(
        self,
        anomaly_type: AnomalyType,
        risk_assessment: RiskAssessment,
    ) -> Tuple[List[str], List[str]]:
        """Generiert Empfehlungen und sofortige Massnahmen."""
        recommendations: List[str] = []
        immediate_actions: List[str] = []

        # Risiko-basierte allgemeine Empfehlungen
        if risk_assessment in [RiskAssessment.HIGH, RiskAssessment.CRITICAL]:
            immediate_actions.append("Zahlungen an diese Entity stoppen")
            immediate_actions.append("Verantwortlichen Manager informieren")

        if risk_assessment == RiskAssessment.CRITICAL:
            immediate_actions.append("Compliance-Abteilung einschalten")
            immediate_actions.append("Alle offenen Vorgaenge einfrieren")

        # Anomalie-spezifische Empfehlungen
        if anomaly_type == AnomalyType.DUPLICATE_INVOICE:
            recommendations.append("Rechnung mit vorherigen Rechnungen abgleichen")
            recommendations.append("Lieferanten kontaktieren zur Klaerung")
        elif anomaly_type == AnomalyType.IBAN_CHANGE:
            recommendations.append("Neue IBAN telefonisch beim Lieferanten verifizieren")
            recommendations.append("Schriftliche Bestätigung der Bankverbindung anfordern")
            immediate_actions.append("Keine Zahlung auf neue IBAN ohne Verifizierung")
        elif anomaly_type == AnomalyType.CEO_FRAUD:
            recommendations.append("Absender-Identität verifizieren")
            recommendations.append("Vier-Augen-Prinzip für alle Zahlungen aktivieren")
            immediate_actions.append("IT-Sicherheit über verdaechtige Email informieren")
        elif anomaly_type == AnomalyType.PHANTOM_SUPPLIER:
            recommendations.append("Lieferanten-Existenz prüfen (Handelsregister)")
            recommendations.append("Bestellhistorie analysieren")
        elif anomaly_type == AnomalyType.PRICE_DEVIATION:
            recommendations.append("Preise mit Rahmenvertrag abgleichen")
            recommendations.append("Marktpreise recherchieren")

        # Allgemeine Empfehlungen
        recommendations.append("Untersuchungsergebnis dokumentieren")
        recommendations.append("Praeventivmassnahmen für zukünftige Faelle prüfen")

        return recommendations, immediate_actions

    def _calculate_confidence(
        self,
        findings: List[str],
        related_docs: List[RelatedDocument],
    ) -> float:
        """Berechnet die Konfidenz der Analyse."""
        base_confidence = 0.5

        # Mehr Daten = höhere Konfidenz
        if len(related_docs) > 5:
            base_confidence += 0.15
        if len(related_docs) > 20:
            base_confidence += 0.10

        # Mehr Erkenntnisse = höhere Konfidenz
        if len(findings) > 3:
            base_confidence += 0.10
        if len(findings) > 6:
            base_confidence += 0.10

        return min(0.95, base_confidence)

    # =========================================================================
    # Alert Creation
    # =========================================================================

    async def _create_investigation_alert(
        self,
        db: AsyncSession,
        investigation: Investigation,
    ) -> Optional[UUID]:
        """Erstellt einen Alert für die Untersuchung."""
        if not investigation.report:
            return None

        report = investigation.report

        # Severity basierend auf Risikobewertung
        severity_map = {
            RiskAssessment.LOW: AlertSeverity.LOW,
            RiskAssessment.MEDIUM: AlertSeverity.MEDIUM,
            RiskAssessment.HIGH: AlertSeverity.HIGH,
            RiskAssessment.CRITICAL: AlertSeverity.CRITICAL,
        }
        severity = severity_map[report.risk_assessment]

        # Alert-Code basierend auf Anomalie-Typ
        alert_code = f"INV_{investigation.anomaly_type.value.upper()[:8]}"

        alert = Alert(
            company_id=investigation.company_id,
            alert_code=alert_code,
            category=AlertCategory.FRAUD.value,
            severity=severity.value,
            title=f"Untersuchung: {investigation.anomaly_type.value}",
            message=report.summary,
            source_type="investigation",
            source_id=str(investigation.id),
            document_id=investigation.document_id,
            entity_id=investigation.entity_id,
            metadata={
                "investigation_id": str(investigation.id),
                "risk_assessment": report.risk_assessment.value,
                "findings_count": len(report.detailed_findings),
                "recommendations_count": len(report.recommendations),
            },
            context={
                "immediate_actions": report.immediate_actions,
                "recommendations": report.recommendations[:3],  # Top 3
            },
            available_actions=["acknowledge", "dismiss", "resolve", "escalate"],
        )

        db.add(alert)
        await db.flush()

        logger.info(
            "investigation_alert_created",
            investigation_id=str(investigation.id),
            alert_id=str(alert.id),
            severity=severity.value,
        )

        return alert.id

    # =========================================================================
    # Public API
    # =========================================================================

    async def get_investigation(
        self,
        investigation_id: UUID,
    ) -> Optional[Investigation]:
        """Gibt eine Untersuchung zurück."""
        async with self._investigations_lock:
            return self._active_investigations.get(investigation_id)

    async def list_investigations(
        self,
        company_id: Optional[UUID] = None,
        status: Optional[InvestigationStatus] = None,
        limit: int = 50,
    ) -> List[Investigation]:
        """Listet Untersuchungen auf."""
        async with self._investigations_lock:
            investigations = list(self._active_investigations.values())

        if company_id:
            investigations = [i for i in investigations if i.company_id == company_id]

        if status:
            investigations = [i for i in investigations if i.status == status]

        # Nach Erstellungsdatum sortieren (neueste zuerst)
        investigations.sort(key=lambda x: x.created_at, reverse=True)

        return investigations[:limit]

    async def resolve_investigation(
        self,
        investigation_id: UUID,
        resolution_notes: Optional[str] = None,
    ) -> bool:
        """Markiert eine Untersuchung als abgeschlossen."""
        async with self._investigations_lock:
            investigation = self._active_investigations.get(investigation_id)
            if not investigation:
                return False

            investigation.status = InvestigationStatus.RESOLVED
            investigation.updated_at = datetime.now(timezone.utc)
            if resolution_notes:
                investigation.metadata["resolution_notes"] = resolution_notes

        logger.info(
            "investigation_resolved",
            investigation_id=str(investigation_id),
        )

        return True


# =============================================================================
# Singleton Factory
# =============================================================================

_service_instance: Optional[AnomalyInvestigationService] = None
_service_lock = threading.Lock()


def get_anomaly_investigation_service() -> AnomalyInvestigationService:
    """Factory-Funktion für AnomalyInvestigationService Singleton."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = AnomalyInvestigationService()
    return _service_instance
