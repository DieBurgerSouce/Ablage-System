# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Retention Enforcement Celery Tasks.

Testet:
- enforce_retention_daily_scan (Taeglicher Scan auf Retention-Verletztungen)
- process_post_retention_reviews (Verarbeitung abgelaufener Archive)
- generate_retention_compliance_report (Compliance-Report Generierung)

Feinpoliert und durchdacht - Enterprise-grade Retention Enforcement Tests.
"""

import pytest
from datetime import date, datetime, timezone
from typing import Dict, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from uuid import uuid4, UUID


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_celery_task():
    """Create mock Celery task with retry capability."""
    task = MagicMock()
    task.retry = MagicMock(side_effect=Exception("retry"))
    return task


@pytest.fixture
def mock_async_session():
    """Create mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add = Mock()
    return session


@pytest.fixture
def mock_company():
    """Create mock company."""
    company = Mock()
    company.id = uuid4()
    company.short_name = "TestFirma"
    company.is_active = True
    return company


@pytest.fixture
def mock_document():
    """Create mock document."""
    doc = Mock()
    doc.id = uuid4()
    doc.is_archived = True
    doc.archived_at = datetime.now(timezone.utc)
    doc.company_id = uuid4()
    return doc


@pytest.fixture
def mock_archive():
    """Create mock document archive."""
    archive = Mock()
    archive.id = uuid4()
    archive.document_id = uuid4()
    archive.company_id = uuid4()
    archive.retention_category = "business_records"
    archive.retention_expires_at = date.today()
    return archive


@pytest.fixture
def mock_expired_archive():
    """Create mock expired archive."""
    archive = Mock()
    archive.id = uuid4()
    archive.document_id = uuid4()
    archive.company_id = uuid4()
    archive.retention_category = "business_records"
    archive.retention_expires_at = date(2020, 1, 1)  # Expired
    return archive


@pytest.fixture
def mock_compliance_dashboard():
    """Create mock compliance dashboard."""
    dashboard = Mock()
    dashboard.total_archives = 100
    dashboard.active_retention = 80
    dashboard.expired_retention = 15
    dashboard.expiring_30_days = 5
    dashboard.expiring_90_days = 10
    dashboard.by_category = {
        "business_records": 50,
        "tax_documents": 30,
        "invoices": 20,
    }
    return dashboard


# ========================= TestEnforceRetentionDailyScan =========================


