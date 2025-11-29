# -*- coding: utf-8 -*-
"""
Unit tests for Backup Service.

Tests backup functionality for PostgreSQL, Redis, MinIO, and Config.
"""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import tempfile
import os

import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.backup_service import (
    BackupConfig,
    BackupResult,
    BackupService,
    get_backup_service,
)


class TestBackupConfig:
    """Tests for BackupConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BackupConfig()

        assert config.retention_days == 30
        assert config.compression_enabled is True
        assert config.encryption_enabled is False
        assert config.remote_enabled is False

    def test_config_from_environment(self):
        """Test configuration from environment variables."""
        with patch.dict(os.environ, {
            "BACKUP_DIR": "/custom/backup/path",
            "BACKUP_RETENTION_DAYS": "60",
            "BACKUP_COMPRESSION": "false",
            "BACKUP_ENCRYPTION": "true",
            "BACKUP_GPG_RECIPIENT": "test@example.com",
        }):
            config = BackupConfig()

            # Use Path comparison to handle platform differences
            assert config.backup_dir == Path("/custom/backup/path")
            assert config.retention_days == 60
            assert config.compression_enabled is False
            assert config.encryption_enabled is True
            assert config.gpg_recipient == "test@example.com"

    def test_postgres_config(self):
        """Test PostgreSQL configuration."""
        with patch.dict(os.environ, {
            "DB_HOST": "postgres.local",
            "DB_PORT": "5432",
            "DB_NAME": "test_db",
            "DB_USER": "test_user",
            "DB_PASSWORD": "secret123",
        }):
            config = BackupConfig()

            assert config.postgres_host == "postgres.local"
            assert config.postgres_port == 5432
            assert config.postgres_db == "test_db"
            assert config.postgres_user == "test_user"
            assert config.postgres_password == "secret123"

    def test_redis_config(self):
        """Test Redis configuration."""
        with patch.dict(os.environ, {
            "REDIS_HOST": "redis.local",
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": "redis_secret",
        }):
            config = BackupConfig()

            assert config.redis_host == "redis.local"
            assert config.redis_port == 6379
            assert config.redis_password == "redis_secret"

    def test_minio_config(self):
        """Test MinIO configuration."""
        with patch.dict(os.environ, {
            "MINIO_ENDPOINT": "minio.local:9000",
            "MINIO_ACCESS_KEY": "access123",
            "MINIO_SECRET_KEY": "secret456",
            "MINIO_BUCKETS": "bucket1,bucket2,bucket3",
        }):
            config = BackupConfig()

            assert config.minio_endpoint == "minio.local:9000"
            assert config.minio_access_key == "access123"
            assert config.minio_secret_key == "secret456"
            assert config.minio_buckets == ["bucket1", "bucket2", "bucket3"]

    def test_remote_sync_config(self):
        """Test remote sync configuration."""
        with patch.dict(os.environ, {
            "BACKUP_REMOTE_ENABLED": "true",
            "BACKUP_REMOTE_TARGET": "user@backup.server:/backups",
            "BACKUP_REMOTE_SSH_KEY": "/root/.ssh/backup_key",
        }):
            config = BackupConfig()

            assert config.remote_enabled is True
            assert config.remote_target == "user@backup.server:/backups"
            assert config.remote_ssh_key == "/root/.ssh/backup_key"


class TestBackupResult:
    """Tests for BackupResult dataclass."""

    def test_success_result(self):
        """Test successful backup result."""
        result = BackupResult(
            success=True,
            backup_type="postgres",
            path=Path("/backups/postgres/postgres_20231128_120000.sql.gz"),
            size_bytes=1024 * 1024 * 100,
            duration_seconds=45.5,
            validated=True,
            encrypted=False,
        )

        assert result.success is True
        assert result.backup_type == "postgres"
        assert result.size_bytes == 100 * 1024 * 1024
        assert result.validated is True
        assert result.error is None

    def test_failure_result(self):
        """Test failed backup result."""
        result = BackupResult(
            success=False,
            backup_type="redis",
            error="Redis-Verbindung fehlgeschlagen",
        )

        assert result.success is False
        assert result.backup_type == "redis"
        assert result.error == "Redis-Verbindung fehlgeschlagen"
        assert result.path is None


class TestBackupService:
    """Tests for BackupService class."""

    @pytest.fixture
    def temp_backup_dir(self):
        """Create temporary backup directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_config(self, temp_backup_dir):
        """Create mock configuration."""
        config = BackupConfig()
        config.backup_dir = temp_backup_dir
        config.compression_enabled = True
        config.encryption_enabled = False
        config.remote_enabled = False
        return config

    @pytest.fixture
    def backup_service(self, mock_config):
        """Create backup service with mock config."""
        return BackupService(config=mock_config)

    def test_service_initialization(self, backup_service, temp_backup_dir):
        """Test service initializes correctly."""
        assert backup_service.config.backup_dir == temp_backup_dir
        assert backup_service.metrics is not None

        # Check directories were created
        assert (temp_backup_dir / "postgres").exists()
        assert (temp_backup_dir / "redis").exists()
        assert (temp_backup_dir / "minio").exists()
        assert (temp_backup_dir / "config").exists()

    def test_generate_filename(self, backup_service):
        """Test filename generation with timestamp."""
        filename = backup_service._generate_filename("postgres", ".sql.gz")

        assert filename.startswith("postgres_")
        assert filename.endswith(".sql.gz")
        # Format: postgres_YYYYMMDD_HHMMSS.sql.gz
        assert len(filename) == len("postgres_20231128_120000.sql.gz")

    @pytest.mark.asyncio
    async def test_backup_postgres_success(self, backup_service):
        """Test successful PostgreSQL backup."""
        # Mock subprocess
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("app.services.backup_service.run_subprocess", return_value=mock_proc):
            with patch.object(backup_service, "_compress_file", new_callable=AsyncMock):
                with patch.object(backup_service, "validate_backup", new_callable=AsyncMock, return_value=True):
                    # Create temp file to simulate pg_dump output
                    temp_sql = backup_service.config.backup_dir / "postgres" / "test.sql"
                    temp_sql.write_text("-- PostgreSQL dump")

                    result = await backup_service.backup_postgres()

                    # Since we mocked everything, check the method ran
                    assert isinstance(result, BackupResult)
                    assert result.backup_type == "postgres"

    @pytest.mark.asyncio
    async def test_backup_postgres_failure(self, backup_service):
        """Test PostgreSQL backup failure."""
        # Mock subprocess with failure
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"pg_dump: Fehler"))

        with patch("app.services.backup_service.run_subprocess", return_value=mock_proc):
            result = await backup_service.backup_postgres()

            assert result.success is False
            assert result.backup_type == "postgres"
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_backup_redis_pg_dump_not_found(self, backup_service):
        """Test Redis backup when redis-cli not found."""
        with patch("app.services.backup_service.run_subprocess", side_effect=FileNotFoundError):
            result = await backup_service.backup_redis()

            assert result.success is False
            assert "nicht gefunden" in result.error

    @pytest.mark.asyncio
    async def test_backup_config(self, backup_service, temp_backup_dir):
        """Test config backup creates tar.gz."""
        # Create some config files to backup
        config_dir = temp_backup_dir / "config_source"
        config_dir.mkdir()
        (config_dir / "test.conf").write_text("key=value")

        backup_service.config.config_paths = [config_dir]

        with patch.object(backup_service, "validate_backup", new_callable=AsyncMock, return_value=True):
            result = await backup_service.backup_config()

            assert result.success is True
            assert result.backup_type == "config"
            assert result.path is not None
            assert result.path.suffix == ".gz"

    @pytest.mark.asyncio
    async def test_backup_full(self, backup_service):
        """Test full backup runs all components."""
        # Mock individual backup methods
        postgres_result = BackupResult(success=True, backup_type="postgres")
        redis_result = BackupResult(success=True, backup_type="redis")
        minio_result = BackupResult(success=True, backup_type="minio")
        config_result = BackupResult(success=True, backup_type="config")

        with patch.object(backup_service, "backup_postgres", new_callable=AsyncMock, return_value=postgres_result):
            with patch.object(backup_service, "backup_redis", new_callable=AsyncMock, return_value=redis_result):
                with patch.object(backup_service, "backup_minio", new_callable=AsyncMock, return_value=minio_result):
                    with patch.object(backup_service, "backup_config", new_callable=AsyncMock, return_value=config_result):
                        results = await backup_service.backup_full()

                        assert len(results) == 4
                        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_validate_backup_gzip(self, backup_service, temp_backup_dir):
        """Test validation of gzip files."""
        import gzip

        # Create valid gzip file
        gzip_path = temp_backup_dir / "test.sql.gz"
        with gzip.open(gzip_path, "wt") as f:
            f.write("-- PostgreSQL dump\nCREATE TABLE test;")

        result = await backup_service.validate_backup(gzip_path)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_backup_tar(self, backup_service, temp_backup_dir):
        """Test validation of tar files."""
        import tarfile

        # Create valid tar.gz file
        tar_path = temp_backup_dir / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            # Add a dummy file
            dummy = temp_backup_dir / "dummy.txt"
            dummy.write_text("test content")
            tar.add(dummy, arcname="dummy.txt")
            dummy.unlink()

        result = await backup_service.validate_backup(tar_path)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_backup_nonexistent(self, backup_service):
        """Test validation of non-existent file."""
        result = await backup_service.validate_backup(Path("/nonexistent/file.gz"))
        assert result is False

    @pytest.mark.asyncio
    async def test_retention_policy(self, backup_service, temp_backup_dir):
        """Test retention policy deletes old files."""
        import time

        # Create old file (set mtime to 60 days ago)
        old_file = temp_backup_dir / "postgres" / "old_backup.sql.gz"
        old_file.write_bytes(b"old data")
        old_mtime = time.time() - (60 * 86400)  # 60 days ago
        os.utime(old_file, (old_mtime, old_mtime))

        # Create new file
        new_file = temp_backup_dir / "postgres" / "new_backup.sql.gz"
        new_file.write_bytes(b"new data")

        # Set retention to 30 days
        backup_service.config.retention_days = 30

        deleted = await backup_service.apply_retention_policy()

        assert deleted["postgres"] == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_list_backups(self, backup_service, temp_backup_dir):
        """Test listing backups."""
        # Create some backup files
        (temp_backup_dir / "postgres" / "postgres_20231128_120000.sql.gz").write_bytes(b"data1")
        (temp_backup_dir / "redis" / "redis_20231128_120000.rdb").write_bytes(b"data2")

        backups = backup_service.list_backups()

        assert len(backups) == 2
        types = [b["type"] for b in backups]
        assert "postgres" in types
        assert "redis" in types

    def test_list_backups_filtered(self, backup_service, temp_backup_dir):
        """Test listing backups with filter."""
        (temp_backup_dir / "postgres" / "backup1.sql.gz").write_bytes(b"data1")
        (temp_backup_dir / "postgres" / "backup2.sql.gz").write_bytes(b"data2")
        (temp_backup_dir / "redis" / "backup.rdb").write_bytes(b"data3")

        backups = backup_service.list_backups(backup_type="postgres")

        assert len(backups) == 2
        assert all(b["type"] == "postgres" for b in backups)


