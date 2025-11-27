# -*- coding: utf-8 -*-
"""
German Language Correction Agent for Ablage-System.

Enterprise-grade German text correction for OCR output:
- Umlaut restoration (ae→ä, oe→ö, ue→ü, ss→ß)
- Context-aware correction using German vocabulary
- OCR error pattern detection and correction
- Compound word handling

KRITISCH: 100% Genauigkeit für deutsche Umlaute erforderlich.
Feinpoliert und durchdacht - Perfekte deutsche Textverarbeitung.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.agents.base import PostprocessingAgent
from app.german_validator import GermanValidator

logger = logging.getLogger(__name__)


class GermanCorrectionAgent(PostprocessingAgent):
    """
    German language correction agent for post-OCR text processing.

    Corrects common OCR errors in German text:
    - Restores umlauts from ASCII substitutions
    - Fixes Eszett (ß) vs. double-s errors
    - Applies context-aware corrections
    - Validates correction quality
    """

    # Common German words that should contain umlauts
    # Used for context-aware correction
    UMLAUT_WORDS: Dict[str, str] = {
        # ä words
        "aenderung": "Änderung",
        "aenderungen": "Änderungen",
        "aerger": "Ärger",
        "ahnlich": "ähnlich",
        "aerztlich": "ärztlich",
        "baecker": "Bäcker",
        "gebaeck": "Gebäck",
        "gepaeck": "Gepäck",
        "geraet": "Gerät",
        "geraete": "Geräte",
        "geschaeft": "Geschäft",
        "geschaefte": "Geschäfte",
        "gespraech": "Gespräch",
        "gewaehrleistung": "Gewährleistung",
        "haendler": "Händler",
        "jaehrlich": "jährlich",
        "kaeufer": "Käufer",
        "laenge": "Länge",
        "maerz": "März",
        "naechste": "nächste",
        "spaeter": "später",
        "staerke": "Stärke",
        "taetigkeit": "Tätigkeit",
        "taeglich": "täglich",
        "waehrung": "Währung",
        "waehrend": "während",
        "zaehlung": "Zählung",
        # ö words
        "behoerde": "Behörde",
        "behoerden": "Behörden",
        "erhoehung": "Erhöhung",
        "gehoert": "gehört",
        "groesse": "Größe",
        "hoehe": "Höhe",
        "koennen": "können",
        "moechten": "möchten",
        "moeglich": "möglich",
        "moeglichkeit": "Möglichkeit",
        "noetig": "nötig",
        "oeffnung": "Öffnung",
        "oeffentlich": "öffentlich",
        "oekonomisch": "ökonomisch",
        "schoen": "schön",
        "stoerung": "Störung",
        "unterstuetzung": "Unterstützung",
        "voellig": "völlig",
        "woertlich": "wörtlich",
        # ü words
        "ausfuehrung": "Ausführung",
        "begruendung": "Begründung",
        "durchfuehrung": "Durchführung",
        "einfuehrung": "Einführung",
        "erfuellung": "Erfüllung",
        "fuenf": "fünf",
        "fuer": "für",
        "gefuehl": "Gefühl",
        "gebuehr": "Gebühr",
        "gebuehren": "Gebühren",
        "gueltig": "gültig",
        "guenstig": "günstig",
        "kuendigung": "Kündigung",
        "kuenftig": "künftig",
        "muessen": "müssen",
        "natuerlich": "natürlich",
        "pruefung": "Prüfung",
        "stueck": "Stück",
        "ueber": "über",
        "ueberpruefung": "Überprüfung",
        "uebertragung": "Übertragung",
        "ueberweisung": "Überweisung",
        "unterstuetzung": "Unterstützung",
        "verfuegbar": "verfügbar",
        "verfuegung": "Verfügung",
        "wuerde": "würde",
        "wuenschen": "wünschen",
        "zurueck": "zurück",
        # ß words
        "ausserdem": "außerdem",
        "ausserhalb": "außerhalb",
        "draussen": "draußen",
        "fussball": "Fußball",
        "gemass": "gemäß",
        "grosse": "große",
        "grossen": "großen",
        "grosser": "großer",
        "heissen": "heißen",
        "heisst": "heißt",
        "massnahme": "Maßnahme",
        "massnahmen": "Maßnahmen",
        "schliessen": "schließen",
        "strasse": "Straße",
        "strassen": "Straßen",
        "weiss": "weiß",
    }

    # Patterns for OCR errors
    OCR_SUBSTITUTION_PATTERNS: List[Tuple[str, str, str]] = [
        # (pattern, replacement, context_hint)
        (r'\bae\b', 'ä', 'standalone'),
        (r'\boe\b', 'ö', 'standalone'),
        (r'\bue\b', 'ü', 'standalone'),
        (r'AE', 'Ä', 'uppercase'),
        (r'OE', 'Ö', 'uppercase'),
        (r'UE', 'Ü', 'uppercase'),
    ]

    def __init__(self):
        """Initialize the German Correction Agent."""
        super().__init__(name="german_correction_agent")
        self.validator = GermanValidator()
        self._build_correction_lookup()

    def _build_correction_lookup(self) -> None:
        """Build case-insensitive lookup for word corrections."""
        self._correction_lookup: Dict[str, str] = {}
        for wrong, correct in self.UMLAUT_WORDS.items():
            self._correction_lookup[wrong.lower()] = correct
            # Also add uppercase variants
            self._correction_lookup[wrong.upper()] = correct.upper()
            self._correction_lookup[wrong.capitalize()] = correct

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Correct German-specific OCR errors in text.

        Args:
            input_data: Dictionary containing:
                - text: OCR text to correct
                - classification: Optional document classification
                - options: Optional correction options

        Returns:
            Correction result containing:
                - text: Corrected text
                - original_text: Original input text
                - corrections_applied: Number of corrections made
                - correction_details: List of specific corrections
                - validation_score: Quality score after correction
                - umlauts_restored: Count of umlauts restored
        """
        self.validate_input(input_data, ["text"])

        text = input_data["text"]
        options = input_data.get("options", {})

        self.logger.info(
            "german_correction_started",
            text_length=len(text),
        )

        original_text = text
        correction_details: List[Dict[str, Any]] = []

        # Step 1: Validate current state
        initial_validation = self.validator.validate_umlauts(text)

        # Step 2: Apply word-based corrections
        text, word_corrections = self._apply_word_corrections(text)
        correction_details.extend(word_corrections)

        # Step 3: Apply pattern-based corrections (with context checking)
        if not options.get("skip_pattern_corrections", False):
            text, pattern_corrections = self._apply_pattern_corrections(text)
            correction_details.extend(pattern_corrections)

        # Step 4: Fix Eszett (ß) issues
        if not options.get("skip_eszett_corrections", False):
            text, eszett_corrections = self._apply_eszett_corrections(text)
            correction_details.extend(eszett_corrections)

        # Step 5: Validate after corrections
        final_validation = self.validator.validate_umlauts(text)

        # Count umlauts restored
        original_umlauts = set(initial_validation.get("umlauts_found", []))
        final_umlauts = set(final_validation.get("umlauts_found", []))
        umlauts_restored = len(final_umlauts - original_umlauts)

        result = {
            "text": text,
            "original_text": original_text,
            "corrections_applied": len(correction_details),
            "correction_details": correction_details[:50],  # Limit to 50 for response size
            "validation_score": final_validation.get("confidence", 0.0),
            "umlauts_restored": umlauts_restored,
            "initial_validation": {
                "umlauts_found": initial_validation.get("umlauts_found", []),
                "potential_errors": len(initial_validation.get("potential_errors", [])),
            },
            "final_validation": {
                "umlauts_found": final_validation.get("umlauts_found", []),
                "potential_errors": len(final_validation.get("potential_errors", [])),
            },
        }

        self.logger.info(
            "german_correction_completed",
            corrections=len(correction_details),
            umlauts_restored=umlauts_restored,
            validation_score=final_validation.get("confidence"),
        )

        return result

    def _apply_word_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply word-based umlaut corrections.

        Matches known German words with ASCII substitutions and
        replaces them with correct umlaut versions.
        """
        corrections = []
        result_text = text

        # Find and correct known words
        words = re.findall(r'\b\w+\b', text)

        for word in words:
            lookup_key = word.lower()
            if lookup_key in self._correction_lookup:
                correct_word = self._correction_lookup[lookup_key]

                # Preserve original case pattern
                if word.isupper():
                    correct_word = correct_word.upper()
                elif word[0].isupper() and word[1:].islower():
                    correct_word = correct_word.capitalize()

                if word != correct_word:
                    # Use word boundaries for safe replacement
                    pattern = r'\b' + re.escape(word) + r'\b'
                    result_text = re.sub(pattern, correct_word, result_text, count=1)

                    corrections.append({
                        "type": "word_correction",
                        "original": word,
                        "corrected": correct_word,
                        "confidence": 0.95,
                    })

        return result_text, corrections

    def _apply_pattern_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply pattern-based corrections with context awareness.

        More aggressive corrections for clear patterns.
        """
        corrections = []
        result_text = text

        # Context-aware ae/oe/ue replacement
        # Only replace when followed by certain letter combinations
        # that are common in German but not in the ASCII form

        context_patterns = [
            # ae → ä in common contexts
            (r'ae(?=rzt)', 'ä'),  # Ärztin, ärztlich
            (r'ae(?=nder)', 'ä'),  # ändern
            (r'ae(?=hnl)', 'ä'),  # ähnlich
            (r'ae(?=lter)', 'ä'),  # älter
            (r'(?<=G)ae(?=st)', 'ä'),  # Gäste
            (r'(?<=H)ae(?=nd)', 'ä'),  # Händler
            (r'(?<=J)ae(?=hr)', 'ä'),  # jährlich
            (r'(?<=K)ae(?=uf)', 'ä'),  # Käufer
            (r'(?<=M)ae(?=rz)', 'ä'),  # März
            (r'(?<=N)ae(?=ch)', 'ä'),  # nächste
            (r'(?<=Sp)ae(?=t)', 'ä'),  # später
            (r'(?<=T)ae(?=t)', 'ä'),  # Tätigkeit
            (r'(?<=W)ae(?=hr)', 'ä'),  # während

            # oe → ö in common contexts
            (r'(?<=B)oe(?=rs)', 'ö'),  # Börse
            (r'(?<=H)oe(?=he)', 'ö'),  # Höhe
            (r'(?<=K)oe(?=nn)', 'ö'),  # können
            (r'(?<=M)oe(?=g)', 'ö'),  # möglich
            (r'(?<=N)oe(?=t)', 'ö'),  # nötig
            (r'oe(?=ffn)', 'ö'),  # Öffnung, öffentlich
            (r'(?<=Sch)oe(?=n)', 'ö'),  # schön
            (r'(?<=V)oe(?=ll)', 'ö'),  # völlig
            (r'(?<=W)oe(?=rt)', 'ö'),  # Wörtlich

            # ue → ü in common contexts
            (r'(?<=F)ue(?=r\b)', 'ü'),  # für
            (r'(?<=F)ue(?=nf)', 'ü'),  # fünf
            (r'(?<=G)ue(?=lt)', 'ü'),  # gültig
            (r'(?<=G)ue(?=nst)', 'ü'),  # günstig
            (r'(?<=M)ue(?=ss)', 'ü'),  # müssen
            (r'(?<=Pr)ue(?=f)', 'ü'),  # Prüfung
            (r'(?<=St)ue(?=ck)', 'ü'),  # Stück
            (r'ue(?=ber)', 'ü'),  # über, Überweisung
            (r'(?<=W)ue(?=rd)', 'ü'),  # würde
            (r'(?<=W)ue(?=nsch)', 'ü'),  # wünschen
            (r'(?<=Z)ue(?=r)', 'ü'),  # zurück
        ]

        for pattern, replacement in context_patterns:
            matches = list(re.finditer(pattern, result_text, re.IGNORECASE))
            for match in reversed(matches):  # Reverse to preserve positions
                original = match.group()
                result_text = result_text[:match.start()] + replacement + result_text[match.end():]

                corrections.append({
                    "type": "pattern_correction",
                    "original": original,
                    "corrected": replacement,
                    "position": match.start(),
                    "confidence": 0.85,
                })

        return result_text, corrections

    def _apply_eszett_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply Eszett (ß) corrections.

        Carefully corrects ss → ß based on German spelling rules:
        - ß follows long vowels and diphthongs
        - ss follows short vowels
        """
        corrections = []
        result_text = text

        # Known words that should have ß
        eszett_words = {
            "strasse": "Straße",
            "strassen": "Straßen",
            "grosse": "große",
            "grossen": "großen",
            "grosser": "großer",
            "grosses": "großes",
            "heissen": "heißen",
            "heisst": "heißt",
            "weiss": "weiß",
            "weisse": "weiße",
            "draussen": "draußen",
            "ausserdem": "außerdem",
            "ausserhalb": "außerhalb",
            "gemass": "gemäß",
            "massnahme": "Maßnahme",
            "massnahmen": "Maßnahmen",
            "fussball": "Fußball",
            "schliessen": "schließen",
            "schliesst": "schließt",
            "giessen": "gießen",
            "spass": "Spaß",
            "gruss": "Gruß",
            "gruesse": "Grüße",
            "fuss": "Fuß",
            "fuesse": "Füße",
        }

        for wrong, correct in eszett_words.items():
            # Case-insensitive search
            pattern = r'\b' + re.escape(wrong) + r'\b'
            matches = list(re.finditer(pattern, result_text, re.IGNORECASE))

            for match in reversed(matches):
                original = match.group()

                # Preserve case
                if original.isupper():
                    replacement = correct.upper()
                elif original[0].isupper():
                    replacement = correct
                else:
                    replacement = correct.lower()

                result_text = result_text[:match.start()] + replacement + result_text[match.end():]

                corrections.append({
                    "type": "eszett_correction",
                    "original": original,
                    "corrected": replacement,
                    "confidence": 0.9,
                })

        return result_text, corrections

    def get_correction_stats(self) -> Dict[str, Any]:
        """Get statistics about correction capabilities."""
        return {
            "known_umlaut_words": len(self.UMLAUT_WORDS),
            "pattern_corrections": len(self.OCR_SUBSTITUTION_PATTERNS),
            "supported_corrections": [
                "ae → ä",
                "oe → ö",
                "ue → ü",
                "ss → ß",
                "AE → Ä",
                "OE → Ö",
                "UE → Ü",
            ],
        }
