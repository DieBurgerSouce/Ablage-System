# -*- coding: utf-8 -*-
"""
Unit-Tests fuer SignatureService.

Testet:
- Signaturanfrage erstellen
- Dokument signieren (einzeln und alle)
- Signatur ablehnen
- Signierreihenfolge validieren
- Signaturen verifizieren
- Ausstehende Signaturen abrufen
- Audit-Trail erstellen

Feinpoliert und durchdacht - Umfassende Signatur-Service-Tests.
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import List
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from app.db.models_signature import (
    SignatureRequest,
    SignatureEntry,
    SignatureAuditLog,
    SignatureStatus,
    SignatureLevel,
    SignatureProvider,
)
from app.services.signature.signature_service import (
    SignatureService,
    SignerInfo,
    SignatureVerificationResult,
)


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session():
    """Erstellt eine Mock-Datenbank-Session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def company_id() -> UUID:
    """Mandanten-ID."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Benutzer-ID."""
    return uuid4()


@pytest.fixture
def document_id() -> UUID:
    """Dokument-ID."""
    return uuid4()


@pytest.fixture
def sample_signers() -> List[SignerInfo]:
    """Beispiel-Unterzeichner."""
    return [
        SignerInfo(
            email="max.mustermann@example.com",
            name="Max Mustermann",
            user_id=uuid4(),
            signing_order=1,
        ),
        SignerInfo(
            email="erika.musterfrau@example.com",
            name="Erika Musterfrau",
            user_id=uuid4(),
            signing_order=2,
        ),
    ]


@pytest.fixture
def service() -> SignatureService:
    """Erstellt eine SignatureService-Instanz."""
    return SignatureService()


@pytest.fixture
def mock_signature_request(company_id, document_id, user_id):
    """Erstellt eine Mock-Signaturanfrage."""
    request = Mock(spec=SignatureRequest)
    request.id = uuid4()
    request.document_id = document_id
    request.company_id = company_id
    request.title = "Vertrag Unterschrift"
    request.signature_level = SignatureLevel.ADVANCED.value
    request.provider = SignatureProvider.INTERNAL.value
    request.status = SignatureStatus.PENDING.value
    request.requested_by = user_id
    request.requested_at = datetime.now(timezone.utc)
    request.completed_at = None
    request.expires_at = None
    request.signing_order_required = False
    request.deleted_at = None
    request.entries = []
    request.audit_logs = []
    return request


@pytest.fixture
def mock_signature_entry(company_id, mock_signature_request):
    """Erstellt einen Mock-Signatureintrag."""
    entry = Mock(spec=SignatureEntry)
    entry.id = uuid4()
    entry.signature_request_id = mock_signature_request.id
    entry.company_id = company_id
    entry.signer_id = uuid4()
    entry.signer_email = "max.mustermann@example.com"
    entry.signer_name = "Max Mustermann"
    entry.signing_order = 1
    entry.status = SignatureStatus.PENDING.value
    entry.signed_at = None
    entry.rejected_at = None
    entry.rejection_reason = None
    entry.certificate_issuer = None
    entry.certificate_serial = None
    entry.signature_hash = None
    entry.created_at = datetime.now(timezone.utc)
    return entry


# ========================= Tests =========================


