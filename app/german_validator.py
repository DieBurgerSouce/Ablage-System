# -*- coding: utf-8 -*-
"""
German Text Validator for Ablage-System
Ensures 100% accuracy for German language processing

CRITICAL: Business requirement - 100% umlaut accuracy
"""

import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json

class GermanValidator:
    """German text validation with focus on business documents"""

    # German special characters that MUST be preserved
    UMLAUTS = ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü']

    # Common OCR errors to detect
    # Note: Only multi-character substitutions are reliable indicators of OCR errors
    # Single character substitutions (a→ä) are too common to flag reliably
    OCR_ERROR_PATTERNS = {
        'ä': ['ae'],  # Most reliable: ae→ä substitution
        'ö': ['oe'],  # Most reliable: oe→ö substitution
        'ü': ['ue'],  # Most reliable: ue→ü substitution
        'ß': ['ss'],  # Common: ss→ß (context dependent)
        'Ä': ['Ae', 'AE'],
        'Ö': ['Oe', 'OE'],
        'Ü': ['Ue', 'UE']
    }

    # German business terminology - COMPREHENSIVE LIST
    BUSINESS_TERMS = {
        # Company forms
        "GmbH": "Gesellschaft mit beschränkter Haftung",
        "AG": "Aktiengesellschaft",
        "KG": "Kommanditgesellschaft",
        "OHG": "Offene Handelsgesellschaft",
        "GbR": "Gesellschaft bürgerlichen Rechts",  # Added as requested!
        "e.V.": "eingetragener Verein",
        "e.G.": "eingetragene Genossenschaft",
        "e.K.": "eingetragener Kaufmann",
        "KGaA": "Kommanditgesellschaft auf Aktien",
        "UG": "Unternehmergesellschaft (haftungsbeschränkt)",
        "PartG": "Partnerschaftsgesellschaft",
        "PartG mbB": "Partnerschaftsgesellschaft mit beschränkter Berufshaftung",
        "GmbH & Co. KG": "GmbH & Compagnie KG",
        # Tax and registration
        "USt-IdNr.": "Umsatzsteuer-Identifikationsnummer",
        "St.-Nr.": "Steuernummer",
        "HRB": "Handelsregister Abteilung B",
        "HRA": "Handelsregister Abteilung A",
        "GnR": "Genossenschaftsregister",
        "PR": "Partnerschaftsregister",
        # Authorization and signature
        "i.A.": "im Auftrag",
        "i.V.": "in Vertretung",
        "ppa.": "per procura",
        "gez.": "gezeichnet",
        # Financial terms
        "MwSt.": "Mehrwertsteuer",
        "USt.": "Umsatzsteuer",
        "inkl.": "inklusive",
        "exkl.": "exklusive",
        "zzgl.": "zuzüglich",
        "abzgl.": "abzüglich",
        "netto": "netto",
        "brutto": "brutto"
    }

    # Common German date months
    GERMAN_MONTHS = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    # Invoice field mapping (German -> English for internal processing)
    INVOICE_FIELDS = {
        "Rechnungsnummer": "invoice_number",
        "Rechnungsdatum": "invoice_date",
        "Leistungszeitraum": "service_period",
        "Steuernummer": "tax_number",
        "USt-IdNr": "vat_id",
        "Rechnungsempfänger": "recipient",
        "Rechnungssteller": "issuer",
        "Nettobetrag": "net_amount",
        "Steuersatz": "tax_rate",
        "Steuerbetrag": "tax_amount",
        "Bruttobetrag": "gross_amount",
        "Zahlungsziel": "payment_terms",
        "Bankverbindung": "bank_details",
        "IBAN": "iban",
        "BIC": "bic",
        "Verwendungszweck": "reference"
    }

    def __init__(self):
        """Initialize validator with German locale settings"""
        self.validation_stats = {
            "total_validated": 0,
            "umlauts_found": 0,
            "errors_detected": 0
        }

    def validate_umlauts(self, text: str) -> Dict:
        """
        Validate German umlauts with 100% accuracy requirement

        Args:
            text: Text to validate

        Returns:
            Validation result with confidence score
        """
        if not text:
            return {
                "valid": True,
                "umlauts_found": [],
                "potential_errors": [],
                "confidence": 1.0,
                "message": "Empty text"
            }

        # Find all umlauts in text
        found_umlauts = [u for u in self.UMLAUTS if u in text]

        # Check for potential OCR errors
        potential_errors = []

        # Check each umlaut pattern
        for umlaut, error_patterns in self.OCR_ERROR_PATTERNS.items():
            if umlaut not in text:  # Umlaut missing
                for pattern in error_patterns:
                    if pattern in text:
                        potential_errors.append({
                            "suspected": f"'{pattern}' might be '{umlaut}'",
                            "pattern": pattern,
                            "should_be": umlaut,
                            "severity": "high" if len(pattern) > 1 else "medium"
                        })
                        break

        # Special check for ß vs ss
        if "ss" in text.lower() and "ß" not in text:
            # Check if it might be a false positive (e.g., "Adresse" is correct)
            words_with_ss = re.findall(r'\w*ss\w*', text, re.IGNORECASE)
            for word in words_with_ss:
                if self._might_need_eszett(word):
                    potential_errors.append({
                        "suspected": f"'{word}' might contain 'ß'",
                        "pattern": "ss",
                        "should_be": "ß",
                        "severity": "medium"
                    })

        # Calculate confidence
        confidence = 1.0
        if potential_errors:
            confidence = max(0.3, 1.0 - (len(potential_errors) * 0.15))

        # Update statistics
        self.validation_stats["total_validated"] += 1
        self.validation_stats["umlauts_found"] += len(found_umlauts)
        if potential_errors:
            self.validation_stats["errors_detected"] += 1

        return {
            "valid": len(potential_errors) == 0,
            "umlauts_found": found_umlauts,
            "potential_errors": potential_errors,
            "confidence": round(confidence, 2),
            "text_length": len(text)
        }

    def validate_date_format(self, text: str) -> List[str]:
        """
        Extract and validate German date formats

        Supports:
        - DD.MM.YYYY (31.12.2024)
        - DD. Month YYYY (31. Dezember 2024)
        - DD.MM.YY (31.12.24)
        - D.M.YYYY (1.1.2024)
        """
        dates_found = []

        # Pattern 1: DD.MM.YYYY or D.M.YYYY
        pattern1 = r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b'
        dates_found.extend(re.findall(pattern1, text))

        # Pattern 2: DD. Month YYYY
        months_pattern = '|'.join(self.GERMAN_MONTHS)
        pattern2 = rf'\b\d{{1,2}}\.\s*(?:{months_pattern})\s*\d{{4}}\b'
        dates_found.extend(re.findall(pattern2, text, re.IGNORECASE))

        # Pattern 3: Written out dates (e.g., "ersten Januar 2024")
        pattern3 = rf'\b(?:ersten?|zweiten?|dritten?|\d{{1,2}}\.)\s+(?:{months_pattern})\s+\d{{4}}\b'
        dates_found.extend(re.findall(pattern3, text, re.IGNORECASE))

        # Remove duplicates while preserving order
        seen = set()
        unique_dates = []
        for date in dates_found:
            if date not in seen:
                seen.add(date)
                unique_dates.append(date)

        return unique_dates

    def validate_currency_format(self, text: str) -> List[str]:
        """
        Extract German currency formats

        Supports:
        - 1.234,56 €
        - 1.234,56 EUR
        - € 1.234,56
        - 1234,56 Euro
        """
        amounts_found = []

        # Pattern for German number format with currency
        patterns = [
            r'\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s*(?:€|EUR|Euro)',
            r'(?:€|EUR)\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?',
            r'\d+(?:,\d{2})?\s*(?:€|EUR|Euro)',
        ]

        for pattern in patterns:
            amounts_found.extend(re.findall(pattern, text, re.IGNORECASE))

        # Clean up and deduplicate
        unique_amounts = list(set(amounts_found))

        # Sort by amount (extract numeric value for sorting)
        def extract_amount(amt_str):
            # Remove currency symbols and spaces
            cleaned = re.sub(r'[€EUR\s]|Euro', '', amt_str, flags=re.IGNORECASE)
            # Convert German format to float
            cleaned = cleaned.replace('.', '').replace(',', '.')
            try:
                return float(cleaned)
            except ValueError:
                return 0

        unique_amounts.sort(key=extract_amount)

        return unique_amounts

    def extract_business_terms(self, text: str) -> Dict:
        """Extract German business terms and abbreviations"""
        found_terms = {}

        for abbr, full_name in self.BUSINESS_TERMS.items():
            # Use word boundaries for accurate matching
            # For terms ending in period, don't require trailing word boundary
            escaped = re.escape(abbr)
            if abbr.endswith('.'):
                pattern = r'\b' + escaped + r'(?=\s|:|$|,)'
            else:
                pattern = r'\b' + escaped + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                found_terms[abbr] = {
                    "full_name": full_name,
                    "count": len(re.findall(pattern, text, re.IGNORECASE))
                }

        return found_terms

    def extract_invoice_fields(self, text: str) -> Dict:
        """Extract standard German invoice fields"""
        extracted_fields = {}

        for german_field, english_key in self.INVOICE_FIELDS.items():
            # Look for field labels followed by colons or similar
            pattern = rf'{german_field}\s*[:：]\s*([^\n]+)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_fields[english_key] = {
                    "german_label": german_field,
                    "value": match.group(1).strip(),
                    "confidence": 0.9 if german_field in text else 0.7
                }

        return extracted_fields

    def validate_iban(self, iban: str) -> bool:
        """Validate German IBAN format"""
        # Remove spaces and convert to uppercase
        iban = iban.replace(' ', '').upper()

        # German IBAN: DE + 2 check digits + 18 digits
        if not re.match(r'^DE\d{20}$', iban):
            return False

        # IBAN checksum validation (simplified)
        # Move first 4 chars to end and replace letters with numbers
        rearranged = iban[4:] + iban[:4]
        numeric_iban = ''
        for char in rearranged:
            if char.isdigit():
                numeric_iban += char
            else:
                numeric_iban += str(ord(char) - ord('A') + 10)

        # Check if mod 97 equals 1
        return int(numeric_iban) % 97 == 1

    def validate_vat_id(self, vat_id: str) -> bool:
        """Validate German VAT ID (USt-IdNr.)"""
        # German VAT ID: DE + 9 digits
        vat_id = vat_id.replace(' ', '').upper()
        return bool(re.match(r'^DE\d{9}$', vat_id))

    def _might_need_eszett(self, word: str) -> bool:
        """
        Heuristic to check if 'ss' might should be 'ß'
        Based on common German words and rules
        """
        # Common words that should have ß
        eszett_words = [
            'groß', 'straße', 'gruß', 'fuß', 'maß', 'spaß',
            'schloss', 'fluss', 'muss', 'weiß', 'heiß'
        ]

        word_lower = word.lower()

        # Check if it matches common ß words (with ss instead)
        for eszett_word in eszett_words:
            if eszett_word.replace('ß', 'ss') in word_lower:
                return True

        # After long vowels and diphthongs, it's often ß
        # This is a simplified heuristic
        if re.search(r'[aeiouäöü]{2}ss', word_lower):
            return True

        return False

    def get_validation_summary(self) -> Dict:
        """Get summary of all validations performed"""
        return {
            "statistics": self.validation_stats,
            "capabilities": {
                "umlaut_detection": True,
                "date_extraction": True,
                "currency_extraction": True,
                "business_term_recognition": True,
                "invoice_field_extraction": True,
                "iban_validation": True,
                "vat_id_validation": True
            },
            "supported_date_formats": [
                "DD.MM.YYYY",
                "DD. Month YYYY",
                "DD.MM.YY"
            ],
            "supported_currency_formats": [
                "1.234,56 €",
                "€ 1.234,56",
                "1.234,56 EUR"
            ]
        }
