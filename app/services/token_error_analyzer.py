# -*- coding: utf-8 -*-
"""
Token-Level Error Analyzer für OCR-Qualitätsanalyse.

Analysiert OCR-Ergebnisse auf Token-Ebene:
- Identifiziert Tokens/Wörter mit niedriger Confidence
- Erkennt häufige OCR-Fehlermuster
- Gibt Verbesserungsvorschläge
- Erstellt detaillierte Fehlerberichte

Feinpoliert und durchdacht - OCR-Debugging leicht gemacht.
"""

import re
import structlog
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = structlog.get_logger(__name__)


@dataclass
class TokenError:
    """Repräsentiert einen Token-Fehler."""
    position: int
    token: str
    confidence: float
    context: str  # Umgebender Text
    error_type: str  # z.B. "low_confidence", "ocr_pattern", "umlaut_suspect"
    suggestion: Optional[str] = None


@dataclass
class ErrorPattern:
    """Häufiges OCR-Fehlermuster."""
    pattern: str
    frequency: int
    examples: List[str] = field(default_factory=list)
    suggested_fix: Optional[str] = None


@dataclass
class ErrorAnalysisResult:
    """Ergebnis der Token-Error-Analyse."""
    total_tokens: int
    error_count: int
    error_rate: float
    mean_confidence: float
    min_confidence: float
    errors: List[TokenError]
    patterns: List[ErrorPattern]
    word_errors: Dict[str, List[TokenError]]
    recommendations: List[str]
    severity: str  # "low", "medium", "high", "critical"


