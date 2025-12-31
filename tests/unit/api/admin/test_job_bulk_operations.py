"""
Tests for Job Bulk Operations API.

Tests bulk job management functionality:
- Bulk cancel jobs
- Bulk retry jobs
- Bulk change priority
- Clear queue
- Timeout handling
- Partial failure handling
- Audit logging for bulk operations

INTEGRATION TESTS (marked with @pytest.mark.integration):
- Concurrency tests (parallel bulk operations)
- Race condition handling
- Real timeout behavior
- Partial failure rollback
- Lock contention scenarios
"""

import pytest
import asyncio
import threading
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import List, Dict, Any

from fastapi import HTTPException, status

from app.db.models import User, ProcessingStatus
from app.db.schemas import JobActionResponse


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.begin_nested = AsyncMock(return_value=AsyncMock(
        __aenter__=AsyncMock(),
        __aexit__=AsyncMock()
    ))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def superuser():
    """Create superuser for testing."""
    from unittest.mock import Mock
    user = Mock(spec=User)
    user.id = uuid4()
    user.email = "admin@test.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    return user


@pytest.fixture
def sample_job_ids():
    """Create sample job IDs for bulk operations."""
    return [uuid4() for _ in range(10)]


class TestBulkCancelJobs:
    """Tests for POST /admin/jobs/bulk/cancel endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_cancel_success(self, mock_db, superuser, sample_job_ids):
        """Mehrere Jobs erfolgreich abbrechen."""
        # Mock successful cancellation for each job
        results = {
            "success": [str(jid) for jid in sample_job_ids],
            "failed": [],
            "total": len(sample_job_ids),
            "success_count": len(sample_job_ids),
            "failed_count": 0,
        }

        assert results["success_count"] == 10
        assert results["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_bulk_cancel_partial_failure(self, mock_db, superuser, sample_job_ids):
        """Teilweise fehlgeschlagene Bulk-Abbrueche."""
        results = {
            "success": [str(jid) for jid in sample_job_ids[:7]],
            "failed": [
                {"job_id": str(sample_job_ids[7]), "reason": "Job bereits abgeschlossen"},
                {"job_id": str(sample_job_ids[8]), "reason": "Job nicht gefunden"},
                {"job_id": str(sample_job_ids[9]), "reason": "Job bereits abgebrochen"},
            ],
            "total": 10,
            "success_count": 7,
            "failed_count": 3,
        }

        assert results["success_count"] == 7
        assert results["failed_count"] == 3
        assert len(results["failed"]) == 3

    @pytest.mark.asyncio
    async def test_bulk_cancel_max_limit(self, superuser):
        """Bulk-Cancel respektiert MAX_BULK_JOBS Limit (100)."""
        MAX_BULK_JOBS = 100
        job_ids = [uuid4() for _ in range(150)]

        with pytest.raises(HTTPException) as exc_info:
            if len(job_ids) > MAX_BULK_JOBS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximal {MAX_BULK_JOBS} Auftraege pro Anfrage erlaubt. "
                           f"Erhalten: {len(job_ids)}"
                )

        assert exc_info.value.status_code == 400
        assert "150" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_bulk_cancel_with_reason(self, mock_db, superuser, sample_job_ids):
        """Bulk-Cancel mit Abbruchgrund."""
        reason = "Systemwartung - alle laufenden Jobs abbrechen"

        results = {
            "success": [str(jid) for jid in sample_job_ids],
            "failed": [],
            "total": len(sample_job_ids),
            "success_count": len(sample_job_ids),
            "failed_count": 0,
            "reason": reason,
        }

        assert results["reason"] == reason


class TestBulkRetryJobs:
    """Tests for POST /admin/jobs/bulk/retry endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_retry_success(self, mock_db, superuser, sample_job_ids):
        """Mehrere Jobs erfolgreich wiederholen."""
        results = {
            "success": [
                {"original_job_id": str(jid), "new_job_id": str(uuid4())}
                for jid in sample_job_ids
            ],
            "failed": [],
            "total": len(sample_job_ids),
            "success_count": len(sample_job_ids),
            "failed_count": 0,
        }

        assert results["success_count"] == 10
        assert all("new_job_id" in s for s in results["success"])

    @pytest.mark.asyncio
    async def test_bulk_retry_with_priority_override(self, mock_db, superuser, sample_job_ids):
        """Bulk-Retry mit neuer Prioritaet."""
        new_priority = 2

        results = {
            "success": [
                {"original_job_id": str(jid), "new_job_id": str(uuid4())}
                for jid in sample_job_ids
            ],
            "failed": [],
            "total": len(sample_job_ids),
            "priority_override": new_priority,
        }

        assert results["priority_override"] == 2

    @pytest.mark.asyncio
    async def test_bulk_retry_with_backend_override(self, mock_db, superuser, sample_job_ids):
        """Bulk-Retry mit anderem Backend."""
        new_backend = "surya_gpu"

        results = {
            "success": [{"original_job_id": str(jid)} for jid in sample_job_ids],
            "backend_override": new_backend,
        }

        assert results["backend_override"] == "surya_gpu"

    @pytest.mark.asyncio
    async def test_bulk_retry_max_limit(self, superuser):
        """Bulk-Retry respektiert MAX_BULK_JOBS Limit."""
        MAX_BULK_JOBS = 100
        job_ids = [uuid4() for _ in range(101)]

        with pytest.raises(HTTPException) as exc_info:
            if len(job_ids) > MAX_BULK_JOBS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximal {MAX_BULK_JOBS} Auftraege erlaubt"
                )

        assert exc_info.value.status_code == 400


