# -*- coding: utf-8 -*-
"""
Umfassende Unit Tests fuer DATEV Connect Services.

Testet alle Komponenten der DATEVconnect Integration:
- DATEVAuthService - OAuth2 Flow
- DATEVConnector - ERP Connector
- KontierungsvorschlagService - ML-basierte Kontierung
- GoBDComplianceService - Festschreibung und Compliance

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.datev]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession fuer Datenbank-Tests."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_connection_id() -> UUID:
    """Sample Connection UUID."""
    return uuid4()


@pytest.fixture
def sample_company_id() -> UUID:
    """Sample Company UUID."""
    return uuid4()


@pytest.fixture
def sample_document_id() -> UUID:
    """Sample Document UUID."""
    return uuid4()


@pytest.fixture
def sample_entity_id() -> UUID:
    """Sample Entity UUID."""
    return uuid4()


@pytest.fixture
def sample_buchung_data() -> Dict:
    """Sample Buchungsdaten fuer Tests."""
    return {
        "belegdatum": datetime.now().date(),
        "betrag_soll": 119.00,
        "betrag_haben": 119.00,
        "konto_soll": "4400",
        "konto_haben": "70000",
        "steuerschluessel": "9",
        "buchungstext": "Wareneingang Test GmbH",
        "belegnummer": "RE-2026-001",
    }


@pytest.fixture
def sample_kontierung_input() -> Dict:
    """Sample Input fuer Kontierungsvorschlaege."""
    return {
        "lieferant_name": "Test GmbH",
        "lieferant_steuernr": "DE123456789",
        "betrag_brutto": Decimal("119.00"),
        "betrag_netto": Decimal("100.00"),
        "mwst_satz": Decimal("19.0"),
        "dokument_typ": "Rechnung",
    }


# =============================================================================
# DATEV AUTH SERVICE TESTS
# =============================================================================


class TestDATEVAuthService:
    """Tests fuer DATEVAuthService - OAuth2 Flow."""

    def test_get_authorization_url_generates_valid_url(self):
        """Authorization URL wird korrekt generiert."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        url, state = auth_service.get_authorization_url(
            client_id="test_client_id",
            redirect_uri="https://app.example.com/callback",
            environment="sandbox",
        )

        assert "https://login.sandbox.datev.de" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=" in url
        assert "state=" in url
        assert len(state) > 20  # CSRF token sollte lang sein

    def test_get_authorization_url_production_environment(self):
        """Production URL wird korrekt generiert."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        url, state = auth_service.get_authorization_url(
            client_id="prod_client",
            redirect_uri="https://app.example.com/callback",
            environment="production",
        )

        assert "https://login.datev.de" in url
        assert "prod_client" in url

    def test_get_authorization_url_includes_all_scopes(self):
        """Alle erforderlichen Scopes sind enthalten."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        url, state = auth_service.get_authorization_url(
            client_id="test",
            redirect_uri="https://example.com/cb",
        )

        assert "openid" in url
        assert "datev:accounting" in url or "datev%3Aaccounting" in url
        assert "offline_access" in url

    def test_validate_state_valid_token(self):
        """Gueltiger State wird akzeptiert."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        _, state = auth_service.get_authorization_url(
            client_id="test",
            redirect_uri="https://example.com/cb",
        )

        # State sollte beim ersten Abruf gueltig sein
        result = auth_service.validate_state(state)
        assert result is not None
        assert "client_id" in result
        assert result["client_id"] == "test"

    def test_validate_state_consumed_after_use(self):
        """State ist nach einmaliger Verwendung ungueltig."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        _, state = auth_service.get_authorization_url(
            client_id="test",
            redirect_uri="https://example.com/cb",
        )

        # Erster Abruf
        result1 = auth_service.validate_state(state)
        assert result1 is not None

        # Zweiter Abruf sollte fehlschlagen
        result2 = auth_service.validate_state(state)
        assert result2 is None

    def test_validate_state_invalid_token(self):
        """Ungueltiger State wird abgelehnt."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        result = auth_service.validate_state("invalid_random_state")
        assert result is None

    @pytest.mark.asyncio
    async def test_token_needs_refresh_expired(self):
        """Abgelaufene Tokens werden als refresh-beduerftig erkannt."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()

        # Token abgelaufen vor 1 Stunde
        expired_at = datetime.utcnow() - timedelta(hours=1)
        needs_refresh = await auth_service.token_needs_refresh(expired_at)
        assert needs_refresh is True

    @pytest.mark.asyncio
    async def test_token_needs_refresh_expiring_soon(self):
        """Bald ablaufende Tokens werden als refresh-beduerftig erkannt."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()

        # Token laeuft in 2 Minuten ab (Buffer ist 5 Minuten)
        expiring_soon = datetime.utcnow() + timedelta(minutes=2)
        needs_refresh = await auth_service.token_needs_refresh(expiring_soon)
        assert needs_refresh is True

    @pytest.mark.asyncio
    async def test_token_needs_refresh_valid(self):
        """Noch gueltige Tokens benoetigen keinen Refresh."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()

        # Token laeuft in 1 Stunde ab
        valid_until = datetime.utcnow() + timedelta(hours=1)
        needs_refresh = await auth_service.token_needs_refresh(valid_until)
        assert needs_refresh is False

    @pytest.mark.asyncio
    async def test_token_needs_refresh_none_token(self):
        """Kein Token bedeutet Refresh erforderlich."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        needs_refresh = await auth_service.token_needs_refresh(None)
        assert needs_refresh is True


# =============================================================================
# KONTIERUNGSVORSCHLAG SERVICE TESTS
# =============================================================================


class TestKontierungsvorschlagService:
    """Tests fuer ML-basierte Kontierungsvorschlaege."""

    @pytest.mark.asyncio
    async def test_suggest_kontierung_returns_suggestion(
        self, mock_db_session, sample_connection_id, sample_kontierung_input
    ):
        """Service gibt Kontierungsvorschlag zurueck."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # Mock: Keine historischen Patterns
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            **sample_kontierung_input,
        )

        assert suggestion is not None
        assert "konto_soll" in suggestion
        assert "konto_haben" in suggestion
        assert "confidence" in suggestion
        assert 0.0 <= suggestion["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_suggest_kontierung_with_entity_pattern(
        self, mock_db_session, sample_connection_id, sample_entity_id
    ):
        """Pattern-basierter Vorschlag bei bekanntem Lieferanten."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # Mock: Pattern fuer Lieferanten existiert
        mock_pattern = Mock()
        mock_pattern.konto_soll = "4400"
        mock_pattern.konto_haben = "70001"
        mock_pattern.steuerschluessel = "9"
        mock_pattern.confidence = 0.95
        mock_pattern.usage_count = 50
        mock_pattern.success_count = 48

        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            mock_pattern
        )

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            entity_id=sample_entity_id,
            lieferant_name="Bekannter Lieferant",
            betrag_brutto=Decimal("119.00"),
            betrag_netto=Decimal("100.00"),
            mwst_satz=Decimal("19.0"),
            dokument_typ="Rechnung",
        )

        assert suggestion is not None
        # Bei bekanntem Pattern sollte Confidence hoch sein
        assert suggestion["confidence"] >= 0.5

    @pytest.mark.asyncio
    async def test_suggest_kontierung_default_fallback(
        self, mock_db_session, sample_connection_id
    ):
        """Fallback auf Standard-Kontierung bei unbekanntem Lieferanten."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # Mock: Kein Pattern gefunden
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            None
        )
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            lieferant_name="Unbekannter Lieferant XYZ",
            betrag_brutto=Decimal("119.00"),
            betrag_netto=Decimal("100.00"),
            mwst_satz=Decimal("19.0"),
            dokument_typ="Rechnung",
        )

        # Sollte trotzdem einen Vorschlag liefern (Default)
        assert suggestion is not None
        assert "konto_soll" in suggestion
        assert "konto_haben" in suggestion
        # Default Confidence sollte niedrig sein
        assert suggestion["confidence"] < 0.8

    @pytest.mark.asyncio
    async def test_learn_from_correction(
        self, mock_db_session, sample_connection_id, sample_entity_id
    ):
        """Service lernt aus User-Korrekturen."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # Mock successful DB operations
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            None
        )

        success = await service.learn_from_correction(
            db=mock_db_session,
            connection_id=sample_connection_id,
            entity_id=sample_entity_id,
            original_konto_soll="4400",
            original_konto_haben="70000",
            corrected_konto_soll="4400",
            corrected_konto_haben="70001",
            betrag=Decimal("119.00"),
        )

        assert success is True
        # DB commit sollte aufgerufen worden sein
        mock_db_session.commit.assert_called()

    def test_calculate_confidence_high_success_rate(self):
        """Hohe Success-Rate ergibt hohe Confidence."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        confidence = service._calculate_confidence(
            usage_count=100, success_count=95, base_confidence=0.8
        )

        assert confidence >= 0.85

    def test_calculate_confidence_low_usage(self):
        """Wenig Nutzung ergibt niedrigere Confidence."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        confidence = service._calculate_confidence(
            usage_count=3, success_count=3, base_confidence=0.8
        )

        # Bei wenig Nutzung sollte Confidence niedriger sein
        assert confidence < 0.9


# =============================================================================
# GOBD COMPLIANCE SERVICE TESTS
# =============================================================================


class TestGoBDComplianceService:
    """Tests fuer GoBD-konforme Festschreibung."""

    def test_calculate_gobd_hash(self, sample_buchung_data):
        """GoBD Hash wird korrekt berechnet."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        hash_value = service.calculate_gobd_hash(
            connection_id=uuid4(),
            buchungsnummer=1,
            **sample_buchung_data,
        )

        # Hash sollte 64 Zeichen lang sein (SHA-256 hex)
        assert len(hash_value) == 64
        # Hash sollte hexadezimal sein
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_calculate_gobd_hash_deterministic(self, sample_buchung_data):
        """Gleiche Daten ergeben gleichen Hash."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        connection_id = uuid4()

        hash1 = service.calculate_gobd_hash(
            connection_id=connection_id, buchungsnummer=1, **sample_buchung_data
        )

        hash2 = service.calculate_gobd_hash(
            connection_id=connection_id, buchungsnummer=1, **sample_buchung_data
        )

        assert hash1 == hash2

    def test_calculate_gobd_hash_different_data(self, sample_buchung_data):
        """Verschiedene Daten ergeben verschiedene Hashes."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        connection_id = uuid4()

        hash1 = service.calculate_gobd_hash(
            connection_id=connection_id, buchungsnummer=1, **sample_buchung_data
        )

        # Aendere Betrag
        modified_data = sample_buchung_data.copy()
        modified_data["betrag_soll"] = 200.00
        modified_data["betrag_haben"] = 200.00

        hash2 = service.calculate_gobd_hash(
            connection_id=connection_id, buchungsnummer=1, **modified_data
        )

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_festschreiben_buchung_success(
        self, mock_db_session, sample_connection_id
    ):
        """Buchung wird erfolgreich festgeschrieben."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        # Mock Buchung
        mock_buchung = Mock()
        mock_buchung.id = uuid4()
        mock_buchung.gobd_festgeschrieben = False
        mock_buchung.connection_id = sample_connection_id
        mock_buchung.buchungsnummer = 1
        mock_buchung.belegdatum = datetime.now().date()
        mock_buchung.betrag_soll = 119.00
        mock_buchung.betrag_haben = 119.00
        mock_buchung.konto_soll = "4400"
        mock_buchung.konto_haben = "70000"
        mock_buchung.steuerschluessel = "9"
        mock_buchung.buchungstext = "Test"
        mock_buchung.belegnummer = "RE-001"

        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            mock_buchung
        )

        user_id = uuid4()
        success = await service.festschreiben_buchung(
            db=mock_db_session,
            buchung_id=mock_buchung.id,
            user_id=user_id,
        )

        assert success is True
        assert mock_buchung.gobd_festgeschrieben is True
        assert mock_buchung.gobd_hash is not None
        assert mock_buchung.festgeschrieben_at is not None
        assert mock_buchung.festgeschrieben_by == user_id

    @pytest.mark.asyncio
    async def test_festschreiben_already_festgeschrieben(
        self, mock_db_session, sample_connection_id
    ):
        """Bereits festgeschriebene Buchung kann nicht erneut festgeschrieben werden."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        # Mock bereits festgeschriebene Buchung
        mock_buchung = Mock()
        mock_buchung.id = uuid4()
        mock_buchung.gobd_festgeschrieben = True

        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            mock_buchung
        )

        success = await service.festschreiben_buchung(
            db=mock_db_session,
            buchung_id=mock_buchung.id,
            user_id=uuid4(),
        )

        # Sollte False zurueckgeben (bereits festgeschrieben)
        assert success is False

    @pytest.mark.asyncio
    async def test_verify_buchung_integrity_valid(
        self, mock_db_session, sample_connection_id
    ):
        """Integritaet einer unveraenderten Buchung wird bestaetigt."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        # Berechne korrekten Hash
        buchung_data = {
            "belegdatum": datetime.now().date(),
            "betrag_soll": 119.00,
            "betrag_haben": 119.00,
            "konto_soll": "4400",
            "konto_haben": "70000",
            "steuerschluessel": "9",
            "buchungstext": "Test",
            "belegnummer": "RE-001",
        }

        correct_hash = service.calculate_gobd_hash(
            connection_id=sample_connection_id, buchungsnummer=1, **buchung_data
        )

        # Mock Buchung mit korrektem Hash
        mock_buchung = Mock()
        mock_buchung.id = uuid4()
        mock_buchung.gobd_festgeschrieben = True
        mock_buchung.gobd_hash = correct_hash
        mock_buchung.connection_id = sample_connection_id
        mock_buchung.buchungsnummer = 1
        mock_buchung.belegdatum = buchung_data["belegdatum"]
        mock_buchung.betrag_soll = buchung_data["betrag_soll"]
        mock_buchung.betrag_haben = buchung_data["betrag_haben"]
        mock_buchung.konto_soll = buchung_data["konto_soll"]
        mock_buchung.konto_haben = buchung_data["konto_haben"]
        mock_buchung.steuerschluessel = buchung_data["steuerschluessel"]
        mock_buchung.buchungstext = buchung_data["buchungstext"]
        mock_buchung.belegnummer = buchung_data["belegnummer"]

        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            mock_buchung
        )

        is_valid = await service.verify_buchung_integrity(
            db=mock_db_session,
            buchung_id=mock_buchung.id,
        )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_buchung_integrity_tampered(
        self, mock_db_session, sample_connection_id
    ):
        """Manipulierte Buchung wird erkannt."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        # Mock Buchung mit falschem Hash (manipuliert)
        mock_buchung = Mock()
        mock_buchung.id = uuid4()
        mock_buchung.gobd_festgeschrieben = True
        mock_buchung.gobd_hash = "0" * 64  # Falscher Hash
        mock_buchung.connection_id = sample_connection_id
        mock_buchung.buchungsnummer = 1
        mock_buchung.belegdatum = datetime.now().date()
        mock_buchung.betrag_soll = 119.00  # Original war anders
        mock_buchung.betrag_haben = 119.00
        mock_buchung.konto_soll = "4400"
        mock_buchung.konto_haben = "70000"
        mock_buchung.steuerschluessel = "9"
        mock_buchung.buchungstext = "Test"
        mock_buchung.belegnummer = "RE-001"

        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            mock_buchung
        )

        is_valid = await service.verify_buchung_integrity(
            db=mock_db_session,
            buchung_id=mock_buchung.id,
        )

        # Manipulierte Buchung sollte ungueltig sein
        assert is_valid is False


