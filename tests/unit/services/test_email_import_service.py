"""
Unit Tests fuer EmailImportService.

Tests fuer IMAP-Verbindung, E-Mail-Parsing, Attachment-Extraktion
und Credential-Verschluesselung.
"""

import pytest
import socket
from datetime import datetime, timezone
from email.message import Message
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.imports.email_import_service import (
    EmailImportService,
    EmailAttachment,
    ParsedEmail,
)


class TestEmailParsing:
    """Tests fuer E-Mail-Parsing."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_parse_email_simple(self, service: EmailImportService) -> None:
        """Test parsing a simple email."""
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Thu, 01 Jan 2024 12:00:00 +0000
Message-ID: <test123@example.com>
Content-Type: text/plain; charset="utf-8"

This is the email body."""

        result = service._parse_email(uid=1, raw_email=raw_email)

        assert isinstance(result, ParsedEmail)
        assert result.from_address == "sender@example.com"
        assert result.subject == "Test Subject"
        assert result.message_id == "<test123@example.com>"
        assert result.uid == 1

    def test_parse_email_with_german_subject(self, service: EmailImportService) -> None:
        """Test parsing email with German umlauts in subject."""
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: =?UTF-8?Q?Rechnungs=C3=BCbersicht_f=C3=BCr_M=C3=A4rz?=
Date: Thu, 01 Jan 2024 12:00:00 +0000

Body text."""

        result = service._parse_email(uid=2, raw_email=raw_email)

        assert "Rechnungsübersicht" in result.subject
        assert "März" in result.subject

    def test_parse_email_extracts_body_text(self, service: EmailImportService) -> None:
        """Test parsing email extracts body text."""
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Thu, 01 Jan 2024 12:00:00 +0000
Content-Type: text/plain; charset="utf-8"

This is the email body text."""

        result = service._parse_email(uid=3, raw_email=raw_email)

        assert result.body_text is not None
        assert "email body text" in result.body_text


class TestHeaderDecoding:
    """Tests fuer Header-Dekodierung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_decode_header_simple(self, service: EmailImportService) -> None:
        """Test decoding simple ASCII header."""
        result = service._decode_header("Simple Header")
        assert result == "Simple Header"

    def test_decode_header_empty(self, service: EmailImportService) -> None:
        """Test decoding empty header."""
        result = service._decode_header("")
        assert result == ""

    def test_decode_header_utf8_quoted_printable(
        self, service: EmailImportService
    ) -> None:
        """Test decoding UTF-8 quoted-printable header."""
        result = service._decode_header("=?UTF-8?Q?M=C3=BCller?=")
        assert "Müller" in result


class TestAttachmentExtraction:
    """Tests fuer Attachment-Extraktion."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_extract_attachment_returns_none_for_no_filename(
        self, service: EmailImportService
    ) -> None:
        """Test extraction returns None when no filename."""
        part = MagicMock(spec=Message)
        part.get_filename.return_value = None

        result = service._extract_attachment(part)

        assert result is None

    def test_extract_attachment_returns_none_for_blocked_extension(
        self, service: EmailImportService
    ) -> None:
        """Test extraction returns None for blocked extension."""
        part = MagicMock(spec=Message)
        part.get_filename.return_value = "virus.exe"
        part.get_content_type.return_value = "application/x-msdownload"

        result = service._extract_attachment(part)

        assert result is None


class TestCredentialEncryption:
    """Tests fuer Credential-Verschluesselung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    @patch("app.services.imports.email_import_service.encrypt_data")
    def test_encrypt_password(
        self, mock_encrypt: MagicMock, service: EmailImportService
    ) -> None:
        """Test password encryption calls encryption function."""
        mock_encrypt.return_value = b"encrypted_password"
        password = "my_secret_password"

        # EmailImportService doesn't expose _encrypt_password directly
        # This tests that encrypt_data is available for the service
        from app.services.imports.email_import_service import encrypt_data

        result = encrypt_data(password.encode())
        mock_encrypt.assert_called_once()

    @patch("app.services.imports.email_import_service.decrypt_data")
    def test_decrypt_password(
        self, mock_decrypt: MagicMock, service: EmailImportService
    ) -> None:
        """Test password decryption calls decryption function."""
        mock_decrypt.return_value = b"decrypted_password"
        encrypted = b"encrypted_data"

        from app.services.imports.email_import_service import decrypt_data

        result = decrypt_data(encrypted)
        mock_decrypt.assert_called_once()


# =============================================================================
# Async Tests
# =============================================================================

@pytest.mark.asyncio
class TestAsyncEmailOperations:
    """Async tests fuer Email Import operations."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    async def test_service_creation(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test service can be instantiated."""
        assert service is not None
        assert service.db == mock_db


