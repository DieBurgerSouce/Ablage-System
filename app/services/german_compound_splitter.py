# -*- coding: utf-8 -*-
"""
German Compound Word Splitter Service.

Ermöglicht:
- Zerlegung deutscher Komposita in Einzelteile
- Erkennung von Fugenelementen (s, es, n, en, er)
- Suchoptimierung durch Indexierung aller Bestandteile
- Validierung von Komposita-Strukturen

Feinpoliert und durchdacht - Linguistisch korrekte Kompositazerlegung.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CompoundSplit:
    """Ergebnis einer Komposita-Zerlegung."""
    original: str
    parts: List[str]
    fugen_elements: List[str]
    is_compound: bool
    confidence: float  # 0-1
    base_words: List[str]  # Grundformen ohne Fugenelemente

    def __repr__(self) -> str:
        if not self.is_compound:
            return f"<CompoundSplit '{self.original}' (kein Kompositum)>"
        parts_str = " + ".join(self.parts)
        return f"<CompoundSplit '{self.original}' -> [{parts_str}]>"


# =============================================================================
# German Compound Splitter
# =============================================================================


class GermanCompoundSplitter:
    """
    Fortgeschrittener deutscher Komposita-Zerteiler.

    Verwendet:
    - Umfangreiche deutsche Wortstamm-Datenbank
    - Fugenelement-Erkennung (s, es, n, en, er)
    - Rekursive Zerlegung für Mehrfach-Komposita
    - Validierung durch Wörterbuch-Lookup
    """

    # Fugenelemente und ihre häufigsten Kontexte
    FUGENELEMENTE: Dict[str, List[str]] = {
        "s": [
            "Arbeit", "Beruf", "Bund", "Dienst", "Ding", "Einheit",
            "Freiheit", "Geburt", "Geschäft", "Gesundheit", "Glück",
            "Handlung", "Hoffnung", "Kenntnis", "König", "Lebens",
            "Liebe", "Macht", "Ordnung", "Prüfung", "Qualität",
            "Recht", "Regierung", "Sicherheit", "Steuer", "Umwelt",
            "Verkehr", "Versicherung", "Verwaltung", "Wirtschaft",
            "Wohnung", "Zeit",
        ],
        "es": [
            "Bund", "Land", "Tag", "Jahr", "Kind",
        ],
        "n": [
            "Auge", "Bote", "Ende", "Erbe", "Hase", "Name",
            "Schule", "Seite", "Sonne", "Woche",
        ],
        "en": [
            "Blume", "Firma", "Frau", "Straße", "Tasche", "Zeitung",
            "Arbeit", "Einheit", "Mehrheit", "Minderheit",
        ],
        "er": [
            "Bild", "Buch", "Ei", "Feld", "Geld", "Geist",
            "Gut", "Kind", "Land", "Licht", "Rad", "Rind", "Volk",
        ],
        "e": [
            "Hund", "Maus", "Schwein", "Tag",
        ],
    }

    # Bekannte deutsche Basiswörter (erweiterte Liste)
    # Diese Liste sollte in Produktion durch eine echte Wörterbuch-Datenbank ersetzt werden
    GERMAN_BASE_WORDS: FrozenSet[str] = frozenset([
        # Substantive - Allgemein
        "Arbeit", "Auto", "Bahn", "Bank", "Bau", "Baum", "Berg", "Bild",
        "Blatt", "Blume", "Brot", "Buch", "Bund", "Büro", "Dach", "Dienst",
        "Dorf", "Ende", "Erde", "Fahrt", "Fall", "Familie", "Farbe", "Feld",
        "Feuer", "Film", "Fisch", "Fluß", "Frage", "Frau", "Freund", "Garten",
        "Gast", "Gebäude", "Geld", "Geschichte", "Gesetz", "Gesicht", "Gespräch",
        "Glas", "Glück", "Gott", "Grenze", "Grund", "Gruppe", "Hand", "Haus",
        "Herr", "Herz", "Himmel", "Hof", "Holz", "Jahr", "Kind", "Kirche",
        "Klasse", "Kopf", "Kraft", "Krieg", "Kunst", "Land", "Leben", "Lehrer",
        "Leute", "Licht", "Liebe", "Luft", "Mann", "Markt", "Meer", "Meister",
        "Mensch", "Mitte", "Monat", "Morgen", "Mutter", "Nacht", "Name", "Natur",
        "Ort", "Papier", "Partei", "Platz", "Politik", "Post", "Preis", "Problem",
        "Punkt", "Rat", "Raum", "Recht", "Regen", "Rest", "Rolle", "Sache",
        "Schiff", "Schule", "Seite", "Sinn", "Sohn", "Sonne", "Sorge", "Spiel",
        "Sport", "Sprache", "Staat", "Stadt", "Stelle", "Stimme", "Stock",
        "Straße", "Stück", "Student", "Stunde", "System", "Tag", "Teil", "Text",
        "Tier", "Tisch", "Tochter", "Tod", "Tor", "Tür", "Uhr", "Vater",
        "Verein", "Verkehr", "Volk", "Wahl", "Wald", "Wand", "Wasser", "Weg",
        "Welt", "Werk", "Wert", "Wetter", "Woche", "Wohnung", "Wort", "Zeit",
        "Zeitung", "Ziel", "Zimmer", "Zug", "Zukunft",

        # Substantive - Geschäft/Recht
        "Amt", "Antrag", "Auftrag", "Bereich", "Betrag", "Betrieb", "Beweis",
        "Bezirk", "Dokument", "Erfolg", "Ergebnis", "Firma", "Geschäft",
        "Gewinn", "Handel", "Kauf", "Kosten", "Kunde", "Leistung", "Lieferung",
        "Nummer", "Prüfung", "Rechnung", "Steuer", "Termin", "Umsatz", "Vertrag",
        "Verwaltung", "Vorgang", "Zahlung",

        # Substantive - Technik/Computer
        "Anlage", "Datei", "Daten", "Entwicklung", "Gerät", "Information",
        "Lösung", "Maschine", "Netz", "Programm", "Rechner", "Software",
        "Speicher", "Technik", "Verfahren",

        # Abstrakta
        "Änderung", "Bedeutung", "Bewegung", "Bildung", "Druck", "Einheit",
        "Einrichtung", "Entscheidung", "Erfahrung", "Erklärung", "Form",
        "Freiheit", "Gefahr", "Gefühl", "Gesundheit", "Gewalt", "Hilfe",
        "Hoffnung", "Idee", "Interesse", "Kenntnis", "Möglichkeit", "Ordnung",
        "Pflicht", "Plan", "Qualität", "Regel", "Ruhe", "Schutz", "Sicherheit",
        "Unterschied", "Ursache", "Verantwortung", "Verbindung", "Versuch",
        "Verwendung", "Vorstellung", "Wahrheit", "Wirkung", "Wissenschaft",
        "Zahl", "Zustand",

        # Verben als Substantive (Nominalisierungen)
        "Führung", "Handlung", "Haltung", "Leitung", "Meinung", "Richtung",
        "Sammlung", "Sendung", "Sicherung", "Stellung", "Versicherung",
        "Warnung", "Werbung", "Zahlung", "Zeitung",

        # Adjektive als Basis
        "Frei", "Groß", "Haupt", "Klein", "Lang", "Neu", "Schnell", "Weit",

        # Zusammengesetzte Teile
        "Finanz", "Bundes", "Landes", "Volks", "Staats",

        # Fachbegriffe
        "Ministerium", "Gericht", "Behörde", "Institut", "Zentrum",
        "Gesellschaft", "Verband", "Stiftung", "Agentur",
    ])

    # Minimale Wortlänge für Bestandteile
    MIN_PART_LENGTH = 3

    def __init__(
        self,
        min_part_length: int = 3,
        custom_words: Optional[Set[str]] = None,
    ) -> None:
        """
        Initialisiere Compound Splitter.

        Args:
            min_part_length: Minimale Länge für Wortbestandteile
            custom_words: Zusätzliche Basiswörter
        """
        self.min_part_length = min_part_length

        # Kombiniere Basis- und benutzerdefinierte Wörter
        self._base_words: Set[str] = set(self.GERMAN_BASE_WORDS)
        if custom_words:
            self._base_words.update(custom_words)

        # Lowercase-Lookup für schnellere Suche
        self._base_words_lower: Set[str] = {w.lower() for w in self._base_words}

        logger.debug(
            "GermanCompoundSplitter initialisiert",
            base_words_count=len(self._base_words),
        )

    def split(self, word: str) -> CompoundSplit:
        """
        Zerlege ein deutsches Kompositum.

        Args:
            word: Das zu zerlegende Wort

        Returns:
            CompoundSplit mit Zerlegungsergebnis
        """
        if not word or len(word) < self.min_part_length * 2:
            return CompoundSplit(
                original=word,
                parts=[word] if word else [],
                fugen_elements=[],
                is_compound=False,
                confidence=1.0,
                base_words=[word] if word else [],
            )

        # Versuche rekursive Zerlegung
        result = self._recursive_split(word)

        if result:
            parts, fugen, confidence = result
            base_words = self._extract_base_words(parts, fugen)

            return CompoundSplit(
                original=word,
                parts=parts,
                fugen_elements=fugen,
                is_compound=len(parts) > 1,
                confidence=confidence,
                base_words=base_words,
            )

        return CompoundSplit(
            original=word,
            parts=[word],
            fugen_elements=[],
            is_compound=False,
            confidence=0.5,  # Unsicher
            base_words=[word],
        )

    def _recursive_split(
        self,
        word: str,
        depth: int = 0,
        max_depth: int = 4,
    ) -> Optional[Tuple[List[str], List[str], float]]:
        """
        Rekursive Komposita-Zerlegung.

        Returns:
            (parts, fugen_elements, confidence) oder None
        """
        if depth > max_depth:
            return None

        word_lower = word.lower()

        # Wenn das Wort selbst ein Basiswort ist, fertig
        if word_lower in self._base_words_lower:
            return ([word], [], 1.0)

        best_result: Optional[Tuple[List[str], List[str], float]] = None
        best_confidence = 0.0

        # Versuche verschiedene Trennpunkte
        for i in range(self.min_part_length, len(word) - self.min_part_length + 1):
            left = word[:i]
            right = word[i:]

            # Prüfe auf Fugenelement
            for fugen, _ in self.FUGENELEMENTE.items():
                if left.lower().endswith(fugen):
                    # Entferne Fugenelement vom linken Teil
                    left_base = left[:-len(fugen)]
                    if len(left_base) >= self.min_part_length:
                        if left_base.lower() in self._base_words_lower:
                            # Rekursiv den rechten Teil prüfen
                            right_result = self._recursive_split(right, depth + 1)
                            if right_result:
                                right_parts, right_fugen, right_conf = right_result
                                new_parts = [left_base + fugen] + right_parts
                                new_fugen = [fugen] + right_fugen
                                new_conf = min(0.9, right_conf * 0.95)

                                if new_conf > best_confidence:
                                    best_confidence = new_conf
                                    best_result = (new_parts, new_fugen, new_conf)

            # Prüfe ohne Fugenelement
            if left.lower() in self._base_words_lower:
                right_result = self._recursive_split(right, depth + 1)
                if right_result:
                    right_parts, right_fugen, right_conf = right_result
                    new_parts = [left] + right_parts
                    new_fugen = [""] + right_fugen
                    new_conf = right_conf * 0.9

                    if new_conf > best_confidence:
                        best_confidence = new_conf
                        best_result = (new_parts, new_fugen, new_conf)

        return best_result

    def _extract_base_words(
        self,
        parts: List[str],
        fugen: List[str],
    ) -> List[str]:
        """Extrahiere Grundformen ohne Fugenelemente."""
        base_words = []

        for i, part in enumerate(parts):
            if i < len(fugen) and fugen[i]:
                # Entferne Fugenelement
                base = part[:-len(fugen[i])] if part.endswith(fugen[i]) else part
            else:
                base = part
            base_words.append(base)

        return base_words

    def split_for_search(self, word: str) -> List[str]:
        """
        Zerlege Wort für Suchindexierung.

        Gibt alle suchbaren Bestandteile zurück:
        - Das Original-Wort
        - Alle Einzelteile
        - Grundformen ohne Fugenelemente

        Args:
            word: Das zu zerlegende Wort

        Returns:
            Liste aller suchbaren Begriffe
        """
        result = self.split(word)

        search_terms: Set[str] = {word.lower()}

        if result.is_compound:
            # Füge alle Teile hinzu
            for part in result.parts:
                search_terms.add(part.lower())

            # Füge Grundformen hinzu
            for base in result.base_words:
                search_terms.add(base.lower())

        return list(search_terms)

    def is_compound(self, word: str) -> bool:
        """
        Prüfe ob ein Wort ein Kompositum ist.

        Args:
            word: Das zu prüfende Wort

        Returns:
            True wenn Kompositum erkannt
        """
        result = self.split(word)
        return result.is_compound

    def validate_compound(self, word: str) -> Tuple[bool, float]:
        """
        Validiere ob ein Wort ein gültiges deutsches Kompositum ist.

        Args:
            word: Das zu validierende Wort

        Returns:
            (is_valid, confidence)
        """
        result = self.split(word)
        return (result.is_compound, result.confidence)

    def add_base_word(self, word: str) -> None:
        """Füge ein neues Basiswort hinzu."""
        self._base_words.add(word)
        self._base_words_lower.add(word.lower())

    def add_base_words(self, words: List[str]) -> None:
        """Füge mehrere Basiswörter hinzu."""
        for word in words:
            self.add_base_word(word)


# =============================================================================
# Singleton
# =============================================================================

_compound_splitter: Optional[GermanCompoundSplitter] = None


def get_compound_splitter() -> GermanCompoundSplitter:
    """Hole globale GermanCompoundSplitter-Instanz."""
    global _compound_splitter
    if _compound_splitter is None:
        _compound_splitter = GermanCompoundSplitter()
        logger.info("GermanCompoundSplitter initialisiert")
    return _compound_splitter


# =============================================================================
# Convenience Functions
# =============================================================================


def split_compound(word: str) -> CompoundSplit:
    """Zerlege ein deutsches Kompositum."""
    return get_compound_splitter().split(word)


def split_for_search(word: str) -> List[str]:
    """Zerlege Wort für Suchindexierung."""
    return get_compound_splitter().split_for_search(word)


def is_compound(word: str) -> bool:
    """Prüfe ob ein Wort ein Kompositum ist."""
    return get_compound_splitter().is_compound(word)


# =============================================================================
# Umlaut-Normalisierung für OCR-Fehlertoleranz
# =============================================================================


# Mapping für bidirektionale Umlaut-Expansion
UMLAUT_EXPANSIONS: Dict[str, List[str]] = {
    # Umlaute zu ASCII-Varianten (inkl. OCR-Fehler ohne Punkte)
    'ä': ['ä', 'ae', 'a'],
    'ö': ['ö', 'oe', 'o'],
    'ü': ['ü', 'ue', 'u'],
    'ß': ['ß', 'ss'],
    # Grossbuchstaben
    'Ä': ['Ä', 'Ae', 'AE', 'A'],
    'Ö': ['Ö', 'Oe', 'OE', 'O'],
    'Ü': ['Ü', 'Ue', 'UE', 'U'],
}

# Reverse-Mapping: ASCII-Digraphen zu Umlauten
DIGRAPH_TO_UMLAUT: Dict[str, str] = {
    'ae': 'ä', 'Ae': 'Ä', 'AE': 'Ä',
    'oe': 'ö', 'Oe': 'Ö', 'OE': 'Ö',
    'ue': 'ü', 'Ue': 'Ü', 'UE': 'Ü',
    'ss': 'ß',
}


def expand_umlaut_variants(word: str) -> List[str]:
    """Expandiert ein Wort mit möglichen Umlaut-Varianten.

    Behandelt OCR-Fehler, bei denen:
    - ä zu ae, a oder ä wird
    - ö zu oe, o oder ö wird
    - ü zu ue, u oder ü wird
    - ß zu ss wird

    Args:
        word: Eingabewort (kann Umlaute oder ASCII-Digraphen enthalten)

    Returns:
        Liste aller möglichen Varianten (inkl. Original)

    Example:
        >>> expand_umlaut_variants("Größe")
        ['größe', 'größe', 'grosse']
        >>> expand_umlaut_variants("Mueller")
        ['mueller', 'müller']
    """
    variants: Set[str] = {word.lower()}
    word_lower = word.lower()

    # 1. Forward: Umlaute zu ASCII-Varianten expandieren
    for umlaut, replacements in UMLAUT_EXPANSIONS.items():
        umlaut_lower = umlaut.lower()
        if umlaut_lower in word_lower:
            for replacement in replacements:
                replacement_lower = replacement.lower()
                if replacement_lower != umlaut_lower:
                    variant = word_lower.replace(umlaut_lower, replacement_lower)
                    variants.add(variant)

    # 2. Reverse: ASCII-Digraphen zu Umlauten expandieren
    for digraph, umlaut in DIGRAPH_TO_UMLAUT.items():
        digraph_lower = digraph.lower()
        if digraph_lower in word_lower:
            variant = word_lower.replace(digraph_lower, umlaut)
            variants.add(variant)

    result = list(variants)
    if len(result) > 1:
        logger.debug(
            "umlaut_expansion",
            original=word,
            variants=result[:5],  # Max 5 für Logging
            total_variants=len(result)
        )

    return result


def expand_query_with_umlauts(query: str) -> Tuple[str, List[str]]:
    """Expandiert eine Suchanfrage mit Umlaut-Varianten.

    Verarbeitet alle Woerter in der Query und generiert
    OR-verknüpfte Varianten für bessere OCR-Fehlertoleranz.

    Args:
        query: Originale Suchanfrage

    Returns:
        Tuple von (erweiterte_query, liste_zusätzlicher_terms)

    Example:
        >>> expand_query_with_umlauts("Größe Müller")
        ("Größe Müller größe grosse mueller müller", ["größe", "grosse", ...])
    """
    words = query.split()
    all_terms: Set[str] = set(words)
    additional_terms: List[str] = []

    for word in words:
        # Nur Woerter mit mind. 3 Zeichen expandieren
        if len(word) >= 3:
            variants = expand_umlaut_variants(word)
            for variant in variants:
                if variant not in {w.lower() for w in all_terms}:
                    all_terms.add(variant)
                    additional_terms.append(variant)

    if additional_terms:
        logger.debug(
            "query_umlaut_expansion",
            original=query,
            additional_terms=additional_terms[:10],
            total_additional=len(additional_terms)
        )
        # Erweiterte Query: Original + Varianten
        expanded_query = query + " " + " ".join(additional_terms[:15])  # Max 15 Zusatzterms
        return expanded_query, additional_terms

    return query, []
