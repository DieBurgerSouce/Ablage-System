# -*- coding: utf-8 -*-
"""
Handwriting Detection Agent.

Ermöglicht:
- Erkennung von handschriftlichen Bereichen in Dokumenten
- Unterschrift-Detection auf Verträgen
- Handschriftliche Notizen und Anmerkungen
- Formular-Ausfüllungen (handgeschrieben)
- Confidence-Anpassung für handschriftliche Regionen

Feinpoliert und durchdacht - Handschrift zuverlässig erkennen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import structlog

from app.agents.base import AgentCategory, PreprocessingAgent
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class HandwritingType(str, Enum):
    """Typen von handschriftlichen Inhalten."""
    SIGNATURE = "signature"              # Unterschrift
    ANNOTATION = "annotation"            # Handschriftliche Anmerkung
    FORM_FILL = "form_fill"              # Formularausfüllung
    FULL_HANDWRITTEN = "full_handwritten"  # Komplett handgeschriebenes Dokument
    MIXED = "mixed"                      # Gemischt (gedruckt + handschriftlich)
    NONE = "none"                        # Keine Handschrift erkannt


class HandwritingConfidence(str, Enum):
    """Konfidenz-Level für Handschrift-Erkennung."""
    DEFINITE_HANDWRITING = "definite_handwriting"   # >85% handschriftlich
    LIKELY_HANDWRITING = "likely_handwriting"       # 60-85% handschriftlich
    PARTIAL_HANDWRITING = "partial_handwriting"     # 30-60% (Teile handschriftlich)
    LIKELY_PRINTED = "likely_printed"               # 10-30% handschriftlich
    DEFINITE_PRINTED = "definite_printed"           # <10% handschriftlich


class HandwritingFeature(str, Enum):
    """Erkannte Handschrift-Merkmale."""
    IRREGULAR_BASELINE = "irregular_baseline"     # Ungleichmäßige Grundlinie
    VARIABLE_SLANT = "variable_slant"             # Variable Neigung
    CONNECTED_STROKES = "connected_strokes"       # Verbundene Striche
    PRESSURE_VARIATION = "pressure_variation"     # Druckvariationen
    IRREGULAR_SPACING = "irregular_spacing"       # Ungleichmäßiger Abstand
    CURSIVE_PATTERNS = "cursive_patterns"         # Kursive Muster
    INK_CHARACTERISTICS = "ink_characteristics"   # Tinten-Merkmale
    SIGNATURE_PATTERN = "signature_pattern"       # Unterschrift-spezifisch


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class HandwritingRegion:
    """Eine erkannte handschriftliche Region im Dokument."""
    x: int
    y: int
    width: int
    height: int
    confidence: float  # 0-1
    region_type: HandwritingType
    features: List[HandwritingFeature] = field(default_factory=list)

    @property
    def area(self) -> int:
        """Fläche der Region in Pixeln."""
        return self.width * self.height

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Bounding Box als Tuple (x, y, w, h)."""
        return (self.x, self.y, self.width, self.height)

    def overlaps(self, other: "HandwritingRegion", threshold: float = 0.5) -> bool:
        """Prüfe ob zwei Regionen überlappen."""
        x1_start, x1_end = self.x, self.x + self.width
        y1_start, y1_end = self.y, self.y + self.height
        x2_start, x2_end = other.x, other.x + other.width
        y2_start, y2_end = other.y, other.y + other.height

        overlap_x = max(0, min(x1_end, x2_end) - max(x1_start, x2_start))
        overlap_y = max(0, min(y1_end, y2_end) - max(y1_start, y2_start))
        overlap_area = overlap_x * overlap_y

        min_area = min(self.area, other.area)
        if min_area == 0:
            return False

        return (overlap_area / min_area) >= threshold


@dataclass
class HandwritingFeatureScore:
    """Score für ein einzelnes Handschrift-Merkmal."""
    feature: HandwritingFeature
    detected: bool
    confidence: float  # 0-1
    description: str = ""


@dataclass
class HandwritingAnalysis:
    """Vollständige Handschrift-Analyse eines Dokuments."""
    has_handwriting: bool
    handwriting_percentage: float  # 0-100
    confidence: float  # 0-1
    confidence_level: HandwritingConfidence
    primary_type: HandwritingType
    regions: List[HandwritingRegion]
    features: List[HandwritingFeatureScore]
    recommended_backend: str
    confidence_penalty: float  # Confidence-Abzug für OCR
    analysis_details: Dict[str, object]

    @property
    def region_count(self) -> int:
        """Anzahl der handschriftlichen Regionen."""
        return len(self.regions)

    @property
    def total_handwriting_area(self) -> int:
        """Gesamtfläche aller handschriftlichen Regionen."""
        return sum(r.area for r in self.regions)

    @property
    def signature_regions(self) -> List[HandwritingRegion]:
        """Nur Unterschrift-Regionen."""
        return [r for r in self.regions if r.region_type == HandwritingType.SIGNATURE]

    @property
    def annotation_regions(self) -> List[HandwritingRegion]:
        """Nur Anmerkungs-Regionen."""
        return [r for r in self.regions if r.region_type == HandwritingType.ANNOTATION]


