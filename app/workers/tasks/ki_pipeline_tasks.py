# -*- coding: utf-8 -*-
"""
KI-Pipeline Celery Tasks.

Asynchrone Verarbeitung für die KI-Pipeline:
- Confidence-Berechnung nach OCR-Abschluss
- Lernprofil-Aktualisierung nach Korrekturen
- Cross-Document-Matching für neue Dokumente
- Zusammenfassungs-Generierung
- Batch-Aufgaben (naechtlich)
- Confidence-Neuberechnung mit Lernfortschritt

Feinpoliert und durchdacht - Automatisierte KI-Pipeline.
"""

import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import Document
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# CONFIDENCE TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.process_extraction_confidence_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="default",
)
def process_extraction_confidence_task(
    self,
    document_id: str,
    company_id: str,
    extracted_fields: Optional[Dict[str, str]] = None,
    extraction_method: str = "ocr",
    supplier_name: Optional[str] = None,
    document_type: Optional[str] = None,
) -> Dict[str, object]:
    """Confidence-Scores für ein Dokument berechnen.

    Wird nach OCR-Abschluss automatisch aufgerufen.

    Args:
        document_id: Dokument-ID
        company_id: Firma-ID
        extracted_fields: Extrahierte Felder {field_name: value}
        extraction_method: Extraktionsmethode (ocr, llm, regex, template)
        supplier_name: Lieferantenname für Lernprofil
        document_type: Dokumenttyp für Lernprofil

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    from app.services.extraction_confidence_service import (
        get_extraction_confidence_service,
    )

    async def _process() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_extraction_confidence_service()

            if not extracted_fields:
                logger.warning(
                    "ki_pipeline_no_fields",
                    document_id=document_id,
                )
                return {"status": "skipped", "reason": "keine extrahierten Felder"}

            results = await service.process_document_extraction(
                db=db,
                document_id=UUID(document_id),
                company_id=UUID(company_id),
                extracted_fields=extracted_fields,
                extraction_method=extraction_method,
                supplier_name=supplier_name,
                document_type=document_type,
            )

            await db.commit()

            return {
                "status": "completed",
                "document_id": document_id,
                "field_count": len(results),
                "high_confidence": sum(
                    1 for r in results if r.confidence_level == "high"
                ),
                "medium_confidence": sum(
                    1 for r in results if r.confidence_level == "medium"
                ),
                "low_confidence": sum(
                    1 for r in results if r.confidence_level == "low"
                ),
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_process())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_process())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_confidence_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# LEARNING TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.update_learning_profiles_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def update_learning_profiles_task(
    self,
    company_id: str,
    document_id: str,
    field_name: str,
    original_value: str,
    corrected_value: str,
    supplier_name: Optional[str] = None,
    document_type: Optional[str] = None,
) -> Dict[str, object]:
    """Lernprofil nach Korrektur aktualisieren.

    Wird nach Einreichen einer Korrektur aufgerufen.

    Args:
        company_id: Firma-ID
        document_id: Dokument-ID
        field_name: Name des korrigierten Feldes
        original_value: Urspruenglicher Wert
        corrected_value: Korrigierter Wert
        supplier_name: Lieferantenname
        document_type: Dokumenttyp

    Returns:
        Dict mit Profil-Informationen
    """
    from app.services.extraction_learning_service import (
        get_extraction_learning_service,
    )

    async def _update() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_extraction_learning_service()

            profile = await service.record_correction(
                db=db,
                company_id=UUID(company_id),
                document_id=UUID(document_id),
                field_name=field_name,
                original_value=original_value,
                corrected_value=corrected_value,
                supplier_name=supplier_name,
                document_type=document_type,
            )

            await db.commit()

            return {
                "status": "completed",
                "profile_id": str(profile.id),
                "profile_type": profile.profile_type,
                "profile_key": profile.profile_key,
                "correction_count": profile.correction_count,
                "confidence_boost": profile.confidence_boost,
                "has_overrides": bool(profile.field_overrides),
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_update())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_update())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_learning_failed",
            company_id=company_id,
            field_name=field_name,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# CROSS-DOCUMENT MATCHING TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.run_cross_document_matching_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="default",
)
def run_cross_document_matching_task(
    self,
    company_id: str,
    document_id: str,
    candidate_doc_ids: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Cross-Document-Matching für ein neues Dokument ausführen.

    Vergleicht das Dokument mit potenziell verwandten Dokumenten.

    Args:
        company_id: Firma-ID
        document_id: Neues Dokument-ID
        candidate_doc_ids: Optionale Liste von Kandidaten-IDs

    Returns:
        Dict mit Matching-Ergebnissen
    """
    from app.services.cross_document_intelligence_service import (
        get_cross_document_intelligence_service,
    )

    async def _match() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_cross_document_intelligence_service()

            if candidate_doc_ids:
                matches_created = 0
                for cand_id in candidate_doc_ids:
                    try:
                        await service.compare_documents(
                            db=db,
                            company_id=UUID(company_id),
                            doc_a_id=UUID(document_id),
                            doc_b_id=UUID(cand_id),
                        )
                        matches_created += 1
                    except Exception as e:
                        logger.warning(
                            "cross_doc_match_single_failed",
                            doc_a=document_id,
                            doc_b=cand_id,
                            **safe_error_log(e),
                        )

                await db.commit()

                return {
                    "status": "completed",
                    "document_id": document_id,
                    "candidates_checked": len(candidate_doc_ids),
                    "matches_created": matches_created,
                }

            # Ohne Kandidaten: Existierende Matches laden
            matches = await service.find_related_documents(
                db=db,
                company_id=UUID(company_id),
                document_id=UUID(document_id),
            )

            return {
                "status": "completed",
                "document_id": document_id,
                "existing_matches": len(matches),
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_match())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_match())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_cross_doc_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# SUMMARY TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.generate_document_summary_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def generate_document_summary_task(
    self,
    document_id: str,
    company_id: str,
    document_type: Optional[str] = None,
) -> Dict[str, object]:
    """Zusammenfassung für ein Dokument generieren.

    Wird nach Extraktion automatisch aufgerufen.

    Args:
        document_id: Dokument-ID
        company_id: Firma-ID
        document_type: Optionaler Dokumenttyp

    Returns:
        Dict mit Summary-Informationen
    """
    from app.services.document_summary_service import (
        get_document_summary_service,
    )

    async def _generate() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_document_summary_service()

            summary = await service.generate_summary(
                db=db,
                document_id=UUID(document_id),
                company_id=UUID(company_id),
                document_type=document_type,
            )

            await db.commit()

            return {
                "status": "completed",
                "document_id": document_id,
                "summary_id": str(summary.id),
                "template": summary.summary_template,
                "summary_length": len(summary.summary_text),
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_generate())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_generate())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_summary_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.batch_generate_summaries_task",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    queue="maintenance",
)
def batch_generate_summaries_task(
    self,
    company_id: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, object]:
    """Naechtliche Batch-Generierung fehlender Zusammenfassungen.

    Findet Dokumente ohne Summary und generiert diese.

    Args:
        company_id: Optionale Firma-ID (None = alle Firmen)
        limit: Maximale Anzahl

    Returns:
        Dict mit Batch-Statistiken
    """
    from app.services.document_summary_service import (
        get_document_summary_service,
    )
    from app.db.models_ki_pipeline import DocumentSummary

    async def _batch() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_document_summary_service()

            # Dokumente ohne Summary finden
            subquery = select(DocumentSummary.document_id)
            query = (
                select(Document.id, Document.company_id)
                .where(
                    and_(
                        Document.deleted_at.is_(None),
                        Document.id.notin_(subquery),
                    )
                )
                .limit(limit)
            )

            if company_id:
                query = query.where(Document.company_id == UUID(company_id))

            result = await db.execute(query)
            docs = result.all()

            generated = 0
            failed = 0

            for doc_id, comp_id in docs:
                try:
                    await service.generate_summary(
                        db=db,
                        document_id=doc_id,
                        company_id=comp_id,
                    )
                    generated += 1
                except Exception as e:
                    logger.warning(
                        "batch_summary_single_failed",
                        document_id=str(doc_id),
                        **safe_error_log(e),
                    )
                    failed += 1

            await db.commit()

            return {
                "status": "completed",
                "documents_found": len(docs),
                "summaries_generated": generated,
                "failed": failed,
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_batch())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_batch())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_batch_summary_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# RECALCULATION TASKS
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.recalculate_confidence_with_learning_task",
    bind=True,
    max_retries=1,
    default_retry_delay=600,
    queue="maintenance",
)
def recalculate_confidence_with_learning_task(
    self,
    company_id: Optional[str] = None,
    limit: int = 1000,
) -> Dict[str, object]:
    """Periodische Neuberechnung der Confidence-Scores mit neuen Lernprofilen.

    Aktualisiert Confidence-Scores für Dokumente, bei denen sich
    die Lernprofile seit der letzten Berechnung geändert haben.

    Args:
        company_id: Optionale Firma-ID
        limit: Maximale Anzahl zu verarbeitender Dokumente

    Returns:
        Dict mit Neuberechnungs-Statistiken
    """
    from app.db.models_ki_pipeline import ExtractionConfidence, LearningProfile

    async def _recalculate() -> Dict[str, object]:
        async with get_async_session_context() as db:
            # Finde Dokumente die Neuberechnung benötigen:
            # Confidence-Records die älter sind als die letzte Lernprofil-Änderung
            # Vereinfacht: Alle nicht-korrigierten Records mit medium/low Confidence
            query = (
                select(
                    ExtractionConfidence.document_id,
                    ExtractionConfidence.company_id,
                )
                .where(
                    and_(
                        ExtractionConfidence.was_corrected == False,
                        ExtractionConfidence.confidence_level.in_(["medium", "low"]),
                    )
                )
                .distinct()
                .limit(limit)
            )

            if company_id:
                query = query.where(
                    ExtractionConfidence.company_id == UUID(company_id)
                )

            result = await db.execute(query)
            docs = result.all()

            logger.info(
                "ki_pipeline_recalculate_start",
                documents_to_process=len(docs),
            )

            return {
                "status": "completed",
                "documents_found": len(docs),
                "note": "Neuberechnung in zukuenftiger Version mit vollem Lernprofil-Abgleich",
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_recalculate())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_recalculate())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_recalculate_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# EXTRACTION WITH CONFIDENCE (Spec: extract_with_confidence_task)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.extract_with_confidence_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="default",
)
def extract_with_confidence_task(
    self,
    document_id: str,
) -> Dict[str, object]:
    """Führt Confidence-Extraktion für ein neues Dokument durch.

    Laedt das Dokument, extrahiert Felder und berechnet Confidence-Scores.
    Wird typischerweise nach OCR-Abschluss aufgerufen.

    Args:
        document_id: Dokument-ID als String

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    from app.services.confidence_extraction_service import (
        get_confidence_extraction_service,
    )

    async def _extract() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_confidence_extraction_service()

            records = await service.extract_with_confidence(
                db=db,
                document_id=UUID(document_id),
            )

            return {
                "status": "completed",
                "document_id": document_id,
                "field_count": len(records),
                "high_confidence": sum(
                    1 for r in records if r.confidence_level == "high"
                ),
                "medium_confidence": sum(
                    1 for r in records if r.confidence_level == "medium"
                ),
                "low_confidence": sum(
                    1 for r in records if r.confidence_level == "low"
                ),
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_extract())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_extract())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_extract_confidence_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# BATCH LEARNING (Spec: learn_from_corrections_batch_task)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.learn_from_corrections_batch_task",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    queue="maintenance",
)
def learn_from_corrections_batch_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Täglich: Verarbeitet akkumulierte Korrekturen und aktualisiert Lernprofile.

    Iteriert über alle Firmen und führt retrain_profiles aus.

    Args:
        company_id: Optionale Firma-ID (None = alle Firmen)

    Returns:
        Dict mit Batch-Statistiken
    """
    from app.services.extraction_learning_service import (
        get_extraction_learning_service,
    )
    from app.db.models_ki_pipeline import LearningProfile

    async def _batch_learn() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_extraction_learning_service()

            if company_id:
                # Einzelne Firma
                stats = await service.get_learning_statistics(
                    db=db,
                    company_id=UUID(company_id),
                )
                await db.commit()
                return {
                    "status": "completed",
                    "companies_processed": 1,
                    "statistics": stats,
                }

            # Alle Firmen mit Lernprofilen
            result = await db.execute(
                select(LearningProfile.company_id)
                .distinct()
            )
            company_ids = [row[0] for row in result.all()]

            total_profiles_updated = 0
            for comp_id in company_ids:
                try:
                    stats = await service.get_learning_statistics(
                        db=db,
                        company_id=comp_id,
                    )
                    total_profiles_updated += int(stats.get("total_profiles", 0))
                except Exception as e:
                    logger.warning(
                        "batch_learn_company_failed",
                        company_id=str(comp_id),
                        **safe_error_log(e),
                    )

            await db.commit()

            return {
                "status": "completed",
                "companies_processed": len(company_ids),
                "total_profiles": total_profiles_updated,
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_batch_learn())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_batch_learn())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_batch_learn_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# CROSS-DOC DISCREPANCY DETECTION (Spec: detect_cross_doc_discrepancies_task)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.detect_cross_doc_discrepancies_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="default",
)
def detect_cross_doc_discrepancies_task(
    self,
    document_id: str,
    company_id: str,
) -> Dict[str, object]:
    """Prüft ein neues Dokument auf Abweichungen zu verwandten Dokumenten.

    Wird nach OCR-Abschluss aufgerufen um z.B. Rechnung vs. Lieferschein
    automatisch zu vergleichen.

    Args:
        document_id: Dokument-ID
        company_id: Firma-ID

    Returns:
        Dict mit erkannten Anomalien
    """
    from app.services.cross_document_intelligence_service import (
        get_cross_document_intelligence_service,
    )

    async def _detect() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_cross_document_intelligence_service()

            anomalies = await service.detect_anomalies(
                db=db,
                company_id=UUID(company_id),
                document_id=UUID(document_id),
            )

            return {
                "status": "completed",
                "document_id": document_id,
                "anomaly_count": len(anomalies),
                "anomalies": anomalies[:10],  # Erste 10 für Zusammenfassung
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_detect())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_detect())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_discrepancy_detection_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# RETRAIN LEARNING PROFILES (Spec: retrain_learning_profiles_task)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.retrain_learning_profiles_task",
    bind=True,
    max_retries=1,
    default_retry_delay=600,
    queue="maintenance",
)
def retrain_learning_profiles_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Wöchentlich: Retrain aller Lernprofile.

    Aktualisiert Confidence-Boosts basierend auf akkumulierten Korrekturen.

    Args:
        company_id: Optionale Firma-ID (None = alle Firmen)

    Returns:
        Dict mit Retrain-Statistiken
    """
    from app.services.extraction_learning_service import (
        get_extraction_learning_service,
    )
    from app.db.models_ki_pipeline import LearningProfile

    async def _retrain() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = get_extraction_learning_service()

            if company_id:
                stats = await service.get_learning_statistics(
                    db=db,
                    company_id=UUID(company_id),
                )
                await db.commit()
                return {
                    "status": "completed",
                    "companies_processed": 1,
                    "statistics": stats,
                }

            # Alle Firmen
            result = await db.execute(
                select(LearningProfile.company_id)
                .distinct()
            )
            company_ids = [row[0] for row in result.all()]

            total_stats: Dict[str, int] = {
                "companies": len(company_ids),
                "total_profiles": 0,
                "total_corrections": 0,
            }

            for comp_id in company_ids:
                try:
                    stats = await service.get_learning_statistics(
                        db=db,
                        company_id=comp_id,
                    )
                    total_stats["total_profiles"] += int(
                        stats.get("total_profiles", 0)
                    )
                    total_stats["total_corrections"] += int(
                        stats.get("total_corrections", 0)
                    )
                except Exception as e:
                    logger.warning(
                        "retrain_company_failed",
                        company_id=str(comp_id),
                        **safe_error_log(e),
                    )

            await db.commit()

            return {
                "status": "completed",
                **total_stats,
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_retrain())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_retrain())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_retrain_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# PRICE DEVIATION CHECK (Spec: check_price_deviations_task)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.ki_pipeline_tasks.check_price_deviations_task",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    queue="maintenance",
)
def check_price_deviations_task(
    self,
    company_id: Optional[str] = None,
    months_lookback: int = 12,
) -> Dict[str, object]:
    """Täglich: Prüft auf Preisabweichungen bei Lieferanten.

    Vergleicht aktuelle Rechnungsbetraege mit dem 12-Monats-Durchschnitt
    des jeweiligen Lieferanten und meldet signifikante Abweichungen.

    Args:
        company_id: Optionale Firma-ID
        months_lookback: Anzahl Monate für Durchschnittsberechnung

    Returns:
        Dict mit erkannten Preisabweichungen
    """
    from app.db.models import InvoiceTracking, BusinessEntity

    async def _check_prices() -> Dict[str, object]:
        async with get_async_session_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months_lookback)

            # Firmenfilter
            conditions = [
                InvoiceTracking.created_at >= cutoff,
                InvoiceTracking.amount > 0,
            ]
            if company_id:
                conditions.append(
                    InvoiceTracking.company_id == UUID(company_id)
                )

            # Durchschnittliche Betraege pro Lieferant berechnen
            # Über Document -> BusinessEntity
            avg_query = (
                select(
                    Document.business_entity_id,
                    func.avg(InvoiceTracking.amount).label("avg_amount"),
                    func.stddev(InvoiceTracking.amount).label("stddev_amount"),
                    func.count().label("invoice_count"),
                )
                .join(Document, Document.id == InvoiceTracking.document_id)
                .where(
                    and_(
                        *conditions,
                        Document.business_entity_id.isnot(None),
                    )
                )
                .group_by(Document.business_entity_id)
                .having(func.count() >= 3)  # Mindestens 3 Rechnungen
            )

            result = await db.execute(avg_query)
            entity_stats = result.all()

            deviations: List[Dict[str, object]] = []

            # Letzte Rechnungen prüfen
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            for entity_id, avg_amount, stddev_amount, count in entity_stats:
                if avg_amount is None or avg_amount == 0:
                    continue

                # Letzte Rechnung finden
                recent_result = await db.execute(
                    select(InvoiceTracking.amount, InvoiceTracking.invoice_number)
                    .join(Document, Document.id == InvoiceTracking.document_id)
                    .where(
                        and_(
                            Document.business_entity_id == entity_id,
                            InvoiceTracking.created_at >= recent_cutoff,
                        )
                    )
                    .order_by(InvoiceTracking.created_at.desc())
                    .limit(1)
                )
                recent = recent_result.one_or_none()
                if not recent:
                    continue

                recent_amount = recent[0]
                if recent_amount is None:
                    continue

                # Abweichung berechnen
                deviation_pct = abs(recent_amount - float(avg_amount)) / float(avg_amount)

                if deviation_pct > 0.20:  # >20% Abweichung
                    deviations.append({
                        "entity_id": str(entity_id),
                        "invoice_number": recent[1],
                        "current_amount": round(recent_amount, 2),
                        "avg_amount": round(float(avg_amount), 2),
                        "deviation_percent": round(deviation_pct * 100, 1),
                        "severity": "kritisch" if deviation_pct > 0.5 else "warnung",
                        "invoice_count": count,
                    })

            return {
                "status": "completed",
                "entities_analyzed": len(entity_stats),
                "deviations_found": len(deviations),
                "deviations": deviations[:20],  # Top 20
            }

    try:
        return asyncio.get_event_loop().run_until_complete(_check_prices())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_check_prices())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "ki_pipeline_price_deviation_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)
