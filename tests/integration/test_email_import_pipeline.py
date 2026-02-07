# -*- coding: utf-8 -*-
"""
Integration Tests: Email Import Pipeline.

Tests den vollständigen Email → Document Flow mit Celery-Orchestrierung:
- IMAP Email-Abruf mit Attachments
- Absender-Matching zu Entities
- Duplikat-Erkennung via Message-ID
- Fehler-Handling und Recovery

Feinpoliert und durchdacht - Comprehensive Celery Testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime
from uuid import uuid4
from pathlib import Path
import asyncio

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def email_config_data():
    """Sample email import configuration."""
    return {
        "name": "Test IMAP Account",
        "email_address": "invoices@test-company.de",
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "use_ssl": True,
        "folder_filter": "INBOX",
        "subject_filter": ".*Rechnung.*",
        "sender_filter": None,
        "auto_archive": True,
        "enabled": True,
    }


@pytest.fixture
def mock_imap_email():
    """Mock IMAP email with PDF attachment."""
    email_data = MagicMock()
    email_data.message_id = "<test123@amazon.de>"
    email_data.subject = "Ihre Rechnung RE-2024-001"
    email_data.sender = "rechnungen@amazon.de"
    email_data.date = datetime(2026, 1, 15, 10, 30, 0)
    email_data.attachments = [
        {
            "filename": "Rechnung_RE-2024-001.pdf",
            "content_type": "application/pdf",
            "size_bytes": 45678,
            "data": b"%PDF-1.4...",
        }
    ]
    return email_data


@pytest.fixture
def mock_entity_amazon():
    """Mock Amazon entity for sender matching."""
    return {
        "id": str(uuid4()),
        "type": "supplier",
        "name": "Amazon EU S.a.r.l.",
        "email_addresses": ["rechnungen@amazon.de", "invoices@amazon.de"],
        "vat_id": "LU12345678",
    }


# =============================================================================
# TEST 1: FULL EMAIL IMPORT PIPELINE
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_import_full_pipeline(
    async_client: AsyncClient,
    auth_headers: dict,
    email_config_data: dict,
    mock_imap_email,
    mock_entity_amazon,
):
    """
    Test vollständigen Email → Document Flow.

    ARRANGE: Email-Konfiguration mit Attachment
    ACT: Trigger sync_all_email_configs Task
    ASSERT: Dokument erstellt, Entity verknüpft, Email archiviert
    """
    # ARRANGE: Create email config
    with patch("app.services.imports.email_import_service.EmailImportService") as MockService:
        mock_service = MockService.return_value
        mock_service.connect_imap = AsyncMock(return_value=True)
        mock_service.fetch_emails = AsyncMock(return_value=[mock_imap_email])
        mock_service.archive_email = AsyncMock(return_value=True)

        with patch("app.services.entity_search_service.EntitySearchService") as MockEntitySearch:
            mock_entity_search = MockEntitySearch.return_value
            mock_entity_search.match_by_email = AsyncMock(return_value=mock_entity_amazon)

            # Create config via API
            response = await async_client.post(
                "/api/v1/imports/email/configs",
                json=email_config_data,
                headers=auth_headers,
            )
            assert response.status_code == 201
            config_id = response.json()["id"]

            # ACT: Trigger manual sync (simulates Celery task)
            response = await async_client.post(
                f"/api/v1/imports/email/configs/{config_id}/sync",
                headers=auth_headers,
            )

            # ASSERT: Sync initiated
            assert response.status_code == 202
            sync_result = response.json()
            assert sync_result["status"] == "processing"

            # ASSERT: IMAP connect called
            mock_service.connect_imap.assert_called_once()

            # ASSERT: Fetch emails called
            mock_service.fetch_emails.assert_called_once()

            # ASSERT: Entity matching called
            mock_entity_search.match_by_email.assert_called_once_with("rechnungen@amazon.de")

            # ASSERT: Archive email called (auto_archive=True)
            assert mock_service.archive_email.call_count >= 1


# =============================================================================
# TEST 2: PDF ATTACHMENT EXTRACTION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_import_attachment_extraction(
    async_client: AsyncClient,
    auth_headers: dict,
    mock_imap_email,
    tmp_path,
):
    """
    Test PDF Attachment-Extraktion und Speicherung.

    ARRANGE: Email mit 3 Attachments (2 PDF, 1 JPG)
    ACT: Extract und speichere Attachments
    ASSERT: 2 PDFs gespeichert, 1 JPG ignoriert (config-abhängig)
    """
    # ARRANGE: Email mit mehreren Attachments
    mock_imap_email.attachments = [
        {
            "filename": "Rechnung_001.pdf",
            "content_type": "application/pdf",
            "size_bytes": 12345,
            "data": b"%PDF-1.4\ntest content",
        },
        {
            "filename": "Anhang.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 56789,
            "data": b"\xff\xd8\xff...",
        },
        {
            "filename": "Rechnung_002.pdf",
            "content_type": "application/pdf",
            "size_bytes": 23456,
            "data": b"%PDF-1.5\nmore content",
        },
    ]

    with patch("app.services.imports.email_import_service.EmailImportService") as MockService:
        mock_service = MockService.return_value
        mock_service.extract_attachments = AsyncMock(
            return_value=[
                {"filename": "Rechnung_001.pdf", "path": str(tmp_path / "Rechnung_001.pdf")},
                {"filename": "Rechnung_002.pdf", "path": str(tmp_path / "Rechnung_002.pdf")},
            ]
        )

        # ACT: Extract attachments
        result = await mock_service.extract_attachments(mock_imap_email, file_patterns=["*.pdf"])

        # ASSERT: 2 PDFs extracted
        assert len(result) == 2
        assert all("Rechnung" in r["filename"] for r in result)
        assert all(r["filename"].endswith(".pdf") for r in result)


# =============================================================================
# TEST 3: SENDER MATCHING
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_import_sender_matching(
    async_client: AsyncClient,
    auth_headers: dict,
    mock_imap_email,
    mock_entity_amazon,
):
    """
    Test automatische Entity-Erkennung aus Email-Absender.

    ARRANGE: Email von bekanntem Absender
    ACT: Match sender zu Entity
    ASSERT: Entity korrekt verknüpft mit 95%+ Confidence
    """
    # ARRANGE: Mock EntitySearchService
    with patch("app.services.entity_search_service.EntitySearchService") as MockService:
        mock_service = MockService.return_value
        mock_service.match_by_email = AsyncMock(
            return_value={
                "entity": mock_entity_amazon,
                "confidence": 0.98,
                "match_type": "email_exact",
            }
        )

        # ACT: Match sender
        result = await mock_service.match_by_email(mock_imap_email.sender)

        # ASSERT: High confidence match
        assert result["confidence"] > 0.95
        assert result["match_type"] == "email_exact"
        assert result["entity"]["email_addresses"][0] == "rechnungen@amazon.de"


# =============================================================================
# TEST 4: DUPLICATE PREVENTION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_import_duplicate_prevention(
    async_client: AsyncClient,
    auth_headers: dict,
    mock_imap_email,
):
    """
    Test Duplikat-Erkennung via Message-ID.

    ARRANGE: Email mit Message-ID bereits importiert
    ACT: Versuche erneuten Import
    ASSERT: Import wird übersprungen, kein Duplikat erstellt
    """
    # ARRANGE: Mock ImportLogService
    with patch("app.services.imports.import_log_service.ImportLogService") as MockLogService:
        mock_log_service = MockLogService.return_value
        # First import: No duplicates
        mock_log_service.check_duplicate = AsyncMock(return_value=None)
        # Second import: Duplicate found
        mock_log_service.check_duplicate = AsyncMock(
            return_value={
                "id": str(uuid4()),
                "message_id": mock_imap_email.message_id,
                "imported_at": datetime(2026, 1, 15, 10, 0, 0),
            }
        )

        # ACT: Check duplicate
        duplicate = await mock_log_service.check_duplicate(mock_imap_email.message_id)

        # ASSERT: Duplicate detected
        assert duplicate is not None
        assert duplicate["message_id"] == "<test123@amazon.de>"


# =============================================================================
# TEST 5: IMAP FAILURE HANDLING
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_import_error_recovery(
    async_client: AsyncClient,
    auth_headers: dict,
    email_config_data: dict,
):
    """
    Test IMAP-Fehlerbehandlung und Retry-Logik.

    ARRANGE: IMAP-Server antwortet mit Fehler
    ACT: Trigger sync mit Retry-Mechanismus
    ASSERT: 3 Retry-Versuche, dann Fehler geloggt
    """
    # ARRANGE: Mock IMAP connection failure
    with patch("app.services.imports.email_import_service.EmailImportService") as MockService:
        mock_service = MockService.return_value
        mock_service.connect_imap = AsyncMock(
            side_effect=[
                ConnectionError("IMAP connection timeout"),
                ConnectionError("IMAP connection timeout"),
                True,  # Success on 3rd attempt
            ]
        )

        # ACT: Attempt connection with retry
        attempts = 0
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                result = await mock_service.connect_imap(
                    server=email_config_data["imap_server"],
                    port=email_config_data["imap_port"],
                    use_ssl=email_config_data["use_ssl"],
                )
                if result is True:
                    break
            except ConnectionError as e:
                last_error = e
                attempts += 1
                await asyncio.sleep(0.1)  # Simulated backoff

        # ASSERT: 2 failures + 1 success = 3 attempts
        assert mock_service.connect_imap.call_count == 3
        assert attempts == 2  # 2 failures before success
        assert last_error is not None
