# -*- coding: utf-8 -*-
"""
Unit Tests fuer AutoCategorizationV2Service.

Testet LLM-basierte Dokument-Kategorisierung mit:
- Ollama-Integration
- Multi-Label-Klassifikation
- Fallback auf Pattern-Matching
- Korrektur-Lernen
- Confidence-Kalibrierung

Feinpoliert und durchdacht.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.ai.auto_categorization_v2_service import (
    AutoCategorizationV2Service,
    CategorizationV2Result,
    CategoryLabel,
    CategoryExplanation,
    DocumentType,
    CategorizationMethod,
    DOCUMENT_TYPE_LABELS_DE,
    get_auto_categorization_v2_service,
    reset_auto_categorization_v2_service,
)
from app.services.ai.auto_categorization_service import (
    CategorizationResult,
    DocumentCategory,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service() -> AutoCategorizationV2Service:
    """Erstellt frischen Service fuer jeden Test."""
    reset_auto_categorization_v2_service()
    return AutoCategorizationV2Service()


@pytest.fixture
def mock_ollama_service() -> MagicMock:
    """Mock fuer Ollama Service."""
    mock = MagicMock()
    mock.is_available = AsyncMock(return_value=True)
    mock.generate = AsyncMock(return_value='{"primary_type": "invoice", "primary_confidence": 0.95}')
    return mock


@pytest.fixture
def mock_pattern_service() -> MagicMock:
    """Mock fuer Pattern-basierten Kategorisierungs-Service."""
    mock = MagicMock()
    mock.categorize_text = MagicMock(
        return_value=CategorizationResult(
            category=DocumentCategory.INVOICE_INCOMING,
            display_name="Eingangsrechnung",
            confidence=0.85,
            matched_keywords=["rechnung", "betrag", "iban"],
            matched_patterns=["rechnung\\s*nr"],
            secondary_categories=[
                (DocumentCategory.DELIVERY_NOTE, 0.3),
            ],
        )
    )
    return mock


@pytest.fixture
def sample_invoice_text() -> str:
    """Beispiel-Rechnungstext."""
    return """
    Firma Musterhandel GmbH
    Musterstrasse 123
    12345 Musterstadt

    RECHNUNG

    Rechnungsnummer: RE-2026-001234
    Rechnungsdatum: 01.02.2026
    Faelligkeitsdatum: 15.02.2026

    Pos.  Beschreibung                    Menge    Einzelpreis    Gesamt
    1     Widget Professional             10       49,99 EUR      499,90 EUR
    2     Widget Enterprise               5        99,99 EUR      499,95 EUR

    Nettobetrag:                                                  999,85 EUR
    MwSt. 19%:                                                    189,97 EUR
    Gesamtbetrag:                                               1.189,82 EUR

    Bankverbindung:
    IBAN: DE89 3704 0044 0532 0130 00
    BIC: COBADEFFXXX

    Zahlungsziel: 14 Tage netto
    """


@pytest.fixture
def sample_contract_text() -> str:
    """Beispiel-Vertragstext."""
    return """
    RAHMENVERTRAG

    zwischen

    Musterhandel GmbH
    (nachfolgend "Auftraggeber")

    und

    Dienstleister AG
    (nachfolgend "Auftragnehmer")

    wird folgender Vertrag geschlossen:

    § 1 Vertragsgegenstand
    Der Auftragnehmer erbringt fuer den Auftraggeber IT-Dienstleistungen.

    § 2 Vertragsdauer
    Der Vertrag beginnt am 01.03.2026 und laeuft auf unbestimmte Zeit.
    Die Kuendigungsfrist betraegt 3 Monate zum Quartalsende.

    § 3 Verguetung
    Die monatliche Verguetung betraegt 5.000,00 EUR zzgl. MwSt.

    Unterschriften:
    """


# =============================================================================
# Tests: Basis-Funktionalitaet
# =============================================================================

class TestCategorizationV2Basics:
    """Tests fuer grundlegende Kategorisierungs-Funktionen."""

    def test_document_type_labels_de_complete(self):
        """Stellt sicher, dass alle DocumentTypes deutsche Labels haben."""
        for doc_type in DocumentType:
            assert doc_type in DOCUMENT_TYPE_LABELS_DE, f"Fehlendes Label fuer {doc_type}"
            assert len(DOCUMENT_TYPE_LABELS_DE[doc_type]) > 0

    def test_text_hash_consistency(self, service: AutoCategorizationV2Service):
        """Text-Hash sollte fuer gleichen Text identisch sein."""
        text = "Dies ist ein Testtext."
        hash1 = service._compute_text_hash(text)
        hash2 = service._compute_text_hash(text)
        assert hash1 == hash2

    def test_text_hash_normalization(self, service: AutoCategorizationV2Service):
        """Text-Hash sollte Whitespace normalisieren."""
        text1 = "Dies ist   ein Test"
        text2 = "Dies ist ein Test"
        hash1 = service._compute_text_hash(text1)
        hash2 = service._compute_text_hash(text2)
        assert hash1 == hash2

    def test_text_hash_case_insensitive(self, service: AutoCategorizationV2Service):
        """Text-Hash sollte case-insensitive sein."""
        text1 = "RECHNUNG"
        text2 = "rechnung"
        hash1 = service._compute_text_hash(text1)
        hash2 = service._compute_text_hash(text2)
        assert hash1 == hash2

    def test_truncate_text_short(self, service: AutoCategorizationV2Service):
        """Kurze Texte sollten nicht gekuerzt werden."""
        short_text = "Kurzer Text"
        result = service._truncate_text(short_text, max_length=100)
        assert result == short_text

    def test_truncate_text_long(self, service: AutoCategorizationV2Service):
        """Lange Texte sollten sinnvoll gekuerzt werden."""
        long_text = "A" * 5000
        result = service._truncate_text(long_text, max_length=1000)
        assert len(result) <= 1000 + 50  # Etwas Spielraum fuer Marker
        assert "[...Text gekuerzt...]" in result


# =============================================================================
# Tests: Pattern-basierte Kategorisierung (Fallback)
# =============================================================================

class TestPatternBasedCategorization:
    """Tests fuer Pattern-basierte Kategorisierung."""

    @pytest.mark.asyncio
    async def test_pattern_fallback_on_llm_unavailable(
        self,
        service: AutoCategorizationV2Service,
        mock_pattern_service: MagicMock,
        sample_invoice_text: str,
    ):
        """Sollte auf Pattern-Matching zurueckfallen wenn LLM nicht verfuegbar."""
        mock_ollama = MagicMock()
        mock_ollama.is_available = AsyncMock(return_value=False)

        service._ollama = mock_ollama
        service._pattern_service = mock_pattern_service

        result = await service.categorize_text(sample_invoice_text, use_llm=True)

        assert result.method == CategorizationMethod.PATTERN
        assert result.primary_type == DocumentType.INVOICE
        assert result.pattern_result is not None

    @pytest.mark.asyncio
    async def test_pattern_only_mode(
        self,
        service: AutoCategorizationV2Service,
        mock_pattern_service: MagicMock,
        sample_invoice_text: str,
    ):
        """Sollte nur Pattern-Matching verwenden wenn use_llm=False."""
        service._pattern_service = mock_pattern_service

        result = await service.categorize_text(sample_invoice_text, use_llm=False)

        assert result.method == CategorizationMethod.PATTERN
        assert result.primary_type == DocumentType.INVOICE

    @pytest.mark.asyncio
    async def test_pattern_result_conversion(
        self,
        service: AutoCategorizationV2Service,
        mock_pattern_service: MagicMock,
    ):
        """Pattern-Ergebnis sollte korrekt in V2-Format konvertiert werden."""
        service._pattern_service = mock_pattern_service

        result = await service.categorize_text("Test", use_llm=False)

        assert isinstance(result, CategorizationV2Result)
        assert len(result.labels) >= 1
        assert result.labels[0].is_primary is True
        assert result.explanation is not None
        assert len(result.explanation.key_indicators) > 0


# =============================================================================
# Tests: LLM-basierte Kategorisierung
# =============================================================================

class TestLLMCategorization:
    """Tests fuer LLM-basierte Kategorisierung."""

    @pytest.mark.asyncio
    async def test_llm_categorization_success(
        self,
        service: AutoCategorizationV2Service,
        mock_ollama_service: MagicMock,
        mock_pattern_service: MagicMock,
        sample_invoice_text: str,
    ):
        """Erfolgreiche LLM-Kategorisierung."""
        mock_ollama_service.generate = AsyncMock(return_value='''
        {
            "primary_type": "invoice",
            "primary_confidence": 0.95,
            "additional_types": [
                {"type": "order", "confidence": 0.3}
            ],
            "explanation": {
                "summary": "Rechnung erkannt anhand typischer Merkmale",
                "key_indicators": ["Rechnungsnummer", "IBAN", "MwSt"],
                "context_clues": ["Zahlungsziel", "Bankverbindung"],
                "reasoning": "Dokument enthaelt Rechnungsnummer, Betraege und Zahlungsdaten"
            }
        }
        ''')

        service._ollama = mock_ollama_service
        service._pattern_service = mock_pattern_service

        result = await service.categorize_text(sample_invoice_text, use_llm=True)

        assert result.method == CategorizationMethod.LLM
        assert result.primary_type == DocumentType.INVOICE
        assert result.primary_confidence >= 0.9
        assert len(result.labels) >= 2
        assert "Rechnungsnummer" in result.explanation.key_indicators

    @pytest.mark.asyncio
    async def test_llm_fallback_on_parse_error(
        self,
        service: AutoCategorizationV2Service,
        mock_ollama_service: MagicMock,
        mock_pattern_service: MagicMock,
        sample_invoice_text: str,
    ):
        """Sollte auf Pattern zurueckfallen bei LLM Parse-Fehler."""
        mock_ollama_service.generate = AsyncMock(return_value="Invalid JSON Response")

        service._ollama = mock_ollama_service
        service._pattern_service = mock_pattern_service

        result = await service.categorize_text(sample_invoice_text, use_llm=True)

        # Sollte auf Pattern-Matching zurueckfallen
        assert result.method == CategorizationMethod.PATTERN

    @pytest.mark.asyncio
    async def test_llm_json_extraction_from_text(
        self,
        service: AutoCategorizationV2Service,
    ):
        """JSON sollte aus umgebendem Text extrahiert werden."""
        response = '''
        Hier ist meine Analyse:
        {"primary_type": "contract", "primary_confidence": 0.88}
        Das war meine Antwort.
        '''
        result = service._parse_llm_response(response)

        assert result is not None
        assert result["primary_type"] == "contract"

    @pytest.mark.asyncio
    async def test_llm_skipped_for_short_text(
        self,
        service: AutoCategorizationV2Service,
        mock_pattern_service: MagicMock,
    ):
        """LLM sollte fuer zu kurze Texte uebersprungen werden."""
        service._pattern_service = mock_pattern_service
        mock_ollama = MagicMock()
        service._ollama = mock_ollama

        short_text = "Kurz"
        result = await service.categorize_text(short_text, use_llm=True)

        # LLM sollte nicht aufgerufen werden
        mock_ollama.is_available.assert_not_called()
        assert result.method == CategorizationMethod.PATTERN

    @pytest.mark.asyncio
    async def test_llm_skipped_for_high_pattern_confidence(
        self,
        service: AutoCategorizationV2Service,
        mock_pattern_service: MagicMock,
        sample_invoice_text: str,
    ):
        """LLM sollte uebersprungen werden wenn Pattern sehr sicher ist."""
        mock_pattern_service.categorize_text = MagicMock(
            return_value=CategorizationResult(
                category=DocumentCategory.INVOICE_INCOMING,
                display_name="Eingangsrechnung",
                confidence=0.95,  # Sehr hoch
                matched_keywords=["rechnung"],
                matched_patterns=[],
                secondary_categories=[],
            )
        )
        service._pattern_service = mock_pattern_service
        mock_ollama = MagicMock()
        service._ollama = mock_ollama

        result = await service.categorize_text(sample_invoice_text, use_llm=True)

        # LLM sollte nicht aufgerufen werden bei hoher Pattern-Confidence
        mock_ollama.is_available.assert_not_called()
        assert result.method == CategorizationMethod.PATTERN


# =============================================================================
# Tests: Caching
# =============================================================================

class TestCaching:
    """Tests fuer Ergebnis-Caching."""

    @pytest.mark.asyncio
    async def test_cache_hit(
        self,
        service: AutoCategorizationV2Service,
        mock_pattern_service: MagicMock,
    ):
        """Wiederholte Anfragen sollten aus Cache kommen."""
        service._pattern_service = mock_pattern_service

        text = "Rechnung Test"

        # Erste Anfrage
        result1 = await service.categorize_text(text, use_llm=False, use_cache=True)

        # Zweite Anfrage
        result2 = await service.categorize_text(text, use_llm=False, use_cache=True)

        assert result2.method == CategorizationMethod.CACHED
        # Pattern sollte nur einmal aufgerufen werden
        assert mock_pattern_service.categorize_text.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_disabled(
        self,
        service: AutoCategorizationV2Service,
        mock_pattern_service: MagicMock,
    ):
        """Cache kann deaktiviert werden."""
        service._pattern_service = mock_pattern_service

        text = "Rechnung Test"

        await service.categorize_text(text, use_llm=False, use_cache=True)
        result = await service.categorize_text(text, use_llm=False, use_cache=False)

        assert result.method != CategorizationMethod.CACHED

    def test_clear_cache(self, service: AutoCategorizationV2Service):
        """Cache sollte geleert werden koennen."""
        service._cache["test_hash"] = (MagicMock(), datetime.now(timezone.utc))
        service._cache["test_hash2"] = (MagicMock(), datetime.now(timezone.utc))

        count = service.clear_cache()

        assert count == 2
        assert len(service._cache) == 0


# =============================================================================
# Tests: Multi-Label
# =============================================================================

class TestMultiLabel:
    """Tests fuer Multi-Label-Klassifikation."""

    @pytest.mark.asyncio
    async def test_multiple_labels_from_llm(
        self,
        service: AutoCategorizationV2Service,
        mock_ollama_service: MagicMock,
        mock_pattern_service: MagicMock,
        sample_invoice_text: str,
    ):
        """LLM sollte mehrere Labels mit Confidences liefern."""
        mock_ollama_service.generate = AsyncMock(return_value='''
        {
            "primary_type": "invoice",
            "primary_confidence": 0.92,
            "additional_types": [
                {"type": "order", "confidence": 0.45},
                {"type": "delivery_note", "confidence": 0.35}
            ],
            "explanation": {
                "summary": "Mehrere Dokumenttypen moeglich",
                "key_indicators": [],
                "context_clues": [],
                "reasoning": ""
            }
        }
        ''')

        service._ollama = mock_ollama_service
        service._pattern_service = mock_pattern_service

        result = await service.categorize_text(sample_invoice_text, use_llm=True)

        assert len(result.labels) == 3
        assert result.labels[0].is_primary is True
        assert result.labels[0].document_type == DocumentType.INVOICE
        assert result.labels[1].document_type == DocumentType.ORDER
        assert result.labels[2].document_type == DocumentType.DELIVERY_NOTE

    def test_secondary_categories_from_pattern(
        self,
        service: AutoCategorizationV2Service,
    ):
        """Sekundaere Kategorien aus Pattern sollten uebernommen werden."""
        pattern_result = CategorizationResult(
            category=DocumentCategory.INVOICE_INCOMING,
            display_name="Eingangsrechnung",
            confidence=0.8,
            matched_keywords=["rechnung"],
            matched_patterns=[],
            secondary_categories=[
                (DocumentCategory.ORDER, 0.4),
                (DocumentCategory.DELIVERY_NOTE, 0.3),
            ],
        )

        import time
        result = service._convert_pattern_result(pattern_result, time.perf_counter())

        assert len(result.labels) >= 2


# =============================================================================
# Tests: Kalibrierung
# =============================================================================

class TestCalibration:
    """Tests fuer Confidence-Kalibrierung."""

    def test_apply_calibration_adjustment(
        self,
        service: AutoCategorizationV2Service,
    ):
        """Kalibrierung sollte Confidence anpassen."""
        from app.services.ai.auto_categorization_v2_service import CalibrationData

        service._calibration_data[DocumentType.INVOICE] = CalibrationData(
            document_type=DocumentType.INVOICE,
            total_predictions=100,
            correct_predictions=90,
            accuracy=0.9,
            confidence_adjustment=-0.05,  # Reduziere um 5%
            last_updated=datetime.now(timezone.utc),
        )

        result = CategorizationV2Result(
            primary_type=DocumentType.INVOICE,
            primary_confidence=0.95,
            labels=[],
            explanation=CategoryExplanation("", [], [], ""),
            method=CategorizationMethod.LLM,
            processing_time_ms=100,
        )

        calibrated = service._apply_calibration(result)

        assert calibrated.calibrated_confidence == 0.90  # 0.95 - 0.05

    def test_calibration_clipping(
        self,
        service: AutoCategorizationV2Service,
    ):
        """Kalibrierte Confidence sollte auf 0-1 begrenzt sein."""
        from app.services.ai.auto_categorization_v2_service import CalibrationData

        service._calibration_data[DocumentType.INVOICE] = CalibrationData(
            document_type=DocumentType.INVOICE,
            total_predictions=10,
            correct_predictions=1,
            accuracy=0.1,
            confidence_adjustment=0.2,  # Wuerde 1.15 ergeben
            last_updated=datetime.now(timezone.utc),
        )

        result = CategorizationV2Result(
            primary_type=DocumentType.INVOICE,
            primary_confidence=0.95,
            labels=[],
            explanation=CategoryExplanation("", [], [], ""),
            method=CategorizationMethod.LLM,
            processing_time_ms=100,
        )

        calibrated = service._apply_calibration(result)

        assert calibrated.calibrated_confidence <= 1.0


# =============================================================================
# Tests: Korrektur-Lernen
# =============================================================================

class TestCorrectionLearning:
    """Tests fuer Lernen aus User-Korrekturen."""

    def test_extract_keywords(
        self,
        service: AutoCategorizationV2Service,
        sample_invoice_text: str,
    ):
        """Keywords sollten aus Text extrahiert werden."""
        keywords = service._extract_keywords(sample_invoice_text)

        assert len(keywords) > 0
        assert "rechnung" in [k.lower() for k in keywords]

    def test_confidence_level_mapping(
        self,
        service: AutoCategorizationV2Service,
    ):
        """Confidence sollte korrekt auf Levels gemappt werden."""
        assert service._confidence_level(0.96) == "auto_apply"
        assert service._confidence_level(0.85) == "suggest"
        assert service._confidence_level(0.60) == "review"
        assert service._confidence_level(0.30) == "low"


# =============================================================================
# Tests: Singleton
# =============================================================================

class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_instance(self):
        """Sollte immer dieselbe Instanz zurueckgeben."""
        reset_auto_categorization_v2_service()

        service1 = get_auto_categorization_v2_service()
        service2 = get_auto_categorization_v2_service()

        assert service1 is service2

    def test_singleton_reset(self):
        """Reset sollte neue Instanz erzeugen."""
        service1 = get_auto_categorization_v2_service()
        reset_auto_categorization_v2_service()
        service2 = get_auto_categorization_v2_service()

        assert service1 is not service2