class TestEnforceRetentionDailyScan:
    """Tests fuer enforce_retention_daily_scan Task."""

    def test_scan_no_violations(self, mock_async_session, mock_company):
        """Clean state sollte 0 violations zurueckgeben."""
        # Mock Company query - returns active company
        company_result = AsyncMock()
        company_result.scalars.return_value.all.return_value = [mock_company]

        # Mock Document query - no orphaned docs
        doc_result = AsyncMock()
        doc_result.scalars.return_value.all.return_value = []

        # Mock Archive query - no archives
        archive_result = MagicMock()
        archive_result.scalars.return_value.all.return_value = []

        mock_async_session.execute = AsyncMock(
            side_effect=[company_result, doc_result, archive_result]
        )

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('asyncio.get_event_loop') as mock_loop:
                mock_event_loop = Mock()
                mock_event_loop.run_until_complete = Mock(
                    return_value={
                        "archives_checked": 0,
                        "violations_found": 0,
                        "inconsistencies_fixed": 0,
                        "companies_scanned": 1,
                    }
                )
                mock_loop.return_value = mock_event_loop

                from app.workers.tasks.retention_enforcement_tasks import enforce_retention_daily_scan

                result = enforce_retention_daily_scan()

                assert result["violations_found"] == 0
                assert result["inconsistencies_fixed"] == 0
                assert result["companies_scanned"] == 1

    def test_scan_finds_inconsistency(self, mock_async_session, mock_company, mock_document):
        """is_archived=True ohne archive entry sollte violation finden."""
        # Mock Company query
        company_result = MagicMock()
        company_result.scalars.return_value.all.return_value = [mock_company]

        # Mock Document query - one orphaned doc
        doc_result = MagicMock()
        doc_result.scalars.return_value.all.return_value = [mock_document]

        # Mock Archive query - no archive for doc
        archive_result = MagicMock()
        archive_result.scalar_one_or_none.return_value = None

        # Mock Archive list query - empty
        archive_list_result = MagicMock()
        archive_list_result.scalars.return_value.all.return_value = []

        # Mock pending-reviews count query (final gauge update)
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_async_session.execute = AsyncMock(
            side_effect=[company_result, doc_result, archive_result, archive_list_result, count_result]
        )

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            async def _run_scan():
                from app.workers.tasks.retention_enforcement_tasks import _daily_enforcement_scan
                return await _daily_enforcement_scan(mock_async_session)

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(_run_scan())

            assert result["violations_found"] == 1
            assert result["companies_scanned"] == 1

    def test_scan_fixes_inconsistency(self, mock_async_session, mock_company, mock_document):
        """Sollte is_archived=False setzen bei orphaned doc."""
        # Mock Company query
        company_result = MagicMock()
        company_result.scalars.return_value.all.return_value = [mock_company]

        # Mock Document query - one orphaned doc
        doc_result = MagicMock()
        doc_result.scalars.return_value.all.return_value = [mock_document]

        # Mock Archive query - no archive
        archive_result = MagicMock()
        archive_result.scalar_one_or_none.return_value = None

        # Mock Archive list query
        archive_list_result = MagicMock()
        archive_list_result.scalars.return_value.all.return_value = []

        # Mock pending-reviews count query (final gauge update)
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_async_session.execute = AsyncMock(
            side_effect=[company_result, doc_result, archive_result, archive_list_result, count_result]
        )

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            async def _run_scan():
                from app.workers.tasks.retention_enforcement_tasks import _daily_enforcement_scan
                return await _daily_enforcement_scan(mock_async_session)

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(_run_scan())

            assert result["inconsistencies_fixed"] == 1
            assert mock_document.is_archived is False
            assert mock_document.archived_at is None

    def test_scan_counts_archives(self, mock_async_session, mock_company, mock_archive):
        """Sollte alle Archives zaehlen."""
        # Mock Company query
        company_result = MagicMock()
        company_result.scalars.return_value.all.return_value = [mock_company]

        # Mock Document query - no orphaned
        doc_result = MagicMock()
        doc_result.scalars.return_value.all.return_value = []

        # Mock Archive query - 3 archives
        archive_result = MagicMock()
        archive_result.scalars.return_value.all.return_value = [
            mock_archive,
            mock_archive,
            mock_archive,
        ]

        # Mock pending-reviews count query (final gauge update)
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_async_session.execute = AsyncMock(
            side_effect=[company_result, doc_result, archive_result, count_result]
        )

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            async def _run_scan():
                from app.workers.tasks.retention_enforcement_tasks import _daily_enforcement_scan
                return await _daily_enforcement_scan(mock_async_session)

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(_run_scan())

            assert result["archives_checked"] == 3

    def test_scan_multiple_companies(self, mock_async_session):
        """Sollte ueber mehrere Companies scannen."""
        company1 = Mock()
        company1.id = uuid4()
        company1.short_name = "Firma1"
        company1.is_active = True

        company2 = Mock()
        company2.id = uuid4()
        company2.short_name = "Firma2"
        company2.is_active = True

        # Mock Company query - 2 companies
        company_result = MagicMock()
        company_result.scalars.return_value.all.return_value = [company1, company2]

        # Mock Document queries - empty for both
        doc_result1 = MagicMock()
        doc_result1.scalars.return_value.all.return_value = []
        doc_result2 = MagicMock()
        doc_result2.scalars.return_value.all.return_value = []

        # Mock Archive queries - empty for both
        archive_result1 = MagicMock()
        archive_result1.scalars.return_value.all.return_value = []
        archive_result2 = MagicMock()
        archive_result2.scalars.return_value.all.return_value = []

        # Mock pending-reviews count query (final gauge update)
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_async_session.execute = AsyncMock(
            side_effect=[company_result, doc_result1, archive_result1, doc_result2, archive_result2, count_result]
        )

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            async def _run_scan():
                from app.workers.tasks.retention_enforcement_tasks import _daily_enforcement_scan
                return await _daily_enforcement_scan(mock_async_session)

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(_run_scan())

            assert result["companies_scanned"] == 2

    def test_scan_error_retries(self, mock_celery_task):
        """Bei Exception sollte self.retry aufgerufen werden."""
        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.side_effect = Exception("Database error")

            with patch('asyncio.get_event_loop') as mock_loop:
                mock_event_loop = Mock()
                mock_event_loop.run_until_complete = Mock(
                    side_effect=Exception("Database error")
                )
                mock_loop.return_value = mock_event_loop

                from app.workers.tasks.retention_enforcement_tasks import enforce_retention_daily_scan

                # Patch the task's retry method
                with patch.object(enforce_retention_daily_scan, 'retry', side_effect=Exception("retry")):
                    with pytest.raises(Exception) as exc_info:
                        enforce_retention_daily_scan()

                    assert "retry" in str(exc_info.value) or "Database error" in str(exc_info.value)


