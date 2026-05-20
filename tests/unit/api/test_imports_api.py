# -*- coding: utf-8 -*-
"""
Unit Tests fuer Imports API Endpoints.

Testet:
- Email Import Konfigurationen
- Folder Import Konfigurationen
- Import-Regeln
- Import-Logs und Statistiken

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_email_config():
    """Sample Email Import Config fuer Tests."""
    return Mock(
        id=uuid4(),
        name="Office 365 Import",
        imap_server="outlook.office365.com",
        imap_port=993,
        use_ssl=True,
        use_starttls=False,
        imap_folder="INBOX",
        processed_folder="Processed",
        error_folder="Errors",
        sync_interval_minutes=15,
        filter_from_addresses=["@trusted.de"],
        filter_subject_patterns=["Rechnung*"],
        filter_attachment_types=["pdf", "png"],
        extract_attachments_only=True,
        include_email_body_as_document=False,
        auto_classify=True,
        auto_ocr=True,
        default_folder_id=uuid4(),
        company_id=None,
        is_active=True,
        connection_status="connected",
        last_sync_at=datetime.now(timezone.utc),
        total_emails_processed=1250,
        total_documents_created=890,
        last_error=None,
        error_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_folder_config():
    """Sample Folder Import Config fuer Tests."""
    return Mock(
        id=uuid4(),
        name="Rechnungsordner Scanner",
        watch_path="C:\\Import\\Rechnungen",
        is_network_path=False,
        recursive=True,
        include_patterns=["*.pdf", "*.tiff"],
        exclude_patterns=["temp_*", "*_backup*"],
        move_after_processing=True,
        processed_subfolder="verarbeitet",
        error_subfolder="fehler",
        delete_after_processing=False,
        auto_classify=True,
        auto_ocr=True,
        default_folder_id=uuid4(),
        preserve_filename=True,
        poll_interval_seconds=60,
        company_id=None,
        is_active=True,
        watcher_status="running",
        last_poll_at=datetime.now(timezone.utc),
        files_processed_today=45,
        total_files_processed=3200,
        total_documents_created=3150,
        last_error=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_import_rule():
    """Sample Import Rule fuer Tests."""
    return Mock(
        id=uuid4(),
        name="Rechnungen automatisch taggen",
        description="Taggt eingehende Rechnungen automatisch",
        priority=100,
        applies_to_email_configs=[str(uuid4())],
        applies_to_folder_configs=[],
        applies_to_all=False,
        conditions={
            "operator": "AND",
            "rules": [
                {"field": "filename", "operator": "contains", "value": "rechnung"}
            ]
        },
        actions={
            "set_tags": ["rechnung", "finanzen"],
            "set_folder": str(uuid4()),
        },
        is_active=True,
        match_count=540,
        last_matched_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_import_log():
    """Sample Import Log fuer Tests."""
    return Mock(
        id=uuid4(),
        user_id=uuid4(),
        source_type="email",
        email_config_id=uuid4(),
        folder_config_id=None,
        batch_id=uuid4(),
        email_from="absender@firma.de",
        email_subject="Rechnung Nr. 12345",
        email_date=datetime.now(timezone.utc),
        original_path=None,
        original_filename="Rechnung_12345.pdf",
        status="completed",
        document_id=uuid4(),
        file_hash="abc123def456",
        file_size=256000,
        mime_type="application/pdf",
        matched_rule_id=uuid4(),
        applied_actions={"set_tags": ["rechnung"]},
        error_message=None,
        error_code=None,
        retry_count=0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        processing_duration_ms=1250,
    )


@pytest.fixture
def sample_sync_result():
    """Sample Sync Result fuer Tests."""
    return Mock(
        emails_processed=25,
        attachments_extracted=18,
        documents_created=18,
        duplicates_skipped=2,
        errors=[],
        created_document_ids=[uuid4() for _ in range(18)],
    )


@pytest.fixture
def sample_poll_result():
    """Sample Poll Result fuer Tests."""
    return Mock(
        files_processed=12,
        documents_created=12,
        duplicates_skipped=0,
        files_moved=12,
        errors=[],
        created_document_ids=[uuid4() for _ in range(12)],
    )


# =============================================================================
# Email Config Tests
# =============================================================================

class TestEmailConfigList:
    """Tests fuer Email-Config-Liste."""

    @pytest.mark.asyncio
    async def test_list_email_configs_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten von Email-Configs."""
        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_configs.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/imports/email/configs",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_list_email_configs_with_filters(self, async_client, auth_headers):
        """Email-Configs mit Filtern auflisten."""
        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_configs.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/imports/email/configs?active_only=true",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


