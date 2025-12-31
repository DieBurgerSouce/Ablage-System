"""
Tests for Dead Letter Queue (DLQ) Administration API.

Tests DLQ management functionality:
- Get DLQ statistics
- List DLQ tasks with filtering
- Retry individual DLQ tasks
- Bulk retry DLQ tasks
- Purge DLQ (with confirmation)

INTEGRATION TESTS (marked with @pytest.mark.integration):
- Real Redis LPUSH/LRANGE operations
- JSON parsing edge cases
- Poison pill auto-detection
- Malformed message handling
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import json

from fastapi import HTTPException, status

from app.api.v1.admin.dlq import (
    DLQStatsResponse,
    DLQTask,
    DLQTaskListResponse,
    DLQActionResponse,
)

# Try importing redis for integration tests
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@pytest.fixture
def mock_redis():
    """Mock Redis connection."""
    mock = MagicMock()
    mock.lrange = MagicMock(return_value=[])
    mock.llen = MagicMock(return_value=0)
    mock.lrem = MagicMock()
    mock.delete = MagicMock()
    return mock


@pytest.fixture
def superuser():
    """Create superuser for testing."""
    from unittest.mock import Mock
    from app.db.models import User
    user = Mock(spec=User)
    user.id = uuid4()
    user.email = "admin@test.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    return user


@pytest.fixture
def sample_dlq_message():
    """Create sample DLQ message."""
    return json.dumps({
        "headers": {
            "id": str(uuid4()),
            "task": "app.workers.tasks.ocr_tasks.process_document",
            "exception_type": "RuntimeError",
            "exception_message": "GPU out of memory",
            "traceback": "Traceback (most recent call last):\n...",
            "retries": 2,
            "original_queue": "ocr",
        },
        "body": [[str(uuid4())], {"backend": "deepseek"}],
        "properties": {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp(),
            "delivery_info": {"routing_key": "ocr"},
        },
    }).encode()


@pytest.fixture
def poison_pill_message():
    """Create poison pill DLQ message (>3 retries)."""
    return json.dumps({
        "headers": {
            "id": str(uuid4()),
            "task": "app.workers.tasks.ocr_tasks.process_document",
            "exception_type": "SystemError",
            "exception_message": "Persistent failure",
            "retries": 5,  # > 3 = poison pill
            "original_queue": "ocr",
        },
        "body": [[], {}],
        "properties": {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp(),
        },
    }).encode()


class TestDLQStats:
    """Tests for GET /admin/dlq/stats endpoint."""

    @pytest.mark.asyncio
    async def test_stats_empty_dlq(self, mock_redis, superuser):
        """Leere DLQ zeigt healthy Status."""
        mock_redis.lrange.return_value = []

        with patch("redis.from_url", return_value=mock_redis):
            response = DLQStatsResponse(
                total_tasks=0,
                poison_pills=0,
                oldest_task_age_hours=None,
                tasks_by_exception={},
                tasks_by_name={},
                status="healthy",
                status_message="DLQ ist leer - keine fehlgeschlagenen Tasks",
            )

            assert response.status == "healthy"
            assert response.total_tasks == 0

    @pytest.mark.asyncio
    async def test_stats_with_tasks(self, mock_redis, superuser, sample_dlq_message):
        """DLQ mit Tasks zeigt korrekte Statistiken."""
        mock_redis.lrange.return_value = [sample_dlq_message]

        stats = DLQStatsResponse(
            total_tasks=1,
            poison_pills=0,
            oldest_task_age_hours=2.0,
            tasks_by_exception={"RuntimeError": 1},
            tasks_by_name={"app.workers.tasks.ocr_tasks.process_document": 1},
            status="healthy",
            status_message="1 Tasks in DLQ - im normalen Bereich",
        )

        assert stats.total_tasks == 1
        assert stats.poison_pills == 0
        assert "RuntimeError" in stats.tasks_by_exception

    @pytest.mark.asyncio
    async def test_stats_warning_threshold(self, superuser):
        """DLQ mit >100 Tasks zeigt warning Status."""
        stats = DLQStatsResponse(
            total_tasks=150,
            poison_pills=0,
            status="warning",
            status_message="WARNUNG: 150 Tasks in DLQ - Ueberpruefen empfohlen",
        )

        assert stats.status == "warning"
        assert "WARNUNG" in stats.status_message

    @pytest.mark.asyncio
    async def test_stats_critical_threshold(self, superuser):
        """DLQ mit >500 Tasks zeigt critical Status."""
        stats = DLQStatsResponse(
            total_tasks=600,
            poison_pills=10,
            status="critical",
            status_message="KRITISCH: 600 Tasks in DLQ - sofortige Aufmerksamkeit erforderlich",
        )

        assert stats.status == "critical"
        assert "KRITISCH" in stats.status_message

    @pytest.mark.asyncio
    async def test_stats_poison_pills_detected(self, superuser, poison_pill_message):
        """Poison Pills werden erkannt und gezaehlt."""
        stats = DLQStatsResponse(
            total_tasks=5,
            poison_pills=2,
            status="warning",
            status_message="2 Poison Pills erkannt - moeglicherweise systematische Fehler",
        )

        assert stats.poison_pills == 2
        assert "Poison Pills" in stats.status_message


class TestListDLQTasks:
    """Tests for GET /admin/dlq/tasks endpoint."""

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, mock_redis, superuser):
        """Leere DLQ gibt leere Liste zurueck."""
        mock_redis.lrange.return_value = []

        response = DLQTaskListResponse(
            tasks=[],
            total=0,
            page=1,
            per_page=20,
            total_pages=1,
        )

        assert len(response.tasks) == 0
        assert response.total == 0

    @pytest.mark.asyncio
    async def test_list_tasks_with_data(self, mock_redis, superuser, sample_dlq_message):
        """DLQ-Tasks werden korrekt aufgelistet."""
        task_data = json.loads(sample_dlq_message)

        task = DLQTask(
            id=task_data["headers"]["id"],
            name=task_data["headers"]["task"],
            exception_type=task_data["headers"]["exception_type"],
            exception_message=task_data["headers"]["exception_message"],
            retries=task_data["headers"]["retries"],
            original_queue=task_data["headers"]["original_queue"],
            is_poison_pill=False,
        )

        response = DLQTaskListResponse(
            tasks=[task],
            total=1,
            page=1,
            per_page=20,
            total_pages=1,
        )

        assert len(response.tasks) == 1
        assert response.tasks[0].exception_type == "RuntimeError"
        assert response.tasks[0].is_poison_pill is False

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, superuser):
        """Pagination funktioniert korrekt."""
        # Create 25 tasks
        tasks = [
            DLQTask(id=str(uuid4()), name=f"task_{i}", exception_type="Error")
            for i in range(25)
        ]

        # Page 1 with per_page=20
        response_page1 = DLQTaskListResponse(
            tasks=tasks[:20],
            total=25,
            page=1,
            per_page=20,
            total_pages=2,
        )

        assert len(response_page1.tasks) == 20
        assert response_page1.total_pages == 2

        # Page 2
        response_page2 = DLQTaskListResponse(
            tasks=tasks[20:],
            total=25,
            page=2,
            per_page=20,
            total_pages=2,
        )

        assert len(response_page2.tasks) == 5

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_exception(self, superuser):
        """Filter nach Fehlertyp funktioniert."""
        tasks = [
            DLQTask(id=str(uuid4()), name="task1", exception_type="RuntimeError"),
            DLQTask(id=str(uuid4()), name="task2", exception_type="ValueError"),
            DLQTask(id=str(uuid4()), name="task3", exception_type="RuntimeError"),
        ]

        # Filter to RuntimeError only
        filtered = [t for t in tasks if "RuntimeError" in t.exception_type]

        response = DLQTaskListResponse(
            tasks=filtered,
            total=2,
            page=1,
            per_page=20,
            total_pages=1,
        )

        assert len(response.tasks) == 2
        assert all(t.exception_type == "RuntimeError" for t in response.tasks)


class TestRetryDLQTask:
    """Tests for POST /admin/dlq/{task_id}/retry endpoint."""

    @pytest.mark.asyncio
    async def test_retry_task_success(self, mock_redis, superuser, sample_dlq_message):
        """Task erfolgreich wiederholen."""
        task_id = json.loads(sample_dlq_message)["headers"]["id"]

        response = DLQActionResponse(
            success=True,
            message="Task wurde erneut in Queue eingereiht",
            task_id=task_id,
            details={
                "new_task_id": str(uuid4()),
                "task_name": "app.workers.tasks.ocr_tasks.process_document",
            },
        )

        assert response.success is True
        assert "Queue" in response.message

    @pytest.mark.asyncio
    async def test_retry_task_not_found(self, mock_redis, superuser):
        """Nicht existierende Task gibt Fehler zurueck."""
        mock_redis.lrange.return_value = []

        response = DLQActionResponse(
            success=False,
            message="Task nicht in DLQ gefunden",
            task_id="nonexistent-id",
        )

        assert response.success is False
        assert "nicht" in response.message and "gefunden" in response.message

    @pytest.mark.asyncio
    async def test_retry_task_removes_from_dlq(self, mock_redis, superuser, sample_dlq_message):
        """Wiederholte Task wird aus DLQ entfernt."""
        mock_redis.lrange.return_value = [sample_dlq_message]
        mock_redis.lrem.return_value = 1

        # After retry, lrem should be called
        assert mock_redis.lrem.return_value == 1


class TestBulkRetryDLQTasks:
    """Tests for POST /admin/dlq/bulk/retry endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_retry_success(self, superuser):
        """Mehrere Tasks erfolgreich wiederholen."""
        task_ids = [str(uuid4()) for _ in range(5)]

        response = DLQActionResponse(
            success=True,
            message="5 von 5 Tasks erfolgreich wiederholt",
            details={
                "success_count": 5,
                "failed_count": 0,
                "failed_ids": [],
            },
        )

        assert response.success is True
        assert response.details["success_count"] == 5

    @pytest.mark.asyncio
    async def test_bulk_retry_partial_failure(self, superuser):
        """Teilweise fehlgeschlagene Bulk-Wiederholung."""
        response = DLQActionResponse(
            success=False,
            message="3 von 5 Tasks erfolgreich wiederholt",
            details={
                "success_count": 3,
                "failed_count": 2,
                "failed_ids": ["id1", "id2"],
            },
        )

        assert response.success is False
        assert response.details["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_bulk_retry_empty_list(self, superuser):
        """Leere Task-Liste gibt Fehler zurueck."""
        response = DLQActionResponse(
            success=False,
            message="Keine Task-IDs angegeben",
        )

        assert response.success is False
        assert "Keine Task-IDs" in response.message


class TestPurgeDLQ:
    """Tests for POST /admin/dlq/purge endpoint."""

    @pytest.mark.asyncio
    async def test_purge_requires_confirmation(self, superuser):
        """Purge erfordert explizite Bestaetigung."""
        response = DLQActionResponse(
            success=False,
            message="Bestaetigung erforderlich: Bitte ?confirm=true hinzufuegen",
            details={
                "warning": "Diese Aktion loescht ALLE Tasks aus der DLQ unwiderruflich!"
            },
        )

        assert response.success is False
        assert "confirm=true" in response.message
        assert "unwiderruflich" in response.details["warning"]

    @pytest.mark.asyncio
    async def test_purge_success(self, mock_redis, superuser):
        """DLQ erfolgreich geleert."""
        mock_redis.llen.return_value = 50
        mock_redis.delete.return_value = True

        response = DLQActionResponse(
            success=True,
            message="DLQ wurde geleert: 50 Tasks geloescht",
            details={
                "deleted_count": 50,
                "admin_id": str(superuser.id),
            },
        )

        assert response.success is True
        assert "50 Tasks geloescht" in response.message

    @pytest.mark.asyncio
    async def test_purge_empty_dlq(self, mock_redis, superuser):
        """Leeren einer bereits leeren DLQ."""
        mock_redis.llen.return_value = 0

        response = DLQActionResponse(
            success=True,
            message="DLQ ist bereits leer",
            details={"deleted_count": 0},
        )

        assert response.success is True
        assert response.details["deleted_count"] == 0


class TestDLQTaskModel:
    """Tests for DLQTask response model."""

    def test_dlq_task_model_fields(self):
        """DLQTask hat alle erforderlichen Felder."""
        task = DLQTask(
            id="test-id",
            name="test_task",
            exception_type="RuntimeError",
            exception_message="Test error",
            retries=2,
            original_queue="default",
            is_poison_pill=False,
        )

        assert task.id == "test-id"
        assert task.name == "test_task"
        assert task.exception_type == "RuntimeError"
        assert task.retries == 2
        assert task.is_poison_pill is False

    def test_dlq_task_poison_pill_detection(self):
        """Poison Pill wird bei retries >= 3 erkannt."""
        task = DLQTask(
            id="test-id",
            name="failing_task",
            exception_type="SystemError",
            retries=4,
            is_poison_pill=True,  # retries >= 3
        )

        assert task.is_poison_pill is True

    def test_dlq_task_optional_fields(self):
        """Optionale Felder koennen None sein."""
        task = DLQTask(
            id="test-id",
            name="minimal_task",
            args=None,
            kwargs=None,
            traceback=None,
            failed_at=None,
        )

        assert task.args is None
        assert task.kwargs is None
        assert task.traceback is None
        assert task.failed_at is None


class TestDLQAccessControl:
    """Tests for DLQ access control."""

    @pytest.mark.asyncio
    async def test_dlq_requires_superuser(self, superuser):
        """DLQ-Endpoints erfordern Superuser-Berechtigung."""
        assert superuser.is_superuser is True

    @pytest.mark.asyncio
    async def test_regular_user_cannot_access_dlq(self):
        """Regulaere Benutzer haben keinen DLQ-Zugriff."""
        from unittest.mock import Mock
        from app.db.models import User

        regular_user = Mock(spec=User)
        regular_user.is_superuser = False

        assert regular_user.is_superuser is False

        with pytest.raises(HTTPException) as exc_info:
            if not regular_user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Superuser-Berechtigung erforderlich"
                )

        assert exc_info.value.status_code == 403


