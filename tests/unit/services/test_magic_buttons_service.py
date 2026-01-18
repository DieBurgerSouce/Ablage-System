# -*- coding: utf-8 -*-
"""Unit tests for Magic Buttons Service.

Tests:
- Magic button types and statuses
- Preview functionality
- Execute functionality (mocked dependencies)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.magic_buttons_service import (
    MagicButtonsService,
    MagicButtonType,
    MagicButtonStatus,
    MagicButtonPreview,
    MagicButtonResult,
    get_magic_buttons_service,
)


@pytest.fixture
def magic_service() -> MagicButtonsService:
    """Create MagicButtonsService instance."""
    return MagicButtonsService()


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Test user ID."""
    return uuid4()


@pytest.fixture
def document_id():
    """Test document ID."""
    return uuid4()


class TestMagicButtonTypeEnum:
    """Tests for MagicButtonType enum."""

    def test_all_button_types_exist(self):
        """Test all expected button types are defined."""
        expected = ["daily_close", "monthly_report", "clear_open_items", "create_contact"]
        for btn_type in expected:
            assert MagicButtonType(btn_type) is not None

    def test_button_type_values(self):
        """Test button type string values."""
        assert MagicButtonType.DAILY_CLOSE.value == "daily_close"
        assert MagicButtonType.MONTHLY_REPORT.value == "monthly_report"
        assert MagicButtonType.CLEAR_OPEN_ITEMS.value == "clear_open_items"
        assert MagicButtonType.CREATE_CONTACT.value == "create_contact"


class TestMagicButtonStatusEnum:
    """Tests for MagicButtonStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses are defined."""
        expected = ["pending", "preview", "running", "completed", "partial", "failed"]
        for status in expected:
            assert MagicButtonStatus(status) is not None


class TestMagicButtonPreviewDataclass:
    """Tests for MagicButtonPreview dataclass."""

    def test_preview_creation_with_defaults(self):
        """Test MagicButtonPreview can be created with defaults."""
        preview = MagicButtonPreview(
            button_type=MagicButtonType.DAILY_CLOSE,
            title="Test",
            description="Test description",
        )
        assert preview.button_type == MagicButtonType.DAILY_CLOSE
        assert preview.document_count == 0
        assert preview.transaction_count == 0
        assert preview.estimated_amount == Decimal("0.00")
        assert preview.can_execute is True
        assert preview.block_reason is None
        assert preview.warnings == []
        assert preview.items == []

    def test_preview_with_all_fields(self):
        """Test MagicButtonPreview with all fields."""
        preview = MagicButtonPreview(
            button_type=MagicButtonType.MONTHLY_REPORT,
            title="Monats-Report",
            description="Export fuer Januar",
            document_count=50,
            transaction_count=100,
            entity_count=20,
            invoice_count=30,
            estimated_amount=Decimal("15000.00"),
            estimated_duration_seconds=60,
            warnings=["Warnung 1", "Warnung 2"],
            items=[{"type": "test", "count": 5}],
            can_execute=True,
            block_reason=None,
        )
        assert preview.document_count == 50
        assert preview.invoice_count == 30
        assert preview.estimated_amount == Decimal("15000.00")
        assert len(preview.warnings) == 2


class TestMagicButtonResultDataclass:
    """Tests for MagicButtonResult dataclass."""

    def test_result_creation_with_defaults(self):
        """Test MagicButtonResult can be created with defaults."""
        result = MagicButtonResult(
            button_type=MagicButtonType.DAILY_CLOSE,
            status=MagicButtonStatus.COMPLETED,
            title="Tages-Abschluss",
            message="Erfolgreich",
        )
        assert result.button_type == MagicButtonType.DAILY_CLOSE
        assert result.status == MagicButtonStatus.COMPLETED
        assert result.processed_count == 0
        assert result.success_count == 0
        assert result.error_count == 0
        assert result.total_amount == Decimal("0.00")
        assert result.details == []
        assert result.errors == []
        assert result.duration_ms == 0
        assert result.export_file_id is None

    def test_result_with_statistics(self):
        """Test MagicButtonResult with statistics."""
        result = MagicButtonResult(
            button_type=MagicButtonType.CLEAR_OPEN_ITEMS,
            status=MagicButtonStatus.PARTIAL,
            title="Offene Posten",
            message="Teilweise erfolgreich",
            processed_count=100,
            success_count=90,
            error_count=10,
            skipped_count=5,
            total_amount=Decimal("50000.00"),
            errors=["Fehler 1", "Fehler 2"],
            duration_ms=5000,
        )
        assert result.processed_count == 100
        assert result.success_count == 90
        assert result.error_count == 10
        assert result.skipped_count == 5
        assert len(result.errors) == 2
        assert result.duration_ms == 5000


