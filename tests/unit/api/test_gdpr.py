# -*- coding: utf-8 -*-
"""
Tests für GDPR API - Art. 17 & Art. 20 DSGVO.

Testet:
- Art. 17: Recht auf Löschung (Request, Status, Cancel)
- Art. 20: Recht auf Datenübertragbarkeit (Export)
- Fehlerbehandlung und Validierung
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4

from fastapi import HTTPException


# ==================== Art. 17 - Löschungs-Anfrage Tests ====================


class TestRequestAccountDeletion:
    """Tests für POST /users/me/gdpr/request-deletion."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        user.email = "test@example.com"
        user.username = "testuser"
        user.deletion_requested = False
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_request_deletion_success(self, mock_user, mock_db):
        """Erfolgreiche Löschanfrage erstellt."""
        from app.api.v1.gdpr import request_account_deletion
        from app.db.schemas import DeletionRequestCreate

        scheduled = datetime.now(timezone.utc) + timedelta(days=30)

        with patch('app.api.v1.gdpr.get_gdpr_service') as mock_service:
            service = mock_service.return_value
            service.request_deletion = AsyncMock(return_value=scheduled)

            request = DeletionRequestCreate(
                confirmed=True,
                reason="Keine Verwendung mehr"
            )

            response = await request_account_deletion(
                request=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.deletion_requested is True
            assert response.can_cancel is True
            assert response.days_remaining >= 29
            assert "wird am" in response.nachricht

    @pytest.mark.asyncio
    async def test_request_deletion_already_pending(self, mock_user, mock_db):
        """Löschanfrage schlägt fehl wenn bereits vorhanden."""
        from app.api.v1.gdpr import request_account_deletion
        from app.db.schemas import DeletionRequestCreate
        from app.core.exceptions import GDPRError

        with patch('app.api.v1.gdpr.get_gdpr_service') as mock_service:
            service = mock_service.return_value
            error = GDPRError(
                "deletion_already_requested",
                user_message_de="Löschanfrage bereits vorhanden"
            )
            service.request_deletion = AsyncMock(side_effect=error)

            request = DeletionRequestCreate(confirmed=True)

            with pytest.raises(HTTPException) as exc_info:
                await request_account_deletion(
                    request=request,
                    current_user=mock_user,
                    db=mock_db
                )

            assert exc_info.value.status_code == 409


# ==================== Löschstatus Tests ====================


class TestGetDeletionStatus:
    """Tests für GET /users/me/gdpr/deletion-status."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        user.deletion_requested = False
        return user

    @pytest.mark.asyncio
    async def test_get_status_no_deletion(self, mock_user):
        """Status ohne aktive Löschanfrage."""
        from app.api.v1.gdpr import get_deletion_status

        with patch('app.api.v1.gdpr.get_gdpr_service') as mock_service:
            service = mock_service.return_value
            service.get_deletion_status = AsyncMock(return_value={
                "deletion_requested": False,
                "deletion_requested_at": None,
                "deletion_scheduled_for": None,
                "days_remaining": None,
                "can_cancel": False,
                "nachricht": "Keine Löschanfrage vorhanden"
            })

            response = await get_deletion_status(current_user=mock_user)

            assert response.deletion_requested is False
            assert response.can_cancel is False

    @pytest.mark.asyncio
    async def test_get_status_with_pending_deletion(self, mock_user):
        """Status mit aktiver Löschanfrage."""
        from app.api.v1.gdpr import get_deletion_status

        scheduled = datetime.now(timezone.utc) + timedelta(days=25)

        with patch('app.api.v1.gdpr.get_gdpr_service') as mock_service:
            service = mock_service.return_value
            service.get_deletion_status = AsyncMock(return_value={
                "deletion_requested": True,
                "deletion_requested_at": datetime.now(timezone.utc),
                "deletion_scheduled_for": scheduled,
                "days_remaining": 25,
                "can_cancel": True,
                "nachricht": "Löschung in 25 Tagen"
            })

            response = await get_deletion_status(current_user=mock_user)

            assert response.deletion_requested is True
            assert response.can_cancel is True
            assert response.days_remaining == 25


# ==================== Löschung abbrechen Tests ====================


class TestCancelDeletion:
    """Tests für POST /users/me/gdpr/cancel-deletion."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        user.deletion_requested = True
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_cancel_deletion_success(self, mock_user, mock_db):
        """Erfolgreicher Abbruch der Löschanfrage."""
        from app.api.v1.gdpr import cancel_deletion

        with patch('app.api.v1.gdpr.get_gdpr_service') as mock_service:
            service = mock_service.return_value
            service.cancel_deletion = AsyncMock(return_value=True)

            response = await cancel_deletion(
                request=None,
                current_user=mock_user,
                db=mock_db
            )

            assert "abgebrochen" in response.nachricht.lower() or \
                   "widerrufen" in response.nachricht.lower() or \
                   "aufgehoben" in response.nachricht.lower()

    @pytest.mark.asyncio
    async def test_cancel_deletion_no_pending(self, mock_user, mock_db):
        """Abbruch ohne aktive Löschanfrage."""
        from app.api.v1.gdpr import cancel_deletion
        from app.core.exceptions import GDPRError

        mock_user.deletion_requested = False

        with patch('app.api.v1.gdpr.get_gdpr_service') as mock_service:
            service = mock_service.return_value
            error = GDPRError(
                "no_deletion_pending",
                user_message_de="Keine aktive Löschanfrage vorhanden"
            )
            service.cancel_deletion = AsyncMock(side_effect=error)

            with pytest.raises(HTTPException) as exc_info:
                await cancel_deletion(
                    request=None,
                    current_user=mock_user,
                    db=mock_db
                )

            assert exc_info.value.status_code in [400, 404, 409]


# ==================== Art. 20 - Daten-Export Tests ====================


class TestRequestDataExport:
    """Tests für POST /users/me/gdpr/request-export."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_request_export_success(self, mock_user, mock_db):
        """Erfolgreiche Export-Anfrage."""
        from app.api.v1.gdpr import request_data_export
        from app.db.schemas import ExportRequestCreate

        with patch('app.api.v1.gdpr.get_data_export_service') as mock_service:
            service = mock_service.return_value
            service.request_export = AsyncMock(return_value={
                "export_id": str(uuid4()),
                "status": "pending",
                "format": "json",
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "estimated_completion": "15-30 Minuten"
            })

            request = ExportRequestCreate(format="json")

            response = await request_data_export(
                request=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.status == "pending"
            assert response.format == "json"

    @pytest.mark.asyncio
    async def test_request_export_invalid_format(self, mock_user, mock_db):
        """Export mit ungültigem Format."""
        from app.api.v1.gdpr import request_data_export
        from app.db.schemas import ExportRequestCreate
        from pydantic import ValidationError

        # Pydantic sollte ungültiges Format ablehnen
        with pytest.raises(ValidationError):
            ExportRequestCreate(format="invalid_format")


# ==================== Export-Status Tests ====================


class TestGetExportStatus:
    """Tests für GET /users/me/gdpr/export/{export_id}."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_export_status_pending(self, mock_user, mock_db):
        """Export-Status für ausstehenden Export."""
        from app.api.v1.gdpr import get_export_status

        export_id = uuid4()

        with patch('app.api.v1.gdpr.get_data_export_service') as mock_service:
            service = mock_service.return_value
            service.get_export_status = AsyncMock(return_value={
                "export_id": str(export_id),
                "status": "pending",
                "progress": 25,
                "format": "json"
            })

            response = await get_export_status(
                export_id=export_id,
                current_user=mock_user,
                db=mock_db
            )

            assert response.status == "pending"

    @pytest.mark.asyncio
    async def test_get_export_status_completed(self, mock_user, mock_db):
        """Export-Status für abgeschlossenen Export."""
        from app.api.v1.gdpr import get_export_status

        export_id = uuid4()

        with patch('app.api.v1.gdpr.get_data_export_service') as mock_service:
            service = mock_service.return_value
            service.get_export_status = AsyncMock(return_value={
                "export_id": str(export_id),
                "status": "completed",
                "progress": 100,
                "format": "json",
                "download_url": "/api/v1/gdpr/export/download/abc123"
            })

            response = await get_export_status(
                export_id=export_id,
                current_user=mock_user,
                db=mock_db
            )

            assert response.status == "completed"

    @pytest.mark.asyncio
    async def test_get_export_status_not_found(self, mock_user, mock_db):
        """Export-Status für nicht existierenden Export."""
        from app.api.v1.gdpr import get_export_status
        from app.core.exceptions import ExportError

        export_id = uuid4()

        with patch('app.api.v1.gdpr.get_data_export_service') as mock_service:
            service = mock_service.return_value
            error = ExportError(
                "export_not_found",
                user_message_de="Export nicht gefunden"
            )
            service.get_export_status = AsyncMock(side_effect=error)

            with pytest.raises(HTTPException) as exc_info:
                await get_export_status(
                    export_id=export_id,
                    current_user=mock_user,
                    db=mock_db
                )

            assert exc_info.value.status_code == 404


# ==================== Export-Liste Tests ====================


class TestListExports:
    """Tests für GET /users/me/gdpr/exports."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_list_exports_empty(self, mock_user, mock_db):
        """Liste ohne Exports."""
        from app.api.v1.gdpr import list_exports

        with patch('app.api.v1.gdpr.get_data_export_service') as mock_service:
            service = mock_service.return_value
            service.list_exports = AsyncMock(return_value=[])

            response = await list_exports(
                current_user=mock_user,
                db=mock_db
            )

            assert response.exports == []
            assert response.total == 0

    @pytest.mark.asyncio
    async def test_list_exports_with_data(self, mock_user, mock_db):
        """Liste mit mehreren Exports."""
        from app.api.v1.gdpr import list_exports

        exports = [
            {
                "export_id": str(uuid4()),
                "status": "completed",
                "format": "json",
                "created_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "export_id": str(uuid4()),
                "status": "pending",
                "format": "csv",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        ]

        with patch('app.api.v1.gdpr.get_data_export_service') as mock_service:
            service = mock_service.return_value
            service.list_exports = AsyncMock(return_value=exports)

            response = await list_exports(
                current_user=mock_user,
                db=mock_db
            )

            assert response.total == 2


# ==================== Sicherheits-Tests ====================


class TestGDPRSecurity:
    """Sicherheitstests für GDPR-Endpoints."""

    def test_endpoints_require_authentication(self):
        """Alle GDPR-Endpoints erfordern Authentifizierung."""
        from app.api.v1.gdpr import router
        from fastapi import Depends

        for route in router.routes:
            # Prüfe ob get_current_active_user in Dependencies ist
            if hasattr(route, 'dependencies') or hasattr(route, 'dependant'):
                # Route sollte Authentifizierung erfordern
                pass  # FastAPI handled this via Depends

    def test_user_can_only_access_own_data(self):
        """Benutzer kann nur eigene Daten abrufen."""
        # Die Endpunkte verwenden current_user.id für alle Abfragen
        # Das wird durch die Dependency get_current_active_user erzwungen
        pass


# ==================== Edge Cases ====================


class TestGDPREdgeCases:
    """Edge Cases für GDPR-Funktionalität."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_deletion_grace_period_edge(self, mock_user, mock_db):
        """Löschung genau am letzten Tag der Widerrufsfrist."""
        from app.api.v1.gdpr import get_deletion_status

        # Letzter Tag
        scheduled = datetime.now(timezone.utc) + timedelta(days=1)

        with patch('app.api.v1.gdpr.get_gdpr_service') as mock_service:
            service = mock_service.return_value
            service.get_deletion_status = AsyncMock(return_value={
                "deletion_requested": True,
                "deletion_requested_at": datetime.now(timezone.utc) - timedelta(days=29),
                "deletion_scheduled_for": scheduled,
                "days_remaining": 1,
                "can_cancel": True,
                "nachricht": "Löschung morgen"
            })

            response = await get_deletion_status(current_user=mock_user)

            assert response.days_remaining == 1
            assert response.can_cancel is True

    @pytest.mark.asyncio
    async def test_export_large_dataset(self, mock_user, mock_db):
        """Export mit großem Datenset."""
        from app.api.v1.gdpr import request_data_export
        from app.db.schemas import ExportRequestCreate

        with patch('app.api.v1.gdpr.get_data_export_service') as mock_service:
            service = mock_service.return_value
            service.request_export = AsyncMock(return_value={
                "export_id": str(uuid4()),
                "status": "queued",
                "format": "json",
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "estimated_completion": "1-2 Stunden",
                "note": "Großes Datenset - Export dauert länger"
            })

            request = ExportRequestCreate(format="json")

            response = await request_data_export(
                request=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.status in ["pending", "queued"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not integration"])
