"""
Document Analyzer Service for intelligent OCR backend selection.

Analyzes document content and structure to recommend the optimal OCR backend:
- DeepSeek: Best for handwriting, complex layouts, Fraktur
- GOT-OCR: Best for tables, formulas, clean text
- Surya GPU: Best for simple text-only documents (fast)
- Surya (CPU): Fallback for all document types

CRITICAL: Proper backend selection can improve OCR speed by 20-30%.
"""

import io
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from PIL import Image
import structlog

# OpenCV import with fallback
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None
    OPENCV_AVAILABLE = False

# PDF processing
try:
    import pypdfium2 as pdfium
    PDFIUM_AVAILABLE = True
except ImportError:
    pdfium = None
    PDFIUM_AVAILABLE = False

logger = structlog.get_logger(__name__)


class OCRBackend(str, Enum):
    """Available OCR backends."""
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    SURYA_GPU = "surya_gpu"
    SURYA = "surya"  # CPU fallback
    DONUT = "donut"
    HYBRID = "hybrid"


class DocumentType(str, Enum):
    """Document content types."""
    TEXT_ONLY = "text_only"          # Simple text documents
    TEXT_WITH_IMAGES = "text_images"  # Mixed content
    TABLE_HEAVY = "table_heavy"       # Documents with tables
    FORM = "form"                     # Forms with fields
    HANDWRITTEN = "handwritten"       # Handwriting
    HISTORICAL = "historical"         # Old/Fraktur fonts
    TECHNICAL = "technical"           # Formulas, diagrams
    MIXED = "mixed"                   # Complex mixed content
    UNKNOWN = "unknown"


class DocumentComplexity(str, Enum):
    """Document complexity levels."""
    SIMPLE = "simple"      # Single column, clear text
    MODERATE = "moderate"  # Some layout complexity
    COMPLEX = "complex"    # Multi-column, mixed content
    VERY_COMPLEX = "very_complex"  # Historical, damaged, handwritten


@dataclass
class DocumentAnalysisResult:
    """Result of document analysis."""
    document_type: DocumentType
    complexity: DocumentComplexity
    recommended_backend: OCRBackend
    confidence: float  # 0-1, how confident we are in the recommendation
    alternative_backend: Optional[OCRBackend] = None

    # Detected features
    has_tables: bool = False
    has_images: bool = False
    has_handwriting: bool = False
    has_formulas: bool = False
    has_multiple_columns: bool = False
    is_historical: bool = False
    estimated_text_density: float = 0.0  # 0-1
    estimated_noise_level: float = 0.0   # 0-1

    # Image properties
    width: int = 0
    height: int = 0
    dpi_estimate: int = 0
    is_color: bool = True
    page_count: int = 1

    # Analysis metadata
    analysis_time_ms: float = 0.0
    features_detected: List[str] = field(default_factory=list)
    reasoning: str = ""


