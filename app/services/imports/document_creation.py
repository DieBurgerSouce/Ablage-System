# -*- coding: utf-8 -*-
"""Kanonischer Dokument-Anlage-Pfad für die Import-Kanäle (E-Mail/Folder).

Hintergrund (Neuausrichtung Welle D, Defekt 1): Die Import-Services riefen
``DocumentService(self.db).create(...)`` auf — ``DocumentService`` in
``app/services/document_service.py`` hat aber weder einen db-Konstruktor
noch eine ``create()``-Methode, d. h. jeder Import wäre mit einem
Laufzeit-``TypeError`` gecrasht. Dieses Modul bündelt stattdessen den
funktionierenden Anlage-Weg des Upload-Endpoints (``api/v1/documents.py``)
und von ``scripts/import_wa_we.py``:

    StorageService.upload_document -> Document-ORM -> Commit -> OCR-Task

Eigenschaften:
- MinIO-Upload mit ASCII-sicheren Objekt-Metadaten (S3-User-Metadata sind
  HTTP-Header, US-ASCII — Umlaut-Dateinamen dürfen den Import nicht brechen;
  der Original-Name bleibt in ``Document.original_filename`` erhalten).
- ``Document.company_id`` ist NOT NULL: Company kommt aus der Import-Config,
  sonst Fallback über ``UserCompany`` (User-Modell hat KEIN company_id-Feld).
- Optionaler Standard-Ordner via ``folder_documents``-Verknüpfung
  (Document hat keine folder_id-Spalte).
- OCR-Task best-effort NACH dem Commit (der Task läuft in einem anderen
  Prozess und braucht die persistierte Zeile); bei Einreihungs-Fehler fällt
  der Status auf "uploaded" zurück (Muster aus api/v1/documents.py).
- ``auto_classify`` braucht keinen eigenen Trigger: Die Quick Classification
  wird vom OCR-Task nach Abschluss getriggert (siehe ocr_tasks.py).

Feinpoliert und durchdacht.
"""

from __future__ import annotations

import os
from typing import Dict, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


def ascii_safe_filename(filename: str) -> str:
    """Umlaut-sichere ASCII-Variante für MinIO-Objekt-Metadaten.

    S3/MinIO-User-Metadata sind HTTP-Header (US-ASCII); "März_Rechnung.pdf"
    würde dort knallen. Muster aus ``scripts/import_wa_we.py``.
    """
    mapping = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    }
    for src, dst in mapping.items():
        filename = filename.replace(src, dst)
    safe = filename.encode("ascii", "ignore").decode("ascii")
    return safe or "unnamed"


async def resolve_import_company_id(
    db: AsyncSession,
    user_id: UUID,
    config_company_id: Optional[UUID],
) -> UUID:
    """Ermittelt die Company für ein Import-Dokument.

    Vorrang hat die Company der Import-Konfiguration; sonst die aktive
    Firma des Config-Users via ``UserCompany`` (gleiche Logik wie
    ``api/dependencies.get_user_company_id`` — das User-Modell selbst hat
    kein Firmen-Feld, Security-Fix B1).

    Raises:
        ValueError: Wenn keine Company ermittelbar ist —
            ``Document.company_id`` ist NOT NULL, ohne Firma kann kein
            Dokument angelegt werden (Fehler landet im ImportLog).
    """
    if config_company_id is not None:
        return config_company_id

    from app.db.models_cash_company import Company, UserCompany

    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user_id)
        .where(UserCompany.is_current == True)  # noqa: E712
        .where(Company.is_active == True)  # noqa: E712
        .where(Company.deleted_at.is_(None))
        .order_by(UserCompany.created_at.desc(), UserCompany.id.desc())
        .limit(1)
    )
    company_id = result.scalars().first()

    if company_id is None:
        result = await db.execute(
            select(UserCompany.company_id)
            .join(Company, Company.id == UserCompany.company_id)
            .where(UserCompany.user_id == user_id)
            .where(Company.is_active == True)  # noqa: E712
            .where(Company.deleted_at.is_(None))
            .order_by(UserCompany.created_at.asc())
            .limit(1)
        )
        company_id = result.scalars().first()

    if company_id is None:
        raise ValueError(
            "Keine aktive Firma für den Import-Benutzer gefunden — "
            "Dokument kann nicht angelegt werden (company_id ist Pflicht)"
        )
    return company_id


async def _link_default_folder(
    db: AsyncSession,
    document_id: UUID,
    folder_id: UUID,
    user_id: UUID,
) -> None:
    """Verknüpft das Dokument best-effort mit dem Standard-Ordner der Config.

    Document hat KEINE folder_id-Spalte — die Zuordnung läuft über die
    ``folder_documents``-Tabelle (Muster aus auto_filing_service). Ein
    stale/gelöschter Ordner darf den Import nicht brechen.
    """
    from app.db.models_folder import Folder, FolderDocument

    folder = await db.get(Folder, folder_id)
    if folder is None:
        logger.warning(
            "import_default_folder_missing",
            document_id=str(document_id),
            folder_id=str(folder_id),
        )
        return

    db.add(
        FolderDocument(
            folder_id=folder_id,
            document_id=document_id,
            is_primary=True,
            added_by_id=user_id,
        )
    )


