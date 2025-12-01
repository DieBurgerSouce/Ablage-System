"""Document Sharing API endpoints.

Provides REST API endpoints for:
- Sharing documents with other users
- Managing document access permissions
- Viewing shared documents
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.models import User, Document, DocumentAccess, AccessLevel
from app.db.database import get_db
from app.api.dependencies import get_current_active_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sharing", tags=["sharing"])


# ==================== Schemas ====================

class ShareDocumentRequest(BaseModel):
    """Request für Dokumentfreigabe."""
    user_id: UUID = Field(..., description="Benutzer-ID des Empfängers")
    access_level: str = Field(
        default="view",
        description="Zugriffsebene: view, comment, edit, manage"
    )
    expires_in_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Ablauf in Tagen (optional)"
    )
    can_share: bool = Field(
        default=False,
        description="Darf der Empfänger weitergeben?"
    )
    note: Optional[str] = Field(
        None,
        max_length=500,
        description="Optionale Notiz"
    )


class ShareResponse(BaseModel):
    """Response für Dokumentfreigabe."""
    id: UUID
    document_id: UUID
    user_id: UUID
    access_level: str
    expires_at: Optional[datetime]
    can_share: bool
    created_at: datetime
    message: str


class SharedUserInfo(BaseModel):
    """Information über einen Benutzer mit Zugriff."""
    user_id: UUID
    username: str
    email: str
    access_level: str
    can_share: bool
    expires_at: Optional[datetime]
    granted_at: datetime
    granted_by_username: Optional[str]


class SharedDocumentInfo(BaseModel):
    """Information über ein geteiltes Dokument."""
    document_id: UUID
    filename: str
    document_type: Optional[str]
    access_level: str
    shared_by_username: str
    shared_at: datetime
    expires_at: Optional[datetime]


class UpdateAccessRequest(BaseModel):
    """Request für Aktualisierung des Zugriffs."""
    access_level: Optional[str] = Field(None, description="Neue Zugriffsebene")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Neuer Ablauf")
    can_share: Optional[bool] = Field(None, description="Weitergabe erlauben?")


# ==================== Endpoints ====================

@router.post("/documents/{document_id}/share", response_model=ShareResponse)
async def share_document(
    document_id: UUID,
    request: ShareDocumentRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokument mit einem anderen Benutzer teilen.

    **Zugriffsebenen:**
    - view: Nur lesen
    - comment: Lesen + Kommentieren
    - edit: Lesen + Bearbeiten
    - manage: Vollzugriff inkl. Weitergabe

    **Beispiel:**
    ```
    POST /api/v1/sharing/documents/{id}/share
    {
        "user_id": "...",
        "access_level": "edit",
        "expires_in_days": 30
    }
    ```
    """
    # Validiere Zugriffsebene
    valid_levels = [e.value for e in AccessLevel]
    if request.access_level not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Zugriffsebene. Erlaubt: {', '.join(valid_levels)}"
        )

    # Prüfe ob Benutzer Eigentümer ist oder Manage-Berechtigung hat
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Prüfe Berechtigung zum Teilen
    can_share = False
    if document.owner_id == current_user.id:
        can_share = True
    else:
        # Prüfe DocumentAccess
        access_query = select(DocumentAccess).where(
            and_(
                DocumentAccess.document_id == document_id,
                DocumentAccess.user_id == current_user.id,
                DocumentAccess.can_share == True,
                or_(
                    DocumentAccess.expires_at.is_(None),
                    DocumentAccess.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        result = await db.execute(access_query)
        user_access = result.scalar_one_or_none()
        if user_access:
            can_share = True

    if not can_share:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung zum Teilen dieses Dokuments"
        )

    # Verhindere Teilen mit sich selbst
    if request.user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Dokument kann nicht mit sich selbst geteilt werden"
        )

    # Prüfe ob Empfänger existiert
    recipient_query = select(User).where(User.id == request.user_id)
    result = await db.execute(recipient_query)
    recipient = result.scalar_one_or_none()

    if not recipient:
        raise HTTPException(status_code=404, detail="Empfänger nicht gefunden")

    if not recipient.is_active:
        raise HTTPException(status_code=400, detail="Empfänger ist deaktiviert")

    # Prüfe ob bereits geteilt
    existing_query = select(DocumentAccess).where(
        and_(
            DocumentAccess.document_id == document_id,
            DocumentAccess.user_id == request.user_id
        )
    )
    result = await db.execute(existing_query)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Dokument ist bereits mit diesem Benutzer geteilt. Verwende PUT zum Aktualisieren."
        )

    # Ablaufdatum berechnen
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)

    # Zugriff erstellen
    access = DocumentAccess(
        document_id=document_id,
        user_id=request.user_id,
        granted_by_id=current_user.id,
        access_level=request.access_level,
        expires_at=expires_at,
        can_share=request.can_share,
        share_note=request.note
    )
    db.add(access)
    await db.commit()
    await db.refresh(access)

    logger.info(
        "document_shared",
        document_id=str(document_id),
        shared_by=str(current_user.id),
        shared_with=str(request.user_id),
        access_level=request.access_level
    )

    return ShareResponse(
        id=access.id,
        document_id=document_id,
        user_id=request.user_id,
        access_level=request.access_level,
        expires_at=expires_at,
        can_share=request.can_share,
        created_at=access.created_at,
        message=f"Dokument erfolgreich mit {recipient.username} geteilt"
    )


