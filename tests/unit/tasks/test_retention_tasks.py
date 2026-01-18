"""
Unit Tests fuer GoBD Retention Tasks - Aufbewahrungsfristen-Management.

Tests:
- Check expiring archives task
- Archive integrity verification task
- Process expired archives task (Auto-Delete)
- Retention report generation task
- Audit log creation
"""

import sys
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Mock async_session_factory before importing retention_tasks
mock_async_session_factory = MagicMock()
with patch.dict('sys.modules', {}):
    # First patch the database module
    mock_db_module = MagicMock()
    mock_db_module.async_session_factory = mock_async_session_factory
    sys.modules['app.db.database'] = mock_db_module

    # Now we can import retention_tasks (it will use mocked database)
    from app.workers.tasks.retention_tasks import (
        _check_expiring_archives,
        _batch_verify_integrity,
        _process_expired_archives,
        _create_retention_audit_log,
    )

from app.db.models import RetentionCategory


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_company():
    """Create mock company."""
    company = MagicMock()
    company.id = uuid4()
    company.short_name = "TestFirma"
    company.is_active = True
    return company


@pytest.fixture
def mock_archive():
    """Create mock document archive."""
    archive = MagicMock()
    archive.id = uuid4()
    archive.document_id = uuid4()
    archive.company_id = uuid4()
    archive.retention_category = RetentionCategory.INVOICE.value
    archive.retention_expires_at = date.today() + timedelta(days=30)
    archive.content_hash = "a" * 64
    archive.is_verified = True
    archive.last_verification_at = datetime.now(timezone.utc)
    archive.retention_reminder_sent = False
    return archive


@pytest.fixture
def mock_retention_setting():
    """Create mock retention setting."""
    setting = MagicMock()
    setting.category = RetentionCategory.INVOICE.value
    setting.retention_years = 10
    setting.auto_delete_enabled = True
    setting.requires_approval_for_delete = False
    return setting


class TestCheckExpiringArchives:
    """Tests fuer _check_expiring_archives Funktion."""

    @pytest.mark.asyncio
    async def test_check_no_expiring_archives(self, mock_db, mock_company):
        """Keine ablaufenden Archive gefunden."""
        # Mock companies query
        mock_companies_result = MagicMock()
        mock_companies_result.scalars.return_value.all.return_value = [mock_company]
        mock_db.execute.return_value = mock_companies_result

        # Mock archive_service
        with patch(
            "app.workers.tasks.retention_tasks.archive_service"
        ) as mock_archive_service:
            mock_archive_service.get_expiring_archives = AsyncMock(return_value=[])

            result = await _check_expiring_archives(mock_db, days_ahead=90)

        assert result["total_expiring"] == 0
        assert result["total_reminded"] == 0
        assert result["days_ahead"] == 90

    @pytest.mark.asyncio
    async def test_check_with_expiring_archives(self, mock_db, mock_company, mock_archive):
        """Ablaufende Archive gefunden und erinnert."""
        mock_companies_result = MagicMock()
        mock_companies_result.scalars.return_value.all.return_value = [mock_company]
        mock_db.execute.return_value = mock_companies_result

        with patch(
            "app.workers.tasks.retention_tasks.archive_service"
        ) as mock_archive_service, patch(
            "app.workers.tasks.retention_tasks._create_retention_audit_log",
            new_callable=AsyncMock
        ) as mock_audit:
            mock_archive_service.get_expiring_archives = AsyncMock(
                return_value=[mock_archive]
            )
            mock_archive_service.mark_reminder_sent = AsyncMock()

            result = await _check_expiring_archives(mock_db, days_ahead=90)

        assert result["total_expiring"] == 1
        assert result["total_reminded"] == 1
        assert mock_company.short_name in result["by_company"]
        mock_archive_service.mark_reminder_sent.assert_called_once()
        mock_db.commit.assert_called_once()


