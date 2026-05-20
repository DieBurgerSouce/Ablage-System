# -*- coding: utf-8 -*-
"""
Vergleichstest: Qwen2.5-VL-7B vs Surya OCR

Testet beide Backends auf 10 TIF-Dateien aus Trainings_Data
und vergleicht technische Performance sowie inhaltliche Qualitaet.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch


def get_test_files(count: int = 10) -> List[str]:
    """Hole 10 TIF-Dateien aus Trainings_Data."""
    trainings_path = Path("Trainings_Data/UP00001C")
    tif_files = sorted(trainings_path.glob("*.TIF"))[:count]
    return [str(f) for f in tif_files]


def count_umlauts(text: str) -> Dict[str, int]:
    """Zaehle deutsche Umlaute im Text."""
    umlauts = {
        "ae": text.count("\u00e4"),
        "oe": text.count("\u00f6"),
        "ue": text.count("\u00fc"),
        "Ae": text.count("\u00c4"),
        "Oe": text.count("\u00d6"),
        "Ue": text.count("\u00dc"),
        "ss": text.count("\u00df"),
    }
    umlauts["total"] = sum(umlauts.values())
    return umlauts


async def test_surya(test_files: List[str]) -> Dict[str, Any]:
    """Teste Surya OCR auf allen Dateien."""
    print("\n" + "=" * 60)
    print("=== SURYA OCR TEST (CPU) ===")
    print("=" * 60)

    from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent

    agent = SuryaDoclingAgent()
    results = []
    total_start = time.time()

    for i, file_path in enumerate(test_files):
        print(f"\n[{i+1}/{len(test_files)}] Verarbeite: {Path(file_path).name}")
        start = time.time()

        try:
            result = await agent.process({"image_path": file_path, "language": "de"})
            elapsed = time.time() - start

            text = result.get("text", "")
            umlauts = count_umlauts(text)

            results.append({
                "file": Path(file_path).name,
                "success": result.get("success", False),
                "chars": len(text),
                "words": len(text.split()) if text else 0,
                "umlauts": umlauts["total"],
                "time_s": round(elapsed, 2),
                "text_preview": text[:200] if text else "",
            })

            print(f"    -> {len(text)} Zeichen, {umlauts['total']} Umlaute, {elapsed:.2f}s")

        except Exception as e:
            print(f"    -> FEHLER: {e}")
            results.append({
                "file": Path(file_path).name,
                "success": False,
                "error": str(e),
                "time_s": time.time() - start,
            })

    total_time = time.time() - total_start

    # Cleanup
    await agent.cleanup()

    return {
        "backend": "surya",
        "display_name": "Surya + Docling (CPU)",
        "total_time_s": round(total_time, 2),
        "avg_time_s": round(total_time / len(test_files), 2),
        "vram_gb": 0,
        "results": results,
        "success_rate": sum(1 for r in results if r.get("success", False)) / len(results),
        "total_chars": sum(r.get("chars", 0) for r in results),
        "total_umlauts": sum(r.get("umlauts", 0) for r in results),
    }


async def test_qwen(test_files: List[str]) -> Dict[str, Any]:
    """Teste Qwen OCR auf allen Dateien."""
    print("\n" + "=" * 60)
    print("=== QWEN2.5-VL-7B OCR TEST (GPU) ===")
    print("=" * 60)

    if not torch.cuda.is_available():
        print("WARNUNG: Keine GPU verfuegbar!")
        return {"backend": "qwen", "error": "No GPU available"}

    # Pruefen ob Modell vollstaendig heruntergeladen wurde
    cache_path = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-VL-7B-Instruct"
    if cache_path.exists():
        total_size = sum(f.stat().st_size for f in cache_path.rglob("*") if f.is_file())
        size_gb = total_size / (1024**3)
        print(f"Modell-Cache: {size_gb:.2f} GB")
        if size_gb < 13:
            print("WARNUNG: Modell scheint nicht vollstaendig heruntergeladen!")
            print("Download wird beim ersten Aufruf fortgesetzt...")

    from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

    agent = QwenOCRAgent()
    results = []
    total_start = time.time()

    # VRAM vor dem Test
    vram_before = torch.cuda.memory_allocated() / (1024**3)
    peak_vram = 0

    for i, file_path in enumerate(test_files):
        print(f"\n[{i+1}/{len(test_files)}] Verarbeite: {Path(file_path).name}")
        start = time.time()

        try:
            result = await agent.process({"image_path": file_path, "language": "de"})
            elapsed = time.time() - start

            # VRAM-Peak tracken
            current_vram = torch.cuda.memory_allocated() / (1024**3)
            peak_vram = max(peak_vram, current_vram)

            text = result.get("text", "")
            umlauts = count_umlauts(text)

            results.append({
                "file": Path(file_path).name,
                "success": result.get("success", False),
                "chars": len(text),
                "words": len(text.split()) if text else 0,
                "umlauts": umlauts["total"],
                "time_s": round(elapsed, 2),
                "vram_gb": round(current_vram, 2),
                "text_preview": text[:200] if text else "",
            })

            print(f"    -> {len(text)} Zeichen, {umlauts['total']} Umlaute, {elapsed:.2f}s, {current_vram:.1f}GB VRAM")

        except Exception as e:
            print(f"    -> FEHLER: {e}")
            results.append({
                "file": Path(file_path).name,
                "success": False,
                "error": str(e),
                "time_s": time.time() - start,
            })

    total_time = time.time() - total_start

    # Cleanup
    await agent.cleanup()
    torch.cuda.empty_cache()

    return {
        "backend": "qwen",
        "display_name": "Qwen2.5-VL-7B (GPU)",
        "total_time_s": round(total_time, 2),
        "avg_time_s": round(total_time / len(test_files), 2),
        "vram_gb": round(peak_vram, 2),
        "results": results,
        "success_rate": sum(1 for r in results if r.get("success", False)) / len(results),
        "total_chars": sum(r.get("chars", 0) for r in results),
        "total_umlauts": sum(r.get("umlauts", 0) for r in results),
    }


def print_comparison(surya: Dict, qwen: Dict):
    """Drucke Vergleichstabelle."""
    print("\n" + "=" * 80)
    print("=== TECHNISCHER VERGLEICH ===")
    print("=" * 80)

    print(f"""
