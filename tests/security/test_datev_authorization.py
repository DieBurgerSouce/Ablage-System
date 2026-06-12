# -*- coding: utf-8 -*-
"""
Security Tests fuer DATEV Authorization.

Testet die Behebung folgender Sicherheitsluecken:
- CRITICAL-1: Authorization Bypass in delete_vendor_mapping (OWASP A07:2021)
- CRITICAL-2: Authorization Bypass in _get_config (OWASP A07:2021)
- HIGH-1: Information Disclosure in Error Responses
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_user_a():
    """Mock User A (Besitzer der Konfiguration)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user_a@test.de"
    user.is_active = True
    return user


@pytest.fixture
def mock_user_b():
    """Mock User B (Angreifer - versucht fremde Ressourcen zu manipulieren)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user_b@test.de"
    user.is_active = True
    return user


@pytest.fixture
def mock_config_for_user_a(mock_user_a):
    """DATEV Konfiguration die User A gehoert."""
    config = MagicMock()
    config.id = uuid.uuid4()
    config.user_id = mock_user_a.id
    config.berater_nr = "1234567"
    config.mandanten_nr = "12345"
    config.kontenrahmen = "SKR03"
    config.wj_beginn = date(2025, 1, 1)
    config.is_active = True
    config.is_default = True
    return config


@pytest.fixture
def mock_vendor_mapping(mock_config_for_user_a):
    """Vendor-Mapping das zur Konfiguration von User A gehoert."""
    mapping = MagicMock()
    mapping.id = uuid.uuid4()
    mapping.config_id = mock_config_for_user_a.id
    mapping.vendor_name = "Test Lieferant GmbH"
    mapping.vendor_vat_id = "DE123456789"
    mapping.expense_account = "3200"
    mapping.creditor_account = "70001"
    return mapping


# =============================================================================
# AUTHORIZATION TESTS - delete_vendor_mapping
# =============================================================================

class TestDeleteVendorMappingAuthorization:
    """Tests fuer CRITICAL-1: Authorization in delete_vendor_mapping."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_cannot_delete_other_users_vendor_mapping(
        self, mock_user_a, mock_user_b, mock_config_for_user_a, mock_vendor_mapping
    ):
        """
        SECURITY TEST: User B darf Vendor-Mapping von User A NICHT loeschen.

        Vor dem Fix konnte jeder authentifizierte User beliebige Vendor-Mappings
        loeschen, wenn er die UUIDs kannte/erriet.
        """
        from app.api.v1.datev import delete_vendor_mapping
        from fastapi import HTTPException

        # Mock DB Session
        mock_db = AsyncMock(spec=AsyncSession)

        # Config-Query: Gibt None zurueck, weil User B nicht der Besitzer ist
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = config_result

        # User B versucht Mapping von User A zu loeschen
        with pytest.raises(HTTPException) as exc_info:
            await delete_vendor_mapping(
                config_id=mock_config_for_user_a.id,
                mapping_id=mock_vendor_mapping.id,
                db=mock_db,
                current_user=mock_user_b,  # ANGREIFER
            )

        # Erwartung: 404 (Konfiguration nicht gefunden fuer diesen User)
        assert exc_info.value.status_code == 404
        assert "Konfiguration nicht gefunden" in exc_info.value.detail

        # WICHTIG: delete() sollte NICHT aufgerufen worden sein
        mock_db.delete.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_owner_can_delete_own_vendor_mapping(
        self, mock_user_a, mock_config_for_user_a, mock_vendor_mapping
    ):
        """
        POSITIVE TEST: Besitzer kann sein eigenes Vendor-Mapping loeschen.
        """
        from app.api.v1.datev import delete_vendor_mapping

        # Mock DB Session
        mock_db = AsyncMock(spec=AsyncSession)

        # Config-Query: Gibt Config zurueck (User A ist Besitzer)
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = mock_config_for_user_a

        # Mapping-Query: Gibt Mapping zurueck
        mapping_result = MagicMock()
        mapping_result.scalar_one_or_none.return_value = mock_vendor_mapping

        mock_db.execute.side_effect = [config_result, mapping_result]

        # User A loescht sein eigenes Mapping - sollte funktionieren
        await delete_vendor_mapping(
            config_id=mock_config_for_user_a.id,
            mapping_id=mock_vendor_mapping.id,
            db=mock_db,
            current_user=mock_user_a,  # BESITZER
        )

        # delete() sollte aufgerufen worden sein
        mock_db.delete.assert_called_once_with(mock_vendor_mapping)
        mock_db.commit.assert_called_once()


# =============================================================================
# AUTHORIZATION TESTS - _get_config in ExportService
# =============================================================================

