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
    source_rule: Optional[str] = None                # Regel die diesen Insight generiert hat
    confidence: float = 1.0                          # Konfidenz (angepasst durch Feedback)

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
            "source_rule": self.source_rule,
            "confidence": self.confidence,
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
class RuleFeedbackStats:
    """Statistiken zu User-Feedback fuer eine Regel."""
    rule_id: str
    helpful_count: int = 0
    unhelpful_count: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_feedback(self) -> int:
        """Gesamtanzahl Feedback."""
        return self.helpful_count + self.unhelpful_count

    @property
    def weight(self) -> float:
        """
        Berechnet Gewichtung basierend auf Feedback.

        Formel: Nutzt Wilson Score Interval Lower Bound fuer faire Gewichtung.
        - 0.3 bei vielen negativen Feedbacks (Regel wird gefiltert)
        - 1.0 bei neutralem/keinem Feedback (Standard)
        - 1.5 bei vielen positiven Feedbacks (Regel wird bevorzugt)
        """
        if self.total_feedback == 0:
            return 1.0

        # Positiver Anteil
        positive_ratio = self.helpful_count / self.total_feedback

        # Wilson Score Lower Bound fuer statistische Signifikanz
        import math
        z = 1.96  # 95% Konfidenz
        n = self.total_feedback
        p = positive_ratio

        # Wilson Score
        denominator = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denominator
        spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator

        lower_bound = centre - spread

        # Mapping: [0, 1] -> [0.3, 1.5]
        # 0.5 = neutral -> 1.0
        # 0.0 = sehr negativ -> 0.3
        # 1.0 = sehr positiv -> 1.5
        weight = 0.3 + (lower_bound * 1.2)

        # Clamp to [0.3, 1.5]
        return max(0.3, min(1.5, weight))


