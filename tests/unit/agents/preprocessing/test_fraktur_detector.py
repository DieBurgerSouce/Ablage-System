# -*- coding: utf-8 -*-
"""
Unit tests for Fraktur Script Detection Agent.

Tests Fraktur detection, visual analysis,
and OCR backend recommendations.
"""

import pytest
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from app.agents.preprocessing.fraktur_detector import (
    FrakturDetectorAgent,
    FrakturAnalysis,
    FrakturFeatureScore,
    FrakturConfidence,
    FrakturFeature,
    FrakturPatternLibrary,
    get_fraktur_detector,
    detect_fraktur,
    is_fraktur,
    get_recommended_backend,
)


@pytest.mark.unit
class TestFrakturConfidence:
    """Test FrakturConfidence enum."""

    def test_confidence_levels(self):
        """Test all confidence levels exist."""
        assert FrakturConfidence.DEFINITE_FRAKTUR.value == "definite_fraktur"
        assert FrakturConfidence.LIKELY_FRAKTUR.value == "likely_fraktur"
        assert FrakturConfidence.MIXED.value == "mixed"
        assert FrakturConfidence.LIKELY_ANTIQUA.value == "likely_antiqua"
        assert FrakturConfidence.DEFINITE_ANTIQUA.value == "definite_antiqua"


@pytest.mark.unit
class TestFrakturFeature:
    """Test FrakturFeature enum."""

    def test_feature_types(self):
        """Test all feature types exist."""
        features = [
            FrakturFeature.LONG_S,
            FrakturFeature.ROUND_R,
            FrakturFeature.LIGATURES,
            FrakturFeature.BROKEN_STROKES,
            FrakturFeature.BLACKLETTER_STYLE,
        ]

        for feature in features:
            assert isinstance(feature.value, str)


@pytest.mark.unit
class TestFrakturFeatureScore:
    """Test FrakturFeatureScore dataclass."""

    def test_feature_score_creation(self):
        """Test creating a feature score."""
        score = FrakturFeatureScore(
            feature=FrakturFeature.LONG_S,
            detected=True,
            confidence=0.9,
            occurrences=5,
            positions=[(10, 20, 5, 8)],
        )

        assert score.feature == FrakturFeature.LONG_S
        assert score.detected
        assert score.confidence == 0.9
        assert score.occurrences == 5

    def test_feature_not_detected(self):
        """Test feature not detected."""
        score = FrakturFeatureScore(
            feature=FrakturFeature.ROUND_R,
            detected=False,
            confidence=0.0,
            occurrences=0,
        )

        assert not score.detected
        assert score.confidence == 0.0


@pytest.mark.unit
class TestFrakturAnalysis:
    """Test FrakturAnalysis dataclass."""

    def test_analysis_creation(self):
        """Test creating an analysis result."""
        features = [
            FrakturFeatureScore(
                feature=FrakturFeature.LONG_S,
                detected=True,
                confidence=0.8,
                occurrences=3,
            ),
            FrakturFeatureScore(
                feature=FrakturFeature.BROKEN_STROKES,
                detected=True,
                confidence=0.7,
                occurrences=0,
            ),
        ]

        analysis = FrakturAnalysis(
            is_fraktur=True,
            confidence=0.85,
            confidence_level=FrakturConfidence.LIKELY_FRAKTUR,
            features=features,
            recommended_backend="deepseek",
            analysis_details={"visual_score": 0.8},
        )

        assert analysis.is_fraktur
        assert analysis.confidence == 0.85
        assert analysis.recommended_backend == "deepseek"
        assert analysis.total_fraktur_indicators == 2

    def test_feature_summary(self):
        """Test feature_summary property."""
        features = [
            FrakturFeatureScore(
                feature=FrakturFeature.LONG_S,
                detected=True,
                confidence=0.9,
                occurrences=5,
            ),
            FrakturFeatureScore(
                feature=FrakturFeature.ROUND_R,
                detected=False,
                confidence=0.1,
                occurrences=0,
            ),
        ]

        analysis = FrakturAnalysis(
            is_fraktur=True,
            confidence=0.8,
            confidence_level=FrakturConfidence.LIKELY_FRAKTUR,
            features=features,
            recommended_backend="deepseek",
            analysis_details={},
        )

        summary = analysis.feature_summary

        assert summary["long_s"] == True
        assert summary["round_r"] == False