# =============================================================================
# Handwriting Pattern Library
# =============================================================================


class HandwritingPatternLibrary:
    """Bibliothek von Handschrift-Erkennungsmustern."""

    # Typische Unterschrift-Positionen (relativ zum Dokument)
    SIGNATURE_ZONES: List[Dict[str, float]] = [
        {"y_start": 0.7, "y_end": 1.0, "x_start": 0.0, "x_end": 0.5},   # Unten links
        {"y_start": 0.7, "y_end": 1.0, "x_start": 0.5, "x_end": 1.0},   # Unten rechts
        {"y_start": 0.85, "y_end": 1.0, "x_start": 0.3, "x_end": 0.7},  # Unten mittig
    ]

    # Textur-Parameter für Handschrift vs. Druck
    TEXTURE_PARAMS = {
        "handwriting": {
            "stroke_width_variance": (0.3, 1.0),   # Hohe Varianz
            "baseline_variance": (2.0, 20.0),      # Ungleichmäßige Grundlinie
            "slant_variance": (5.0, 45.0),         # Variable Neigung
            "spacing_coefficient_variance": (0.2, 0.8),
        },
        "printed": {
            "stroke_width_variance": (0.0, 0.15),  # Niedrige Varianz
            "baseline_variance": (0.0, 1.5),       # Gleichmäßige Grundlinie
            "slant_variance": (0.0, 3.0),          # Minimale Neigung
            "spacing_coefficient_variance": (0.0, 0.1),
        },
    }

    # Mindestgröße für handschriftliche Regionen
    MIN_REGION_SIZE = {
        "signature": (50, 20),       # (width, height) in Pixeln
        "annotation": (30, 15),
        "form_fill": (20, 10),
        "full_handwritten": (100, 50),
    }


# =============================================================================
# Handwriting Detector Agent
# =============================================================================


