# -*- coding: utf-8 -*-
"""
Vergleich Chandra OCR vs Surya OCR auf 10 TIF-Dateien.

Technischer und inhaltlicher Vergleich:
- Processing Time
- Text Length
- Confidence
- Character/Word Count
- Deutsche Umlaute
"""

import asyncio
import time
import json
from pathlib import Path
from datetime import datetime
import sys
import os

# UTF-8 Encoding
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

async def run_comparison():
    from app.agents.ocr import ChandraOCRAgent, SuryaDoclingAgent

    # Test-Dateien
    tif_files = [
        "Trainings_Data/UP000000/00000009.TIF",
        "Trainings_Data/UP000000/0000000B.TIF",
        "Trainings_Data/UP000000/0000000C.TIF",
        "Trainings_Data/UP000000/0000000D.TIF",
        "Trainings_Data/UP000000/0000000E.TIF",
        "Trainings_Data/UP000000/0000000F.TIF",
        "Trainings_Data/UP000000/00000010.TIF",
        "Trainings_Data/UP000000/00000011.TIF",
        "Trainings_Data/UP000000/00000012.TIF",
        "Trainings_Data/UP000000/00000013.TIF",
    ]

    print("=" * 70)
    print("CHANDRA vs SURYA OCR VERGLEICH")
    print("=" * 70)
    print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Anzahl Testdateien: {len(tif_files)}")
    print()

    # Agents erstellen
    print("Initialisiere Agents...")
    chandra = ChandraOCRAgent(quantization='none')
    surya = SuryaDoclingAgent()
    print(f"  Chandra: {chandra.name} (GPU={chandra.gpu_required}, VRAM={chandra.vram_gb}GB)")
    print(f"  Surya: {surya.name} (GPU={surya.gpu_required})")
    print()

    results = {
        "chandra": [],
        "surya": [],
        "comparison": []
    }

    # Verarbeitung
    for i, tif_path in enumerate(tif_files):
        print(f"\n[{i+1}/{len(tif_files)}] Verarbeite: {Path(tif_path).name}")
        print("-" * 50)

        if not Path(tif_path).exists():
            print(f"  WARNUNG: Datei nicht gefunden!")
            continue

        file_result = {"file": tif_path}

        # Chandra OCR
        print("  Chandra OCR...")
        start = time.perf_counter()
        try:
            chandra_result = await chandra.process({
                "image_path": tif_path,
                "language": "de"
            })
            chandra_time = time.perf_counter() - start

            if chandra_result.get("success"):
                text = chandra_result.get("text", "")
                file_result["chandra"] = {
                    "success": True,
                    "time_sec": round(chandra_time, 2),
                    "text_length": len(text),
                    "word_count": len(text.split()),
                    "has_umlauts": any(c in text for c in "aouAOU"),
                    "confidence": chandra_result.get("confidence", 0),
                    "text_preview": text[:200] if text else ""
                }
                print(f"    OK - {len(text)} Zeichen in {chandra_time:.2f}s")
            else:
                file_result["chandra"] = {
                    "success": False,
                    "error": chandra_result.get("error", "Unknown"),
                    "time_sec": round(chandra_time, 2)
                }
                print(f"    FEHLER: {chandra_result.get('error', 'Unknown')}")
        except Exception as e:
            chandra_time = time.perf_counter() - start
            file_result["chandra"] = {
                "success": False,
                "error": str(e),
                "time_sec": round(chandra_time, 2)
            }
            print(f"    EXCEPTION: {e}")

        results["chandra"].append(file_result.get("chandra", {}))

        # Surya OCR
        print("  Surya OCR...")
        start = time.perf_counter()
        try:
            surya_result = await surya.process({
                "image_path": tif_path,
                "language": "de"
            })
            surya_time = time.perf_counter() - start

            if surya_result.get("success"):
                text = surya_result.get("text", "")
                file_result["surya"] = {
                    "success": True,
                    "time_sec": round(surya_time, 2),
                    "text_length": len(text),
                    "word_count": len(text.split()),
                    "has_umlauts": any(c in text for c in "aouAOU"),
                    "confidence": surya_result.get("confidence", 0),
                    "text_preview": text[:200] if text else ""
                }
                print(f"    OK - {len(text)} Zeichen in {surya_time:.2f}s")
            else:
                file_result["surya"] = {
                    "success": False,
                    "error": surya_result.get("error", "Unknown"),
                    "time_sec": round(surya_time, 2)
                }
                print(f"    FEHLER: {surya_result.get('error', 'Unknown')}")
        except Exception as e:
            surya_time = time.perf_counter() - start
            file_result["surya"] = {
                "success": False,
                "error": str(e),
                "time_sec": round(surya_time, 2)
            }
            print(f"    EXCEPTION: {e}")

        results["surya"].append(file_result.get("surya", {}))
        results["comparison"].append(file_result)

    # Cleanup
    print("\n\nBereinige Agents...")
    await chandra.cleanup()

    # Statistiken
    print("\n" + "=" * 70)
    print("ZUSAMMENFASSUNG")
    print("=" * 70)

    # Chandra Stats
    chandra_success = [r for r in results["chandra"] if r.get("success")]
    chandra_times = [r["time_sec"] for r in chandra_success]
    chandra_lengths = [r["text_length"] for r in chandra_success]

    print("\nCHANDRA OCR:")
    print(f"  Erfolgsrate: {len(chandra_success)}/{len(results['chandra'])}")
    if chandra_times:
        print(f"  Durchschnittliche Zeit: {sum(chandra_times)/len(chandra_times):.2f}s")
        print(f"  Gesamtzeit: {sum(chandra_times):.2f}s")
    if chandra_lengths:
        print(f"  Durchschnittliche Textlaenge: {sum(chandra_lengths)/len(chandra_lengths):.0f} Zeichen")

    # Surya Stats
    surya_success = [r for r in results["surya"] if r.get("success")]
    surya_times = [r["time_sec"] for r in surya_success]
    surya_lengths = [r["text_length"] for r in surya_success]

    print("\nSURYA OCR:")
    print(f"  Erfolgsrate: {len(surya_success)}/{len(results['surya'])}")
    if surya_times:
        print(f"  Durchschnittliche Zeit: {sum(surya_times)/len(surya_times):.2f}s")
        print(f"  Gesamtzeit: {sum(surya_times):.2f}s")
    if surya_lengths:
        print(f"  Durchschnittliche Textlaenge: {sum(surya_lengths)/len(surya_lengths):.0f} Zeichen")

    # Vergleich
    print("\nVERGLEICH:")
    if chandra_times and surya_times:
        speed_ratio = sum(surya_times) / sum(chandra_times) if sum(chandra_times) > 0 else 0
        print(f"  Geschwindigkeit: Chandra ist {speed_ratio:.1f}x {'schneller' if speed_ratio > 1 else 'langsamer'} als Surya")

    if chandra_lengths and surya_lengths:
        text_ratio = sum(chandra_lengths) / sum(surya_lengths) if sum(surya_lengths) > 0 else 0
        print(f"  Textmenge: Chandra extrahiert {text_ratio:.1f}x {'mehr' if text_ratio > 1 else 'weniger'} Text")

    # Speichere Ergebnisse
    output_file = Path("scripts/chandra_surya_comparison.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nErgebnisse gespeichert in: {output_file}")

    # Detail-Vergleich pro Datei
    print("\n" + "=" * 70)
    print("DETAIL-VERGLEICH PRO DATEI")
    print("=" * 70)

    for comp in results["comparison"]:
        fname = Path(comp["file"]).name
        ch = comp.get("chandra", {})
        su = comp.get("surya", {})

        print(f"\n{fname}:")
        if ch.get("success") and su.get("success"):
            print(f"  Chandra: {ch['text_length']} Zeichen, {ch['time_sec']}s")
            print(f"  Surya:   {su['text_length']} Zeichen, {su['time_sec']}s")
            print(f"  Chandra Text: {ch['text_preview'][:100]}...")
            print(f"  Surya Text:   {su['text_preview'][:100]}...")
        elif ch.get("success"):
            print(f"  Chandra: OK ({ch['text_length']} Zeichen)")
            print(f"  Surya: FEHLER - {su.get('error', 'Unknown')}")
        elif su.get("success"):
            print(f"  Chandra: FEHLER - {ch.get('error', 'Unknown')}")
            print(f"  Surya: OK ({su['text_length']} Zeichen)")
        else:
            print(f"  Beide FEHLER")

if __name__ == "__main__":
    print("Starte Vergleich Chandra vs Surya...")
    print("HINWEIS: Der erste Start laedt das Chandra-Modell (~18GB)")
    print()
    asyncio.run(run_comparison())
