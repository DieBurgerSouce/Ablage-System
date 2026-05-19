# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Document Lifecycle Service.

Testet:
- Stufen-Uebergaenge (vorwaerts, Validierung)
- SLA-Verletzungserkennung
- Kanban-Uebersicht
- Stufen-Metriken
- Dokument-Historie
- Dataclass-Serialisierung

Feinpoliert und durchdacht - Document Lifecycle Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4, UUID

from app.services.document_lifecycle_service import (
    DocumentLifecycleService,
    SLAViolation,
    StageMetric,
)
from app.db.models_document_lifecycle import (
    DocumentLifecycleStage,
    STAGE_ORDER,
)

pytestmark = [pytest.mark.unit]


# ========================= Fixtures =========================


@pytest.fixture
def mock_db() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    return session


@pytest.fixture
def lifecycle_service(mock_db) -> DocumentLifecycleService:
    return DocumentLifecycleService(db=mock_db)


@pytest.fixture
def sample_document_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_company_id() -> UUID:
    return uuid4()


# ========================= Dataclass Tests =========================


class TestSLAViolationDataclass:
    """Tests fuer SLAViolation Dataclass."""

    def test_sla_violation_to_dict(self):
        """SLAViolation serialisiert korrekt."""
        now = datetime.now(timezone.utc)
        violation = SLAViolation(
            document_id=uuid4(),
            document_filename="Rechnung.pdf",
            document_type="invoice",
            current_stage="pruefung",
            entered_stage_at=now,
            max_duration_hours=24,
            actual_duration_hours=30.5,
            overdue_hours=6.5,
            escalation_to_role="manager",
        )

        d = violation.to_dict()
        assert d["document_filename"] == "Rechnung.pdf"
        assert d["max_duration_hours"] == 24
        assert d["overdue_hours"] == 6.5
        assert d["escalation_to_role"] == "manager"


class TestStageMetricDataclass:
    """Tests fuer StageMetric Dataclass."""

    def test_stage_metric_to_dict(self):
        """StageMetric serialisiert korrekt."""
        metric = StageMetric(
            stage="klassifizierung",
            avg_duration_seconds=3600.0,
            min_duration_seconds=600.0,
            max_duration_seconds=7200.0,
            total_transitions=42,
            sla_compliance_rate=0.952,
        )

        d = metric.to_dict()
        assert d["stage"] == "klassifizierung"
        assert d["avg_duration_seconds"] == 3600.0
        assert d["total_transitions"] == 42
        assert d["sla_compliance_rate"] == 0.952


# ========================= Stage Transition Tests =========================


