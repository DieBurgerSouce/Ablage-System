# -*- coding: utf-8 -*-
"""
Erweiterter Annotation Service.

Dokument-Annotationen: Bereiche markieren, Kommentare, Bounding Boxes.
Erlaubt praezise Markierungen auf Dokumentseiten mit Kommentaren.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import DocumentAnnotation
from app.db.models_annotations_extended import AnnotationType

logger = structlog.get_logger(__name__)


class EnhancedAnnotationService:
    """Erweiterter Service für Dokument-Annotationen.

    Ergaenzt den bestehenden AnnotationService um:
    - Typisierte Annotationstypen (Bounding Box, Pfeile, Stempel)
    - Normalisierte Positionsangaben (0-1)
    - Resolve-Workflow
    """

    async def create_annotation(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
        author_id: UUID,
        annotation_type: AnnotationType,
        page_number: int,
        x: float,
        y: float,
        width: Optional[float] = None,
        height: Optional[float] = None,
        text: Optional[str] = None,
        color: str = "#FFD700",
    ) -> DocumentAnnotation:
        """Neue Annotation erstellen (Bounding Box + Kommentar).

        Args:
            db: Datenbank-Session
            company_id: Mandant-ID
            document_id: Dokument-ID
            author_id: Ersteller-ID
            annotation_type: Typ der Annotation
            page_number: Seitennummer
            x: X-Position (0.0-1.0 normalisiert)
            y: Y-Position (0.0-1.0 normalisiert)
            width: Breite für Bounding Box (optional)
            height: Höhe für Bounding Box (optional)
            text: Annotationstext (optional)
            color: Hex-Farbe (Standard: #FFD700)

        Returns:
            Erstellte DocumentAnnotation
        """
        position: Dict[str, float] = {"x": x, "y": y}
        if width is not None:
            position["width"] = width
        if height is not None:
            position["height"] = height

        annotation = DocumentAnnotation(
            id=uuid.uuid4(),
            document_id=document_id,
            company_id=company_id,
            user_id=author_id,
            annotation_type=annotation_type.value,
            content=text,
            page=page_number,
            position=position,
            color=color,
        )

        db.add(annotation)
        await db.flush()

        logger.info(
            "enhanced_annotation_created",
            annotation_id=str(annotation.id),
            document_id=str(document_id),
            annotation_type=annotation_type.value,
            page=page_number,
        )
        return annotation

    async def get_annotations(
        self,
        db: AsyncSession,
        document_id: UUID,
        page_number: Optional[int] = None,
    ) -> List[DocumentAnnotation]:
        """Alle Annotationen für ein Dokument/eine Seite abrufen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            page_number: Optionaler Seitenfilter

        Returns:
            Liste der Annotationen
        """
        conditions = [DocumentAnnotation.document_id == document_id]
        if page_number is not None:
            conditions.append(DocumentAnnotation.page == page_number)

        query = (
            select(DocumentAnnotation)
            .where(and_(*conditions))
            .order_by(DocumentAnnotation.page, DocumentAnnotation.created_at)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_annotation(
        self,
        db: AsyncSession,
        annotation_id: UUID,
        user_id: UUID,
        **updates: object,
    ) -> DocumentAnnotation:
        """Annotation aktualisieren.

        Args:
            db: Datenbank-Session
            annotation_id: Annotation-ID
            user_id: Benutzer-ID (für Berechtigungsprüfung)
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierte Annotation

        Raises:
            ValueError: Wenn Annotation nicht gefunden
        """
        result = await db.execute(
            select(DocumentAnnotation).where(
                DocumentAnnotation.id == annotation_id
            )
        )
        annotation = result.scalar_one_or_none()

        if not annotation:
            raise ValueError("Annotation nicht gefunden")

        allowed_fields = {"content", "color", "position", "page"}
        for field, value in updates.items():
            if field in allowed_fields and value is not None:
                setattr(annotation, field, value)

        await db.flush()

        logger.info(
            "enhanced_annotation_updated",
            annotation_id=str(annotation_id),
            user_id=str(user_id),
        )
        return annotation

    async def resolve_annotation(
        self,
        db: AsyncSession,
        annotation_id: UUID,
        user_id: UUID,
    ) -> DocumentAnnotation:
        """Annotation als erledigt markieren.

        Args:
            db: Datenbank-Session
            annotation_id: Annotation-ID
            user_id: Benutzer-ID der die Annotation erledigt

        Returns:
            Aktualisierte Annotation

        Raises:
            ValueError: Wenn Annotation nicht gefunden
        """
        result = await db.execute(
            select(DocumentAnnotation).where(
                DocumentAnnotation.id == annotation_id
            )
        )
        annotation = result.scalar_one_or_none()

        if not annotation:
            raise ValueError("Annotation nicht gefunden")

        annotation.is_resolved = True
        annotation.resolved_by_id = user_id
        annotation.resolved_at = utc_now()

        await db.flush()

        logger.info(
            "enhanced_annotation_resolved",
            annotation_id=str(annotation_id),
            resolved_by=str(user_id),
        )
        return annotation

    async def delete_annotation(
        self,
        db: AsyncSession,
        annotation_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Annotation löschen (nur Autor oder Admin).

        Args:
            db: Datenbank-Session
            annotation_id: Annotation-ID
            user_id: Benutzer-ID (muss Autor sein)

        Returns:
            True wenn erfolgreich gelöscht
        """
        result = await db.execute(
            select(DocumentAnnotation).where(
                and_(
                    DocumentAnnotation.id == annotation_id,
                    DocumentAnnotation.user_id == user_id,
                )
            )
        )
        annotation = result.scalar_one_or_none()

        if not annotation:
            return False

        await db.delete(annotation)
        await db.flush()

        logger.info(
            "enhanced_annotation_deleted",
            annotation_id=str(annotation_id),
            deleted_by=str(user_id),
        )
        return True


# Singleton
_enhanced_annotation_service: Optional[EnhancedAnnotationService] = None


def get_enhanced_annotation_service() -> EnhancedAnnotationService:
    """Factory-Funktion für EnhancedAnnotationService Singleton."""
    global _enhanced_annotation_service
    if _enhanced_annotation_service is None:
        _enhanced_annotation_service = EnhancedAnnotationService()
    return _enhanced_annotation_service
