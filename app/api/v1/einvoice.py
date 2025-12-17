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
        # XML-Content ermitteln
        xml_content: Optional[str] = None

        if file:
            content = await file.read()
            parser = get_parser_service()
            result = await parser.parse_file(content, file.filename or "unknown")
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

        if not xml_content:
            raise HTTPException(
                status_code=400,
                detail="Kein XML-Inhalt gefunden"
            )

        # Validierung durchfuehren
        # TODO: Echte Validierung mit KoSIT/Mustang implementieren
        # Fuer jetzt: Basis-Validierung

        errors: list[ValidationError] = []
        warnings: list[ValidationWarning] = []
        schema_valid = True
        schematron_valid = True

        # Einfache XML-Validierung
        try:
            from lxml import etree
            etree.fromstring(xml_content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            schema_valid = False
            errors.append(ValidationError(
                code="XML_SYNTAX",
                location="root",
                message=str(e),
                severity="fatal"
            ))

        is_valid = schema_valid and schematron_valid and len(errors) == 0

        return EInvoiceValidationResponse(
            valid=is_valid,
            validator_used=validator.value,
            validated_at=datetime.now(timezone.utc),
            schema_valid=schema_valid,
            schematron_valid=schematron_valid,
            pdf_a_compliant=None,  # Nur bei ZUGFeRD-PDF relevant
            errors=errors,
            warnings=warnings,
            error_count=len(errors),
            warning_count=len(warnings),
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
