# -*- coding: utf-8 -*-
"""
Company Metrics Service.

Aggregiert Metriken über alle Firmen für das Multi-Firma-Dashboard.
Bietet Vergleichsdaten und KPIs für Management-Übersicht.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (

    Company,
    Document,
    BusinessEntity,
    InvoiceTracking,
    DunningRecord,
    BankTransaction,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class CompanyDocumentMetrics:
    """Dokument-Metriken für eine Firma."""

    total_documents: int = 0
    documents_this_month: int = 0
    documents_last_month: int = 0
    document_growth_percent: float = 0.0


@dataclass
class CompanyInvoiceMetrics:
    """Rechnungs-Metriken für eine Firma."""

    total_invoices: int = 0
    total_amount: Decimal = Decimal("0.00")
    paid_amount: Decimal = Decimal("0.00")
    outstanding_amount: Decimal = Decimal("0.00")
    overdue_count: int = 0
    overdue_amount: Decimal = Decimal("0.00")
    average_payment_days: float = 0.0


@dataclass
class CompanyEntityMetrics:
    """Geschäftspartner-Metriken für eine Firma."""

    total_entities: int = 0
    customers: int = 0
    suppliers: int = 0
    high_risk_entities: int = 0


@dataclass
class CompanyDunningMetrics:
    """Mahnwesen-Metriken für eine Firma."""

    active_dunnings: int = 0
    total_dunning_amount: Decimal = Decimal("0.00")
    level_1_count: int = 0
    level_2_count: int = 0
    level_3_count: int = 0
    level_4_count: int = 0


@dataclass
class CompanyBankingMetrics:
    """Banking-Metriken für eine Firma."""

    total_balance: Decimal = Decimal("0.00")
    incoming_this_month: Decimal = Decimal("0.00")
    outgoing_this_month: Decimal = Decimal("0.00")
    unmatched_transactions: int = 0


@dataclass
class CompanyMetrics:
    """Aggregierte Metriken für eine Firma."""

    company_id: UUID
    company_name: str
    company_short_name: Optional[str] = None
    is_active: bool = True

    documents: CompanyDocumentMetrics = field(default_factory=CompanyDocumentMetrics)
    invoices: CompanyInvoiceMetrics = field(default_factory=CompanyInvoiceMetrics)
    entities: CompanyEntityMetrics = field(default_factory=CompanyEntityMetrics)
    dunning: CompanyDunningMetrics = field(default_factory=CompanyDunningMetrics)
    banking: CompanyBankingMetrics = field(default_factory=CompanyBankingMetrics)

    # Health Score (0-100)
    health_score: int = 100

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für JSON-Response."""
        return {
            "company_id": str(self.company_id),
            "company_name": self.company_name,
            "company_short_name": self.company_short_name,
            "is_active": self.is_active,
            "health_score": self.health_score,
            "documents": {
                "total": self.documents.total_documents,
                "this_month": self.documents.documents_this_month,
                "last_month": self.documents.documents_last_month,
                "growth_percent": round(self.documents.document_growth_percent, 1),
            },
            "invoices": {
                "total": self.invoices.total_invoices,
                "total_amount": float(self.invoices.total_amount),
                "paid_amount": float(self.invoices.paid_amount),
                "outstanding_amount": float(self.invoices.outstanding_amount),
                "overdue_count": self.invoices.overdue_count,
                "overdue_amount": float(self.invoices.overdue_amount),
                "average_payment_days": round(self.invoices.average_payment_days, 1),
            },
            "entities": {
                "total": self.entities.total_entities,
                "customers": self.entities.customers,
                "suppliers": self.entities.suppliers,
                "high_risk": self.entities.high_risk_entities,
            },
            "dunning": {
                "active": self.dunning.active_dunnings,
                "total_amount": float(self.dunning.total_dunning_amount),
                "by_level": {
                    "1": self.dunning.level_1_count,
                    "2": self.dunning.level_2_count,
                    "3": self.dunning.level_3_count,
                    "4": self.dunning.level_4_count,
                },
            },
            "banking": {
                "balance": float(self.banking.total_balance),
                "incoming_this_month": float(self.banking.incoming_this_month),
                "outgoing_this_month": float(self.banking.outgoing_this_month),
                "unmatched_transactions": self.banking.unmatched_transactions,
            },
        }


