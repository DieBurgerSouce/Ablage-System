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
    """Klassifizierter Dokumenttyp - 15 Types fuer Enterprise-Klassifikation.

    Phase 1.2: Erweitert um Bank Statement, Tax Document, Dunning Letter,
    Purchase Order, Credit Note.

    Synchronisiert mit app.db.models.DocumentType.
    """
    # === RECHNUNGSWESEN ===
    INVOICE = "invoice"              # Rechnung (Ein-/Ausgang)
    CREDIT_NOTE = "credit_note"      # Gutschrift
    RECEIPT = "receipt"              # Quittung/Kassenbon
    DUNNING = "dunning"              # Mahnung (Zahlungserinnerung bis 3. Mahnung)

    # === BESTELLWESEN ===
    ORDER = "order"                  # Bestellung (allgemein)
    PURCHASE_ORDER = "purchase_order"  # Bestellauftrag (formell)
    OFFER = "offer"                  # Angebot
    DELIVERY_NOTE = "delivery_note"  # Lieferschein

    # === VERTRAEGE & DOKUMENTE ===
    CONTRACT = "contract"            # Vertrag
    FORM = "form"                    # Formular
    LETTER = "letter"                # Brief/Korrespondenz
    REPORT = "report"                # Bericht

    # === FINANZ & STEUER ===
    BANK_STATEMENT = "bank_statement"  # Kontoauszug
    TAX_DOCUMENT = "tax_document"      # Steuerdokument (USt-Voranmeldung, etc.)

    # === SONSTIGES ===
    OTHER = "other"                  # Sonstiges (bekannt aber nicht kategorisiert)
    UNKNOWN = "unknown"              # Unbekannt (Klassifikation fehlgeschlagen)


class Currency(str, Enum):
    """Unterstuetzte Waehrungen."""
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    CHF = "CHF"


class AmountSource(str, Enum):
    """Quelle eines extrahierten Betrags fuer Audit-Trail."""
    DOCUMENT = "document"      # Direkt aus Rechnung extrahiert
    COMPUTED = "computed"      # Berechnet (z.B. gross = net + vat)
    NOT_FOUND = "not_found"    # Nicht gefunden


class ValidationStatus(str, Enum):
    """Status einer Validierungspruefung."""
    VALID = "valid"
    INVALID = "invalid"
    SKIPPED = "skipped"        # Nicht durchgefuehrt (fehlende Daten)
    PENDING = "pending"        # Async-Pruefung ausstehend (z.B. VIES)


