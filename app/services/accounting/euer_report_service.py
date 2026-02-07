# -*- coding: utf-8 -*-
"""
EÜR Report Service (Einnahmen-Überschuss-Rechnung) - GL-Based.

Generates EÜR from GL entries grouped by account classes:
- Revenue (Einnahmen): Account class 8
- Expenses (Ausgaben): Account class 3, 4

GoBD-compliant, uses posted journal entries only.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_gl_posting import (
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
)
from app.services.accounting.eur_service import EURReport  # Reuse existing

logger = structlog.get_logger(__name__)


@dataclass
class EUeRReport:
    """EÜR Report from GL entries."""
    company_id: UUID
    fiscal_year: int
    period_start: date
    period_end: date

    total_revenue: Decimal
    total_expenses: Decimal
    profit_loss: Decimal


class EUeRReportService:
    """
    Service for EÜR (Einnahmen-Überschuss-Rechnung) from GL entries.

    Groups entries by account_class:
    - Revenue: class 8 (Erlöse)
    - Expenses: class 3 + 4 (Wareneingang + Aufwendungen)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_euer(
        self,
        company_id: UUID,
        fiscal_year: int,
    ) -> EUeRReport:
        """
        Generates EÜR for a fiscal year.

        Args:
            company_id: Company ID
            fiscal_year: Fiscal year

        Returns:
            EUeRReport with revenue, expenses, profit/loss
        """
        period_start = date(fiscal_year, 1, 1)
        period_end = date(fiscal_year, 12, 31)

        # Query: Sum debit/credit per account class
        stmt = (
            select(
                JournalEntryLine.account_number,
                func.sum(JournalEntryLine.debit_amount).label("total_debit"),
                func.sum(JournalEntryLine.credit_amount).label("total_credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                and_(
                    JournalEntry.company_id == company_id,
                    JournalEntry.fiscal_year == fiscal_year,
                    JournalEntry.status == JournalEntryStatus.POSTED.value,
                )
            )
            .group_by(JournalEntryLine.account_number)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        revenue = Decimal("0")
        expenses = Decimal("0")

        for row in rows:
            account_number = row.account_number
            total_debit = row.total_debit or Decimal("0")
            total_credit = row.total_credit or Decimal("0")

            # Account class is first digit
            account_class = int(account_number[0]) if account_number else 0

            if account_class == 8:
                # Revenue accounts (Erlöse)
                # In SKR03: Erlöse are credit-sided
                revenue += total_credit - total_debit
            elif account_class in (3, 4):
                # Expense accounts (Wareneinkauf, Aufwendungen)
                # In SKR03: Aufwendungen are debit-sided
                expenses += total_debit - total_credit

        profit_loss = revenue - expenses

        return EUeRReport(
            company_id=company_id,
            fiscal_year=fiscal_year,
            period_start=period_start,
            period_end=period_end,
            total_revenue=revenue,
            total_expenses=expenses,
            profit_loss=profit_loss,
        )

    async def export_anlage_euer(self, report: EUeRReport) -> str:
        """
        Exports as Anlage EÜR (tax form).

        Delegates to EURReport.to_anlage_eur() (reuse existing).
        """
        # TODO: Convert to EURReport and call to_anlage_eur()
        raise NotImplementedError("Anlage EÜR export - delegates to EURReport")


def get_euer_report_service(db: AsyncSession) -> EUeRReportService:
    """FastAPI Dependency."""
    return EUeRReportService(db)