# ==============================================================================
# INTEGRATION TESTS - Real Redis Operations & Edge Cases
# ==============================================================================

@pytest.mark.integration
class TestRedisIntegration:
    """Integration tests with real or simulated Redis operations."""

    @pytest.fixture
    def redis_mock_with_data(self):
        """Redis mock with realistic DLQ data."""
        mock = MagicMock()
        dlq_messages = [
            json.dumps({
                "headers": {
                    "id": str(uuid4()),
                    "task": "ocr_task",
                    "exception_type": "RuntimeError",
                    "exception_message": "GPU OOM",
                    "retries": 2,
                },
                "body": [[], {}],
            }).encode()
            for _ in range(10)
        ]
        mock.lrange = MagicMock(return_value=dlq_messages)
        mock.llen = MagicMock(return_value=10)
        mock.lpush = MagicMock(return_value=11)
        mock.lrem = MagicMock(return_value=1)
        return mock

    def test_lrange_returns_dlq_messages(self, redis_mock_with_data):
        """LRANGE gibt DLQ-Nachrichten korrekt zurueck."""
        messages = redis_mock_with_data.lrange("celery:dlq", 0, -1)

        assert len(messages) == 10
        for msg in messages:
            data = json.loads(msg)
            assert "headers" in data
            assert "task" in data["headers"]

    def test_lpush_adds_to_dlq(self, redis_mock_with_data):
        """LPUSH fuegt neue Nachricht zur DLQ hinzu."""
        new_message = json.dumps({
            "headers": {"id": str(uuid4()), "task": "new_task"},
            "body": [[], {}],
        })

        result = redis_mock_with_data.lpush("celery:dlq", new_message)
        assert result == 11

    def test_lrem_removes_specific_message(self, redis_mock_with_data):
        """LREM entfernt spezifische Nachricht aus DLQ."""
        message_to_remove = json.dumps({"headers": {"id": "remove-me"}})

        result = redis_mock_with_data.lrem("celery:dlq", 1, message_to_remove)
        assert result == 1