class TestMagicButtonsSingleton:
    """Tests for singleton pattern."""

    def test_get_magic_buttons_service_returns_same_instance(self):
        """Test that get_magic_buttons_service returns same instance."""
        service1 = get_magic_buttons_service()
        service2 = get_magic_buttons_service()
        assert service1 is service2


@pytest.mark.asyncio
class TestPreviewDailyClose:
    """Tests for preview_daily_close method."""

    async def test_preview_returns_correct_type(
        self, magic_service: MagicButtonsService, company_id
    ):
        """Test preview returns MagicButtonPreview."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock document query
        doc_result = MagicMock()
        doc_result.scalars.return_value.all.return_value = []

        # Mock transaction query
        trans_result = MagicMock()
        trans_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [doc_result, trans_result]

        preview = await magic_service.preview_daily_close(
            db=mock_db,
            company_id=company_id,
        )

        assert isinstance(preview, MagicButtonPreview)
        assert preview.button_type == MagicButtonType.DAILY_CLOSE
        assert "Tages-Abschluss" in preview.title

    async def test_preview_with_no_items_cannot_execute(
        self, magic_service: MagicButtonsService, company_id
    ):
        """Test preview with no items sets can_execute=False."""
        mock_db = AsyncMock(spec=AsyncSession)

        doc_result = MagicMock()
        doc_result.scalars.return_value.all.return_value = []

        trans_result = MagicMock()
        trans_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [doc_result, trans_result]

        preview = await magic_service.preview_daily_close(
            db=mock_db,
            company_id=company_id,
        )

        assert preview.can_execute is False
        assert preview.block_reason is not None
        assert "Keine offenen Posten" in preview.block_reason

    async def test_preview_with_custom_date(
        self, magic_service: MagicButtonsService, company_id
    ):
        """Test preview with custom target date."""
        mock_db = AsyncMock(spec=AsyncSession)

        doc_result = MagicMock()
        doc_result.scalars.return_value.all.return_value = []

        trans_result = MagicMock()
        trans_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [doc_result, trans_result]

        target = date(2026, 1, 15)
        preview = await magic_service.preview_daily_close(
            db=mock_db,
            company_id=company_id,
            target_date=target,
        )

        assert "15.01.2026" in preview.description


@pytest.mark.asyncio
class TestPreviewMonthlyReport:
    """Tests for preview_monthly_report method."""

    async def test_preview_returns_correct_type(
        self, magic_service: MagicButtonsService, company_id
    ):
        """Test preview returns MagicButtonPreview."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # Mock amount query
        amount_result = MagicMock()
        amount_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, amount_result]

        preview = await magic_service.preview_monthly_report(
            db=mock_db,
            company_id=company_id,
            year=2026,
            month=1,
        )

        assert isinstance(preview, MagicButtonPreview)
        assert preview.button_type == MagicButtonType.MONTHLY_REPORT
        assert "Monats-Report" in preview.title
        assert "Januar" in preview.description

    async def test_preview_with_no_documents_cannot_execute(
        self, magic_service: MagicButtonsService, company_id
    ):
        """Test preview with no documents sets can_execute=False."""
        mock_db = AsyncMock(spec=AsyncSession)

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        amount_result = MagicMock()
        amount_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, amount_result]

        preview = await magic_service.preview_monthly_report(
            db=mock_db,
            company_id=company_id,
            year=2026,
            month=1,
        )

        assert preview.can_execute is False
        assert "Keine exportierbaren Dokumente" in preview.block_reason


