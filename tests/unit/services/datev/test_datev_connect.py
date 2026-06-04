# -*- coding: utf-8 -*-
"""
Umfassende Unit Tests fuer DATEV Connect Services.

Testet alle Komponenten der DATEVconnect Integration gegen die ECHTE Service-API:
- DATEVAuthService - OAuth2 Flow
- DATEVConnector - ERP Connector
- KontierungsvorschlagService - ML-basierte Kontierung
- GoBDComplianceService - Festschreibung und Compliance

Feinpoliert und durchdacht - Enterprise Test Coverage.

Historie: Diese Tests waren urspruenglich gegen eine erfundene API geschrieben
und durch einen Prod-Import-Bug (encrypt_value/decrypt_value fehlten in
app.core.encryption) blockiert. Der Bug ist behoben (Aliase ergaenzt); die Tests
pruefen jetzt den TATSAECHLICHEN Vertrag der Services.

Mock-Hinweis (AsyncSession):
`db.execute(...)` ist eine Coroutine (await), das zurueckgegebene Result-Objekt
ist jedoch SYNCHRON (.scalar_one_or_none()/.scalars().all()/.first()). Wuerde man
`AsyncMock()` direkt als Session nutzen, lieferten dessen Child-Mocks Coroutinen
statt Werten ('coroutine' object has no attribute ...). Deshalb werden Result-
Mocks ueber die Helper unten als MagicMock erstellt und per side_effect/return_value
an `db.execute` gehaengt.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID, uuid4

import pytest

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.datev]


# =============================================================================
# ECHTER PROD-BUG: KontierungsvorschlagService <-> DATEVBuchung-Modell
# =============================================================================
#
# KontierungsvorschlagService referenziert in seinen ORM-Queries und beim
# Schreiben Spalten, die das Modell app.db.models.DATEVBuchung NICHT besitzt:
#   - kontierung_service.py:459-461,467 (_suggest_from_history) sowie
#     _suggest_from_patterns / get_similar_buchungen nutzen
#     models.DATEVBuchung.konto / .gegenkonto / .bu_schluessel / .umsatz /
#     .soll_haben
#   - learn_from_correction setzt buchung.konto / .gegenkonto / .user_korrektur /
#     .original_suggestion_konto
# Das Modell hat stattdessen: konto_soll / konto_haben / steuerschluessel /
# betrag_soll / betrag_haben (und gobd_festgeschrieben statt ist_festgeschrieben).
#
# Folge: select(models.DATEVBuchung.konto, ...) wirft bereits beim Aufbau der
# Query `AttributeError: type object 'DATEVBuchung' has no attribute 'konto'`.
# suggest_kontierung() crasht damit zur Laufzeit IMMER, sobald die History-/
# Pattern-Strategie erreicht wird.
#
# Die folgenden Tests beschreiben das KORREKTE erwartete Verhalten (ein Vorschlag
# wird zurueckgegeben). Da der Prod-Code dies verletzt, werden sie NICHT kuenstlich
# gruen gemacht, sondern mit strict-xfail markiert. Behebung gehoert in den
# Prod-Code (Service-Spaltennamen an das Modell angleichen ODER Modell-Properties
# ergaenzen). Sobald gefixt, schlaegt strict-xfail als XPASS->Failure an und
# signalisiert, den Marker zu entfernen.
_xfail_kontierung_model_mismatch = pytest.mark.xfail(
    strict=True,
    raises=AttributeError,
    reason=(
        "echter Bug: KontierungsvorschlagService nutzt nicht-existente "
        "DATEVBuchung-Spalten (konto/gegenkonto/bu_schluessel/umsatz/soll_haben "
        "statt konto_soll/konto_haben/steuerschluessel/betrag_*); "
        "kontierung_service.py:459 -> AttributeError beim select()-Aufbau, "
        "suggest_kontierung crasht zur Laufzeit."
    ),
)


# =============================================================================
# MOCK-HELPER fuer AsyncSession Result-Objekte
# =============================================================================


def _result_scalar_one_or_none(value: object) -> MagicMock:
    """Result-Mock mit .scalar_one_or_none() -> value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _result_first(value: object) -> MagicMock:
    """Result-Mock mit .first() -> value (z.B. aggregierte Zeile oder None)."""
    result = MagicMock()
    result.first.return_value = value
    return result