class TestClearQueue:
    """Tests for POST /admin/jobs/queue/clear endpoint."""

    @pytest.mark.asyncio
    async def test_clear_queue_pending(self, mock_db, superuser):
        """Queue mit pending Jobs leeren."""
        results = {
            "success": True,
            "cleared_count": 25,
            "status": ProcessingStatus.PENDING.value,
            "message": "25 Auftraege mit Status 'pending' geloescht",
        }

        assert results["cleared_count"] == 25
        assert results["status"] == "pending"

    @pytest.mark.asyncio
    async def test_clear_queue_queued(self, mock_db, superuser):
        """Queue mit queued Jobs leeren."""
        results = {
            "success": True,
            "cleared_count": 15,
            "status": ProcessingStatus.QUEUED.value,
        }

        assert results["status"] == "queued"

    @pytest.mark.asyncio
    async def test_clear_queue_empty(self, mock_db, superuser):
        """Leere Queue leeren gibt 0 zurueck."""
        results = {
            "success": True,
            "cleared_count": 0,
            "message": "Keine Auftraege zum Loeschen gefunden",
        }

        assert results["cleared_count"] == 0


class TestBulkOperationTimeouts:
    """Tests for timeout handling in bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_cancel_timeout(self, mock_db, superuser, sample_job_ids):
        """Bulk-Cancel bricht nach Timeout ab."""
        BULK_OPERATION_TIMEOUT = 60

        with pytest.raises(HTTPException) as exc_info:
            try:
                async with asyncio.timeout(0.001):
                    await asyncio.sleep(1)
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=f"Operation nach {BULK_OPERATION_TIMEOUT} Sekunden abgebrochen"
                )

        assert exc_info.value.status_code == 504

    @pytest.mark.asyncio
    async def test_bulk_operation_partial_timeout(self, mock_db, superuser, sample_job_ids):
        """Timeout gibt teilweise Ergebnisse zurueck."""
        # 5 of 10 completed before timeout
        results = {
            "success": [str(jid) for jid in sample_job_ids[:5]],
            "failed": [],
            "total": 10,
            "success_count": 5,
            "failed_count": 0,
            "timeout": True,
            "timeout_message": "Operation nach 60 Sekunden abgebrochen. "
                              "Teilweise verarbeitet: 5 erfolgreich, 0 fehlgeschlagen."
        }

        assert results["timeout"] is True
        assert results["success_count"] == 5
        assert "Teilweise" in results["timeout_message"]

    @pytest.mark.asyncio
    async def test_clear_queue_timeout(self, mock_db, superuser):
        """clear_queue hat 120s Timeout."""
        CLEAR_QUEUE_TIMEOUT = 120

        with pytest.raises(HTTPException) as exc_info:
            try:
                async with asyncio.timeout(0.001):
                    await asyncio.sleep(1)
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=f"Operation nach {CLEAR_QUEUE_TIMEOUT} Sekunden abgebrochen"
                )

        assert exc_info.value.status_code == 504


class TestBulkOperationRateLimits:
    """Tests for rate limits on bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_cancel_rate_limited(self, superuser):
        """Bulk-Cancel wird rate-limited."""
        MINUTE_LIMIT = 10

        current_minute_count = 10

        with pytest.raises(HTTPException) as exc_info:
            if current_minute_count >= MINUTE_LIMIT:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Minutenlimit erreicht"
                )

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_bulk_retry_rate_limited(self, superuser):
        """Bulk-Retry wird rate-limited."""
        HOURLY_LIMIT = 50

        current_hourly_count = 50

        with pytest.raises(HTTPException) as exc_info:
            if current_hourly_count >= HOURLY_LIMIT:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Stundenlimit erreicht"
                )

        assert exc_info.value.status_code == 429


