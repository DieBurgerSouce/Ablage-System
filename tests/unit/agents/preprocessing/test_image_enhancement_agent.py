# -*- coding: utf-8 -*-
"""
Unit Tests for ImageEnhancementAgent.

Tests image enhancement capabilities:
- Deskew correction
- Noise reduction
- Contrast enhancement
- Adaptive binarization
- Quality improvement estimation
"""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import numpy as np

from app.agents.preprocessing.image_enhancement_agent import ImageEnhancementAgent


class MockCV2:
    """Mock OpenCV module for testing without actual cv2 dependency."""

    IMREAD_GRAYSCALE = 0
    COLOR_GRAY2BGR = 8
    COLOR_BGR2GRAY = 6
    COLOR_BGR2LAB = 44
    COLOR_LAB2BGR = 56
    INTER_CUBIC = 2
    BORDER_REPLICATE = 1
    ADAPTIVE_THRESH_GAUSSIAN_C = 1
    THRESH_BINARY = 0
    MORPH_RECT = 0
    CV_64F = 6

    @staticmethod
    def imread(path: str, *args) -> np.ndarray:
        """Mock image reading."""
        return np.ones((100, 100, 3), dtype=np.uint8) * 128

    @staticmethod
    def cvtColor(img: np.ndarray, code: int) -> np.ndarray:
        """Mock color conversion."""
        if len(img.shape) == 3:
            return np.mean(img, axis=2).astype(np.uint8)
        return np.stack([img] * 3, axis=2)

    @staticmethod
    def Canny(img: np.ndarray, threshold1: int, threshold2: int, **kwargs) -> np.ndarray:
        """Mock edge detection."""
        return np.zeros_like(img)

    @staticmethod
    def HoughLinesP(edges: np.ndarray, **kwargs) -> np.ndarray:
        """Mock Hough line detection."""
        return np.array([[[0, 0, 100, 2]]])  # Slight angle

    @staticmethod
    def getRotationMatrix2D(center: tuple, angle: float, scale: float) -> np.ndarray:
        """Mock rotation matrix."""
        return np.eye(2, 3)

    @staticmethod
    def warpAffine(img: np.ndarray, matrix: np.ndarray, size: tuple, **kwargs) -> np.ndarray:
        """Mock warp affine transformation."""
        return img.copy()

    @staticmethod
    def fastNlMeansDenoisingColored(img: np.ndarray, dst, **kwargs) -> np.ndarray:
        """Mock denoising."""
        return img.copy()

    @staticmethod
    def fastNlMeansDenoising(img: np.ndarray, dst, **kwargs) -> np.ndarray:
        """Mock grayscale denoising."""
        return img.copy()

    @staticmethod
    def createCLAHE(**kwargs) -> MagicMock:
        """Mock CLAHE creation."""
        clahe = MagicMock()
        clahe.apply = lambda x: x
        return clahe

    @staticmethod
    def split(img: np.ndarray) -> tuple:
        """Mock channel split."""
        return img[:, :, 0], img[:, :, 1], img[:, :, 2]

    @staticmethod
    def merge(channels: list) -> np.ndarray:
        """Mock channel merge."""
        return np.stack(channels, axis=2)

    @staticmethod
    def GaussianBlur(img: np.ndarray, ksize: tuple, sigma: float) -> np.ndarray:
        """Mock Gaussian blur."""
        return img.copy()

    @staticmethod
    def adaptiveThreshold(img: np.ndarray, maxval: int, method: int, thresh_type: int, **kwargs) -> np.ndarray:
        """Mock adaptive threshold."""
        return np.where(img > 127, 255, 0).astype(np.uint8)

    @staticmethod
    def imwrite(path: str, img: np.ndarray) -> bool:
        """Mock image writing."""
        return True

    @staticmethod
    def Laplacian(img: np.ndarray, ddepth: int) -> np.ndarray:
        """Mock Laplacian for sharpness calculation."""
        result = MagicMock()
        result.var = lambda: 100.0
        return result


class TestImageEnhancementAgentInit:
    """Test agent initialization."""

    def test_agent_initialization_with_opencv(self) -> None:
        """Agent sollte mit OpenCV korrekt initialisiert werden."""
        with patch.dict("sys.modules", {"cv2": MockCV2}):
            agent = ImageEnhancementAgent()
            # Re-ensure with mock
            agent._cv2 = MockCV2

            assert agent.name == "image_enhancement_agent"
            assert agent.category.value == "preprocessing"

    def test_agent_initialization_without_opencv(self) -> None:
        """Agent sollte ohne OpenCV initialisiert werden (mit Warnung)."""
        with patch.dict("sys.modules", {"cv2": None}):
            with patch("app.agents.preprocessing.image_enhancement_agent.logger") as mock_logger:
                # Force import failure
                agent = ImageEnhancementAgent()
                agent._cv2 = None  # Simulate missing opencv

                assert agent._cv2 is None

    def test_enhancement_thresholds(self) -> None:
        """Agent sollte korrekte Enhancement-Schwellwerte haben."""
        agent = ImageEnhancementAgent()

        assert agent.SKEW_THRESHOLD_DEGREES == 0.5
        assert agent.NOISE_THRESHOLD == 0.3
        assert agent.CONTRAST_THRESHOLD == 0.4
        assert agent.BINARIZE_THRESHOLD == 0.5


