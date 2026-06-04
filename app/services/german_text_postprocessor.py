# -*- coding: utf-8 -*-
"""
Unified German Text Postprocessor.

Gemeinsamer Service für deutsche Textnachbearbeitung in allen OCR-Backends:
- Umlaut-Restaurierung (ae->ä, oe->ö, ue->ü)
- Eszett-Korrektur (ss->ß wo angemessen)
- Kontextbasierte Korrektur mit deutschem Woerterbuch
- Compound-Word-Erkennung und -Splitting
- Phonetische Ähnlichkeit (Cologne Phonetic)
- Integration mit GermanValidator
- Branchenspezifische Fachvokabulare (Phase 8)

Feinpoliert und durchdacht - Deutsche OCR-Qualität.
"""

import re
import structlog
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING
from functools import lru_cache
from app.core.safe_errors import safe_error_log

if TYPE_CHECKING:
    from app.services.ocr.industry_vocabulary_service import (
        IndustryType,
        IndustryVocabularyService,
    )
    from app.services.german_spellchecker import GermanSpellchecker

logger = structlog.get_logger(__name__)


class GermanTextPostprocessor:
    """
    Unified German Text Postprocessor für alle OCR-Backends.

    Features:
    - Context-aware Umlaut-Restaurierung
    - Eszett (ss) Korrektur
    - Deutsches Woerterbuch für häufige Woerter
    - Integration mit GermanValidator (optional)
    - Statistiken über Korrekturen

    Usage:
        postprocessor = GermanTextPostprocessor()
        result = postprocessor.postprocess(text)
        # result = {"text": "korrigierter Text", "corrections": [...], ...}
    """

    # Deutsche Wörter die häufig Umlaute benötigen (MIT echten Umlauten!)
    # Sortiert nach Häufigkeit in Geschäftsdokumenten
    GERMAN_UMLAUT_WORDS: Set[str] = {
        # Geschäftsbegriffe
        'über', 'überprüfung', 'überweisung', 'übersicht', 'übernahme',
        'für', 'führung', 'ausführung', 'durchführung',
        'büro', 'gebühr', 'gebühren',
        'größe', 'größer', 'größte',
        'öffentlich', 'öffnung', 'eröffnung',
        'änderung', 'ändern', 'ergänzung',
        'prüfung', 'prüfen', 'überprüfung',
        'erklärung', 'klärung', 'aufklärung',
        'möglich', 'möglichkeit', 'unmöglich',
        'geschäft', 'geschäftsführer', 'geschäftlich',
        'gültig', 'gültigkeit', 'ungültig',
        'straße', 'hauptstraße',
        'müller', 'schröder', 'köhler', 'bäcker',
        'münchen', 'köln', 'düsseldorf', 'nürnberg', 'würzburg',
        'träger', 'empfänger', 'absender',
        'währung', 'erläuterung', 'begründung',
        'verfügung', 'verfügbar', 'zuständig',
        'ausländisch', 'inländisch',
        'stück', 'rückgabe', 'rücksendung',
        'kürzlich', 'natürlich', 'persönlich',
        # Zusätzliche häufige Wörter
        'üblich', 'gewöhnlich', 'völlig', 'völker',
        'höchst', 'nächst', 'nächste', 'früchte',
        'märz', 'körper', 'börse', 'gerät', 'geräte',
        'tätigkeit', 'tätig', 'qualität', 'kapazität',
        'universität', 'priorität', 'autorität',
        'zurück', 'zurückgeben', 'zurücksenden',
        'ausdrücklich', 'selbstverständlich',
        'möglicherweise', 'gewöhnlicherweise',
        'bezüglich', 'diesbezüglich', 'hinsichtlich',
        # Weitere häufige Geschäftswörter
        'bürger', 'bürgerlich', 'bürokratie',
        'fähig', 'fähigkeit', 'unfähig',
        'händler', 'händisch', 'hämisch',
        'jährlich', 'järhlich', 'monatlich',
        'länger', 'längst', 'längere',
        'männlich', 'weiblich', 'mündlich',
        'nötig', 'notwendig', 'unnötig',
        'öfter', 'öfters', 'häufig',
        'plötzlich', 'schließlich', 'endgültig',
        'räumlich', 'räumen', 'geräumig',
        'säulen', 'säuberlich', 'säubern',
        'täglich', 'wöchentlich', 'stündlich',
        'übrig', 'übrigens', 'überall',
        'völkerrecht', 'völkerrechtlich',
        'wählen', 'wähler', 'auswählen',
        'zählen', 'zähler', 'unzählig',
    }

    # Wörter mit Eszett (nach langem Vokal/Diphthong) - MIT echtem ß!
    ESZETT_WORDS: Set[str] = {
        'groß', 'größe', 'größer', 'größte',
        'straße', 'hauptstraße',
        'gruß', 'grüße', 'begrüßung',
        'fuß', 'füße',
        'maß', 'maße', 'maßnahme', 'maßnahmen',
        'spaß',
        'weiß', 'weißer',
        'heiß', 'heißt', 'heißen',
        'außen', 'außer', 'außerdem', 'außerhalb',
        'schließen', 'schließlich', 'abschließend',
        'gemäß',
        'beschluß', 'anschluß', 'abschluß',
        'fließend', 'fließen',
        'gießen', 'schießen',
        'reißen', 'beißen',
        'genuß', 'genüsse',
        # Weitere häufige ß-Wörter
        'bloß', 'bloße',
        'büßen', 'büße',
        'draußen',
        'fleiß', 'fleißig',
        'fraß',
        'gefäß', 'gefäße',
        'gewiß', 'gewißheit',
        'gleißen', 'gleißend',
        'haß', 'hassen',  # Alte Rechtschreibung
        'heißer', 'heißeste',
        'laß', 'lassen',  # Alte Rechtschreibung
        'maßstab', 'maßgeblich',
        'muß', 'müssen',  # Alte Rechtschreibung
        'naß', 'nässe',  # Alte Rechtschreibung
        'paß', 'pässe',  # Alte Rechtschreibung
        'preußen', 'preußisch',
        'riß', 'risse',
        'ruß', 'rußig',
        'saß', 'säße',
        'schoß', 'schöße',
        'sproß', 'sprößling',
        'stoß', 'stöße', 'stoßen',
        'süß', 'süße', 'süßigkeit',
        'vergißmeinnicht',
        'verschließen', 'verschlußsache',
        'wußte',  # Alte Rechtschreibung
    }

    # Mapping von ASCII zu Umlaut (KORRIGIERT!)
    ASCII_TO_UMLAUT: Dict[str, str] = {
        'ae': 'ä',
        'oe': 'ö',
        'ue': 'ü',
        'Ae': 'Ä',
        'Oe': 'Ö',
        'Ue': 'Ü',
        'AE': 'Ä',
        'OE': 'Ö',
        'UE': 'Ü',
    }

    # Häufige deutsche Compound-Word-Präfixe
    COMPOUND_PREFIXES: Set[str] = {
        'über', 'unter', 'vor', 'nach', 'aus', 'ein', 'ab', 'an', 'auf',
        'durch', 'gegen', 'hinter', 'mit', 'neben', 'ohne', 'seit', 'von',
        'zwischen', 'außer', 'bei', 'binnen', 'dank', 'entlang', 'gemäß',
        'infolge', 'kraft', 'laut', 'mittels', 'trotz', 'während', 'wegen',
        'zufolge', 'zugunsten', 'zuliebe', 'zwecks',
        # Business-spezifisch
        'geschäfts', 'kunden', 'dienst', 'leistungs', 'vertrags', 'rechts',
        'steuer', 'finanz', 'personal', 'versicherungs', 'handels', 'betriebs',
    }

    # Häufige Compound-Word-Suffixe
    COMPOUND_SUFFIXES: Set[str] = {
        'ung', 'heit', 'keit', 'schaft', 'tum', 'nis', 'sal', 'ling',
        'chen', 'lein', 'er', 'ler', 'ner', 'ist', 'ant', 'ent',
        'bericht', 'nummer', 'datum', 'betrag', 'konto', 'vertrag',
        'rechnung', 'leistung', 'zahlung', 'bestellung', 'lieferung',
    }

    # Cologne Phonetic Mapping für deutsche Laute
    COLOGNE_PHONETIC_MAP: Dict[str, str] = {
        'a': '0', 'e': '0', 'i': '0', 'o': '0', 'u': '0',
        'ä': '0', 'ö': '0', 'ü': '0',
        'h': '',
        'b': '1', 'p': '1',
        'd': '2', 't': '2',
        'f': '3', 'v': '3', 'w': '3', 'ph': '3',
        'g': '4', 'k': '4', 'q': '4',
        'x': '48',
        'l': '5',
        'm': '6', 'n': '6',
        'r': '7',
        's': '8', 'z': '8', 'ß': '8',
        'c': '4',  # Depends on context, simplified
        'j': '0',
    }

    def __init__(
        self,
        use_validator: bool = True,
        aggressive_mode: bool = False,
        use_industry_vocabulary: bool = True,
        use_spellchecker: bool = True
    ):
        """
        Initialisiere German Text Postprocessor.

        Args:
            use_validator: GermanValidator für erweiterte Validierung nutzen
            aggressive_mode: Aggressivere Umlaut-Ersetzung (mehr false positives möglich)
            use_industry_vocabulary: Branchenspezifische Vokabulare nutzen (Phase 8)
            use_spellchecker: SymSpell-basierte Rechtschreibkorrektur nutzen (Phase 5.1)
        """
        self.use_validator = use_validator
        self.aggressive_mode = aggressive_mode
        self.use_industry_vocabulary = use_industry_vocabulary
        self.use_spellchecker = use_spellchecker
        self._validator = None
        self._industry_vocab_service: Optional["IndustryVocabularyService"] = None
        self._spellchecker: Optional["GermanSpellchecker"] = None
        self._stats = {
            "total_processed": 0,
            "umlaut_corrections": 0,
            "eszett_corrections": 0,
            "industry_corrections": 0,
            "spelling_corrections": 0,
            "validation_errors": 0
        }

        # Lade GermanValidator wenn verfügbar
        if use_validator:
            try:
                from app.german_validator import GermanValidator
                self._validator = GermanValidator()
                logger.debug("german_validator_loaded")
            except ImportError:
                logger.warning("german_validator_not_available")
                self._validator = None

        # Lade IndustryVocabularyService wenn verfügbar (Phase 8)
        if use_industry_vocabulary:
            try:
                from app.services.ocr.industry_vocabulary_service import (
                    get_industry_vocabulary_service,
                )
                self._industry_vocab_service = get_industry_vocabulary_service()
                logger.debug("industry_vocabulary_service_loaded")
            except ImportError:
                logger.warning("industry_vocabulary_service_not_available")
                self._industry_vocab_service = None

        # Lade GermanSpellchecker wenn verfügbar (Phase 5.1)
        if use_spellchecker:
            try:
                from app.services.german_spellchecker import get_german_spellchecker
                self._spellchecker = get_german_spellchecker()
                logger.debug("german_spellchecker_loaded")
            except ImportError:
                logger.warning("german_spellchecker_not_available")
                self._spellchecker = None

        # Precompile regex patterns für Performance
        self._word_pattern = re.compile(r'\b\w+\b')

        # Erstelle Lookup-Dictionaries für schnellere Suche
        self._umlaut_lookup = self._build_umlaut_lookup()
        self._eszett_lookup = self._build_eszett_lookup()

        logger.info(
            "german_postprocessor_initialized",
            use_validator=use_validator,
            aggressive_mode=aggressive_mode,
            use_industry_vocabulary=use_industry_vocabulary,
            use_spellchecker=use_spellchecker,
            umlaut_words_count=len(self.GERMAN_UMLAUT_WORDS),
            eszett_words_count=len(self.ESZETT_WORDS)
        )

    def _build_umlaut_lookup(self) -> Dict[str, str]:
        """
        Erstelle Lookup von ASCII-Varianten zu Umlaut-Versionen.

        Returns:
            Dict mapping "für" -> "für", "über" -> "über", etc.
        """
        lookup = {}

        for word in self.GERMAN_UMLAUT_WORDS:
            # Generiere ASCII-Version (ohne Umlaute)
            ascii_version = word
            ascii_version = ascii_version.replace('ä', 'ae')
            ascii_version = ascii_version.replace('ö', 'oe')
            ascii_version = ascii_version.replace('ü', 'ue')
            ascii_version = ascii_version.replace('Ä', 'Ae')
            ascii_version = ascii_version.replace('Ö', 'Oe')
            ascii_version = ascii_version.replace('Ü', 'Ue')

            # Mapping: ASCII -> echte Umlaute
            if ascii_version != word:
                lookup[ascii_version] = word

        return lookup

    def _build_eszett_lookup(self) -> Dict[str, str]:
        """
        Erstelle Lookup von ss-Varianten zu Eszett-Versionen.

        Returns:
            Dict mapping "strasse" -> "Straße", "gross" -> "groß", etc.
        """
        lookup = {}

        for word in self.ESZETT_WORDS:
            # Generiere ss-Version (ohne ß)
            ss_version = word.replace('ß', 'ss')

            # Mapping: ss-Version -> ß-Version
            if ss_version != word:
                lookup[ss_version] = word

        return lookup

    @lru_cache(maxsize=10000)
    def cologne_phonetic(self, word: str) -> str:
        """
        Berechne Cologne Phonetic Code für ein deutsches Wort.

        Der Cologne Phonetic Algorithmus ist optimiert für deutsche Namen
        und Wörter, im Gegensatz zu Soundex (für Englisch).

        Args:
            word: Deutsches Wort

        Returns:
            Phonetischer Code als String
        """
        if not word:
            return ""

        word = word.lower().strip()
        result = []

        i = 0
        while i < len(word):
            char = word[i]

            # Spezialfall: 'ch' nach a, o, u -> '4', sonst '8'
            if char == 'c' and i + 1 < len(word) and word[i + 1] == 'h':
                if i > 0 and word[i - 1] in 'aou':
                    result.append('4')
                else:
                    result.append('8')
                i += 2
                continue

            # Spezialfall: 'sch' -> '8'
            if char == 's' and i + 2 < len(word) and word[i + 1:i + 3] == 'ch':
                result.append('8')
                i += 3
                continue

            # Spezialfall: 'ph' -> '3'
            if char == 'p' and i + 1 < len(word) and word[i + 1] == 'h':
                result.append('3')
                i += 2
                continue

            # Standard-Mapping
            if char in self.COLOGNE_PHONETIC_MAP:
                code = self.COLOGNE_PHONETIC_MAP[char]
                if code:
                    result.append(code)
            i += 1

        # Entferne aufeinanderfolgende Duplikate
        if not result:
            return ""

        final = [result[0]]
        for code in result[1:]:
            if code != final[-1]:
                final.append(code)

        # Entferne führende Nullen (außer wenn nur Nullen)
        code_str = ''.join(final)
        return code_str.lstrip('0') or '0'

    def phonetic_similarity(self, word1: str, word2: str) -> float:
        """
        Berechne phonetische Ähnlichkeit zweier deutscher Wörter.

        Verwendet Cologne Phonetic für deutschen Sprachraum.

        Args:
            word1: Erstes Wort
            word2: Zweites Wort

        Returns:
            Ähnlichkeit zwischen 0.0 und 1.0
        """
        code1 = self.cologne_phonetic(word1)
        code2 = self.cologne_phonetic(word2)

        if code1 == code2:
            return 1.0

        # Levenshtein-basierte Ähnlichkeit der phonetischen Codes
        max_len = max(len(code1), len(code2))
        if max_len == 0:
            return 1.0

        distance = self._levenshtein_distance(code1, code2)
        return 1.0 - (distance / max_len)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Berechne Levenshtein-Distanz zwischen zwei Strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def split_compound_word(self, word: str) -> List[str]:
        """
        Versuche ein deutsches Compound-Word zu splitten.

        Verwendet Präfix/Suffix-Listen und Heuristiken für deutsche
        Komposita (z.B. "Geschäftsbericht" -> ["Geschäfts", "bericht"]).

        Args:
            word: Potentielles Compound-Word

        Returns:
            Liste der Wortbestandteile (oder [word] wenn kein Compound)
        """
        if len(word) < 6:  # Zu kurz für sinnvolles Compound
            return [word]

        word_lower = word.lower()
        parts = []

        # Prüfe bekannte Präfixe
        for prefix in sorted(self.COMPOUND_PREFIXES, key=len, reverse=True):
            if word_lower.startswith(prefix) and len(word_lower) > len(prefix) + 3:
                rest = word[len(prefix):]
                parts.append(word[:len(prefix)])
                # Rekursiv den Rest prüfen
                rest_parts = self.split_compound_word(rest)
                parts.extend(rest_parts)
                return parts

        # Prüfe bekannte Suffixe
        for suffix in sorted(self.COMPOUND_SUFFIXES, key=len, reverse=True):
            if word_lower.endswith(suffix) and len(word_lower) > len(suffix) + 3:
                stem = word[:-len(suffix)]
                parts.append(stem)
                parts.append(word[-len(suffix):])
                return parts

        # Keine Aufteilung gefunden
        return [word]

    def correct_with_phonetic(
        self,
        word: str,
        candidates: List[str],
        threshold: float = 0.7
    ) -> Optional[str]:
        """
        Korrigiere ein Wort basierend auf phonetischer Ähnlichkeit.

        Nützlich für OCR-Fehler wie "Mueller" -> "Müller".

        Args:
            word: Zu korrigierendes Wort
            candidates: Liste möglicher korrekter Wörter
            threshold: Mindest-Ähnlichkeit (0.0-1.0)

        Returns:
            Bester Match oder None wenn keiner über threshold
        """
        best_match = None
        best_similarity = threshold

        for candidate in candidates:
            similarity = self.phonetic_similarity(word, candidate)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = candidate

        return best_match

    def postprocess(
        self,
        text: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Führe deutsche Textnachbearbeitung durch.

        Args:
            text: Zu verarbeitender Text
            options: Zusätzliche Optionen:
                - skip_umlauts: Umlaut-Korrektur überspringen
                - skip_eszett: Eszett-Korrektur überspringen
                - skip_spelling: Rechtschreibkorrektur überspringen (Phase 5.1)
                - skip_industry: Branchenspezifische Korrektur überspringen
                - industry: Explizite Branche (z.B. "baugewerbe", "medizin")
                - expand_abbreviations: Abkürzungen im Text expandieren
                - validate: Mit GermanValidator validieren

        Returns:
            Dict mit:
                - text: Korrigierter Text
                - corrections: Liste der Korrekturen
                - stats: Statistiken
                - validation: Validierungsergebnis (optional)
                - industry_detection: Erkannte Branche (optional)
        """
        if not text or not text.strip():
            return {
                "text": text or "",
                "corrections": [],
                "stats": {"total": 0},
                "processed": False
            }

        options = options or {}
        corrections: List[Dict[str, Any]] = []
        corrected_text = text

        self._stats["total_processed"] += 1

        # 1. Umlaut-Restaurierung
        if not options.get("skip_umlauts", False):
            corrected_text, umlaut_corrections = self._restore_umlauts(corrected_text)
            corrections.extend(umlaut_corrections)
            self._stats["umlaut_corrections"] += len(umlaut_corrections)

        # 2. Eszett-Korrektur
        if not options.get("skip_eszett", False):
            corrected_text, eszett_corrections = self._restore_eszett(corrected_text)
            corrections.extend(eszett_corrections)
            self._stats["eszett_corrections"] += len(eszett_corrections)

        # 3. Rechtschreibkorrektur mit SymSpell (Phase 5.1)
        if not options.get("skip_spelling", False) and self._spellchecker:
            corrected_text, spelling_corrections = self._apply_spelling_correction(
                corrected_text
            )
            corrections.extend(spelling_corrections)
            self._stats["spelling_corrections"] += len(spelling_corrections)

        # 4. Branchenspezifische Korrektur (Phase 8)
        industry_detection = None
        if not options.get("skip_industry", False) and self._industry_vocab_service:
            corrected_text, industry_corrections, industry_detection = (
                self._apply_industry_corrections(
                    corrected_text,
                    industry=options.get("industry"),
                    expand_abbreviations=options.get("expand_abbreviations", False)
                )
            )
            corrections.extend(industry_corrections)
            self._stats["industry_corrections"] += len(industry_corrections)

        # 5. Validierung (optional)
        validation_result = None
        if options.get("validate", False) and self._validator:
            try:
                validation_result = self._validator.validate_umlauts(corrected_text)
            except Exception as e:
                logger.warning("validation_failed", **safe_error_log(e))
                self._stats["validation_errors"] += 1

        # 6. Erstelle Ergebnis
        result = {
            "text": corrected_text,
            "corrections": corrections,
            "corrections_count": len(corrections),
            "stats": {
                "umlaut_corrections": sum(1 for c in corrections if c["type"] == "umlaut"),
                "eszett_corrections": sum(1 for c in corrections if c["type"] == "eszett"),
                "spelling_corrections": sum(1 for c in corrections if c["type"] == "spelling"),
                "industry_corrections": sum(
                    1 for c in corrections
                    if c.get("type") in ("variant_correction", "general_ocr_correction")
                ),
                "total": len(corrections)
            },
            "processed": True,
            "text_changed": corrected_text != text
        }

        if validation_result:
            result["validation"] = validation_result

        if industry_detection:
            result["industry_detection"] = industry_detection

        logger.debug(
            "german_postprocessing_completed",
            corrections_count=len(corrections),
            text_changed=result["text_changed"],
            industry_detected=industry_detection.get("industry") if industry_detection else None
        )

        return result

    def _apply_industry_corrections(
        self,
        text: str,
        industry: Optional[str] = None,
        expand_abbreviations: bool = False
    ) -> Tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Wende branchenspezifische Korrekturen an (Phase 8).

        Args:
            text: Eingabetext
            industry: Explizite Branche (optional)
            expand_abbreviations: Abkürzungen expandieren

        Returns:
            Tuple (korrigierter_text, korrekturen, industry_detection)
        """
        if not self._industry_vocab_service:
            return text, [], None

        try:
            from app.services.ocr.industry_vocabulary_service import IndustryType


            # Branche bestimmen
            industry_type = None
            if industry:
                try:
                    industry_type = IndustryType(industry.lower())
                except ValueError:
                    logger.warning(
                        "invalid_industry_type",
                        industry=industry,
                        valid_types=[t.value for t in IndustryType]
                    )

            # Korrekturen anwenden
            result = self._industry_vocab_service.apply_industry_corrections(
                text=text,
                industry=industry_type,
                expand_abbreviations=expand_abbreviations,
                auto_detect_industry=True
            )

            # Industry Detection Info erstellen
            industry_detection = None
            if result.detected_industry:
                industry_detection = {
                    "industry": result.detected_industry.value,
                    "confidence": result.industry_confidence,
                    "abbreviations_expanded": result.abbreviations_expanded,
                    "compounds_found": result.compounds_found
                }

            return result.corrected_text, result.corrections, industry_detection

        except Exception as e:
            logger.warning(
                "industry_correction_failed",
                **safe_error_log(e),
                error_type=type(e).__name__
            )
            return text, [], None

    def _apply_spelling_correction(
        self,
        text: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Wende SymSpell-basierte Rechtschreibkorrektur an (Phase 5.1).

        Args:
            text: Eingabetext

        Returns:
            Tuple (korrigierter_text, korrekturen)
        """
        if not self._spellchecker:
            return text, []

        try:
            corrected_text, corrections = self._spellchecker.correct_text(
                text,
                preserve_case=True,
                preserve_numbers=True
            )

            # Konvertiere Corrections in unser Format
            formatted_corrections = []
            for corr in corrections:
                formatted_corrections.append({
                    "type": "spelling",
                    "original": corr["original"],
                    "corrected": corr["corrected"],
                    "position": corr.get("position", 0),
                    "confidence": 0.85  # SymSpell-basierte Korrektur
                })

            return corrected_text, formatted_corrections

        except Exception as e:
            logger.warning(
                "spelling_correction_failed",
                **safe_error_log(e),
                error_type=type(e).__name__
            )
            return text, []

    def _restore_umlauts(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Restauriere Umlaute in deutschen Woertern.

        Verwendet kontextbasierte Ersetzung mit Woerterbuch-Lookup.

        Args:
            text: Eingabetext

        Returns:
            Tuple (korrigierter_text, liste_der_korrekturen)
        """
        corrections = []
        words = self._word_pattern.findall(text)

        for word in words:
            word_lower = word.lower()

            # Lookup in vorberechneter Tabelle
            if word_lower in self._umlaut_lookup:
                corrected_word = self._umlaut_lookup[word_lower]

                # Grossschreibung beibehalten
                if word[0].isupper():
                    corrected_word = corrected_word.capitalize()
                elif word.isupper():
                    corrected_word = corrected_word.upper()

                # Ersetze im Text (nur erstes Vorkommen)
                pattern = r'\b' + re.escape(word) + r'\b'
                if re.search(pattern, text):
                    text = re.sub(pattern, corrected_word, text, count=1)
                    corrections.append({
                        "type": "umlaut",
                        "original": word,
                        "corrected": corrected_word,
                        "confidence": 0.95
                    })

        return text, corrections

    def _restore_eszett(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Restauriere Eszett (ss) in deutschen Woertern.

        Args:
            text: Eingabetext

        Returns:
            Tuple (korrigierter_text, liste_der_korrekturen)
        """
        corrections = []

        for ss_word, eszett_word in self._eszett_lookup.items():
            # Case variations
            variations = [
                (ss_word, eszett_word),
                (ss_word.capitalize(), eszett_word.capitalize()),
                (ss_word.upper(), eszett_word.upper()),
            ]

            for original, replacement in variations:
                pattern = r'\b' + re.escape(original) + r'\b'
                if re.search(pattern, text):
                    text = re.sub(pattern, replacement, text)
                    corrections.append({
                        "type": "eszett",
                        "original": original,
                        "corrected": replacement,
                        "confidence": 0.90
                    })

        return text, corrections

    def get_stats(self) -> Dict[str, Any]:
        """Hole Verarbeitungsstatistiken."""
        stats = {
            **self._stats,
            "umlaut_words_in_dictionary": len(self.GERMAN_UMLAUT_WORDS),
            "eszett_words_in_dictionary": len(self.ESZETT_WORDS)
        }

        # Fuege Industry Vocabulary Stats hinzu wenn verfügbar
        if self._industry_vocab_service:
            industry_stats = self._industry_vocab_service.get_statistics()
            stats["industry_vocabularies"] = industry_stats

        # Fuege Spellchecker Stats hinzu wenn verfügbar (Phase 5.1)
        if self._spellchecker:
            spellchecker_stats = self._spellchecker.get_stats()
            stats["spellchecker"] = spellchecker_stats

        return stats

    def reset_stats(self) -> None:
        """Setze Statistiken zurück."""
        self._stats = {
            "total_processed": 0,
            "umlaut_corrections": 0,
            "eszett_corrections": 0,
            "spelling_corrections": 0,
            "industry_corrections": 0,
            "validation_errors": 0
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_postprocessor: Optional[GermanTextPostprocessor] = None


def get_german_postprocessor() -> GermanTextPostprocessor:
    """Hole Singleton-Instance des German Postprocessors."""
    global _postprocessor
    if _postprocessor is None:
        _postprocessor = GermanTextPostprocessor()
    return _postprocessor


def postprocess_german_text(
    text: str,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience-Funktion für deutsche Textnachbearbeitung.

    Args:
        text: Zu verarbeitender Text
        options: Verarbeitungsoptionen

    Returns:
        Dict mit korrigiertem Text und Metadaten
    """
    return get_german_postprocessor().postprocess(text, options)
