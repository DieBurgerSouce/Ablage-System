# -*- coding: utf-8 -*-
"""
Unit Tests fuer HandelsregisterMonitoringService.

Vision 2026 Q4: Tests fuer erweitertes Handelsregister-Monitoring.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio

from app.services.external.handelsregister_monitoring_service import (
    HandelsregisterMonitoringService,
    CompanyValidation,
    InsolvencyRecord,
    MonitoringAlert,
    AnnualReport,
    MonitoredEntity,
    CompanyStatus,
    InsolvencyType,
    MonitoringEvent,
    ValidationResult,
    get_handelsregister_monitoring_service,
)


class TestCompanyStatus:
    """Tests fuer CompanyStatus Enum."""

    def test_company_status_values(self) -> None:
        """Test: CompanyStatus Enum hat alle erwarteten Werte."""
        assert CompanyStatus.ACTIVE.value == "active"
        assert CompanyStatus.IN_LIQUIDATION.value == "in_liquidation"
        assert CompanyStatus.DISSOLVED.value == "dissolved"
        assert CompanyStatus.MERGED.value == "merged"
        assert CompanyStatus.UNKNOWN.value == "unknown"


class TestInsolvencyType:
    """Tests fuer InsolvencyType Enum."""

    def test_insolvency_type_values(self) -> None:
        """Test: InsolvencyType Enum hat alle erwarteten Werte."""
        assert InsolvencyType.NONE.value == "none"
        assert InsolvencyType.APPLICATION.value == "application"
        assert InsolvencyType.PRELIMINARY.value == "preliminary"
        assert InsolvencyType.OPENED.value == "opened"
        assert InsolvencyType.SELF_ADMIN.value == "self_administration"
        assert InsolvencyType.REJECTED.value == "rejected"
        assert InsolvencyType.CONCLUDED.value == "concluded"


class TestMonitoringEvent:
    """Tests fuer MonitoringEvent Enum."""

    def test_monitoring_event_values(self) -> None:
        """Test: MonitoringEvent Enum hat alle erwarteten Werte."""
        assert MonitoringEvent.NAME_CHANGE.value == "name_change"
        assert MonitoringEvent.ADDRESS_CHANGE.value == "address_change"
        assert MonitoringEvent.MANAGEMENT_CHANGE.value == "management_change"
        assert MonitoringEvent.CAPITAL_CHANGE.value == "capital_change"
        assert MonitoringEvent.STATUS_CHANGE.value == "status_change"
        assert MonitoringEvent.INSOLVENCY_NOTICE.value == "insolvency_notice"
        assert MonitoringEvent.ANNUAL_REPORT.value == "annual_report"
        assert MonitoringEvent.LIQUIDATION.value == "liquidation"


class TestValidationResult:
    """Tests fuer ValidationResult Enum."""

    def test_validation_result_values(self) -> None:
        """Test: ValidationResult Enum hat alle erwarteten Werte."""
        assert ValidationResult.VALID.value == "valid"
        assert ValidationResult.INVALID.value == "invalid"
        assert ValidationResult.INACTIVE.value == "inactive"
        assert ValidationResult.WARNING.value == "warning"
        assert ValidationResult.PENDING.value == "pending"


class TestCompanyValidation:
    """Tests fuer CompanyValidation."""

    def test_company_validation_creation(self) -> None:
        """Test: CompanyValidation kann erstellt werden."""
        entity_id = uuid4()
        validation = CompanyValidation(
            entity_id=entity_id,
            company_name="Muster GmbH",
            result=ValidationResult.VALID,
            register_court="Amtsgericht Muenchen",
            register_number="HRB 123456",
            legal_form="GmbH",
            status=CompanyStatus.ACTIVE,
        )

        assert validation.entity_id == entity_id
        assert validation.company_name == "Muster GmbH"
        assert validation.result == ValidationResult.VALID
        assert validation.legal_form == "GmbH"

    def test_company_validation_to_dict(self) -> None:
        """Test: CompanyValidation to_dict Methode."""
        validation = CompanyValidation(
            entity_id=uuid4(),
            company_name="Test AG",
            result=ValidationResult.VALID,
            register_court="Amtsgericht Frankfurt",
            register_number="HRB 654321",
            legal_form="AG",
            status=CompanyStatus.ACTIVE,
        )

        result = validation.to_dict()

        assert "entity_id" in result
        assert result["company_name"] == "Test AG"
        assert result["result"] == "valid"
        assert result["legal_form"] == "AG"

    def test_company_validation_with_discrepancies(self) -> None:
        """Test: CompanyValidation mit Abweichungen."""
        validation = CompanyValidation(
            entity_id=uuid4(),
            company_name="Beispiel GmbH",
            result=ValidationResult.WARNING,
            name_matches=False,
            address_matches=True,
            discrepancies=[
                "Firmenname im Register abweichend",
            ],
        )

        assert validation.result == ValidationResult.WARNING
        assert validation.name_matches is False
        assert len(validation.discrepancies) == 1


class TestInsolvencyRecord:
    """Tests fuer InsolvencyRecord."""

    def test_insolvency_record_creation(self) -> None:
        """Test: InsolvencyRecord kann erstellt werden."""
        record = InsolvencyRecord(
            company_name="Pleite GmbH",
            court="Amtsgericht Muenchen",
            case_number="IN 1234/26",
            insolvency_type=InsolvencyType.OPENED,
            filing_date=date(2026, 1, 1),
            opening_date=date(2026, 1, 15),
            administrator="RA Dr. Insolvenz",
            creditor_meeting_date=date(2026, 2, 15),
        )

        assert record.company_name == "Pleite GmbH"
        assert record.insolvency_type == InsolvencyType.OPENED
        assert record.administrator == "RA Dr. Insolvenz"

    def test_insolvency_record_to_dict(self) -> None:
        """Test: InsolvencyRecord to_dict Methode."""
        record = InsolvencyRecord(
            company_name="Test Insolvenz GmbH",
            court="Amtsgericht Berlin",
            case_number="IN 5678/26",
            insolvency_type=InsolvencyType.APPLICATION,
            filing_date=date(2026, 1, 10),
        )

        result = record.to_dict()

        assert result["company_name"] == "Test Insolvenz GmbH"
        assert result["insolvency_type"] == "application"
        assert result["filing_date"] == "2026-01-10"


class TestMonitoringAlert:
    """Tests fuer MonitoringAlert."""

    def test_monitoring_alert_creation(self) -> None:
        """Test: MonitoringAlert kann erstellt werden."""
        entity_id = uuid4()
        company_id = uuid4()

        alert = MonitoringAlert(
            entity_id=entity_id,
            company_id=company_id,
            entity_name="Risiko GmbH",
            event_type=MonitoringEvent.INSOLVENCY_NOTICE,
            severity="critical",
            title="Insolvenzverfahren eroeffnet",
            message="Amtsgericht Muenchen hat Insolvenzverfahren eroeffnet",
        )

        assert alert.entity_id == entity_id
        assert alert.event_type == MonitoringEvent.INSOLVENCY_NOTICE
        assert alert.severity == "critical"
        assert alert.acknowledged is False

    def test_monitoring_alert_to_dict(self) -> None:
        """Test: MonitoringAlert to_dict Methode."""
        alert = MonitoringAlert(
            entity_id=uuid4(),
            company_id=uuid4(),
            entity_name="Test GmbH",
            event_type=MonitoringEvent.STATUS_CHANGE,
            severity="high",
            title="Status geaendert",
            message="Status von aktiv zu liquidation",
            old_value="active",
            new_value="in_liquidation",
        )

        result = alert.to_dict()

        assert "id" in result
        assert result["event_type"] == "status_change"
        assert result["old_value"] == "active"
        assert result["new_value"] == "in_liquidation"


class TestAnnualReport:
    """Tests fuer AnnualReport."""

    def test_annual_report_creation(self) -> None:
        """Test: AnnualReport kann erstellt werden."""
        report = AnnualReport(
            company_name="Erfolg AG",
            fiscal_year=2024,
            publication_date=date(2025, 6, 30),
            total_assets=Decimal("5000000.00"),
            equity=Decimal("2000000.00"),
            revenue=Decimal("8000000.00"),
            profit_loss=Decimal("500000.00"),
            employees=50,
            equity_ratio=Decimal("40.0"),
        )

        assert report.company_name == "Erfolg AG"
        assert report.fiscal_year == 2024
        assert report.equity_ratio == Decimal("40.0")

    def test_annual_report_to_dict(self) -> None:
        """Test: AnnualReport to_dict Methode."""
        report = AnnualReport(
            company_name="Test GmbH",
            fiscal_year=2023,
            publication_date=date(2024, 6, 30),
            total_assets=Decimal("1000000.00"),
            equity=Decimal("400000.00"),
            revenue=Decimal("2000000.00"),
            document_type="abbreviated",
        )

        result = report.to_dict()

        assert result["fiscal_year"] == 2023
        assert result["document_type"] == "abbreviated"
        assert result["total_assets"] == "1000000.00"


class TestMonitoredEntity:
    """Tests fuer MonitoredEntity."""

    def test_monitored_entity_creation(self) -> None:
        """Test: MonitoredEntity kann erstellt werden."""
        entity_id = uuid4()
        company_id = uuid4()

        monitored = MonitoredEntity(
            entity_id=entity_id,
            company_id=company_id,
            entity_name="Monitored GmbH",
            register_number="HRB 123456",
            monitor_insolvency=True,
            monitor_changes=True,
            monitor_annual_reports=False,
        )

        assert monitored.entity_id == entity_id
        assert monitored.entity_name == "Monitored GmbH"
        assert monitored.monitor_insolvency is True
        assert monitored.monitor_annual_reports is False


class TestHandelsregisterMonitoringService:
    """Tests fuer HandelsregisterMonitoringService."""

    @pytest.fixture
    def service(self) -> HandelsregisterMonitoringService:
        """Erstellt Service-Instanz fuer Tests."""
        return HandelsregisterMonitoringService()

    def test_service_initialization(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Service wird korrekt initialisiert."""
        assert service is not None
        assert len(service._monitored_entities) == 0
        assert len(service._alerts) == 0

    @pytest.mark.asyncio
    async def test_validate_company_valid(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Erfolgreiche Firmen-Validierung."""
        entity_id = uuid4()
        company_id = uuid4()

        validation = await service.validate_company(
            entity_id=entity_id,
            company_id=company_id,
            company_name="Normal GmbH",
            address="Musterstrasse 1, 80331 Muenchen",
        )

        assert validation is not None
        assert validation.result == ValidationResult.VALID
        assert validation.status == CompanyStatus.ACTIVE
        assert validation.legal_form == "GmbH"

    @pytest.mark.asyncio
    async def test_validate_company_invalid(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Firma nicht gefunden."""
        entity_id = uuid4()
        company_id = uuid4()

        validation = await service.validate_company(
            entity_id=entity_id,
            company_id=company_id,
            company_name="INVALID Test Company",
        )

        assert validation.result == ValidationResult.INVALID
        assert "nicht gefunden" in validation.discrepancies[0]

    @pytest.mark.asyncio
    async def test_validate_company_insolvent(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Firma mit Insolvenzverfahren."""
        entity_id = uuid4()
        company_id = uuid4()

        validation = await service.validate_company(
            entity_id=entity_id,
            company_id=company_id,
            company_name="INSOLVENT GmbH",
        )

        assert validation.result == ValidationResult.WARNING
        assert validation.insolvency_status == InsolvencyType.OPENED

    @pytest.mark.asyncio
    async def test_validate_company_liquidation(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Aufgeloeste Firma."""
        entity_id = uuid4()
        company_id = uuid4()

        validation = await service.validate_company(
            entity_id=entity_id,
            company_id=company_id,
            company_name="LIQUIDATION GmbH",
        )

        assert validation.result == ValidationResult.INACTIVE
        assert validation.status == CompanyStatus.DISSOLVED

    @pytest.mark.asyncio
    async def test_check_insolvency_none(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Keine Insolvenz gefunden."""
        entity_id = uuid4()

        insolvency = await service.check_insolvency(
            entity_id=entity_id,
            company_name="Gesunde GmbH",
        )

        assert insolvency is None

    @pytest.mark.asyncio
    async def test_check_insolvency_found(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Insolvenz gefunden."""
        entity_id = uuid4()

        insolvency = await service.check_insolvency(
            entity_id=entity_id,
            company_name="INSOLVENT AG",
        )

        assert insolvency is not None
        assert insolvency.insolvency_type == InsolvencyType.OPENED
        assert insolvency.administrator == "RA Dr. Mustermann"

    @pytest.mark.asyncio
    async def test_get_annual_reports(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Jahresabschluesse abrufen."""
        entity_id = uuid4()

        reports = await service.get_annual_reports(
            entity_id=entity_id,
            company_name="Test AG",
            years=3,
        )

        assert len(reports) == 3
        # Reports sollten nach Jahr absteigend sortiert sein
        assert all(isinstance(r, AnnualReport) for r in reports)

    @pytest.mark.asyncio
    async def test_start_monitoring(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Monitoring starten."""
        entity_id = uuid4()
        company_id = uuid4()

        monitored = await service.start_monitoring(
            entity_id=entity_id,
            company_id=company_id,
            entity_name="Monitor Me GmbH",
            register_number="HRB 999888",
        )

        assert monitored is not None
        assert monitored.entity_name == "Monitor Me GmbH"
        assert entity_id in service._monitored_entities

    @pytest.mark.asyncio
    async def test_stop_monitoring(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Monitoring stoppen."""
        entity_id = uuid4()
        company_id = uuid4()

        await service.start_monitoring(
            entity_id=entity_id,
            company_id=company_id,
            entity_name="Stop Monitor GmbH",
        )

        result = await service.stop_monitoring(entity_id)

        assert result is True
        assert entity_id not in service._monitored_entities

    @pytest.mark.asyncio
    async def test_stop_monitoring_not_found(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Stoppen fuer nicht ueberwachte Entity."""
        result = await service.stop_monitoring(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_get_monitored_entities(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Ueberwachte Entities auflisten."""
        company_id = uuid4()

        await service.start_monitoring(
            entity_id=uuid4(),
            company_id=company_id,
            entity_name="Entity 1",
        )
        await service.start_monitoring(
            entity_id=uuid4(),
            company_id=company_id,
            entity_name="Entity 2",
        )

        entities = service.get_monitored_entities(company_id=company_id)

        assert len(entities) == 2

    @pytest.mark.asyncio
    async def test_acknowledge_alert(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Alert bestaetigen."""
        alert = MonitoringAlert(
            entity_id=uuid4(),
            company_id=uuid4(),
            entity_name="Alert Test",
            event_type=MonitoringEvent.STATUS_CHANGE,
            severity="medium",
            title="Test Alert",
            message="Test Message",
        )
        service._alerts[alert.id] = alert

        user_id = uuid4()
        result = await service.acknowledge_alert(alert.id, user_id)

        assert result is True
        assert alert.acknowledged is True
        assert alert.acknowledged_by == user_id
        assert alert.acknowledged_at is not None

    @pytest.mark.asyncio
    async def test_acknowledge_alert_not_found(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Nicht existierenden Alert bestaetigen."""
        result = await service.acknowledge_alert(uuid4(), uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_get_pending_alerts(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Ausstehende Alerts abrufen."""
        company_id = uuid4()

        # Fuege Alerts hinzu
        alert1 = MonitoringAlert(
            entity_id=uuid4(),
            company_id=company_id,
            entity_name="Alert 1",
            event_type=MonitoringEvent.STATUS_CHANGE,
            severity="high",
            title="Alert 1",
            message="Message 1",
        )
        alert2 = MonitoringAlert(
            entity_id=uuid4(),
            company_id=company_id,
            entity_name="Alert 2",
            event_type=MonitoringEvent.INSOLVENCY_NOTICE,
            severity="critical",
            title="Alert 2",
            message="Message 2",
            acknowledged=True,  # Dieser sollte nicht erscheinen
        )

        service._alerts[alert1.id] = alert1
        service._alerts[alert2.id] = alert2

        pending = await service.get_pending_alerts(company_id=company_id)

        assert len(pending) == 1
        assert pending[0].id == alert1.id

    @pytest.mark.asyncio
    async def test_calculate_risk_impact_not_monitored(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Risk-Impact fuer nicht ueberwachte Entity."""
        impact = await service.calculate_risk_impact(uuid4())

        assert impact["risk_factor"] == 0
        assert "Nicht ueberwacht" in impact["reason"]

    @pytest.mark.asyncio
    async def test_calculate_risk_impact_valid(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Risk-Impact fuer valide Entity."""
        entity_id = uuid4()
        company_id = uuid4()

        # Starte Monitoring und validiere
        await service.validate_company(
            entity_id=entity_id,
            company_id=company_id,
            company_name="Valid Company GmbH",
        )

        impact = await service.calculate_risk_impact(entity_id)

        assert impact["entity_id"] == str(entity_id)
        assert "factors" in impact


class TestLegalFormDetection:
    """Tests fuer Rechtsform-Erkennung."""

    @pytest.fixture
    def service(self) -> HandelsregisterMonitoringService:
        """Erstellt Service-Instanz fuer Tests."""
        return HandelsregisterMonitoringService()

    @pytest.mark.asyncio
    async def test_detect_gmbh(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: GmbH wird erkannt."""
        validation = await service.validate_company(
            entity_id=uuid4(),
            company_id=uuid4(),
            company_name="Muster GmbH",
        )
        assert validation.legal_form == "GmbH"

    @pytest.mark.asyncio
    async def test_detect_ag(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: AG wird erkannt."""
        validation = await service.validate_company(
            entity_id=uuid4(),
            company_id=uuid4(),
            company_name="Beispiel AG",
        )
        assert validation.legal_form == "AG"

    @pytest.mark.asyncio
    async def test_detect_ug(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: UG wird erkannt."""
        validation = await service.validate_company(
            entity_id=uuid4(),
            company_id=uuid4(),
            company_name="Startup UG",
        )
        assert validation.legal_form == "UG"

    @pytest.mark.asyncio
    async def test_detect_kg(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: KG wird erkannt."""
        validation = await service.validate_company(
            entity_id=uuid4(),
            company_id=uuid4(),
            company_name="Handel KG",
        )
        assert validation.legal_form == "KG"


class TestGetHandelsregisterMonitoringService:
    """Tests fuer Factory-Funktion."""

    def test_get_service_singleton(self) -> None:
        """Test: Factory gibt Singleton-Instanz zurueck."""
        # Reset global instance for test
        import app.services.external.handelsregister_monitoring_service as module
        module._service_instance = None

        service1 = get_handelsregister_monitoring_service()
        service2 = get_handelsregister_monitoring_service()

        assert service1 is service2

    def test_get_service_type(self) -> None:
        """Test: Factory gibt korrekte Instanz zurueck."""
        import app.services.external.handelsregister_monitoring_service as module
        module._service_instance = None

        service = get_handelsregister_monitoring_service()
        assert isinstance(service, HandelsregisterMonitoringService)


class TestMonitoringCheckWorkflow:
    """Tests fuer Monitoring-Check-Workflow."""

    @pytest.fixture
    def service(self) -> HandelsregisterMonitoringService:
        """Erstellt Service-Instanz fuer Tests."""
        return HandelsregisterMonitoringService()

    @pytest.mark.asyncio
    async def test_run_monitoring_check_empty(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Monitoring-Check ohne Entities."""
        alerts = await service.run_monitoring_check()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_run_monitoring_check_skips_not_due(
        self, service: HandelsregisterMonitoringService
    ) -> None:
        """Test: Monitoring-Check ueberspringt nicht faellige Entities."""
        entity_id = uuid4()

        monitored = await service.start_monitoring(
            entity_id=entity_id,
            company_id=uuid4(),
            entity_name="Not Due GmbH",
        )

        # Setze next_check_at in die Zukunft
        monitored.next_check_at = datetime.now(timezone.utc) + timedelta(days=7)

        alerts = await service.run_monitoring_check()

        # Entity sollte nicht geprueft worden sein
        assert monitored.last_check_at is None