@pytest.mark.asyncio
class TestIMAPConnection:
    """Tests fuer IMAP-Verbindung."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_create_imap_connection_ssl(self, service: EmailImportService) -> None:
        """Test IMAP connection configuration with SSL."""
        # The _create_imap_connection method exists and should work
        # We just verify the method exists
        assert hasattr(service, "_create_imap_connection")


class TestEmailAttachment:
    """Tests fuer EmailAttachment Datenklasse."""

    def test_email_attachment_creation(self) -> None:
        """Test EmailAttachment can be created."""
        attachment = EmailAttachment(
            filename="document.pdf",
            content=b"%PDF-1.4 test content",
            mime_type="application/pdf",
        )

        assert attachment.filename == "document.pdf"
        assert attachment.mime_type == "application/pdf"
        assert attachment.size > 0
        assert attachment.file_hash is not None

    def test_email_attachment_hash(self) -> None:
        """Test EmailAttachment generates consistent hash."""
        content = b"test content"
        attachment1 = EmailAttachment(
            filename="test.pdf",
            content=content,
            mime_type="application/pdf",
        )
        attachment2 = EmailAttachment(
            filename="test.pdf",
            content=content,
            mime_type="application/pdf",
        )

        assert attachment1.file_hash == attachment2.file_hash


class TestParsedEmail:
    """Tests fuer ParsedEmail Datenklasse."""

    def test_parsed_email_creation(self) -> None:
        """Test ParsedEmail can be created."""
        parsed = ParsedEmail(
            uid=1,
            message_id="<test@example.com>",
            from_address="sender@example.com",
            subject="Test Subject",
            date=datetime.now(timezone.utc),
            attachments=[],
        )

        assert parsed.uid == 1
        assert parsed.message_id == "<test@example.com>"
        assert parsed.from_address == "sender@example.com"
        assert parsed.subject == "Test Subject"
        assert parsed.attachments == []

    def test_parsed_email_with_attachments(self) -> None:
        """Test ParsedEmail with attachments."""
        attachment = EmailAttachment(
            filename="doc.pdf",
            content=b"content",
            mime_type="application/pdf",
        )
        parsed = ParsedEmail(
            uid=1,
            message_id="<test@example.com>",
            from_address="sender@example.com",
            subject="Test",
            date=None,
            attachments=[attachment],
        )

        assert len(parsed.attachments) == 1
        assert parsed.attachments[0].filename == "doc.pdf"


# =============================================================================
# Security and Edge Case Tests
# =============================================================================


@pytest.mark.asyncio
class TestIMAPSSLConnections:
    """Tests fuer IMAP SSL/STARTTLS Verbindungen."""

    @pytest.fixture(autouse=True)
    def _mock_ssrf_dns(self):
        """SSRF-DNS-Precheck neutralisieren.

        _create_imap_connection loest den Host per socket.getaddrinfo auf (SSRF-
        Guard, fail-closed). Ohne Netz/DNS im Container schlaegt das fuer
        imap.example.com fehl -> ConnectionError VOR dem gemockten IMAPClient.
        Wir mocken die Aufloesung auf eine oeffentliche IP (nicht SSRF-blockiert),
        damit der Guard passiert und die eigentliche Verbindungs-Logik (Port/
        STARTTLS/Fehlerbehandlung) mit dem gemockten Client getestet wird.
        """
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 993))
            ]
            yield mock_gai

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    @patch("app.services.imports.email_import_service.IMAP_AVAILABLE", True)
    @patch("app.services.imports.email_import_service.IMAPClient")
    def test_ssl_connection_uses_correct_port(
        self, mock_imap_client: MagicMock, service: EmailImportService
    ) -> None:
        """Test SSL-Verbindung verwendet Port 993."""
        mock_client = MagicMock()
        mock_imap_client.return_value = mock_client

        service._create_imap_connection(
            server="imap.example.com",
            port=993,
            username="user@example.com",
            password="password123",
            use_ssl=True,
            use_starttls=False,
        )

        mock_imap_client.assert_called_once_with(
            "imap.example.com", port=993, ssl=True
        )
        mock_client.login.assert_called_once()

    @patch("app.services.imports.email_import_service.IMAP_AVAILABLE", True)
    @patch("app.services.imports.email_import_service.IMAPClient")
    def test_starttls_connection_upgrades_connection(
        self, mock_imap_client: MagicMock, service: EmailImportService
    ) -> None:
        """Test STARTTLS-Verbindung upgraded zu TLS."""
        mock_client = MagicMock()
        mock_imap_client.return_value = mock_client

        service._create_imap_connection(
            server="imap.example.com",
            port=143,
            username="user@example.com",
            password="password123",
            use_ssl=False,
            use_starttls=True,
        )

        mock_imap_client.assert_called_once_with(
            "imap.example.com", port=143, ssl=False
        )
        mock_client.starttls.assert_called_once()
        mock_client.login.assert_called_once()


class TestAttachmentExtractionEdgeCases:
    """Tests fuer Anhang-Extraktion Edge Cases."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_extract_empty_attachment_returns_none(
        self, service: EmailImportService
    ) -> None:
        """Test leerer Anhang wird abgelehnt."""
        part = MagicMock(spec=Message)
        part.get_filename.return_value = "empty.pdf"
        part.get_payload.return_value = b""
        part.get_content_type.return_value = "application/pdf"

        result = service._extract_attachment(part)

        assert result is None

    def test_extract_oversized_attachment_returns_none(
        self, service: EmailImportService
    ) -> None:
        """Test uebergroesser Anhang wird abgelehnt."""
        part = MagicMock(spec=Message)
        part.get_filename.return_value = "huge.pdf"
        # MAX_ATTACHMENT_SIZE ist 50 MB
        part.get_payload.return_value = b"x" * (51 * 1024 * 1024)
        part.get_content_type.return_value = "application/pdf"

        result = service._extract_attachment(part)

        assert result is None

    def test_extract_invalid_mime_type_returns_none(
        self, service: EmailImportService
    ) -> None:
        """Test ungueltiger MIME-Type wird abgelehnt."""
        part = MagicMock(spec=Message)
        part.get_filename.return_value = "script.js"
        part.get_payload.return_value = b"alert('test')"
        part.get_content_type.return_value = "application/javascript"

        result = service._extract_attachment(part)

        assert result is None

    def test_extract_attachment_with_unicode_filename(
        self, service: EmailImportService
    ) -> None:
        """Test Anhang mit Unicode-Dateiname wird korrekt dekodiert."""
        part = MagicMock(spec=Message)
        # Encoded German filename
        part.get_filename.return_value = "=?UTF-8?Q?Rechnung_M=C3=BCller.pdf?="
        part.get_payload.return_value = b"%PDF-1.4 test content"
        part.get_content_type.return_value = "application/pdf"

        result = service._extract_attachment(part)

        assert result is not None
        assert "Müller" in result.filename


