# -*- coding: utf-8 -*-
"""
Tests fuer AutoGroundTruthService.

Testet:
- Automatische Ground-Truth-Generierung
- Auto-Accept-Validierung
- Strukturelle Validierung
- Umlaut-Validierung
- OCR-Artefakt-Erkennung
- Batch-Verarbeitung
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.auto_ground_truth_service import (
    AutoGroundTruthService,
    AutoAcceptResult,
    StructuralValidationResult,
    ProcessingResult,
    get_auto_ground_truth_service,
)


class TestAutoAcceptResultDataclass:
    """Tests fuer AutoAcceptResult Dataclass."""

    def test_create_accept_result(self):
        """Sollte akzeptierendes Ergebnis erstellen."""
        result = AutoAcceptResult(
            should_accept=True,
            reasons=["Confidence OK", "Struktur valide"],
            confidence=0.96,
            validation_details={"confidence_valid": True},
            business_priority=1.5
        )

        assert result.should_accept is True
        assert len(result.reasons) == 2
        assert result.confidence == 0.96
        assert result.business_priority == 1.5

    def test_create_reject_result(self):
        """Sollte ablehnendes Ergebnis erstellen."""
        result = AutoAcceptResult(
            should_accept=False,
            reasons=["Confidence zu niedrig"],
            confidence=0.75,
            validation_details={"confidence_valid": False}
        )

        assert result.should_accept is False
        assert result.business_priority == 1.0  # Default


class TestStructuralValidationResultDataclass:
    """Tests fuer StructuralValidationResult Dataclass."""

    def test_create_valid_result(self):
        """Sollte valides Ergebnis erstellen."""
        result = StructuralValidationResult(
            is_valid=True,
            missing_fields=[],
            found_fields={"date": "2024-01-15", "amount": "1234.56"},
            validation_score=1.0
        )

        assert result.is_valid is True
        assert len(result.found_fields) == 2
        assert result.validation_score == 1.0

    def test_create_invalid_result(self):
        """Sollte invalides Ergebnis erstellen."""
        result = StructuralValidationResult(
            is_valid=False,
            missing_fields=["invoice_number"],
            found_fields={"date": "2024-01-15"},
            validation_score=0.67
        )

        assert result.is_valid is False
        assert "invoice_number" in result.missing_fields


class TestProcessingResultDataclass:
    """Tests fuer ProcessingResult Dataclass."""

    def test_create_success_result(self):
        """Sollte erfolgreiche Verarbeitung erstellen."""
        result = ProcessingResult(
            success=True,
            sample_id=uuid4(),
            auto_accepted=True,
            needs_manual_review=False,
            reasons=["Automatisch akzeptiert"]
        )

        assert result.success is True
        assert result.auto_accepted is True

    def test_result_default_reasons(self):
        """Sollte leere reasons-Liste als Default haben."""
        result = ProcessingResult(success=False)

        assert result.reasons == []


class TestAutoGroundTruthServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_service(self):
        """Sollte Service korrekt initialisieren."""
        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            service = AutoGroundTruthService()

            assert service.umlaut_validator is not None

    def test_service_constants(self):
        """Sollte Konstanten korrekt definieren."""
        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            service = AutoGroundTruthService()

            assert service.SPOT_CHECK_RATE == 0.10
            assert service.MIN_TEXT_LENGTH == 50
            assert service.DEFAULT_CONFIDENCE_THRESHOLD == 0.95


class TestValidateForAutoAccept:
    """Tests fuer validate_for_auto_accept Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.auto_ground_truth_service.UmlautValidationService') as mock_umlaut:
            mock_umlaut_instance = MagicMock()
            mock_umlaut_instance.validate_text.return_value = MagicMock(
                umlaut_accuracy=1.0,
                suggestions=[]
            )
            mock_umlaut.return_value = mock_umlaut_instance
            return AutoGroundTruthService()

    @pytest.mark.asyncio
    async def test_accept_high_confidence(self, service: AutoGroundTruthService):
        """Sollte Text mit hoher Confidence akzeptieren."""
        text = "Dies ist ein ausreichend langer Testtext fuer die Validierung."

        result = await service.validate_for_auto_accept(
            text=text,
            document_type="letter",
            confidence=0.98
        )

        assert result.should_accept is True
        assert result.validation_details["confidence_valid"] is True

    @pytest.mark.asyncio
    async def test_reject_low_confidence(self, service: AutoGroundTruthService):
        """Sollte Text mit niedriger Confidence ablehnen."""
        text = "Dies ist ein ausreichend langer Testtext fuer die Validierung."

        result = await service.validate_for_auto_accept(
            text=text,
            document_type="letter",
            confidence=0.80
        )

        assert result.should_accept is False
        assert result.validation_details["confidence_valid"] is False

    @pytest.mark.asyncio
    async def test_reject_short_text(self, service: AutoGroundTruthService):
        """Sollte kurzen Text ablehnen."""
        text = "Kurz"

        result = await service.validate_for_auto_accept(
            text=text,
            document_type="letter",
            confidence=0.99
        )

        assert result.should_accept is False
        assert result.validation_details["text_length_valid"] is False

    @pytest.mark.asyncio
    async def test_reject_empty_text(self, service: AutoGroundTruthService):
        """Sollte leeren Text ablehnen."""
        result = await service.validate_for_auto_accept(
            text="",
            document_type="letter",
            confidence=0.99
        )

        assert result.should_accept is False


