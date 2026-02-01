# -*- coding: utf-8 -*-
"""
Predictive Payment AI Service.

ML-basiertes Zahlungsverhalten-Vorhersagesystem:
- Zahlungsverzoegerung-Prognose
- Ausfallwahrscheinlichkeit
- Dynamische Zahlungsziel-Empfehlungen
- Cash-Flow-Projektion

Phase 3: Predictive Payment AI
Feinpoliert und durchdacht.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, List, Tuple
from uuid import UUID
import math

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, Document, InvoiceTracking
from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


# =============================================================================
# Feature Engineering Constants
# =============================================================================

class RiskTier(str, Enum):
    """Risiko-Klassifizierung basierend auf Vorhersagen."""
    LOW = "low"           # Score 0-30: Niedriges Risiko
    MEDIUM = "medium"     # Score 30-60: Mittleres Risiko
    HIGH = "high"         # Score 60-80: Hohes Risiko
    CRITICAL = "critical" # Score 80-100: Kritisches Risiko


class PaymentTermSuggestion(str, Enum):
    """Empfohlene Zahlungsbedingungen."""
    PREPAYMENT = "prepayment"       # Vorkasse
    IMMEDIATE = "immediate"          # Sofortzahlung
    NET_7 = "net_7"                 # 7 Tage netto
    NET_14 = "net_14"               # 14 Tage netto
    NET_30 = "net_30"               # 30 Tage netto (Standard)
    NET_45 = "net_45"               # 45 Tage netto
    NET_60 = "net_60"               # 60 Tage netto
    INSTALLMENT = "installment"      # Ratenzahlung


# Feature weights for payment delay prediction
DELAY_FEATURE_WEIGHTS = {
    "payment_history_avg_delay": 0.25,
    "payment_history_std_delay": 0.10,
    "invoice_volume_factor": 0.10,
    "relationship_age_factor": 0.15,
    "current_outstanding_factor": 0.15,
    "seasonal_factor": 0.10,
    "dunning_history_factor": 0.15,
}

# Seasonal factors (Germany: Q4 slow due to holidays, Q1 slow due to year-end)
SEASONAL_DELAY_FACTORS = {
    1: 1.15,   # Januar - Jahresabschluss
    2: 1.05,
    3: 1.0,
    4: 0.95,
    5: 0.95,
    6: 1.0,
    7: 1.05,   # Urlaubszeit
    8: 1.10,   # Urlaubszeit
    9: 0.95,
    10: 0.95,
    11: 1.0,
    12: 1.20,  # Weihnachten
}


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PaymentFeatures:
    """Feature-Vektor fuer Zahlungsvorhersage."""
    entity_id: UUID

    # Historische Zahlungsmetriken
    payment_history_avg_delay: float = 0.0  # Tage
    payment_history_std_delay: float = 0.0  # Standardabweichung
    total_invoices: int = 0
    paid_invoices: int = 0
    overdue_invoices: int = 0

    # Volumen-Metriken
    invoice_volume_total: float = 0.0
    invoice_volume_last_90_days: float = 0.0

    # Beziehungs-Metriken
    relationship_age_days: int = 0
    first_invoice_date: Optional[datetime] = None
    last_payment_date: Optional[datetime] = None

    # Aktuelle Situation
    current_outstanding: float = 0.0
    current_overdue: float = 0.0

    # Industrie/Kategorie (fuer zukuenftige Erweiterung)
    industry_category: Optional[str] = None

    # Mahnhistorie
    total_dunning_events: int = 0
    max_dunning_level_reached: int = 0

    # Skonto-Nutzung
    skonto_usage_rate: float = 0.0  # 0-1

    def to_dict(self) -> Dict:
        """Serialisierung fuer Logging/Storage."""
        return {
            "entity_id": str(self.entity_id),
            "payment_history_avg_delay": round(self.payment_history_avg_delay, 1),
            "payment_history_std_delay": round(self.payment_history_std_delay, 1),
            "total_invoices": self.total_invoices,
            "paid_invoices": self.paid_invoices,
            "overdue_invoices": self.overdue_invoices,
            "invoice_volume_total": round(self.invoice_volume_total, 2),
            "invoice_volume_last_90_days": round(self.invoice_volume_last_90_days, 2),
            "relationship_age_days": self.relationship_age_days,
            "current_outstanding": round(self.current_outstanding, 2),
            "current_overdue": round(self.current_overdue, 2),
            "total_dunning_events": self.total_dunning_events,
            "max_dunning_level_reached": self.max_dunning_level_reached,
            "skonto_usage_rate": round(self.skonto_usage_rate, 2),
        }


@dataclass
class PaymentDelayPrediction:
    """Vorhersage der Zahlungsverzoegerung."""
    entity_id: UUID
    predicted_delay_days: float
    confidence: float  # 0-1
    risk_tier: RiskTier
    delay_range_min: float  # Untere Grenze (25. Perzentil)
    delay_range_max: float  # Obere Grenze (75. Perzentil)
    prediction_timestamp: datetime = field(default_factory=utc_now)

    # Erklaerung der Vorhersage
    top_factors: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class DefaultProbabilityPrediction:
    """Vorhersage der Ausfallwahrscheinlichkeit."""
    entity_id: UUID
    default_probability: float  # 0-1
    confidence: float  # 0-1
    risk_tier: RiskTier
    prediction_timestamp: datetime = field(default_factory=utc_now)

    # Faktoren
    contributing_factors: Dict[str, float] = field(default_factory=dict)


@dataclass
class PaymentTermsSuggestion:
    """Empfohlene Zahlungsbedingungen."""
    entity_id: UUID
    invoice_amount: float
    suggested_term: PaymentTermSuggestion
    suggested_days: int
    suggested_skonto_percentage: float
    suggested_skonto_days: int
    expected_payment_date: datetime
    reasoning: str
    confidence: float


@dataclass
class CashFlowProjection:
    """Projizierter Cash-Flow."""
    projection_date: datetime
    days_ahead: int
    expected_inflow: float
    expected_inflow_min: float  # Pessimistisch
    expected_inflow_max: float  # Optimistisch
    expected_outflow: float
    net_flow: float
    cumulative_balance: float
    entity_contributions: List[Dict] = field(default_factory=list)


@dataclass
class PredictionFeedback:
    """Feedback fuer kontinuierliches Lernen."""
    prediction_id: str
    entity_id: UUID
    prediction_type: str  # "delay", "default", "terms"
    predicted_value: float
    actual_value: float
    feedback_timestamp: datetime = field(default_factory=utc_now)
    was_accurate: bool = False  # Innerhalb Toleranz


# =============================================================================
# Predictive Payment Service
# =============================================================================

class PredictivePaymentService:
    """
    Service fuer ML-basierte Zahlungsverhaltens-Vorhersagen.

    Features:
    - Zahlungsverzoegerung-Prognose pro Entity
    - Ausfallwahrscheinlichkeit
    - Dynamische Zahlungsziel-Empfehlungen
    - Cash-Flow-Projektion

    Integriert sich mit:
    - RiskScoringService (bestehende Risiko-Scores)
    - SkontoService (Skonto-Optimierung)
    - CashFlowService (Cash-Flow-Prognosen)
    - MLOps Pipeline (Model Registry, Retraining)
    """

    # Konfiguration
    MIN_INVOICES_FOR_PREDICTION = 3  # Mindestanzahl Rechnungen
    DEFAULT_DELAY_DAYS = 5.0  # Default wenn keine Historie
    DEFAULT_CONFIDENCE = 0.5

    # Model-Konfiguration (in Produktion aus ModelRegistry)
    MODEL_VERSION = "1.0.0"
    MODEL_TYPE = "payment_predictor"

    def __init__(self) -> None:
        """Initialisiere PredictivePaymentService."""
        # In Produktion: Model aus Registry laden
        self._model_loaded = False
        self._feature_cache: Dict[str, Tuple[PaymentFeatures, datetime]] = {}
        self._cache_ttl_seconds = 300  # 5 Minuten

    async def extract_features(
        self,
        db: AsyncSession,
        entity_id: UUID,
        use_cache: bool = True,
    ) -> PaymentFeatures:
        """
        Extrahiere Features fuer eine Entity.

        Args:
            db: Datenbank-Session
            entity_id: Geschaeftspartner-ID
            use_cache: Feature-Cache nutzen

        Returns:
            PaymentFeatures mit allen relevanten Metriken
        """
        cache_key = str(entity_id)

        # Cache pruefen
        if use_cache and cache_key in self._feature_cache:
            cached_features, cached_at = self._feature_cache[cache_key]
            if (utc_now() - cached_at).total_seconds() < self._cache_ttl_seconds:
                return cached_features

        features = PaymentFeatures(entity_id=entity_id)

        # Entity abrufen
        entity_result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()

        if not entity:
            logger.warning(
                "extract_features_entity_not_found",
                entity_id=str(entity_id),
            )
            return features

        # Beziehungsdauer berechnen
        if entity.first_document_date:
            features.first_invoice_date = entity.first_document_date
            age_delta = utc_now() - entity.first_document_date.replace(tzinfo=timezone.utc)
            features.relationship_age_days = age_delta.days

        # Industrie-Kategorie (falls vorhanden)
        features.industry_category = getattr(entity, 'industry', None)

        # Rechnungsdaten abrufen
        await self._extract_invoice_features(db, entity_id, features)

        # Cache aktualisieren
        self._feature_cache[cache_key] = (features, utc_now())

        return features

    async def _extract_invoice_features(
        self,
        db: AsyncSession,
        entity_id: UUID,
        features: PaymentFeatures,
    ) -> None:
        """Extrahiere Rechnungs-bezogene Features."""
        # Alle Rechnungen des Geschaeftspartners finden
        invoice_query = (
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )

        invoice_result = await db.execute(invoice_query)
        invoices = invoice_result.scalars().all()

        if not invoices:
            return

        features.total_invoices = len(invoices)
        now = utc_now()
        ninety_days_ago = now - timedelta(days=90)

        # Zahlungsverzoegerungen analysieren
        delay_days_list: List[float] = []
        paid_invoices: List[InvoiceTracking] = []
        total_volume = Decimal("0.00")
        volume_last_90_days = Decimal("0.00")
        outstanding_amount = Decimal("0.00")
        overdue_amount = Decimal("0.00")
        skonto_eligible = 0
        skonto_used = 0

        for inv in invoices:
            # Volumen berechnen
            if inv.amount:
                total_volume += Decimal(str(inv.amount))
                if inv.invoice_date and inv.invoice_date.replace(tzinfo=timezone.utc) >= ninety_days_ago:
                    volume_last_90_days += Decimal(str(inv.amount))

            # Status analysieren
            if inv.status == "paid":
                paid_invoices.append(inv)
                features.paid_invoices += 1

                # Zahlungsverzoegerung berechnen
                if inv.paid_at and inv.due_date:
                    paid_date = inv.paid_at.replace(tzinfo=None) if inv.paid_at.tzinfo else inv.paid_at
                    due_date = inv.due_date.replace(tzinfo=None) if inv.due_date.tzinfo else inv.due_date
                    delay = (paid_date - due_date).days
                    delay_days_list.append(float(delay))

                    # Letztes Zahlungsdatum
                    if features.last_payment_date is None or inv.paid_at > features.last_payment_date:
                        features.last_payment_date = inv.paid_at

            elif inv.status in ("overdue", "dunning"):
                features.overdue_invoices += 1
                if inv.outstanding_amount:
                    overdue_amount += Decimal(str(inv.outstanding_amount))
                elif inv.amount:
                    overdue_amount += Decimal(str(inv.amount))

            elif inv.status in ("open", "sent", "partial"):
                # Pruefen ob ueberfaellig
                due_utc = inv.due_date.replace(tzinfo=timezone.utc) if inv.due_date and not inv.due_date.tzinfo else inv.due_date
                if inv.outstanding_amount:
                    outstanding_amount += Decimal(str(inv.outstanding_amount))
                elif inv.amount:
                    outstanding_amount += Decimal(str(inv.amount))

                if due_utc and due_utc < now:
                    features.overdue_invoices += 1
                    overdue_amount += Decimal(str(inv.outstanding_amount or inv.amount or 0))

            # Skonto-Nutzung
            if inv.skonto_percentage and inv.skonto_percentage > 0:
                skonto_eligible += 1
                if inv.skonto_used:
                    skonto_used += 1

            # Mahnhistorie
            if inv.dunning_level and inv.dunning_level > 0:
                features.total_dunning_events += 1
                if inv.dunning_level > features.max_dunning_level_reached:
                    features.max_dunning_level_reached = inv.dunning_level

        # Statistische Berechnungen
        if delay_days_list:
            features.payment_history_avg_delay = sum(delay_days_list) / len(delay_days_list)
            if len(delay_days_list) > 1:
                mean = features.payment_history_avg_delay
                variance = sum((x - mean) ** 2 for x in delay_days_list) / len(delay_days_list)
                features.payment_history_std_delay = math.sqrt(variance)

        # Volumen
        features.invoice_volume_total = float(total_volume)
        features.invoice_volume_last_90_days = float(volume_last_90_days)

        # Ausstehend
        features.current_outstanding = float(outstanding_amount)
        features.current_overdue = float(overdue_amount)

        # Skonto-Nutzungsrate
        if skonto_eligible > 0:
            features.skonto_usage_rate = skonto_used / skonto_eligible

    async def predict_payment_delay(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> PaymentDelayPrediction:
        """
        Prognostiziere Zahlungsverzoegerung fuer eine Entity.

        Args:
            db: Datenbank-Session
            entity_id: Geschaeftspartner-ID

        Returns:
            PaymentDelayPrediction mit Vorhersage und Konfidenz
        """
        features = await self.extract_features(db, entity_id)

        # Pruefen ob genuegend Daten vorhanden
        if features.paid_invoices < self.MIN_INVOICES_FOR_PREDICTION:
            # Fallback auf Default mit niedriger Konfidenz
            return PaymentDelayPrediction(
                entity_id=entity_id,
                predicted_delay_days=self.DEFAULT_DELAY_DAYS,
                confidence=0.3,
                risk_tier=RiskTier.MEDIUM,
                delay_range_min=0.0,
                delay_range_max=14.0,
                top_factors=[("insufficient_data", 1.0)],
            )

        # Feature-basierte Vorhersage
        predicted_delay = self._calculate_delay_prediction(features)

        # Konfidenz basierend auf Datenmenge und Konsistenz
        confidence = self._calculate_prediction_confidence(features)

        # Range basierend auf Standardabweichung
        std_dev = features.payment_history_std_delay or 5.0
        delay_range_min = max(0, predicted_delay - std_dev)
        delay_range_max = predicted_delay + std_dev * 1.5

        # Risiko-Tier bestimmen
        risk_tier = self._classify_delay_risk(predicted_delay)

        # Top-Faktoren fuer Erklaerbarkeit
        top_factors = self._get_top_delay_factors(features, predicted_delay)

        prediction = PaymentDelayPrediction(
            entity_id=entity_id,
            predicted_delay_days=round(predicted_delay, 1),
            confidence=round(confidence, 2),
            risk_tier=risk_tier,
            delay_range_min=round(delay_range_min, 1),
            delay_range_max=round(delay_range_max, 1),
            top_factors=top_factors,
        )

        # SECURITY: Keine Entity-Namen loggen
        logger.info(
            "payment_delay_predicted",
            entity_id=str(entity_id),
            predicted_delay=prediction.predicted_delay_days,
            confidence=prediction.confidence,
            risk_tier=prediction.risk_tier.value,
        )

        return prediction

    def _calculate_delay_prediction(self, features: PaymentFeatures) -> float:
        """Berechne erwartete Zahlungsverzoegerung."""
        # Basis: historischer Durchschnitt
        base_delay = features.payment_history_avg_delay

        # Saisonaler Faktor
        current_month = utc_now().month
        seasonal_factor = SEASONAL_DELAY_FACTORS.get(current_month, 1.0)

        # Volumen-Faktor (hoehere Volumen = zuverlaessiger)
        volume_factor = 1.0
        if features.invoice_volume_total > 50000:
            volume_factor = 0.9
        elif features.invoice_volume_total < 5000:
            volume_factor = 1.1

        # Beziehungs-Faktor (laengere Beziehung = stabiler)
        relationship_factor = 1.0
        if features.relationship_age_days > 365:
            relationship_factor = 0.95
        elif features.relationship_age_days < 90:
            relationship_factor = 1.1

        # Ausstehende Betraege-Faktor
        outstanding_factor = 1.0
        if features.current_outstanding > 10000:
            outstanding_factor = 1.15
        if features.current_overdue > 0:
            outstanding_factor += 0.1

        # Mahn-Historie-Faktor
        dunning_factor = 1.0 + (features.max_dunning_level_reached * 0.1)

        # Kombinierte Vorhersage
        predicted_delay = (
            base_delay
            * seasonal_factor
            * volume_factor
            * relationship_factor
            * outstanding_factor
            * dunning_factor
        )

        return max(0, predicted_delay)

    def _calculate_prediction_confidence(self, features: PaymentFeatures) -> float:
        """Berechne Konfidenz der Vorhersage."""
        confidence = 0.5  # Basis

        # Mehr Daten = hoehere Konfidenz
        if features.paid_invoices >= 10:
            confidence += 0.2
        elif features.paid_invoices >= 5:
            confidence += 0.1

        # Niedrigere Standardabweichung = konsistenteres Verhalten = hoehere Konfidenz
        if features.payment_history_std_delay < 3:
            confidence += 0.15
        elif features.payment_history_std_delay > 10:
            confidence -= 0.1

        # Laengere Beziehung = mehr Vertrauen
        if features.relationship_age_days > 365:
            confidence += 0.1

        # Aktuelle Aktivitaet (letzte 90 Tage)
        if features.invoice_volume_last_90_days > 0:
            confidence += 0.05

        return min(0.95, max(0.3, confidence))

    def _classify_delay_risk(self, delay_days: float) -> RiskTier:
        """Klassifiziere Risiko basierend auf Verzoegerung."""
        if delay_days <= 3:
            return RiskTier.LOW
        elif delay_days <= 10:
            return RiskTier.MEDIUM
        elif delay_days <= 20:
            return RiskTier.HIGH
        else:
            return RiskTier.CRITICAL

    def _get_top_delay_factors(
        self,
        features: PaymentFeatures,
        predicted_delay: float,
    ) -> List[Tuple[str, float]]:
        """Identifiziere wichtigste Faktoren fuer die Vorhersage."""
        factors: List[Tuple[str, float]] = []

        # Historische Verzoegerung
        if features.payment_history_avg_delay > 0:
            factors.append((
                "historical_payment_behavior",
                min(1.0, features.payment_history_avg_delay / 30),
            ))

        # Mahnhistorie
        if features.max_dunning_level_reached > 0:
            factors.append((
                "dunning_history",
                min(1.0, features.max_dunning_level_reached / 4),
            ))

        # Aktuelle ueberfaellige Betraege
        if features.current_overdue > 0:
            factors.append((
                "current_overdue_balance",
                min(1.0, features.current_overdue / 10000),
            ))

        # Beziehungsdauer
        if features.relationship_age_days < 180:
            factors.append((
                "short_relationship",
                1.0 - (features.relationship_age_days / 180),
            ))

        # Sortieren nach Wichtigkeit
        factors.sort(key=lambda x: x[1], reverse=True)
        return factors[:5]

    async def predict_default_probability(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> DefaultProbabilityPrediction:
        """
        Prognostiziere Ausfallwahrscheinlichkeit fuer eine Entity.

        Args:
            db: Datenbank-Session
            entity_id: Geschaeftspartner-ID

        Returns:
            DefaultProbabilityPrediction (0-1)
        """
        features = await self.extract_features(db, entity_id)

        # Basis-Wahrscheinlichkeit
        default_prob = 0.05  # 5% Baseline

        contributing_factors: Dict[str, float] = {}

        # Faktor: Aktuelle Ueberfaelligkeitsrate
        if features.total_invoices > 0:
            overdue_rate = features.overdue_invoices / features.total_invoices
            overdue_contribution = overdue_rate * 0.4
            default_prob += overdue_contribution
            if overdue_rate > 0:
                contributing_factors["overdue_rate"] = round(overdue_rate, 2)

        # Faktor: Mahnhistorie (hoechste Mahnstufe)
        if features.max_dunning_level_reached >= 3:
            dunning_contribution = 0.25
            default_prob += dunning_contribution
            contributing_factors["high_dunning_level"] = features.max_dunning_level_reached

        elif features.max_dunning_level_reached >= 2:
            default_prob += 0.1
            contributing_factors["dunning_level"] = features.max_dunning_level_reached

        # Faktor: Durchschnittliche Verzoegerung
        if features.payment_history_avg_delay > 30:
            delay_contribution = 0.15
            default_prob += delay_contribution
            contributing_factors["chronic_late_payment"] = round(features.payment_history_avg_delay, 1)

        elif features.payment_history_avg_delay > 14:
            default_prob += 0.05
            contributing_factors["moderate_delay"] = round(features.payment_history_avg_delay, 1)

        # Faktor: Kurze Beziehungsdauer mit Problemen
        if features.relationship_age_days < 180 and features.overdue_invoices > 0:
            default_prob += 0.1
            contributing_factors["new_customer_issues"] = True

        # Faktor: Hohe ausstehende Betraege relativ zum Volumen
        if features.invoice_volume_total > 0:
            outstanding_ratio = features.current_outstanding / features.invoice_volume_total
            if outstanding_ratio > 0.5:
                default_prob += 0.1
                contributing_factors["high_outstanding_ratio"] = round(outstanding_ratio, 2)

        # Faktor: Skonto-Nutzung (positiv)
        if features.skonto_usage_rate > 0.7:
            default_prob -= 0.03  # Reduziert Risiko
            contributing_factors["skonto_user"] = round(features.skonto_usage_rate, 2)

        # Grenzen einhalten
        default_prob = max(0.01, min(0.95, default_prob))

        # Konfidenz
        confidence = self._calculate_prediction_confidence(features)

        # Risiko-Tier
        if default_prob < 0.1:
            risk_tier = RiskTier.LOW
        elif default_prob < 0.25:
            risk_tier = RiskTier.MEDIUM
        elif default_prob < 0.5:
            risk_tier = RiskTier.HIGH
        else:
            risk_tier = RiskTier.CRITICAL

        prediction = DefaultProbabilityPrediction(
            entity_id=entity_id,
            default_probability=round(default_prob, 3),
            confidence=round(confidence, 2),
            risk_tier=risk_tier,
            contributing_factors=contributing_factors,
        )

        logger.info(
            "default_probability_predicted",
            entity_id=str(entity_id),
            probability=prediction.default_probability,
            risk_tier=prediction.risk_tier.value,
        )

        return prediction

    async def suggest_payment_terms(
        self,
        db: AsyncSession,
        entity_id: UUID,
        invoice_amount: float,
    ) -> PaymentTermsSuggestion:
        """
        Empfehle optimale Zahlungsbedingungen fuer eine Entity.

        Beruecksichtigt:
        - Historisches Zahlungsverhalten
        - Risikoniveau
        - Rechnungsbetrag
        - Geschaeftsbeziehung

        Args:
            db: Datenbank-Session
            entity_id: Geschaeftspartner-ID
            invoice_amount: Rechnungsbetrag in EUR

        Returns:
            PaymentTermsSuggestion mit Empfehlung
        """
        # Hole Vorhersagen
        delay_prediction = await self.predict_payment_delay(db, entity_id)
        default_prediction = await self.predict_default_probability(db, entity_id)
        features = await self.extract_features(db, entity_id)

        # Basis-Empfehlung: NET_30
        suggested_term = PaymentTermSuggestion.NET_30
        suggested_days = 30
        suggested_skonto = 2.0
        suggested_skonto_days = 10
        reasoning_parts: List[str] = []

        # Anpassung basierend auf Risiko
        if default_prediction.risk_tier == RiskTier.CRITICAL:
            suggested_term = PaymentTermSuggestion.PREPAYMENT
            suggested_days = 0
            suggested_skonto = 0.0
            suggested_skonto_days = 0
            reasoning_parts.append("Kritisches Risiko: Vorkasse empfohlen")

        elif default_prediction.risk_tier == RiskTier.HIGH:
            if invoice_amount > 5000:
                suggested_term = PaymentTermSuggestion.PREPAYMENT
                suggested_days = 0
                reasoning_parts.append("Hohes Risiko bei hohem Betrag: Vorkasse")
            else:
                suggested_term = PaymentTermSuggestion.NET_7
                suggested_days = 7
                reasoning_parts.append("Hohes Risiko: Kurze Zahlungsfrist")

        elif default_prediction.risk_tier == RiskTier.MEDIUM:
            suggested_term = PaymentTermSuggestion.NET_14
            suggested_days = 14
            suggested_skonto = 2.5
            suggested_skonto_days = 7
            reasoning_parts.append("Mittleres Risiko: Verkuerzte Frist mit Skonto-Anreiz")

        elif default_prediction.risk_tier == RiskTier.LOW:
            # Langjahrige, zuverlaessige Kunden bekommen bessere Konditionen
            if features.relationship_age_days > 730 and features.skonto_usage_rate > 0.5:
                suggested_term = PaymentTermSuggestion.NET_45
                suggested_days = 45
                suggested_skonto = 3.0
                suggested_skonto_days = 14
                reasoning_parts.append("Langjaerige Beziehung, zuverlaessiger Zahler: Erweiterte Frist")
            elif features.relationship_age_days > 365:
                suggested_term = PaymentTermSuggestion.NET_30
                suggested_days = 30
                suggested_skonto = 2.5
                suggested_skonto_days = 10
                reasoning_parts.append("Etablierter Kunde: Standard-Konditionen")
            else:
                suggested_term = PaymentTermSuggestion.NET_30
                suggested_days = 30
                reasoning_parts.append("Niedriges Risiko: Standard-Konditionen")

        # Anpassung basierend auf Rechnungsbetrag
        if invoice_amount > 20000 and suggested_term not in [PaymentTermSuggestion.PREPAYMENT, PaymentTermSuggestion.IMMEDIATE]:
            # Bei hohen Betraegen: Ratenzahlung anbieten
            if delay_prediction.risk_tier in [RiskTier.LOW, RiskTier.MEDIUM]:
                reasoning_parts.append("Hoher Betrag: Ratenzahlung moeglich")
            else:
                # Kuerze Frist bei hohem Betrag und Risiko
                if suggested_days > 14:
                    suggested_days = 14
                    suggested_term = PaymentTermSuggestion.NET_14
                    reasoning_parts.append("Hoher Betrag mit Risiko: Verkuerzte Frist")

        # Skonto-Optimierung basierend auf Skonto-Nutzungsrate
        if features.skonto_usage_rate > 0.8:
            # Kunde nutzt Skonto haeufig - attraktives Angebot machen
            suggested_skonto = min(3.5, suggested_skonto + 0.5)
            reasoning_parts.append("Skonto-affiner Kunde: Erhoehter Skonto-Anreiz")
        elif features.skonto_usage_rate < 0.2:
            # Kunde nutzt Skonto selten - reduzieren
            suggested_skonto = max(1.5, suggested_skonto - 0.5)

        # Erwartetes Zahlungsdatum berechnen
        expected_delay = delay_prediction.predicted_delay_days
        expected_payment_date = utc_now() + timedelta(days=suggested_days + expected_delay)

        # Konfidenz kombinieren
        combined_confidence = (delay_prediction.confidence + default_prediction.confidence) / 2

        suggestion = PaymentTermsSuggestion(
            entity_id=entity_id,
            invoice_amount=invoice_amount,
            suggested_term=suggested_term,
            suggested_days=suggested_days,
            suggested_skonto_percentage=suggested_skonto,
            suggested_skonto_days=suggested_skonto_days,
            expected_payment_date=expected_payment_date,
            reasoning="; ".join(reasoning_parts),
            confidence=round(combined_confidence, 2),
        )

        logger.info(
            "payment_terms_suggested",
            entity_id=str(entity_id),
            invoice_amount=invoice_amount,
            suggested_term=suggestion.suggested_term.value,
            suggested_days=suggestion.suggested_days,
        )

        return suggestion

    async def calculate_expected_cash_flow(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 30,
    ) -> List[CashFlowProjection]:
        """
        Projiziere Cash-Flow basierend auf ML-Vorhersagen.

        Beruecksichtigt:
        - Offene Rechnungen mit Faelligkeiten
        - Vorhergesagte Zahlungsverzoegerungen pro Entity
        - Ausfallwahrscheinlichkeiten

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            days_ahead: Tage in die Zukunft

        Returns:
            Liste von CashFlowProjection pro Tag
        """
        now = utc_now()
        end_date = now + timedelta(days=days_ahead)

        # Hole alle offenen Rechnungen (SECURITY: company_id Filter)
        invoice_query = (
            select(InvoiceTracking, Document)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["open", "sent", "partial", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )

        invoice_result = await db.execute(invoice_query)
        invoices = invoice_result.all()

        # Gruppiere Zahlungen pro Tag
        daily_projections: Dict[int, Dict] = {}
        for day_offset in range(days_ahead + 1):
            daily_projections[day_offset] = {
                "expected_inflow": 0.0,
                "expected_inflow_min": 0.0,
                "expected_inflow_max": 0.0,
                "entity_contributions": [],
            }

        # Cache fuer Entity-Vorhersagen
        entity_predictions: Dict[str, Tuple[PaymentDelayPrediction, DefaultProbabilityPrediction]] = {}

        for invoice, document in invoices:
            entity_id = document.business_entity_id
            if not entity_id:
                continue

            entity_key = str(entity_id)

            # Hole/Cache Entity-Vorhersagen
            if entity_key not in entity_predictions:
                delay_pred = await self.predict_payment_delay(db, entity_id)
                default_pred = await self.predict_default_probability(db, entity_id)
                entity_predictions[entity_key] = (delay_pred, default_pred)

            delay_pred, default_pred = entity_predictions[entity_key]

            # Erwartetes Zahlungsdatum berechnen
            due_date = invoice.due_date
            if not due_date:
                due_date = now + timedelta(days=14)  # Default

            due_date = due_date.replace(tzinfo=timezone.utc) if not due_date.tzinfo else due_date

            # Vorhergesagtes Zahlungsdatum
            expected_payment_date = due_date + timedelta(days=delay_pred.predicted_delay_days)

            # Welcher Tag in der Projektion?
            days_from_now = (expected_payment_date - now).days
            if days_from_now < 0:
                days_from_now = 0
            if days_from_now > days_ahead:
                days_from_now = days_ahead

            # Ausstehender Betrag
            outstanding = float(invoice.outstanding_amount or invoice.amount or 0)
            if outstanding <= 0:
                continue

            # Erwarteter Eingang unter Beruecksichtigung der Ausfallwahrscheinlichkeit
            probability_of_payment = 1.0 - default_pred.default_probability
            expected_amount = outstanding * probability_of_payment

            # Optimistisch/Pessimistisch
            optimistic_amount = outstanding * (1.0 - default_pred.default_probability * 0.5)
            pessimistic_amount = outstanding * (1.0 - default_pred.default_probability * 2.0)
            pessimistic_amount = max(0, pessimistic_amount)

            # Zur Projektion hinzufuegen
            daily_projections[days_from_now]["expected_inflow"] += expected_amount
            daily_projections[days_from_now]["expected_inflow_min"] += pessimistic_amount
            daily_projections[days_from_now]["expected_inflow_max"] += optimistic_amount
            daily_projections[days_from_now]["entity_contributions"].append({
                "entity_id": entity_key,
                "invoice_id": str(invoice.id),
                "amount": outstanding,
                "expected_amount": expected_amount,
                "probability": probability_of_payment,
            })

        # Konvertiere zu Liste von CashFlowProjection
        projections: List[CashFlowProjection] = []
        cumulative_balance = 0.0

        for day_offset in range(days_ahead + 1):
            day_data = daily_projections[day_offset]
            expected_inflow = day_data["expected_inflow"]
            expected_outflow = 0.0  # Hier koennten Verbindlichkeiten einfliessen
            net_flow = expected_inflow - expected_outflow
            cumulative_balance += net_flow

            projections.append(CashFlowProjection(
                projection_date=now + timedelta(days=day_offset),
                days_ahead=day_offset,
                expected_inflow=round(expected_inflow, 2),
                expected_inflow_min=round(day_data["expected_inflow_min"], 2),
                expected_inflow_max=round(day_data["expected_inflow_max"], 2),
                expected_outflow=expected_outflow,
                net_flow=round(net_flow, 2),
                cumulative_balance=round(cumulative_balance, 2),
                entity_contributions=day_data["entity_contributions"],
            ))

        logger.info(
            "cash_flow_projected",
            company_id=str(company_id),
            days_ahead=days_ahead,
            total_expected_inflow=sum(p.expected_inflow for p in projections),
        )

        return projections

    async def record_prediction_feedback(
        self,
        db: AsyncSession,
        feedback: PredictionFeedback,
    ) -> None:
        """
        Erfasse Feedback fuer kontinuierliches Lernen.

        Wird aufgerufen wenn tatsaechliche Zahlungen erfolgen,
        um Vorhersage-Genauigkeit zu tracken.

        Args:
            db: Datenbank-Session
            feedback: Feedback-Objekt
        """
        # Genauigkeit pruefen
        if feedback.prediction_type == "delay":
            # Toleranz: +/- 3 Tage
            feedback.was_accurate = abs(feedback.predicted_value - feedback.actual_value) <= 3
        elif feedback.prediction_type == "default":
            # Bei Default-Vorhersage: War die Vorhersage "hoch" und ist ausgefallen oder umgekehrt
            predicted_default = feedback.predicted_value > 0.5
            actual_default = feedback.actual_value > 0
            feedback.was_accurate = predicted_default == actual_default

        # In Produktion: Speichern fuer Retraining
        logger.info(
            "prediction_feedback_recorded",
            entity_id=str(feedback.entity_id),
            prediction_type=feedback.prediction_type,
            predicted=round(feedback.predicted_value, 2),
            actual=round(feedback.actual_value, 2),
            was_accurate=feedback.was_accurate,
        )

        # TODO: Speichern in DB fuer MLOps Retraining Pipeline
        # Dies wuerde ueber OCRCorrectionFeedback-aehnliche Tabelle erfolgen

    def clear_feature_cache(self, entity_id: Optional[UUID] = None) -> None:
        """Loesche Feature-Cache (fuer Tests oder nach Updates)."""
        if entity_id:
            cache_key = str(entity_id)
            self._feature_cache.pop(cache_key, None)
        else:
            self._feature_cache.clear()


# =============================================================================
# Singleton
# =============================================================================

_predictive_payment_service: Optional[PredictivePaymentService] = None


def get_predictive_payment_service() -> PredictivePaymentService:
    """Returns singleton instance of PredictivePaymentService."""
    global _predictive_payment_service
    if _predictive_payment_service is None:
        _predictive_payment_service = PredictivePaymentService()
    return _predictive_payment_service
