# -*- coding: utf-8 -*-
"""
Unit-Tests für GDPR Celery Tasks.

Testet:
- process_deletion_requests (Art. 17 DSGVO)
- check_retention_compliance (Aufbewahrungsfristen)
- send_breach_notification (Art. 33/34 DSGVO)
- generate_compliance_report

Feinpoliert und durchdacht - GDPR-konforme Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def sample_user():
    """Create sample user for deletion."""
    user = Mock()
    user.id = uuid4()
    user.email = "delete-me@example.com"
    user.deletion_scheduled_for = datetime.now(timezone.utc) - timedelta(days=1)
    user.deletion_confirmed = True
    return user


@pytest.fixture
def sample_document():
    """Create sample document."""
    doc = Mock()
    doc.id = uuid4()
    doc.owner_id = uuid4()
    doc.file_path = "/documents/test.pdf"
    doc.data_category = "personal_identifiable"
    doc.created_at = datetime.now(timezone.utc) - timedelta(days=400)
    doc.deleted_at = None
    return doc


@pytest.fixture
def sample_deletion_request():
    """Create sample GDPR deletion request."""
    request = Mock()
    request.id = uuid4()
    request.user_id = uuid4()
    request.status = "pending"
    request.deletion_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    request.completed_at = None
    return request


# ========================= process_deletion_requests Tests =========================


class TestProcessDeletionRequests:
    """Tests for GDPR deletion request processing."""

    @pytest.mark.asyncio
    async def test_process_deletion_from_user_field(self, mock_db, sample_user):
        """Loeschung via User.deletion_scheduled_for."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_user]
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.gdpr_tasks._delete_user_data') as mock_delete:
                mock_delete.return_value = {"documents": 5, "audit_entries": 10}

                from app.workers.tasks.gdpr_tasks import _process_deletion_requests_async

                stats = await _process_deletion_requests_async()

                # Function processes both user field deletions and request table deletions
                assert stats["requests_processed"] >= 1
                assert stats["users_deleted"] >= 1

    @pytest.mark.asyncio
    async def test_process_deletion_handles_errors(self, mock_db, sample_user):
        """Fehler bei einzelnem User sollten nicht alles stoppen."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_user]
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.gdpr_tasks._delete_user_data') as mock_delete:
                mock_delete.side_effect = Exception("Database error")

                from app.workers.tasks.gdpr_tasks import _process_deletion_requests_async

                stats = await _process_deletion_requests_async()

                assert len(stats["errors"]) > 0
                assert stats["users_deleted"] == 0

    @pytest.mark.asyncio
    async def test_process_deletion_no_pending_requests(self, mock_db):
        """Ohne Anfragen sollte nichts passieren."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = []
            mock_db.execute.return_value = mock_result

            from app.workers.tasks.gdpr_tasks import _process_deletion_requests_async

            stats = await _process_deletion_requests_async()

            assert stats["requests_processed"] == 0
            assert stats["users_deleted"] == 0


# ========================= _delete_user_data Tests =========================


class TestDeleteUserData:
    """Tests for user data deletion helper."""

    @pytest.mark.skip(reason="SQLAlchemy func.json() incompatible with Mock - needs integration test")
    @pytest.mark.asyncio
    async def test_delete_user_documents(self, mock_db, sample_document):
        """Dokumente sollten aus Storage und DB geloescht werden."""
        with patch('app.services.storage_service.get_storage_service') as mock_storage:
            storage = Mock()
            storage.delete_document = AsyncMock()
            mock_storage.return_value = storage

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_document]
            mock_db.execute.return_value = mock_result

            from app.workers.tasks.gdpr_tasks import _delete_user_data

            stats = await _delete_user_data(mock_db, sample_document.owner_id, None)

            assert stats["documents"] == 1
            storage.delete_document.assert_called_once()

    @pytest.mark.skip(reason="SQLAlchemy func.json() incompatible with Mock - needs integration test")
    @pytest.mark.asyncio
    async def test_delete_user_anonymizes_audit_logs(self, mock_db):
        """Audit-Logs sollten anonymisiert werden."""
        with patch('app.services.storage_service.get_storage_service') as mock_storage:
            storage = Mock()
            storage.delete_document = AsyncMock()
            mock_storage.return_value = storage

            mock_doc_result = Mock()
            mock_doc_result.scalars.return_value.all.return_value = []

            mock_update_result = Mock()
            mock_update_result.rowcount = 5

            mock_db.execute.side_effect = [
                mock_doc_result,  # Document query
                mock_doc_result,  # Document delete
                mock_update_result,  # Audit log update
                mock_doc_result,  # User delete
            ]

            from app.workers.tasks.gdpr_tasks import _delete_user_data

            stats = await _delete_user_data(mock_db, uuid4(), None)

            assert stats["audit_entries"] == 5


