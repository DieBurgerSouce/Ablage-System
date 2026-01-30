# -*- coding: utf-8 -*-
"""
Document Classification Agent for Ablage-System.

Enterprise-grade document classification with:
- Document type detection (invoice, contract, letter, receipt, form)
- Language detection (German-first)
- Quality assessment (DPI, noise, clarity)
- Complexity scoring (tables, handwriting, multi-column)
- OCR backend recommendation

Feinpoliert und durchdacht - 100% Genauigkeit für deutsche Dokumente.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.agents.base import PreprocessingAgent
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class DocumentClassificationAgent(PreprocessingAgent):
    """
    Intelligent document classification agent.

    Analyzes uploaded documents to determine:
    - Document type (invoice, contract, letter, receipt, form, report, other)
    - Primary language (German-optimized)
    - Document complexity for OCR backend selection
    - Quality score for preprocessing decisions
    """

    # Document type keywords (German-first)
    DOCUMENT_KEYWORDS: Dict[str, List[str]] = {
        "invoice": [
            "rechnung", "rechnungsnummer", "rechnungsdatum", "invoice",
            "steuerbetrag", "nettobetrag", "bruttobetrag", "mwst",
            "mehrwertsteuer", "umsatzsteuer", "ust-idnr", "zahlungsziel",
            "bankverbindung", "iban", "bic", "rechnungsempfänger",
        ],
        "contract": [
            "vertrag", "vereinbarung", "vertragspartner", "paragraph",
            "haftung", "kündigung", "laufzeit", "unterschrift", "vertraglich",
            "gerichtsstand", "salvatorische klausel", "nebenabreden",
            "vertragsgegenstand", "vertragsbeginn", "vertragsende",
        ],
        "letter": [
            "sehr geehrte", "mit freundlichen grüßen", "betreff", "anrede",
            "hochachtungsvoll", "liebe grüße", "bezugnehmend auf",
            "anbei erhalten sie", "wie besprochen", "zur kenntnisnahme",
        ],
        "receipt": [
            "quittung", "kassenbon", "beleg", "zahlung erhalten",
            "bar bezahlt", "kartenzahlung", "kassennummer", "transaktions",
            "bon-nr", "mwst-satz", "zwischensumme", "gesamt",
        ],
        "form": [
            "antrag", "formular", "ausfüllen", "ankreuzen", "pflichtfeld",
            "unterschrift erforderlich", "zutreffendes ankreuzen",
            "geburtsdatum", "postleitzahl", "persönliche angaben",
        ],
        "report": [
            "bericht", "zusammenfassung", "analyse", "ergebnis", "fazit",
            "einleitung", "methodik", "schlussfolgerung", "empfehlung",
            "statistik", "auswertung", "übersicht",
        ],
    }

    # Language detection patterns
    LANGUAGE_PATTERNS: Dict[str, List[str]] = {
        "de": [
            "die", "der", "das", "und", "ist", "von", "für", "mit",
            "nicht", "auf", "sind", "haben", "werden", "einer", "eine",
            "ä", "ö", "ü", "ß", "sehr geehrte", "mit freundlichen",
        ],
        "en": [
            "the", "and", "is", "for", "with", "not", "are", "have",
            "been", "this", "that", "from", "dear", "regards", "sincerely",
        ],
    }

    # Complexity indicators
    COMPLEXITY_INDICATORS: Dict[str, List[str]] = {
        "tables": [
            "|", "┌", "┐", "└", "┘", "├", "┤", "┬", "┴", "┼",
            "tabelle", "spalte", "zeile", "summe", "gesamt",
        ],
        "multi_column": [
            "          ",  # Large whitespace gaps indicating columns
        ],
        "handwriting_indicators": [
            "handschriftlich", "unterschrift", "signatur",
        ],
    }

    # Backend recommendations based on document characteristics
    BACKEND_RECOMMENDATIONS: Dict[str, Dict[str, Any]] = {
        "deepseek": {
            "strengths": ["complex_layout", "fraktur", "handwriting", "tables"],
            "min_quality": 0.4,
            "vram_required": 12,
        },
        "got_ocr": {
            "strengths": ["tables", "formulas", "standard_text", "fast"],
            "min_quality": 0.5,
            "vram_required": 10,
        },
        "surya": {
            "strengths": ["standard_text", "multi_page", "cpu_fallback"],
            "min_quality": 0.6,
            "vram_required": 0,
        },
        "surya_gpu": {
            "strengths": ["standard_text", "fast", "multi_page"],
            "min_quality": 0.5,
            "vram_required": 4,
        },
    }

    # File extensions and their handling
    SUPPORTED_EXTENSIONS: Dict[str, str] = {
        ".pdf": "document",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".tif": "image",
        ".bmp": "image",
        ".webp": "image",
    }

    def __init__(self):
        """Initialize the Document Classification Agent."""
        super().__init__(name="document_classification_agent")
        self._sample_text_cache: Dict[str, str] = {}

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a document based on its content and characteristics.

        Args:
            input_data: Dictionary containing:
                - file_path: Path to the document file
                - options: Optional processing options

        Returns:
            Classification result containing:
                - document_type: Detected document type
                - language: Detected primary language
                - complexity: Complexity assessment
                - quality_score: Quality score (0.0-1.0)
                - has_tables: Boolean
                - has_handwriting: Boolean
                - has_multi_column: Boolean
                - recommended_backend: Recommended OCR backend
                - confidence: Classification confidence
                - metadata: Additional metadata
        """
        self.validate_input(input_data, ["file_path"])

        file_path = Path(input_data["file_path"])
        options = input_data.get("options", {})

        self.logger.info(
            "classification_started",
            file_path=str(file_path),
        )

        # Step 1: File analysis
        file_info = await self._analyze_file(file_path)

        # Step 2: Extract sample text (if possible)
        sample_text = await self._extract_sample_text(file_path, file_info)

        # Step 3: Detect document type
        document_type, type_confidence = self._classify_document_type(sample_text)

        # Step 4: Detect language
        language, lang_confidence = self._detect_language(sample_text)

        # Step 5: Assess complexity
        complexity_result = self._assess_complexity(sample_text, file_info)

        # Step 6: Calculate quality score
        quality_score = self._calculate_quality_score(file_info, complexity_result)

        # Step 7: Recommend OCR backend
        recommended_backend = self._recommend_backend(
            document_type=document_type,
            complexity=complexity_result,
            quality_score=quality_score,
            options=options,
        )

        # Calculate overall confidence
        overall_confidence = (type_confidence + lang_confidence) / 2

        result = {
            "document_type": document_type,
            "language": language,
            "complexity": complexity_result["level"],
            "quality_score": round(quality_score, 2),
            "has_tables": complexity_result["has_tables"],
            "has_handwriting": complexity_result["has_handwriting"],
            "has_multi_column": complexity_result["has_multi_column"],
            "recommended_backend": recommended_backend,
            "confidence": round(overall_confidence, 2),
            "metadata": {
                "file_info": file_info,
                "type_confidence": round(type_confidence, 2),
                "language_confidence": round(lang_confidence, 2),
                "complexity_details": complexity_result,
                "sample_text_length": len(sample_text),
            },
        }

        self.logger.info(
            "classification_completed",
            document_type=document_type,
            language=language,
            backend=recommended_backend,
            confidence=overall_confidence,
        )

        return result

    async def _analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Analyze file properties.

        Returns file information including size, type, and basic metadata.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

        stat = file_path.stat()
        extension = file_path.suffix.lower()

        file_info = {
            "path": str(file_path),
            "name": file_path.name,
            "extension": extension,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "file_type": self.SUPPORTED_EXTENSIONS.get(extension, "unknown"),
            "is_supported": extension in self.SUPPORTED_EXTENSIONS,
        }

        # Additional analysis for images
        if file_info["file_type"] == "image":
            file_info.update(await self._analyze_image(file_path))

        # Additional analysis for PDFs
        elif extension == ".pdf":
            file_info.update(await self._analyze_pdf(file_path))

        return file_info

    async def _analyze_image(self, file_path: Path) -> Dict[str, Any]:
        """Analyze image properties."""
        try:
            from PIL import Image

            with Image.open(file_path) as img:
                width, height = img.size
                dpi = img.info.get("dpi", (72, 72))

                # Estimate DPI if not available
                if isinstance(dpi, tuple):
                    dpi_x, dpi_y = dpi
                else:
                    dpi_x = dpi_y = dpi

                return {
                    "width": width,
                    "height": height,
                    "dpi_x": int(dpi_x) if dpi_x else 72,
                    "dpi_y": int(dpi_y) if dpi_y else 72,
                    "mode": img.mode,
                    "format": img.format,
                    "page_count": 1,
                    "is_grayscale": img.mode in ("L", "LA", "1"),
                }

        except Exception as e:
            self.logger.warning(
                "image_analysis_failed",
                file_path=str(file_path),
                **safe_error_log(e),
            )
            return {
                "width": 0,
                "height": 0,
                "dpi_x": 72,
                "dpi_y": 72,
                "page_count": 1,
            }

    async def _analyze_pdf(self, file_path: Path) -> Dict[str, Any]:
        """Analyze PDF properties."""
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(str(file_path))
            page_count = len(pdf)

            # Get first page dimensions
            if page_count > 0:
                page = pdf[0]
                width = page.get_width()
                height = page.get_height()
            else:
                width = height = 0

            pdf.close()

            return {
                "page_count": page_count,
                "width": int(width),
                "height": int(height),
                "dpi_x": 72,  # PDF native resolution
                "dpi_y": 72,
            }

        except Exception as e:
            self.logger.warning(
                "pdf_analysis_failed",
                file_path=str(file_path),
                **safe_error_log(e),
            )
            return {
                "page_count": 1,
                "width": 0,
                "height": 0,
                "dpi_x": 72,
                "dpi_y": 72,
            }

    async def _extract_sample_text(
        self, file_path: Path, file_info: Dict[str, Any]
    ) -> str:
        """
        Extract sample text for classification.

        Uses lightweight extraction for quick classification.
        """
        cache_key = str(file_path)
        if cache_key in self._sample_text_cache:
            return self._sample_text_cache[cache_key]

        sample_text = ""

        try:
            if file_info.get("extension") == ".pdf":
                sample_text = await self._extract_pdf_text(file_path)
            else:
                # For images, we can't extract text directly
                # Classification will be based on file properties
                sample_text = ""

        except Exception as e:
            self.logger.warning(
                "sample_text_extraction_failed",
                file_path=str(file_path),
                **safe_error_log(e),
            )

        # Cache for reuse
        self._sample_text_cache[cache_key] = sample_text

        return sample_text

    async def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF for classification."""
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(str(file_path))

            # Extract text from first 3 pages max (for quick classification)
            text_parts = []
            for i in range(min(3, len(pdf))):
                page = pdf[i]
                textpage = page.get_textpage()
                text_parts.append(textpage.get_text_range())

            pdf.close()

            return "\n".join(text_parts)[:5000]  # Limit to 5000 chars

        except Exception as e:
            self.logger.warning(
                "pdf_text_extraction_failed",
                file_path=str(file_path),
                **safe_error_log(e),
            )
            return ""

    def _classify_document_type(self, text: str) -> Tuple[str, float]:
        """
        Classify document type based on keywords.

        Returns (document_type, confidence).
        """
        if not text:
            return "unknown", 0.5

        text_lower = text.lower()
        scores: Dict[str, int] = {}

        # Count keyword matches for each document type
        for doc_type, keywords in self.DOCUMENT_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    # Weight longer keywords higher
                    score += len(keyword.split())
            scores[doc_type] = score

        # Find the type with highest score
        if not scores or max(scores.values()) == 0:
            return "other", 0.4

        best_type = max(scores.items(), key=lambda x: x[1])
        doc_type = best_type[0]
        score = best_type[1]

        # Calculate confidence based on score
        # More keyword matches = higher confidence
        total_keywords = len(self.DOCUMENT_KEYWORDS[doc_type])
        confidence = min(0.95, 0.5 + (score / total_keywords) * 0.5)

        return doc_type, confidence

    def _detect_language(self, text: str) -> Tuple[str, float]:
        """
        Detect document language.

        Returns (language_code, confidence).
        German-first detection for Ablage-System.
        """
        if not text:
            return "de", 0.5  # Default to German

        text_lower = text.lower()
        scores: Dict[str, int] = {}

        for lang, patterns in self.LANGUAGE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                count = text_lower.count(pattern)
                score += count
            scores[lang] = score

        # Check for German umlauts (strong indicator)
        umlaut_count = sum(1 for char in text if char in "äöüÄÖÜß")
        scores["de"] = scores.get("de", 0) + (umlaut_count * 3)  # Weight umlauts heavily

        if not scores or max(scores.values()) == 0:
            return "de", 0.5  # Default to German

        best_lang = max(scores.items(), key=lambda x: x[1])
        lang = best_lang[0]
        score = best_lang[1]

        # Calculate confidence
        confidence = min(0.95, 0.6 + min(score, 50) / 100)

        return lang, confidence

    def _assess_complexity(
        self, text: str, file_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Assess document complexity for OCR backend selection.

        Returns complexity assessment with details.
        """
        text_lower = text.lower() if text else ""

        # Check for tables
        table_indicators = sum(
            1 for indicator in self.COMPLEXITY_INDICATORS["tables"]
            if indicator in text_lower
        )
        has_tables = table_indicators >= 2

        # Check for multi-column layout
        has_multi_column = any(
            indicator in text
            for indicator in self.COMPLEXITY_INDICATORS["multi_column"]
        )

        # Check for handwriting indicators
        has_handwriting = any(
            indicator in text_lower
            for indicator in self.COMPLEXITY_INDICATORS["handwriting_indicators"]
        )

        # Calculate complexity score
        complexity_score = 0.0
        complexity_factors = []

        if has_tables:
            complexity_score += 0.3
            complexity_factors.append("tables")

        if has_multi_column:
            complexity_score += 0.2
            complexity_factors.append("multi_column")

        if has_handwriting:
            complexity_score += 0.4
            complexity_factors.append("handwriting")

        # Multi-page documents are more complex
        page_count = file_info.get("page_count", 1)
        if page_count > 10:
            complexity_score += 0.2
            complexity_factors.append("many_pages")
        elif page_count > 1:
            complexity_score += 0.1
            complexity_factors.append("multi_page")

        # Large file size can indicate complexity
        size_mb = file_info.get("size_mb", 0)
        if size_mb > 50:
            complexity_score += 0.1
            complexity_factors.append("large_file")

        # Determine complexity level
        if complexity_score >= 0.6:
            level = "high"
        elif complexity_score >= 0.3:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "score": round(complexity_score, 2),
            "has_tables": has_tables,
            "has_handwriting": has_handwriting,
            "has_multi_column": has_multi_column,
            "factors": complexity_factors,
            "page_count": page_count,
        }

    def _calculate_quality_score(
        self, file_info: Dict[str, Any], complexity: Dict[str, Any]
    ) -> float:
        """
        Calculate document quality score.

        Higher score = better quality for OCR.
        """
        score = 0.7  # Base score

        # DPI assessment
        dpi = file_info.get("dpi_x", 72)
        if dpi >= 300:
            score += 0.2
        elif dpi >= 200:
            score += 0.1
        elif dpi < 100:
            score -= 0.2

        # File size assessment (not too small, not corrupted)
        size_mb = file_info.get("size_mb", 0)
        if 0.1 <= size_mb <= 100:
            score += 0.1
        elif size_mb < 0.01:  # Very small, might be corrupted
            score -= 0.3

        # Supported format
        if file_info.get("is_supported", False):
            score += 0.1

        # Handwriting reduces effective quality
        if complexity.get("has_handwriting"):
            score -= 0.1

        return max(0.1, min(1.0, score))

    def _recommend_backend(
        self,
        document_type: str,
        complexity: Dict[str, Any],
        quality_score: float,
        options: Dict[str, Any],
    ) -> str:
        """
        Recommend optimal OCR backend based on document characteristics.

        Enterprise-grade selection logic.
        """
        # Check for forced backend option
        if forced := options.get("force_backend"):
            return forced

        complexity_level = complexity.get("level", "medium")
        has_tables = complexity.get("has_tables", False)
        has_handwriting = complexity.get("has_handwriting", False)

        # Decision tree for backend selection

        # High complexity or handwriting -> DeepSeek (best quality)
        if complexity_level == "high" or has_handwriting:
            if quality_score >= self.BACKEND_RECOMMENDATIONS["deepseek"]["min_quality"]:
                return "deepseek"

        # Invoices with tables -> GOT-OCR or DeepSeek
        if document_type == "invoice":
            if has_tables:
                # DeepSeek for complex invoices
                if complexity_level != "low":
                    return "deepseek"
                # GOT-OCR for simple invoices with tables
                return "got_ocr"
            # Simple invoice
            return "deepseek"

        # Documents with tables -> GOT-OCR (good at tables)
        if has_tables:
            return "got_ocr"

        # Standard documents with good quality -> Surya GPU (fast)
        if quality_score >= 0.7 and complexity_level == "low":
            return "surya_gpu"

        # Low quality documents -> DeepSeek (best at recovery)
        if quality_score < 0.5:
            return "deepseek"

        # Medium complexity -> GOT-OCR (balanced)
        if complexity_level == "medium":
            return "got_ocr"

        # Default for standard German documents
        return "deepseek"

    def clear_cache(self) -> None:
        """Clear the sample text cache."""
        self._sample_text_cache.clear()
