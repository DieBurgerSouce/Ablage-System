# -*- coding: utf-8 -*-
"""Workflow Analytics API Endpoints.

Enterprise Workflow Analytics und SLA Monitoring mit:
- SLA Status und Verletzungen
- Bottleneck-Analyse
- Throughput-Metriken
- Parallele Genehmigungen

15 Endpoints:
- SLA (5): Status, Breaches, Define, Metrics, Start
- Analytics (4): Bottlenecks, Throughput, User Productivity, Durations
- Parallel Approvals (6): Create, Vote, Status, List, Cancel, Workflow Approvals
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.api.v1.workflows import get_user_company_id
from app.core.safe_errors import safe_error_detail
from app.db.models import User
from app.services.bpmn.sla_service import get_sla_service
from app.services.bpmn.approval_service import (
    get_parallel_approval_service,
    ConsensusType,
    ApprovalDecision,
)
from app.services.bpmn.workflow_analytics_service import get_workflow_analytics_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflow-analytics"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SLADefinitionCreate(BaseModel):
    """Schema für SLA-Definition."""

    workflow_type: str = Field(..., min_length=1, max_length=100)
    max_duration_hours: int = Field(..., ge=1, le=720)
    description: Optional[str] = None
    escalation_user_id: Optional[UUID] = None


class SLADefinitionResponse(BaseModel):
    """Schema für SLA-Definition-Antwort."""

    workflow_type: str
    max_duration_hours: int
    description: Optional[str] = None
    escalation_user_id: Optional[str] = None
    is_default: bool = False


class SLAStatusResponse(BaseModel):
    """Schema für SLA-Status-Antwort."""

    instance_id: str
    has_sla: bool
    status: Optional[str] = None
    start_time: Optional[str] = None
    deadline: Optional[str] = None
    max_duration_hours: Optional[int] = None
    elapsed_hours: Optional[float] = None
    elapsed_percent: Optional[float] = None
    remaining_hours: Optional[float] = None
    completed: bool = False
    on_time: Optional[bool] = None
    end_time: Optional[str] = None
    alerts_sent: List[str] = []
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SLABreachResponse(BaseModel):
    """Schema für SLA-Verletzung."""

    instance_id: str
    business_key: Optional[str] = None
    workflow_key: Optional[str] = None
    workflow_name: Optional[str] = None
    start_time: str
    deadline: str
    end_time: str
    max_duration_hours: int
    actual_duration_hours: float
    breach_by_hours: float


class SLAMetricsResponse(BaseModel):
    """Schema für SLA-Metriken."""

    time_range_days: int
    total_workflows: int
    on_time: int
    breached: int
    compliance_rate: float
    avg_duration_hours: float
    by_workflow: JSONDict


class BottleneckAnalysisResponse(BaseModel):
    """Schema für Bottleneck-Analyse."""

    time_range_days: int
    slow_tasks: List[JSONDict]
    blocked_tasks: List[JSONDict]
    escalation_hotspots: List[JSONDict]
    recommendations: List[str]


class ThroughputResponse(BaseModel):
    """Schema für Durchsatz-Metriken."""

    time_range_days: int
    group_by: str
    data: List[JSONDict]
    summary: JSONDict


class UserProductivityResponse(BaseModel):
    """Schema für User-Produktivitaet."""

    user_id: str
    time_range_days: int
    metrics: JSONDict
    performance_score: JSONDict
    score_breakdown: JSONDict


class DurationResponse(BaseModel):
    """Schema für Dauern pro Workflow-Typ."""

    time_range_days: int
    by_workflow_type: List[JSONDict]
    summary: JSONDict


class ParallelApprovalCreate(BaseModel):
    """Schema für parallele Genehmigung erstellen."""

    approvers: List[UUID] = Field(..., min_length=1)
    consensus_type: str = Field(default="all", pattern="^(all|majority|any|unanimous|quorum)$")
    quorum_count: Optional[int] = Field(None, ge=1)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    element_id: str = Field(default="parallel_approval", max_length=100)


class VoteRequest(BaseModel):
    """Schema für Abstimmung."""

    decision: str = Field(..., pattern="^(approved|rejected|abstained)$")
    comment: Optional[str] = Field(None, max_length=1000)


class ParallelApprovalResponse(BaseModel):
    """Schema für parallele Genehmigung."""

    approval_id: str
    instance_id: str
    title: str
    description: Optional[str] = None
    consensus_type: str
    status: str
    created_at: Optional[str] = None
    due_date: Optional[str] = None
    final_decision: Optional[str] = None
    votes: Optional[JSONDict] = None
    votes_summary: Dict[str, int]


class VoteResponse(BaseModel):
    """Schema für Abstimmungsergebnis."""

    approval_id: str
    vote_recorded: bool
    decision: str
    consensus_reached: bool
    final_decision: Optional[str] = None
    status: str
    votes_summary: Dict[str, int]


# =============================================================================
# SLA Endpoints (5)
# =============================================================================

@router.get(
    "/sla/status",
    response_model=List[SLAStatusResponse],
    summary="SLA-Status aller aktiven Workflows",
)
async def get_all_sla_status(
    workflow_type: Optional[str] = Query(None, description="Filter nach Workflow-Typ"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SLAStatusResponse]:
    """Gibt SLA-Status aller aktiven Workflows zurück."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    from sqlalchemy import select, and_
    from app.db.bpmn_models.bpmn import ProcessInstance, ProcessDefinition, ProcessStatus

    sla_service = get_sla_service(db)

    # Laufende Instanzen laden
    conditions = [
        ProcessInstance.company_id == company_id,
        ProcessInstance.status == ProcessStatus.RUNNING,
    ]

    if workflow_type:
        query = (
            select(ProcessInstance)
            .join(ProcessDefinition)
            .where(
                and_(
                    *conditions,
                    ProcessDefinition.key == workflow_type,
                )
            )
            .limit(limit)
        )
    else:
        query = (
            select(ProcessInstance)
            .where(and_(*conditions))
            .limit(limit)
        )

    result = await db.execute(query)
    instances = list(result.scalars().all())

    statuses = []
    for instance in instances:
        try:
            sla_status = await sla_service.check_sla_status(
                instance.id,
                company_id,
            )
            statuses.append(SLAStatusResponse(**sla_status))
        except Exception:
            continue

    return statuses


