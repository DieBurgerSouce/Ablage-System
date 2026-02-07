"""
CO2-Fussabdruck Rechner.

Berechnung von Emissionen nach GHG Protocol.
"""

from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.models_esg import ESGCarbonFootprint, ESGScope

logger = structlog.get_logger(__name__)


# Standard-Emissionsfaktoren (kg CO2e pro Einheit)
# Quellen: DEFRA, UBA, GHG Protocol
EMISSION_FACTORS = {
    # Scope 1 - Direkte Emissionen
    "diesel_l": {"factor": 2.68, "unit": "Liter", "scope": "scope_1", "source": "DEFRA 2023"},
    "benzin_l": {"factor": 2.31, "unit": "Liter", "scope": "scope_1", "source": "DEFRA 2023"},
    "erdgas_kwh": {"factor": 0.202, "unit": "kWh", "scope": "scope_1", "source": "UBA 2023"},
    "erdgas_m3": {"factor": 2.0, "unit": "m3", "scope": "scope_1", "source": "UBA 2023"},
    "heizoel_l": {"factor": 2.68, "unit": "Liter", "scope": "scope_1", "source": "DEFRA 2023"},
    "lpg_l": {"factor": 1.51, "unit": "Liter", "scope": "scope_1", "source": "DEFRA 2023"},

    # Scope 2 - Indirekte Emissionen (Energie)
    "strom_de_kwh": {"factor": 0.420, "unit": "kWh", "scope": "scope_2", "source": "UBA 2023"},
    "strom_oeko_kwh": {"factor": 0.0, "unit": "kWh", "scope": "scope_2", "source": "Market-based"},
    "fernwaerme_kwh": {"factor": 0.200, "unit": "kWh", "scope": "scope_2", "source": "UBA 2023"},

    # Scope 3 - Weitere indirekte Emissionen
    "pkw_km": {"factor": 0.147, "unit": "km", "scope": "scope_3", "source": "DEFRA 2023"},
    "bahn_km": {"factor": 0.029, "unit": "km", "scope": "scope_3", "source": "DEFRA 2023"},
    "flug_kurz_km": {"factor": 0.255, "unit": "km", "scope": "scope_3", "source": "DEFRA 2023"},
    "flug_lang_km": {"factor": 0.195, "unit": "km", "scope": "scope_3", "source": "DEFRA 2023"},
    "hotel_nacht": {"factor": 31.1, "unit": "Nacht", "scope": "scope_3", "source": "DEFRA 2023"},
    "papier_kg": {"factor": 0.919, "unit": "kg", "scope": "scope_3", "source": "DEFRA 2023"},
    "wasser_m3": {"factor": 0.344, "unit": "m3", "scope": "scope_3", "source": "DEFRA 2023"},
    "abfall_kg": {"factor": 0.467, "unit": "kg", "scope": "scope_3", "source": "DEFRA 2023"},
}