class TestBatchVerifyIntegrity:
    """Tests fuer _batch_verify_integrity Funktion."""

    @pytest.mark.asyncio
    async def test_verify_all_valid(self, mock_db, mock_archive):
        """Alle Archive sind gueltig."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_archive]
        mock_db.execute.return_value = mock_result

        with patch(
            "app.workers.tasks.retention_tasks.archive_service"
        ) as mock_archive_service:
            mock_archive_service.verify_document_integrity = AsyncMock(return_value=True)

            result = await _batch_verify_integrity(mock_db, None, batch_size=100)

        assert result["verified"] == 1
        assert result["failed"] == 0
        assert result["failed_documents"] == []

    @pytest.mark.asyncio
    async def test_verify_some_failed(self, mock_db, mock_archive):
        """Einige Archive sind fehlerhaft."""
        mock_archive2 = MagicMock()
        mock_archive2.id = uuid4()
        mock_archive2.document_id = uuid4()
        mock_archive2.content_hash = "b" * 64

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_archive, mock_archive2]
        mock_db.execute.return_value = mock_result

        with patch(
            "app.workers.tasks.retention_tasks.archive_service"
        ) as mock_archive_service:
            # Erstes valide, zweites fehlerhaft
            mock_archive_service.verify_document_integrity = AsyncMock(
                side_effect=[True, False]
            )

            result = await _batch_verify_integrity(mock_db, None, batch_size=100)

        assert result["verified"] == 1
        assert result["failed"] == 1
        assert len(result["failed_documents"]) == 1

    @pytest.mark.asyncio
    async def test_verify_with_company_filter(self, mock_db, mock_archive):
        """Verifikation nur fuer bestimmte Firma."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_archive]
        mock_db.execute.return_value = mock_result

        with patch(
            "app.workers.tasks.retention_tasks.archive_service"
        ) as mock_archive_service:
            mock_archive_service.verify_document_integrity = AsyncMock(return_value=True)

            result = await _batch_verify_integrity(
                mock_db, company_id=company_id, batch_size=50
            )

        assert result["batch_size"] == 50


class TestProcessExpiredArchives:
    """Tests fuer _process_expired_archives Funktion (Auto-Delete)."""

    @pytest.mark.asyncio
    async def test_no_auto_delete_categories(self, mock_db):
        """Keine Kategorien mit Auto-Loeschung konfiguriert."""
        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_settings_result

        result = await _process_expired_archives(mock_db)

        assert "Keine Kategorien" in result["message"]
        assert result["deleted"] == 0
        assert result["pending_approval"] == 0

    @pytest.mark.asyncio
    async def test_auto_delete_without_approval(
        self, mock_db, mock_archive, mock_retention_setting
    ):
        """Archive automatisch loeschen ohne Approval."""
        # Abgelaufenes Archiv
        mock_archive.retention_expires_at = date.today() - timedelta(days=10)
        mock_archive.retention_category = RetentionCategory.INVOICE.value

        # Mock settings query
        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.all.return_value = [mock_retention_setting]

        # Mock expired archives query
        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = [mock_archive]

        # Mock setting lookup
        mock_setting_lookup = MagicMock()
        mock_setting_lookup.scalar_one_or_none.return_value = mock_retention_setting

        mock_db.execute.side_effect = [
            mock_settings_result,
            mock_expired_result,
            mock_setting_lookup,
        ]

        with patch(
            "app.workers.tasks.retention_tasks._create_retention_audit_log",
            new_callable=AsyncMock
        ):
            result = await _process_expired_archives(mock_db)

        assert result["deleted"] == 1
        assert result["pending_approval"] == 0
        mock_db.delete.assert_called_once_with(mock_archive)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_delete_with_approval_required(
        self, mock_db, mock_archive, mock_retention_setting
    ):
        """Archive markieren wenn Approval erforderlich."""
        mock_archive.retention_expires_at = date.today() - timedelta(days=5)
        mock_retention_setting.requires_approval_for_delete = True

        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.all.return_value = [mock_retention_setting]

        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = [mock_archive]

        mock_setting_lookup = MagicMock()
        mock_setting_lookup.scalar_one_or_none.return_value = mock_retention_setting

        mock_db.execute.side_effect = [
            mock_settings_result,
            mock_expired_result,
            mock_setting_lookup,
        ]

        with patch(
            "app.workers.tasks.retention_tasks._create_retention_audit_log",
            new_callable=AsyncMock
        ):
            result = await _process_expired_archives(mock_db)

        assert result["deleted"] == 0
        assert result["pending_approval"] == 1
        mock_db.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_delete_no_setting_found(self, mock_db, mock_archive, mock_retention_setting):
        """Ueberspringe Archive ohne passende Einstellung."""
        mock_archive.retention_expires_at = date.today() - timedelta(days=5)
        mock_archive.retention_category = "unknown_category"

        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.all.return_value = [mock_retention_setting]

        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = [mock_archive]

        mock_setting_lookup = MagicMock()
        mock_setting_lookup.scalar_one_or_none.return_value = None  # Keine Einstellung

        mock_db.execute.side_effect = [
            mock_settings_result,
            mock_expired_result,
            mock_setting_lookup,
        ]

        result = await _process_expired_archives(mock_db)

        assert result["deleted"] == 0
        assert result["pending_approval"] == 0


