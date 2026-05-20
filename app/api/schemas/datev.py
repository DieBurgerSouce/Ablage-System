# -*- coding: utf-8 -*-
"""
Pydantic-Modelle für DATEV Export API Endpoints.

Definiert Request/Response Schemas für:
- /api/v1/datev/config - Konfiguration verwalten
- /api/v1/datev/export - Buchungsstapel exportieren
- /api/v1/datev/export/preview - Export-Vorschau

Standards: DATEV Buchungsstapel CSV Format (Version 700)
"""

import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# VALIDATION PATTERNS
# =============================================================================

# EU VAT-ID: 2 Buchstaben Ländercode + 8-12 Zeichen (Ziffern/Buchstaben je nach Land)
# Beispiel: DE123456789, AT U12345678, FR 12345678901
VAT_ID_PATTERN = re.compile(r'^[A-Z]{2}[A-Z0-9]{2,13}$')

# IBAN: 2 Buchstaben + 2 Prüfziffern + 11-30 alphanumerische Zeichen
# Beispiel: DE89370400440532013000
IBAN_PATTERN = re.compile(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$')

# Kontonummer: 4-10 Ziffern
ACCOUNT_NUMBER_PATTERN = re.compile(r'^[0-9]{4,10}$')


# =============================================================================
# ENUMS
# =============================================================================

class Kontenrahmen(str, Enum):
    """Unterstützte Kontenrahmen."""
    SKR03 = "SKR03"
    SKR04 = "SKR04"


class DATEVExportStatus(str, Enum):
    """Export-Status."""
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class DATEVExportType(str, Enum):
    """Export-Typ."""
    BUCHUNGSSTAPEL = "buchungsstapel"
    STAMMDATEN = "stammdaten"


class DATEVTaxCode(str, Enum):
    """
    DATEV Steuerschlüssel (BU-Schlüssel).

    Vorsteuer (Eingangsrechnungen):
    - 9: 19% Vorsteuer
    - 8: 7% Vorsteuer
    - 94: Innergemeinschaftlicher Erwerb 19%
    - 93: Innergemeinschaftlicher Erwerb 7%
    - 91: Reverse Charge 19%

    Umsatzsteuer (Ausgangsrechnungen):
    - 3: 19% Umsatzsteuer
    - 2: 7% Umsatzsteuer
    - 10: Innergemeinschaftliche Lieferung
    - 13: Reverse Charge (Empfänger schuldet)
    """
    # Vorsteuer (Eingang)
    VST_19 = "9"
    VST_7 = "8"
    VST_EU_19 = "94"
    VST_EU_7 = "93"
    VST_RC = "91"
    VST_0 = "0"

    # Umsatzsteuer (Ausgang)
    UST_19 = "3"
    UST_7 = "2"
    UST_EU = "10"
    UST_RC = "13"
    UST_0 = "0"


class SollHaben(str, Enum):
    """Soll/Haben Kennzeichen."""
    SOLL = "S"
    HABEN = "H"


# =============================================================================
# CONFIGURATION SCHEMAS
# =============================================================================

class DATEVConfigurationBase(BaseModel):
    """Basis-Schema für DATEV-Konfiguration."""
    berater_nr: str = Field(
        ...,
        min_length=1,
        max_length=7,
        description="Beraternummer (max. 7-stellig, nur Ziffern)"
    )
    mandanten_nr: str = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Mandantennummer (max. 5-stellig, nur Ziffern)"
    )
    wj_beginn: date = Field(
        ...,
        description="Wirtschaftsjahr-Beginn (z.B. 2025-01-01)"
    )
    kontenrahmen: Kontenrahmen = Field(
        Kontenrahmen.SKR03,
        description="Kontenrahmen (SKR03 oder SKR04)"
    )

    @field_validator("berater_nr")
    @classmethod
    def validate_berater_nr(cls, v: str) -> str:
        """Validiere Beraternummer (nur Ziffern, auffüllen auf 7 Stellen)."""
        cleaned = v.strip()
        if not cleaned.isdigit():
            raise ValueError("Beraternummer darf nur Ziffern enthalten")
        return cleaned.zfill(7)

    @field_validator("mandanten_nr")
    @classmethod
    def validate_mandanten_nr(cls, v: str) -> str:
        """Validiere Mandantennummer (nur Ziffern, auffüllen auf 5 Stellen)."""
        cleaned = v.strip()
        if not cleaned.isdigit():
            raise ValueError("Mandantennummer darf nur Ziffern enthalten")
        return cleaned.zfill(5)

    @field_validator("wj_beginn")
    @classmethod
    def validate_wj_beginn(cls, v: date) -> date:
        """
        Validiere Wirtschaftsjahr-Beginn.

        MEDIUM-10 FIX: WJ-Beginn darf nicht in der Zukunft liegen
        und sollte ein realistisches Datum sein (nach Jahr 2000).
        """
        today = date.today()

        # Nicht in der Zukunft (mit Toleranz für nächstes Jahr)
        max_future_date = date(today.year + 1, 12, 31)
        if v > max_future_date:
            raise ValueError(
                f"Wirtschaftsjahr-Beginn darf nicht mehr als ein Jahr in der Zukunft liegen "
                f"(maximal {max_future_date.isoformat()})"
            )

        # Nicht zu weit in der Vergangenheit
        min_date = date(2000, 1, 1)
        if v < min_date:
            raise ValueError(
                f"Wirtschaftsjahr-Beginn muss nach dem {min_date.isoformat()} liegen"
            )

        return v


