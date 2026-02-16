"""
Reference number patterns for German documents.

Patterns for extracting:
- Invoice numbers (Rechnungsnummer)
- Order numbers (Bestellnummer)
- Customer numbers (Kundennummer)
- Tax IDs (Steuernummer, USt-IdNr)
- IBAN / BIC
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Pattern as RePattern

from app.services.extraction.base import Pattern


class ReferencePatterns:
    """Collection of reference number patterns."""

    # ==========================================================================
    # INVOICE/ORDER NUMBERS
    # ==========================================================================

    # Invoice number: "Rechnungsnummer: RE-2024-001234"
    INVOICE_NUMBER: RePattern[str] = re.compile(
        r"(?P<label>rechnungs?-?(?:nr\.?|nummer)|rechnung\s*nr\.?|"
        r"invoice\s*(?:no\.?|number|#)|beleg-?nr\.?)"
        r"[\s:]*"
        r"(?P<number>[A-Za-z0-9\-_/]{3,30})",
        re.IGNORECASE,
    )

    # Invoice number (reverse format): "F-201451\nInvoice No."
    # Used when value appears BEFORE the label (common in tabular layouts)
    INVOICE_NUMBER_REVERSE: RePattern[str] = re.compile(
        r"(?P<number>[A-Z]-?\d{5,8})"
        r"\s*\n\s*"
        r"(?P<label>Invoice\s*(?:No\.?|Number)|Rechnungs?-?(?:Nr\.?|nummer))",
        re.IGNORECASE,
    )

    # ==========================================================================
    # VENDOR-SPECIFIC INVOICE NUMBER FORMATS (Added 2025-12-15)
    # ==========================================================================

    # Asal-Format: RG + 8 Ziffern (z.B. RG20012108)
    INVOICE_NUMBER_RG: RePattern[str] = re.compile(
        r"\b(?P<number>RG\d{8})\b",
        re.IGNORECASE,
    )

    # Amefa-Format: CD + 10 Ziffern (z.B. CD4921000467)
    INVOICE_NUMBER_CD: RePattern[str] = re.compile(
        r"\b(?P<number>CD\d{10})\b",
        re.IGNORECASE,
    )

    # AUER Packaging: VK + 7 Ziffern (z.B. VK 1036735 oder VK1036735)
    INVOICE_NUMBER_VK: RePattern[str] = re.compile(
        r"\bVK\s*(?P<number>\d{7})\b",
        re.IGNORECASE,
    )

    # AUER Delivery: D + 5-6 Ziffern (z.B. D119925)
    INVOICE_NUMBER_D: RePattern[str] = re.compile(
        r"\b(?P<number>D\d{5,6})\b",
        re.IGNORECASE,
    )

    # Standalone 6-stellige Nummer gefolgt von Datum (a.b.s. Rechenzentrum Format)
    INVOICE_NUMBER_ABS: RePattern[str] = re.compile(
        r"\b(?P<number>\d{6})\s*\n\s*\d{2}\.\d{2}\.\d{2,4}",
    )

    # a.b.s. Rechenzentrum VERTIKALES Layout (Added 2025-12-15):
    # Labels kommen zuerst vertikal, dann Werte vertikal
    # Format:
    #   Rechnungs-Nr.
    #   Kunden-Nr.
    #   Rechnungsdatum
    #   Rechnung        <- optional header
    #   246543          <- Invoice number (erste 5-8 stellige Zahl)
    INVOICE_NUMBER_VERTICAL: RePattern[str] = re.compile(
        r"Rechnungs-Nr\.?\s*\n"
        r"Kunden-Nr\.?\s*\n"
        r"Rechnungsdatum\s*\n"
        r"(?:Rechnung\s*\n)?"
        r"(?P<number>\d{5,8})",
        re.IGNORECASE,
    )

    # Order number: "Bestellnummer: 123456"
    ORDER_NUMBER: RePattern[str] = re.compile(
        r"(?P<label>bestell?-?(?:nr\.?|nummer)|bestellung\s*nr\.?|"
        r"order\s*(?:no\.?|number|#)|auftrags?-?(?:nr\.?|nummer))"
        r"[\s:]*"
        r"(?P<number>[A-Za-z0-9\-_/]{3,30})",
        re.IGNORECASE,
    )

    # Order number (reverse format): "V-210089\nOrder No."
    # Used when value appears BEFORE the label (common in tabular layouts)
    ORDER_NUMBER_REVERSE: RePattern[str] = re.compile(
        r"(?P<number>[A-Z]-?\d{5,8})"
        r"\s*\n\s*"
        r"(?P<label>Order\s*(?:No\.?|Number)|Bestell?-?(?:Nr\.?|nummer)|Auftrags?-?(?:Nr\.?|nummer))",
        re.IGNORECASE,
    )

    # Customer number: "Kundennummer: K12345"
    CUSTOMER_NUMBER: RePattern[str] = re.compile(
        r"(?P<label>kunden?-?(?:nr\.?|nummer)|customer\s*(?:no\.?|number|#))"
        r"[\s:]*"
        r"(?P<number>[A-Za-z0-9\-_]{3,20})",
        re.IGNORECASE,
    )

    # Generic reference: "Ihre Referenz: REF-2024-001"
    REFERENCE_NUMBER: RePattern[str] = re.compile(
        r"(?P<label>(?:ihre|unsere)\s*referenz|referenz-?(?:nr\.?|nummer)|"
        r"reference\s*(?:no\.?|number)|ref\.?)"
        r"[\s:]*"
        r"(?P<number>[A-Za-z0-9\-_/]{3,30})",
        re.IGNORECASE,
    )

    # ==========================================================================
    # TAX IDENTIFIERS
    # ==========================================================================

    # German tax number: "Steuernummer: 123/456/78901"
    TAX_NUMBER: RePattern[str] = re.compile(
        r"(?P<label>steuer-?(?:nr\.?|nummer)|st\.?\s*nr\.?)"
        r"[\s:]*"
        r"(?P<number>\d{2,3}/\d{3}/\d{4,5}|\d{10,13})",
        re.IGNORECASE,
    )

    # VAT ID: "USt-IdNr.: DE123456789"
    VAT_ID: RePattern[str] = re.compile(
        r"(?P<label>ust\.?-?id(?:-?nr\.?)?|umsatzsteuer-?id(?:entifikations)?-?(?:nr\.?|nummer)?|"
        r"vat\s*(?:id|no\.?|number)|mwst\.?\s*nr\.?)"
        r"[\s:]*"
        r"(?P<number>[A-Z]{2}\s*\d{9,12})",
        re.IGNORECASE,
    )

    # Swiss VAT: "CHE-123.456.789 MWST"
    SWISS_VAT_ID: RePattern[str] = re.compile(
        r"(?P<number>CHE[-\s]?\d{3}[.\s]?\d{3}[.\s]?\d{3})\s*"
        r"(?:MWST|TVA|IVA)?",
        re.IGNORECASE,
    )

    # ==========================================================================
    # BANKING
    # ==========================================================================

    # IBAN: "DE89 3704 0044 0532 0130 00"
    IBAN: RePattern[str] = re.compile(
        r"(?P<label>IBAN)?[\s:]*"
        r"(?P<number>[A-Z]{2}\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{0,2})",
        re.IGNORECASE,
    )

    # BIC/SWIFT: "COBADEFFXXX"
    BIC: RePattern[str] = re.compile(
        r"(?P<label>BIC|SWIFT)[\s:]*"
        r"(?P<number>[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)",
        re.IGNORECASE,
    )


class ReferencePattern(Pattern[str]):
    """Pattern for extracting reference numbers."""

    def __init__(
        self,
        name: str,
        regex: RePattern[str],
        number_group: str = "number",
        base_confidence: float = 0.85,
        normalize_func: Optional[callable] = None,
    ) -> None:
        super().__init__(name, regex, base_confidence)
        self.number_group = number_group
        self.normalize_func = normalize_func

    def normalize(self, value: str, groups: Dict[str, str]) -> str:
        """Extract and optionally normalize the reference number."""
        number = groups.get(self.number_group, value)
        if self.normalize_func:
            return self.normalize_func(number)
        return number.strip()


def normalize_iban(iban: str) -> str:
    """Normalize IBAN by removing spaces."""
    return re.sub(r"\s", "", iban.upper())


def validate_iban(iban: str) -> bool:
    """Validate IBAN checksum."""
    iban = normalize_iban(iban)

    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", iban):
        return False

    # Move first 4 chars to end
    rearranged = iban[4:] + iban[:4]

    # Convert letters to numbers (A=10, B=11, ..., Z=35)
    numeric = ""
    for char in rearranged:
        if char.isalpha():
            numeric += str(ord(char) - ord("A") + 10)
        else:
            numeric += char

    # Check mod 97
    return int(numeric) % 97 == 1


def normalize_vat_id(vat_id: str) -> str:
    """Normalize VAT ID by removing spaces."""
    return re.sub(r"\s", "", vat_id.upper())


def validate_german_vat_id(vat_id: str) -> bool:
    """Validate German VAT ID format."""
    vat_id = normalize_vat_id(vat_id)
    return bool(re.match(r"^DE\d{9}$", vat_id))


def get_reference_patterns() -> List[Pattern[Any]]:
    """Get all reference patterns for registration."""
    patterns = ReferencePatterns()

    return [
        ReferencePattern(
            name="invoice_number",
            regex=patterns.INVOICE_NUMBER,
            base_confidence=0.90,
        ),
        ReferencePattern(
            name="order_number",
            regex=patterns.ORDER_NUMBER,
            base_confidence=0.90,
        ),
        ReferencePattern(
            name="customer_number",
            regex=patterns.CUSTOMER_NUMBER,
            base_confidence=0.85,
        ),
        ReferencePattern(
            name="reference_number",
            regex=patterns.REFERENCE_NUMBER,
            base_confidence=0.80,
        ),
        ReferencePattern(
            name="tax_number",
            regex=patterns.TAX_NUMBER,
            base_confidence=0.90,
        ),
        ReferencePattern(
            name="vat_id",
            regex=patterns.VAT_ID,
            normalize_func=normalize_vat_id,
            base_confidence=0.95,
        ),
        ReferencePattern(
            name="swiss_vat_id",
            regex=patterns.SWISS_VAT_ID,
            base_confidence=0.90,
        ),
        ReferencePattern(
            name="iban",
            regex=patterns.IBAN,
            normalize_func=normalize_iban,
            base_confidence=0.95,
        ),
        ReferencePattern(
            name="bic",
            regex=patterns.BIC,
            base_confidence=0.90,
        ),
    ]


def extract_invoice_number(text: str) -> Optional[str]:
    """Extract invoice number from text.

    Supports multiple formats:
    - Standard: "Invoice No.: F-201451"
    - Reverse: "F-201451\\nInvoice No." (value before label)
    - Vendor-specific: RG, CD, VK, D formats (Asal, Amefa, AUER)
    - a.b.s. Rechenzentrum: 6-digit number followed by date
    """
    patterns = ReferencePatterns()

    # Label-Keywords die NICHT als Rechnungsnummer akzeptiert werden
    LABEL_KEYWORDS = frozenset([
        'datum', 'nr', 'nummer', 'kunde', 'kunden', 'betrag',
        'mwst', 'steuer', 'summe', 'netto', 'brutto', 'artikel',
        'position', 'menge', 'preis', 'date', 'amount', 'customer',
        'rechnungsdatum', 'lieferdatum', 'bestelldatum', 'rechnungsnummer',
        'invoice', 'number', 'order', 'delivery', 'total',
    ])

    def is_likely_label(value: str) -> bool:
        """Prüft ob ein Wert wahrscheinlich ein Label ist."""
        if not value:
            return True
        value_clean = value.lower().replace('-', '').replace('.', '').replace(' ', '')
        return any(kw in value_clean for kw in LABEL_KEYWORDS)

    # 1. Try vendor-specific formats FIRST (most specific)
    # These are very reliable because they have distinctive prefixes

    # Asal: RG + 8 digits
    match = patterns.INVOICE_NUMBER_RG.search(text)
    if match:
        number = match.group("number").strip()
        if not is_likely_label(number):
            return number

    # Amefa: CD + 10 digits
    match = patterns.INVOICE_NUMBER_CD.search(text)
    if match:
        number = match.group("number").strip()
        if not is_likely_label(number):
            return number

    # AUER: VK + 7 digits
    match = patterns.INVOICE_NUMBER_VK.search(text)
    if match:
        number = f"VK{match.group('number').strip()}"
        if not is_likely_label(number):
            return number

    # AUER Delivery: D + 5-6 digits
    match = patterns.INVOICE_NUMBER_D.search(text)
    if match:
        number = match.group("number").strip()
        if not is_likely_label(number):
            return number

    # a.b.s. Rechenzentrum: 6-digit followed by date
    match = patterns.INVOICE_NUMBER_ABS.search(text)
    if match:
        number = match.group("number").strip()
        if not is_likely_label(number):
            return number

    # a.b.s. Rechenzentrum VERTIKALES Layout (Added 2025-12-15)
    # Behebt Problem wo "Kunden-Nr." als Rechnungsnummer extrahiert wurde
    match = patterns.INVOICE_NUMBER_VERTICAL.search(text)
    if match:
        number = match.group("number").strip()
        if not is_likely_label(number):
            return number

    # 2. Try reverse format (value before label - common in tables)
    match = patterns.INVOICE_NUMBER_REVERSE.search(text)
    if match:
        number = match.group("number").strip()
        if not is_likely_label(number):
            return number

    # 3. Fall back to standard format (label before value)
    match = patterns.INVOICE_NUMBER.search(text)
    if match:
        number = match.group("number").strip()
        if not is_likely_label(number):
            return number

    return None


def extract_order_number(text: str) -> Optional[str]:
    """Extract order number from text.

    Supports both formats:
    - Standard: "Order No.: V-210089"
    - Reverse: "V-210089\\nOrder No." (value before label)
    """
    patterns = ReferencePatterns()

    # Try reverse format first (more specific)
    match = patterns.ORDER_NUMBER_REVERSE.search(text)
    if match:
        return match.group("number").strip()

    # Fall back to standard format
    match = patterns.ORDER_NUMBER.search(text)
    return match.group("number").strip() if match else None


def extract_iban(text: str) -> Optional[str]:
    """Extract and validate IBAN from text."""
    patterns = ReferencePatterns()
    match = patterns.IBAN.search(text)
    if match:
        iban = normalize_iban(match.group("number"))
        if validate_iban(iban):
            return iban
    return None


def extract_vat_id(text: str) -> Optional[str]:
    """Extract VAT ID from text."""
    patterns = ReferencePatterns()

    # Try EU VAT ID
    match = patterns.VAT_ID.search(text)
    if match:
        return normalize_vat_id(match.group("number"))

    # Try Swiss VAT ID
    match = patterns.SWISS_VAT_ID.search(text)
    if match:
        return match.group("number").strip()

    return None