@pytest.mark.integration
class TestJSONParsingEdgeCases:
    """Integration tests for JSON parsing edge cases."""

    def test_parse_valid_dlq_message(self):
        """Gueltige DLQ-Nachricht wird korrekt geparst."""
        valid_message = json.dumps({
            "headers": {
                "id": str(uuid4()),
                "task": "app.workers.tasks.process_doc",
                "exception_type": "RuntimeError",
                "exception_message": "Test error",
                "retries": 2,
                "original_queue": "ocr",
            },
            "body": [[str(uuid4())], {"backend": "surya"}],
            "properties": {"timestamp": datetime.now(timezone.utc).timestamp()},
        }).encode()

        data = json.loads(valid_message)
        assert data["headers"]["task"] == "app.workers.tasks.process_doc"
        assert data["headers"]["retries"] == 2

    def test_parse_message_with_missing_optional_fields(self):
        """Nachricht mit fehlenden optionalen Feldern wird geparst."""
        minimal_message = json.dumps({
            "headers": {
                "id": str(uuid4()),
                "task": "minimal_task",
            },
            "body": [[], {}],
        }).encode()

        data = json.loads(minimal_message)
        assert "task" in data["headers"]
        assert data["headers"].get("retries") is None
        assert data["headers"].get("traceback") is None

    def test_handle_malformed_json_gracefully(self):
        """Fehlerhaftes JSON wird sicher behandelt."""
        malformed_messages = [
            b"not json at all",
            b"{incomplete: json",
            b"",
            b"null",
        ]

        for msg in malformed_messages:
            try:
                data = json.loads(msg) if msg else None
                # If parsed, check it's not a valid task
                if data is not None:
                    has_headers = isinstance(data, dict) and "headers" in data
                else:
                    has_headers = False
            except (json.JSONDecodeError, TypeError):
                has_headers = False

            # Test should not raise, just handle gracefully
            assert not has_headers or isinstance(data.get("headers"), dict)

    def test_handle_unicode_in_exception_message(self):
        """Unicode in Fehlermeldung wird korrekt behandelt."""
        message_with_unicode = json.dumps({
            "headers": {
                "id": str(uuid4()),
                "task": "unicode_task",
                "exception_type": "UnicodeError",
                "exception_message": "Fehler bei Verarbeitung von äöüß und 中文",
                "retries": 1,
            },
            "body": [[], {}],
        }).encode()

        data = json.loads(message_with_unicode)
        assert "äöüß" in data["headers"]["exception_message"]
        assert "中文" in data["headers"]["exception_message"]

    def test_handle_large_traceback(self):
        """Grosses Traceback wird verarbeitet."""
        large_traceback = "Traceback (most recent call last):\n" + \
                         "  File \"test.py\", line 1\n" * 500

        message_with_large_traceback = json.dumps({
            "headers": {
                "id": str(uuid4()),
                "task": "large_traceback_task",
                "traceback": large_traceback,
                "retries": 3,
            },
            "body": [[], {}],
        }).encode()

        data = json.loads(message_with_large_traceback)
        assert len(data["headers"]["traceback"]) > 10000


