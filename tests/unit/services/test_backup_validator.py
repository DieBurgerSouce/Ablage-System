# -*- coding: utf-8 -*-
"""
Unit tests for Backup Validator Service.

Tests backup validation functionality:
- PostgreSQL dump validation
- Redis RDB validation
- MinIO backup validation
- Config archive validation
- GPG encrypted backup validation
- Checksum verification
"""

import asyncio
import gzip
import hashlib
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.backup_validator import (
    BackupValidator,
    ValidationLevel,
    ValidationStatus,
    ValidationResult,
    ValidationIssue,
    get_backup_validator,
)


class TestValidationLevel:
    """Tests for ValidationLevel enum."""

    def test_all_levels_defined(self):
        """Test all validation levels are defined."""
        assert ValidationLevel.QUICK.value == "quick"
        assert ValidationLevel.STANDARD.value == "standard"
        assert ValidationLevel.DEEP.value == "deep"
        assert ValidationLevel.FULL.value == "full"


class TestValidationStatus:
    """Tests for ValidationStatus enum."""

    def test_all_statuses_defined(self):
        """Test all validation statuses are defined."""
        assert ValidationStatus.VALID.value == "valid"
        assert ValidationStatus.INVALID.value == "invalid"
        assert ValidationStatus.WARNING.value == "warning"
        assert ValidationStatus.SKIPPED.value == "skipped"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test valid result properties."""
        result = ValidationResult(
            backup_path=Path("/backups/test.sql.gz"),
            backup_type="postgres",
            status=ValidationStatus.VALID,
            level=ValidationLevel.STANDARD,
            issues=[],
        )

        assert result.is_valid is True
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_warning_result(self):
        """Test result with warnings is still valid."""
        result = ValidationResult(
            backup_path=Path("/backups/test.sql.gz"),
            backup_type="postgres",
            status=ValidationStatus.WARNING,
            level=ValidationLevel.STANDARD,
            issues=[
                ValidationIssue(
                    severity="warning",
                    code="TEST_WARNING",
                    message="Test warning message"
                )
            ],
        )

        assert result.is_valid is True
        assert result.error_count == 0
        assert result.warning_count == 1

    def test_invalid_result(self):
        """Test invalid result properties."""
        result = ValidationResult(
            backup_path=Path("/backups/test.sql.gz"),
            backup_type="postgres",
            status=ValidationStatus.INVALID,
            level=ValidationLevel.STANDARD,
            issues=[
                ValidationIssue(
                    severity="error",
                    code="TEST_ERROR",
                    message="Test error message"
                )
            ],
        )

        assert result.is_valid is False
        assert result.error_count == 1
        assert result.warning_count == 0


class TestBackupValidator:
    """Tests for BackupValidator class."""

    @pytest.fixture
    def validator(self) -> BackupValidator:
        """Create BackupValidator instance."""
        return BackupValidator()

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    # =========================================================================
    # Type Detection Tests
    # =========================================================================

    def test_detect_postgres_backup(self, validator: BackupValidator, temp_dir: Path):
        """Test detection of PostgreSQL backup."""
        postgres_file = temp_dir / "postgres_20231128_120000.sql.gz"
        postgres_file.write_bytes(b"dummy")

        backup_type = validator._detect_backup_type(postgres_file)
        assert backup_type == "postgres"

    def test_detect_redis_backup(self, validator: BackupValidator, temp_dir: Path):
        """Test detection of Redis RDB backup."""
        redis_file = temp_dir / "redis_20231128_120000.rdb"
        redis_file.write_bytes(b"dummy")

        backup_type = validator._detect_backup_type(redis_file)
        assert backup_type == "redis"

    def test_detect_minio_backup(self, validator: BackupValidator, temp_dir: Path):
        """Test detection of MinIO backup."""
        minio_dir = temp_dir / "minio_20231128_120000"
        minio_dir.mkdir()

        backup_type = validator._detect_backup_type(minio_dir)
        assert backup_type == "minio"

    def test_detect_config_backup(self, validator: BackupValidator, temp_dir: Path):
        """Test detection of config backup."""
        config_file = temp_dir / "config_20231128_120000.tar.gz"
        config_file.write_bytes(b"dummy")

        backup_type = validator._detect_backup_type(config_file)
        assert backup_type == "config"

    def test_detect_encrypted_backup(self, validator: BackupValidator, temp_dir: Path):
        """Test detection of GPG encrypted backup."""
        encrypted_file = temp_dir / "postgres_20231128_120000.sql.gz.gpg"
        encrypted_file.write_bytes(b"dummy")

        backup_type = validator._detect_backup_type(encrypted_file)
        assert backup_type == "encrypted"

    def test_detect_by_parent_directory(self, validator: BackupValidator, temp_dir: Path):
        """Test detection by parent directory name."""
        postgres_dir = temp_dir / "postgres"
        postgres_dir.mkdir()
        backup_file = postgres_dir / "backup_123.gz"
        backup_file.write_bytes(b"dummy")

        backup_type = validator._detect_backup_type(backup_file)
        assert backup_type == "postgres"

    # =========================================================================
    # PostgreSQL Backup Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_validate_postgres_nonexistent(self, validator: BackupValidator):
        """Test validation of non-existent PostgreSQL backup."""
        result = await validator.validate_backup(
            Path("/nonexistent/postgres.sql.gz"),
            level=ValidationLevel.QUICK
        )

        assert result.status == ValidationStatus.INVALID
        assert result.error_count > 0
        assert any(i.code == "FILE_NOT_FOUND" for i in result.issues)

    @pytest.mark.asyncio
    async def test_validate_postgres_valid_quick(self, validator: BackupValidator, temp_dir: Path):
        """Test quick validation of valid PostgreSQL backup."""
        # Create valid gzip SQL file
        postgres_file = temp_dir / "postgres" / "postgres_20231128_120000.sql.gz"
        postgres_file.parent.mkdir(parents=True, exist_ok=True)

        with gzip.open(postgres_file, "wt", encoding="utf-8") as f:
            f.write("-- PostgreSQL dump\nCREATE TABLE users (id INT);")

        result = await validator.validate_backup(postgres_file, level=ValidationLevel.QUICK)

        assert result.status == ValidationStatus.VALID
        assert result.backup_type == "postgres"
        assert result.total_size_bytes > 0

    @pytest.mark.asyncio
    async def test_validate_postgres_too_small(self, validator: BackupValidator, temp_dir: Path):
        """Test validation rejects too-small PostgreSQL backup."""
        postgres_file = temp_dir / "postgres" / "small.sql.gz"
        postgres_file.parent.mkdir(parents=True, exist_ok=True)
        postgres_file.write_bytes(b"x" * 50)  # Very small file

        result = await validator.validate_backup(
            postgres_file,
            level=ValidationLevel.QUICK,
            expected_type="postgres"
        )

        assert result.status == ValidationStatus.INVALID
        assert any(i.code == "FILE_TOO_SMALL" for i in result.issues)

    @pytest.mark.asyncio
    async def test_validate_postgres_standard_with_tables(self, validator: BackupValidator, temp_dir: Path):
        """Test standard validation detects tables in PostgreSQL backup."""
        postgres_file = temp_dir / "postgres_backup.sql.gz"

        sql_content = """
        -- PostgreSQL database dump
        CREATE TABLE users (id SERIAL PRIMARY KEY, email VARCHAR(255));
        CREATE TABLE documents (id SERIAL PRIMARY KEY, title TEXT);
        CREATE TABLE tags (id SERIAL PRIMARY KEY, name VARCHAR(100));
        INSERT INTO users (email) VALUES ('test@example.com');
        """

        with gzip.open(postgres_file, "wt", encoding="utf-8") as f:
            f.write(sql_content)

        result = await validator.validate_backup(postgres_file, level=ValidationLevel.STANDARD)

        assert result.status in (ValidationStatus.VALID, ValidationStatus.WARNING)
        assert "tables_found" in result.metadata
        assert "users" in result.metadata["tables_found"]
        assert "documents" in result.metadata["tables_found"]

    @pytest.mark.asyncio
    async def test_validate_postgres_missing_tables(self, validator: BackupValidator, temp_dir: Path):
        """Test validation warns about missing expected tables."""
        postgres_file = temp_dir / "postgres_backup.sql.gz"

        sql_content = """
        -- PostgreSQL database dump
        CREATE TABLE random_table (id INT);
        INSERT INTO random_table (id) VALUES (1);
        """

        with gzip.open(postgres_file, "wt", encoding="utf-8") as f:
            f.write(sql_content)

        result = await validator.validate_backup(postgres_file, level=ValidationLevel.STANDARD)

        # Should have warning about missing tables
        assert any(i.code == "MISSING_TABLES" for i in result.issues)

    @pytest.mark.asyncio
    async def test_validate_postgres_no_data(self, validator: BackupValidator, temp_dir: Path):
        """Test validation warns when no INSERT statements found."""
        postgres_file = temp_dir / "postgres_backup.sql.gz"

        sql_content = """
        -- PostgreSQL database dump
        CREATE TABLE users (id INT);
        -- No INSERT statements
        """

        with gzip.open(postgres_file, "wt", encoding="utf-8") as f:
            f.write(sql_content)

        result = await validator.validate_backup(postgres_file, level=ValidationLevel.STANDARD)

        assert any(i.code == "NO_DATA" for i in result.issues)

    # =========================================================================
    # Redis Backup Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_validate_redis_valid(self, validator: BackupValidator, temp_dir: Path):
        """Test validation of valid Redis RDB backup."""
        redis_file = temp_dir / "redis" / "redis_20231128_120000.rdb"
        redis_file.parent.mkdir(parents=True, exist_ok=True)

        # Create valid RDB header: REDIS0011 (version 11)
        rdb_content = b"REDIS0011" + b"\x00" * 100 + b"\xff"
        redis_file.write_bytes(rdb_content)

        result = await validator.validate_backup(redis_file, level=ValidationLevel.STANDARD)

        assert result.status == ValidationStatus.VALID
        assert result.backup_type == "redis"
        assert "rdb_version" in result.metadata

    @pytest.mark.asyncio
    async def test_validate_redis_invalid_header(self, validator: BackupValidator, temp_dir: Path):
        """Test validation rejects Redis backup with invalid header."""
        redis_file = temp_dir / "redis" / "invalid.rdb"
        redis_file.parent.mkdir(parents=True, exist_ok=True)
        redis_file.write_bytes(b"INVALID_HEADER" + b"\x00" * 100)

        result = await validator.validate_backup(
            redis_file,
            level=ValidationLevel.STANDARD,
            expected_type="redis"
        )

        assert any(i.code == "INVALID_RDB_HEADER" for i in result.issues)

    @pytest.mark.asyncio
    async def test_validate_redis_missing_eof(self, validator: BackupValidator, temp_dir: Path):
        """Test validation warns about missing EOF marker in RDB."""
        redis_file = temp_dir / "redis" / "no_eof.rdb"
        redis_file.parent.mkdir(parents=True, exist_ok=True)

        # Valid header but no EOF marker
        rdb_content = b"REDIS0011" + b"\x00" * 100  # No 0xFF at end
        redis_file.write_bytes(rdb_content)

        result = await validator.validate_backup(redis_file, level=ValidationLevel.DEEP)

        assert any(i.code == "MISSING_EOF_MARKER" for i in result.issues)

    # =========================================================================
    # MinIO Backup Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_validate_minio_tar_valid(self, validator: BackupValidator, temp_dir: Path):
        """Test validation of valid MinIO tar.gz backup."""
        minio_file = temp_dir / "minio" / "minio_20231128_120000.tar.gz"
        minio_file.parent.mkdir(parents=True, exist_ok=True)

        # Create tar.gz with bucket structure
        with tarfile.open(minio_file, "w:gz") as tar:
            # Create bucket directories
            for bucket in ["documents", "processed", "thumbnails"]:
                bucket_dir = temp_dir / "minio_backup" / bucket
                bucket_dir.mkdir(parents=True, exist_ok=True)
                dummy_file = bucket_dir / "test.txt"
                dummy_file.write_text("test content")
                tar.add(bucket_dir, arcname=f"minio_backup/{bucket}")

        result = await validator.validate_backup(minio_file, level=ValidationLevel.STANDARD)

        assert result.status == ValidationStatus.VALID
        assert result.backup_type == "minio"
        assert result.file_count > 0

    @pytest.mark.asyncio
    async def test_validate_minio_directory(self, validator: BackupValidator, temp_dir: Path):
        """Test validation of MinIO backup as directory."""
        minio_dir = temp_dir / "minio" / "minio_20231128_120000"
        minio_dir.mkdir(parents=True, exist_ok=True)

        # Create bucket structure
        for bucket in ["documents", "processed"]:
            bucket_dir = minio_dir / bucket
            bucket_dir.mkdir()
            (bucket_dir / "test.txt").write_text("test content")

        result = await validator.validate_backup(minio_dir, level=ValidationLevel.STANDARD)

        assert result.status in (ValidationStatus.VALID, ValidationStatus.WARNING)
        assert result.backup_type == "minio"
        assert "buckets_found" in result.metadata

    @pytest.mark.asyncio
    async def test_validate_minio_missing_buckets(self, validator: BackupValidator, temp_dir: Path):
        """Test validation warns about missing buckets."""
        minio_dir = temp_dir / "minio" / "minio_backup"
        minio_dir.mkdir(parents=True, exist_ok=True)

        # Only create one bucket
        (minio_dir / "documents").mkdir()
        (minio_dir / "documents" / "test.txt").write_text("test")

        result = await validator.validate_backup(minio_dir, level=ValidationLevel.STANDARD)

        # Should warn about missing buckets (processed, thumbnails)
        assert any(i.code == "MISSING_BUCKETS" for i in result.issues)

    # =========================================================================
    # Config Backup Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_validate_config_valid(self, validator: BackupValidator, temp_dir: Path):
        """Test validation of valid config backup."""
        config_file = temp_dir / "config" / "config_20231128_120000.tar.gz"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Create config tar.gz
        with tarfile.open(config_file, "w:gz") as tar:
            # Create config files
            env_file = temp_dir / ".env"
            env_file.write_text("DATABASE_URL=postgres://...")
            tar.add(env_file, arcname=".env")

            app_dir = temp_dir / "app"
            app_dir.mkdir()
            (app_dir / "config.py").write_text("# Config")
            tar.add(app_dir, arcname="app")

        result = await validator.validate_backup(config_file, level=ValidationLevel.STANDARD)

        assert result.status in (ValidationStatus.VALID, ValidationStatus.WARNING)
        assert result.backup_type == "config"
        assert result.file_count > 0

    @pytest.mark.asyncio
    async def test_validate_config_missing_important_files(self, validator: BackupValidator, temp_dir: Path):
        """Test validation warns about missing important config files."""
        config_file = temp_dir / "config" / "incomplete.tar.gz"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Create tar.gz with only random file
        with tarfile.open(config_file, "w:gz") as tar:
            random_file = temp_dir / "random.txt"
            random_file.write_text("random content")
            tar.add(random_file, arcname="random.txt")

        result = await validator.validate_backup(config_file, level=ValidationLevel.STANDARD)

        assert any(i.code == "MISSING_CONFIG" for i in result.issues)

    # =========================================================================
    # Encrypted Backup Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_validate_encrypted_valid(self, validator: BackupValidator, temp_dir: Path):
        """Test validation of encrypted backup."""
        encrypted_file = temp_dir / "postgres_backup.sql.gz.gpg"

        # Create file with GPG binary format header
        gpg_content = bytes([0x85, 0x01, 0x00]) + b"\x00" * 200
        encrypted_file.write_bytes(gpg_content)

        result = await validator.validate_backup(encrypted_file, level=ValidationLevel.STANDARD)

        assert result.backup_type == "encrypted"
        assert "gpg_format" in result.metadata

    @pytest.mark.asyncio
    async def test_validate_encrypted_ascii_armored(self, validator: BackupValidator, temp_dir: Path):
        """Test validation of ASCII-armored GPG backup."""
        encrypted_file = temp_dir / "backup.gpg"
        encrypted_file.write_text(
            "-----BEGIN PGP MESSAGE-----\n"
            "hQEMA...\n"
            "-----END PGP MESSAGE-----"
        )

        result = await validator.validate_backup(encrypted_file, level=ValidationLevel.STANDARD)

        assert result.backup_type == "encrypted"

    @pytest.mark.asyncio
    async def test_validate_encrypted_too_small(self, validator: BackupValidator, temp_dir: Path):
        """Test validation rejects too-small encrypted file."""
        encrypted_file = temp_dir / "small.gpg"
        encrypted_file.write_bytes(b"x" * 50)

        result = await validator.validate_backup(
            encrypted_file,
            level=ValidationLevel.STANDARD,
            expected_type="encrypted"
        )

        assert any(i.code == "FILE_TOO_SMALL" for i in result.issues)

    @pytest.mark.asyncio
    async def test_validate_encrypted_detects_original_type(self, validator: BackupValidator, temp_dir: Path):
        """Test validation detects original backup type from filename."""
        # PostgreSQL backup
        pg_encrypted = temp_dir / "postgres_backup.sql.gz.gpg"
        pg_encrypted.write_bytes(bytes([0x85]) + b"\x00" * 200)

        result = await validator.validate_backup(pg_encrypted, level=ValidationLevel.STANDARD)
        assert result.metadata.get("original_type") == "postgres"

        # Redis backup
        redis_encrypted = temp_dir / "redis_backup.rdb.gpg"
        redis_encrypted.write_bytes(bytes([0x85]) + b"\x00" * 200)

        result = await validator.validate_backup(redis_encrypted, level=ValidationLevel.STANDARD)
        assert result.metadata.get("original_type") == "redis"

    # =========================================================================
    # Checksum Verification
    # =========================================================================

    @pytest.mark.asyncio
    async def test_calculate_checksum(self, validator: BackupValidator, temp_dir: Path):
        """Test checksum calculation."""
        test_file = temp_dir / "test.txt"
        test_content = b"Test content for checksum"
        test_file.write_bytes(test_content)

        expected_checksum = hashlib.sha256(test_content).hexdigest()
        actual_checksum = await validator._calculate_checksum(test_file)

        assert actual_checksum == expected_checksum

    @pytest.mark.asyncio
    async def test_verify_checksum_success(self, validator: BackupValidator, temp_dir: Path):
        """Test successful checksum verification."""
        test_file = temp_dir / "test.txt"
        test_content = b"Test content for checksum"
        test_file.write_bytes(test_content)

        expected_checksum = hashlib.sha256(test_content).hexdigest()

        result = await validator.verify_checksum(test_file, expected_checksum)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_checksum_failure(self, validator: BackupValidator, temp_dir: Path):
        """Test checksum verification failure."""
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"Test content")

        result = await validator.verify_checksum(test_file, "invalid_checksum_12345")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_checksum_nonexistent_file(self, validator: BackupValidator):
        """Test checksum verification for non-existent file."""
        result = await validator.verify_checksum(
            Path("/nonexistent/file.txt"),
            "any_checksum"
        )
        assert result is False

    # =========================================================================
    # Validate All Backups
    # =========================================================================

    @pytest.mark.asyncio
    async def test_validate_all_backups(self, validator: BackupValidator, temp_dir: Path):
        """Test validation of all backups in directory."""
        # Create backup directory structure
        (temp_dir / "postgres").mkdir()
        (temp_dir / "redis").mkdir()
        (temp_dir / "minio").mkdir()
        (temp_dir / "config").mkdir()

        # Create valid PostgreSQL backup
        pg_file = temp_dir / "postgres" / "backup.sql.gz"
        with gzip.open(pg_file, "wt") as f:
            f.write("-- PostgreSQL dump\nCREATE TABLE test (id INT);")

        # Create valid Redis backup
        redis_file = temp_dir / "redis" / "backup.rdb"
        redis_file.write_bytes(b"REDIS0011" + b"\x00" * 100 + b"\xff")

        results = await validator.validate_all_backups(temp_dir, level=ValidationLevel.QUICK)

        assert len(results) >= 2
        assert any(r.backup_type == "postgres" for r in results)
        assert any(r.backup_type == "redis" for r in results)

    # =========================================================================
    # Deep Validation Level
    # =========================================================================

    @pytest.mark.asyncio
    async def test_deep_validation_calculates_checksum(self, validator: BackupValidator, temp_dir: Path):
        """Test deep validation includes checksum calculation."""
        test_file = temp_dir / "postgres" / "backup.sql.gz"
        test_file.parent.mkdir(parents=True, exist_ok=True)

        with gzip.open(test_file, "wt") as f:
            f.write("-- PostgreSQL dump\nCREATE TABLE test (id INT);")

        result = await validator.validate_backup(test_file, level=ValidationLevel.DEEP)

        assert result.checksum_sha256 is not None
        assert len(result.checksum_sha256) == 64  # SHA256 hex length


class TestBackupValidatorSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test get_backup_validator returns singleton."""
        # Reset singleton for test
        import app.services.backup_validator as validator_module
        validator_module._validator_instance = None

        validator1 = get_backup_validator()
        validator2 = get_backup_validator()

        assert validator1 is validator2

        # Reset singleton after test
        validator_module._validator_instance = None


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_error_issue(self):
        """Test error issue creation."""
        issue = ValidationIssue(
            severity="error",
            code="TEST_ERROR",
            message="Test error message",
            details={"key": "value"}
        )

        assert issue.severity == "error"
        assert issue.code == "TEST_ERROR"
        assert issue.details == {"key": "value"}

    def test_warning_issue(self):
        """Test warning issue creation."""
        issue = ValidationIssue(
            severity="warning",
            code="TEST_WARNING",
            message="Test warning message"
        )

        assert issue.severity == "warning"
        assert issue.details is None

    def test_info_issue(self):
        """Test info issue creation."""
        issue = ValidationIssue(
            severity="info",
            code="TEST_INFO",
            message="Test info message"
        )

        assert issue.severity == "info"