def _result_scalars_all(items: List[object]) -> MagicMock:
    """Result-Mock mit .scalars().all() -> items."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _result_scalar(value: object) -> MagicMock:
    """Result-Mock mit .scalar() -> value (z.B. func.count)."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db_session():
    """
    Mock AsyncSession fuer Datenbank-Tests.

    db.execute ist ein AsyncMock (awaitbar). Tests setzen das/die Result-Objekt(e)
    ueber db.execute.return_value oder db.execute.side_effect (Liste von
    _result_*-Helpern in Aufrufreihenfolge des Services).
    """
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()  # add ist synchron in SQLAlchemy 2.0 async
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
def sample_buchung() -> Mock:
    """
    Sample DATEVBuchung-Mock fuer GoBD-Hash-Tests.

    Felder entsprechen dem _BuchungProtocol des echten GoBDComplianceService
    (buchungs_guid, umsatz, soll_haben, konto, gegenkonto, bu_schluessel,
    belegdatum, belegfeld_1, buchungstext).
    """
    buchung = Mock()
    buchung.buchungs_guid = "GUID-0001"
    buchung.umsatz = Decimal("119.00")
    buchung.soll_haben = "S"
    buchung.konto = "4400"
    buchung.gegenkonto = "1600"
    buchung.bu_schluessel = "9"
    buchung.belegdatum = datetime(2026, 1, 15).date()
    buchung.belegfeld_1 = "RE-2026-001"
    buchung.buchungstext = "Wareneingang Test GmbH"
    return buchung


@pytest.fixture
def sample_kontierung_input():
    """
    Sample KontierungsInput fuer Tests.

    Verwendet die ECHTE KontierungsInput-Dataklasse des Services
    (entity_name, betrag_brutto, betrag_netto, mwst_satz, dokument_typ, richtung).
    """
    from app.services.datev.connect.kontierung_service import KontierungsInput

    return KontierungsInput(
        entity_name="Test GmbH",
        entity_vat_id="DE123456789",
        betrag_brutto=Decimal("119.00"),
        betrag_netto=Decimal("100.00"),
        mwst_satz=Decimal("19.0"),
        dokument_typ="invoice",
        richtung="incoming",
    )


# =============================================================================
# DATEV AUTH SERVICE TESTS
# =============================================================================


class TestDATEVAuthService:
    """Tests fuer DATEVAuthService - OAuth2 Flow."""

    def test_get_authorization_url_generates_valid_url(self):
        """Authorization URL wird korrekt generiert (sandbox)."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        url, state = auth_service.get_authorization_url(
            client_id="test_client_id",
            redirect_uri="https://app.example.com/callback",
            environment="sandbox",
        )

        assert "https://login.sandbox.datev.de" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=https://app.example.com/callback" in url
        assert f"state={state}" in url
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
        assert "client_id=prod_client" in url

    def test_get_authorization_url_includes_all_scopes(self):
        """Alle erforderlichen Scopes (DATEV_SCOPES) sind enthalten."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        url, _ = auth_service.get_authorization_url(
            client_id="test",
            redirect_uri="https://example.com/cb",
        )

        # Scopes werden raw (mit Leerzeichen) in den scope-Parameter geschrieben
        assert "openid" in url
        assert "datev:accounting" in url
        assert "datev:master-data" in url
        assert "datev:documents" in url
        assert "offline_access" in url

    def test_validate_state_valid_token(self):
        """Gueltiger State wird akzeptiert und liefert Metadaten."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        _, state = auth_service.get_authorization_url(
            client_id="test",
            redirect_uri="https://example.com/cb",
        )

        result = auth_service.validate_state(state)
        assert result is not None
        assert result["client_id"] == "test"
        assert result["redirect_uri"] == "https://example.com/cb"

    def test_validate_state_consumed_after_use(self):
        """State ist nach einmaliger Verwendung ungueltig (CSRF One-Time-Use)."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        _, state = auth_service.get_authorization_url(
            client_id="test",
            redirect_uri="https://example.com/cb",
        )

        # Erster Abruf gueltig
        assert auth_service.validate_state(state) is not None
        # Zweiter Abruf schlaegt fehl (verbraucht)
        assert auth_service.validate_state(state) is None

    def test_validate_state_invalid_token(self):
        """Unbekannter State wird abgelehnt."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        assert auth_service.validate_state("invalid_random_state") is None

    @pytest.mark.asyncio
    async def test_token_needs_refresh_expired(self):
        """Abgelaufene Tokens werden als refresh-beduerftig erkannt.

        Hinweis: Der Service vergleicht gegen utc_now() (timezone-aware), daher
        muessen Vergleichszeitpunkte ebenfalls aware (UTC) sein.
        """
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        expired_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert await auth_service.token_needs_refresh(expired_at) is True

    @pytest.mark.asyncio
    async def test_token_needs_refresh_expiring_soon(self):
        """Bald ablaufende Tokens (innerhalb 5-Min-Buffer) brauchen Refresh."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        # Buffer ist TOKEN_REFRESH_BUFFER_MINUTES = 5; 2 Min < Buffer -> Refresh
        expiring_soon = datetime.now(timezone.utc) + timedelta(minutes=2)
        assert await auth_service.token_needs_refresh(expiring_soon) is True

    @pytest.mark.asyncio
    async def test_token_needs_refresh_valid(self):
        """Noch lange gueltige Tokens benoetigen keinen Refresh."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        valid_until = datetime.now(timezone.utc) + timedelta(hours=1)
        assert await auth_service.token_needs_refresh(valid_until) is False

    @pytest.mark.asyncio
    async def test_token_needs_refresh_none_token(self):
        """Fehlender Ablaufzeitpunkt bedeutet Refresh erforderlich."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()
        assert await auth_service.token_needs_refresh(None) is True


