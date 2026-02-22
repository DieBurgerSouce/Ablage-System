# -*- coding: utf-8 -*-
"""
Enhanced OCR Feedback Service.

Erweitertes OCR-Korrektur-System mit:
- Inline-Korrekturen auf Feld-Ebene
- Korrektur-Queue für niedrig-konfidente Extraktionen
- Gamification: Punkte pro Korrektur, woechentliches Leaderboard
- Batch-Korrektur-Verarbeitung
- Integration mit Self-Learning Pipeline

Phase 6.3: OCR Feedback UX Improvements für Enterprise-Dokumentenmanagement.
Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Praezision.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, func, and_, or_, update, delete, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================


# Punkte-Konfiguration für Gamification
POINTS_CONFIG = {
    # Basis-Punkte pro Korrektur-Typ
    "text_correction": 10,
    "amount_correction": 15,  # Betraege sind wichtiger
    "date_correction": 12,
    "entity_correction": 20,  # Entities sind komplex
    "iban_correction": 25,
    "vat_id_correction": 25,
    "reference_correction": 15,

    # Bonus-Punkte
    "major_correction_bonus": 5,  # Für grosse Korrekturen
    "low_confidence_bonus": 10,  # Korrektur von <60% Konfidenz
    "consecutive_correction_bonus": 2,  # Pro aufeinanderfolgende Korrektur (max 10)
    "quality_verified_bonus": 15,  # Wenn Korrektur verifiziert wird
    "first_of_day_bonus": 5,  # Erste Korrektur des Tages
    "streak_bonus_per_day": 3,  # Pro Tag im Streak

    # Schwellenwerte
    "max_consecutive_bonus": 20,  # Max Bonus für konsekutive Korrekturen
}

# Leaderboard-Konfiguration
LEADERBOARD_CONFIG = {
    "weekly_top_count": 10,  # Top 10 pro Woche
    "monthly_top_count": 20,  # Top 20 pro Monat
    "min_corrections_for_ranking": 5,  # Min 5 Korrekturen für Ranking
}

# Low-Confidence Schwellenwert für Queue
LOW_CONFIDENCE_THRESHOLD = 0.70


# =============================================================================
# ENUMS
# =============================================================================


class CorrectionStatus(str, Enum):
    """Status einer Korrektur."""
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class QueuePriority(str, Enum):
    """Priorität in der Korrektur-Queue."""
    CRITICAL = "critical"  # <40% Konfidenz
    HIGH = "high"  # 40-55% Konfidenz
    MEDIUM = "medium"  # 55-65% Konfidenz
    LOW = "low"  # 65-70% Konfidenz


class LeaderboardPeriod(str, Enum):
    """Zeitraum für Leaderboard."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ALL_TIME = "all_time"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class CorrectionFeedback:
    """Korrektur-Feedback Datenstruktur."""
    document_id: UUID
    field_name: str
    original_value: str
    corrected_value: str
    confidence_before: float
    correction_type: str = "text"  # text, amount, date, entity, iban, vat_id, reference
    user_id: Optional[UUID] = None
    ocr_backend: Optional[str] = None
    page_number: Optional[int] = None
    bounding_box: Optional[Dict[str, float]] = None  # x, y, width, height
    context_text: Optional[str] = None  # Umgebender Text


@dataclass
class CorrectionResult:
    """Ergebnis einer Korrektur-Verarbeitung."""
    correction_id: UUID
    document_id: UUID
    field_name: str
    applied: bool
    points_awarded: int
    bonus_points: int
    total_points: int
    new_user_total: int
    new_streak: int
    achievements_unlocked: List[str]
    feedback_message: str


@dataclass
class QueueItem:
    """Ein Eintrag in der Korrektur-Queue."""
    id: UUID
    document_id: UUID
    document_filename: str
    field_name: str
    ocr_value: str
    confidence: float
    priority: QueuePriority
    ocr_backend: str
    document_type: str
    entity_name: Optional[str]
    created_at: datetime
    page_number: Optional[int] = None
    context_text: Optional[str] = None
    suggested_value: Optional[str] = None  # ML-Vorschlag


@dataclass
class LeaderboardEntry:
    """Ein Eintrag im Leaderboard."""
    rank: int
    user_id: UUID
    username: str
    full_name: Optional[str]
    corrections_count: int
    total_points: int
    accuracy_rate: float  # Anteil verifizierter Korrekturen
    current_streak: int
    longest_streak: int
    achievements: List[str]
    is_current_user: bool = False


@dataclass
class UserStats:
    """Benutzer-Statistiken."""
    user_id: UUID
    total_corrections: int
    total_points: int
    current_streak: int
    longest_streak: int
    weekly_corrections: int
    weekly_points: int
    monthly_corrections: int
    monthly_points: int
    weekly_rank: Optional[int]
    monthly_rank: Optional[int]
    accuracy_rate: float
    achievements: List[str]
    recent_corrections: List[Dict[str, Any]]
    points_breakdown: Dict[str, int]


