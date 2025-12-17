# -*- coding: utf-8 -*-
"""
Tests fuer PaymentService.

Testet:
- Zahlungserstellung
- IBAN/BIC-Validierung
- Workflow (Draft -> Approved -> Submitted -> Confirmed)
- Stornierung
- Skonto-Erkennung
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.payment_service import (
    PaymentService,
    PaymentValidationResult,
)
from app.services.banking.models import (
    PaymentStatus,
    PaymentType,
    PaymentOrderCreate,
)


class TestIBANValidation:
    """Tests fuer IBAN-Validierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_normalize_iban(self, service: PaymentService):
        """Sollte IBAN normalisieren."""
        assert service._normalize_iban("DE89 3704 0044 0532 0130 00") == "DE89370400440532013000"
        assert service._normalize_iban("de89370400440532013000") == "DE89370400440532013000"

    def test_validate_iban_checksum_valid(self, service: PaymentService):
        """Sollte gueltige IBAN akzeptieren."""
        # Bekannte gueltige IBANs
        valid_ibans = [
            "DE89370400440532013000",
            "AT611904300234573201",
            "CH9300762011623852957",
        ]
        for iban in valid_ibans:
            assert service._validate_iban_checksum(iban), f"IBAN sollte gueltig sein: {iban}"

    def test_validate_iban_checksum_invalid(self, service: PaymentService):
        """Sollte ungueltige IBAN ablehnen."""
        invalid_ibans = [
            "DE89370400440532013001",  # Falsche Pruefziffer
            "DE00370400440532013000",  # Pruefziffer 00
            "INVALID",
        ]
        for iban in invalid_ibans:
            assert not service._validate_iban_checksum(iban), f"IBAN sollte ungueltig sein: {iban}"


class TestPaymentValidation:
    """Tests fuer Zahlungsvalidierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_validate_payment_success(self, service: PaymentService):
        """Sollte gueltige Zahlung akzeptieren."""
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013000",
            amount=Decimal("100.00"),
            reference="Rechnung 2024-001",
        )

        result = service._validate_payment(data)

        assert result.valid
        assert len(result.errors) == 0

    def test_validate_payment_invalid_iban_checksum(self, service: PaymentService):
        """Sollte IBAN mit falscher Pruefziffer ablehnen."""
        # Diese IBAN hat eine falsche Pruefziffer (endet auf 01 statt 00)
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013001",  # Falsche Pruefziffer
            amount=Decimal("100.00"),
        )

        result = service._validate_payment(data)

        assert not result.valid
        assert any("Pruefziffer" in e for e in result.errors)

    def test_validate_payment_large_amount_warning(self, service: PaymentService):
        """Sollte Warnung bei grossem Betrag ausgeben."""
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013000",
            amount=Decimal("60000.00"),  # Ueber MAX_SINGLE_PAYMENT
            reference="Grosser Transfer",
        )

        result = service._validate_payment(data)

        # Sollte valide sein, aber mit Warnung
        assert result.valid
        assert len(result.warnings) > 0

    def test_validate_payment_past_date(self, service: PaymentService):
        """Sollte vergangenes Datum ablehnen."""
        data = PaymentOrderCreate(
            bank_account_id=uuid4(),
            beneficiary_name="Test GmbH",
            beneficiary_iban="DE89370400440532013000",
            amount=Decimal("100.00"),
            reference="Test",
            execution_date=date.today() - timedelta(days=1),
        )

        result = service._validate_payment(data)

        assert not result.valid
        assert any("Vergangenheit" in e for e in result.errors)


class TestEndToEndIDGeneration:
    """Tests fuer End-to-End-ID-Generierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_generate_end_to_end_id_format(self, service: PaymentService):
        """Sollte korrektes Format haben."""
        e2e_id = service._generate_end_to_end_id()

        assert e2e_id.startswith("E2E")
        assert len(e2e_id) > 10

    def test_generate_end_to_end_id_unique(self, service: PaymentService):
        """Sollte eindeutige IDs generieren."""
        ids = [service._generate_end_to_end_id() for _ in range(100)]
        assert len(ids) == len(set(ids))


class TestBankReferenceGeneration:
    """Tests fuer Bank-Referenznummer-Generierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_generate_bank_reference_format(self, service: PaymentService):
        """Sollte korrektes Format haben."""
        ref = service._generate_bank_reference()

        assert ref.startswith("REF")
        assert len(ref) > 10


class TestTANValidation:
    """Tests fuer TAN-Validierung."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_validate_tan_valid(self, service: PaymentService):
        """Sollte gueltige TAN akzeptieren."""
        assert service._validate_tan("123456")

    def test_validate_tan_too_short(self, service: PaymentService):
        """Sollte zu kurze TAN ablehnen."""
        assert not service._validate_tan("12345")

    def test_validate_tan_too_long(self, service: PaymentService):
        """Sollte zu lange TAN ablehnen."""
        assert not service._validate_tan("1234567")

    def test_validate_tan_non_numeric(self, service: PaymentService):
        """Sollte nicht-numerische TAN ablehnen."""
        assert not service._validate_tan("12345a")

    def test_validate_tan_empty(self, service: PaymentService):
        """Sollte leere TAN ablehnen."""
        assert not service._validate_tan("")
        assert not service._validate_tan(None)


class TestPaymentServiceWithMockedDB:
    """Tests mit gemockter Datenbank."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_get_payment_not_found(
        self, service: PaymentService, mock_db
    ):
        """Sollte None zurueckgeben wenn Zahlung nicht gefunden."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_payment(mock_db, user_id, payment_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_approve_payment_wrong_status(
        self, service: PaymentService, mock_db
    ):
        """Sollte Fehler werfen wenn Status nicht 'draft' ist."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.APPROVED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="kann nicht genehmigt"):
            await service.approve_payment(mock_db, user_id, payment_id)

    @pytest.mark.asyncio
    async def test_cancel_payment_wrong_status(
        self, service: PaymentService, mock_db
    ):
        """Sollte Fehler werfen wenn Status nicht stornierbar ist."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.CONFIRMED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="kann nicht storniert"):
            await service.cancel_payment(mock_db, user_id, payment_id)

    @pytest.mark.asyncio
    async def test_submit_payment_not_approved(
        self, service: PaymentService, mock_db
    ):
        """Sollte Fehler werfen wenn Zahlung nicht genehmigt ist."""
        user_id = uuid4()
        payment_id = uuid4()

        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.DRAFT.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_payment
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="muss genehmigt"):
            await service.submit_payment(mock_db, user_id, payment_id)


class TestPaymentServiceThresholds:
    """Tests fuer Schwellenwerte."""

    @pytest.fixture
    def service(self) -> PaymentService:
        return PaymentService()

    def test_max_single_payment(self, service: PaymentService):
        """Sollte korrekten Max-Einzelbetrag haben."""
        assert service.MAX_SINGLE_PAYMENT == Decimal("50000.00")

    def test_max_batch_total(self, service: PaymentService):
        """Sollte korrekten Max-Batch-Betrag haben."""
        assert service.MAX_BATCH_TOTAL == Decimal("100000.00")
