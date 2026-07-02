# -*- coding: utf-8 -*-
"""
Document Progress Service für Ablage-System.

Live-Status-Tracker für Dokumente im DHL-Tracking-Stil.

Zeigt Echtzeit-Fortschritt:
Hochgeladen -> OCR laeuft (43%) -> Extraktion -> Prüfung -> Fertig

Feinpoliert und durchdacht - Enterprise Document Progress Tracking.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models_smart_dashboard import (
    BatchProgressTracker,
    DocumentProgressTracker,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Verarbeitungsschritte mit deutschen Labels
# =============================================================================

PROCESSING_STEPS: List[Tuple[str, str]] = [
    ("hochgeladen", "Hochgeladen"),
    ("ocr_warteschlange", "In OCR-Warteschlange"),
    ("ocr_laeuft", "OCR laeuft"),
    ("extraktion", "Daten-Extraktion"),
    ("validierung", "Validierung"),
    ("fertig", "Fertig"),
]

# Mapping für schnellen Zugriff
STEP_LABELS: Dict[str, str] = dict(PROCESSING_STEPS)
STEP_ORDER: Dict[str, int] = {step: idx for idx, (step, _) in enumerate(PROCESSING_STEPS)}
TOTAL_STEPS = len(PROCESSING_STEPS)


# =============================================================================
# Document Progress Service
# =============================================================================

class DocumentProgressService:
    """Live-Status-Tracker für Dokumente - DHL-Tracking-Stil."""

    async def create_tracker(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
    ) -> DocumentProgressTracker:
        """Neuen Progress-Tracker für ein Dokument erstellen.

        Args:
            db: Async Datenbank-Session
            document_id: Dokument-ID
            company_id: Firmen-ID

        Returns:
            Neuer DocumentProgressTracker
        """
        now = utc_now()

        tracker = DocumentProgressTracker(
            document_id=document_id,
            company_id=company_id,
            current_step="hochgeladen",
            total_steps=TOTAL_STEPS,
            progress_percent=round((1 / TOTAL_STEPS) * 100, 1),
            steps_completed=[
                {
                    "name": "hochgeladen",
                    "status": "completed",
                    "started_at": now.isoformat(),
                    "completed_at": now.isoformat(),
                    "metadata": {},
                }
            ],
        )
        db.add(tracker)
        await db.flush()

        logger.info(
            "document_progress.tracker_created",
            tracker_id=str(tracker.id),
            document_id=str(document_id),
            company_id=str(company_id),
        )

        return tracker

    async def update_progress(
        self,
        db: AsyncSession,
        document_id: UUID,
        step: str,
        progress_percent: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> Optional[DocumentProgressTracker]:
        """Fortschritt aktualisieren - wird von OCR-Tasks aufgerufen.

        Args:
            db: Async Datenbank-Session
            document_id: Dokument-ID
            step: Aktueller Schritt (z.B. "ocr_laeuft")
            progress_percent: Optionaler Fortschritt in Prozent (berechnet sonst automatisch)
            error_message: Optionale Fehlernachricht

        Returns:
            Aktualisierter Tracker oder None falls nicht gefunden
        """
        stmt = select(DocumentProgressTracker).where(
            DocumentProgressTracker.document_id == document_id,
        )
        result = await db.execute(stmt)
        tracker = result.scalar_one_or_none()

        if not tracker:
            logger.warning(
                "document_progress.tracker_not_found",
                document_id=str(document_id),
                step=step,
            )
            return None

        now = utc_now()
        steps_completed = list(tracker.steps_completed or [])

        # Fehlerfall behandeln
        if error_message:
            tracker.current_step = "fehler"
            tracker.error_message = error_message
            tracker.progress_percent = 0.0
            steps_completed.append({
                "name": "fehler",
                "status": "failed",
                "started_at": now.isoformat(),
                "completed_at": now.isoformat(),
                "metadata": {"error": error_message},
            })
            tracker.steps_completed = steps_completed
            tracker.updated_at = now
            await db.flush()

            logger.warning(
                "document_progress.error",
                document_id=str(document_id),
                step=step,
            )
            return tracker

        # Normaler Fortschritt
        tracker.current_step = step
        tracker.updated_at = now

        # Schritt als abgeschlossen markieren
        completed_step_names = {s.get("name") for s in steps_completed}
        if step not in completed_step_names:
            steps_completed.append({
                "name": step,
                "status": "completed",
                "started_at": now.isoformat(),
                "completed_at": now.isoformat(),
                "metadata": {},
            })
            tracker.steps_completed = steps_completed

        # Fortschritt berechnen
        step_idx = STEP_ORDER.get(step, 0)
        if progress_percent is not None:
            tracker.progress_percent = min(max(progress_percent, 0.0), 100.0)
        else:
            tracker.progress_percent = round(
                ((step_idx + 1) / TOTAL_STEPS) * 100, 1,
            )

        # Fertigstellung
        if step == "fertig":
            tracker.completed_at = now
            tracker.progress_percent = 100.0

        # Geschätzte Fertigstellungszeit berechnen
        tracker.estimated_completion = self._estimate_completion(
            step, steps_completed, now,
        )

        await db.flush()

        logger.info(
            "document_progress.updated",
            document_id=str(document_id),
            step=step,
            progress_percent=tracker.progress_percent,
        )

        return tracker

    async def get_progress(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Optional[DocumentProgressTracker]:
        """Aktuellen Fortschritt abrufen.

        Args:
            db: Async Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Fortschritts-Tracker oder None
        """
        stmt = select(DocumentProgressTracker).where(
            DocumentProgressTracker.document_id == document_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_batch_progress(
        self,
        db: AsyncSession,
        company_id: UUID,
        batch_id: Optional[UUID] = None,
    ) -> Dict[str, object]:
        """Batch-Fortschritt: Gesamtfortschritt + geschätzte Restzeit + Fehler.

        Args:
            db: Async Datenbank-Session
            company_id: Firmen-ID
            batch_id: Optionale Batch-ID für spezifischen Batch

        Returns:
            Batch-Fortschritts-Übersicht
        """
        logger.info(
            "document_progress.get_batch_progress",
            company_id=str(company_id),
        )

        # Falls spezifischer Batch angefragt, BatchProgressTracker nutzen
        if batch_id:
            batch_stmt = select(BatchProgressTracker).where(
                and_(
                    BatchProgressTracker.batch_id == batch_id,
                    BatchProgressTracker.company_id == company_id,
                )
            )
            batch_result = await db.execute(batch_stmt)
            batch_tracker = batch_result.scalar_one_or_none()
            if batch_tracker:
                return batch_tracker.to_dict()

        # Ansonsten: Gesamtübersicht aus DocumentProgressTracker
        step_counts_stmt = (
            select(
                DocumentProgressTracker.current_step,
                func.count(DocumentProgressTracker.id).label("count"),
            )
            .where(DocumentProgressTracker.company_id == company_id)
            .group_by(DocumentProgressTracker.current_step)
        )
        result = await db.execute(step_counts_stmt)
        step_counts: Dict[str, int] = {row[0]: row[1] for row in result.all()}

        total = sum(step_counts.values())
        completed = step_counts.get("fertig", 0)
        errors = step_counts.get("fehler", 0)
        in_progress = total - completed - errors

        # Gesamtfortschritt berechnen
        if total > 0:
            overall_percent = round((completed / total) * 100, 1)
        else:
            overall_percent = 0.0

        # Durchschnittliche Verarbeitungszeit berechnen
        avg_time_stmt = (
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        DocumentProgressTracker.completed_at
                        - DocumentProgressTracker.started_at,
                    )
                )
            )
            .where(
                and_(
                    DocumentProgressTracker.company_id == company_id,
                    DocumentProgressTracker.completed_at.isnot(None),
                )
            )
        )
        avg_result = await db.execute(avg_time_stmt)
        avg_seconds = avg_result.scalar()

        # Geschätzte Restzeit
        estimated_remaining_seconds: Optional[float] = None
        if avg_seconds and in_progress > 0:
            estimated_remaining_seconds = round(float(avg_seconds) * in_progress, 1)

        # Fehlerliste (letzte 10)
        error_stmt = (
            select(DocumentProgressTracker)
            .where(
                and_(
                    DocumentProgressTracker.company_id == company_id,
                    DocumentProgressTracker.current_step == "fehler",
                )
            )
            .order_by(DocumentProgressTracker.updated_at.desc())
            .limit(10)
        )
        error_result = await db.execute(error_stmt)
        error_docs = [
            {
                "document_id": str(t.document_id),
                "error_message": t.error_message,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in error_result.scalars().all()
        ]

        return {
            "total_documents": total,
            "completed": completed,
            "in_progress": in_progress,
            "errors": errors,
            "overall_percent": overall_percent,
            "step_counts": step_counts,
            "avg_processing_seconds": round(float(avg_seconds), 1) if avg_seconds else None,
            "estimated_remaining_seconds": estimated_remaining_seconds,
            "recent_errors": error_docs,
            "processing_steps": [
                {"step": s, "label": l} for s, l in PROCESSING_STEPS
            ],
        }

    async def create_batch_tracker(
        self,
        db: AsyncSession,
        batch_id: UUID,
        company_id: UUID,
        total_documents: int,
    ) -> BatchProgressTracker:
        """Neuen Batch-Progress-Tracker erstellen.

        Args:
            db: Async Datenbank-Session
            batch_id: Batch-ID
            company_id: Firmen-ID
            total_documents: Gesamtanzahl Dokumente

        Returns:
            Neuer BatchProgressTracker
        """
        tracker = BatchProgressTracker(
            batch_id=batch_id,
            company_id=company_id,
            total_documents=total_documents,
        )
        db.add(tracker)
        await db.flush()

        logger.info(
            "document_progress.batch_tracker_created",
            batch_id=str(batch_id),
            company_id=str(company_id),
            total_documents=total_documents,
        )

        return tracker

    async def update_batch_progress(
        self,
        db: AsyncSession,
        batch_id: UUID,
        processed: int,
        failed: int = 0,
        current_document_name: Optional[str] = None,
    ) -> Optional[BatchProgressTracker]:
        """Batch-Fortschritt aktualisieren.

        Args:
            db: Async Datenbank-Session
            batch_id: Batch-ID
            processed: Anzahl verarbeiteter Dokumente
            failed: Anzahl fehlgeschlagener Dokumente
            current_document_name: Name des aktuell verarbeiteten Dokuments

        Returns:
            Aktualisierter Batch-Tracker oder None
        """
        stmt = select(BatchProgressTracker).where(
            BatchProgressTracker.batch_id == batch_id,
        )
        result = await db.execute(stmt)
        tracker = result.scalar_one_or_none()

        if not tracker:
            return None

        now = utc_now()
        tracker.processed = processed
        tracker.failed = failed
        tracker.current_document_name = current_document_name
        tracker.updated_at = now

        if tracker.total_documents > 0:
            tracker.progress_percent = round(
                ((processed + failed) / tracker.total_documents) * 100, 1,
            )

        # Zeitschätzung
        elapsed = (now - tracker.started_at).total_seconds() if tracker.started_at else 0
        done = processed + failed
        if done > 0 and elapsed > 0:
            remaining = tracker.total_documents - done
            avg_per_doc = elapsed / done
            tracker.estimated_remaining_seconds = int(avg_per_doc * remaining)

        # Fertigstellung prüfen
        if done >= tracker.total_documents:
            tracker.completed_at = now
            tracker.progress_percent = 100.0
            tracker.estimated_remaining_seconds = 0

        await db.flush()
        return tracker

    async def cleanup_completed_trackers(
        self,
        db: AsyncSession,
        older_than_days: int = 7,
    ) -> int:
        """Alte abgeschlossene Tracker entfernen.

        Args:
            db: Async Datenbank-Session
            older_than_days: Alter in Tagen ab dem gelöscht wird

        Returns:
            Anzahl gelöschter Tracker
        """
        cutoff = utc_now() - timedelta(days=older_than_days)

        # Dokument-Tracker bereinigen
        doc_stmt = delete(DocumentProgressTracker).where(
            and_(
                DocumentProgressTracker.current_step == "fertig",
                DocumentProgressTracker.completed_at < cutoff,
            )
        )
        doc_result = await db.execute(doc_stmt)
        doc_deleted = doc_result.rowcount

        # Batch-Tracker bereinigen
        batch_stmt = delete(BatchProgressTracker).where(
            and_(
                BatchProgressTracker.completed_at.isnot(None),
                BatchProgressTracker.completed_at < cutoff,
            )
        )
        batch_result = await db.execute(batch_stmt)
        batch_deleted = batch_result.rowcount

        total_deleted = doc_deleted + batch_deleted

        logger.info(
            "document_progress.cleanup_completed",
            doc_deleted=doc_deleted,
            batch_deleted=batch_deleted,
            total_deleted=total_deleted,
            older_than_days=older_than_days,
        )

        return total_deleted

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    @staticmethod
    def _estimate_completion(
        current_step: str,
        steps_completed: List[Dict[str, str]],
        now: datetime,
    ) -> Optional[datetime]:
        """Geschätzte Fertigstellungszeit basierend auf bisheriger Dauer.

        Args:
            current_step: Aktueller Verarbeitungsschritt
            steps_completed: Bisher abgeschlossene Schritte
            now: Aktuelle Zeit

        Returns:
            Geschätzte Fertigstellungszeit oder None
        """
        if current_step in ("fertig", "fehler"):
            return None

        current_order = STEP_ORDER.get(current_step, 0)
        remaining_steps = TOTAL_STEPS - current_order - 1

        if remaining_steps <= 0:
            return None

        # Durchschnittliche Dauer pro Schritt aus bisherigen Schritten
        if len(steps_completed) >= 2:
            try:
                first_ts = datetime.fromisoformat(steps_completed[0]["completed_at"])
                last_ts = datetime.fromisoformat(steps_completed[-1]["completed_at"])
                elapsed = (last_ts - first_ts).total_seconds()
                completed_count = len(steps_completed)
                if completed_count > 0 and elapsed > 0:
                    avg_per_step = elapsed / completed_count
                    estimated_remaining = avg_per_step * remaining_steps
                    return now + timedelta(seconds=estimated_remaining)
            except (KeyError, ValueError) as e:
                logger.debug(
                    "progress_eta_estimate_fallback",
                    error_type=type(e).__name__,
                )

        # Fallback: 30 Sekunden pro Schritt
        return now + timedelta(seconds=30 * remaining_steps)