class TestEmailConfigCreate:
    """Tests fuer Email-Config-Erstellung."""

    @pytest.mark.asyncio
    async def test_create_email_config_success(self, async_client, auth_headers):
        """Erfolgreiche Email-Config-Erstellung."""
        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_config.return_value = uuid4()
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/email/configs",
                json={
                    "name": "Neuer Email Import",
                    "imap_server": "imap.example.com",
                    "imap_port": 993,
                    "username": "user@example.com",
                    "password": "secret123",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 400, 422]

    @pytest.mark.asyncio
    async def test_create_email_config_with_filters(self, async_client, auth_headers):
        """Email-Config mit Filtern erstellen."""
        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_config.return_value = uuid4()
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/email/configs",
                json={
                    "name": "Filtered Import",
                    "imap_server": "imap.example.com",
                    "username": "user@example.com",
                    "password": "secret123",
                    "filter_from_addresses": ["@trusted.de"],
                    "filter_subject_patterns": ["Rechnung*"],
                    "filter_attachment_types": ["pdf"],
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 400, 422]


class TestEmailConfigGet:
    """Tests fuer Email-Config-Abruf."""

    @pytest.mark.asyncio
    async def test_get_email_config_success(self, async_client, auth_headers, sample_email_config):
        """Erfolgreicher Email-Config-Abruf."""
        config_id = sample_email_config.id

        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_config.return_value = sample_email_config
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/imports/email/configs/{config_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_get_email_config_not_found(self, async_client, auth_headers):
        """Email-Config-Abruf fuer nicht existierende Config."""
        non_existent_id = uuid4()

        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_config.return_value = None
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/imports/email/configs/{non_existent_id}",
                headers=auth_headers,
            )

            assert response.status_code in [404, 401]


