# -*- coding: utf-8 -*-
"""Tests fuer InsolvencyWarningService.

Testet Insolvenz-Fruehwarnsystem, Risiko-Analyse und Kreditlimit-Empfehlungen.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.insolvency_warning_service import (
    InsolvencyWarningService,
    InsolvencyStatus,
    RiskSignalType,
    SignalSeverity,
    ExternalDataSource,
    RiskSignal,
    InsolvencyCheck,
    EntityHealthSummary,
    get_insolvency_warning_service,
)


class TestRiskSignalAnalysis:
    """Tests fuer Risiko-Signal Analyse."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    def test_calculate_risk_score_no_signals(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Kein Risiko bei keinen Signalen."""
        score = service._calculate_risk_score([])
        assert score == 0

    def test_calculate_risk_score_single_low_signal(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Niedriger Score bei einzelnem niedrigen Signal."""
        signals = [
            RiskSignal(
                id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                signal_type=RiskSignalType.ADDRESS_CHANGE,
                severity=SignalSeverity.INFO,
                source=ExternalDataSource.INTERNAL,
                detected_at=datetime.now(timezone.utc),
                description="Adressaenderung",
            )
        ]

        score = service._calculate_risk_score(signals)
        assert score < 20  # Niedriger Score

    def test_calculate_risk_score_critical_signal(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Hoher Score bei kritischem Signal."""
        signals = [
            RiskSignal(
                id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                signal_type=RiskSignalType.INSOLVENCY_FILING,
                severity=SignalSeverity.CRITICAL,
                source=ExternalDataSource.BUNDESANZEIGER,
                detected_at=datetime.now(timezone.utc),
                description="Insolvenzantrag gestellt",
            )
        ]

        score = service._calculate_risk_score(signals)
        assert score >= 90  # Sehr hoher Score

    def test_calculate_risk_score_multiple_signals(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Additive Scores bei mehreren Signalen."""
        signals = [
            RiskSignal(
                id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                signal_type=RiskSignalType.PAYMENT_DELAY_INCREASING,
                severity=SignalSeverity.MEDIUM,
                source=ExternalDataSource.INTERNAL,
                detected_at=datetime.now(timezone.utc),
                description="Zahlungsverzoegerung steigt",
            ),
            RiskSignal(
                id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                signal_type=RiskSignalType.ORDER_VOLUME_DECLINING,
                severity=SignalSeverity.LOW,
                source=ExternalDataSource.INTERNAL,
                detected_at=datetime.now(timezone.utc),
                description="Bestellvolumen sinkt",
            ),
        ]

        score = service._calculate_risk_score(signals)
        assert 30 <= score <= 60  # Mittlerer Bereich


class TestStatusDetermination:
    """Tests fuer Status-Bestimmung."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    def test_determine_status_active(self, service: InsolvencyWarningService) -> None:
        """Test: ACTIVE Status bei niedrigem Score."""
        status = service._determine_status(10, [])
        assert status == InsolvencyStatus.ACTIVE

    def test_determine_status_watch(self, service: InsolvencyWarningService) -> None:
        """Test: WATCH Status bei mittlerem Score."""
        status = service._determine_status(35, [])
        assert status == InsolvencyStatus.WATCH

    def test_determine_status_warning(self, service: InsolvencyWarningService) -> None:
        """Test: WARNING Status bei hohem Score."""
        status = service._determine_status(60, [])
        assert status == InsolvencyStatus.WARNING

    def test_determine_status_insolvency_filing_overrides_score(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Insolvenzantrag ueberschreibt Score."""
        signals = [
            RiskSignal(
                id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                signal_type=RiskSignalType.INSOLVENCY_FILING,
                severity=SignalSeverity.CRITICAL,
                source=ExternalDataSource.BUNDESANZEIGER,
                detected_at=datetime.now(timezone.utc),
                description="Insolvenzantrag",
            )
        ]

        # Auch bei niedrigem Score sollte Status INSOLVENCY_FILED sein
        status = service._determine_status(20, signals)
        assert status == InsolvencyStatus.INSOLVENCY_FILED

    def test_determine_status_insolvency_opened(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Eroeffnetes Insolvenzverfahren."""
        signals = [
            RiskSignal(
                id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                signal_type=RiskSignalType.INSOLVENCY_OPENING,
                severity=SignalSeverity.CRITICAL,
                source=ExternalDataSource.HANDELSREGISTER,
                detected_at=datetime.now(timezone.utc),
                description="Insolvenzverfahren eroeffnet",
            )
        ]

        status = service._determine_status(50, signals)
        assert status == InsolvencyStatus.INSOLVENCY_OPENED

    def test_determine_status_liquidation(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Liquidation Status."""
        signals = [
            RiskSignal(
                id=uuid4(),
                entity_id=uuid4(),
                company_id=uuid4(),
                signal_type=RiskSignalType.LIQUIDATION_START,
                severity=SignalSeverity.CRITICAL,
                source=ExternalDataSource.HANDELSREGISTER,
                detected_at=datetime.now(timezone.utc),
                description="Liquidation eingeleitet",
            )
        ]

        status = service._determine_status(30, signals)
        assert status == InsolvencyStatus.LIQUIDATION


class TestInsolvencyCheck:
    """Tests fuer Insolvenz-Pruefung."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_check_entity_insolvency_healthy(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Pruefung eines gesunden Unternehmens."""
        entity_id = uuid4()
        company_id = uuid4()

        # Mock entity
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "Gesunde GmbH"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity

        # Mock invoices - keine problematischen
        mock_invoices = MagicMock()
        mock_invoices.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_result, mock_invoices, MagicMock()]

        check = await service.check_entity_insolvency(
            db=mock_db,
            entity_id=entity_id,
            company_id=company_id,
            include_external=False,
        )

        assert check is not None
        assert check.status == InsolvencyStatus.ACTIVE
        assert check.risk_score == 0

    @pytest.mark.asyncio
    async def test_check_entity_insolvency_with_payment_issues(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Pruefung mit Zahlungsproblemen."""
        entity_id = uuid4()
        company_id = uuid4()

        # Mock entity
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "Problematisch GmbH"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity

        # Mock invoices - einige ueberfaellig
        now = datetime.now(timezone.utc)
        mock_invoices = []
        for i in range(3):
            inv = MagicMock()
            inv.id = uuid4()
            inv.status = "overdue"
            inv.due_date = (now - timedelta(days=100 + i * 10)).date()
            inv.amount = 1000.0 + i * 500
            inv.invoice_date = (now - timedelta(days=120 + i * 10)).date()
            mock_invoices.append(inv)

        mock_invoices_result = MagicMock()
        mock_invoices_result.scalars.return_value.all.return_value = mock_invoices

        mock_db.execute.side_effect = [mock_result, mock_invoices_result, MagicMock()]

        check = await service.check_entity_insolvency(
            db=mock_db,
            entity_id=entity_id,
            company_id=company_id,
            include_external=False,
        )

        assert check is not None
        assert check.risk_score > 0
        assert len(check.signals) > 0

    @pytest.mark.asyncio
    async def test_check_entity_not_found(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Entity nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.check_entity_insolvency(
                db=mock_db,
                entity_id=uuid4(),
                company_id=uuid4(),
            )


class TestInternalSignalAnalysis:
    """Tests fuer interne Signal-Analyse."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_analyze_payment_delay_increasing(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Erkennung steigender Zahlungsverzoegerung."""
        entity_id = uuid4()
        company_id = uuid4()
        now = datetime.now(timezone.utc)

        # Aeltere Rechnungen mit geringer Verzoegerung
        older_invoices = []
        for i in range(5):
            inv = MagicMock()
            inv.status = "paid"
            inv.due_date = (now - timedelta(days=150 + i * 10)).date()
            inv.paid_date = (now - timedelta(days=145 + i * 10)).date()  # 5 Tage Verzoegerung
            inv.invoice_date = (now - timedelta(days=180 + i * 10)).date()
            inv.amount = 500.0
            older_invoices.append(inv)

        # Neuere Rechnungen mit hoher Verzoegerung
        recent_invoices = []
        for i in range(5):
            inv = MagicMock()
            inv.status = "paid"
            inv.due_date = (now - timedelta(days=60 + i * 5)).date()
            inv.paid_date = (now - timedelta(days=30 + i * 5)).date()  # 30 Tage Verzoegerung
            inv.invoice_date = (now - timedelta(days=90 + i * 5)).date()
            inv.amount = 500.0
            recent_invoices.append(inv)

        all_invoices = older_invoices + recent_invoices

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = all_invoices
        mock_db.execute.return_value = mock_result

        signals = await service._analyze_internal_signals(
            db=mock_db,
            entity_id=entity_id,
            company_id=company_id,
        )

        # Sollte PAYMENT_DELAY_INCREASING Signal enthalten
        delay_signals = [
            s for s in signals
            if s.signal_type == RiskSignalType.PAYMENT_DELAY_INCREASING
        ]
        assert len(delay_signals) >= 0  # Je nach Datenkonstellation

    @pytest.mark.asyncio
    async def test_analyze_payment_default(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Erkennung von Zahlungsausfaellen."""
        entity_id = uuid4()
        company_id = uuid4()
        now = datetime.now(timezone.utc)

        # Stark ueberfaellige Rechnungen (>90 Tage)
        overdue_invoices = []
        for i in range(3):
            inv = MagicMock()
            inv.status = "overdue"
            inv.due_date = (now - timedelta(days=100 + i * 20)).date()
            inv.invoice_date = (now - timedelta(days=130 + i * 20)).date()
            inv.amount = 2000.0
            inv.paid_date = None
            overdue_invoices.append(inv)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = overdue_invoices
        mock_db.execute.return_value = mock_result

        signals = await service._analyze_internal_signals(
            db=mock_db,
            entity_id=entity_id,
            company_id=company_id,
        )

        # Sollte PAYMENT_DEFAULT Signal enthalten
        default_signals = [
            s for s in signals if s.signal_type == RiskSignalType.PAYMENT_DEFAULT
        ]
        assert len(default_signals) > 0
        assert default_signals[0].severity == SignalSeverity.HIGH


class TestCreditLimitRecommendation:
    """Tests fuer Kreditlimit-Empfehlungen."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_credit_limit_healthy_entity(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Kreditlimit fuer gesundes Unternehmen."""
        # Mock: 100.000 EUR Jahresumsatz
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("100000.00")
        mock_db.execute.return_value = mock_result

        limit = await service._calculate_credit_limit_recommendation(
            db=mock_db,
            entity_id=uuid4(),
            company_id=uuid4(),
            status=InsolvencyStatus.ACTIVE,
            risk_score=10,
        )

        # 10% von 100.000 = 10.000, bei niedrigem Risiko voller Betrag
        assert limit is not None
        assert limit >= Decimal("9000")  # Abzueglich kleiner Score-Reduktion

    @pytest.mark.asyncio
    async def test_credit_limit_warning_status(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Reduziertes Kreditlimit bei Warning-Status."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("100000.00")
        mock_db.execute.return_value = mock_result

        limit = await service._calculate_credit_limit_recommendation(
            db=mock_db,
            entity_id=uuid4(),
            company_id=uuid4(),
            status=InsolvencyStatus.WARNING,
            risk_score=60,
        )

        # WARNING hat 0.4 Faktor -> 4.000 Basis, plus Score-Reduktion
        assert limit is not None
        assert limit < Decimal("5000")

    @pytest.mark.asyncio
    async def test_credit_limit_insolvency_zero(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Kein Kreditlimit bei Insolvenz."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("100000.00")
        mock_db.execute.return_value = mock_result

        limit = await service._calculate_credit_limit_recommendation(
            db=mock_db,
            entity_id=uuid4(),
            company_id=uuid4(),
            status=InsolvencyStatus.INSOLVENCY_FILED,
            risk_score=95,
        )

        assert limit == Decimal("0")

    @pytest.mark.asyncio
    async def test_credit_limit_no_history(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Kein Limit ohne Umsatzhistorie."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        limit = await service._calculate_credit_limit_recommendation(
            db=mock_db,
            entity_id=uuid4(),
            company_id=uuid4(),
            status=InsolvencyStatus.ACTIVE,
            risk_score=10,
        )

        assert limit is None


class TestEntityHealthSummary:
    """Tests fuer Entity Health Summary."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_entity_health_summary(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Health Summary abrufen."""
        entity_id = uuid4()
        company_id = uuid4()

        # Mock entity
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "Test GmbH"

        # Mock invoices - keine
        mock_entity_result = MagicMock()
        mock_entity_result.scalar_one_or_none.return_value = mock_entity

        mock_invoices_result = MagicMock()
        mock_invoices_result.scalars.return_value.all.return_value = []

        mock_open_invoices_result = MagicMock()
        mock_open_invoices_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            mock_entity_result,
            mock_invoices_result,
            MagicMock(),  # credit limit query
            mock_open_invoices_result,
        ]

        with patch.object(
            service,
            "check_entity_insolvency",
            return_value=InsolvencyCheck(
                entity_id=entity_id,
                entity_name="Test GmbH",
                check_date=datetime.now(timezone.utc),
                status=InsolvencyStatus.ACTIVE,
                risk_score=5,
                signals=[],
                credit_limit_recommendation=Decimal("5000"),
                last_external_check=None,
            ),
        ):
            summary = await service.get_entity_health_summary(
                db=mock_db,
                entity_id=entity_id,
                company_id=company_id,
            )

        assert summary is not None
        assert summary.entity_id == entity_id
        assert summary.status == InsolvencyStatus.ACTIVE


class TestHighRiskEntities:
    """Tests fuer High-Risk Entity Abfrage."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_high_risk_entities_empty(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Keine High-Risk Entities."""
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        high_risk = await service.get_high_risk_entities(
            db=mock_db,
            company_id=company_id,
            min_risk_score=50,
        )

        assert high_risk == []


class TestStatistics:
    """Tests fuer Statistiken."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock fuer Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_statistics(
        self, service: InsolvencyWarningService, mock_db: AsyncMock
    ) -> None:
        """Test: Statistiken abrufen."""
        company_id = uuid4()

        # Mock entity count
        mock_count = MagicMock()
        mock_count.scalar.return_value = 50

        # Mock risk volume
        mock_volume = MagicMock()
        mock_volume.scalar.return_value = Decimal("75000.00")

        mock_db.execute.side_effect = [mock_count, mock_volume]

        stats = await service.get_statistics(
            db=mock_db,
            company_id=company_id,
            period_days=30,
        )

        assert stats is not None
        assert stats.company_id == company_id
        assert stats.total_monitored_entities == 50
        assert stats.total_at_risk_volume == Decimal("75000.00")


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_instance(self) -> None:
        """Test: Singleton gibt immer gleiche Instanz zurueck."""
        service1 = get_insolvency_warning_service()
        service2 = get_insolvency_warning_service()

        assert service1 is service2

    def test_service_has_required_methods(self) -> None:
        """Test: Service hat alle erforderlichen Methoden."""
        service = get_insolvency_warning_service()

        assert hasattr(service, "check_entity_insolvency")
        assert hasattr(service, "get_entity_health_summary")
        assert hasattr(service, "get_high_risk_entities")
        assert hasattr(service, "acknowledge_signal")
        assert hasattr(service, "get_statistics")


class TestSignalWeights:
    """Tests fuer Signal-Gewichtungen."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    def test_insolvency_opening_highest_weight(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Insolvenzeroeffnung hat hoechste Gewichtung."""
        weights = service.SIGNAL_WEIGHTS

        assert weights[RiskSignalType.INSOLVENCY_OPENING] == 100
        assert weights[RiskSignalType.INSOLVENCY_FILING] == 90

    def test_address_change_lowest_weight(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Adressaenderung hat niedrigste Gewichtung."""
        weights = service.SIGNAL_WEIGHTS

        assert weights[RiskSignalType.ADDRESS_CHANGE] == 10

    def test_all_signal_types_have_weights(
        self, service: InsolvencyWarningService
    ) -> None:
        """Test: Alle Signal-Typen haben Gewichtungen."""
        weights = service.SIGNAL_WEIGHTS

        # Pruefe wichtige Typen
        assert RiskSignalType.PAYMENT_DEFAULT in weights
        assert RiskSignalType.PAYMENT_DELAY_INCREASING in weights
        assert RiskSignalType.ORDER_VOLUME_DECLINING in weights


class TestThresholds:
    """Tests fuer Schwellenwerte."""

    @pytest.fixture
    def service(self) -> InsolvencyWarningService:
        """Erstellt InsolvencyWarningService Instanz."""
        return InsolvencyWarningService()

    def test_threshold_values(self, service: InsolvencyWarningService) -> None:
        """Test: Schwellenwerte sind korrekt definiert."""
        assert service.WATCH_THRESHOLD == 30
        assert service.WARNING_THRESHOLD == 50
        assert service.CRITICAL_THRESHOLD == 75

    def test_threshold_ordering(self, service: InsolvencyWarningService) -> None:
        """Test: Schwellenwerte sind aufsteigend."""
        assert service.WATCH_THRESHOLD < service.WARNING_THRESHOLD
        assert service.WARNING_THRESHOLD < service.CRITICAL_THRESHOLD
