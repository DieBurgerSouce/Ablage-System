#!/usr/bin/env python3
"""
Populate Training Samples mit OCR-Text.

Fuellt leere OCRTrainingSample-Eintraege mit echtem OCR-Text aus Surya.
Aktualisiert Status basierend auf Auto-Accept Kriterien.

Ausfuehrung im Container:
  docker exec -it ablage-backend python scripts/populate_training_samples.py --limit 100
"""

import asyncio
import argparse
import sys
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

# UTF-8 Output fuer Windows Console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Projekt-Root zum Path hinzufuegen
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session_context
from app.db.models import OCRTrainingSample, TrainingSampleStatus


# =============================================================================
# Surya OCR Integration
# =============================================================================

_surya_models: dict = {}


def load_surya_models() -> dict:
    """Laedt Surya 0.17.0 Modelle (einmalig, gecached)."""
    global _surya_models

    if _surya_models:
        return _surya_models

    print("[INIT] Lade Surya 0.17.0 Modelle...", flush=True)

    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    from surya.foundation import FoundationPredictor
    from surya.common.surya.schema import TaskNames

    _surya_models["foundation"] = FoundationPredictor()
    print("  -> Foundation Predictor geladen", flush=True)

    _surya_models["detection"] = DetectionPredictor()
    print("  -> Detection Predictor geladen", flush=True)

    _surya_models["recognition"] = RecognitionPredictor(_surya_models["foundation"])
    print("  -> Recognition Predictor geladen", flush=True)

    _surya_models["task_name"] = TaskNames.ocr_with_boxes

    print("[INIT] Surya Modelle bereit!\n", flush=True)
    return _surya_models


def run_surya_ocr(file_path: Path) -> tuple[bool, str, float]:
    """Fuehrt OCR mit Surya 0.17.0 durch."""
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

        # OCR ausfuehren
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
        print(f"    OCR Error: {e}")
        return False, "", 0.0


# =============================================================================
# Auto-Accept Validation
# =============================================================================

def validate_for_auto_accept(text: str, confidence: float) -> tuple[bool, str]:
    """Prueft ob OCR-Ergebnis auto-accepted werden kann."""

    if not text or len(text) < 50:
        return False, "Text zu kurz"

    if confidence < 0.90:  # 90% Threshold fuer pending
        return False, f"Confidence {confidence:.1%} < 90%"

    # Basis-Strukturcheck
    alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
    if alpha_ratio < 0.3:
        return False, "Zu wenig Text-Inhalt"

    if confidence >= 0.95:
        return True, "Auto-accepted (95%+)"

    return False, "Needs review (90-95%)"


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

    return "letter"  # Default


# =============================================================================
# Main Processing
# =============================================================================

async def process_batch(
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, int, int]:
    """Verarbeitet einen Batch von Samples."""

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
        .offset(offset)
    )
    samples = result.scalars().all()

    if not samples:
        return 0, 0, 0

    processed = 0
    auto_accepted = 0
    needs_review = 0

    for sample in samples:
        file_path = Path(sample.file_path)

        # Pruefe ob Datei existiert
        if not file_path.exists():
            print(f"  [{processed+1}] SKIP: Datei nicht gefunden: {file_path.name}")
            processed += 1
            continue

        print(f"  [{processed+1}/{len(samples)}] {file_path.name}...", end=" ", flush=True)

        # OCR ausfuehren
        success, text, confidence = run_surya_ocr(file_path)

        if not success or not text:
            print("OCR FEHLER")
            processed += 1
            continue

        # Auto-Accept pruefen
        should_accept, reason = validate_for_auto_accept(text, confidence)

        # Dokumenttyp erkennen
        doc_type = detect_document_type(text)

        # Sample aktualisieren
        sample.ground_truth_text = text
        sample.auto_acceptance_confidence = confidence
        sample.document_type = doc_type
        sample.source = "surya_batch"

        if should_accept:
            sample.status = TrainingSampleStatus.VERIFIED.value
            sample.auto_accepted = True
            sample.verified_at = datetime.now(timezone.utc)
            auto_accepted += 1
            print(f"VERIFIED ({confidence:.1%}, {doc_type})")
        else:
            sample.status = TrainingSampleStatus.PENDING.value
            sample.auto_accepted = False
            needs_review += 1
            print(f"PENDING ({confidence:.1%}, {reason})")

        processed += 1

        # Commit alle 10 Samples
        if processed % 10 == 0:
            await db.commit()

    # Final commit
    await db.commit()

    return processed, auto_accepted, needs_review


async def main():
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(description="Populate Training Samples mit OCR")
    parser.add_argument("--limit", type=int, default=100, help="Anzahl Samples pro Batch")
    parser.add_argument("--batches", type=int, default=1, help="Anzahl Batches")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  TRAINING SAMPLES POPULATION")
    print("  Surya OCR -> Auto-Accept -> Database Update")
    print("=" * 70)

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
        print(f"\n  Leere pending Samples: {empty_count}")
        print(f"  Verarbeite: {args.limit} x {args.batches} = {args.limit * args.batches} Samples")
        print()

    total_processed = 0
    total_accepted = 0
    total_review = 0

    for batch_num in range(args.batches):
        print(f"\n--- Batch {batch_num + 1}/{args.batches} ---")

        async with get_async_session_context() as db:
            processed, accepted, review = await process_batch(
                db,
                limit=args.limit,
                offset=0,  # Immer von vorne, da wir Status aendern
            )

            total_processed += processed
            total_accepted += accepted
            total_review += review

            if processed == 0:
                print("  Keine weiteren Samples zu verarbeiten.")
                break

    # Zusammenfassung
    print("\n" + "=" * 70)
    print("  ZUSAMMENFASSUNG")
    print("=" * 70)
    print(f"  Verarbeitet:    {total_processed}")
    print(f"  Auto-Accepted:  {total_accepted} ({total_accepted/max(total_processed,1)*100:.1f}%)")
    print(f"  Needs Review:   {total_review} ({total_review/max(total_processed,1)*100:.1f}%)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