@dataclass
class BatchCorrectionResult:
    """Ergebnis einer Batch-Korrektur."""
    batch_id: UUID
    total_corrections: int
    applied_count: int
    rejected_count: int
    total_points_awarded: int
    processing_time_ms: int
    errors: List[Dict[str, Any]]


# =============================================================================
# DATABASE MODELS REFERENCE
# =============================================================================
#
# Hinweis: Die folgenden Models sind in app/db/models_ocr_feedback.py definiert.
# Hier nur als Referenz dokumentiert (siehe OCRCorrectionFeedback Model).
#
# Das bestehende Model OCRCorrectionFeedback wird verwendet mit extra_data für:
# - points_base, points_bonus, points_total: Gamification-Punkte
# - page_number, bounding_box, context_text: Positions-Metadaten
# - is_queue_item: True wenn aus Queue
# - bonus_details: Liste der Bonus-Gruende
#
# Für erweiterte Gamification-Statistiken kann UserCorrectionStats hinzugefuegt
# werden (total_corrections, total_points, streaks, achievements).
#


# =============================================================================
# MAIN SERVICE
# =============================================================================


class EnhancedOCRFeedbackService:
    """
    Erweiterter OCR Feedback Service mit Gamification.

    Features:
    - Inline-Korrekturen auf Feld-Ebene
    - Korrektur-Queue für niedrig-konfidente Extraktionen
    - Punkte-System mit Boni
    - Leaderboard (woechentlich/monatlich)
    - Streak-Tracking
    - Achievement-System
    - Batch-Korrektur-Verarbeitung
    - Integration mit Self-Learning Pipeline
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self._db = db

    # =========================================================================
    # CORRECTION SUBMISSION
    # =========================================================================

    async def submit_correction(
        self,
        feedback: CorrectionFeedback,
        company_id: UUID,
    ) -> CorrectionResult:
        """
        Verarbeitet eine einzelne Korrektur.

        Berechnet Punkte, aktualisiert Stats und triggert Learning-Pipeline.

        Args:
            feedback: Korrektur-Feedback
            company_id: Firmen-ID

        Returns:
            CorrectionResult mit Punkten und Status
        """
        from app.db.models_ocr_feedback import OCRCorrectionFeedback, FeedbackStatus
        from app.services.ocr.self_learning_service import (
            CorrectionFeedback as SLCorrectionFeedback,
            get_self_learning_service,
        )

        correction_id = uuid4()
        now = utc_now()

        # 1. Basis-Punkte berechnen
        base_points = self._calculate_base_points(feedback.correction_type)

        # 2. Bonus-Punkte berechnen
        bonus_points, bonus_details = await self._calculate_bonus_points(
            feedback, company_id, now
        )

        total_points = base_points + bonus_points

        # 3. Korrektur speichern
        ocr_feedback = OCRCorrectionFeedback(
            id=correction_id,
            document_id=feedback.document_id,
            company_id=company_id,
            user_id=feedback.user_id,
            backend=feedback.ocr_backend or "unknown",
            field_name=feedback.field_name,
            original_value=feedback.original_value,
            corrected_value=feedback.corrected_value,
            correction_type=feedback.correction_type,
            confidence_before=feedback.confidence_before,
            status=FeedbackStatus.PENDING.value,
            extra_data={
                "points_base": base_points,
                "points_bonus": bonus_points,
                "points_total": total_points,
                "bonus_details": bonus_details,
                "page_number": feedback.page_number,
                "bounding_box": feedback.bounding_box,
                "context_text": feedback.context_text,
            },
        )
        self._db.add(ocr_feedback)

        # 4. User-Stats aktualisieren
        new_user_total, new_streak, achievements = await self._update_user_stats(
            feedback.user_id, company_id, total_points, now
        )

        # 5. Aus Queue entfernen (falls vorhanden)
        await self._remove_from_queue(feedback.document_id, feedback.field_name)

        # 6. Self-Learning Pipeline triggern (async)
        try:
            sl_service = get_self_learning_service(self._db)
            sl_feedback = SLCorrectionFeedback(
                document_id=feedback.document_id,
                field_name=feedback.field_name,
                original_value=feedback.original_value,
                corrected_value=feedback.corrected_value,
                ocr_backend=feedback.ocr_backend or "unknown",
                original_confidence=feedback.confidence_before,
                user_id=feedback.user_id,
                correction_type=feedback.correction_type,
            )
            await sl_service.process_correction(sl_feedback)
        except Exception as e:
            logger.warning(
                "self_learning_trigger_failed",
                correction_id=str(correction_id),
                **safe_error_log(e),
            )

        # 7. Auto-Template Update (wenn Entity bekannt und Bounding Box vorhanden)
        try:
            from app.db.models import Document
            from app.services.ocr.auto_template_service import get_auto_template_service

            doc_result = await self._db.execute(
                select(Document).where(Document.id == feedback.document_id)
            )
            doc = doc_result.scalar_one_or_none()

            if doc and doc.business_entity_id and feedback.bounding_box:
                template_service = get_auto_template_service()
                await template_service.update_template_from_correction(
                    db=self._db,
                    entity_id=doc.business_entity_id,
                    company_id=company_id,
                    field_name=feedback.field_name,
                    corrected_bounding_box=feedback.bounding_box,
                    corrected_value=feedback.corrected_value,
                )
        except Exception as e:
            logger.warning(
                "auto_template_update_failed",
                correction_id=str(correction_id),
                **safe_error_log(e),
            )

        await self._db.flush()

        # Feedback-Nachricht generieren
        feedback_msg = self._generate_feedback_message(
            total_points, bonus_details, achievements
        )

        logger.info(
            "ocr_correction_submitted",
            correction_id=str(correction_id),
            document_id=str(feedback.document_id),
            field_name=feedback.field_name,
            points=total_points,
            new_streak=new_streak,
        )

        return CorrectionResult(
            correction_id=correction_id,
            document_id=feedback.document_id,
            field_name=feedback.field_name,
            applied=True,
            points_awarded=base_points,
            bonus_points=bonus_points,
            total_points=total_points,
            new_user_total=new_user_total,
            new_streak=new_streak,
            achievements_unlocked=achievements,
            feedback_message=feedback_msg,
        )

    async def submit_batch_corrections(
        self,
        corrections: List[CorrectionFeedback],
        company_id: UUID,
        user_id: UUID,
    ) -> BatchCorrectionResult:
        """
        Verarbeitet mehrere Korrekturen als Batch.

        Args:
            corrections: Liste von Korrekturen
            company_id: Firmen-ID
            user_id: Benutzer-ID

        Returns:
            BatchCorrectionResult
        """
        import time
        start_time = time.time()

        batch_id = uuid4()
        applied_count = 0
        rejected_count = 0
        total_points = 0
        errors: List[Dict[str, Any]] = []

        for correction in corrections:
            try:
                # User-ID setzen falls nicht vorhanden
                if not correction.user_id:
                    correction.user_id = user_id

                result = await self.submit_correction(correction, company_id)

                if result.applied:
                    applied_count += 1
                    total_points += result.total_points
                else:
                    rejected_count += 1

            except Exception as e:
                rejected_count += 1
                errors.append({
                    "document_id": str(correction.document_id),
                    "field_name": correction.field_name,
                    "error": safe_error_detail(e, "Batch-Korrektur"),
                })
                logger.warning(
                    "batch_correction_item_failed",
                    document_id=str(correction.document_id),
                    **safe_error_log(e),
                )

        await self._db.commit()

        processing_time = int((time.time() - start_time) * 1000)

        logger.info(
            "batch_corrections_completed",
            batch_id=str(batch_id),
            total=len(corrections),
            applied=applied_count,
            rejected=rejected_count,
            points=total_points,
            time_ms=processing_time,
        )

        return BatchCorrectionResult(
            batch_id=batch_id,
            total_corrections=len(corrections),
            applied_count=applied_count,
            rejected_count=rejected_count,
            total_points_awarded=total_points,
            processing_time_ms=processing_time,
            errors=errors,
        )

    # =========================================================================
    # CORRECTION QUEUE
    # =========================================================================

    async def get_correction_queue(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        priority: Optional[QueuePriority] = None,
        document_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[QueueItem], int]:
        """
        Holt die Korrektur-Queue mit Filterung.

        Args:
            company_id: Firmen-ID
            user_id: Optional - Filter auf zugewiesene Items
            priority: Optional - Filter auf Priorität
            document_type: Optional - Filter auf Dokumenttyp
            limit: Maximale Anzahl
            offset: Offset für Pagination

        Returns:
            Tuple von (Queue-Items, Gesamt-Anzahl)
        """
        from app.db.models import Document
        from app.db.models_ocr_feedback import OCRCorrectionFeedback

        # Subquery für niedrig-konfidente Extraktionen
        # Wir nutzen OCRCorrectionFeedback wo confidence_before < Schwellenwert
        # und noch kein Status "processed" oder "verified"

        # Alternativ: Direkt aus extracted_data mit niedriger Konfidenz
        # Hier vereinfachte Variante über vorhandene Feedbacks

        conditions = [
            OCRCorrectionFeedback.company_id == company_id,
            OCRCorrectionFeedback.confidence_before < LOW_CONFIDENCE_THRESHOLD,
            OCRCorrectionFeedback.status == "pending",
        ]

        if user_id:
            conditions.append(OCRCorrectionFeedback.user_id == user_id)

        # Count Query
        count_stmt = select(func.count(OCRCorrectionFeedback.id)).where(and_(*conditions))
        count_result = await self._db.execute(count_stmt)
        total_count = count_result.scalar() or 0

        # Main Query mit Join auf Document
        stmt = (
            select(OCRCorrectionFeedback, Document)
            .join(Document, Document.id == OCRCorrectionFeedback.document_id)
            .where(and_(*conditions))
            .order_by(OCRCorrectionFeedback.confidence_before.asc())  # Niedrigste zuerst
            .limit(limit)
            .offset(offset)
        )

        result = await self._db.execute(stmt)
        rows = result.all()

        queue_items: List[QueueItem] = []
        for feedback, doc in rows:
            priority_val = self._calculate_priority(feedback.confidence_before)

            queue_items.append(QueueItem(
                id=feedback.id,
                document_id=feedback.document_id,
                document_filename=doc.original_filename,
                field_name=feedback.field_name,
                ocr_value=feedback.original_value,
                confidence=feedback.confidence_before,
                priority=priority_val,
                ocr_backend=feedback.backend,
                document_type=doc.document_type,
                entity_name=doc.business_entity.name if doc.business_entity else None,
                created_at=feedback.created_at,
                page_number=feedback.extra_data.get("page_number") if feedback.extra_data else None,
                context_text=feedback.extra_data.get("context_text") if feedback.extra_data else None,
            ))

        return queue_items, total_count

    async def add_to_queue(
        self,
        document_id: UUID,
        field_name: str,
        ocr_value: str,
        confidence: float,
        company_id: UUID,
        ocr_backend: Optional[str] = None,
        page_number: Optional[int] = None,
        context_text: Optional[str] = None,
        suggested_value: Optional[str] = None,
    ) -> UUID:
        """
        Fuegt eine Extraktion zur Korrektur-Queue hinzu.

        Wird automatisch aufgerufen bei OCR-Ergebnissen unter Schwellenwert.

        Args:
            document_id: Dokument-ID
            field_name: Feldname
            ocr_value: OCR-Wert
            confidence: Konfidenz
            company_id: Firmen-ID
            ocr_backend: OCR-Backend
            page_number: Seitennummer
            context_text: Kontext-Text
            suggested_value: ML-Vorschlag

        Returns:
            Queue-Item ID
        """
        from app.db.models_ocr_feedback import OCRCorrectionFeedback, FeedbackStatus

        # Prüfen ob bereits in Queue
        exists_stmt = select(OCRCorrectionFeedback.id).where(
            and_(
                OCRCorrectionFeedback.document_id == document_id,
                OCRCorrectionFeedback.field_name == field_name,
                OCRCorrectionFeedback.status == FeedbackStatus.PENDING.value,
            )
        )
        exists_result = await self._db.execute(exists_stmt)
        if exists_result.scalar_one_or_none():
            logger.debug(
                "queue_item_already_exists",
                document_id=str(document_id),
                field_name=field_name,
            )
            return exists_result.scalar()  # Existing ID

        item_id = uuid4()
        queue_item = OCRCorrectionFeedback(
            id=item_id,
            document_id=document_id,
            company_id=company_id,
            backend=ocr_backend or "unknown",
            field_name=field_name,
            original_value=ocr_value,
            corrected_value="",  # Noch keine Korrektur
            correction_type="text",
            confidence_before=confidence,
            status=FeedbackStatus.PENDING.value,
            extra_data={
                "is_queue_item": True,
                "page_number": page_number,
                "context_text": context_text,
                "suggested_value": suggested_value,
            },
        )
        self._db.add(queue_item)
        await self._db.flush()

        logger.info(
            "added_to_correction_queue",
            item_id=str(item_id),
            document_id=str(document_id),
            field_name=field_name,
            confidence=confidence,
        )

        return item_id

    async def claim_queue_item(
        self,
        item_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> bool:
        """
        Reserviert ein Queue-Item für einen Benutzer.

        Args:
            item_id: Queue-Item ID
            user_id: Benutzer-ID
            company_id: Firmen-ID

        Returns:
            True bei Erfolg
        """
        from app.db.models_ocr_feedback import OCRCorrectionFeedback, FeedbackStatus

        stmt = (
            update(OCRCorrectionFeedback)
            .where(
                and_(
                    OCRCorrectionFeedback.id == item_id,
                    OCRCorrectionFeedback.company_id == company_id,
                    OCRCorrectionFeedback.status == FeedbackStatus.PENDING.value,
                    OCRCorrectionFeedback.user_id.is_(None),  # Noch nicht zugewiesen
                )
            )
            .values(
                user_id=user_id,
                updated_at=utc_now(),
            )
        )

        result = await self._db.execute(stmt)
        return result.rowcount > 0

    # =========================================================================
    # LEADERBOARD
    # =========================================================================

    async def get_leaderboard(
        self,
        company_id: UUID,
        period: LeaderboardPeriod = LeaderboardPeriod.WEEKLY,
        current_user_id: Optional[UUID] = None,
        limit: int = 10,
    ) -> List[LeaderboardEntry]:
        """
        Holt das Leaderboard für einen Zeitraum.

        Args:
            company_id: Firmen-ID
            period: Zeitraum (weekly/monthly/all_time)
            current_user_id: Optionale aktuelle User-ID für Markierung
            limit: Maximale Anzahl

        Returns:
            Liste von LeaderboardEntry
        """
        from app.db.models import User
        from app.db.models_ocr_feedback import OCRCorrectionFeedback, FeedbackStatus

        # Zeitraum bestimmen
        now = utc_now()
        if period == LeaderboardPeriod.WEEKLY:
            start_date = now - timedelta(days=7)
        elif period == LeaderboardPeriod.MONTHLY:
            start_date = now - timedelta(days=30)
        else:  # ALL_TIME
            start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)

        # Aggregation Query
        stmt = (
            select(
                OCRCorrectionFeedback.user_id,
                User.username,
                User.full_name,
                func.count(OCRCorrectionFeedback.id).label("corrections_count"),
                func.sum(
                    case(
                        (OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer),
                         OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer)),
                        else_=10  # Default
                    )
                ).label("total_points"),
                func.count(
                    case((OCRCorrectionFeedback.status == FeedbackStatus.VERIFIED.value, 1))
                ).label("verified_count"),
            )
            .join(User, User.id == OCRCorrectionFeedback.user_id)
            .where(
                and_(
                    OCRCorrectionFeedback.company_id == company_id,
                    OCRCorrectionFeedback.user_id.isnot(None),
                    OCRCorrectionFeedback.created_at >= start_date,
                    OCRCorrectionFeedback.status.in_([
                        FeedbackStatus.PENDING.value,
                        FeedbackStatus.PROCESSED.value,
                        FeedbackStatus.VERIFIED.value,
                    ]),
                )
            )
            .group_by(OCRCorrectionFeedback.user_id, User.username, User.full_name)
            .having(func.count(OCRCorrectionFeedback.id) >= LEADERBOARD_CONFIG["min_corrections_for_ranking"])
            .order_by(func.sum(
                case(
                    (OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer),
                     OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer)),
                    else_=10
                )
            ).desc())
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        rows = result.all()

        leaderboard: List[LeaderboardEntry] = []
        for idx, row in enumerate(rows, start=1):
            accuracy = (row.verified_count / row.corrections_count) if row.corrections_count > 0 else 0.0

            # Streak und Achievements laden (vereinfacht)
            streak_data = await self._get_user_streak(row.user_id)

            leaderboard.append(LeaderboardEntry(
                rank=idx,
                user_id=row.user_id,
                username=row.username,
                full_name=row.full_name,
                corrections_count=row.corrections_count,
                total_points=row.total_points or 0,
                accuracy_rate=accuracy,
                current_streak=streak_data.get("current", 0),
                longest_streak=streak_data.get("longest", 0),
                achievements=streak_data.get("achievements", []),
                is_current_user=(row.user_id == current_user_id),
            ))

        return leaderboard

    async def get_user_stats(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> UserStats:
        """
        Holt die Statistiken eines Benutzers.

        Args:
            user_id: Benutzer-ID
            company_id: Firmen-ID

        Returns:
            UserStats
        """
        from app.db.models_ocr_feedback import OCRCorrectionFeedback, FeedbackStatus

        now = utc_now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # Gesamt-Statistiken
        total_stmt = select(
            func.count(OCRCorrectionFeedback.id).label("total"),
            func.sum(
                case(
                    (OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer),
                     OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer)),
                    else_=10
                )
            ).label("points"),
            func.count(
                case((OCRCorrectionFeedback.status == FeedbackStatus.VERIFIED.value, 1))
            ).label("verified"),
            func.count(
                case((OCRCorrectionFeedback.status == FeedbackStatus.REJECTED.value, 1))
            ).label("rejected"),
        ).where(
            and_(
                OCRCorrectionFeedback.user_id == user_id,
                OCRCorrectionFeedback.company_id == company_id,
            )
        )
        total_result = await self._db.execute(total_stmt)
        total_row = total_result.one()

        # Woechentliche Statistiken
        weekly_stmt = select(
            func.count(OCRCorrectionFeedback.id).label("count"),
            func.sum(
                case(
                    (OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer),
                     OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer)),
                    else_=10
                )
            ).label("points"),
        ).where(
            and_(
                OCRCorrectionFeedback.user_id == user_id,
                OCRCorrectionFeedback.company_id == company_id,
                OCRCorrectionFeedback.created_at >= week_ago,
            )
        )
        weekly_result = await self._db.execute(weekly_stmt)
        weekly_row = weekly_result.one()

        # Monatliche Statistiken
        monthly_stmt = select(
            func.count(OCRCorrectionFeedback.id).label("count"),
            func.sum(
                case(
                    (OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer),
                     OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer)),
                    else_=10
                )
            ).label("points"),
        ).where(
            and_(
                OCRCorrectionFeedback.user_id == user_id,
                OCRCorrectionFeedback.company_id == company_id,
                OCRCorrectionFeedback.created_at >= month_ago,
            )
        )
        monthly_result = await self._db.execute(monthly_stmt)
        monthly_row = monthly_result.one()

        # Streak und Achievements
        streak_data = await self._get_user_streak(user_id)

        # Ranks berechnen
        weekly_rank = await self._get_user_rank(user_id, company_id, LeaderboardPeriod.WEEKLY)
        monthly_rank = await self._get_user_rank(user_id, company_id, LeaderboardPeriod.MONTHLY)

        # Letzte Korrekturen
        recent_stmt = (
            select(OCRCorrectionFeedback)
            .where(
                and_(
                    OCRCorrectionFeedback.user_id == user_id,
                    OCRCorrectionFeedback.company_id == company_id,
                )
            )
            .order_by(OCRCorrectionFeedback.created_at.desc())
            .limit(10)
        )
        recent_result = await self._db.execute(recent_stmt)
        recent_corrections = [
            {
                "id": str(c.id),
                "field_name": c.field_name,
                "points": c.extra_data.get("points_total", 10) if c.extra_data else 10,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_result.scalars().all()
        ]

        # Punkte-Aufschluesselung
        points_breakdown = await self._get_points_breakdown(user_id, company_id)

        accuracy = (total_row.verified / total_row.total) if total_row.total > 0 else 0.0

        return UserStats(
            user_id=user_id,
            total_corrections=total_row.total or 0,
            total_points=total_row.points or 0,
            current_streak=streak_data.get("current", 0),
            longest_streak=streak_data.get("longest", 0),
            weekly_corrections=weekly_row.count or 0,
            weekly_points=weekly_row.points or 0,
            monthly_corrections=monthly_row.count or 0,
            monthly_points=monthly_row.points or 0,
            weekly_rank=weekly_rank,
            monthly_rank=monthly_rank,
            accuracy_rate=accuracy,
            achievements=streak_data.get("achievements", []),
            recent_corrections=recent_corrections,
            points_breakdown=points_breakdown,
        )

    # =========================================================================
    # INSTANT FEEDBACK PATH
    # =========================================================================

    async def _try_instant_feedback(
        self,
        db: AsyncSession,
        field_name: str,
        original_value: str,
        corrected_value: str,
        ocr_backend: str,
        entity_id: Optional[UUID] = None,
    ) -> bool:
        """
        Schnelle Feedback-Verarbeitung für kleine Korrekturen.

        Überspringt die Batch-Queue wenn edit_distance <= 2.
        """
        # Calculate edit distance
        if len(original_value) == 0 or len(corrected_value) == 0:
            return False

        distance = self._simple_edit_distance(original_value, corrected_value)
        if distance > 2:
            return False

        # Import here to avoid circular dependency
        from app.services.ocr.self_learning_service import (
            SelfLearningOCRService,
            CorrectionFeedback as SLCorrectionFeedback,
        )

        feedback = SLCorrectionFeedback(
            document_id=uuid4(),  # placeholder
            field_name=field_name,
            original_value=original_value,
            corrected_value=corrected_value,
            ocr_backend=ocr_backend,
            original_confidence=0.8,
        )

        learning_service = SelfLearningOCRService(db)
        return await learning_service.apply_immediate_correction(
            db, feedback, entity_id
        )

    @staticmethod
    def _simple_edit_distance(s1: str, s2: str) -> int:
        """Einfache Levenshtein-Distanz Berechnung."""
        if len(s1) < len(s2):
            return EnhancedOCRFeedbackService._simple_edit_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                curr_row.append(min(
                    prev_row[j + 1] + 1,
                    curr_row[j] + 1,
                    prev_row[j] + (c1 != c2),
                ))
            prev_row = curr_row
        return prev_row[-1]

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calculate_base_points(self, correction_type: str) -> int:
        """Berechnet Basis-Punkte basierend auf Korrektur-Typ."""
        key = f"{correction_type}_correction"
        return POINTS_CONFIG.get(key, POINTS_CONFIG["text_correction"])

    async def _calculate_bonus_points(
        self,
        feedback: CorrectionFeedback,
        company_id: UUID,
        now: datetime,
    ) -> Tuple[int, List[str]]:
        """Berechnet Bonus-Punkte und gibt Details zurück."""
        bonus = 0
        details: List[str] = []

        # 1. Major Correction Bonus
        if self._is_major_correction(feedback.original_value, feedback.corrected_value):
            bonus += POINTS_CONFIG["major_correction_bonus"]
            details.append("Grosse Korrektur")

        # 2. Low Confidence Bonus
        if feedback.confidence_before < 0.60:
            bonus += POINTS_CONFIG["low_confidence_bonus"]
            details.append("Niedrige Konfidenz korrigiert")

        # 3. Consecutive Correction Bonus
        consecutive = await self._get_consecutive_corrections(feedback.user_id, now)
        if consecutive > 0:
            consecutive_bonus = min(
                consecutive * POINTS_CONFIG["consecutive_correction_bonus"],
                POINTS_CONFIG["max_consecutive_bonus"]
            )
            bonus += consecutive_bonus
            details.append(f"{consecutive}x Korrektur-Combo")

        # 4. First of Day Bonus
        if await self._is_first_of_day(feedback.user_id, now):
            bonus += POINTS_CONFIG["first_of_day_bonus"]
            details.append("Erste Korrektur heute")

        # 5. Streak Bonus
        streak = await self._get_current_streak(feedback.user_id)
        if streak > 1:
            streak_bonus = streak * POINTS_CONFIG["streak_bonus_per_day"]
            bonus += streak_bonus
            details.append(f"{streak}-Tage-Streak")

        return bonus, details

    def _is_major_correction(self, original: str, corrected: str) -> bool:
        """Prüft ob es eine grosse Korrektur ist."""
        if not original or not corrected:
            return True
        len_diff = abs(len(original) - len(corrected))
        max_len = max(len(original), len(corrected), 1)
        return (len_diff / max_len) > 0.3

    async def _get_consecutive_corrections(
        self,
        user_id: Optional[UUID],
        now: datetime,
    ) -> int:
        """Holt Anzahl aufeinanderfolgender Korrekturen in den letzten 10 Minuten."""
        if not user_id:
            return 0

        from app.db.models_ocr_feedback import OCRCorrectionFeedback

        ten_min_ago = now - timedelta(minutes=10)
        stmt = select(func.count(OCRCorrectionFeedback.id)).where(
            and_(
                OCRCorrectionFeedback.user_id == user_id,
                OCRCorrectionFeedback.created_at >= ten_min_ago,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def _is_first_of_day(
        self,
        user_id: Optional[UUID],
        now: datetime,
    ) -> bool:
        """Prüft ob es die erste Korrektur des Tages ist."""
        if not user_id:
            return False

        from app.db.models_ocr_feedback import OCRCorrectionFeedback

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(OCRCorrectionFeedback.id)).where(
            and_(
                OCRCorrectionFeedback.user_id == user_id,
                OCRCorrectionFeedback.created_at >= today_start,
            )
        )
        result = await self._db.execute(stmt)
        count = result.scalar() or 0
        return count == 0  # Erste wenn noch keine

    async def _get_current_streak(self, user_id: Optional[UUID]) -> int:
        """Holt aktuellen Streak (Tage in Folge mit Korrekturen)."""
        if not user_id:
            return 0

        from app.db.models_ocr_feedback import OCRCorrectionFeedback

        # Letzte 30 Tage mit Korrekturen
        today = date.today()
        streak = 0

        for i in range(30):
            check_date = today - timedelta(days=i)
            stmt = select(func.count(OCRCorrectionFeedback.id)).where(
                and_(
                    OCRCorrectionFeedback.user_id == user_id,
                    func.date(OCRCorrectionFeedback.created_at) == check_date,
                )
            )
            result = await self._db.execute(stmt)
            count = result.scalar() or 0

            if count > 0:
                streak += 1
            elif i > 0:  # Erster Tag ohne Korrektur nach Streak
                break

        return streak

    async def _update_user_stats(
        self,
        user_id: Optional[UUID],
        company_id: UUID,
        points: int,
        now: datetime,
    ) -> Tuple[int, int, List[str]]:
        """Aktualisiert User-Stats und gibt neue Totals zurück."""
        if not user_id:
            return 0, 0, []

        # Vereinfachte Implementation ohne separate Stats-Tabelle
        # In Produktion: UserCorrectionStats Tabelle verwenden

        from app.db.models_ocr_feedback import OCRCorrectionFeedback

        # Total berechnen
        total_stmt = select(func.sum(
            case(
                (OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer),
                 OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer)),
                else_=10
            )
        )).where(OCRCorrectionFeedback.user_id == user_id)
        total_result = await self._db.execute(total_stmt)
        new_total = (total_result.scalar() or 0) + points

        # Streak
        streak = await self._get_current_streak(user_id)

        # Achievements prüfen
        achievements = await self._check_achievements(user_id, company_id, new_total, streak)

        return new_total, streak, achievements

    async def _check_achievements(
        self,
        user_id: UUID,
        company_id: UUID,
        total_points: int,
        streak: int,
    ) -> List[str]:
        """Prüft und vergibt Achievements."""
        new_achievements: List[str] = []

        # Achievement-Definitionen
        ACHIEVEMENTS = {
            "first_correction": {"threshold": 1, "type": "corrections"},
            "correction_10": {"threshold": 10, "type": "corrections"},
            "correction_50": {"threshold": 50, "type": "corrections"},
            "correction_100": {"threshold": 100, "type": "corrections"},
            "points_100": {"threshold": 100, "type": "points"},
            "points_500": {"threshold": 500, "type": "points"},
            "points_1000": {"threshold": 1000, "type": "points"},
            "streak_3": {"threshold": 3, "type": "streak"},
            "streak_7": {"threshold": 7, "type": "streak"},
            "streak_30": {"threshold": 30, "type": "streak"},
        }

        from app.db.models_ocr_feedback import OCRCorrectionFeedback

        # Anzahl Korrekturen
        count_stmt = select(func.count(OCRCorrectionFeedback.id)).where(
            OCRCorrectionFeedback.user_id == user_id
        )
        count_result = await self._db.execute(count_stmt)
        total_corrections = count_result.scalar() or 0

        # Vorhandene Achievements laden (aus extra_data des letzten Eintrags)
        # In Produktion: UserCorrectionStats.achievements
        existing: Set[str] = set()

        for name, config in ACHIEVEMENTS.items():
            if name in existing:
                continue

            threshold = config["threshold"]
            ach_type = config["type"]

            if ach_type == "corrections" and total_corrections >= threshold:
                new_achievements.append(name)
            elif ach_type == "points" and total_points >= threshold:
                new_achievements.append(name)
            elif ach_type == "streak" and streak >= threshold:
                new_achievements.append(name)

        return new_achievements

    async def _remove_from_queue(
        self,
        document_id: UUID,
        field_name: str,
    ) -> None:
        """Entfernt ein Item aus der Queue nach Korrektur."""
        # In dieser Implementation sind Queue-Items dieselben wie Feedbacks
        # mit Status "pending" und is_queue_item=True
        # Nach Korrektur werden sie zu normalen Feedbacks
        pass

    def _calculate_priority(self, confidence: float) -> QueuePriority:
        """Berechnet Priorität basierend auf Konfidenz."""
        if confidence < 0.40:
            return QueuePriority.CRITICAL
        elif confidence < 0.55:
            return QueuePriority.HIGH
        elif confidence < 0.65:
            return QueuePriority.MEDIUM
        else:
            return QueuePriority.LOW

    async def _get_user_streak(self, user_id: UUID) -> Dict[str, Any]:
        """Holt Streak-Daten für einen User."""
        current = await self._get_current_streak(user_id)
        # Longest Streak: In Produktion aus Stats-Tabelle
        # Hier vereinfacht: current = longest wenn aktiv
        return {
            "current": current,
            "longest": max(current, 0),
            "achievements": [],  # In Produktion aus Stats
        }

    async def _get_user_rank(
        self,
        user_id: UUID,
        company_id: UUID,
        period: LeaderboardPeriod,
    ) -> Optional[int]:
        """Berechnet den Rang eines Users im Leaderboard."""
        leaderboard = await self.get_leaderboard(
            company_id, period, current_user_id=user_id, limit=100
        )
        for entry in leaderboard:
            if entry.user_id == user_id:
                return entry.rank
        return None

    async def _get_points_breakdown(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> Dict[str, int]:
        """Holt Punkte-Aufschluesselung nach Korrektur-Typ."""
        from app.db.models_ocr_feedback import OCRCorrectionFeedback

        stmt = (
            select(
                OCRCorrectionFeedback.correction_type,
                func.count(OCRCorrectionFeedback.id).label("count"),
                func.sum(
                    case(
                        (OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer),
                         OCRCorrectionFeedback.extra_data["points_total"].astext.cast(Integer)),
                        else_=10
                    )
                ).label("points"),
            )
            .where(
                and_(
                    OCRCorrectionFeedback.user_id == user_id,
                    OCRCorrectionFeedback.company_id == company_id,
                )
            )
            .group_by(OCRCorrectionFeedback.correction_type)
        )

        result = await self._db.execute(stmt)
        return {row.correction_type: row.points or 0 for row in result.all()}

    def _generate_feedback_message(
        self,
        total_points: int,
        bonus_details: List[str],
        achievements: List[str],
    ) -> str:
        """Generiert eine Feedback-Nachricht für den User."""
        msg_parts = [f"+{total_points} Punkte"]

        if bonus_details:
            msg_parts.append(f"({', '.join(bonus_details)})")

        if achievements:
            achievement_labels = {
                "first_correction": "Erste Korrektur!",
                "correction_10": "10 Korrekturen!",
                "correction_50": "50 Korrekturen!",
                "correction_100": "Korrektur-Meister!",
                "points_100": "100 Punkte erreicht!",
                "points_500": "Punkte-Sammler!",
                "points_1000": "Punkte-Champion!",
                "streak_3": "3-Tage-Streak!",
                "streak_7": "Wochen-Streak!",
                "streak_30": "Monats-Champion!",
            }
            for ach in achievements:
                label = achievement_labels.get(ach, ach)
                msg_parts.append(f"Neues Achievement: {label}")

        return " ".join(msg_parts)


# =============================================================================
# SERVICE FACTORY
# =============================================================================


def get_feedback_service(db: AsyncSession) -> EnhancedOCRFeedbackService:
    """
    Factory-Funktion für den Enhanced Feedback Service.

    Args:
        db: Datenbank-Session

    Returns:
        EnhancedOCRFeedbackService Instance
    """
    return EnhancedOCRFeedbackService(db)
