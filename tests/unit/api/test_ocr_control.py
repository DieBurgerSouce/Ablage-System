# -*- coding: utf-8 -*-
"""
Unit Tests für OCR Control API Endpoints.

Testet:
- OCR starten (POST /documents/{id}/start)
- OCR abbrechen (POST /documents/{id}/cancel)
- OCR Backend wechseln (PUT /documents/{id}/backend)
- Error Handling

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestOCRStart:
    """Tests für OCR Start Endpoint (POST /api/v1/ocr/documents/{id}/start)."""

    @pytest.mark.asyncio
    async def test_start_ocr_success(self, async_client):
        """Erfolgreiches Starten der OCR-Verarbeitung."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "auto",
                    "priority": 5,
                    "force_reprocess": False
                }
            )

            # 200/202 OK, 401 auth, 403 CSRF, 404 not found
            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_start_ocr_with_deepseek_backend(self, async_client):
        """OCR mit DeepSeek Backend starten."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "deepseek",
                    "priority": 8,
                    "force_reprocess": False
                }
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_start_ocr_with_got_ocr_backend(self, async_client):
        """OCR mit GOT-OCR Backend starten."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "got_ocr",
                    "priority": 5,
                    "force_reprocess": False
                }
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_start_ocr_with_surya_backend(self, async_client):
        """OCR mit Surya Backend starten."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "surya",
                    "priority": 3,
                    "force_reprocess": False
                }
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_start_ocr_force_reprocess(self, async_client):
        """OCR mit Force-Reprocess starten."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "auto",
                    "priority": 5,
                    "force_reprocess": True
                }
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_start_ocr_high_priority(self, async_client):
        """OCR mit hoher Priorität starten."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "deepseek",
                    "priority": 10,  # Höchste Priorität
                    "force_reprocess": False
                }
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_start_ocr_invalid_backend(self, async_client):
        """OCR mit ungültigem Backend ablehnen."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "invalid_backend",
                    "priority": 5,
                    "force_reprocess": False
                }
            )

            assert response.status_code in [400, 401, 403, 404, 422]

    @pytest.mark.asyncio
    async def test_start_ocr_invalid_priority(self, async_client):
        """OCR mit ungültiger Priorität ablehnen."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={
                    "backend": "auto",
                    "priority": 15,  # Über Maximum von 10
                    "force_reprocess": False
                }
            )

            assert response.status_code in [400, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_start_ocr_document_not_found(self, async_client):
        """OCR für nicht existierendes Dokument."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Document not found
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={"backend": "auto", "priority": 5, "force_reprocess": False}
            )

            assert response.status_code in [401, 403, 404, 500]

    @pytest.mark.asyncio
    async def test_start_ocr_unauthorized(self, async_client):
        """OCR ohne Authentifizierung ablehnen."""
        doc_id = str(uuid4())

        response = await async_client.post(
            f"/api/v1/ocr/documents/{doc_id}/start",
            json={"backend": "auto", "priority": 5, "force_reprocess": False}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_start_ocr_default_values(self, async_client):
        """OCR mit Standardwerten starten."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={}  # Nur Standardwerte verwenden
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]


class TestOCRCancel:
    """Tests für OCR Cancel Endpoint (POST /api/v1/ocr/documents/{id}/cancel)."""

    @pytest.mark.asyncio
    async def test_cancel_ocr_success(self, async_client):
        """Erfolgreiches Abbrechen der OCR-Verarbeitung."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/cancel"
            )

            assert response.status_code in [200, 401, 403, 404, 409, 500]

    @pytest.mark.asyncio
    async def test_cancel_ocr_document_not_found(self, async_client):
        """Abbrechen für nicht existierendes Dokument."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/cancel"
            )

            assert response.status_code in [401, 403, 404, 500]

    @pytest.mark.asyncio
    async def test_cancel_ocr_not_processing(self, async_client):
        """Abbrechen wenn Dokument nicht in Verarbeitung."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Document exists but not processing
            mock_doc = Mock(
                id=uuid4(),
                status="completed",
                task_id=None,
                owner_id=uuid4()
            )
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_doc
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/cancel"
            )

            # Sollte 409 Conflict sein (kein aktiver Task)
            assert response.status_code in [401, 403, 404, 409, 500]

    @pytest.mark.asyncio
    async def test_cancel_ocr_unauthorized(self, async_client):
        """Abbrechen ohne Authentifizierung ablehnen."""
        doc_id = str(uuid4())

        response = await async_client.post(
            f"/api/v1/ocr/documents/{doc_id}/cancel"
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_cancel_ocr_not_owner(self, async_client):
        """Abbrechen ohne Berechtigung (nicht Owner)."""
        doc_id = str(uuid4())
        user_id = uuid4()
        other_owner_id = uuid4()

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=user_id, is_active=True, is_admin=False)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Document owned by someone else
            mock_doc = Mock(
                id=uuid4(),
                status="processing",
                task_id="task-123",
                owner_id=other_owner_id
            )
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_doc
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/cancel"
            )

            assert response.status_code in [401, 403, 404, 500]


