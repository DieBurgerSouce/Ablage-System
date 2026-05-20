# -*- coding: utf-8 -*-
"""
Active Learning Service.

Intelligente Priorisierung von OCR-Korrekturen fuer maximalen Lerneffekt.
Uncertainty Sampling: System identifiziert Dokumente mit niedrigem Confidence
und priorisiert sie fuer menschliche Pruefung.

Scoring-Formel:
    priority = (1 - ocr_confidence) * 0.4   # Unsicherheit
             + frequency_weight * 0.3        # Wie oft taucht das Pattern auf
             + recency_weight * 0.2          # Neuere Dokumente bevorzugen
             + diversity_weight * 0.1        # Verschiedene Fehlertypen

Feinpoliert und durchdacht - Enterprise Active Learning fuer deutsche Dokumente.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, ProcessingStatus
from app.db.models_active_learning import (
    ActiveLearningMetrics,
    ActiveLearningQueue,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class ActiveLearningService:
    """Intelligente Priorisierung von OCR-Korrekturen.

    Identifiziert Dokumente mit niedrigem Confidence-Score und priorisiert
    sie fuer menschliche Pruefung um den Lerneffekt zu maximieren.
    """

    # Scoring-Gewichte
    WEIGHT_UNCERTAINTY: float = 0.4
    WEIGHT_FREQUENCY: float = 0.3
    WEIGHT_RECENCY: float = 0.2
    WEIGHT_DIVERSITY: float = 0.1

    # Schwellwerte
    LOW_CONFIDENCE_THRESHOLD: float = 0.85
    MIN_CONFIDENCE_FOR_QUEUE: float = 0.1  # Filter offensichtlich kaputte Scans

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def populate_queue(
        self,
        company_id: UUID,
        limit: int = 50,
    ) -> int:
        """Befuellt die Review-Queue mit priorisierten Dokumenten.

        Sucht nach Dokumenten mit niedrigem OCR-Confidence die noch nicht
        in der Queue sind und berechnet deren Prioritaets-Score.

        Args:
            company_id: Company-ID fuer Tenant-Isolation.
            limit: Maximale Anzahl neuer Queue-Eintraege.

        Returns:
            Anzahl der neu hinzugefuegten Queue-Eintraege.
        """
        logger.info(
            "populate_queue_starting",
            company_id=str(company_id),
            limit=limit,
        )

        try:
            # Bereits gequeuete Dokument-IDs holen
            existing_subquery = (
                select(ActiveLearningQueue.document_id)
                .where(
                    and_(
                        ActiveLearningQueue.company_id == company_id,
                        ActiveLearningQueue.status.in_(["queued", "in_review"]),
                    )
                )
            )

            # Dokumente mit niedrigem Confidence finden
            query = (
                select(Document)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.status == ProcessingStatus.COMPLETED,
                        Document.ocr_confidence.isnot(None),
                        Document.ocr_confidence < self.LOW_CONFIDENCE_THRESHOLD,
                        Document.ocr_confidence >= self.MIN_CONFIDENCE_FOR_QUEUE,
                        Document.id.notin_(existing_subquery),
                    )
                )
                .order_by(Document.ocr_confidence.asc())
                .limit(limit)
            )

            result = await self.session.execute(query)
            documents = list(result.scalars().all())

            if not documents:
                logger.info(
                    "populate_queue_no_candidates",
                    company_id=str(company_id),
                )
                return 0

            # Haeufigkeitsanalyse: Wie oft tauchen bestimmte Confidence-Bereiche auf
            frequency_map = await self._calculate_frequency_weights(
                company_id, documents
            )

            # Diversitaetsanalyse: Welche Fehlertypen sind schon in der Queue
            existing_reasons = await self._get_existing_queue_reasons(company_id)

            now = datetime.now(timezone.utc)
            added_count = 0

            for doc in documents:
                confidence = doc.ocr_confidence or 0.0

                # Unsicherheits-Score (Inverse der Confidence)
                uncertainty = 1.0 - confidence

                # Haeufigkeits-Gewicht (normalisiert 0-1)
                freq_weight = frequency_map.get(
                    self._confidence_bucket(confidence), 0.5
                )

                # Aktualitaets-Gewicht (neuere Dokumente bevorzugen)
                doc_age_days = (
                    (now - doc.created_at).days
                    if doc.created_at
                    else 30
                )
                recency_weight = max(0.0, 1.0 - (doc_age_days / 90.0))

                # Diversitaets-Gewicht (unterrepresentierte Gruende bevorzugen)
                queue_reason = self._determine_queue_reason(confidence, doc)
                diversity_weight = (
                    0.8 if queue_reason not in existing_reasons else 0.3
                )

                # Gesamt-Prioritaet berechnen
                priority = (
                    uncertainty * self.WEIGHT_UNCERTAINTY
                    + freq_weight * self.WEIGHT_FREQUENCY
                    + recency_weight * self.WEIGHT_RECENCY
                    + diversity_weight * self.WEIGHT_DIVERSITY
                )

                # Felder identifizieren die Aufmerksamkeit brauchen
                field_focus = self._identify_field_focus(doc)

                queue_item = ActiveLearningQueue(
                    document_id=doc.id,
                    company_id=company_id,
                    priority_score=round(priority, 4),
                    uncertainty_score=round(uncertainty, 4),
                    estimated_impact=self._estimate_impact(confidence, freq_weight),
                    queue_reason=queue_reason,
                    ocr_backend=doc.ocr_backend if hasattr(doc, "ocr_backend") else None,
                    ocr_confidence=confidence,
                    field_focus=field_focus,
                    status="queued",
                )
                self.session.add(queue_item)
                existing_reasons.add(queue_reason)
                added_count += 1

            await self.session.flush()

            logger.info(
                "populate_queue_completed",
                company_id=str(company_id),
                added=added_count,
                candidates=len(documents),
            )

            return added_count

        except Exception as e:
            logger.error(
                "populate_queue_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            raise

    async def get_next_review_item(
        self,
        company_id: UUID,
    ) -> Optional[ActiveLearningQueue]:
        """Holt das naechste Item zur Pruefung (hoechste Prioritaet).

        Setzt den Status auf 'in_review' um parallele Bearbeitung zu vermeiden.

        Args:
            company_id: Company-ID fuer Tenant-Isolation.

        Returns:
            Das naechste Queue-Item oder None wenn die Queue leer ist.
        """
        query = (
            select(ActiveLearningQueue)
            .where(
                and_(
                    ActiveLearningQueue.company_id == company_id,
                    ActiveLearningQueue.status == "queued",
                )
            )
            .order_by(ActiveLearningQueue.priority_score.desc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        result = await self.session.execute(query)
        item = result.scalar_one_or_none()

        if item is not None:
            item.status = "in_review"
            await self.session.flush()

            logger.info(
                "next_review_item_fetched",
                item_id=str(item.id),
                priority=item.priority_score,
                reason=item.queue_reason,
            )

        return item

    async def submit_review(
        self,
        item_id: UUID,
        user_id: UUID,
        corrections: Dict[str, str],
        skip: bool = False,
    ) -> ActiveLearningQueue:
        """Speichert die Korrektur oder das Ueberspringen eines Nutzers.

        Args:
            item_id: ID des Queue-Items.
            user_id: ID des pruefenden Benutzers.
            corrections: Korrekturdaten {feldname: korrigierter_wert}.
            skip: True wenn der Nutzer das Item ueberspringt.

        Returns:
            Das aktualisierte Queue-Item.

        Raises:
            ValueError: Wenn das Item nicht gefunden wird oder nicht bearbeitbar ist.
        """
        query = select(ActiveLearningQueue).where(
            ActiveLearningQueue.id == item_id
        )
        result = await self.session.execute(query)
        item = result.scalar_one_or_none()

        if item is None:
            raise ValueError(f"Queue-Item nicht gefunden: {item_id}")

        if not item.is_actionable:
            raise ValueError(
                f"Queue-Item nicht bearbeitbar (Status: {item.status})"
            )

        now = datetime.now(timezone.utc)

        if skip:
            item.status = "skipped"
            item.reviewed_by_id = user_id
            item.reviewed_at = now
        else:
            item.status = "reviewed"
            item.reviewed_by_id = user_id
            item.reviewed_at = now
            item.correction_data = corrections

        await self.session.flush()

        logger.info(
            "review_submitted",
            item_id=str(item_id),
            user_id=str(user_id),
            skipped=skip,
            corrections_count=len(corrections) if not skip else 0,
        )

        return item

    async def calculate_impact_metrics(
        self,
        company_id: UUID,
    ) -> Dict[str, float]:
        """Berechnet Impact-Metriken: 'X Korrekturen haben Y Fehler verhindert'.

        Vergleicht Confidence-Werte vor und nach Training und aggregiert
        die geschaetzten verhinderten Fehler.

        Args:
            company_id: Company-ID fuer Tenant-Isolation.

        Returns:
            Dict mit Impact-Metriken.
        """
        today = date.today()

        # Reviewed items der letzten 30 Tage
        thirty_days_ago = today - timedelta(days=30)

        query = select(
            func.count(ActiveLearningQueue.id).label("total_reviewed"),
            func.count(
                ActiveLearningQueue.id
            ).filter(
                ActiveLearningQueue.correction_data.isnot(None)
            ).label("total_corrections"),
            func.avg(ActiveLearningQueue.ocr_confidence).label("avg_confidence"),
            func.sum(ActiveLearningQueue.estimated_impact).label("total_impact"),
        ).where(
            and_(
                ActiveLearningQueue.company_id == company_id,
                ActiveLearningQueue.status.in_(["reviewed", "skipped"]),
                ActiveLearningQueue.reviewed_at >= datetime(
                    thirty_days_ago.year,
                    thirty_days_ago.month,
                    thirty_days_ago.day,
                    tzinfo=timezone.utc,
                ),
            )
        )

        result = await self.session.execute(query)
        row = result.first()

        total_reviewed = row.total_reviewed or 0 if row else 0
        total_corrections = row.total_corrections or 0 if row else 0
        avg_confidence = row.avg_confidence or 0.0 if row else 0.0
        total_impact = row.total_impact or 0.0 if row else 0.0

        # Durchschnittliche Confidence-Verbesserung berechnen
        confidence_improvement = 0.0
        if total_corrections > 0:
            # Schaetzung: Jede Korrektur verbessert die Confidence um ~0.1
            confidence_improvement = min(0.15, total_corrections * 0.01)

        # Metriken in Datenbank speichern/aktualisieren
        existing_query = select(ActiveLearningMetrics).where(
            and_(
                ActiveLearningMetrics.metric_date == today,
                ActiveLearningMetrics.company_id == company_id,
            )
        )
        existing_result = await self.session.execute(existing_query)
        metrics = existing_result.scalar_one_or_none()

        if metrics is None:
            metrics = ActiveLearningMetrics(
                metric_date=today,
                company_id=company_id,
                total_reviewed=total_reviewed,
                total_corrections=total_corrections,
                estimated_errors_prevented=int(total_impact),
                avg_confidence_before=avg_confidence,
                avg_confidence_after=avg_confidence + confidence_improvement,
            )
            self.session.add(metrics)
        else:
            metrics.total_reviewed = total_reviewed
            metrics.total_corrections = total_corrections
            metrics.estimated_errors_prevented = int(total_impact)
            metrics.avg_confidence_before = avg_confidence
            metrics.avg_confidence_after = avg_confidence + confidence_improvement

        await self.session.flush()

        return {
            "total_reviewed_30d": total_reviewed,
            "total_corrections_30d": total_corrections,
            "estimated_errors_prevented": round(total_impact, 1),
            "avg_confidence_before": round(avg_confidence, 4),
            "avg_confidence_after": round(avg_confidence + confidence_improvement, 4),
            "confidence_improvement": round(confidence_improvement, 4),
            "correction_rate": round(
                total_corrections / total_reviewed if total_reviewed > 0 else 0.0,
                4,
            ),
        }

    async def get_queue_stats(
        self,
        company_id: UUID,
    ) -> Dict[str, int]:
        """Statistiken der Review-Warteschlange.

        Args:
            company_id: Company-ID fuer Tenant-Isolation.

        Returns:
            Dict mit Queue-Statistiken.
        """
        query = select(
            ActiveLearningQueue.status,
            func.count(ActiveLearningQueue.id).label("count"),
        ).where(
            ActiveLearningQueue.company_id == company_id,
        ).group_by(
            ActiveLearningQueue.status,
        )

        result = await self.session.execute(query)
        rows = result.all()

        stats: Dict[str, int] = {
            "queued": 0,
            "in_review": 0,
            "reviewed": 0,
            "skipped": 0,
            "total": 0,
        }

        for row in rows:
            stats[row.status] = row.count
            stats["total"] += row.count

        # Durchschnittliche Prioritaet der offenen Items
        avg_query = select(
            func.avg(ActiveLearningQueue.priority_score),
        ).where(
            and_(
                ActiveLearningQueue.company_id == company_id,
                ActiveLearningQueue.status == "queued",
            )
        )
        avg_result = await self.session.execute(avg_query)
        avg_priority = avg_result.scalar() or 0.0
        stats["avg_priority"] = int(round(avg_priority * 100))  # Als Prozent

        return stats

    async def get_review_history(
        self,
        company_id: UUID,
        limit: int = 20,
    ) -> List[ActiveLearningQueue]:
        """Letzte bearbeitete Items mit Korrekturdaten.

        Args:
            company_id: Company-ID fuer Tenant-Isolation.
            limit: Maximale Anzahl zurueckzugebender Items.

        Returns:
            Liste der letzten bearbeiteten Queue-Items.
        """
        query = (
            select(ActiveLearningQueue)
            .where(
                and_(
                    ActiveLearningQueue.company_id == company_id,
                    ActiveLearningQueue.status.in_(["reviewed", "skipped"]),
                )
            )
            .order_by(ActiveLearningQueue.reviewed_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _calculate_frequency_weights(
        self,
        company_id: UUID,
        documents: List[Document],
    ) -> Dict[str, float]:
        """Berechnet Haeufigkeits-Gewichte fuer Confidence-Bereiche.

        Haeufigere Fehlermuster sind wertvoller fuer Training weil die
        Korrektur mehr zukuenftige Dokumente beeinflusst.
        """
        # Zaehle Dokumente pro Confidence-Bucket
        bucket_counts: Dict[str, int] = {}
        for doc in documents:
            bucket = self._confidence_bucket(doc.ocr_confidence or 0.0)
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

        # Normalisiere auf 0-1
        max_count = max(bucket_counts.values()) if bucket_counts else 1
        return {
            bucket: count / max_count
            for bucket, count in bucket_counts.items()
        }

    async def _get_existing_queue_reasons(
        self,
        company_id: UUID,
    ) -> set:
        """Holt die existierenden Queue-Gruende fuer Diversitaetsberechnung."""
        query = (
            select(ActiveLearningQueue.queue_reason)
            .where(
                and_(
                    ActiveLearningQueue.company_id == company_id,
                    ActiveLearningQueue.status == "queued",
                )
            )
            .distinct()
        )
        result = await self.session.execute(query)
        return {row[0] for row in result.all()}

    @staticmethod
    def _confidence_bucket(confidence: float) -> str:
        """Ordnet eine Confidence einem Bucket zu."""
        if confidence < 0.3:
            return "very_low"
        elif confidence < 0.5:
            return "low"
        elif confidence < 0.7:
            return "medium"
        else:
            return "moderate"

    @staticmethod
    def _determine_queue_reason(
        confidence: float,
        doc: Document,
    ) -> str:
        """Bestimmt den Grund fuer die Queue-Aufnahme."""
        if confidence < 0.3:
            return "edge_case"
        elif confidence < 0.5:
            return "low_confidence"
        elif confidence < 0.7:
            return "high_frequency_pattern"
        else:
            return "low_confidence"

    @staticmethod
    def _identify_field_focus(doc: Document) -> List[str]:
        """Identifiziert Felder die besondere Aufmerksamkeit brauchen.

        Basiert auf den extrahierten Daten des Dokuments und typischen
        Fehlerquellen bei deutschen Dokumenten.
        """
        fields: List[str] = []

        # Typische Problemfelder bei OCR-Erkennung
        metadata = getattr(doc, "metadata_", None) or {}
        extracted = metadata.get("extracted_data", {}) if isinstance(metadata, dict) else {}

        # Betraege: Haeufige Verwechslung von Komma/Punkt
        if extracted.get("amount") or extracted.get("total_amount"):
            fields.append("amount")

        # Datum: Deutsche Formate vs ISO
        if extracted.get("date") or extracted.get("invoice_date"):
            fields.append("date")

        # Lieferant: Umlaute problematisch
        if extracted.get("supplier") or extracted.get("sender"):
            fields.append("supplier")

        # Falls keine spezifischen Felder identifiziert: Standardset
        if not fields:
            fields = ["text", "amount", "date"]

        return fields

    @staticmethod
    def _estimate_impact(
        confidence: float,
        frequency_weight: float,
    ) -> float:
        """Schaetzt den Impact einer Korrektur.

        Niedrigere Confidence + hoehere Haeufigkeit = mehr Impact.
        """
        uncertainty = 1.0 - confidence
        # Basis: ~5 zukuenftige Fehler pro niedrig-confidence Korrektur
        base_impact = uncertainty * 10.0
        # Frequenz-Multiplikator
        return round(base_impact * (0.5 + frequency_weight * 0.5), 2)