class HandwritingDetectorAgent(PreprocessingAgent):
    """
    Agent zur Erkennung von handschriftlichen Inhalten.

    Analysiert:
    - Strich-Charakteristik (Breite, Verbindungen)
    - Grundlinien-Varianz
    - Neigungsvariationen
    - Druckvariationen (bei Scans)
    - Positionsmuster (Unterschriften typisch unten)
    """

    # Gewichtung der Erkennungsmethoden
    WEIGHTS = {
        "stroke_analysis": 0.30,
        "baseline_analysis": 0.25,
        "slant_analysis": 0.20,
        "texture_analysis": 0.15,
        "position_analysis": 0.10,
    }

    # Schwellenwerte für Klassifizierung
    THRESHOLDS = {
        "definite_handwriting": 0.85,
        "likely_handwriting": 0.60,
        "partial_handwriting": 0.30,
        "likely_printed": 0.10,
    }

    # Confidence Penalty für handschriftliche Bereiche
    # Handschrift ist schwerer zu OCR-en, daher Confidence-Abzug
    CONFIDENCE_PENALTIES = {
        HandwritingType.FULL_HANDWRITTEN: -0.20,
        HandwritingType.SIGNATURE: -0.15,
        HandwritingType.ANNOTATION: -0.15,
        HandwritingType.FORM_FILL: -0.12,
        HandwritingType.MIXED: -0.10,
        HandwritingType.NONE: 0.0,
    }

    def __init__(self) -> None:
        """Initialisiere Handwriting Detector."""
        super().__init__(name="handwriting_detector")
        self.pattern_library = HandwritingPatternLibrary()
        self._model_loaded = False

        logger.info("HandwritingDetectorAgent initialisiert")

    async def process(self, input_data: Dict[str, object]) -> Dict[str, object]:
        """
        Analysiere Dokument auf handschriftliche Inhalte.

        Args:
            input_data: Dictionary mit:
                - image: numpy array oder Pfad zum Bild
                - metadata: Optional - Dokument-Metadaten
                - detect_signatures: Optional - bool, Unterschriften suchen

        Returns:
            Dictionary mit HandwritingAnalysis
        """
        self.validate_input(input_data, ["image"])

        image = input_data.get("image")
        metadata = input_data.get("metadata", {})
        detect_signatures = input_data.get("detect_signatures", True)

        # Konvertiere Bild falls nötig
        image_array = await self._prepare_image(image)
        if image_array is None:
            return self._create_no_handwriting_result(metadata)

        # Führe verschiedene Analysen durch
        stroke_score = self._analyze_stroke_characteristics(image_array)
        baseline_score = self._analyze_baseline_variance(image_array)
        slant_score = self._analyze_slant_variance(image_array)
        texture_score = self._analyze_texture_patterns(image_array)
        position_score = self._analyze_position_patterns(image_array) if detect_signatures else 0.5

        # Kombiniere Scores
        combined_score = (
            self.WEIGHTS["stroke_analysis"] * stroke_score +
            self.WEIGHTS["baseline_analysis"] * baseline_score +
            self.WEIGHTS["slant_analysis"] * slant_score +
            self.WEIGHTS["texture_analysis"] * texture_score +
            self.WEIGHTS["position_analysis"] * position_score
        )

        # Bestimme Konfidenz-Level
        confidence_level = self._determine_confidence_level(combined_score)

        # Erkenne handschriftliche Regionen
        regions = await self._detect_handwriting_regions(
            image_array,
            detect_signatures=detect_signatures
        )

        # Bestimme primären Handschrift-Typ
        primary_type = self._determine_primary_type(regions, combined_score, image_array)

        # Berechne Handschrift-Anteil
        image_area = image_array.shape[0] * image_array.shape[1]
        handwriting_area = sum(r.area for r in regions)
        handwriting_percentage = (handwriting_area / image_area * 100) if image_area > 0 else 0.0

        # Sammle Feature-Details
        features = self._collect_feature_details(
            stroke_score, baseline_score, slant_score, texture_score
        )

        # Empfehle Backend
        recommended_backend = self._recommend_backend(primary_type, confidence_level)

        # Berechne Confidence Penalty
        confidence_penalty = self.CONFIDENCE_PENALTIES.get(primary_type, 0.0)

        analysis = HandwritingAnalysis(
            has_handwriting=combined_score >= self.THRESHOLDS["likely_printed"],
            handwriting_percentage=round(handwriting_percentage, 2),
            confidence=combined_score,
            confidence_level=confidence_level,
            primary_type=primary_type,
            regions=regions,
            features=features,
            recommended_backend=recommended_backend,
            confidence_penalty=confidence_penalty,
            analysis_details={
                "stroke_score": round(stroke_score, 3),
                "baseline_score": round(baseline_score, 3),
                "slant_score": round(slant_score, 3),
                "texture_score": round(texture_score, 3),
                "position_score": round(position_score, 3),
                "image_dimensions": {"height": image_array.shape[0], "width": image_array.shape[1]},
                "document_metadata": metadata,
            }
        )

        logger.info(
            "handwriting_analysis_complete",
            has_handwriting=analysis.has_handwriting,
            handwriting_percentage=round(analysis.handwriting_percentage, 1),
            confidence=round(analysis.confidence, 3),
            primary_type=analysis.primary_type.value,
            region_count=len(regions),
            recommended_backend=recommended_backend,
            confidence_penalty=confidence_penalty,
        )

        return {
            "analysis": analysis,
            "has_handwriting": analysis.has_handwriting,
            "handwriting_percentage": analysis.handwriting_percentage,
            "primary_type": analysis.primary_type.value,
            "regions": [self._region_to_dict(r) for r in regions],
            "recommended_backend": analysis.recommended_backend,
            "confidence_penalty": analysis.confidence_penalty,
        }

    async def _prepare_image(self, image: Union[str, np.ndarray, object]) -> Optional[np.ndarray]:
        """Konvertiere Eingabe zu numpy array."""
        try:
            if isinstance(image, str):
                # Bild-Pfad - hier würde echtes Laden stattfinden
                try:
                    from PIL import Image
                    pil_image = Image.open(image)
                    return np.array(pil_image)
                except ImportError:
                    logger.warning("PIL nicht verfuegbar, Bild konnte nicht geladen werden")
                    return None
                except Exception as e:
                    logger.warning("image_load_error", path=image, **safe_error_log(e))
                    return None

            if isinstance(image, np.ndarray):
                return image

            # PIL Image
            if hasattr(image, "mode") and hasattr(image, "size"):
                return np.array(image)

            return None

        except Exception as e:
            logger.warning("image_preparation_error", **safe_error_log(e))
            return None

    def _analyze_stroke_characteristics(self, image: np.ndarray) -> float:
        """
        Analysiere Strich-Charakteristiken.

        Handschrift hat:
        - Variable Strichbreite
        - Verbundene Striche (Kursiv)
        - Unregelmäßige Endungen
        """
        try:
            # Grayscale
            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # Binärisierung
            threshold = np.mean(gray)
            binary = (gray < threshold).astype(np.uint8)

            # Berechne lokale Strichbreiten-Varianz
            # Verwende Distanztransformation als Approximation
            try:
                from scipy import ndimage

                # Distanz zum nächsten Hintergrund-Pixel
                dist = ndimage.distance_transform_edt(binary)

                # Nur nicht-null Werte betrachten
                stroke_widths = dist[dist > 0]

                if len(stroke_widths) < 100:
                    return 0.5  # Nicht genug Daten

                # Variationskoeffizient der Strichbreite
                cv = np.std(stroke_widths) / np.mean(stroke_widths) if np.mean(stroke_widths) > 0 else 0

                # Handschrift hat höhere Varianz (CV > 0.3 typisch)
                params = self.pattern_library.TEXTURE_PARAMS
                hw_min, hw_max = params["handwriting"]["stroke_width_variance"]
                pr_min, pr_max = params["printed"]["stroke_width_variance"]

                if cv >= hw_min:
                    return min(0.95, 0.5 + (cv - hw_min) * 0.5)
                elif cv <= pr_max:
                    return max(0.05, 0.5 - (pr_max - cv) * 2)

                return 0.5

            except ImportError:
                return 0.5

        except Exception as e:
            logger.warning("stroke_analysis_error", **safe_error_log(e))
            return 0.5

    def _analyze_baseline_variance(self, image: np.ndarray) -> float:
        """
        Analysiere Grundlinien-Varianz.

        Handschrift hat ungleichmäßige Grundlinien.
        """
        try:
            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # Horizontale Projektion (Zeilenprofil)
            threshold = np.mean(gray)
            binary = (gray < threshold).astype(np.uint8)

            # Summe pro Zeile
            row_sums = np.sum(binary, axis=1)

            # Finde Textzeilen (lokale Maxima)
            from scipy.signal import find_peaks
            try:
                peaks, _ = find_peaks(row_sums, height=np.mean(row_sums), distance=10)
            except Exception:
                peaks = np.where(row_sums > np.mean(row_sums))[0]

            if len(peaks) < 3:
                return 0.5

            # Berechne Abstände zwischen Zeilen
            line_distances = np.diff(peaks)

            if len(line_distances) == 0:
                return 0.5

            # Variationskoeffizient der Zeilenabstände
            cv = np.std(line_distances) / np.mean(line_distances) if np.mean(line_distances) > 0 else 0

            # Handschrift hat höhere Varianz
            if cv > 0.15:
                return min(0.9, 0.5 + cv * 1.5)
            elif cv < 0.05:
                return max(0.1, 0.5 - (0.05 - cv) * 5)

            return 0.5

        except ImportError:
            return 0.5
        except Exception as e:
            logger.warning("baseline_analysis_error", **safe_error_log(e))
            return 0.5

    def _analyze_slant_variance(self, image: np.ndarray) -> float:
        """
        Analysiere Neigungsvarianz.

        Handschrift hat variable Neigung, Druck ist gleichmäßig.
        """
        try:
            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # Gradient in X und Y Richtung
            grad_x = np.gradient(gray.astype(np.float32), axis=1)
            grad_y = np.gradient(gray.astype(np.float32), axis=0)

            # Winkel der Gradienten
            angles = np.arctan2(grad_y, grad_x) * 180 / np.pi

            # Nur signifikante Gradienten betrachten
            magnitude = np.sqrt(grad_x**2 + grad_y**2)
            significant = magnitude > np.percentile(magnitude, 70)

            significant_angles = angles[significant]

            if len(significant_angles) < 100:
                return 0.5

            # Varianz der Winkel
            angle_std = np.std(significant_angles)

            # Handschrift hat höhere Winkel-Varianz
            if angle_std > 30:
                return min(0.9, 0.5 + (angle_std - 30) * 0.01)
            elif angle_std < 15:
                return max(0.1, 0.5 - (15 - angle_std) * 0.02)

            return 0.5

        except Exception as e:
            logger.warning("slant_analysis_error", **safe_error_log(e))
            return 0.5

    def _analyze_texture_patterns(self, image: np.ndarray) -> float:
        """
        Analysiere Texturmuster.

        Handschrift hat charakteristische Texturen:
        - Mehr lokale Varianz
        - Weniger regelmäßige Muster
        """
        try:
            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.float32)
            else:
                gray = image.astype(np.float32)

            try:
                from scipy import ndimage

                # Lokale Varianz
                local_mean = ndimage.uniform_filter(gray, size=7)
                local_sqr_mean = ndimage.uniform_filter(gray**2, size=7)
                local_var = local_sqr_mean - local_mean**2

                # Durchschnittliche lokale Varianz
                mean_local_var = np.mean(local_var)

                # Handschrift hat höhere lokale Varianz
                if mean_local_var > 500:
                    return min(0.85, 0.5 + (mean_local_var - 500) * 0.0003)
                elif mean_local_var < 200:
                    return max(0.15, 0.5 - (200 - mean_local_var) * 0.001)

                return 0.5

            except ImportError:
                return 0.5

        except Exception as e:
            logger.warning("texture_analysis_error", **safe_error_log(e))
            return 0.5

    def _analyze_position_patterns(self, image: np.ndarray) -> float:
        """
        Analysiere typische Positionen für Unterschriften.

        Unterschriften sind häufig:
        - Unten auf der Seite
        - Rechts oder links
        - In definierten Bereichen
        """
        try:
            h, w = image.shape[:2]

            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # Binärisierung
            threshold = np.mean(gray)
            binary = (gray < threshold).astype(np.uint8)

            # Prüfe typische Unterschrift-Zonen
            signature_indicators = 0

            for zone in self.pattern_library.SIGNATURE_ZONES:
                y_start = int(zone["y_start"] * h)
                y_end = int(zone["y_end"] * h)
                x_start = int(zone["x_start"] * w)
                x_end = int(zone["x_end"] * w)

                zone_region = binary[y_start:y_end, x_start:x_end]

                # Berechne Ink-Density in Zone
                ink_density = np.mean(zone_region)

                # Moderate Ink-Density deutet auf Unterschrift hin (nicht leer, nicht voll Text)
                if 0.05 < ink_density < 0.25:
                    # Prüfe auf typische Unterschrift-Eigenschaften
                    # (kompakter Bereich, nicht über volle Breite)
                    col_sums = np.sum(zone_region, axis=0)
                    non_empty_cols = np.sum(col_sums > 0)
                    total_cols = len(col_sums)

                    # Unterschrift nimmt nicht die volle Breite ein
                    if 0.2 < non_empty_cols / total_cols < 0.6:
                        signature_indicators += 1

            if signature_indicators >= 2:
                return 0.8
            elif signature_indicators == 1:
                return 0.65

            return 0.5

        except Exception as e:
            logger.warning("position_analysis_error", **safe_error_log(e))
            return 0.5

    async def _detect_handwriting_regions(
        self,
        image: np.ndarray,
        detect_signatures: bool = True
    ) -> List[HandwritingRegion]:
        """
        Erkenne einzelne handschriftliche Regionen.

        Returns:
            Liste von HandwritingRegion Objekten
        """
        regions: List[HandwritingRegion] = []

        try:
            h, w = image.shape[:2]

            if len(image.shape) == 3:
                gray = np.mean(image, axis=2).astype(np.uint8)
            else:
                gray = image

            # Binärisierung
            threshold = np.mean(gray)
            binary = (gray < threshold).astype(np.uint8)

            try:
                from scipy import ndimage

                # Connected Component Analysis
                labeled, num_features = ndimage.label(binary)

                if num_features == 0:
                    return regions

                # Analysiere jede Komponente
                for i in range(1, min(num_features + 1, 100)):  # Max 100 Regionen
                    component = (labeled == i)

                    # Bounding Box
                    rows = np.any(component, axis=1)
                    cols = np.any(component, axis=0)

                    if not np.any(rows) or not np.any(cols):
                        continue

                    y_min, y_max = np.where(rows)[0][[0, -1]]
                    x_min, x_max = np.where(cols)[0][[0, -1]]

                    region_w = x_max - x_min + 1
                    region_h = y_max - y_min + 1

                    # Zu kleine Regionen ignorieren
                    if region_w < 10 or region_h < 5:
                        continue

                    # Extrahiere Region für Analyse
                    region_image = gray[y_min:y_max+1, x_min:x_max+1]

                    # Analysiere ob handschriftlich
                    hw_score = self._analyze_region_for_handwriting(region_image)

                    if hw_score < 0.4:
                        continue  # Wahrscheinlich gedruckt

                    # Bestimme Region-Typ
                    region_type = self._classify_region_type(
                        x_min, y_min, region_w, region_h, h, w, hw_score
                    )

                    # Features für die Region
                    features = self._detect_region_features(region_image)

                    regions.append(HandwritingRegion(
                        x=int(x_min),
                        y=int(y_min),
                        width=int(region_w),
                        height=int(region_h),
                        confidence=hw_score,
                        region_type=region_type,
                        features=features,
                    ))

                # Merge überlappende Regionen
                regions = self._merge_overlapping_regions(regions)

            except ImportError:
                # Ohne scipy: Einfache Grid-basierte Analyse
                regions = self._detect_regions_simple(gray, h, w)

        except Exception as e:
            logger.warning("region_detection_error", **safe_error_log(e))

        return regions

    def _analyze_region_for_handwriting(self, region_image: np.ndarray) -> float:
        """Analysiere eine Region auf Handschrift-Eigenschaften."""
        try:
            # Vereinfachte Analyse für einzelne Region
            scores = []

            # Strichbreiten-Varianz
            stroke_score = self._analyze_stroke_characteristics(region_image)
            scores.append(stroke_score)

            # Lokale Textur
            texture_score = self._analyze_texture_patterns(region_image)
            scores.append(texture_score)

            return np.mean(scores) if scores else 0.5

        except Exception:
            return 0.5

    def _classify_region_type(
        self,
        x: int, y: int,
        w: int, h: int,
        img_h: int, img_w: int,
        hw_score: float
    ) -> HandwritingType:
        """Klassifiziere den Typ einer handschriftlichen Region."""
        # Relative Position
        rel_y = y / img_h
        rel_w = w / img_w

        # Unterschriften sind typisch:
        # - Im unteren Drittel
        # - Nicht zu breit (< 50% der Seitenbreite)
        if rel_y > 0.6 and rel_w < 0.5:
            return HandwritingType.SIGNATURE

        # Formular-Ausfüllungen:
        # - Kleine, schmale Regionen
        if w < img_w * 0.3 and h < img_h * 0.1:
            return HandwritingType.FORM_FILL

        # Anmerkungen:
        # - Am Rand oder zwischen Text
        if x < img_w * 0.1 or x + w > img_w * 0.9:
            return HandwritingType.ANNOTATION

        # Große Regionen = vollständig handgeschrieben
        if w * h > img_w * img_h * 0.3:
            return HandwritingType.FULL_HANDWRITTEN

        return HandwritingType.ANNOTATION

    def _detect_region_features(self, region_image: np.ndarray) -> List[HandwritingFeature]:
        """Erkenne Handschrift-Features in einer Region."""
        features: List[HandwritingFeature] = []

        try:
            # Baseline-Varianz
            baseline_score = self._analyze_baseline_variance(region_image)
            if baseline_score > 0.6:
                features.append(HandwritingFeature.IRREGULAR_BASELINE)

            # Neigungs-Varianz
            slant_score = self._analyze_slant_variance(region_image)
            if slant_score > 0.6:
                features.append(HandwritingFeature.VARIABLE_SLANT)

            # Strich-Charakteristiken
            stroke_score = self._analyze_stroke_characteristics(region_image)
            if stroke_score > 0.6:
                features.append(HandwritingFeature.CONNECTED_STROKES)
                features.append(HandwritingFeature.PRESSURE_VARIATION)

            # Textur-Muster
            texture_score = self._analyze_texture_patterns(region_image)
            if texture_score > 0.6:
                features.append(HandwritingFeature.IRREGULAR_SPACING)

        except Exception as e:
            logger.debug(
                "handwriting_feature_detection_failed",
                error_type=type(e).__name__,
            )

        return features

    def _detect_regions_simple(
        self,
        gray: np.ndarray,
        h: int, w: int
    ) -> List[HandwritingRegion]:
        """Einfache Region-Detection ohne scipy."""
        regions: List[HandwritingRegion] = []

        # Grid-basierte Analyse
        grid_h, grid_w = 4, 4
        cell_h, cell_w = h // grid_h, w // grid_w

        for gy in range(grid_h):
            for gx in range(grid_w):
                y_start = gy * cell_h
                x_start = gx * cell_w
                cell = gray[y_start:y_start+cell_h, x_start:x_start+cell_w]

                hw_score = self._analyze_region_for_handwriting(cell)

                if hw_score > 0.5:
                    region_type = self._classify_region_type(
                        x_start, y_start, cell_w, cell_h, h, w, hw_score
                    )
                    regions.append(HandwritingRegion(
                        x=x_start,
                        y=y_start,
                        width=cell_w,
                        height=cell_h,
                        confidence=hw_score,
                        region_type=region_type,
                        features=[],
                    ))

        return regions

    def _merge_overlapping_regions(
        self,
        regions: List[HandwritingRegion]
    ) -> List[HandwritingRegion]:
        """Merge überlappende Regionen."""
        if len(regions) <= 1:
            return regions

        merged: List[HandwritingRegion] = []
        used = set()

        for i, r1 in enumerate(regions):
            if i in used:
                continue

            # Finde alle überlappenden Regionen
            group = [r1]
            used.add(i)

            for j, r2 in enumerate(regions):
                if j in used:
                    continue
                if r1.overlaps(r2, threshold=0.3):
                    group.append(r2)
                    used.add(j)

            # Merge Gruppe zu einer Region
            if len(group) == 1:
                merged.append(r1)
            else:
                # Kombiniere Bounding Boxes
                x_min = min(r.x for r in group)
                y_min = min(r.y for r in group)
                x_max = max(r.x + r.width for r in group)
                y_max = max(r.y + r.height for r in group)

                # Durchschnittliche Confidence
                avg_conf = np.mean([r.confidence for r in group])

                # Häufigster Typ
                types = [r.region_type for r in group]
                primary_type = max(set(types), key=types.count)

                # Alle Features
                all_features = list(set(f for r in group for f in r.features))

                merged.append(HandwritingRegion(
                    x=x_min,
                    y=y_min,
                    width=x_max - x_min,
                    height=y_max - y_min,
                    confidence=avg_conf,
                    region_type=primary_type,
                    features=all_features,
                ))

        return merged

    def _determine_primary_type(
        self,
        regions: List[HandwritingRegion],
        overall_score: float,
        image: np.ndarray
    ) -> HandwritingType:
        """Bestimme den primären Handschrift-Typ des Dokuments."""
        if not regions:
            if overall_score < self.THRESHOLDS["likely_printed"]:
                return HandwritingType.NONE
            return HandwritingType.MIXED

        # Berechne Anteil der Typen
        image_area = image.shape[0] * image.shape[1]
        type_areas: Dict[HandwritingType, int] = {}

        for region in regions:
            type_areas[region.region_type] = type_areas.get(region.region_type, 0) + region.area

        # Größter Typ
        if not type_areas:
            return HandwritingType.NONE

        largest_type = max(type_areas, key=type_areas.get)  # type: ignore
        largest_area = type_areas[largest_type]

        # Wenn > 50% des Dokuments handgeschrieben
        if largest_area > image_area * 0.5:
            return HandwritingType.FULL_HANDWRITTEN

        # Wenn nur Unterschriften
        if largest_type == HandwritingType.SIGNATURE and len(type_areas) == 1:
            return HandwritingType.SIGNATURE

        # Wenn mehrere Typen
        if len(type_areas) > 1:
            return HandwritingType.MIXED

        return largest_type

    def _collect_feature_details(
        self,
        stroke_score: float,
        baseline_score: float,
        slant_score: float,
        texture_score: float
    ) -> List[HandwritingFeatureScore]:
        """Sammle Feature-Details für die Analyse."""
        features = []

        features.append(HandwritingFeatureScore(
            feature=HandwritingFeature.CONNECTED_STROKES,
            detected=stroke_score > 0.6,
            confidence=stroke_score,
            description="Verbundene Striche typisch fuer Kursivschrift"
        ))

        features.append(HandwritingFeatureScore(
            feature=HandwritingFeature.IRREGULAR_BASELINE,
            detected=baseline_score > 0.6,
            confidence=baseline_score,
            description="Ungleichmaessige Grundlinie"
        ))

        features.append(HandwritingFeatureScore(
            feature=HandwritingFeature.VARIABLE_SLANT,
            detected=slant_score > 0.6,
            confidence=slant_score,
            description="Variable Schriftneigung"
        ))

        features.append(HandwritingFeatureScore(
            feature=HandwritingFeature.IRREGULAR_SPACING,
            detected=texture_score > 0.6,
            confidence=texture_score,
            description="Ungleichmaessige Buchstabenabstaende"
        ))

        return features

    def _determine_confidence_level(self, score: float) -> HandwritingConfidence:
        """Bestimme Konfidenz-Level basierend auf Score."""
        if score >= self.THRESHOLDS["definite_handwriting"]:
            return HandwritingConfidence.DEFINITE_HANDWRITING
        elif score >= self.THRESHOLDS["likely_handwriting"]:
            return HandwritingConfidence.LIKELY_HANDWRITING
        elif score >= self.THRESHOLDS["partial_handwriting"]:
            return HandwritingConfidence.PARTIAL_HANDWRITING
        elif score >= self.THRESHOLDS["likely_printed"]:
            return HandwritingConfidence.LIKELY_PRINTED
        else:
            return HandwritingConfidence.DEFINITE_PRINTED

    def _recommend_backend(
        self,
        primary_type: HandwritingType,
        confidence_level: HandwritingConfidence
    ) -> str:
        """Empfehle OCR-Backend basierend auf Handschrift-Analyse."""
        # DeepSeek ist am besten für Handschrift
        if primary_type in (
            HandwritingType.FULL_HANDWRITTEN,
            HandwritingType.SIGNATURE,
            HandwritingType.ANNOTATION,
        ):
            return "deepseek"

        if confidence_level in (
            HandwritingConfidence.DEFINITE_HANDWRITING,
            HandwritingConfidence.LIKELY_HANDWRITING,
        ):
            return "deepseek"

        # Für Formular-Ausfüllungen: DeepSeek oder hybrid
        if primary_type == HandwritingType.FORM_FILL:
            return "deepseek"

        # Bei gemischten Dokumenten: DeepSeek
        if primary_type == HandwritingType.MIXED:
            return "deepseek"

        # Rein gedruckte Dokumente: GOT-OCR ist schneller
        if confidence_level == HandwritingConfidence.DEFINITE_PRINTED:
            return "got_ocr"

        # Default: DeepSeek (robuster)
        return "deepseek"

    def _create_no_handwriting_result(
        self,
        metadata: Dict[str, object]
    ) -> Dict[str, object]:
        """Erstelle Ergebnis für Fall ohne erkennbares Bild."""
        analysis = HandwritingAnalysis(
            has_handwriting=False,
            handwriting_percentage=0.0,
            confidence=0.0,
            confidence_level=HandwritingConfidence.DEFINITE_PRINTED,
            primary_type=HandwritingType.NONE,
            regions=[],
            features=[],
            recommended_backend="got_ocr",
            confidence_penalty=0.0,
            analysis_details={"error": "Bild konnte nicht analysiert werden", "metadata": metadata},
        )

        return {
            "analysis": analysis,
            "has_handwriting": False,
            "handwriting_percentage": 0.0,
            "primary_type": HandwritingType.NONE.value,
            "regions": [],
            "recommended_backend": "got_ocr",
            "confidence_penalty": 0.0,
        }

    def _region_to_dict(self, region: HandwritingRegion) -> Dict[str, object]:
        """Konvertiere Region zu Dictionary."""
        return {
            "x": region.x,
            "y": region.y,
            "width": region.width,
            "height": region.height,
            "confidence": round(region.confidence, 3),
            "region_type": region.region_type.value,
            "features": [f.value for f in region.features],
            "area": region.area,
        }


