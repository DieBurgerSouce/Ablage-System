# -*- coding: utf-8 -*-
"""
OCR Template Auto-Generation Celery Tasks.

Hintergrund-Aufgaben fuer automatische Template-Erkennung:
- Taeglich neue Template-Kandidaten scannen
- Automatische Template-Generierung fuer qualifizierte Kandidaten

Feinpoliert und durchdacht - Automatische OCR-Optimierung.
"""

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="ocr.scan_template_candidates",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="metadata",
)
def scan_template_candidates_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """
    Scanne nach neuen Template-Kandidaten und generiere Templates.

    Durchsucht alle Companies (oder eine spezifische) nach Entities
    die genug aehnliche Dokumente haben, um automatisch ein Template
    zu generieren.

    Typisches Schedule: Taeglich um 03:00 via Celery Beat.

    Args:
        company_id: Optionale Company-ID. Wenn None, werden alle Companies gescannt.

    Returns:
        Dict mit Scan-Ergebnissen:
            - scanned_companies: Anzahl gescannter Companies
            - candidates_found: Anzahl gefundener Kandidaten
            - templates_generated: Anzahl generierter Templates
            - errors: Liste von Fehlern
    """

    async def _scan() -> Dict[str, object]:
        from sqlalchemy import select, func
        from app.db.models import Document
        from app.services.ocr.auto_template_service import get_auto_template_service

        result: Dict[str, object] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "scanned_companies": 0,
            "candidates_found": 0,
            "templates_generated": 0,
            "template_ids": [],
            "errors": [],
        }

        service = get_auto_template_service()

        async with get_async_session_context() as db:
            # Companies bestimmen
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                # Alle Companies mit OCR-Dokumenten
                stmt = (
                    select(Document.company_id)
                    .where(Document.ocr_status == "completed")
                    .group_by(Document.company_id)
                    .having(func.count(Document.id) >= 3)
                )
                res = await db.execute(stmt)
                company_ids = [row[0] for row in res.all() if row[0] is not None]

            logger.info(
                "ocr_template_scan_start",
                companies=len(company_ids),
            )

            for cid in company_ids:
                result["scanned_companies"] = int(result["scanned_companies"]) + 1

                try:
                    candidates = await service.list_candidates(db, cid)

                    for candidate in candidates:
                        result["candidates_found"] = int(result["candidates_found"]) + 1

                        if not candidate.is_candidate:
                            continue

                        try:
                            template = await service.generate_template(
                                db=db,
                                entity_id=candidate.entity_id,
                                company_id=cid,
                                document_ids=candidate.document_ids,
                            )

                            # Auto-Aktivierung pruefen
                            await service.check_and_auto_activate(db, template)

                            result["templates_generated"] = (
                                int(result["templates_generated"]) + 1
                            )
                            template_ids = result.get("template_ids")
                            if isinstance(template_ids, list):
                                template_ids.append(str(template.id))

                            logger.info(
                                "ocr_template_auto_generated",
                                template_id=str(template.id),
                                entity_id=str(candidate.entity_id),
                                company_id=str(cid),
                                fields=len(candidate.matching_fields),
                            )

                        except Exception as gen_err:
                            errors = result.get("errors")
                            if isinstance(errors, list):
                                errors.append({
                                    "entity_id": str(candidate.entity_id),
                                    "company_id": str(cid),
                                    "error": safe_error_detail(
                                        gen_err, "Template-Generierung"
                                    ),
                                })
                            logger.warning(
                                "ocr_template_generation_failed",
                                entity_id=str(candidate.entity_id),
                                **safe_error_log(gen_err),
                            )

                except Exception as scan_err:
                    errors = result.get("errors")
                    if isinstance(errors, list):
                        errors.append({
                            "company_id": str(cid),
                            "error": safe_error_detail(scan_err, "Kandidaten-Scan"),
                        })
                    logger.warning(
                        "ocr_template_scan_company_failed",
                        company_id=str(cid),
                        **safe_error_log(scan_err),
                    )

            await db.commit()

        result["completed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(
            "ocr_template_scan_complete",
            scanned=result["scanned_companies"],
            candidates=result["candidates_found"],
            generated=result["templates_generated"],
        )

        return result

    try:
        return asyncio.get_event_loop().run_until_complete(_scan())
    except Exception as e:
        logger.error("ocr_template_scan_error", **safe_error_log(e))
        raise self.retry(exc=e)
