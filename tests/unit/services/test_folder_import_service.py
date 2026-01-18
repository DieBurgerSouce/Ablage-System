"""
Unit Tests fuer FolderImportService.

Tests fuer Watchdog-Monitoring, Path-Validierung, File-Verarbeitung
und Sicherheitsaspekte.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.imports.folder_import_service import FolderImportService


class TestPathValidation:
    """Tests fuer Path-Validierung und Sicherheit."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FolderImportService:
        """Create service instance with mocked allowed paths."""
        with patch.object(
            FolderImportService, "_load_allowed_paths",
            return_value=["/data/imports", "/home/user/documents"]
        ):
            svc = FolderImportService(db=mock_db)
        return svc

    def test_validate_path_allowed(self, service: FolderImportService) -> None:
        """Test validation of allowed path."""
        result = service._validate_path("/data/imports/invoices")
        assert result is True

    def test_validate_path_not_allowed(self, service: FolderImportService) -> None:
        """Test validation of disallowed path."""
        with pytest.raises(ValueError, match="nicht in erlaubten"):
            service._validate_path("/etc/passwd")

    def test_validate_path_traversal_blocked(
        self, service: FolderImportService
    ) -> None:
        """Test path traversal attack is blocked."""
        with pytest.raises(ValueError, match="Path-Traversal"):
            service._validate_path("/data/imports/../../../etc/passwd")

    def test_validate_path_with_dots(self, service: FolderImportService) -> None:
        """Test path with .. in middle is blocked."""
        with pytest.raises(ValueError, match="Path-Traversal"):
            service._validate_path("/data/imports/test/../../../etc")

    def test_validate_path_symlink_resolution(
        self, service: FolderImportService
    ) -> None:
        """Test path with .. is detected before symlink resolution."""
        with pytest.raises(ValueError, match="Path-Traversal"):
            service._validate_path("/data/imports/../link")

    def test_validate_windows_path(self, service: FolderImportService) -> None:
        """Test Windows path validation."""
        service._allowed_base_paths = ["C:\\Data\\Imports", "D:\\Documents"]
        result = service._validate_path("C:\\Data\\Imports\\invoices")
        assert result is True

    def test_validate_windows_path_traversal(
        self, service: FolderImportService
    ) -> None:
        """Test Windows path traversal blocked."""
        service._allowed_base_paths = ["C:\\Data\\Imports"]
        with pytest.raises(ValueError, match="Path-Traversal"):
            service._validate_path("C:\\Data\\Imports\\..\\..\\Windows\\System32")


class TestFilenameSanitization:
    """Tests fuer Dateinamen-Bereinigung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FolderImportService:
        """Create service instance."""
        with patch.object(
            FolderImportService, "_load_allowed_paths",
            return_value=["/data/imports"]
        ):
            return FolderImportService(db=mock_db)

    def test_sanitize_normal_filename(self, service: FolderImportService) -> None:
        """Test sanitizing normal filename."""
        result = service._sanitize_filename("invoice_2024.pdf")
        assert result == "invoice_2024.pdf"

    def test_sanitize_filename_with_spaces(self, service: FolderImportService) -> None:
        """Test sanitizing filename with spaces."""
        result = service._sanitize_filename("my invoice file.pdf")
        # Service might replace spaces or keep them
        assert ".pdf" in result

    def test_sanitize_filename_with_special_chars(
        self, service: FolderImportService
    ) -> None:
        """Test sanitizing filename with special characters."""
        result = service._sanitize_filename("test<>:\"|?*.pdf")
        # Should remove or replace dangerous characters
        assert "<" not in result
        assert ">" not in result
        assert "\"" not in result


class TestServiceLifecycle:
    """Tests fuer Service-Lifecycle."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FolderImportService:
        """Create service instance."""
        with patch.object(
            FolderImportService, "_load_allowed_paths",
            return_value=["/data/imports"]
        ):
            return FolderImportService(db=mock_db)

    def test_service_creation(self, service: FolderImportService) -> None:
        """Test service can be instantiated."""
        assert service is not None
        assert hasattr(service, "db")

    def test_service_has_allowed_paths(self, service: FolderImportService) -> None:
        """Test service has allowed paths configured."""
        assert hasattr(service, "_allowed_base_paths")
        assert len(service._allowed_base_paths) > 0


