# -*- coding: utf-8 -*-
"""
Document Processing Tasks - Celery Tasks für Dokumentverarbeitung.

Tasks:
- document_bulk_export_task: Bulk-Export von Dokumenten (ZIP, PDF, CSV)
- document_cleanup_task: Alte Dokumente aufräumen
- document_reprocess_task: Dokumente neu verarbeiten
"""

import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID

import structlog
from celery import states
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app, CPUTask
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.session import get_async_session_context
from app.db.models import Document, User
from app.services.storage_service import get_storage_service

logger = structlog.get_logger(__name__)


# =============================================================================
# BULK EXPORT TASK
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_tasks.document_bulk_export_task",
    queue="default",
    max_retries=2,
    soft_time_limit=1800,  # 30 min
    time_limit=2100,  # 35 min
    acks_late=True,
)
def document_bulk_export_task(
    self,
    document_ids: List[str],
    user_id: str,
    export_format: str = "zip",
    include_metadata: bool = True,
) -> dict:
    """
    Exportiert mehrere Dokumente als ZIP, zusammengefuegtes PDF oder CSV.

    Args:
        document_ids: Liste der Dokument-UUIDs als Strings
        user_id: User-UUID für Berechtigungsprüfung
        export_format: "zip" | "pdf" | "csv"
        include_metadata: Metadaten-JSON beilegen (bei zip)

    Returns:
        dict mit:
        - success: bool
        - download_url: Temporaere Download-URL
        - file_size: Größe in Bytes
        - document_count: Anzahl exportierter Dokumente
        - errors: Liste fehlgeschlagener Dokumente
    """
    import asyncio

    async def _do_export():
        async with get_async_session_context() as db:
            return await _execute_bulk_export(
                db=db,
                document_ids=[UUID(doc_id) for doc_id in document_ids],
                user_id=UUID(user_id),
                export_format=export_format,
                include_metadata=include_metadata,
                task=self,
            )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_do_export())
        loop.close()
        return result

    except Exception as e:
        logger.error("document_bulk_export_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": safe_error_detail(e, "Export"),
            "document_count": 0,
            "errors": [],
        }


async def _execute_bulk_export(
    db: AsyncSession,
    document_ids: List[UUID],
    user_id: UUID,
    export_format: str,
    include_metadata: bool,
    task,
) -> dict:
    """
    Führt den eigentlichen Export aus.
    """
    storage = get_storage_service()
    errors: List[dict] = []
    exported_count = 0

    # Dokumente laden (nur die des Users)
    query = select(Document).where(
        Document.id.in_(document_ids),
        Document.owner_id == user_id,
        Document.deleted_at.is_(None)
    )
    result = await db.execute(query)
    documents = result.scalars().all()

    if not documents:
        return {
            "success": False,
            "error": "Keine Dokumente gefunden oder keine Berechtigung",
            "document_count": 0,
            "errors": [],
        }

    total = len(documents)

    if export_format == "zip":
        return await _export_as_zip(
            documents=documents,
            storage=storage,
            include_metadata=include_metadata,
            task=task,
            errors=errors,
            user_id=user_id,
        )

    elif export_format == "csv":
        return await _export_as_csv(
            documents=documents,
            storage=storage,
            task=task,
            user_id=user_id,
        )

    elif export_format == "pdf":
        return await _export_as_merged_pdf(
            documents=documents,
            storage=storage,
            task=task,
            errors=errors,
            user_id=user_id,
        )

    else:
        return {
            "success": False,
            "error": f"Unbekanntes Format: {export_format}",
            "document_count": 0,
            "errors": [],
        }


