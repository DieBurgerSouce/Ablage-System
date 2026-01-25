# -*- coding: utf-8 -*-
"""
Industry Vocabularies fuer deutsche Fachsprache.

Phase 8: Deutsche Fachsprache

Dieses Modul stellt branchenspezifische Vokabularien bereit fuer:
- Baugewerbe (VOB, HOAI, Baumaterialien)
- Handwerk (Berufsbezeichnungen, Werkzeuge)
- Medizin (Diagnosen, Behandlungen, Medikamente)
- Recht (Juristische Terminologie, Vertragsrecht)
- Handel (Kaufmaennische Begriffe, Logistik)
- IT (Technische Begriffe, Software)

Verwendung:
    from app.data.industry_vocabularies import load_vocabulary

    vocab = load_vocabulary("baugewerbe")
    terms = vocab["terms"]
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

VOCABULARY_DIR = Path(__file__).parent


@lru_cache(maxsize=10)
def load_vocabulary(industry: str) -> Dict[str, Any]:
    """
    Laedt ein Branchenvokabular.

    Args:
        industry: Name der Branche (z.B. "baugewerbe", "medizin")

    Returns:
        Dictionary mit terms, compounds, abbreviations

    Raises:
        FileNotFoundError: Wenn Vokabular nicht existiert
    """
    vocab_file = VOCABULARY_DIR / f"{industry}.json"
    if not vocab_file.exists():
        raise FileNotFoundError(f"Vokabular '{industry}' nicht gefunden: {vocab_file}")

    with open(vocab_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_available_industries() -> list[str]:
    """Gibt Liste aller verfuegbaren Branchen zurueck."""
    return [
        f.stem for f in VOCABULARY_DIR.glob("*.json")
        if f.stem != "__init__"
    ]


def get_term(industry: str, term: str) -> Optional[Dict[str, Any]]:
    """
    Holt einen einzelnen Term aus einem Vokabular.

    Args:
        industry: Name der Branche
        term: Der gesuchte Term

    Returns:
        Term-Dictionary oder None
    """
    try:
        vocab = load_vocabulary(industry)
        return vocab.get("terms", {}).get(term.lower())
    except FileNotFoundError:
        return None


def get_abbreviation(industry: str, abbrev: str) -> Optional[str]:
    """
    Holt die Expansion einer Abkuerzung.

    Args:
        industry: Name der Branche
        abbrev: Die Abkuerzung (z.B. "VOB")

    Returns:
        Volle Bezeichnung oder None
    """
    try:
        vocab = load_vocabulary(industry)
        return vocab.get("abbreviations", {}).get(abbrev.upper())
    except FileNotFoundError:
        return None


__all__ = [
    "load_vocabulary",
    "get_available_industries",
    "get_term",
    "get_abbreviation",
    "VOCABULARY_DIR",
]
