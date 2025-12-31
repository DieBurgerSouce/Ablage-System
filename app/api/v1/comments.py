"""
Comments API Endpoints.

Enterprise-level Collaboration-Feature fuer Dokument-Kommentare:
- Kommentare zu Dokumenten hinzufuegen/bearbeiten/loeschen
- Replies (verschachtelte Kommentare)
- @Mentions mit Benachrichtigungen
- Reaktionen auf Kommentare

Feinpoliert und durchdacht - Collaboration auf Enterprise-Niveau.

Security:
- Dokumentzugriff wird vor jeder Operation validiert
- User-Existenz wird vor Mention-Benachrichtigungen geprüft
"""

import structlog
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, exists
from sqlalchemy.orm import selectinload

from app.db.models import (
    User,
    Document,
    DocumentComment,
    DocumentActivity,
    UserNotification,
    ActivityType,
    NotificationType,
    DocumentAccess,
    AccessLevel,
)
from app.api.dependencies import get_current_user, get_db
from app.db.schemas import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentsListResponse,
    MentionSchema,
    ReactionSchema,
    ReactionAdd,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["comments"])


async def _verify_document_access(
    db: AsyncSession,
    document_id: UUID,
    user_id: UUID,
    required_level: str = AccessLevel.COMMENT.value,
) -> Document:
    """Prueft ob User Zugriff auf das Dokument hat mit ausreichendem Access-Level.

    Zugriff erlaubt wenn:
    - User ist Owner des Dokuments (immer voller Zugriff)
    - User hat expliziten Zugriff via document_access Tabelle mit ausreichendem Level

    Access-Level Hierarchie:
    - VIEW: Nur lesen (NICHT ausreichend fuer Kommentare!)
    - COMMENT: Lesen + Kommentieren
    - EDIT: Lesen + Bearbeiten
    - MANAGE: Vollzugriff

    Args:
        db: Datenbank-Session
        document_id: ID des Dokuments
        user_id: ID des anfragenden Users
        required_level: Mindest-Access-Level (default: 'comment')

    Returns:
        Document wenn Zugriff erlaubt

    Raises:
        HTTPException 404: Dokument nicht gefunden
        HTTPException 403: Zugriff verweigert oder unzureichendes Level
    """
    # Access-Level Hierarchie definieren
    ACCESS_LEVEL_HIERARCHY = {
        AccessLevel.VIEW.value: 1,
        AccessLevel.COMMENT.value: 2,
        AccessLevel.EDIT.value: 3,
        AccessLevel.MANAGE.value: 4,
    }

    required_level_num = ACCESS_LEVEL_HIERARCHY.get(required_level, 2)

    # Dokument abrufen
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    # Owner hat immer vollen Zugriff
    if document.owner_id == user_id:
        return document

    # Pruefe shared access MIT access_level Check
    # Hole alle gueltigen Access-Levels fuer diesen User
    valid_levels = [
        level for level, num in ACCESS_LEVEL_HIERARCHY.items()
        if num >= required_level_num
    ]

    access_result = await db.execute(
        select(exists().where(
            and_(
                DocumentAccess.document_id == document_id,
                DocumentAccess.user_id == user_id,
                DocumentAccess.access_level.in_(valid_levels),
                or_(
                    DocumentAccess.expires_at.is_(None),
                    DocumentAccess.expires_at > func.now()
                )
            )
        ))
    )
    has_sufficient_access = access_result.scalar()

    if not has_sufficient_access:
        logger.warning(
            "document_access_denied",
            document_id=str(document_id),
            user_id=str(user_id),
            operation="comment",
            required_level=required_level,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Aktion auf diesem Dokument"
        )

    return document


def _build_comment_response(comment: DocumentComment, user: User) -> CommentResponse:
    """Erstellt CommentResponse aus DB-Modell."""
    # Parse mentions from JSON - MentionSchema erwartet UUID
    mentions = []
    if comment.mentions:
        for m in comment.mentions:
            try:
                mentions.append(MentionSchema(
                    userId=UUID(m.get("userId", "")),
                    userName=m.get("userName", ""),
                    startIndex=m.get("startIndex"),
                    endIndex=m.get("endIndex"),
                ))
            except (ValueError, TypeError):
                # Ungueltige UUID in alten Daten ignorieren
                logger.warning(
                    "invalid_mention_uuid",
                    mention_data=m,
                    comment_id=str(comment.id),
                )
                continue

    # Parse reactions from JSON
    reactions = []
    if comment.reactions:
        for r in comment.reactions:
            reactions.append(ReactionSchema(
                emoji=r.get("emoji", ""),
                count=r.get("count", 0),
                userIds=r.get("userIds", []),
            ))

    return CommentResponse(
        id=str(comment.id),
        documentId=str(comment.document_id),
        userId=str(comment.user_id),
        userName=user.full_name or user.username or user.email,
        userAvatar=None,  # Could be extended with avatar URL
        content=comment.content,
        mentions=mentions,
        parentId=str(comment.parent_id) if comment.parent_id else None,
        createdAt=comment.created_at.isoformat() if comment.created_at else "",
        updatedAt=comment.updated_at.isoformat() if comment.updated_at else None,
        isEdited=comment.is_edited,
        reactions=reactions,
    )


