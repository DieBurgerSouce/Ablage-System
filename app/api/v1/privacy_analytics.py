# -*- coding: utf-8 -*-
"""
Privacy Analytics API.

Bietet differentially-private Aggregationen für sensible Daten.
Schuetzt Privacy durch mathematische Garantien (Epsilon-Differential-Privacy).

Vision 2.0 Feature: Anonymized Analytics (Phase 5)
Feinpoliert und durchdacht.
"""

import structlog
from typing import Dict, List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_user_company_id
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User, Document, InvoiceTracking, BusinessEntity
from app.services.privacy.differential_privacy_service import (
    DifferentialPrivacyService,
    DPResult,
    QueryType,
    SensitivityLevel,
    get_dp_service,
)
from app.services.privacy.privacy_budget_tracker import (
    BudgetExhaustedError,
    BudgetStatus,
    PrivacyBudgetTracker,
    get_budget_tracker,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/privacy", tags=["Privacy Analytics"])


# ============================================================================
# Request/Response Models
# ============================================================================

# Type alias for filter values
FilterValue = Union[str, int, float, bool, None, List[str], List[int]]
FilterDict = Dict[str, FilterValue]


class DPCountRequest(BaseModel):
    """Request für DP-geschuetzten COUNT."""
    table: str = Field(..., description="Tabelle (documents, invoices, entities)")
    filters: FilterDict = Field(default_factory=dict, description="Filter-Bedingungen")
    epsilon: Optional[float] = Field(None, ge=0.1, le=5.0, description="Privacy-Parameter")


class DPSumRequest(BaseModel):
    """Request für DP-geschuetzte SUM."""
    table: str = Field(..., description="Tabelle")
    column: str = Field(..., description="Spalte für SUM")
    max_contribution: float = Field(..., gt=0, description="Max Beitrag pro Zeile")
    filters: FilterDict = Field(default_factory=dict)
    epsilon: Optional[float] = Field(None, ge=0.1, le=5.0)


class DPHistogramRequest(BaseModel):
    """Request für DP-geschuetztes Histogram."""
    table: str = Field(..., description="Tabelle")
    group_by: str = Field(..., description="Gruppierungs-Spalte")
    filters: FilterDict = Field(default_factory=dict)
    epsilon: Optional[float] = Field(None, ge=0.1, le=5.0)
    suppress_below_k: bool = Field(True, description="Gruppen unter K-Schwelle unterdrücken")


class DPResultResponse(BaseModel):
    """Response für DP-geschuetzte Ergebnisse."""
    value: float
    epsilon_used: float
    mechanism: str
    confidence_interval: List[float]
    k_anonymity_satisfied: bool
    group_size: Optional[int] = None
    budget_remaining: float


class DPHistogramResponse(BaseModel):
    """Response für DP-geschuetztes Histogram."""
    categories: Dict[str, DPResultResponse]
    total_epsilon: float
    budget_remaining: float


class BudgetStatusResponse(BaseModel):
    """Response für Budget-Status."""
    company_id: str
    date: str
    total_budget: float
    consumed: float
    remaining: float
    is_exhausted: bool
    queries_count: int
    reset_at: str


class SensitivityInfoResponse(BaseModel):
    """Response für Sensitivitaets-Info."""
    level: str
    epsilon_range: List[float]
    description: str


# ============================================================================
# Allowed Tables and Columns (Whitelist)
# ============================================================================

ALLOWED_TABLES = {
    "documents": {
        "model": Document,
        "count_columns": ["id", "status", "document_type"],
        "sum_columns": [],
        "group_by_columns": ["status", "document_type", "created_at"],
    },
    "invoices": {
        "model": InvoiceTracking,
        "count_columns": ["id", "status", "dunning_level"],
        "sum_columns": ["total_amount", "outstanding_amount"],
        "group_by_columns": ["status", "dunning_level", "is_overdue"],
    },
    "entities": {
        "model": BusinessEntity,
        "count_columns": ["id", "entity_type"],
        "sum_columns": [],
        "group_by_columns": ["entity_type", "risk_category"],
    },
}


# ============================================================================
# Helper Functions
# ============================================================================

def validate_table_access(table: str, operation: str, column: Optional[str] = None) -> None:
    """Validiert Tabellen- und Spalten-Zugriff."""
    if table not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tabelle '{table}' nicht erlaubt. Erlaubt: {list(ALLOWED_TABLES.keys())}"
        )

    config = ALLOWED_TABLES[table]

    if operation == "sum" and column:
        if column not in config["sum_columns"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SUM auf Spalte '{column}' nicht erlaubt."
            )

    if operation == "group_by" and column:
        if column not in config["group_by_columns"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GROUP BY auf Spalte '{column}' nicht erlaubt."
            )


