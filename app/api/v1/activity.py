"""
Activity API Endpoints.

Enterprise-level Activity-Tracking fuer Dokumente:
- Aktivitaetsverlauf eines Dokuments abrufen
- Aktivitaeten nach Typ filtern
- Paginierung fuer grosse Historien

Feinpoliert und durchdacht - Vollstaendige Audit-Trail auf Enterprise-Niveau.
"""

import structlog
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.db.models import (
    User,
    Document,
    DocumentActivity,
    ActivityType,
)
from app.api.dependencies import get_current_user, get_db
from app.db.schemas import (
    ActivityResponse,
    ActivitiesListResponse,
    ActivityTypeEnum,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["activity"])


def _build_activity_response(activity: DocumentActivity, user: Optional[User]) -> ActivityResponse:
    """Erstellt ActivityResponse aus DB-Modell."""
    return ActivityResponse(
        id=str(activity.id),
        documentId=str(activity.document_id),
        userId=str(activity.user_id) if activity.user_id else "",
        userName=user.full_name or user.username or user.email if user else "System",
        userAvatar=None,
        type=activity.activity_type,
        description=activity.description,
        metadata=activity.activity_metadata,
        createdAt=activity.created_at.isoformat() if activity.created_at else "",
    )


@router.get(
    "/{document_id}/activity",
    response_model=ActivitiesListResponse,
    summary="Aktivitaetsverlauf",
    description="Gibt den Aktivitaetsverlauf eines Dokuments zurueck."
)
async def list_activities(
    document_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    activity_type: Optional[ActivityTypeEnum] = Query(None, description="Nach Typ filtern"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivitiesListResponse:
    """Aktivitaetsverlauf eines Dokuments."""
    # Pruefe ob Dokument existiert
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    # Base filter
    base_filter = DocumentActivity.document_id == document_id
    if activity_type:
        base_filter = and_(base_filter, DocumentActivity.activity_type == activity_type.value)

    # Total count
    count_result = await db.execute(
        select(func.count(DocumentActivity.id)).where(base_filter)
    )
    total = count_result.scalar() or 0

    # Query Activities
    query = (
        select(DocumentActivity)
        .where(base_filter)
        .order_by(DocumentActivity.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    activities_db = result.scalars().all()

    # Lade User-Objekte
    activities = []
    for activity in activities_db:
        user = None
        if activity.user_id:
            user_result = await db.execute(
                select(User).where(User.id == activity.user_id)
            )
            user = user_result.scalar_one_or_none()

        activities.append(_build_activity_response(activity, user))

    return ActivitiesListResponse(
        activities=activities,
        total=total,
        hasMore=(offset + limit) < total,
    )


@router.post(
    "/{document_id}/activity/view",
    status_code=status.HTTP_201_CREATED,
    summary="View-Aktivitaet loggen",
    description="Loggt eine View-Aktivitaet fuer ein Dokument."
)
async def log_view_activity(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Loggt View-Aktivitaet."""
    # Pruefe ob Dokument existiert
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    activity = DocumentActivity(
        document_id=document_id,
        user_id=current_user.id,
        activity_type=ActivityType.DOCUMENT_VIEWED.value,
        description="Dokument angesehen",
        metadata={},
    )

    db.add(activity)
    await db.commit()

    logger.info(
        "activity_logged",
        activity_type="document_viewed",
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    return {"success": True, "activity_id": str(activity.id)}


@router.post(
    "/{document_id}/activity/download",
    status_code=status.HTTP_201_CREATED,
    summary="Download-Aktivitaet loggen",
    description="Loggt eine Download-Aktivitaet fuer ein Dokument."
)
async def log_download_activity(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Loggt Download-Aktivitaet."""
    # Pruefe ob Dokument existiert
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    activity = DocumentActivity(
        document_id=document_id,
        user_id=current_user.id,
        activity_type=ActivityType.DOCUMENT_DOWNLOADED.value,
        description="Dokument heruntergeladen",
        metadata={},
    )

    db.add(activity)
    await db.commit()

    logger.info(
        "activity_logged",
        activity_type="document_downloaded",
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    return {"success": True, "activity_id": str(activity.id)}
