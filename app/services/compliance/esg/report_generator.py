"""
ESG-Berichtsgenerator.

Erstellt Nachhaltigkeitsberichte in verschiedenen Formaten.
"""

from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.models_esg import (
    ESGReport, ESGCarbonFootprint, ESGSupplierRating,
    ESGCertification, ESGGoal, ReportStatus
)

logger = structlog.get_logger(__name__)


# Berichtsvorlagen
REPORT_TEMPLATES = {
    "annual": {
        "name": "Jaehrlicher Nachhaltigkeitsbericht",
        "sections": [
            "executive_summary",
            "carbon_footprint",
            "supplier_sustainability",
            "certifications",
            "goals_progress",
            "outlook",
        ],
    },
    "quarterly": {
        "name": "Quartalsueberblick",
        "sections": [
            "summary",
            "carbon_footprint_quarterly",
            "key_metrics",
            "actions_completed",
        ],
    },
    "csrd": {
        "name": "CSRD-konformer Bericht",
        "sections": [
            "general_information",
            "governance",
            "strategy",
            "impact_risk_opportunity",
            "metrics_targets",
        ],
    },
    "dnk": {
        "name": "Deutscher Nachhaltigkeitskodex",
        "sections": [
            "strategy", "materiality", "goals", "depth_of_value_chain",
            "responsibility", "rules_processes", "control", "incentive",
            "stakeholder", "innovation_product", "usage_natural_resources",
            "resource_management", "climate_emissions", "employment_rights",
            "equal_opportunities", "qualification", "human_rights",
            "community", "political_influence", "compliance",
        ],
    },
}