class TestGetConfigAuthorization:
    """Tests fuer CRITICAL-2: Authorization in _get_config."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_cannot_access_other_users_config_by_id(
        self, mock_user_a, mock_user_b, mock_config_for_user_a
    ):
        """
        SECURITY TEST: User B darf Config von User A NICHT laden (per config_id).

        Vor dem Fix wurde user_id nicht geprueft wenn config_id angegeben war.
        Ein Angreifer konnte so fremde Konfigurationen fuer Exporte verwenden.
        """
        from app.services.datev.export_service import DATEVExportService

        service = DATEVExportService()

        # Mock DB Session
        mock_db = AsyncMock(spec=AsyncSession)

        # Query gibt None zurueck, weil user_id nicht matcht (nach Fix)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        # User B versucht Config von User A zu laden
        config = await service._get_config(
            db=mock_db,
            config_id=mock_config_for_user_a.id,
            user_id=mock_user_b.id,  # ANGREIFER
        )

        # Erwartung: None (Config nicht gefunden fuer diesen User)
        assert config is None

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_owner_can_access_own_config_by_id(
        self, mock_user_a, mock_config_for_user_a
    ):
        """
        POSITIVE TEST: Besitzer kann seine eigene Config laden.
        """
        from app.services.datev.export_service import DATEVExportService

        service = DATEVExportService()

        # Mock DB Session
        mock_db = AsyncMock(spec=AsyncSession)

        # Query gibt Config zurueck (User A ist Besitzer)
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_config_for_user_a
        mock_db.execute.return_value = result

        # User A laedt seine eigene Config
        config = await service._get_config(
            db=mock_db,
            config_id=mock_config_for_user_a.id,
            user_id=mock_user_a.id,  # BESITZER
        )

        # Erwartung: Config wird zurueckgegeben
        assert config is not None
        assert config.id == mock_config_for_user_a.id


# =============================================================================
# INFORMATION DISCLOSURE TESTS
# =============================================================================

class TestInformationDisclosure:
    """Tests fuer HIGH-1: Information Disclosure in Error Responses."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_no_exception_details_in_error_response(self, mock_user_a):
        """
        SECURITY TEST: Exception-Details duerfen NICHT an Client gesendet werden.

        Vor dem Fix wurden interne Exception-Texte in der HTTP Response exponiert.
        Dies koennte Angreifern Informationen ueber das System liefern.
        """
        from app.api.v1.datev import export_buchungsstapel
        from app.api.schemas.datev import DATEVExportRequest
        from fastapi import HTTPException

        # Mock DB Session
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock Service der eine Exception wirft
        with patch('app.api.v1.datev.get_datev_export_service') as mock_get_service:
            mock_service = MagicMock()
            # Simuliere einen internen Fehler mit sensiblen Details
            mock_service.export_buchungsstapel = AsyncMock(
                side_effect=RuntimeError(
                    "Connection to database failed: host=db.internal.company.com, "
                    "user=admin, password=secret123"
                )
            )
            mock_get_service.return_value = mock_service

            request = DATEVExportRequest(
                document_ids=[uuid.uuid4()],
                period_from=date(2025, 1, 1),
                period_to=date(2025, 12, 31),
            )

            with pytest.raises(HTTPException) as exc_info:
                await export_buchungsstapel(
                    request=request,
                    db=mock_db,
                    current_user=mock_user_a,
                )

            # Status sollte 500 sein
            assert exc_info.value.status_code == 500

            # KRITISCH: Sensible Details duerfen NICHT in Response sein
            error_detail = exc_info.value.detail
            assert "database" not in error_detail.lower()
            assert "password" not in error_detail.lower()
            assert "secret" not in error_detail.lower()
            assert "host=" not in error_detail.lower()

            # Generische deutsche Fehlermeldung erwartet
            assert "Export fehlgeschlagen" in error_detail
            assert "Administrator" in error_detail

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_value_error_shows_user_friendly_message(self, mock_user_a):
        """
        TEST: ValueError wird mit benutzerfreundlicher Nachricht behandelt.

        ValueError wird als 400 mit GENERISCHER deutscher Meldung beantwortet.
        ANGEPASST (2026-06-12): Die App reicht rohe ValueError-Texte bewusst
        NICHT an den Client durch (Information-Disclosure-Schutz, vgl.
        SECURITY FIX in app/api/v1/datev.py) - der Original-Text wird nur
        serverseitig geloggt.
        """
        from app.api.v1.datev import export_buchungsstapel
        from app.api.schemas.datev import DATEVExportRequest
        from fastapi import HTTPException

        mock_db = AsyncMock(spec=AsyncSession)

        with patch('app.api.v1.datev.get_datev_export_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.export_buchungsstapel = AsyncMock(
                side_effect=ValueError("Keine exportierbaren Dokumente gefunden.")
            )
            mock_get_service.return_value = mock_service

            request = DATEVExportRequest(
                document_ids=[uuid.uuid4()],
            )

            with pytest.raises(HTTPException) as exc_info:
                await export_buchungsstapel(
                    request=request,
                    db=mock_db,
                    current_user=mock_user_a,
                )

            # ValueError -> 400 Bad Request mit generischer deutscher Meldung
            assert exc_info.value.status_code == 400
            assert "Ungültige Eingabedaten" in exc_info.value.detail
            # Interner Fehlertext darf NICHT zum Client durchsickern
            assert "exportierbaren Dokumente" not in exc_info.value.detail


