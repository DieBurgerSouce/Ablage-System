# -*- coding: utf-8 -*-
"""
Tests für den Image Preprocessor Service.

Testet:
- Preprocessing Pipeline (NONE, LIGHT, STANDARD, AGGRESSIVE)
- DPI Normalization
- Deskewing
- Denoising
- Contrast Enhancement (CLAHE)
- Grayscale Conversion
- Quality Improvement Estimation
- PIL Fallback ohne OpenCV
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from PIL import Image
from io import BytesIO

from app.services.image_preprocessor import (
    ImagePreprocessor,
    PreprocessingConfig,
    PreprocessingMode,
    PreprocessingResult,
    get_image_preprocessor,
    preprocess_for_ocr,
    OPENCV_AVAILABLE,
)


class TestPreprocessingConfig:
    """Tests für PreprocessingConfig Dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PreprocessingConfig()

        assert config.mode == PreprocessingMode.STANDARD
        assert config.target_dpi == 300
        assert config.deskew is True
        assert config.denoise is True
        assert config.enhance_contrast is True
        assert config.normalize_illumination is True
        assert config.convert_grayscale is False
        assert config.sharpen is False
        assert config.skew_threshold_degrees == 0.5
        assert config.noise_reduction_strength == 10.0
        assert config.clahe_clip_limit == 2.0
        assert config.clahe_tile_size == (8, 8)

    def test_custom_config(self):
        """Test custom configuration."""
        config = PreprocessingConfig(
            mode=PreprocessingMode.AGGRESSIVE,
            target_dpi=600,
            deskew=False,
            sharpen=True,
        )

        assert config.mode == PreprocessingMode.AGGRESSIVE
        assert config.target_dpi == 600
        assert config.deskew is False
        assert config.sharpen is True


class TestImagePreprocessorInitialization:
    """Tests für Preprocessor Initialisierung."""

    def test_default_initialization(self):
        """Test initialization with defaults."""
        preprocessor = ImagePreprocessor()

        assert preprocessor.config.mode == PreprocessingMode.STANDARD
        assert preprocessor.config.target_dpi == 300

    def test_custom_config_initialization(self):
        """Test initialization with custom config."""
        config = PreprocessingConfig(mode=PreprocessingMode.LIGHT)
        preprocessor = ImagePreprocessor(config)

        assert preprocessor.config.mode == PreprocessingMode.LIGHT

    def test_initialization_logs_opencv_status(self):
        """Test that initialization logs OpenCV availability."""
        with patch("app.services.image_preprocessor.logger") as mock_logger:
            preprocessor = ImagePreprocessor()

            mock_logger.info.assert_called()


class TestPreprocessingModeNone:
    """Tests für NONE Preprocessing Mode."""

    def test_mode_none_returns_original_image(self):
        """Mode NONE should return image unchanged."""
        config = PreprocessingConfig(mode=PreprocessingMode.NONE)
        preprocessor = ImagePreprocessor(config)

        # Create test image
        image = Image.new("RGB", (100, 100), color="white")

        result = preprocessor.process(image)

        assert result.applied_steps == ["none"]
        assert result.original_size == (100, 100)
        assert result.processed_size == (100, 100)
        assert result.processing_time_ms == 0.0


class TestDPIEstimation:
    """Tests für DPI Estimation."""

    def test_estimate_dpi_from_metadata(self):
        """Test DPI extraction from image metadata."""
        preprocessor = ImagePreprocessor()

        # Create image with DPI metadata
        image = Image.new("RGB", (100, 100))
        image.info['dpi'] = (300, 300)

        dpi = preprocessor._estimate_dpi(image)

        assert dpi == 300

    def test_estimate_dpi_high_res(self):
        """High resolution images should estimate 300 DPI."""
        preprocessor = ImagePreprocessor()

        # A4 at ~300dpi is roughly 2480x3508
        image = Image.new("RGB", (2500, 3500))

        dpi = preprocessor._estimate_dpi(image)

        assert dpi == 300

    def test_estimate_dpi_medium_res(self):
        """Medium resolution images should estimate 150 DPI."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (1200, 1600))

        dpi = preprocessor._estimate_dpi(image)

        assert dpi == 150

    def test_estimate_dpi_low_res(self):
        """Low resolution images should estimate 72 DPI."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (800, 600))

        dpi = preprocessor._estimate_dpi(image)

        assert dpi == 72