class TestCheckOCRArtifacts:
    """Tests fuer _check_ocr_artifacts Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            return AutoGroundTruthService()

    def test_no_artifacts_clean_text(self, service: AutoGroundTruthService):
        """Sollte keinen Artefakte in sauberem Text finden."""
        text = "Dies ist ein sauberer deutscher Geschaeftstext ohne Probleme."

        result = service._check_ocr_artifacts(text)

        assert result["has_artifacts"] is False
        assert len(result["artifact_types"]) == 0

    def test_detect_special_char_cluster(self, service: AutoGroundTruthService):
        """Sollte Sonderzeichen-Cluster erkennen."""
        text = "Text mit !@#$%& vielen Sonderzeichen"

        result = service._check_ocr_artifacts(text)

        assert result["has_artifacts"] is True
        assert "sonderzeichen_cluster" in result["artifact_types"]

    def test_detect_digit_letter_confusion(self, service: AutoGroundTruthService):
        """Sollte Zahl-Buchstaben-Verwechslung erkennen."""
        text = "Text mit a1b2c3d4e5 Verwechslungen"

        result = service._check_ocr_artifacts(text)

        assert result["has_artifacts"] is True
        assert "digit_letter_confusion" in result["artifact_types"]

    def test_detect_excessive_caps(self, service: AutoGroundTruthService):
        """Sollte uebermaeßige Grossbuchstaben erkennen."""
        text = "Text mit ABCDEFGHIJKLMNOP zu vielen Grossbuchstaben"

        result = service._check_ocr_artifacts(text)

        assert result["has_artifacts"] is True
        assert "excessive_caps" in result["artifact_types"]


class TestValidateStructure:
    """Tests fuer _validate_structure Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            return AutoGroundTruthService()

    def test_invoice_all_fields_found(self, service: AutoGroundTruthService):
        """Sollte alle Rechnungsfelder finden."""
        text = """
        Rechnung Nr. RE-2024-001
        Datum: 15.01.2024
        Gesamtbetrag: 1.234,56 EUR
        """

        result = service._validate_structure(text, "invoice")

        assert result.is_valid is True
        assert result.validation_score == 1.0
        assert "invoice_number" in result.found_fields

    def test_invoice_missing_fields(self, service: AutoGroundTruthService):
        """Sollte fehlende Rechnungsfelder melden."""
        text = "Nur ein Text ohne relevante Felder."

        result = service._validate_structure(text, "invoice")

        assert result.is_valid is False
        assert "invoice_number" in result.missing_fields

    def test_letter_no_required_fields(self, service: AutoGroundTruthService):
        """Sollte Briefe ohne Pflichtfelder akzeptieren."""
        text = "Dies ist ein einfacher Brief."

        result = service._validate_structure(text, "letter")

        assert result.is_valid is True
        assert result.validation_score == 1.0

    def test_with_extracted_fields(self, service: AutoGroundTruthService):
        """Sollte bereits extrahierte Felder beruecksichtigen."""
        text = "Text ohne offensichtliche Felder"
        extracted = {"invoice_number": "RE-001", "date": "2024-01-15", "amount": "100.00"}

        result = service._validate_structure(text, "invoice", extracted_fields=extracted)

        assert result.is_valid is True


class TestDetectUmlauts:
    """Tests fuer Umlaut-Erkennung."""

    @pytest.fixture
    def service(self):
        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            return AutoGroundTruthService()

    def test_detect_umlauts_present(self, service: AutoGroundTruthService):
        """Sollte Umlaute erkennen."""
        text = "Text mit Umlauten: aeoeue ß"

        assert service._detect_umlauts(text) is True

    def test_detect_umlauts_absent(self, service: AutoGroundTruthService):
        """Sollte fehlende Umlaute erkennen."""
        text = "Text without umlauts: ae oe ue"

        assert service._detect_umlauts(text) is False

    def test_extract_umlaut_words(self, service: AutoGroundTruthService):
        """Sollte Woerter mit Umlauten extrahieren."""
        # Text mit echten Umlauten (ä, ö, ü, ß) - nicht Umschreibungen
        text = "Grüße aus München und Düsseldorf"

        words = service._extract_umlaut_words(text)

        assert len(words) > 0
        # Sollte "Grüße", "München", "Düsseldorf" finden
        assert any("ü" in w or "ß" in w for w in words)


