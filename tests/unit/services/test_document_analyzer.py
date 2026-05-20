# -*- coding: utf-8 -*-
"""
Tests fuer DocumentAnalyzer.

Testet:
- Dokumentanalyse und Backend-Empfehlung
- Feature-Erkennung (Tabellen, Bilder, Handschrift)
- Dokumenttyp-Klassifikation
- Komplexitaetsbewertung
- DPI-Schaetzung
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from app.services.document_analyzer import (
    DocumentAnalyzer,
    DocumentAnalysisResult,
    OCRBackend,
    DocumentType,
    DocumentComplexity,
    get_document_analyzer,
    analyze_and_recommend,
)


class TestDocumentAnalysisResultDataclass:
    """Tests fuer DocumentAnalysisResult Dataclass."""

    def test_create_basic_result(self):
        """Sollte Basis-Ergebnis erstellen."""
        result = DocumentAnalysisResult(
            document_type=DocumentType.TEXT_ONLY,
            complexity=DocumentComplexity.SIMPLE,
            recommended_backend=OCRBackend.SURYA_GPU,
            confidence=0.85
        )

        assert result.document_type == DocumentType.TEXT_ONLY
        assert result.complexity == DocumentComplexity.SIMPLE
        assert result.recommended_backend == OCRBackend.SURYA_GPU
        assert result.confidence == 0.85

    def test_result_with_features(self):
        """Sollte Ergebnis mit Features erstellen."""
        result = DocumentAnalysisResult(
            document_type=DocumentType.TABLE_HEAVY,
            complexity=DocumentComplexity.COMPLEX,
            recommended_backend=OCRBackend.GOT_OCR,
            confidence=0.90,
            has_tables=True,
            has_images=True,
            has_multiple_columns=True,
            features_detected=["tables", "images", "multiple_columns"]
        )

        assert result.has_tables is True
        assert result.has_images is True
        assert len(result.features_detected) == 3

    def test_result_defaults(self):
        """Sollte korrekte Defaults haben."""
        result = DocumentAnalysisResult(
            document_type=DocumentType.UNKNOWN,
            complexity=DocumentComplexity.SIMPLE,
            recommended_backend=OCRBackend.SURYA,
            confidence=0.5
        )

        assert result.has_tables is False
        assert result.has_images is False
        assert result.has_handwriting is False
        assert result.estimated_text_density == 0.0
        assert result.page_count == 1
        assert result.features_detected == []


class TestOCRBackendEnum:
    """Tests fuer OCRBackend Enum."""

    def test_backend_values(self):
        """Sollte korrekte Backend-Werte haben."""
        assert OCRBackend.DEEPSEEK.value == "deepseek"
        assert OCRBackend.GOT_OCR.value == "got_ocr"
        assert OCRBackend.SURYA_GPU.value == "surya_gpu"
        assert OCRBackend.SURYA.value == "surya"


class TestDocumentTypeEnum:
    """Tests fuer DocumentType Enum."""

    def test_document_type_values(self):
        """Sollte korrekte Dokumenttyp-Werte haben."""
        assert DocumentType.TEXT_ONLY.value == "text_only"
        assert DocumentType.TABLE_HEAVY.value == "table_heavy"
        assert DocumentType.HANDWRITTEN.value == "handwritten"
        assert DocumentType.HISTORICAL.value == "historical"


class TestDocumentComplexityEnum:
    """Tests fuer DocumentComplexity Enum."""

    def test_complexity_values(self):
        """Sollte korrekte Komplexitaetswerte haben."""
        assert DocumentComplexity.SIMPLE.value == "simple"
        assert DocumentComplexity.MODERATE.value == "moderate"
        assert DocumentComplexity.COMPLEX.value == "complex"
        assert DocumentComplexity.VERY_COMPLEX.value == "very_complex"


class TestDocumentAnalyzerInit:
    """Tests fuer Analyzer-Initialisierung."""

    def test_init_creates_analyzer(self):
        """Sollte Analyzer korrekt initialisieren."""
        analyzer = DocumentAnalyzer()

        assert analyzer.BACKEND_CAPABILITIES is not None
        assert OCRBackend.DEEPSEEK in analyzer.BACKEND_CAPABILITIES

    def test_backend_capabilities_structure(self):
        """Sollte korrekte Capabilities-Struktur haben."""
        analyzer = DocumentAnalyzer()

        for backend, capabilities in analyzer.BACKEND_CAPABILITIES.items():
            assert "handwriting" in capabilities
            assert "tables" in capabilities
            assert "simple_text" in capabilities
            assert "speed" in capabilities
            assert "german_accuracy" in capabilities


class TestEstimateDPI:
    """Tests fuer _estimate_dpi Methode."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    def test_estimate_dpi_from_metadata(self, analyzer: DocumentAnalyzer):
        """Sollte DPI aus Metadaten lesen."""
        image = MagicMock()
        image.info = {"dpi": (300, 300)}

        result = analyzer._estimate_dpi(image)

        assert result == 300

    def test_estimate_dpi_large_image(self, analyzer: DocumentAnalyzer):
        """Sollte hohen DPI fuer grosse Bilder schaetzen."""
        image = MagicMock()
        image.info = {}
        image.size = (2500, 3500)

        result = analyzer._estimate_dpi(image)

        assert result == 300

    def test_estimate_dpi_medium_image(self, analyzer: DocumentAnalyzer):
        """Sollte mittleren DPI fuer mittlere Bilder schaetzen."""
        image = MagicMock()
        image.info = {}
        image.size = (1200, 1600)

        result = analyzer._estimate_dpi(image)

        assert result == 150

    def test_estimate_dpi_small_image(self, analyzer: DocumentAnalyzer):
        """Sollte niedrigen DPI fuer kleine Bilder schaetzen."""
        image = MagicMock()
        image.info = {}
        image.size = (800, 600)

        result = analyzer._estimate_dpi(image)

        assert result == 72