class TestCreateRetentionAuditLog:
    """Tests fuer _create_retention_audit_log Funktion."""

    @pytest.mark.asyncio
    async def test_create_audit_log(self, mock_db):
        """Audit-Log-Eintrag erstellen."""
        document_id = uuid4()
        company_id = uuid4()

        # Mock AuditLog class
        mock_audit_log = MagicMock()
        with patch("app.workers.tasks.retention_tasks.AuditLog", return_value=mock_audit_log):
            await _create_retention_audit_log(
                db=mock_db,
                document_id=document_id,
                company_id=company_id,
                action="retention_expired_archive_removed",
                details={
                    "archive_id": str(uuid4()),
                    "retention_category": "invoice",
                    "auto_deleted": True,
                },
            )

        # Pruefe, dass ein AuditLog erstellt wurde
        mock_db.add.assert_called_once_with(mock_audit_log)

    @pytest.mark.asyncio
    async def test_audit_log_with_different_actions(self, mock_db):
        """Verschiedene Audit-Aktionen protokollieren."""
        document_id = uuid4()
        company_id = uuid4()

        actions = [
            "retention_reminder_sent",
            "retention_expired_pending_approval",
            "retention_expired_archive_removed",
        ]

        for action in actions:
            mock_db.reset_mock()
            mock_audit_log = MagicMock()
            with patch("app.workers.tasks.retention_tasks.AuditLog", return_value=mock_audit_log):
                await _create_retention_audit_log(
                    db=mock_db,
                    document_id=document_id,
                    company_id=company_id,
                    action=action,
                    details={"test": True},
                )
            mock_db.add.assert_called_once()


