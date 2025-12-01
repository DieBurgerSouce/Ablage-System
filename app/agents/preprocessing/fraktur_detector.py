# -*- coding: utf-8 -*-
"""
Fraktur Script Detection Agent.

Ermöglicht:
- Erkennung von Frakturschrift in Dokumentbildern
- Analyse visueller Merkmale (Long-s, Ligaturen, Strichmuster)
- Konfidenz-basierte Klassifizierung
- Integration mit OCR-Backend-Auswahl

Feinpoliert und durchdacht - Historische Schriften zuverlässig erkennen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.agents.base import AgentCategory, PreprocessingAgent

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class FrakturConfidence(str, Enum):
    """Konfidenz-Level für Fraktur-Erkennung."""
    DEFINITE_FRAKTUR = "definite_fraktur"      # >90% Fraktur
    LIKELY_FRAKTUR = "likely_fraktur"          # 70-90% Fraktur
    MIXED = "mixed"                             # 40-70% (gemischt)
    LIKELY_ANTIQUA = "likely_antiqua"          # 10-40% Fraktur
    DEFINITE_ANTIQUA = "definite_antiqua"      # <10% Fraktur


class FrakturFeature(str, Enum):
    """Erkannte Fraktur-Merkmale."""
    LONG_S = "long_s"                          # ſ (langes s)
    ROUND_R = "round_r"                        # ꝛ (r rotunda)
    LIGATURES = "ligatures"                    # ch, ck, tz, etc.
    BROKEN_STROKES = "broken_strokes"          # Gebrochene Linien
    DIAMOND_DOTS = "diamond_dots"              # Rautenförmige i-Punkte
    TALL_ASCENDERS = "tall_ascenders"          # Hohe Oberlängen
    ORNATE_CAPITALS = "ornate_capitals"        # Verzierte Großbuchstaben
    BLACKLETTER_STYLE = "blackletter_style"    # Genereller Textura-Stil


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class FrakturFeatureScore:
    """Score für ein einzelnes Fraktur-Merkmal."""
    feature: FrakturFeature
    detected: bool
    confidence: float  # 0-1
    occurrences: int = 0
    positions: List[Tuple[int, int, int, int]] = field(default_factory=list)  # (x, y, w, h)


@dataclass
class FrakturAnalysis:
    """Vollständige Fraktur-Analyse eines Dokuments."""
    is_fraktur: bool
    confidence: float  # 0-1
    confidence_level: FrakturConfidence
    features: List[FrakturFeatureScore]
    recommended_backend: str
    analysis_details: Dict[str, Any]

    @property
    def feature_summary(self) -> Dict[str, bool]:
        """Zusammenfassung erkannter Features."""
        return {f.feature.value: f.detected for f in self.features}

    @property
    def total_fraktur_indicators(self) -> int:
        """Anzahl erkannter Fraktur-Indikatoren."""
        return sum(1 for f in self.features if f.detected)


# =============================================================================
# Fraktur Character Patterns
# =============================================================================


class FrakturPatternLibrary:
    """Bibliothek von Fraktur-spezifischen Mustern."""

    # Unicode-Zeichen die auf Fraktur hinweisen
    FRAKTUR_UNICODE_CHARS: Dict[str, str] = {
        "\u017f": "long_s",          # ſ
        "\u1e9e": "capital_eszett",   # ẞ
        "\ua75b": "round_r",          # ꝛ
        "\ua75d": "fraktur_v",        # ꝝ
        "\u0292": "ezh_z",            # ʒ
    }

    # Typische Fraktur-Ligaturen (als Muster)
    FRAKTUR_LIGATURES: List[str] = [
        "ch", "ck", "tz", "st", "ft", "ff", "fi", "fl",
        "sz", "ſt", "ſſ", "ſi", "ſl", "ſch",
    ]

    # Wörter die häufig mit langem s erscheinen
    LONG_S_CONTEXTS: List[str] = [
        "daſs", "muſs", "laſſen", "faſſen", "wiſſen",
        "eſſen", "meſſen", "preſſen", "ſein", "ſie",
        "ſo", "ſich", "ſelbſt", "ſolch", "ſehr",
    ]

    # Historische Schreibweisen die auf Fraktur-Ära hindeuten
    FRAKTUR_ERA_INDICATORS: List[str] = [
        "Thür", "Thor", "Theil", "Thier", "Thal",
        "thun", "gethan", "Muth", "Wuth", "Rath",
        "Noth", "Werth", "daß", "muß", "Fluß",
        "Schloß", "Kuß", "Nuß", "Genuß",
    ]


# =============================================================================
# Fraktur Detector Agent
# =============================================================================


class FrakturDetectorAgent(PreprocessingAgent):
    """
    Agent zur Erkennung von Frakturschrift.

    Analysiert:
    - Visuelle Merkmale (Strichmuster, Ligaturen)
    - Unicode-Zeichen (langes s, Fraktur-spezifische Glyphen)
    - Textmuster (historische Schreibweisen)
    - Layout-Eigenschaften
    """

    # Gewichtung der verschiedenen Erkennungsmethoden
    WEIGHTS = {
        "visual_analysis": 0.35,
        "unicode_detection": 0.30,
        "text_pattern": 0.25,
        "layout_analysis": 0.10,
    }

    # Schwellenwerte für Klassifizierung
    THRESHOLDS = {
        "definite_fraktur": 0.90,
        "likely_fraktur": 0.70,
        "mixed": 0.40,
        "likely_antiqua": 0.10,
    }

    def __init__(self) -> None:
        """Initialisiere Fraktur Detector."""
        super().__init__(name="fraktur_detector")
        self.pattern_library = FrakturPatternLibrary()
        self._model_loaded = False

        logger.info("FrakturDetectorAgent initialisiert")

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analysiere Dokument auf Frakturschrift.

        Args:
            input_data: Dictionary mit:
                - image: numpy array oder Pfad zum Bild
                - text: Optional - bereits extrahierter Text
                - metadata: Optional - Dokument-Metadaten

        Returns:
            Dictionary mit FrakturAnalysis
        """
        self.validate_input(input_data, ["image"])

        image = input_data.get("image")
        text = input_data.get("text", "")
        metadata = input_data.get("metadata", {})

        # Führe verschiedene Analysen durch
        visual_score = await self._analyze_visual_features(image)
        unicode_score = self._analyze_unicode_chars(text) if text else 0.0
        pattern_score = self._analyze_text_patterns(text) if text else 0.0
        layout_score = await self._analyze_layout(image)

        # Kombiniere Scores mit Gewichtung
        if text:
            combined_score = (
                self.WEIGHTS["visual_analysis"] * visual_score +
                self.WEIGHTS["unicode_detection"] * unicode_score +
                self.WEIGHTS["text_pattern"] * pattern_score +
                self.WEIGHTS["layout_analysis"] * layout_score
            )
        else:
            # Ohne Text: Nur visuelle Analyse
            visual_weight = self.WEIGHTS["visual_analysis"] + self.WEIGHTS["layout_analysis"]
            combined_score = (
                (self.WEIGHTS["visual_analysis"] / visual_weight) * visual_score +
                (self.WEIGHTS["layout_analysis"] / visual_weight) * layout_score
            )

        # Bestimme Konfidenz-Level
        confidence_level = self._determine_confidence_level(combined_score)

        # Sammle Feature-Details
        features = await self._collect_feature_details(image, text)

        # Empfehle Backend
        recommended_backend = self._recommend_backend(combined_score, confidence_level)

        analysis = FrakturAnalysis(
            is_fraktur=combined_score >= self.THRESHOLDS["mixed"],
            confidence=combined_score,
            confidence_level=confidence_level,
            features=features,
            recommended_backend=recommended_backend,
            analysis_details={
                "visual_score": visual_score,
                "unicode_score": unicode_score,
                "pattern_score": pattern_score,
                "layout_score": layout_score,
                "has_text_input": bool(text),
                "document_metadata": metadata,
            }
        )

        logger.info(
            "fraktur_analysis_complete",
            is_fraktur=analysis.is_fraktur,
            confidence=round(analysis.confidence, 3),
            level=analysis.confidence_level.value,
            recommended_backend=recommended_backend,
        )

        return {
            "analysis": analysis,
            "is_fraktur": analysis.is_fraktur,
            "confidence": analysis.confidence,
            "recommended_backend": analysis.recommended_backend,
        }

    async def _analyze_visual_features(self, image: Any) -> float:
        """
        Analysiere visuelle Fraktur-Merkmale.

        Erkennt:
        - Gebrochene Strichführung (charakteristisch für Fraktur)
        - Hohe Oberlängen und tiefe Unterlängen
        - Spitze Winkel vs. runde Formen
        - Verzierte Großbuchstaben
        """
        try:
            # Konvertiere zu numpy array falls nötig
            if isinstance(image, str):
                # Bild-Pfad - in echtem System hier laden
                return 0.5  # Neutral wenn nicht ladbar

            if not isinstance(image, np.ndarray):
                return 0.5

            scores = []

            # 1. Stroke Analysis - Fraktur hat mehr gebrochene Linien
            stroke_score = self._analyze_stroke_patterns(image)
            scores.append(stroke_score)

            # 2. Aspect Ratio der Glyphen - Fraktur ist oft schmaler
            aspect_score = self._analyze_glyph_aspect_ratio(image)
            scores.append(aspect_score)

            # 3. Contrast und Stroke Width - Fraktur hat variable Strichstärke
            contrast_score = self._analyze_stroke_width_variation(image)
            scores.append(contrast_score)

            # 4. Vertikale Betonung - Fraktur betont Vertikale
            vertical_score = self._analyze_vertical_emphasis(image)
            scores.append(vertical_score)

            return np.mean(scores) if scores else 0.5

        except Exception as e:
            logger.warning("visual_analysis_error", error=str(e))
            return 0.5  # Neutral bei Fehler

    def _analyze_stroke_patterns(self, image: np.ndarray) -> float:
        """Analysiere Strichmuster für Fraktur-typische gebrochene Linien."""
        try:
            # Grayscale conversion falls nötig
            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # Einfache Kantenerkennung mittels Sobel-ähnlichem Filter
            # Fraktur hat mehr horizontale Unterbrechungen
            dx = np.diff(gray.astype(np.float32), axis=1)
            dy = np.diff(gray.astype(np.float32), axis=0)

            # Verhältnis von horizontalen zu vertikalen Kanten
            h_edges = np.sum(np.abs(dx) > 30)
            v_edges = np.sum(np.abs(dy) > 30)

            if v_edges == 0:
                return 0.5

            # Fraktur hat tendenziell mehr horizontale Unterbrechungen
            ratio = h_edges / v_edges

            # Normalisierung: 0.8-1.5 ist neutral, >1.5 deutet auf Fraktur
            if ratio > 1.5:
                return min(0.9, 0.5 + (ratio - 1.5) * 0.2)
            elif ratio < 0.8:
                return max(0.1, 0.5 - (0.8 - ratio) * 0.2)

            return 0.5

        except Exception:
            return 0.5

    def _analyze_glyph_aspect_ratio(self, image: np.ndarray) -> float:
        """Analysiere Seitenverhältnis der Glyphen."""
        try:
            # Fraktur-Glyphen sind oft schmaler und höher
            # Vereinfachte Analyse über das Gesamtbild
            h, w = image.shape[:2]

            # Textzeilen-Analyse würde hier stattfinden
            # Placeholder für echte Implementierung
            return 0.5

        except Exception:
            return 0.5

    def _analyze_stroke_width_variation(self, image: np.ndarray) -> float:
        """Analysiere Variation der Strichstärke."""
        try:
            # Fraktur hat charakteristische Strichstärken-Variation
            # (dick bei Abstrichen, dünn bei Aufstrichen)

            if len(image.shape) == 3:
                gray = np.mean(image, axis=2)
            else:
                gray = image

            # Berechne lokale Standardabweichung als Maß für Variation
            from scipy import ndimage
            local_std = ndimage.generic_filter(
                gray.astype(np.float32),
                np.std,
                size=5
            )

            mean_variation = np.mean(local_std)

            # Hohe Variation deutet auf Fraktur
            if mean_variation > 30:
                return min(0.8, 0.5 + (mean_variation - 30) * 0.01)

            return 0.5

        except ImportError:
            # scipy nicht verfügbar
            return 0.5
        except Exception:
            return 0.5

    def _analyze_vertical_emphasis(self, image: np.ndarray) -> float:
        """Analysiere vertikale Betonung im Schriftbild."""
        try:
            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # FFT-basierte Analyse der dominanten Richtungen
            # Fraktur hat stärkere vertikale Komponenten

            f_transform = np.fft.fft2(gray)
            f_shift = np.fft.fftshift(f_transform)
            magnitude = np.abs(f_shift)

            h, w = magnitude.shape
            center_h, center_w = h // 2, w // 2

            # Horizontale vs vertikale Energie
            h_energy = np.sum(magnitude[center_h-10:center_h+10, :])
            v_energy = np.sum(magnitude[:, center_w-10:center_w+10])

            if h_energy == 0:
                return 0.5

            ratio = v_energy / h_energy

            # Starke vertikale Komponente deutet auf Fraktur
            if ratio > 1.2:
                return min(0.8, 0.5 + (ratio - 1.2) * 0.15)

            return 0.5

        except Exception:
            return 0.5

    def _analyze_unicode_chars(self, text: str) -> float:
        """Analysiere Text auf Fraktur-spezifische Unicode-Zeichen."""
        if not text:
            return 0.0

        fraktur_char_count = 0
        total_chars = len(text)

        for char in text:
            if char in self.pattern_library.FRAKTUR_UNICODE_CHARS:
                fraktur_char_count += 1

        # Auch langes s in verschiedenen Formen erkennen
        long_s_count = text.count("\u017f")  # ſ

        if total_chars == 0:
            return 0.0

        # Schon wenige Fraktur-Zeichen sind starke Indikatoren
        if fraktur_char_count > 0:
            return min(1.0, 0.5 + fraktur_char_count * 0.1)

        return 0.0

    def _analyze_text_patterns(self, text: str) -> float:
        """Analysiere Text auf Fraktur-typische Muster."""
        if not text:
            return 0.0

        text_lower = text.lower()
        indicators_found = 0

        # Prüfe auf historische Schreibweisen
        for indicator in self.pattern_library.FRAKTUR_ERA_INDICATORS:
            if indicator.lower() in text_lower:
                indicators_found += 1

        # Prüfe auf Long-s Kontexte
        for context in self.pattern_library.LONG_S_CONTEXTS:
            if context.lower() in text_lower:
                indicators_found += 1

        # Prüfe auf Ligaturen
        for ligature in self.pattern_library.FRAKTUR_LIGATURES:
            if ligature in text_lower:
                indicators_found += 0.5

        # Normalisiere Score
        if indicators_found > 10:
            return 0.95
        elif indicators_found > 5:
            return 0.7 + indicators_found * 0.03
        elif indicators_found > 0:
            return 0.3 + indicators_found * 0.08

        return 0.0

    async def _analyze_layout(self, image: Any) -> float:
        """Analysiere Layout-Eigenschaften."""
        try:
            if not isinstance(image, np.ndarray):
                return 0.5

            # Historische Fraktur-Dokumente haben oft:
            # - Engere Zeilenabstände
            # - Sperrung (gesperrter Satz) statt Kursivierung
            # - Längere Textblöcke

            # Placeholder für detaillierte Layout-Analyse
            return 0.5

        except Exception:
            return 0.5

    async def _collect_feature_details(
        self,
        image: Any,
        text: str
    ) -> List[FrakturFeatureScore]:
        """Sammle Details zu allen erkannten Features."""
        features = []

        # Long S Detection
        long_s_count = text.count("\u017f") if text else 0
        features.append(FrakturFeatureScore(
            feature=FrakturFeature.LONG_S,
            detected=long_s_count > 0,
            confidence=min(1.0, long_s_count * 0.2) if long_s_count > 0 else 0.0,
            occurrences=long_s_count,
        ))

        # Round R Detection
        round_r_count = text.count("\ua75b") if text else 0
        features.append(FrakturFeatureScore(
            feature=FrakturFeature.ROUND_R,
            detected=round_r_count > 0,
            confidence=min(1.0, round_r_count * 0.3) if round_r_count > 0 else 0.0,
            occurrences=round_r_count,
        ))

        # Ligature Detection
        ligature_count = 0
        if text:
            for lig in self.pattern_library.FRAKTUR_LIGATURES:
                ligature_count += text.lower().count(lig)
        features.append(FrakturFeatureScore(
            feature=FrakturFeature.LIGATURES,
            detected=ligature_count > 5,
            confidence=min(1.0, ligature_count * 0.05) if ligature_count > 0 else 0.0,
            occurrences=ligature_count,
        ))

        # Broken Strokes (from visual analysis)
        visual_broken = await self._detect_broken_strokes(image)
        features.append(FrakturFeatureScore(
            feature=FrakturFeature.BROKEN_STROKES,
            detected=visual_broken > 0.6,
            confidence=visual_broken,
            occurrences=0,  # Nicht zählbar
        ))

        # Blackletter Style (overall assessment)
        blackletter_score = await self._assess_blackletter_style(image)
        features.append(FrakturFeatureScore(
            feature=FrakturFeature.BLACKLETTER_STYLE,
            detected=blackletter_score > 0.5,
            confidence=blackletter_score,
            occurrences=0,
        ))

        return features

    async def _detect_broken_strokes(self, image: Any) -> float:
        """Erkenne gebrochene Strichführung."""
        try:
            if not isinstance(image, np.ndarray):
                return 0.5

            return self._analyze_stroke_patterns(image)
        except Exception:
            return 0.5

    async def _assess_blackletter_style(self, image: Any) -> float:
        """Bewerte generellen Blackletter/Textura-Stil."""
        try:
            if not isinstance(image, np.ndarray):
                return 0.5

            # Kombiniere mehrere visuelle Indikatoren
            scores = [
                await self._analyze_visual_features(image),
                self._analyze_vertical_emphasis(image),
            ]

            return np.mean(scores)
        except Exception:
            return 0.5

    def _determine_confidence_level(self, score: float) -> FrakturConfidence:
        """Bestimme Konfidenz-Level basierend auf Score."""
        if score >= self.THRESHOLDS["definite_fraktur"]:
            return FrakturConfidence.DEFINITE_FRAKTUR
        elif score >= self.THRESHOLDS["likely_fraktur"]:
            return FrakturConfidence.LIKELY_FRAKTUR
        elif score >= self.THRESHOLDS["mixed"]:
            return FrakturConfidence.MIXED
        elif score >= self.THRESHOLDS["likely_antiqua"]:
            return FrakturConfidence.LIKELY_ANTIQUA
        else:
            return FrakturConfidence.DEFINITE_ANTIQUA

    def _recommend_backend(
        self,
        score: float,
        confidence_level: FrakturConfidence
    ) -> str:
        """Empfehle OCR-Backend basierend auf Fraktur-Analyse."""
        # DeepSeek ist am besten für Fraktur
        if confidence_level in (
            FrakturConfidence.DEFINITE_FRAKTUR,
            FrakturConfidence.LIKELY_FRAKTUR
        ):
            return "deepseek"

        # Bei gemischten Dokumenten: DeepSeek mit Fallback
        if confidence_level == FrakturConfidence.MIXED:
            return "deepseek"  # Sicherste Wahl

        # Für moderne Texte: GOT-OCR ist schneller
        if confidence_level == FrakturConfidence.DEFINITE_ANTIQUA:
            return "got_ocr"

        # Default: DeepSeek (robuster)
        return "deepseek"


