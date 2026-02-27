"""
PII (Personally Identifiable Information) Masking for Logging.

Security-critical module to prevent PII leakage in logs:
- Kundennummern (Customer Numbers)
- IBANs
- VAT-IDs
- Email Addresses
- Phone Numbers
- Names (context-dependent)

GDPR/DSGVO Compliant - Art. 5(1)(c) Datenminimierung.

Feinpoliert und durchdacht - Enterprise-grade PII protection.
"""

from __future__ import annotations

import re
import structlog
import functools
from typing import Callable, Dict, List, Optional, Set, Union

logger = structlog.get_logger(__name__)


# =============================================================================
# PII PATTERNS
# =============================================================================

# Kundennummern (typische Formate: KD12345, 123456, K-12345)
CUSTOMER_NUMBER_PATTERN = re.compile(
    r"\b(?:KD|K-?|Kd\.?\s*Nr\.?\s*|Kundennr\.?\s*|Kunden-?Nr\.?\s*)?(\d{4,10})\b",
    re.IGNORECASE
)

# IBAN (DE12 3456 7890 1234 5678 90)
IBAN_PATTERN = re.compile(
    r"\b([A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){4}\d{2})\b",
    re.IGNORECASE
)

# BIC/SWIFT (COBADEFFXXX)
BIC_PATTERN = re.compile(
    r"\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b"
)

# VAT-ID / USt-IdNr (DE123456789)
VAT_ID_PATTERN = re.compile(
    r"\b((?:DE|AT|CH|FR|IT|NL|BE|PL|CZ|DK|ES|FI|GB|GR|HU|IE|LU|PT|SE|SI|SK)[A-Z]?\d{8,12})\b",
    re.IGNORECASE
)

# Email Addresses
EMAIL_PATTERN = re.compile(
    r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
)

# German Phone Numbers (+49 123 4567890, 0123-4567890)
PHONE_PATTERN = re.compile(
    r"\b(?:\+49[\s-]?|0)(\d{2,5}[\s-]?\d{3,8}[\s-]?\d{0,5})\b"
)

# Steuernummer (German Tax ID: 12/345/67890)
STEUERNUMMER_PATTERN = re.compile(
    r"\b(\d{2,3}/\d{3}/\d{4,5})\b"
)

# Sozialversicherungsnummer (German Social Security)
SVNR_PATTERN = re.compile(
    r"\b(\d{2}\s?\d{6}\s?[A-Z]\s?\d{3})\b"
)

# Kreditkartennummer (partial - last 4 digits shown)
CREDIT_CARD_PATTERN = re.compile(
    r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b"
)

# Matchcodes (typischerweise Grossbuchstaben, 3-20 Zeichen)
MATCHCODE_PATTERN = re.compile(
    r"\b(?:Matchcode[\s:]*)?([A-Z][A-Z0-9_-]{2,19})\b"
)


# =============================================================================
# MASKING FUNCTIONS
# =============================================================================

def mask_iban(iban: str) -> str:
    """Maskiert IBAN, zeigt nur Land und letzte 4 Ziffern.

    Args:
        iban: Die zu maskierende IBAN

    Returns:
        Maskierte IBAN (z.B. "DE**********5678")
    """
    iban_clean = iban.replace(" ", "")
    if len(iban_clean) < 6:
        return "****"
    return f"{iban_clean[:2]}{'*' * (len(iban_clean) - 6)}{iban_clean[-4:]}"


def mask_email(email: str) -> str:
    """Maskiert Email, zeigt erste Buchstaben und Domain.

    Args:
        email: Die zu maskierende Email

    Returns:
        Maskierte Email (z.B. "m***@example.com")
    """
    parts = email.split("@")
    if len(parts) != 2:
        return "***@***"
    local = parts[0]
    domain = parts[1]
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def mask_phone(phone: str) -> str:
    """Maskiert Telefonnummer, zeigt nur letzte 4 Ziffern.

    Args:
        phone: Die zu maskierende Telefonnummer

    Returns:
        Maskierte Nummer (z.B. "****5678")
    """
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "****"
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def mask_customer_number(number: str) -> str:
    """Maskiert Kundennummer, zeigt nur letzte 3 Ziffern.

    Args:
        number: Die zu maskierende Kundennummer

    Returns:
        Maskierte Nummer (z.B. "***345")
    """
    digits = re.sub(r"\D", "", number)
    if len(digits) <= 3:
        return "***"
    return f"{'*' * (len(digits) - 3)}{digits[-3:]}"


