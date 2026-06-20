# -*- coding: utf-8 -*-
"""
SmartDunningService - Intelligentes Mahnwesen mit KI-Unterstützung.

Features:
- Optimales Mahntiming basierend auf Kundenhistorie
- Personalisierte Mahntexte via Ollama (deutsch)
- A/B-Testing von Mahnstrategien
- Erfolgstracking pro Strategie
- Zahlungsvorhersage basierend auf Kundenverhalten

On-Premises: Nutzt ausschließlich lokales Ollama (keine Cloud-LLMs).

Feinpoliert und durchdacht - Enterprise Dunning Intelligence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set, Union

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    AppConfig,
)
from app.services.ai.ollama_service import OllamaService, get_ollama_service
from app.services.risk_scoring_service import (
    RiskScoringService,
    RiskFactors,
    TrendDirection,
    get_risk_scoring_service,
)
from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Type aliases
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]


# =============================================================================
# Prometheus Metriken
# =============================================================================

DUNNING_GENERATED = Counter(
    "smart_dunning_generated_total",
    "Anzahl generierter Mahntexte",
    ["dunning_level", "strategy", "tone"]
)

DUNNING_SENT = Counter(
    "smart_dunning_sent_total",
    "Anzahl versendeter Mahnungen",
    ["dunning_level", "strategy"]
)

DUNNING_SUCCESS = Counter(
    "smart_dunning_success_total",
    "Anzahl erfolgreicher Mahnungen (führten zu Zahlung)",
    ["dunning_level", "strategy"]
)

DUNNING_PREDICTION_ACCURACY = Gauge(
    "smart_dunning_prediction_accuracy",
    "Genauigkeit der Zahlungsvorhersage",
    ["prediction_type"]
)

AB_TEST_CONVERSION = Gauge(
    "smart_dunning_ab_test_conversion",
    "Conversion Rate pro A/B Test Variante",
    ["test_id", "variant"]
)

DUNNING_TEXT_GENERATION_DURATION = Histogram(
    "smart_dunning_text_generation_seconds",
    "Dauer der Mahntext-Generierung",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)


# =============================================================================
# Enums und Konstanten
# =============================================================================

class DunningLevel(int, Enum):
    """Mahnstufen."""
    REMINDER = 0  # Freundliche Zahlungserinnerung
    FIRST = 1     # 1. Mahnung
    SECOND = 2    # 2. Mahnung
    FINAL = 3     # Letzte Mahnung vor Inkasso
    INKASSO = 4   # Übergabe an Inkasso


class DunningTone(str, Enum):
    """Tonfall der Mahnung."""
    FRIENDLY = "friendly"       # Freundlich
    NEUTRAL = "neutral"         # Sachlich/Neutral
    FIRM = "firm"               # Bestimmt
    URGENT = "urgent"           # Dringend
    FINAL = "final"             # Letztmalig


class DunningStrategy(str, Enum):
    """Mahnstrategie."""
    STANDARD = "standard"           # Standard-Ablauf
    RELATIONSHIP = "relationship"   # Beziehungsorientiert
    FINANCIAL = "financial"         # Finanzdruck-orientiert
    LEGAL = "legal"                 # Rechtliche Konsequenzen
    ESCALATION = "escalation"       # Schnelle Eskalation


class PaymentLikelihood(str, Enum):
    """Zahlungswahrscheinlichkeit."""
    HIGH = "high"       # >75% - Zahlung wahrscheinlich
    MEDIUM = "medium"   # 40-75% - Unsicher
    LOW = "low"         # <40% - Zahlung unwahrscheinlich


class CustomerSegment(str, Enum):
    """Kundensegment für Personalisierung."""
    VIP = "vip"                 # Langjaeahrige Top-Kunden
    GOOD = "good"               # Gute Zahlungshistorie
    NORMAL = "normal"           # Durchschnitt
    RISKY = "risky"             # Erhöhtes Risiko
    PROBLEMATIC = "problematic" # Chronisch späte Zahler


# Deutsche Mahnstufen-Labels
DUNNING_LEVEL_LABELS_DE: Dict[DunningLevel, str] = {
    DunningLevel.REMINDER: "Zahlungserinnerung",
    DunningLevel.FIRST: "1. Mahnung",
    DunningLevel.SECOND: "2. Mahnung",
    DunningLevel.FINAL: "Letzte Mahnung",
    DunningLevel.INKASSO: "Inkasso-Ankündigung",
}

# Standard-Wartezeiten zwischen Mahnstufen (Tage)
DEFAULT_WAITING_PERIODS: Dict[DunningLevel, int] = {
    DunningLevel.REMINDER: 7,   # 7 Tage nach Fälligkeit
    DunningLevel.FIRST: 14,     # 14 Tage nach Erinnerung
    DunningLevel.SECOND: 14,    # 14 Tage nach 1. Mahnung
    DunningLevel.FINAL: 7,      # 7 Tage nach 2. Mahnung
    DunningLevel.INKASSO: 14,   # 14 Tage nach letzter Mahnung
}


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class DunningText:
    """Generierter Mahntext."""
    subject: str
    greeting: str
    body: str
    closing: str
    full_text: str
    tone: DunningTone
    dunning_level: DunningLevel
    strategy: DunningStrategy
    personalization_factors: List[str]
    generation_time_ms: int


@dataclass
class DunningTiming:
    """Optimales Mahntiming."""
    recommended_date: datetime
    days_from_now: int
    reasoning: str
    confidence: float
    factors: JSONDict


@dataclass
class PaymentPrediction:
    """Zahlungsvorhersage."""
    likelihood: PaymentLikelihood
    probability: float  # 0.0-1.0
    expected_payment_date: Optional[datetime]
    expected_delay_days: int
    factors: JSONDict
    recommendations: List[str]


@dataclass
class CustomerProfile:
    """Kundenprofil für Personalisierung."""
    entity_id: uuid.UUID
    segment: CustomerSegment
    avg_payment_delay: float
    payment_trend: TrendDirection
    total_invoices: int
    open_invoices: int
    relationship_months: float
    last_payment_date: Optional[datetime]
    preferred_communication: Optional[str]
    language: str = "de"


@dataclass
class ABTestVariant:
    """A/B Test Variante."""
    variant_id: str
    strategy: DunningStrategy
    tone: DunningTone
    waiting_period_modifier: float  # 1.0 = Standard, 0.8 = 20% schneller
    sample_count: int
    success_count: int
    conversion_rate: float


@dataclass
class ABTest:
    """A/B Test Definition."""
    test_id: str
    name: str
    description: str
    variants: List[ABTestVariant]
    is_active: bool
    start_date: datetime
    end_date: Optional[datetime]
    dunning_level: DunningLevel
    created_at: datetime


@dataclass
class DunningResult:
    """Ergebnis einer Mahnungs-Aktion."""
    invoice_id: uuid.UUID
    dunning_level: DunningLevel
    text: DunningText
    timing: DunningTiming
    prediction: PaymentPrediction
    ab_test_variant: Optional[str]


# =============================================================================
# LLM Prompt Templates
# =============================================================================

DUNNING_TEXT_SYSTEM_PROMPT = """Du bist ein Experte für professionelle Geschäftskommunikation in Deutschland.
Deine Aufgabe ist es, Mahntexte zu erstellen, die:
1. Professionell und respektvoll sind
2. Klar und eindeutig formuliert sind
3. Rechtlich korrekt sind (deutsches Mahnrecht)
4. Den gewünschten Tonfall treffen
5. Die Kundenbeziehung berücksichtigen

