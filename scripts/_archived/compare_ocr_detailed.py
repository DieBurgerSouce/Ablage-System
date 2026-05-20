# -*- coding: utf-8 -*-
"""
Detaillierter OCR-Vergleich auf 10 Dokumenten.
Speichert vollstaendige Texte fuer manuelle Analyse.
"""
import asyncio
import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime

# Windows encoding fix
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

# 10 verschiedene Testdokumente aus verschiedenen Ordnern
TEST_FILES = [
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000B.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000004/00000400.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000008/00000800.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP00000C/00000C00.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000010/00001000.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000014/00001400.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000018/00001800.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP00001C/00001C00.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000020/00002000.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000024/00002400.TIF",
]

OUTPUT_DIR = Path("C:/Users/benfi/Ablage_System/ocr_comparison_results")


def test_doctr(image_path: str) -> dict:
    """Test DocTR direkt."""
    try:
        from doctr.io import DocumentFile
        from doctr.models import ocr_predictor

        start = time.perf_counter()
        model = ocr_predictor(pretrained=True)
        doc = DocumentFile.from_images([image_path])
        result = model(doc)

        text_lines = []
        total_conf = 0.0
        word_count = 0

        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    line_text = ' '.join([word.value for word in line.words])
                    text_lines.append(line_text)
                    for word in line.words:
                        total_conf += word.confidence
                        word_count += 1

        text = '\n'.join(text_lines)
        confidence = total_conf / word_count if word_count > 0 else 0.0
        elapsed = time.perf_counter() - start

        return {
            "backend": "DocTR",
            "success": True,
            "time": elapsed,
            "chars": len(text),
            "words": word_count,
            "confidence": confidence,
            "text": text
        }
    except Exception as e:
        return {"backend": "DocTR", "success": False, "error": str(e)}


async def test_surya(image_path: str) -> dict:
    """Test Surya CPU."""
    try:
        from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
        agent = SuryaDoclingAgent()
        start = time.perf_counter()
        result = await agent.process({"image_path": image_path, "language": "de"})
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            return {
                "backend": "Surya",
                "success": True,
                "time": elapsed,
                "chars": len(text),
                "words": len(text.split()),
                "confidence": result.get('confidence', 0),
                "text": text
            }
        else:
            return {"backend": "Surya", "success": False, "error": result.get('error', 'Kein Text')}
    except Exception as e:
        return {"backend": "Surya", "success": False, "error": str(e)}


