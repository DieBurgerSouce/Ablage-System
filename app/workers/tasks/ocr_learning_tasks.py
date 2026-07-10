# -*- coding: utf-8 -*-
"""
OCR Learning Tasks - Self-Learning Feedback Loop.

Celery-Tasks die die OCR-Korrektur-Queue konsumieren und
daraus Verbesserungen ableiten:

1. consume_correction_queue: Verarbeitet Redis-Queue, generiert/aktualisiert Templates
2. apply_learned_patterns: Wendet gelernte Backend-Gewichte an

Diese Tasks schliessen die Feedback-Loop:
  User-Korrektur -> Redis Queue -> Template-Update -> Backend-Gewichte -> bessere OCR
"""

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func

from app.workers.celery_app import celery_app, CPUTask
from app.core.safe_errors import safe_error_log
from app.core.redis_state import RedisStateManager
from app.db.session import get_worker_session_context
from app.db.models import Document
from app.db.models_ocr_feedback import (
    OCRBackendPerformance,
    OCRCorrectionFeedback,
)
from app.services.monitoring.prometheus_metrics import (
    ocr_corrections_total,
    ocr_correction_queue_length,
    ocr_templates_created_total,
    ocr_templates_updated_total,
    ocr_templates_deactivated_total,
    ocr_template_correction_rate,
    ocr_backend_weight,
    ocr_feedback_processing_duration_seconds,
)

logger = structlog.get_logger(__name__)

# Minimum Korrekturen pro Entity bevor Template-Generierung versucht wird
MIN_CORRECTIONS_FOR_TEMPLATE = 3

# Redis-Key fuer Backend-Gewichte
BACKEND_WEIGHTS_KEY = "ocr_learning:backend_weights"