# =============================================================================
# Singleton und Convenience Functions
# =============================================================================


_handwriting_detector: Optional[HandwritingDetectorAgent] = None


def get_handwriting_detector() -> HandwritingDetectorAgent:
    """Hole globale HandwritingDetectorAgent-Instanz."""
    global _handwriting_detector
    if _handwriting_detector is None:
        _handwriting_detector = HandwritingDetectorAgent()
        logger.info("HandwritingDetectorAgent initialisiert")
    return _handwriting_detector


async def detect_handwriting(
    image: Union[str, np.ndarray, object],
    metadata: Optional[Dict[str, object]] = None,
    detect_signatures: bool = True
) -> HandwritingAnalysis:
    """
    Convenience-Funktion zur Handschrift-Erkennung.

    Args:
        image: Bild als numpy array, PIL Image oder Pfad
        metadata: Optional - Dokument-Metadaten
        detect_signatures: Unterschriften suchen

    Returns:
        HandwritingAnalysis mit Ergebnis
    """
    detector = get_handwriting_detector()
    result = await detector.execute({
        "image": image,
        "metadata": metadata or {},
        "detect_signatures": detect_signatures,
    })
    return result["result"]["analysis"]


async def has_handwriting(image: Union[str, np.ndarray, object]) -> bool:
    """Schnelle Prüfung ob Dokument Handschrift enthält."""
    analysis = await detect_handwriting(image)
    return analysis.has_handwriting


async def get_handwriting_regions(
    image: Union[str, np.ndarray, object],
    detect_signatures: bool = True
) -> List[HandwritingRegion]:
    """Hole handschriftliche Regionen aus Dokument."""
    analysis = await detect_handwriting(image, detect_signatures=detect_signatures)
    return analysis.regions


async def get_confidence_penalty(image: Union[str, np.ndarray, object]) -> float:
    """
    Hole Confidence-Penalty basierend auf Handschrift-Anteil.

    Diese Penalty sollte vom OCR-Confidence abgezogen werden,
    da Handschrift generell schwerer zu erkennen ist.
    """
    analysis = await detect_handwriting(image)
    return analysis.confidence_penalty


async def route_to_backend_for_handwriting(image: Union[str, np.ndarray, object]) -> str:
    """Empfehle OCR-Backend basierend auf Handschrift-Erkennung."""
    analysis = await detect_handwriting(image)
    return analysis.recommended_backend