class TestClassifyDocumentType:
    """Tests fuer _classify_document_type Methode."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    def test_classify_handwritten(self, analyzer: DocumentAnalyzer):
        """Sollte Handschrift erkennen."""
        result = analyzer._classify_document_type(
            has_tables=False,
            has_images=False,
            has_handwriting=True,
            has_formulas=False,
            has_multiple_columns=False,
            is_historical=False,
            text_density=0.5
        )

        assert result == DocumentType.HANDWRITTEN

    def test_classify_historical(self, analyzer: DocumentAnalyzer):
        """Sollte historisches Dokument erkennen."""
        result = analyzer._classify_document_type(
            has_tables=False,
            has_images=False,
            has_handwriting=False,
            has_formulas=False,
            has_multiple_columns=False,
            is_historical=True,
            text_density=0.5
        )

        assert result == DocumentType.HISTORICAL

    def test_classify_table_heavy(self, analyzer: DocumentAnalyzer):
        """Sollte Tabellen-lastiges Dokument erkennen."""
        result = analyzer._classify_document_type(
            has_tables=True,
            has_images=False,
            has_handwriting=False,
            has_formulas=False,
            has_multiple_columns=False,
            is_historical=False,
            text_density=0.5
        )

        assert result == DocumentType.TABLE_HEAVY

    def test_classify_technical(self, analyzer: DocumentAnalyzer):
        """Sollte technisches Dokument erkennen."""
        result = analyzer._classify_document_type(
            has_tables=False,
            has_images=False,
            has_handwriting=False,
            has_formulas=True,
            has_multiple_columns=False,
            is_historical=False,
            text_density=0.5
        )

        assert result == DocumentType.TECHNICAL

    def test_classify_text_only(self, analyzer: DocumentAnalyzer):
        """Sollte reinen Text erkennen."""
        result = analyzer._classify_document_type(
            has_tables=False,
            has_images=False,
            has_handwriting=False,
            has_formulas=False,
            has_multiple_columns=False,
            is_historical=False,
            text_density=0.5
        )

        assert result == DocumentType.TEXT_ONLY

    def test_classify_mixed(self, analyzer: DocumentAnalyzer):
        """Sollte gemischtes Dokument erkennen."""
        result = analyzer._classify_document_type(
            has_tables=True,
            has_images=True,
            has_handwriting=False,
            has_formulas=False,
            has_multiple_columns=False,
            is_historical=False,
            text_density=0.5
        )

        assert result == DocumentType.MIXED


class TestAssessComplexity:
    """Tests fuer _assess_complexity Methode."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    def test_simple_document(self, analyzer: DocumentAnalyzer):
        """Sollte einfaches Dokument erkennen."""
        result = analyzer._assess_complexity(
            has_tables=False,
            has_images=False,
            has_handwriting=False,
            has_multiple_columns=False,
            is_historical=False,
            noise_level=0.1
        )

        assert result == DocumentComplexity.SIMPLE

    def test_moderate_complexity(self, analyzer: DocumentAnalyzer):
        """Sollte moderate Komplexitaet erkennen."""
        result = analyzer._assess_complexity(
            has_tables=True,
            has_images=False,
            has_handwriting=False,
            has_multiple_columns=False,
            is_historical=False,
            noise_level=0.1
        )

        assert result == DocumentComplexity.MODERATE

    def test_complex_document(self, analyzer: DocumentAnalyzer):
        """Sollte komplexes Dokument erkennen."""
        result = analyzer._assess_complexity(
            has_tables=True,
            has_images=True,
            has_handwriting=False,
            has_multiple_columns=True,
            is_historical=False,
            noise_level=0.1
        )

        assert result == DocumentComplexity.COMPLEX

    def test_very_complex_document(self, analyzer: DocumentAnalyzer):
        """Sollte sehr komplexes Dokument erkennen."""
        result = analyzer._assess_complexity(
            has_tables=True,
            has_images=True,
            has_handwriting=True,
            has_multiple_columns=True,
            is_historical=False,
            noise_level=0.6
        )

        assert result == DocumentComplexity.VERY_COMPLEX


