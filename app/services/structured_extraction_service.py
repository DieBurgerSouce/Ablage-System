# -*- coding: utf-8 -*-
"""
Structured Extraction Service.

Haupt-Orchestrierung fuer strukturierte Datenextraktion:
- Klassifizierung
- Typspezifische Extraktion (Invoice, Order, Contract)
- Plausibilitaetspruefung

Performance: < 200ms pro Dokument (ohne OCR)

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

import re
import structlog
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.extracted_data import (
    AmountSource,
    Currency,
    DocumentClassificationResult,
    ExtractedAddress,
    ExtractedBankAccount,
    ExtractedContractData,
    ExtractedDocumentData,
    ExtractedDocumentType,
    ExtractedInvoiceData,
    ExtractedLineItem,
    ExtractedOrderData,
    ExtractionValidations,
    InvoiceDirection,
)
from app.services.document_classification_service import (
    DocumentClassificationService,
    get_classification_service,
)
from app.services.entity_extraction_service import EntityExtractionService
from app.services.translation_service import (
    TranslationService,
    get_translation_service,
)
from app.services.company_matching_service import (
    CompanyMatchingService,
    get_company_matching_service,
)

# Enhanced Extraction Integration (Feature Flag gesteuert)
try:
    from app.services.extraction import (
        EnhancedExtractionAdapter,
        ENABLE_ENHANCED_EXTRACTION,
    )
    _enhanced_extraction_available = True
except ImportError:
    _enhanced_extraction_available = False
    ENABLE_ENHANCED_EXTRACTION = False

# Lazy import fuer LineItem-Extraktion (vermeidet zirkulaere Imports)
_line_item_service_class = None
_line_item_service_instance = None

logger = structlog.get_logger(__name__)


def _get_line_item_service():
    """Lazy-Load des LineItemExtractionService."""
    global _line_item_service_class, _line_item_service_instance
    if _line_item_service_instance is None:
        if _line_item_service_class is None:
            from app.services.line_item_extraction_service import (
                LineItemExtractionService,
            )
            _line_item_service_class = LineItemExtractionService
        _line_item_service_instance = _line_item_service_class()
    return _line_item_service_instance


# Singleton fuer Enhanced Extraction Adapter
_enhanced_extraction_adapter: Optional["EnhancedExtractionAdapter"] = None


def _get_enhanced_extraction_adapter() -> Optional["EnhancedExtractionAdapter"]:
    """Lazy-Load des EnhancedExtractionAdapter."""
    global _enhanced_extraction_adapter
    if not _enhanced_extraction_available or not ENABLE_ENHANCED_EXTRACTION:
        return None
    if _enhanced_extraction_adapter is None:
        _enhanced_extraction_adapter = EnhancedExtractionAdapter()
    return _enhanced_extraction_adapter


# =============================================================================
# HTML SANITIZATION
# =============================================================================

# Regex zum Entfernen von HTML-Tags
_HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
# Regex zum Entfernen von HTML-Entities
_HTML_ENTITY_PATTERN = re.compile(r'&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);')


def sanitize_extracted_text(text: Optional[str]) -> Optional[str]:
    """
    Bereinigt extrahierten Text von HTML-Tags und -Entities.

    Entfernt:
    - HTML-Tags wie <b>, </b>, <br/>, etc.
    - HTML-Entities wie &nbsp;, &#160;, etc.
    - Mehrfache Leerzeichen

    Args:
        text: Der zu bereinigende Text

    Returns:
        Bereinigter Text oder None wenn Input None war
    """
    if text is None:
        return None

    # HTML-Tags entfernen
    cleaned = _HTML_TAG_PATTERN.sub('', text)

    # Gaengige HTML-Entities ersetzen
    cleaned = cleaned.replace('&nbsp;', ' ')
    cleaned = cleaned.replace('&amp;', '&')
    cleaned = cleaned.replace('&lt;', '<')
    cleaned = cleaned.replace('&gt;', '>')
    cleaned = cleaned.replace('&quot;', '"')
    cleaned = cleaned.replace('&apos;', "'")

    # Verbleibende Entities entfernen
    cleaned = _HTML_ENTITY_PATTERN.sub('', cleaned)

    # Mehrfache Leerzeichen normalisieren
    cleaned = ' '.join(cleaned.split())

    return cleaned.strip() if cleaned else None


# =============================================================================
# REGEX PATTERNS
# =============================================================================

class PaymentPatterns:
    """Patterns fuer Zahlungsbedingungen - KRITISCH fuer Buchhaltung!"""

    # Zahlungsziel: "Zahlbar innerhalb von 30 Tagen" oder "Zahlungsziel: 14 Tage netto"
    PAYMENT_DAYS = re.compile(
        r'(?:zahlbar|zahlungsziel|f[aä]llig|netto)[\s:]*'
        r'(?:innerhalb\s*(?:von\s*)?)?'
        r'(\d{1,3})\s*(?:tage|tagen)',
        re.IGNORECASE
    )

    # Erweitertes Payment Pattern - deckt mehr Varianten ab
    # "NET 30", "net 30 days", "30 Tage netto", "Netto 30", "30T"
    PAYMENT_DAYS_EXTENDED = re.compile(
        r'(?:'
        r'net(?:to)?\s*(\d{1,3})|'               # NET 30, netto 30
        r'(\d{1,3})\s*(?:tage?\s*)?net(?:to)?|'  # 30 Tage netto, 30T netto
        r'(\d{1,3})\s*days?\s*net|'              # 30 days net (englisch)
        r'zahlungsfrist\s*(\d{1,3})|'            # Zahlungsfrist 30
        r'payment\s*(?:within|in)\s*(\d{1,3})'   # payment within 30
        r')',
        re.IGNORECASE
    )

    # Sofortige Zahlung erkennen
    PAYMENT_IMMEDIATE = re.compile(
        r'(?:zahlbar\s*sofort|sofort\s*f[aä]llig|bar\s*bei\s*[uü]bergabe|'
        r'zahlung\s*bei\s*lieferung|vorauskasse|vorkasse|'
        r'due\s*(?:upon|on)\s*receipt)',
        re.IGNORECASE
    )

    # Fälligkeitsdatum direkt: "Fällig am 15.02.2024" oder "Due Date 14-03-20"
    DUE_DATE_DIRECT = re.compile(
        r'(?:f[aä]llig(?:keit)?|zahlbar\s*bis|zahlungsziel|due\s*date|vervaldatum)[\s:]*'
        r'(?:am\s*)?(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})',
        re.IGNORECASE
    )

    # Skonto-Prozent: "2% Skonto" oder "Skonto 2,0%"
    SKONTO_PERCENT = re.compile(
        r'(?:(\d{1,2}(?:[,\.]\d{1,2})?)\s*%?\s*(?:skonto|rabatt|nachlass)|'
        r'(?:skonto|rabatt|nachlass)\s*(\d{1,2}(?:[,\.]\d{1,2})?)\s*%)',
        re.IGNORECASE
    )

    # Skonto-Frist: "bei Zahlung innerhalb 10 Tagen"
    SKONTO_DAYS = re.compile(
        r'(?:skonto|rabatt).*?'
        r'(?:innerhalb|binnen)\s*(?:von\s*)?'
        r'(\d{1,3})\s*(?:tage|tagen)',
        re.IGNORECASE
    )

    # Kombiniertes Skonto-Pattern: "2% Skonto 10 Tage, 30 Tage netto"
    SKONTO_FULL = re.compile(
        r'(\d{1,2}(?:[,\.]\d)?)\s*%?\s*(?:skonto|nachlass)'
        r'.*?(\d{1,3})\s*(?:tage|tagen)',
        re.IGNORECASE
    )

    # Skonto-Volltext (fuer early_payment_info)
    SKONTO_FULLTEXT = re.compile(
        r'(\d{1,2}(?:[,\.]\d)?%?\s*(?:skonto|nachlass|rabatt)'
        r'.*?(?:innerhalb|binnen|bei\s*zahlung).*?\d{1,3}\s*tage\w*)',
        re.IGNORECASE
    )

    # Verzugszinsen: "Verzugszinsen 9% über Basiszinssatz"
    LATE_INTEREST = re.compile(
        r'verzugszins(?:en)?[\s:]*'
        r'(\d{1,2}(?:[,\.]\d{1,2})?)\s*%',
        re.IGNORECASE
    )

    # Verzugszinsen Volltext
    LATE_INTEREST_FULLTEXT = re.compile(
        r'(verzugszins(?:en)?.*?(?:basiszins|prozent|p\.?a\.?))',
        re.IGNORECASE
    )

    # Zahlungsart: "Zahlung per Überweisung"
    PAYMENT_METHOD = re.compile(
        r'(?:zahlung|bezahlung)\s*(?:per|via|durch)?\s*'
        r'([uü]berweisung|lastschrift|bar|kreditkarte|paypal|rechnung)',
        re.IGNORECASE
    )


class AmountPatterns:
    """Patterns fuer deutsche Geldbetraege."""

    # Deutsches Format: 1.234,56 EUR oder 1234,56 €
    GERMAN_AMOUNT = re.compile(
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR|Euro)?',
        re.IGNORECASE
    )

    # Nettobetrag mit Label
    # WICHTIG: Muss Dezimalstellen haben (,XX) um "Netto 10 dagen" auszuschliessen
    NET_AMOUNT = re.compile(
        r'(?:netto(?:betrag)?|zwischensumme|summe\s*netto)[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:€|EUR)?',
        re.IGNORECASE
    )

    # Bruttobetrag mit Label (inkl. Bestellwert, Auftragswert)
    # WICHTIG: Muss Dezimalstellen haben (,XX)
    GROSS_AMOUNT = re.compile(
        r'(?:brutto(?:betrag)?|gesamt(?:betrag)?|endbetrag|'
        r'zu\s*zahlen(?:der\s*betrag)?|rechnungsbetrag|'
        r'bestell(?:wert|betrag)|auftrags(?:wert|summe)|'
        r'vertrags(?:wert|summe))[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:€|EUR)?',
        re.IGNORECASE
    )

    # Total EUR (englisch/niederlaendisch) - Betrag auf gleicher oder naechster Zeile
    # Bei NL-Rechnungen ist dies oft der EINZIGE Betrag (= Nettobetrag ohne MwSt)
    TOTAL_EUR = re.compile(
        r'Total\s+EUR[\s\n:]*(\d{1,3}(?:\.\d{3})*,\d{2})',
        re.IGNORECASE
    )

    # Fragmentierter Gesamtbetrag: Betrag gefolgt von "Total EUR" Label
    TOTAL_EUR_REVERSE = re.compile(
        r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*[V✓]?\s*\n\s*(?:<b>)?Total\s+EUR(?:</b>)?',
        re.IGNORECASE
    )

    # MwSt mit Satz und Betrag
    VAT_WITH_RATE = re.compile(
        r'(?:mwst\.?|ust\.?|mehrwertsteuer|umsatzsteuer)\s*'
        r'(\d{1,2})\s*%[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
        re.IGNORECASE
    )

    # MwSt nur Betrag
    VAT_AMOUNT = re.compile(
        r'(?:mwst\.?|ust\.?|mehrwertsteuer)[\s:]*'
        r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
        re.IGNORECASE
    )

    # MwSt-Satz ohne Betrag
    VAT_RATE = re.compile(
        r'(?:mwst\.?|ust\.?|mehrwertsteuer)\s*'
        r'(\d{1,2})\s*%',
        re.IGNORECASE
    )


class ReferencePatterns:
    """Patterns fuer Dokumentreferenzen."""

    # ==========================================================================
    # VENDOR-SPECIFIC INVOICE NUMBER FORMATS (Added 2025-12-15)
    # Diese Patterns haben hoechste Prioritaet, da sie sehr spezifisch sind
    # ==========================================================================

    # Asal-Format: RG + 8 Ziffern (z.B. RG20012108)
    INVOICE_NUMBER_RG = re.compile(r'\b(RG\d{8})\b', re.IGNORECASE)

    # Amefa-Format: CD + 10 Ziffern (z.B. CD4921000467)
    INVOICE_NUMBER_CD = re.compile(r'\b(CD\d{10})\b', re.IGNORECASE)

    # AUER Packaging: VK + 7 Ziffern (z.B. VK 1036735 oder VK1036735)
    INVOICE_NUMBER_VK = re.compile(r'\bVK\s*(\d{7})\b', re.IGNORECASE)

    # AUER Delivery: D + 5-6 Ziffern (z.B. D119925)
    INVOICE_NUMBER_D = re.compile(r'\b(D\d{5,6})\b', re.IGNORECASE)

    # Standalone 6-stellige Nummer gefolgt von Datum (a.b.s. Rechenzentrum Format)
    INVOICE_NUMBER_ABS = re.compile(r'\b(\d{6})\s*\n\s*\d{2}\.\d{2}\.\d{2,4}')

    # a.b.s. Rechenzentrum VERTIKALES Layout:
    # Labels kommen zuerst vertikal, dann Werte vertikal
    # Format:
    #   Rechnungs-Nr.
    #   Kunden-Nr.
    #   Rechnungsdatum
    #   Rechnung        <- optional header
    #   246543          <- Invoice number (erste 5-6 stellige Zahl nach den Labels)
    #   25.05.22        <- Date
    #   310835          <- Customer number
    INVOICE_NUMBER_VERTICAL_LAYOUT = re.compile(
        r'Rechnungs-Nr\.?\s*\n'
        r'Kunden-Nr\.?\s*\n'
        r'Rechnungsdatum\s*\n'
        r'(?:Rechnung\s*\n)?'  # Optional "Rechnung" header
        r'(\d{5,8})',  # Invoice number (5-8 digits)
        re.IGNORECASE
    )

    # ==========================================================================
    # STANDARD PATTERNS
    # ==========================================================================

    # Rechnungsnummer (Standard: Label vor Wert)
    INVOICE_NUMBER = re.compile(
        r'(?:rechnung(?:s)?|re|rg|invoice|beleg|faktura)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Rechnungsnummer REVERSE: "F-201401\nInvoice No." (Wert vor Label)
    # F-xxx Pattern fuer niederlaendische/internationale Rechnungen
    INVOICE_NUMBER_REVERSE = re.compile(
        r'(F-\d{5,8})\s*\n\s*(?:Invoice\s*(?:No\.?|Number)|Rechnungs?-?(?:Nr\.?|nummer)|Factuurnr)',
        re.IGNORECASE
    )

    # ==========================================================================
    # LABEL-SKIP KEYWORDS (zur Vermeidung von false positives)
    # ==========================================================================

    LABEL_KEYWORDS = frozenset([
        'datum', 'nr', 'nummer', 'kunde', 'kunden', 'betrag',
        'mwst', 'steuer', 'summe', 'netto', 'brutto', 'artikel',
        'position', 'menge', 'preis', 'date', 'amount', 'customer',
        'rechnungsdatum', 'lieferdatum', 'bestelldatum', 'rechnungsnummer',
        'invoice', 'number', 'order', 'delivery', 'total',
    ])

    # Bestellnummer (Standard: Label vor Wert)
    ORDER_NUMBER = re.compile(
        r'(?:bestell(?:ung)?|auftrag(?:s)?|order|po)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Bestellnummer REVERSE: "V-210089\nOrder No." (Wert vor Label)
    # V-xxx Pattern fuer niederlaendische/internationale Bestellungen
    ORDER_NUMBER_REVERSE = re.compile(
        r'(V-\d{5,8})\s*\n\s*(?:Order\s*(?:No\.?|Number)|Bestell?-?(?:Nr\.?|nummer)|Auftragsnr)',
        re.IGNORECASE
    )

    # Kundennummer - auch mit Bindestrich wie "KD-78901" und "Bill-to Customer No."
    CUSTOMER_NUMBER = re.compile(
        r'(?:'
        r'(?:bill[- ]?to\s+)?'  # Optional "Bill-to" Prefix
        r'(?:kunden?|kd\.?|customer)'
        r')[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9]{2,20})',
        re.IGNORECASE
    )

    # Lieferscheinnummer
    DELIVERY_NOTE = re.compile(
        r'(?:liefer(?:schein)?|ls|delivery)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Vertragsnummer
    CONTRACT_NUMBER = re.compile(
        r'(?:vertrag(?:s)?|contract|vtr)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Angebotsnummer
    QUOTATION_NUMBER = re.compile(
        r'(?:angebot(?:s)?|offerte|quote|ang)[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9/\.]{2,25})',
        re.IGNORECASE
    )

    # Lieferantennummer (fuer ERP-Integration: SAP, DATEV, etc.)
    SUPPLIER_NUMBER = re.compile(
        r'(?:'
        r'lieferant(?:en)?|kreditor(?:en)?|supplier|vendor'
        r')[\s\-\.:]?'
        r'(?:nr\.?|nummer|no\.?|id)[\s:\.]*'
        r'([A-Z0-9][-A-Z0-9]{2,20})',
        re.IGNORECASE
    )


class DatePatterns:
    """Patterns fuer deutsche und internationale Datumsformate."""

    # Deutsches Datum: 15.02.2024 oder 15.02.24 oder 15-02-2024
    DATE_DE = re.compile(
        r'\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b'
    )

    # Rechnungsdatum (deutsch + niederlaendisch + englisch)
    INVOICE_DATE = re.compile(
        r'(?:rechnung(?:s)?datum|factuurdatum|invoice\s*date|datum\s*der?\s*rechnung|ausgestellt\s*am)[\s:]*'
        r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})',
        re.IGNORECASE
    )

    # Bestelldatum
    ORDER_DATE = re.compile(
        r'(?:bestell(?:ung)?(?:s)?datum|order\s*date|datum\s*der?\s*bestellung)[\s:]*'
        r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})',
        re.IGNORECASE
    )

    # Liefertermin
    DELIVERY_DATE = re.compile(
        r'(?:liefer(?:ung)?(?:s)?(?:termin|datum)|delivery\s*date|gew[uü]nschte?\s*lieferung)[\s:]*'
        r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})',
        re.IGNORECASE
    )

    # Leistungszeitraum: "Leistungszeitraum: 01.01.2024 - 31.01.2024"
    SERVICE_PERIOD = re.compile(
        r'(?:leistungs?zeitraum|abrechnungszeitraum|zeitraum)[\s:]*'
        r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\s*'
        r'[-–bis]+\s*'
        r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})',
        re.IGNORECASE
    )

    # Vertragslaufzeit: "Laufzeit: 12 Monate"
    CONTRACT_DURATION = re.compile(
        r'(?:laufzeit|vertrags?dauer|g[uü]ltigkeit)[\s:]*'
        r'(\d{1,3})\s*'
        r'(tage|wochen|monate|jahre)',
        re.IGNORECASE
    )

    # Kuendigungsfrist: "3 Monate zum Quartalsende"
    NOTICE_PERIOD = re.compile(
        r'(?:k[uü]ndigungs?frist|frist)[\s:]*'
        r'(\d{1,2})\s*'
        r'(tage|wochen|monate|jahre)'
        r'(?:\s*zum\s*(monatsende|quartalsende|jahresende))?',
        re.IGNORECASE
    )


class DeliveryPatterns:
    """Patterns fuer Lieferbedingungen und Incoterms."""

    # Incoterms 2020 (alle 11 Standardterms)
    INCOTERMS = re.compile(
        r'\b(EXW|FCA|CPT|CIP|DAP|DPU|DDP|FAS|FOB|CFR|CIF)\b'
        r'(?:\s+([A-Za-z][A-Za-z\s,\-]{2,50}?))?'  # Optional: Ort
        r'(?:\s+(?:Incoterms?)?\s*(?:20\d{2})?)?',  # Optional: Jahr
        re.IGNORECASE
    )

    # Deutsche Lieferbedingungen
    DELIVERY_TERMS_DE = re.compile(
        r'(?:lieferbedingung(?:en)?|lieferkonditionen?|versandbedingung(?:en)?|'
        r'lieferung|versand)[\s:]*([^\n]{5,100})',
        re.IGNORECASE
    )

    # Lieferadress-Labels
    DELIVERY_ADDRESS_LABELS = re.compile(
        r'\b(?:lieferadresse|lieferanschrift|deliver(?:y\s*)?(?:to|address)|'
        r'ship\s*to|warenempf[aä]nger)\b',
        re.IGNORECASE
    )


class ReverseChargePatterns:
    """Patterns fuer Steuerbefreiung bei innergemeinschaftlicher Lieferung."""

    # Reverse Charge / Innergemeinschaftliche Lieferung
    REVERSE_CHARGE = re.compile(
        r'(?:intra[- ]?community\s*supply|reverse\s*charge|'
        r'innergemeinschaftliche\s*lieferung|steuerfreie?\s*lieferung|'
        r'steuerbefreit(?:e)?(?:\s*(?:gem[aä][sß]|nach|lt\.?)?\s*(?:\xa7|§)?\s*4)?|'
        r'vat\s*(?:exempt|0%?\s*reverse)|btw\s*verlegd|'
        r'tax\s*free\s*(?:intra[- ]?eu|cross[- ]?border)|'
        r'steuerfrei(?:e)?(?:\s*innergemeinschaftliche)?)',
        re.IGNORECASE
    )

    # Volltext-Pattern fuer reverse_charge_note
    REVERSE_CHARGE_FULLTEXT = re.compile(
        r'((?:steuerbefreit(?:e)?|steuerfrei(?:e)?|vat\s*exempt|reverse\s*charge|'
        r'innergemeinschaftliche\s*lieferung|intra[- ]?community\s*supply)'
        r'[^\n]{0,100})',
        re.IGNORECASE
    )


class CurrencyPatterns:
    """Patterns fuer Waehrungserkennung."""

    # Waehrungssymbole und -codes
    CURRENCY = re.compile(
        r'\b(EUR|USD|GBP|CHF|€|\$|£)\b',
        re.IGNORECASE
    )

    # Waehrung in Kontext (z.B. "Total EUR", "Betrag in EUR")
    CURRENCY_CONTEXT = re.compile(
        r'(?:total|summe|betrag|amount|preis|price)\s*(EUR|USD|GBP|CHF|€)',
        re.IGNORECASE
    )

    # Mapping von Symbolen zu ISO-Codes
    CURRENCY_MAP = {
        '€': 'EUR', 'EURO': 'EUR', 'EUR': 'EUR',
        '$': 'USD', 'DOLLAR': 'USD', 'USD': 'USD',
        '£': 'GBP', 'POUND': 'GBP', 'GBP': 'GBP',
        'CHF': 'CHF', 'FRANKEN': 'CHF', 'SFR': 'CHF',
    }


# Laender-Mapping fuer VAT-Validierung (mehrsprachig)
COUNTRY_NAME_TO_CODE = {
    # Deutschland
    'deutschland': 'DE', 'germany': 'DE', 'duitsland': 'DE',
    'allemagne': 'DE', 'd': 'DE', 'de': 'DE',
    # Niederlande
    'niederlande': 'NL', 'netherlands': 'NL', 'nederland': 'NL',
    'holland': 'NL', 'nl': 'NL',
    # Oesterreich
    'oesterreich': 'AT', 'österreich': 'AT', 'austria': 'AT',
    'autriche': 'AT', 'oostenrijk': 'AT', 'a': 'AT', 'at': 'AT',
    # Belgien
    'belgien': 'BE', 'belgium': 'BE', 'belgique': 'BE',
    'belgie': 'BE', 'b': 'BE', 'be': 'BE',
    # Frankreich
    'frankreich': 'FR', 'france': 'FR', 'francia': 'FR',
    'f': 'FR', 'fr': 'FR',
    # Italien
    'italien': 'IT', 'italy': 'IT', 'italia': 'IT',
    'i': 'IT', 'it': 'IT',
    # Spanien
    'spanien': 'ES', 'spain': 'ES', 'espana': 'ES', 'españa': 'ES',
    'e': 'ES', 'es': 'ES',
    # Polen
    'polen': 'PL', 'poland': 'PL', 'polska': 'PL', 'pl': 'PL',
    # Schweiz
    'schweiz': 'CH', 'switzerland': 'CH', 'suisse': 'CH',
    'svizzera': 'CH', 'ch': 'CH',
    # Grossbritannien
    'grossbritannien': 'GB', 'großbritannien': 'GB', 'united kingdom': 'GB',
    'uk': 'GB', 'gb': 'GB', 'england': 'GB',
    # Tschechien
    'tschechien': 'CZ', 'czech republic': 'CZ', 'czechia': 'CZ', 'cz': 'CZ',
    # Luxemburg
    'luxemburg': 'LU', 'luxembourg': 'LU', 'l': 'LU', 'lu': 'LU',
}


# =============================================================================
# STRUCTURED EXTRACTION SERVICE
# =============================================================================

class StructuredExtractionService:
    """
    Orchestriert die strukturierte Datenextraktion.

    Workflow:
    1. Klassifizierung (Invoice, Order, Contract, ...)
    2. Typspezifische Extraktion
    3. Plausibilitaetspruefung
    4. Zusammenfuehrung zu ExtractedDocumentData

    Usage:
        service = StructuredExtractionService()
        result = await service.extract(ocr_text)
        print(result.classification.document_type)
        print(result.invoice.gross_amount)
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self.classification_service = get_classification_service()
        self.entity_service = EntityExtractionService()
        self.translation_service = get_translation_service()

    def _clean_company_name(self, name: str) -> str:
        """
        Bereinigt OCR-Artefakte und HTML aus Firmennamen.

        Behandelt:
        - HTML-Tags und Entities (NEU!)
        - Dokumenttyp-Indikatoren ("Sales - Invoice", etc.)
        - Duplizierte Namensteile
        - Bevorzugt Teil mit Rechtsform oder "Name - Beschreibung" Format
        """
        if not name:
            return name

        # 0. HTML-Sanitization (NEU - entfernt <b>, </b>, etc.)
        cleaned = sanitize_extracted_text(name)
        if not cleaned:
            return name

        # 1. Entferne Dokumenttyp-Indikatoren
        doc_type_patterns = [
            "Sales - Invoice", "Sales-Invoice", "Invoice -", "- Invoice",
            "Rechnung -", "- Rechnung", "Order -", "- Order",
            "Bestellung -", "- Bestellung"
        ]
        # cleaned wurde bereits durch HTML-Sanitization gesetzt
        for pattern in doc_type_patterns:
            if pattern.lower() in cleaned.lower():
                idx = cleaned.lower().find(pattern.lower())
                cleaned = cleaned[:idx] + cleaned[idx + len(pattern):]
                cleaned = cleaned.strip(' -')

        # 2. Deduplizierung: Wenn erstes Wort spaeter nochmal auftaucht
        words = cleaned.split()
        if len(words) >= 4:
            first_word_lower = words[0].lower()
            for i in range(2, len(words)):
                if words[i].lower() == first_word_lower:
                    first_part = ' '.join(words[:i]).rstrip(' -')
                    second_part = ' '.join(words[i:])
                    # Praeferiere "Name - Beschreibung" Format (mit Bindestrich)
                    if ' - ' in second_part:
                        return second_part
                    if ' - ' in first_part:
                        return first_part
                    # Sonst zweiten Teil (oft bereinigter)
                    return second_part

        return cleaned if cleaned else name

    async def extract(
        self,
        text: str,
        document_id: Optional[str] = None,
        tables: Optional[List[Any]] = None,
        detected_language: Optional[str] = None,
        page_count: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> ExtractedDocumentData:
        """
        Extrahiert strukturierte Daten aus OCR-Text.

        Bei nicht-deutschen/englischen Texten wird automatisch uebersetzt,
        um einheitliche Keyword-Suche zu ermoeglichen.

        Args:
            text: OCR-Text
            document_id: Optionale Dokument-ID fuer Logging
            tables: Optionale Liste von TableStructure-Objekten (Docling)
            detected_language: Erkannte Sprache (ISO 639-1, z.B. "ru", "pl")
            db: Optionale DB-Session fuer Eingangs-/Ausgangsrechnung-Erkennung

        Returns:
            ExtractedDocumentData mit Klassifizierung und typspezifischen Daten
        """
        start_time = datetime.now()

        # Null-Check fuer text
        if not text:
            logger.warning("extract_called_with_empty_text", document_id=document_id)
            return ExtractedDocumentData(
                extraction_version="2.0.0",
                extracted_at=datetime.now().isoformat(),
            )

        # 0. Uebersetzung falls noetig (nicht-deutsche/englische Dokumente)
        original_language = detected_language
        was_translated = False
        translation_confidence: Optional[float] = None
        text_for_extraction = text

        if detected_language and self.translation_service.is_translation_needed(detected_language):
            translation_result = await self.translation_service.translate_for_extraction(
                text=text,
                source_language=detected_language,
            )
            if translation_result.was_translated:
                text_for_extraction = translation_result.translated_text
                was_translated = True
                translation_confidence = translation_result.confidence
                logger.info(
                    "text_translated_for_extraction",
                    document_id=document_id,
                    source_language=detected_language,
                    translation_duration_ms=translation_result.duration_ms,
                    translation_confidence=translation_result.confidence,
                )

        # 1. Klassifizierung (mit uebersetztem Text falls noetig)
        classification = self.classification_service.classify(text_for_extraction)

        # 2. Basis-Entities extrahieren (aus uebersetztem Text)
        entities = await self.entity_service.extract_entities(text_for_extraction)

        # 3. Typspezifische Extraktion
        result = ExtractedDocumentData(
            classification=classification,
            extraction_version="2.0.0",
            extracted_at=datetime.now().isoformat(),
            # Uebersetzungs-Metadaten
            original_language=original_language,
            was_translated=was_translated,
            translation_confidence=translation_confidence,
        )

        # Allgemeine Entities hinzufuegen
        result.vat_ids = [i.normalized_value for i in entities.identifiers if i.identifier_type == "vat_id"]
        result.ibans = [i.normalized_value for i in entities.identifiers if i.identifier_type == "iban"]
        result.companies = [c.name for c in entities.company_names]

        # Alle Daten extrahieren (aus uebersetztem Text)
        result.dates = self._extract_all_dates(text_for_extraction)

        # Alle Betraege extrahieren (aus uebersetztem Text)
        result.amounts = self._extract_all_amounts(text_for_extraction)

        # 4. Typspezifische Extraktion (mit uebersetztem Text)
        if classification.document_type == ExtractedDocumentType.INVOICE:
            result.invoice = await self._extract_invoice_data(
                text_for_extraction, entities, tables, page_count=page_count
            )
        elif classification.document_type == ExtractedDocumentType.ORDER:
            result.order = await self._extract_order_data(
                text_for_extraction, entities, tables
            )
        elif classification.document_type == ExtractedDocumentType.CONTRACT:
            result.contract = self._extract_contract_data(text_for_extraction, entities)

        # 5. Eingangs-/Ausgangsrechnung-Erkennung (falls DB-Session vorhanden)
        if result.invoice and db:
            try:
                matching_service = get_company_matching_service()
                direction, confidence, reason = await matching_service.match_invoice_direction(
                    result.invoice, db
                )
                result.invoice.invoice_direction = direction
                result.invoice.invoice_direction_confidence = confidence
                result.invoice.invoice_direction_reason = reason

                if direction != InvoiceDirection.UNKNOWN:
                    logger.info(
                        "invoice_direction_set",
                        document_id=document_id,
                        direction=direction.value,
                        confidence=confidence,
                        reason=reason,
                    )
            except Exception as e:
                logger.warning(
                    "invoice_direction_detection_failed",
                    document_id=document_id,
                    error=str(e),
                )

        # 6. Overall Confidence berechnen
        result.overall_confidence = self._calculate_overall_confidence(result)

        # Logging
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(
            "structured_extraction_completed",
            document_id=document_id,
            document_type=classification.document_type.value,
            classification_confidence=classification.confidence,
            overall_confidence=result.overall_confidence,
            elapsed_ms=round(elapsed, 2),
            original_language=original_language,
            was_translated=was_translated,
        )

        return result

    # =========================================================================
    # INVOICE EXTRACTION
    # =========================================================================

    async def _extract_invoice_data(
        self,
        text: str,
        entities: Any,
        tables: Optional[List[Any]] = None,
        page_count: Optional[int] = None,
    ) -> ExtractedInvoiceData:
        """Extrahiert Rechnungsdaten inkl. Positionen aus Tabellen."""
        invoice = ExtractedInvoiceData()
        warnings: List[str] = []

        # Seitenanzahl setzen (aus OCR-Metadaten)
        if page_count is not None and page_count > 0:
            invoice.page_count = page_count

        # Referenznummern
        # FIX 2025-12-15: Erweiterte Extraktion mit vendor-spezifischen Patterns
        # und Label-Skip-Logik um false positives zu vermeiden
        invoice.invoice_number = self._extract_invoice_number_with_validation(text)

        # WICHTIG: Zuerst REVERSE-Patterns versuchen (V-xxx vor "Order No.")
        invoice.order_number = (
            self._extract_first_match(ReferencePatterns.ORDER_NUMBER_REVERSE, text) or
            self._extract_first_match(ReferencePatterns.ORDER_NUMBER, text) or
            self._extract_fragmented_reference(text, [
                'order no', 'bestellnr', 'bestell-nr', 'auftragsnr', 'po no'
            ])
        )

        invoice.customer_number = self._extract_first_match(
            ReferencePatterns.CUSTOMER_NUMBER, text
        ) or self._extract_fragmented_reference(text, [
            'customer no', 'kundennr', 'kunden-nr', 'kd-nr',
            'bill-to customer', 'bill to customer no'
        ])

        invoice.delivery_note_number = self._extract_first_match(
            ReferencePatterns.DELIVERY_NOTE, text
        )

        # Lieferantennummer (optional - fuer ERP-Integration)
        invoice.supplier_number = self._extract_first_match(
            ReferencePatterns.SUPPLIER_NUMBER, text
        ) or self._extract_fragmented_reference(text, [
            'supplier no', 'vendor no', 'lieferanten-nr', 'kreditor-nr'
        ])

        # Daten (mit Raw-Wert-Erfassung fuer Audit-Trail)
        invoice.invoice_date = self._extract_labeled_date(
            DatePatterns.INVOICE_DATE, text
        ) or self._extract_fragmented_date(text, [
            'factuurdatum', 'rechnungsdatum', 'invoice date', 'datum'
        ]) or self._extract_first_date(text)

        # Raw-Wert fuer invoice_date extrahieren (Original-String aus Dokument)
        if invoice.invoice_date:
            raw_date_match = DatePatterns.INVOICE_DATE.search(text)
            if raw_date_match:
                invoice.invoice_date_raw = raw_date_match.group(0).strip()
            else:
                # Fallback: Generisches Datumsformat suchen (alle Separatoren)
                generic_date_pattern = re.compile(r'\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}')
                raw_match = generic_date_pattern.search(text)
                if raw_match:
                    invoice.invoice_date_raw = raw_match.group(0)

        # Faelligkeitsdatum
        due_date_match = PaymentPatterns.DUE_DATE_DIRECT.search(text)
        if due_date_match:
            invoice.due_date = self._parse_date_groups(
                due_date_match.group(1),
                due_date_match.group(2),
                due_date_match.group(3)
            )
            # Raw-Wert speichern (DD.MM.YYYY Format)
            invoice.due_date_raw = f"{due_date_match.group(1)}.{due_date_match.group(2)}.{due_date_match.group(3)}"

        # Fallback: Fragmentiertes Due Date (Label auf separater Zeile)
        if not invoice.due_date:
            invoice.due_date = self._extract_fragmented_date(text, [
                'due date', 'vervaldatum', 'fällig', 'zahlbar bis'
            ])

        # Oder aus Zahlungsziel berechnen
        if not invoice.due_date and invoice.invoice_date:
            days_match = PaymentPatterns.PAYMENT_DAYS.search(text)
            if days_match:
                days = int(days_match.group(1))
                invoice.due_date = invoice.invoice_date + timedelta(days=days)
                # Due date wurde berechnet - kein Raw-Wert verfuegbar

        # Leistungszeitraum
        period_match = DatePatterns.SERVICE_PERIOD.search(text)
        if period_match:
            invoice.service_period_start = self._parse_date_groups(
                period_match.group(1),
                period_match.group(2),
                period_match.group(3)
            )
            invoice.service_period_end = self._parse_date_groups(
                period_match.group(4),
                period_match.group(5),
                period_match.group(6)
            )

        # Betraege
        invoice.net_amount = self._extract_labeled_amount(
            AmountPatterns.NET_AMOUNT, text
        )

        # gross_amount mit Source-Tracking
        gross_from_doc = self._extract_labeled_amount(AmountPatterns.GROSS_AMOUNT, text)
        if gross_from_doc:
            invoice.gross_amount = gross_from_doc
            invoice.gross_amount_source = AmountSource.DOCUMENT

        # Fallback fuer Nettobetrag: Total EUR (englisch/niederlaendisch)
        # Bei NL-Rechnungen ohne MwSt ist "Total EUR" der Nettobetrag
        if not invoice.net_amount:
            total_eur_match = AmountPatterns.TOTAL_EUR.search(text)
            if total_eur_match:
                invoice.net_amount = self._parse_german_amount(total_eur_match.group(1))

        # Fallback: Fragmentierter Gesamtbetrag (Betrag vor "Total EUR" Label)
        if not invoice.net_amount:
            reverse_match = AmountPatterns.TOTAL_EUR_REVERSE.search(text)
            if reverse_match:
                invoice.net_amount = self._parse_german_amount(reverse_match.group(1))

        # Brutto nur setzen wenn explizit gefunden UND unterschiedlich von Netto
        # (bei Rechnungen ohne MwSt-Ausweis gibt es keinen Bruttobetrag)
        if invoice.gross_amount and invoice.net_amount:
            if invoice.gross_amount == invoice.net_amount:
                # Gleicher Betrag = kein separater Brutto noetig
                invoice.gross_amount = None
                invoice.gross_amount_source = AmountSource.NOT_FOUND

        # MwSt mit Source-Tracking
        vat_with_rate = AmountPatterns.VAT_WITH_RATE.search(text)
        if vat_with_rate:
            invoice.vat_rate = Decimal(vat_with_rate.group(1))
            invoice.vat_amount = self._parse_german_amount(vat_with_rate.group(2))
            invoice.vat_amount_source = AmountSource.DOCUMENT
        else:
            # Nur Betrag
            vat_amount_match = AmountPatterns.VAT_AMOUNT.search(text)
            if vat_amount_match:
                invoice.vat_amount = self._parse_german_amount(vat_amount_match.group(1))
                invoice.vat_amount_source = AmountSource.DOCUMENT

            # Nur Satz
            vat_rate_match = AmountPatterns.VAT_RATE.search(text)
            if vat_rate_match:
                invoice.vat_rate = Decimal(vat_rate_match.group(1))

        # === WAEHRUNGSERKENNUNG (Phase 5) ===
        # Prioritaet: Kontextbasiert > Allgemein
        currency_context_match = CurrencyPatterns.CURRENCY_CONTEXT.search(text)
        if currency_context_match:
            raw_currency = currency_context_match.group(1).upper()
            currency_code = CurrencyPatterns.CURRENCY_MAP.get(raw_currency, raw_currency)
            try:
                invoice.currency = Currency(currency_code)
                logger.debug("currency_extracted_from_context", currency=currency_code)
            except ValueError:
                pass  # Unbekannte Waehrung - Default bleibt EUR

        # Fallback: Erste Waehrung im Text
        if invoice.currency == Currency.EUR:
            currency_match = CurrencyPatterns.CURRENCY.search(text)
            if currency_match:
                raw_currency = currency_match.group(1).upper()
                currency_code = CurrencyPatterns.CURRENCY_MAP.get(raw_currency, raw_currency)
                try:
                    invoice.currency = Currency(currency_code)
                    logger.debug("currency_extracted_fallback", currency=currency_code)
                except ValueError as e:
                    logger.debug(
                        "currency_code_parse_failed",
                        error_type=type(e).__name__,
                    )

        # === ZAHLUNGSBEDINGUNGEN (KRITISCH!) ===

        # Zahlungsziel in Tagen - versuche mehrere Patterns
        payment_days_match = PaymentPatterns.PAYMENT_DAYS.search(text)
        days = None
        if payment_days_match:
            days = payment_days_match.group(1)
        else:
            # Fallback: Erweitertes Pattern für "NET 30", "30 days net", etc.
            extended_match = PaymentPatterns.PAYMENT_DAYS_EXTENDED.search(text)
            if extended_match:
                # Finde die erste nicht-None Gruppe
                for group in extended_match.groups():
                    if group:
                        days = group
                        break

        if days:
            invoice.payment_terms = f"{days} Tage netto"
            invoice.payment_terms_days = int(days)  # Strukturiertes Feld fuer Berechnungen
        else:
            # Prüfe auf sofortige Zahlung
            immediate_match = PaymentPatterns.PAYMENT_IMMEDIATE.search(text)
            if immediate_match:
                invoice.payment_terms = "Zahlbar sofort"
                invoice.payment_terms_days = 0  # Sofort = 0 Tage

        # Zahlungsart
        payment_method_match = PaymentPatterns.PAYMENT_METHOD.search(text)
        if payment_method_match:
            invoice.payment_method = payment_method_match.group(1).title()

        # Skonto - Kombination
        skonto_full_match = PaymentPatterns.SKONTO_FULL.search(text)
        if skonto_full_match:
            invoice.discount_percent = self._parse_german_amount(
                skonto_full_match.group(1).replace(",", ".")
            )
            invoice.discount_days = int(skonto_full_match.group(2))
        else:
            # Einzelne Patterns
            skonto_percent_match = PaymentPatterns.SKONTO_PERCENT.search(text)
            if skonto_percent_match:
                # Pattern hat zwei Gruppen - eine davon ist gesetzt
                percent_str = skonto_percent_match.group(1) or skonto_percent_match.group(2)
                if percent_str:
                    invoice.discount_percent = self._parse_german_amount(
                        percent_str.replace(",", ".")
                    )

            skonto_days_match = PaymentPatterns.SKONTO_DAYS.search(text)
            if skonto_days_match:
                invoice.discount_days = int(skonto_days_match.group(1))

        # Skonto-Betrag berechnen
        if invoice.discount_percent and invoice.gross_amount:
            invoice.discount_amount = (
                invoice.gross_amount * invoice.discount_percent / Decimal("100")
            ).quantize(Decimal("0.01"))

        # Skonto-Faelligkeitsdatum berechnen
        if invoice.discount_days and invoice.invoice_date:
            invoice.discount_due_date = (
                invoice.invoice_date + timedelta(days=invoice.discount_days)
            )

        # Skonto-Volltext
        skonto_fulltext_match = PaymentPatterns.SKONTO_FULLTEXT.search(text)
        if skonto_fulltext_match:
            invoice.early_payment_info = skonto_fulltext_match.group(1).strip()

        # Verzugszinsen
        late_interest_match = PaymentPatterns.LATE_INTEREST_FULLTEXT.search(text)
        if late_interest_match:
            invoice.late_payment_info = late_interest_match.group(1).strip()

        # Absender/Empfaenger aus Entities - INTELLIGENTE Zuordnung
        if entities.addresses:
            sender_addr = None
            recipient_addr = None

            # 1. Pass: Explizite Rollenzuordnung aus Entity-Extraktion
            for addr in entities.addresses:
                role = getattr(addr, 'role', None)
                if role == "sender" and not sender_addr:
                    sender_addr = addr
                    logger.debug(
                        "address_attributed_by_role",
                        role="sender",
                        city=addr.city,
                        country=getattr(addr, 'country', None),
                    )
                elif role == "recipient" and not recipient_addr:
                    recipient_addr = addr
                    logger.debug(
                        "address_attributed_by_role",
                        role="recipient",
                        city=addr.city,
                        country=getattr(addr, 'country', None),
                    )

            # 2. Pass: Cross-Border Heuristik (bei EU-Rechnungen)
            # Non-DE Adresse = wahrscheinlich auslaendischer Sender
            if not sender_addr and not recipient_addr and len(entities.addresses) >= 2:
                for addr in entities.addresses:
                    country = getattr(addr, 'country', 'DE') or 'DE'
                    if country.upper() != 'DE' and not sender_addr:
                        sender_addr = addr
                        logger.debug(
                            "address_attributed_by_crossborder",
                            role="sender",
                            country=country,
                            reason="non_de_address_likely_foreign_supplier",
                        )
                    elif country.upper() == 'DE' and not recipient_addr:
                        recipient_addr = addr
                        logger.debug(
                            "address_attributed_by_crossborder",
                            role="recipient",
                            country=country,
                            reason="de_address_likely_local_recipient",
                        )

            # 3. Pass: Positionale Zuordnung (Fallback)
            if not sender_addr and entities.addresses:
                sender_addr = entities.addresses[0]
                logger.debug(
                    "address_attributed_by_position",
                    role="sender",
                    position=0,
                )
            if not recipient_addr and len(entities.addresses) > 1:
                # Nimm die erste Adresse die NICHT sender_addr ist
                for addr in entities.addresses:
                    if addr != sender_addr:
                        recipient_addr = addr
                        logger.debug(
                            "address_attributed_by_position",
                            role="recipient",
                        )
                        break

            # Zuweisen der Adressen (mit HTML-Sanitization)
            if sender_addr:
                invoice.sender = ExtractedAddress(
                    street=sanitize_extracted_text(sender_addr.street),
                    street_number=sanitize_extracted_text(sender_addr.street_number) if hasattr(sender_addr, 'street_number') else None,
                    zip_code=sanitize_extracted_text(sender_addr.postal_code),
                    city=sanitize_extracted_text(sender_addr.city),
                    country=sender_addr.country if sender_addr.country else "DE",
                    company=sanitize_extracted_text(sender_addr.company_name) if hasattr(sender_addr, 'company_name') else None,
                )

            if recipient_addr:
                invoice.recipient = ExtractedAddress(
                    street=sanitize_extracted_text(recipient_addr.street),
                    street_number=sanitize_extracted_text(recipient_addr.street_number) if hasattr(recipient_addr, 'street_number') else None,
                    zip_code=sanitize_extracted_text(recipient_addr.postal_code),
                    city=sanitize_extracted_text(recipient_addr.city),
                    country=recipient_addr.country if recipient_addr.country else "DE",
                    company=sanitize_extracted_text(recipient_addr.company_name) if hasattr(recipient_addr, 'company_name') else None,
                )

        # Firmennamen mit Rechtsform (GmbH, etc.) - ueberschreiben Kontext-Namen
        if entities.company_names:
            # Erster Firmenname = Absender (ueberschreibt nur wenn vorhanden)
            if invoice.sender and entities.company_names[0].name:
                company = entities.company_names[0]
                # Bereinige und kombiniere name + legal_form
                clean_name = self._clean_company_name(company.name)
                full_name = f"{clean_name} {company.legal_form}" if company.legal_form else clean_name
                invoice.sender.company = full_name
            # Zweiter Firmenname = Empfaenger (falls vorhanden)
            if len(entities.company_names) > 1 and invoice.recipient:
                company = entities.company_names[1]
                # Bereinige und kombiniere name + legal_form
                clean_name = self._clean_company_name(company.name)
                full_name = f"{clean_name} {company.legal_form}" if company.legal_form else clean_name
                invoice.recipient.company = full_name

        # USt-IdNr - Intelligente Zuordnung (sender vs. recipient)
        vat_ids = [i for i in entities.identifiers if i.identifier_type == "vat_id"]
        if vat_ids:
            sender_vat, recipient_vat = self._attribute_vat_ids(
                vat_ids,
                entities.addresses
            )
            invoice.sender_vat_id = sender_vat
            invoice.recipient_vat_id = recipient_vat

            logger.debug(
                "vat_id_attribution_result",
                total_vat_ids=len(vat_ids),
                sender_vat_id=sender_vat,
                recipient_vat_id=recipient_vat,
            )

            # === LAENDER-VALIDIERUNG (Phase 3) ===
            # Pruefe ob VAT-Laender zu Adress-Laendern passen
            if invoice.sender_vat_id and invoice.sender:
                sender_country = invoice.sender.country
                if not self._validate_vat_country_match(invoice.sender_vat_id, sender_country):
                    warnings.append(
                        f"USt-IdNr {invoice.sender_vat_id} passt nicht zum Absender-Land {sender_country}"
                    )
                    invoice.needs_review = True

            if invoice.recipient_vat_id and invoice.recipient:
                recipient_country = invoice.recipient.country
                if not self._validate_vat_country_match(invoice.recipient_vat_id, recipient_country):
                    warnings.append(
                        f"USt-IdNr {invoice.recipient_vat_id} passt nicht zum Empfaenger-Land {recipient_country}"
                    )
                    invoice.needs_review = True

        # Steuernummer
        for identifier in entities.identifiers:
            if identifier.identifier_type == "tax_number":
                invoice.sender_tax_number = identifier.normalized_value
                break

        # IBAN + BIC (Phase 6: BIC in Bankdaten speichern)
        # BIC mit hoechster Konfidenz waehlen (gelabelte BICs haben 0.98)
        iban_id = None
        bic_id = None
        for identifier in entities.identifiers:
            if identifier.identifier_type == "iban" and not iban_id:
                iban_id = identifier
            elif identifier.identifier_type == "bic":
                # BIC mit hoechster Konfidenz bevorzugen
                if not bic_id or identifier.confidence > bic_id.confidence:
                    bic_id = identifier

        if iban_id or bic_id:
            invoice.sender_bank = ExtractedBankAccount(
                iban=iban_id.normalized_value if iban_id else None,
                bic=bic_id.normalized_value if bic_id else None,
            )
            logger.debug(
                "bank_account_extracted",
                iban=iban_id.normalized_value[:8] + "***" if iban_id else None,
                bic=bic_id.normalized_value if bic_id else None,
                iban_country=iban_id.country_code if iban_id else None,
                bic_country=bic_id.country_code if bic_id else None,
            )

            # === IBAN-LAND VALIDIERUNG (Plausibilitaetscheck) ===
            if invoice.sender_bank.iban and invoice.sender_vat_id:
                iban_country = invoice.sender_bank.iban[:2].upper()
                vat_country = invoice.sender_vat_id[:2].upper()

                if iban_country != vat_country:
                    invoice.extraction_warnings.append(
                        f"IBAN-Land ({iban_country}) != USt-IdNr-Land ({vat_country})"
                    )
                    invoice.needs_review = True
                    logger.warning(
                        "iban_vat_country_mismatch",
                        iban_country=iban_country,
                        vat_country=vat_country,
                    )

        # E-Mail
        if entities.emails:
            invoice.sender_email = entities.emails[0]

        # Telefon
        if entities.phone_numbers:
            invoice.sender_phone = entities.phone_numbers[0]

        # === LIEFERBEDINGUNGEN / INCOTERMS ===
        incoterms_match = DeliveryPatterns.INCOTERMS.search(text)
        if incoterms_match:
            incoterm = incoterms_match.group(1).upper()
            location = incoterms_match.group(2)
            if location:
                invoice.delivery_terms = f"{incoterm} {location.strip()}"
            else:
                invoice.delivery_terms = incoterm
            logger.debug(
                "incoterms_extracted",
                incoterm=incoterm,
                location=location,
            )

        # Fallback: Deutsche Lieferbedingungen
        if not invoice.delivery_terms:
            delivery_match = DeliveryPatterns.DELIVERY_TERMS_DE.search(text)
            if delivery_match:
                invoice.delivery_terms = delivery_match.group(1).strip()[:100]

        # === LIEFERADRESSE (falls abweichend) ===
        # Suche nach explizit gelabelter Lieferadresse
        for addr in entities.addresses:
            addr_position = getattr(addr, 'position_start', 0)
            context_start = max(0, addr_position - 100)
            context = text[context_start:addr_position]
            if DeliveryPatterns.DELIVERY_ADDRESS_LABELS.search(context):
                invoice.delivery_address = ExtractedAddress(
                    street=addr.street,
                    street_number=getattr(addr, 'street_number', None),
                    zip_code=addr.postal_code,
                    city=addr.city,
                    country=addr.country if addr.country else "DE",
                    company=getattr(addr, 'company_name', None),
                )
                logger.debug("delivery_address_extracted", city=addr.city)
                break

        # Fallback: Dritte Adresse ist oft Lieferadresse
        if not invoice.delivery_address and len(entities.addresses) >= 3:
            addr = entities.addresses[2]
            invoice.delivery_address = ExtractedAddress(
                street=addr.street,
                street_number=getattr(addr, 'street_number', None),
                zip_code=addr.postal_code,
                city=addr.city,
                country=addr.country if addr.country else "DE",
                company=getattr(addr, 'company_name', None),
            )

        # === REVERSE CHARGE / INNERGEMEINSCHAFTLICHE LIEFERUNG ===
        reverse_charge_match = ReverseChargePatterns.REVERSE_CHARGE.search(text)
        if reverse_charge_match:
            invoice.is_reverse_charge = True
            # Volltext fuer reverse_charge_note extrahieren
            fulltext_match = ReverseChargePatterns.REVERSE_CHARGE_FULLTEXT.search(text)
            if fulltext_match:
                invoice.reverse_charge_note = fulltext_match.group(1).strip()[:200]

            # NEU: Setze vat_exemption_reason basierend auf dem Match
            matched_text = reverse_charge_match.group(0).lower()
            if 'intra' in matched_text or 'innergemeinschaftlich' in matched_text:
                invoice.vat_exemption_reason = "Innergemeinschaftliche Lieferung"
                invoice.intra_community_supply = True
            elif 'reverse' in matched_text:
                invoice.vat_exemption_reason = "Reverse Charge"
            elif 'steuerbefreit' in matched_text or 'steuerfrei' in matched_text:
                invoice.vat_exemption_reason = "Steuerbefreit"

            logger.debug(
                "reverse_charge_detected",
                note=invoice.reverse_charge_note,
                exemption_reason=invoice.vat_exemption_reason,
                intra_community=invoice.intra_community_supply,
            )

        # Heuristik: Wenn sender und recipient VAT IDs unterschiedliche Laender haben
        # und VAT-Rate 0 ist, dann ist es wahrscheinlich Reverse Charge
        if not invoice.is_reverse_charge:
            sender_country = invoice.sender_vat_id[:2] if invoice.sender_vat_id else None
            recipient_country = invoice.recipient_vat_id[:2] if invoice.recipient_vat_id else None
            if (
                sender_country and recipient_country and
                sender_country != recipient_country and
                invoice.vat_rate == Decimal("0")
            ):
                invoice.is_reverse_charge = True
                # Bei unterschiedlichen EU-Laendern ist es eine innergemeinschaftliche Lieferung
                invoice.intra_community_supply = True
                invoice.vat_exemption_reason = "Innergemeinschaftliche Lieferung (inferiert)"
                logger.debug(
                    "reverse_charge_inferred",
                    sender_country=sender_country,
                    recipient_country=recipient_country,
                    vat_rate=str(invoice.vat_rate),
                    intra_community=True,
                )

        # === REVERSE CHARGE: vat_amount explizit auf 0 setzen ===
        # Bei Reverse Charge MUSS vat_amount = 0 sein, nicht null
        if invoice.is_reverse_charge and invoice.vat_amount is None:
            invoice.vat_amount = Decimal("0")
            invoice.vat_rate = Decimal("0")
            invoice.vat_amount_source = AmountSource.COMPUTED
            # vat_reason fuer Audit-Trail setzen
            if invoice.intra_community_supply:
                invoice.vat_reason = "intra-community supply / reverse charge"
            else:
                invoice.vat_reason = "reverse charge"
            logger.debug(
                "reverse_charge_vat_zeroed",
                reason="vat_amount was null, set to 0 for Reverse Charge invoice",
                vat_reason=invoice.vat_reason,
            )

        # === LINE ITEMS EXTRAKTION ===
        # Aus Docling-Tabellen extrahieren
        if tables:
            try:
                line_item_service = _get_line_item_service()
                invoice.line_items = await line_item_service.extract_from_tables(tables)

                # Plausibilitaet: Summe Positionen vs. Nettobetrag
                if invoice.line_items and invoice.net_amount:
                    is_valid, calculated = line_item_service.validate_against_total(
                        invoice.line_items, invoice.net_amount
                    )
                    if not is_valid and calculated:
                        warnings.append(
                            f"Positionssumme ({calculated}) weicht von Nettobetrag ({invoice.net_amount}) ab"
                        )
                        invoice.needs_review = True

                logger.debug(
                    "line_items_extracted",
                    count=len(invoice.line_items),
                    from_tables=len(tables),
                )
            except Exception as e:
                logger.warning(
                    "line_item_extraction_failed",
                    error=str(e),
                    table_count=len(tables),
                )
                warnings.append(f"Positionsextraktion fehlgeschlagen: {str(e)}")

        # Falls keine Tabellen oder Extraktion fehlgeschlagen: Regex-Fallback
        if not invoice.line_items and text:
            try:
                line_item_service = _get_line_item_service()
                invoice.line_items = await line_item_service.extract_from_text(text)
                if invoice.line_items:
                    logger.debug(
                        "line_items_from_text_fallback",
                        count=len(invoice.line_items),
                    )
            except Exception as e:
                logger.debug("line_item_text_fallback_failed", error=str(e))

        # Warnungen sammeln
        invoice.extraction_warnings = list(invoice.extraction_warnings) + warnings

        # === ENHANCED EXTRACTION (Optional) ===
        # Verbessert Payment Terms, Amounts und Line Items mit erweiterten Patterns
        enhanced_adapter = _get_enhanced_extraction_adapter()
        logger.warning(
            "DEBUG_enhanced_extraction_check",
            enhanced_adapter_available=enhanced_adapter is not None,
            enable_flag=ENABLE_ENHANCED_EXTRACTION,
            module_available=_enhanced_extraction_available,
        )
        if enhanced_adapter:
            try:
                enhanced_result = enhanced_adapter.extract_all(
                    text=text,
                    invoice_date=invoice.invoice_date,
                    tables=tables,
                )

                # Payment Terms uebernehmen wenn besser
                if enhanced_result.payment_terms:
                    pt = enhanced_result.payment_terms
                    # Nur uebernehmen wenn Confidence hoch oder vorher nichts gefunden
                    if pt.payment_days is not None and (
                        not invoice.payment_terms or pt.confidence > 0.7
                    ):
                        invoice.payment_terms = (
                            f"{pt.payment_days} Tage netto"
                            if not pt.is_immediate else "Zahlbar sofort"
                        )
                    if pt.due_date and not invoice.due_date:
                        invoice.due_date = pt.due_date
                    if pt.discount_tiers and not invoice.discount_percent:
                        best = pt.best_discount
                        if best:
                            invoice.discount_percent = best.percent
                            invoice.discount_days = best.days
                    if pt.extraction_warnings:
                        invoice.extraction_warnings = (
                            list(invoice.extraction_warnings) + pt.extraction_warnings
                        )

                # Amounts uebernehmen wenn besser
                if enhanced_result.amounts:
                    amt = enhanced_result.amounts
                    if amt.net_amount and (
                        not invoice.net_amount or amt.net_confidence > 0.8
                    ):
                        invoice.net_amount = amt.net_amount
                    if amt.gross_amount and (
                        not invoice.gross_amount or amt.gross_confidence > 0.8
                    ):
                        invoice.gross_amount = amt.gross_amount
                        invoice.gross_amount_source = AmountSource.DOCUMENT  # Aus Enhanced Extraction
                    if amt.vat_amount and (
                        not invoice.vat_amount or amt.vat_confidence > 0.8
                    ):
                        invoice.vat_amount = amt.vat_amount
                        invoice.vat_amount_source = AmountSource.DOCUMENT  # Aus Enhanced Extraction
                    # Note: Decimal("0") ist falsy, also explizit auf None pruefen
                    if amt.vat_rate is not None and invoice.vat_rate is None:
                        invoice.vat_rate = amt.vat_rate

                # Line Items uebernehmen wenn BESSER (nicht nur mehr)
                existing_items = invoice.line_items or []

                # DEBUG: Log existing items
                logger.warning(
                    "DEBUG_line_items_before_enhanced",
                    existing_count=len(existing_items),
                    existing_items=[
                        {
                            "desc": (i.description or "")[:50],
                            "qty": str(i.quantity) if i.quantity else "None",
                            "unit_price": str(i.unit_price) if i.unit_price else "None",
                            "total": str(i.total_price) if i.total_price else "None",
                        }
                        for i in existing_items
                    ] if existing_items else [],
                    enhanced_count=len(enhanced_result.line_items) if enhanced_result.line_items else 0,
                    enhanced_items=[
                        {
                            "desc": (i.description or "")[:50],
                            "qty": str(i.quantity) if i.quantity else "None",
                            "unit_price": str(i.unit_price) if i.unit_price else "None",
                            "total": str(i.total_price) if i.total_price else "None",
                        }
                        for i in enhanced_result.line_items
                    ] if enhanced_result.line_items else [],
                )

                if enhanced_result.line_items:
                    # Qualitaetspruefung der bestehenden Items
                    existing_has_issues = self._has_low_quality_line_items(existing_items)
                    enhanced_has_issues = self._has_low_quality_line_items_enhanced(
                        enhanced_result.line_items
                    )

                    # DEBUG: Log quality check results
                    logger.warning(
                        "DEBUG_line_items_quality_check",
                        existing_has_issues=existing_has_issues,
                        enhanced_has_issues=enhanced_has_issues,
                    )

                    # Enhanced uebernehmen wenn:
                    # 1. Bestehende Items haben Qualitaetsprobleme UND Enhanced nicht, ODER
                    # 2. Enhanced hat mehr Items UND keine Qualitaetsprobleme
                    should_use_enhanced = (
                        (existing_has_issues and not enhanced_has_issues) or
                        (len(enhanced_result.line_items) > len(existing_items)
                         and not enhanced_has_issues)
                    )

                    logger.warning(
                        "DEBUG_should_use_enhanced",
                        should_use_enhanced=should_use_enhanced,
                        condition1=existing_has_issues and not enhanced_has_issues,
                        condition2=len(enhanced_result.line_items) > len(existing_items) and not enhanced_has_issues,
                    )

                    if should_use_enhanced:
                        from app.services.extraction import convert_to_schema_line_item
                        invoice.line_items = [
                            ExtractedLineItem(**convert_to_schema_line_item(item))
                            for item in enhanced_result.line_items
                        ]
                        logger.info(
                            "using_enhanced_line_items",
                            reason="better_quality" if existing_has_issues else "more_items",
                            existing_count=len(existing_items),
                            enhanced_count=len(enhanced_result.line_items),
                            existing_had_issues=existing_has_issues,
                        )
                    else:
                        logger.warning(
                            "DEBUG_keeping_existing_line_items",
                            reason="enhanced_not_better",
                            existing_count=len(existing_items),
                            enhanced_count=len(enhanced_result.line_items),
                        )

                # Validierungs-Warnungen hinzufuegen
                for v in enhanced_result.validations:
                    if not v.is_valid:
                        invoice.extraction_warnings = (
                            list(invoice.extraction_warnings) + [v.message]
                        )

                if enhanced_result.needs_review:
                    invoice.needs_review = True

                logger.debug(
                    "enhanced_extraction_applied",
                    payment_terms_improved=enhanced_result.payment_terms is not None,
                    amounts_improved=enhanced_result.amounts is not None,
                    line_items_count=len(enhanced_result.line_items),
                    confidence=enhanced_result.overall_confidence,
                )

            except Exception as e:
                logger.warning(
                    "enhanced_extraction_failed",
                    error=str(e),
                )
                # Nicht kritisch - regulaere Extraktion bleibt erhalten

        # === REVERSE CHARGE HEURISTIK (nach Enhanced Extraction wiederholen) ===
        # Jetzt ist vat_rate moeglicherweise aus dem AmountExtractor bekannt
        if not invoice.is_reverse_charge:
            sender_country = invoice.sender_vat_id[:2] if invoice.sender_vat_id else None
            recipient_country = invoice.recipient_vat_id[:2] if invoice.recipient_vat_id else None

            # Fall 1: Unterschiedliche EU-Laender + VAT Rate 0
            if (
                sender_country and recipient_country and
                sender_country != recipient_country and
                invoice.vat_rate == Decimal("0")
            ):
                invoice.is_reverse_charge = True
                invoice.intra_community_supply = True
                invoice.vat_exemption_reason = "Innergemeinschaftliche Lieferung (inferiert)"
                logger.info(
                    "reverse_charge_inferred_post_enhanced",
                    sender_country=sender_country,
                    recipient_country=recipient_country,
                    vat_rate=str(invoice.vat_rate),
                )

            # Fall 2: Unterschiedliche EU-Laender ohne MwSt-Betrag (auch bei vat_rate=None)
            elif (
                sender_country and recipient_country and
                sender_country != recipient_country and
                not invoice.vat_amount
            ):
                invoice.is_reverse_charge = True
                invoice.intra_community_supply = True
                invoice.vat_exemption_reason = "Innergemeinschaftliche Lieferung (inferiert)"
                logger.info(
                    "reverse_charge_inferred_no_vat",
                    sender_country=sender_country,
                    recipient_country=recipient_country,
                )

        # Plausibilitaetspruefung
        invoice = self._validate_invoice(invoice)

        # === REVERSE CHARGE POST-VALIDATION FIX ===
        # Falls _validate_invoice() is_reverse_charge gesetzt hat, vat_amount=0 setzen
        if invoice.is_reverse_charge and invoice.vat_amount is None:
            invoice.vat_amount = Decimal("0")
            invoice.vat_rate = Decimal("0") if invoice.vat_rate is None else invoice.vat_rate
            invoice.vat_amount_source = AmountSource.COMPUTED
            # vat_reason setzen (wichtig fuer Audit-Trail)
            if invoice.intra_community_supply:
                invoice.vat_reason = "intra-community supply / reverse charge"
            else:
                invoice.vat_reason = "reverse charge"
            logger.info(
                "reverse_charge_vat_zeroed_post_validation",
                reason="vat_amount=0 set after _validate_invoice detected RC",
                vat_reason=invoice.vat_reason,
            )

        # === BRUTTO BERECHNUNG (falls nicht aus Dokument extrahiert) ===
        # Wenn gross_amount nicht gefunden aber net_amount und vat_amount vorhanden
        if (
            invoice.gross_amount is None and
            invoice.net_amount is not None and
            invoice.vat_amount is not None
        ):
            invoice.gross_amount = invoice.net_amount + invoice.vat_amount
            invoice.gross_amount_source = AmountSource.COMPUTED
            logger.debug(
                "gross_amount_computed",
                net=str(invoice.net_amount),
                vat=str(invoice.vat_amount),
                gross=str(invoice.gross_amount),
            )

        # === VALIDIERUNGEN ERSTELLEN ===
        # Field-Confidence sammeln (basierend auf Extraktion)
        field_confidence: Dict[str, float] = {}
        if invoice.invoice_number:
            field_confidence["invoice_number"] = 0.95
        if invoice.invoice_date:
            field_confidence["invoice_date"] = 0.90
        if invoice.net_amount:
            field_confidence["net_amount"] = 0.85
        if invoice.gross_amount:
            # Confidence basierend auf Source
            field_confidence["gross_amount"] = (
                0.95 if invoice.gross_amount_source == AmountSource.DOCUMENT else 0.80
            )
        if invoice.sender_bank and invoice.sender_bank.iban:
            field_confidence["iban"] = 0.99  # IBAN-Checksum ist sehr zuverlaessig
        if invoice.sender_vat_id:
            field_confidence["sender_vat_id"] = 0.95

        # Validierungen erstellen
        invoice.validations = self._build_validations(invoice, field_confidence)

        return invoice

    def _has_low_quality_line_items(self, items: List[ExtractedLineItem]) -> bool:
        """
        Prueft ob Line Items verdaechtig schlecht sind.

        Erkennt:
        - Header-Text in Beschreibungen (z.B. "Description No.")
        - Null-Preise
        - Unplausible Mengen (Bruchzahlen wie 1.3 statt 384)
        """
        if not items:
            return True

        header_indicators = [
            'description', 'beschreibung', 'quantity', 'menge',
            'amount', 'betrag', 'price', 'preis', 'no.', 'nr.',
            'unit', 'einheit', 'total', 'summe'
        ]

        for item in items:
            desc = (item.description or "").lower().strip()

            # Kurze Beschreibung mit Header-Text = schlecht
            if len(desc) < 20:
                for header in header_indicators:
                    if header in desc:
                        logger.debug(
                            "low_quality_line_item_detected",
                            reason="header_in_description",
                            description=item.description,
                            header_found=header,
                        )
                        return True

            # Beide Preise 0 oder None = verdaechtig
            total_zero = item.total_price == Decimal(0) or item.total_price is None
            unit_zero = item.unit_price == Decimal(0) or item.unit_price is None
            if total_zero and unit_zero:
                logger.debug(
                    "low_quality_line_item_detected",
                    reason="zero_prices",
                    description=item.description,
                )
                return True

            # Unplausible Mengen (Bruchzahlen wie 1.3)
            if item.quantity and Decimal(0) < item.quantity < Decimal(1):
                logger.debug(
                    "low_quality_line_item_detected",
                    reason="fractional_quantity",
                    quantity=str(item.quantity),
                    description=item.description,
                )
                return True

        return False

    def _has_low_quality_line_items_enhanced(self, items: List) -> bool:
        """
        Prueft Enhanced Line Items (anderes Dataclass-Format).

        Gleiche Logik wie _has_low_quality_line_items, aber fuer
        das ExtractedLineItem-Dataclass aus dem Enhanced Extractor.
        """
        if not items:
            return True

        header_indicators = [
            'description', 'beschreibung', 'quantity', 'menge',
            'amount', 'betrag', 'price', 'preis', 'no.', 'nr.'
        ]

        for item in items:
            desc = (item.description or "").lower().strip()

            # Kurze Beschreibung mit Header-Text = schlecht
            if len(desc) < 20:
                for header in header_indicators:
                    if header in desc:
                        logger.debug(
                            "low_quality_enhanced_item_detected",
                            reason="header_in_description",
                            description=item.description,
                            header_found=header,
                        )
                        return True

            # Beide Preise 0 oder None = verdaechtig
            total_zero = item.total_price == Decimal(0) or item.total_price is None
            unit_zero = item.unit_price == Decimal(0) or item.unit_price is None
            if total_zero and unit_zero:
                logger.debug(
                    "low_quality_enhanced_item_detected",
                    reason="zero_prices",
                    description=item.description,
                )
                return True

            # Unplausible Mengen (Bruchzahlen wie 1.3)
            if item.quantity and Decimal(0) < item.quantity < Decimal(1):
                logger.debug(
                    "low_quality_enhanced_item_detected",
                    reason="fractional_quantity",
                    quantity=str(item.quantity),
                    description=item.description,
                )
                return True

        return False

    def _validate_invoice(self, invoice: ExtractedInvoiceData) -> ExtractedInvoiceData:
        """Prueft Plausibilitaet der Rechnungsdaten."""
        warnings = list(invoice.extraction_warnings)
        confidence = 0.5  # Basis-Konfidenz

        # Rechnungsnummer gefunden?
        if invoice.invoice_number:
            confidence += 0.15

        # Rechnungsdatum gefunden?
        if invoice.invoice_date:
            confidence += 0.10

        # Betraege vorhanden?
        if invoice.gross_amount:
            confidence += 0.10

        # Netto + MwSt = Brutto?
        if invoice.net_amount and invoice.vat_amount and invoice.gross_amount:
            expected = invoice.net_amount + invoice.vat_amount
            tolerance = Decimal("0.10")  # 10 Cent Toleranz
            if abs(expected - invoice.gross_amount) <= tolerance:
                confidence += 0.15
            else:
                warnings.append(
                    f"Betragsinkonsistenz: {invoice.net_amount} + {invoice.vat_amount} = "
                    f"{invoice.net_amount + invoice.vat_amount} != {invoice.gross_amount}"
                )
                invoice.needs_review = True

        # MwSt-Satz plausibel?
        if invoice.vat_rate:
            if invoice.vat_rate in [Decimal("7"), Decimal("19"), Decimal("0")]:
                confidence += 0.05
            else:
                warnings.append(f"Ungewoehnlicher MwSt-Satz: {invoice.vat_rate}%")

        # IBAN-Validierung (bereits in Entity-Service)
        if invoice.sender_bank and invoice.sender_bank.iban:
            confidence += 0.10

        # Skonto-Berechnung plausibel?
        if invoice.discount_percent and invoice.discount_days:
            if invoice.discount_percent <= Decimal("5") and invoice.discount_days <= 30:
                confidence += 0.05
            else:
                warnings.append(
                    f"Ungewoehnliche Skonto-Bedingungen: {invoice.discount_percent}% / {invoice.discount_days} Tage"
                )

        # Positionen gefunden?
        if invoice.line_items:
            confidence += 0.05  # Bonus fuer gefundene Positionen

            # Positionssumme vs. Gesamtbetrag validieren
            line_items_total = sum(
                item.total_price for item in invoice.line_items
                if item.total_price is not None
            )

            # Vergleiche mit Netto- oder Bruttobetrag
            reference_amount = invoice.net_amount or invoice.gross_amount
            if line_items_total and reference_amount:
                tolerance = Decimal("1.00")  # 1 EUR Toleranz fuer Rundungsfehler
                difference = abs(line_items_total - reference_amount)

                if difference <= tolerance:
                    # Summen stimmen ueberein - Confidence-Boost
                    confidence += 0.15
                else:
                    # Summen weichen ab - Confidence reduzieren
                    # Je groesser die Abweichung, desto mehr Reduktion
                    deviation_percent = (difference / reference_amount) * 100 if reference_amount else Decimal(0)

                    if deviation_percent <= Decimal("5"):
                        # Kleine Abweichung (<5%) - leichte Reduktion
                        confidence -= 0.05
                        warnings.append(
                            f"Leichte Abweichung: Positionssumme ({line_items_total:.2f} €) vs. "
                            f"Gesamtbetrag ({reference_amount:.2f} €) - Differenz: {difference:.2f} €"
                        )
                    elif deviation_percent <= Decimal("20"):
                        # Mittlere Abweichung (5-20%) - deutliche Reduktion
                        confidence -= 0.15
                        warnings.append(
                            f"Abweichung: Positionssumme ({line_items_total:.2f} €) weicht von "
                            f"Gesamtbetrag ({reference_amount:.2f} €) ab - Differenz: {difference:.2f} €"
                        )
                        invoice.needs_review = True
                    else:
                        # Grosse Abweichung (>20%) - starke Reduktion
                        confidence -= 0.25
                        warnings.append(
                            f"Starke Abweichung: Positionssumme ({line_items_total:.2f} €) vs. "
                            f"Gesamtbetrag ({reference_amount:.2f} €) - Differenz: {difference:.2f} € "
                            f"({deviation_percent:.0f}%)"
                        )
                        invoice.needs_review = True

        # === REVERSE CHARGE AUTO-ERKENNUNG ===
        # Automatisch setzen bei: MwSt=0 + Cross-Border EU-Transaktion
        if (
            (invoice.vat_amount is None or invoice.vat_amount == Decimal("0"))
            and invoice.sender_vat_id
            and invoice.recipient_vat_id
        ):
            sender_country = invoice.sender_vat_id[:2].upper()
            recipient_country = invoice.recipient_vat_id[:2].upper()

            if sender_country != recipient_country and not invoice.is_reverse_charge:
                warnings.append(
                    f"MwSt=0 bei {sender_country}->{recipient_country}: "
                    f"Reverse Charge automatisch gesetzt"
                )
                invoice.is_reverse_charge = True
                invoice.intra_community_supply = True
                if not invoice.vat_exemption_reason:
                    invoice.vat_exemption_reason = "Innergemeinschaftliche Lieferung (auto)"
                logger.info(
                    "reverse_charge_auto_detected",
                    sender_country=sender_country,
                    recipient_country=recipient_country,
                )

        invoice.extraction_confidence = min(max(confidence, 0.10), 0.99)  # Min 10%, Max 99%
        invoice.extraction_warnings = warnings

        return invoice

    def _build_validations(
        self,
        invoice: ExtractedInvoiceData,
        field_confidence: Optional[Dict[str, float]] = None,
    ) -> ExtractionValidations:
        """
        Erstellt strukturierte Validierungsergebnisse fuer Audit und Qualitaetssicherung.

        Prueft:
        - IBAN MOD-97 Checksum
        - IBAN-Land vs. Absender-Land
        - USt-IdNr-Land vs. Absender-Land
        - Summen-Konsistenz (Line Items vs. Netto)

        Args:
            invoice: Extrahierte Rechnungsdaten
            field_confidence: Optional Dict mit Feld-Konfidenz (0.0-1.0)

        Returns:
            ExtractionValidations mit allen Pruefungsergebnissen
        """
        validations = ExtractionValidations()

        # === IBAN-Validierung ===
        if invoice.sender_bank and invoice.sender_bank.iban:
            # Import lokale IBAN-Validierung
            try:
                from app.services.extraction.patterns.reference_patterns import validate_iban
                validations.iban_checksum_valid = validate_iban(invoice.sender_bank.iban)
            except ImportError:
                # Fallback: Eigene MOD-97 Validierung
                iban = invoice.sender_bank.iban.replace(" ", "").upper()
                if len(iban) >= 5:
                    # IBAN rearrangieren (4 Zeichen von vorne nach hinten)
                    rearranged = iban[4:] + iban[:4]
                    # Buchstaben zu Zahlen konvertieren (A=10, B=11, ...)
                    numeric = ""
                    for char in rearranged:
                        if char.isdigit():
                            numeric += char
                        else:
                            numeric += str(ord(char.upper()) - ord('A') + 10)
                    # MOD-97 Pruefung
                    try:
                        validations.iban_checksum_valid = int(numeric) % 97 == 1
                    except ValueError:
                        validations.iban_checksum_valid = None

            # IBAN-Land vs. Absender-Land
            iban_country = invoice.sender_bank.iban[:2].upper()
            sender_country = None
            if invoice.sender and invoice.sender.country:
                sender_country = invoice.sender.country.upper()
            if sender_country:
                validations.iban_country_match = iban_country == sender_country
            else:
                validations.iban_country_match = None  # Nicht pruefbar

        # === USt-IdNr-Validierung ===
        if invoice.sender_vat_id and invoice.sender:
            vat_country = invoice.sender_vat_id[:2].upper() if len(invoice.sender_vat_id) >= 2 else None
            sender_country = invoice.sender.country.upper() if invoice.sender.country else None
            if vat_country and sender_country:
                validations.vat_country_match = vat_country == sender_country

        # === Summen-Konsistenz (Line Items vs. Netto) ===
        if invoice.line_items and invoice.net_amount:
            line_sum = sum(
                item.total_price for item in invoice.line_items
                if item.total_price is not None
            )
            if line_sum > Decimal("0"):
                # Toleranz: max(1% vom Netto, 2 EUR)
                tolerance = max(invoice.net_amount * Decimal("0.01"), Decimal("2.00"))
                diff = abs(line_sum - invoice.net_amount)
                validations.sums_match = diff <= tolerance
                if not validations.sums_match:
                    validations.sums_difference = diff

        # === Field-Level Confidence ===
        if field_confidence:
            validations.field_confidence = field_confidence

        return validations

    # =========================================================================
    # VAT ID ATTRIBUTION
    # =========================================================================

    def _attribute_vat_ids(
        self,
        vat_ids: List[Any],
        addresses: List[Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Intelligente USt-IdNr Zuordnung basierend auf:
        1. Laendercode-Matching (NL VAT -> NL Adresse)
        2. Adress-Rolle (sender/recipient)
        3. Position/Proximity im Text
        4. Cross-Border Heuristik (Non-DE = sender, DE = recipient)

        Args:
            vat_ids: Liste von ExtractedIdentifier mit identifier_type="vat_id"
            addresses: Liste von ExtractedAddress mit role-Attribut

        Returns:
            Tuple von (sender_vat_id, recipient_vat_id)
        """
        sender_vat: Optional[str] = None
        recipient_vat: Optional[str] = None

        if not vat_ids:
            return None, None

        # Erstelle Lookup fuer Adressen nach Laendercode und Rolle
        sender_countries: set = set()
        recipient_countries: set = set()

        for addr in addresses:
            country = getattr(addr, 'country', None) or "DE"
            role = getattr(addr, 'role', None)

            if role == "sender":
                sender_countries.add(country.upper())
            elif role == "recipient":
                recipient_countries.add(country.upper())

        logger.debug(
            "vat_attribution_context",
            vat_count=len(vat_ids),
            sender_countries=list(sender_countries),
            recipient_countries=list(recipient_countries),
        )

        # 1. Pass: Laendercode-Matching (hoechste Prioritaet)
        for vat in vat_ids:
            country = getattr(vat, 'country_code', None)
            if not country:
                # Fallback: Extrahiere Laendercode aus normalized_value
                normalized = vat.normalized_value
                if len(normalized) >= 2:
                    country = normalized[:2].upper()

            if country:
                if country in sender_countries and not sender_vat:
                    sender_vat = vat.normalized_value
                    logger.debug(
                        "vat_attributed_by_country",
                        vat_id=sender_vat,
                        country=country,
                        role="sender",
                    )
                elif country in recipient_countries and not recipient_vat:
                    recipient_vat = vat.normalized_value
                    logger.debug(
                        "vat_attributed_by_country",
                        vat_id=recipient_vat,
                        country=country,
                        role="recipient",
                    )

        # 2. Pass: Proximity-basierte Zuordnung (falls noch nicht zugeordnet)
        if (not sender_vat or not recipient_vat) and addresses:
            for vat in vat_ids:
                if vat.normalized_value in (sender_vat, recipient_vat):
                    continue

                # Finde naechste Adresse
                nearest_addr = self._find_nearest_address(
                    vat.position_start, addresses
                )
                if nearest_addr:
                    role = getattr(nearest_addr, 'role', None)
                    if role == "sender" and not sender_vat:
                        sender_vat = vat.normalized_value
                        logger.debug(
                            "vat_attributed_by_proximity",
                            vat_id=sender_vat,
                            role="sender",
                        )
                    elif role == "recipient" and not recipient_vat:
                        recipient_vat = vat.normalized_value
                        logger.debug(
                            "vat_attributed_by_proximity",
                            vat_id=recipient_vat,
                            role="recipient",
                        )

        # 3. Pass: Cross-Border Heuristik (bei innergemeinschaftlichen Lieferungen)
        # Non-DE VAT = typischerweise sender, DE VAT = recipient
        if len(vat_ids) >= 2 and (not sender_vat or not recipient_vat):
            de_vats = [v for v in vat_ids if v.normalized_value.startswith("DE")]
            non_de_vats = [v for v in vat_ids if not v.normalized_value.startswith("DE")]

            if non_de_vats and de_vats:
                if not sender_vat:
                    sender_vat = non_de_vats[0].normalized_value
                    logger.debug(
                        "vat_attributed_by_crossborder_heuristic",
                        vat_id=sender_vat,
                        role="sender",
                        reason="non_de_vat_is_typically_foreign_supplier",
                    )
                if not recipient_vat:
                    recipient_vat = de_vats[0].normalized_value
                    logger.debug(
                        "vat_attributed_by_crossborder_heuristic",
                        vat_id=recipient_vat,
                        role="recipient",
                        reason="de_vat_is_typically_local_customer",
                    )

        # 4. Ultimate Fallback: Erste VAT-ID = sender (Rueckwaertskompatibilitaet)
        if not sender_vat and vat_ids:
            sender_vat = vat_ids[0].normalized_value
            logger.debug(
                "vat_attributed_by_fallback",
                vat_id=sender_vat,
                role="sender",
                reason="first_vat_id_fallback",
            )

        return sender_vat, recipient_vat

    def _find_nearest_address(
        self,
        position: int,
        addresses: List[Any],
    ) -> Optional[Any]:
        """
        Finde die naechste Adresse zu einer Textposition.

        Args:
            position: Position im Text
            addresses: Liste von ExtractedAddress

        Returns:
            Naechste Adresse oder None
        """
        if not addresses:
            return None

        nearest = None
        min_distance = float('inf')

        for addr in addresses:
            addr_position = getattr(addr, 'position_start', 0)
            distance = abs(position - addr_position)
            if distance < min_distance:
                min_distance = distance
                nearest = addr

        return nearest

    def _validate_vat_country_match(
        self,
        vat_id: Optional[str],
        address_country: Optional[str],
    ) -> bool:
        """
        Prueft ob USt-IdNr zum Adressland passt (Phase 3: Laender-Validierung).

        Bei Mismatch wird True zurueckgegeben wenn die Validierung fehlschlaegt,
        damit eine Warnung generiert werden kann.

        Args:
            vat_id: USt-IdNr (z.B. "NL820594829B01")
            address_country: Land aus Adresse (z.B. "NL", "Nederland", "Niederlande")

        Returns:
            True wenn VAT und Land zusammenpassen, False bei Mismatch
        """
        if not vat_id or not address_country:
            return True  # Kann nicht validieren - kein Fehler

        # VAT-Laendercode extrahieren (erste 2 Zeichen)
        vat_country = vat_id[:2].upper()

        # Adress-Land normalisieren
        addr_country = address_country.strip().upper()

        # Mapping anwenden (mehrsprachige Laendernamen -> ISO Code)
        addr_country_lower = address_country.strip().lower()
        if addr_country_lower in COUNTRY_NAME_TO_CODE:
            addr_country = COUNTRY_NAME_TO_CODE[addr_country_lower]

        # Vergleich
        if vat_country == addr_country:
            return True

        # Sonderfall: Wenn addr_country zu kurz ist (z.B. nur "D" fuer Deutschland)
        # und wir keinen Match haben, versuche laengere Varianten
        if len(addr_country) <= 2 and vat_country != addr_country:
            logger.debug(
                "vat_country_mismatch",
                vat_id=vat_id,
                vat_country=vat_country,
                address_country=address_country,
                normalized_addr_country=addr_country,
            )
            return False

        return True

    # =========================================================================
    # ORDER EXTRACTION
    # =========================================================================

    async def _extract_order_data(
        self,
        text: str,
        entities: Any,
        tables: Optional[List[Any]] = None
    ) -> ExtractedOrderData:
        """Extrahiert Bestelldaten inkl. Positionen aus Tabellen."""
        order = ExtractedOrderData()

        # Referenznummern
        order.order_number = self._extract_first_match(
            ReferencePatterns.ORDER_NUMBER, text
        )
        order.quotation_number = self._extract_first_match(
            ReferencePatterns.QUOTATION_NUMBER, text
        )
        order.customer_order_number = self._extract_first_match(
            ReferencePatterns.CUSTOMER_NUMBER, text
        )

        # Daten
        order.order_date = self._extract_labeled_date(
            DatePatterns.ORDER_DATE, text
        ) or self._extract_first_date(text)

        order.delivery_date = self._extract_labeled_date(
            DatePatterns.DELIVERY_DATE, text
        )

        # Betraege
        order.total_amount = self._extract_labeled_amount(
            AmountPatterns.GROSS_AMOUNT, text
        )

        # Adressen
        if entities.addresses:
            if len(entities.addresses) >= 1:
                addr = entities.addresses[0]
                order.orderer = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )
            if len(entities.addresses) >= 2:
                addr = entities.addresses[1]
                order.supplier = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )

        # Firmenname
        if entities.company_names:
            if order.orderer:
                order.orderer.company = entities.company_names[0].name

        # Zahlungsbedingungen
        payment_days_match = PaymentPatterns.PAYMENT_DAYS.search(text)
        if payment_days_match:
            order.payment_terms = f"{payment_days_match.group(1)} Tage netto"

        # === LINE ITEMS EXTRAKTION ===
        # Aus Docling-Tabellen extrahieren
        if tables:
            try:
                line_item_service = _get_line_item_service()
                order.line_items = await line_item_service.extract_from_tables(tables)
                logger.debug(
                    "order_line_items_extracted",
                    count=len(order.line_items),
                    from_tables=len(tables),
                )
            except Exception as e:
                logger.warning(
                    "order_line_item_extraction_failed",
                    error=str(e),
                    table_count=len(tables),
                )

        # Falls keine Tabellen: Regex-Fallback
        if not order.line_items and text:
            try:
                line_item_service = _get_line_item_service()
                order.line_items = await line_item_service.extract_from_text(text)
            except Exception as e:
                logger.debug("order_line_item_text_fallback_failed", error=str(e))

        # Konfidenz
        confidence = 0.5
        if order.order_number:
            confidence += 0.20
        if order.order_date:
            confidence += 0.15
        if order.delivery_date:
            confidence += 0.10
        if order.total_amount:
            confidence += 0.10
        if order.line_items:
            confidence += 0.05  # Bonus fuer gefundene Positionen

        order.extraction_confidence = min(confidence, 0.99)

        return order

    # =========================================================================
    # CONTRACT EXTRACTION
    # =========================================================================

    def _extract_contract_data(
        self,
        text: str,
        entities: Any
    ) -> ExtractedContractData:
        """Extrahiert Vertragsdaten."""
        contract = ExtractedContractData()

        # Vertragsnummer
        contract.contract_number = self._extract_first_match(
            ReferencePatterns.CONTRACT_NUMBER, text
        )

        # Daten
        contract.contract_date = self._extract_first_date(text)

        # Leistungszeitraum = Vertragszeitraum?
        period_match = DatePatterns.SERVICE_PERIOD.search(text)
        if period_match:
            contract.start_date = self._parse_date_groups(
                period_match.group(1),
                period_match.group(2),
                period_match.group(3)
            )
            contract.end_date = self._parse_date_groups(
                period_match.group(4),
                period_match.group(5),
                period_match.group(6)
            )

        # Vertragslaufzeit
        duration_match = DatePatterns.CONTRACT_DURATION.search(text)
        if duration_match:
            duration = int(duration_match.group(1))
            unit = duration_match.group(2).lower()

            if "monat" in unit:
                contract.duration_months = duration
            elif "jahr" in unit:
                contract.duration_months = duration * 12
            elif "woche" in unit:
                contract.duration_months = max(1, duration // 4)

        # Kuendigungsfrist
        notice_match = DatePatterns.NOTICE_PERIOD.search(text)
        if notice_match:
            notice_value = notice_match.group(1)
            notice_unit = notice_match.group(2)
            notice_deadline = notice_match.group(3) if len(notice_match.groups()) > 2 else None

            notice_text = f"{notice_value} {notice_unit}"
            if notice_deadline:
                notice_text += f" zum {notice_deadline}"
            contract.notice_period = notice_text

        # Automatische Verlaengerung suchen
        if re.search(r'verl[aä]nger(?:t|ung)|auto(?:matisch)?.*?renew', text, re.IGNORECASE):
            contract.auto_renewal = True

        # Betraege
        contract.contract_value = self._extract_labeled_amount(
            AmountPatterns.GROSS_AMOUNT, text
        )

        # Monatlicher Betrag (auch "Monatlicher Betrag: 1.000,00 EUR")
        monthly_match = re.search(
            r'(?:monatlich(?:er|e|es)?(?:\s+betrag)?|mtl\.?|pro\s*monat)[\s:]*'
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR)?',
            text,
            re.IGNORECASE
        )
        if monthly_match:
            contract.monthly_value = self._parse_german_amount(monthly_match.group(1))

        # Vertragsparteien
        if entities.addresses:
            if len(entities.addresses) >= 1:
                addr = entities.addresses[0]
                contract.party_a = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )
            if len(entities.addresses) >= 2:
                addr = entities.addresses[1]
                contract.party_b = ExtractedAddress(
                    street=addr.street,
                    zip_code=addr.postal_code,
                    city=addr.city,
                )

        # Firmennamen
        if entities.company_names:
            if contract.party_a and len(entities.company_names) >= 1:
                contract.party_a.company = entities.company_names[0].name
            if contract.party_b and len(entities.company_names) >= 2:
                contract.party_b.company = entities.company_names[1].name

        # Vertragstyp erkennen
        if re.search(r'miet(?:vertrag)?|pacht', text, re.IGNORECASE):
            contract.contract_type = "Mietvertrag"
        elif re.search(r'dienst(?:leistungs?)?(?:vertrag)?|service', text, re.IGNORECASE):
            contract.contract_type = "Dienstleistungsvertrag"
        elif re.search(r'arbeits(?:vertrag)?', text, re.IGNORECASE):
            contract.contract_type = "Arbeitsvertrag"
        elif re.search(r'kauf(?:vertrag)?', text, re.IGNORECASE):
            contract.contract_type = "Kaufvertrag"
        elif re.search(r'rahmen(?:vertrag)?', text, re.IGNORECASE):
            contract.contract_type = "Rahmenvertrag"

        # Konfidenz
        confidence = 0.5
        if contract.contract_number:
            confidence += 0.15
        if contract.start_date or contract.end_date:
            confidence += 0.15
        if contract.notice_period:
            confidence += 0.10
        if contract.duration_months:
            confidence += 0.10
        if contract.contract_type:
            confidence += 0.10

        contract.extraction_confidence = min(confidence, 0.99)

        return contract

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _is_likely_label(self, value: str) -> bool:
        """Prueft ob ein Wert wahrscheinlich ein Label ist.

        FIX 2025-12-15: Verhindert dass Labels wie "Kunden-Nr." oder
        "Rechnungsdatum" als Rechnungsnummern extrahiert werden.
        """
        if not value:
            return True
        value_clean = value.lower().replace('-', '').replace('.', '').replace(' ', '')
        return any(kw in value_clean for kw in ReferencePatterns.LABEL_KEYWORDS)

    def _extract_invoice_number_with_validation(self, text: str) -> Optional[str]:
        """Extrahiert Rechnungsnummer mit vendor-spezifischen Patterns und Label-Skip.

        FIX 2025-12-15: Erweiterte Extraktion fuer:
        - Asal: RG20012108
        - Amefa: CD4921000467
        - AUER: VK 1036735, D119925
        - a.b.s.: 6-stellige Nummer vor Datum
        - Standard: Rechnungsnr., Invoice No., etc.

        Die Label-Skip-Logik verhindert dass Labels wie "Kunden-Nr." oder
        "Rechnungsdatum" faelschlicherweise als Rechnungsnummern extrahiert werden.
        """
        # 1. Vendor-spezifische Patterns ZUERST (hoechste Prioritaet)
        # Diese sind sehr spezifisch und daher zuverlaessig

        # Asal: RG + 8 digits
        match = ReferencePatterns.INVOICE_NUMBER_RG.search(text)
        if match:
            number = match.group(1).strip()
            if not self._is_likely_label(number):
                return number

        # Amefa: CD + 10 digits
        match = ReferencePatterns.INVOICE_NUMBER_CD.search(text)
        if match:
            number = match.group(1).strip()
            if not self._is_likely_label(number):
                return number

        # AUER: VK + 7 digits
        match = ReferencePatterns.INVOICE_NUMBER_VK.search(text)
        if match:
            number = f"VK{match.group(1).strip()}"
            if not self._is_likely_label(number):
                return number

        # AUER Delivery: D + 5-6 digits
        match = ReferencePatterns.INVOICE_NUMBER_D.search(text)
        if match:
            number = match.group(1).strip()
            if not self._is_likely_label(number):
                return number

        # a.b.s. Rechenzentrum: 6-digit followed by date
        match = ReferencePatterns.INVOICE_NUMBER_ABS.search(text)
        if match:
            number = match.group(1).strip()
            if not self._is_likely_label(number):
                return number

        # a.b.s. Rechenzentrum VERTIKALES Layout:
        # Labels vertikal, dann Werte vertikal
        # FIX 2025-12-15: Behebt das Problem wo "Kunden-Nr." als Rechnungsnummer
        # extrahiert wurde weil das Standard-Pattern den naechsten Text nach
        # "Rechnungs-Nr." nahm (was bei vertikalem Layout das naechste Label war)
        match = ReferencePatterns.INVOICE_NUMBER_VERTICAL_LAYOUT.search(text)
        if match:
            number = match.group(1).strip()
            if not self._is_likely_label(number):
                logger.debug(
                    "vertical_layout_invoice_number_extracted",
                    invoice_number=number,
                    pattern="INVOICE_NUMBER_VERTICAL_LAYOUT"
                )
                return number

        # 2. Standard REVERSE format (value before label - common in tables)
        match = ReferencePatterns.INVOICE_NUMBER_REVERSE.search(text)
        if match:
            number = match.group(1).strip()
            if not self._is_likely_label(number):
                return number

        # 3. Standard format (label before value)
        match = ReferencePatterns.INVOICE_NUMBER.search(text)
        if match:
            number = match.group(1).strip()
            if not self._is_likely_label(number):
                return number

        # 4. Fallback: Fragmentierte Referenz
        fragmented = self._extract_fragmented_reference(text, [
            'invoice no', 'rechnungsnr', 'rechnungs-nr', 'factuurnr'
        ])
        if fragmented and not self._is_likely_label(fragmented):
            return fragmented

        return None

    def _extract_first_match(
        self,
        pattern: re.Pattern,
        text: str
    ) -> Optional[str]:
        """Extrahiert den ersten Match eines Patterns."""
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return None

    def _extract_labeled_amount(
        self,
        pattern: re.Pattern,
        text: str
    ) -> Optional[Decimal]:
        """Extrahiert einen Betrag mit Label."""
        match = pattern.search(text)
        if match:
            return self._parse_german_amount(match.group(1))
        return None

    def _extract_labeled_date(
        self,
        pattern: re.Pattern,
        text: str
    ) -> Optional[date]:
        """Extrahiert ein Datum mit Label."""
        match = pattern.search(text)
        if match:
            return self._parse_date_groups(
                match.group(1),
                match.group(2),
                match.group(3)
            )
        return None

    def _extract_first_date(self, text: str) -> Optional[date]:
        """Extrahiert das erste gefundene Datum."""
        match = DatePatterns.DATE_DE.search(text)
        if match:
            return self._parse_date_groups(
                match.group(1),
                match.group(2),
                match.group(3)
            )
        return None

    def _extract_fragmented_reference(
        self,
        text: str,
        labels: List[str]
    ) -> Optional[str]:
        """
        Extrahiert Referenznummer aus fragmentiertem OCR-Text.

        Sucht nach Pattern wie:
            V-210089
            Order No.

        Wo das Label NACH der Referenz auf einer separaten Zeile steht.
        Sucht die NÄCHSTE vorherige Zeile die eine Referenz sein könnte.
        """
        lines = text.split('\n')

        # Referenz-Pattern: Alphanumerisch mit Bindestrichen/Punkten
        ref_pattern = re.compile(
            r'^([A-Z][-A-Z0-9/\.]{2,25})$',  # Muss mit Buchstabe beginnen
            re.IGNORECASE
        )

        for i, line in enumerate(lines):
            line = line.strip()

            # Prüfe ob diese Zeile ein Label ist
            line_lower = line.lower()
            for label in labels:
                if label in line_lower:
                    # Gefunden! Suche Referenz in der DIREKT vorherigen Zeile zuerst
                    # dann weiter zurück (max 3)
                    for j in range(i - 1, max(-1, i - 4), -1):
                        if j < 0:
                            break
                        prev_line = lines[j].strip()
                        match = ref_pattern.match(prev_line)
                        if match:
                            ref = match.group(1)
                            # Validiere: Keine reinen Zahlen, keine Daten, keine anderen Labels
                            is_date = re.match(r'^\d{2}[-./]\d{2}[-./]\d{2,4}$', ref)
                            is_label = any(lbl in prev_line.lower() for lbl in [
                                'no.', 'nr.', 'date', 'datum', 'bank', 'iban'
                            ])
                            if not is_date and not is_label:
                                logger.debug(
                                    "fragmented_reference_extracted",
                                    label=label,
                                    reference=ref,
                                    line_index=j,
                                )
                                return ref
        return None

    def _extract_fragmented_date(
        self,
        text: str,
        labels: List[str]
    ) -> Optional[date]:
        """
        Extrahiert Datum aus fragmentiertem OCR-Text.

        Sucht nach Pattern wie:
            06-04-20
            Factuurdatum

        Wo das Label NACH dem Datum auf einer separaten Zeile steht.
        """
        lines = text.split('\n')

        # Datum-Pattern: DD-MM-YY oder DD.MM.YY oder DD/MM/YY
        date_pattern = re.compile(
            r'^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})$'
        )

        for i, line in enumerate(lines):
            line = line.strip()

            # Prüfe ob diese Zeile ein Label ist
            line_lower = line.lower()
            for label in labels:
                if label in line_lower:
                    # Gefunden! Suche Datum in vorherigen Zeilen (max 3)
                    for j in range(max(0, i - 3), i):
                        prev_line = lines[j].strip()
                        match = date_pattern.match(prev_line)
                        if match:
                            result = self._parse_date_groups(
                                match.group(1),
                                match.group(2),
                                match.group(3)
                            )
                            if result:
                                logger.debug(
                                    "fragmented_date_extracted",
                                    label=label,
                                    date_str=prev_line,
                                    result=str(result),
                                )
                                return result
        return None

    def _extract_all_dates(self, text: str) -> List[date]:
        """Extrahiert alle Daten aus dem Text."""
        if not text:
            return []
        dates = []
        for match in DatePatterns.DATE_DE.finditer(text):
            d = self._parse_date_groups(
                match.group(1),
                match.group(2),
                match.group(3)
            )
            if d and d not in dates:
                dates.append(d)
        return dates

    def _extract_all_amounts(self, text: str) -> List[Decimal]:
        """Extrahiert alle Betraege aus dem Text."""
        if not text:
            return []
        amounts = []
        for match in AmountPatterns.GERMAN_AMOUNT.finditer(text):
            amount = self._parse_german_amount(match.group(1))
            if amount and amount not in amounts and amount > Decimal("0"):
                amounts.append(amount)
        return sorted(amounts, reverse=True)[:10]  # Top 10 Betraege

    def _parse_german_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parst einen deutschen Geldbetrag."""
        try:
            # Tausendertrenner (.) entfernen, Dezimalkomma zu Punkt
            cleaned = amount_str.replace(".", "").replace(",", ".")
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    def _parse_date_groups(
        self,
        day: str,
        month: str,
        year: str
    ) -> Optional[date]:
        """Parst Datumsgruppen zu einem date-Objekt.

        Behandelt 2-stellige Jahreszahlen korrekt:
        - 00-49 → 2000-2049
        - 50-99 → 1950-1999
        """
        try:
            year_int = int(year)
            # 2-stellige Jahreszahl korrigieren
            if year_int < 100:
                if year_int >= 50:
                    year_int += 1900  # 50-99 → 1950-1999
                else:
                    year_int += 2000  # 00-49 → 2000-2049
            return date(year_int, int(month), int(day))
        except ValueError:
            return None

    def _calculate_overall_confidence(
        self,
        result: ExtractedDocumentData
    ) -> float:
        """Berechnet die Gesamtkonfidenz."""
        confidences = []

        if result.classification:
            confidences.append(result.classification.confidence)

        primary_data = result.get_primary_data()
        if primary_data:
            confidences.append(primary_data.extraction_confidence)

        if not confidences:
            return 0.0

        return sum(confidences) / len(confidences)


# =============================================================================
# SINGLETON INSTANCE (Thread-Safe)
# =============================================================================

import threading

_structured_extraction_service: Optional[StructuredExtractionService] = None
_extraction_service_lock = threading.Lock()


def get_structured_extraction_service() -> StructuredExtractionService:
    """
    Gibt die Singleton-Instanz zurueck.

    Thread-safe durch Double-Checked Locking - wichtig fuer
    Celery Worker mit mehreren Prozessen/Threads.
    """
    global _structured_extraction_service

    # Fast path: Singleton bereits initialisiert
    if _structured_extraction_service is not None:
        return _structured_extraction_service

    # Slow path: Mit Lock initialisieren
    with _extraction_service_lock:
        # Nochmal pruefen nach Lock-Erwerb
        if _structured_extraction_service is not None:
            return _structured_extraction_service

        _structured_extraction_service = StructuredExtractionService()

    return _structured_extraction_service


def reset_structured_extraction_service() -> None:
    """Setzt die Singleton-Instanz zurueck (fuer Tests)."""
    global _structured_extraction_service
    with _extraction_service_lock:
        _structured_extraction_service = None