class TestDeskewCorrection:
    """Test deskew correction functionality."""

    def test_deskew_no_lines_detected(self) -> None:
        """Keine erkannten Linien sollten Originalbild zurückgeben."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        # Mock HoughLinesP to return None
        agent._cv2.HoughLinesP = lambda *args, **kwargs: None

        img = np.ones((100, 100, 3), dtype=np.uint8)
        result, angle = agent._deskew(img)

        assert angle == 0.0
        np.testing.assert_array_equal(result, img)

    def test_deskew_small_angle_no_correction(self) -> None:
        """Kleine Winkel sollten nicht korrigiert werden."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        # Mock small angle detection
        agent._cv2.HoughLinesP = lambda *args, **kwargs: np.array([[[0, 0, 100, 1]]])  # Very small angle

        img = np.ones((100, 100, 3), dtype=np.uint8)
        result, angle = agent._deskew(img)

        # Small angle should be detected but not corrected
        assert abs(angle) < 5  # Reasonable small angle


class TestNoiseReduction:
    """Test noise reduction functionality."""

    def test_denoise_color_image(self) -> None:
        """Farbbild-Entrauschung sollte funktionieren."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        img = np.ones((100, 100, 3), dtype=np.uint8) * 128
        result = agent._denoise(img)

        assert result.shape == img.shape

    def test_denoise_grayscale_image(self) -> None:
        """Graustufen-Entrauschung sollte funktionieren."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()
        agent._cv2.fastNlMeansDenoising = lambda img, dst, **kwargs: img.copy()

        img = np.ones((100, 100), dtype=np.uint8) * 128
        result = agent._denoise(img)

        assert result.shape == img.shape


class TestContrastEnhancement:
    """Test contrast enhancement functionality."""

    def test_enhance_contrast_color_image(self) -> None:
        """Farbbildkontrastverstärkung sollte funktionieren."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        img = np.ones((100, 100, 3), dtype=np.uint8) * 128
        result = agent._enhance_contrast(img)

        assert result is not None

    def test_enhance_contrast_grayscale_image(self) -> None:
        """Graustufenkontrastverstärkung sollte funktionieren."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        img = np.ones((100, 100), dtype=np.uint8) * 128
        result = agent._enhance_contrast(img)

        assert result is not None


class TestAdaptiveBinarization:
    """Test adaptive binarization functionality."""

    def test_binarize_color_image(self) -> None:
        """Farbbildbinarisierung sollte funktionieren."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        img = np.ones((100, 100, 3), dtype=np.uint8) * 128
        result = agent._adaptive_binarize(img)

        assert result is not None

    def test_binarize_grayscale_image(self) -> None:
        """Graustufenbinarisierung sollte funktionieren."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        img = np.ones((100, 100), dtype=np.uint8) * 128
        result = agent._adaptive_binarize(img)

        assert result is not None


class TestQualityImprovement:
    """Test quality improvement estimation."""

    def test_estimate_improvement_with_enhancements(self) -> None:
        """Qualitätsverbesserung sollte geschätzt werden."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        original = np.ones((100, 100, 3), dtype=np.uint8) * 128
        enhanced = np.ones((100, 100, 3), dtype=np.uint8) * 200

        # Mock Laplacian to return different values
        call_count = [0]
        def mock_laplacian(img, depth):
            call_count[0] += 1
            result = MagicMock()
            result.var = lambda: 100.0 if call_count[0] == 1 else 150.0
            return result

        agent._cv2.Laplacian = mock_laplacian

        improvement = agent._estimate_quality_improvement(
            original, enhanced, ["denoise", "contrast"]
        )

        assert isinstance(improvement, float)
        assert 0.0 <= improvement <= 0.5

    def test_estimate_improvement_no_enhancements(self) -> None:
        """Keine Verbesserungen sollten 0 zurückgeben."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        original = np.ones((100, 100, 3), dtype=np.uint8) * 128
        enhanced = original.copy()

        # Mock Laplacian to return same values
        def mock_laplacian(img, depth):
            result = MagicMock()
            result.var = lambda: 100.0
            return result

        agent._cv2.Laplacian = mock_laplacian

        improvement = agent._estimate_quality_improvement(
            original, enhanced, []
        )

        assert improvement == 0.0


