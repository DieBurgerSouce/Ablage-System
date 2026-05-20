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
- Context-Window für verbesserte Umlaut-Korrektur
- Hunspell DE Dictionary Integration
- Custom Vocabulary Upload per Projekt

KRITISCH: 100% Genauigkeit für deutsche Umlaute erforderlich.
Feinpoliert und durchdacht - Perfekte deutsche Textverarbeitung.
"""

import json
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Deque, Dict, List, Optional, Set, Tuple

import structlog

from app.agents.base import PostprocessingAgent
from app.german_validator import GermanValidator
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Try to import Hunspell (optional dependency)
try:
    import hunspell
    HUNSPELL_AVAILABLE = True
except ImportError:
    HUNSPELL_AVAILABLE = False
    hunspell = None  # type: ignore
    logger.info("hunspell_not_available", message="Hunspell-Dictionary deaktiviert")

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


# =============================================================================
# Context-Window für verbesserte Umlaut-Korrektur
# =============================================================================


@dataclass
class ContextWindow:
    """
    Sliding Context-Window für kontextabhängige Korrekturen.

    Speichert vorherige Wörter/Sätze für bessere Kontextanalyse.
    Ermöglicht Entscheidungen basierend auf umliegenden Wörtern.
    """

    window_size: int = 5  # Anzahl der Wörter im Kontext
    _words: Deque[str] = field(default_factory=deque)
    _sentences: Deque[str] = field(default_factory=deque)

    def __post_init__(self) -> None:
        """Initialize deques with maxlen."""
        self._words = deque(maxlen=self.window_size)
        self._sentences = deque(maxlen=3)  # Letzte 3 Sätze

    def add_word(self, word: str) -> None:
        """Füge Wort zum Kontext hinzu."""
        self._words.append(word)

    def add_sentence(self, sentence: str) -> None:
        """Füge Satz zum Kontext hinzu."""
        self._sentences.append(sentence)

    def get_context_words(self) -> List[str]:
        """Hole aktuelle Kontext-Wörter."""
        return list(self._words)

    def get_context_sentences(self) -> List[str]:
        """Hole aktuelle Kontext-Sätze."""
        return list(self._sentences)

    def contains_domain_keyword(self, domain_keywords: Set[str]) -> bool:
        """
        Prüfe ob Kontext Domain-Keywords enthält.

        Args:
            domain_keywords: Set von Keywords für die Domain

        Returns:
            True wenn mindestens ein Keyword im Kontext
        """
        context = " ".join(self._words).lower()
        return any(kw.lower() in context for kw in domain_keywords)

    def get_umlaut_density(self) -> float:
        """
        Berechne Umlaut-Dichte im aktuellen Kontext.

        Returns:
            Verhältnis von Umlauten zu Zeichen (0-1)
        """
        context = "".join(self._words)
        if not context:
            return 0.0
        umlaut_count = sum(1 for c in context if c in "äöüÄÖÜß")
        return umlaut_count / len(context)

    def clear(self) -> None:
        """Lösche Kontext."""
        self._words.clear()
        self._sentences.clear()


# Domain-Keywords für kontextbasierte Domain-Erkennung
DOMAIN_KEYWORDS: Dict[str, Set[str]] = {
    "accounting": {
        "rechnung", "bilanz", "konto", "buchung", "steuer", "mwst",
        "umsatz", "gewinn", "verlust", "zahlung", "betrag", "euro", "€",
        "forderung", "verbindlichkeit", "kredit", "soll", "haben",
    },
    "legal": {
        "vertrag", "paragraph", "gesetz", "recht", "klausel", "partei",
        "haftung", "kündigung", "frist", "vollmacht", "gericht", "urteil",
        "anwalt", "mandant", "verfahren", "beschluss", "vereinbarung",
    },
    "medical": {
        "patient", "diagnose", "behandlung", "arzt", "praxis", "krankenhaus",
        "medikament", "rezept", "befund", "untersuchung", "therapie",
        "krankheit", "symptom", "operation", "anamnese", "blutdruck",
    },
}


# =============================================================================
# Custom Vocabulary Manager
# =============================================================================


class CustomVocabularyManager:
    """
    Manager für projekt-spezifische Custom Vocabularies.

    Ermöglicht:
    - Upload von projekt-spezifischen Wortlisten
    - Persistenz in JSON-Dateien
    - Thread-sichere Updates
    """

    DEFAULT_VOCAB_DIR = Path("data/vocabularies")

    def __init__(self, vocab_dir: Optional[Path] = None) -> None:
        """
        Initialisiere CustomVocabularyManager.

        Args:
            vocab_dir: Verzeichnis für Vocabulary-Dateien
        """
        self.vocab_dir = vocab_dir or self.DEFAULT_VOCAB_DIR
        self.vocab_dir.mkdir(parents=True, exist_ok=True)
        self._vocabularies: Dict[str, Set[str]] = {}
        self._corrections: Dict[str, Dict[str, str]] = {}
        self._lock = threading.Lock()

        # Load existing vocabularies
        self._load_all_vocabularies()

        logger.info(
            "custom_vocabulary_manager_initialized",
            vocab_dir=str(self.vocab_dir),
            loaded_projects=len(self._vocabularies),
        )

    def _load_all_vocabularies(self) -> None:
        """Lade alle existierenden Vocabularies."""
        for vocab_file in self.vocab_dir.glob("*.json"):
            try:
                project_id = vocab_file.stem
                self._load_vocabulary(project_id)
            except Exception as e:
                logger.warning(
                    "vocabulary_load_failed",
                    file=str(vocab_file),
                    **safe_error_log(e),
                )

    def _load_vocabulary(self, project_id: str) -> None:
        """Lade Vocabulary für ein Projekt."""
        vocab_file = self.vocab_dir / f"{project_id}.json"

        if not vocab_file.exists():
            return

        with open(vocab_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        with self._lock:
            self._vocabularies[project_id] = set(data.get("words", []))
            self._corrections[project_id] = data.get("corrections", {})

    def _save_vocabulary(self, project_id: str) -> None:
        """Speichere Vocabulary für ein Projekt."""
        vocab_file = self.vocab_dir / f"{project_id}.json"

        with self._lock:
            data = {
                "words": list(self._vocabularies.get(project_id, [])),
                "corrections": self._corrections.get(project_id, {}),
            }

        with open(vocab_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_vocabulary(
        self,
        project_id: str,
        words: List[str],
        corrections: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        """
        Füge Wörter zum Projekt-Vocabulary hinzu.

        Args:
            project_id: Projekt-ID
            words: Liste von Wörtern
            corrections: Optional: Dict von {falsch: richtig} Korrekturen

        Returns:
            Info über hinzugefügte Wörter
        """
        with self._lock:
            if project_id not in self._vocabularies:
                self._vocabularies[project_id] = set()
                self._corrections[project_id] = {}

            existing_count = len(self._vocabularies[project_id])
            self._vocabularies[project_id].update(words)
            new_count = len(self._vocabularies[project_id])

            if corrections:
                self._corrections[project_id].update(corrections)

        self._save_vocabulary(project_id)

        added = new_count - existing_count
        logger.info(
            "vocabulary_updated",
            project_id=project_id,
            words_added=added,
            total_words=new_count,
            corrections_added=len(corrections) if corrections else 0,
        )

        return {
            "project_id": project_id,
            "words_added": added,
            "total_words": new_count,
            "corrections_count": len(self._corrections.get(project_id, {})),
        }

    def get_vocabulary(self, project_id: str) -> Set[str]:
        """Hole Vocabulary für ein Projekt."""
        with self._lock:
            return self._vocabularies.get(project_id, set()).copy()

    def get_corrections(self, project_id: str) -> Dict[str, str]:
        """Hole Korrekturen für ein Projekt."""
        with self._lock:
            return self._corrections.get(project_id, {}).copy()

    def delete_vocabulary(self, project_id: str) -> bool:
        """Lösche Vocabulary für ein Projekt."""
        with self._lock:
            if project_id in self._vocabularies:
                del self._vocabularies[project_id]
            if project_id in self._corrections:
                del self._corrections[project_id]

        vocab_file = self.vocab_dir / f"{project_id}.json"
        if vocab_file.exists():
            vocab_file.unlink()
            return True
        return False

    def list_projects(self) -> List[Dict[str, object]]:
        """Liste alle Projekte mit Vocabulary-Statistiken."""
        with self._lock:
            return [
                {
                    "project_id": pid,
                    "word_count": len(words),
                    "corrections_count": len(self._corrections.get(pid, {})),
                }
                for pid, words in self._vocabularies.items()
            ]


# Global Custom Vocabulary Manager Singleton
_custom_vocab_manager: Optional[CustomVocabularyManager] = None
_vocab_manager_lock = threading.Lock()


def get_custom_vocabulary_manager() -> CustomVocabularyManager:
    """Hole globale CustomVocabularyManager Instanz."""
    global _custom_vocab_manager

    if _custom_vocab_manager is not None:
        return _custom_vocab_manager

    with _vocab_manager_lock:
        if _custom_vocab_manager is None:
            _custom_vocab_manager = CustomVocabularyManager()

    return _custom_vocab_manager


# =============================================================================
# Hunspell Dictionary Integration
# =============================================================================


class HunspellDictionary:
    """
    Hunspell German Dictionary Integration.

    Verwendet das deutsche Hunspell-Wörterbuch für:
    - Rechtschreibprüfung
    - Wortvorschläge
    - Validierung von Korrekturen
    """

    # Typische Pfade für Hunspell-Dictionaries
    DICT_PATHS = [
        "/usr/share/hunspell",
        "/usr/share/myspell",
        "C:\\Hunspell",
        str(Path.home() / "hunspell"),
    ]

    def __init__(self) -> None:
        """Initialisiere Hunspell Dictionary."""
        self._hunspell: Optional[object] = None
        self._available = False

        if HUNSPELL_AVAILABLE:
            self._init_hunspell()

    def _init_hunspell(self) -> None:
        """Initialize Hunspell with German dictionary."""
        # Try to find German dictionary
        for base_path in self.DICT_PATHS:
            dic_path = Path(base_path) / "de_DE.dic"
            aff_path = Path(base_path) / "de_DE.aff"

            if dic_path.exists() and aff_path.exists():
                try:
                    self._hunspell = hunspell.HunSpell(str(dic_path), str(aff_path))
                    self._available = True
                    logger.info(
                        "hunspell_initialized",
                        dic_path=str(dic_path),
                    )
                    return
                except Exception as e:
                    logger.warning(
                        "hunspell_init_failed",
                        path=str(dic_path),
                        **safe_error_log(e),
                    )

        # Try system default
        try:
            self._hunspell = hunspell.HunSpell("de_DE")
            self._available = True
            logger.info("hunspell_initialized_default")
        except Exception as e:
            logger.info(
                "hunspell_not_found",
                **safe_error_log(e),
                message="Hunspell DE Dictionary nicht verfügbar",
            )

    @property
    def available(self) -> bool:
        """Check if Hunspell is available."""
        return self._available

    def spell_check(self, word: str) -> bool:
        """
        Prüfe Rechtschreibung eines Wortes.

        Args:
            word: Wort zum Prüfen

        Returns:
            True wenn korrekt geschrieben
        """
        if not self._available or not self._hunspell:
            return True  # Assume correct if not available

        try:
            return bool(self._hunspell.spell(word))
        except Exception:
            return True

    def suggest(self, word: str) -> List[str]:
        """
        Hole Korrekturvorschläge für ein Wort.

        Args:
            word: Falsch geschriebenes Wort

        Returns:
            Liste von Vorschlägen
        """
        if not self._available or not self._hunspell:
            return []

        try:
            suggestions = self._hunspell.suggest(word)
            return [s.decode("utf-8") if isinstance(s, bytes) else s for s in suggestions]
        except Exception:
            return []

    def get_best_suggestion(self, word: str) -> Optional[str]:
        """
        Hole beste Korrektur für ein Wort (falls falsch).

        Args:
            word: Wort zum Prüfen/Korrigieren

        Returns:
            Bester Vorschlag oder None wenn korrekt
        """
        if self.spell_check(word):
            return None

        suggestions = self.suggest(word)
        if suggestions:
            # Filter für deutsche Umlaute - bevorzuge Vorschläge mit Umlauten
            umlaut_suggestions = [s for s in suggestions if any(c in s for c in "äöüÄÖÜß")]
            if umlaut_suggestions:
                return umlaut_suggestions[0]
            return suggestions[0]

        return None


# Global Hunspell Dictionary Singleton
_hunspell_dict: Optional[HunspellDictionary] = None
_hunspell_lock = threading.Lock()


def get_hunspell_dictionary() -> HunspellDictionary:
    """Hole globale HunspellDictionary Instanz."""
    global _hunspell_dict

    if _hunspell_dict is not None:
        return _hunspell_dict

    with _hunspell_lock:
        if _hunspell_dict is None:
            _hunspell_dict = HunspellDictionary()

    return _hunspell_dict


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
        # ä words (keys = ASCII OCR output, values = correct German)
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

    def __init__(
        self,
        enable_languagetool: bool = True,
        enable_hunspell: bool = True,
        context_window_size: int = 5,
    ):
        """
        Initialize the German Correction Agent.

        Args:
            enable_languagetool: Enable LanguageTool for grammar checking
            enable_hunspell: Enable Hunspell dictionary for spell checking
            context_window_size: Size of context window for corrections
        """
        super().__init__(name="german_correction_agent")
        self.validator = GermanValidator()
        self._build_correction_lookup()
        self._build_vocabulary_lookup()

        # Initialize context window
        self._context_window = ContextWindow(window_size=context_window_size)

        # Initialize LanguageTool if available and enabled
        self._language_tool: Optional[LanguageTool] = None
        if enable_languagetool and LANGUAGETOOL_AVAILABLE:
            self._init_language_tool()

        # Initialize Hunspell dictionary
        self._hunspell: Optional[HunspellDictionary] = None
        if enable_hunspell:
            self._hunspell = get_hunspell_dictionary()

        # Initialize Custom Vocabulary Manager
        self._vocab_manager = get_custom_vocabulary_manager()

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
                **safe_error_log(e),
            )
            self._language_tool = None

    async def process(self, input_data: Dict[str, object]) -> Dict[str, object]:
        """
        Correct German-specific OCR errors in text.

        Full NLP pipeline with:
        1. Context window initialization and domain detection
        2. Custom project vocabulary corrections
        3. Word-based umlaut corrections
        4. Context-aware pattern corrections
        5. Eszett (ß) corrections
        6. Domain-specific corrections (accounting, legal, medical)
        7. Hunspell dictionary corrections
        8. Fuzzy matching for OCR errors (Levenshtein)
        9. Compound word validation
        10. LanguageTool grammar/spelling check
        11. Quality scoring

        Args:
            input_data: Dictionary containing:
                - text: OCR text to correct
                - classification: Optional document classification
                - domain: Optional domain hint (accounting, legal, medical)
                - project_id: Optional project ID for custom vocabulary
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
                - domain_detected: Detected or provided domain
                - context_analysis: Context window analysis
        """
        self.validate_input(input_data, ["text"])

        text = input_data["text"]
        options = input_data.get("options", {})
        domain = input_data.get("domain")
        project_id = input_data.get("project_id")
        classification = input_data.get("classification", {})

        # Step 1: Initialize context window and detect domain
        self._context_window.clear()
        self._initialize_context(text)

        # Auto-detect domain from context if not provided
        if not domain:
            domain = self._detect_domain_from_context()

        # Fallback to classification-based detection
        if not domain and classification:
            domain = self._detect_domain_from_classification(classification)

        self.logger.info(
            "german_correction_started",
            text_length=len(text),
            domain=domain,
            project_id=project_id,
            languagetool_enabled=self._language_tool is not None,
            hunspell_enabled=self._hunspell is not None and self._hunspell.available,
            context_umlaut_density=self._context_window.get_umlaut_density(),
        )

        original_text = text
        correction_details: List[Dict[str, object]] = []

        # Step 2: Validate current state
        initial_validation = self.validator.validate_umlauts(text)

        # Step 3: Apply custom project vocabulary corrections first
        if project_id and not options.get("skip_custom_vocabulary", False):
            text, custom_corrections = self._apply_custom_vocabulary_corrections(
                text, project_id
            )
            correction_details.extend(custom_corrections)

        # Step 4: Apply word-based corrections (known umlaut words)
        text, word_corrections = self._apply_word_corrections(text)
        correction_details.extend(word_corrections)

        # Step 5: Apply context-aware pattern corrections
        if not options.get("skip_pattern_corrections", False):
            text, pattern_corrections = self._apply_context_aware_corrections(text)
            correction_details.extend(pattern_corrections)

        # Step 6: Fix Eszett (ß) issues
        if not options.get("skip_eszett_corrections", False):
            text, eszett_corrections = self._apply_eszett_corrections(text)
            correction_details.extend(eszett_corrections)

        # Step 7: Apply domain-specific corrections
        if domain and not options.get("skip_domain_corrections", False):
            text, domain_corrections = self._apply_domain_corrections(text, domain)
            correction_details.extend(domain_corrections)

        # Step 8: Apply Hunspell dictionary corrections
        if self._hunspell and self._hunspell.available and not options.get("skip_hunspell", False):
            text, hunspell_corrections = self._apply_hunspell_corrections(text)
            correction_details.extend(hunspell_corrections)

        # Step 9: Apply fuzzy matching for remaining OCR errors
        if not options.get("skip_fuzzy_matching", False):
            text, fuzzy_corrections = self._apply_fuzzy_corrections(text)
            correction_details.extend(fuzzy_corrections)

        # Step 10: Validate and fix compound words
        if not options.get("skip_compound_validation", False):
            text, compound_corrections = self._validate_compound_words(text)
            correction_details.extend(compound_corrections)

        # Step 11: Apply LanguageTool corrections (grammar/spelling)
        if self._language_tool and not options.get("skip_languagetool", False):
            text, lt_corrections = self._apply_language_tool_corrections(text)
            correction_details.extend(lt_corrections)

        # Step 12: Validate after all corrections
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
        self, classification: Dict[str, object]
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

    def _initialize_context(self, text: str) -> None:
        """
        Initialize context window with text for context-aware corrections.

        Analyzes first portion of text to establish domain context.

        Args:
            text: Full text to analyze
        """
        # Split into sentences and words
        sentences = re.split(r'[.!?]+', text)[:5]  # First 5 sentences
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                self._context_window.add_sentence(sentence)
                words = re.findall(r'\b\w+\b', sentence)
                for word in words:
                    self._context_window.add_word(word)

    def _detect_domain_from_context(self) -> Optional[str]:
        """
        Detect document domain from context window.

        Uses domain keywords to identify document type.

        Returns:
            Domain name or None
        """
        for domain_name, keywords in DOMAIN_KEYWORDS.items():
            if self._context_window.contains_domain_keyword(keywords):
                self.logger.debug(
                    "domain_detected_from_context",
                    domain=domain_name,
                )
                return domain_name

        return None

    def _apply_custom_vocabulary_corrections(
        self, text: str, project_id: str
    ) -> Tuple[str, List[Dict[str, object]]]:
        """
        Apply project-specific custom vocabulary corrections.

        Args:
            text: Text to correct
            project_id: Project ID for vocabulary lookup

        Returns:
            Tuple of (corrected_text, corrections)
        """
        corrections = []
        result_text = text

        # Get custom corrections for project
        custom_corrections = self._vocab_manager.get_corrections(project_id)

        if not custom_corrections:
            return result_text, corrections

        for wrong, correct in custom_corrections.items():
            # Case-insensitive search
            pattern = r'\b' + re.escape(wrong) + r'\b'
            matches = list(re.finditer(pattern, result_text, re.IGNORECASE))

            for match in reversed(matches):
                original = match.group()

                # Preserve case pattern
                if original.isupper():
                    replacement = correct.upper()
                elif original[0].isupper():
                    replacement = correct.capitalize() if len(correct) > 0 else correct
                else:
                    replacement = correct.lower()

                result_text = (
                    result_text[:match.start()] + replacement + result_text[match.end():]
                )

                corrections.append({
                    "type": "custom_vocabulary",
                    "project_id": project_id,
                    "original": original,
                    "corrected": replacement,
                    "confidence": 0.98,  # High confidence for custom vocabulary
                })

        return result_text, corrections

    def _apply_context_aware_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, object]]]:
        """
        Apply context-aware pattern corrections with enhanced logic.

        Uses context window to make better correction decisions:
        - Higher confidence in high-umlaut-density contexts
        - Domain-specific pattern adjustments
        - Surrounding word analysis

        Returns:
            Tuple of (corrected_text, corrections)
        """
        corrections = []
        result_text = text

        # Get context umlaut density for confidence adjustment
        umlaut_density = self._context_window.get_umlaut_density()
        base_confidence = 0.85 + (umlaut_density * 0.1)  # Higher if more umlauts in context

        # Context-aware ae/oe/ue replacement patterns
        context_patterns = [
            # ae → ä in common contexts
            (r'ae(?=rzt)', 'ä', 'medical'),  # Ärztin, ärztlich
            (r'ae(?=nder)', 'ä', None),  # ändern
            (r'ae(?=hnl)', 'ä', None),  # ähnlich
            (r'ae(?=lter)', 'ä', None),  # älter
            (r'(?<=G)ae(?=st)', 'ä', None),  # Gäste
            (r'(?<=H)ae(?=nd)', 'ä', None),  # Händler
            (r'(?<=J)ae(?=hr)', 'ä', 'accounting'),  # jährlich
            (r'(?<=K)ae(?=uf)', 'ä', 'accounting'),  # Käufer
            (r'(?<=M)ae(?=rz)', 'ä', None),  # März
            (r'(?<=N)ae(?=ch)', 'ä', None),  # nächste
            (r'(?<=Sp)ae(?=t)', 'ä', None),  # später
            (r'(?<=T)ae(?=t)', 'ä', None),  # Tätigkeit
            (r'(?<=W)ae(?=hr)', 'ä', 'accounting'),  # während, Währung

            # oe → ö in common contexts
            (r'(?<=B)oe(?=rs)', 'ö', 'accounting'),  # Börse
            (r'(?<=Geb)oe(?=hr)', 'ü', 'accounting'),  # Gebühr (special case)
            (r'(?<=H)oe(?=he)', 'ö', None),  # Höhe
            (r'(?<=K)oe(?=nn)', 'ö', None),  # können
            (r'(?<=M)oe(?=g)', 'ö', None),  # möglich
            (r'(?<=N)oe(?=t)', 'ö', None),  # nötig
            (r'oe(?=ffn)', 'ö', None),  # Öffnung, öffentlich
            (r'(?<=Sch)oe(?=n)', 'ö', None),  # schön
            (r'(?<=V)oe(?=ll)', 'ö', None),  # völlig
            (r'(?<=W)oe(?=rt)', 'ö', None),  # Wörtlich

            # ue → ü in common contexts
            (r'(?<=F)ue(?=r\b)', 'ü', None),  # für
            (r'(?<=F)ue(?=nf)', 'ü', None),  # fünf
            (r'(?<=G)ue(?=lt)', 'ü', 'legal'),  # gültig
            (r'(?<=G)ue(?=nst)', 'ü', 'accounting'),  # günstig
            (r'(?<=M)ue(?=ss)', 'ü', None),  # müssen
            (r'(?<=Pr)ue(?=f)', 'ü', None),  # Prüfung
            (r'(?<=St)ue(?=ck)', 'ü', 'accounting'),  # Stück
            (r'ue(?=ber)', 'ü', None),  # über, Überweisung
            (r'(?<=W)ue(?=rd)', 'ü', None),  # würde
            (r'(?<=W)ue(?=nsch)', 'ü', None),  # wünschen
            (r'(?<=Z)ue(?=r)', 'ü', None),  # zurück
            (r'(?<=K)ue(?=nd)', 'ü', 'legal'),  # Kündigung
            (r'(?<=Verg)ue(?=t)', 'ü', 'legal'),  # Vergütung
        ]

        # Detect current domain from context
        current_domain = self._detect_domain_from_context()

        for pattern, replacement, pattern_domain in context_patterns:
            # Adjust confidence based on domain match
            confidence = base_confidence
            if pattern_domain and current_domain == pattern_domain:
                confidence += 0.05  # Boost for domain match

            matches = list(re.finditer(pattern, result_text, re.IGNORECASE))
            for match in reversed(matches):
                original = match.group()
                result_text = result_text[:match.start()] + replacement + result_text[match.end():]

                corrections.append({
                    "type": "context_pattern_correction",
                    "original": original,
                    "corrected": replacement,
                    "position": match.start(),
                    "confidence": round(min(confidence, 0.95), 3),
                    "domain_match": pattern_domain == current_domain if pattern_domain else None,
                })

        return result_text, corrections

    def _apply_hunspell_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, object]]]:
        """
        Apply Hunspell dictionary corrections.

        Uses German Hunspell dictionary for:
        - Spell checking
        - Umlaut-aware suggestions
        - Validation of corrections

        Returns:
            Tuple of (corrected_text, corrections)
        """
        corrections = []
        result_text = text

        if not self._hunspell or not self._hunspell.available:
            return result_text, corrections

        # Find words that might need correction
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text)  # Only ASCII words (potential umlaut missing)

        for word in words:
            # Skip if already contains umlauts
            if any(c in word for c in "äöüÄÖÜß"):
                continue

            # Check if word needs correction
            suggestion = self._hunspell.get_best_suggestion(word)

            if suggestion and suggestion != word:
                # Only apply if suggestion contains umlauts (likely OCR error)
                if any(c in suggestion for c in "äöüÄÖÜß"):
                    # Preserve case
                    if word.isupper():
                        replacement = suggestion.upper()
                    elif word[0].isupper() and word[1:].islower():
                        replacement = suggestion.capitalize()
                    else:
                        replacement = suggestion

                    # Apply correction
                    pattern = r'\b' + re.escape(word) + r'\b'
                    new_text = re.sub(pattern, replacement, result_text, count=1)

                    if new_text != result_text:
                        result_text = new_text
                        corrections.append({
                            "type": "hunspell_correction",
                            "original": word,
                            "corrected": replacement,
                            "confidence": 0.88,
                        })

        return result_text, corrections

    def _apply_word_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, object]]]:
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
    ) -> Tuple[str, List[Dict[str, object]]]:
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
    ) -> Tuple[str, List[Dict[str, object]]]:
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
    ) -> Tuple[str, List[Dict[str, object]]]:
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

        # ASCII↔UTF-8 mapping for umlaut variants
        umlaut_map = [("ae", "\u00e4"), ("oe", "\u00f6"), ("ue", "\u00fc")]

        for wrong, correct in domain_words.items():
            # Try both ASCII and UTF-8 forms of the key so that
            # partial conversions by earlier pipeline steps (Step 5
            # context-aware corrections) are still matched.
            variants = [wrong]
            alt = wrong
            for ascii_form, utf8_form in umlaut_map:
                alt = alt.replace(ascii_form, utf8_form)
            if alt != wrong:
                variants.append(alt)

            for variant in variants:
                pattern = r'\b' + re.escape(variant) + r'\b'
                matches = list(re.finditer(pattern, result_text, re.IGNORECASE))

                if not matches:
                    continue

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

                    if original != replacement:
                        corrections.append({
                            "type": "domain_correction",
                            "domain": domain,
                            "original": original,
                            "corrected": replacement,
                            "confidence": 0.92,
                        })

                break  # First matching variant wins; skip remaining variants

        return result_text, corrections

    def _apply_fuzzy_corrections(
        self, text: str
    ) -> Tuple[str, List[Dict[str, object]]]:
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
    ) -> Tuple[str, List[Dict[str, object]]]:
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
    ) -> Tuple[str, List[Dict[str, object]]]:
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
                **safe_error_log(e),
            )
            return text, corrections

    def _calculate_quality_metrics(
        self,
        original_text: str,
        corrected_text: str,
        correction_details: List[Dict[str, object]],
        final_validation: Dict[str, object],
    ) -> Dict[str, object]:
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

    def get_correction_stats(self) -> Dict[str, object]:
        """Get statistics about correction capabilities."""
        # Get custom vocabulary stats
        custom_vocab_projects = self._vocab_manager.list_projects() if hasattr(self, "_vocab_manager") else []

        return {
            "known_umlaut_words": len(self.UMLAUT_WORDS),
            "pattern_corrections": len(self.OCR_SUBSTITUTION_PATTERNS),
            "vocabulary_size": len(self._vocabulary) if hasattr(self, "_vocabulary") else 0,
            "domain_vocabularies": list(DOMAIN_CORRECTIONS.keys()),
            "languagetool_available": LANGUAGETOOL_AVAILABLE,
            "languagetool_enabled": self._language_tool is not None,
            "hunspell_available": HUNSPELL_AVAILABLE,
            "hunspell_enabled": self._hunspell is not None and self._hunspell.available if hasattr(self, "_hunspell") else False,
            "context_window_size": self._context_window.window_size if hasattr(self, "_context_window") else 0,
            "custom_vocabulary_projects": len(custom_vocab_projects),
            "custom_vocabulary_details": custom_vocab_projects,
            "fuzzy_threshold": self.FUZZY_THRESHOLD,
            "supported_corrections": [
                "ae → ä",
                "oe → ö",
                "ue → ü",
                "ss → ß",
                "AE → Ä",
                "OE → Ö",
                "UE → Ü",
                "Domain-specific corrections (accounting, legal, medical)",
                "Context-aware pattern corrections",
                "Hunspell dictionary corrections",
                "Custom project vocabulary",
                "Fuzzy matching (Levenshtein)",
                "Compound word validation",
                "LanguageTool grammar check",
            ],
        }

    # =========================================================================
    # Custom Vocabulary API Methods
    # =========================================================================

    def add_project_vocabulary(
        self,
        project_id: str,
        words: List[str],
        corrections: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        """
        Add custom vocabulary for a project.

        Args:
            project_id: Unique project identifier
            words: List of valid words to add
            corrections: Optional dict of {wrong: correct} mappings

        Returns:
            Info about added vocabulary
        """
        return self._vocab_manager.add_vocabulary(project_id, words, corrections)

    def get_project_vocabulary(self, project_id: str) -> Dict[str, object]:
        """
        Get vocabulary for a project.

        Args:
            project_id: Project identifier

        Returns:
            Dict with words and corrections
        """
        return {
            "project_id": project_id,
            "words": list(self._vocab_manager.get_vocabulary(project_id)),
            "corrections": self._vocab_manager.get_corrections(project_id),
        }

    def delete_project_vocabulary(self, project_id: str) -> bool:
        """
        Delete vocabulary for a project.

        Args:
            project_id: Project identifier

        Returns:
            True if deleted
        """
        return self._vocab_manager.delete_vocabulary(project_id)

    def list_project_vocabularies(self) -> List[Dict[str, object]]:
        """
        List all project vocabularies.

        Returns:
            List of project vocabulary stats
        """
        return self._vocab_manager.list_projects()
