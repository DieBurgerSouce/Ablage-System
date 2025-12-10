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

    # Order number: "Bestellnummer: 123456"
    ORDER_NUMBER: RePattern[str] = re.compile(
        r"(?P<label>bestell?-?(?:nr\.?|nummer)|bestellung\s*nr\.?|"
        r"order\s*(?:no\.?|number|#)|auftrags?-?(?:nr\.?|nummer))"
        r"[\s:]*"
        r"(?P<number>[A-Za-z0-9\-_/]{3,30})",
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
    """Extract invoice number from text."""
    patterns = ReferencePatterns()
    match = patterns.INVOICE_NUMBER.search(text)
    return match.group("number").strip() if match else None


def extract_order_number(text: str) -> Optional[str]:
    """Extract order number from text."""
    patterns = ReferencePatterns()
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
