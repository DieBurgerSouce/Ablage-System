# -*- coding: utf-8 -*-
"""
Tests fuer Invoice Pipeline Service.

Testet vollautomatischen Rechnungsworkflow:
- OCR-Qualitaetspruefung
- Entity-Linking
- Dokument-Kategorisierung
- Auto-Approval
- Zahlungsfreigabe
- Eskalation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import Optional

from app.services.invoice_pipeline_service import (
    InvoicePipelineService,
    PipelineResult,
    PipelineStats,
    PipelineStage,
    PipelineStatus,
    DEFAULT_OCR_CONFIDENCE_THRESHOLD,
    get_invoice_pipeline_service,
)
from app.services.approval.auto_approval_service import (
    AutoApprovalDecision,
    AutoApprovalConfig,
)
from app.services.document_entity_linker_service import LinkingResult
from app.services.ai.autonomous_actions_service import AutonomyConfig


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalars = MagicMock()
    mock_result.scalars.return_value.all = MagicMock(return_value=[])
    db.execute = AsyncMock(return_value=mock_result)
    return db


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Test User-ID."""
    return uuid4()


@pytest.fixture
def document_id():
    """Test Document-ID."""
    return uuid4()


@pytest.fixture
def mock_document(company_id):
    """Mock Document-Objekt."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.company_id = company_id
    doc.entity_id = None
    doc.category = None
    doc.ocr_confidence = 0.95
    doc.extracted_data = {"ocr_confidence": 0.95, "invoice": "Rechnung Nr. 12345"}
    doc.ocr_text = "Rechnung Nr. 12345"
    return doc


@pytest.fixture
def mock_approval_result():
    """Mock AutoApprovalResult."""
    result = MagicMock()
    result.decision = AutoApprovalDecision.AUTO_APPROVED
    result.reasons = ["Betrag unter Limit", "Bekannter Lieferant"]
    result.matched_rules = ["rule_1", "rule_2"]
    result.confidence = 0.95
    result.explanation = "Automatisch genehmigt - alle Kriterien erfuellt"
    result.approval_id = None
    result.approved_at = None
    result.approved_by_rule = "rule_1"
    result.escalation_reason = None
    result.suggested_approvers = None
    result.audit_trail = []
    return result


@pytest.fixture
def mock_linking_result():
    """Mock LinkingResult."""
    return LinkingResult(
        linked_count=1,
        unlinked_count=0,
        low_confidence_count=0,
        error_count=0,
        already_linked_count=0,
        details=[{"document_id": str(uuid4()), "confidence": 0.92}],
    )


@pytest.fixture
def service(mock_db, company_id):
    """InvoicePipelineService Instanz mit gemockten Sub-Services."""
    service = InvoicePipelineService(db=mock_db, company_id=company_id)

    # Mock sub-services
    service.auto_approval_service = MagicMock()
    service.entity_linker = MagicMock()
    service.autonomous_actions = MagicMock()

    return service


# =============================================================================
# process_invoice Tests
# =============================================================================


class TestProcessInvoice:
    """Tests fuer process_invoice Methode."""

    @pytest.mark.asyncio
    async def test_document_not_found_returns_failed(
        self,
        service,
        document_id,
    ):
        """Test: Nicht gefundenes Dokument gibt FAILED zurueck."""
        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = None

            result = await service.process_invoice(document_id)

            assert result.status == PipelineStatus.FAILED
            assert result.stage == PipelineStage.OCR_COMPLETE
            assert result.document_id == document_id
            assert result.error_message == "Dokument nicht gefunden"
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_company_id_mismatch_returns_failed(
        self,
        service,
        mock_document,
        document_id,
    ):
        """Test: Company-ID-Konflikt gibt FAILED zurueck."""
        # Anderes company_id setzen
        mock_document.company_id = uuid4()

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = mock_document

            result = await service.process_invoice(document_id)

            assert result.status == PipelineStatus.FAILED
            assert result.error_message == "Keine Berechtigung fuer dieses Dokument"
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_low_ocr_quality_returns_needs_review(
        self,
        service,
        mock_document,
        document_id,
    ):
        """Test: Niedrige OCR-Qualitaet gibt NEEDS_REVIEW zurueck."""
        mock_document.ocr_confidence = 0.5
        mock_document.extracted_data = {"ocr_confidence": 0.5}

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = mock_document

            result = await service.process_invoice(document_id)

            assert result.status == PipelineStatus.NEEDS_REVIEW
            assert result.stage == PipelineStage.OCR_COMPLETE
            assert result.confidence < DEFAULT_OCR_CONFIDENCE_THRESHOLD
            assert "OCR-Qualitaet zu niedrig" in result.actions_taken[0]
            assert result.next_action == "Manuelle OCR-Korrektur erforderlich"

    @pytest.mark.asyncio
    async def test_successful_auto_approval_returns_success(
        self,
        service,
        mock_document,
        mock_approval_result,
        document_id,
    ):
        """Test: Erfolgreiche Auto-Genehmigung gibt SUCCESS zurueck."""
        mock_approval_result.decision = AutoApprovalDecision.AUTO_APPROVED

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            with patch.object(service, '_check_auto_approval', new_callable=AsyncMock) as mock_approval:
                with patch.object(service, '_mark_as_approved', new_callable=AsyncMock):
                    with patch.object(service, '_mark_payment_ready', new_callable=AsyncMock):
                        mock_load.return_value = mock_document
                        mock_approval.return_value = mock_approval_result

                        result = await service.process_invoice(document_id)

                        assert result.status == PipelineStatus.SUCCESS
                        assert result.stage == PipelineStage.PAYMENT_READY
                        assert result.confidence == mock_approval_result.confidence
                        assert "Automatisch genehmigt" in result.actions_taken[-2]
                        assert "Als zahlungsbereit markiert" in result.actions_taken[-1]
                        assert result.next_action == "Zahlung kann durchgefuehrt werden"
                        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_requires_review_returns_needs_review(
        self,
        service,
        mock_document,
        mock_approval_result,
        document_id,
    ):
        """Test: Manuelle Pruefung erforderlich gibt NEEDS_REVIEW zurueck."""
        mock_approval_result.decision = AutoApprovalDecision.REQUIRES_REVIEW
        mock_approval_result.suggested_approvers = ["user1@example.com", "user2@example.com"]

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            with patch.object(service, '_check_auto_approval', new_callable=AsyncMock) as mock_approval:
                mock_load.return_value = mock_document
                mock_approval.return_value = mock_approval_result

                result = await service.process_invoice(document_id)

                assert result.status == PipelineStatus.NEEDS_REVIEW
                assert result.stage == PipelineStage.APPROVED
                assert "Manuelle Pruefung erforderlich" in result.actions_taken[-1]
                assert result.next_action == "Manuelle Genehmigung durch Approver erforderlich"
                assert "suggested_approvers" in result.metadata
                assert len(result.metadata["suggested_approvers"]) == 2

    @pytest.mark.asyncio
    async def test_escalation_returns_escalated(
        self,
        service,
        mock_document,
        mock_approval_result,
        document_id,
    ):
        """Test: Eskalation gibt ESCALATED zurueck."""
        mock_approval_result.decision = AutoApprovalDecision.ESCALATE
        mock_approval_result.escalation_reason = "Betrag zu hoch"

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            with patch.object(service, '_check_auto_approval', new_callable=AsyncMock) as mock_approval:
                with patch.object(service, '_escalate_document', new_callable=AsyncMock):
                    mock_load.return_value = mock_document
                    mock_approval.return_value = mock_approval_result

                    result = await service.process_invoice(document_id)

                    assert result.status == PipelineStatus.ESCALATED
                    assert result.stage == PipelineStage.ESCALATED
                    assert "Eskaliert" in result.actions_taken[-1]
                    assert result.next_action == "Admin-Review erforderlich"
                    assert result.metadata["escalation_reason"] == "Betrag zu hoch"

    @pytest.mark.asyncio
    async def test_entity_linking_succeeds(
        self,
        service,
        mock_document,
        mock_approval_result,
        mock_linking_result,
        document_id,
    ):
        """Test: Entity-Linking wird erfolgreich durchgefuehrt."""
        mock_document.entity_id = None  # Kein Entity verknuepft
        mock_approval_result.decision = AutoApprovalDecision.AUTO_APPROVED

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            with patch.object(service, '_perform_entity_linking', new_callable=AsyncMock) as mock_linking:
                with patch.object(service, '_check_auto_approval', new_callable=AsyncMock) as mock_approval:
                    with patch.object(service, '_mark_as_approved', new_callable=AsyncMock):
                        with patch.object(service, '_mark_payment_ready', new_callable=AsyncMock):
                            mock_load.return_value = mock_document
                            mock_linking.return_value = mock_linking_result
                            mock_approval.return_value = mock_approval_result

                            result = await service.process_invoice(document_id)

                            # Pruefe dass Entity-Linking ausgefuehrt wurde
                            mock_linking.assert_called_once_with(mock_document)
                            # Pruefe dass in actions_taken erwahnt
                            assert any("Entity automatisch verknuepft" in action for action in result.actions_taken)

    @pytest.mark.asyncio
    async def test_entity_linking_fails_gracefully(
        self,
        service,
        mock_document,
        mock_approval_result,
        document_id,
    ):
        """Test: Fehlgeschlagenes Entity-Linking verhindert Pipeline nicht."""
        mock_document.entity_id = None
        mock_approval_result.decision = AutoApprovalDecision.AUTO_APPROVED

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            with patch.object(service, '_perform_entity_linking', new_callable=AsyncMock) as mock_linking:
                with patch.object(service, '_check_auto_approval', new_callable=AsyncMock) as mock_approval:
                    with patch.object(service, '_mark_as_approved', new_callable=AsyncMock):
                        with patch.object(service, '_mark_payment_ready', new_callable=AsyncMock):
                            mock_load.return_value = mock_document
                            mock_linking.return_value = None  # Linking fehlgeschlagen
                            mock_approval.return_value = mock_approval_result

                            result = await service.process_invoice(document_id)

                            # Pipeline sollte trotzdem erfolgreich sein
                            assert result.status == PipelineStatus.SUCCESS
                            # Fehlgeschlagenes Linking sollte erwähnt werden
                            assert any("Keine passende Entity gefunden" in action for action in result.actions_taken)

    @pytest.mark.asyncio
    async def test_actions_taken_list_populated(
        self,
        service,
        mock_document,
        mock_approval_result,
        document_id,
    ):
        """Test: actions_taken Liste wird korrekt gefuellt."""
        mock_approval_result.decision = AutoApprovalDecision.AUTO_APPROVED

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            with patch.object(service, '_check_auto_approval', new_callable=AsyncMock) as mock_approval:
                with patch.object(service, '_mark_as_approved', new_callable=AsyncMock):
                    with patch.object(service, '_mark_payment_ready', new_callable=AsyncMock):
                        mock_load.return_value = mock_document
                        mock_approval.return_value = mock_approval_result

                        result = await service.process_invoice(document_id)

                        # Mindestens 3 Actions: OCR validiert, Genehmigt, Zahlungsbereit
                        assert len(result.actions_taken) >= 3
                        assert "OCR-Qualitaet validiert" in result.actions_taken[0]
                        assert isinstance(result.actions_taken, list)
                        # Alle actions sollten deutsche Strings sein
                        for action in result.actions_taken:
                            assert isinstance(action, str)
                            assert len(action) > 0

    @pytest.mark.asyncio
    async def test_user_id_passed_through_for_audit(
        self,
        service,
        mock_document,
        mock_approval_result,
        document_id,
        user_id,
    ):
        """Test: user_id wird fuer Audit-Trail weitergegeben."""
        mock_approval_result.decision = AutoApprovalDecision.AUTO_APPROVED

        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            with patch.object(service, '_check_auto_approval', new_callable=AsyncMock) as mock_approval:
                with patch.object(service, '_mark_as_approved', new_callable=AsyncMock) as mock_mark_approved:
                    with patch.object(service, '_mark_payment_ready', new_callable=AsyncMock):
                        mock_load.return_value = mock_document
                        mock_approval.return_value = mock_approval_result

                        result = await service.process_invoice(document_id, user_id=user_id)

                        # Pruefe dass user_id an _mark_as_approved uebergeben wurde
                        mock_mark_approved.assert_called_once()
                        call_args = mock_mark_approved.call_args
                        assert call_args[0][2] == user_id  # Drittes Argument ist user_id

    @pytest.mark.asyncio
    async def test_exception_handling_returns_failed(
        self,
        service,
        document_id,
    ):
        """Test: Exceptions werden korrekt behandelt und geben FAILED zurueck."""
        with patch.object(service, '_load_document', new_callable=AsyncMock) as mock_load:
            mock_load.side_effect = Exception("Database connection failed")

            result = await service.process_invoice(document_id)

            assert result.status == PipelineStatus.FAILED
            assert result.stage == PipelineStage.OCR_COMPLETE
            assert "Pipeline-Fehler" in result.error_message
            assert result.confidence == 0.0
            assert result.processing_time_ms >= 0  # Can be 0 for very fast failures


# =============================================================================
# PipelineResult und PipelineStats Tests
# =============================================================================


class TestDataStructures:
    """Tests fuer Datenstrukturen."""

    def test_pipeline_result_structure(self, document_id):
        """Test: PipelineResult hat korrekte Struktur."""
        result = PipelineResult(
            document_id=document_id,
            stage=PipelineStage.PAYMENT_READY,
            status=PipelineStatus.SUCCESS,
            confidence=0.95,
            actions_taken=["Action 1", "Action 2"],
            next_action="Next step",
            processing_time_ms=1500,
            error_message=None,
            metadata={"key": "value"},
        )

        assert result.document_id == document_id
        assert result.stage == PipelineStage.PAYMENT_READY
        assert result.status == PipelineStatus.SUCCESS
        assert result.confidence == 0.95
        assert len(result.actions_taken) == 2
        assert result.next_action == "Next step"
        assert result.processing_time_ms == 1500
        assert result.error_message is None
        assert result.metadata["key"] == "value"

    def test_pipeline_stats_structure(self):
        """Test: PipelineStats hat korrekte Struktur."""
        stats = PipelineStats(
            total_processed=100,
            successful=80,
            needs_review=15,
            failed=3,
            escalated=2,
            avg_processing_time_ms=1250.5,
            auto_approval_rate=75.0,
            entity_linking_rate=90.0,
            avg_confidence=0.88,
        )

        assert stats.total_processed == 100
        assert stats.successful == 80
        assert stats.needs_review == 15
        assert stats.failed == 3
        assert stats.escalated == 2
        assert stats.avg_processing_time_ms == 1250.5
        assert stats.auto_approval_rate == 75.0
        assert stats.entity_linking_rate == 90.0
        assert stats.avg_confidence == 0.88

    def test_pipeline_stats_default_zeros(self):
        """Test: PipelineStats Standardwerte sind Null."""
        stats = PipelineStats(
            total_processed=0,
            successful=0,
            needs_review=0,
            failed=0,
            escalated=0,
            avg_processing_time_ms=0.0,
            auto_approval_rate=0.0,
            entity_linking_rate=0.0,
            avg_confidence=0.0,
        )

        assert stats.total_processed == 0
        assert stats.successful == 0
        assert stats.avg_processing_time_ms == 0.0
        assert stats.auto_approval_rate == 0.0


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Tests fuer Enums."""

    def test_pipeline_stage_values(self):
        """Test: PipelineStage Enum-Werte sind korrekt."""
        assert PipelineStage.OCR_COMPLETE == "ocr_complete"
        assert PipelineStage.ENTITY_LINKED == "entity_linked"
        assert PipelineStage.CATEGORIZED == "categorized"
        assert PipelineStage.APPROVED == "approved"
        assert PipelineStage.PAYMENT_READY == "payment_ready"
        assert PipelineStage.ESCALATED == "escalated"

    def test_pipeline_status_values(self):
        """Test: PipelineStatus Enum-Werte sind korrekt."""
        assert PipelineStatus.SUCCESS == "success"
        assert PipelineStatus.NEEDS_REVIEW == "needs_review"
        assert PipelineStatus.FAILED == "failed"
        assert PipelineStatus.ESCALATED == "escalated"


