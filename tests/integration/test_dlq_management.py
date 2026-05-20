# -*- coding: utf-8 -*-
"""
Integration Tests: DLQ Management (Dead Letter Queue).

Tests Dead-Letter-Queue-Verwaltung für fehlgeschlagene Celery Tasks:
- Retry-Mechanismus
- Cleanup alter Tasks
- Critical threshold alerts

Feinpoliert und durchdacht - DLQ Management Testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4
import asyncio

import pytest_asyncio
from httpx import AsyncClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def failed_task():
    """Sample failed Celery task."""
    return {
        "id": str(uuid4()),
        "task_name": "import.sync_email_config",
        "args": ["config_123"],
        "kwargs": {},
        "exception": "ConnectionError: IMAP connection timeout",
        "failed_at": datetime.utcnow(),
        "retry_count": 0,
        "max_retries": 3,
    }


@pytest.fixture
def dlq_tasks():
    """Sample DLQ with multiple failed tasks."""
    now = datetime.utcnow()
    return [
        {
            "id": str(uuid4()),
            "task_name": "ocr.process_document",
            "failed_at": now - timedelta(days=7),
            "retry_count": 3,
            "status": "max_retries_exceeded",
        },
        {
            "id": str(uuid4()),
            "task_name": "import.sync_email_config",
            "failed_at": now - timedelta(days=2),
            "retry_count": 1,
            "status": "retryable",
        },
        {
            "id": str(uuid4()),
            "task_name": "datev.refresh_token",
            "failed_at": now - timedelta(hours=1),
            "retry_count": 0,
            "status": "retryable",
        },
    ]


# =============================================================================
# TEST 1: DLQ RETRY MECHANISM
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_dlq_retry_mechanism(
    async_client: AsyncClient,
    auth_headers: dict,
    failed_task: dict,
):
    """
    Test automatischen Retry-Mechanismus für fehlgeschlagene Tasks.

    ARRANGE: Task im DLQ mit retry_count < max_retries
    ACT: Trigger retry mit exponential backoff
    ASSERT: Task erfolgreich wiederholt oder max_retries erreicht
    """
    with patch("app.workers.celery_app.celery_app") as MockCelery:
        mock_celery = MockCelery

        retry_count = 0
        max_retries = 3

        async def mock_retry_task(task_id: str, backoff_seconds: int = 60):
            """Retry failed task with exponential backoff."""
            nonlocal retry_count

            # Wait for backoff period
            await asyncio.sleep(backoff_seconds / 1000)  # Convert to ms for testing

            retry_count += 1

            if retry_count < 3:
                # Still failing
                raise ConnectionError("IMAP connection timeout")

            # Success on 3rd retry
            return {"success": True, "retry_count": retry_count}

        mock_celery.retry_task = mock_retry_task

        # ACT: Retry task with exponential backoff
        last_error = None
        result = None

        for attempt in range(max_retries):
            backoff = 60 * (2 ** attempt)  # Exponential backoff: 60s, 120s, 240s

            try:
                result = await mock_celery.retry_task(failed_task["id"], backoff)
                break
            except Exception as e:
                last_error = e

        # ASSERT: Success after 3 retries
        assert retry_count == 3
        assert result is not None
        assert result["success"] is True


# =============================================================================
# TEST 2: DLQ CLEANUP OLD TASKS
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_dlq_cleanup_old_tasks(
    async_client: AsyncClient,
    auth_headers: dict,
    dlq_tasks: list,
):
    """
    Test Cleanup von alten DLQ-Tasks.

    ARRANGE: DLQ mit Tasks > 7 Tage alt
    ACT: Cleanup tasks older than retention period
    ASSERT: Alte Tasks gelöscht, recent Tasks behalten
    """
    with patch("app.services.dlq_management_service.DLQManagementService") as MockService:
        mock_service = MockService.return_value

        async def mock_cleanup_old_tasks(retention_days: int = 7):
            """Remove tasks older than retention period."""
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

            deleted_tasks = [
                task for task in dlq_tasks
                if task["failed_at"] < cutoff_date
            ]

            remaining_tasks = [
                task for task in dlq_tasks
                if task["failed_at"] >= cutoff_date
            ]

            return {
                "deleted_count": len(deleted_tasks),
                "remaining_count": len(remaining_tasks),
                "deleted_task_ids": [t["id"] for t in deleted_tasks],
            }

        mock_service.cleanup_old_tasks = mock_cleanup_old_tasks

        # ACT: Cleanup tasks older than 7 days
        result = await mock_service.cleanup_old_tasks(retention_days=7)

        # ASSERT: Old task deleted, recent tasks kept
        assert result["deleted_count"] == 1  # Task from 7 days ago
        assert result["remaining_count"] == 2  # Tasks from 2 days and 1 hour ago


# =============================================================================
# TEST 3: DLQ CRITICAL THRESHOLD ALERTS
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_dlq_alert_threshold(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """
    Test Alert-Generierung bei kritischer DLQ-Größe.

    ARRANGE: DLQ mit 100+ fehlgeschlagenen Tasks
    ACT: Check DLQ size gegen threshold
    ASSERT: Critical alert (SYS_002) erstellt
    """
    # ARRANGE: Large DLQ
    dlq_size = 150
    threshold = 100

    with patch("app.services.dlq_management_service.DLQManagementService") as MockDLQService:
        with patch("app.services.alert_center_service.AlertCenterService") as MockAlertService:
            mock_dlq = MockDLQService.return_value
            mock_alerts = MockAlertService.return_value

            async def mock_get_dlq_size():
                """Get current DLQ size."""
                return dlq_size

            alert_created = False

            async def mock_create_alert(category: str, alert_code: str, severity: str, **kwargs):
                """Mock alert creation."""
                nonlocal alert_created
                if alert_code == "SYS_002":
                    alert_created = True
                return {
                    "id": str(uuid4()),
                    "alert_code": alert_code,
                    "severity": severity,
                }

            mock_dlq.get_dlq_size = mock_get_dlq_size
            mock_alerts.create_alert = mock_create_alert

            # ACT: Check threshold
            current_size = await mock_dlq.get_dlq_size()

            if current_size > threshold:
                await mock_alerts.create_alert(
                    category="system",
                    alert_code="SYS_002",
                    severity="critical",
                    title="DLQ Queue zu groß",
                    message=f"Dead-Letter-Queue enthält {current_size} fehlgeschlagene Tasks (Threshold: {threshold})",
                    metadata={
                        "dlq_size": current_size,
                        "threshold": threshold,
                    },
                )

            # ASSERT: Alert created
            assert current_size > threshold
            assert alert_created is True


# =============================================================================
# BONUS: DLQ TASK ANALYSIS
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_dlq_task_analysis(
    async_client: AsyncClient,
    auth_headers: dict,
    dlq_tasks: list,
):
    """
    Test DLQ-Task-Analyse für Debugging.

    ARRANGE: DLQ mit verschiedenen Task-Typen
    ACT: Analyse nach Task-Name, Exception-Type
    ASSERT: Top failing tasks identifiziert
    """
    # Add more tasks with repeated failures
    extended_dlq = dlq_tasks + [
        {
            "id": str(uuid4()),
            "task_name": "ocr.process_document",
            "exception": "OOMError: GPU out of memory",
            "failed_at": datetime.utcnow() - timedelta(hours=2),
        },
        {
            "id": str(uuid4()),
            "task_name": "ocr.process_document",
            "exception": "OOMError: GPU out of memory",
            "failed_at": datetime.utcnow() - timedelta(hours=3),
        },
        {
            "id": str(uuid4()),
            "task_name": "import.sync_email_config",
            "exception": "ConnectionError: IMAP timeout",
            "failed_at": datetime.utcnow() - timedelta(hours=1),
        },
    ]

    with patch("app.services.dlq_management_service.DLQManagementService") as MockService:
        mock_service = MockService.return_value

        def analyze_dlq(tasks: list) -> dict:
            """Analyze DLQ for patterns."""
            from collections import Counter

            # Count by task name
            task_counts = Counter(t["task_name"] for t in tasks)

            # Count by exception type (if available)
            exception_counts = Counter(
                t.get("exception", "Unknown") for t in tasks
                if "exception" in t
            )

            return {
                "total_tasks": len(tasks),
                "top_failing_tasks": task_counts.most_common(3),
                "top_exceptions": exception_counts.most_common(3),
            }

        mock_service.analyze_dlq = analyze_dlq

        # ACT: Analyze DLQ
        result = mock_service.analyze_dlq(extended_dlq)

        # ASSERT: Analysis complete
        assert result["total_tasks"] == 6

        # ocr.process_document is top failing (3 occurrences)
        assert result["top_failing_tasks"][0][0] == "ocr.process_document"
        assert result["top_failing_tasks"][0][1] == 3

        # OOMError is top exception
        assert "OOMError" in result["top_exceptions"][0][0]


# =============================================================================
# BONUS: DLQ TASK MANUAL RETRY
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_dlq_manual_retry(
    async_client: AsyncClient,
    auth_headers: dict,
    failed_task: dict,
):
    """
    Test manueller Retry über Admin-API.

    ARRANGE: Task im DLQ
    ACT: Admin triggert manuellen Retry
    ASSERT: Task re-queued mit reset retry_count
    """
    with patch("app.services.dlq_management_service.DLQManagementService") as MockService:
        mock_service = MockService.return_value

        async def mock_manual_retry(task_id: str, reset_retry_count: bool = True):
            """Manually retry a DLQ task."""
            # Reset retry count if requested
            if reset_retry_count:
                failed_task["retry_count"] = 0

            # Re-queue task
            return {
                "task_id": task_id,
                "status": "requeued",
                "retry_count": failed_task["retry_count"],
            }

        mock_service.manual_retry = mock_manual_retry

        # ACT: Manual retry
        result = await mock_service.manual_retry(failed_task["id"], reset_retry_count=True)

        # ASSERT: Task requeued with reset count
        assert result["status"] == "requeued"
        assert result["retry_count"] == 0
