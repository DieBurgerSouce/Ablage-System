# -*- coding: utf-8 -*-
"""
Image Enhancement Agent for Ablage-System.

Enterprise-grade image preprocessing for optimal OCR results:
- Deskew correction (straighten rotated documents)
- Noise reduction (remove scanning artifacts)
- Contrast enhancement (improve text visibility)
- Adaptive binarization (for low-quality scans)

Feinpoliert und durchdacht - Optimale Bildqualität für deutsche Dokumente.
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.agents.base import PreprocessingAgent

logger = structlog.get_logger(__name__)


class ImageEnhancementAgent(PreprocessingAgent):
    """
    Image enhancement agent for pre-OCR processing.

    Applies intelligent image preprocessing to maximize OCR accuracy:
    - Automatic deskew correction using Hough line detection
    - Adaptive noise reduction preserving text edges
    - CLAHE contrast enhancement for better text/background separation
    - Binarization for severely degraded documents
    """

    # Enhancement thresholds
    SKEW_THRESHOLD_DEGREES: float = 0.5  # Minimum skew to correct
    NOISE_THRESHOLD: float = 0.3  # Quality threshold for noise reduction
    CONTRAST_THRESHOLD: float = 0.4  # Quality threshold for contrast enhancement
    BINARIZE_THRESHOLD: float = 0.5  # Quality threshold for binarization

    def __init__(self):
        """Initialize the Image Enhancement Agent."""
        super().__init__(name="image_enhancement_agent")
        self._cv2 = None
        self._ensure_opencv()

    def _ensure_opencv(self) -> None:
        """Ensure OpenCV is available."""
        try:
            import cv2
            self._cv2 = cv2
        except ImportError:
            logger.warning("OpenCV not available - image enhancement limited")
            self._cv2 = None

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance document image for optimal OCR.

        Args:
            input_data: Dictionary containing:
                - file_path: Path to image file
                - quality_score: Optional quality score from classification
                - options: Optional enhancement options

        Returns:
            Enhancement result containing:
                - enhanced_image_path: Path to enhanced image
                - original_path: Path to original image
                - enhancements_applied: List of applied enhancements
                - quality_improvement: Estimated quality improvement
                - metadata: Enhancement metadata
        """
        self.validate_input(input_data, ["file_path"])

        file_path = Path(input_data["file_path"])
        quality_score = input_data.get("quality_score", 0.7)
        options = input_data.get("options", {})

        self.logger.info(
            "image_enhancement_started",
            file_path=str(file_path),
            quality_score=quality_score,
        )

        # If OpenCV not available, return original
        if self._cv2 is None:
            self.logger.warning("opencv_not_available_skipping_enhancement")
            return {
                "enhanced_image_path": str(file_path),
                "original_path": str(file_path),
                "enhancements_applied": [],
                "quality_improvement": 0.0,
                "metadata": {"opencv_available": False},
            }

        # Load image
        img = self._load_image(file_path)
        if img is None:
            return {
                "enhanced_image_path": str(file_path),
                "original_path": str(file_path),
                "enhancements_applied": [],
                "quality_improvement": 0.0,
                "metadata": {"error": "Konnte Bild nicht laden"},
            }

        enhancements_applied = []
        original_img = img.copy()

        # Step 1: Deskew correction
        if not options.get("skip_deskew", False):
            img, skew_angle = self._deskew(img)
            if abs(skew_angle) > self.SKEW_THRESHOLD_DEGREES:
                enhancements_applied.append(f"deskew_{skew_angle:.1f}°")

        # Step 2: Noise reduction (for lower quality images)
        if quality_score < 0.7 and not options.get("skip_denoise", False):
            img = self._denoise(img)
            enhancements_applied.append("denoise")

        # Step 3: Contrast enhancement
        if quality_score < 0.8 and not options.get("skip_contrast", False):
            img = self._enhance_contrast(img)
            enhancements_applied.append("contrast")

        # Step 4: Adaptive binarization (for very low quality)
        if quality_score < self.BINARIZE_THRESHOLD and not options.get("skip_binarize", False):
            img = self._adaptive_binarize(img)
            enhancements_applied.append("binarize")

        # Save enhanced image
        output_path = self._save_enhanced_image(file_path, img)

        # Calculate quality improvement estimate
        quality_improvement = self._estimate_quality_improvement(
            original_img, img, enhancements_applied
        )

        result = {
            "enhanced_image_path": str(output_path),
            "original_path": str(file_path),
            "enhancements_applied": enhancements_applied,
            "quality_improvement": round(quality_improvement, 2),
            "metadata": {
                "original_shape": original_img.shape,
                "enhanced_shape": img.shape,
                "enhancement_count": len(enhancements_applied),
            },
        }

        self.logger.info(
            "image_enhancement_completed",
            enhancements=enhancements_applied,
            quality_improvement=quality_improvement,
        )

        return result

    def _load_image(self, file_path: Path) -> Optional[np.ndarray]:
        """Load image from file."""
        try:
            img = self._cv2.imread(str(file_path))
            if img is None:
                # Try loading as grayscale
                img = self._cv2.imread(str(file_path), self._cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    img = self._cv2.cvtColor(img, self._cv2.COLOR_GRAY2BGR)
            return img
        except Exception as e:
            self.logger.error(
                "image_load_failed",
                file_path=str(file_path),
                error=str(e),
            )
            return None

    def _deskew(self, img: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Correct image skew using Hough line detection.

        Returns (corrected_image, skew_angle_degrees).
        """
        try:
            # Convert to grayscale for edge detection
            gray = self._cv2.cvtColor(img, self._cv2.COLOR_BGR2GRAY)

            # Edge detection
            edges = self._cv2.Canny(gray, 50, 150, apertureSize=3)

            # Hough line detection
            lines = self._cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=100,
                minLineLength=100,
                maxLineGap=10,
            )

            if lines is None or len(lines) == 0:
                return img, 0.0

            # Calculate angles of detected lines
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                # Only consider near-horizontal lines (-45° to +45°)
                if -45 <= angle <= 45:
                    angles.append(angle)

            if not angles:
                return img, 0.0

            # Use median angle for robustness
            median_angle = np.median(angles)

            # Only correct if skew is significant
            if abs(median_angle) < self.SKEW_THRESHOLD_DEGREES:
                return img, median_angle

            # Rotate image to correct skew
            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            rotation_matrix = self._cv2.getRotationMatrix2D(center, median_angle, 1.0)
            corrected = self._cv2.warpAffine(
                img,
                rotation_matrix,
                (w, h),
                flags=self._cv2.INTER_CUBIC,
                borderMode=self._cv2.BORDER_REPLICATE,
            )

            return corrected, median_angle

        except Exception as e:
            self.logger.warning(
                "deskew_failed",
                error=str(e),
            )
            return img, 0.0

    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """
        Apply noise reduction preserving text edges.

        Uses Non-local Means Denoising for best results.
        """
        try:
            # Use fastNlMeansDenoisingColored for color images
            if len(img.shape) == 3:
                denoised = self._cv2.fastNlMeansDenoisingColored(
                    img,
                    None,
                    h=10,  # Filter strength
                    hForColorComponents=10,
                    templateWindowSize=7,
                    searchWindowSize=21,
                )
            else:
                denoised = self._cv2.fastNlMeansDenoising(
                    img,
                    None,
                    h=10,
                    templateWindowSize=7,
                    searchWindowSize=21,
                )
            return denoised

        except Exception as e:
            self.logger.warning(
                "denoise_failed",
                error=str(e),
            )
            return img

    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """
        Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization).

        CLAHE provides better results than global histogram equalization
        for document images with varying illumination.
        """
        try:
            # Convert to LAB color space for better contrast enhancement
            if len(img.shape) == 3:
                lab = self._cv2.cvtColor(img, self._cv2.COLOR_BGR2LAB)
                l_channel, a_channel, b_channel = self._cv2.split(lab)

                # Apply CLAHE to L channel only
                clahe = self._cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l_channel = clahe.apply(l_channel)

                # Merge channels and convert back
                lab = self._cv2.merge([l_channel, a_channel, b_channel])
                enhanced = self._cv2.cvtColor(lab, self._cv2.COLOR_LAB2BGR)
            else:
                # Grayscale image
                clahe = self._cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                enhanced = clahe.apply(img)

            return enhanced

        except Exception as e:
            self.logger.warning(
                "contrast_enhancement_failed",
                error=str(e),
            )
            return img

    def _adaptive_binarize(self, img: np.ndarray) -> np.ndarray:
        """
        Apply adaptive binarization for low-quality scans.

        Uses Otsu's method with Gaussian blur for optimal threshold selection.
        """
        try:
            # Convert to grayscale if needed
            if len(img.shape) == 3:
                gray = self._cv2.cvtColor(img, self._cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()

            # Apply Gaussian blur to reduce noise
            blurred = self._cv2.GaussianBlur(gray, (5, 5), 0)

            # Adaptive thresholding works better for documents
            binary = self._cv2.adaptiveThreshold(
                blurred,
                255,
                self._cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                self._cv2.THRESH_BINARY,
                blockSize=11,
                C=2,
            )

            # Convert back to BGR for consistency
            if len(img.shape) == 3:
                binary = self._cv2.cvtColor(binary, self._cv2.COLOR_GRAY2BGR)

            return binary

        except Exception as e:
            self.logger.warning(
                "binarization_failed",
                error=str(e),
            )
            return img

    def _save_enhanced_image(self, original_path: Path, img: np.ndarray) -> Path:
        """Save enhanced image to temporary file."""
        try:
            # Create output path with .enhanced suffix
            output_path = original_path.with_suffix(".enhanced.png")

            # If we can't write to the same directory, use temp directory
            try:
                self._cv2.imwrite(str(output_path), img)
            except Exception:
                # Fall back to temp directory
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False, prefix="enhanced_"
                ) as tmp:
                    output_path = Path(tmp.name)
                    self._cv2.imwrite(str(output_path), img)

            return output_path

        except Exception as e:
            self.logger.error(
                "save_enhanced_failed",
                error=str(e),
            )
            return original_path

    def _estimate_quality_improvement(
        self,
        original: np.ndarray,
        enhanced: np.ndarray,
        enhancements: List[str],
    ) -> float:
        """
        Estimate quality improvement from enhancements.

        Uses variance of Laplacian as a proxy for image sharpness/quality.
        """
        try:
            # Convert to grayscale for comparison
            if len(original.shape) == 3:
                orig_gray = self._cv2.cvtColor(original, self._cv2.COLOR_BGR2GRAY)
            else:
                orig_gray = original

            if len(enhanced.shape) == 3:
                enh_gray = self._cv2.cvtColor(enhanced, self._cv2.COLOR_BGR2GRAY)
            else:
                enh_gray = enhanced

            # Calculate Laplacian variance (measure of sharpness)
            orig_laplacian = self._cv2.Laplacian(orig_gray, self._cv2.CV_64F).var()
            enh_laplacian = self._cv2.Laplacian(enh_gray, self._cv2.CV_64F).var()

            # Calculate improvement ratio
            if orig_laplacian > 0:
                improvement = (enh_laplacian - orig_laplacian) / orig_laplacian
            else:
                improvement = 0.1 if enhancements else 0.0

            # Bound the improvement estimate
            return max(0.0, min(0.5, improvement))

        except Exception as e:
            self.logger.warning(
                "quality_estimation_failed",
                error=str(e),
            )
            # Estimate based on number of enhancements applied
            return min(0.3, len(enhancements) * 0.1)
