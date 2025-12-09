"""Docling Layout Analyzer - Dokumentstruktur-Extraktion.

Verwendet Docling's DocumentConverter um Dokumentstruktur zu analysieren:
- Tabellenstrukturen mit Zellen-Level-Daten
- Bilder/Figuren-Erkennung
- Abschnittshierarchie
- Lesereihenfolge-Bestimmung
- Mehrspalten-Layout-Erkennung
- Header/Footer-Identifikation

CPU-only Operation (0 VRAM Anforderung).
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import structlog

from app.agents.ocr.models.layout_models import (
    BoundingBox,
    DocumentLayout,
    LayoutElement,
    LayoutElementType,
    PageLayout,
    TableCell,
    TableStructure,
)

logger = structlog.get_logger(__name__)


class DoclingLayoutAnalyzer:
    """CPU-only Dokument-Layout-Analyzer mit Docling.

    Extrahiert:
    - Dokumentstruktur (Abschnitte, Absätze)
    - Tabellenstrukturen mit Zellen-Level-Daten
    - Bild-Bereiche
    - Lesereihenfolge
    - Mehrspalten-Erkennung

    Singleton-Pattern für Speichereffizienz.
    """

    _instance: Optional["DoclingLayoutAnalyzer"] = None
    _lock: Optional[asyncio.Lock] = None

    def __init__(self) -> None:
        """Initialisiere Docling Analyzer."""
        self._converter = None
        self._is_loaded = False

        # Initialisiere Class-Level Lock
        if DoclingLayoutAnalyzer._lock is None:
            DoclingLayoutAnalyzer._lock = asyncio.Lock()

        logger.info("DoclingLayoutAnalyzer initialisiert")

    @classmethod
    def get_instance(cls) -> "DoclingLayoutAnalyzer":
        """Singleton-Pattern für Speichereffizienz."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Setzt Singleton zurück (für Tests)."""
        cls._instance = None
        cls._lock = None

    async def load_converter(self) -> None:
        """Lade Docling DocumentConverter (Lazy Loading)."""
        async with self._lock:
            if self._is_loaded:
                return

            logger.info("Lade Docling DocumentConverter...")

            # Im Executor ausführen da Docling-Laden CPU-intensiv ist
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_converter_sync)

            self._is_loaded = True
            logger.info("Docling DocumentConverter geladen")

    def _load_converter_sync(self) -> None:
        """Synchrones Converter-Laden."""
        try:
            from docling.document_converter import (
                DocumentConverter,
                ImageFormatOption,
                PdfFormatOption,
            )
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat

            # Pipeline-Options für Layout-Struktur-Extraktion
            # WICHTIG: do_ocr=False damit Docling nicht EasyOCR auf GPU lädt
            # (Surya macht das OCR separat und effizienter)
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False  # Surya handles OCR
            pipeline_options.do_table_structure = True

            # FormatOptions mit unseren Pipeline-Options erstellen
            pdf_format = PdfFormatOption(pipeline_options=pipeline_options)
            image_format = ImageFormatOption(pipeline_options=pipeline_options)

            self._converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF, InputFormat.IMAGE],
                format_options={
                    InputFormat.PDF: pdf_format,
                    InputFormat.IMAGE: image_format,
                },
            )

        except ImportError as e:
            logger.error("Docling Import fehlgeschlagen", error=str(e))
            raise ImportError(
                "Docling nicht installiert. Bitte 'pip install docling' ausführen."
            ) from e

    async def analyze(
        self,
        document_path: Union[str, Path],
        options: Optional[Dict[str, Any]] = None,
    ) -> DocumentLayout:
        """Analysiere Dokument-Layout.

        Args:
            document_path: Pfad zu PDF oder Bild-Datei
            options: Optionale Analyse-Optionen
                - extract_tables: bool (default: True)
                - extract_figures: bool (default: True)
                - detect_columns: bool (default: True)

        Returns:
            DocumentLayout mit Struktur-Informationen

        Raises:
            FileNotFoundError: Wenn Dokument nicht existiert
            RuntimeError: Wenn Analyse fehlschlägt
        """
        options = options or {}
        document_path = Path(document_path)

        if not document_path.exists():
            raise FileNotFoundError(f"Dokument nicht gefunden: {document_path}")

        await self.load_converter()

        logger.info("Analysiere Dokument-Layout", path=str(document_path))

        try:
            # Docling-Konvertierung im Executor ausführen
            loop = asyncio.get_event_loop()
            docling_result = await loop.run_in_executor(
                None, self._convert_document, str(document_path)
            )

            # Docling-Ergebnis in unsere Layout-Modelle parsen
            layout = self._parse_docling_result(docling_result, options)

            logger.info(
                "Layout-Analyse abgeschlossen",
                pages=len(layout.pages),
                tables=layout.table_count,
                figures=layout.figure_count,
            )

            return layout

        except Exception as e:
            logger.error("Layout-Analyse fehlgeschlagen", error=str(e), exc_info=True)
            # Minimales Layout bei Fehler zurückgeben
            return DocumentLayout(pages=[], reading_order_valid=False)

    def _convert_document(self, document_path: str) -> Any:
        """Synchrone Docling-Konvertierung."""
        result = self._converter.convert(document_path)
        return result

    def _parse_docling_result(
        self, docling_result: Any, options: Dict[str, Any]
    ) -> DocumentLayout:
        """Parse Docling-Ergebnis in DocumentLayout-Struktur."""
        pages: List[PageLayout] = []
        table_count = 0
        figure_count = 0

        # Dokument-Struktur zugreifen
        document = docling_result.document

        # Seiten-Informationen sammeln
        page_info = self._get_page_info(document)

        # Elemente pro Seite gruppieren
        page_elements: Dict[int, List[LayoutElement]] = {
            i: [] for i in range(len(page_info))
        }

        # Elemente verarbeiten
        reading_order_counter = 0
        for item in document.iterate_items():
            # Seite bestimmen
            page_idx = self._get_item_page(item)
            if page_idx is None or page_idx >= len(page_info):
                continue

            # Element erstellen
            element = self._create_layout_element(
                item, page_idx + 1, reading_order_counter, options
            )

            if element:
                page_elements[page_idx].append(element)
                reading_order_counter += 1

                if element.element_type == LayoutElementType.TABLE:
                    table_count += 1
                elif element.element_type == LayoutElementType.FIGURE:
                    figure_count += 1

        # PageLayout-Objekte erstellen
        for page_idx, info in enumerate(page_info):
            elements = page_elements.get(page_idx, [])
            # Nach Lesereihenfolge sortieren
            elements.sort(key=lambda e: e.reading_order)

            # Spalten erkennen
            num_columns = self._detect_columns(elements)

            pages.append(
                PageLayout(
                    page_number=page_idx + 1,
                    width=info.get("width", 612),
                    height=info.get("height", 792),
                    elements=elements,
                    num_columns=num_columns,
                    has_header=any(
                        e.element_type == LayoutElementType.HEADER for e in elements
                    ),
                    has_footer=any(
                        e.element_type == LayoutElementType.FOOTER for e in elements
                    ),
                )
            )

        return DocumentLayout(
            pages=pages,
            total_elements=sum(len(p.elements) for p in pages),
            table_count=table_count,
            figure_count=figure_count,
            reading_order_valid=True,
        )

    def _get_page_info(self, document: Any) -> List[Dict[str, Any]]:
        """Extrahiere Seiten-Informationen aus Docling-Dokument."""
        page_info = []

        if hasattr(document, "pages") and document.pages:
            for page in document.pages:
                info = {"width": 612, "height": 792}  # Default US Letter
                if hasattr(page, "size"):
                    if hasattr(page.size, "width"):
                        info["width"] = page.size.width
                    if hasattr(page.size, "height"):
                        info["height"] = page.size.height
                page_info.append(info)
        else:
            # Fallback: Eine Seite annehmen
            page_info.append({"width": 612, "height": 792})

        return page_info

    def _get_item_page(self, item: Any) -> Optional[int]:
        """Bestimme Seitennummer eines Elements."""
        if hasattr(item, "prov") and item.prov:
            for prov in item.prov:
                if hasattr(prov, "page_no"):
                    return prov.page_no - 1  # 0-indexiert
        return 0  # Default erste Seite

    def _create_layout_element(
        self,
        item: Any,
        page_number: int,
        reading_order: int,
        options: Dict[str, Any],
    ) -> Optional[LayoutElement]:
        """Erstelle LayoutElement aus Docling-Item."""
        # Element-Typ bestimmen
        element_type = self._get_element_type(item)

        # Nach Optionen filtern
        if (
            element_type == LayoutElementType.TABLE
            and not options.get("extract_tables", True)
        ):
            return None
        if (
            element_type == LayoutElementType.FIGURE
            and not options.get("extract_figures", True)
        ):
            return None

        # Bounding Box extrahieren
        bbox = self._get_bbox(item)
        if bbox is None:
            # Fallback-BBox erstellen
            bbox = BoundingBox(x0=0, y0=0, x1=100, y1=100)

        # Element erstellen
        element = LayoutElement(
            element_type=element_type,
            bbox=bbox,
            reading_order=reading_order,
            page_number=page_number,
            text=self._get_text(item),
            confidence=self._get_confidence(item),
        )

        # Tabellenstruktur extrahieren falls Tabelle
        if element_type == LayoutElementType.TABLE:
            element.table = self._extract_table_structure(item)

        return element

    def _get_element_type(self, item: Any) -> LayoutElementType:
        """Mappe Docling-Item-Typ auf LayoutElementType."""
        type_name = type(item).__name__.lower()

        mapping = {
            "tableitem": LayoutElementType.TABLE,
            "figureitem": LayoutElementType.FIGURE,
            "textitem": LayoutElementType.TEXT,
            "sectionheaderitem": LayoutElementType.HEADING,
            "listitem": LayoutElementType.LIST,
            "captionitem": LayoutElementType.CAPTION,
            "footnoteitem": LayoutElementType.FOOTNOTE,
            "formulaitem": LayoutElementType.FORMULA,
            "codeitem": LayoutElementType.CODE,
        }

        # Label-basierte Erkennung als Fallback
        if hasattr(item, "label"):
            label = str(item.label).lower()
            if "header" in label:
                return LayoutElementType.HEADER
            if "footer" in label:
                return LayoutElementType.FOOTER
            if "page" in label and "number" in label:
                return LayoutElementType.PAGE_NUMBER

        return mapping.get(type_name, LayoutElementType.TEXT)

    def _get_bbox(self, item: Any) -> Optional[BoundingBox]:
        """Extrahiere Bounding Box aus Docling-Item."""
        if not hasattr(item, "prov") or not item.prov:
            return None

        for prov in item.prov:
            if hasattr(prov, "bbox") and prov.bbox:
                b = prov.bbox
                # Docling verwendet l, t, r, b (left, top, right, bottom)
                return BoundingBox(
                    x0=getattr(b, "l", 0),
                    y0=getattr(b, "t", 0),
                    x1=getattr(b, "r", 100),
                    y1=getattr(b, "b", 100),
                )
        return None

    def _get_text(self, item: Any) -> str:
        """Extrahiere Text aus Docling-Item."""
        if hasattr(item, "text"):
            return str(item.text)
        if hasattr(item, "export_to_plaintext"):
            return item.export_to_plaintext()
        return ""

    def _get_confidence(self, item: Any) -> float:
        """Extrahiere Confidence aus Docling-Item."""
        if hasattr(item, "confidence"):
            return float(item.confidence)
        return 0.9  # Default Confidence

    def _extract_table_structure(self, item: Any) -> Optional[TableStructure]:
        """Extrahiere detaillierte Tabellenstruktur aus Docling TableItem."""
        if not hasattr(item, "data") or not item.data:
            return None

        try:
            data = item.data
            cells: List[TableCell] = []

            # Grid-basierte Extraktion
            if hasattr(data, "grid") and data.grid:
                for row_idx, row in enumerate(data.grid):
                    for col_idx, cell_data in enumerate(row):
                        cell_text = ""
                        if hasattr(cell_data, "text"):
                            cell_text = str(cell_data.text)
                        elif cell_data is not None:
                            cell_text = str(cell_data)

                        cell = TableCell(
                            row=row_idx,
                            col=col_idx,
                            text=cell_text,
                            row_span=getattr(cell_data, "row_span", 1)
                            if cell_data
                            else 1,
                            col_span=getattr(cell_data, "col_span", 1)
                            if cell_data
                            else 1,
                            is_header=row_idx == 0,
                        )
                        cells.append(cell)

                num_rows = len(data.grid)
                num_cols = len(data.grid[0]) if data.grid else 0

            # Alternative: table_cells Attribut
            elif hasattr(data, "table_cells") and data.table_cells:
                max_row = 0
                max_col = 0
                for tc in data.table_cells:
                    row = getattr(tc, "row_index", 0)
                    col = getattr(tc, "col_index", 0)
                    max_row = max(max_row, row)
                    max_col = max(max_col, col)

                    cell = TableCell(
                        row=row,
                        col=col,
                        text=getattr(tc, "text", ""),
                        row_span=getattr(tc, "row_span", 1),
                        col_span=getattr(tc, "col_span", 1),
                        is_header=getattr(tc, "is_header", row == 0),
                    )
                    cells.append(cell)

                num_rows = max_row + 1
                num_cols = max_col + 1
            else:
                return None

            return TableStructure(
                num_rows=num_rows,
                num_cols=num_cols,
                cells=cells,
                has_header=True,  # Annahme: Erste Zeile ist Header
                bbox=self._get_bbox(item),
            )

        except Exception as e:
            logger.warning("Tabellen-Extraktion fehlgeschlagen", error=str(e))
            return None

    def _detect_columns(self, elements: List[LayoutElement]) -> int:
        """Erkenne Anzahl der Spalten aus Element-Positionen."""
        if not elements:
            return 1

        # Nur Text-Elemente für Spalten-Erkennung
        text_elements = [e for e in elements if e.is_text]
        if len(text_elements) < 3:
            return 1

        # X-Koordinaten analysieren
        x_positions = sorted(set(e.bbox.x0 for e in text_elements))

        if len(x_positions) < 2:
            return 1

        # Nach deutlichen Lücken suchen (Spalten-Trennung)
        gaps = [
            x_positions[i + 1] - x_positions[i] for i in range(len(x_positions) - 1)
        ]
        if not gaps:
            return 1

        avg_gap = sum(gaps) / len(gaps)

        # Große Lücken = Spalten-Trennung
        large_gaps = [g for g in gaps if g > avg_gap * 2]

        return len(large_gaps) + 1

    def get_status(self) -> Dict[str, Any]:
        """Hole Analyzer-Status."""
        return {
            "name": "docling_layout_analyzer",
            "is_loaded": self._is_loaded,
            "capabilities": [
                "table_extraction",
                "figure_detection",
                "reading_order",
                "multi_column",
                "header_footer",
            ],
        }

    async def cleanup(self) -> None:
        """Ressourcen freigeben."""
        self._converter = None
        self._is_loaded = False
        logger.info("DoclingLayoutAnalyzer Cleanup abgeschlossen")
