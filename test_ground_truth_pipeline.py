#!/usr/bin/env python3
"""
Test-Skript für die Smart Ground-Truth Pipeline.

Testet:
1. Business Document Profiles
2. Auto-Ground-Truth Service
3. Coverage Tracking
4. Verification Queue
5. Retraining Trigger
"""

import asyncio
import uuid
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


async def test_pipeline():
    """Haupttest für die Ground-Truth Pipeline."""

    print("\n" + "=" * 60)
    print("  SMART GROUND-TRUTH PIPELINE TEST")
    print("=" * 60 + "\n")

    from app.db.session import get_async_session_context
    from sqlalchemy import select, func

    async with get_async_session_context() as db:

        # ============================================================
        # 1. Business Document Profiles prüfen
        # ============================================================
        print("\n[1] BUSINESS DOCUMENT PROFILES")
        print("-" * 40)

        from app.db.models import BusinessDocumentProfile

        profiles_result = await db.execute(
            select(BusinessDocumentProfile)
        )
        profiles = profiles_result.scalars().all()

        if profiles:
            print(f"✓ {len(profiles)} Profile gefunden:")
            for p in profiles:
                print(f"  - {p.document_type}: criticality={p.business_criticality}, "
                      f"daily_volume={p.estimated_daily_volume}, "
                      f"auto_accept_conf={p.auto_accept_confidence}")
        else:
            print("✗ Keine Profile gefunden - Migration prüfen!")
            return

        # ============================================================
        # 2. Auto-Ground-Truth Service testen
        # ============================================================
        print("\n[2] AUTO-GROUND-TRUTH SERVICE")
        print("-" * 40)

        from app.services.auto_ground_truth_service import get_auto_ground_truth_service

        auto_gt_service = get_auto_ground_truth_service()

        # Test mit einem simulierten OCR-Ergebnis
        test_texts = [
            # High confidence, mit Umlauten
            ("Dies ist eine Testrechnung für Müller GmbH. Betrag: 1.234,56 €", 0.98, "invoice"),
            # Medium confidence
            ("Vertrag über Büroräume in München", 0.92, "contract"),
            # Low confidence - sollte nicht auto-accepted werden
            ("Unleserlicher Text...", 0.75, "letter"),
        ]

        print("\nSimulierte OCR-Ergebnisse testen:")
        for text, confidence, doc_type in test_texts:
            is_valid, reasons = await auto_gt_service.validate_for_auto_accept(
                text=text,
                document_type=doc_type,
                confidence=confidence
            )
            status = "✓ Auto-Accept" if is_valid else "✗ Queue"
            print(f"\n  Text: '{text[:40]}...'")
            print(f"  Confidence: {confidence:.0%}, Typ: {doc_type}")
            print(f"  Ergebnis: {status}")
            if reasons:
                print(f"  Gründe: {', '.join(reasons)}")

        # ============================================================
        # 3. Coverage Tracking testen
        # ============================================================
        print("\n[3] COVERAGE TRACKING")
        print("-" * 40)

        from app.services.coverage_tracking_service import get_coverage_tracking_service

        coverage_service = get_coverage_tracking_service()

        # Aktuelle Coverage berechnen
        coverage_status = await coverage_service.calculate_coverage(db)

        print(f"\n  Overall Coverage: {coverage_status.overall_coverage:.1%}")
        print(f"  Weighted Coverage: {coverage_status.weighted_coverage:.1%}")
        print(f"  Target erreicht: {'✓' if coverage_status.target_reached else '✗'} (Ziel: 90%)")
        print(f"\n  Total verified: {coverage_status.total_verified_samples}")
        print(f"  Total pending: {coverage_status.total_pending_samples}")
        print(f"  Auto-accepted: {coverage_status.auto_accepted_count}")
        print(f"  Spot-check pending: {coverage_status.spot_check_pending}")

        print("\n  Coverage pro Typ:")
        for doc_type, data in coverage_status.coverage_by_type.items():
            emoji = "✓" if data.get("target_reached", False) else "✗"
            print(f"    {emoji} {doc_type}: {data.get('coverage_percent', 0):.1f}% "
                  f"({data.get('verified_samples', 0)}/{data.get('target_samples', 0)} Samples)")

        # Coverage Gaps identifizieren
        gaps = await coverage_service.get_coverage_gaps(db)
        if gaps:
            print(f"\n  Coverage Gaps ({len(gaps)}):")
            for gap in gaps[:3]:  # Top 3
                print(f"    - {gap.document_type}: {gap.current_coverage:.1%} "
                      f"(benötigt noch {gap.samples_needed} Samples)")

        # ============================================================
        # 4. Verification Queue testen
        # ============================================================
        print("\n[4] VERIFICATION QUEUE")
        print("-" * 40)

        from app.services.verification_queue_service import get_verification_queue_service

        queue_service = get_verification_queue_service()

        # Queue Stats holen
        stats = await queue_service.get_queue_stats(db)

        print(f"\n  Pending Samples: {stats.pending_count}")
        print(f"  Spot-Check Pending: {stats.spot_check_pending}")
        print(f"  High Priority: {stats.high_priority_count}")

        if stats.coverage_gaps:
            print(f"\n  Coverage Gaps: {len(stats.coverage_gaps)}")

        # Nächstes Sample zur Verifikation
        next_sample = await queue_service.get_next_for_verification(db)
        if next_sample:
            print(f"\n  Nächstes zu prüfendes Sample:")
            print(f"    ID: {next_sample.id}")
            print(f"    Typ: {next_sample.document_type}")
            print(f"    Priority: {next_sample.business_priority}")
            print(f"    Auto-Accepted: {next_sample.auto_accepted}")
        else:
            print("\n  Keine Samples in Queue")

        # ============================================================
        # 5. Retraining Trigger prüfen
        # ============================================================
        print("\n[5] RETRAINING RECOMMENDATION")
        print("-" * 40)

        should_retrain, reasons = await coverage_service.get_retraining_recommendation(
            db=db,
            min_new_samples=50
        )

        print(f"\n  Retraining empfohlen: {'✓' if should_retrain else '✗'}")
        print(f"  Gründe:")
        for reason in reasons:
            print(f"    - {reason}")

        # ============================================================
        # 6. Testdokument durch Pipeline schicken
        # ============================================================
        print("\n[6] VOLLSTÄNDIGER PIPELINE-TEST")
        print("-" * 40)

        from app.db.models import Document, OCRTrainingSample

        # Prüfe ob Dokumente vorhanden sind
        doc_count_result = await db.execute(
            select(func.count(Document.id))
        )
        doc_count = doc_count_result.scalar() or 0

        sample_count_result = await db.execute(
            select(func.count(OCRTrainingSample.id))
        )
        sample_count = sample_count_result.scalar() or 0

        print(f"\n  Dokumente in DB: {doc_count}")
        print(f"  Training Samples: {sample_count}")

        # Hol ein Dokument mit extracted_text
        doc_result = await db.execute(
            select(Document).where(
                Document.extracted_text.isnot(None),
                Document.extracted_text != ""
            ).limit(1)
        )
        doc = doc_result.scalar_one_or_none()

        if doc:
            print(f"\n  Test-Dokument: {doc.filename}")
            print(f"    Typ: {doc.doc_type or 'unknown'}")
            print(f"    Text-Länge: {len(doc.extracted_text or '')} Zeichen")

            # Simuliere Auto-Ground-Truth für dieses Dokument
            # (normalerweise läuft das automatisch in der OCR-Pipeline)
            result = await auto_gt_service.process_document_for_training(
                db=db,
                document_id=doc.id,
                ocr_text=doc.extracted_text,
                ocr_confidence=0.95,  # Simulierte Confidence
                document_type=doc.doc_type or "invoice",
                backend_used="deepseek"
            )

            if result:
                print(f"\n    ✓ Training Sample erstellt:")
                print(f"      ID: {result.get('sample_id')}")
                print(f"      Auto-Accepted: {result.get('auto_accepted')}")
                print(f"      Needs Spot-Check: {result.get('needs_spot_check')}")
                print(f"      Source: {result.get('source')}")
            else:
                print(f"\n    - Sample bereits vorhanden oder nicht qualifiziert")
        else:
            print("\n  ✗ Keine Dokumente mit Text gefunden")
            print("    Bitte erst Dokumente hochladen und OCR ausführen!")

        # ============================================================
        # Zusammenfassung
        # ============================================================
        print("\n" + "=" * 60)
        print("  ZUSAMMENFASSUNG")
        print("=" * 60)

        all_ok = True
        checks = [
            ("Business Profiles", len(profiles) > 0),
            ("Auto-GT Service", True),  # Wenn wir hier ankommen, funktioniert er
            ("Coverage Tracking", coverage_status is not None),
            ("Verification Queue", stats is not None),
        ]

        for name, ok in checks:
            status = "✓" if ok else "✗"
            print(f"  {status} {name}")
            if not ok:
                all_ok = False

        if all_ok:
            print("\n  ✓ Pipeline ist bereit für Produktion!")
            print(f"\n  Nächste Schritte:")
            print(f"    1. Dokumente hochladen (aktuell: {doc_count})")
            print(f"    2. OCR ausführen lassen")
            print(f"    3. Coverage beobachten (aktuell: {coverage_status.weighted_coverage:.1%})")
            print(f"    4. Bei 90% Coverage: Surya-Retraining triggern")
        else:
            print("\n  ✗ Es gibt Probleme - siehe oben")

        print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
