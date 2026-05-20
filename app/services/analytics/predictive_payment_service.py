# -*- coding: utf-8 -*-
"""
Predictive Payment Analytics Service.

Vision 2026 Q3: Vorhersage von Zahlungseingaengen mit Erklärbarkeit.

Features:
- ML-basierte Zahlungsprognose
- Historische Zahlungsmuster-Analyse
- Risiko-Score Integration
- Erklärbare Faktoren mit Gewichtung
- Confidence-Intervalle

Feinpoliert und durchdacht - Deutsche Qualität.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (

    BusinessEntity,
    Document,
    InvoiceTracking,
    BankTransaction,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

PREDICTION_REQUESTS = Counter(
    "payment_prediction_requests_total",
    "Anzahl der Zahlungsvorhersagen",
    ["confidence_level"]
)

PREDICTION_DURATION = Histogram(
    "payment_prediction_duration_seconds",
    "Dauer der Zahlungsvorhersage",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0]
)

PREDICTION_ACCURACY = Histogram(
    "payment_prediction_accuracy_days",
    "Genauigkeit der Vorhersage (Tage Abweichung)",
    buckets=[1, 3, 5, 7, 14, 30]
)


# =============================================================================
# Datenstrukturen
# =============================================================================

class PredictionConfidence(str, Enum):
    """Konfidenz-Level der Vorhersage."""
    HIGH = "high"      # >85% Konfidenz
    MEDIUM = "medium"  # 70-85% Konfidenz
    LOW = "low"        # <70% Konfidenz


@dataclass
class PredictionFactor:
    """Ein Faktor der zur Vorhersage beitraegt."""
    name: str
    contribution: float  # 0.0 - 1.0
    value: str
    explanation: str


@dataclass
class ConfidenceInterval:
    """Konfidenzintervall für Vorhersage."""
    lower_days: int
    upper_days: int
    probability: float  # z.B. 0.9 für 90% Konfidenz


@dataclass
class PaymentPrediction:
    """Ergebnis einer Zahlungsvorhersage."""
    invoice_id: uuid.UUID
    predicted_payment_date: date
    confidence: float
    confidence_level: PredictionConfidence
    predicted_days_from_due: int  # Positive = nach Fälligkeit
    factors: List[PredictionFactor]
    confidence_interval: ConfidenceInterval
    explanation: str
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityPaymentProfile:
    """Zahlungsprofil eines Geschäftspartners."""
    entity_id: uuid.UUID
    avg_payment_delay_days: float
    median_payment_delay_days: float
    std_deviation_days: float
    total_invoices: int
    on_time_rate: float  # 0.0 - 1.0
    early_payment_rate: float
    late_payment_rate: float
    typical_payment_weekday: Optional[int]  # 0=Montag, 6=Sonntag
    seasonal_patterns: Dict[int, float]  # Monat -> Durchschnittliche Verzögerung


@dataclass
class CashflowPrediction:
    """Aggregierte Cashflow-Vorhersage."""
    date: date
    expected_amount: Decimal
    confidence: float
    invoice_count: int
    high_confidence_amount: Decimal
    medium_confidence_amount: Decimal
    low_confidence_amount: Decimal


# =============================================================================
# Feature Gewichtungen
# =============================================================================

FEATURE_WEIGHTS = {
    "payment_history": 0.35,      # Zahlungshistorie (wichtigster Faktor)
    "risk_score": 0.20,           # Entity Risk Score
    "invoice_amount": 0.15,       # Rechnungsbetrag
    "relationship_age": 0.10,     # Beziehungsdauer
    "day_of_week": 0.05,          # Wochentag
    "month_pattern": 0.05,        # Monatsmuster
    "skonto_available": 0.05,     # Skonto verfügbar
    "dunning_level": 0.05,        # Aktuelle Mahnstufe
}


class PredictivePaymentService:
    """
    Service für Zahlungsvorhersagen.

    Verwendet historische Daten und ML-basierte Analyse
    um Zahlungseingaenge vorherzusagen.
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._profile_cache: Dict[uuid.UUID, EntityPaymentProfile] = {}
        self._cache_ttl_seconds = 3600  # 1 Stunde

    async def predict_payment(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> PaymentPrediction:
        """
        Sagt das voraussichtliche Zahlungsdatum vorher.

        Args:
            db: Database Session
            invoice_id: Invoice-ID
            company_id: Optional Company-ID

        Returns:
            PaymentPrediction mit vorhergesagtem Datum und Erklärung
        """
        import time
        start_time = time.perf_counter()

        # Invoice laden
        result = await db.execute(
            select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise ValueError(f"Rechnung nicht gefunden: {invoice_id}")

        # Entity laden falls verknüpft
        entity: Optional[BusinessEntity] = None
        if invoice.entity_id:
            entity_result = await db.execute(
                select(BusinessEntity).where(BusinessEntity.id == invoice.entity_id)
            )
            entity = entity_result.scalar_one_or_none()

        # Zahlungsprofil erstellen/laden
        profile: Optional[EntityPaymentProfile] = None
        if invoice.entity_id:
            profile = await self._get_or_build_profile(db, invoice.entity_id, company_id)

        # Features berechnen
        features = await self._calculate_features(
            db, invoice, entity, profile, company_id
        )

        # Vorhersage berechnen
        predicted_delay_days, confidence, factors = self._predict_delay(
            invoice, entity, profile, features
        )

        # Berechnungen
        base_date = invoice.due_date or (
            invoice.invoice_date + timedelta(days=30) if invoice.invoice_date else date.today()
        )
        predicted_payment_date = base_date + timedelta(days=predicted_delay_days)

        # Konfidenz-Level bestimmen
        if confidence >= 0.85:
            confidence_level = PredictionConfidence.HIGH
        elif confidence >= 0.70:
            confidence_level = PredictionConfidence.MEDIUM
        else:
            confidence_level = PredictionConfidence.LOW

        # Konfidenzintervall berechnen
        std_dev = profile.std_deviation_days if profile else 7.0
        confidence_interval = ConfidenceInterval(
            lower_days=max(0, predicted_delay_days - int(std_dev * 1.5)),
            upper_days=predicted_delay_days + int(std_dev * 1.5),
            probability=0.90,
        )

        # Erklärung generieren
        explanation = self._generate_explanation(
            invoice, entity, profile, predicted_delay_days, factors
        )

        # Alternativen generieren
        alternatives = self._generate_alternatives(
            predicted_payment_date, predicted_delay_days, std_dev
        )

        # Metriken
        duration = time.perf_counter() - start_time
        PREDICTION_DURATION.observe(duration)
        PREDICTION_REQUESTS.labels(confidence_level=confidence_level.value).inc()

        logger.info(
            "payment_prediction_completed",
            invoice_id=str(invoice_id),
            predicted_date=predicted_payment_date.isoformat(),
            confidence=round(confidence, 2),
            delay_days=predicted_delay_days,
            duration_ms=int(duration * 1000),
        )

        return PaymentPrediction(
            invoice_id=invoice_id,
            predicted_payment_date=predicted_payment_date,
            confidence=round(confidence, 3),
            confidence_level=confidence_level,
            predicted_days_from_due=predicted_delay_days,
            factors=factors,
            confidence_interval=confidence_interval,
            explanation=explanation,
            alternatives=alternatives,
            metadata={
                "base_date": base_date.isoformat(),
                "entity_id": str(invoice.entity_id) if invoice.entity_id else None,
                "has_profile": profile is not None,
                "processing_time_ms": int(duration * 1000),
            },
        )

    async def predict_cashflow(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        days: int = 30,
        start_date: Optional[date] = None,
    ) -> List[CashflowPrediction]:
        """
        Sagt aggregierte Cashflow-Eingaenge vorher.

        Args:
            db: Database Session
            company_id: Company-ID
            days: Anzahl Tage voraus
            start_date: Startdatum (default: heute)

        Returns:
            Liste von CashflowPrediction pro Tag
        """
        start = start_date or date.today()
        end = start + timedelta(days=days)

        # Offene Rechnungen laden
        result = await db.execute(
            select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "overdue", "partially_paid"]),
                )
            )
        )
        open_invoices = list(result.scalars().all())

        # Vorhersagen pro Rechnung
        predictions_by_date: Dict[date, List[Tuple[Decimal, float]]] = {}

        for invoice in open_invoices:
            try:
                prediction = await self.predict_payment(db, invoice.id, company_id)
                pred_date = prediction.predicted_payment_date

                if start <= pred_date <= end:
                    if pred_date not in predictions_by_date:
                        predictions_by_date[pred_date] = []

                    outstanding = invoice.outstanding_amount or invoice.total_gross or Decimal("0")
                    predictions_by_date[pred_date].append(
                        (outstanding, prediction.confidence)
                    )
            except Exception as e:
                logger.warning(
                    "cashflow_prediction_failed_for_invoice",
                    invoice_id=str(invoice.id),
                    **safe_error_log(e),
                )

        # Aggregieren pro Tag
        cashflow_predictions: List[CashflowPrediction] = []

        for day_offset in range(days + 1):
            current_date = start + timedelta(days=day_offset)
            day_predictions = predictions_by_date.get(current_date, [])

            total_amount = sum(p[0] for p in day_predictions)
            avg_confidence = (
                sum(p[1] for p in day_predictions) / len(day_predictions)
                if day_predictions else 0.0
            )

            high_conf = sum(p[0] for p in day_predictions if p[1] >= 0.85)
            medium_conf = sum(p[0] for p in day_predictions if 0.70 <= p[1] < 0.85)
            low_conf = sum(p[0] for p in day_predictions if p[1] < 0.70)

            cashflow_predictions.append(CashflowPrediction(
                date=current_date,
                expected_amount=total_amount,
                confidence=round(avg_confidence, 3),
                invoice_count=len(day_predictions),
                high_confidence_amount=high_conf,
                medium_confidence_amount=medium_conf,
                low_confidence_amount=low_conf,
            ))

        return cashflow_predictions

    async def get_entity_profile(
        self,
        db: AsyncSession,
        entity_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> EntityPaymentProfile:
        """
        Gibt das Zahlungsprofil eines Geschäftspartners zurück.

        Args:
            db: Database Session
            entity_id: Entity-ID
            company_id: Optional Company-ID

        Returns:
            EntityPaymentProfile
        """
        return await self._get_or_build_profile(db, entity_id, company_id)

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    async def _get_or_build_profile(
        self,
        db: AsyncSession,
        entity_id: uuid.UUID,
        company_id: Optional[uuid.UUID],
    ) -> EntityPaymentProfile:
        """Laedt oder erstellt ein Zahlungsprofil."""
        # Cache prüfen (vereinfacht, ohne TTL-Check)
        if entity_id in self._profile_cache:
            return self._profile_cache[entity_id]

        # Historische Zahlungen laden
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.entity_id == entity_id,
                InvoiceTracking.status == "paid",
                InvoiceTracking.paid_at.isnot(None),
            )
        )
        if company_id:
            query = query.where(InvoiceTracking.company_id == company_id)

        result = await db.execute(query.limit(100))  # Letzte 100 Rechnungen
        paid_invoices = list(result.scalars().all())

        # Verzögerungen berechnen
        delays: List[float] = []
        payment_weekdays: List[int] = []
        monthly_delays: Dict[int, List[float]] = {m: [] for m in range(1, 13)}

        for inv in paid_invoices:
            if inv.due_date and inv.paid_at:
                delay = (inv.paid_at.date() - inv.due_date).days
                delays.append(float(delay))
                payment_weekdays.append(inv.paid_at.weekday())
                monthly_delays[inv.paid_at.month].append(float(delay))

        # Statistiken berechnen
        total = len(paid_invoices)

        if delays:
            avg_delay = statistics.mean(delays)
            median_delay = statistics.median(delays)
            std_dev = statistics.stdev(delays) if len(delays) > 1 else 7.0
            on_time_rate = len([d for d in delays if d <= 0]) / total
            early_rate = len([d for d in delays if d < 0]) / total
            late_rate = len([d for d in delays if d > 0]) / total
        else:
            avg_delay = 7.0  # Default: 1 Woche nach Fälligkeit
            median_delay = 7.0
            std_dev = 7.0
            on_time_rate = 0.5
            early_rate = 0.1
            late_rate = 0.4

        # Typischer Zahlungstag
        typical_weekday: Optional[int] = None
        if payment_weekdays:
            weekday_counts = {}
            for wd in payment_weekdays:
                weekday_counts[wd] = weekday_counts.get(wd, 0) + 1
            typical_weekday = max(weekday_counts, key=lambda k: weekday_counts[k])

        # Saisonale Muster
        seasonal = {
            m: statistics.mean(monthly_delays[m]) if monthly_delays[m] else avg_delay
            for m in range(1, 13)
        }

        profile = EntityPaymentProfile(
            entity_id=entity_id,
            avg_payment_delay_days=round(avg_delay, 1),
            median_payment_delay_days=round(median_delay, 1),
            std_deviation_days=round(std_dev, 1),
            total_invoices=total,
            on_time_rate=round(on_time_rate, 3),
            early_payment_rate=round(early_rate, 3),
            late_payment_rate=round(late_rate, 3),
            typical_payment_weekday=typical_weekday,
            seasonal_patterns=seasonal,
        )

        # Cache speichern
        self._profile_cache[entity_id] = profile

        return profile

    async def _calculate_features(
        self,
        db: AsyncSession,
        invoice: InvoiceTracking,
        entity: Optional[BusinessEntity],
        profile: Optional[EntityPaymentProfile],
        company_id: Optional[uuid.UUID],
    ) -> Dict[str, Any]:
        """Berechnet Features für die Vorhersage."""
        features: Dict[str, Any] = {}

        # Basis-Features
        features["invoice_amount"] = float(invoice.total_gross or 0)
        features["days_until_due"] = (
            (invoice.due_date - date.today()).days
            if invoice.due_date else 30
        )
        features["dunning_level"] = invoice.dunning_level or 0
        features["has_skonto"] = invoice.skonto_percentage is not None

        # Entity-Features
        if entity:
            features["entity_risk_score"] = entity.risk_score or 50
            features["relationship_age_months"] = (
                (datetime.now(timezone.utc) - entity.created_at).days // 30
                if entity.created_at else 0
            )
        else:
            features["entity_risk_score"] = 50
            features["relationship_age_months"] = 0

        # Profil-Features
        if profile:
            features["avg_delay"] = profile.avg_payment_delay_days
            features["on_time_rate"] = profile.on_time_rate
            features["typical_weekday"] = profile.typical_payment_weekday
            features["total_invoices"] = profile.total_invoices
        else:
            features["avg_delay"] = 7.0
            features["on_time_rate"] = 0.5
            features["typical_weekday"] = None
            features["total_invoices"] = 0

        # Zeitliche Features
        features["current_month"] = date.today().month
        features["day_of_week"] = date.today().weekday()

        return features

    def _predict_delay(
        self,
        invoice: InvoiceTracking,
        entity: Optional[BusinessEntity],
        profile: Optional[EntityPaymentProfile],
        features: Dict[str, Any],
    ) -> Tuple[int, float, List[PredictionFactor]]:
        """
        Berechnet die vorhergesagte Verzögerung.

        Returns:
            (predicted_delay_days, confidence, factors)
        """
        factors: List[PredictionFactor] = []
        weighted_delay = 0.0
        total_confidence = 0.0

        # 1. Zahlungshistorie (35%)
        if profile and profile.total_invoices > 0:
            history_delay = profile.avg_payment_delay_days
            history_confidence = min(0.95, 0.5 + profile.total_invoices * 0.05)

            weighted_delay += history_delay * FEATURE_WEIGHTS["payment_history"]
            total_confidence += history_confidence * FEATURE_WEIGHTS["payment_history"]

            factors.append(PredictionFactor(
                name="Zahlungshistorie",
                contribution=FEATURE_WEIGHTS["payment_history"],
                value=f"{profile.avg_payment_delay_days:.1f} Tage",
                explanation=f"Durchschnittliche Zahlungsverzögerung bei {profile.total_invoices} Rechnungen",
            ))
        else:
            # Fallback ohne Historie
            weighted_delay += 7.0 * FEATURE_WEIGHTS["payment_history"]
            total_confidence += 0.3 * FEATURE_WEIGHTS["payment_history"]

            factors.append(PredictionFactor(
                name="Zahlungshistorie",
                contribution=FEATURE_WEIGHTS["payment_history"],
                value="Keine Daten",
                explanation="Keine historischen Zahlungsdaten vorhanden, verwende Standardwert",
            ))

        # 2. Risiko-Score (20%)
        risk_score = features.get("entity_risk_score", 50)
        risk_delay = (risk_score / 100) * 14  # 0-100 -> 0-14 Tage

        weighted_delay += risk_delay * FEATURE_WEIGHTS["risk_score"]
        total_confidence += (1 - risk_score / 100) * 0.8 * FEATURE_WEIGHTS["risk_score"]

        factors.append(PredictionFactor(
            name="Risiko-Score",
            contribution=FEATURE_WEIGHTS["risk_score"],
            value=f"{risk_score}/100",
            explanation=f"Entity-Risiko-Score beeinflusst erwartete Verzögerung",
        ))

        # 3. Rechnungsbetrag (15%)
        amount = features.get("invoice_amount", 0)
        if amount > 10000:
            amount_delay = 7  # Größere Betraege dauern länger
        elif amount > 5000:
            amount_delay = 5
        elif amount > 1000:
            amount_delay = 3
        else:
            amount_delay = 0

        weighted_delay += amount_delay * FEATURE_WEIGHTS["invoice_amount"]
        total_confidence += 0.7 * FEATURE_WEIGHTS["invoice_amount"]

        factors.append(PredictionFactor(
            name="Rechnungsbetrag",
            contribution=FEATURE_WEIGHTS["invoice_amount"],
            value=f"{amount:.2f} EUR",
            explanation=f"Höhere Betraege werden tendenziell später bezahlt",
        ))

        # 4. Beziehungsdauer (10%)
        relationship_months = features.get("relationship_age_months", 0)
        if relationship_months > 24:
            rel_delay = -2  # Lange Beziehung = schnellere Zahlung
        elif relationship_months > 12:
            rel_delay = 0
        else:
            rel_delay = 3

        weighted_delay += rel_delay * FEATURE_WEIGHTS["relationship_age"]
        total_confidence += min(0.8, relationship_months / 24) * FEATURE_WEIGHTS["relationship_age"]

        factors.append(PredictionFactor(
            name="Beziehungsdauer",
            contribution=FEATURE_WEIGHTS["relationship_age"],
            value=f"{relationship_months} Monate",
            explanation=f"Längere Geschäftsbeziehungen zeigen zuverlaessigeres Zahlungsverhalten",
        ))

        # 5. Mahnstufe (5%)
        dunning = features.get("dunning_level", 0)
        if dunning > 0:
            # Bei Mahnung erwarten wir schnellere Zahlung
            dunning_delay = -dunning * 3
            weighted_delay += dunning_delay * FEATURE_WEIGHTS["dunning_level"]

            factors.append(PredictionFactor(
                name="Mahnstufe",
                contribution=FEATURE_WEIGHTS["dunning_level"],
                value=f"Stufe {dunning}",
                explanation=f"Mahnung beschleunigt typischerweise die Zahlung",
            ))

        total_confidence += 0.5 * FEATURE_WEIGHTS["dunning_level"]

        # 6. Skonto (5%)
        if features.get("has_skonto", False):
            skonto_delay = -5  # Skonto motiviert frühe Zahlung
            weighted_delay += skonto_delay * FEATURE_WEIGHTS["skonto_available"]

            factors.append(PredictionFactor(
                name="Skonto",
                contribution=FEATURE_WEIGHTS["skonto_available"],
                value="Verfügbar",
                explanation=f"Skonto-Angebot motiviert frühere Zahlung",
            ))

        total_confidence += 0.6 * FEATURE_WEIGHTS["skonto_available"]

        # Normalisierung
        predicted_delay = max(0, int(round(weighted_delay)))
        confidence = min(0.95, max(0.3, total_confidence))

        return predicted_delay, confidence, factors

    def _generate_explanation(
        self,
        invoice: InvoiceTracking,
        entity: Optional[BusinessEntity],
        profile: Optional[EntityPaymentProfile],
        predicted_delay: int,
        factors: List[PredictionFactor],
    ) -> str:
        """Generiert eine erklärende Zusammenfassung."""
        entity_name = entity.name if entity else "Unbekannter Partner"

        if profile and profile.total_invoices > 0:
            history_part = (
                f"Basierend auf {profile.total_invoices} historischen Zahlungen "
                f"(Durchschnitt: {profile.avg_payment_delay_days:.1f} Tage Verzögerung)"
            )
        else:
            history_part = "Keine Zahlungshistorie vorhanden, Standardwerte verwendet"

        top_factors = sorted(factors, key=lambda f: f.contribution, reverse=True)[:3]
        factor_list = ", ".join(f.name for f in top_factors)

        if predicted_delay <= 0:
            timing = "puenktlich oder frühzeitig"
        elif predicted_delay <= 7:
            timing = f"etwa {predicted_delay} Tage nach Fälligkeit"
        elif predicted_delay <= 14:
            timing = f"etwa 1-2 Wochen nach Fälligkeit"
        else:
            timing = f"etwa {predicted_delay} Tage nach Fälligkeit"

        return (
            f"Erwarteter Zahlungseingang von '{entity_name}': {timing}. "
            f"{history_part}. "
            f"Wichtigste Faktoren: {factor_list}."
        )

    def _generate_alternatives(
        self,
        predicted_date: date,
        predicted_delay: int,
        std_dev: float,
    ) -> List[Dict[str, Any]]:
        """Generiert alternative Szenarien."""
        return [
            {
                "scenario": "optimistisch",
                "date": (predicted_date - timedelta(days=int(std_dev))).isoformat(),
                "probability": 0.25,
                "description": "Frühzeitige Zahlung bei günstigem Verlauf",
            },
            {
                "scenario": "erwartet",
                "date": predicted_date.isoformat(),
                "probability": 0.50,
                "description": "Wahrscheinlichster Zeitpunkt basierend auf Analyse",
            },
            {
                "scenario": "pessimistisch",
                "date": (predicted_date + timedelta(days=int(std_dev * 1.5))).isoformat(),
                "probability": 0.25,
                "description": "Spätere Zahlung bei Verzögerungen",
            },
        ]


# =============================================================================
# Factory
# =============================================================================

_predictive_payment_service: Optional[PredictivePaymentService] = None


def get_predictive_payment_service() -> PredictivePaymentService:
    """Factory für PredictivePaymentService Singleton."""
    global _predictive_payment_service
    if _predictive_payment_service is None:
        _predictive_payment_service = PredictivePaymentService()
    return _predictive_payment_service
