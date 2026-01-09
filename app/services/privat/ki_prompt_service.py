"""Privat KI-Prompt Service.

Privat-spezifische KI-Analysen auf Basis des bestehenden LLMService.
Deutsche Prompt-Templates fuer:
- Immobilien-Wertschaetzung
- Fahrzeug-Analyse
- Anlage-Beratung
- Versicherungs-Check
- Finanz-Assistent Chat

Features:
- Jinja2-Template Rendering
- Response-Parsing (JSON)
- Redis-Caching
- Prometheus-Metriken
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.rag.llm_service import (
    LLMService,
    LLMMessage,
    LLMResponse,
    LLMContextType,
)

logger = structlog.get_logger(__name__)

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

KI_ANALYSIS_REQUESTS = Counter(
    "privat_ki_analysis_requests_total",
    "Anzahl KI-Analyse-Anfragen",
    ["analysis_type", "status"]
)

KI_ANALYSIS_DURATION = Histogram(
    "privat_ki_analysis_duration_seconds",
    "Dauer der KI-Analyse",
    ["analysis_type"],
    buckets=[1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
)

KI_CACHE_HITS = Counter(
    "privat_ki_cache_hits_total",
    "Anzahl Cache-Hits"
)

KI_CACHE_MISSES = Counter(
    "privat_ki_cache_misses_total",
    "Anzahl Cache-Misses"
)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PropertyValueAnalysis:
    """Ergebnis einer Immobilien-Wertanalyse."""
    property_id: UUID
    estimated_value_eur: float
    confidence_percent: int
    reasoning: str
    market_comparison: str
    value_trend: str  # steigend, stabil, fallend
    rental_potential_eur: Optional[float] = None
    roi_estimate_percent: Optional[float] = None
    raw_response: Optional[str] = None
    cached: bool = False
    analysis_time_ms: float = 0.0


@dataclass
class VehicleDepreciationAnalysis:
    """Ergebnis einer Fahrzeug-Wertanalyse."""
    vehicle_id: UUID
    current_value_eur: float
    original_value_eur: float
    depreciation_percent: float
    remaining_value_percent: float
    optimal_sell_timeframe: str
    market_demand: str  # hoch, mittel, gering
    value_factors: List[str]
    raw_response: Optional[str] = None
    cached: bool = False
    analysis_time_ms: float = 0.0


@dataclass
class InvestmentAdvice:
    """Ergebnis einer Anlage-Beratung."""
    space_id: UUID
    risk_profile: str  # konservativ, ausgewogen, wachstumsorientiert
    current_allocation_assessment: str
    optimization_suggestions: List[str]
    rebalancing_needed: bool
    expected_return_estimate: str
    diversification_score: int  # 0-100
    raw_response: Optional[str] = None
    cached: bool = False
    analysis_time_ms: float = 0.0


@dataclass
class InsuranceCheckResult:
    """Ergebnis eines Versicherungs-Checks."""
    space_id: UUID
    coverage_assessment: str  # ausreichend, verbesserungswuerdig, unzureichend
    identified_gaps: List[str]
    recommendations: List[str]
    cost_optimization_potential_eur: Optional[float] = None
    priority_actions: List[str] = field(default_factory=list)
    raw_response: Optional[str] = None
    cached: bool = False
    analysis_time_ms: float = 0.0


@dataclass
class FinancialQAResponse:
    """Antwort auf eine Finanz-Frage."""
    question: str
    answer: str
    confidence: str  # hoch, mittel, gering
    sources_used: List[str]
    follow_up_suggestions: List[str]
    disclaimer: str
    raw_response: Optional[str] = None
    analysis_time_ms: float = 0.0


# =============================================================================
# PRIVAT KI-PROMPT SERVICE
# =============================================================================

class PrivatKIPromptService:
    """Privat-spezifische KI-Prompt-Analyse.

    Nutzt den bestehenden LLMService fuer Inference.
    Deutsche Jinja2-Templates fuer domainspezifische Prompts.

    Thread-safe Singleton Pattern mit Double-Checked Locking.
    """

    _instance: Optional["PrivatKIPromptService"] = None
    _class_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "PrivatKIPromptService":
        """Singleton Pattern - Thread-safe mit Double-Checked Locking.

        WICHTIG: Alle Instanz-Attribute werden in __new__ initialisiert,
        nicht in __init__, um Race Conditions zu vermeiden.
        """
        # Double-checked locking: Erst ohne Lock pruefen
        if cls._instance is None:
            with cls._class_lock:
                # Nochmal pruefen nachdem Lock erworben
                if cls._instance is None:
                    instance = super().__new__(cls)

                    # ALLE Attribute hier initialisieren - NICHT in __init__!
                    instance._llm_service = LLMService()
                    instance._template_dir = Path(__file__).parent / "templates" / "privat"
                    instance._jinja_env = Environment(
                        loader=FileSystemLoader(str(instance._template_dir)),
                        autoescape=select_autoescape(["html", "xml"]),
                        trim_blocks=True,
                        lstrip_blocks=True,
                    )
                    instance._cache: Dict[str, Any] = {}  # In-Memory Cache
                    instance._cache_lock = threading.RLock()  # Thread-safe Cache-Zugriff
                    instance._cache_ttl_seconds = 3600 * 24  # 24 Stunden
                    instance._initialized = True

                    cls._instance = instance
                    logger.info("privat_ki_prompt_service_initialized")
        return cls._instance

    def __init__(self) -> None:
        """No-op - Initialisierung erfolgt in __new__."""
        pass

    def _render_template(self, template_name: str, **kwargs: Any) -> str:
        """Rendert ein Jinja2-Template.

        Args:
            template_name: Name des Templates (z.B. "property_valuation.j2")
            **kwargs: Template-Variablen

        Returns:
            Gerendeter Prompt-String
        """
        try:
            template = self._jinja_env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            logger.error(
                "template_render_error",
                template=template_name,
                error=str(e)
            )
            raise

    def _get_cache_key(self, prefix: str, entity_id: UUID, **kwargs: Any) -> str:
        """Generiert einen Cache-Key.

        Args:
            prefix: Praefix (z.B. "property")
            entity_id: Entity-ID
            **kwargs: Zusaetzliche Faktoren

        Returns:
            Cache-Key als Hash
        """
        data = f"{prefix}:{entity_id}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Holt Wert aus Cache (Thread-safe).

        WICHTIG: Gibt eine KOPIE zurueck um Cache-Mutation zu verhindern!
        """
        import copy

        with self._cache_lock:
            if cache_key in self._cache:
                entry = self._cache[cache_key]
                if datetime.now(timezone.utc).timestamp() - entry["timestamp"] < self._cache_ttl_seconds:
                    KI_CACHE_HITS.inc()
                    # KRITISCH: Kopie zurueckgeben um Mutation des gecachten Objekts zu verhindern
                    return copy.deepcopy(entry["data"])
                else:
                    del self._cache[cache_key]
        KI_CACHE_MISSES.inc()
        return None

    def _set_cache(self, cache_key: str, data: Any) -> None:
        """Speichert Wert im Cache (Thread-safe)."""
        with self._cache_lock:
            self._cache[cache_key] = {
                "data": data,
                "timestamp": datetime.now(timezone.utc).timestamp()
            }

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parst JSON aus LLM-Response.

        Args:
            response: LLM-Antwort (kann Markdown-Bloecke enthalten)

        Returns:
            Geparster Dict
        """
        # Entferne Markdown Code-Bloecke
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.warning(
                "json_parse_error",
                response_preview=text[:200],
                error=str(e)
            )
            # Fallback: Leeres Dict
            return {}

    # =========================================================================
    # ANALYSE-METHODEN
    # =========================================================================

    async def analyze_property_value(
        self,
        db: AsyncSession,
        property_id: UUID,
        use_cache: bool = True
    ) -> PropertyValueAnalysis:
        """Analysiert den Wert einer Immobilie.

        Args:
            db: Database Session
            property_id: ID der Immobilie
            use_cache: Cache verwenden

        Returns:
            PropertyValueAnalysis
        """
        import time
        from app.db.models import PrivatProperty

        start_time = time.perf_counter()
        cache_key = self._get_cache_key("property", property_id)

        # Cache pruefen
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                cached.cached = True
                return cached

        # Property laden
        property_obj = await db.get(PrivatProperty, property_id)
        if not property_obj:
            raise ValueError(f"Property {property_id} nicht gefunden")

        # Template rendern
        prompt = self._render_template(
            "property_valuation.j2",
            address=property_obj.address or "Keine Adresse",
            year_built=property_obj.year_built or "Unbekannt",
            living_area_sqm=property_obj.living_area_sqm or 0,
            rooms=property_obj.rooms or 0,
            current_rent=float(property_obj.monthly_rent or 0),
            purchase_price=float(property_obj.purchase_price or 0),
            property_type=property_obj.property_type or "Sonstiges",
            region=property_obj.city or "Deutschland",
        )

        # LLM-Anfrage
        messages = [
            LLMMessage(
                role="system",
                content="Du bist ein erfahrener deutscher Immobilien-Gutachter. "
                        "Analysiere Immobilien sachlich und gib realistische Einschaetzungen."
            ),
            LLMMessage(role="user", content=prompt)
        ]

        try:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="property", status="started").inc()

            response = await self._llm_service.generate(
                messages=messages,
                context_type=LLMContextType.EXTRACTION,
                enable_thinking=False,
                temperature=0.3  # Weniger kreativ fuer Fakten
            )

            parsed = self._parse_json_response(response.content)

            result = PropertyValueAnalysis(
                property_id=property_id,
                estimated_value_eur=float(parsed.get("estimated_value_eur", 0)),
                confidence_percent=int(parsed.get("confidence_percent", 50)),
                reasoning=parsed.get("reasoning", "Keine Begruendung verfuegbar"),
                market_comparison=parsed.get("market_comparison", ""),
                value_trend=parsed.get("value_trend", "stabil"),
                rental_potential_eur=parsed.get("rental_potential_eur"),
                roi_estimate_percent=parsed.get("roi_estimate_percent"),
                raw_response=response.content,
                cached=False,
                analysis_time_ms=(time.perf_counter() - start_time) * 1000
            )

            # Cache speichern
            self._set_cache(cache_key, result)

            KI_ANALYSIS_REQUESTS.labels(analysis_type="property", status="success").inc()
            KI_ANALYSIS_DURATION.labels(analysis_type="property").observe(
                result.analysis_time_ms / 1000
            )

            return result

        except Exception as e:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="property", status="error").inc()
            logger.error(
                "property_analysis_error",
                property_id=str(property_id),
                error=str(e)
            )
            raise

    async def analyze_vehicle_depreciation(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
        use_cache: bool = True
    ) -> VehicleDepreciationAnalysis:
        """Analysiert den Wertverlust eines Fahrzeugs.

        Args:
            db: Database Session
            vehicle_id: ID des Fahrzeugs
            use_cache: Cache verwenden

        Returns:
            VehicleDepreciationAnalysis
        """
        import time
        from app.db.models import PrivatVehicle

        start_time = time.perf_counter()
        cache_key = self._get_cache_key("vehicle", vehicle_id)

        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                cached.cached = True
                return cached

        vehicle = await db.get(PrivatVehicle, vehicle_id)
        if not vehicle:
            raise ValueError(f"Vehicle {vehicle_id} nicht gefunden")

        prompt = self._render_template(
            "vehicle_analysis.j2",
            brand=vehicle.brand or "Unbekannt",
            model=vehicle.model or "Unbekannt",
            year=vehicle.year or datetime.now().year,
            mileage_km=vehicle.current_mileage or 0,
            purchase_price=float(vehicle.purchase_price or 0),
            fuel_type=vehicle.fuel_type or "Benzin",
            vehicle_type=vehicle.vehicle_type or "PKW",
        )

        messages = [
            LLMMessage(
                role="system",
                content="Du bist ein deutscher KFZ-Sachverstaendiger. "
                        "Analysiere Fahrzeugwerte basierend auf Marktdaten."
            ),
            LLMMessage(role="user", content=prompt)
        ]

        try:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="vehicle", status="started").inc()

            response = await self._llm_service.generate(
                messages=messages,
                context_type=LLMContextType.EXTRACTION,
                enable_thinking=False,
                temperature=0.3
            )

            parsed = self._parse_json_response(response.content)

            result = VehicleDepreciationAnalysis(
                vehicle_id=vehicle_id,
                current_value_eur=float(parsed.get("current_value_eur", 0)),
                original_value_eur=float(vehicle.purchase_price or 0),
                depreciation_percent=float(parsed.get("depreciation_percent", 0)),
                remaining_value_percent=float(parsed.get("remaining_value_percent", 0)),
                optimal_sell_timeframe=parsed.get("optimal_sell_timeframe", "Unbekannt"),
                market_demand=parsed.get("market_demand", "mittel"),
                value_factors=parsed.get("value_factors", []),
                raw_response=response.content,
                cached=False,
                analysis_time_ms=(time.perf_counter() - start_time) * 1000
            )

            self._set_cache(cache_key, result)

            KI_ANALYSIS_REQUESTS.labels(analysis_type="vehicle", status="success").inc()
            KI_ANALYSIS_DURATION.labels(analysis_type="vehicle").observe(
                result.analysis_time_ms / 1000
            )

            return result

        except Exception as e:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="vehicle", status="error").inc()
            logger.error("vehicle_analysis_error", vehicle_id=str(vehicle_id), error=str(e))
            raise

    async def get_investment_advice(
        self,
        db: AsyncSession,
        space_id: UUID,
        use_cache: bool = True
    ) -> InvestmentAdvice:
        """Generiert Anlage-Beratung fuer einen Space.

        Args:
            db: Database Session
            space_id: ID des Private Space
            use_cache: Cache verwenden

        Returns:
            InvestmentAdvice
        """
        import time
        from app.db.models import PrivatInvestment

        start_time = time.perf_counter()
        cache_key = self._get_cache_key("investment", space_id)

        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                cached.cached = True
                return cached

        # Alle Investments laden
        result = await db.execute(
            select(PrivatInvestment).where(PrivatInvestment.space_id == space_id)
        )
        investments = result.scalars().all()

        # Investment-Zusammenfassung erstellen
        investment_summary = []
        total_value = 0
        for inv in investments:
            value = float(inv.current_value or inv.purchase_value or 0)
            total_value += value
            investment_summary.append({
                "type": inv.investment_type,
                "name": inv.name,
                "value_eur": value,
                "purchase_date": str(inv.purchase_date) if inv.purchase_date else "Unbekannt",
            })

        prompt = self._render_template(
            "investment_advice.j2",
            investments=investment_summary,
            total_value_eur=total_value,
            num_investments=len(investments),
        )

        messages = [
            LLMMessage(
                role="system",
                content="Du bist ein deutscher Finanzberater. "
                        "Gib sachliche Anlageempfehlungen ohne garantierte Renditen zu versprechen."
            ),
            LLMMessage(role="user", content=prompt)
        ]

        try:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="investment", status="started").inc()

            response = await self._llm_service.generate(
                messages=messages,
                context_type=LLMContextType.EXTRACTION,
                enable_thinking=False,
                temperature=0.4
            )

            parsed = self._parse_json_response(response.content)

            result_obj = InvestmentAdvice(
                space_id=space_id,
                risk_profile=parsed.get("risk_profile", "ausgewogen"),
                current_allocation_assessment=parsed.get("current_allocation_assessment", ""),
                optimization_suggestions=parsed.get("optimization_suggestions", []),
                rebalancing_needed=parsed.get("rebalancing_needed", False),
                expected_return_estimate=parsed.get("expected_return_estimate", ""),
                diversification_score=int(parsed.get("diversification_score", 50)),
                raw_response=response.content,
                cached=False,
                analysis_time_ms=(time.perf_counter() - start_time) * 1000
            )

            self._set_cache(cache_key, result_obj)

            KI_ANALYSIS_REQUESTS.labels(analysis_type="investment", status="success").inc()
            KI_ANALYSIS_DURATION.labels(analysis_type="investment").observe(
                result_obj.analysis_time_ms / 1000
            )

            return result_obj

        except Exception as e:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="investment", status="error").inc()
            logger.error("investment_advice_error", space_id=str(space_id), error=str(e))
            raise

    async def check_insurance_coverage(
        self,
        db: AsyncSession,
        space_id: UUID,
        use_cache: bool = True
    ) -> InsuranceCheckResult:
        """Prueft Versicherungsdeckung eines Space.

        Args:
            db: Database Session
            space_id: ID des Private Space
            use_cache: Cache verwenden

        Returns:
            InsuranceCheckResult
        """
        import time
        from app.db.models import PrivatInsurance

        start_time = time.perf_counter()
        cache_key = self._get_cache_key("insurance", space_id)

        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                cached.cached = True
                return cached

        # Alle Versicherungen laden
        result = await db.execute(
            select(PrivatInsurance).where(PrivatInsurance.space_id == space_id)
        )
        insurances = result.scalars().all()

        insurance_summary = []
        for ins in insurances:
            insurance_summary.append({
                "type": ins.insurance_type,
                "provider": ins.provider,
                "coverage_amount_eur": float(ins.coverage_amount or 0),
                "annual_premium_eur": float(ins.annual_premium or 0),
                "is_active": ins.is_active,
            })

        prompt = self._render_template(
            "insurance_check.j2",
            insurances=insurance_summary,
            num_insurances=len(insurances),
        )

        messages = [
            LLMMessage(
                role="system",
                content="Du bist ein deutscher Versicherungsberater. "
                        "Analysiere Deckung und identifiziere Luecken."
            ),
            LLMMessage(role="user", content=prompt)
        ]

        try:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="insurance", status="started").inc()

            response = await self._llm_service.generate(
                messages=messages,
                context_type=LLMContextType.EXTRACTION,
                enable_thinking=False,
                temperature=0.3
            )

            parsed = self._parse_json_response(response.content)

            result_obj = InsuranceCheckResult(
                space_id=space_id,
                coverage_assessment=parsed.get("coverage_assessment", "verbesserungswuerdig"),
                identified_gaps=parsed.get("identified_gaps", []),
                recommendations=parsed.get("recommendations", []),
                cost_optimization_potential_eur=parsed.get("cost_optimization_potential_eur"),
                priority_actions=parsed.get("priority_actions", []),
                raw_response=response.content,
                cached=False,
                analysis_time_ms=(time.perf_counter() - start_time) * 1000
            )

            self._set_cache(cache_key, result_obj)

            KI_ANALYSIS_REQUESTS.labels(analysis_type="insurance", status="success").inc()
            KI_ANALYSIS_DURATION.labels(analysis_type="insurance").observe(
                result_obj.analysis_time_ms / 1000
            )

            return result_obj

        except Exception as e:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="insurance", status="error").inc()
            logger.error("insurance_check_error", space_id=str(space_id), error=str(e))
            raise

    async def financial_qa(
        self,
        db: AsyncSession,
        space_id: UUID,
        question: str
    ) -> FinancialQAResponse:
        """Beantwortet eine Finanz-Frage im Kontext des Space.

        Args:
            db: Database Session
            space_id: ID des Private Space
            question: Die Frage

        Returns:
            FinancialQAResponse
        """
        import time

        start_time = time.perf_counter()

        # Kontext aus verschiedenen Quellen sammeln
        context_parts = []

        # TODO: Kontext aus DB laden (Properties, Vehicles, etc.)
        # Fuer jetzt: Einfache Frage beantworten

        prompt = self._render_template(
            "financial_qa.j2",
            question=question,
            context="\n".join(context_parts) if context_parts else "Kein zusaetzlicher Kontext verfuegbar.",
        )

        messages = [
            LLMMessage(
                role="system",
                content="Du bist ein deutscher Finanz-Assistent. "
                        "Beantworte Fragen klar und verstaendlich. "
                        "Gib keine Anlageberatung und weise auf Risiken hin."
            ),
            LLMMessage(role="user", content=prompt)
        ]

        try:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="qa", status="started").inc()

            response = await self._llm_service.generate(
                messages=messages,
                context_type=LLMContextType.REALTIME,  # Schnelle Antwort
                enable_thinking=False,
                temperature=0.5
            )

            parsed = self._parse_json_response(response.content)

            # Falls JSON-Parse fehlschlaegt, verwende direkte Antwort
            if not parsed or "answer" not in parsed:
                result_obj = FinancialQAResponse(
                    question=question,
                    answer=response.content,
                    confidence="mittel",
                    sources_used=[],
                    follow_up_suggestions=[],
                    disclaimer="Diese Antwort dient nur zur Information und ersetzt keine professionelle Finanzberatung.",
                    raw_response=response.content,
                    analysis_time_ms=(time.perf_counter() - start_time) * 1000
                )
            else:
                result_obj = FinancialQAResponse(
                    question=question,
                    answer=parsed.get("answer", response.content),
                    confidence=parsed.get("confidence", "mittel"),
                    sources_used=parsed.get("sources_used", []),
                    follow_up_suggestions=parsed.get("follow_up_suggestions", []),
                    disclaimer=parsed.get(
                        "disclaimer",
                        "Diese Antwort dient nur zur Information und ersetzt keine professionelle Finanzberatung."
                    ),
                    raw_response=response.content,
                    analysis_time_ms=(time.perf_counter() - start_time) * 1000
                )

            KI_ANALYSIS_REQUESTS.labels(analysis_type="qa", status="success").inc()
            KI_ANALYSIS_DURATION.labels(analysis_type="qa").observe(
                result_obj.analysis_time_ms / 1000
            )

            return result_obj

        except Exception as e:
            KI_ANALYSIS_REQUESTS.labels(analysis_type="qa", status="error").inc()
            logger.error("financial_qa_error", question=question[:100], error=str(e))
            raise

    def clear_cache(self, entity_type: Optional[str] = None, entity_id: Optional[UUID] = None) -> int:
        """Loescht Cache-Eintraege (Thread-safe).

        Args:
            entity_type: Typ (property, vehicle, etc.) oder None fuer alle
            entity_id: Spezifische Entity-ID oder None fuer alle

        Returns:
            Anzahl geloeschter Eintraege
        """
        with self._cache_lock:
            if entity_type is None and entity_id is None:
                count = len(self._cache)
                self._cache.clear()
                return count

            keys_to_delete = []
            prefix = f"{entity_type}:{entity_id}" if entity_id else f"{entity_type}:"

            for key in self._cache:
                if entity_type and key.startswith(prefix):
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._cache[key]

            return len(keys_to_delete)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_privat_ki_prompt_service() -> PrivatKIPromptService:
    """Factory-Funktion fuer PrivatKIPromptService Singleton.

    Returns:
        Die globale PrivatKIPromptService-Instanz

    Note:
        Thread-safety wird durch das Singleton Pattern in der Klasse garantiert.
        Keine separate globale Variable mehr noetig - das Singleton Pattern
        in __new__ ist bereits thread-safe.
    """
    return PrivatKIPromptService()