class ESGReportGenerator:
    """
    Generator fuer ESG-Berichte.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_report_templates() -> Dict[str, Dict[str, Any]]:
        """Gebe verfuegbare Berichtsvorlagen zurueck."""
        return REPORT_TEMPLATES

    async def generate_report(
        self,
        company_id: UUID,
        report_type: str,
        period_start: date,
        period_end: date,
        title: Optional[str] = None,
        reporting_standard: Optional[str] = None,
        created_by_id: Optional[UUID] = None,
    ) -> ESGReport:
        """
        Generiere einen ESG-Bericht.
        """
        if report_type not in REPORT_TEMPLATES:
            raise ValueError(f"Unbekannter Berichtstyp: {report_type}")

        template = REPORT_TEMPLATES[report_type]

        # Sammle Metriken
        metrics = await self._collect_metrics(company_id, period_start, period_end)

        # Generiere Inhalt
        content = await self._generate_content(
            company_id, period_start, period_end, template, metrics
        )

        # Erstelle Zusammenfassung
        summary = self._generate_summary(metrics, template)

        # Bestimme Geschaeftsjahr
        fiscal_year = period_end.year

        # Default-Titel
        if not title:
            title = f"{template['name']} {fiscal_year}"

        report = ESGReport(
            company_id=company_id,
            title=title,
            report_type=report_type,
            reporting_standard=reporting_standard,
            period_start=period_start,
            period_end=period_end,
            fiscal_year=fiscal_year,
            status=ReportStatus.DRAFT,
            summary=summary,
            content_json=content,
            metrics_summary=metrics,
            created_by_id=created_by_id,
        )

        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        logger.info(
            "esg_report_generated",
            report_id=str(report.id),
            company_id=str(company_id),
            report_type=report_type,
        )

        return report

    async def _collect_metrics(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """Sammle alle relevanten Metriken."""
        metrics = {}

        # CO2-Emissionen
        carbon_result = await self.db.execute(
            select(
                func.sum(ESGCarbonFootprint.co2_equivalent_kg),
                ESGCarbonFootprint.scope
            ).where(
                and_(
                    ESGCarbonFootprint.company_id == company_id,
                    ESGCarbonFootprint.period_start >= period_start,
                    ESGCarbonFootprint.period_end <= period_end,
                )
            ).group_by(ESGCarbonFootprint.scope)
        )

        emissions_by_scope = {}
        total_emissions = 0
        for row in carbon_result.fetchall():
            value = float(row[0] or 0)
            emissions_by_scope[row[1]] = value
            total_emissions += value

        metrics["total_co2_emissions_kg"] = total_emissions
        metrics["total_co2_emissions_tons"] = total_emissions / 1000
        metrics["scope_1_emissions_kg"] = emissions_by_scope.get("scope_1", 0)
        metrics["scope_2_emissions_kg"] = emissions_by_scope.get("scope_2", 0)
        metrics["scope_3_emissions_kg"] = emissions_by_scope.get("scope_3", 0)

        # Lieferanten-Scores
        supplier_result = await self.db.execute(
            select(
                func.avg(ESGSupplierRating.overall_score),
                func.count(func.distinct(ESGSupplierRating.entity_id))
            ).where(
                and_(
                    ESGSupplierRating.company_id == company_id,
                    ESGSupplierRating.rating_date >= period_start,
                )
            )
        )
        supplier_row = supplier_result.fetchone()
        metrics["supplier_avg_score"] = round(float(supplier_row[0] or 0), 1)
        metrics["suppliers_rated"] = supplier_row[1] or 0

        # Zertifizierungen
        cert_result = await self.db.execute(
            select(func.count()).where(
                and_(
                    ESGCertification.company_id == company_id,
                    ESGCertification.status == "active",
                )
            )
        )
        metrics["active_certifications"] = cert_result.scalar() or 0

        # Ziele
        goals_result = await self.db.execute(
            select(ESGGoal).where(
                and_(
                    ESGGoal.company_id == company_id,
                    ESGGoal.is_active == True,
                )
            )
        )
        goals = goals_result.scalars().all()
        metrics["total_goals"] = len(goals)
        metrics["goals_on_track"] = sum(1 for g in goals if g.on_track is True)
        metrics["goals_avg_progress"] = (
            sum(g.progress_percentage or 0 for g in goals) / len(goals)
            if goals else 0
        )

        return metrics

    async def _generate_content(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
        template: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generiere strukturierten Berichtsinhalt."""
        content = {
            "sections": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        for section in template["sections"]:
            section_data = await self._generate_section(
                section, company_id, period_start, period_end, metrics
            )
            content["sections"][section] = section_data

        return content

    async def _generate_section(
        self,
        section_name: str,
        company_id: UUID,
        period_start: date,
        period_end: date,
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generiere einzelne Berichtssektion."""
        # Basis-Struktur
        section = {
            "title": section_name.replace("_", " ").title(),
            "content": {},
        }

        if section_name in ["executive_summary", "summary"]:
            section["content"] = {
                "total_emissions_tons": metrics.get("total_co2_emissions_tons", 0),
                "supplier_score": metrics.get("supplier_avg_score", 0),
                "certifications": metrics.get("active_certifications", 0),
                "goals_progress": metrics.get("goals_avg_progress", 0),
            }

        elif section_name in ["carbon_footprint", "carbon_footprint_quarterly"]:
            section["content"] = {
                "total_kg": metrics.get("total_co2_emissions_kg", 0),
                "scope_1_kg": metrics.get("scope_1_emissions_kg", 0),
                "scope_2_kg": metrics.get("scope_2_emissions_kg", 0),
                "scope_3_kg": metrics.get("scope_3_emissions_kg", 0),
            }

        elif section_name == "supplier_sustainability":
            section["content"] = {
                "suppliers_rated": metrics.get("suppliers_rated", 0),
                "average_score": metrics.get("supplier_avg_score", 0),
            }

        elif section_name == "certifications":
            # Lade Zertifizierungen
            cert_result = await self.db.execute(
                select(ESGCertification).where(
                    and_(
                        ESGCertification.company_id == company_id,
                        ESGCertification.status == "active",
                    )
                )
            )
            certs = cert_result.scalars().all()
            section["content"] = {
                "count": len(certs),
                "certifications": [
                    {
                        "type": c.certification_type,
                        "name": c.certification_name,
                        "expiry": c.expiry_date.isoformat() if c.expiry_date else None,
                    }
                    for c in certs
                ],
            }

        elif section_name == "goals_progress":
            section["content"] = {
                "total_goals": metrics.get("total_goals", 0),
                "on_track": metrics.get("goals_on_track", 0),
                "avg_progress": metrics.get("goals_avg_progress", 0),
            }

        return section

    def _generate_summary(
        self,
        metrics: Dict[str, Any],
        template: Dict[str, Any],
    ) -> str:
        """Generiere Text-Zusammenfassung."""
        total_tons = metrics.get("total_co2_emissions_tons", 0)
        supplier_score = metrics.get("supplier_avg_score", 0)
        goals_on_track = metrics.get("goals_on_track", 0)
        total_goals = metrics.get("total_goals", 0)
        certs = metrics.get("active_certifications", 0)

        summary_parts = [
            f"Gesamtemissionen: {total_tons:.1f} Tonnen CO2e",
            f"Lieferanten-Durchschnittsbewertung: {supplier_score:.1f}/100",
            f"Aktive Zertifizierungen: {certs}",
        ]

        if total_goals > 0:
            summary_parts.append(f"Ziele auf Kurs: {goals_on_track}/{total_goals}")

        return " | ".join(summary_parts)

    async def get_reports(
        self,
        company_id: UUID,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole vorhandene Berichte.
        """
        query = select(ESGReport).where(ESGReport.company_id == company_id)

        if report_type:
            query = query.where(ESGReport.report_type == report_type)
        if status:
            query = query.where(ESGReport.status == status)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(ESGReport.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        reports = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "title": r.title,
                "report_type": r.report_type,
                "reporting_standard": r.reporting_standard,
                "period_start": r.period_start.isoformat() if r.period_start else None,
                "period_end": r.period_end.isoformat() if r.period_end else None,
                "fiscal_year": r.fiscal_year,
                "status": r.status,
                "summary": r.summary,
                "metrics_summary": r.metrics_summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in reports
        ], total

    async def get_report_detail(
        self,
        report_id: UUID,
        company_id: UUID,
    ) -> Optional[dict]:
        """Hole Bericht-Details."""
        result = await self.db.execute(
            select(ESGReport).where(
                and_(
                    ESGReport.id == report_id,
                    ESGReport.company_id == company_id,
                )
            )
        )
        report = result.scalar_one_or_none()

        if not report:
            return None

        return {
            "id": str(report.id),
            "title": report.title,
            "report_type": report.report_type,
            "reporting_standard": report.reporting_standard,
            "period_start": report.period_start.isoformat() if report.period_start else None,
            "period_end": report.period_end.isoformat() if report.period_end else None,
            "fiscal_year": report.fiscal_year,
            "status": report.status,
            "summary": report.summary,
            "content": report.content_json,
            "metrics_summary": report.metrics_summary,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "approved_at": report.approved_at.isoformat() if report.approved_at else None,
            "published_at": report.published_at.isoformat() if report.published_at else None,
            "notes": report.notes,
        }

    async def update_report_status(
        self,
        report_id: UUID,
        company_id: UUID,
        new_status: str,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """Aktualisiere Berichtsstatus."""
        result = await self.db.execute(
            select(ESGReport).where(
                and_(
                    ESGReport.id == report_id,
                    ESGReport.company_id == company_id,
                )
            )
        )
        report = result.scalar_one_or_none()

        if not report:
            return False

        # Validiere Status-Uebergang
        valid_statuses = [s.value for s in ReportStatus]
        if new_status not in valid_statuses:
            raise ValueError(f"Ungueltiger Status: {new_status}")

        report.status = new_status

        if new_status == ReportStatus.APPROVED:
            report.approved_at = datetime.now(timezone.utc)
            report.approved_by_id = user_id
        elif new_status == ReportStatus.PUBLISHED:
            report.published_at = datetime.now(timezone.utc)

        await self.db.commit()

        return True


def get_esg_report_generator(db: AsyncSession) -> ESGReportGenerator:
    """Factory-Funktion fuer ESGReportGenerator."""
    return ESGReportGenerator(db)