class InvoiceDirection(str, Enum):
    """
    Richtung einer Rechnung basierend auf Admin-Firmendaten.

    INCOMING: Eingangsrechnung - Empfaenger ist die eigene Firma
    OUTGOING: Ausgangsrechnung - Absender ist die eigene Firma
    UNKNOWN: Keine eindeutige Zuordnung moeglich
    """
    INCOMING = "incoming"      # Eingangsrechnung (an uns)
    OUTGOING = "outgoing"      # Ausgangsrechnung (von uns)
    UNKNOWN = "unknown"        # Nicht bestimmbar


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

    def _clean_company_name(self, name: str) -> str:
        """Bereinige OCR-Artefakte aus Firmennamen.

        OCR extrahiert manchmal:
        'ALPAC Sales - Invoice kunststof bakken en pallets Alpac - kunststof...'

        Problem: Logo + Dokumenttyp + echter Firmenname vermischt.
        Loesung:
        1. Entferne Dokumenttyp-Indikatoren (Sales - Invoice, Rechnung, etc.)
        2. Finde duplizierten Firmennamen und behalte den besseren Teil
        """
        if not name or len(name) < 5:
            return name

        # 1. Entferne Dokumenttyp-Indikatoren aus dem Namen
        doc_type_patterns = [
            "Sales - Invoice",
            "Sales-Invoice",
            "Invoice -",
            "- Invoice",
            "Rechnung -",
            "- Rechnung",
        ]
        cleaned = name
        for pattern in doc_type_patterns:
            if pattern.lower() in cleaned.lower():
                # Finde Position und entferne
                idx = cleaned.lower().find(pattern.lower())
                cleaned = cleaned[:idx] + cleaned[idx + len(pattern):]
                cleaned = cleaned.strip(' -')

        # 2. Deduplizierung: Wenn erstes Wort spaeter nochmal auftaucht
        words = cleaned.split()
        if len(words) >= 4:
            first_word_lower = words[0].lower()
            for i in range(2, len(words)):
                if words[i].lower() == first_word_lower:
                    # Duplikat gefunden
                    first_part = ' '.join(words[:i]).rstrip(' -')
                    second_part = ' '.join(words[i:])

                    # Praeferiere den Teil mit Rechtsform-Suffix
                    if any(suffix in second_part for suffix in ['BV', 'B.V.', 'GmbH', 'AG', 'Ltd', 'Inc', 'e.V.']):
                        return second_part
                    if any(suffix in first_part for suffix in ['BV', 'B.V.', 'GmbH', 'AG', 'Ltd', 'Inc', 'e.V.']):
                        return first_part

                    # Praeferiere "Name - Beschreibung" Format (echter Firmenname)
                    # "Alpac - kunststof" ist besser als "ALPAC kunststof"
                    if ' - ' in second_part:
                        return second_part

                    return first_part

        return cleaned if cleaned else name

    def to_multiline(self) -> List[str]:
        """Formatiere als mehrzeilige Adresse fuer PDF."""
        lines = []

        # Bereinigung: OCR-Artefakte entfernen (Logo, Dokumenttyp, Duplikate)
        company_text = self._clean_company_name(self.company or "")
        person_text = self.person or ""

        # Deduplizierung zwischen company und person
        if company_text and person_text:
            c_lower = company_text.lower().strip()
            p_lower = person_text.lower().strip()

            # 1. Exakter Substring-Check
            if p_lower in c_lower or c_lower in p_lower:
                person_text = ""
            else:
                # 2. Wort-basierte Pruefung fuer aehnliche Namen
                c_words = set(c_lower.split())
                p_words = set(p_lower.split())

                # Wenn erstes Wort gleich -> wahrscheinlich Duplikat
                c_first = c_lower.split()[0] if c_lower else ""
                p_first = p_lower.split()[0] if p_lower else ""

                if c_first == p_first and len(c_first) > 2:
                    person_text = ""
                # Oder: >50% Wort-Ueberlappung
                elif c_words and p_words:
                    overlap = len(c_words & p_words)
                    smaller = min(len(c_words), len(p_words))
                    if smaller > 0 and overlap / smaller >= 0.5:
                        person_text = ""

        if company_text:
            lines.append(company_text)
        if person_text:
            lines.append(person_text)

        # Strasse mit Hausnummer kombinieren
        street_line = self.street or ""
        if self.street_number:
            street_line = f"{street_line} {self.street_number}".strip()
        if street_line:
            lines.append(street_line)

        # PLZ und Stadt (immer mit Laendercode fuer Konsistenz)
        if self.zip_code or self.city:
            city_line = f"{self.zip_code or ''} {self.city or ''}".strip()
            country_code = self.country.upper() if self.country else "DE"
            city_line = f"{city_line}, {country_code}"
            lines.append(city_line)

        return lines


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


class ExtractionValidations(BaseModel):
    """
    Strukturierte Validierungsergebnisse fuer Audit und Qualitaetssicherung.

    Enthaelt Pruefungsergebnisse fuer:
    - IBAN-Checksum (MOD-97)
    - IBAN-Land vs. Absender-Land
    - USt-IdNr-Land vs. Absender-Land
    - Summen-Konsistenz (Line Items vs. Netto)
    - Field-Level Confidence
    """
    # === IBAN-Validierung ===
    iban_checksum_valid: Optional[bool] = Field(
        None, description="True wenn IBAN MOD-97 Checksum korrekt"
    )
    iban_country_match: Optional[bool] = Field(
        None, description="True wenn IBAN-Land = Absender-Land"
    )

    # === USt-IdNr-Validierung ===
    vat_country_match: Optional[bool] = Field(
        None, description="True wenn USt-IdNr-Land = Absender-Land"
    )
    vies_vat_valid: Optional[bool] = Field(
        None, description="True wenn VIES-Abfrage erfolgreich (null = nicht geprueft)"
    )

    # === Summen-Konsistenz ===
    sums_match: Optional[bool] = Field(
        None, description="True wenn Summe Line Items ~ Nettobetrag"
    )
    sums_difference: Optional[Decimal] = Field(
        None, description="Differenz falls sums_match=False"
    )

    # === Field-Level Confidence ===
    field_confidence: Dict[str, float] = Field(
        default_factory=dict,
        description="Konfidenz pro extrahiertem Feld (0.0-1.0)"
    )


