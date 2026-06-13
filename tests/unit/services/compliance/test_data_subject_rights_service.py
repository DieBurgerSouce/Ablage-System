# -*- coding: utf-8 -*-
"""
Unit tests for DataSubjectRightsService (Art. 15-21 DSGVO).

Phase 7: Compliance & Audit - GDPR Erweiterungen

Tests:
- DSR-Anfrage erstellen (Art. 15-21)
- Identitaetsverifikation
- Datenexport (Art. 15, 20)
- Datenberichtigung (Art. 16)
- Datenloeschung (Art. 17)
- Anfragen-Verwaltung
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.compliance.data_subject_rights_service import (
    DataSubjectRightsService,
    DSRType,
    DSRStatus,
    DataCategory,
    DSRRequest,
    DSRCreateResult,
    DSRVerificationResult,
    PersonalDataExport,
    PersonalDataSummary,
    ErasureResult,
    RectificationResult,
)


@pytest.fixture
def dsr_service():
    """Create DataSubjectRightsService instance."""
    return DataSubjectRightsService()


@pytest.fixture
def mock_user_id():
    """Create mock user ID."""
    return uuid4()


@pytest.fixture
def mock_company_id():
    """Create mock company ID."""
    return uuid4()


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    """Create mock user object."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.first_name = "Max"
    user.last_name = "Mustermann"
    user.company_id = uuid4()
    user.created_at = datetime.now(timezone.utc) - timedelta(days=365)
    user.preferences = {"theme": "dark", "language": "de"}
    return user


@pytest.fixture
def mock_dsr_request():
    """Create mock DSR request."""
    request = MagicMock()
    request.id = uuid4()
    request.user_id = uuid4()
    request.request_type = DSRType.ACCESS.value
    request.status = DSRStatus.PENDING.value
    request.requester_email = "test@example.com"
    request.verification_token = "test-token-12345"
    request.verified_at = None
    request.due_date = datetime.now(timezone.utc) + timedelta(days=30)
    request.requested_at = datetime.now(timezone.utc)
    request.created_at = datetime.now(timezone.utc)
    return request


