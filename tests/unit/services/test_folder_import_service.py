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

from app.services.import.folder_import_service import FolderImportService


class TestPathValidation:
    """Tests fuer Path-Validierung und Sicherheit."""

    @pytest.fixture
    def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    def test_validate_path_allowed(self, service: FolderImportService) -> None:
        """Test validation of allowed path."""
        allowed_paths = ["/data/imports", "/home/user/documents"]

        result = service._validate_path("/data/imports/invoices", allowed_paths)

        assert result is True

    def test_validate_path_not_allowed(self, service: FolderImportService) -> None:
        """Test validation of disallowed path."""
        allowed_paths = ["/data/imports", "/home/user/documents"]

        result = service._validate_path("/etc/passwd", allowed_paths)

        assert result is False

    def test_validate_path_traversal_blocked(
        self, service: FolderImportService
    ) -> None:
        """Test path traversal attack is blocked."""
        allowed_paths = ["/data/imports"]

        # Path traversal attempt
        result = service._validate_path(
            "/data/imports/../../../etc/passwd", allowed_paths
        )

        assert result is False

    def test_validate_path_with_dots(self, service: FolderImportService) -> None:
        """Test path with .. in middle is blocked."""
        allowed_paths = ["/data/imports"]

        result = service._validate_path("/data/imports/test/../../../etc", allowed_paths)

        assert result is False

    def test_validate_path_symlink_resolution(
        self, service: FolderImportService
    ) -> None:
        """Test symlink is resolved to real path."""
        allowed_paths = ["/data/imports"]

        # Mock os.path.realpath to simulate symlink
        with patch("os.path.realpath") as mock_realpath:
            mock_realpath.return_value = "/etc/passwd"

            result = service._validate_path("/data/imports/link", allowed_paths)

            assert result is False

    def test_validate_windows_path(self, service: FolderImportService) -> None:
        """Test Windows path validation."""
        allowed_paths = ["C:\\Data\\Imports", "D:\\Documents"]

        result = service._validate_path(
            "C:\\Data\\Imports\\invoices", allowed_paths
        )

        assert result is True

    def test_validate_windows_path_traversal(
        self, service: FolderImportService
    ) -> None:
        """Test Windows path traversal blocked."""
        allowed_paths = ["C:\\Data\\Imports"]

        result = service._validate_path(
            "C:\\Data\\Imports\\..\\..\\Windows\\System32", allowed_paths
        )

        assert result is False


class TestPatternMatching:
    """Tests fuer Include/Exclude Pattern Matching."""

    @pytest.fixture
    def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    def test_matches_include_pattern(self, service: FolderImportService) -> None:
        """Test file matches include pattern."""
        include_patterns = ["*.pdf", "*.png"]
        exclude_patterns: list[str] = []

        result = service._matches_patterns(
            "invoice.pdf", include_patterns, exclude_patterns
        )

        assert result is True

    def test_no_match_include_pattern(self, service: FolderImportService) -> None:
        """Test file does not match include pattern."""
        include_patterns = ["*.pdf", "*.png"]
        exclude_patterns: list[str] = []

        result = service._matches_patterns(
            "document.docx", include_patterns, exclude_patterns
        )

        assert result is False

    def test_excluded_pattern(self, service: FolderImportService) -> None:
        """Test file is excluded by pattern."""
        include_patterns = ["*.pdf"]
        exclude_patterns = ["temp_*.pdf", "draft_*.pdf"]

        result = service._matches_patterns(
            "temp_invoice.pdf", include_patterns, exclude_patterns
        )

        assert result is False

    def test_include_all_when_empty(self, service: FolderImportService) -> None:
        """Test all files included when no include patterns."""
        include_patterns: list[str] = []
        exclude_patterns: list[str] = []

        result = service._matches_patterns(
            "any_file.xyz", include_patterns, exclude_patterns
        )

        assert result is True

    def test_exclude_hidden_files(self, service: FolderImportService) -> None:
        """Test hidden files are excluded."""
        include_patterns = ["*"]
        exclude_patterns = [".*"]

        result = service._matches_patterns(
            ".hidden_file", include_patterns, exclude_patterns
        )

        assert result is False

    def test_case_insensitive_pattern(self, service: FolderImportService) -> None:
        """Test case-insensitive pattern matching."""
        include_patterns = ["*.pdf", "*.PDF"]
        exclude_patterns: list[str] = []

        result = service._matches_patterns(
            "INVOICE.PDF", include_patterns, exclude_patterns
        )

        assert result is True