class DocumentAnalyzer:
    """
    Analyzes documents to recommend optimal OCR backend.

    Uses image analysis and heuristics to detect:
    - Document type (text, tables, forms, etc.)
    - Complexity level
    - Special content (handwriting, formulas, etc.)

    Based on analysis, recommends the best OCR backend.
    """

    # Backend capabilities matrix
    BACKEND_CAPABILITIES = {
        OCRBackend.DEEPSEEK: {
            "handwriting": 0.95,
            "historical": 0.90,
            "complex_layout": 0.85,
            "tables": 0.70,
            "formulas": 0.75,
            "simple_text": 0.80,
            "speed": 0.30,  # Slower
            "german_accuracy": 0.95,
        },
        OCRBackend.GOT_OCR: {
            "handwriting": 0.60,
            "historical": 0.50,
            "complex_layout": 0.75,
            "tables": 0.90,
            "formulas": 0.85,
            "simple_text": 0.85,
            "speed": 0.70,  # Faster
            "german_accuracy": 0.85,
        },
        OCRBackend.SURYA_GPU: {
            "handwriting": 0.40,
            "historical": 0.30,
            "complex_layout": 0.60,
            "tables": 0.65,
            "formulas": 0.50,
            "simple_text": 0.90,
            "speed": 0.90,  # Fast
            "german_accuracy": 0.80,
        },
        OCRBackend.SURYA: {
            "handwriting": 0.35,
            "historical": 0.25,
            "complex_layout": 0.55,
            "tables": 0.60,
            "formulas": 0.45,
            "simple_text": 0.85,
            "speed": 0.50,  # CPU is moderate
            "german_accuracy": 0.75,
        },
    }

    def __init__(self):
        """Initialize document analyzer."""
        logger.info(
            "document_analyzer_initialized",
            opencv_available=OPENCV_AVAILABLE,
            pdfium_available=PDFIUM_AVAILABLE
        )

    def analyze(
        self,
        image: Image.Image,
        language: str = "de",
        prefer_speed: bool = False,
        gpu_available: bool = True
    ) -> DocumentAnalysisResult:
        """
        Analyze document and recommend OCR backend.

        Args:
            image: PIL Image to analyze
            language: Expected document language
            prefer_speed: Prioritize speed over accuracy
            gpu_available: Whether GPU backends are available

        Returns:
            DocumentAnalysisResult with recommendation
        """
        import time
        start_time = time.perf_counter()

        # Basic image properties
        width, height = image.size
        is_color = image.mode in ["RGB", "RGBA"]
        dpi_estimate = self._estimate_dpi(image)

        # Convert for analysis
        if OPENCV_AVAILABLE:
            np_image = self._pil_to_cv2(image)
            gray = cv2.cvtColor(np_image, cv2.COLOR_BGR2GRAY) if len(np_image.shape) == 3 else np_image
        else:
            np_image = np.array(image.convert("L"))
            gray = np_image

        # Feature detection
        features = []
        has_tables = False
        has_images = False
        has_handwriting = False
        has_formulas = False
        has_multiple_columns = False
        is_historical = False
        text_density = 0.0
        noise_level = 0.0

        if OPENCV_AVAILABLE:
            # Detect tables (grid patterns)
            has_tables = self._detect_tables(gray)
            if has_tables:
                features.append("tables")

            # Detect images/figures
            has_images = self._detect_images(np_image)
            if has_images:
                features.append("embedded_images")

            # Detect handwriting characteristics
            has_handwriting = self._detect_handwriting(gray)
            if has_handwriting:
                features.append("handwriting")

            # Detect multi-column layout
            has_multiple_columns = self._detect_multiple_columns(gray)
            if has_multiple_columns:
                features.append("multiple_columns")

            # Detect historical/degraded document
            is_historical = self._detect_historical(gray)
            if is_historical:
                features.append("historical")

            # Estimate text density
            text_density = self._estimate_text_density(gray)
            features.append(f"text_density:{text_density:.2f}")

            # Estimate noise level
            noise_level = self._estimate_noise_level(gray)
            if noise_level > 0.3:
                features.append(f"noisy:{noise_level:.2f}")

        # Determine document type
        doc_type = self._classify_document_type(
            has_tables=has_tables,
            has_images=has_images,
            has_handwriting=has_handwriting,
            has_formulas=has_formulas,
            has_multiple_columns=has_multiple_columns,
            is_historical=is_historical,
            text_density=text_density
        )

        # Determine complexity
        complexity = self._assess_complexity(
            has_tables=has_tables,
            has_images=has_images,
            has_handwriting=has_handwriting,
            has_multiple_columns=has_multiple_columns,
            is_historical=is_historical,
            noise_level=noise_level
        )

        # Recommend backend
        recommended, alternative, confidence, reasoning = self._recommend_backend(
            doc_type=doc_type,
            complexity=complexity,
            language=language,
            prefer_speed=prefer_speed,
            gpu_available=gpu_available,
            features=features
        )

        analysis_time = (time.perf_counter() - start_time) * 1000

        result = DocumentAnalysisResult(
            document_type=doc_type,
            complexity=complexity,
            recommended_backend=recommended,
            confidence=confidence,
            alternative_backend=alternative,
            has_tables=has_tables,
            has_images=has_images,
            has_handwriting=has_handwriting,
            has_formulas=has_formulas,
            has_multiple_columns=has_multiple_columns,
            is_historical=is_historical,
            estimated_text_density=text_density,
            estimated_noise_level=noise_level,
            width=width,
            height=height,
            dpi_estimate=dpi_estimate,
            is_color=is_color,
            page_count=1,
            analysis_time_ms=analysis_time,
            features_detected=features,
            reasoning=reasoning
        )

        logger.info(
            "document_analyzed",
            document_type=doc_type.value,
            complexity=complexity.value,
            recommended_backend=recommended.value,
            confidence=round(confidence, 2),
            features=features,
            analysis_time_ms=round(analysis_time, 2)
        )

        return result

    def _pil_to_cv2(self, image: Image.Image) -> np.ndarray:
        """Convert PIL Image to OpenCV format."""
        if image.mode != "RGB":
            image = image.convert("RGB")
        np_image = np.array(image)
        return cv2.cvtColor(np_image, cv2.COLOR_RGB2BGR)

    def _estimate_dpi(self, image: Image.Image) -> int:
        """Estimate image DPI."""
        if hasattr(image, 'info') and 'dpi' in image.info:
            dpi = image.info['dpi']
            if isinstance(dpi, tuple):
                return int(dpi[0])
            return int(dpi)

        # Heuristic based on size
        width, height = image.size
        if width > 2000 or height > 2000:
            return 300
        elif width > 1000 or height > 1000:
            return 150
        return 72

    def _detect_tables(self, gray: np.ndarray) -> bool:
        """Detect if image contains table structures."""
        if not OPENCV_AVAILABLE:
            return False

        # Detect horizontal and vertical lines
        # Use morphological operations

        # Horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(
            cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1],
            cv2.MORPH_OPEN,
            horizontal_kernel
        )

        # Vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(
            cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1],
            cv2.MORPH_OPEN,
            vertical_kernel
        )

        # Count line intersections
        combined = cv2.add(horizontal_lines, vertical_lines)
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # If we have several intersecting lines, likely a table
        horizontal_count = cv2.countNonZero(horizontal_lines)
        vertical_count = cv2.countNonZero(vertical_lines)

        total_pixels = gray.shape[0] * gray.shape[1]
        line_ratio = (horizontal_count + vertical_count) / total_pixels

        return line_ratio > 0.005 and len(contours) > 4

    def _detect_images(self, image: np.ndarray) -> bool:
        """Detect if document contains embedded images/figures."""
        if not OPENCV_AVAILABLE:
            return False

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

        # Find large contiguous regions that aren't text
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Look for large rectangular regions
        image_area = gray.shape[0] * gray.shape[1]
        large_regions = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area > image_area * 0.05:  # > 5% of image
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                # Images typically have reasonable aspect ratios
                if 0.3 < aspect_ratio < 3.0:
                    large_regions += 1

        return large_regions >= 1

    def _detect_handwriting(self, gray: np.ndarray) -> bool:
        """Detect handwriting characteristics in image."""
        if not OPENCV_AVAILABLE:
            return False

        # Handwriting detection heuristics:
        # 1. High variation in stroke width
        # 2. Non-uniform baseline
        # 3. Connected components with irregular shapes

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

        # Analyze connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

        if num_labels < 10:
            return False

        # Calculate variance in component sizes (handwriting has high variance)
        areas = stats[1:, cv2.CC_STAT_AREA]  # Skip background
        if len(areas) < 5:
            return False

        area_variance = np.std(areas) / (np.mean(areas) + 1e-6)

        # High variance suggests handwriting
        return area_variance > 2.0

    def _detect_multiple_columns(self, gray: np.ndarray) -> bool:
        """Detect multi-column layout."""
        if not OPENCV_AVAILABLE:
            return False

        height, width = gray.shape

        # Project horizontally to find column gaps
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

        # Horizontal projection
        horizontal_projection = np.sum(binary, axis=0)

        # Find gaps (regions with low ink)
        threshold = np.max(horizontal_projection) * 0.1
        gaps = horizontal_projection < threshold

        # Count significant gaps in the middle of the document
        middle_start = width // 4
        middle_end = 3 * width // 4
        middle_gaps = gaps[middle_start:middle_end]

        # Find continuous gap regions
        gap_regions = []
        in_gap = False
        gap_start = 0

        for i, is_gap in enumerate(middle_gaps):
            if is_gap and not in_gap:
                gap_start = i
                in_gap = True
            elif not is_gap and in_gap:
                gap_width = i - gap_start
                if gap_width > width * 0.02:  # Gap > 2% of width
                    gap_regions.append(gap_width)
                in_gap = False

        return len(gap_regions) >= 1

    def _detect_historical(self, gray: np.ndarray) -> bool:
        """Detect historical/degraded document characteristics."""
        if not OPENCV_AVAILABLE:
            return False

        # Historical documents often have:
        # 1. Uneven illumination
        # 2. Faded text
        # 3. Stains/damage

        # Check for low contrast
        contrast = gray.std()
        if contrast < 40:  # Low contrast suggests faded text
            return True

        # Check for uneven illumination
        # Divide image into quadrants and compare brightness
        h, w = gray.shape
        quadrants = [
            gray[:h//2, :w//2].mean(),
            gray[:h//2, w//2:].mean(),
            gray[h//2:, :w//2].mean(),
            gray[h//2:, w//2:].mean()
        ]
        brightness_variance = np.std(quadrants)

        # High variance suggests uneven illumination
        return brightness_variance > 30

    def _estimate_text_density(self, gray: np.ndarray) -> float:
        """Estimate text density (0-1)."""
        if not OPENCV_AVAILABLE:
            return 0.5

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        ink_pixels = cv2.countNonZero(binary)
        total_pixels = gray.shape[0] * gray.shape[1]

        return min(1.0, ink_pixels / total_pixels * 10)  # Scale to 0-1

    def _estimate_noise_level(self, gray: np.ndarray) -> float:
        """Estimate noise level in image (0-1)."""
        if not OPENCV_AVAILABLE:
            return 0.0

        # Use Laplacian variance as noise indicator
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()

        # Normalize to 0-1 range (empirically determined thresholds)
        # Low variance = clean, high variance = noisy
        noise_level = min(1.0, variance / 1000)

        return noise_level

    def _classify_document_type(
        self,
        has_tables: bool,
        has_images: bool,
        has_handwriting: bool,
        has_formulas: bool,
        has_multiple_columns: bool,
        is_historical: bool,
        text_density: float
    ) -> DocumentType:
        """Classify document into type category."""

        if has_handwriting:
            return DocumentType.HANDWRITTEN

        if is_historical:
            return DocumentType.HISTORICAL

        if has_tables:
            if has_images or has_formulas:
                return DocumentType.MIXED
            return DocumentType.TABLE_HEAVY

        if has_formulas:
            return DocumentType.TECHNICAL

        if has_images:
            return DocumentType.TEXT_WITH_IMAGES

        if has_multiple_columns:
            return DocumentType.MIXED

        if text_density > 0.3:
            return DocumentType.TEXT_ONLY

        return DocumentType.UNKNOWN

    def _assess_complexity(
        self,
        has_tables: bool,
        has_images: bool,
        has_handwriting: bool,
        has_multiple_columns: bool,
        is_historical: bool,
        noise_level: float
    ) -> DocumentComplexity:
        """Assess document complexity level."""

        complexity_score = 0

        if has_handwriting:
            complexity_score += 3
        if is_historical:
            complexity_score += 3
        if has_tables:
            complexity_score += 2
        if has_images:
            complexity_score += 1
        if has_multiple_columns:
            complexity_score += 1
        if noise_level > 0.5:
            complexity_score += 2

        if complexity_score >= 5:
            return DocumentComplexity.VERY_COMPLEX
        elif complexity_score >= 3:
            return DocumentComplexity.COMPLEX
        elif complexity_score >= 1:
            return DocumentComplexity.MODERATE
        else:
            return DocumentComplexity.SIMPLE

    def _recommend_backend(
        self,
        doc_type: DocumentType,
        complexity: DocumentComplexity,
        language: str,
        prefer_speed: bool,
        gpu_available: bool,
        features: List[str]
    ) -> Tuple[OCRBackend, Optional[OCRBackend], float, str]:
        """
        Recommend optimal OCR backend based on analysis.

        Returns:
            (recommended_backend, alternative_backend, confidence, reasoning)
        """
        reasoning_parts = []

        # Build requirements based on document type
        requirements = {}

        if doc_type == DocumentType.HANDWRITTEN:
            requirements["handwriting"] = 1.0
            reasoning_parts.append("Handschrift erkannt - DeepSeek empfohlen")

        elif doc_type == DocumentType.HISTORICAL:
            requirements["historical"] = 1.0
            requirements["german_accuracy"] = 0.8
            reasoning_parts.append("Historisches Dokument - DeepSeek für Fraktur")

        elif doc_type == DocumentType.TABLE_HEAVY:
            requirements["tables"] = 1.0
            reasoning_parts.append("Tabellen erkannt - GOT-OCR empfohlen")

        elif doc_type == DocumentType.TECHNICAL:
            requirements["formulas"] = 1.0
            reasoning_parts.append("Technisches Dokument - GOT-OCR für Formeln")

        elif doc_type == DocumentType.TEXT_ONLY:
            requirements["simple_text"] = 1.0
            if prefer_speed:
                requirements["speed"] = 0.8
                reasoning_parts.append("Einfacher Text + Speed-Priorität - Surya GPU")
            else:
                reasoning_parts.append("Einfacher Text - Surya GPU ausreichend")

        elif doc_type in [DocumentType.MIXED, DocumentType.TEXT_WITH_IMAGES]:
            requirements["complex_layout"] = 0.8
            reasoning_parts.append("Komplexes Layout - DeepSeek oder GOT-OCR")

        # Add German language preference
        if language == "de":
            requirements["german_accuracy"] = 0.7
            reasoning_parts.append("Deutsche Sprache priorisiert")

        # Speed preference
        if prefer_speed:
            requirements["speed"] = 0.6

        # Score each backend
        scores = {}
        available_backends = list(OCRBackend)

        if not gpu_available:
            available_backends = [OCRBackend.SURYA]  # CPU only
            reasoning_parts.append("Keine GPU - nur CPU-Backend")

        for backend in available_backends:
            if backend not in self.BACKEND_CAPABILITIES:
                continue

            capabilities = self.BACKEND_CAPABILITIES[backend]
            score = 0.0
            weight_sum = 0.0

            for req_key, req_weight in requirements.items():
                if req_key in capabilities:
                    score += capabilities[req_key] * req_weight
                    weight_sum += req_weight

            if weight_sum > 0:
                scores[backend] = score / weight_sum
            else:
                scores[backend] = 0.5  # Default score

        # Sort by score
        sorted_backends = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if not sorted_backends:
            return OCRBackend.SURYA, None, 0.5, "Fallback auf CPU-Backend"

        recommended = sorted_backends[0][0]
        confidence = sorted_backends[0][1]
        alternative = sorted_backends[1][0] if len(sorted_backends) > 1 else None

        reasoning = " | ".join(reasoning_parts)

        return recommended, alternative, confidence, reasoning


# Singleton instance
_analyzer: Optional[DocumentAnalyzer] = None


def get_document_analyzer() -> DocumentAnalyzer:
    """Get singleton analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = DocumentAnalyzer()
    return _analyzer


def analyze_and_recommend(
    image: Image.Image,
    language: str = "de",
    prefer_speed: bool = False,
    gpu_available: bool = True
) -> Dict[str, Any]:
    """
    Convenience function to analyze document and get recommendation.

    Returns:
        Dict with recommended_backend, document_type, confidence, etc.
    """
    analyzer = get_document_analyzer()
    result = analyzer.analyze(image, language, prefer_speed, gpu_available)

    return {
        "recommended_backend": result.recommended_backend.value,
        "alternative_backend": result.alternative_backend.value if result.alternative_backend else None,
        "document_type": result.document_type.value,
        "complexity": result.complexity.value,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "features": result.features_detected
    }