class TestGoBDRetentionCompliance:
    """GoBD-Compliance Tests fuer Retention Tasks."""

    @pytest.mark.asyncio
    async def test_gobd_vollstaendigkeit_reminders_sent(
        self, mock_db, mock_company, mock_archive
    ):
        """Vollstaendigkeit: Alle ablaufenden Archive werden erinnert."""
        mock_archive2 = MagicMock()
        mock_archive2.id = uuid4()
        mock_archive2.document_id = uuid4()
        mock_archive2.retention_expires_at = date.today() + timedelta(days=60)

        mock_companies_result = MagicMock()
        mock_companies_result.scalars.return_value.all.return_value = [mock_company]
        mock_db.execute.return_value = mock_companies_result

        with patch(
            "app.workers.tasks.retention_tasks.archive_service"
        ) as mock_archive_service, patch(
            "app.workers.tasks.retention_tasks._create_retention_audit_log",
            new_callable=AsyncMock
        ):
            mock_archive_service.get_expiring_archives = AsyncMock(
                return_value=[mock_archive, mock_archive2]
            )
            mock_archive_service.mark_reminder_sent = AsyncMock()

            result = await _check_expiring_archives(mock_db, days_ahead=90)

        assert result["total_reminded"] == 2
        assert mock_archive_service.mark_reminder_sent.call_count == 2

    @pytest.mark.asyncio
    async def test_gobd_nachvollziehbarkeit_audit_log(self, mock_db, mock_archive):
        """Nachvollziehbarkeit: Loeschung wird protokolliert."""
        mock_archive.retention_expires_at = date.today() - timedelta(days=5)

        mock_setting = MagicMock()
        mock_setting.category = mock_archive.retention_category
        mock_setting.auto_delete_enabled = True
        mock_setting.requires_approval_for_delete = False

        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.all.return_value = [mock_setting]

        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = [mock_archive]

        mock_setting_lookup = MagicMock()
        mock_setting_lookup.scalar_one_or_none.return_value = mock_setting

        mock_db.execute.side_effect = [
            mock_settings_result,
            mock_expired_result,
            mock_setting_lookup,
        ]

        with patch(
            "app.workers.tasks.retention_tasks._create_retention_audit_log",
            new_callable=AsyncMock
        ) as mock_audit:
            await _process_expired_archives(mock_db)

            # Audit-Log wurde erstellt
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            # Check positional or keyword args
            assert call_args[1].get("action") == "retention_expired_archive_removed" or \
                   (len(call_args[0]) > 4 and "archive_removed" in str(call_args))

    @pytest.mark.asyncio
    async def test_gobd_ordnung_category_based_deletion(self, mock_db):
        """Ordnung: Loeschung basiert auf Dokumentkategorie."""
        invoice_archive = MagicMock()
        invoice_archive.id = uuid4()
        invoice_archive.document_id = uuid4()
        invoice_archive.retention_category = RetentionCategory.INVOICE.value
        invoice_archive.retention_expires_at = date.today() - timedelta(days=1)
        invoice_archive.company_id = uuid4()

        contract_archive = MagicMock()
        contract_archive.id = uuid4()
        contract_archive.document_id = uuid4()
        contract_archive.retention_category = RetentionCategory.CONTRACT.value
        contract_archive.retention_expires_at = date.today() - timedelta(days=1)
        contract_archive.company_id = uuid4()

        # Nur Invoices mit Auto-Delete
        invoice_setting = MagicMock()
        invoice_setting.category = RetentionCategory.INVOICE.value
        invoice_setting.auto_delete_enabled = True
        invoice_setting.requires_approval_for_delete = False

        mock_settings_result = MagicMock()
        mock_settings_result.scalars.return_value.all.return_value = [invoice_setting]

        # Nur Invoice-Archiv (wegen Kategoriefilter in Query)
        mock_expired_result = MagicMock()
        mock_expired_result.scalars.return_value.all.return_value = [invoice_archive]

        mock_setting_lookup = MagicMock()
        mock_setting_lookup.scalar_one_or_none.return_value = invoice_setting

        mock_db.execute.side_effect = [
            mock_settings_result,
            mock_expired_result,
            mock_setting_lookup,
        ]

        with patch(
            "app.workers.tasks.retention_tasks._create_retention_audit_log",
            new_callable=AsyncMock
        ):
            result = await _process_expired_archives(mock_db)

        # Nur Invoice geloescht (Contract hat kein Auto-Delete)
        assert result["deleted"] == 1
        assert RetentionCategory.INVOICE.value in result["categories_checked"]


class TestRetentionCategories:
    """Tests fuer Aufbewahrungskategorien."""

    def test_all_gobd_categories_defined(self):
        """Alle GoBD-relevanten Kategorien sind definiert."""
        categories = [c.value for c in RetentionCategory]

        # Nach deutschem Recht erforderliche Kategorien
        assert "invoice" in categories        # Rechnungen (10 Jahre)
        assert "contract" in categories       # Vertraege (10 Jahre)
        assert "correspondence" in categories # Geschaeftsbriefe (6 Jahre)
        assert "booking_document" in categories  # Buchungsbelege (10 Jahre)
        assert "annual_report" in categories  # Jahresabschluesse (10 Jahre)
        assert "tax_document" in categories   # Steuerunterlagen (10 Jahre)