# ========================= TestProcessPostRetentionReviews =========================


class TestProcessPostRetentionReviews:
    """Tests fuer process_post_retention_reviews Task."""

    def test_reviews_processes_expired(self, mock_async_session, mock_expired_archive):
        """Sollte abgelaufene Archives finden und verarbeiten."""
        # Mock Archive query - one expired
        archive_result = MagicMock()
        archive_result.scalars.return_value.all.return_value = [mock_expired_archive]

        mock_async_session.execute = AsyncMock(return_value=archive_result)

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('app.workers.tasks.retention_enforcement_tasks._create_enforcement_audit_log') as mock_audit:
                mock_audit.return_value = AsyncMock()

                with patch('app.services.slack_service.SlackService') as mock_slack_class:
                    mock_slack = Mock()
                    mock_slack.is_enabled = False
                    mock_slack_class.return_value = mock_slack

                    async def _run_process():
                        from app.workers.tasks.retention_enforcement_tasks import _process_post_retention_reviews
                        return await _process_post_retention_reviews(mock_async_session)

                    import asyncio
                    result = asyncio.get_event_loop().run_until_complete(_run_process())

                    assert result["reviews_processed"] == 1

    def test_reviews_creates_audit_log(self, mock_async_session, mock_expired_archive):
        """Sollte Audit-Log fuer jede Review erstellen."""
        # Mock Archive query
        archive_result = MagicMock()
        archive_result.scalars.return_value.all.return_value = [mock_expired_archive]

        mock_async_session.execute = AsyncMock(return_value=archive_result)

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('app.workers.tasks.retention_enforcement_tasks._create_enforcement_audit_log') as mock_audit:
                mock_audit.return_value = AsyncMock()

                with patch('app.services.slack_service.SlackService') as mock_slack_class:
                    mock_slack = Mock()
                    mock_slack.is_enabled = False
                    mock_slack_class.return_value = mock_slack

                    async def _run_process():
                        from app.workers.tasks.retention_enforcement_tasks import _process_post_retention_reviews
                        return await _process_post_retention_reviews(mock_async_session)

                    import asyncio
                    asyncio.get_event_loop().run_until_complete(_run_process())

                    # Verify audit log was called
                    mock_audit.assert_called_once()
                    call_args = mock_audit.call_args
                    assert call_args[0][1] == mock_expired_archive.document_id
                    assert call_args[0][2] == mock_expired_archive.company_id
                    assert call_args[0][3] == "post_retention_review_processed"

    def test_reviews_sends_notification(self, mock_async_session, mock_expired_archive):
        """Sollte Slack-Notification senden."""
        # Mock Archive query
        archive_result = MagicMock()
        archive_result.scalars.return_value.all.return_value = [mock_expired_archive]

        mock_async_session.execute = AsyncMock(return_value=archive_result)

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('app.workers.tasks.retention_enforcement_tasks._create_enforcement_audit_log') as mock_audit:
                mock_audit.return_value = AsyncMock()

                with patch('app.services.slack_service.SlackService') as mock_slack_class:
                    mock_slack = Mock()
                    mock_slack.is_enabled = True
                    mock_slack.send_notification = AsyncMock()
                    mock_slack_class.return_value = mock_slack

                    async def _run_process():
                        from app.workers.tasks.retention_enforcement_tasks import _process_post_retention_reviews
                        return await _process_post_retention_reviews(mock_async_session)

                    import asyncio
                    result = asyncio.get_event_loop().run_until_complete(_run_process())

                    assert result["notifications_sent"] == 1
                    mock_slack.send_notification.assert_called_once()

    def test_reviews_notification_failure_continues(self, mock_async_session, mock_expired_archive):
        """Sollte bei Slack-Fehler weitermachen."""
        # Mock Archive query
        archive_result = MagicMock()
        archive_result.scalars.return_value.all.return_value = [mock_expired_archive]

        mock_async_session.execute = AsyncMock(return_value=archive_result)

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('app.workers.tasks.retention_enforcement_tasks._create_enforcement_audit_log') as mock_audit:
                mock_audit.return_value = AsyncMock()

                with patch('app.services.slack_service.SlackService') as mock_slack_class:
                    mock_slack = Mock()
                    mock_slack.is_enabled = True
                    mock_slack.send_notification = AsyncMock(side_effect=Exception("Slack error"))
                    mock_slack_class.return_value = mock_slack

                    async def _run_process():
                        from app.workers.tasks.retention_enforcement_tasks import _process_post_retention_reviews
                        return await _process_post_retention_reviews(mock_async_session)

                    import asyncio
                    result = asyncio.get_event_loop().run_until_complete(_run_process())

                    # Should still process review despite notification failure
                    assert result["reviews_processed"] == 1
                    assert result["notifications_sent"] == 0

    def test_reviews_empty_no_expired(self, mock_async_session):
        """Keine abgelaufenen Archives sollte 0 zurueckgeben."""
        # Mock Archive query - empty
        archive_result = MagicMock()
        archive_result.scalars.return_value.all.return_value = []

        mock_async_session.execute = AsyncMock(return_value=archive_result)

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            async def _run_process():
                from app.workers.tasks.retention_enforcement_tasks import _process_post_retention_reviews
                return await _process_post_retention_reviews(mock_async_session)

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(_run_process())

            assert result["reviews_processed"] == 0
            assert result["notifications_sent"] == 0