@pytest.mark.asyncio
class TestProcessDocumentForTraining:
    """Tests fuer process_document_for_training Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.auto_ground_truth_service.UmlautValidationService') as mock_umlaut:
            mock_umlaut_instance = MagicMock()
            mock_umlaut_instance.validate_text.return_value = MagicMock(
                umlaut_accuracy=1.0,
                suggestions=[]
            )
            mock_umlaut.return_value = mock_umlaut_instance
            return AutoGroundTruthService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        return db

    async def test_process_high_confidence_document(
        self, service: AutoGroundTruthService, mock_db
    ):
        """Sollte Dokument mit hoher Confidence verarbeiten."""
        # Mock profile query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, '_create_auto_accepted_sample', new_callable=AsyncMock
        ) as mock_create:
            mock_sample = MagicMock()
            mock_sample.id = uuid4()
            mock_sample.needs_spot_check = False
            mock_create.return_value = mock_sample

            result = await service.process_document_for_training(
                db=mock_db,
                document_id=uuid4(),
                ocr_text="Dies ist ein langer Testtext fuer die Verarbeitung mit ausreichender Laenge.",
                ocr_confidence=0.98,
                document_type="letter"
            )

            assert result.success is True
            assert result.auto_accepted is True

    async def test_process_low_confidence_document(
        self, service: AutoGroundTruthService, mock_db
    ):
        """Sollte Dokument mit niedriger Confidence ablehnen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.process_document_for_training(
            db=mock_db,
            document_id=uuid4(),
            ocr_text="Testtext mit ausreichender Laenge fuer die Verarbeitung.",
            ocr_confidence=0.70,
            document_type="letter"
        )

        assert result.success is False
        assert result.auto_accepted is False
        assert result.needs_manual_review is True


@pytest.mark.asyncio
class TestProcessBatch:
    """Tests fuer process_batch Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            return AutoGroundTruthService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_batch_empty_documents(self, service: AutoGroundTruthService, mock_db):
        """Sollte leeren Batch verarbeiten."""
        result = await service.process_batch(mock_db, document_ids=[])

        assert result["processed"] == 0

    async def test_batch_respects_max_limit(
        self, service: AutoGroundTruthService, mock_db
    ):
        """Sollte max_documents Limit respektieren."""
        doc_ids = [uuid4() for _ in range(10)]

        with patch.object(
            service, '_get_document_with_ocr', new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None  # Dokumente nicht gefunden

            result = await service.process_batch(
                mock_db,
                document_ids=doc_ids,
                max_documents=5
            )

            # Sollte nur 5 verarbeitet haben
            assert mock_get.call_count == 5


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_auto_ground_truth_service_singleton(self):
        """Sollte immer gleiche Instanz zurueckgeben."""
        # Reset singleton
        import app.services.auto_ground_truth_service as module
        module._auto_ground_truth_service = None

        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            svc1 = get_auto_ground_truth_service()
            svc2 = get_auto_ground_truth_service()

        assert svc1 is svc2


class TestFieldPatterns:
    """Tests fuer Feld-Pattern-Erkennung."""

    @pytest.fixture
    def service(self):
        with patch('app.services.auto_ground_truth_service.UmlautValidationService'):
            return AutoGroundTruthService()

    def test_invoice_number_patterns(self, service: AutoGroundTruthService):
        """Sollte verschiedene Rechnungsnummern-Formate erkennen."""
        test_cases = [
            "Rechnungs-Nr.: 2024-001",
            "Rechnung Nr. RE-123",
            "Invoice #: ABC123",
        ]

        for text in test_cases:
            result = service._validate_structure(text, "invoice")
            assert "invoice_number" in result.found_fields, f"Pattern nicht erkannt in: {text}"

    def test_date_patterns(self, service: AutoGroundTruthService):
        """Sollte verschiedene Datumsformate erkennen."""
        test_cases = [
            "Datum: 15.01.2024",
            "Date: 2024-01-15",
            "Am 15/01/24",
        ]

        for text in test_cases:
            result = service._validate_structure(text, "contract")
            assert "date" in result.found_fields, f"Datum nicht erkannt in: {text}"

    def test_amount_patterns(self, service: AutoGroundTruthService):
        """Sollte verschiedene Betragsformate erkennen."""
        test_cases = [
            "Gesamt: 1.234,56 EUR",
            "Summe: 100,00€",
            "1.234,56 €",
        ]

        for text in test_cases:
            result = service._validate_structure(text, "invoice")
            assert "amount" in result.found_fields, f"Betrag nicht erkannt in: {text}"
