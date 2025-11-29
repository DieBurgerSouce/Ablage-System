# -*- coding: utf-8 -*-
"""
Unit Tests for DocumentClassificationAgent.

Tests document classification capabilities:
- Document type detection (invoice, contract, letter, etc.)
- Language detection (German-first with umlaut priority)
- Complexity assessment
- Quality scoring
- OCR backend recommendation
"""

import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.preprocessing.classification_agent import DocumentClassificationAgent


class TestDocumentClassificationAgentInit:
    """Test agent initialization."""

    def test_agent_initialization(self) -> None:
        """Agent sollte korrekt initialisiert werden."""
        agent = DocumentClassificationAgent()

        assert agent.name == "document_classification_agent"
        assert agent.category.value == "preprocessing"
        assert hasattr(agent, "_sample_text_cache")
        assert agent._sample_text_cache == {}

    def test_agent_has_document_keywords(self) -> None:
        """Agent sollte Dokument-Keywords für alle Typen haben."""
        agent = DocumentClassificationAgent()

        expected_types = ["invoice", "contract", "letter", "receipt", "form", "report"]
        for doc_type in expected_types:
            assert doc_type in agent.DOCUMENT_KEYWORDS
            assert len(agent.DOCUMENT_KEYWORDS[doc_type]) > 0

    def test_agent_has_language_patterns(self) -> None:
        """Agent sollte Sprachmuster für DE und EN haben."""
        agent = DocumentClassificationAgent()

        assert "de" in agent.LANGUAGE_PATTERNS
        assert "en" in agent.LANGUAGE_PATTERNS
        assert "ä" in agent.LANGUAGE_PATTERNS["de"]
        assert "ö" in agent.LANGUAGE_PATTERNS["de"]
        assert "ü" in agent.LANGUAGE_PATTERNS["de"]
        assert "ß" in agent.LANGUAGE_PATTERNS["de"]

    def test_agent_has_backend_recommendations(self) -> None:
        """Agent sollte Backend-Empfehlungen haben."""
        agent = DocumentClassificationAgent()

        expected_backends = ["deepseek", "got_ocr", "surya", "surya_gpu"]
        for backend in expected_backends:
            assert backend in agent.BACKEND_RECOMMENDATIONS
            assert "strengths" in agent.BACKEND_RECOMMENDATIONS[backend]
            assert "min_quality" in agent.BACKEND_RECOMMENDATIONS[backend]
            assert "vram_required" in agent.BACKEND_RECOMMENDATIONS[backend]


