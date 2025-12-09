"""Layout-Modelle für Dokumentstruktur-Analyse.

Diese Modelle repräsentieren die von Docling extrahierte Dokumentstruktur:
- Bounding Boxes für Positionierung
- Tabellen mit Zellen-Level-Daten
- Layout-Elemente (Text, Tabellen, Bilder, etc.)
- Seiten- und Dokument-Level-Strukturen
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LayoutElementType(str, Enum):
    """Dokumentlayout-Elementtypen von Docling."""

    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    HEADING = "heading"
    LIST = "list"
    FOOTER = "footer"
    HEADER = "header"
    PAGE_NUMBER = "page_number"
    CAPTION = "caption"
    FORMULA = "formula"
    CODE = "code"
    FOOTNOTE = "footnote"
    UNKNOWN = "unknown"


@dataclass
class BoundingBox:
    """Begrenzungsrahmen-Koordinaten.

    Koordinatensystem: Ursprung oben-links, y wächst nach unten.
    """

    x0: float  # Links
    y0: float  # Oben
    x1: float  # Rechts
    y1: float  # Unten

    @property
    def width(self) -> float:
        """Breite des Begrenzungsrahmens."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Höhe des Begrenzungsrahmens."""
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        """Fläche des Begrenzungsrahmens."""
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        """Mittelpunkt des Begrenzungsrahmens."""
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def contains_point(self, x: float, y: float) -> bool:
        """Prüft ob ein Punkt im Begrenzungsrahmen liegt."""
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def overlaps(self, other: "BoundingBox") -> bool:
        """Prüft ob sich zwei Begrenzungsrahmen überlappen."""
        return not (
            self.x1 < other.x0
            or other.x1 < self.x0
            or self.y1 < other.y0
            or other.y1 < self.y0
        )

    def overlap_ratio(self, other: "BoundingBox") -> float:
        """Berechnet das Überlappungsverhältnis (IoU-ähnlich)."""
        if not self.overlaps(other):
            return 0.0

        # Schnittfläche
        x_overlap = max(0, min(self.x1, other.x1) - max(self.x0, other.x0))
        y_overlap = max(0, min(self.y1, other.y1) - max(self.y0, other.y0))
        intersection = x_overlap * y_overlap

        # Vereinigungsfläche
        union = self.area + other.area - intersection

        return intersection / union if union > 0 else 0.0

    def to_dict(self) -> Dict[str, float]:
        """Konvertiert zu Dictionary."""
        return {
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_list(cls, coords: List[float]) -> "BoundingBox":
        """Erstellt BoundingBox aus Liste [x0, y0, x1, y1]."""
        if len(coords) < 4:
            raise ValueError(f"Benötigt mindestens 4 Koordinaten, erhalten: {len(coords)}")
        return cls(x0=coords[0], y0=coords[1], x1=coords[2], y1=coords[3])


@dataclass
class TableCell:
    """Einzelne Tabellenzelle mit Inhalt und Position."""

    row: int
    col: int
    text: str = ""
    row_span: int = 1
    col_span: int = 1
    bbox: Optional[BoundingBox] = None
    is_header: bool = False
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "row": self.row,
            "col": self.col,
            "text": self.text,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "is_header": self.is_header,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict() if self.bbox else None,
        }


@dataclass
class TableStructure:
    """Komplette Tabellenstruktur von Docling."""

    num_rows: int
    num_cols: int
    cells: List[TableCell] = field(default_factory=list)
    has_header: bool = False
    bbox: Optional[BoundingBox] = None
    caption: Optional[str] = None
    confidence: float = 0.0

    def get_cell(self, row: int, col: int) -> Optional[TableCell]:
        """Holt eine Zelle nach Position."""
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell
        return None

    def get_row(self, row: int) -> List[TableCell]:
        """Holt alle Zellen einer Zeile."""
        return sorted(
            [cell for cell in self.cells if cell.row == row],
            key=lambda c: c.col
        )

    def get_column(self, col: int) -> List[TableCell]:
        """Holt alle Zellen einer Spalte."""
        return sorted(
            [cell for cell in self.cells if cell.col == col],
            key=lambda c: c.row
        )

    def to_grid(self) -> List[List[str]]:
        """Konvertiert zu 2D-Grid (nur Text)."""
        grid = [["" for _ in range(self.num_cols)] for _ in range(self.num_rows)]
        for cell in self.cells:
            if 0 <= cell.row < self.num_rows and 0 <= cell.col < self.num_cols:
                grid[cell.row][cell.col] = cell.text
        return grid

    def to_markdown(self) -> str:
        """Konvertiert Tabelle zu Markdown-Format."""
        if not self.cells or self.num_rows == 0 or self.num_cols == 0:
            return ""

        grid = self.to_grid()
        lines = []

        for row_idx, row in enumerate(grid):
            line = "| " + " | ".join(cell or "" for cell in row) + " |"
            lines.append(line)

            # Separator nach Header-Zeile
            if row_idx == 0 and self.has_header:
                separator = "| " + " | ".join(["---"] * self.num_cols) + " |"
                lines.append(separator)

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "num_rows": self.num_rows,
            "num_cols": self.num_cols,
            "has_header": self.has_header,
            "caption": self.caption,
            "confidence": self.confidence,
            "cells": [cell.to_dict() for cell in self.cells],
            "grid": self.to_grid(),
            "markdown": self.to_markdown(),
            "bbox": self.bbox.to_dict() if self.bbox else None,
        }