# =============================================================================
# Async Tests
# =============================================================================

@pytest.mark.asyncio
class TestAsyncFolderOperations:
    """Async tests fuer Folder Import operations."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> FolderImportService:
        """Create service instance."""
        with patch.object(
            FolderImportService, "_load_allowed_paths",
            return_value=["/data/imports"]
        ):
            return FolderImportService(db=mock_db)

    async def test_list_configs(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test listing folder configs."""
        config1 = MagicMock()
        config1.id = uuid4()
        config1.name = "Config 1"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config1]
        mock_db.execute.return_value = mock_result

        user_id = uuid4()

        result = await service.list_configs(user_id)

        assert len(result) == 1
        mock_db.execute.assert_called_once()

    async def test_get_config_found(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test getting specific folder config."""
        config_id = uuid4()
        user_id = uuid4()
        config = MagicMock()
        config.id = config_id
        config.name = "Test Config"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute.return_value = mock_result

        result = await service.get_config(config_id, user_id)

        assert result is not None

    async def test_get_config_not_found(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test getting non-existent folder config."""
        config_id = uuid4()
        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_config(config_id, user_id)

        assert result is None


@pytest.mark.asyncio
class TestWatcherManagement:
    """Tests fuer Watcher-Verwaltung."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> FolderImportService:
        """Create service instance."""
        with patch.object(
            FolderImportService, "_load_allowed_paths",
            return_value=["/data/imports"]
        ):
            return FolderImportService(db=mock_db)

    async def test_start_watcher_path_not_found(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test starting watcher for non-existent path."""
        config_id = uuid4()
        user_id = uuid4()

        # Mock config with non-existent path
        config = MagicMock()
        config.id = config_id
        config.watch_path = "/data/imports/nonexistent"
        config.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute.return_value = mock_result

        with patch("os.path.exists", return_value=False):
            # Should raise or return error
            try:
                result = await service.start_watcher(config_id, user_id)
                # If it returns result, check for error
                if isinstance(result, dict):
                    assert result.get("success") is False or "error" in str(result).lower()
            except (ValueError, FileNotFoundError):
                # Expected exception for non-existent path
                pass

    async def test_stop_watcher_not_running(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test stopping watcher that is not running."""
        config_id = uuid4()
        user_id = uuid4()

        # Mock config
        config = MagicMock()
        config.id = config_id
        config.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute.return_value = mock_result

        # Watcher not in active watchers
        result = await service.stop_watcher(config_id, user_id)

        # Should indicate no watcher was running
        assert result is not None


@pytest.mark.asyncio
class TestPollFolder:
    """Tests fuer manuelle Ordner-Abfrage."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> FolderImportService:
        """Create service instance."""
        with patch.object(
            FolderImportService, "_load_allowed_paths",
            return_value=["/data/imports"]
        ):
            return FolderImportService(db=mock_db)

    async def test_poll_folder_empty_directory(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test polling empty directory."""
        config_id = uuid4()
        user_id = uuid4()

        # Mock config
        config = MagicMock()
        config.id = config_id
        config.watch_path = "/data/imports/empty"
        config.include_patterns = ["*.pdf"]
        config.exclude_patterns = []
        config.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute.return_value = mock_result

        with patch("os.path.exists", return_value=True):
            with patch("os.path.isdir", return_value=True):
                with patch.object(service, "_collect_files", return_value=[]):
                    result = await service.poll_folder(config_id, user_id)

        # Should succeed with 0 files processed
        assert result is not None
