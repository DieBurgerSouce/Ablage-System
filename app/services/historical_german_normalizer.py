# -*- coding: utf-8 -*-
"""
Historical German Text Normalizer.

Ermöglicht:
- Normalisierung historischer deutscher Rechtschreibung
- Pre-1996-Reform (daß -> dass)
- 19. Jahrhundert Schreibweisen (Thür -> Tür)
- Fraktur-spezifische Zeichen (ſ -> s)
- C/K/Z-Varianten aus älteren Texten

Feinpoliert und durchdacht - Historische Texte modern lesbar machen.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class NormalizationEra(str, Enum):
    """Historische Periode für Normalisierung."""
    MODERN = "modern"           # Nach 1996
    PRE_1996 = "pre_1996"       # 1901-1996
    IMPERIAL = "imperial"       # 1871-1901
    NINETEENTH = "nineteenth"   # 1800-1871
    FRAKTUR = "fraktur"         # Fraktur-spezifisch


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class NormalizationResult:
    """Ergebnis einer Normalisierung."""
    original: str
    normalized: str
    changes: List[Tuple[str, str, int]]  # (old, new, position)
    era_detected: Optional[NormalizationEra]
    confidence: float

    @property
    def was_changed(self) -> bool:
        """Wurde Text geändert?"""
        return self.original != self.normalized

    @property
    def change_count(self) -> int:
        """Anzahl der Änderungen."""
        return len(self.changes)


# =============================================================================
# Historical German Normalizer
# =============================================================================


class HistoricalGermanNormalizer:
    """
    Normalisierer für historische deutsche Rechtschreibung.

    Behandelt:
    - Pre-1996 Reform: daß -> dass, muß -> muss
    - 19. Jahrhundert: Th -> T, C -> K/Z, ph -> f
    - Fraktur: ſ (langes s) -> s, ꝛ -> r
    - Regionale Varianten
    """

    # Pre-1996 ß/ss Mappings (nach langen Vokalen bleibt ß)
    PRE_1996_MAPPINGS: Dict[str, str] = {
        "daß": "dass",
        "muß": "muss",
        "müßte": "müsste",
        "müßten": "müssten",
        "wußte": "wusste",
        "wußten": "wussten",
        "bewußt": "bewusst",
        "unbewußt": "unbewusst",
        "Bewußtsein": "Bewusstsein",
        "faßt": "fasst",
        "gefaßt": "gefasst",
        "paßt": "passt",
        "gepaßt": "gepasst",
        "Faß": "Fass",
        "Fäßchen": "Fässchen",
        "Schloß": "Schloss",
        "Schlößchen": "Schlösschen",
        "Fluß": "Fluss",
        "Flüsse": "Flüsse",  # bleibt
        "Flußlauf": "Flusslauf",
        "Kuß": "Kuss",
        "Küsse": "Küsse",  # bleibt
        "Nuß": "Nuss",
        "Nüsse": "Nüsse",  # bleibt
        "Haß": "Hass",
        "häßlich": "hässlich",
        "Nässe": "Nässe",  # bleibt (nach kurzem Vokal)
        "naß": "nass",
        "blaß": "blass",
        "Baß": "Bass",
        "Biß": "Biss",
        "Genuß": "Genuss",
        "Verdruß": "Verdruss",
        "Abriß": "Abriss",
        "Aufriß": "Aufriss",
        "Einriß": "Einriss",
        "Grundriß": "Grundriss",
        "Riß": "Riss",
        "Mißbrauch": "Missbrauch",
        "mißbrauchen": "missbrauchen",
        "Mißerfolg": "Misserfolg",
        "mißlingen": "misslingen",
        "Mißverständnis": "Missverständnis",
        "mißverstehen": "missverstehen",
        "Kompromiß": "Kompromiss",
        "Ergebniß": "Ergebnis",
        "Ereigniß": "Ereignis",
        "Erlaubniß": "Erlaubnis",
        "Gefängniß": "Gefängnis",
        "Verhältniß": "Verhältnis",
        "Zeugniß": "Zeugnis",
    }

    # 19. Jahrhundert Th -> T Mappings
    TH_MAPPINGS: Dict[str, str] = {
        "Thür": "Tür",
        "Thüre": "Türe",
        "Thor": "Tor",
        "Thore": "Tore",
        "Theil": "Teil",
        "Theile": "Teile",
        "theilen": "teilen",
        "Thier": "Tier",
        "Thiere": "Tiere",
        "Thal": "Tal",
        "Thale": "Tale",
        "Thaler": "Taler",
        "Thon": "Ton",
        "Thräne": "Träne",
        "Thränen": "Tränen",
        "Thron": "Thron",  # bleibt (griechisch)
        "thun": "tun",
        "that": "tat",
        "gethan": "getan",
        "Unterthan": "Untertan",
        "Thatsache": "Tatsache",
        "Muth": "Mut",
        "muthig": "mutig",
        "Wuth": "Wut",
        "wüthend": "wütend",
        "Rath": "Rat",
        "Räthe": "Räte",
        "rathen": "raten",
        "Noth": "Not",
        "Nöthe": "Nöte",
        "nöthig": "nötig",
        "Werth": "Wert",
        "Werthe": "Werte",
        "werthvoll": "wertvoll",
    }

    # C -> K/Z Mappings
    C_MAPPINGS: Dict[str, str] = {
        "Curs": "Kurs",
        "Curse": "Kurse",
        "Circus": "Zirkus",
        "Conto": "Konto",
        "Conten": "Konten",
        "Credit": "Kredit",
        "Credite": "Kredite",
        "Caffee": "Kaffee",
        "Classe": "Klasse",
        "Classen": "Klassen",
        "Cultur": "Kultur",
        "Comfort": "Komfort",
        "Commission": "Kommission",
        "Comité": "Komitee",
        "Compagnie": "Kompanie",
        "Concert": "Konzert",
        "Concerte": "Konzerte",
        "Contrakt": "Kontrakt",
        "Copie": "Kopie",
        "Copien": "Kopien",
        "Corps": "Korps",
        "Correspondent": "Korrespondent",
        "Correspondenz": "Korrespondenz",
        "Coupon": "Kupon",
        "Coupons": "Kupons",
    }

    # ph -> f Mappings
    PH_MAPPINGS: Dict[str, str] = {
        "Telephon": "Telefon",
        "Telephone": "Telefone",
        "telephonieren": "telefonieren",
        "Photographie": "Fotografie",
        "Photograph": "Fotograf",
        "Photographen": "Fotografen",
        "photographieren": "fotografieren",
        "Phantasie": "Fantasie",  # auch Phantasie ist korrekt
        "Delphin": "Delfin",
        "Delphine": "Delfine",
        "Graphik": "Grafik",
        "graphisch": "grafisch",
        "Geographie": "Geografie",
        "geographisch": "geografisch",
        "Orthographie": "Orthografie",
        "orthographisch": "orthografisch",
        "Biographie": "Biografie",
        "biographisch": "biografisch",
    }

    # Fraktur-spezifische Zeichen
    FRAKTUR_CHARS: Dict[str, str] = {
        "\u017f": "s",     # ſ (langes s)
        "\u1e9e": "ß",     # ẞ (großes ß)
        "\ua75b": "r",     # ꝛ (r rotunda)
        "\ua75d": "v",     # Fraktur v
        "\u0292": "z",     # ʒ (Ezh, als z verwendet)
    }

    # Wörter die NICHT normalisiert werden sollen
    PRESERVE_WORDS: FrozenSet[str] = frozenset([
        "Goethe",
        "Beethoven",
        "Schopenhauer",
        "Nietzsche",
        "Gymnasium",  # Griechisch
        "Philosophie",
        "Theater",
        "Thema",
        "Theorie",
        "Therapie",
        "These",
        "Apotheke",
        "Mathematik",
        "Rhythmus",
        "Rhetorik",
        "Rhein",
        "Rheinland",
    ])

    def __init__(
        self,
        enable_pre_1996: bool = True,
        enable_th_normalization: bool = True,
        enable_c_normalization: bool = True,
        enable_ph_normalization: bool = True,
        enable_fraktur: bool = True,
    ) -> None:
        """
        Initialisiere Historical Normalizer.

        Args:
            enable_pre_1996: Pre-1996 ß/ss Normalisierung
            enable_th_normalization: Th->T Normalisierung
            enable_c_normalization: C->K/Z Normalisierung
            enable_ph_normalization: ph->f Normalisierung
            enable_fraktur: Fraktur-Zeichen Normalisierung
        """
        self.enable_pre_1996 = enable_pre_1996
        self.enable_th_normalization = enable_th_normalization
        self.enable_c_normalization = enable_c_normalization
        self.enable_ph_normalization = enable_ph_normalization
        self.enable_fraktur = enable_fraktur

        # Kombinierte Mappings erstellen
        self._build_combined_mappings()

        logger.debug(
            "HistoricalGermanNormalizer initialisiert",
            mappings_count=len(self._all_mappings),
        )

    def _build_combined_mappings(self) -> None:
        """Erstelle kombiniertes Mapping-Dictionary."""
        self._all_mappings: Dict[str, str] = {}

        if self.enable_pre_1996:
            self._all_mappings.update(self.PRE_1996_MAPPINGS)

        if self.enable_th_normalization:
            self._all_mappings.update(self.TH_MAPPINGS)

        if self.enable_c_normalization:
            self._all_mappings.update(self.C_MAPPINGS)

        if self.enable_ph_normalization:
            self._all_mappings.update(self.PH_MAPPINGS)

        # Lowercase-Version für case-insensitive Matching
        self._mappings_lower: Dict[str, Tuple[str, str]] = {
            k.lower(): (k, v) for k, v in self._all_mappings.items()
        }

    def normalize(self, text: str) -> NormalizationResult:
        """
        Normalisiere historischen deutschen Text.

        Args:
            text: Der zu normalisierende Text

        Returns:
            NormalizationResult mit Details
        """
        if not text:
            return NormalizationResult(
                original=text,
                normalized=text,
                changes=[],
                era_detected=None,
                confidence=1.0,
            )

        changes: List[Tuple[str, str, int]] = []
        result = text

        # Fraktur-Zeichen zuerst
        if self.enable_fraktur:
            for old_char, new_char in self.FRAKTUR_CHARS.items():
                pos = 0
                while pos < len(result):
                    idx = result.find(old_char, pos)
                    if idx == -1:
                        break
                    changes.append((old_char, new_char, idx))
                    result = result[:idx] + new_char + result[idx + 1:]
                    pos = idx + 1

        # Wort-basierte Normalisierung
        words = self._tokenize_with_positions(result)

        for word, start_pos in words:
            if word.lower() in (p.lower() for p in self.PRESERVE_WORDS):
                continue

            word_lower = word.lower()
            if word_lower in self._mappings_lower:
                original_case, normalized = self._mappings_lower[word_lower]

                # Case-Preserving Replacement
                if word[0].isupper() and not normalized[0].isupper():
                    normalized = normalized.capitalize()
                elif word.isupper():
                    normalized = normalized.upper()

                if word != normalized:
                    changes.append((word, normalized, start_pos))
                    result = result[:start_pos] + normalized + result[start_pos + len(word):]

        # Era Detection
        era_detected = self._detect_era(text)

        # Confidence basierend auf Änderungen
        if not changes:
            confidence = 1.0
        else:
            # Mehr Änderungen = höheres Vertrauen in die Erkennung
            confidence = min(0.95, 0.7 + len(changes) * 0.05)

        return NormalizationResult(
            original=text,
            normalized=result,
            changes=changes,
            era_detected=era_detected,
            confidence=confidence,
        )

    def _tokenize_with_positions(self, text: str) -> List[Tuple[str, int]]:
        """Tokenisiere Text mit Positionsangaben."""
        words = []
        current_word = ""
        current_start = 0

        for i, char in enumerate(text):
            if char.isalpha() or char in "äöüÄÖÜß":
                if not current_word:
                    current_start = i
                current_word += char
            else:
                if current_word:
                    words.append((current_word, current_start))
                    current_word = ""

        if current_word:
            words.append((current_word, current_start))

        return words

    def _detect_era(self, text: str) -> Optional[NormalizationEra]:
        """Erkenne historische Periode anhand von Textmerkmalen."""
        text_lower = text.lower()

        # Fraktur-Zeichen?
        if any(c in text for c in self.FRAKTUR_CHARS.keys()):
            return NormalizationEra.FRAKTUR

        # Th-Schreibweisen?
        th_indicators = ["thür", "thor", "theil", "thier", "thal", "thun", "muth", "rath"]
        if any(ind in text_lower for ind in th_indicators):
            return NormalizationEra.NINETEENTH

        # Pre-1996 ß?
        pre96_indicators = ["daß", "muß", "wußte", "bewußt", "schloß", "fluß"]
        if any(ind in text_lower for ind in pre96_indicators):
            return NormalizationEra.PRE_1996

        # C statt K/Z?
        c_indicators = ["circus", "conto", "credit", "classe", "cultur"]
        if any(ind in text_lower for ind in c_indicators):
            return NormalizationEra.IMPERIAL

        return NormalizationEra.MODERN

    def normalize_fraktur_only(self, text: str) -> str:
        """Normalisiere nur Fraktur-spezifische Zeichen."""
        result = text
        for old_char, new_char in self.FRAKTUR_CHARS.items():
            result = result.replace(old_char, new_char)
        return result

    def is_historical(self, text: str) -> bool:
        """Prüfe ob Text historische Schreibweisen enthält."""
        era = self._detect_era(text)
        return era not in (NormalizationEra.MODERN, None)


# =============================================================================
# Singleton
# =============================================================================

_historical_normalizer: Optional[HistoricalGermanNormalizer] = None


def get_historical_normalizer() -> HistoricalGermanNormalizer:
    """Hole globale HistoricalGermanNormalizer-Instanz."""
    global _historical_normalizer
    if _historical_normalizer is None:
        _historical_normalizer = HistoricalGermanNormalizer()
        logger.info("HistoricalGermanNormalizer initialisiert")
    return _historical_normalizer


# =============================================================================
# Convenience Functions
# =============================================================================


def normalize_historical(text: str) -> NormalizationResult:
    """Normalisiere historischen deutschen Text."""
    return get_historical_normalizer().normalize(text)


def normalize_fraktur(text: str) -> str:
    """Normalisiere Fraktur-Zeichen."""
    return get_historical_normalizer().normalize_fraktur_only(text)


def is_historical_text(text: str) -> bool:
    """Prüfe ob Text historische Schreibweisen enthält."""
    return get_historical_normalizer().is_historical(text)