class DATEVConfigurationCreate(DATEVConfigurationBase):
    """Schema zum Erstellen einer DATEV-Konfiguration."""
    # Standardkonten Eingang
    incoming_expense_account: Optional[str] = Field(
        None,
        max_length=10,
        description="Aufwandskonto für Eingangsrechnungen (z.B. 4200)"
    )
    incoming_creditor_account: Optional[str] = Field(
        None,
        max_length=10,
        description="Kreditorenkonto für Eingangsrechnungen (z.B. 70000)"
    )

    # Standardkonten Ausgang
    outgoing_revenue_account: Optional[str] = Field(
        None,
        max_length=10,
        description="Erlöskonto für Ausgangsrechnungen (z.B. 8400)"
    )
    outgoing_debtor_account: Optional[str] = Field(
        None,
        max_length=10,
        description="Debitorenkonto für Ausgangsrechnungen (z.B. 10000)"
    )

    # Sammelkonten
    sammelkonto_kreditoren: str = Field(
        "1600",
        max_length=10,
        description="Sammelkonto Kreditoren (Standard: 1600)"
    )
    sammelkonto_debitoren: str = Field(
        "1400",
        max_length=10,
        description="Sammelkonto Debitoren (Standard: 1400)"
    )

    # Optionen
    sachkontenlange: int = Field(
        4,
        ge=4,
        le=8,
        description="Länge der Sachkonten (4-8 Stellen)"
    )
    buchungstext_format: str = Field(
        "{invoice_number}",
        max_length=100,
        description="Format für Buchungstext (Platzhalter: {invoice_number}, {sender})"
    )
    is_default: bool = Field(
        False,
        description="Als Standard-Konfiguration verwenden"
    )


