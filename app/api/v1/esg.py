"""
ESG API Endpoints (Phase 7.4).

Environmental, Social, Governance Nachhaltigkeitsberichterstattung.
"""

from datetime import date
from typing import Optional, List, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.safe_errors import safe_error_detail
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id
from app.db.models import User
from app.services.compliance.esg import (
    get_esg_service,
    get_carbon_calculator,
    get_supplier_sustainability_service,
    get_esg_report_generator,
    get_certification_tracker,
    CarbonCalculator,
    ESGReportGenerator,
    CertificationTracker,
)

router = APIRouter(prefix="/esg", tags=["ESG-Reporting"])


# === Pydantic Models ===

class CarbonEmissionRecord(BaseModel):
    """CO2-Emissions-Eintrag."""
    period_start: date
    period_end: date
    source_category: str
    consumption_value: float
    consumption_unit: str
    source_description: Optional[str] = None
    custom_factor: Optional[float] = None
    custom_factor_source: Optional[str] = None
    document_id: Optional[UUID] = None
    data_quality: str = "medium"
    calculation_method: str = "GHG Protocol"
    notes: Optional[str] = None


class SupplierRatingCreate(BaseModel):
    """Lieferanten-Bewertung erstellen."""
    entity_id: UUID
    environmental_details: Dict[str, float]
    social_details: Dict[str, float]
    governance_details: Dict[str, float]
    certifications: Optional[List[str]] = None
    improvement_areas: Optional[List[str]] = None
    action_plan: Optional[str] = None
    assessment_method: str = "self_assessment"
    valid_until: Optional[date] = None
    notes: Optional[str] = None


class CertificationCreate(BaseModel):
    """Zertifizierung hinzufuegen."""
    certification_type: str
    certification_name: str
    issue_date: date
    category: str
    certification_body: Optional[str] = None
    certificate_number: Optional[str] = None
    expiry_date: Optional[date] = None
    scope_description: Optional[str] = None
    applicable_sites: Optional[List[str]] = None
    document_id: Optional[UUID] = None
    next_audit_date: Optional[date] = None
    reminder_days_before: int = 90
    notes: Optional[str] = None


class ReportGenerate(BaseModel):
    """Bericht generieren."""
    report_type: str
    period_start: date
    period_end: date
    title: Optional[str] = None
    reporting_standard: Optional[str] = None


class GoalCreate(BaseModel):
    """ESG-Ziel erstellen."""
    title: str
    description: Optional[str] = None
    category: str
    metric_name: str
    metric_unit: Optional[str] = None
    baseline_value: Optional[float] = None
    baseline_year: Optional[int] = None
    target_value: float
    target_year: int
    sdg_goals: Optional[List[int]] = None


class GoalProgressUpdate(BaseModel):
    """Ziel-Fortschritt aktualisieren."""
    current_value: float


# === Dashboard ===

@router.get("/dashboard")
async def get_esg_dashboard(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole ESG-Dashboard-Zusammenfassung.
    """
    service = get_esg_service(db)

    return await service.get_dashboard_summary(
        company_id=(await get_user_company_id(db, user)),
        period_start=period_start,
        period_end=period_end,
    )


# === Carbon Footprint ===

@router.get("/carbon-footprint/emission-factors")
async def get_emission_factors():
    """
    Hole verfügbare Emissionsfaktoren.
    """
    return {"factors": CarbonCalculator.get_emission_factors()}


@router.post("/carbon-footprint/calculate")
async def calculate_emissions(
    source_category: str,
    consumption_value: float,
    custom_factor: Optional[float] = None,
):
    """
    Berechne CO2-Emissionen ohne Speicherung.
    """
    try:
        result = CarbonCalculator.calculate_emissions(
            source_category=source_category,
            consumption_value=consumption_value,
            custom_factor=custom_factor,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "ESG-Bericht"))


@router.post("/carbon-footprint")
async def record_carbon_emissions(
    data: CarbonEmissionRecord,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Erfasse CO2-Emissionen.
    """
    calculator = get_carbon_calculator(db)

    try:
        entry = await calculator.record_emissions(
            company_id=(await get_user_company_id(db, user)),
            period_start=data.period_start,
            period_end=data.period_end,
            source_category=data.source_category,
            consumption_value=data.consumption_value,
            consumption_unit=data.consumption_unit,
            source_description=data.source_description,
            custom_factor=data.custom_factor,
            custom_factor_source=data.custom_factor_source,
            document_id=data.document_id,
            data_quality=data.data_quality,
            calculation_method=data.calculation_method,
            recorded_by_id=user.id,
            notes=data.notes,
        )

        return {
            "success": True,
            "entry_id": str(entry.id),
            "co2_equivalent_kg": entry.co2_equivalent_kg,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "ESG-Bericht"))


