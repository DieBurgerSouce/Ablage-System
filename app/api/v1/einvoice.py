# -*- coding: utf-8 -*-
"""
E-Invoice API Endpoints.

Endpunkte für:
- /api/v1/einvoice/parse - E-Rechnung parsen
- /api/v1/einvoice/generate/zugferd - ZUGFeRD-PDF generieren
- /api/v1/einvoice/generate/xrechnung - XRechnung-XML generieren
- /api/v1/einvoice/validate - E-Rechnung validieren
- /api/v1/einvoice/formats - Unterstützte Formate

Standards: ZUGFeRD 2.x, XRechnung 3.0.2
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user
from app.core.security import build_content_disposition
from app.db.models import User, Document, EInvoiceDocument
from app.services.storage_service import get_storage_service

from app.api.schemas.einvoice import (
    EInvoiceConvertRequest,
    EInvoiceConvertResponse,
    EInvoiceFormatsResponse,
    EInvoiceGenerateResponse,
    EInvoiceParseResponse,
    EInvoiceValidateRequest,
    EInvoiceValidationResponse,
    SupportedFormat,
    ValidationError,
    ValidationWarning,
    ValidatorType,
    XRechnungGenerateRequest,
    XRechnungSyntax,
    ZUGFeRDGenerateRequest,
    ZUGFeRDProfile,
)
from app.db import models
from app.db.database import get_async_db
from app.services.einvoice.generator_service import get_generator_service
from app.services.einvoice.parser_service import get_parser_service
from app.core.safe_errors import safe_error_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/einvoice", tags=["E-Invoice"])


# =============================================================================
# PARSE ENDPOINTS
# =============================================================================

@router.post(
    "/parse",
    response_model=EInvoiceParseResponse,
    summary="E-Rechnung parsen",
    description="""
    Parst eine eingehende E-Rechnung (ZUGFeRD-PDF oder XRechnung-XML).

    **Unterstützte Formate:**
    - ZUGFeRD 2.x PDF (Factur-X)
    - XRechnung 3.0.x (CII oder UBL XML)
    - ZUGFeRD 1.0 PDF (Legacy)

    **Rückgabe:**
    - Extrahierte Rechnungsdaten als ExtractedInvoiceData
    - Erkanntes Format und Profil
    - Optional: Direkte Speicherung als Dokument
    """
)
async def parse_einvoice(
    file: UploadFile = File(..., description="ZUGFeRD-PDF oder XRechnung-XML"),
    extract_to_document: bool = Query(
        False,
        description="Sofort als Dokument in DB speichern"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> EInvoiceParseResponse:
    """Parst eine E-Rechnung aus hochgeladener Datei."""
    parser = get_parser_service()

    try:
        content = await file.read()
        filename = file.filename or "unknown"

        # Parsen der E-Rechnung
        result = await parser.parse_file(content, filename)

        if extract_to_document:
            # Auto-Save: Dokument und E-Invoice-Datensatz erstellen
            storage = get_storage_service()

            # 1. Checksum berechnen
            file_hash = hashlib.sha256(content).hexdigest()

            # 2. MIME-Type bestimmen
            mime_type = file.content_type or (
                "application/pdf" if filename.lower().endswith(".pdf")
                else "application/xml"
            )

            # 3. In MinIO hochladen
            try:
                upload_result = await storage.upload_document(
                    file_data=content,
                    filename=filename,
                    content_type=mime_type,
                    user_id=str(current_user.id),
                    metadata={
                        "document_type": "invoice",
                        "einvoice_format": result.format_detected.value if result.format_detected else "unknown",
                        "original_filename": filename,
                    }
                )
            except Exception as e:
                logger.error("einvoice_storage_upload_failed", **safe_error_log(e))
                raise HTTPException(
                    status_code=500,
                    detail="Speicherung fehlgeschlagen. E-Rechnung wurde geparst aber nicht gespeichert."
                )

            # 4. Document-Eintrag erstellen
            doc_id = uuid4()
            new_document = Document(
                id=doc_id,
                filename=upload_result["storage_path"].split("/")[-1],
                original_filename=filename,
                file_path=upload_result["storage_path"],
                file_size=len(content),
                mime_type=mime_type,
                checksum=file_hash,
                document_type="invoice",
                status="processed",
                owner_id=current_user.id,
                extracted_data=result.invoice_data.model_dump() if result.invoice_data else {},
                document_metadata={
                    "einvoice_format": result.format_detected.value if result.format_detected else None,
                    "einvoice_profile": result.profile.value if result.profile else None,
                    "einvoice_version": result.version,
                    "auto_saved": True,
                }
            )
            db.add(new_document)

            # 5. EInvoiceDocument-Eintrag erstellen
            einvoice_id = uuid4()
            einvoice_doc = EInvoiceDocument(
                id=einvoice_id,
                document_id=doc_id,
                format=result.format_detected.value if result.format_detected else "unknown",
                profile=result.profile.value if result.profile else None,
                version=result.version,
                xml_content=result.xml_content,
                xml_hash=hashlib.sha256(result.xml_content.encode()).hexdigest() if result.xml_content else None,
                was_extracted=True,
                was_generated=False,
                source_filename=filename,
                extraction_method="facturx",
            )
            db.add(einvoice_doc)

            await db.commit()

            # IDs in der Response setzen
            result.document_id = doc_id
            result.einvoice_id = einvoice_id

            logger.info(
                "einvoice_auto_saved",
                document_id=str(doc_id),
                einvoice_id=str(einvoice_id),
                format=result.format_detected.value if result.format_detected else "unknown",
            )

        return result

    except ValueError as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung - keine internen Details
        logger.warning(
            "einvoice_parse_validation_error",
            extra={"filename": file.filename, **safe_error_log(e)}
        )
        raise HTTPException(status_code=400, detail="Ungültige E-Rechnung. Bitte Format prüfen.")

    except ImportError as e:
        logger.error("einvoice_parse_import_error", **safe_error_log(e))
        raise HTTPException(
            status_code=501,
            detail="factur-x Bibliothek nicht installiert"
        )

    except Exception as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung
        logger.exception("einvoice_parse_error")
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Parsen. Bitte versuchen Sie es erneut."
        )


# =============================================================================
# GENERATE ENDPOINTS
# =============================================================================

@router.post(
    "/generate/zugferd",
    response_class=Response,
    summary="ZUGFeRD-PDF generieren",
    description="""
    Generiert eine ZUGFeRD 2.x konforme PDF-Rechnung aus einem bestehenden Dokument.

    **Profile:**
    - MINIMUM: Minimale Daten
    - BASIC: Basis-Rechnungsdaten
    - EN16931: EN 16931 konform (empfohlen)
    - EXTENDED: Erweiterte Daten
    - XRECHNUNG: XRechnung-Profil (B2G Deutschland)

    **Rückgabe:** PDF-Datei zum Download
    """
)
async def generate_zugferd(
    document_id: UUID = Query(..., description="Dokument-ID"),
    profile: ZUGFeRDProfile = Query(
        ZUGFeRDProfile.EN16931,
        description="ZUGFeRD-Profil"
    ),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    """Generiert ein ZUGFeRD-PDF."""
    generator = get_generator_service()

    try:
        pdf_bytes, einvoice_id = await generator.generate_zugferd_pdf(
            document_id=document_id,
            db=db,
            profile=profile,
        )

        await db.commit()

        # Dateiname generieren
        filename = f"zugferd_{document_id}_{profile.value.lower()}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                # SECURITY: Use sanitized Content-Disposition (Phase 10)
                "Content-Disposition": build_content_disposition(filename, "attachment"),
                "X-EInvoice-ID": str(einvoice_id),
            }
        )

    except ValueError as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung
        logger.warning(
            "einvoice_generate_zugferd_validation_error",
            extra={"document_id": str(document_id), **safe_error_log(e)}
        )
        raise HTTPException(status_code=400, detail="Ungültige Daten für ZUGFeRD-Generierung.")

    except ImportError as e:
        logger.error("einvoice_generate_import_error", **safe_error_log(e))
        raise HTTPException(
            status_code=501,
            detail="factur-x Bibliothek nicht installiert"
        )

    except Exception as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung
        logger.exception("einvoice_generate_zugferd_error")
        raise HTTPException(
            status_code=500,
            detail="Fehler bei ZUGFeRD-Generierung. Bitte versuchen Sie es erneut."
        )


@router.post(
    "/generate/xrechnung",
    response_class=Response,
    summary="XRechnung-XML generieren",
    description="""
    Generiert eine XRechnung 3.0.2 konforme XML-Datei aus einem bestehenden Dokument.

    **Wichtig für B2G:**
    - Leitweg-ID (BT-10) muss im Dokument gesetzt sein
    - BT-23, BT-34, BT-49 sind Pflichtfelder ab Version 3.0.1

    **Syntax:**
    - CII: UN/CEFACT Cross Industry Invoice (empfohlen)
    - UBL: Universal Business Language 2.1 (erfordert Mustang)

    **Rückgabe:** XML-Datei zum Download
    """
)
async def generate_xrechnung(
    document_id: UUID = Query(..., description="Dokument-ID"),
    syntax: XRechnungSyntax = Query(
        XRechnungSyntax.CII,
        description="XML-Syntax: CII oder UBL"
    ),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    """Generiert ein XRechnung-XML."""
    generator = get_generator_service()

    try:
        xml_content, einvoice_id = await generator.generate_xrechnung_xml(
            document_id=document_id,
            db=db,
            syntax=syntax,
        )

        await db.commit()

        # Dateiname generieren
        filename = f"xrechnung_{document_id}_{syntax.value.lower()}.xml"

        return Response(
            content=xml_content.encode("utf-8"),
            media_type="application/xml",
            headers={
                # SECURITY: Use sanitized Content-Disposition (Phase 10)
                "Content-Disposition": build_content_disposition(filename, "attachment"),
                "X-EInvoice-ID": str(einvoice_id),
            }
        )

    except NotImplementedError as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung
        logger.warning("einvoice_xrechnung_not_implemented", **safe_error_log(e))
        raise HTTPException(status_code=501, detail="Diese XRechnung-Funktion ist nicht implementiert.")

    except ValueError as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung
        logger.warning(
            "einvoice_generate_xrechnung_validation_error",
            extra={"document_id": str(document_id), **safe_error_log(e)}
        )
        raise HTTPException(status_code=400, detail="Ungültige Daten für XRechnung-Generierung.")

    except Exception as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung
        logger.exception("einvoice_generate_xrechnung_error")
        raise HTTPException(
            status_code=500,
            detail="Fehler bei XRechnung-Generierung. Bitte versuchen Sie es erneut."
        )


# =============================================================================
# VALIDATION ENDPOINT
# =============================================================================

@router.post(
    "/validate",
    response_model=EInvoiceValidationResponse,
    summary="E-Rechnung validieren",
    description="""
    Validiert eine E-Rechnung gegen den Standard.

    **Validatoren:**
    - FACTURX: factur-x integrierte Validierung (schnell)
    - KOSIT: Offizieller KoSIT-Validator (erfordert Mustang)
    - MUSTANG: Mustang-integrierter Validator (erfordert Mustang)

    **Prüfungen:**
    - XML-Schema-Validierung (XSD)
    - Schematron-Business-Rules
    - PDF/A-3 Konformität (bei ZUGFeRD)
    """
)
async def validate_einvoice(
    file: Optional[UploadFile] = File(None, description="E-Rechnung als Datei"),
    document_id: Optional[UUID] = Query(None, description="Oder: Dokument-ID"),
    validator: ValidatorType = Query(
        ValidatorType.FACTURX,
        description="Validierungsengine"
    ),
    db: AsyncSession = Depends(get_async_db),
) -> EInvoiceValidationResponse:
    """Validiert eine E-Rechnung."""
    # Mindestens eine Quelle erforderlich
    if file is None and document_id is None:
        raise HTTPException(
            status_code=400,
            detail="Entweder 'file' oder 'document_id' erforderlich"
        )

    try:
        # Validator Service holen
        from app.services.einvoice.validator_service import (
            get_validator_service,
            ValidatorType as ServiceValidatorType,
        )
        validator_service = get_validator_service()

        # XML-Content oder PDF ermitteln
        xml_content: Optional[str] = None
        pdf_content: Optional[bytes] = None
        is_pdf = False

        if file:
            content = await file.read()
            filename = file.filename or "unknown"

            # Prüfen ob PDF oder XML
            if filename.lower().endswith(".pdf") or content[:4] == b"%PDF":
                pdf_content = content
                is_pdf = True
            else:
                # XML direkt oder via Parser extrahieren
                if content.startswith(b"<?xml") or content.startswith(b"<"):
                    xml_content = content.decode("utf-8")
                else:
                    parser = get_parser_service()
                    result = await parser.parse_file(content, filename)
                    xml_content = result.xml_content

        elif document_id:
            # Aus DB laden
            stmt = select(models.EInvoiceDocument).where(
                models.EInvoiceDocument.document_id == document_id
            )
            result = await db.execute(stmt)
            einvoice_doc = result.scalar_one_or_none()

            if not einvoice_doc:
                raise HTTPException(
                    status_code=404,
                    detail=f"Keine E-Invoice für Dokument: {document_id}"
                )

            xml_content = einvoice_doc.xml_content

        if not xml_content and not pdf_content:
            raise HTTPException(
                status_code=400,
                detail="Kein XML-Inhalt gefunden"
            )

        # Validator-Typ mappen
        service_validator = ServiceValidatorType.AUTO
        if validator == ValidatorType.FACTURX:
            service_validator = ServiceValidatorType.FACTURX
        elif validator == ValidatorType.KOSIT:
            service_validator = ServiceValidatorType.KOSIT
        elif validator == ValidatorType.MUSTANG:
            service_validator = ServiceValidatorType.MUSTANG

        # Validierung durchführen
        if is_pdf and pdf_content:
            validation_result = await validator_service.validate_pdf(
                pdf_content, service_validator
            )
        else:
            validation_result = await validator_service.validate_xml(
                xml_content, service_validator  # type: ignore
            )

        # Ergebnis in API-Response umwandeln
        errors: list[ValidationError] = []
        warnings: list[ValidationWarning] = []

        for msg in validation_result.messages:
            if msg.severity.value in ("fatal", "error"):
                errors.append(ValidationError(
                    code=msg.code,
                    location=msg.location,
                    message=msg.message,
                    severity=msg.severity.value
                ))
            else:
                warnings.append(ValidationWarning(
                    code=msg.code,
                    location=msg.location,
                    message=msg.message
                ))

        return EInvoiceValidationResponse(
            valid=validation_result.valid,
            validator_used=validation_result.validator_used,
            validated_at=validation_result.validated_at,
            schema_valid=validation_result.schema_valid,
            schematron_valid=validation_result.schematron_valid,
            pdf_a_compliant=validation_result.pdf_a_compliant,
            errors=errors,
            warnings=warnings,
            error_count=validation_result.error_count,
            warning_count=validation_result.warning_count,
        )

    except HTTPException:
        raise

    except Exception as e:
        # SECURITY FIX 28-19: Generische Fehlermeldung
        logger.exception("einvoice_validate_error")
        raise HTTPException(
            status_code=500,
            detail="Fehler bei Validierung. Bitte versuchen Sie es erneut."
        )


# =============================================================================
# INFO ENDPOINTS
# =============================================================================

@router.get(
    "/formats",
    response_model=EInvoiceFormatsResponse,
    summary="Unterstützte Formate",
    description="Gibt alle unterstützten E-Rechnungsformate und Profile zurück."
)
async def get_formats() -> EInvoiceFormatsResponse:
    """Gibt unterstützte Formate zurück."""
    return EInvoiceFormatsResponse(
        formats=[
            SupportedFormat(
                id="zugferd",
                name="ZUGFeRD 2.3.3",
                description="ZUGFeRD/Factur-X PDF mit eingebettetem XML",
                supported_profiles=["MINIMUM", "BASIC", "BASIC_WL", "EN16931", "EXTENDED"],
                b2g_compatible=False,
            ),
            SupportedFormat(
                id="xrechnung_cii",
                name="XRechnung 3.0.2 (CII)",
                description="XRechnung im UN/CEFACT CII-Format",
                supported_profiles=["XRECHNUNG"],
                b2g_compatible=True,
            ),
            SupportedFormat(
                id="xrechnung_ubl",
                name="XRechnung 3.0.2 (UBL)",
                description="XRechnung im UBL 2.1-Format (erfordert Mustang)",
                supported_profiles=["XRECHNUNG"],
                b2g_compatible=True,
            ),
        ],
        default_format="zugferd",
        default_profile="EN16931",
    )


@router.get(
    "/health/mustang",
    summary="Mustang Service Health",
    description="Prüft ob der Mustang Microservice verfügbar ist."
)
async def check_mustang_health() -> dict:
    """Prüft Mustang Service Verfügbarkeit."""
    from app.services.einvoice.mustang_client import (

        get_mustang_client,
        MustangConnectionError,
    )

    client = get_mustang_client()

    try:
        async with client:
            is_available = await client.is_available()

            if is_available:
                # Version abfragen
                version_info = await client.get_version()
                return {
                    "status": "healthy",
                    "service": "mustang",
                    "available": True,
                    "mustang_version": version_info.mustang_version,
                    "java_version": version_info.java_version,
                    "features": {
                        "xrechnung_ubl": True,
                        "kosit_validation": True,
                        "pdf_extraction": True,
                    }
                }
            else:
                return {
                    "status": "unavailable",
                    "service": "mustang",
                    "available": False,
                    "message": "Mustang Service nicht erreichbar",
                }

    except MustangConnectionError as e:
        return {
            "status": "error",
            "service": "mustang",
            "available": False,
            "error": safe_error_detail(e, "Vorgang"),
        }

    except Exception as e:
        logger.warning(
            "mustang_health_check_error",
            **safe_error_log(e)
        )
        return {
            "status": "error",
            "service": "mustang",
            "available": False,
            "error": safe_error_detail(e, "Vorgang"),
        }


@router.get(
    "/{document_id}",
    response_model=dict,
    summary="E-Invoice Status",
    description="Gibt den E-Invoice Status für ein Dokument zurück."
)
async def get_einvoice_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),  # W.3 SECURITY FIX: Auth required
) -> dict:
    """Gibt E-Invoice Status zurück.

    Args:
        document_id: Document UUID
        db: Database session
        current_user: Authenticated user (required)

    Raises:
        HTTPException 403: If user doesn't own the document
        HTTPException 404: If document not found
    """
    # W.3 SECURITY FIX: Verify document ownership (IDOR prevention)
    doc_stmt = select(models.Document).where(models.Document.id == document_id)
    doc_result = await db.execute(doc_stmt)
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail=f"Dokument nicht gefunden: {document_id}"
        )

    # Check ownership - user must own the document or be superuser
    if document.owner_id != current_user.id and not current_user.is_superuser:
        logger.warning(
            "einvoice_access_denied",
            extra={
                "document_id": str(document_id),
                "user_id": str(current_user.id),
                "owner_id": str(document.owner_id) if document.owner_id else None
            }
        )
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für dieses Dokument"
        )

    stmt = select(models.EInvoiceDocument).where(
        models.EInvoiceDocument.document_id == document_id
    )
    result = await db.execute(stmt)
    einvoice_doc = result.scalar_one_or_none()

    if not einvoice_doc:
        return {
            "has_einvoice": False,
            "document_id": str(document_id),
        }

    return {
        "has_einvoice": True,
        "document_id": str(document_id),
        "einvoice_id": str(einvoice_doc.id),
        "format": einvoice_doc.format,
        "profile": einvoice_doc.profile,
        "version": einvoice_doc.version,
        "is_valid": einvoice_doc.is_valid,
        "was_generated": einvoice_doc.was_generated,
        "was_extracted": einvoice_doc.was_extracted,
        "leitweg_id": einvoice_doc.leitweg_id,
        "validation_summary": einvoice_doc.get_validation_summary() if einvoice_doc.is_valid is not None else None,
        "created_at": einvoice_doc.created_at.isoformat() if einvoice_doc.created_at else None,
    }


@router.get(
    "/{document_id}/xml",
    response_class=Response,
    summary="XML herunterladen",
    description="Laedt das XML einer E-Rechnung herunter."
)
async def download_xml(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),  # W.4 SECURITY FIX: Auth required
) -> Response:
    """Laedt XML herunter.

    Args:
        document_id: Document UUID
        db: Database session
        current_user: Authenticated user (required)

    Raises:
        HTTPException 403: If user doesn't own the document
        HTTPException 404: If document or e-invoice not found
    """
    # W.4 SECURITY FIX: Verify document ownership (IDOR prevention)
    doc_stmt = select(models.Document).where(models.Document.id == document_id)
    doc_result = await db.execute(doc_stmt)
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail=f"Dokument nicht gefunden: {document_id}"
        )

    # Check ownership - user must own the document or be superuser
    if document.owner_id != current_user.id and not current_user.is_superuser:
        logger.warning(
            "einvoice_xml_download_denied",
            extra={
                "document_id": str(document_id),
                "user_id": str(current_user.id),
                "owner_id": str(document.owner_id) if document.owner_id else None
            }
        )
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für dieses Dokument"
        )

    stmt = select(models.EInvoiceDocument).where(
        models.EInvoiceDocument.document_id == document_id
    )
    result = await db.execute(stmt)
    einvoice_doc = result.scalar_one_or_none()

    if not einvoice_doc or not einvoice_doc.xml_content:
        raise HTTPException(
            status_code=404,
            detail=f"Keine E-Invoice für Dokument: {document_id}"
        )

    filename = f"einvoice_{document_id}.xml"

    return Response(
        content=einvoice_doc.xml_content.encode("utf-8"),
        media_type="application/xml",
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10)
            "Content-Disposition": build_content_disposition(filename, "attachment"),
        }
    )


# =============================================================================
# ZUGFERD EMBED/EXTRACT ENDPOINTS
# =============================================================================

def safe_error_detail(e: Exception, context: str = "Vorgang") -> str:
    """Generiert sichere Fehlermeldung ohne interne Details."""
    return f"{context} fehlgeschlagen. Bitte versuchen Sie es erneut."


@router.post(
    "/embed",
    response_class=Response,
    summary="XML in PDF embedden",
    description="""
    Embeddet ZUGFeRD XML in ein bestehendes PDF-Dokument.

    **Voraussetzungen:**
    - Dokument muss ein PDF sein
    - XML muss valide ZUGFeRD/Factur-X Struktur haben

    **Rückgabe:** PDF mit eingebettetem XML
    """
)
async def embed_xml_in_pdf(
    document_id: UUID = Query(..., description="Dokument-ID (muss PDF sein)"),
    xml_content: str = Query(None, description="XML-Inhalt (alternativ zu file)"),
    xml_file: Optional[UploadFile] = File(None, description="XML-Datei hochladen"),
    profile: str = Query("EN16931", description="ZUGFeRD-Profil"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """Embeddet ZUGFeRD XML in ein PDF."""
    from app.services.einvoice import get_zugferd_embedder, ZUGFeRDProfile
    from app.services.storage_service import get_storage_service

    # XML-Inhalt ermitteln
    if xml_file:
        xml_bytes = await xml_file.read()
        xml_content = xml_bytes.decode("utf-8")
    elif not xml_content:
        raise HTTPException(
            status_code=400,
            detail="Entweder xml_content oder xml_file erforderlich"
        )

    # Dokument laden und Berechtigung prüfen
    doc_stmt = select(models.Document).where(models.Document.id == document_id)
    doc_result = await db.execute(doc_stmt)
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")

    if not document.mime_type or "pdf" not in document.mime_type.lower():
        raise HTTPException(status_code=400, detail="Dokument ist kein PDF")

    try:
        # Profile validieren
        try:
            zugferd_profile = ZUGFeRDProfile(profile)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungültiges Profil: {profile}")

        embedder = get_zugferd_embedder()
        if not embedder.available:
            raise HTTPException(
                status_code=501,
                detail="PDF-Backend nicht verfügbar (PyMuPDF oder pikepdf erforderlich)"
            )

        storage = get_storage_service()

        # PDF laden
        pdf_content = await storage.get_document(document.file_path)
        if not pdf_content:
            raise HTTPException(status_code=404, detail="PDF nicht im Storage gefunden")

        # XML embedden
        embedded_pdf, metadata = embedder.embed_xml_in_pdf(
            pdf_content=pdf_content,
            xml_content=xml_content,
            profile=zugferd_profile,
        )

        filename = f"zugferd_{document_id}.pdf"

        return Response(
            content=embedded_pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": build_content_disposition(filename, "attachment"),
                "X-ZUGFeRD-Profile": profile,
                "X-XML-Hash": metadata.get("xml_hash", ""),
            }
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("embed_validation_error", **safe_error_log(e))
        raise HTTPException(status_code=400, detail="Ungültige Eingabedaten")
    except Exception as e:
        logger.exception("embed_xml_failed")
        raise HTTPException(status_code=500, detail="Embedding fehlgeschlagen")


@router.post(
    "/extract",
    response_model=dict,
    summary="XML aus PDF extrahieren",
    description="""
    Extrahiert eingebettetes ZUGFeRD XML aus einem PDF.

    **Rückgabe:**
    - xml_content: Extrahiertes XML
    - found: True wenn XML gefunden
    - profile: Erkanntes Profil (falls ermittelbar)
    """
)
async def extract_xml_from_pdf(
    document_id: UUID = Query(None, description="Dokument-ID"),
    file: Optional[UploadFile] = File(None, description="PDF-Datei hochladen"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Extrahiert ZUGFeRD XML aus PDF."""
    from app.services.einvoice import get_zugferd_embedder
    from app.services.storage_service import get_storage_service

    if not document_id and not file:
        raise HTTPException(
            status_code=400,
            detail="Entweder document_id oder file erforderlich"
        )

    embedder = get_zugferd_embedder()
    if not embedder.available:
        raise HTTPException(
            status_code=501,
            detail="PDF-Backend nicht verfügbar"
        )

    pdf_content: Optional[bytes] = None

    if file:
        pdf_content = await file.read()
    elif document_id:
        # Dokument laden
        doc_stmt = select(models.Document).where(models.Document.id == document_id)
        doc_result = await db.execute(doc_stmt)
        document = doc_result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

        if document.owner_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")

        storage = get_storage_service()
        pdf_content = await storage.get_document(document.file_path)

    if not pdf_content:
        raise HTTPException(status_code=404, detail="PDF nicht gefunden")

    try:
        xml_content = embedder.extract_xml_from_pdf(pdf_content)

        if xml_content:
            # Profil erkennen (vereinfacht)
            detected_profile = None
            if "urn:cen.eu:en16931" in xml_content:
                detected_profile = "EN16931"
            elif "urn:factur-x.eu:1p0:extended" in xml_content:
                detected_profile = "EXTENDED"
            elif "urn:factur-x.eu:1p0:basic" in xml_content:
                detected_profile = "BASIC"
            elif "urn:factur-x.eu:1p0:minimum" in xml_content:
                detected_profile = "MINIMUM"

            return {
                "found": True,
                "xml_content": xml_content,
                "profile": detected_profile,
                "document_id": str(document_id) if document_id else None,
            }
        else:
            return {
                "found": False,
                "xml_content": None,
                "profile": None,
                "document_id": str(document_id) if document_id else None,
                "message": "Kein eingebettetes XML gefunden",
            }

    except Exception as e:
        logger.exception("extract_xml_failed")
        raise HTTPException(status_code=500, detail="Extraktion fehlgeschlagen")


