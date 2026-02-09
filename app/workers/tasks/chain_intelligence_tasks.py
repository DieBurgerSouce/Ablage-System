# -*- coding: utf-8 -*-
"""
Chain Intelligence Celery Tasks.

Automatische Analyse von Dokumentenketten:
- Naechtliche Lueckenerkennung fuer alle Firmen
- Woechentliche Erkennung verwaister Dokumente
- Proaktive Benachrichtigungen bei kritischen Luecken

Feinpoliert und durchdacht - Proaktive Kettenanalyse.
"""

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context

logger = structlog.get_logger(__name__)


# =============================================================================
# Nightly Gap Scan
# =============================================================================


@celery_app.task(
    name="chain_intelligence.scan_gaps",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def scan_chain_gaps_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Scannt alle Ketten auf fehlende Glieder.

    Wird naechtlich um 03:30 Uhr ausgefuehrt.
    Wenn company_id angegeben, nur fuer diese Firma.
    Sonst fuer alle Firmen mit Ketten.

    Args:
        company_id: Optional - nur fuer diese Firma

    Returns:
        Dict mit Scan-Ergebnissen und Statistiken
    """
    from app.services.document_chain_intelligence_service import (
        get_chain_intelligence_service,
    )
    from app.db.models import Document
    from sqlalchemy import select, func

    async def _scan_gaps() -> Dict[str, object]:
        service = get_chain_intelligence_service()
        results: Dict[str, object] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "companies_scanned": 0,
            "total_chains": 0,
            "total_gaps": 0,
            "critical_gaps": 0,
            "warning_gaps": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
            # Company IDs ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                # Alle Firmen mit Ketten
                stmt = (
                    select(Document.company_id)
                    .where(
                        Document.chain_id.isnot(None),
                        Document.deleted_at.is_(None),
                    )
                    .distinct()
                )
                result = await db.execute(stmt)
                company_ids = [row[0] for row in result.fetchall()]

            for cid in company_ids:
                try:
                    report = await service.scan_for_gaps(
                        company_id=cid,
                        db=db,
                    )
                    results["companies_scanned"] = int(results["companies_scanned"]) + 1
                    results["total_chains"] = int(results["total_chains"]) + report.total_chains
                    results["total_gaps"] = int(results["total_gaps"]) + len(report.gaps)
                    results["critical_gaps"] = int(results["critical_gaps"]) + sum(
                        1 for g in report.gaps if g.severity == "critical"
                    )
                    results["warning_gaps"] = int(results["warning_gaps"]) + sum(
                        1 for g in report.gaps if g.severity == "warning"
                    )
                except Exception as e:
                    error_list = results.get("errors", [])
                    if isinstance(error_list, list) and len(error_list) < 10:
                        error_list.append({
                            "company_id": str(cid),
                            "error": str(type(e).__name__),
                        })
                    logger.warning(
                        "chain_gap_scan_company_error",
                        company_id=str(cid),
                        **safe_error_log(e),
                    )

        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        return results

    try:
        result = asyncio.get_event_loop().run_until_complete(_scan_gaps())

        logger.info(
            "chain_gap_scan_completed",
            companies=result["companies_scanned"],
            chains=result["total_chains"],
            gaps=result["total_gaps"],
            critical=result["critical_gaps"],
        )

        return result
    except Exception as e:
        logger.error("chain_gap_scan_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Weekly Orphan Detection
# =============================================================================


@celery_app.task(
    name="chain_intelligence.detect_orphans",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def detect_orphan_documents_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Erkennt verwaiste Dokumente ohne Kettenverknuepfung.

    Wird woechentlich am Sonntag um 04:00 Uhr ausgefuehrt.

    Args:
        company_id: Optional - nur fuer diese Firma

    Returns:
        Dict mit Orphan-Statistiken
    """
    from app.services.document_chain_intelligence_service import (
        get_chain_intelligence_service,
    )
    from app.db.models import Document
    from sqlalchemy import select

    async def _detect_orphans() -> Dict[str, object]:
        service = get_chain_intelligence_service()
        results: Dict[str, object] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "companies_scanned": 0,
            "total_orphans": 0,
            "orphans_with_matches": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                stmt = (
                    select(Document.company_id)
                    .where(Document.deleted_at.is_(None))
                    .distinct()
                )
                result = await db.execute(stmt)
                company_ids = [row[0] for row in result.fetchall()]

            for cid in company_ids:
                try:
                    orphans = await service.detect_orphan_documents(
                        company_id=cid,
                        db=db,
                    )
                    results["companies_scanned"] = int(results["companies_scanned"]) + 1
                    results["total_orphans"] = int(results["total_orphans"]) + len(orphans)
                    results["orphans_with_matches"] = int(results["orphans_with_matches"]) + sum(
                        1 for o in orphans if o.potential_chain_ids
                    )
                except Exception as e:
                    error_list = results.get("errors", [])
                    if isinstance(error_list, list) and len(error_list) < 10:
                        error_list.append({
                            "company_id": str(cid),
                            "error": str(type(e).__name__),
                        })
                    logger.warning(
                        "orphan_detection_company_error",
                        company_id=str(cid),
                        **safe_error_log(e),
                    )

        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        return results

    try:
        result = asyncio.get_event_loop().run_until_complete(_detect_orphans())

        logger.info(
            "orphan_detection_completed",
            companies=result["companies_scanned"],
            orphans=result["total_orphans"],
            with_matches=result["orphans_with_matches"],
        )

        return result
    except Exception as e:
        logger.error("orphan_detection_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Celery Beat Schedule
# =============================================================================

CHAIN_INTELLIGENCE_BEAT_SCHEDULE = {
    # Naechtlicher Gap-Scan um 03:30
    "chain-intelligence-gap-scan": {
        "task": "chain_intelligence.scan_gaps",
        "schedule": {
            "hour": 3,
            "minute": 30,
        },
        "options": {"queue": "default"},
    },
    # Woechentliche Orphan-Erkennung Sonntag 04:00
    "chain-intelligence-orphan-detection": {
        "task": "chain_intelligence.detect_orphans",
        "schedule": {
            "day_of_week": 0,  # Sonntag
            "hour": 4,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
}
