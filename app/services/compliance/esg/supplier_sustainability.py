"""
Lieferanten-Nachhaltigkeitsbewertung.

Bewertung und Tracking der Lieferketten-Nachhaltigkeit.
"""

from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.models_esg import ESGSupplierRating

logger = structlog.get_logger(__name__)


# Bewertungskriterien mit Gewichtung
RATING_CRITERIA = {
    "environmental": {
        "weight": 0.35,
        "criteria": {
            "co2_emissions": {"weight": 0.30, "label": "CO2-Emissionen"},
            "energy_efficiency": {"weight": 0.25, "label": "Energieeffizienz"},
            "waste_management": {"weight": 0.20, "label": "Abfallmanagement"},
            "water_usage": {"weight": 0.15, "label": "Wasserverbrauch"},
            "certifications": {"weight": 0.10, "label": "Umweltzertifizierungen"},
        },
    },
    "social": {
        "weight": 0.35,
        "criteria": {
            "labor_standards": {"weight": 0.30, "label": "Arbeitsstandards"},
            "health_safety": {"weight": 0.25, "label": "Arbeitsschutz"},
            "human_rights": {"weight": 0.25, "label": "Menschenrechte"},
            "diversity": {"weight": 0.10, "label": "Diversitaet"},
            "community": {"weight": 0.10, "label": "Gemeinwohl"},
        },
    },
    "governance": {
        "weight": 0.30,
        "criteria": {
            "compliance": {"weight": 0.35, "label": "Compliance"},
            "transparency": {"weight": 0.25, "label": "Transparenz"},
            "ethics": {"weight": 0.20, "label": "Ethik & Integritaet"},
            "risk_management": {"weight": 0.10, "label": "Risikomanagement"},
            "data_protection": {"weight": 0.10, "label": "Datenschutz"},
        },
    },
}