@pytest.mark.unit
class TestFrakturPatternLibrary:
    """Test FrakturPatternLibrary class."""

    def test_unicode_chars_defined(self):
        """Test Fraktur Unicode chars are defined."""
        library = FrakturPatternLibrary()

        assert "\u017f" in library.FRAKTUR_UNICODE_CHARS  # ſ
        assert "\ua75b" in library.FRAKTUR_UNICODE_CHARS  # ꝛ

    def test_ligatures_defined(self):
        """Test Fraktur ligatures are defined."""
        library = FrakturPatternLibrary()

        assert "ch" in library.FRAKTUR_LIGATURES
        assert "ck" in library.FRAKTUR_LIGATURES
        assert "tz" in library.FRAKTUR_LIGATURES

    def test_era_indicators_defined(self):
        """Test era indicators are defined."""
        library = FrakturPatternLibrary()

        assert "Thür" in library.FRAKTUR_ERA_INDICATORS
        assert "daß" in library.FRAKTUR_ERA_INDICATORS


@pytest.mark.unit
class TestFrakturDetectorAgent:
    """Test FrakturDetectorAgent class."""

    def setup_method(self):
        """Setup before each test."""
        self.detector = FrakturDetectorAgent()

    def test_agent_initialization(self):
        """Test agent initialization."""
        assert self.detector.name == "fraktur_detector"
        assert self.detector.pattern_library is not None

    @pytest.mark.asyncio
    async def test_process_with_image(self):
        """Test processing with image input."""
        # Create a simple test image (grayscale)
        image = np.random.randint(0, 255, (100, 200), dtype=np.uint8)

        result = await self.detector.process({
            "image": image,
            "text": "",
            "metadata": {},
        })

        assert "analysis" in result
        assert "is_fraktur" in result
        assert "confidence" in result
        assert "recommended_backend" in result

    @pytest.mark.asyncio
    async def test_process_with_text(self):
        """Test processing with text containing Fraktur chars."""
        image = np.zeros((100, 200), dtype=np.uint8)

        # Text with Fraktur-era indicators
        text = "Der Thür und das Thor, daß er kommen muß."

        result = await self.detector.process({
            "image": image,
            "text": text,
            "metadata": {},
        })

        assert "analysis" in result
        # Should detect Fraktur-era text
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_process_with_long_s(self):
        """Test processing with long s character."""
        image = np.zeros((100, 200), dtype=np.uint8)

        # Text with long s
        text = "daſs er kommt"  # ſ is long s

        result = await self.detector.process({
            "image": image,
            "text": text,
            "metadata": {},
        })

        assert result["is_fraktur"] or result["confidence"] > 0.3

    @pytest.mark.asyncio
    async def test_process_modern_text(self):
        """Test processing modern text."""
        image = np.random.randint(0, 255, (100, 200), dtype=np.uint8)

        text = "Das ist ein moderner deutscher Text."

        result = await self.detector.process({
            "image": image,
            "text": text,
            "metadata": {},
        })

        # Modern text should have low Fraktur confidence
        assert result["confidence"] < 0.7

    @pytest.mark.asyncio
    async def test_unicode_char_analysis(self):
        """Test Unicode character analysis."""
        # Test _analyze_unicode_chars method
        text_with_fraktur = "Teſt"  # with long s
        score = self.detector._analyze_unicode_chars(text_with_fraktur)

        assert score > 0

        text_modern = "Test"
        score_modern = self.detector._analyze_unicode_chars(text_modern)

        assert score_modern == 0

    @pytest.mark.asyncio
    async def test_text_pattern_analysis(self):
        """Test text pattern analysis."""
        # Historical text patterns
        text_historical = "Die Thür des Thales und der Muth."
        score = self.detector._analyze_text_patterns(text_historical)

        assert score > 0

        text_modern = "Die Tür des Tals und der Mut."
        score_modern = self.detector._analyze_text_patterns(text_modern)

        assert score_modern < score

    def test_confidence_level_determination(self):
        """Test confidence level determination."""
        # High confidence
        level = self.detector._determine_confidence_level(0.95)
        assert level == FrakturConfidence.DEFINITE_FRAKTUR

        # Medium confidence
        level = self.detector._determine_confidence_level(0.75)
        assert level == FrakturConfidence.LIKELY_FRAKTUR

        # Mixed
        level = self.detector._determine_confidence_level(0.55)
        assert level == FrakturConfidence.MIXED

        # Low confidence
        level = self.detector._determine_confidence_level(0.25)
        assert level == FrakturConfidence.LIKELY_ANTIQUA

        # Very low confidence
        level = self.detector._determine_confidence_level(0.05)
        assert level == FrakturConfidence.DEFINITE_ANTIQUA

    def test_backend_recommendation(self):
        """Test backend recommendation logic."""
        # Definite Fraktur -> DeepSeek
        backend = self.detector._recommend_backend(
            0.95, FrakturConfidence.DEFINITE_FRAKTUR
        )
        assert backend == "deepseek"

        # Likely Fraktur -> DeepSeek
        backend = self.detector._recommend_backend(
            0.8, FrakturConfidence.LIKELY_FRAKTUR
        )
        assert backend == "deepseek"

        # Definite Antiqua -> GOT-OCR
        backend = self.detector._recommend_backend(
            0.05, FrakturConfidence.DEFINITE_ANTIQUA
        )
        assert backend == "got_ocr"