async def _create_activity(
    db: AsyncSession,
    document_id: UUID,
    user_id: UUID,
    activity_type: str,
    description: str,
    metadata: dict = None,
) -> None:
    """Erstellt einen Activity-Log-Eintrag."""
    activity = DocumentActivity(
        document_id=document_id,
        user_id=user_id,
        activity_type=activity_type,
        description=description,
        metadata=metadata or {},
    )
    db.add(activity)


async def _create_mention_notifications(
    db: AsyncSession,
    comment: DocumentComment,
    document: Document,
    from_user: User,
    mentions: List[MentionSchema],
) -> None:
    """Erstellt Benachrichtigungen fuer Mentions.

    Security: Validiert dass der erwähnte User existiert bevor
    eine Notification erstellt wird.
    """
    for mention in mentions:
        try:
            # MentionSchema.userId ist jetzt UUID, keine Konvertierung nötig
            mentioned_user_id = mention.userId

            # Nicht sich selbst benachrichtigen
            if mentioned_user_id == from_user.id:
                continue

            # Security: Pruefe ob User existiert
            user_result = await db.execute(
                select(exists().where(User.id == mentioned_user_id))
            )
            user_exists = user_result.scalar()

            if not user_exists:
                logger.warning(
                    "mention_user_not_found",
                    mentioned_user_id=str(mentioned_user_id),
                    comment_id=str(comment.id),
                    from_user_id=str(from_user.id),
                )
                continue

            notification = UserNotification(
                user_id=mentioned_user_id,
                from_user_id=from_user.id,
                document_id=document.id,
                notification_type=NotificationType.MENTION.value,
                title="Erwaehnung in Kommentar",
                message=f"{from_user.full_name or from_user.username} hat Sie in einem Kommentar erwaehnt",
                action_url=f"/documents/{document.id}?comment={comment.id}",
            )
            db.add(notification)
        except Exception as e:
            logger.warning(
                "mention_notification_failed",
                mention_user_id=str(mention.userId),
                error=str(e),
            )
            continue


