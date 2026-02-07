# -*- coding: utf-8 -*-
"""
JSONB Input Validation Utilities.

Prevents logic injection and DoS via deeply nested or oversized JSON payloads.
Addresses CWE-89 (SQL Injection via JSONB) and CWE-400 (Resource Exhaustion).
"""

import json
from typing import Dict, List, Optional, Set, Union

# JSON-compatible data type for JSONB payloads
JsonValue = Union[str, int, float, bool, None, Dict[str, object], List[object]]

MAX_JSONB_SIZE_BYTES = 50 * 1024  # 50KB
MAX_NESTING_DEPTH = 5
MAX_ARRAY_LENGTH = 100


def validate_jsonb_size(data: JsonValue, max_bytes: int = MAX_JSONB_SIZE_BYTES) -> None:
    """Validate that JSONB payload does not exceed size limit."""
    serialized = json.dumps(data, default=str)
    if len(serialized.encode("utf-8")) > max_bytes:
        raise ValueError(
            f"JSON-Payload zu gross (max {max_bytes // 1024}KB erlaubt)"
        )


def validate_jsonb_depth(
    data: JsonValue,
    max_depth: int = MAX_NESTING_DEPTH,
    _current_depth: int = 0,
) -> None:
    """Validate that JSONB payload does not exceed nesting depth."""
    if _current_depth > max_depth:
        raise ValueError(
            f"JSON-Verschachtelung zu tief (max {max_depth} Ebenen erlaubt)"
        )

    if isinstance(data, dict):
        for value in data.values():
            validate_jsonb_depth(value, max_depth, _current_depth + 1)
    elif isinstance(data, list):
        if len(data) > MAX_ARRAY_LENGTH:
            raise ValueError(
                f"JSON-Array zu lang (max {MAX_ARRAY_LENGTH} Elemente erlaubt)"
            )
        for item in data:
            validate_jsonb_depth(item, max_depth, _current_depth + 1)


def validate_jsonb_keys(
    data: JsonValue,
    allowed_keys: Optional[Set[str]] = None,
) -> None:
    """Validate that JSONB dict keys don't contain injection patterns.

    Note: allowed_keys is only enforced at the top-level dict.
    Nested dicts are still checked for injection patterns but may contain
    any key names. This is intentional for rule/workflow conditions where
    top-level keys are known but nested structures vary.
    """
    if isinstance(data, dict):
        for key in data.keys():
            if not isinstance(key, str):
                raise ValueError("JSON-Keys muessen Strings sein")
            # Reject SQL injection patterns in keys
            if any(c in key for c in ("'", '"', ";", "--", "/*", "*/", "\x00")):
                raise ValueError(
                    f"Ungueltiger JSON-Key: Sonderzeichen nicht erlaubt"
                )
            if allowed_keys and key not in allowed_keys:
                raise ValueError(
                    f"Unbekannter JSON-Key: '{key}'"
                )
        for value in data.values():
            # Injection patterns checked recursively; allowed_keys only at top level
            validate_jsonb_keys(value)
    elif isinstance(data, list):
        for item in data:
            validate_jsonb_keys(item)


def validate_jsonb_payload(
    data: JsonValue,
    max_bytes: int = MAX_JSONB_SIZE_BYTES,
    max_depth: int = MAX_NESTING_DEPTH,
    allowed_keys: Optional[Set[str]] = None,
) -> None:
    """Full JSONB payload validation."""
    validate_jsonb_size(data, max_bytes)
    validate_jsonb_depth(data, max_depth)
    validate_jsonb_keys(data, allowed_keys)
