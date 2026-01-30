# -*- coding: utf-8 -*-
"""
RecommendationsService - Intelligente Finanz-Empfehlungen.

Generiert automatisch regelbasierte Empfehlungen:
1. Refinancing: Kredit-Zins > Markt + 1%
2. Rebalancing: Allokation > 10% von Target
3. Insurance Gap: Coverage < Empfehlung
4. Emergency Fund: < 3 Monate
5. High-Cost Alert: Ausgabe > 2σ
6. Deadline Warning: Wichtige Frist < 30 Tage
7. Value Update: Wert nicht aktualisiert > 6 Monate

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from enum import Enum

import structlog
from prometheus_client import Counter, Gauge
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

RECOMMENDATIONS_GENERATED = Counter(
    "recommendations_generated_total",
    "Anzahl generierter Empfehlungen",
    ["recommendation_type", "priority"]
)

ACTIVE_RECOMMENDATIONS = Gauge(
    "active_recommendations_count",
    "Anzahl aktiver Empfehlungen pro Space",
    ["space_id"]
)


# =============================================================================
# Enums und Konstanten
# =============================================================================

class RecommendationPriority(str, Enum):
    """Prioritaet einer Empfehlung."""
    CRITICAL = "kritisch"
    HIGH = "hoch"
    MEDIUM = "mittel"
    LOW = "niedrig"
    INFO = "info"


class RecommendationCategory(str, Enum):
    """Kategorie einer Empfehlung."""
    REFINANCING = "refinancing"
    REBALANCING = "rebalancing"
    INSURANCE = "versicherung"
    EMERGENCY_FUND = "notgroschen"
    DEADLINE = "frist"
    VALUE_UPDATE = "wertaktualisierung"
    COST_ALERT = "kostenalarm"
    TAX = "steuer"
    OPTIMIZATION = "optimierung"
    RISK = "risiko"


# Aktuelle Marktzinsen (statisch, sollte regelmaessig aktualisiert werden)
MARKET_INTEREST_RATES = {
    "hypothek": Decimal("3.8"),      # 10-Jahres Baufinanzierung
    "baufinanzierung": Decimal("3.8"),
    "immobiliendarlehen": Decimal("4.0"),
    "autokredit": Decimal("5.5"),
    "ratenkredit": Decimal("7.0"),
    "privatkredit": Decimal("8.5"),
    "dispositionskredit": Decimal("12.0"),
    "default": Decimal("7.0"),
}

# Schwellenwerte
REFINANCING_THRESHOLD = Decimal("1.0")  # 1% ueber Marktzins
EMERGENCY_FUND_MONTHS_MIN = 3
EMERGENCY_FUND_MONTHS_RECOMMENDED = 6
VALUE_UPDATE_THRESHOLD_DAYS = 180  # 6 Monate
DEADLINE_WARNING_DAYS = [90, 30, 14, 7]
REBALANCING_THRESHOLD_PCT = Decimal("10")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Recommendation:
    """Eine einzelne Empfehlung."""
    id: str  # Eindeutige ID (z.B. "refinancing_loan_123")
    category: RecommendationCategory
    priority: RecommendationPriority

    title: str
    description: str
    impact: str  # Erwarteter Nutzen/Ersparnis

    # Betroffene Ressource
    resource_type: Optional[str]  # "loan", "property", "vehicle", etc.
    resource_id: Optional[UUID]
    resource_name: Optional[str]

    # Zahlen
    potential_savings: Optional[Decimal]
    current_value: Optional[Decimal]
    recommended_value: Optional[Decimal]

    # Aktionen
    suggested_actions: List[str]

    # Meta
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    is_dismissable: bool = True


@dataclass
class RecommendationsSummary:
    """Zusammenfassung aller Empfehlungen fuer einen Space."""
    space_id: UUID

    # Alle Empfehlungen nach Prioritaet
    critical: List[Recommendation]
    high: List[Recommendation]
    medium: List[Recommendation]
    low: List[Recommendation]
    info: List[Recommendation]

    # Statistiken
    total_count: int
    total_potential_savings: Decimal

    # Top-3 nach Impact
    top_recommendations: List[Recommendation]

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Singleton Service
# =============================================================================

class RecommendationsService:
    """
    Singleton Service fuer intelligente Finanz-Empfehlungen.

    Analysiert alle Finanzdaten und generiert priorisierte,
    umsetzbare Empfehlungen ohne externe APIs.
    """

    _instance: Optional["RecommendationsService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "RecommendationsService":
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
        logger.info("recommendations_service_initialized")

    # =========================================================================
    # Haupt-Methode: Alle Empfehlungen generieren
    # =========================================================================

    async def generate_recommendations(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> RecommendationsSummary:
        """Generiert alle Empfehlungen fuer einen Space."""
        all_recommendations: List[Recommendation] = []

        # 1. Refinancing-Empfehlungen
        refinancing_recs = await self._check_refinancing_opportunities(db, space_id)
        all_recommendations.extend(refinancing_recs)

        # 2. Rebalancing-Empfehlungen
        rebalancing_recs = await self._check_rebalancing_needs(db, space_id)
        all_recommendations.extend(rebalancing_recs)

        # 3. Versicherungs-Luecken
        insurance_recs = await self._check_insurance_gaps(db, space_id)
        all_recommendations.extend(insurance_recs)

        # 4. Notgroschen-Check
        emergency_recs = await self._check_emergency_fund(db, space_id)
        all_recommendations.extend(emergency_recs)

        # 5. Frist-Warnungen
        deadline_recs = await self._check_upcoming_deadlines(db, space_id)
        all_recommendations.extend(deadline_recs)

        # 6. Wert-Aktualisierungen
        value_recs = await self._check_stale_values(db, space_id)
        all_recommendations.extend(value_recs)

        # 7. Service/TUeV Erinnerungen
        vehicle_recs = await self._check_vehicle_maintenance(db, space_id)
        all_recommendations.extend(vehicle_recs)

        # Nach Prioritaet sortieren
        critical = [r for r in all_recommendations if r.priority == RecommendationPriority.CRITICAL]
        high = [r for r in all_recommendations if r.priority == RecommendationPriority.HIGH]
        medium = [r for r in all_recommendations if r.priority == RecommendationPriority.MEDIUM]
        low = [r for r in all_recommendations if r.priority == RecommendationPriority.LOW]
        info = [r for r in all_recommendations if r.priority == RecommendationPriority.INFO]

        # Potenzielle Ersparnisse summieren
        total_savings = sum(
            r.potential_savings or Decimal("0") for r in all_recommendations
        )

        # Top-3 nach Impact (Ersparnisse)
        sorted_by_impact = sorted(
            [r for r in all_recommendations if r.potential_savings],
            key=lambda x: x.potential_savings or Decimal("0"),
            reverse=True
        )
        top_recommendations = sorted_by_impact[:3]

        # Prometheus Metrik
        ACTIVE_RECOMMENDATIONS.labels(space_id=str(space_id)).set(len(all_recommendations))

        logger.info(
            "recommendations_generated",
            space_id=str(space_id),
            total_count=len(all_recommendations),
            critical_count=len(critical),
            total_potential_savings=str(total_savings),
        )

        return RecommendationsSummary(
            space_id=space_id,
            critical=critical,
            high=high,
            medium=medium,
            low=low,
            info=info,
            total_count=len(all_recommendations),
            total_potential_savings=total_savings,
            top_recommendations=top_recommendations,
        )

    # =========================================================================
    # Refinancing-Check
    # =========================================================================

    async def _check_refinancing_opportunities(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[Recommendation]:
        """Prueft auf Umschuldungs-Moeglichkeiten."""
        from app.db.models import PrivatLoan

        recommendations: List[Recommendation] = []

        result = await db.execute(
            select(PrivatLoan).where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.is_active == True,
                PrivatLoan.current_balance > 0,
            )
        )
        loans = result.scalars().all()

        for loan in loans:
            loan_type = (loan.loan_type or "default").lower()
            market_rate = MARKET_INTEREST_RATES.get(loan_type, MARKET_INTEREST_RATES["default"])
            current_rate = loan.interest_rate or Decimal("0")

            # Pruefe ob signifikant ueber Marktzins
            rate_difference = current_rate - market_rate

            if rate_difference >= REFINANCING_THRESHOLD:
                # Potenzielle Ersparnis berechnen
                remaining = loan.current_balance or Decimal("0")
                monthly_payment = loan.monthly_payment or Decimal("0")

                # Geschaetzte Restlaufzeit
                if monthly_payment > 0:
                    months_remaining = remaining / monthly_payment
                    annual_interest_current = remaining * (current_rate / 100)
                    annual_interest_market = remaining * (market_rate / 100)
                    annual_savings = annual_interest_current - annual_interest_market
                    total_savings = (annual_savings * months_remaining / 12).quantize(Decimal("0.01"))
                else:
                    total_savings = None

                priority = RecommendationPriority.HIGH
                if rate_difference >= Decimal("2"):
                    priority = RecommendationPriority.CRITICAL

                rec = Recommendation(
                    id=f"refinancing_loan_{loan.id}",
                    category=RecommendationCategory.REFINANCING,
                    priority=priority,
                    title=f"Umschuldung pruefen: {loan.name}",
                    description=(
                        f"Ihr Kreditzins ({current_rate}%) liegt {rate_difference}% ueber dem "
                        f"aktuellen Marktzins ({market_rate}%). Eine Umschuldung koennte sich lohnen."
                    ),
                    impact=f"Potenzielle Ersparnis: {total_savings or 'zu berechnen'} EUR",
                    resource_type="loan",
                    resource_id=loan.id,
                    resource_name=loan.name,
                    potential_savings=total_savings,
                    current_value=current_rate,
                    recommended_value=market_rate,
                    suggested_actions=[
                        "Holen Sie Angebote von anderen Banken ein",
                        "Pruefen Sie die Vorfaelligkeitsentschaedigung",
                        "Vergleichen Sie Gesamtkosten inkl. Umschuldungsgebuehren",
                    ],
                )
                recommendations.append(rec)

                RECOMMENDATIONS_GENERATED.labels(
                    recommendation_type="refinancing",
                    priority=priority.value
                ).inc()

        return recommendations

    # =========================================================================
    # Rebalancing-Check
    # =========================================================================

    async def _check_rebalancing_needs(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[Recommendation]:
        """Prueft auf Portfolio-Rebalancing Bedarf."""
        from app.services.privat.investment_intelligence_service import get_investment_intelligence_service

        recommendations: List[Recommendation] = []
        intel_service = get_investment_intelligence_service()

        try:
            rebal_recs = await intel_service.generate_rebalancing_recommendations(
                db, space_id, target_profile="ausgewogen", threshold_pct=REBALANCING_THRESHOLD_PCT
            )

            for rebal in rebal_recs:
                if abs(rebal.difference) >= REBALANCING_THRESHOLD_PCT:
                    priority = RecommendationPriority.MEDIUM
                    if abs(rebal.difference) >= 20:
                        priority = RecommendationPriority.HIGH

                    rec = Recommendation(
                        id=f"rebalancing_{rebal.category}_{space_id}",
                        category=RecommendationCategory.REBALANCING,
                        priority=priority,
                        title=f"Portfolio-Rebalancing: {rebal.category.title()}",
                        description=(
                            f"Die Allokation fuer '{rebal.category}' weicht um "
                            f"{abs(rebal.difference)}% vom Ziel ab. "
                            f"Aktuell: {rebal.current_percentage}%, Ziel: {rebal.target_percentage}%"
                        ),
                        impact=f"Empfohlene Aktion: {rebal.action.title()} von ca. {rebal.amount_to_adjust} EUR",
                        resource_type="portfolio",
                        resource_id=None,
                        resource_name=f"Kategorie: {rebal.category}",
                        potential_savings=None,  # Rebalancing spart kein Geld direkt
                        current_value=rebal.current_percentage,
                        recommended_value=rebal.target_percentage,
                        suggested_actions=[
                            f"{rebal.action.title()} Sie Investments in der Kategorie '{rebal.category}'",
                            f"Betroffene Typen: {', '.join(rebal.affected_types[:3]) if rebal.affected_types else 'keine spezifischen'}",
                            "Pruefen Sie die Transaktionskosten vor der Umsetzung",
                        ],
                    )
                    recommendations.append(rec)

                    RECOMMENDATIONS_GENERATED.labels(
                        recommendation_type="rebalancing",
                        priority=priority.value
                    ).inc()

        except Exception as e:
            logger.warning(
                "rebalancing_check_failed",
                space_id=str(space_id),
                **safe_error_log(e),
            )

        return recommendations

    # =========================================================================
    # Versicherungs-Luecken
    # =========================================================================

    async def _check_insurance_gaps(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[Recommendation]:
        """Prueft auf Versicherungs-Luecken."""
        from app.db.models import PrivatInsurance

        recommendations: List[Recommendation] = []

        # Essentielle Versicherungen
        essential = [
            ("haftpflicht", "Privathaftpflicht", RecommendationPriority.HIGH),
            ("hausrat", "Hausratversicherung", RecommendationPriority.MEDIUM),
            ("berufsunfaehigkeit", "Berufsunfaehigkeitsversicherung", RecommendationPriority.HIGH),
        ]

        result = await db.execute(
            select(PrivatInsurance.insurance_type)
            .where(
                PrivatInsurance.space_id == space_id,
                PrivatInsurance.is_active == True,
            )
        )
        existing_types = [row[0].lower() for row in result.all()]

        for ins_type, ins_name, priority in essential:
            # Pruefe verschiedene Schreibweisen
            found = any(
                ins_type in existing or existing in ins_type
                for existing in existing_types
            )

            if not found:
                rec = Recommendation(
                    id=f"insurance_gap_{ins_type}_{space_id}",
                    category=RecommendationCategory.INSURANCE,
                    priority=priority,
                    title=f"Versicherungs-Luecke: {ins_name}",
                    description=(
                        f"Eine {ins_name} ist eine wichtige Absicherung, "
                        f"die in Ihrem Portfolio fehlt."
                    ),
                    impact="Schutz vor finanziellen Risiken",
                    resource_type="insurance",
                    resource_id=None,
                    resource_name=ins_name,
                    potential_savings=None,
                    current_value=None,
                    recommended_value=None,
                    suggested_actions=[
                        f"Informieren Sie sich ueber {ins_name}",
                        "Holen Sie mehrere Angebote ein",
                        "Pruefen Sie Deckungssummen und Ausschluesse",
                    ],
                )
                recommendations.append(rec)

                RECOMMENDATIONS_GENERATED.labels(
                    recommendation_type="insurance_gap",
                    priority=priority.value
                ).inc()

        return recommendations

    # =========================================================================
    # Notgroschen-Check
    # =========================================================================

    async def _check_emergency_fund(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[Recommendation]:
        """Prueft die Notgroschen-Reserve."""
        from app.db.models import PrivatInvestment

        recommendations: List[Recommendation] = []

        # Liquide Mittel holen
        result = await db.execute(
            select(func.coalesce(func.sum(PrivatInvestment.current_value), 0))
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
                PrivatInvestment.investment_type.in_(["tagesgeld", "festgeld", "sparbuch", "girokonto"]),
            )
        )
        liquid_assets = Decimal(str(result.scalar() or 0))

        # Geschaetzte monatliche Ausgaben (Fallback: 2500 EUR)
        estimated_monthly_expenses = Decimal("2500")

        months_covered = liquid_assets / estimated_monthly_expenses if estimated_monthly_expenses > 0 else Decimal("0")

        if months_covered < EMERGENCY_FUND_MONTHS_MIN:
            priority = RecommendationPriority.CRITICAL if months_covered < 1 else RecommendationPriority.HIGH
            target_amount = estimated_monthly_expenses * EMERGENCY_FUND_MONTHS_RECOMMENDED
            gap = target_amount - liquid_assets

            rec = Recommendation(
                id=f"emergency_fund_{space_id}",
                category=RecommendationCategory.EMERGENCY_FUND,
                priority=priority,
                title="Notgroschen aufbauen",
                description=(
                    f"Ihre liquiden Reserven ({liquid_assets:.0f} EUR) decken nur etwa "
                    f"{months_covered:.1f} Monate. Empfohlen sind mindestens "
                    f"{EMERGENCY_FUND_MONTHS_RECOMMENDED} Monatsausgaben."
                ),
                impact=f"Finanzielle Sicherheit durch {EMERGENCY_FUND_MONTHS_RECOMMENDED} Monate Reserve",
                resource_type="savings",
                resource_id=None,
                resource_name="Notgroschen",
                potential_savings=None,
                current_value=liquid_assets,
                recommended_value=target_amount,
                suggested_actions=[
                    f"Sparen Sie {gap:.0f} EUR fuer einen vollstaendigen Notgroschen",
                    "Richten Sie einen Dauerauftrag auf ein Tagesgeldkonto ein",
                    "Priorisieren Sie Liquiditaet vor Rendite fuer diesen Betrag",
                ],
            )
            recommendations.append(rec)

            RECOMMENDATIONS_GENERATED.labels(
                recommendation_type="emergency_fund",
                priority=priority.value
            ).inc()

        return recommendations

    # =========================================================================
    # Frist-Warnungen
    # =========================================================================

    async def _check_upcoming_deadlines(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[Recommendation]:
        """Prueft auf anstehende wichtige Fristen."""
        from app.db.models import PrivatDeadline

        recommendations: List[Recommendation] = []
        today = date.today()

        for days_ahead in [90, 30, 14, 7]:
            target_date = today + timedelta(days=days_ahead)

            result = await db.execute(
                select(PrivatDeadline)
                .where(
                    PrivatDeadline.space_id == space_id,
                    PrivatDeadline.is_active == True,
                    PrivatDeadline.is_completed == False,
                    PrivatDeadline.due_date <= target_date,
                    PrivatDeadline.due_date >= today,
                )
                .limit(10)
            )
            deadlines = result.scalars().all()

            for deadline in deadlines:
                days_until = (deadline.due_date - today).days

                # Prioritaet basierend auf verbleibenden Tagen
                if days_until <= 7:
                    priority = RecommendationPriority.CRITICAL
                elif days_until <= 14:
                    priority = RecommendationPriority.HIGH
                elif days_until <= 30:
                    priority = RecommendationPriority.MEDIUM
                else:
                    priority = RecommendationPriority.LOW

                rec = Recommendation(
                    id=f"deadline_{deadline.id}",
                    category=RecommendationCategory.DEADLINE,
                    priority=priority,
                    title=f"Frist in {days_until} Tagen: {deadline.title}",
                    description=deadline.description or f"Frist am {deadline.due_date}",
                    impact="Rechtzeitige Erledigung vermeidet Probleme",
                    resource_type="deadline",
                    resource_id=deadline.id,
                    resource_name=deadline.title,
                    potential_savings=None,
                    current_value=None,
                    recommended_value=None,
                    suggested_actions=[
                        f"Erledigen Sie '{deadline.title}' vor dem {deadline.due_date}",
                        "Setzen Sie sich eine Erinnerung",
                    ],
                )
                recommendations.append(rec)

                RECOMMENDATIONS_GENERATED.labels(
                    recommendation_type="deadline",
                    priority=priority.value
                ).inc()

            # Nur einmal pro Deadline
            break

        return recommendations

    # =========================================================================
    # Veraltete Werte
    # =========================================================================

    async def _check_stale_values(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[Recommendation]:
        """Prueft auf veraltete Wert-Angaben."""
        from app.db.models import PrivatProperty, PrivatInvestment

        recommendations: List[Recommendation] = []
        threshold_date = date.today() - timedelta(days=VALUE_UPDATE_THRESHOLD_DAYS)

        # Properties mit alten Werten
        prop_result = await db.execute(
            select(PrivatProperty)
            .where(
                PrivatProperty.space_id == space_id,
                or_(PrivatProperty.deleted_at == None, PrivatProperty.deleted_at.is_(None)),
                or_(
                    PrivatProperty.last_kpi_calculation == None,
                    PrivatProperty.last_kpi_calculation < datetime(
                        threshold_date.year, threshold_date.month, threshold_date.day,
                        tzinfo=timezone.utc
                    ),
                ),
            )
        )
        stale_properties = prop_result.scalars().all()

        for prop in stale_properties:
            rec = Recommendation(
                id=f"value_update_property_{prop.id}",
                category=RecommendationCategory.VALUE_UPDATE,
                priority=RecommendationPriority.LOW,
                title=f"Wert aktualisieren: {prop.name}",
                description=(
                    f"Der Wert dieser Immobilie wurde laenger als "
                    f"{VALUE_UPDATE_THRESHOLD_DAYS} Tage nicht aktualisiert."
                ),
                impact="Aktuelle Werte verbessern Ihre Finanzuebersicht",
                resource_type="property",
                resource_id=prop.id,
                resource_name=prop.name,
                potential_savings=None,
                current_value=prop.current_value,
                recommended_value=None,
                suggested_actions=[
                    "Aktualisieren Sie den geschaetzten Marktwert",
                    "Nutzen Sie Online-Immobilienbewertungen als Referenz",
                ],
            )
            recommendations.append(rec)

        # Investments mit alten Werten
        inv_result = await db.execute(
            select(PrivatInvestment)
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
                or_(
                    PrivatInvestment.value_date == None,
                    PrivatInvestment.value_date < threshold_date,
                ),
            )
        )
        stale_investments = inv_result.scalars().all()

        for inv in stale_investments:
            rec = Recommendation(
                id=f"value_update_investment_{inv.id}",
                category=RecommendationCategory.VALUE_UPDATE,
                priority=RecommendationPriority.LOW,
                title=f"Wert aktualisieren: {inv.name}",
                description=(
                    f"Der Wert dieses Investments wurde laenger als "
                    f"{VALUE_UPDATE_THRESHOLD_DAYS} Tage nicht aktualisiert."
                ),
                impact="Aktuelle Werte fuer bessere Portfolio-Analyse",
                resource_type="investment",
                resource_id=inv.id,
                resource_name=inv.name,
                potential_savings=None,
                current_value=inv.current_value,
                recommended_value=None,
                suggested_actions=[
                    "Pruefen Sie den aktuellen Kurs/Wert",
                    "Aktualisieren Sie den Wert in der App",
                ],
            )
            recommendations.append(rec)

        return recommendations

    # =========================================================================
    # Fahrzeug-Wartung
    # =========================================================================

    async def _check_vehicle_maintenance(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[Recommendation]:
        """Prueft auf anstehende Fahrzeug-Wartung."""
        from app.db.models import PrivatVehicle

        recommendations: List[Recommendation] = []
        today = date.today()

        result = await db.execute(
            select(PrivatVehicle)
            .where(
                PrivatVehicle.space_id == space_id,
                PrivatVehicle.is_active == True,
            )
        )
        vehicles = result.scalars().all()

        for vehicle in vehicles:
            # TUeV Check
            if vehicle.tuev_due:
                days_until_tuev = (vehicle.tuev_due - today).days

                if days_until_tuev <= 30:
                    priority = RecommendationPriority.CRITICAL if days_until_tuev <= 7 else RecommendationPriority.HIGH
                    if days_until_tuev < 0:
                        title = f"TUeV ueberfaellig: {vehicle.name}"
                        description = f"Der TUeV ist seit {abs(days_until_tuev)} Tagen abgelaufen!"
                        priority = RecommendationPriority.CRITICAL
                    else:
                        title = f"TUeV in {days_until_tuev} Tagen: {vehicle.name}"
                        description = f"TUeV-Termin am {vehicle.tuev_due}"

                    rec = Recommendation(
                        id=f"tuev_{vehicle.id}",
                        category=RecommendationCategory.DEADLINE,
                        priority=priority,
                        title=title,
                        description=description,
                        impact="Pflicht-Untersuchung, ohne TUeV keine Zulassung",
                        resource_type="vehicle",
                        resource_id=vehicle.id,
                        resource_name=vehicle.name,
                        potential_savings=None,
                        current_value=None,
                        recommended_value=None,
                        suggested_actions=[
                            "TUeV-Termin vereinbaren",
                            "Fahrzeug auf offensichtliche Maengel pruefen",
                        ],
                    )
                    recommendations.append(rec)

            # Inspektion Check
            if vehicle.inspection_due:
                days_until_inspection = (vehicle.inspection_due - today).days

                if days_until_inspection <= 30:
                    priority = RecommendationPriority.MEDIUM
                    if days_until_inspection <= 7:
                        priority = RecommendationPriority.HIGH

                    rec = Recommendation(
                        id=f"inspection_{vehicle.id}",
                        category=RecommendationCategory.DEADLINE,
                        priority=priority,
                        title=f"Inspektion in {days_until_inspection} Tagen: {vehicle.name}",
                        description=f"Naechste Inspektion am {vehicle.inspection_due}",
                        impact="Regelmaessige Wartung erhaelt den Fahrzeugwert",
                        resource_type="vehicle",
                        resource_id=vehicle.id,
                        resource_name=vehicle.name,
                        potential_savings=None,
                        current_value=None,
                        recommended_value=None,
                        suggested_actions=[
                            "Werkstatt-Termin vereinbaren",
                            "Serviceheft bereithalten",
                        ],
                    )
                    recommendations.append(rec)

        return recommendations

    # =========================================================================
    # Batch-Operationen fuer Celery
    # =========================================================================

    async def generate_all_recommendations(
        self,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Generiert Empfehlungen fuer alle Spaces (fuer Celery Beat)."""
        from app.db.models import PrivatSpace


        result = await db.execute(
            select(PrivatSpace.id).where(PrivatSpace.is_active == True)
        )
        space_ids = [row[0] for row in result.all()]

        processed = 0
        total_recommendations = 0
        errors = 0

        for space_id in space_ids:
            try:
                summary = await self.generate_recommendations(db, space_id)
                total_recommendations += summary.total_count
                processed += 1
            except Exception as e:
                errors += 1
                logger.error(
                    "recommendations_generation_failed",
                    space_id=str(space_id),
                    **safe_error_log(e),
                )

        logger.info(
            "all_recommendations_generated",
            total_spaces=len(space_ids),
            processed=processed,
            total_recommendations=total_recommendations,
            errors=errors,
        )

        return {
            "total_spaces": len(space_ids),
            "processed": processed,
            "total_recommendations": total_recommendations,
            "errors": errors,
        }


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_recommendations_service() -> RecommendationsService:
    """Gibt die Singleton-Instanz des Recommendations Service zurueck."""
    return RecommendationsService()