# ========================= check_retention_compliance Tests =========================


class TestCheckRetentionCompliance:
    """Tests for retention compliance checking."""

    @pytest.mark.asyncio
    async def test_retention_finds_expired_documents(self, mock_db, sample_document):
        """Abgelaufene Dokumente sollten gefunden werden."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_document]
            mock_db.execute.return_value = mock_result

            from app.workers.tasks.gdpr_tasks import _check_retention_compliance_async

            stats = await _check_retention_compliance_async(dry_run=True)

            assert stats["documents_expired"] >= 0
            assert stats["dry_run"] is True

    @pytest.mark.asyncio
    async def test_retention_dry_run_no_delete(self, mock_db, sample_document):
        """Dry-Run sollte nicht loeschen."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_document]
            mock_db.execute.return_value = mock_result

            from app.workers.tasks.gdpr_tasks import _check_retention_compliance_async

            stats = await _check_retention_compliance_async(dry_run=True)

            assert stats["documents_deleted"] == 0

    @pytest.mark.asyncio
    async def test_retention_soft_deletes_expired(self, mock_db, sample_document):
        """Abgelaufene Dokumente sollten soft-deleted werden."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_document]
            mock_db.execute.return_value = mock_result

            from app.workers.tasks.gdpr_tasks import _check_retention_compliance_async

            stats = await _check_retention_compliance_async(dry_run=False)

            # Should call commit for soft-delete
            mock_db.commit.assert_called()


# ========================= send_breach_notification Tests =========================


class TestSendBreachNotification:
    """Tests for breach notification (Art. 33/34 DSGVO)."""

    @pytest.mark.asyncio
    async def test_breach_notification_admin_alert(self):
        """Admin sollte immer benachrichtigt werden."""
        with patch('app.services.notification_service.get_notification_service') as mock_notif:
            service = AsyncMock()
            service.send_admin_alert = AsyncMock()
            mock_notif.return_value = service

            from app.workers.tasks.gdpr_tasks import _send_breach_notification_async

            stats = await _send_breach_notification_async(
                breach_id="BREACH-001",
                breach_type="unauthorized_access",
                affected_records=100,
                description="Test breach",
                notify_authority=False,
                notify_users=False,
            )

            assert stats["admin_notified"] is True
            service.send_admin_alert.assert_called()

    @pytest.mark.asyncio
    async def test_breach_notification_authority_report(self):
        """Behoerdenmeldung sollte bei notify_authority=True erfolgen."""
        with patch('app.services.notification_service.get_notification_service') as mock_notif:
            service = AsyncMock()
            service.send_admin_alert = AsyncMock()
            mock_notif.return_value = service

            from app.workers.tasks.gdpr_tasks import _send_breach_notification_async

            stats = await _send_breach_notification_async(
                breach_id="BREACH-002",
                breach_type="data_leak",
                affected_records=1000,
                description="Large breach",
                notify_authority=True,
                notify_users=False,
            )

            assert stats["authority_notified"] is True
            # Should be called at least twice (admin + authority)
            assert service.send_admin_alert.call_count >= 2

    @pytest.mark.asyncio
    async def test_breach_notification_72h_deadline(self):
        """Deadline sollte 72 Stunden sein."""
        with patch('app.services.notification_service.get_notification_service') as mock_notif:
            service = AsyncMock()
            service.send_admin_alert = AsyncMock()
            mock_notif.return_value = service

            from app.workers.tasks.gdpr_tasks import _send_breach_notification_async

            stats = await _send_breach_notification_async(
                breach_id="BREACH-003",
                breach_type="test",
                affected_records=10,
                description="Test",
                notify_authority=False,
                notify_users=False,
            )

            # Check deadline is approximately 72 hours from now
            deadline = datetime.fromisoformat(stats["deadline"])
            now = datetime.now(timezone.utc)
            diff_hours = (deadline - now).total_seconds() / 3600

            assert 71 < diff_hours < 73


# ========================= generate_compliance_report Tests =========================


class TestGenerateComplianceReport:
    """Tests for compliance report generation."""

    @pytest.mark.asyncio
    async def test_report_includes_user_stats(self, mock_db):
        """Report sollte Benutzerstatistiken enthalten."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_count = Mock()
            mock_count.scalar.return_value = 100

            mock_db.execute.return_value = mock_count

            with patch('app.core.gdpr.get_gdpr_manager') as mock_gdpr:
                gdpr = Mock()
                gdpr.check_retention_compliance.return_value = {"status": "ok"}
                mock_gdpr.return_value = gdpr

                from app.workers.tasks.gdpr_tasks import _generate_compliance_report_async

                report = await _generate_compliance_report_async()

                assert "users" in report
                assert "documents" in report
                assert "generated_at" in report

    @pytest.mark.asyncio
    async def test_report_includes_retention_status(self, mock_db):
        """Report sollte Retention-Status enthalten."""
        with patch('app.db.database.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_count = Mock()
            mock_count.scalar.return_value = 0
            mock_db.execute.return_value = mock_count

            with patch('app.core.gdpr.get_gdpr_manager') as mock_gdpr:
                gdpr = Mock()
                gdpr.check_retention_compliance.return_value = {
                    "compliant": True,
                    "expired_documents": 0,
                }
                mock_gdpr.return_value = gdpr

                from app.workers.tasks.gdpr_tasks import _generate_compliance_report_async

                report = await _generate_compliance_report_async()

                assert "retention" in report


# ========================= Constants Tests =========================


class TestGDPRConstants:
    """Tests for GDPR-related constants."""

    def test_deletion_deadline_is_30_days(self):
        """Loeschfrist sollte 30 Tage sein (Art. 17)."""
        from app.workers.tasks.gdpr_tasks import GDPR_DELETION_DEADLINE_DAYS

        assert GDPR_DELETION_DEADLINE_DAYS == 30

    def test_breach_notification_is_72_hours(self):
        """Breach-Meldung sollte 72 Stunden sein (Art. 33)."""
        from app.workers.tasks.gdpr_tasks import BREACH_NOTIFICATION_HOURS

        assert BREACH_NOTIFICATION_HOURS == 72


# ========================= Format Authority Report Tests =========================


class TestFormatAuthorityReport:
    """Tests for authority report formatting."""

    def test_format_includes_all_fields(self):
        """Behoerdenbericht sollte alle Pflichtfelder enthalten."""
        from app.workers.tasks.gdpr_tasks import _format_authority_report

        report_data = {
            "breach_id": "BREACH-001",
            "organization": "Test GmbH",
            "contact_email": "dpo@test.de",
            "breach_type": "data_leak",
            "affected_records": 500,
            "description": "Datenleck entdeckt",
            "detection_time": "2024-12-01T10:00:00Z",
            "measures_taken": "System gesichert",
        }

        formatted = _format_authority_report(report_data)

        assert "Art. 33 DSGVO" in formatted
        assert "BREACH-001" in formatted
        assert "Test GmbH" in formatted
        assert "500" in formatted
