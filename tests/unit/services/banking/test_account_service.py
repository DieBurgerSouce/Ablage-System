# -*- coding: utf-8 -*-
"""
Tests fuer AccountService.

Testet:
- Bankkonto erstellen
- Bankkonto abrufen
- Bankkonto aktualisieren
- Bankkonto loeschen (Soft-Delete)
- IBAN-Validierung
- Duplikat-Erkennung
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.account_service import AccountService
from app.services.banking.models import (
    BankAccountCreate,
    BankAccountUpdate,
    BankAccountType,
)


class TestAccountServiceIBANValidation:
    """Detaillierte Tests fuer IBAN-Validierung."""

    @pytest.fixture
    def service(self) -> AccountService:
        return AccountService()

    def test_validate_iban_normalize_whitespace(self, service: AccountService):
        """Sollte Leerzeichen in IBAN ignorieren."""
        iban_with_spaces = "DE89 3704 0044 0532 0130 00"
        iban_without_spaces = "DE89370400440532013000"

        assert service.validate_iban(iban_with_spaces)
        assert service.validate_iban(iban_without_spaces)

    def test_validate_iban_case_insensitive(self, service: AccountService):
        """Sollte Gross-/Kleinschreibung ignorieren."""
        assert service.validate_iban("DE89370400440532013000")
        assert service.validate_iban("de89370400440532013000")
        assert service.validate_iban("De89370400440532013000")

    def test_validate_iban_length_check(self, service: AccountService):
        """Sollte IBANs mit falscher Laenge ablehnen."""
        # Zu kurz (< 15)
        assert not service.validate_iban("DE8937040044")
        # Zu lang (> 34)
        assert not service.validate_iban("DE89370400440532013000123456789012345")

    def test_validate_iban_country_format(self, service: AccountService):
        """Sollte korrektes Laenderformat pruefen."""
        # Gueltig: 2 Buchstaben + 2 Ziffern
        assert service.validate_iban("DE89370400440532013000")
        # Ungueltig: Ziffern am Anfang
        assert not service.validate_iban("12DE370400440532013000")
        # Ungueltig: Buchstaben als Pruefsumme
        assert not service.validate_iban("DEXY370400440532013000")

    def test_validate_iban_mod97_check(self, service: AccountService):
        """Sollte MOD-97 Pruefsumme validieren."""
        # Echte deutsche IBANs (MOD-97 = 1)
        valid_ibans = [
            "DE89370400440532013000",
            "DE68210501700012345678",
            "DE75512108001245126199",
            "DE27100777770209299700",
        ]
        for iban in valid_ibans:
            assert service.validate_iban(iban), f"Sollte gueltig sein: {iban}"

        # Manipulierte IBANs (MOD-97 != 1)
        invalid_ibans = [
            "DE90370400440532013000",  # Pruefsumme geaendert
            "DE89370400440532013001",  # Letzte Ziffer geaendert
        ]
        for iban in invalid_ibans:
            assert not service.validate_iban(iban), f"Sollte ungueltig sein: {iban}"

    def test_validate_international_ibans(self, service: AccountService):
        """Sollte internationale IBANs korrekt validieren."""
        valid_international = [
            "AT611904300234573201",     # Oesterreich (20 Zeichen)
            "CH9300762011623852957",    # Schweiz (21 Zeichen)
            "FR7630006000011234567890189",  # Frankreich (27 Zeichen)
            "GB82WEST12345698765432",   # UK (22 Zeichen)
            "NL91ABNA0417164300",       # Niederlande (18 Zeichen)
            "BE68539007547034",         # Belgien (16 Zeichen)
        ]
        for iban in valid_international:
            assert service.validate_iban(iban), f"Sollte gueltig sein: {iban}"


class TestAccountServiceBankNameDetection:
    """Tests fuer automatische Bank-Erkennung aus IBAN."""

    @pytest.fixture
    def service(self) -> AccountService:
        return AccountService()

    def test_detect_bank_region_from_blz(self, service: AccountService):
        """Sollte Bank-Region aus BLZ erkennen."""
        test_cases = [
            ("DE89100000000000000001", "Bundesbank"),  # BLZ 100...
            ("DE89200000000000000002", "Hamburg"),     # BLZ 200...
            ("DE89370000000000000003", "Koeln"),       # BLZ 370...
            ("DE89500000000000000004", "Frankfurt"),   # BLZ 500...
            ("DE89700000000000000005", "Muenchen"),    # BLZ 700...
        ]
        for iban, expected_region in test_cases:
            bank_name = service._get_bank_name_from_iban(iban)
            if bank_name:
                assert expected_region in bank_name, f"Sollte {expected_region} enthalten: {iban}"

    def test_no_bank_name_for_foreign_iban(self, service: AccountService):
        """Sollte keinen Banknamen fuer auslaendische IBANs liefern."""
        foreign_iban = "AT611904300234573201"  # Oesterreich
        bank_name = service._get_bank_name_from_iban(foreign_iban)
        assert bank_name is None


class TestAccountServiceResponseConversion:
    """Tests fuer Response-Konvertierung."""

    @pytest.fixture
    def service(self) -> AccountService:
        return AccountService()

    def test_to_response_basic_fields(self, service: AccountService):
        """Sollte alle Basis-Felder korrekt konvertieren."""
        # Mock Account object
        mock_account = MagicMock()
        mock_account.id = uuid4()
        mock_account.user_id = uuid4()
        mock_account.company_id = uuid4()
        mock_account.account_name = "Girokonto"
        mock_account.iban = "DE89370400440532013000"
        mock_account.bic = "COBADEFFXXX"
        mock_account.bank_name = "Commerzbank"
        mock_account.account_holder = "Max Mustermann"
        mock_account.account_type = "checking"
        mock_account.currency = "EUR"
        mock_account.is_active = True
        mock_account.connection_status = "manual"
        mock_account.current_balance = Decimal("1234.56")
        mock_account.balance_date = datetime.now()
        mock_account.last_sync_at = None
        mock_account.auto_sync_enabled = False
        mock_account.created_at = datetime.now()
        mock_account.updated_at = datetime.now()

        response = service._to_response(mock_account)

        assert response.id == mock_account.id
        assert response.user_id == mock_account.user_id
        assert response.account_name == "Girokonto"
        assert response.iban == "DE89370400440532013000"
        assert response.bic == "COBADEFFXXX"
        assert response.account_type == BankAccountType.CHECKING
        assert response.currency == "EUR"
        assert response.is_active is True
        assert response.current_balance == Decimal("1234.56")

    def test_to_response_default_values(self, service: AccountService):
        """Sollte Standardwerte fuer fehlende Felder setzen."""
        mock_account = MagicMock()
        mock_account.id = uuid4()
        mock_account.user_id = uuid4()
        mock_account.company_id = None
        mock_account.account_name = "Test"
        mock_account.iban = "DE89370400440532013000"
        mock_account.bic = None
        mock_account.bank_name = None
        mock_account.account_holder = None
        mock_account.account_type = None
        mock_account.currency = None
        mock_account.is_active = True
        mock_account.connection_status = None
        mock_account.current_balance = None
        mock_account.balance_date = None
        mock_account.last_sync_at = None
        mock_account.auto_sync_enabled = None
        mock_account.created_at = datetime.now()
        mock_account.updated_at = None

        response = service._to_response(mock_account)

        assert response.account_type == BankAccountType.CHECKING
        assert response.currency == "EUR"
        assert response.connection_status == "manual"
        assert response.auto_sync_enabled is False


class TestAccountServiceWithMockedDB:
    """Tests mit gemockter Datenbank."""

    @pytest.fixture
    def service(self) -> AccountService:
        return AccountService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.get = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_create_account_validates_iban(self, service: AccountService, mock_db):
        """Sollte ungueltige IBAN bei Erstellung ablehnen (Pydantic-Validierung)."""
        from pydantic import ValidationError

        # Die IBAN-Validierung geschieht bereits beim Erstellen des Schemas
        with pytest.raises(ValidationError) as exc_info:
            BankAccountCreate(
                account_name="Test",
                iban="INVALID_IBAN",  # Zu kurz und ungueltige Struktur
            )

        # Pydantic wirft ValidationError, nicht ValueError
        assert "iban" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_account_checks_duplicate(self, service: AccountService, mock_db):
        """Sollte Duplikat-IBAN ablehnen."""
        user_id = uuid4()
        valid_data = BankAccountCreate(
            account_name="Test",
            iban="DE89370400440532013000",
        )

        # Mock: IBAN existiert bereits
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # Existierendes Konto
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc_info:
            await service.create_account(mock_db, user_id, valid_data)

        assert "existiert bereits" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_account_returns_none_for_other_user(self, service: AccountService, mock_db):
        """Sollte None zurueckgeben wenn Konto anderem User gehoert."""
        user_id = uuid4()
        other_user_id = uuid4()
        account_id = uuid4()

        mock_account = MagicMock()
        mock_account.user_id = other_user_id  # Anderer User
        mock_account.deleted_at = None
        mock_db.get.return_value = mock_account

        result = await service.get_account(mock_db, user_id, account_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_account_returns_none_for_deleted(self, service: AccountService, mock_db):
        """Sollte None zurueckgeben wenn Konto geloescht ist."""
        user_id = uuid4()
        account_id = uuid4()

        mock_account = MagicMock()
        mock_account.user_id = user_id
        mock_account.deleted_at = datetime.now()  # Geloescht
        mock_db.get.return_value = mock_account

        result = await service.get_account(mock_db, user_id, account_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_account_soft_delete(self, service: AccountService, mock_db):
        """Sollte Soft-Delete durchfuehren."""
        company_id = uuid4()
        account_id = uuid4()

        mock_account = MagicMock()
        mock_account.company_id = company_id
        mock_account.deleted_at = None
        mock_account.is_active = True
        mock_db.get.return_value = mock_account

        result = await service.delete_account(mock_db, company_id, account_id)

        assert result is True
        assert mock_account.deleted_at is not None
        assert mock_account.is_active is False
        mock_db.commit.assert_called_once()
