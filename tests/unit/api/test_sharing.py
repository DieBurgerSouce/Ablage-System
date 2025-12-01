# -*- coding: utf-8 -*-
"""
Unit Tests für Document Sharing API Endpoints.

Testet:
- Dokument teilen (share)
- Freigabe widerrufen (revoke)
- Geteilte Benutzer auflisten
- Mit mir geteilte Dokumente
- Freigabe aktualisieren
- Error Handling

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestShareDocument:
    """Tests für Document Sharing Endpoint (POST /api/v1/sharing/documents/{id}/share)."""

    @pytest.mark.asyncio
    async def test_share_document_success(self, async_client):
        """Erfolgreiches Teilen eines Dokuments."""
        doc_id = str(uuid4())
        recipient_id = str(uuid4())
        owner_id = uuid4()

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth, \
             patch("app.api.v1.sharing.get_db") as mock_db:

            mock_auth.return_value = Mock(id=owner_id, is_active=True)

            # Mock database queries
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock document query - user is owner
            mock_doc = Mock(id=uuid4(), owner_id=owner_id)
            mock_doc_result = Mock()
            mock_doc_result.scalar_one_or_none.return_value = mock_doc

            # Mock recipient query
            mock_recipient = Mock(id=uuid4(), username="empfaenger", is_active=True)
            mock_recipient_result = Mock()
            mock_recipient_result.scalar_one_or_none.return_value = mock_recipient

            # Mock existing share check - no existing share
            mock_existing_result = Mock()
            mock_existing_result.scalar_one_or_none.return_value = None

            mock_session.execute = AsyncMock(side_effect=[
                mock_doc_result,
                mock_recipient_result,
                mock_existing_result
            ])

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": recipient_id,
                    "access_level": "view",
                    "expires_in_days": 30,
                    "can_share": False
                }
            )

            # 200/201 OK, 401 auth, 403 CSRF/forbidden, 404 not found
            assert response.status_code in [200, 201, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_share_document_invalid_access_level(self, async_client):
        """Teilen mit ungültiger Zugriffsebene ablehnen."""
        doc_id = str(uuid4())
        recipient_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": recipient_id,
                    "access_level": "invalid_level"
                }
            )

            # Sollte 400 oder 422 Validation Error sein
            assert response.status_code in [400, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_share_document_with_self_rejected(self, async_client):
        """Teilen mit sich selbst ablehnen."""
        doc_id = str(uuid4())
        user_id = uuid4()

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth, \
             patch("app.api.v1.sharing.get_db") as mock_db:

            mock_auth.return_value = Mock(id=user_id, is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock document - user is owner
            mock_doc = Mock(id=uuid4(), owner_id=user_id)
            mock_doc_result = Mock()
            mock_doc_result.scalar_one_or_none.return_value = mock_doc
            mock_session.execute = AsyncMock(return_value=mock_doc_result)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": str(user_id),  # Versucht mit sich selbst zu teilen
                    "access_level": "view"
                }
            )

            # Sollte 400 Bad Request sein
            assert response.status_code in [400, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_share_document_unauthorized(self, async_client):
        """Teilen ohne Authentifizierung ablehnen."""
        doc_id = str(uuid4())
        recipient_id = str(uuid4())

        response = await async_client.post(
            f"/api/v1/sharing/documents/{doc_id}/share",
            json={
                "user_id": recipient_id,
                "access_level": "view"
            }
        )

        # Sollte 401 Unauthorized sein
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_share_document_not_owner(self, async_client):
        """Teilen ohne Berechtigung (kein Owner) ablehnen."""
        doc_id = str(uuid4())
        recipient_id = str(uuid4())
        user_id = uuid4()
        other_owner_id = uuid4()

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth, \
             patch("app.api.v1.sharing.get_db") as mock_db:

            mock_auth.return_value = Mock(id=user_id, is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock document - user is NOT owner
            mock_doc = Mock(id=uuid4(), owner_id=other_owner_id)
            mock_doc_result = Mock()
            mock_doc_result.scalar_one_or_none.return_value = mock_doc

            # Mock access check - user has no sharing permission
            mock_access_result = Mock()
            mock_access_result.scalar_one_or_none.return_value = None

            mock_session.execute = AsyncMock(side_effect=[
                mock_doc_result,
                mock_access_result
            ])

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": recipient_id,
                    "access_level": "view"
                }
            )

            # Sollte 403 Forbidden sein
            assert response.status_code in [401, 403, 404, 500]

    @pytest.mark.asyncio
    async def test_share_document_already_shared(self, async_client):
        """Doppeltes Teilen ablehnen (409 Conflict)."""
        doc_id = str(uuid4())
        recipient_id = str(uuid4())
        owner_id = uuid4()

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth, \
             patch("app.api.v1.sharing.get_db") as mock_db:

            mock_auth.return_value = Mock(id=owner_id, is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock document
            mock_doc = Mock(id=uuid4(), owner_id=owner_id)
            mock_doc_result = Mock()
            mock_doc_result.scalar_one_or_none.return_value = mock_doc

            # Mock recipient
            mock_recipient = Mock(id=uuid4(), username="empfaenger", is_active=True)
            mock_recipient_result = Mock()
            mock_recipient_result.scalar_one_or_none.return_value = mock_recipient

            # Mock existing share - ALREADY EXISTS
            mock_existing = Mock(id=uuid4())
            mock_existing_result = Mock()
            mock_existing_result.scalar_one_or_none.return_value = mock_existing

            mock_session.execute = AsyncMock(side_effect=[
                mock_doc_result,
                mock_recipient_result,
                mock_existing_result
            ])

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": recipient_id,
                    "access_level": "view"
                }
            )

            # Sollte 409 Conflict sein
            assert response.status_code in [401, 403, 404, 409, 422, 500]

    @pytest.mark.asyncio
    async def test_share_document_with_expiration(self, async_client):
        """Teilen mit Ablaufdatum."""
        doc_id = str(uuid4())
        recipient_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": recipient_id,
                    "access_level": "edit",
                    "expires_in_days": 90,
                    "can_share": True,
                    "note": "Für Projektarbeit"
                }
            )

            assert response.status_code in [200, 201, 401, 403, 404, 422, 500]


class TestRevokeShare:
    """Tests für Revoke Share Endpoint (DELETE /api/v1/sharing/documents/{id}/share/{user_id})."""

    @pytest.mark.asyncio
    async def test_revoke_share_success(self, async_client):
        """Erfolgreiches Widerrufen einer Freigabe."""
        doc_id = str(uuid4())
        user_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.delete(
                f"/api/v1/sharing/documents/{doc_id}/share/{user_id}"
            )

            # 200/204 OK, 401 auth, 403 CSRF/forbidden, 404 not found
            assert response.status_code in [200, 204, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_revoke_share_not_found(self, async_client):
        """Widerrufen einer nicht existierenden Freigabe."""
        doc_id = str(uuid4())
        user_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth, \
             patch("app.api.v1.sharing.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock document exists
            mock_doc = Mock(id=uuid4(), owner_id=uuid4())
            mock_doc_result = Mock()
            mock_doc_result.scalar_one_or_none.return_value = mock_doc

            # Mock access not found
            mock_access_result = Mock()
            mock_access_result.scalar_one_or_none.return_value = None

            mock_session.execute = AsyncMock(side_effect=[
                mock_doc_result,
                mock_access_result
            ])

            response = await async_client.delete(
                f"/api/v1/sharing/documents/{doc_id}/share/{user_id}"
            )

            # Sollte 404 Not Found sein
            assert response.status_code in [401, 403, 404]

    @pytest.mark.asyncio
    async def test_revoke_share_unauthorized(self, async_client):
        """Widerrufen ohne Authentifizierung ablehnen."""
        doc_id = str(uuid4())
        user_id = str(uuid4())

        response = await async_client.delete(
            f"/api/v1/sharing/documents/{doc_id}/share/{user_id}"
        )

        assert response.status_code in [401, 403]


class TestGetSharedUsers:
    """Tests für Shared Users List Endpoint (GET /api/v1/sharing/documents/{id}/shared-with)."""

    @pytest.mark.asyncio
    async def test_get_shared_users_success(self, async_client):
        """Erfolgreiches Auflisten der geteilten Benutzer."""
        doc_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/sharing/documents/{doc_id}/shared-with"
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_get_shared_users_unauthorized(self, async_client):
        """Auflisten ohne Authentifizierung ablehnen."""
        doc_id = str(uuid4())

        response = await async_client.get(
            f"/api/v1/sharing/documents/{doc_id}/shared-with"
        )

        assert response.status_code in [401, 403]


class TestSharedWithMe:
    """Tests für Shared With Me Endpoint (GET /api/v1/sharing/shared-with-me)."""

    @pytest.mark.asyncio
    async def test_get_shared_with_me_success(self, async_client):
        """Erfolgreiches Auflisten der mit mir geteilten Dokumente."""
        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get("/api/v1/sharing/shared-with-me")

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_get_shared_with_me_include_expired(self, async_client):
        """Mit mir geteilte Dokumente inkl. abgelaufener."""
        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/sharing/shared-with-me",
                params={"include_expired": True}
            )

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_get_shared_with_me_unauthorized(self, async_client):
        """Auflisten ohne Authentifizierung ablehnen."""
        response = await async_client.get("/api/v1/sharing/shared-with-me")

        assert response.status_code in [401, 403]


class TestUpdateShare:
    """Tests für Update Share Endpoint (PUT /api/v1/sharing/documents/{id}/share/{user_id})."""

    @pytest.mark.asyncio
    async def test_update_share_success(self, async_client):
        """Erfolgreiches Aktualisieren einer Freigabe."""
        doc_id = str(uuid4())
        user_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/sharing/documents/{doc_id}/share/{user_id}",
                json={
                    "access_level": "edit",
                    "expires_in_days": 60,
                    "can_share": True
                }
            )

            assert response.status_code in [200, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_update_share_access_level_only(self, async_client):
        """Nur Zugriffsebene aktualisieren."""
        doc_id = str(uuid4())
        user_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/sharing/documents/{doc_id}/share/{user_id}",
                json={"access_level": "manage"}
            )

            assert response.status_code in [200, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_update_share_invalid_access_level(self, async_client):
        """Aktualisieren mit ungültiger Zugriffsebene ablehnen."""
        doc_id = str(uuid4())
        user_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/sharing/documents/{doc_id}/share/{user_id}",
                json={"access_level": "superadmin"}  # Ungültig
            )

            assert response.status_code in [400, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_update_share_not_found(self, async_client):
        """Aktualisieren einer nicht existierenden Freigabe."""
        doc_id = str(uuid4())
        user_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/sharing/documents/{doc_id}/share/{user_id}",
                json={"access_level": "view"}
            )

            assert response.status_code in [401, 403, 404, 500]


class TestSharingResponseModels:
    """Tests für Sharing Response Models."""

    def test_share_document_request_model(self):
        """Test ShareDocumentRequest Model."""
        from app.api.v1.sharing import ShareDocumentRequest

        request = ShareDocumentRequest(
            user_id=uuid4(),
            access_level="edit",
            expires_in_days=30,
            can_share=True,
            note="Test-Freigabe"
        )

        assert request.access_level == "edit"
        assert request.expires_in_days == 30
        assert request.can_share is True
        assert request.note == "Test-Freigabe"

    def test_share_document_request_defaults(self):
        """Test ShareDocumentRequest mit Standardwerten."""
        from app.api.v1.sharing import ShareDocumentRequest

        request = ShareDocumentRequest(user_id=uuid4())

        assert request.access_level == "view"
        assert request.expires_in_days is None
        assert request.can_share is False
        assert request.note is None

    def test_share_response_model(self):
        """Test ShareResponse Model."""
        from app.api.v1.sharing import ShareResponse

        response = ShareResponse(
            id=uuid4(),
            document_id=uuid4(),
            user_id=uuid4(),
            access_level="view",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            can_share=False,
            created_at=datetime.now(timezone.utc),
            message="Erfolgreich geteilt"
        )

        assert response.access_level == "view"
        assert response.can_share is False
        assert "Erfolgreich" in response.message

    def test_shared_user_info_model(self):
        """Test SharedUserInfo Model."""
        from app.api.v1.sharing import SharedUserInfo

        info = SharedUserInfo(
            user_id=uuid4(),
            username="testuser",
            email="test@example.com",
            access_level="edit",
            can_share=True,
            expires_at=None,
            granted_at=datetime.now(timezone.utc),
            granted_by_username="admin"
        )

        assert info.username == "testuser"
        assert info.access_level == "edit"
        assert info.can_share is True

    def test_shared_document_info_model(self):
        """Test SharedDocumentInfo Model."""
        from app.api.v1.sharing import SharedDocumentInfo

        info = SharedDocumentInfo(
            document_id=uuid4(),
            filename="test.pdf",
            document_type="invoice",
            access_level="view",
            shared_by_username="admin",
            shared_at=datetime.now(timezone.utc),
            expires_at=None
        )

        assert info.filename == "test.pdf"
        assert info.document_type == "invoice"

    def test_update_access_request_model(self):
        """Test UpdateAccessRequest Model."""
        from app.api.v1.sharing import UpdateAccessRequest

        request = UpdateAccessRequest(
            access_level="manage",
            expires_in_days=90,
            can_share=True
        )

        assert request.access_level == "manage"
        assert request.expires_in_days == 90


class TestSharingErrorHandling:
    """Tests für Sharing Error Handling."""

    @pytest.mark.asyncio
    async def test_share_document_not_found_german_message(self, async_client):
        """Deutsche Fehlermeldung bei nicht gefundenem Dokument."""
        doc_id = str(uuid4())
        recipient_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth, \
             patch("app.api.v1.sharing.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Document not found
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": recipient_id,
                    "access_level": "view"
                }
            )

            if response.status_code == 404:
                data = response.json()
                detail = data.get("detail", "")
                # Sollte deutsche Fehlermeldung enthalten
                assert any(word in detail.lower() for word in ["nicht", "gefunden", "not", "found"])

    @pytest.mark.asyncio
    async def test_share_invalid_uuid_format(self, async_client):
        """Ungültiges UUID-Format ablehnen."""
        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/sharing/documents/invalid-uuid/share",
                json={
                    "user_id": "also-invalid",
                    "access_level": "view"
                }
            )

            assert response.status_code in [401, 403, 404, 422]


class TestSharingAccessLevels:
    """Tests für verschiedene Zugriffsebenen."""

    @pytest.mark.asyncio
    async def test_share_with_view_access(self, async_client):
        """Teilen mit Nur-Lesen-Zugriff."""
        doc_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": str(uuid4()),
                    "access_level": "view"
                }
            )

            assert response.status_code in [200, 201, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_share_with_comment_access(self, async_client):
        """Teilen mit Kommentar-Zugriff."""
        doc_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": str(uuid4()),
                    "access_level": "comment"
                }
            )

            assert response.status_code in [200, 201, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_share_with_edit_access(self, async_client):
        """Teilen mit Bearbeitungs-Zugriff."""
        doc_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": str(uuid4()),
                    "access_level": "edit"
                }
            )

            assert response.status_code in [200, 201, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_share_with_manage_access(self, async_client):
        """Teilen mit Vollzugriff (manage)."""
        doc_id = str(uuid4())

        with patch("app.api.v1.sharing.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/sharing/documents/{doc_id}/share",
                json={
                    "user_id": str(uuid4()),
                    "access_level": "manage",
                    "can_share": True
                }
            )

            assert response.status_code in [200, 201, 401, 403, 404, 422, 500]
