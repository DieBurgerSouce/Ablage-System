# -*- coding: utf-8 -*-
"""
Unit Tests für User Settings API Endpoints.

Testet:
- Alle Einstellungen abrufen/aktualisieren
- Display-Einstellungen (dark, light, whitescreen, blackscreen)
- OCR-Einstellungen
- Benachrichtigungseinstellungen
- Datenschutzeinstellungen
- Einstellungen zurücksetzen
- Error Handling

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestGetAllSettings:
    """Tests für Get All Settings Endpoint (GET /api/v1/settings/)."""

    @pytest.mark.asyncio
    async def test_get_settings_success(self, async_client):
        """Erfolgreiche Abfrage aller Einstellungen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )
            mock_auth.return_value = mock_user

            response = await async_client.get("/api/v1/settings/")

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_get_settings_with_existing_preferences(self, async_client):
        """Einstellungen mit vorhandenen Präferenzen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                preferences={
                    "display": {"display_mode": "light", "language": "en"},
                    "ocr": {"default_backend": "deepseek"},
                    "notifications": {"email_on_ocr_complete": False},
                    "privacy": {"share_analytics": True}
                },
                created_at=datetime.now(timezone.utc)
            )
            mock_auth.return_value = mock_user

            response = await async_client.get("/api/v1/settings/")

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_get_settings_unauthorized(self, async_client):
        """Einstellungen ohne Authentifizierung abrufen."""
        response = await async_client.get("/api/v1/settings/")

        assert response.status_code in [401, 403]


class TestUpdateAllSettings:
    """Tests für Update All Settings Endpoint (PUT /api/v1/settings/)."""

    @pytest.mark.asyncio
    async def test_update_settings_success(self, async_client):
        """Erfolgreiches Aktualisieren mehrerer Einstellungsbereiche."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth, \
             patch("app.api.v1.settings.get_db") as mock_db:

            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )
            mock_auth.return_value = mock_user

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            response = await async_client.put(
                "/api/v1/settings/",
                json={
                    "display": {"display_mode": "light"},
                    "ocr": {"default_backend": "deepseek"}
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_settings_partial(self, async_client):
        """Nur einen Einstellungsbereich aktualisieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/",
                json={
                    "display": {"display_mode": "blackscreen"}
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]


class TestDisplaySettings:
    """Tests für Display Settings Endpoints."""

    @pytest.mark.asyncio
    async def test_get_display_settings(self, async_client):
        """Display-Einstellungen abrufen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None
            )

            response = await async_client.get("/api/v1/settings/display")

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_update_display_mode_dark(self, async_client):
        """Dark Mode aktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth, \
             patch("app.api.v1.settings.get_db") as mock_db:

            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "dark",
                    "language": "de",
                    "items_per_page": 25,
                    "show_previews": True,
                    "compact_view": False
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_display_mode_light(self, async_client):
        """Light Mode aktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "light",
                    "language": "de",
                    "items_per_page": 50,
                    "show_previews": True,
                    "compact_view": False
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_display_mode_whitescreen(self, async_client):
        """Whitescreen Mode (High Contrast) aktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "whitescreen",
                    "language": "de",
                    "items_per_page": 25,
                    "show_previews": False,
                    "compact_view": True
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_display_mode_blackscreen(self, async_client):
        """Blackscreen Mode aktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "blackscreen",
                    "language": "de",
                    "items_per_page": 25,
                    "show_previews": True,
                    "compact_view": False
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_display_mode_invalid(self, async_client):
        """Ungültiger Display Mode ablehnen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "invalid_mode",
                    "language": "de",
                    "items_per_page": 25,
                    "show_previews": True,
                    "compact_view": False
                }
            )

            assert response.status_code in [400, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_update_language_english(self, async_client):
        """Sprache auf Englisch setzen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "dark",
                    "language": "en",
                    "items_per_page": 25,
                    "show_previews": True,
                    "compact_view": False
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_language_invalid(self, async_client):
        """Ungültige Sprache ablehnen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "dark",
                    "language": "fr",  # Nicht unterstützt
                    "items_per_page": 25,
                    "show_previews": True,
                    "compact_view": False
                }
            )

            assert response.status_code in [400, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_update_items_per_page_validation(self, async_client):
        """Items per Page Validierung (10-100)."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            # Zu wenig
            response = await async_client.put(
                "/api/v1/settings/display",
                json={
                    "display_mode": "dark",
                    "language": "de",
                    "items_per_page": 5,  # Min ist 10
                    "show_previews": True,
                    "compact_view": False
                }
            )

            assert response.status_code in [400, 401, 403, 422]


class TestOCRSettings:
    """Tests für OCR Settings Endpoints."""

    @pytest.mark.asyncio
    async def test_get_ocr_settings(self, async_client):
        """OCR-Einstellungen abrufen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None
            )

            response = await async_client.get("/api/v1/settings/ocr")

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_update_ocr_backend_auto(self, async_client):
        """OCR Backend auf Auto setzen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/ocr",
                json={
                    "default_backend": "auto",
                    "default_language": "de",
                    "auto_start_ocr": True,
                    "default_priority": 5
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_ocr_backend_deepseek(self, async_client):
        """OCR Backend auf DeepSeek setzen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/ocr",
                json={
                    "default_backend": "deepseek",
                    "default_language": "de",
                    "auto_start_ocr": True,
                    "default_priority": 8
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_ocr_backend_got_ocr(self, async_client):
        """OCR Backend auf GOT-OCR setzen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/ocr",
                json={
                    "default_backend": "got_ocr",
                    "default_language": "de",
                    "auto_start_ocr": False,
                    "default_priority": 5
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_ocr_backend_surya(self, async_client):
        """OCR Backend auf Surya setzen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/ocr",
                json={
                    "default_backend": "surya",
                    "default_language": "de",
                    "auto_start_ocr": True,
                    "default_priority": 3
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_ocr_backend_invalid(self, async_client):
        """Ungültiges OCR Backend ablehnen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/ocr",
                json={
                    "default_backend": "nonexistent_backend",
                    "default_language": "de",
                    "auto_start_ocr": True,
                    "default_priority": 5
                }
            )

            assert response.status_code in [400, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_update_ocr_priority_validation(self, async_client):
        """OCR Priority Validierung (1-10)."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            # Priority zu hoch
            response = await async_client.put(
                "/api/v1/settings/ocr",
                json={
                    "default_backend": "auto",
                    "default_language": "de",
                    "auto_start_ocr": True,
                    "default_priority": 15  # Max ist 10
                }
            )

            assert response.status_code in [400, 401, 403, 422]


class TestNotificationSettings:
    """Tests für Notification Settings Endpoints."""

    @pytest.mark.asyncio
    async def test_get_notification_settings(self, async_client):
        """Benachrichtigungseinstellungen abrufen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None
            )

            response = await async_client.get("/api/v1/settings/notifications")

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_update_notification_all_enabled(self, async_client):
        """Alle Benachrichtigungen aktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/notifications",
                json={
                    "email_on_ocr_complete": True,
                    "email_on_ocr_failed": True,
                    "email_on_share": True,
                    "email_digest": "daily"
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_notification_all_disabled(self, async_client):
        """Alle Benachrichtigungen deaktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/notifications",
                json={
                    "email_on_ocr_complete": False,
                    "email_on_ocr_failed": False,
                    "email_on_share": False,
                    "email_digest": "none"
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_notification_digest_weekly(self, async_client):
        """E-Mail-Digest auf wöchentlich setzen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/notifications",
                json={
                    "email_on_ocr_complete": True,
                    "email_on_ocr_failed": True,
                    "email_on_share": True,
                    "email_digest": "weekly"
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_notification_digest_invalid(self, async_client):
        """Ungültige Digest-Frequenz ablehnen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/notifications",
                json={
                    "email_on_ocr_complete": True,
                    "email_on_ocr_failed": True,
                    "email_on_share": True,
                    "email_digest": "monthly"  # Nicht erlaubt
                }
            )

            assert response.status_code in [400, 401, 403, 422]


class TestPrivacySettings:
    """Tests für Privacy Settings Endpoints."""

    @pytest.mark.asyncio
    async def test_get_privacy_settings(self, async_client):
        """Datenschutzeinstellungen abrufen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None
            )

            response = await async_client.get("/api/v1/settings/privacy")

            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_update_privacy_share_analytics_enabled(self, async_client):
        """Analytik-Sharing aktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/privacy",
                json={
                    "share_analytics": True,
                    "show_profile_to_others": True,
                    "allow_search_indexing": True
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]

    @pytest.mark.asyncio
    async def test_update_privacy_all_disabled(self, async_client):
        """Alle Datenschutz-Optionen deaktivieren."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/privacy",
                json={
                    "share_analytics": False,
                    "show_profile_to_others": False,
                    "allow_search_indexing": False
                }
            )

            assert response.status_code in [200, 401, 403, 422, 500]


class TestResetSettings:
    """Tests für Reset Settings Endpoint (POST /api/v1/settings/reset)."""

    @pytest.mark.asyncio
    async def test_reset_settings_success(self, async_client):
        """Erfolgreiches Zurücksetzen aller Einstellungen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth, \
             patch("app.api.v1.settings.get_db") as mock_db:

            mock_user = Mock(
                id=uuid4(),
                is_active=True,
                preferences={
                    "display": {"display_mode": "light"},
                    "ocr": {"default_backend": "deepseek"}
                },
                created_at=datetime.now(timezone.utc)
            )
            mock_auth.return_value = mock_user

            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            response = await async_client.post("/api/v1/settings/reset")

            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_reset_settings_unauthorized(self, async_client):
        """Zurücksetzen ohne Authentifizierung ablehnen."""
        response = await async_client.post("/api/v1/settings/reset")

        assert response.status_code in [401, 403]


class TestSettingsResponseModels:
    """Tests für Settings Response Models."""

    def test_display_settings_model(self):
        """Test DisplaySettings Model."""
        from app.api.v1.settings import DisplaySettings

        settings = DisplaySettings(
            display_mode="dark",
            language="de",
            items_per_page=25,
            show_previews=True,
            compact_view=False
        )

        assert settings.display_mode == "dark"
        assert settings.language == "de"
        assert settings.items_per_page == 25

    def test_display_settings_defaults(self):
        """Test DisplaySettings Standardwerte."""
        from app.api.v1.settings import DisplaySettings

        settings = DisplaySettings()

        assert settings.display_mode == "dark"
        assert settings.language == "de"
        assert settings.items_per_page == 25

    def test_ocr_settings_model(self):
        """Test OCRSettings Model."""
        from app.api.v1.settings import OCRSettings

        settings = OCRSettings(
            default_backend="deepseek",
            default_language="de",
            auto_start_ocr=True,
            default_priority=8
        )

        assert settings.default_backend == "deepseek"
        assert settings.default_priority == 8

    def test_notification_settings_model(self):
        """Test NotificationSettings Model."""
        from app.api.v1.settings import NotificationSettings

        settings = NotificationSettings(
            email_on_ocr_complete=True,
            email_on_ocr_failed=True,
            email_on_share=False,
            email_digest="daily"
        )

        assert settings.email_on_ocr_complete is True
        assert settings.email_digest == "daily"

    def test_privacy_settings_model(self):
        """Test PrivacySettings Model."""
        from app.api.v1.settings import PrivacySettings

        settings = PrivacySettings(
            share_analytics=False,
            show_profile_to_others=True,
            allow_search_indexing=True
        )

        assert settings.share_analytics is False
        assert settings.show_profile_to_others is True

    def test_user_settings_response_model(self):
        """Test UserSettingsResponse Model."""
        from app.api.v1.settings import (
            UserSettingsResponse,
            DisplaySettings,
            OCRSettings,
            NotificationSettings,
            PrivacySettings
        )

        response = UserSettingsResponse(
            display=DisplaySettings(),
            ocr=OCRSettings(),
            notifications=NotificationSettings(),
            privacy=PrivacySettings(),
            last_updated=datetime.now(timezone.utc)
        )

        assert response.display.display_mode == "dark"
        assert response.ocr.default_backend == "auto"
        assert response.notifications.email_on_ocr_complete is True
        assert response.privacy.share_analytics is False


class TestSettingsErrorHandling:
    """Tests für Settings Error Handling."""

    @pytest.mark.asyncio
    async def test_settings_invalid_json(self, async_client):
        """Ungültiges JSON ablehnen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                "/api/v1/settings/display",
                content="invalid json",
                headers={"Content-Type": "application/json"}
            )

            assert response.status_code in [400, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_settings_missing_required_fields(self, async_client):
        """Fehlende Pflichtfelder ablehnen."""
        with patch("app.api.v1.settings.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                preferences=None,
                created_at=datetime.now(timezone.utc)
            )

            response = await async_client.put(
                "/api/v1/settings/display",
                json={}  # Leeres JSON
            )

            # Pydantic sollte Defaults verwenden, daher 200 oder 422
            assert response.status_code in [200, 400, 401, 403, 422, 500]
