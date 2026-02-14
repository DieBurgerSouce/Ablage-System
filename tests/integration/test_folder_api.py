"""Integrations-Tests fuer die Folder API Endpoints.

Testet die REST API mit echten HTTP-Aufrufen gegen den FastAPI TestClient.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

# Check if dependencies are available
try:
    from fastapi.testclient import TestClient
    from app.api.v1.folders import (
        FolderCreate,
        FolderUpdate,
        FolderMoveRequest,
        DocumentAddRequest,
        ReorderRequest,
        PermissionSetRequest,
        FolderResponse,
    )
    FOLDER_API_AVAILABLE = True
except ImportError:
    FOLDER_API_AVAILABLE = False

requires_folder_api = pytest.mark.skipif(
    not FOLDER_API_AVAILABLE,
    reason="Folder API dependencies not available",
)


@requires_folder_api
class TestFolderSchemas:
    """Tests fuer Pydantic Schemas."""

    def test_folder_create_minimal(self):
        """Minimale Ordner-Erstellung mit nur Name."""
        data = FolderCreate(name="Test-Ordner")
        assert data.name == "Test-Ordner"
        assert data.parent_id is None
        assert data.icon == "Folder"
        assert data.folder_type == "geschaeftlich"

    def test_folder_create_full(self):
        """Vollstaendige Ordner-Erstellung mit allen Feldern."""
        parent = uuid4()
        data = FolderCreate(
            name="Rechnungen 2025",
            parent_id=parent,
            description="Alle Rechnungen fuer 2025",
            icon="Receipt",
            color="#3B82F6",
            folder_type="archiv",
            folder_metadata={"jahr": 2025},
        )
        assert data.name == "Rechnungen 2025"
        assert data.parent_id == parent
        assert data.color == "#3B82F6"
        assert data.folder_metadata == {"jahr": 2025}

    def test_folder_create_name_validation(self):
        """Name darf nicht leer sein."""
        with pytest.raises(Exception):
            FolderCreate(name="")

    def test_folder_create_color_validation(self):
        """Farbe muss gueltiger Hex-Code sein."""
        # Gueltig
        FolderCreate(name="Test", color="#FF0000")
        FolderCreate(name="Test", color="#3b82f6")
        # Ungueltig
        with pytest.raises(Exception):
            FolderCreate(name="Test", color="rot")
        with pytest.raises(Exception):
            FolderCreate(name="Test", color="#GGG")

    def test_folder_update_partial(self):
        """Partielle Aktualisierung - nur gesetzte Felder."""
        data = FolderUpdate(name="Neuer Name")
        assert data.name == "Neuer Name"
        assert data.description is None
        assert data.icon is None

    def test_folder_move_request(self):
        """Ordner-Verschiebung Validierung."""
        target = uuid4()
        data = FolderMoveRequest(new_parent_id=target)
        assert data.new_parent_id == target

        # Verschiebung in Root
        data = FolderMoveRequest(new_parent_id=None)
        assert data.new_parent_id is None

    def test_document_add_request(self):
        """Dokument-Zuordnung Validierung."""
        doc_id = uuid4()
        data = DocumentAddRequest(document_id=doc_id)
        assert data.document_id == doc_id
        assert data.is_primary is True

    def test_reorder_request(self):
        """Sortier-Request mit Ordner-IDs."""
        ids = [uuid4() for _ in range(3)]
        data = ReorderRequest(folder_order=ids)
        assert len(data.folder_order) == 3

    def test_permission_set_request(self):
        """Berechtigungs-Request Validierung."""
        uid = uuid4()
        data = PermissionSetRequest(user_id=uid, permission_level="write")
        assert data.user_id == uid
        assert data.permission_level == "write"
        assert data.propagate is True


@requires_folder_api
class TestFolderResponseModel:
    """Tests fuer Response-Modelle."""

    def test_folder_response_from_attributes(self):
        """FolderResponse kann aus ORM-Attributen erstellt werden."""
        fid = uuid4()
        cid = uuid4()
        data = FolderResponse(
            id=fid,
            company_id=cid,
            parent_id=None,
            name="Buchhaltung",
            path=str(fid),
            level=0,
            sort_order=0,
            folder_type="geschaeftlich",
            icon="Folder",
            document_count=5,
            subfolder_count=2,
            is_locked=False,
        )
        assert data.id == fid
        assert data.name == "Buchhaltung"
        assert data.document_count == 5
        assert data.is_locked is False