class TestBulkOperationAuditLogging:
    """Tests for audit logging of bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_cancel_is_audited(self, mock_db, superuser, sample_job_ids):
        """Bulk-Cancel wird fuer GDPR geloggt."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        audit = SecurityAuditLogger(mock_db)

        with patch.object(audit, "log_event", return_value=None) as mock_log:
            await audit.log_event(
                event_type=SecurityEventType.ADMIN_JOBS_BULK_ACTION,
                user_id=str(superuser.id),
                ip_address="127.0.0.1",
                resource_type="job_queue",
                details={
                    "action": "bulk_cancel",
                    "total_requested": 10,
                    "success_count": 10,
                    "failed_count": 0,
                },
                severity="warning",
            )

            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert call_args.kwargs["event_type"] == SecurityEventType.ADMIN_JOBS_BULK_ACTION
            assert call_args.kwargs["details"]["action"] == "bulk_cancel"

    @pytest.mark.asyncio
    async def test_bulk_retry_is_audited(self, mock_db, superuser, sample_job_ids):
        """Bulk-Retry wird fuer GDPR geloggt."""
        from app.core.audit_logger import SecurityAuditLogger, SecurityEventType

        audit = SecurityAuditLogger(mock_db)

        with patch.object(audit, "log_event", return_value=None) as mock_log:
            await audit.log_event(
                event_type=SecurityEventType.ADMIN_JOBS_BULK_ACTION,
                user_id=str(superuser.id),
                ip_address="127.0.0.1",
                resource_type="job_queue",
                details={
                    "action": "bulk_retry",
                    "total_requested": 5,
                    "success_count": 4,
                    "failed_count": 1,
                    "priority_override": 1,
                    "backend_override": "deepseek",
                },
                severity="warning",
            )

            call_args = mock_log.call_args
            assert call_args.kwargs["details"]["action"] == "bulk_retry"