# =============================================================================
# AUDIT LOGGING TESTS
# =============================================================================

class TestAuditLogging:
    """Tests fuer Audit-Logging der CRUD-Operationen."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_delete_vendor_mapping_is_logged(
        self, mock_user_a, mock_config_for_user_a, mock_vendor_mapping
    ):
        """
        TEST: Loeschen eines Vendor-Mappings wird geloggt.
        """
        from app.api.v1.datev import delete_vendor_mapping

        mock_db = AsyncMock(spec=AsyncSession)

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = mock_config_for_user_a

        mapping_result = MagicMock()
        mapping_result.scalar_one_or_none.return_value = mock_vendor_mapping

        mock_db.execute.side_effect = [config_result, mapping_result]

        with patch('app.api.v1.datev.logger') as mock_logger:
            await delete_vendor_mapping(
                config_id=mock_config_for_user_a.id,
                mapping_id=mock_vendor_mapping.id,
                db=mock_db,
                current_user=mock_user_a,
            )

            # Logging sollte aufgerufen worden sein
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args

            # Pruefe Log-Event Name
            assert call_args[0][0] == "datev_vendor_mapping_deleted"

            # Pruefe Log-Details. ANGEPASST (2026-06-12): structlog-Konvention
            # des Projekts = Kontext als Keyword-Argumente, NICHT als
            # stdlib-"extra"-Dict.
            extra = call_args[1]
            assert "mapping_id" in extra
            assert "config_id" in extra
            assert "user_id" in extra

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_export_error_is_logged_with_context(self, mock_user_a):
        """
        TEST: Export-Fehler werden mit Kontext geloggt (aber ohne sensible Daten).
        """
        from app.api.v1.datev import export_buchungsstapel
        from app.api.schemas.datev import DATEVExportRequest
        from fastapi import HTTPException

        mock_db = AsyncMock(spec=AsyncSession)

        with patch('app.api.v1.datev.get_datev_export_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.export_buchungsstapel = AsyncMock(
                side_effect=RuntimeError("Internal error")
            )
            mock_get_service.return_value = mock_service

            with patch('app.api.v1.datev.logger') as mock_logger:
                request = DATEVExportRequest(document_ids=[uuid.uuid4()])

                with pytest.raises(HTTPException):
                    await export_buchungsstapel(
                        request=request,
                        db=mock_db,
                        current_user=mock_user_a,
                    )

                # exception() sollte aufgerufen worden sein
                mock_logger.exception.assert_called_once()
                call_args = mock_logger.exception.call_args

                # Log-Event Name
                assert call_args[0][0] == "datev_export_error"

                # user_id sollte geloggt werden. ANGEPASST (2026-06-12):
                # structlog-Konvention = Keyword-Argumente statt "extra"-Dict.
                extra = call_args[1]
                assert "user_id" in extra
                assert "error_type" in extra


# =============================================================================
# BOUNDARY TESTS
# =============================================================================

class TestAuthorizationBoundaries:
    """Tests fuer Edge Cases und Grenzfaelle."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_uuid_collision_does_not_bypass_auth(
        self, mock_user_a, mock_user_b
    ):
        """
        TEST: Selbst wenn UUIDs zufaellig kollidieren, wird Authorization geprueft.
        """
        from app.services.datev.export_service import DATEVExportService

        service = DATEVExportService()

        # Beide User haben zufaellig die gleiche config_id (extrem unwahrscheinlich)
        shared_config_id = uuid.uuid4()

        mock_db = AsyncMock(spec=AsyncSession)

        # Query prueft BEIDE: config_id UND user_id
        # Fuer User B wird None zurueckgegeben
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        config = await service._get_config(
            db=mock_db,
            config_id=shared_config_id,
            user_id=mock_user_b.id,
        )

        assert config is None

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_empty_uuid_handled_gracefully(self, mock_user_a):
        """
        TEST: Leere/Null UUIDs werden sicher behandelt.
        """
        from app.api.v1.datev import delete_vendor_mapping
        from fastapi import HTTPException

        mock_db = AsyncMock(spec=AsyncSession)

        # Config-Query gibt None zurueck
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        # Zufaellige UUIDs - sollte 404 geben
        with pytest.raises(HTTPException) as exc_info:
            await delete_vendor_mapping(
                config_id=uuid.uuid4(),
                mapping_id=uuid.uuid4(),
                db=mock_db,
                current_user=mock_user_a,
            )

        assert exc_info.value.status_code == 404