async def create_import_document(
    db: AsyncSession,
    *,
    user_id: UUID,
    company_id: UUID,
    content: bytes,
    filename: str,
    original_filename: str,
    mime_type: str,
    file_size: int,
    file_hash: str,
    import_metadata: Dict[str, object],
    document_type: str = "other",
    default_folder_id: Optional[UUID] = None,
    auto_ocr: bool = True,
) -> UUID:
    """Legt ein Import-Dokument auf dem kanonischen Weg an.

    Ablauf identisch zum Upload-Endpoint (api/v1/documents.py):
    MinIO-Upload -> Document-Zeile (mit ``document_metadata``) ->
    optionaler Ordner-Link -> Commit -> OCR-Task (best-effort).

    Args:
        db: Async-Session (Aufrufer-Session; es wird committet, damit der
            OCR-Worker die Zeile sieht — die Import-Services committen im
            Fluss ohnehin mehrfach, z. B. im Duplikat-Pfad).
        user_id: Owner des Dokuments.
        company_id: Ziel-Company (Pflicht, siehe resolve_import_company_id).
        content: Datei-Bytes (bereits Malware-gescannt vom Aufrufer).
        filename: Ziel-Dateiname (bereits bereinigt vom Aufrufer).
        original_filename: Unveränderter Quell-Dateiname (DB, max. 255).
        mime_type: MIME-Type.
        file_size: Dateigröße in Bytes.
        file_hash: SHA256 (wird als ``Document.checksum`` persistiert;
            Dedupe hat der Aufrufer bereits gemacht).
        import_metadata: Quell-Metadaten (import_source, email_from, ...) —
            landen 1:1 in ``Document.document_metadata``.
        document_type: DocumentType-Wert (Default "other"; Import-Regeln
            können ihn nachträglich setzen).
        default_folder_id: Optionaler Standard-Ordner der Import-Config.
        auto_ocr: OCR-Task nach Anlage einreihen (Status "pending"),
            sonst Status "uploaded".

    Returns:
        Die Document-ID.
    """
    from app.db.models import Document
    from app.services.storage_service import get_storage_service

    import_source = str(import_metadata.get("import_source") or "import")

    # 1) MinIO-Upload (StorageService generiert user_id/hash-basierten Key)
    storage = get_storage_service()
    upload_result = await storage.upload_document(
        file_data=content,
        filename=ascii_safe_filename(os.path.basename(filename)),
        content_type=mime_type,
        user_id=str(user_id),
        metadata={"import-source": ascii_safe_filename(import_source)},
    )
    storage_path = upload_result["storage_path"]

    # 2) Document-Zeile (derselbe Weg wie Upload-API/import_wa_we)
    doc_id = uuid4()
    document = Document(
        id=doc_id,
        filename=storage_path.split("/")[-1],
        original_filename=(original_filename or filename)[:255],
        file_path=storage_path,
        file_size=file_size,
        mime_type=mime_type,
        checksum=file_hash,
        document_type=document_type,
        status="pending" if auto_ocr else "uploaded",
        owner_id=user_id,
        company_id=company_id,
        document_metadata=dict(import_metadata),
    )
    db.add(document)
    await db.flush()

    # 3) Standard-Ordner-Verknüpfung (best-effort)
    if default_folder_id is not None:
        try:
            await _link_default_folder(db, doc_id, default_folder_id, user_id)
        except Exception as folder_err:
            logger.warning(
                "import_folder_link_failed",
                document_id=str(doc_id),
                folder_id=str(default_folder_id),
                **safe_error_log(folder_err),
            )

    # Erst persistieren, dann OCR anstoßen — der Task läuft in einem
    # anderen Prozess und braucht die committete Zeile.
    await db.commit()

    # 4) OCR-Task best-effort (Muster api/v1/documents.py): Fehler bei der
    #    Einreihung (z. B. Redis weg) brechen den Import NICHT ab.
    if auto_ocr:
        try:
            from app.workers.tasks.ocr_tasks import process_document_task

            process_document_task.apply_async(
                kwargs={
                    "document_id": str(doc_id),
                    "backend": "auto",
                    "language": "de",
                    "priority": "normal",
                },
            )
        except Exception as ocr_err:
            logger.warning(
                "import_ocr_queue_failed",
                document_id=str(doc_id),
                **safe_error_log(ocr_err),
            )
            document.status = "uploaded"
            await db.commit()

    logger.info(
        "import_document_created",
        document_id=str(doc_id),
        import_source=import_source,
        company_id=str(company_id),
        auto_ocr=auto_ocr,
    )
    return doc_id
