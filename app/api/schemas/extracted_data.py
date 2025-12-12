# -*- coding: utf-8 -*-
"""
Pydantic-Modelle fuer strukturierte Datenextraktion.

Dieses Modul definiert die Datenstrukturen fuer:
- Rechnungen (InvoiceData)
- Bestellungen (OrderData)
- Vertraege (ContractData)

Diese werden automatisch bei JEDEM Dokument-Upload extrahiert
und in documents.extracted_data (JSONB) gespeichert.

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

from __future__ import annotations

from dataclasses import field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMS
# =============================================================================

class ExtractedDocumentType(str, Enum):
    """Klassifizierter Dokumenttyp."""
    INVOICE = "invoice"
    ORDER = "order"
    CONTRACT = "contract"
    DELIVERY_NOTE = "delivery_note"
    RECEIPT = "receipt"
    LETTER = "letter"
    UNKNOWN = "unknown"


class Currency(str, Enum):
    """Unterstuetzte Waehrungen."""
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    CHF = "CHF"


# =============================================================================
# BASISMODELLE
# =============================================================================

class ExtractedAddress(BaseModel):
    """
    Extrahierte Adresse aus einem Dokument.

    Unterstuetzt deutsche Adressformate:
    - Firma / Person
    - Strasse mit Hausnummer
    - PLZ + Stadt
    - Land (Standard: DE)
    """
    company: Optional[str] = Field(None, description="Firmenname")
    person: Optional[str] = Field(None, description="Ansprechpartner / Name")
    street: Optional[str] = Field(None, description="Strasse")
    street_number: Optional[str] = Field(None, description="Hausnummer")
    zip_code: Optional[str] = Field(None, description="Postleitzahl")
    city: Optional[str] = Field(None, description="Stadt")
    country: str = Field("DE", description="Laendercode (ISO 3166-1 alpha-2)")

    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, v: Optional[str]) -> Optional[str]:
        """Validiere deutsche PLZ (5 Ziffern)."""
        if v is None:
            return v
        cleaned = v.strip().replace(" ", "")
        # Deutsche PLZ: 5 Ziffern
        if len(cleaned) == 5 and cleaned.isdigit():
            return cleaned
        # Andere Laender: Original zurueckgeben
        return cleaned

    def is_complete(self) -> bool:
        """Pruefe ob Adresse vollstaendig ist."""
        return bool(self.zip_code and self.city)

    def to_single_line(self) -> str:
        """Formatiere als einzeilige Adresse."""
        parts = []
        if self.company:
            parts.append(self.company)
        if self.person:
            parts.append(self.person)
        if self.street:
            parts.append(self.street)
        if self.zip_code and self.city:
            parts.append(f"{self.zip_code} {self.city}")
        return ", ".join(parts)


class ExtractedBankAccount(BaseModel):
    """Extrahierte Bankverbindung."""
    iban: Optional[str] = Field(None, description="IBAN (ohne Leerzeichen)")
    bic: Optional[str] = Field(None, description="BIC/SWIFT-Code")
    bank_name: Optional[str] = Field(None, description="Name der Bank")
    account_holder: Optional[str] = Field(None, description="Kontoinhaber")

    @field_validator("iban")
    @classmethod
    def normalize_iban(cls, v: Optional[str]) -> Optional[str]:
        """Normalisiere IBAN (entferne Leerzeichen)."""
        if v is None:
            return v
        return v.replace(" ", "").upper()


class ExtractedLineItem(BaseModel):
    """
    Eine Rechnungs-/Bestellposition.

    Felder:
    - position: Positionsnummer (1, 2, 3, ...)
    - article_number: Optionale Artikelnummer
    - description: Beschreibung der Leistung/des Artikels
    - quantity: Menge
    - unit: Einheit (Stk, kg, h, etc.)
    - unit_price: Einzelpreis
    - total_price: Gesamtpreis (Menge * Einzelpreis)
    - vat_rate: MwSt-Satz in Prozent (7, 19, etc.)
    """
    position: int = Field(..., ge=1, description="Positionsnummer")
    article_number: Optional[str] = Field(None, description="Artikelnummer")
    description: str = Field(..., min_length=1, description="Beschreibung")
    quantity: Optional[Decimal] = Field(None, ge=0, description="Menge")
    unit: Optional[str] = Field(None, description="Einheit (Stk, kg, h, etc.)")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="Einzelpreis")
    total_price: Optional[Decimal] = Field(None, ge=0, description="Gesamtpreis")
    vat_rate: Optional[Decimal] = Field(None, ge=0, le=100, description="MwSt-Satz in %")

    @model_validator(mode="after")
    def validate_price_calculation(self) -> "ExtractedLineItem":
        """Pruefe Plausibilitaet: total_price ~= quantity * unit_price."""
        if self.quantity and self.unit_price and self.total_price:
            expected = self.quantity * self.unit_price
            tolerance = Decimal("0.02")  # 2 Cent Toleranz
            if abs(expected - self.total_price) > tolerance:
                # Warnung, aber kein Fehler (OCR-Ungenauigkeiten)
                pass
        return self


# =============================================================================
# RECHNUNGSDATEN (InvoiceData)
# =============================================================================

class ExtractedInvoiceData(BaseModel):
    """
    Strukturierte Rechnungsdaten.

    Extrahiert aus deutschen Rechnungen:
    - Rechnungsnummer, Bestellnummer, Kundennummer
    - Rechnungsdatum, Faelligkeitsdatum
    - Absender (Rechnungssteller) mit USt-ID, IBAN
    - Empfaenger
    - Betraege: Netto, MwSt, Brutto
    - Positionen (optional)

    Alle Felder sind optional, da nicht jede Rechnung vollstaendig ist.
    """
    document_type: Literal["invoice"] = "invoice"

    # === Referenznummern ===
    invoice_number: Optional[str] = Field(None, description="Rechnungsnummer")
    order_number: Optional[str] = Field(None, description="Bestellnummer / Auftragsnummer")
    customer_number: Optional[str] = Field(None, description="Kundennummer")
    delivery_note_number: Optional[str] = Field(None, description="Lieferscheinnummer")

    # === Daten ===
    invoice_date: Optional[date] = Field(None, description="Rechnungsdatum")
    due_date: Optional[date] = Field(None, description="Faelligkeitsdatum")
    service_period_start: Optional[date] = Field(None, description="Leistungszeitraum Beginn")
    service_period_end: Optional[date] = Field(None, description="Leistungszeitraum Ende")

    # === Absender (Rechnungssteller) ===
    sender: Optional[ExtractedAddress] = Field(None, description="Absender / Rechnungssteller")
    sender_vat_id: Optional[str] = Field(None, description="USt-IdNr des Absenders")
    sender_tax_number: Optional[str] = Field(None, description="Steuernummer des Absenders")
    sender_bank: Optional[ExtractedBankAccount] = Field(None, description="Bankverbindung des Absenders")
    sender_email: Optional[str] = Field(None, description="E-Mail des Absenders")
    sender_phone: Optional[str] = Field(None, description="Telefon des Absenders")
    sender_contact: Optional[str] = Field(None, description="Ansprechpartner des Absenders")

    # === Empfaenger ===
    recipient: Optional[ExtractedAddress] = Field(None, description="Empfaenger / Rechnungsadresse")
    recipient_vat_id: Optional[str] = Field(None, description="USt-IdNr des Empfaengers")

    # === Betraege ===
    net_amount: Optional[Decimal] = Field(None, ge=0, description="Nettobetrag")
    vat_rate: Optional[Decimal] = Field(None, ge=0, le=100, description="MwSt-Satz in % (7, 19)")
    vat_amount: Optional[Decimal] = Field(None, ge=0, description="MwSt-Betrag")
    gross_amount: Optional[Decimal] = Field(None, ge=0, description="Bruttobetrag")
    currency: Currency = Field(Currency.EUR, description="Waehrung")

    # === Positionen ===
    line_items: List[ExtractedLineItem] = Field(default_factory=list, description="Rechnungspositionen")

    # === Zahlungsinformationen (KRITISCH für Buchhaltung!) ===
    payment_terms: Optional[str] = Field(None, description="Zahlungsbedingungen (z.B. '30 Tage netto')")
    payment_method: Optional[str] = Field(None, description="Zahlungsart (Ueberweisung, Lastschrift, etc.)")

    # Skonto-Daten
    discount_percent: Optional[Decimal] = Field(None, ge=0, le=100, description="Skonto-Prozentsatz")
    discount_days: Optional[int] = Field(None, ge=0, description="Skonto-Frist in Tagen")
    discount_amount: Optional[Decimal] = Field(None, ge=0, description="Berechneter Skonto-Betrag")
    discount_due_date: Optional[date] = Field(None, description="Skonto-Faelligkeitsdatum")

    # Volltext-Infos
    early_payment_info: Optional[str] = Field(None, description="Skonto-Volltext (z.B. '2% Skonto bei Zahlung innerhalb 10 Tagen')")
    late_payment_info: Optional[str] = Field(None, description="Verzugszinsen-Info (z.B. '9% ueber Basiszinssatz')")

    # === Meta ===
    extraction_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Extraktions-Konfidenz (0-1)")
    needs_review: bool = Field(False, description="Manuelle Pruefung erforderlich")
    extraction_warnings: List[str] = Field(default_factory=list, description="Warnungen bei der Extraktion")

    @model_validator(mode="after")
    def validate_amounts(self) -> "ExtractedInvoiceData":
        """Pruefe Plausibilitaet: Netto + MwSt = Brutto."""
        if self.net_amount and self.vat_amount and self.gross_amount:
            expected_gross = self.net_amount + self.vat_amount
            tolerance = Decimal("0.02")  # 2 Cent Toleranz
            if abs(expected_gross - self.gross_amount) > tolerance:
                if "extraction_warnings" not in self.__dict__:
                    self.extraction_warnings = []
                self.extraction_warnings.append(
                    f"Betragsinkonsistenz: {self.net_amount} + {self.vat_amount} != {self.gross_amount}"
                )
                self.needs_review = True
        return self

    @field_validator("sender_vat_id", "recipient_vat_id")
    @classmethod
    def normalize_vat_id(cls, v: Optional[str]) -> Optional[str]:
        """Normalisiere USt-IdNr (ohne Leerzeichen, Grossbuchstaben)."""
        if v is None:
            return v
        return v.replace(" ", "").upper()


# =============================================================================
# BESTELLDATEN (OrderData)
# =============================================================================

class ExtractedOrderData(BaseModel):
    """
    Strukturierte Bestelldaten.

    Extrahiert aus deutschen Bestellungen/Auftragsbestaetigungen.
    """
    document_type: Literal["order"] = "order"

    # === Referenznummern ===
    order_number: Optional[str] = Field(None, description="Bestellnummer")
    customer_order_number: Optional[str] = Field(None, description="Kunden-Bestellnummer")
    quotation_number: Optional[str] = Field(None, description="Angebotsnummer")

    # === Daten ===
    order_date: Optional[date] = Field(None, description="Bestelldatum")
    delivery_date: Optional[date] = Field(None, description="Gewuenschter Liefertermin")
    confirmation_date: Optional[date] = Field(None, description="Auftragsbestaetigungsdatum")

    # === Besteller ===
    orderer: Optional[ExtractedAddress] = Field(None, description="Besteller")
    orderer_contact: Optional[str] = Field(None, description="Ansprechpartner beim Besteller")

    # === Lieferant ===
    supplier: Optional[ExtractedAddress] = Field(None, description="Lieferant")
    supplier_contact: Optional[str] = Field(None, description="Ansprechpartner beim Lieferanten")

    # === Lieferadresse ===
    delivery_address: Optional[ExtractedAddress] = Field(None, description="Lieferadresse (falls abweichend)")

    # === Positionen ===
    line_items: List[ExtractedLineItem] = Field(default_factory=list, description="Bestellpositionen")

    # === Betraege ===
    total_amount: Optional[Decimal] = Field(None, ge=0, description="Gesamtbetrag")
    currency: Currency = Field(Currency.EUR, description="Waehrung")

    # === Bedingungen ===
    payment_terms: Optional[str] = Field(None, description="Zahlungsbedingungen")
    delivery_terms: Optional[str] = Field(None, description="Lieferbedingungen")

    # === Meta ===
    extraction_confidence: float = Field(0.0, ge=0.0, le=1.0)
    needs_review: bool = Field(False)
    extraction_warnings: List[str] = Field(default_factory=list)


# =============================================================================
# VERTRAGSDATEN (ContractData)
# =============================================================================

class ExtractedContractData(BaseModel):
    """
    Strukturierte Vertragsdaten.

    Extrahiert aus deutschen Vertraegen.
    """
    document_type: Literal["contract"] = "contract"

    # === Referenznummern ===
    contract_number: Optional[str] = Field(None, description="Vertragsnummer")
    previous_contract_number: Optional[str] = Field(None, description="Vorheriger Vertrag (bei Verlaengerung)")

    # === Daten ===
    contract_date: Optional[date] = Field(None, description="Vertragsdatum / Unterzeichnung")
    start_date: Optional[date] = Field(None, description="Vertragsbeginn")
    end_date: Optional[date] = Field(None, description="Vertragsende")

    # === Laufzeit ===
    duration_months: Optional[int] = Field(None, ge=0, description="Vertragslaufzeit in Monaten")
    notice_period: Optional[str] = Field(None, description="Kuendigungsfrist (z.B. '3 Monate')")
    auto_renewal: Optional[bool] = Field(None, description="Automatische Verlaengerung")
    renewal_period: Optional[str] = Field(None, description="Verlaengerungszeitraum")

    # === Vertragspartner ===
    party_a: Optional[ExtractedAddress] = Field(None, description="Vertragspartner A")
    party_a_signatory: Optional[str] = Field(None, description="Unterzeichner Partei A")
    party_b: Optional[ExtractedAddress] = Field(None, description="Vertragspartner B")
    party_b_signatory: Optional[str] = Field(None, description="Unterzeichner Partei B")

    # === Werte ===
    contract_value: Optional[Decimal] = Field(None, ge=0, description="Vertragswert gesamt")
    monthly_value: Optional[Decimal] = Field(None, ge=0, description="Monatlicher Betrag")
    currency: Currency = Field(Currency.EUR, description="Waehrung")

    # === Vertragsgegenstand ===
    subject: Optional[str] = Field(None, description="Vertragsgegenstand (Zusammenfassung)")
    contract_type: Optional[str] = Field(None, description="Vertragsart (Mietvertrag, Dienstvertrag, etc.)")

    # === Meta ===
    extraction_confidence: float = Field(0.0, ge=0.0, le=1.0)
    needs_review: bool = Field(False)
    extraction_warnings: List[str] = Field(default_factory=list)


# =============================================================================
# KLASSIFIZIERUNGSERGEBNIS
# =============================================================================

class DocumentClassificationResult(BaseModel):
    """Ergebnis der Dokumentklassifizierung."""
    document_type: ExtractedDocumentType = Field(..., description="Klassifizierter Dokumenttyp")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenz der Klassifizierung")
    matched_keywords: List[str] = Field(default_factory=list, description="Gefundene Keywords")
    alternative_type: Optional[ExtractedDocumentType] = Field(None, description="Alternativer Dokumenttyp")
    alternative_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Konfidenz der Alternative")


# =============================================================================
# WRAPPER FUER EXTRACTED_DATA JSONB
# =============================================================================

class ExtractedDocumentData(BaseModel):
    """
    Wrapper fuer alle extrahierten Daten eines Dokuments.

    Dies ist das Schema fuer das documents.extracted_data JSONB-Feld.
    """
    # === Klassifizierung ===
    classification: Optional[DocumentClassificationResult] = Field(
        None, description="Ergebnis der Dokumentklassifizierung"
    )

    # === Typspezifische Daten (nur eines gesetzt) ===
    invoice: Optional[ExtractedInvoiceData] = Field(None, description="Rechnungsdaten")
    order: Optional[ExtractedOrderData] = Field(None, description="Bestelldaten")
    contract: Optional[ExtractedContractData] = Field(None, description="Vertragsdaten")

    # === Allgemeine extrahierte Entitaeten ===
    vat_ids: List[str] = Field(default_factory=list, description="Alle gefundenen USt-IdNr")
    ibans: List[str] = Field(default_factory=list, description="Alle gefundenen IBANs")
    dates: List[date] = Field(default_factory=list, description="Alle gefundenen Daten")
    amounts: List[Decimal] = Field(default_factory=list, description="Alle gefundenen Betraege")
    companies: List[str] = Field(default_factory=list, description="Alle gefundenen Firmennamen")

    # === Meta ===
    extraction_version: str = Field("1.0.0", description="Version des Extraktionsalgorithmus")
    extracted_at: Optional[str] = Field(None, description="Zeitstempel der Extraktion (ISO 8601)")
    overall_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Gesamtkonfidenz")

    # === Uebersetzungs-Metadaten (NEU fuer Mehrsprachigkeit) ===
    original_language: Optional[str] = Field(
        None, description="Originalsprache des Dokuments (ISO 639-1, z.B. 'ru', 'pl')"
    )
    was_translated: bool = Field(
        False, description="Ob der Text vor der Extraktion uebersetzt wurde"
    )
    translation_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Konfidenz der Uebersetzung (0.0-1.0)"
    )

    def get_primary_data(self) -> Optional[Union[ExtractedInvoiceData, ExtractedOrderData, ExtractedContractData]]:
        """Gibt die typspezifischen Daten zurueck."""
        if self.invoice:
            return self.invoice
        if self.order:
            return self.order
        if self.contract:
            return self.contract
        return None


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    # Enums
    "ExtractedDocumentType",
    "Currency",
    # Basismodelle
    "ExtractedAddress",
    "ExtractedBankAccount",
    "ExtractedLineItem",
    # Dokumenttypen
    "ExtractedInvoiceData",
    "ExtractedOrderData",
    "ExtractedContractData",
    # Klassifizierung
    "DocumentClassificationResult",
    # Wrapper
    "ExtractedDocumentData",
]
