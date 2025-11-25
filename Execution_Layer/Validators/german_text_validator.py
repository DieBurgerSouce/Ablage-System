"""
German Text Validator - Specialized German Language Validation

Comprehensive validation for German text extracted via OCR.
Handles umlauts, special characters, business terms, and formatting.
"""

import re
import unicodedata
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ValidationSeverity(Enum):
    """Validation issue severity."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Validation issue found in text."""
    severity: ValidationSeverity
    field: str
    message: str
    original_value: str
    suggested_correction: Optional[str] = None
    confidence: float = 1.0


@dataclass
class ValidationResult:
    """Result of text validation."""
    is_valid: bool
    issues: List[ValidationIssue]
    corrected_text: Optional[str] = None
    confidence_score: float = 1.0


class GermanTextValidator:
    """
    Validator for German text extracted from documents.

    Capabilities:
    - Umlaut validation (ä, ö, ü, ß)
    - Business term validation
    - Date format validation
    - Currency format validation
    - Tax ID validation
    - Company name validation
    """

    def __init__(self):
        # German umlauts and special characters
        self.german_umlauts = {'ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß'}

        # Common OCR misrecognitions for umlauts
        self.umlaut_misrecognitions = {
            'ü': ['ii', 'u', 'ue'],
            'Ü': ['II', 'U', 'Ue'],
            'ä': ['a', 'ae', '£'],
            'Ä': ['A', 'Ae'],
            'ö': ['o', 'oe', '6'],
            'Ö': ['O', 'Oe'],
            'ß': ['ss', 'B', 'ẞ']
        }

        # German business terms (from glossar)
        self.business_terms = {
            'legal_entities': [
                'GmbH', 'AG', 'KG', 'GbR', 'UG', 'e.V.', 'PartG',
                'OHG', 'KGaA', 'SE', 'eG'
            ],
            'business_roles': [
                'Geschäftsführer', 'Vorstand', 'Prokurist',
                'Gesellschafter', 'Kommanditist'
            ],
            'document_types': [
                'Rechnung', 'Lieferschein', 'Vertrag', 'Angebot',
                'Bestellung', 'Gutschrift', 'Mahnung'
            ],
            'invoice_fields': [
                'Rechnungsnummer', 'Rechnungsdatum', 'Leistungsdatum',
                'Zahlungsziel', 'Nettobetrag', 'Bruttobetrag',
                'Umsatzsteuer', 'Mehrwertsteuer'
            ]
        }

        # German date patterns
        self.date_patterns = [
            r'\d{1,2}\.\d{1,2}\.\d{4}',  # DD.MM.YYYY
            r'\d{1,2}\.\d{1,2}\.\d{2}',  # DD.MM.YY
        ]

        # German currency pattern
        self.currency_pattern = r'\d{1,3}(?:\.\d{3})*,\d{2}\s*€?'

    def validate(self, text: str, field_name: str = "text") -> ValidationResult:
        """
        Comprehensive validation of German text.

        Args:
            text: Text to validate
            field_name: Name of the field being validated

        Returns:
            ValidationResult with issues and corrections
        """
        issues = []

        # 1. Unicode normalization check
        issues.extend(self._validate_unicode_normalization(text, field_name))

        # 2. Umlaut validation
        issues.extend(self._validate_umlauts(text, field_name))

        # 3. Business term validation
        issues.extend(self._validate_business_terms(text, field_name))

        # 4. Format validation (dates, currency, etc.)
        issues.extend(self._validate_formats(text, field_name))

        # 5. Character set validation
        issues.extend(self._validate_character_set(text, field_name))

        # Determine if valid (only errors make it invalid)
        is_valid = not any(issue.severity == ValidationSeverity.ERROR for issue in issues)

        # Calculate confidence score
        confidence_score = self._calculate_confidence(text, issues)

        # Generate corrected text if needed
        corrected_text = self._generate_corrections(text, issues) if issues else None

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            corrected_text=corrected_text,
            confidence_score=confidence_score
        )

    def _validate_unicode_normalization(
        self,
        text: str,
        field_name: str
    ) -> List[ValidationIssue]:
        """Validate Unicode normalization (NFC required for German)."""
        issues = []

        normalized = unicodedata.normalize('NFC', text)
        if normalized != text:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field=field_name,
                message="Text is not in NFC normalization form",
                original_value=text,
                suggested_correction=normalized,
                confidence=1.0
            ))

        return issues

    def _validate_umlauts(self, text: str, field_name: str) -> List[ValidationIssue]:
        """Validate German umlauts and detect common OCR errors."""
        issues = []

        # Check for common umlaut misrecognitions
        for correct, misrecognitions in self.umlaut_misrecognitions.items():
            for wrong in misrecognitions:
                # Look for patterns that suggest misrecognition
                # Example: "Muller" should be "Müller"
                if wrong in text:
                    # Context-aware detection
                    if self._is_likely_umlaut_error(text, wrong, correct):
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            field=field_name,
                            message=f"Possible umlaut misrecognition: '{wrong}' might be '{correct}'",
                            original_value=text,
                            suggested_correction=text.replace(wrong, correct),
                            confidence=0.7  # Lower confidence for suggestions
                        ))

        return issues

    def _is_likely_umlaut_error(
        self,
        text: str,
        wrong: str,
        correct: str
    ) -> bool:
        """
        Check if wrong character is likely a misrecognized umlaut.

        Uses context and known German words to determine likelihood.
        """
        # Common German words with umlauts
        common_words_with_umlauts = [
            'Müller', 'München', 'Köln', 'Düsseldorf', 'Geschäftsführer',
            'übernehmen', 'für', 'über', 'früher', 'größer', 'möglich',
            'Straße', 'Größe'
        ]

        # Check if replacing would create a known word
        potential_correction = text.replace(wrong, correct)

        for word in common_words_with_umlauts:
            if word in potential_correction:
                return True

        return False

    def _validate_business_terms(
        self,
        text: str,
        field_name: str
    ) -> List[ValidationIssue]:
        """Validate German business terminology."""
        issues = []

        # Check for legal entity abbreviations
        for entity in self.business_terms['legal_entities']:
            # Look for malformed versions
            # Example: "GmbH" often misread as "GmbI-I" or "Gm bH"
            pattern = re.escape(entity)
            if not re.search(pattern, text):
                # Check for common OCR errors
                malformed_patterns = [
                    entity.replace('b', 'l'),  # b -> l
                    entity.replace('H', 'I-I'),  # H -> I-I
                    entity.replace('G', 'C'),  # G -> C
                ]

                for malformed in malformed_patterns:
                    if malformed in text:
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            field=field_name,
                            message=f"Possible business term misrecognition: '{malformed}' should be '{entity}'",
                            original_value=text,
                            suggested_correction=text.replace(malformed, entity),
                            confidence=0.8
                        ))

        return issues

    def _validate_formats(
        self,
        text: str,
        field_name: str
    ) -> List[ValidationIssue]:
        """Validate German date and currency formats."""
        issues = []

        # Validate dates
        issues.extend(self._validate_dates(text, field_name))

        # Validate currency
        issues.extend(self._validate_currency(text, field_name))

        # Validate tax IDs
        issues.extend(self._validate_tax_ids(text, field_name))

        return issues

    def _validate_dates(self, text: str, field_name: str) -> List[ValidationIssue]:
        """Validate German date format (DD.MM.YYYY)."""
        issues = []

        # Find all date-like patterns
        for pattern in self.date_patterns:
            matches = re.findall(pattern, text)

            for match in matches:
                if not self._is_valid_german_date(match):
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        field=field_name,
                        message=f"Invalid German date format: '{match}'",
                        original_value=match,
                        confidence=1.0
                    ))

        return issues

    def _is_valid_german_date(self, date_str: str) -> bool:
        """Check if date string is valid German date."""
        # Simple validation: check day/month ranges
        parts = date_str.split('.')
        if len(parts) != 3:
            return False

        try:
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])

            if not (1 <= day <= 31):
                return False
            if not (1 <= month <= 12):
                return False
            if len(parts[2]) == 4 and not (1900 <= year <= 2100):
                return False

            return True

        except ValueError:
            return False

    def _validate_currency(
        self,
        text: str,
        field_name: str
    ) -> List[ValidationIssue]:
        """Validate German currency format (1.234,56 €)."""
        issues = []

        # Find currency-like patterns
        matches = re.findall(r'\d+[,\.]\d+\s*€?', text)

        for match in matches:
            if not self._is_valid_german_currency(match):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field=field_name,
                    message=f"Non-standard currency format: '{match}' (expected German format: 1.234,56 €)",
                    original_value=match,
                    confidence=0.9
                ))

        return issues

    def _is_valid_german_currency(self, currency_str: str) -> bool:
        """Check if currency string uses German format."""
        # German format uses comma for decimals, period for thousands
        return ',' in currency_str

    def _validate_tax_ids(
        self,
        text: str,
        field_name: str
    ) -> List[ValidationIssue]:
        """Validate German tax IDs (Steuernummer, USt-IdNr)."""
        issues = []

        # Steuernummer pattern: XX/XXX/XXXXX
        steuernummer_pattern = r'\d{2,3}/\d{3}/\d{5}'
        steuernummer_matches = re.findall(steuernummer_pattern, text)

        # USt-IdNr pattern: DEXXXXXXXXX
        ust_idnr_pattern = r'DE\d{9}'
        ust_idnr_matches = re.findall(ust_idnr_pattern, text)

        # Basic validation (more complex validation would check checksums)
        for match in ust_idnr_matches:
            if len(match) != 11:  # DE + 9 digits
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field=field_name,
                    message=f"Invalid USt-IdNr format: '{match}'",
                    original_value=match,
                    confidence=1.0
                ))

        return issues

    def _validate_character_set(
        self,
        text: str,
        field_name: str
    ) -> List[ValidationIssue]:
        """Validate that text uses appropriate German character set."""
        issues = []

        # Check for suspicious characters that might indicate OCR errors
        suspicious_chars = ['¬', '§', '£', '¢', '¥', '|', '~']

        for char in suspicious_chars:
            if char in text:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field=field_name,
                    message=f"Suspicious character '{char}' found (possible OCR error)",
                    original_value=text,
                    confidence=0.8
                ))

        return issues

    def _calculate_confidence(
        self,
        text: str,
        issues: List[ValidationIssue]
    ) -> float:
        """Calculate overall confidence score for validation."""
        if not issues:
            return 1.0

        # Start with perfect confidence
        confidence = 1.0

        # Deduct based on issue severity
        for issue in issues:
            if issue.severity == ValidationSeverity.ERROR:
                confidence -= 0.15
            elif issue.severity == ValidationSeverity.WARNING:
                confidence -= 0.05

        return max(0.0, confidence)

    def _generate_corrections(
        self,
        text: str,
        issues: List[ValidationIssue]
    ) -> str:
        """Generate corrected text based on validation issues."""
        corrected = text

        # Apply suggested corrections
        for issue in issues:
            if issue.suggested_correction and issue.confidence > 0.7:
                corrected = issue.suggested_correction

        return corrected


