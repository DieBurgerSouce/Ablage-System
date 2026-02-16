"""
Analytics Team Stats API Endpoint

Leichtgewichtiger Endpoint für Team-Produktivitaets-Daten.
Aggregiert Document + AuditLog Tabellen pro Benutzer.
"""

from datetime import date, datetime, timezone, timedelta
from typing import Dict, List, Literal, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, AuditLog, User
from app.api.dependencies import get_db, get_current_active_user, get_current_company_id
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _get_period_start(period: str) -> datetime:
    """Berechnet den Startpunkt für den angegebenen Zeitraum."""
    now = datetime.now(timezone.utc)
    if period == "day":
        return now - timedelta(days=1)
    elif period == "week":
        return now - timedelta(weeks=1)
    elif period == "quarter":
        return now - timedelta(days=90)
    else:  # month (default)
        return now - timedelta(days=30)


@router.get(
    "/team-stats",
    summary="Team-Produktivitaets-Statistiken",
    description="Aggregierte Produktivitaetsdaten pro Benutzer für den angegebenen Zeitraum",
)
async def get_team_stats(
    period: Literal["day", "week", "month", "quarter"] = Query(
        "month",
        description="Zeitraum: day, week, month oder quarter",
    ),
    start_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Starttermin (YYYY-MM-DD). Überschreibt period.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Endtermin (YYYY-MM-DD). Überschreibt period.",
    ),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Holt Team-Produktivitaets-Statistiken.

    **Enthält pro Benutzer:**
    - documents_processed: Anzahl verarbeiteter Dokumente
    - avg_approval_time_hours: Durchschnittliche Freigabe-Dauer
    - ocr_corrections: Anzahl OCR-Korrekturen
    - quality_score: Qualitaets-Score (0-100)

    **Rollen:** Alle authentifizierten Benutzer (company-level)
    """
    logger.info(
        "analytics.get_team_stats",
        user_id=str(current_user.id),
        company_id=str(company_id),
        period=period,
    )

    if start_date and end_date:
        period_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        period_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    else:
        period_start = _get_period_start(period)
        period_end = datetime.now(timezone.utc)

    try:
        # Documents processed per user
        doc_result = await db.execute(
            select(
                Document.owner_id.label("user_id"),
                func.count(Document.id).label("documents_processed"),
                func.avg(Document.processing_duration_ms).label("avg_processing_ms"),
                func.avg(Document.ocr_confidence).label("avg_confidence"),
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                    Document.deleted_at.is_(None),
                )
            )
            .group_by(Document.owner_id)
        )
        doc_rows = doc_result.all()

        # OCR corrections per user (audit log entries with action containing 'ocr_correction')
        correction_result = await db.execute(
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("ocr_corrections"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.created_at <= period_end,
                    AuditLog.action.ilike("%ocr_correct%"),
                )
            )
            .group_by(AuditLog.user_id)
        )
        correction_rows = {
            str(row.user_id): row.ocr_corrections
            for row in correction_result.all()
        }

        # Approval actions per user (for avg approval time)
        approval_result = await db.execute(
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("approval_count"),
            )
            .where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= period_start,
                    AuditLog.created_at <= period_end,
                    AuditLog.action.ilike("%approv%"),
                    AuditLog.success.is_(True),
                )
            )
            .group_by(AuditLog.user_id)
        )
        approval_rows = {
            str(row.user_id): row.approval_count
            for row in approval_result.all()
        }

        # Get usernames
        user_ids = [row.user_id for row in doc_rows if row.user_id is not None]
        user_map: Dict[str, str] = {}
        if user_ids:
            user_result = await db.execute(
                select(User.id, User.username).where(User.id.in_(user_ids))
            )
            user_map = {
                str(row.id): row.username for row in user_result.all()
            }

        # Build response
        user_stats: List[Dict] = []
        total_documents = 0

        for row in doc_rows:
            if row.user_id is None:
                continue

            uid = str(row.user_id)
            doc_count = row.documents_processed or 0
            total_documents += doc_count
            avg_confidence = float(row.avg_confidence or 0)
            corrections = correction_rows.get(uid, 0)
            approvals = approval_rows.get(uid, 0)

            # Quality score: based on OCR confidence and correction ratio
            correction_ratio = corrections / max(doc_count, 1)
            quality_score = round(
                min(100, max(0, avg_confidence * 100 - correction_ratio * 10)),
                1,
            )

            # Estimate avg approval time (simplified: approvals / hours in period)
            period_hours = (datetime.now(timezone.utc) - period_start).total_seconds() / 3600
            avg_approval_hours = round(
                period_hours / max(approvals, 1), 1
            ) if approvals > 0 else 0

            user_stats.append({
                "user_id": uid,
                "username": user_map.get(uid, "Unbekannt"),
                "documents_processed": doc_count,
                "avg_approval_time_hours": avg_approval_hours,
                "ocr_corrections": corrections,
                "quality_score": quality_score,
            })

        # Sort by documents_processed descending
        user_stats.sort(key=lambda x: x["documents_processed"], reverse=True)

        return {
            "user_stats": user_stats,
            "period": period,
            "total_documents": total_documents,
        }

    except Exception as e:
        logger.error(
            "analytics.team_stats_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Team-Statistiken",
        )


@router.get(
    "/team-workload",
    summary="Team-Workload-Heatmap",
    description="Dokumentenverteilung nach Wochentag und Stunde für Heatmap-Visualisierung",
)
async def get_team_workload(
    period: Literal["day", "week", "month", "quarter"] = Query(
        "month",
        description="Zeitraum: day, week, month oder quarter",
    ),
    start_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Starttermin (YYYY-MM-DD). Überschreibt period.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="Benutzerdefinierter Endtermin (YYYY-MM-DD). Überschreibt period.",
    ),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Holt Workload-Verteilung nach Wochentag (0=Mo..6=So) und Stunde (0-23).

    Ergebnis wird für Heatmap-Darstellung im Team-Tab verwendet.
    """
    logger.info(
        "analytics.get_team_workload",
        user_id=str(current_user.id),
        company_id=str(company_id),
        period=period,
    )

    if start_date and end_date:
        period_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        period_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    else:
        period_start = _get_period_start(period)
        period_end = datetime.now(timezone.utc)

    try:
        result = await db.execute(
            select(
                Document.owner_id.label("user_id"),
                func.extract("dow", Document.created_at).label("day_of_week_raw"),
                func.extract("hour", Document.created_at).label("hour"),
                func.count(Document.id).label("count"),
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                    Document.deleted_at.is_(None),
                )
            )
            .group_by(
                Document.owner_id,
                func.extract("dow", Document.created_at),
                func.extract("hour", Document.created_at),
            )
        )
        raw_rows = result.all()

        # Get usernames for all user_ids
        user_ids = list({row.user_id for row in raw_rows if row.user_id is not None})
        user_map: Dict[str, str] = {}
        if user_ids:
            user_result = await db.execute(
                select(User.id, User.username).where(User.id.in_(user_ids))
            )
            user_map = {str(row.id): row.username for row in user_result.all()}

        # PostgreSQL EXTRACT(dow) returns 0=Sunday..6=Saturday
        # Convert to ISO: 0=Monday..6=Sunday
        def pg_dow_to_iso(pg_dow: int) -> int:
            return (pg_dow - 1) % 7 if pg_dow > 0 else 6

        rows: List[Dict] = []
        for row in raw_rows:
            if row.user_id is None:
                continue
            uid = str(row.user_id)
            rows.append({
                "user_id": uid,
                "username": user_map.get(uid, "Unbekannt"),
                "day_of_week": pg_dow_to_iso(int(row.day_of_week_raw)),
                "hour": int(row.hour),
                "count": row.count,
            })

        return {"rows": rows}

    except Exception as e:
        logger.error(
            "analytics.team_workload_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Workload-Daten",
        )
