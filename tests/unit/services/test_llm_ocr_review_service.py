# -*- coding: utf-8 -*-
"""
Tests fuer LLMOCRReviewService.

Testet:
- LLM-basierte OCR-Review
- Circuit Breaker Pattern
- Batch Review
- Review Stats
- Response Parsing
- Fehlerbehandlung
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
import sys

# Mock tenacity if not installed
if 'tenacity' not in sys.modules:
    tenacity_mock = MagicMock()
    tenacity_mock.retry = lambda **kwargs: lambda f: f
    tenacity_mock.stop_after_attempt = MagicMock()
    tenacity_mock.wait_exponential = MagicMock()
    tenacity_mock.retry_if_exception_type = MagicMock()
    sys.modules['tenacity'] = tenacity_mock

from app.services.llm_ocr_review_service import (
    LLMOCRReviewService,
    LLMReviewResult,
    BatchReviewResult,
    get_llm_ocr_review_service,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
)


class TestLLMReviewResultDataclass:
    """Tests fuer LLMReviewResult Dataclass."""

    def test_create_basic_result(self):
        """Sollte LLMReviewResult mit Pflichtfeldern erstellen."""
        result = LLMReviewResult(
            quality_score=8.5,
            issues_found=["OCR-Fehler 1", "OCR-Fehler 2"],
            recommendation="accept",
            reasoning="Text ist gut lesbar und verwendbar."
        )

        assert result.quality_score == 8.5
        assert len(result.issues_found) == 2
        assert result.recommendation == "accept"
        assert result.corrected_text is None
        assert result.confidence == 0.0
        assert result.processing_time_ms == 0

    def test_create_result_with_correction(self):
        """Sollte LLMReviewResult mit Korrektur erstellen."""
        result = LLMReviewResult(
            quality_score=7.0,
            issues_found=["Umlaut-Fehler: ae -> ae"],
            recommendation="accept",
            reasoning="Nach Korrektur verwendbar.",
            corrected_text="Korrigierter Text mit korrekten Umlauten.",
            confidence=0.85,
            processing_time_ms=1500
        )

        assert result.corrected_text is not None
        assert result.confidence == 0.85
        assert result.processing_time_ms == 1500


class TestBatchReviewResultDataclass:
    """Tests fuer BatchReviewResult Dataclass."""

    def test_create_batch_result(self):
        """Sollte BatchReviewResult erstellen."""
        result = BatchReviewResult(
            total_processed=10,
            accepted=6,
            rejected=2,
            needs_human=2,
            errors=0,
            avg_quality_score=7.5,
            details=[{"sample_id": "test", "quality_score": 8.0}]
        )

        assert result.total_processed == 10
        assert result.accepted == 6
        assert result.rejected == 2
        assert result.needs_human == 2
        assert result.avg_quality_score == 7.5

    def test_batch_result_defaults(self):
        """Sollte BatchReviewResult mit Defaults erstellen."""
        result = BatchReviewResult()

        assert result.total_processed == 0
        assert result.accepted == 0
        assert result.details == []


class TestLLMOCRReviewServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_service(self):
        """Sollte Service korrekt initialisieren."""
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            service = LLMOCRReviewService()

            assert service.llm_service is not None

    def test_init_with_custom_llm_service(self):
        """Sollte Service mit benutzerdefiniertem LLM Service erstellen."""
        mock_llm = MagicMock()
        service = LLMOCRReviewService(llm_service=mock_llm)

        assert service.llm_service is mock_llm


class TestCircuitBreaker:
    """Tests fuer Circuit Breaker Pattern."""

    @pytest.fixture
    def service(self):
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            svc = LLMOCRReviewService()
            # Reset circuit breaker state
            svc.reset_circuit_breaker()
            return svc

    def test_circuit_starts_closed(self, service: LLMOCRReviewService):
        """Circuit sollte initial geschlossen sein."""
        status = service.get_circuit_status()

        assert status["circuit_state"] == "closed"
        assert status["failure_count"] == 0
        assert status["is_accepting_requests"] is True

    def test_circuit_opens_after_failures(self, service: LLMOCRReviewService):
        """Circuit sollte nach Fehlerschwelle oeffnen."""
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            service._record_failure()

        status = service.get_circuit_status()

        assert status["circuit_state"] == "open"
        assert status["failure_count"] == CIRCUIT_BREAKER_FAILURE_THRESHOLD
        assert status["is_accepting_requests"] is False

    def test_circuit_rejects_when_open(self, service: LLMOCRReviewService):
        """Offener Circuit sollte keine Anfragen akzeptieren."""
        # Oeffne Circuit
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            service._record_failure()

        assert service._check_circuit_breaker() is False

    def test_circuit_success_resets_failures(self, service: LLMOCRReviewService):
        """Erfolg sollte Fehlerz_ahler zuruecksetzen."""
        service._record_failure()
        service._record_failure()
        service._record_success()

        status = service.get_circuit_status()
        assert status["failure_count"] == 0

    def test_circuit_half_open_after_timeout(self, service: LLMOCRReviewService):
        """Circuit sollte nach Timeout zu Half-Open wechseln."""
        # Oeffne Circuit
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            service._record_failure()

        # Simuliere Timeout
        LLMOCRReviewService._last_failure_time = datetime.now(timezone.utc) - timedelta(
            seconds=CIRCUIT_BREAKER_RECOVERY_TIMEOUT + 1
        )

        # Sollte jetzt Anfragen akzeptieren (Half-Open)
        assert service._check_circuit_breaker() is True

        status = service.get_circuit_status()
        assert status["circuit_state"] == "half_open"

    def test_circuit_closes_after_successes(self, service: LLMOCRReviewService):
        """Circuit sollte nach Erfolgen in Half-Open schliessen."""
        # Bringe Circuit in Half-Open
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            service._record_failure()
        LLMOCRReviewService._last_failure_time = datetime.now(timezone.utc) - timedelta(
            seconds=CIRCUIT_BREAKER_RECOVERY_TIMEOUT + 1
        )
        service._check_circuit_breaker()  # Triggert Half-Open

        # Erfolge aufzeichnen
        for _ in range(CIRCUIT_BREAKER_SUCCESS_THRESHOLD):
            service._record_success()

        status = service.get_circuit_status()
        assert status["circuit_state"] == "closed"

    def test_reset_circuit_breaker(self, service: LLMOCRReviewService):
        """Reset sollte Circuit komplett zuruecksetzen."""
        # Oeffne Circuit
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            service._record_failure()

        service.reset_circuit_breaker()

        status = service.get_circuit_status()
        assert status["circuit_state"] == "closed"
        assert status["failure_count"] == 0


class TestParseResponse:
    """Tests fuer _parse_llm_response Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            return LLMOCRReviewService()

    def test_parse_complete_response(self, service: LLMOCRReviewService):
        """Sollte vollstaendige Antwort parsen."""
        response = """
        <quality_score>8</quality_score>
        <issues>
        - Keine OCR-Fehler gefunden
        </issues>
        <corrected_text>UNCHANGED</corrected_text>
        <recommendation>accept</recommendation>
        <reasoning>Der Text ist gut lesbar.</reasoning>
        """

        result = service._parse_llm_response(response)

        assert result.quality_score == 8.0
        assert result.recommendation == "accept"
        assert result.corrected_text is None  # UNCHANGED sollte None sein
        assert "Der Text ist gut lesbar" in result.reasoning

    def test_parse_response_with_correction(self, service: LLMOCRReviewService):
        """Sollte Antwort mit Korrektur parsen."""
        response = """
        <quality_score>7.5</quality_score>
        <issues>
        - Umlaut-Fehler: ae -> ae
        - Zeichenfehler: 0 -> O
        </issues>
        <corrected_text>Dies ist der korrigierte Text.</corrected_text>
        <recommendation>accept</recommendation>
        <reasoning>Nach Korrektur verwendbar.</reasoning>
        """

        result = service._parse_llm_response(response)

        assert result.quality_score == 7.5
        assert len(result.issues_found) == 2
        assert result.corrected_text == "Dies ist der korrigierte Text."

    def test_parse_response_reject(self, service: LLMOCRReviewService):
        """Sollte Ablehnung parsen."""
        response = """
        <quality_score>2</quality_score>
        <issues>
        - Text ist stark beschaedigt
        - Unleserliche Abschnitte
        </issues>
        <corrected_text>UNCHANGED</corrected_text>
        <recommendation>reject</recommendation>
        <reasoning>Text ist nicht verwendbar.</reasoning>
        """

        result = service._parse_llm_response(response)

        assert result.quality_score == 2.0
        assert result.recommendation == "reject"

    def test_parse_response_needs_human(self, service: LLMOCRReviewService):
        """Sollte needs_human parsen."""
        response = """
        <quality_score>5</quality_score>
        <issues>
        - Einige Fehler erkannt
        </issues>
        <corrected_text>UNCHANGED</corrected_text>
        <recommendation>needs_human</recommendation>
        <reasoning>Manuelle Pruefung erforderlich.</reasoning>
        """

        result = service._parse_llm_response(response)

        assert result.recommendation == "needs_human"

    def test_parse_invalid_quality_score(self, service: LLMOCRReviewService):
        """Sollte bei ungueltigem Score Default verwenden."""
        response = """
        <quality_score>15</quality_score>
        <recommendation>accept</recommendation>
        """

        result = service._parse_llm_response(response)

        # Score > 10 sollte ignoriert werden, Default ist 5.0
        assert result.quality_score == 5.0

    def test_parse_missing_tags(self, service: LLMOCRReviewService):
        """Sollte bei fehlenden Tags Defaults verwenden."""
        response = "Hier ist ein unstrukturierter Text ohne Tags."

        result = service._parse_llm_response(response)

        assert result.quality_score == 5.0  # Default
        assert result.recommendation == "needs_human"  # Default
        assert result.confidence < 0.8  # Niedrige Confidence


