"""OCR Confidence Service - Extrahiert Wort-Level Confidence-Daten fuer Viewer-Heatmap.

Dieser Service extrahiert Confidence-Daten aus OCR-Ergebnissen und bereitet sie
fuer die Heatmap-Visualisierung im Document Viewer auf.

Die Daten werden aus mehreren Quellen kombiniert:
- document.metadata JSONB (primaer)
- ocr_results.bounding_boxes JSONB
- ocr_results.detected_layout JSONB
- document.ocr_confidence (Fallback fuer Gesamt-Confidence)

Created: 2026-02-08
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, OCRResult, User
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class WordConfidence:
    """Wort-Level Confidence-Daten mit Position."""
    text: str
    confidence: float  # 0.0 - 1.0
    page: int
    x: float  # normalized 0-1
    y: float  # normalized 0-1
    width: float  # normalized 0-1
    height: float  # normalized 0-1


@dataclass
class PageConfidence:
    """Seiten-Level Confidence-Daten."""
    page_number: int
    overall_confidence: float
    words: List[WordConfidence] = field(default_factory=list)
    backend: str = "unknown"


@dataclass
class DocumentConfidenceData:
    """Dokument-Level Confidence-Daten."""
    document_id: str
    total_pages: int
    overall_confidence: float
    pages: List[PageConfidence] = field(default_factory=list)
    backend: str = "unknown"


class OCRConfidenceService:
    """Service zum Extrahieren von OCR-Confidence-Daten."""

    def __init__(self, db: AsyncSession):
        """
        Initialisiere den Service.

        Args:
            db: Async Database Session
        """
        self._db = db

    async def get_confidence_data(
        self,
        document_id: UUID,
        user_id: UUID,
        page_number: Optional[int] = None
    ) -> DocumentConfidenceData:
        """
        Extrahiert Confidence-Daten fuer ein Dokument.

        Args:
            document_id: Dokument-ID
            user_id: Benutzer-ID (fuer Access-Check)
            page_number: Optional spezifische Seitennummer (None = alle Seiten)

        Returns:
            DocumentConfidenceData mit strukturierten Confidence-Daten

        Raises:
            ValueError: Dokument nicht gefunden oder keine Berechtigung
        """
        # Dokument laden mit Access-Check
        query = select(Document).where(Document.id == document_id)
        result = await self._db.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden")

        # Access-Check: User muss Owner sein
        if document.owner_id != user_id:
            raise ValueError("Keine Berechtigung fuer dieses Dokument")

        # Basis-Daten sammeln
        total_pages = document.page_count or 1
        overall_confidence = document.ocr_confidence or 0.0
        backend = document.ocr_backend_used or "unknown"

        # OCR-Ergebnisse laden
        ocr_query = select(OCRResult).where(OCRResult.document_id == document_id)
        if page_number is not None:
            ocr_query = ocr_query.where(OCRResult.page_number == page_number)
        ocr_query = ocr_query.order_by(OCRResult.page_number)

        ocr_results = await self._db.execute(ocr_query)
        ocr_results_list = list(ocr_results.scalars().all())

        logger.info(
            "extracting_confidence_data",
            document_id=str(document_id),
            total_pages=total_pages,
            ocr_results_count=len(ocr_results_list),
            backend=backend
        )

        # Seiten-Daten extrahieren
        pages: List[PageConfidence] = []

        if ocr_results_list:
            # Daten aus OCRResult-Eintraegen extrahieren
            for ocr_result in ocr_results_list:
                page_data = self._extract_page_confidence(
                    ocr_result,
                    backend
                )
                if page_data:
                    pages.append(page_data)
        else:
            # Fallback: Versuche aus document.metadata zu extrahieren
            pages = self._extract_from_document_metadata(
                document,
                page_number,
                backend
            )

        # Wenn keine Seiten-Daten vorhanden, erstelle Fallback
        if not pages:
            pages = self._create_fallback_pages(
                total_pages,
                overall_confidence,
                backend,
                page_number
            )

        # Gesamtconfidence berechnen (Durchschnitt aller Seiten)
        if pages:
            overall_confidence = sum(p.overall_confidence for p in pages) / len(pages)

        return DocumentConfidenceData(
            document_id=str(document_id),
            total_pages=total_pages,
            overall_confidence=round(overall_confidence, 4),
            pages=pages,
            backend=backend
        )

    def _extract_page_confidence(
        self,
        ocr_result: OCRResult,
        backend: str
    ) -> Optional[PageConfidence]:
        """
        Extrahiert Confidence-Daten aus einem OCRResult.

        Args:
            ocr_result: OCRResult-Eintrag
            backend: OCR-Backend Name

        Returns:
            PageConfidence oder None bei Fehler
        """
        try:
            page_num = ocr_result.page_number or 1
            page_confidence = ocr_result.confidence_score or 0.0

            words: List[WordConfidence] = []

            # 1. Versuche aus bounding_boxes zu extrahieren
            if ocr_result.bounding_boxes and isinstance(ocr_result.bounding_boxes, list):
                words = self._extract_words_from_bounding_boxes(
                    ocr_result.bounding_boxes,
                    page_num
                )

            # 2. Versuche aus detected_layout zu extrahieren
            if not words and ocr_result.detected_layout and isinstance(ocr_result.detected_layout, dict):
                words = self._extract_words_from_layout(
                    ocr_result.detected_layout,
                    page_num
                )

            return PageConfidence(
                page_number=page_num,
                overall_confidence=round(page_confidence, 4),
                words=words,
                backend=backend
            )

        except Exception as e:
            logger.warning(
                "failed_to_extract_page_confidence",
                ocr_result_id=str(ocr_result.id),
                **safe_error_log(e)
            )
            return None

    def _extract_words_from_bounding_boxes(
        self,
        bounding_boxes: List[Dict[str, Any]],
        page_num: int
    ) -> List[WordConfidence]:
        """
        Extrahiert Woerter aus bounding_boxes Array.

        Erwartet Format:
        [
            {
                "text": "Wort",
                "confidence": 0.95,
                "bbox": [x, y, width, height]  # normalized 0-1
            }
        ]

        Args:
            bounding_boxes: Liste von Bounding-Box-Dicts
            page_num: Seitennummer

        Returns:
            Liste von WordConfidence-Objekten
        """
        words: List[WordConfidence] = []

        for box in bounding_boxes:
            if not isinstance(box, dict):
                continue

            text = box.get("text", "")
            confidence = box.get("confidence", 0.0)
            bbox = box.get("bbox", [0, 0, 0, 0])

            if not text or not bbox or len(bbox) < 4:
                continue

            # Sicherstellen dass bbox normalisiert ist (0-1)
            x, y, width, height = bbox[:4]

            # Falls bbox absolute Werte sind, versuche zu normalisieren
            # (heuristisch: Werte > 10 sind wahrscheinlich Pixel)
            if max(x, y, width, height) > 10:
                # Annahme: Standard-Seitengroesse A4 (595 x 842 Punkte)
                x = x / 595.0
                y = y / 842.0
                width = width / 595.0
                height = height / 842.0

            words.append(WordConfidence(
                text=text,
                confidence=float(confidence),
                page=page_num,
                x=float(x),
                y=float(y),
                width=float(width),
                height=float(height)
            ))

        return words

    def _extract_words_from_layout(
        self,
        layout: Dict[str, Any],
        page_num: int
    ) -> List[WordConfidence]:
        """
        Extrahiert Woerter aus detected_layout Dict.

        Verschiedene Backends speichern Layout unterschiedlich:
        - DeepSeek: layout.words[], layout.regions[]
        - GOT-OCR: layout.tokens[], layout.lines[]
        - Surya: layout.blocks[], layout.text_regions[]

        Args:
            layout: Layout-Dict
            page_num: Seitennummer

        Returns:
            Liste von WordConfidence-Objekten
        """
        words: List[WordConfidence] = []

        # Versuche verschiedene Keys
        word_keys = ["words", "tokens", "text_regions", "regions", "blocks"]

        for key in word_keys:
            if key in layout and isinstance(layout[key], list):
                for item in layout[key]:
                    if not isinstance(item, dict):
                        continue

                    word = self._parse_layout_item(item, page_num)
                    if word:
                        words.append(word)

                # Wenn wir Woerter gefunden haben, stoppen
                if words:
                    break

        return words

    def _parse_layout_item(
        self,
        item: Dict[str, Any],
        page_num: int
    ) -> Optional[WordConfidence]:
        """
        Parsed ein Layout-Item zu WordConfidence.

        Args:
            item: Layout-Item Dict
            page_num: Seitennummer

        Returns:
            WordConfidence oder None
        """
        text = item.get("text") or item.get("content") or ""
        if not text:
            return None

        confidence = item.get("confidence") or item.get("score") or 0.0

        # Bounding-Box kann in verschiedenen Formaten sein
        bbox = (
            item.get("bbox")
            or item.get("bounding_box")
            or item.get("box")
            or item.get("coordinates")
        )

        if not bbox:
            return None

        # Versuche bbox zu parsen
        try:
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                x, y, width, height = bbox[:4]
            elif isinstance(bbox, dict):
                x = bbox.get("x", 0)
                y = bbox.get("y", 0)
                width = bbox.get("width", 0) or bbox.get("w", 0)
                height = bbox.get("height", 0) or bbox.get("h", 0)
            else:
                return None

            # Normalisieren falls noetig (siehe _extract_words_from_bounding_boxes)
            if max(x, y, width, height) > 10:
                x = x / 595.0
                y = y / 842.0
                width = width / 595.0
                height = height / 842.0

            return WordConfidence(
                text=str(text),
                confidence=float(confidence),
                page=page_num,
                x=float(x),
                y=float(y),
                width=float(width),
                height=float(height)
            )

        except (ValueError, TypeError, KeyError):
            return None

    def _extract_from_document_metadata(
        self,
        document: Document,
        page_number: Optional[int],
        backend: str
    ) -> List[PageConfidence]:
        """
        Extrahiert Confidence-Daten aus document.metadata JSONB.

        Args:
            document: Document-Objekt
            page_number: Optional spezifische Seite
            backend: Backend-Name

        Returns:
            Liste von PageConfidence
        """
        pages: List[PageConfidence] = []

        if not document.document_metadata:
            return pages

        metadata = document.document_metadata

        # Versuche verschiedene Metadata-Keys
        # (abhaengig davon wie OCR-Agents die Daten speichern)
        confidence_keys = [
            "ocr_confidence_data",
            "confidence_data",
            "page_confidences",
            "pages"
        ]

        for key in confidence_keys:
            if key in metadata and isinstance(metadata[key], (list, dict)):
                try:
                    # Parse je nach Struktur
                    if isinstance(metadata[key], list):
                        pages = self._parse_metadata_pages_list(
                            metadata[key],
                            page_number,
                            backend
                        )
                    elif isinstance(metadata[key], dict):
                        pages = self._parse_metadata_pages_dict(
                            metadata[key],
                            page_number,
                            backend
                        )

                    if pages:
                        break

                except Exception as e:
                    logger.debug(
                        "failed_to_parse_metadata_key",
                        key=key,
                        **safe_error_log(e)
                    )
                    continue

        return pages

    def _parse_metadata_pages_list(
        self,
        pages_data: List[Dict[str, Any]],
        page_number: Optional[int],
        backend: str
    ) -> List[PageConfidence]:
        """Parsed Seiten-Liste aus Metadata."""
        pages: List[PageConfidence] = []

        for idx, page_data in enumerate(pages_data):
            if not isinstance(page_data, dict):
                continue

            page_num = page_data.get("page", idx + 1)

            # Filter nach page_number wenn gegeben
            if page_number is not None and page_num != page_number:
                continue

            page_conf = page_data.get("confidence") or page_data.get("overall_confidence") or 0.0

            words: List[WordConfidence] = []

            # Extrahiere Woerter wenn vorhanden
            if "words" in page_data and isinstance(page_data["words"], list):
                words = self._extract_words_from_bounding_boxes(
                    page_data["words"],
                    page_num
                )

            pages.append(PageConfidence(
                page_number=page_num,
                overall_confidence=round(page_conf, 4),
                words=words,
                backend=backend
            ))

        return pages

    def _parse_metadata_pages_dict(
        self,
        pages_data: Dict[str, Any],
        page_number: Optional[int],
        backend: str
    ) -> List[PageConfidence]:
        """Parsed Seiten-Dict aus Metadata (Key = Page Number)."""
        pages: List[PageConfidence] = []

        for page_key, page_data in pages_data.items():
            if not isinstance(page_data, dict):
                continue

            try:
                page_num = int(page_key)
            except (ValueError, TypeError):
                continue

            # Filter nach page_number wenn gegeben
            if page_number is not None and page_num != page_number:
                continue

            page_conf = page_data.get("confidence") or page_data.get("overall_confidence") or 0.0

            words: List[WordConfidence] = []

            # Extrahiere Woerter wenn vorhanden
            if "words" in page_data and isinstance(page_data["words"], list):
                words = self._extract_words_from_bounding_boxes(
                    page_data["words"],
                    page_num
                )

            pages.append(PageConfidence(
                page_number=page_num,
                overall_confidence=round(page_conf, 4),
                words=words,
                backend=backend
            ))

        return pages

    def _create_fallback_pages(
        self,
        total_pages: int,
        overall_confidence: float,
        backend: str,
        page_number: Optional[int]
    ) -> List[PageConfidence]:
        """
        Erstellt Fallback-Seiten wenn keine Detail-Daten vorhanden.

        Nutzt die Gesamt-Confidence fuer alle Seiten.

        Args:
            total_pages: Anzahl Seiten
            overall_confidence: Gesamt-Confidence
            backend: Backend-Name
            page_number: Optional spezifische Seite

        Returns:
            Liste von PageConfidence mit leeren Word-Listen
        """
        pages: List[PageConfidence] = []

        if page_number is not None:
            # Nur spezifische Seite
            pages.append(PageConfidence(
                page_number=page_number,
                overall_confidence=round(overall_confidence, 4),
                words=[],
                backend=backend
            ))
        else:
            # Alle Seiten
            for page_num in range(1, total_pages + 1):
                pages.append(PageConfidence(
                    page_number=page_num,
                    overall_confidence=round(overall_confidence, 4),
                    words=[],
                    backend=backend
                ))

        return pages

    async def get_confidence_summary(
        self,
        document_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Liefert eine Zusammenfassung der Confidence-Daten.

        Schnellere Alternative zu get_confidence_data() fuer Overview.

        Args:
            document_id: Dokument-ID
            user_id: Benutzer-ID

        Returns:
            Dict mit Summary-Daten

        Raises:
            ValueError: Dokument nicht gefunden oder keine Berechtigung
        """
        # Dokument laden mit Access-Check
        query = select(Document).where(Document.id == document_id)
        result = await self._db.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden")

        if document.owner_id != user_id:
            raise ValueError("Keine Berechtigung fuer dieses Dokument")

        # OCR-Ergebnisse zaehlen
        ocr_query = select(OCRResult).where(OCRResult.document_id == document_id)
        ocr_results = await self._db.execute(ocr_query)
        ocr_results_list = list(ocr_results.scalars().all())

        # Per-Page Averages berechnen
        page_averages: Dict[int, float] = {}
        for ocr_result in ocr_results_list:
            if ocr_result.page_number and ocr_result.confidence_score is not None:
                page_averages[ocr_result.page_number] = round(
                    ocr_result.confidence_score, 4
                )

        return {
            "document_id": str(document_id),
            "overall_confidence": round(document.ocr_confidence or 0.0, 4),
            "total_pages": document.page_count or 1,
            "backend": document.ocr_backend_used or "unknown",
            "page_averages": page_averages,
            "has_word_level_data": any(
                bool(r.bounding_boxes) for r in ocr_results_list
            )
        }