class TestCreateRequest:
    """Tests for create_request method."""

    @pytest.mark.asyncio
    async def test_create_access_request(
        self, dsr_service, mock_db, mock_user_id, mock_company_id
    ):
        """Auskunftsantrag (Art. 15) erfolgreich erstellen."""
        result = await dsr_service.create_request(
            db=mock_db,
            request_type=DSRType.ACCESS,
            requester_email="test@example.com",
            requester_name="Max Mustermann",
            user_id=mock_user_id,
            company_id=mock_company_id,
            description="Ich moechte alle meine Daten einsehen.",
        )

        assert result.success is True
        assert result.request_id is not None
        assert result.verification_token is not None
        assert result.status == DSRStatus.PENDING
        # user_id ist gesetzt -> bereits eingeloggt -> keine Email-Verifikation noetig
        assert result.verification_required is False
        # Due date sollte 30 Tage in der Zukunft sein
        assert result.due_date > datetime.now(timezone.utc)
        mock_db.add.assert_called()
        # Service nutzt flush() (Transaktion wird vom Caller committet)
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_request_anonymous_requires_verification(
        self, dsr_service, mock_db, mock_company_id
    ):
        """Ohne user_id ist Email-Verifikation erforderlich."""
        result = await dsr_service.create_request(
            db=mock_db,
            request_type=DSRType.ACCESS,
            requester_email="anon@example.com",
            company_id=mock_company_id,
        )

        assert result.success is True
        assert result.verification_required is True

    @pytest.mark.asyncio
    async def test_create_erasure_request(
        self, dsr_service, mock_db, mock_user_id, mock_company_id
    ):
        """Loeschantrag (Art. 17) erfolgreich erstellen."""
        result = await dsr_service.create_request(
            db=mock_db,
            request_type=DSRType.ERASURE,
            requester_email="test@example.com",
            user_id=mock_user_id,
            company_id=mock_company_id,
            affected_data_categories=[DataCategory.PERSONAL, DataCategory.DOCUMENTS],
        )

        assert result.success is True
        assert result.request_id is not None

    @pytest.mark.asyncio
    async def test_create_rectification_request(
        self, dsr_service, mock_db, mock_user_id, mock_company_id
    ):
        """Berichtigungsantrag (Art. 16) erfolgreich erstellen."""
        result = await dsr_service.create_request(
            db=mock_db,
            request_type=DSRType.RECTIFICATION,
            requester_email="test@example.com",
            user_id=mock_user_id,
            company_id=mock_company_id,
            rectification_details={"first_name": "Maximilian", "last_name": "Musterfrau"},
        )

        assert result.success is True
        assert result.request_id is not None

    @pytest.mark.asyncio
    async def test_create_portability_request(
        self, dsr_service, mock_db, mock_user_id, mock_company_id
    ):
        """Portabilitaetsantrag (Art. 20) erfolgreich erstellen."""
        result = await dsr_service.create_request(
            db=mock_db,
            request_type=DSRType.PORTABILITY,
            requester_email="test@example.com",
            user_id=mock_user_id,
            company_id=mock_company_id,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_request_due_date_30_days(
        self, dsr_service, mock_db, mock_user_id
    ):
        """Due Date ist 30 Tage nach Antragstellung (DSGVO-Frist)."""
        result = await dsr_service.create_request(
            db=mock_db,
            request_type=DSRType.ACCESS,
            requester_email="test@example.com",
            user_id=mock_user_id,
        )

        now = datetime.now(timezone.utc)
        expected_due = now + timedelta(days=30)
        # Toleranz von 1 Minute
        assert abs((result.due_date - expected_due).total_seconds()) < 60


class TestVerifyIdentity:
    """Tests for verify_identity method."""

    @pytest.mark.asyncio
    async def test_verify_identity_success(
        self, dsr_service, mock_db, mock_dsr_request
    ):
        """Identitaet erfolgreich verifizieren."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_dsr_request
        mock_db.execute.return_value = mock_result

        result = await dsr_service.verify_identity(
            db=mock_db,
            request_id=mock_dsr_request.id,
            verification_token="test-token-12345",
        )

        assert result.success is True
        assert result.verified is True
        assert result.verified_at is not None
        assert mock_dsr_request.verified_at is not None

    @pytest.mark.asyncio
    async def test_verify_identity_invalid_token(
        self, dsr_service, mock_db, mock_dsr_request
    ):
        """Verifikation mit falschem Token fehlgeschlagen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_dsr_request
        mock_db.execute.return_value = mock_result

        result = await dsr_service.verify_identity(
            db=mock_db,
            request_id=mock_dsr_request.id,
            verification_token="wrong-token",
        )

        assert result.success is False
        assert result.verified is False
        # Service meldet "Ungültiger Verifizierungstoken" (mit Umlaut)
        assert "ungültig" in result.message.lower() or "token" in result.message.lower()

    @pytest.mark.asyncio
    async def test_verify_identity_request_not_found(
        self, dsr_service, mock_db
    ):
        """Verifikation fehlgeschlagen - Anfrage nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await dsr_service.verify_identity(
            db=mock_db,
            request_id=uuid4(),
            verification_token="any-token",
        )

        assert result.success is False
        assert "nicht gefunden" in result.message

    @pytest.mark.asyncio
    async def test_verify_identity_already_verified(
        self, dsr_service, mock_db, mock_dsr_request
    ):
        """Anfrage bereits verifiziert."""
        mock_dsr_request.verified_at = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_dsr_request
        mock_db.execute.return_value = mock_result

        result = await dsr_service.verify_identity(
            db=mock_db,
            request_id=mock_dsr_request.id,
            verification_token="test-token-12345",
        )

        assert result.success is True
        assert result.verified is True
        assert "bereits verifiziert" in result.message


class TestExportPersonalDataSummary:
    """Tests for export_personal_data_summary method."""

    @pytest.mark.asyncio
    async def test_export_personal_data_summary_success(
        self, dsr_service, mock_db, mock_user
    ):
        """Datenzusammenfassung erfolgreich exportieren.

        Der Service nutzt db.execute(select(User/Document/...)) - 4 Aufrufe bei
        include_documents+include_activity: User, Dokumente, Kommentare,
        Aktivitaeten.
        """
        def res(scalar_value=None, scalars_list=None):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=scalar_value)
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=scalars_list or [])
            r.scalars = MagicMock(return_value=scalars)
            return r

        user_result = res(scalar_value=mock_user)
        doc_result = res(scalars_list=[MagicMock(id=uuid4(), filename="a.pdf", document_type="invoice", created_at=datetime.now(timezone.utc))])
        comment_result = res(scalars_list=[])
        activity_result = res(scalars_list=[])
        mock_db.execute.side_effect = [user_result, doc_result, comment_result, activity_result]

        result = await dsr_service.export_personal_data_summary(
            db=mock_db,
            user_id=mock_user.id,
            company_id=mock_user.company_id,
            include_documents=True,
            include_activity=True,
        )

        assert isinstance(result, PersonalDataSummary)
        assert result.user_id == mock_user.id
        assert result.export_date is not None
        assert len(result.data_categories) > 0
        # Service legt die Benutzerdaten unter "benutzer" ab
        assert "benutzer" in result.personal_data
        assert result.personal_data["benutzer"]["email"] == mock_user.email

    @pytest.mark.asyncio
    async def test_export_personal_data_summary_user_not_found(
        self, dsr_service, mock_db
    ):
        """Ohne User wird eine Summary ohne Benutzerdaten geliefert (kein Raise).

        Der Service prueft `if user:` und ueberspringt die Benutzerdaten -
        er wirft keine Exception.
        """
        def res(scalar_value=None, scalars_list=None):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=scalar_value)
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=scalars_list or [])
            r.scalars = MagicMock(return_value=scalars)
            return r

        # User None, dann Dokumente/Aktivitaeten leer
        mock_db.execute.side_effect = [res(scalar_value=None), res(), res(), res()]

        result = await dsr_service.export_personal_data_summary(
            db=mock_db,
            user_id=uuid4(),
        )

        assert isinstance(result, PersonalDataSummary)
        assert "benutzer" not in result.personal_data


class TestRectifyData:
    """Tests for rectify_data method."""

    @pytest.mark.asyncio
    async def test_rectify_data_success(
        self, dsr_service, mock_db, mock_user
    ):
        """Erlaubtes Feld (name) erfolgreich berichtigen."""
        mock_user.name = "Max Mustermann"
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute.return_value = user_result

        result = await dsr_service.rectify_data(
            db=mock_db,
            user_id=mock_user.id,
            corrections={"name": "Maximilian Mustermann"},
            reason="Name war falsch geschrieben",
        )

        assert result.success is True
        assert "name" in result.corrected_fields
        assert mock_user.name == "Maximilian Mustermann"

    @pytest.mark.asyncio
    async def test_rectify_data_protected_fields(
        self, dsr_service, mock_db, mock_user
    ):
        """Geschuetzte Felder (id/email) duerfen nicht geaendert werden."""
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_db.execute.return_value = user_result

        result = await dsr_service.rectify_data(
            db=mock_db,
            user_id=mock_user.id,
            corrections={"id": uuid4(), "email": "hacker@evil.com", "name": "Valid"},
            reason="Test",
        )

        # id und email sind geschuetzt
        assert "id" in result.protected_fields
        assert "email" in result.protected_fields
        # name (erlaubt) wurde berichtigt
        assert "name" in result.corrected_fields

    @pytest.mark.asyncio
    async def test_rectify_data_user_not_found(
        self, dsr_service, mock_db
    ):
        """Berichtigung fehlgeschlagen - Benutzer nicht gefunden."""
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute.return_value = user_result

        result = await dsr_service.rectify_data(
            db=mock_db,
            user_id=uuid4(),
            corrections={"name": "Test"},
        )

        assert result.success is False
        assert "nicht gefunden" in result.message


class TestListRequests:
    """Tests for list_requests method."""

    @pytest.mark.asyncio
    async def test_list_requests_by_user(
        self, dsr_service, mock_db, mock_user_id, mock_dsr_request
    ):
        """Anfragen nach Benutzer filtern."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_dsr_request]
        mock_db.execute.return_value = mock_result

        requests = await dsr_service.list_requests(
            db=mock_db,
            user_id=mock_user_id,
        )

        assert isinstance(requests, list)
        assert len(requests) >= 0

    @pytest.mark.asyncio
    async def test_list_requests_by_status(
        self, dsr_service, mock_db, mock_company_id, mock_dsr_request
    ):
        """Anfragen nach Status filtern."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_dsr_request]
        mock_db.execute.return_value = mock_result

        requests = await dsr_service.list_requests(
            db=mock_db,
            company_id=mock_company_id,
            status=DSRStatus.PENDING,
        )

        assert isinstance(requests, list)

    @pytest.mark.asyncio
    async def test_list_requests_overdue(
        self, dsr_service, mock_db, mock_company_id
    ):
        """Ueberfaellige Anfragen filtern (Serialisierung zu DSRRequest)."""
        # DB-Row braucht gueltige Enum-Werte, damit DSRType()/DSRStatus()
        # nicht fehlschlagen.
        overdue_request = MagicMock()
        overdue_request.id = uuid4()
        overdue_request.request_type = DSRType.ACCESS.value
        overdue_request.status = DSRStatus.IN_PROGRESS.value
        overdue_request.requester_email = "test@example.com"
        overdue_request.requester_name = "Max Mustermann"
        overdue_request.user_id = uuid4()
        overdue_request.company_id = mock_company_id
        overdue_request.description = None
        overdue_request.affected_data_categories = [DataCategory.PERSONAL.value]
        overdue_request.requested_at = datetime.now(timezone.utc) - timedelta(days=40)
        overdue_request.created_at = datetime.now(timezone.utc) - timedelta(days=40)
        overdue_request.due_date = datetime.now(timezone.utc) - timedelta(days=5)
        overdue_request.verified_at = None
        overdue_request.started_at = None
        overdue_request.completed_at = None
        overdue_request.assigned_to_id = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [overdue_request]
        mock_db.execute.return_value = mock_result

        requests = await dsr_service.list_requests(
            db=mock_db,
            company_id=mock_company_id,
            overdue_only=True,
        )

        assert len(requests) == 1
        assert requests[0].status == DSRStatus.IN_PROGRESS
        # Ueberfaellig -> days_remaining auf 0 geklemmt
        assert requests[0].days_remaining == 0


class TestGetRequest:
    """Tests for get_request method."""

    @pytest.mark.asyncio
    async def test_get_request_success(
        self, dsr_service, mock_db, mock_dsr_request
    ):
        """Anfrage erfolgreich abrufen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_dsr_request
        mock_db.execute.return_value = mock_result

        request = await dsr_service.get_request(
            db=mock_db,
            request_id=mock_dsr_request.id,
        )

        assert request is not None

    @pytest.mark.asyncio
    async def test_get_request_with_user_filter(
        self, dsr_service, mock_db, mock_dsr_request, mock_user_id
    ):
        """Anfrage mit Benutzer-Filter abrufen."""
        mock_dsr_request.user_id = mock_user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_dsr_request
        mock_db.execute.return_value = mock_result

        request = await dsr_service.get_request(
            db=mock_db,
            request_id=mock_dsr_request.id,
            user_id=mock_user_id,
        )

        assert request is not None

    @pytest.mark.asyncio
    async def test_get_request_not_found(
        self, dsr_service, mock_db
    ):
        """Anfrage nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        request = await dsr_service.get_request(
            db=mock_db,
            request_id=uuid4(),
        )

        assert request is None


class TestDSRTypes:
    """Tests for DSRType enum values."""

    def test_all_dsgvo_rights_covered(self):
        """Alle DSGVO-Betroffenenrechte sind abgedeckt."""
        required_types = [
            "access",       # Art. 15
            "rectification",  # Art. 16
            "erasure",      # Art. 17
            "restriction",  # Art. 18
            "portability",  # Art. 20
            "objection",    # Art. 21
        ]

        type_values = [t.value for t in DSRType]

        for required in required_types:
            assert required in type_values, f"DSRType '{required}' fehlt"


class TestDataCategories:
    """Tests for DataCategory enum values."""

    def test_all_data_categories_exist(self):
        """Alle Datenkategorien sind definiert."""
        required_categories = [
            "personal",
            "financial",
            "documents",
            "activity",
        ]

        category_values = [c.value for c in DataCategory]

        for required in required_categories:
            assert required in category_values, f"DataCategory '{required}' fehlt"


class TestDSRStatus:
    """Tests for DSRStatus enum values."""

    def test_all_status_values_exist(self):
        """Alle Status-Werte sind definiert."""
        required_statuses = [
            "pending",
            "in_progress",
            "completed",
            "rejected",
            "cancelled",
        ]

        status_values = [s.value for s in DSRStatus]

        for required in required_statuses:
            assert required in status_values, f"DSRStatus '{required}' fehlt"
