"""
Contract Management Service

Business logic for managing B2B contracts including:
- CRUD operations
- Deadline tracking and alerts
- Renewal options management
- Contract analytics
"""

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.orm import selectinload

import structlog

from app.db.models import (
    BusinessContract,
    ContractMilestone,
    ContractRenewalOption,
    ContractAmendment,
    ContractType,
    ContractStatus,
    RenewalOptionStatus,
    MilestoneType,
    AmendmentStatus,
    BusinessEntity,
    Document,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ContractSummary:
    """Summary statistics for contracts."""
    total_contracts: int
    active_contracts: int
    expiring_soon: int
    critical_deadlines: int
    total_value: Decimal
    monthly_commitment: Decimal


@dataclass
class DeadlineAlert:
    """Alert for an upcoming deadline."""
    contract_id: UUID
    contract_number: str
    contract_title: str
    deadline_type: str  # "notice", "end", "renewal"
    deadline_date: date
    days_remaining: int
    urgency: str  # "critical", "warning", "upcoming"
    party_name: Optional[str]


@dataclass
class ContractTimelineEvent:
    """Event in a contract timeline."""
    event_date: date
    event_type: str
    title: str
    description: Optional[str]
    is_completed: bool
    contract_id: UUID


# =============================================================================
# Contract Service
# =============================================================================

class ContractService:
    """
    Service for managing business contracts.

    Features:
    - Full CRUD operations
    - Deadline calculations and alerts
    - Renewal management
    - Portfolio analytics
    """

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    async def create_contract(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        contract_number: str,
        title: str,
        start_date: date,
        contract_type: ContractType = ContractType.OTHER,
        end_date: Optional[date] = None,
        duration_months: Optional[int] = None,
        notice_period_days: int = 30,
        auto_renewal: bool = False,
        renewal_period_months: Optional[int] = None,
        total_value: Optional[Decimal] = None,
        monthly_value: Optional[Decimal] = None,
        party_a_id: Optional[UUID] = None,
        party_a_name: Optional[str] = None,
        party_b_id: Optional[UUID] = None,
        party_b_name: Optional[str] = None,
        document_id: Optional[UUID] = None,
        **kwargs,
    ) -> BusinessContract:
        """Create a new contract."""
        # Calculate end_date from duration if not provided
        if not end_date and duration_months:
            end_date = start_date + timedelta(days=duration_months * 30)

        contract = BusinessContract(
            company_id=company_id,
            created_by_id=user_id,
            contract_number=contract_number,
            title=title,
            contract_type=contract_type,
            start_date=start_date,
            end_date=end_date,
            duration_months=duration_months,
            notice_period_days=notice_period_days,
            auto_renewal=auto_renewal,
            renewal_period_months=renewal_period_months,
            total_value=total_value,
            monthly_value=monthly_value,
            party_a_id=party_a_id,
            party_a_name=party_a_name,
            party_b_id=party_b_id,
            party_b_name=party_b_name,
            document_id=document_id,
            status=ContractStatus.DRAFT,
            **kwargs,
        )

        db.add(contract)
        await db.flush()

        # Create default milestones
        await self._create_default_milestones(db, contract)

        # Create renewal options if auto_renewal
        if auto_renewal and renewal_period_months and end_date:
            await self._create_renewal_options(db, contract)

        await db.commit()
        await db.refresh(contract)

        logger.info(
            "contract_created",
            contract_id=str(contract.id),
            contract_number=contract_number,
            company_id=str(company_id),
        )

        return contract

    async def get_contract(
        self,
        db: AsyncSession,
        contract_id: UUID,
        company_id: UUID,
    ) -> Optional[BusinessContract]:
        """Get a single contract by ID."""
        result = await db.execute(
            select(BusinessContract)
            .options(
                selectinload(BusinessContract.party_a),
                selectinload(BusinessContract.party_b),
                selectinload(BusinessContract.milestones),
                selectinload(BusinessContract.renewal_options),
            )
            .where(
                and_(
                    BusinessContract.id == contract_id,
                    BusinessContract.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_contract(
        self,
        db: AsyncSession,
        contract_id: UUID,
        company_id: UUID,
        **updates,
    ) -> Optional[BusinessContract]:
        """Update a contract."""
        contract = await self.get_contract(db, contract_id, company_id)
        if not contract:
            return None

        for key, value in updates.items():
            if hasattr(contract, key) and value is not None:
                setattr(contract, key, value)

        contract.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(contract)

        logger.info(
            "contract_updated",
            contract_id=str(contract_id),
            fields=list(updates.keys()),
        )

        return contract

    async def delete_contract(
        self,
        db: AsyncSession,
        contract_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Delete a contract (soft delete by setting status to TERMINATED)."""
        contract = await self.get_contract(db, contract_id, company_id)
        if not contract:
            return False

        contract.status = ContractStatus.TERMINATED
        contract.terminated_date = date.today()
        contract.updated_at = datetime.utcnow()

        await db.commit()

        logger.info("contract_deleted", contract_id=str(contract_id))
        return True

    # -------------------------------------------------------------------------
    # List and Search
    # -------------------------------------------------------------------------

    async def list_contracts(
        self,
        db: AsyncSession,
        company_id: UUID,
        status: Optional[ContractStatus] = None,
        contract_type: Optional[ContractType] = None,
        party_id: Optional[UUID] = None,
        expiring_within_days: Optional[int] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        order_by: str = "end_date",
        order_dir: str = "asc",
    ) -> Tuple[List[BusinessContract], int]:
        """List contracts with filtering."""
        query = select(BusinessContract).where(
            BusinessContract.company_id == company_id
        )

        # Apply filters
        if status:
            query = query.where(BusinessContract.status == status)
        else:
            # Exclude terminated by default
            query = query.where(BusinessContract.status != ContractStatus.TERMINATED)

        if contract_type:
            query = query.where(BusinessContract.contract_type == contract_type)

        if party_id:
            query = query.where(
                or_(
                    BusinessContract.party_a_id == party_id,
                    BusinessContract.party_b_id == party_id,
                )
            )

        if expiring_within_days:
            cutoff_date = date.today() + timedelta(days=expiring_within_days)
            query = query.where(
                and_(
                    BusinessContract.end_date.isnot(None),
                    BusinessContract.end_date <= cutoff_date,
                    BusinessContract.end_date >= date.today(),
                )
            )

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    BusinessContract.contract_number.ilike(search_pattern),
                    BusinessContract.title.ilike(search_pattern),
                    BusinessContract.party_a_name.ilike(search_pattern),
                    BusinessContract.party_b_name.ilike(search_pattern),
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Order
        order_column = getattr(BusinessContract, order_by, BusinessContract.end_date)
        if order_dir == "desc":
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(asc(order_column))

        # Pagination
        query = query.offset(offset).limit(limit)

        # Include relationships
        query = query.options(
            selectinload(BusinessContract.party_a),
            selectinload(BusinessContract.party_b),
        )

        result = await db.execute(query)
        contracts = list(result.scalars().all())

        return contracts, total

    # -------------------------------------------------------------------------
    # Deadline Management
    # -------------------------------------------------------------------------

    async def get_upcoming_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 90,
    ) -> List[DeadlineAlert]:
        """Get all upcoming contract deadlines."""
        alerts: List[DeadlineAlert] = []
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        # Get contracts with upcoming notice deadlines or end dates
        result = await db.execute(
            select(BusinessContract)
            .options(selectinload(BusinessContract.party_a))
            .where(
                and_(
                    BusinessContract.company_id == company_id,
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                    or_(
                        and_(
                            BusinessContract.notice_deadline.isnot(None),
                            BusinessContract.notice_deadline <= cutoff,
                            BusinessContract.notice_deadline >= today,
                        ),
                        and_(
                            BusinessContract.end_date.isnot(None),
                            BusinessContract.end_date <= cutoff,
                            BusinessContract.end_date >= today,
                        ),
                    ),
                )
            )
        )
        contracts = result.scalars().all()

        for contract in contracts:
            # Notice deadline alert
            if contract.notice_deadline and today <= contract.notice_deadline <= cutoff:
                days = (contract.notice_deadline - today).days
                alerts.append(DeadlineAlert(
                    contract_id=contract.id,
                    contract_number=contract.contract_number,
                    contract_title=contract.title,
                    deadline_type="notice",
                    deadline_date=contract.notice_deadline,
                    days_remaining=days,
                    urgency=self._get_urgency(days),
                    party_name=contract.party_a.name if contract.party_a else contract.party_a_name,
                ))

            # End date alert
            if contract.end_date and today <= contract.end_date <= cutoff:
                days = (contract.end_date - today).days
                # Only add if different from notice deadline
                if not contract.notice_deadline or contract.notice_deadline != contract.end_date:
                    alerts.append(DeadlineAlert(
                        contract_id=contract.id,
                        contract_number=contract.contract_number,
                        contract_title=contract.title,
                        deadline_type="end",
                        deadline_date=contract.end_date,
                        days_remaining=days,
                        urgency=self._get_urgency(days),
                        party_name=contract.party_a.name if contract.party_a else contract.party_a_name,
                    ))

        # Get renewal option deadlines
        renewal_result = await db.execute(
            select(ContractRenewalOption)
            .join(BusinessContract)
            .where(
                and_(
                    BusinessContract.company_id == company_id,
                    ContractRenewalOption.status == RenewalOptionStatus.AVAILABLE,
                    ContractRenewalOption.exercise_deadline <= cutoff,
                    ContractRenewalOption.exercise_deadline >= today,
                )
            )
            .options(selectinload(ContractRenewalOption.contract))
        )
        renewal_options = renewal_result.scalars().all()

        for option in renewal_options:
            days = (option.exercise_deadline - today).days
            alerts.append(DeadlineAlert(
                contract_id=option.contract_id,
                contract_number=option.contract.contract_number,
                contract_title=f"{option.contract.title} - Verlaengerungsoption {option.option_number}",
                deadline_type="renewal",
                deadline_date=option.exercise_deadline,
                days_remaining=days,
                urgency=self._get_urgency(days),
                party_name=None,
            ))

        # Sort by days remaining
        alerts.sort(key=lambda a: a.days_remaining)
        return alerts

    def _get_urgency(self, days: int) -> str:
        """Determine urgency level based on days remaining."""
        if days <= 7:
            return "critical"
        elif days <= 30:
            return "warning"
        return "upcoming"

    # -------------------------------------------------------------------------
    # Renewal Management
    # -------------------------------------------------------------------------

    async def exercise_renewal_option(
        self,
        db: AsyncSession,
        option_id: UUID,
        user_id: UUID,
        company_id: UUID,
        notes: Optional[str] = None,
    ) -> Tuple[Optional[ContractRenewalOption], Optional[str]]:
        """Exercise a renewal option."""
        result = await db.execute(
            select(ContractRenewalOption)
            .join(BusinessContract)
            .where(
                and_(
                    ContractRenewalOption.id == option_id,
                    BusinessContract.company_id == company_id,
                )
            )
            .options(selectinload(ContractRenewalOption.contract))
        )
        option = result.scalar_one_or_none()

        if not option:
            return None, "Verlaengerungsoption nicht gefunden"

        if option.status != RenewalOptionStatus.AVAILABLE:
            return None, f"Option nicht verfuegbar (Status: {option.status})"

        if option.exercise_deadline < date.today():
            option.status = RenewalOptionStatus.EXPIRED
            await db.commit()
            return None, "Frist fuer Verlaengerungsoption abgelaufen"

        # Exercise the option
        option.status = RenewalOptionStatus.EXERCISED
        option.exercised_date = date.today()
        option.exercised_by_id = user_id
        option.decision_notes = notes

        # Update contract
        contract = option.contract
        contract.end_date = option.renewal_start_date + timedelta(
            days=option.renewal_duration_months * 30
        )
        contract.current_renewal_count += 1
        contract.status = ContractStatus.RENEWED

        # Update notice deadline
        contract.update_notice_deadline()

        # Update financial values if specified
        if option.new_monthly_value:
            contract.monthly_value = option.new_monthly_value
            if option.renewal_duration_months:
                contract.total_value = option.new_monthly_value * option.renewal_duration_months

        await db.commit()

        logger.info(
            "renewal_option_exercised",
            option_id=str(option_id),
            contract_id=str(contract.id),
            new_end_date=str(contract.end_date),
        )

        return option, None

    async def decline_renewal_option(
        self,
        db: AsyncSession,
        option_id: UUID,
        user_id: UUID,
        company_id: UUID,
        notes: Optional[str] = None,
    ) -> Tuple[Optional[ContractRenewalOption], Optional[str]]:
        """Decline a renewal option."""
        result = await db.execute(
            select(ContractRenewalOption)
            .join(BusinessContract)
            .where(
                and_(
                    ContractRenewalOption.id == option_id,
                    BusinessContract.company_id == company_id,
                )
            )
        )
        option = result.scalar_one_or_none()

        if not option:
            return None, "Verlaengerungsoption nicht gefunden"

        if option.status != RenewalOptionStatus.AVAILABLE:
            return None, f"Option nicht verfuegbar (Status: {option.status})"

        option.status = RenewalOptionStatus.DECLINED
        option.exercised_date = date.today()
        option.exercised_by_id = user_id
        option.decision_notes = notes

        await db.commit()

        logger.info(
            "renewal_option_declined",
            option_id=str(option_id),
        )

        return option, None

    # -------------------------------------------------------------------------
    # Analytics
    # -------------------------------------------------------------------------

    async def get_portfolio_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> ContractSummary:
        """Get contract portfolio summary statistics."""
        today = date.today()
        expiring_cutoff = today + timedelta(days=90)
        critical_cutoff = today + timedelta(days=30)

        # Total contracts (non-terminated)
        total_result = await db.execute(
            select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.company_id == company_id,
                    BusinessContract.status != ContractStatus.TERMINATED,
                )
            )
        )
        total = total_result.scalar() or 0

        # Active contracts
        active_result = await db.execute(
            select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.company_id == company_id,
                    BusinessContract.status == ContractStatus.ACTIVE,
                )
            )
        )
        active = active_result.scalar() or 0

        # Expiring soon
        expiring_result = await db.execute(
            select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.company_id == company_id,
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                    BusinessContract.end_date.isnot(None),
                    BusinessContract.end_date <= expiring_cutoff,
                    BusinessContract.end_date >= today,
                )
            )
        )
        expiring = expiring_result.scalar() or 0

        # Critical deadlines (notice within 30 days)
        critical_result = await db.execute(
            select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.company_id == company_id,
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                    BusinessContract.notice_deadline.isnot(None),
                    BusinessContract.notice_deadline <= critical_cutoff,
                    BusinessContract.notice_deadline >= today,
                )
            )
        )
        critical = critical_result.scalar() or 0

        # Total value
        value_result = await db.execute(
            select(
                func.coalesce(func.sum(BusinessContract.total_value), 0),
                func.coalesce(func.sum(BusinessContract.monthly_value), 0),
            ).where(
                and_(
                    BusinessContract.company_id == company_id,
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                )
            )
        )
        values = value_result.fetchone()

        return ContractSummary(
            total_contracts=total,
            active_contracts=active,
            expiring_soon=expiring,
            critical_deadlines=critical,
            total_value=Decimal(str(values[0])) if values and values[0] is not None else Decimal("0"),
            monthly_commitment=Decimal(str(values[1])) if values and values[1] is not None else Decimal("0"),
        )

    async def get_contract_timeline(
        self,
        db: AsyncSession,
        contract_id: UUID,
        company_id: UUID,
    ) -> List[ContractTimelineEvent]:
        """Get timeline events for a contract."""
        contract = await self.get_contract(db, contract_id, company_id)
        if not contract:
            return []

        events: List[ContractTimelineEvent] = []
        today = date.today()

        # Contract start
        events.append(ContractTimelineEvent(
            event_date=contract.start_date,
            event_type="contract_start",
            title="Vertragsbeginn",
            description=None,
            is_completed=contract.start_date <= today,
            contract_id=contract.id,
        ))

        # Contract milestones
        for milestone in contract.milestones:
            events.append(ContractTimelineEvent(
                event_date=milestone.scheduled_date,
                event_type=milestone.milestone_type.value,
                title=milestone.title,
                description=milestone.description,
                is_completed=milestone.is_completed,
                contract_id=contract.id,
            ))

        # Renewal options
        for option in contract.renewal_options:
            events.append(ContractTimelineEvent(
                event_date=option.exercise_deadline,
                event_type="renewal_option",
                title=f"Verlaengerungsoption {option.option_number}",
                description=f"{option.renewal_duration_months} Monate",
                is_completed=option.status in [
                    RenewalOptionStatus.EXERCISED,
                    RenewalOptionStatus.DECLINED,
                    RenewalOptionStatus.EXPIRED,
                ],
                contract_id=contract.id,
            ))

        # Notice deadline
        if contract.notice_deadline:
            events.append(ContractTimelineEvent(
                event_date=contract.notice_deadline,
                event_type="notice_deadline",
                title="Kuendigungsfrist",
                description=f"{contract.notice_period_days} Tage Frist",
                is_completed=contract.notice_deadline <= today,
                contract_id=contract.id,
            ))

        # Contract end
        if contract.end_date:
            events.append(ContractTimelineEvent(
                event_date=contract.end_date,
                event_type="contract_end",
                title="Vertragsende",
                description=None,
                is_completed=contract.end_date <= today,
                contract_id=contract.id,
            ))

        # Sort by date
        events.sort(key=lambda e: e.event_date)
        return events

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    async def _create_default_milestones(
        self,
        db: AsyncSession,
        contract: BusinessContract,
    ) -> None:
        """Create default milestones for a contract."""
        milestones = []

        # Contract start milestone
        milestones.append(ContractMilestone(
            contract_id=contract.id,
            milestone_type=MilestoneType.CONTRACT_START,
            title="Vertragsbeginn",
            scheduled_date=contract.start_date,
            is_completed=contract.start_date <= date.today(),
        ))

        # Notice deadline milestone
        if contract.notice_deadline:
            milestones.append(ContractMilestone(
                contract_id=contract.id,
                milestone_type=MilestoneType.NOTICE_DEADLINE,
                title="Kuendigungsfrist",
                description=f"{contract.notice_period_days} Tage vor Vertragsende",
                scheduled_date=contract.notice_deadline,
            ))

        # Contract end milestone
        if contract.end_date:
            milestones.append(ContractMilestone(
                contract_id=contract.id,
                milestone_type=MilestoneType.CONTRACT_END,
                title="Vertragsende",
                scheduled_date=contract.end_date,
            ))

        # Price adjustment milestone
        if contract.price_adjustment_clause and contract.price_adjustment_date:
            milestones.append(ContractMilestone(
                contract_id=contract.id,
                milestone_type=MilestoneType.PRICE_ADJUSTMENT,
                title="Preisanpassung",
                description=f"Index: {contract.price_adjustment_index or 'VPI'}",
                scheduled_date=contract.price_adjustment_date,
            ))

        for milestone in milestones:
            db.add(milestone)

    async def _create_renewal_options(
        self,
        db: AsyncSession,
        contract: BusinessContract,
        num_options: int = 3,
    ) -> None:
        """Create renewal options for a contract."""
        if not contract.end_date or not contract.renewal_period_months:
            return

        current_end = contract.end_date
        for i in range(1, num_options + 1):
            if contract.max_renewals and i > contract.max_renewals:
                break

            # Exercise deadline is notice_period_days before current end
            exercise_deadline = current_end - timedelta(days=contract.notice_period_days)

            # New start date is current end
            renewal_start = current_end

            option = ContractRenewalOption(
                contract_id=contract.id,
                option_number=i,
                renewal_duration_months=contract.renewal_period_months,
                exercise_deadline=exercise_deadline,
                renewal_start_date=renewal_start,
                notice_required_days=contract.notice_period_days,
            )
            db.add(option)

            # Next option's end date
            current_end = renewal_start + timedelta(days=contract.renewal_period_months * 30)


# =============================================================================
# Singleton
# =============================================================================

_contract_service: Optional[ContractService] = None


def get_contract_service() -> ContractService:
    """Get or create ContractService singleton."""
    global _contract_service
    if _contract_service is None:
        _contract_service = ContractService()
    return _contract_service
