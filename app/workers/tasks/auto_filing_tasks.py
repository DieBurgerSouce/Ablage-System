# -*- coding: utf-8 -*-
"""
Celery Tasks fuer automatische Dokumentenablage und Matching.

Feature #7: Automation 2.0
- auto_file_new_documents_task: Neue Dokumente automatisch ablegen
- train_filing_model_task: Woechentlich Filing-Modelle trainieren
- auto_match_documents_task: Einzelnes Dokument matchen
- batch_match_documents_task: Taeglich Batch-Matching durchfuehren
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, select

from app.core.datetime_utils import utc_now
from app.db.models import Company, Document
from app.db.models_approval_extended import AutoFilingRule
from app.db.session import get_sync_session
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.auto_file_new_documents_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def auto_file_new_documents_task(
    self,
    company_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, object]:
    """Legt neue/unklassifizierte Dokumente automatisch ab.

    Wird regelmaessig via Celery Beat ausgefuehrt.
    Sucht Dokumente ohne Kategorie und versucht sie automatisch abzulegen.

    Args:
        company_id: Optional: Nur fuer diese Firma
        limit: Max. Anzahl Dokumente pro Durchlauf

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte automatische Dokumentenablage...")

    async def _process() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_filing_service import (
            AutoFilingService,
        )

        total_processed = 0
        total_filed = 0
        total_skipped = 0
        errors: List[str] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    # Unklassifizierte Dokumente finden
                    doc_stmt = (
                        select(Document)
                        .where(
                            and_(
                                Document.company_id == cid,
                                Document.category.is_(None),
                            )
                        )
                        .order_by(Document.created_at.desc())
                        .limit(limit)
                    )
                    doc_result = await db.execute(doc_stmt)
                    documents = doc_result.scalars().all()

                    if not documents:
                        continue

                    service = AutoFilingService(db)

                    for doc in documents:
                        total_processed += 1
                        result = await service.auto_file_document(
                            db, cid, doc.id
                        )

                        if result.filed:
                            total_filed += 1
                        else:
                            total_skipped += 1

                    await db.commit()

                except Exception as exc:
                    error_msg = (
                        f"Fehler bei Auto-Filing fuer "
                        f"Company {cid}: {exc}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)

        return {
            "processed": total_processed,
            "filed": total_filed,
            "skipped": total_skipped,
            "companies_processed": len(company_ids),
            "errors": errors,
        }

    result = asyncio.run(_process())

    logger.info(
        "Auto-Filing abgeschlossen: %d verarbeitet, %d abgelegt, "
        "%d uebersprungen",
        result.get("processed", 0),
        result.get("filed", 0),
        result.get("skipped", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.train_filing_model_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def train_filing_model_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Trainiert Filing-Modelle basierend auf historischen Daten.

    Wird woechentlich via Celery Beat ausgefuehrt.
    Aktualisiert Accuracy-Werte und Trainingsstatistiken.

    Args:
        company_id: Optional: Nur fuer diese Firma

    Returns:
        Dict mit Trainings-Statistiken
    """
    logger.info("Starte Filing-Modell-Training...")

    async def _train() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_filing_service import (
            AutoFilingService,
        )

        training_results: List[Dict[str, object]] = []
        errors: List[str] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    service = AutoFilingService(db)

                    # Alle aktiven Regeln laden
                    rules_stmt = select(AutoFilingRule).where(
                        and_(
                            AutoFilingRule.company_id == cid,
                            AutoFilingRule.is_active.is_(True),
                        )
                    )
                    rules_result = await db.execute(rules_stmt)
                    rules = rules_result.scalars().all()

                    for rule in rules:
                        try:
                            result = await service.train_model(
                                db, cid, rule.id
                            )
                            training_results.append(result)
                        except Exception as exc:
                            error_msg = (
                                f"Fehler beim Training von Regel "
                                f"{rule.id}: {exc}"
                            )
                            errors.append(error_msg)
                            logger.error(error_msg)

                    await db.commit()

                except Exception as exc:
                    error_msg = (
                        f"Fehler beim Training fuer "
                        f"Company {cid}: {exc}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)

        return {
            "models_trained": len(training_results),
            "companies_processed": len(company_ids),
            "results": training_results,
            "errors": errors,
        }

    result = asyncio.run(_train())

    logger.info(
        "Filing-Modell-Training abgeschlossen: %d Modelle trainiert",
        result.get("models_trained", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.auto_match_documents_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def auto_match_documents_task(
    self,
    company_id: str,
    document_id: str,
    confidence_threshold: float = 0.8,
) -> Dict[str, object]:
    """Matched ein einzelnes Dokument mit potenziellen Partnern.

    Wird ausgeloest wenn ein neues Dokument verarbeitet wurde.

    Args:
        company_id: ID der Firma
        document_id: ID des Dokuments
        confidence_threshold: Mindest-Confidence

    Returns:
        Dict mit Match-Ergebnissen
    """
    logger.info(
        "Starte Auto-Matching fuer Dokument %s...", document_id
    )

    async def _match() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_matching_service import (
            AutoMatchingService,
        )

        async with get_async_session_context() as db:
            service = AutoMatchingService(db)

            saved_matches = await service.auto_match_and_save(
                db,
                UUID(company_id),
                UUID(document_id),
                confidence_threshold,
            )

            await db.commit()

            return {
                "document_id": document_id,
                "matches_found": len(saved_matches),
                "matches": [
                    {
                        "match_id": str(m.id),
                        "matched_document_id": str(
                            m.matched_document_id
                        ),
                        "match_type": m.match_type,
                        "confidence": m.confidence,
                    }
                    for m in saved_matches
                ],
            }

    result = asyncio.run(_match())

    logger.info(
        "Auto-Matching abgeschlossen fuer %s: %d Matches",
        document_id,
        result.get("matches_found", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.batch_match_documents_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def batch_match_documents_task(
    self,
    company_id: Optional[str] = None,
    confidence_threshold: float = 0.8,
    limit: int = 200,
) -> Dict[str, object]:
    """Batch-Matching: Sucht Matches fuer ungematchte Dokumente.

    Wird taeglich via Celery Beat ausgefuehrt.
    Verarbeitet Dokumente die noch keine Matching-Partner haben.

    Args:
        company_id: Optional: Nur fuer diese Firma
        confidence_threshold: Mindest-Confidence
        limit: Max. Anzahl Dokumente pro Durchlauf

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte Batch-Dokumenten-Matching...")

    async def _batch_match() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_matching_service import (
            AutoMatchingService,
        )

        total_processed = 0
        total_matches = 0
        errors: List[str] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    service = AutoMatchingService(db)

                    # Ungematchte Dokumente holen
                    unmatched = await service.get_unmatched_documents(
                        db, cid, limit=limit
                    )

                    for doc_info in unmatched:
                        doc_id_str = str(doc_info.get("document_id", ""))
                        if not doc_id_str:
                            continue

                        total_processed += 1

                        try:
                            saved = await service.auto_match_and_save(
                                db,
                                cid,
                                UUID(doc_id_str),
                                confidence_threshold,
                            )
                            total_matches += len(saved)
                        except Exception as exc:
                            logger.warning(
                                "Match-Fehler fuer Dokument %s: %s",
                                doc_id_str,
                                str(exc),
                            )

                    await db.commit()

                except Exception as exc:
                    error_msg = (
                        f"Fehler beim Batch-Matching fuer "
                        f"Company {cid}: {exc}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)

        return {
            "processed": total_processed,
            "matches_found": total_matches,
            "companies_processed": len(company_ids),
            "errors": errors,
        }

    result = asyncio.run(_batch_match())

    logger.info(
        "Batch-Matching abgeschlossen: %d verarbeitet, %d Matches",
        result.get("processed", 0),
        result.get("matches_found", 0),
    )

    return result