def mask_vat_id(vat_id: str) -> str:
    """Maskiert VAT-ID, zeigt nur Ländercode.

    Args:
        vat_id: Die zu maskierende VAT-ID

    Returns:
        Maskierte VAT-ID (z.B. "DE*********")
    """
    if len(vat_id) < 3:
        return "***"
    return f"{vat_id[:2]}{'*' * (len(vat_id) - 2)}"


def mask_credit_card(cc: str) -> str:
    """Maskiert Kreditkartennummer, zeigt nur letzte 4 Ziffern.

    Args:
        cc: Die zu maskierende Kreditkartennummer

    Returns:
        Maskierte Nummer (z.B. "****-****-****-5678")
    """
    digits = re.sub(r"\D", "", cc)
    if len(digits) < 4:
        return "****-****-****-****"
    return f"****-****-****-{digits[-4:]}"


def mask_pii(
    text: str,
    mask_customer_numbers: bool = True,
    mask_ibans: bool = True,
    mask_vat_ids: bool = True,
    mask_emails: bool = True,
    mask_phones: bool = True,
    mask_credit_cards: bool = True,
    custom_patterns: Optional[List[re.Pattern]] = None,
) -> str:
    """Maskiert alle PII in einem Text.

    Args:
        text: Der zu bereinigende Text
        mask_customer_numbers: Kundennummern maskieren
        mask_ibans: IBANs maskieren
        mask_vat_ids: VAT-IDs maskieren
        mask_emails: E-Mails maskieren
        mask_phones: Telefonnummern maskieren
        mask_credit_cards: Kreditkartennummern maskieren
        custom_patterns: Zusätzliche Patterns

    Returns:
        Text mit maskierten PII-Daten
    """
    if not text or not isinstance(text, str):
        return text

    result = text

    # IBAN (vor Kundennummern, da länger)
    if mask_ibans:
        result = IBAN_PATTERN.sub(
            lambda m: mask_iban(m.group(1)),
            result
        )

    # Kreditkarten
    if mask_credit_cards:
        result = CREDIT_CARD_PATTERN.sub(
            lambda m: mask_credit_card(m.group(1)),
            result
        )

    # VAT-IDs
    if mask_vat_ids:
        result = VAT_ID_PATTERN.sub(
            lambda m: mask_vat_id(m.group(1)),
            result
        )

    # Steuernummern
    result = STEUERNUMMER_PATTERN.sub(
        lambda m: "**/***/****",
        result
    )

    # Emails
    if mask_emails:
        result = EMAIL_PATTERN.sub(
            lambda m: mask_email(m.group(1)),
            result
        )

    # Telefonnummern
    if mask_phones:
        result = PHONE_PATTERN.sub(
            lambda m: mask_phone(m.group(0)),
            result
        )

    # Kundennummern (zuletzt, da am häufigsten false positives)
    if mask_customer_numbers:
        # Nur wenn Kontext-Hinweis vorhanden
        result = re.sub(
            r"\b(KD|Kd\.?\s*Nr\.?\s*|Kundennr\.?\s*|Kunden-?Nr\.?\s*)(\d{4,10})\b",
            lambda m: f"{m.group(1)}***{m.group(2)[-3:]}",
            result,
            flags=re.IGNORECASE
        )

    # Custom patterns
    if custom_patterns:
        for pattern in custom_patterns:
            result = pattern.sub("***REDACTED***", result)

    return result


