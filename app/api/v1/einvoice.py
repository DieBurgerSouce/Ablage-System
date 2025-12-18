# -*- coding: utf-8 -*-
"""
E-Invoice API Endpoints.

Endpunkte fuer:
- /api/v1/einvoice/parse - E-Rechnung parsen
- /api/v1/einvoice/generate/zugferd - ZUGFeRD-PDF generieren
- /api/v1/einvoice/generate/xrechnung - XRechnung-XML generieren
- /api/v1/einvoice/validate - E-Rechnung validieren
- /api/v1/einvoice/formats - Unterstuetzte Formate

Standards: ZUGFeRD 2.x, XRechnung 3.0.2
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    **Unterstuetzte Formate:**
    - ZUGFeRD 2.x PDF (Factur-X)
    - XRechnung 3.0.x (CII oder UBL XML)
    - ZUGFeRD 1.0 PDF (Legacy)

    **Rueckgabe:**
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
) -> EInvoiceParseResponse:
    """Parst eine E-Rechnung aus hochgeladener Datei."""
    parser = get_parser_service()

    try:
        content = await file.read()
        filename = file.filename or "unknown"

        if extract_to_document:
            # TODO: Erst Dokument erstellen, dann parsen und speichern
            # Fuer jetzt: Nur parsen
            result = await parser.parse_file(content, filename)
        else:
            result = await parser.parse_file(content, filename)

        return result

    except ValueError as e:
        logger.warning(
            "einvoice_parse_validation_error",
            extra={"filename": file.filename, "error": str(e)}
        )
        raise HTTPException(status_code=400, detail=str(e))

    except ImportError as e:
        logger.error("einvoice_parse_import_error", extra={"error": str(e)})
        raise HTTPException(
            status_code=501,
            detail="factur-x Bibliothek nicht installiert"
        )

    except Exception as e:
        logger.exception("einvoice_parse_error")
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Parsen: {str(e)}"
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

    **Rueckgabe:** PDF-Datei zum Download
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
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-EInvoice-ID": str(einvoice_id),
            }
        )

    except ValueError as e:
        logger.warning(
            "einvoice_generate_zugferd_validation_error",
            extra={"document_id": str(document_id), "error": str(e)}
        )
        raise HTTPException(status_code=400, detail=str(e))

    except ImportError as e:
        logger.error("einvoice_generate_import_error", extra={"error": str(e)})
        raise HTTPException(
            status_code=501,
            detail="factur-x Bibliothek nicht installiert"
        )

    except Exception as e:
        logger.exception("einvoice_generate_zugferd_error")
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei ZUGFeRD-Generierung: {str(e)}"
        )


@router.post(
    "/generate/xrechnung",
    response_class=Response,
    summary="XRechnung-XML generieren",
    description="""
    Generiert eine XRechnung 3.0.2 konforme XML-Datei aus einem bestehenden Dokument.

    **Wichtig fuer B2G:**
    - Leitweg-ID (BT-10) muss im Dokument gesetzt sein
    - BT-23, BT-34, BT-49 sind Pflichtfelder ab Version 3.0.1

    **Syntax:**
    - CII: UN/CEFACT Cross Industry Invoice (empfohlen)
    - UBL: Universal Business Language 2.1 (erfordert Mustang)

    **Rueckgabe:** XML-Datei zum Download
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
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-EInvoice-ID": str(einvoice_id),
            }
        )

    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    except ValueError as e:
        logger.warning(
            "einvoice_generate_xrechnung_validation_error",
            extra={"document_id": str(document_id), "error": str(e)}
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.exception("einvoice_generate_xrechnung_error")
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei XRechnung-Generierung: {str(e)}"
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

    **Pruefungen:**
    - XML-Schema-Validierung (XSD)
    - Schematron-Business-Rules
    - PDF/A-3 Konformitaet (bei ZUGFeRD)
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

            # Pruefen ob PDF oder XML
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
                    detail=f"Keine E-Invoice fuer Dokument: {document_id}"
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

        # Validierung durchfuehren
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
        logger.exception("einvoice_validate_error")
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei Validierung: {str(e)}"
        )


# =============================================================================
# INFO ENDPOINTS
# =============================================================================

@router.get(
    "/formats",
    response_model=EInvoiceFormatsResponse,
    summary="Unterstuetzte Formate",
    description="Gibt alle unterstuetzten E-Rechnungsformate und Profile zurueck."
)
async def get_formats() -> EInvoiceFormatsResponse:
    """Gibt unterstuetzte Formate zurueck."""
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
    description="Prueft ob der Mustang Microservice verfuegbar ist."
)
async def check_mustang_health() -> dict:
    """Prueft Mustang Service Verfuegbarkeit."""
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
            "error": str(e),
        }

    except Exception as e:
        logger.warning(
            "mustang_health_check_error",
            extra={"error": str(e)}
        )
        return {
            "status": "error",
            "service": "mustang",
            "available": False,
            "error": str(e),
        }


@router.get(
    "/{document_id}",
    response_model=dict,
    summary="E-Invoice Status",
    description="Gibt den E-Invoice Status fuer ein Dokument zurueck."
)
async def get_einvoice_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Gibt E-Invoice Status zurueck."""
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
) -> Response:
    """Laedt XML herunter."""
    stmt = select(models.EInvoiceDocument).where(
        models.EInvoiceDocument.document_id == document_id
    )
    result = await db.execute(stmt)
    einvoice_doc = result.scalar_one_or_none()

    if not einvoice_doc or not einvoice_doc.xml_content:
        raise HTTPException(
            status_code=404,
            detail=f"Keine E-Invoice fuer Dokument: {document_id}"
        )

    filename = f"einvoice_{document_id}.xml"

    return Response(
        content=einvoice_doc.xml_content.encode("utf-8"),
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
    )
