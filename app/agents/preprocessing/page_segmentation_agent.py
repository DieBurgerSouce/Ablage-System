# -*- coding: utf-8 -*-
"""
Page Segmentation Agent for Ablage-System.

Enterprise-grade document page segmentation:
- Multi-page PDF extraction and rendering
- Region of interest (ROI) detection
- Text block segmentation
- Table region detection
- Image region detection
- Reading order determination

Feinpoliert und durchdacht - Intelligente Seitensegmentierung für deutsche Dokumente.
"""

import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.agents.base import PreprocessingAgent
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class RegionType(str, Enum):
    """Types of document regions."""

    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    HEADER = "header"
    FOOTER = "footer"
    SIDEBAR = "sidebar"
    FIGURE = "figure"
    CAPTION = "caption"


class LayoutType(str, Enum):
    """Document layout types."""

    SINGLE_COLUMN = "single_column"
    MULTI_COLUMN = "multi_column"
    MIXED = "mixed"


@dataclass
class Region:
    """Detected region in a document page."""

    region_id: str
    region_type: RegionType
    page_num: int
    bbox: Tuple[int, int, int, int]  # (x, y, width, height)
    confidence: float = 0.0
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def area(self) -> int:
        """Calculate region area."""
        return self.bbox[2] * self.bbox[3]

    @property
    def center(self) -> Tuple[int, int]:
        """Calculate region center point."""
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "region_id": self.region_id,
            "type": self.region_type.value,
            "page": self.page_num,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "area": self.area,
            "center": self.center,
            "metadata": self.metadata,
        }


@dataclass
class PageInfo:
    """Information about a document page."""

    page_num: int
    width: int
    height: int
    dpi: int = 300
    regions: List[Region] = field(default_factory=list)
    layout_type: LayoutType = LayoutType.SINGLE_COLUMN
    image_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "page_num": self.page_num,
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "layout_type": self.layout_type.value,
            "region_count": len(self.regions),
            "image_path": self.image_path,
        }


