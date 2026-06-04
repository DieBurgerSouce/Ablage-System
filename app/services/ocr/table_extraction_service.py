# -*- coding: utf-8 -*-
"""
Table Extraction Service.

Ermöglicht:
- Extraktion strukturierter Tabellen aus Dokumenten
- Multiple Output-Formate (Markdown, JSON-LD, CSV)
- Cell-Level Confidence Tracking
- Spanning Cell Detection (row/col spans)
- Header-Row Erkennung

Feinpoliert und durchdacht - Tabellen präzise extrahieren.
"""

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.agents.ocr.models.layout_models import (
    BoundingBox,
    DocumentLayout,
    LayoutElement,
    LayoutElementType,
    PageLayout,
    TableCell,
    TableStructure,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class TableExportFormat(str, Enum):
    """Unterstützte Export-Formate."""
    MARKDOWN = "markdown"
    CSV = "csv"
    JSON = "json"
    JSON_LD = "json_ld"
    HTML = "html"
    EXCEL_COMPATIBLE = "excel_compatible"


class TableType(str, Enum):
    """Erkannter Tabellentyp."""
    INVOICE_LINE_ITEMS = "invoice_line_items"
    PRICING_TABLE = "pricing_table"
    DATA_TABLE = "data_table"
    COMPARISON_TABLE = "comparison_table"
    SCHEDULE_TABLE = "schedule_table"
    CONTACT_TABLE = "contact_table"
    GENERIC = "generic"


class CellDataType(str, Enum):
    """Erkannter Datentyp einer Zelle."""
    TEXT = "text"
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    DATE = "date"
    EMPTY = "empty"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EnhancedTableCell:
    """Erweiterte Tabellenzelle mit zusätzlichen Metadaten."""
    row: int
    col: int
    text: str = ""
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    confidence: float = 0.0
    data_type: CellDataType = CellDataType.TEXT
    normalized_value: Optional[Union[str, float, Decimal]] = None
    bbox: Optional[BoundingBox] = None
    formatting: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "row": self.row,
            "col": self.col,
            "text": self.text,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "is_header": self.is_header,
            "confidence": round(self.confidence, 3),
            "data_type": self.data_type.value,
            "normalized_value": str(self.normalized_value) if self.normalized_value is not None else None,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "formatting": self.formatting,
        }


@dataclass
class TableColumn:
    """Metadaten für eine Tabellenspalte."""
    index: int
    header_text: str = ""
    data_type: CellDataType = CellDataType.TEXT
    width_ratio: float = 0.0  # Relative Breite (0-1)
    alignment: str = "left"  # left, center, right
    is_numeric: bool = False
    contains_currency: bool = False
    avg_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "header_text": self.header_text,
            "data_type": self.data_type.value,
            "width_ratio": round(self.width_ratio, 3),
            "alignment": self.alignment,
            "is_numeric": self.is_numeric,
            "contains_currency": self.contains_currency,
            "avg_confidence": round(self.avg_confidence, 3),
        }


@dataclass
class ExtractedTable:
    """Vollständig extrahierte Tabelle mit allen Metadaten."""
    table_id: str
    page_number: int
    num_rows: int
    num_cols: int
    cells: List[EnhancedTableCell] = field(default_factory=list)
    columns: List[TableColumn] = field(default_factory=list)
    has_header: bool = False
    header_row_count: int = 0
    table_type: TableType = TableType.GENERIC
    caption: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    overall_confidence: float = 0.0
    extraction_details: Dict[str, Any] = field(default_factory=dict)

    @property
    def data_rows(self) -> List[List[EnhancedTableCell]]:
        """Nur Datenzeilen (ohne Header)."""
        rows = []
        for row_idx in range(self.header_row_count, self.num_rows):
            row_cells = sorted(
                [c for c in self.cells if c.row == row_idx],
                key=lambda c: c.col
            )
            rows.append(row_cells)
        return rows

    @property
    def header_rows(self) -> List[List[EnhancedTableCell]]:
        """Nur Header-Zeilen."""
        rows = []
        for row_idx in range(self.header_row_count):
            row_cells = sorted(
                [c for c in self.cells if c.row == row_idx],
                key=lambda c: c.col
            )
            rows.append(row_cells)
        return rows

    def get_cell(self, row: int, col: int) -> Optional[EnhancedTableCell]:
        """Hole Zelle nach Position."""
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "table_id": self.table_id,
            "page_number": self.page_number,
            "num_rows": self.num_rows,
            "num_cols": self.num_cols,
            "has_header": self.has_header,
            "header_row_count": self.header_row_count,
            "table_type": self.table_type.value,
            "caption": self.caption,
            "overall_confidence": round(self.overall_confidence, 3),
            "cells": [c.to_dict() for c in self.cells],
            "columns": [c.to_dict() for c in self.columns],
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "extraction_details": self.extraction_details,
        }


