# -*- coding: utf-8 -*-
"""
Entity Extraction Agent for Ablage-System.

Enterprise-grade business entity extraction from German documents:
- Date extraction (German formats)
- Currency/amount extraction
- IBAN validation and extraction
- VAT ID (USt-IdNr.) extraction
- Business term recognition
- Invoice field mapping

Feinpoliert und durchdacht - Präzise Entitätserkennung für Geschäftsdokumente.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agents.base import PostprocessingAgent
from app.german_validator import GermanValidator

logger = logging.getLogger(__name__)


class EntityExtractionAgent(PostprocessingAgent):
    """
    Entity extraction agent for German business documents.

    Extracts and validates:
    - Dates (German formats: DD.MM.YYYY, written months)
    - Currency amounts (German format: 1.234,56 EUR)
    - IBANs with checksum validation
    - VAT IDs (German: DE + 9 digits)
    - Business terms and abbreviations
    - Document-specific fields (invoices, contracts)
    """

    # Entity types with confidence weights
    ENTITY_TYPES = {
        "DATE": {"confidence_base": 0.9, "critical": True},
        "CURRENCY": {"confidence_base": 0.9, "critical": True},
        "IBAN": {"confidence_base": 0.95, "critical": True},
        "VAT_ID": {"confidence_base": 0.95, "critical": True},
        "BUSINESS_TERM": {"confidence_base": 0.85, "critical": False},
        "INVOICE_NUMBER": {"confidence_base": 0.9, "critical": True},
        "TAX_NUMBER": {"confidence_base": 0.9, "critical": True},
        "EMAIL": {"confidence_base": 0.95, "critical": False},
        "PHONE": {"confidence_base": 0.85, "critical": False},
        "POSTAL_CODE": {"confidence_base": 0.9, "critical": False},
        "COMPANY_NAME": {"confidence_base": 0.75, "critical": False},
    }

    # German phone number patterns
    PHONE_PATTERNS = [
        r'\+49\s*\(?\d{2,5}\)?\s*[\d\s\-/]+',  # +49 format
        r'0\d{2,4}[\s\-/]?\d{4,}',  # German local format
        r'\(\d{3,5}\)\s*\d{4,}',  # With area code in parentheses
    ]

    # Email pattern
    EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

    # German postal code pattern (5 digits)
    POSTAL_CODE_PATTERN = r'\b\d{5}\b'

    # Invoice number patterns (German)
    INVOICE_NUMBER_PATTERNS = [
        r'(?:RE|RG|Rechnung|Invoice|Rechnungs?-?Nr\.?|Beleg-?Nr\.?)[\s:]*([A-Z0-9\-/]+)',
        r'(?:Rechnungsnummer|Invoice Number)[\s:]*([A-Z0-9\-/]+)',
        r'Nr\.?\s*(\d{4,}[A-Z0-9\-]*)',
    ]

    # Tax number patterns
    TAX_NUMBER_PATTERNS = [
        r'(?:St\.?-?Nr\.?|Steuernummer|Tax-?ID)[\s:]*(\d{2,3}/\d{3}/\d{4,5})',
        r'(?:Steuer-?Nr\.?)[\s:]*(\d{10,13})',
    ]

    def __init__(self):
        """Initialize the Entity Extraction Agent."""
        super().__init__(name="entity_extraction_agent")
        self.validator = GermanValidator()

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract business entities from document text.

        Args:
            input_data: Dictionary containing:
                - text: Document text to analyze
                - classification: Optional document classification
                - options: Optional extraction options

        Returns:
            Extraction result containing:
                - entities: List of extracted entities
                - entity_count: Total number of entities found
                - entity_types: Count per entity type
                - critical_entities: List of critical entities found
                - invoice_data: Structured invoice data (if applicable)
        """
        self.validate_input(input_data, ["text"])

        text = input_data["text"]
        classification = input_data.get("classification", {})
        options = input_data.get("options", {})

        self.logger.info(
            "entity_extraction_started",
            text_length=len(text),
            document_type=classification.get("document_type"),
        )

        entities: List[Dict[str, Any]] = []

        # Extract all entity types
        entities.extend(self._extract_dates(text))
        entities.extend(self._extract_currencies(text))
        entities.extend(self._extract_ibans(text))
        entities.extend(self._extract_vat_ids(text))
        entities.extend(self._extract_business_terms(text))
        entities.extend(self._extract_contact_info(text))
        entities.extend(self._extract_invoice_numbers(text))
        entities.extend(self._extract_tax_numbers(text))

        # Document-specific extraction
        document_type = classification.get("document_type", "other")
        invoice_data = None

        if document_type == "invoice":
            invoice_data = self._extract_invoice_fields(text)
            # Add invoice fields as entities
            for field, info in invoice_data.items():
                if info.get("value"):
                    entities.append({
                        "type": f"INVOICE_{field.upper()}",
                        "value": info["value"],
                        "german_label": info.get("german_label"),
                        "confidence": info.get("confidence", 0.8),
                        "source": "invoice_field",
                    })

        # Calculate statistics
        entity_types = {}
        critical_entities = []

        for entity in entities:
            entity_type = entity["type"]
            entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

            if self.ENTITY_TYPES.get(entity_type, {}).get("critical", False):
                critical_entities.append(entity)

        result = {
            "entities": entities,
            "entity_count": len(entities),
            "entity_types": entity_types,
            "critical_entities": critical_entities,
            "critical_count": len(critical_entities),
        }

        if invoice_data:
            result["invoice_data"] = invoice_data

        self.logger.info(
            "entity_extraction_completed",
            entity_count=len(entities),
            entity_types=list(entity_types.keys()),
            critical_count=len(critical_entities),
        )

        return result

    def _extract_dates(self, text: str) -> List[Dict[str, Any]]:
        """Extract German date formats."""
        entities = []

        dates = self.validator.validate_date_format(text)

        for date in dates:
            entities.append({
                "type": "DATE",
                "value": date,
                "confidence": 0.9,
                "format": self._identify_date_format(date),
                "source": "date_extraction",
            })

        return entities

    def _identify_date_format(self, date: str) -> str:
        """Identify the format of a date string."""
        if re.match(r'\d{1,2}\.\d{1,2}\.\d{4}', date):
            return "DD.MM.YYYY"
        elif re.match(r'\d{1,2}\.\d{1,2}\.\d{2}', date):
            return "DD.MM.YY"
        elif any(month in date for month in self.validator.GERMAN_MONTHS):
            return "DD. Month YYYY"
        return "unknown"

    def _extract_currencies(self, text: str) -> List[Dict[str, Any]]:
        """Extract German currency amounts."""
        entities = []

        amounts = self.validator.validate_currency_format(text)

        for amount in amounts:
            # Parse the numeric value
            numeric_value = self._parse_german_currency(amount)

            entities.append({
                "type": "CURRENCY",
                "value": amount,
                "numeric_value": numeric_value,
                "currency": self._identify_currency(amount),
                "confidence": 0.9,
                "source": "currency_extraction",
            })

        return entities

    def _parse_german_currency(self, amount_str: str) -> Optional[float]:
        """Parse German currency format to float."""
        try:
            # Remove currency symbols
            cleaned = re.sub(r'[€EUR\s]|Euro', '', amount_str, flags=re.IGNORECASE)
            # Convert German format to standard
            cleaned = cleaned.replace('.', '').replace(',', '.')
            return float(cleaned)
        except ValueError:
            return None

    def _identify_currency(self, amount_str: str) -> str:
        """Identify currency from amount string."""
        if '€' in amount_str or 'EUR' in amount_str.upper() or 'Euro' in amount_str:
            return "EUR"
        return "unknown"

    def _extract_ibans(self, text: str) -> List[Dict[str, Any]]:
        """Extract and validate IBANs."""
        entities = []

        # IBAN pattern (German: DE + 20 digits, but support international)
        iban_pattern = r'\b[A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){4}\d{2,4}\b'
        matches = re.findall(iban_pattern, text.replace(' ', ''))

        for iban in matches:
            # Clean up
            clean_iban = iban.replace(' ', '').upper()

            # Validate if German IBAN
            is_valid = False
            if clean_iban.startswith('DE'):
                is_valid = self.validator.validate_iban(clean_iban)

            entities.append({
                "type": "IBAN",
                "value": clean_iban,
                "formatted": self._format_iban(clean_iban),
                "validated": is_valid,
                "country": clean_iban[:2],
                "confidence": 0.95 if is_valid else 0.7,
                "source": "iban_extraction",
            })

        return entities

    def _format_iban(self, iban: str) -> str:
        """Format IBAN with spaces for readability."""
        return ' '.join([iban[i:i + 4] for i in range(0, len(iban), 4)])

    def _extract_vat_ids(self, text: str) -> List[Dict[str, Any]]:
        """Extract and validate VAT IDs."""
        entities = []

        # German VAT ID pattern
        vat_pattern = r'\b(DE\s?\d{9})\b'
        matches = re.findall(vat_pattern, text, re.IGNORECASE)

        for vat_id in matches:
            clean_vat = vat_id.replace(' ', '').upper()
            is_valid = self.validator.validate_vat_id(clean_vat)

            entities.append({
                "type": "VAT_ID",
                "value": clean_vat,
                "validated": is_valid,
                "confidence": 0.95 if is_valid else 0.7,
                "source": "vat_extraction",
            })

        # Also look for USt-IdNr. pattern
        ust_pattern = r'USt-?IdNr\.?\s*:?\s*(DE\s?\d{9})'
        ust_matches = re.findall(ust_pattern, text, re.IGNORECASE)

        for vat_id in ust_matches:
            clean_vat = vat_id.replace(' ', '').upper()
            if not any(e["value"] == clean_vat for e in entities):
                is_valid = self.validator.validate_vat_id(clean_vat)
                entities.append({
                    "type": "VAT_ID",
                    "value": clean_vat,
                    "validated": is_valid,
                    "confidence": 0.95 if is_valid else 0.7,
                    "source": "vat_extraction",
                })

        return entities

    def _extract_business_terms(self, text: str) -> List[Dict[str, Any]]:
        """Extract German business terms and abbreviations."""
        entities = []

        terms = self.validator.extract_business_terms(text)

        for abbr, info in terms.items():
            entities.append({
                "type": "BUSINESS_TERM",
                "value": abbr,
                "full_name": info["full_name"],
                "count": info["count"],
                "confidence": 0.95,
                "source": "business_term_extraction",
            })

        return entities

    def _extract_contact_info(self, text: str) -> List[Dict[str, Any]]:
        """Extract contact information (email, phone, postal code)."""
        entities = []

        # Extract emails
        emails = re.findall(self.EMAIL_PATTERN, text)
        for email in emails:
            entities.append({
                "type": "EMAIL",
                "value": email.lower(),
                "confidence": 0.95,
                "source": "contact_extraction",
            })

        # Extract phone numbers
        for pattern in self.PHONE_PATTERNS:
            phones = re.findall(pattern, text)
            for phone in phones:
                # Clean up phone number
                clean_phone = re.sub(r'[\s\-/]', '', phone)
                if len(clean_phone) >= 10:  # Minimum valid length
                    entities.append({
                        "type": "PHONE",
                        "value": phone.strip(),
                        "normalized": clean_phone,
                        "confidence": 0.85,
                        "source": "contact_extraction",
                    })

        # Extract postal codes (5-digit German format)
        # Only extract if followed by city name pattern
        postal_pattern = r'\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)\b'
        postal_matches = re.findall(postal_pattern, text)
        for postal, city in postal_matches:
            entities.append({
                "type": "POSTAL_CODE",
                "value": postal,
                "city": city,
                "confidence": 0.9,
                "source": "contact_extraction",
            })

        return entities

    def _extract_invoice_numbers(self, text: str) -> List[Dict[str, Any]]:
        """Extract invoice numbers."""
        entities = []

        for pattern in self.INVOICE_NUMBER_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match[0] else match[-1]

                if match and len(match) >= 4:
                    entities.append({
                        "type": "INVOICE_NUMBER",
                        "value": match.strip(),
                        "confidence": 0.9,
                        "source": "invoice_number_extraction",
                    })

        return entities

    def _extract_tax_numbers(self, text: str) -> List[Dict[str, Any]]:
        """Extract German tax numbers."""
        entities = []

        for pattern in self.TAX_NUMBER_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match[0] else match[-1]

                if match:
                    entities.append({
                        "type": "TAX_NUMBER",
                        "value": match.strip(),
                        "confidence": 0.9,
                        "source": "tax_number_extraction",
                    })

        return entities

    def _extract_invoice_fields(self, text: str) -> Dict[str, Any]:
        """Extract structured invoice fields."""
        return self.validator.extract_invoice_fields(text)

    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about extraction capabilities."""
        return {
            "entity_types": list(self.ENTITY_TYPES.keys()),
            "critical_types": [
                k for k, v in self.ENTITY_TYPES.items() if v["critical"]
            ],
            "supported_date_formats": [
                "DD.MM.YYYY",
                "DD.MM.YY",
                "DD. Month YYYY",
            ],
            "supported_currencies": ["EUR", "€", "Euro"],
            "iban_validation": True,
            "vat_validation": True,
        }