class TestCreateSignatureRequest:
    """Tests fuer das Erstellen von Signaturanfragen."""

    @pytest.mark.asyncio
    async def test_create_signature_request(
        self, service, mock_db_session, document_id, company_id,
        user_id, sample_signers,
    ):
        """Erstellt eine Signaturanfrage mit 2 Unterzeichnern."""
        # Mock refresh to set entries
        async def mock_refresh(obj):
            if isinstance(obj, SignatureRequest):
                obj.entries = []

        mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_signature_request(
            db=mock_db_session,
            document_id=document_id,
            company_id=company_id,
            requested_by=user_id,
            title="Vertrag Unterschrift",
            signers=sample_signers,
            signature_level="advanced",
            provider="internal",
            signing_order_required=False,
            expires_in_days=30,
        )

        # Verifiziere: Request wurde zur Session hinzugefuegt
        assert mock_db_session.add.call_count >= 1
        # Verifiziere: flush und commit wurden aufgerufen
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

        # 1 Request + 2 Entries + 1 AuditLog = min 4 add() Aufrufe
        assert mock_db_session.add.call_count >= 4

    @pytest.mark.asyncio
    async def test_create_request_sets_expiry(
        self, service, mock_db_session, document_id, company_id, user_id,
    ):
        """Signaturanfrage hat korrekte Ablaufzeit."""
        signer = SignerInfo(
            email="test@example.com", name="Test User", signing_order=1,
        )

        async def mock_refresh(obj):
            pass

        mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

        await service.create_signature_request(
            db=mock_db_session,
            document_id=document_id,
            company_id=company_id,
            requested_by=user_id,
            title="Ablauftest",
            signers=[signer],
            expires_in_days=7,
        )

        # Erstes add() ist der Request
        first_add_call = mock_db_session.add.call_args_list[0]
        request_obj = first_add_call[0][0]
        assert request_obj.expires_at is not None


class TestSignDocument:
    """Tests fuer das Signieren von Dokumenten."""

    @pytest.mark.asyncio
    async def test_sign_document_updates_entry(
        self, service, mock_db_session, company_id, mock_signature_entry,
        mock_signature_request,
    ):
        """Signieren aktualisiert den Entry-Status auf SIGNED."""
        signer_id = uuid4()
        mock_signature_request.entries = [mock_signature_entry]

        # Mock _get_entry
        with patch.object(
            service, '_get_entry', return_value=mock_signature_entry,
        ), patch.object(
            service, 'get_signature_request',
            return_value=mock_signature_request,
        ):
            result = await service.sign_document(
                db=mock_db_session,
                entry_id=mock_signature_entry.id,
                company_id=company_id,
                signer_id=signer_id,
                certificate_issuer="D-Trust GmbH",
                certificate_serial="SN-12345",
                ip_address="192.168.1.1",
            )

        assert result.status == SignatureStatus.SIGNED.value
        assert result.signed_at is not None
        assert result.certificate_issuer == "D-Trust GmbH"
        assert result.certificate_serial == "SN-12345"
        assert result.signature_hash is not None
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sign_all_completes_request(
        self, service, mock_db_session, company_id, mock_signature_request,
    ):
        """Wenn alle Eintraege signiert sind, wird der Request abgeschlossen."""
        signer_id = uuid4()

        # Erstelle einen Entry der bereits als SIGNED markiert ist
        entry1 = Mock(spec=SignatureEntry)
        entry1.id = uuid4()
        entry1.status = SignatureStatus.SIGNED.value
        entry1.signing_order = 1

        # Zweiter Entry: pending, wird jetzt signiert
        entry2 = Mock(spec=SignatureEntry)
        entry2.id = uuid4()
        entry2.status = SignatureStatus.PENDING.value
        entry2.signing_order = 2
        entry2.signature_request_id = mock_signature_request.id
        entry2.signed_at = None
        entry2.certificate_issuer = None
        entry2.certificate_serial = None
        entry2.signature_hash = None
        entry2.signer_id = None

        mock_signature_request.entries = [entry1, entry2]
        mock_signature_request.signing_order_required = False

        with patch.object(
            service, '_get_entry', return_value=entry2,
        ), patch.object(
            service, 'get_signature_request',
            return_value=mock_signature_request,
        ):
            await service.sign_document(
                db=mock_db_session,
                entry_id=entry2.id,
                company_id=company_id,
                signer_id=signer_id,
            )

        # Entry 2 wurde signiert
        assert entry2.status == SignatureStatus.SIGNED.value

        # Jetzt sind alle SIGNED -> Request sollte completed sein
        # (_check_request_completion prueft entries)
        # entry2 status wurde oben gesetzt
        assert mock_signature_request.status == SignatureStatus.SIGNED.value
        assert mock_signature_request.completed_at is not None


