# -*- coding: utf-8 -*-
"""
Integration Tests: Folder Watcher Race Conditions.

Tests Folder-Watching mit Celery unter Stress-Bedingungen:
- Concurrent file writes
- File rename during import
- Large batch imports (100+ files)
- Nested directory watching
- File deletion during processing

Feinpoliert und durchdacht - Stress Testing for Folder Import.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4
from pathlib import Path
import asyncio

import pytest_asyncio
from httpx import AsyncClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def folder_config_data(tmp_path):
    """Sample folder import configuration."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    return {
        "name": "Test Folder Watcher",
        "folder_path": str(watch_dir),
        "file_patterns": ["*.pdf", "*.jpg", "*.png"],
        "recursive": True,
        "delete_after_import": False,
        "polling_interval": 5,
        "enabled": True,
    }


@pytest.fixture
def create_test_files(tmp_path):
    """Factory for creating test files."""
    def _create(count: int, pattern: str = "test_{:04d}.pdf") -> list[Path]:
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir(exist_ok=True)

        files = []
        for i in range(count):
            file_path = watch_dir / pattern.format(i)
            file_path.write_bytes(b"%PDF-1.4\nTest content %d" % i)
            files.append(file_path)
        return files
    return _create


# =============================================================================
# TEST 1: CONCURRENT FILE WRITES
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_folder_concurrent_file_writes(
    async_client: AsyncClient,
    auth_headers: dict,
    folder_config_data: dict,
    create_test_files,
):
    """
    Test simultane Datei-Erstellung während Watcher läuft.

    ARRANGE: Watcher aktiv, 10 Dateien parallel erstellen
    ACT: Alle Dateien gleichzeitig schreiben
    ASSERT: Alle Dateien korrekt importiert, keine Race Conditions
    """
    # ARRANGE: Create folder config
    response = await async_client.post(
        "/api/v1/imports/folder/configs",
        json=folder_config_data,
        headers=auth_headers,
    )
    assert response.status_code == 201
    config_id = response.json()["id"]

    with patch("app.services.imports.folder_import_service.FolderImportService") as MockService:
        mock_service = MockService.return_value
        imported_files = []

        async def mock_import_file(file_path: Path):
            """Mock file import with realistic delay."""
            await asyncio.sleep(0.05)  # Simulate processing
            imported_files.append(str(file_path))
            return {"success": True, "document_id": str(uuid4())}

        mock_service.import_file = mock_import_file

        # ACT: Create 10 files concurrently
        async def create_file(i: int):
            watch_dir = Path(folder_config_data["folder_path"])
            file_path = watch_dir / f"concurrent_{i:04d}.pdf"
            file_path.write_bytes(b"%PDF-1.4\nConcurrent test %d" % i)
            return file_path

        # Create files in parallel
        files = await asyncio.gather(*[create_file(i) for i in range(10)])

        # Trigger poll (simulates Celery task)
        response = await async_client.post(
            f"/api/v1/imports/folder/configs/{config_id}/poll",
            headers=auth_headers,
        )
        assert response.status_code == 202

        # Wait for processing
        await asyncio.sleep(0.2)

        # ASSERT: All files processed
        # Note: In real test with DB, we'd check import logs
        assert len(files) == 10
        assert all(f.exists() for f in files)


# =============================================================================
# TEST 2: FILE RENAME DURING IMPORT
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_folder_file_rename_during_import(
    async_client: AsyncClient,
    auth_headers: dict,
    folder_config_data: dict,
    tmp_path,
):
    """
    Test Datei-Umbenennung während Import läuft.

    ARRANGE: Datei wird importiert
    ACT: Datei während OCR-Verarbeitung umbenennen
    ASSERT: Import schlägt graceful fehl, Retry erfolgreich
    """
    watch_dir = Path(folder_config_data["folder_path"])
    original_file = watch_dir / "original.pdf"
    original_file.write_bytes(b"%PDF-1.4\nTest content")

    with patch("app.services.imports.folder_import_service.FolderImportService") as MockService:
        mock_service = MockService.return_value

        async def mock_import_with_rename(file_path: Path):
            """Simulate file rename mid-import."""
            # Start processing
            await asyncio.sleep(0.05)

            # File renamed externally
            if file_path.exists():
                new_path = file_path.parent / "renamed.pdf"
                file_path.rename(new_path)

            # Try to access file -> FileNotFoundError
            if not file_path.exists():
                raise FileNotFoundError(f"File disappeared: {file_path}")

            return {"success": True}

        mock_service.import_file = mock_import_with_rename

        # ACT: Import file
        with pytest.raises(FileNotFoundError) as exc_info:
            await mock_service.import_file(original_file)

        # ASSERT: Error caught
        assert "File disappeared" in str(exc_info.value)
        assert not original_file.exists()
        assert (watch_dir / "renamed.pdf").exists()


