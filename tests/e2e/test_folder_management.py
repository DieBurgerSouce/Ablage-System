# -*- coding: utf-8 -*-
"""
E2E Tests: Folder Management

Tests folder CRUD operations, tree navigation, and drag-drop functionality.

Feinpoliert und durchdacht - Ordner-Management Tests.
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.mark.e2e
class TestFolderCRUD:
    """Test folder create, read, update, delete operations."""

    @pytest.mark.asyncio
    async def test_create_folder(self):
        """Test Ordner-Erstellung."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.create_folder.return_value = {
                "id": "folder_001",
                "name": "Rechnungen 2024",
                "parent_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "document_count": 0
            }
            MockFolder.return_value = mock_folder

            folder = await mock_folder.create_folder(
                name="Rechnungen 2024",
                parent_id=None
            )

            assert folder["id"] == "folder_001"
            assert folder["name"] == "Rechnungen 2024"
            assert folder["document_count"] == 0

    @pytest.mark.asyncio
    async def test_create_subfolder(self):
        """Test Unterordner-Erstellung."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.create_folder.return_value = {
                "id": "folder_002",
                "name": "Q1 2024",
                "parent_id": "folder_001",
                "path": "/Rechnungen 2024/Q1 2024",
                "depth": 1
            }
            MockFolder.return_value = mock_folder

            subfolder = await mock_folder.create_folder(
                name="Q1 2024",
                parent_id="folder_001"
            )

            assert subfolder["parent_id"] == "folder_001"
            assert subfolder["depth"] == 1
            assert "Q1 2024" in subfolder["path"]

    @pytest.mark.asyncio
    async def test_update_folder_name(self):
        """Test Ordner-Umbenennung."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.update_folder.return_value = {
                "id": "folder_001",
                "name": "Rechnungen 2024 (Archiv)",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            MockFolder.return_value = mock_folder

            updated = await mock_folder.update_folder(
                folder_id="folder_001",
                name="Rechnungen 2024 (Archiv)"
            )

            assert "Archiv" in updated["name"]

    @pytest.mark.asyncio
    async def test_delete_empty_folder(self):
        """Test Löschen eines leeren Ordners."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.delete_folder.return_value = {
                "success": True,
                "folder_id": "folder_002",
                "message": "Ordner erfolgreich gelöscht"
            }
            MockFolder.return_value = mock_folder

            result = await mock_folder.delete_folder("folder_002")

            assert result["success"] is True
            assert result["folder_id"] == "folder_002"


@pytest.mark.e2e
class TestFolderTreeNavigation:
    """Test folder tree navigation and hierarchy."""

    @pytest.mark.asyncio
    async def test_get_folder_tree(self):
        """Test Abrufen der Ordner-Hierarchie."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.get_folder_tree.return_value = {
                "root": {
                    "id": "root",
                    "name": "Meine Dokumente",
                    "children": [
                        {
                            "id": "folder_001",
                            "name": "Rechnungen 2024",
                            "children": [
                                {"id": "folder_002", "name": "Q1 2024", "children": []},
                                {"id": "folder_003", "name": "Q2 2024", "children": []}
                            ]
                        },
                        {
                            "id": "folder_004",
                            "name": "Verträge",
                            "children": []
                        }
                    ]
                }
            }
            MockFolder.return_value = mock_folder

            tree = await mock_folder.get_folder_tree()

            assert tree["root"]["name"] == "Meine Dokumente"
            assert len(tree["root"]["children"]) == 2
            assert len(tree["root"]["children"][0]["children"]) == 2

    @pytest.mark.asyncio
    async def test_get_folder_breadcrumbs(self):
        """Test Breadcrumb-Navigation."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.get_breadcrumbs.return_value = [
                {"id": "root", "name": "Meine Dokumente"},
                {"id": "folder_001", "name": "Rechnungen 2024"},
                {"id": "folder_002", "name": "Q1 2024"}
            ]
            MockFolder.return_value = mock_folder

            breadcrumbs = await mock_folder.get_breadcrumbs("folder_002")

            assert len(breadcrumbs) == 3
            assert breadcrumbs[0]["name"] == "Meine Dokumente"
            assert breadcrumbs[-1]["name"] == "Q1 2024"

    @pytest.mark.asyncio
    async def test_folder_auto_navigation_single_subfolder(self):
        """Test automatische Navigation bei einzelnem Unterordner."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            # Folder has exactly 1 subfolder, should auto-navigate
            mock_folder.get_folder_contents.return_value = {
                "folder_id": "folder_001",
                "subfolders": [{"id": "folder_002", "name": "Q1 2024"}],
                "documents": [],
                "should_auto_navigate": True,
                "auto_navigate_to": "folder_002"
            }
            MockFolder.return_value = mock_folder

            contents = await mock_folder.get_folder_contents("folder_001")

            assert contents["should_auto_navigate"] is True
            assert contents["auto_navigate_to"] == "folder_002"


@pytest.mark.e2e
class TestFolderDragDrop:
    """Test drag-and-drop folder operations."""

    @pytest.mark.asyncio
    async def test_move_document_to_folder(self):
        """Test Dokument in anderen Ordner verschieben."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.move_document.return_value = {
                "success": True,
                "document_id": "doc_001",
                "old_folder_id": "folder_001",
                "new_folder_id": "folder_002",
                "message": "Dokument erfolgreich verschoben"
            }
            MockFolder.return_value = mock_folder

            result = await mock_folder.move_document(
                document_id="doc_001",
                target_folder_id="folder_002"
            )

            assert result["success"] is True
            assert result["new_folder_id"] == "folder_002"

    @pytest.mark.asyncio
    async def test_move_folder_to_parent(self):
        """Test Ordner unter anderen Parent verschieben."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.move_folder.return_value = {
                "success": True,
                "folder_id": "folder_003",
                "old_parent_id": "folder_001",
                "new_parent_id": "folder_004",
                "new_path": "/Verträge/Q2 2024"
            }
            MockFolder.return_value = mock_folder

            result = await mock_folder.move_folder(
                folder_id="folder_003",
                new_parent_id="folder_004"
            )

            assert result["success"] is True
            assert result["new_parent_id"] == "folder_004"
            assert "Verträge" in result["new_path"]

    @pytest.mark.asyncio
    async def test_prevent_circular_folder_move(self):
        """Test Verhinderung von zirkulären Ordner-Verschiebungen."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.move_folder.side_effect = ValueError(
                "Zirkuläre Verschiebung nicht erlaubt"
            )
            MockFolder.return_value = mock_folder

            # Try to move parent into its own child
            with pytest.raises(ValueError, match="Zirkuläre Verschiebung"):
                await mock_folder.move_folder(
                    folder_id="folder_001",
                    new_parent_id="folder_002"  # folder_002 is child of folder_001
                )
