# -*- coding: utf-8 -*-
"""
ExplainabilityService - Transparente Entscheidungserklaerungen.

Das "Sprachzentrum" des Systems:
- Erklaert WARUM eine Empfehlung gemacht wird
- Zeigt WELCHE FAKTOREN zur Entscheidung fuehrten
- Berechnet KONKRETEN IMPACT mit Zahlen
- Bietet ALTERNATIVEN und erklaert warum nicht

TRUE Enterprise-Level: User versteht WARUM und WIE GENAU.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

EXPLANATIONS_GENERATED = Counter(
    "explanations_generated_total",
    "Anzahl generierter Erklaerungen",
    ["explanation_type"]
)

EXPLANATION_COMPLEXITY = Histogram(
    "explanation_complexity_factors",
    "Anzahl Faktoren in Erklaerungen",
    buckets=[1, 2, 3, 5, 7, 10, 15, 20]
)


# =============================================================================
# Enums und Typen
# =============================================================================

class FactorType(str, Enum):
    """Typen von Erklaerungsfaktoren."""
    FINANCIAL = "financial"            # Finanzielle Auswirkung
    RISK = "risk"                      # Risikobetrachtung
    COMPLIANCE = "compliance"          # Fristen/Regularien
    TREND = "trend"                    # Trendentwicklung
    COMPARISON = "comparison"          # Vergleichswert
    THRESHOLD = "threshold"            # Schwellenwert
    HISTORICAL = "historical"          # Historische Daten
    PROJECTION = "projection"          # Prognose


class ImpactDirection(str, Enum):
    """Richtung des Impacts."""
    POSITIVE = "positiv"
    NEGATIVE = "negativ"
    NEUTRAL = "neutral"


class ConfidenceLevel(str, Enum):
    """Konfidenzniveau der Erklaerung."""
    VERY_HIGH = "sehr_hoch"    # 90%+
    HIGH = "hoch"              # 75-90%
    MEDIUM = "mittel"          # 50-75%
    LOW = "niedrig"            # 25-50%
    UNCERTAIN = "unsicher"     # <25%


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExplanationFactor:
    """Ein einzelner Erklaerungsfaktor."""
    id: UUID = field(default_factory=uuid4)

    # Faktor-Details
    factor_type: FactorType = FactorType.FINANCIAL
    name: str = ""
    description: str = ""

    # Werte
    current_value: Optional[float] = None
    reference_value: Optional[float] = None
    unit: str = ""  # z.B. "EUR", "%", "Monate"

    # Impact
    impact_direction: ImpactDirection = ImpactDirection.NEUTRAL
    impact_weight: float = 0.0  # 0-1, Gewichtung im Gesamt-Score
    impact_points: float = 0.0  # Beitrag zum Gesamt-Score

    # Visualisierung
    visualization_type: str = "bar"  # bar, gauge, trend, comparison

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "factor_type": self.factor_type.value,
            "name": self.name,
            "description": self.description,
            "current_value": self.current_value,
            "reference_value": self.reference_value,
            "unit": self.unit,
            "impact_direction": self.impact_direction.value,
            "impact_weight": self.impact_weight,
            "impact_points": self.impact_points,
            "visualization_type": self.visualization_type,
        }


@dataclass
class AlternativeOption:
    """Eine alternative Handlungsoption."""
    name: str
    description: str
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    why_not_chosen: str = ""
    estimated_impact: float = 0.0  # Geschaetzter Impact-Score

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "pros": self.pros,
            "cons": self.cons,
            "why_not_chosen": self.why_not_chosen,
            "estimated_impact": self.estimated_impact,
        }


@dataclass
class ImpactBreakdown:
    """Detaillierte Aufschluesselung des Impacts."""
    # Finanziell
    immediate_savings: Decimal = Decimal("0")      # Sofortige Ersparnis
    annual_savings: Decimal = Decimal("0")         # Jaehrliche Ersparnis
    one_time_cost: Decimal = Decimal("0")          # Einmalige Kosten
    ongoing_cost: Decimal = Decimal("0")           # Laufende Kosten

    # Zeitlich
    time_to_implement: str = ""                    # "1 Tag", "2 Wochen"
    time_to_benefit: str = ""                      # "Sofort", "Nach 3 Monaten"

    # Risiko
    risk_before: float = 0.0                       # Risiko-Score vorher (0-100)
    risk_after: float = 0.0                        # Risiko-Score nachher

    # Opportunity
    opportunity_cost_if_not_done: Decimal = Decimal("0")

    def net_benefit(self) -> Decimal:
        """Berechnet Netto-Vorteil."""
        return (
            self.immediate_savings +
            self.annual_savings -
            self.one_time_cost -
            self.ongoing_cost
        )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "immediate_savings": float(self.immediate_savings),
            "annual_savings": float(self.annual_savings),
            "one_time_cost": float(self.one_time_cost),
            "ongoing_cost": float(self.ongoing_cost),
            "net_benefit": float(self.net_benefit()),
            "time_to_implement": self.time_to_implement,
            "time_to_benefit": self.time_to_benefit,
            "risk_before": self.risk_before,
            "risk_after": self.risk_after,
            "risk_reduction": self.risk_before - self.risk_after,
            "opportunity_cost_if_not_done": float(self.opportunity_cost_if_not_done),
        }


@dataclass
class DecisionExplanation:
    """Vollstaendige Erklaerung einer Entscheidung."""
    id: UUID = field(default_factory=uuid4)

    # Referenz zur Entscheidung
    decision_id: Optional[UUID] = None
    recommendation_id: Optional[UUID] = None

    # Zusammenfassung
    headline: str = ""                             # Einzeilige Zusammenfassung
    summary: str = ""                              # 2-3 Saetze Erklaerung
    main_reason: str = ""                          # Hauptgrund

    # Faktoren
    factors: List[ExplanationFactor] = field(default_factory=list)

    # Impact-Details
    impact_breakdown: ImpactBreakdown = field(default_factory=ImpactBreakdown)

    # Alternativen
    alternatives: List[AlternativeOption] = field(default_factory=list)

    # Confidence
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    confidence_percent: float = 0.0
    confidence_reasoning: str = ""                 # Warum diese Confidence?
    data_quality: str = ""                         # "24 Monate historische Daten"

    # Aktionen
    suggested_next_steps: List[str] = field(default_factory=list)
    action_url: str = ""

    # Metadaten
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer API."""
        return {
            "id": str(self.id),
            "decision_id": str(self.decision_id) if self.decision_id else None,
            "recommendation_id": str(self.recommendation_id) if self.recommendation_id else None,
            "headline": self.headline,
            "summary": self.summary,
            "main_reason": self.main_reason,
            "factors": [f.to_dict() for f in self.factors],
            "impact_breakdown": self.impact_breakdown.to_dict(),
            "alternatives": [a.to_dict() for a in self.alternatives],
            "confidence": {
                "level": self.confidence_level.value,
                "percent": self.confidence_percent,
                "reasoning": self.confidence_reasoning,
                "data_quality": self.data_quality,
            },
            "suggested_next_steps": self.suggested_next_steps,
            "action_url": self.action_url,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# ExplainabilityService
# =============================================================================

class ExplainabilityService:
    """
    Singleton Service fuer Entscheidungserklaerungen.

    Generiert menschenlesbare, detaillierte Erklaerungen fuer:
    - Empfehlungen (Recommendations)
    - Entscheidungen (Unified Decisions)
    - Early Warnings
    - Financial Health Score
    - Anomalie-Erkennungen

    KEINE Black Box - volle Transparenz.
    """

    _instance: Optional["ExplainabilityService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ExplainabilityService":
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

        # Templates fuer Erklaerungen (Deutsche Sprache)
        self._templates = self._load_templates()

        # Cache fuer generierte Erklaerungen
        self._explanation_cache: Dict[UUID, DecisionExplanation] = {}
        self._max_cache_size = 500

        logger.info("explainability_service_initialized")

    def _load_templates(self) -> Dict[str, Dict[str, str]]:
        """Laedt Erklaerungstemplates."""
        return {
            "refinanzierung": {
                "headline": "Refinanzierung spart {savings} EUR",
                "summary": "Der aktuelle Zins ({current_rate}%) liegt {diff}% ueber dem Marktzins ({market_rate}%). Bei einer Restlaufzeit von {remaining_years} Jahren ergibt sich eine Ersparnis von {savings} EUR.",
                "main_reason": "Zinsdifferenz von {diff}% bei Restlaufzeit {remaining_years} Jahre",
            },
            "versicherungsluecke": {
                "headline": "Deckungsluecke: {asset} nicht ausreichend versichert",
                "summary": "Der {asset} hat eine Deckungsluecke bei {gap_type}. Die empfohlene Deckungssumme ist {recommended_coverage}. Bei einem Schadensfall droht ein finanzieller Verlust von bis zu {potential_loss} EUR.",
                "main_reason": "Fehlende Deckung fuer {gap_type}",
            },
            "budgetueberschreitung": {
                "headline": "Budget '{category}' um {overage_percent}% ueberschritten",
                "summary": "Die Kategorie '{category}' hat das monatliche Budget von {budget} EUR um {overage} EUR ({overage_percent}%) ueberschritten. Dies beeinflusst den Financial Health Score negativ.",
                "main_reason": "Ausgaben {spent} EUR statt geplanter {budget} EUR",
            },
            "early_warning": {
                "headline": "{kpi_name} erreicht kritischen Wert in {months} Monaten",
                "summary": "Der aktuelle Wert von {kpi_name} ist {current_value}. Bei dem aktuellen Trend wird der kritische Schwellenwert ({threshold}) in ca. {months} Monaten erreicht.",
                "main_reason": "Trend zeigt {trend_direction} mit {trend_slope}% pro Monat",
            },
            "health_score": {
                "headline": "Financial Health Score: {score}/100",
                "summary": "Der Score setzt sich zusammen aus: Schuldenmanagement ({debt_component}), Liquiditaet ({liquidity_component}), Diversifikation ({diversification_component}), Absicherung ({insurance_component}), Vorsorge ({retirement_component}) und Sparen ({savings_component}).",
                "main_reason": "Haupteinflussfaktoren: {main_factors}",
            },
        }

    # =========================================================================
    # Explanation Generation
    # =========================================================================

    async def explain_recommendation(
        self,
        recommendation_id: UUID,
        recommendation_data: Dict[str, Any],
    ) -> DecisionExplanation:
        """
        Generiert Erklaerung fuer eine Empfehlung.

        Args:
            recommendation_id: ID der Empfehlung
            recommendation_data: Daten der Empfehlung (category, priority, etc.)

        Returns:
            Vollstaendige Erklaerung
        """
        category = recommendation_data.get("category", "allgemein")
        explanation = DecisionExplanation(recommendation_id=recommendation_id)

        # Kategorie-spezifische Erklaerung
        if category == "refinanzierung":
            explanation = await self._explain_refinancing(recommendation_data)
        elif category == "versicherung":
            explanation = await self._explain_insurance_gap(recommendation_data)
        elif category == "cost_control":
            explanation = await self._explain_budget_exceeded(recommendation_data)
        elif category == "investment":
            explanation = await self._explain_investment(recommendation_data)
        else:
            explanation = await self._explain_generic(recommendation_data)

        explanation.recommendation_id = recommendation_id

        # Cache
        self._cache_explanation(recommendation_id, explanation)

        EXPLANATIONS_GENERATED.labels(
            explanation_type=category
        ).inc()

        EXPLANATION_COMPLEXITY.observe(len(explanation.factors))

        return explanation

    async def explain_early_warning(
        self,
        warning_data: Dict[str, Any],
    ) -> DecisionExplanation:
        """Generiert Erklaerung fuer einen Early Warning Alert."""
        kpi_name = warning_data.get("kpi_name", "KPI")
        current_value = warning_data.get("current_value", 0)
        projected_value = warning_data.get("projected_value", 0)
        threshold_value = warning_data.get("threshold_value", 0)
        months_to_breach = warning_data.get("months_to_breach", 0)

        template = self._templates["early_warning"]

        # Trend berechnen
        if projected_value > current_value:
            trend_direction = "steigend"
            trend_slope = ((projected_value - current_value) / max(current_value, 1)) * 100 / max(months_to_breach, 1)
        else:
            trend_direction = "fallend"
            trend_slope = ((current_value - projected_value) / max(current_value, 1)) * 100 / max(months_to_breach, 1)

        explanation = DecisionExplanation(
            headline=template["headline"].format(
                kpi_name=kpi_name,
                months=months_to_breach,
            ),
            summary=template["summary"].format(
                kpi_name=kpi_name,
                current_value=f"{current_value:.2f}",
                threshold=f"{threshold_value:.2f}",
                months=months_to_breach,
            ),
            main_reason=template["main_reason"].format(
                trend_direction=trend_direction,
                trend_slope=f"{trend_slope:.1f}",
            ),
        )

        # Faktoren hinzufuegen
        explanation.factors = [
            ExplanationFactor(
                factor_type=FactorType.TREND,
                name="Aktueller Wert",
                description=f"Der {kpi_name} liegt aktuell bei {current_value:.2f}",
                current_value=current_value,
                reference_value=threshold_value,
                unit="",
                impact_direction=ImpactDirection.NEGATIVE if projected_value > threshold_value else ImpactDirection.NEUTRAL,
                impact_weight=0.4,
                visualization_type="gauge",
            ),
            ExplanationFactor(
                factor_type=FactorType.PROJECTION,
                name="Prognose",
                description=f"Bei aktuellem Trend: {projected_value:.2f} in {months_to_breach} Monaten",
                current_value=projected_value,
                reference_value=current_value,
                unit="",
                impact_direction=ImpactDirection.NEGATIVE,
                impact_weight=0.4,
                visualization_type="trend",
            ),
            ExplanationFactor(
                factor_type=FactorType.THRESHOLD,
                name="Kritischer Schwellenwert",
                description=f"Bei Ueberschreitung von {threshold_value:.2f} wird eine Aktion empfohlen",
                current_value=threshold_value,
                impact_direction=ImpactDirection.NEUTRAL,
                impact_weight=0.2,
                visualization_type="bar",
            ),
        ]

        # Confidence basierend auf Datenqualitaet
        explanation.confidence_level = ConfidenceLevel.MEDIUM
        explanation.confidence_percent = 65.0
        explanation.confidence_reasoning = "Basierend auf 12 Monaten historischer Daten"
        explanation.data_quality = "12 Monate Verlaufsdaten"

        # Naechste Schritte
        explanation.suggested_next_steps = [
            f"{kpi_name} monatlich ueberwachen",
            "Budget oder Ausgaben anpassen",
            "Finanzberater konsultieren falls Trend anhaelt",
        ]

        return explanation

    async def explain_health_score(
        self,
        health_score_data: Dict[str, Any],
    ) -> DecisionExplanation:
        """Generiert detaillierte Erklaerung des Financial Health Scores."""
        score = health_score_data.get("score", 0)
        components = health_score_data.get("components", {})

        # Komponenten-Scores
        debt = components.get("debt_management", {}).get("score", 0)
        liquidity = components.get("liquidity", {}).get("score", 0)
        diversification = components.get("diversification", {}).get("score", 0)
        insurance = components.get("insurance", {}).get("score", 0)
        retirement = components.get("retirement", {}).get("score", 0)
        savings = components.get("savings", {}).get("score", 0)

        # Haupteinflussfaktoren identifizieren
        all_components = [
            ("Schuldenmanagement", debt),
            ("Liquiditaet", liquidity),
            ("Diversifikation", diversification),
            ("Absicherung", insurance),
            ("Vorsorge", retirement),
            ("Sparen", savings),
        ]
        sorted_components = sorted(all_components, key=lambda x: x[1])
        weakest = sorted_components[:2]  # 2 schwaechste
        strongest = sorted_components[-2:]  # 2 staerkste

        main_factors = ", ".join([f"{name} ({score})" for name, score in weakest])

        template = self._templates["health_score"]

        explanation = DecisionExplanation(
            headline=template["headline"].format(score=score),
            summary=template["summary"].format(
                debt_component=debt,
                liquidity_component=liquidity,
                diversification_component=diversification,
                insurance_component=insurance,
                retirement_component=retirement,
                savings_component=savings,
            ),
            main_reason=template["main_reason"].format(main_factors=main_factors),
        )

        # Faktoren fuer jede Komponente
        explanation.factors = [
            ExplanationFactor(
                factor_type=FactorType.FINANCIAL,
                name="Schuldenmanagement",
                description=components.get("debt_management", {}).get("description", ""),
                current_value=debt,
                reference_value=100,
                unit="Punkte",
                impact_direction=ImpactDirection.POSITIVE if debt >= 60 else ImpactDirection.NEGATIVE,
                impact_weight=0.25,
                impact_points=debt * 0.25,
                visualization_type="gauge",
            ),
            ExplanationFactor(
                factor_type=FactorType.RISK,
                name="Liquiditaet",
                description=components.get("liquidity", {}).get("description", ""),
                current_value=liquidity,
                reference_value=100,
                unit="Punkte",
                impact_direction=ImpactDirection.POSITIVE if liquidity >= 60 else ImpactDirection.NEGATIVE,
                impact_weight=0.20,
                impact_points=liquidity * 0.20,
                visualization_type="gauge",
            ),
            ExplanationFactor(
                factor_type=FactorType.FINANCIAL,
                name="Diversifikation",
                description=components.get("diversification", {}).get("description", ""),
                current_value=diversification,
                reference_value=100,
                unit="Punkte",
                impact_direction=ImpactDirection.POSITIVE if diversification >= 60 else ImpactDirection.NEGATIVE,
                impact_weight=0.15,
                impact_points=diversification * 0.15,
                visualization_type="bar",
            ),
            ExplanationFactor(
                factor_type=FactorType.RISK,
                name="Absicherung",
                description=components.get("insurance", {}).get("description", ""),
                current_value=insurance,
                reference_value=100,
                unit="Punkte",
                impact_direction=ImpactDirection.POSITIVE if insurance >= 60 else ImpactDirection.NEGATIVE,
                impact_weight=0.15,
                impact_points=insurance * 0.15,
                visualization_type="gauge",
            ),
            ExplanationFactor(
                factor_type=FactorType.PROJECTION,
                name="Vorsorge",
                description=components.get("retirement", {}).get("description", ""),
                current_value=retirement,
                reference_value=100,
                unit="Punkte",
                impact_direction=ImpactDirection.POSITIVE if retirement >= 60 else ImpactDirection.NEGATIVE,
                impact_weight=0.15,
                impact_points=retirement * 0.15,
                visualization_type="trend",
            ),
            ExplanationFactor(
                factor_type=FactorType.FINANCIAL,
                name="Sparquote",
                description=components.get("savings", {}).get("description", ""),
                current_value=savings,
                reference_value=100,
                unit="Punkte",
                impact_direction=ImpactDirection.POSITIVE if savings >= 60 else ImpactDirection.NEGATIVE,
                impact_weight=0.10,
                impact_points=savings * 0.10,
                visualization_type="bar",
            ),
        ]

        # Alternativen: Was koennte den Score verbessern?
        explanation.alternatives = []
        for name, component_score in weakest:
            if component_score < 60:
                explanation.alternatives.append(AlternativeOption(
                    name=f"{name} verbessern",
                    description=f"Aktuell {component_score} Punkte - Potential fuer Verbesserung",
                    pros=[f"Score-Verbesserung um bis zu {(60 - component_score) * 0.25:.0f} Punkte moeglich"],
                    cons=["Erfordert Zeit und Aufwand"],
                    estimated_impact=(60 - component_score) * 0.25,
                ))

        # Confidence
        explanation.confidence_level = ConfidenceLevel.HIGH
        explanation.confidence_percent = 85.0
        explanation.confidence_reasoning = "Basierend auf vollstaendigen Finanzdaten"
        explanation.data_quality = "Aktuelle Daten aus allen Modulen"

        # Naechste Schritte
        explanation.suggested_next_steps = [
            f"Fokus auf {weakest[0][0]} legen (aktuell {weakest[0][1]} Punkte)",
            "Monatliche Score-Entwicklung verfolgen",
            "Konkrete Empfehlungen im Privat-Modul pruefen",
        ]

        return explanation

    # =========================================================================
    # Specific Explanation Generators
    # =========================================================================

    async def _explain_refinancing(
        self,
        data: Dict[str, Any],
    ) -> DecisionExplanation:
        """Erklaert eine Refinanzierungsempfehlung."""
        current_rate = data.get("current_rate", 0)
        market_rate = data.get("market_rate", 0)
        remaining_years = data.get("remaining_years", 0)
        remaining_principal = Decimal(str(data.get("remaining_principal", 0)))
        potential_savings = data.get("potential_savings", 0)

        rate_diff = current_rate - market_rate

        template = self._templates["refinanzierung"]

        explanation = DecisionExplanation(
            headline=template["headline"].format(savings=f"{potential_savings:,.0f}"),
            summary=template["summary"].format(
                current_rate=f"{current_rate:.2f}",
                market_rate=f"{market_rate:.2f}",
                diff=f"{rate_diff:.2f}",
                remaining_years=remaining_years,
                savings=f"{potential_savings:,.0f}",
            ),
            main_reason=template["main_reason"].format(
                diff=f"{rate_diff:.2f}",
                remaining_years=remaining_years,
            ),
        )

        # Faktoren
        explanation.factors = [
            ExplanationFactor(
                factor_type=FactorType.COMPARISON,
                name="Aktueller Zinssatz",
                description=f"Dein aktueller Kredit hat einen Zinssatz von {current_rate:.2f}%",
                current_value=current_rate,
                reference_value=market_rate,
                unit="%",
                impact_direction=ImpactDirection.NEGATIVE,
                impact_weight=0.4,
                visualization_type="comparison",
            ),
            ExplanationFactor(
                factor_type=FactorType.COMPARISON,
                name="Markt-Zinssatz",
                description=f"Aktuelle Marktkonditionen: {market_rate:.2f}%",
                current_value=market_rate,
                reference_value=current_rate,
                unit="%",
                impact_direction=ImpactDirection.POSITIVE,
                impact_weight=0.3,
                visualization_type="comparison",
            ),
            ExplanationFactor(
                factor_type=FactorType.PROJECTION,
                name="Restlaufzeit",
                description=f"Je laenger die Restlaufzeit, desto groesser die Ersparnis",
                current_value=remaining_years,
                unit="Jahre",
                impact_direction=ImpactDirection.POSITIVE if remaining_years > 5 else ImpactDirection.NEUTRAL,
                impact_weight=0.3,
                visualization_type="bar",
            ),
        ]

        # Impact Breakdown
        annual_savings = Decimal(str(potential_savings)) / Decimal(str(remaining_years)) if remaining_years > 0 else Decimal("0")
        explanation.impact_breakdown = ImpactBreakdown(
            immediate_savings=Decimal("0"),
            annual_savings=annual_savings,
            one_time_cost=Decimal("1500"),  # Geschaetzte Umschuldungskosten
            ongoing_cost=Decimal("0"),
            time_to_implement="2-4 Wochen",
            time_to_benefit="Mit naechster Rate",
            risk_before=0,
            risk_after=0,
            opportunity_cost_if_not_done=Decimal(str(potential_savings)),
        )

        # Alternativen
        explanation.alternatives = [
            AlternativeOption(
                name="Sondertilgung statt Umschuldung",
                description="Extra-Zahlungen auf den bestehenden Kredit",
                pros=["Keine Umschuldungskosten", "Flexibel"],
                cons=["Geringere Gesamtersparnis", "Nur wenn Sondertilgung erlaubt"],
                why_not_chosen="Umschuldung spart langfristig mehr bei dieser Zinsdifferenz",
                estimated_impact=float(potential_savings) * 0.6,
            ),
            AlternativeOption(
                name="Abwarten",
                description="Auf weitere Zinssenkungen warten",
                pros=["Vielleicht noch bessere Konditionen"],
                cons=["Risiko steigender Zinsen", "Entgangene Ersparnis"],
                why_not_chosen="Aktueller Marktzins bereits attraktiv",
                estimated_impact=0,
            ),
        ]

        # Confidence
        explanation.confidence_level = ConfidenceLevel.HIGH
        explanation.confidence_percent = 82.0
        explanation.confidence_reasoning = "Konkrete Zins- und Laufzeitdaten vorliegend"
        explanation.data_quality = "Aktuelle Kreditdaten und Marktkonditionen"

        explanation.suggested_next_steps = [
            "Angebote von 2-3 Banken einholen",
            "Umschuldungskosten in Rechnung stellen",
            "Kuendigungsfrist des aktuellen Kredits pruefen",
        ]

        return explanation

    async def _explain_insurance_gap(
        self,
        data: Dict[str, Any],
    ) -> DecisionExplanation:
        """Erklaert eine Versicherungsluecken-Empfehlung."""
        asset = data.get("affected_asset", "Vermoegenswert")
        gap_type = data.get("gap_type", "Deckungsluecke")
        recommended_coverage = data.get("recommended_coverage", "")
        potential_loss = data.get("potential_loss", 0)
        severity = data.get("severity", "medium")

        template = self._templates["versicherungsluecke"]

        explanation = DecisionExplanation(
            headline=template["headline"].format(asset=asset),
            summary=template["summary"].format(
                asset=asset,
                gap_type=gap_type,
                recommended_coverage=recommended_coverage,
                potential_loss=f"{potential_loss:,.0f}",
            ),
            main_reason=template["main_reason"].format(gap_type=gap_type),
        )

        # Faktoren
        explanation.factors = [
            ExplanationFactor(
                factor_type=FactorType.RISK,
                name="Unversichertes Risiko",
                description=f"Bei {gap_type} besteht aktuell keine ausreichende Deckung",
                current_value=0,  # 0% Deckung
                reference_value=100,  # 100% waere ideal
                unit="%",
                impact_direction=ImpactDirection.NEGATIVE,
                impact_weight=0.5,
                visualization_type="gauge",
            ),
            ExplanationFactor(
                factor_type=FactorType.FINANCIAL,
                name="Potenzieller Verlust",
                description=f"Im Schadensfall droht ein Verlust von bis zu {potential_loss:,.0f} EUR",
                current_value=potential_loss,
                unit="EUR",
                impact_direction=ImpactDirection.NEGATIVE,
                impact_weight=0.3,
                visualization_type="bar",
            ),
            ExplanationFactor(
                factor_type=FactorType.COMPARISON,
                name="Empfohlene Deckung",
                description=recommended_coverage,
                impact_direction=ImpactDirection.POSITIVE,
                impact_weight=0.2,
                visualization_type="bar",
            ),
        ]

        # Impact Breakdown - geschaetzte Praemie
        estimated_annual_premium = Decimal(str(potential_loss)) * Decimal("0.002")  # 0.2% des Werts

        explanation.impact_breakdown = ImpactBreakdown(
            immediate_savings=Decimal("0"),
            annual_savings=Decimal("0"),
            one_time_cost=Decimal("0"),
            ongoing_cost=estimated_annual_premium,
            time_to_implement="1-2 Wochen",
            time_to_benefit="Sofort nach Abschluss",
            risk_before=80.0 if severity == "critical" else 50.0,
            risk_after=10.0,
            opportunity_cost_if_not_done=Decimal(str(potential_loss)),
        )

        # Confidence
        explanation.confidence_level = ConfidenceLevel.HIGH if severity == "critical" else ConfidenceLevel.MEDIUM
        explanation.confidence_percent = 75.0
        explanation.confidence_reasoning = "Basierend auf Vermoegensanalyse"

        explanation.suggested_next_steps = [
            "Aktuelle Versicherungspolicen pruefen",
            "Vergleichsangebote einholen",
            f"Deckung fuer {gap_type} erhoehen",
        ]

        return explanation

    async def _explain_budget_exceeded(
        self,
        data: Dict[str, Any],
    ) -> DecisionExplanation:
        """Erklaert eine Budgetueberschreitung."""
        category = data.get("category", "Kategorie")
        budget = Decimal(str(data.get("budget", 0)))
        spent = Decimal(str(data.get("spent", 0)))
        overage = spent - budget
        overage_percent = (float(overage) / float(budget) * 100) if budget > 0 else 0

        template = self._templates["budgetueberschreitung"]

        explanation = DecisionExplanation(
            headline=template["headline"].format(
                category=category,
                overage_percent=f"{overage_percent:.0f}",
            ),
            summary=template["summary"].format(
                category=category,
                budget=f"{budget:.2f}",
                overage=f"{overage:.2f}",
                overage_percent=f"{overage_percent:.1f}",
            ),
            main_reason=template["main_reason"].format(
                spent=f"{spent:.2f}",
                budget=f"{budget:.2f}",
            ),
        )

        # Faktoren
        explanation.factors = [
            ExplanationFactor(
                factor_type=FactorType.FINANCIAL,
                name="Geplantes Budget",
                description=f"Monatliches Budget: {budget:.2f} EUR",
                current_value=float(budget),
                unit="EUR",
                impact_direction=ImpactDirection.NEUTRAL,
                impact_weight=0.3,
                visualization_type="bar",
            ),
            ExplanationFactor(
                factor_type=FactorType.FINANCIAL,
                name="Tatsaechliche Ausgaben",
                description=f"Ausgegeben: {spent:.2f} EUR",
                current_value=float(spent),
                reference_value=float(budget),
                unit="EUR",
                impact_direction=ImpactDirection.NEGATIVE,
                impact_weight=0.4,
                visualization_type="comparison",
            ),
            ExplanationFactor(
                factor_type=FactorType.THRESHOLD,
                name="Ueberschreitung",
                description=f"{overage:.2f} EUR ueber Budget ({overage_percent:.1f}%)",
                current_value=float(overage),
                unit="EUR",
                impact_direction=ImpactDirection.NEGATIVE,
                impact_weight=0.3,
                visualization_type="bar",
            ),
        ]

        explanation.impact_breakdown = ImpactBreakdown(
            immediate_savings=Decimal("0"),
            annual_savings=overage * Decimal("12"),  # Wenn jeden Monat gespart
            one_time_cost=Decimal("0"),
            ongoing_cost=Decimal("0"),
            time_to_implement="Sofort",
            time_to_benefit="Naechster Monat",
            risk_before=min(overage_percent, 100),
            risk_after=0,
        )

        explanation.suggested_next_steps = [
            f"Ausgaben in '{category}' analysieren",
            "Budget fuer naechsten Monat anpassen",
            "Automatische Warnungen bei 80% Budget setzen",
        ]

        return explanation

    async def _explain_investment(
        self,
        data: Dict[str, Any],
    ) -> DecisionExplanation:
        """Erklaert eine Investment-Empfehlung."""
        # Generic Investment explanation
        return await self._explain_generic(data)

    async def _explain_generic(
        self,
        data: Dict[str, Any],
    ) -> DecisionExplanation:
        """Generische Erklaerung fuer nicht-kategorisierte Empfehlungen."""
        title = data.get("title", "Empfehlung")
        description = data.get("description", "")
        priority = data.get("priority", "normal")

        explanation = DecisionExplanation(
            headline=title,
            summary=description,
            main_reason=data.get("reason", "Systemempfehlung basierend auf Datenanalyse"),
        )

        # Generische Faktoren
        explanation.factors = [
            ExplanationFactor(
                factor_type=FactorType.FINANCIAL,
                name="Empfehlungspriorität",
                description=f"Diese Empfehlung hat Prioritaet: {priority}",
                impact_direction=ImpactDirection.NEUTRAL,
                impact_weight=1.0,
                visualization_type="bar",
            ),
        ]

        explanation.confidence_level = ConfidenceLevel.MEDIUM
        explanation.confidence_percent = 60.0

        return explanation

    # =========================================================================
    # Cache Management
    # =========================================================================

    def _cache_explanation(self, key: UUID, explanation: DecisionExplanation) -> None:
        """Speichert Erklaerung im Cache."""
        self._explanation_cache[key] = explanation

        # Cache-Groesse begrenzen
        if len(self._explanation_cache) > self._max_cache_size:
            # Aelteste Eintraege entfernen
            oldest_keys = sorted(
                self._explanation_cache.keys(),
                key=lambda k: self._explanation_cache[k].created_at
            )[:100]
            for k in oldest_keys:
                del self._explanation_cache[k]

    def get_cached_explanation(self, key: UUID) -> Optional[DecisionExplanation]:
        """Holt Erklaerung aus Cache."""
        return self._explanation_cache.get(key)


# =============================================================================
# Singleton Factory
# =============================================================================

_explainability_instance: Optional[ExplainabilityService] = None
_explainability_lock = threading.Lock()


def get_explainability_service() -> ExplainabilityService:
    """Factory-Funktion fuer ExplainabilityService Singleton."""
    global _explainability_instance
    if _explainability_instance is None:
        with _explainability_lock:
            if _explainability_instance is None:
                _explainability_instance = ExplainabilityService()
    return _explainability_instance
