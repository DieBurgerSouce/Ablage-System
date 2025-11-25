"""
Invoice Data Extractor Sub-Agent

Specialized sub-agent for extracting structured data from German invoices.
Extracts fields like invoice number, date, amounts, VAT, company details, etc.

Accuracy target: > 95% for key fields
Processing time: < 1s per invoice
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

import structlog
from pydantic import BaseModel, Field, validator

from app.utils.german_text import normalize_german_text, extract_german_date


logger = structlog.get_logger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class InvoiceAddress(BaseModel):
    """Company address model."""
    company_name: Optional[str] = None
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "Deutschland"


class InvoiceAmount(BaseModel):
    """Invoice amount breakdown."""
    net_amount: Optional[Decimal] = Field(None, description="Nettobetrag")
    vat_amount: Optional[Decimal] = Field(None, description="Mehrwertsteuer")
    gross_amount: Optional[Decimal] = Field(None, description="Bruttobetrag")
    currency: str = "EUR"

    @validator("net_amount", "vat_amount", "gross_amount", pre=True)
    def parse_decimal(cls, v):
        """Parse German decimal format (1.234,56 -> Decimal)."""
        if v is None or v == "":
            return None
        if isinstance(v, Decimal):
            return v
        # Convert German format to standard
        v_str = str(v).replace(".", "").replace(",", ".")
        return Decimal(v_str)


class InvoiceLineItem(BaseModel):
    """Invoice line item."""
    description: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    total_price: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = Field(None, description="Mehrwertsteuersatz (%)")


class InvoiceData(BaseModel):
    """Complete structured invoice data."""
    # Invoice metadata
    invoice_number: Optional[str] = Field(None, description="Rechnungsnummer")
    invoice_date: Optional[datetime] = Field(None, description="Rechnungsdatum")
    due_date: Optional[datetime] = Field(None, description="Fälligkeitsdatum")
    delivery_date: Optional[datetime] = Field(None, description="Lieferdatum")

    # Parties
    issuer: InvoiceAddress = Field(default_factory=InvoiceAddress, description="Rechnungssteller")
    recipient: InvoiceAddress = Field(default_factory=InvoiceAddress, description="Rechnungsempfänger")

    # Amounts
    amounts: InvoiceAmount = Field(default_factory=InvoiceAmount)

    # Line items
    line_items: List[InvoiceLineItem] = Field(default_factory=list)

    # Tax information
    tax_id: Optional[str] = Field(None, description="Steuernummer")
    vat_id: Optional[str] = Field(None, description="USt-IdNr.")

    # Payment
    payment_method: Optional[str] = None
    bank_account: Optional[str] = Field(None, description="IBAN")
    bic: Optional[str] = None

    # Additional
    notes: Optional[str] = Field(None, description="Anmerkungen")
    reference_number: Optional[str] = Field(None, description="Referenznummer")

    # Extraction metadata
    extraction_confidence: float = Field(0.0, ge=0.0, le=1.0)
    extraction_method: str = "pattern_matching"


# ============================================================================
# Invoice Data Extractor
# ============================================================================

class InvoiceDataExtractor:
    """
    Specialized sub-agent for extracting structured data from German invoices.

    Uses pattern matching and German business document conventions.
    """

    # German VAT rates
    VAT_RATES = {
        "19": Decimal("0.19"),    # Standard rate
        "7": Decimal("0.07"),      # Reduced rate
        "0": Decimal("0.00"),      # Tax-free
    }

    # Regex patterns for key fields
    PATTERNS = {
        "invoice_number": [
            r"rechnungsnr\.?\s*:?\s*(\w+[-/]?\d+)",
            r"invoice\s+no\.?\s*:?\s*(\w+[-/]?\d+)",
            r"re-nr\.?\s*:?\s*(\w+[-/]?\d+)",
        ],
        "invoice_date": [
            r"rechnungsdatum\s*:?\s*(\d{1,2}[.]\d{1,2}[.]\d{2,4})",
            r"datum\s*:?\s*(\d{1,2}[.]\d{1,2}[.]\d{2,4})",
        ],
        "due_date": [
            r"fälligkeitsdatum\s*:?\s*(\d{1,2}[.]\d{1,2}[.]\d{2,4})",
            r"zahlbar\s+bis\s*:?\s*(\d{1,2}[.]\d{1,2}[.]\d{2,4})",
        ],
        "tax_id": [
            r"steuernummer\s*:?\s*([\d\s/]+)",
            r"st[-.]?nr\.?\s*:?\s*([\d\s/]+)",
        ],
        "vat_id": [
            r"ust[-.]?idnr\.?\s*:?\s*([A-Z]{2}\s?\d+)",
            r"vat\s+id\s*:?\s*([A-Z]{2}\s?\d+)",
        ],
        "iban": [
            r"iban\s*:?\s*([A-Z]{2}\d{2}\s?[\dA-Z\s]+)",
        ],
        "bic": [
            r"bic\s*:?\s*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)",
        ],
        "net_amount": [
            r"nettobetrag\s*:?\s*€?\s*([\d.,]+)\s*€?",
            r"summe\s+netto\s*:?\s*€?\s*([\d.,]+)\s*€?",
        ],
        "vat_amount": [
            r"mwst\.?\s*(?:\d+%)?\s*:?\s*€?\s*([\d.,]+)\s*€?",
            r"ust\.?\s*(?:\d+%)?\s*:?\s*€?\s*([\d.,]+)\s*€?",
            r"mehrwertsteuer\s*:?\s*€?\s*([\d.,]+)\s*€?",
        ],
        "gross_amount": [
            r"bruttobetrag\s*:?\s*€?\s*([\d.,]+)\s*€?",
            r"summe\s+brutto\s*:?\s*€?\s*([\d.,]+)\s*€?",
            r"gesamtbetrag\s*:?\s*€?\s*([\d.,]+)\s*€?",
            r"zu\s+zahlen\s*:?\s*€?\s*([\d.,]+)\s*€?",
        ],
    }

    def __init__(self):
        logger.info("invoice_extractor_initialized")

    async def extract(self, ocr_text: str) -> InvoiceData:
        """
        Extract structured invoice data from OCR text.

        Args:
            ocr_text: Raw OCR text from invoice

        Returns:
            InvoiceData object with extracted fields
        """
        # Normalize German text
        text = normalize_german_text(ocr_text)

        logger.info("extracting_invoice_data", text_length=len(text))

        try:
            # Extract all fields
            invoice_data = InvoiceData()

            # Basic metadata
            invoice_data.invoice_number = self._extract_invoice_number(text)
            invoice_data.invoice_date = self._extract_date(text, "invoice_date")
            invoice_data.due_date = self._extract_date(text, "due_date")

            # Tax IDs
            invoice_data.tax_id = self._extract_tax_id(text)
            invoice_data.vat_id = self._extract_vat_id(text)

            # Addresses
            invoice_data.issuer = self._extract_issuer_address(text)
            invoice_data.recipient = self._extract_recipient_address(text)

            # Amounts
            invoice_data.amounts = self._extract_amounts(text)

            # Payment info
            invoice_data.bank_account = self._extract_iban(text)
            invoice_data.bic = self._extract_bic(text)

            # Line items (basic extraction)
            invoice_data.line_items = self._extract_line_items(text)

            # Calculate extraction confidence
            invoice_data.extraction_confidence = self._calculate_confidence(invoice_data)

            logger.info(
                "invoice_data_extracted",
                invoice_number=invoice_data.invoice_number,
                confidence=invoice_data.extraction_confidence,
                fields_extracted=self._count_extracted_fields(invoice_data)
            )

            return invoice_data

        except Exception as e:
            logger.exception("invoice_extraction_failed", error=str(e))
            # Return empty invoice data with error
            return InvoiceData(
                extraction_confidence=0.0,
                notes=f"Extraction failed: {str(e)}"
            )

    def _extract_invoice_number(self, text: str) -> Optional[str]:
        """Extract invoice number."""
        for pattern in self.PATTERNS["invoice_number"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_date(self, text: str, date_type: str) -> Optional[datetime]:
        """Extract date (invoice date, due date, etc.)."""
        patterns = self.PATTERNS.get(date_type, [])
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                return extract_german_date(date_str)
        return None

    def _extract_tax_id(self, text: str) -> Optional[str]:
        """Extract German tax number (Steuernummer)."""
        for pattern in self.PATTERNS["tax_id"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_vat_id(self, text: str) -> Optional[str]:
        """Extract VAT ID (USt-IdNr)."""
        for pattern in self.PATTERNS["vat_id"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                vat_id = match.group(1).replace(" ", "")
                # Validate format (DE + 9 digits)
                if re.match(r"^DE\d{9}$", vat_id):
                    return vat_id
        return None

    def _extract_iban(self, text: str) -> Optional[str]:
        """Extract IBAN."""
        for pattern in self.PATTERNS["iban"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                iban = match.group(1).replace(" ", "")
                # Validate IBAN format (basic check)
                if re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]+$", iban):
                    return iban
        return None

    def _extract_bic(self, text: str) -> Optional[str]:
        """Extract BIC/SWIFT code."""
        for pattern in self.PATTERNS["bic"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_amounts(self, text: str) -> InvoiceAmount:
        """Extract invoice amounts (net, VAT, gross)."""
        amounts = InvoiceAmount()

        # Extract net amount
        for pattern in self.PATTERNS["net_amount"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amounts.net_amount = self._parse_german_decimal(match.group(1))
                break

        # Extract VAT amount
        for pattern in self.PATTERNS["vat_amount"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amounts.vat_amount = self._parse_german_decimal(match.group(1))
                break

        # Extract gross amount
        for pattern in self.PATTERNS["gross_amount"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amounts.gross_amount = self._parse_german_decimal(match.group(1))
                break

        # Validate: gross = net + VAT
        if amounts.net_amount and amounts.vat_amount and not amounts.gross_amount:
            amounts.gross_amount = amounts.net_amount + amounts.vat_amount

        return amounts

    def _parse_german_decimal(self, value: str) -> Decimal:
        """Parse German decimal format (1.234,56 -> Decimal(1234.56))."""
        # Remove dots (thousands separator), replace comma with dot
        value_clean = value.replace(".", "").replace(",", ".")
        return Decimal(value_clean)

    def _extract_issuer_address(self, text: str) -> InvoiceAddress:
        """Extract issuer (sender) address."""
        # Heuristic: usually at top of invoice
        lines = text.split("\n")[:20]  # First 20 lines

        address = InvoiceAddress()

        # Look for company name (often first non-empty line)
        for line in lines:
            line_clean = line.strip()
            if len(line_clean) > 3 and not re.match(r"^\d+$", line_clean):
                address.company_name = line_clean
                break

        # Look for address components
        for line in lines:
            # Postal code + city (e.g., "12345 Berlin")
            match = re.search(r"(\d{5})\s+([A-ZÄÖÜa-zäöüß\s]+)", line)
            if match and not address.postal_code:
                address.postal_code = match.group(1)
                address.city = match.group(2).strip()

        return address

    def _extract_recipient_address(self, text: str) -> InvoiceAddress:
        """Extract recipient address."""
        # Look for "An:" or "Empfänger:" keywords
        recipient_section = re.search(
            r"(?:an|empfänger):\s*(.+?)(?:\n\n|\n\s*\n)",
            text,
            re.IGNORECASE | re.DOTALL
        )

        if not recipient_section:
            return InvoiceAddress()

        recipient_text = recipient_section.group(1)
        lines = recipient_text.split("\n")

        address = InvoiceAddress()

        # First line is usually company name
        if lines:
            address.company_name = lines[0].strip()

        # Look for postal code + city
        for line in lines:
            match = re.search(r"(\d{5})\s+([A-ZÄÖÜa-zäöüß\s]+)", line)
            if match:
                address.postal_code = match.group(1)
                address.city = match.group(2).strip()
                break

        return address

    def _extract_line_items(self, text: str) -> List[InvoiceLineItem]:
        """Extract invoice line items (basic extraction)."""
        # This is a simplified extraction - would need table parsing for full accuracy
        line_items = []

        # Look for lines with quantity, description, price pattern
        # Example: "2 x Widget XL à 45,00 € = 90,00 €"
        pattern = r"(\d+)\s*x?\s*(.+?)\s+à\s+([\d.,]+)\s*€\s*=\s*([\d.,]+)\s*€"

        for match in re.finditer(pattern, text, re.IGNORECASE):
            item = InvoiceLineItem(
                description=match.group(2).strip(),
                quantity=Decimal(match.group(1)),
                unit_price=self._parse_german_decimal(match.group(3)),
                total_price=self._parse_german_decimal(match.group(4))
            )
            line_items.append(item)

        return line_items

    def _calculate_confidence(self, invoice_data: InvoiceData) -> float:
        """
        Calculate extraction confidence based on which fields were extracted.

        Weighted by field importance:
        - Critical fields (invoice number, amounts): 40%
        - Important fields (dates, tax IDs): 30%
        - Optional fields (addresses, line items): 30%
        """
        critical_score = 0.0
        important_score = 0.0
        optional_score = 0.0

        # Critical fields (40% weight)
        critical_fields = [
            invoice_data.invoice_number,
            invoice_data.amounts.gross_amount,
        ]
        critical_score = sum(1 for f in critical_fields if f) / len(critical_fields)

        # Important fields (30% weight)
        important_fields = [
            invoice_data.invoice_date,
            invoice_data.vat_id or invoice_data.tax_id,
            invoice_data.amounts.net_amount,
            invoice_data.amounts.vat_amount,
        ]
        important_score = sum(1 for f in important_fields if f) / len(important_fields)

        # Optional fields (30% weight)
        optional_fields = [
            invoice_data.due_date,
            invoice_data.issuer.company_name,
            invoice_data.recipient.company_name,
            invoice_data.bank_account,
            len(invoice_data.line_items) > 0,
        ]
        optional_score = sum(1 for f in optional_fields if f) / len(optional_fields)

        # Weighted average
        confidence = (
            0.40 * critical_score +
            0.30 * important_score +
            0.30 * optional_score
        )

        return round(confidence, 2)

    def _count_extracted_fields(self, invoice_data: InvoiceData) -> int:
        """Count how many fields were successfully extracted."""
        count = 0

        # Check all optional fields
        if invoice_data.invoice_number:
            count += 1
        if invoice_data.invoice_date:
            count += 1
        if invoice_data.due_date:
            count += 1
        if invoice_data.tax_id:
            count += 1
        if invoice_data.vat_id:
            count += 1
        if invoice_data.amounts.net_amount:
            count += 1
        if invoice_data.amounts.vat_amount:
            count += 1
        if invoice_data.amounts.gross_amount:
            count += 1
        if invoice_data.issuer.company_name:
            count += 1
        if invoice_data.recipient.company_name:
            count += 1
        if invoice_data.bank_account:
            count += 1
        if invoice_data.line_items:
            count += len(invoice_data.line_items)

        return count


# ============================================================================
# CLI for Testing
# ============================================================================

async def main():
    """CLI for testing invoice extraction."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python invoice_data_extractor.py <ocr_text_file>")
        sys.exit(1)

    text_file = sys.argv[1]

    with open(text_file, "r", encoding="utf-8") as f:
        ocr_text = f.read()

    # Extract data
    extractor = InvoiceDataExtractor()
    invoice_data = await extractor.extract(ocr_text)

    # Print results
    print("\n=== Extracted Invoice Data ===\n")
    print(invoice_data.json(indent=2, ensure_ascii=False))
    print(f"\nExtraction Confidence: {invoice_data.extraction_confidence:.0%}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