async def get_company_id(db: AsyncSession, user: User) -> UUID:
    """Ermittelt die aktive Company-ID des Users via UserCompany-Tabelle."""
    company_id = await get_user_company_id(db, user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine zugewiesene Firma."
        )
    return company_id


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/budget", response_model=BudgetStatusResponse)
async def get_privacy_budget(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BudgetStatusResponse:
    """
    Gibt aktuellen Privacy-Budget-Status zurück.

    Das Budget wird täglich um Mitternacht zurückgesetzt.
    """
    company_id = await get_company_id(db, current_user)
    tracker = await get_budget_tracker()
    status_obj = await tracker.get_status(company_id)

    return BudgetStatusResponse(
        company_id=str(status_obj.company_id),
        date=status_obj.date.isoformat(),
        total_budget=status_obj.total_budget,
        consumed=round(status_obj.consumed, 4),
        remaining=round(status_obj.remaining, 4),
        is_exhausted=status_obj.is_exhausted,
        queries_count=status_obj.queries_count,
        reset_at=status_obj.reset_at.isoformat(),
    )


@router.post("/count", response_model=DPResultResponse)
async def dp_count_query(
    request: DPCountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DPResultResponse:
    """
    Führt einen privacy-geschuetzten COUNT aus.

    Verwendet Laplace-Mechanismus mit Sensitivitaet 1.
    Gruppen unter K-Schwelle (default: 5) werden als 0 gemeldet.
    """
    company_id = await get_company_id(db, current_user)

    # Validiere Tabellen-Zugriff
    validate_table_access(request.table, "count")

    # Hole Services
    dp_service = get_dp_service()
    tracker = await get_budget_tracker()

    epsilon = request.epsilon or dp_service.config.default_epsilon

    # Prüfe Budget
    if not await tracker.check_budget_available(company_id, epsilon):
        status_obj = await tracker.get_status(company_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Privacy-Budget erschoepft. Verbleibend: {status_obj.remaining:.4f}, "
                   f"Benötigt: {epsilon:.4f}. Reset um {status_obj.reset_at.isoformat()}."
        )

    # Führe echten COUNT aus
    model = ALLOWED_TABLES[request.table]["model"]
    query = select(func.count(model.id)).where(model.company_id == company_id)

    # Wende Filter an (sichere Implementierung nötig)
    # Hier vereinfacht - in Produktion mit SQLAlchemy Filter Builder

    result = await db.execute(query)
    actual_count = result.scalar() or 0

    # Wende DP an
    dp_result = dp_service.dp_count(actual_count, epsilon)

    # Verbrauche Budget
    try:
        await tracker.consume_budget(
            company_id,
            epsilon,
            query_type="count",
            endpoint=f"/privacy/count/{request.table}"
        )
    except BudgetExhaustedError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=safe_error_detail(e, "Privacy-Budget")
        )

    remaining = await tracker.get_remaining_budget(company_id)

    # SECURITY: Keine Original-Werte loggen (Geschäftsgeheimnis/PII)
    # Nur Metadata ohne sensible Informationen
    logger.info(
        "dp_count_executed",
        table=request.table,
        epsilon=epsilon,
    )

    return DPResultResponse(
        value=dp_result.noisy_value,
        epsilon_used=dp_result.epsilon_used,
        mechanism=dp_result.mechanism.value,
        confidence_interval=list(dp_result.confidence_interval),
        k_anonymity_satisfied=dp_result.k_anonymity_satisfied,
        group_size=dp_result.group_size,
        budget_remaining=remaining
    )


@router.post("/sum", response_model=DPResultResponse)
async def dp_sum_query(
    request: DPSumRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DPResultResponse:
    """
    Führt eine privacy-geschuetzte SUM aus.

    Benötigt max_contribution um Sensitivitaet zu begrenzen.
    """
    company_id = await get_company_id(db, current_user)

    # Validiere Zugriff
    validate_table_access(request.table, "sum", request.column)

    dp_service = get_dp_service()
    tracker = await get_budget_tracker()

    epsilon = request.epsilon or dp_service.config.default_epsilon

    # Prüfe Budget
    if not await tracker.check_budget_available(company_id, epsilon):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Privacy-Budget erschoepft."
        )

    # Führe echten SUM aus
    model = ALLOWED_TABLES[request.table]["model"]
    column = getattr(model, request.column)
    query = select(func.sum(column)).where(model.company_id == company_id)

    result = await db.execute(query)
    actual_sum = float(result.scalar() or 0)

    # Wende DP an
    dp_result = dp_service.dp_sum(actual_sum, request.max_contribution, epsilon)

    # Verbrauche Budget
    await tracker.consume_budget(
        company_id, epsilon, query_type="sum",
        endpoint=f"/privacy/sum/{request.table}/{request.column}"
    )

    remaining = await tracker.get_remaining_budget(company_id)

    return DPResultResponse(
        value=dp_result.noisy_value,
        epsilon_used=dp_result.epsilon_used,
        mechanism=dp_result.mechanism.value,
        confidence_interval=list(dp_result.confidence_interval),
        k_anonymity_satisfied=dp_result.k_anonymity_satisfied,
        group_size=None,
        budget_remaining=remaining
    )


@router.get("/sensitivity-levels")
async def get_sensitivity_levels(
    current_user: User = Depends(get_current_active_user),
) -> List[SensitivityInfoResponse]:
    """
    Gibt verfügbare Sensitivitaetsstufen mit empfohlenen Epsilon-Werten zurück.
    """
    dp_service = get_dp_service()

    descriptions = {
        SensitivityLevel.LOW: "Niedrig sensible Daten (z.B. Dokumenten-Statistiken)",
        SensitivityLevel.MEDIUM: "Mittel sensible Daten (z.B. aggregierte Finanzen)",
        SensitivityLevel.HIGH: "Hoch sensible Daten (z.B. Rechnungsbetraege)",
        SensitivityLevel.CRITICAL: "Kritisch sensible Daten (z.B. Gehaelter, Gesundheit)",
    }

    return [
        SensitivityInfoResponse(
            level=level.value,
            epsilon_range=list(dp_service.config.sensitivity_epsilon_map[level]),
            description=descriptions[level]
        )
        for level in SensitivityLevel
    ]


@router.get("/estimate-noise")
async def estimate_noise_impact(
    value: float = Query(..., description="Geschätzter Wert"),
    sensitivity: float = Query(1.0, description="Query-Sensitivitaet"),
    epsilon: float = Query(1.0, ge=0.1, le=5.0, description="Privacy-Parameter"),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Union[int, float]]:
    """
    Schätzt den erwarteten Rausch-Impact vor Ausführung einer Query.

    Hilft bei der Wahl des richtigen Epsilon-Werts.
    """
    dp_service = get_dp_service()
    return dp_service.estimate_noise_impact(value, sensitivity, epsilon)


@router.post("/budget/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_privacy_budget(
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Setzt Privacy-Budget zurück (nur für Admins).
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können das Budget zurücksetzen."
        )

    company_id = await get_company_id(db, current_user)
    tracker = await get_budget_tracker()
    await tracker.reset_budget(company_id)

    logger.info(
        "privacy_budget_reset_by_admin",
        company_id=str(company_id),
        admin_user=current_user.email
    )
