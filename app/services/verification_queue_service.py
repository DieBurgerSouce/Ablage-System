# -*- coding: utf-8 -*-
"""
Verification Queue Service für Ablage-System OCR.

Priorisierte Queue für manuelle Verifikation von OCR-Samples.

Bei 500+ Dokumenten/Tag werden ~80-90% automatisch akzeptiert.
Dieser Service verwaltet die restlichen ~10-20% für manuelle Prüfung:

1. Business-kritische Typen (Rechnungen > Verträge > Briefe)
2. Coverage-Lücken (Typen unter 90% Abdeckung)
3. Auto-Accepted Stichproben (10% der auto-accepted)
4. Low-Confidence Samples

Feinpoliert und durchdacht - Enterprise-grade Verification Queue.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    OCRTrainingSample,
    BusinessDocumentProfile,
    TrainingSampleStatus,
    User,
    Document,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Types und Enums
# =============================================================================

class VerificationPriority(str, Enum):
    """Priorität für Verifikation."""
    CRITICAL = "critical"      # Business-kritisch, Coverage-Lücke
    HIGH = "high"              # Stichproben-Review, niedrige Confidence
    MEDIUM = "medium"          # Standard-Samples
    LOW = "low"                # Optional, keine Eile


@dataclass
class QueueItem:
    """Ein Element in der Verifikations-Queue."""
    sample_id: UUID
    document_type: Optional[str]
    priority: VerificationPriority
    priority_score: float  # 0-100, höher = wichtiger
    reason: str
    ocr_text_preview: str
    confidence: float
    is_spot_check: bool
    created_at: datetime
    file_path: Optional[str] = None
    document_id: Optional[UUID] = None  # Verknüpfung zu Document für ExtractedData


@dataclass
class QueueStats:
    """Statistiken der Verifikations-Queue."""
    total_pending: int
    pending_by_priority: Dict[str, int]
    pending_by_type: Dict[str, int]
    spot_checks_pending: int
    oldest_item_days: float
    avg_wait_time_hours: float
    coverage_gaps: List[Dict[str, Any]]


@dataclass
class VerificationResult:
    """Ergebnis einer Verifikation."""
    sample_id: UUID
    approved: bool
    corrected_text: Optional[str]
    correction_notes: Optional[str]
    verified_by_id: UUID
    verified_at: datetime


# =============================================================================
# Verification Queue Service
# =============================================================================

class VerificationQueueService:
    """
    Service für priorisierte Verifikations-Queue.

    Priorisierung:
    1. Business-kritische Typen (Rechnungen > Verträge > Briefe)
    2. Coverage-Lücken (Typen unter 90% Abdeckung)
    3. Auto-Accepted Stichproben (10% der auto-accepted)
    4. Low-Confidence Samples
    """

    # Priorität basierend auf Dokumenttyp
    TYPE_PRIORITY = {
        "invoice": 1.5,       # Rechnungen hoechste Priorität
        "contract": 1.3,      # Verträge hoch
        "order_confirmation": 1.2,
        "letter": 1.0,        # Standard
        "delivery_note": 0.8, # Niedriger
    }

    # Gewichtung für Priority-Score Berechnung
    PRIORITY_WEIGHTS = {
        "coverage_gap": 30,      # Lücke in Coverage
        "spot_check": 25,        # Stichproben-Review
        "type_priority": 20,     # Dokumenttyp-Wichtigkeit
        "low_confidence": 15,    # Niedrige Confidence
        "age": 10,               # Alter des Samples
    }

    # =========================================================================
    # QUEUE MANAGEMENT
    # =========================================================================

    async def get_next_for_verification(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_type: Optional[str] = None,
        include_spot_checks: bool = True,
    ) -> Optional[QueueItem]:
        """
        Holt nächstes Sample zur Verifikation.

        Priorisiert nach:
        1. Priority-Score (höher = wichtiger)
        2. Alter (aeltere zuerst)

        Args:
            db: Datenbank-Session
            user_id: User der verifiziert
            document_type: Optional Filter für Dokumenttyp
            include_spot_checks: Ob Stichproben-Reviews eingeschlossen werden

        Returns:
            QueueItem oder None wenn Queue leer
        """
        # Hole Coverage-Status für Priority-Berechnung
        coverage_status = await self._get_coverage_status(db)

        # Baue Query für pending Samples
        # Filtere Samples ohne Text heraus (leere Platzhalter)
        query = select(OCRTrainingSample).where(
            and_(
                or_(
                    # Nicht-verifizierte Samples
                    OCRTrainingSample.status == TrainingSampleStatus.PENDING.value,
                    OCRTrainingSample.status == TrainingSampleStatus.ANNOTATED.value,
                    # Stichproben-Reviews
                    and_(
                        OCRTrainingSample.needs_spot_check == True,
                        OCRTrainingSample.spot_check_passed.is_(None),
                    ) if include_spot_checks else False,
                ),
                OCRTrainingSample.deleted_at.is_(None),
                # Nur Samples mit echtem Text (keine leeren Platzhalter)
                OCRTrainingSample.ground_truth_text.isnot(None),
                func.length(OCRTrainingSample.ground_truth_text) > 0,
            )
        )

        if document_type:
            query = query.where(OCRTrainingSample.document_type == document_type)

        # Hole alle Kandidaten
        result = await db.execute(query)
        samples = result.scalars().all()

        if not samples:
            return None

        # Berechne Priority-Score für alle Samples
        scored_samples = []
        for sample in samples:
            score = await self._calculate_priority_score(
                sample=sample,
                coverage_status=coverage_status,
            )
            scored_samples.append((sample, score))

        # Sortiere nach Score (hoechster zuerst)
        scored_samples.sort(key=lambda x: x[1], reverse=True)

        # Hole bestes Sample
        best_sample, best_score = scored_samples[0]

        # Hole document_id über file_path Lookup
        document_id = await self._lookup_document_id(db, best_sample.file_path)

        # Erstelle QueueItem
        return QueueItem(
            sample_id=best_sample.id,
            document_type=best_sample.document_type,
            priority=self._score_to_priority(best_score),
            priority_score=best_score,
            reason=self._get_priority_reason(best_sample, coverage_status),
            ocr_text_preview=best_sample.ground_truth_text[:500] if best_sample.ground_truth_text else "",
            confidence=best_sample.auto_acceptance_confidence or 0.0,
            is_spot_check=best_sample.needs_spot_check and best_sample.auto_accepted,
            created_at=best_sample.created_at,
            file_path=best_sample.file_path,
            document_id=document_id,
        )

    async def get_queue_stats(self, db: AsyncSession) -> QueueStats:
        """
        Holt Statistiken der Verifikations-Queue.

        Returns:
            QueueStats mit detaillierten Metriken
        """
        # Zaehle pending Samples (nur mit echtem Text)
        total_result = await db.execute(
            select(func.count(OCRTrainingSample.id)).where(
                and_(
                    or_(
                        OCRTrainingSample.status == TrainingSampleStatus.PENDING.value,
                        OCRTrainingSample.status == TrainingSampleStatus.ANNOTATED.value,
                    ),
                    OCRTrainingSample.deleted_at.is_(None),
                    OCRTrainingSample.ground_truth_text.isnot(None),
                    func.length(OCRTrainingSample.ground_truth_text) > 0,
                )
            )
        )
        total_pending = total_result.scalar() or 0

        # Zaehle pending Stichproben (nur mit echtem Text)
        spot_check_result = await db.execute(
            select(func.count(OCRTrainingSample.id)).where(
                and_(
                    OCRTrainingSample.needs_spot_check == True,
                    OCRTrainingSample.spot_check_passed.is_(None),
                    OCRTrainingSample.deleted_at.is_(None),
                    OCRTrainingSample.ground_truth_text.isnot(None),
                    func.length(OCRTrainingSample.ground_truth_text) > 0,
                )
            )
        )
        spot_checks_pending = spot_check_result.scalar() or 0

        # Zaehle nach Dokumenttyp (nur mit echtem Text)
        type_result = await db.execute(
            select(
                OCRTrainingSample.document_type,
                func.count(OCRTrainingSample.id)
            )
            .where(
                and_(
                    or_(
                        OCRTrainingSample.status == TrainingSampleStatus.PENDING.value,
                        OCRTrainingSample.status == TrainingSampleStatus.ANNOTATED.value,
                    ),
                    OCRTrainingSample.deleted_at.is_(None),
                    OCRTrainingSample.ground_truth_text.isnot(None),
                    func.length(OCRTrainingSample.ground_truth_text) > 0,
                )
            )
            .group_by(OCRTrainingSample.document_type)
        )
        pending_by_type = {row[0] or "unknown": row[1] for row in type_result.fetchall()}

        # Berechne Priority-Verteilung (vereinfacht)
        pending_by_priority = {
            "critical": 0,
            "high": spot_checks_pending,  # Stichproben = High Priority
            "medium": max(0, total_pending - spot_checks_pending),
            "low": 0,
        }

        # Aeltestes Sample
        oldest_result = await db.execute(
            select(func.min(OCRTrainingSample.created_at)).where(
                and_(
                    or_(
                        OCRTrainingSample.status == TrainingSampleStatus.PENDING.value,
                        OCRTrainingSample.status == TrainingSampleStatus.ANNOTATED.value,
                    ),
                    OCRTrainingSample.deleted_at.is_(None),
                )
            )
        )
        oldest_date = oldest_result.scalar()
        oldest_item_days = 0.0
        if oldest_date:
            oldest_item_days = (datetime.now(timezone.utc) - oldest_date).total_seconds() / 86400

        # Coverage-Lücken
        coverage_gaps = await self._get_coverage_gaps(db)

        return QueueStats(
            total_pending=total_pending,
            pending_by_priority=pending_by_priority,
            pending_by_type=pending_by_type,
            spot_checks_pending=spot_checks_pending,
            oldest_item_days=oldest_item_days,
            avg_wait_time_hours=oldest_item_days * 24 / 2,  # Schätzung
            coverage_gaps=coverage_gaps,
        )

    async def verify_sample(
        self,
        db: AsyncSession,
        sample_id: UUID,
        user_id: UUID,
        approved: bool,
        corrected_text: Optional[str] = None,
        correction_notes: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verifiziert ein Sample.

        Args:
            db: Datenbank-Session
            sample_id: Sample-ID
            user_id: Verifizierer
            approved: Ob Ground-Truth akzeptiert wird
            corrected_text: Korrigierter Text (falls nicht approved)
            correction_notes: Notizen zur Korrektur

        Returns:
            VerificationResult
        """
        # Hole Sample
        result = await db.execute(
            select(OCRTrainingSample).where(OCRTrainingSample.id == sample_id)
        )
        sample = result.scalar_one_or_none()

        if not sample:
            raise ValueError(f"Sample {sample_id} nicht gefunden")

        now = datetime.now(timezone.utc)

        # Handle Stichproben-Review
        if sample.needs_spot_check and sample.auto_accepted:
            sample.spot_check_passed = approved
            sample.spot_checked_at = now
            sample.spot_checked_by_id = user_id

            if not approved and corrected_text:
                # Korrektur des auto-accepted Textes
                sample.ground_truth_text = corrected_text
                sample.annotation_notes = correction_notes

            logger.info(
                "spot_check_completed",
                sample_id=str(sample_id),
                passed=approved,
            )
        else:
            # Standard-Verifikation
            if approved:
                sample.status = TrainingSampleStatus.VERIFIED.value
            else:
                sample.status = TrainingSampleStatus.REJECTED.value if not corrected_text else TrainingSampleStatus.ANNOTATED.value

            sample.verified_by_id = user_id
            sample.verified_at = now

            if corrected_text:
                sample.ground_truth_text = corrected_text

            if correction_notes:
                sample.annotation_notes = correction_notes

            logger.info(
                "sample_verified",
                sample_id=str(sample_id),
                approved=approved,
                status=sample.status,
            )

        await db.commit()

        # Update Profile Statistics
        if sample.document_type:
            await self._update_profile_stats(db, sample.document_type)

        return VerificationResult(
            sample_id=sample_id,
            approved=approved,
            corrected_text=corrected_text,
            correction_notes=correction_notes,
            verified_by_id=user_id,
            verified_at=now,
        )

    async def get_items_by_type(
        self,
        db: AsyncSession,
        document_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[QueueItem]:
        """
        Holt Queue-Items für einen bestimmten Dokumenttyp.

        Args:
            db: Datenbank-Session
            document_type: Dokumenttyp
            limit: Maximale Anzahl
            offset: Offset für Pagination

        Returns:
            Liste von QueueItems
        """
        coverage_status = await self._get_coverage_status(db)

        result = await db.execute(
            select(OCRTrainingSample)
            .where(
                and_(
                    OCRTrainingSample.document_type == document_type,
                    or_(
                        OCRTrainingSample.status == TrainingSampleStatus.PENDING.value,
                        OCRTrainingSample.status == TrainingSampleStatus.ANNOTATED.value,
                        and_(
                            OCRTrainingSample.needs_spot_check == True,
                            OCRTrainingSample.spot_check_passed.is_(None),
                        ),
                    ),
                    OCRTrainingSample.deleted_at.is_(None),
                )
            )
            .order_by(desc(OCRTrainingSample.created_at))
            .limit(limit)
            .offset(offset)
        )
        samples = result.scalars().all()

        items = []
        for sample in samples:
            score = await self._calculate_priority_score(sample, coverage_status)
            items.append(QueueItem(
                sample_id=sample.id,
                document_type=sample.document_type,
                priority=self._score_to_priority(score),
                priority_score=score,
                reason=self._get_priority_reason(sample, coverage_status),
                ocr_text_preview=sample.ground_truth_text[:500] if sample.ground_truth_text else "",
                confidence=sample.auto_acceptance_confidence or 0.0,
                is_spot_check=sample.needs_spot_check and sample.auto_accepted,
                created_at=sample.created_at,
                file_path=sample.file_path,
            ))

        return items

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    async def _calculate_priority_score(
        self,
        sample: OCRTrainingSample,
        coverage_status: Dict[str, float],
    ) -> float:
        """Berechnet Priority-Score für ein Sample (0-100)."""
        score = 0.0

        # 1. Coverage-Gap Score (max 30)
        doc_type = sample.document_type or "unknown"
        coverage = coverage_status.get(doc_type, 1.0)
        if coverage < 0.90:  # Unter 90% Ziel
            gap_score = (0.90 - coverage) * 100  # 0-90 wenn 0% Coverage
            score += min(30, gap_score * self.PRIORITY_WEIGHTS["coverage_gap"] / 30)

        # 2. Stichproben-Review Score (max 25)
        if sample.needs_spot_check and sample.auto_accepted:
            score += self.PRIORITY_WEIGHTS["spot_check"]

        # 3. Dokumenttyp-Priorität (max 20)
        type_priority = self.TYPE_PRIORITY.get(doc_type, 1.0)
        score += type_priority * self.PRIORITY_WEIGHTS["type_priority"] / 1.5

        # 4. Low-Confidence Score (max 15)
        confidence = sample.auto_acceptance_confidence or 1.0
        if confidence < 0.95:
            conf_score = (0.95 - confidence) * 100  # Max wenn 0% Confidence
            score += min(15, conf_score * self.PRIORITY_WEIGHTS["low_confidence"] / 50)

        # 5. Age Score (max 10) - aeltere Samples bevorzugen
        if sample.created_at:
            age_days = (datetime.now(timezone.utc) - sample.created_at).total_seconds() / 86400
            age_score = min(10, age_days * 2)  # 5 Tage = volle Punkte
            score += age_score

        return min(100, score)

    def _score_to_priority(self, score: float) -> VerificationPriority:
        """Konvertiert Score zu Priority-Enum."""
        if score >= 60:
            return VerificationPriority.CRITICAL
        elif score >= 40:
            return VerificationPriority.HIGH
        elif score >= 20:
            return VerificationPriority.MEDIUM
        else:
            return VerificationPriority.LOW

    def _get_priority_reason(
        self,
        sample: OCRTrainingSample,
        coverage_status: Dict[str, float],
    ) -> str:
        """Generiert menschenlesbare Prioritäts-Begruendung."""
        reasons = []

        doc_type = sample.document_type or "unknown"
        coverage = coverage_status.get(doc_type, 1.0)

        if coverage < 0.90:
            reasons.append(f"Coverage-Lücke ({coverage:.0%})")

        if sample.needs_spot_check and sample.auto_accepted:
            reasons.append("Stichproben-Review")

        if sample.auto_acceptance_confidence and sample.auto_acceptance_confidence < 0.95:
            reasons.append(f"Niedrige Confidence ({sample.auto_acceptance_confidence:.0%})")

        if sample.document_type == "invoice":
            reasons.append("Geschäftskritisch (Rechnung)")

        if not reasons:
            reasons.append("Standard-Verifikation")

        return ", ".join(reasons)

    async def _get_coverage_status(self, db: AsyncSession) -> Dict[str, float]:
        """Holt aktuelle Coverage pro Dokumenttyp."""
        result = await db.execute(
            select(BusinessDocumentProfile)
            .where(BusinessDocumentProfile.is_active == True)
        )
        profiles = result.scalars().all()

        coverage_status = {}
        for profile in profiles:
            coverage_status[profile.document_type] = profile.coverage_percentage or 0.0

        return coverage_status

    async def _get_coverage_gaps(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """Holt Dokumenttypen mit Coverage unter Ziel."""
        result = await db.execute(
            select(BusinessDocumentProfile)
            .where(
                and_(
                    BusinessDocumentProfile.is_active == True,
                    BusinessDocumentProfile.coverage_percentage < BusinessDocumentProfile.target_coverage,
                )
            )
        )
        profiles = result.scalars().all()

        gaps = []
        for profile in profiles:
            target_samples = int(
                profile.estimated_daily_volume * profile.target_coverage * 0.1
            )
            gaps.append({
                "document_type": profile.document_type,
                "display_name": profile.display_name,
                "current_coverage": profile.coverage_percentage,
                "target_coverage": profile.target_coverage,
                "samples_needed": max(0, target_samples - profile.verified_sample_count),
            })

        return gaps

    async def _update_profile_stats(self, db: AsyncSession, document_type: str) -> None:
        """Aktualisiert Profile-Statistiken nach Verifikation."""
        from app.services.auto_ground_truth_service import get_auto_ground_truth_service

        service = get_auto_ground_truth_service()
        await service._update_profile_statistics(db, document_type)

    async def _lookup_document_id(
        self,
        db: AsyncSession,
        file_path: Optional[str],
    ) -> Optional[UUID]:
        """
        Sucht document_id anhand des file_path.

        Versucht verschiedene Matching-Strategien:
        1. Exakter Pfad-Match
        2. Endung des Pfades (Dateiname)

        Args:
            db: Datenbank-Session
            file_path: Pfad aus OCRTrainingSample

        Returns:
            UUID des Documents oder None
        """
        if not file_path:
            return None

        # Strategie 1: Exakter Pfad-Match
        result = await db.execute(
            select(Document.id).where(Document.file_path == file_path).limit(1)
        )
        doc_id = result.scalar_one_or_none()
        if doc_id:
            return doc_id

        # Strategie 2: Match über Dateinamen (letzter Teil des Pfades)
        import os
        filename = os.path.basename(file_path)
        if filename:
            result = await db.execute(
                select(Document.id)
                .where(Document.file_path.like(f"%{filename}"))
                .limit(1)
            )
            doc_id = result.scalar_one_or_none()
            if doc_id:
                return doc_id

        # Strategie 3: Match über original_filename
        if filename:
            result = await db.execute(
                select(Document.id)
                .where(Document.original_filename == filename)
                .order_by(desc(Document.created_at))
                .limit(1)
            )
            doc_id = result.scalar_one_or_none()
            if doc_id:
                return doc_id

        logger.debug(
            "document_lookup_failed",
            file_path=file_path,
            message="Kein Document für file_path gefunden",
        )
        return None


# =============================================================================
# Singleton Instance
# =============================================================================

_verification_queue_service: Optional[VerificationQueueService] = None


def get_verification_queue_service() -> VerificationQueueService:
    """Holt oder erstellt Singleton-Instanz des VerificationQueueService."""
    global _verification_queue_service
    if _verification_queue_service is None:
        _verification_queue_service = VerificationQueueService()
    return _verification_queue_service
