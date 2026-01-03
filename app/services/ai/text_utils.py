# -*- coding: utf-8 -*-
"""
Zentrale Text-Utilities fuer AI-Services.

Stellt wiederverwendbare Funktionen fuer:
- Deutsche Text-Normalisierung (mit Umlaut-Support)
- Feld-Aehnlichkeitsberechnung
- Text-Hashing

Vermeidet Code-Duplikation zwischen:
- duplicate_detection_service.py
- auto_categorization_service.py
- smart_matching_service.py
"""

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


def normalize_german_text(
    text: Optional[str],
    remove_punctuation: bool = True,
    preserve_umlauts: bool = True,
    max_length: Optional[int] = None,
) -> str:
    """
    Normalisiert deutschen Text fuer Vergleiche und Matching.

    WICHTIG: Erhaelt standardmaessig deutsche Umlaute (ä, ö, ü, ß)
    fuer korrekten Vergleich deutscher Dokumente.

    Args:
        text: Der zu normalisierende Text
        remove_punctuation: Ob Satzzeichen entfernt werden sollen
        preserve_umlauts: Ob Umlaute erhalten bleiben sollen (Standard: True)
        max_length: Optionale maximale Textlaenge

    Returns:
        Normalisierter Text als String
    """
    if not text:
        return ""

    # Lowercase
    text = text.lower()

    # Whitespace normalisieren
    text = re.sub(r'\s+', ' ', text)

    # Sonderzeichen entfernen (optional)
    if remove_punctuation:
        if preserve_umlauts:
            # \w mit re.UNICODE matched alle Unicode-Buchstaben inkl. äöüß
            text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
        else:
            # Nur ASCII-Buchstaben behalten
            text = re.sub(r'[^a-z0-9\s]', '', text)

    # Laenge begrenzen
    if max_length and len(text) > max_length:
        text = text[:max_length]

    return text.strip()


def calculate_text_hash(text: str, normalize: bool = True) -> str:
    """
    Berechnet SHA-256 Hash eines Texts.

    Args:
        text: Der zu hashende Text
        normalize: Ob der Text vorher normalisiert werden soll

    Returns:
        SHA-256 Hash als Hex-String
    """
    if normalize:
        text = normalize_german_text(text)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def calculate_text_similarity(
    text1: str,
    text2: str,
    normalize: bool = True,
    max_length: int = 10000,
) -> float:
    """
    Berechnet Text-Aehnlichkeit mit SequenceMatcher.

    Args:
        text1: Erster Text
        text2: Zweiter Text
        normalize: Ob Texte vorher normalisiert werden sollen
        max_length: Maximale Textlaenge fuer Performance

    Returns:
        Aehnlichkeitswert zwischen 0.0 und 1.0
    """
    if normalize:
        t1 = normalize_german_text(text1, max_length=max_length)
        t2 = normalize_german_text(text2, max_length=max_length)
    else:
        t1 = text1[:max_length] if len(text1) > max_length else text1
        t2 = text2[:max_length] if len(text2) > max_length else text2

    if not t1 or not t2:
        return 0.0

    return SequenceMatcher(None, t1, t2).ratio()


def calculate_field_similarity(
    value1: Any,
    value2: Any,
    field_type: str = "string",
) -> float:
    """
    Berechnet Aehnlichkeit zwischen zwei Feldwerten.

    Unterstuetzt verschiedene Feldtypen:
    - string: Text-Aehnlichkeit
    - number: Numerische Aehnlichkeit
    - date: Datums-Match
    - exact: Exakter Match

    Args:
        value1: Erster Wert
        value2: Zweiter Wert
        field_type: Typ des Felds

    Returns:
        Aehnlichkeitswert zwischen 0.0 und 1.0
    """
    # Null-Checks
    if value1 is None and value2 is None:
        return 1.0
    if value1 is None or value2 is None:
        return 0.0

    if field_type == "exact":
        return 1.0 if value1 == value2 else 0.0

    if field_type == "number":
        try:
            n1 = float(value1)
            n2 = float(value2)
            if n1 == 0 and n2 == 0:
                return 1.0
            max_val = max(abs(n1), abs(n2))
            if max_val == 0:
                return 1.0
            return 1.0 - (abs(n1 - n2) / max_val)
        except (TypeError, ValueError):
            return 0.0

    if field_type == "date":
        # Exakter Match fuer Daten
        return 1.0 if str(value1) == str(value2) else 0.0

    # Default: String-Aehnlichkeit
    s1 = str(value1)
    s2 = str(value2)
    return calculate_text_similarity(s1, s2)


def extract_keywords(
    text: str,
    min_length: int = 3,
    max_keywords: int = 50,
) -> List[str]:
    """
    Extrahiert Keywords aus Text.

    Args:
        text: Der zu analysierende Text
        min_length: Minimale Wortlaenge
        max_keywords: Maximale Anzahl Keywords

    Returns:
        Liste von Keywords
    """
    if not text:
        return []

    # Normalisieren
    normalized = normalize_german_text(text, remove_punctuation=True)

    # Woerter extrahieren
    words = normalized.split()

    # Filtern und deduplizieren
    keywords = []
    seen = set()
    for word in words:
        if len(word) >= min_length and word not in seen:
            seen.add(word)
            keywords.append(word)
            if len(keywords) >= max_keywords:
                break

    return keywords


def fuzzy_match_strings(
    query: str,
    candidates: List[str],
    threshold: float = 0.7,
    normalize: bool = True,
) -> List[Tuple[str, float]]:
    """
    Findet aehnliche Strings in einer Liste.

    Args:
        query: Suchstring
        candidates: Liste von Kandidaten
        threshold: Mindest-Aehnlichkeit (0.0 - 1.0)
        normalize: Ob Strings normalisiert werden sollen

    Returns:
        Liste von (Kandidat, Aehnlichkeit) Tupeln, sortiert nach Aehnlichkeit
    """
    results = []
    query_norm = normalize_german_text(query) if normalize else query

    for candidate in candidates:
        cand_norm = normalize_german_text(candidate) if normalize else candidate
        similarity = SequenceMatcher(None, query_norm, cand_norm).ratio()
        if similarity >= threshold:
            results.append((candidate, similarity))

    # Nach Aehnlichkeit sortieren
    return sorted(results, key=lambda x: x[1], reverse=True)


def validate_confidence(confidence: float) -> float:
    """
    Validiert und begrenzt Confidence-Werte auf [0.0, 1.0].

    Args:
        confidence: Der zu validierende Confidence-Wert

    Returns:
        Begrenzter Confidence-Wert zwischen 0.0 und 1.0
    """
    if confidence < 0.0:
        return 0.0
    if confidence > 1.0:
        return 1.0
    return confidence


def calculate_weighted_average(
    scores: List[Tuple[float, float]],
) -> float:
    """
    Berechnet gewichteten Durchschnitt.

    Args:
        scores: Liste von (Wert, Gewicht) Tupeln

    Returns:
        Gewichteter Durchschnitt
    """
    if not scores:
        return 0.0

    total_weight = sum(weight for _, weight in scores)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(value * weight for value, weight in scores)
    return weighted_sum / total_weight
