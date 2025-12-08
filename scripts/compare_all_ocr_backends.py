# -*- coding: utf-8 -*-
"""
OCR Backend Vergleich - 6 Backends auf 10 TIF-Dateien.

Vergleicht:
1. Chandra OCR (9B VLM) - GPU
2. DocTR (CPU-optimiert)
3. OlmOCR-2 (7B) - GPU
4. PaddleOCR PP-OCRv5 (CPU)
5. Qwen2.5-VL-7B - GPU
6. Surya CPU (0.17.0)

Metriken:
- Verarbeitungszeit
- Textlaenge
- Umlaut-Erkennung
- Confidence Score
"""

import asyncio
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from tabulate import tabulate

logger = structlog.get_logger(__name__)


# Test files - 10 diverse TIF files from different folders
TEST_FILES = [
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000B.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000C.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000004/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000008/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP00000C/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000010/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000014/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000018/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP00001C/00000009.TIF",
]


def count_umlauts(text: str) -> Dict[str, int]:
    """Zaehle deutsche Umlaute im Text."""
    umlauts = {
        'ae': text.count('ae'),
        'oe': text.count('oe'),
        'ue': text.count('ue'),
        'Ae': text.count('Ae'),
        'Oe': text.count('Oe'),
        'Ue': text.count('Ue'),
        'ss': text.count('ss'),
    }
    return umlauts


