# -*- coding: utf-8 -*-
"""
Smart Dashboard Service für Ablage-System.

Echtzeit-KPIs berechnet aus echten Tabellen:
- InvoiceTracking: Offene Rechnungen, Betraege
- Document: Heutige Dokumente, OCR-Stats
- ProcessingJob: Queue-Länge, Fehlerraten
- ApprovalRequest: Ausstehende Genehmigungen
- Alert: Aktive Alerts

Tabs: Übersicht | Finanzen | Dokumente | Workflows | System
Jeder Tab hat spezifische Widgets die rollen-abhängig gefiltert werden.

Feinpoliert und durchdacht - Enterprise Smart Dashboard.
"""

from datetime import timedelta
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    Document,
    InvoiceTracking,
    InvoiceStatus,
    ProcessingJob,
    ProcessingStatus,
)
from app.db.models_smart_dashboard import (
    DashboardKPI,
    DashboardLayout,
    DashboardTab,
    DashboardWidget,
    DocumentProgressTracker,
    SmartDashboardConfig,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Rollen-Widget-Mapping
# =============================================================================

ROLE_WIDGETS: Dict[str, List[Dict[str, str]]] = {
    "buchhaltung": [
        {"key": "open_invoices", "label": "Offene Rechnungen", "type": "kpi_card"},
        {"key": "payment_runs", "label": "Zahlungslaeufe", "type": "table"},
        {"key": "dunning_status", "label": "Mahnungen", "type": "kpi_card"},
        {"key": "skonto_opportunities", "label": "Skonto-Möglichkeiten", "type": "table"},
        {"key": "aging_report", "label": "Fälligkeitsanalyse", "type": "chart_bar"},
        {"key": "cashflow_overview", "label": "Cashflow", "type": "chart_line"},
    ],
    "geschäftsführung": [
        {"key": "health_score", "label": "Gesundheits-Score", "type": "kpi_card"},
        {"key": "cashflow_chart", "label": "Cashflow-Entwicklung", "type": "chart_line"},
        {"key": "anomaly_alerts", "label": "Anomalien", "type": "alert_summary"},
        {"key": "revenue_trend", "label": "Umsatz-Trend", "type": "chart_line"},
        {"key": "kpi_overview", "label": "KPI-Übersicht", "type": "kpi_card"},
        {"key": "risk_entities", "label": "Risiko-Entitäten", "type": "table"},
    ],
    "sachbearbeitung": [
        {"key": "inbox_queue", "label": "Eingangs-Warteschlange", "type": "queue_status"},
        {"key": "pending_review", "label": "Zu prüfende Dokumente", "type": "table"},
        {"key": "my_tasks", "label": "Meine Aufgaben", "type": "table"},
        {"key": "recent_documents", "label": "Letzte Dokumente", "type": "activity_feed"},
        {"key": "ocr_status", "label": "OCR-Status", "type": "progress_list"},
    ],
}


# =============================================================================
# Smart Dashboard Service
# =============================================================================

class SmartDashboardService:
    """Smart Dashboard - Echtzeit-KPIs aus echten Tabellen mit Tab-Struktur."""

    # =========================================================================
    # Core KPI Methods (query REAL tables)
    # =========================================================================

    async def get_realtime_kpis(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, Dict[str, object]]:
        """Berechnet aktuelle KPIs direkt aus den echten Tabellen.

        Queries InvoiceTracking, Document, ProcessingJob, ApprovalRequest.

        Args:
            db: Async Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Dictionary mit KPI-Key als Schluessel und KPI-Daten als Wert
        """
        logger.info(
            "smart_dashboard.get_realtime_kpis",
            company_id=str(company_id),
        )

        now = utc_now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        kpis: Dict[str, Dict[str, object]] = {}

        # --- Offene Rechnungen (InvoiceTracking via Document.company_id) ---
        try:
            open_invoice_stmt = (
                select(
                    func.count(InvoiceTracking.id).label("count"),
                    func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("total"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.status.in_([
                            InvoiceStatus.OPEN.value,
                            InvoiceStatus.SENT.value,
                            InvoiceStatus.PARTIAL.value,
                        ]),
                    )
                )
            )
            result = await db.execute(open_invoice_stmt)
            row = result.one()
            open_count = row.count or 0
            open_amount = float(row.total or 0.0)

            kpis["offene_rechnungen_anzahl"] = {
                "kpi_key": "offene_rechnungen_anzahl",
                "current_value": open_count,
                "unit": "count",
                "trend_direction": "stable",
                "metadata": {"label": "Offene Rechnungen"},
            }
            kpis["offene_rechnungen_summe"] = {
                "kpi_key": "offene_rechnungen_summe",
                "current_value": round(open_amount, 2),
                "unit": "EUR",
                "trend_direction": "stable",
                "metadata": {"label": "Offener Betrag"},
            }
        except Exception as e:
            logger.warning("smart_dashboard.kpi_invoice_error", error_type=type(e).__name__)
            kpis["offene_rechnungen_anzahl"] = self._default_kpi("offene_rechnungen_anzahl", 0, "count", "Offene Rechnungen")
            kpis["offene_rechnungen_summe"] = self._default_kpi("offene_rechnungen_summe", 0, "EUR", "Offener Betrag")

        # --- OCR Queue Länge (ProcessingJob queued/processing) ---
        try:
            queue_stmt = (
                select(func.count(ProcessingJob.id))
                .join(Document, ProcessingJob.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        ProcessingJob.status.in_([
                            ProcessingStatus.QUEUED.value,
                            ProcessingStatus.PROCESSING.value,
                        ]),
                    )
                )
            )
            result = await db.execute(queue_stmt)
            queue_len = result.scalar() or 0

            kpis["ocr_queue_länge"] = {
                "kpi_key": "ocr_queue_länge",
                "current_value": queue_len,
                "unit": "count",
                "trend_direction": "stable",
                "metadata": {"label": "OCR-Warteschlange"},
            }
        except Exception as e:
            logger.warning("smart_dashboard.kpi_queue_error", error_type=type(e).__name__)
            kpis["ocr_queue_länge"] = self._default_kpi("ocr_queue_länge", 0, "count", "OCR-Warteschlange")

        # --- Cashflow (bezahlte Rechnungen letzte 30 Tage) ---
        try:
            thirty_days_ago = now - timedelta(days=30)
            cashflow_stmt = (
                select(func.coalesce(func.sum(InvoiceTracking.paid_amount), 0.0))
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.paid_at >= thirty_days_ago,
                        InvoiceTracking.status == InvoiceStatus.PAID.value,
                    )
                )
            )
            result = await db.execute(cashflow_stmt)
            cashflow = float(result.scalar() or 0.0)

            kpis["cashflow_aktuell"] = {
                "kpi_key": "cashflow_aktuell",
                "current_value": round(cashflow, 2),
                "unit": "EUR",
                "trend_direction": "stable",
                "metadata": {"label": "Cashflow (30 Tage)"},
            }
        except Exception as e:
            logger.warning("smart_dashboard.kpi_cashflow_error", error_type=type(e).__name__)
            kpis["cashflow_aktuell"] = self._default_kpi("cashflow_aktuell", 0, "EUR", "Cashflow (30 Tage)")

        # --- Dokumente heute ---
        try:
            docs_today_stmt = (
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.created_at >= today_start,
                    )
                )
            )
            result = await db.execute(docs_today_stmt)
            docs_today = result.scalar() or 0

            kpis["dokumente_heute"] = {
                "kpi_key": "dokumente_heute",
                "current_value": docs_today,
                "unit": "count",
                "trend_direction": "stable",
                "metadata": {"label": "Dokumente heute"},
            }
        except Exception as e:
            logger.warning("smart_dashboard.kpi_docs_error", error_type=type(e).__name__)
            kpis["dokumente_heute"] = self._default_kpi("dokumente_heute", 0, "count", "Dokumente heute")

        # --- Ausstehende Genehmigungen ---
        try:
            from app.db.models import ApprovalRequest
            approvals_stmt = (
                select(func.count(ApprovalRequest.id))
                .where(
                    and_(
                        ApprovalRequest.company_id == company_id,
                        ApprovalRequest.status == "pending",
                    )
                )
            )
            result = await db.execute(approvals_stmt)
            pending_approvals = result.scalar() or 0

            kpis["genehmigungen_ausstehend"] = {
                "kpi_key": "genehmigungen_ausstehend",
                "current_value": pending_approvals,
                "unit": "count",
                "trend_direction": "stable",
                "metadata": {"label": "Ausstehende Genehmigungen"},
            }
        except Exception as e:
            logger.warning("smart_dashboard.kpi_approvals_error", error_type=type(e).__name__)
            kpis["genehmigungen_ausstehend"] = self._default_kpi("genehmigungen_ausstehend", 0, "count", "Ausstehende Genehmigungen")

        return kpis

    # =========================================================================
    # Tab Data Methods
    # =========================================================================

    async def get_tab_data(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        tab: DashboardTab,
        role: Optional[str] = None,
    ) -> Dict[str, object]:
        """Daten für einen spezifischen Dashboard-Tab."""
        logger.info(
            "smart_dashboard.get_tab_data",
            company_id=str(company_id),
            tab=tab.value,
        )

        widgets = await self._get_tab_widgets(db, company_id, tab, role)

        if tab == DashboardTab.OVERVIEW:
            data = await self._get_overview_data(db, company_id)
        elif tab == DashboardTab.FINANCE:
            data = await self.get_finance_tab(db, company_id)
        elif tab == DashboardTab.DOCUMENTS:
            data = await self.get_documents_tab(db, company_id)
        elif tab == DashboardTab.WORKFLOWS:
            data = await self.get_workflows_tab(db, company_id)
        elif tab == DashboardTab.SYSTEM:
            data = await self.get_system_tab(db, company_id)
        else:
            data = {}

        data["tab"] = tab.value
        data["widgets"] = [w.to_dict() for w in widgets]
        return data

    async def get_finance_tab(
        self, db: AsyncSession, company_id: UUID,
    ) -> Dict[str, object]:
        """Finanzen-Tab: Offene Posten, Cashflow-Trend, Skonto, Mahnstatus."""
        now = utc_now()

        # Offene Posten nach Status
        try:
            status_stmt = (
                select(
                    InvoiceTracking.status,
                    func.count(InvoiceTracking.id).label("count"),
                    func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("total"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(and_(Document.company_id == company_id, Document.deleted_at.is_(None)))
                .group_by(InvoiceTracking.status)
            )
            result = await db.execute(status_stmt)
            status_breakdown = {
                row.status: {"count": row.count, "total": round(float(row.total), 2)}
                for row in result.all()
            }
        except Exception as e:
            logger.warning("smart_dashboard.finance_status_error", error_type=type(e).__name__)
            status_breakdown = {}

        # Überfällige
        try:
            overdue_stmt = (
                select(
                    func.count(InvoiceTracking.id).label("count"),
                    func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("total"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.due_date < now,
                        InvoiceTracking.status.in_([
                            InvoiceStatus.OPEN.value, InvoiceStatus.SENT.value, InvoiceStatus.OVERDUE.value,
                        ]),
                    )
                )
            )
            result = await db.execute(overdue_stmt)
            overdue_row = result.one()
            overdue_data = {"count": overdue_row.count or 0, "total": round(float(overdue_row.total or 0.0), 2)}
        except Exception as e:
            logger.warning("smart_dashboard.finance_overdue_error", error_type=type(e).__name__)
            overdue_data = {"count": 0, "total": 0.0}

        # Skonto-Potential (nächste 7 Tage)
        try:
            skonto_deadline = now + timedelta(days=7)
            skonto_stmt = (
                select(
                    func.count(InvoiceTracking.id).label("count"),
                    func.coalesce(func.sum(InvoiceTracking.skonto_amount), 0.0).label("savings"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.skonto_deadline.isnot(None),
                        InvoiceTracking.skonto_deadline > now,
                        InvoiceTracking.skonto_deadline <= skonto_deadline,
                        InvoiceTracking.skonto_used.is_(False),
                        InvoiceTracking.status.in_([InvoiceStatus.OPEN.value, InvoiceStatus.SENT.value]),
                    )
                )
            )
            result = await db.execute(skonto_stmt)
            skonto_row = result.one()
            skonto_data = {"count": skonto_row.count or 0, "potential_savings": round(float(skonto_row.savings or 0.0), 2)}
        except Exception as e:
            logger.warning("smart_dashboard.finance_skonto_error", error_type=type(e).__name__)
            skonto_data = {"count": 0, "potential_savings": 0.0}

        # Mahnstatus
        try:
            dunning_stmt = (
                select(func.count(InvoiceTracking.id))
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.status == InvoiceStatus.DUNNING.value,
                    )
                )
            )
            result = await db.execute(dunning_stmt)
            dunning_count = result.scalar() or 0
        except Exception as e:
            logger.warning("smart_dashboard.finance_dunning_error", error_type=type(e).__name__)
            dunning_count = 0

        # Aging Buckets (Fälligkeitsverteilung)
        aging_buckets: List[Dict[str, object]] = []
        try:
            aging_stmt = (
                select(
                    case(
                        (InvoiceTracking.due_date >= now, "nicht_fällig"),
                        (func.extract("day", now - InvoiceTracking.due_date) <= 30, "1_30_tage"),
                        (func.extract("day", now - InvoiceTracking.due_date) <= 60, "31_60_tage"),
                        (func.extract("day", now - InvoiceTracking.due_date) <= 90, "61_90_tage"),
                        else_="über_90_tage",
                    ).label("bucket"),
                    func.count(InvoiceTracking.id).label("count"),
                    func.coalesce(func.sum(InvoiceTracking.amount), 0.0).label("amount"),
                )
                .join(Document, InvoiceTracking.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        InvoiceTracking.paid_at.is_(None),
                        InvoiceTracking.due_date.isnot(None),
                        InvoiceTracking.status.in_([
                            InvoiceStatus.OPEN.value,
                            InvoiceStatus.SENT.value,
                            InvoiceStatus.PARTIAL.value,
                            InvoiceStatus.OVERDUE.value,
                        ]),
                    )
                )
                .group_by("bucket")
            )
            result = await db.execute(aging_stmt)
            bucket_labels = {
                "nicht_fällig": "Nicht fällig",
                "1_30_tage": "1-30 Tage",
                "31_60_tage": "31-60 Tage",
                "61_90_tage": "61-90 Tage",
                "über_90_tage": "Über 90 Tage",
            }
            for row in result.all():
                aging_buckets.append({
                    "bucket": bucket_labels.get(row.bucket, row.bucket),
                    "count": row.count or 0,
                    "amount": round(float(row.amount or 0.0), 2),
                })
        except Exception as e:
            logger.warning("smart_dashboard.finance_aging_error", error_type=type(e).__name__)

        # Dunning Stages (Mahnstufen-Verteilung)
        dunning_stages: List[Dict[str, object]] = []
        try:
            from app.db.models import DunningRecord
            stages_stmt = (
                select(
                    DunningRecord.dunning_level.label("stage"),
                    func.count(DunningRecord.id).label("count"),
                )
                .join(Document, DunningRecord.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        DunningRecord.status.notin_(["closed", "written_off"]),
                    )
                )
                .group_by(DunningRecord.dunning_level)
                .order_by(DunningRecord.dunning_level)
            )
            result = await db.execute(stages_stmt)
            for row in result.all():
                dunning_stages.append({
                    "stage": row.stage or 0,
                    "count": row.count or 0,
                })
        except Exception as e:
            logger.warning("smart_dashboard.finance_dunning_stages_error", error_type=type(e).__name__)

        return {
            "offene_posten": status_breakdown,
            "überfällige_rechnungen": overdue_data,
            "skonto_übersicht": skonto_data,
            "mahnungen_aktiv": dunning_count,
            "aging_buckets": aging_buckets,
            "dunning_stages": dunning_stages,
        }

    async def get_documents_tab(
        self, db: AsyncSession, company_id: UUID,
    ) -> Dict[str, object]:
        """Dokumente-Tab: OCR-Queue, zuletzt verarbeitet, Fehlerrate, Klassifikation."""
        now = utc_now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = now - timedelta(days=7)

        # OCR-Queue
        try:
            queue_stmt = (
                select(ProcessingJob.status, func.count(ProcessingJob.id).label("count"))
                .join(Document, ProcessingJob.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        ProcessingJob.status.in_([
                            ProcessingStatus.QUEUED.value, ProcessingStatus.PROCESSING.value, ProcessingStatus.PENDING.value,
                        ]),
                    )
                )
                .group_by(ProcessingJob.status)
            )
            result = await db.execute(queue_stmt)
            queue_breakdown = {row.status: row.count for row in result.all()}
        except Exception as e:
            logger.warning("smart_dashboard.docs_queue_error", error_type=type(e).__name__)
            queue_breakdown = {}

        # Kürzlich verarbeitet (heute)
        try:
            recent_stmt = (
                select(
                    Document.id, Document.original_filename, Document.document_type,
                    Document.status, Document.ocr_confidence, Document.processing_duration_ms, Document.created_at,
                )
                .where(
                    and_(
                        Document.company_id == company_id, Document.deleted_at.is_(None),
                        Document.status == ProcessingStatus.COMPLETED.value, Document.processed_date >= today_start,
                    )
                )
                .order_by(Document.processed_date.desc()).limit(20)
            )
            result = await db.execute(recent_stmt)
            recently_processed = [
                {
                    "id": str(row.id), "filename": row.original_filename,
                    "document_type": row.document_type, "status": row.status,
                    "confidence": round(row.ocr_confidence, 2) if row.ocr_confidence else None,
                    "duration_ms": row.processing_duration_ms,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in result.all()
            ]
        except Exception as e:
            logger.warning("smart_dashboard.docs_recent_error", error_type=type(e).__name__)
            recently_processed = []

        # Fehlerrate (7 Tage)
        try:
            error_stmt = (
                select(
                    func.count(ProcessingJob.id).label("total"),
                    func.count(case((ProcessingJob.status == ProcessingStatus.FAILED.value, ProcessingJob.id))).label("failed"),
                )
                .join(Document, ProcessingJob.document_id == Document.id)
                .where(and_(Document.company_id == company_id, ProcessingJob.created_at >= seven_days_ago))
            )
            result = await db.execute(error_stmt)
            error_row = result.one()
            total_jobs = error_row.total or 0
            failed_jobs = error_row.failed or 0
            error_rate = round((failed_jobs / total_jobs * 100), 2) if total_jobs > 0 else 0.0
        except Exception as e:
            logger.warning("smart_dashboard.docs_error_rate_error", error_type=type(e).__name__)
            total_jobs, failed_jobs, error_rate = 0, 0, 0.0

        # Klassifikation (7 Tage)
        try:
            classification_stmt = (
                select(Document.document_type, func.count(Document.id).label("count"))
                .where(
                    and_(
                        Document.company_id == company_id, Document.deleted_at.is_(None),
                        Document.created_at >= seven_days_ago,
                    )
                )
                .group_by(Document.document_type).order_by(func.count(Document.id).desc()).limit(10)
            )
            result = await db.execute(classification_stmt)
            classification_stats = {row.document_type: row.count for row in result.all()}
        except Exception as e:
            logger.warning("smart_dashboard.docs_classification_error", error_type=type(e).__name__)
            classification_stats = {}

        return {
            "ocr_queue": queue_breakdown,
            "ocr_queue_gesamt": sum(queue_breakdown.values()),
            "kürzlich_verarbeitet": recently_processed,
            "fehlerrate": {"rate_percent": error_rate, "total_jobs": total_jobs, "failed_jobs": failed_jobs, "zeitraum_tage": 7},
            "klassifikation": classification_stats,
        }

    async def get_workflows_tab(
        self, db: AsyncSession, company_id: UUID,
    ) -> Dict[str, object]:
        """Workflows-Tab: Genehmigungen, SLA-Status."""
        now = utc_now()

        try:
            from app.db.models import ApprovalRequest
            pending_stmt = (
                select(ApprovalRequest.entity_type, func.count(ApprovalRequest.id).label("count"))
                .where(and_(ApprovalRequest.company_id == company_id, ApprovalRequest.status == "pending"))
                .group_by(ApprovalRequest.entity_type)
            )
            result = await db.execute(pending_stmt)
            pending_by_type = {row.entity_type: row.count for row in result.all()}
            total_pending = sum(pending_by_type.values())
        except Exception as e:
            logger.warning("smart_dashboard.workflows_pending_error", error_type=type(e).__name__)
            pending_by_type, total_pending = {}, 0

        try:
            from app.db.models import ApprovalRequest
            overdue_stmt = (
                select(func.count(ApprovalRequest.id))
                .where(and_(ApprovalRequest.company_id == company_id, ApprovalRequest.status == "pending", ApprovalRequest.due_date < now))
            )
            result = await db.execute(overdue_stmt)
            overdue_approvals = result.scalar() or 0
        except Exception as e:
            logger.warning("smart_dashboard.workflows_overdue_error", error_type=type(e).__name__)
            overdue_approvals = 0

        return {
            "ausstehende_genehmigungen": {"gesamt": total_pending, "nach_typ": pending_by_type},
            "überfällige_genehmigungen": overdue_approvals,
        }

    async def get_system_tab(
        self, db: AsyncSession, company_id: UUID,
    ) -> Dict[str, object]:
        """System-Tab: GPU, Queues, Verarbeitungszeiten, Speicher."""
        now = utc_now()

        # Queue-Tiefen
        try:
            queue_stmt = (
                select(ProcessingJob.job_type, ProcessingJob.status, func.count(ProcessingJob.id).label("count"))
                .join(Document, ProcessingJob.document_id == Document.id)
                .where(
                    and_(
                        Document.company_id == company_id,
                        ProcessingJob.status.in_([ProcessingStatus.QUEUED.value, ProcessingStatus.PROCESSING.value]),
                    )
                )
                .group_by(ProcessingJob.job_type, ProcessingJob.status)
            )
            result = await db.execute(queue_stmt)
            queue_depths: Dict[str, Dict[str, int]] = {}
            for row in result.all():
                if row.job_type not in queue_depths:
                    queue_depths[row.job_type] = {}
                queue_depths[row.job_type][row.status] = row.count
        except Exception as e:
            logger.warning("smart_dashboard.system_queue_error", error_type=type(e).__name__)
            queue_depths = {}

        # Durchschnittliche Verarbeitungszeit (24h)
        try:
            yesterday = now - timedelta(hours=24)
            avg_stmt = (
                select(func.avg(Document.processing_duration_ms).label("avg_ms"), func.count(Document.id).label("count"))
                .where(
                    and_(
                        Document.company_id == company_id, Document.deleted_at.is_(None),
                        Document.processed_date >= yesterday, Document.processing_duration_ms.isnot(None),
                    )
                )
            )
            result = await db.execute(avg_stmt)
            avg_row = result.one()
            avg_processing_ms = round(float(avg_row.avg_ms or 0), 0)
            processed_count = avg_row.count or 0
        except Exception as e:
            logger.warning("smart_dashboard.system_avg_error", error_type=type(e).__name__)
            avg_processing_ms, processed_count = 0, 0

        gpu_info = await self._get_gpu_metrics()

        # Speichernutzung
        try:
            storage_stmt = (
                select(func.count(Document.id).label("doc_count"), func.coalesce(func.sum(Document.file_size), 0).label("total_size"))
                .where(and_(Document.company_id == company_id, Document.deleted_at.is_(None)))
            )
            result = await db.execute(storage_stmt)
            storage_row = result.one()
            storage_info = {
                "dokumente_anzahl": storage_row.doc_count or 0,
                "speicher_bytes": storage_row.total_size or 0,
                "speicher_gb": round((storage_row.total_size or 0) / (1024 ** 3), 2),
            }
        except Exception as e:
            logger.warning("smart_dashboard.system_storage_error", error_type=type(e).__name__)
            storage_info = {"dokumente_anzahl": 0, "speicher_bytes": 0, "speicher_gb": 0.0}

        return {
            "queue_tiefen": queue_depths,
            "verarbeitungszeit": {"durchschnitt_ms": avg_processing_ms, "verarbeitete_24h": processed_count},
            "gpu": gpu_info,
            "speicher": storage_info,
        }

    # =========================================================================
    # Layout Management
    # =========================================================================

    async def get_user_layout(
        self, db: AsyncSession, user_id: UUID, company_id: UUID, tab: DashboardTab,
    ) -> Dict[str, object]:
        """Persoenliches Widget-Layout eines Users für einen Tab."""
        stmt = select(DashboardLayout).where(
            and_(DashboardLayout.user_id == user_id, DashboardLayout.company_id == company_id, DashboardLayout.tab == tab.value)
        )
        result = await db.execute(stmt)
        layout = result.scalar_one_or_none()

        if layout:
            return layout.to_dict()

        widgets = await self._get_tab_widgets(db, company_id, tab, role=None)
        default_config = [
            {"widget_id": str(w.id), "x": w.position_x, "y": w.position_y, "w": w.position_w, "h": w.position_h, "visible": True}
            for w in widgets
        ]
        return {"user_id": str(user_id), "company_id": str(company_id), "tab": tab.value, "widgets_config": default_config, "is_custom": False}

    async def save_user_layout(
        self, db: AsyncSession, user_id: UUID, company_id: UUID, tab: DashboardTab, widgets_config: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """Speichert benutzerdefiniertes Widget-Layout."""
        logger.info("smart_dashboard.save_user_layout", user_id=str(user_id), tab=tab.value, widget_count=len(widgets_config))

        stmt = select(DashboardLayout).where(
            and_(DashboardLayout.user_id == user_id, DashboardLayout.company_id == company_id, DashboardLayout.tab == tab.value)
        )
        result = await db.execute(stmt)
        layout = result.scalar_one_or_none()

        if layout:
            layout.widgets_config = widgets_config
            layout.is_custom = True
            layout.updated_at = utc_now()
        else:
            layout = DashboardLayout(user_id=user_id, company_id=company_id, tab=tab.value, widgets_config=widgets_config, is_custom=True)
            db.add(layout)

        await db.flush()
        return layout.to_dict()

    # =========================================================================
    # Legacy API
    # =========================================================================

    async def get_role_widgets(self, role: str) -> List[Dict[str, str]]:
        """Widget-Liste basierend auf Benutzerrolle."""
        return ROLE_WIDGETS.get(role, ROLE_WIDGETS.get("sachbearbeitung", []))

    async def save_layout(
        self, db: AsyncSession, company_id: UUID, user_id: UUID, tab: DashboardTab, layout: Dict[str, object],
    ) -> SmartDashboardConfig:
        """Benutzerdefiniertes Widget-Layout speichern (Legacy)."""
        stmt = select(SmartDashboardConfig).where(and_(SmartDashboardConfig.company_id == company_id, SmartDashboardConfig.user_id == user_id))
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if config:
            existing_layout = config.widget_layout or {}
            existing_layout[tab.value] = layout
            config.widget_layout = existing_layout
            config.active_tab = tab.value
            config.updated_at = utc_now()
        else:
            config = SmartDashboardConfig(company_id=company_id, user_id=user_id, active_tab=tab.value, widget_layout={tab.value: layout})
            db.add(config)

        await db.flush()
        return config

    async def calculate_kpi_trends(self, db: AsyncSession, company_id: UUID) -> Dict[str, Dict[str, object]]:
        """KPI-Trends berechnen (Vergleich mit Vorperiode)."""
        now = utc_now()
        yesterday = now - timedelta(hours=24)
        current_kpis = await self.get_realtime_kpis(db, company_id)

        stmt = select(DashboardKPI).where(
            and_(DashboardKPI.company_id == company_id, DashboardKPI.calculated_at <= yesterday)
        ).order_by(DashboardKPI.calculated_at.desc())
        result = await db.execute(stmt)
        old_kpis = result.scalars().all()

        old_kpi_dict: Dict[str, float] = {}
        for kpi in old_kpis:
            if kpi.kpi_key not in old_kpi_dict:
                old_kpi_dict[kpi.kpi_key] = kpi.current_value

        trends: Dict[str, Dict[str, object]] = {}
        for kpi_key, kpi_data in current_kpis.items():
            current_val = float(kpi_data.get("current_value", 0))
            previous_val = old_kpi_dict.get(kpi_key)
            if previous_val is not None and previous_val != 0:
                change_pct = ((current_val - previous_val) / abs(previous_val)) * 100
                direction = "up" if change_pct > 1.0 else ("down" if change_pct < -1.0 else "stable")
            else:
                change_pct, direction = 0.0, "stable"
            trends[kpi_key] = {"kpi_key": kpi_key, "current_value": current_val, "previous_value": previous_val, "change_percent": round(change_pct, 2), "direction": direction, "unit": kpi_data.get("unit", "count")}

        return trends

    async def get_available_widgets(self, db: AsyncSession, company_id: UUID) -> List[Dict[str, object]]:
        """Alle verfügbaren Widget-Typen für eine Firma."""
        stmt = select(DashboardWidget).where(and_(DashboardWidget.company_id == company_id, DashboardWidget.is_active.is_(True))).order_by(DashboardWidget.tab, DashboardWidget.position_y)
        result = await db.execute(stmt)
        widgets = result.scalars().all()
        if not widgets:
            return self._get_default_widget_list()
        return [w.to_dict() for w in widgets]

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    async def _get_tab_widgets(self, db: AsyncSession, company_id: UUID, tab: DashboardTab, role: Optional[str]) -> List[DashboardWidget]:
        """Widgets für einen Tab laden, gefiltert nach Rolle."""
        stmt = (
            select(DashboardWidget)
            .where(and_(DashboardWidget.company_id == company_id, DashboardWidget.tab == tab.value, DashboardWidget.is_active.is_(True)))
            .order_by(DashboardWidget.position_y, DashboardWidget.position_x)
        )
        result = await db.execute(stmt)
        widgets = list(result.scalars().all())

        if role and widgets:
            return [w for w in widgets if not w.min_roles or role in (w.min_roles or [])]
        return widgets

    async def _get_overview_data(self, db: AsyncSession, company_id: UUID) -> Dict[str, object]:
        """Übersicht-Tab: Top-KPIs + letzte Aktivitäten."""
        kpis = await self.get_realtime_kpis(db, company_id)

        recent_stmt = (
            select(DocumentProgressTracker).where(DocumentProgressTracker.company_id == company_id)
            .order_by(DocumentProgressTracker.updated_at.desc()).limit(10)
        )
        result = await db.execute(recent_stmt)
        recent_progress = [r.to_dict() for r in result.scalars().all()]

        return {
            "kpis": kpis,
            "letzte_aktivitäten": recent_progress,
            "zusammenfassung": {
                "dokumente_heute": kpis.get("dokumente_heute", {}).get("current_value", 0),
                "offene_rechnungen": kpis.get("offene_rechnungen_anzahl", {}).get("current_value", 0),
                "offener_betrag": kpis.get("offene_rechnungen_summe", {}).get("current_value", 0),
                "ocr_warteschlange": kpis.get("ocr_queue_länge", {}).get("current_value", 0),
                "genehmigungen": kpis.get("genehmigungen_ausstehend", {}).get("current_value", 0),
            },
        }

    @staticmethod
    async def _get_gpu_metrics() -> Dict[str, object]:
        """GPU-Metriken via PyTorch (falls verfügbar)."""
        try:
            import torch
            if torch.cuda.is_available():
                device = torch.cuda.current_device()
                total_mem = torch.cuda.get_device_properties(device).total_mem / (1024 ** 3)
                allocated = torch.cuda.memory_allocated(device) / (1024 ** 3)
                return {
                    "verfügbar": True, "name": torch.cuda.get_device_name(device),
                    "speicher_gesamt_gb": round(total_mem, 2), "speicher_verwendet_gb": round(allocated, 2),
                    "auslastung_prozent": round((allocated / total_mem) * 100, 1) if total_mem > 0 else 0,
                }
        except Exception:
            pass
        return {"verfügbar": False, "name": None, "speicher_gesamt_gb": 0, "speicher_verwendet_gb": 0, "auslastung_prozent": 0}

    @staticmethod
    def _default_kpi(key: str, value: float, unit: str, label: str) -> Dict[str, object]:
        """Erzeugt ein Standard-KPI Dictionary."""
        return {"kpi_key": key, "current_value": value, "unit": unit, "trend_direction": "stable", "metadata": {"label": label}}

    @staticmethod
    def _get_default_widget_list() -> List[Dict[str, object]]:
        """Statische Widget-Liste als Fallback."""
        return [
            {"tab": "overview", "widget_type": "kpi_card", "title": "Offene Rechnungen", "data_source": "get_realtime_kpis"},
            {"tab": "overview", "widget_type": "kpi_card", "title": "Dokumente heute", "data_source": "get_realtime_kpis"},
            {"tab": "overview", "widget_type": "kpi_card", "title": "OCR-Warteschlange", "data_source": "get_realtime_kpis"},
            {"tab": "overview", "widget_type": "activity_feed", "title": "Letzte Aktivitäten", "data_source": "get_tab_data"},
            {"tab": "finance", "widget_type": "kpi_card", "title": "Offener Betrag", "data_source": "get_finance_tab"},
            {"tab": "finance", "widget_type": "chart_bar", "title": "Fälligkeitsanalyse", "data_source": "get_finance_tab"},
            {"tab": "finance", "widget_type": "table", "title": "Skonto-Möglichkeiten", "data_source": "get_finance_tab"},
            {"tab": "documents", "widget_type": "queue_status", "title": "Verarbeitungs-Queue", "data_source": "get_documents_tab"},
            {"tab": "documents", "widget_type": "progress_list", "title": "Aktuelle Verarbeitung", "data_source": "get_documents_tab"},
            {"tab": "workflows", "widget_type": "kpi_card", "title": "Ausstehende Genehmigungen", "data_source": "get_workflows_tab"},
            {"tab": "system", "widget_type": "system_health", "title": "System-Gesundheit", "data_source": "get_system_tab"},
            {"tab": "system", "widget_type": "gauge", "title": "GPU-Auslastung", "data_source": "get_system_tab"},
        ]