# =============================================================================
# KONTIERUNGSVORSCHLAG SERVICE TESTS
#
# Echte API: suggest_kontierung(db, connection_id, input_data: KontierungsInput)
#            -> KontierungsSuggestion (Dataklasse, nicht dict).
# suggest_kontierung ruft intern db.execute ZWEIMAL auf:
#   1) _suggest_from_history -> .first()
#   2) _suggest_from_patterns -> .scalar_one_or_none()
# =============================================================================


class TestKontierungsvorschlagService:
    """Tests fuer ML-basierte Kontierungsvorschlaege."""

    @pytest.mark.asyncio
    async def test_suggest_kontierung_returns_suggestion(
        self, mock_db_session, sample_connection_id, sample_kontierung_input
    ):
        """Service gibt eine KontierungsSuggestion mit gueltiger Konfidenz zurueck."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsSuggestion,
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # 1) Historie: kein Treffer, 2) Pattern: kein Treffer
        mock_db_session.execute.side_effect = [
            _result_first(None),
            _result_scalar_one_or_none(None),
        ]

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            input_data=sample_kontierung_input,
        )

        assert isinstance(suggestion, KontierungsSuggestion)
        assert suggestion.konto
        assert suggestion.gegenkonto
        assert 0.0 <= suggestion.confidence <= 1.0
        # Quelle ist eine der definierten Strategien
        assert suggestion.source in ("rule", "ml", "history", "manual")

    @pytest.mark.asyncio
    async def test_suggest_kontierung_keyword_match_buero(
        self, mock_db_session, sample_connection_id
    ):
        """Keyword-Match erkennt Bueromaterial und schlaegt Buerokonto vor."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsInput,
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()
        # Historie + Pattern leer -> Keyword-Strategie gewinnt
        mock_db_session.execute.side_effect = [
            _result_first(None),
            _result_scalar_one_or_none(None),
        ]

        input_data = KontierungsInput(
            entity_name="Buerobedarf Mueller",
            stichwort="Toner und Schreibwaren",
            betrag_brutto=Decimal("59.50"),
            mwst_satz=Decimal("19.0"),
            dokument_typ="invoice",
            richtung="incoming",
        )

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            input_data=input_data,
        )

        # SKR03: Buerokosten -> Konto 4930 (Gegenkonto Verbindlichkeiten 1600)
        assert suggestion.konto == "4930"
        assert suggestion.gegenkonto == "1600"
        assert suggestion.source == "rule"
        # Keyword-Vorschlag hat hoehere Konfidenz als der reine Default (0.3)
        assert suggestion.confidence > 0.3

    @pytest.mark.asyncio
    async def test_suggest_kontierung_default_fallback(
        self, mock_db_session, sample_connection_id
    ):
        """Fallback auf Standard-Kontierung bei unbekanntem Lieferanten."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsInput,
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()
        mock_db_session.execute.side_effect = [
            _result_first(None),
            _result_scalar_one_or_none(None),
        ]

        input_data = KontierungsInput(
            entity_name="Unbekannter Lieferant XYZ",
            betrag_brutto=Decimal("119.00"),
            mwst_satz=Decimal("19.0"),
            dokument_typ="invoice",
            richtung="incoming",
        )

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            input_data=input_data,
        )

        # SKR03 Standard incoming: Aufwand 4400 / Verbindlichkeiten 1600
        assert suggestion.konto == "4400"
        assert suggestion.gegenkonto == "1600"
        # Default-Kontierung ist der Fallback (source "manual", Konfidenz niedrig)
        assert suggestion.source == "manual"
        assert suggestion.confidence < 0.8

    @pytest.mark.asyncio
    async def test_suggest_kontierung_uses_history_pattern(
        self, mock_db_session, sample_connection_id, sample_kontierung_input
    ):
        """Mehrfache historische Treffer ergeben einen History-Vorschlag mit hoher Konfidenz."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # _suggest_from_history liest row als Tuple-aehnlich:
        # row[0]=konto, row[1]=gegenkonto, row[2]=bu_schluessel, row[3]=count
        history_row = ("4400", "70001", "9", 5)
        mock_db_session.execute.side_effect = [
            _result_first(history_row),
            _result_scalar_one_or_none(None),  # kein Pattern
        ]

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            input_data=sample_kontierung_input,
        )

        assert suggestion.source == "history"
        assert suggestion.konto == "4400"
        assert suggestion.gegenkonto == "70001"
        # Konfidenz = min(0.95, 0.5 + count*0.1) = min(0.95, 1.0) = 0.95
        assert suggestion.confidence == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_learn_from_correction(
        self, mock_db_session, sample_connection_id
    ):
        """Service lernt aus User-Korrektur und committed die Aenderung."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # Buchung wird gefunden (Pattern-Update entfaellt, da kein input_data)
        mock_buchung = Mock()
        mock_buchung.konto = "4400"
        mock_buchung.gegenkonto = "70000"
        mock_db_session.execute.return_value = _result_scalar_one_or_none(mock_buchung)

        success = await service.learn_from_correction(
            db=mock_db_session,
            connection_id=sample_connection_id,
            buchung_id=uuid4(),
            corrected_konto="4400",
            corrected_gegenkonto="70001",
            corrected_bu_schluessel="9",
        )

        assert success is True
        # Korrektur wird auf den echten DATEVBuchung-Spalten persistiert
        assert mock_buchung.konto_soll == "4400"
        assert mock_buchung.konto_haben == "70001"
        assert mock_buchung.steuerschluessel == "9"
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_learn_from_correction_buchung_not_found(
        self, mock_db_session, sample_connection_id
    ):
        """Korrektur ohne passende Buchung committed trotzdem (kein Crash)."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()
        mock_db_session.execute.return_value = _result_scalar_one_or_none(None)

        success = await service.learn_from_correction(
            db=mock_db_session,
            connection_id=sample_connection_id,
            buchung_id=uuid4(),
            corrected_konto="4930",
            corrected_gegenkonto="1600",
        )

        assert success is True
        mock_db_session.commit.assert_awaited()

    def test_tax_code_from_mwst_satz(self):
        """Steuerschluessel wird korrekt aus dem MwSt-Satz abgeleitet."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()

        # 19% -> "9", 7% -> "8", None -> Standard "9"
        assert service._get_tax_code(Decimal("19.0")) == "9"
        assert service._get_tax_code(Decimal("7.0")) == "8"
        assert service._get_tax_code(None) == "9"


# =============================================================================
# GOBD COMPLIANCE SERVICE TESTS
#
# Echte API: _calculate_buchung_hash(buchung) (SHA-256 ueber GoBD-Felder),
#            verify_buchung_integrity(db, buchung_id) -> Tuple[bool, Optional[str]],
#            check_buchung_modifiable(db, buchung_id) -> Tuple[bool, Optional[str]].
# Beide DB-Methoden lesen die Buchung via .scalar_one_or_none().
# =============================================================================


class TestGoBDComplianceService:
    """Tests fuer GoBD-konforme Festschreibung."""

    def test_calculate_buchung_hash(self, sample_buchung):
        """GoBD Hash (SHA-256) wird ueber die Buchungsfelder berechnet."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        hash_value = service._calculate_buchung_hash(sample_buchung)

        # SHA-256 hex = 64 Zeichen, nur 0-9a-f
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_calculate_buchung_hash_deterministic(self, sample_buchung):
        """Gleiche Buchungsdaten ergeben den gleichen Hash."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        assert (
            service._calculate_buchung_hash(sample_buchung)
            == service._calculate_buchung_hash(sample_buchung)
        )

    def test_calculate_buchung_hash_different_data(self, sample_buchung):
        """Geaenderter Umsatz fuehrt zu abweichendem Hash."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        hash1 = service._calculate_buchung_hash(sample_buchung)

        sample_buchung.umsatz = Decimal("200.00")
        hash2 = service._calculate_buchung_hash(sample_buchung)

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_verify_buchung_integrity_valid(self, mock_db_session, sample_buchung):
        """Integritaet einer unveraenderten festgeschriebenen Buchung wird bestaetigt."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        # Korrekten Hash aus den aktuellen Daten berechnen und am Mock setzen
        correct_hash = service._calculate_buchung_hash(sample_buchung)
        sample_buchung.ist_festgeschrieben = True
        sample_buchung.festschreibung_hash = correct_hash
        mock_db_session.execute.return_value = _result_scalar_one_or_none(sample_buchung)

        is_valid, error = await service.verify_buchung_integrity(
            db=mock_db_session,
            buchung_id=uuid4(),
        )

        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_verify_buchung_integrity_tampered(self, mock_db_session, sample_buchung):
        """Manipulierte (Hash-Mismatch) Buchung wird als ungueltig erkannt."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        sample_buchung.ist_festgeschrieben = True
        sample_buchung.festschreibung_hash = "0" * 64  # Falscher Hash
        mock_db_session.execute.return_value = _result_scalar_one_or_none(sample_buchung)

        is_valid, error = await service.verify_buchung_integrity(
            db=mock_db_session,
            buchung_id=uuid4(),
        )

        assert is_valid is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_verify_buchung_integrity_not_festgeschrieben(
        self, mock_db_session, sample_buchung
    ):
        """Nicht-festgeschriebene Buchungen gelten per Definition als integer."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        sample_buchung.ist_festgeschrieben = False
        mock_db_session.execute.return_value = _result_scalar_one_or_none(sample_buchung)

        is_valid, error = await service.verify_buchung_integrity(
            db=mock_db_session,
            buchung_id=uuid4(),
        )

        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_verify_buchung_integrity_not_found(self, mock_db_session):
        """Fehlende Buchung liefert (False, Fehlermeldung)."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        mock_db_session.execute.return_value = _result_scalar_one_or_none(None)

        is_valid, error = await service.verify_buchung_integrity(
            db=mock_db_session,
            buchung_id=uuid4(),
        )

        assert is_valid is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_check_buchung_modifiable_festgeschrieben(
        self, mock_db_session, sample_buchung
    ):
        """Festgeschriebene Buchung darf nicht mehr geaendert werden."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        sample_buchung.ist_festgeschrieben = True
        sample_buchung.festschreibung_datum = datetime(2026, 1, 31)
        sample_buchung.sync_status = "synced"
        mock_db_session.execute.return_value = _result_scalar_one_or_none(sample_buchung)

        modifiable, reason = await service.check_buchung_modifiable(
            db=mock_db_session,
            buchung_id=uuid4(),
        )

        assert modifiable is False
        assert reason is not None

    @pytest.mark.asyncio
    async def test_check_buchung_modifiable_editable(
        self, mock_db_session, sample_buchung
    ):
        """Nicht-festgeschriebene, noch nicht gesyncte Buchung ist aenderbar."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()

        sample_buchung.ist_festgeschrieben = False
        sample_buchung.sync_status = "pending"
        mock_db_session.execute.return_value = _result_scalar_one_or_none(sample_buchung)

        modifiable, reason = await service.check_buchung_modifiable(
            db=mock_db_session,
            buchung_id=uuid4(),
        )

        assert modifiable is True
        assert reason is None