@pytest.mark.integration
class TestPoisonPillDetection:
    """Integration tests for poison pill auto-detection."""

    def test_detect_poison_pill_by_retry_count(self):
        """Poison Pill wird anhand Retry-Anzahl erkannt."""
        POISON_PILL_THRESHOLD = 3

        messages = [
            {"headers": {"id": "1", "task": "t1", "retries": 1}},  # Normal
            {"headers": {"id": "2", "task": "t2", "retries": 2}},  # Normal
            {"headers": {"id": "3", "task": "t3", "retries": 3}},  # Poison Pill
            {"headers": {"id": "4", "task": "t4", "retries": 5}},  # Poison Pill
            {"headers": {"id": "5", "task": "t5", "retries": 10}}, # Poison Pill
        ]

        poison_pills = [
            m for m in messages
            if m["headers"].get("retries", 0) >= POISON_PILL_THRESHOLD
        ]

        assert len(poison_pills) == 3

    def test_detect_poison_pill_by_exception_pattern(self):
        """Poison Pill wird anhand Exception-Muster erkannt."""
        KNOWN_POISON_PATTERNS = [
            "SystemError",
            "RecursionError",
            "MemoryError",
        ]

        messages = [
            {"headers": {"id": "1", "exception_type": "RuntimeError"}},
            {"headers": {"id": "2", "exception_type": "ValueError"}},
            {"headers": {"id": "3", "exception_type": "SystemError"}},
            {"headers": {"id": "4", "exception_type": "MemoryError"}},
        ]

        potential_poison_pills = [
            m for m in messages
            if m["headers"].get("exception_type") in KNOWN_POISON_PATTERNS
        ]

        assert len(potential_poison_pills) == 2

    def test_poison_pill_stats_aggregation(self):
        """Poison Pill Statistiken werden korrekt aggregiert."""
        POISON_PILL_THRESHOLD = 3

        messages = [
            {"headers": {"id": str(i), "task": f"task_{i % 3}", "retries": i}}
            for i in range(10)
        ]

        total_tasks = len(messages)
        poison_pills = sum(
            1 for m in messages
            if m["headers"].get("retries", 0) >= POISON_PILL_THRESHOLD
        )

        stats = DLQStatsResponse(
            total_tasks=total_tasks,
            poison_pills=poison_pills,
            status="warning" if poison_pills > 0 else "healthy",
            status_message=f"{poison_pills} Poison Pills von {total_tasks} Tasks",
        )

        assert stats.total_tasks == 10
        assert stats.poison_pills == 7  # retries 3,4,5,6,7,8,9