async def _export_as_zip(
    documents: List[Document],
    storage,
    include_metadata: bool,
    task,
    errors: List[dict],
    user_id: UUID,
) -> dict:
    """Exportiert Dokumente als ZIP-Archiv."""
    zip_buffer = io.BytesIO()
    exported_count = 0
    total = len(documents)

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, doc in enumerate(documents):
            try:
                # Progress Update
                task.update_state(
                    state=states.STARTED,
                    meta={
                        "current": i + 1,
                        "total": total,
                        "status": f"Exportiere {doc.original_filename or doc.filename}..."
                    }
                )

                # Datei aus Storage laden
                file_content = await storage.get_document(doc.file_path)

                if file_content:
                    # Eindeutigen Dateinamen generieren
                    filename = doc.original_filename or doc.filename or f"document_{doc.id}"
                    # Duplikate vermeiden
                    safe_filename = f"{doc.id[:8]}_{filename}"
                    zf.writestr(safe_filename, file_content)
                    exported_count += 1

                    # Metadaten beilegen
                    if include_metadata:
                        meta = {
                            "id": str(doc.id),
                            "filename": doc.original_filename,
                            "document_type": doc.document_type,
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                            "mime_type": doc.mime_type,
                            "file_size": doc.file_size,
                            "extracted_data": doc.extracted_data or {},
                            "tags": doc.tags or [],
                        }
                        meta_filename = f"{doc.id[:8]}_{Path(filename).stem}_metadata.json"
                        zf.writestr(meta_filename, json.dumps(meta, indent=2, ensure_ascii=False))
                else:
                    errors.append({
                        "document_id": str(doc.id),
                        "error": "Datei nicht im Storage gefunden"
                    })

            except Exception as e:
                errors.append({
                    "document_id": str(doc.id),
                    "error": safe_error_detail(e, "Export")
                })
                logger.warning("zip_export_document_failed", document_id=str(doc.id), **safe_error_log(e))

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()

    # ZIP in Storage speichern (temporaer)
    export_filename = f"export_{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    export_path = f"exports/{user_id}/{export_filename}"

    try:
        await storage.upload_document(
            file_data=zip_bytes,
            filename=export_filename,
            content_type="application/zip",
            user_id=str(user_id),
            metadata={"export_type": "bulk", "document_count": exported_count}
        )

        # Temporaere Download-URL generieren (1 Stunde gültig)
        download_url = await storage.get_presigned_url(export_path, expires_in=3600)

        return {
            "success": len(errors) == 0,
            "download_url": download_url,
            "file_path": export_path,
            "file_size": len(zip_bytes),
            "document_count": exported_count,
            "errors": errors,
            "format": "zip",
        }

    except Exception as e:
        logger.error("zip_upload_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": "ZIP-Upload fehlgeschlagen",
            "document_count": exported_count,
            "errors": errors,
        }


async def _export_as_csv(
    documents: List[Document],
    storage,
    task,
    user_id: UUID,
) -> dict:
    """Exportiert Dokument-Metadaten als CSV."""
    import csv
    from io import StringIO

    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer, delimiter=";", quoting=csv.QUOTE_ALL)

    # Header
    writer.writerow([
        "ID",
        "Dateiname",
        "Dokumenttyp",
        "MIME-Type",
        "Größe (Bytes)",
        "Erstellt am",
        "Status",
        "Tags",
        "OCR-Konfidenz",
    ])

    # Daten
    for doc in documents:
        writer.writerow([
            str(doc.id),
            doc.original_filename or doc.filename,
            doc.document_type or "",
            doc.mime_type or "",
            doc.file_size or 0,
            doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "",
            doc.status or "",
            ", ".join(doc.tags or []),
            doc.ocr_confidence or "",
        ])

    csv_content = csv_buffer.getvalue().encode("utf-8-sig")  # BOM für Excel

    # CSV speichern
    export_filename = f"export_{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    export_path = f"exports/{user_id}/{export_filename}"

    try:
        await storage.upload_document(
            file_data=csv_content,
            filename=export_filename,
            content_type="text/csv; charset=utf-8",
            user_id=str(user_id),
            metadata={"export_type": "csv", "document_count": len(documents)}
        )

        download_url = await storage.get_presigned_url(export_path, expires_in=3600)

        return {
            "success": True,
            "download_url": download_url,
            "file_path": export_path,
            "file_size": len(csv_content),
            "document_count": len(documents),
            "errors": [],
            "format": "csv",
        }

    except Exception as e:
        logger.error("csv_upload_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": "CSV-Upload fehlgeschlagen",
            "document_count": len(documents),
            "errors": [],
        }


