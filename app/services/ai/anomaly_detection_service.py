# -*- coding: utf-8 -*-
"""
AnomalyDetectionService - Erkennung ungewoehnlicher Muster.

Erkennt Anomalien in Dokumenten:
- Ungewoehnliche Betraege (>3x Median)
- Unbekannte Lieferanten mit hohen Betraegen
- Doppelte Rechnungsnummern
- Unuebliche Zahlungsziele
- Auffällige Muster

Ziel-Konfidenz: 85%+ für Alert.

Feinpoliert und durchdacht - Fraud Prevention & Quality Control.
"""

from __future__ import annotations

import asyncio
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Union

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity
from app.services.ai.extracted_data_wrapper import ExtractedData, get_extracted_data
from app.services.ai.decision_service import (
    AIDecisionService,
    AIDecisionResult,
    DecisionType,
    get_ai_decision_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

ANOMALY_REQUESTS = Counter(
    "anomaly_detection_requests_total",
    "Anzahl der Anomalie-Erkennungs-Anfragen",
    ["anomaly_type", "severity"]
)

ANOMALY_DURATION = Histogram(
    "anomaly_detection_duration_seconds",
    "Dauer der Anomalie-Erkennung in Sekunden",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)


# =============================================================================
# Anomalie-Typen und Konfiguration
# =============================================================================

class AnomalyType(str, Enum):
    """Typen von Anomalien."""
    HIGH_AMOUNT = "high_amount"  # Ungewoehnlich hoher Betrag
    NEW_SUPPLIER_HIGH_VALUE = "new_supplier_high_value"  # Neuer Lieferant + hoher Betrag
    DUPLICATE_NUMBER = "duplicate_number"  # Doppelte Rechnungsnummer
    UNUSUAL_PAYMENT_TERMS = "unusual_payment_terms"  # Unuebliches Zahlungsziel
    ROUND_AMOUNT = "round_amount"  # Verdaechtig runder Betrag
    WEEKEND_INVOICE = "weekend_invoice"  # Rechnung am Wochenende
    MISSING_VAT = "missing_vat"  # Fehlende USt-Id bei hohem Betrag
    AMOUNT_MISMATCH = "amount_mismatch"  # Netto + MwSt != Brutto
    FUTURE_DATE = "future_date"  # Datum in der Zukunft


class AnomalySeverity(str, Enum):
    """Schweregrad einer Anomalie."""
    LOW = "low"  # Info
    MEDIUM = "medium"  # Warnung
    HIGH = "high"  # Kritisch
    CRITICAL = "critical"  # Sofortige Prüfung erforderlich


@dataclass
class AnomalyThresholds:
    """Schwellenwerte für Anomalie-Erkennung."""
    high_amount_factor: float = 3.0  # x-faches des Medians
    new_supplier_min_amount: Decimal = Decimal("1000")
    unusual_payment_days_min: int = 60
    round_amount_threshold: Decimal = Decimal("10000")
    vat_check_min_amount: Decimal = Decimal("500")
    amount_mismatch_tolerance: float = 0.01  # 1%


@dataclass
class DetectedAnomaly:
    """Eine erkannte Anomalie."""
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    confidence: float
    description: str
    details: Dict[str, Union[str, int, float, List[str]]] = field(default_factory=dict)
    recommendation: Optional[str] = None


@dataclass
class AnomalyCheckResult:
    """Ergebnis der Anomalie-Prüfung."""
    anomalies: List[DetectedAnomaly] = field(default_factory=list)
    is_suspicious: bool = False
    overall_risk_score: float = 0.0
    processing_time_ms: int = 0


class AnomalyDetectionService:
    """
    Erkennung von Anomalien in Dokumenten.

    Prüft auf verschiedene verdaechtige Muster und
    berechnet einen Risiko-Score.
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._decision_service = get_ai_decision_service()
        self._thresholds = AnomalyThresholds()
        self._amount_cache: Dict[uuid.UUID, List[float]] = {}

    async def _get_historical_amounts(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID],
        days: int = 365,
    ) -> List[float]:
        """Laedt historische Betraege für Vergleich."""
        cache_key = company_id or uuid.UUID('00000000-0000-0000-0000-000000000000')
        if cache_key in self._amount_cache:
            return self._amount_cache[cache_key]

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # N+1 QUERY FIX: Direkte JSONB-Extraction statt 1000 Document-Objekte laden
        # Vorher: Lade 1000 Documents, parse JSONB in Python → langsam & memory-intensiv
        # Jetzt: Extrahiere nur total_gross direkt in SQL → schnell & effizient
        from sqlalchemy import cast, Float
        from sqlalchemy.dialects.postgresql import JSONB

        query = select(
            Document.extracted_data["total_gross"].astext.cast(Float)
        ).where(
            and_(
                Document.extracted_data.isnot(None),
                Document.extracted_data["total_gross"].isnot(None),
                Document.created_at >= cutoff,
            )
        )

        if company_id:
            query = query.where(Document.company_id == company_id)

        result = await db.execute(query.limit(1000))
        rows = result.all()

        # Extrahiere Betraege aus Result (schon als Float gecasted)
        amounts = [row[0] for row in rows if row[0] is not None and row[0] > 0]

        if len(amounts) < 10:
            # Fallback auf Default-Werte
            amounts = [500, 1000, 2000, 5000, 10000]

        self._amount_cache[cache_key] = amounts
        return amounts

    async def _check_high_amount(
        self,
        db: AsyncSession,
        data: ExtractedData,
        company_id: Optional[uuid.UUID],
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf ungewoehnlich hohe Betraege."""
        if not data.total_gross:
            return None

        amount = float(data.total_gross)
        historical = await self._get_historical_amounts(db, company_id)

        if len(historical) < 5:
            return None

        median = statistics.median(historical)
        threshold = median * self._thresholds.high_amount_factor

        if amount > threshold:
            factor = amount / median if median > 0 else 0

            # Severity basierend auf Faktor
            if factor > 10:
                severity = AnomalySeverity.CRITICAL
            elif factor > 5:
                severity = AnomalySeverity.HIGH
            else:
                severity = AnomalySeverity.MEDIUM

            confidence = min(0.5 + (factor - 3) * 0.1, 0.95)

            return DetectedAnomaly(
                anomaly_type=AnomalyType.HIGH_AMOUNT,
                severity=severity,
                confidence=confidence,
                description=f"Betrag {amount:.2f} EUR ist {factor:.1f}x höher als der Median ({median:.2f} EUR)",
                details={
                    "amount": amount,
                    "median": median,
                    "factor": round(factor, 2),
                    "threshold": threshold,
                },
                recommendation="Betrag manuell prüfen und mit Lieferant abgleichen",
            )

        return None

    async def _check_new_supplier_high_value(
        self,
        db: AsyncSession,
        data: ExtractedData,
        company_id: Optional[uuid.UUID],
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf neue Lieferanten mit hohen Betraegen."""
        if not data.total_gross or not data.supplier_name:
            return None

        amount = data.total_gross
        if amount < self._thresholds.new_supplier_min_amount:
            return None

        # Prüfe ob Lieferant bekannt ist
        if data.supplier_id:
            # Lieferant existiert bereits
            return None

        # Suche nach ähnlichen Namen
        query = select(BusinessEntity).where(
            BusinessEntity.name.ilike(f"%{data.supplier_name[:20]}%")
        )
        if company_id:
            query = query.where(BusinessEntity.company_id == company_id)

        result = await db.execute(query.limit(5))
        similar = result.scalars().all()

        if not similar:
            confidence = 0.7 + min(float(amount) / 10000 * 0.1, 0.2)

            severity = AnomalySeverity.MEDIUM
            if amount > Decimal("5000"):
                severity = AnomalySeverity.HIGH
            if amount > Decimal("20000"):
                severity = AnomalySeverity.CRITICAL

            return DetectedAnomaly(
                anomaly_type=AnomalyType.NEW_SUPPLIER_HIGH_VALUE,
                severity=severity,
                confidence=confidence,
                description=f"Unbekannter Lieferant '{data.supplier_name}' mit hohem Betrag ({amount:.2f} EUR)",
                details={
                    "supplier_name": data.supplier_name,
                    "amount": float(amount),
                },
                recommendation="Lieferant verifizieren bevor Zahlung freigegeben wird",
            )

        return None

    async def _check_duplicate_number(
        self,
        db: AsyncSession,
        data: ExtractedData,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID],
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf doppelte Rechnungsnummern."""
        if not data.invoice_number:
            return None

        # N+1 QUERY FIX: JSONB-Filter direkt in SQL statt Python-Schleife
        # PostgreSQL JSONB-Operator: extracted_data->>'invoice_number' = 'value'
        query = select(Document).where(
            and_(
                Document.id != document_id,
                Document.extracted_data.isnot(None),
                # JSONB Text-Extraktion mit ->> Operator
                Document.extracted_data["invoice_number"].astext == data.invoice_number,
            )
        )
        if company_id:
            query = query.where(Document.company_id == company_id)

        result = await db.execute(query.limit(5))
        duplicates = result.scalars().all()

        if duplicates:
            return DetectedAnomaly(
                anomaly_type=AnomalyType.DUPLICATE_NUMBER,
                severity=AnomalySeverity.HIGH,
                confidence=0.95,
                description=f"Rechnungsnummer '{data.invoice_number}' existiert bereits ({len(duplicates)}x)",
                details={
                    "invoice_number": data.invoice_number,
                    "duplicate_count": len(duplicates),
                    "duplicate_document_ids": [str(d.id) for d in duplicates],
                },
                recommendation="Mögliche Doppelrechnung - Vor Zahlung prüfen",
            )

        return None

    def _check_unusual_payment_terms(
        self,
        data: ExtractedData,
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf unuebliche Zahlungsziele."""
        if not data.payment_term_days:
            return None

        days = data.payment_term_days

        # Unueblich lang
        if days > self._thresholds.unusual_payment_days_min:
            return DetectedAnomaly(
                anomaly_type=AnomalyType.UNUSUAL_PAYMENT_TERMS,
                severity=AnomalySeverity.LOW,
                confidence=0.7,
                description=f"Ungewoehnlich langes Zahlungsziel: {days} Tage",
                details={"payment_term_days": days},
                recommendation="Zahlungsziel prüfen - ggf. Skonto nutzen",
            )

        # Negativ oder 0
        if days <= 0:
            return DetectedAnomaly(
                anomaly_type=AnomalyType.UNUSUAL_PAYMENT_TERMS,
                severity=AnomalySeverity.MEDIUM,
                confidence=0.8,
                description=f"Ungültiges Zahlungsziel: {days} Tage",
                details={"payment_term_days": days},
                recommendation="Zahlungsziel korrigieren",
            )

        return None

    def _check_round_amount(
        self,
        data: ExtractedData,
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf verdaechtig runde Betraege."""
        if not data.total_gross:
            return None

        amount = float(data.total_gross)

        if amount < float(self._thresholds.round_amount_threshold):
            return None

        # Prüfe ob Betrag sehr rund ist (z.B. 10000, 50000)
        if amount % 1000 == 0 and amount >= 10000:
            return DetectedAnomaly(
                anomaly_type=AnomalyType.ROUND_AMOUNT,
                severity=AnomalySeverity.LOW,
                confidence=0.5,
                description=f"Verdaechtig runder Betrag: {amount:.2f} EUR",
                details={"amount": amount},
                recommendation="Betrag gegen Einzelpositionen prüfen",
            )

        return None

    def _check_weekend_invoice(
        self,
        data: ExtractedData,
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf Rechnungen am Wochenende."""
        if not data.invoice_date:
            return None

        weekday = data.invoice_date.weekday()

        if weekday >= 5:  # Samstag oder Sonntag
            day_name = "Samstag" if weekday == 5 else "Sonntag"
            return DetectedAnomaly(
                anomaly_type=AnomalyType.WEEKEND_INVOICE,
                severity=AnomalySeverity.LOW,
                confidence=0.5,
                description=f"Rechnung datiert auf {day_name}",
                details={
                    "invoice_date": data.invoice_date.isoformat(),
                    "weekday": weekday,
                },
            )

        return None

    def _check_missing_vat(
        self,
        data: ExtractedData,
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf fehlende USt-ID bei hohen Betraegen."""
        if not data.total_gross:
            return None

        amount = data.total_gross
        if amount < self._thresholds.vat_check_min_amount:
            return None

        if not data.supplier_vat_id and not data.customer_vat_id:
            return DetectedAnomaly(
                anomaly_type=AnomalyType.MISSING_VAT,
                severity=AnomalySeverity.MEDIUM,
                confidence=0.6,
                description=f"Keine USt-ID bei Rechnung über {amount:.2f} EUR",
                details={"amount": float(amount)},
                recommendation="USt-ID des Lieferanten prüfen für Vorsteuerabzug",
            )

        return None

    def _check_amount_mismatch(
        self,
        data: ExtractedData,
    ) -> Optional[DetectedAnomaly]:
        """Prüft ob Netto + MwSt = Brutto."""
        if not data.total_net or not data.total_gross or not data.vat_amount:
            return None

        calculated_gross = float(data.total_net) + float(data.vat_amount)
        actual_gross = float(data.total_gross)

        diff = abs(calculated_gross - actual_gross)
        tolerance = actual_gross * self._thresholds.amount_mismatch_tolerance

        if diff > tolerance and diff > 0.01:
            return DetectedAnomaly(
                anomaly_type=AnomalyType.AMOUNT_MISMATCH,
                severity=AnomalySeverity.MEDIUM,
                confidence=0.85,
                description=f"Netto ({data.total_net}) + MwSt ({data.vat_amount}) != Brutto ({data.total_gross})",
                details={
                    "total_net": float(data.total_net),
                    "vat_amount": float(data.vat_amount),
                    "total_gross": actual_gross,
                    "calculated_gross": calculated_gross,
                    "difference": round(diff, 2),
                },
                recommendation="Betraege auf Rechnung prüfen",
            )

        return None

    def _check_future_date(
        self,
        data: ExtractedData,
    ) -> Optional[DetectedAnomaly]:
        """Prüft auf Datum in der Zukunft."""
        if not data.invoice_date:
            return None

        today = datetime.now(timezone.utc).date()
        invoice_date = data.invoice_date

        if invoice_date > today:
            days_ahead = (invoice_date - today).days
            return DetectedAnomaly(
                anomaly_type=AnomalyType.FUTURE_DATE,
                severity=AnomalySeverity.MEDIUM,
                confidence=0.9,
                description=f"Rechnungsdatum liegt {days_ahead} Tage in der Zukunft",
                details={
                    "invoice_date": invoice_date.isoformat(),
                    "today": today.isoformat(),
                    "days_ahead": days_ahead,
                },
                recommendation="Rechnungsdatum prüfen",
            )

        return None

    async def check_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> AnomalyCheckResult:
        """
        Prüft ein Dokument auf Anomalien.

        Args:
            db: Database Session
            document_id: Dokument-ID
            company_id: Optional Company-ID

        Returns:
            AnomalyCheckResult
        """
        start_time = time.perf_counter()

        # Lade Document und erstelle ExtractedData Wrapper
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return AnomalyCheckResult()

        data = get_extracted_data(doc)
        if not data:
            return AnomalyCheckResult()

        anomalies: List[DetectedAnomaly] = []

        # ASYNC PATTERN FIX: Parallel statt Sequential Execution
        # Vorher: Sequential awaits verlangsamen die Verarbeitung
        # Jetzt: asyncio.gather() für parallele Ausführung
        async_results = await asyncio.gather(
            self._check_high_amount(db, data, company_id),
            self._check_new_supplier_high_value(db, data, company_id),
            self._check_duplicate_number(db, data, document_id, company_id),
            return_exceptions=True,  # Einzelne Fehler stoppen nicht alle Checks
        )

        # Ergebnisse verarbeiten
        for result in async_results:
            if isinstance(result, Exception):
                logger.warning("anomaly_check_failed", error=str(result))
            elif result is not None:
                anomalies.append(result)

        # Sync-Checks
        sync_checks = [
            self._check_unusual_payment_terms(data),
            self._check_round_amount(data),
            self._check_weekend_invoice(data),
            self._check_missing_vat(data),
            self._check_amount_mismatch(data),
            self._check_future_date(data),
        ]

        for check in sync_checks:
            if check:
                anomalies.append(check)

        # Risiko-Score berechnen
        severity_weights = {
            AnomalySeverity.LOW: 0.1,
            AnomalySeverity.MEDIUM: 0.3,
            AnomalySeverity.HIGH: 0.6,
            AnomalySeverity.CRITICAL: 1.0,
        }

        risk_score = sum(
            severity_weights[a.severity] * a.confidence
            for a in anomalies
        )
        risk_score = min(risk_score, 1.0)

        is_suspicious = risk_score > 0.3 or any(
            a.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL)
            for a in anomalies
        )

        processing_time_ms = int((time.perf_counter() - start_time) * 1000)
        ANOMALY_DURATION.observe(processing_time_ms / 1000)

        # Metriken
        for anomaly in anomalies:
            ANOMALY_REQUESTS.labels(
                anomaly_type=anomaly.anomaly_type.value,
                severity=anomaly.severity.value,
            ).inc()

        return AnomalyCheckResult(
            anomalies=anomalies,
            is_suspicious=is_suspicious,
            overall_risk_score=round(risk_score, 3),
            processing_time_ms=processing_time_ms,
        )

    async def create_anomaly_decision(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        check_result: AnomalyCheckResult,
        company_id: Optional[uuid.UUID] = None,
    ) -> Optional[AIDecisionResult]:
        """
        Erstellt eine AI-Entscheidung für erkannte Anomalien.

        Args:
            db: Database Session
            document_id: Dokument-ID
            check_result: Ergebnis der Anomalie-Prüfung
            company_id: Optional Company-ID

        Returns:
            AIDecisionResult oder None wenn keine Anomalien
        """
        if not check_result.anomalies:
            return None

        # Decision Value
        decision_value = {
            "anomalies": [
                {
                    "type": a.anomaly_type.value,
                    "severity": a.severity.value,
                    "description": a.description,
                }
                for a in check_result.anomalies
            ],
            "risk_score": check_result.overall_risk_score,
            "is_suspicious": check_result.is_suspicious,
        }

        # Explanation
        explanation = {
            "reasons": [a.description for a in check_result.anomalies[:5]],
            "recommendations": [
                a.recommendation for a in check_result.anomalies
                if a.recommendation
            ][:3],
            "details": {
                a.anomaly_type.value: a.details
                for a in check_result.anomalies
            },
        }

        # Confidence aus Risiko-Score ableiten
        confidence = min(0.5 + check_result.overall_risk_score * 0.5, 0.95)

        # Entscheidung erstellen (niemals Auto-Apply für Anomalien)
        return await self._decision_service.make_decision(
            db=db,
            decision_type=DecisionType.ANOMALY,
            decision_value=decision_value,
            confidence=confidence,
            document_id=document_id,
            company_id=company_id,
            explanation=explanation,
            features_used={
                "anomaly_count": len(check_result.anomalies),
                "risk_score": check_result.overall_risk_score,
            },
            apply_callback=None,  # Anomalien werden nie automatisch angewendet
        )


# Singleton-Instanz mit Thread-Safety
_anomaly_detection_service: Optional[AnomalyDetectionService] = None
_service_lock = threading.Lock()


def get_anomaly_detection_service() -> AnomalyDetectionService:
    """Factory für AnomalyDetectionService Singleton (Thread-safe)."""
    global _anomaly_detection_service
    if _anomaly_detection_service is None:
        with _service_lock:
            # Double-check locking pattern
            if _anomaly_detection_service is None:
                _anomaly_detection_service = AnomalyDetectionService()
    return _anomaly_detection_service