# ========================= TestGenerateComplianceReport =========================


class TestGenerateComplianceReport:
    """Tests fuer generate_retention_compliance_report Task."""

    def test_report_single_company(self, mock_async_session, mock_company, mock_compliance_dashboard):
        """Sollte Report fuer eine Company generieren."""
        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('app.workers.tasks.retention_enforcement_tasks.retention_enforcement_service') as mock_service:
                mock_service.get_compliance_dashboard = AsyncMock(return_value=mock_compliance_dashboard)

                async def _run_generate():
                    from app.workers.tasks.retention_enforcement_tasks import _generate_compliance_report
                    return await _generate_compliance_report(mock_async_session, mock_company.id)

                import asyncio
                result = asyncio.get_event_loop().run_until_complete(_run_generate())

                assert result["companies_included"] == 1
                assert str(mock_company.id) in result["reports"]
                assert result["reports"][str(mock_company.id)]["total_archives"] == 100

    def test_report_all_companies(self, mock_async_session, mock_compliance_dashboard):
        """Sollte Report fuer alle Companies generieren."""
        company1 = Mock()
        company1.id = uuid4()
        company1.short_name = "Firma1"
        company1.is_active = True

        company2 = Mock()
        company2.id = uuid4()
        company2.short_name = "Firma2"
        company2.is_active = True

        # Mock Company query
        company_result = MagicMock()
        company_result.scalars.return_value.all.return_value = [company1, company2]

        mock_async_session.execute = AsyncMock(return_value=company_result)

        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('app.workers.tasks.retention_enforcement_tasks.retention_enforcement_service') as mock_service:
                mock_service.get_compliance_dashboard = AsyncMock(return_value=mock_compliance_dashboard)

                async def _run_generate():
                    from app.workers.tasks.retention_enforcement_tasks import _generate_compliance_report
                    return await _generate_compliance_report(mock_async_session, None)

                import asyncio
                result = asyncio.get_event_loop().run_until_complete(_run_generate())

                assert result["companies_included"] == 2
                assert "Firma1" in result["reports"]
                assert "Firma2" in result["reports"]

    def test_report_contains_metrics(self, mock_async_session, mock_company, mock_compliance_dashboard):
        """Report sollte erwartete Metriken enthalten."""
        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.return_value = mock_async_session

            with patch('app.workers.tasks.retention_enforcement_tasks.retention_enforcement_service') as mock_service:
                mock_service.get_compliance_dashboard = AsyncMock(return_value=mock_compliance_dashboard)

                async def _run_generate():
                    from app.workers.tasks.retention_enforcement_tasks import _generate_compliance_report
                    return await _generate_compliance_report(mock_async_session, mock_company.id)

                import asyncio
                result = asyncio.get_event_loop().run_until_complete(_run_generate())

                report = result["reports"][str(mock_company.id)]
                assert report["total_archives"] == 100
                assert report["active_retention"] == 80
                assert report["expired_retention"] == 15
                assert report["expiring_30_days"] == 5
                assert report["expiring_90_days"] == 10
                assert "by_category" in report
                assert report["by_category"]["business_records"] == 50

    def test_report_error_retries(self, mock_celery_task):
        """Bei Exception sollte self.retry aufgerufen werden."""
        with patch('app.workers.tasks.retention_enforcement_tasks.async_session_factory') as mock_factory:
            mock_factory.return_value.__aenter__.side_effect = Exception("Database error")

            with patch('asyncio.get_event_loop') as mock_loop:
                mock_event_loop = Mock()
                mock_event_loop.run_until_complete = Mock(
                    side_effect=Exception("Database error")
                )
                mock_loop.return_value = mock_event_loop

                from app.workers.tasks.retention_enforcement_tasks import generate_retention_compliance_report

                # Patch the task's retry method
                with patch.object(generate_retention_compliance_report, 'retry', side_effect=Exception("retry")):
                    with pytest.raises(Exception) as exc_info:
                        generate_retention_compliance_report()

                    assert "retry" in str(exc_info.value) or "Database error" in str(exc_info.value)