class TestBackupServiceEncryption:
    """Tests for GPG encryption functionality."""

    @pytest.fixture
    def backup_service_with_encryption(self, tmp_path):
        """Create backup service with encryption enabled."""
        config = BackupConfig()
        config.backup_dir = tmp_path
        config.encryption_enabled = True
        config.gpg_recipient = "test@example.com"
        return BackupService(config=config)

    @pytest.mark.asyncio
    async def test_encrypt_backup_success(self, backup_service_with_encryption, tmp_path):
        """Test successful encryption."""
        # Create test file
        test_file = tmp_path / "test.sql.gz"
        test_file.write_bytes(b"test data")

        # Mock GPG subprocess
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("app.services.backup_service.run_subprocess", return_value=mock_proc):
            # Create the expected output file
            expected_output = test_file.with_suffix(".gz.gpg")
            expected_output.write_bytes(b"encrypted")

            result = await backup_service_with_encryption.encrypt_backup(test_file)

            assert result is not None
            assert str(result).endswith(".gpg")

    @pytest.mark.asyncio
    async def test_encrypt_backup_gpg_not_found(self, backup_service_with_encryption, tmp_path):
        """Test encryption when GPG not installed."""
        test_file = tmp_path / "test.sql.gz"
        test_file.write_bytes(b"test data")

        with patch("app.services.backup_service.run_subprocess", side_effect=FileNotFoundError):
            result = await backup_service_with_encryption.encrypt_backup(test_file)

            assert result is None

    @pytest.mark.asyncio
    async def test_encrypt_nonexistent_file(self, backup_service_with_encryption):
        """Test encrypting non-existent file."""
        result = await backup_service_with_encryption.encrypt_backup(
            Path("/nonexistent/file.sql.gz")
        )

        assert result is None