class DATEVConfigurationUpdate(BaseModel):
    """Schema zum Aktualisieren einer DATEV-Konfiguration."""
    berater_nr: Optional[str] = Field(None, max_length=7)
    mandanten_nr: Optional[str] = Field(None, max_length=5)
    wj_beginn: Optional[date] = None
    kontenrahmen: Optional[Kontenrahmen] = None
    incoming_expense_account: Optional[str] = Field(None, max_length=10)
    incoming_creditor_account: Optional[str] = Field(None, max_length=10)
    outgoing_revenue_account: Optional[str] = Field(None, max_length=10)
    outgoing_debtor_account: Optional[str] = Field(None, max_length=10)
    sammelkonto_kreditoren: Optional[str] = Field(None, max_length=10)
    sammelkonto_debitoren: Optional[str] = Field(None, max_length=10)
    sachkontenlange: Optional[int] = Field(None, ge=4, le=8)
    buchungstext_format: Optional[str] = Field(None, max_length=100)
    is_default: Optional[bool] = None

    @field_validator("wj_beginn")
    @classmethod
    def validate_wj_beginn(cls, v: Optional[date]) -> Optional[date]:
        """Validiere Wirtschaftsjahr-Beginn (gleiche Regeln wie Base)."""
        if v is None:
            return None

        today = date.today()

        # Nicht in der Zukunft (mit Toleranz für nächstes Jahr)
        max_future_date = date(today.year + 1, 12, 31)
        if v > max_future_date:
            raise ValueError(
                f"Wirtschaftsjahr-Beginn darf nicht mehr als ein Jahr in der Zukunft liegen "
                f"(maximal {max_future_date.isoformat()})"
            )

        # Nicht zu weit in der Vergangenheit
        min_date = date(2000, 1, 1)
        if v < min_date:
            raise ValueError(
                f"Wirtschaftsjahr-Beginn muss nach dem {min_date.isoformat()} liegen"
            )

        return v


class DATEVConfigurationResponse(DATEVConfigurationBase):
    """Response-Schema für DATEV-Konfiguration."""
    id: UUID
    incoming_expense_account: Optional[str] = None
    incoming_creditor_account: Optional[str] = None
    outgoing_revenue_account: Optional[str] = None
    outgoing_debtor_account: Optional[str] = None
    sammelkonto_kreditoren: str
    sammelkonto_debitoren: str
    sachkontenlange: int
    buchungstext_format: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# VENDOR MAPPING SCHEMAS
# =============================================================================

class DATEVVendorMappingCreate(BaseModel):
    """Schema zum Erstellen eines Vendor-Mappings."""
    vendor_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Firmenname (Fuzzy-Match)"
    )
    vendor_vat_id: Optional[str] = Field(
        None,
        max_length=50,
        description="USt-IdNr (exakter Match, Format: DE123456789)"
    )
    verify_vat_with_vies: bool = Field(
        False,
        description="USt-IdNr gegen EU VIES-Datenbank validieren (optional)"
    )
    vendor_iban: Optional[str] = Field(
        None,
        max_length=34,
        description="IBAN (exakter Match, Format: DE89370400440532013000)"
    )
    business_entity_id: Optional[UUID] = Field(
        None,
        description="Verknüpfter Geschäftspartner"
    )
    expense_account: str = Field(
        ...,
        max_length=10,
        description="Aufwandskonto (4-10 Ziffern, z.B. 4200)"
    )
    creditor_account: Optional[str] = Field(
        None,
        max_length=10,
        description="Personenkonto/Kreditor (4-10 Ziffern, z.B. 70001)"
    )
    cost_center: Optional[str] = Field(
        None,
        max_length=20,
        description="Kostenstelle"
    )
    cost_object: Optional[str] = Field(
        None,
        max_length=20,
        description="Kostenträger"
    )

    @field_validator("vendor_vat_id")
    @classmethod
    def validate_vat_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiere USt-IdNr Format (EU VAT-ID)."""
        if v is None:
            return None
        # Whitespace und Sonderzeichen entfernen
        cleaned = re.sub(r'[\s\-.]', '', v.upper())
        if not VAT_ID_PATTERN.match(cleaned):
            raise ValueError(
                "Ungültige USt-IdNr. Format: 2 Buchstaben Ländercode + 8-12 Zeichen "
                "(z.B. DE123456789, ATU12345678)"
            )
        return cleaned

    @field_validator("vendor_iban")
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        """Validiere IBAN Format (basic, ohne Prüfsumme)."""
        if v is None:
            return None
        # Whitespace entfernen und uppercase
        cleaned = re.sub(r'\s', '', v.upper())
        if not IBAN_PATTERN.match(cleaned):
            raise ValueError(
                "Ungültige IBAN. Format: 2 Buchstaben + 2 Prüfziffern + Kontonummer "
                "(z.B. DE89370400440532013000)"
            )
        return cleaned

    @field_validator("expense_account", "creditor_account")
    @classmethod
    def validate_account_number(cls, v: Optional[str]) -> Optional[str]:
        """Validiere Kontonummer (nur Ziffern, 4-10 Stellen)."""
        if v is None:
            return None
        cleaned = v.strip()
        if not ACCOUNT_NUMBER_PATTERN.match(cleaned):
            raise ValueError(
                "Ungültige Kontonummer. Muss 4-10 Ziffern enthalten (z.B. 4200, 70001)"
            )
        return cleaned


class DATEVVendorMappingUpdate(BaseModel):
    """Schema zum Aktualisieren eines Vendor-Mappings."""
    vendor_name: Optional[str] = Field(None, max_length=255)
    vendor_vat_id: Optional[str] = Field(None, max_length=50)
    vendor_iban: Optional[str] = Field(None, max_length=34)
    business_entity_id: Optional[UUID] = None
    expense_account: Optional[str] = Field(None, max_length=10)
    creditor_account: Optional[str] = Field(None, max_length=10)
    cost_center: Optional[str] = Field(None, max_length=20)
    cost_object: Optional[str] = Field(None, max_length=20)

    # Validators (gleiche wie in Create)
    @field_validator("vendor_vat_id")
    @classmethod
    def validate_vat_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiere USt-IdNr Format (EU VAT-ID)."""
        if v is None:
            return None
        cleaned = re.sub(r'[\s\-.]', '', v.upper())
        if not VAT_ID_PATTERN.match(cleaned):
            raise ValueError(
                "Ungültige USt-IdNr. Format: 2 Buchstaben Ländercode + 8-12 Zeichen"
            )
        return cleaned

    @field_validator("vendor_iban")
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        """Validiere IBAN Format (basic, ohne Prüfsumme)."""
        if v is None:
            return None
        cleaned = re.sub(r'\s', '', v.upper())
        if not IBAN_PATTERN.match(cleaned):
            raise ValueError(
                "Ungültige IBAN. Format: 2 Buchstaben + 2 Prüfziffern + Kontonummer"
            )
        return cleaned

    @field_validator("expense_account", "creditor_account")
    @classmethod
    def validate_account_number(cls, v: Optional[str]) -> Optional[str]:
        """Validiere Kontonummer (nur Ziffern, 4-10 Stellen)."""
        if v is None:
            return None
        cleaned = v.strip()
        if not ACCOUNT_NUMBER_PATTERN.match(cleaned):
            raise ValueError(
                "Ungültige Kontonummer. Muss 4-10 Ziffern enthalten"
            )
        return cleaned