@dataclass
class DashboardSummary:
    """Zusammenfassung aller Firmen-Metriken."""

    total_companies: int = 0
    active_companies: int = 0
    total_documents: int = 0
    total_invoices: int = 0
    total_outstanding_amount: Decimal = Decimal("0.00")
    total_overdue_amount: Decimal = Decimal("0.00")
    total_entities: int = 0
    active_dunnings: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für JSON-Response."""
        return {
            "total_companies": self.total_companies,
            "active_companies": self.active_companies,
            "total_documents": self.total_documents,
            "total_invoices": self.total_invoices,
            "total_outstanding_amount": float(self.total_outstanding_amount),
            "total_overdue_amount": float(self.total_overdue_amount),
            "total_entities": self.total_entities,
            "active_dunnings": self.active_dunnings,
        }


class CompanyMetricsService:
    """Service für Firmen-Metriken und Dashboard-Daten."""

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    async def get_company_metrics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> CompanyMetrics:
        """
        Holt Metriken für eine einzelne Firma.

        Args:
            db: Datenbank-Session
            company_id: ID der Firma

        Returns:
            CompanyMetrics mit allen Aggregationen
        """
        # Lade Company
        company_query = select(Company).where(Company.id == company_id)
        result = await db.execute(company_query)
        company = result.scalar_one_or_none()

        if not company:
            raise ValueError(f"Firma nicht gefunden: {company_id}")

        metrics = CompanyMetrics(
            company_id=company_id,
            company_name=company.name,
            company_short_name=company.short_name,
            is_active=company.is_active if hasattr(company, 'is_active') else True,
        )

        # Sammle alle Metriken parallel
        metrics.documents = await self._get_document_metrics(db, company_id)
        metrics.invoices = await self._get_invoice_metrics(db, company_id)
        metrics.entities = await self._get_entity_metrics(db, company_id)
        metrics.dunning = await self._get_dunning_metrics(db, company_id)
        metrics.banking = await self._get_banking_metrics(db, company_id)

        # Berechne Health Score
        metrics.health_score = self._calculate_health_score(metrics)

        return metrics

    async def get_all_company_metrics(
        self,
        db: AsyncSession,
        include_inactive: bool = False,
    ) -> List[CompanyMetrics]:
        """
        Holt Metriken für alle Firmen.

        Args:
            db: Datenbank-Session
            include_inactive: Auch inaktive Firmen einbeziehen

        Returns:
            Liste von CompanyMetrics
        """
        # Lade alle Companies
        query = select(Company)
        if not include_inactive:
            query = query.where(Company.is_active == True)

        result = await db.execute(query)
        companies = result.scalars().all()

        metrics_list = []
        for company in companies:
            try:
                metrics = await self.get_company_metrics(db, company.id)
                metrics_list.append(metrics)
            except Exception as e:
                logger.warning(
                    "company_metrics_error",
                    company_id=str(company.id),
                    **safe_error_log(e),
                )

        # Sortiere nach Health Score (schlechteste zuerst für Attention)
        metrics_list.sort(key=lambda m: m.health_score)

        return metrics_list

    async def get_dashboard_summary(
        self,
        db: AsyncSession,
    ) -> DashboardSummary:
        """
        Holt Zusammenfassung aller Firmen-Metriken.

        Args:
            db: Datenbank-Session

        Returns:
            DashboardSummary mit aggregierten Werten
        """
        summary = DashboardSummary()

        # Company-Zaehlung
        total_query = select(func.count(Company.id))
        active_query = select(func.count(Company.id)).where(Company.is_active == True)

        total_result = await db.execute(total_query)
        active_result = await db.execute(active_query)

        summary.total_companies = total_result.scalar() or 0
        summary.active_companies = active_result.scalar() or 0

        # Dokumente gesamt
        doc_query = select(func.count(Document.id))
        doc_result = await db.execute(doc_query)
        summary.total_documents = doc_result.scalar() or 0

        # Rechnungen
        invoice_query = select(
            func.count(InvoiceTracking.id),
            func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0),
        )
        invoice_result = await db.execute(invoice_query)
        row = invoice_result.one()
        summary.total_invoices = row[0] or 0
        summary.total_outstanding_amount = Decimal(str(row[1] or 0))

        # Überfällige
        today = date.today()
        overdue_query = select(
            func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0)
        ).where(
            and_(
                InvoiceTracking.due_date < today,
                InvoiceTracking.outstanding_amount > 0,
            )
        )
        overdue_result = await db.execute(overdue_query)
        summary.total_overdue_amount = Decimal(str(overdue_result.scalar() or 0))

        # Entities
        entity_query = select(func.count(BusinessEntity.id))
        entity_result = await db.execute(entity_query)
        summary.total_entities = entity_result.scalar() or 0

        # Aktive Mahnungen
        dunning_query = select(func.count(DunningRecord.id)).where(
            DunningRecord.status == "pending"
        )
        dunning_result = await db.execute(dunning_query)
        summary.active_dunnings = dunning_result.scalar() or 0

        return summary

    async def get_company_comparison(
        self,
        db: AsyncSession,
        company_ids: Optional[List[UUID]] = None,
        metric: str = "invoices",
    ) -> List[Dict[str, Any]]:
        """
        Vergleicht Metriken zwischen Firmen.

        Args:
            db: Datenbank-Session
            company_ids: Liste von Company-IDs (None = alle)
            metric: Metrik für Vergleich (invoices, documents, entities, dunning)

        Returns:
            Liste von Vergleichsdaten
        """
        # Lade Firmen
        query = select(Company)
        if company_ids:
            query = query.where(Company.id.in_(company_ids))
        else:
            query = query.where(Company.is_active == True)

        result = await db.execute(query)
        companies = result.scalars().all()

        comparison_data = []

        for company in companies:
            metrics = await self.get_company_metrics(db, company.id)
            comparison_data.append({
                "company_id": str(company.id),
                "company_name": company.name,
                "company_short_name": company.short_name,
                "metric_type": metric,
                "value": self._get_comparison_value(metrics, metric),
                "details": self._get_comparison_details(metrics, metric),
            })

        # Sortiere nach Wert (hoechster zuerst)
        comparison_data.sort(key=lambda x: x["value"], reverse=True)

        return comparison_data

    # =========================================================================
    # Private Methoden für Metrik-Sammlung
    # =========================================================================

    async def _get_document_metrics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> CompanyDocumentMetrics:
        """Sammelt Dokument-Metriken."""
        metrics = CompanyDocumentMetrics()

        today = date.today()
        first_of_month = today.replace(day=1)
        first_of_last_month = (first_of_month - timedelta(days=1)).replace(day=1)

        # Total
        total_query = select(func.count(Document.id)).where(
            Document.company_id == company_id
        )
        total_result = await db.execute(total_query)
        metrics.total_documents = total_result.scalar() or 0

        # This month
        this_month_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= first_of_month,
            )
        )
        this_month_result = await db.execute(this_month_query)
        metrics.documents_this_month = this_month_result.scalar() or 0

        # Last month
        last_month_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= first_of_last_month,
                Document.created_at < first_of_month,
            )
        )
        last_month_result = await db.execute(last_month_query)
        metrics.documents_last_month = last_month_result.scalar() or 0

        # Growth
        if metrics.documents_last_month > 0:
            metrics.document_growth_percent = (
                (metrics.documents_this_month - metrics.documents_last_month)
                / metrics.documents_last_month
            ) * 100

        return metrics

    async def _get_invoice_metrics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> CompanyInvoiceMetrics:
        """Sammelt Rechnungs-Metriken."""
        metrics = CompanyInvoiceMetrics()

        today = date.today()

        # Basis-Query mit Company-Filter über Document
        base_query = (
            select(InvoiceTracking)
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(Document.company_id == company_id)
        )

        # Aggregationen
        agg_query = (
            select(
                func.count(InvoiceTracking.id),
                func.coalesce(func.sum(InvoiceTracking.total_amount), 0),
                func.coalesce(
                    func.sum(
                        InvoiceTracking.total_amount - InvoiceTracking.outstanding_amount
                    ),
                    0,
                ),
                func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0),
            )
            .select_from(InvoiceTracking)
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(Document.company_id == company_id)
        )

        result = await db.execute(agg_query)
        row = result.one()

        metrics.total_invoices = row[0] or 0
        metrics.total_amount = Decimal(str(row[1] or 0))
        metrics.paid_amount = Decimal(str(row[2] or 0))
        metrics.outstanding_amount = Decimal(str(row[3] or 0))

        # Überfällige
        overdue_query = (
            select(
                func.count(InvoiceTracking.id),
                func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0),
            )
            .select_from(InvoiceTracking)
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    InvoiceTracking.due_date < today,
                    InvoiceTracking.outstanding_amount > 0,
                )
            )
        )

        overdue_result = await db.execute(overdue_query)
        overdue_row = overdue_result.one()

        metrics.overdue_count = overdue_row[0] or 0
        metrics.overdue_amount = Decimal(str(overdue_row[1] or 0))

        # Durchschnittliche Zahlungstage (nur bezahlte Rechnungen)
        # Verwendet InvoiceTracking.paid_at (datetime) und invoice_date (date)
        payment_days_query = (
            select(
                func.avg(
                    func.extract('epoch', InvoiceTracking.paid_at) / 86400 -
                    func.extract('epoch', func.cast(InvoiceTracking.invoice_date, InvoiceTracking.paid_at.type)) / 86400
                )
            )
            .select_from(InvoiceTracking)
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at.isnot(None),
                    InvoiceTracking.invoice_date.isnot(None),
                )
            )
        )
        payment_days_result = await db.execute(payment_days_query)
        avg_payment_days = payment_days_result.scalar()
        if avg_payment_days is not None:
            metrics.average_payment_days = round(float(avg_payment_days), 1)

        return metrics

    async def _get_entity_metrics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> CompanyEntityMetrics:
        """Sammelt Geschäftspartner-Metriken."""
        metrics = CompanyEntityMetrics()

        # Total
        total_query = select(func.count(BusinessEntity.id)).where(
            BusinessEntity.company_id == company_id
        )
        total_result = await db.execute(total_query)
        metrics.total_entities = total_result.scalar() or 0

        # Kunden vs Lieferanten (basierend auf entity_type)
        customer_query = select(func.count(BusinessEntity.id)).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.entity_type == "customer",
            )
        )
        customer_result = await db.execute(customer_query)
        metrics.customers = customer_result.scalar() or 0

        supplier_query = select(func.count(BusinessEntity.id)).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.entity_type == "supplier",
            )
        )
        supplier_result = await db.execute(supplier_query)
        metrics.suppliers = supplier_result.scalar() or 0

        # High-Risk (risk_score >= 75)
        high_risk_query = select(func.count(BusinessEntity.id)).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.risk_score >= 75,
            )
        )
        high_risk_result = await db.execute(high_risk_query)
        metrics.high_risk_entities = high_risk_result.scalar() or 0

        return metrics

    async def _get_dunning_metrics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> CompanyDunningMetrics:
        """Sammelt Mahnwesen-Metriken."""
        metrics = CompanyDunningMetrics()

        # Aktive Mahnungen mit Company-Filter über Document
        active_query = (
            select(
                func.count(DunningRecord.id),
                func.coalesce(func.sum(DunningRecord.total_with_fees), 0),
            )
            .select_from(DunningRecord)
            .join(Document, Document.id == DunningRecord.document_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    DunningRecord.status == "pending",
                )
            )
        )

        result = await db.execute(active_query)
        row = result.one()

        metrics.active_dunnings = row[0] or 0
        metrics.total_dunning_amount = Decimal(str(row[1] or 0))

        # Nach Level aufschluesseln
        for level in range(1, 5):
            level_query = (
                select(func.count(DunningRecord.id))
                .select_from(DunningRecord)
                .join(Document, Document.id == DunningRecord.document_id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        DunningRecord.status == "pending",
                        DunningRecord.dunning_level == level,
                    )
                )
            )
            level_result = await db.execute(level_query)
            count = level_result.scalar() or 0

            if level == 1:
                metrics.level_1_count = count
            elif level == 2:
                metrics.level_2_count = count
            elif level == 3:
                metrics.level_3_count = count
            elif level == 4:
                metrics.level_4_count = count

        return metrics

    async def _get_banking_metrics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> CompanyBankingMetrics:
        """Sammelt Banking-Metriken."""
        metrics = CompanyBankingMetrics()

        today = date.today()
        first_of_month = today.replace(day=1)

        # Einnahmen diesen Monat
        incoming_query = (
            select(func.coalesce(func.sum(BankTransaction.amount), 0))
            .where(
                and_(
                    BankTransaction.company_id == company_id,
                    BankTransaction.amount > 0,
                    BankTransaction.booking_date >= first_of_month,
                )
            )
        )
        incoming_result = await db.execute(incoming_query)
        metrics.incoming_this_month = Decimal(str(incoming_result.scalar() or 0))

        # Ausgaben diesen Monat
        outgoing_query = (
            select(func.coalesce(func.sum(func.abs(BankTransaction.amount)), 0))
            .where(
                and_(
                    BankTransaction.company_id == company_id,
                    BankTransaction.amount < 0,
                    BankTransaction.booking_date >= first_of_month,
                )
            )
        )
        outgoing_result = await db.execute(outgoing_query)
        metrics.outgoing_this_month = Decimal(str(outgoing_result.scalar() or 0))

        # Ungematchte Transaktionen
        unmatched_query = (
            select(func.count(BankTransaction.id))
            .where(
                and_(
                    BankTransaction.company_id == company_id,
                    BankTransaction.matched_document_id.is_(None),
                )
            )
        )
        unmatched_result = await db.execute(unmatched_query)
        metrics.unmatched_transactions = unmatched_result.scalar() or 0

        return metrics

    def _calculate_health_score(self, metrics: CompanyMetrics) -> int:
        """
        Berechnet den Health Score (0-100) für eine Firma.

        Faktoren:
        - Überfällige Rechnungen (-30 max)
        - High-Risk Entities (-20 max)
        - Aktive Mahnungen Level 3/4 (-20 max)
        - Ungematchte Transaktionen (-10 max)
        - Dokument-Wachstum (+10 max)
        """
        score = 100

        # Überfällige Rechnungen
        if metrics.invoices.overdue_count > 0:
            overdue_ratio = metrics.invoices.overdue_count / max(
                metrics.invoices.total_invoices, 1
            )
            score -= min(30, int(overdue_ratio * 100))

        # High-Risk Entities
        if metrics.entities.high_risk_entities > 0:
            risk_ratio = metrics.entities.high_risk_entities / max(
                metrics.entities.total_entities, 1
            )
            score -= min(20, int(risk_ratio * 100))

        # Mahnungen Level 3/4
        serious_dunnings = metrics.dunning.level_3_count + metrics.dunning.level_4_count
        if serious_dunnings > 0:
            score -= min(20, serious_dunnings * 5)

        # Ungematchte Transaktionen
        if metrics.banking.unmatched_transactions > 10:
            score -= min(10, (metrics.banking.unmatched_transactions - 10) // 5)

        # Dokument-Wachstum (positiver Bonus)
        if metrics.documents.document_growth_percent > 0:
            score += min(10, int(metrics.documents.document_growth_percent / 10))

        return max(0, min(100, score))

    def _get_comparison_value(self, metrics: CompanyMetrics, metric: str) -> float:
        """Holt den Vergleichswert für eine Metrik."""
        if metric == "invoices":
            return float(metrics.invoices.total_amount)
        elif metric == "documents":
            return float(metrics.documents.total_documents)
        elif metric == "entities":
            return float(metrics.entities.total_entities)
        elif metric == "dunning":
            return float(metrics.dunning.total_dunning_amount)
        elif metric == "outstanding":
            return float(metrics.invoices.outstanding_amount)
        elif metric == "overdue":
            return float(metrics.invoices.overdue_amount)
        elif metric == "health":
            return float(metrics.health_score)
        else:
            return 0.0

    def _get_comparison_details(
        self, metrics: CompanyMetrics, metric: str
    ) -> Dict[str, Any]:
        """Holt zusätzliche Details für einen Vergleich."""
        if metric == "invoices":
            return {
                "total_count": metrics.invoices.total_invoices,
                "paid_amount": float(metrics.invoices.paid_amount),
                "outstanding_amount": float(metrics.invoices.outstanding_amount),
            }
        elif metric == "documents":
            return {
                "this_month": metrics.documents.documents_this_month,
                "growth_percent": metrics.documents.document_growth_percent,
            }
        elif metric == "entities":
            return {
                "customers": metrics.entities.customers,
                "suppliers": metrics.entities.suppliers,
                "high_risk": metrics.entities.high_risk_entities,
            }
        elif metric == "dunning":
            return {
                "active_count": metrics.dunning.active_dunnings,
                "by_level": {
                    "1": metrics.dunning.level_1_count,
                    "2": metrics.dunning.level_2_count,
                    "3": metrics.dunning.level_3_count,
                    "4": metrics.dunning.level_4_count,
                },
            }
        else:
            return {}


# Singleton-Instanz
company_metrics_service = CompanyMetricsService()