class TestDocumentTypeClassification:
    """Test document type classification logic."""

    def test_classify_invoice_german(self) -> None:
        """Deutsche Rechnungen sollten korrekt erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Rechnung Nr. 2024-001
        Rechnungsdatum: 15.03.2024

        Sehr geehrte Damen und Herren,

        für die erbrachten Leistungen erlauben wir uns, folgenden Betrag in Rechnung zu stellen:

        Nettobetrag: 1.000,00 EUR
        MwSt. 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR

        Zahlungsziel: 30 Tage
        IBAN: DE89 3704 0044 0532 0130 00
        BIC: COBADEFFXXX
        """

        doc_type, confidence = agent._classify_document_type(text)

        assert doc_type == "invoice"
        assert confidence >= 0.7

    def test_classify_contract_german(self) -> None:
        """Deutsche Verträge sollten korrekt erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Mietvertrag

        zwischen den Vertragspartnern:

        § 1 Vertragsgegenstand
        Der Vermieter vermietet dem Mieter die nachstehend bezeichnete Wohnung.

        § 2 Mietzeit und Kündigung
        Vertragsbeginn: 01.04.2024
        Die Laufzeit beträgt unbefristet.

        § 3 Haftung

        § 4 Salvatorische Klausel

        Unterschrift: ________________
        Gerichtsstand: Berlin
        """

        doc_type, confidence = agent._classify_document_type(text)

        assert doc_type == "contract"
        assert confidence >= 0.7

    def test_classify_letter_german(self) -> None:
        """Deutsche Briefe sollten korrekt erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Sehr geehrte Damen und Herren,

        bezugnehmend auf unser Telefonat möchte ich wie besprochen die Unterlagen übersenden.
        Anbei erhalten Sie die gewünschten Dokumente zur Kenntnisnahme.

        Mit freundlichen Grüßen
        Max Mustermann
        """

        doc_type, confidence = agent._classify_document_type(text)

        assert doc_type == "letter"
        assert confidence >= 0.6

    def test_classify_receipt_german(self) -> None:
        """Deutsche Quittungen sollten korrekt erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        QUITTUNG
        Kassenbon Nr. 12345

        Artikel 1        10,99 EUR
        Artikel 2        5,49 EUR
        -------------------
        Zwischensumme    16,48 EUR
        MwSt-Satz 19%     2,63 EUR
        -------------------
        Gesamt           16,48 EUR

        Bar bezahlt
        Kartenzahlung akzeptiert
        """

        doc_type, confidence = agent._classify_document_type(text)

        assert doc_type == "receipt"
        assert confidence >= 0.6

    def test_classify_form_german(self) -> None:
        """Deutsche Formulare sollten korrekt erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        ANTRAG auf Erteilung einer Aufenthaltsgenehmigung

        Bitte füllen Sie dieses Formular vollständig aus.
        Pflichtfeld mit * markiert.

        Persönliche Angaben:
        Name: ________________
        Geburtsdatum: __.__.____
        Postleitzahl: _____

        [ ] Zutreffendes ankreuzen

        Unterschrift erforderlich: ________________
        """

        doc_type, confidence = agent._classify_document_type(text)

        assert doc_type == "form"
        assert confidence >= 0.6

    def test_classify_empty_text_returns_unknown(self) -> None:
        """Leerer Text sollte 'unknown' zurückgeben."""
        agent = DocumentClassificationAgent()

        doc_type, confidence = agent._classify_document_type("")

        assert doc_type == "unknown"
        assert confidence == 0.5

    def test_classify_no_keywords_returns_other(self) -> None:
        """Text ohne erkannte Keywords sollte 'other' zurückgeben."""
        agent = DocumentClassificationAgent()
        text = "Dies ist ein generischer Text ohne spezifische Dokumentmerkmale."

        doc_type, confidence = agent._classify_document_type(text)

        assert doc_type == "other"
        assert confidence == 0.4


class TestLanguageDetection:
    """Test language detection capabilities."""

    def test_detect_german_with_umlauts(self) -> None:
        """Deutscher Text mit Umlauten sollte erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Österreichische Küche mit Käsespätzle und Würstchen.
        Übermäßige Größe für gewöhnliche Verhältnisse.
        """

        language, confidence = agent._detect_language(text)

        assert language == "de"
        assert confidence >= 0.7

    def test_detect_german_with_common_words(self) -> None:
        """Deutscher Text ohne Umlaute sollte erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Die Firma hat einen neuen Vertrag mit dem Kunden abgeschlossen.
        Der Mitarbeiter ist nicht auf der Arbeit, da er krank ist.
        """

        language, confidence = agent._detect_language(text)

        assert language == "de"
        assert confidence >= 0.6

    def test_detect_english(self) -> None:
        """Englischer Text sollte erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Dear Sir or Madam,

        This is a formal letter regarding the recent contract.
        We have been working on this project for months.

        Sincerely,
        John Smith
        """

        language, confidence = agent._detect_language(text)

        assert language == "en"
        assert confidence >= 0.6

    def test_empty_text_defaults_to_german(self) -> None:
        """Leerer Text sollte Deutsch als Standard zurückgeben."""
        agent = DocumentClassificationAgent()

        language, confidence = agent._detect_language("")

        assert language == "de"
        assert confidence == 0.5

    def test_umlaut_weighting(self) -> None:
        """Umlaute sollten stark gewichtet werden."""
        agent = DocumentClassificationAgent()
        # Mostly English but with German umlauts
        text = "The company in München has a café"

        language, confidence = agent._detect_language(text)

        # Should detect German due to ü in München
        assert language == "de"


