# -*- coding: utf-8 -*-
"""
Pydantic-Modelle fuer E-Invoice API Endpoints.

Definiert Request/Response Schemas fuer:
- /api/v1/einvoice/parse
- /api/v1/einvoice/generate/zugferd
- /api/v1/einvoice/generate/xrechnung
- /api/v1/einvoice/validate

Standards: ZUGFeRD 2.x, XRechnung 3.0.2
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .extracted_data import ExtractedInvoiceData


# =============================================================================
# ENUMS
# =============================================================================

class ZUGFeRDProfile(str, Enum):
    """ZUGFeRD/Factur-X Profil-Stufen."""
    MINIMUM = "MINIMUM"
    BASIC = "BASIC"
    BASIC_WL = "BASIC_WL"
    EN16931 = "EN16931"
    EXTENDED = "EXTENDED"
    XRECHNUNG = "XRECHNUNG"


class XRechnungSyntax(str, Enum):
    """XRechnung XML-Syntax Varianten."""
    CII = "CII"  # UN/CEFACT Cross Industry Invoice
    UBL = "UBL"  # Universal Business Language 2.1


class ValidatorType(str, Enum):
    """Verfuegbare Validatoren."""
    KOSIT = "kosit"
    MUSTANG = "mustang"
    FACTURX = "facturx"
    ALL = "all"


class EInvoiceFormatDetected(str, Enum):
    """Erkanntes E-Rechnungsformat."""
    ZUGFERD_1_0 = "zugferd_1.0"
    ZUGFERD_2_0 = "zugferd_2.0"
    ZUGFERD_2_1 = "zugferd_2.1"
    ZUGFERD_2_2 = "zugferd_2.2"
    ZUGFERD_2_3 = "zugferd_2.3"
    XRECHNUNG_2_0 = "xrechnung_2.0"
    XRECHNUNG_2_1 = "xrechnung_2.1"
    XRECHNUNG_2_2 = "xrechnung_2.2"
    XRECHNUNG_2_3 = "xrechnung_2.3"
    XRECHNUNG_3_0 = "xrechnung_3.0"
    FACTURX = "facturx"
    UNKNOWN = "unknown"


# =============================================================================
# VALIDATION RESULTS
# =============================================================================

class ValidationError(BaseModel):
    """Einzelner Validierungsfehler."""
    code: str = Field(..., description="Fehlercode (z.B. 'BR-DE-1')")
    location: str = Field(..., description="XPath oder Zeilennummer")
    message: str = Field(..., description="Fehlerbeschreibung")
    severity: str = Field("error", description="Schweregrad: 'error' oder 'fatal'")


class ValidationWarning(BaseModel):
    """Einzelne Validierungswarnung."""
    code: str = Field(..., description="Warnungscode")
    location: str = Field(..., description="XPath oder Zeilennummer")
    message: str = Field(..., description="Warnungsbeschreibung")


# =============================================================================
# PARSE REQUEST/RESPONSE
# =============================================================================

class EInvoiceParseRequest(BaseModel):
    """Request fuer E-Invoice Parsing (optional, meist via multipart/form-data)."""
    extract_to_document: bool = Field(
        False,
        description="Sofort als Dokument in DB speichern"
    )


class EInvoiceParseResponse(BaseModel):
    """Response nach erfolgreichem E-Invoice Parsing."""
    success: bool = Field(..., description="Parsing erfolgreich")
    format_detected: EInvoiceFormatDetected = Field(
        ...,
        description="Erkanntes E-Rechnungsformat"
    )
    profile: Optional[ZUGFeRDProfile] = Field(
        None,
        description="Erkanntes Profil (bei ZUGFeRD)"
    )
    version: Optional[str] = Field(
        None,
        description="Erkannte Version (z.B. '2.3.3', '3.0.2')"
    )
    invoice_data: ExtractedInvoiceData = Field(
        ...,
        description="Extrahierte Rechnungsdaten"
    )
    xml_content: Optional[str] = Field(
        None,
        description="Extrahiertes XML (wenn vorhanden)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnungen beim Parsen"
    )
    document_id: Optional[UUID] = Field(
        None,
        description="Dokument-ID (wenn extract_to_document=True)"
    )
    einvoice_id: Optional[UUID] = Field(
        None,
        description="E-Invoice Datensatz ID"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "format_detected": "zugferd_2.3",
                "profile": "EN16931",
                "version": "2.3.3",
                "invoice_data": {
                    "document_type": "invoice",
                    "invoice_number": "RE-2024-00123",
                    "invoice_date": "2024-12-17",
                    "net_amount": 1000.00,
                    "vat_rate": 19.0,
                    "vat_amount": 190.00,
                    "gross_amount": 1190.00
                },
                "warnings": []
            }
        }


# =============================================================================
# GENERATE REQUEST/RESPONSE
# =============================================================================

class ZUGFeRDGenerateRequest(BaseModel):
    """Request fuer ZUGFeRD PDF-Generierung."""
    document_id: UUID = Field(..., description="Dokument-ID als Basis")
    profile: ZUGFeRDProfile = Field(
        ZUGFeRDProfile.EN16931,
        description="ZUGFeRD-Profil"
    )
    attach_original_pdf: bool = Field(
        True,
        description="Original-PDF als Basis verwenden (falls vorhanden)"
    )
    validate_before_generate: bool = Field(
        True,
        description="Daten vor Generierung validieren"
    )


class XRechnungGenerateRequest(BaseModel):
    """Request fuer XRechnung XML-Generierung."""
    document_id: UUID = Field(..., description="Dokument-ID als Basis")
    syntax: XRechnungSyntax = Field(
        XRechnungSyntax.CII,
        description="XML-Syntax: CII (UN/CEFACT) oder UBL"
    )
    validate_before_return: bool = Field(
        True,
        description="Mit KoSIT validieren vor Rueckgabe"
    )


class EInvoiceGenerateResponse(BaseModel):
    """Response nach E-Invoice Generierung."""
    success: bool = Field(..., description="Generierung erfolgreich")
    format: str = Field(..., description="Generiertes Format")
    profile: Optional[str] = Field(None, description="Verwendetes Profil")
    einvoice_id: UUID = Field(..., description="E-Invoice Datensatz ID")
    document_id: UUID = Field(..., description="Zugehoeriges Dokument")
    download_url: str = Field(..., description="URL zum Download")
    file_size_bytes: int = Field(..., description="Dateigroesse")
    validation_result: Optional["EInvoiceValidationResponse"] = Field(
        None,
        description="Validierungsergebnis (wenn validate=True)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnungen bei der Generierung"
    )
    generated_at: datetime = Field(..., description="Generierungszeitpunkt")


# =============================================================================
# VALIDATION REQUEST/RESPONSE
# =============================================================================

class EInvoiceValidateRequest(BaseModel):
    """Request fuer E-Invoice Validierung."""
    document_id: Optional[UUID] = Field(
        None,
        description="Dokument-ID (wenn bereits in DB)"
    )
    validator: ValidatorType = Field(
        ValidatorType.KOSIT,
        description="Zu verwendender Validator"
    )


class EInvoiceValidationResponse(BaseModel):
    """Response nach E-Invoice Validierung."""
    valid: bool = Field(..., description="Gesamtergebnis: Gueltig")
    validator_used: str = Field(..., description="Verwendeter Validator")
    validated_at: datetime = Field(..., description="Validierungszeitpunkt")

    # Detaillierte Ergebnisse
    schema_valid: bool = Field(..., description="XSD Schema-Validierung bestanden")
    schematron_valid: bool = Field(..., description="Schematron Business Rules bestanden")
    pdf_a_compliant: Optional[bool] = Field(
        None,
        description="PDF/A-3 Konformitaet (nur bei ZUGFeRD)"
    )

    # Fehler und Warnungen
    errors: List[ValidationError] = Field(
        default_factory=list,
        description="Validierungsfehler"
    )
    warnings: List[ValidationWarning] = Field(
        default_factory=list,
        description="Validierungswarnungen"
    )
    error_count: int = Field(0, description="Anzahl Fehler")
    warning_count: int = Field(0, description="Anzahl Warnungen")

    # Optionale Details
    validation_report_url: Optional[str] = Field(
        None,
        description="URL zum detaillierten Validierungsbericht"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "validator_used": "kosit",
                "validated_at": "2024-12-17T14:30:00Z",
                "schema_valid": True,
                "schematron_valid": True,
                "pdf_a_compliant": True,
                "errors": [],
                "warnings": [],
                "error_count": 0,
                "warning_count": 0
            }
        }


# =============================================================================
# FORMATS RESPONSE
# =============================================================================

class SupportedFormat(BaseModel):
    """Beschreibung eines unterstuetzten Formats."""
    id: str = Field(..., description="Format-ID")
    name: str = Field(..., description="Anzeigename")
    description: str = Field(..., description="Beschreibung")
    supported_profiles: Optional[List[str]] = Field(
        None,
        description="Unterstuetzte Profile (bei ZUGFeRD)"
    )
    b2g_compatible: bool = Field(..., description="Fuer Behoerden geeignet (B2G)")


class EInvoiceFormatsResponse(BaseModel):
    """Response mit allen unterstuetzten Formaten."""
    formats: List[SupportedFormat] = Field(
        default_factory=list,
        description="Liste unterstuetzter Formate"
    )
    default_format: str = Field(
        "zugferd",
        description="Standard-Format"
    )
    default_profile: str = Field(
        "EN16931",
        description="Standard-Profil"
    )


# =============================================================================
# CONVERT REQUEST/RESPONSE
# =============================================================================

class EInvoiceConvertRequest(BaseModel):
    """Request fuer Format-Konvertierung."""
    source_document_id: Optional[UUID] = Field(
        None,
        description="Quell-Dokument ID"
    )
    target_format: str = Field(..., description="Zielformat")
    target_profile: Optional[str] = Field(None, description="Zielprofil")


class EInvoiceConvertResponse(BaseModel):
    """Response nach Format-Konvertierung."""
    success: bool
    source_format: str
    target_format: str
    einvoice_id: UUID
    download_url: str
    warnings: List[str] = Field(default_factory=list)


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    # Enums
    "ZUGFeRDProfile",
    "XRechnungSyntax",
    "ValidatorType",
    "EInvoiceFormatDetected",
    # Validation
    "ValidationError",
    "ValidationWarning",
    # Parse
    "EInvoiceParseRequest",
    "EInvoiceParseResponse",
    # Generate
    "ZUGFeRDGenerateRequest",
    "XRechnungGenerateRequest",
    "EInvoiceGenerateResponse",
    # Validate
    "EInvoiceValidateRequest",
    "EInvoiceValidationResponse",
    # Formats
    "SupportedFormat",
    "EInvoiceFormatsResponse",
    # Convert
    "EInvoiceConvertRequest",
    "EInvoiceConvertResponse",
]