class TestDPINormalization:
    """Tests für DPI Normalization."""

    def test_normalize_dpi_upscale(self):
        """Test upscaling from 150 to 300 DPI."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (100, 100))

        normalized = preprocessor._normalize_dpi(image, 150, 300)

        # Should be scaled up by 2x
        assert normalized.size == (200, 200)

    def test_normalize_dpi_downscale(self):
        """Test downscaling (limited to 0.5x minimum)."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (100, 100))

        # 600 -> 150 would be 0.25x, but limited to 0.5x
        normalized = preprocessor._normalize_dpi(image, 600, 150)

        assert normalized.size == (50, 50)

    def test_normalize_dpi_skip_same(self):
        """Skip normalization if DPI is the same."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (100, 100))

        normalized = preprocessor._normalize_dpi(image, 300, 300)

        # Should return same size (no scaling)
        assert normalized.size == (100, 100)

    def test_normalize_dpi_skip_near_one(self):
        """Skip normalization if scale factor is near 1.0."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (100, 100))

        # 290 -> 300 is ~1.03x, within 0.1 tolerance
        normalized = preprocessor._normalize_dpi(image, 290, 300)

        assert normalized.size == (100, 100)


class TestProcessPipeline:
    """Tests für die vollständige Processing Pipeline."""

    def test_process_returns_result(self):
        """Test that process returns PreprocessingResult."""
        preprocessor = ImagePreprocessor()
        image = Image.new("RGB", (200, 200), color="white")

        result = preprocessor.process(image)

        assert isinstance(result, PreprocessingResult)
        assert result.image is not None
        assert result.original_size == (200, 200)
        assert result.processing_time_ms >= 0

    def test_process_with_override_config(self):
        """Test processing with override config."""
        preprocessor = ImagePreprocessor(PreprocessingConfig(mode=PreprocessingMode.STANDARD))
        image = Image.new("RGB", (100, 100))

        override_config = PreprocessingConfig(mode=PreprocessingMode.NONE)
        result = preprocessor.process(image, config=override_config)

        # Override should take effect
        assert result.applied_steps == ["none"]

    def test_process_tracks_applied_steps(self):
        """Test that applied steps are recorded."""
        config = PreprocessingConfig(
            mode=PreprocessingMode.STANDARD,
            enhance_contrast=True,
        )
        preprocessor = ImagePreprocessor(config)
        image = Image.new("RGB", (200, 200))

        result = preprocessor.process(image)

        # Should have at least some steps applied
        assert len(result.applied_steps) > 0

    def test_process_grayscale_conversion(self):
        """Test grayscale conversion option."""
        config = PreprocessingConfig(
            mode=PreprocessingMode.LIGHT,
            convert_grayscale=True,
            deskew=False,
            denoise=False,
            enhance_contrast=False,
        )
        preprocessor = ImagePreprocessor(config)

        # Create colored image
        image = Image.new("RGB", (100, 100), color="red")

        result = preprocessor.process(image)

        # Should have grayscale step recorded
        assert "grayscale" in result.applied_steps


