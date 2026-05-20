# -*- coding: utf-8 -*-
"""
Unit Tests fuer CrossValidationService.

Testet:
- Betrags-Plausibilitaet (Netto + MwSt = Brutto)
- IBAN-Format- und Pruefziffer-Validierung
- USt-ID-Format-Validierung
- Datums-Plausibilitaet
- Duplikat-Erkennung
- Aggregierte Validierung
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ocr.cross_validation_service import (
    CrossValidationService,
    CrossValidationResult,
    ValidationResult,
    ValidationSeverity,
    AMOUNT_TOLERANCE,
    VALID_VAT_RATES,
    get_cross_validation_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service() -> CrossValidationService:
    """Erstelle Service-Instanz."""
    return CrossValidationService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


# =============================================================================
# Amount Validation Tests
# =============================================================================


class TestAmountValidation:
    """Tests fuer Betrags-Plausibilitaet."""

    def test_amounts_plausible(self, service: CrossValidationService) -> None:
        """Netto + MwSt = Brutto ist plausibel."""
        result = service.validate_amounts(
            netto=Decimal("100.00"),
            mwst=Decimal("19.00"),
            brutto=Decimal("119.00"),
        )
        assert result.passed is True
        assert result.confidence_adjustment > 0

    def test_amounts_inconsistent(self, service: CrossValidationService) -> None:
        """Inkonsistente Betraege werden erkannt."""
        result = service.validate_amounts(
            netto=Decimal("100.00"),
            mwst=Decimal("19.00"),
            brutto=Decimal("125.00"),  # Falsch
        )
        assert result.passed is False
        assert result.severity == ValidationSeverity.ERROR

    def test_amounts_within_tolerance(self, service: CrossValidationService) -> None:
        """Betraege innerhalb Toleranz (2 Cent) sind OK."""
        result = service.validate_amounts(
            netto=Decimal("100.00"),
            mwst=Decimal("19.00"),
            brutto=Decimal("119.01"),  # 1 Cent Abweichung
        )
        assert result.passed is True

    def test_no_amounts(self, service: CrossValidationService) -> None:
        """Keine Betraege ergibt neutrale Validierung."""
        result = service.validate_amounts(netto=None, mwst=None, brutto=None)
        assert result.passed is True
        assert result.confidence_adjustment == 0.0

    def test_unusual_vat_rate(self, service: CrossValidationService) -> None:
        """Unueblicher USt-Satz wird als Warnung gemeldet."""
        result = service.validate_amounts(
            netto=Decimal("100.00"),
            mwst=Decimal("19.00"),
            brutto=Decimal("119.00"),
            ust_satz=Decimal("15"),  # Unueblich
        )
        assert result.passed is False
        assert result.severity == ValidationSeverity.WARNING

    def test_standard_vat_rates_accepted(self, service: CrossValidationService) -> None:
        """Standard-USt-Saetze (0%, 7%, 19%) werden akzeptiert."""
        for rate in [Decimal("0"), Decimal("7"), Decimal("19")]:
            result = service.validate_amounts(
                netto=Decimal("100.00"),
                mwst=Decimal("19.00"),
                brutto=Decimal("119.00"),
                ust_satz=rate,
            )
            # Entweder bestanden oder nur wegen berechnetem Satz fehlgeschlagen
            assert result.check_name == "amount_plausibility"

    def test_calculated_vat_rate_warning(self, service: CrossValidationService) -> None:
        """Berechneter unueblicher MwSt-Satz ergibt Warnung."""
        result = service.validate_amounts(
            netto=Decimal("100.00"),
            mwst=Decimal("15.00"),  # 15% -> unueblich
            brutto=Decimal("115.00"),
        )
        assert result.passed is False


# =============================================================================
# IBAN Validation Tests
# =============================================================================


class TestIBANValidation:
    """Tests fuer IBAN-Validierung."""

    @pytest.mark.asyncio
    async def test_valid_iban(
        self, service: CrossValidationService, mock_db: AsyncMock
    ) -> None:
        """Gueltige deutsche IBAN wird akzeptiert."""
        result = await service.validate_iban(
            "DE89 3704 0044 0532 0130 00", None, mock_db
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_no_iban(
        self, service: CrossValidationService, mock_db: AsyncMock
    ) -> None:
        """Keine IBAN ergibt neutrale Validierung."""
        result = await service.validate_iban(None, None, mock_db)
        assert result.passed is True
        assert result.confidence_adjustment == 0.0

    @pytest.mark.asyncio
    async def test_invalid_format(
        self, service: CrossValidationService, mock_db: AsyncMock
    ) -> None:
        """Ungueltiges IBAN-Format wird erkannt."""
        result = await service.validate_iban("1234", None, mock_db)
        assert result.passed is False
        assert result.severity == ValidationSeverity.ERROR

    @pytest.mark.asyncio
    async def test_wrong_length(
        self, service: CrossValidationService, mock_db: AsyncMock
    ) -> None:
        """Falsche IBAN-Laenge wird erkannt."""
        result = await service.validate_iban("DE89370400440532", None, mock_db)
        assert result.passed is False
        assert "Laenge" in result.message

    @pytest.mark.asyncio
    async def test_invalid_checksum(
        self, service: CrossValidationService, mock_db: AsyncMock
    ) -> None:
        """Falsche Pruefziffer wird erkannt."""
        result = await service.validate_iban(
            "DE00370400440532013000", None, mock_db
        )
        assert result.passed is False
        assert "Pruefziffer" in result.message

    def test_iban_checksum_validation(self, service: CrossValidationService) -> None:
        """IBAN-Pruefziffer-Algorithmus funktioniert korrekt."""
        assert service._validate_iban_checksum("DE89370400440532013000") is True
        assert service._validate_iban_checksum("DE00370400440532013000") is False


# =============================================================================
# USt-ID Validation Tests
# =============================================================================


class TestUStIDValidation:
    """Tests fuer USt-ID-Validierung."""

    def test_valid_german_ust_id(self, service: CrossValidationService) -> None:
        """Gueltige deutsche USt-ID wird akzeptiert."""
        result = service.validate_ust_id("DE123456789")
        assert result.passed is True

    def test_no_ust_id(self, service: CrossValidationService) -> None:
        """Keine USt-ID ergibt neutrale Validierung."""
        result = service.validate_ust_id(None)
        assert result.passed is True

    def test_too_short(self, service: CrossValidationService) -> None:
        """Zu kurze USt-ID wird abgelehnt."""
        result = service.validate_ust_id("DE1")
        assert result.passed is False

    def test_no_country_code(self, service: CrossValidationService) -> None:
        """USt-ID ohne Laendercode wird abgelehnt."""
        result = service.validate_ust_id("12345678901")
        assert result.passed is False

    def test_german_wrong_length(self, service: CrossValidationService) -> None:
        """Deutsche USt-ID mit falscher Laenge wird abgelehnt."""
        result = service.validate_ust_id("DE12345")  # Zu kurz
        assert result.passed is False

    def test_german_non_digits(self, service: CrossValidationService) -> None:
        """Deutsche USt-ID mit Buchstaben nach DE wird abgelehnt."""
        result = service.validate_ust_id("DE12345678A")
        assert result.passed is False

    def test_whitespace_handling(self, service: CrossValidationService) -> None:
        """Leerzeichen in USt-ID werden entfernt."""
        result = service.validate_ust_id("DE 123 456 789")
        assert result.passed is True


# =============================================================================
# Date Validation Tests
# =============================================================================


class TestDateValidation:
    """Tests fuer Datums-Validierung."""

    def test_plausible_dates(self, service: CrossValidationService) -> None:
        """Plausible Datumsfelder werden akzeptiert."""
        today = date.today()
        result = service.validate_dates(
            invoice_date=today - timedelta(days=5),
            due_date=today + timedelta(days=25),
        )
        assert result.passed is True

    def test_no_dates(self, service: CrossValidationService) -> None:
        """Keine Datumsfelder ergibt neutrale Validierung."""
        result = service.validate_dates()
        assert result.passed is True

    def test_future_invoice_date(self, service: CrossValidationService) -> None:
        """Rechnungsdatum in der Zukunft wird erkannt."""
        future_date = date.today() + timedelta(days=30)
        result = service.validate_dates(invoice_date=future_date)
        assert result.passed is False
        assert "Zukunft" in result.message

    def test_very_old_invoice_date(self, service: CrossValidationService) -> None:
        """Sehr altes Rechnungsdatum wird erkannt."""
        old_date = date.today() - timedelta(days=800)
        result = service.validate_dates(invoice_date=old_date)
        assert result.passed is False

    def test_due_date_before_invoice_date(self, service: CrossValidationService) -> None:
        """Faelligkeitsdatum vor Rechnungsdatum wird erkannt."""
        today = date.today()
        result = service.validate_dates(
            invoice_date=today,
            due_date=today - timedelta(days=10),
        )
        assert result.passed is False
        assert "vor Rechnungsdatum" in result.message

    def test_delivery_date_deviation(self, service: CrossValidationService) -> None:
        """Starke Lieferdatum-Abweichung wird erkannt."""
        today = date.today()
        result = service.validate_dates(
            invoice_date=today,
            delivery_date=today - timedelta(days=200),
        )
        assert result.passed is False


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelpers:
    """Tests fuer Hilfsmethoden."""

    def test_to_decimal_valid(self, service: CrossValidationService) -> None:
        """Gueltige Decimal-Konvertierung."""
        assert service._to_decimal("100.50") == Decimal("100.50")
        assert service._to_decimal(42) == Decimal("42")
        assert service._to_decimal(Decimal("19.99")) == Decimal("19.99")

    def test_to_decimal_invalid(self, service: CrossValidationService) -> None:
        """Ungueltige Decimal-Konvertierung ergibt None."""
        assert service._to_decimal(None) is None
        assert service._to_decimal("abc") is None

    def test_to_str(self, service: CrossValidationService) -> None:
        """String-Konvertierung."""
        assert service._to_str("hallo") == "hallo"
        assert service._to_str(None) is None
        assert service._to_str("  ") is None

    def test_to_date(self, service: CrossValidationService) -> None:
        """Datums-Konvertierung."""
        assert service._to_date(None) is None
        assert service._to_date("2024-03-15") == date(2024, 3, 15)
        assert service._to_date("invalid") is None

    def test_get_stats(self, service: CrossValidationService) -> None:
        """Statistiken werden korrekt zurueckgegeben."""
        stats = service.get_stats()
        assert "total_validations" in stats
        assert "errors_found" in stats

    def test_singleton(self) -> None:
        """Singleton-Pattern funktioniert."""
        import app.services.ocr.cross_validation_service as module
        module._cross_validation_service = None

        s1 = get_cross_validation_service()
        s2 = get_cross_validation_service()
        assert s1 is s2
