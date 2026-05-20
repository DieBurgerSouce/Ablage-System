"""Vergleich: Surya vs Surya+Docling Enhanced

Testet beide OCR-Backends auf echten Dokumenten und vergleicht:
- Verarbeitungszeit
- Textextraktion
- Tabellenerkennung
- Umlaut-Genauigkeit
"""

import asyncio
import time
import random
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Projekt-Root zum Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
from app.agents.ocr.surya_docling_enhanced_agent import SuryaDoclingEnhancedAgent


def find_test_documents(base_path: Path, count: int = 5) -> List[Path]:
    """Finde zufällige Test-Dokumente."""
    documents = []

    for folder in base_path.iterdir():
        if folder.is_dir() and folder.name.startswith("UP"):
            for file in folder.iterdir():
                if file.suffix.upper() in [".PDF", ".TIF", ".TIFF", ".PNG", ".JPG"]:
                    documents.append(file)

    # Zufällige Auswahl
    if len(documents) > count:
        documents = random.sample(documents, count)

    return documents


async def test_surya_basic(agent: SuryaDoclingAgent, image_path: Path) -> Dict[str, Any]:
    """Teste Surya ohne Docling."""
    start = time.perf_counter()

    result = await agent.process({
        "image_path": str(image_path),
        "language": "de",
    })

    duration = time.perf_counter() - start

    return {
        "backend": "surya_basic",
        "duration_s": round(duration, 2),
        "success": result.get("success", False),
        "text_length": len(result.get("text", "")),
        "confidence": result.get("confidence", 0),
        "has_umlauts": result.get("metadata", {}).get("has_umlauts", False),
        "text_preview": result.get("text", "")[:200],
        "error": result.get("error"),
    }


async def test_surya_enhanced(agent: SuryaDoclingEnhancedAgent, image_path: Path) -> Dict[str, Any]:
    """Teste Surya mit Docling Layout-Analyse."""
    start = time.perf_counter()

    result = await agent.process({
        "image_path": str(image_path),
        "language": "de",
    })

    duration = time.perf_counter() - start

    return {
        "backend": "surya_enhanced",
        "duration_s": round(duration, 2),
        "success": result.get("success", False),
        "text_length": len(result.get("text", "")),
        "confidence": result.get("confidence", 0),
        "has_umlauts": result.get("metadata", {}).get("has_umlauts", False),
        "layout_used": result.get("layout_analysis_used", False),
        "tables_found": len(result.get("tables", [])),
        "reading_order": result.get("reading_order_applied", False),
        "layout_summary": result.get("layout", {}),
        "text_preview": result.get("text", "")[:200],
        "error": result.get("error"),
    }


async def compare_document(
    doc_path: Path,
    basic_agent: SuryaDoclingAgent,
    enhanced_agent: SuryaDoclingEnhancedAgent,
) -> Dict[str, Any]:
    """Vergleiche beide Backends für ein Dokument."""
    print(f"\n{'='*60}")
    print(f"Dokument: {doc_path.name}")
    print(f"Größe: {doc_path.stat().st_size / 1024:.1f} KB")
    print(f"{'='*60}")

    # Test Basic Surya
    print("\n[1/2] Teste Surya Basic...")
    basic_result = await test_surya_basic(basic_agent, doc_path)

    # Test Enhanced Surya
    print("[2/2] Teste Surya Enhanced (mit Docling)...")
    enhanced_result = await test_surya_enhanced(enhanced_agent, doc_path)

    # Ergebnisse anzeigen
    print(f"\n--- Ergebnisse ---")
    print(f"\nSURYA BASIC:")
    print(f"  Zeit: {basic_result['duration_s']}s")
    print(f"  Erfolg: {basic_result['success']}")
    print(f"  Text-Länge: {basic_result['text_length']} Zeichen")
    print(f"  Confidence: {basic_result['confidence']:.2%}")
    print(f"  Umlaute erkannt: {basic_result['has_umlauts']}")
    if basic_result.get("error"):
        print(f"  FEHLER: {basic_result['error']}")

    print(f"\nSURYA ENHANCED (+ Docling):")
    print(f"  Zeit: {enhanced_result['duration_s']}s")
    print(f"  Erfolg: {enhanced_result['success']}")
    print(f"  Text-Länge: {enhanced_result['text_length']} Zeichen")
    print(f"  Confidence: {enhanced_result['confidence']:.2%}")
    print(f"  Umlaute erkannt: {enhanced_result['has_umlauts']}")
    print(f"  Layout-Analyse: {enhanced_result['layout_used']}")
    print(f"  Tabellen gefunden: {enhanced_result['tables_found']}")
    print(f"  Lesereihenfolge: {enhanced_result['reading_order']}")
    if enhanced_result.get("layout_summary"):
        ls = enhanced_result['layout_summary']
        print(f"  Layout-Details: {ls.get('table_count', 0)} Tabellen, {ls.get('figure_count', 0)} Figuren")
    if enhanced_result.get("error"):
        print(f"  FEHLER: {enhanced_result['error']}")

    # Vergleich
    print(f"\n--- Vergleich ---")
    time_diff = enhanced_result['duration_s'] - basic_result['duration_s']
    text_diff = enhanced_result['text_length'] - basic_result['text_length']
    print(f"  Zeit-Unterschied: {time_diff:+.2f}s (Enhanced {'langsamer' if time_diff > 0 else 'schneller'})")
    print(f"  Text-Unterschied: {text_diff:+d} Zeichen")

    return {
        "document": doc_path.name,
        "basic": basic_result,
        "enhanced": enhanced_result,
    }