class TokenErrorAnalyzer:
    """
    Analysiert OCR-Ergebnisse auf Token-Ebene für Debugging.

    Features:
    - Token-zu-Wort Mapping
    - Fehlermuster-Erkennung
    - Confidence-Distribution-Analyse
    - Verbesserungsvorschläge
    - Detaillierte Berichte

    Usage:
        analyzer = TokenErrorAnalyzer()
        result = analyzer.analyze(ocr_result)
        print(result.recommendations)
    """

    # Confidence-Schwellenwerte
    LOW_CONFIDENCE_THRESHOLD = 0.7
    VERY_LOW_CONFIDENCE_THRESHOLD = 0.5
    CRITICAL_CONFIDENCE_THRESHOLD = 0.3

    # Bekannte OCR-Fehlermuster (Regex -> Beschreibung)
    OCR_ERROR_PATTERNS: Dict[str, str] = {
        r'[0O]': 'Null/O Verwechslung',
        r'[1lI]': 'Eins/l/I Verwechslung',
        r'[5S]': 'Fünf/S Verwechslung',
        r'[8B]': 'Acht/B Verwechslung',
        r'rn|m': 'rn/m Verwechslung',
        r'cl|d': 'cl/d Verwechslung',
        r'ae|ä': 'ae/ä OCR-Problem',
        r'oe|ö': 'oe/ö OCR-Problem',
        r'ue|ü': 'ue/ü OCR-Problem',
        r'ss|ß': 'ss/ß OCR-Problem',
        r'\s{2,}': 'Mehrfache Leerzeichen',
        r'[^\x00-\x7F]+': 'Ungewöhnliche Zeichen',
    }

    # Häufige OCR-Fehler mit Korrekturen (lowercase keys!)
    COMMON_OCR_ERRORS: Dict[str, str] = {
        'teh': 'the',
        'adn': 'and',
        'tne': 'the',
        'rnit': 'mit',
        'clas': 'das',
        'uncl': 'und',
        'l-lerr': 'Herr',
        'frall': 'Frau',
        'stre': 'Straße',
        'str,': 'Str.',
        'grnbh': 'GmbH',
        'grnbl-l': 'GmbH',
    }

    def __init__(
        self,
        low_confidence_threshold: float = 0.7,
        context_window: int = 5
    ):
        """
        Initialisiere Token Error Analyzer.

        Args:
            low_confidence_threshold: Schwellenwert für "niedrige" Confidence
            context_window: Anzahl Wörter für Kontextanzeige
        """
        self.low_confidence_threshold = low_confidence_threshold
        self.context_window = context_window

        logger.info(
            "token_error_analyzer_initialized",
            threshold=low_confidence_threshold,
            context_window=context_window
        )

    def analyze(
        self,
        ocr_result: Dict[str, Any],
        text: Optional[str] = None
    ) -> ErrorAnalysisResult:
        """
        Analysiere OCR-Ergebnis auf Token-Fehler.

        Args:
            ocr_result: OCR-Ergebnis mit confidence_data
            text: Optional - extrahierter Text (falls nicht in ocr_result)

        Returns:
            ErrorAnalysisResult mit detaillierter Analyse
        """
        # Extrahiere Daten
        text = text or ocr_result.get("text", "")
        confidence_data = ocr_result.get("confidence_data", {})

        token_confidences = confidence_data.get("token_confidences", [])
        low_conf_positions = confidence_data.get("low_confidence_positions", [])
        mean_confidence = confidence_data.get("mean_confidence", 0.0)
        min_confidence = confidence_data.get("min_confidence", 0.0)
        total_tokens = confidence_data.get("total_tokens", len(token_confidences))

        # Analysiere Fehler
        errors = self._identify_errors(
            text, token_confidences, low_conf_positions
        )

        # Gruppiere Fehler nach Wörtern
        word_errors = self._group_errors_by_word(errors, text)

        # Erkenne Fehlermuster
        patterns = self._detect_error_patterns(text, errors)

        # Generiere Empfehlungen
        recommendations = self._generate_recommendations(
            errors, patterns, mean_confidence
        )

        # Berechne Schweregrad
        severity = self._calculate_severity(
            len(errors), total_tokens, min_confidence
        )

        error_rate = len(errors) / total_tokens if total_tokens > 0 else 0.0

        result = ErrorAnalysisResult(
            total_tokens=total_tokens,
            error_count=len(errors),
            error_rate=error_rate,
            mean_confidence=mean_confidence,
            min_confidence=min_confidence,
            errors=errors,
            patterns=patterns,
            word_errors=word_errors,
            recommendations=recommendations,
            severity=severity
        )

        logger.info(
            "token_error_analysis_completed",
            total_tokens=total_tokens,
            error_count=len(errors),
            pattern_count=len(patterns),
            severity=severity
        )

        return result

    def _identify_errors(
        self,
        text: str,
        token_confidences: List[float],
        low_conf_positions: List[Dict]
    ) -> List[TokenError]:
        """
        Identifiziere Token-Fehler im Text.

        Args:
            text: OCR-Text
            token_confidences: Liste der Token-Confidences
            low_conf_positions: Positionen mit niedriger Confidence

        Returns:
            Liste von TokenError Objekten
        """
        errors = []
        words = text.split()

        # Verarbeite low_confidence_positions
        for pos_info in low_conf_positions:
            position = pos_info.get("position", 0)
            confidence = pos_info.get("confidence", 0.0)

            # Finde das zugehörige Wort
            word, word_idx = self._find_word_at_position(text, position)

            # Generiere Kontext
            context = self._get_context(words, word_idx)

            # Bestimme Fehlertyp
            error_type = self._classify_error_type(word, confidence)

            # Generiere Vorschlag
            suggestion = self._suggest_correction(word)

            errors.append(TokenError(
                position=position,
                token=word,
                confidence=confidence,
                context=context,
                error_type=error_type,
                suggestion=suggestion
            ))

        # Zusätzlich: Prüfe auf bekannte OCR-Fehlermuster im Text
        pattern_errors = self._find_pattern_errors(text)
        errors.extend(pattern_errors)

        # Deduplizieren (nach Position)
        seen_positions = set()
        unique_errors = []
        for error in errors:
            if error.position not in seen_positions:
                seen_positions.add(error.position)
                unique_errors.append(error)

        return sorted(unique_errors, key=lambda e: e.position)

    def _find_word_at_position(
        self,
        text: str,
        char_position: int
    ) -> Tuple[str, int]:
        """
        Finde das Wort an einer bestimmten Zeichenposition.

        Args:
            text: Gesamttext
            char_position: Zeichenposition

        Returns:
            Tuple (Wort, Wortindex)
        """
        if not text or char_position < 0:
            return ("", -1)

        # Begrenze Position auf Textlänge
        char_position = min(char_position, len(text) - 1)

        # Finde Wortgrenzen
        start = char_position
        end = char_position

        # Suche Wortanfang
        while start > 0 and not text[start - 1].isspace():
            start -= 1

        # Suche Wortende
        while end < len(text) and not text[end].isspace():
            end += 1

        word = text[start:end]

        # Berechne Wortindex
        words_before = text[:start].split()
        word_idx = len(words_before)

        return (word, word_idx)

    def _get_context(self, words: List[str], word_idx: int) -> str:
        """
        Generiere Kontextstring um ein Wort.

        Args:
            words: Liste aller Wörter
            word_idx: Index des Zielworts

        Returns:
            Kontextstring mit markiertem Wort
        """
        if word_idx < 0 or word_idx >= len(words):
            return ""

        start = max(0, word_idx - self.context_window)
        end = min(len(words), word_idx + self.context_window + 1)

        context_words = words[start:end]

        # Markiere das Zielwort
        relative_idx = word_idx - start
        if 0 <= relative_idx < len(context_words):
            context_words[relative_idx] = f"**{context_words[relative_idx]}**"

        return " ".join(context_words)

    def _classify_error_type(self, word: str, confidence: float) -> str:
        """
        Klassifiziere den Fehlertyp basierend auf Wort und Confidence.

        Args:
            word: Das betroffene Wort
            confidence: Token-Confidence

        Returns:
            Fehlertyp-String
        """
        if confidence < self.CRITICAL_CONFIDENCE_THRESHOLD:
            return "critical_confidence"
        elif confidence < self.VERY_LOW_CONFIDENCE_THRESHOLD:
            return "very_low_confidence"
        elif confidence < self.LOW_CONFIDENCE_THRESHOLD:
            return "low_confidence"

        # Prüfe auf spezifische Muster
        if re.search(r'[0O1lI5S8B]', word):
            return "character_confusion"
        if re.search(r'ae|oe|ue', word.lower()):
            return "umlaut_suspect"
        if re.search(r'ss', word):
            return "eszett_suspect"

        return "unknown"

    def _suggest_correction(self, word: str) -> Optional[str]:
        """
        Schlage eine Korrektur für ein Wort vor.

        Args:
            word: Das zu korrigierende Wort

        Returns:
            Korrekturvorschlag oder None
        """
        # Prüfe bekannte Fehler
        word_lower = word.lower()
        if word_lower in self.COMMON_OCR_ERRORS:
            return self.COMMON_OCR_ERRORS[word_lower]

        # Umlaut-Korrekturen
        corrected = word
        corrected = corrected.replace('ae', 'ä')
        corrected = corrected.replace('oe', 'ö')
        corrected = corrected.replace('ue', 'ü')
        corrected = corrected.replace('Ae', 'Ä')
        corrected = corrected.replace('Oe', 'Ö')
        corrected = corrected.replace('Ue', 'Ü')

        if corrected != word:
            return corrected

        return None

    def _find_pattern_errors(self, text: str) -> List[TokenError]:
        """
        Finde Fehler basierend auf bekannten OCR-Mustern.

        Args:
            text: OCR-Text

        Returns:
            Liste von TokenError für Musterfehler
        """
        errors = []

        for word in self.COMMON_OCR_ERRORS.keys():
            for match in re.finditer(re.escape(word), text, re.IGNORECASE):
                errors.append(TokenError(
                    position=match.start(),
                    token=match.group(),
                    confidence=0.5,  # Geschätzt
                    context=text[max(0, match.start()-20):match.end()+20],
                    error_type="known_ocr_error",
                    suggestion=self.COMMON_OCR_ERRORS[word.lower()]
                ))

        return errors

    def _group_errors_by_word(
        self,
        errors: List[TokenError],
        text: str
    ) -> Dict[str, List[TokenError]]:
        """
        Gruppiere Fehler nach Wörtern.

        Args:
            errors: Liste von TokenError
            text: OCR-Text

        Returns:
            Dict mit Wort -> Liste von Fehlern
        """
        word_errors: Dict[str, List[TokenError]] = defaultdict(list)

        for error in errors:
            word_errors[error.token].append(error)

        return dict(word_errors)

    def _detect_error_patterns(
        self,
        text: str,
        errors: List[TokenError]
    ) -> List[ErrorPattern]:
        """
        Erkenne wiederkehrende Fehlermuster.

        Args:
            text: OCR-Text
            errors: Liste von TokenError

        Returns:
            Liste von ErrorPattern
        """
        patterns = []
        pattern_counts: Dict[str, int] = defaultdict(int)
        pattern_examples: Dict[str, List[str]] = defaultdict(list)

        # Zähle Fehlertypen
        for error in errors:
            pattern_counts[error.error_type] += 1
            if len(pattern_examples[error.error_type]) < 3:
                pattern_examples[error.error_type].append(error.token)

        # Prüfe auf OCR-Muster im Text
        for pattern, description in self.OCR_ERROR_PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                pattern_counts[description] = len(matches)
                pattern_examples[description] = matches[:3]

        # Erstelle ErrorPattern Objekte
        for pattern_name, count in pattern_counts.items():
            if count > 0:
                patterns.append(ErrorPattern(
                    pattern=pattern_name,
                    frequency=count,
                    examples=pattern_examples[pattern_name],
                    suggested_fix=self._get_pattern_fix(pattern_name)
                ))

        return sorted(patterns, key=lambda p: p.frequency, reverse=True)

    def _get_pattern_fix(self, pattern_name: str) -> Optional[str]:
        """Hole Korrekturvorschlag für ein Muster."""
        fixes = {
            "low_confidence": "Dokument mit höherer Auflösung scannen",
            "very_low_confidence": "Bildqualität prüfen, evtl. anderen OCR-Backend verwenden",
            "critical_confidence": "Manuelles Review erforderlich",
            "character_confusion": "Font-Training oder manuelles Mapping konfigurieren",
            "umlaut_suspect": "German Text Postprocessor aktivieren",
            "eszett_suspect": "ß/ss Korrektur aktivieren",
            "known_ocr_error": "Bekannter Fehler - wird automatisch korrigiert",
            "Null/O Verwechslung": "Kontext-basierte Korrektur aktivieren",
            "Eins/l/I Verwechslung": "Kontext-basierte Korrektur aktivieren",
            "ae/ä OCR-Problem": "Umlaut-Postprocessing aktivieren",
            "oe/ö OCR-Problem": "Umlaut-Postprocessing aktivieren",
            "ue/ü OCR-Problem": "Umlaut-Postprocessing aktivieren",
            "ss/ß OCR-Problem": "Eszett-Postprocessing aktivieren",
        }
        return fixes.get(pattern_name)

    def _generate_recommendations(
        self,
        errors: List[TokenError],
        patterns: List[ErrorPattern],
        mean_confidence: float
    ) -> List[str]:
        """
        Generiere Verbesserungsempfehlungen.

        Args:
            errors: Liste von TokenError
            patterns: Liste von ErrorPattern
            mean_confidence: Durchschnittliche Confidence

        Returns:
            Liste von Empfehlungen
        """
        recommendations = []

        # Confidence-basierte Empfehlungen
        if mean_confidence < 0.6:
            recommendations.append(
                "⚠️ Niedrige Gesamtconfidence ({:.1%}). "
                "Prüfen Sie die Bildqualität oder verwenden Sie einen anderen OCR-Backend."
                .format(mean_confidence)
            )
        elif mean_confidence < 0.8:
            recommendations.append(
                "ℹ️ Moderate Confidence ({:.1%}). "
                "Manuelle Überprüfung für kritische Dokumente empfohlen."
                .format(mean_confidence)
            )

        # Muster-basierte Empfehlungen
        umlaut_patterns = [p for p in patterns if 'Umlaut' in p.pattern or 'ä' in p.pattern]
        if umlaut_patterns:
            recommendations.append(
                "🔤 Umlaut-Probleme erkannt. "
                "Aktivieren Sie den German Text Postprocessor mit: "
                "options={'postprocess': True}"
            )

        character_confusion = [p for p in patterns if 'Verwechslung' in p.pattern]
        if character_confusion:
            recommendations.append(
                "🔢 Zeichen-Verwechslungen erkannt (0/O, 1/l/I). "
                "Prüfen Sie numerische Felder manuell."
            )

        # Fehleranzahl-basierte Empfehlungen
        if len(errors) > 20:
            recommendations.append(
                "⚡ Viele Fehler erkannt ({}). "
                "Erwägen Sie, das Dokument mit höherer Auflösung zu scannen."
                .format(len(errors))
            )

        # Kritische Fehler
        critical_errors = [e for e in errors if e.error_type == "critical_confidence"]
        if critical_errors:
            recommendations.append(
                "🚨 {} kritische Fehler (Confidence < 30%) gefunden. "
                "Manuelle Überprüfung dringend empfohlen."
                .format(len(critical_errors))
            )

        if not recommendations:
            recommendations.append(
                "✅ Keine signifikanten Probleme erkannt. "
                "OCR-Qualität ist akzeptabel."
            )

        return recommendations

    def _calculate_severity(
        self,
        error_count: int,
        total_tokens: int,
        min_confidence: float
    ) -> str:
        """
        Berechne Schweregrad der Fehleranalyse.

        Args:
            error_count: Anzahl der Fehler
            total_tokens: Gesamtzahl Tokens
            min_confidence: Minimale Confidence

        Returns:
            Schweregrad: "low", "medium", "high", "critical"
        """
        if total_tokens == 0:
            return "low"

        error_rate = error_count / total_tokens

        if min_confidence < 0.3 or error_rate > 0.2:
            return "critical"
        elif min_confidence < 0.5 or error_rate > 0.1:
            return "high"
        elif min_confidence < 0.7 or error_rate > 0.05:
            return "medium"
        else:
            return "low"

    def format_report(
        self,
        result: ErrorAnalysisResult,
        verbose: bool = False
    ) -> str:
        """
        Formatiere Analyseergebnis als lesbaren Bericht.

        Args:
            result: ErrorAnalysisResult
            verbose: Detaillierter Bericht?

        Returns:
            Formatierter Bericht als String
        """
        lines = [
            "=" * 60,
            "TOKEN-LEVEL ERROR ANALYSIS REPORT",
            "=" * 60,
            "",
            f"Gesamttokens: {result.total_tokens}",
            f"Fehleranzahl: {result.error_count}",
            f"Fehlerrate: {result.error_rate:.1%}",
            f"Durchschnittliche Confidence: {result.mean_confidence:.1%}",
            f"Minimale Confidence: {result.min_confidence:.1%}",
            f"Schweregrad: {result.severity.upper()}",
            "",
            "-" * 40,
            "EMPFEHLUNGEN:",
            "-" * 40,
        ]

        for rec in result.recommendations:
            lines.append(f"  {rec}")

        if verbose and result.patterns:
            lines.extend([
                "",
                "-" * 40,
                "ERKANNTE MUSTER:",
                "-" * 40,
            ])
            for pattern in result.patterns[:10]:
                lines.append(
                    f"  • {pattern.pattern}: {pattern.frequency}x "
                    f"(z.B. {', '.join(pattern.examples[:2])})"
                )

        if verbose and result.errors:
            lines.extend([
                "",
                "-" * 40,
                "TOP 10 FEHLER:",
                "-" * 40,
            ])
            for error in result.errors[:10]:
                lines.append(
                    f"  Pos {error.position}: '{error.token}' "
                    f"({error.confidence:.1%}) - {error.error_type}"
                )
                if error.suggestion:
                    lines.append(f"    → Vorschlag: {error.suggestion}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


# =============================================================================
# Singleton Instance
# =============================================================================

_analyzer: Optional[TokenErrorAnalyzer] = None


def get_token_error_analyzer() -> TokenErrorAnalyzer:
    """Hole Singleton-Instance des Token Error Analyzers."""
    global _analyzer
    if _analyzer is None:
        _analyzer = TokenErrorAnalyzer()
    return _analyzer


def analyze_ocr_tokens(
    ocr_result: Dict[str, Any],
    text: Optional[str] = None
) -> ErrorAnalysisResult:
    """
    Convenience-Funktion für Token-Error-Analyse.

    Args:
        ocr_result: OCR-Ergebnis mit confidence_data
        text: Optional - extrahierter Text

    Returns:
        ErrorAnalysisResult
    """
    return get_token_error_analyzer().analyze(ocr_result, text)