WICHTIG:
- Alle Texte auf Deutsch
- Keine Drohungen oder Beleidigungen
- Korrekte Anrede und Grussformel
- Konkrete Zahlungsinformationen einbinden
- Bei höheren Mahnstufen rechtliche Konsequenzen erwaehnen
"""

DUNNING_TEXT_USER_PROMPT = """Erstelle einen Mahntext mit folgenden Parametern:

RECHNUNGSDATEN:
- Rechnungsnummer: {invoice_number}
- Rechnungsdatum: {invoice_date}
- Fälligkeitsdatum: {due_date}
- Betrag: {amount} {currency}
- Tage überfällig: {days_overdue}

MAHNSTUFE: {dunning_level} ({dunning_level_de})

TONFALL: {tone} ({tone_description})

KUNDENPROFIL:
- Segment: {customer_segment}
- Geschäftsbeziehung: {relationship_months} Monate
- Zahlungsverhalten: {payment_behavior}
- Offene Rechnungen: {open_invoices}

STRATEGIE: {strategy}

BESONDERE HINWEISE:
{special_instructions}

Antworte im folgenden JSON-Format:
{{
    "subject": "Betreff der E-Mail/des Briefs",
    "greeting": "Anrede",
    "body": "Haupttext (2-4 Absätze)",
    "closing": "Grussformel mit Unterschrift"
}}
"""

PAYMENT_PREDICTION_PROMPT = """Basierend auf dem Kundenprofil, schätze die Zahlungswahrscheinlichkeit:

KUNDENDATEN:
- Durchschnittliche Zahlungsverzögerung: {avg_delay} Tage
- Zahlungstrend: {trend}
- Gesamte Rechnungen: {total_invoices}
- Offene Rechnungen: {open_invoices}
- Überfällige Rechnungen: {overdue_invoices}
- Geschäftsbeziehung: {relationship_months} Monate
- Risiko-Score: {risk_score}

AKTUELLE RECHNUNG:
- Betrag: {amount} {currency}
- Tage überfällig: {days_overdue}
- Aktuelle Mahnstufe: {dunning_level}