@pytest.mark.asyncio
class TestPreviewClearOpenItems:
    """Tests for preview_clear_open_items method."""

    async def test_preview_returns_correct_type(
        self, magic_service: MagicButtonsService, company_id
    ):
        """Test preview returns MagicButtonPreview."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock overdue query
        overdue_result = MagicMock()
        overdue_result.scalars.return_value.all.return_value = []

        # Mock transaction count query
        trans_result = MagicMock()
        trans_result.scalar.return_value = 0

        mock_db.execute.side_effect = [overdue_result, trans_result]

        preview = await magic_service.preview_clear_open_items(
            db=mock_db,
            company_id=company_id,
        )

        assert isinstance(preview, MagicButtonPreview)
        assert preview.button_type == MagicButtonType.CLEAR_OPEN_ITEMS
        assert "Offene Posten" in preview.title

    async def test_preview_with_many_overdue_shows_warning(
        self, magic_service: MagicButtonsService, company_id
    ):
        """Test preview with many overdue invoices shows warning."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Create mock invoices
        mock_invoices = []
        for i in range(15):
            inv = MagicMock()
            inv.outstanding_amount = Decimal("1000.00")
            inv.total_amount = Decimal("1000.00")
            mock_invoices.append(inv)

        overdue_result = MagicMock()
        overdue_result.scalars.return_value.all.return_value = mock_invoices

        trans_result = MagicMock()
        trans_result.scalar.return_value = 0

        mock_db.execute.side_effect = [overdue_result, trans_result]

        preview = await magic_service.preview_clear_open_items(
            db=mock_db,
            company_id=company_id,
        )

        assert preview.invoice_count == 15
        assert len(preview.warnings) > 0
        assert any("15" in w for w in preview.warnings)


@pytest.mark.asyncio
class TestPreviewCreateContact:
    """Tests for preview_create_contact method."""

    async def test_preview_document_not_found(
        self, magic_service: MagicButtonsService, company_id, document_id
    ):
        """Test preview when document is not found."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock document query - not found
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = doc_result

        preview = await magic_service.preview_create_contact(
            db=mock_db,
            company_id=company_id,
            document_id=document_id,
        )

        assert preview.can_execute is False
        assert "nicht gefunden" in preview.block_reason

    async def test_preview_no_company_name_found(
        self, magic_service: MagicButtonsService, company_id, document_id
    ):
        """Test preview when no company name in document."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock document with no extracted data
        mock_doc = MagicMock()
        mock_doc.extracted_data = {}

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc
        mock_db.execute.return_value = doc_result

        preview = await magic_service.preview_create_contact(
            db=mock_db,
            company_id=company_id,
            document_id=document_id,
        )

        assert preview.can_execute is False
        assert "Firmenname" in preview.block_reason

    async def test_preview_with_valid_document(
        self, magic_service: MagicButtonsService, company_id, document_id
    ):
        """Test preview with valid document data - company name found."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock document with extracted data
        mock_doc = MagicMock()
        mock_doc.extracted_data = {
            "sender": {
                "company": "Test GmbH",
                "vat_id": "DE123456789",
                "address": {"street": "Teststr. 1", "city": "Berlin"},
            },
            "iban": "DE89370400440532013000",
        }

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        # Mock existing entity check - not found (returns empty result)
        entity_result = MagicMock()
        entity_result.scalars.return_value.first.return_value = None

        # First call for doc query, second for entity check
        mock_db.execute.side_effect = [doc_result, entity_result]

        preview = await magic_service.preview_create_contact(
            db=mock_db,
            company_id=company_id,
            document_id=document_id,
        )

        assert preview.can_execute is True
        assert len(preview.items) > 0
        # Check fields are extracted
        names = [item["field"] for item in preview.items]
        assert "name" in names
        assert "vat_id" in names
        assert "iban" in names


@pytest.mark.asyncio
class TestExecuteDailyClose:
    """Tests for execute_daily_close method."""

    async def test_execute_returns_result(
        self, magic_service: MagicButtonsService, company_id, user_id
    ):
        """Test execute returns MagicButtonResult."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()

        # Mock reconciliation service - patch where it's imported inside execute method
        with patch(
            "app.services.banking.reconciliation_service.ReconciliationService"
        ) as MockReconciliationService:
            mock_reconciliation = MagicMock()
            mock_batch_result = MagicMock()
            mock_batch_result.total_processed = 0
            mock_batch_result.matched_count = 0
            mock_batch_result.skipped_count = 0
            mock_reconciliation.batch_reconcile = AsyncMock(return_value=mock_batch_result)
            MockReconciliationService.return_value = mock_reconciliation

            # Mock document linker service
            with patch(
                "app.services.document_entity_linker_service.get_document_entity_linker_service"
            ) as mock_linker_factory:
                mock_linker = MagicMock()
                mock_linker.link_document = AsyncMock(return_value={"linked": False})
                mock_linker_factory.return_value = mock_linker

                # Mock document query
                doc_result = MagicMock()
                doc_result.scalars.return_value.all.return_value = []
                mock_db.execute.return_value = doc_result

                result = await magic_service.execute_daily_close(
                    db=mock_db,
                    company_id=company_id,
                    user_id=user_id,
                )

        assert isinstance(result, MagicButtonResult)
        assert result.button_type == MagicButtonType.DAILY_CLOSE
        assert result.status == MagicButtonStatus.COMPLETED
        # duration_ms can be 0 for fast mocked operations
        assert result.duration_ms >= 0