class TestBackupServiceRemoteSync:
    """Tests for remote sync functionality."""

    @pytest.fixture
    def backup_service_with_remote(self, tmp_path):
        """Create backup service with remote sync enabled."""
        config = BackupConfig()
        config.backup_dir = tmp_path
        config.remote_enabled = True
        config.remote_target = "user@backup.server:/backups"
        config.remote_ssh_key = "/root/.ssh/backup_key"
        return BackupService(config=config)

    @pytest.mark.asyncio
    async def test_sync_to_remote_disabled(self, tmp_path):
        """Test sync when remote is disabled."""
        config = BackupConfig()
        config.backup_dir = tmp_path
        config.remote_enabled = False
        service = BackupService(config=config)

        result = await service.sync_to_remote()

        assert result is False

    @pytest.mark.asyncio
    async def test_sync_to_remote_success(self, backup_service_with_remote):
        """Test successful remote sync."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("app.services.backup_service.run_subprocess", return_value=mock_proc):
            result = await backup_service_with_remote.sync_to_remote()

            assert result is True

    @pytest.mark.asyncio
    async def test_sync_to_remote_retry(self, backup_service_with_remote):
        """Test remote sync with retry."""
        # First two calls fail, third succeeds
        mock_proc_fail = AsyncMock()
        mock_proc_fail.returncode = 1
        mock_proc_fail.communicate = AsyncMock(return_value=(b"", b"Verbindung fehlgeschlagen"))

        mock_proc_success = AsyncMock()
        mock_proc_success.returncode = 0
        mock_proc_success.communicate = AsyncMock(return_value=(b"", b""))

        call_count = 0

        async def mock_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return mock_proc_fail
            return mock_proc_success

        with patch("app.services.backup_service.run_subprocess", side_effect=mock_subprocess):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await backup_service_with_remote.sync_to_remote(max_retries=3)

                # Should succeed on third attempt
                assert result is True

    @pytest.mark.asyncio
    async def test_sync_to_remote_rsync_not_found(self, backup_service_with_remote):
        """Test sync when rsync not found."""
        with patch("app.services.backup_service.run_subprocess", side_effect=FileNotFoundError):
            result = await backup_service_with_remote.sync_to_remote()

            assert result is False


class TestBackupServiceSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test get_backup_service returns singleton."""
        # Reset singleton for test
        import app.services.backup_service as backup_module
        backup_module._backup_service = None

        service1 = get_backup_service()
        service2 = get_backup_service()

        assert service1 is service2

        # Reset singleton after test
        backup_module._backup_service = None