class TestFileAgeCheck:
    """Tests fuer File-Alter-Pruefung."""

    @pytest.fixture
    def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    def test_file_old_enough(self, service: FolderImportService) -> None:
        """Test file is old enough to process."""
        import time

        # File modified 60 seconds ago
        mtime = time.time() - 60
        min_age_seconds = 30

        result = service._is_file_old_enough(mtime, min_age_seconds)

        assert result is True

    def test_file_too_new(self, service: FolderImportService) -> None:
        """Test file is too new to process."""
        import time

        # File modified just now
        mtime = time.time()
        min_age_seconds = 30

        result = service._is_file_old_enough(mtime, min_age_seconds)

        assert result is False

    def test_file_age_zero_threshold(self, service: FolderImportService) -> None:
        """Test file with zero age threshold."""
        import time

        mtime = time.time()
        min_age_seconds = 0

        result = service._is_file_old_enough(mtime, min_age_seconds)

        assert result is True


class TestFileHashCalculation:
    """Tests fuer File-Hash-Berechnung."""

    @pytest.fixture
    def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    def test_calculate_file_hash(self, service: FolderImportService) -> None:
        """Test SHA256 hash calculation."""
        content = b"Test file content for hashing"

        with patch("builtins.open", MagicMock(return_value=MagicMock())):
            with patch("hashlib.sha256") as mock_sha256:
                mock_hash = MagicMock()
                mock_hash.hexdigest.return_value = "abc123def456"
                mock_sha256.return_value = mock_hash

                result = service._calculate_file_hash("/path/to/file.pdf")

                assert result == "abc123def456"

    def test_calculate_hash_large_file(self, service: FolderImportService) -> None:
        """Test hash calculation for large file (chunked reading)."""
        # Service should read file in chunks
        with patch("builtins.open") as mock_open:
            mock_file = MagicMock()
            mock_file.read.side_effect = [b"chunk1", b"chunk2", b""]
            mock_open.return_value.__enter__.return_value = mock_file

            with patch("hashlib.sha256") as mock_sha256:
                mock_hash = MagicMock()
                mock_hash.hexdigest.return_value = "hash123"
                mock_sha256.return_value = mock_hash

                result = service._calculate_file_hash("/path/to/large_file.pdf")

                # Should have updated hash with each chunk
                assert mock_hash.update.call_count == 2


class TestDuplicateDetection:
    """Tests fuer Duplikat-Erkennung."""

    @pytest.fixture
    def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    @pytest.mark.asyncio
    async def test_is_duplicate_true(self, service: FolderImportService) -> None:
        """Test duplicate detection - is duplicate."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # Found existing
        mock_db.execute.return_value = mock_result

        file_hash = "abc123def456"
        config_id = str(uuid4())

        result = await service._is_duplicate(mock_db, file_hash, config_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_duplicate_false(self, service: FolderImportService) -> None:
        """Test duplicate detection - not duplicate."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Not found
        mock_db.execute.return_value = mock_result

        file_hash = "abc123def456"
        config_id = str(uuid4())

        result = await service._is_duplicate(mock_db, file_hash, config_id)

        assert result is False


class TestWatcherManagement:
    """Tests fuer Watcher-Start/Stop."""

    @pytest.fixture
    def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    def test_watcher_not_running_initially(
        self, service: FolderImportService
    ) -> None:
        """Test watcher is not running initially."""
        config_id = str(uuid4())

        result = service.is_watcher_running(config_id)

        assert result is False

    @patch("watchdog.observers.Observer")
    def test_start_watcher(
        self, mock_observer_class: MagicMock, service: FolderImportService
    ) -> None:
        """Test starting watcher."""
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        config = MagicMock()
        config.id = str(uuid4())
        config.watch_path = "/data/imports"
        config.recursive = True

        with patch.object(service, "_validate_path", return_value=True):
            with patch("os.path.exists", return_value=True):
                result = service.start_watcher(config)

        assert result["success"] is True
        mock_observer.start.assert_called_once()

    @patch("watchdog.observers.Observer")
    def test_stop_watcher(
        self, mock_observer_class: MagicMock, service: FolderImportService
    ) -> None:
        """Test stopping watcher."""
        mock_observer = MagicMock()
        config_id = str(uuid4())

        # Add running watcher
        service._watchers[config_id] = mock_observer

        result = service.stop_watcher(config_id)

        assert result["success"] is True
        mock_observer.stop.assert_called_once()
        assert config_id not in service._watchers

    def test_stop_watcher_not_running(self, service: FolderImportService) -> None:
        """Test stopping watcher that is not running."""
        config_id = str(uuid4())

        result = service.stop_watcher(config_id)

        assert result["success"] is False
        assert "nicht aktiv" in result["message"].lower() or "not running" in result["message"].lower()