# =============================================================================
# Service Initialization Tests
# =============================================================================


class TestServiceInitialization:
    """Tests fuer Service-Initialisierung."""

    def test_service_initialization_with_configs(self, mock_db, company_id):
        """Test: Service kann mit Konfigurationen initialisiert werden."""
        from decimal import Decimal

        auto_approval_config = AutoApprovalConfig(
            default_max_amount=Decimal("10000.0"),
            default_max_risk_score=50,
            default_min_relationship_months=3,
            enable_amount_based_approval=True,
            enable_trusted_supplier_approval=True,
        )
        autonomy_config = AutonomyConfig(
            invoice_approval_threshold=0.9,
            document_classification_threshold=0.85,
            entity_linking_threshold=0.88,
            payment_auto_approve_limit=Decimal("5000.00"),
            auto_approval_enabled=True,
        )

        service = InvoicePipelineService(
            db=mock_db,
            company_id=company_id,
            auto_approval_config=auto_approval_config,
            autonomy_config=autonomy_config,
        )

        assert service.db == mock_db
        assert service.company_id == company_id
        assert service.auto_approval_service is not None
        assert service.entity_linker is not None
        assert service.autonomous_actions is not None

    def test_factory_function_returns_service(self, mock_db, company_id):
        """Test: Factory-Funktion gibt Service zurueck."""
        service = get_invoice_pipeline_service(db=mock_db, company_id=company_id)

        assert isinstance(service, InvoicePipelineService)
        assert service.db == mock_db
        assert service.company_id == company_id


# =============================================================================
# Konstanten Tests
# =============================================================================


class TestConstants:
    """Tests fuer Konstanten."""

    def test_default_ocr_confidence_threshold(self):
        """Test: DEFAULT_OCR_CONFIDENCE_THRESHOLD ist 0.85."""
        assert DEFAULT_OCR_CONFIDENCE_THRESHOLD == 0.85
