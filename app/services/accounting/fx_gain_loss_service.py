# -*- coding: utf-8 -*-
"""
FX Gain/Loss Service - Kursgewinne und -verluste.

Berechnet realisierte und unrealisierte Kursdifferenzen
und erstellt Buchungssätze im GL-System.

SKR03 Konten:
- 2650: Sonstige Erträge, unregelmäßig (Kursgewinne)
- 2150: Sonstige Aufwendungen (Kursverluste)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models_fx import FXGainLossEntry
from app.db.models_gl_posting import JournalEntry, JournalEntryLine

logger = structlog.get_logger(__name__)

# SKR03 FX accounts
KURSGEWINN_ACCOUNT = "2650"  # Kursgewinne
KURSVERLUST_ACCOUNT = "2150"  # Kursverluste


@dataclass
class FXGainLossResult:
    """Ergebnis einer Kursdifferenz-Berechnung."""
    original_currency: str
    original_amount: Decimal
    booking_rate: Decimal
    settlement_rate: Decimal
    booking_eur_amount: Decimal
    settlement_eur_amount: Decimal
    gain_loss_amount: Decimal  # positive = gain, negative = loss
    gain_loss_account: str  # 2650 or 2150
    is_gain: bool


class FXGainLossService:
    """Service für Kursgewinne und -verluste."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def calculate_realized_gain_loss(
        self,
        original_amount: Decimal,
        original_currency: str,
        booking_rate: Decimal,
        settlement_rate: Decimal,
    ) -> FXGainLossResult:
        """
        Berechnet realisierten Kursgewinn/-verlust.

        Formel: (original_amount / settlement_rate) - (original_amount / booking_rate)
        Positiv = Kursgewinn (Konto 2650)
        Negativ = Kursverlust (Konto 2150)
        """
        booking_eur = (original_amount / booking_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        settlement_eur = (original_amount / settlement_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        gain_loss = settlement_eur - booking_eur
        is_gain = gain_loss >= Decimal("0")

        return FXGainLossResult(
            original_currency=original_currency,
            original_amount=original_amount,
            booking_rate=booking_rate,
            settlement_rate=settlement_rate,
            booking_eur_amount=booking_eur,
            settlement_eur_amount=settlement_eur,
            gain_loss_amount=abs(gain_loss),
            gain_loss_account=KURSGEWINN_ACCOUNT if is_gain else KURSVERLUST_ACCOUNT,
            is_gain=is_gain,
        )

    def calculate_unrealized_gain_loss(
        self,
        original_amount: Decimal,
        original_currency: str,
        booking_rate: Decimal,
        current_rate: Decimal,
    ) -> FXGainLossResult:
        """
        Berechnet unrealisierten Kursgewinn/-verlust (Monatsabschluss-Bewertung).
        Gleiche Formel wie realisiert, aber mit aktuellem Stichtagskurs.
        """
        return self.calculate_realized_gain_loss(
            original_amount, original_currency, booking_rate, current_rate
        )

    async def post_fx_gain_loss(
        self,
        company_id: UUID,
        result: FXGainLossResult,
        realized: bool,
        posted_by: UUID,
        reference_document_id: Optional[UUID] = None,
    ) -> FXGainLossEntry:
        """
        Erstellt GL-Buchungssatz für Kursgewinn/-verlust.

        Kursgewinn: Debit Bank/Forderung, Credit 2650
        Kursverlust: Debit 2150, Credit Bank/Forderung
        """
        from app.services.accounting.gl_posting_service import GLPostingService, JournalEntryLineCreate

        gl_service = GLPostingService(self.db)

        if result.is_gain:
            lines = [
                JournalEntryLineCreate(
                    account_number="1200",  # Bank (simplified)
                    account_name="Bank",
                    debit_amount=result.gain_loss_amount,
                    credit_amount=Decimal("0"),
                    text=f"Kursgewinn {result.original_currency}",
                ),
                JournalEntryLineCreate(
                    account_number=KURSGEWINN_ACCOUNT,
                    account_name="Kursgewinne",
                    debit_amount=Decimal("0"),
                    credit_amount=result.gain_loss_amount,
                    text=f"Kursgewinn {result.original_currency}",
                ),
            ]
        else:
            lines = [
                JournalEntryLineCreate(
                    account_number=KURSVERLUST_ACCOUNT,
                    account_name="Kursverluste",
                    debit_amount=result.gain_loss_amount,
                    credit_amount=Decimal("0"),
                    text=f"Kursverlust {result.original_currency}",
                ),
                JournalEntryLineCreate(
                    account_number="1200",
                    account_name="Bank",
                    debit_amount=Decimal("0"),
                    credit_amount=result.gain_loss_amount,
                    text=f"Kursverlust {result.original_currency}",
                ),
            ]

        kind = "realisiert" if realized else "unrealisiert"
        description = f"Kursdifferenz {result.original_currency} ({kind})"

        journal_entry = await gl_service.create_journal_entry(
            company_id=company_id,
            lines=lines,
            posting_date=utc_now().date(),
            description=description,
            source="pipeline",
            created_by=posted_by,
        )

        # Auto-post the FX entry
        await gl_service.post_journal_entry(journal_entry.id, posted_by)

        # Record FX gain/loss
        fx_entry = FXGainLossEntry(
            company_id=company_id,
            journal_entry_id=journal_entry.id,
            original_currency=result.original_currency,
            original_amount=result.original_amount,
            booking_rate=result.booking_rate,
            settlement_rate=result.settlement_rate,
            gain_loss_amount=result.gain_loss_amount if result.is_gain else -result.gain_loss_amount,
            gain_loss_account=result.gain_loss_account,
            realized=realized,
            reference_document_id=reference_document_id,
        )
        self.db.add(fx_entry)
        await self.db.commit()
        await self.db.refresh(fx_entry)

        logger.info(
            "fx_gain_loss_posted",
            company_id=str(company_id),
            currency=result.original_currency,
            amount=str(result.gain_loss_amount),
            is_gain=result.is_gain,
            realized=realized,
        )

        return fx_entry

    async def get_fx_entries(
        self,
        company_id: UUID,
        realized: Optional[bool] = None,
        currency: Optional[str] = None,
    ) -> List[FXGainLossEntry]:
        """Laedt FX-Einträge mit optionalen Filtern."""
        conditions = [FXGainLossEntry.company_id == company_id]
        if realized is not None:
            conditions.append(FXGainLossEntry.realized == realized)
        if currency:
            conditions.append(FXGainLossEntry.original_currency == currency)

        result = await self.db.execute(
            select(FXGainLossEntry).where(and_(*conditions)).order_by(FXGainLossEntry.created_at.desc())
        )
        return list(result.scalars().all())


def get_fx_gain_loss_service(db: AsyncSession) -> FXGainLossService:
    return FXGainLossService(db)