async def test_got_ocr(image_path: str) -> dict:
    """Test GOT-OCR 2.0."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {"backend": "GOT-OCR", "success": False, "error": "No GPU"}

        from app.agents.ocr.got_ocr_agent import GOTOCRAgent
        agent = GOTOCRAgent()
        start = time.perf_counter()
        result = await agent.process({
            "image_path": image_path,
            "language": "de",
            "document_id": f"test-{Path(image_path).stem}"
        })
        elapsed = time.perf_counter() - start

        if result.get("success") and result.get("text"):
            text = result["text"]
            return {
                "backend": "GOT-OCR",
                "success": True,
                "time": elapsed,
                "chars": len(text),
                "words": len(text.split()),
                "confidence": result.get('confidence', 0),
                "text": text
            }
        else:
            return {"backend": "GOT-OCR", "success": False, "error": result.get('error', 'Kein Text')}
    except Exception as e:
        return {"backend": "GOT-OCR", "success": False, "error": str(e)}
    finally:
        try:
            import torch
            torch.cuda.empty_cache()
        except:
            pass


async def process_document(doc_idx: int, image_path: str, output_dir: Path) -> dict:
    """Verarbeite ein Dokument mit allen Backends."""
    doc_name = Path(image_path).stem
    print(f"\n{'='*60}")
    print(f"DOKUMENT {doc_idx + 1}/10: {doc_name}")
    print(f"{'='*60}")

    results = {"document": doc_name, "path": image_path, "backends": {}}

    # DocTR
    print(f"  DocTR...", end=" ", flush=True)
    doctr_result = test_doctr(image_path)
    if doctr_result.get("success"):
        print(f"OK ({doctr_result['time']:.1f}s, {doctr_result['chars']} chars)")
    else:
        print(f"FEHLER: {doctr_result.get('error', 'Unknown')[:50]}")
    results["backends"]["DocTR"] = doctr_result

    # Surya
    print(f"  Surya...", end=" ", flush=True)
    surya_result = await test_surya(image_path)
    if surya_result.get("success"):
        print(f"OK ({surya_result['time']:.1f}s, {surya_result['chars']} chars)")
    else:
        print(f"FEHLER: {surya_result.get('error', 'Unknown')[:50]}")
    results["backends"]["Surya"] = surya_result

    # GOT-OCR
    print(f"  GOT-OCR...", end=" ", flush=True)
    got_result = await test_got_ocr(image_path)
    if got_result.get("success"):
        print(f"OK ({got_result['time']:.1f}s, {got_result['chars']} chars)")
    else:
        print(f"FEHLER: {got_result.get('error', 'Unknown')[:50]}")
    results["backends"]["GOT-OCR"] = got_result

    # Speichere Texte einzeln
    doc_dir = output_dir / doc_name
    doc_dir.mkdir(parents=True, exist_ok=True)

    for backend_name, backend_result in results["backends"].items():
        if backend_result.get("success") and backend_result.get("text"):
            text_file = doc_dir / f"{backend_name.lower().replace('-', '_')}.txt"
            with open(text_file, "w", encoding="utf-8") as f:
                f.write(f"Backend: {backend_name}\n")
                f.write(f"Dokument: {doc_name}\n")
                f.write(f"Zeit: {backend_result['time']:.1f}s\n")
                f.write(f"Zeichen: {backend_result['chars']}\n")
                f.write(f"Woerter: {backend_result['words']}\n")
                f.write(f"Confidence: {backend_result['confidence']:.1%}\n")
                f.write(f"\n{'='*60}\n")
                f.write(f"TEXT:\n")
                f.write(f"{'='*60}\n\n")
                f.write(backend_result["text"])

    return results


async def main():
    print("="*60)
    print("DETAILLIERTER OCR-BACKEND VERGLEICH")
    print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Anzahl Dokumente: {len(TEST_FILES)}")
    print("="*60)

    # Pruefe ob alle Dateien existieren
    existing_files = []
    for f in TEST_FILES:
        if Path(f).exists():
            existing_files.append(f)
        else:
            print(f"WARNUNG: {f} nicht gefunden!")

    if not existing_files:
        print("FEHLER: Keine Testdateien gefunden!")
        return

    print(f"\n{len(existing_files)} Testdateien gefunden.\n")

    # Output-Verzeichnis erstellen
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []

    for idx, file_path in enumerate(existing_files):
        result = await process_document(idx, file_path, OUTPUT_DIR)
        all_results.append(result)

    # Zusammenfassung speichern
    summary_file = OUTPUT_DIR / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        # Entferne Text aus Summary (zu gross)
        summary = []
        for r in all_results:
            doc_summary = {"document": r["document"], "path": r["path"], "backends": {}}
            for backend, data in r["backends"].items():
                doc_summary["backends"][backend] = {
                    k: v for k, v in data.items() if k != "text"
                }
            summary.append(doc_summary)
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Zusammenfassung ausgeben
    print("\n" + "="*60)
    print("ZUSAMMENFASSUNG")
    print("="*60)

    # Statistiken pro Backend
    backends = ["DocTR", "Surya", "GOT-OCR"]
    stats = {b: {"success": 0, "total_time": 0, "total_chars": 0, "total_conf": 0} for b in backends}

    for result in all_results:
        for backend in backends:
            data = result["backends"].get(backend, {})
            if data.get("success"):
                stats[backend]["success"] += 1
                stats[backend]["total_time"] += data.get("time", 0)
                stats[backend]["total_chars"] += data.get("chars", 0)
                stats[backend]["total_conf"] += data.get("confidence", 0)

    print(f"\n{'Backend':<12} | {'Erfolg':<8} | {'Avg Zeit':<10} | {'Avg Chars':<10} | {'Avg Conf':<10}")
    print("-"*60)
    for backend in backends:
        s = stats[backend]
        if s["success"] > 0:
            avg_time = s["total_time"] / s["success"]
            avg_chars = s["total_chars"] / s["success"]
            avg_conf = s["total_conf"] / s["success"]
            print(f"{backend:<12} | {s['success']}/{len(existing_files):<6} | {avg_time:>7.1f}s | {avg_chars:>10.0f} | {avg_conf:>9.1%}")
        else:
            print(f"{backend:<12} | 0/{len(existing_files):<6} | {'N/A':>8} | {'N/A':>10} | {'N/A':>10}")

    print(f"\nErgebnisse gespeichert in: {OUTPUT_DIR}")
    print("Einzelne Textdateien pro Dokument und Backend verfuegbar.")


if __name__ == "__main__":
    asyncio.run(main())