@dataclass
class UserContext:
    """Aktueller Kontext des Users."""
    user_id: UUID
    space_id: Optional[UUID] = None
    current_page: Optional[str] = None
    recent_queries: List[str] = field(default_factory=list)
    recent_entities: List[ExtractedEntity] = field(default_factory=list)
    session_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Memory Management: Max items pro Liste
    MAX_RECENT_QUERIES: int = field(default=50, repr=False)
    MAX_RECENT_ENTITIES: int = field(default=100, repr=False)

    def add_query(self, query: str) -> None:
        """Fuegt Query hinzu mit automatischem Pruning."""
        self.recent_queries.append(query)
        if len(self.recent_queries) > self.MAX_RECENT_QUERIES:
            self.recent_queries = self.recent_queries[-self.MAX_RECENT_QUERIES:]
        self.last_activity = datetime.now(timezone.utc)

    def add_entities(self, entities: List[ExtractedEntity]) -> None:
        """Fuegt Entities hinzu mit automatischem Pruning."""
        self.recent_entities.extend(entities)
        if len(self.recent_entities) > self.MAX_RECENT_ENTITIES:
            self.recent_entities = self.recent_entities[-self.MAX_RECENT_ENTITIES:]
        self.last_activity = datetime.now(timezone.utc)


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
        user_rule_weights: Optional[Dict[str, float]] = None,
    ) -> List[ProactiveInsight]:
        """Evaluiert alle Regeln fuer eine Entity.

        Args:
            entity: Die zu evaluierende Entity.
            context_data: Kontext-Daten fuer die Regelauswertung.
            user_rule_weights: Optional User-spezifische Regel-Gewichte (0-2).
                               1.0 = Standard, <1 = weniger oft zeigen, >1 = bevorzugen.

        Returns:
            Liste von generierten ProactiveInsights.
        """
        insights = []
        user_rule_weights = user_rule_weights or {}

        for rule in self._rules:
            if entity.entity_type in rule.entity_types:
                try:
                    if rule.condition(context_data):
                        insight = rule.generate(context_data)
                        insight.related_entities.append(entity)
                        insight.source_rule = rule.rule_id

                        # User-spezifische Gewichtung anwenden
                        weight = user_rule_weights.get(rule.rule_id, 1.0)
                        insight.confidence = insight.confidence * weight

                        # Insights mit zu niedriger Konfidenz filtern
                        if insight.confidence >= 0.3:
                            insights.append(insight)
                        else:
                            logger.debug(
                                "insight_filtered_low_confidence",
                                rule_id=rule.rule_id,
                                confidence=insight.confidence,
                            )
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

        # Memory Management Limits
        self._max_user_contexts = 1000  # Max concurrent user contexts
        self._context_ttl = timedelta(hours=24)  # Context expiry
        self._max_cache_entries = 500  # Max cache entries
        self._cache_ttl = timedelta(hours=1)  # Cache expiry
        self._cache_timestamps: Dict[str, datetime] = {}  # Track cache entry ages

        # Feedback Learning Storage
        # Structure: {user_id: {rule_id: RuleFeedbackStats}}
        self._user_feedback: Dict[UUID, Dict[str, "RuleFeedbackStats"]] = {}
        self._feedback_lock = asyncio.Lock()
        self._max_feedback_users = 5000  # Max users with feedback
        self._feedback_ttl = timedelta(days=90)  # Feedback expiry
        self._feedback_timestamps: Dict[UUID, datetime] = {}  # Track last update

        # Insight cache fuer Feedback-Lookup
        # Structure: {insight_id_str: (insight, user_id, created_at)}
        self._generated_insights: Dict[str, Tuple[ProactiveInsight, UUID, datetime]] = {}
        self._max_generated_insights = 10000  # Max insights to track
        self._insight_retention = timedelta(hours=48)  # Keep insights for feedback

        self._initialized = True

        logger.info("proactive_insights_service_initialized")

    async def cleanup_stale_contexts(self) -> int:
        """
        Entfernt abgelaufene User-Kontexte und Cache-Eintraege.

        Returns:
            Anzahl entfernter Eintraege.
        """
        async with self._cache_lock:
            now = datetime.now(timezone.utc)
            removed = 0

            # Cleanup stale user contexts
            cutoff = now - self._context_ttl
            stale_users = [
                uid for uid, ctx in self._user_contexts.items()
                if ctx.last_activity < cutoff
            ]
            for uid in stale_users:
                del self._user_contexts[uid]
                removed += 1

            # Enforce max contexts (LRU-style)
            if len(self._user_contexts) > self._max_user_contexts:
                sorted_contexts = sorted(
                    self._user_contexts.items(),
                    key=lambda x: x[1].last_activity
                )
                excess = len(self._user_contexts) - self._max_user_contexts
                for uid, _ in sorted_contexts[:excess]:
                    del self._user_contexts[uid]
                    removed += 1

            # Cleanup stale cache entries
            cache_cutoff = now - self._cache_ttl
            stale_cache_keys = [
                key for key, ts in self._cache_timestamps.items()
                if ts < cache_cutoff
            ]
            for key in stale_cache_keys:
                if key in self._insight_cache:
                    del self._insight_cache[key]
                del self._cache_timestamps[key]
                removed += 1

            # Enforce max cache entries (LRU-style)
            if len(self._insight_cache) > self._max_cache_entries:
                sorted_cache = sorted(
                    self._cache_timestamps.items(),
                    key=lambda x: x[1]
                )
                excess = len(self._insight_cache) - self._max_cache_entries
                for key, _ in sorted_cache[:excess]:
                    if key in self._insight_cache:
                        del self._insight_cache[key]
                    del self._cache_timestamps[key]
                    removed += 1

            if removed > 0:
                logger.info("proactive_insights_cleanup", removed=removed)

            return removed

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

        # Kontext aktualisieren (mit automatischem Pruning)
        context = self._get_or_create_context(user_id, space_id)
        context.add_query(user_question)
        context.add_entities(entities)

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

        Args:
            insight_id: ID des bewerteten Insights.
            was_helpful: True wenn Insight hilfreich war.
            user_id: ID des Users der Feedback gibt.
        """
        insight_id_str = str(insight_id)

        # Insight aus Cache laden
        insight_data = self._generated_insights.get(insight_id_str)
        if not insight_data:
            logger.warning(
                "insight_feedback_insight_not_found",
                insight_id=insight_id_str,
                user_id=str(user_id),
            )
            return

        insight, original_user_id, created_at = insight_data

        # Sicherheitscheck: Feedback nur vom gleichen User
        if original_user_id != user_id:
            logger.warning(
                "insight_feedback_user_mismatch",
                insight_id=insight_id_str,
                expected_user=str(original_user_id),
                actual_user=str(user_id),
            )
            return

        source_rule = insight.source_rule
        if not source_rule:
            logger.warning(
                "insight_feedback_no_source_rule",
                insight_id=insight_id_str,
            )
            return

        # Feedback speichern
        async with self._feedback_lock:
            now = datetime.now(timezone.utc)

            # User-Feedback-Dict initialisieren
            if user_id not in self._user_feedback:
                self._user_feedback[user_id] = {}

            # Regel-Stats initialisieren
            if source_rule not in self._user_feedback[user_id]:
                self._user_feedback[user_id][source_rule] = RuleFeedbackStats(
                    rule_id=source_rule
                )

            # Feedback zaehlen
            stats = self._user_feedback[user_id][source_rule]
            if was_helpful:
                stats.helpful_count += 1
            else:
                stats.unhelpful_count += 1
            stats.last_updated = now

            # User-Timestamp aktualisieren
            self._feedback_timestamps[user_id] = now

            # Memory Management: Alte Feedbacks entfernen
            await self._cleanup_stale_feedback()

        logger.info(
            "insight_feedback_recorded",
            insight_id=insight_id_str,
            was_helpful=was_helpful,
            user_id=str(user_id),
            source_rule=source_rule,
            new_weight=self._user_feedback[user_id][source_rule].weight,
            total_feedback=self._user_feedback[user_id][source_rule].total_feedback,
        )

    async def _cleanup_stale_feedback(self) -> int:
        """
        Entfernt veraltete Feedback-Daten.

        Returns:
            Anzahl entfernter User-Feedback-Eintraege.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - self._feedback_ttl
        removed = 0

        # Veraltete Users entfernen
        stale_users = [
            uid for uid, ts in self._feedback_timestamps.items()
            if ts < cutoff
        ]
        for uid in stale_users:
            del self._user_feedback[uid]
            del self._feedback_timestamps[uid]
            removed += 1

        # Max Users enforcem (LRU-style)
        if len(self._user_feedback) > self._max_feedback_users:
            sorted_users = sorted(
                self._feedback_timestamps.items(),
                key=lambda x: x[1]
            )
            excess = len(self._user_feedback) - self._max_feedback_users
            for uid, _ in sorted_users[:excess]:
                del self._user_feedback[uid]
                del self._feedback_timestamps[uid]
                removed += 1

        # Veraltete generated insights entfernen
        insight_cutoff = now - self._insight_retention
        stale_insights = [
            iid for iid, (_, _, ts) in self._generated_insights.items()
            if ts < insight_cutoff
        ]
        for iid in stale_insights:
            del self._generated_insights[iid]

        if removed > 0 or stale_insights:
            logger.debug(
                "feedback_cleanup_completed",
                removed_users=removed,
                removed_insights=len(stale_insights),
            )

        return removed

    def get_user_rule_weights(self, user_id: UUID) -> Dict[str, float]:
        """
        Gibt die personalisierten Regel-Gewichte fuer einen User zurueck.

        Args:
            user_id: User-ID.

        Returns:
            Dict von rule_id -> weight (0.3-1.5).
        """
        if user_id not in self._user_feedback:
            return {}

        return {
            rule_id: stats.weight
            for rule_id, stats in self._user_feedback[user_id].items()
        }

    async def get_feedback_summary(self, user_id: UUID) -> Dict[str, Any]:
        """
        Gibt eine Zusammenfassung des User-Feedbacks zurueck.

        Args:
            user_id: User-ID.

        Returns:
            Zusammenfassung mit Gewichten und Statistiken.
        """
        if user_id not in self._user_feedback:
            return {
                "user_id": str(user_id),
                "has_feedback": False,
                "rules": [],
            }

        rules = []
        for rule_id, stats in self._user_feedback[user_id].items():
            rules.append({
                "rule_id": rule_id,
                "helpful_count": stats.helpful_count,
                "unhelpful_count": stats.unhelpful_count,
                "total_feedback": stats.total_feedback,
                "weight": stats.weight,
                "last_updated": stats.last_updated.isoformat(),
            })

        # Nach Anzahl Feedback sortieren
        rules.sort(key=lambda x: x["total_feedback"], reverse=True)

        return {
            "user_id": str(user_id),
            "has_feedback": True,
            "total_rules": len(rules),
            "rules": rules,
        }

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

        # User-spezifische Regel-Gewichte laden
        user_rule_weights = self.get_user_rule_weights(user_context.user_id)

        for entity in entities:
            # Kontext-Daten fuer diese Entity zusammenstellen
            context_data = additional_data.copy()
            context_data["entity_name"] = entity.entity_name
            context_data["entity_id"] = str(entity.entity_id) if entity.entity_id else None

            # Mock-Daten fuer Demo (in Produktion: aus DB laden)
            context_data = self._enrich_with_mock_data(entity, context_data)

            # Regeln evaluieren mit User-Gewichten
            entity_insights = self._rule_engine.evaluate(
                entity,
                context_data,
                user_rule_weights=user_rule_weights,
            )
            insights.extend(entity_insights)

        # Deduplizieren und priorisieren
        final_insights = self._deduplicate_and_prioritize(insights)

        # Insights fuer Feedback-Tracking registrieren
        now = datetime.now(timezone.utc)
        for insight in final_insights:
            self._generated_insights[str(insight.id)] = (
                insight,
                user_context.user_id,
                now,
            )

        # Max Insights im Cache enforcem
        if len(self._generated_insights) > self._max_generated_insights:
            # Aelteste entfernen (FIFO)
            sorted_insights = sorted(
                self._generated_insights.items(),
                key=lambda x: x[1][2]  # Sort by created_at
            )
            excess = len(self._generated_insights) - self._max_generated_insights
            for iid, _ in sorted_insights[:excess]:
                del self._generated_insights[iid]

        return final_insights

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
# Extended Insight Rules (Phase 6)
# =============================================================================

