"""Unit-Tests fuer den Folder-Service.

Testet Ordnerverwaltung mit Hierarchie, Berechtigungen und Dokumenten-Zuordnung.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4
from datetime import datetime, timezone

# Check if folder service dependencies are available
try:
    from app.db.models_folder import (
        Folder,
        FolderDocument,
        FolderPermission,
        FolderPermissionLevel,
        FolderType,
    )
    from app.services.folder_service import FolderService
    FOLDER_SERVICE_AVAILABLE = True
except ImportError:
    FOLDER_SERVICE_AVAILABLE = False

requires_folder_service = pytest.mark.skipif(
    not FOLDER_SERVICE_AVAILABLE,
    reason="Folder service dependencies not installed",
)


@requires_folder_service
class TestFolderModels:
    """Tests fuer Folder-Datenbankmodelle."""

    def test_folder_type_enum(self):
        """FolderType Enum hat alle erwarteten Werte."""
        assert FolderType.GESCHAEFTLICH.value == "geschaeftlich"
        assert FolderType.ARCHIV.value == "archiv"
        assert FolderType.PROJEKT.value == "projekt"
        assert FolderType.EINGANG.value == "eingang"
        assert FolderType.AUSGANG.value == "ausgang"
        assert FolderType.CUSTOM.value == "custom"

    def test_permission_level_enum(self):
        """FolderPermissionLevel Enum hat korrekte Hierarchie."""
        assert FolderPermissionLevel.READ.value == "read"
        assert FolderPermissionLevel.WRITE.value == "write"
        assert FolderPermissionLevel.ADMIN.value == "admin"

    def test_folder_repr(self):
        """Folder __repr__ zeigt Name und Pfad."""
        folder = Folder()
        folder.id = uuid4()
        folder.name = "Test-Ordner"
        folder.path = "root/child"
        result = repr(folder)
        assert "Test-Ordner" in result
        assert "root/child" in result


@requires_folder_service
class TestFolderServiceCreate:
    """Tests fuer Ordner-Erstellung."""

    @pytest.fixture
    def service(self):
        """FolderService-Instanz."""
        return FolderService()

    @pytest.fixture
    def mock_db(self):
        """Mock AsyncSession."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def company_id(self):
        return uuid4()

    @pytest.fixture
    def user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_create_root_folder(self, service, mock_db, company_id, user_id):
        """Root-Ordner erstellen setzt path auf eigene ID."""
        folder = await service.create_folder(
            mock_db,
            company_id=company_id,
            name="Buchhaltung",
            created_by_id=user_id,
        )
        assert folder.name == "Buchhaltung"
        assert folder.company_id == company_id
        assert folder.parent_id is None
        assert folder.level == 0
        assert folder.folder_type == FolderType.GESCHAEFTLICH.value
        # Path wird auf eigene ID gesetzt
        assert str(folder.id) in folder.path
        # Permission fuer Ersteller wird angelegt
        assert mock_db.add.call_count >= 2  # folder + permission

    @pytest.mark.asyncio
    async def test_create_subfolder(self, service, mock_db, company_id, user_id):
        """Unterordner erhaelt Pfad des Parents + eigene ID."""
        parent_id = uuid4()
        parent_folder = Mock()
        parent_folder.id = parent_id
        parent_folder.path = str(parent_id)
        parent_folder.level = 0
        parent_folder.company_id = company_id

        # Mock: _get_folder_internal findet den Parent
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = parent_folder
        mock_db.execute.return_value = mock_result

        folder = await service.create_folder(
            mock_db,
            company_id=company_id,
            name="Rechnungen",
            created_by_id=user_id,
            parent_id=parent_id,
        )
        assert folder.name == "Rechnungen"
        assert folder.parent_id == parent_id
        assert folder.level == 1
        assert str(parent_id) in folder.path

    @pytest.mark.asyncio
    async def test_create_folder_invalid_parent(self, service, mock_db, company_id, user_id):
        """Fehler wenn Parent-Ordner nicht existiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Uebergeordneter Ordner nicht gefunden"):
            await service.create_folder(
                mock_db,
                company_id=company_id,
                name="Fehler",
                created_by_id=user_id,
                parent_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_create_folder_custom_type(self, service, mock_db, company_id, user_id):
        """Ordner mit benutzerdefiniertem Typ erstellen."""
        folder = await service.create_folder(
            mock_db,
            company_id=company_id,
            name="Archiv 2025",
            created_by_id=user_id,
            folder_type=FolderType.ARCHIV.value,
            icon="Archive",
            color="#EF4444",
        )
        assert folder.folder_type == FolderType.ARCHIV.value
        assert folder.icon == "Archive"
        assert folder.color == "#EF4444"


@requires_folder_service
class TestFolderServicePermissions:
    """Tests fuer Berechtigungspruefung."""

    @pytest.fixture
    def service(self):
        return FolderService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_check_access_admin_has_all(self, service, mock_db):
        """Admin-Berechtigung gewaehrt alle Zugriffe."""
        folder_id = uuid4()
        user_id = uuid4()

        # Mock: Direkte Admin-Berechtigung gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "admin"
        mock_db.execute.return_value = mock_result

        assert await service.check_folder_access(mock_db, folder_id, user_id, "read")
        assert await service.check_folder_access(mock_db, folder_id, user_id, "write")
        assert await service.check_folder_access(mock_db, folder_id, user_id, "admin")

    @pytest.mark.asyncio
    async def test_check_access_read_only(self, service, mock_db):
        """Read-Berechtigung reicht nicht fuer Write."""
        folder_id = uuid4()
        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "read"
        mock_db.execute.return_value = mock_result

        assert await service.check_folder_access(mock_db, folder_id, user_id, "read")
        assert not await service.check_folder_access(mock_db, folder_id, user_id, "write")

    @pytest.mark.asyncio
    async def test_check_access_no_permission(self, service, mock_db):
        """Ohne Berechtigung wird Zugriff verweigert."""
        folder_id = uuid4()
        user_id = uuid4()

        # Erste Query: Direkte Berechtigung = None
        # Zweite Query: Folder path
        # Dritte Query: Ancestor Berechtigungen
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # direct perm
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # folder path
        ]
        mock_db.execute.side_effect = results

        assert not await service.check_folder_access(mock_db, folder_id, user_id, "read")


@requires_folder_service
class TestFolderServiceHierarchy:
    """Tests fuer Ordner-Hierarchie."""

    @pytest.fixture
    def service(self):
        return FolderService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        return db

    def test_materialized_path_format(self):
        """Materialized Path folgt dem Format UUID/UUID/UUID."""
        root_id = uuid4()
        child_id = uuid4()
        grandchild_id = uuid4()

        root_path = str(root_id)
        child_path = f"{root_path}/{child_id}"
        grandchild_path = f"{child_path}/{grandchild_id}"

        # Pfad-Teile extrahieren
        parts = grandchild_path.split("/")
        assert len(parts) == 3
        assert parts[0] == str(root_id)
        assert parts[1] == str(child_id)
        assert parts[2] == str(grandchild_id)

    @pytest.mark.asyncio
    async def test_move_folder_cycle_detection(self, service, mock_db):
        """Ordner kann nicht in seinen eigenen Unterordner verschoben werden."""
        folder_id = uuid4()
        child_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()

        folder = Mock()
        folder.id = folder_id
        folder.path = str(folder_id)
        folder.level = 0
        folder.is_locked = False
        folder.parent_id = None
        folder.company_id = company_id

        child = Mock()
        child.id = child_id
        child.path = f"{folder_id}/{child_id}"
        child.level = 1
        child.company_id = company_id

        # check_folder_access -> True
        perm_result = MagicMock()
        perm_result.scalar_one_or_none.return_value = "admin"

        # _get_folder_internal returns folder, then child
        folder_result = MagicMock()
        folder_result.scalar_one_or_none.side_effect = [folder, child]

        mock_db.execute.side_effect = [perm_result, folder_result, folder_result]

        # Versuche folder in sein Kind zu verschieben
        with pytest.raises(ValueError, match="eigenen Unterordner"):
            await service.move_folder(
                mock_db, folder_id, child_id, company_id, user_id
            )


@requires_folder_service
class TestFolderServiceDocuments:
    """Tests fuer Dokument-Zuordnung."""

    @pytest.fixture
    def service(self):
        return FolderService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_add_document_duplicate(self, service, mock_db):
        """Doppelte Zuordnung wird abgelehnt."""
        folder_id = uuid4()
        document_id = uuid4()
        user_id = uuid4()
        company_id = uuid4()

        # check_folder_access -> True
        perm_result = MagicMock()
        perm_result.scalar_one_or_none.return_value = "write"

        # Existing check -> already exists
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = Mock()

        mock_db.execute.side_effect = [perm_result, existing_result]

        with pytest.raises(ValueError, match="bereits in diesem Ordner"):
            await service.add_document_to_folder(
                mock_db, folder_id, document_id, user_id, company_id
            )

    @pytest.mark.asyncio
    async def test_add_document_no_permission(self, service, mock_db):
        """Zuordnung ohne Berechtigung wird abgelehnt."""
        folder_id = uuid4()
        document_id = uuid4()
        user_id = uuid4()
        company_id = uuid4()

        # check_folder_access -> False (no permission found, no folder path)
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # direct perm
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # folder path
        ]
        mock_db.execute.side_effect = results

        with pytest.raises(PermissionError, match="Keine Berechtigung"):
            await service.add_document_to_folder(
                mock_db, folder_id, document_id, user_id, company_id
            )


@requires_folder_service
class TestFolderServiceSearch:
    """Tests fuer Ordner-Suche."""

    @pytest.fixture
    def service(self):
        return FolderService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_search_returns_results(self, service, mock_db):
        """Suche gibt gefundene Ordner zurueck."""
        company_id = uuid4()
        user_id = uuid4()

        # Mock: Count = 2
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        # Mock: 2 Folders
        folder1 = Mock()
        folder1.id = uuid4()
        folder1.name = "Rechnungen 2025"

        folder2 = Mock()
        folder2.id = uuid4()
        folder2.name = "Rechnungen 2024"

        folders_result = MagicMock()
        folders_result.scalars.return_value.all.return_value = [folder1, folder2]

        mock_db.execute.side_effect = [count_result, folders_result]

        folders, total = await service.search_folders(
            mock_db, company_id, user_id, "Rechnungen"
        )
        assert total == 2
        assert len(folders) == 2


@requires_folder_service
class TestFolderServiceStats:
    """Tests fuer Ordner-Statistiken."""

    @pytest.fixture
    def service(self):
        return FolderService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_stats_nonexistent_folder(self, service, mock_db):
        """Statistiken fuer nicht-existierenden Ordner geben leeres Dict."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        stats = await service.get_folder_stats(mock_db, uuid4(), uuid4())
        assert stats == {}


@requires_folder_service
class TestFolderServiceReorder:
    """Tests fuer Ordner-Sortierung."""

    @pytest.fixture
    def service(self):
        return FolderService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_reorder_sets_sort_order(self, service, mock_db):
        """Neuordnung setzt sort_order korrekt."""
        company_id = uuid4()
        user_id = uuid4()
        folder_ids = [uuid4() for _ in range(3)]

        result = await service.reorder_folders(
            mock_db, None, company_id, user_id, folder_ids
        )
        assert result is True
        # 3 execute calls for 3 folders
        assert mock_db.execute.call_count == 3
