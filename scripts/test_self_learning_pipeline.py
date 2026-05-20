#!/usr/bin/env python3
"""
Self-Learning Pipeline Test fuer Ablage-System OCR.

Testet die komplette Pipeline mit 50 Dokumenten aus Trainings_Data:
1. OCR mit Surya durchfuehren
2. Auto Ground-Truth Validierung
3. LLM Review mit qwen2.5:14b
4. Ergebnisse auswerten

Ausfuehrung: python scripts/test_self_learning_pipeline.py
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

# UTF-8 Output fuer Windows Console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

# Projekt-Root zum Path hinzufuegen
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class DocumentResult:
    """Ergebnis fuer ein einzelnes Dokument."""
    filename: str
    ocr_success: bool = False
    ocr_text: str = ""
    ocr_confidence: float = 0.0
    ocr_time_ms: int = 0

    # Auto Ground-Truth
    auto_accepted: bool = False
    auto_accept_reasons: list = field(default_factory=list)
    umlaut_score: float = 0.0

    # LLM Review
    llm_reviewed: bool = False
    llm_quality_score: float = 0.0
    llm_recommendation: str = ""
    llm_corrected_text: Optional[str] = None
    llm_issues: list = field(default_factory=list)
    llm_time_ms: int = 0

    error: Optional[str] = None


@dataclass
class PipelineStats:
    """Gesamtstatistiken der Pipeline."""
    total_documents: int = 0
    ocr_success: int = 0
    ocr_failed: int = 0
    auto_accepted: int = 0
    auto_rejected: int = 0
    llm_accepted: int = 0
    llm_rejected: int = 0
    llm_needs_human: int = 0
    avg_ocr_time_ms: float = 0.0
    avg_llm_time_ms: float = 0.0
    avg_ocr_confidence: float = 0.0
    avg_llm_quality: float = 0.0
    umlaut_accuracy: float = 0.0


# LLM Review Prompt (gleich wie im Service)
REVIEW_SYSTEM_PROMPT = """Du bist ein spezialisierter OCR-Qualitaetsprufer fuer deutsche Geschaeftsdokumente.

Deine Aufgabe ist es, OCR-extrahierten Text zu analysieren und zu bewerten.
Du bist Experte fuer:
- Deutsche Rechtschreibung und Grammatik
- Umlaute (ae, oe, ue, ss) und ihre OCR-typischen Fehler
- Geschaeftsdokumente (Rechnungen, Vertraege, Briefe)
- OCR-typische Fehler (0/O Verwechslung, l/1 Verwechslung, etc.)

Sei praezise und kritisch. Qualitaet ist wichtiger als Quantitaet."""

REVIEW_USER_PROMPT = """Analysiere diesen OCR-Text und bewerte seine Qualitaet.

Dokumenttyp: {doc_type}

OCR-Text:
<ocr_text>
{text}
</ocr_text>

Bewerte folgende Aspekte:
1. Semantische Korrektheit - Macht der Text inhaltlich Sinn?
2. OCR-Fehler - Typische Erkennungsfehler (0/O, l/1, rn/m, etc.)
3. Umlaute - Korrekte deutsche Umlaute (ae/ae, oe/oe, ue/ue, ss/ss)
4. Strukturelle Vollstaendigkeit - Sind wichtige Felder erkennbar?

Antworte EXAKT im folgenden Format:

<quality_score>[Zahl 1-10]</quality_score>

<issues>
- [Problem 1]
- [Problem 2]
</issues>

<corrected_text>
[Korrigierter Text falls Korrekturen noetig, sonst UNCHANGED]
</corrected_text>

<recommendation>[accept|reject|needs_human]</recommendation>

