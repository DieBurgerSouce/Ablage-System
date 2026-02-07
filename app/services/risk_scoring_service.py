"""
Risk Scoring Service v2.0

Berechnet Risiko-Scores fuer Geschaeftspartner basierend auf:
- Zahlungsverhalten (Zahlungsverzoegerungen, Ausfallraten)
- Dokumentenhistorie (Anzahl, Frequenz, Typen)
- Rechnungsvolumen und -muster
- Branchenrisiko (NEU in v2.0)
- Zahlungstrend-Analyse mit linearer Regression (NEU in v2.0)
- Externe Datenquellen (vorbereitete Schnittstellen, NEU in v2.0)

Feinpoliert und durchdacht - Enterprise Risk Scoring.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import math

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, Document, InvoiceTracking, RiskScoreHistory
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# Risk Levels and Enums
# ============================================================================

class RiskLevel(str, Enum):
    """Risk Level Classification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TrendDirection(str, Enum):
    """Payment Trend Direction."""
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    WORSENING = "WORSENING"


# ============================================================================
# Risk Factor Weights (V2 - Re-normalized to sum to 1.0)
# ============================================================================

RISK_WEIGHTS_V1 = {
    "payment_delay": 0.35,      # Zahlungsverzoegerung
    "default_rate": 0.25,       # Ausfallrate
    "invoice_volume": 0.15,     # Rechnungsvolumen (niedriger = riskanter)
    "document_frequency": 0.10, # Dokumentenfrequenz (unregelmaessig = riskanter)
    "relationship_age": 0.15,   # Beziehungsdauer (kuerzer = riskanter)
}

RISK_WEIGHTS_V2 = {
    "payment_delay": 0.20,      # Zahlungsverzoegerung (reduziert fuer neue Faktoren)
    "default_rate": 0.15,       # Ausfallrate
    "invoice_volume": 0.10,     # Rechnungsvolumen
    "document_frequency": 0.05, # Dokumentenfrequenz
    "relationship_age": 0.10,   # Beziehungsdauer
    "industry_risk": 0.15,      # Branchenrisiko (NEU)
    "payment_trend": 0.20,      # Zahlungstrend (NEU)
    "economic_indicators": 0.05,  # Wirtschaftsindikatoren (NEU, Platzhalter)
}


# ============================================================================
# Industry Risk Scores
# ============================================================================

INDUSTRY_RISK_SCORES: Dict[str, int] = {
    # Low risk (score 0-20)
    "healthcare": 10,
    "utilities": 15,
    "government": 5,
    "public_sector": 5,
    "pharma": 12,
    "insurance": 18,

    # Medium risk (score 21-50)
    "manufacturing": 35,
    "retail": 40,
    "technology": 30,
    "automotive": 38,
    "logistics": 35,
    "food_beverage": 32,
    "professional_services": 28,
    "education": 25,
    "media": 42,
    "telecommunications": 30,

    # High risk (score 51-80)
    "construction": 55,
    "hospitality": 60,
    "real_estate": 50,
    "tourism": 65,
    "aviation": 58,
    "energy": 52,
    "mining": 55,
    "agriculture": 48,

    # Very high risk (score 81-100)
    "startup": 85,
    "crypto": 90,
    "fintech": 75,
    "entertainment": 70,
    "fashion": 72,

    # Default for unknown industries
    "unknown": 50,
}


# ============================================================================
# External Data Provider Interfaces (Stubs for future integration)
# ============================================================================

@dataclass
class ExternalData:
    """External data from third-party providers."""
    provider: str
    company_name: Optional[str] = None
    credit_rating: Optional[str] = None
    credit_score: Optional[int] = None
    insolvency_risk: Optional[float] = None
    payment_index: Optional[float] = None
    last_updated: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


class ExternalDataProvider(ABC):
    """Abstract base class for external data providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""
        pass

    @abstractmethod
    async def get_company_data(self, entity_id: UUID, vat_id: Optional[str] = None) -> Optional[ExternalData]:
        """
        Fetch company data from external source.

        Args:
            entity_id: Internal entity ID
            vat_id: VAT ID for lookup (optional)

        Returns:
            ExternalData object or None if not available
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        pass


class NorthDataProvider(ExternalDataProvider):
    """
    Stub for North Data integration.

    North Data provides company information for German/European businesses:
    - Financial statements
    - Ownership structure
    - Business relationships
    - Insolvency notifications

    TODO: Implement when API access is available.
    """

    @property
    def provider_name(self) -> str:
        return "north_data"

    async def get_company_data(self, entity_id: UUID, vat_id: Optional[str] = None) -> Optional[ExternalData]:
        """
        Stub implementation - returns None.

        In production, this would:
        1. Look up company by VAT ID or name
        2. Fetch financial indicators
        3. Return structured ExternalData

        Example API call (when implemented):
        ```
        response = await self._client.get(
            f"/companies/{vat_id}",
            params={"include": "financials,relationships"}
        )
        ```
        """
        logger.debug(
            "northdata_lookup_stub",
            entity_id=str(entity_id),
            message="NorthData Integration nicht konfiguriert"
        )
        return None

    async def is_available(self) -> bool:
        """Check if North Data API is configured."""
        # TODO: Check environment variable NORTH_DATA_API_KEY
        return False