@pytest.mark.asyncio
class TestExecuteMonthlyReport:
    """Tests for execute_monthly_report method."""

    async def test_execute_returns_result(
        self, magic_service: MagicButtonsService, company_id, user_id
    ):
        """Test execute returns MagicButtonResult."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()

        # Mock DATEV service - patch where it's imported inside execute method
        with patch(
            "app.services.datev.get_datev_export_service"
        ) as mock_datev_factory:
            mock_datev = MagicMock()
            mock_export_record = MagicMock()
            mock_export_record.id = uuid4()
            mock_export_record.filename = "EXTF_202601.csv"
            mock_export_record.document_count = 50
            mock_datev.export_buchungsstapel = AsyncMock(
                return_value=(b"csv_content", mock_export_record)
            )
            mock_datev_factory.return_value = mock_datev

            result = await magic_service.execute_monthly_report(
                db=mock_db,
                company_id=company_id,
                user_id=user_id,
                year=2026,
                month=1,
            )

        assert isinstance(result, MagicButtonResult)
        assert result.button_type == MagicButtonType.MONTHLY_REPORT
        assert result.status == MagicButtonStatus.COMPLETED
        assert result.processed_count == 50
        assert result.export_filename == "EXTF_202601.csv"


@pytest.mark.asyncio
class TestExecuteClearOpenItems:
    """Tests for execute_clear_open_items method."""

    async def test_execute_returns_result(
        self, magic_service: MagicButtonsService, company_id, user_id
    ):
        """Test execute returns MagicButtonResult."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()

        # Mock reconciliation service - patch where it's imported inside execute method
        with patch(
            "app.services.banking.reconciliation_service.ReconciliationService"
        ) as MockReconciliationService:
            mock_reconciliation = MagicMock()
            mock_batch_result = MagicMock()
            mock_batch_result.total_processed = 10
            mock_batch_result.matched_count = 8
            mock_reconciliation.batch_reconcile = AsyncMock(return_value=mock_batch_result)
            MockReconciliationService.return_value = mock_reconciliation

            result = await magic_service.execute_clear_open_items(
                db=mock_db,
                company_id=company_id,
                user_id=user_id,
                auto_reconcile=True,
                increase_dunning=False,
            )

        assert isinstance(result, MagicButtonResult)
        assert result.button_type == MagicButtonType.CLEAR_OPEN_ITEMS
        assert result.status == MagicButtonStatus.COMPLETED
        assert result.success_count >= 8


@pytest.mark.asyncio
class TestExecuteCreateContact:
    """Tests for execute_create_contact method."""

    async def test_execute_document_not_found(
        self, magic_service: MagicButtonsService, company_id, user_id, document_id
    ):
        """Test execute when document is not found."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock document query - not found
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = doc_result

        result = await magic_service.execute_create_contact(
            db=mock_db,
            company_id=company_id,
            user_id=user_id,
            document_id=document_id,
        )

        assert result.status == MagicButtonStatus.FAILED
        assert "nicht gefunden" in result.message

    async def test_execute_with_valid_document(
        self, magic_service: MagicButtonsService, company_id, user_id, document_id
    ):
        """Test execute with valid document."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        # Mock document with extracted data
        mock_doc = MagicMock()
        mock_doc.id = document_id
        mock_doc.extracted_data = {
            "sender": {
                "company": "Test GmbH",
                "vat_id": "DE123456789",
            },
            "iban": "DE89370400440532013000",
        }

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc
        mock_db.execute.return_value = doc_result

        result = await magic_service.execute_create_contact(
            db=mock_db,
            company_id=company_id,
            user_id=user_id,
            document_id=document_id,
        )

        assert result.status == MagicButtonStatus.COMPLETED
        assert result.success_count == 1
        assert "Test GmbH" in result.message
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    async def test_execute_with_override_name(
        self, magic_service: MagicButtonsService, company_id, user_id, document_id
    ):
        """Test execute with override name."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        # Mock document with extracted data
        mock_doc = MagicMock()
        mock_doc.id = document_id
        mock_doc.extracted_data = {
            "sender": {"company": "Original Name"},
        }

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc
        mock_db.execute.return_value = doc_result

        result = await magic_service.execute_create_contact(
            db=mock_db,
            company_id=company_id,
            user_id=user_id,
            document_id=document_id,
            override_name="Override GmbH",
        )

        assert result.status == MagicButtonStatus.COMPLETED
        assert "Override GmbH" in result.message
