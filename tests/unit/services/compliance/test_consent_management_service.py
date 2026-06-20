# -*- coding: utf-8 -*-
"""
Unit tests for ConsentManagementService (Art. 6, 7 DSGVO).

Phase 7: Compliance & Audit - GDPR Erweiterungen

Testet gegen den ECHTEN Vertrag von
app.services.compliance.consent_management_service:
- grant_consent (Convenience-Wrapper um record_consent)
- withdraw_consent (ConsentWithdrawalResult: was_active/impacts)
- check_consent (ConsentCheckResult: consent_given/status/message)
- get_consent_history (ConsentHistoryEntry-Liste)
- get_consent_summary (ConsentSummary: by_scope Dict)
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import hashlib

from app.services.compliance.consent_management_service import (
    ConsentManagementService,
    ConsentScope,
    ConsentMethod,
    ConsentStatus,
    ConsentHistoryAction,
    ConsentGrantResult,
    ConsentWithdrawalResult,
    ConsentCheckResult,
    ConsentHistoryEntry,
    ConsentSummary,
)


@pytest.fixture
def consent_service():
    """Create ConsentManagementService instance."""
    return ConsentManagementService()


@pytest.fixture
def mock_user_id():
    return uuid4()


@pytest.fixture
def mock_company_id():
    return uuid4()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_consent_version():
    """Create mock active consent version (von get_active_consent_version)."""
    version = MagicMock()
    version.id = uuid4()
    version.scope = ConsentScope.PERSONAL_DATA.value
    version.version = "1.0.0"
    version.text_hash = hashlib.sha256(b"Voller Einwilligungstext...").hexdigest()
    version.is_active = True
    return version


def _result(scalar_value=None, scalars_list=None):
    """Mock-Result fuer db.execute()."""
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=scalar_value)
    res.scalar = MagicMock(return_value=scalar_value)
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=scalars_list if scalars_list is not None else [])
    res.scalars = MagicMock(return_value=scalars)
    return res


class TestGrantConsent:
    """Tests for grant_consent (-> record_consent)."""

    @pytest.mark.asyncio
    async def test_grant_consent_success_new_record(
        self, consent_service, mock_db, mock_user_id, mock_company_id, mock_consent_version
    ):
        """Neue Einwilligung erfolgreich erteilen (kein Bestandsdatensatz)."""
        # existing-Query liefert None -> neuer Datensatz
        mock_db.execute.return_value = _result(scalar_value=None)

        with patch.object(
            consent_service, "get_active_consent_version",
            new=AsyncMock(return_value=mock_consent_version),
        ):
            result = await consent_service.grant_consent(
                db=mock_db,
                user_id=mock_user_id,
                scope=ConsentScope.PERSONAL_DATA,
                consent_method=ConsentMethod.WEB_FORM,
                company_id=mock_company_id,
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
            )

        assert isinstance(result, ConsentGrantResult)
        assert result.success is True
        assert result.scope == ConsentScope.PERSONAL_DATA
        assert "erfolgreich erteilt" in result.message
        assert result.text_hash == mock_consent_version.text_hash
        # Neuer Consent + History-Eintrag wurden hinzugefuegt
        assert mock_db.add.call_count >= 2
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_grant_consent_updates_existing(
        self, consent_service, mock_db, mock_user_id, mock_company_id, mock_consent_version
    ):
        """Bestehender (widerrufener) Datensatz wird reaktiviert."""
        existing_consent = MagicMock()
        existing_consent.id = uuid4()
        existing_consent.consent_given = False
        existing_consent.withdrawn_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock_db.execute.return_value = _result(scalar_value=existing_consent)

        with patch.object(
            consent_service, "get_active_consent_version",
            new=AsyncMock(return_value=mock_consent_version),
        ):
            result = await consent_service.grant_consent(
                db=mock_db,
                user_id=mock_user_id,
                scope=ConsentScope.PERSONAL_DATA,
                consent_method=ConsentMethod.WEB_FORM,
                company_id=mock_company_id,
            )

        assert result.success is True
        # Bestandsdatensatz wurde reaktiviert
        assert existing_consent.consent_given is True
        assert existing_consent.withdrawn_at is None


class TestWithdrawConsent:
    """Tests for withdraw_consent."""

    @pytest.mark.asyncio
    async def test_withdraw_consent_success(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Aktive Einwilligung erfolgreich widerrufen."""
        existing_consent = MagicMock()
        existing_consent.id = uuid4()
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None
        mock_db.execute.return_value = _result(scalar_value=existing_consent)

        result = await consent_service.withdraw_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.MARKETING,
            reason="Keine Marketingemails mehr gewuenscht",
            company_id=mock_company_id,
        )

        assert isinstance(result, ConsentWithdrawalResult)
        assert result.success is True
        assert result.scope == ConsentScope.MARKETING
        assert result.was_active is True
        assert "erfolgreich widerrufen" in result.message
        assert existing_consent.consent_given is False
        assert existing_consent.withdrawn_at is not None
        # Marketing-Widerruf liefert Auswirkungen
        assert len(result.impacts) > 0

    @pytest.mark.asyncio
    async def test_withdraw_consent_not_found(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Widerruf ohne vorhandene Einwilligung -> success=False."""
        mock_db.execute.return_value = _result(scalar_value=None)

        result = await consent_service.withdraw_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.ANALYTICS,
            company_id=mock_company_id,
        )

        assert result.success is False
        assert result.was_active is False
        assert "gefunden" in result.message

    @pytest.mark.asyncio
    async def test_withdraw_consent_already_withdrawn(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Bereits widerrufene Einwilligung: erneuter Widerruf ist idempotent.

        Der Service kennt keinen Sonderfall - er setzt erneut withdrawn_at,
        meldet aber was_active=False (war vorher nicht aktiv).
        """
        existing_consent = MagicMock()
        existing_consent.id = uuid4()
        existing_consent.consent_given = False
        existing_consent.withdrawn_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock_db.execute.return_value = _result(scalar_value=existing_consent)

        result = await consent_service.withdraw_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.ANALYTICS,
            company_id=mock_company_id,
        )

        assert result.success is True
        assert result.was_active is False