@dataclass
class LayoutElement:
    """Einzelnes Layout-Element (Absatz, Tabelle, Bild, etc.)."""

    element_type: LayoutElementType
    bbox: BoundingBox
    reading_order: int
    page_number: int
    text: str = ""
    confidence: float = 0.0
    table: Optional[TableStructure] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_text(self) -> bool:
        """Prüft ob Element Textinhalt hat."""
        return self.element_type in [
            LayoutElementType.TEXT,
            LayoutElementType.HEADING,
            LayoutElementType.LIST,
            LayoutElementType.CAPTION,
            LayoutElementType.FOOTNOTE,
        ]

    @property
    def is_structural(self) -> bool:
        """Prüft ob Element strukturell ist (Header/Footer)."""
        return self.element_type in [
            LayoutElementType.HEADER,
            LayoutElementType.FOOTER,
            LayoutElementType.PAGE_NUMBER,
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        result = {
            "element_type": self.element_type.value,
            "bbox": self.bbox.to_dict(),
            "reading_order": self.reading_order,
            "page_number": self.page_number,
            "text": self.text,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

        if self.table:
            result["table"] = self.table.to_dict()

        return result


@dataclass
class PageLayout:
    """Layout-Information für eine einzelne Seite."""

    page_number: int
    width: float
    height: float
    elements: List[LayoutElement] = field(default_factory=list)
    num_columns: int = 1
    has_header: bool = False
    has_footer: bool = False
    rotation: float = 0.0  # Grad

    @property
    def text_elements(self) -> List[LayoutElement]:
        """Alle Text-Elemente der Seite."""
        return [e for e in self.elements if e.is_text]

    @property
    def tables(self) -> List[LayoutElement]:
        """Alle Tabellen-Elemente der Seite."""
        return [e for e in self.elements if e.element_type == LayoutElementType.TABLE]

    @property
    def figures(self) -> List[LayoutElement]:
        """Alle Bild-Elemente der Seite."""
        return [e for e in self.elements if e.element_type == LayoutElementType.FIGURE]

    def get_elements_by_type(self, element_type: LayoutElementType) -> List[LayoutElement]:
        """Holt alle Elemente eines bestimmten Typs."""
        return [e for e in self.elements if e.element_type == element_type]

    def get_elements_in_reading_order(self) -> List[LayoutElement]:
        """Holt Elemente in Lesereihenfolge sortiert."""
        return sorted(self.elements, key=lambda e: e.reading_order)

    def get_full_text(self, include_tables: bool = True) -> str:
        """Extrahiert den kompletten Text der Seite in Lesereihenfolge."""
        text_parts = []

        for element in self.get_elements_in_reading_order():
            if element.is_text and element.text:
                text_parts.append(element.text)
            elif element.element_type == LayoutElementType.TABLE and include_tables:
                if element.table:
                    text_parts.append(element.table.to_markdown())

        return "\n\n".join(text_parts)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "num_columns": self.num_columns,
            "has_header": self.has_header,
            "has_footer": self.has_footer,
            "rotation": self.rotation,
            "element_count": len(self.elements),
            "table_count": len(self.tables),
            "figure_count": len(self.figures),
            "elements": [e.to_dict() for e in self.elements],
        }


@dataclass
class DocumentLayout:
    """Komplette Dokumentstruktur."""

    pages: List[PageLayout] = field(default_factory=list)
    total_elements: int = 0
    table_count: int = 0
    figure_count: int = 0
    reading_order_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        """Anzahl der Seiten."""
        return len(self.pages)

    @property
    def has_tables(self) -> bool:
        """Prüft ob das Dokument Tabellen enthält."""
        return self.table_count > 0

    @property
    def has_figures(self) -> bool:
        """Prüft ob das Dokument Bilder enthält."""
        return self.figure_count > 0

    @property
    def has_multi_column_pages(self) -> bool:
        """Prüft ob das Dokument mehrspaltigen Seiten hat."""
        return any(page.num_columns > 1 for page in self.pages)

    @property
    def multi_column_page_count(self) -> int:
        """Anzahl der mehrspaltigen Seiten."""
        return sum(1 for page in self.pages if page.num_columns > 1)

    def get_all_tables(self) -> List[TableStructure]:
        """Holt alle Tabellen aus dem Dokument."""
        tables = []
        for page in self.pages:
            for element in page.tables:
                if element.table:
                    tables.append(element.table)
        return tables

    def get_full_text(self, include_tables: bool = True) -> str:
        """Extrahiert den kompletten Text des Dokuments."""
        page_texts = []
        for page in self.pages:
            page_text = page.get_full_text(include_tables=include_tables)
            if page_text:
                page_texts.append(page_text)
        return "\n\n--- Seitenumbruch ---\n\n".join(page_texts)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "page_count": self.page_count,
            "total_elements": self.total_elements,
            "table_count": self.table_count,
            "figure_count": self.figure_count,
            "reading_order_valid": self.reading_order_valid,
            "has_multi_column_pages": self.has_multi_column_pages,
            "multi_column_page_count": self.multi_column_page_count,
            "metadata": self.metadata,
            "pages": [page.to_dict() for page in self.pages],
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """Konvertiert zu kurzem Zusammenfassungs-Dictionary (ohne Elemente)."""
        return {
            "page_count": self.page_count,
            "total_elements": self.total_elements,
            "table_count": self.table_count,
            "figure_count": self.figure_count,
            "reading_order_valid": self.reading_order_valid,
            "has_multi_column_pages": self.has_multi_column_pages,
            "multi_column_page_count": self.multi_column_page_count,
        }
