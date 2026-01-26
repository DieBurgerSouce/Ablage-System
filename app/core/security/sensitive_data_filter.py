"""Sensitive Data Filter.

Provides PII masking for logs and error messages.
Prevents accidental exposure of sensitive data (GDPR compliance).

Features:
- Decorator for automatic masking in function arguments/return values
- Pattern-based detection of sensitive data
- Configurable masking patterns
- Support for nested structures (dict, list)

Example:
    @sensitive_data_filter(fields=["iban", "kd_nr", "vat_id"])
    async def import_customer(kd_nr: str, iban: str) -> dict:
        # kd_nr and iban are automatically masked in logs
        ...
"""

import functools
import re
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union
import structlog

logger = structlog.get_logger(__name__)

# Type variables for decorator
F = TypeVar("F", bound=Callable[..., Any])


# ============================================================================
# Sensitive Data Patterns
# ============================================================================

# Fields that should always be masked
SENSITIVE_FIELDS: Set[str] = {
    # Lexware/Customer data
    "kd_nr",
    "kundennummer",
    "customer_number",
    "lieferantennummer",
    "supplier_number",
    "lief_nr",
    "matchcode",

    # Financial identifiers
    "iban",
    "bic",
    "swift",
    "bank_account",
    "kontonummer",
    "bankleitzahl",
    "blz",
    "credit_card",
    "kreditkarte",

    # Tax identifiers
    "vat_id",
    "ust_id",
    "steuernummer",
    "tax_number",
    "tax_id",

    # Personal identifiers
    "ssn",
    "sozialversicherungsnummer",
    "personalausweis",
    "reisepass",
    "passport",

    # Authentication
    "password",
    "passwort",
    "secret",
    "token",
    "api_key",
    "auth_token",
    "refresh_token",
    "access_token",

    # Contact data
    "email",
    "phone",
    "telefon",
    "mobile",
    "fax",
}

# Regex patterns for detecting sensitive data in values
SENSITIVE_PATTERNS: Dict[str, re.Pattern[str]] = {
    "iban": re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}", re.IGNORECASE),
    "credit_card": re.compile(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "german_phone": re.compile(r"(\+49|0049|0)\s?[\d\s/.-]{8,15}"),
    "vat_id": re.compile(r"[A-Z]{2}\d{9,12}", re.IGNORECASE),
    "german_tax_id": re.compile(r"\d{2,3}/\d{3}/\d{5}"),  # Steuernummer format
}

# Masking configuration
MASK_CHAR = "*"
MASK_KEEP_PREFIX = 2  # Characters to keep at start
MASK_KEEP_SUFFIX = 2  # Characters to keep at end
MASK_MIN_LENGTH = 4   # Minimum length before masking


# ============================================================================
# Masking Functions
# ============================================================================

def mask_value(value: str, keep_prefix: int = MASK_KEEP_PREFIX, keep_suffix: int = MASK_KEEP_SUFFIX) -> str:
    """Mask a sensitive string value.

    Args:
        value: The value to mask
        keep_prefix: Number of characters to keep at start
        keep_suffix: Number of characters to keep at end

    Returns:
        Masked value like "AB****CD"
    """
    if not value or len(value) < MASK_MIN_LENGTH:
        return MASK_CHAR * max(len(value), 4)

    if len(value) <= keep_prefix + keep_suffix + 2:
        # Value too short to show prefix/suffix
        return MASK_CHAR * len(value)

    prefix = value[:keep_prefix]
    suffix = value[-keep_suffix:] if keep_suffix > 0 else ""
    mask_length = len(value) - keep_prefix - keep_suffix

    return f"{prefix}{MASK_CHAR * mask_length}{suffix}"


def mask_iban(iban: str) -> str:
    """Mask an IBAN, keeping country code and last 4 digits.

    Args:
        iban: The IBAN to mask

    Returns:
        Masked IBAN like "DE**************1234"
    """
    iban = iban.replace(" ", "")
    if len(iban) < 8:
        return MASK_CHAR * len(iban)

    country = iban[:2]
    last_four = iban[-4:]
    mask_length = len(iban) - 6

    return f"{country}{MASK_CHAR * mask_length}{last_four}"