# Schwellenwerte fuer Template-Deaktivierung/Boost
TEMPLATE_HIGH_CORRECTION_RATE = 0.30  # >30% Korrekturrate = deaktivieren
TEMPLATE_LOW_CORRECTION_RATE = 0.05   # <5% Korrekturrate = Boost erhoehen


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="ocr_learning.consume_correction_queue",
)
def consume_correction_queue(
    self,
    max_items: int = 200,
) -> Dict[str, object]:
    """
    Konsumiere die Redis-Korrektur-Queue und leite Verbesserungen ab.

    Verarbeitet Korrekturen aus ocr_learning:correction_queue:
    1. Gruppiert nach Entity (Lieferant)
    2. Erkennt Template-Kandidaten (>=3 Korrekturen pro Entity)
    3. Generiert/aktualisiert Supplier-OCR-Templates
    4. Aktualisiert Backend-Auswahl-Gewichte basierend auf Fehlermustern

    Args:
        max_items: Maximale Anzahl Queue-Eintraege pro Durchlauf

    Returns:
        Verarbeitungsstatistiken
    """
    task_id = self.request.id

    logger.info(
        "ocr_correction_queue_consumer_starting",
        task_id=task_id,
        max_items=max_items,
    )

    async def _consume_async() -> Dict[str, object]:
        redis = RedisStateManager.get_instance()
        await redis.connect()

        queue_key = "ocr_learning:correction_queue"

        # 1. Pop items aus der Queue
        corrections: List[Dict[str, object]] = []
        for _ in range(max_items):
            raw = await redis._redis.rpop(queue_key)
            if raw is None:
                break
            try:
                item = json.loads(raw)
                corrections.append(item)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    "ocr_correction_queue_invalid_item",
                    error=str(e),
                )

        if not corrections:
            logger.info(
                "ocr_correction_queue_empty",
                task_id=task_id,
            )
            # Queue-Laenge auf 0 setzen
            remaining = await redis._redis.llen(queue_key) or 0
            ocr_correction_queue_length.set(remaining)
            return {
                "success": True,
                "task_id": task_id,
                "items_processed": 0,
                "templates_updated": 0,
                "templates_created": 0,
                "message": "Keine Korrekturen in der Queue",
            }

        # Queue-Laenge nach Pop aktualisieren
        remaining = await redis._redis.llen(queue_key) or 0
        ocr_correction_queue_length.set(remaining)

        logger.info(
            "ocr_correction_queue_items_popped",
            task_id=task_id,
            count=len(corrections),
        )

        # 2. Gruppiere nach Entity (Lieferant)
        entity_corrections: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        backend_error_counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        async with get_worker_session_context() as session:
            for correction in corrections:
                doc_id_str = correction.get("document_id")
                if not doc_id_str:
                    continue

                try:
                    doc_id = UUID(doc_id_str)
                except (ValueError, TypeError):
                    continue

                # Hole Entity-ID aus Dokument
                result = await session.execute(
                    select(
                        Document.business_entity_id,
                        Document.company_id,
                    ).where(Document.id == doc_id)
                )
                row = result.one_or_none()
                if row and row.business_entity_id:
                    entity_key = f"{row.business_entity_id}:{row.company_id}"
                    correction["_entity_id"] = str(row.business_entity_id)
                    correction["_company_id"] = str(row.company_id)
                    entity_corrections[entity_key].append(correction)

                # Backend-Fehler zaehlen fuer Gewichts-Update
                backend = correction.get("ocr_backend", "unknown")
                field = correction.get("field_name", "unknown")
                backend_error_counts[backend][field] += 1

                # Prometheus: Korrektur zaehlen
                company_id_str = correction.get("_company_id", "unknown")
                ocr_corrections_total.labels(
                    field_name=field,
                    backend=backend,
                    company_id=company_id_str,
                ).inc()

        # 3. Template-Generierung/Update fuer Entities mit genuegend Korrekturen
        templates_created = 0
        templates_updated = 0

        async with get_worker_session_context() as session:
            from app.services.ocr.auto_template_service import get_auto_template_service

            template_service = get_auto_template_service()

            for entity_key, entity_corrs in entity_corrections.items():
                if len(entity_corrs) < MIN_CORRECTIONS_FOR_TEMPLATE:
                    continue

                parts = entity_key.split(":", 1)
                if len(parts) != 2:
                    continue

                entity_id = UUID(parts[0])
                company_id = UUID(parts[1])

                try:
                    # Versuche Template-Kandidat zu erkennen
                    candidate = await template_service.detect_template_candidate(
                        db=session,
                        entity_id=entity_id,
                        company_id=company_id,
                    )

                    if candidate and candidate.is_candidate:
                        # Generiere neues Template
                        await template_service.generate_template(
                            db=session,
                            entity_id=entity_id,
                            company_id=company_id,
                            document_ids=candidate.document_ids,
                        )
                        templates_created += 1
                        ocr_templates_created_total.labels(
                            company_id=str(company_id),
                        ).inc()

                        logger.info(
                            "ocr_template_auto_generated",
                            entity_id=str(entity_id),
                            document_count=candidate.document_count,
                            fields=len(candidate.matching_fields),
                        )

                    # Update bestehende Templates mit Korrektur-Daten
                    for corr in entity_corrs:
                        field_name = corr.get("field_name")
                        if not field_name:
                            continue

                        # Bounding Box ist optional - nur updaten wenn vorhanden
                        # Korrekturen ohne Bounding Box werden trotzdem fuer
                        # Confidence-Anpassungen genutzt
                        updated = await template_service.update_template_from_correction(
                            db=session,
                            entity_id=entity_id,
                            company_id=company_id,
                            field_name=field_name,
                            corrected_bounding_box={
                                "x": 0.0, "y": 0.0,
                                "width": 0.0, "height": 0.0,
                            },
                            corrected_value=str(
                                corr.get("corrected_value", "")
                            ),
                        )
                        if updated:
                            templates_updated += 1
                            ocr_templates_updated_total.labels(
                                entity_id=str(entity_id),
                            ).inc()

                except Exception as e:
                    logger.warning(
                        "ocr_template_update_failed",
                        entity_id=str(entity_id),
                        **safe_error_log(e),
                    )

            await session.commit()

        # 4. Backend-Gewichte in Redis aktualisieren
        await _update_backend_weights(redis, backend_error_counts)

        result = {
            "success": True,
            "task_id": task_id,
            "items_processed": len(corrections),
            "entities_with_corrections": len(entity_corrections),
            "templates_created": templates_created,
            "templates_updated": templates_updated,
            "backend_error_summary": {
                backend: dict(fields)
                for backend, fields in backend_error_counts.items()
            },
        }

        logger.info(
            "ocr_correction_queue_consumer_completed",
            **result,
        )

        return result

    start_time = time.monotonic()
    task_result = asyncio.run(_consume_async())
    duration = time.monotonic() - start_time
    ocr_feedback_processing_duration_seconds.labels(
        task_name="consume_correction_queue",
    ).observe(duration)
    return task_result


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="ocr_learning.apply_learned_patterns",
)
def apply_learned_patterns(
    self,
    period_days: int = 30,
) -> Dict[str, object]:
    """
    Wende gelernte Muster an: Backend-Gewichte und Template-Effektivitaet.

    Laeuft taeglich und:
    1. Laedt Backend-Performance aus ocr_backend_performance
    2. Aktualisiert Backend-Auswahl-Gewichte in Redis
    3. Evaluiert Template-Effektivitaet:
       - Templates mit hoher Korrekturrate deaktivieren
       - Templates mit niedriger Korrekturrate boosten
    4. Persistiert gelernte Gewichte in PostgreSQL

    Args:
        period_days: Analysezeitraum in Tagen

    Returns:
        Zusammenfassung der Anpassungen
    """
    task_id = self.request.id

    logger.info(
        "apply_learned_patterns_starting",
        task_id=task_id,
        period_days=period_days,
    )

    async def _apply_async() -> Dict[str, object]:
        redis = RedisStateManager.get_instance()
        await redis.connect()

        period_start = datetime.now(timezone.utc) - timedelta(days=period_days)
        backends_adjusted = 0
        templates_deactivated = 0
        templates_boosted = 0

        async with get_worker_session_context() as session:
            # 1. Lade Backend-Performance-Daten
            perf_query = (
                select(OCRBackendPerformance)
                .where(
                    OCRBackendPerformance.calculated_at >= period_start,
                )
                .order_by(OCRBackendPerformance.calculated_at.desc())
            )
            perf_result = await session.execute(perf_query)
            perf_records = perf_result.scalars().all()

            # 2. Berechne Backend-Gewichte basierend auf Fehlerraten
            backend_weights: Dict[str, Dict[str, float]] = defaultdict(dict)

            for record in perf_records:
                backend = record.backend
                field = record.field_name

                # Basisgewicht 1.0, reduziert durch Fehlerrate
                correction_rate = record.correction_rate or 0.0
                base_weight = max(0.3, 1.0 - correction_rate * 2.0)

                # Umlaut-Penalty fuer deutsche Dokumente
                umlaut_penalty = (record.umlaut_error_rate or 0.0) * 0.5
                # Ziffern-Penalty
                digit_penalty = (record.digit_error_rate or 0.0) * 0.3

                final_weight = max(0.1, base_weight - umlaut_penalty - digit_penalty)
                backend_weights[backend][field] = round(final_weight, 4)

            # 3. Speichere Gewichte in Redis fuer Echtzeit-Nutzung
            if backend_weights:
                weights_data = {
                    "weights": {
                        b: dict(f) for b, f in backend_weights.items()
                    },
                    "calculated_at": datetime.now(timezone.utc).isoformat(),
                    "period_days": period_days,
                }
                await redis._redis.setex(
                    BACKEND_WEIGHTS_KEY,
                    timedelta(days=7),
                    json.dumps(weights_data),
                )
                backends_adjusted = len(backend_weights)

                # Prometheus: Backend-Gewichte als Gauge setzen
                for bk, fields in backend_weights.items():
                    for fn, weight in fields.items():
                        ocr_backend_weight.labels(
                            backend=bk,
                            field_name=fn,
                        ).set(weight)

                logger.info(
                    "backend_weights_updated",
                    backends=backends_adjusted,
                    weights=weights_data["weights"],
                )

            # 4. Template-Effektivitaet evaluieren
            from app.db.models_ocr_template import SupplierOCRTemplate

            # Lade aktive Templates
            template_query = (
                select(SupplierOCRTemplate)
                .where(SupplierOCRTemplate.is_active == True)
            )
            template_result = await session.execute(template_query)
            templates = template_result.scalars().all()

            for template in templates:
                if not template.entity_id:
                    continue

                # Zaehle Korrekturen fuer diese Entity im Zeitraum
                correction_count_query = (
                    select(func.count(OCRCorrectionFeedback.id))
                    .join(
                        Document,
                        Document.id == OCRCorrectionFeedback.document_id,
                    )
                    .where(
                        and_(
                            Document.business_entity_id == template.entity_id,
                            OCRCorrectionFeedback.created_at >= period_start,
                        )
                    )
                )
                corr_count = (
                    await session.execute(correction_count_query)
                ).scalar() or 0

                # Zaehle verarbeitete Dokumente fuer diese Entity
                doc_count_query = (
                    select(func.count(Document.id))
                    .where(
                        and_(
                            Document.business_entity_id == template.entity_id,
                            Document.processed_date >= period_start,
                        )
                    )
                )
                doc_count = (
                    await session.execute(doc_count_query)
                ).scalar() or 0

                if doc_count == 0:
                    continue

                template_correction_rate = corr_count / doc_count

                # Prometheus: Korrekturrate pro Template setzen
                ocr_template_correction_rate.labels(
                    template_id=str(template.id),
                    entity_id=str(template.entity_id),
                ).set(round(template_correction_rate, 4))

                if template_correction_rate > TEMPLATE_HIGH_CORRECTION_RATE:
                    # Template ist ineffektiv -> deaktivieren
                    template.is_active = False
                    template.auto_apply = False
                    templates_deactivated += 1
                    ocr_templates_deactivated_total.inc()

                    logger.warning(
                        "template_deactivated_high_correction_rate",
                        template_id=str(template.id),
                        entity_id=str(template.entity_id),
                        correction_rate=round(template_correction_rate, 3),
                    )

                elif template_correction_rate < TEMPLATE_LOW_CORRECTION_RATE:
                    # Template ist sehr effektiv -> Confidence erhoehen
                    if template.field_definitions:
                        updated_defs = list(template.field_definitions)
                        for field_def in updated_defs:
                            current_boost = field_def.get("confidence_boost", 0.10)
                            # Max 25% Boost
                            field_def["confidence_boost"] = min(
                                0.25, current_boost + 0.02
                            )
                        template.field_definitions = updated_defs
                        templates_boosted += 1

                        logger.info(
                            "template_boosted_low_correction_rate",
                            template_id=str(template.id),
                            entity_id=str(template.entity_id),
                            correction_rate=round(template_correction_rate, 3),
                        )

            await session.commit()

        result = {
            "success": True,
            "task_id": task_id,
            "backends_adjusted": backends_adjusted,
            "backend_weights": {
                b: dict(f) for b, f in backend_weights.items()
            },
            "templates_deactivated": templates_deactivated,
            "templates_boosted": templates_boosted,
            "period_days": period_days,
        }

        logger.info(
            "apply_learned_patterns_completed",
            **result,
        )

        return result

    start_time = time.monotonic()
    task_result = asyncio.run(_apply_async())
    duration = time.monotonic() - start_time
    ocr_feedback_processing_duration_seconds.labels(
        task_name="apply_learned_patterns",
    ).observe(duration)
    return task_result


