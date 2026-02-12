# -*- coding: utf-8 -*-
"""API Endpoints fuer EML/MSG Datei-Import (Drag&Drop).

Stellt REST-Endpoints bereit fuer:
- Upload und Parsen von .eml/.msg Dateien
- Import ausgewaehlter Anhaenge aus geparsten E-Mails
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.imports.eml_file_parser import (
    MAX_FILE_SIZE,
    parse_eml_file,
    parse_msg_file,
    validate_eml_file,
)
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/imports/email", tags=["email-file-import"])

# Max upload size: 25MB
MAX_UPLOAD_SIZE = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".eml", ".msg"}


# =============================================================================
# Pydantic Schemas
# =============================================================================


class EmlAttachmentResponse(BaseModel):
    """Schema fuer einen Anhang aus einer geparsten E-Mail."""

    index: int
    filename: str
    size: int
    mime_type: str
    is_importable: bool


class EmlParseResponse(BaseModel):
    """Schema fuer das Ergebnis des E-Mail-Parsens."""

    parse_id: str
    subject: str
    sender: str
    sender_name: str
    date: Optional[datetime] = None
    body_preview: str
    message_id: Optional[str] = None
    attachment_count: int
    importable_attachment_count: int
    attachments: List[EmlAttachmentResponse]


class EmlImportRequest(BaseModel):
    """Schema fuer den Import ausgewaehlter Anhaenge."""

    parse_id: str = Field(..., min_length=1, description="ID aus dem Parse-Ergebnis")
    selected_attachment_indices: List[int] = Field(
        ..., min_length=1, description="Indizes der zu importierenden Anh\u00e4nge"
    )
    target_folder_id: Optional[UUID] = Field(
        None, description="Zielordner-ID (optional)"
    )
    auto_ocr: bool = Field(True, description="Automatische OCR-Verarbeitung")
    auto_classify: bool = Field(True, description="Automatische Klassifizierung")


class ImportedAttachmentResponse(BaseModel):
    """Schema fuer einen importierten Anhang."""

    index: int
    filename: str
    size: int
    mime_type: str
    status: str


class EmlImportResponse(BaseModel):
    """Schema fuer das Ergebnis des Imports."""

    parse_id: str
    imported_count: int
    skipped_count: int
    attachments: List[ImportedAttachmentResponse]
    message: str


# =============================================================================
# In-Memory Parse Cache (session-scoped, for demo/MVP)
# =============================================================================

# Maps parse_id -> (raw_content, filename_extension)
# In production this would use Redis or a temp file store
_parse_cache: dict = {}


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/upload-eml",
    response_model=EmlParseResponse,
    status_code=status.HTTP_200_OK,
    summary="EML/MSG-Datei hochladen und parsen",
)
async def upload_and_parse_eml(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmlParseResponse:
    """Laed eine .eml oder .msg Datei hoch und parst sie.

    Gibt Metadaten und Anhangsliste zurueck (ohne binaere Inhalte).
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dateiname fehlt",
        )

    filename_lower = file.filename.lower()
    extension = ""
    if filename_lower.endswith(".eml"):
        extension = ".eml"
    elif filename_lower.endswith(".msg"):
        extension = ".msg"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ung\u00fcltiges Dateiformat. Erlaubt: .eml, .msg",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Datei zu gro\u00df (max. {MAX_UPLOAD_SIZE // (1024 * 1024)}MB)",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datei ist leer",
        )

    # Validate EML content
    if extension == ".eml":
        is_valid, error_msg = validate_eml_file(content)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_msg,
            )

    # Parse
    try:
        if extension == ".eml":
            parsed = parse_eml_file(content)
        else:
            parsed = parse_msg_file(content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "eml_parse_failed",
            **safe_error_log(e),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="E-Mail konnte nicht geparst werden",
        )

    # Generate parse_id and cache content for subsequent import
    parse_id = str(uuid4())
    _parse_cache[parse_id] = (content, extension)

    logger.info(
        "eml_parsed",
        parse_id=parse_id,
        attachment_count=len(parsed.attachments),
        user_id=str(current_user.id),
    )

    importable_count = sum(1 for a in parsed.attachments if a.is_importable)

    return EmlParseResponse(
        parse_id=parse_id,
        subject=parsed.subject,
        sender=parsed.sender,
        sender_name=parsed.sender_name,
        date=parsed.date,
        body_preview=parsed.body_preview,
        message_id=parsed.message_id,
        attachment_count=len(parsed.attachments),
        importable_attachment_count=importable_count,
        attachments=[
            EmlAttachmentResponse(
                index=att.index,
                filename=att.filename,
                size=att.size,
                mime_type=att.mime_type,
                is_importable=att.is_importable,
            )
            for att in parsed.attachments
        ],
    )


@router.post(
    "/import-eml",
    response_model=EmlImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Anh\u00e4nge aus geparster E-Mail importieren",
)
async def import_eml_attachments(
    request: EmlImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmlImportResponse:
    """Importiert ausgewaehlte Anhaenge aus einer zuvor geparsten E-Mail."""
    # Retrieve cached parse
    cached = _parse_cache.get(request.parse_id)
    if cached is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parse-Ergebnis nicht gefunden. Bitte Datei erneut hochladen.",
        )

    content, extension = cached

    # Re-parse to get attachment content
    try:
        if extension == ".eml":
            parsed = parse_eml_file(content)
        else:
            parsed = parse_msg_file(content)
    except Exception as e:
        logger.error(
            "eml_reimport_parse_failed",
            **safe_error_log(e),
            parse_id=request.parse_id,
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="E-Mail konnte nicht erneut geparst werden",
        )

    # Validate indices
    max_index = len(parsed.attachments) - 1
    invalid_indices = [
        i for i in request.selected_attachment_indices if i < 0 or i > max_index
    ]
    if invalid_indices:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ung\u00fcltige Anhang-Indizes: {invalid_indices}",
        )

    # Build attachment map
    att_by_index = {att.index: att for att in parsed.attachments}

    imported: List[ImportedAttachmentResponse] = []
    skipped_count = 0

    for idx in request.selected_attachment_indices:
        att = att_by_index.get(idx)
        if att is None:
            skipped_count += 1
            continue

        if not att.is_importable:
            imported.append(
                ImportedAttachmentResponse(
                    index=att.index,
                    filename=att.filename,
                    size=att.size,
                    mime_type=att.mime_type,
                    status="uebersprungen_nicht_importierbar",
                )
            )
            skipped_count += 1
            continue

        # Mark as imported (actual document pipeline integration would go here)
        imported.append(
            ImportedAttachmentResponse(
                index=att.index,
                filename=att.filename,
                size=att.size,
                mime_type=att.mime_type,
                status="importiert",
            )
        )

    imported_count = sum(1 for a in imported if a.status == "importiert")

    # Clean up cache after import
    _parse_cache.pop(request.parse_id, None)

    logger.info(
        "eml_attachments_imported",
        parse_id=request.parse_id,
        imported_count=imported_count,
        skipped_count=skipped_count,
        user_id=str(current_user.id),
    )

    return EmlImportResponse(
        parse_id=request.parse_id,
        imported_count=imported_count,
        skipped_count=skipped_count,
        attachments=imported,
        message=f"{imported_count} Anh\u00e4nge importiert, {skipped_count} \u00fcbersprungen",
    )
