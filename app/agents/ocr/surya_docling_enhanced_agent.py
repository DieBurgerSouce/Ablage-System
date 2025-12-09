"""Enhanced Surya-Docling OCR Agent mit vollständiger Layout-Integration.

Pipeline:
1. Docling: Dokumentstruktur-Analyse (Tabellen, Layout, Lesereihenfolge)
2. Surya: OCR-Textextraktion
3. Merger: Struktur mit Text kombinieren für reichhaltiges Ergebnis

CPU-only Operation (0 VRAM Anforderung).
Deutsche Dokument-Optimierung (Rechnungen 42%, Verträge 17% des Datensatzes).
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from PIL import Image
import pypdfium2 as pdfium

from app.agents.base import OCRAgent, OCRResult
from app.agents.ocr.docling_layout_analyzer import DoclingLayoutAnalyzer
from app.agents.ocr.models.layout_models import (
    DocumentLayout,
    LayoutElement,
    LayoutElementType,
    PageLayout,
    TableStructure,
    BoundingBox,
)

logger = structlog.get_logger(__name__)


class SuryaDoclingEnhancedAgent(OCRAgent):
    """Enhanced Surya+Docling Agent mit vollständiger Layout-Integration.

    Features:
    - Vollständige Docling Layout-Analyse (Tabellen, Figuren, Abschnitte)
    - Surya OCR mit deutscher Optimierung
    - Lesereihenfolge-Erhaltung für mehrspaltige Dokumente
    - Tabellenstruktur-Extraktion mit Zellen-Level-Daten
    - CPU-only Operation (0 VRAM)

    Konfigurationsoptionen:
    - enable_layout_analysis: bool (default: True)
    - extract_tables: bool (default: True)
    - preserve_reading_order: bool (default: True)
    - fallback_on_layout_error: bool (default: True)
    """

    # Class-Level Lock für Model-Loading
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialisiere Enhanced Agent.

        Args:
            config: Optionale Konfiguration mit Schlüsseln:
                - enable_layout_analysis: Layout-Analyse aktivieren
                - extract_tables: Tabellen extrahieren
                - preserve_reading_order: Lesereihenfolge bewahren
                - fallback_on_layout_error: Bei Layout-Fehler fortfahren
        """
        super().__init__(
            name="surya_docling_enhanced_agent", gpu_required=False, vram_gb=0
        )

        # Class-Level Lock initialisieren
        if SuryaDoclingEnhancedAgent._model_lock is None:
            SuryaDoclingEnhancedAgent._model_lock = asyncio.Lock()

        # Konfiguration
        self._config = config or {}
        self._enable_layout = self._config.get("enable_layout_analysis", True)
        self._extract_tables = self._config.get("extract_tables", True)
        self._preserve_reading_order = self._config.get("preserve_reading_order", True)
        self._fallback_on_error = self._config.get("fallback_on_layout_error", True)

        # Komponenten
        self._layout_analyzer: Optional[DoclingLayoutAnalyzer] = None
        self._surya_models_loaded = False

        # Surya-Modelle (lazy loaded)
        self._det_predictor = None
        self._rec_predictor = None
        self._foundation_predictor = None
        self._task_name = None

        # Deutsche Sprache
        self.default_language = "de"

        logger.info(
            "SuryaDoclingEnhancedAgent initialisiert",
            layout_enabled=self._enable_layout,
            table_extraction=self._extract_tables,
        )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verarbeite Dokument mit Enhanced Docling+Surya Pipeline.

        Args:
            input_data: Dictionary mit:
                - image_path: Pfad zu Bild oder PDF
                - language: Optionaler Sprach-Hint (default: "de")
                - options: Optionale Verarbeitungsoptionen

        Returns:
            Strukturiertes OCR-Ergebnis mit Layout-Informationen
        """
        start_time = time.perf_counter()

        try:
            # Parameter extrahieren
            image_path = input_data.get("image_path")
            if not image_path:
                raise ValueError("image_path ist erforderlich")

            language = input_data.get("language", self.default_language)
            options = input_data.get("options", {})

            document_path = Path(image_path)

            logger.info(
                "Enhanced OCR gestartet",
                path=str(document_path),
                language=language,
                layout_enabled=self._enable_layout,
            )

            # Komponenten initialisieren
            await self._ensure_initialized()

            # Phase 1: Layout-Analyse (wenn aktiviert)
            layout: Optional[DocumentLayout] = None
            if self._enable_layout:
                try:
                    layout = await self._analyze_layout(document_path, options)
                except Exception as e:
                    logger.warning(
                        "Layout-Analyse fehlgeschlagen, fahre nur mit OCR fort",
                        error=str(e),
                    )
                    if not self._fallback_on_error:
                        raise

            # Phase 2: Surya OCR
            images = await self._load_images(document_path)
            ocr_results = await self._run_surya_ocr(images, language)

            # Phase 3: Ergebnisse zusammenführen
            merged_result = self._merge_results(ocr_results, layout)

            # Verarbeitungszeit berechnen
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Standardisiertes Ergebnis erstellen
            result = self.create_success_result(
                text=merged_result["text"],
                confidence=merged_result["confidence"],
                processing_time_ms=processing_time_ms,
                page_count=len(images),
                language=language,
                layout=merged_result.get("layout_summary"),
                pages=merged_result.get("pages"),
                has_umlauts=self._check_umlauts(merged_result["text"]),
            )

            # Enhanced Metadata hinzufügen
            result_dict = result.to_dict()
            result_dict["tables"] = merged_result.get("tables", [])
            result_dict["reading_order_applied"] = merged_result.get(
                "reading_order_applied", False
            )
            result_dict["layout_analysis_used"] = layout is not None

            logger.info(
                "Enhanced OCR abgeschlossen",
                chars=len(merged_result["text"]),
                tables=len(merged_result.get("tables", [])),
                processing_ms=processing_time_ms,
            )

            return result_dict

        except Exception as e:
            logger.error("Enhanced OCR fehlgeschlagen", error=str(e), exc_info=True)
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            result = self.create_error_result(
                error=str(e),
                error_code="SURYA_DOCLING_ENHANCED_ERROR",
                processing_time_ms=processing_time_ms,
            )
            return result.to_dict()

    async def _ensure_initialized(self) -> None:
        """Stelle sicher dass alle Komponenten initialisiert sind."""
        async with self._model_lock:
            # Docling Analyzer initialisieren
            if self._enable_layout and self._layout_analyzer is None:
                self._layout_analyzer = DoclingLayoutAnalyzer.get_instance()

            # Surya-Modelle initialisieren
            if not self._surya_models_loaded:
                await self._load_surya_models()

    async def _load_surya_models(self) -> None:
        """Lade Surya OCR-Modelle."""
        if self._surya_models_loaded:
            return

        logger.info("Lade Surya 0.17.0 Modelle...")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_surya_models_sync)

        self._surya_models_loaded = True
        logger.info("Surya-Modelle geladen (CPU-Modus)")

    def _load_surya_models_sync(self) -> None:
        """Synchrones Surya-Model-Laden."""
        from surya.detection import DetectionPredictor
        from surya.recognition import RecognitionPredictor
        from surya.foundation import FoundationPredictor
        from surya.common.surya.schema import TaskNames

        self._task_name = TaskNames.ocr_with_boxes
        self._foundation_predictor = FoundationPredictor()
        self._det_predictor = DetectionPredictor()
        self._rec_predictor = RecognitionPredictor(self._foundation_predictor)

    async def _analyze_layout(
        self, document_path: Path, options: Dict[str, Any]
    ) -> DocumentLayout:
        """Führe Docling Layout-Analyse aus."""
        analysis_options = {
            "extract_tables": self._extract_tables,
            "extract_figures": options.get("extract_figures", True),
            "detect_columns": True,
        }

        return await self._layout_analyzer.analyze(document_path, analysis_options)

    async def _load_images(self, document_path: Path) -> List[Image.Image]:
        """Lade Dokument als Bilder."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._load_images_sync, document_path)

    def _load_images_sync(self, document_path: Path) -> List[Image.Image]:
        """Synchrones Bild-Laden."""
        images = []

        if document_path.suffix.lower() == ".pdf":
            pdf = pdfium.PdfDocument(str(document_path))
            for page_num in range(len(pdf)):
                page = pdf[page_num]
                pil_image = page.render(scale=300 / 72).to_pil()
                images.append(pil_image)
            pdf.close()
        else:
            image = Image.open(document_path)
            if image.mode != "RGB":
                image = image.convert("RGB")
            images.append(image)

        return images

    async def _run_surya_ocr(
        self, images: List[Image.Image], language: str
    ) -> List[Dict[str, Any]]:
        """Führe Surya OCR auf Bildern aus."""
        results = []

        for idx, image in enumerate(images):
            loop = asyncio.get_event_loop()
            page_result = await loop.run_in_executor(
                None, self._process_single_image, image, language
            )
            page_result["page_number"] = idx + 1
            results.append(page_result)

        return results

    def _process_single_image(
        self, image: Image.Image, language: str
    ) -> Dict[str, Any]:
        """Verarbeite einzelnes Bild mit Surya."""
        predictions = self._rec_predictor(
            [image],
            task_names=[self._task_name],
            det_predictor=self._det_predictor,
        )

        text_blocks = []
        all_text = []

        if predictions and len(predictions) > 0:
            pred = predictions[0]

            if hasattr(pred, "text_lines"):
                for line in pred.text_lines:
                    text = line.text if hasattr(line, "text") else str(line)
                    confidence = line.confidence if hasattr(line, "confidence") else 0.0
                    bbox = line.bbox if hasattr(line, "bbox") else []

                    if text and text.strip():
                        text_blocks.append(
                            {
                                "text": text,
                                "confidence": float(confidence),
                                "bbox": list(bbox) if bbox else [],
                            }
                        )
                        all_text.append(text)

        return {
            "text_blocks": text_blocks,
            "full_text": "\n".join(all_text),
            "confidence": self._calculate_page_confidence(text_blocks),
        }

    def _calculate_page_confidence(self, text_blocks: List[Dict[str, Any]]) -> float:
        """Berechne durchschnittliche Confidence für Seite."""
        if not text_blocks:
            return 0.0
        confidences = [b["confidence"] for b in text_blocks]
        return sum(confidences) / len(confidences)

    def _merge_results(
        self,
        ocr_results: List[Dict[str, Any]],
        layout: Optional[DocumentLayout],
    ) -> Dict[str, Any]:
        """Führe Surya OCR-Ergebnisse mit Docling-Layout zusammen."""
        if not layout or not layout.pages:
            # Kein Layout - Plain OCR-Ergebnisse zurückgeben
            return self._create_plain_result(ocr_results)

        # Mit Layout zusammenführen
        merged_pages = []
        all_text_parts = []
        all_tables = []
        total_confidence = 0.0

        # Sicherstellen dass wir genug Seiten haben
        max_pages = max(len(ocr_results), len(layout.pages))

        for page_idx in range(max_pages):
            ocr_page = (
                ocr_results[page_idx] if page_idx < len(ocr_results) else None
            )
            layout_page = layout.pages[page_idx] if page_idx < len(layout.pages) else None

            if ocr_page is None:
                continue

            # Lesereihenfolge aus Layout anwenden
            if self._preserve_reading_order and layout_page:
                ordered_text = self._apply_reading_order(
                    ocr_page["text_blocks"], layout_page
                )
            else:
                ordered_text = ocr_page["full_text"]

            all_text_parts.append(ordered_text)
            total_confidence += ocr_page["confidence"]

            # Tabellen extrahieren
            page_tables = []
            if layout_page:
                page_tables = self._extract_page_tables(layout_page, ocr_page)
                all_tables.extend(page_tables)

            # Merged Page Data erstellen
            merged_pages.append(
                {
                    "page_number": page_idx + 1,
                    "text": ordered_text,
                    "confidence": ocr_page["confidence"],
                    "num_columns": layout_page.num_columns if layout_page else 1,
                    "has_tables": len(page_tables) > 0,
                    "table_count": len(page_tables),
                    "text_blocks": ocr_page["text_blocks"],
                }
            )

        # Seiten kombinieren
        full_text = "\n\n--- Seitenumbruch ---\n\n".join(all_text_parts)
        avg_confidence = (
            total_confidence / len(ocr_results) if ocr_results else 0.0
        )

        return {
            "text": full_text,
            "confidence": avg_confidence,
            "pages": merged_pages,
            "tables": all_tables,
            "reading_order_applied": self._preserve_reading_order,
            "layout_summary": layout.to_summary_dict() if layout else None,
        }

    def _create_plain_result(
        self, ocr_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Erstelle Ergebnis ohne Layout-Analyse."""
        all_text = []
        total_confidence = 0.0

        for page in ocr_results:
            all_text.append(page["full_text"])
            total_confidence += page["confidence"]

        return {
            "text": "\n\n--- Seitenumbruch ---\n\n".join(all_text),
            "confidence": total_confidence / len(ocr_results) if ocr_results else 0.0,
            "pages": ocr_results,
            "tables": [],
            "reading_order_applied": False,
            "layout_summary": None,
        }

    def _apply_reading_order(
        self, text_blocks: List[Dict[str, Any]], page_layout: PageLayout
    ) -> str:
        """Wende Docling-Lesereihenfolge auf OCR-Text-Blöcke an."""
        if not page_layout.elements or not text_blocks:
            return "\n".join(b["text"] for b in text_blocks)

        # OCR-Blöcke nach Positionen zu Layout-Elementen zuordnen
        ordered_texts = []

        # Layout-Elemente nach Lesereihenfolge sortieren
        sorted_elements = page_layout.get_elements_in_reading_order()

        for element in sorted_elements:
            if element.is_text:
                # Passenden OCR-Text nach BBox-Überlappung finden
                matching_text = self._find_matching_text(element, text_blocks)
                if matching_text:
                    ordered_texts.append(matching_text)
            elif element.element_type == LayoutElementType.TABLE and element.table:
                # Tabelle als Markdown einfügen
                ordered_texts.append(element.table.to_markdown())

        # Unzugeordnete Blöcke hinzufügen
        matched_texts = set(ordered_texts)
        for block in text_blocks:
            if block["text"] not in matched_texts:
                ordered_texts.append(block["text"])

        return "\n".join(ordered_texts)

    def _find_matching_text(
        self, element: LayoutElement, text_blocks: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Finde OCR-Text-Block der zum Layout-Element passt."""
        if not element.bbox:
            return None

        best_match = None
        best_overlap = 0.0

        for block in text_blocks:
            if not block.get("bbox") or len(block["bbox"]) < 4:
                continue

            overlap = self._calculate_bbox_overlap(element.bbox, block["bbox"])

            if overlap > best_overlap:
                best_overlap = overlap
                best_match = block["text"]

        return best_match if best_overlap > 0.3 else None

    def _calculate_bbox_overlap(
        self, bbox1: BoundingBox, bbox2: List[float]
    ) -> float:
        """Berechne Überlappungsverhältnis zwischen zwei BBoxes."""
        try:
            x1_min, y1_min = bbox1.x0, bbox1.y0
            x1_max, y1_max = bbox1.x1, bbox1.y1

            x2_min, y2_min = bbox2[0], bbox2[1]
            x2_max, y2_max = bbox2[2], bbox2[3]

            # Schnittfläche berechnen
            x_overlap = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
            y_overlap = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
            intersection = x_overlap * y_overlap

            # Vereinigungsfläche berechnen
            area1 = (x1_max - x1_min) * (y1_max - y1_min)
            area2 = (x2_max - x2_min) * (y2_max - y2_min)
            union = area1 + area2 - intersection

            return intersection / union if union > 0 else 0.0

        except (IndexError, TypeError):
            return 0.0

    def _extract_page_tables(
        self, page_layout: PageLayout, ocr_page: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extrahiere Tabellenstrukturen von Seite."""
        tables = []

        for element in page_layout.tables:
            if element.table:
                table_data = self._serialize_table(element.table, ocr_page)
                tables.append(table_data)

        return tables

    def _serialize_table(
        self, table: TableStructure, ocr_page: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Serialisiere Tabellenstruktur zu Dict."""
        # Grid-Repräsentation erstellen
        grid = [[None for _ in range(table.num_cols)] for _ in range(table.num_rows)]

        for cell in table.cells:
            if 0 <= cell.row < table.num_rows and 0 <= cell.col < table.num_cols:
                # Text aus OCR holen wenn Zell-Text leer
                cell_text = cell.text
                if not cell_text and cell.bbox:
                    cell_text = self._find_text_in_region(
                        cell.bbox, ocr_page["text_blocks"]
                    )

                grid[cell.row][cell.col] = {
                    "text": cell_text,
                    "row_span": cell.row_span,
                    "col_span": cell.col_span,
                    "is_header": cell.is_header,
                }

        return {
            "rows": table.num_rows,
            "cols": table.num_cols,
            "has_header": table.has_header,
            "grid": grid,
            "caption": table.caption,
            "markdown": table.to_markdown(),
        }

    def _find_text_in_region(
        self, bbox: BoundingBox, text_blocks: List[Dict[str, Any]]
    ) -> str:
        """Finde OCR-Text innerhalb eines Bounding-Box-Bereichs."""
        matching_texts = []

        for block in text_blocks:
            if not block.get("bbox") or len(block["bbox"]) < 4:
                continue

            overlap = self._calculate_bbox_overlap(bbox, block["bbox"])
            if overlap > 0.5:
                matching_texts.append(block["text"])

        return " ".join(matching_texts)

    def _check_umlauts(self, text: str) -> bool:
        """Prüfe ob Text deutsche Umlaute enthält."""
        german_chars = ["ä", "ö", "ü", "Ä", "Ö", "Ü", "ß"]
        return any(char in text for char in german_chars)

    async def cleanup(self) -> None:
        """Ressourcen freigeben."""
        self._det_predictor = None
        self._rec_predictor = None
        self._foundation_predictor = None
        self._surya_models_loaded = False

        await super().cleanup()
        logger.info("SuryaDoclingEnhancedAgent Cleanup abgeschlossen")

    def get_status(self) -> Dict[str, Any]:
        """Hole Agent-Status."""
        status = {
            "name": self.name,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "surya_models_loaded": self._surya_models_loaded,
            "layout_analyzer_available": self._layout_analyzer is not None,
            "default_language": self.default_language,
            "config": {
                "layout_analysis_enabled": self._enable_layout,
                "table_extraction_enabled": self._extract_tables,
                "reading_order_preservation": self._preserve_reading_order,
            },
            "status": "ready" if self._surya_models_loaded else "not_loaded",
        }

        if self._layout_analyzer:
            status["layout_analyzer_status"] = self._layout_analyzer.get_status()

        return status
