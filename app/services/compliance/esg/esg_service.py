"""
ESG Haupt-Service.

Zentrale Koordination aller ESG-Funktionen.
"""

from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.models_esg import (
    ESGCarbonFootprint, ESGSupplierRating, ESGCertification,
    ESGReport, ESGGoal, ESGScope, ESGCategory, CertificationStatus
)

logger = structlog.get_logger(__name__)


class ESGService:
    """
    Zentraler ESG-Service.

    Koordiniert alle ESG-bezogenen Funktionen und bietet
    eine einheitliche Schnittstelle.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_summary(
        self,
        company_id: UUID,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Hole ESG-Dashboard-Zusammenfassung.
        """
        today = date.today()
        if not period_start:
            period_start = date(today.year, 1, 1)
        if not period_end:
            period_end = today

        # CO2-Emissionen
        carbon_result = await self.db.execute(
            select(func.sum(ESGCarbonFootprint.co2_equivalent_kg)).where(
                and_(
                    ESGCarbonFootprint.company_id == company_id,
                    ESGCarbonFootprint.period_start >= period_start,
                    ESGCarbonFootprint.period_end <= period_end,
                )
            )
        )
        total_emissions = carbon_result.scalar() or 0

        # Emissionen nach Scope
        scope_result = await self.db.execute(
            select(
                ESGCarbonFootprint.scope,
                func.sum(ESGCarbonFootprint.co2_equivalent_kg)
            ).where(
                and_(
                    ESGCarbonFootprint.company_id == company_id,
                    ESGCarbonFootprint.period_start >= period_start,
                    ESGCarbonFootprint.period_end <= period_end,
                )
            ).group_by(ESGCarbonFootprint.scope)
        )
        emissions_by_scope = {
            row[0]: float(row[1] or 0) for row in scope_result.fetchall()
        }

        # Lieferanten-Durchschnittsbewertung
        supplier_result = await self.db.execute(
            select(func.avg(ESGSupplierRating.overall_score)).where(
                and_(
                    ESGSupplierRating.company_id == company_id,
                    ESGSupplierRating.rating_date >= period_start,
                )
            )
        )
        avg_supplier_score = supplier_result.scalar()

        # Anzahl bewerteter Lieferanten
        supplier_count_result = await self.db.execute(
            select(func.count(func.distinct(ESGSupplierRating.entity_id))).where(
                ESGSupplierRating.company_id == company_id
            )
        )
        rated_suppliers = supplier_count_result.scalar() or 0

        # Aktive Zertifizierungen
        cert_result = await self.db.execute(
            select(func.count()).where(
                and_(
                    ESGCertification.company_id == company_id,
                    ESGCertification.status == CertificationStatus.ACTIVE,
                )
            )
        )
        active_certifications = cert_result.scalar() or 0

        # Ziele und Fortschritt
        goals_result = await self.db.execute(
            select(ESGGoal).where(
                and_(
                    ESGGoal.company_id == company_id,
                    ESGGoal.is_active == True,
                )
            )
        )
        goals = goals_result.scalars().all()

        goals_on_track = sum(1 for g in goals if g.on_track is True)
        goals_total = len(goals)

        return {
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "carbon_footprint": {
                "total_emissions_kg": float(total_emissions),
                "total_emissions_tons": float(total_emissions) / 1000,
                "by_scope": emissions_by_scope,
            },
            "suppliers": {
                "rated_count": rated_suppliers,
                "average_score": round(float(avg_supplier_score), 1) if avg_supplier_score else None,
            },
            "certifications": {
                "active_count": active_certifications,
            },
            "goals": {
                "total": goals_total,
                "on_track": goals_on_track,
                "progress_rate": round(goals_on_track / goals_total * 100, 1) if goals_total > 0 else None,
            },
        }

    async def get_carbon_footprint_trend(
        self,
        company_id: UUID,
        months: int = 12,
    ) -> List[Dict[str, Any]]:
        """
        Hole CO2-Fussabdruck-Trend über Zeit.
        """
        result = await self.db.execute(
            select(
                func.date_trunc('month', ESGCarbonFootprint.period_start).label('month'),
                ESGCarbonFootprint.scope,
                func.sum(ESGCarbonFootprint.co2_equivalent_kg).label('total')
            ).where(
                ESGCarbonFootprint.company_id == company_id
            ).group_by(
                func.date_trunc('month', ESGCarbonFootprint.period_start),
                ESGCarbonFootprint.scope
            ).order_by(
                func.date_trunc('month', ESGCarbonFootprint.period_start)
            ).limit(months * 3)  # 3 Scopes
        )

        # Gruppiere nach Monat
        trend_data: Dict[str, Dict[str, float]] = {}
        for row in result.fetchall():
            month_str = row[0].strftime("%Y-%m") if row[0] else "unknown"
            if month_str not in trend_data:
                trend_data[month_str] = {"scope_1": 0, "scope_2": 0, "scope_3": 0}
            trend_data[month_str][row[1]] = float(row[2] or 0)

        return [
            {
                "month": month,
                "scope_1": data.get("scope_1", 0),
                "scope_2": data.get("scope_2", 0),
                "scope_3": data.get("scope_3", 0),
                "total": sum(data.values()),
            }
            for month, data in sorted(trend_data.items())
        ]

    async def create_goal(
        self,
        company_id: UUID,
        title: str,
        description: Optional[str],
        category: str,
        metric_name: str,
        metric_unit: Optional[str],
        baseline_value: Optional[float],
        baseline_year: Optional[int],
        target_value: float,
        target_year: int,
        sdg_goals: Optional[List[int]] = None,
    ) -> ESGGoal:
        """
        Erstelle ein neues ESG-Ziel.
        """
        # Validiere Kategorie
        valid_categories = [c.value for c in ESGCategory]
        if category not in valid_categories:
            raise ValueError(f"Ungültige Kategorie. Erlaubt: {valid_categories}")

        goal = ESGGoal(
            company_id=company_id,
            title=title,
            description=description,
            category=category,
            metric_name=metric_name,
            metric_unit=metric_unit,
            baseline_value=baseline_value,
            baseline_year=baseline_year,
            target_value=target_value,
            target_year=target_year,
            sdg_goals=sdg_goals or [],
            is_active=True,
        )

        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)

        logger.info(
            "esg_goal_created",
            goal_id=str(goal.id),
            company_id=str(company_id),
            title=title,
        )

        return goal

    async def update_goal_progress(
        self,
        goal_id: UUID,
        company_id: UUID,
        current_value: float,
    ) -> ESGGoal:
        """
        Aktualisiere den Fortschritt eines ESG-Ziels.
        """
        result = await self.db.execute(
            select(ESGGoal).where(
                and_(
                    ESGGoal.id == goal_id,
                    ESGGoal.company_id == company_id,
                )
            )
        )
        goal = result.scalar_one_or_none()

        if not goal:
            raise ValueError("Ziel nicht gefunden")

        goal.current_value = current_value
        goal.current_value_date = date.today()

        # Berechne Fortschritt
        if goal.baseline_value is not None and goal.target_value is not None:
            if goal.target_value != goal.baseline_value:
                progress = (current_value - goal.baseline_value) / (goal.target_value - goal.baseline_value) * 100
                goal.progress_percentage = max(0, min(100, progress))

                # Bestimme ob auf Kurs
                today = date.today()
                years_elapsed = today.year - (goal.baseline_year or today.year)
                years_total = goal.target_year - (goal.baseline_year or today.year)

                if years_total > 0:
                    expected_progress = (years_elapsed / years_total) * 100
                    goal.on_track = goal.progress_percentage >= expected_progress * 0.9  # 90% Toleranz

        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def get_goals(
        self,
        company_id: UUID,
        category: Optional[str] = None,
        active_only: bool = True,
    ) -> List[dict]:
        """
        Hole ESG-Ziele.
        """
        query = select(ESGGoal).where(ESGGoal.company_id == company_id)

        if category:
            query = query.where(ESGGoal.category == category)
        if active_only:
            query = query.where(ESGGoal.is_active == True)

        query = query.order_by(ESGGoal.target_year, ESGGoal.title)

        result = await self.db.execute(query)
        goals = result.scalars().all()

        return [
            {
                "id": str(g.id),
                "title": g.title,
                "description": g.description,
                "category": g.category,
                "metric_name": g.metric_name,
                "metric_unit": g.metric_unit,
                "baseline_value": g.baseline_value,
                "baseline_year": g.baseline_year,
                "target_value": g.target_value,
                "target_year": g.target_year,
                "current_value": g.current_value,
                "current_value_date": g.current_value_date.isoformat() if g.current_value_date else None,
                "progress_percentage": g.progress_percentage,
                "on_track": g.on_track,
                "sdg_goals": g.sdg_goals,
            }
            for g in goals
        ]

    async def get_sdg_mapping(
        self,
        company_id: UUID,
    ) -> Dict[int, List[str]]:
        """
        Hole Mapping von SDG-Zielen zu Unternehmenszielen.
        """
        result = await self.db.execute(
            select(ESGGoal).where(
                and_(
                    ESGGoal.company_id == company_id,
                    ESGGoal.is_active == True,
                    ESGGoal.sdg_goals != None,
                )
            )
        )
        goals = result.scalars().all()

        sdg_mapping: Dict[int, List[str]] = {}
        for goal in goals:
            for sdg in (goal.sdg_goals or []):
                if sdg not in sdg_mapping:
                    sdg_mapping[sdg] = []
                sdg_mapping[sdg].append(goal.title)

        return sdg_mapping


def get_esg_service(db: AsyncSession) -> ESGService:
    """Factory-Funktion für ESGService."""
    return ESGService(db)