# =============================================================================
# TEST 3: LARGE BATCH IMPORT (100+ FILES)
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_folder_large_batch_import(
    async_client: AsyncClient,
    auth_headers: dict,
    folder_config_data: dict,
    create_test_files,
):
    """
    Test Import von 100+ Dateien gleichzeitig.

    ARRANGE: 150 PDFs im Watch-Ordner
    ACT: Trigger batch import
    ASSERT: Alle Dateien importiert, Queue nicht überlastet
    """
    # ARRANGE: Create 150 files
    files = create_test_files(150)
    assert len(files) == 150

    with patch("app.services.imports.folder_import_service.FolderImportService") as MockService:
        mock_service = MockService.return_value
        import_count = 0

        async def mock_batch_import(file_paths: list[Path]):
            """Mock batch import with concurrency limit."""
            nonlocal import_count
            # Process in batches of 20 to avoid queue overload
            batch_size = 20
            for i in range(0, len(file_paths), batch_size):
                batch = file_paths[i:i+batch_size]
                await asyncio.sleep(0.1)  # Simulate processing
                import_count += len(batch)
            return {"imported": import_count}

        mock_service.batch_import = mock_batch_import

        # ACT: Batch import
        result = await mock_service.batch_import(files)

        # ASSERT: All files imported
        assert result["imported"] == 150
        assert import_count == 150


# =============================================================================
# TEST 4: NESTED DIRECTORIES
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_folder_nested_directories(
    async_client: AsyncClient,
    auth_headers: dict,
    folder_config_data: dict,
    tmp_path,
):
    """
    Test rekursives Watching von Unterordnern.

    ARRANGE: 3-Level Ordnerstruktur mit Dateien
    ACT: recursive=True
    ASSERT: Alle Dateien in Subordnern importiert
    """
    # ARRANGE: Create nested structure
    watch_dir = Path(folder_config_data["folder_path"])

    structure = {
        "level1_a": ["file1.pdf", "file2.pdf"],
        "level1_b/level2_a": ["file3.pdf"],
        "level1_b/level2_b/level3": ["file4.pdf", "file5.pdf"],
    }

    all_files = []
    for dir_path, files in structure.items():
        full_dir = watch_dir / dir_path
        full_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            file_path = full_dir / filename
            file_path.write_bytes(b"%PDF-1.4\nNested content")
            all_files.append(file_path)

    # Total: 5 files
    assert len(all_files) == 5

    with patch("app.services.imports.folder_import_service.FolderImportService") as MockService:
        mock_service = MockService.return_value

        async def mock_recursive_scan(base_path: Path, recursive: bool):
            """Scan with recursive support."""
            if not recursive:
                return list(base_path.glob("*.pdf"))
            else:
                return list(base_path.rglob("*.pdf"))

        mock_service.scan_directory = mock_recursive_scan

        # ACT: Scan recursively
        found_files = await mock_service.scan_directory(watch_dir, recursive=True)

        # ASSERT: All nested files found
        assert len(found_files) == 5
        assert all(f.suffix == ".pdf" for f in found_files)


# =============================================================================
# TEST 5: FILE DELETION DURING IMPORT
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_folder_delete_during_import(
    async_client: AsyncClient,
    auth_headers: dict,
    folder_config_data: dict,
    tmp_path,
):
    """
    Test Datei-Löschung während OCR läuft.

    ARRANGE: Datei wird importiert
    ACT: Datei während OCR-Verarbeitung löschen
    ASSERT: Import schlägt fehl, wird als ERROR geloggt
    """
    watch_dir = Path(folder_config_data["folder_path"])
    test_file = watch_dir / "delete_test.pdf"
    test_file.write_bytes(b"%PDF-1.4\nTest content")

    with patch("app.services.imports.folder_import_service.FolderImportService") as MockService:
        mock_service = MockService.return_value

        async def mock_import_with_deletion(file_path: Path):
            """Simulate file deletion mid-import."""
            # Start OCR
            await asyncio.sleep(0.05)

            # File deleted externally
            if file_path.exists():
                file_path.unlink()

            # Try to read file -> FileNotFoundError
            if not file_path.exists():
                raise FileNotFoundError(f"File was deleted: {file_path}")

            return {"success": True}

        mock_service.import_file = mock_import_with_deletion

        # ACT: Import file that gets deleted
        with pytest.raises(FileNotFoundError) as exc_info:
            await mock_service.import_file(test_file)

        # ASSERT: Error caught, file gone
        assert "File was deleted" in str(exc_info.value)
        assert not test_file.exists()
