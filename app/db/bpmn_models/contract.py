"""
Business Contract Models

Re-exports canonical models from app.db.models_entity_business to avoid
duplicate __tablename__ definitions that crash SQLAlchemy at startup.

Original comprehensive contract management models are defined in:
    app/db/models_entity_business.py
"""

from datetime import date

from sqlalchemy import event

# Import all contract-related models and enums from the canonical source
from app.db.models_entity_business import (  # noqa: F401
    AmendmentStatus,
    BusinessContract,
    ContractAmendment,
    ContractMilestone,
    ContractRenewalOption,
    ContractStatus,
    ContractType,
    MilestoneType,
    RenewalOptionStatus,
)


# =============================================================================
# Event Listeners
# =============================================================================

@event.listens_for(BusinessContract, 'before_insert')
@event.listens_for(BusinessContract, 'before_update')
def contract_before_save(mapper, connection, target: BusinessContract):
    """Auto-calculate notice deadline before saving."""
    if target.end_date and target.notice_period_days:
        target.notice_deadline = target.calculate_notice_deadline()

    # Auto-update status based on dates
    today = date.today()
    if target.status not in [ContractStatus.DRAFT, ContractStatus.TERMINATED]:
        if target.end_date:
            if target.end_date < today:
                target.status = ContractStatus.EXPIRED
            elif (target.end_date - today).days <= 90:
                target.status = ContractStatus.EXPIRING_SOON
            elif target.status == ContractStatus.EXPIRING_SOON:
                target.status = ContractStatus.ACTIVE