class TestCheckConsent:
    """Tests for check_consent (ConsentCheckResult.consent_given/status)."""

    @pytest.mark.asyncio
    async def test_check_consent_active(
        self, consent_service, mock_db, mock_user_id, mock_company_id, mock_consent_version
    ):
        """Aktive Einwilligung -> consent_given=True, status=ACTIVE."""
        existing_consent = MagicMock()
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None
        existing_consent.granted_at = datetime.now(timezone.utc) - timedelta(days=10)
        existing_consent.valid_until = None
        # Hash passt zur aktiven Version (version_current=True)
        existing_consent.consent_text_hash = mock_consent_version.text_hash
        mock_db.execute.return_value = _result(scalar_value=existing_consent)

        with patch.object(
            consent_service, "get_active_consent_version",
            new=AsyncMock(return_value=mock_consent_version),
        ):
            result = await consent_service.check_consent(
                db=mock_db,
                user_id=mock_user_id,
                scope=ConsentScope.DOCUMENT_PROCESSING,
                company_id=mock_company_id,
            )

        assert isinstance(result, ConsentCheckResult)
        assert result.consent_given is True
        assert result.status == ConsentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_check_consent_expired(
        self, consent_service, mock_db, mock_user_id, mock_company_id, mock_consent_version
    ):
        """Abgelaufene Einwilligung -> status=EXPIRED, consent_given=False."""
        existing_consent = MagicMock()
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None
        existing_consent.granted_at = datetime.now(timezone.utc) - timedelta(days=400)
        existing_consent.valid_until = datetime.now(timezone.utc) - timedelta(days=30)
        existing_consent.consent_text_hash = mock_consent_version.text_hash
        mock_db.execute.return_value = _result(scalar_value=existing_consent)

        with patch.object(
            consent_service, "get_active_consent_version",
            new=AsyncMock(return_value=mock_consent_version),
        ):
            result = await consent_service.check_consent(
                db=mock_db,
                user_id=mock_user_id,
                scope=ConsentScope.ANALYTICS,
                company_id=mock_company_id,
            )

        assert result.status == ConsentStatus.EXPIRED
        assert result.consent_given is False
        assert result.requires_renewal is True

    @pytest.mark.asyncio
    async def test_check_consent_withdrawn(
        self, consent_service, mock_db, mock_user_id, mock_company_id, mock_consent_version
    ):
        """Widerrufene Einwilligung -> status=WITHDRAWN."""
        existing_consent = MagicMock()
        existing_consent.consent_given = False
        existing_consent.withdrawn_at = datetime.now(timezone.utc) - timedelta(days=5)
        existing_consent.granted_at = datetime.now(timezone.utc) - timedelta(days=30)
        existing_consent.valid_until = None
        existing_consent.consent_text_hash = mock_consent_version.text_hash
        mock_db.execute.return_value = _result(scalar_value=existing_consent)

        with patch.object(
            consent_service, "get_active_consent_version",
            new=AsyncMock(return_value=mock_consent_version),
        ):
            result = await consent_service.check_consent(
                db=mock_db,
                user_id=mock_user_id,
                scope=ConsentScope.MARKETING,
                company_id=mock_company_id,
            )

        assert result.status == ConsentStatus.WITHDRAWN
        assert result.consent_given is False

    @pytest.mark.asyncio
    async def test_check_consent_not_found(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Keine Einwilligung -> status=NOT_GIVEN, consent_given=False."""
        mock_db.execute.return_value = _result(scalar_value=None)

        result = await consent_service.check_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.FINANCIAL_DATA,
            company_id=mock_company_id,
        )

        assert result.status == ConsentStatus.NOT_GIVEN
        assert result.consent_given is False


class TestGetConsentSummary:
    """Tests for get_consent_summary (ConsentSummary.by_scope Dict)."""

    @pytest.mark.asyncio
    async def test_get_consent_summary_aggregates(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Zusammenfassung aggregiert ueber alle Scopes (by_scope-Dict)."""
        # check_all_consents ruft check_consent je Scope -> kein Consent (None),
        # daher Status NOT_GIVEN ueberall. get_consent_history liefert leer.
        mock_db.execute.return_value = _result(scalar_value=None, scalars_list=[])

        summary = await consent_service.get_consent_summary(
            db=mock_db,
            user_id=mock_user_id,
            company_id=mock_company_id,
        )

        assert isinstance(summary, ConsentSummary)
        assert summary.user_id == mock_user_id
        assert summary.total_scopes == len(ConsentScope)
        # Alle Scopes ohne Datensatz -> by_scope deckt alle Scopes ab
        assert len(summary.by_scope) == len(ConsentScope)
        assert all(v == ConsentStatus.NOT_GIVEN for v in summary.by_scope.values())


class TestGetConsentHistory:
    """Tests for get_consent_history (ConsentHistoryEntry-Liste)."""

    @pytest.mark.asyncio
    async def test_get_consent_history_success(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Consent-Historie wird zu ConsentHistoryEntry serialisiert."""
        history_entries = [
            MagicMock(
                id=uuid4(),
                consent_scope_id=uuid4(),
                action=ConsentHistoryAction.GRANTED.value,
                created_at=datetime.now(timezone.utc) - timedelta(days=30),
                previous_value=False,
                new_value=True,
                consent_version_id=uuid4(),
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
                reason=None,
            ),
            MagicMock(
                id=uuid4(),
                consent_scope_id=uuid4(),
                action=ConsentHistoryAction.WITHDRAWN.value,
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
                previous_value=True,
                new_value=False,
                consent_version_id=uuid4(),
                ip_address="192.168.1.2",
                user_agent="Mozilla/5.0",
                reason="Keine Emails mehr",
            ),
        ]
        mock_db.execute.return_value = _result(scalars_list=history_entries)

        history = await consent_service.get_consent_history(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.MARKETING,
        )

        assert len(history) == 2
        assert all(isinstance(e, ConsentHistoryEntry) for e in history)
        # action wird in das Enum konvertiert
        assert history[0].action == ConsentHistoryAction.GRANTED
        assert history[1].action == ConsentHistoryAction.WITHDRAWN


class TestConsentScopes:
    """Tests for ConsentScope/ConsentMethod enum values."""

    def test_all_required_scopes_exist(self):
        """Alle erforderlichen Scopes sind definiert."""
        required_scopes = [
            "personal_data",
            "financial_data",
            "document_processing",
            "analytics",
            "marketing",
        ]
        scope_values = [s.value for s in ConsentScope]
        for required in required_scopes:
            assert required in scope_values, f"Scope '{required}' fehlt"

    def test_consent_methods(self):
        """Alle Consent-Methoden sind definiert."""
        methods = [m.value for m in ConsentMethod]
        assert "web_form" in methods
        assert "api" in methods
        assert "paper" in methods