<reasoning>
[Deine Begruendung hier]
</reasoning>"""


# Global Surya models (lazy loaded)
_surya_models: dict = {}


def _load_surya_models() -> dict:
    """Laedt Surya 0.17.0 Modelle (einmalig, gecached)."""
    global _surya_models

    if _surya_models:
        return _surya_models

    print("  [INIT] Lade Surya 0.17.0 Modelle...", flush=True)

    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    from surya.foundation import FoundationPredictor
    from surya.common.surya.schema import TaskNames

    _surya_models["foundation"] = FoundationPredictor()
    print("    -> Foundation Predictor geladen", flush=True)

    _surya_models["detection"] = DetectionPredictor()
    print("    -> Detection Predictor geladen", flush=True)

    _surya_models["recognition"] = RecognitionPredictor(_surya_models["foundation"])
    print("    -> Recognition Predictor geladen", flush=True)

    _surya_models["task_name"] = TaskNames.ocr_with_boxes

    print("  [INIT] Surya Modelle bereit!\n", flush=True)
    return _surya_models


def run_surya_ocr_sync(file_path: Path) -> tuple[bool, str, float, int]:
    """Fuehrt OCR mit Surya 0.17.0 durch (synchron)."""
    from PIL import Image
    import pypdfium2 as pdfium

    start_time = time.perf_counter()

    try:
        # Modelle laden (gecached)
        models = _load_surya_models()
        det_predictor = models["detection"]
        rec_predictor = models["recognition"]
        task_name = models["task_name"]

        # Bilder laden
        images = []
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            pdf = pdfium.PdfDocument(str(file_path))
            for page_num in range(len(pdf)):
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
            return False, "Keine Bilder geladen", 0.0, int((time.perf_counter() - start_time) * 1000)

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
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        return True, text, avg_confidence, elapsed_ms

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        import traceback
        return False, f"Surya Error: {str(e)}\n{traceback.format_exc()[:500]}", 0.0, elapsed_ms


def estimate_confidence(text: str) -> float:
    """Schaetzt OCR-Confidence basierend auf Textqualitaet."""
    if not text or len(text) < 10:
        return 0.0

    # Faktoren fuer Confidence
    score = 1.0

    # Zu viele Sonderzeichen = niedrige Confidence
    special_ratio = sum(1 for c in text if not c.isalnum() and c not in " \n.,;:-()") / len(text)
    if special_ratio > 0.3:
        score *= 0.7

    # Zu wenig Buchstaben = niedrige Confidence
    alpha_ratio = sum(1 for c in text if c.isalpha()) / len(text)
    if alpha_ratio < 0.4:
        score *= 0.8

    # Deutsche Woerter vorhanden = hoehere Confidence
    german_words = ["und", "der", "die", "das", "ist", "von", "mit", "fuer", "zur", "vom"]
    text_lower = text.lower()
    german_found = sum(1 for w in german_words if w in text_lower)
    if german_found >= 3:
        score *= 1.1

    return min(max(score, 0.0), 1.0)


def check_auto_accept(text: str, confidence: float) -> tuple[bool, list, float]:
    """Prueft ob OCR-Ergebnis auto-accepted werden kann."""

    reasons = []

    # 1. Confidence Check (>= 95%)
    if confidence < 0.95:
        reasons.append(f"Confidence zu niedrig: {confidence:.1%}")

    # 2. Minimale Textlaenge (>= 50 Zeichen)
    if len(text) < 50:
        reasons.append(f"Text zu kurz: {len(text)} Zeichen")

    # 3. Umlaut-Validierung
    umlaut_score = calculate_umlaut_score(text)
    if umlaut_score < 0.8:
        reasons.append(f"Umlaut-Score zu niedrig: {umlaut_score:.1%}")

    # 4. Strukturelle Plausibilitaet
    if not has_basic_structure(text):
        reasons.append("Strukturelle Probleme erkannt")

    should_accept = len(reasons) == 0
    return should_accept, reasons, umlaut_score


def calculate_umlaut_score(text: str) -> float:
    """Berechnet Umlaut-Score (0-1)."""

    # Zaehle echte Umlaute vs. ASCII-Ersetzungen
    real_umlauts = len([c for c in text if c in "aeoeueAeOeUess"])
    ascii_umlauts = 0

    # Zaehle ASCII-Ersetzungen in Woertern
    import re
    ascii_patterns = [
        r'\b\w*ae\w*\b',  # ae in Woertern
        r'\b\w*oe\w*\b',  # oe in Woertern
        r'\b\w*ue\w*\b',  # ue in Woertern (aber nicht "que")
    ]

    for pattern in ascii_patterns:
        matches = re.findall(pattern, text.lower())
        # Filtere false positives
        for match in matches:
            if not any(fp in match for fp in ["que", "due", "sue", "true", "blue"]):
                ascii_umlauts += 1

    if real_umlauts + ascii_umlauts == 0:
        return 1.0  # Keine Umlaute erwartet

    return real_umlauts / max(real_umlauts + ascii_umlauts, 1)


def has_basic_structure(text: str) -> bool:
    """Prueft grundlegende Textstruktur."""

    # Mindestens ein paar Woerter
    words = text.split()
    if len(words) < 5:
        return False

    # Nicht nur Sonderzeichen
    alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
    if alpha_ratio < 0.3:
        return False

    return True


async def run_llm_review(
    client: httpx.AsyncClient,
    text: str,
    model: str = "qwen2.5:14b",
) -> tuple[float, str, Optional[str], list, int]:
    """Fuehrt LLM-Review durch."""

    start_time = time.perf_counter()

    try:
        # Prompt zusammenbauen
        prompt = REVIEW_USER_PROMPT.format(
            doc_type="unknown",
            text=text[:4000],  # Limit fuer Token
        )

        # Ollama API aufrufen
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": f"{REVIEW_SYSTEM_PROMPT}\n\n{prompt}",
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 1000,
                },
            },
            timeout=120.0,
        )

        if response.status_code != 200:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return 0.0, "error", None, [f"HTTP {response.status_code}"], elapsed_ms

        data = response.json()
        content = data.get("response", "")

        # Antwort parsen
        import re

        # Quality Score
        score_match = re.search(r'<quality_score>\s*(\d+(?:\.\d+)?)\s*</quality_score>', content)
        quality_score = float(score_match.group(1)) if score_match else 5.0

        # Recommendation
        rec_match = re.search(r'<recommendation>\s*(accept|reject|needs_human)\s*</recommendation>', content)
        recommendation = rec_match.group(1) if rec_match else "needs_human"

        # Corrected Text
        corrected_match = re.search(r'<corrected_text>(.*?)</corrected_text>', content, re.DOTALL)
        corrected_text = None
        if corrected_match:
            corrected = corrected_match.group(1).strip()
            if corrected and corrected.upper() != "UNCHANGED":
                corrected_text = corrected

        # Issues
        issues_match = re.search(r'<issues>(.*?)</issues>', content, re.DOTALL)
        issues = []
        if issues_match:
            for line in issues_match.group(1).strip().split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    issues.append(line[1:].strip())

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return quality_score, recommendation, corrected_text, issues, elapsed_ms

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return 0.0, "error", None, [str(e)], elapsed_ms


async def process_document(
    ollama_client: httpx.AsyncClient,
    file_path: Path,
) -> DocumentResult:
    """Verarbeitet ein einzelnes Dokument durch die Pipeline."""

    result = DocumentResult(filename=file_path.name)

    # 1. OCR mit Surya (synchron, da GPU-Model)
    print(f"    [OCR] {file_path.name}...", end=" ", flush=True)
    ocr_success, ocr_text, confidence, ocr_time = run_surya_ocr_sync(file_path)

    result.ocr_success = ocr_success
    result.ocr_time_ms = ocr_time

    if not ocr_success:
        result.error = ocr_text
        print(f"FEHLER ({ocr_time}ms)")
        return result

    result.ocr_text = ocr_text
    result.ocr_confidence = confidence
    print(f"OK ({len(ocr_text)} chars, {confidence:.1%}, {ocr_time}ms)")

    # 2. Auto Ground-Truth Check
    print(f"    [AUTO] Pruefe Auto-Accept...", end=" ", flush=True)
    auto_accepted, reasons, umlaut_score = check_auto_accept(ocr_text, confidence)

    result.auto_accepted = auto_accepted
    result.auto_accept_reasons = reasons
    result.umlaut_score = umlaut_score

    if auto_accepted:
        print(f"AKZEPTIERT (Umlaut: {umlaut_score:.1%})")
    else:
        print(f"ABGELEHNT: {', '.join(reasons[:2])}")

    # 3. LLM Review (fuer alle, nicht nur rejected)
    print(f"    [LLM] Review mit qwen2.5:14b...", end=" ", flush=True)
    quality, rec, corrected, issues, llm_time = await run_llm_review(
        ollama_client, ocr_text
    )

    result.llm_reviewed = True
    result.llm_quality_score = quality
    result.llm_recommendation = rec
    result.llm_corrected_text = corrected
    result.llm_issues = issues
    result.llm_time_ms = llm_time

    status = "AKZEPTIERT" if rec == "accept" else ("ABGELEHNT" if rec == "reject" else "MANUELL")
    print(f"{status} (Score: {quality}/10, {llm_time}ms)")

    if issues:
        print(f"         Issues: {', '.join(issues[:3])}")

    return result


def print_summary(results: list[DocumentResult], stats: PipelineStats) -> None:
    """Gibt Zusammenfassung aus."""

    print("\n")
    print("=" * 80)
    print("  SELF-LEARNING PIPELINE TEST - ZUSAMMENFASSUNG")
    print("=" * 80)

    print(f"\n  Dokumente verarbeitet: {stats.total_documents}")
    print()

    # OCR Stats
    print("  OCR (Surya):")
    print(f"    - Erfolgreich:      {stats.ocr_success} ({stats.ocr_success/stats.total_documents*100:.1f}%)")
    print(f"    - Fehlgeschlagen:   {stats.ocr_failed}")
    print(f"    - Durchschnitt:     {stats.avg_ocr_time_ms:.0f}ms pro Dokument")
    print(f"    - Avg Confidence:   {stats.avg_ocr_confidence:.1%}")
    print()

    # Auto Ground-Truth Stats
    print("  Auto Ground-Truth:")
    print(f"    - Auto-Akzeptiert:  {stats.auto_accepted} ({stats.auto_accepted/max(stats.ocr_success,1)*100:.1f}%)")
    print(f"    - Abgelehnt:        {stats.auto_rejected}")
    print(f"    - Umlaut-Accuracy:  {stats.umlaut_accuracy:.1%}")
    print()

    # LLM Review Stats
    print("  LLM Review (qwen2.5:14b):")
    print(f"    - Akzeptiert:       {stats.llm_accepted} ({stats.llm_accepted/max(stats.ocr_success,1)*100:.1f}%)")
    print(f"    - Abgelehnt:        {stats.llm_rejected}")
    print(f"    - Needs Human:      {stats.llm_needs_human}")
    print(f"    - Avg Quality:      {stats.avg_llm_quality:.1f}/10")
    print(f"    - Avg Zeit:         {stats.avg_llm_time_ms:.0f}ms pro Dokument")
    print()

    # Pipeline Bewertung
    print("-" * 80)

    if stats.ocr_success >= stats.total_documents * 0.9:
        print("  [OK] OCR-Erfolgsrate >= 90%")
    else:
        print("  [!!] OCR-Erfolgsrate < 90% - Verbesserung noetig")

    if stats.umlaut_accuracy >= 0.8:
        print("  [OK] Umlaut-Accuracy >= 80%")
    else:
        print("  [!!] Umlaut-Accuracy < 80% - LLM-Korrektur empfohlen")

    if stats.llm_accepted >= stats.ocr_success * 0.6:
        print("  [OK] LLM-Akzeptanzrate >= 60%")
    else:
        print("  [!!] LLM-Akzeptanzrate < 60% - OCR-Qualitaet verbessern")

    total_accepted = stats.auto_accepted + stats.llm_accepted
    print(f"\n  GESAMT VERWENDBAR: {total_accepted}/{stats.total_documents} ({total_accepted/stats.total_documents*100:.1f}%)")
    print()

    # Empfehlung
    if stats.avg_llm_quality >= 7:
        print("  EMPFEHLUNG: Pipeline ist produktionsreif!")
    elif stats.avg_llm_quality >= 5:
        print("  EMPFEHLUNG: Pipeline nutzbar, LLM-Korrektur aktivieren")
    else:
        print("  EMPFEHLUNG: OCR-Backend wechseln oder mehr Training noetig")

    print()


async def main() -> None:
    """Hauptfunktion des Pipeline-Tests."""

    print("\n" + "=" * 80)
    print("  SELF-LEARNING PIPELINE TEST")
    print("  Teste Surya OCR -> Auto Ground-Truth -> LLM Review (qwen2.5:14b)")
    print("=" * 80)

    # Training-Ordner
    training_dir = Path("C:/Users/benfi/Ablage_System/Trainings_Data/UP000000")

    if not training_dir.exists():
        print(f"\n  FEHLER: Training-Ordner nicht gefunden: {training_dir}")
        return

    # Dokumente sammeln (PDFs und TIFs)
    # Konfigurierbar: MAX_DOCS als Argument oder Default 10
    import sys
    max_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    documents = sorted(
        [f for f in training_dir.iterdir() if f.suffix.upper() in [".PDF", ".TIF", ".TIFF"]]
    )[:max_docs]

    print(f"\n  Gefunden: {len(documents)} Dokumente in {training_dir}")
    print(f"  Teste: erste {max_docs} Dokumente (Argument: python script.py <anzahl>)")
    print()

    # HTTP Client fuer Ollama
    async with httpx.AsyncClient() as ollama_client:

        results: list[DocumentResult] = []

        print("-" * 80)
        print("  VERARBEITUNG")
        print("-" * 80)

        for i, doc_path in enumerate(documents, 1):
            print(f"\n  [{i}/{len(documents)}] {doc_path.name}")

            result = await process_document(ollama_client, doc_path)
            results.append(result)

        # Statistiken berechnen
        stats = PipelineStats()
        stats.total_documents = len(results)

        ocr_times = []
        llm_times = []
        confidences = []
        qualities = []
        umlaut_scores = []

        for r in results:
            if r.ocr_success:
                stats.ocr_success += 1
                ocr_times.append(r.ocr_time_ms)
                confidences.append(r.ocr_confidence)
                umlaut_scores.append(r.umlaut_score)

                if r.auto_accepted:
                    stats.auto_accepted += 1
                else:
                    stats.auto_rejected += 1

                if r.llm_reviewed:
                    llm_times.append(r.llm_time_ms)
                    qualities.append(r.llm_quality_score)

                    if r.llm_recommendation == "accept":
                        stats.llm_accepted += 1
                    elif r.llm_recommendation == "reject":
                        stats.llm_rejected += 1
                    else:
                        stats.llm_needs_human += 1
            else:
                stats.ocr_failed += 1

        stats.avg_ocr_time_ms = sum(ocr_times) / max(len(ocr_times), 1)
        stats.avg_llm_time_ms = sum(llm_times) / max(len(llm_times), 1)
        stats.avg_ocr_confidence = sum(confidences) / max(len(confidences), 1)
        stats.avg_llm_quality = sum(qualities) / max(len(qualities), 1)
        stats.umlaut_accuracy = sum(umlaut_scores) / max(len(umlaut_scores), 1)

        # Zusammenfassung nur am Ende ausgeben
        print_summary(results, stats)


if __name__ == "__main__":
    asyncio.run(main())
