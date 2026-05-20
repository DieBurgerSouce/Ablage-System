# -*- coding: utf-8 -*-
"""
German Text Validator for Ablage-System
Ensures 100% accuracy for German language processing

CRITICAL: Business requirement - 100% umlaut accuracy

Erweitert um:
- EnhancedUmlautHandler: Kontextbasierte Umlaut-Wiederherstellung
- GermanCapitalizationValidator: Deutsche Großschreibungs-Validierung
"""

import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple
from datetime import datetime
import json

import structlog

logger = structlog.get_logger(__name__)

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


# =============================================================================
# Enhanced Umlaut Handler (NEU)
# =============================================================================


@dataclass
class UmlautCorrection:
    """Details zu einer Umlaut-Korrektur."""
    original: str
    corrected: str
    position: int
    confidence: float
    rule_applied: str


class EnhancedUmlautHandler:
    """
    Kontextbewusste Umlaut-Wiederherstellung mit False-Positive-Vermeidung.

    Behandelt:
    - ae -> ä, oe -> ö, ue -> ü Konvertierung
    - ss -> ß nach langen Vokalen
    - Vermeidung von False Positives (Israel, Michael, etc.)
    """

    # Wörter die NICHT konvertiert werden dürfen (False Positives)
    FALSE_POSITIVES: FrozenSet[str] = frozenset([
        # Eigennamen mit ae
        "israel", "michael", "rafael", "raphael", "gabriel", "nathanael",
        "ismaël", "ismael", "aero", "aerob", "maestro", "pharao",
        "mae", "gaelic", "paella",
        # Wörter mit oe
        "poet", "poesie", "poem", "koexistenz", "koeffizient",
        "boeing", "phoenix", "oekumene", "noel", "joel", "roentgen",
        # Wörter mit ue
        "bauer", "mauer", "trauer", "sauer", "treue", "neue", "reue",
        "feuer", "euer", "teuer", "steuer", "abenteuer", "ungeheuer",
        "queue", "duell", "duett", "suez", "manuel", "sequel",
        "fuel", "cruel", "duel",
        # Wörter mit ss das kein ß sein soll
        "adresse", "adressen", "esse", "essen", "messe", "message",
        "professor", "mission", "passion", "session",
    ])

    # Wörter die definitiv Umlaute haben sollten
    DEFINITE_UMLAUTS: Dict[str, str] = {
        # ae -> ä
        "ärger": "Ärger", "änderung": "Änderung", "aerztlich": "ärztlich",
        "aesthetik": "Ästhetik", "äquivalent": "äquivalent",
        "muenchen": "München", "nuernberg": "Nürnberg",
        "geschäftsführer": "Geschäftsführer", "geschäft": "Geschäft",
        "tätigkeit": "Tätigkeit", "währung": "Währung",
        "nächste": "nächste", "später": "später",
        "stärke": "Stärke", "länge": "Länge",
        # oe -> ö
        "oesterreich": "Österreich", "koeln": "Köln",
        "goettingen": "Göttingen", "moenchengladbach": "Mönchengladbach",
        "öffnung": "Öffnung", "moechte": "möchte",
        "können": "können", "hoeren": "hören",
        "größe": "Größe", "schoenheit": "Schönheit",
        # ue -> ü
        "muenster": "Münster", "duesseldorf": "Düsseldorf",
        "zuerich": "Zürich", "gruende": "Gründe",
        "prüfung": "Prüfung", "verfügung": "Verfügung",
        "führung": "Führung", "begruendung": "Begründung",
        "überprüfen": "überprüfen", "übersicht": "Übersicht",
        # ss -> ß
        "strasse": "Straße", "gruss": "Gruß", "fuss": "Fuß",
        "mass": "Maß", "spass": "Spaß", "gross": "groß",
        "weiss": "weiß", "heiss": "heiß",
    }

    # Sichere Kontexte für Konvertierung
    # (Regex-Pattern, ob Konvertierung sicher ist)
    SAFE_PATTERNS: Dict[str, List[Tuple[str, bool]]] = {
        "ae": [
            # Sichere Konvertierungen
            (r'(?<=[bcdfghjklmnprstvwxz])ae(?=[lnrst])', True),  # z.B. "Änderung"
            (r'^ae(?=[gmnrst])', True),  # Wortanfang mit ae
            (r'(?<=sch)ae(?=[ft])', True),  # z.B. "Geschäft"
            # Unsichere/False Positives
            (r'(?<=[aeiou])ae', False),  # Nach Vokal
            (r'ae(?=l$)', False),  # Endet auf -ael (Michael, etc.)
        ],
        "oe": [
            (r'(?<=[bcdfghjklmnprstvwxz])oe(?=[fhlnrs])', True),
            (r'^oe(?=[fst])', True),
            (r'(?<=k|g|sch)oe(?=[n])', True),  # können, mögen
            (r'oe(?=t$)', False),  # Poet
            (r'(?<=[aeiou])oe', False),
        ],
        "ue": [
            (r'(?<=[bcdfghjklmnprstvwxz])ue(?=[bcdfghlmnrst])', True),
            (r'^ue(?=[b])', True),  # über
            (r'(?<=f|pr)ue(?=[f])', True),  # Prüfung, Führung
            (r'ue(?=r$)', False),  # Bauer, Mauer
            (r'(?<=e|a)ue(?=r)', False),  # Feuer, Steuer
        ],
    }

    def __init__(self, strict_mode: bool = True) -> None:
        """
        Initialisiere Enhanced Umlaut Handler.

        Args:
            strict_mode: Bei True nur sichere Konvertierungen
        """
        self.strict_mode = strict_mode
        self._definite_lookup: Dict[str, str] = {
            k.lower(): v for k, v in self.DEFINITE_UMLAUTS.items()
        }
        logger.debug("EnhancedUmlautHandler initialisiert", strict_mode=strict_mode)

    def restore_umlauts(self, text: str) -> Tuple[str, List[UmlautCorrection]]:
        """
        Stelle Umlaute kontextbewusst wieder her.

        Args:
            text: Der zu korrigierende Text

        Returns:
            (korrigierter_text, liste_der_korrekturen)
        """
        if not text:
            return text, []

        corrections: List[UmlautCorrection] = []
        result = text

        # Zuerst definitive Wörter ersetzen
        words = re.findall(r'\b\w+\b', result)
        for word in words:
            word_lower = word.lower()
            if word_lower in self._definite_lookup:
                correct = self._definite_lookup[word_lower]
                # Case-Preserving
                if word[0].isupper():
                    correct = correct[0].upper() + correct[1:]
                if word != correct:
                    pos = result.find(word)
                    corrections.append(UmlautCorrection(
                        original=word,
                        corrected=correct,
                        position=pos,
                        confidence=0.95,
                        rule_applied="definite_word",
                    ))
                    result = result.replace(word, correct, 1)

        # Dann kontextbasierte Konvertierung
        if not self.strict_mode:
            result, ctx_corrections = self._apply_context_patterns(result)
            corrections.extend(ctx_corrections)

        return result, corrections

    def _apply_context_patterns(self, text: str) -> Tuple[str, List[UmlautCorrection]]:
        """Wende kontextbasierte Muster an."""
        corrections: List[UmlautCorrection] = []
        result = text

        # ae -> ä
        result, ae_corr = self._convert_pattern(result, "ae", "ä")
        corrections.extend(ae_corr)

        # oe -> ö
        result, oe_corr = self._convert_pattern(result, "oe", "ö")
        corrections.extend(oe_corr)

        # ue -> ü
        result, ue_corr = self._convert_pattern(result, "ue", "ü")
        corrections.extend(ue_corr)

        return result, corrections

    def _convert_pattern(
        self,
        text: str,
        pattern: str,
        replacement: str,
    ) -> Tuple[str, List[UmlautCorrection]]:
        """Konvertiere einzelnes Pattern mit Kontextprüfung."""
        corrections: List[UmlautCorrection] = []
        result = text

        # Finde alle Vorkommen
        pattern_lower = pattern.lower()
        idx = 0
        while True:
            idx = result.lower().find(pattern_lower, idx)
            if idx == -1:
                break

            # Extrahiere umgebendes Wort
            word_start = idx
            word_end = idx + len(pattern)

            while word_start > 0 and result[word_start - 1].isalpha():
                word_start -= 1
            while word_end < len(result) and result[word_end].isalpha():
                word_end += 1

            word = result[word_start:word_end]

            # Prüfe False Positives
            if word.lower() in self.FALSE_POSITIVES:
                idx += len(pattern)
                continue

            # Prüfe sichere Muster
            is_safe = self._is_safe_conversion(text, idx, pattern)

            if is_safe:
                # Ersetze
                original_char = result[idx:idx + len(pattern)]
                if original_char[0].isupper():
                    new_char = replacement.upper()
                else:
                    new_char = replacement

                corrections.append(UmlautCorrection(
                    original=original_char,
                    corrected=new_char,
                    position=idx,
                    confidence=0.85,
                    rule_applied=f"context_{pattern}_to_{replacement}",
                ))

                result = result[:idx] + new_char + result[idx + len(pattern):]
                idx += 1
            else:
                idx += len(pattern)

        return result, corrections

    def _is_safe_conversion(self, text: str, position: int, pattern: str) -> bool:
        """Prüfe ob Konvertierung sicher ist."""
        patterns = self.SAFE_PATTERNS.get(pattern, [])

        # Hole Kontext
        start = max(0, position - 5)
        end = min(len(text), position + len(pattern) + 5)
        context = text[start:end]

        for regex, is_safe in patterns:
            if re.search(regex, context, re.IGNORECASE):
                return is_safe

        # Default: unsicher
        return False

    def is_false_positive(self, word: str) -> bool:
        """Prüfe ob Wort ein bekannter False Positive ist."""
        return word.lower() in self.FALSE_POSITIVES


