# -*- coding: utf-8 -*-
"""External Data Enrichment periodic tasks (F12).

Phase 12: Integration mit SupplierVerificationService.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Dict, Any

import structlog
from sqlalchemy import select, and_, delete

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log
from app.db.session import async_session_maker
from app.db.models import BusinessEntity, AppConfig

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.tasks.enrichment_tasks.enrich_entity")
def enrich_entity(entity_id: str) -> dict:
    """Bereichere eine Entity mit externen Daten.

    Quellen:
    - Handelsregister (common-register.de)
    - Bundesanzeiger
    - USt-IdNr Pruefung (BZSt)
    """
    logger.info("enrichment_entity_start", entity_id=entity_id)
    try:
        result = asyncio.get_event_loop().run_until_complete(
            _enrich_entity(entity_id)
        )
        logger.info(
            "enrichment_entity_complete",
            entity_id=entity_id,
            sources_checked=result.get("sources_checked", 0),
        )
        return result
    except Exception as e:
        logger.error("enrichment_entity_error", entity_id=entity_id, **safe_error_log(e))
        raise


async def _enrich_entity(entity_id: str) -> Dict[str, Any]:
    """Async Implementation fuer Entity Enrichment."""
    from app.services.external.supplier_verification_service import SupplierVerificationService

    async with async_session_maker() as db:
        # Entity laden
        entity = await db.get(BusinessEntity, UUID(entity_id))

        if not entity:
            logger.warning("enrichment_entity_not_found", entity_id=entity_id)
            return {
                "status": "skipped",
                "entity_id": entity_id,
                "reason": "Entity not found",
            }

        if not entity.company_id:
            return {
                "status": "skipped",
                "entity_id": entity_id,
                "reason": "No company_id",
            }

        try:
            # SupplierVerificationService nutzen
            service = SupplierVerificationService(db)
            result = await service.verify_supplier(entity.id, entity.company_id)

            sources_checked = len(result.findings) if result else 0

            # Enrichment-Ergebnis loggen
            if result:
                logger.info(
                    "entity_enriched",
                    entity_id=entity_id,
                    findings=sources_checked,
                    overall_status=result.overall_status.value if result.overall_status else "unknown",
                )

            return {
                "status": "success",
                "entity_id": entity_id,
                "sources_checked": sources_checked,
            }

        except Exception as e:
            logger.warning(
                "enrichment_verification_failed",
                entity_id=entity_id,
                **safe_error_log(e),
            )
            return {
                "status": "error",
                "entity_id": entity_id,
                "sources_checked": 0,
            }


@celery_app.task(name="app.workers.tasks.enrichment_tasks.cleanup_expired_cache")
def cleanup_expired_cache() -> dict:
    """Bereinige abgelaufene Enrichment-Cache-Eintraege."""
    logger.info("enrichment_cleanup_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_cleanup_expired_cache())
        logger.info(
            "enrichment_cleanup_complete",
            entries_cleaned=result.get("entries_cleaned", 0),
        )
        return result
    except Exception as e:
        logger.error("enrichment_cleanup_error", **safe_error_log(e))
        raise


async def _cleanup_expired_cache() -> Dict[str, Any]:
    """Async Implementation fuer Cache Cleanup."""
    entries_cleaned = 0
    # Cache-Eintraege aelter als 7 Tage loeschen
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    async with async_session_maker() as db:
        # Enrichment-Cache in AppConfig (Keys mit "enrichment_cache_" Prefix)
        cache_result = await db.execute(
            select(AppConfig).where(AppConfig.key.like("enrichment_cache_%"))
        )
        cache_entries = cache_result.scalars().all()

        for entry in cache_entries:
            try:
                if entry.value and "cached_at" in entry.value:
                    cached_at = datetime.fromisoformat(entry.value["cached_at"])
                    if cached_at.replace(tzinfo=timezone.utc) < cutoff:
                        await db.delete(entry)
                        entries_cleaned += 1
                elif entry.updated_at and entry.updated_at.replace(tzinfo=timezone.utc) < cutoff:
                    # Fallback: updated_at nutzen
                    await db.delete(entry)
                    entries_cleaned += 1
            except Exception:
                continue

        await db.commit()

        logger.info(
            "enrichment_cache_cleaned",
            entries_removed=entries_cleaned,
            cutoff_date=cutoff.isoformat(),
        )

    return {
        "status": "success",
        "entries_cleaned": entries_cleaned,
    }
