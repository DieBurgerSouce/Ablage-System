# -*- coding: utf-8 -*-
"""
VLM OCR Backend Test - OlmOCR-2 und Qwen2.5-VL

Fokussierter Test der beiden Vision-Language Models auf 5 TIF-Dateien.
Models sind bereits gecached und sollten schnell laden.
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


# Test files - 5 diverse TIF files
TEST_FILES = [
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000B.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000C.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000004/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000008/00000009.TIF",
]


def count_umlauts(text: str) -> int:
    """Zaehle deutsche Umlaute im Text."""
    count = 0
    for umlaut in ['ae', 'oe', 'ue', 'Ae', 'Oe', 'Ue', 'ss']:
        count += text.count(umlaut)
    return count


async def test_backend(backend_name: str, agent, file_path: str) -> Dict[str, Any]:
    """Teste ein Backend mit einer Datei."""
    start_time = time.perf_counter()

    try:
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
            "text_preview": text[:300] if text else "",
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
            "umlauts": 0,
            "text_preview": "",
            "error": str(e),
        }


async def test_olmocr():
    """Teste OlmOCR-2."""
    print("\n" + "=" * 80)
    print("TESTE: OlmOCR-2 (7B VLM)")
    print("=" * 80)

    import torch
    if not torch.cuda.is_available():
        print("[FEHLER] Keine GPU verfuegbar!")
        return []

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM frei: {torch.cuda.mem_get_info()[0] / 1024**3:.1f} GB")

    try:
        print("\nLade OlmOCR-2 Modell (cached)...")
        from app.agents.ocr.olmocr_agent import OlmOCRAgent
        agent = OlmOCRAgent()
        print("[OK] OlmOCR-2 Agent erstellt")
    except Exception as e:
        print(f"[FEHLER] OlmOCR-2 konnte nicht geladen werden: {e}")
        return []

    results = []

    # Find existing test files
    existing_files = [f for f in TEST_FILES if Path(f).exists()]
    if not existing_files:
        import glob
        existing_files = glob.glob("C:/Users/benfi/Ablage_System/Trainings_Data/**/*.TIF", recursive=True)[:5]

    print(f"\nTeste mit {len(existing_files)} Dateien:")

    for i, file_path in enumerate(existing_files[:5]):
        print(f"  [{i+1}/5] {Path(file_path).name}...", end=" ", flush=True)

        result = await test_backend("OlmOCR-2", agent, file_path)
        results.append(result)

        if result["success"]:
            print(f"OK ({result['processing_time_ms']}ms, {result['text_length']} chars)")
        else:
            error_msg = result.get('error', 'Unbekannt')[:80]
            print(f"FEHLER: {error_msg}")

    # Cleanup
    try:
        await agent.cleanup()
        torch.cuda.empty_cache()
        print("\n[OK] GPU Memory freigegeben")
    except Exception:
        pass

    return results


async def test_qwen():
    """Teste Qwen2.5-VL."""
    print("\n" + "=" * 80)
    print("TESTE: Qwen2.5-VL-7B")
    print("=" * 80)

    import torch
    if not torch.cuda.is_available():
        print("[FEHLER] Keine GPU verfuegbar!")
        return []

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM frei: {torch.cuda.mem_get_info()[0] / 1024**3:.1f} GB")

    try:
        print("\nLade Qwen2.5-VL Modell (cached)...")
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent
        agent = QwenOCRAgent()
        print("[OK] Qwen2.5-VL Agent erstellt")
    except Exception as e:
        print(f"[FEHLER] Qwen2.5-VL konnte nicht geladen werden: {e}")
        return []

    results = []

    # Find existing test files
    existing_files = [f for f in TEST_FILES if Path(f).exists()]
    if not existing_files:
        import glob
        existing_files = glob.glob("C:/Users/benfi/Ablage_System/Trainings_Data/**/*.TIF", recursive=True)[:5]

    print(f"\nTeste mit {len(existing_files)} Dateien:")

    for i, file_path in enumerate(existing_files[:5]):
        print(f"  [{i+1}/5] {Path(file_path).name}...", end=" ", flush=True)

        result = await test_backend("Qwen2.5-VL", agent, file_path)
        results.append(result)

        if result["success"]:
            print(f"OK ({result['processing_time_ms']}ms, {result['text_length']} chars)")
        else:
            error_msg = result.get('error', 'Unbekannt')[:80]
            print(f"FEHLER: {error_msg}")

    # Cleanup
    try:
        await agent.cleanup()
        torch.cuda.empty_cache()
        print("\n[OK] GPU Memory freigegeben")
    except Exception:
        pass

    return results


async def main():
    """Hauptfunktion - teste beide VLM Backends nacheinander."""
    print("=" * 80)
    print("VLM OCR BACKEND TEST - OlmOCR-2 & Qwen2.5-VL")
    print(f"Gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    all_results = []

    # Test OlmOCR-2 first
    olmocr_results = await test_olmocr()
    all_results.extend(olmocr_results)

    # Short pause between models
    print("\n--- Pause vor naechstem Backend (5s) ---")
    await asyncio.sleep(5)

    # Test Qwen2.5-VL
    qwen_results = await test_qwen()
    all_results.extend(qwen_results)

    # Print summary
    print("\n" + "=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)

    for backend in ["OlmOCR-2", "Qwen2.5-VL"]:
        backend_results = [r for r in all_results if r["backend"] == backend]
        if backend_results:
            successful = [r for r in backend_results if r["success"]]
            if successful:
                avg_time = sum(r["processing_time_ms"] for r in successful) / len(successful)
                avg_chars = sum(r["text_length"] for r in successful) / len(successful)
                avg_conf = sum(r["confidence"] for r in successful) / len(successful)
                avg_umlauts = sum(r["umlauts"] for r in successful) / len(successful)

                print(f"\n{backend}:")
                print(f"  Erfolgsrate: {len(successful)}/{len(backend_results)}")
                print(f"  Durchschn. Zeit: {avg_time:.0f}ms")
                print(f"  Durchschn. Zeichen: {avg_chars:.0f}")
                print(f"  Durchschn. Confidence: {avg_conf:.2%}")
                print(f"  Durchschn. Umlaute: {avg_umlauts:.1f}")
            else:
                print(f"\n{backend}: Alle {len(backend_results)} Tests fehlgeschlagen")
                for r in backend_results:
                    print(f"  - {r['file']}: {r.get('error', 'Unbekannt')[:60]}")

    # Save results
    output_file = Path(__file__).parent / "vlm_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nErgebnisse gespeichert: {output_file}")

    # Show text samples
    print("\n" + "=" * 80)
    print("TEXTBEISPIELE (erste Datei)")
    print("=" * 80)

    first_file_results = [r for r in all_results if r.get("text_preview")]
    for r in first_file_results[:2]:  # One per backend
        print(f"\n--- {r['backend']} ({r['file']}) ---")
        print(r["text_preview"][:500])
        print(f"... ({r['text_length']} Zeichen total)")

    return all_results


if __name__ == "__main__":
    asyncio.run(main())
