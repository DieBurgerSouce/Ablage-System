# -*- coding: utf-8 -*-
"""Celery Tasks für das Autonomous Trust System.

Phase 2.1: Multi-Level Trust für autonome KI-Aktionen:
- Verarbeitung fälliger Proposals
- Trust-Level Metriken Aktualisierung
- Rollback-Bereinigung
"""

from __future__ import annotations

import structlog
from datetime import timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import and_, select, func

from app.core.datetime_utils import utc_now
from app.workers.celery_app import celery_app
from app.db.session import get_sync_session, get_async_session
from app.db.models import (
    AutonomousTrustConfig,
    AutonomousProposalQueue,
    Company,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Proposal Processing Tasks
# ============================================================================


@celery_app.task(
    name="app.workers.tasks.autonomous_trust_tasks.process_due_proposals",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="maintenance",
)
def process_due_proposals(
    self,
    batch_size: int = 100,
) -> Dict[str, Any]:
    """Verarbeitet fällige Proposals.

    Wird alle 15 Minuten via Celery Beat ausgeführt.
    Sucht nach PENDING Proposals deren scheduled_at erreicht ist
    und führt sie automatisch aus.

    Args:
        batch_size: Maximale Anzahl pro Durchlauf

    Returns:
        Dict mit Statistiken
    """
    import asyncio

    logger.info("Starte Verarbeitung fälliger Proposals...")

    async def _process():
        from app.services.ai.delayed_acceptance_service import (
            DelayedAcceptanceService,
            ProposalType,
        )
        from app.services.ai.autonomous_actions_service import (
            AutonomousActionsService,
            get_autonomous_actions_service,
        )

        async with get_async_session() as db:
            delayed_service = DelayedAcceptanceService(db)

            # Executor-Map für verschiedene Proposal-Typen
            async def execute_payment_approval(target_id: UUID, value: Dict) -> bool:
                """Führt Payment-Approval aus."""
                try:
                    service = await get_autonomous_actions_service(db)
                    result = await service.execute_payment_approval(
                        invoice_id=target_id,
                        company_id=value.get("company_id"),
                    )
                    return result.success
                except Exception as e:
                    logger.error(f"Payment approval failed: {e}")
                    return False

            async def execute_dunning(target_id: UUID, value: Dict) -> bool:
                """Führt Mahnungsstufen-Erhöhung aus."""
                try:
                    service = await get_autonomous_actions_service(db)
                    result = await service.execute_dunning(
                        invoice_id=target_id,
                        company_id=value.get("company_id"),
                    )
                    return result.success
                except Exception as e:
                    logger.error(f"Dunning execution failed: {e}")
                    return False

            async def execute_master_data_update(target_id: UUID, value: Dict) -> bool:
                """Führt Stammdaten-Update aus."""
                try:
                    service = await get_autonomous_actions_service(db)
                    result = await service.execute_master_data_update(
                        entity_id=target_id,
                        field=value.get("field", ""),
                        new_value=value.get("new_value", ""),
                        company_id=value.get("company_id"),
                    )
                    return result.success
                except Exception as e:
                    logger.error(f"Master data update failed: {e}")
                    return False

            async def execute_generic(target_id: UUID, value: Dict) -> bool:
                """Generische Ausführung (Logging)."""
                logger.info(
                    f"Generische Ausführung für {target_id}",
                    value=value,
                )
                return True

            executor_map = {
                ProposalType.APPROVE_PAYMENT: execute_payment_approval,
                ProposalType.SEND_DUNNING: execute_dunning,
                ProposalType.UPDATE_MASTER_DATA: execute_master_data_update,
                ProposalType.FILE_DOCUMENT: execute_generic,
                ProposalType.ASSIGN_ENTITY: execute_generic,
                ProposalType.CLASSIFY_DOCUMENT: execute_generic,
            }

            stats = await delayed_service.process_due_proposals(executor_map)
            return stats

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    stats = loop.run_until_complete(_process())

    logger.info(
        f"Proposal-Verarbeitung abgeschlossen: "
        f"{stats.get('processed', 0)} verarbeitet, "
        f"{stats.get('success', 0)} erfolgreich, "
        f"{stats.get('failed', 0)} fehlgeschlagen"
    )

    return stats


@celery_app.task(
    name="app.workers.tasks.autonomous_trust_tasks.update_trust_metrics",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="maintenance",
)
def update_trust_metrics(self) -> Dict[str, Any]:
    """Aktualisiert Trust-Metriken für alle Companies.

    Wird täglich via Celery Beat ausgeführt.
    Berechnet und speichert Metriken-Snapshot für jede Company.

    Returns:
        Dict mit Statistiken
    """
    import asyncio

    logger.info("Starte Trust-Metriken Aktualisierung...")

    async def _update():
        from app.services.ai.trust_level_service import TrustLevelService

        async with get_async_session() as db:
            # Hole alle aktiven Trust-Configs
            result = await db.execute(
                select(AutonomousTrustConfig)
                .where(AutonomousTrustConfig.is_enabled == True)
            )
            configs = result.scalars().all()

            updated_count = 0

            for config in configs:
                try:
                    service = TrustLevelService(db)
                    metrics = await service.get_trust_metrics(
                        company_id=config.company_id,
                        document_type=config.document_type,
                        days=30,
                    )

                    # Speichere Snapshot
                    config.metrics_snapshot = {
                        "total_decisions": metrics.total_decisions,
                        "auto_applied": metrics.auto_applied,
                        "approved": metrics.approved,
                        "rejected": metrics.rejected,
                        "corrected": metrics.corrected,
                        "approval_rate": metrics.approval_rate,
                        "error_rate": metrics.error_rate,
                        "avg_confidence": metrics.avg_confidence,
                        "days_without_error": metrics.days_without_error,
                    }
                    config.metrics_updated_at = utc_now()

                    updated_count += 1

                except Exception as e:
                    logger.warning(
                        f"Fehler bei Metriken-Update für {config.company_id}: {e}"
                    )

            await db.commit()
            return {"updated": updated_count, "total": len(configs)}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    stats = loop.run_until_complete(_update())

    logger.info(
        f"Trust-Metriken Aktualisierung abgeschlossen: "
        f"{stats.get('updated', 0)} von {stats.get('total', 0)} aktualisiert"
    )

    return stats


@celery_app.task(
    name="app.workers.tasks.autonomous_trust_tasks.evaluate_trust_upgrades",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="maintenance",
)
def evaluate_trust_upgrades(self) -> Dict[str, Any]:
    """Evaluiert mögliche Trust-Level Upgrades.

    Wird wöchentlich via Celery Beat ausgeführt.
    Prüft ob Companies für Upgrade bereit sind und erstellt Vorschläge.

    Returns:
        Dict mit Upgrade-Kandidaten
    """
    import asyncio

    logger.info("Starte Trust-Level Upgrade-Evaluierung...")

    async def _evaluate():
        from app.services.ai.trust_level_service import TrustLevelService, TrustLevel

        async with get_async_session() as db:
            # Hole alle Trust-Configs (ausser Level 4)
            result = await db.execute(
                select(AutonomousTrustConfig)
                .where(
                    and_(
                        AutonomousTrustConfig.is_enabled == True,
                        AutonomousTrustConfig.trust_level != TrustLevel.LEVEL_4_AUTONOMOUS.value,
                    )
                )
            )
            configs = result.scalars().all()

            upgrade_candidates = []

            for config in configs:
                try:
                    service = TrustLevelService(db)
                    recommendation = await service.evaluate_trust_level(
                        company_id=config.company_id,
                        document_type=config.document_type,
                    )

                    if recommendation.can_upgrade:
                        upgrade_candidates.append({
                            "company_id": str(config.company_id),
                            "document_type": config.document_type,
                            "current_level": recommendation.current_level.value,
                            "recommended_level": recommendation.recommended_level.value,
                            "reason": recommendation.reason,
                        })

                except Exception as e:
                    logger.warning(
                        f"Fehler bei Upgrade-Evaluierung für {config.company_id}: {e}"
                    )

            return {
                "evaluated": len(configs),
                "upgrade_candidates": len(upgrade_candidates),
                "candidates": upgrade_candidates,
            }

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    stats = loop.run_until_complete(_evaluate())

    logger.info(
        f"Trust-Level Evaluierung abgeschlossen: "
        f"{stats.get('upgrade_candidates', 0)} Upgrade-Kandidaten gefunden"
    )

    return stats


@celery_app.task(
    name="app.workers.tasks.autonomous_trust_tasks.cleanup_expired_proposals",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="maintenance",
)
def cleanup_expired_proposals(
    self,
    retention_days: int = 90,
) -> Dict[str, Any]:
    """Bereinigt abgelaufene Proposals.

    Wird täglich via Celery Beat ausgeführt.
    Löscht alte Proposals deren Rollback-Zeitraum abgelaufen ist.

    Args:
        retention_days: Aufbewahrungszeitraum nach Rollback-Ende

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte Bereinigung abgelaufener Proposals...")

    with get_sync_session() as db:
        cutoff = utc_now() - timedelta(days=retention_days)

        # Zaehle zu löschende Proposals
        count_query = (
            select(func.count(AutonomousProposalQueue.id))
            .where(
                and_(
                    AutonomousProposalQueue.status.in_([
                        "approved", "rejected", "auto_accepted",
                        "expired", "rolled_back", "cancelled"
                    ]),
                    AutonomousProposalQueue.updated_at < cutoff,
                )
            )
        )
        result = db.execute(count_query)
        to_delete = result.scalar() or 0

        if to_delete > 0:
            # Lösche alte Proposals (in Batches)
            from sqlalchemy import delete

            delete_stmt = (
                delete(AutonomousProposalQueue)
                .where(
                    and_(
                        AutonomousProposalQueue.status.in_([
                            "approved", "rejected", "auto_accepted",
                            "expired", "rolled_back", "cancelled"
                        ]),
                        AutonomousProposalQueue.updated_at < cutoff,
                    )
                )
            )
            db.execute(delete_stmt)
            db.commit()

    logger.info(f"Proposal-Bereinigung abgeschlossen: {to_delete} gelöscht")

    return {"deleted": to_delete, "retention_days": retention_days}


# ============================================================================
# Notification Tasks
# ============================================================================


@celery_app.task(
    name="app.workers.tasks.autonomous_trust_tasks.notify_pending_proposals",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="notifications",
)
def notify_pending_proposals(self) -> Dict[str, Any]:
    """Sendet Benachrichtigungen für ausstehende Proposals.

    Wird stündlich via Celery Beat ausgeführt.
    Benachrichtigt Admins über Proposals die bald ausgeführt werden.

    Returns:
        Dict mit Statistiken
    """
    import asyncio

    logger.info("Starte Pending-Proposals Benachrichtigung...")

    async def _notify():
        from app.services.ai.delayed_acceptance_service import DelayedAcceptanceService

        async with get_async_session() as db:
            now = utc_now()
            warning_threshold = now + timedelta(hours=2)

            # Hole Proposals die in den nächsten 2 Stunden fällig sind
            result = await db.execute(
                select(AutonomousProposalQueue)
                .where(
                    and_(
                        AutonomousProposalQueue.status == "pending",
                        AutonomousProposalQueue.scheduled_at <= warning_threshold,
                        AutonomousProposalQueue.scheduled_at > now,
                    )
                )
            )
            proposals = result.scalars().all()

            # Gruppiere nach Company
            by_company: Dict[UUID, list] = {}
            for p in proposals:
                if p.company_id not in by_company:
                    by_company[p.company_id] = []
                by_company[p.company_id].append(p)

            notifications_sent = 0

            for company_id, company_proposals in by_company.items():
                try:
                    from app.services.notification.unified_hub import (
                        send_notification,
                        NotificationCategory,
                        NotificationSeverity,
                    )
                    from app.db.models import User

                    # Finde Admin-Benutzer
                    admin_result = await db.execute(
                        select(User).where(
                            and_(
                                User.is_active == True,
                                User.is_superuser == True,
                            )
                        ).limit(1)
                    )
                    admin = admin_result.scalar_one_or_none()

                    if admin:
                        types_summary = ", ".join(
                            set(p.proposal_type for p in company_proposals)
                        )
                        await send_notification(
                            recipient_user_id=admin.id,
                            recipient_email=admin.email or "",
                            notification_type="pending_proposals",
                            title=f"{len(company_proposals)} ausstehende KI-Vorschläge",
                            message=(
                                f"Es stehen {len(company_proposals)} automatische Aktionen "
                                f"zur Ausführung an: {types_summary}. "
                                f"Prüfen oder ablehnen Sie diese rechtzeitig."
                            ),
                            category=NotificationCategory.SYSTEM,
                            severity=NotificationSeverity.HIGH,
                            company_id=company_id,
                            reference_type="pending_proposals",
                            session=db,
                        )
                    notifications_sent += 1
                except Exception as e:
                    logger.warning(f"Benachrichtigungsfehler: {e}")

            return {
                "proposals_found": len(proposals),
                "companies_notified": notifications_sent,
            }

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    stats = loop.run_until_complete(_notify())

    logger.info(
        f"Pending-Proposals Benachrichtigung abgeschlossen: "
        f"{stats.get('proposals_found', 0)} Proposals, "
        f"{stats.get('companies_notified', 0)} Benachrichtigungen"
    )

    return stats
