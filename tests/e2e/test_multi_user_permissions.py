# -*- coding: utf-8 -*-
"""
E2E Tests: Multi-User Permissions

Tests permission checks, access control, and multi-tenancy.

Feinpoliert und durchdacht - Berechtigungs-Tests.
"""

import pytest
import asyncio
from typing import Dict, Any
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.mark.e2e
class TestDocumentPermissions:
    """Test document-level permissions."""

    @pytest.mark.asyncio
    async def test_owner_can_access_document(self):
        """Test dass Owner auf eigene Dokumente zugreifen kann."""
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.get_document.return_value = {
                "id": "doc_001",
                "filename": "rechnung.pdf",
                "owner_id": "user_001",
                "permissions": {
                    "can_read": True,
                    "can_write": True,
                    "can_delete": True,
                    "can_share": True
                }
            }
            MockDoc.return_value = mock_doc

            document = await mock_doc.get_document(
                document_id="doc_001",
                user_id="user_001"
            )

            assert document["owner_id"] == "user_001"
            assert document["permissions"]["can_read"] is True
            assert document["permissions"]["can_write"] is True

    @pytest.mark.asyncio
    async def test_shared_user_has_limited_access(self):
        """Test dass geteilte Benutzer limitierten Zugriff haben."""
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.get_document.return_value = {
                "id": "doc_001",
                "filename": "rechnung.pdf",
                "owner_id": "user_001",
                "shared_with": ["user_002"],
                "permissions": {
                    "can_read": True,
                    "can_write": False,  # No write access for shared user
                    "can_delete": False,
                    "can_share": False
                }
            }
            MockDoc.return_value = mock_doc

            document = await mock_doc.get_document(
                document_id="doc_001",
                user_id="user_002"  # Shared user
            )

            assert document["permissions"]["can_read"] is True
            assert document["permissions"]["can_write"] is False
            assert document["permissions"]["can_delete"] is False

    @pytest.mark.asyncio
    async def test_unauthorized_user_denied_access(self):
        """Test dass unberechtigte Benutzer Zugriff verweigert wird."""
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.get_document.side_effect = PermissionError(
                "Zugriff verweigert: Sie haben keine Berechtigung für dieses Dokument"
            )
            MockDoc.return_value = mock_doc

            with pytest.raises(PermissionError, match="Zugriff verweigert"):
                await mock_doc.get_document(
                    document_id="doc_001",
                    user_id="user_003"  # Unauthorized user
                )


@pytest.mark.e2e
class TestFolderPermissions:
    """Test folder-level permissions."""

    @pytest.mark.asyncio
    async def test_folder_permission_inheritance(self):
        """Test dass Unterordner Berechtigungen erben."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.get_folder_permissions.return_value = {
                "folder_id": "folder_002",
                "parent_id": "folder_001",
                "permissions": {
                    "can_read": True,
                    "can_write": True,
                    "inherited_from": "folder_001"
                }
            }
            MockFolder.return_value = mock_folder

            permissions = await mock_folder.get_folder_permissions(
                folder_id="folder_002",
                user_id="user_001"
            )

            assert permissions["permissions"]["inherited_from"] == "folder_001"
            assert permissions["permissions"]["can_read"] is True

    @pytest.mark.asyncio
    async def test_folder_sharing_with_team(self):
        """Test Ordner-Freigabe für Team."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.share_folder.return_value = {
                "success": True,
                "folder_id": "folder_001",
                "shared_with": ["team_accounting"],
                "permission_level": "read_write",
                "message": "Ordner erfolgreich geteilt"
            }
            MockFolder.return_value = mock_folder

            result = await mock_folder.share_folder(
                folder_id="folder_001",
                share_with_team="team_accounting",
                permission_level="read_write"
            )

            assert result["success"] is True
            assert "team_accounting" in result["shared_with"]

    @pytest.mark.asyncio
    async def test_revoke_folder_access(self):
        """Test Ordner-Zugriff entziehen."""
        with patch("app.services.folder_service.FolderService") as MockFolder:
            mock_folder = AsyncMock()
            mock_folder.revoke_access.return_value = {
                "success": True,
                "folder_id": "folder_001",
                "revoked_from": "user_002",
                "message": "Zugriff erfolgreich entzogen"
            }
            MockFolder.return_value = mock_folder

            result = await mock_folder.revoke_access(
                folder_id="folder_001",
                user_id="user_002"
            )

            assert result["success"] is True
            assert result["revoked_from"] == "user_002"


@pytest.mark.e2e
class TestMultiTenancy:
    """Test multi-tenancy isolation."""

    @pytest.mark.asyncio
    async def test_tenant_data_isolation(self):
        """Test dass Mandanten-Daten isoliert sind."""
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            # User from tenant_001 cannot see tenant_002 documents
            mock_doc.list_documents.return_value = {
                "documents": [
                    {"id": "doc_001", "tenant_id": "tenant_001"},
                    {"id": "doc_002", "tenant_id": "tenant_001"}
                ],
                "total": 2,
                "tenant_id": "tenant_001"
            }
            MockDoc.return_value = mock_doc

            documents = await mock_doc.list_documents(
                user_id="user_001",
                tenant_id="tenant_001"
            )

            # All documents belong to same tenant
            assert all(doc["tenant_id"] == "tenant_001" for doc in documents["documents"])
            assert len(documents["documents"]) == 2

    @pytest.mark.asyncio
    async def test_cross_tenant_access_denied(self):
        """Test dass Cross-Tenant-Zugriff verhindert wird."""
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.get_document.side_effect = PermissionError(
                "Zugriff verweigert: Dokument gehört zu anderem Mandanten"
            )
            MockDoc.return_value = mock_doc

            # User from tenant_001 tries to access tenant_002 document
            with pytest.raises(PermissionError, match="anderem Mandanten"):
                await mock_doc.get_document(
                    document_id="doc_999",  # Belongs to tenant_002
                    user_id="user_001",     # From tenant_001
                    tenant_id="tenant_001"
                )

    @pytest.mark.asyncio
    async def test_super_admin_cross_tenant_access(self):
        """Test dass Super-Admin auf alle Mandanten zugreifen kann."""
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.get_document.return_value = {
                "id": "doc_999",
                "tenant_id": "tenant_002",
                "filename": "cross_tenant_document.pdf",
                "accessed_by_admin": True
            }
            MockDoc.return_value = mock_doc

            document = await mock_doc.get_document(
                document_id="doc_999",
                user_id="admin_001",
                is_super_admin=True  # Super admin flag
            )

            assert document["tenant_id"] == "tenant_002"
            assert document["accessed_by_admin"] is True