class SchufaB2BProvider(ExternalDataProvider):
    """
    Stub for Schufa B2B integration.

    Schufa provides:
    - Business credit scores
    - Payment behavior indices
    - Default probability

    TODO: Implement when API access is available.
    """

    @property
    def provider_name(self) -> str:
        return "schufa_b2b"

    async def get_company_data(self, entity_id: UUID, vat_id: Optional[str] = None) -> Optional[ExternalData]:
        """
        Stub implementation - returns None.

        In production, this would:
        1. Authenticate with Schufa B2B API
        2. Request company rating
        3. Parse and return ExternalData

        Example API call (when implemented):
        ```
        response = await self._client.post(
            "/b2b/rating",
            json={"vatId": vat_id, "country": "DE"}
        )
        ```
        """
        logger.debug(
            "schufa_lookup_stub",
            entity_id=str(entity_id),
            message="Schufa B2B Integration nicht konfiguriert"
        )
        return None

    async def is_available(self) -> bool:
        """Check if Schufa B2B API is configured."""
        # TODO: Check environment variables SCHUFA_B2B_USER, SCHUFA_B2B_PASSWORD
        return False


class CreditreformProvider(ExternalDataProvider):
    """
    Stub for Creditreform integration.

    Creditreform provides:
    - Bonitaetsindex (credit rating)
    - Payment experience data
    - Company financials

    TODO: Implement when API access is available.
    """

    @property
    def provider_name(self) -> str:
        return "creditreform"

    async def get_company_data(self, entity_id: UUID, vat_id: Optional[str] = None) -> Optional[ExternalData]:
        """Stub implementation - returns None."""
        logger.debug(
            "creditreform_lookup_stub",
            entity_id=str(entity_id),
            message="Creditreform Integration nicht konfiguriert"
        )
        return None

    async def is_available(self) -> bool:
        """Check if Creditreform API is configured."""
        return False


# ============================================================================
# Risk Factor Data Classes
# ============================================================================

@dataclass
class RiskFactor:
    """Einzelner Risikofaktor mit Bewertung."""
    name: str
    value: float           # Original-Wert
    score: float           # Normalisierter Score (0-100)
    weight: float          # Gewichtung
    weighted_score: float  # Gewichteter Beitrag zum Gesamt-Score
    description: str       # Deutsche Beschreibung


@dataclass
class PaymentHistoryEntry:
    """Einzelner Zahlungseintrag fuer Trend-Analyse."""
    invoice_id: UUID
    due_date: datetime
    paid_at: Optional[datetime]
    delay_days: int  # Positive = verspaetet, Negative = frueh