async def _update_backend_weights(
    redis: RedisStateManager,
    error_counts: Dict[str, Dict[str, int]],
) -> None:
    """
    Aktualisiere Backend-Gewichte inkrementell basierend auf neuen Fehlern.

    Laedt bestehende Gewichte, aktualisiert mit EMA, speichert zurueck.

    Args:
        redis: Redis-Instanz
        error_counts: Fehler-Zaehler pro Backend/Feld
    """
    if not error_counts:
        return

    try:
        # Lade bestehende Gewichte
        existing_raw = await redis._redis.get(BACKEND_WEIGHTS_KEY)
        existing_weights: Dict[str, Dict[str, float]] = {}
        if existing_raw:
            try:
                existing_data = json.loads(existing_raw)
                existing_weights = existing_data.get("weights", {})
            except (json.JSONDecodeError, TypeError) as e:
                # Gespeicherte Gewichte korrupt -> werden verworfen und neu aufgebaut
                logger.warning("backend_weights_corrupt_reset", **safe_error_log(e))

        # EMA-Update: alpha = 0.1 (langsame Anpassung)
        alpha = 0.1
        for backend, field_errors in error_counts.items():
            if backend not in existing_weights:
                existing_weights[backend] = {}

            for field_name, error_count in field_errors.items():
                current = existing_weights[backend].get(field_name, 1.0)
                # Jeder Fehler reduziert das Gewicht leicht
                penalty = min(0.1, error_count * 0.01)
                new_weight = current * (1 - alpha) + (current - penalty) * alpha
                existing_weights[backend][field_name] = round(
                    max(0.1, new_weight), 4
                )

        # Speichere aktualisierte Gewichte
        weights_data = {
            "weights": existing_weights,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "incremental": True,
        }
        await redis._redis.setex(
            BACKEND_WEIGHTS_KEY,
            timedelta(days=7),
            json.dumps(weights_data),
        )

    except Exception as e:
        logger.warning(
            "backend_weights_incremental_update_failed",
            **safe_error_log(e),
        )