@pytest.mark.unit
class TestVisualAnalysis:
    """Test visual analysis methods."""

    def setup_method(self):
        """Setup before each test."""
        self.detector = FrakturDetectorAgent()

    @pytest.mark.asyncio
    async def test_visual_features_grayscale(self):
        """Test visual analysis with grayscale image."""
        # Create simple grayscale image
        image = np.random.randint(50, 200, (100, 200), dtype=np.uint8)

        score = await self.detector._analyze_visual_features(image)

        assert 0 <= score <= 1

    @pytest.mark.asyncio
    async def test_visual_features_color(self):
        """Test visual analysis with color image."""
        # Create color image (RGB)
        image = np.random.randint(50, 200, (100, 200, 3), dtype=np.uint8)

        score = await self.detector._analyze_visual_features(image)

        assert 0 <= score <= 1

    @pytest.mark.asyncio
    async def test_visual_features_invalid(self):
        """Test visual analysis with invalid input."""
        # String path (not actual image)
        score = await self.detector._analyze_visual_features("/path/to/image.png")

        # Should return neutral score
        assert score == 0.5

    def test_stroke_pattern_analysis(self):
        """Test stroke pattern analysis."""
        # Create test image
        image = np.random.randint(50, 200, (100, 200), dtype=np.uint8)

        score = self.detector._analyze_stroke_patterns(image)

        assert 0 <= score <= 1

    def test_vertical_emphasis_analysis(self):
        """Test vertical emphasis analysis."""
        # Create test image with vertical lines
        image = np.zeros((100, 200), dtype=np.uint8)
        image[:, ::10] = 255  # Vertical stripes

        score = self.detector._analyze_vertical_emphasis(image)

        assert 0 <= score <= 1


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_fraktur_detector_singleton(self):
        """Test singleton pattern."""
        detector1 = get_fraktur_detector()
        detector2 = get_fraktur_detector()

        assert detector1 is detector2

    @pytest.mark.asyncio
    async def test_detect_fraktur_function(self):
        """Test detect_fraktur convenience function."""
        image = np.zeros((100, 200), dtype=np.uint8)

        analysis = await detect_fraktur(image, text="Test")

        assert isinstance(analysis, FrakturAnalysis)

    @pytest.mark.asyncio
    async def test_is_fraktur_function(self):
        """Test is_fraktur convenience function."""
        image = np.zeros((100, 200), dtype=np.uint8)

        result = await is_fraktur(image, text="Modern text")

        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_get_recommended_backend_function(self):
        """Test get_recommended_backend convenience function."""
        image = np.zeros((100, 200), dtype=np.uint8)

        backend = await get_recommended_backend(image, text="Test")

        assert backend in ["deepseek", "got_ocr", "surya", "surya_gpu"]


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Setup before each test."""
        self.detector = FrakturDetectorAgent()

    @pytest.mark.asyncio
    async def test_empty_text(self):
        """Test with empty text."""
        image = np.zeros((100, 200), dtype=np.uint8)

        result = await self.detector.process({
            "image": image,
            "text": "",
            "metadata": {},
        })

        assert "analysis" in result

    @pytest.mark.asyncio
    async def test_very_small_image(self):
        """Test with very small image."""
        image = np.zeros((10, 10), dtype=np.uint8)

        result = await self.detector.process({
            "image": image,
            "text": "",
            "metadata": {},
        })

        assert "analysis" in result

    def test_analyze_unicode_empty(self):
        """Test unicode analysis with empty string."""
        score = self.detector._analyze_unicode_chars("")

        assert score == 0.0

    def test_analyze_patterns_empty(self):
        """Test pattern analysis with empty string."""
        score = self.detector._analyze_text_patterns("")

        assert score == 0.0