async def main():
    """Hauptfunktion für Vergleichstest."""
    print("="*60)
    print("SURYA vs SURYA+DOCLING ENHANCED - Vergleichstest")
    print("="*60)

    # Pfad zu Trainingsdaten
    base_path = Path("C:/Users/benfi/Ablage_System/Trainings_Data")

    if not base_path.exists():
        print(f"FEHLER: Trainingsdaten-Pfad existiert nicht: {base_path}")
        return

    # Test-Dokumente finden
    print("\nSuche Test-Dokumente...")
    documents = find_test_documents(base_path, count=5)

    if not documents:
        print("FEHLER: Keine Test-Dokumente gefunden!")
        return

    print(f"Gefunden: {len(documents)} Dokumente")
    for doc in documents:
        print(f"  - {doc.name} ({doc.stat().st_size/1024:.1f} KB)")

    # Agents initialisieren
    print("\nInitialisiere Agents...")
    basic_agent = SuryaDoclingAgent()
    enhanced_agent = SuryaDoclingEnhancedAgent()

    # Tests durchführen
    results = []
    for doc in documents:
        try:
            result = await compare_document(doc, basic_agent, enhanced_agent)
            results.append(result)
        except Exception as e:
            print(f"\nFEHLER bei {doc.name}: {e}")
            import traceback
            traceback.print_exc()

    # Zusammenfassung
    print("\n" + "="*60)
    print("ZUSAMMENFASSUNG")
    print("="*60)

    if not results:
        print("Keine erfolgreichen Tests!")
        return

    # Statistiken berechnen
    basic_times = [r["basic"]["duration_s"] for r in results if r["basic"]["success"]]
    enhanced_times = [r["enhanced"]["duration_s"] for r in results if r["enhanced"]["success"]]
    tables_found = sum(r["enhanced"]["tables_found"] for r in results)
    layout_used = sum(1 for r in results if r["enhanced"]["layout_used"])

    print(f"\nAnzahl getesteter Dokumente: {len(results)}")

    if basic_times:
        print(f"\nSURYA BASIC:")
        print(f"  Durchschnittliche Zeit: {sum(basic_times)/len(basic_times):.2f}s")
        print(f"  Min/Max: {min(basic_times):.2f}s / {max(basic_times):.2f}s")

    if enhanced_times:
        print(f"\nSURYA ENHANCED:")
        print(f"  Durchschnittliche Zeit: {sum(enhanced_times)/len(enhanced_times):.2f}s")
        print(f"  Min/Max: {min(enhanced_times):.2f}s / {max(enhanced_times):.2f}s")
        print(f"  Dokumente mit Layout-Analyse: {layout_used}/{len(results)}")
        print(f"  Tabellen insgesamt gefunden: {tables_found}")

    # Cleanup
    await basic_agent.cleanup()
    await enhanced_agent.cleanup()

    print("\n" + "="*60)
    print("Test abgeschlossen!")


if __name__ == "__main__":
    asyncio.run(main())