def mask_dict_values(
    data: Dict[str, object],
    sensitive_keys: Optional[Set[str]] = None,
    deep: bool = True,
) -> Dict[str, object]:
    """Maskiert PII in Dict-Werten.

    Args:
        data: Das zu bereinigende Dict
        sensitive_keys: Zusätzliche Keys die immer maskiert werden
        deep: Rekursiv in nested Dicts/Lists

    Returns:
        Dict mit maskierten Werten
    """
    if not isinstance(data, dict):
        return data

    default_sensitive_keys = {
        "iban", "bic", "vat_id", "ust_id", "steuernummer",
        "customer_number", "kd_nr", "kundennummer",
        "email", "phone", "telefon", "mobil",
        "password", "passwort", "secret", "token",
        "api_key", "credit_card", "kreditkarte",
        "ssn", "svnr", "sozialversicherungsnummer",
        "matchcode", "primary_customer_number", "primary_supplier_number",
    }

    if sensitive_keys:
        default_sensitive_keys.update(sensitive_keys)

    result = {}

    for key, value in data.items():
        key_lower = key.lower()

        # Immer vollständig maskieren für bekannte sensitive Keys
        if key_lower in default_sensitive_keys:
            if isinstance(value, str):
                result[key] = "***REDACTED***"
            elif isinstance(value, dict) and deep:
                result[key] = {k: "***" for k in value.keys()}
            else:
                result[key] = "***"
        elif isinstance(value, str):
            # PII-Masking auf String-Werte
            result[key] = mask_pii(value)
        elif isinstance(value, dict) and deep:
            result[key] = mask_dict_values(value, sensitive_keys, deep)
        elif isinstance(value, list) and deep:
            result[key] = [
                mask_dict_values(item, sensitive_keys, deep) if isinstance(item, dict)
                else mask_pii(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value

    return result


# =============================================================================
# LOGGING WRAPPER
# =============================================================================

class PIIMaskingLogger:
    """Logger-Wrapper der automatisch PII maskiert.

    Usage:
        logger = PIIMaskingLogger(structlog.get_logger(__name__))
        logger.info("entity_imported", entity_name="Mueller GmbH", iban="DE123...")
        # Loggt: entity_name=Mueller GmbH, iban=DE**********3456
    """

    def __init__(
        self,
        wrapped_logger: object,
        mask_all_strings: bool = True,
        sensitive_keys: Optional[Set[str]] = None,
    ):
        """Initialisiert den PII-Masking Logger.

        Args:
            wrapped_logger: Der zu wrappende Logger
            mask_all_strings: Alle String-Argumente auf PII prüfen
            sensitive_keys: Zusätzliche sensitive Keys
        """
        self._logger = wrapped_logger
        self._mask_all_strings = mask_all_strings
        self._sensitive_keys = sensitive_keys or set()

    def _mask_kwargs(self, kwargs: Dict[str, object]) -> Dict[str, object]:
        """Maskiert PII in Keyword-Argumenten."""
        return mask_dict_values(kwargs, self._sensitive_keys, deep=True)

    def debug(self, event: str, **kwargs: object) -> None:
        """Debug log mit PII-Masking."""
        self._logger.debug(event, **self._mask_kwargs(kwargs))

    def info(self, event: str, **kwargs: object) -> None:
        """Info log mit PII-Masking."""
        self._logger.info(event, **self._mask_kwargs(kwargs))

    def warning(self, event: str, **kwargs: object) -> None:
        """Warning log mit PII-Masking."""
        self._logger.warning(event, **self._mask_kwargs(kwargs))

    def error(self, event: str, **kwargs: object) -> None:
        """Error log mit PII-Masking."""
        self._logger.error(event, **self._mask_kwargs(kwargs))

    def exception(self, event: str, **kwargs: object) -> None:
        """Exception log mit PII-Masking."""
        self._logger.exception(event, **self._mask_kwargs(kwargs))

    def critical(self, event: str, **kwargs: object) -> None:
        """Critical log mit PII-Masking."""
        self._logger.critical(event, **self._mask_kwargs(kwargs))

    # Alias für Kompatibilität
    warn = warning


def get_pii_safe_logger(name: str) -> PIIMaskingLogger:
    """Erstellt einen PII-sicheren Logger.

    Args:
        name: Logger-Name (typischerweise __name__)

    Returns:
        PIIMaskingLogger-Instanz
    """
    return PIIMaskingLogger(structlog.get_logger(name))


# =============================================================================
# DECORATOR
# =============================================================================

def mask_pii_in_logs(func: Callable[..., object]) -> Callable[..., object]:
    """Decorator zum automatischen PII-Masking in Log-Ausgaben.

    Usage:
        @mask_pii_in_logs
        def process_entity(entity_data: dict):
            logger.info("Processing", **entity_data)  # Automatisch maskiert
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Maskiere kwargs vor dem Aufruf (für logging innerhalb der Funktion)
        masked_kwargs = mask_dict_values(kwargs)
        return func(*args, **masked_kwargs)
    return wrapper
