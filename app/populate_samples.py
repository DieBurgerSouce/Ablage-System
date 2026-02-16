#!/usr/bin/env python3
"""
Populate Training Samples mit OCR-Text.

Fuellt leere OCRTrainingSample-Einträge mit echtem OCR-Text aus Surya.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session_context
from app.db.models import OCRTrainingSample, TrainingSampleStatus
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Surya OCR Integration
# =============================================================================

_surya_models: dict = {}


def load_surya_models() -> dict:
    """Laedt Surya 0.17.0 Modelle (einmalig, gecached)."""
    global _surya_models

    if _surya_models:
        return _surya_models

    logger.info("surya_models_loading")

    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    from surya.foundation import FoundationPredictor
    from surya.common.surya.schema import TaskNames

    _surya_models["foundation"] = FoundationPredictor()
    logger.info("foundation_predictor_loaded")

    _surya_models["detection"] = DetectionPredictor()
    logger.info("detection_predictor_loaded")

    _surya_models["recognition"] = RecognitionPredictor(_surya_models["foundation"])
    logger.info("recognition_predictor_loaded")

    _surya_models["task_name"] = TaskNames.ocr_with_boxes

    logger.info("surya_models_ready")
    return _surya_models


def run_surya_ocr(file_path: Path) -> tuple[bool, str, float]:
    """Führt OCR mit Surya 0.17.0 durch."""
    from PIL import Image
    import pypdfium2 as pdfium

    try:
        models = load_surya_models()
        det_predictor = models["detection"]
        rec_predictor = models["recognition"]
        task_name = models["task_name"]

        # Bilder laden
        images = []
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            pdf = pdfium.PdfDocument(str(file_path))
            for page_num in range(min(len(pdf), 10)):  # Max 10 Seiten
                page = pdf[page_num]
                pil_image = page.render(scale=300/72).to_pil()
                images.append(pil_image)
            pdf.close()
        else:
            img = Image.open(file_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)

        if not images:
            return False, "", 0.0

        # OCR ausführen
        all_text = []
        total_confidence = 0.0
        total_blocks = 0

        for image in images:
            predictions = rec_predictor(
                [image],
                task_names=[task_name],
                det_predictor=det_predictor,
            )

            if predictions and len(predictions) > 0:
                pred = predictions[0]
                if hasattr(pred, "text_lines"):
                    page_text = []
                    for line in pred.text_lines:
                        text = line.text if hasattr(line, "text") else str(line)
                        conf = line.confidence if hasattr(line, "confidence") else 0.0
                        if text and text.strip():
                            page_text.append(text)
                            total_confidence += conf
                            total_blocks += 1
                    all_text.append("\n".join(page_text))

        text = "\n\n".join(all_text)
        avg_confidence = (total_confidence / total_blocks) if total_blocks > 0 else 0.0

        return True, text, avg_confidence

    except Exception as e:
        logger.error("ocr_error", **safe_error_log(e))
        return False, "", 0.0


def detect_document_type(text: str) -> Optional[str]:
    """Erkennt Dokumenttyp aus Text."""
    text_lower = text.lower()

    if any(w in text_lower for w in ["rechnung", "invoice", "rechnungsnummer", "rechnungsdatum"]):
        return "invoice"
    if any(w in text_lower for w in ["vertrag", "contract", "vereinbarung"]):
        return "contract"
    if any(w in text_lower for w in ["lieferschein", "delivery", "versand"]):
        return "delivery_note"
    if any(w in text_lower for w in ["bestellung", "order", "auftrag"]):
        return "order_confirmation"

    return "letter"


async def process_batch(limit: int = 50) -> tuple[int, int, int]:
    """Verarbeitet einen Batch von Samples."""

    async with get_async_session_context() as db:
        # Hole pending Samples ohne Text
        result = await db.execute(
            select(OCRTrainingSample)
            .where(
                and_(
                    OCRTrainingSample.status == TrainingSampleStatus.PENDING.value,
                    OCRTrainingSample.ground_truth_text == "",
                    OCRTrainingSample.file_path.isnot(None),
                )
            )
            .order_by(OCRTrainingSample.created_at)
            .limit(limit)
        )
        samples = result.scalars().all()

        if not samples:
            logger.info("no_empty_samples_found")
            return 0, 0, 0

        logger.info("processing_samples", count=len(samples))

        processed = 0
        auto_accepted = 0
        needs_review = 0

        for sample in samples:
            file_path = Path(sample.file_path)

            # Prüfe ob Datei existiert
            if not file_path.exists():
                logger.warning("file_not_found", index=processed+1, filename=file_path.name)
                processed += 1
                continue

            logger.info("processing_file", index=processed+1, total=len(samples), filename=file_path.name)

            # OCR ausführen
            success, text, confidence = run_surya_ocr(file_path)

            if not success or not text:
                logger.error("ocr_failed", filename=file_path.name)
                processed += 1
                continue

            # Dokumenttyp erkennen
            doc_type = detect_document_type(text)

            # Sample aktualisieren
            sample.ground_truth_text = text
            sample.auto_acceptance_confidence = confidence
            sample.document_type = doc_type
            sample.source = "surya_batch"

            # Auto-Accept bei 95%+ Confidence
            if confidence >= 0.95:
                sample.status = TrainingSampleStatus.VERIFIED.value
                sample.auto_accepted = True
                sample.verified_at = datetime.now(timezone.utc)
                auto_accepted += 1
                logger.info("sample_verified", confidence=confidence, doc_type=doc_type)
            else:
                sample.status = TrainingSampleStatus.PENDING.value
                sample.auto_accepted = False
                needs_review += 1
                logger.info("sample_pending_review", confidence=confidence, doc_type=doc_type)

            processed += 1

            # Commit nach jedem Sample (wichtig bei langen OCR-Tasks)
            await db.commit()
            logger.debug("sample_saved_to_db")

        return processed, auto_accepted, needs_review


async def main():
    """Hauptfunktion."""
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    logger.info("training_samples_population_starting")

    # Zaehle leere Samples
    async with get_async_session_context() as db:
        count_result = await db.execute(
            select(func.count(OCRTrainingSample.id))
            .where(
                and_(
                    OCRTrainingSample.status == TrainingSampleStatus.PENDING.value,
                    OCRTrainingSample.ground_truth_text == "",
                )
            )
        )
        empty_count = count_result.scalar() or 0
        logger.info("empty_pending_samples_count", count=empty_count, limit=limit)

    processed, accepted, review = await process_batch(limit)

    logger.info("training_samples_population_completed",
                processed=processed,
                auto_accepted=accepted,
                needs_review=review)


if __name__ == "__main__":
    asyncio.run(main())