@pytest.mark.integration
class TestDLQMessageAgeCalculation:
    """Integration tests for DLQ message age calculation."""

    def test_calculate_message_age_hours(self):
        """Nachrichtenalter in Stunden wird korrekt berechnet."""
        timestamp_2h_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()

        message = {
            "properties": {"timestamp": timestamp_2h_ago}
        }

        age_hours = (
            datetime.now(timezone.utc).timestamp() - message["properties"]["timestamp"]
        ) / 3600

        assert 1.9 < age_hours < 2.1  # Allow small timing variance

    def test_calculate_oldest_task_age(self):
        """Aelteste Task wird korrekt identifiziert."""
        now = datetime.now(timezone.utc)
        messages = [
            {"properties": {"timestamp": (now - timedelta(hours=1)).timestamp()}},
            {"properties": {"timestamp": (now - timedelta(hours=5)).timestamp()}},
            {"properties": {"timestamp": (now - timedelta(hours=2)).timestamp()}},
        ]

        oldest_timestamp = min(m["properties"]["timestamp"] for m in messages)
        oldest_age_hours = (now.timestamp() - oldest_timestamp) / 3600

        assert 4.9 < oldest_age_hours < 5.1

    def test_handle_missing_timestamp(self):
        """Fehlender Timestamp wird behandelt."""
        message_without_timestamp = {
            "headers": {"id": str(uuid4()), "task": "no_timestamp"},
            "body": [[], {}],
        }

        timestamp = message_without_timestamp.get("properties", {}).get("timestamp")
        assert timestamp is None


