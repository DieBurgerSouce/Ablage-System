# -*- coding: utf-8 -*-
"""
Industry Vocabulary Service für deutsche Fachsprache.

Phase 8: Deutsche Fachsprache

Dieses Modul bietet:
- Automatische Branchenerkennung aus Text
- Branchenspezifische OCR-Korrekturen
- Abkürzungsexpansion
- Compound-Word-Erkennung
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.logging_config import get_logger
from app.data.industry_vocabularies import (
    get_abbreviation,
    get_available_industries,
    get_term,
    load_vocabulary,
)

logger = get_logger(__name__)


class IndustryType(str, Enum):
    """Unterstützte Branchentypen."""

    BAUGEWERBE = "baugewerbe"
    HANDWERK = "handwerk"
    MEDIZIN = "medizin"
    RECHT = "recht"
    HANDEL = "handel"
    IT = "it"
    GENERAL = "general"


@dataclass
class CorrectionResult:
    """Ergebnis einer Textkorrektur."""

    original_text: str
    corrected_text: str
    corrections: List[Dict[str, Any]] = field(default_factory=list)
    detected_industry: Optional[IndustryType] = None
    industry_confidence: float = 0.0
    abbreviations_expanded: List[Dict[str, str]] = field(default_factory=list)
    compounds_found: List[str] = field(default_factory=list)

    @property
    def has_corrections(self) -> bool:
        """True wenn Korrekturen vorgenommen wurden."""
        return len(self.corrections) > 0

    @property
    def correction_count(self) -> int:
        """Anzahl der Korrekturen."""
        return len(self.corrections)


@dataclass
class IndustryDetectionResult:
    """Ergebnis der Branchenerkennung."""

    industry: IndustryType
    confidence: float
    keyword_matches: List[str]
    secondary_industries: List[Tuple[IndustryType, float]] = field(default_factory=list)


class IndustryVocabularyService:
    """
    Service für branchenspezifische Vokabularkorrekturen.

    Features:
    - Automatische Branchenerkennung aus OCR-Text
    - Korrektur von OCR-Fehlern basierend auf Branchenvokabular
    - Abkürzungsexpansion (optional)
    - Compound-Word-Erkennung und -Korrektur
    """

    # Minimum confidence für automatische Branchenzuordnung
    MIN_INDUSTRY_CONFIDENCE = 0.3

    # Gewichtung für Keyword-Matching
    KEYWORD_WEIGHT_PRIMARY = 1.0
    KEYWORD_WEIGHT_SECONDARY = 0.5

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._vocabulary_cache: Dict[str, Dict[str, Any]] = {}
        self._variant_lookup: Dict[str, Dict[str, Tuple[str, str]]] = {}
        self._initialize_variant_lookups()

    def _initialize_variant_lookups(self) -> None:
        """Baut Lookup-Tabellen für schnelle Variantensuche auf."""
        for industry in get_available_industries():
            try:
                vocab = load_vocabulary(industry)
                self._vocabulary_cache[industry] = vocab

                # Varianten-Lookup aufbauen: variant -> (canonical, term_key)
                self._variant_lookup[industry] = {}
                terms = vocab.get("terms", {})

                for term_key, term_data in terms.items():
                    canonical = term_data.get("canonical", "")
                    variants = term_data.get("variants", [])

                    for variant in variants:
                        # Case-insensitive lookup
                        variant_lower = variant.lower()
                        self._variant_lookup[industry][variant_lower] = (
                            canonical,
                            term_key,
                        )

                logger.debug(
                    f"Vokabular '{industry}' geladen: {len(terms)} Terme, "
                    f"{len(self._variant_lookup[industry])} Varianten"
                )

            except FileNotFoundError:
                logger.warning(f"Vokabular '{industry}' nicht gefunden")
            except Exception as e:
                logger.error(f"Fehler beim Laden von Vokabular '{industry}': {e}")

    def detect_industry(self, text: str) -> IndustryDetectionResult:
        """
        Erkennt die Branche aus dem Text.

        Args:
            text: Der zu analysierende Text

        Returns:
            IndustryDetectionResult mit erkannter Branche und Confidence
        """
        if not text:
            return IndustryDetectionResult(
                industry=IndustryType.GENERAL,
                confidence=0.0,
                keyword_matches=[],
            )

        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        industry_scores: Dict[str, Tuple[float, List[str]]] = {}

        for industry in get_available_industries():
            vocab = self._vocabulary_cache.get(industry, {})
            detection_keywords = vocab.get("detection_keywords", [])

            matches: List[str] = []
            score = 0.0

            # Primary keywords prüfen
            for keyword in detection_keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in words:
                    matches.append(keyword)
                    score += self.KEYWORD_WEIGHT_PRIMARY

            # Zusätzlich: Terme im Text suchen
            terms = vocab.get("terms", {})
            for term_key, term_data in terms.items():
                term_canonical = term_data.get("canonical", "").lower()
                if term_canonical in text_lower and term_canonical not in [
                    m.lower() for m in matches
                ]:
                    matches.append(term_canonical)
                    score += self.KEYWORD_WEIGHT_SECONDARY

            # Score normalisieren basierend auf Keyword-Anzahl
            if detection_keywords:
                max_possible = len(detection_keywords) * self.KEYWORD_WEIGHT_PRIMARY
                normalized_score = min(score / max_possible, 1.0)
            else:
                normalized_score = 0.0

            industry_scores[industry] = (normalized_score, matches)

        # Beste Branche bestimmen
        sorted_industries = sorted(
            industry_scores.items(), key=lambda x: x[1][0], reverse=True
        )

        if sorted_industries and sorted_industries[0][1][0] >= self.MIN_INDUSTRY_CONFIDENCE:
            best_industry = sorted_industries[0][0]
            best_score, best_matches = sorted_industries[0][1]

            # Sekundaere Branchen sammeln
            secondary = [
                (IndustryType(ind), score)
                for ind, (score, _) in sorted_industries[1:4]
                if score >= self.MIN_INDUSTRY_CONFIDENCE
            ]

            return IndustryDetectionResult(
                industry=IndustryType(best_industry),
                confidence=best_score,
                keyword_matches=best_matches,
                secondary_industries=secondary,
            )

        return IndustryDetectionResult(
            industry=IndustryType.GENERAL,
            confidence=0.0,
            keyword_matches=[],
        )

    def apply_industry_corrections(
        self,
        text: str,
        industry: Optional[IndustryType] = None,
        expand_abbreviations: bool = False,
        auto_detect_industry: bool = True,
    ) -> CorrectionResult:
        """
        Wendet branchenspezifische Korrekturen auf den Text an.

        Args:
            text: Der zu korrigierende Text
            industry: Die Branche (optional, wird sonst erkannt)
            expand_abbreviations: Abkürzungen expandieren
            auto_detect_industry: Branche automatisch erkennen wenn nicht angegeben

        Returns:
            CorrectionResult mit korrigiertem Text und Details
        """
        if not text:
            return CorrectionResult(
                original_text=text,
                corrected_text=text,
            )

        # Branche bestimmen
        detected_industry: Optional[IndustryType] = None
        industry_confidence = 0.0

        if industry and industry != IndustryType.GENERAL:
            detected_industry = industry
            industry_confidence = 1.0
        elif auto_detect_industry:
            detection = self.detect_industry(text)
            if detection.confidence >= self.MIN_INDUSTRY_CONFIDENCE:
                detected_industry = detection.industry
                industry_confidence = detection.confidence

        corrections: List[Dict[str, Any]] = []
        abbreviations_expanded: List[Dict[str, str]] = []
        compounds_found: List[str] = []
        corrected_text = text

        # Branchenspezifische Korrekturen anwenden
        if detected_industry and detected_industry != IndustryType.GENERAL:
            industry_key = detected_industry.value
            vocab = self._vocabulary_cache.get(industry_key, {})

            # 1. Varianten-Korrekturen
            corrected_text, variant_corrections = self._apply_variant_corrections(
                corrected_text, industry_key
            )
            corrections.extend(variant_corrections)

            # 2. Abkürzungen expandieren (optional)
            if expand_abbreviations:
                corrected_text, abbrev_expansions = self._expand_abbreviations(
                    corrected_text, industry_key
                )
                abbreviations_expanded.extend(abbrev_expansions)

            # 3. Compound-Words finden
            compounds = self._find_compounds(corrected_text, industry_key)
            compounds_found.extend(compounds)

        # Allgemeine Korrekturen anwenden (für alle Branchen)
        corrected_text, general_corrections = self._apply_general_corrections(
            corrected_text
        )
        corrections.extend(general_corrections)

        return CorrectionResult(
            original_text=text,
            corrected_text=corrected_text,
            corrections=corrections,
            detected_industry=detected_industry,
            industry_confidence=industry_confidence,
            abbreviations_expanded=abbreviations_expanded,
            compounds_found=compounds_found,
        )

    def _apply_variant_corrections(
        self, text: str, industry: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Wendet Varianten-Korrekturen an."""
        corrections: List[Dict[str, Any]] = []
        variant_lookup = self._variant_lookup.get(industry, {})

        if not variant_lookup:
            return text, corrections

        # Woerter im Text finden
        words = re.findall(r"\b[\wäöüÄÖÜß]+\b", text)

        for word in words:
            word_lower = word.lower()
            if word_lower in variant_lookup:
                canonical, term_key = variant_lookup[word_lower]

                # Nur korrigieren wenn nicht schon korrekt
                if word != canonical and word_lower != canonical.lower():
                    # Case-Preserving Replacement
                    if word[0].isupper():
                        replacement = canonical
                    else:
                        replacement = canonical.lower()

                    # Pattern für Wortgrenzen
                    pattern = r"\b" + re.escape(word) + r"\b"
                    new_text = re.sub(pattern, replacement, text, count=1)

                    if new_text != text:
                        corrections.append(
                            {
                                "type": "variant_correction",
                                "original": word,
                                "corrected": replacement,
                                "term_key": term_key,
                                "industry": industry,
                            }
                        )
                        text = new_text

        return text, corrections

    def _expand_abbreviations(
        self, text: str, industry: str
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Expandiert Abkürzungen."""
        expansions: List[Dict[str, str]] = []
        vocab = self._vocabulary_cache.get(industry, {})
        abbreviations = vocab.get("abbreviations", {})

        for abbrev, full_form in abbreviations.items():
            # Pattern: Abkürzung mit Wortgrenzen
            pattern = r"\b" + re.escape(abbrev) + r"\b"
            if re.search(pattern, text):
                # Nur expandieren, nicht ersetzen (zur Info)
                expansions.append(
                    {
                        "abbreviation": abbrev,
                        "expansion": full_form,
                    }
                )

        return text, expansions

    def _find_compounds(self, text: str, industry: str) -> List[str]:
        """Findet Compound-Words im Text."""
        compounds_found: List[str] = []
        vocab = self._vocabulary_cache.get(industry, {})
        compounds = vocab.get("compounds", [])

        text_lower = text.lower()

        for compound in compounds:
            word = compound.get("word", "")
            if word.lower() in text_lower:
                compounds_found.append(word)

        return compounds_found

    def _apply_general_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Wendet allgemeine Korrekturen an (branchenübergreifend).

        Korrigiert häufige OCR-Fehler wie:
        - l/1 Verwechslungen
        - O/0 Verwechslungen
        - Fehlende Umlaute
        """
        corrections: List[Dict[str, Any]] = []

        # Häufige OCR-Fehlermuster
        ocr_patterns = [
            # l/1 in bekannten Woertern
            (r"\bRechnug\b", "Rechnung", "missing_n"),
            (r"\bLleferung\b", "Lieferung", "l_i_confusion"),
            (r"\blleferung\b", "Lieferung", "l_i_confusion"),
            (r"\blnvoice\b", "Invoice", "l_i_confusion"),
            (r"\blnnung\b", "Innung", "l_i_confusion"),
            (r"\blnstallation\b", "Installation", "l_i_confusion"),
            # 0/O Verwechslungen
            (r"\bDiagn0se\b", "Diagnose", "o_0_confusion"),
            (r"\bPr0dukt\b", "Produkt", "o_0_confusion"),
            (r"\bStyrop0r\b", "Styropor", "o_0_confusion"),
            # Doppelbuchstaben-Fehler
            (r"\bVerrtrag\b", "Vertrag", "double_letter"),
            (r"\bRechnuung\b", "Rechnung", "double_letter"),
        ]

        for pattern, replacement, error_type in ocr_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                corrections.append(
                    {
                        "type": "general_ocr_correction",
                        "pattern": pattern,
                        "corrected": replacement,
                        "error_type": error_type,
                    }
                )

        return text, corrections

    def get_abbreviation_expansion(
        self, abbrev: str, industry: Optional[IndustryType] = None
    ) -> Optional[str]:
        """
        Holt die Expansion einer Abkürzung.

        Args:
            abbrev: Die Abkürzung
            industry: Optionale Branche für kontextspezifische Expansion

        Returns:
            Die volle Bezeichnung oder None
        """
        # Zuerst in spezifischer Branche suchen
        if industry and industry != IndustryType.GENERAL:
            result = get_abbreviation(industry.value, abbrev)
            if result:
                return result

        # Dann in allen Branchen suchen
        for ind in get_available_industries():
            result = get_abbreviation(ind, abbrev)
            if result:
                return result

        return None

    def get_term_info(
        self, term: str, industry: Optional[IndustryType] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Holt Informationen zu einem Term.

        Args:
            term: Der gesuchte Term
            industry: Optionale Branche

        Returns:
            Term-Informationen oder None
        """
        if industry and industry != IndustryType.GENERAL:
            result = get_term(industry.value, term)
            if result:
                return result

        # In allen Branchen suchen
        for ind in get_available_industries():
            result = get_term(ind, term)
            if result:
                result["industry"] = ind
                return result

        return None

    def get_industry_keywords(self, industry: IndustryType) -> List[str]:
        """
        Gibt die Detection-Keywords für eine Branche zurück.

        Args:
            industry: Die Branche

        Returns:
            Liste der Keywords
        """
        if industry == IndustryType.GENERAL:
            return []

        vocab = self._vocabulary_cache.get(industry.value, {})
        return vocab.get("detection_keywords", [])

    def get_statistics(self) -> Dict[str, Any]:
        """
        Gibt Statistiken über geladene Vokabulare zurück.

        Returns:
            Dictionary mit Statistiken
        """
        stats: Dict[str, Any] = {
            "industries_loaded": len(self._vocabulary_cache),
            "industries": {},
        }

        for industry, vocab in self._vocabulary_cache.items():
            terms = vocab.get("terms", {})
            compounds = vocab.get("compounds", [])
            abbreviations = vocab.get("abbreviations", {})

            stats["industries"][industry] = {
                "terms_count": len(terms),
                "variants_count": len(self._variant_lookup.get(industry, {})),
                "compounds_count": len(compounds),
                "abbreviations_count": len(abbreviations),
                "detection_keywords_count": len(vocab.get("detection_keywords", [])),
            }

        return stats


# Singleton-Instanz
_industry_vocabulary_service: Optional[IndustryVocabularyService] = None


def get_industry_vocabulary_service() -> IndustryVocabularyService:
    """
    Gibt die Singleton-Instanz des IndustryVocabularyService zurück.

    Returns:
        IndustryVocabularyService Instanz
    """
    global _industry_vocabulary_service
    if _industry_vocabulary_service is None:
        _industry_vocabulary_service = IndustryVocabularyService()
    return _industry_vocabulary_service
