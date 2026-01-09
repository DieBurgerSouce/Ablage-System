"""
Coverage Tracking Service

Trackt Fortschritt zur 90% Business-Abdeckung für OCR Training.

Berechnet Coverage pro Dokumenttyp und identifiziert Lücken.
"""

import uuid
from datetime import datetime, timedelta
from app.core.datetime_utils import utc_now
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessDocumentProfile,
    CoverageSnapshot,
    Document,
    OCRTrainingSample,
)

logger = structlog.get_logger(__name__)


class CoverageGap:
    """Repräsentiert eine Coverage-Lücke für einen Dokumenttyp."""

    def __init__(
        self,
        document_type: str,
        display_name: str,
        current_coverage: float,
        target_coverage: float,
        samples_needed: int,
        business_criticality: float,
        priority_score: float
    ):
        self.document_type = document_type
        self.display_name = display_name
        self.current_coverage = current_coverage
        self.target_coverage = target_coverage
        self.samples_needed = samples_needed
        self.business_criticality = business_criticality
        self.priority_score = priority_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "display_name": self.display_name,
            "current_coverage": round(self.current_coverage, 4),
            "target_coverage": self.target_coverage,
            "samples_needed": self.samples_needed,
            "business_criticality": self.business_criticality,
            "priority_score": round(self.priority_score, 4),
            "gap_percentage": round((self.target_coverage - self.current_coverage) * 100, 2)
        }


class CoverageStatus:
    """Gesamtstatus der Training Coverage."""

    def __init__(
        self,
        overall_coverage: float,
        weighted_coverage: float,
        coverage_by_type: Dict[str, Dict[str, Any]],
        total_verified_samples: int,
        total_pending_samples: int,
        auto_accepted_count: int,
        spot_check_pending: int,
        target_reached: bool
    ):
        self.overall_coverage = overall_coverage
        self.weighted_coverage = weighted_coverage
        self.coverage_by_type = coverage_by_type
        self.total_verified_samples = total_verified_samples
        self.total_pending_samples = total_pending_samples
        self.auto_accepted_count = auto_accepted_count
        self.spot_check_pending = spot_check_pending
        self.target_reached = target_reached

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_coverage": round(self.overall_coverage, 4),
            "weighted_coverage": round(self.weighted_coverage, 4),
            "coverage_by_type": self.coverage_by_type,
            "total_verified_samples": self.total_verified_samples,
            "total_pending_samples": self.total_pending_samples,
            "auto_accepted_count": self.auto_accepted_count,
            "spot_check_pending": self.spot_check_pending,
            "target_reached": self.target_reached,
            "target_coverage": 0.90
        }


class CoverageTrend:
    """Trend-Analyse für Coverage über Zeit."""

    def __init__(
        self,
        period_start: datetime,
        period_end: datetime,
        data_points: List[Dict[str, Any]],
        trend_direction: str,  # "improving", "stable", "declining"
        average_daily_improvement: float,
        projected_target_date: Optional[datetime]
    ):
        self.period_start = period_start
        self.period_end = period_end
        self.data_points = data_points
        self.trend_direction = trend_direction
        self.average_daily_improvement = average_daily_improvement
        self.projected_target_date = projected_target_date

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "data_points": self.data_points,
            "trend_direction": self.trend_direction,
            "average_daily_improvement": round(self.average_daily_improvement, 6),
            "projected_target_date": self.projected_target_date.isoformat() if self.projected_target_date else None
        }


