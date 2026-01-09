# -*- coding: utf-8 -*-
"""
Proactive Insights Service.

Enterprise Feature: Kontextsensitive, proaktive Insights fuer Chat und UI.

Dieses Modul analysiert User-Aktionen und Chat-Kontext und generiert
automatisch relevante Insights:

- "Du fragst nach Lieferant XY - er ist 23% teurer als der Durchschnitt"
- "Du schaust auf Mieteinnahmen - Miete liegt unter Marktniveau"
- "Du fragst nach Versicherungen - 3 haben ueberlappende Deckung"

TRUE Enterprise-Level: Das System DENKT MIT, nicht nur ANTWORTET.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================

class InsightType(str, Enum):
    """Typ des proaktiven Insights."""
    OPTIMIZATION = "optimization"           # Optimierungsmoeglichkeit
    WARNING = "warning"                     # Warnung/Risiko
    OPPORTUNITY = "opportunity"             # Chance/Gelegenheit
    INFORMATION = "information"             # Neutrale Info
    COMPARISON = "comparison"               # Vergleich
    TREND = "trend"                         # Trend-Erkennung
    ANOMALY = "anomaly"                     # Anomalie
    REMINDER = "reminder"                   # Erinnerung
    RECOMMENDATION = "recommendation"        # Empfehlung


class EntityType(str, Enum):
    """Typ der erkannten Entity."""
    SUPPLIER = "supplier"
    PROPERTY = "property"
    INSURANCE = "insurance"
    LOAN = "loan"
    VEHICLE = "vehicle"
    BANK_ACCOUNT = "bank_account"
    INVESTMENT = "investment"
    DOCUMENT = "document"
    KPI = "kpi"
    CATEGORY = "category"
    GENERAL = "general"


class InsightPriority(str, Enum):
    """Prioritaet des Insights."""
    CRITICAL = "critical"       # Muss gezeigt werden
    HIGH = "high"               # Sollte gezeigt werden
    MEDIUM = "medium"           # Kann gezeigt werden
    LOW = "low"                 # Optional


class ContextSource(str, Enum):
    """Quelle des Kontexts."""
    CHAT_MESSAGE = "chat_message"
    PAGE_VIEW = "page_view"
    SEARCH_QUERY = "search_query"
    REPORT_VIEW = "report_view"
    ENTITY_ACCESS = "entity_access"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExtractedEntity:
    """Eine aus dem Kontext extrahierte Entity."""
    entity_type: EntityType
    entity_id: Optional[UUID] = None
    entity_name: str = ""
    confidence: float = 0.0
    source_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProactiveInsight:
    """Ein proaktiver Insight."""
    id: UUID = field(default_factory=uuid4)
    insight_type: InsightType = InsightType.INFORMATION
    priority: InsightPriority = InsightPriority.MEDIUM
    title: str = ""
    message: str = ""
    detail: str = ""
    related_entities: List[ExtractedEntity] = field(default_factory=list)
    potential_value: Optional[Decimal] = None       # Potenzieller Wert in EUR
    action_url: Optional[str] = None                # URL fuer Aktion
    action_label: Optional[str] = None              # Label fuer Aktion
    expires_at: Optional[datetime] = None           # Wann Insight verfaellt
    context_source: ContextSource = ContextSource.CHAT_MESSAGE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "insight_type": self.insight_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "message": self.message,
            "detail": self.detail,
            "related_entities": [
                {
                    "entity_type": e.entity_type.value,
                    "entity_id": str(e.entity_id) if e.entity_id else None,
                    "entity_name": e.entity_name,
                    "confidence": e.confidence,
                }
                for e in self.related_entities
            ],
            "potential_value": float(self.potential_value) if self.potential_value else None,
            "action_url": self.action_url,
            "action_label": self.action_label,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "context_source": self.context_source.value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EnrichedResponse:
    """Angereicherte Antwort mit proaktiven Insights."""
    original_response: str
    insights: List[ProactiveInsight]
    follow_up_suggestions: List[str]
    enriched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "original_response": self.original_response,
            "insights": [i.to_dict() for i in self.insights],
            "follow_up_suggestions": self.follow_up_suggestions,
            "enriched_at": self.enriched_at.isoformat(),
        }


@dataclass
class UserContext:
    """Aktueller Kontext des Users."""
    user_id: UUID
    space_id: Optional[UUID] = None
    current_page: Optional[str] = None
    recent_queries: List[str] = field(default_factory=list)
    recent_entities: List[ExtractedEntity] = field(default_factory=list)
    session_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Entity Extraction Patterns
# =============================================================================

class EntityPatterns:
    """Muster zur Entity-Erkennung aus Text."""

    # Deutsche Schluesselwoerter fuer Entity-Typen
    PATTERNS = {
        EntityType.SUPPLIER: [
            r"lieferant\s+(\w+)",
            r"von\s+(\w+)\s+(?:gekauft|bestellt|bezogen)",
            r"(?:rechnung|invoice)\s+von\s+(\w+)",
            r"(\w+)\s+lieferung",
        ],
        EntityType.PROPERTY: [
            r"immobilie\s+(\w+)",
            r"wohnung\s+(?:in\s+)?(\w+)",
            r"haus\s+(?:in\s+)?(\w+)",
            r"objekt\s+(\w+)",
            r"miet(?:e|einnahmen?)\s+(?:von\s+)?(\w+)",
        ],
        EntityType.INSURANCE: [
            r"versicherung\s+(\w+)",
            r"(\w+)versicherung",
            r"police\s+(\w+)",
            r"(?:haftpflicht|kasko|leben|kranken)(\w*)",
        ],
        EntityType.LOAN: [
            r"kredit\s+(\w+)",
            r"darlehen\s+(\w+)",
            r"finanzierung\s+(\w+)",
            r"tilgung\s+(\w+)",
        ],
        EntityType.VEHICLE: [
            r"fahrzeug\s+(\w+)",
            r"auto\s+(\w+)",
            r"pkw\s+(\w+)",
            r"(?:bmw|audi|vw|mercedes|ford|opel|toyota)\s+(\w*)",
        ],
        EntityType.KPI: [
            r"(?:dti|debt.to.income)",
            r"sparquote",
            r"health\s*score",
            r"notgroschen",
            r"liquidit",
            r"rendite",
            r"eigenkapital",
        ],
    }

    # Kontext-Schluesselwoerter fuer Insight-Generierung
    CONTEXT_KEYWORDS = {
        "kosten": ["kosten", "preis", "teuer", "guenstig", "sparen", "ausgabe"],
        "risiko": ["risiko", "gefahr", "warnung", "kritisch", "problem"],
        "optimierung": ["optimieren", "verbessern", "steigern", "reduzieren"],
        "vergleich": ["vergleich", "alternative", "besser", "schlechter"],
        "trend": ["trend", "entwicklung", "steigt", "faellt", "stabil"],
    }


# =============================================================================
# Insight Generation Rules
# =============================================================================

@dataclass
class InsightRule:
    """Regel zur Insight-Generierung."""
    rule_id: str
    entity_types: List[EntityType]
    condition: Callable[[Dict[str, Any]], bool]
    generate: Callable[[Dict[str, Any]], ProactiveInsight]
    priority: InsightPriority = InsightPriority.MEDIUM


class InsightRuleEngine:
    """Engine fuer Insight-Generierung basierend auf Regeln."""

    def __init__(self) -> None:
        self._rules: List[InsightRule] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Registriert die Standard-Regeln."""

        # Regel: Lieferant teurer als Durchschnitt
        self._rules.append(InsightRule(
            rule_id="supplier_above_average",
            entity_types=[EntityType.SUPPLIER],
            condition=lambda ctx: ctx.get("price_vs_average", 0) > 10,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.OPTIMIZATION,
                priority=InsightPriority.HIGH,
                title=f"{ctx.get('supplier_name', 'Lieferant')} ueberdurchschnittlich teuer",
                message=f"Dieser Lieferant ist {ctx.get('price_vs_average', 0):.0f}% teurer als der Durchschnitt.",
                detail="Basierend auf Vergleich mit aehnlichen Lieferanten in der gleichen Kategorie.",
                potential_value=Decimal(str(ctx.get("potential_savings", 0))),
                action_url="/suppliers/compare",
                action_label="Alternativen vergleichen",
            ),
        ))

        # Regel: Miete unter Marktniveau
        self._rules.append(InsightRule(
            rule_id="rent_below_market",
            entity_types=[EntityType.PROPERTY],
            condition=lambda ctx: ctx.get("rent_vs_market", 0) < -10,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.OPPORTUNITY,
                priority=InsightPriority.MEDIUM,
                title="Miete unter Marktniveau",
                message=f"Die Miete liegt {abs(ctx.get('rent_vs_market', 0)):.0f}% unter dem Marktniveau.",
                detail="Bei naechster Gelegenheit koennte eine Mietanpassung sinnvoll sein.",
                potential_value=Decimal(str(ctx.get("potential_rent_increase", 0) * 12)),
                action_url=f"/properties/{ctx.get('property_id')}/rent-analysis",
                action_label="Mietanalyse oeffnen",
            ),
        ))

        # Regel: Versicherungsluecke
        self._rules.append(InsightRule(
            rule_id="insurance_gap",
            entity_types=[EntityType.INSURANCE],
            condition=lambda ctx: ctx.get("has_coverage_gap", False),
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.WARNING,
                priority=InsightPriority.CRITICAL,
                title="Versicherungsluecke erkannt",
                message=f"Fuer {ctx.get('asset_type', 'diesen Vermoegenswert')} fehlt {ctx.get('missing_coverage', 'eine wichtige Deckung')}.",
                detail="Ohne diese Deckung besteht ein erhebliches finanzielles Risiko.",
                action_url="/insurance/gaps",
                action_label="Luecke schliessen",
            ),
        ))

        # Regel: Ueberlappende Versicherungen
        self._rules.append(InsightRule(
            rule_id="insurance_overlap",
            entity_types=[EntityType.INSURANCE],
            condition=lambda ctx: len(ctx.get("overlapping_policies", [])) > 1,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.OPTIMIZATION,
                priority=InsightPriority.MEDIUM,
                title="Ueberlappende Versicherungsdeckung",
                message=f"{len(ctx.get('overlapping_policies', []))} Policen haben ueberlappende Deckung.",
                detail="Eine Konsolidierung koennte Praemien sparen.",
                potential_value=Decimal(str(ctx.get("potential_premium_savings", 0))),
                action_url="/insurance/consolidate",
                action_label="Konsolidierung pruefen",
            ),
        ))

        # Regel: Kredit-Refinanzierung moeglich
        self._rules.append(InsightRule(
            rule_id="loan_refinance_opportunity",
            entity_types=[EntityType.LOAN],
            condition=lambda ctx: ctx.get("interest_vs_market", 0) > 0.5,  # 0.5% hoeher
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.OPPORTUNITY,
                priority=InsightPriority.HIGH,
                title="Refinanzierung sinnvoll",
                message=f"Der aktuelle Zins liegt {ctx.get('interest_vs_market', 0):.2f}% ueber dem Marktzins.",
                detail=f"Bei Refinanzierung koennten ca. {ctx.get('potential_savings_annual', 0):,.0f} EUR/Jahr gespart werden.",
                potential_value=Decimal(str(ctx.get("potential_savings_total", 0))),
                action_url=f"/loans/{ctx.get('loan_id')}/refinance",
                action_label="Refinanzierung simulieren",
            ),
        ))

        # Regel: DTI zu hoch
        self._rules.append(InsightRule(
            rule_id="dti_critical",
            entity_types=[EntityType.KPI],
            condition=lambda ctx: ctx.get("dti_ratio", 0) > 40,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.WARNING,
                priority=InsightPriority.CRITICAL,
                title="DTI kritisch hoch",
                message=f"Dein DTI liegt bei {ctx.get('dti_ratio', 0):.1f}% - das ist ueber dem kritischen Schwellenwert.",
                detail="Ein DTI ueber 40% kann zu Kreditablehnungen und finanzieller Belastung fuehren.",
                action_url="/simulator/what-if",
                action_label="Reduktion simulieren",
            ),
        ))

        # Regel: Notgroschen zu niedrig
        self._rules.append(InsightRule(
            rule_id="emergency_fund_low",
            entity_types=[EntityType.KPI],
            condition=lambda ctx: ctx.get("emergency_fund_months", 6) < 3,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.WARNING,
                priority=InsightPriority.HIGH,
                title="Notgroschen aufbauen",
                message=f"Dein Notgroschen reicht nur fuer {ctx.get('emergency_fund_months', 0):.1f} Monate.",
                detail="Experten empfehlen mindestens 3-6 Monatsausgaben als Reserve.",
                action_url="/simulator/what-if",
                action_label="Aufbau simulieren",
            ),
        ))

        # Regel: Positive Trend-Erkennung
        self._rules.append(InsightRule(
            rule_id="positive_trend",
            entity_types=[EntityType.KPI, EntityType.GENERAL],
            condition=lambda ctx: ctx.get("trend_direction") == "up" and ctx.get("trend_strength", 0) > 0.1,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.TREND,
                priority=InsightPriority.LOW,
                title=f"{ctx.get('kpi_name', 'KPI')} verbessert sich",
                message=f"Positiver Trend: +{ctx.get('trend_strength', 0) * 100:.1f}% in den letzten {ctx.get('trend_period', 3)} Monaten.",
                detail="Weiter so! Die aktuellen Massnahmen zeigen Wirkung.",
            ),
        ))

    def evaluate(
        self,
        entity: ExtractedEntity,
        context_data: Dict[str, Any],
    ) -> List[ProactiveInsight]:
        """Evaluiert alle Regeln fuer eine Entity."""
        insights = []

        for rule in self._rules:
            if entity.entity_type in rule.entity_types:
                try:
                    if rule.condition(context_data):
                        insight = rule.generate(context_data)
                        insight.related_entities.append(entity)
                        insights.append(insight)
                except Exception as e:
                    logger.warning(
                        "rule_evaluation_failed",
                        rule_id=rule.rule_id,
                        error=str(e),
                    )

        return insights