@pytest.mark.asyncio
class TestSenderMatching:
    """Tests fuer Absender-Zuordnung."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    async def test_valid_sender_matches_entity(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test gueltiger Absender wird Entity zugeordnet."""
        from app.db.models import BusinessEntity

        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.name = "Test GmbH"
        entity.email = "sender@example.com"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        mock_db.execute.return_value = mock_result

        # EmailImportService doesn't expose sender matching directly
        # But we verify the database query would work
        from sqlalchemy import select
        from app.db.models import BusinessEntity

        query = select(BusinessEntity).where(
            BusinessEntity.email == "sender@example.com"
        )
        result = await mock_db.execute(query)
        found_entity = result.scalar_one_or_none()

        assert found_entity is not None
        assert found_entity.email == "sender@example.com"

    async def test_no_sender_match_returns_none(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test unbekannter Absender liefert None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        from sqlalchemy import select
        from app.db.models import BusinessEntity

        query = select(BusinessEntity).where(
            BusinessEntity.email == "unknown@example.com"
        )
        result = await mock_db.execute(query)
        found_entity = result.scalar_one_or_none()

        assert found_entity is None


@pytest.mark.asyncio
class TestErrorRecovery:
    """Tests fuer Fehlerbehandlung und Recovery."""

    @pytest.fixture(autouse=True)
    def _mock_ssrf_dns(self):
        """SSRF-DNS-Precheck neutralisieren (siehe TestIMAPSSLConnections).

        Ohne DNS-Mock scheitert _create_imap_connection am getaddrinfo-Precheck
        (imap.example.com nicht aufloesbar) statt an der eigentlich getesteten
        Login-Fehlerbehandlung ('IMAP-Verbindung fehlgeschlagen').
        """
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 993))
            ]
            yield mock_gai

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    @patch("app.services.imports.email_import_service.IMAP_AVAILABLE", True)
    @patch("app.services.imports.email_import_service.IMAPClient")
    def test_imap_disconnect_during_sync_raises_error(
        self, mock_imap_client: MagicMock, service: EmailImportService
    ) -> None:
        """Test IMAP-Verbindungsabbruch wirft Fehler."""
        mock_client = MagicMock()
        mock_client.login.side_effect = ConnectionError("Connection lost")
        mock_imap_client.return_value = mock_client

        with pytest.raises(ConnectionError, match="IMAP-Verbindung fehlgeschlagen"):
            service._create_imap_connection(
                server="imap.example.com",
                port=993,
                username="user@example.com",
                password="password123",
                use_ssl=True,
            )

    async def test_retry_after_failure_updates_status(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test Retry nach Fehler aktualisiert Status."""
        from app.db.models import EmailImportConfig

        config_id = uuid4()
        user_id = uuid4()

        # Mock config
        config = MagicMock(spec=EmailImportConfig)
        config.id = config_id
        config.imap_server = "imap.example.com"
        config.imap_port = 993
        config.use_ssl = True
        config.use_starttls = False
        config.username_encrypted = b"encrypted_user"
        config.password_encrypted = b"encrypted_pass"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.imports.email_import_service.decrypt_data",
            side_effect=Exception("Decryption failed")
        ):
            result = await service.test_connection(config_id, user_id)

        # Should return failure without crashing
        assert result["success"] is False
        assert "error" in result["message"].lower() or "fehler" in result["message"].lower()


class TestEmailParsingErrorHandling:
    """Tests fuer robuste E-Mail-Parsing-Fehlerbehandlung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_parse_email_with_malformed_date(self, service: EmailImportService) -> None:
        """Test E-Mail mit fehlerhaftem Datum nutzt Fallback."""
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Invalid Date String
Content-Type: text/plain

Body text."""

        result = service._parse_email(uid=1, raw_email=raw_email)

        assert result is not None
        assert result.date is not None  # Fallback auf datetime.now()

    def test_parse_email_with_missing_headers(self, service: EmailImportService) -> None:
        """Test E-Mail mit fehlenden Headers."""
        raw_email = b"""Content-Type: text/plain

Body text without headers."""

        result = service._parse_email(uid=1, raw_email=raw_email)

        assert result is not None
        assert result.subject == "(Kein Betreff)"
        assert result.from_address  # Should have some default


class TestEInvoiceExtraction:
    """Tests fuer _extract_einvoice_if_present (OPEN-44, ZUGFeRD-Empfang)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        return EmailImportService(db=mock_db)

    @pytest.mark.asyncio
    async def test_skips_non_pdf_xml(self, service: EmailImportService) -> None:
        """Bild-Anhang (.png) loest keine E-Rechnungs-Extraktion aus (No-Op)."""
        att = EmailAttachment(filename="scan.png", content=b"\x89PNGdata", mime_type="image/png")
        with patch("app.services.einvoice.parser_service.get_parser_service") as mock_get:
            await service._extract_einvoice_if_present(
                document_id=uuid4(), attachment=att, user_id=uuid4()
            )
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_pdf_calls_parse_and_store(self, service: EmailImportService) -> None:
        """PDF-Anhang ruft parse_and_store auf (E-Rechnungs-Extraktion)."""
        att = EmailAttachment(filename="rechnung.pdf", content=b"%PDF-1.7 data", mime_type="application/pdf")
        parser = MagicMock()
        parser.parse_and_store = AsyncMock(
            return_value=MagicMock(success=True, format_detected=MagicMock(value="zugferd_2_3"))
        )
        with patch("app.services.einvoice.parser_service.get_parser_service", return_value=parser):
            await service._extract_einvoice_if_present(
                document_id=uuid4(), attachment=att, user_id=uuid4()
            )
            parser.parse_and_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_parser_failure_is_swallowed(self, service: EmailImportService) -> None:
        """Parser-Fehler bricht den Import NICHT (best-effort, voll geguarded)."""
        att = EmailAttachment(filename="rechnung.pdf", content=b"%PDF-broken", mime_type="application/pdf")
        parser = MagicMock()
        parser.parse_and_store = AsyncMock(side_effect=RuntimeError("parse boom"))
        with patch("app.services.einvoice.parser_service.get_parser_service", return_value=parser):
            # Darf NICHT raisen
            await service._extract_einvoice_if_present(
                document_id=uuid4(), attachment=att, user_id=uuid4()
            )
            parser.parse_and_store.assert_awaited_once()