class CoverageTrackingService:
    """
    Service für Coverage-Tracking und 90% Business-Abdeckung.

    Berechnet Coverage pro Dokumenttyp basierend auf:
    - Verified Training Samples
    - Geschätztem Daily Volume
    - Business Criticality

    Formel:
    coverage[type] = verified_samples[type] / target_samples[type]
    target_samples[type] = daily_volume[type] * sample_ratio

    sample_ratio ist konfigurierbar (default: 0.10 = 10% der Dokumente)
    """

    # Ziel-Sampling-Rate: 10% der täglichen Dokumente als Training Samples
    DEFAULT_SAMPLE_RATIO = 0.10
    # Ziel-Coverage: 90%
    TARGET_COVERAGE = 0.90

    async def calculate_coverage(
        self,
        db: AsyncSession,
        sample_ratio: float = DEFAULT_SAMPLE_RATIO
    ) -> CoverageStatus:
        """
        Berechnet aktuelle Coverage für alle Dokumenttypen.

        Args:
            db: Database session
            sample_ratio: Anteil der täglichen Dokumente als Target (default 10%)

        Returns:
            CoverageStatus mit Details pro Typ
        """
        # Business Profiles laden
        profiles_result = await db.execute(
            select(BusinessDocumentProfile).where(
                BusinessDocumentProfile.is_active == True
            )
        )
        profiles = {p.document_type: p for p in profiles_result.scalars().all()}

        if not profiles:
            logger.warning("coverage_no_profiles", message="Keine Business Document Profiles gefunden")
            return CoverageStatus(
                overall_coverage=0.0,
                weighted_coverage=0.0,
                coverage_by_type={},
                total_verified_samples=0,
                total_pending_samples=0,
                auto_accepted_count=0,
                spot_check_pending=0,
                target_reached=False
            )

        coverage_by_type: Dict[str, Dict[str, Any]] = {}
        total_weighted_coverage = 0.0
        total_weight = 0.0
        total_verified = 0
        total_pending = 0
        total_auto_accepted = 0
        total_spot_check_pending = 0

        for doc_type, profile in profiles.items():
            # Verified Samples zählen
            verified_result = await db.execute(
                select(func.count(OCRTrainingSample.id)).where(
                    and_(
                        OCRTrainingSample.document_type == doc_type,
                        OCRTrainingSample.status == "verified"
                    )
                )
            )
            verified_count = verified_result.scalar() or 0

            # Pending Samples zählen
            pending_result = await db.execute(
                select(func.count(OCRTrainingSample.id)).where(
                    and_(
                        OCRTrainingSample.document_type == doc_type,
                        OCRTrainingSample.status == "pending"
                    )
                )
            )
            pending_count = pending_result.scalar() or 0

            # Auto-Accepted zählen
            auto_accepted_result = await db.execute(
                select(func.count(OCRTrainingSample.id)).where(
                    and_(
                        OCRTrainingSample.document_type == doc_type,
                        OCRTrainingSample.auto_accepted == True
                    )
                )
            )
            auto_accepted_count = auto_accepted_result.scalar() or 0

            # Spot-Check Pending zählen
            spot_check_result = await db.execute(
                select(func.count(OCRTrainingSample.id)).where(
                    and_(
                        OCRTrainingSample.document_type == doc_type,
                        OCRTrainingSample.needs_spot_check == True,
                        OCRTrainingSample.spot_check_passed.is_(None)
                    )
                )
            )
            spot_check_pending = spot_check_result.scalar() or 0

            # Target Samples berechnen
            target_samples = int(profile.estimated_daily_volume * sample_ratio)
            target_samples = max(target_samples, 1)  # Minimum 1

            # Coverage berechnen
            coverage = min(verified_count / target_samples, 1.0) if target_samples > 0 else 0.0

            # Gewichtete Coverage
            weight = profile.business_criticality * profile.estimated_daily_volume
            total_weighted_coverage += coverage * weight
            total_weight += weight

            coverage_by_type[doc_type] = {
                "display_name": profile.display_name,
                "verified_samples": verified_count,
                "pending_samples": pending_count,
                "auto_accepted": auto_accepted_count,
                "spot_check_pending": spot_check_pending,
                "target_samples": target_samples,
                "coverage": round(coverage, 4),
                "coverage_percent": round(coverage * 100, 2),
                "business_criticality": profile.business_criticality,
                "daily_volume": profile.estimated_daily_volume,
                "samples_needed": max(0, target_samples - verified_count),
                "target_reached": coverage >= self.TARGET_COVERAGE
            }

            total_verified += verified_count
            total_pending += pending_count
            total_auto_accepted += auto_accepted_count
            total_spot_check_pending += spot_check_pending

        # Overall Coverage (einfacher Durchschnitt)
        overall_coverage = sum(
            data["coverage"] for data in coverage_by_type.values()
        ) / len(coverage_by_type) if coverage_by_type else 0.0

        # Weighted Coverage (nach Business Criticality)
        weighted_coverage = total_weighted_coverage / total_weight if total_weight > 0 else 0.0

        # Target erreicht wenn gewichtete Coverage >= 90%
        target_reached = weighted_coverage >= self.TARGET_COVERAGE

        logger.info(
            "coverage_calculated",
            overall_coverage=round(overall_coverage, 4),
            weighted_coverage=round(weighted_coverage, 4),
            total_verified=total_verified,
            target_reached=target_reached
        )

        return CoverageStatus(
            overall_coverage=overall_coverage,
            weighted_coverage=weighted_coverage,
            coverage_by_type=coverage_by_type,
            total_verified_samples=total_verified,
            total_pending_samples=total_pending,
            auto_accepted_count=total_auto_accepted,
            spot_check_pending=total_spot_check_pending,
            target_reached=target_reached
        )

    async def get_coverage_gaps(
        self,
        db: AsyncSession,
        min_gap_threshold: float = 0.05  # Mindestens 5% unter Target
    ) -> List[CoverageGap]:
        """
        Identifiziert Dokumenttypen unter Ziel-Coverage.

        Args:
            db: Database session
            min_gap_threshold: Mindest-Gap für Aufnahme in Liste

        Returns:
            Liste von CoverageGaps, sortiert nach Priority Score
        """
        coverage_status = await self.calculate_coverage(db)
        gaps: List[CoverageGap] = []

        for doc_type, data in coverage_status.coverage_by_type.items():
            current = data["coverage"]
            gap = self.TARGET_COVERAGE - current

            if gap >= min_gap_threshold:
                # Priority Score: Gap * Business Criticality * Daily Volume Weight
                priority_score = gap * data["business_criticality"] * (data["daily_volume"] / 100)

                gaps.append(CoverageGap(
                    document_type=doc_type,
                    display_name=data["display_name"],
                    current_coverage=current,
                    target_coverage=self.TARGET_COVERAGE,
                    samples_needed=data["samples_needed"],
                    business_criticality=data["business_criticality"],
                    priority_score=priority_score
                ))

        # Nach Priority Score sortieren (höchste zuerst)
        gaps.sort(key=lambda g: g.priority_score, reverse=True)

        logger.info(
            "coverage_gaps_identified",
            total_gaps=len(gaps),
            gap_types=[g.document_type for g in gaps]
        )

        return gaps

    async def get_coverage_trend(
        self,
        db: AsyncSession,
        days: int = 30
    ) -> CoverageTrend:
        """
        Analysiert Coverage-Trend über die letzten N Tage.

        Args:
            db: Database session
            days: Anzahl Tage für Analyse

        Returns:
            CoverageTrend mit Datenpunkten und Projektion
        """
        period_end = utc_now()
        period_start = period_end - timedelta(days=days)

        # Historische Snapshots laden
        snapshots_result = await db.execute(
            select(CoverageSnapshot).where(
                CoverageSnapshot.snapshot_date >= period_start.date()
            ).order_by(CoverageSnapshot.snapshot_date)
        )
        snapshots = snapshots_result.scalars().all()

        data_points: List[Dict[str, Any]] = []

        for snapshot in snapshots:
            data_points.append({
                "date": snapshot.snapshot_date.isoformat(),
                "overall_coverage": round(snapshot.overall_coverage, 4),
                "weighted_coverage": round(snapshot.weighted_coverage, 4),
                "total_verified_samples": snapshot.total_verified_samples,
                "auto_accepted_count": snapshot.auto_accepted_count,
                "new_samples_today": snapshot.new_samples_today
            })

        # Trend-Richtung bestimmen
        if len(data_points) < 2:
            trend_direction = "stable"
            avg_improvement = 0.0
        else:
            first_coverage = data_points[0]["weighted_coverage"]
            last_coverage = data_points[-1]["weighted_coverage"]
            change = last_coverage - first_coverage

            if change > 0.02:  # > 2% Verbesserung
                trend_direction = "improving"
            elif change < -0.02:  # > 2% Verschlechterung
                trend_direction = "declining"
            else:
                trend_direction = "stable"

            # Durchschnittliche tägliche Verbesserung
            days_elapsed = max((period_end - period_start).days, 1)
            avg_improvement = change / days_elapsed

        # Projektion: Wann wird 90% erreicht?
        projected_target_date = None
        if avg_improvement > 0 and data_points:
            current_coverage = data_points[-1]["weighted_coverage"]
            gap_to_target = self.TARGET_COVERAGE - current_coverage

            if gap_to_target > 0:
                days_to_target = int(gap_to_target / avg_improvement)
                if days_to_target <= 365:  # Max 1 Jahr projizieren
                    projected_target_date = period_end + timedelta(days=days_to_target)

        logger.info(
            "coverage_trend_analyzed",
            days=days,
            data_points_count=len(data_points),
            trend_direction=trend_direction,
            avg_daily_improvement=round(avg_improvement, 6)
        )

        return CoverageTrend(
            period_start=period_start,
            period_end=period_end,
            data_points=data_points,
            trend_direction=trend_direction,
            average_daily_improvement=avg_improvement,
            projected_target_date=projected_target_date
        )

    async def save_daily_snapshot(
        self,
        db: AsyncSession
    ) -> CoverageSnapshot:
        """
        Speichert täglichen Coverage-Snapshot für Trend-Analyse.

        Args:
            db: Database session

        Returns:
            Erstellter CoverageSnapshot
        """
        today = utc_now().date()

        # Prüfen ob heute schon ein Snapshot existiert
        existing_result = await db.execute(
            select(CoverageSnapshot).where(
                CoverageSnapshot.snapshot_date == today
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            logger.info("coverage_snapshot_exists", date=today.isoformat())
            # Update statt neu erstellen
            coverage_status = await self.calculate_coverage(db)

            existing.overall_coverage = coverage_status.overall_coverage
            existing.weighted_coverage = coverage_status.weighted_coverage
            existing.total_verified_samples = coverage_status.total_verified_samples
            existing.total_pending_samples = coverage_status.total_pending_samples
            existing.auto_accepted_count = coverage_status.auto_accepted_count
            existing.spot_check_pending = coverage_status.spot_check_pending
            existing.coverage_by_type = coverage_status.coverage_by_type

            # Neue Samples heute zählen
            new_today_result = await db.execute(
                select(func.count(OCRTrainingSample.id)).where(
                    and_(
                        func.date(OCRTrainingSample.created_at) == today,
                        OCRTrainingSample.status == "verified"
                    )
                )
            )
            existing.new_samples_today = new_today_result.scalar() or 0

            await db.commit()
            await db.refresh(existing)
            return existing

        # Neuen Snapshot erstellen
        coverage_status = await self.calculate_coverage(db)

        # Neue Samples heute zählen
        new_today_result = await db.execute(
            select(func.count(OCRTrainingSample.id)).where(
                and_(
                    func.date(OCRTrainingSample.created_at) == today,
                    OCRTrainingSample.status == "verified"
                )
            )
        )
        new_samples_today = new_today_result.scalar() or 0

        snapshot = CoverageSnapshot(
            id=uuid.uuid4(),
            snapshot_date=today,
            overall_coverage=coverage_status.overall_coverage,
            weighted_coverage=coverage_status.weighted_coverage,
            total_verified_samples=coverage_status.total_verified_samples,
            total_pending_samples=coverage_status.total_pending_samples,
            auto_accepted_count=coverage_status.auto_accepted_count,
            spot_check_pending=coverage_status.spot_check_pending,
            coverage_by_type=coverage_status.coverage_by_type,
            new_samples_today=new_samples_today
        )

        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)

        logger.info(
            "coverage_snapshot_saved",
            date=today.isoformat(),
            overall_coverage=round(coverage_status.overall_coverage, 4),
            weighted_coverage=round(coverage_status.weighted_coverage, 4),
            new_samples=new_samples_today
        )

        return snapshot

    async def get_retraining_recommendation(
        self,
        db: AsyncSession,
        min_new_samples: int = 50
    ) -> Tuple[bool, List[str]]:
        """
        Prüft ob Surya-Retraining empfohlen wird.

        Kriterien:
        1. Gewichtete Coverage >= 90%
        2. Mindestens min_new_samples neue verified Samples
        3. Keine kritischen Coverage-Lücken

        Args:
            db: Database session
            min_new_samples: Minimum neue Samples seit letztem Training

        Returns:
            Tuple (should_retrain, reasons)
        """
        reasons: List[str] = []
        should_retrain = False

        # Coverage Status prüfen
        coverage = await self.calculate_coverage(db)

        # Coverage-Gaps prüfen
        gaps = await self.get_coverage_gaps(db)
        critical_gaps = [g for g in gaps if g.business_criticality >= 1.3]

        # Neue Samples seit letztem Snapshot zählen
        yesterday = (utc_now() - timedelta(days=1)).date()

        yesterday_snapshot_result = await db.execute(
            select(CoverageSnapshot).where(
                CoverageSnapshot.snapshot_date == yesterday
            )
        )
        yesterday_snapshot = yesterday_snapshot_result.scalar_one_or_none()

        if yesterday_snapshot:
            new_samples = coverage.total_verified_samples - yesterday_snapshot.total_verified_samples
        else:
            # Fallback: Samples der letzten 24h zählen
            new_samples_result = await db.execute(
                select(func.count(OCRTrainingSample.id)).where(
                    and_(
                        OCRTrainingSample.created_at >= utc_now() - timedelta(days=1),
                        OCRTrainingSample.status == "verified"
                    )
                )
            )
            new_samples = new_samples_result.scalar() or 0

        # Entscheidungslogik
        if coverage.weighted_coverage >= self.TARGET_COVERAGE:
            reasons.append(f"90% Coverage erreicht ({coverage.weighted_coverage:.1%})")

            if new_samples >= min_new_samples:
                reasons.append(f"{new_samples} neue verified Samples verfügbar")
                should_retrain = True
            else:
                reasons.append(f"Nur {new_samples}/{min_new_samples} neue Samples (warte auf mehr)")
        else:
            reasons.append(f"Coverage bei {coverage.weighted_coverage:.1%} (Ziel: 90%)")

        if critical_gaps:
            gap_types = [g.document_type for g in critical_gaps]
            reasons.append(f"Kritische Coverage-Lücken: {', '.join(gap_types)}")
            should_retrain = False  # Nicht trainieren bei kritischen Lücken

        logger.info(
            "retraining_recommendation",
            should_retrain=should_retrain,
            weighted_coverage=round(coverage.weighted_coverage, 4),
            new_samples=new_samples,
            reasons=reasons
        )

        return should_retrain, reasons


# Singleton-Instanz
_coverage_tracking_service: Optional[CoverageTrackingService] = None


def get_coverage_tracking_service() -> CoverageTrackingService:
    """Gibt Singleton-Instanz des CoverageTrackingService zurück."""
    global _coverage_tracking_service
    if _coverage_tracking_service is None:
        _coverage_tracking_service = CoverageTrackingService()
    return _coverage_tracking_service