@dataclass
class TableExtractionResult:
    """Gesamtergebnis der Tabellen-Extraktion."""
    document_id: str
    tables: List[ExtractedTable]
    total_tables: int
    page_count: int
    extraction_timestamp: str
    processing_time_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "total_tables": self.total_tables,
            "page_count": self.page_count,
            "extraction_timestamp": self.extraction_timestamp,
            "processing_time_ms": self.processing_time_ms,
            "tables": [t.to_dict() for t in self.tables],
            "metadata": self.metadata,
        }


# =============================================================================
# Helper Functions
# =============================================================================


def parse_german_decimal(value: str) -> Optional[Decimal]:
    """Konvertiert deutsches Zahlenformat zu Decimal."""
    if not value or not value.strip():
        return None

    # Bereinige String
    cleaned = value.strip()
    cleaned = re.sub(r"[€$£¥]", "", cleaned)
    cleaned = cleaned.strip()

    # Prüfe auf leeren String nach Bereinigung
    if not cleaned:
        return None

    # Entferne Tausendertrennzeichen und konvertiere Dezimalkomma
    if "," in cleaned and "." in cleaned:
        # Format: 1.234,56 (deutsch)
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        # Format: 1,234.56 (englisch)
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Nur Komma: 1234,56 oder 1,234 (Tausendertrenner)
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            cleaned = cleaned.replace(",", ".")
        elif len(parts) == 2 and len(parts[1]) == 3:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")

    # Entferne alle verbleibenden Nicht-Ziffern außer Punkt und Minus
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def detect_cell_data_type(text: str) -> Tuple[CellDataType, Optional[Union[str, float, Decimal]]]:
    """Erkennt den Datentyp einer Zelle und normalisiert den Wert."""
    if not text or not text.strip():
        return CellDataType.EMPTY, None

    text = text.strip()

    # Währung
    currency_pattern = r"^[€$£¥]?\s*[\d.,]+\s*[€$£¥]?$"
    if re.match(currency_pattern, text):
        value = parse_german_decimal(text)
        if value is not None:
            return CellDataType.CURRENCY, value

    # Prozent
    if text.endswith("%"):
        value = parse_german_decimal(text[:-1])
        if value is not None:
            return CellDataType.PERCENTAGE, value

    # Zahl
    number_pattern = r"^[\d.,\-]+$"
    if re.match(number_pattern, text):
        value = parse_german_decimal(text)
        if value is not None:
            return CellDataType.NUMBER, value

    # Datum (deutsche Formate)
    date_patterns = [
        r"^\d{1,2}\.\d{1,2}\.\d{2,4}$",  # DD.MM.YYYY
        r"^\d{4}-\d{2}-\d{2}$",           # YYYY-MM-DD
        r"^\d{1,2}/\d{1,2}/\d{2,4}$",    # DD/MM/YYYY
    ]
    for pattern in date_patterns:
        if re.match(pattern, text):
            return CellDataType.DATE, text

    return CellDataType.TEXT, text