class PageSegmentationAgent(PreprocessingAgent):
    """
    Page segmentation agent for multi-page document processing.

    Handles:
    - PDF page extraction and rendering
    - Region detection using OpenCV
    - Layout classification (single/multi-column)
    - Reading order determination
    - Table and image detection
    """

    # Segmentation thresholds
    MIN_TEXT_BLOCK_HEIGHT: int = 20  # pixels
    MIN_TEXT_BLOCK_WIDTH: int = 50  # pixels
    MIN_TABLE_CELLS: int = 4  # minimum cells to consider as table
    COLUMN_GAP_THRESHOLD: int = 50  # pixels
    HEADER_ZONE_PERCENT: float = 0.12  # top 12% of page
    FOOTER_ZONE_PERCENT: float = 0.10  # bottom 10% of page
    MIN_REGION_AREA: int = 500  # minimum region area in pixels

    # Rendering settings
    DEFAULT_DPI: int = 300
    MAX_DPI: int = 600

    def __init__(self):
        """Initialize the Page Segmentation Agent."""
        super().__init__(name="page_segmentation_agent")
        self._cv2 = None
        self._pypdfium2 = None
        self._ensure_dependencies()

    def _ensure_dependencies(self) -> None:
        """Ensure required dependencies are available."""
        try:
            import cv2
            self._cv2 = cv2
        except ImportError:
            logger.warning("OpenCV nicht verfügbar - Segmentierung eingeschränkt")
            self._cv2 = None

        try:
            import pypdfium2
            self._pypdfium2 = pypdfium2
        except ImportError:
            logger.warning("pypdfium2 nicht verfügbar - PDF-Verarbeitung eingeschränkt")
            self._pypdfium2 = None

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Segment document into processable regions.

        Args:
            input_data: Dictionary containing:
                - file_path: Path to document file (PDF or image)
                - classification: Optional classification result
                - options: Optional segmentation options

        Returns:
            Segmentation result containing:
                - pages: List of page information
                - regions: All detected regions
                - reading_order: Ordered list of region IDs
                - layout_summary: Overall layout analysis
                - metadata: Segmentation metadata
        """
        self.validate_input(input_data, ["file_path"])

        file_path = Path(input_data["file_path"])
        classification = input_data.get("classification", {})
        options = input_data.get("options", {})

        self.logger.info(
            "page_segmentation_started",
            file_path=str(file_path),
            file_type=file_path.suffix.lower(),
        )

        # Extract pages from document
        pages = await self._extract_pages(file_path, options)

        if not pages:
            self.logger.warning(
                "no_pages_extracted",
                file_path=str(file_path),
            )
            return {
                "pages": [],
                "regions": [],
                "reading_order": [],
                "layout_summary": {"error": "Keine Seiten extrahiert"},
                "metadata": {"page_count": 0},
            }

        # Detect regions on each page
        all_regions: List[Region] = []
        for page in pages:
            if page.image_path and self._cv2 is not None:
                page_regions = self._detect_regions(page)
                page.regions = page_regions
                all_regions.extend(page_regions)

                # Classify page layout
                page.layout_type = self._classify_layout(page_regions, page.width)

        # Determine reading order
        reading_order = self._determine_reading_order(all_regions, pages)

        # Create layout summary
        layout_summary = self._create_layout_summary(pages, all_regions)

        result = {
            "pages": [page.to_dict() for page in pages],
            "regions": [region.to_dict() for region in all_regions],
            "reading_order": reading_order,
            "layout_summary": layout_summary,
            "metadata": {
                "page_count": len(pages),
                "total_regions": len(all_regions),
                "file_path": str(file_path),
                "dpi": options.get("dpi", self.DEFAULT_DPI),
            },
        }

        self.logger.info(
            "page_segmentation_completed",
            page_count=len(pages),
            region_count=len(all_regions),
            layout_types=[p.layout_type.value for p in pages],
        )

        return result

    async def _extract_pages(
        self,
        file_path: Path,
        options: Dict[str, Any],
    ) -> List[PageInfo]:
        """
        Extract pages from document file.

        Args:
            file_path: Path to document
            options: Extraction options (dpi, max_pages)

        Returns:
            List of PageInfo objects
        """
        suffix = file_path.suffix.lower()
        dpi = min(options.get("dpi", self.DEFAULT_DPI), self.MAX_DPI)
        max_pages = options.get("max_pages", 100)

        pages: List[PageInfo] = []

        if suffix == ".pdf":
            pages = await self._extract_pdf_pages(file_path, dpi, max_pages)
        elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
            pages = await self._extract_image_page(file_path)
        else:
            self.logger.warning(
                "unsupported_file_type",
                suffix=suffix,
            )

        return pages

    async def _extract_pdf_pages(
        self,
        file_path: Path,
        dpi: int,
        max_pages: int,
    ) -> List[PageInfo]:
        """Extract pages from PDF using pypdfium2."""
        if self._pypdfium2 is None:
            self.logger.error("pypdfium2_not_available")
            return []

        pages: List[PageInfo] = []

        try:
            pdf = self._pypdfium2.PdfDocument(str(file_path))
            page_count = min(len(pdf), max_pages)

            for page_num in range(page_count):
                pdf_page = pdf[page_num]

                # Get page dimensions
                width_pt, height_pt = pdf_page.get_size()

                # Calculate pixel dimensions at target DPI
                scale = dpi / 72.0  # PDF points to pixels
                width_px = int(width_pt * scale)
                height_px = int(height_pt * scale)

                # Render page to image
                bitmap = pdf_page.render(scale=scale)
                img_array = bitmap.to_numpy()

                # Save to temporary file
                with tempfile.NamedTemporaryFile(
                    suffix=".png",
                    delete=False,
                    prefix=f"page_{page_num}_",
                ) as tmp:
                    # Convert RGB to BGR for OpenCV if needed
                    if self._cv2 is not None and len(img_array.shape) == 3:
                        if img_array.shape[2] == 4:  # RGBA
                            img_bgr = self._cv2.cvtColor(img_array, self._cv2.COLOR_RGBA2BGR)
                        else:  # RGB
                            img_bgr = self._cv2.cvtColor(img_array, self._cv2.COLOR_RGB2BGR)
                        self._cv2.imwrite(tmp.name, img_bgr)
                    else:
                        # Fallback: save with numpy
                        import PIL.Image
                        PIL.Image.fromarray(img_array).save(tmp.name)

                    image_path = tmp.name

                pages.append(
                    PageInfo(
                        page_num=page_num,
                        width=width_px,
                        height=height_px,
                        dpi=dpi,
                        image_path=image_path,
                    )
                )

            pdf.close()

        except Exception as e:
            self.logger.error(
                "pdf_extraction_failed",
                file_path=str(file_path),
                **safe_error_log(e),
            )

        return pages

    async def _extract_image_page(self, file_path: Path) -> List[PageInfo]:
        """Extract single image as a page."""
        if self._cv2 is None:
            return []

        try:
            img = self._cv2.imread(str(file_path))
            if img is None:
                return []

            height, width = img.shape[:2]

            return [
                PageInfo(
                    page_num=0,
                    width=width,
                    height=height,
                    dpi=self.DEFAULT_DPI,
                    image_path=str(file_path),
                )
            ]

        except Exception as e:
            self.logger.error(
                "image_extraction_failed",
                file_path=str(file_path),
                **safe_error_log(e),
            )
            return []

    def _detect_regions(self, page: PageInfo) -> List[Region]:
        """
        Detect regions of interest on a page.

        Args:
            page: PageInfo with image_path set

        Returns:
            List of detected regions
        """
        if not page.image_path or self._cv2 is None:
            return []

        regions: List[Region] = []

        try:
            # Load image
            img = self._cv2.imread(page.image_path)
            if img is None:
                return []

            # Convert to grayscale
            gray = self._cv2.cvtColor(img, self._cv2.COLOR_BGR2GRAY)

            # Detect text blocks
            text_regions = self._detect_text_blocks(gray, page.page_num)
            regions.extend(text_regions)

            # Detect tables
            table_regions = self._detect_tables(gray, page.page_num)
            regions.extend(table_regions)

            # Detect images/figures
            image_regions = self._detect_images(img, gray, page.page_num)
            regions.extend(image_regions)

            # Classify header/footer regions
            self._classify_header_footer(regions, page.height)

            # Filter overlapping regions
            regions = self._filter_overlapping_regions(regions)

        except Exception as e:
            self.logger.error(
                "region_detection_failed",
                page_num=page.page_num,
                **safe_error_log(e),
            )

        return regions

    def _detect_text_blocks(
        self,
        gray: np.ndarray,
        page_num: int,
    ) -> List[Region]:
        """
        Detect text block regions using morphological operations.

        Args:
            gray: Grayscale image
            page_num: Page number

        Returns:
            List of text block regions
        """
        regions: List[Region] = []

        try:
            # Apply adaptive thresholding
            binary = self._cv2.adaptiveThreshold(
                gray,
                255,
                self._cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                self._cv2.THRESH_BINARY_INV,
                blockSize=11,
                C=2,
            )

            # Morphological operations to connect text lines
            kernel_h = self._cv2.getStructuringElement(
                self._cv2.MORPH_RECT, (30, 1)
            )
            kernel_v = self._cv2.getStructuringElement(
                self._cv2.MORPH_RECT, (1, 10)
            )

            # Horizontal dilation to connect words
            dilated_h = self._cv2.dilate(binary, kernel_h, iterations=2)

            # Vertical dilation to connect lines
            dilated = self._cv2.dilate(dilated_h, kernel_v, iterations=2)

            # Find contours
            contours, _ = self._cv2.findContours(
                dilated,
                self._cv2.RETR_EXTERNAL,
                self._cv2.CHAIN_APPROX_SIMPLE,
            )

            for i, contour in enumerate(contours):
                x, y, w, h = self._cv2.boundingRect(contour)

                # Filter by minimum size
                if (
                    w >= self.MIN_TEXT_BLOCK_WIDTH
                    and h >= self.MIN_TEXT_BLOCK_HEIGHT
                    and w * h >= self.MIN_REGION_AREA
                ):
                    regions.append(
                        Region(
                            region_id=f"text_{page_num}_{i}",
                            region_type=RegionType.TEXT,
                            page_num=page_num,
                            bbox=(x, y, w, h),
                            confidence=0.8,
                        )
                    )

        except Exception as e:
            self.logger.warning(
                "text_block_detection_failed",
                **safe_error_log(e),
            )

        return regions

    def _detect_tables(
        self,
        gray: np.ndarray,
        page_num: int,
    ) -> List[Region]:
        """
        Detect table regions using line detection.

        Args:
            gray: Grayscale image
            page_num: Page number

        Returns:
            List of table regions
        """
        regions: List[Region] = []

        try:
            # Apply threshold
            _, binary = self._cv2.threshold(
                gray, 0, 255, self._cv2.THRESH_BINARY_INV + self._cv2.THRESH_OTSU
            )

            # Detect horizontal lines
            kernel_h = self._cv2.getStructuringElement(
                self._cv2.MORPH_RECT, (40, 1)
            )
            horizontal = self._cv2.morphologyEx(
                binary, self._cv2.MORPH_OPEN, kernel_h, iterations=2
            )

            # Detect vertical lines
            kernel_v = self._cv2.getStructuringElement(
                self._cv2.MORPH_RECT, (1, 40)
            )
            vertical = self._cv2.morphologyEx(
                binary, self._cv2.MORPH_OPEN, kernel_v, iterations=2
            )

            # Combine lines
            table_mask = self._cv2.add(horizontal, vertical)

            # Find contours of table structures
            contours, _ = self._cv2.findContours(
                table_mask,
                self._cv2.RETR_EXTERNAL,
                self._cv2.CHAIN_APPROX_SIMPLE,
            )

            for i, contour in enumerate(contours):
                x, y, w, h = self._cv2.boundingRect(contour)

                # Tables should be reasonably sized
                if w * h >= self.MIN_REGION_AREA * 4:
                    # Check for grid-like structure (multiple intersections)
                    roi = table_mask[y : y + h, x : x + w]
                    intersection_count = self._count_line_intersections(roi)

                    if intersection_count >= self.MIN_TABLE_CELLS:
                        regions.append(
                            Region(
                                region_id=f"table_{page_num}_{i}",
                                region_type=RegionType.TABLE,
                                page_num=page_num,
                                bbox=(x, y, w, h),
                                confidence=0.85,
                                metadata={"intersections": intersection_count},
                            )
                        )

        except Exception as e:
            self.logger.warning(
                "table_detection_failed",
                **safe_error_log(e),
            )

        return regions

    def _count_line_intersections(self, table_roi: np.ndarray) -> int:
        """Count line intersections in table region."""
        try:
            # Find corners/intersections using Harris corner detection
            corners = self._cv2.cornerHarris(
                table_roi.astype(np.float32), 2, 3, 0.04
            )
            corners = self._cv2.dilate(corners, None)

            # Threshold for corners
            threshold = 0.01 * corners.max()
            corner_count = np.sum(corners > threshold)

            return corner_count

        except Exception:
            return 0

    def _detect_images(
        self,
        img: np.ndarray,
        gray: np.ndarray,
        page_num: int,
    ) -> List[Region]:
        """
        Detect embedded image/figure regions.

        Args:
            img: Color image
            gray: Grayscale image
            page_num: Page number

        Returns:
            List of image regions
        """
        regions: List[Region] = []

        try:
            # Use edge detection to find image boundaries
            edges = self._cv2.Canny(gray, 50, 150)

            # Dilate to connect edges
            kernel = self._cv2.getStructuringElement(
                self._cv2.MORPH_RECT, (5, 5)
            )
            dilated = self._cv2.dilate(edges, kernel, iterations=3)

            # Find contours
            contours, _ = self._cv2.findContours(
                dilated,
                self._cv2.RETR_EXTERNAL,
                self._cv2.CHAIN_APPROX_SIMPLE,
            )

            for i, contour in enumerate(contours):
                x, y, w, h = self._cv2.boundingRect(contour)

                # Images should be relatively large and square-ish
                if w * h >= self.MIN_REGION_AREA * 10:
                    aspect_ratio = w / h if h > 0 else 0

                    # Check if region has image-like characteristics
                    # (non-text: high color variance, less uniform)
                    roi = img[y : y + h, x : x + w]
                    if self._is_image_region(roi):
                        regions.append(
                            Region(
                                region_id=f"image_{page_num}_{i}",
                                region_type=RegionType.IMAGE,
                                page_num=page_num,
                                bbox=(x, y, w, h),
                                confidence=0.7,
                                metadata={"aspect_ratio": round(aspect_ratio, 2)},
                            )
                        )

        except Exception as e:
            self.logger.warning(
                "image_detection_failed",
                **safe_error_log(e),
            )

        return regions

    def _is_image_region(self, roi: np.ndarray) -> bool:
        """Check if region is likely an image (not text)."""
        try:
            if roi.size == 0:
                return False

            # Check color variance
            if len(roi.shape) == 3:
                gray = self._cv2.cvtColor(roi, self._cv2.COLOR_BGR2GRAY)
            else:
                gray = roi

            # Images typically have more variance than text
            variance = np.var(gray)

            # Text regions tend to be mostly black/white (bimodal)
            # Images have more continuous tones
            hist = self._cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist = hist.flatten() / hist.sum()

            # Check if distribution is not bimodal (not text-like)
            mid_range = hist[64:192].sum()

            return variance > 1000 and mid_range > 0.3

        except Exception:
            return False

    def _classify_header_footer(
        self,
        regions: List[Region],
        page_height: int,
    ) -> None:
        """
        Reclassify text regions as header/footer based on position.

        Args:
            regions: List of regions to classify
            page_height: Page height in pixels
        """
        header_threshold = int(page_height * self.HEADER_ZONE_PERCENT)
        footer_threshold = int(page_height * (1 - self.FOOTER_ZONE_PERCENT))

        for region in regions:
            if region.region_type != RegionType.TEXT:
                continue

            _, y, _, h = region.bbox
            center_y = y + h // 2

            if center_y < header_threshold:
                region.region_type = RegionType.HEADER
            elif center_y > footer_threshold:
                region.region_type = RegionType.FOOTER

    def _filter_overlapping_regions(
        self,
        regions: List[Region],
        overlap_threshold: float = 0.5,
    ) -> List[Region]:
        """
        Filter out overlapping regions, keeping larger/higher confidence.

        Args:
            regions: List of regions
            overlap_threshold: IoU threshold for filtering

        Returns:
            Filtered list of regions
        """
        if not regions:
            return []

        # Sort by area (descending) and confidence
        sorted_regions = sorted(
            regions,
            key=lambda r: (r.area, r.confidence),
            reverse=True,
        )

        filtered: List[Region] = []

        for region in sorted_regions:
            # Check overlap with already selected regions
            overlaps = False
            for selected in filtered:
                if selected.page_num != region.page_num:
                    continue

                iou = self._calculate_iou(region.bbox, selected.bbox)
                if iou > overlap_threshold:
                    overlaps = True
                    break

            if not overlaps:
                filtered.append(region)

        return filtered

    def _calculate_iou(
        self,
        bbox1: Tuple[int, int, int, int],
        bbox2: Tuple[int, int, int, int],
    ) -> float:
        """Calculate Intersection over Union of two bounding boxes."""
        x1, y1, w1, h1 = bbox1
        x2, y2, w2, h2 = bbox2

        # Calculate intersection
        xi = max(x1, x2)
        yi = max(y1, y2)
        wi = min(x1 + w1, x2 + w2) - xi
        hi = min(y1 + h1, y2 + h2) - yi

        if wi <= 0 or hi <= 0:
            return 0.0

        intersection = wi * hi
        union = w1 * h1 + w2 * h2 - intersection

        return intersection / union if union > 0 else 0.0

    def _classify_layout(
        self,
        regions: List[Region],
        page_width: int,
    ) -> LayoutType:
        """
        Classify page layout as single/multi column.

        Args:
            regions: List of regions on page
            page_width: Page width in pixels

        Returns:
            Layout type classification
        """
        if not regions:
            return LayoutType.SINGLE_COLUMN

        # Get text regions only
        text_regions = [
            r for r in regions
            if r.region_type in (RegionType.TEXT, RegionType.HEADER, RegionType.FOOTER)
        ]

        if len(text_regions) < 2:
            return LayoutType.SINGLE_COLUMN

        # Analyze x-coordinates of regions
        x_positions = [(r.bbox[0], r.bbox[0] + r.bbox[2]) for r in text_regions]

        # Find gaps in x-coordinates
        page_center = page_width // 2
        margin = self.COLUMN_GAP_THRESHOLD

        left_regions = sum(
            1 for x1, x2 in x_positions
            if x2 < page_center - margin
        )
        right_regions = sum(
            1 for x1, x2 in x_positions
            if x1 > page_center + margin
        )
        spanning_regions = sum(
            1 for x1, x2 in x_positions
            if x1 < page_center and x2 > page_center
        )

        # Determine layout type
        if left_regions > 1 and right_regions > 1:
            if spanning_regions > 0:
                return LayoutType.MIXED
            return LayoutType.MULTI_COLUMN

        return LayoutType.SINGLE_COLUMN

    def _determine_reading_order(
        self,
        regions: List[Region],
        pages: List[PageInfo],
    ) -> List[str]:
        """
        Determine reading order of regions.

        Algorithm:
        1. Group regions by page
        2. Within each page, sort by layout type
        3. For single column: top-to-bottom
        4. For multi-column: detect columns, then left-to-right within row

        Args:
            regions: All regions
            pages: Page information

        Returns:
            Ordered list of region IDs
        """
        reading_order: List[str] = []

        # Group by page
        regions_by_page: Dict[int, List[Region]] = {}
        for region in regions:
            if region.page_num not in regions_by_page:
                regions_by_page[region.page_num] = []
            regions_by_page[region.page_num].append(region)

        # Process each page
        for page in sorted(pages, key=lambda p: p.page_num):
            page_regions = regions_by_page.get(page.page_num, [])
            if not page_regions:
                continue

            if page.layout_type == LayoutType.SINGLE_COLUMN:
                # Simple top-to-bottom ordering
                sorted_regions = sorted(
                    page_regions,
                    key=lambda r: r.bbox[1],  # y-coordinate
                )
            else:
                # Multi-column: group by column, then sort
                sorted_regions = self._sort_multi_column(
                    page_regions, page.width
                )

            reading_order.extend([r.region_id for r in sorted_regions])

        return reading_order

    def _sort_multi_column(
        self,
        regions: List[Region],
        page_width: int,
    ) -> List[Region]:
        """
        Sort regions for multi-column layout.

        Groups regions into columns based on x-position,
        then sorts within each row.
        """
        # Determine column boundaries
        column_threshold = page_width // 2

        # Group into rows based on y-coordinate overlap
        rows: List[List[Region]] = []

        for region in sorted(regions, key=lambda r: r.bbox[1]):
            # Find row with overlapping y-coordinates
            placed = False
            for row in rows:
                if self._y_overlaps(region, row[0]):
                    row.append(region)
                    placed = True
                    break

            if not placed:
                rows.append([region])

        # Sort each row left-to-right, then flatten
        sorted_regions: List[Region] = []
        for row in rows:
            row_sorted = sorted(row, key=lambda r: r.bbox[0])
            sorted_regions.extend(row_sorted)

        return sorted_regions

    def _y_overlaps(self, r1: Region, r2: Region) -> bool:
        """Check if two regions overlap in y-coordinate."""
        y1, h1 = r1.bbox[1], r1.bbox[3]
        y2, h2 = r2.bbox[1], r2.bbox[3]

        return not (y1 + h1 < y2 or y2 + h2 < y1)

    def _create_layout_summary(
        self,
        pages: List[PageInfo],
        regions: List[Region],
    ) -> Dict[str, Any]:
        """
        Create summary of document layout analysis.

        Args:
            pages: All pages
            regions: All regions

        Returns:
            Layout summary dictionary
        """
        # Count regions by type
        region_counts: Dict[str, int] = {}
        for region in regions:
            rtype = region.region_type.value
            region_counts[rtype] = region_counts.get(rtype, 0) + 1

        # Count layout types
        layout_counts: Dict[str, int] = {}
        for page in pages:
            ltype = page.layout_type.value
            layout_counts[ltype] = layout_counts.get(ltype, 0) + 1

        # Determine dominant layout
        dominant_layout = max(
            layout_counts.items(),
            key=lambda x: x[1],
            default=(LayoutType.SINGLE_COLUMN.value, 0),
        )[0]

        return {
            "page_count": len(pages),
            "total_regions": len(regions),
            "region_counts": region_counts,
            "layout_counts": layout_counts,
            "dominant_layout": dominant_layout,
            "has_tables": region_counts.get("table", 0) > 0,
            "has_images": region_counts.get("image", 0) > 0,
            "has_multi_column": layout_counts.get("multi_column", 0) > 0,
        }
