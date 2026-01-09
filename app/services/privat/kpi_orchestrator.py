# -*- coding: utf-8 -*-
"""
KPIOrchestrationService - Koordiniert alle bestehenden Calculation Services.

Dieser Service orchestriert KEINE eigenen Berechnungen, sondern:
- Koordiniert PropertyCalculationService, VehicleCalculationService,
  LoanScenarioService, InvestmentIntelligenceService, FinancialHealthService
- Stellt korrekte Abhaengigkeitsreihenfolge sicher
- Publiziert Events bei Aenderungen
- Bietet Batch-Operationen fuer periodische Neuberechnung

Enterprise Feature - Singleton Pattern.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

KPI_ORCHESTRATION_RUNS = Counter(
    "kpi_orchestration_runs_total",
    "Anzahl der KPI-Orchestrierungen",
    ["operation_type", "status"]
)

KPI_ORCHESTRATION_DURATION = Histogram(
    "kpi_orchestration_duration_seconds",
    "Dauer der KPI-Orchestrierung",
    ["operation_type"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

KPI_ENTITIES_PROCESSED = Gauge(
    "kpi_entities_processed_last_run",
    "Anzahl verarbeiteter Entities bei letztem Lauf",
    ["entity_type"]
)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EntityKPIResult:
    """Ergebnis der KPI-Berechnung fuer eine Entity."""
    entity_type: str  # "property", "vehicle", "loan", "investment", "insurance"
    entity_id: UUID
    success: bool
    calculated_kpis: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SpaceKPIResult:
    """Ergebnis der KPI-Berechnung fuer einen Space."""
    space_id: UUID

    # Ergebnisse pro Entity-Typ
    property_results: List[EntityKPIResult] = field(default_factory=list)
    vehicle_results: List[EntityKPIResult] = field(default_factory=list)
    loan_results: List[EntityKPIResult] = field(default_factory=list)
    investment_results: List[EntityKPIResult] = field(default_factory=list)
    insurance_results: List[EntityKPIResult] = field(default_factory=list)

    # Financial Health Score (abhaengig von allen anderen)
    financial_health_score: Optional[Decimal] = None
    financial_health_dimensions: Dict[str, Decimal] = field(default_factory=dict)

    # Zusammenfassung
    total_calculated: int = 0
    total_errors: int = 0

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BatchKPIResult:
    """Ergebnis der Batch-KPI-Berechnung."""
    total_spaces: int = 0
    spaces_processed: int = 0
    spaces_skipped: int = 0

    total_entities_calculated: int = 0
    total_errors: int = 0
    errors: List[str] = field(default_factory=list)

    # Nach Entity-Typ
    properties_calculated: int = 0
    vehicles_calculated: int = 0
    loans_calculated: int = 0
    investments_calculated: int = 0
    insurances_calculated: int = 0

    average_health_score: Optional[Decimal] = None

    duration_seconds: float = 0.0
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Service
# =============================================================================

class KPIOrchestrationService:
    """
    Koordiniert alle bestehenden Calculation Services.

    Fuehrt KEINE eigenen Berechnungen durch, sondern:
    - Ruft bestehende Services in korrekter Reihenfolge auf
    - Stellt sicher dass Financial Health NACH allen anderen laeuft
    - Publiziert Events bei Aenderungen
    - Bietet Batch-Operationen
    """

    def __init__(self) -> None:
        """Initialisiert den Orchestrator."""
        # Lazy Loading - Services werden bei Bedarf geholt
        self._property_service = None
        self._vehicle_service = None
        self._loan_service = None
        self._investment_service = None
        self._insurance_service = None
        self._financial_health_service = None

    # =========================================================================
    # Service Getters (Lazy Loading)
    # =========================================================================

    def _get_property_service(self):
        """Lazy Load PropertyIntelligenceService."""
        if self._property_service is None:
            from app.services.privat.property_intelligence_service import (
                get_property_intelligence_service
            )
            self._property_service = get_property_intelligence_service()
        return self._property_service

    def _get_vehicle_service(self):
        """Lazy Load VehicleIntelligenceService."""
        if self._vehicle_service is None:
            from app.services.privat.vehicle_intelligence_service import (
                get_vehicle_intelligence_service
            )
            self._vehicle_service = get_vehicle_intelligence_service()
        return self._vehicle_service

    def _get_loan_service(self):
        """Lazy Load LoanScenarioService."""
        if self._loan_service is None:
            from app.services.privat.loan_scenario_service import (
                get_loan_scenario_service
            )
            self._loan_service = get_loan_scenario_service()
        return self._loan_service

    def _get_investment_service(self):
        """Lazy Load InvestmentIntelligenceService."""
        if self._investment_service is None:
            from app.services.privat.investment_intelligence_service import (
                get_investment_intelligence_service
            )
            self._investment_service = get_investment_intelligence_service()
        return self._investment_service

    def _get_insurance_service(self):
        """Lazy Load InsuranceIntelligenceService."""
        if self._insurance_service is None:
            from app.services.privat.insurance_intelligence_service import (
                get_insurance_intelligence_service
            )
            self._insurance_service = get_insurance_intelligence_service()
        return self._insurance_service

    def _get_financial_health_service(self):
        """Lazy Load FinancialHealthService."""
        if self._financial_health_service is None:
            from app.services.privat.financial_health_service import (
                get_financial_health_service
            )
            self._financial_health_service = get_financial_health_service()
        return self._financial_health_service

    # =========================================================================
    # Space-Level Orchestration
    # =========================================================================

    async def recalculate_all_for_space(
        self,
        db: AsyncSession,
        space_id: UUID,
        include_properties: bool = True,
        include_vehicles: bool = True,
        include_loans: bool = True,
        include_investments: bool = True,
        include_insurances: bool = True,
        include_financial_health: bool = True,
    ) -> SpaceKPIResult:
        """
        Berechnet alle KPIs fuer einen Space in korrekter Reihenfolge.

        Reihenfolge:
        1. Properties (unabhaengig)
        2. Vehicles (unabhaengig)
        3. Loans (unabhaengig)
        4. Investments (unabhaengig)
        5. Insurances (unabhaengig)
        6. Financial Health (ABHAENGIG von allen anderen!)

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            include_*: Welche Entity-Typen berechnet werden sollen

        Returns:
            SpaceKPIResult mit allen Ergebnissen
        """
        from datetime import datetime, timezone
        import time

        start_time = time.time()
        KPI_ORCHESTRATION_RUNS.labels(operation_type="space", status="started").inc()

        result = SpaceKPIResult(space_id=space_id)

        try:
            # 1. Properties
            if include_properties:
                result.property_results = await self._calculate_property_kpis(
                    db, space_id
                )

            # 2. Vehicles
            if include_vehicles:
                result.vehicle_results = await self._calculate_vehicle_kpis(
                    db, space_id
                )

            # 3. Loans
            if include_loans:
                result.loan_results = await self._calculate_loan_kpis(
                    db, space_id
                )

            # 4. Investments
            if include_investments:
                result.investment_results = await self._calculate_investment_kpis(
                    db, space_id
                )

            # 5. Insurances
            if include_insurances:
                result.insurance_results = await self._calculate_insurance_kpis(
                    db, space_id
                )

            # 6. Financial Health (MUSS zuletzt kommen!)
            if include_financial_health:
                health_result = await self._calculate_financial_health(db, space_id)
                result.financial_health_score = health_result.get("overall_score")
                result.financial_health_dimensions = health_result.get("dimensions", {})

            # Zusammenfassung berechnen
            all_results = (
                result.property_results +
                result.vehicle_results +
                result.loan_results +
                result.investment_results +
                result.insurance_results
            )
            result.total_calculated = sum(1 for r in all_results if r.success)
            result.total_errors = sum(1 for r in all_results if not r.success)

            # Events publizieren
            await self._publish_recalculation_events(db, space_id, result)

            duration = time.time() - start_time
            KPI_ORCHESTRATION_DURATION.labels(operation_type="space").observe(duration)
            KPI_ORCHESTRATION_RUNS.labels(operation_type="space", status="completed").inc()

            logger.info(
                "kpi_orchestration_completed",
                space_id=str(space_id),
                total_calculated=result.total_calculated,
                total_errors=result.total_errors,
                health_score=float(result.financial_health_score) if result.financial_health_score else None,
                duration_seconds=duration,
            )

            return result

        except Exception as e:
            KPI_ORCHESTRATION_RUNS.labels(operation_type="space", status="failed").inc()
            logger.exception(
                "kpi_orchestration_failed",
                space_id=str(space_id),
                error=str(e),
            )
            raise

    # =========================================================================
    # Entity-Specific Calculations (Delegation)
    # =========================================================================

    async def _calculate_property_kpis(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[EntityKPIResult]:
        """Berechnet Property KPIs via PropertyIntelligenceService."""
        from app.db.models import PrivatProperty

        results: List[EntityKPIResult] = []

        # Alle Properties des Spaces laden
        query = select(PrivatProperty).where(
            PrivatProperty.space_id == space_id,
            PrivatProperty.deleted_at.is_(None),
        )
        db_result = await db.execute(query)
        properties = db_result.scalars().all()

        service = self._get_property_service()

        for prop in properties:
            try:
                analytics = await service.get_full_analytics(db, prop.id, persist=True)
                results.append(EntityKPIResult(
                    entity_type="property",
                    entity_id=prop.id,
                    success=True,
                    calculated_kpis={
                        "gross_yield": float(analytics.gross_rental_yield) if analytics.gross_rental_yield else None,
                        "net_yield": float(analytics.net_rental_yield) if analytics.net_rental_yield else None,
                        "estimated_value": float(analytics.valuation.estimated_current_value) if analytics.valuation else None,
                        "health_score": float(analytics.health_score),
                    }
                ))
            except Exception as e:
                results.append(EntityKPIResult(
                    entity_type="property",
                    entity_id=prop.id,
                    success=False,
                    error=str(e),
                ))

        KPI_ENTITIES_PROCESSED.labels(entity_type="property").set(len(results))
        return results

    async def _calculate_vehicle_kpis(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[EntityKPIResult]:
        """Berechnet Vehicle KPIs via VehicleIntelligenceService."""
        from app.db.models import PrivatVehicle

        results: List[EntityKPIResult] = []

        query = select(PrivatVehicle).where(
            PrivatVehicle.space_id == space_id,
            PrivatVehicle.deleted_at.is_(None),
        )
        db_result = await db.execute(query)
        vehicles = db_result.scalars().all()

        service = self._get_vehicle_service()

        for vehicle in vehicles:
            try:
                analytics = await service.get_full_analytics(db, vehicle.id, persist=True)
                results.append(EntityKPIResult(
                    entity_type="vehicle",
                    entity_id=vehicle.id,
                    success=True,
                    calculated_kpis={
                        "current_value": float(analytics.current_value) if analytics.current_value else None,
                        "monthly_tco": float(analytics.monthly_tco) if analytics.monthly_tco else None,
                        "depreciation_rate": float(analytics.annual_depreciation_rate) if analytics.annual_depreciation_rate else None,
                    }
                ))
            except Exception as e:
                results.append(EntityKPIResult(
                    entity_type="vehicle",
                    entity_id=vehicle.id,
                    success=False,
                    error=str(e),
                ))

        KPI_ENTITIES_PROCESSED.labels(entity_type="vehicle").set(len(results))
        return results

    async def _calculate_loan_kpis(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[EntityKPIResult]:
        """Berechnet Loan KPIs via LoanScenarioService."""
        from app.db.models import PrivatLoan

        results: List[EntityKPIResult] = []

        query = select(PrivatLoan).where(
            PrivatLoan.space_id == space_id,
            PrivatLoan.deleted_at.is_(None),
        )
        db_result = await db.execute(query)
        loans = db_result.scalars().all()

        service = self._get_loan_service()

        for loan in loans:
            try:
                # Hole aktuellen Amortisierungsplan
                analysis = await service.get_full_analysis(db, loan.id, persist=True)
                results.append(EntityKPIResult(
                    entity_type="loan",
                    entity_id=loan.id,
                    success=True,
                    calculated_kpis={
                        "remaining_balance": float(analysis.remaining_balance) if analysis else None,
                        "total_interest_remaining": float(analysis.total_interest_remaining) if analysis else None,
                        "months_remaining": analysis.months_remaining if analysis else None,
                    }
                ))
            except Exception as e:
                results.append(EntityKPIResult(
                    entity_type="loan",
                    entity_id=loan.id,
                    success=False,
                    error=str(e),
                ))

        KPI_ENTITIES_PROCESSED.labels(entity_type="loan").set(len(results))
        return results

    async def _calculate_investment_kpis(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[EntityKPIResult]:
        """Berechnet Investment KPIs via InvestmentIntelligenceService."""
        from app.db.models import PrivatInvestment

        results: List[EntityKPIResult] = []

        query = select(PrivatInvestment).where(
            PrivatInvestment.space_id == space_id,
            PrivatInvestment.deleted_at.is_(None),
        )
        db_result = await db.execute(query)
        investments = db_result.scalars().all()

        service = self._get_investment_service()

        for investment in investments:
            try:
                analytics = await service.get_full_analytics(db, investment.id, persist=True)
                results.append(EntityKPIResult(
                    entity_type="investment",
                    entity_id=investment.id,
                    success=True,
                    calculated_kpis={
                        "current_value": float(analytics.current_value) if analytics.current_value else None,
                        "total_return": float(analytics.total_return_percent) if analytics.total_return_percent else None,
                        "annual_return": float(analytics.annual_return_percent) if analytics.annual_return_percent else None,
                    }
                ))
            except Exception as e:
                results.append(EntityKPIResult(
                    entity_type="investment",
                    entity_id=investment.id,
                    success=False,
                    error=str(e),
                ))

        KPI_ENTITIES_PROCESSED.labels(entity_type="investment").set(len(results))
        return results

    async def _calculate_insurance_kpis(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[EntityKPIResult]:
        """Berechnet Insurance KPIs via InsuranceIntelligenceService."""
        service = self._get_insurance_service()

        results: List[EntityKPIResult] = []

        try:
            # Insurance Intelligence liefert Space-Level Ergebnis
            analysis = await service.get_full_analysis(db, space_id, persist=True)

            # Ein "virtuelles" Ergebnis fuer den ganzen Space
            results.append(EntityKPIResult(
                entity_type="insurance",
                entity_id=space_id,  # Space-ID als "Entity"
                success=True,
                calculated_kpis={
                    "coverage_score": float(analysis.coverage_score),
                    "health_score": float(analysis.health_score),
                    "annual_premium_total": float(analysis.annual_premium_total),
                    "urgent_deadlines": analysis.urgent_deadlines_count,
                }
            ))
        except Exception as e:
            results.append(EntityKPIResult(
                entity_type="insurance",
                entity_id=space_id,
                success=False,
                error=str(e),
            ))

        KPI_ENTITIES_PROCESSED.labels(entity_type="insurance").set(len(results))
        return results

    async def _calculate_financial_health(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> Dict[str, Any]:
        """
        Berechnet Financial Health Score (MUSS nach allen anderen laufen!).

        Der FinancialHealthService aggregiert:
        - Vermoegenswerte (Properties, Vehicles, Investments)
        - Verbindlichkeiten (Loans)
        - Absicherung (Insurances)
        - Cash Flow
        """
        service = self._get_financial_health_service()

        try:
            health = await service.calculate_health_score(db, space_id, persist=True)
            return {
                "overall_score": health.overall_score,
                "dimensions": {
                    "liquidity": health.liquidity_score,
                    "assets": health.assets_score,
                    "liabilities": health.liabilities_score,
                    "insurance": health.insurance_score,
                    "savings": health.savings_score,
                    "diversification": health.diversification_score,
                }
            }
        except Exception as e:
            logger.warning(
                "financial_health_calculation_failed",
                space_id=str(space_id),
                error=str(e),
            )
            return {"overall_score": None, "dimensions": {}}

    # =========================================================================
    # Event Publishing
    # =========================================================================

    async def _publish_recalculation_events(
        self,
        db: AsyncSession,
        space_id: UUID,
        result: SpaceKPIResult,
    ) -> None:
        """Publiziert Events nach Neuberechnung."""
        try:
            from app.services.events.event_bus import get_event_bus, EventType

            event_bus = get_event_bus()

            # System-Event fuer KPI-Neuberechnung
            await event_bus.publish(
                EventType.SYSTEM_KPI_RECALCULATION,
                {
                    "space_id": str(space_id),
                    "total_calculated": result.total_calculated,
                    "total_errors": result.total_errors,
                    "health_score": float(result.financial_health_score) if result.financial_health_score else None,
                    "properties": len(result.property_results),
                    "vehicles": len(result.vehicle_results),
                    "loans": len(result.loan_results),
                    "investments": len(result.investment_results),
                }
            )

        except Exception as e:
            # Event-Publishing sollte nie die Hauptfunktion blockieren
            logger.warning(
                "kpi_event_publishing_failed",
                space_id=str(space_id),
                error=str(e),
            )

    # =========================================================================
    # Batch Operations
    # =========================================================================

    async def recalculate_all_spaces(
        self,
        db: AsyncSession,
        space_ids: Optional[List[UUID]] = None,
    ) -> BatchKPIResult:
        """
        Berechnet KPIs fuer alle (oder ausgewaehlte) Spaces.

        Args:
            db: Datenbank-Session
            space_ids: Optional: Nur diese Spaces berechnen

        Returns:
            BatchKPIResult mit Statistiken
        """
        import time
        from app.db.models import PrivatSpace

        start_time = time.time()
        KPI_ORCHESTRATION_RUNS.labels(operation_type="batch", status="started").inc()

        # Spaces laden
        if space_ids:
            query = select(PrivatSpace).where(PrivatSpace.id.in_(space_ids))
        else:
            query = select(PrivatSpace).where(PrivatSpace.deleted_at.is_(None))

        db_result = await db.execute(query)
        spaces = db_result.scalars().all()

        result = BatchKPIResult(total_spaces=len(spaces))
        total_health_scores: List[Decimal] = []

        for space in spaces:
            try:
                space_result = await self.recalculate_all_for_space(db, space.id)
                result.spaces_processed += 1
                result.total_entities_calculated += space_result.total_calculated
                result.total_errors += space_result.total_errors

                # Nach Typ zaehlen
                result.properties_calculated += len([r for r in space_result.property_results if r.success])
                result.vehicles_calculated += len([r for r in space_result.vehicle_results if r.success])
                result.loans_calculated += len([r for r in space_result.loan_results if r.success])
                result.investments_calculated += len([r for r in space_result.investment_results if r.success])
                result.insurances_calculated += len([r for r in space_result.insurance_results if r.success])

                if space_result.financial_health_score:
                    total_health_scores.append(space_result.financial_health_score)

            except Exception as e:
                result.spaces_skipped += 1
                result.errors.append(f"Space {space.id}: {str(e)}")
                logger.warning(
                    "batch_space_calculation_failed",
                    space_id=str(space.id),
                    error=str(e),
                )

        # Durchschnittlichen Health Score berechnen
        if total_health_scores:
            result.average_health_score = (
                sum(total_health_scores) / len(total_health_scores)
            ).quantize(Decimal("0.01"))

        result.duration_seconds = time.time() - start_time

        KPI_ORCHESTRATION_DURATION.labels(operation_type="batch").observe(result.duration_seconds)
        KPI_ORCHESTRATION_RUNS.labels(operation_type="batch", status="completed").inc()

        await db.commit()

        logger.info(
            "batch_kpi_orchestration_completed",
            total_spaces=result.total_spaces,
            spaces_processed=result.spaces_processed,
            spaces_skipped=result.spaces_skipped,
            total_entities=result.total_entities_calculated,
            average_health_score=float(result.average_health_score) if result.average_health_score else None,
            duration_seconds=result.duration_seconds,
        )

        return result

    # =========================================================================
    # Single Entity Recalculation
    # =========================================================================

    async def recalculate_single_entity(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: UUID,
        recalculate_health: bool = True,
    ) -> EntityKPIResult:
        """
        Berechnet KPIs fuer eine einzelne Entity.

        Nuetzlich wenn sich Daten einer Entity geaendert haben und
        nur diese neu berechnet werden soll.

        Args:
            db: Datenbank-Session
            entity_type: "property", "vehicle", "loan", "investment"
            entity_id: Entity-ID
            recalculate_health: Ob Financial Health auch neu berechnet werden soll

        Returns:
            EntityKPIResult
        """
        KPI_ORCHESTRATION_RUNS.labels(operation_type="single", status="started").inc()

        result: EntityKPIResult

        try:
            if entity_type == "property":
                service = self._get_property_service()
                analytics = await service.get_full_analytics(db, entity_id, persist=True)
                result = EntityKPIResult(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    success=True,
                    calculated_kpis={"health_score": float(analytics.health_score)},
                )

            elif entity_type == "vehicle":
                service = self._get_vehicle_service()
                analytics = await service.get_full_analytics(db, entity_id, persist=True)
                result = EntityKPIResult(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    success=True,
                    calculated_kpis={
                        "current_value": float(analytics.current_value) if analytics.current_value else None
                    },
                )

            elif entity_type == "loan":
                service = self._get_loan_service()
                analysis = await service.get_full_analysis(db, entity_id, persist=True)
                result = EntityKPIResult(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    success=True,
                    calculated_kpis={
                        "remaining_balance": float(analysis.remaining_balance) if analysis else None
                    },
                )

            elif entity_type == "investment":
                service = self._get_investment_service()
                analytics = await service.get_full_analytics(db, entity_id, persist=True)
                result = EntityKPIResult(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    success=True,
                    calculated_kpis={
                        "current_value": float(analytics.current_value) if analytics.current_value else None
                    },
                )

            else:
                result = EntityKPIResult(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    success=False,
                    error=f"Unbekannter Entity-Typ: {entity_type}",
                )

            # Financial Health neu berechnen (wenn gewuenscht)
            if recalculate_health and result.success:
                # Space-ID holen
                space_id = await self._get_space_id_for_entity(db, entity_type, entity_id)
                if space_id:
                    await self._calculate_financial_health(db, space_id)

            KPI_ORCHESTRATION_RUNS.labels(operation_type="single", status="completed").inc()

            logger.info(
                "single_entity_kpi_calculated",
                entity_type=entity_type,
                entity_id=str(entity_id),
                success=result.success,
            )

            return result

        except Exception as e:
            KPI_ORCHESTRATION_RUNS.labels(operation_type="single", status="failed").inc()
            logger.exception(
                "single_entity_kpi_failed",
                entity_type=entity_type,
                entity_id=str(entity_id),
                error=str(e),
            )
            return EntityKPIResult(
                entity_type=entity_type,
                entity_id=entity_id,
                success=False,
                error=str(e),
            )

    async def _get_space_id_for_entity(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: UUID,
    ) -> Optional[UUID]:
        """Ermittelt die Space-ID fuer eine Entity."""
        from app.db.models import PrivatProperty, PrivatVehicle, PrivatLoan, PrivatInvestment

        model_map = {
            "property": PrivatProperty,
            "vehicle": PrivatVehicle,
            "loan": PrivatLoan,
            "investment": PrivatInvestment,
        }

        model = model_map.get(entity_type)
        if not model:
            return None

        result = await db.execute(
            select(model.space_id).where(model.id == entity_id)
        )
        return result.scalar_one_or_none()


# =============================================================================
# Singleton
# =============================================================================

_kpi_orchestration_service: Optional[KPIOrchestrationService] = None
_service_lock = threading.Lock()


def get_kpi_orchestration_service() -> KPIOrchestrationService:
    """Factory fuer KPIOrchestrationService Singleton (Thread-safe)."""
    global _kpi_orchestration_service
    if _kpi_orchestration_service is None:
        with _service_lock:
            if _kpi_orchestration_service is None:
                _kpi_orchestration_service = KPIOrchestrationService()
    return _kpi_orchestration_service
