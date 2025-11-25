"""
German Text Validation Snippets
Umlaut checks, date/currency formats, business term validation
"""

import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from decimal import Decimal


# ============================================================================
# Pattern 1: Umlaut Detection and Validation
# ============================================================================

GERMAN_UMLAUTS = {
    'lowercase': ['ä', 'ö', 'ü', 'ß'],
    'uppercase': ['Ä', 'Ö', 'Ü'],
    'all': ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü']
}


def has_umlauts(text: str) -> bool:
    """Check if text contains German umlauts."""
    return any(char in text for char in GERMAN_UMLAUTS['all'])


def count_umlauts(text: str) -> Dict[str, int]:
    """Count occurrences of each umlaut."""
    counts = {umlaut: text.count(umlaut) for umlaut in GERMAN_UMLAUTS['all']}
    counts['total'] = sum(counts.values())
    return counts


def validate_umlaut_integrity(text: str) -> Dict[str, any]:
    """
    Validate that umlauts are correctly encoded (not replaced with ae, oe, ue).

    Returns dict with validation status and potential issues.
    """
    issues = []

    # Check for common umlaut replacements (OCR errors)
    replacements = {
        'ae': 'ä',
        'oe': 'ö',
        'ue': 'ü',
        'Ae': 'Ä',
        'Oe': 'Ö',
        'Ue': 'Ü',
        'ss': 'ß'
    }

    for replacement, correct in replacements.items():
        # Find potential incorrect replacements
        pattern = rf'\b\w*{replacement}\w*\b'
        matches = re.findall(pattern, text)
        if matches:
            # Heuristic: if word contains 'ae/oe/ue' and it's capitalized or all lowercase
            for match in matches:
                if replacement in match and correct not in match:
                    issues.append({
                        'type': 'potential_replacement',
                        'found': match,
                        'replacement': replacement,
                        'suggestion': match.replace(replacement, correct)
                    })

    return {
        'valid': len(issues) == 0,
        'has_umlauts': has_umlauts(text),
        'umlaut_counts': count_umlauts(text),
        'issues': issues
    }


# ============================================================================
# Pattern 2: Unicode Normalization
# ============================================================================

def normalize_german_text(text: str) -> str:
    """
    Normalize German text to NFC form (composed characters).

    Important for consistent umlaut representation.
    """
    # NFC normalization (composed form: ä instead of a + ̈)
    text = unicodedata.normalize('NFC', text)

    # Fraktur to modern German character mapping
    fraktur_map = {
        '\u1E9E': 'ß',     # Capital ß
        '\uA758': 'Q',     # Fraktur Q
        '\uA759': 'q',     # Fraktur q
        '\u017F': 's',     # Long s (ſ)
    }

    for old_char, new_char in fraktur_map.items():
        text = text.replace(old_char, new_char)

    return text


# ============================================================================
# Pattern 3: German Date Validation (DD.MM.YYYY)
# ============================================================================

def validate_german_date(date_str: str) -> Tuple[bool, Optional[datetime]]:
    """
    Validate and parse German date format (DD.MM.YYYY).

    Returns: (is_valid, parsed_datetime or None)
    """
    # Pattern: DD.MM.YYYY
    pattern = r'^\d{1,2}\.\d{1,2}\.\d{4}$'

    if not re.match(pattern, date_str):
        return False, None

    try:
        parsed = datetime.strptime(date_str, '%d.%m.%Y')
        return True, parsed
    except ValueError:
        return False, None


def extract_german_dates(text: str) -> List[Dict[str, any]]:
    """
    Extract all German-format dates from text.

    Returns list of dicts with date string, parsed datetime, and position.
    """
    # Pattern: DD.MM.YYYY
    pattern = r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b'
    matches = re.finditer(pattern, text)

    dates = []
    for match in matches:
        date_str = match.group(0)
        is_valid, parsed = validate_german_date(date_str)

        dates.append({
            'raw': date_str,
            'valid': is_valid,
            'parsed': parsed,
            'position': match.span()
        })

    return dates


GERMAN_MONTHS = {
    'Januar': 1, 'Februar': 2, 'März': 3, 'April': 4,
    'Mai': 5, 'Juni': 6, 'Juli': 7, 'August': 8,
    'September': 9, 'Oktober': 10, 'November': 11, 'Dezember': 12
}


def parse_german_date_with_month_name(date_str: str) -> Optional[datetime]:
    """
    Parse dates like "31. Dezember 2024" or "1. Mai 2024".
    """
    # Pattern: DD. Month YYYY
    pattern = r'(\d{1,2})\.\s*(' + '|'.join(GERMAN_MONTHS.keys()) + r')\s*(\d{4})'
    match = re.search(pattern, date_str)

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)
    year = int(match.group(3))
    month = GERMAN_MONTHS[month_name]

    try:
        return datetime(year, month, day)
    except ValueError:
        return None


# ============================================================================
# Pattern 4: German Currency Validation (1.234,56 €)
# ============================================================================

def validate_german_currency(amount_str: str) -> Tuple[bool, Optional[Decimal]]:
    """
    Validate and parse German currency format.

    Formats:
    - 1.234,56 €
    - 1234,56€
    - € 1.234,56

    Returns: (is_valid, parsed_decimal or None)
    """
    # Remove whitespace and currency symbol
    cleaned = amount_str.strip().replace('€', '').replace(' ', '')

    # Pattern: 1.234,56 or 1234,56
    pattern = r'^\d{1,3}(\.\d{3})*,\d{2}$'

    if not re.match(pattern, cleaned):
        return False, None

    try:
        # Convert to decimal: remove thousand separators, replace comma with dot
        numeric = cleaned.replace('.', '').replace(',', '.')
        decimal_value = Decimal(numeric)
        return True, decimal_value
    except Exception:
        return False, None