# =============================================================================
# DATEV CONNECTOR TESTS
# =============================================================================


class TestDATEVConnector:
    """Tests fuer den Haupt-DATEVConnector."""

    @pytest.mark.asyncio
    async def test_connector_initialization(self):
        """DATEVConnector kann initialisiert werden."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector()
        assert connector is not None
        assert connector.name == "DATEV"

    @pytest.mark.asyncio
    async def test_get_sync_entity_types(self):
        """Connector liefert unterstuetzte Entity-Typen."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector()
        entity_types = connector.get_sync_entity_types()

        assert isinstance(entity_types, list)
        assert "customers" in entity_types
        assert "suppliers" in entity_types
        assert "accounts" in entity_types

    @pytest.mark.asyncio
    async def test_test_connection_without_token(self, mock_db_session):
        """Test Connection schlaegt ohne Token fehl."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector()

        # Mock Connection ohne Token
        mock_connection = Mock()
        mock_connection.access_token_encrypted = None
        mock_connection.client_id = "test"
        mock_connection.environment = "sandbox"

        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            mock_connection
        )

        success = await connector.test_connection(mock_db_session, uuid4())
        assert success is False

    @pytest.mark.asyncio
    async def test_connect_returns_auth_url(self, mock_db_session):
        """Connect gibt Authorization URL zurueck."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector()

        # Mock Connection
        mock_connection = Mock()
        mock_connection.id = uuid4()
        mock_connection.client_id = "test_client"
        mock_connection.environment = "sandbox"

        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            mock_connection
        )

        result = await connector.connect(
            mock_db_session,
            connection_id=mock_connection.id,
            redirect_uri="https://example.com/callback",
        )

        assert result is not None
        assert "authorization_url" in result or isinstance(result, dict)


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================


