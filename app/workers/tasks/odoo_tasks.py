"""
Odoo Celery Tasks.

Phase 6: Odoo Integration Deepening
- Webhook event processing
- Extended data sync (Projects, Timesheet, Inventory)
- AI feedback push to Odoo
- Retry handling for failed operations

Feinpoliert und durchdacht - Reliable Odoo Task Orchestration.
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.schemas.odoo import OdooWebhookStatus, OdooFeedbackStatus

logger = structlog.get_logger(__name__)


# =============================================================================
# Webhook Processing Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.odoo_tasks.process_odoo_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_odoo_webhook(
    self,
    event_db_id: str,
    connection_id: str,
    event_type: str,
    action: str,
    record_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Verarbeitet ein Odoo Webhook-Event.

    Args:
        event_db_id: ID des Webhook-Events in unserer DB
        connection_id: ERP-Verbindungs-ID
        event_type: Typ (customer, supplier, invoice, etc.)
        action: Aktion (create, update, delete)
        record_id: Odoo Record-ID
        data: Event-Daten

    Returns:
        Verarbeitungsergebnis
    """
    import asyncio

    async def _process() -> Dict[str, Any]:
        from app.db.models import OdooWebhookEvent, ERPConnection

        async with get_async_session_context() as db:
            # Update event status to processing
            await db.execute(
                update(OdooWebhookEvent)
                .where(OdooWebhookEvent.id == UUID(event_db_id))
                .values(
                    status=OdooWebhookStatus.PROCESSING.value,
                    processing_attempts=OdooWebhookEvent.processing_attempts + 1,
                    last_attempt_at=datetime.now(timezone.utc),
                    task_id=self.request.id,
                )
            )
            await db.commit()

            try:
                # Route to appropriate handler
                result = await _route_webhook_event(
                    db=db,
                    connection_id=UUID(connection_id),
                    event_type=event_type,
                    action=action,
                    record_id=record_id,
                    data=data,
                )

                # Mark as success
                await db.execute(
                    update(OdooWebhookEvent)
                    .where(OdooWebhookEvent.id == UUID(event_db_id))
                    .values(
                        status=OdooWebhookStatus.SUCCESS.value,
                        processed_at=datetime.now(timezone.utc),
                        error_message=None,
                    )
                )
                await db.commit()

                logger.info(
                    "odoo_webhook_processed",
                    event_id=event_db_id,
                    event_type=event_type,
                    action=action,
                    record_id=record_id,
                )

                return {
                    "success": True,
                    "event_id": event_db_id,
                    "event_type": event_type,
                    "action": action,
                    **result,
                }

            except Exception as e:
                # Mark as failed
                await db.execute(
                    update(OdooWebhookEvent)
                    .where(OdooWebhookEvent.id == UUID(event_db_id))
                    .values(
                        status=OdooWebhookStatus.FAILED.value,
                        error_message=safe_error_detail(e, "Webhook-Verarbeitung"),
                    )
                )
                await db.commit()

                logger.exception(
                    "odoo_webhook_processing_failed",
                    event_id=event_db_id,
                    **safe_error_log(e),
                )
                raise

    return asyncio.get_event_loop().run_until_complete(_process())


