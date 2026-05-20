#!/usr/bin/env python3
"""
Re-Processing Script fuer Quick-Classification.

Dieses Script startet den Celery-Task zum Re-Prozessieren
aller Dokumente mit dem aktualisierten Quick-Classification-Code.

WICHTIG: Vor dem Ausfuehren sicherstellen dass:
1. Der Celery Worker laeuft
2. Die Datenbank erreichbar ist
3. Redis erreichbar ist

Usage:
    python scripts/reprocess_quick_classification.py [--sync] [--batch-size 50]

Argumente:
    --sync          Synchron ausfuehren (wartet auf Ergebnis)
    --batch-size N  Dokumente pro Batch (default: 50)
    --skip-correct  Nur aktualisieren wenn sich etwas aendert
"""

import argparse
import sys
import os
import time

# Projekt-Root zum Path hinzufuegen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(
        description="Re-Process Quick-Classification fuer alle Dokumente"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Synchron ausfuehren (wartet auf Ergebnis)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Dokumente pro Batch (default: 50)",
    )
    parser.add_argument(
        "--skip-correct",
        action="store_true",
        help="Nur aktualisieren wenn sich etwas aendert",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Quick-Classification Re-Processing")
    print("=" * 60)
    print(f"Batch-Size:    {args.batch_size}")
    print(f"Skip Correct:  {args.skip_correct}")
    print(f"Sync Mode:     {args.sync}")
    print("=" * 60)

    # Import Celery Task
    try:
        from app.workers.tasks.extraction_tasks import reprocess_quick_classification
    except ImportError as e:
        print(f"\nFEHLER: Konnte Task nicht importieren: {e}")
        print("Stellen Sie sicher dass Sie im Projekt-Root sind.")
        sys.exit(1)

    # Task starten
    print("\nStarte Task...")
    result = reprocess_quick_classification.apply_async(
        kwargs={
            "batch_size": args.batch_size,
            "skip_correct": args.skip_correct,
        }
    )

    print(f"Task ID: {result.id}")

    if args.sync:
        print("\nWarte auf Ergebnis...")
        try:
            # Fortschritt anzeigen
            while not result.ready():
                meta = result.info
                if isinstance(meta, dict) and "percent" in meta:
                    print(
                        f"  Fortschritt: {meta['current']}/{meta['total']} "
                        f"({meta['percent']}%)",
                        end="\r",
                    )
                time.sleep(2)

            # Ergebnis abrufen
            final_result = result.get(timeout=3600)
            print("\n")
            print("=" * 60)
            print("ERGEBNIS")
            print("=" * 60)
            print(f"Verarbeitet:  {final_result.get('total_processed', 0)}")
            print(f"Aktualisiert: {final_result.get('total_updated', 0)}")
            print(f"Uebersprungen: {final_result.get('total_skipped', 0)}")
            print(f"Fehlgeschlagen: {final_result.get('total_failed', 0)}")
            print(f"Dauer:        {final_result.get('duration_seconds', 0):.1f}s")
            print("=" * 60)

            # Beispiele anzeigen
            examples = final_result.get("examples", [])
            if examples:
                print("\nBeispiele fuer Aenderungen:")
                for ex in examples[:5]:
                    print(f"  {ex['filename']}:")
                    print(f"    Alt: {ex['old_invoice']} -> Neu: {ex['new_invoice']}")
                    print(f"    {ex['old_suggestion']} -> {ex['new_suggestion']}")
                    print()

        except Exception as e:
            print(f"\nFEHLER: {e}")
            sys.exit(1)
    else:
        print("\nTask wurde asynchron gestartet.")
        print(f"Status pruefen mit: celery -A app.workers.celery_app result {result.id}")


if __name__ == "__main__":
    main()
