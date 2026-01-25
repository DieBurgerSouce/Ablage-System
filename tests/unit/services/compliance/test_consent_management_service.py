# -*- coding: utf-8 -*-
"""
Unit tests for ConsentManagementService (Art. 6, 7 DSGVO).

Phase 7: Compliance & Audit - GDPR Erweiterungen

Tests:
- Consent erteilen (grant)
- Consent widerrufen (withdraw)
- Consent-Status pruefen (check)
- Consent-Historie abrufen
- Consent-Versionen verwalten
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
    ConsentRecord,
    ConsentGrantResult,
    ConsentWithdrawalResult,
    ConsentCheckResult,
)


@pytest.fixture
def consent_service():
    """Create ConsentManagementService instance."""
    return ConsentManagementService()


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
    return db


@pytest.fixture
def mock_consent_version():
    """Create mock consent version record."""
    version = MagicMock()
    version.id = uuid4()
    version.scope = ConsentScope.PERSONAL_DATA.value
    version.version = "1.0.0"
    version.title = "Verarbeitung personenbezogener Daten"
    version.description = "Beschreibung"
    version.full_text = "Voller Einwilligungstext..."
    version.text_hash = hashlib.sha256(b"Voller Einwilligungstext...").hexdigest()
    version.is_active = True
    version.effective_from = datetime.now(timezone.utc) - timedelta(days=30)
    return version


class TestGrantConsent:
    """Tests for grant_consent method."""

    @pytest.mark.asyncio
    async def test_grant_consent_success(
        self, consent_service, mock_db, mock_user_id, mock_company_id, mock_consent_version
    ):
        """Einwilligung erfolgreich erteilen."""
        # Mock: Keine existierende Consent
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Mock: Consent-Version abrufen
        with patch.object(
            consent_service, '_get_active_consent_version',
            return_value=mock_consent_version
        ):
            result = await consent_service.grant_consent(
                db=mock_db,
                user_id=mock_user_id,
                scope=ConsentScope.PERSONAL_DATA,
                method=ConsentMethod.WEB_FORM,
                company_id=mock_company_id,
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
            )

        assert result.success is True
        assert result.scope == ConsentScope.PERSONAL_DATA
        assert result.consent_given is True
        assert "erfolgreich erteilt" in result.message
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_grant_consent_already_active(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Einwilligung bereits aktiv - keine Aenderung."""
        # Mock: Existierende aktive Consent
        existing_consent = MagicMock()
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_consent
        mock_db.execute.return_value = mock_result

        result = await consent_service.grant_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.PERSONAL_DATA,
            method=ConsentMethod.WEB_FORM,
            company_id=mock_company_id,
        )

        assert result.success is True
        assert "bereits aktiv" in result.message

    @pytest.mark.asyncio
    async def test_grant_consent_reactivate_withdrawn(
        self, consent_service, mock_db, mock_user_id, mock_company_id, mock_consent_version
    ):
        """Widerrufene Einwilligung reaktivieren."""
        # Mock: Existierende widerrufene Consent
        existing_consent = MagicMock()
        existing_consent.consent_given = False
        existing_consent.withdrawn_at = datetime.now(timezone.utc) - timedelta(days=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_consent
        mock_db.execute.return_value = mock_result

        with patch.object(
            consent_service, '_get_active_consent_version',
            return_value=mock_consent_version
        ):
            result = await consent_service.grant_consent(
                db=mock_db,
                user_id=mock_user_id,
                scope=ConsentScope.PERSONAL_DATA,
                method=ConsentMethod.WEB_FORM,
                company_id=mock_company_id,
            )

        assert result.success is True
        assert existing_consent.consent_given is True
        assert existing_consent.withdrawn_at is None


class TestWithdrawConsent:
    """Tests for withdraw_consent method."""

    @pytest.mark.asyncio
    async def test_withdraw_consent_success(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Einwilligung erfolgreich widerrufen."""
        # Mock: Existierende aktive Consent
        existing_consent = MagicMock()
        existing_consent.id = uuid4()
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None
        existing_consent.scope = ConsentScope.MARKETING.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_consent
        mock_db.execute.return_value = mock_result

        result = await consent_service.withdraw_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.MARKETING,
            reason="Keine Marketingemails mehr gewuenscht",
            company_id=mock_company_id,
        )

        assert result.success is True
        assert result.scope == ConsentScope.MARKETING
        assert result.consent_given is False
        assert "erfolgreich widerrufen" in result.message
        assert existing_consent.consent_given is False
        assert existing_consent.withdrawn_at is not None

    @pytest.mark.asyncio
    async def test_withdraw_consent_not_found(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Widerruf fehlgeschlagen - keine Einwilligung gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await consent_service.withdraw_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.ANALYTICS,
            company_id=mock_company_id,
        )

        assert result.success is False
        assert "nicht gefunden" in result.message

    @pytest.mark.asyncio
    async def test_withdraw_consent_already_withdrawn(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Widerruf fehlgeschlagen - bereits widerrufen."""
        existing_consent = MagicMock()
        existing_consent.consent_given = False
        existing_consent.withdrawn_at = datetime.now(timezone.utc) - timedelta(days=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_consent
        mock_db.execute.return_value = mock_result

        result = await consent_service.withdraw_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.ANALYTICS,
            company_id=mock_company_id,
        )

        assert result.success is False
        assert "bereits widerrufen" in result.message


class TestCheckConsent:
    """Tests for check_consent method."""

    @pytest.mark.asyncio
    async def test_check_consent_active(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Aktive Einwilligung pruefen."""
        existing_consent = MagicMock()
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None
        existing_consent.granted_at = datetime.now(timezone.utc) - timedelta(days=10)
        existing_consent.valid_until = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_consent
        mock_db.execute.return_value = mock_result

        result = await consent_service.check_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.DOCUMENT_PROCESSING,
            company_id=mock_company_id,
        )

        assert result.has_consent is True
        assert result.status == ConsentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_check_consent_expired(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Abgelaufene Einwilligung pruefen."""
        existing_consent = MagicMock()
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None
        existing_consent.granted_at = datetime.now(timezone.utc) - timedelta(days=400)
        existing_consent.valid_until = datetime.now(timezone.utc) - timedelta(days=30)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_consent
        mock_db.execute.return_value = mock_result

        result = await consent_service.check_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.ANALYTICS,
            company_id=mock_company_id,
        )

        assert result.has_consent is False
        assert result.status == ConsentStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_check_consent_withdrawn(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Widerrufene Einwilligung pruefen."""
        existing_consent = MagicMock()
        existing_consent.consent_given = False
        existing_consent.withdrawn_at = datetime.now(timezone.utc) - timedelta(days=5)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_consent
        mock_db.execute.return_value = mock_result

        result = await consent_service.check_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.MARKETING,
            company_id=mock_company_id,
        )

        assert result.has_consent is False
        assert result.status == ConsentStatus.WITHDRAWN

    @pytest.mark.asyncio
    async def test_check_consent_not_found(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Keine Einwilligung gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await consent_service.check_consent(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.FINANCIAL_DATA,
            company_id=mock_company_id,
        )

        assert result.has_consent is False
        assert result.status == ConsentStatus.NOT_GIVEN


class TestGetConsentSummary:
    """Tests for get_consent_summary method."""

    @pytest.mark.asyncio
    async def test_get_consent_summary_all_scopes(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Zusammenfassung aller Consent-Scopes abrufen."""
        # Mock: Verschiedene Consents fuer verschiedene Scopes
        consents = [
            MagicMock(
                scope=ConsentScope.PERSONAL_DATA.value,
                consent_given=True,
                withdrawn_at=None,
                granted_at=datetime.now(timezone.utc) - timedelta(days=10),
                valid_until=None,
            ),
            MagicMock(
                scope=ConsentScope.MARKETING.value,
                consent_given=False,
                withdrawn_at=datetime.now(timezone.utc) - timedelta(days=5),
                granted_at=datetime.now(timezone.utc) - timedelta(days=30),
                valid_until=None,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = consents
        mock_db.execute.return_value = mock_result

        summary = await consent_service.get_consent_summary(
            db=mock_db,
            user_id=mock_user_id,
            company_id=mock_company_id,
        )

        assert summary.user_id == mock_user_id
        assert len(summary.scopes) >= 2
        # Personal Data sollte aktiv sein
        personal_data_scope = next(
            (s for s in summary.scopes if s.scope == ConsentScope.PERSONAL_DATA),
            None
        )
        assert personal_data_scope is not None
        assert personal_data_scope.status == ConsentStatus.ACTIVE


class TestGetConsentHistory:
    """Tests for get_consent_history method."""

    @pytest.mark.asyncio
    async def test_get_consent_history_success(
        self, consent_service, mock_db, mock_user_id, mock_company_id
    ):
        """Consent-Historie erfolgreich abrufen."""
        history_entries = [
            MagicMock(
                id=uuid4(),
                action=ConsentHistoryAction.GRANTED.value,
                created_at=datetime.now(timezone.utc) - timedelta(days=30),
                previous_value=False,
                new_value=True,
                ip_address="192.168.1.1",
                reason=None,
            ),
            MagicMock(
                id=uuid4(),
                action=ConsentHistoryAction.WITHDRAWN.value,
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
                previous_value=True,
                new_value=False,
                ip_address="192.168.1.2",
                reason="Keine Emails mehr",
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = history_entries
        mock_db.execute.return_value = mock_result

        history = await consent_service.get_consent_history(
            db=mock_db,
            user_id=mock_user_id,
            scope=ConsentScope.MARKETING,
            company_id=mock_company_id,
        )

        assert len(history) == 2
        assert history[0].action in [ConsentHistoryAction.GRANTED, ConsentHistoryAction.WITHDRAWN]


class TestConsentScopes:
    """Tests for ConsentScope enum values."""

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