# =============================================================================
# German Capitalization Validator (NEU)
# =============================================================================


@dataclass
class CapitalizationIssue:
    """Ein Großschreibungs-Problem."""
    word: str
    position: int
    expected_capitalized: bool
    reason: str


class GermanCapitalizationValidator:
    """
    Validiert deutsche Großschreibungs-Regeln.

    Prüft:
    - Substantive müssen großgeschrieben sein
    - Satzanfänge großgeschrieben
    - Formelles Sie/Ihnen großgeschrieben
    """

    # Substantiv-Suffixe (indizieren Nomen)
    NOUN_SUFFIXES: FrozenSet[str] = frozenset([
        "ung", "heit", "keit", "schaft", "nis", "tum", "ling",
        "tion", "sion", "ität", "ismus", "ant", "ent", "ist", "or",
        "eur", "eur", "ie", "ik", "ur", "age", "enz", "anz",
    ])

    # Artikel (folgendes Wort ist meist Substantiv)
    ARTICLES: FrozenSet[str] = frozenset([
        "der", "die", "das", "den", "dem", "des",
        "ein", "eine", "einer", "einem", "einen", "eines",
        "kein", "keine", "keiner", "keinem", "keinen", "keines",
    ])

    # Präpositionen mit Artikel (folgendes Wort ist meist Substantiv)
    PREPOSITION_ARTICLE_COMBOS: FrozenSet[str] = frozenset([
        "im", "am", "zum", "zur", "vom", "beim", "ans", "aufs", "ins",
    ])

    # Formelle Anrede (immer großgeschrieben)
    FORMAL_PRONOUNS: FrozenSet[str] = frozenset([
        "sie", "ihnen", "ihr", "ihre", "ihrer", "ihrem", "ihren",
    ])

    def __init__(self) -> None:
        """Initialisiere Capitalization Validator."""
        logger.debug("GermanCapitalizationValidator initialisiert")

    def validate(self, text: str) -> Tuple[float, List[CapitalizationIssue]]:
        """
        Validiere Großschreibung im Text.

        Args:
            text: Der zu validierende Text

        Returns:
            (accuracy, list_of_issues)
        """
        if not text:
            return 1.0, []

        issues: List[CapitalizationIssue] = []
        words = self._tokenize_with_context(text)

        total_nouns = 0
        correct_capitalization = 0

        for word, position, prev_word, is_sentence_start in words:
            if len(word) < 2:
                continue

            # Prüfe ob es ein Substantiv sein sollte
            should_be_capitalized, reason = self._should_be_capitalized(
                word, prev_word, is_sentence_start
            )

            if should_be_capitalized:
                total_nouns += 1
                is_capitalized = word[0].isupper()

                if is_capitalized:
                    correct_capitalization += 1
                else:
                    issues.append(CapitalizationIssue(
                        word=word,
                        position=position,
                        expected_capitalized=True,
                        reason=reason,
                    ))

        accuracy = correct_capitalization / total_nouns if total_nouns > 0 else 1.0

        return accuracy, issues

    def _tokenize_with_context(
        self,
        text: str,
    ) -> List[Tuple[str, int, Optional[str], bool]]:
        """
        Tokenisiere mit Kontext.

        Returns:
            List von (word, position, prev_word, is_sentence_start)
        """
        tokens = []
        prev_word: Optional[str] = None
        is_sentence_start = True

        # Einfache Tokenisierung
        pattern = r'\b(\w+)\b'
        for match in re.finditer(pattern, text):
            word = match.group(1)
            position = match.start()

            tokens.append((word, position, prev_word, is_sentence_start))

            # Update für nächste Iteration
            prev_word = word

            # Prüfe Satzende nach diesem Wort
            end_pos = match.end()
            if end_pos < len(text):
                following = text[end_pos:end_pos + 2]
                is_sentence_start = bool(re.match(r'[.!?]\s', following))
            else:
                is_sentence_start = False

        return tokens

    def _should_be_capitalized(
        self,
        word: str,
        prev_word: Optional[str],
        is_sentence_start: bool,
    ) -> Tuple[bool, str]:
        """
        Prüfe ob ein Wort großgeschrieben sein sollte.

        Returns:
            (should_be_capitalized, reason)
        """
        word_lower = word.lower()

        # Satzanfang
        if is_sentence_start:
            return True, "Satzanfang"

        # Nach Artikel -> Substantiv
        if prev_word and prev_word.lower() in self.ARTICLES:
            return True, f"Nach Artikel '{prev_word}'"

        # Nach Präposition+Artikel-Kombination
        if prev_word and prev_word.lower() in self.PREPOSITION_ARTICLE_COMBOS:
            return True, f"Nach '{prev_word}'"

        # Substantiv-Suffix
        for suffix in self.NOUN_SUFFIXES:
            if word_lower.endswith(suffix) and len(word) > len(suffix) + 2:
                return True, f"Substantiv-Suffix '-{suffix}'"

        # Formelle Anrede (nur in Briefen, schwer zu erkennen)
        # Hier konservativ: nicht als Fehler markieren

        return False, ""

    def fix_capitalization(self, text: str) -> str:
        """
        Korrigiere Großschreibung im Text.

        Args:
            text: Der zu korrigierende Text

        Returns:
            Korrigierter Text
        """
        _, issues = self.validate(text)

        if not issues:
            return text

        result = text

        # Von hinten nach vorne ersetzen um Positionsverschiebung zu vermeiden
        for issue in sorted(issues, key=lambda x: x.position, reverse=True):
            word = issue.word
            pos = issue.position

            if issue.expected_capitalized and not word[0].isupper():
                corrected = word[0].upper() + word[1:]
                result = result[:pos] + corrected + result[pos + len(word):]

        return result