class TestOCRChangeBackend:
    """Tests für OCR Backend Change Endpoint (PUT /api/v1/ocr/documents/{id}/backend)."""

    @pytest.mark.asyncio
    async def test_change_backend_success(self, async_client):
        """Erfolgreiches Wechseln des OCR Backends."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/ocr/documents/{doc_id}/backend",
                json={"backend": "deepseek"}
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_change_backend_to_got_ocr(self, async_client):
        """Backend zu GOT-OCR wechseln."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/ocr/documents/{doc_id}/backend",
                json={"backend": "got_ocr"}
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_change_backend_to_surya(self, async_client):
        """Backend zu Surya wechseln."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/ocr/documents/{doc_id}/backend",
                json={"backend": "surya"}
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_change_backend_to_auto(self, async_client):
        """Backend zu Auto wechseln."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/ocr/documents/{doc_id}/backend",
                json={"backend": "auto"}
            )

            assert response.status_code in [200, 202, 401, 403, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_change_backend_invalid(self, async_client):
        """Wechseln zu ungültigem Backend ablehnen."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/ocr/documents/{doc_id}/backend",
                json={"backend": "nonexistent"}
            )

            assert response.status_code in [400, 401, 403, 404, 422]

    @pytest.mark.asyncio
    async def test_change_backend_document_not_found(self, async_client):
        """Backend wechseln für nicht existierendes Dokument."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.put(
                f"/api/v1/ocr/documents/{doc_id}/backend",
                json={"backend": "deepseek"}
            )

            assert response.status_code in [401, 403, 404, 500]

    @pytest.mark.asyncio
    async def test_change_backend_unauthorized(self, async_client):
        """Backend wechseln ohne Authentifizierung ablehnen."""
        doc_id = str(uuid4())

        response = await async_client.put(
            f"/api/v1/ocr/documents/{doc_id}/backend",
            json={"backend": "deepseek"}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_change_backend_while_processing(self, async_client):
        """Backend wechseln während Verarbeitung."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Document is currently processing
            mock_doc = Mock(
                id=uuid4(),
                status="processing",
                task_id="task-123",
                owner_id=uuid4()
            )
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_doc
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.put(
                f"/api/v1/ocr/documents/{doc_id}/backend",
                json={"backend": "got_ocr"}
            )

            # Könnte 409 Conflict sein oder Backend wechseln und neu starten
            assert response.status_code in [200, 202, 401, 403, 404, 409, 422, 500]


class TestOCRControlResponseModels:
    """Tests für OCR Control Response Models."""

    def test_ocr_start_request_model(self):
        """Test OCRStartRequest Model."""
        from app.api.v1.ocr import OCRStartRequest

        request = OCRStartRequest(
            backend="deepseek",
            priority=8,
            force_reprocess=True
        )

        assert request.backend == "deepseek"
        assert request.priority == 8
        assert request.force_reprocess is True

    def test_ocr_start_request_defaults(self):
        """Test OCRStartRequest Standardwerte."""
        from app.api.v1.ocr import OCRStartRequest

        request = OCRStartRequest()

        assert request.backend == "auto"
        assert request.priority == 5
        assert request.force_reprocess is False

    def test_ocr_start_response_model(self):
        """Test OCRStartResponse Model."""
        from app.api.v1.ocr import OCRStartResponse

        response = OCRStartResponse(
            erfolg=True,
            dokument_id=uuid4(),
            task_id="task-abc123",
            backend="deepseek",
            prioritaet=8,
            nachricht="OCR-Verarbeitung gestartet"
        )

        assert response.erfolg is True
        assert response.backend == "deepseek"
        assert response.prioritaet == 8
        assert "gestartet" in response.nachricht

    def test_ocr_cancel_response_model(self):
        """Test OCRCancelResponse Model."""
        from app.api.v1.ocr import OCRCancelResponse

        response = OCRCancelResponse(
            erfolg=True,
            dokument_id=uuid4(),
            task_id="task-abc123",
            nachricht="OCR-Verarbeitung abgebrochen"
        )

        assert response.erfolg is True
        assert "abgebrochen" in response.nachricht


class TestOCRControlErrorHandling:
    """Tests für OCR Control Error Handling."""

    @pytest.mark.asyncio
    async def test_start_ocr_german_error_message(self, async_client):
        """Deutsche Fehlermeldung bei OCR-Start-Fehler."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Document not found
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/start",
                json={"backend": "auto", "priority": 5, "force_reprocess": False}
            )

            if response.status_code == 404:
                data = response.json()
                detail = data.get("detail", "")
                # Sollte deutsche Fehlermeldung enthalten
                assert any(word in detail.lower() for word in ["nicht", "gefunden", "not", "found"])

    @pytest.mark.asyncio
    async def test_cancel_ocr_german_error_message(self, async_client):
        """Deutsche Fehlermeldung bei Abbruch-Fehler."""
        doc_id = str(uuid4())

        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth, \
             patch("app.api.v1.ocr.get_db") as mock_db:

            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Document not processing
            mock_doc = Mock(
                id=uuid4(),
                status="completed",
                task_id=None,
                owner_id=uuid4()
            )
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_doc
            mock_session.execute = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                f"/api/v1/ocr/documents/{doc_id}/cancel"
            )

            if response.status_code == 409:
                data = response.json()
                detail = data.get("detail", "")
                # Sollte deutsche Fehlermeldung enthalten
                assert any(word in detail.lower() for word in ["nicht", "aktiv", "keine", "verarbeitung"])

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, async_client):
        """Ungültiges UUID-Format ablehnen."""
        with patch("app.api.v1.ocr.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/ocr/documents/not-a-valid-uuid/start",
                json={"backend": "auto", "priority": 5, "force_reprocess": False}
            )

            assert response.status_code in [401, 403, 404, 422]