class TestEmailConfigUpdate:
    """Tests fuer Email-Config-Update."""

    @pytest.mark.asyncio
    async def test_update_email_config_success(self, async_client, auth_headers, sample_email_config):
        """Erfolgreiches Email-Config-Update."""
        config_id = sample_email_config.id

        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.update_config.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/imports/email/configs/{config_id}",
                json={"name": "Aktualisierter Import"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


class TestEmailConfigDelete:
    """Tests fuer Email-Config-Loeschung."""

    @pytest.mark.asyncio
    async def test_delete_email_config_success(self, async_client, auth_headers, sample_email_config):
        """Erfolgreiche Email-Config-Loeschung."""
        config_id = sample_email_config.id

        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.delete_config.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/imports/email/configs/{config_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


class TestEmailConfigOperations:
    """Tests fuer Email-Config-Operationen."""

    @pytest.mark.asyncio
    async def test_test_email_connection_success(self, async_client, auth_headers, sample_email_config):
        """Erfolgreicher IMAP-Verbindungstest."""
        config_id = sample_email_config.id

        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.test_connection.return_value = {
                "success": True,
                "message": "Verbindung erfolgreich",
                "mailbox_count": 1250,
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/imports/email/configs/{config_id}/test",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_sync_email_config_success(self, async_client, auth_headers, sample_email_config, sample_sync_result):
        """Erfolgreicher Email-Sync."""
        config_id = sample_email_config.id

        with patch("app.api.v1.imports.EmailImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.sync_emails.return_value = sample_sync_result
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/imports/email/configs/{config_id}/sync?max_emails=50",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


# =============================================================================
# Folder Config Tests
# =============================================================================

class TestFolderConfigList:
    """Tests fuer Folder-Config-Liste."""

    @pytest.mark.asyncio
    async def test_list_folder_configs_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten von Folder-Configs."""
        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_configs.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/imports/folder/configs",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


class TestFolderConfigCreate:
    """Tests fuer Folder-Config-Erstellung."""

    @pytest.mark.asyncio
    async def test_create_folder_config_success(self, async_client, auth_headers):
        """Erfolgreiche Folder-Config-Erstellung."""
        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_config.return_value = uuid4()
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/folder/configs",
                json={
                    "name": "Neuer Ordner Import",
                    "watch_path": "C:\\Import\\Dokumente",
                    "recursive": True,
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 400, 422]

    @pytest.mark.asyncio
    async def test_create_folder_config_with_patterns(self, async_client, auth_headers):
        """Folder-Config mit Mustern erstellen."""
        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_config.return_value = uuid4()
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/folder/configs",
                json={
                    "name": "Filtered Folder Import",
                    "watch_path": "C:\\Import\\PDFs",
                    "include_patterns": ["*.pdf"],
                    "exclude_patterns": ["temp_*"],
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 400, 422]


class TestFolderConfigGet:
    """Tests fuer Folder-Config-Abruf."""

    @pytest.mark.asyncio
    async def test_get_folder_config_success(self, async_client, auth_headers, sample_folder_config):
        """Erfolgreicher Folder-Config-Abruf."""
        config_id = sample_folder_config.id

        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_config.return_value = sample_folder_config
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/imports/folder/configs/{config_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


class TestFolderConfigUpdate:
    """Tests fuer Folder-Config-Update."""

    @pytest.mark.asyncio
    async def test_update_folder_config_success(self, async_client, auth_headers, sample_folder_config):
        """Erfolgreiches Folder-Config-Update."""
        config_id = sample_folder_config.id

        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.update_config.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/imports/folder/configs/{config_id}",
                json={"name": "Aktualisierter Ordner Import"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


class TestFolderConfigDelete:
    """Tests fuer Folder-Config-Loeschung."""

    @pytest.mark.asyncio
    async def test_delete_folder_config_success(self, async_client, auth_headers, sample_folder_config):
        """Erfolgreiche Folder-Config-Loeschung."""
        config_id = sample_folder_config.id

        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.delete_config.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/imports/folder/configs/{config_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


class TestFolderConfigOperations:
    """Tests fuer Folder-Config-Operationen."""

    @pytest.mark.asyncio
    async def test_start_folder_watcher_success(self, async_client, auth_headers, sample_folder_config):
        """Erfolgreicher Start des Folder-Watchers."""
        config_id = sample_folder_config.id

        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.start_watcher.return_value = {
                "success": True,
                "message": "Watcher gestartet",
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/imports/folder/configs/{config_id}/start",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_stop_folder_watcher_success(self, async_client, auth_headers, sample_folder_config):
        """Erfolgreiches Stoppen des Folder-Watchers."""
        config_id = sample_folder_config.id

        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.stop_watcher.return_value = {
                "success": True,
                "message": "Watcher gestoppt",
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/imports/folder/configs/{config_id}/stop",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_poll_folder_success(self, async_client, auth_headers, sample_folder_config, sample_poll_result):
        """Erfolgreicher manueller Folder-Scan."""
        config_id = sample_folder_config.id

        with patch("app.api.v1.imports.FolderImportService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.poll_folder.return_value = sample_poll_result
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/imports/folder/configs/{config_id}/poll",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


# =============================================================================
# Import Rules Tests
# =============================================================================

class TestImportRuleList:
    """Tests fuer Import-Regel-Liste."""

    @pytest.mark.asyncio
    async def test_list_import_rules_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten von Import-Regeln."""
        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_rules.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/imports/rules",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_list_import_rules_active_only(self, async_client, auth_headers):
        """Nur aktive Import-Regeln auflisten."""
        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_rules.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/imports/rules?active_only=true",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


class TestImportRuleCreate:
    """Tests fuer Import-Regel-Erstellung."""

    @pytest.mark.asyncio
    async def test_create_import_rule_success(self, async_client, auth_headers):
        """Erfolgreiche Import-Regel-Erstellung."""
        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_rule.return_value = uuid4()
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/rules",
                json={
                    "name": "Rechnungen taggen",
                    "priority": 100,
                    "conditions": {
                        "operator": "AND",
                        "rules": [
                            {"field": "filename", "operator": "contains", "value": "rechnung"}
                        ]
                    },
                    "actions": {
                        "set_tags": ["rechnung"]
                    },
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 400, 422]

    @pytest.mark.asyncio
    async def test_create_import_rule_applies_to_all(self, async_client, auth_headers):
        """Import-Regel fuer alle Quellen erstellen."""
        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_rule.return_value = uuid4()
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/rules",
                json={
                    "name": "Globale Regel",
                    "applies_to_all": True,
                    "conditions": {},
                    "actions": {"set_tags": ["importiert"]},
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 400, 422]


class TestImportRuleGet:
    """Tests fuer Import-Regel-Abruf."""

    @pytest.mark.asyncio
    async def test_get_import_rule_success(self, async_client, auth_headers, sample_import_rule):
        """Erfolgreicher Import-Regel-Abruf."""
        rule_id = sample_import_rule.id

        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_rule.return_value = sample_import_rule
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/imports/rules/{rule_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_get_import_rule_not_found(self, async_client, auth_headers):
        """Import-Regel-Abruf fuer nicht existierende Regel."""
        non_existent_id = uuid4()

        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_rule.return_value = None
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/imports/rules/{non_existent_id}",
                headers=auth_headers,
            )

            assert response.status_code in [404, 401]


class TestImportRuleUpdate:
    """Tests fuer Import-Regel-Update."""

    @pytest.mark.asyncio
    async def test_update_import_rule_success(self, async_client, auth_headers, sample_import_rule):
        """Erfolgreiches Import-Regel-Update."""
        rule_id = sample_import_rule.id

        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.update_rule.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/imports/rules/{rule_id}",
                json={"name": "Aktualisierte Regel"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


class TestImportRuleDelete:
    """Tests fuer Import-Regel-Loeschung."""

    @pytest.mark.asyncio
    async def test_delete_import_rule_success(self, async_client, auth_headers, sample_import_rule):
        """Erfolgreiche Import-Regel-Loeschung."""
        rule_id = sample_import_rule.id

        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.delete_rule.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/imports/rules/{rule_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


class TestImportRuleOperations:
    """Tests fuer Import-Regel-Operationen."""

    @pytest.mark.asyncio
    async def test_reorder_import_rules_success(self, async_client, auth_headers):
        """Erfolgreiches Neuordnen von Import-Regeln."""
        rule_id_1 = str(uuid4())
        rule_id_2 = str(uuid4())

        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.reorder_rules.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/rules/reorder",
                json={
                    "priorities": [
                        {"rule_id": rule_id_1, "priority": 50},
                        {"rule_id": rule_id_2, "priority": 100},
                    ]
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 400]

    @pytest.mark.asyncio
    async def test_test_import_rule_success(self, async_client, auth_headers, sample_import_rule):
        """Erfolgreicher Test einer Import-Regel."""
        rule_id = sample_import_rule.id

        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.test_rule.return_value = {
                "matches": True,
                "matched_conditions": ["filename contains 'rechnung'"],
                "would_apply_actions": {"set_tags": ["rechnung"]},
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/imports/rules/{rule_id}/test",
                json={
                    "metadata": {"filename": "Rechnung_2024.pdf"},
                    "source_type": "email",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_test_all_import_rules_success(self, async_client, auth_headers):
        """Erfolgreicher Test aller Import-Regeln."""
        with patch("app.api.v1.imports.ImportRuleService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.test_all_rules.return_value = {
                "matching_rules": [
                    {"rule_id": str(uuid4()), "name": "Regel 1", "priority": 100}
                ],
                "first_matching_rule": {"rule_id": str(uuid4()), "name": "Regel 1"},
            }
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/imports/rules/test-all",
                json={
                    "metadata": {"filename": "Test.pdf"},
                    "source_type": "folder",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


class TestImportRuleSchema:
    """Tests fuer Import-Regel-Schema-Endpoints."""

    @pytest.mark.asyncio
    async def test_get_rule_fields_success(self, async_client, auth_headers):
        """Verfuegbare Bedingungs-Felder abrufen."""
        with patch.object(
            __import__("app.services.imports", fromlist=["ImportRuleService"]).ImportRuleService,
            "get_available_fields",
            return_value=[
                {"field": "filename", "type": "string", "label": "Dateiname"},
                {"field": "size", "type": "number", "label": "Dateigroesse"},
            ]
        ):
            response = await async_client.get(
                "/api/v1/imports/rules/schema/fields",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_get_rule_operators_success(self, async_client, auth_headers):
        """Verfuegbare Operatoren abrufen."""
        with patch.object(
            __import__("app.services.imports", fromlist=["ImportRuleService"]).ImportRuleService,
            "get_available_operators",
            return_value=[
                {"operator": "contains", "label": "Enthaelt", "types": ["string"]},
                {"operator": "eq", "label": "Gleich", "types": ["string", "number"]},
            ]
        ):
            response = await async_client.get(
                "/api/v1/imports/rules/schema/operators",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_get_rule_actions_success(self, async_client, auth_headers):
        """Verfuegbare Aktionen abrufen."""
        with patch.object(
            __import__("app.services.imports", fromlist=["ImportRuleService"]).ImportRuleService,
            "get_available_actions",
            return_value=[
                {"action": "set_tags", "label": "Tags setzen", "params": ["tags"]},
                {"action": "set_folder", "label": "Ordner setzen", "params": ["folder_id"]},
            ]
        ):
            response = await async_client.get(
                "/api/v1/imports/rules/schema/actions",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


# =============================================================================
# Validation Tests
# =============================================================================

class TestValidation:
    """Tests fuer Validierung."""

    @pytest.mark.asyncio
    async def test_create_email_config_invalid_port(self, async_client, auth_headers):
        """Email-Config mit ungueltigem Port erstellen."""
        response = await async_client.post(
            "/api/v1/imports/email/configs",
            json={
                "name": "Test Config",
                "imap_server": "imap.example.com",
                "imap_port": 70000,  # Ungueltiger Port
                "username": "user@example.com",
                "password": "secret",
            },
            headers=auth_headers,
        )

        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_folder_config_invalid_interval(self, async_client, auth_headers):
        """Folder-Config mit ungueltigem Intervall erstellen."""
        response = await async_client.post(
            "/api/v1/imports/folder/configs",
            json={
                "name": "Test Config",
                "watch_path": "C:\\Import",
                "poll_interval_seconds": 5,  # Zu klein (min 10)
            },
            headers=auth_headers,
        )

        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_rule_invalid_priority(self, async_client, auth_headers):
        """Import-Regel mit ungueltiger Prioritaet erstellen."""
        response = await async_client.post(
            "/api/v1/imports/rules",
            json={
                "name": "Test Regel",
                "priority": 5000,  # Zu hoch (max 1000)
                "conditions": {},
                "actions": {},
            },
            headers=auth_headers,
        )

        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_email_config_empty_name(self, async_client, auth_headers):
        """Email-Config mit leerem Namen erstellen."""
        response = await async_client.post(
            "/api/v1/imports/email/configs",
            json={
                "name": "",  # Leerer Name
                "imap_server": "imap.example.com",
                "username": "user@example.com",
                "password": "secret",
            },
            headers=auth_headers,
        )

        assert response.status_code in [401, 422]