def parse_german_amount(amount_str: str) -> Optional[float]:
    """Parse German amount to float (1.234,56 → 1234.56)."""
    is_valid, decimal_value = validate_german_currency(amount_str)
    return float(decimal_value) if is_valid else None


def format_german_currency(amount: float) -> str:
    """Format float as German currency (1234.56 → 1.234,56 €)."""
    # Format with thousand separators and 2 decimals
    formatted = f"{amount:,.2f}"

    # Replace default formatting (1,234.56) with German (1.234,56)
    german_formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')

    return f"{german_formatted} €"


# ============================================================================
# Pattern 5: Business Term Extraction
# ============================================================================

LEGAL_FORMS = [
    'GmbH', 'AG', 'KG', 'GbR', 'UG', 'e.V.', 'PartG', 'OHG',
    'GmbH & Co. KG', 'SE', 'KGaA'
]

BUSINESS_TERMS = {
    'document_types': [
        'Rechnung', 'Gutschrift', 'Lieferschein', 'Vertrag',
        'Angebot', 'Bestellung', 'Auftragsbestätigung'
    ],
    'financial': [
        'Umsatzsteuer', 'Mehrwertsteuer', 'Netto', 'Brutto',
        'Skonto', 'Zahlungsziel', 'Fälligkeit'
    ],
    'authorization': [
        'i.A.', 'i.V.', 'ppa.', 'gez.'
    ]
}


def extract_company_names(text: str) -> List[str]:
    """
    Extract company names with legal forms.

    Examples: "Müller GmbH", "Bäcker & Partner AG"
    """
    # Pattern: Capitalized word(s) + legal form
    legal_forms_pattern = '|'.join(re.escape(form) for form in LEGAL_FORMS)
    pattern = rf'([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜa-zäöüß\-&]+)*\s+(?:{legal_forms_pattern}))'

    matches = re.findall(pattern, text)
    return list(set(matches))  # Remove duplicates


def extract_business_terms(text: str) -> Dict[str, List[str]]:
    """
    Extract all business terms from text.

    Returns dict categorized by type.
    """
    found_terms = {}

    for category, terms in BUSINESS_TERMS.items():
        found = []
        for term in terms:
            if term in text:
                found.append(term)
        if found:
            found_terms[category] = found

    return found_terms


# ============================================================================
# Pattern 6: Tax ID Validation
# ============================================================================

def validate_ust_idnr(ust_id: str) -> bool:
    """
    Validate German VAT ID (Umsatzsteuer-Identifikationsnummer).

    Format: DE + 9 digits (e.g., DE123456789)
    """
    pattern = r'^DE\d{9}$'
    return bool(re.match(pattern, ust_id))


def validate_steuernummer(steuer_nr: str) -> bool:
    """
    Validate German tax number (Steuernummer).

    Format: XX/XXX/XXXXX (regional variations exist)
    """
    # Common pattern: 2-3 digits / 3 digits / 5 digits
    pattern = r'^\d{2,3}/\d{3}/\d{5}$'
    return bool(re.match(pattern, steuer_nr))


def extract_tax_ids(text: str) -> Dict[str, Optional[str]]:
    """
    Extract tax IDs from text.

    Returns dict with 'ust_idnr' and 'steuernummer'.
    """
    result = {'ust_idnr': None, 'steuernummer': None}

    # USt-IdNr
    ust_match = re.search(r'DE\d{9}', text)
    if ust_match:
        result['ust_idnr'] = ust_match.group(0)

    # Steuernummer
    steuer_match = re.search(r'\d{2,3}/\d{3}/\d{5}', text)
    if steuer_match:
        result['steuernummer'] = steuer_match.group(0)

    return result


# ============================================================================
# Pattern 7: Fuzzy Business Term Matching
# ============================================================================

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_match_business_term(text: str, threshold: float = 0.85) -> List[Dict[str, any]]:
    """
    Fuzzy match business terms (useful for OCR errors).

    Args:
        text: Input text
        threshold: Similarity threshold (0-1)

    Returns list of matches with similarity scores.
    """
    all_terms = []
    for terms in BUSINESS_TERMS.values():
        all_terms.extend(terms)
    all_terms.extend(LEGAL_FORMS)

    words = text.split()
    matches = []

    for word in words:
        for term in all_terms:
            distance = levenshtein_distance(word.lower(), term.lower())
            max_len = max(len(word), len(term))
            similarity = 1 - (distance / max_len)

            if similarity >= threshold:
                matches.append({
                    'word': word,
                    'matched_term': term,
                    'similarity': round(similarity, 3)
                })

    return matches


# ============================================================================
# Usage Examples
# ============================================================================

if __name__ == "__main__":
    # Example 1: Umlaut validation
    text = "Müller GmbH, Äußere Straße 123"
    print(validate_umlaut_integrity(text))

    # Example 2: Date extraction
    invoice_text = "Rechnungsdatum: 31.12.2024, Fälligkeit: 15.01.2025"
    dates = extract_german_dates(invoice_text)
    print(dates)

    # Example 3: Currency parsing
    amount = "1.234,56 €"
    is_valid, decimal_value = validate_german_currency(amount)
    print(f"Valid: {is_valid}, Value: {decimal_value}")

    # Example 4: Company extraction
    contract = "Vertrag zwischen Müller GmbH und Schulze AG"
    companies = extract_company_names(contract)
    print(companies)  # ['Müller GmbH', 'Schulze AG']

    # Example 5: Tax ID extraction
    invoice = "USt-IdNr: DE123456789, Steuernummer: 19/815/08155"
    tax_ids = extract_tax_ids(invoice)
    print(tax_ids)