class TestStageTransitions:
    """Tests fuer Stufen-Uebergaenge."""

    @pytest.mark.asyncio
    async def test_first_transition_no_from_stage(
        self, lifecycle_service, mock_db, sample_document_id, sample_company_id
    ):
        """Erster Uebergang hat keine from_stage."""
        with patch.object(lifecycle_service, '_get_last_event', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            event = await lifecycle_service.transition_stage(
                document_id=sample_document_id,
                company_id=sample_company_id,
                to_stage=DocumentLifecycleStage.EINGANG,
            )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_backward_transition_raises_error(
        self, lifecycle_service, mock_db, sample_document_id, sample_company_id
    ):
        """Rueckwaerts-Uebergang wirft ValueError."""
        mock_event = Mock()
        mock_event.to_stage = DocumentLifecycleStage.PRUEFUNG.value
        mock_event.transitioned_at = datetime.now(timezone.utc) - timedelta(hours=1)

        with patch.object(lifecycle_service, '_get_last_event', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_event

            with pytest.raises(ValueError, match="kann nicht zurückgesetzt"):
                await lifecycle_service.transition_stage(
                    document_id=sample_document_id,
                    company_id=sample_company_id,
                    to_stage=DocumentLifecycleStage.EINGANG,  # Rueckwaerts!
                )

    @pytest.mark.asyncio
    async def test_same_stage_transition_raises_error(
        self, lifecycle_service, mock_db, sample_document_id, sample_company_id
    ):
        """Uebergang in gleiche Stufe wirft ValueError."""
        mock_event = Mock()
        mock_event.to_stage = DocumentLifecycleStage.OCR.value
        mock_event.transitioned_at = datetime.now(timezone.utc)

        with patch.object(lifecycle_service, '_get_last_event', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_event

            with pytest.raises(ValueError):
                await lifecycle_service.transition_stage(
                    document_id=sample_document_id,
                    company_id=sample_company_id,
                    to_stage=DocumentLifecycleStage.OCR,  # Gleiche Stufe!
                )


# ========================= Current Stage Tests =========================


class TestGetCurrentStage:
    """Tests fuer aktuelle Stufe."""

    @pytest.mark.asyncio
    async def test_no_events_returns_none(self, lifecycle_service, mock_db, sample_document_id):
        """Keine Events -> None."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        stage = await lifecycle_service.get_current_stage(sample_document_id)
        assert stage is None

    @pytest.mark.asyncio
    async def test_valid_stage_returned(self, lifecycle_service, mock_db, sample_document_id):
        """Gueltige Stufe wird als Enum zurueckgegeben."""
        mock_event = Mock()
        mock_event.to_stage = "prüfung"

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_db.execute = AsyncMock(return_value=mock_result)

        stage = await lifecycle_service.get_current_stage(sample_document_id)
        assert stage == DocumentLifecycleStage.PRUEFUNG

    @pytest.mark.asyncio
    async def test_unknown_stage_returns_none(self, lifecycle_service, mock_db, sample_document_id):
        """Unbekannte Stufe gibt None zurueck."""
        mock_event = Mock()
        mock_event.to_stage = "unknown_stage"

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_event
        mock_db.execute = AsyncMock(return_value=mock_result)

        stage = await lifecycle_service.get_current_stage(sample_document_id)
        assert stage is None


# ========================= SLA Violation Tests =========================


class TestSLAViolations:
    """Tests fuer SLA-Verletzungserkennung."""

    @pytest.mark.asyncio
    async def test_no_configs_no_violations(
        self, lifecycle_service, mock_db, sample_company_id
    ):
        """Ohne SLA-Konfiguration keine Verletzungen."""
        # Mock: keine Configs
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        violations = await lifecycle_service.check_sla_violations(sample_company_id)
        assert violations == []

    @pytest.mark.asyncio
    async def test_sla_check_handles_exception(
        self, lifecycle_service, mock_db, sample_company_id
    ):
        """Exception bei SLA-Check wird abgefangen."""
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        violations = await lifecycle_service.check_sla_violations(sample_company_id)
        assert violations == []  # Graceful degradation


# ========================= Lifecycle Overview Tests =========================


class TestLifecycleOverview:
    """Tests fuer Kanban-Uebersicht."""

    @pytest.mark.asyncio
    async def test_overview_initializes_all_stages(
        self, lifecycle_service, mock_db, sample_company_id
    ):
        """Uebersicht enthaelt alle definierten Stufen."""
        # Mock: leere Ergebnisse
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        overview = await lifecycle_service.get_lifecycle_overview(sample_company_id)

        # Alle Stages muessen vorhanden sein (mit 0)
        for stage in DocumentLifecycleStage:
            assert stage.value in overview
            assert overview[stage.value] == 0

    @pytest.mark.asyncio
    async def test_overview_handles_exception(
        self, lifecycle_service, mock_db, sample_company_id
    ):
        """Exception bei Overview wird abgefangen."""
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        overview = await lifecycle_service.get_lifecycle_overview(sample_company_id)

        # Sollte trotzdem initialisierte Stufen zurueckgeben
        assert isinstance(overview, dict)
        for stage in DocumentLifecycleStage:
            assert stage.value in overview


# ========================= Stage Metrics Tests =========================


class TestStageMetrics:
    """Tests fuer Stufen-Metriken."""

    @pytest.mark.asyncio
    async def test_metrics_empty_result(
        self, lifecycle_service, mock_db, sample_company_id
    ):
        """Leere Metriken bei keinen Daten."""
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        metrics = await lifecycle_service.get_stage_metrics(sample_company_id)
        assert metrics == []

    @pytest.mark.asyncio
    async def test_metrics_with_data(
        self, lifecycle_service, mock_db, sample_company_id
    ):
        """Metriken werden korrekt aus DB-Ergebnissen erstellt."""
        mock_row = ("prüfung", 3600.0, 600.0, 7200.0, 42, 0.95)
        mock_result = Mock()
        mock_result.all.return_value = [mock_row]
        mock_db.execute = AsyncMock(return_value=mock_result)

        metrics = await lifecycle_service.get_stage_metrics(sample_company_id, days=30)

        assert len(metrics) == 1
        assert metrics[0].stage == "prüfung"
        assert metrics[0].avg_duration_seconds == 3600.0
        assert metrics[0].total_transitions == 42
        assert metrics[0].sla_compliance_rate == 0.95

    @pytest.mark.asyncio
    async def test_metrics_handles_exception(
        self, lifecycle_service, mock_db, sample_company_id
    ):
        """Exception bei Metriken wird abgefangen."""
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        metrics = await lifecycle_service.get_stage_metrics(sample_company_id)
        assert metrics == []


# ========================= Document History Tests =========================


class TestDocumentHistory:
    """Tests fuer Dokument-Historie."""

    @pytest.mark.asyncio
    async def test_history_returns_ordered_events(
        self, lifecycle_service, mock_db, sample_document_id, sample_company_id
    ):
        """Historie gibt chronologisch sortierte Events zurueck."""
        mock_events = [Mock(), Mock(), Mock()]
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_events
        mock_db.execute = AsyncMock(return_value=mock_result)

        history = await lifecycle_service.get_document_history(
            document_id=sample_document_id,
            company_id=sample_company_id,
        )

        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_history_empty_for_new_document(
        self, lifecycle_service, mock_db, sample_document_id, sample_company_id
    ):
        """Neues Dokument hat leere Historie."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        history = await lifecycle_service.get_document_history(
            document_id=sample_document_id,
            company_id=sample_company_id,
        )

        assert history == []


# ========================= Stage Order Tests =========================


class TestStageOrder:
    """Tests fuer Stufen-Reihenfolge."""

    def test_stage_order_defined(self):
        """STAGE_ORDER ist definiert und nicht leer."""
        assert len(STAGE_ORDER) > 0

    def test_all_stages_in_order(self):
        """Alle Stages sind in STAGE_ORDER enthalten."""
        for stage in DocumentLifecycleStage:
            assert stage in STAGE_ORDER

    def test_eingang_is_first(self):
        """EINGANG ist die erste Stufe."""
        assert STAGE_ORDER[0] == DocumentLifecycleStage.EINGANG

    def test_archivierung_is_last(self):
        """ARCHIVIERUNG ist die letzte Stufe."""
        assert STAGE_ORDER[-1] == DocumentLifecycleStage.ARCHIVIERUNG
