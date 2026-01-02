# -*- coding: utf-8 -*-
"""
OCR Inhaltlicher Vergleich - Vergleicht extrahierten Text pro Dokument.

Testet alle funktionierenden Backends auf 3 Testdateien und zeigt
den extrahierten Text nebeneinander.
"""

import asyncio
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

logger = structlog.get_logger(__name__)

# 3 Test-Dateien fuer detaillierten Vergleich
TEST_FILES = [
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/00000009.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000B.TIF",
    "C:/Users/benfi/Ablage_System/Trainings_Data/UP000000/0000000C.TIF",
]


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
            "text": text,
            "text_length": len(text),
            "confidence": result.get("confidence", 0),
            "processing_time_ms": elapsed_ms,
            "error": result.get("error"),
        }

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return {
            "backend": backend_name,
            "file": Path(file_path).name,
            "success": False,
            "text": "",
            "text_length": 0,
            "confidence": 0,
            "processing_time_ms": elapsed_ms,
            "error": str(e),
        }


def analyze_text_quality(text: str) -> Dict[str, Any]:
    """Analysiere Textqualitaet."""
    import re

    # Zaehle verschiedene Elemente
    words = text.split()
    lines = text.strip().split('\n')

    # Deutsche Umlaute (ae-Schreibweise)
    umlauts_ae = sum(text.count(u) for u in ['ae', 'oe', 'ue', 'Ae', 'Oe', 'Ue', 'ss'])

    # Echte Umlaute
    real_umlauts = sum(text.count(u) for u in ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß'])

    # Zahlen
    numbers = len(re.findall(r'\d+', text))

    # Datum-Muster
    dates = len(re.findall(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', text))

    # IBAN/BIC
    ibans = len(re.findall(r'[A-Z]{2}\d{2}[\s]?[\d\s]{16,}', text))

    # Euro-Betraege
    euros = len(re.findall(r'\d+[.,]\d{2}\s*(EUR|Euro|€)', text, re.I))

    return {
        "words": len(words),
        "lines": len(lines),
        "chars": len(text),
        "umlauts_ae_style": umlauts_ae,
        "umlauts_real": real_umlauts,
        "numbers": numbers,
        "dates": dates,
        "ibans": ibans,
        "euro_amounts": euros,
    }


async def run_comparison():
    """Fuehre inhaltlichen Vergleich durch."""
    print("=" * 100)
    print("OCR INHALTLICHER VERGLEICH")
    print(f"Gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # Finde existierende Test-Dateien
    existing_files = [f for f in TEST_FILES if Path(f).exists()]
    if not existing_files:
        import glob
        existing_files = glob.glob("C:/Users/benfi/Ablage_System/Trainings_Data/**/*.TIF", recursive=True)[:3]

    print(f"\nTeste mit {len(existing_files)} Dateien:")
    for f in existing_files:
        print(f"  - {f}")

    # Initialisiere Backends
    print("\n" + "-" * 50)
    print("INITIALISIERE BACKENDS")
    print("-" * 50)

    backends = {}

    # 1. Surya CPU (funktioniert)
    try:
        from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
        backends["Surya CPU"] = SuryaDoclingAgent()
        print("[OK] Surya CPU")
    except Exception as e:
        print(f"[FEHLER] Surya CPU: {e}")

    # 2. Chandra 4-bit GPU (sollte funktionieren)
    try:
        import torch
        if torch.cuda.is_available():
            from app.agents.ocr.chandra_agent import ChandraOCRAgent
            backends["Chandra 4bit"] = ChandraOCRAgent(quantization="4bit")
            print("[OK] Chandra 4-bit GPU")
    except Exception as e:
        print(f"[FEHLER] Chandra: {e}")

    print(f"\n{len(backends)} Backends bereit")

    # Ergebnisse sammeln
    all_results: Dict[str, List[Dict[str, Any]]] = {}

    for file_path in existing_files:
        file_name = Path(file_path).name
        print(f"\n{'=' * 100}")
        print(f"DATEI: {file_name}")
        print("=" * 100)

        all_results[file_name] = []

        for backend_name, agent in backends.items():
            print(f"\n--- {backend_name} ---")

            result = await test_backend(backend_name, agent, file_path)
            all_results[file_name].append(result)

            if result["success"] and result["text"]:
                # Analysiere Textqualitaet
                quality = analyze_text_quality(result["text"])

                print(f"Zeit: {result['processing_time_ms']}ms | Confidence: {result['confidence']:.2%}")
                print(f"Zeichen: {quality['chars']} | Woerter: {quality['words']} | Zeilen: {quality['lines']}")
                print(f"Umlaute (ae-Stil): {quality['umlauts_ae_style']} | Echte Umlaute: {quality['umlauts_real']}")
                print(f"Zahlen: {quality['numbers']} | Daten: {quality['dates']} | IBANs: {quality['ibans']} | Euro: {quality['euro_amounts']}")
                print(f"\nTEXT (erste 1000 Zeichen):")
                print("-" * 50)
                print(result["text"][:1000])
                if len(result["text"]) > 1000:
                    print(f"\n... ({len(result['text']) - 1000} weitere Zeichen)")
            else:
                print(f"FEHLER: {result.get('error', 'Kein Text extrahiert')}")

        # GPU Memory freigeben nach jedem Dokument
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except:
            pass

    # Vergleichstabelle
    print("\n" + "=" * 100)
    print("VERGLEICHS-ZUSAMMENFASSUNG")
    print("=" * 100)

    for file_name, results in all_results.items():
        print(f"\n{file_name}:")
        print("-" * 80)

        for r in results:
            if r["success"] and r["text"]:
                quality = analyze_text_quality(r["text"])
                print(f"  {r['backend']:15} | {r['processing_time_ms']:6}ms | {quality['chars']:5} chars | {quality['words']:4} words | {r['confidence']:.0%} conf")
            else:
                print(f"  {r['backend']:15} | FEHLER: {r.get('error', 'Unbekannt')[:40]}")

    # Speichere Ergebnisse
    output_file = Path(__file__).parent / "ocr_content_comparison.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "files": list(all_results.keys()),
            "backends": list(backends.keys()),
            "results": all_results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n\nErgebnisse gespeichert: {output_file}")

    # Cleanup
    for name, agent in backends.items():
        try:
            await agent.cleanup()
        except:
            pass

    return all_results


if __name__ == "__main__":
    asyncio.run(run_comparison())
