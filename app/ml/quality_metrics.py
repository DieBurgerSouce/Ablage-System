# -*- coding: utf-8 -*-
"""
OCR Quality Metrics: CER, WER und deutsche Sprach-Metriken.

Ermöglicht:
- Character Error Rate (CER) Berechnung
- Word Error Rate (WER) Berechnung
- Deutsche Umlaut-Genauigkeit
- Levenshtein-Distanz mit Edit-Operationen
- Ground-Truth-Vergleich für Benchmarks

Feinpoliert und durchdacht - Datengetriebene Qualitätsmessung.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


class EditOperation(str, Enum):
    """Typ der Edit-Operation."""
    INSERTION = "insertion"
    DELETION = "deletion"
    SUBSTITUTION = "substitution"
    MATCH = "match"


@dataclass
class EditInfo:
    """Details zu einer Edit-Operation."""
    operation: EditOperation
    position: int
    reference_char: Optional[str] = None
    hypothesis_char: Optional[str] = None

    def __repr__(self) -> str:
        if self.operation == EditOperation.INSERTION:
            return f"+'{self.hypothesis_char}'@{self.position}"
        elif self.operation == EditOperation.DELETION:
            return f"-'{self.reference_char}'@{self.position}"
        elif self.operation == EditOperation.SUBSTITUTION:
            return f"'{self.reference_char}'->'{self.hypothesis_char}'@{self.position}"
        else:
            return f"='{self.reference_char}'@{self.position}"


@dataclass
class LevenshteinResult:
    """Ergebnis der Levenshtein-Distanz-Berechnung."""
    distance: int
    insertions: int
    deletions: int
    substitutions: int
    operations: List[EditInfo] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        """Gesamtzahl der Fehler."""
        return self.insertions + self.deletions + self.substitutions


@dataclass
class OCRQualityMetrics:
    """
    Vollständige OCR-Qualitätsmetriken.

    Attributes:
        cer: Character Error Rate (0-1, niedriger ist besser)
        wer: Word Error Rate (0-1, niedriger ist besser)
        char_accuracy: Zeichen-Genauigkeit (1 - CER)
        word_accuracy: Wort-Genauigkeit (1 - WER)
        levenshtein_distance: Rohe Edit-Distanz
        insertions: Anzahl der Einfügungen
        deletions: Anzahl der Löschungen
        substitutions: Anzahl der Ersetzungen
        umlaut_accuracy: Deutsche Umlaut-Genauigkeit (0-1)
        umlaut_errors: Details zu Umlaut-Fehlern
        capitalization_accuracy: Großschreibungs-Genauigkeit (0-1)
        reference_length: Länge des Referenztexts
        hypothesis_length: Länge des OCR-Outputs
    """
    cer: float
    wer: float
    char_accuracy: float
    word_accuracy: float
    levenshtein_distance: int
    insertions: int
    deletions: int
    substitutions: int

    # Deutsche Metriken
    umlaut_accuracy: float = 1.0
    umlaut_errors: List[str] = field(default_factory=list)
    capitalization_accuracy: float = 1.0

    # Längen
    reference_length: int = 0
    hypothesis_length: int = 0

    def to_dict(self) -> Dict[str, float]:
        """Konvertiere zu Dictionary für Serialisierung."""
        return {
            "cer": round(self.cer, 4),
            "wer": round(self.wer, 4),
            "char_accuracy": round(self.char_accuracy, 4),
            "word_accuracy": round(self.word_accuracy, 4),
            "levenshtein_distance": self.levenshtein_distance,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "substitutions": self.substitutions,
            "umlaut_accuracy": round(self.umlaut_accuracy, 4),
            "capitalization_accuracy": round(self.capitalization_accuracy, 4),
            "reference_length": self.reference_length,
            "hypothesis_length": self.hypothesis_length,
        }

    def is_acceptable(
        self,
        max_cer: float = 0.05,
        max_wer: float = 0.10,
        min_umlaut_accuracy: float = 1.0,
    ) -> bool:
        """
        Prüfe ob Metriken akzeptabel sind.

        Args:
            max_cer: Maximale CER (Standard: 5%)
            max_wer: Maximale WER (Standard: 10%)
            min_umlaut_accuracy: Minimale Umlaut-Genauigkeit (Standard: 100%)

        Returns:
            True wenn alle Schwellwerte eingehalten
        """
        return (
            self.cer <= max_cer
            and self.wer <= max_wer
            and self.umlaut_accuracy >= min_umlaut_accuracy
        )


@dataclass
class UmlautAnalysis:
    """Analyse der Umlaut-Erkennung."""
    total_umlauts: int
    correct_umlauts: int
    missed_umlauts: List[Tuple[str, int]]  # (char, position)
    false_positives: List[Tuple[str, int]]  # (char, position)
    accuracy: float

    def to_dict(self) -> Dict[str, float]:
        """Konvertiere zu Dictionary."""
        return {
            "total_umlauts": self.total_umlauts,
            "correct_umlauts": self.correct_umlauts,
            "missed_umlauts": len(self.missed_umlauts),
            "false_positives": len(self.false_positives),
            "accuracy": round(self.accuracy, 4),
        }


# =============================================================================
# Quality Calculator
# =============================================================================


class OCRQualityCalculator:
    """
    Thread-safe, zustandsloser Qualitäts-Rechner.

    Berechnet CER, WER und deutsche Sprach-Metriken
    für OCR-Ergebnisse gegen Ground-Truth-Referenzen.
    """

    # Deutsche Umlaute und Eszett
    UMLAUTS = frozenset("äöüÄÖÜß")

    # Mapping für potenzielle OCR-Fehler bei Umlauten
    # HINWEIS: Latin-1-Doppelkodierungen (z.B. "Ã¤") sind ABSICHTLICH —
    # sie repräsentieren reale OCR-Korruptionsmuster zur Erkennung.
    UMLAUT_SUBSTITUTIONS = {
        "ä": ["a", "ae", "Ã¤"],  # Intentional Latin-1 double-encoding for OCR detection
        "ö": ["o", "oe", "Ã¶"],  # Intentional Latin-1 double-encoding for OCR detection
        "ü": ["u", "ue", "Ã¼"],  # Intentional Latin-1 double-encoding for OCR detection
        "Ä": ["A", "Ae", "AE", "Ã„"],  # Intentional Latin-1 double-encoding for OCR detection
        "Ö": ["O", "Oe", "OE", "Ã–"],  # Intentional Latin-1 double-encoding for OCR detection
        "Ü": ["U", "Ue", "UE", "Ãœ"],  # Intentional Latin-1 double-encoding for OCR detection
        "ß": ["ss", "SS", "sz", "B", "Ã"],  # Intentional Latin-1 double-encoding for OCR detection
    }

    def __init__(self) -> None:
        """Initialisiere Calculator."""
        logger.debug("OCRQualityCalculator initialisiert")

    # -------------------------------------------------------------------------
    # Levenshtein Distance
    # -------------------------------------------------------------------------

    def levenshtein_distance(
        self,
        reference: str,
        hypothesis: str,
        return_operations: bool = False,
    ) -> LevenshteinResult:
        """
        Berechne Levenshtein-Distanz mit Wagner-Fischer-Algorithmus.

        Optimiert für Speichereffizienz O(min(m,n)).

        Args:
            reference: Referenztext (Ground-Truth)
            hypothesis: OCR-Output
            return_operations: Ob Edit-Operationen zurückgegeben werden sollen

        Returns:
            LevenshteinResult mit Distanz und Fehlerdetails
        """
        if not reference and not hypothesis:
            return LevenshteinResult(
                distance=0,
                insertions=0,
                deletions=0,
                substitutions=0,
            )

        if not reference:
            return LevenshteinResult(
                distance=len(hypothesis),
                insertions=len(hypothesis),
                deletions=0,
                substitutions=0,
            )

        if not hypothesis:
            return LevenshteinResult(
                distance=len(reference),
                insertions=0,
                deletions=len(reference),
                substitutions=0,
            )

        m, n = len(reference), len(hypothesis)

        # Vollständige Matrix für Backtracking (wenn Operationen benötigt)
        if return_operations:
            return self._levenshtein_with_backtracking(reference, hypothesis)

        # Speicheroptimierte Version
        if m < n:
            reference, hypothesis = hypothesis, reference
            m, n = n, m

        # Nur zwei Zeilen benötigt
        previous_row = list(range(n + 1))
        current_row = [0] * (n + 1)

        # Für Fehlertypen-Zählung
        insertions = 0
        deletions = 0
        substitutions = 0

        for i in range(1, m + 1):
            current_row[0] = i

            for j in range(1, n + 1):
                cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1

                deletion = previous_row[j] + 1
                insertion = current_row[j - 1] + 1
                substitution = previous_row[j - 1] + cost

                current_row[j] = min(deletion, insertion, substitution)

            previous_row, current_row = current_row, previous_row

        distance = previous_row[n]

        # Approximation der Fehlertypen (ohne vollständiges Backtracking)
        # Genauere Zählung erfordert return_operations=True
        total_errors = distance
        length_diff = abs(len(reference) - len(hypothesis))

        if len(hypothesis) > len(reference):
            insertions = min(length_diff, total_errors)
            substitutions = max(0, total_errors - insertions)
        else:
            deletions = min(length_diff, total_errors)
            substitutions = max(0, total_errors - deletions)

        return LevenshteinResult(
            distance=distance,
            insertions=insertions,
            deletions=deletions,
            substitutions=substitutions,
        )

    def _levenshtein_with_backtracking(
        self,
        reference: str,
        hypothesis: str,
    ) -> LevenshteinResult:
        """Levenshtein mit vollständigem Backtracking für exakte Edit-Operationen."""
        m, n = len(reference), len(hypothesis)

        # Vollständige Matrix
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        # Basis-Fälle
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        # Matrix füllen
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # Deletion
                    dp[i][j - 1] + 1,      # Insertion
                    dp[i - 1][j - 1] + cost,  # Substitution/Match
                )

        # Backtracking
        operations: List[EditInfo] = []
        insertions = 0
        deletions = 0
        substitutions = 0

        i, j = m, n
        while i > 0 or j > 0:
            if i > 0 and j > 0 and reference[i - 1] == hypothesis[j - 1]:
                operations.append(EditInfo(
                    operation=EditOperation.MATCH,
                    position=i - 1,
                    reference_char=reference[i - 1],
                    hypothesis_char=hypothesis[j - 1],
                ))
                i -= 1
                j -= 1
            elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
                operations.append(EditInfo(
                    operation=EditOperation.SUBSTITUTION,
                    position=i - 1,
                    reference_char=reference[i - 1],
                    hypothesis_char=hypothesis[j - 1],
                ))
                substitutions += 1
                i -= 1
                j -= 1
            elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
                operations.append(EditInfo(
                    operation=EditOperation.INSERTION,
                    position=j - 1,
                    hypothesis_char=hypothesis[j - 1],
                ))
                insertions += 1
                j -= 1
            elif i > 0:
                operations.append(EditInfo(
                    operation=EditOperation.DELETION,
                    position=i - 1,
                    reference_char=reference[i - 1],
                ))
                deletions += 1
                i -= 1

        operations.reverse()

        return LevenshteinResult(
            distance=dp[m][n],
            insertions=insertions,
            deletions=deletions,
            substitutions=substitutions,
            operations=operations,
        )

    # -------------------------------------------------------------------------
    # CER / WER
    # -------------------------------------------------------------------------

    def calculate_cer(self, reference: str, hypothesis: str) -> float:
        """
        Berechne Character Error Rate.

        CER = (S + D + I) / N

        Wobei:
        - S = Substitutionen
        - D = Deletions
        - I = Insertionen
        - N = Anzahl Zeichen in Referenz

        Args:
            reference: Referenztext (Ground-Truth)
            hypothesis: OCR-Output

        Returns:
            CER als Float (0-1), kann >1 sein bei sehr schlechtem OCR
        """
        if not reference:
            return 0.0 if not hypothesis else 1.0

        result = self.levenshtein_distance(reference, hypothesis)
        return result.distance / len(reference)

    def calculate_wer(self, reference: str, hypothesis: str) -> float:
        """
        Berechne Word Error Rate.

        WER = (S + D + I) / N auf Wort-Ebene

        Args:
            reference: Referenztext (Ground-Truth)
            hypothesis: OCR-Output

        Returns:
            WER als Float (0-1), kann >1 sein bei sehr schlechtem OCR
        """
        ref_words = self._tokenize(reference)
        hyp_words = self._tokenize(hypothesis)

        if not ref_words:
            return 0.0 if not hyp_words else 1.0

        # Wort-Level Levenshtein
        m, n = len(ref_words), len(hyp_words)

        if m < n:
            ref_words, hyp_words = hyp_words, ref_words
            m, n = n, m

        previous_row = list(range(n + 1))
        current_row = [0] * (n + 1)

        for i in range(1, m + 1):
            current_row[0] = i

            for j in range(1, n + 1):
                cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
                current_row[j] = min(
                    previous_row[j] + 1,
                    current_row[j - 1] + 1,
                    previous_row[j - 1] + cost,
                )

            previous_row, current_row = current_row, previous_row

        distance = previous_row[n]

        # Original Referenz-Länge für WER-Berechnung
        original_ref_len = len(self._tokenize(reference))
        return distance / original_ref_len if original_ref_len > 0 else 0.0

    def _tokenize(self, text: str) -> List[str]:
        """Tokenisiere Text in Wörter."""
        if not text:
            return []
        # Einfache Whitespace-Tokenisierung
        return text.split()

    # -------------------------------------------------------------------------
    # German-specific Metrics
    # -------------------------------------------------------------------------

    def calculate_umlaut_accuracy(
        self,
        reference: str,
        hypothesis: str,
    ) -> UmlautAnalysis:
        """
        Berechne Genauigkeit der Umlaut-Erkennung.

        Prüft:
        - Korrekt erkannte Umlaute
        - Verpasste Umlaute (in Referenz aber nicht in Output)
        - False Positives (in Output aber nicht in Referenz)

        Args:
            reference: Referenztext
            hypothesis: OCR-Output

        Returns:
            UmlautAnalysis mit Details
        """
        ref_umlauts: List[Tuple[str, int]] = []
        hyp_umlauts: List[Tuple[str, int]] = []

        # Finde Umlaute in Referenz
        for i, char in enumerate(reference):
            if char in self.UMLAUTS:
                ref_umlauts.append((char, i))

        # Finde Umlaute in Hypothesis
        for i, char in enumerate(hypothesis):
            if char in self.UMLAUTS:
                hyp_umlauts.append((char, i))

        if not ref_umlauts and not hyp_umlauts:
            return UmlautAnalysis(
                total_umlauts=0,
                correct_umlauts=0,
                missed_umlauts=[],
                false_positives=[],
                accuracy=1.0,
            )

        # Alignment basierend auf Position (mit Toleranz)
        correct = 0
        missed: List[Tuple[str, int]] = []
        false_positives: List[Tuple[str, int]] = []

        # Einfacher Matching-Algorithmus
        matched_hyp_indices: set = set()

        for ref_char, ref_pos in ref_umlauts:
            found = False
            # Suche in Hypothesis mit Positions-Toleranz (±5 Zeichen)
            for idx, (hyp_char, hyp_pos) in enumerate(hyp_umlauts):
                if idx in matched_hyp_indices:
                    continue
                if hyp_char == ref_char and abs(hyp_pos - ref_pos) <= 5:
                    correct += 1
                    matched_hyp_indices.add(idx)
                    found = True
                    break

            if not found:
                missed.append((ref_char, ref_pos))

        # False positives = nicht gematchte Hypothesis-Umlaute
        for idx, (hyp_char, hyp_pos) in enumerate(hyp_umlauts):
            if idx not in matched_hyp_indices:
                false_positives.append((hyp_char, hyp_pos))

        total = len(ref_umlauts)
        accuracy = correct / total if total > 0 else 1.0

        return UmlautAnalysis(
            total_umlauts=total,
            correct_umlauts=correct,
            missed_umlauts=missed,
            false_positives=false_positives,
            accuracy=accuracy,
        )

    def calculate_capitalization_accuracy(
        self,
        reference: str,
        hypothesis: str,
    ) -> float:
        """
        Berechne Großschreibungs-Genauigkeit.

        Wichtig für Deutsche Substantive.

        Args:
            reference: Referenztext
            hypothesis: OCR-Output

        Returns:
            Genauigkeit (0-1)
        """
        if not reference or not hypothesis:
            return 1.0

        ref_words = self._tokenize(reference)
        hyp_words = self._tokenize(hypothesis)

        if not ref_words:
            return 1.0

        # Vergleiche Großschreibung wortweise
        correct = 0
        total = 0

        for ref_word in ref_words:
            if not ref_word:
                continue

            total += 1
            ref_is_capitalized = ref_word[0].isupper()

            # Finde passendes Wort in Hypothesis (case-insensitive)
            ref_lower = ref_word.lower()
            for hyp_word in hyp_words:
                if hyp_word.lower() == ref_lower:
                    hyp_is_capitalized = hyp_word[0].isupper()
                    if ref_is_capitalized == hyp_is_capitalized:
                        correct += 1
                    break

        return correct / total if total > 0 else 1.0

    # -------------------------------------------------------------------------
    # Full Metrics
    # -------------------------------------------------------------------------

    def calculate_full_metrics(
        self,
        reference: str,
        hypothesis: str,
    ) -> OCRQualityMetrics:
        """
        Berechne alle OCR-Qualitätsmetriken.

        Args:
            reference: Referenztext (Ground-Truth)
            hypothesis: OCR-Output

        Returns:
            OCRQualityMetrics mit allen Metriken
        """
        # Levenshtein mit Details
        lev_result = self.levenshtein_distance(reference, hypothesis)

        # CER
        cer = lev_result.distance / len(reference) if reference else 0.0

        # WER
        wer = self.calculate_wer(reference, hypothesis)

        # German-specific
        umlaut_analysis = self.calculate_umlaut_accuracy(reference, hypothesis)
        cap_accuracy = self.calculate_capitalization_accuracy(reference, hypothesis)

        # Umlaut-Fehler als Strings
        umlaut_errors: List[str] = []
        for char, pos in umlaut_analysis.missed_umlauts:
            umlaut_errors.append(f"Verpasst: '{char}' an Position {pos}")
        for char, pos in umlaut_analysis.false_positives:
            umlaut_errors.append(f"False Positive: '{char}' an Position {pos}")

        return OCRQualityMetrics(
            cer=cer,
            wer=wer,
            char_accuracy=1.0 - min(cer, 1.0),
            word_accuracy=1.0 - min(wer, 1.0),
            levenshtein_distance=lev_result.distance,
            insertions=lev_result.insertions,
            deletions=lev_result.deletions,
            substitutions=lev_result.substitutions,
            umlaut_accuracy=umlaut_analysis.accuracy,
            umlaut_errors=umlaut_errors,
            capitalization_accuracy=cap_accuracy,
            reference_length=len(reference),
            hypothesis_length=len(hypothesis),
        )

    # -------------------------------------------------------------------------
    # Batch Processing
    # -------------------------------------------------------------------------

    def calculate_batch_metrics(
        self,
        samples: List[Tuple[str, str]],
    ) -> Dict[str, float]:
        """
        Berechne aggregierte Metriken für einen Batch.

        Args:
            samples: Liste von (reference, hypothesis) Paaren

        Returns:
            Dictionary mit aggregierten Metriken
        """
        if not samples:
            return {
                "avg_cer": 0.0,
                "avg_wer": 0.0,
                "avg_umlaut_accuracy": 1.0,
                "sample_count": 0,
            }

        total_cer = 0.0
        total_wer = 0.0
        total_umlaut_acc = 0.0

        for reference, hypothesis in samples:
            metrics = self.calculate_full_metrics(reference, hypothesis)
            total_cer += metrics.cer
            total_wer += metrics.wer
            total_umlaut_acc += metrics.umlaut_accuracy

        n = len(samples)
        return {
            "avg_cer": total_cer / n,
            "avg_wer": total_wer / n,
            "avg_umlaut_accuracy": total_umlaut_acc / n,
            "sample_count": n,
        }


# =============================================================================
# Singleton
# =============================================================================

_quality_calculator: Optional[OCRQualityCalculator] = None


def get_quality_calculator() -> OCRQualityCalculator:
    """
    Hole globale OCRQualityCalculator-Instanz.

    Thread-safe durch GIL bei einfacher Zuweisung.
    """
    global _quality_calculator
    if _quality_calculator is None:
        _quality_calculator = OCRQualityCalculator()
        logger.info("OCRQualityCalculator initialisiert")
    return _quality_calculator


# =============================================================================
# Convenience Functions
# =============================================================================


def calculate_cer(reference: str, hypothesis: str) -> float:
    """Berechne CER (Character Error Rate)."""
    return get_quality_calculator().calculate_cer(reference, hypothesis)


def calculate_wer(reference: str, hypothesis: str) -> float:
    """Berechne WER (Word Error Rate)."""
    return get_quality_calculator().calculate_wer(reference, hypothesis)


def calculate_metrics(reference: str, hypothesis: str) -> OCRQualityMetrics:
    """Berechne alle OCR-Qualitätsmetriken."""
    return get_quality_calculator().calculate_full_metrics(reference, hypothesis)


# Alias für Backwards-Kompatibilität mit Tests
calculate_quality_metrics = calculate_metrics


def analyze_umlaut_accuracy(reference: str, hypothesis: str) -> UmlautAnalysis:
    """
    Analysiere Umlaut-Genauigkeit zwischen Referenz und OCR-Ergebnis.

    Args:
        reference: Referenztext (Ground Truth)
        hypothesis: OCR-Ergebnis

    Returns:
        UmlautAnalysis mit Details zu Umlaut-Fehlern
    """
    return get_quality_calculator().calculate_umlaut_accuracy(reference, hypothesis)


def compare_texts(reference: str, hypothesis: str) -> Dict[str, float]:
    """
    Schneller Vergleich zweier Texte.

    Returns:
        Dictionary mit CER, WER und Umlaut-Genauigkeit
    """
    metrics = calculate_metrics(reference, hypothesis)
    return metrics.to_dict()