class TestComplexityAssessment:
    """Test complexity assessment logic."""

    def test_detect_tables_in_text(self) -> None:
        """Tabellen im Text sollten erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Produktübersicht:

        | Produkt | Preis | Menge |
        |---------|-------|-------|
        | A       | 10€   | 5     |
        | B       | 20€   | 3     |

        Summe: 110€
        """
        file_info = {"page_count": 1, "size_mb": 0.5}

        complexity = agent._assess_complexity(text, file_info)

        assert complexity["has_tables"] is True
        assert "tables" in complexity["factors"]

    def test_detect_handwriting_indicators(self) -> None:
        """Handschrift-Indikatoren sollten erkannt werden."""
        agent = DocumentClassificationAgent()
        text = """
        Bitte unterschreiben Sie hier: _______________
        Handschriftlich ausfüllen!
        Signatur erforderlich.
        """
        file_info = {"page_count": 1, "size_mb": 0.5}

        complexity = agent._assess_complexity(text, file_info)

        assert complexity["has_handwriting"] is True
        assert "handwriting" in complexity["factors"]

    def test_multi_page_increases_complexity(self) -> None:
        """Viele Seiten sollten die Komplexität erhöhen."""
        agent = DocumentClassificationAgent()
        text = "Einfacher Text"
        file_info = {"page_count": 15, "size_mb": 5.0}

        complexity = agent._assess_complexity(text, file_info)

        assert "many_pages" in complexity["factors"]
        assert complexity["score"] >= 0.2

    def test_large_file_increases_complexity(self) -> None:
        """Große Dateien sollten die Komplexität erhöhen."""
        agent = DocumentClassificationAgent()
        text = "Einfacher Text"
        file_info = {"page_count": 1, "size_mb": 60.0}

        complexity = agent._assess_complexity(text, file_info)

        assert "large_file" in complexity["factors"]

    def test_complexity_levels(self) -> None:
        """Komplexitätsstufen sollten korrekt zugeordnet werden."""
        agent = DocumentClassificationAgent()

        # Low complexity
        low = agent._assess_complexity("Einfacher Text", {"page_count": 1, "size_mb": 0.1})
        assert low["level"] == "low"

        # High complexity
        high_text = """
        | Tabelle | mit | Daten |
        Unterschrift handschriftlich
        """
        high = agent._assess_complexity(high_text, {"page_count": 20, "size_mb": 60})
        assert high["level"] == "high"


class TestQualityScoring:
    """Test quality score calculation."""

    def test_high_dpi_increases_quality(self) -> None:
        """Hohe DPI sollte die Qualität erhöhen."""
        agent = DocumentClassificationAgent()
        file_info = {"dpi_x": 300, "size_mb": 1.0, "is_supported": True}
        complexity = {"has_handwriting": False}

        score = agent._calculate_quality_score(file_info, complexity)

        assert score >= 0.9

    def test_low_dpi_decreases_quality(self) -> None:
        """Niedrige DPI sollte die Qualität verringern."""
        agent = DocumentClassificationAgent()
        file_info = {"dpi_x": 72, "size_mb": 1.0, "is_supported": True}
        complexity = {"has_handwriting": False}

        score = agent._calculate_quality_score(file_info, complexity)

        assert score < 0.8

    def test_very_small_file_decreases_quality(self) -> None:
        """Sehr kleine Dateien sollten die Qualität verringern."""
        agent = DocumentClassificationAgent()
        file_info = {"dpi_x": 300, "size_mb": 0.001, "is_supported": True}
        complexity = {"has_handwriting": False}

        score = agent._calculate_quality_score(file_info, complexity)

        assert score < 0.7

    def test_handwriting_decreases_quality(self) -> None:
        """Handschrift sollte die effektive Qualität verringern."""
        agent = DocumentClassificationAgent()
        file_info = {"dpi_x": 300, "size_mb": 1.0, "is_supported": True}
        complexity_with = {"has_handwriting": True}
        complexity_without = {"has_handwriting": False}

        score_with = agent._calculate_quality_score(file_info, complexity_with)
        score_without = agent._calculate_quality_score(file_info, complexity_without)

        assert score_with < score_without

    def test_quality_bounds(self) -> None:
        """Qualitätswert sollte zwischen 0.1 und 1.0 liegen."""
        agent = DocumentClassificationAgent()

        # Minimum case
        min_info = {"dpi_x": 50, "size_mb": 0.001, "is_supported": False}
        min_score = agent._calculate_quality_score(min_info, {"has_handwriting": True})
        assert min_score >= 0.1

        # Maximum case
        max_info = {"dpi_x": 600, "size_mb": 5.0, "is_supported": True}
        max_score = agent._calculate_quality_score(max_info, {"has_handwriting": False})
        assert max_score <= 1.0


