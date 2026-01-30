# -*- coding: utf-8 -*-
"""
Orchestration Celery Tasks.

Enterprise Feature: Cross-Module Event-Orchestrierung.

Tasks:
- process_pending_orchestration_actions: Verarbeitet ausstehende Aktionen
- start_orchestrator_listener: Startet den Event-Listener
- emit_system_event: Emittiert ein System-Event
- analyze_cascading_impacts: Analysiert kaskadierende Auswirkungen

Diese Tasks sind das Rueckgrat der proaktiven System-Intelligenz.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram

from app.workers.celery_app import celery_app, CPUTask
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

ORCHESTRATION_TASK_COUNTER = Counter(
    "orchestration_tasks_total",
    "Anzahl ausgefuehrter Orchestration Tasks",
    ["task_name", "status"]
)

ORCHESTRATION_TASK_DURATION = Histogram(
    "orchestration_task_duration_seconds",
    "Dauer der Orchestration Tasks",
    ["task_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)


# =============================================================================
# Hilfsfunktion fuer async in Celery
# =============================================================================

def run_async(coro):
    """Fuehrt eine Coroutine in einem neuen Event Loop aus."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Orchestration Tasks
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_tasks.process_pending_orchestration_actions",
    max_retries=3,
    default_retry_delay=60,
    queue="orchestration",
    soft_time_limit=300,
    time_limit=600,
)
def process_pending_orchestration_actions(
    self,
    max_actions: int = 50,
) -> Dict[str, Any]:
    """
    Verarbeitet ausstehende Orchestrierungs-Aktionen.

    Sollte regelmaessig (z.B. alle 1-5 Minuten) via Celery Beat ausgefuehrt werden.
    Priorisiert kritische Aktionen und verarbeitet sie in der richtigen Reihenfolge.

    Args:
        max_actions: Maximale Anzahl zu verarbeitender Aktionen pro Durchlauf

    Returns:
        Statistik der verarbeiteten Aktionen
    """
    logger.info(
        "process_pending_orchestration_actions_started",
        task_id=self.request.id,
        max_actions=max_actions,
    )

    start_time = datetime.now(timezone.utc)

    async def _process():
        from app.services.orchestration import get_cross_module_orchestrator

        orchestrator = get_cross_module_orchestrator()
        processed_count = await orchestrator.process_pending_actions(max_actions)

        metrics = await orchestrator.get_metrics()
        return processed_count, metrics

    try:
        processed_count, metrics = run_async(_process())

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        ORCHESTRATION_TASK_COUNTER.labels(
            task_name="process_pending_actions",
            status="success"
        ).inc()

        ORCHESTRATION_TASK_DURATION.labels(
            task_name="process_pending_actions"
        ).observe(duration)

        logger.info(
            "process_pending_orchestration_actions_completed",
            task_id=self.request.id,
            processed_count=processed_count,
            remaining_pending=metrics.get("pending_actions_count", 0),
            duration_seconds=duration,
        )

        return {
            "status": "success",
            "processed_count": processed_count,
            "metrics": metrics,
            "duration_seconds": duration,
        }

    except Exception as e:
        ORCHESTRATION_TASK_COUNTER.labels(
            task_name="process_pending_actions",
            status="error"
        ).inc()

        logger.error(
            "process_pending_orchestration_actions_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_tasks.emit_system_event",
    max_retries=2,
    default_retry_delay=30,
    queue="orchestration",
    soft_time_limit=60,
    time_limit=120,
)
def emit_system_event(
    self,
    event_type: str,
    payload: Dict[str, Any],
    source: str = "celery_task",
    user_id: Optional[str] = None,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Emittiert ein System-Event ueber den Event Bus.

    Ermoeglicht das Senden von Events aus Celery Tasks heraus,
    die dann vom CrossModuleOrchestrator verarbeitet werden.

    Args:
        event_type: Der Event-Typ (z.B. "finance.anomaly_detected")
        payload: Die Event-Daten
        source: Quelle des Events (default: celery_task)
        user_id: Optional User-ID
        space_id: Optional Space-ID

    Returns:
        Event-ID und Anzahl der Subscriber
    """
    logger.info(
        "emit_system_event_started",
        task_id=self.request.id,
        event_type=event_type,
    )

    async def _emit():
        from app.services.events.event_bus import get_event_bus, EventType

        event_bus = get_event_bus()
        await event_bus.connect()

        # EventType aus String
        try:
            event_type_enum = EventType(event_type)
        except ValueError:
            logger.warning(
                "unknown_event_type",
                event_type=event_type,
            )
            # Fallback auf SYSTEM_ERROR wenn unbekannt
            event_type_enum = EventType.SYSTEM_ERROR

        event = await event_bus.publish_event(
            event_type=event_type_enum,
            payload=payload,
            source=source,
            user_id=UUID(user_id) if user_id else None,
            space_id=UUID(space_id) if space_id else None,
        )

        return str(event.event_id)

    try:
        event_id = run_async(_emit())

        logger.info(
            "emit_system_event_completed",
            task_id=self.request.id,
            event_type=event_type,
            event_id=event_id,
        )

        return {
            "status": "success",
            "event_id": event_id,
            "event_type": event_type,
        }

    except Exception as e:
        logger.error(
            "emit_system_event_failed",
            task_id=self.request.id,
            event_type=event_type,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_tasks.check_and_emit_threshold_events",
    max_retries=2,
    default_retry_delay=60,
    queue="orchestration",
    soft_time_limit=300,
    time_limit=600,
)
def check_and_emit_threshold_events(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prueft KPIs auf Schwellenwert-Ueberschreitungen und emittiert entsprechende Events.

    Diese Task verbindet Predictive Intelligence mit dem Event Bus:
    - Liest Early Warnings aus der DB
    - Emittiert passende Events fuer jede Warnung
    - Der Orchestrator kann dann darauf reagieren

    Args:
        space_id: Optional - nur fuer diesen Space pruefen

    Returns:
        Anzahl emittierter Events
    """
    logger.info(
        "check_and_emit_threshold_events_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    async def _check():
        from app.db.session import get_async_session
        from app.services.events.event_bus import get_event_bus, EventType
        from sqlalchemy import select
        from app.db.models import PrivatEarlyWarning, PrivatSpace

        event_bus = get_event_bus()
        await event_bus.connect()

        events_emitted = 0

        async with get_async_session() as db:
            # Aktive Warnings laden
            query = select(PrivatEarlyWarning).where(
                PrivatEarlyWarning.is_resolved == False
            )

            if space_id:
                query = query.where(PrivatEarlyWarning.space_id == UUID(space_id))

            result = await db.execute(query)
            warnings = result.scalars().all()

            for warning in warnings:
                # Event-Typ basierend auf KPI-Name bestimmen
                kpi_to_event = {
                    "dti": EventType.FINANCE_ANOMALY_DETECTED,
                    "debt_to_income": EventType.FINANCE_ANOMALY_DETECTED,
                    "emergency_fund_months": EventType.FINANCE_BUDGET_EXCEEDED,
                    "portfolio_concentration": EventType.INVESTMENT_REBALANCING_NEEDED,
                    "rental_yield": EventType.PROPERTY_KPIS_CALCULATED,
                    "insurance_coverage": EventType.INSURANCE_GAP_DETECTED,
                }

                event_type = kpi_to_event.get(
                    warning.kpi_name.lower(),
                    EventType.SYSTEM_KPI_RECALCULATION
                )

                # Space laden fuer User-ID
                space_result = await db.execute(
                    select(PrivatSpace).where(PrivatSpace.id == warning.space_id)
                )
                space = space_result.scalar_one_or_none()
                user_id = space.user_id if space else None

                # Event emittieren
                await event_bus.publish_event(
                    event_type=event_type,
                    payload={
                        "warning_id": str(warning.id),
                        "kpi_name": warning.kpi_name,
                        "current_value": float(warning.current_value),
                        "projected_value": float(warning.projected_value),
                        "threshold_value": float(warning.threshold_value),
                        "threshold_type": warning.threshold_type,
                        "projected_breach_date": warning.projected_breach_date.isoformat() if warning.projected_breach_date else None,
                        "severity": warning.severity,
                        "message": warning.message,
                    },
                    source="threshold_check_task",
                    user_id=user_id,
                    space_id=warning.space_id,
                )

                events_emitted += 1

        return events_emitted

    try:
        events_emitted = run_async(_check())

        logger.info(
            "check_and_emit_threshold_events_completed",
            task_id=self.request.id,
            events_emitted=events_emitted,
        )

        return {
            "status": "success",
            "events_emitted": events_emitted,
        }

    except Exception as e:
        logger.error(
            "check_and_emit_threshold_events_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_tasks.get_orchestration_metrics",
    max_retries=1,
    queue="orchestration",
    soft_time_limit=30,
    time_limit=60,
)
def get_orchestration_metrics(self) -> Dict[str, Any]:
    """
    Holt aktuelle Orchestrierungs-Metriken.

    Kann on-demand oder periodisch aufgerufen werden fuer Monitoring.

    Returns:
        Orchestrierungs-Metriken
    """
    logger.debug(
        "get_orchestration_metrics_started",
        task_id=self.request.id,
    )

    async def _get_metrics():
        from app.services.orchestration import get_cross_module_orchestrator
        from app.services.events.event_bus import get_event_bus

        orchestrator = get_cross_module_orchestrator()
        event_bus = get_event_bus()

        orch_metrics = await orchestrator.get_metrics()
        event_metrics = event_bus.get_metrics()

        return {
            "orchestrator": orch_metrics,
            "event_bus": event_metrics,
        }

    try:
        metrics = run_async(_get_metrics())

        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(
            "get_orchestration_metrics_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        return {
            "status": "error",
            "error": safe_error_detail(e, "Vorgang"),
        }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_tasks.cleanup_old_decisions",
    max_retries=2,
    default_retry_delay=120,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=600,
)
def cleanup_old_decisions(
    self,
    days_to_keep: int = 30,
) -> Dict[str, Any]:
    """
    Raeumt alte Orchestrierungs-Entscheidungen auf.

    Sollte woechentlich via Celery Beat ausgefuehrt werden.

    Args:
        days_to_keep: Anzahl Tage, die Entscheidungen behalten werden

    Returns:
        Anzahl geloeschter Entscheidungen
    """
    logger.info(
        "cleanup_old_decisions_started",
        task_id=self.request.id,
        days_to_keep=days_to_keep,
    )

    # In-Memory Decisions werden automatisch durch max_decision_history begrenzt
    # Diese Task koennte in Zukunft DB-persistierte Decisions aufraeumen

    logger.info(
        "cleanup_old_decisions_completed",
        task_id=self.request.id,
        note="In-memory decisions are auto-limited",
    )

    return {
        "status": "success",
        "message": "In-memory decisions are automatically limited by max_decision_history",
    }