@router.delete("/documents/{document_id}/share/{user_id}")
async def revoke_share(
    document_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumentfreigabe widerrufen.

    Nur der Dokument-Eigentümer oder der ursprüngliche Teilende
    kann die Freigabe widerrufen.
    """
    # Prüfe Dokument-Eigentümer
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Hole den Zugriffseintrag
    access_query = select(DocumentAccess).where(
        and_(
            DocumentAccess.document_id == document_id,
            DocumentAccess.user_id == user_id
        )
    )
    result = await db.execute(access_query)
    access = result.scalar_one_or_none()

    if not access:
        raise HTTPException(status_code=404, detail="Freigabe nicht gefunden")

    # Prüfe Berechtigung zum Widerrufen
    can_revoke = (
        document.owner_id == current_user.id or  # Eigentümer
        access.granted_by_id == current_user.id  # Ursprünglicher Teilender
    )

    if not can_revoke:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung zum Widerrufen dieser Freigabe"
        )

    await db.delete(access)
    await db.commit()

    logger.info(
        "document_share_revoked",
        document_id=str(document_id),
        revoked_by=str(current_user.id),
        revoked_for=str(user_id)
    )

    return {"message": "Freigabe erfolgreich widerrufen"}


@router.get("/documents/{document_id}/shared-with", response_model=List[SharedUserInfo])
async def get_shared_users(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Liste aller Benutzer, mit denen das Dokument geteilt ist.

    Nur der Dokument-Eigentümer oder Benutzer mit Manage-Berechtigung
    können diese Liste sehen.
    """
    # Prüfe Dokument und Berechtigung
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Prüfe Berechtigung
    is_owner = document.owner_id == current_user.id
    has_manage = False

    if not is_owner:
        access_query = select(DocumentAccess).where(
            and_(
                DocumentAccess.document_id == document_id,
                DocumentAccess.user_id == current_user.id,
                DocumentAccess.access_level == AccessLevel.MANAGE.value,
                or_(
                    DocumentAccess.expires_at.is_(None),
                    DocumentAccess.expires_at > datetime.now(timezone.utc)
                )
            )
        )
        result = await db.execute(access_query)
        has_manage = result.scalar_one_or_none() is not None

    if not is_owner and not has_manage:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung zum Anzeigen der Freigaben"
        )

    # Hole alle Freigaben mit Benutzerinfo
    from sqlalchemy.orm import aliased
    granted_by_user = aliased(User)

    query = (
        select(
            DocumentAccess,
            User.username,
            User.email,
            granted_by_user.username.label("granted_by_username")
        )
        .join(User, DocumentAccess.user_id == User.id)
        .outerjoin(granted_by_user, DocumentAccess.granted_by_id == granted_by_user.id)
        .where(DocumentAccess.document_id == document_id)
        .order_by(DocumentAccess.created_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    shared_users = []
    for access, username, email, granted_by in rows:
        shared_users.append(SharedUserInfo(
            user_id=access.user_id,
            username=username,
            email=email,
            access_level=access.access_level,
            can_share=access.can_share,
            expires_at=access.expires_at,
            granted_at=access.created_at,
            granted_by_username=granted_by
        ))

    return shared_users


@router.get("/shared-with-me", response_model=List[SharedDocumentInfo])
async def get_documents_shared_with_me(
    include_expired: bool = Query(False, description="Abgelaufene Freigaben anzeigen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Liste aller Dokumente, die mit mir geteilt wurden.

    Zeigt alle Dokumente an, auf die der aktuelle Benutzer
    via DocumentAccess Zugriff hat (nicht eigene Dokumente).
    """
    from sqlalchemy.orm import aliased
    granted_by_user = aliased(User)

    conditions = [DocumentAccess.user_id == current_user.id]

    if not include_expired:
        conditions.append(
            or_(
                DocumentAccess.expires_at.is_(None),
                DocumentAccess.expires_at > datetime.now(timezone.utc)
            )
        )

    query = (
        select(
            DocumentAccess,
            Document.filename,
            Document.document_type,
            granted_by_user.username.label("shared_by_username")
        )
        .join(Document, DocumentAccess.document_id == Document.id)
        .outerjoin(granted_by_user, DocumentAccess.granted_by_id == granted_by_user.id)
        .where(and_(*conditions))
        .order_by(DocumentAccess.created_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    shared_docs = []
    for access, filename, doc_type, shared_by in rows:
        shared_docs.append(SharedDocumentInfo(
            document_id=access.document_id,
            filename=filename,
            document_type=doc_type,
            access_level=access.access_level,
            shared_by_username=shared_by or "Unbekannt",
            shared_at=access.created_at,
            expires_at=access.expires_at
        ))

    return shared_docs


@router.put("/documents/{document_id}/share/{user_id}", response_model=ShareResponse)
async def update_share(
    document_id: UUID,
    user_id: UUID,
    request: UpdateAccessRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Bestehende Freigabe aktualisieren.

    Erlaubt das Ändern von:
    - Zugriffsebene
    - Ablaufdatum
    - Weitergabe-Berechtigung
    """
    # Prüfe Dokument und Berechtigung
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Hole bestehenden Zugriff
    access_query = select(DocumentAccess).where(
        and_(
            DocumentAccess.document_id == document_id,
            DocumentAccess.user_id == user_id
        )
    )
    result = await db.execute(access_query)
    access = result.scalar_one_or_none()

    if not access:
        raise HTTPException(status_code=404, detail="Freigabe nicht gefunden")

    # Prüfe Berechtigung zum Ändern
    can_update = (
        document.owner_id == current_user.id or
        access.granted_by_id == current_user.id
    )

    if not can_update:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung zum Ändern dieser Freigabe"
        )

    # Aktualisieren
    if request.access_level:
        valid_levels = [e.value for e in AccessLevel]
        if request.access_level not in valid_levels:
            raise HTTPException(
                status_code=400,
                detail=f"Ungültige Zugriffsebene. Erlaubt: {', '.join(valid_levels)}"
            )
        access.access_level = request.access_level

    if request.expires_in_days is not None:
        access.expires_at = datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)

    if request.can_share is not None:
        access.can_share = request.can_share

    await db.commit()
    await db.refresh(access)

    logger.info(
        "document_share_updated",
        document_id=str(document_id),
        updated_by=str(current_user.id),
        updated_for=str(user_id)
    )

    return ShareResponse(
        id=access.id,
        document_id=document_id,
        user_id=user_id,
        access_level=access.access_level,
        expires_at=access.expires_at,
        can_share=access.can_share,
        created_at=access.created_at,
        message="Freigabe erfolgreich aktualisiert"
    )