class TestBackendRecommendation:
    """Test OCR backend recommendation logic."""

    def test_forced_backend_option(self) -> None:
        """Force-Backend Option sollte respektiert werden."""
        agent = DocumentClassificationAgent()

        result = agent._recommend_backend(
            document_type="invoice",
            complexity={"level": "high", "has_tables": True, "has_handwriting": False},
            quality_score=0.9,
            options={"force_backend": "surya"},
        )

        assert result == "surya"

    def test_high_complexity_recommends_deepseek(self) -> None:
        """Hohe Komplexität sollte DeepSeek empfehlen."""
        agent = DocumentClassificationAgent()

        result = agent._recommend_backend(
            document_type="contract",
            complexity={"level": "high", "has_tables": True, "has_handwriting": True},
            quality_score=0.8,
            options={},
        )

        assert result == "deepseek"

    def test_handwriting_recommends_deepseek(self) -> None:
        """Handschrift sollte DeepSeek empfehlen."""
        agent = DocumentClassificationAgent()

        result = agent._recommend_backend(
            document_type="form",
            complexity={"level": "medium", "has_tables": False, "has_handwriting": True},
            quality_score=0.7,
            options={},
        )

        assert result == "deepseek"

    def test_invoice_with_tables_recommends_got_or_deepseek(self) -> None:
        """Rechnungen mit Tabellen sollten GOT oder DeepSeek empfehlen."""
        agent = DocumentClassificationAgent()

        # Simple invoice with tables -> got_ocr
        result_simple = agent._recommend_backend(
            document_type="invoice",
            complexity={"level": "low", "has_tables": True, "has_handwriting": False},
            quality_score=0.8,
            options={},
        )
        assert result_simple == "got_ocr"

        # Complex invoice with tables -> deepseek
        result_complex = agent._recommend_backend(
            document_type="invoice",
            complexity={"level": "medium", "has_tables": True, "has_handwriting": False},
            quality_score=0.8,
            options={},
        )
        assert result_complex == "deepseek"

    def test_simple_document_recommends_surya_gpu(self) -> None:
        """Einfache Dokumente mit guter Qualität sollten Surya GPU empfehlen."""
        agent = DocumentClassificationAgent()

        result = agent._recommend_backend(
            document_type="letter",
            complexity={"level": "low", "has_tables": False, "has_handwriting": False},
            quality_score=0.85,
            options={},
        )

        assert result == "surya_gpu"

    def test_low_quality_recommends_deepseek(self) -> None:
        """Niedrige Qualität sollte DeepSeek empfehlen."""
        agent = DocumentClassificationAgent()

        result = agent._recommend_backend(
            document_type="letter",
            complexity={"level": "low", "has_tables": False, "has_handwriting": False},
            quality_score=0.4,
            options={},
        )

        assert result == "deepseek"