class SupplierSustainabilityService:
    """
    Service fuer Lieferanten-Nachhaltigkeitsbewertung.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_rating_criteria() -> Dict[str, Any]:
        """Gebe Bewertungskriterien zurueck."""
        return RATING_CRITERIA

    @staticmethod
    def calculate_scores(
        environmental_details: Dict[str, float],
        social_details: Dict[str, float],
        governance_details: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Berechne Einzel- und Gesamtscores.

        Alle Werte sollten 0-100 sein.
        """
        def calc_category_score(details: Dict[str, float], category: str) -> float:
            criteria = RATING_CRITERIA[category]["criteria"]
            total_weight = 0
            weighted_sum = 0

            for criterion_key, criterion_config in criteria.items():
                if criterion_key in details:
                    value = min(100, max(0, details[criterion_key]))  # Clamp 0-100
                    weighted_sum += value * criterion_config["weight"]
                    total_weight += criterion_config["weight"]

            if total_weight > 0:
                return weighted_sum / total_weight
            return 0

        environmental_score = calc_category_score(environmental_details, "environmental")
        social_score = calc_category_score(social_details, "social")
        governance_score = calc_category_score(governance_details, "governance")

        # Gesamtscore
        overall_score = (
            environmental_score * RATING_CRITERIA["environmental"]["weight"] +
            social_score * RATING_CRITERIA["social"]["weight"] +
            governance_score * RATING_CRITERIA["governance"]["weight"]
        )

        return {
            "environmental_score": round(environmental_score, 1),
            "social_score": round(social_score, 1),
            "governance_score": round(governance_score, 1),
            "overall_score": round(overall_score, 1),
        }

    @staticmethod
    def determine_risk_level(overall_score: float) -> str:
        """Bestimme Risikolevel basierend auf Score."""
        if overall_score >= 80:
            return "low"
        elif overall_score >= 60:
            return "medium"
        elif overall_score >= 40:
            return "high"
        else:
            return "critical"

    async def create_rating(
        self,
        company_id: UUID,
        entity_id: UUID,
        environmental_details: Dict[str, float],
        social_details: Dict[str, float],
        governance_details: Dict[str, float],
        certifications: Optional[List[str]] = None,
        improvement_areas: Optional[List[str]] = None,
        action_plan: Optional[str] = None,
        assessment_method: str = "self_assessment",
        assessed_by_id: Optional[UUID] = None,
        valid_until: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> ESGSupplierRating:
        """
        Erstelle eine neue Lieferanten-Bewertung.
        """
        # Berechne Scores
        scores = self.calculate_scores(
            environmental_details,
            social_details,
            governance_details,
        )

        # Bestimme Risikolevel
        risk_level = self.determine_risk_level(scores["overall_score"])

        # Bestimme Risikofaktoren
        risk_factors = []
        if scores["environmental_score"] < 50:
            risk_factors.append("Niedrige Umweltbewertung")
        if scores["social_score"] < 50:
            risk_factors.append("Niedrige Sozialbewertung")
        if scores["governance_score"] < 50:
            risk_factors.append("Niedrige Governance-Bewertung")

        rating = ESGSupplierRating(
            company_id=company_id,
            entity_id=entity_id,
            rating_date=date.today(),
            valid_until=valid_until,
            overall_score=scores["overall_score"],
            environmental_score=scores["environmental_score"],
            social_score=scores["social_score"],
            governance_score=scores["governance_score"],
            environmental_details=environmental_details,
            social_details=social_details,
            governance_details=governance_details,
            risk_level=risk_level,
            risk_factors=risk_factors,
            certifications=certifications or [],
            improvement_areas=improvement_areas or [],
            action_plan=action_plan,
            assessment_method=assessment_method,
            assessed_by_id=assessed_by_id,
            notes=notes,
        )

        self.db.add(rating)
        await self.db.commit()
        await self.db.refresh(rating)

        logger.info(
            "supplier_rating_created",
            rating_id=str(rating.id),
            entity_id=str(entity_id),
            overall_score=scores["overall_score"],
            risk_level=risk_level,
        )

        return rating

    async def get_ratings(
        self,
        company_id: UUID,
        entity_id: Optional[UUID] = None,
        risk_level: Optional[str] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole Lieferanten-Bewertungen.
        """
        query = select(ESGSupplierRating).where(
            ESGSupplierRating.company_id == company_id
        )

        if entity_id:
            query = query.where(ESGSupplierRating.entity_id == entity_id)
        if risk_level:
            query = query.where(ESGSupplierRating.risk_level == risk_level)
        if min_score is not None:
            query = query.where(ESGSupplierRating.overall_score >= min_score)
        if max_score is not None:
            query = query.where(ESGSupplierRating.overall_score <= max_score)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(ESGSupplierRating.rating_date.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        ratings = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "entity_id": str(r.entity_id),
                "rating_date": r.rating_date.isoformat() if r.rating_date else None,
                "valid_until": r.valid_until.isoformat() if r.valid_until else None,
                "overall_score": r.overall_score,
                "environmental_score": r.environmental_score,
                "social_score": r.social_score,
                "governance_score": r.governance_score,
                "risk_level": r.risk_level,
                "risk_factors": r.risk_factors,
                "certifications": r.certifications,
                "assessment_method": r.assessment_method,
            }
            for r in ratings
        ], total

    async def get_latest_rating(
        self,
        company_id: UUID,
        entity_id: UUID,
    ) -> Optional[dict]:
        """
        Hole neueste Bewertung fuer einen Lieferanten.
        """
        result = await self.db.execute(
            select(ESGSupplierRating).where(
                and_(
                    ESGSupplierRating.company_id == company_id,
                    ESGSupplierRating.entity_id == entity_id,
                )
            ).order_by(ESGSupplierRating.rating_date.desc())
            .limit(1)
        )
        rating = result.scalar_one_or_none()

        if not rating:
            return None

        return {
            "id": str(rating.id),
            "entity_id": str(rating.entity_id),
            "rating_date": rating.rating_date.isoformat() if rating.rating_date else None,
            "valid_until": rating.valid_until.isoformat() if rating.valid_until else None,
            "overall_score": rating.overall_score,
            "environmental_score": rating.environmental_score,
            "social_score": rating.social_score,
            "governance_score": rating.governance_score,
            "environmental_details": rating.environmental_details,
            "social_details": rating.social_details,
            "governance_details": rating.governance_details,
            "risk_level": rating.risk_level,
            "risk_factors": rating.risk_factors,
            "certifications": rating.certifications,
            "improvement_areas": rating.improvement_areas,
            "action_plan": rating.action_plan,
            "assessment_method": rating.assessment_method,
            "notes": rating.notes,
        }

    async def get_risk_summary(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Hole Risiko-Zusammenfassung aller Lieferanten.
        """
        # Hole neueste Bewertung pro Lieferant
        subquery = (
            select(
                ESGSupplierRating.entity_id,
                func.max(ESGSupplierRating.rating_date).label("latest_date")
            )
            .where(ESGSupplierRating.company_id == company_id)
            .group_by(ESGSupplierRating.entity_id)
            .subquery()
        )

        result = await self.db.execute(
            select(ESGSupplierRating).join(
                subquery,
                and_(
                    ESGSupplierRating.entity_id == subquery.c.entity_id,
                    ESGSupplierRating.rating_date == subquery.c.latest_date,
                )
            )
        )
        latest_ratings = result.scalars().all()

        # Zaehle nach Risikolevel
        by_risk = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        total_score = 0

        for rating in latest_ratings:
            level = rating.risk_level or "medium"
            by_risk[level] = by_risk.get(level, 0) + 1
            total_score += rating.overall_score or 0

        total_suppliers = len(latest_ratings)

        return {
            "total_suppliers": total_suppliers,
            "average_score": round(total_score / total_suppliers, 1) if total_suppliers > 0 else None,
            "by_risk_level": by_risk,
            "high_risk_count": by_risk["high"] + by_risk["critical"],
        }


def get_supplier_sustainability_service(db: AsyncSession) -> SupplierSustainabilityService:
    """Factory-Funktion fuer SupplierSustainabilityService."""
    return SupplierSustainabilityService(db)
