# -*- coding: utf-8 -*-
"""
Umlaut-Validierungs-Service für Ablage-System OCR.

Spezialisiert auf deutsche Umlaute (ae, oe, ue, ss) mit:
- Automatische Erkennung von Umlaut-Fehlern
- Woerterbuch-basierte Korrektur
- Konsistenzprüfung zwischen Ground Truth und OCR-Output
- CER/WER-Berechnung mit Umlaut-Fokus

Ziel: 100% Umlaut-Genauigkeit für deutsche Dokumente.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum
import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Types und Enums
# =============================================================================

class UmlautType(str, Enum):
    """Typ des Umlaut-Fehlers."""
    AE_TO_A = "ae_to_a"  # ae wurde als a erkannt
    OE_TO_O = "oe_to_o"  # oe wurde als o erkannt
    UE_TO_U = "ue_to_u"  # ue wurde als u erkannt
    SS_TO_S = "ss_to_s"  # ss wurde als s erkannt (Eszett)
    A_TO_AE = "a_to_ae"  # a wurde faelschlicherweise als ae erkannt
    O_TO_OE = "o_to_oe"
    U_TO_UE = "u_to_ue"
    DIGRAPH_SPLIT = "digraph_split"  # ae wurde als a-e getrennt


@dataclass
class UmlautSuggestion:
    """Vorschlag für eine Umlaut-Korrektur."""
    original: str
    suggested: str
    position: int
    context: str
    umlaut_type: UmlautType
    confidence: float = 1.0
    word_context: str = ""


@dataclass
class UmlautValidationResult:
    """Ergebnis der Umlaut-Validierung."""
    text: str
    suggestions: List[UmlautSuggestion] = field(default_factory=list)
    umlaut_accuracy: float = 1.0
    total_umlauts_expected: int = 0
    total_umlauts_found: int = 0
    missing_umlauts: List[str] = field(default_factory=list)
    extra_umlauts: List[str] = field(default_factory=list)
    corrected_text: Optional[str] = None


# =============================================================================
# Deutsche Woerterbuecher
# =============================================================================

# Bekannte deutsche Woerter mit Umlauten
# Format: {falsche_schreibweise: korrekte_schreibweise}
KNOWN_UMLAUT_WORDS: Dict[str, str] = {
    # Häufige Woerter mit ae
    "für": "für",
    "über": "über",
    "während": "während",
    "nächste": "nächste",
    "nächsten": "nächsten",
    "später": "später",
    "ändern": "ändern",
    "änderung": "Änderung",
    "änderungen": "Änderungen",
    "ähnlich": "ähnlich",
    "ärger": "Ärger",
    "aerzte": "Aerzte",
    "aerztin": "Aerztin",
    "länger": "länger",
    "stärker": "stärker",
    "waerme": "Waerme",
    "jährlich": "jährlich",
    "maerz": "Maerz",
    "maennlich": "maennlich",
    "schaeden": "Schaeden",
    "kraefter": "Kraefte",
    "erklärung": "Erklärung",
    "gerät": "Gerät",
    "geräte": "Geräte",
    "fähig": "fähig",
    "fähigkeit": "Fähigkeit",
    "gefaehrlich": "gefaehrlich",
    "ungefaehr": "ungefaehr",
    "sämtliche": "sämtliche",
    "tätigkeit": "Tätigkeit",
    "täglich": "täglich",
    "zusätzlich": "zusätzlich",
    "massnahme": "Massnahme",
    "massnahmen": "Massnahmen",

    # Häufige Woerter mit oe
    "können": "können",
    "könnte": "könnte",
    "moechten": "moechten",
    "moechte": "moechte",
    "möglich": "möglich",
    "möglichkeit": "Möglichkeit",
    "möglicherweise": "möglicherweise",
    "öffnen": "öffnen",
    "öffnung": "Öffnung",
    "öffentlich": "öffentlich",
    "oekonomisch": "oekonomisch",
    "hoechste": "hoechste",
    "hoechstens": "hoechstens",
    "hoeren": "hoeren",
    "gehoeren": "gehoeren",
    "behoerde": "Behoerde",
    "behoerden": "Behoerden",
    "größe": "Größe",
    "größte": "größte",
    "erhöhen": "erhöhen",
    "stoeren": "stoeren",
    "störung": "Störung",
    "koerper": "Koerper",
    "woertlich": "woertlich",
    "foerdern": "foerdern",
    "foerderung": "Foerderung",
    "loesen": "loesen",
    "loesung": "Loesung",
    "löschen": "löschen",
    "noetigen": "noetigen",
    "noetig": "noetig",

    # Häufige Woerter mit ue
    "müssen": "müssen",
    "müsste": "müsste",
    "wünschen": "wünschen",
    "wuerden": "wuerden",
    "wuerde": "wuerde",
    "zurück": "zurück",
    "verfügbar": "verfügbar",
    "verfügen": "verfügen",
    "überall": "überall",
    "ueblich": "ueblich",
    "üblicherweise": "üblicherweise",
    "übernehmen": "übernehmen",
    "übernahme": "Übernahme",
    "überprüfen": "überprüfen",
    "überprüfung": "Überprüfung",
    "übertragen": "übertragen",
    "übertragung": "Übertragung",
    "überweisen": "überweisen",
    "überweisung": "Überweisung",
    "führen": "führen",
    "führung": "Führung",
    "ausführen": "ausführen",
    "durchführen": "durchführen",
    "einführen": "einführen",
    "gruende": "Gruende",
    "gruendlich": "gruendlich",
    "prüfung": "Prüfung",
    "prüfen": "prüfen",
    "gebühr": "Gebühr",
    "gebühren": "Gebühren",
    "günstig": "günstig",
    "günstiger": "günstiger",
    "gültig": "gültig",
    "gültigkeit": "Gültigkeit",
    "kündigen": "kündigen",
    "kündigung": "Kündigung",
    "kürzlich": "kürzlich",
    "nützlich": "nützlich",
    "stück": "Stück",
    "stuetzen": "stuetzen",
    "unterstützen": "unterstützen",
    "unterstützung": "Unterstützung",

    # Woerter mit ss (Eszett)
    "strasse": "Strasse",
    "strassen": "Strassen",
    "schließen": "schließen",
    "abschließen": "abschließen",
    "anschließend": "anschließend",
    "ausschließlich": "ausschließlich",
    "bestätigen": "bestätigen",
    "bestätigung": "Bestätigung",
    "größe": "Größe",
    "größen": "Größen",
    "gruss": "Gruss",
    "gruesse": "Gruesse",
    "ermaessigung": "Ermaessigung",
    "massgeblich": "massgeblich",
    "regelmassig": "regelmäßig",
    "spass": "Spass",
    "wissen": "wissen",  # bleibt ss
    "gewiss": "gewiss",
    "gewissheit": "Gewissheit",
}

# Woerter die KEINE Umlaute haben (False Positives vermeiden)
NON_UMLAUT_WORDS: Set[str] = {
    "haben", "werden", "sollen", "wollen", "konnen",  # Ohne Umlaute
    "uber", "fur", "durch", "nach", "unter",  # Praepositions-Varianten
    "user", "super", "computer", "server",  # Anglizismen
    "euro", "europa", "europaeisch",
    "auto", "automatisch",
}


# =============================================================================
# Service-Klasse
# =============================================================================

class UmlautValidationService:
    """
    Service für die Validierung und Korrektur deutscher Umlaute.

    Features:
    - Automatische Erkennung von Umlaut-Fehlern
    - Woerterbuch-basierte Korrekturvorschläge
    - Konsistenzprüfung zwischen Texten
    - Statistische Auswertung der Umlaut-Genauigkeit
    """

    def __init__(self):
        """Initialisiere den Umlaut-Validierungs-Service."""
        self.known_words = KNOWN_UMLAUT_WORDS
        self.non_umlaut_words = NON_UMLAUT_WORDS
        logger.info(
            "umlaut_validation_service_initialized",
            known_words=len(self.known_words),
        )

    def detect_potential_umlaut_errors(
        self,
        text: str,
    ) -> List[UmlautSuggestion]:
        """
        Erkennt potentielle Umlaut-Fehler in einem Text.

        Args:
            text: Zu prüfender Text

        Returns:
            Liste von Korrekturvorschlägen
        """
        suggestions: List[UmlautSuggestion] = []
        text_lower = text.lower()

        # Suche nach bekannten Woertern ohne Umlaute
        for wrong_spelling, correct_spelling in self.known_words.items():
            # Pattern für Wortgrenzen
            pattern = rf'\b{re.escape(wrong_spelling)}\b'

            for match in re.finditer(pattern, text_lower):
                position = match.start()
                original = text[position:position + len(wrong_spelling)]

                # Bestimme Umlaut-Typ
                umlaut_type = self._determine_umlaut_type(wrong_spelling, correct_spelling)

                # Kontext extrahieren
                context_start = max(0, position - 20)
                context_end = min(len(text), position + len(wrong_spelling) + 20)
                context = text[context_start:context_end]

                suggestions.append(UmlautSuggestion(
                    original=original,
                    suggested=correct_spelling,
                    position=position,
                    context=context,
                    umlaut_type=umlaut_type,
                    confidence=0.9,
                    word_context=self._get_word_context(text, position),
                ))

        return suggestions

    def auto_correct_umlauts(self, text: str) -> str:
        """
        Korrigiert automatisch Umlaut-Fehler in einem Text.

        Args:
            text: Zu korrigierender Text

        Returns:
            Korrigierter Text
        """
        corrected = text

        for wrong_spelling, correct_spelling in self.known_words.items():
            # Case-insensitive Ersetzung mit Beibehaltung der Gross/Kleinschreibung
            pattern = rf'\b{re.escape(wrong_spelling)}\b'

            def replace_preserve_case(match: re.Match) -> str:
                original = match.group(0)
                if original[0].isupper():
                    return correct_spelling.capitalize()
                return correct_spelling.lower()

            corrected = re.sub(pattern, replace_preserve_case, corrected, flags=re.IGNORECASE)

        return corrected

    def validate_umlaut_consistency(
        self,
        ground_truth: str,
        ocr_output: str,
    ) -> UmlautValidationResult:
        """
        Prüft die Konsistenz der Umlaute zwischen Ground Truth und OCR-Output.

        Args:
            ground_truth: Referenztext (korrekt)
            ocr_output: OCR-Ergebnis (zu prüfen)

        Returns:
            Validierungsergebnis mit Genauigkeitsmetriken
        """
        # Extrahiere alle Umlaute
        gt_umlauts = self._extract_umlauts(ground_truth)
        ocr_umlauts = self._extract_umlauts(ocr_output)

        # Zaehle Übereinstimmungen
        gt_umlaut_count = len(gt_umlauts)
        ocr_umlaut_count = len(ocr_umlauts)

        # Berechne Accuracy
        if gt_umlaut_count == 0:
            accuracy = 1.0 if ocr_umlaut_count == 0 else 0.0
        else:
            # Wortweise Vergleich
            gt_words = set(self._extract_umlaut_words(ground_truth))
            ocr_words = set(self._extract_umlaut_words(ocr_output))

            correct = len(gt_words & ocr_words)
            total = len(gt_words | ocr_words)
            accuracy = correct / total if total > 0 else 1.0

        # Fehlende und überzaehlige Umlaute
        missing = list(set(gt_umlauts) - set(ocr_umlauts))
        extra = list(set(ocr_umlauts) - set(gt_umlauts))

        # Korrekturvorschläge
        suggestions = self.detect_potential_umlaut_errors(ocr_output)

        return UmlautValidationResult(
            text=ocr_output,
            suggestions=suggestions,
            umlaut_accuracy=accuracy,
            total_umlauts_expected=gt_umlaut_count,
            total_umlauts_found=ocr_umlaut_count,
            missing_umlauts=missing,
            extra_umlauts=extra,
            corrected_text=self.auto_correct_umlauts(ocr_output) if suggestions else None,
        )

    def calculate_umlaut_cer(
        self,
        ground_truth: str,
        ocr_output: str,
    ) -> float:
        """
        Berechnet die Character Error Rate nur für Umlaut-Zeichen.

        Args:
            ground_truth: Referenztext
            ocr_output: OCR-Ergebnis

        Returns:
            Umlaut-spezifische CER (0.0 = perfekt, 1.0 = alle falsch)
        """
        # Extrahiere nur Umlaut-Positionen und vergleiche
        gt_umlauts = self._extract_umlaut_positions(ground_truth)
        ocr_umlauts = self._extract_umlaut_positions(ocr_output)

        if not gt_umlauts:
            return 0.0 if not ocr_umlauts else 1.0

        # Levenshtein für Umlaut-Sequenz
        gt_sequence = "".join([c for _, c in gt_umlauts])
        ocr_sequence = "".join([c for _, c in ocr_umlauts])

        distance = self._levenshtein_distance(gt_sequence, ocr_sequence)
        max_len = max(len(gt_sequence), len(ocr_sequence))

        return distance / max_len if max_len > 0 else 0.0

    def validate_text(self, text: str) -> UmlautValidationResult:
        """
        Validiert einen einzelnen Text auf Umlaut-Qualität.

        Im Gegensatz zu validate_umlaut_consistency() erfordert diese
        Methode keinen Ground-Truth-Vergleich, sondern prüft nur
        den Text selbst auf potentielle Umlaut-Probleme.

        Args:
            text: Zu prüfender Text

        Returns:
            UmlautValidationResult mit Fehlerhinweisen und Korrekturvorschlägen
        """
        # Erkenne potentielle Fehler
        suggestions = self.detect_potential_umlaut_errors(text)

        # Zaehle Umlaute im Text
        umlauts_found = self._extract_umlauts(text)
        umlaut_count = len(umlauts_found)

        # Berechne eine Schätzung der Genauigkeit basierend auf Fehlern
        # Wenn keine Vorschläge, ist der Text wahrscheinlich korrekt
        if umlaut_count == 0:
            accuracy = 1.0  # Kein Umlaut = keine Fehler möglich
        elif len(suggestions) == 0:
            accuracy = 1.0  # Umlaute vorhanden, keine Fehler erkannt
        else:
            # Fehlerrate basierend auf gefundenen Problemen
            error_rate = len(suggestions) / max(umlaut_count, len(suggestions))
            accuracy = max(0.0, 1.0 - error_rate)

        # Korrigierte Version erstellen falls noetig
        corrected_text = self.auto_correct_umlauts(text) if suggestions else None

        return UmlautValidationResult(
            text=text,
            suggestions=suggestions,
            umlaut_accuracy=accuracy,
            total_umlauts_expected=umlaut_count + len(suggestions),  # Schätzung
            total_umlauts_found=umlaut_count,
            missing_umlauts=[s.suggested for s in suggestions],  # Was fehlt
            extra_umlauts=[],  # Ohne Ground Truth nicht bestimmbar
            corrected_text=corrected_text,
        )

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def _determine_umlaut_type(
        self,
        wrong: str,
        correct: str,
    ) -> UmlautType:
        """Bestimmt den Typ des Umlaut-Fehlers."""
        if "ae" in correct and "ae" not in wrong:
            return UmlautType.AE_TO_A
        elif "oe" in correct and "oe" not in wrong:
            return UmlautType.OE_TO_O
        elif "ue" in correct and "ue" not in wrong:
            return UmlautType.UE_TO_U
        elif "ss" in correct:
            return UmlautType.SS_TO_S
        return UmlautType.DIGRAPH_SPLIT

    def _get_word_context(self, text: str, position: int) -> str:
        """Extrahiert das umgebende Wort."""
        # Finde Wortgrenzen
        start = position
        while start > 0 and text[start - 1].isalnum():
            start -= 1

        end = position
        while end < len(text) and text[end].isalnum():
            end += 1

        return text[start:end]

    def _extract_umlauts(self, text: str) -> List[str]:
        """Extrahiert alle Umlaute aus einem Text."""
        umlauts = []
        umlaut_chars = set('aeoeuessAEOEUESS')

        # Suche nach ae, oe, ue, ss
        for pattern in ['ae', 'oe', 'ue', 'ss', 'Ae', 'Oe', 'Ue', 'AE', 'OE', 'UE', 'SS']:
            umlauts.extend(re.findall(pattern, text))

        return umlauts

    def _extract_umlaut_positions(self, text: str) -> List[Tuple[int, str]]:
        """Extrahiert Umlaute mit ihren Positionen."""
        positions = []

        for pattern in ['ae', 'oe', 'ue', 'ss']:
            for match in re.finditer(pattern, text.lower()):
                positions.append((match.start(), match.group()))

        return sorted(positions, key=lambda x: x[0])

    def _extract_umlaut_words(self, text: str) -> List[str]:
        """Extrahiert Woerter die Umlaute enthalten."""
        words = re.findall(r'\b\w+\b', text.lower())
        umlaut_words = []

        for word in words:
            if any(u in word for u in ['ae', 'oe', 'ue', 'ss']):
                umlaut_words.append(word)

        return umlaut_words

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Berechnet die Levenshtein-Distanz zwischen zwei Strings."""
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


# =============================================================================
# Singleton und Factory
# =============================================================================

_service_instance: Optional[UmlautValidationService] = None


def get_umlaut_validation_service() -> UmlautValidationService:
    """Gibt die Singleton-Instanz des Services zurück."""
    global _service_instance
    if _service_instance is None:
        _service_instance = UmlautValidationService()
    return _service_instance