class TestFileAnalysis:
    """Test file analysis functionality."""

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file_raises_error(self) -> None:
        """Nicht existierende Datei sollte FileNotFoundError werfen."""
        agent = DocumentClassificationAgent()
        fake_path = Path("/nonexistent/file.pdf")

        with pytest.raises(FileNotFoundError) as exc_info:
            await agent._analyze_file(fake_path)

        assert "Datei nicht gefunden" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_analyze_supported_extension(self) -> None:
        """Unterstützte Dateierweiterungen sollten erkannt werden."""
        agent = DocumentClassificationAgent()

        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"dummy content")
            tmp_path = Path(tmp.name)

        try:
            file_info = await agent._analyze_file(tmp_path)

            assert file_info["extension"] == ".pdf"
            assert file_info["is_supported"] is True
            assert file_info["file_type"] == "document"
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_analyze_unsupported_extension(self) -> None:
        """Nicht unterstützte Dateierweiterungen sollten als unknown markiert werden."""
        agent = DocumentClassificationAgent()

        # Create temp file with unsupported extension
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as tmp:
            tmp.write(b"dummy content")
            tmp_path = Path(tmp.name)

        try:
            file_info = await agent._analyze_file(tmp_path)

            assert file_info["extension"] == ".xyz"
            assert file_info["is_supported"] is False
            assert file_info["file_type"] == "unknown"
        finally:
            tmp_path.unlink()


class TestCacheManagement:
    """Test sample text cache functionality."""

    def test_clear_cache(self) -> None:
        """Cache sollte geleert werden können."""
        agent = DocumentClassificationAgent()
        agent._sample_text_cache["test_key"] = "test_value"

        agent.clear_cache()

        assert len(agent._sample_text_cache) == 0

    @pytest.mark.asyncio
    async def test_cache_is_used(self) -> None:
        """Cache sollte bei wiederholten Aufrufen verwendet werden."""
        agent = DocumentClassificationAgent()

        # Pre-populate cache - use Path converted to string for correct cache key
        file_path = Path("/path/to/file.pdf")
        cache_key = str(file_path)  # Matches what the method uses internally
        cached_text = "Cached text content"
        agent._sample_text_cache[cache_key] = cached_text

        file_info = {"extension": ".pdf"}

        result = await agent._extract_sample_text(file_path, file_info)

        assert result == cached_text


class TestFullProcessingPipeline:
    """Test complete classification pipeline."""

    @pytest.mark.asyncio
    async def test_process_requires_file_path(self) -> None:
        """Verarbeitung sollte file_path erfordern."""
        agent = DocumentClassificationAgent()

        with pytest.raises(ValueError) as exc_info:
            await agent.process({})

        assert "file_path" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_nonexistent_file(self) -> None:
        """Verarbeitung einer nicht existierenden Datei sollte Fehler werfen."""
        agent = DocumentClassificationAgent()

        with pytest.raises(FileNotFoundError):
            await agent.process({"file_path": "/nonexistent/file.pdf"})

    @pytest.mark.asyncio
    async def test_process_returns_complete_result(self) -> None:
        """Verarbeitung sollte vollständiges Ergebnis zurückgeben."""
        agent = DocumentClassificationAgent()

        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 dummy content")
            tmp_path = Path(tmp.name)

        try:
            # Mock the PDF text extraction
            with patch.object(
                agent, "_extract_pdf_text", new_callable=AsyncMock
            ) as mock_extract:
                mock_extract.return_value = "Rechnung Nr. 2024-001 MwSt Bruttobetrag"

                result = await agent.process({"file_path": str(tmp_path)})

                # Verify all expected keys are present
                expected_keys = [
                    "document_type",
                    "language",
                    "complexity",
                    "quality_score",
                    "has_tables",
                    "has_handwriting",
                    "has_multi_column",
                    "recommended_backend",
                    "confidence",
                    "metadata",
                ]
                for key in expected_keys:
                    assert key in result, f"Missing key: {key}"

                # Verify types
                assert isinstance(result["document_type"], str)
                assert isinstance(result["language"], str)
                assert isinstance(result["quality_score"], float)
                assert isinstance(result["confidence"], float)
                assert isinstance(result["has_tables"], bool)
                assert isinstance(result["has_handwriting"], bool)
                assert isinstance(result["metadata"], dict)
        finally:
            tmp_path.unlink()