class TestRejectSignature:
    """Tests fuer das Ablehnen von Signaturen."""

    @pytest.mark.asyncio
    async def test_reject_signature(
        self, service, mock_db_session, company_id,
        mock_signature_entry, mock_signature_request,
    ):
        """Ablehnung setzt Status auf REJECTED mit Begruendung."""
        signer_id = uuid4()

        with patch.object(
            service, '_get_entry', return_value=mock_signature_entry,
        ), patch.object(
            service, 'get_signature_request',
            return_value=mock_signature_request,
        ):
            result = await service.reject_signature(
                db=mock_db_session,
                entry_id=mock_signature_entry.id,
                company_id=company_id,
                signer_id=signer_id,
                reason="Vertragsbedingungen nicht akzeptabel",
                ip_address="10.0.0.1",
            )

        assert result.status == SignatureStatus.REJECTED.value
        assert result.rejected_at is not None
        assert result.rejection_reason == "Vertragsbedingungen nicht akzeptabel"
        # Request sollte auch REJECTED sein
        assert mock_signature_request.status == SignatureStatus.REJECTED.value
        mock_db_session.commit.assert_awaited_once()


class TestSigningOrderEnforcement:
    """Tests fuer die Signierreihenfolge."""

    @pytest.mark.asyncio
    async def test_signing_order_enforcement(
        self, service, mock_db_session, company_id, mock_signature_request,
    ):
        """Sequentielle Signierung validiert Reihenfolge."""
        mock_signature_request.signing_order_required = True

        # Entry 1 noch pending
        entry1 = Mock(spec=SignatureEntry)
        entry1.id = uuid4()
        entry1.status = SignatureStatus.PENDING.value
        entry1.signing_order = 1
        entry1.signer_name = "Max Mustermann"

        # Entry 2 versucht zu signieren, bevor Entry 1 fertig ist
        entry2 = Mock(spec=SignatureEntry)
        entry2.id = uuid4()
        entry2.status = SignatureStatus.PENDING.value
        entry2.signing_order = 2
        entry2.signature_request_id = mock_signature_request.id
        entry2.signer_id = None

        mock_signature_request.entries = [entry1, entry2]

        with patch.object(
            service, '_get_entry', return_value=entry2,
        ), patch.object(
            service, 'get_signature_request',
            return_value=mock_signature_request,
        ):
            with pytest.raises(ValueError, match="Signierreihenfolge"):
                await service.sign_document(
                    db=mock_db_session,
                    entry_id=entry2.id,
                    company_id=company_id,
                    signer_id=uuid4(),
                )


class TestVerifySignatures:
    """Tests fuer die Signaturverifikation."""

    @pytest.mark.asyncio
    async def test_verify_signatures_fully_signed(
        self, service, mock_db_session, document_id, company_id,
    ):
        """Vollstaendig signiertes Dokument wird korrekt erkannt."""
        entry1 = Mock(spec=SignatureEntry)
        entry1.id = uuid4()
        entry1.status = SignatureStatus.SIGNED.value
        entry1.signer_name = "Max Mustermann"
        entry1.signer_email = "max@example.com"
        entry1.signed_at = datetime.now(timezone.utc)
        entry1.certificate_issuer = "D-Trust GmbH"
        entry1.signature_hash = "abc123"

        entry2 = Mock(spec=SignatureEntry)
        entry2.id = uuid4()
        entry2.status = SignatureStatus.SIGNED.value
        entry2.signer_name = "Erika Musterfrau"
        entry2.signer_email = "erika@example.com"
        entry2.signed_at = datetime.now(timezone.utc)
        entry2.certificate_issuer = "D-Trust GmbH"
        entry2.signature_hash = "def456"

        request = Mock(spec=SignatureRequest)
        request.entries = [entry1, entry2]

        # Mock execute result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [request]
        mock_db_session.execute.return_value = mock_result

        result = await service.verify_signatures(
            db=mock_db_session,
            document_id=document_id,
            company_id=company_id,
        )

        assert result.is_fully_signed is True
        assert result.total_signatures == 2
        assert result.completed_signatures == 2
        assert result.pending_signatures == 0
        assert result.rejected_signatures == 0

    @pytest.mark.asyncio
    async def test_verify_signatures_partial(
        self, service, mock_db_session, document_id, company_id,
    ):
        """Teilweise signiertes Dokument wird korrekt erkannt."""
        entry1 = Mock(spec=SignatureEntry)
        entry1.id = uuid4()
        entry1.status = SignatureStatus.SIGNED.value
        entry1.signer_name = "Max Mustermann"
        entry1.signer_email = "max@example.com"
        entry1.signed_at = datetime.now(timezone.utc)
        entry1.certificate_issuer = None
        entry1.signature_hash = "abc123"

        entry2 = Mock(spec=SignatureEntry)
        entry2.id = uuid4()
        entry2.status = SignatureStatus.PENDING.value
        entry2.signer_name = "Erika Musterfrau"
        entry2.signer_email = "erika@example.com"
        entry2.signed_at = None
        entry2.certificate_issuer = None
        entry2.signature_hash = None

        request = Mock(spec=SignatureRequest)
        request.entries = [entry1, entry2]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [request]
        mock_db_session.execute.return_value = mock_result

        result = await service.verify_signatures(
            db=mock_db_session,
            document_id=document_id,
            company_id=company_id,
        )

        assert result.is_fully_signed is False
        assert result.total_signatures == 2
        assert result.completed_signatures == 1
        assert result.pending_signatures == 1
        assert result.rejected_signatures == 0