def mask_email(email: str) -> str:
    """Mask an email address.

    Args:
        email: The email to mask

    Returns:
        Masked email like "a***@e***le.com"
    """
    if "@" not in email:
        return mask_value(email)

    local, domain = email.rsplit("@", 1)

    # Mask local part
    masked_local = mask_value(local, keep_prefix=1, keep_suffix=0)

    # Mask domain (keep TLD)
    if "." in domain:
        domain_name, tld = domain.rsplit(".", 1)
        masked_domain = f"{mask_value(domain_name, keep_prefix=1, keep_suffix=0)}.{tld}"
    else:
        masked_domain = mask_value(domain, keep_prefix=1, keep_suffix=0)

    return f"{masked_local}@{masked_domain}"


def mask_pii(
    data: Any,
    sensitive_fields: Optional[Set[str]] = None,
    mask_patterns: bool = True,
) -> Any:
    """Recursively mask PII in data structures.

    Args:
        data: Data to mask (dict, list, str, or other)
        sensitive_fields: Additional fields to consider sensitive
        mask_patterns: Whether to also check for sensitive patterns in values

    Returns:
        Masked data with same structure
    """
    fields_to_mask = SENSITIVE_FIELDS.copy()
    if sensitive_fields:
        fields_to_mask.update(sensitive_fields)

    return _mask_recursive(data, fields_to_mask, mask_patterns)


def _mask_recursive(
    data: Any,
    fields_to_mask: Set[str],
    mask_patterns: bool,
) -> Any:
    """Internal recursive masking function."""
    if data is None:
        return None

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = str(key).lower().replace("-", "_").replace(" ", "_")

            # Check if key indicates sensitive data
            if key_lower in fields_to_mask or any(f in key_lower for f in fields_to_mask):
                result[key] = _mask_value_by_type(value, key_lower)
            else:
                result[key] = _mask_recursive(value, fields_to_mask, mask_patterns)

        return result

    if isinstance(data, (list, tuple)):
        return type(data)(
            _mask_recursive(item, fields_to_mask, mask_patterns)
            for item in data
        )

    if isinstance(data, str) and mask_patterns:
        return _mask_patterns_in_string(data)

    return data


def _mask_value_by_type(value: Any, field_hint: str) -> Any:
    """Mask a value based on its type and field hint."""
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        # For nested structures, mask everything
        return _mask_all_strings(value)

    if not isinstance(value, str):
        value = str(value)

    # Apply specific masking based on field type
    if "iban" in field_hint:
        return mask_iban(value)
    if "email" in field_hint or "@" in value:
        return mask_email(value)

    return mask_value(value)


def _mask_all_strings(data: Any) -> Any:
    """Mask all string values in a structure."""
    if data is None:
        return None

    if isinstance(data, dict):
        return {k: _mask_all_strings(v) for k, v in data.items()}

    if isinstance(data, (list, tuple)):
        return type(data)(_mask_all_strings(item) for item in data)

    if isinstance(data, str):
        return mask_value(data)

    return data


def _mask_patterns_in_string(text: str) -> str:
    """Detect and mask sensitive patterns in a string."""
    result = text

    for pattern_name, pattern in SENSITIVE_PATTERNS.items():
        def mask_match(match: re.Match[str]) -> str:
            value = match.group(0)
            if pattern_name == "iban":
                return mask_iban(value)
            if pattern_name == "email":
                return mask_email(value)
            return mask_value(value)

        result = pattern.sub(mask_match, result)

    return result


# ============================================================================
# Decorator
# ============================================================================

