# -*- coding: utf-8 -*-
"""
OCR Backend Comparison Test: docTR vs Surya

Vergleicht docTR und Surya auf 10 TIF-Dateien aus den Trainingsdaten.
Misst Verarbeitungszeit, extrahierten Text und Confidence.

Usage:
    python scripts/test_ocr_comparison.py
"""

import asyncio
import time
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.ocr.doctr_agent import DocTRAgent, is_doctr_available
from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent


# TIF files to test
TIF_FILES = [
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\00000009.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\0000000B.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\0000000C.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\0000000D.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\0000000E.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\0000000F.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\00000010.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\00000011.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\00000012.TIF",
    r"C:\Users\benfi\Ablage_System\Trainings_Data\UP000000\00000013.TIF",
]


def print_separator():
    print("=" * 80)


def print_result_summary(result: dict, backend_name: str):
    """Print a summary of OCR result."""
    print(f"\n--- {backend_name} Result ---")
    print(f"Success: {result.get('success', False)}")
    print(f"Confidence: {result.get('confidence', 0.0):.3f}")
    print(f"Processing Time: {result.get('processing_time_ms', 0)} ms")
    print(f"Character Count: {result.get('char_count', len(result.get('text', '')))}")
    print(f"Word Count: {result.get('word_count', len(result.get('text', '').split()))}")

    text = result.get("text", "")
    if text:
        # Check for German umlauts
        umlauts = ['ae', 'oe', 'ue', 'Ae', 'Oe', 'Ue', 'ss']
        found_umlauts = [u for u in umlauts if u in text]
        print(f"Umlauts found: {found_umlauts}")

        # Show first 500 chars
        preview = text[:500].replace('\n', ' ')
        print(f"\nText Preview (first 500 chars):\n{preview}...")
    else:
        print("No text extracted!")
        if result.get("error"):
            print(f"Error: {result.get('error')}")


async def test_single_file(file_path: str, doctr_agent: DocTRAgent, surya_agent: SuryaDoclingAgent):
    """Test both backends on a single file."""
    print_separator()
    print(f"\nTesting: {Path(file_path).name}")
    print_separator()

    input_data = {
        "image_path": file_path,
        "language": "de",
        "document_id": Path(file_path).stem
    }

    results = {}

    # Test docTR
    print("\n[1/2] Running docTR...")
    start = time.time()
    try:
        doctr_result = await doctr_agent.process(input_data)
        doctr_result["processing_time_ms"] = int((time.time() - start) * 1000)
        results["doctr"] = doctr_result
        print_result_summary(doctr_result, "docTR")
    except Exception as e:
        print(f"docTR Error: {e}")
        results["doctr"] = {"success": False, "error": str(e)}

    # Test Surya
    print("\n[2/2] Running Surya...")
    start = time.time()
    try:
        surya_result = await surya_agent.process(input_data)
        surya_result["processing_time_ms"] = int((time.time() - start) * 1000)
        results["surya"] = surya_result
        print_result_summary(surya_result, "Surya")
    except Exception as e:
        print(f"Surya Error: {e}")
        results["surya"] = {"success": False, "error": str(e)}

    return results


async def main():
    """Main comparison test."""
    print("\n" + "=" * 80)
    print("OCR BACKEND COMPARISON TEST: docTR vs Surya")
    print("=" * 80)

    # Check availability
    print(f"\ndocTR available: {is_doctr_available()}")

    # Initialize agents
    print("\nInitializing agents...")
    doctr_agent = DocTRAgent()
    surya_agent = SuryaDoclingAgent()

    print(f"docTR Agent Status: {doctr_agent.get_status()}")
    print(f"Surya Agent Status: {surya_agent.get_status()}")

    # Verify files exist
    existing_files = [f for f in TIF_FILES if Path(f).exists()]
    print(f"\nFound {len(existing_files)} of {len(TIF_FILES)} TIF files")

    if not existing_files:
        print("ERROR: No TIF files found!")
        return

    # Run tests
    all_results = []

    for file_path in existing_files[:10]:  # Limit to 10 files
        result = await test_single_file(file_path, doctr_agent, surya_agent)
        all_results.append({
            "file": Path(file_path).name,
            "doctr": result.get("doctr", {}),
            "surya": result.get("surya", {})
        })

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY COMPARISON")
    print("=" * 80)

    doctr_times = []
    surya_times = []
    doctr_confidences = []
    surya_confidences = []
    doctr_chars = []
    surya_chars = []

    print(f"\n{'File':<20} {'docTR Time':<12} {'Surya Time':<12} {'docTR Conf':<12} {'Surya Conf':<12} {'docTR Chars':<12} {'Surya Chars':<12}")
    print("-" * 92)

    for r in all_results:
        doctr = r.get("doctr", {})
        surya = r.get("surya", {})

        dt = doctr.get("processing_time_ms", 0)
        st = surya.get("processing_time_ms", 0)
        dc = doctr.get("confidence", 0.0)
        sc = surya.get("confidence", 0.0)
        dch = len(doctr.get("text", ""))
        sch = len(surya.get("text", ""))

        doctr_times.append(dt)
        surya_times.append(st)
        doctr_confidences.append(dc)
        surya_confidences.append(sc)
        doctr_chars.append(dch)
        surya_chars.append(sch)

        print(f"{r['file']:<20} {dt:<12} {st:<12} {dc:<12.3f} {sc:<12.3f} {dch:<12} {sch:<12}")

    print("-" * 92)

    # Averages
    if all_results:
        avg_doctr_time = sum(doctr_times) / len(doctr_times)
        avg_surya_time = sum(surya_times) / len(surya_times)
        avg_doctr_conf = sum(doctr_confidences) / len(doctr_confidences)
        avg_surya_conf = sum(surya_confidences) / len(surya_confidences)
        avg_doctr_chars = sum(doctr_chars) / len(doctr_chars)
        avg_surya_chars = sum(surya_chars) / len(surya_chars)

        print(f"{'AVERAGE':<20} {avg_doctr_time:<12.0f} {avg_surya_time:<12.0f} {avg_doctr_conf:<12.3f} {avg_surya_conf:<12.3f} {avg_doctr_chars:<12.0f} {avg_surya_chars:<12.0f}")

        print("\n" + "=" * 80)
        print("FINAL ANALYSIS")
        print("=" * 80)

        print(f"\nProcessing Speed:")
        if avg_doctr_time < avg_surya_time:
            speedup = avg_surya_time / avg_doctr_time if avg_doctr_time > 0 else 0
            print(f"  -> docTR ist {speedup:.1f}x schneller als Surya")
        else:
            speedup = avg_doctr_time / avg_surya_time if avg_surya_time > 0 else 0
            print(f"  -> Surya ist {speedup:.1f}x schneller als docTR")

        print(f"\nConfidence:")
        print(f"  -> docTR durchschnittliche Confidence: {avg_doctr_conf:.3f}")
        print(f"  -> Surya durchschnittliche Confidence: {avg_surya_conf:.3f}")

        print(f"\nText Output:")
        print(f"  -> docTR durchschnittliche Zeichen: {avg_doctr_chars:.0f}")
        print(f"  -> Surya durchschnittliche Zeichen: {avg_surya_chars:.0f}")

    # Cleanup
    await doctr_agent.cleanup()
    await surya_agent.cleanup()

    print("\n" + "=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