class CarbonCalculator:
    """
    CO2-Rechner nach GHG Protocol.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_emission_factors() -> Dict[str, Dict[str, Any]]:
        """Gebe verfuegbare Emissionsfaktoren zurueck."""
        return EMISSION_FACTORS

    @staticmethod
    def calculate_emissions(
        source_category: str,
        consumption_value: float,
        custom_factor: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Berechne CO2-Emissionen fuer einen Verbrauchswert.
        """
        if custom_factor is not None:
            return {
                "co2_equivalent_kg": consumption_value * custom_factor,
                "emission_factor": custom_factor,
                "emission_factor_source": "Benutzerdefiniert",
                "scope": None,
            }

        factor_data = EMISSION_FACTORS.get(source_category)
        if not factor_data:
            raise ValueError(f"Unbekannte Emissionsquelle: {source_category}")

        return {
            "co2_equivalent_kg": consumption_value * factor_data["factor"],
            "emission_factor": factor_data["factor"],
            "emission_factor_source": factor_data["source"],
            "scope": factor_data["scope"],
            "unit": factor_data["unit"],
        }

    async def record_emissions(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
        source_category: str,
        consumption_value: float,
        consumption_unit: str,
        source_description: Optional[str] = None,
        custom_factor: Optional[float] = None,
        custom_factor_source: Optional[str] = None,
        document_id: Optional[UUID] = None,
        data_quality: str = "medium",
        calculation_method: str = "GHG Protocol",
        recorded_by_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> ESGCarbonFootprint:
        """
        Erfasse CO2-Emissionen.
        """
        # Berechne Emissionen
        calc_result = self.calculate_emissions(
            source_category=source_category,
            consumption_value=consumption_value,
            custom_factor=custom_factor,
        )

        # Bestimme Scope
        scope = calc_result.get("scope")
        if not scope:
            factor_data = EMISSION_FACTORS.get(source_category, {})
            scope = factor_data.get("scope", "scope_3")

        entry = ESGCarbonFootprint(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            scope=scope,
            source_category=source_category,
            source_description=source_description,
            consumption_value=consumption_value,
            consumption_unit=consumption_unit,
            co2_equivalent_kg=calc_result["co2_equivalent_kg"],
            emission_factor=calc_result["emission_factor"],
            emission_factor_source=custom_factor_source or calc_result.get("emission_factor_source"),
            document_id=document_id,
            calculation_method=calculation_method,
            data_quality=data_quality,
            recorded_by_id=recorded_by_id,
            verified=False,
            notes=notes,
        )

        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        logger.info(
            "carbon_emissions_recorded",
            entry_id=str(entry.id),
            company_id=str(company_id),
            scope=scope,
            co2_kg=calc_result["co2_equivalent_kg"],
        )

        return entry

    async def get_emissions(
        self,
        company_id: UUID,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        scope: Optional[str] = None,
        source_category: Optional[str] = None,
        verified_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole erfasste Emissionen.
        """
        query = select(ESGCarbonFootprint).where(
            ESGCarbonFootprint.company_id == company_id
        )

        if period_start:
            query = query.where(ESGCarbonFootprint.period_start >= period_start)
        if period_end:
            query = query.where(ESGCarbonFootprint.period_end <= period_end)
        if scope:
            query = query.where(ESGCarbonFootprint.scope == scope)
        if source_category:
            query = query.where(ESGCarbonFootprint.source_category == source_category)
        if verified_only:
            query = query.where(ESGCarbonFootprint.verified == True)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(ESGCarbonFootprint.period_start.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        entries = result.scalars().all()

        return [
            {
                "id": str(e.id),
                "period_start": e.period_start.isoformat() if e.period_start else None,
                "period_end": e.period_end.isoformat() if e.period_end else None,
                "scope": e.scope,
                "source_category": e.source_category,
                "source_description": e.source_description,
                "consumption_value": e.consumption_value,
                "consumption_unit": e.consumption_unit,
                "co2_equivalent_kg": e.co2_equivalent_kg,
                "emission_factor": e.emission_factor,
                "emission_factor_source": e.emission_factor_source,
                "data_quality": e.data_quality,
                "verified": e.verified,
                "notes": e.notes,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ], total

    async def get_emissions_summary(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """
        Hole Emissions-Zusammenfassung.
        """
        # Total
        total_result = await self.db.execute(
            select(func.sum(ESGCarbonFootprint.co2_equivalent_kg)).where(
                and_(
                    ESGCarbonFootprint.company_id == company_id,
                    ESGCarbonFootprint.period_start >= period_start,
                    ESGCarbonFootprint.period_end <= period_end,
                )
            )
        )
        total_kg = total_result.scalar() or 0

        # Nach Scope
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
        by_scope = {row[0]: float(row[1] or 0) for row in scope_result.fetchall()}

        # Nach Kategorie (Top 5)
        category_result = await self.db.execute(
            select(
                ESGCarbonFootprint.source_category,
                func.sum(ESGCarbonFootprint.co2_equivalent_kg)
            ).where(
                and_(
                    ESGCarbonFootprint.company_id == company_id,
                    ESGCarbonFootprint.period_start >= period_start,
                    ESGCarbonFootprint.period_end <= period_end,
                )
            ).group_by(ESGCarbonFootprint.source_category)
            .order_by(func.sum(ESGCarbonFootprint.co2_equivalent_kg).desc())
            .limit(5)
        )
        top_categories = [
            {"category": row[0], "co2_kg": float(row[1] or 0)}
            for row in category_result.fetchall()
        ]

        return {
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "total_co2_kg": float(total_kg),
            "total_co2_tons": float(total_kg) / 1000,
            "by_scope": {
                "scope_1": by_scope.get("scope_1", 0),
                "scope_2": by_scope.get("scope_2", 0),
                "scope_3": by_scope.get("scope_3", 0),
            },
            "top_categories": top_categories,
        }

    async def verify_entry(
        self,
        entry_id: UUID,
        company_id: UUID,
        verified_by_id: UUID,
    ) -> bool:
        """
        Verifiziere einen Emissions-Eintrag.
        """
        result = await self.db.execute(
            select(ESGCarbonFootprint).where(
                and_(
                    ESGCarbonFootprint.id == entry_id,
                    ESGCarbonFootprint.company_id == company_id,
                )
            )
        )
        entry = result.scalar_one_or_none()

        if not entry:
            return False

        entry.verified = True
        entry.verified_at = datetime.now(timezone.utc)
        entry.verified_by_id = verified_by_id

        await self.db.commit()

        return True


def get_carbon_calculator(db: AsyncSession) -> CarbonCalculator:
    """Factory-Funktion fuer CarbonCalculator."""
    return CarbonCalculator(db)