def extract_key_info(text: str) -> Dict[str, Any]:
    """Extrahiere wichtige Informationen aus dem Text."""
    import re

    info = {
        "has_iban": bool(re.search(r'[A-Z]{2}\d{2}[\s]?[\d\s]{16,}', text)),
        "has_date": bool(re.search(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', text)),
        "has_euro": bool(re.search(r'\d+[.,]\d{2}\s*(EUR|Euro|€)', text, re.I)),
        "word_count": len(text.split()),
        "line_count": len(text.strip().split('\n')),
    }
    return info


async def test_backend(backend_name: str, agent, file_path: str) -> Dict[str, Any]:
    """Teste ein Backend mit einer Datei."""
    start_time = time.perf_counter()

    try:
        # Process the file
        result = await agent.process({"image_path": file_path, "language": "de"})

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        text = result.get("text", "")

        return {
            "backend": backend_name,
            "file": Path(file_path).name,
            "success": result.get("success", False),
            "text_length": len(text),
            "confidence": result.get("confidence", 0),
            "processing_time_ms": elapsed_ms,
            "umlauts": count_umlauts(text),
            "key_info": extract_key_info(text),
            "text_preview": text[:200] if text else "",
            "error": result.get("error"),
        }

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return {
            "backend": backend_name,
            "file": Path(file_path).name,
            "success": False,
            "text_length": 0,
            "confidence": 0,
            "processing_time_ms": elapsed_ms,
            "umlauts": {},
            "key_info": {},
            "text_preview": "",
            "error": str(e),
        }


async def run_comparison():
    """Fuehre den vollstaendigen Vergleich durch."""

    print("=" * 80)
    print("OCR BACKEND VERGLEICH - 6 Backends auf 10 TIF-Dateien")
    print(f"Gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Verify test files exist
    existing_files = []
    for f in TEST_FILES:
        if Path(f).exists():
            existing_files.append(f)
        else:
            print(f"WARNUNG: Datei nicht gefunden: {f}")

    if len(existing_files) < 10:
        # Find alternative files
        print(f"\nNur {len(existing_files)} Dateien gefunden. Suche Alternativen...")
        import glob
        all_tifs = glob.glob("C:/Users/benfi/Ablage_System/Trainings_Data/**/*.TIF", recursive=True)
        for tif in all_tifs[:10 - len(existing_files)]:
            if tif not in existing_files:
                existing_files.append(tif)

    test_files = existing_files[:10]
    print(f"\nTeste mit {len(test_files)} Dateien:")
    for f in test_files:
        print(f"  - {Path(f).name}")

    # Initialize backends
    print("\n" + "-" * 80)
    print("INITIALISIERE BACKENDS...")
    print("-" * 80)

    backends = {}

    # 1. Surya CPU (immer verfuegbar)
    try:
        from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
        backends["Surya CPU"] = SuryaDoclingAgent()
        print("[OK] Surya CPU initialisiert")
    except Exception as e:
        print(f"[FEHLER] Surya CPU: {e}")

    # 2. DocTR CPU
    try:
        from app.agents.ocr.doctr_agent import DocTRAgent, is_doctr_available
        if is_doctr_available():
            backends["DocTR CPU"] = DocTRAgent()
            print("[OK] DocTR CPU initialisiert")
        else:
            print("[SKIP] DocTR nicht installiert")
    except Exception as e:
        print(f"[FEHLER] DocTR: {e}")

    # 3. PaddleOCR CPU
    try:
        from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent
        backends["PaddleOCR"] = PaddleOCRAgent()
        print("[OK] PaddleOCR initialisiert")
    except Exception as e:
        print(f"[FEHLER] PaddleOCR: {e}")

    # 4. Chandra GPU (4-bit fuer VRAM-Effizienz)
    try:
        import torch
        if torch.cuda.is_available():
            from app.agents.ocr.chandra_agent import ChandraOCRAgent
            backends["Chandra 4bit"] = ChandraOCRAgent(quantization="4bit")
            print("[OK] Chandra 4-bit GPU initialisiert")
        else:
            print("[SKIP] Chandra - keine GPU verfuegbar")
    except Exception as e:
        print(f"[FEHLER] Chandra: {e}")

    # 5. OlmOCR GPU
    try:
        import torch
        if torch.cuda.is_available():
            from app.agents.ocr.olmocr_agent import OlmOCRAgent
            backends["OlmOCR-2"] = OlmOCRAgent()
            print("[OK] OlmOCR-2 GPU initialisiert")
        else:
            print("[SKIP] OlmOCR-2 - keine GPU verfuegbar")
    except Exception as e:
        print(f"[FEHLER] OlmOCR-2: {e}")

    # 6. Qwen GPU
    try:
        import torch
        if torch.cuda.is_available():
            from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent
            backends["Qwen2.5-VL"] = QwenOCRAgent()
            print("[OK] Qwen2.5-VL GPU initialisiert")
        else:
            print("[SKIP] Qwen2.5-VL - keine GPU verfuegbar")
    except Exception as e:
        print(f"[FEHLER] Qwen2.5-VL: {e}")

    print(f"\n{len(backends)} Backends bereit zum Testen")

    # Run tests
    all_results: List[Dict[str, Any]] = []

    for backend_name, agent in backends.items():
        print(f"\n{'=' * 80}")
        print(f"TESTE: {backend_name}")
        print("=" * 80)

        backend_results = []

        for i, file_path in enumerate(test_files):
            print(f"  [{i+1}/{len(test_files)}] {Path(file_path).name}...", end=" ", flush=True)

            result = await test_backend(backend_name, agent, file_path)
            backend_results.append(result)
            all_results.append(result)

            if result["success"]:
                print(f"OK ({result['processing_time_ms']}ms, {result['text_length']} chars)")
            else:
                print(f"FEHLER: {result.get('error', 'Unbekannt')[:50]}")

        # Cleanup nach jedem Backend (GPU Memory freigeben)
        try:
            await agent.cleanup()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        # Backend-Zusammenfassung
        successful = [r for r in backend_results if r["success"]]
        if successful:
            avg_time = sum(r["processing_time_ms"] for r in successful) / len(successful)
            avg_chars = sum(r["text_length"] for r in successful) / len(successful)
            avg_conf = sum(r["confidence"] for r in successful) / len(successful)

            print(f"\n  Zusammenfassung {backend_name}:")
            print(f"    Erfolgreich: {len(successful)}/{len(test_files)}")
            print(f"    Durchschn. Zeit: {avg_time:.0f}ms")
            print(f"    Durchschn. Zeichen: {avg_chars:.0f}")
            print(f"    Durchschn. Confidence: {avg_conf:.2%}")

    # Generate comparison report
    print("\n" + "=" * 80)
    print("VERGLEICHS-REPORT")
    print("=" * 80)

    # Aggregate by backend
    backend_stats = {}
    for result in all_results:
        name = result["backend"]
        if name not in backend_stats:
            backend_stats[name] = {
                "total": 0,
                "successful": 0,
                "total_time_ms": 0,
                "total_chars": 0,
                "total_confidence": 0,
                "total_umlauts": 0,
                "errors": []
            }

        backend_stats[name]["total"] += 1
        if result["success"]:
            backend_stats[name]["successful"] += 1
            backend_stats[name]["total_time_ms"] += result["processing_time_ms"]
            backend_stats[name]["total_chars"] += result["text_length"]
            backend_stats[name]["total_confidence"] += result["confidence"]

            umlauts = result.get("umlauts", {})
            backend_stats[name]["total_umlauts"] += sum(umlauts.values())
        else:
            backend_stats[name]["errors"].append(result.get("error", "Unbekannt"))

    # Create comparison table
    table_data = []
    for name, stats in backend_stats.items():
        success_count = stats["successful"]
        if success_count > 0:
            avg_time = stats["total_time_ms"] / success_count
            avg_chars = stats["total_chars"] / success_count
            avg_conf = stats["total_confidence"] / success_count
            avg_umlauts = stats["total_umlauts"] / success_count
        else:
            avg_time = avg_chars = avg_conf = avg_umlauts = 0

        table_data.append([
            name,
            f"{success_count}/{stats['total']}",
            f"{avg_time:.0f}ms",
            f"{avg_chars:.0f}",
            f"{avg_conf:.2%}",
            f"{avg_umlauts:.1f}",
        ])

    # Sort by success rate, then by speed
    table_data.sort(key=lambda x: (-int(x[1].split("/")[0]), int(x[2].replace("ms", ""))))

    headers = ["Backend", "Erfolg", "Avg Zeit", "Avg Zeichen", "Avg Confidence", "Avg Umlaute"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    # Save detailed results
    output_file = Path(__file__).parent / "ocr_comparison_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "test_files": test_files,
            "backends_tested": list(backends.keys()),
            "results": all_results,
            "summary": {
                name: {
                    "success_rate": f"{stats['successful']}/{stats['total']}",
                    "avg_time_ms": stats["total_time_ms"] / stats["successful"] if stats["successful"] > 0 else 0,
                    "avg_chars": stats["total_chars"] / stats["successful"] if stats["successful"] > 0 else 0,
                    "avg_confidence": stats["total_confidence"] / stats["successful"] if stats["successful"] > 0 else 0,
                }
                for name, stats in backend_stats.items()
            }
        }, f, indent=2, ensure_ascii=False)

    print(f"\nDetaillierte Ergebnisse gespeichert: {output_file}")

    # Print sample text comparison
    print("\n" + "=" * 80)
    print("TEXTVERGLEICH (erste Datei)")
    print("=" * 80)

    first_file_results = [r for r in all_results if r["file"] == Path(test_files[0]).name]
    for result in first_file_results:
        print(f"\n--- {result['backend']} ---")
        if result["success"]:
            preview = result.get("text_preview", "")[:300]
            print(preview)
            print(f"... ({result['text_length']} Zeichen total)")
        else:
            print(f"FEHLER: {result.get('error', 'Unbekannt')}")

    return all_results


if __name__ == "__main__":
    asyncio.run(run_comparison())
