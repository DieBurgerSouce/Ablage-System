"""
Holding KPI Service.

Aggregierte KPIs für Multi-Company Holding-Sicht.

Features:
- Konsolidierte Finanzkennzahlen über alle Firmen
- Intercompany-Verrechnungen Tracking
- Darlehen zwischen Firmen
- Konzernabschluss-Vorbereitung

Created: 2026-01-19
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Company,
    Document,
    InvoiceTracking,
    BusinessEntity,
    BankAccount,
    BankTransaction,
    UserCompany,
)

logger = structlog.get_logger(__name__)


class HoldingKPIService:
    """Service für Holding-Level KPIs und Analytics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_consolidated_overview(
        self,
        user_id: UUID,
        company_ids: Optional[List[UUID]] = None,
    ) -> Dict[str, Any]:
        """Hole konsolidierte Übersicht über alle/ausgewaehlte Firmen.

        Args:
            user_id: User-ID für Berechtigungsprüfung
            company_ids: Optional - Nur diese Firmen einbeziehen

        Returns:
            Konsolidierte KPIs
        """
        # Hole alle Firmen auf die der User Zugriff hat
        if company_ids is None:
            result = await self.db.execute(
                select(Company.id)
                .join(UserCompany, UserCompany.company_id == Company.id)
                .where(
                    UserCompany.user_id == user_id,
                    Company.deleted_at.is_(None)
                )
            )
            company_ids = [row[0] for row in result.all()]

        if not company_ids:
            return self._empty_overview()

        # Parallel alle KPIs sammeln
        overview = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "company_count": len(company_ids),
            "companies": await self._get_company_summaries(company_ids),
            "financials": await self._get_consolidated_financials(company_ids),
            "documents": await self._get_document_metrics(company_ids),
            "invoices": await self._get_invoice_metrics(company_ids),
            "banking": await self._get_banking_metrics(company_ids),
            "intercompany": await self._get_intercompany_metrics(company_ids),
        }

        return overview

    async def _get_company_summaries(
        self, company_ids: List[UUID]
    ) -> List[Dict[str, Any]]:
        """Hole Zusammenfassung für jede Firma."""
        result = await self.db.execute(
            select(Company).where(Company.id.in_(company_ids))
        )
        companies = result.scalars().all()

        summaries = []
        for company in companies:
            summaries.append({
                "id": str(company.id),
                "name": company.name,
                "short_name": company.short_name,
                "subscription_tier": company.subscription_tier or "free",
                "is_active": company.is_active,
            })

        return summaries

    async def _get_consolidated_financials(
        self, company_ids: List[UUID]
    ) -> Dict[str, Any]:
        """Hole konsolidierte Finanzkennzahlen."""
        # Offene Rechnungen (Forderungen)
        receivables_result = await self.db.execute(
            select(func.sum(InvoiceTracking.amount))
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.invoice_type == "outgoing",
                InvoiceTracking.is_paid == False,
            )
        )
        total_receivables = receivables_result.scalar() or Decimal("0")

        # Offene Verbindlichkeiten
        payables_result = await self.db.execute(
            select(func.sum(InvoiceTracking.amount))
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
            )
        )
        total_payables = payables_result.scalar() or Decimal("0")

        # Überfällige Forderungen
        now = datetime.now(timezone.utc)
        overdue_receivables_result = await self.db.execute(
            select(func.sum(InvoiceTracking.amount))
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.invoice_type == "outgoing",
                InvoiceTracking.is_paid == False,
                InvoiceTracking.due_date < now,
            )
        )
        overdue_receivables = overdue_receivables_result.scalar() or Decimal("0")

        # Überfällige Verbindlichkeiten
        overdue_payables_result = await self.db.execute(
            select(func.sum(InvoiceTracking.amount))
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
                InvoiceTracking.due_date < now,
            )
        )
        overdue_payables = overdue_payables_result.scalar() or Decimal("0")

        return {
            "total_receivables": float(total_receivables),
            "total_payables": float(total_payables),
            "net_position": float(total_receivables - total_payables),
            "overdue_receivables": float(overdue_receivables),
            "overdue_payables": float(overdue_payables),
            "currency": "EUR",
        }

    async def _get_document_metrics(
        self, company_ids: List[UUID]
    ) -> Dict[str, Any]:
        """Hole Dokument-Metriken."""
        # Dokumente diese Monat
        start_of_month = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        this_month_result = await self.db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.company_id.in_(company_ids),
                Document.created_at >= start_of_month,
                Document.deleted_at.is_(None),
            )
        )
        documents_this_month = this_month_result.scalar() or 0

        # Gesamt
        total_result = await self.db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.company_id.in_(company_ids),
                Document.deleted_at.is_(None),
            )
        )
        total_documents = total_result.scalar() or 0

        # Pro Status
        status_result = await self.db.execute(
            select(Document.status, func.count())
            .where(
                Document.company_id.in_(company_ids),
                Document.deleted_at.is_(None),
            )
            .group_by(Document.status)
        )
        by_status = {status or "unknown": count for status, count in status_result.all()}

        return {
            "total": total_documents,
            "this_month": documents_this_month,
            "by_status": by_status,
        }

    async def _get_invoice_metrics(
        self, company_ids: List[UUID]
    ) -> Dict[str, Any]:
        """Hole Rechnungs-Metriken."""
        # Offene Rechnungen Anzahl
        open_outgoing_result = await self.db.execute(
            select(func.count())
            .select_from(InvoiceTracking)
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.invoice_type == "outgoing",
                InvoiceTracking.is_paid == False,
            )
        )
        open_outgoing = open_outgoing_result.scalar() or 0

        open_incoming_result = await self.db.execute(
            select(func.count())
            .select_from(InvoiceTracking)
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
            )
        )
        open_incoming = open_incoming_result.scalar() or 0

        # Durchschnittliche Zahlungsdauer (letzte 90 Tage)
        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

        avg_payment_result = await self.db.execute(
            select(func.avg(InvoiceTracking.paid_date - InvoiceTracking.invoice_date))
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.is_paid == True,
                InvoiceTracking.paid_date.isnot(None),
                InvoiceTracking.paid_date >= ninety_days_ago,
            )
        )
        avg_payment_days = avg_payment_result.scalar()
        avg_payment_days = avg_payment_days.days if avg_payment_days else None

        return {
            "open_outgoing": open_outgoing,
            "open_incoming": open_incoming,
            "avg_payment_days": avg_payment_days,
        }

    async def _get_banking_metrics(
        self, company_ids: List[UUID]
    ) -> Dict[str, Any]:
        """Hole Banking-Metriken."""
        # Summe aller Kontostaende
        balance_result = await self.db.execute(
            select(func.sum(BankAccount.balance))
            .where(
                BankAccount.company_id.in_(company_ids),
                BankAccount.is_active == True,
            )
        )
        total_balance = balance_result.scalar() or Decimal("0")

        # Anzahl Konten
        accounts_result = await self.db.execute(
            select(func.count())
            .select_from(BankAccount)
            .where(
                BankAccount.company_id.in_(company_ids),
                BankAccount.is_active == True,
            )
        )
        account_count = accounts_result.scalar() or 0

        # Transaktionen letzte 30 Tage
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        transactions_result = await self.db.execute(
            select(func.count())
            .select_from(BankTransaction)
            .where(
                BankTransaction.company_id.in_(company_ids),
                BankTransaction.booking_date >= thirty_days_ago,
            )
        )
        transactions_30d = transactions_result.scalar() or 0

        return {
            "total_balance": float(total_balance),
            "account_count": account_count,
            "transactions_last_30d": transactions_30d,
            "currency": "EUR",
        }

    async def _get_intercompany_metrics(
        self, company_ids: List[UUID]
    ) -> Dict[str, Any]:
        """Hole Intercompany-Metriken (Verrechnungen zwischen Firmen).

        Identifiziert Transaktionen wo Sender und Empfänger
        beide zur Holding gehoeren.
        """
        # Finde Intercompany-Rechnungen
        # Eine Rechnung ist Intercompany wenn:
        # - Aussteller (company_id) in company_ids
        # - Empfänger (entity) gehoert zu einer anderen Firma in company_ids

        # Hole alle Entity-IDs die zu unseren Firmen gehoeren
        entity_result = await self.db.execute(
            select(BusinessEntity.id, BusinessEntity.company_presence)
            .where(BusinessEntity.company_presence.isnot(None))
        )
        entities = entity_result.all()

        # Filter Entities die zu mehreren unserer Firmen gehoeren
        intercompany_entity_ids = set()
        for entity_id, presence in entities:
            if presence and len(set(presence) & {str(c) for c in company_ids}) >= 1:
                intercompany_entity_ids.add(entity_id)

        if not intercompany_entity_ids:
            return {
                "total_intercompany_volume": 0.0,
                "intercompany_receivables": 0.0,
                "intercompany_payables": 0.0,
                "transaction_count": 0,
            }

        # Intercompany Forderungen/Verbindlichkeiten
        # (vereinfacht - müsste noch verfeinert werden für echte Intercompany-Erkennung)
        intercompany_result = await self.db.execute(
            select(
                InvoiceTracking.invoice_type,
                func.sum(InvoiceTracking.amount),
                func.count()
            )
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.entity_id.in_(intercompany_entity_ids),
                InvoiceTracking.is_paid == False,
            )
            .group_by(InvoiceTracking.invoice_type)
        )

        results = {row[0]: (float(row[1] or 0), row[2]) for row in intercompany_result.all()}

        outgoing = results.get("outgoing", (0.0, 0))
        incoming = results.get("incoming", (0.0, 0))

        return {
            "total_intercompany_volume": outgoing[0] + incoming[0],
            "intercompany_receivables": outgoing[0],
            "intercompany_payables": incoming[0],
            "transaction_count": outgoing[1] + incoming[1],
        }

    def _empty_overview(self) -> Dict[str, Any]:
        """Leere Übersicht wenn keine Firmen vorhanden."""
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "company_count": 0,
            "companies": [],
            "financials": {
                "total_receivables": 0.0,
                "total_payables": 0.0,
                "net_position": 0.0,
                "overdue_receivables": 0.0,
                "overdue_payables": 0.0,
                "currency": "EUR",
            },
            "documents": {"total": 0, "this_month": 0, "by_status": {}},
            "invoices": {"open_outgoing": 0, "open_incoming": 0, "avg_payment_days": None},
            "banking": {"total_balance": 0.0, "account_count": 0, "transactions_last_30d": 0, "currency": "EUR"},
            "intercompany": {
                "total_intercompany_volume": 0.0,
                "intercompany_receivables": 0.0,
                "intercompany_payables": 0.0,
                "transaction_count": 0,
            },
        }

    async def get_company_comparison(
        self,
        company_ids: List[UUID],
        metric: str = "revenue",
    ) -> List[Dict[str, Any]]:
        """Vergleiche Firmen anhand einer Metrik.

        Args:
            company_ids: Firmen zum Vergleichen
            metric: revenue, documents, invoices, etc.

        Returns:
            Vergleichsdaten pro Firma
        """
        comparisons = []

        for company_id in company_ids:
            # Hole Company-Info
            company_result = await self.db.execute(
                select(Company).where(Company.id == company_id)
            )
            company = company_result.scalar_one_or_none()

            if not company:
                continue

            value = 0.0

            if metric == "documents":
                result = await self.db.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                    )
                )
                value = float(result.scalar() or 0)

            elif metric == "receivables":
                result = await self.db.execute(
                    select(func.sum(InvoiceTracking.amount))
                    .where(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.invoice_type == "outgoing",
                        InvoiceTracking.is_paid == False,
                    )
                )
                value = float(result.scalar() or 0)

            elif metric == "payables":
                result = await self.db.execute(
                    select(func.sum(InvoiceTracking.amount))
                    .where(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.invoice_type == "incoming",
                        InvoiceTracking.is_paid == False,
                    )
                )
                value = float(result.scalar() or 0)

            elif metric == "balance":
                result = await self.db.execute(
                    select(func.sum(BankAccount.balance))
                    .where(
                        BankAccount.company_id == company_id,
                        BankAccount.is_active == True,
                    )
                )
                value = float(result.scalar() or 0)

            comparisons.append({
                "company_id": str(company_id),
                "company_name": company.name,
                "metric": metric,
                "value": value,
            })

        # Sortiere absteigend nach Wert
        comparisons.sort(key=lambda x: x["value"], reverse=True)

        return comparisons
