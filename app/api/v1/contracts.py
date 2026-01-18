"""
Contract Management API Endpoints

Endpoints for managing business contracts including:
- CRUD operations for contracts
- Deadline tracking and alerts
- Renewal options management
- Contract analytics
"""

from datetime import date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.api.schemas.contract import (
    # Contract schemas
    ContractCreate,
    ContractUpdate,
    ContractResponse,
    ContractDetailResponse,
    ContractListResponse,
    ContractListParams,
    # Milestone schemas
    MilestoneCreate,
    MilestoneUpdate,
    ContractMilestoneResponse,
    # Renewal schemas
    RenewalOptionCreate,
    RenewalOptionDecision,
    ContractRenewalOptionResponse,
    # Amendment schemas
    AmendmentCreate,
    AmendmentUpdate,
    ContractAmendmentResponse,
    # Other schemas
    DeadlineAlertResponse,
    DeadlineListResponse,
    ContractSummaryResponse,
    ContractTimelineResponse,
    ContractTimelineEventResponse,
    # Enums
    ContractStatus,
    ContractType,
    MilestoneType,
    AmendmentStatus,
)
from app.services.contract_service import (
    get_contract_service,
    ContractService,
)
from app.db.models import (
    BusinessContract,
    ContractMilestone,
    ContractRenewalOption,
    ContractAmendment,
    ContractType as DBContractType,
    ContractStatus as DBContractStatus,
    MilestoneType as DBMilestoneType,
    AmendmentStatus as DBAmendmentStatus,
    RenewalOptionStatus,
    User,
    Company,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/contracts", tags=["Contracts"])


# =============================================================================
# Helper Functions
# =============================================================================

def _contract_to_response(contract: BusinessContract) -> ContractResponse:
    """Convert a contract model to a response schema."""
    party_a = None
    if contract.party_a:
        party_a = {
            "id": contract.party_a.id,
            "name": contract.party_a.name,
            "entity_type": contract.party_a.entity_type.value if contract.party_a.entity_type else None,
        }

    party_b = None
    if contract.party_b:
        party_b = {
            "id": contract.party_b.id,
            "name": contract.party_b.name,
            "entity_type": contract.party_b.entity_type.value if contract.party_b.entity_type else None,
        }

    return ContractResponse(
        id=contract.id,
        company_id=contract.company_id,
        contract_number=contract.contract_number,
        title=contract.title,
        contract_type=ContractType(contract.contract_type.value),
        description=contract.description,
        status=ContractStatus(contract.status.value),
        party_a_id=contract.party_a_id,
        party_a_name=contract.party_a_name,
        party_a_signatory=contract.party_a_signatory,
        party_a=party_a,
        party_b_id=contract.party_b_id,
        party_b_name=contract.party_b_name,
        party_b_signatory=contract.party_b_signatory,
        party_b=party_b,
        contract_date=contract.contract_date,
        start_date=contract.start_date,
        end_date=contract.end_date,
        duration_months=contract.duration_months,
        notice_period_days=contract.notice_period_days,
        notice_deadline=contract.notice_deadline,
        auto_renewal=contract.auto_renewal,
        renewal_period_months=contract.renewal_period_months,
        max_renewals=contract.max_renewals,
        current_renewal_count=contract.current_renewal_count,
        total_value=contract.total_value,
        monthly_value=contract.monthly_value,
        currency=contract.currency,
        payment_terms=contract.payment_terms,
        price_adjustment_clause=contract.price_adjustment_clause,
        price_adjustment_index=contract.price_adjustment_index,
        price_adjustment_date=contract.price_adjustment_date,
        price_adjustment_percent=contract.price_adjustment_percent,
        governing_law=contract.governing_law,
        jurisdiction=contract.jurisdiction,
        arbitration_clause=contract.arbitration_clause,
        document_id=contract.document_id,
        signed_date=contract.signed_date,
        terminated_date=contract.terminated_date,
        termination_reason=contract.termination_reason,
        reminder_days=contract.reminder_days or [90, 60, 30, 14, 7],
        notification_emails=contract.notification_emails or [],
        last_reminder_sent=contract.last_reminder_sent,
        tags=contract.tags or [],
        metadata=contract.metadata or {},
        key_contacts=contract.key_contacts or [],
        notes=contract.notes,
        days_until_end=contract.days_until_end,
        days_until_notice_deadline=contract.days_until_notice_deadline,
        is_expiring_soon=contract.is_expiring_soon,
        is_notice_deadline_critical=contract.is_notice_deadline_critical,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        created_by_id=contract.created_by_id,
    )


def _milestone_to_response(milestone: ContractMilestone) -> ContractMilestoneResponse:
    """Convert a milestone model to a response schema."""
    return ContractMilestoneResponse(
        id=milestone.id,
        contract_id=milestone.contract_id,
        milestone_type=MilestoneType(milestone.milestone_type.value),
        title=milestone.title,
        description=milestone.description,
        scheduled_date=milestone.scheduled_date,
        is_completed=milestone.is_completed,
        completed_date=milestone.completed_date,
        completion_notes=milestone.completion_notes,
        reminder_days_before=milestone.reminder_days_before or [14, 7, 1],
        days_until_due=milestone.days_until_due,
        is_overdue=milestone.is_overdue,
        created_at=milestone.created_at,
        updated_at=milestone.updated_at,
    )


def _renewal_option_to_response(option: ContractRenewalOption) -> ContractRenewalOptionResponse:
    """Convert a renewal option model to a response schema."""
    return ContractRenewalOptionResponse(
        id=option.id,
        contract_id=option.contract_id,
        option_number=option.option_number,
        renewal_duration_months=option.renewal_duration_months,
        price_adjustment_type=option.price_adjustment_type,
        price_adjustment_value=option.price_adjustment_value,
        new_monthly_value=option.new_monthly_value,
        exercise_deadline=option.exercise_deadline,
        renewal_start_date=option.renewal_start_date,
        notice_required_days=option.notice_required_days,
        status=option.status.value,
        exercised_date=option.exercised_date,
        exercised_by_id=option.exercised_by_id,
        decision_notes=option.decision_notes,
        days_until_deadline=option.days_until_deadline,
        is_deadline_critical=option.is_deadline_critical,
        created_at=option.created_at,
        updated_at=option.updated_at,
    )


def _amendment_to_response(amendment: ContractAmendment) -> ContractAmendmentResponse:
    """Convert an amendment model to a response schema."""
    return ContractAmendmentResponse(
        id=amendment.id,
        contract_id=amendment.contract_id,
        amendment_number=amendment.amendment_number,
        title=amendment.title,
        amendment_date=amendment.amendment_date,
        effective_date=amendment.effective_date,
        changes_summary=amendment.changes_summary,
        affected_clauses=amendment.affected_clauses or [],
        changes_detail=amendment.changes_detail or {},
        value_change=amendment.value_change,
        new_total_value=amendment.new_total_value,
        document_id=amendment.document_id,
        status=AmendmentStatus(amendment.status.value),
        approved_by_id=amendment.approved_by_id,
        approved_date=amendment.approved_date,
        created_at=amendment.created_at,
        updated_at=amendment.updated_at,
    )


# =============================================================================
# Contract CRUD Endpoints
# =============================================================================

@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractResponse:
    """
    Erstelle einen neuen Vertrag.

    Erstellt einen Geschaeftsvertrag mit:
    - Automatischer Berechnung der Kuendigungsfrist
    - Standard-Meilensteinen
    - Verlaengerungsoptionen bei automatischer Verlaengerung
    """
    service = get_contract_service()

    contract = await service.create_contract(
        db=db,
        company_id=company.company_id,
        user_id=current_user.id,
        contract_number=data.contract_number,
        title=data.title,
        contract_type=DBContractType(data.contract_type.value),
        start_date=data.start_date,
        end_date=data.end_date,
        duration_months=data.duration_months,
        notice_period_days=data.notice_period_days,
        auto_renewal=data.auto_renewal,
        renewal_period_months=data.renewal_period_months,
        max_renewals=data.max_renewals,
        total_value=data.total_value,
        monthly_value=data.monthly_value,
        party_a_id=data.party_a_id,
        party_a_name=data.party_a_name,
        party_a_signatory=data.party_a_signatory,
        party_b_id=data.party_b_id,
        party_b_name=data.party_b_name,
        party_b_signatory=data.party_b_signatory,
        document_id=data.document_id,
        description=data.description,
        contract_date=data.contract_date,
        currency=data.currency,
        payment_terms=data.payment_terms,
        price_adjustment_clause=data.price_adjustment_clause,
        price_adjustment_index=data.price_adjustment_index,
        price_adjustment_date=data.price_adjustment_date,
        price_adjustment_percent=data.price_adjustment_percent,
        governing_law=data.governing_law,
        jurisdiction=data.jurisdiction,
        arbitration_clause=data.arbitration_clause,
        reminder_days=data.reminder_days,
        notification_emails=data.notification_emails,
        tags=data.tags,
        metadata=data.metadata,
        key_contacts=data.key_contacts,
        notes=data.notes,
    )

    return _contract_to_response(contract)


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    status: Optional[ContractStatus] = Query(None, description="Filter nach Status"),
    contract_type: Optional[ContractType] = Query(None, description="Filter nach Vertragsart"),
    party_id: Optional[UUID] = Query(None, description="Filter nach Vertragspartner"),
    expiring_within_days: Optional[int] = Query(None, ge=1, le=365, description="Ablaufende Vertraege innerhalb X Tagen"),
    search: Optional[str] = Query(None, max_length=200, description="Suche in Vertragsnr, Titel, Parteien"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    order_by: str = Query("end_date", description="Sortierfeld"),
    order_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractListResponse:
    """
    Liste aller Vertraege mit Filteroptionen.

    Filter:
    - status: Vertragsstatus
    - contract_type: Vertragsart
    - party_id: Vertragspartner-ID
    - expiring_within_days: Nur ablaufende Vertraege
    - search: Volltextsuche
    """
    service = get_contract_service()

    contracts, total = await service.list_contracts(
        db=db,
        company_id=company.company_id,
        status=DBContractStatus(status.value) if status else None,
        contract_type=DBContractType(contract_type.value) if contract_type else None,
        party_id=party_id,
        expiring_within_days=expiring_within_days,
        search=search,
        offset=offset,
        limit=limit,
        order_by=order_by,
        order_dir=order_dir,
    )

    return ContractListResponse(
        items=[_contract_to_response(c) for c in contracts],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/summary", response_model=ContractSummaryResponse)
async def get_contract_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractSummaryResponse:
    """
    Portfolio-Zusammenfassung aller Vertraege.

    Liefert:
    - Gesamtzahl Vertraege
    - Aktive Vertraege
    - Bald ablaufende Vertraege (90 Tage)
    - Kritische Fristen (30 Tage)
    - Gesamtwert und monatliche Verpflichtungen
    """
    service = get_contract_service()
    summary = await service.get_portfolio_summary(db=db, company_id=company.company_id)

    return ContractSummaryResponse(
        total_contracts=summary.total_contracts,
        active_contracts=summary.active_contracts,
        expiring_soon=summary.expiring_soon,
        critical_deadlines=summary.critical_deadlines,
        total_value=summary.total_value,
        monthly_commitment=summary.monthly_commitment,
    )


@router.get("/deadlines", response_model=DeadlineListResponse)
async def get_upcoming_deadlines(
    days_ahead: int = Query(90, ge=1, le=365, description="Tage voraus"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DeadlineListResponse:
    """
    Alle anstehenden Fristen und Deadlines.

    Liefert:
    - Kuendigungsfristen
    - Vertragsenden
    - Verlaengerungsfristen

    Sortiert nach Dringlichkeit.
    """
    service = get_contract_service()
    alerts = await service.get_upcoming_deadlines(
        db=db,
        company_id=company.company_id,
        days_ahead=days_ahead,
    )

    return DeadlineListResponse(
        items=[
            DeadlineAlertResponse(
                contract_id=a.contract_id,
                contract_number=a.contract_number,
                contract_title=a.contract_title,
                deadline_type=a.deadline_type,
                deadline_date=a.deadline_date,
                days_remaining=a.days_remaining,
                urgency=a.urgency,
                party_name=a.party_name,
            )
            for a in alerts
        ],
        total=len(alerts),
    )


@router.get("/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractDetailResponse:
    """
    Vertrag mit allen Details abrufen.

    Enthaelt:
    - Vertragsdaten
    - Meilensteine
    - Verlaengerungsoptionen
    - Aenderungen/Nachtraege
    """
    service = get_contract_service()
    contract = await service.get_contract(
        db=db,
        contract_id=contract_id,
        company_id=company.company_id,
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    base_response = _contract_to_response(contract)

    return ContractDetailResponse(
        **base_response.model_dump(),
        milestones=[_milestone_to_response(m) for m in contract.milestones],
        renewal_options=[_renewal_option_to_response(o) for o in contract.renewal_options],
        amendments=[_amendment_to_response(a) for a in getattr(contract, 'amendments', [])],
    )


@router.get("/{contract_id}/timeline", response_model=ContractTimelineResponse)
async def get_contract_timeline(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractTimelineResponse:
    """
    Vertragstimeline mit allen Ereignissen.

    Zeigt chronologisch:
    - Vertragsbeginn
    - Meilensteine
    - Kuendigungsfristen
    - Verlaengerungsoptionen
    - Vertragsende
    """
    service = get_contract_service()

    # First get the contract to check permissions and get contract_number
    contract = await service.get_contract(
        db=db,
        contract_id=contract_id,
        company_id=company.company_id,
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    events = await service.get_contract_timeline(
        db=db,
        contract_id=contract_id,
        company_id=company.company_id,
    )

    return ContractTimelineResponse(
        contract_id=contract_id,
        contract_number=contract.contract_number,
        events=[
            ContractTimelineEventResponse(
                event_date=e.event_date,
                event_type=e.event_type,
                title=e.title,
                description=e.description,
                is_completed=e.is_completed,
                contract_id=e.contract_id,
            )
            for e in events
        ],
    )


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: UUID,
    data: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractResponse:
    """
    Vertrag aktualisieren.

    Aktualisiert nur die angegebenen Felder.
    Kuendigungsfrist wird automatisch neu berechnet.
    """
    service = get_contract_service()

    # Prepare updates dict
    updates = data.model_dump(exclude_unset=True)

    # Convert enums
    if "contract_type" in updates and updates["contract_type"]:
        updates["contract_type"] = DBContractType(updates["contract_type"].value)
    if "status" in updates and updates["status"]:
        updates["status"] = DBContractStatus(updates["status"].value)

    contract = await service.update_contract(
        db=db,
        contract_id=contract_id,
        company_id=company.company_id,
        **updates,
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    return _contract_to_response(contract)


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> None:
    """
    Vertrag loeschen (Soft-Delete).

    Setzt Status auf TERMINATED statt physischem Loeschen.
    """
    service = get_contract_service()

    success = await service.delete_contract(
        db=db,
        contract_id=contract_id,
        company_id=company.company_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )


# =============================================================================
# Milestone Endpoints
# =============================================================================

@router.post("/{contract_id}/milestones", response_model=ContractMilestoneResponse, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    contract_id: UUID,
    data: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractMilestoneResponse:
    """
    Meilenstein zu einem Vertrag hinzufuegen.
    """
    # Verify contract exists
    service = get_contract_service()
    contract = await service.get_contract(db, contract_id, company.company_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    milestone = ContractMilestone(
        contract_id=contract_id,
        milestone_type=DBMilestoneType(data.milestone_type.value),
        title=data.title,
        description=data.description,
        scheduled_date=data.scheduled_date,
        reminder_days_before=data.reminder_days_before,
    )

    db.add(milestone)
    await db.commit()
    await db.refresh(milestone)

    return _milestone_to_response(milestone)


@router.patch("/{contract_id}/milestones/{milestone_id}", response_model=ContractMilestoneResponse)
async def update_milestone(
    contract_id: UUID,
    milestone_id: UUID,
    data: MilestoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractMilestoneResponse:
    """
    Meilenstein aktualisieren.
    """
    from sqlalchemy import select, and_

    # Verify contract exists
    service = get_contract_service()
    contract = await service.get_contract(db, contract_id, company.company_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # Get milestone
    result = await db.execute(
        select(ContractMilestone).where(
            and_(
                ContractMilestone.id == milestone_id,
                ContractMilestone.contract_id == contract_id,
            )
        )
    )
    milestone = result.scalar_one_or_none()

    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meilenstein nicht gefunden",
        )

    # Update fields
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if hasattr(milestone, key) and value is not None:
            setattr(milestone, key, value)

    await db.commit()
    await db.refresh(milestone)

    return _milestone_to_response(milestone)


@router.delete("/{contract_id}/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    contract_id: UUID,
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> None:
    """
    Meilenstein loeschen.
    """
    from sqlalchemy import select, and_

    # Verify contract exists
    service = get_contract_service()
    contract = await service.get_contract(db, contract_id, company.company_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # Get milestone
    result = await db.execute(
        select(ContractMilestone).where(
            and_(
                ContractMilestone.id == milestone_id,
                ContractMilestone.contract_id == contract_id,
            )
        )
    )
    milestone = result.scalar_one_or_none()

    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meilenstein nicht gefunden",
        )

    await db.delete(milestone)
    await db.commit()


# =============================================================================
# Renewal Option Endpoints
# =============================================================================

@router.get("/{contract_id}/renewal-options", response_model=List[ContractRenewalOptionResponse])
async def list_renewal_options(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[ContractRenewalOptionResponse]:
    """
    Verlaengerungsoptionen eines Vertrags auflisten.
    """
    service = get_contract_service()
    contract = await service.get_contract(db, contract_id, company.company_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    return [_renewal_option_to_response(o) for o in contract.renewal_options]


@router.post("/{contract_id}/renewal-options/{option_id}/decision", response_model=ContractRenewalOptionResponse)
async def make_renewal_decision(
    contract_id: UUID,
    option_id: UUID,
    data: RenewalOptionDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractRenewalOptionResponse:
    """
    Verlaengerungsoption ausueben oder ablehnen.

    Decision: "exercise" oder "decline"
    """
    service = get_contract_service()

    if data.decision == "exercise":
        option, error = await service.exercise_renewal_option(
            db=db,
            option_id=option_id,
            user_id=current_user.id,
            company_id=company.company_id,
            notes=data.notes,
        )
    else:
        option, error = await service.decline_renewal_option(
            db=db,
            option_id=option_id,
            user_id=current_user.id,
            company_id=company.company_id,
            notes=data.notes,
        )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return _renewal_option_to_response(option)


# =============================================================================
# Amendment Endpoints
# =============================================================================

@router.post("/{contract_id}/amendments", response_model=ContractAmendmentResponse, status_code=status.HTTP_201_CREATED)
async def create_amendment(
    contract_id: UUID,
    data: AmendmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractAmendmentResponse:
    """
    Nachtrag/Aenderung zu einem Vertrag hinzufuegen.
    """
    from sqlalchemy import select, func

    # Verify contract exists
    service = get_contract_service()
    contract = await service.get_contract(db, contract_id, company.company_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # Get next amendment number
    result = await db.execute(
        select(func.coalesce(func.max(ContractAmendment.amendment_number), 0))
        .where(ContractAmendment.contract_id == contract_id)
    )
    next_number = (result.scalar() or 0) + 1

    amendment = ContractAmendment(
        contract_id=contract_id,
        amendment_number=next_number,
        title=data.title,
        amendment_date=data.amendment_date,
        effective_date=data.effective_date,
        changes_summary=data.changes_summary,
        affected_clauses=data.affected_clauses,
        changes_detail=data.changes_detail,
        value_change=data.value_change,
        new_total_value=data.new_total_value,
        document_id=data.document_id,
        status=DBAmendmentStatus.DRAFT,
        created_by_id=current_user.id,
    )

    db.add(amendment)
    await db.commit()
    await db.refresh(amendment)

    return _amendment_to_response(amendment)


@router.patch("/{contract_id}/amendments/{amendment_id}", response_model=ContractAmendmentResponse)
async def update_amendment(
    contract_id: UUID,
    amendment_id: UUID,
    data: AmendmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ContractAmendmentResponse:
    """
    Nachtrag aktualisieren.
    """
    from sqlalchemy import select, and_

    # Verify contract exists
    service = get_contract_service()
    contract = await service.get_contract(db, contract_id, company.company_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # Get amendment
    result = await db.execute(
        select(ContractAmendment).where(
            and_(
                ContractAmendment.id == amendment_id,
                ContractAmendment.contract_id == contract_id,
            )
        )
    )
    amendment = result.scalar_one_or_none()

    if not amendment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nachtrag nicht gefunden",
        )

    # Update fields
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"]:
        updates["status"] = DBAmendmentStatus(updates["status"].value)
        # Track approval
        if updates["status"] == DBAmendmentStatus.APPROVED:
            amendment.approved_by_id = current_user.id
            amendment.approved_date = date.today()

    for key, value in updates.items():
        if hasattr(amendment, key) and value is not None:
            setattr(amendment, key, value)

    await db.commit()
    await db.refresh(amendment)

    return _amendment_to_response(amendment)


@router.delete("/{contract_id}/amendments/{amendment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_amendment(
    contract_id: UUID,
    amendment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> None:
    """
    Nachtrag loeschen (nur im DRAFT-Status).
    """
    from sqlalchemy import select, and_

    # Verify contract exists
    service = get_contract_service()
    contract = await service.get_contract(db, contract_id, company.company_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # Get amendment
    result = await db.execute(
        select(ContractAmendment).where(
            and_(
                ContractAmendment.id == amendment_id,
                ContractAmendment.contract_id == contract_id,
            )
        )
    )
    amendment = result.scalar_one_or_none()

    if not amendment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nachtrag nicht gefunden",
        )

    if amendment.status != DBAmendmentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur Nachtraege im Entwurf-Status koennen geloescht werden",
        )

    await db.delete(amendment)
    await db.commit()
