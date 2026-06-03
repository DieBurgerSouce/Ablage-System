# -*- coding: utf-8 -*-
"""Worker-Control-Service (G1-Kontrakt M6).

Stellt einen *ehrlichen* Neustart-Hook fuer Celery-Worker bereit. Der zugehoerige
Admin-Endpoint (G1) ruft diesen Hook auf und spiegelt das Ergebnis:
- Ist ein echter Restart-Mechanismus aktiv, wird er ausgefuehrt (``performed=True``)
  und G1 antwortet mit HTTP 200.
- Ist KEIN Mechanismus verfuegbar, liefert der Hook ``performed=False`` und G1
  antwortet ehrlich mit HTTP 501 — KEIN gefaelschter Erfolg.

Scope-Hinweis (G4): Dieser Service kapselt nur die Worker-Steuerung; er erstellt
KEINE API-Endpoints.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class WorkerRestartResult:
    """Ergebnis einer Worker-Neustart-Anforderung.

    Attributes:
        performed: True, wenn tatsaechlich ein Neustart ausgeloest wurde.
        mechanism: Verwendeter Mechanismus (z. B. ``"pool_restart"`` oder ``"none"``).
        detail: Menschlich lesbarer, deutscher Detailtext (kein PII).
    """

    performed: bool
    mechanism: str
    detail: str


async def request_worker_restart(reason: str) -> WorkerRestartResult:
    """Fordert einen Neustart der Celery-Worker an (ehrlich, ohne Fake-Erfolg).

    Args:
        reason: Grund der Anforderung (fuer Audit/Logging; kein PII erwartet).

    Returns:
        WorkerRestartResult mit ``performed``/``mechanism``/``detail``.
    """
    # Lazy-Import: celery_app ist schwergewichtig und soll nicht beim Modul-Import
    # dieses Services geladen werden.
    try:
        from app.workers.celery_app import celery_app
    except Exception as exc:  # noqa: BLE001 - ehrliche Degradation, kein PII
        logger.warning("worker_restart_celery_unavailable", error=type(exc).__name__)
        return WorkerRestartResult(
            performed=False,
            mechanism="none",
            detail="Celery-App nicht verfuegbar — kein Neustart moeglich.",
        )

    # Pool-Restart ist nur moeglich, wenn in der Celery-Konfiguration aktiviert.
    pool_restarts_enabled = bool(getattr(celery_app.conf, "worker_pool_restarts", False))
    if not pool_restarts_enabled:
        logger.info("worker_restart_not_enabled", reason=reason)
        return WorkerRestartResult(
            performed=False,
            mechanism="none",
            detail=(
                "Kein Neustart-Mechanismus aktiv (worker_pool_restarts=False). "
                "Der Endpoint sollte ehrlich HTTP 501 zurueckgeben."
            ),
        )

    try:
        # broadcast() ist blockierend -> in einen Thread auslagern, damit der
        # Event-Loop nicht blockiert wird.
        replies = await asyncio.to_thread(
            celery_app.control.broadcast,
            "pool_restart",
            arguments={"reload": True},
            reply=True,
            timeout=5.0,
        )
    except Exception as exc:  # noqa: BLE001 - ehrliche Degradation, kein PII
        logger.warning("worker_restart_broadcast_failed", error=type(exc).__name__)
        return WorkerRestartResult(
            performed=False,
            mechanism="pool_restart",
            detail="Neustart-Broadcast fehlgeschlagen.",
        )

    worker_count = len(replies) if replies else 0
    if worker_count > 0:
        logger.info("worker_restart_performed", reason=reason, workers=worker_count)
        return WorkerRestartResult(
            performed=True,
            mechanism="pool_restart",
            detail=f"Pool-Restart an {worker_count} Worker gesendet.",
        )

    logger.warning("worker_restart_no_workers", reason=reason)
    return WorkerRestartResult(
        performed=False,
        mechanism="pool_restart",
        detail="Keine Worker haben auf den Neustart-Broadcast geantwortet.",
    )
