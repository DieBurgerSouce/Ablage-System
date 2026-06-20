# -*- coding: utf-8 -*-
"""Tests fuer PaymentInitiationService.

Testet Zahlungsinitiierung, Genehmigungsworkflow und Stornierung:
- Validierung von Zahlungsanfragen
- Tageslimit-Pruefung
- Genehmigungspflicht
- PSD2 und FinTS Routing
- Batch-Zahlungen
- Stornierung
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, Mock, MagicMock, patch

from app.services.banking.payment_initiation_service import (
    PaymentInitiationService,
    PaymentConfig,
    PaymentRequest,
    PaymentResult,
    BatchPaymentRequest,
    BatchPaymentResult,
)
from app.db.models_banking_connection import (
    PaymentInitiationStatus,
    ConnectionStatus,
)


class TestPaymentProductionGuard:
    """F-08: PSD2/FinTS-Zahlungsausloesung muss in Produktion blockiert sein
    (BaFin/PSD2 nicht freigegeben). Kein Placeholder-Token/Mock-TAN darf je
    als echte Zahlung durchgehen.
    """

    @pytest.fixture
    def service(self) -> PaymentInitiationService:
        return PaymentInitiationService(
            psd2_service=Mock(),
            fints_service=Mock(),
            config=PaymentConfig(),
        )

    async def test_initiate_payment_blocked_in_production(
        self, service: PaymentInitiationService
    ) -> None:
        """initiate_payment liefert in Produktion success=False ohne DB-/Bankkontakt."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )
        db = AsyncMock()
        with patch(
            "app.services.banking.payment_initiation_service.settings"
        ) as mock_settings:
            mock_settings.is_production = True
            result = await service.initiate_payment(
                db=db, request=request, user_id=uuid4()
            )
        assert result.success is False
        assert "deaktiviert" in (result.error_message or "")
        # Guard greift VOR jedem DB-/Bankzugriff
        db.get.assert_not_called()

    async def test_complete_payment_sca_blocked_in_production(
        self, service: PaymentInitiationService
    ) -> None:
        """complete_payment_sca liefert in Produktion success=False ohne DB-Zugriff."""
        db = AsyncMock()
        with patch(
            "app.services.banking.payment_initiation_service.settings"
        ) as mock_settings:
            mock_settings.is_production = True
            result = await service.complete_payment_sca(
                db=db,
                payment_id=uuid4(),
                company_id=uuid4(),
                user_id=uuid4(),
            )
        assert result.success is False
        assert "deaktiviert" in (result.error_message or "")
        db.get.assert_not_called()

    async def test_guard_does_not_overblock_outside_production(
        self, service: PaymentInitiationService
    ) -> None:
        """Adversarial: ausserhalb Produktion greift der Guard NICHT -
        normaler Pfad (hier: Validierung) laeuft weiter."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("-5.00"),  # negativ -> Validierungsfehler, NICHT Prod-Guard
        )
        db = AsyncMock()
        with patch(
            "app.services.banking.payment_initiation_service.settings"
        ) as mock_settings:
            mock_settings.is_production = False
            result = await service.initiate_payment(
                db=db, request=request, user_id=uuid4()
            )
        assert result.success is False
        # Fehler stammt aus der Validierung (positiv), NICHT aus dem Prod-Guard
        assert "positiv" in (result.error_message or "")


class TestPaymentValidation:
    """Tests fuer Zahlungsvalidierung."""

    @pytest.fixture
    def service(self) -> PaymentInitiationService:
        """Erstellt Service-Instanz mit Mocks."""
        return PaymentInitiationService(
            psd2_service=Mock(),
            fints_service=Mock(),
            config=PaymentConfig(),
        )

    def test_validate_negative_amount(self, service: PaymentInitiationService) -> None:
        """Test: Negativer Betrag wird abgelehnt."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("-100.00"),
        )
        error = service._validate_payment_request(request)
        assert error is not None
        assert "positiv" in error

    def test_validate_zero_amount(self, service: PaymentInitiationService) -> None:
        """Test: Betrag null wird abgelehnt."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("0"),
        )
        error = service._validate_payment_request(request)
        assert error is not None

    def test_validate_exceeds_max(self, service: PaymentInitiationService) -> None:
        """Test: Betrag ueber Maximum wird abgelehnt."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("200000.00"),
        )
        error = service._validate_payment_request(request)
        assert error is not None
        assert "Maximum" in error or "Maximal" in error

    def test_validate_empty_creditor_name(self, service: PaymentInitiationService) -> None:
        """Test: Leerer Empfaengername wird abgelehnt."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )
        error = service._validate_payment_request(request)
        assert error is not None
        assert "Empfängername" in error or "Empfaengername" in error

    def test_validate_invalid_iban(self, service: PaymentInitiationService) -> None:
        """Test: Ungueltige IBAN wird abgelehnt."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="INVALID",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )
        error = service._validate_payment_request(request)
        assert error is not None
        assert "IBAN" in error

    def test_validate_past_execution_date(self, service: PaymentInitiationService) -> None:
        """Test: Ausfuehrungsdatum in der Vergangenheit wird abgelehnt."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("100.00"),
            execution_date=date.today() - timedelta(days=1),
        )
        error = service._validate_payment_request(request)
        assert error is not None
        assert "Vergangenheit" in error

    def test_validate_valid_request(self, service: PaymentInitiationService) -> None:
        """Test: Gueltige Anfrage wird akzeptiert."""
        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )
        error = service._validate_payment_request(request)
        assert error is None


class TestInitiatePayment:
    """Tests fuer initiate_payment Methode."""

    @pytest.fixture
    def service(self) -> PaymentInitiationService:
        """Erstellt Service-Instanz mit Mocks."""
        return PaymentInitiationService(
            psd2_service=Mock(),
            fints_service=Mock(),
            config=PaymentConfig(),
        )

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_account_not_found(self, service: PaymentInitiationService, mock_db: AsyncMock) -> None:
        """Test: Konto nicht gefunden liefert Fehler."""
        mock_db.get = AsyncMock(return_value=None)

        request = PaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )

        result = await service.initiate_payment(mock_db, request, uuid4())

        assert result.success is False
        assert "Konto" in result.error_message

    @pytest.mark.asyncio
    async def test_connection_company_mismatch(self, service: PaymentInitiationService, mock_db: AsyncMock) -> None:
        """Test: Firmen-Mismatch bei Verbindung wird abgelehnt."""
        mock_account = Mock()
        mock_account.connection_id = uuid4()

        mock_connection = Mock()
        mock_connection.company_id = uuid4()  # different company
        mock_connection.status = ConnectionStatus.ACTIVE.value

        mock_db.get = AsyncMock(side_effect=[mock_account, mock_connection])

        request = PaymentRequest(
            company_id=uuid4(),  # different from connection
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )

        result = await service.initiate_payment(mock_db, request, uuid4())

        assert result.success is False
        assert "Berechtigung" in result.error_message

    @pytest.mark.asyncio
    async def test_inactive_connection(self, service: PaymentInitiationService, mock_db: AsyncMock) -> None:
        """Test: Inaktive Verbindung wird abgelehnt."""
        company_id = uuid4()
        mock_account = Mock()
        mock_account.connection_id = uuid4()

        mock_connection = Mock()
        mock_connection.company_id = company_id
        mock_connection.status = "expired"

        mock_db.get = AsyncMock(side_effect=[mock_account, mock_connection])

        request = PaymentRequest(
            company_id=company_id,
            account_id=uuid4(),
            creditor_name="Test GmbH",
            creditor_iban="DE89370400440532013000",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )

        result = await service.initiate_payment(mock_db, request, uuid4())

        assert result.success is False
        assert "nicht aktiv" in result.error_message

    @pytest.mark.asyncio
    async def test_daily_limit_exceeded(self, service: PaymentInitiationService, mock_db: AsyncMock) -> None:
        """Test: Tageslimit wird geprueft und Ueberschreitung abgelehnt."""
        company_id = uuid4()
        mock_account = Mock()
        mock_account.connection_id = uuid4()

        mock_connection = Mock()
        mock_connection.company_id = company_id
        mock_connection.status = ConnectionStatus.ACTIVE.value

        mock_db.get = AsyncMock(side_effect=[mock_account, mock_connection])

        with patch.object(service, "_get_daily_payment_total", return_value=Decimal("499999.00")):
            request = PaymentRequest(
                company_id=company_id,
                account_id=uuid4(),
                creditor_name="Test GmbH",
                creditor_iban="DE89370400440532013000",
                creditor_bic=None,
                amount=Decimal("2000.00"),
            )
            result = await service.initiate_payment(mock_db, request, uuid4())

        assert result.success is False
        assert "Tageslimit" in result.error_message

    @pytest.mark.asyncio
    async def test_requires_approval_high_amount(self, service: PaymentInitiationService, mock_db: AsyncMock) -> None:
        """Test: Hoher Betrag erfordert Genehmigung."""
        company_id = uuid4()
        mock_account = Mock()
        mock_account.connection_id = uuid4()
        mock_account.iban = "DE89370400440532013000"

        mock_connection = Mock()
        mock_connection.company_id = company_id
        mock_connection.status = ConnectionStatus.ACTIVE.value
        mock_connection.id = uuid4()

        mock_db.get = AsyncMock(side_effect=[mock_account, mock_connection])
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch.object(service, "_get_daily_payment_total", return_value=Decimal("0")):
            request = PaymentRequest(
                company_id=company_id,
                account_id=uuid4(),
                creditor_name="Test GmbH",
                creditor_iban="DE89370400440532013000",
                creditor_bic=None,
                amount=Decimal("6000.00"),
            )
            result = await service.initiate_payment(mock_db, request, uuid4())

        assert result.success is True
        assert result.requires_approval is True


class TestApprovePayment:
    """Tests fuer approve_payment Methode."""

    @pytest.fixture
    def service(self) -> PaymentInitiationService:
        """Erstellt Service-Instanz."""
        return PaymentInitiationService(
            psd2_service=Mock(),
            fints_service=Mock(),
        )

    @pytest.mark.asyncio
    async def test_payment_not_found(self, service: PaymentInitiationService) -> None:
        """Test: Zahlung nicht gefunden bei Genehmigung."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        result = await service.approve_payment(mock_db, uuid4(), uuid4(), uuid4())
        assert result.success is False
        assert "nicht gefunden" in result.error_message

    @pytest.mark.asyncio
    async def test_self_approval_rejected(self, service: PaymentInitiationService) -> None:
        """Test: Eigene Zahlungen koennen nicht freigegeben werden."""
        mock_db = AsyncMock()
        user_id = uuid4()
        company_id = uuid4()

        mock_payment = Mock()
        mock_payment.company_id = company_id
        mock_payment.status = PaymentInitiationStatus.DRAFT.value
        mock_payment.created_by_id = user_id

        mock_db.get = AsyncMock(return_value=mock_payment)

        result = await service.approve_payment(mock_db, uuid4(), company_id, user_id)
        assert result.success is False
        assert "Eigene" in result.error_message