def detect_table_type(table: ExtractedTable) -> TableType:
    """Erkennt den Typ einer Tabelle basierend auf Inhalt."""
    header_texts = [c.text.lower() for c in table.cells if c.is_header]
    all_text = " ".join([c.text.lower() for c in table.cells])

    # Invoice Line Items
    invoice_keywords = ["pos", "artikel", "menge", "preis", "summe", "betrag", "netto", "brutto"]
    if sum(1 for kw in invoice_keywords if kw in all_text) >= 3:
        return TableType.INVOICE_LINE_ITEMS

    # Pricing Table
    pricing_keywords = ["preis", "kosten", "tarif", "rate", "gebühr"]
    if sum(1 for kw in pricing_keywords if kw in all_text) >= 2:
        return TableType.PRICING_TABLE

    # Schedule/Calendar Table
    schedule_keywords = ["datum", "termin", "zeit", "uhrzeit", "tag", "woche"]
    if sum(1 for kw in schedule_keywords if kw in all_text) >= 2:
        return TableType.SCHEDULE_TABLE

    # Comparison Table
    if table.num_cols >= 3 and table.has_header:
        # Prüfe ob Headers Vergleichsitems sind
        return TableType.COMPARISON_TABLE

    # Contact Table
    contact_keywords = ["name", "email", "telefon", "adresse", "kontakt"]
    if sum(1 for kw in contact_keywords if kw in all_text) >= 2:
        return TableType.CONTACT_TABLE

    # Data Table
    numeric_cells = sum(1 for c in table.cells if c.data_type in [CellDataType.NUMBER, CellDataType.CURRENCY])
    if numeric_cells > len(table.cells) * 0.3:
        return TableType.DATA_TABLE

    return TableType.GENERIC


# =============================================================================
# Table Extraction Service
# =============================================================================


