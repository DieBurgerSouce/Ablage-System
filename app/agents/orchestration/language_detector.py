# -*- coding: utf-8 -*-
"""
Language Detector - Multilinguale Spracherkennung.

Enterprise-grade Spracherkennung für OCR-Routing:
- Deutsche Dokumente (Priorität)
- Polnische Dokumente
- Russische/Kyrillische Dokumente
- Weitere Sprachen (Latein + Kyrillisch)

Verwendet:
- langdetect: Schnelle Basiserkennnung
- lingua: Bessere Erkennung für Kyrillisch und kurze Texte

Feinpoliert und durchdacht - Präzise Spracherkennung für optimales Routing.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS & TYPES
# =============================================================================


class ScriptType(str, Enum):
    """Schriftsystem-Typen."""

    LATIN = "latin"
    CYRILLIC = "cyrillic"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class LanguageCode(str, Enum):
    """Unterstützte Sprachen mit ISO 639-1 Codes."""

    GERMAN = "de"
    ENGLISH = "en"
    POLISH = "pl"
    RUSSIAN = "ru"
    UKRAINIAN = "uk"
    CZECH = "cs"
    FRENCH = "fr"
    ITALIAN = "it"
    SPANISH = "es"
    DUTCH = "nl"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, code: str) -> "LanguageCode":
        """Convert ISO code to LanguageCode."""
        code = code.lower()[:2]
        try:
            return cls(code)
        except ValueError:
            return cls.UNKNOWN


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class LanguageDetectionResult:
    """Ergebnis der Spracherkennung."""

    primary_language: LanguageCode
    confidence: float
    script_type: ScriptType
    all_languages: List[Tuple[LanguageCode, float]] = field(default_factory=list)
    is_multilingual: bool = False
    detection_method: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "primary_language": self.primary_language.value,
            "confidence": self.confidence,
            "script_type": self.script_type.value,
            "all_languages": [
                {"language": lang.value, "confidence": conf}
                for lang, conf in self.all_languages
            ],
            "is_multilingual": self.is_multilingual,
            "detection_method": self.detection_method,
        }


# =============================================================================
# LANGUAGE DETECTOR
# =============================================================================


class LanguageDetector:
    """
    Multilinguale Spracherkennung für OCR-Routing.

    Features:
    - Automatische Schrifterkennung (Latein/Kyrillisch)
    - Primäre Sprache + Alternativen
    - Konfidenzwerte
    - Optimiert für DE/PL/RU
    """

    # Sprachspezifische Muster für schnelle Vorerkennung
    GERMAN_PATTERNS = [
        r"\b(der|die|das|und|für|mit|von|auf|ist|sind|werden|wurde)\b",
        r"\b(nicht|auch|oder|aber|nach|bei|über|unter|durch)\b",
        r"[äöüßÄÖÜ]",
    ]

    POLISH_PATTERNS = [
        r"\b(jest|są|być|może|oraz|przez|tylko|jednak|także)\b",
        r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]",
    ]

    RUSSIAN_PATTERNS = [
        r"[а-яА-ЯёЁ]{3,}",  # Kyrillische Wörter
        r"\b(и|в|на|с|по|для|не|что|как|это)\b",
    ]

    # OCR Backend Empfehlungen pro Sprache
    LANGUAGE_BACKEND_PREFERENCES = {
        LanguageCode.GERMAN: ["deepseek", "got_ocr", "surya"],
        LanguageCode.ENGLISH: ["got_ocr", "deepseek", "surya"],
        LanguageCode.POLISH: ["donut", "got_ocr", "surya"],
        LanguageCode.RUSSIAN: ["donut", "surya"],
        LanguageCode.UKRAINIAN: ["donut", "surya"],
        LanguageCode.UNKNOWN: ["donut", "got_ocr"],
    }

    def __init__(self) -> None:
        """Initialize language detector with available backends."""
        self._langdetect_available = False
        self._lingua_available = False

        # Try to import langdetect
        try:
            import langdetect

            # Seed for reproducibility
            langdetect.DetectorFactory.seed = 42
            self._langdetect = langdetect
            self._langdetect_available = True
            logger.info("langdetect verfügbar")
        except ImportError:
            logger.warning(
                "langdetect nicht installiert. "
                "Installieren mit: pip install langdetect"
            )

        # Try to import lingua
        try:
            from lingua import Language, LanguageDetectorBuilder


            # Build detector for relevant languages
            self._lingua_detector = (
                LanguageDetectorBuilder.from_languages(
                    Language.GERMAN,
                    Language.ENGLISH,
                    Language.POLISH,
                    Language.RUSSIAN,
                    Language.UKRAINIAN,
                    Language.CZECH,
                    Language.FRENCH,
                    Language.ITALIAN,
                    Language.SPANISH,
                    Language.DUTCH,
                )
                .with_preloaded_language_models()
                .build()
            )
            self._lingua_available = True
            self._Language = Language
            logger.info("lingua verfügbar")
        except ImportError:
            logger.warning(
                "lingua nicht installiert. "
                "Installieren mit: pip install lingua-language-detector"
            )

    def detect(self, text: str) -> LanguageDetectionResult:
        """
        Erkennt die Sprache(n) eines Textes.

        Args:
            text: Text zur Analyse

        Returns:
            LanguageDetectionResult mit Sprache und Konfidenz
        """
        if not text or len(text.strip()) < 3:
            return LanguageDetectionResult(
                primary_language=LanguageCode.UNKNOWN,
                confidence=0.0,
                script_type=ScriptType.UNKNOWN,
                detection_method="no_text",
            )

        # Step 1: Detect script type
        script_type = self._detect_script(text)

        # Step 2: Quick pattern-based pre-detection
        pattern_result = self._pattern_detection(text)
        if pattern_result and pattern_result.confidence > 0.9:
            pattern_result.script_type = script_type
            return pattern_result

        # Step 3: Use lingua for Cyrillic (better accuracy)
        if script_type == ScriptType.CYRILLIC and self._lingua_available:
            return self._lingua_detect(text, script_type)

        # Step 4: Use langdetect for Latin scripts
        if self._langdetect_available:
            result = self._langdetect_detect(text, script_type)
            if result.confidence > 0.5:
                return result

        # Step 5: Fallback to lingua if langdetect uncertain
        if self._lingua_available:
            return self._lingua_detect(text, script_type)

        # Step 6: Use pattern result if nothing else works
        if pattern_result:
            return pattern_result

        return LanguageDetectionResult(
            primary_language=LanguageCode.GERMAN,  # Default for German system
            confidence=0.3,
            script_type=script_type,
            detection_method="default_fallback",
        )

    def _detect_script(self, text: str) -> ScriptType:
        """Detect script type (Latin/Cyrillic/Mixed)."""
        latin_count = len(re.findall(r"[a-zA-ZäöüßÄÖÜàáâãéèêëíìîïóòôõúùûüçñ]", text))
        cyrillic_count = len(re.findall(r"[а-яА-ЯёЁіІїЇєЄґҐ]", text))

        total = latin_count + cyrillic_count
        if total == 0:
            return ScriptType.UNKNOWN

        latin_ratio = latin_count / total
        cyrillic_ratio = cyrillic_count / total

        if latin_ratio > 0.9:
            return ScriptType.LATIN
        elif cyrillic_ratio > 0.9:
            return ScriptType.CYRILLIC
        elif latin_ratio > 0.1 and cyrillic_ratio > 0.1:
            return ScriptType.MIXED
        elif latin_ratio > cyrillic_ratio:
            return ScriptType.LATIN
        else:
            return ScriptType.CYRILLIC

    def _pattern_detection(self, text: str) -> Optional[LanguageDetectionResult]:
        """Quick pattern-based language detection."""
        text_lower = text.lower()

        # Check German patterns
        german_matches = sum(
            len(re.findall(pattern, text_lower, re.IGNORECASE))
            for pattern in self.GERMAN_PATTERNS
        )

        # Check Polish patterns
        polish_matches = sum(
            len(re.findall(pattern, text_lower, re.IGNORECASE))
            for pattern in self.POLISH_PATTERNS
        )

        # Check Russian patterns
        russian_matches = sum(
            len(re.findall(pattern, text, re.IGNORECASE))
            for pattern in self.RUSSIAN_PATTERNS
        )

        total_words = len(text.split())
        if total_words == 0:
            return None

        # Calculate confidence based on pattern matches
        german_conf = min(german_matches / (total_words * 0.3), 1.0)
        polish_conf = min(polish_matches / (total_words * 0.2), 1.0)
        russian_conf = min(russian_matches / (total_words * 0.3), 1.0)

        # Return if high confidence
        if german_conf > 0.9:
            return LanguageDetectionResult(
                primary_language=LanguageCode.GERMAN,
                confidence=german_conf,
                script_type=ScriptType.LATIN,
                detection_method="pattern_german",
            )
        if polish_conf > 0.9:
            return LanguageDetectionResult(
                primary_language=LanguageCode.POLISH,
                confidence=polish_conf,
                script_type=ScriptType.LATIN,
                detection_method="pattern_polish",
            )
        if russian_conf > 0.8:
            return LanguageDetectionResult(
                primary_language=LanguageCode.RUSSIAN,
                confidence=russian_conf,
                script_type=ScriptType.CYRILLIC,
                detection_method="pattern_russian",
            )

        return None

    def _langdetect_detect(
        self, text: str, script_type: ScriptType
    ) -> LanguageDetectionResult:
        """Use langdetect for language detection."""
        try:
            # Get all language probabilities
            probabilities = self._langdetect.detect_langs(text)

            all_languages = []
            for prob in probabilities[:5]:  # Top 5
                lang_code = LanguageCode.from_string(prob.lang)
                all_languages.append((lang_code, prob.prob))

            if all_languages:
                primary = all_languages[0]
                return LanguageDetectionResult(
                    primary_language=primary[0],
                    confidence=primary[1],
                    script_type=script_type,
                    all_languages=all_languages,
                    is_multilingual=len(all_languages) > 1 and all_languages[1][1] > 0.2,
                    detection_method="langdetect",
                )

        except Exception as e:
            logger.debug("langdetect_error", **safe_error_log(e))

        return LanguageDetectionResult(
            primary_language=LanguageCode.UNKNOWN,
            confidence=0.0,
            script_type=script_type,
            detection_method="langdetect_failed",
        )

    def _lingua_detect(
        self, text: str, script_type: ScriptType
    ) -> LanguageDetectionResult:
        """Use lingua for language detection (better for Cyrillic)."""
        try:
            # Get confidence values for all languages
            confidence_values = self._lingua_detector.compute_language_confidence_values(
                text
            )

            all_languages = []
            for cv in confidence_values[:5]:  # Top 5
                lang_code = self._lingua_to_code(cv.language)
                all_languages.append((lang_code, cv.value))

            if all_languages:
                primary = all_languages[0]
                return LanguageDetectionResult(
                    primary_language=primary[0],
                    confidence=primary[1],
                    script_type=script_type,
                    all_languages=all_languages,
                    is_multilingual=len(all_languages) > 1 and all_languages[1][1] > 0.2,
                    detection_method="lingua",
                )

        except Exception as e:
            logger.debug("lingua_error", **safe_error_log(e))

        return LanguageDetectionResult(
            primary_language=LanguageCode.UNKNOWN,
            confidence=0.0,
            script_type=script_type,
            detection_method="lingua_failed",
        )

    def _lingua_to_code(self, lingua_lang: "lingua.Language") -> LanguageCode:
        """Convert lingua Language to LanguageCode."""
        mapping = {
            "GERMAN": LanguageCode.GERMAN,
            "ENGLISH": LanguageCode.ENGLISH,
            "POLISH": LanguageCode.POLISH,
            "RUSSIAN": LanguageCode.RUSSIAN,
            "UKRAINIAN": LanguageCode.UKRAINIAN,
            "CZECH": LanguageCode.CZECH,
            "FRENCH": LanguageCode.FRENCH,
            "ITALIAN": LanguageCode.ITALIAN,
            "SPANISH": LanguageCode.SPANISH,
            "DUTCH": LanguageCode.DUTCH,
        }
        return mapping.get(lingua_lang.name, LanguageCode.UNKNOWN)

    def get_recommended_backends(
        self, language: LanguageCode
    ) -> List[str]:
        """Get recommended OCR backends for a language."""
        return self.LANGUAGE_BACKEND_PREFERENCES.get(
            language,
            self.LANGUAGE_BACKEND_PREFERENCES[LanguageCode.UNKNOWN],
        )

    def is_cyrillic_language(self, language: LanguageCode) -> bool:
        """Check if language uses Cyrillic script."""
        return language in (LanguageCode.RUSSIAN, LanguageCode.UKRAINIAN)

    def detect_from_image_text(
        self,
        ocr_text: str,
        min_confidence: float = 0.5,
    ) -> LanguageDetectionResult:
        """
        Detect language from OCR-extracted text.

        Handles OCR noise and errors better than raw detect().

        Args:
            ocr_text: Text extracted by OCR
            min_confidence: Minimum confidence threshold

        Returns:
            LanguageDetectionResult
        """
        # Clean OCR text
        cleaned = self._clean_ocr_text(ocr_text)

        if len(cleaned) < 20:
            # Too short for reliable detection
            return LanguageDetectionResult(
                primary_language=LanguageCode.GERMAN,  # Default
                confidence=0.3,
                script_type=self._detect_script(cleaned),
                detection_method="ocr_short_text",
            )

        result = self.detect(cleaned)

        # Apply confidence penalty for OCR text
        result.confidence *= 0.9  # OCR may have errors

        if result.confidence < min_confidence:
            # Fall back to German for low confidence
            result.primary_language = LanguageCode.GERMAN

        return result

    def _clean_ocr_text(self, text: str) -> str:
        """Clean OCR text for better language detection."""
        # Remove common OCR artifacts
        text = re.sub(r"[|_\\\/\[\]{}]", "", text)
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove very short words (likely OCR errors)
        words = text.split()
        words = [w for w in words if len(w) > 1]
        return " ".join(words)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


# Singleton instance
_detector: Optional[LanguageDetector] = None


def get_detector() -> LanguageDetector:
    """Get singleton language detector instance."""
    global _detector
    if _detector is None:
        _detector = LanguageDetector()
    return _detector


def detect_language(text: str) -> LanguageDetectionResult:
    """
    Convenience function to detect language.

    Args:
        text: Text to analyze

    Returns:
        LanguageDetectionResult
    """
    return get_detector().detect(text)


def get_language_backends(text: str) -> List[str]:
    """
    Get recommended backends for text's language.

    Args:
        text: Text to analyze

    Returns:
        List of backend names in order of preference
    """
    detector = get_detector()
    result = detector.detect(text)
    return detector.get_recommended_backends(result.primary_language)