# =============================================================================
# DATEV CONNECTOR TESTS
#
# Echte API: DATEVConnector(config: DATEVConnectionConfig); erbt von ERPConnector.
# Methoden: connect()/test_connection() ohne Args, sync_customers(...),
#           push_buchungsstapel(...), get_kontenplan(...).
# =============================================================================


class TestDATEVConnector:
    """Tests fuer den Haupt-DATEVConnector."""

    def _make_config(self):
        from app.services.datev.connect.datev_connector import DATEVConnectionConfig

        return DATEVConnectionConfig(
            beraternummer="12345",
            mandantennummer="67890",
            client_id="test_client",
            client_secret="test_secret",
            api_environment="sandbox",
            kontenrahmen="SKR03",
        )

    def test_connector_initialization(self):
        """DATEVConnector kann mit DATEVConnectionConfig initialisiert werden."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector(self._make_config())
        assert connector is not None
        # erp_type wird in __post_init__ auf 'datev' gesetzt
        assert connector.erp_type == "datev"
        assert connector.config.beraternummer == "12345"

    def test_connector_uses_sandbox_base_url(self):
        """Sandbox-Umgebung waehlt die Sandbox-API-Basis-URL."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector(self._make_config())
        assert "sandbox" in connector._api_base

    def test_token_needs_refresh_without_token(self):
        """Ohne Access-Token meldet der Connector Refresh-Bedarf."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector(self._make_config())
        # config.access_token ist leer -> Refresh noetig
        assert connector._token_needs_refresh() is True

    def test_validate_buchung_detects_missing_fields(self):
        """Buchungs-Validierung meldet fehlende Pflichtfelder."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector(self._make_config())

        errors = connector._validate_buchung({})
        # Umsatz, Konto, Gegenkonto, Belegdatum und Soll/Haben fehlen
        assert any("Umsatz" in e for e in errors)
        assert any("Konto" in e for e in errors)
        assert any("Gegenkonto" in e for e in errors)
        assert any("Belegdatum" in e for e in errors)
        assert any("Soll/Haben" in e for e in errors)

    def test_validate_buchung_accepts_valid(self):
        """Vollstaendige, gueltige Buchung erzeugt keine Validierungsfehler."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector(self._make_config())

        errors = connector._validate_buchung(
            {
                "umsatz": 119.00,
                "konto": "4400",
                "gegenkonto": "1600",
                "belegdatum": datetime(2026, 1, 15).date(),
                "soll_haben": "S",
            }
        )
        assert errors == []

    @pytest.mark.asyncio
    async def test_push_buchungsstapel_empty(self):
        """Leerer Buchungsstapel wird abgewiesen."""
        from app.services.datev.connect.datev_connector import DATEVConnector

        connector = DATEVConnector(self._make_config())

        success, stapel_id, errors = await connector.push_buchungsstapel([])

        assert success is False
        assert stapel_id is None
        assert errors


# =============================================================================
# API ENDPOINT / PYDANTIC SCHEMA TESTS
# =============================================================================


class TestDATEVConnectAPI:
    """Tests fuer DATEV Connect Pydantic-Schemas."""

    @pytest.mark.asyncio
    async def test_list_connections_schema(self):
        """DATEVConnectionResponse akzeptiert die echten Response-Felder."""
        from app.api.v1.datev_connect import DATEVConnectionResponse

        response = DATEVConnectionResponse(
            id=str(uuid4()),
            name="Test Connection",
            beraternummer="12345",
            mandantennummer="67890",
            wirtschaftsjahr_beginn=1,
            api_environment="sandbox",
            kontenrahmen="SKR03",
            sachkontenlange=4,
            personenkontenlange=5,
            buchungsmodus="manuell",
            gobd_enabled=True,
            festschreibung_automatisch=False,
            connection_status="pending",
            is_active=True,
            created_at=datetime.now().isoformat(),
        )

        assert response.name == "Test Connection"
        assert response.kontenrahmen == "SKR03"

    @pytest.mark.asyncio
    async def test_create_connection_schema(self):
        """DATEVConnectionCreate validiert gueltige Eingaben."""
        from app.api.v1.datev_connect import DATEVConnectionCreate

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
        """BuchungCreate verwendet die echten Felder (umsatz, soll_haben, konto)."""
        from app.api.v1.datev_connect import BuchungCreate

        buchung = BuchungCreate(
            belegdatum=datetime.now().date(),
            umsatz=Decimal("119.00"),
            soll_haben="S",
            konto="4400",
            gegenkonto="1600",
            buchungstext="Test Buchung",
        )

        assert buchung.konto == "4400"
        assert buchung.umsatz == Decimal("119.00")
        assert buchung.soll_haben == "S"

    def test_create_buchung_schema_invalid_soll_haben(self):
        """BuchungCreate erzwingt das Soll/Haben-Pattern ^[SH]$."""
        from pydantic import ValidationError

        from app.api.v1.datev_connect import BuchungCreate

        with pytest.raises(ValidationError):
            BuchungCreate(
                belegdatum=datetime.now().date(),
                umsatz=Decimal("119.00"),
                soll_haben="X",  # ungueltig
                konto="4400",
                gegenkonto="1600",
            )

    def test_kontierung_response_schema(self):
        """KontierungResponse Response-Schema (echter Klassenname)."""
        from app.api.v1.datev_connect import KontierungResponse

        vorschlag = KontierungResponse(
            konto="4400",
            gegenkonto="1600",
            bu_schluessel="9",
            kostenstelle=None,
            confidence=0.85,
            source="rule",
            explanation="Regel-Match",
        )

        assert vorschlag.konto == "4400"
        assert vorschlag.confidence == 0.85
        assert vorschlag.source == "rule"


# =============================================================================
# CELERY TASK TESTS
# =============================================================================


class TestDATEVCeleryTasks:
    """Tests fuer DATEV Celery Background Tasks."""

    def test_tasks_are_registered(self):
        """Die zentralen DATEV-Tasks sind als Funktionen definiert."""
        from app.workers.tasks import datev_connect_tasks

        assert hasattr(datev_connect_tasks, "refresh_all_datev_tokens")
        assert hasattr(datev_connect_tasks, "sync_datev_stammdaten")
        assert hasattr(datev_connect_tasks, "sync_all_datev_stammdaten")
        assert hasattr(datev_connect_tasks, "push_datev_buchungsstapel")
        assert hasattr(datev_connect_tasks, "upload_pending_datev_belege")
        assert hasattr(datev_connect_tasks, "datev_gobd_compliance_check")
        assert hasattr(datev_connect_tasks, "datev_auto_festschreibung")
        assert hasattr(datev_connect_tasks, "sync_datev_kontenplan")

    def test_refresh_tokens_task_structure(self):
        """Token-Refresh-Task ist ein Celery-Task (delay/apply_async vorhanden)."""
        from app.workers.tasks.datev_connect_tasks import refresh_all_datev_tokens

        assert hasattr(refresh_all_datev_tokens, "delay")
        assert hasattr(refresh_all_datev_tokens, "apply_async")
        # Registrierter Task-Name folgt dem Modulpfad-Schema
        assert refresh_all_datev_tokens.name.endswith("refresh_all_datev_tokens")

    def test_sync_stammdaten_task_structure(self):
        """Stammdaten-Sync-Task ist ein Celery-Task."""
        from app.workers.tasks.datev_connect_tasks import sync_datev_stammdaten

        assert hasattr(sync_datev_stammdaten, "delay")
        assert hasattr(sync_datev_stammdaten, "apply_async")


# =============================================================================
# EDGE CASES & ERROR HANDLING
# =============================================================================


class TestDATEVEdgeCases:
    """Edge Cases und Fehlerbehandlung (Service-Layer)."""

    def test_empty_buchungstext_hash(self, sample_buchung):
        """Leerer Buchungstext fuehrt nicht zu einem Crash bei der Hash-Berechnung."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        sample_buchung.buchungstext = ""
        hash_value = service._calculate_buchung_hash(sample_buchung)

        assert len(hash_value) == 64

    def test_special_characters_in_buchungstext_hash(self, sample_buchung):
        """Deutsche Umlaute/Sonderzeichen werden im Hash korrekt verarbeitet."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        sample_buchung.buchungstext = "Müller GmbH & Co. KG - Bürobedarf"
        sample_buchung.belegfeld_1 = "RE-2026/001"
        hash_value = service._calculate_buchung_hash(sample_buchung)

        assert len(hash_value) == 64

    def test_large_betrag_hash(self, sample_buchung):
        """Grosse Betraege werden bei der Hash-Berechnung korrekt verarbeitet."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        sample_buchung.umsatz = Decimal("9999999.99")
        hash_value = service._calculate_buchung_hash(sample_buchung)

        assert len(hash_value) == 64

    @pytest.mark.asyncio
    async def test_kontierung_zero_betrag(self, mock_db_session, sample_connection_id):
        """Kontierung mit Betrag 0 (z.B. Gutschrift) liefert trotzdem einen Vorschlag."""
        from app.services.datev.connect.kontierung_service import (
            KontierungsInput,
            KontierungsvorschlagService,
        )

        service = KontierungsvorschlagService()
        mock_db_session.execute.side_effect = [
            _result_first(None),
            _result_scalar_one_or_none(None),
        ]

        input_data = KontierungsInput(
            entity_name="Test",
            betrag_brutto=Decimal("0.00"),
            mwst_satz=Decimal("0.0"),
            dokument_typ="credit_note",
            richtung="incoming",
        )

        suggestion = await service.suggest_kontierung(
            db=mock_db_session,
            connection_id=sample_connection_id,
            input_data=input_data,
        )

        assert suggestion is not None
        assert suggestion.konto


