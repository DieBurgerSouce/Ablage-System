# -*- coding: utf-8 -*-
"""
Anomalie-Erkennung Celery Tasks fuer Ablage-System.

Automatisierte Anomalie-Pruefungen:
- anomaly.run_detection - Taegliche Gesamtpruefung aller Mandanten
- anomaly.check_single_document - Pruefung fuer ein einzelnes neues Dokument

SECURITY: NEVER log financial details, IBANs or PII.

Phase 2.3 der Feature-Roadmap (Februar 2026).
Feinpoliert und durchdacht - Automated Anomaly Detection.
"""

import asyncio
from datetime import timedelta
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_

from app.workers.celery_app import celery_app
from app.db.session import get_worker_session_context
from app.db.models import Company, Document, InvoiceTracking
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Taegliche Anomalie-Erkennung
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.anomaly_tasks.run_anomaly_detection_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def run_anomaly_detection_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """
    Taegliche Anomalie-Erkennung fuer alle oder einen bestimmten Mandanten.

    Fuehrt alle aktiven Anomalie-Regeln aus und speichert erkannte
    Anomalien in der Datenbank.

    Args:
        company_id: Optionale Mandanten-ID (falls None: alle Mandanten)

    Returns:
        Dict mit Erkennungs-Statistiken
    """
    from app.services.anomaly.anomaly_detection_service import (
        get_anomaly_detection_service,
    )

    async def _run() -> Dict[str, object]:
        async with get_worker_session_context() as db:
            stats: Dict[str, object] = {
                "companies_scanned": 0,
                "total_anomalies": 0,
                "by_type": {},
                "errors": 0,
            }

            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_stmt = (
                    select(Company.id).where(Company.is_active.is_(True))
                )
                company_result = await db.execute(company_stmt)
                company_ids = [row[0] for row in company_result.all()]

            service = get_anomaly_detection_service(db)

            for cid in company_ids:
                try:
                    anomalies = await service.run_all_checks(cid)
                    stats["companies_scanned"] = (
                        int(stats["companies_scanned"]) + 1
                    )
                    stats["total_anomalies"] = (
                        int(stats["total_anomalies"]) + len(anomalies)
                    )

                    by_type = stats.get("by_type", {})
                    if not isinstance(by_type, dict):
                        by_type = {}
                    for anomaly in anomalies:
                        current = by_type.get(anomaly.anomaly_type, 0)
                        if isinstance(current, int):
                            by_type[anomaly.anomaly_type] = current + 1
                        else:
                            by_type[anomaly.anomaly_type] = 1
                    stats["by_type"] = by_type

                except Exception as exc:
                    logger.warning(
                        "anomaly_detection_company_error",
                        company_id=str(cid),
                        **safe_error_log(exc),
                    )
                    stats["errors"] = int(stats["errors"]) + 1

            await db.commit()
            return stats

    try:
        result = asyncio.run(_run())
        logger.info(
            "anomaly_detection_completed",
            companies_scanned=result["companies_scanned"],
            total_anomalies=result["total_anomalies"],
        )
        return result
    except Exception as exc:
        logger.error("anomaly_detection_failed", **safe_error_log(exc))
        raise self.retry(exc=exc)


# =============================================================================
# Einzel-Dokument Pruefung
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.anomaly_tasks.check_single_document_anomalies_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def check_single_document_anomalies_task(
    self,
    document_id: str,
    company_id: str,
) -> Dict[str, object]:
    """
    Prueft Anomalien fuer ein einzelnes neues Dokument.

    Wird ausgeloest, wenn ein neues Dokument verarbeitet wurde.
    Fuehrt Duplikat- und Betrags-Pruefungen durch.

    Args:
        document_id: Dokument-ID
        company_id: Mandanten-ID

    Returns:
        Dict mit Erkennungs-Ergebnis
    """
    from app.services.anomaly.anomaly_detection_service import (
        get_anomaly_detection_service,
    )

    async def _check() -> Dict[str, object]:
        async with get_worker_session_context() as db:
            service = get_anomaly_detection_service(db)
            cid = UUID(company_id)

            anomalies: List[object] = []

            # Duplikat-Pruefung
            try:
                dup_anomalies = await service.check_duplicate_invoices(cid)
                # Filtere auf das betreffende Dokument
                for anomaly in dup_anomalies:
                    if str(anomaly.source_id) == document_id or document_id in (
                        anomaly.related_ids or []
                    ):
                        anomalies.append(anomaly)
            except Exception as exc:
                logger.warning(
                    "single_doc_duplicate_check_error",
                    document_id=document_id,
                    **safe_error_log(exc),
                )

            # Betrags-Ausreisser-Pruefung
            try:
                amount_anomalies = await service.check_amount_outliers(cid)
                for anomaly in amount_anomalies:
                    if str(anomaly.source_id) == document_id:
                        anomalies.append(anomaly)
            except Exception as exc:
                logger.warning(
                    "single_doc_amount_check_error",
                    document_id=document_id,
                    **safe_error_log(exc),
                )

            if anomalies:
                db.add_all(anomalies)
                await db.flush()

            await db.commit()

            return {
                "document_id": document_id,
                "anomalies_found": len(anomalies),
                "types": list({
                    a.anomaly_type for a in anomalies
                    if hasattr(a, "anomaly_type")
                }),
            }

    try:
        result = asyncio.run(_check())
        if result["anomalies_found"] > 0:
            logger.info(
                "single_document_anomalies_detected",
                document_id=document_id,
                anomalies_found=result["anomalies_found"],
            )
        return result
    except Exception as exc:
        logger.error(
            "single_document_anomaly_check_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)
