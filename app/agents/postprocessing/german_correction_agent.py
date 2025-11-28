# -*- coding: utf-8 -*-
"""
German Language Correction Agent for Ablage-System.

Enterprise-grade German text correction for OCR output:
- Umlaut restoration (ae→ä, oe→ö, ue→ü, ss→ß)
- Context-aware correction using German vocabulary
- OCR error pattern detection and correction
- Compound word handling
- LanguageTool integration for grammar/context
- Levenshtein fuzzy matching for OCR errors
- Domain-specific corrections (accounting, legal, medical)

KRITISCH: 100% Genauigkeit für deutsche Umlaute erforderlich.
Feinpoliert und durchdacht - Perfekte deutsche Textverarbeitung.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from app.agents.base import PostprocessingAgent
from app.german_validator import GermanValidator

logger = structlog.get_logger(__name__)

# Try to import LanguageTool (optional dependency)
try:
    from language_tool_python import LanguageTool
    LANGUAGETOOL_AVAILABLE = True
except ImportError:
    LANGUAGETOOL_AVAILABLE = False
    LanguageTool = None  # type: ignore
    logger.info("language_tool_not_available", message="LanguageTool-Korrekturen deaktiviert")


# Domain-specific corrections for accounting, legal, and medical texts
DOMAIN_CORRECTIONS: Dict[str, Dict[str, str]] = {
    "accounting": {
        # Buchhaltung / Rechnungswesen
        "bilanzierung": "Bilanzierung",
        "buchfuehrung": "Buchführung",
        "gewinnermittlung": "Gewinnermittlung",
        "jahresabschluss": "Jahresabschluss",
        "kostenstelle": "Kostenstelle",
        "mehrwertsteuer": "Mehrwertsteuer",
        "rueckstellung": "Rückstellung",
        "rueckstellungen": "Rückstellungen",
        "steuererklaerung": "Steuererklärung",
        "umsatzsteuer": "Umsatzsteuer",
        "vorsteuer": "Vorsteuer",
        "zahlungsziel": "Zahlungsziel",
        "abschreibung": "Abschreibung",
        "gutschrift": "Gutschrift",
        "kontoauszug": "Kontoauszug",
        "kontoauszuege": "Kontoauszüge",
        "ueberweisungsbeleg": "Überweisungsbeleg",
    },
    "legal": {
        # Rechtswesen / Verträge
        "buergerliches": "bürgerliches",
        "eigentuemer": "Eigentümer",
        "eigentumsuebertragung": "Eigentumsübertragung",
        "gebuehrenordnung": "Gebührenordnung",
        "geschaeftsfuehrer": "Geschäftsführer",
        "gesellschaftsvertrag": "Gesellschaftsvertrag",
        "grundstueck": "Grundstück",
        "grundstuecke": "Grundstücke",
        "haftungsausschluss": "Haftungsausschluss",
        "kuendigungsfrist": "Kündigungsfrist",
        "rechtsfaehigkeit": "Rechtsfähigkeit",
        "schadensersatz": "Schadensersatz",
        "verguetung": "Vergütung",
        "verjaehrung": "Verjährung",
        "vertragspartner": "Vertragspartner",
        "vollmacht": "Vollmacht",
        "zustaendigkeit": "Zuständigkeit",
    },
    "medical": {
        # Medizin / Gesundheitswesen
        "aerztekammer": "Ärztekammer",
        "arztbericht": "Arztbericht",
        "behandlungsvertrag": "Behandlungsvertrag",
        "befundbericht": "Befundbericht",
        "ernaehrung": "Ernährung",
        "gesundheitspruefung": "Gesundheitsprüfung",
        "krankenkasse": "Krankenkasse",
        "krankenversicherung": "Krankenversicherung",
        "patientenakte": "Patientenakte",
        "ueberweisung": "Überweisung",
        "untersuchungsbericht": "Untersuchungsbericht",
        "verordnung": "Verordnung",
        "zahnaerztlich": "zahnärztlich",
    },
}

# Common German vocabulary for fuzzy matching (most frequent words with umlauts)
GERMAN_VOCABULARY: Set[str] = {
    # High-frequency umlaut words
    "über", "für", "würde", "können", "möchten", "müssen",
    "während", "später", "nächste", "größe", "höhe",
    "Änderung", "Prüfung", "Gebühr", "Verfügung", "Kündigung",
    "Geschäft", "Behörde", "Straße", "Maßnahme", "Größe",
    "Höhe", "Länge", "Stärke", "Wärme", "Kälte",
    "Tätigkeit", "Möglichkeit", "Notwendigkeit", "Schwierigkeit",
    "Führung", "Überprüfung", "Übertragung", "Überweisung",
    "öffentlich", "möglich", "nötig", "völlig", "gültig",
    "jährlich", "täglich", "wöchentlich", "monatlich",
    "Bäcker", "Händler", "Käufer", "Verkäufer",
    "schön", "groß", "größer", "größte",
    "fünf", "zwölf", "fünfzig", "sechzig", "siebzig",
}


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

    # Minimum similarity threshold for fuzzy matching (Levenshtein)
    FUZZY_THRESHOLD: float = 0.85

    # Common German compound word prefixes and suffixes
    COMPOUND_PREFIXES: Set[str] = {
        "ab", "an", "auf", "aus", "be", "bei", "durch", "ein", "ent",
        "er", "ge", "hin", "miss", "mit", "nach", "über", "um", "un",
        "unter", "ver", "vor", "weg", "zer", "zu", "zurück",
    }

    COMPOUND_SUFFIXES: Set[str] = {
        "ung", "heit", "keit", "schaft", "nis", "tum", "ling",
        "chen", "lein", "bar", "sam", "lich", "ig", "isch",
        "haft", "los", "voll", "reich", "arm", "frei",
    }

    def __init__(self, enable_languagetool: bool = True):
        """
        Initialize the German Correction Agent.

        Args:
            enable_languagetool: Enable LanguageTool for grammar checking
        """
        super().__init__(name="german_correction_agent")
        self.validator = GermanValidator()
        self._build_correction_lookup()
        self._build_vocabulary_lookup()

        # Initialize LanguageTool if available and enabled
        self._language_tool: Optional[LanguageTool] = None
        if enable_languagetool and LANGUAGETOOL_AVAILABLE:
            self._init_language_tool()

    def _build_correction_lookup(self) -> None:
        """Build case-insensitive lookup for word corrections."""
        self._correction_lookup: Dict[str, str] = {}
        for wrong, correct in self.UMLAUT_WORDS.items():
            self._correction_lookup[wrong.lower()] = correct
            # Also add uppercase variants
            self._correction_lookup[wrong.upper()] = correct.upper()
            self._correction_lookup[wrong.capitalize()] = correct

    def _build_vocabulary_lookup(self) -> None:
        """Build vocabulary lookup for fuzzy matching."""
        self._vocabulary: Set[str] = set()

        # Add from global vocabulary
        self._vocabulary.update(GERMAN_VOCABULARY)

        # Add correct forms from UMLAUT_WORDS
        self._vocabulary.update(self.UMLAUT_WORDS.values())

        # Add from domain corrections
        for domain_words in DOMAIN_CORRECTIONS.values():
            self._vocabulary.update(domain_words.values())

        # Build lowercase lookup for faster matching
        self._vocabulary_lower: Dict[str, str] = {
            word.lower(): word for word in self._vocabulary
        }

        self.logger.debug(
            "vocabulary_built",
            total_words=len(self._vocabulary),
        )

    def _init_language_tool(self) -> None:
        """Initialize LanguageTool for German grammar checking."""
        try:
            self._language_tool = LanguageTool("de-DE")
            self.logger.info(
                "language_tool_initialized",
                language="de-DE",
            )
        except Exception as e:
            self.logger.warning(
                "language_tool_init_failed",
                error=str(e),
            )
            self._language_tool = None

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Correct German-specific OCR errors in text.

        Full NLP pipeline with:
        1. Word-based umlaut corrections
        2. Context-aware pattern corrections
        3. Eszett (ß) corrections
        4. Domain-specific corrections (accounting, legal, medical)
        5. Fuzzy matching for OCR errors (Levenshtein)
        6. Compound word validation
        7. LanguageTool grammar/spelling check
        8. Quality scoring

        Args:
            input_data: Dictionary containing:
                - text: OCR text to correct
                - classification: Optional document classification
                - domain: Optional domain hint (accounting, legal, medical)
                - options: Optional correction options

        Returns:
            Correction result containing:
                - text: Corrected text
                - original_text: Original input text
                - corrections_applied: Number of corrections made
                - correction_details: List of specific corrections
                - validation_score: Quality score after correction
                - quality_metrics: Detailed quality metrics
                - umlauts_restored: Count of umlauts restored
        """
        self.validate_input(input_data, ["text"])

        text = input_data["text"]
        options = input_data.get("options", {})
        domain = input_data.get("domain")
        classification = input_data.get("classification", {})

        # Auto-detect domain from classification if not provided
        if not domain and classification:
            domain = self._detect_domain_from_classification(classification)

        self.logger.info(
            "german_correction_started",
            text_length=len(text),
            domain=domain,
            languagetool_enabled=self._language_tool is not None,
        )

        original_text = text
        correction_details: List[Dict[str, Any]] = []

        # Step 1: Validate current state
        initial_validation = self.validator.validate_umlauts(text)

        # Step 2: Apply word-based corrections (known umlaut words)
        text, word_corrections = self._apply_word_corrections(text)
        correction_details.extend(word_corrections)

        # Step 3: Apply pattern-based corrections (context-aware)
        if not options.get("skip_pattern_corrections", False):
            text, pattern_corrections = self._apply_pattern_corrections(text)
            correction_details.extend(pattern_corrections)

        # Step 4: Fix Eszett (ß) issues
        if not options.get("skip_eszett_corrections", False):
            text, eszett_corrections = self._apply_eszett_corrections(text)
            correction_details.extend(eszett_corrections)

        # Step 5: Apply domain-specific corrections
        if domain and not options.get("skip_domain_corrections", False):
            text, domain_corrections = self._apply_domain_corrections(text, domain)
            correction_details.extend(domain_corrections)

        # Step 6: Apply fuzzy matching for remaining OCR errors
        if not options.get("skip_fuzzy_matching", False):
            text, fuzzy_corrections = self._apply_fuzzy_corrections(text)
            correction_details.extend(fuzzy_corrections)

        # Step 7: Validate and fix compound words
        if not options.get("skip_compound_validation", False):
            text, compound_corrections = self._validate_compound_words(text)
            correction_details.extend(compound_corrections)

        # Step 8: Apply LanguageTool corrections (grammar/spelling)
        if self._language_tool and not options.get("skip_languagetool", False):
            text, lt_corrections = self._apply_language_tool_corrections(text)
            correction_details.extend(lt_corrections)

        # Step 9: Validate after all corrections
        final_validation = self.validator.validate_umlauts(text)

        # Count umlauts restored
        original_umlauts = set(initial_validation.get("umlauts_found", []))
        final_umlauts = set(final_validation.get("umlauts_found", []))
        umlauts_restored = len(final_umlauts - original_umlauts)

        # Calculate quality metrics
        quality_metrics = self._calculate_quality_metrics(
            original_text=original_text,
            corrected_text=text,
            correction_details=correction_details,
            final_validation=final_validation,
        )

        result = {
            "text": text,
            "original_text": original_text,
            "corrections_applied": len(correction_details),
            "correction_details": correction_details[:100],  # Limit for response size
            "validation_score": quality_metrics["overall_score"],
            "quality_metrics": quality_metrics,
            "umlauts_restored": umlauts_restored,
            "domain_detected": domain,
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
            quality_score=quality_metrics["overall_score"],
            domain=domain,
        )

        return result

    def _detect_domain_from_classification(
        self, classification: Dict[str, Any]
    ) -> Optional[str]:
        """Detect domain from document classification."""
        doc_type = classification.get("document_type", "").lower()

        # Map document types to domains
        domain_mapping = {
            "rechnung": "accounting",
            "invoice": "accounting",
            "kontoauszug": "accounting",
            "bilanz": "accounting",
            "vertrag": "legal",
            "contract": "legal",
            "vollmacht": "legal",
            "testament": "legal",
            "arztbrief": "medical",
            "befund": "medical",
            "rezept": "medical",
            "überweisung": "medical",
        }

        for keyword, domain in domain_mapping.items():
            if keyword in doc_type:
                return domain

        return None

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

    def _apply_domain_corrections(
        self, text: str, domain: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply domain-specific corrections.

        Args:
            text: Text to correct
            domain: Domain name (accounting, legal, medical)

        Returns:
            Tuple of (corrected_text, corrections)
        """
        corrections = []
        result_text = text

        if domain not in DOMAIN_CORRECTIONS:
            return result_text, corrections

        domain_words = DOMAIN_CORRECTIONS[domain]

        for wrong, correct in domain_words.items():
            # Case-insensitive search
            pattern = r'\b' + re.escape(wrong) + r'\b'
            matches = list(re.finditer(pattern, result_text, re.IGNORECASE))

            for match in reversed(matches):
                original = match.group()

                # Preserve case pattern
                if original.isupper():
                    replacement = correct.upper()
                elif original[0].isupper():
                    replacement = correct
                else:
                    replacement = correct.lower()

                result_text = (
                    result_text[:match.start()] + replacement + result_text[match.end():]
                )

                corrections.append({
                    "type": "domain_correction",
                    "domain": domain,
                    "original": original,
                    "corrected": replacement,
                    "confidence": 0.92,
                })

        return result_text, corrections

    def _apply_fuzzy_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply fuzzy matching corrections using Levenshtein distance.

        Finds words that are similar to known German vocabulary
        and suggests corrections for likely OCR errors.

        Returns:
            Tuple of (corrected_text, corrections)
        """
        corrections = []
        result_text = text

        # Extract words from text
        words = re.findall(r'\b[a-zA-ZäöüÄÖÜß]+\b', text)

        for word in words:
            # Skip short words and already correct words
            if len(word) < 4:
                continue

            word_lower = word.lower()

            # Skip if word is already in vocabulary
            if word_lower in self._vocabulary_lower:
                continue

            # Skip if word was already corrected by previous steps
            if word_lower in self._correction_lookup:
                continue

            # Find best fuzzy match
            best_match, similarity = self._find_best_match(word)

            if best_match and similarity >= self.FUZZY_THRESHOLD:
                # Preserve case pattern
                if word.isupper():
                    replacement = best_match.upper()
                elif word[0].isupper():
                    replacement = best_match.capitalize()
                else:
                    replacement = best_match.lower()

                if word != replacement:
                    # Use word boundaries for safe replacement
                    pattern = r'\b' + re.escape(word) + r'\b'
                    result_text = re.sub(pattern, replacement, result_text, count=1)

                    corrections.append({
                        "type": "fuzzy_correction",
                        "original": word,
                        "corrected": replacement,
                        "similarity": round(similarity, 3),
                        "confidence": round(similarity * 0.9, 3),
                    })

        return result_text, corrections

    def _find_best_match(self, word: str) -> Tuple[Optional[str], float]:
        """
        Find the best matching word from vocabulary using SequenceMatcher.

        Args:
            word: Word to find match for

        Returns:
            Tuple of (best_match, similarity_score)
        """
        word_lower = word.lower()
        best_match: Optional[str] = None
        best_similarity: float = 0.0

        for vocab_word in self._vocabulary:
            vocab_lower = vocab_word.lower()

            # Quick length check - skip if too different
            len_diff = abs(len(word) - len(vocab_word))
            if len_diff > 2:
                continue

            # Calculate similarity
            similarity = SequenceMatcher(None, word_lower, vocab_lower).ratio()

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = vocab_word

        return best_match, best_similarity

    def _validate_compound_words(
        self, text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Validate and correct German compound words.

        German compound words can be very long and OCR often
        introduces errors at word boundaries.

        Returns:
            Tuple of (corrected_text, corrections)
        """
        corrections = []
        result_text = text

        # Find long words that might be compounds
        long_words = re.findall(r'\b[a-zA-ZäöüÄÖÜß]{12,}\b', text)

        for word in long_words:
            # Try to split and validate compound word
            parts = self._split_compound_word(word)

            if parts and len(parts) > 1:
                # Check if any part needs umlaut correction
                corrected_parts = []
                needs_correction = False

                for part in parts:
                    part_lower = part.lower()
                    if part_lower in self._correction_lookup:
                        corrected = self._correction_lookup[part_lower]
                        corrected_parts.append(corrected)
                        if corrected.lower() != part_lower:
                            needs_correction = True
                    else:
                        corrected_parts.append(part)

                if needs_correction:
                    # Reconstruct compound word
                    replacement = "".join(corrected_parts)

                    # Preserve original case pattern
                    if word[0].isupper():
                        replacement = replacement[0].upper() + replacement[1:]

                    if word != replacement:
                        pattern = r'\b' + re.escape(word) + r'\b'
                        result_text = re.sub(pattern, replacement, result_text, count=1)

                        corrections.append({
                            "type": "compound_correction",
                            "original": word,
                            "corrected": replacement,
                            "parts": parts,
                            "confidence": 0.8,
                        })

        return result_text, corrections

    def _split_compound_word(self, word: str) -> List[str]:
        """
        Attempt to split a German compound word into parts.

        Uses known prefixes, suffixes, and vocabulary to find
        valid split points.

        Args:
            word: Compound word to split

        Returns:
            List of word parts, or empty list if cannot split
        """
        word_lower = word.lower()
        parts = []

        # Try to find a prefix
        for prefix in sorted(self.COMPOUND_PREFIXES, key=len, reverse=True):
            if word_lower.startswith(prefix) and len(word) > len(prefix) + 3:
                remainder = word[len(prefix):]

                # Check if remainder is a known word
                if remainder.lower() in self._vocabulary_lower:
                    return [word[:len(prefix)], remainder]

                # Try to split remainder recursively
                sub_parts = self._split_compound_word(remainder)
                if sub_parts:
                    return [word[:len(prefix)]] + sub_parts

        # Try to find a suffix
        for suffix in sorted(self.COMPOUND_SUFFIXES, key=len, reverse=True):
            if word_lower.endswith(suffix) and len(word) > len(suffix) + 3:
                prefix_part = word[:-len(suffix)]

                # Check if prefix part is a known word
                if prefix_part.lower() in self._vocabulary_lower:
                    return [prefix_part, word[-len(suffix):]]

        # Try to find a split point using vocabulary
        for i in range(4, len(word) - 3):
            left = word[:i]
            right = word[i:]

            left_lower = left.lower()
            right_lower = right.lower()

            # Check if both parts are valid
            left_valid = (
                left_lower in self._vocabulary_lower or
                left_lower in self._correction_lookup
            )
            right_valid = (
                right_lower in self._vocabulary_lower or
                right_lower in self._correction_lookup
            )

            if left_valid and right_valid:
                return [left, right]

        return []

    def _apply_language_tool_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply LanguageTool grammar and spelling corrections.

        Uses LanguageTool for advanced German grammar checking
        and context-aware corrections.

        Returns:
            Tuple of (corrected_text, corrections)
        """
        corrections = []

        if not self._language_tool:
            return text, corrections

        try:
            # Get matches from LanguageTool
            matches = self._language_tool.check(text)

            # Sort by offset in reverse to apply corrections from end to start
            matches_sorted = sorted(
                matches,
                key=lambda m: m.offset,
                reverse=True,
            )

            result_text = text

            for match in matches_sorted:
                # Skip rules that are too aggressive or context-dependent
                if match.ruleId in {
                    "COMMA_PARENTHESIS_WHITESPACE",
                    "WHITESPACE_RULE",
                }:
                    continue

                # Only apply if we have a replacement
                if match.replacements:
                    replacement = match.replacements[0]
                    original = result_text[match.offset:match.offset + match.errorLength]

                    # Apply correction
                    result_text = (
                        result_text[:match.offset] +
                        replacement +
                        result_text[match.offset + match.errorLength:]
                    )

                    corrections.append({
                        "type": "languagetool_correction",
                        "rule_id": match.ruleId,
                        "category": match.category,
                        "original": original,
                        "corrected": replacement,
                        "message": match.message,
                        "confidence": 0.85,
                    })

            return result_text, corrections

        except Exception as e:
            self.logger.warning(
                "languagetool_error",
                error=str(e),
            )
            return text, corrections

    def _calculate_quality_metrics(
        self,
        original_text: str,
        corrected_text: str,
        correction_details: List[Dict[str, Any]],
        final_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive quality metrics for the correction.

        Returns:
            Dictionary with quality metrics
        """
        # Count corrections by type
        correction_counts: Dict[str, int] = {}
        total_confidence = 0.0

        for correction in correction_details:
            ctype = correction.get("type", "unknown")
            correction_counts[ctype] = correction_counts.get(ctype, 0) + 1
            total_confidence += correction.get("confidence", 0.5)

        # Calculate average confidence
        avg_confidence = (
            total_confidence / len(correction_details)
            if correction_details else 1.0
        )

        # Calculate text similarity (how much changed)
        text_similarity = SequenceMatcher(
            None, original_text, corrected_text
        ).ratio()

        # Umlaut density (expected for German text)
        umlaut_count = sum(1 for c in corrected_text if c in "äöüÄÖÜß")
        text_length = len(corrected_text)
        umlaut_density = umlaut_count / text_length if text_length > 0 else 0

        # Expected umlaut density for German text is ~1-3%
        umlaut_score = min(1.0, umlaut_density * 50)  # Normalize to 0-1

        # Validation score from validator
        validation_confidence = final_validation.get("confidence", 0.5)

        # Calculate overall score
        overall_score = (
            avg_confidence * 0.3 +
            validation_confidence * 0.3 +
            umlaut_score * 0.2 +
            (1.0 - abs(0.98 - text_similarity)) * 0.2  # Penalize too many or too few changes
        )

        return {
            "overall_score": round(overall_score, 3),
            "average_confidence": round(avg_confidence, 3),
            "validation_confidence": round(validation_confidence, 3),
            "text_similarity": round(text_similarity, 3),
            "umlaut_density": round(umlaut_density, 5),
            "umlaut_score": round(umlaut_score, 3),
            "corrections_by_type": correction_counts,
            "total_corrections": len(correction_details),
        }

    def get_correction_stats(self) -> Dict[str, Any]:
        """Get statistics about correction capabilities."""
        return {
            "known_umlaut_words": len(self.UMLAUT_WORDS),
            "pattern_corrections": len(self.OCR_SUBSTITUTION_PATTERNS),
            "vocabulary_size": len(self._vocabulary) if hasattr(self, "_vocabulary") else 0,
            "domain_vocabularies": list(DOMAIN_CORRECTIONS.keys()),
            "languagetool_available": LANGUAGETOOL_AVAILABLE,
            "languagetool_enabled": self._language_tool is not None,
            "fuzzy_threshold": self.FUZZY_THRESHOLD,
            "supported_corrections": [
                "ae → ä",
                "oe → ö",
                "ue → ü",
                "ss → ß",
                "AE → Ä",
                "OE → Ö",
                "UE → Ü",
                "Domain-specific corrections",
                "Fuzzy matching (Levenshtein)",
                "Compound word validation",
                "LanguageTool grammar check",
            ],
        }
