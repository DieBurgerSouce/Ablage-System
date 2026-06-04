# -*- coding: utf-8 -*-
"""
Document Feature Classifier for OCR Backend Selection.

Analysiert Dokument-Features um das optimale OCR-Backend zu wählen:
- Tabellen-Detection -> GOT-OCR
- Fraktur-Detection -> DeepSeek
- Formel-Detection -> GOT-OCR
- Layout-Komplexität -> Surya+Docling
- Sprache (DE/EN)

Feinpoliert und durchdacht - Intelligente Backend-Auswahl.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Optional imports for image analysis
PIL_AVAILABLE = False
NUMPY_AVAILABLE = False
CV2_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    pass

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    pass

try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    pass


class DocumentComplexity(str, Enum):
    """Komplexitätsstufen eines Dokuments."""
    SIMPLE = "simple"           # Reiner Text, keine Struktur
    MODERATE = "moderate"       # Einfache Struktur, wenige Elemente
    COMPLEX = "complex"         # Tabellen, mehrspaltiges Layout
    VERY_COMPLEX = "very_complex"  # Formeln, Diagramme, komplexe Layouts


class DocumentFeature(str, Enum):
    """Erkannte Dokument-Features."""
    TABLES = "tables"
    FRAKTUR = "fraktur"
    FORMULAS = "formulas"
    MULTI_COLUMN = "multi_column"
    HANDWRITING = "handwriting"
    IMAGES = "images"
    STAMPS = "stamps"
    SIGNATURES = "signatures"
    NOISE = "noise"
    LOW_CONTRAST = "low_contrast"


@dataclass
class DocumentFeatures:
    """Ergebnis der Feature-Analyse eines Dokuments."""
    # Feature Detection
    has_tables: bool = False
    has_fraktur: bool = False
    has_formulas: bool = False
    has_multi_column: bool = False
    has_handwriting: bool = False
    has_images: bool = False
    has_stamps: bool = False
    has_signatures: bool = False

    # Quality Indicators
    has_noise: bool = False
    has_low_contrast: bool = False
    estimated_dpi: int = 300

    # Complexity
    complexity: DocumentComplexity = DocumentComplexity.SIMPLE

    # Language Detection
    detected_language: str = "de"
    language_confidence: float = 0.9

    # Backend Recommendation
    recommended_backend: str = "deepseek"
    backend_confidence: float = 0.8
    alternative_backends: List[str] = field(default_factory=list)

    # Feature Scores
    feature_scores: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "has_tables": self.has_tables,
            "has_fraktur": self.has_fraktur,
            "has_formulas": self.has_formulas,
            "has_multi_column": self.has_multi_column,
            "has_handwriting": self.has_handwriting,
            "has_images": self.has_images,
            "complexity": self.complexity.value,
            "detected_language": self.detected_language,
            "language_confidence": self.language_confidence,
            "recommended_backend": self.recommended_backend,
            "backend_confidence": self.backend_confidence,
            "alternative_backends": self.alternative_backends,
            "feature_scores": self.feature_scores,
        }


class DocumentFeatureClassifier:
    """
    Classifier für Dokument-Features zur OCR-Backend-Auswahl.

    Verwendet regelbasierte Heuristiken und optionale ML-Modelle
    um Dokument-Features zu erkennen und das beste Backend zu empfehlen.

    Backend-Empfehlungen:
    - DeepSeek: Deutsche Texte, Fraktur, komplexe Umlaute
    - GOT-OCR: Tabellen, Formeln, strukturierte Layouts
    - Surya: Schnelle Verarbeitung, einfache Dokumente
    - Surya+Docling: Layout-Analyse, mehrspaltiges Layout
    """

    # Backend-Feature Mapping (welches Backend ist für welches Feature optimal)
    BACKEND_FEATURE_SCORES = {
        "deepseek": {
            DocumentFeature.FRAKTUR: 1.0,
            DocumentFeature.HANDWRITING: 0.8,
            DocumentFeature.NOISE: 0.7,
            DocumentFeature.LOW_CONTRAST: 0.6,
        },
        "got_ocr": {
            DocumentFeature.TABLES: 1.0,
            DocumentFeature.FORMULAS: 1.0,
            DocumentFeature.MULTI_COLUMN: 0.8,
            DocumentFeature.IMAGES: 0.7,
        },
        "surya": {
            DocumentFeature.STAMPS: 0.6,
            DocumentFeature.SIGNATURES: 0.5,
        },
        "surya_gpu": {
            DocumentFeature.STAMPS: 0.7,
            DocumentFeature.SIGNATURES: 0.6,
        },
        "surya_docling": {
            DocumentFeature.MULTI_COLUMN: 0.9,
            DocumentFeature.TABLES: 0.7,
            DocumentFeature.IMAGES: 0.8,
        },
    }

    # Sprach-Backend Präferenzen
    LANGUAGE_BACKEND_PREFERENCE = {
        "de": ["deepseek", "got_ocr", "surya_gpu", "surya"],
        "en": ["got_ocr", "surya_gpu", "deepseek", "surya"],
        "multi": ["got_ocr", "deepseek", "surya_gpu", "surya"],
    }

    def __init__(
        self,
        enable_visual_analysis: bool = True,
        enable_ml_detection: bool = False,
    ) -> None:
        """
        Initialisiere Document Feature Classifier.

        Args:
            enable_visual_analysis: Bild-basierte Feature-Erkennung
            enable_ml_detection: ML-basierte Feature-Erkennung (langsamer)
        """
        self.enable_visual_analysis = enable_visual_analysis and PIL_AVAILABLE
        self.enable_ml_detection = enable_ml_detection

        logger.info(
            "document_feature_classifier_initialized",
            visual_analysis=self.enable_visual_analysis,
            ml_detection=self.enable_ml_detection,
        )

    def analyze(
        self,
        image_path: str,
        text_sample: Optional[str] = None,
    ) -> DocumentFeatures:
        """
        Analysiere Dokument und erkenne Features.

        Args:
            image_path: Pfad zum Dokumentbild
            text_sample: Optionaler Text-Sample für Spracherkennung

        Returns:
            DocumentFeatures mit allen erkannten Features
        """
        features = DocumentFeatures()

        # Bild-basierte Analyse
        if self.enable_visual_analysis:
            self._analyze_image_features(image_path, features)

        # Text-basierte Analyse
        if text_sample:
            self._analyze_text_features(text_sample, features)

        # Komplexität berechnen
        self._calculate_complexity(features)

        # Backend-Empfehlung generieren
        self._recommend_backend(features)

        logger.debug(
            "document_features_analyzed",
            path=image_path,
            complexity=features.complexity.value,
            recommended=features.recommended_backend,
        )

        return features

    def _analyze_image_features(
        self,
        image_path: str,
        features: DocumentFeatures,
    ) -> None:
        """Analysiere Bild-Features."""
        if not PIL_AVAILABLE:
            return

        try:
            img = Image.open(image_path)
            width, height = img.size

            # Estimate DPI from image size
            # Typical A4 at 300 DPI is ~2480x3508
            if width > 2000 and height > 2800:
                features.estimated_dpi = 300
            elif width > 1000 and height > 1400:
                features.estimated_dpi = 150
            else:
                features.estimated_dpi = 72

            # Convert to grayscale for analysis
            if img.mode != 'L':
                img_gray = img.convert('L')
            else:
                img_gray = img

            if NUMPY_AVAILABLE:
                img_array = np.array(img_gray)

                # Check for low contrast
                std_dev = np.std(img_array)
                if std_dev < 30:
                    features.has_low_contrast = True
                    features.feature_scores["low_contrast"] = 1.0 - (std_dev / 30)

                # Check for noise (high frequency content)
                if CV2_AVAILABLE:
                    laplacian_var = cv2.Laplacian(img_array, cv2.CV_64F).var()
                    if laplacian_var > 500:
                        features.has_noise = True
                        features.feature_scores["noise"] = min(1.0, laplacian_var / 1000)

                # Simple table detection (look for grid patterns)
                if self._detect_table_patterns(img_array):
                    features.has_tables = True
                    features.feature_scores["tables"] = 0.7

                # Multi-column detection (analyze horizontal projection)
                if self._detect_multi_column(img_array):
                    features.has_multi_column = True
                    features.feature_scores["multi_column"] = 0.6

            img.close()

        except Exception as e:
            logger.warning("image_analysis_failed", path=image_path, **safe_error_log(e))

    def _detect_table_patterns(self, img_array: "np.ndarray") -> bool:
        """Erkenne Tabellen-Patterns im Bild."""
        if not CV2_AVAILABLE:
            return False

        try:
            # Edge detection
            edges = cv2.Canny(img_array, 50, 150)

            # Hough transform für Linien
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi/180,
                threshold=100,
                minLineLength=50,
                maxLineGap=10
            )

            if lines is None:
                return False

            # Zähle horizontale und vertikale Linien
            horizontal_lines = 0
            vertical_lines = 0

            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi

                if abs(angle) < 10 or abs(angle) > 170:
                    horizontal_lines += 1
                elif 80 < abs(angle) < 100:
                    vertical_lines += 1

            # Tabelle erkannt wenn genug horizontale UND vertikale Linien
            return horizontal_lines >= 3 and vertical_lines >= 2

        except Exception:
            return False

    def _detect_multi_column(self, img_array: "np.ndarray") -> bool:
        """Erkenne mehrspaltige Layouts."""
        try:
            # Horizontale Projektion
            horizontal_proj = np.sum(img_array < 128, axis=0)

            # Suche nach deutlichen Lücken (Spalten-Trenner)
            threshold = np.max(horizontal_proj) * 0.1
            gaps = horizontal_proj < threshold

            # Zähle zusammenhängende Lücken
            gap_count = 0
            in_gap = False
            for is_gap in gaps:
                if is_gap and not in_gap:
                    gap_count += 1
                    in_gap = True
                elif not is_gap:
                    in_gap = False

            # Mehrspaltiges Layout bei mindestens einer deutlichen Lücke in der Mitte
            return gap_count >= 1

        except Exception:
            return False

    def _analyze_text_features(
        self,
        text_sample: str,
        features: DocumentFeatures,
    ) -> None:
        """Analysiere Text-Features."""
        if not text_sample:
            return

        text_lower = text_sample.lower()

        # Spracherkennung (einfache Heuristik)
        german_indicators = ["der", "die", "das", "und", "ist", "ich", "nicht", "sie", "es", "wir"]
        english_indicators = ["the", "and", "is", "to", "of", "a", "in", "that", "it", "for"]

        german_count = sum(1 for word in german_indicators if f" {word} " in f" {text_lower} ")
        english_count = sum(1 for word in english_indicators if f" {word} " in f" {text_lower} ")

        if german_count > english_count:
            features.detected_language = "de"
            features.language_confidence = min(0.95, 0.5 + german_count * 0.05)
        elif english_count > german_count:
            features.detected_language = "en"
            features.language_confidence = min(0.95, 0.5 + english_count * 0.05)
        else:
            features.detected_language = "multi"
            features.language_confidence = 0.5

        # Fraktur-Erkennung (typische Fehler bei Fraktur-OCR)
        fraktur_indicators = [
            "ſ",  # langes s
            "ꝛ",  # r-Ligatur
        ]
        fraktur_error_patterns = [
            "ck" in text_sample and text_sample.count("ck") > 3,  # Häufige ck in alten Texten
            "th" in text_sample and text_sample.count("th") > 5,  # Alte Schreibweise
        ]

        if any(ind in text_sample for ind in fraktur_indicators) or sum(fraktur_error_patterns) >= 2:
            features.has_fraktur = True
            features.feature_scores["fraktur"] = 0.8

        # Formel-Erkennung
        formula_patterns = [
            "=" in text_sample and any(c.isdigit() for c in text_sample),
            "+" in text_sample and "-" in text_sample,
            any(sym in text_sample for sym in ["∫", "∑", "∏", "√", "∂", "∞"]),
        ]

        if sum(formula_patterns) >= 2:
            features.has_formulas = True
            features.feature_scores["formulas"] = 0.7

    def _calculate_complexity(self, features: DocumentFeatures) -> None:
        """Berechne Gesamtkomplexität des Dokuments."""
        complexity_score = 0.0

        if features.has_tables:
            complexity_score += 0.3
        if features.has_fraktur:
            complexity_score += 0.4
        if features.has_formulas:
            complexity_score += 0.3
        if features.has_multi_column:
            complexity_score += 0.2
        if features.has_handwriting:
            complexity_score += 0.4
        if features.has_noise:
            complexity_score += 0.2
        if features.has_low_contrast:
            complexity_score += 0.2

        if complexity_score < 0.2:
            features.complexity = DocumentComplexity.SIMPLE
        elif complexity_score < 0.4:
            features.complexity = DocumentComplexity.MODERATE
        elif complexity_score < 0.7:
            features.complexity = DocumentComplexity.COMPLEX
        else:
            features.complexity = DocumentComplexity.VERY_COMPLEX

    def _recommend_backend(self, features: DocumentFeatures) -> None:
        """Generiere Backend-Empfehlung basierend auf Features."""
        backend_scores: Dict[str, float] = {
            "deepseek": 0.0,
            "got_ocr": 0.0,
            "surya": 0.0,
            "surya_gpu": 0.0,
        }

        # Score basierend auf erkannten Features
        detected_features = []
        if features.has_tables:
            detected_features.append(DocumentFeature.TABLES)
        if features.has_fraktur:
            detected_features.append(DocumentFeature.FRAKTUR)
        if features.has_formulas:
            detected_features.append(DocumentFeature.FORMULAS)
        if features.has_multi_column:
            detected_features.append(DocumentFeature.MULTI_COLUMN)
        if features.has_handwriting:
            detected_features.append(DocumentFeature.HANDWRITING)
        if features.has_noise:
            detected_features.append(DocumentFeature.NOISE)
        if features.has_low_contrast:
            detected_features.append(DocumentFeature.LOW_CONTRAST)

        for backend, feature_scores in self.BACKEND_FEATURE_SCORES.items():
            for feature in detected_features:
                if feature in feature_scores:
                    backend_scores[backend] += feature_scores[feature]

        # Sprach-Präferenz hinzufügen
        lang_prefs = self.LANGUAGE_BACKEND_PREFERENCE.get(
            features.detected_language,
            self.LANGUAGE_BACKEND_PREFERENCE["de"]
        )
        for i, backend in enumerate(lang_prefs):
            if backend in backend_scores:
                backend_scores[backend] += (len(lang_prefs) - i) * 0.1

        # Komplexitäts-Bonus für bestimmte Backends
        if features.complexity in [DocumentComplexity.COMPLEX, DocumentComplexity.VERY_COMPLEX]:
            backend_scores["deepseek"] += 0.2
            backend_scores["got_ocr"] += 0.15

        # Default-Bonus für DeepSeek bei deutschen Dokumenten
        if features.detected_language == "de":
            backend_scores["deepseek"] += 0.3

        # Bestes Backend wählen
        sorted_backends = sorted(
            backend_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        best_backend, best_score = sorted_backends[0]
        total_score = sum(backend_scores.values())

        features.recommended_backend = best_backend
        features.backend_confidence = best_score / total_score if total_score > 0 else 0.5
        features.alternative_backends = [b for b, _ in sorted_backends[1:3]]
        features.feature_scores["backend_scores"] = {b: round(s, 3) for b, s in sorted_backends}


# Singleton instance
_document_classifier: Optional[DocumentFeatureClassifier] = None


def get_document_classifier() -> DocumentFeatureClassifier:
    """Hole globale DocumentFeatureClassifier Instanz."""
    global _document_classifier
    if _document_classifier is None:
        _document_classifier = DocumentFeatureClassifier()
    return _document_classifier


def classify_document_for_ocr(
    image_path: str,
    text_sample: Optional[str] = None,
) -> DocumentFeatures:
    """
    Convenience-Funktion zur Dokument-Klassifizierung.

    Args:
        image_path: Pfad zum Dokumentbild
        text_sample: Optionaler Text-Sample

    Returns:
        DocumentFeatures mit Backend-Empfehlung
    """
    classifier = get_document_classifier()
    return classifier.analyze(image_path, text_sample)