@router.get(
    "/{document_id}/comments",
    response_model=CommentsListResponse,
    summary="Kommentare auflisten",
    description="Gibt alle Kommentare eines Dokuments zurueck."
)
async def list_comments(
    document_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentsListResponse:
    """Liste aller Kommentare eines Dokuments."""
    # Security: Pruefe Dokumentzugriff (VIEW Level reicht zum Lesen)
    await _verify_document_access(
        db, document_id, current_user.id,
        required_level=AccessLevel.VIEW.value
    )

    # Total count
    count_result = await db.execute(
        select(func.count(DocumentComment.id)).where(
            and_(
                DocumentComment.document_id == document_id,
                DocumentComment.is_deleted == False,
            )
        )
    )
    total = count_result.scalar() or 0

    # Query Kommentare mit User
    query = (
        select(DocumentComment, User)
        .join(User, DocumentComment.user_id == User.id)
        .where(
            and_(
                DocumentComment.document_id == document_id,
                DocumentComment.is_deleted == False,
            )
        )
        .order_by(DocumentComment.created_at.asc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    rows = result.all()

    comments = []
    for comment, user in rows:
        comments.append(_build_comment_response(comment, user))

    return CommentsListResponse(
        comments=comments,
        total=total,
        hasMore=(offset + limit) < total,
    )


@router.post(
    "/{document_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Kommentar hinzufuegen",
    description="Fuegt einen neuen Kommentar zu einem Dokument hinzu."
)
async def create_comment(
    document_id: UUID,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    """Neuen Kommentar erstellen."""
    # Security: Pruefe Dokumentzugriff
    document = await _verify_document_access(db, document_id, current_user.id)

    # Pruefe ob Parent-Kommentar existiert (falls Reply)
    if comment_data.parentId:
        parent_result = await db.execute(
            select(DocumentComment).where(
                and_(
                    DocumentComment.id == comment_data.parentId,
                    DocumentComment.document_id == document_id,
                    DocumentComment.is_deleted == False,
                )
            )
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent-Kommentar nicht gefunden"
            )

    # Mentions als JSON vorbereiten (UUID zu String für JSON-Speicherung)
    mentions_json = []
    if comment_data.mentions:
        for m in comment_data.mentions:
            mentions_json.append({
                "userId": str(m.userId),
                "userName": m.userName,
                "startIndex": m.startIndex,
                "endIndex": m.endIndex,
            })

    # Kommentar erstellen
    comment = DocumentComment(
        document_id=document_id,
        user_id=current_user.id,
        parent_id=comment_data.parentId,
        content=comment_data.content,
        mentions=mentions_json,
        reactions=[],
    )

    db.add(comment)
    await db.flush()  # ID generieren

    # Activity-Log erstellen
    activity_type = ActivityType.COMMENT_REPLIED.value if comment_data.parentId else ActivityType.COMMENT_ADDED.value
    await _create_activity(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        activity_type=activity_type,
        description=f"Kommentar hinzugefuegt" if not comment_data.parentId else "Antwort hinzugefuegt",
        metadata={"comment_id": str(comment.id)},
    )

    # Mention-Benachrichtigungen erstellen
    if comment_data.mentions:
        await _create_mention_notifications(
            db=db,
            comment=comment,
            document=document,
            from_user=current_user,
            mentions=comment_data.mentions,
        )

    # Reply-Benachrichtigung an Parent-Autor
    if comment_data.parentId:
        parent_result = await db.execute(
            select(DocumentComment).where(DocumentComment.id == comment_data.parentId)
        )
        parent = parent_result.scalar_one_or_none()
        if parent and parent.user_id != current_user.id:
            notification = UserNotification(
                user_id=parent.user_id,
                from_user_id=current_user.id,
                document_id=document_id,
                notification_type=NotificationType.COMMENT_REPLY.value,
                title="Antwort auf Ihren Kommentar",
                message=f"{current_user.full_name or current_user.username} hat auf Ihren Kommentar geantwortet",
                action_url=f"/documents/{document_id}?comment={comment.id}",
            )
            db.add(notification)

    await db.commit()
    await db.refresh(comment)

    logger.info(
        "comment_created",
        comment_id=str(comment.id),
        document_id=str(document_id),
        user_id=str(current_user.id),
        is_reply=bool(comment_data.parentId),
    )

    return _build_comment_response(comment, current_user)


@router.patch(
    "/{document_id}/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Kommentar aktualisieren",
    description="Aktualisiert einen bestehenden Kommentar."
)
async def update_comment(
    document_id: UUID,
    comment_id: UUID,
    comment_data: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    """Kommentar aktualisieren.

    Verwendet SELECT ... FOR UPDATE um TOCTOU Race Conditions zu verhindern.
    """
    # Security: Pruefe Dokumentzugriff
    await _verify_document_access(db, document_id, current_user.id)

    # Kommentar abrufen mit Row-Level Lock
    # FOR UPDATE verhindert dass der Kommentar zwischen Check und Update
    # von einem anderen Thread geloescht wird
    result = await db.execute(
        select(DocumentComment).where(
            and_(
                DocumentComment.id == comment_id,
                DocumentComment.document_id == document_id,
                DocumentComment.is_deleted == False,
            )
        ).with_for_update()
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kommentar nicht gefunden"
        )

    # Nur eigene Kommentare bearbeiten
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung zum Bearbeiten dieses Kommentars"
        )

    # Aktualisieren
    comment.content = comment_data.content
    comment.is_edited = True

    if comment_data.mentions:
        mentions_json = []
        for m in comment_data.mentions:
            mentions_json.append({
                "userId": str(m.userId),  # UUID zu String für JSON
                "userName": m.userName,
                "startIndex": m.startIndex,
                "endIndex": m.endIndex,
            })
        comment.mentions = mentions_json

    await db.commit()
    await db.refresh(comment)

    logger.info(
        "comment_updated",
        comment_id=str(comment_id),
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    return _build_comment_response(comment, current_user)


@router.delete(
    "/{document_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Kommentar loeschen",
    description="Loescht einen Kommentar (Soft-Delete)."
)
async def delete_comment(
    document_id: UUID,
    comment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Kommentar loeschen (Soft-Delete).

    Verwendet SELECT ... FOR UPDATE um TOCTOU Race Conditions zu verhindern.
    """
    # Security: Pruefe Dokumentzugriff
    await _verify_document_access(db, document_id, current_user.id)

    # Row-Level Lock verhindert gleichzeitige Updates waehrend wir loeschen
    result = await db.execute(
        select(DocumentComment).where(
            and_(
                DocumentComment.id == comment_id,
                DocumentComment.document_id == document_id,
                DocumentComment.is_deleted == False,
            )
        ).with_for_update()
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kommentar nicht gefunden"
        )

    # Nur eigene Kommentare loeschen (oder Admin)
    if comment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung zum Loeschen dieses Kommentars"
        )

    # Soft-Delete
    comment.is_deleted = True
    await db.commit()

    logger.info(
        "comment_deleted",
        comment_id=str(comment_id),
        document_id=str(document_id),
        user_id=str(current_user.id),
    )


@router.post(
    "/{document_id}/comments/{comment_id}/reactions",
    response_model=CommentResponse,
    summary="Reaktion hinzufuegen",
    description="Fuegt eine Reaktion zu einem Kommentar hinzu."
)
async def add_reaction(
    document_id: UUID,
    comment_id: UUID,
    reaction_data: ReactionAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    """Reaktion zu Kommentar hinzufuegen.

    Verwendet SELECT ... FOR UPDATE fuer atomare Updates bei Concurrent Access.
    """
    # Security: Pruefe Dokumentzugriff
    await _verify_document_access(db, document_id, current_user.id)

    # SELECT ... FOR UPDATE fuer Row-Level Locking
    # Dies verhindert Race Conditions bei gleichzeitigen Reaction-Updates
    result = await db.execute(
        select(DocumentComment, User)
        .join(User, DocumentComment.user_id == User.id)
        .where(
            and_(
                DocumentComment.id == comment_id,
                DocumentComment.document_id == document_id,
                DocumentComment.is_deleted == False,
            )
        )
        .with_for_update()  # Row-Level Lock
    )
    row = result.one_or_none()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kommentar nicht gefunden"
        )

    comment, comment_user = row

    # Reactions aktualisieren (jetzt unter Lock)
    # Deep copy um Referenz-Probleme zu vermeiden
    reactions = list(comment.reactions or [])
    user_id_str = str(current_user.id)

    # Suche existierende Reaktion mit diesem Emoji
    found = False
    for reaction in reactions:
        if reaction.get("emoji") == reaction_data.emoji:
            user_ids = list(reaction.get("userIds", []))
            if user_id_str not in user_ids:
                user_ids.append(user_id_str)
                reaction["userIds"] = user_ids
                reaction["count"] = len(user_ids)
            found = True
            break

    if not found:
        reactions.append({
            "emoji": reaction_data.emoji,
            "count": 1,
            "userIds": [user_id_str],
        })

    comment.reactions = reactions
    await db.commit()
    await db.refresh(comment)

    logger.info(
        "reaction_added",
        comment_id=str(comment_id),
        emoji=reaction_data.emoji,
        user_id=str(current_user.id),
    )

    return _build_comment_response(comment, comment_user)


@router.delete(
    "/{document_id}/comments/{comment_id}/reactions/{emoji}",
    response_model=CommentResponse,
    summary="Reaktion entfernen",
    description="Entfernt eine Reaktion von einem Kommentar."
)
async def remove_reaction(
    document_id: UUID,
    comment_id: UUID,
    emoji: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    """Reaktion von Kommentar entfernen.

    Verwendet SELECT ... FOR UPDATE fuer atomare Updates bei Concurrent Access.
    """
    # Security: Pruefe Dokumentzugriff
    await _verify_document_access(db, document_id, current_user.id)

    # SELECT ... FOR UPDATE fuer Row-Level Locking
    result = await db.execute(
        select(DocumentComment, User)
        .join(User, DocumentComment.user_id == User.id)
        .where(
            and_(
                DocumentComment.id == comment_id,
                DocumentComment.document_id == document_id,
                DocumentComment.is_deleted == False,
            )
        )
        .with_for_update()  # Row-Level Lock
    )
    row = result.one_or_none()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kommentar nicht gefunden"
        )

    comment, comment_user = row

    # Reactions aktualisieren (unter Lock)
    # Deep copy um Referenz-Probleme zu vermeiden
    reactions = list(comment.reactions or [])
    user_id_str = str(current_user.id)

    new_reactions = []
    for reaction in reactions:
        if reaction.get("emoji") == emoji:
            user_ids = list(reaction.get("userIds", []))
            if user_id_str in user_ids:
                user_ids.remove(user_id_str)
                reaction["userIds"] = user_ids
                reaction["count"] = len(user_ids)
            if reaction["count"] > 0:
                new_reactions.append(reaction)
        else:
            new_reactions.append(reaction)

    comment.reactions = new_reactions
    await db.commit()
    await db.refresh(comment)

    logger.info(
        "reaction_removed",
        comment_id=str(comment_id),
        emoji=emoji,
        user_id=str(current_user.id),
    )

    return _build_comment_response(comment, comment_user)
