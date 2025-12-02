"""Unit Tests fuer BackupValidator.

Tests fuer die Backup-Validierung aus dem Execution_Layer.
"""

import asyncio
import gzip
import hashlib
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

import pytest

import sys

# Add Execution_Layer to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "Execution_Layer"))

from Validators.backup_validator import (
    BackupValidationResult,
    BackupValidator,
)


class TestBackupValidationResult:
    """Tests fuer BackupValidationResult Datenstruktur."""

    def test_create_valid_result(self) -> None:
        """Test: Gueltiges Ergebnis kann erstellt werden."""
        result = BackupValidationResult(
            backup_file="/path/to/backup.sql.gz",
            backup_type="postgres",
            is_valid=True,
            checksum_verified=True,
            restoration_tested=True,
            data_integrity_ok=True,
            decryption_ok=True,
            errors=[],
            warnings=[],
            metadata={"file_size_mb": 100.5},
            duration_seconds=5.5,
        )

        assert result.is_valid
        assert result.checksum_verified
        assert result.restoration_tested
        assert result.data_integrity_ok
        assert result.decryption_ok
        assert len(result.errors) == 0
        assert result.metadata["file_size_mb"] == 100.5

    def test_create_invalid_result(self) -> None:
        """Test: Ungueltiges Ergebnis mit Fehlern."""
        result = BackupValidationResult(
            backup_file="/path/to/backup.sql.gz",
            backup_type="postgres",
            is_valid=False,
            checksum_verified=False,
            restoration_tested=False,
            data_integrity_ok=False,
            decryption_ok=True,
            errors=["Pruefsummen-Fehler", "Wiederherstellung fehlgeschlagen"],
            warnings=["Sicherung aelter als 26 Stunden"],
        )

        assert not result.is_valid
        assert not result.checksum_verified
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_to_dict(self) -> None:
        """Test: Konvertierung zu Dictionary."""
        result = BackupValidationResult(
            backup_file="/path/to/backup.sql.gz",
            backup_type="postgres",
            is_valid=True,
            checksum_verified=True,
            restoration_tested=True,
            data_integrity_ok=True,
            decryption_ok=True,
            metadata={"file_size_mb": 50.0},
            duration_seconds=3.2,
        )

        data = result.to_dict()

        assert data["backup_file"] == "/path/to/backup.sql.gz"
        assert data["backup_type"] == "postgres"
        assert data["is_valid"] is True
        assert "timestamp" in data
        assert data["duration_seconds"] == 3.2

    def test_default_values(self) -> None:
        """Test: Standard-Werte werden gesetzt."""
        result = BackupValidationResult(
            backup_file="test.sql",
            backup_type="full",
            is_valid=True,
            checksum_verified=True,
            restoration_tested=True,
            data_integrity_ok=True,
            decryption_ok=True,
        )

        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)
        assert isinstance(result.metadata, dict)
        assert result.duration_seconds == 0.0
        assert isinstance(result.timestamp, datetime)


class TestBackupValidatorInit:
    """Tests fuer BackupValidator Initialisierung."""

    def test_init_basic(self, tmp_path: Path) -> None:
        """Test: Basis-Initialisierung."""
        validator = BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
        )

        assert validator.db_url == "postgresql://test:test@localhost/test"
        assert validator.backup_dir == tmp_path
        assert validator.gpg_home is None
        assert validator.gpg_passphrase_file is None

    def test_init_with_gpg(self, tmp_path: Path) -> None:
        """Test: Initialisierung mit GPG-Konfiguration."""
        gpg_home = tmp_path / ".gnupg"
        gpg_passphrase = tmp_path / "passphrase.txt"
        gpg_home.mkdir()
        gpg_passphrase.write_text("secret")

        validator = BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
            gpg_home=gpg_home,
            gpg_passphrase_file=gpg_passphrase,
        )

        assert validator.gpg_home == gpg_home
        assert validator.gpg_passphrase_file == gpg_passphrase

    def test_expected_tables(self, tmp_path: Path) -> None:
        """Test: Erwartete Tabellen sind definiert."""
        validator = BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
        )

        assert "users" in validator.expected_tables
        assert "documents" in validator.expected_tables
        assert "ocr_results" in validator.expected_tables
        assert "audit_logs" in validator.expected_tables