# =============================================================================
# Proactive Insights Service
# =============================================================================

class ProactiveInsightsService:
    """
    Service fuer proaktive, kontextsensitive Insights.

    Analysiert User-Interaktionen und Chat-Nachrichten, extrahiert
    relevante Entities und generiert automatisch hilfreiche Insights.

    Singleton-Pattern fuer globalen Zugriff.
    """

    _instance: Optional["ProactiveInsightsService"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "ProactiveInsightsService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._rule_engine = InsightRuleEngine()
        self._entity_patterns = EntityPatterns()
        self._user_contexts: Dict[UUID, UserContext] = {}
        self._insight_cache: Dict[str, List[ProactiveInsight]] = {}
        self._cache_lock = asyncio.Lock()
        self._initialized = True

        logger.info("proactive_insights_service_initialized")

    async def enrich_chat_response(
        self,
        user_id: UUID,
        user_question: str,
        base_answer: str,
        space_id: Optional[UUID] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> EnrichedResponse:
        """
        Reichert eine Chat-Antwort mit proaktiven Insights an.

        Args:
            user_id: ID des Users
            user_question: Die Frage des Users
            base_answer: Die Basis-Antwort (ohne Insights)
            space_id: Optional Space-ID
            additional_context: Zusaetzlicher Kontext (z.B. aktuelle KPIs)

        Returns:
            EnrichedResponse mit Insights und Follow-up-Vorschlaegen
        """
        logger.info(
            "enriching_chat_response",
            user_id=str(user_id),
            question_length=len(user_question),
        )

        # Entities aus Frage extrahieren
        entities = await self._extract_entities(user_question)

        # Kontext aktualisieren
        context = self._get_or_create_context(user_id, space_id)
        context.recent_queries.append(user_question)
        context.recent_entities.extend(entities)

        # Insights generieren
        insights = await self._generate_insights(
            entities=entities,
            user_context=context,
            additional_data=additional_context or {},
        )

        # Follow-up Vorschlaege generieren
        follow_ups = self._generate_follow_up_suggestions(
            user_question,
            entities,
            insights,
        )

        logger.info(
            "chat_response_enriched",
            insight_count=len(insights),
            follow_up_count=len(follow_ups),
        )

        return EnrichedResponse(
            original_response=base_answer,
            insights=insights,
            follow_up_suggestions=follow_ups,
        )

    async def get_contextual_insights(
        self,
        user_id: UUID,
        context_source: ContextSource,
        context_data: Dict[str, Any],
        space_id: Optional[UUID] = None,
    ) -> List[ProactiveInsight]:
        """
        Generiert kontextuelle Insights basierend auf User-Aktionen.

        Args:
            user_id: ID des Users
            context_source: Quelle des Kontexts (Page View, Search, etc.)
            context_data: Kontext-Daten (z.B. aktuelle Seite, Entity-ID)
            space_id: Optional Space-ID

        Returns:
            Liste von relevanten Insights
        """
        logger.info(
            "generating_contextual_insights",
            user_id=str(user_id),
            context_source=context_source.value,
        )

        # Entity aus Kontext extrahieren
        entities = []
        if "entity_type" in context_data and "entity_id" in context_data:
            entities.append(ExtractedEntity(
                entity_type=EntityType(context_data["entity_type"]),
                entity_id=UUID(context_data["entity_id"]) if context_data.get("entity_id") else None,
                entity_name=context_data.get("entity_name", ""),
                confidence=1.0,  # Explizit angegeben
            ))

        # Zusaetzliche Entities aus Text extrahieren
        if "search_query" in context_data:
            text_entities = await self._extract_entities(context_data["search_query"])
            entities.extend(text_entities)

        # User-Kontext
        context = self._get_or_create_context(user_id, space_id)

        # Insights generieren
        insights = await self._generate_insights(
            entities=entities,
            user_context=context,
            additional_data=context_data,
        )

        # Context Source setzen
        for insight in insights:
            insight.context_source = context_source

        return insights

    async def get_dashboard_insights(
        self,
        user_id: UUID,
        current_kpis: Dict[str, float],
        space_id: Optional[UUID] = None,
        max_insights: int = 5,
    ) -> List[ProactiveInsight]:
        """
        Generiert Insights fuer das Dashboard.

        Analysiert aktuelle KPIs und generiert die wichtigsten Insights
        fuer die Dashboard-Anzeige.

        Args:
            user_id: ID des Users
            current_kpis: Aktuelle KPI-Werte
            space_id: Optional Space-ID
            max_insights: Maximale Anzahl Insights

        Returns:
            Priorisierte Liste von Insights
        """
        logger.info(
            "generating_dashboard_insights",
            user_id=str(user_id),
            kpi_count=len(current_kpis),
        )

        insights = []

        # KPI-Entity erstellen
        kpi_entity = ExtractedEntity(
            entity_type=EntityType.KPI,
            entity_name="Financial KPIs",
            confidence=1.0,
        )

        # Regel-Engine mit KPI-Daten fuettern
        kpi_insights = self._rule_engine.evaluate(kpi_entity, current_kpis)
        insights.extend(kpi_insights)

        # Nach Prioritaet sortieren
        priority_order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3,
        }
        insights.sort(key=lambda i: priority_order.get(i.priority, 4))

        return insights[:max_insights]

    async def learn_from_feedback(
        self,
        insight_id: UUID,
        was_helpful: bool,
        user_id: UUID,
    ) -> None:
        """
        Lernt aus User-Feedback zu Insights.

        Speichert ob ein Insight hilfreich war und passt zukuenftige
        Generierung entsprechend an.
        """
        logger.info(
            "insight_feedback_received",
            insight_id=str(insight_id),
            was_helpful=was_helpful,
            user_id=str(user_id),
        )

        # TODO: Implement feedback learning
        # - Speichere Feedback in DB
        # - Passe Regel-Gewichte an
        # - Personalisiere fuer User
        pass

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _extract_entities(self, text: str) -> List[ExtractedEntity]:
        """Extrahiert Entities aus Text."""
        entities = []
        text_lower = text.lower()

        for entity_type, patterns in EntityPatterns.PATTERNS.items():
            for pattern in patterns:
                try:
                    matches = re.findall(pattern, text_lower)
                    for match in matches:
                        entity_name = match if isinstance(match, str) else match[0] if match else ""
                        if entity_name and len(entity_name) > 2:
                            entities.append(ExtractedEntity(
                                entity_type=entity_type,
                                entity_name=entity_name.strip(),
                                confidence=0.7,  # Pattern-basiert
                                source_text=text,
                            ))
                except re.error:
                    continue

        # Deduplizieren
        seen = set()
        unique_entities = []
        for entity in entities:
            key = (entity.entity_type, entity.entity_name)
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)

        return unique_entities

    async def _generate_insights(
        self,
        entities: List[ExtractedEntity],
        user_context: UserContext,
        additional_data: Dict[str, Any],
    ) -> List[ProactiveInsight]:
        """Generiert Insights basierend auf Entities und Kontext."""
        insights = []

        for entity in entities:
            # Kontext-Daten fuer diese Entity zusammenstellen
            context_data = additional_data.copy()
            context_data["entity_name"] = entity.entity_name
            context_data["entity_id"] = str(entity.entity_id) if entity.entity_id else None

            # Mock-Daten fuer Demo (in Produktion: aus DB laden)
            context_data = self._enrich_with_mock_data(entity, context_data)

            # Regeln evaluieren
            entity_insights = self._rule_engine.evaluate(entity, context_data)
            insights.extend(entity_insights)

        # Deduplizieren und priorisieren
        return self._deduplicate_and_prioritize(insights)

    def _enrich_with_mock_data(
        self,
        entity: ExtractedEntity,
        context_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Reichert Kontext mit simulierten Daten an (fuer Demo)."""
        # In Produktion wuerden diese Daten aus der DB kommen

        if entity.entity_type == EntityType.SUPPLIER:
            context_data.setdefault("price_vs_average", 15)  # 15% teurer
            context_data.setdefault("potential_savings", 500)
            context_data.setdefault("supplier_name", entity.entity_name.title())

        elif entity.entity_type == EntityType.PROPERTY:
            context_data.setdefault("rent_vs_market", -12)  # 12% unter Markt
            context_data.setdefault("potential_rent_increase", 150)
            context_data.setdefault("property_id", str(entity.entity_id or uuid4()))

        elif entity.entity_type == EntityType.INSURANCE:
            # Zufaellig Insights generieren fuer Demo
            import random
            if random.random() > 0.5:
                context_data.setdefault("has_coverage_gap", True)
                context_data.setdefault("missing_coverage", "Elementarschadenversicherung")
                context_data.setdefault("asset_type", "Immobilie")
            if random.random() > 0.7:
                context_data.setdefault("overlapping_policies", ["Policy A", "Policy B"])
                context_data.setdefault("potential_premium_savings", 200)

        elif entity.entity_type == EntityType.LOAN:
            context_data.setdefault("interest_vs_market", 1.1)  # 1.1% hoeher
            context_data.setdefault("potential_savings_annual", 1300)
            context_data.setdefault("potential_savings_total", 15600)
            context_data.setdefault("loan_id", str(entity.entity_id or uuid4()))

        return context_data

    def _deduplicate_and_prioritize(
        self,
        insights: List[ProactiveInsight],
    ) -> List[ProactiveInsight]:
        """Dedupliziert und priorisiert Insights."""
        # Nach Titel deduplizieren
        seen_titles: Set[str] = set()
        unique = []
        for insight in insights:
            if insight.title not in seen_titles:
                seen_titles.add(insight.title)
                unique.append(insight)

        # Nach Prioritaet sortieren
        priority_order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3,
        }
        unique.sort(key=lambda i: priority_order.get(i.priority, 4))

        return unique

    def _generate_follow_up_suggestions(
        self,
        user_question: str,
        entities: List[ExtractedEntity],
        insights: List[ProactiveInsight],
    ) -> List[str]:
        """Generiert Follow-up-Vorschlaege basierend auf Kontext."""
        suggestions = []

        # Basierend auf Entity-Typen
        entity_types = {e.entity_type for e in entities}

        if EntityType.SUPPLIER in entity_types:
            suggestions.append("Moechtest du alternative Lieferanten vergleichen?")

        if EntityType.PROPERTY in entity_types:
            suggestions.append("Soll ich eine Mietpreis-Analyse erstellen?")

        if EntityType.INSURANCE in entity_types:
            suggestions.append("Moechtest du deine Versicherungen auf Luecken pruefen?")

        if EntityType.LOAN in entity_types:
            suggestions.append("Soll ich eine Refinanzierung simulieren?")

        if EntityType.KPI in entity_types:
            suggestions.append("Was-Wenn-Simulation fuer deine Finanzen?")

        # Basierend auf Insights
        if any(i.insight_type == InsightType.WARNING for i in insights):
            suggestions.append("Soll ich Handlungsempfehlungen geben?")

        if any(i.insight_type == InsightType.OPPORTUNITY for i in insights):
            suggestions.append("Moechtest du die Optimierungspotenziale im Detail sehen?")

        return suggestions[:3]  # Max 3 Vorschlaege

    def _get_or_create_context(
        self,
        user_id: UUID,
        space_id: Optional[UUID] = None,
    ) -> UserContext:
        """Holt oder erstellt User-Kontext."""
        if user_id not in self._user_contexts:
            self._user_contexts[user_id] = UserContext(
                user_id=user_id,
                space_id=space_id,
            )
        return self._user_contexts[user_id]


# =============================================================================
# Singleton Accessor
# =============================================================================

_insights_instance: Optional[ProactiveInsightsService] = None
_insights_lock = threading.Lock()


def get_proactive_insights_service() -> ProactiveInsightsService:
    """Gibt die Singleton-Instanz des Proactive Insights Service zurueck."""
    global _insights_instance
    with _insights_lock:
        if _insights_instance is None:
            _insights_instance = ProactiveInsightsService()
        return _insights_instance