class RiskFactors:
    """Einzelne Risikofaktoren mit Bewertung (V1 compatibility)."""

    def __init__(self) -> None:
        self.payment_delay_days: float = 0.0  # Durchschnittliche Verzoegerung in Tagen
        self.default_rate: float = 0.0  # Prozent ausgefallener Zahlungen
        self.invoice_volume: float = 0.0  # Gesamtvolumen in EUR
        self.document_frequency: float = 0.0  # Dokumente pro Monat
        self.relationship_months: float = 0.0  # Beziehungsdauer in Monaten
        self.total_invoices: int = 0
        self.paid_invoices: int = 0
        self.overdue_invoices: int = 0
        self.open_invoices: int = 0

        # V2 additions
        self.industry_code: str = "unknown"
        self.industry_risk_score: float = 50.0
        self.payment_trend: TrendDirection = TrendDirection.STABLE
        self.trend_slope: float = 0.0  # Tage/Monat (negativ = Verbesserung)
        self.trend_adjustment: int = 0  # Score-Anpassung basierend auf Trend
        self.external_data: Optional[ExternalData] = None
        self.economic_indicator_score: float = 50.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer JSON-Speicherung."""
        result = {
            "payment_delay_days": round(self.payment_delay_days, 1),
            "default_rate": round(self.default_rate * 100, 1),  # Als Prozent
            "invoice_volume": round(self.invoice_volume, 2),
            "document_frequency": round(self.document_frequency, 2),
            "relationship_months": round(self.relationship_months, 1),
            "total_invoices": self.total_invoices,
            "paid_invoices": self.paid_invoices,
            "overdue_invoices": self.overdue_invoices,
            "open_invoices": self.open_invoices,
            # V2 additions
            "industry_code": self.industry_code,
            "industry_risk_score": round(self.industry_risk_score, 1),
            "payment_trend": self.payment_trend.value,
            "trend_slope": round(self.trend_slope, 2),
            "trend_adjustment": self.trend_adjustment,
            "economic_indicator_score": round(self.economic_indicator_score, 1),
        }

        if self.external_data:
            result["external_data_provider"] = self.external_data.provider
            if self.external_data.credit_score:
                result["external_credit_score"] = self.external_data.credit_score

        return result


# ============================================================================
# Detailed Response Models
# ============================================================================

@dataclass
class RiskScoreDetailedResponse:
    """Enhanced API response with detailed risk information."""
    entity_id: UUID
    overall_score: int  # 0-100
    risk_level: RiskLevel
    factors: Dict[str, RiskFactor]
    trend: TrendDirection
    trend_score_adjustment: int
    last_calculated: datetime
    recommendations: List[str]  # German recommendations
    payment_behavior_score: float
    version: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "entity_id": str(self.entity_id),
            "overall_score": self.overall_score,
            "risk_level": self.risk_level.value,
            "factors": {
                name: {
                    "name": f.name,
                    "value": f.value,
                    "score": round(f.score, 1),
                    "weight": f.weight,
                    "weighted_score": round(f.weighted_score, 1),
                    "description": f.description,
                }
                for name, f in self.factors.items()
            },
            "trend": self.trend.value,
            "trend_score_adjustment": self.trend_score_adjustment,
            "last_calculated": self.last_calculated.isoformat(),
            "recommendations": self.recommendations,
            "payment_behavior_score": round(self.payment_behavior_score, 1),
            "version": self.version,
        }


# ============================================================================
# Risk Scoring Service V2
# ============================================================================

class RiskScoringService:
    """Service fuer Risiko-Score-Berechnung (V2)."""

    def __init__(
        self,
        use_v2_weights: bool = True,
        external_providers: Optional[List[ExternalDataProvider]] = None,
    ) -> None:
        """
        Initialize the risk scoring service.

        Args:
            use_v2_weights: Use V2 weights with new factors (default: True)
            external_providers: Optional list of external data providers
        """
        self._use_v2 = use_v2_weights
        self._weights = RISK_WEIGHTS_V2 if use_v2_weights else RISK_WEIGHTS_V1
        self._external_providers = external_providers or [
            NorthDataProvider(),
            SchufaB2BProvider(),
            CreditreformProvider(),
        ]

    @property
    def version(self) -> str:
        """Return service version."""
        return "2.0" if self._use_v2 else "1.0"

    async def calculate_risk_score(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> Tuple[float, float, RiskFactors]:
        """
        Berechnet Risiko-Score fuer einen Geschaeftspartner.

        Returns:
            Tuple[risk_score, payment_behavior_score, factors]
            - risk_score: 0-100 (100 = hoechstes Risiko)
            - payment_behavior_score: 0-100 (100 = bester Zahler)
            - factors: Detaillierte Risikofaktoren
        """
        factors = await self._collect_factors(db, entity_id)

        # Einzelne Scores berechnen (jeweils 0-100, hoeher = riskanter)
        payment_delay_score = self._score_payment_delay(factors.payment_delay_days)
        default_rate_score = self._score_default_rate(factors.default_rate)
        invoice_volume_score = self._score_invoice_volume(factors.invoice_volume)
        document_frequency_score = self._score_document_frequency(factors.document_frequency)
        relationship_age_score = self._score_relationship_age(factors.relationship_months)

        if self._use_v2:
            # V2: Berechne zusaetzliche Faktoren
            industry_risk_score = factors.industry_risk_score
            payment_trend_score = self._score_payment_trend(factors.trend_slope, factors.payment_trend)
            economic_score = factors.economic_indicator_score

            # Gewichteter Gesamt-Risiko-Score (V2)
            risk_score = (
                payment_delay_score * self._weights["payment_delay"]
                + default_rate_score * self._weights["default_rate"]
                + invoice_volume_score * self._weights["invoice_volume"]
                + document_frequency_score * self._weights["document_frequency"]
                + relationship_age_score * self._weights["relationship_age"]
                + industry_risk_score * self._weights["industry_risk"]
                + payment_trend_score * self._weights["payment_trend"]
                + economic_score * self._weights["economic_indicators"]
            )
        else:
            # V1: Original Berechnung
            risk_score = (
                payment_delay_score * self._weights["payment_delay"]
                + default_rate_score * self._weights["default_rate"]
                + invoice_volume_score * self._weights["invoice_volume"]
                + document_frequency_score * self._weights["document_frequency"]
                + relationship_age_score * self._weights["relationship_age"]
            )

        # Payment Behavior Score (umgekehrte Skala: hoeher = besser)
        # Hauptsaechlich basierend auf Zahlungsverzoegerung und Ausfallrate
        payment_behavior_score = 100 - (
            payment_delay_score * 0.6 + default_rate_score * 0.4
        )

        return (
            min(100, max(0, risk_score)),
            min(100, max(0, payment_behavior_score)),
            factors,
        )

    async def calculate_risk_score_detailed(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> RiskScoreDetailedResponse:
        """
        Berechnet detaillierten Risiko-Score mit allen Faktoren.

        Returns:
            RiskScoreDetailedResponse mit allen Details
        """
        factors = await self._collect_factors(db, entity_id)

        # Berechne alle Einzelscores
        payment_delay_score = self._score_payment_delay(factors.payment_delay_days)
        default_rate_score = self._score_default_rate(factors.default_rate)
        invoice_volume_score = self._score_invoice_volume(factors.invoice_volume)
        document_frequency_score = self._score_document_frequency(factors.document_frequency)
        relationship_age_score = self._score_relationship_age(factors.relationship_months)

        # Erstelle detaillierte Faktor-Objekte
        factor_details: Dict[str, RiskFactor] = {
            "payment_delay": RiskFactor(
                name="payment_delay",
                value=factors.payment_delay_days,
                score=payment_delay_score,
                weight=self._weights["payment_delay"],
                weighted_score=payment_delay_score * self._weights["payment_delay"],
                description=f"Durchschnittliche Zahlungsverzoegerung: {factors.payment_delay_days:.1f} Tage",
            ),
            "default_rate": RiskFactor(
                name="default_rate",
                value=factors.default_rate * 100,
                score=default_rate_score,
                weight=self._weights["default_rate"],
                weighted_score=default_rate_score * self._weights["default_rate"],
                description=f"Ausfallrate: {factors.default_rate * 100:.1f}%",
            ),
            "invoice_volume": RiskFactor(
                name="invoice_volume",
                value=factors.invoice_volume,
                score=invoice_volume_score,
                weight=self._weights["invoice_volume"],
                weighted_score=invoice_volume_score * self._weights["invoice_volume"],
                description=f"Rechnungsvolumen: {factors.invoice_volume:,.2f} EUR",
            ),
            "document_frequency": RiskFactor(
                name="document_frequency",
                value=factors.document_frequency,
                score=document_frequency_score,
                weight=self._weights["document_frequency"],
                weighted_score=document_frequency_score * self._weights["document_frequency"],
                description=f"Dokumentenfrequenz: {factors.document_frequency:.1f} pro Monat",
            ),
            "relationship_age": RiskFactor(
                name="relationship_age",
                value=factors.relationship_months,
                score=relationship_age_score,
                weight=self._weights["relationship_age"],
                weighted_score=relationship_age_score * self._weights["relationship_age"],
                description=f"Beziehungsdauer: {factors.relationship_months:.1f} Monate",
            ),
        }

        overall_score = sum(f.weighted_score for f in factor_details.values())

        if self._use_v2:
            # V2: Zusaetzliche Faktoren
            industry_risk_score = factors.industry_risk_score
            payment_trend_score = self._score_payment_trend(factors.trend_slope, factors.payment_trend)
            economic_score = factors.economic_indicator_score

            factor_details["industry_risk"] = RiskFactor(
                name="industry_risk",
                value=factors.industry_risk_score,
                score=industry_risk_score,
                weight=self._weights["industry_risk"],
                weighted_score=industry_risk_score * self._weights["industry_risk"],
                description=f"Branchenrisiko ({factors.industry_code}): {factors.industry_risk_score:.0f}",
            )

            factor_details["payment_trend"] = RiskFactor(
                name="payment_trend",
                value=factors.trend_slope,
                score=payment_trend_score,
                weight=self._weights["payment_trend"],
                weighted_score=payment_trend_score * self._weights["payment_trend"],
                description=self._get_trend_description(factors.payment_trend, factors.trend_slope),
            )

            factor_details["economic_indicators"] = RiskFactor(
                name="economic_indicators",
                value=economic_score,
                score=economic_score,
                weight=self._weights["economic_indicators"],
                weighted_score=economic_score * self._weights["economic_indicators"],
                description="Wirtschaftliche Indikatoren (externe Daten)",
            )

            overall_score = sum(f.weighted_score for f in factor_details.values())

        # Risk Level bestimmen
        risk_level = self._get_risk_level(overall_score)

        # Payment Behavior Score
        payment_behavior_score = 100 - (
            factor_details["payment_delay"].score * 0.6
            + factor_details["default_rate"].score * 0.4
        )

        # Empfehlungen generieren
        recommendations = self._generate_recommendations(factors, risk_level)

        return RiskScoreDetailedResponse(
            entity_id=entity_id,
            overall_score=int(min(100, max(0, overall_score))),
            risk_level=risk_level,
            factors=factor_details,
            trend=factors.payment_trend,
            trend_score_adjustment=factors.trend_adjustment,
            last_calculated=datetime.now(timezone.utc),
            recommendations=recommendations,
            payment_behavior_score=max(0, min(100, payment_behavior_score)),
            version=self.version,
        )

    async def _collect_factors(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> RiskFactors:
        """Sammelt alle Risikofaktoren fuer einen Geschaeftspartner."""
        factors = RiskFactors()

        # Entity abrufen
        entity_result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()

        if not entity:
            return factors

        # Basis-Statistiken aus Entity
        factors.invoice_volume = entity.total_invoice_amount or 0.0

        # Beziehungsdauer berechnen
        if entity.first_document_date:
            age_delta = datetime.now(entity.first_document_date.tzinfo) - entity.first_document_date
            factors.relationship_months = age_delta.days / 30.0
        else:
            factors.relationship_months = 0.0

        # Dokumentenfrequenz berechnen
        if entity.document_count and entity.first_document_date and entity.last_document_date:
            span_days = (entity.last_document_date - entity.first_document_date).days
            if span_days > 0:
                factors.document_frequency = (entity.document_count / span_days) * 30  # Pro Monat
            else:
                factors.document_frequency = float(entity.document_count)
        else:
            factors.document_frequency = 0.0

        # Invoice Tracking Daten abrufen
        await self._collect_invoice_factors(db, entity_id, factors)

        if self._use_v2:
            # V2: Industry Risk
            industry_code = self._get_industry_code(entity)
            factors.industry_code = industry_code
            factors.industry_risk_score = float(INDUSTRY_RISK_SCORES.get(industry_code, 50))

            # V2: Payment Trend Analysis
            await self._analyze_payment_trend(db, entity_id, factors)

            # V2: External Data (wenn Provider verfuegbar)
            await self._fetch_external_data(entity_id, entity.vat_id, factors)

        return factors

    def _get_industry_code(self, entity: BusinessEntity) -> str:
        """
        Bestimmt den Branchencode fuer eine Entity.

        Aktuell basierend auf risk_factors JSONB oder Default.
        In Zukunft: Erweiterbar durch Lexware-Import oder manuelle Eingabe.
        """
        if entity.risk_factors and isinstance(entity.risk_factors, dict):
            industry = entity.risk_factors.get("industry_code")
            if industry and industry in INDUSTRY_RISK_SCORES:
                return str(industry)

        # TODO: Erkennung aus Name/Branche/Lexware-Daten
        # Vorerst: Default
        return "unknown"

    async def _collect_invoice_factors(
        self,
        db: AsyncSession,
        entity_id: UUID,
        factors: RiskFactors,
    ) -> None:
        """Sammelt Rechnungs-bezogene Faktoren."""
        # Alle Rechnungen des Geschaeftspartners finden
        # Ueber Document -> InvoiceTracking
        invoice_query = (
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    Document.deleted_at.is_(None),
                )
            )
        )

        invoice_result = await db.execute(invoice_query)
        invoices = invoice_result.scalars().all()

        if not invoices:
            return

        factors.total_invoices = len(invoices)

        # Zahlungsstatus analysieren
        paid_invoices = []
        overdue_count = 0
        open_count = 0

        now = datetime.now(timezone.utc)

        for inv in invoices:
            if inv.status == "paid":
                paid_invoices.append(inv)
                factors.paid_invoices += 1
            elif inv.status in ("overdue", "dunning"):
                overdue_count += 1
                factors.overdue_invoices += 1
            elif inv.status in ("open", "sent"):
                # Pruefen ob ueberfaellig (UTC-Vergleich)
                due_utc = inv.due_date.replace(tzinfo=timezone.utc) if inv.due_date and not inv.due_date.tzinfo else inv.due_date
                if due_utc and due_utc < now:
                    overdue_count += 1
                    factors.overdue_invoices += 1
                else:
                    open_count += 1
                    factors.open_invoices += 1

        # Zahlungsverzoegerung berechnen
        if paid_invoices:
            delay_days = []
            for inv in paid_invoices:
                if inv.paid_at and inv.due_date:
                    paid_date = inv.paid_at.replace(tzinfo=None) if inv.paid_at.tzinfo else inv.paid_at
                    due_date = inv.due_date.replace(tzinfo=None) if inv.due_date.tzinfo else inv.due_date
                    delay = (paid_date - due_date).days
                    if delay > 0:  # Nur Verzoegerungen zaehlen
                        delay_days.append(delay)

            if delay_days:
                factors.payment_delay_days = sum(delay_days) / len(delay_days)

        # Ausfallrate berechnen (ueberfaellige / total)
        if factors.total_invoices > 0:
            factors.default_rate = overdue_count / factors.total_invoices

    async def _analyze_payment_trend(
        self,
        db: AsyncSession,
        entity_id: UUID,
        factors: RiskFactors,
    ) -> None:
        """
        Analysiert den Zahlungstrend der letzten 12 Monate.

        Verwendet lineare Regression auf Zahlungsverzoegerungen:
        - Steigung negativ -> Verbesserung (frueheres Zahlen)
        - Steigung ~0 -> Stabil
        - Steigung positiv -> Verschlechterung (spaeteres Zahlen)
        """
        # Zahlungshistorie der letzten 12 Monate abrufen
        twelve_months_ago = datetime.now(timezone.utc) - timedelta(days=365)

        history_query = (
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.business_entity_id == entity_id,
                    Document.deleted_at.is_(None),
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at.isnot(None),
                    InvoiceTracking.due_date.isnot(None),
                    InvoiceTracking.paid_at >= twelve_months_ago,
                )
            )
            .order_by(InvoiceTracking.paid_at.asc())
        )

        result = await db.execute(history_query)
        paid_invoices = result.scalars().all()

        if len(paid_invoices) < 3:
            # Nicht genug Daten fuer Trend-Analyse
            factors.payment_trend = TrendDirection.STABLE
            factors.trend_slope = 0.0
            factors.trend_adjustment = 0
            return

        # Berechne Zahlungsverzoegerungen mit Zeitstempel
        data_points: List[Tuple[float, float]] = []

        for inv in paid_invoices:
            if inv.paid_at and inv.due_date:
                paid_date = inv.paid_at.replace(tzinfo=None) if inv.paid_at.tzinfo else inv.paid_at
                due_date = inv.due_date.replace(tzinfo=None) if inv.due_date.tzinfo else inv.due_date
                delay_days = (paid_date - due_date).days

                # X = Monate seit Beginn des Beobachtungszeitraums
                months_elapsed = (paid_date - twelve_months_ago.replace(tzinfo=None)).days / 30.0
                data_points.append((months_elapsed, float(delay_days)))

        if len(data_points) < 3:
            factors.payment_trend = TrendDirection.STABLE
            factors.trend_slope = 0.0
            factors.trend_adjustment = 0
            return

        # Lineare Regression: y = mx + b
        slope, _ = self._linear_regression(data_points)
        factors.trend_slope = slope

        # Trend-Klassifikation und Score-Anpassung
        if slope <= -0.5:
            # Deutliche Verbesserung: >0.5 Tage pro Monat schneller
            factors.payment_trend = TrendDirection.IMPROVING
            factors.trend_adjustment = max(-20, int(slope * 4))  # -10 bis -20
        elif slope >= 0.5:
            # Deutliche Verschlechterung: >0.5 Tage pro Monat langsamer
            factors.payment_trend = TrendDirection.WORSENING
            factors.trend_adjustment = min(30, int(slope * 4))  # +10 bis +30
        else:
            # Stabil: -0.5 bis +0.5 Tage/Monat
            factors.payment_trend = TrendDirection.STABLE
            factors.trend_adjustment = 0

    def _linear_regression(self, data_points: List[Tuple[float, float]]) -> Tuple[float, float]:
        """
        Einfache lineare Regression (Least Squares).

        Args:
            data_points: List of (x, y) tuples

        Returns:
            (slope, intercept)
        """
        n = len(data_points)
        if n == 0:
            return 0.0, 0.0

        sum_x = sum(p[0] for p in data_points)
        sum_y = sum(p[1] for p in data_points)
        sum_xy = sum(p[0] * p[1] for p in data_points)
        sum_xx = sum(p[0] * p[0] for p in data_points)

        denominator = n * sum_xx - sum_x * sum_x
        if abs(denominator) < 1e-10:
            return 0.0, sum_y / n if n > 0 else 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n

        return slope, intercept

    async def _fetch_external_data(
        self,
        entity_id: UUID,
        vat_id: Optional[str],
        factors: RiskFactors,
    ) -> None:
        """
        Ruft externe Daten von konfigurierten Providern ab.

        Aktuell: Alle Provider sind Stubs (nicht implementiert).
        Bei Konfiguration: Ersten verfuegbaren Provider nutzen.
        """
        for provider in self._external_providers:
            try:
                if await provider.is_available():
                    data = await provider.get_company_data(entity_id, vat_id)
                    if data:
                        factors.external_data = data
                        # Externer Score beeinflusst economic_indicator_score
                        if data.credit_score:
                            # Normalisiere externen Score auf 0-100 (hoeher = riskanter)
                            # Annahme: Externer Score ist 0-100, niedrig = gut
                            factors.economic_indicator_score = float(data.credit_score)
                        break
            except Exception as e:
                logger.warning(
                    "external_data_fetch_failed",
                    provider=provider.provider_name,
                    entity_id=str(entity_id),
                    error=str(e),
                )

    def _score_payment_delay(self, delay_days: float) -> float:
        """Bewertet Zahlungsverzoegerung. 0 Tage = 0 Score, 30+ Tage = 100."""
        if delay_days <= 0:
            return 0.0
        if delay_days >= 30:
            return 100.0
        return (delay_days / 30) * 100

    def _score_default_rate(self, rate: float) -> float:
        """Bewertet Ausfallrate. 0% = 0 Score, 20%+ = 100."""
        if rate <= 0:
            return 0.0
        if rate >= 0.20:
            return 100.0
        return (rate / 0.20) * 100

    def _score_invoice_volume(self, volume: float) -> float:
        """Bewertet Rechnungsvolumen. Niedriger = riskanter (weniger Engagement)."""
        # 0 EUR = 80 Score (keine Historie), 100k+ EUR = 0 Score (etabliert)
        if volume <= 0:
            return 80.0
        if volume >= 100000:
            return 0.0
        # Lineare Abnahme
        return 80 - (volume / 100000) * 80

    def _score_document_frequency(self, freq_per_month: float) -> float:
        """Bewertet Dokumentenfrequenz. Unregelmaessig = riskanter."""
        # 0 Dokumente/Monat = 60 Score, 10+ = 0 Score
        if freq_per_month <= 0:
            return 60.0
        if freq_per_month >= 10:
            return 0.0
        return 60 - (freq_per_month / 10) * 60

    def _score_relationship_age(self, months: float) -> float:
        """Bewertet Beziehungsdauer. Kuerzer = riskanter."""
        # 0 Monate = 70 Score, 24+ Monate = 0 Score
        if months <= 0:
            return 70.0
        if months >= 24:
            return 0.0
        return 70 - (months / 24) * 70

    def _score_payment_trend(self, slope: float, trend: TrendDirection) -> float:
        """
        Bewertet den Zahlungstrend.

        - Verbessernder Trend (slope < 0): Niedriger Score (gut)
        - Stabiler Trend (slope ~0): Mittlerer Score
        - Verschlechternder Trend (slope > 0): Hoher Score (schlecht)
        """
        if trend == TrendDirection.IMPROVING:
            # Stark verbessernd: Score 0-30
            return max(0, 30 + slope * 10)  # slope ist negativ
        elif trend == TrendDirection.WORSENING:
            # Verschlechternd: Score 60-100
            return min(100, 60 + slope * 10)  # slope ist positiv
        else:
            # Stabil: Score 30-60
            return 45 + slope * 10

    def _get_risk_level(self, score: float) -> RiskLevel:
        """Bestimmt das Risiko-Level basierend auf dem Score."""
        if score < 25:
            return RiskLevel.LOW
        elif score < 50:
            return RiskLevel.MEDIUM
        elif score < 75:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _get_trend_description(self, trend: TrendDirection, slope: float) -> str:
        """Generiert eine deutsche Beschreibung fuer den Trend."""
        if trend == TrendDirection.IMPROVING:
            return f"Zahlungsverhalten verbessert sich ({abs(slope):.1f} Tage/Monat schneller)"
        elif trend == TrendDirection.WORSENING:
            return f"Zahlungsverhalten verschlechtert sich ({slope:.1f} Tage/Monat langsamer)"
        else:
            return "Zahlungsverhalten ist stabil"

    def _generate_recommendations(
        self,
        factors: RiskFactors,
        risk_level: RiskLevel,
    ) -> List[str]:
        """
        Generiert deutsche Empfehlungen basierend auf Risikofaktoren.
        """
        recommendations: List[str] = []

        # Empfehlungen basierend auf einzelnen Faktoren
        if factors.payment_delay_days > 14:
            recommendations.append(
                "Straffere Zahlungsbedingungen vereinbaren (z.B. Vorkasse, kuerzere Zahlungsziele)"
            )

        if factors.default_rate > 0.1:
            recommendations.append(
                "Kreditlimit ueberpruefen und ggf. reduzieren"
            )

        if factors.payment_trend == TrendDirection.WORSENING:
            recommendations.append(
                "Zahlerverhalten beobachten - moegliche Liquiditaetsprobleme"
            )
        elif factors.payment_trend == TrendDirection.IMPROVING:
            recommendations.append(
                "Positiver Trend - Geschaeftsbeziehung ausbauen moeglich"
            )

        if factors.industry_risk_score >= 70:
            recommendations.append(
                f"Branche ({factors.industry_code}) hat erhoehtes Risiko - besondere Vorsicht geboten"
            )

        if factors.relationship_months < 6:
            recommendations.append(
                "Neue Geschaeftsbeziehung - engmaschigere Ueberwachung empfohlen"
            )

        # Allgemeine Empfehlungen basierend auf Gesamt-Risiko
        if risk_level == RiskLevel.CRITICAL:
            recommendations.insert(0, "ACHTUNG: Kritisches Risiko - Lieferstopp oder Vorkasse empfohlen")
        elif risk_level == RiskLevel.HIGH:
            recommendations.insert(0, "Hohes Risiko - manuelle Freigabe fuer groessere Auftraege erforderlich")

        if not recommendations:
            recommendations.append("Keine besonderen Massnahmen erforderlich")

        return recommendations

    async def update_entity_risk_score(
        self,
        db: AsyncSession,
        entity_id: UUID,
    ) -> Optional[BusinessEntity]:
        """
        Aktualisiert den Risiko-Score eines Geschaeftspartners.

        Returns:
            Updated BusinessEntity or None if not found
        """
        risk_score, payment_score, factors = await self.calculate_risk_score(db, entity_id)

        # Entity aktualisieren
        result = await db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()

        if not entity:
            logger.warning(
                "entity_not_found_for_risk_update",
                entity_id=str(entity_id),
            )
            return None

        entity.risk_score = risk_score
        entity.payment_behavior_score = payment_score
        entity.risk_factors = factors.to_dict()
        entity.risk_calculated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(entity)

        # SECURITY: Kein entity.name loggen (PII) - nur entity_id
        logger.info(
            "risk_score_updated",
            entity_id=str(entity.id),
            risk_score=round(risk_score, 1),
            payment_behavior_score=round(payment_score, 1),
            version=self.version,
        )

        return entity

    async def update_all_risk_scores(
        self,
        db: AsyncSession,
        entity_type: Optional[str] = None,
        limit: int = 1000,
    ) -> int:
        """
        Aktualisiert Risiko-Scores fuer alle (oder gefilterte) Geschaeftspartner.

        Returns:
            Number of updated entities
        """
        query = select(BusinessEntity.id).where(
            and_(
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
            )
        )

        if entity_type:
            query = query.where(BusinessEntity.entity_type == entity_type)

        query = query.limit(limit)

        result = await db.execute(query)
        entity_ids = [row[0] for row in result.fetchall()]

        updated_count = 0
        for entity_id in entity_ids:
            try:
                await self.update_entity_risk_score(db, entity_id)
                updated_count += 1
            except Exception as e:
                logger.error(
                    "risk_score_update_failed",
                    entity_id=str(entity_id),
                    error=str(e),
                )

        logger.info(
            "risk_scores_batch_updated",
            updated_count=updated_count,
            version=self.version,
        )
        return updated_count

    async def save_risk_score_history(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        score: float,
        factors: RiskFactors,
        trigger_event: str = "scheduled",
    ) -> RiskScoreHistory:
        """
        Speichert einen Risk-Score-Eintrag in der Historie.

        Args:
            db: Database session
            entity_id: Entity ID
            company_id: Company ID
            score: Calculated risk score
            factors: Risk factors used
            trigger_event: What triggered the calculation

        Returns:
            Created RiskScoreHistory entry
        """
        history_entry = RiskScoreHistory(
            entity_id=entity_id,
            company_id=company_id,
            score=score,
            risk_level=self._get_risk_level(score).value.lower(),
            factors=factors.to_dict(),
            trigger_event=trigger_event,
            calculated_at=datetime.now(timezone.utc),
        )

        db.add(history_entry)
        await db.commit()
        await db.refresh(history_entry)

        return history_entry

    async def get_historical_trend(
        self,
        db: AsyncSession,
        entity_id: UUID,
        days: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Ruft historische Risk-Scores fuer Trend-Anzeige ab.

        Args:
            db: Database session
            entity_id: Entity ID
            days: Number of days to look back

        Returns:
            List of {date, score, risk_level} dicts
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            select(RiskScoreHistory)
            .where(
                and_(
                    RiskScoreHistory.entity_id == entity_id,
                    RiskScoreHistory.calculated_at >= cutoff_date,
                )
            )
            .order_by(RiskScoreHistory.calculated_at.asc())
        )

        result = await db.execute(query)
        history = result.scalars().all()

        return [
            {
                "date": entry.calculated_at.isoformat(),
                "score": entry.score,
                "risk_level": entry.risk_level,
            }
            for entry in history
        ]


# Singleton instance
_risk_scoring_service: Optional[RiskScoringService] = None


def get_risk_scoring_service(use_v2: bool = True) -> RiskScoringService:
    """
    Returns singleton instance of RiskScoringService.

    Args:
        use_v2: Use V2 weights and features (default: True)
    """
    global _risk_scoring_service
    if _risk_scoring_service is None:
        _risk_scoring_service = RiskScoringService(use_v2_weights=use_v2)
    return _risk_scoring_service


def reset_risk_scoring_service() -> None:
    """Reset the singleton instance (for testing)."""
    global _risk_scoring_service
    _risk_scoring_service = None
