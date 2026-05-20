# -*- coding: utf-8 -*-
"""
Fraud Early Warning Service - Proaktive Betrugserkennung.

Enterprise Feature: Frühwarnsystem für potenzielle Betrugsfaelle.

Features:
- Duplikate-Erkennung (ähnliche Rechnungen)
- Preisanomalien (historischer Vergleich)
- Phantom-Lieferanten-Erkennung
- Ungewoehnliche Zahlungsmuster
- Round-Amount Detection
- Velocity Checks (ploetzliche Aktivitätsspitzen)

SECURITY: Alle Alerts werden OHNE PII geloggt (nur IDs).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    BankTransaction,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

FRAUD_ALERTS_GENERATED = Counter(
    "fraud_alerts_generated_total",
    "Total fraud alerts generated",
    ["alert_type", "severity", "company_id"]
)

FRAUD_SCAN_TIME = Histogram(
    "fraud_scan_duration_seconds",
    "Time to run fraud scan",
    ["company_id", "scan_type"]
)

FRAUD_SCORE_DISTRIBUTION = Histogram(
    "fraud_score_distribution",
    "Distribution of fraud risk scores",
    ["company_id"],
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
)


# =============================================================================
# Enums
# =============================================================================

class FraudAlertType(str, Enum):
    """Typ des Fraud-Alerts."""
    DUPLICATE_INVOICE = "duplicate_invoice"
    PRICE_ANOMALY = "price_anomaly"
    PHANTOM_SUPPLIER = "phantom_supplier"
    UNUSUAL_PATTERN = "unusual_pattern"
    ROUND_AMOUNT = "round_amount"
    VELOCITY_SPIKE = "velocity_spike"
    SPLIT_INVOICE = "split_invoice"
    UNUSUAL_TIMING = "unusual_timing"
    NEW_HIGH_VALUE = "new_high_value"
    DORMANT_REACTIVATION = "dormant_reactivation"


class FraudSeverity(str, Enum):
    """Schweregrad des Fraud-Alerts."""
    CRITICAL = "critical"   # Sofortige Untersuchung
    HIGH = "high"           # Innerhalb 24h prüfen
    MEDIUM = "medium"       # Innerhalb 7 Tage prüfen
    LOW = "low"             # Zur Kenntnis


class FraudStatus(str, Enum):
    """Status des Fraud-Alerts."""
    NEW = "new"
    INVESTIGATING = "investigating"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    RESOLVED = "resolved"


# =============================================================================
# TypedDicts
# =============================================================================

class FraudIndicatorDict(TypedDict):
    """Ein Fraud-Indikator."""
    indicator_type: str
    description: str
    weight: float
    evidence: Dict[str, Any]


class FraudAlertDict(TypedDict):
    """Fraud-Alert Dictionary."""
    id: str
    alert_type: str
    severity: str
    status: str
    title: str
    summary: str
    detail: str
    risk_score: int
    confidence: float
    company_id: str
    entity_id: Optional[str]
    document_id: Optional[str]
    invoice_id: Optional[str]
    indicators: List[FraudIndicatorDict]
    recommended_actions: List[str]
    created_at: str
    expires_at: Optional[str]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FraudIndicator:
    """Ein einzelner Fraud-Indikator."""
    indicator_type: str
    description: str
    weight: float  # 0.0 - 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FraudAlert:
    """Ein Fraud-Frühwarnungs-Alert."""
    id: UUID = field(default_factory=uuid4)
    alert_type: FraudAlertType = FraudAlertType.UNUSUAL_PATTERN
    severity: FraudSeverity = FraudSeverity.MEDIUM
    status: FraudStatus = FraudStatus.NEW

    # Content
    title: str = ""
    summary: str = ""
    detail: str = ""

    # Risk Assessment
    risk_score: int = 0  # 0-100
    confidence: float = 0.7

    # Context
    company_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    document_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None

    # Evidence
    indicators: List[FraudIndicator] = field(default_factory=list)

    # Actions
    recommended_actions: List[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    def to_dict(self) -> FraudAlertDict:
        """Konvertiert zu Dictionary."""
        return FraudAlertDict(
            id=str(self.id),
            alert_type=self.alert_type.value,
            severity=self.severity.value,
            status=self.status.value,
            title=self.title,
            summary=self.summary,
            detail=self.detail,
            risk_score=self.risk_score,
            confidence=self.confidence,
            company_id=str(self.company_id) if self.company_id else "",
            entity_id=str(self.entity_id) if self.entity_id else None,
            document_id=str(self.document_id) if self.document_id else None,
            invoice_id=str(self.invoice_id) if self.invoice_id else None,
            indicators=[
                FraudIndicatorDict(
                    indicator_type=ind.indicator_type,
                    description=ind.description,
                    weight=ind.weight,
                    evidence=ind.evidence,
                )
                for ind in self.indicators
            ],
            recommended_actions=self.recommended_actions,
            created_at=self.created_at.isoformat(),
            expires_at=self.expires_at.isoformat() if self.expires_at else None,
        )


@dataclass
class FraudScanResult:
    """Ergebnis eines Fraud-Scans."""
    company_id: UUID
    scan_completed_at: datetime
    scan_duration_seconds: float
    total_alerts: int
    alerts_by_type: Dict[str, int]
    alerts_by_severity: Dict[str, int]
    alerts: List[FraudAlert]
    overall_risk_score: int
    high_risk_entities: List[UUID]


# =============================================================================
# Fraud Early Warning Service
# =============================================================================

class FraudEarlyWarningService:
    """
    Proaktives Frühwarnsystem für Betrug.

    Analysiert Transaktionen, Rechnungen und Entities
    auf verdaechtige Muster.
    """

    # Schwellenwerte
    DUPLICATE_SIMILARITY_THRESHOLD = 0.85  # 85% Ähnlichkeit = Duplikat-Verdacht
    PRICE_DEVIATION_THRESHOLD = 0.3  # 30% Abweichung = Anomalie
    ROUND_AMOUNT_THRESHOLD = 100  # Betraege wie 100, 500, 1000
    VELOCITY_MULTIPLIER = 3.0  # 3x normales Volumen = Spike
    DORMANT_DAYS = 180  # 6 Monate inaktiv = dormant
    NEW_HIGH_VALUE_THRESHOLD = 10000  # Neue Entity mit >10k = Warnung

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._entity_patterns: Dict[UUID, Dict[str, Any]] = {}

    async def scan(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int = 30,
    ) -> FraudScanResult:
        """
        Führt vollständigen Fraud-Scan durch.

        Args:
            db: Database Session
            company_id: Company-ID
            scan_days: Zeitraum für Scan (letzte X Tage)

        Returns:
            FraudScanResult mit allen Alerts
        """
        import time
        start_time = time.perf_counter()

        logger.info(
            "starting_fraud_scan",
            company_id=str(company_id),
            scan_days=scan_days,
        )

        alerts: List[FraudAlert] = []

        # 1. Duplikat-Erkennung
        duplicate_alerts = await self._check_duplicates(db, company_id, scan_days)
        alerts.extend(duplicate_alerts)

        # 2. Preis-Anomalien
        price_alerts = await self._check_price_anomalies(db, company_id, scan_days)
        alerts.extend(price_alerts)

        # 3. Phantom-Lieferanten
        phantom_alerts = await self._check_phantom_suppliers(db, company_id)
        alerts.extend(phantom_alerts)

        # 4. Ungewoehnliche Muster
        pattern_alerts = await self._check_unusual_patterns(db, company_id, scan_days)
        alerts.extend(pattern_alerts)

        # 5. Round-Amount Detection
        round_alerts = await self._check_round_amounts(db, company_id, scan_days)
        alerts.extend(round_alerts)

        # 6. Velocity Spikes
        velocity_alerts = await self._check_velocity_spikes(db, company_id, scan_days)
        alerts.extend(velocity_alerts)

        # 7. Split Invoice Detection
        split_alerts = await self._check_split_invoices(db, company_id, scan_days)
        alerts.extend(split_alerts)

        # 8. New High-Value Entities
        new_entity_alerts = await self._check_new_high_value_entities(db, company_id, scan_days)
        alerts.extend(new_entity_alerts)

        # 9. Dormant Reactivation
        dormant_alerts = await self._check_dormant_reactivation(db, company_id, scan_days)
        alerts.extend(dormant_alerts)

        # Statistiken
        duration = time.perf_counter() - start_time

        alerts_by_type = {}
        alerts_by_severity = {}
        high_risk_entities: Set[UUID] = set()

        for alert in alerts:
            alerts_by_type[alert.alert_type.value] = alerts_by_type.get(alert.alert_type.value, 0) + 1
            alerts_by_severity[alert.severity.value] = alerts_by_severity.get(alert.severity.value, 0) + 1

            if alert.risk_score >= 70 and alert.entity_id:
                high_risk_entities.add(alert.entity_id)

            # Metriken
            FRAUD_ALERTS_GENERATED.labels(
                alert_type=alert.alert_type.value,
                severity=alert.severity.value,
                company_id=str(company_id),
            ).inc()

            FRAUD_SCORE_DISTRIBUTION.labels(
                company_id=str(company_id),
            ).observe(alert.risk_score)

        # Gesamt-Risiko
        overall_risk = self._calculate_overall_risk(alerts)

        FRAUD_SCAN_TIME.labels(
            company_id=str(company_id),
            scan_type="full",
        ).observe(duration)

        logger.info(
            "fraud_scan_completed",
            company_id=str(company_id),
            total_alerts=len(alerts),
            critical_alerts=alerts_by_severity.get("critical", 0),
            high_alerts=alerts_by_severity.get("high", 0),
            overall_risk=overall_risk,
            duration_seconds=duration,
        )

        return FraudScanResult(
            company_id=company_id,
            scan_completed_at=datetime.now(timezone.utc),
            scan_duration_seconds=duration,
            total_alerts=len(alerts),
            alerts_by_type=alerts_by_type,
            alerts_by_severity=alerts_by_severity,
            alerts=alerts,
            overall_risk_score=overall_risk,
            high_risk_entities=list(high_risk_entities),
        )

    async def _check_duplicates(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt potenzielle Duplikat-Rechnungen."""
        alerts = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=scan_days)

        # Lade Rechnungen
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at >= cutoff,
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        # Gruppiere nach Entity + Betrag (potenzielle Duplikate)
        invoice_groups: Dict[str, List[InvoiceTracking]] = {}

        for inv in invoices:
            # Erstelle Hash-Key: Entity + gerundeter Betrag
            amount_rounded = round(float(inv.amount or 0), -1)  # Auf 10er runden
            key = f"{inv.entity_id}_{amount_rounded}"

            if key not in invoice_groups:
                invoice_groups[key] = []
            invoice_groups[key].append(inv)

        # Prüfen auf Duplikate
        for key, group in invoice_groups.items():
            if len(group) < 2:
                continue

            # Vergleiche Paare
            for i, inv1 in enumerate(group):
                for inv2 in group[i+1:]:
                    similarity = self._calculate_invoice_similarity(inv1, inv2)

                    if similarity >= self.DUPLICATE_SIMILARITY_THRESHOLD:
                        # Duplikat gefunden
                        risk_score = int(similarity * 100)
                        severity = FraudSeverity.HIGH if risk_score >= 90 else FraudSeverity.MEDIUM

                        alerts.append(FraudAlert(
                            alert_type=FraudAlertType.DUPLICATE_INVOICE,
                            severity=severity,
                            company_id=company_id,
                            entity_id=inv1.entity_id,
                            invoice_id=inv1.id,
                            title="Potenzielle Duplikat-Rechnung",
                            summary=f"Rechnung mit {similarity*100:.0f}% Ähnlichkeit gefunden.",
                            detail=f"Beide Rechnungen haben ähnliche Betraege und Zeitpunkte.",
                            risk_score=risk_score,
                            confidence=similarity,
                            indicators=[
                                FraudIndicator(
                                    indicator_type="amount_match",
                                    description="Betraege nahezu identisch",
                                    weight=0.4,
                                    evidence={
                                        "amount1": float(inv1.amount or 0),
                                        "amount2": float(inv2.amount or 0),
                                    },
                                ),
                                FraudIndicator(
                                    indicator_type="timing_match",
                                    description="Zeitlich nah beieinander",
                                    weight=0.3,
                                    evidence={
                                        "days_apart": abs((inv1.invoice_date - inv2.invoice_date).days) if inv1.invoice_date and inv2.invoice_date else 0,
                                    },
                                ),
                            ],
                            recommended_actions=[
                                "Beide Rechnungen manuell vergleichen",
                                "Lieferant kontaktieren zur Klaerung",
                                "Zahlungssperre setzen bis Klaerung",
                            ],
                        ))

        return alerts

    def _calculate_invoice_similarity(
        self,
        inv1: InvoiceTracking,
        inv2: InvoiceTracking,
    ) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Rechnungen."""
        score = 0.0
        weights_total = 0.0

        # Betrag (40% Gewicht)
        if inv1.amount and inv2.amount:
            amount_diff = abs(float(inv1.amount) - float(inv2.amount))
            max_amount = max(float(inv1.amount), float(inv2.amount))
            if max_amount > 0:
                amount_similarity = 1 - (amount_diff / max_amount)
                score += amount_similarity * 0.4
            weights_total += 0.4

        # Datum (30% Gewicht)
        if inv1.invoice_date and inv2.invoice_date:
            days_diff = abs((inv1.invoice_date - inv2.invoice_date).days)
            date_similarity = max(0, 1 - (days_diff / 30))  # 30 Tage = 0 Ähnlichkeit
            score += date_similarity * 0.3
            weights_total += 0.3

        # Gleiche Entity (20% Gewicht)
        if inv1.entity_id and inv2.entity_id and inv1.entity_id == inv2.entity_id:
            score += 0.2
        weights_total += 0.2

        # Rechnungsnummer-Ähnlichkeit (10% Gewicht)
        if inv1.invoice_number and inv2.invoice_number:
            # Levenshtein-Distanz vereinfacht
            if inv1.invoice_number == inv2.invoice_number:
                score += 0.1
            elif inv1.invoice_number[:-1] == inv2.invoice_number[:-1]:
                score += 0.05
        weights_total += 0.1

        return score / weights_total if weights_total > 0 else 0

    async def _check_price_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt Preis-Anomalien im historischen Vergleich."""
        alerts = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=scan_days)

        # Aktuelle Rechnungen nach Entity gruppieren
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at >= cutoff,
            )
        )

        result = await db.execute(query)
        recent_invoices = result.scalars().all()

        # Für jede Entity historischen Durchschnitt berechnen
        entity_invoices: Dict[UUID, List[InvoiceTracking]] = {}
        for inv in recent_invoices:
            if inv.entity_id:
                if inv.entity_id not in entity_invoices:
                    entity_invoices[inv.entity_id] = []
                entity_invoices[inv.entity_id].append(inv)

        # Historische Daten laden (aelter als scan_days)
        historical_cutoff = cutoff - timedelta(days=365)  # 1 Jahr Historie

        for entity_id, invoices in entity_invoices.items():
            # Historische Betraege
            hist_query = select(func.avg(InvoiceTracking.amount)).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.created_at >= historical_cutoff,
                    InvoiceTracking.created_at < cutoff,
                )
            )
            hist_result = await db.execute(hist_query)
            historical_avg = hist_result.scalar_one_or_none()

            if not historical_avg or historical_avg == 0:
                continue

            # Aktuelle Betraege prüfen
            for inv in invoices:
                if not inv.amount:
                    continue

                deviation = (float(inv.amount) - float(historical_avg)) / float(historical_avg)

                if abs(deviation) >= self.PRICE_DEVIATION_THRESHOLD:
                    risk_score = min(100, int(abs(deviation) * 100))
                    severity = FraudSeverity.HIGH if abs(deviation) > 0.5 else FraudSeverity.MEDIUM

                    direction = "höher" if deviation > 0 else "niedriger"

                    alerts.append(FraudAlert(
                        alert_type=FraudAlertType.PRICE_ANOMALY,
                        severity=severity,
                        company_id=company_id,
                        entity_id=entity_id,
                        invoice_id=inv.id,
                        title=f"Preisanomalie: {abs(deviation)*100:.0f}% {direction}",
                        summary=f"Rechnungsbetrag weicht erheblich vom historischen Durchschnitt ab.",
                        detail=f"Aktuell: {float(inv.amount):,.2f} EUR, Historisch: {float(historical_avg):,.2f} EUR",
                        risk_score=risk_score,
                        confidence=0.8,
                        indicators=[
                            FraudIndicator(
                                indicator_type="price_deviation",
                                description=f"{abs(deviation)*100:.0f}% Abweichung vom Durchschnitt",
                                weight=0.7,
                                evidence={
                                    "current_amount": float(inv.amount),
                                    "historical_avg": float(historical_avg),
                                    "deviation_percent": deviation * 100,
                                },
                            ),
                        ],
                        recommended_actions=[
                            "Rechnung auf Korrektheit prüfen",
                            "Preise mit Vertrag abgleichen",
                            "Lieferant nach Begruendung fragen",
                        ],
                    ))

        return alerts

    async def _check_phantom_suppliers(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[FraudAlert]:
        """Erkennt potenzielle Phantom-Lieferanten."""
        alerts = []

        # Lieferanten ohne vollständige Daten
        query = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.entity_type == "supplier",
            )
        )

        result = await db.execute(query)
        suppliers = result.scalars().all()

        for supplier in suppliers:
            risk_indicators = []

            # Fehlende kritische Daten
            if not supplier.iban:
                risk_indicators.append(FraudIndicator(
                    indicator_type="missing_iban",
                    description="Keine IBAN hinterlegt",
                    weight=0.3,
                    evidence={},
                ))

            if not supplier.tax_id and not supplier.vat_id:
                risk_indicators.append(FraudIndicator(
                    indicator_type="missing_tax_id",
                    description="Keine Steuer-ID oder USt-ID",
                    weight=0.3,
                    evidence={},
                ))

            if not supplier.address_street or not supplier.address_city:
                risk_indicators.append(FraudIndicator(
                    indicator_type="incomplete_address",
                    description="Unvollständige Adresse",
                    weight=0.2,
                    evidence={},
                ))

            # Zahlungen prüfen (nur IBAN-Wechsel)
            if supplier.iban:
                # Prüfen ob IBAN in anderen Entities vorkommt
                iban_query = select(func.count()).where(
                    and_(
                        BusinessEntity.company_id == company_id,
                        BusinessEntity.iban == supplier.iban,
                        BusinessEntity.id != supplier.id,
                    )
                )
                iban_result = await db.execute(iban_query)
                duplicate_iban_count = iban_result.scalar_one()

                if duplicate_iban_count > 0:
                    risk_indicators.append(FraudIndicator(
                        indicator_type="shared_iban",
                        description=f"IBAN wird von {duplicate_iban_count} anderen Entities verwendet",
                        weight=0.5,
                        evidence={"duplicate_count": duplicate_iban_count},
                    ))

            # Alert erstellen wenn genug Indikatoren
            if risk_indicators:
                total_weight = sum(ind.weight for ind in risk_indicators)

                if total_weight >= 0.5:
                    risk_score = min(100, int(total_weight * 100))
                    severity = FraudSeverity.HIGH if total_weight >= 0.8 else FraudSeverity.MEDIUM

                    alerts.append(FraudAlert(
                        alert_type=FraudAlertType.PHANTOM_SUPPLIER,
                        severity=severity,
                        company_id=company_id,
                        entity_id=supplier.id,
                        title="Verdaechtiger Lieferant",
                        summary=f"{len(risk_indicators)} Risiko-Indikatoren gefunden.",
                        detail="Unvollständige oder verdaechtige Stammdaten.",
                        risk_score=risk_score,
                        confidence=0.7,
                        indicators=risk_indicators,
                        recommended_actions=[
                            "Lieferanten-Daten verifizieren",
                            "Existenz des Unternehmens prüfen (Handelsregister)",
                            "Kontaktdaten validieren",
                            "Zahlungen temporaer aussetzen",
                        ],
                    ))

        return alerts

    async def _check_unusual_patterns(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt ungewoehnliche Transaktionsmuster."""
        alerts = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=scan_days)

        # Ungewoehnliche Uhrzeiten (ausserhalb Geschäftszeiten)
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= cutoff,
                or_(
                    func.extract("hour", Document.created_at) < 6,
                    func.extract("hour", Document.created_at) > 22,
                ),
            )
        )

        result = await db.execute(query)
        unusual_time_docs = result.scalars().all()

        if len(unusual_time_docs) > 5:
            alerts.append(FraudAlert(
                alert_type=FraudAlertType.UNUSUAL_TIMING,
                severity=FraudSeverity.LOW,
                company_id=company_id,
                title="Aktivität ausserhalb Geschäftszeiten",
                summary=f"{len(unusual_time_docs)} Dokumente ausserhalb normaler Geschäftszeiten erstellt.",
                detail="Dokumente wurden zwischen 22:00 und 06:00 hochgeladen.",
                risk_score=30,
                confidence=0.5,
                indicators=[
                    FraudIndicator(
                        indicator_type="unusual_timing",
                        description="Erstellung ausserhalb Geschäftszeiten",
                        weight=0.3,
                        evidence={"count": len(unusual_time_docs)},
                    ),
                ],
                recommended_actions=[
                    "Aktivitätsprotokoll prüfen",
                    "Benutzerkonten auf Kompromittierung prüfen",
                ],
            ))

        return alerts

    async def _check_round_amounts(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt verdaechtig runde Betraege."""
        alerts = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=scan_days)

        # Runde Betraege zaehlen
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at >= cutoff,
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        round_invoices = []
        for inv in invoices:
            if inv.amount:
                amount = float(inv.amount)
                # Prüfen ob runder Betrag (ohne Cents, teilbar durch 100)
                if amount >= self.ROUND_AMOUNT_THRESHOLD and amount % 100 == 0:
                    round_invoices.append(inv)

        # Zu viele runde Betraege sind verdaechtig
        round_ratio = len(round_invoices) / len(invoices) if invoices else 0

        if round_ratio > 0.3 and len(round_invoices) >= 3:  # >30% rund und mindestens 3
            alerts.append(FraudAlert(
                alert_type=FraudAlertType.ROUND_AMOUNT,
                severity=FraudSeverity.MEDIUM,
                company_id=company_id,
                title="Überdurchschnittlich viele runde Betraege",
                summary=f"{len(round_invoices)} von {len(invoices)} Rechnungen ({round_ratio*100:.0f}%) haben runde Betraege.",
                detail="Runde Betraege können auf geschätzte oder fingierte Rechnungen hindeuten.",
                risk_score=int(round_ratio * 70),
                confidence=0.6,
                indicators=[
                    FraudIndicator(
                        indicator_type="round_amount_pattern",
                        description=f"{round_ratio*100:.0f}% runde Betraege",
                        weight=0.5,
                        evidence={
                            "round_count": len(round_invoices),
                            "total_count": len(invoices),
                            "ratio": round_ratio,
                        },
                    ),
                ],
                recommended_actions=[
                    "Runde Rechnungen einzeln prüfen",
                    "Zugrundeliegende Leistungen verifizieren",
                ],
            ))

        return alerts

    async def _check_velocity_spikes(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt ploetzliche Aktivitätsspitzen."""
        alerts = []

        # Vergleiche aktuelle Woche mit historischem Durchschnitt
        current_week_start = datetime.now(timezone.utc) - timedelta(days=7)
        historical_start = current_week_start - timedelta(days=90)

        # Aktuelle Woche
        current_query = select(func.count()).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at >= current_week_start,
            )
        )
        current_result = await db.execute(current_query)
        current_count = current_result.scalar_one()

        # Historischer Durchschnitt pro Woche
        hist_query = select(func.count()).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at >= historical_start,
                InvoiceTracking.created_at < current_week_start,
            )
        )
        hist_result = await db.execute(hist_query)
        hist_count = hist_result.scalar_one()

        weeks_in_history = 12  # 90 Tage / 7
        avg_per_week = hist_count / weeks_in_history if weeks_in_history > 0 else 0

        if avg_per_week > 0 and current_count > avg_per_week * self.VELOCITY_MULTIPLIER:
            spike_factor = current_count / avg_per_week

            alerts.append(FraudAlert(
                alert_type=FraudAlertType.VELOCITY_SPIKE,
                severity=FraudSeverity.HIGH if spike_factor > 5 else FraudSeverity.MEDIUM,
                company_id=company_id,
                title=f"Aktivitätsspitze: {spike_factor:.1f}x normal",
                summary=f"Diese Woche: {current_count} Rechnungen, Durchschnitt: {avg_per_week:.1f}",
                detail="Ploetzliche Aktivitätsspitzen können auf Betrug oder Systemmanipulation hindeuten.",
                risk_score=min(100, int(spike_factor * 20)),
                confidence=0.7,
                indicators=[
                    FraudIndicator(
                        indicator_type="velocity_spike",
                        description=f"{spike_factor:.1f}x normale Aktivität",
                        weight=0.6,
                        evidence={
                            "current_week": current_count,
                            "avg_weekly": avg_per_week,
                            "spike_factor": spike_factor,
                        },
                    ),
                ],
                recommended_actions=[
                    "Rechnungen dieser Woche prüfen",
                    "Benutzeraktivität analysieren",
                    "Automatische Uploads prüfen",
                ],
            ))

        return alerts

    async def _check_split_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt potenzielle Rechnungssplitting-Muster."""
        alerts = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=scan_days)

        # Mehrere Rechnungen am selben Tag vom selben Lieferanten
        query = select(
            InvoiceTracking.entity_id,
            func.date(InvoiceTracking.invoice_date).label("inv_date"),
            func.count().label("count"),
            func.sum(InvoiceTracking.amount).label("total"),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at >= cutoff,
            )
        ).group_by(
            InvoiceTracking.entity_id,
            func.date(InvoiceTracking.invoice_date),
        ).having(
            func.count() >= 3  # 3+ Rechnungen am selben Tag
        )

        result = await db.execute(query)
        suspicious_groups = result.all()

        for group in suspicious_groups:
            if not group.entity_id:
                continue

            # Prüfen ob Einzelbetraege unter einer Schwelle liegen
            detail_query = select(InvoiceTracking.amount).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.entity_id == group.entity_id,
                    func.date(InvoiceTracking.invoice_date) == group.inv_date,
                )
            )
            detail_result = await db.execute(detail_query)
            amounts = [r[0] for r in detail_result.all()]

            # Typisches Split-Muster: Alle Betraege unter einer Schwelle (z.B. 1000 EUR)
            max_amount = max(float(a) for a in amounts) if amounts else 0
            total = float(group.total or 0)

            if max_amount < 1000 and total > 2000:
                alerts.append(FraudAlert(
                    alert_type=FraudAlertType.SPLIT_INVOICE,
                    severity=FraudSeverity.MEDIUM,
                    company_id=company_id,
                    entity_id=group.entity_id,
                    title=f"Potentielles Rechnungssplitting",
                    summary=f"{group.count} Rechnungen am {group.inv_date}, Summe: {total:,.2f} EUR",
                    detail="Mehrere kleine Rechnungen vom selben Lieferanten am selben Tag.",
                    risk_score=60,
                    confidence=0.6,
                    indicators=[
                        FraudIndicator(
                            indicator_type="split_pattern",
                            description=f"{group.count} Rechnungen, max. {max_amount:,.2f} EUR einzeln",
                            weight=0.5,
                            evidence={
                                "invoice_count": group.count,
                                "max_single_amount": max_amount,
                                "total_amount": total,
                                "date": str(group.inv_date),
                            },
                        ),
                    ],
                    recommended_actions=[
                        "Rechnungen konsolidieren oder Grund prüfen",
                        "Genehmigungsschwellen prüfen",
                        "Lieferant kontaktieren",
                    ],
                ))

        return alerts

    async def _check_new_high_value_entities(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt neue Entities mit hohen Betraegen."""
        alerts = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=scan_days)

        # Neue Entities
        new_entities_query = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.created_at >= cutoff,
            )
        )

        result = await db.execute(new_entities_query)
        new_entities = result.scalars().all()

        for entity in new_entities:
            # Summe der Rechnungen für diese Entity
            sum_query = select(func.sum(InvoiceTracking.amount)).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.entity_id == entity.id,
                )
            )
            sum_result = await db.execute(sum_query)
            total = sum_result.scalar_one_or_none()

            if total and float(total) > self.NEW_HIGH_VALUE_THRESHOLD:
                alerts.append(FraudAlert(
                    alert_type=FraudAlertType.NEW_HIGH_VALUE,
                    severity=FraudSeverity.MEDIUM,
                    company_id=company_id,
                    entity_id=entity.id,
                    title="Neue Entity mit hohem Volumen",
                    summary=f"Neuer Partner mit {float(total):,.2f} EUR in {scan_days} Tagen.",
                    detail="Neue Geschäftsbeziehungen mit hohen Betraegen sollten geprüft werden.",
                    risk_score=50,
                    confidence=0.5,
                    indicators=[
                        FraudIndicator(
                            indicator_type="new_high_value",
                            description=f"Neuer Partner, {float(total):,.2f} EUR Volumen",
                            weight=0.4,
                            evidence={
                                "total_amount": float(total),
                                "days_since_creation": (datetime.now(timezone.utc) - entity.created_at).days if entity.created_at else 0,
                            },
                        ),
                    ],
                    recommended_actions=[
                        "Entity-Daten verifizieren",
                        "Handelsregister-Eintrag prüfen",
                        "Referenzen einholen",
                    ],
                ))

        return alerts

    async def _check_dormant_reactivation(
        self,
        db: AsyncSession,
        company_id: UUID,
        scan_days: int,
    ) -> List[FraudAlert]:
        """Erkennt reaktivierte ruhende Konten."""
        alerts = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=scan_days)
        dormant_cutoff = cutoff - timedelta(days=self.DORMANT_DAYS)

        # Entities mit Aktivität nach langer Pause
        # Subquery: Letzte Aktivität vor dormant_cutoff
        subquery = select(
            InvoiceTracking.entity_id,
            func.max(InvoiceTracking.created_at).label("last_activity_before"),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at < dormant_cutoff,
            )
        ).group_by(InvoiceTracking.entity_id).subquery()

        # Aktuelle Aktivität
        recent_query = select(
            InvoiceTracking.entity_id,
            func.count().label("recent_count"),
            func.sum(InvoiceTracking.amount).label("recent_total"),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.created_at >= cutoff,
            )
        ).group_by(InvoiceTracking.entity_id)

        recent_result = await db.execute(recent_query)
        recent_entities = {r.entity_id: {"count": r.recent_count, "total": r.recent_total} for r in recent_result.all()}

        # Prüfen auf dormant + reactivation
        dormant_query = select(subquery).where(
            subquery.c.entity_id.in_(list(recent_entities.keys()))
        )

        dormant_result = await db.execute(dormant_query)
        dormant_entities = dormant_result.all()

        for entity in dormant_entities:
            if entity.entity_id and entity.entity_id in recent_entities:
                recent_data = recent_entities[entity.entity_id]
                days_dormant = (cutoff - entity.last_activity_before).days if entity.last_activity_before else 0

                if days_dormant >= self.DORMANT_DAYS:
                    alerts.append(FraudAlert(
                        alert_type=FraudAlertType.DORMANT_REACTIVATION,
                        severity=FraudSeverity.MEDIUM,
                        company_id=company_id,
                        entity_id=entity.entity_id,
                        title=f"Reaktivierung nach {days_dormant} Tagen",
                        summary=f"Partner war {days_dormant} Tage inaktiv, jetzt {recent_data['count']} neue Transaktionen.",
                        detail=f"Neues Volumen: {float(recent_data['total'] or 0):,.2f} EUR",
                        risk_score=45,
                        confidence=0.55,
                        indicators=[
                            FraudIndicator(
                                indicator_type="dormant_reactivation",
                                description=f"{days_dormant} Tage inaktiv, dann reaktiviert",
                                weight=0.4,
                                evidence={
                                    "days_dormant": days_dormant,
                                    "recent_transactions": recent_data["count"],
                                    "recent_amount": float(recent_data["total"] or 0),
                                },
                            ),
                        ],
                        recommended_actions=[
                            "Kontaktdaten auf Aktualitaet prüfen",
                            "Bankverbindung verifizieren",
                            "Bestellung legitimieren",
                        ],
                    ))

        return alerts

    def _calculate_overall_risk(self, alerts: List[FraudAlert]) -> int:
        """Berechnet Gesamt-Risiko-Score."""
        if not alerts:
            return 0

        # Gewichtete Summe basierend auf Severity
        severity_weights = {
            FraudSeverity.CRITICAL: 4,
            FraudSeverity.HIGH: 3,
            FraudSeverity.MEDIUM: 2,
            FraudSeverity.LOW: 1,
        }

        weighted_sum = sum(
            alert.risk_score * severity_weights.get(alert.severity, 1)
            for alert in alerts
        )

        total_weight = sum(
            severity_weights.get(alert.severity, 1)
            for alert in alerts
        )

        if total_weight == 0:
            return 0

        return min(100, int(weighted_sum / total_weight))


# =============================================================================
# Singleton
# =============================================================================

_fraud_service: Optional[FraudEarlyWarningService] = None


def get_fraud_early_warning_service() -> FraudEarlyWarningService:
    """Gibt die Singleton-Instanz zurück."""
    global _fraud_service
    if _fraud_service is None:
        _fraud_service = FraudEarlyWarningService()
    return _fraud_service