async def _export_as_merged_pdf(
    documents: List[Document],
    storage,
    task,
    errors: List[dict],
    user_id: UUID,
) -> dict:
    """Fuegt alle PDFs zu einem zusammen."""
    try:
        from pypdf import PdfWriter
    except ImportError:
        try:
            from PyPDF2 import PdfWriter
        except ImportError:
            return {
                "success": False,
                "error": "PDF-Bibliothek nicht installiert (pypdf oder PyPDF2)",
                "document_count": 0,
                "errors": [],
            }

    writer = PdfWriter()
    exported_count = 0
    total = len(documents)

    for i, doc in enumerate(documents):
        try:
            # Nur PDFs
            if not doc.mime_type or "pdf" not in doc.mime_type.lower():
                errors.append({
                    "document_id": str(doc.id),
                    "error": "Kein PDF"
                })
                continue

            task.update_state(
                state=states.STARTED,
                meta={
                    "current": i + 1,
                    "total": total,
                    "status": f"Fuege {doc.original_filename or doc.filename} hinzu..."
                }
            )

            file_content = await storage.get_document(doc.file_path)
            if file_content:
                from io import BytesIO
                try:
                    from pypdf import PdfReader
                except ImportError:
                    from PyPDF2 import PdfReader

                reader = PdfReader(BytesIO(file_content))
                for page in reader.pages:
                    writer.add_page(page)
                exported_count += 1
            else:
                errors.append({
                    "document_id": str(doc.id),
                    "error": "Datei nicht gefunden"
                })

        except Exception as e:
            errors.append({
                "document_id": str(doc.id),
                "error": safe_error_detail(e, "PDF-Merge")
            })
            logger.warning("pdf_merge_document_failed", document_id=str(doc.id), **safe_error_log(e))

    if exported_count == 0:
        return {
            "success": False,
            "error": "Keine PDFs konnten zusammengefuegt werden",
            "document_count": 0,
            "errors": errors,
        }

    # Merged PDF schreiben
    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()

    export_filename = f"merged_{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
    export_path = f"exports/{user_id}/{export_filename}"

    try:
        await storage.upload_document(
            file_data=pdf_bytes,
            filename=export_filename,
            content_type="application/pdf",
            user_id=str(user_id),
            metadata={"export_type": "merged_pdf", "document_count": exported_count}
        )

        download_url = await storage.get_presigned_url(export_path, expires_in=3600)

        return {
            "success": len(errors) == 0,
            "download_url": download_url,
            "file_path": export_path,
            "file_size": len(pdf_bytes),
            "document_count": exported_count,
            "errors": errors,
            "format": "pdf",
        }

    except Exception as e:
        logger.error("pdf_upload_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": "PDF-Upload fehlgeschlagen",
            "document_count": exported_count,
            "errors": errors,
        }


# =============================================================================
# REPROCESS TASK
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_tasks.document_reprocess_task",
    queue="default",
    max_retries=1,
)
def document_reprocess_task(
    self,
    document_ids: List[str],
    user_id: str,
    reprocess_ocr: bool = True,
    reprocess_embeddings: bool = False,
) -> dict:
    """
    Verarbeitet Dokumente erneut (OCR und/oder Embeddings).

    Args:
        document_ids: Liste der Dokument-UUIDs
        user_id: User-UUID
        reprocess_ocr: OCR erneut ausführen
        reprocess_embeddings: Embeddings neu generieren

    Returns:
        dict mit Verarbeitungsergebnis
    """
    # Hier könnte man OCR-Tasks triggern
    from app.workers.tasks.ocr_tasks import process_document_task
    from app.workers.tasks.embedding_tasks import generate_document_embedding

    results = {"success": 0, "failed": 0, "errors": []}

    for doc_id in document_ids:
        try:
            if reprocess_ocr:
                process_document_task.delay(document_id=doc_id)

            if reprocess_embeddings:
                generate_document_embedding.delay(
                    document_id=doc_id,
                )

            results["success"] += 1

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "document_id": doc_id,
                "error": safe_error_detail(e, "Reprocess")
            })

    return results