@router.get(
    "/sla/breaches",
    response_model=List[SLABreachResponse],
    summary="SLA-Verletzungen auflisten",
)
async def get_sla_breaches(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SLABreachResponse]:
    """Listet alle SLA-Verletzungen im Zeitraum auf."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    sla_service = get_sla_service(db)

    breaches = await sla_service.get_sla_breaches(
        company_id=company_id,
        time_range_days=days,
        limit=limit,
    )

    return [SLABreachResponse(**b) for b in breaches]


@router.post(
    "/sla/define",
    response_model=SLADefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="SLA definieren",
)
async def define_sla(
    data: SLADefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SLADefinitionResponse:
    """Definiert SLA für einen Workflow-Typ."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    sla_service = get_sla_service(db)

    try:
        result = await sla_service.define_sla(
            workflow_type=data.workflow_type,
            max_duration_hours=data.max_duration_hours,
            company_id=company_id,
            description=data.description,
            escalation_user_id=data.escalation_user_id,
        )
        await db.commit()
        return SLADefinitionResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/sla/metrics",
    response_model=SLAMetricsResponse,
    summary="SLA-Metriken abrufen",
)
async def get_sla_metrics(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SLAMetricsResponse:
    """Gibt SLA-Performance-Metriken zurück."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    sla_service = get_sla_service(db)

    metrics = await sla_service.calculate_sla_metrics(
        company_id=company_id,
        time_range_days=days,
    )

    return SLAMetricsResponse(**metrics)


@router.post(
    "/{instance_id}/sla/start",
    response_model=SLAStatusResponse,
    summary="SLA-Tracking starten",
)
async def start_sla_tracking(
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SLAStatusResponse:
    """Startet SLA-Tracking für eine Workflow-Instanz."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    sla_service = get_sla_service(db)

    try:
        result = await sla_service.start_sla_tracking(
            workflow_instance_id=instance_id,
            company_id=company_id,
        )
        await db.commit()
        return SLAStatusResponse(**result, has_sla=True)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# Analytics Endpoints (4)
# =============================================================================

@router.get(
    "/analytics/bottlenecks",
    response_model=BottleneckAnalysisResponse,
    summary="Bottleneck-Analyse",
)
async def get_bottleneck_analysis(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BottleneckAnalysisResponse:
    """Identifiziert Workflow-Engpaesse."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    analytics_service = get_workflow_analytics_service(db)

    result = await analytics_service.get_bottleneck_analysis(
        company_id=company_id,
        time_range_days=days,
        limit=limit,
    )

    return BottleneckAnalysisResponse(**result)


@router.get(
    "/analytics/throughput",
    response_model=ThroughputResponse,
    summary="Durchsatz-Metriken",
)
async def get_throughput_metrics(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    group_by: str = Query("day", pattern="^(day|week|month)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThroughputResponse:
    """Gibt Durchsatz-Metriken zurück."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    analytics_service = get_workflow_analytics_service(db)

    result = await analytics_service.get_throughput_metrics(
        company_id=company_id,
        time_range_days=days,
        group_by=group_by,
    )

    return ThroughputResponse(**result)


@router.get(
    "/analytics/user-productivity/{user_id}",
    response_model=UserProductivityResponse,
    summary="User-Produktivitaet",
)
async def get_user_productivity(
    user_id: UUID,
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProductivityResponse:
    """Gibt Produktivitaetsmetriken für einen User zurück."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    analytics_service = get_workflow_analytics_service(db)

    result = await analytics_service.get_user_productivity(
        user_id=user_id,
        company_id=company_id,
        time_range_days=days,
    )

    return UserProductivityResponse(**result)


@router.get(
    "/analytics/durations",
    response_model=DurationResponse,
    summary="Durchschnittliche Dauern",
)
async def get_average_durations(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DurationResponse:
    """Gibt durchschnittliche Dauern pro Workflow-Typ zurück."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    analytics_service = get_workflow_analytics_service(db)

    result = await analytics_service.get_average_duration_by_type(
        company_id=company_id,
        time_range_days=days,
    )

    return DurationResponse(**result)


# =============================================================================
# Parallel Approval Endpoints (6)
# =============================================================================

@router.post(
    "/{instance_id}/approvals",
    response_model=ParallelApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Parallele Genehmigung erstellen",
)
async def create_parallel_approval(
    instance_id: UUID,
    data: ParallelApprovalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParallelApprovalResponse:
    """Erstellt eine parallele Genehmigung für einen Workflow."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    approval_service = get_parallel_approval_service(db)

    try:
        result = await approval_service.create_parallel_approval(
            workflow_instance_id=instance_id,
            approvers=data.approvers,
            company_id=company_id,
            consensus_type=ConsensusType(data.consensus_type),
            quorum_count=data.quorum_count,
            title=data.title,
            description=data.description,
            due_date=data.due_date,
            element_id=data.element_id,
        )
        await db.commit()

        return ParallelApprovalResponse(
            votes_summary={"total": len(data.approvers), "pending": len(data.approvers)},
            **result,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/approvals/{approval_id}/vote",
    response_model=VoteResponse,
    summary="Abstimmung abgeben",
)
async def record_vote(
    approval_id: str,
    data: VoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VoteResponse:
    """Zeichnet die Abstimmung eines Genehmigers auf."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    approval_service = get_parallel_approval_service(db)

    try:
        result = await approval_service.record_approval_vote(
            approval_id=approval_id,
            approver_id=current_user.id,
            decision=ApprovalDecision(data.decision),
            company_id=company_id,
            comment=data.comment,
        )
        await db.commit()

        return VoteResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/approvals/{approval_id}",
    response_model=ParallelApprovalResponse,
    summary="Genehmigung abrufen",
)
async def get_approval_status(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParallelApprovalResponse:
    """Gibt den Status einer parallelen Genehmigung zurück."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    approval_service = get_parallel_approval_service(db)

    try:
        result = await approval_service.get_approval_status(
            approval_id=approval_id,
            company_id=company_id,
        )

        return ParallelApprovalResponse(
            approval_id=result["approval_id"],
            instance_id=result["instance_id"],
            title=result["title"],
            description=result.get("description"),
            consensus_type=result["consensus_type"],
            status=result["status"],
            created_at=result.get("created_at"),
            due_date=result.get("due_date"),
            final_decision=result.get("final_decision"),
            votes=result.get("votes"),
            votes_summary=result["votes_summary"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/approvals",
    response_model=List[ParallelApprovalResponse],
    summary="Meine ausstehenden Genehmigungen",
)
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ParallelApprovalResponse]:
    """Listet alle ausstehenden Genehmigungen für den aktuellen User."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    approval_service = get_parallel_approval_service(db)

    results = await approval_service.list_pending_approvals(
        user_id=current_user.id,
        company_id=company_id,
    )

    return [
        ParallelApprovalResponse(
            approval_id=r["approval_id"],
            instance_id=r["instance_id"],
            title=r["title"],
            description=r.get("description"),
            consensus_type=r["consensus_type"],
            status="pending",
            created_at=r.get("created_at"),
            due_date=r.get("due_date"),
            votes_summary=r["votes_summary"],
        )
        for r in results
    ]


@router.delete(
    "/approvals/{approval_id}",
    response_model=JSONDict,
    summary="Genehmigung abbrechen",
)
async def cancel_approval(
    approval_id: str,
    reason: Optional[str] = Query(None, description="Abbruchgrund"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Bricht eine parallele Genehmigung ab."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    approval_service = get_parallel_approval_service(db)

    try:
        result = await approval_service.cancel_approval(
            approval_id=approval_id,
            company_id=company_id,
            reason=reason,
            cancelled_by_id=current_user.id,
        )
        await db.commit()

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{instance_id}/approvals",
    response_model=List[ParallelApprovalResponse],
    summary="Workflow-Genehmigungen auflisten",
)
async def list_workflow_approvals(
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ParallelApprovalResponse]:
    """Listet alle parallelen Genehmigungen einer Workflow-Instanz."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    approval_service = get_parallel_approval_service(db)

    try:
        results = await approval_service.list_workflow_approvals(
            workflow_instance_id=instance_id,
            company_id=company_id,
        )

        return [
            ParallelApprovalResponse(
                approval_id=r["approval_id"],
                instance_id=str(instance_id),
                title=r["title"],
                consensus_type=r["consensus_type"],
                status=r["status"],
                created_at=r.get("created_at"),
                final_decision=r.get("final_decision"),
                votes_summary=r["votes_summary"],
            )
            for r in results
        ]

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