class TaxBreakdownItem(BaseModel):
    """
    MwSt-Aufschluesselung fuer eine Steuerkategorie.

    Erforderlich fuer ZUGFeRD/XRechnung wenn mehrere MwSt-Saetze
    auf einer Rechnung vorkommen (z.B. 7% + 19%).
    """
    tax_category_code: str = Field(
        ...,
        description="UN/CEFACT Tax Category Code (S=Standard, Z=Zero, E=Exempt, AE=Reverse Charge)"
    )
    tax_rate: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="Steuersatz in Prozent"
    )
    taxable_amount: Decimal = Field(
        ...,
        description="Bemessungsgrundlage (Nettobetrag fuer diese Kategorie)"
    )
    tax_amount: Decimal = Field(
        ...,
        description="Steuerbetrag"
    )
    exemption_reason: Optional[str] = Field(
        None,
        description="Steuerbefreiungsgrund (BT-120)"
    )
    exemption_reason_code: Optional[str] = Field(
        None,
        description="Code fuer Steuerbefreiung (BT-121, z.B. vatex-eu-ic)"
    )


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
    supplier_number: Optional[str] = Field(
        None, description="Lieferantennummer/Kreditorennummer fuer ERP-Integration"
    )

    # === Daten ===
    invoice_date: Optional[date] = Field(None, description="Rechnungsdatum")
    invoice_date_raw: Optional[str] = Field(
        None, description="Rechnungsdatum Original-String (z.B. '06.04.2020')"
    )
    due_date: Optional[date] = Field(None, description="Faelligkeitsdatum")
    due_date_raw: Optional[str] = Field(
        None, description="Faelligkeitsdatum Original-String"
    )
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

    # === Zusaetzliche Lieferanteninformationen ===
    sender_tax_number_alternative: Optional[str] = Field(
        None, description="Alternative Steuernummer des Absenders (z.B. NL-Nummer 85xxxxxx)"
    )

    # === Lieferadresse (falls abweichend von Rechnungsadresse) ===
    delivery_address: Optional[ExtractedAddress] = Field(
        None, description="Lieferadresse (falls abweichend von Rechnungsadresse)"
    )

    # === Lieferbedingungen ===
    delivery_terms: Optional[str] = Field(
        None, description="Lieferbedingungen/Incoterms (EXW, FOB, CIF, DAP, DDP)"
    )

    # === Steuerbefreiung bei innergemeinschaftlicher Lieferung ===
    reverse_charge_note: Optional[str] = Field(
        None, description="Hinweis auf Steuerbefreiung (z.B. 'Intra-Community supply - VAT reverse charged')"
    )
    is_reverse_charge: bool = Field(
        False, description="True wenn innergemeinschaftliche Lieferung mit Reverse Charge"
    )
    vat_exemption_reason: Optional[str] = Field(
        None, description="Grund für Steuerbefreiung (z.B. 'Intra-Community supply', 'Reverse Charge')"
    )
    intra_community_supply: bool = Field(
        False, description="True bei innergemeinschaftlicher Lieferung (EU-Grenzueberschreitend)"
    )

    # === Betraege ===
    net_amount: Optional[Decimal] = Field(None, ge=0, description="Nettobetrag")
    vat_rate: Optional[Decimal] = Field(None, ge=0, le=100, description="MwSt-Satz in % (7, 19)")
    vat_amount: Optional[Decimal] = Field(None, ge=0, description="MwSt-Betrag")
    vat_amount_source: AmountSource = Field(
        AmountSource.NOT_FOUND, description="Quelle des MwSt-Betrags"
    )
    gross_amount: Optional[Decimal] = Field(None, ge=0, description="Bruttobetrag")
    gross_amount_source: AmountSource = Field(
        AmountSource.NOT_FOUND, description="Quelle des Bruttobetrags"
    )
    currency: Currency = Field(Currency.EUR, description="Waehrung")
    vat_reason: Optional[str] = Field(
        None, description="Grund für MwSt-Höhe (z.B. 'intra-community supply / reverse charge')"
    )

    # === Positionen ===
    line_items: List[ExtractedLineItem] = Field(default_factory=list, description="Rechnungspositionen")

    # === Zahlungsinformationen (KRITISCH für Buchhaltung!) ===
    payment_terms: Optional[str] = Field(None, description="Zahlungsbedingungen (z.B. '30 Tage netto')")
    payment_terms_days: Optional[int] = Field(
        None,
        ge=0,
        description="Zahlungsfrist in Tagen (strukturiert fuer Berechnungen)"
    )
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

    # === OCR Metadaten ===
    page_count: Optional[int] = Field(None, ge=1, description="Anzahl der Seiten im Dokument")
    ocr_confidence_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Gesamtkonfidenz der OCR-Erkennung"
    )

    # === Validierungsergebnisse ===
    validations: Optional[ExtractionValidations] = Field(
        None, description="Strukturierte Validierungsergebnisse"
    )

    # === Eingangs-/Ausgangsrechnung-Erkennung ===
    invoice_direction: InvoiceDirection = Field(
        InvoiceDirection.UNKNOWN,
        description="Eingangsrechnung (incoming) oder Ausgangsrechnung (outgoing)"
    )
    invoice_direction_confidence: float = Field(
        0.0, ge=0.0, le=1.0,
        description="Konfidenz der Richtungserkennung (0.0-1.0)"
    )
    invoice_direction_reason: Optional[str] = Field(
        None, description="Grund für die Klassifizierung (intern, z.B. 'VAT-ID match')"
    )

    # ==========================================================================
    # E-INVOICE / XRECHNUNG FELDER (ZUGFeRD 2.x / XRechnung 3.0.2)
    # ==========================================================================

    # === XRechnung Pflichtfelder (B2G) ===
    buyer_reference: Optional[str] = Field(
        None,
        description="Leitweg-ID / Buyer Reference (BT-10) - PFLICHT fuer B2G-Rechnungen"
    )
    business_process_type: Optional[str] = Field(
        None,
        description="Geschaeftsprozesstyp (BT-23) - z.B. 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0'"
    )
    seller_electronic_address: Optional[str] = Field(
        None,
        description="Elektronische Adresse Verkaeufer (BT-34) - z.B. GLN, PEPPOL-ID, E-Mail"
    )
    seller_electronic_address_scheme: Optional[str] = Field(
        None,
        description="Schema der elektronischen Adresse (BT-34-1) - z.B. '0088' fuer GLN, '0204' fuer Leitweg-ID"
    )
    buyer_electronic_address: Optional[str] = Field(
        None,
        description="Elektronische Adresse Kaeufer (BT-49)"
    )
    buyer_electronic_address_scheme: Optional[str] = Field(
        None,
        description="Schema der elektronischen Adresse Kaeufer (BT-49-1)"
    )

    # === Rechnungstyp und Kontext ===
    invoice_type_code: Optional[str] = Field(
        None,
        description="UN/CEFACT Invoice Type Code (BT-3) - 380=Rechnung, 381=Gutschrift, 384=Korrekturrechnung"
    )
    invoice_note: Optional[str] = Field(
        None,
        description="Rechnungshinweis/Bemerkung (BT-22) - Freitext"
    )
    contract_reference: Optional[str] = Field(
        None,
        description="Vertragsnummer (BT-12) - Referenz auf zugrundeliegenden Vertrag"
    )
    project_reference: Optional[str] = Field(
        None,
        description="Projektnummer (BT-11) - Referenz auf Projekt"
    )
    purchase_order_reference: Optional[str] = Field(
        None,
        description="Bestellnummer des Kaeufers (BT-13) - Referenz auf Bestellung"
    )

    # === Zahlungsdetails (erweitert fuer E-Invoice) ===
    payment_means_code: Optional[str] = Field(
        None,
        description="UN/CEFACT Payment Means Code (BT-81) - 30=Ueberweisung, 58=SEPA, 59=SEPA-Lastschrift"
    )
    payment_reference: Optional[str] = Field(
        None,
        description="Verwendungszweck (BT-83) - Strukturierte Zahlungsreferenz"
    )

    # === MwSt-Aufschluesselung (mehrere Saetze) ===
    tax_breakdown: List[TaxBreakdownItem] = Field(
        default_factory=list,
        description="MwSt-Aufschluesselung fuer mehrere Steuersaetze (BG-23)"
    )

    # === E-Invoice Metadaten ===
    einvoice_format: Optional[str] = Field(
        None,
        description="E-Rechnungsformat: 'zugferd', 'xrechnung_cii', 'xrechnung_ubl', 'facturx'"
    )
    einvoice_profile: Optional[str] = Field(
        None,
        description="ZUGFeRD Profil: 'MINIMUM', 'BASIC', 'BASIC_WL', 'EN16931', 'EXTENDED', 'XRECHNUNG'"
    )
    einvoice_version: Optional[str] = Field(
        None,
        description="Version des E-Rechnungsstandards (z.B. '2.3.3', '3.0.2')"
    )
    einvoice_xml_embedded: bool = Field(
        False,
        description="True wenn XML in PDF eingebettet war (ZUGFeRD-PDF)"
    )
    einvoice_validation_status: Optional[str] = Field(
        None,
        description="Validierungsstatus: 'valid', 'invalid', 'not_validated'"
    )

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
    document_hash: Optional[str] = Field(
        None, description="SHA256 Hash des Originaldokuments (sha256:...)"
    )

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
    "AmountSource",
    "ValidationStatus",
    "InvoiceDirection",
    # Basismodelle
    "ExtractedAddress",
    "ExtractedBankAccount",
    "ExtractedLineItem",
    "ExtractionValidations",
    "TaxBreakdownItem",
    # Dokumenttypen
    "ExtractedInvoiceData",
    "ExtractedOrderData",
    "ExtractedContractData",
    # Klassifizierung
    "DocumentClassificationResult",
    # Wrapper
    "ExtractedDocumentData",
]
