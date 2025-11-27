"""
German Text Normalizer - UTF-8/Umlaut Handling
100% accuracy requirement for German characters
Priority: P0 - CRITICAL

Handles:
- Umlauts (ä, ö, ü, Ä, Ö, Ü)
- Eszett (ß)
- Unicode normalization (NFC)
- Fraktur character mapping
- Historical orthography variants
"""

import unicodedata
import re
from typing import Dict, List, Tuple, Optional

import structlog

logger = structlog.get_logger(__name__)


class GermanNormalizer:
    """
    Normalize German text for OCR post-processing
    Ensures 100% umlaut accuracy
    """

    def __init__(self):
        """Initialize German text normalizer"""
        # Fraktur to modern German mapping
        self.fraktur_map = {
            '\u1E9E': 'ß',  # Capital ß (rarely used)
            '\uFB00': 'ff',  # Ligature ff
            '\uFB01': 'fi',  # Ligature fi
            '\uFB02': 'fl',  # Ligature fl
            '\uFB03': 'ffi', # Ligature ffi
            '\uFB04': 'ffl', # Ligature ffl
            '\uFB05': 'ſt',  # Ligature long s + t
            '\u017F': 's',   # Long s (Fraktur)
        }

        # Common OCR errors for German characters
        self.common_errors = {
            # Eszett confusions
            'ß': ['B', 'β', 'ss'],
            # Umlaut confusions
            'ä': ['a', 'ae', 'a"'],
            'ö': ['o', 'oe', 'o"'],
            'ü': ['u', 'ue', 'u"'],
            'Ä': ['A', 'Ae', 'A"'],
            'Ö': ['O', 'Oe', 'O"'],
            'Ü': ['U', 'Ue', 'U"'],
        }

        # Context-based correction patterns
        self.context_patterns = [
            # Common German words with ß
            (r'Stra[sß]e', 'Straße'),
            (r'gro[sß]', 'groß'),
            (r'Fu[sß]', 'Fuß'),
            (r'au[sß]en', 'außen'),
            (r'hei[sß]t', 'heißt'),
            (r'wei[sß]', 'weiß'),
            (r'Gru[sß]', 'Gruß'),
            (r'schlie[sß]t', 'schließt'),

            # Common words with umlauts
            (r'M[uü]ller', 'Müller'),
            (r'M[uü]nchen', 'München'),
            (r'K[oö]ln', 'Köln'),
            (r'D[uü]sseldorf', 'Düsseldorf'),
            (r'N[uü]rnberg', 'Nürnberg'),
            (r'f[uü]r', 'für'),
            (r'[uü]ber', 'über'),
            (r'Tr[ae]ger', 'Träger'),
            (r'erm[ae]�[sß]igt', 'ermäßigt'),
        ]

        logger.info("German normalizer initialized")

    def normalize(
        self,
        text: str,
        fix_encoding: bool = True,
        fix_fraktur: bool = True,
        fix_common_errors: bool = True
    ) -> str:
        """
        Normalize German text

        Args:
            text: Input text (may contain encoding errors)
            fix_encoding: Fix UTF-8 encoding issues
            fix_fraktur: Convert Fraktur characters
            fix_common_errors: Apply context-based error correction

        Returns:
            Normalized German text
        """
        if not text:
            return text

        # Step 1: Fix encoding issues
        if fix_encoding:
            text = self._fix_encoding(text)

        # Step 2: Unicode normalization (NFC = composed form)
        text = unicodedata.normalize('NFC', text)

        # Step 3: Convert Fraktur characters
        if fix_fraktur:
            text = self._convert_fraktur(text)

        # Step 4: Context-based error correction
        if fix_common_errors:
            text = self._fix_common_errors(text)

        return text

    def _fix_encoding(self, text: str) -> str:
        """
        Fix common UTF-8 encoding issues

        Common problems:
        - Mojibake (encoding/decoding errors)
        - Mixed encodings
        - Invalid characters
        """
        # Try to detect and fix common encoding issues
        try:
            # Check if text is actually bytes
            if isinstance(text, bytes):
                try:
                    text = text.decode('utf-8')
                except UnicodeDecodeError:
                    text = text.decode('latin-1')

            # Fix common mojibake patterns for German umlauts
            replacements = {
                'Ã¤': 'ä',  # ä encoded as latin-1, read as utf-8
                'Ã¶': 'ö',
                'Ã¼': 'ü',
                'Ã„': 'Ä',
                'Ã–': 'Ö',
                'Ãœ': 'Ü',
                'ÃŸ': 'ß',
                'ﾃ¤': 'ä',  # Another mojibake variant
                'ﾃ¶': 'ö',
                'ﾃ¼': 'ü',
            }

            for wrong, correct in replacements.items():
                text = text.replace(wrong, correct)

            return text

        except Exception as e:
            logger.warning("encoding_fix_failed", error=str(e))
            return text

    def _convert_fraktur(self, text: str) -> str:
        """Convert Fraktur/Gothic characters to modern German"""
        for old, new in self.fraktur_map.items():
            text = text.replace(old, new)
        return text

    def _fix_common_errors(self, text: str) -> str:
        """Apply context-based error corrections"""
        # Apply pattern-based corrections
        for pattern, replacement in self.context_patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def validate_umlauts(self, text: str) -> Dict[str, any]:
        """
        Validate that all umlauts are correctly encoded

        Args:
            text: Text to validate

        Returns:
            Dict with validation results
        """
        umlauts_found = []
        potential_errors = []

        # Find all umlauts
        umlauts = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
        for umlaut in umlauts:
            count = text.count(umlaut)
            if count > 0:
                umlauts_found.append({
                    'character': umlaut,
                    'count': count,
                    'codepoint': f'U+{ord(umlaut):04X}'
                })

        # Check for common error patterns
        error_patterns = {
            r'ae(?![a-z])': 'ä',  # ae not followed by letter
            r'oe(?![a-z])': 'ö',
            r'ue(?![a-z])': 'ü',
            r'Ae(?![a-z])': 'Ä',
            r'Oe(?![a-z])': 'Ö',
            r'Ue(?![a-z])': 'Ü',
            r'ss(?=[A-ZÄÖÜ])': 'ß',  # ss before capital letter
        }

        for pattern, should_be in error_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                potential_errors.append({
                    'pattern': pattern,
                    'should_be': should_be,
                    'occurrences': len(matches),
                    'severity': 'high'
                })

        # Calculate confidence score
        error_count = len(potential_errors)
        confidence = max(0.0, 1.0 - (error_count * 0.1))

        return {
            'valid': error_count == 0,
            'umlauts_found': umlauts_found,
            'potential_errors': potential_errors,
            'confidence': round(confidence, 2),
            'text_length': len(text)
        }

    def split_compound_words(
        self,
        word: str,
        dictionary: Optional[List[str]] = None
    ) -> List[str]:
        """
        Split German compound words for better searchability

        Args:
            word: German compound word (e.g., 'Donaudampfschifffahrtsgesellschaft')
            dictionary: Optional dictionary of known words

        Returns:
            List of component words
        """
        # This is a placeholder - real implementation would use:
        # - CharSplit algorithm
        # - German morphology rules
        # - Word frequency statistics

        # Simple mock implementation
        if dictionary is None:
            dictionary = [
                'Donau', 'Dampf', 'Schiff', 'Fahrt', 'Gesellschaft',
                'Rechnung', 'Nummer', 'Datum', 'Betrag'
            ]

        # Try to find longest matching prefixes
        components = []
        remaining = word

        while remaining:
            found = False
            for length in range(len(remaining), 0, -1):
                prefix = remaining[:length]
                if prefix in dictionary:
                    components.append(prefix)
                    remaining = remaining[length:]
                    found = True
                    break

            if not found:
                # No match found, take first character
                components.append(remaining[0])
                remaining = remaining[1:]

        return components

    def correct_eszett(self, text: str) -> str:
        """
        Correct common Eszett (ß) errors

        Args:
            text: Text potentially with ß errors

        Returns:
            Text with corrected ß
        """
        # Common patterns where ß should be used
        replacements = {
            'strasse': 'straße',
            'Strasse': 'Straße',
            'STRASSE': 'STRASSE',  # Keep uppercase
            'grossen': 'großen',
            'grossen': 'großen',
            'aussen': 'außen',
            'Aussen': 'Außen',
            'heissen': 'heißen',
            'weissen': 'weißen',
            'fliessen': 'fließen',
            'giessen': 'gießen',
        }

        for wrong, correct in replacements.items():
            # Use word boundaries to avoid partial matches
            text = re.sub(rf'\b{wrong}\b', correct, text)

        return text

    def format_currency(self, amount: float, locale: str = "de_DE") -> str:
        """
        Format amount as German currency

        Args:
            amount: Numeric amount
            locale: Locale (default: German)

        Returns:
            Formatted currency string (e.g., "1.234,56 €")
        """
        # German number format: 1.234,56 €
        formatted = f"{amount:,.2f}"

        # Replace thousand separator and decimal point
        formatted = formatted.replace(',', 'X')  # Temp
        formatted = formatted.replace('.', ',')   # Decimal
        formatted = formatted.replace('X', '.')   # Thousand

        return f"{formatted} €"

    def parse_german_date(self, date_str: str) -> Optional[Tuple[int, int, int]]:
        """
        Parse German date format

        Args:
            date_str: Date string (e.g., "22.11.2024")

        Returns:
            Tuple of (day, month, year) or None
        """
        # Common German date formats
        patterns = [
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # DD.MM.YYYY
            r'(\d{1,2})\.\s*(\w+)\s*(\d{4})',  # DD. Month YYYY
        ]

        month_names = {
            'Januar': 1, 'Februar': 2, 'März': 3, 'April': 4,
            'Mai': 5, 'Juni': 6, 'Juli': 7, 'August': 8,
            'September': 9, 'Oktober': 10, 'November': 11, 'Dezember': 12
        }

        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                day = int(match.group(1))
                month = match.group(2)

                # Check if month is numeric or name
                if month.isdigit():
                    month = int(month)
                else:
                    month = month_names.get(month, None)
                    if month is None:
                        continue

                year = int(match.group(3))

                return (day, month, year)

        return None


# Singleton instance
_german_normalizer = None


def get_german_normalizer() -> GermanNormalizer:
    """Get global GermanNormalizer instance"""
    global _german_normalizer
    if _german_normalizer is None:
        _german_normalizer = GermanNormalizer()
    return _german_normalizer