@router.post(
    "/check-pdfa3",
    response_model=dict,
    summary="PDF/A-3 Konformität prüfen",
    description="Prüft ob ein PDF PDF/A-3 konform ist und eingebettete Dateien hat."
)
async def check_pdfa3_compliance(
    document_id: UUID = Query(None, description="Dokument-ID"),
    file: Optional[UploadFile] = File(None, description="PDF-Datei hochladen"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Prüft PDF/A-3 Konformität."""
    from app.services.einvoice import get_zugferd_embedder
    from app.services.storage_service import get_storage_service

    if not document_id and not file:
        raise HTTPException(
            status_code=400,
            detail="Entweder document_id oder file erforderlich"
        )

    embedder = get_zugferd_embedder()
    if not embedder.available:
        raise HTTPException(status_code=501, detail="PDF-Backend nicht verfügbar")

    pdf_content: Optional[bytes] = None

    if file:
        pdf_content = await file.read()
    elif document_id:
        doc_stmt = select(models.Document).where(models.Document.id == document_id)
        doc_result = await db.execute(doc_stmt)
        document = doc_result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

        if document.owner_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")

        storage = get_storage_service()
        pdf_content = await storage.get_document(document.file_path)

    if not pdf_content:
        raise HTTPException(status_code=404, detail="PDF nicht gefunden")

    try:
        result = embedder.check_pdfa3_compliance(pdf_content)
        result["document_id"] = str(document_id) if document_id else None
        return result

    except Exception as e:
        logger.exception("pdfa3_check_failed")
        raise HTTPException(status_code=500, detail="Prüfung fehlgeschlagen")


@router.post(
    "/batch-convert",
    summary="Batch ZUGFeRD Konvertierung",
    description="""
    Startet asynchrone Batch-Konvertierung mehrerer Dokumente zu ZUGFeRD.

    **Rückgabe:** Task-ID für Status-Abfrage
    """
)
async def batch_convert_to_zugferd(
    document_ids: List[UUID] = Query(..., description="Liste der Dokument-IDs"),
    profile: str = Query("EN16931", description="ZUGFeRD-Profil"),
    overwrite: bool = Query(False, description="Bestehende E-Invoices überschreiben"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Startet Batch-Konvertierung zu ZUGFeRD."""
    from app.workers.tasks.einvoice_tasks import zugferd_batch_convert_task

    if len(document_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximal 50 Dokumente pro Batch"
        )

    try:
        task = zugferd_batch_convert_task.delay(
            document_ids=[str(doc_id) for doc_id in document_ids],
            user_id=str(current_user.id),
            profile=profile,
            overwrite_existing=overwrite,
        )

        return {
            "task_id": task.id,
            "status": "queued",
            "message": f"Batch-Konvertierung von {len(document_ids)} Dokumenten gestartet",
            "profile": profile,
            "document_count": len(document_ids),
        }

    except Exception as e:
        logger.error("batch_convert_start_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Batch-Konvertierung konnte nicht gestartet werden"
        )


# =============================================================================
# E-RECHNUNG 2025: TRANSMISSION ENDPOINTS (PEPPOL/EMAIL)
# =============================================================================

@router.post(
    "/{document_id}/send",
    response_model=dict,
    summary="E-Rechnung versenden",
    description="""
    Versendet eine E-Rechnung über Peppol oder Email-Fallback.

    **Peppol-Versand:**
    - Prüft automatisch ob Empfänger Peppol-faehig ist (SMP Lookup)
    - Sendet über konfigurierten Peppol Access Point
    - Tracking der Zustellung und Bestätigung (MDN)

    **Email-Fallback:**
    - Wenn Peppol nicht verfügbar, wird Email verwendet
    - XRechnung-XML als Anhang

    **Voraussetzungen:**
    - E-Invoice muss für Dokument existieren
    - Leitweg-ID (BT-10) muss gesetzt sein
    """
)
async def send_einvoice(
    document_id: UUID,
    fallback_email: Optional[str] = Query(None, description="Email für Fallback"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Versendet E-Rechnung über Peppol oder Email."""
    from app.workers.tasks.einvoice_tasks import einvoice_send_peppol_task

    # E-Invoice prüfen
    stmt = select(EInvoiceDocument).where(
        EInvoiceDocument.document_id == document_id
    )
    result = await db.execute(stmt)
    einvoice = result.scalar_one_or_none()

    if not einvoice:
        raise HTTPException(
            status_code=404,
            detail="Keine E-Invoice für dieses Dokument gefunden. Bitte zuerst generieren."
        )

    # Berechtigung prüfen
    doc_stmt = select(Document).where(Document.id == document_id)
    doc_result = await db.execute(doc_stmt)
    document = doc_result.scalar_one_or_none()

    if document and document.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")

    try:
        task = einvoice_send_peppol_task.delay(
            einvoice_id=str(einvoice.id),
            fallback_email=fallback_email,
        )

        return {
            "task_id": task.id,
            "status": "queued",
            "message": "E-Rechnung wurde in Versandwarteschlange eingereiht",
            "einvoice_id": str(einvoice.id),
            "leitweg_id": einvoice.leitweg_id,
        }

    except Exception as e:
        logger.error("einvoice_send_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Versand konnte nicht gestartet werden"
        )


@router.get(
    "/{document_id}/transmission",
    response_model=dict,
    summary="Transmission Status",
    description="Gibt den Übertragungsstatus einer E-Rechnung zurück."
)
async def get_transmission_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Gibt Transmission Status zurück."""
    from app.db.models_einvoice import EInvoiceTransmission

    # E-Invoice laden
    stmt = select(EInvoiceDocument).where(
        EInvoiceDocument.document_id == document_id
    )
    result = await db.execute(stmt)
    einvoice = result.scalar_one_or_none()

    if not einvoice:
        raise HTTPException(status_code=404, detail="Keine E-Invoice gefunden")

    # Transmissions laden
    trans_stmt = select(EInvoiceTransmission).where(
        EInvoiceTransmission.einvoice_id == einvoice.id
    ).order_by(EInvoiceTransmission.created_at.desc())

    trans_result = await db.execute(trans_stmt)
    transmissions = trans_result.scalars().all()

    return {
        "einvoice_id": str(einvoice.id),
        "leitweg_id": einvoice.leitweg_id,
        "transmissions": [
            {
                "id": str(t.id),
                "channel": t.channel,
                "status": t.status,
                "sent_at": t.sent_at.isoformat() if t.sent_at else None,
                "delivered_at": t.delivered_at.isoformat() if t.delivered_at else None,
                "acknowledged_at": t.acknowledged_at.isoformat() if t.acknowledged_at else None,
                "peppol_message_id": t.peppol_message_id,
                "error": t.last_error,
                "retry_count": t.retry_count,
            }
            for t in transmissions
        ],
        "has_transmissions": len(transmissions) > 0,
        "latest_status": transmissions[0].status if transmissions else None,
    }


@router.post(
    "/check-peppol",
    response_model=dict,
    summary="Peppol-Faehigkeit prüfen",
    description="Prüft ob ein Empfänger Peppol-faehig ist (SMP Lookup)."
)
async def check_peppol_capability(
    leitweg_id: str = Query(..., description="Leitweg-ID des Empfängers"),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Prüft Peppol-Faehigkeit eines Empfängers."""
    from app.services.einvoice import get_peppol_sender

    sender = get_peppol_sender()

    if not sender.is_configured:
        return {
            "peppol_available": False,
            "reason": "Peppol nicht konfiguriert",
            "fallback_required": True,
        }

    can_peppol, endpoint = await sender.check_peppol_capability(leitweg_id)

    return {
        "leitweg_id": leitweg_id,
        "peppol_available": can_peppol,
        "endpoint": {
            "participant_id": endpoint.participant_id if endpoint else None,
            "endpoint_url": endpoint.endpoint_url[:50] + "..." if endpoint and len(endpoint.endpoint_url) > 50 else (endpoint.endpoint_url if endpoint else None),
            "is_active": endpoint.is_active if endpoint else None,
        } if endpoint else None,
        "fallback_required": not can_peppol,
    }


# =============================================================================
# E-RECHNUNG 2025: INCOMING E-INVOICE ENDPOINTS
# =============================================================================

@router.post(
    "/receive",
    response_model=dict,
    summary="E-Rechnung empfangen (Webhook)",
    description="""
    Webhook-Endpunkt für eingehende E-Rechnungen.

    **Unterstützte Quellen:**
    - Peppol AS4 (automatisch via Access Point)
    - Manueller Upload (XML oder PDF)

    **Verarbeitung:**
    - Automatische Format-Erkennung
    - Validierung gegen XRechnung/ZUGFeRD
    - Entity-Linking (Absender erkennen)
    - Alert bei Validierungsfehlern
    """
)
async def receive_einvoice(
    file: Optional[UploadFile] = File(None, description="E-Rechnung Datei"),
    peppol_payload: Optional[str] = Query(None, description="Peppol XML Payload"),
    source: str = Query("upload", description="Quelle: peppol, email, portal, upload"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Empfängt und verarbeitet eingehende E-Rechnung."""
    from app.services.einvoice import get_receiver_service

    receiver = get_receiver_service()

    # Content ermitteln
    xml_content: Optional[str] = None
    pdf_content: Optional[bytes] = None
    filename: Optional[str] = None

    if file:
        content = await file.read()
        filename = file.filename

        if filename and filename.lower().endswith(".pdf"):
            # PDF: XML extrahieren
            from app.services.einvoice import get_zugferd_embedder
            embedder = get_zugferd_embedder()
            xml_content = embedder.extract_xml_from_pdf(content)
            pdf_content = content

            if not xml_content:
                raise HTTPException(
                    status_code=400,
                    detail="Kein eingebettetes XML im PDF gefunden"
                )
        else:
            # XML direkt
            try:
                xml_content = content.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="Datei ist kein gültiges UTF-8 XML"
                )

    elif peppol_payload:
        xml_content = peppol_payload
        source = "peppol"

    else:
        raise HTTPException(
            status_code=400,
            detail="Entweder 'file' oder 'peppol_payload' erforderlich"
        )

    # Company ID ermitteln (aus User)
    company_id = current_user.company_id if hasattr(current_user, 'company_id') else current_user.id

    try:
        result = await receiver.process_incoming_invoice(
            xml_content=xml_content,
            source=source,
            company_id=company_id,
            db=db,
            pdf_content=pdf_content,
            original_filename=filename,
            auto_link_entity=True,
            create_document=True,
        )

        if result.success:
            return {
                "success": True,
                "incoming_id": str(result.incoming_invoice_id) if result.incoming_invoice_id else None,
                "document_id": str(result.document_id) if result.document_id else None,
                "entity_id": str(result.entity_id) if result.entity_id else None,
                "validation_passed": result.validation_passed,
                "validation_errors": len(result.validation_errors),
                "validation_warnings": len(result.validation_warnings),
                "invoice_info": {
                    "invoice_number": result.invoice_info.invoice_number if result.invoice_info else None,
                    "invoice_date": result.invoice_info.invoice_date.isoformat() if result.invoice_info and result.invoice_info.invoice_date else None,
                    "seller_name": result.invoice_info.seller_name if result.invoice_info else None,
                    "gross_amount": str(result.invoice_info.gross_amount) if result.invoice_info and result.invoice_info.gross_amount else None,
                    "format": result.invoice_info.format if result.invoice_info else None,
                } if result.invoice_info else None,
                "alerts_created": len(result.alerts_created),
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=result.error or "Verarbeitung fehlgeschlagen"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("einvoice_receive_failed")
        raise HTTPException(
            status_code=500,
            detail="Verarbeitung fehlgeschlagen"
        )


@router.get(
    "/incoming",
    response_model=dict,
    summary="Eingehende E-Rechnungen",
    description="Listet alle eingehenden E-Rechnungen auf."
)
async def list_incoming_einvoices(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Listet eingehende E-Rechnungen."""
    from app.db.models_einvoice import IncomingEInvoice

    # Company ID
    company_id = current_user.company_id if hasattr(current_user, 'company_id') else current_user.id

    query = select(IncomingEInvoice).where(
        IncomingEInvoice.company_id == company_id
    )

    if status:
        query = query.where(IncomingEInvoice.status == status)

    query = query.order_by(IncomingEInvoice.received_at.desc()).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": str(item.id),
                "channel": item.channel,
                "status": item.status,
                "received_at": item.received_at.isoformat() if item.received_at else None,
                "invoice_number": item.invoice_number,
                "invoice_date": item.invoice_date.isoformat() if item.invoice_date else None,
                "seller_name": item.seller_name,
                "total_amount": str(item.total_amount) if item.total_amount else None,
                "currency": item.currency,
                "is_valid": item.is_valid,
                "format": item.format,
                "document_id": str(item.document_id) if item.document_id else None,
                "entity_id": str(item.entity_id) if item.entity_id else None,
            }
            for item in items
        ],
        "total": len(items),
        "page": page,
        "per_page": per_page,
    }


@router.get(
    "/incoming/{incoming_id}",
    response_model=dict,
    summary="Eingehende E-Rechnung Details",
    description="Gibt Details einer eingehenden E-Rechnung zurück."
)
async def get_incoming_einvoice(
    incoming_id: UUID,
    include_xml: bool = Query(False, description="XML-Inhalt einschließen"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Gibt Details einer eingehenden E-Rechnung zurück."""
    from app.db.models_einvoice import IncomingEInvoice

    query = select(IncomingEInvoice).where(
        IncomingEInvoice.id == incoming_id
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Eingehende E-Rechnung nicht gefunden")

    response = {
        "id": str(item.id),
        "channel": item.channel,
        "status": item.status,
        "received_at": item.received_at.isoformat() if item.received_at else None,
        "processed_at": item.processed_at.isoformat() if item.processed_at else None,
        "format": item.format,
        "invoice_number": item.invoice_number,
        "invoice_date": item.invoice_date.isoformat() if item.invoice_date else None,
        "seller_name": item.seller_name,
        "buyer_reference": item.buyer_reference,
        "total_amount": str(item.total_amount) if item.total_amount else None,
        "currency": item.currency,
        "is_valid": item.is_valid,
        "validation_errors": item.validation_errors,
        "validation_warnings": item.validation_warnings,
        "document_id": str(item.document_id) if item.document_id else None,
        "entity_id": str(item.entity_id) if item.entity_id else None,
        "peppol_message_id": item.peppol_message_id,
        "peppol_sender_id": item.peppol_sender_id,
        "email_sender": item.email_sender,
        "email_subject": item.email_subject,
    }

    if include_xml:
        response["xml_content"] = item.xml_content

    return response