class TestRecommendBackend:
    """Tests fuer _recommend_backend Methode."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    def test_recommend_deepseek_for_handwriting(self, analyzer: DocumentAnalyzer):
        """Sollte DeepSeek fuer Handschrift empfehlen."""
        recommended, alternative, confidence, reasoning = analyzer._recommend_backend(
            doc_type=DocumentType.HANDWRITTEN,
            complexity=DocumentComplexity.COMPLEX,
            language="de",
            prefer_speed=False,
            gpu_available=True,
            features=["handwriting"]
        )

        assert recommended == OCRBackend.DEEPSEEK

    def test_recommend_got_for_tables(self, analyzer: DocumentAnalyzer):
        """Sollte GOT-OCR fuer Tabellen empfehlen."""
        recommended, alternative, confidence, reasoning = analyzer._recommend_backend(
            doc_type=DocumentType.TABLE_HEAVY,
            complexity=DocumentComplexity.MODERATE,
            language="de",
            prefer_speed=False,
            gpu_available=True,
            features=["tables"]
        )

        assert recommended == OCRBackend.GOT_OCR

    def test_recommend_surya_for_simple_text(self, analyzer: DocumentAnalyzer):
        """Sollte Surya GPU fuer einfachen Text empfehlen."""
        recommended, alternative, confidence, reasoning = analyzer._recommend_backend(
            doc_type=DocumentType.TEXT_ONLY,
            complexity=DocumentComplexity.SIMPLE,
            language="de",
            prefer_speed=True,
            gpu_available=True,
            features=[]
        )

        assert recommended == OCRBackend.SURYA_GPU

    def test_fallback_without_gpu(self, analyzer: DocumentAnalyzer):
        """Sollte CPU-Fallback ohne GPU empfehlen."""
        recommended, alternative, confidence, reasoning = analyzer._recommend_backend(
            doc_type=DocumentType.TEXT_ONLY,
            complexity=DocumentComplexity.SIMPLE,
            language="de",
            prefer_speed=False,
            gpu_available=False,
            features=[]
        )

        assert recommended == OCRBackend.SURYA

    def test_reasoning_contains_language(self, analyzer: DocumentAnalyzer):
        """Sollte Sprache in Reasoning erwaehnen."""
        recommended, alternative, confidence, reasoning = analyzer._recommend_backend(
            doc_type=DocumentType.TEXT_ONLY,
            complexity=DocumentComplexity.SIMPLE,
            language="de",
            prefer_speed=False,
            gpu_available=True,
            features=[]
        )

        assert "Deutsch" in reasoning


class TestAnalyze:
    """Tests fuer analyze Hauptmethode."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    @pytest.fixture
    def mock_pil_image(self):
        image = MagicMock()
        image.size = (1200, 1600)
        image.mode = "RGB"
        image.info = {}
        image.convert.return_value = image
        return image

    def test_analyze_without_opencv(self, analyzer: DocumentAnalyzer, mock_pil_image):
        """Sollte ohne OpenCV funktionieren."""
        with patch('app.services.document_analyzer.OPENCV_AVAILABLE', False):
            with patch('numpy.array', return_value=np.zeros((1600, 1200), dtype=np.uint8)):
                result = analyzer.analyze(mock_pil_image)

                assert result is not None
                assert result.document_type is not None
                assert result.recommended_backend is not None

    def test_analyze_returns_result(self, analyzer: DocumentAnalyzer, mock_pil_image):
        """Sollte DocumentAnalysisResult zurueckgeben."""
        with patch.object(analyzer, '_detect_tables', return_value=False), \
             patch.object(analyzer, '_detect_images', return_value=False), \
             patch.object(analyzer, '_detect_handwriting', return_value=False), \
             patch.object(analyzer, '_detect_multiple_columns', return_value=False), \
             patch.object(analyzer, '_detect_historical', return_value=False), \
             patch.object(analyzer, '_estimate_text_density', return_value=0.5), \
             patch.object(analyzer, '_estimate_noise_level', return_value=0.1), \
             patch.object(analyzer, '_pil_to_cv2', return_value=np.zeros((1600, 1200, 3), dtype=np.uint8)), \
             patch('app.services.document_analyzer.OPENCV_AVAILABLE', True), \
             patch('cv2.cvtColor', return_value=np.zeros((1600, 1200), dtype=np.uint8)):

            result = analyzer.analyze(mock_pil_image)

            assert isinstance(result, DocumentAnalysisResult)
            assert result.width == 1200
            assert result.height == 1600

    def test_analyze_with_language(self, analyzer: DocumentAnalyzer, mock_pil_image):
        """Sollte Sprachpraeferenz beruecksichtigen."""
        with patch.object(analyzer, '_detect_tables', return_value=False), \
             patch.object(analyzer, '_detect_images', return_value=False), \
             patch.object(analyzer, '_detect_handwriting', return_value=False), \
             patch.object(analyzer, '_detect_multiple_columns', return_value=False), \
             patch.object(analyzer, '_detect_historical', return_value=False), \
             patch.object(analyzer, '_estimate_text_density', return_value=0.5), \
             patch.object(analyzer, '_estimate_noise_level', return_value=0.1), \
             patch.object(analyzer, '_pil_to_cv2', return_value=np.zeros((1600, 1200, 3), dtype=np.uint8)), \
             patch('app.services.document_analyzer.OPENCV_AVAILABLE', True), \
             patch('cv2.cvtColor', return_value=np.zeros((1600, 1200), dtype=np.uint8)):

            result = analyzer.analyze(mock_pil_image, language="de")

            assert "Deutsch" in result.reasoning