# ============================================================================
# Specialized Validators
# ============================================================================

class CompanyNameValidator:
    """Validator for German company names."""

    @staticmethod
    def validate(company_name: str) -> ValidationResult:
        """Validate German company name."""
        issues = []

        # Must contain legal entity suffix
        legal_entities = ['GmbH', 'AG', 'KG', 'GbR', 'UG', 'e.V.']
        has_legal_entity = any(entity in company_name for entity in legal_entities)

        if not has_legal_entity:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                field="company_name",
                message="Company name missing legal entity suffix (GmbH, AG, etc.)",
                original_value=company_name,
                confidence=1.0
            ))

        return ValidationResult(
            is_valid=len(issues) == 0,
            issues=issues
        )


class InvoiceNumberValidator:
    """Validator for German invoice numbers."""

    @staticmethod
    def validate(invoice_number: str) -> ValidationResult:
        """Validate invoice number format."""
        issues = []

        # Must be unique and sequential (basic check for format)
        if len(invoice_number) < 4:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                field="invoice_number",
                message="Invoice number too short (minimum 4 characters)",
                original_value=invoice_number,
                confidence=1.0
            ))

        # Check for valid characters (alphanumeric, dash, slash)
        if not re.match(r'^[A-Z0-9\-/]+$', invoice_number):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field="invoice_number",
                message="Invoice number contains unusual characters",
                original_value=invoice_number,
                confidence=0.9
            ))

        return ValidationResult(
            is_valid=len(issues) == 0,
            issues=issues
        )


# ============================================================================
# Usage Example
# ============================================================================

if __name__ == "__main__":
    validator = GermanTextValidator()

    # Example 1: Text with umlauts
    result = validator.validate("Müller GmbH", "company_name")
    print(f"Valid: {result.is_valid}, Issues: {len(result.issues)}")

    # Example 2: Text with potential OCR errors
    result = validator.validate("Muller GmbI-I", "company_name")
    print(f"Valid: {result.is_valid}, Issues: {len(result.issues)}")
    for issue in result.issues:
        print(f"  - {issue.severity.value}: {issue.message}")
        if issue.suggested_correction:
            print(f"    Suggested: {issue.suggested_correction}")

    # Example 3: Date validation
    result = validator.validate("Datum: 32.13.2024", "invoice_date")
    print(f"Valid: {result.is_valid}, Issues: {len(result.issues)}")


# See also:
# - Static_Knowledge/Skills/german_text_processing_skill.yaml
# - Static_Knowledge/Snippets/german_validation_snippets.py
# - Static_Knowledge/Glossar/business_terms_de.yaml
# - app/german_validator.py
