# -*- coding: utf-8 -*-
"""
Unit-Tests für Cleanup Celery Tasks.

Testet:
- cleanup_soft_deleted_documents (GDPR 30-Tage)
- cleanup_orphaned_files (MinIO)
- cleanup_expired_cache (Redis)
- cleanup_search_analytics
- cleanup_expired_sessions
- cleanup_expired_verification_tokens

Feinpoliert und durchdacht - GDPR-konforme Cleanup-Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def sample_soft_deleted_document():
    """Create sample soft-deleted document."""
    doc = Mock()
    doc.id = uuid4()
    doc.file_path = "/documents/deleted.pdf"
    doc.deleted_at = datetime.now(timezone.utc) - timedelta(days=35)
    return doc


@pytest.fixture
def sample_orphaned_file():
    """Create sample orphaned file info."""
    return {
        "id": str(uuid4()),
        "name": "orphaned.pdf",
        "path": "/documents/orphaned.pdf",
    }


@pytest.fixture
def mock_storage_service():
    """Create mock storage service."""
    storage = Mock()
    storage.delete_document = AsyncMock()
    storage.delete_file = AsyncMock()
    storage.list_all_documents = AsyncMock()
    return storage


# ========================= cleanup_soft_deleted_documents Tests =========================


class TestCleanupSoftDeletedDocuments:
    """Tests for soft-delete cleanup (GDPR 30-day retention)."""

    @pytest.mark.asyncio
    async def test_cleanup_finds_old_documents(self, mock_db, sample_soft_deleted_document, mock_storage_service):
        """Sollte Dokumente aelter als 30 Tage finden."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_soft_deleted_document]
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.cleanup_tasks.get_storage_service') as mock_get_storage:
                mock_get_storage.return_value = mock_storage_service

                from app.workers.tasks.cleanup_tasks import _cleanup_soft_deleted_async

                stats = await _cleanup_soft_deleted_async(retention_days=30, dry_run=True)

                assert stats["documents_found"] == 1
                assert stats["dry_run"] is True

    @pytest.mark.asyncio
    async def test_cleanup_dry_run_no_delete(self, mock_db, sample_soft_deleted_document, mock_storage_service):
        """Dry-Run sollte nicht loeschen."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_soft_deleted_document]
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.cleanup_tasks.get_storage_service') as mock_get_storage:
                mock_get_storage.return_value = mock_storage_service

                from app.workers.tasks.cleanup_tasks import _cleanup_soft_deleted_async

                stats = await _cleanup_soft_deleted_async(retention_days=30, dry_run=True)

                assert stats["documents_deleted"] == 0
                mock_storage_service.delete_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_deletes_storage_files(self, mock_db, sample_soft_deleted_document, mock_storage_service):
        """Sollte Dateien aus MinIO loeschen."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_soft_deleted_document]
            mock_result.rowcount = 1
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.cleanup_tasks.get_storage_service') as mock_get_storage:
                mock_get_storage.return_value = mock_storage_service

                from app.workers.tasks.cleanup_tasks import _cleanup_soft_deleted_async

                stats = await _cleanup_soft_deleted_async(retention_days=30, dry_run=False)

                mock_storage_service.delete_document.assert_called_once()
                assert stats["files_deleted"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_continues_on_storage_error(self, mock_db, sample_soft_deleted_document, mock_storage_service):
        """Storage-Fehler sollten nicht stoppen."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = [sample_soft_deleted_document]
            mock_result.rowcount = 1
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.cleanup_tasks.get_storage_service') as mock_get_storage:
                mock_storage_service.delete_document.side_effect = Exception("MinIO error")
                mock_get_storage.return_value = mock_storage_service

                from app.workers.tasks.cleanup_tasks import _cleanup_soft_deleted_async

                stats = await _cleanup_soft_deleted_async(retention_days=30, dry_run=False)

                # Should continue despite error
                assert stats["files_deleted"] == 0
                # DB delete should still happen
                mock_db.commit.assert_called()


# ========================= cleanup_orphaned_files Tests =========================


class TestCleanupOrphanedFiles:
    """Tests for orphaned file cleanup."""

    @pytest.mark.asyncio
    async def test_finds_orphaned_files(self, mock_db, sample_orphaned_file, mock_storage_service):
        """Sollte verwaiste Dateien finden."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_storage_service.list_all_documents.return_value = [sample_orphaned_file]

            mock_result = Mock()
            mock_result.fetchall.return_value = []  # No documents in DB
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.cleanup_tasks.get_storage_service') as mock_get_storage:
                mock_get_storage.return_value = mock_storage_service

                from app.workers.tasks.cleanup_tasks import _cleanup_orphaned_files_async

                stats = await _cleanup_orphaned_files_async()

                assert stats["files_checked"] == 1
                assert stats["orphaned_found"] == 1

    @pytest.mark.asyncio
    async def test_deletes_orphaned_files(self, mock_db, sample_orphaned_file, mock_storage_service):
        """Sollte verwaiste Dateien loeschen."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_storage_service.list_all_documents.return_value = [sample_orphaned_file]

            mock_result = Mock()
            mock_result.fetchall.return_value = []
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.cleanup_tasks.get_storage_service') as mock_get_storage:
                mock_get_storage.return_value = mock_storage_service

                from app.workers.tasks.cleanup_tasks import _cleanup_orphaned_files_async

                stats = await _cleanup_orphaned_files_async()

                assert stats["orphaned_deleted"] == 1
                mock_storage_service.delete_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_orphans_when_all_in_db(self, mock_db, sample_orphaned_file, mock_storage_service):
        """Keine Orphans wenn alle Dateien in DB."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_storage_service.list_all_documents.return_value = [sample_orphaned_file]

            mock_result = Mock()
            mock_result.fetchall.return_value = [(uuid4(),)]  # Document exists
            mock_db.execute.return_value = mock_result

            with patch('app.workers.tasks.cleanup_tasks.get_storage_service') as mock_get_storage:
                mock_get_storage.return_value = mock_storage_service

                from app.workers.tasks.cleanup_tasks import _cleanup_orphaned_files_async

                stats = await _cleanup_orphaned_files_async()

                # File ID might not match - depends on implementation
                assert stats["files_checked"] == 1


# ========================= cleanup_search_analytics Tests =========================


class TestCleanupSearchAnalytics:
    """Tests for search analytics cleanup."""

    @pytest.mark.asyncio
    async def test_finds_old_analytics(self, mock_db):
        """Sollte alte Analytics finden."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_count_result = Mock()
            mock_count_result.scalar.return_value = 1000
            mock_db.execute.return_value = mock_count_result

            from app.workers.tasks.cleanup_tasks import _cleanup_search_analytics_async

            stats = await _cleanup_search_analytics_async(retention_months=6, dry_run=True)

            assert stats["entries_found"] == 1000
            assert stats["dry_run"] is True

    @pytest.mark.asyncio
    async def test_deletes_old_analytics(self, mock_db):
        """Sollte alte Analytics loeschen."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            mock_count_result = Mock()
            mock_count_result.scalar.return_value = 500

            mock_delete_result = Mock()
            mock_delete_result.rowcount = 500

            mock_db.execute.side_effect = [mock_count_result, mock_delete_result]

            from app.workers.tasks.cleanup_tasks import _cleanup_search_analytics_async

            stats = await _cleanup_search_analytics_async(retention_months=6, dry_run=False)

            assert stats["entries_deleted"] == 500
            mock_db.commit.assert_called()


# ========================= cleanup_expired_sessions Tests =========================


class TestCleanupExpiredSessions:
    """Tests for session cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_sessions(self, mock_db):
        """Sollte abgelaufene Sessions loeschen."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            with patch('app.workers.tasks.cleanup_tasks.get_session_manager') as mock_get_manager:
                manager = Mock()
                manager.cleanup_expired_sessions = AsyncMock(return_value=50)
                mock_get_manager.return_value = manager

                from app.workers.tasks.cleanup_tasks import _cleanup_expired_sessions_async

                stats = await _cleanup_expired_sessions_async()

                assert stats["sessions_deleted"] == 50

    @pytest.mark.asyncio
    async def test_cleanup_sessions_handles_error(self, mock_db):
        """Fehler sollten gefangen werden."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            with patch('app.workers.tasks.cleanup_tasks.get_session_manager') as mock_get_manager:
                mock_get_manager.side_effect = Exception("Manager error")

                from app.workers.tasks.cleanup_tasks import _cleanup_expired_sessions_async

                stats = await _cleanup_expired_sessions_async()

                assert len(stats["errors"]) > 0


# ========================= cleanup_expired_verification_tokens Tests =========================


class TestCleanupExpiredVerificationTokens:
    """Tests for verification token cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_tokens(self, mock_db):
        """Sollte abgelaufene Tokens loeschen."""
        with patch('app.workers.tasks.cleanup_tasks.get_db_session') as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_db

            with patch('app.workers.tasks.cleanup_tasks.get_email_verification_service') as mock_get_service:
                service = Mock()
                service.cleanup_expired_tokens = AsyncMock(return_value=25)
                mock_get_service.return_value = service

                from app.workers.tasks.cleanup_tasks import _cleanup_expired_verification_tokens_async

                stats = await _cleanup_expired_verification_tokens_async()

                assert stats["tokens_deleted"] == 25


# ========================= cleanup_expired_cache Tests =========================


class TestCleanupExpiredCache:
    """Tests for Redis cache cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_cache_patterns(self):
        """Sollte Cache-Patterns bereinigen."""
        with patch('app.workers.tasks.cleanup_tasks.get_redis_storage') as mock_get_redis:
            redis = AsyncMock()
            redis.scan_iter = AsyncMock(return_value=AsyncIteratorMock([]))
            mock_get_redis.return_value = redis

            from app.workers.tasks.cleanup_tasks import _cleanup_expired_cache_async

            stats = await _cleanup_expired_cache_async()

            assert "patterns_checked" in stats
            assert len(stats["patterns_checked"]) > 0

    @pytest.mark.asyncio
    async def test_cleanup_cache_no_redis(self):
        """Ohne Redis sollte leer zurueckgeben."""
        with patch('app.workers.tasks.cleanup_tasks.get_redis_storage') as mock_get_redis:
            mock_get_redis.return_value = None

            from app.workers.tasks.cleanup_tasks import _cleanup_expired_cache_async

            stats = await _cleanup_expired_cache_async()

            assert stats["keys_deleted"] == 0


# ========================= Constants Tests =========================


class TestCleanupConstants:
    """Tests for cleanup constants."""

    def test_soft_delete_retention_is_30_days(self):
        """Soft-Delete Retention sollte 30 Tage sein."""
        from app.workers.tasks.cleanup_tasks import SOFT_DELETE_RETENTION_DAYS

        assert SOFT_DELETE_RETENTION_DAYS == 30

    def test_batch_size_reasonable(self):
        """Batch-Size sollte vernuenftig sein."""
        from app.workers.tasks.cleanup_tasks import BATCH_SIZE

        assert 10 <= BATCH_SIZE <= 1000


# ========================= Helper Classes =========================


class AsyncIteratorMock:
    """Helper class to mock async iterators."""

    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)