class DATEVVendorMappingResponse(BaseModel):
    """Response-Schema für Vendor-Mapping."""
    id: UUID
    config_id: UUID
    vendor_name: Optional[str] = None
    vendor_vat_id: Optional[str] = None
    vendor_iban: Optional[str] = None
    business_entity_id: Optional[UUID] = None
    expense_account: str
    creditor_account: Optional[str] = None
    cost_center: Optional[str] = None
    cost_object: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# EXPORT SCHEMAS
# =============================================================================

class DATEVExportRequest(BaseModel):
    """Request für DATEV-Export."""
    config_id: Optional[UUID] = Field(
        None,
        description="Konfiguration (falls nicht angegeben: Standard-Konfiguration)"
    )
    document_ids: Optional[List[UUID]] = Field(
        None,
        description="Spezifische Dokumente exportieren (optional)"
    )
    period_from: Optional[date] = Field(
        None,
        description="Zeitraum von (Rechnungsdatum)"
    )
    period_to: Optional[date] = Field(
        None,
        description="Zeitraum bis (Rechnungsdatum)"
    )
    include_already_exported: bool = Field(
        False,
        description="Bereits exportierte Dokumente einschließen"
    )
    export_type: DATEVExportType = Field(
        DATEVExportType.BUCHUNGSSTAPEL,
        description="Export-Typ"
    )


