"""
Portal-Dokumentenservice.

Kunden können Dokumente hochladen.
"""

from datetime import datetime, timezone
from typing import Optional, List, BinaryIO
from uuid import UUID
from pathlib import Path
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.models_portal import (
    PortalDocument, PortalUser
)

logger = structlog.get_logger(__name__)

# Erlaubte Dateitypen
ALLOWED_MIME_TYPES = {
    "application/pdf": [".pdf"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/tiff": [".tif", ".tiff"],
}

# Maximale Dateigröße (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


class PortalDocumentService:
    """
    Service für Dokument-Uploads im Kundenportal.
    """

    def __init__(self, db: AsyncSession, storage_path: str = "/data/portal_uploads"):
        self.db = db
        self.storage_path = storage_path

    def _validate_file(
        self,
        filename: str,
        content_type: Optional[str],
        file_size: int,
    ) -> tuple[bool, str]:
        """
        Validiere eine hochgeladene Datei.

        Returns:
            Tuple aus (ist_valide, Fehlermeldung)
        """
        # Sicherheit: Dateiname darf keine Pfad-Trenner, Null-Bytes oder
        # Parent-Verweise enthalten (Path-Traversal, CWE-22). Auch wenn
        # Path().stem/.suffix Verzeichnisanteile entfernt, lehnen wir hier
        # explizit ab statt uns auf Seiteneffekte zu verlassen.
        if not filename or not filename.strip():
            return False, "Ungueltiger Dateiname"
        if (
            "\x00" in filename
            or "/" in filename
            or "\\" in filename
            or ".." in filename
        ):
            return False, "Ungueltiger Dateiname (Pfad nicht erlaubt)"

        # Prüfe Dateigröße
        if file_size > MAX_FILE_SIZE:
            return False, f"Datei zu gross. Maximum: {MAX_FILE_SIZE // (1024*1024)} MB"

        # Prüfe Dateiendung
        ext = Path(filename).suffix.lower()
        allowed_extensions = []
        for extensions in ALLOWED_MIME_TYPES.values():
            allowed_extensions.extend(extensions)

        if ext not in allowed_extensions:
            return False, f"Dateityp nicht erlaubt. Erlaubt: {', '.join(allowed_extensions)}"

        # Prüfe MIME-Type wenn angegeben
        if content_type and content_type not in ALLOWED_MIME_TYPES:
            # Toleriere fehlenden MIME-Type, aber logge
            logger.warning(
                "portal_upload_unknown_mime",
                content_type=content_type,
                filename=filename,
            )

        return True, ""

    async def upload_document(
        self,
        portal_user: PortalUser,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        description: Optional[str] = None,
        document_type: Optional[str] = None,
        complaint_id: Optional[UUID] = None,
        message_id: Optional[UUID] = None,
    ) -> PortalDocument:
        """
        Lade ein Dokument hoch.
        """
        # Validiere
        is_valid, error = self._validate_file(filename, content_type, len(content))
        if not is_valid:
            raise ValueError(error)

        # Generiere Storage-Pfad
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_filename = Path(filename).stem[:50]  # Begrenze Länge
        ext = Path(filename).suffix.lower()
        storage_filename = f"{portal_user.company_id}/{portal_user.entity_id}/{timestamp}_{safe_filename}{ext}"
        full_path = os.path.join(self.storage_path, storage_filename)

        # Erstelle Verzeichnis falls noetig
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Speichere Datei
        with open(full_path, "wb") as f:
            f.write(content)

        # Erstelle DB-Eintrag
        portal_doc = PortalDocument(
            company_id=portal_user.company_id,
            entity_id=portal_user.entity_id,
            uploaded_by_id=portal_user.id,
            complaint_id=complaint_id,
            message_id=message_id,
            original_filename=filename,
            file_size=len(content),
            mime_type=content_type,
            storage_path=storage_filename,
            description=description,
            document_type=document_type,
            processing_status="pending",
        )

        self.db.add(portal_doc)
        await self.db.commit()
        await self.db.refresh(portal_doc)

        logger.info(
            "portal_document_uploaded",
            portal_document_id=str(portal_doc.id),
            entity_id=str(portal_user.entity_id),
            filename=filename,
            size=len(content),
        )

        return portal_doc

    async def get_documents(
        self,
        entity_id: UUID,
        company_id: UUID,
        complaint_id: Optional[UUID] = None,
        document_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole alle hochgeladenen Dokumente für einen Entity.
        """
        query = select(PortalDocument).where(
            and_(
                PortalDocument.entity_id == entity_id,
                PortalDocument.company_id == company_id,
            )
        )

        if complaint_id:
            query = query.where(PortalDocument.complaint_id == complaint_id)
        if document_type:
            query = query.where(PortalDocument.document_type == document_type)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(PortalDocument.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        documents = result.scalars().all()

        doc_list = []
        for doc in documents:
            doc_list.append({
                "id": str(doc.id),
                "original_filename": doc.original_filename,
                "file_size": doc.file_size,
                "mime_type": doc.mime_type,
                "description": doc.description,
                "document_type": doc.document_type,
                "processing_status": doc.processing_status,
                "complaint_id": str(doc.complaint_id) if doc.complaint_id else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
            })

        return doc_list, total

    async def get_document_detail(
        self,
        document_id: UUID,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[dict]:
        """
        Hole Details eines Dokuments.
        """
        result = await self.db.execute(
            select(PortalDocument).where(
                and_(
                    PortalDocument.id == document_id,
                    PortalDocument.entity_id == entity_id,
                    PortalDocument.company_id == company_id,
                )
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        return {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "description": doc.description,
            "document_type": doc.document_type,
            "processing_status": doc.processing_status,
            "processed_document_id": str(doc.document_id) if doc.document_id else None,
            "complaint_id": str(doc.complaint_id) if doc.complaint_id else None,
            "message_id": str(doc.message_id) if doc.message_id else None,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
        }

    async def get_document_content(
        self,
        document_id: UUID,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[tuple[bytes, str, str]]:
        """
        Hole den Inhalt eines Dokuments.

        Returns:
            Tuple aus (content, filename, content_type) oder None
        """
        result = await self.db.execute(
            select(PortalDocument).where(
                and_(
                    PortalDocument.id == document_id,
                    PortalDocument.entity_id == entity_id,
                    PortalDocument.company_id == company_id,
                )
            )
        )
        doc = result.scalar_one_or_none()

        if not doc or not doc.storage_path:
            return None

        full_path = os.path.join(self.storage_path, doc.storage_path)

        if not os.path.exists(full_path):
            logger.error(
                "portal_document_file_not_found",
                document_id=str(document_id),
                path=full_path,
            )
            return None

        with open(full_path, "rb") as f:
            content = f.read()

        return content, doc.original_filename, doc.mime_type or "application/octet-stream"

    async def delete_document(
        self,
        document_id: UUID,
        portal_user: PortalUser,
    ) -> bool:
        """
        Lösche ein hochgeladenes Dokument.

        Nur möglich wenn noch nicht verarbeitet.
        """
        result = await self.db.execute(
            select(PortalDocument).where(
                and_(
                    PortalDocument.id == document_id,
                    PortalDocument.entity_id == portal_user.entity_id,
                    PortalDocument.company_id == portal_user.company_id,
                    PortalDocument.processing_status == "pending",
                    PortalDocument.document_id.is_(None),  # Noch nicht verknüpft
                )
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return False

        # Lösche Datei
        if doc.storage_path:
            full_path = os.path.join(self.storage_path, doc.storage_path)
            if os.path.exists(full_path):
                os.remove(full_path)

        # Lösche DB-Eintrag
        await self.db.delete(doc)
        await self.db.commit()

        logger.info(
            "portal_document_deleted",
            document_id=str(document_id),
        )

        return True

    @staticmethod
    def get_allowed_file_types() -> List[dict]:
        """Gebe erlaubte Dateitypen zurück."""
        types = []
        for mime, extensions in ALLOWED_MIME_TYPES.items():
            types.append({
                "mime_type": mime,
                "extensions": extensions,
            })
        return types

    @staticmethod
    def get_max_file_size() -> int:
        """Gebe maximale Dateigröße zurück."""
        return MAX_FILE_SIZE


def get_portal_document_service(
    db: AsyncSession,
    storage_path: str = "/data/portal_uploads"
) -> PortalDocumentService:
    """Factory-Funktion für PortalDocumentService."""
    return PortalDocumentService(db, storage_path)