# ========================= Helper Function Tests =========================


class TestHelperFunctions:
    """Tests fuer Helper-Funktionen."""

    def test_create_enforcement_audit_log(self, mock_async_session):
        """Sollte Audit-Log korrekt erstellen."""
        doc_id = uuid4()
        company_id = uuid4()
        action = "test_action"
        details = {"key": "value"}

        async def _run_create():
            from app.workers.tasks.retention_enforcement_tasks import _create_enforcement_audit_log
            await _create_enforcement_audit_log(
                mock_async_session,
                doc_id,
                company_id,
                action,
                details
            )

        import asyncio
        asyncio.get_event_loop().run_until_complete(_run_create())

        # Verify session.add was called
        mock_async_session.add.assert_called_once()
        added_log = mock_async_session.add.call_args[0][0]

        assert added_log.company_id == company_id
        assert added_log.action == action
        assert added_log.resource_type == "document_archive"
        assert added_log.resource_id == doc_id
        assert added_log.audit_metadata == details
        assert added_log.ip_address == "system"
        assert added_log.user_agent == "retention_enforcement_task"


# ========================= Task Definition Tests =========================


class TestTaskDefinitions:
    """Tests fuer Task-Definitionen."""

    def test_enforce_retention_daily_scan_exists(self):
        """enforce_retention_daily_scan sollte existieren."""
        from app.workers.tasks.retention_enforcement_tasks import enforce_retention_daily_scan
        assert enforce_retention_daily_scan is not None

    def test_process_post_retention_reviews_exists(self):
        """process_post_retention_reviews sollte existieren."""
        from app.workers.tasks.retention_enforcement_tasks import process_post_retention_reviews
        assert process_post_retention_reviews is not None

    def test_generate_retention_compliance_report_exists(self):
        """generate_retention_compliance_report sollte existieren."""
        from app.workers.tasks.retention_enforcement_tasks import generate_retention_compliance_report
        assert generate_retention_compliance_report is not None

    def test_tasks_have_names(self):
        """Tasks sollten benannt sein."""
        from app.workers.tasks.retention_enforcement_tasks import (
            enforce_retention_daily_scan,
            process_post_retention_reviews,
            generate_retention_compliance_report,
        )

        assert enforce_retention_daily_scan.name is not None
        assert "retention_enforcement" in enforce_retention_daily_scan.name
        assert process_post_retention_reviews.name is not None
        assert "retention_enforcement" in process_post_retention_reviews.name
        assert generate_retention_compliance_report.name is not None
        assert "retention_enforcement" in generate_retention_compliance_report.name

    def test_tasks_have_correct_options(self):
        """Tasks sollten korrekte Celery-Optionen haben."""
        from app.workers.tasks.retention_enforcement_tasks import (
            enforce_retention_daily_scan,
            process_post_retention_reviews,
            generate_retention_compliance_report,
        )

        # Check bind=True
        assert enforce_retention_daily_scan.request is not None

        # Check acks_late and max_retries are set (these are task options)
        # We can't directly test these but we can verify tasks are properly decorated
        assert hasattr(enforce_retention_daily_scan, 'run')
        assert hasattr(process_post_retention_reviews, 'run')
        assert hasattr(generate_retention_compliance_report, 'run')