# =============================================================================
# Convenience Functions (NEU)
# =============================================================================


def get_german_validator() -> GermanValidator:
    """Hole GermanValidator-Instanz."""
    return GermanValidator()


def get_umlaut_handler(strict_mode: bool = True) -> EnhancedUmlautHandler:
    """Hole EnhancedUmlautHandler-Instanz."""
    return EnhancedUmlautHandler(strict_mode=strict_mode)


def get_capitalization_validator() -> GermanCapitalizationValidator:
    """Hole GermanCapitalizationValidator-Instanz."""
    return GermanCapitalizationValidator()


def validate_german_text(text: str) -> Dict:
    """
    Vollständige Validierung eines deutschen Texts.

    Kombiniert alle Validatoren.

    Returns:
        Dictionary mit allen Validierungsergebnissen
    """
    validator = GermanValidator()
    umlaut_handler = EnhancedUmlautHandler(strict_mode=False)
    cap_validator = GermanCapitalizationValidator()

    # Umlaut-Validierung
    umlaut_result = validator.validate_umlauts(text)

    # Umlaut-Wiederherstellung
    corrected_text, umlaut_corrections = umlaut_handler.restore_umlauts(text)

    # Großschreibungs-Validierung
    cap_accuracy, cap_issues = cap_validator.validate(text)

    # Daten/Währung extrahieren
    dates = validator.validate_date_format(text)
    currencies = validator.validate_currency_format(text)

    return {
        "original_text": text,
        "corrected_text": corrected_text,
        "umlaut_validation": umlaut_result,
        "umlaut_corrections": [
            {
                "original": c.original,
                "corrected": c.corrected,
                "position": c.position,
                "confidence": c.confidence,
            }
            for c in umlaut_corrections
        ],
        "capitalization": {
            "accuracy": round(cap_accuracy, 4),
            "issues_count": len(cap_issues),
            "issues": [
                {"word": i.word, "position": i.position, "reason": i.reason}
                for i in cap_issues
            ],
        },
        "extracted_dates": dates,
        "extracted_currencies": currencies,
        "overall_confidence": round(
            (umlaut_result["confidence"] + cap_accuracy) / 2, 2
        ),
    }
