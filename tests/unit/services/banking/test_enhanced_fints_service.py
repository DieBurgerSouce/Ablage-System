# -*- coding: utf-8 -*-
"""
Unit Tests fuer EnhancedFinTSService.

Vision 2026 Q4: Tests fuer erweiterte Banking-Integration.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio

from app.services.banking.enhanced_fints_service import (
    EnhancedFinTSService,
    BankConnection,
    BankAccountInfo,
    IncomingPayment,
    ReconciliationResult,
    SyncResult,
    ReconciliationConfig,
    ReconciliationType,
    NotificationChannel,
    SyncSchedule,
    ConnectionHealth,
    get_enhanced_fints_service,
)


class TestReconciliationType:
    """Tests fuer ReconciliationType Enum."""

    def test_reconciliation_type_values(self) -> None:
        """Test: ReconciliationType Enum hat alle erwarteten Werte."""
        assert ReconciliationType.EXACT_MATCH.value == "exact_match"
        assert ReconciliationType.REFERENCE_MATCH.value == "reference_match"
        assert ReconciliationType.AMOUNT_MATCH.value == "amount_match"
        assert ReconciliationType.SKONTO_MATCH.value == "skonto_match"
        assert ReconciliationType.PARTIAL_MATCH.value == "partial_match"
        assert ReconciliationType.MANUAL.value == "manual"


class TestSyncSchedule:
    """Tests fuer SyncSchedule Enum."""

    def test_sync_schedule_values(self) -> None:
        """Test: SyncSchedule Enum hat alle erwarteten Werte."""
        assert SyncSchedule.REALTIME.value == "realtime"
        assert SyncSchedule.HOURLY.value == "hourly"
        assert SyncSchedule.DAILY.value == "daily"
        assert SyncSchedule.MANUAL.value == "manual"


class TestConnectionHealth:
    """Tests fuer ConnectionHealth Enum."""

    def test_connection_health_values(self) -> None:
        """Test: ConnectionHealth Enum hat alle erwarteten Werte."""
        assert ConnectionHealth.HEALTHY.value == "healthy"
        assert ConnectionHealth.DEGRADED.value == "degraded"
        assert ConnectionHealth.UNHEALTHY.value == "unhealthy"
        assert ConnectionHealth.EXPIRED.value == "expired"


class TestBankConnection:
    """Tests fuer BankConnection."""

    def test_bank_connection_creation(self) -> None:
        """Test: BankConnection kann erstellt werden."""
        company_id = uuid4()
        connection = BankConnection(
            company_id=company_id,
            bank_name="Deutsche Bank",
            blz="10070000",
            bic="DEUTDEDB",
            fints_url="https://fints.deutsche-bank.de",
            sync_schedule=SyncSchedule.DAILY,
        )

        assert connection.company_id == company_id
        assert connection.bank_name == "Deutsche Bank"
        assert connection.blz == "10070000"
        assert connection.health_status == ConnectionHealth.HEALTHY
        assert connection.error_count == 0

    def test_bank_connection_to_dict(self) -> None:
        """Test: BankConnection to_dict Methode."""
        connection = BankConnection(
            bank_name="Sparkasse",
            blz="12345678",
            sync_schedule=SyncSchedule.HOURLY,
        )

        result = connection.to_dict()

        assert "id" in result
        assert result["bank_name"] == "Sparkasse"
        assert result["blz"] == "12345678"
        assert result["sync_schedule"] == "hourly"
        assert result["health_status"] == "healthy"


class TestBankAccountInfo:
    """Tests fuer BankAccountInfo."""

    def test_bank_account_creation(self) -> None:
        """Test: BankAccountInfo kann erstellt werden."""
        account = BankAccountInfo(
            iban="DE89370400440532013000",
            account_name="Geschaeftskonto",
            account_type="checking",
            currency="EUR",
            current_balance=Decimal("12500.50"),
            available_balance=Decimal("12000.00"),
        )

        assert account.iban == "DE89370400440532013000"
        assert account.account_name == "Geschaeftskonto"
        assert account.current_balance == Decimal("12500.50")
        assert account.currency == "EUR"


class TestIncomingPayment:
    """Tests fuer IncomingPayment."""

    def test_incoming_payment_creation(self) -> None:
        """Test: IncomingPayment kann erstellt werden."""
        payment = IncomingPayment(
            transaction_id="TX123456",
            account_iban="DE89370400440532013000",
            amount=Decimal("1500.00"),
            currency="EUR",
            sender_name="Muster GmbH",
            sender_iban="DE12500105170648489890",
            reference_text="RE-2026-001 Zahlung",
            booking_date=date.today(),
            confidence=0.95,
        )

        assert payment.transaction_id == "TX123456"
        assert payment.amount == Decimal("1500.00")
        assert payment.sender_name == "Muster GmbH"
        assert payment.confidence == 0.95


class TestReconciliationResult:
    """Tests fuer ReconciliationResult."""

    def test_reconciliation_result_exact_match(self) -> None:
        """Test: ReconciliationResult fuer exakten Match."""
        result = ReconciliationResult(
            transaction_id="TX123",
            invoice_id=uuid4(),
            reconciliation_type=ReconciliationType.EXACT_MATCH,
            confidence=0.99,
            matched_amount=Decimal("1000.00"),
            expected_amount=Decimal("1000.00"),
            difference=Decimal("0"),
            explanation="IBAN und Betrag stimmen exakt ueberein",
        )

        assert result.reconciliation_type == ReconciliationType.EXACT_MATCH
        assert result.confidence == 0.99
        assert result.difference == Decimal("0")

    def test_reconciliation_result_skonto_match(self) -> None:
        """Test: ReconciliationResult fuer Skonto-Match."""
        result = ReconciliationResult(
            transaction_id="TX456",
            invoice_id=uuid4(),
            reconciliation_type=ReconciliationType.SKONTO_MATCH,
            confidence=0.85,
            matched_amount=Decimal("980.00"),
            expected_amount=Decimal("1000.00"),
            difference=Decimal("20.00"),
            explanation="Betrag entspricht 2% Skonto-Abzug",
        )

        assert result.reconciliation_type == ReconciliationType.SKONTO_MATCH
        assert result.difference == Decimal("20.00")


class TestSyncResult:
    """Tests fuer SyncResult."""

    def test_sync_result_success(self) -> None:
        """Test: SyncResult fuer erfolgreichen Sync."""
        connection_id = uuid4()
        result = SyncResult(
            connection_id=connection_id,
            account_iban="DE89370400440532013000",
            success=True,
            transaction_count=50,
            new_transactions=10,
            reconciled_count=8,
            notifications_sent=5,
        )

        assert result.success is True
        assert result.transaction_count == 50
        assert result.new_transactions == 10
        assert result.reconciled_count == 8

    def test_sync_result_to_dict(self) -> None:
        """Test: SyncResult to_dict Methode."""
        result = SyncResult(
            connection_id=uuid4(),
            account_iban="DE89370400440532013000",
            success=True,
            transaction_count=25,
        )

        dict_result = result.to_dict()

        assert "connection_id" in dict_result
        assert dict_result["success"] is True
        assert dict_result["transaction_count"] == 25


class TestReconciliationConfig:
    """Tests fuer ReconciliationConfig."""

    def test_config_default_values(self) -> None:
        """Test: ReconciliationConfig Standardwerte."""
        config = ReconciliationConfig()

        assert len(config.strategies) == 5
        assert ReconciliationType.EXACT_MATCH in config.strategies
        assert config.auto_reconcile_threshold == 0.9
        assert config.suggest_threshold == 0.7
        assert config.amount_tolerance == Decimal("0.01")

    def test_config_custom_values(self) -> None:
        """Test: ReconciliationConfig mit benutzerdefinierten Werten."""
        config = ReconciliationConfig(
            auto_reconcile_threshold=0.95,
            suggest_threshold=0.8,
            large_payment_threshold=Decimal("50000"),
        )

        assert config.auto_reconcile_threshold == 0.95
        assert config.suggest_threshold == 0.8
        assert config.large_payment_threshold == Decimal("50000")


class TestEnhancedFinTSService:
    """Tests fuer EnhancedFinTSService."""

    @pytest.fixture
    def service(self) -> EnhancedFinTSService:
        """Erstellt Service-Instanz fuer Tests."""
        return EnhancedFinTSService()

    @pytest.fixture
    def service_with_config(self) -> EnhancedFinTSService:
        """Erstellt Service mit Custom-Config."""
        config = ReconciliationConfig(
            auto_reconcile_threshold=0.85,
            notify_on_reconciliation=True,
        )
        return EnhancedFinTSService(reconciliation_config=config)

    def test_service_initialization(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Service wird korrekt initialisiert."""
        assert service is not None
        assert service.reconciliation_config is not None
        assert len(service._connections) == 0

    def test_register_notification_handler(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Notification Handler registrieren."""
        handler = MagicMock()

        service.register_notification_handler(NotificationChannel.EMAIL, handler)

        assert NotificationChannel.EMAIL in service._notification_handlers
        assert service._notification_handlers[NotificationChannel.EMAIL] == handler

    @pytest.mark.asyncio
    async def test_add_bank_connection(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Bank-Verbindung hinzufuegen."""
        company_id = uuid4()

        connection = await service.add_bank_connection(
            company_id=company_id,
            bank_name="Commerzbank",
            blz="50040000",
            fints_url="https://fints.commerzbank.de",
            sync_schedule=SyncSchedule.DAILY,
        )

        assert connection is not None
        assert connection.company_id == company_id
        assert connection.bank_name == "Commerzbank"
        assert connection.sync_schedule == SyncSchedule.DAILY
        assert connection.next_sync_at is not None

    @pytest.mark.asyncio
    async def test_list_connections(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Bank-Verbindungen auflisten."""
        company_id = uuid4()

        await service.add_bank_connection(
            company_id=company_id,
            bank_name="Bank 1",
            blz="11111111",
            fints_url="https://fints1.de",
        )
        await service.add_bank_connection(
            company_id=company_id,
            bank_name="Bank 2",
            blz="22222222",
            fints_url="https://fints2.de",
        )

        connections = service.list_connections(company_id=company_id)

        assert len(connections) == 2

    @pytest.mark.asyncio
    async def test_get_connection(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Einzelne Verbindung abrufen."""
        company_id = uuid4()

        connection = await service.add_bank_connection(
            company_id=company_id,
            bank_name="Test Bank",
            blz="99999999",
            fints_url="https://test.de",
        )

        retrieved = service.get_connection(connection.id)

        assert retrieved is not None
        assert retrieved.id == connection.id
        assert retrieved.bank_name == "Test Bank"

    @pytest.mark.asyncio
    async def test_get_nonexistent_connection(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Nicht existierende Verbindung abrufen."""
        result = service.get_connection(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_sync_connection_not_found(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Sync fuer nicht existierende Verbindung."""
        result = await service.sync_connection(uuid4())

        assert result.success is False
        assert "nicht gefunden" in result.error

    @pytest.mark.asyncio
    async def test_check_connection_health_not_found(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Health-Check fuer nicht existierende Verbindung."""
        health = await service.check_connection_health(uuid4())
        assert health == ConnectionHealth.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_connection_health_healthy(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Health-Check fuer gesunde Verbindung."""
        company_id = uuid4()
        connection = await service.add_bank_connection(
            company_id=company_id,
            bank_name="Healthy Bank",
            blz="12345678",
            fints_url="https://healthy.de",
        )

        health = await service.check_connection_health(connection.id)
        assert health == ConnectionHealth.HEALTHY

    @pytest.mark.asyncio
    async def test_check_connection_health_with_errors(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Health-Check bei Verbindung mit Fehlern."""
        company_id = uuid4()
        connection = await service.add_bank_connection(
            company_id=company_id,
            bank_name="Error Bank",
            blz="12345678",
            fints_url="https://error.de",
        )

        # Simuliere Fehler
        connection.error_count = 3

        health = await service.check_connection_health(connection.id)
        assert health == ConnectionHealth.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_all_connections_health(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Health-Check fuer alle Verbindungen."""
        company_id = uuid4()

        await service.add_bank_connection(
            company_id=company_id,
            bank_name="Bank A",
            blz="11111111",
            fints_url="https://a.de",
        )
        await service.add_bank_connection(
            company_id=company_id,
            bank_name="Bank B",
            blz="22222222",
            fints_url="https://b.de",
        )

        health_map = await service.check_all_connections_health()

        assert len(health_map) == 2
        for connection_id, health in health_map.items():
            assert isinstance(health, ConnectionHealth)


class TestEnhancedFinTSServiceSync:
    """Tests fuer Sync-Funktionalitaet."""

    @pytest.fixture
    def service(self) -> EnhancedFinTSService:
        """Erstellt Service-Instanz fuer Tests."""
        return EnhancedFinTSService()

    @pytest.mark.asyncio
    async def test_sync_all_connections_empty(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Sync ohne Verbindungen."""
        results = await service.sync_all_connections()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_sync_skips_unhealthy(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Sync ueberspringt ungesunde Verbindungen."""
        company_id = uuid4()
        connection = await service.add_bank_connection(
            company_id=company_id,
            bank_name="Unhealthy Bank",
            blz="12345678",
            fints_url="https://unhealthy.de",
        )

        # Als unhealthy markieren
        connection.health_status = ConnectionHealth.UNHEALTHY

        results = await service.sync_all_connections(force=True)

        # Sollte uebersprungen werden
        assert len(results) == 0


class TestReconciliationStrategies:
    """Tests fuer Reconciliation-Strategien."""

    def test_strategies_order(self) -> None:
        """Test: Standard-Strategien haben korrekte Reihenfolge."""
        config = ReconciliationConfig()

        # Exakte Matches zuerst
        assert config.strategies[0] == ReconciliationType.EXACT_MATCH
        assert config.strategies[1] == ReconciliationType.REFERENCE_MATCH

    def test_confidence_thresholds(self) -> None:
        """Test: Confidence-Schwellenwerte sind sinnvoll."""
        config = ReconciliationConfig()

        assert config.auto_reconcile_threshold > config.suggest_threshold
        assert config.auto_reconcile_threshold <= 1.0
        assert config.suggest_threshold >= 0.5


class TestGetEnhancedFinTSService:
    """Tests fuer Factory-Funktion."""

    def test_get_service_singleton(self) -> None:
        """Test: Factory gibt Singleton-Instanz zurueck."""
        # Reset global instance for test
        import app.services.banking.enhanced_fints_service as module
        module._service_instance = None

        service1 = get_enhanced_fints_service()
        service2 = get_enhanced_fints_service()

        assert service1 is service2

    def test_get_service_with_config(self) -> None:
        """Test: Factory mit Config erstellt neue Instanz."""
        import app.services.banking.enhanced_fints_service as module
        module._service_instance = None

        config = ReconciliationConfig(auto_reconcile_threshold=0.95)
        service = get_enhanced_fints_service(reconciliation_config=config)

        assert service.reconciliation_config.auto_reconcile_threshold == 0.95

    def test_get_service_type(self) -> None:
        """Test: Factory gibt korrekte Instanz zurueck."""
        import app.services.banking.enhanced_fints_service as module
        module._service_instance = None

        service = get_enhanced_fints_service()
        assert isinstance(service, EnhancedFinTSService)


class TestNextSyncCalculation:
    """Tests fuer Sync-Zeitpunkt-Berechnung."""

    @pytest.fixture
    def service(self) -> EnhancedFinTSService:
        """Erstellt Service-Instanz fuer Tests."""
        return EnhancedFinTSService()

    def test_calculate_next_sync_realtime(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Realtime-Sync berechnet kurzes Intervall."""
        next_sync = service._calculate_next_sync(SyncSchedule.REALTIME)

        # Sollte in ca. 5 Minuten sein
        now = datetime.now(timezone.utc)
        diff = (next_sync - now).total_seconds()
        assert 280 <= diff <= 320  # ~5 Minuten mit Toleranz

    def test_calculate_next_sync_hourly(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Hourly-Sync berechnet 1-Stunden-Intervall."""
        next_sync = service._calculate_next_sync(SyncSchedule.HOURLY)

        now = datetime.now(timezone.utc)
        diff = (next_sync - now).total_seconds()
        assert 3500 <= diff <= 3700  # ~1 Stunde mit Toleranz

    def test_calculate_next_sync_daily(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Daily-Sync berechnet naechsten Tag."""
        next_sync = service._calculate_next_sync(SyncSchedule.DAILY)

        now = datetime.now(timezone.utc)
        diff = (next_sync - now).total_seconds() / 3600  # In Stunden
        assert diff > 0
        assert diff <= 48  # Maximal 2 Tage

    def test_calculate_next_sync_manual(
        self, service: EnhancedFinTSService
    ) -> None:
        """Test: Manual-Sync berechnet weit in der Zukunft."""
        next_sync = service._calculate_next_sync(SyncSchedule.MANUAL)

        now = datetime.now(timezone.utc)
        diff = (next_sync - now).days
        assert diff >= 364  # ~1 Jahr
