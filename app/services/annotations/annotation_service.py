"""Dokumentenannotations-Service.

Verwaltet PDF/Bild-Annotationen mit Threading, @-Mentions und Approval-Markierungen.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentAnnotation, User

logger = structlog.get_logger(__name__)


class AnnotationService:
    """Service für Dokument-Annotationen."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_annotation(
        self,
        document_id: UUID,
        user_id: UUID,
        company_id: UUID,
        annotation_type: str,
        content: str,
        page_number: int = 1,
        position: Optional[dict[str, float]] = None,
        svg_data: Optional[str] = None,
        parent_annotation_id: Optional[UUID] = None,
        mentioned_user_ids: Optional[list[UUID]] = None,
    ) -> DocumentAnnotation:
        """Erstellt eine neue Annotation.

        Args:
            document_id: Dokument-ID
            user_id: Ersteller
            company_id: Mandant (RLS)
            annotation_type: Typ (comment, highlight, drawing, approval, rejection)
            content: Textinhalt
            page_number: Seitennummer (Standard: 1)
            position: Position als Dict {x, y, width, height}
            svg_data: SVG-Daten für Zeichnungen
            parent_annotation_id: Eltern-Annotation für Threads
            mentioned_user_ids: Erwaehnte Benutzer

        Returns:
            Erstellte Annotation
        """
        annotation = DocumentAnnotation(
            document_id=document_id,
            user_id=user_id,
            company_id=company_id,
            annotation_type=annotation_type,
            content=content,
            page=page_number,
            position=position or {},
            svg_data=svg_data,
            parent_annotation_id=parent_annotation_id,
            mentioned_user_ids=[str(uid) for uid in (mentioned_user_ids or [])],
        )
        self.db.add(annotation)
        await self.db.flush()

        logger.info(
            "annotation_created",
            annotation_id=str(annotation.id),
            document_id=str(document_id),
            annotation_type=annotation_type,
        )
        return annotation

    async def get_annotations_for_document(
        self,
        document_id: UUID,
        company_id: UUID,
        page_number: Optional[int] = None,
        annotation_type: Optional[str] = None,
        include_resolved: bool = False,
    ) -> Sequence[DocumentAnnotation]:
        """Holt alle Annotationen für ein Dokument."""
        query = select(DocumentAnnotation).where(
            and_(
                DocumentAnnotation.document_id == document_id,
                DocumentAnnotation.company_id == company_id,
            )
        )

        if page_number is not None:
            query = query.where(DocumentAnnotation.page == page_number)
        if annotation_type:
            query = query.where(DocumentAnnotation.annotation_type == annotation_type)
        if not include_resolved:
            query = query.where(
                or_(
                    DocumentAnnotation.is_resolved == False,
                    DocumentAnnotation.is_resolved == None,
                )
            )

        query = query.order_by(DocumentAnnotation.page, DocumentAnnotation.created_at)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_thread(
        self,
        annotation_id: UUID,
        company_id: UUID,
    ) -> Sequence[DocumentAnnotation]:
        """Holt einen kompletten Annotation-Thread."""
        query = (
            select(DocumentAnnotation)
            .where(
                and_(
                    or_(
                        DocumentAnnotation.id == annotation_id,
                        DocumentAnnotation.parent_annotation_id == annotation_id,
                    ),
                    DocumentAnnotation.company_id == company_id,
                )
            )
            .order_by(DocumentAnnotation.created_at)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_annotation(
        self,
        annotation_id: UUID,
        company_id: UUID,
        user_id: UUID,
        content: Optional[str] = None,
        is_resolved: Optional[bool] = None,
    ) -> Optional[DocumentAnnotation]:
        """Aktualisiert eine Annotation."""
        query = select(DocumentAnnotation).where(
            and_(
                DocumentAnnotation.id == annotation_id,
                DocumentAnnotation.company_id == company_id,
            )
        )
        result = await self.db.execute(query)
        annotation = result.scalar_one_or_none()

        if not annotation:
            return None

        if content is not None:
            annotation.content = content
        if is_resolved is not None:
            annotation.is_resolved = is_resolved
            if is_resolved:
                annotation.resolved_by_id = user_id
                annotation.resolved_at = datetime.utcnow()

        await self.db.flush()
        return annotation

    async def delete_annotation(
        self,
        annotation_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Löscht eine Annotation (nur eigene)."""
        query = select(DocumentAnnotation).where(
            and_(
                DocumentAnnotation.id == annotation_id,
                DocumentAnnotation.company_id == company_id,
                DocumentAnnotation.user_id == user_id,
            )
        )
        result = await self.db.execute(query)
        annotation = result.scalar_one_or_none()

        if not annotation:
            return False

        await self.db.delete(annotation)
        await self.db.flush()
        return True

    async def get_annotation_stats(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> dict[str, int]:
        """Statistiken für Dokument-Annotationen."""
        query = select(
            DocumentAnnotation.annotation_type,
            func.count(DocumentAnnotation.id),
        ).where(
            and_(
                DocumentAnnotation.document_id == document_id,
                DocumentAnnotation.company_id == company_id,
            )
        ).group_by(DocumentAnnotation.annotation_type)

        result = await self.db.execute(query)
        stats: dict[str, int] = {}
        for row in result:
            stats[row[0]] = row[1]
        stats["total"] = sum(stats.values())
        return stats