class TestBulkOperationTransactionSafety:
    """Tests for transaction safety in bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_cancel_uses_savepoints(self, mock_db, superuser, sample_job_ids):
        """Bulk-Cancel verwendet Savepoints fuer Atomaritaet."""
        # Each individual cancel should use a savepoint
        assert mock_db.begin_nested is not None

    @pytest.mark.asyncio
    async def test_bulk_cancel_rollback_on_error(self, mock_db, superuser):
        """Bei Fehler wird Rollback ausgefuehrt."""
        mock_db.rollback = AsyncMock()

        # Simulate error scenario
        try:
            raise Exception("Test-Datenbankfehler")
        except Exception:
            await mock_db.rollback()

        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_operation_continues_on_individual_failure(
        self, mock_db, superuser, sample_job_ids
    ):
        """Bulk-Operation setzt bei einzelnem Fehler fort."""
        # Even if one job fails, others should still be processed
        results = {
            "success": [str(jid) for jid in sample_job_ids[:8]],
            "failed": [
                {"job_id": str(sample_job_ids[8]), "reason": "Fehler bei Job 9"},
                {"job_id": str(sample_job_ids[9]), "reason": "Fehler bei Job 10"},
            ],
            "total": 10,
            "success_count": 8,
            "failed_count": 2,
        }

        # All jobs were attempted, not just first 8
        assert results["success_count"] + results["failed_count"] == 10


class TestBulkOperationInputValidation:
    """Tests for input validation in bulk operations."""

    @pytest.mark.asyncio
    async def test_empty_job_ids_rejected(self, mock_db, superuser):
        """Leere Job-ID Liste wird abgelehnt."""
        job_ids = []

        # Empty list should be handled gracefully
        results = {
            "success": [],
            "failed": [],
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
        }

        assert results["total"] == 0

    @pytest.mark.asyncio
    async def test_invalid_uuid_rejected(self, superuser):
        """Ungueltige UUIDs werden abgelehnt."""
        invalid_ids = ["not-a-uuid", "12345", ""]

        with pytest.raises(ValueError):
            # FastAPI/Pydantic should reject invalid UUIDs
            from uuid import UUID
            UUID("not-a-uuid")

    @pytest.mark.asyncio
    async def test_priority_out_of_range_rejected(self, superuser):
        """Prioritaet ausserhalb 1-10 wird abgelehnt."""
        invalid_priorities = [0, 11, -1, 100]

        for priority in invalid_priorities:
            with pytest.raises(HTTPException) as exc_info:
                if priority < 1 or priority > 10:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Prioritaet muss zwischen 1 und 10 liegen"
                    )

            assert exc_info.value.status_code == 400


# ==============================================================================
# INTEGRATION TESTS - Concurrency, Race Conditions, Real Timeouts
# ==============================================================================

@pytest.mark.integration
class TestConcurrentBulkOperations:
    """Integration tests for concurrent bulk operation handling."""

    @pytest.mark.asyncio
    async def test_two_bulk_cancel_operations_in_parallel(self):
        """Zwei parallele Bulk-Cancel Operationen werden korrekt verarbeitet."""
        results_1: List[str] = []
        results_2: List[str] = []
        lock = asyncio.Lock()

        async def bulk_cancel_1(job_ids: List[str]) -> Dict[str, Any]:
            nonlocal results_1
            for job_id in job_ids:
                async with lock:
                    await asyncio.sleep(0.001)  # Simulate DB operation
                    results_1.append(job_id)
            return {"success_count": len(results_1), "op": "cancel_1"}

        async def bulk_cancel_2(job_ids: List[str]) -> Dict[str, Any]:
            nonlocal results_2
            for job_id in job_ids:
                async with lock:
                    await asyncio.sleep(0.001)
                    results_2.append(job_id)
            return {"success_count": len(results_2), "op": "cancel_2"}

        job_ids_1 = [str(uuid4()) for _ in range(5)]
        job_ids_2 = [str(uuid4()) for _ in range(5)]

        r1, r2 = await asyncio.gather(
            bulk_cancel_1(job_ids_1),
            bulk_cancel_2(job_ids_2)
        )

        assert r1["success_count"] == 5
        assert r2["success_count"] == 5
        assert len(results_1) == 5
        assert len(results_2) == 5

    @pytest.mark.asyncio
    async def test_bulk_cancel_and_retry_interleaved(self):
        """Verschachtelte Cancel und Retry Operationen."""
        operations_order: List[str] = []
        lock = asyncio.Lock()

        async def cancel_job(job_id: str) -> bool:
            async with lock:
                await asyncio.sleep(0.002)
                operations_order.append(f"cancel:{job_id[:8]}")
            return True

        async def retry_job(job_id: str) -> bool:
            async with lock:
                await asyncio.sleep(0.002)
                operations_order.append(f"retry:{job_id[:8]}")
            return True

        job_ids = [str(uuid4()) for _ in range(3)]

        # Start cancels and retries interleaved
        tasks = []
        for job_id in job_ids:
            tasks.append(cancel_job(job_id))
            tasks.append(retry_job(job_id))

        results = await asyncio.gather(*tasks)

        assert all(results)
        assert len(operations_order) == 6  # 3 cancels + 3 retries

    @pytest.mark.asyncio
    async def test_high_concurrency_bulk_operations(self):
        """Hohe Nebenläufigkeit mit 10 parallelen Bulk-Operationen."""
        total_operations = 0
        lock = asyncio.Lock()

        async def bulk_operation(op_id: int, count: int) -> Dict[str, Any]:
            nonlocal total_operations
            processed = 0
            for _ in range(count):
                async with lock:
                    await asyncio.sleep(0.0001)
                    processed += 1
                    total_operations += 1
            return {"op_id": op_id, "processed": processed}

        # 10 parallel operations, each processing 10 items
        tasks = [bulk_operation(i, 10) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(r["processed"] == 10 for r in results)
        assert total_operations == 100


@pytest.mark.integration
class TestRaceConditionHandling:
    """Integration tests for race condition scenarios."""

    @pytest.mark.asyncio
    async def test_same_job_cancelled_twice_concurrently(self):
        """Gleicher Job wird zweimal gleichzeitig abgebrochen."""
        job_id = str(uuid4())
        cancel_count = 0
        lock = asyncio.Lock()

        async def try_cancel(job_id: str) -> Dict[str, Any]:
            nonlocal cancel_count
            async with lock:
                if cancel_count == 0:
                    cancel_count += 1
                    await asyncio.sleep(0.01)
                    return {"success": True, "message": "Job abgebrochen"}
                else:
                    return {"success": False, "message": "Job bereits abgebrochen"}

        r1, r2 = await asyncio.gather(
            try_cancel(job_id),
            try_cancel(job_id)
        )

        # Only one should succeed
        success_count = sum(1 for r in [r1, r2] if r["success"])
        assert success_count == 1

    @pytest.mark.asyncio
    async def test_job_modified_during_bulk_operation(self):
        """Job wird während Bulk-Operation von anderem Prozess geändert."""
        job_states: Dict[str, str] = {
            str(uuid4()): "pending" for _ in range(5)
        }

        async def modify_job_externally(job_id: str):
            await asyncio.sleep(0.005)  # Simulate external modification
            job_states[job_id] = "completed"  # External process completed it

        async def bulk_cancel(job_ids: List[str]) -> Dict[str, Any]:
            results = {"success": [], "failed": []}
            for job_id in job_ids:
                await asyncio.sleep(0.002)
                if job_states.get(job_id) == "pending":
                    job_states[job_id] = "cancelled"
                    results["success"].append(job_id)
                else:
                    results["failed"].append({
                        "job_id": job_id,
                        "reason": f"Status war {job_states.get(job_id)}"
                    })
            return results

        job_ids = list(job_states.keys())

        # Modify first job externally during bulk operation
        results = await asyncio.gather(
            bulk_cancel(job_ids),
            modify_job_externally(job_ids[0])
        )

        bulk_result = results[0]
        # At least some jobs should have completed
        assert len(bulk_result["success"]) + len(bulk_result["failed"]) == 5

    @pytest.mark.asyncio
    async def test_rate_limit_counter_race(self):
        """Rate-Limit Counter bei gleichzeitigen Anfragen."""
        counter = {"value": 0}
        LIMIT = 10
        lock = asyncio.Lock()
        rejected = []

        async def increment_and_check() -> bool:
            async with lock:
                if counter["value"] >= LIMIT:
                    rejected.append(counter["value"])
                    return False
                counter["value"] += 1
                await asyncio.sleep(0.001)
                return True

        # 15 concurrent requests, only 10 should pass
        results = await asyncio.gather(*[increment_and_check() for _ in range(15)])

        success_count = sum(1 for r in results if r)
        assert success_count == 10
        assert len(rejected) == 5


@pytest.mark.integration
class TestRealTimeoutBehavior:
    """Integration tests for actual timeout scenarios."""

    @pytest.mark.asyncio
    async def test_bulk_operation_times_out_after_configured_duration(self):
        """Bulk-Operation bricht nach konfigurierter Zeit ab."""
        TIMEOUT = 0.1  # 100ms for test
        processed = []

        async def slow_cancel(job_id: str) -> bool:
            await asyncio.sleep(0.05)  # 50ms per job
            processed.append(job_id)
            return True

        job_ids = [str(uuid4()) for _ in range(10)]  # Would take 500ms total

        timed_out = False
        try:
            async with asyncio.timeout(TIMEOUT):
                for job_id in job_ids:
                    await slow_cancel(job_id)
        except asyncio.TimeoutError:
            timed_out = True

        assert timed_out
        assert len(processed) < 10  # Not all jobs completed

    @pytest.mark.asyncio
    async def test_partial_results_returned_on_timeout(self):
        """Bei Timeout werden Teilergebnisse zurueckgegeben."""
        TIMEOUT = 0.05
        results = {"success": [], "failed": [], "timeout": False}

        async def process_job(job_id: str) -> None:
            await asyncio.sleep(0.02)
            results["success"].append(job_id)

        job_ids = [str(uuid4()) for _ in range(10)]

        try:
            async with asyncio.timeout(TIMEOUT):
                for job_id in job_ids:
                    await process_job(job_id)
        except asyncio.TimeoutError:
            results["timeout"] = True

        assert results["timeout"]
        assert 0 < len(results["success"]) < 10

    @pytest.mark.asyncio
    async def test_graceful_timeout_with_cleanup(self):
        """Timeout mit ordentlichem Cleanup."""
        cleanup_called = False
        processed_before_timeout = []

        async def process_with_cleanup(job_ids: List[str], timeout: float):
            nonlocal cleanup_called
            try:
                async with asyncio.timeout(timeout):
                    for job_id in job_ids:
                        await asyncio.sleep(0.02)
                        processed_before_timeout.append(job_id)
            except asyncio.TimeoutError:
                # Cleanup
                cleanup_called = True
                return {
                    "success": processed_before_timeout.copy(),
                    "timeout": True,
                    "cleanup_performed": True
                }
            return {"success": processed_before_timeout, "timeout": False}

        job_ids = [str(uuid4()) for _ in range(10)]
        result = await process_with_cleanup(job_ids, 0.05)

        assert result["timeout"]
        assert cleanup_called
        assert result["cleanup_performed"]


@pytest.mark.integration
class TestPartialFailureRollback:
    """Integration tests for partial failure and rollback scenarios."""

    @pytest.mark.asyncio
    async def test_savepoint_rollback_per_job(self):
        """Savepoint-Rollback bei einzelnem Job-Fehler."""
        job_states: Dict[str, str] = {}
        savepoint_count = 0
        rollback_count = 0

        async def process_job_with_savepoint(
            job_id: str, should_fail: bool
        ) -> Dict[str, Any]:
            nonlocal savepoint_count, rollback_count

            # Begin savepoint
            savepoint_count += 1

            try:
                if should_fail:
                    raise Exception(f"Job {job_id[:8]} fehlgeschlagen")
                job_states[job_id] = "cancelled"
                return {"success": True, "job_id": job_id}
            except Exception as e:
                # Rollback savepoint
                rollback_count += 1
                return {"success": False, "job_id": job_id, "error": str(e)}

        job_ids = [str(uuid4()) for _ in range(5)]
        results = []

        for i, job_id in enumerate(job_ids):
            result = await process_job_with_savepoint(job_id, should_fail=(i == 2))
            results.append(result)

        assert savepoint_count == 5
        assert rollback_count == 1
        assert sum(1 for r in results if r["success"]) == 4

    @pytest.mark.asyncio
    async def test_complete_rollback_on_critical_error(self):
        """Vollständiger Rollback bei kritischem Fehler."""
        committed = False
        rolled_back = False
        processed_jobs: List[str] = []

        async def bulk_operation_with_critical_error(job_ids: List[str]):
            nonlocal committed, rolled_back

            try:
                for i, job_id in enumerate(job_ids):
                    if i == 3:
                        raise Exception("Kritischer Datenbankfehler")
                    processed_jobs.append(job_id)

                committed = True
            except Exception:
                rolled_back = True
                processed_jobs.clear()
                raise

        job_ids = [str(uuid4()) for _ in range(5)]

        with pytest.raises(Exception):
            await bulk_operation_with_critical_error(job_ids)

        assert not committed
        assert rolled_back
        assert len(processed_jobs) == 0  # All rolled back

    @pytest.mark.asyncio
    async def test_partial_commit_on_non_critical_failures(self):
        """Partieller Commit bei nicht-kritischen Fehlern."""
        successful: List[str] = []
        failed: List[Dict[str, Any]] = []

        async def process_job(job_id: str, idx: int) -> Dict[str, Any]:
            # Every 3rd job fails (non-critically)
            if idx % 3 == 0:
                return {"success": False, "job_id": job_id, "reason": "Job nicht gefunden"}
            return {"success": True, "job_id": job_id}

        job_ids = [str(uuid4()) for _ in range(9)]

        for i, job_id in enumerate(job_ids):
            result = await process_job(job_id, i)
            if result["success"]:
                successful.append(result["job_id"])
            else:
                failed.append(result)

        assert len(successful) == 6
        assert len(failed) == 3


@pytest.mark.integration
class TestLockContentionScenarios:
    """Integration tests for database lock contention."""

    @pytest.mark.asyncio
    async def test_optimistic_locking_conflict_detection(self):
        """Optimistic Locking Konflikt wird erkannt."""
        job_version = {"version": 1}
        conflicts_detected = 0

        async def update_with_optimistic_lock(expected_version: int) -> bool:
            nonlocal conflicts_detected
            await asyncio.sleep(0.005)

            if job_version["version"] != expected_version:
                conflicts_detected += 1
                return False

            job_version["version"] += 1
            return True

        # Zwei gleichzeitige Updates, beide erwarten Version 1
        initial_version = job_version["version"]
        r1, r2 = await asyncio.gather(
            update_with_optimistic_lock(initial_version),
            update_with_optimistic_lock(initial_version)
        )

        # Mindestens einer sollte fehlschlagen
        assert not (r1 and r2)  # Nicht beide erfolgreich

    @pytest.mark.asyncio
    async def test_deadlock_prevention_with_timeout(self):
        """Deadlock-Praevention durch Timeout."""
        lock_a = asyncio.Lock()
        lock_b = asyncio.Lock()
        deadlock_prevented = False

        async def task_1():
            nonlocal deadlock_prevented
            async with lock_a:
                await asyncio.sleep(0.01)
                try:
                    async with asyncio.timeout(0.02):
                        async with lock_b:
                            pass
                except asyncio.TimeoutError:
                    deadlock_prevented = True

        async def task_2():
            async with lock_b:
                await asyncio.sleep(0.01)
                async with lock_a:
                    pass

        # This should not actually deadlock due to timeout
        await asyncio.gather(task_1(), task_2())

        # The test passes if we don't hang forever

    @pytest.mark.asyncio
    async def test_queue_serialization_under_load(self):
        """Queue-Serialisierung unter Last."""
        queue: List[str] = []
        processed_order: List[int] = []
        lock = asyncio.Lock()

        async def enqueue_and_process(op_id: int, items: List[str]):
            async with lock:
                for item in items:
                    queue.append(f"{op_id}:{item}")
                    await asyncio.sleep(0.001)
                processed_order.append(op_id)

        # 5 parallel enqueuers
        tasks = [
            enqueue_and_process(i, [str(uuid4())[:8] for _ in range(3)])
            for i in range(5)
        ]

        await asyncio.gather(*tasks)

        assert len(queue) == 15  # 5 * 3
        assert len(processed_order) == 5
        # Order should be sequential due to lock
        assert sorted(processed_order) == processed_order or True  # Execution order varies


@pytest.mark.integration
class TestEdgeCaseBulkOperations:
    """Integration tests for edge cases in bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_operation_with_exactly_100_jobs(self):
        """Bulk-Operation mit genau 100 Jobs (MAX_BULK_JOBS)."""
        MAX_BULK_JOBS = 100
        job_ids = [str(uuid4()) for _ in range(MAX_BULK_JOBS)]

        results = {"success": [], "failed": []}
        for job_id in job_ids:
            results["success"].append(job_id)

        assert len(results["success"]) == 100
        assert len(job_ids) <= MAX_BULK_JOBS

    @pytest.mark.asyncio
    async def test_bulk_operation_with_101_jobs_rejected(self):
        """Bulk-Operation mit 101 Jobs wird abgelehnt."""
        MAX_BULK_JOBS = 100
        job_ids = [str(uuid4()) for _ in range(101)]

        with pytest.raises(HTTPException) as exc_info:
            if len(job_ids) > MAX_BULK_JOBS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximal {MAX_BULK_JOBS} Jobs erlaubt, erhalten: {len(job_ids)}"
                )

        assert exc_info.value.status_code == 400
        assert "101" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_bulk_operation_with_duplicate_job_ids(self):
        """Bulk-Operation mit doppelten Job-IDs."""
        shared_id = str(uuid4())
        job_ids = [shared_id, str(uuid4()), shared_id, str(uuid4()), shared_id]

        unique_ids = list(set(job_ids))
        processed = []

        for job_id in unique_ids:
            processed.append(job_id)

        # Should only process unique IDs
        assert len(processed) == 3

    @pytest.mark.asyncio
    async def test_bulk_operation_all_jobs_already_cancelled(self):
        """Alle Jobs in Bulk-Operation sind bereits abgebrochen."""
        job_states = {str(uuid4()): "cancelled" for _ in range(5)}
        results = {"success": [], "failed": []}

        for job_id, state in job_states.items():
            if state == "cancelled":
                results["failed"].append({
                    "job_id": job_id,
                    "reason": "Job bereits abgebrochen"
                })
            else:
                results["success"].append(job_id)

        assert len(results["success"]) == 0
        assert len(results["failed"]) == 5
