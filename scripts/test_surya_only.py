# -*- coding: utf-8 -*-
"""
Surya OCR Backend Test

Testet Surya auf 10 TIF-Dateien aus den Trainingsdaten.
Misst Verarbeitungszeit, extrahierten Text und Confidence.

Usage:
    python scripts/test_surya_only.py
"""

import asyncio
import time
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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


async def test_single_file(file_path: str, surya_agent: SuryaDoclingAgent):
    """Test Surya on a single file."""
    print_separator()
    print(f"\nTesting: {Path(file_path).name}")
    print_separator()

    input_data = {
        "image_path": file_path,
        "language": "de",
        "document_id": Path(file_path).stem
    }

    # Test Surya
    print("\nRunning Surya...")
    start = time.time()
    try:
        surya_result = await surya_agent.process(input_data)
        surya_result["processing_time_ms"] = int((time.time() - start) * 1000)
        print_result_summary(surya_result, "Surya")
        return surya_result
    except Exception as e:
        print(f"Surya Error: {e}")
        return {"success": False, "error": str(e)}


async def main():
    """Main Surya test."""
    print("\n" + "=" * 80)
    print("SURYA OCR BACKEND TEST")
    print("=" * 80)

    # Initialize agent
    print("\nInitializing Surya agent...")
    surya_agent = SuryaDoclingAgent()

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
        result = await test_single_file(file_path, surya_agent)
        all_results.append({
            "file": Path(file_path).name,
            "result": result
        })

    # Print summary
    print("\n" + "=" * 80)
    print("SURYA RESULTS SUMMARY")
    print("=" * 80)

    surya_times = []
    surya_confidences = []
    surya_chars = []

    print(f"\n{'File':<20} {'Time (ms)':<12} {'Confidence':<12} {'Chars':<12}")
    print("-" * 60)

    for r in all_results:
        result = r.get("result", {})

        st = result.get("processing_time_ms", 0)
        sc = result.get("confidence", 0.0)
        sch = len(result.get("text", ""))

        surya_times.append(st)
        surya_confidences.append(sc)
        surya_chars.append(sch)

        print(f"{r['file']:<20} {st:<12} {sc:<12.3f} {sch:<12}")

    print("-" * 60)

    # Averages
    if all_results:
        avg_surya_time = sum(surya_times) / len(surya_times)
        avg_surya_conf = sum(surya_confidences) / len(surya_confidences)
        avg_surya_chars = sum(surya_chars) / len(surya_chars)

        print(f"{'AVERAGE':<20} {avg_surya_time:<12.0f} {avg_surya_conf:<12.3f} {avg_surya_chars:<12.0f}")

        print("\n" + "=" * 80)
        print("FINAL ANALYSIS")
        print("=" * 80)

        print(f"\nSurya Performance:")
        print(f"  -> Durchschnittliche Verarbeitungszeit: {avg_surya_time:.0f} ms")
        print(f"  -> Durchschnittliche Confidence: {avg_surya_conf:.3f}")
        print(f"  -> Durchschnittliche Zeichen: {avg_surya_chars:.0f}")

    # Cleanup
    await surya_agent.cleanup()

    print("\n" + "=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