class TestGetPendingSignatures:
    """Tests fuer ausstehende Signaturen."""

    @pytest.mark.asyncio
    async def test_get_pending_signatures(
        self, service, mock_db_session, company_id,
    ):
        """Gibt nur ausstehende Signaturen eines Users zurueck."""
        signer_id = uuid4()

        entry1 = Mock(spec=SignatureEntry)
        entry1.id = uuid4()
        entry1.status = SignatureStatus.PENDING.value
        entry1.signer_id = signer_id
        entry1.signer_email = "max@example.com"

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [entry1]
        mock_db_session.execute.return_value = mock_result

        result = await service.get_pending_signatures(
            db=mock_db_session,
            signer_id=signer_id,
            company_id=company_id,
        )

        assert len(result) == 1
        assert result[0].status == SignatureStatus.PENDING.value


class TestAuditTrail:
    """Tests fuer den Audit-Trail."""

    @pytest.mark.asyncio
    async def test_audit_trail_creation(
        self, service, mock_db_session, document_id, company_id, user_id,
    ):
        """Audit-Events werden bei Aktionen erstellt."""
        signer = SignerInfo(
            email="test@example.com", name="Test User", signing_order=1,
        )

        async def mock_refresh(obj):
            pass

        mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

        await service.create_signature_request(
            db=mock_db_session,
            document_id=document_id,
            company_id=company_id,
            requested_by=user_id,
            title="Audit-Test",
            signers=[signer],
        )

        # Mindestens ein AuditLog-Eintrag sollte hinzugefuegt worden sein
        # (1 Request + 1 Entry + 1 AuditLog = 3 add Aufrufe)
        add_calls = mock_db_session.add.call_args_list
        audit_logs = [
            call[0][0] for call in add_calls
            if isinstance(call[0][0], SignatureAuditLog)
        ]
        assert len(audit_logs) == 1
        assert audit_logs[0].action == "requested"

    @pytest.mark.asyncio
    async def test_get_audit_trail(
        self, service, mock_db_session, company_id,
    ):
        """Audit-Trail wird korrekt abgerufen."""
        request_id = uuid4()

        log1 = Mock(spec=SignatureAuditLog)
        log1.id = uuid4()
        log1.action = "requested"
        log1.performed_at = datetime.now(timezone.utc)

        log2 = Mock(spec=SignatureAuditLog)
        log2.id = uuid4()
        log2.action = "signed"
        log2.performed_at = datetime.now(timezone.utc)

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [log2, log1]
        mock_db_session.execute.return_value = mock_result

        result = await service.get_audit_trail(
            db=mock_db_session,
            request_id=request_id,
            company_id=company_id,
        )

        assert len(result) == 2
        assert result[0].action == "signed"
        assert result[1].action == "requested"