+-----------------------------+------------------------+------------------------+
| Metrik                      | Surya (CPU)            | Qwen2.5-VL (GPU)       |
+-----------------------------+------------------------+------------------------+
| Erfolgsrate                 | {surya.get('success_rate', 0)*100:>6.1f}%               | {qwen.get('success_rate', 0)*100:>6.1f}%               |
| Gesamtzeit                  | {surya.get('total_time_s', 0):>6.1f}s               | {qwen.get('total_time_s', 0):>6.1f}s               |
| Durchschnitt/Bild           | {surya.get('avg_time_s', 0):>6.2f}s               | {qwen.get('avg_time_s', 0):>6.2f}s               |
| VRAM-Verbrauch              | {surya.get('vram_gb', 0):>6.1f} GB              | {qwen.get('vram_gb', 0):>6.1f} GB              |
| Extrahierte Zeichen         | {surya.get('total_chars', 0):>6}                 | {qwen.get('total_chars', 0):>6}                 |
| Erkannte Umlaute            | {surya.get('total_umlauts', 0):>6}                 | {qwen.get('total_umlauts', 0):>6}                 |
+-----------------------------+------------------------+------------------------+
""")

    print("\n" + "=" * 80)
    print("=== INHALTLICHER VERGLEICH (Textbeispiele) ===")
    print("=" * 80)

    surya_results = surya.get("results", [])
    qwen_results = qwen.get("results", [])

    for i, (sr, qr) in enumerate(zip(surya_results[:3], qwen_results[:3])):
        print(f"\n--- Datei {i+1}: {sr.get('file', 'unknown')} ---")
        print(f"\nSurya ({sr.get('chars', 0)} Zeichen, {sr.get('umlauts', 0)} Umlaute):")
        print(f"  {sr.get('text_preview', '(kein Text)')[:150]}...")
        print(f"\nQwen ({qr.get('chars', 0)} Zeichen, {qr.get('umlauts', 0)} Umlaute):")
        print(f"  {qr.get('text_preview', '(kein Text)')[:150]}...")


async def main():
    """Hauptfunktion fuer Vergleichstest."""
    print("=" * 80)
    print("     QWEN2.5-VL-7B vs SURYA OCR - VERGLEICHSTEST")
    print("=" * 80)

    # Test-Dateien laden
    test_files = get_test_files(10)
    print(f"\nTest-Dateien: {len(test_files)} TIF-Bilder")
    for f in test_files[:3]:
        print(f"  - {Path(f).name}")
    print("  ...")

    # GPU-Status
    if torch.cuda.is_available():
        print(f"\nGPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB")
    else:
        print("\nKeine GPU verfuegbar - Qwen-Test wird uebersprungen")

    # Surya testen
    surya_results = await test_surya(test_files)

    # Qwen testen (falls GPU verfuegbar)
    if torch.cuda.is_available():
        qwen_results = await test_qwen(test_files)
    else:
        qwen_results = {"backend": "qwen", "error": "No GPU"}

    # Vergleich ausgeben
    print_comparison(surya_results, qwen_results)

    # Ergebnisse speichern
    output = {
        "test_files": test_files,
        "surya": surya_results,
        "qwen": qwen_results,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    output_path = Path("scripts/ocr_comparison_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nErgebnisse gespeichert: {output_path}")

    return output


if __name__ == "__main__":
    asyncio.run(main())