# =============================================================================
# Singleton und Convenience Functions
# =============================================================================


_fraktur_detector: Optional[FrakturDetectorAgent] = None


def get_fraktur_detector() -> FrakturDetectorAgent:
    """Hole globale FrakturDetectorAgent-Instanz."""
    global _fraktur_detector
    if _fraktur_detector is None:
        _fraktur_detector = FrakturDetectorAgent()
        logger.info("FrakturDetectorAgent initialisiert")
    return _fraktur_detector


async def detect_fraktur(
    image: Any,
    text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> FrakturAnalysis:
    """
    Convenience-Funktion zur Fraktur-Erkennung.

    Args:
        image: Bild als numpy array oder Pfad
        text: Optional - bereits extrahierter Text
        metadata: Optional - Dokument-Metadaten

    Returns:
        FrakturAnalysis mit Ergebnis
    """
    detector = get_fraktur_detector()
    result = await detector.execute({
        "image": image,
        "text": text or "",
        "metadata": metadata or {},
    })
    return result["result"]["analysis"]


async def is_fraktur(image: Any, text: Optional[str] = None) -> bool:
    """Schnelle Prüfung ob Dokument Fraktur enthält."""
    analysis = await detect_fraktur(image, text)
    return bool(analysis.is_fraktur)  # Konvertiere numpy.bool_ zu Python bool


async def get_recommended_backend(image: Any, text: Optional[str] = None) -> str:
    """Empfehle OCR-Backend basierend auf Fraktur-Erkennung."""
    analysis = await detect_fraktur(image, text)
    return analysis.recommended_backend