class ExtendedInsightRuleEngine(InsightRuleEngine):
    """
    Erweiterte Rule Engine mit Phase 6 Insights.

    Neue Regeln fuer:
    - Skonto-Deadlines
    - Vertrags-Kuendigungsfristen
    - Zahlungsfristen
    - Preisanomalien
    - Batch-Genehmigungsvorschlaege
    - Fehlende Stammdaten
    """

    def __init__(self) -> None:
        super().__init__()
        self._register_extended_rules()

    def _register_extended_rules(self) -> None:
        """Registriert die erweiterten Regeln aus Phase 6."""

        # Regel: Skonto laeuft ab
        self._rules.append(InsightRule(
            rule_id="skonto_expiring",
            entity_types=[EntityType.DOCUMENT],
            condition=lambda ctx: ctx.get("skonto_days_remaining", 99) <= 3 and ctx.get("skonto_days_remaining", 0) >= 0,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.REMINDER,
                priority=InsightPriority.CRITICAL if ctx.get("skonto_days_remaining", 99) <= 1 else InsightPriority.HIGH,
                title=f"Skonto-Frist in {ctx.get('skonto_days_remaining', 0)} Tag(en)",
                message=f"Bei Zahlung bis {ctx.get('skonto_deadline', 'morgen')} sparen Sie {ctx.get('skonto_percentage', 2):.1f}% ({ctx.get('skonto_amount', 0):,.2f} EUR).",
                detail=f"Rechnung: {ctx.get('invoice_number', 'Unbekannt')}, Lieferant: {ctx.get('supplier_name', 'Unbekannt')}",
                potential_value=Decimal(str(ctx.get("skonto_amount", 0))),
                action_url=f"/invoices/{ctx.get('invoice_id')}",
                action_label="Jetzt bezahlen",
                expires_at=ctx.get("skonto_deadline_datetime"),
            ),
        ))

        # Regel: Vertragskuendigung naht
        self._rules.append(InsightRule(
            rule_id="contract_cancellation",
            entity_types=[EntityType.DOCUMENT],
            condition=lambda ctx: ctx.get("cancellation_days_remaining", 99) <= 30 and ctx.get("cancellation_days_remaining", 0) >= 0,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.WARNING,
                priority=InsightPriority.HIGH if ctx.get("cancellation_days_remaining", 99) <= 7 else InsightPriority.MEDIUM,
                title=f"Kuendigungsfrist in {ctx.get('cancellation_days_remaining', 0)} Tagen",
                message=f"Vertrag '{ctx.get('contract_name', 'Unbekannt')}' verlaengert sich automatisch wenn nicht gekuendigt.",
                detail=f"Monatliche Kosten: {ctx.get('monthly_cost', 0):,.2f} EUR, Verlaengerung: {ctx.get('auto_extend_months', 12)} Monate",
                potential_value=Decimal(str(ctx.get("annual_cost", 0))),
                action_url=f"/contracts/{ctx.get('contract_id')}",
                action_label="Vertrag pruefen",
            ),
        ))

        # Regel: Zahlung ueberfaellig
        self._rules.append(InsightRule(
            rule_id="payment_overdue",
            entity_types=[EntityType.DOCUMENT],
            condition=lambda ctx: ctx.get("days_overdue", 0) > 0,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.WARNING,
                priority=InsightPriority.CRITICAL if ctx.get("days_overdue", 0) > 14 else InsightPriority.HIGH,
                title=f"Zahlung {ctx.get('days_overdue', 0)} Tage ueberfaellig",
                message=f"Rechnung '{ctx.get('invoice_number', 'Unbekannt')}' ist seit {ctx.get('days_overdue', 0)} Tagen ueberfaellig.",
                detail=f"Ausstehender Betrag: {ctx.get('outstanding_amount', 0):,.2f} EUR, Mahnstufe: {ctx.get('dunning_level', 0)}",
                potential_value=Decimal(str(ctx.get("outstanding_amount", 0))),
                action_url=f"/invoices/{ctx.get('invoice_id')}",
                action_label="Rechnung oeffnen",
            ),
        ))

        # Regel: Preisanomalie erkannt
        self._rules.append(InsightRule(
            rule_id="price_anomaly",
            entity_types=[EntityType.SUPPLIER],
            condition=lambda ctx: abs(ctx.get("price_deviation_percent", 0)) > 20,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.ANOMALY,
                priority=InsightPriority.HIGH if abs(ctx.get("price_deviation_percent", 0)) > 50 else InsightPriority.MEDIUM,
                title=f"Preisabweichung bei {ctx.get('supplier_name', 'Lieferant')}",
                message=f"Aktueller Preis liegt {ctx.get('price_deviation_percent', 0):+.1f}% {'ueber' if ctx.get('price_deviation_percent', 0) > 0 else 'unter'} dem Durchschnitt.",
                detail=f"Historischer Durchschnitt: {ctx.get('historical_avg', 0):,.2f} EUR, Aktuell: {ctx.get('current_price', 0):,.2f} EUR",
                action_url=f"/entities/{ctx.get('supplier_id')}/price-analysis",
                action_label="Preisanalyse",
            ),
        ))

        # Regel: Batch-Genehmigung moeglich
        self._rules.append(InsightRule(
            rule_id="batch_approval_suggestion",
            entity_types=[EntityType.SUPPLIER, EntityType.GENERAL],
            condition=lambda ctx: ctx.get("pending_approval_count", 0) >= 3 and ctx.get("same_supplier", False),
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.OPTIMIZATION,
                priority=InsightPriority.MEDIUM,
                title=f"Batch-Genehmigung: {ctx.get('pending_approval_count', 0)} Dokumente",
                message=f"{ctx.get('pending_approval_count', 0)} Dokumente von {ctx.get('supplier_name', 'einem Lieferanten')} warten auf Genehmigung.",
                detail=f"Gesamtwert: {ctx.get('total_amount', 0):,.2f} EUR. Batch-Verarbeitung spart Zeit.",
                action_url="/approvals?batch=true",
                action_label="Batch genehmigen",
            ),
        ))

        # Regel: Fehlende Stammdaten
        self._rules.append(InsightRule(
            rule_id="missing_data_hint",
            entity_types=[EntityType.SUPPLIER],
            condition=lambda ctx: len(ctx.get("missing_fields", [])) > 0,
            generate=lambda ctx: ProactiveInsight(
                insight_type=InsightType.WARNING,
                priority=InsightPriority.MEDIUM if "iban" in ctx.get("missing_fields", []) else InsightPriority.LOW,
                title=f"Unvollstaendige Stammdaten: {ctx.get('entity_name', 'Entitaet')}",
                message=f"Fehlende Felder: {', '.join(ctx.get('missing_fields', []))}",
                detail="Vollstaendige Stammdaten ermoeglichen automatische Verarbeitung.",
                action_url=f"/entities/{ctx.get('entity_id')}/edit",
                action_label="Daten ergaenzen",
            ),
        ))


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


def get_extended_rule_engine() -> ExtendedInsightRuleEngine:
    """Gibt eine ExtendedInsightRuleEngine Instanz zurueck."""
    return ExtendedInsightRuleEngine()