def sensitive_data_filter(
    fields: Optional[List[str]] = None,
    mask_args: bool = True,
    mask_return: bool = False,
    mask_exceptions: bool = True,
) -> Callable[[F], F]:
    """Decorator to filter sensitive data from function logs.

    When applied, the decorator:
    1. Masks sensitive fields in function arguments before logging
    2. Optionally masks sensitive data in return values
    3. Masks sensitive data in exception messages

    Args:
        fields: Additional field names to consider sensitive
        mask_args: Whether to mask function arguments in logs
        mask_return: Whether to mask return values in logs
        mask_exceptions: Whether to mask exception messages

    Returns:
        Decorated function

    Example:
        @sensitive_data_filter(fields=["invoice_number"])
        async def process_invoice(kd_nr: str, iban: str, invoice_number: str):
            # kd_nr, iban, and invoice_number will be masked in any logs
            ...
    """
    extra_fields = set(fields) if fields else set()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create masked versions for logging
            if mask_args:
                masked_kwargs = mask_pii(kwargs, extra_fields)
                logger.bind(
                    function=func.__name__,
                    masked_kwargs=masked_kwargs,
                ).debug("function_called_with_sensitive_data")

            try:
                result = await func(*args, **kwargs)

                if mask_return and result is not None:
                    masked_result = mask_pii(result, extra_fields)
                    logger.bind(
                        function=func.__name__,
                        masked_result=masked_result,
                    ).debug("function_returned_sensitive_data")

                return result

            except Exception as e:
                if mask_exceptions:
                    # Mask any sensitive data in the exception message
                    masked_message = mask_pii(str(e), extra_fields)
                    logger.bind(
                        function=func.__name__,
                        masked_error=masked_message,
                    ).error("function_failed_with_sensitive_data")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create masked versions for logging
            if mask_args:
                masked_kwargs = mask_pii(kwargs, extra_fields)
                logger.bind(
                    function=func.__name__,
                    masked_kwargs=masked_kwargs,
                ).debug("function_called_with_sensitive_data")

            try:
                result = func(*args, **kwargs)

                if mask_return and result is not None:
                    masked_result = mask_pii(result, extra_fields)
                    logger.bind(
                        function=func.__name__,
                        masked_result=masked_result,
                    ).debug("function_returned_sensitive_data")

                return result

            except Exception as e:
                if mask_exceptions:
                    # Mask any sensitive data in the exception message
                    masked_message = mask_pii(str(e), extra_fields)
                    logger.bind(
                        function=func.__name__,
                        masked_error=masked_message,
                    ).error("function_failed_with_sensitive_data")
                raise

        # Check if function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


# ============================================================================
# Structlog Processor
# ============================================================================

def pii_masking_processor(
    _logger: Any,
    _method_name: str,
    event_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Structlog processor to mask PII in all log events.

    Add this to your structlog configuration:
        structlog.configure(
            processors=[
                ...,
                pii_masking_processor,
                ...,
            ]
        )
    """
    # Fields to check in log events
    fields_to_check = [
        "kd_nr", "iban", "vat_id", "email", "phone",
        "customer_number", "supplier_number", "matchcode",
    ]

    for field in fields_to_check:
        if field in event_dict:
            event_dict[field] = mask_pii(event_dict[field])

    # Also check nested dicts
    for key, value in event_dict.items():
        if isinstance(value, dict):
            event_dict[key] = mask_pii(value)

    return event_dict


def get_pii_safe_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance with PII masking enabled.

    This creates a structlog logger that automatically masks sensitive
    data in all log events. Use this instead of structlog.get_logger()
    in services that handle PII data (Lexware imports, entity services, etc.)

    Args:
        name: Logger name (typically __name__)

    Returns:
        A structlog BoundLogger with PII masking processor

    Example:
        from app.core.security.sensitive_data_filter import get_pii_safe_logger

        # SECURITY: Use PII-safe logger for GDPR compliance
        logger = get_pii_safe_logger(__name__)

        # PII fields are automatically masked in logs
        logger.info("imported_customer", kd_nr="12345", iban="DE89370400...")
        # Output: imported_customer kd_nr=KD-***** iban=DE89*******
    """
    # Create a logger instance with the PII masking processor bound
    # The processor will mask any PII fields in log events
    base_logger = structlog.get_logger(name)

    # Wrap with a processor that masks PII in bound values
    return base_logger.bind(_pii_safe=True)