class DATEVBuchungsstapelEntry(BaseModel):
    """
    Eine Zeile im DATEV Buchungsstapel.

    Entspricht einer Buchungszeile gemäß DATEV-Format Version 700.
    """
    umsatz: Decimal = Field(..., description="Betrag (immer positiv)")
    soll_haben: SollHaben = Field(..., description="S = Soll, H = Haben")
    wkz_umsatz: str = Field("EUR", description="Währungskennzeichen")
    kurs: Optional[Decimal] = Field(None, description="Wechselkurs (bei Fremdwährung)")
    konto: str = Field(..., description="Sachkonto (z.B. 4200)")
    gegenkonto: str = Field(..., description="Gegenkonto (z.B. 70000)")
    bu_schluessel: Optional[str] = Field(None, description="Steuerschlüssel (BU-Schlüssel)")
    belegdatum: date = Field(..., description="Belegdatum")
    belegfeld_1: str = Field(..., description="Rechnungsnummer (max. 36 Zeichen)")
    belegfeld_2: Optional[str] = Field(None, description="Zusatzinfo (max. 12 Zeichen)")
    skonto: Optional[Decimal] = Field(None, description="Skonto-Betrag")
    buchungstext: str = Field(..., max_length=60, description="Buchungstext")

    # Optionale Felder
    kostenstelle_1: Optional[str] = Field(None, max_length=20)
    kostenstelle_2: Optional[str] = Field(None, max_length=20)
    kostentraeger: Optional[str] = Field(None, max_length=20)
    festschreibung: Optional[str] = Field(None, description="Festschreibungskennzeichen")


class DATEVExportPreview(BaseModel):
    """Vorschau eines DATEV-Exports."""
    document_count: int = Field(..., description="Anzahl exportierbarer Dokumente")
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    total_amount: Decimal = Field(..., description="Gesamtbetrag")
    sample_entries: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Beispiel-Buchungen (max. 10)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnungen (z.B. fehlende Daten)"
    )
    skipped_count: int = Field(0, description="Anzahl übersprungener Dokumente")
    skipped_reasons: Dict[str, int] = Field(
        default_factory=dict,
        description="Gründe für Übersprungene ({grund: anzahl})"
    )


class DATEVExportResponse(BaseModel):
    """Response nach erfolgreichem DATEV-Export."""
    id: UUID
    filename: str
    export_type: DATEVExportType
    document_count: int
    file_size_bytes: int
    status: DATEVExportStatus
    content_hash: str
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    exported_at: datetime
    download_url: Optional[str] = None

    # Statistiken
    included_documents: List[UUID] = Field(default_factory=list)
    skipped_documents: List[UUID] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DATEVExportHistoryItem(BaseModel):
    """Ein Eintrag in der Export-Historie."""
    id: UUID
    export_type: DATEVExportType
    filename: str
    document_count: int
    status: DATEVExportStatus
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    exported_at: datetime

    @field_validator("export_type", mode="before")
    @classmethod
    def convert_export_type(cls, v: Any) -> DATEVExportType:
        """Konvertiert String zu Enum falls nötig."""
        if isinstance(v, str):
            return DATEVExportType(v)
        return v

    @field_validator("status", mode="before")
    @classmethod
    def convert_status(cls, v: Any) -> DATEVExportStatus:
        """Konvertiert String zu Enum falls nötig."""
        if isinstance(v, str):
            return DATEVExportStatus(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class DATEVExportHistoryResponse(BaseModel):
    """Paginierte Export-Historie."""
    items: List[DATEVExportHistoryItem]
    total: int
    page: int
    page_size: int


# =============================================================================
# KONTENRAHMEN INFO
# =============================================================================

class KontenrahmenAccount(BaseModel):
    """Ein Konto im Kontenrahmen."""
    nummer: str = Field(..., description="Kontonummer")
    bezeichnung: str = Field(..., description="Kontobezeichnung")
    kategorie: str = Field(..., description="Kontokategorie")


class KontenrahmenInfo(BaseModel):
    """Informationen über einen Kontenrahmen."""
    name: Kontenrahmen
    beschreibung: str
    standard_konten: Dict[str, str] = Field(
        ...,
        description="Standard-Konten (z.B. {'wareneingang_19': '3200'})"
    )
    verfuegbare_kategorien: List[str] = Field(
        ...,
        description="Verfügbare Kontokategorien"
    )