class TestCancelPayment:
    """Tests fuer cancel_payment Methode."""

    @pytest.fixture
    def service(self) -> PaymentInitiationService:
        """Erstellt Service-Instanz."""
        return PaymentInitiationService(
            psd2_service=Mock(),
            fints_service=Mock(),
        )

    @pytest.mark.asyncio
    async def test_cancel_draft_payment(self, service: PaymentInitiationService) -> None:
        """Test: Entwurfs-Zahlung kann storniert werden."""
        mock_db = AsyncMock()
        company_id = uuid4()

        mock_payment = Mock()
        mock_payment.company_id = company_id
        mock_payment.status = PaymentInitiationStatus.DRAFT.value
        mock_payment.id = uuid4()

        mock_db.get = AsyncMock(return_value=mock_payment)
        mock_db.commit = AsyncMock()

        result = await service.cancel_payment(mock_db, mock_payment.id, company_id, uuid4())
        assert result.success is True
        assert mock_payment.status == PaymentInitiationStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_executed_payment_rejected(self, service: PaymentInitiationService) -> None:
        """Test: Ausgefuehrte Zahlung kann nicht storniert werden."""
        mock_db = AsyncMock()
        company_id = uuid4()

        mock_payment = Mock()
        mock_payment.company_id = company_id
        mock_payment.status = PaymentInitiationStatus.ACCEPTED.value
        mock_payment.id = uuid4()

        mock_db.get = AsyncMock(return_value=mock_payment)

        result = await service.cancel_payment(mock_db, mock_payment.id, company_id, uuid4())
        assert result.success is False
        assert "nicht storniert" in result.error_message


