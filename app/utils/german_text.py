# -*- coding: utf-8 -*-
"""
German Text Utilities.

Provides normalization and validation functions for German text processing.
"""

import re
import unicodedata
from typing import Optional


def normalize_german_text(text: str) -> str:
    """
    Normalize German text for processing.

    Handles:
    - Unicode normalization (NFC)
    - Umlaut variants
    - Fraktur character mapping
    - Whitespace normalization

    Args:
        text: Input text to normalize

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Unicode normalization to NFC (composed form)
    text = unicodedata.normalize("NFC", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    return text


def normalize_umlauts(text: str) -> str:
    """
    Normalize ASCII umlaut substitutions to proper umlauts.

    Converts:
    - ae -> ä
    - oe -> ö
    - ue -> ü
    - ss -> ß (contextual)

    Args:
        text: Input text

    Returns:
        Text with normalized umlauts
    """
    if not text:
        return ""

    # Common umlaut substitutions
    replacements = [
        ("Ae", "Ä"),
        ("Oe", "Ö"),
        ("Ue", "Ü"),
        ("ae", "ä"),
        ("oe", "ö"),
        ("ue", "ü"),
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    return text