async def _route_webhook_event(
    db: AsyncSession,
    connection_id: UUID,
    event_type: str,
    action: str,
    record_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Routet Webhook-Event zum richtigen Handler.
    """
    handlers = {
        "customer": _handle_customer_event,
        "supplier": _handle_supplier_event,
        "invoice": _handle_invoice_event,
        "payment": _handle_payment_event,
        "product": _handle_product_event,
    }

    handler = handlers.get(event_type)
    if not handler:
        logger.warning(
            "odoo_webhook_unknown_type",
            event_type=event_type,
        )
        return {"handled": False, "reason": "Unbekannter Event-Typ"}

    return await handler(db, connection_id, action, record_id, data)


async def _handle_customer_event(
    db: AsyncSession,
    connection_id: UUID,
    action: str,
    record_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Verarbeitet Kunden-Events von Odoo."""
    from app.db.models import BusinessEntity, ERPEntityMapping

    if action == "delete":
        # Mark local entity as deactivated (don't delete, for audit)
        mapping = await db.execute(
            select(ERPEntityMapping).where(
                and_(
                    ERPEntityMapping.connection_id == connection_id,
                    ERPEntityMapping.remote_id == str(record_id),
                    ERPEntityMapping.entity_type == "customer",
                )
            )
        )
        existing_mapping = mapping.scalar_one_or_none()

        if existing_mapping:
            await db.execute(
                update(BusinessEntity)
                .where(BusinessEntity.id == existing_mapping.local_id)
                .values(is_active=False, updated_at=datetime.now(timezone.utc))
            )
            await db.commit()
            return {"handled": True, "action": "deactivated", "local_id": str(existing_mapping.local_id)}

        return {"handled": True, "action": "not_found"}

    # For create/update - sync the data
    # This would normally call the sync engine, but for webhook we can do direct update
    # SECURITY: Do NOT log customer names or other PII
    return {
        "handled": True,
        "action": action,
        "record_id": record_id,
        "fields_updated": list(data.keys()) if data else [],
    }


async def _handle_supplier_event(
    db: AsyncSession,
    connection_id: UUID,
    action: str,
    record_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Verarbeitet Lieferanten-Events von Odoo."""
    # Similar to customer handling
    return {
        "handled": True,
        "action": action,
        "record_id": record_id,
        "fields_updated": list(data.keys()) if data else [],
    }


async def _handle_invoice_event(
    db: AsyncSession,
    connection_id: UUID,
    action: str,
    record_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Verarbeitet Rechnungs-Events von Odoo."""
    # Update invoice tracking if we have it linked
    from app.db.models import InvoiceTracking, ERPEntityMapping

    # Check if invoice is linked
    mapping = await db.execute(
        select(ERPEntityMapping).where(
            and_(
                ERPEntityMapping.connection_id == connection_id,
                ERPEntityMapping.remote_id == str(record_id),
                ERPEntityMapping.entity_type == "invoice",
            )
        )
    )
    existing_mapping = mapping.scalar_one_or_none()

    if existing_mapping:
        # Update payment status if provided
        payment_state = data.get("payment_state")
        if payment_state:
            status_map = {
                "paid": "paid",
                "partial": "partial",
                "not_paid": "open",
                "reversed": "cancelled",
            }
            new_status = status_map.get(payment_state, "open")

            await db.execute(
                update(InvoiceTracking)
                .where(InvoiceTracking.document_id == existing_mapping.local_id)
                .values(
                    status=new_status,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

            return {
                "handled": True,
                "action": "status_updated",
                "new_status": new_status,
            }

    return {
        "handled": True,
        "action": action,
        "record_id": record_id,
    }


async def _handle_payment_event(
    db: AsyncSession,
    connection_id: UUID,
    action: str,
    record_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Verarbeitet Zahlungs-Events von Odoo."""
    # Link payment to invoice if possible
    # SECURITY: Do NOT log payment amounts
    return {
        "handled": True,
        "action": action,
        "record_id": record_id,
    }


async def _handle_product_event(
    db: AsyncSession,
    connection_id: UUID,
    action: str,
    record_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Verarbeitet Produkt-Events von Odoo."""
    # Product catalog updates
    return {
        "handled": True,
        "action": action,
        "record_id": record_id,
        "fields_updated": list(data.keys()) if data else [],
    }


@celery_app.task(
    name="app.workers.tasks.odoo_tasks.retry_failed_odoo_webhook",
    bind=True,
    max_retries=2,
)
def retry_failed_odoo_webhook(self, event_db_id: str) -> Dict[str, Any]:
    """
    Wiederholt ein fehlgeschlagenes Webhook-Event.

    Args:
        event_db_id: ID des Webhook-Events

    Returns:
        Verarbeitungsergebnis
    """
    import asyncio

    async def _retry() -> Dict[str, Any]:
        from app.db.models import OdooWebhookEvent

        async with get_async_session_context() as db:
            result = await db.execute(
                select(OdooWebhookEvent).where(
                    OdooWebhookEvent.id == UUID(event_db_id)
                )
            )
            event = result.scalar_one_or_none()

            if not event:
                return {"success": False, "error": "Event nicht gefunden"}

            if event.status == OdooWebhookStatus.SUCCESS.value:
                return {"success": True, "message": "Event bereits verarbeitet"}

            # Re-queue the original task
            process_odoo_webhook.delay(
                event_db_id=str(event.id),
                connection_id=str(event.connection_id),
                event_type=event.event_type,
                action=event.action,
                record_id=int(event.odoo_record_id) if event.odoo_record_id else 0,
                data=event.payload_preview or {},
            )

            return {
                "success": True,
                "message": "Retry eingereiht",
                "event_id": str(event.id),
            }

    return asyncio.get_event_loop().run_until_complete(_retry())


# =============================================================================
# Extended Data Sync Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.odoo_tasks.sync_extended_data",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def sync_extended_data(
    self,
    connection_id: str,
    data_types: List[str],
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synchronisiert erweiterte Datentypen aus Odoo.

    Args:
        connection_id: ERP-Verbindungs-ID
        data_types: Liste der Datentypen (projects, timesheet, inventory, products)
        since: Optional ISO-Timestamp für Delta-Sync

    Returns:
        Sync-Ergebnis pro Datentyp
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        from app.workers.tasks.erp_sync_tasks import get_connection_config, create_connector

        async with get_async_session_context() as db:
            config = await get_connection_config(db, UUID(connection_id))
            if not config:
                return {"success": False, "error": "Verbindung nicht gefunden"}

            if not config.is_active:
                return {"success": False, "error": "Verbindung deaktiviert"}

            connector = await create_connector(config)
            if not await connector.connect():
                return {"success": False, "error": connector.last_error}

            since_dt = None
            if since:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

            results: Dict[str, Any] = {}

            try:
                for data_type in data_types:
                    try:
                        if data_type == "projects":
                            result = await connector.sync_projects(since=since_dt)
                        elif data_type == "timesheet":
                            result = await connector.sync_timesheet_entries(since=since_dt)
                        elif data_type == "inventory":
                            result = await connector.sync_stock_moves(since=since_dt)
                        elif data_type == "products":
                            result = await connector.sync_product_catalog(since=since_dt)
                        else:
                            results[data_type] = {"error": "Unbekannter Datentyp"}
                            continue

                        # Update sync status
                        await _update_sync_status(
                            db=db,
                            connection_id=UUID(connection_id),
                            data_type=data_type,
                            records_synced=result.records_synced,
                            success=result.success,
                            error=result.error_message,
                        )

                        results[data_type] = {
                            "success": result.success,
                            "records_synced": result.records_synced,
                            "error": result.error_message,
                        }

                    except Exception as e:
                        logger.exception(
                            "odoo_extended_sync_type_error",
                            data_type=data_type,
                            **safe_error_log(e),
                        )
                        results[data_type] = {
                            "success": False,
                            "error": safe_error_detail(e, "Sync"),
                        }

            finally:
                await connector.disconnect()

            logger.info(
                "odoo_extended_sync_completed",
                connection_id=connection_id,
                data_types=data_types,
                results_summary={k: v.get("records_synced", 0) for k, v in results.items()},
            )

            return {
                "success": True,
                "connection_id": connection_id,
                "results": results,
            }

    return asyncio.get_event_loop().run_until_complete(_sync())


async def _update_sync_status(
    db: AsyncSession,
    connection_id: UUID,
    data_type: str,
    records_synced: int,
    success: bool,
    error: Optional[str],
) -> None:
    """Aktualisiert den Sync-Status für einen Datentyp."""
    from app.db.models import OdooSyncStatus
    import uuid

    now = datetime.now(timezone.utc)

    # Try to find existing status
    result = await db.execute(
        select(OdooSyncStatus).where(
            and_(
                OdooSyncStatus.connection_id == connection_id,
                OdooSyncStatus.data_type == data_type,
            )
        )
    )
    status_record = result.scalar_one_or_none()

    if status_record:
        update_data = {
            "last_sync_at": now,
            "last_record_count": records_synced,
            "total_records_synced": OdooSyncStatus.total_records_synced + records_synced,
            "updated_at": now,
        }

        if success:
            update_data["last_successful_sync_at"] = now
            update_data["consecutive_failures"] = 0
            update_data["last_error"] = None
            update_data["is_paused"] = False
        else:
            update_data["consecutive_failures"] = OdooSyncStatus.consecutive_failures + 1
            update_data["last_error"] = error
            # Pause after 5 consecutive failures
            if status_record.consecutive_failures >= 4:
                update_data["is_paused"] = True

        await db.execute(
            update(OdooSyncStatus)
            .where(OdooSyncStatus.id == status_record.id)
            .values(**update_data)
        )
    else:
        # Create new status record
        new_status = OdooSyncStatus(
            id=uuid.uuid4(),
            connection_id=connection_id,
            data_type=data_type,
            last_sync_at=now,
            last_successful_sync_at=now if success else None,
            total_records_synced=records_synced,
            last_record_count=records_synced,
            consecutive_failures=0 if success else 1,
            last_error=error,
            is_paused=False,
        )
        db.add(new_status)

    await db.commit()


# =============================================================================
# AI Feedback Push Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.odoo_tasks.push_ai_feedback",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def push_ai_feedback(
    self,
    connection_id: str,
    entity_id: str,
    feedback_type: str,
    feedback_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Pusht AI-Feedback zu Odoo.

    Args:
        connection_id: ERP-Verbindungs-ID
        entity_id: Lokale Entity-ID
        feedback_type: Typ (risk_score, payment_suggestion, skonto_prediction)
        feedback_data: Feedback-Daten

    Returns:
        Push-Ergebnis
    """
    import asyncio

    async def _push() -> Dict[str, Any]:
        from app.services.erp.odoo_feedback_service import OdooFeedbackService

        async with get_async_session_context() as db:
            service = OdooFeedbackService()

            if feedback_type == "risk_score":
                success, error = await service.push_risk_score(
                    db=db,
                    connection_id=UUID(connection_id),
                    entity_id=UUID(entity_id),
                    score=feedback_data.get("score", 50),
                    payment_behavior_score=feedback_data.get("payment_behavior_score", 50),
                    risk_level=feedback_data.get("risk_level", "medium"),
                    factors=feedback_data.get("factors", {}),
                )

            elif feedback_type == "payment_suggestion":
                success, error = await service.push_payment_suggestion(
                    db=db,
                    connection_id=UUID(connection_id),
                    entity_id=UUID(entity_id),
                    suggested_payment_term=feedback_data.get("suggested_payment_term", ""),
                    suggested_credit_limit=feedback_data.get("suggested_credit_limit"),
                    reason=feedback_data.get("reason", ""),
                    confidence=feedback_data.get("confidence", 0.5),
                    based_on_invoices=feedback_data.get("based_on_invoices", 0),
                )

            elif feedback_type == "skonto_prediction":
                success, error = await service.push_skonto_prediction(
                    db=db,
                    connection_id=UUID(connection_id),
                    entity_id=UUID(entity_id),
                    skonto_usage_probability=feedback_data.get("skonto_usage_probability", 0.5),
                    average_payment_days=feedback_data.get("average_payment_days", 30),
                    recommended_skonto_percent=feedback_data.get("recommended_skonto_percent"),
                    recommendation=feedback_data.get("recommendation", ""),
                )

            else:
                return {"success": False, "error": f"Unbekannter Feedback-Typ: {feedback_type}"}

            return {
                "success": success,
                "error": error,
                "entity_id": entity_id,
                "feedback_type": feedback_type,
            }

    return asyncio.get_event_loop().run_until_complete(_push())


@celery_app.task(name="app.workers.tasks.odoo_tasks.push_all_risk_scores")
def push_all_risk_scores(connection_id: str) -> Dict[str, Any]:
    """
    Pusht alle Risk Scores zu Odoo (Batch).

    Args:
        connection_id: ERP-Verbindungs-ID

    Returns:
        Batch-Ergebnis
    """
    import asyncio

    async def _push_all() -> Dict[str, Any]:
        from app.db.models import BusinessEntity, ERPEntityMapping
        from app.services.risk_scoring_service import RiskScoringService

        async with get_async_session_context() as db:
            # Get all entities with Odoo mapping
            result = await db.execute(
                select(ERPEntityMapping).where(
                    and_(
                        ERPEntityMapping.connection_id == UUID(connection_id),
                        ERPEntityMapping.entity_type.in_(["customer", "supplier"]),
                    )
                )
            )
            mappings = result.scalars().all()

            if not mappings:
                return {
                    "success": True,
                    "message": "Keine Entities mit Odoo-Verknüpfung gefunden",
                    "pushed": 0,
                }

            risk_service = RiskScoringService()
            pushed = 0
            failed = 0

            for mapping in mappings:
                try:
                    # Calculate risk score
                    score, payment_score, factors = await risk_service.calculate_risk_score(
                        db, mapping.local_id
                    )

                    # Determine risk level
                    if score >= 75:
                        risk_level = "critical"
                    elif score >= 50:
                        risk_level = "high"
                    elif score >= 25:
                        risk_level = "medium"
                    else:
                        risk_level = "low"

                    # Queue push task
                    push_ai_feedback.delay(
                        connection_id=connection_id,
                        entity_id=str(mapping.local_id),
                        feedback_type="risk_score",
                        feedback_data={
                            "score": score,
                            "payment_behavior_score": payment_score,
                            "risk_level": risk_level,
                            "factors": factors.to_dict(),
                        },
                    )
                    pushed += 1

                except Exception as e:
                    logger.warning(
                        "odoo_risk_score_batch_item_failed",
                        entity_id=str(mapping.local_id),
                        **safe_error_log(e),
                    )
                    failed += 1

            logger.info(
                "odoo_risk_scores_batch_queued",
                connection_id=connection_id,
                pushed=pushed,
                failed=failed,
            )

            return {
                "success": True,
                "pushed": pushed,
                "failed": failed,
                "total": len(mappings),
            }

    return asyncio.get_event_loop().run_until_complete(_push_all())


# =============================================================================
# Retry Failed Operations Task
# =============================================================================


@celery_app.task(name="app.workers.tasks.odoo_tasks.retry_failed_syncs")
def retry_failed_syncs() -> Dict[str, Any]:
    """
    Wiederholt fehlgeschlagene Sync-Operationen.

    Wird periodisch aufgerufen um:
    - Fehlgeschlagene Webhook-Events erneut zu verarbeiten
    - Fehlgeschlagene Feedback-Pushes zu wiederholen

    Returns:
        Retry-Statistiken
    """
    import asyncio

    async def _retry() -> Dict[str, Any]:
        from app.db.models import OdooWebhookEvent, OdooAIFeedback

        async with get_async_session_context() as db:
            now = datetime.now(timezone.utc)
            retry_window = now - timedelta(hours=24)  # Only retry events from last 24h

            # Find failed webhook events
            webhook_result = await db.execute(
                select(OdooWebhookEvent).where(
                    and_(
                        OdooWebhookEvent.status == OdooWebhookStatus.FAILED.value,
                        OdooWebhookEvent.received_at >= retry_window,
                        OdooWebhookEvent.processing_attempts < 5,
                    )
                ).limit(50)
            )
            failed_webhooks = webhook_result.scalars().all()

            # Find failed feedback pushes
            feedback_result = await db.execute(
                select(OdooAIFeedback).where(
                    and_(
                        OdooAIFeedback.status == OdooFeedbackStatus.FAILED.value,
                        OdooAIFeedback.created_at >= retry_window,
                        OdooAIFeedback.push_attempts < 5,
                    )
                ).limit(50)
            )
            failed_feedbacks = feedback_result.scalars().all()

            webhooks_retried = 0
            feedbacks_retried = 0

            # Retry webhooks
            for webhook in failed_webhooks:
                retry_failed_odoo_webhook.delay(str(webhook.id))
                webhooks_retried += 1

            # Retry feedbacks
            for feedback in failed_feedbacks:
                push_ai_feedback.delay(
                    connection_id=str(feedback.connection_id),
                    entity_id=str(feedback.entity_id),
                    feedback_type=feedback.feedback_type,
                    feedback_data=feedback.feedback_data,
                )
                feedbacks_retried += 1

            logger.info(
                "odoo_failed_syncs_retried",
                webhooks_retried=webhooks_retried,
                feedbacks_retried=feedbacks_retried,
            )

            return {
                "success": True,
                "webhooks_retried": webhooks_retried,
                "feedbacks_retried": feedbacks_retried,
            }

    return asyncio.get_event_loop().run_until_complete(_retry())


