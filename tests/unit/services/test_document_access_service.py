"""
Unit Tests fuer Document Access Service - GoBD-konforme Zugriffsprotokollierung.

Tests:
- Dokumentzugriff-Logging (VIEW, DOWNLOAD, EXPORT)
- Audit-Trail-Abfragen
- Benutzer-Zugriffshistorie
- Firmen-Zugriffsstatistiken
- Sequenzluecken-Erkennung
- Audit-Trail-Integritaetspruefung
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.document_access_service import DocumentAccessService, document_access_service
from app.db.models import DocumentAccessType, DocumentAccessLog


@pytest.fixture
def access_service():
    """Create DocumentAccessService instance."""
    return DocumentAccessService()


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_access_log():
    """Create mock access log entry."""
    log = MagicMock()
    log.id = uuid4()
    log.document_id = uuid4()
    log.user_id = uuid4()
    log.company_id = uuid4()
    log.access_type = DocumentAccessType.VIEW.value
    log.access_reason = None
    log.ip_address = "192.168.1.100"
    log.user_agent = "Mozilla/5.0"
    log.request_id = "req-123"
    log.success = True
    log.error_message = None
    log.bytes_transferred = None
    log.accessed_at = datetime.now(timezone.utc)
    log.access_metadata = {}
    log.sequence_number = 42
    return log


class TestLogAccess:
    """Tests fuer log_access Methode."""

    @pytest.mark.asyncio
    async def test_log_access_success(self, access_service, mock_db):
        """Dokumentzugriff erfolgreich protokollieren."""
        document_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()

        log_entry = await access_service.log_access(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            access_type=DocumentAccessType.VIEW.value,
            user_id=user_id,
            ip_address="10.0.0.1",
            user_agent="TestBrowser/1.0",
            request_id="test-req-001",
        )

        # Pruefen, dass log_entry erstellt wurde
        assert log_entry is not None
        assert log_entry.document_id == document_id
        assert log_entry.company_id == company_id
        assert log_entry.user_id == user_id
        assert log_entry.access_type == DocumentAccessType.VIEW.value
        assert log_entry.success is True

        # Pruefen, dass DB-Operationen aufgerufen wurden
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_access_failed(self, access_service, mock_db):
        """Fehlgeschlagenen Dokumentzugriff protokollieren."""
        document_id = uuid4()
        company_id = uuid4()

        log_entry = await access_service.log_access(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            access_type=DocumentAccessType.DOWNLOAD.value,
            success=False,
            error_message="Zugriff verweigert",
        )

        assert log_entry.success is False
        assert log_entry.error_message == "Zugriff verweigert"

    @pytest.mark.asyncio
    async def test_log_access_with_metadata(self, access_service, mock_db):
        """Dokumentzugriff mit zusaetzlichen Metadaten protokollieren."""
        document_id = uuid4()
        company_id = uuid4()
        metadata = {"export_format": "PDF", "pages": [1, 2, 3]}

        log_entry = await access_service.log_access(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            access_type=DocumentAccessType.EXPORT.value,
            metadata=metadata,
        )

        assert log_entry.access_metadata == metadata

    @pytest.mark.asyncio
    async def test_log_access_truncates_user_agent(self, access_service, mock_db):
        """User-Agent wird auf 500 Zeichen begrenzt."""
        document_id = uuid4()
        company_id = uuid4()
        long_user_agent = "A" * 1000  # 1000 Zeichen

        log_entry = await access_service.log_access(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            access_type=DocumentAccessType.VIEW.value,
            user_agent=long_user_agent,
        )

        assert len(log_entry.user_agent) == 500


class TestLogView:
    """Tests fuer log_view Shortcut."""

    @pytest.mark.asyncio
    async def test_log_view_shortcut(self, access_service, mock_db):
        """VIEW-Zugriff ueber Shortcut protokollieren."""
        document_id = uuid4()
        company_id = uuid4()

        log_entry = await access_service.log_view(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert log_entry.access_type == DocumentAccessType.VIEW.value


class TestLogDownload:
    """Tests fuer log_download Shortcut."""

    @pytest.mark.asyncio
    async def test_log_download_shortcut(self, access_service, mock_db):
        """DOWNLOAD-Zugriff ueber Shortcut protokollieren."""
        document_id = uuid4()
        company_id = uuid4()

        log_entry = await access_service.log_download(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            bytes_transferred=12345,
        )

        assert log_entry.access_type == DocumentAccessType.DOWNLOAD.value
        assert log_entry.bytes_transferred == 12345


class TestLogExport:
    """Tests fuer log_export Shortcut."""

    @pytest.mark.asyncio
    async def test_log_export_shortcut(self, access_service, mock_db):
        """EXPORT-Zugriff ueber Shortcut protokollieren."""
        document_id = uuid4()
        company_id = uuid4()

        log_entry = await access_service.log_export(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            export_format="PDF",
        )

        assert log_entry.access_type == DocumentAccessType.EXPORT.value
        assert log_entry.access_metadata.get("export_format") == "PDF"


class TestGetDocumentAuditTrail:
    """Tests fuer get_document_audit_trail Methode."""

    @pytest.mark.asyncio
    async def test_get_audit_trail_success(self, access_service, mock_db, mock_access_log):
        """Audit-Trail erfolgreich abrufen."""
        document_id = uuid4()
        company_id = uuid4()

        # Mock Query Results
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 10

        mock_first_last_result = MagicMock()
        mock_first_last_result.one.return_value = (
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 12, 31, tzinfo=timezone.utc),
        )

        mock_logs_result = MagicMock()
        mock_logs_result.scalars.return_value.all.return_value = [mock_access_log]

        mock_users_result = MagicMock()
        mock_users_result.scalars.return_value.all.return_value = []

        mock_gaps_result = MagicMock()
        mock_gaps_result.scalar.return_value = 0

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_first_last_result,
            mock_logs_result,
            mock_users_result,
            mock_gaps_result,
        ]

        result = await access_service.get_document_audit_trail(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert result["total_count"] == 10
        assert result["has_gaps"] is False
        assert result["gap_count"] == 0
        assert len(result["logs"]) == 1

    @pytest.mark.asyncio
    async def test_get_audit_trail_with_date_filter(self, access_service, mock_db, mock_access_log):
        """Audit-Trail mit Datumsfilter abrufen."""
        document_id = uuid4()
        company_id = uuid4()
        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 6, 30, tzinfo=timezone.utc)

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_first_last_result = MagicMock()
        mock_first_last_result.one.return_value = (start_date, end_date)

        mock_logs_result = MagicMock()
        mock_logs_result.scalars.return_value.all.return_value = []

        mock_gaps_result = MagicMock()
        mock_gaps_result.scalar.return_value = 0

        # Note: When logs are empty, user_ids is empty, so users query is NOT called
        # Only 4 execute calls: count, first/last, logs, gaps
        mock_db.execute.side_effect = [
            mock_count_result,
            mock_first_last_result,
            mock_logs_result,
            mock_gaps_result,
        ]

        result = await access_service.get_document_audit_trail(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
        )

        assert result["total_count"] == 5

    @pytest.mark.asyncio
    async def test_get_audit_trail_with_access_type_filter(self, access_service, mock_db):
        """Audit-Trail mit Zugriffstyp-Filter abrufen."""
        document_id = uuid4()
        company_id = uuid4()

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3

        mock_first_last_result = MagicMock()
        mock_first_last_result.one.return_value = (None, None)

        mock_logs_result = MagicMock()
        mock_logs_result.scalars.return_value.all.return_value = []

        mock_gaps_result = MagicMock()
        mock_gaps_result.scalar.return_value = 0

        # Note: When logs are empty, user_ids is empty, so users query is NOT called
        # Only 4 execute calls: count, first/last, logs, gaps
        mock_db.execute.side_effect = [
            mock_count_result,
            mock_first_last_result,
            mock_logs_result,
            mock_gaps_result,
        ]

        result = await access_service.get_document_audit_trail(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            access_type=DocumentAccessType.DOWNLOAD.value,
        )

        assert result["total_count"] == 3


class TestGetUserAccessHistory:
    """Tests fuer get_user_access_history Methode."""

    @pytest.mark.asyncio
    async def test_get_user_history_success(self, access_service, mock_db, mock_access_log):
        """Benutzer-Zugriffshistorie abrufen."""
        user_id = uuid4()
        company_id = uuid4()

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 50

        mock_logs_result = MagicMock()
        mock_logs_result.scalars.return_value.all.return_value = [mock_access_log]

        mock_stats_result = MagicMock()
        mock_stats_result.all.return_value = [
            (DocumentAccessType.VIEW.value, 30),
            (DocumentAccessType.DOWNLOAD.value, 20),
        ]

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_logs_result,
            mock_stats_result,
        ]

        result = await access_service.get_user_access_history(
            db=mock_db,
            user_id=user_id,
            company_id=company_id,
        )

        assert result["user_id"] == str(user_id)
        assert result["total_count"] == 50
        assert DocumentAccessType.VIEW.value in result["access_stats"]
        assert result["access_stats"][DocumentAccessType.VIEW.value] == 30


class TestGetCompanyAccessStatistics:
    """Tests fuer get_company_access_statistics Methode."""

    @pytest.mark.asyncio
    async def test_get_company_stats_success(self, access_service, mock_db):
        """Firmen-Zugriffsstatistiken abrufen."""
        company_id = uuid4()

        # Mock alle Sub-Queries
        mock_total = MagicMock()
        mock_total.scalar.return_value = 1000

        mock_by_type = MagicMock()
        mock_by_type.all.return_value = [
            (DocumentAccessType.VIEW.value, 600),
            (DocumentAccessType.DOWNLOAD.value, 300),
            (DocumentAccessType.EXPORT.value, 100),
        ]

        mock_docs = MagicMock()
        mock_docs.scalar.return_value = 150

        mock_users = MagicMock()
        mock_users.scalar.return_value = 25

        mock_failed = MagicMock()
        mock_failed.scalar.return_value = 5

        mock_daily = MagicMock()
        mock_daily.all.return_value = [
            ("2025-01-15", 50),
            ("2025-01-16", 45),
        ]

        mock_top_docs = MagicMock()
        mock_top_docs.all.return_value = [
            (uuid4(), 100),
            (uuid4(), 80),
        ]

        mock_top_users = MagicMock()
        mock_top_users.all.return_value = [
            (uuid4(), 200),
            (uuid4(), 150),
        ]

        mock_db.execute.side_effect = [
            mock_total,
            mock_by_type,
            mock_docs,
            mock_users,
            mock_failed,
            mock_daily,
            mock_top_docs,
            mock_top_users,
        ]

        result = await access_service.get_company_access_statistics(
            db=mock_db,
            company_id=company_id,
        )

        assert result["total_accesses"] == 1000
        assert result["by_access_type"][DocumentAccessType.VIEW.value] == 600
        assert result["failed_access_count"] == 5
        assert len(result["by_day"]) == 2
        assert len(result["top_documents"]) == 2
        assert len(result["top_users"]) == 2


class TestSequenceGapDetection:
    """Tests fuer Sequenzluecken-Erkennung (GoBD Vollstaendigkeit)."""

    @pytest.mark.asyncio
    async def test_no_gaps_detected(self, access_service, mock_db):
        """Keine Luecken bei korrekter Sequenz."""
        document_id = uuid4()
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        mock_db.execute.return_value = mock_result

        result = await access_service._check_sequence_gaps_detailed(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert result["has_gaps"] is False
        assert result["gap_count"] == 0

    @pytest.mark.asyncio
    async def test_gaps_detected_with_null_sequences(self, access_service, mock_db):
        """Luecken bei NULL-Sequenznummern erkennen."""
        document_id = uuid4()
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 3  # 3 NULL sequences

        mock_db.execute.return_value = mock_result

        result = await access_service._check_sequence_gaps_detailed(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert result["has_gaps"] is True
        assert result["gap_count"] == 3


class TestVerifyAuditTrailIntegrity:
    """Tests fuer verify_audit_trail_integrity Methode."""

    @pytest.mark.asyncio
    async def test_verify_integrity_success(self, access_service, mock_db):
        """Integritaetspruefung erfolgreich (keine Probleme)."""
        company_id = uuid4()

        # Mock NULL sequences check
        mock_null = MagicMock()
        mock_null.scalar.return_value = 0

        # Mock range check
        mock_range = MagicMock()
        mock_range.one.return_value = (1, 100, 100)  # min, max, count

        mock_db.execute.side_effect = [mock_null, mock_range]

        result = await access_service.verify_audit_trail_integrity(
            db=mock_db,
            company_id=company_id,
        )

        assert result["is_valid"] is True
        assert result["total_records"] == 100
        assert result["expected_sequence"] == 100
        assert len(result["gaps"]) == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_with_null_sequences(self, access_service, mock_db):
        """Integritaetspruefung mit NULL-Sequenznummern."""
        company_id = uuid4()

        mock_null = MagicMock()
        mock_null.scalar.return_value = 5  # 5 NULL sequences

        mock_range = MagicMock()
        mock_range.one.return_value = (1, 100, 95)

        mock_db.execute.side_effect = [mock_null, mock_range]

        result = await access_service.verify_audit_trail_integrity(
            db=mock_db,
            company_id=company_id,
        )

        assert result["is_valid"] is False
        assert len(result["gaps"]) == 1
        assert result["gaps"][0]["type"] == "null_sequence"

    @pytest.mark.asyncio
    async def test_verify_integrity_with_date_filter(self, access_service, mock_db):
        """Integritaetspruefung mit Datumsfilter."""
        company_id = uuid4()
        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 6, 30, tzinfo=timezone.utc)

        mock_null = MagicMock()
        mock_null.scalar.return_value = 0

        mock_range = MagicMock()
        mock_range.one.return_value = (50, 150, 101)

        mock_db.execute.side_effect = [mock_null, mock_range]

        result = await access_service.verify_audit_trail_integrity(
            db=mock_db,
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
        )

        assert result["is_valid"] is True


class TestGoBDCompliance:
    """GoBD-Compliance Tests fuer DocumentAccessService."""

    @pytest.mark.asyncio
    async def test_gobd_nachvollziehbarkeit(self, access_service, mock_db):
        """Nachvollziehbarkeit: Jeder Zugriff wird mit Kontext protokolliert."""
        document_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()

        # Patch DocumentAccessLog to auto-set accessed_at (normally server_default)
        original_class = DocumentAccessLog

        class MockDocumentAccessLog(original_class):
            def __init__(self, **kwargs):
                if "accessed_at" not in kwargs:
                    kwargs["accessed_at"] = datetime.now(timezone.utc)
                # Call object.__init__ since SQLAlchemy model doesn't need parent __init__
                for key, value in kwargs.items():
                    setattr(self, key, value)

        with patch(
            "app.services.document_access_service.DocumentAccessLog",
            MockDocumentAccessLog,
        ):
            log_entry = await access_service.log_access(
                db=mock_db,
                document_id=document_id,
                company_id=company_id,
                user_id=user_id,
                access_type=DocumentAccessType.VIEW.value,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
                request_id="req-gobd-001",
                access_reason="Pruefung durch Steuerberater",
            )

            # GoBD Nachvollziehbarkeit: Wer, Wann, Was, Warum
            assert log_entry.user_id == user_id  # Wer
            assert log_entry.accessed_at is not None  # Wann (auto-set)
            assert log_entry.access_type == DocumentAccessType.VIEW.value  # Was
            assert log_entry.access_reason == "Pruefung durch Steuerberater"  # Warum
            assert log_entry.ip_address == "10.0.0.1"  # Zusaetzlicher Kontext
            assert log_entry.request_id == "req-gobd-001"  # Korrelation

    @pytest.mark.asyncio
    async def test_gobd_unveraenderbarkeit_log_created(self, access_service, mock_db):
        """Unveraenderbarkeit: Logs werden persistiert (DB-Trigger verhindert Aenderung)."""
        document_id = uuid4()
        company_id = uuid4()

        log_entry = await access_service.log_access(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
            access_type=DocumentAccessType.VIEW.value,
        )

        # Log wurde in DB geschrieben
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        # Note: DB-Trigger (in Migration 101) verhindert UPDATE/DELETE

    @pytest.mark.asyncio
    async def test_gobd_vollstaendigkeit_sequence_check(self, access_service, mock_db):
        """Vollstaendigkeit: Sequenznummern-Pruefung erkennt Luecken."""
        document_id = uuid4()
        company_id = uuid4()

        # Simuliere Luecke
        mock_result = MagicMock()
        mock_result.scalar.return_value = 2  # 2 fehlende Sequenzen

        mock_db.execute.return_value = mock_result

        result = await access_service._check_sequence_gaps_detailed(
            db=mock_db,
            document_id=document_id,
            company_id=company_id,
        )

        assert result["has_gaps"] is True  # Luecke erkannt


class TestSingletonInstance:
    """Tests fuer Singleton-Instanz."""

    def test_singleton_instance_exists(self):
        """Singleton-Instanz ist verfuegbar."""
        from app.services.document_access_service import document_access_service

        assert document_access_service is not None
        assert isinstance(document_access_service, DocumentAccessService)

    def test_singleton_is_same_instance(self):
        """Singleton ist immer dieselbe Instanz."""
        from app.services.document_access_service import document_access_service as instance1
        from app.services.document_access_service import document_access_service as instance2

        assert instance1 is instance2
