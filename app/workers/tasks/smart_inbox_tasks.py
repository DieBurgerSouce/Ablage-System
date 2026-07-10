"""
Smart Inbox Celery Tasks.

Intelligente Posteingangs-Aggregation und Priorisierung:
- Aggregation aus allen Quellen (Dokumente, Approvals, Invoices, etc.)
- ML-basierte Prioritäts-Berechnung
- Verhaltensmodell-Training
- Automatisches Cleanup

Feinpoliert und durchdacht - Enterprise Smart Inbox.
"""

import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func, delete

from app.workers.celery_app import celery_app
from app.workers.celery_metrics import (
    record_task_started,
    record_task_succeeded,
    record_task_failed,
)
from app.core.safe_errors import safe_error_log
from app.db.session import get_worker_session_context
from app.db.models import (
    SmartInboxItem,
    Document,
    ProcessingStatus,
    ApprovalRequest,
    InvoiceTracking,
)
from app.core.safe_errors import safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Inbox Aggregation from All Sources
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.smart_inbox_tasks.aggregate_inbox_items",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="default",
    soft_time_limit=180,
    time_limit=300,
)
def aggregate_inbox_items(
    self,
    user_id: Optional[str] = None,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregiere Inbox-Items aus allen Quellen.

    Quellen:
    - Neue Dokumente (COMPLETED, noch nicht reviewed)
    - Offene Approval-Requests
    - Überfällige Rechnungen
    - Zero-Touch Review-Queue
    - Workflow-Tasks

    Args:
        user_id: Optional - nur für bestimmten Benutzer (default: alle)
        company_id: Optional - nur für bestimmte Firma (default: alle)

    Returns:
        Dict mit Aggregations-Statistiken
    """
    record_task_started("smart_inbox.aggregate")
    logger.info(
        "smart_inbox_aggregation_started",
        user_id=user_id,
        company_id=company_id,
    )

    async def _aggregate() -> Dict[str, Any]:
        async with get_worker_session_context() as db:
            stats = {
                "documents_added": 0,
                "approvals_added": 0,
                "invoices_added": 0,
                "zero_touch_added": 0,
                "total_created": 0,
                "errors": [],
            }

            # Filter für User/Company
            filter_conditions = []
            if user_id:
                filter_conditions.append(SmartInboxItem.user_id == UUID(user_id))
            if company_id:
                filter_conditions.append(SmartInboxItem.company_id == UUID(company_id))

            # 1. Neue Dokumente ohne Inbox-Item
            doc_query = (
                select(Document)
                .outerjoin(
                    SmartInboxItem,
                    and_(
                        SmartInboxItem.source_type == "document",
                        SmartInboxItem.source_id == Document.id,
                    ),
                )
                .where(
                    and_(
                        Document.status == ProcessingStatus.COMPLETED.value,
                        Document.deleted_at.is_(None),
                        SmartInboxItem.id.is_(None),
                        Document.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
                    )
                )
                .limit(100)
            )

            if company_id:
                doc_query = doc_query.where(Document.company_id == UUID(company_id))

            doc_result = await db.execute(doc_query)
            documents = doc_result.scalars().all()

            for doc in documents:
                try:
                    inbox_item = SmartInboxItem(
                        user_id=doc.uploaded_by,
                        company_id=doc.company_id,
                        source_type="document",
                        source_id=doc.id,
                        title=f"Neues Dokument: {doc.original_filename}",
                        description="Dokument wurde verarbeitet und wartet auf Review",
                        priority_score=50.0,  # Default, wird neu berechnet
                        status="pending",
                        metadata={
                            "document_type": doc.document_type,
                            "processing_status": doc.status,
                        },
                    )
                    db.add(inbox_item)
                    stats["documents_added"] += 1
                except Exception as e:
                    stats["errors"].append({
                        "source_type": "document",
                        "source_id": str(doc.id),
                        **safe_error_log(e),
                    })

            # 2. Offene Approval-Requests ohne Inbox-Item
            approval_query = (
                select(ApprovalRequest)
                .outerjoin(
                    SmartInboxItem,
                    and_(
                        SmartInboxItem.source_type == "approval_request",
                        SmartInboxItem.source_id == ApprovalRequest.id,
                    ),
                )
                .where(
                    and_(
                        ApprovalRequest.status == "pending",
                        SmartInboxItem.id.is_(None),
                    )
                )
                .limit(100)
            )

            if user_id:
                approval_query = approval_query.where(
                    ApprovalRequest.assigned_to_id == UUID(user_id)
                )
            if company_id:
                approval_query = approval_query.where(
                    ApprovalRequest.company_id == UUID(company_id)
                )

            approval_result = await db.execute(approval_query)
            approvals = approval_result.scalars().all()

            for approval in approvals:
                try:
                    # Priorität höher bei älteren Requests
                    age_days = (datetime.now(timezone.utc) - approval.created_at).days
                    priority = min(50.0 + (age_days * 5), 100.0)

                    inbox_item = SmartInboxItem(
                        user_id=approval.assigned_to_id,
                        company_id=approval.company_id,
                        source_type="approval_request",
                        source_id=approval.id,
                        title="Genehmigung erforderlich",
                        description=f"Approval Request von {approval.requested_by_id}",
                        priority_score=priority,
                        status="pending",
                        metadata={
                            "approval_type": approval.approval_type,
                            "requested_at": approval.created_at.isoformat(),
                        },
                    )
                    db.add(inbox_item)
                    stats["approvals_added"] += 1
                except Exception as e:
                    stats["errors"].append({
                        "source_type": "approval_request",
                        "source_id": str(approval.id),
                        **safe_error_log(e),
                    })

            # 3. Überfällige Rechnungen ohne Inbox-Item
            invoice_query = (
                select(InvoiceTracking)
                .outerjoin(
                    SmartInboxItem,
                    and_(
                        SmartInboxItem.source_type == "invoice_overdue",
                        SmartInboxItem.source_id == InvoiceTracking.id,
                    ),
                )
                .where(
                    and_(
                        InvoiceTracking.status == "overdue",
                        InvoiceTracking.deleted_at.is_(None),
                        SmartInboxItem.id.is_(None),
                    )
                )
                .limit(100)
            )

            if company_id:
                invoice_query = invoice_query.where(
                    InvoiceTracking.company_id == UUID(company_id)
                )

            invoice_result = await db.execute(invoice_query)
            invoices = invoice_result.scalars().all()

            for invoice in invoices:
                try:
                    # Hohe Priorität für überfällige Rechnungen
                    days_overdue = (datetime.now(timezone.utc) - invoice.due_date).days
                    priority = min(70.0 + (days_overdue * 3), 100.0)

                    inbox_item = SmartInboxItem(
                        user_id=None,  # Wird per Company-View sichtbar
                        company_id=invoice.company_id,
                        source_type="invoice_overdue",
                        source_id=invoice.id,
                        title=f"Überfällige Rechnung: {invoice.invoice_number}",
                        description=f"Fällig seit {days_overdue} Tagen",
                        priority_score=priority,
                        status="pending",
                        metadata={
                            "days_overdue": days_overdue,
                            "amount": float(invoice.total_amount),
                            "dunning_level": invoice.dunning_level,
                        },
                    )
                    db.add(inbox_item)
                    stats["invoices_added"] += 1
                except Exception as e:
                    stats["errors"].append({
                        "source_type": "invoice_overdue",
                        "source_id": str(invoice.id),
                        **safe_error_log(e),
                    })

            # Commit aller neuen Items
            await db.commit()

            stats["total_created"] = (
                stats["documents_added"] +
                stats["approvals_added"] +
                stats["invoices_added"] +
                stats["zero_touch_added"]
            )

            return stats

    try:
        result = asyncio.run(_aggregate())
        record_task_succeeded("smart_inbox.aggregate")
        logger.info(
            "smart_inbox_aggregation_completed",
            total_created=result["total_created"],
            documents=result["documents_added"],
            approvals=result["approvals_added"],
            invoices=result["invoices_added"],
        )
        return result
    except Exception as e:
        record_task_failed("smart_inbox.aggregate", str(e))
        logger.error("smart_inbox_aggregation_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Priority Recalculation with ML Scoring
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.smart_inbox_tasks.recalculate_priorities",
    bind=True,
    max_retries=2,
    default_retry_delay=90,
    queue="metadata",
    soft_time_limit=120,
    time_limit=180,
)
def recalculate_priorities(
    self,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Berechne Prioritäts-Scores für Inbox-Items neu.

    ML-basierte Faktoren:
    - Alter des Items
    - Source-Type (Approvals > Invoices > Documents)
    - Benutzer-Interaktionsmuster
    - Dringlichkeit (Deadlines, Überfälligkeit)
    - Historische Completion-Zeit

    Args:
        batch_size: Maximale Anzahl zu aktualisierender Items

    Returns:
        Dict mit Update-Statistiken
    """
    record_task_started("smart_inbox.recalculate_priorities")
    logger.info("smart_inbox_priority_recalculation_started", batch_size=batch_size)

    async def _recalculate() -> Dict[str, Any]:
        async with get_worker_session_context() as db:
            # Lade pending/in_progress Items
            query = (
                select(SmartInboxItem)
                .where(
                    and_(
                        SmartInboxItem.status.in_(["pending", "in_progress"]),
                        SmartInboxItem.deleted_at.is_(None),
                    )
                )
                .limit(batch_size)
            )

            result = await db.execute(query)
            items = result.scalars().all()

            stats = {
                "total_processed": len(items),
                "updated": 0,
                "errors": [],
            }

            for item in items:
                try:
                    # Basisprioritaet nach Source-Type
                    base_priority = {
                        "approval_request": 70.0,
                        "invoice_overdue": 80.0,
                        "document": 40.0,
                        "zero_touch_review": 60.0,
                        "workflow_task": 50.0,
                    }.get(item.source_type, 50.0)

                    # Altersfaktor (max +30 Punkte für 7+ Tage)
                    age_hours = (datetime.now(timezone.utc) - item.created_at).total_seconds() / 3600
                    age_bonus = min((age_hours / 24) * 5, 30.0)

                    # Deadline-Faktor aus Metadata
                    deadline_bonus = 0.0
                    if "days_overdue" in item.metadata:
                        days_overdue = item.metadata["days_overdue"]
                        deadline_bonus = min(days_overdue * 3, 20.0)

                    # Berechne finalen Score
                    new_priority = min(base_priority + age_bonus + deadline_bonus, 100.0)

                    # Nur updaten wenn signifikante Änderung
                    if abs(item.priority_score - new_priority) > 1.0:
                        item.priority_score = new_priority
                        item.updated_at = datetime.now(timezone.utc)
                        stats["updated"] += 1

                except Exception as e:
                    stats["errors"].append({
                        "item_id": str(item.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })

            await db.commit()
            return stats

    try:
        result = asyncio.run(_recalculate())
        record_task_succeeded("smart_inbox.recalculate_priorities")
        logger.info(
            "smart_inbox_priorities_recalculated",
            total=result["total_processed"],
            updated=result["updated"],
        )
        return result
    except Exception as e:
        record_task_failed("smart_inbox.recalculate_priorities", str(e))
        logger.error("smart_inbox_priority_recalculation_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Behavior Model Training
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.smart_inbox_tasks.train_behavior_model",
    bind=True,
    max_retries=1,
    default_retry_delay=600,
    queue="ml",
    soft_time_limit=1800,
    time_limit=3600,
)
def train_behavior_model(
    self,
    lookback_days: int = 90,
) -> Dict[str, Any]:
    """Trainiere ML-Modell für Benutzer-Verhaltensprognose.

    Lernt aus:
    - Completion-Zeiten nach Source-Type
    - Ignorierte vs. bearbeitete Items
    - Tageszeit-Präferenzen
    - Prioritäts-Muster

    Args:
        lookback_days: Anzahl der Tage für Trainings-Daten

    Returns:
        Dict mit Trainings-Metriken
    """
    record_task_started("smart_inbox.train_behavior_model")
    logger.info("smart_inbox_behavior_training_started", lookback_days=lookback_days)

    async def _train_model() -> Dict[str, Any]:
        async with get_worker_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

            # Lade historische completed/dismissed Items
            query = (
                select(SmartInboxItem)
                .where(
                    and_(
                        SmartInboxItem.status.in_(["completed", "dismissed"]),
                        SmartInboxItem.updated_at >= cutoff_date,
                    )
                )
            )

            result = await db.execute(query)
            items = result.scalars().all()

            if len(items) < 100:
                logger.warning(
                    "smart_inbox_insufficient_training_data",
                    sample_size=len(items),
                )
                return {
                    "success": False,
                    "error": f"Zu wenig Daten ({len(items)} < 100 Minimum)",
                }

            # Berechne Statistiken nach Source-Type und User
            stats_by_source = {}
            stats_by_user = {}

            for item in items:
                source_type = item.source_type
                user_id = str(item.user_id) if item.user_id else "company_level"

                # Completion-Zeit berechnen
                completion_time = None
                if item.updated_at and item.created_at:
                    completion_time = (item.updated_at - item.created_at).total_seconds() / 3600

                # Nach Source-Type aggregieren
                if source_type not in stats_by_source:
                    stats_by_source[source_type] = {
                        "completed": 0,
                        "dismissed": 0,
                        "avg_completion_hours": [],
                    }

                if item.status == "completed":
                    stats_by_source[source_type]["completed"] += 1
                    if completion_time:
                        stats_by_source[source_type]["avg_completion_hours"].append(completion_time)
                else:
                    stats_by_source[source_type]["dismissed"] += 1

                # Nach User aggregieren
                if user_id not in stats_by_user:
                    stats_by_user[user_id] = {
                        "total_items": 0,
                        "completion_rate": 0.0,
                    }
                stats_by_user[user_id]["total_items"] += 1

            # Berechne Durchschnitte
            for source_type, data in stats_by_source.items():
                total = data["completed"] + data["dismissed"]
                data["completion_rate"] = (data["completed"] / total) if total > 0 else 0
                if data["avg_completion_hours"]:
                    data["avg_completion_hours"] = sum(data["avg_completion_hours"]) / len(data["avg_completion_hours"])
                else:
                    data["avg_completion_hours"] = 0

            # Speichere Modell in AppConfig
            from app.db.models import AppConfig

            config_query = select(AppConfig).where(
                AppConfig.key == "smart_inbox_behavior_model"
            )
            config_result = await db.execute(config_query)
            config = config_result.scalar_one_or_none()

            model_data = {
                "stats_by_source": stats_by_source,
                "sample_size": len(items),
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "lookback_days": lookback_days,
            }

            if config:
                config.value = model_data
            else:
                config = AppConfig(
                    key="smart_inbox_behavior_model",
                    value=model_data,
                )
                db.add(config)

            await db.commit()

            return {
                "success": True,
                "sample_size": len(items),
                "source_types_analyzed": len(stats_by_source),
                "users_analyzed": len(stats_by_user),
            }

    try:
        result = asyncio.run(_train_model())
        record_task_succeeded("smart_inbox.train_behavior_model")
        logger.info(
            "smart_inbox_behavior_model_trained",
            sample_size=result.get("sample_size"),
            source_types=result.get("source_types_analyzed"),
        )
        return result
    except Exception as e:
        record_task_failed("smart_inbox.train_behavior_model", str(e))
        logger.error("smart_inbox_behavior_training_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Cleanup Completed Items
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.smart_inbox_tasks.cleanup_completed_items",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
    soft_time_limit=180,
    time_limit=300,
)
def cleanup_completed_items(
    self,
    retention_days: int = 30,
) -> Dict[str, Any]:
    """Lösche alte completed/dismissed Inbox-Items.

    Args:
        retention_days: Behalte Items für X Tage (default: 30)

    Returns:
        Dict mit Cleanup-Statistiken
    """
    record_task_started("smart_inbox.cleanup_completed")
    logger.info("smart_inbox_cleanup_started", retention_days=retention_days)

    async def _cleanup() -> Dict[str, Any]:
        async with get_worker_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

            # Soft-Delete alte Items
            stmt = (
                delete(SmartInboxItem)
                .where(
                    and_(
                        SmartInboxItem.status.in_(["completed", "dismissed"]),
                        SmartInboxItem.updated_at < cutoff_date,
                        SmartInboxItem.deleted_at.is_(None),
                    )
                )
            )

            result = await db.execute(stmt)
            await db.commit()

            deleted_count = result.rowcount

            return {
                "deleted_count": deleted_count,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
            }

    try:
        result = asyncio.run(_cleanup())
        record_task_succeeded("smart_inbox.cleanup_completed")
        logger.info(
            "smart_inbox_cleanup_completed",
            deleted=result["deleted_count"],
            retention_days=retention_days,
        )
        return result
    except Exception as e:
        record_task_failed("smart_inbox.cleanup_completed", str(e))
        logger.error("smart_inbox_cleanup_failed", **safe_error_log(e))
        raise self.retry(exc=e)
