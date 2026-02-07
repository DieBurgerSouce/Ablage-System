# -*- coding: utf-8 -*-
"""
AmountTierService - Betragsbasierte Freigabestufen.

Drei konfigurierbare Stufen pro Firma:
- Auto (<500 EUR): Automatische Freigabe bei ausreichendem Trust-Level
- One-Click (500-5000 EUR): Ein-Klick-Bestaetigung
- Explicit (>5000 EUR): Explizite Pruefung erforderlich
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import Company

logger = structlog.get_logger(__name__)


class ApprovalMode(str, Enum):
    """Freigabemodus."""
    AUTO = "auto"
    ONE_CLICK = "one_click"
    EXPLICIT = "explicit"


@dataclass
class AmountTier:
    """Eine Betrags-Freigabestufe."""
    name: str
    max_amount: Decimal
    approval_mode: str  # "auto", "one_click", "explicit"
    min_trust_level: str  # Trust-Level Mindestanforderung


# Default tiers
DEFAULT_TIERS: List[AmountTier] = [
    AmountTier(
        name="Automatisch",
        max_amount=Decimal("500.00"),
        approval_mode="auto",
        min_trust_level="auto_accept",
    ),
    AmountTier(
        name="Ein-Klick",
        max_amount=Decimal("5000.00"),
        approval_mode="one_click",
        min_trust_level="confidence",
    ),
    AmountTier(
        name="Explizit",
        max_amount=Decimal("999999999.99"),
        approval_mode="explicit",
        min_trust_level="assistance",
    ),
]

# Trust level ordering for comparison
TRUST_LEVEL_ORDER = {
    "assistance": 1,
    "auto_accept": 2,
    "confidence": 3,
    "autonomous": 4,
}


class AmountTierService:
    """Verwaltet betragsbasierte Freigabestufen pro Firma."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_tiers(self, company_id: UUID) -> List[AmountTier]:
        """Laedt Tier-Konfiguration fuer eine Firma (aus filing_rules JSONB).
        Falls keine Custom-Config existiert, werden Default-Tiers zurueckgegeben."""
        try:
            stmt = select(Company).where(Company.id == company_id)
            result = await self.db.execute(stmt)
            company = result.scalar_one_or_none()

            if not company:
                logger.warning("Company not found", company_id=str(company_id))
                return DEFAULT_TIERS

            # Load from filing_rules JSONB under "amount_tiers" key
            if not company.filing_rules or "amount_tiers" not in company.filing_rules:
                logger.info("No custom amount tiers found, returning defaults", company_id=str(company_id))
                return DEFAULT_TIERS

            tiers_data = company.filing_rules["amount_tiers"]
            tiers = []
            for tier_dict in tiers_data:
                tier = AmountTier(
                    name=tier_dict["name"],
                    max_amount=Decimal(str(tier_dict["max_amount"])),
                    approval_mode=tier_dict["approval_mode"],
                    min_trust_level=tier_dict["min_trust_level"],
                )
                tiers.append(tier)

            return tiers

        except Exception as e:
            logger.warning("Failed to load amount tiers", **safe_error_log(e, f"company_id={company_id}"))
            return DEFAULT_TIERS

    async def update_tiers(self, company_id: UUID, tiers: List[AmountTier]) -> List[AmountTier]:
        """Aktualisiert Tier-Konfiguration fuer eine Firma.
        Validiert: mindestens 2 Stufen, aufsteigende max_amounts, letzte Stufe ist EXPLICIT."""
        try:
            # Validation: at least 2 tiers
            if len(tiers) < 2:
                raise ValueError("Mindestens 2 Betragstufen erforderlich")

            # Validation: max_amounts ascending
            for i in range(len(tiers) - 1):
                if tiers[i].max_amount >= tiers[i + 1].max_amount:
                    raise ValueError("Betrags-Obergrenze muss aufsteigend sein")

            # Validation: last tier must be EXPLICIT
            if tiers[-1].approval_mode != "explicit":
                raise ValueError("Letzte Betragstufe muss 'Explizit' sein")

            # Load company
            stmt = select(Company).where(Company.id == company_id)
            result = await self.db.execute(stmt)
            company = result.scalar_one_or_none()

            if not company:
                raise ValueError("Firma nicht gefunden")

            # Convert tiers to dict format for JSONB storage
            tiers_data = []
            for tier in tiers:
                tiers_data.append({
                    "name": tier.name,
                    "max_amount": str(tier.max_amount),
                    "approval_mode": tier.approval_mode,
                    "min_trust_level": tier.min_trust_level,
                })

            # Store in filing_rules JSONB under "amount_tiers" key
            if not company.filing_rules:
                company.filing_rules = {}
            company.filing_rules["amount_tiers"] = tiers_data

            # Persist
            await self.db.flush()
            await self.db.commit()

            logger.info("Amount tiers updated", company_id=str(company_id), tier_count=len(tiers))
            return tiers

        except Exception as e:
            await self.db.rollback()
            logger.error("Failed to update amount tiers", **safe_error_log(e, f"company_id={company_id}"))
            raise

    async def get_approval_mode(
        self, company_id: UUID, amount: Decimal, trust_level: str
    ) -> str:
        """Bestimmt den Freigabemodus basierend auf Betrag und Trust-Level.

        Logik:
        1. Finde passende Stufe (erste wo amount <= max_amount)
        2. Pruefe ob trust_level >= min_trust_level der Stufe
        3. Falls Trust-Level nicht ausreicht -> naechsthoehere Stufe
        """
        tiers = await self.get_tiers(company_id)

        for i, tier in enumerate(tiers):
            if amount <= tier.max_amount:
                # Check if trust level meets minimum
                trust_order_current = TRUST_LEVEL_ORDER.get(trust_level, 0)
                trust_order_required = TRUST_LEVEL_ORDER.get(tier.min_trust_level, 0)

                if trust_order_current >= trust_order_required:
                    return tier.approval_mode

                # Trust level insufficient, escalate to next higher tier
                if i + 1 < len(tiers):
                    return tiers[i + 1].approval_mode
                else:
                    # Already at highest tier, return EXPLICIT
                    return "explicit"

        return "explicit"


def get_amount_tier_service(db: AsyncSession) -> AmountTierService:
    """Dependency injection factory."""
    return AmountTierService(db)