class TableExtractionService:
    """
    Service zur Extraktion und Verarbeitung von Tabellen aus Dokumenten.

    Features:
    - Cell-Level Confidence Tracking
    - Spanning Cell Detection
    - Header-Row Erkennung
    - Multiple Export-Formate
    - Automatische Typerkennung
    """

    # Schwellenwerte
    HEADER_CONFIDENCE_THRESHOLD = 0.7
    MIN_HEADER_SCORE = 0.5

    def __init__(self, db: Optional[AsyncSession] = None):
        """Initialisiere Table Extraction Service."""
        self.db = db

    async def extract_tables_from_document(
        self,
        document_id: str,
        layout: Optional[DocumentLayout] = None
    ) -> TableExtractionResult:
        """
        Extrahiert alle Tabellen aus einem Dokument.

        Args:
            document_id: Dokument-ID
            layout: Optional - bereits extrahiertes Layout

        Returns:
            TableExtractionResult mit allen Tabellen
        """
        import time
        start_time = time.time()

        tables: List[ExtractedTable] = []
        page_count = 0

        # Layout laden falls nicht übergeben
        if layout is None:
            layout = await self._load_document_layout(document_id)

        if layout is None:
            logger.warning(
                "table_extraction_no_layout",
                document_id=document_id
            )
            return TableExtractionResult(
                document_id=document_id,
                tables=[],
                total_tables=0,
                page_count=0,
                extraction_timestamp=datetime.now(timezone.utc).isoformat(),
                processing_time_ms=0,
                metadata={"error": "Kein Layout verfügbar"},
            )

        page_count = layout.page_count

        # Tabellen von allen Seiten extrahieren
        table_idx = 0
        for page in layout.pages:
            for element in page.elements:
                if element.element_type == LayoutElementType.TABLE and element.table:
                    table_id = f"{document_id}_table_{table_idx}"
                    extracted = self._extract_table(
                        element.table,
                        table_id=table_id,
                        page_number=page.page_number,
                        element_bbox=element.bbox,
                    )
                    tables.append(extracted)
                    table_idx += 1

        processing_time = int((time.time() - start_time) * 1000)

        logger.info(
            "table_extraction_complete",
            document_id=document_id,
            table_count=len(tables),
            page_count=page_count,
            processing_time_ms=processing_time,
        )

        return TableExtractionResult(
            document_id=document_id,
            tables=tables,
            total_tables=len(tables),
            page_count=page_count,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            processing_time_ms=processing_time,
            metadata={
                "has_invoice_tables": any(t.table_type == TableType.INVOICE_LINE_ITEMS for t in tables),
                "avg_confidence": sum(t.overall_confidence for t in tables) / len(tables) if tables else 0,
            },
        )

    def _extract_table(
        self,
        table: TableStructure,
        table_id: str,
        page_number: int,
        element_bbox: Optional[BoundingBox] = None
    ) -> ExtractedTable:
        """Extrahiert eine einzelne Tabelle mit erweiterten Metadaten."""
        cells: List[EnhancedTableCell] = []
        cell_confidences = []

        # Zellen konvertieren und anreichern
        for cell in table.cells:
            data_type, normalized = detect_cell_data_type(cell.text)

            enhanced = EnhancedTableCell(
                row=cell.row,
                col=cell.col,
                text=cell.text,
                row_span=cell.row_span,
                col_span=cell.col_span,
                is_header=cell.is_header,
                confidence=cell.confidence,
                data_type=data_type,
                normalized_value=normalized,
                bbox=cell.bbox,
            )
            cells.append(enhanced)

            if cell.confidence > 0:
                cell_confidences.append(cell.confidence)

        # Header-Erkennung verfeinern
        header_row_count = self._detect_header_rows(cells, table.num_rows, table.num_cols)

        # Header-Zellen markieren
        for cell in cells:
            if cell.row < header_row_count:
                cell.is_header = True

        # Spalten-Metadaten berechnen
        columns = self._analyze_columns(cells, table.num_cols, table.bbox)

        # Gesamtconfidence
        overall_confidence = sum(cell_confidences) / len(cell_confidences) if cell_confidences else 0.0

        extracted = ExtractedTable(
            table_id=table_id,
            page_number=page_number,
            num_rows=table.num_rows,
            num_cols=table.num_cols,
            cells=cells,
            columns=columns,
            has_header=header_row_count > 0,
            header_row_count=header_row_count,
            caption=table.caption,
            bbox=element_bbox or table.bbox,
            overall_confidence=overall_confidence,
            extraction_details={
                "spanning_cells": sum(1 for c in cells if c.row_span > 1 or c.col_span > 1),
                "numeric_cells": sum(1 for c in cells if c.data_type in [CellDataType.NUMBER, CellDataType.CURRENCY]),
                "empty_cells": sum(1 for c in cells if c.data_type == CellDataType.EMPTY),
            },
        )

        # Tabellentyp erkennen
        extracted.table_type = detect_table_type(extracted)

        return extracted

    def _detect_header_rows(
        self,
        cells: List[EnhancedTableCell],
        num_rows: int,
        num_cols: int
    ) -> int:
        """Erkennt die Anzahl der Header-Zeilen."""
        if num_rows == 0:
            return 0

        # Score für jede Zeile berechnen
        row_scores = []

        for row_idx in range(min(3, num_rows)):  # Max 3 Header-Zeilen
            row_cells = [c for c in cells if c.row == row_idx]

            if not row_cells:
                row_scores.append(0)
                continue

            score = 0

            # Kriterium 1: Alle Zellen sind Text (keine Zahlen)
            text_cells = sum(1 for c in row_cells if c.data_type == CellDataType.TEXT)
            if text_cells == len(row_cells):
                score += 0.3

            # Kriterium 2: Kurze Texte (typisch für Header)
            short_texts = sum(1 for c in row_cells if len(c.text) < 30)
            if short_texts >= len(row_cells) * 0.7:
                score += 0.2

            # Kriterium 3: Typische Header-Keywords
            header_keywords = [
                "nr", "pos", "artikel", "beschreibung", "menge", "preis",
                "summe", "einheit", "bezeichnung", "name", "datum", "betrag"
            ]
            keyword_matches = sum(
                1 for c in row_cells
                if any(kw in c.text.lower() for kw in header_keywords)
            )
            if keyword_matches >= 2:
                score += 0.3

            # Kriterium 4: Unterschied zu nächster Zeile
            if row_idx < num_rows - 1:
                next_row_cells = [c for c in cells if c.row == row_idx + 1]
                next_row_types = {c.data_type for c in next_row_cells}
                this_row_types = {c.data_type for c in row_cells}

                if next_row_types != this_row_types:
                    score += 0.2

            row_scores.append(score)

        # Finde Header-Zeilen
        header_count = 0
        for score in row_scores:
            if score >= self.MIN_HEADER_SCORE:
                header_count += 1
            else:
                break

        return header_count

    def _analyze_columns(
        self,
        cells: List[EnhancedTableCell],
        num_cols: int,
        table_bbox: Optional[BoundingBox]
    ) -> List[TableColumn]:
        """Analysiert Spalten-Metadaten."""
        columns = []

        for col_idx in range(num_cols):
            col_cells = [c for c in cells if c.col == col_idx]

            if not col_cells:
                columns.append(TableColumn(index=col_idx))
                continue

            # Header-Text
            header_cells = [c for c in col_cells if c.is_header]
            header_text = header_cells[0].text if header_cells else ""

            # Datentyp-Analyse (ignoriere Header)
            data_cells = [c for c in col_cells if not c.is_header]
            data_types = [c.data_type for c in data_cells]

            # Häufigster Datentyp
            if data_types:
                type_counts: Dict[CellDataType, int] = {}
                for dt in data_types:
                    type_counts[dt] = type_counts.get(dt, 0) + 1
                dominant_type = max(type_counts, key=type_counts.get)  # type: ignore
            else:
                dominant_type = CellDataType.TEXT

            # Numerisch?
            is_numeric = dominant_type in [CellDataType.NUMBER, CellDataType.CURRENCY, CellDataType.PERCENTAGE]

            # Währung?
            contains_currency = CellDataType.CURRENCY in data_types

            # Durchschnittliche Confidence
            confidences = [c.confidence for c in col_cells if c.confidence > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            # Breite berechnen (falls BBoxes verfügbar)
            width_ratio = 0.0
            if table_bbox:
                col_bboxes = [c.bbox for c in col_cells if c.bbox]
                if col_bboxes:
                    min_x = min(b.x0 for b in col_bboxes)
                    max_x = max(b.x1 for b in col_bboxes)
                    width_ratio = (max_x - min_x) / table_bbox.width if table_bbox.width > 0 else 0

            # Alignment (basierend auf Datentyp)
            alignment = "right" if is_numeric else "left"

            columns.append(TableColumn(
                index=col_idx,
                header_text=header_text,
                data_type=dominant_type,
                width_ratio=width_ratio,
                alignment=alignment,
                is_numeric=is_numeric,
                contains_currency=contains_currency,
                avg_confidence=avg_confidence,
            ))

        return columns

    async def _load_document_layout(self, document_id: str) -> Optional[DocumentLayout]:
        """Lädt das Layout eines Dokuments aus der Datenbank."""
        if not self.db:
            return None

        try:
            from app.db.models import Document

            doc_query = select(Document).where(Document.id == document_id)
            result = await self.db.execute(doc_query)
            document = result.scalar_one_or_none()

            if not document or not document.metadata:
                return None

            # Layout aus Metadata extrahieren
            layout_data = document.metadata.get("layout")
            if not layout_data:
                return None

            # Layout rekonstruieren (vereinfacht)
            # In echter Implementation: Vollständige Deserialisierung
            return None

        except Exception as e:
            logger.error(
                "layout_load_error",
                document_id=document_id,
                **safe_error_log(e)
            )
            return None

    # =========================================================================
    # Export Functions
    # =========================================================================

    def export_table(
        self,
        table: ExtractedTable,
        format: TableExportFormat,
        include_metadata: bool = False
    ) -> str:
        """
        Exportiert eine Tabelle in das gewünschte Format.

        Args:
            table: Zu exportierende Tabelle
            format: Export-Format
            include_metadata: Metadaten inkludieren

        Returns:
            Exportierte Tabelle als String
        """
        if format == TableExportFormat.MARKDOWN:
            return self._export_markdown(table)
        elif format == TableExportFormat.CSV:
            return self._export_csv(table)
        elif format == TableExportFormat.JSON:
            return self._export_json(table, include_metadata)
        elif format == TableExportFormat.JSON_LD:
            return self._export_json_ld(table)
        elif format == TableExportFormat.HTML:
            return self._export_html(table)
        elif format == TableExportFormat.EXCEL_COMPATIBLE:
            return self._export_excel_compatible_csv(table)
        else:
            return self._export_markdown(table)

    def _export_markdown(self, table: ExtractedTable) -> str:
        """Exportiert als Markdown-Tabelle."""
        if not table.cells or table.num_rows == 0 or table.num_cols == 0:
            return ""

        # Grid erstellen
        grid: List[List[str]] = [["" for _ in range(table.num_cols)] for _ in range(table.num_rows)]

        for cell in table.cells:
            if 0 <= cell.row < table.num_rows and 0 <= cell.col < table.num_cols:
                grid[cell.row][cell.col] = cell.text

        lines = []

        for row_idx, row in enumerate(grid):
            # Escape Pipes in Zellen
            escaped = [c.replace("|", "\\|") for c in row]
            line = "| " + " | ".join(escaped) + " |"
            lines.append(line)

            # Separator nach Header
            if row_idx == table.header_row_count - 1 and table.has_header:
                # Alignment-basierter Separator
                separators = []
                for col in table.columns:
                    if col.alignment == "right":
                        separators.append("---:")
                    elif col.alignment == "center":
                        separators.append(":---:")
                    else:
                        separators.append("---")
                separator = "| " + " | ".join(separators) + " |"
                lines.append(separator)
            elif row_idx == 0 and not table.has_header:
                # Default Separator
                separator = "| " + " | ".join(["---"] * table.num_cols) + " |"
                lines.append(separator)

        return "\n".join(lines)

    def _export_csv(self, table: ExtractedTable) -> str:
        """Exportiert als CSV."""
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quotechar='"')

        # Grid erstellen
        for row_idx in range(table.num_rows):
            row_cells = sorted(
                [c for c in table.cells if c.row == row_idx],
                key=lambda c: c.col
            )

            # Lücken füllen
            row = []
            for col_idx in range(table.num_cols):
                cell = next((c for c in row_cells if c.col == col_idx), None)
                row.append(cell.text if cell else "")

            writer.writerow(row)

        return output.getvalue()

    def _export_excel_compatible_csv(self, table: ExtractedTable) -> str:
        """Exportiert als Excel-kompatibles CSV mit BOM."""
        csv_content = self._export_csv(table)
        # UTF-8 BOM für Excel
        return "\ufeff" + csv_content

    def _export_json(self, table: ExtractedTable, include_metadata: bool) -> str:
        """Exportiert als JSON."""
        if include_metadata:
            return json.dumps(table.to_dict(), ensure_ascii=False, indent=2)

        # Nur Daten
        grid = []
        for row_idx in range(table.num_rows):
            row_cells = sorted(
                [c for c in table.cells if c.row == row_idx],
                key=lambda c: c.col
            )
            row = {
                table.columns[c.col].header_text or f"col_{c.col}": c.text
                for c in row_cells
                if c.col < len(table.columns)
            }
            grid.append(row)

        return json.dumps(grid, ensure_ascii=False, indent=2)

    def _export_json_ld(self, table: ExtractedTable) -> str:
        """Exportiert als JSON-LD (Linked Data)."""
        # Schema.org Table Markup
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Table",
            "name": table.caption or f"Table {table.table_id}",
            "about": table.table_type.value,
            "numberOfRows": table.num_rows,
            "numberOfColumns": table.num_cols,
            "creator": "Ablage-System OCR",
            "dateCreated": datetime.now(timezone.utc).isoformat(),
        }

        # Header
        if table.has_header and table.columns:
            json_ld["tableHeader"] = {
                "@type": "TableSection",
                "row": [{
                    "@type": "TableRow",
                    "cell": [
                        {"@type": "TableCell", "cellContent": col.header_text}
                        for col in table.columns
                    ]
                }]
            }

        # Body
        body_rows = []
        for row_idx in range(table.header_row_count, table.num_rows):
            row_cells = sorted(
                [c for c in table.cells if c.row == row_idx],
                key=lambda c: c.col
            )
            body_rows.append({
                "@type": "TableRow",
                "cell": [
                    {
                        "@type": "TableCell",
                        "cellContent": c.text,
                        "position": f"R{c.row}C{c.col}",
                    }
                    for c in row_cells
                ]
            })

        if body_rows:
            json_ld["tableBody"] = {
                "@type": "TableSection",
                "row": body_rows
            }

        # Confidence als zusätzliche Property
        json_ld["additionalProperty"] = {
            "@type": "PropertyValue",
            "name": "confidence",
            "value": table.overall_confidence,
        }

        return json.dumps(json_ld, ensure_ascii=False, indent=2)

    def _export_html(self, table: ExtractedTable) -> str:
        """Exportiert als HTML-Tabelle."""
        html_parts = ['<table class="extracted-table">']

        # Caption
        if table.caption:
            html_parts.append(f'  <caption>{self._html_escape(table.caption)}</caption>')

        # Header
        if table.has_header:
            html_parts.append('  <thead>')
            for row_idx in range(table.header_row_count):
                row_cells = sorted(
                    [c for c in table.cells if c.row == row_idx],
                    key=lambda c: c.col
                )
                html_parts.append('    <tr>')
                for cell in row_cells:
                    attrs = []
                    if cell.col_span > 1:
                        attrs.append(f'colspan="{cell.col_span}"')
                    if cell.row_span > 1:
                        attrs.append(f'rowspan="{cell.row_span}"')
                    attrs_str = " " + " ".join(attrs) if attrs else ""
                    html_parts.append(f'      <th{attrs_str}>{self._html_escape(cell.text)}</th>')
                html_parts.append('    </tr>')
            html_parts.append('  </thead>')

        # Body
        html_parts.append('  <tbody>')
        for row_idx in range(table.header_row_count, table.num_rows):
            row_cells = sorted(
                [c for c in table.cells if c.row == row_idx],
                key=lambda c: c.col
            )
            html_parts.append('    <tr>')
            for cell in row_cells:
                attrs = []
                if cell.col_span > 1:
                    attrs.append(f'colspan="{cell.col_span}"')
                if cell.row_span > 1:
                    attrs.append(f'rowspan="{cell.row_span}"')

                # Alignment
                col = table.columns[cell.col] if cell.col < len(table.columns) else None
                if col and col.alignment != "left":
                    attrs.append(f'style="text-align: {col.alignment}"')

                attrs_str = " " + " ".join(attrs) if attrs else ""
                html_parts.append(f'      <td{attrs_str}>{self._html_escape(cell.text)}</td>')
            html_parts.append('    </tr>')
        html_parts.append('  </tbody>')

        html_parts.append('</table>')

        return "\n".join(html_parts)

    def _html_escape(self, text: str) -> str:
        """Escaped HTML-Sonderzeichen."""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def export_all_tables(
        self,
        result: TableExtractionResult,
        format: TableExportFormat,
        include_metadata: bool = False
    ) -> str:
        """
        Exportiert alle Tabellen aus einem Ergebnis.

        Args:
            result: Extraction-Ergebnis
            format: Export-Format
            include_metadata: Metadaten inkludieren

        Returns:
            Alle Tabellen als String (getrennt durch Leerzeilen)
        """
        if format == TableExportFormat.JSON or format == TableExportFormat.JSON_LD:
            # JSON: Als Array
            if format == TableExportFormat.JSON_LD:
                tables_json = [json.loads(self.export_table(t, format)) for t in result.tables]
            else:
                if include_metadata:
                    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
                tables_json = [json.loads(self.export_table(t, format, include_metadata)) for t in result.tables]
            return json.dumps(tables_json, ensure_ascii=False, indent=2)
        else:
            # Andere Formate: Mit Trennern
            parts = []
            for i, table in enumerate(result.tables):
                if format == TableExportFormat.MARKDOWN:
                    parts.append(f"### Tabelle {i+1} (Seite {table.page_number})")
                    if table.caption:
                        parts.append(f"*{table.caption}*")
                parts.append(self.export_table(table, format, include_metadata))
            return "\n\n".join(parts)


# =============================================================================
# Singleton
# =============================================================================


_table_extraction_service: Optional[TableExtractionService] = None


def get_table_extraction_service(db: Optional[AsyncSession] = None) -> TableExtractionService:
    """Hole Table Extraction Service Instanz."""
    global _table_extraction_service
    if _table_extraction_service is None or db is not None:
        _table_extraction_service = TableExtractionService(db)
    return _table_extraction_service