class TestConvenienceFunctions:
    """Tests fuer Convenience-Funktionen."""

    def test_get_document_analyzer_singleton(self):
        """Sollte immer gleiche Instanz zurueckgeben."""
        # Reset singleton
        import app.services.document_analyzer as module
        module._analyzer = None

        analyzer1 = get_document_analyzer()
        analyzer2 = get_document_analyzer()

        assert analyzer1 is analyzer2

    def test_analyze_and_recommend_returns_dict(self):
        """Sollte Dictionary mit Empfehlung zurueckgeben."""
        mock_image = MagicMock()
        mock_image.size = (1200, 1600)
        mock_image.mode = "RGB"
        mock_image.info = {}
        mock_image.convert.return_value = mock_image

        with patch('app.services.document_analyzer.get_document_analyzer') as mock_get:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = DocumentAnalysisResult(
                document_type=DocumentType.TEXT_ONLY,
                complexity=DocumentComplexity.SIMPLE,
                recommended_backend=OCRBackend.SURYA_GPU,
                confidence=0.85,
                reasoning="Test reasoning"
            )
            mock_get.return_value = mock_analyzer

            result = analyze_and_recommend(mock_image)

            assert "recommended_backend" in result
            assert "document_type" in result
            assert "complexity" in result
            assert "confidence" in result
            assert "reasoning" in result


class TestPILToCV2:
    """Tests fuer _pil_to_cv2 Methode."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    def test_convert_rgb_image(self, analyzer: DocumentAnalyzer):
        """Sollte RGB-Bild konvertieren."""
        mock_image = MagicMock()
        mock_image.mode = "RGB"
        mock_image.convert.return_value = mock_image

        with patch('numpy.array', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
             patch('cv2.cvtColor', return_value=np.zeros((100, 100, 3), dtype=np.uint8)):
            result = analyzer._pil_to_cv2(mock_image)

            assert result is not None

    def test_convert_non_rgb_image(self, analyzer: DocumentAnalyzer):
        """Sollte Nicht-RGB-Bild zuerst konvertieren."""
        mock_image = MagicMock()
        mock_image.mode = "L"  # Grayscale
        mock_converted = MagicMock()
        mock_converted.mode = "RGB"
        mock_image.convert.return_value = mock_converted

        with patch('numpy.array', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
             patch('cv2.cvtColor', return_value=np.zeros((100, 100, 3), dtype=np.uint8)):
            result = analyzer._pil_to_cv2(mock_image)

            mock_image.convert.assert_called_with("RGB")


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.fixture
    def analyzer(self):
        return DocumentAnalyzer()

    def test_empty_features_list(self, analyzer: DocumentAnalyzer):
        """Sollte mit leerer Feature-Liste funktionieren."""
        recommended, alternative, confidence, reasoning = analyzer._recommend_backend(
            doc_type=DocumentType.UNKNOWN,
            complexity=DocumentComplexity.SIMPLE,
            language="de",
            prefer_speed=False,
            gpu_available=True,
            features=[]
        )

        assert recommended is not None

    def test_very_small_image(self, analyzer: DocumentAnalyzer):
        """Sollte sehr kleine Bilder verarbeiten."""
        image = MagicMock()
        image.info = {}
        image.size = (100, 100)

        result = analyzer._estimate_dpi(image)

        assert result == 72