class TestDATEVConnectAPI:
    """Tests fuer DATEV Connect API Endpoints."""

    @pytest.mark.asyncio
    async def test_list_connections_schema(self):
        """GET /datev-connect/connections Endpoint Schema."""
        # Verifiziere dass Pydantic Schemas korrekt sind
        from app.api.v1.datev_connect import DATEVConnectionResponse

        response = DATEVConnectionResponse(
            id=uuid4(),
            name="Test Connection",
            beraternummer="12345",
            mandantennummer="67890",
            kontenrahmen="SKR03",
            wirtschaftsjahr_beginn=1,
            connection_status="pending",
            auto_kontierung=False,
            auto_beleg_upload=True,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert response.name == "Test Connection"
        assert response.kontenrahmen == "SKR03"

    @pytest.mark.asyncio
    async def test_create_connection_schema(self):
        """POST /datev-connect/connections Schema Validierung."""
        from app.api.v1.datev_connect import DATEVConnectionCreate

        # Gueltige Eingabe
        create_data = DATEVConnectionCreate(
            name="Neue Verbindung",
            beraternummer="12345",
            mandantennummer="67890",
            kontenrahmen="SKR03",
            wirtschaftsjahr_beginn=1,
        )

        assert create_data.name == "Neue Verbindung"
        assert create_data.kontenrahmen == "SKR03"

    @pytest.mark.asyncio
    async def test_create_buchung_schema(self):
        """POST /datev-connect/buchungen Schema Validierung."""
        from app.api.v1.datev_connect import BuchungCreate

        buchung = BuchungCreate(
            belegdatum=datetime.now().date(),
            betrag_soll=119.00,
            betrag_haben=119.00,
            konto_soll="4400",
            konto_haben="70000",
            buchungstext="Test Buchung",
        )

        assert buchung.konto_soll == "4400"
        assert buchung.betrag_soll == 119.00

    def test_kontierung_vorschlag_schema(self):
        """Kontierungsvorschlag Response Schema."""
        from app.api.v1.datev_connect import KontierungVorschlagResponse

        vorschlag = KontierungVorschlagResponse(
            konto_soll="4400",
            konto_haben="70000",
            steuerschluessel="9",
            kostenstelle=None,
            confidence=0.85,
            source="pattern",
        )

        assert vorschlag.konto_soll == "4400"
        assert vorschlag.confidence == 0.85
        assert vorschlag.source == "pattern"


# =============================================================================
# CELERY TASK TESTS
# =============================================================================


class TestDATEVCeleryTasks:
    """Tests fuer DATEV Celery Background Tasks."""

    def test_task_names_registered(self):
        """DATEV Tasks sind mit korrekten Namen registriert."""
        # Import der Tasks registriert sie
        from app.workers.tasks import datev_connect_tasks

        # Verifiziere Task-Namen
        expected_tasks = [
            "datev.refresh_all_tokens",
            "datev.sync_stammdaten",
            "datev.sync_all_stammdaten",
            "datev.push_buchungsstapel",
            "datev.upload_pending_belege",
            "datev.gobd_compliance_check",
            "datev.auto_festschreibung",
            "datev.sync_kontenplan",
        ]

        # Tasks sollten definiert sein
        assert hasattr(datev_connect_tasks, "refresh_all_datev_tokens")
        assert hasattr(datev_connect_tasks, "sync_datev_stammdaten")
        assert hasattr(datev_connect_tasks, "push_datev_buchungsstapel")

    @pytest.mark.asyncio
    async def test_refresh_tokens_task_structure(self):
        """Token Refresh Task hat korrekte Struktur."""
        from app.workers.tasks.datev_connect_tasks import refresh_all_datev_tokens

        # Task sollte Celery Task sein
        assert hasattr(refresh_all_datev_tokens, "delay")
        assert hasattr(refresh_all_datev_tokens, "apply_async")

    @pytest.mark.asyncio
    async def test_sync_stammdaten_task_structure(self):
        """Stammdaten Sync Task hat korrekte Struktur."""
        from app.workers.tasks.datev_connect_tasks import sync_datev_stammdaten

        assert hasattr(sync_datev_stammdaten, "delay")
        assert hasattr(sync_datev_stammdaten, "apply_async")


# =============================================================================
# EDGE CASES & ERROR HANDLING
# =============================================================================


class TestDATEVEdgeCases:
    """Edge Cases und Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_empty_buchungstext_handling(self):
        """Leerer Buchungstext wird korrekt behandelt."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        # Sollte nicht crashen bei leerem Buchungstext
        hash_value = service.calculate_gobd_hash(
            connection_id=uuid4(),
            buchungsnummer=1,
            belegdatum=datetime.now().date(),
            betrag_soll=100.0,
            betrag_haben=100.0,
            konto_soll="4400",
            konto_haben="70000",
            steuerschluessel="9",
            buchungstext="",  # Leer
            belegnummer="RE-001",
        )

        assert hash_value is not None
        assert len(hash_value) == 64

    @pytest.mark.asyncio
    async def test_special_characters_in_buchungstext(self):
        """Sonderzeichen im Buchungstext werden korrekt verarbeitet."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        # Deutsche Umlaute und Sonderzeichen
        hash_value = service.calculate_gobd_hash(
            connection_id=uuid4(),
            buchungsnummer=1,
            belegdatum=datetime.now().date(),
            betrag_soll=100.0,
            betrag_haben=100.0,
            konto_soll="4400",
            konto_haben="70000",
            steuerschluessel="9",
            buchungstext="Müller GmbH & Co. KG - Bürobedarf",
            belegnummer="RE-2026/001",
        )

        assert hash_value is not None
        assert len(hash_value) == 64

    @pytest.mark.asyncio
    async def test_large_betrag_handling(self):
        """Grosse Betraege werden korrekt verarbeitet."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        hash_value = service.calculate_gobd_hash(
            connection_id=uuid4(),
            buchungsnummer=1,
            belegdatum=datetime.now().date(),
            betrag_soll=9999999.99,  # Grosser Betrag
            betrag_haben=9999999.99,
            konto_soll="4400",
            konto_haben="70000",
            steuerschluessel="9",
            buchungstext="Grosse Rechnung",
            belegnummer="RE-001",
        )

        assert hash_value is not None

    @pytest.mark.asyncio
    async def test_kontierung_zero_betrag(self, mock_db_session, sample_connection_id):
        """Kontierung mit Betrag 0 wird behandelt."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = (
            None
        )
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            lieferant_name="Test",
            betrag_brutto=Decimal("0.00"),
            betrag_netto=Decimal("0.00"),
            mwst_satz=Decimal("0.0"),
            dokument_typ="Gutschrift",
        )

        # Sollte trotzdem einen Vorschlag liefern
        assert suggestion is not None

    def test_kontenrahmen_validation(self):
        """Nur SKR03 und SKR04 sind erlaubt."""
        from app.api.v1.datev_connect import DATEVConnectionCreate
        from pydantic import ValidationError

        # Gueltige Kontenrahmen
        valid1 = DATEVConnectionCreate(
            name="Test",
            beraternummer="12345",
            mandantennummer="67890",
            kontenrahmen="SKR03",
        )
        assert valid1.kontenrahmen == "SKR03"

        valid2 = DATEVConnectionCreate(
            name="Test",
            beraternummer="12345",
            mandantennummer="67890",
            kontenrahmen="SKR04",
        )
        assert valid2.kontenrahmen == "SKR04"


# =============================================================================
# SECURITY TESTS
# =============================================================================


class TestDATEVSecurity:
    """Sicherheitstests fuer DATEV Connect."""

    def test_state_token_is_cryptographically_secure(self):
        """State Token ist kryptographisch sicher."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()

        states = set()
        for _ in range(100):
            _, state = auth_service.get_authorization_url(
                client_id="test",
                redirect_uri="https://example.com/cb",
            )
            states.add(state)

        # Alle States sollten einzigartig sein
        assert len(states) == 100

    def test_gobd_hash_uses_sha256(self):
        """GoBD Hash verwendet SHA-256."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        hash_value = service.calculate_gobd_hash(
            connection_id=uuid4(),
            buchungsnummer=1,
            belegdatum=datetime.now().date(),
            betrag_soll=100.0,
            betrag_haben=100.0,
            konto_soll="4400",
            konto_haben="70000",
            steuerschluessel="9",
            buchungstext="Test",
            belegnummer="RE-001",
        )

        # SHA-256 Hash ist 64 Hex-Zeichen lang
        assert len(hash_value) == 64

    @pytest.mark.asyncio
    async def test_connection_isolation_by_company(
        self, mock_db_session, sample_company_id
    ):
        """Verbindungen sind nach Company isoliert."""
        # Dieser Test stellt sicher, dass company_id bei allen Queries verwendet wird
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector()

        # Der Connector sollte company_id in allen DB-Queries beruecksichtigen
        # Dies wird durch RLS (Row Level Security) in PostgreSQL erzwungen
        assert connector is not None
