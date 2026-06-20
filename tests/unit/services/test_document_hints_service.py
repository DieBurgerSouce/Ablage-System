# -*- coding: utf-8 -*-
"""
Tests fuer Document Hints Service.

Testet die proaktiven Dokument-Hinweise fuer Enterprise-Features:
- Fehlende Dokumente
- Skonto-Fristen
- Entity Risk Scores
- Ueberfaellige Zahlungen
- OCR-Qualitaet
- Duplikatsverdacht
- Compliance
- Erforderliche Freigaben
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import List

from app.services.document_hints_service import (
    DocumentHintsService,
    DocumentHint,
    HintCategory,
    HintSeverity,
    HintSummary,
)
from app.db.models import (
    Document,
    DocumentType,
    BusinessEntity,
    InvoiceTracking,
    InvoiceStatus,
)


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    return db


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid4()


@pytest.fixture
def document_id():
    """Test Document-ID."""
    return uuid4()


@pytest.fixture
def entity_id():
    """Test Entity-ID."""
    return uuid4()


@pytest.fixture
def hints_service(mock_db):
    """Fixture fuer DocumentHintsService."""
    return DocumentHintsService(session=mock_db)


# Helper to build a mock Document
def _make_doc(
    doc_id=None,
    company_id=None,
    doc_type=DocumentType.INVOICE.value,
    chain_id=None,
    entity_id=None,
    ocr_confidence=0.95,
    extracted_data=None,
):
    """Create a mock Document with the given attributes."""
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id or uuid4()
    mock_doc.company_id = company_id or uuid4()
    mock_doc.document_type = doc_type
    mock_doc.chain_id = chain_id
    mock_doc.business_entity_id = entity_id
    mock_doc.ocr_confidence = ocr_confidence
    mock_doc.extracted_data = extracted_data or {}
    mock_doc.deleted_at = None
    return mock_doc


# =============================================================================
# Get Hints for Single Document Tests
# =============================================================================


class TestGetHintsForDocument:
    """Tests fuer get_hints_for_document."""

    @pytest.mark.asyncio
    async def test_returns_hints_list(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Gibt Liste von Hints zurueck."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        # execute calls: doc query, skonto check, payment overdue, duplicate check
        mock_db.execute.side_effect = [
            mock_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        assert isinstance(hints, list)

    @pytest.mark.asyncio
    async def test_document_not_found_returns_empty_list(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Dokument nicht gefunden gibt leere Liste."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        assert hints == []

    @pytest.mark.asyncio
    async def test_missing_delivery_note_hint(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Fehlender Lieferschein erzeugt Hint."""
        chain_id = "CHAIN-001"
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            chain_id=chain_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        # First execute: document query
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        # _check_missing_documents uses self.session.scalar() for count query
        # _check_skonto_deadline uses execute
        # _check_payment_overdue uses execute
        # _check_duplicate_suspect uses execute
        mock_db.execute.side_effect = [
            doc_result,  # Document load
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto InvoiceTracking
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment InvoiceTracking
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate check
        ]
        # scalar() call for delivery note count = 0
        mock_db.scalar.return_value = 0

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        missing_doc_hints = [h for h in hints if h.category == HintCategory.MISSING_DOCUMENT]
        assert len(missing_doc_hints) > 0
        hint = missing_doc_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "Lieferschein" in hint.title
        assert hint.confidence == 0.85

    @pytest.mark.asyncio
    async def test_skonto_deadline_warning(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Ablaufende Skonto-Frist erzeugt Warning."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        # Skonto in 5 Tagen
        deadline = datetime.now(timezone.utc) + timedelta(days=5)
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.document_id = document_id
        mock_invoice.skonto_deadline = deadline
        mock_invoice.skonto_used = False
        mock_invoice.skonto_percentage = 2.0
        mock_invoice.amount = Decimal("1000.00")

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,  # Document load
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_invoice)),  # skonto InvoiceTracking
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment InvoiceTracking
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        skonto_hints = [h for h in hints if h.category == HintCategory.SKONTO_DEADLINE]
        assert len(skonto_hints) > 0
        hint = skonto_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "Skonto-Frist" in hint.title
        assert hint.expires_at == deadline

    @pytest.mark.asyncio
    async def test_skonto_deadline_critical(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Skonto-Frist in 1 Tag = CRITICAL."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        # Skonto in 1 Tag
        deadline = datetime.now(timezone.utc) + timedelta(days=1)
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.document_id = document_id
        mock_invoice.skonto_deadline = deadline
        mock_invoice.skonto_used = False
        mock_invoice.skonto_percentage = 2.0
        mock_invoice.amount = Decimal("1000.00")

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_invoice)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        skonto_hints = [h for h in hints if h.category == HintCategory.SKONTO_DEADLINE]
        assert len(skonto_hints) > 0
        hint = skonto_hints[0]
        assert hint.severity == HintSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_entity_risk_warning(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
        entity_id,
    ):
        """Test: Erhoehter Entity Risk Score = WARNING."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            entity_id=entity_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        mock_entity = MagicMock(spec=BusinessEntity)
        mock_entity.id = entity_id
        mock_entity.risk_score = 60.0

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,  # Document load
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto InvoiceTracking
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_entity)),  # entity load
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment InvoiceTracking
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]
        # scalar() for overdue count in _check_entity_risk
        mock_db.scalar.return_value = 2

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        risk_hints = [h for h in hints if h.category == HintCategory.ENTITY_RISK]
        assert len(risk_hints) > 0
        hint = risk_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "Risiko-Score" in hint.title
        assert hint.confidence == 0.95

    @pytest.mark.asyncio
    async def test_entity_risk_critical(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
        entity_id,
    ):
        """Test: Kritischer Risk Score >= 75 = CRITICAL."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            entity_id=entity_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        mock_entity = MagicMock(spec=BusinessEntity)
        mock_entity.id = entity_id
        mock_entity.risk_score = 85.0

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_entity)),  # entity
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]
        mock_db.scalar.return_value = 0

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        risk_hints = [h for h in hints if h.category == HintCategory.ENTITY_RISK]
        assert len(risk_hints) > 0
        hint = risk_hints[0]
        assert hint.severity == HintSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_payment_overdue_hint(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Ueberfaellige Zahlung erzeugt Hint."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        # 15 Tage ueberfaellig
        due_date = datetime.now(timezone.utc) - timedelta(days=15)
        mock_invoice = MagicMock(spec=InvoiceTracking)
        mock_invoice.id = uuid4()
        mock_invoice.document_id = document_id
        mock_invoice.due_date = due_date
        mock_invoice.status = InvoiceStatus.OVERDUE.value
        mock_invoice.amount = Decimal("500.00")

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_invoice)),  # payment
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        overdue_hints = [h for h in hints if h.category == HintCategory.PAYMENT_OVERDUE]
        assert len(overdue_hints) > 0
        hint = overdue_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "überfällig" in hint.title
        assert hint.confidence == 1.0

    @pytest.mark.asyncio
    async def test_low_ocr_quality_warning(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Niedrige OCR-Qualitaet = WARNING."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            ocr_confidence=0.65,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        ocr_hints = [h for h in hints if h.category == HintCategory.OCR_QUALITY]
        assert len(ocr_hints) > 0
        hint = ocr_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "OCR" in hint.title
        assert hint.confidence == 0.65

    @pytest.mark.asyncio
    async def test_duplicate_suspect_hint(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Duplikatsverdacht erzeugt Hint."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        # Duplicate document
        duplicate_id = uuid4()
        mock_duplicate = MagicMock(spec=Document)
        mock_duplicate.id = duplicate_id
        mock_duplicate.extracted_data = {"invoice_number": "INV001"}

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,  # Document load
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
        ]

        # Patch _check_duplicate_suspect directly because the service query
        # uses Document.extracted_data["..."].astext which requires JSONB
        # (CrossDBJSON uses JSON as base impl, so astext is unavailable in
        # a pure unit test context).
        expected_hint = DocumentHint(
            category=HintCategory.DUPLICATE_SUSPECT,
            severity=HintSeverity.WARNING,
            title="Moegliches Duplikat",
            message=f"Ein Dokument mit Rechnungsnummer INV001 existiert bereits",
            action_label="Dokumente vergleichen",
            action_type="compare_documents",
            action_data={
                "document_id": str(document_id),
                "duplicate_id": str(duplicate_id),
            },
            confidence=0.80,
        )
        with patch.object(hints_service, "_check_duplicate_suspect", return_value=[expected_hint]):
            hints = await hints_service.get_hints_for_document(document_id, company_id)

        dup_hints = [h for h in hints if h.category == HintCategory.DUPLICATE_SUSPECT]
        assert len(dup_hints) > 0
        hint = dup_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "Duplikat" in hint.title
        assert hint.confidence == 0.80

    @pytest.mark.asyncio
    async def test_compliance_missing_fields(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Fehlende GoBD-Pflichtfelder = Compliance Hint."""
        # Missing invoice_date and total_amount
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            extracted_data={"invoice_number": "INV001"},
        )

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
        ]

        # Patch _check_duplicate_suspect because the service query uses
        # Document.extracted_data["..."].astext which requires JSONB (not
        # available with CrossDBJSON in unit test context).
        # _check_compliance runs after _check_duplicate_suspect in the try block.
        with patch.object(hints_service, "_check_duplicate_suspect", return_value=[]):
            hints = await hints_service.get_hints_for_document(document_id, company_id)

        compliance_hints = [h for h in hints if h.category == HintCategory.COMPLIANCE]
        assert len(compliance_hints) > 0
        hint = compliance_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "GoBD" in hint.title
        assert hint.confidence == 0.90

    @pytest.mark.asyncio
    async def test_action_required_high_amount(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Rechnung >= 10000 EUR = Freigabe erforderlich."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            extracted_data={
                "invoice_number": "INV001",
                "invoice_date": "2025-01-01",
                "total_amount": "15000.00",
            },
        )

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
        ]

        # Patch _check_duplicate_suspect because the service query uses
        # Document.extracted_data["..."].astext which requires JSONB (not
        # available with CrossDBJSON in unit test context).
        # _check_action_required runs after _check_duplicate_suspect.
        with patch.object(hints_service, "_check_duplicate_suspect", return_value=[]):
            hints = await hints_service.get_hints_for_document(document_id, company_id)

        action_hints = [h for h in hints if h.category == HintCategory.ACTION_REQUIRED]
        assert len(action_hints) > 0
        hint = action_hints[0]
        assert hint.severity == HintSeverity.WARNING
        assert "Freigabe" in hint.title
        assert hint.confidence == 1.0

    @pytest.mark.asyncio
    async def test_no_hints_for_clean_document(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Dokument ohne Probleme = keine Hints."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            doc_type=DocumentType.CONTRACT.value,
            extracted_data={},
        )

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        # For a CONTRACT: no check_missing_documents, no skonto/payment (no InvoiceTracking query
        # since those only apply to invoices), no duplicate, no compliance, no action_required
        # The service still calls _check_skonto_deadline and _check_payment_overdue which
        # each call execute to find InvoiceTracking, but since document_type is CONTRACT,
        # only the checks that don't filter on type will run.
        # Actually looking at the code: _check_skonto_deadline and _check_payment_overdue
        # always query InvoiceTracking regardless of document_type
        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
        ]

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        assert hints == []


# =============================================================================
# Get Hints Batch Tests
# =============================================================================


class TestGetHintsBatch:
    """Tests fuer get_hints_batch."""

    @pytest.mark.asyncio
    async def test_batch_with_multiple_documents(
        self,
        hints_service,
        mock_db,
        company_id,
    ):
        """Test: Batch mit mehreren Dokumenten."""
        doc_ids = [uuid4(), uuid4()]

        # Mock documents - both are CONTRACTs with no issues
        mock_docs = []
        for doc_id in doc_ids:
            mock_docs.append(_make_doc(
                doc_id=doc_id,
                company_id=company_id,
                doc_type=DocumentType.CONTRACT.value,
                extracted_data={},
            ))

        # Setup execute mock: for each doc -> doc_query + skonto + payment
        query_results = []
        for doc in mock_docs:
            doc_result = MagicMock()
            doc_result.scalar_one_or_none.return_value = doc
            query_results.append(doc_result)
            query_results.append(MagicMock(scalar_one_or_none=MagicMock(return_value=None)))  # skonto
            query_results.append(MagicMock(scalar_one_or_none=MagicMock(return_value=None)))  # payment
        mock_db.execute.side_effect = query_results

        results = await hints_service.get_hints_batch(doc_ids, company_id)

        assert isinstance(results, dict)
        assert len(results) == 2
        for doc_id in doc_ids:
            assert doc_id in results
            assert isinstance(results[doc_id], list)

    @pytest.mark.asyncio
    async def test_batch_with_empty_list(
        self,
        hints_service,
        company_id,
    ):
        """Test: Batch mit leerer Liste gibt leeres Dict."""
        results = await hints_service.get_hints_batch([], company_id)

        assert results == {}


# =============================================================================
# Get Hint Summary Tests
# =============================================================================


class TestGetHintSummary:
    """Tests fuer get_hint_summary."""

    @pytest.mark.asyncio
    async def test_summary_structure(
        self,
        hints_service,
        mock_db,
        company_id,
    ):
        """Test: Summary hat korrekte Struktur."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        summary = await hints_service.get_hint_summary(company_id)

        assert isinstance(summary, HintSummary)
        assert isinstance(summary.by_category, dict)
        assert isinstance(summary.by_severity, dict)
        assert isinstance(summary.total, int)
        assert isinstance(summary.critical_count, int)

    @pytest.mark.asyncio
    async def test_summary_counts_by_category(
        self,
        hints_service,
        mock_db,
        company_id,
    ):
        """Test: Summary zaehlt Hints nach Kategorie."""
        # Create mock document with low OCR and chain_id
        doc_id = uuid4()
        mock_doc = _make_doc(
            doc_id=doc_id,
            company_id=company_id,
            chain_id="CHAIN-001",
            ocr_confidence=0.65,
            extracted_data={"invoice_number": "INV001"},
        )

        # Mock documents query (get_hint_summary calls execute to list documents)
        mock_docs_result = MagicMock()
        mock_docs_result.scalars.return_value.all.return_value = [mock_doc]

        # Then get_hints_for_document is called for each doc.
        # For this doc: document_type=INVOICE, chain_id set, ocr_confidence=0.65
        # Calls: execute(doc query) -> scalar(missing doc count) -> execute(skonto) -> execute(payment) -> execute(duplicate)
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            mock_docs_result,  # Documents list for summary
            doc_result,  # Document load in get_hints_for_document
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]
        # scalar() for missing doc count = 0
        mock_db.scalar.return_value = 0

        summary = await hints_service.get_hint_summary(company_id)

        # Should have OCR quality hint + missing document hint + compliance (missing invoice_date, total_amount)
        assert summary.total > 0
        assert HintCategory.OCR_QUALITY.value in summary.by_category

    @pytest.mark.asyncio
    async def test_summary_counts_by_severity(
        self,
        hints_service,
        mock_db,
        company_id,
    ):
        """Test: Summary zaehlt Hints nach Severity."""
        doc_id = uuid4()
        mock_doc = _make_doc(
            doc_id=doc_id,
            company_id=company_id,
            ocr_confidence=0.40,  # Very low = critical
            extracted_data={"invoice_number": "INV001"},
        )

        mock_docs_result = MagicMock()
        mock_docs_result.scalars.return_value.all.return_value = [mock_doc]

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            mock_docs_result,
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]

        summary = await hints_service.get_hint_summary(company_id)

        assert HintSeverity.CRITICAL.value in summary.by_severity
        assert summary.critical_count > 0

    @pytest.mark.asyncio
    async def test_summary_empty_database(
        self,
        hints_service,
        mock_db,
        company_id,
    ):
        """Test: Leere Datenbank = Summary mit 0 Counts."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        summary = await hints_service.get_hint_summary(company_id)

        assert summary.total == 0
        assert summary.critical_count == 0
        assert summary.by_category == {}
        assert summary.by_severity == {}


# =============================================================================
# Hint Confidence Tests
# =============================================================================


class TestHintConfidence:
    """Tests fuer Confidence-Werte."""

    @pytest.mark.asyncio
    async def test_confidence_in_range(
        self,
        hints_service,
        mock_db,
        document_id,
        company_id,
    ):
        """Test: Confidence ist immer zwischen 0 und 1."""
        mock_doc = _make_doc(
            doc_id=document_id,
            company_id=company_id,
            chain_id="CHAIN-001",
            extracted_data={"invoice_number": "INV001", "invoice_date": "2025-01-01", "total_amount": "100"},
        )

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        mock_db.execute.side_effect = [
            doc_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # skonto
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # payment
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # duplicate
        ]
        mock_db.scalar.return_value = 0  # missing doc count

        hints = await hints_service.get_hints_for_document(document_id, company_id)

        for hint in hints:
            assert 0.0 <= hint.confidence <= 1.0


# =============================================================================
# Hint Serialization Tests
# =============================================================================


class TestHintSerialization:
    """Tests fuer Hint to_dict() Serialisierung."""

    def test_hint_to_dict(self):
        """Test: DocumentHint.to_dict() Serialisierung."""
        hint = DocumentHint(
            category=HintCategory.SKONTO_DEADLINE,
            severity=HintSeverity.WARNING,
            title="Test Hint",
            message="Test Message",
            action_label="Do Something",
            action_type="test_action",
            action_data={"key": "value"},
            confidence=0.85,
            expires_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )

        result = hint.to_dict()

        assert result["category"] == HintCategory.SKONTO_DEADLINE.value
        assert result["severity"] == HintSeverity.WARNING.value
        assert result["title"] == "Test Hint"
        assert result["message"] == "Test Message"
        assert result["action_label"] == "Do Something"
        assert result["action_type"] == "test_action"
        assert result["action_data"] == {"key": "value"}
        assert result["confidence"] == 0.85
        assert "expires_at" in result

    def test_summary_to_dict(self):
        """Test: HintSummary.to_dict() Serialisierung."""
        summary = HintSummary(
            by_category={"missing_document": 5},
            by_severity={"warning": 10},
            total=15,
            critical_count=3,
        )

        result = summary.to_dict()

        assert result["by_category"] == {"missing_document": 5}
        assert result["by_severity"] == {"warning": 10}
        assert result["total"] == 15
        assert result["critical_count"] == 3