Antworte im JSON-Format:
{{
    "likelihood": "high|medium|low",
    "probability": 0.0-1.0,
    "expected_delay_days": Zahl,
    "reasoning": "Begruendung auf Deutsch",
    "recommendations": ["Empfehlung 1", "Empfehlung 2"]
}}
"""


# =============================================================================
# Tone Descriptions
# =============================================================================

TONE_DESCRIPTIONS: Dict[DunningTone, str] = {
    DunningTone.FRIENDLY: "Freundlich und verstaendnisvoll, möglicher Zahlungsverzug wird als Versehen behandelt",
    DunningTone.NEUTRAL: "Sachlich und professionell, ohne emotionale Wertung",
    DunningTone.FIRM: "Bestimmt und klar, mit Nachdruck auf Zahlungspflicht",
    DunningTone.URGENT: "Dringend, mit Hinweis auf zeitkritische Konsequenzen",
    DunningTone.FINAL: "Letztmalige Aufforderung mit Ankündigung rechtlicher Schritte",
}


# =============================================================================
# Service Implementation
# =============================================================================

class SmartDunningService:
    """
    Intelligentes Mahnwesen mit KI-Unterstützung.

    Features:
    - Personalisierte Mahntexte via Ollama
    - Optimales Timing basierend auf Kundenhistorie
    - A/B-Testing von Strategien
    - Zahlungsvorhersage
    - Erfolgs-Tracking
    """

    # AppConfig Keys
    AB_TESTS_KEY = "smart_dunning_ab_tests"
    STRATEGY_STATS_KEY = "smart_dunning_strategy_stats"
    CUSTOMER_PREFS_KEY = "smart_dunning_customer_prefs"

    # Konfiguration
    LLM_TIMEOUT_SECONDS = 30
    MIN_HISTORY_FOR_PREDICTION = 3  # Mindest-Rechnungen für Vorhersage

    def __init__(
        self,
        ollama_service: Optional[OllamaService] = None,
        risk_service: Optional[RiskScoringService] = None,
    ) -> None:
        """
        Initialisiert den Smart Dunning Service.

        Args:
            ollama_service: Optionaler Ollama Service
            risk_service: Optionaler Risk Scoring Service
        """
        self._ollama = ollama_service
        self._risk_service = risk_service
        self._ab_tests: Dict[str, ABTest] = {}
        self._strategy_stats: Dict[str, Dict[str, int]] = {}

    @property
    def ollama(self) -> OllamaService:
        """Lazy-loaded Ollama Service."""
        if self._ollama is None:
            self._ollama = get_ollama_service()
        return self._ollama

    @property
    def risk_service(self) -> RiskScoringService:
        """Lazy-loaded Risk Scoring Service."""
        if self._risk_service is None:
            self._risk_service = get_risk_scoring_service()
        return self._risk_service

    # =========================================================================
    # Customer Profile
    # =========================================================================

    async def get_customer_profile(
        self,
        db: AsyncSession,
        entity_id: uuid.UUID,
    ) -> Optional[CustomerProfile]:
        """
        Erstellt Kundenprofil für Personalisierung.

        Args:
            db: Database Session
            entity_id: Geschäftspartner-ID

        Returns:
            CustomerProfile oder None
        """
        # Entity laden
        entity_result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()

        if not entity:
            return None

        # Risk Score berechnen
        risk_score, payment_score, factors = await self.risk_service.calculate_risk_score(
            db, entity_id
        )

        # Segment bestimmen
        segment = self._determine_segment(payment_score, factors)

        # Letzte Zahlung finden
        last_payment_query = (
            select(InvoiceTracking.paid_at)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at.isnot(None),
                )
            )
            .order_by(InvoiceTracking.paid_at.desc())
            .limit(1)
        )
        last_payment_result = await db.execute(last_payment_query)
        last_payment = last_payment_result.scalar_one_or_none()

        return CustomerProfile(
            entity_id=entity_id,
            segment=segment,
            avg_payment_delay=factors.payment_delay_days,
            payment_trend=factors.payment_trend,
            total_invoices=factors.total_invoices,
            open_invoices=factors.open_invoices,
            relationship_months=factors.relationship_months,
            last_payment_date=last_payment,
            preferred_communication=None,  # Könnte aus Entity-Metadaten kommen
            language="de",
        )

    def _determine_segment(
        self,
        payment_score: float,
        factors: RiskFactors,
    ) -> CustomerSegment:
        """Bestimmt Kundensegment basierend auf Zahlungsverhalten."""
        if payment_score >= 90 and factors.relationship_months >= 24:
            return CustomerSegment.VIP
        elif payment_score >= 80:
            return CustomerSegment.GOOD
        elif payment_score >= 60:
            return CustomerSegment.NORMAL
        elif payment_score >= 40:
            return CustomerSegment.RISKY
        else:
            return CustomerSegment.PROBLEMATIC

    # =========================================================================
    # Optimal Timing
    # =========================================================================

    async def predict_optimal_timing(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
        dunning_level: DunningLevel,
    ) -> DunningTiming:
        """
        Berechnet optimalen Zeitpunkt für Mahnung.

        Args:
            db: Database Session
            invoice_id: Rechnungs-ID
            dunning_level: Mahnstufe

        Returns:
            DunningTiming mit Empfehlung
        """
        # Rechnung laden
        invoice_result = await db.execute(
            select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if not invoice:
            # Fallback auf Standard-Timing
            default_days = DEFAULT_WAITING_PERIODS.get(dunning_level, 14)
            return DunningTiming(
                recommended_date=datetime.now(timezone.utc) + timedelta(days=default_days),
                days_from_now=default_days,
                reasoning="Keine Rechnungsdaten verfügbar - Standard-Timing",
                confidence=0.5,
                factors={},
            )

        # Entity laden
        doc_result = await db.execute(
            select(Document.business_entity_id)
            .where(Document.id == invoice.document_id)
        )
        entity_id = doc_result.scalar_one_or_none()

        factors: JSONDict = {
            "invoice_amount": invoice.amount,
            "days_overdue": 0,
            "dunning_level": dunning_level.value,
        }

        # Tage überfällig berechnen
        if invoice.due_date:
            due_date = invoice.due_date.replace(tzinfo=timezone.utc) if invoice.due_date.tzinfo is None else invoice.due_date
            days_overdue = (datetime.now(timezone.utc) - due_date).days
            factors["days_overdue"] = max(0, days_overdue)

        # Basis-Wartezeit
        base_days = DEFAULT_WAITING_PERIODS.get(dunning_level, 14)

        if entity_id:
            profile = await self.get_customer_profile(db, entity_id)
            if profile:
                factors["customer_segment"] = profile.segment.value
                factors["avg_payment_delay"] = profile.avg_payment_delay
                factors["payment_trend"] = profile.payment_trend.value

                # Timing anpassen basierend auf Profil
                base_days = self._adjust_timing_by_profile(base_days, profile, dunning_level)

        # Wochentag berücksichtigen (Montag/Dienstag sind optimal)
        recommended_date = datetime.now(timezone.utc) + timedelta(days=base_days)
        weekday = recommended_date.weekday()

        # Auf Montag/Dienstag verschieben wenn möglich
        if weekday >= 5:  # Samstag/Sonntag
            days_to_monday = 7 - weekday
            recommended_date += timedelta(days=days_to_monday)
            base_days += days_to_monday
        elif weekday == 4:  # Freitag -> nächster Montag
            recommended_date += timedelta(days=3)
            base_days += 3

        factors["adjusted_for_weekday"] = True
        factors["final_weekday"] = recommended_date.strftime("%A")

        return DunningTiming(
            recommended_date=recommended_date,
            days_from_now=base_days,
            reasoning=self._build_timing_reasoning(factors, profile if entity_id else None),
            confidence=0.75 if entity_id else 0.5,
            factors=factors,
        )

    def _adjust_timing_by_profile(
        self,
        base_days: int,
        profile: CustomerProfile,
        dunning_level: DunningLevel,
    ) -> int:
        """Passt Timing basierend auf Kundenprofil an."""
        adjusted = base_days

        # VIP-Kunden: Mehr Zeit geben
        if profile.segment == CustomerSegment.VIP:
            adjusted = int(base_days * 1.3)
        # Gute Kunden: Etwas mehr Zeit
        elif profile.segment == CustomerSegment.GOOD:
            adjusted = int(base_days * 1.1)
        # Risiko-Kunden: Schneller mahnen
        elif profile.segment == CustomerSegment.RISKY:
            adjusted = int(base_days * 0.8)
        # Problematische: Noch schneller
        elif profile.segment == CustomerSegment.PROBLEMATIC:
            adjusted = int(base_days * 0.6)

        # Trend berücksichtigen
        if profile.payment_trend == TrendDirection.WORSENING:
            adjusted = int(adjusted * 0.8)  # Schneller bei Verschlechterung
        elif profile.payment_trend == TrendDirection.IMPROVING:
            adjusted = int(adjusted * 1.2)  # Mehr Zeit bei Verbesserung

        # Mindestens 3 Tage, maximal 30 Tage
        return max(3, min(30, adjusted))

    def _build_timing_reasoning(
        self,
        factors: JSONDict,
        profile: Optional[CustomerProfile],
    ) -> str:
        """Erstellt Begruendung für Timing-Empfehlung."""
        parts = []

        if profile:
            parts.append(f"Kundensegment: {profile.segment.value}")
            if profile.avg_payment_delay > 0:
                parts.append(
                    f"Durchschnittliche Zahlungsverzögerung: {profile.avg_payment_delay:.0f} Tage"
                )
            if profile.payment_trend != TrendDirection.STABLE:
                trend_text = "verbessert sich" if profile.payment_trend == TrendDirection.IMPROVING else "verschlechtert sich"
                parts.append(f"Zahlungsverhalten {trend_text}")

        if factors.get("adjusted_for_weekday"):
            parts.append(f"Versand am {factors.get('final_weekday', 'Wochentag')} optimiert")

        return ". ".join(parts) if parts else "Standard-Timing angewendet"

    # =========================================================================
    # Payment Prediction
    # =========================================================================

    async def predict_payment(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
    ) -> PaymentPrediction:
        """
        Sagt Zahlungswahrscheinlichkeit voraus.

        Args:
            db: Database Session
            invoice_id: Rechnungs-ID

        Returns:
            PaymentPrediction
        """
        # Rechnung laden
        invoice_result = await db.execute(
            select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if not invoice:
            return PaymentPrediction(
                likelihood=PaymentLikelihood.MEDIUM,
                probability=0.5,
                expected_payment_date=None,
                expected_delay_days=14,
                factors={},
                recommendations=["Keine Rechnungsdaten verfügbar"],
            )

        # Entity laden
        doc_result = await db.execute(
            select(Document.business_entity_id)
            .where(Document.id == invoice.document_id)
        )
        entity_id = doc_result.scalar_one_or_none()

        if not entity_id:
            return self._default_prediction(invoice)

        # Kundenprofil und Risiko laden
        profile = await self.get_customer_profile(db, entity_id)
        risk_score, payment_score, risk_factors = await self.risk_service.calculate_risk_score(
            db, entity_id
        )

        # Tage überfällig
        days_overdue = 0
        if invoice.due_date:
            due_date = invoice.due_date.replace(tzinfo=timezone.utc) if invoice.due_date.tzinfo is None else invoice.due_date
            days_overdue = max(0, (datetime.now(timezone.utc) - due_date).days)

        # Vorhersage-Faktoren
        factors = {
            "risk_score": risk_score,
            "payment_score": payment_score,
            "days_overdue": days_overdue,
            "dunning_level": invoice.dunning_level if hasattr(invoice, 'dunning_level') else 0,
            "invoice_amount": invoice.amount,
            "avg_payment_delay": risk_factors.payment_delay_days,
            "default_rate": risk_factors.default_rate,
            "total_invoices": risk_factors.total_invoices,
            "open_invoices": risk_factors.open_invoices,
            "relationship_months": risk_factors.relationship_months,
        }

        # Wahrscheinlichkeit berechnen
        probability = self._calculate_payment_probability(factors, profile)
        likelihood = self._probability_to_likelihood(probability)

        # Erwartete Verzögerung
        expected_delay = self._estimate_payment_delay(factors, profile)

        # Erwartetes Zahlungsdatum
        expected_date = None
        if invoice.due_date and probability > 0.3:
            due_date = invoice.due_date.replace(tzinfo=timezone.utc) if invoice.due_date.tzinfo is None else invoice.due_date
            expected_date = due_date + timedelta(days=expected_delay)

        # Empfehlungen generieren
        recommendations = self._generate_payment_recommendations(
            likelihood, factors, profile
        )

        return PaymentPrediction(
            likelihood=likelihood,
            probability=probability,
            expected_payment_date=expected_date,
            expected_delay_days=expected_delay,
            factors=factors,
            recommendations=recommendations,
        )

    def _default_prediction(self, invoice: InvoiceTracking) -> PaymentPrediction:
        """Erstellt Standard-Vorhersage ohne Kundendaten."""
        return PaymentPrediction(
            likelihood=PaymentLikelihood.MEDIUM,
            probability=0.5,
            expected_payment_date=datetime.now(timezone.utc) + timedelta(days=14),
            expected_delay_days=14,
            factors={"invoice_amount": invoice.amount},
            recommendations=["Keine Kundenhistorie vorhanden - Standard-Mahnprozess empfohlen"],
        )

    def _calculate_payment_probability(
        self,
        factors: JSONDict,
        profile: Optional[CustomerProfile],
    ) -> float:
        """Berechnet Zahlungswahrscheinlichkeit."""
        # Basis-Wahrscheinlichkeit
        base_prob = 0.7

        # Payment Score einbeziehen (0-100, höher = besser)
        payment_score = factors.get("payment_score", 50)
        base_prob = 0.3 + (payment_score / 100) * 0.6  # 0.3 - 0.9

        # Anpassungen
        days_overdue = factors.get("days_overdue", 0)
        if days_overdue > 60:
            base_prob *= 0.5
        elif days_overdue > 30:
            base_prob *= 0.7
        elif days_overdue > 14:
            base_prob *= 0.85

        # Dunning Level
        dunning_level = factors.get("dunning_level", 0)
        if dunning_level >= 3:
            base_prob *= 0.6  # Hohe Mahnstufe = weniger wahrscheinlich
        elif dunning_level >= 2:
            base_prob *= 0.8

        # Profil-Anpassung
        if profile:
            if profile.segment == CustomerSegment.VIP:
                base_prob *= 1.2
            elif profile.segment == CustomerSegment.GOOD:
                base_prob *= 1.1
            elif profile.segment == CustomerSegment.RISKY:
                base_prob *= 0.8
            elif profile.segment == CustomerSegment.PROBLEMATIC:
                base_prob *= 0.5

            # Trend
            if profile.payment_trend == TrendDirection.IMPROVING:
                base_prob *= 1.1
            elif profile.payment_trend == TrendDirection.WORSENING:
                base_prob *= 0.8

        return max(0.0, min(1.0, base_prob))

    def _probability_to_likelihood(self, probability: float) -> PaymentLikelihood:
        """Konvertiert Wahrscheinlichkeit zu Likelihood-Kategorie."""
        if probability >= 0.75:
            return PaymentLikelihood.HIGH
        elif probability >= 0.40:
            return PaymentLikelihood.MEDIUM
        else:
            return PaymentLikelihood.LOW

    def _estimate_payment_delay(
        self,
        factors: JSONDict,
        profile: Optional[CustomerProfile],
    ) -> int:
        """Schätzt erwartete Zahlungsverzögerung in Tagen."""
        # Basis: Durchschnittliche Verzögerung oder 14 Tage
        if profile and profile.avg_payment_delay > 0:
            base_delay = int(profile.avg_payment_delay)
        else:
            base_delay = 14

        # Anpassung basierend auf aktuellem Status
        days_overdue = factors.get("days_overdue", 0)
        dunning_level = factors.get("dunning_level", 0)

        # Je länger überfällig, desto länger die erwartete Verzögerung
        if days_overdue > 30:
            base_delay = max(base_delay, days_overdue + 7)

        # Mahnstufen-Anpassung
        delay_by_level = {0: 0, 1: 5, 2: 10, 3: 15, 4: 30}
        base_delay += delay_by_level.get(dunning_level, 0)

        return max(1, min(90, base_delay))

    def _generate_payment_recommendations(
        self,
        likelihood: PaymentLikelihood,
        factors: JSONDict,
        profile: Optional[CustomerProfile],
    ) -> List[str]:
        """Generiert Empfehlungen basierend auf Vorhersage."""
        recommendations = []

        if likelihood == PaymentLikelihood.HIGH:
            recommendations.append("Zahlung wahrscheinlich - Standard-Mahnprozess fortsetzen")
            if profile and profile.segment in (CustomerSegment.VIP, CustomerSegment.GOOD):
                recommendations.append("Bei diesem Kunden kann eine persoenliche Kontaktaufnahme sinnvoll sein")

        elif likelihood == PaymentLikelihood.MEDIUM:
            recommendations.append("Zahlung unsicher - engmaschigere Überwachung empfohlen")
            if factors.get("days_overdue", 0) > 30:
                recommendations.append("Telefonische Nachfrage erwagen")

        else:  # LOW
            recommendations.append("Zahlung unwahrscheinlich - Eskalation oder Inkasso prüfen")
            if factors.get("dunning_level", 0) < 3:
                recommendations.append("Schnellere Eskalation der Mahnstufen empfohlen")
            else:
                recommendations.append("Inkasso-Übergabe vorbereiten")

        # Skonto-Hinweis bei hohen Betraegen
        if factors.get("invoice_amount", 0) > 5000 and likelihood != PaymentLikelihood.LOW:
            recommendations.append("Bei hohem Rechnungsbetrag: Ratenzahlung oder Skonto anbieten")

        return recommendations

    # =========================================================================
    # Text Generation
    # =========================================================================

    async def generate_dunning_text(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
        dunning_level: DunningLevel,
        tone: Optional[DunningTone] = None,
        strategy: Optional[DunningStrategy] = None,
        special_instructions: Optional[str] = None,
    ) -> DunningText:
        """
        Generiert personalisierten Mahntext via LLM.

        Args:
            db: Database Session
            invoice_id: Rechnungs-ID
            dunning_level: Mahnstufe
            tone: Optionaler Tonfall (Default: basierend auf Stufe)
            strategy: Optionale Strategie (Default: basierend auf Kunde)
            special_instructions: Zusätzliche Anweisungen

        Returns:
            DunningText
        """
        import time
        start_time = time.perf_counter()

        # Rechnung laden
        invoice_result = await db.execute(
            select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()

        if not invoice:
            return self._generate_fallback_text(dunning_level, None, tone, strategy)

        # Entity laden
        doc_result = await db.execute(
            select(Document.business_entity_id)
            .where(Document.id == invoice.document_id)
        )
        entity_id = doc_result.scalar_one_or_none()

        profile = None
        if entity_id:
            profile = await self.get_customer_profile(db, entity_id)

        # Ton und Strategie bestimmen
        if tone is None:
            tone = self._determine_tone(dunning_level, profile)
        if strategy is None:
            strategy = self._determine_strategy(profile)

        # Prompt-Daten vorbereiten
        invoice_date = invoice.invoice_date.strftime("%d.%m.%Y") if invoice.invoice_date else "unbekannt"
        due_date = invoice.due_date.strftime("%d.%m.%Y") if invoice.due_date else "unbekannt"

        days_overdue = 0
        if invoice.due_date:
            due_date_utc = invoice.due_date.replace(tzinfo=timezone.utc) if invoice.due_date.tzinfo is None else invoice.due_date
            days_overdue = max(0, (datetime.now(timezone.utc) - due_date_utc).days)

        prompt_data = {
            "invoice_number": invoice.invoice_number or "N/A",
            "invoice_date": invoice_date,
            "due_date": due_date,
            "amount": f"{invoice.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "currency": invoice.currency or "EUR",
            "days_overdue": days_overdue,
            "dunning_level": dunning_level.value,
            "dunning_level_de": DUNNING_LEVEL_LABELS_DE.get(dunning_level, str(dunning_level.value)),
            "tone": tone.value,
            "tone_description": TONE_DESCRIPTIONS.get(tone, ""),
            "customer_segment": profile.segment.value if profile else "normal",
            "relationship_months": profile.relationship_months if profile else 0,
            "payment_behavior": self._describe_payment_behavior(profile),
            "open_invoices": profile.open_invoices if profile else 0,
            "strategy": strategy.value,
            "special_instructions": special_instructions or "Keine besonderen Hinweise",
        }

        try:
            # LLM verfügbar?
            llm_available = await self.ollama.is_available()
            if not llm_available:
                return self._generate_fallback_text(dunning_level, profile, tone, strategy)

            # Prompt erstellen
            user_prompt = DUNNING_TEXT_USER_PROMPT.format(**prompt_data)

            # LLM aufrufen
            response = await asyncio.wait_for(
                self.ollama.generate(
                    prompt=user_prompt,
                    system_prompt=DUNNING_TEXT_SYSTEM_PROMPT,
                    temperature=0.3,
                    format_json=True,
                ),
                timeout=self.LLM_TIMEOUT_SECONDS,
            )

            # Response parsen
            text_data = self._parse_llm_response(response)

            if text_data:
                generation_time_ms = int((time.perf_counter() - start_time) * 1000)

                full_text = self._assemble_full_text(text_data)

                # Metriken
                DUNNING_GENERATED.labels(
                    dunning_level=dunning_level.value,
                    strategy=strategy.value,
                    tone=tone.value,
                ).inc()

                DUNNING_TEXT_GENERATION_DURATION.observe(generation_time_ms / 1000)

                return DunningText(
                    subject=text_data.get("subject", "Zahlungserinnerung"),
                    greeting=text_data.get("greeting", "Sehr geehrte Damen und Herren,"),
                    body=text_data.get("body", ""),
                    closing=text_data.get("closing", "Mit freundlichen Gruessen"),
                    full_text=full_text,
                    tone=tone,
                    dunning_level=dunning_level,
                    strategy=strategy,
                    personalization_factors=self._get_personalization_factors(profile),
                    generation_time_ms=generation_time_ms,
                )

        except asyncio.TimeoutError:
            logger.warning("dunning_text_generation_timeout")
        except Exception as e:
            logger.warning("dunning_text_generation_error", error=str(e))

        return self._generate_fallback_text(dunning_level, profile, tone, strategy)

    def _parse_llm_response(self, response: str) -> Optional[JSONDict]:
        """Parst LLM-Antwort."""
        if not response:
            return None

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError as e:
                    # OPEN-46: ungültiges Dunning-Strategie-JSON sichtbar machen (Fallback bleibt None)
                    logger.error("dunning_strategy_json_invalid", error_type=type(e).__name__)
        return None

    def _determine_tone(
        self,
        dunning_level: DunningLevel,
        profile: Optional[CustomerProfile],
    ) -> DunningTone:
        """Bestimmt optimalen Tonfall."""
        # Basis nach Mahnstufe
        tone_by_level = {
            DunningLevel.REMINDER: DunningTone.FRIENDLY,
            DunningLevel.FIRST: DunningTone.NEUTRAL,
            DunningLevel.SECOND: DunningTone.FIRM,
            DunningLevel.FINAL: DunningTone.URGENT,
            DunningLevel.INKASSO: DunningTone.FINAL,
        }

        base_tone = tone_by_level.get(dunning_level, DunningTone.NEUTRAL)

        # Anpassung nach Profil
        if profile:
            if profile.segment in (CustomerSegment.VIP, CustomerSegment.GOOD):
                # Eine Stufe freundlicher
                if base_tone == DunningTone.FIRM:
                    return DunningTone.NEUTRAL
                elif base_tone == DunningTone.URGENT:
                    return DunningTone.FIRM
            elif profile.segment == CustomerSegment.PROBLEMATIC:
                # Eine Stufe strenger
                if base_tone == DunningTone.FRIENDLY:
                    return DunningTone.NEUTRAL
                elif base_tone == DunningTone.NEUTRAL:
                    return DunningTone.FIRM

        return base_tone

    def _determine_strategy(
        self,
        profile: Optional[CustomerProfile],
    ) -> DunningStrategy:
        """Bestimmt optimale Mahnstrategie."""
        if not profile:
            return DunningStrategy.STANDARD

        if profile.segment == CustomerSegment.VIP:
            return DunningStrategy.RELATIONSHIP
        elif profile.segment == CustomerSegment.GOOD:
            return DunningStrategy.RELATIONSHIP
        elif profile.segment == CustomerSegment.RISKY:
            return DunningStrategy.FINANCIAL
        elif profile.segment == CustomerSegment.PROBLEMATIC:
            return DunningStrategy.ESCALATION

        return DunningStrategy.STANDARD

    def _describe_payment_behavior(
        self,
        profile: Optional[CustomerProfile],
    ) -> str:
        """Beschreibt Zahlungsverhalten für Prompt."""
        if not profile:
            return "Keine historischen Daten verfügbar"

        parts = []

        if profile.avg_payment_delay <= 0:
            parts.append("Zahlt puenktlich")
        elif profile.avg_payment_delay <= 7:
            parts.append("Zahlt meist puenktlich")
        elif profile.avg_payment_delay <= 14:
            parts.append("Zahlt mit leichter Verzögerung")
        elif profile.avg_payment_delay <= 30:
            parts.append("Zahlt regelmäßig verspätet")
        else:
            parts.append("Chronisch verspätete Zahlungen")

        if profile.payment_trend == TrendDirection.IMPROVING:
            parts.append("Trend verbessert sich")
        elif profile.payment_trend == TrendDirection.WORSENING:
            parts.append("Trend verschlechtert sich")

        return ", ".join(parts)

    def _get_personalization_factors(
        self,
        profile: Optional[CustomerProfile],
    ) -> List[str]:
        """Liefert Liste der Personalisierungsfaktoren."""
        factors = []

        if profile:
            factors.append(f"Segment: {profile.segment.value}")
            factors.append(f"Beziehungsdauer: {profile.relationship_months:.0f} Monate")
            if profile.avg_payment_delay > 0:
                factors.append(f"Zahlungsverzögerung: {profile.avg_payment_delay:.0f} Tage")
            factors.append(f"Zahlungstrend: {profile.payment_trend.value}")

        return factors

    def _assemble_full_text(self, text_data: JSONDict) -> str:
        """Setzt vollständigen Text zusammen."""
        parts = [
            text_data.get("greeting", "Sehr geehrte Damen und Herren,"),
            "",
            text_data.get("body", ""),
            "",
            text_data.get("closing", "Mit freundlichen Gruessen"),
        ]
        return "\n".join(parts)

    def _generate_fallback_text(
        self,
        dunning_level: DunningLevel,
        profile: Optional[CustomerProfile],
        tone: Optional[DunningTone],
        strategy: Optional[DunningStrategy],
    ) -> DunningText:
        """Generiert Fallback-Text ohne LLM."""
        tone = tone or DunningTone.NEUTRAL
        strategy = strategy or DunningStrategy.STANDARD

        # Einfache Template-basierte Texte
        templates = {
            DunningLevel.REMINDER: {
                "subject": "Zahlungserinnerung",
                "body": "wir moechten Sie freundlich daran erinnern, dass die oben genannte Rechnung noch nicht beglichen wurde. Bitte überweisen Sie den offenen Betrag zeitnah auf unser Konto.\n\nSollte sich Ihre Zahlung mit diesem Schreiben überschnitten haben, betrachten Sie diese Erinnerung bitte als gegenstandslos.",
            },
            DunningLevel.FIRST: {
                "subject": "1. Mahnung",
                "body": "trotz unserer Zahlungserinnerung konnten wir noch keinen Zahlungseingang feststellen. Wir bitten Sie, den ausstehenden Betrag innerhalb der nächsten 7 Tage zu begleichen.\n\nBitte beachten Sie, dass bei weiterem Zahlungsverzug zusätzliche Mahngebühren anfallen können.",
            },
            DunningLevel.SECOND: {
                "subject": "2. Mahnung",
                "body": "leider ist die Zahlung des genannten Rechnungsbetrages trotz unserer bisherigen Mahnungen noch nicht erfolgt. Wir fordern Sie hiermit nachdrücklich auf, den offenen Betrag innerhalb von 7 Tagen zu überweisen.\n\nBei Nichtzahlung behalten wir uns rechtliche Schritte vor.",
            },
            DunningLevel.FINAL: {
                "subject": "Letzte Mahnung vor Inkasso",
                "body": "dies ist unsere letzte Mahnung. Der offene Betrag ist seit längerem überfällig. Sollte die Zahlung nicht innerhalb von 5 Werktagen bei uns eingehen, werden wir die Forderung ohne weitere Ankündigung an ein Inkassounternehmen übergeben.\n\nDadurch entstehen Ihnen erhebliche zusätzliche Kosten.",
            },
            DunningLevel.INKASSO: {
                "subject": "Inkasso-Ankündigung",
                "body": "trotz mehrfacher Mahnung ist Ihre Zahlung nicht eingegangen. Wir werden die Forderung nunmehr an ein Inkassounternehmen übergeben.\n\nDies führt zu erheblichen zusätzlichen Kosten für Sie, einschliesslich Inkassogebühren, Zinsen und ggf. Gerichtskosten.",
            },
        }

        template = templates.get(dunning_level, templates[DunningLevel.REMINDER])

        greeting = "Sehr geehrte Damen und Herren,"
        closing = "Mit freundlichen Gruessen\n\nIhr Forderungsmanagement"

        full_text = f"{greeting}\n\n{template['body']}\n\n{closing}"

        return DunningText(
            subject=template["subject"],
            greeting=greeting,
            body=template["body"],
            closing=closing,
            full_text=full_text,
            tone=tone,
            dunning_level=dunning_level,
            strategy=strategy,
            personalization_factors=["Fallback-Template (LLM nicht verfügbar)"],
            generation_time_ms=0,
        )

    # =========================================================================
    # A/B Testing
    # =========================================================================

    async def create_ab_test(
        self,
        db: AsyncSession,
        name: str,
        description: str,
        dunning_level: DunningLevel,
        variants: List[JSONDict],
        end_date: Optional[datetime] = None,
    ) -> ABTest:
        """
        Erstellt einen neuen A/B Test.

        Args:
            db: Database Session
            name: Test-Name
            description: Beschreibung
            dunning_level: Mahnstufe für den Test
            variants: Liste von Varianten-Konfigurationen
            end_date: Optionales End-Datum

        Returns:
            ABTest
        """
        test_id = str(uuid.uuid4())[:8]

        variant_objects = []
        for i, var_config in enumerate(variants):
            variant = ABTestVariant(
                variant_id=f"{test_id}_v{i}",
                strategy=DunningStrategy(var_config.get("strategy", "standard")),
                tone=DunningTone(var_config.get("tone", "neutral")),
                waiting_period_modifier=var_config.get("waiting_modifier", 1.0),
                sample_count=0,
                success_count=0,
                conversion_rate=0.0,
            )
            variant_objects.append(variant)

        test = ABTest(
            test_id=test_id,
            name=name,
            description=description,
            variants=variant_objects,
            is_active=True,
            start_date=datetime.now(timezone.utc),
            end_date=end_date,
            dunning_level=dunning_level,
            created_at=datetime.now(timezone.utc),
        )

        self._ab_tests[test_id] = test

        # In DB speichern
        await self._save_ab_tests(db)

        logger.info(
            "ab_test_created",
            test_id=test_id,
            name=name,
            variants_count=len(variant_objects),
        )

        return test

    async def get_ab_test_variant(
        self,
        db: AsyncSession,
        dunning_level: DunningLevel,
        entity_id: uuid.UUID,
    ) -> Optional[ABTestVariant]:
        """
        Waehlt A/B Test Variante für Entity.

        Args:
            db: Database Session
            dunning_level: Mahnstufe
            entity_id: Entity-ID für konsistente Zuweisung

        Returns:
            ABTestVariant oder None wenn kein Test aktiv
        """
        # Aktiven Test für Mahnstufe finden
        active_test = None
        for test in self._ab_tests.values():
            if test.is_active and test.dunning_level == dunning_level:
                if test.end_date is None or test.end_date > datetime.now(timezone.utc):
                    active_test = test
                    break

        if not active_test:
            return None

        # Deterministisch basierend auf Entity-ID (konsistent über Zeit)
        hash_input = f"{active_test.test_id}_{entity_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)
        variant_index = hash_value % len(active_test.variants)

        return active_test.variants[variant_index]

    async def record_ab_test_result(
        self,
        db: AsyncSession,
        variant_id: str,
        success: bool,
    ) -> None:
        """
        Zeichnet A/B Test Ergebnis auf.

        Args:
            db: Database Session
            variant_id: Varianten-ID
            success: Ob Zahlung erfolgte
        """
        for test in self._ab_tests.values():
            for variant in test.variants:
                if variant.variant_id == variant_id:
                    variant.sample_count += 1
                    if success:
                        variant.success_count += 1
                    variant.conversion_rate = (
                        variant.success_count / variant.sample_count
                        if variant.sample_count > 0 else 0.0
                    )

                    # Prometheus Gauge aktualisieren
                    AB_TEST_CONVERSION.labels(
                        test_id=test.test_id,
                        variant=variant.variant_id,
                    ).set(variant.conversion_rate)

                    await self._save_ab_tests(db)
                    return

    async def get_ab_test_results(
        self,
        db: AsyncSession,
        test_id: str,
    ) -> Optional[JSONDict]:
        """
        Gibt A/B Test Ergebnisse zurück.

        Args:
            db: Database Session
            test_id: Test-ID

        Returns:
            Dict mit Ergebnissen oder None
        """
        test = self._ab_tests.get(test_id)
        if not test:
            return None

        # Statistisch signifikanten Gewinner ermitteln (vereinfacht)
        winner = None
        max_rate = 0.0
        min_samples = 30  # Minimum für statistische Signifikanz

        for variant in test.variants:
            if variant.sample_count >= min_samples:
                if variant.conversion_rate > max_rate:
                    max_rate = variant.conversion_rate
                    winner = variant.variant_id

        return {
            "test_id": test.test_id,
            "name": test.name,
            "is_active": test.is_active,
            "start_date": test.start_date.isoformat(),
            "end_date": test.end_date.isoformat() if test.end_date else None,
            "dunning_level": test.dunning_level.value,
            "variants": [
                {
                    "variant_id": v.variant_id,
                    "strategy": v.strategy.value,
                    "tone": v.tone.value,
                    "waiting_modifier": v.waiting_period_modifier,
                    "sample_count": v.sample_count,
                    "success_count": v.success_count,
                    "conversion_rate": round(v.conversion_rate, 4),
                }
                for v in test.variants
            ],
            "winner": winner,
            "statistically_significant": all(
                v.sample_count >= min_samples for v in test.variants
            ),
        }

    async def _save_ab_tests(self, db: AsyncSession) -> None:
        """Speichert A/B Tests in DB."""
        try:
            data = {}
            for test_id, test in self._ab_tests.items():
                data[test_id] = {
                    "test_id": test.test_id,
                    "name": test.name,
                    "description": test.description,
                    "is_active": test.is_active,
                    "start_date": test.start_date.isoformat(),
                    "end_date": test.end_date.isoformat() if test.end_date else None,
                    "dunning_level": test.dunning_level.value,
                    "created_at": test.created_at.isoformat(),
                    "variants": [
                        {
                            "variant_id": v.variant_id,
                            "strategy": v.strategy.value,
                            "tone": v.tone.value,
                            "waiting_modifier": v.waiting_period_modifier,
                            "sample_count": v.sample_count,
                            "success_count": v.success_count,
                            "conversion_rate": v.conversion_rate,
                        }
                        for v in test.variants
                    ],
                }

            result = await db.execute(
                select(AppConfig).where(AppConfig.key == self.AB_TESTS_KEY)
            )
            config = result.scalar_one_or_none()

            if config:
                config.value = data
            else:
                config = AppConfig(key=self.AB_TESTS_KEY, value=data)
                db.add(config)

            await db.commit()
        except Exception as e:
            logger.error("ab_tests_save_error", error=str(e))

    async def load_ab_tests(self, db: AsyncSession) -> None:
        """Laedt A/B Tests aus DB."""
        try:
            result = await db.execute(
                select(AppConfig).where(AppConfig.key == self.AB_TESTS_KEY)
            )
            config = result.scalar_one_or_none()

            if config and config.value:
                for test_id, test_data in config.value.items():
                    variants = [
                        ABTestVariant(
                            variant_id=v["variant_id"],
                            strategy=DunningStrategy(v["strategy"]),
                            tone=DunningTone(v["tone"]),
                            waiting_period_modifier=v["waiting_modifier"],
                            sample_count=v["sample_count"],
                            success_count=v["success_count"],
                            conversion_rate=v["conversion_rate"],
                        )
                        for v in test_data.get("variants", [])
                    ]

                    test = ABTest(
                        test_id=test_data["test_id"],
                        name=test_data["name"],
                        description=test_data["description"],
                        is_active=test_data["is_active"],
                        start_date=datetime.fromisoformat(test_data["start_date"]),
                        end_date=datetime.fromisoformat(test_data["end_date"]) if test_data["end_date"] else None,
                        dunning_level=DunningLevel(test_data["dunning_level"]),
                        variants=variants,
                        created_at=datetime.fromisoformat(test_data["created_at"]),
                    )
                    self._ab_tests[test_id] = test

                logger.info("ab_tests_loaded", count=len(self._ab_tests))
        except Exception as e:
            logger.error("ab_tests_load_error", error=str(e))

    # =========================================================================
    # Strategy Statistics
    # =========================================================================

    async def record_dunning_sent(
        self,
        db: AsyncSession,
        strategy: DunningStrategy,
        dunning_level: DunningLevel,
    ) -> None:
        """Zeichnet versendete Mahnung auf."""
        key = f"{strategy.value}_{dunning_level.value}"
        if key not in self._strategy_stats:
            self._strategy_stats[key] = {"sent": 0, "success": 0}
        self._strategy_stats[key]["sent"] += 1

        DUNNING_SENT.labels(
            dunning_level=dunning_level.value,
            strategy=strategy.value,
        ).inc()

        await self._save_strategy_stats(db)

    async def record_dunning_success(
        self,
        db: AsyncSession,
        strategy: DunningStrategy,
        dunning_level: DunningLevel,
    ) -> None:
        """Zeichnet erfolgreiche Mahnung auf (führte zu Zahlung)."""
        key = f"{strategy.value}_{dunning_level.value}"
        if key not in self._strategy_stats:
            self._strategy_stats[key] = {"sent": 0, "success": 0}
        self._strategy_stats[key]["success"] += 1

        DUNNING_SUCCESS.labels(
            dunning_level=dunning_level.value,
            strategy=strategy.value,
        ).inc()

        await self._save_strategy_stats(db)

    async def get_strategy_statistics(
        self,
        db: AsyncSession,
    ) -> JSONDict:
        """Gibt Strategie-Statistiken zurück."""
        stats = {}

        for key, data in self._strategy_stats.items():
            parts = key.split("_")
            if len(parts) >= 2:
                strategy = parts[0]
                level = "_".join(parts[1:])

                if strategy not in stats:
                    stats[strategy] = {"total_sent": 0, "total_success": 0, "by_level": {}}

                stats[strategy]["total_sent"] += data["sent"]
                stats[strategy]["total_success"] += data["success"]
                stats[strategy]["by_level"][level] = {
                    "sent": data["sent"],
                    "success": data["success"],
                    "success_rate": data["success"] / data["sent"] if data["sent"] > 0 else 0.0,
                }

        # Gesamt-Success-Rate berechnen
        for strategy_data in stats.values():
            if strategy_data["total_sent"] > 0:
                strategy_data["overall_success_rate"] = (
                    strategy_data["total_success"] / strategy_data["total_sent"]
                )
            else:
                strategy_data["overall_success_rate"] = 0.0

        return stats

    async def _save_strategy_stats(self, db: AsyncSession) -> None:
        """Speichert Strategie-Statistiken."""
        try:
            result = await db.execute(
                select(AppConfig).where(AppConfig.key == self.STRATEGY_STATS_KEY)
            )
            config = result.scalar_one_or_none()

            if config:
                config.value = self._strategy_stats
            else:
                config = AppConfig(key=self.STRATEGY_STATS_KEY, value=self._strategy_stats)
                db.add(config)

            await db.commit()
        except Exception as e:
            logger.error("strategy_stats_save_error", error=str(e))

    async def load_strategy_stats(self, db: AsyncSession) -> None:
        """Laedt Strategie-Statistiken."""
        try:
            result = await db.execute(
                select(AppConfig).where(AppConfig.key == self.STRATEGY_STATS_KEY)
            )
            config = result.scalar_one_or_none()

            if config and config.value:
                self._strategy_stats = config.value
                logger.info("strategy_stats_loaded", strategies=len(self._strategy_stats))
        except Exception as e:
            logger.error("strategy_stats_load_error", error=str(e))

    # =========================================================================
    # Main Orchestration
    # =========================================================================

    async def process_dunning(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
        dunning_level: DunningLevel,
        force_strategy: Optional[DunningStrategy] = None,
        force_tone: Optional[DunningTone] = None,
    ) -> DunningResult:
        """
        Verarbeitet eine Mahnung komplett.

        Args:
            db: Database Session
            invoice_id: Rechnungs-ID
            dunning_level: Mahnstufe
            force_strategy: Optionale erzwungene Strategie
            force_tone: Optionaler erzwungener Tonfall

        Returns:
            DunningResult mit Text, Timing und Vorhersage
        """
        # Entity ID ermitteln
        doc_result = await db.execute(
            select(Document.business_entity_id)
            .join(InvoiceTracking, Document.id == InvoiceTracking.document_id)
            .where(InvoiceTracking.id == invoice_id)
        )
        entity_id = doc_result.scalar_one_or_none()

        # A/B Test Variante prüfen
        ab_variant = None
        strategy = force_strategy
        tone = force_tone

        if entity_id and not force_strategy:
            ab_variant = await self.get_ab_test_variant(db, dunning_level, entity_id)
            if ab_variant:
                strategy = ab_variant.strategy
                tone = ab_variant.tone

        # Timing berechnen
        timing = await self.predict_optimal_timing(db, invoice_id, dunning_level)

        # Zahlungsvorhersage
        prediction = await self.predict_payment(db, invoice_id)

        # Text generieren
        text = await self.generate_dunning_text(
            db=db,
            invoice_id=invoice_id,
            dunning_level=dunning_level,
            tone=tone,
            strategy=strategy,
        )

        return DunningResult(
            invoice_id=invoice_id,
            dunning_level=dunning_level,
            text=text,
            timing=timing,
            prediction=prediction,
            ab_test_variant=ab_variant.variant_id if ab_variant else None,
        )


# =============================================================================
# Singleton
# =============================================================================

_smart_dunning_service: Optional[SmartDunningService] = None
_service_lock = threading.Lock()


def get_smart_dunning_service() -> SmartDunningService:
    """Factory für SmartDunningService Singleton (Thread-safe)."""
    global _smart_dunning_service
    if _smart_dunning_service is None:
        with _service_lock:
            if _smart_dunning_service is None:
                _smart_dunning_service = SmartDunningService()
    return _smart_dunning_service


def reset_smart_dunning_service() -> None:
    """Reset für Tests."""
    global _smart_dunning_service
    _smart_dunning_service = None
