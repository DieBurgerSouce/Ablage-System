# -*- coding: utf-8 -*-
"""
Integration tests for Backup API endpoints.

Tests the backup API endpoints with mocked services.

W3b (2026-06-12): Lokal lauffaehig gemacht (W3-Triage-Rezept):
- Rate-Limiter fail-open via Settings-Override (TestClient-IP "testclient"
  ist nicht whitelisted -> fail-closed maskierte ALLE Requests als 503).
- Dummy-Bearer-Header am Client: aktiviert den bearer_token_bypass der
  CSRF-Middleware fuer die POST-Endpoints (Auth laeuft ohnehin ueber
  dependency_overrides, der Header-Inhalt ist irrelevant).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path

import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.main import app
from app.services.backup_service import BackupResult
from app.api.dependencies import get_current_superuser


@pytest.fixture(autouse=True)
def _rate_limiter_fail_open(monkeypatch):
    """Rate-Limiter lokal fail-open stellen (W3-Triage-Rezept).

    Ohne erreichbares Redis antwortet der fail-closed Rate-Limiter sonst
    pauschal mit 503 und maskiert die echte Endpoint-Antwort.
    """
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "RATE_LIMIT_FAIL_CLOSED", False)
    monkeypatch.setattr(app_settings, "RATE_LIMIT_FAIL_CLOSED_CRITICAL", False)


@pytest.fixture
def mock_superuser():
    """Create mock superuser for authentication."""
    user = Mock()
    user.id = "test-admin-id"
    user.email = "admin@test.com"
    user.is_superuser = True
    user.is_active = True
    return user


@pytest.fixture
def mock_backup_service():
    """Create mock backup service."""
    service = Mock()
    service.config = Mock()
    service.config.backup_dir = Path("/var/backups/ablage")
    service.config.encryption_enabled = True
    service.config.remote_enabled = True
    service.config.remote_target = "user@backup:/backups"
    service.config.retention_days = 30
    service.metrics = Mock()
    return service


@pytest.fixture
def client(mock_superuser):
    """Create test client with dependency overrides.

    Der Dummy-Bearer-Header sorgt fuer den CSRF-bearer_token_bypass bei
    POST-Requests; die Authentifizierung selbst kommt aus dem Override.
    """
    # Override authentication dependency
    app.dependency_overrides[get_current_superuser] = lambda: mock_superuser

    yield TestClient(app, headers={"Authorization": "Bearer test-token"})

    # Clean up overrides
    app.dependency_overrides.clear()


class TestBackupStatusEndpoint:
    """Tests for GET /api/v1/backup/status endpoint."""

    def test_status_requires_auth(self):
        """Test that status endpoint requires authentication."""
        # Create a client without auth overrides
        test_client = TestClient(app)
        response = test_client.get("/api/v1/backup/status")
        assert response.status_code in [401, 403]

    def test_status_returns_info(self, client, mock_backup_service):
        """Test status endpoint returns backup system info."""
        from app.services.backup_metrics_service import DiskUsageData

        # Mock disk usage
        mock_disk = DiskUsageData(
            total_bytes=500 * 1024**3,
            used_bytes=200 * 1024**3,
            free_bytes=300 * 1024**3,
            usage_percent=40.0,
        )
        mock_backup_service.metrics.update_disk_usage.return_value = mock_disk
        mock_backup_service.metrics.update_backup_file_counts.return_value = {
            "postgres": 5,
            "redis": 5,
            "minio": 3,
            "config": 10,
        }

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.get("/api/v1/backup/status")

            assert response.status_code == 200
            data = response.json()
            assert "service_aktiv" in data
            assert "encryption_aktiviert" in data
            assert "speicherplatz" in data


class TestBackupListEndpoint:
    """Tests for GET /api/v1/backup/list endpoint."""

    def test_list_requires_auth(self):
        """Test that list endpoint requires authentication."""
        test_client = TestClient(app)
        response = test_client.get("/api/v1/backup/list")
        assert response.status_code in [401, 403]

    def test_list_returns_backups(self, client, mock_backup_service):
        """Test list endpoint returns backup files."""
        mock_backup_service.list_backups.return_value = [
            {
                "type": "postgres",
                "name": "postgres_20231128_120000.sql.gz",
                "path": "/backups/postgres/postgres_20231128_120000.sql.gz",
                "size_bytes": 100 * 1024 * 1024,
                "size_mb": 100.0,
                "created": "2023-11-28T12:00:00",
                "encrypted": False,
            }
        ]

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.get("/api/v1/backup/list")

            assert response.status_code == 200
            data = response.json()
            assert "anzahl" in data
            assert "backups" in data
            assert data["anzahl"] == 1


class TestBackupPostgresEndpoint:
    """Tests for POST /api/v1/backup/postgres endpoint."""

    def test_postgres_requires_auth(self):
        """Test that postgres backup requires authentication."""
        test_client = TestClient(app)
        response = test_client.post("/api/v1/backup/postgres")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_postgres_backup_success(self, client, mock_backup_service):
        """Test successful postgres backup."""
        mock_result = BackupResult(
            success=True,
            backup_type="postgres",
            path=Path("/backups/postgres/backup.sql.gz"),
            size_bytes=100 * 1024 * 1024,
            validated=True,
            encrypted=False,
        )
        mock_backup_service.backup_postgres = AsyncMock(return_value=mock_result)

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.post("/api/v1/backup/postgres")

            assert response.status_code == 200
            data = response.json()
            assert data["erfolg"] is True
            assert data["backup_typ"] == "postgres"


class TestBackupFullEndpoint:
    """Tests for POST /api/v1/backup/full endpoint."""

    def test_full_requires_auth(self):
        """Test that full backup requires authentication."""
        test_client = TestClient(app)
        response = test_client.post("/api/v1/backup/full")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_full_backup_success(self, client, mock_backup_service):
        """Test successful full backup."""
        mock_results = [
            BackupResult(success=True, backup_type="postgres"),
            BackupResult(success=True, backup_type="redis"),
            BackupResult(success=True, backup_type="minio"),
            BackupResult(success=True, backup_type="config"),
        ]
        mock_backup_service.backup_full = AsyncMock(return_value=mock_results)

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.post("/api/v1/backup/full")

            assert response.status_code == 200
            data = response.json()
            assert data["erfolg"] is True
            assert data["erfolgreich"] == 4
            assert data["fehlgeschlagen"] == 0

    @pytest.mark.asyncio
    async def test_full_backup_partial_failure(self, client, mock_backup_service):
        """Test full backup with some failures."""
        mock_results = [
            BackupResult(success=True, backup_type="postgres"),
            BackupResult(success=False, backup_type="redis", error="Fehler"),
            BackupResult(success=True, backup_type="minio"),
            BackupResult(success=True, backup_type="config"),
        ]
        mock_backup_service.backup_full = AsyncMock(return_value=mock_results)

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.post("/api/v1/backup/full")

            assert response.status_code == 200
            data = response.json()
            assert data["erfolg"] is False
            assert data["erfolgreich"] == 3
            assert data["fehlgeschlagen"] == 1


class TestRetentionEndpoint:
    """Tests for POST /api/v1/backup/retention endpoint."""

    def test_retention_requires_auth(self):
        """Test that retention endpoint requires authentication."""
        test_client = TestClient(app)
        response = test_client.post("/api/v1/backup/retention")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_retention_success(self, client, mock_backup_service):
        """Test successful retention policy application."""
        mock_backup_service.apply_retention_policy = AsyncMock(return_value={
            "postgres": 2,
            "redis": 1,
            "minio": 0,
            "config": 3,
        })

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.post("/api/v1/backup/retention")

            assert response.status_code == 200
            data = response.json()
            assert data["erfolg"] is True
            assert data["geloescht_gesamt"] == 6


class TestSyncEndpoint:
    """Tests for POST /api/v1/backup/sync endpoint."""

    def test_sync_requires_auth(self):
        """Test that sync endpoint requires authentication."""
        test_client = TestClient(app)
        response = test_client.post("/api/v1/backup/sync")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_sync_success(self, client, mock_backup_service):
        """Test successful remote sync."""
        mock_backup_service.sync_to_remote = AsyncMock(return_value=True)

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.post("/api/v1/backup/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["erfolg"] is True

    @pytest.mark.asyncio
    async def test_sync_disabled(self, client, mock_backup_service):
        """Test sync when disabled."""
        mock_backup_service.config.remote_enabled = False

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.post("/api/v1/backup/sync")

            assert response.status_code == 400


class TestBackupAPIGermanResponses:
    """Tests for German language responses."""

    @pytest.mark.asyncio
    async def test_full_backup_german_message(self, client, mock_backup_service):
        """Test that full backup returns German message."""
        mock_results = [
            BackupResult(success=True, backup_type="postgres"),
            BackupResult(success=True, backup_type="redis"),
            BackupResult(success=True, backup_type="minio"),
            BackupResult(success=True, backup_type="config"),
        ]
        mock_backup_service.backup_full = AsyncMock(return_value=mock_results)

        with patch("app.api.v1.backup.get_backup_service", return_value=mock_backup_service):
            response = client.post("/api/v1/backup/full")

            assert response.status_code == 200
            data = response.json()
            # Check German field names
            assert "erfolg" in data
            assert "erfolgreich" in data
            assert "fehlgeschlagen" in data
            assert "nachricht" in data
            # Message should be in German
            assert "Backup" in data["nachricht"]