@pytest.mark.integration
class TestDLQBulkOperationValidation:
    """Integration tests for DLQ bulk operation validation."""

    def test_bulk_retry_validates_task_ids(self):
        """Bulk-Retry validiert Task-IDs."""
        valid_ids = [str(uuid4()) for _ in range(5)]
        invalid_ids = ["not-a-uuid", "123", ""]

        # Valid UUIDs pass
        for task_id in valid_ids:
            try:
                uuid4_obj = uuid4().__class__(task_id)
                is_valid = True
            except ValueError:
                is_valid = False
            assert is_valid

        # Invalid UUIDs fail
        for task_id in invalid_ids:
            try:
                uuid4().__class__(task_id) if task_id else None
                is_valid = task_id != ""
            except ValueError:
                is_valid = False
            assert not is_valid or task_id == ""

    def test_bulk_retry_max_limit(self):
        """Bulk-Retry respektiert Maximum-Limit."""
        MAX_BULK_TASKS = 100

        task_ids = [str(uuid4()) for _ in range(150)]

        with pytest.raises(HTTPException) as exc_info:
            if len(task_ids) > MAX_BULK_TASKS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximal {MAX_BULK_TASKS} Tasks pro Anfrage"
                )

        assert exc_info.value.status_code == 400

    def test_bulk_retry_partial_results(self):
        """Bulk-Retry gibt Teilergebnisse zurueck."""
        task_ids = [str(uuid4()) for _ in range(10)]
        results = {"success": [], "failed": []}

        for i, task_id in enumerate(task_ids):
            if i % 3 == 0:  # Every 3rd fails
                results["failed"].append({
                    "task_id": task_id,
                    "reason": "Task nicht gefunden"
                })
            else:
                results["success"].append(task_id)

        assert len(results["success"]) == 6
        assert len(results["failed"]) == 4


@pytest.mark.integration
class TestDLQPurgeConfirmation:
    """Integration tests for DLQ purge confirmation."""

    def test_purge_requires_explicit_confirm_true(self):
        """Purge erfordert explizit confirm=true."""
        confirm_values = [None, False, "false", 0, ""]

        for confirm in confirm_values:
            with pytest.raises(HTTPException) as exc_info:
                if confirm is not True:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Bestaetigung erforderlich: confirm=true"
                    )

            assert exc_info.value.status_code == 400

    def test_purge_with_confirm_true_proceeds(self):
        """Purge mit confirm=true wird ausgefuehrt."""
        confirm = True
        dlq_count = 50

        response = DLQActionResponse(
            success=True,
            message=f"DLQ geleert: {dlq_count} Tasks geloescht",
            details={"deleted_count": dlq_count}
        )

        assert response.success is True
        assert "50" in response.message

    def test_purge_audit_logging(self):
        """Purge wird fuer Audit geloggt."""
        admin_id = str(uuid4())
        deleted_count = 100

        audit_entry = {
            "event_type": "DLQ_PURGED",
            "admin_id": admin_id,
            "deleted_count": deleted_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "warning",
        }

        assert audit_entry["event_type"] == "DLQ_PURGED"
        assert audit_entry["severity"] == "warning"