class TestBatchPayment:
    """Tests fuer Batch-Zahlungen."""

    @pytest.fixture
    def service(self) -> PaymentInitiationService:
        """Erstellt Service-Instanz."""
        return PaymentInitiationService(
            psd2_service=Mock(),
            fints_service=Mock(),
        )

    @pytest.mark.asyncio
    async def test_batch_disabled(self) -> None:
        """Test: Deaktivierte Batch-Zahlungen werden abgelehnt."""
        service = PaymentInitiationService(
            psd2_service=Mock(),
            fints_service=Mock(),
            config=PaymentConfig(allow_batch_payments=False),
        )
        mock_db = AsyncMock()

        request = BatchPaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            payments=[],
        )

        result = await service.initiate_batch_payment(mock_db, request, uuid4())
        assert result.success is False
        assert "deaktiviert" in result.error_message

    @pytest.mark.asyncio
    async def test_batch_exceeds_max_size(self, service: PaymentInitiationService) -> None:
        """Test: Zu grosse Batch wird abgelehnt."""
        mock_db = AsyncMock()
        payments = [
            PaymentRequest(
                company_id=uuid4(),
                account_id=uuid4(),
                creditor_name=f"Test {i}",
                creditor_iban="DE89370400440532013000",
                creditor_bic=None,
                amount=Decimal("10.00"),
            )
            for i in range(101)
        ]

        request = BatchPaymentRequest(
            company_id=uuid4(),
            account_id=uuid4(),
            payments=payments,
        )

        result = await service.initiate_batch_payment(mock_db, request, uuid4())
        assert result.success is False
        assert "Maximal" in result.error_message or "100" in result.error_message
