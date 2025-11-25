"""
German Entity Extractor Sub-Agent

Specialized sub-agent for extracting German business entities from documents.
Focuses on German-specific entities like company types, tax IDs, and addresses.

Features:
- Company name extraction (GmbH, AG, UG, KG, etc.)
- Address parsing (German format)
- Tax ID extraction (USt-IdNr, Steuernummer)
- Bank details (IBAN, BIC)
- Person names (with German titles)
- Date extraction (German formats)
- Currency amounts (German number format)

Uses:
- spaCy for NER
- Regex patterns for structured data
- German-specific validation rules
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import spacy
from spacy.language import Language
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class CompanyEntity:
    """German company entity."""
    name: str
    company_type: str  # GmbH, AG, UG, KG, etc.
    full_name: str  # Complete legal name
    confidence: float
    source_text: str


@dataclass
class AddressEntity:
    """German address."""
    street: Optional[str] = None
    house_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "Deutschland"
    full_address: Optional[str] = None
    confidence: float = 0.0


@dataclass
class TaxIDEntity:
    """German tax identifiers."""
    ust_id: Optional[str] = None  # VAT ID (DE123456789)
    steuernummer: Optional[str] = None  # Tax number
    confidence: float = 0.0


@dataclass
class BankDetailsEntity:
    """Bank account details."""
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    confidence: float = 0.0


@dataclass
class PersonEntity:
    """Person name with German titles."""
    title: Optional[str] = None  # Dr., Prof., Dipl.-Ing., etc.
    first_name: Optional[str] = None
    last_name: str = ""
    full_name: str = ""
    confidence: float = 0.0


@dataclass
class AmountEntity:
    """Currency amount (German format)."""
    value: float
    currency: str = "EUR"
    text: str = ""  # Original text
    confidence: float = 0.0


@dataclass
class DateEntity:
    """Date (German formats)."""
    date: datetime
    text: str  # Original text
    format_detected: str  # DD.MM.YYYY, DD. Monat YYYY, etc.
    confidence: float = 0.0


@dataclass
class ExtractedEntities:
    """All extracted entities from a document."""
    companies: List[CompanyEntity] = field(default_factory=list)
    addresses: List[AddressEntity] = field(default_factory=list)
    tax_ids: List[TaxIDEntity] = field(default_factory=list)
    bank_details: List[BankDetailsEntity] = field(default_factory=list)
    persons: List[PersonEntity] = field(default_factory=list)
    amounts: List[AmountEntity] = field(default_factory=list)
    dates: List[DateEntity] = field(default_factory=list)


# ============================================================================
# German Entity Extractor
# ============================================================================

class GermanEntityExtractor:
    """
    Extract German business entities from text.

    Uses spaCy NER + regex patterns for German-specific entities.
    """

    def __init__(self, spacy_model: str = "de_core_news_lg"):
        """
        Initialize extractor.

        Args:
            spacy_model: spaCy model name
        """
        self.nlp = spacy.load(spacy_model)

        # Compile regex patterns
        self._compile_patterns()

        logger.info("german_entity_extractor_initialized", model=spacy_model)

    def _compile_patterns(self):
        """Compile regex patterns for entity extraction."""

        # Company types (German legal forms)
        self.company_types = [
            "GmbH", "AG", "UG", "KG", "OHG", "GbR", "PartG",
            "e.V.", "e.K.", "SE", "KGaA", "GmbH & Co. KG"
        ]

        # Company pattern
        company_pattern = r'\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\s+(' + '|'.join(
            re.escape(ct) for ct in self.company_types
        ) + r')\b'
        self.company_regex = re.compile(company_pattern)

        # German address pattern
        # Street + house number + postal code + city
        self.address_regex = re.compile(
            r'([A-ZÄÖÜ][a-zäöüß]+(?:straße|strasse|str\.|weg|platz|allee|gasse)?)\s+'
            r'(\d+[a-zA-Z]?)\s*,?\s*'
            r'(\d{5})\s+'
            r'([A-ZÄÖÜ][a-zäöüß]+(?:\s+[a-zäöüß]+)*)',
            re.IGNORECASE
        )

        # VAT ID (USt-IdNr): DE + 9 digits
        self.vat_id_regex = re.compile(r'\b(DE\s?\d{9})\b')

        # German tax number (Steuernummer): Various formats
        self.tax_number_regex = re.compile(
            r'\b(\d{2,3}[/\s]\d{3}[/\s]\d{4,5})\b'
        )

        # IBAN: DE + 2 digits + 18 alphanumeric
        self.iban_regex = re.compile(
            r'\b(DE\d{2}\s?(?:\d{4}\s?){4}\d{2})\b'
        )

        # BIC: 8 or 11 characters
        self.bic_regex = re.compile(
            r'\b([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b'
        )

        # German amount: 1.234,56 € or € 1.234,56
        self.amount_regex = re.compile(
            r'€?\s?(\d{1,3}(?:\.\d{3})*,\d{2})\s?€?'
        )

        # German date formats
        self.date_patterns = [
            (r'(\d{1,2})\.(\d{1,2})\.(\d{4})', '%d.%m.%Y'),  # 22.11.2025
            (r'(\d{1,2})\.\s?(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s?(\d{4})', None),  # 22. November 2025
        ]

        self.date_regexes = [(re.compile(pattern, re.IGNORECASE), fmt) for pattern, fmt in self.date_patterns]

        # German months mapping
        self.german_months = {
            "januar": 1, "februar": 2, "märz": 3, "april": 4,
            "mai": 5, "juni": 6, "juli": 7, "august": 8,
            "september": 9, "oktober": 10, "november": 11, "dezember": 12
        }

        # German academic/professional titles
        self.german_titles = [
            "Dr.", "Prof.", "Dr. med.", "Dr. jur.", "Dr. rer. nat.",
            "Dipl.-Ing.", "Dipl.-Kfm.", "M.Sc.", "B.Sc.", "MBA",
            "Herr", "Frau"
        ]

    def extract(self, text: str) -> ExtractedEntities:
        """
        Extract all German entities from text.

        Args:
            text: Input text

        Returns:
            Extracted entities
        """
        entities = ExtractedEntities()

        # Use spaCy for general NER
        doc = self.nlp(text)

        # Extract spaCy entities
        for ent in doc.ents:
            if ent.label_ == "ORG":
                # Organization - check if it's a German company
                company = self._parse_company(ent.text)
                if company:
                    entities.companies.append(company)

            elif ent.label_ == "PER":
                # Person
                person = self._parse_person(ent.text)
                if person:
                    entities.persons.append(person)

            elif ent.label_ == "LOC":
                # Location - might be part of address
                pass  # Handled by address regex

        # Extract companies with regex
        for match in self.company_regex.finditer(text):
            company = CompanyEntity(
                name=match.group(1),
                company_type=match.group(2),
                full_name=match.group(0),
                confidence=0.95,
                source_text=match.group(0)
            )

            # Deduplicate
            if not any(c.full_name == company.full_name for c in entities.companies):
                entities.companies.append(company)

        # Extract addresses
        for match in self.address_regex.finditer(text):
            address = AddressEntity(
                street=match.group(1),
                house_number=match.group(2),
                postal_code=match.group(3),
                city=match.group(4),
                full_address=match.group(0),
                confidence=0.90
            )
            entities.addresses.append(address)

        # Extract tax IDs
        tax_ids = TaxIDEntity()

        vat_matches = self.vat_id_regex.findall(text)
        if vat_matches:
            tax_ids.ust_id = vat_matches[0].replace(" ", "")
            tax_ids.confidence = 0.98

        tax_num_matches = self.tax_number_regex.findall(text)
        if tax_num_matches:
            tax_ids.steuernummer = tax_num_matches[0]
            tax_ids.confidence = max(tax_ids.confidence, 0.90)

        if tax_ids.ust_id or tax_ids.steuernummer:
            entities.tax_ids.append(tax_ids)

        # Extract bank details
        bank_details = BankDetailsEntity()

        iban_matches = self.iban_regex.findall(text)
        if iban_matches:
            bank_details.iban = iban_matches[0].replace(" ", "")
            bank_details.confidence = 0.95

        bic_matches = self.bic_regex.findall(text)
        if bic_matches:
            bank_details.bic = bic_matches[0]
            bank_details.confidence = max(bank_details.confidence, 0.90)

        if bank_details.iban or bank_details.bic:
            entities.bank_details.append(bank_details)

        # Extract amounts
        for match in self.amount_regex.finditer(text):
            amount_str = match.group(1)

            # Parse German number format
            try:
                value = float(amount_str.replace('.', '').replace(',', '.'))

                entities.amounts.append(AmountEntity(
                    value=value,
                    currency="EUR",
                    text=match.group(0),
                    confidence=0.95
                ))
            except ValueError:
                pass

        # Extract dates
        for regex, date_format in self.date_regexes:
            for match in regex.finditer(text):
                date_entity = self._parse_date(match, date_format)
                if date_entity:
                    entities.dates.append(date_entity)

        logger.info(
            "entities_extracted",
            companies=len(entities.companies),
            addresses=len(entities.addresses),
            tax_ids=len(entities.tax_ids),
            bank_details=len(entities.bank_details),
            persons=len(entities.persons),
            amounts=len(entities.amounts),
            dates=len(entities.dates)
        )

        return entities

    def _parse_company(self, text: str) -> Optional[CompanyEntity]:
        """Parse company name from text."""
        match = self.company_regex.search(text)
        if match:
            return CompanyEntity(
                name=match.group(1),
                company_type=match.group(2),
                full_name=match.group(0),
                confidence=0.90,
                source_text=text
            )
        return None

    def _parse_person(self, text: str) -> Optional[PersonEntity]:
        """Parse person name from text."""
        # Check for German titles
        title = None
        name_part = text

        for t in self.german_titles:
            if text.startswith(t):
                title = t
                name_part = text[len(t):].strip()
                break

        # Split into first and last name
        parts = name_part.split()
        if not parts:
            return None

        if len(parts) == 1:
            return PersonEntity(
                title=title,
                last_name=parts[0],
                full_name=text,
                confidence=0.80
            )
        else:
            return PersonEntity(
                title=title,
                first_name=' '.join(parts[:-1]),
                last_name=parts[-1],
                full_name=text,
                confidence=0.85
            )

    def _parse_date(self, match: re.Match, date_format: Optional[str]) -> Optional[DateEntity]:
        """Parse date from regex match."""
        try:
            if date_format:
                # Numeric date format
                date_str = match.group(0)
                date_obj = datetime.strptime(date_str, date_format)

                return DateEntity(
                    date=date_obj,
                    text=date_str,
                    format_detected=date_format,
                    confidence=0.95
                )
            else:
                # Text month format (e.g., "22. November 2025")
                day = int(match.group(1))
                month_name = match.group(2).lower()
                year = int(match.group(3))

                month = self.german_months.get(month_name)
                if not month:
                    return None

                date_obj = datetime(year, month, day)

                return DateEntity(
                    date=date_obj,
                    text=match.group(0),
                    format_detected="DD. Month YYYY",
                    confidence=0.90
                )
        except (ValueError, IndexError):
            return None

    def extract_invoice_data(self, text: str) -> Dict:
        """
        Extract invoice-specific data.

        Convenience method for invoice processing.

        Args:
            text: Invoice text

        Returns:
            Dictionary with invoice fields
        """
        entities = self.extract(text)

        invoice_data = {
            "company": entities.companies[0] if entities.companies else None,
            "address": entities.addresses[0] if entities.addresses else None,
            "vat_id": entities.tax_ids[0].ust_id if entities.tax_ids else None,
            "tax_number": entities.tax_ids[0].steuernummer if entities.tax_ids else None,
            "iban": entities.bank_details[0].iban if entities.bank_details else None,
            "bic": entities.bank_details[0].bic if entities.bank_details else None,
            "amounts": [a.value for a in entities.amounts],
            "dates": [d.date for d in entities.dates],
            "invoice_date": entities.dates[0].date if entities.dates else None,
        }

        # Infer invoice number (look for "Rechnungsnummer" + number)
        invoice_number_match = re.search(
            r'Rechnung(?:s)?(?:nr|nummer)[:\s]+([A-Z0-9-/]+)',
            text,
            re.IGNORECASE
        )
        if invoice_number_match:
            invoice_data["invoice_number"] = invoice_number_match.group(1)

        return invoice_data


# ============================================================================
# Validation
# ============================================================================

def validate_vat_id(vat_id: str) -> bool:
    """
    Validate German VAT ID format.

    Args:
        vat_id: VAT ID (DE123456789)

    Returns:
        True if valid format
    """
    vat_id = vat_id.replace(" ", "")

    if not re.match(r'^DE\d{9}$', vat_id):
        return False

    # Simple checksum validation (simplified)
    # Full validation would require online API check
    return True


def validate_iban(iban: str) -> bool:
    """
    Validate German IBAN format.

    Args:
        iban: IBAN (DE89370400440532013000)

    Returns:
        True if valid format
    """
    iban = iban.replace(" ", "")

    if not re.match(r'^DE\d{20}$', iban):
        return False

    # IBAN checksum validation (mod 97)
    # Move first 4 chars to end
    rearranged = iban[4:] + iban[:4]

    # Replace letters with numbers (A=10, B=11, ..., Z=35)
    numeric = ""
    for char in rearranged:
        if char.isdigit():
            numeric += char
        else:
            numeric += str(ord(char) - ord('A') + 10)

    # Check if mod 97 == 1
    return int(numeric) % 97 == 1


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    # Example usage
    sample_text = """
    Rechnung

    Müller GmbH
    Musterstraße 123
    12345 Berlin

    USt-IdNr: DE123456789
    Steuernummer: 12/345/67890

    IBAN: DE89 3704 0044 0532 0130 00
    BIC: COBADEFFXXX

    Rechnungsnummer: RE-2025-001
    Rechnungsdatum: 22. November 2025

    Nettobetrag: 1.234,56 €
    MwSt (19%): 234,57 €
    Bruttobetrag: 1.469,13 €

    Mit freundlichen Grüßen
    Dr. Hans Müller
    Geschäftsführer
    """

    extractor = GermanEntityExtractor()
    entities = extractor.extract(sample_text)

    print("\n=== Extracted Entities ===\n")

    print("Companies:")
    for company in entities.companies:
        print(f"  - {company.full_name} (confidence: {company.confidence})")

    print("\nAddresses:")
    for address in entities.addresses:
        print(f"  - {address.full_address} (confidence: {address.confidence})")

    print("\nTax IDs:")
    for tax_id in entities.tax_ids:
        print(f"  - VAT ID: {tax_id.ust_id}")
        print(f"  - Tax Number: {tax_id.steuernummer}")

    print("\nBank Details:")
    for bank in entities.bank_details:
        print(f"  - IBAN: {bank.iban} (valid: {validate_iban(bank.iban) if bank.iban else False})")
        print(f"  - BIC: {bank.bic}")

    print("\nPersons:")
    for person in entities.persons:
        print(f"  - {person.full_name} (title: {person.title})")

    print("\nAmounts:")
    for amount in entities.amounts:
        print(f"  - {amount.value} {amount.currency} (text: {amount.text})")

    print("\nDates:")
    for date in entities.dates:
        print(f"  - {date.date.strftime('%d.%m.%Y')} (text: {date.text})")

    print("\n=== Invoice Data (Structured) ===\n")
    invoice_data = extractor.extract_invoice_data(sample_text)
    for key, value in invoice_data.items():
        print(f"{key}: {value}")