@router.get("/carbon-footprint")
async def get_carbon_emissions(
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    scope: Optional[str] = Query(None),
    source_category: Optional[str] = Query(None),
    verified_only: bool = Query(False),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(100, ge=1, le=500, description="Eintraege pro Seite"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole erfasste Emissionen.
    """
    calculator = get_carbon_calculator(db)

    entries, total = await calculator.get_emissions(
        company_id=(await get_user_company_id(db, user)),
        period_start=period_start,
        period_end=period_end,
        scope=scope,
        source_category=source_category,
        verified_only=verified_only,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return {
        "items": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/carbon-footprint/summary")
async def get_carbon_summary(
    period_start: date = Query(...),
    period_end: date = Query(...),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Emissions-Zusammenfassung.
    """
    calculator = get_carbon_calculator(db)

    return await calculator.get_emissions_summary(
        company_id=(await get_user_company_id(db, user)),
        period_start=period_start,
        period_end=period_end,
    )


@router.get("/carbon-footprint/trend")
async def get_carbon_trend(
    months: int = Query(12, ge=1, le=60),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole CO2-Fussabdruck-Trend.
    """
    service = get_esg_service(db)

    return await service.get_carbon_footprint_trend(
        company_id=(await get_user_company_id(db, user)),
        months=months,
    )


# === Supplier Sustainability ===

@router.get("/supplier-ratings/criteria")
async def get_rating_criteria():
    """
    Hole Bewertungskriterien für Lieferanten.
    """
    from app.services.compliance.esg.supplier_sustainability import SupplierSustainabilityService
    return {"criteria": SupplierSustainabilityService.get_rating_criteria()}


@router.post("/supplier-ratings")
async def create_supplier_rating(
    data: SupplierRatingCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Erstelle Lieferanten-Nachhaltigkeitsbewertung.
    """
    service = get_supplier_sustainability_service(db)

    rating = await service.create_rating(
        company_id=(await get_user_company_id(db, user)),
        entity_id=data.entity_id,
        environmental_details=data.environmental_details,
        social_details=data.social_details,
        governance_details=data.governance_details,
        certifications=data.certifications,
        improvement_areas=data.improvement_areas,
        action_plan=data.action_plan,
        assessment_method=data.assessment_method,
        assessed_by_id=user.id,
        valid_until=data.valid_until,
        notes=data.notes,
    )

    return {
        "success": True,
        "rating_id": str(rating.id),
        "overall_score": rating.overall_score,
        "risk_level": rating.risk_level,
    }


@router.get("/supplier-ratings")
async def get_supplier_ratings(
    entity_id: Optional[UUID] = Query(None),
    risk_level: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Lieferanten-Bewertungen.
    """
    service = get_supplier_sustainability_service(db)

    ratings, total = await service.get_ratings(
        company_id=(await get_user_company_id(db, user)),
        entity_id=entity_id,
        risk_level=risk_level,
        min_score=min_score,
        max_score=max_score,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return {
        "items": ratings,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/supplier-ratings/summary")
async def get_supplier_risk_summary(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Risiko-Zusammenfassung aller Lieferanten.
    """
    service = get_supplier_sustainability_service(db)

    return await service.get_risk_summary(company_id=(await get_user_company_id(db, user)))


@router.get("/supplier-ratings/{entity_id}/latest")
async def get_latest_supplier_rating(
    entity_id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole neueste Bewertung für einen Lieferanten.
    """
    service = get_supplier_sustainability_service(db)

    rating = await service.get_latest_rating(
        company_id=(await get_user_company_id(db, user)),
        entity_id=entity_id,
    )

    if not rating:
        raise HTTPException(status_code=404, detail="Keine Bewertung gefunden")

    return rating


# === Certifications ===

@router.get("/certifications/types")
async def get_certification_types():
    """
    Hole bekannte Zertifizierungstypen.
    """
    return {"types": CertificationTracker.get_certification_types()}


@router.post("/certifications")
async def add_certification(
    data: CertificationCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fuege Zertifizierung hinzu.
    """
    tracker = get_certification_tracker(db)

    try:
        cert = await tracker.add_certification(
            company_id=(await get_user_company_id(db, user)),
            certification_type=data.certification_type,
            certification_name=data.certification_name,
            issue_date=data.issue_date,
            category=data.category,
            certification_body=data.certification_body,
            certificate_number=data.certificate_number,
            expiry_date=data.expiry_date,
            scope_description=data.scope_description,
            applicable_sites=data.applicable_sites,
            document_id=data.document_id,
            next_audit_date=data.next_audit_date,
            reminder_days_before=data.reminder_days_before,
            notes=data.notes,
        )

        return {
            "success": True,
            "certification_id": str(cert.id),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "ESG-Bericht"))


@router.get("/certifications")
async def get_certifications(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    include_expired: bool = Query(False),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Zertifizierungen.
    """
    tracker = get_certification_tracker(db)

    certifications, total = await tracker.get_certifications(
        company_id=(await get_user_company_id(db, user)),
        category=category,
        status=status,
        include_expired=include_expired,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return {
        "items": certifications,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/certifications/summary")
async def get_certification_summary(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Zertifizierungs-Zusammenfassung.
    """
    tracker = get_certification_tracker(db)

    return await tracker.get_certification_summary(company_id=(await get_user_company_id(db, user)))


@router.get("/certifications/expiring")
async def get_expiring_certifications(
    days: int = Query(90, ge=1, le=365),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole bald ablaufende Zertifizierungen.
    """
    tracker = get_certification_tracker(db)

    return {"items": await tracker.get_expiring_soon(
        company_id=(await get_user_company_id(db, user)),
        days=days,
    )}


@router.get("/certifications/upcoming-audits")
async def get_upcoming_audits(
    days: int = Query(60, ge=1, le=365),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole anstehende Audits.
    """
    tracker = get_certification_tracker(db)

    return {"items": await tracker.get_upcoming_audits(
        company_id=(await get_user_company_id(db, user)),
        days=days,
    )}


@router.get("/certifications/{certification_id}")
async def get_certification_detail(
    certification_id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Zertifizierungs-Details.
    """
    tracker = get_certification_tracker(db)

    detail = await tracker.get_certification_detail(
        certification_id=certification_id,
        company_id=(await get_user_company_id(db, user)),
    )

    if not detail:
        raise HTTPException(status_code=404, detail="Zertifizierung nicht gefunden")

    return detail


# === Reports ===

@router.get("/reports/templates")
async def get_report_templates():
    """
    Hole verfügbare Berichtsvorlagen.
    """
    return {"templates": ESGReportGenerator.get_report_templates()}


@router.post("/reports/generate")
async def generate_report(
    data: ReportGenerate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generiere einen ESG-Bericht.
    """
    generator = get_esg_report_generator(db)

    try:
        report = await generator.generate_report(
            company_id=(await get_user_company_id(db, user)),
            report_type=data.report_type,
            period_start=data.period_start,
            period_end=data.period_end,
            title=data.title,
            reporting_standard=data.reporting_standard,
            created_by_id=user.id,
        )

        return {
            "success": True,
            "report_id": str(report.id),
            "title": report.title,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "ESG-Bericht"))


@router.get("/reports")
async def get_reports(
    report_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole ESG-Berichte.
    """
    generator = get_esg_report_generator(db)

    reports, total = await generator.get_reports(
        company_id=(await get_user_company_id(db, user)),
        report_type=report_type,
        status=status,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return {
        "items": reports,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/reports/{report_id}")
async def get_report_detail(
    report_id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Bericht-Details.
    """
    generator = get_esg_report_generator(db)

    detail = await generator.get_report_detail(
        report_id=report_id,
        company_id=(await get_user_company_id(db, user)),
    )

    if not detail:
        raise HTTPException(status_code=404, detail="Bericht nicht gefunden")

    return detail


# === Goals ===

@router.post("/goals")
async def create_goal(
    data: GoalCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Erstelle ein ESG-Ziel.
    """
    service = get_esg_service(db)

    try:
        goal = await service.create_goal(
            company_id=(await get_user_company_id(db, user)),
            title=data.title,
            description=data.description,
            category=data.category,
            metric_name=data.metric_name,
            metric_unit=data.metric_unit,
            baseline_value=data.baseline_value,
            baseline_year=data.baseline_year,
            target_value=data.target_value,
            target_year=data.target_year,
            sdg_goals=data.sdg_goals,
        )

        return {
            "success": True,
            "goal_id": str(goal.id),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "ESG-Bericht"))


@router.get("/goals")
async def get_goals(
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole ESG-Ziele.
    """
    service = get_esg_service(db)

    goals = await service.get_goals(
        company_id=(await get_user_company_id(db, user)),
        category=category,
        active_only=active_only,
    )

    return {"items": goals}


@router.patch("/goals/{goal_id}/progress")
async def update_goal_progress(
    goal_id: UUID,
    data: GoalProgressUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aktualisiere Ziel-Fortschritt.
    """
    service = get_esg_service(db)

    try:
        goal = await service.update_goal_progress(
            goal_id=goal_id,
            company_id=(await get_user_company_id(db, user)),
            current_value=data.current_value,
        )

        return {
            "success": True,
            "progress_percentage": goal.progress_percentage,
            "on_track": goal.on_track,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "ESG-Bericht"))


@router.get("/sdg-mapping")
async def get_sdg_mapping(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole SDG-Mapping.
    """
    service = get_esg_service(db)

    mapping = await service.get_sdg_mapping(company_id=(await get_user_company_id(db, user)))

    return {"mapping": mapping}