class TestDATEVConnectAPIValidation:
    """Schema-Validierungs-Edge-Cases (API-Layer)."""

    def test_kontenrahmen_validation_valid(self):
        """SKR03 und SKR04 sind gueltige Kontenrahmen."""
        from app.api.v1.datev_connect import DATEVConnectionCreate

        for rahmen in ("SKR03", "SKR04"):
            data = DATEVConnectionCreate(
                name="Test",
                beraternummer="12345",
                mandantennummer="67890",
                kontenrahmen=rahmen,
            )
            assert data.kontenrahmen == rahmen

    def test_kontenrahmen_validation_invalid(self):
        """Ungueltiger Kontenrahmen wird abgelehnt (nur SKR03/SKR04 erlaubt)."""
        from pydantic import ValidationError

        from app.api.v1.datev_connect import DATEVConnectionCreate

        with pytest.raises(ValidationError):
            DATEVConnectionCreate(
                name="Test",
                beraternummer="12345",
                mandantennummer="67890",
                kontenrahmen="SKR99",  # ungueltig
            )

    def test_environment_validation_invalid(self):
        """Ungueltige API-Umgebung wird abgelehnt (nur production/sandbox)."""
        from pydantic import ValidationError

        from app.api.v1.datev_connect import DATEVConnectionCreate

        with pytest.raises(ValidationError):
            DATEVConnectionCreate(
                name="Test",
                beraternummer="12345",
                mandantennummer="67890",
                api_environment="staging",  # ungueltig
            )


# =============================================================================
# SECURITY TESTS
# =============================================================================


class TestDATEVSecurity:
    """Sicherheitstests fuer DATEV Connect."""

    def test_state_token_is_cryptographically_secure(self):
        """State-Tokens sind einzigartig (CSRF-Schutz, secrets.token_urlsafe)."""
        from app.services.datev.connect.datev_auth_service import DATEVAuthService

        auth_service = DATEVAuthService()

        states = set()
        for _ in range(100):
            _, state = auth_service.get_authorization_url(
                client_id="test",
                redirect_uri="https://example.com/cb",
            )
            states.add(state)

        assert len(states) == 100

    def test_gobd_hash_uses_sha256(self, sample_buchung):
        """GoBD-Hash ist ein SHA-256 (64 Hex-Zeichen)."""
        from app.services.datev.connect.gobd_compliance_service import (
            GoBDComplianceService,
        )

        service = GoBDComplianceService()
        hash_value = service._calculate_buchung_hash(sample_buchung)

        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)