@pytest.mark.asyncio
class TestReviewSample:
    """Tests fuer review_sample Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            svc = LLMOCRReviewService()
            svc.reset_circuit_breaker()
            return svc

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.flush = AsyncMock()
        return db

    @pytest.fixture
    def sample_ocr_sample(self):
        sample = MagicMock()
        sample.id = uuid4()
        sample.ground_truth_text = "Dies ist ein Testtext mit mindestens 50 Zeichen fuer die Review."
        sample.document_type = "invoice"
        return sample

    async def test_review_sample_short_text(
        self, service: LLMOCRReviewService, mock_db, sample_ocr_sample
    ):
        """Sollte kurzen Text ablehnen."""
        sample_ocr_sample.ground_truth_text = "Zu kurz"

        result = await service.review_sample(mock_db, sample_ocr_sample)

        assert result.recommendation == "reject"
        assert result.quality_score == 0.0
        assert "zu kurz" in result.issues_found[0].lower()

    async def test_review_sample_circuit_open(
        self, service: LLMOCRReviewService, mock_db, sample_ocr_sample
    ):
        """Sollte bei offenem Circuit Fallback zurueckgeben."""
        # Oeffne Circuit
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            service._record_failure()

        result = await service.review_sample(mock_db, sample_ocr_sample)

        assert result.recommendation == "needs_human"
        assert "Circuit Breaker" in result.reasoning or result.confidence == 0.0

    async def test_review_sample_success(
        self, service: LLMOCRReviewService, mock_db, sample_ocr_sample
    ):
        """Sollte Sample erfolgreich reviewen."""
        with patch.object(
            service, '_call_llm_review', new_callable=AsyncMock
        ) as mock_review:
            mock_review.return_value = LLMReviewResult(
                quality_score=8.5,
                issues_found=[],
                recommendation="accept",
                reasoning="Gut lesbar.",
                confidence=0.9
            )

            result = await service.review_sample(mock_db, sample_ocr_sample)

            assert result.quality_score == 8.5
            assert result.recommendation == "accept"


@pytest.mark.asyncio
class TestReviewSampleById:
    """Tests fuer review_sample_by_id Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            return LLMOCRReviewService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        return db

    async def test_sample_not_found(self, service: LLMOCRReviewService, mock_db):
        """Sollte None zurueckgeben wenn Sample nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.review_sample_by_id(mock_db, uuid4())

        assert result is None

    async def test_sample_found_and_reviewed(
        self, service: LLMOCRReviewService, mock_db
    ):
        """Sollte Sample finden und reviewen."""
        sample = MagicMock()
        sample.id = uuid4()
        sample.ground_truth_text = "Testtext mit ausreichender Laenge fuer die Review."
        sample.document_type = "invoice"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, 'review_sample', new_callable=AsyncMock
        ) as mock_review:
            mock_review.return_value = LLMReviewResult(
                quality_score=7.0,
                issues_found=[],
                recommendation="accept",
                reasoning="OK"
            )

            result = await service.review_sample_by_id(mock_db, sample.id)

            assert result is not None
            mock_review.assert_called_once()


@pytest.mark.asyncio
class TestBatchReview:
    """Tests fuer batch_review Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            return LLMOCRReviewService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        return db

    async def test_batch_review_empty(self, service: LLMOCRReviewService, mock_db):
        """Sollte leeren Batch verarbeiten."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.batch_review(mock_db, max_samples=10)

        assert result.total_processed == 0
        assert result.accepted == 0

    async def test_batch_review_processes_samples(
        self, service: LLMOCRReviewService, mock_db
    ):
        """Sollte Samples im Batch verarbeiten."""
        samples = []
        for i in range(3):
            sample = MagicMock()
            sample.id = uuid4()
            sample.ground_truth_text = f"Testtext Nummer {i} mit ausreichender Laenge."
            sample.document_type = "invoice"
            samples.append(sample)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = samples
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, 'review_sample', new_callable=AsyncMock
        ) as mock_review:
            mock_review.return_value = LLMReviewResult(
                quality_score=8.0,
                issues_found=[],
                recommendation="accept",
                reasoning="OK"
            )

            result = await service.batch_review(mock_db, max_samples=10)

            assert result.total_processed == 3
            assert result.accepted == 3
            assert mock_review.call_count == 3


@pytest.mark.asyncio
class TestGetReviewStats:
    """Tests fuer get_review_stats Methode."""

    @pytest.fixture
    def service(self):
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            return LLMOCRReviewService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        return db

    async def test_get_stats_empty(self, service: LLMOCRReviewService, mock_db):
        """Sollte leere Statistiken zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        stats = await service.get_review_stats(mock_db)

        assert stats["total_samples"] == 0
        assert "by_recommendation" in stats


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_llm_ocr_review_service_singleton(self):
        """Sollte immer gleiche Instanz zurueckgeben."""
        # Reset singleton
        import app.services.llm_ocr_review_service as module
        module._llm_ocr_review_service = None

        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()

            svc1 = get_llm_ocr_review_service()
            svc2 = get_llm_ocr_review_service()

        assert svc1 is svc2


class TestTextValidation:
    """Tests fuer Text-Validierung."""

    @pytest.fixture
    def service(self):
        with patch('app.services.llm_ocr_review_service.get_llm_service') as mock_llm:
            mock_llm.return_value = MagicMock()
            return LLMOCRReviewService()

    def test_max_text_length(self, service: LLMOCRReviewService):
        """Sollte maximale Textlaenge respektieren."""
        assert service.MAX_TEXT_LENGTH == 8000

    def test_min_text_length(self, service: LLMOCRReviewService):
        """Sollte minimale Textlaenge respektieren."""
        assert service.MIN_TEXT_LENGTH == 20
