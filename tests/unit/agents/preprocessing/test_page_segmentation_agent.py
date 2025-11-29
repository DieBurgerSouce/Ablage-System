# -*- coding: utf-8 -*-
"""
Unit Tests for PageSegmentationAgent.

Tests page segmentation capabilities:
- PDF page extraction
- Region detection (text, tables, images)
- Layout classification
- Reading order determination
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import numpy as np

from app.agents.preprocessing.page_segmentation_agent import (
    LayoutType,
    PageInfo,
    PageSegmentationAgent,
    Region,
    RegionType,
)


class TestRegionClass:
    """Test Region dataclass functionality."""

    def test_region_creation(self) -> None:
        """Region sollte korrekt erstellt werden."""
        region = Region(
            region_id="text_0_1",
            region_type=RegionType.TEXT,
            page_num=0,
            bbox=(100, 200, 300, 400),
            confidence=0.9,
        )

        assert region.region_id == "text_0_1"
        assert region.region_type == RegionType.TEXT
        assert region.page_num == 0
        assert region.bbox == (100, 200, 300, 400)
        assert region.confidence == 0.9

    def test_region_area(self) -> None:
        """Region-Fläche sollte korrekt berechnet werden."""
        region = Region(
            region_id="test",
            region_type=RegionType.TEXT,
            page_num=0,
            bbox=(0, 0, 100, 200),  # width=100, height=200
        )

        assert region.area == 20000  # 100 * 200

    def test_region_center(self) -> None:
        """Region-Mittelpunkt sollte korrekt berechnet werden."""
        region = Region(
            region_id="test",
            region_type=RegionType.TEXT,
            page_num=0,
            bbox=(100, 100, 200, 100),  # x=100, y=100, w=200, h=100
        )

        assert region.center == (200, 150)  # (100+200/2, 100+100/2)

    def test_region_to_dict(self) -> None:
        """Region sollte zu Dictionary konvertierbar sein."""
        region = Region(
            region_id="table_1_0",
            region_type=RegionType.TABLE,
            page_num=1,
            bbox=(50, 100, 400, 300),
            confidence=0.85,
            metadata={"cells": 12},
        )

        result = region.to_dict()

        assert result["region_id"] == "table_1_0"
        assert result["type"] == "table"
        assert result["page"] == 1
        assert result["bbox"] == (50, 100, 400, 300)
        assert result["confidence"] == 0.85
        assert result["area"] == 120000
        assert result["center"] == (250, 250)
        assert result["metadata"]["cells"] == 12


class TestPageInfoClass:
    """Test PageInfo dataclass functionality."""

    def test_page_info_creation(self) -> None:
        """PageInfo sollte korrekt erstellt werden."""
        page = PageInfo(
            page_num=0,
            width=2480,
            height=3508,
            dpi=300,
        )

        assert page.page_num == 0
        assert page.width == 2480
        assert page.height == 3508
        assert page.dpi == 300
        assert page.regions == []
        assert page.layout_type == LayoutType.SINGLE_COLUMN
        assert page.image_path is None

    def test_page_info_to_dict(self) -> None:
        """PageInfo sollte zu Dictionary konvertierbar sein."""
        page = PageInfo(
            page_num=0,
            width=2480,
            height=3508,
            dpi=300,
            layout_type=LayoutType.MULTI_COLUMN,
            image_path="/tmp/page_0.png",
        )

        result = page.to_dict()

        assert result["page_num"] == 0
        assert result["width"] == 2480
        assert result["height"] == 3508
        assert result["dpi"] == 300
        assert result["layout_type"] == "multi_column"
        assert result["region_count"] == 0
        assert result["image_path"] == "/tmp/page_0.png"


class TestPageSegmentationAgentInit:
    """Test agent initialization."""

    def test_agent_initialization(self) -> None:
        """Agent sollte korrekt initialisiert werden."""
        agent = PageSegmentationAgent()

        assert agent.name == "page_segmentation_agent"
        assert agent.category.value == "preprocessing"

    def test_segmentation_thresholds(self) -> None:
        """Agent sollte korrekte Segmentierungsschwellwerte haben."""
        agent = PageSegmentationAgent()

        assert agent.MIN_TEXT_BLOCK_HEIGHT == 20
        assert agent.MIN_TEXT_BLOCK_WIDTH == 50
        assert agent.MIN_TABLE_CELLS == 4
        assert agent.COLUMN_GAP_THRESHOLD == 50
        assert agent.HEADER_ZONE_PERCENT == 0.12
        assert agent.FOOTER_ZONE_PERCENT == 0.10
        assert agent.MIN_REGION_AREA == 500
        assert agent.DEFAULT_DPI == 300
        assert agent.MAX_DPI == 600


class TestLayoutClassification:
    """Test layout classification functionality."""

    def test_classify_layout_single_column(self) -> None:
        """Einzelspalten-Layout sollte erkannt werden."""
        agent = PageSegmentationAgent()

        # Single column regions (all span full width)
        regions = [
            Region("t1", RegionType.TEXT, 0, (50, 100, 700, 50)),  # Full width
            Region("t2", RegionType.TEXT, 0, (50, 200, 700, 100)),  # Full width
        ]

        layout = agent._classify_layout(regions, 800)

        assert layout == LayoutType.SINGLE_COLUMN

    def test_classify_layout_multi_column(self) -> None:
        """Mehrspalten-Layout sollte erkannt werden."""
        agent = PageSegmentationAgent()

        # Multi-column regions
        regions = [
            Region("t1", RegionType.TEXT, 0, (50, 100, 150, 300)),   # Left column
            Region("t2", RegionType.TEXT, 0, (50, 450, 150, 200)),   # Left column
            Region("t3", RegionType.TEXT, 0, (450, 100, 150, 250)),  # Right column
            Region("t4", RegionType.TEXT, 0, (450, 400, 150, 150)),  # Right column
        ]

        layout = agent._classify_layout(regions, 650)

        assert layout == LayoutType.MULTI_COLUMN

    def test_classify_layout_empty_regions(self) -> None:
        """Leere Regionen sollten Single-Column zurückgeben."""
        agent = PageSegmentationAgent()

        layout = agent._classify_layout([], 800)

        assert layout == LayoutType.SINGLE_COLUMN

    def test_classify_layout_mixed(self) -> None:
        """Gemischtes Layout sollte erkannt werden."""
        agent = PageSegmentationAgent()

        # Header spans full width, body is multi-column
        regions = [
            Region("h1", RegionType.HEADER, 0, (50, 50, 700, 50)),   # Full width header
            Region("t1", RegionType.TEXT, 0, (50, 150, 150, 300)),   # Left column
            Region("t2", RegionType.TEXT, 0, (450, 150, 150, 300)),  # Right column
        ]

        layout = agent._classify_layout(regions, 800)

        # With spanning header and side columns, could be MIXED
        assert layout in [LayoutType.MIXED, LayoutType.SINGLE_COLUMN, LayoutType.MULTI_COLUMN]


class TestIoUCalculation:
    """Test Intersection over Union calculation."""

    def test_iou_no_overlap(self) -> None:
        """Keine Überlappung sollte 0 zurückgeben."""
        agent = PageSegmentationAgent()

        bbox1 = (0, 0, 100, 100)
        bbox2 = (200, 200, 100, 100)

        iou = agent._calculate_iou(bbox1, bbox2)

        assert iou == 0.0

    def test_iou_full_overlap(self) -> None:
        """Vollständige Überlappung sollte 1 zurückgeben."""
        agent = PageSegmentationAgent()

        bbox = (100, 100, 200, 200)

        iou = agent._calculate_iou(bbox, bbox)

        assert iou == 1.0

    def test_iou_partial_overlap(self) -> None:
        """Teilüberlappung sollte korrekten IoU berechnen."""
        agent = PageSegmentationAgent()

        bbox1 = (0, 0, 100, 100)
        bbox2 = (50, 50, 100, 100)

        iou = agent._calculate_iou(bbox1, bbox2)

        # Intersection: 50x50 = 2500
        # Union: 100x100 + 100x100 - 2500 = 17500
        # IoU: 2500/17500 ≈ 0.143
        assert 0.1 < iou < 0.2


class TestHeaderFooterClassification:
    """Test header/footer region classification."""

    def test_classify_header_region(self) -> None:
        """Header-Regionen sollten korrekt klassifiziert werden."""
        agent = PageSegmentationAgent()
        page_height = 1000

        regions = [
            Region("t1", RegionType.TEXT, 0, (50, 50, 400, 30)),  # Near top -> header
            Region("t2", RegionType.TEXT, 0, (50, 500, 400, 30)),  # Middle -> stays text
        ]

        agent._classify_header_footer(regions, page_height)

        # Top 12% of 1000 = 120, so y=50+15=65 center is in header zone
        assert regions[0].region_type == RegionType.HEADER
        assert regions[1].region_type == RegionType.TEXT

    def test_classify_footer_region(self) -> None:
        """Footer-Regionen sollten korrekt klassifiziert werden."""
        agent = PageSegmentationAgent()
        page_height = 1000

        regions = [
            Region("t1", RegionType.TEXT, 0, (50, 950, 400, 30)),  # Near bottom -> footer
            Region("t2", RegionType.TEXT, 0, (50, 500, 400, 30)),  # Middle -> stays text
        ]

        agent._classify_header_footer(regions, page_height)

        # Bottom 10% starts at 900, center of second region is 950+15=965 -> footer
        assert regions[0].region_type == RegionType.FOOTER
        assert regions[1].region_type == RegionType.TEXT


class TestReadingOrderDetermination:
    """Test reading order algorithm."""

    def test_reading_order_single_column(self) -> None:
        """Lesereihenfolge für Einzelspalte sollte top-to-bottom sein."""
        agent = PageSegmentationAgent()

        regions = [
            Region("t3", RegionType.TEXT, 0, (50, 300, 400, 50)),
            Region("t1", RegionType.TEXT, 0, (50, 100, 400, 50)),
            Region("t2", RegionType.TEXT, 0, (50, 200, 400, 50)),
        ]

        pages = [PageInfo(0, 500, 500, layout_type=LayoutType.SINGLE_COLUMN)]

        order = agent._determine_reading_order(regions, pages)

        # Should be sorted by y-coordinate
        assert order == ["t1", "t2", "t3"]

    def test_reading_order_multi_page(self) -> None:
        """Lesereihenfolge über mehrere Seiten sollte korrekt sein."""
        agent = PageSegmentationAgent()

        regions = [
            Region("p1_t1", RegionType.TEXT, 0, (50, 100, 400, 50)),
            Region("p2_t1", RegionType.TEXT, 1, (50, 100, 400, 50)),
            Region("p1_t2", RegionType.TEXT, 0, (50, 200, 400, 50)),
        ]

        pages = [
            PageInfo(0, 500, 500, layout_type=LayoutType.SINGLE_COLUMN),
            PageInfo(1, 500, 500, layout_type=LayoutType.SINGLE_COLUMN),
        ]

        order = agent._determine_reading_order(regions, pages)

        # Page 0 regions first, then page 1
        assert order.index("p1_t1") < order.index("p2_t1")
        assert order.index("p1_t2") < order.index("p2_t1")


class TestRegionFiltering:
    """Test overlapping region filtering."""

    def test_filter_no_overlapping(self) -> None:
        """Nicht-überlappende Regionen sollten erhalten bleiben."""
        agent = PageSegmentationAgent()

        regions = [
            Region("t1", RegionType.TEXT, 0, (0, 0, 100, 100)),
            Region("t2", RegionType.TEXT, 0, (200, 0, 100, 100)),
        ]

        filtered = agent._filter_overlapping_regions(regions)

        assert len(filtered) == 2

    def test_filter_overlapping_keeps_larger(self) -> None:
        """Bei Überlappung sollte die größere Region behalten werden."""
        agent = PageSegmentationAgent()

        regions = [
            Region("t1", RegionType.TEXT, 0, (0, 0, 100, 100), confidence=0.8),
            Region("t2", RegionType.TEXT, 0, (10, 10, 150, 150), confidence=0.9),  # Larger, overlaps
        ]

        filtered = agent._filter_overlapping_regions(regions, overlap_threshold=0.3)

        # Larger region should be kept
        assert len(filtered) == 1
        assert filtered[0].region_id == "t2"

    def test_filter_empty_list(self) -> None:
        """Leere Liste sollte leere Liste zurückgeben."""
        agent = PageSegmentationAgent()

        filtered = agent._filter_overlapping_regions([])

        assert filtered == []


class TestLayoutSummary:
    """Test layout summary creation."""

    def test_create_layout_summary(self) -> None:
        """Layout-Zusammenfassung sollte korrekt erstellt werden."""
        agent = PageSegmentationAgent()

        pages = [
            PageInfo(0, 800, 1200, layout_type=LayoutType.SINGLE_COLUMN),
            PageInfo(1, 800, 1200, layout_type=LayoutType.MULTI_COLUMN),
        ]

        regions = [
            Region("t1", RegionType.TEXT, 0, (50, 100, 400, 50)),
            Region("t2", RegionType.TEXT, 0, (50, 200, 400, 50)),
            Region("table1", RegionType.TABLE, 1, (50, 100, 600, 300)),
            Region("img1", RegionType.IMAGE, 1, (50, 500, 200, 200)),
        ]

        summary = agent._create_layout_summary(pages, regions)

        assert summary["page_count"] == 2
        assert summary["total_regions"] == 4
        assert summary["region_counts"]["text"] == 2
        assert summary["region_counts"]["table"] == 1
        assert summary["region_counts"]["image"] == 1
        assert summary["has_tables"] is True
        assert summary["has_images"] is True
        assert summary["has_multi_column"] is True


class TestYOverlap:
    """Test Y-coordinate overlap detection."""

    def test_y_overlaps_true(self) -> None:
        """Überlappende Y-Koordinaten sollten True zurückgeben."""
        agent = PageSegmentationAgent()

        r1 = Region("t1", RegionType.TEXT, 0, (0, 100, 100, 50))  # y: 100-150
        r2 = Region("t2", RegionType.TEXT, 0, (200, 120, 100, 50))  # y: 120-170

        assert agent._y_overlaps(r1, r2) is True

    def test_y_overlaps_false(self) -> None:
        """Nicht-überlappende Y-Koordinaten sollten False zurückgeben."""
        agent = PageSegmentationAgent()

        r1 = Region("t1", RegionType.TEXT, 0, (0, 100, 100, 50))  # y: 100-150
        r2 = Region("t2", RegionType.TEXT, 0, (200, 200, 100, 50))  # y: 200-250

        assert agent._y_overlaps(r1, r2) is False


class TestFullProcessingPipeline:
    """Test complete segmentation pipeline."""

    @pytest.mark.asyncio
    async def test_process_requires_file_path(self) -> None:
        """Verarbeitung sollte file_path erfordern."""
        agent = PageSegmentationAgent()

        with pytest.raises(ValueError) as exc_info:
            await agent.process({})

        assert "file_path" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_no_pages_extracted(self) -> None:
        """Keine extrahierten Seiten sollten leeres Ergebnis zurückgeben."""
        agent = PageSegmentationAgent()

        with patch.object(agent, "_extract_pages", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = []

            result = await agent.process({"file_path": "/path/to/doc.pdf"})

            assert result["pages"] == []
            assert result["regions"] == []
            assert result["reading_order"] == []
            assert "error" in result["layout_summary"]

    @pytest.mark.asyncio
    async def test_process_returns_complete_result(self) -> None:
        """Verarbeitung sollte vollständiges Ergebnis zurückgeben."""
        agent = PageSegmentationAgent()
        agent._cv2 = None  # Disable region detection

        with patch.object(agent, "_extract_pages", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = [
                PageInfo(0, 800, 1200, dpi=300),
                PageInfo(1, 800, 1200, dpi=300),
            ]

            result = await agent.process({"file_path": "/path/to/doc.pdf"})

            assert "pages" in result
            assert "regions" in result
            assert "reading_order" in result
            assert "layout_summary" in result
            assert "metadata" in result
            assert result["metadata"]["page_count"] == 2


class TestPageExtraction:
    """Test page extraction functionality."""

    @pytest.mark.asyncio
    async def test_extract_pages_unsupported_format(self) -> None:
        """Nicht unterstütztes Format sollte leere Liste zurückgeben."""
        agent = PageSegmentationAgent()

        pages = await agent._extract_pages(Path("/path/to/doc.xyz"), {})

        assert pages == []

    @pytest.mark.asyncio
    async def test_extract_image_page(self) -> None:
        """Bild sollte als einzelne Seite extrahiert werden."""
        agent = PageSegmentationAgent()

        # Mock cv2
        mock_cv2 = MagicMock()
        mock_cv2.imread = lambda path: np.ones((100, 200, 3), dtype=np.uint8)
        agent._cv2 = mock_cv2

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"dummy image")
            tmp_path = Path(tmp.name)

        try:
            pages = await agent._extract_image_page(tmp_path)

            assert len(pages) == 1
            assert pages[0].page_num == 0
            assert pages[0].width == 200
            assert pages[0].height == 100
            assert pages[0].image_path == str(tmp_path)
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_extract_image_page_no_opencv(self) -> None:
        """Ohne OpenCV sollte leere Liste zurückgegeben werden."""
        agent = PageSegmentationAgent()
        agent._cv2 = None

        pages = await agent._extract_image_page(Path("/path/to/image.png"))

        assert pages == []


class TestRegionTypeEnum:
    """Test RegionType enumeration."""

    def test_region_type_values(self) -> None:
        """RegionType sollte alle erwarteten Werte haben."""
        assert RegionType.TEXT.value == "text"
        assert RegionType.TABLE.value == "table"
        assert RegionType.IMAGE.value == "image"
        assert RegionType.HEADER.value == "header"
        assert RegionType.FOOTER.value == "footer"
        assert RegionType.SIDEBAR.value == "sidebar"
        assert RegionType.FIGURE.value == "figure"
        assert RegionType.CAPTION.value == "caption"


class TestLayoutTypeEnum:
    """Test LayoutType enumeration."""

    def test_layout_type_values(self) -> None:
        """LayoutType sollte alle erwarteten Werte haben."""
        assert LayoutType.SINGLE_COLUMN.value == "single_column"
        assert LayoutType.MULTI_COLUMN.value == "multi_column"
        assert LayoutType.MIXED.value == "mixed"
