# -*- coding: utf-8 -*-
"""
Entity Extraction Agent for Ablage-System.

Enterprise-grade business entity extraction from German documents:
- Date extraction (German formats, relative dates, date ranges)
- Currency/amount extraction
- IBAN validation and extraction
- VAT ID (USt-IdNr.) extraction
- Business term recognition
- Invoice field mapping
- Address parsing (multi-line German addresses)
- Contract field extraction
- spaCy NER for persons and organizations
- Advanced entity relationship detection

Feinpoliert und durchdacht - Präzise Entitätserkennung für Geschäftsdokumente.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from app.agents.base import PostprocessingAgent
from app.german_validator import GermanValidator

logger = structlog.get_logger(__name__)

# Try to import spaCy (optional dependency for NER)
try:
    import spacy
    from spacy.tokens import Doc
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None  # type: ignore
    Doc = None  # type: ignore
    logger.info("spacy_not_available", message="spaCy NER deaktiviert")


@dataclass
class GermanAddress:
    """Structured German address."""
    street: Optional[str] = None
    house_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "Deutschland"
    address_addition: Optional[str] = None
    confidence: float = 0.8

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "street": self.street,
            "house_number": self.house_number,
            "postal_code": self.postal_code,
            "city": self.city,
            "country": self.country,
            "address_addition": self.address_addition,
            "formatted": self.format(),
            "confidence": self.confidence,
        }

    def format(self) -> str:
        """Format address as single line."""
        parts = []
        if self.street:
            street_part = self.street
            if self.house_number:
                street_part += f" {self.house_number}"
            parts.append(street_part)
        if self.address_addition:
            parts.append(self.address_addition)
        if self.postal_code or self.city:
            location = f"{self.postal_code or ''} {self.city or ''}".strip()
            parts.append(location)
        if self.country and self.country != "Deutschland":
            parts.append(self.country)
        return ", ".join(parts)


@dataclass
class ContractField:
    """Extracted contract field."""
    field_name: str
    value: str
    german_label: str
    confidence: float = 0.8
    position: Optional[int] = None


# German contract field patterns
CONTRACT_FIELD_PATTERNS: Dict[str, Dict[str, Any]] = {
    "contract_date": {
        "patterns": [
            r"(?:Vertragsdatum|Datum des Vertrags|Abschlussdatum)[\s:]*(\d{1,2}\.\d{1,2}\.\d{4})",
            r"(?:geschlossen am|abgeschlossen am)[\s:]*(\d{1,2}\.\d{1,2}\.\d{4})",
        ],
        "german_label": "Vertragsdatum",
    },
    "start_date": {
        "patterns": [
            r"(?:Vertragsbeginn|Beginn|Laufzeitbeginn|ab dem|beginnend am)[\s:]*(\d{1,2}\.\d{1,2}\.\d{4})",
            r"(?:tritt in Kraft am|wirksam ab)[\s:]*(\d{1,2}\.\d{1,2}\.\d{4})",
        ],
        "german_label": "Vertragsbeginn",
    },
    "end_date": {
        "patterns": [
            r"(?:Vertragsende|Ende|Laufzeitende|bis zum|endet am)[\s:]*(\d{1,2}\.\d{1,2}\.\d{4})",
            r"(?:befristet bis|gültig bis)[\s:]*(\d{1,2}\.\d{1,2}\.\d{4})",
        ],
        "german_label": "Vertragsende",
    },
    "notice_period": {
        "patterns": [
            r"(?:Kündigungsfrist|Frist)[\s:]*(\d+\s*(?:Tage?|Wochen?|Monate?))",
            r"(?:mit einer Frist von)[\s:]*(\d+\s*(?:Tagen?|Wochen?|Monaten?))",
        ],
        "german_label": "Kündigungsfrist",
    },
    "contract_value": {
        "patterns": [
            r"(?:Vertragswert|Gesamtwert|Auftragssumme)[\s:]*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s*(?:€|EUR|Euro))",
            r"(?:in Höhe von)[\s:]*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s*(?:€|EUR|Euro))",
        ],
        "german_label": "Vertragswert",
    },
    "parties": {
        "patterns": [
            r"(?:zwischen|Vertragspartner|Parteien)[\s:]+([A-ZÄÖÜ][^\n,]+?)(?:\s*(?:und|,|\n))",
        ],
        "german_label": "Vertragsparteien",
    },
}


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
        "DATE_RANGE": {"confidence_base": 0.85, "critical": False},
        "RELATIVE_DATE": {"confidence_base": 0.8, "critical": False},
        "CURRENCY": {"confidence_base": 0.9, "critical": True},
        "IBAN": {"confidence_base": 0.95, "critical": True},
        "VAT_ID": {"confidence_base": 0.95, "critical": True},
        "BUSINESS_TERM": {"confidence_base": 0.85, "critical": False},
        "INVOICE_NUMBER": {"confidence_base": 0.9, "critical": True},
        "TAX_NUMBER": {"confidence_base": 0.9, "critical": True},
        "EMAIL": {"confidence_base": 0.95, "critical": False},
        "PHONE": {"confidence_base": 0.85, "critical": False},
        "POSTAL_CODE": {"confidence_base": 0.9, "critical": False},
        "ADDRESS": {"confidence_base": 0.8, "critical": False},
        "PERSON": {"confidence_base": 0.85, "critical": False},
        "ORGANIZATION": {"confidence_base": 0.8, "critical": False},
        "CONTRACT_FIELD": {"confidence_base": 0.85, "critical": True},
    }

    # German street name suffixes
    STREET_SUFFIXES = {
        "straße", "strasse", "str.", "str", "weg", "platz", "allee",
        "ring", "gasse", "damm", "ufer", "chaussee", "steig", "pfad",
        "hof", "anger", "aue", "berg", "brücke", "graben",
    }

    # Common German first names for person detection fallback
    COMMON_FIRST_NAMES: Set[str] = {
        "alexander", "andreas", "anna", "barbara", "bernd", "birgit",
        "brigitte", "christian", "christina", "claudia", "daniel",
        "dieter", "elisabeth", "eva", "frank", "franz", "gabriele",
        "gerhard", "hans", "heinrich", "helga", "helmut", "herbert",
        "ingrid", "jürgen", "karl", "karin", "katharina", "klaus",
        "manfred", "maria", "markus", "martin", "matthias", "michael",
        "monika", "nicole", "norbert", "peter", "petra", "rainer",
        "regina", "renate", "robert", "roland", "sabine", "sandra",
        "stefan", "stephan", "susanne", "thomas", "ulrich", "ursula",
        "walter", "werner", "wolfgang",
    }

    # Relative date expressions (German)
    RELATIVE_DATE_PATTERNS = [
        (r"\bheute\b", "today", 0),
        (r"\bmorgen\b", "tomorrow", 1),
        (r"\bübermorgen\b", "day_after_tomorrow", 2),
        (r"\bgestern\b", "yesterday", -1),
        (r"\bvorgestern\b", "day_before_yesterday", -2),
        (r"\bnächste Woche\b", "next_week", 7),
        (r"\bletzte Woche\b", "last_week", -7),
        (r"\bnächsten Monat\b", "next_month", 30),
        (r"\bletzten Monat\b", "last_month", -30),
        (r"\bin (\d+) Tagen?\b", "in_n_days", None),
        (r"\bvor (\d+) Tagen?\b", "n_days_ago", None),
    ]

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

    def __init__(self, enable_spacy: bool = True):
        """
        Initialize the Entity Extraction Agent.

        Args:
            enable_spacy: Enable spaCy NER for person/organization extraction
        """
        super().__init__(name="entity_extraction_agent")
        self.validator = GermanValidator()

        # Initialize spaCy if available and enabled
        self._nlp: Optional[Any] = None
        if enable_spacy and SPACY_AVAILABLE:
            self._init_spacy()

    def _init_spacy(self) -> None:
        """Initialize spaCy German model for NER."""
        try:
            # Try to load German model (de_core_news_lg preferred, fallback to sm)
            try:
                self._nlp = spacy.load("de_core_news_lg")
                self.logger.info("spacy_initialized", model="de_core_news_lg")
            except OSError:
                try:
                    self._nlp = spacy.load("de_core_news_md")
                    self.logger.info("spacy_initialized", model="de_core_news_md")
                except OSError:
                    try:
                        self._nlp = spacy.load("de_core_news_sm")
                        self.logger.info("spacy_initialized", model="de_core_news_sm")
                    except OSError:
                        self.logger.warning(
                            "spacy_model_not_found",
                            message="Kein deutsches spaCy-Modell gefunden. "
                                    "Installieren mit: python -m spacy download de_core_news_lg",
                        )
        except Exception as e:
            self.logger.warning("spacy_init_failed", error=str(e))
            self._nlp = None

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
        entities.extend(self._extract_relative_dates(text))
        entities.extend(self._extract_date_ranges(text))
        entities.extend(self._extract_currencies(text))
        entities.extend(self._extract_ibans(text))
        entities.extend(self._extract_vat_ids(text))
        entities.extend(self._extract_business_terms(text))
        entities.extend(self._extract_contact_info(text))
        entities.extend(self._extract_invoice_numbers(text))
        entities.extend(self._extract_tax_numbers(text))
        entities.extend(self._extract_addresses(text))

        # spaCy NER for persons and organizations
        if self._nlp:
            entities.extend(self._extract_named_entities_spacy(text))
        else:
            # Fallback to pattern-based extraction
            entities.extend(self._extract_persons_fallback(text))
            entities.extend(self._extract_organizations_fallback(text))

        # Document-specific extraction
        document_type = classification.get("document_type", "other")
        invoice_data = None
        contract_data = None

        if document_type == "invoice":
            invoice_data = self._extract_invoice_fields(text)
            # Add invoice fields as entities
            for field_name, info in invoice_data.items():
                if info.get("value"):
                    entities.append({
                        "type": f"INVOICE_{field_name.upper()}",
                        "value": info["value"],
                        "german_label": info.get("german_label"),
                        "confidence": info.get("confidence", 0.8),
                        "source": "invoice_field",
                    })

        elif document_type in ("contract", "vertrag"):
            contract_data = self._extract_contract_fields(text)
            # Add contract fields as entities
            for field_info in contract_data:
                entities.append({
                    "type": "CONTRACT_FIELD",
                    "field_name": field_info.field_name,
                    "value": field_info.value,
                    "german_label": field_info.german_label,
                    "confidence": field_info.confidence,
                    "source": "contract_field",
                })

        # Deduplicate entities
        original_count = len(entities)
        entities = self._deduplicate_entities(entities)
        duplicates_removed = original_count - len(entities)

        if duplicates_removed > 0:
            self.logger.debug(
                "entities_deduplicated",
                original_count=original_count,
                deduplicated_count=len(entities),
                removed=duplicates_removed,
            )

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
            "spacy_enabled": self._nlp is not None,
        }

        if invoice_data:
            result["invoice_data"] = invoice_data

        if contract_data:
            result["contract_data"] = [f.value for f in contract_data]

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

    def _deduplicate_entities(
        self, entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate entities intelligently.

        Deduplication strategy:
        1. Group entities by type
        2. For each type, find duplicates by normalized value
        3. Merge duplicates, keeping highest confidence
        4. Keep additional metadata from all sources

        Args:
            entities: List of extracted entities

        Returns:
            Deduplicated list of entities
        """
        if not entities:
            return []

        # Group by type
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for entity in entities:
            entity_type = entity.get("type", "UNKNOWN")
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(entity)

        deduplicated = []

        for entity_type, type_entities in by_type.items():
            # Deduplicate within each type
            seen: Dict[str, Dict[str, Any]] = {}

            for entity in type_entities:
                # Get normalized key for deduplication
                key = self._get_entity_key(entity, entity_type)

                if key in seen:
                    # Merge with existing entity
                    seen[key] = self._merge_entities(seen[key], entity)
                else:
                    seen[key] = entity.copy()

            deduplicated.extend(seen.values())

        # Sort by confidence (highest first) and then by type
        deduplicated.sort(
            key=lambda e: (-e.get("confidence", 0), e.get("type", ""))
        )

        return deduplicated

    def _get_entity_key(self, entity: Dict[str, Any], entity_type: str) -> str:
        """
        Get normalized key for entity deduplication.

        Different entity types need different normalization:
        - IBAN: Remove spaces, uppercase
        - PHONE: Remove all non-digits
        - EMAIL: Lowercase
        - CURRENCY: Numeric value if available
        - Others: Stripped, lowercase value

        Args:
            entity: Entity dictionary
            entity_type: Type of the entity

        Returns:
            Normalized key string
        """
        value = entity.get("value", "")

        if entity_type == "IBAN":
            # IBANs: Remove spaces, uppercase
            return value.replace(" ", "").upper()

        elif entity_type == "PHONE":
            # Phone numbers: Only digits
            normalized = entity.get("normalized")
            if normalized:
                return normalized
            return re.sub(r"[^\d+]", "", value)

        elif entity_type == "EMAIL":
            # Emails: Lowercase
            return value.lower().strip()

        elif entity_type == "CURRENCY":
            # Currency: Use numeric value if available
            numeric = entity.get("numeric_value")
            if numeric is not None:
                return f"{entity_type}_{numeric:.2f}"
            return f"{entity_type}_{value.strip()}"

        elif entity_type == "VAT_ID":
            # VAT IDs: Remove spaces, uppercase
            return value.replace(" ", "").upper()

        elif entity_type == "POSTAL_CODE":
            # Postal codes: Just the digits
            return re.sub(r"[^\d]", "", value)

        else:
            # Default: Strip and lowercase
            return f"{entity_type}_{value.strip().lower()}"

    def _merge_entities(
        self,
        existing: Dict[str, Any],
        new: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge two duplicate entities.

        Merging strategy:
        - Keep highest confidence
        - Preserve validation status if any is True
        - Merge sources
        - Keep additional metadata from both

        Args:
            existing: Existing entity (will be modified)
            new: New entity to merge

        Returns:
            Merged entity
        """
        merged = existing.copy()

        # Keep highest confidence
        merged["confidence"] = max(
            existing.get("confidence", 0),
            new.get("confidence", 0)
        )

        # If either is validated, keep True
        if "validated" in existing or "validated" in new:
            merged["validated"] = (
                existing.get("validated", False) or
                new.get("validated", False)
            )

        # Merge sources
        existing_source = existing.get("source", "")
        new_source = new.get("source", "")
        if existing_source and new_source and existing_source != new_source:
            merged["source"] = f"{existing_source}, {new_source}"

        # Track that this was deduplicated
        merged["deduplicated"] = True
        merged["duplicate_count"] = existing.get("duplicate_count", 1) + 1

        # Keep additional fields from new if not in existing
        for key in new:
            if key not in merged and key not in ["source", "confidence"]:
                merged[key] = new[key]

        return merged

    def _extract_relative_dates(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract German relative date expressions.

        Handles expressions like "heute", "morgen", "nächste Woche", etc.
        """
        entities = []
        today = datetime.now()

        for pattern, date_type, offset in self.RELATIVE_DATE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)

            for match in matches:
                if offset is not None:
                    # Fixed offset
                    resolved_date = today + timedelta(days=offset)
                else:
                    # Variable offset (e.g., "in 5 Tagen")
                    try:
                        days = int(match.group(1))
                        if "vor" in pattern:
                            days = -days
                        resolved_date = today + timedelta(days=days)
                    except (IndexError, ValueError):
                        resolved_date = None

                entities.append({
                    "type": "RELATIVE_DATE",
                    "value": match.group(0),
                    "date_type": date_type,
                    "resolved_date": resolved_date.strftime("%d.%m.%Y") if resolved_date else None,
                    "confidence": 0.8,
                    "source": "relative_date_extraction",
                })

        return entities

    def _extract_date_ranges(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract date ranges from German text.

        Handles patterns like "vom 01.01.2024 bis 31.12.2024".
        """
        entities = []

        # Date range patterns
        range_patterns = [
            r"vom?\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:bis|[-–])\s*(?:zum?\s*)?(\d{1,2}\.\d{1,2}\.\d{4})",
            r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–]\s*(\d{1,2}\.\d{1,2}\.\d{4})",
            r"zwischen\s*(?:dem\s*)?(\d{1,2}\.\d{1,2}\.\d{4})\s*und\s*(?:dem\s*)?(\d{1,2}\.\d{1,2}\.\d{4})",
        ]

        for pattern in range_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)

            for match in matches:
                start_date = match.group(1)
                end_date = match.group(2)

                entities.append({
                    "type": "DATE_RANGE",
                    "value": match.group(0),
                    "start_date": start_date,
                    "end_date": end_date,
                    "confidence": 0.85,
                    "source": "date_range_extraction",
                })

        return entities

    def _extract_addresses(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract German addresses from text.

        Handles multi-line addresses and various formats.
        """
        entities = []

        # Street pattern with house number
        street_pattern = (
            r"([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*"
            r"(?:straße|strasse|str\.|weg|platz|allee|ring|gasse|damm|ufer))"
            r"\s*(\d+\s*[a-zA-Z]?(?:\s*[-/]\s*\d+)?)"
        )

        # Full address pattern: Street + House Number + Postal Code + City
        full_address_pattern = (
            street_pattern + r"(?:\s*,?\s*|\s+)"
            r"(\d{5})\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*)"
        )

        # Try full address pattern first
        full_matches = re.finditer(full_address_pattern, text, re.IGNORECASE)

        for match in full_matches:
            address = GermanAddress(
                street=match.group(1).strip(),
                house_number=match.group(2).strip(),
                postal_code=match.group(3),
                city=match.group(4).strip(),
                confidence=0.9,
            )

            entities.append({
                "type": "ADDRESS",
                "value": match.group(0).strip(),
                "structured": address.to_dict(),
                "confidence": address.confidence,
                "source": "address_extraction",
            })

        # Also try simpler street + house number pattern
        street_matches = re.finditer(street_pattern, text, re.IGNORECASE)

        for match in street_matches:
            # Check if already captured in full address
            full_text = match.group(0)
            if any(full_text in e["value"] for e in entities):
                continue

            address = GermanAddress(
                street=match.group(1).strip(),
                house_number=match.group(2).strip(),
                confidence=0.7,
            )

            entities.append({
                "type": "ADDRESS",
                "value": full_text.strip(),
                "structured": address.to_dict(),
                "confidence": address.confidence,
                "source": "address_extraction",
            })

        return entities

    def _extract_named_entities_spacy(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract named entities using spaCy NER.

        Extracts persons (PER) and organizations (ORG) using
        the German spaCy model.
        """
        entities = []

        if not self._nlp:
            return entities

        try:
            # Process text with spaCy (limit to reasonable length)
            doc = self._nlp(text[:100000])  # Limit to ~100k chars

            for ent in doc.ents:
                if ent.label_ == "PER":
                    entities.append({
                        "type": "PERSON",
                        "value": ent.text,
                        "start": ent.start_char,
                        "end": ent.end_char,
                        "confidence": 0.85,
                        "source": "spacy_ner",
                    })
                elif ent.label_ == "ORG":
                    entities.append({
                        "type": "ORGANIZATION",
                        "value": ent.text,
                        "start": ent.start_char,
                        "end": ent.end_char,
                        "confidence": 0.8,
                        "source": "spacy_ner",
                    })

        except Exception as e:
            self.logger.warning("spacy_ner_error", error=str(e))

        return entities

    def _extract_persons_fallback(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract person names using pattern matching (fallback without spaCy).

        Uses common German naming patterns and first name dictionary.
        """
        entities = []

        # Pattern: Title + Name (e.g., "Herr Müller", "Frau Dr. Schmidt")
        title_pattern = (
            r"\b((?:Herr|Frau|Hr\.|Fr\.)\s*"
            r"(?:(?:Dr\.|Prof\.|Dipl\.[-\s]?[A-Za-z]+\.?)\s*)?"
            r"([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?))\b"
        )

        matches = re.finditer(title_pattern, text)
        for match in matches:
            entities.append({
                "type": "PERSON",
                "value": match.group(1).strip(),
                "confidence": 0.8,
                "source": "pattern_person_extraction",
            })

        # Pattern: Known first name + Last name
        for first_name in self.COMMON_FIRST_NAMES:
            pattern = rf"\b({first_name.capitalize()}\s+[A-ZÄÖÜ][a-zäöüß]+)\b"
            matches = re.finditer(pattern, text)

            for match in matches:
                name = match.group(1)
                # Avoid duplicates
                if not any(e["value"] == name for e in entities):
                    entities.append({
                        "type": "PERSON",
                        "value": name,
                        "confidence": 0.75,
                        "source": "pattern_person_extraction",
                    })

        return entities

    def _extract_organizations_fallback(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract organization names using pattern matching (fallback without spaCy).

        Uses German company suffixes and patterns.
        """
        entities = []

        # German company suffixes
        company_suffixes = (
            r"(?:GmbH|AG|KG|OHG|GbR|e\.?V\.?|UG|SE|mbH|"
            r"GmbH\s*&\s*Co\.?\s*KG|"
            r"Inc\.|Corp\.|Ltd\.?|LLC)"
        )

        # Company pattern
        company_pattern = rf"([A-ZÄÖÜ][^\n,;]+?\s*{company_suffixes})"

        matches = re.finditer(company_pattern, text)
        for match in matches:
            company = match.group(1).strip()
            # Clean up
            company = re.sub(r"\s+", " ", company)

            if len(company) > 3:
                entities.append({
                    "type": "ORGANIZATION",
                    "value": company,
                    "confidence": 0.8,
                    "source": "pattern_org_extraction",
                })

        return entities

    def _extract_contract_fields(self, text: str) -> List[ContractField]:
        """
        Extract contract-specific fields from German contracts.

        Uses CONTRACT_FIELD_PATTERNS to find structured data.
        """
        fields = []

        for field_name, config in CONTRACT_FIELD_PATTERNS.items():
            for pattern in config["patterns"]:
                matches = re.finditer(pattern, text, re.IGNORECASE)

                for match in matches:
                    value = match.group(1) if match.lastindex >= 1 else match.group(0)

                    field = ContractField(
                        field_name=field_name,
                        value=value.strip(),
                        german_label=config["german_label"],
                        confidence=0.85,
                        position=match.start(),
                    )
                    fields.append(field)

                    # Only take first match per field type
                    break

        return fields

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
                "Relative dates (heute, morgen, etc.)",
                "Date ranges (vom...bis)",
            ],
            "supported_currencies": ["EUR", "€", "Euro"],
            "iban_validation": True,
            "vat_validation": True,
            "spacy_available": SPACY_AVAILABLE,
            "spacy_enabled": self._nlp is not None,
            "address_extraction": True,
            "contract_fields": list(CONTRACT_FIELD_PATTERNS.keys()),
        }

    # =========================================================================
    # PUBLIC NER API (fuer externe Nutzung ohne full process())
    # =========================================================================

    def extract_named_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Extrahiert Named Entities (Personen, Organisationen) aus Text.

        Oeffentliche API fuer NER-Extraktion ohne vollstaendige process()-Pipeline.
        Nutzt spaCy wenn verfuegbar, sonst Pattern-Matching Fallback.

        Args:
            text: Text zur Analyse (max. 100.000 Zeichen)

        Returns:
            Liste von Entity-Dicts mit:
                - type: "PERSON" oder "ORGANIZATION"
                - value: Extrahierter Name
                - confidence: Konfidenzwert (0.0-1.0)
                - source: Extraktionsmethode
        """
        entities: List[Dict[str, Any]] = []

        # spaCy NER (wenn verfuegbar)
        spacy_entities = self._extract_named_entities_spacy(text)
        entities.extend(spacy_entities)

        # Pattern-Matching Fallback fuer Personen (wenn spaCy keine fand)
        if not any(e["type"] == "PERSON" for e in entities):
            person_entities = self._extract_persons_fallback(text)
            entities.extend(person_entities)

        return entities
