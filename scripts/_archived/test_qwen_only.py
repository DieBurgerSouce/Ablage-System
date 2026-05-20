# -*- coding: utf-8 -*-
"""
Qwen2.5-VL-7B OCR Test - Fokussiert nur auf Qwen.

Das Modell ist vollstaendig gecached und sollte schnell laden.
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
import torch

logger = structlog.get_logger(__name__)


# Test files
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
            "text_preview": text[:500] if text else "",
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


async def main():
    """Teste Qwen2.5-VL-7B."""
    print("=" * 80)
    print("QWEN2.5-VL-7B OCR TEST")
    print(f"Gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    if not torch.cuda.is_available():
        print("[FEHLER] Keine GPU verfuegbar!")
        return

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM gesamt: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print(f"VRAM frei: {torch.cuda.mem_get_info()[0] / 1024**3:.1f} GB")

    # Find test files
    existing_files = [f for f in TEST_FILES if Path(f).exists()]
    if not existing_files:
        import glob
        existing_files = glob.glob("C:/Users/benfi/Ablage_System/Trainings_Data/**/*.TIF", recursive=True)[:5]

    print(f"\nTeste mit {len(existing_files)} Dateien")

    # Load Qwen agent
    print("\n" + "-" * 40)
    print("Lade Qwen2.5-VL-7B Modell (cached)...")
    print("-" * 40)

    try:
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent
        agent = QwenOCRAgent()
        print("[OK] Qwen2.5-VL Agent erstellt")
    except Exception as e:
        print(f"[FEHLER] Qwen2.5-VL konnte nicht geladen werden: {e}")
        import traceback
        traceback.print_exc()
        return

    results = []

    print("\n" + "-" * 40)
    print("STARTE TESTS")
    print("-" * 40)

    for i, file_path in enumerate(existing_files[:5]):
        print(f"\n[{i+1}/5] {Path(file_path).name}")
        print(f"  VRAM vor: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")

        result = await test_backend("Qwen2.5-VL", agent, file_path)
        results.append(result)

        print(f"  VRAM nach: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")

        if result["success"]:
            print(f"  [OK] {result['processing_time_ms']}ms, {result['text_length']} chars, conf={result['confidence']:.2%}")
            print(f"  Text-Preview: {result['text_preview'][:100]}...")
        else:
            print(f"  [FEHLER] {result.get('error', 'Unbekannt')[:100]}")

    # Summary
    print("\n" + "=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    if successful:
        avg_time = sum(r["processing_time_ms"] for r in successful) / len(successful)
        avg_chars = sum(r["text_length"] for r in successful) / len(successful)
        avg_conf = sum(r["confidence"] for r in successful) / len(successful)
        avg_umlauts = sum(r["umlauts"] for r in successful) / len(successful)

        print(f"Erfolgreich: {len(successful)}/{len(results)}")
        print(f"Durchschn. Zeit: {avg_time:.0f}ms")
        print(f"Durchschn. Zeichen: {avg_chars:.0f}")
        print(f"Durchschn. Confidence: {avg_conf:.2%}")
        print(f"Durchschn. Umlaute: {avg_umlauts:.1f}")

    if failed:
        print(f"\nFehlgeschlagen: {len(failed)}")
        for r in failed:
            print(f"  - {r['file']}: {r.get('error', 'Unbekannt')[:60]}")

    # Cleanup
    print("\nCleanup...")
    try:
        await agent.cleanup()
        torch.cuda.empty_cache()
        print(f"[OK] GPU Memory nach Cleanup: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
    except Exception as e:
        print(f"[WARNUNG] Cleanup fehlgeschlagen: {e}")

    # Save results
    output_file = Path(__file__).parent / "qwen_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "model": "Qwen2.5-VL-7B-Instruct",
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nErgebnisse gespeichert: {output_file}")

    # Show full text of first successful result
    if successful:
        print("\n" + "=" * 80)
        print("VOLLSTAENDIGER TEXT (erste Datei)")
        print("=" * 80)
        print(successful[0]["text_preview"])

    return results


if __name__ == "__main__":
    asyncio.run(main())