class TestQualityEstimation:
    """Tests für Quality Improvement Estimation."""

    def test_estimate_quality_improvement_empty(self):
        """Empty steps should give 0 improvement."""
        preprocessor = ImagePreprocessor()

        improvement = preprocessor._estimate_quality_improvement([])

        assert improvement == 0.0

    def test_estimate_quality_improvement_single_step(self):
        """Single step should give appropriate improvement."""
        preprocessor = ImagePreprocessor()

        # Deskewing gives 5%
        improvement = preprocessor._estimate_quality_improvement(["deskewed:2.5deg"])

        assert improvement == 5.0

    def test_estimate_quality_improvement_multiple_steps(self):
        """Multiple steps should add up."""
        preprocessor = ImagePreprocessor()

        steps = ["deskewed:2.0deg", "denoised", "contrast_enhanced"]
        improvement = preprocessor._estimate_quality_improvement(steps)

        # 5.0 + 3.0 + 4.0 = 12.0
        assert improvement == 12.0

    def test_estimate_quality_improvement_capped(self):
        """Improvement should be capped at 15%."""
        preprocessor = ImagePreprocessor()

        # Many steps
        steps = [
            "deskewed:5deg",
            "denoised",
            "contrast_enhanced",
            "illumination_normalized",
            "sharpened",
            "dpi_normalized:150->300",
        ]
        improvement = preprocessor._estimate_quality_improvement(steps)

        # Total would be 18%, but capped at 15%
        assert improvement == 15.0