class TestBackupValidatorValidation:
    """Tests fuer BackupValidator Validierungs-Methoden."""

    @pytest.fixture
    def validator(self, tmp_path: Path) -> BackupValidator:
        """Erstellt einen Validator fuer Tests."""
        return BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
            emit_metrics=False,
        )

    @pytest.fixture
    def sample_backup_file(self, tmp_path: Path) -> Path:
        """Erstellt eine Test-Backup-Datei."""
        backup_file = tmp_path / "backup.sql.gz"

        # Erstelle gzip-komprimierte SQL-Datei
        sql_content = b"-- PostgreSQL dump\nCREATE TABLE test (id INT);\n"
        with gzip.open(backup_file, "wb") as f:
            f.write(sql_content)

        return backup_file

    @pytest.fixture
    def sample_checksum_file(self, sample_backup_file: Path) -> Path:
        """Erstellt eine Checksum-Datei fuer das Backup."""
        checksum_file = Path(str(sample_backup_file) + ".sha256")

        # Berechne Checksum
        sha256 = hashlib.sha256()
        with open(sample_backup_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        checksum = sha256.hexdigest()
        checksum_file.write_text(f"{checksum}  {sample_backup_file.name}\n")

        return checksum_file

    # =========================================================================
    # File Existence Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_validate_missing_file(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: Fehlende Backup-Datei wird erkannt."""
        missing_file = tmp_path / "nonexistent.sql.gz"

        result = await validator.validate_backup(missing_file)

        assert not result.is_valid
        assert any("nicht gefunden" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_existing_file(
        self,
        validator: BackupValidator,
        sample_backup_file: Path,
        sample_checksum_file: Path,
    ) -> None:
        """Test: Existierende Backup-Datei wird gefunden."""
        result = await validator.validate_backup(
            sample_backup_file,
            skip_restoration_test=True,
        )

        # Datei existiert, also kein "nicht gefunden" Fehler
        assert not any("nicht gefunden" in error for error in result.errors)

    # =========================================================================
    # Checksum Verification Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_verify_checksum_valid(
        self,
        validator: BackupValidator,
        sample_backup_file: Path,
        sample_checksum_file: Path,
    ) -> None:
        """Test: Gueltige Pruefsumme wird verifiziert."""
        result = await validator._verify_checksum(sample_backup_file)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_checksum_missing_file(
        self, validator: BackupValidator, sample_backup_file: Path
    ) -> None:
        """Test: Fehlende Pruefsummen-Datei wird erkannt."""
        # Keine Checksum-Datei erstellen
        result = await validator._verify_checksum(sample_backup_file)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_checksum_mismatch(
        self,
        validator: BackupValidator,
        sample_backup_file: Path,
    ) -> None:
        """Test: Falsche Pruefsumme wird erkannt."""
        # Erstelle Checksum-Datei mit falscher Pruefsumme
        checksum_file = Path(str(sample_backup_file) + ".sha256")
        checksum_file.write_text("invalid_checksum  backup.sql.gz\n")

        result = await validator._verify_checksum(sample_backup_file)

        assert result is False

    # =========================================================================
    # File Readability Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_verify_file_readable_gzip(
        self, validator: BackupValidator, sample_backup_file: Path
    ) -> None:
        """Test: Gzip-Datei kann gelesen werden."""
        result = await validator._verify_file_readable(sample_backup_file)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_file_readable_corrupted_gzip(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: Korrupte Gzip-Datei wird erkannt."""
        corrupted_file = tmp_path / "corrupted.sql.gz"
        corrupted_file.write_bytes(b"not valid gzip content")

        result = await validator._verify_file_readable(corrupted_file)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_file_readable_sql(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: SQL-Datei kann gelesen werden."""
        sql_file = tmp_path / "backup.sql"
        sql_file.write_text("CREATE TABLE test;")

        result = await validator._verify_file_readable(sql_file)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_file_readable_empty_file(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: Leere Datei wird als ungueltig erkannt."""
        empty_file = tmp_path / "empty.bin"
        empty_file.write_bytes(b"")

        result = await validator._verify_file_readable(empty_file)

        assert result is False

    # =========================================================================
    # Backup Age Tests
    # =========================================================================

    def test_check_backup_age_recent(
        self, validator: BackupValidator, sample_backup_file: Path
    ) -> None:
        """Test: Aktuelle Backup-Datei hat niedriges Alter."""
        age_hours = validator._check_backup_age(sample_backup_file)

        # Gerade erstellte Datei sollte < 1 Stunde alt sein
        assert age_hours < 1.0

    def test_check_backup_age_type(
        self, validator: BackupValidator, sample_backup_file: Path
    ) -> None:
        """Test: Alter wird als Float zurueckgegeben."""
        age_hours = validator._check_backup_age(sample_backup_file)

        assert isinstance(age_hours, float)

    # =========================================================================
    # Database Backup Detection Tests
    # =========================================================================

    def test_is_database_backup_sql_gz(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: .sql.gz wird als Datenbank-Backup erkannt."""
        backup_file = tmp_path / "backup.sql.gz"
        backup_file.touch()

        assert validator._is_database_backup(backup_file) is True

    def test_is_database_backup_ablage_prefix(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: ablage_* wird als Datenbank-Backup erkannt."""
        backup_file = tmp_path / "ablage_20240101.dump"
        backup_file.touch()

        assert validator._is_database_backup(backup_file) is True

    def test_is_database_backup_other_file(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: Andere Dateien werden nicht als DB-Backup erkannt."""
        backup_file = tmp_path / "config_backup.tar.gz"
        backup_file.touch()

        assert validator._is_database_backup(backup_file) is False


class TestBackupValidatorReport:
    """Tests fuer Report-Generierung."""

    @pytest.fixture
    def validator(self, tmp_path: Path) -> BackupValidator:
        """Erstellt einen Validator fuer Tests."""
        return BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
            emit_metrics=False,
        )

    def test_generate_report_german(self, validator: BackupValidator) -> None:
        """Test: Deutscher Report wird generiert."""
        results = [
            BackupValidationResult(
                backup_file="/backups/backup_2024.sql.gz",
                backup_type="postgres",
                is_valid=True,
                checksum_verified=True,
                restoration_tested=True,
                data_integrity_ok=True,
                decryption_ok=True,
                metadata={"age_hours": 5.0, "file_size_mb": 100.0},
            )
        ]

        report = validator.generate_report(results, include_german=True)

        assert "Sicherungs-Validierungsbericht" in report
        assert "Gueltige Sicherungen" in report
        assert "GUELTIG" in report

    def test_generate_report_english(self, validator: BackupValidator) -> None:
        """Test: Englischer Report wird generiert."""
        results = [
            BackupValidationResult(
                backup_file="/backups/backup_2024.sql.gz",
                backup_type="postgres",
                is_valid=True,
                checksum_verified=True,
                restoration_tested=True,
                data_integrity_ok=True,
                decryption_ok=True,
            )
        ]

        report = validator.generate_report(results, include_german=False)

        assert "Backup Validation Report" in report
        assert "Valid Backups" in report
        assert "VALID" in report

    def test_generate_report_with_errors(self, validator: BackupValidator) -> None:
        """Test: Report enthaelt Fehler."""
        results = [
            BackupValidationResult(
                backup_file="/backups/bad_backup.sql.gz",
                backup_type="postgres",
                is_valid=False,
                checksum_verified=False,
                restoration_tested=False,
                data_integrity_ok=False,
                decryption_ok=True,
                errors=["Pruefsummen-Fehler", "Wiederherstellung fehlgeschlagen"],
                warnings=["Sicherung aelter als 26 Stunden"],
            )
        ]

        report = validator.generate_report(results, include_german=True)

        assert "UNGUELTIG" in report
        assert "Fehler" in report
        assert "Warnungen" in report
        assert "Pruefsummen-Fehler" in report

    def test_generate_report_multiple_backups(self, validator: BackupValidator) -> None:
        """Test: Report mit mehreren Backups."""
        results = [
            BackupValidationResult(
                backup_file="/backups/backup_1.sql.gz",
                backup_type="postgres",
                is_valid=True,
                checksum_verified=True,
                restoration_tested=True,
                data_integrity_ok=True,
                decryption_ok=True,
            ),
            BackupValidationResult(
                backup_file="/backups/backup_2.sql.gz",
                backup_type="postgres",
                is_valid=False,
                checksum_verified=False,
                restoration_tested=False,
                data_integrity_ok=False,
                decryption_ok=True,
                errors=["Test-Fehler"],
            ),
        ]

        report = validator.generate_report(results, include_german=True)

        assert "Gesamt Sicherungen: 2" in report
        assert "Gueltige Sicherungen: 1/2" in report
        assert "backup_1.sql.gz" in report
        assert "backup_2.sql.gz" in report


class TestBackupValidatorDecryption:
    """Tests fuer Entschluesselungs-Handling."""

    @pytest.fixture
    def validator_with_gpg(self, tmp_path: Path) -> BackupValidator:
        """Erstellt einen Validator mit GPG-Konfiguration."""
        gpg_home = tmp_path / ".gnupg"
        gpg_passphrase = tmp_path / "passphrase.txt"
        gpg_home.mkdir()
        gpg_passphrase.write_text("secret")

        return BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
            gpg_home=gpg_home,
            gpg_passphrase_file=gpg_passphrase,
            emit_metrics=False,
        )

    @pytest.fixture
    def validator_without_gpg(self, tmp_path: Path) -> BackupValidator:
        """Erstellt einen Validator ohne GPG-Konfiguration."""
        return BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
            emit_metrics=False,
        )

    @pytest.mark.asyncio
    async def test_handle_decryption_without_gpg_config(
        self, validator_without_gpg: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: Fehlende GPG-Konfiguration wird erkannt."""
        encrypted_file = tmp_path / "backup.sql.gz.gpg"
        encrypted_file.write_bytes(b"encrypted content")

        success, _, errors = await validator_without_gpg._handle_decryption(
            encrypted_file
        )

        assert success is False
        assert any("GPG-Konfiguration" in error for error in errors)

    @pytest.mark.asyncio
    async def test_handle_decryption_missing_passphrase_file(
        self, tmp_path: Path
    ) -> None:
        """Test: Fehlende Passphrase-Datei wird erkannt."""
        gpg_home = tmp_path / ".gnupg"
        gpg_passphrase = tmp_path / "nonexistent_passphrase.txt"
        gpg_home.mkdir()

        validator = BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
            gpg_home=gpg_home,
            gpg_passphrase_file=gpg_passphrase,
            emit_metrics=False,
        )

        encrypted_file = tmp_path / "backup.sql.gz.gpg"
        encrypted_file.write_bytes(b"encrypted content")

        success, _, errors = await validator._handle_decryption(encrypted_file)

        assert success is False
        assert any("Passphrase-Datei nicht gefunden" in error for error in errors)


class TestBackupValidatorIntegration:
    """Integration Tests fuer BackupValidator."""

    @pytest.fixture
    def validator(self, tmp_path: Path) -> BackupValidator:
        """Erstellt einen Validator fuer Tests."""
        return BackupValidator(
            db_connection_string="postgresql://test:test@localhost/test",
            backup_dir=tmp_path,
            emit_metrics=False,
        )

    @pytest.mark.asyncio
    async def test_validate_backup_full_workflow(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: Vollstaendiger Validierungs-Workflow (ohne Restoration)."""
        # Erstelle gueltige Backup-Datei
        backup_file = tmp_path / "ablage_backup.sql.gz"
        sql_content = b"-- PostgreSQL dump\nCREATE TABLE test (id INT);\n"
        with gzip.open(backup_file, "wb") as f:
            f.write(sql_content)

        # Erstelle gueltige Checksum
        sha256 = hashlib.sha256()
        with open(backup_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        checksum = sha256.hexdigest()
        checksum_file = Path(str(backup_file) + ".sha256")
        checksum_file.write_text(f"{checksum}  {backup_file.name}\n")

        # Validiere
        result = await validator.validate_backup(
            backup_file,
            backup_type="postgres",
            skip_restoration_test=True,
        )

        assert result.checksum_verified is True
        assert result.backup_type == "postgres"
        assert result.metadata.get("file_size_mb") is not None

    @pytest.mark.asyncio
    async def test_validate_all_backups_empty_dir(
        self, validator: BackupValidator
    ) -> None:
        """Test: Leeres Backup-Verzeichnis."""
        results = await validator.validate_all_backups(
            max_age_hours=168,
            skip_restoration_test=True,
        )

        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_validate_all_backups_with_files(
        self, validator: BackupValidator, tmp_path: Path
    ) -> None:
        """Test: Backup-Verzeichnis mit Dateien."""
        # Erstelle postgres Unterverzeichnis
        postgres_dir = tmp_path / "postgres"
        postgres_dir.mkdir()

        # Erstelle Test-Backup
        backup_file = postgres_dir / "backup.sql.gz"
        sql_content = b"-- PostgreSQL dump\n"
        with gzip.open(backup_file, "wb") as f:
            f.write(sql_content)

        results = await validator.validate_all_backups(
            max_age_hours=168,
            skip_restoration_test=True,
        )

        assert len(results) == 1
        assert results[0].backup_type == "postgres"