class TestDailyLimitCheck:
    """Tests fuer Daily-Limit-Pruefung."""

    @pytest.fixture
    def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    def test_daily_limit_not_reached(self, service: FolderImportService) -> None:
        """Test daily limit not reached."""
        config = MagicMock()
        config.daily_limit = 100
        config.total_files_today = 50

        result = service._is_daily_limit_reached(config)

        assert result is False

    def test_daily_limit_reached(self, service: FolderImportService) -> None:
        """Test daily limit reached."""
        config = MagicMock()
        config.daily_limit = 100
        config.total_files_today = 100

        result = service._is_daily_limit_reached(config)

        assert result is True

    def test_daily_limit_no_limit(self, service: FolderImportService) -> None:
        """Test no daily limit set."""
        config = MagicMock()
        config.daily_limit = None
        config.total_files_today = 1000

        result = service._is_daily_limit_reached(config)

        assert result is False


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
    async def service(self) -> FolderImportService:
        """Create service instance."""
        return FolderImportService()

    async def test_list_configs(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test listing folder configs."""
        config1 = MagicMock()
        config1.id = str(uuid4())
        config1.name = "Config 1"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config1]
        mock_db.execute.return_value = mock_result

        user_id = str(uuid4())

        result = await service.list_configs(mock_db, user_id)

        assert len(result) == 1
        mock_db.execute.assert_called_once()

    async def test_create_config_valid_path(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test creating folder config with valid path."""
        user_id = str(uuid4())
        data = {
            "name": "Invoice Folder",
            "watch_path": "/data/imports/invoices",
            "recursive": True,
            "include_patterns": ["*.pdf"],
        }

        with patch.object(service, "_validate_path", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    result = await service.create_config(mock_db, user_id, data)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_create_config_invalid_path(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test creating folder config with invalid path."""
        user_id = str(uuid4())
        data = {
            "name": "Invalid Folder",
            "watch_path": "/etc/passwd",
        }

        with patch.object(service, "_validate_path", return_value=False):
            with pytest.raises(ValueError) as exc_info:
                await service.create_config(mock_db, user_id, data)

        assert "nicht erlaubt" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()

    async def test_poll_folder(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test manual folder polling."""
        config = MagicMock()
        config.id = str(uuid4())
        config.watch_path = "/data/imports"
        config.recursive = True
        config.include_patterns = ["*.pdf"]
        config.exclude_patterns = []
        config.min_file_age_seconds = 0
        config.daily_limit = None
        config.total_files_today = 0

        mock_files = [
            MagicMock(path="/data/imports/file1.pdf", is_file=lambda: True),
            MagicMock(path="/data/imports/file2.pdf", is_file=lambda: True),
        ]

        with patch.object(service, "_validate_path", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("os.scandir", return_value=mock_files):
                    with patch.object(service, "_process_file", new_callable=AsyncMock):
                        result = await service.poll_folder(mock_db, config)

        assert result["success"] is True

    async def test_process_file_success(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test successful file processing."""
        config = MagicMock()
        config.id = str(uuid4())
        config.target_folder_id = str(uuid4())
        config.auto_tag_ids = []
        config.enable_ocr = True
        config.ocr_backend = "deepseek"
        config.delete_after_processing = False
        config.move_to_folder = None

        file_path = "/data/imports/invoice.pdf"

        with patch.object(service, "_calculate_file_hash", return_value="hash123"):
            with patch.object(service, "_is_duplicate", new_callable=AsyncMock, return_value=False):
                with patch("builtins.open", MagicMock()):
                    with patch.object(service, "_create_document", new_callable=AsyncMock) as mock_create:
                        mock_create.return_value = MagicMock(id=str(uuid4()))

                        result = await service._process_file(mock_db, config, file_path)

        assert result["success"] is True

    async def test_process_file_duplicate(
        self, service: FolderImportService, mock_db: AsyncMock
    ) -> None:
        """Test file processing with duplicate detection."""
        config = MagicMock()
        config.id = str(uuid4())

        file_path = "/data/imports/duplicate.pdf"

        with patch.object(service, "_calculate_file_hash", return_value="hash123"):
            with patch.object(service, "_is_duplicate", new_callable=AsyncMock, return_value=True):
                result = await service._process_file(mock_db, config, file_path)

        assert result["success"] is False
        assert result["status"] == "duplicate"