class TestPILFallback:
    """Tests für PIL-only Fallback (ohne OpenCV)."""

    def test_enhance_contrast_pil(self):
        """Test PIL-based contrast enhancement."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (100, 100), color="gray")

        enhanced = preprocessor._enhance_contrast_pil(image)

        assert enhanced is not None
        assert enhanced.size == (100, 100)

    @patch("app.services.image_preprocessor.OPENCV_AVAILABLE", False)
    def test_process_without_opencv(self):
        """Test processing pipeline when OpenCV is not available."""
        config = PreprocessingConfig(
            mode=PreprocessingMode.STANDARD,
            enhance_contrast=True,
        )
        preprocessor = ImagePreprocessor(config)

        image = Image.new("RGB", (200, 200))

        # Should not raise, should use PIL fallback
        result = preprocessor.process(image)

        assert result.image is not None


class TestImageConversion:
    """Tests für Bild-Konvertierung."""

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_pil_to_cv2_conversion(self):
        """Test PIL to OpenCV conversion."""
        preprocessor = ImagePreprocessor()

        # Create RGB PIL image
        pil_image = Image.new("RGB", (50, 50), color=(255, 0, 0))  # Red

        cv2_image = preprocessor._pil_to_cv2(pil_image)

        # Should be numpy array
        assert isinstance(cv2_image, np.ndarray)
        assert cv2_image.shape == (50, 50, 3)

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_cv2_to_pil_conversion(self):
        """Test OpenCV to PIL conversion."""
        import cv2

        preprocessor = ImagePreprocessor()

        # Create BGR OpenCV image
        cv2_image = np.zeros((50, 50, 3), dtype=np.uint8)
        cv2_image[:, :, 2] = 255  # Red in BGR

        pil_image = preprocessor._cv2_to_pil(cv2_image)

        assert isinstance(pil_image, Image.Image)
        assert pil_image.size == (50, 50)


class TestDeskewing:
    """Tests für Deskewing."""

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_deskew_straight_image(self):
        """Straight image should have minimal skew."""
        preprocessor = ImagePreprocessor()

        # Create a simple grayscale image
        cv2_image = np.ones((100, 100, 3), dtype=np.uint8) * 255

        result_image, skew_angle = preprocessor._deskew(cv2_image)

        # Should return some angle (possibly 0)
        assert skew_angle is not None or skew_angle == 0.0

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_deskew_no_lines_detected(self):
        """Image with no lines should return original."""
        preprocessor = ImagePreprocessor()

        # Pure white image has no edges
        cv2_image = np.ones((100, 100, 3), dtype=np.uint8) * 255

        result_image, skew_angle = preprocessor._deskew(cv2_image)

        # Should return 0.0 skew for no lines
        assert skew_angle == 0.0


class TestDenoising:
    """Tests für Denoising."""

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_denoise_color_image(self):
        """Test denoising on color image."""
        preprocessor = ImagePreprocessor()

        # Create noisy color image
        cv2_image = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)

        denoised = preprocessor._denoise(cv2_image, strength=10.0)

        assert denoised is not None
        assert denoised.shape == (100, 100, 3)

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_denoise_grayscale_image(self):
        """Test denoising on grayscale image."""
        preprocessor = ImagePreprocessor()

        # Create noisy grayscale image
        cv2_image = np.random.randint(0, 256, (100, 100), dtype=np.uint8)

        denoised = preprocessor._denoise(cv2_image, strength=10.0)

        assert denoised is not None
        assert denoised.shape == (100, 100)


class TestContrastEnhancement:
    """Tests für Contrast Enhancement."""

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_clahe_color_image(self):
        """Test CLAHE on color image."""
        preprocessor = ImagePreprocessor()

        cv2_image = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)

        enhanced = preprocessor._enhance_contrast_clahe(cv2_image)

        assert enhanced is not None
        assert enhanced.shape == (100, 100, 3)

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_clahe_grayscale_image(self):
        """Test CLAHE on grayscale image."""
        preprocessor = ImagePreprocessor()

        cv2_image = np.random.randint(50, 200, (100, 100), dtype=np.uint8)

        enhanced = preprocessor._enhance_contrast_clahe(cv2_image)

        assert enhanced is not None
        assert enhanced.shape == (100, 100)


class TestSharpening:
    """Tests für Sharpening."""

    @pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
    def test_sharpen_image(self):
        """Test image sharpening."""
        preprocessor = ImagePreprocessor()

        cv2_image = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)

        sharpened = preprocessor._sharpen(cv2_image)

        assert sharpened is not None
        assert sharpened.shape == (100, 100, 3)


class TestSingletonAccessor:
    """Tests für Singleton Pattern."""

    def test_get_image_preprocessor_returns_instance(self):
        """Test singleton accessor."""
        preprocessor = get_image_preprocessor()

        assert preprocessor is not None
        assert isinstance(preprocessor, ImagePreprocessor)

    def test_get_image_preprocessor_with_config_creates_new(self):
        """Custom config should create new instance."""
        config = PreprocessingConfig(mode=PreprocessingMode.AGGRESSIVE)

        preprocessor = get_image_preprocessor(config)

        assert preprocessor.config.mode == PreprocessingMode.AGGRESSIVE


class TestConvenienceFunction:
    """Tests für preprocess_for_ocr Convenience Function."""

    def test_preprocess_for_ocr_default(self):
        """Test convenience function with defaults."""
        image = Image.new("RGB", (200, 200), color="white")

        result = preprocess_for_ocr(image)

        assert result is not None
        assert isinstance(result, Image.Image)

    def test_preprocess_for_ocr_with_mode(self):
        """Test convenience function with custom mode."""
        image = Image.new("RGB", (200, 200))

        result = preprocess_for_ocr(image, mode=PreprocessingMode.LIGHT)

        assert result is not None


class TestEdgeCases:
    """Tests für Edge Cases."""

    def test_process_rgba_image(self):
        """Test processing RGBA image (with alpha channel)."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))

        result = preprocessor.process(image)

        # Should handle RGBA without error
        assert result.image is not None

    def test_process_grayscale_input(self):
        """Test processing grayscale input image."""
        preprocessor = ImagePreprocessor()

        image = Image.new("L", (100, 100), color=128)

        result = preprocessor.process(image)

        assert result.image is not None

    def test_process_very_small_image(self):
        """Test processing very small image."""
        preprocessor = ImagePreprocessor()

        image = Image.new("RGB", (10, 10))

        result = preprocessor.process(image)

        assert result.image is not None

    def test_process_very_large_image(self):
        """Test processing large image."""
        preprocessor = ImagePreprocessor()

        # 4000x4000 is large but should still work
        image = Image.new("RGB", (4000, 4000), color="white")

        result = preprocessor.process(image)

        assert result.image is not None
        assert result.processing_time_ms > 0