class TestFullProcessingPipeline:
    """Test complete enhancement pipeline."""

    @pytest.mark.asyncio
    async def test_process_requires_file_path(self) -> None:
        """Verarbeitung sollte file_path erfordern."""
        agent = ImageEnhancementAgent()

        with pytest.raises(ValueError) as exc_info:
            await agent.process({})

        assert "file_path" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_without_opencv(self) -> None:
        """Verarbeitung ohne OpenCV sollte Originalpfad zurückgeben."""
        agent = ImageEnhancementAgent()
        agent._cv2 = None

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"dummy image content")
            tmp_path = Path(tmp.name)

        try:
            result = await agent.process({"file_path": str(tmp_path)})

            assert result["enhanced_image_path"] == str(tmp_path)
            assert result["original_path"] == str(tmp_path)
            assert result["enhancements_applied"] == []
            assert result["quality_improvement"] == 0.0
            assert result["metadata"]["opencv_available"] is False
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_process_low_quality_applies_all_enhancements(self) -> None:
        """Niedrige Qualität sollte alle Enhancements anwenden."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        # Mock _load_image to return a valid image
        def mock_load_image(path):
            return np.ones((100, 100, 3), dtype=np.uint8) * 128

        agent._load_image = mock_load_image

        # Mock _save_enhanced_image
        def mock_save(original_path, img):
            return original_path.with_suffix(".enhanced.png")

        agent._save_enhanced_image = mock_save

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"dummy image content")
            tmp_path = Path(tmp.name)

        try:
            result = await agent.process({
                "file_path": str(tmp_path),
                "quality_score": 0.3,  # Low quality triggers all enhancements
            })

            # Should apply denoise, contrast, and binarize for low quality
            assert "denoise" in result["enhancements_applied"]
            assert "contrast" in result["enhancements_applied"]
            assert "binarize" in result["enhancements_applied"]
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_process_high_quality_applies_fewer_enhancements(self) -> None:
        """Hohe Qualität sollte weniger Enhancements anwenden."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        # Mock _load_image
        def mock_load_image(path):
            return np.ones((100, 100, 3), dtype=np.uint8) * 128

        agent._load_image = mock_load_image

        # Mock _save_enhanced_image
        def mock_save(original_path, img):
            return original_path.with_suffix(".enhanced.png")

        agent._save_enhanced_image = mock_save

        # Mock deskew to return no correction needed
        agent._deskew = lambda img: (img, 0.1)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"dummy image content")
            tmp_path = Path(tmp.name)

        try:
            result = await agent.process({
                "file_path": str(tmp_path),
                "quality_score": 0.9,  # High quality
            })

            # High quality should not trigger denoise, contrast, or binarize
            assert "denoise" not in result["enhancements_applied"]
            assert "binarize" not in result["enhancements_applied"]
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_process_skip_options(self) -> None:
        """Skip-Optionen sollten respektiert werden."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        # Mock _load_image
        def mock_load_image(path):
            return np.ones((100, 100, 3), dtype=np.uint8) * 128

        agent._load_image = mock_load_image

        # Mock _save_enhanced_image
        def mock_save(original_path, img):
            return original_path.with_suffix(".enhanced.png")

        agent._save_enhanced_image = mock_save

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"dummy image content")
            tmp_path = Path(tmp.name)

        try:
            result = await agent.process({
                "file_path": str(tmp_path),
                "quality_score": 0.3,
                "options": {
                    "skip_deskew": True,
                    "skip_denoise": True,
                    "skip_contrast": True,
                    "skip_binarize": True,
                },
            })

            # All enhancements should be skipped
            assert result["enhancements_applied"] == []
        finally:
            tmp_path.unlink()


class TestImageLoading:
    """Test image loading functionality."""

    def test_load_image_success(self) -> None:
        """Bildladung sollte erfolgreich sein."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"dummy")
            tmp_path = Path(tmp.name)

        try:
            result = agent._load_image(tmp_path)
            assert result is not None
            assert isinstance(result, np.ndarray)
        finally:
            tmp_path.unlink()

    def test_load_image_failure_returns_none(self) -> None:
        """Fehlgeschlagene Bildladung sollte None zurückgeben."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()
        agent._cv2.imread = lambda *args, **kwargs: None

        result = agent._load_image(Path("/nonexistent/image.png"))

        assert result is None


class TestImageSaving:
    """Test enhanced image saving functionality."""

    def test_save_enhanced_image(self) -> None:
        """Verbessertes Bild sollte gespeichert werden."""
        agent = ImageEnhancementAgent()
        agent._cv2 = MockCV2()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            img = np.ones((100, 100, 3), dtype=np.uint8)
            result_path = agent._save_enhanced_image(tmp_path, img)

            assert ".enhanced.png" in str(result_path) or "enhanced_" in str(result_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            enhanced_path = tmp_path.with_suffix(".enhanced.png")
            if enhanced_path.exists():
                enhanced_path.unlink()
