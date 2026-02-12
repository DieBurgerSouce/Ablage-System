# -*- coding: utf-8 -*-
"""
PDF Export Service.

Generiert branded PDF-Reports mit ReportLab (pure Python, keine System-Dependencies).
Wichtig für On-Premises Docker-Deployment ohne externe Dependencies.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.reports.report_templates import ChartConfig, ReportColumn

logger = structlog.get_logger(__name__)

# Try to import ReportLab charting - not all installations include renderPM
try:
    from reportlab.graphics import renderPM
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing, String
    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False
    logger.warning("reportlab_charts_unavailable", msg="ReportLab chart support not available. Install reportlab[renderPM] for chart support.")


# =============================================================================
# CONSTANTS
# =============================================================================

# A4 Dimensions
PAGE_WIDTH, PAGE_HEIGHT = A4

# Margins
MARGIN_LEFT = 20 * mm
MARGIN_RIGHT = 20 * mm
MARGIN_TOP = 20 * mm
MARGIN_BOTTOM = 20 * mm

# Colors
COLOR_HEADER_BG = colors.HexColor("#4472C4")
COLOR_HEADER_TEXT = colors.white
COLOR_ROW_EVEN = colors.HexColor("#F2F2F2")
COLOR_ROW_ODD = colors.white
COLOR_BORDER = colors.HexColor("#CCCCCC")

# Fonts
FONT_TITLE = "Helvetica-Bold"
FONT_HEADER = "Helvetica-Bold"
FONT_BODY = "Helvetica"
FONT_SIZE_TITLE = 18
FONT_SIZE_SUBTITLE = 12
FONT_SIZE_HEADER = 10
FONT_SIZE_BODY = 9


# =============================================================================
# PDF EXPORT SERVICE
# =============================================================================


class PdfExportService:
    """Service für PDF-Report-Generierung mit ReportLab."""

    def __init__(self) -> None:
        """Initialisiert den PDF Export Service."""
        self.styles = getSampleStyleSheet()

        # Custom Styles
        self.style_title = ParagraphStyle(
            "CustomTitle",
            parent=self.styles["Title"],
            fontName=FONT_TITLE,
            fontSize=FONT_SIZE_TITLE,
            textColor=COLOR_HEADER_BG,
            spaceAfter=12,
        )

        self.style_subtitle = ParagraphStyle(
            "CustomSubtitle",
            parent=self.styles["Normal"],
            fontName=FONT_BODY,
            fontSize=FONT_SIZE_SUBTITLE,
            textColor=colors.HexColor("#666666"),
            spaceAfter=20,
        )

    async def generate_report_pdf(
        self,
        title: str,
        subtitle: str,
        columns: List[ReportColumn],
        data: List[Dict[str, object]],
        charts: Optional[List[bytes]] = None,
        company_name: str = "Ablage-System",
    ) -> bytes:
        """
        Generiert einen branded PDF-Report.

        Args:
            title: Report-Titel (z.B. "Kostenauswertung")
            subtitle: Untertitel mit Zeitraum
            columns: Liste der Spalten-Definitionen
            data: Report-Daten als Liste von Dicts
            charts: Optional PNG-Chart-Bilder als Bytes
            company_name: Firmenname für Header

        Returns:
            PDF als Bytes
        """
        logger.info(
            "generate_report_pdf",
            title=title,
            rows=len(data),
            columns=len(columns),
            charts=len(charts) if charts else 0,
        )

        # Create PDF in memory
        buffer = io.BytesIO()

        # Create document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=title,
            author=company_name,
        )

        # Build story (list of flowables)
        story: List[object] = []

        # Header
        story.append(Paragraph(f"<b>{company_name}</b>", self.style_title))
        story.append(Spacer(1, 6))

        # Date (German format)
        current_date = datetime.now().strftime("%d.%m.%Y")
        story.append(
            Paragraph(
                f"Erstellt am: {current_date}",
                self.style_subtitle,
            )
        )

        # Title
        story.append(Spacer(1, 12))
        story.append(Paragraph(title, self.style_title))

        # Subtitle
        if subtitle:
            story.append(Paragraph(subtitle, self.style_subtitle))

        story.append(Spacer(1, 12))

        # Table
        if data:
            table = self._create_table(columns, data)
            story.append(table)
        else:
            story.append(Paragraph("Keine Daten verfügbar", self.styles["Normal"]))

        # Charts
        if charts:
            story.append(PageBreak())
            story.append(Paragraph("Visualisierungen", self.style_title))
            story.append(Spacer(1, 12))

            for chart_bytes in charts:
                try:
                    chart_img = Image(io.BytesIO(chart_bytes))
                    # Scale to fit page width
                    chart_img.drawWidth = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
                    chart_img.drawHeight = (PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM) * 0.4
                    story.append(chart_img)
                    story.append(Spacer(1, 12))
                except Exception as e:
                    logger.warning("chart_image_failed", error=str(e))

        # Page footer with page numbers
        def add_page_number(canvas: object, doc: object) -> None:
            """Fügt Seitenzahlen hinzu."""
            page_num = canvas.getPageNumber()
            text = f"Seite {page_num}"
            canvas.saveState()
            canvas.setFont(FONT_BODY, FONT_SIZE_BODY)
            canvas.drawRightString(
                PAGE_WIDTH - MARGIN_RIGHT,
                MARGIN_BOTTOM / 2,
                text,
            )
            canvas.restoreState()

        # Build PDF
        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)

        # Get bytes
        buffer.seek(0)
        pdf_bytes = buffer.getvalue()

        logger.info("generate_report_pdf_complete", size_bytes=len(pdf_bytes))

        return pdf_bytes

    def generate_charts_from_config(
        self,
        chart_configs: List[ChartConfig],
        data: List[Dict[str, object]],
    ) -> List[bytes]:
        """
        Generiert Chart-Bilder für alle ChartConfigs.

        Args:
            chart_configs: Liste von Chart-Konfigurationen
            data: Report-Daten als Liste von Dicts

        Returns:
            Liste von PNG-Bytes für jeden Chart
        """
        if not CHARTS_AVAILABLE:
            logger.warning("charts_skipped", reason="ReportLab chart support not available")
            return []

        chart_images: List[bytes] = []

        for chart_config in chart_configs:
            try:
                chart_bytes = self._render_chart_image(chart_config, data)
                chart_images.append(chart_bytes)
                logger.info(
                    "chart_generated",
                    chart_type=chart_config.chart_type,
                    title=chart_config.title,
                    size_bytes=len(chart_bytes),
                )
            except Exception as e:
                logger.warning(
                    "chart_generation_failed",
                    chart_type=chart_config.chart_type,
                    title=chart_config.title,
                    error=str(e),
                )
                # Don't let one failed chart break the whole PDF
                continue

        return chart_images

    def _render_chart_image(
        self,
        chart_config: ChartConfig,
        data: List[Dict[str, object]],
    ) -> bytes:
        """
        Rendert einen Chart als PNG bytes basierend auf ChartConfig und Report-Daten.

        Args:
            chart_config: Chart-Konfiguration
            data: Report-Daten

        Returns:
            PNG bytes

        Raises:
            ValueError: Wenn Chart-Typ nicht unterstützt wird
        """
        if not CHARTS_AVAILABLE:
            raise RuntimeError("ReportLab chart support not available")

        # Create drawing
        width = 400
        height = 300
        drawing = Drawing(width, height)

        # Extract data for chart
        x_values: List[str] = []
        y_values: List[float] = []

        for row in data:
            x_val = row.get(chart_config.x_axis)
            y_val = row.get(chart_config.y_axis)

            if x_val is not None:
                x_values.append(str(x_val))

            if y_val is not None:
                try:
                    y_values.append(float(y_val))
                except (ValueError, TypeError):
                    y_values.append(0.0)

        # Limit to first 10 data points to avoid overcrowding
        if len(x_values) > 10:
            x_values = x_values[:10]
            y_values = y_values[:10]

        # Create chart based on type
        if chart_config.chart_type == "bar":
            chart = self._create_bar_chart(x_values, y_values, width, height)
        elif chart_config.chart_type == "line" or chart_config.chart_type == "area":
            chart = self._create_line_chart(x_values, y_values, width, height, chart_config.chart_type == "area")
        elif chart_config.chart_type == "pie":
            chart = self._create_pie_chart(x_values, y_values, width, height)
        else:
            raise ValueError(f"Unsupported chart type: {chart_config.chart_type}")

        drawing.add(chart)

        # Add title
        title = String(
            width / 2,
            height - 20,
            chart_config.title,
            fontSize=12,
            fillColor=COLOR_HEADER_BG,
            textAnchor="middle",
            fontName=FONT_HEADER,
        )
        drawing.add(title)

        # Render to PNG
        png_bytes = renderPM.drawToString(drawing, fmt="PNG")
        return png_bytes

    def _create_bar_chart(
        self,
        x_values: List[str],
        y_values: List[float],
        width: int,
        height: int,
    ) -> VerticalBarChart:
        """Erstellt ein VerticalBarChart."""
        chart = VerticalBarChart()
        chart.x = 50
        chart.y = 50
        chart.width = width - 100
        chart.height = height - 100

        chart.data = [y_values]
        chart.categoryAxis.categoryNames = x_values
        chart.categoryAxis.labels.angle = 45
        chart.categoryAxis.labels.fontSize = 8

        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(y_values) * 1.1 if y_values else 100
        chart.valueAxis.labels.fontSize = 8

        chart.bars[0].fillColor = COLOR_HEADER_BG

        return chart

    def _create_line_chart(
        self,
        x_values: List[str],
        y_values: List[float],
        width: int,
        height: int,
        fill_area: bool = False,
    ) -> HorizontalLineChart:
        """Erstellt ein HorizontalLineChart (mit optionalem Area-Fill)."""
        chart = HorizontalLineChart()
        chart.x = 50
        chart.y = 50
        chart.width = width - 100
        chart.height = height - 100

        chart.data = [y_values]
        chart.categoryAxis.categoryNames = x_values
        chart.categoryAxis.labels.angle = 45
        chart.categoryAxis.labels.fontSize = 8

        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(y_values) * 1.1 if y_values else 100
        chart.valueAxis.labels.fontSize = 8

        chart.lines[0].strokeColor = COLOR_HEADER_BG
        chart.lines[0].strokeWidth = 2

        # For area charts, fill below the line
        if fill_area:
            chart.fillColor = colors.HexColor("#E8F0FE")

        return chart

    def _create_pie_chart(
        self,
        x_values: List[str],
        y_values: List[float],
        width: int,
        height: int,
    ) -> Pie:
        """Erstellt ein Pie Chart."""
        chart = Pie()
        chart.x = width / 2 - 75
        chart.y = height / 2 - 75
        chart.width = 150
        chart.height = 150

        chart.data = y_values
        chart.labels = x_values

        # Use a color palette
        chart.slices.strokeWidth = 0.5
        chart.slices.strokeColor = colors.white

        # Color palette
        color_palette = [
            COLOR_HEADER_BG,
            colors.HexColor("#70AD47"),
            colors.HexColor("#FFC000"),
            colors.HexColor("#5B9BD5"),
            colors.HexColor("#C55A11"),
            colors.HexColor("#264478"),
        ]

        for i in range(len(y_values)):
            chart.slices[i].fillColor = color_palette[i % len(color_palette)]

        return chart

    def _create_table(
        self,
        columns: List[ReportColumn],
        data: List[Dict[str, object]],
    ) -> Table:
        """
        Erstellt eine formatierte Tabelle für den PDF-Report.

        Args:
            columns: Spalten-Definitionen
            data: Daten-Zeilen

        Returns:
            ReportLab Table object
        """
        # Build table data
        table_data: List[List[str]] = []

        # Header row
        header_row = [col.label for col in columns]
        table_data.append(header_row)

        # Data rows
        for row_dict in data:
            row = []
            for col in columns:
                value = row_dict.get(col.key)
                formatted_value = self._format_cell_value(value, col.format_type)
                row.append(formatted_value)
            table_data.append(row)

        # Create table
        table = Table(table_data, repeatRows=1)

        # Calculate column widths (equal distribution)
        col_width = (PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT) / len(columns)

        # Apply styling
        style = TableStyle([
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_HEADER_TEXT),
            ("FONTNAME", (0, 0), (-1, 0), FONT_HEADER),
            ("FONTSIZE", (0, 0), (-1, 0), FONT_SIZE_HEADER),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),

            # Data rows
            ("FONTNAME", (0, 1), (-1, -1), FONT_BODY),
            ("FONTSIZE", (0, 1), (-1, -1), FONT_SIZE_BODY),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),

            # Borders
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("LINEBELOW", (0, 0), (-1, 0), 2, COLOR_HEADER_BG),

            # Padding
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])

        # Alternating row colors
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style.add("BACKGROUND", (0, i), (-1, i), COLOR_ROW_EVEN)
            else:
                style.add("BACKGROUND", (0, i), (-1, i), COLOR_ROW_ODD)

        # Right-align numeric columns
        for col_idx, col in enumerate(columns):
            if col.format_type in ["currency", "number", "percent"]:
                style.add("ALIGN", (col_idx, 1), (col_idx, -1), "RIGHT")

        table.setStyle(style)

        return table

    def _format_cell_value(self, value: object, format_type: str) -> str:
        """
        Formatiert einen Zellwert basierend auf dem Format-Typ.

        Args:
            value: Zu formatierender Wert
            format_type: Format-Typ (currency, number, date, text, percent)

        Returns:
            Formatierter String (German locale)
        """
        if value is None:
            return ""

        if format_type == "currency":
            try:
                num_value = float(value)
                # German format: 1.234,56 €
                formatted = f"{num_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                return f"{formatted} €"
            except (ValueError, TypeError):
                return str(value)

        elif format_type == "number":
            try:
                num_value = float(value)
                # German format: 1.234
                formatted = f"{num_value:,.0f}".replace(",", ".")
                return formatted
            except (ValueError, TypeError):
                return str(value)

        elif format_type == "percent":
            try:
                num_value = float(value)
                # German format: 12,34%
                formatted = f"{num_value:.2f}".replace(".", ",")
                return f"{formatted}%"
            except (ValueError, TypeError):
                return str(value)

        elif format_type == "date":
            if isinstance(value, datetime):
                # German format: dd.MM.yyyy
                return value.strftime("%d.%m.%Y")
            elif isinstance(value, str):
                try:
                    # Try to parse ISO format
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return dt.strftime("%d.%m.%Y")
                except Exception:
                    return value
            return str(value)

        else:  # text
            return str(value)
