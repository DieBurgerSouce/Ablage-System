# -*- coding: utf-8 -*-
"""
Tests fuer TaxAdvisorPackageService.

Feature: Automatische Steuerberater-Paket Erstellung
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tax_advisor_package_service import (
    CompletenessReport,
    MissingDocument,
    MissingDocumentType,
    MissingItem,
    PackageConfiguration,
    PackageFrequency,
    PackageStatus,
    TaxAdvisorPackage,
    TaxAdvisorPackageService,
    get_tax_advisor_package_service,
)


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    # Mock execute result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalars = MagicMock()
    mock_result.scalars.return_value.all = MagicMock(return_value=[])
    mock_result.one = MagicMock(return_value=(0, 0))
    mock_result.scalar = MagicMock(return_value=0)
    mock_result.fetchall = MagicMock(return_value=[])

    db.execute = AsyncMock(return_value=mock_result)
    return db


@pytest.fixture
def service(mock_db):
    """TaxAdvisorPackageService instance."""
    return TaxAdvisorPackageService(mock_db)


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid.uuid4()


@pytest.fixture
def config_id():
    """Test Configuration-ID."""
    return uuid.uuid4()


# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================


@pytest.mark.asyncio
async def test_create_configuration_default_values(service, company_id):
    """Erstellt Konfiguration mit Standard-Werten."""
    config = await service.create_configuration(
        company_id=company_id,
        name="Test Config",
    )

    assert isinstance(config, PackageConfiguration)
    assert config.company_id == company_id
    assert config.name == "Test Config"
    assert config.frequency == PackageFrequency.MONTHLY
    assert config.document_categories == service.DEFAULT_CATEGORIES
    assert config.period_start_day == 1
    assert config.delivery_delay_days == 5
    assert config.auto_send is True
    assert config.auto_reminder is True
    assert config.reminder_days_before == 3
    assert config.include_datev_export is True
    assert config.include_pdf_copies is True
    assert config.include_summary_report is True
    assert config.is_active is True
    assert config.recipient_email is None
    assert config.tax_advisor_user_id is None


@pytest.mark.asyncio
async def test_create_configuration_custom_frequency(service, company_id):
    """Erstellt Konfiguration mit benutzerdefinierter Frequenz."""
    config = await service.create_configuration(
        company_id=company_id,
        name="Quarterly Config",
        frequency=PackageFrequency.QUARTERLY,
    )

    assert config.frequency == PackageFrequency.QUARTERLY


@pytest.mark.asyncio
async def test_create_configuration_custom_categories(service, company_id):
    """Erstellt Konfiguration mit benutzerdefinierten Kategorien."""
    custom_categories = ["eingangsrechnung", "ausgangsrechnung"]

    config = await service.create_configuration(
        company_id=company_id,
        name="Custom Categories",
        document_categories=custom_categories,
    )

    assert config.document_categories == custom_categories


@pytest.mark.asyncio
async def test_create_configuration_with_email(service, company_id):
    """Erstellt Konfiguration mit E-Mail-Adresse."""
    email = "steuerberater@example.com"

    config = await service.create_configuration(
        company_id=company_id,
        name="Email Config",
        recipient_email=email,
    )

    assert config.recipient_email == email


@pytest.mark.asyncio
async def test_get_configuration_existing(service, company_id):
    """Holt existierende Konfiguration."""
    config = await service.create_configuration(
        company_id=company_id,
        name="Test Config",
    )

    result = await service.get_configuration(config.id)

    assert result is not None
    assert result.id == config.id
    assert result.name == "Test Config"


@pytest.mark.asyncio
async def test_get_configuration_non_existent(service):
    """Gibt None zurueck fuer nicht-existierende Konfiguration."""
    non_existent_id = uuid.uuid4()

    result = await service.get_configuration(non_existent_id)

    assert result is None


@pytest.mark.asyncio
async def test_get_configurations_for_company_empty(service, company_id):
    """Gibt leere Liste zurueck wenn keine Konfigurationen existieren."""
    result = await service.get_configurations_for_company(company_id)

    assert result == []


@pytest.mark.asyncio
async def test_get_configurations_for_company_multiple(service, company_id):
    """Gibt alle Konfigurationen fuer eine Firma zurueck."""
    config1 = await service.create_configuration(
        company_id=company_id,
        name="Config 1",
    )
    config2 = await service.create_configuration(
        company_id=company_id,
        name="Config 2",
        frequency=PackageFrequency.QUARTERLY,
    )

    # Andere Firma
    other_company = uuid.uuid4()
    await service.create_configuration(
        company_id=other_company,
        name="Other Config",
    )

    result = await service.get_configurations_for_company(company_id)

    assert len(result) == 2
    assert config1 in result
    assert config2 in result


# ============================================================================
# PACKAGE CREATION
# ============================================================================


@pytest.mark.asyncio
async def test_create_package_for_period_monthly(service, company_id):
    """Erstellt Paket fuer Monat."""
    with patch.object(service, '_count_documents_for_period', new_callable=AsyncMock) as mock_count, \
         patch.object(service, '_identify_missing_documents', new_callable=AsyncMock) as mock_missing:

        mock_count.return_value = (10, 5000000)
        mock_missing.return_value = []

        package = await service.create_package_for_period(
            company_id=company_id,
            period="2026-01",
        )

        assert isinstance(package, TaxAdvisorPackage)
        assert package.company_id == company_id
        assert package.period_start == date(2026, 1, 1)
        assert package.period_end == date(2026, 1, 31)
        assert package.period_label == "Januar 2026"
        assert package.document_count == 10
        assert package.total_size_bytes == 5000000
        assert package.status == PackageStatus.READY
        assert package.missing_documents == []


@pytest.mark.asyncio
async def test_create_package_for_period_quarterly(service, company_id):
    """Erstellt Paket fuer Quartal."""
    with patch.object(service, '_count_documents_for_period', new_callable=AsyncMock) as mock_count, \
         patch.object(service, '_identify_missing_documents', new_callable=AsyncMock) as mock_missing:

        mock_count.return_value = (30, 15000000)
        mock_missing.return_value = []

        package = await service.create_package_for_period(
            company_id=company_id,
            period="2026-Q1",
        )

        assert package.period_start == date(2026, 1, 1)
        assert package.period_end == date(2026, 3, 31)
        assert package.period_label == "Q1/2026"
        assert package.document_count == 30


@pytest.mark.asyncio
async def test_create_package_with_missing_documents(service, company_id):
    """Erstellt Paket mit fehlenden Dokumenten."""
    missing_doc = MissingDocument(
        document_type=MissingDocumentType.BANK_STATEMENT,
        description="Kontoauszug Februar fehlt",
        expected_date=date(2026, 2, 1),
        importance="required",
    )

    with patch.object(service, '_count_documents_for_period', new_callable=AsyncMock) as mock_count, \
         patch.object(service, '_identify_missing_documents', new_callable=AsyncMock) as mock_missing:

        mock_count.return_value = (5, 2500000)
        mock_missing.return_value = [missing_doc]

        package = await service.create_package_for_period(
            company_id=company_id,
            period="2026-02",
        )

        assert package.status == PackageStatus.PENDING
        assert len(package.missing_documents) == 1
        assert package.missing_documents[0]["document_type"] == "bank_statement"
        assert package.missing_documents[0]["description"] == "Kontoauszug Februar fehlt"


# ============================================================================
# PERIOD PARSING
# ============================================================================


def test_parse_period_monthly_march(service):
    """Parst Monat-Format korrekt (Maerz)."""
    period_start, period_end, period_label = service._parse_period("2026-03")

    assert period_start == date(2026, 3, 1)
    assert period_end == date(2026, 3, 31)
    assert period_label == "Maerz 2026"


def test_parse_period_quarterly_q1(service):
    """Parst Quartal-Format korrekt."""
    period_start, period_end, period_label = service._parse_period("2026-Q1")

    assert period_start == date(2026, 1, 1)
    assert period_end == date(2026, 3, 31)
    assert period_label == "Q1/2026"


def test_parse_period_quarterly_q2(service):
    """Parst Q2 korrekt."""
    period_start, period_end, period_label = service._parse_period("2026-Q2")

    assert period_start == date(2026, 4, 1)
    assert period_end == date(2026, 6, 30)
    assert period_label == "Q2/2026"


def test_parse_period_quarterly_q4(service):
    """Parst Q4 korrekt (Dezember edge case)."""
    period_start, period_end, period_label = service._parse_period("2026-Q4")

    assert period_start == date(2026, 10, 1)
    assert period_end == date(2026, 12, 31)
    assert period_label == "Q4/2026"


def test_parse_period_december(service):
    """Parst Dezember korrekt (edge case)."""
    period_start, period_end, period_label = service._parse_period("2026-12")

    assert period_start == date(2026, 12, 1)
    assert period_end == date(2026, 12, 31)
    assert period_label == "Dezember 2026"


def test_parse_period_february_leap_year(service):
    """Parst Februar in Schaltjahr korrekt."""
    period_start, period_end, period_label = service._parse_period("2024-02")

    assert period_start == date(2024, 2, 1)
    assert period_end == date(2024, 2, 29)
    assert period_label == "Februar 2024"


def test_parse_period_february_non_leap_year(service):
    """Parst Februar in Nicht-Schaltjahr korrekt."""
    period_start, period_end, period_label = service._parse_period("2026-02")

    assert period_start == date(2026, 2, 1)
    assert period_end == date(2026, 2, 28)
    assert period_label == "Februar 2026"


# ============================================================================
# PACKAGE GENERATION
# ============================================================================


@pytest.mark.asyncio
async def test_generate_package_files(service, company_id):
    """Generiert Paket-Dateien."""
    with patch.object(service, '_generate_datev_export', new_callable=AsyncMock) as mock_datev, \
         patch.object(service, '_generate_pdf_archive', new_callable=AsyncMock) as mock_pdf, \
         patch.object(service, '_generate_summary_report', new_callable=AsyncMock) as mock_report:

        mock_datev.return_value = "/exports/datev/test.zip"
        mock_pdf.return_value = "/exports/pdf/test_docs.zip"
        mock_report.return_value = "/exports/reports/test_summary.pdf"

        package = TaxAdvisorPackage(
            id=uuid.uuid4(),
            configuration_id=uuid.uuid4(),
            company_id=company_id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Januar 2026",
            status=PackageStatus.DRAFT,
        )

        result = await service.generate_package_files(package)

        assert result.status == PackageStatus.READY
        assert result.datev_export_path == "/exports/datev/test.zip"
        assert result.pdf_archive_path == "/exports/pdf/test_docs.zip"
        assert result.summary_report_path == "/exports/reports/test_summary.pdf"


# ============================================================================
# PACKAGE DELIVERY
# ============================================================================


@pytest.mark.asyncio
async def test_send_package_not_ready(service, company_id):
    """Sendet Paket nicht wenn Status nicht READY."""
    package = TaxAdvisorPackage(
        id=uuid.uuid4(),
        configuration_id=uuid.uuid4(),
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        period_label="Januar 2026",
        status=PackageStatus.PENDING,
    )

    result = await service.send_package(package)

    assert result is False


@pytest.mark.asyncio
async def test_send_package_no_email(service, company_id):
    """Sendet Paket nicht wenn keine E-Mail-Adresse."""
    package = TaxAdvisorPackage(
        id=uuid.uuid4(),
        configuration_id=uuid.uuid4(),
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        period_label="Januar 2026",
        status=PackageStatus.READY,
    )

    result = await service.send_package(package)

    assert result is False


@pytest.mark.asyncio
async def test_send_package_success(service, company_id, config_id):
    """Sendet Paket erfolgreich."""
    # Konfiguration mit E-Mail erstellen
    config = await service.create_configuration(
        company_id=company_id,
        name="Test Config",
        recipient_email="steuerberater@example.com",
    )

    package = TaxAdvisorPackage(
        id=uuid.uuid4(),
        configuration_id=config.id,
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        period_label="Januar 2026",
        status=PackageStatus.READY,
        document_count=10,
        datev_export_path="/exports/datev/test.zip",
        pdf_archive_path="/exports/pdf/test_docs.zip",
        summary_report_path="/exports/reports/test_summary.pdf",
    )

    with patch('app.services.notification_service.NotificationService') as mock_notification_class:
        mock_notification = AsyncMock()
        mock_notification.send_email = AsyncMock()
        mock_notification_class.return_value = mock_notification

        result = await service.send_package(package)

        assert result is True
        assert package.status == PackageStatus.SENT
        assert package.sent_at is not None
        assert package.expires_at is not None
        mock_notification.send_email.assert_called_once()


@pytest.mark.asyncio
async def test_send_package_with_explicit_email(service, company_id):
    """Sendet Paket mit expliziter E-Mail-Adresse."""
    package = TaxAdvisorPackage(
        id=uuid.uuid4(),
        configuration_id=uuid.uuid4(),
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        period_label="Januar 2026",
        status=PackageStatus.READY,
        document_count=5,
    )

    with patch('app.services.notification_service.NotificationService') as mock_notification_class:
        mock_notification = AsyncMock()
        mock_notification.send_email = AsyncMock()
        mock_notification_class.return_value = mock_notification

        result = await service.send_package(
            package,
            recipient_email="custom@example.com",
        )

        assert result is True
        assert package.status == PackageStatus.SENT


# ============================================================================
# COMPLETENESS CHECK
# ============================================================================


@pytest.mark.asyncio
async def test_check_completeness_full_year(service, company_id):
    """Prueft Vollstaendigkeit fuer ganzes Jahr."""
    with patch.object(service, '_check_bank_statements', new_callable=AsyncMock) as mock_bank, \
         patch.object(service, '_check_invoices_status', new_callable=AsyncMock) as mock_invoices, \
         patch.object(service, '_check_required_documents', new_callable=AsyncMock) as mock_required, \
         patch.object(service, '_validate_datev_export_readiness', new_callable=AsyncMock) as mock_datev, \
         patch.object(service, '_check_compliance_issues', new_callable=AsyncMock) as mock_compliance:

        # Alle Checks erfolgreich
        mock_bank.return_value = {"complete": True, "missing_months": []}
        mock_invoices.return_value = {"complete": True, "unmatched_invoices": 0, "total_invoices": 10}
        mock_required.return_value = {"complete": True, "missing": {}}
        mock_datev.return_value = {"valid": True, "errors": []}
        mock_compliance.return_value = {"clean": True, "issues": []}

        report = await service.check_completeness(
            company_id=company_id,
            year=2026,
        )

        assert isinstance(report, CompletenessReport)
        assert report.period == "2026"
        assert report.period_start == date(2026, 1, 1)
        assert report.period_end == date(2026, 12, 31)
        assert report.completeness_score == 100.0
        assert report.checks_passed == 5
        assert report.total_checks == 5
        assert report.is_complete is True
        assert len(report.missing_items) == 0


@pytest.mark.asyncio
async def test_check_completeness_quarter(service, company_id):
    """Prueft Vollstaendigkeit fuer Quartal."""
    with patch.object(service, '_check_bank_statements', new_callable=AsyncMock) as mock_bank, \
         patch.object(service, '_check_invoices_status', new_callable=AsyncMock) as mock_invoices, \
         patch.object(service, '_check_required_documents', new_callable=AsyncMock) as mock_required, \
         patch.object(service, '_validate_datev_export_readiness', new_callable=AsyncMock) as mock_datev, \
         patch.object(service, '_check_compliance_issues', new_callable=AsyncMock) as mock_compliance:

        mock_bank.return_value = {"complete": True, "missing_months": []}
        mock_invoices.return_value = {"complete": True, "unmatched_invoices": 0, "total_invoices": 10}
        mock_required.return_value = {"complete": True, "missing": {}}
        mock_datev.return_value = {"valid": True, "errors": []}
        mock_compliance.return_value = {"clean": True, "issues": []}

        report = await service.check_completeness(
            company_id=company_id,
            year=2026,
            quarter=1,
        )

        assert report.period == "Q1/2026"
        assert report.period_start == date(2026, 1, 1)
        assert report.period_end == date(2026, 3, 31)


@pytest.mark.asyncio
async def test_check_completeness_with_missing_items(service, company_id):
    """Prueft Vollstaendigkeit mit fehlenden Items."""
    with patch.object(service, '_check_bank_statements', new_callable=AsyncMock) as mock_bank, \
         patch.object(service, '_check_invoices_status', new_callable=AsyncMock) as mock_invoices, \
         patch.object(service, '_check_required_documents', new_callable=AsyncMock) as mock_required, \
         patch.object(service, '_validate_datev_export_readiness', new_callable=AsyncMock) as mock_datev, \
         patch.object(service, '_check_compliance_issues', new_callable=AsyncMock) as mock_compliance:

        # Einige Checks fehlschlagen
        mock_bank.return_value = {"complete": False, "missing_months": ["2026-02", "2026-03"]}
        mock_invoices.return_value = {"complete": False, "unmatched_invoices": 5, "total_invoices": 10}
        mock_required.return_value = {
            "complete": False,
            "missing": {
                "eingangsrechnung": {
                    "description": "Keine Eingangsrechnungen gefunden",
                    "suggestion": "Laden Sie alle Lieferantenrechnungen hoch",
                }
            }
        }
        mock_datev.return_value = {"valid": False, "errors": ["Keine USt-IdNr hinterlegt"]}
        mock_compliance.return_value = {"clean": True, "issues": []}

        report = await service.check_completeness(
            company_id=company_id,
            year=2026,
        )

        assert report.completeness_score == 20.0  # 1/5 checks passed
        assert report.checks_passed == 1
        assert report.total_checks == 5
        assert report.is_complete is False
        assert len(report.missing_items) > 0

        # Pruefe dass alle fehlenden Items vorhanden sind
        categories = [item.category for item in report.missing_items]
        assert "kontoauszug" in categories
        assert "zahlung" in categories
        assert "eingangsrechnung" in categories
        assert "datev" in categories


# ============================================================================
# DATACLASS TO_DICT METHODS
# ============================================================================


def test_package_configuration_to_dict():
    """PackageConfiguration.to_dict() liefert korrekte Felder."""
    config_id = uuid.uuid4()
    company_id = uuid.uuid4()
    tax_advisor_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)

    config = PackageConfiguration(
        id=config_id,
        company_id=company_id,
        name="Test Config",
        frequency=PackageFrequency.MONTHLY,
        document_categories=["eingangsrechnung", "ausgangsrechnung"],
        period_start_day=1,
        delivery_delay_days=5,
        auto_send=True,
        auto_reminder=True,
        reminder_days_before=3,
        recipient_email="test@example.com",
        tax_advisor_user_id=tax_advisor_id,
        include_datev_export=True,
        include_pdf_copies=True,
        include_summary_report=True,
        is_active=True,
        created_at=created_at,
    )

    result = config.to_dict()

    assert result["id"] == str(config_id)
    assert result["company_id"] == str(company_id)
    assert result["name"] == "Test Config"
    assert result["frequency"] == "monthly"
    assert result["document_categories"] == ["eingangsrechnung", "ausgangsrechnung"]
    assert result["period_start_day"] == 1
    assert result["delivery_delay_days"] == 5
    assert result["auto_send"] is True
    assert result["auto_reminder"] is True
    assert result["reminder_days_before"] == 3
    assert result["recipient_email"] == "test@example.com"
    assert result["tax_advisor_user_id"] == str(tax_advisor_id)
    assert result["include_datev_export"] is True
    assert result["include_pdf_copies"] is True
    assert result["include_summary_report"] is True
    assert result["is_active"] is True
    assert result["created_at"] == created_at.isoformat()


def test_tax_advisor_package_to_dict():
    """TaxAdvisorPackage.to_dict() liefert korrekte Felder."""
    package_id = uuid.uuid4()
    config_id = uuid.uuid4()
    company_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)
    sent_at = datetime.now(timezone.utc)

    package = TaxAdvisorPackage(
        id=package_id,
        configuration_id=config_id,
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        period_label="Januar 2026",
        status=PackageStatus.SENT,
        document_count=10,
        total_size_bytes=5000000,
        datev_export_path="/exports/datev/test.zip",
        pdf_archive_path="/exports/pdf/test.zip",
        summary_report_path="/exports/reports/test.pdf",
        created_at=created_at,
        sent_at=sent_at,
        downloaded_at=None,
        expires_at=None,
        missing_documents=[],
    )

    result = package.to_dict()

    assert result["id"] == str(package_id)
    assert result["configuration_id"] == str(config_id)
    assert result["company_id"] == str(company_id)
    assert result["period_start"] == "2026-01-01"
    assert result["period_end"] == "2026-01-31"
    assert result["period_label"] == "Januar 2026"
    assert result["status"] == "sent"
    assert result["document_count"] == 10
    assert result["total_size_bytes"] == 5000000
    assert result["datev_export_path"] == "/exports/datev/test.zip"
    assert result["pdf_archive_path"] == "/exports/pdf/test.zip"
    assert result["summary_report_path"] == "/exports/reports/test.pdf"
    assert result["created_at"] == created_at.isoformat()
    assert result["sent_at"] == sent_at.isoformat()
    assert result["downloaded_at"] is None
    assert result["expires_at"] is None
    assert result["missing_documents"] == []


def test_missing_document_to_dict():
    """MissingDocument.to_dict() funktioniert korrekt."""
    doc = MissingDocument(
        document_type=MissingDocumentType.BANK_STATEMENT,
        description="Kontoauszug Februar fehlt",
        expected_date=date(2026, 2, 1),
        importance="required",
        notes="Wichtig fuer Monatsabschluss",
    )

    result = doc.to_dict()

    assert result["document_type"] == "bank_statement"
    assert result["description"] == "Kontoauszug Februar fehlt"
    assert result["expected_date"] == "2026-02-01"
    assert result["importance"] == "required"
    assert result["notes"] == "Wichtig fuer Monatsabschluss"


def test_missing_document_to_dict_without_optional_fields():
    """MissingDocument.to_dict() ohne optionale Felder."""
    doc = MissingDocument(
        document_type=MissingDocumentType.INVOICE,
        description="Rechnung fehlt",
    )

    result = doc.to_dict()

    assert result["document_type"] == "invoice"
    assert result["description"] == "Rechnung fehlt"
    assert result["expected_date"] is None
    assert result["importance"] == "required"
    assert result["notes"] is None


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def test_get_tax_advisor_package_service(mock_db):
    """Factory-Funktion gibt Service zurueck."""
    service = get_tax_advisor_package_service(mock_db)

    assert isinstance(service, TaxAdvisorPackageService)
    assert service.db == mock_db


# ============================================================================
# EDGE CASES & ERROR HANDLING
# ============================================================================


@pytest.mark.asyncio
async def test_send_package_notification_exception(service, company_id):
    """Behandelt Ausnahmen beim Versand korrekt."""
    config = await service.create_configuration(
        company_id=company_id,
        name="Test Config",
        recipient_email="test@example.com",
    )

    package = TaxAdvisorPackage(
        id=uuid.uuid4(),
        configuration_id=config.id,
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        period_label="Januar 2026",
        status=PackageStatus.READY,
    )

    with patch('app.services.notification_service.NotificationService') as mock_notification_class:
        mock_notification = AsyncMock()
        mock_notification.send_email = AsyncMock(side_effect=Exception("SMTP Error"))
        mock_notification_class.return_value = mock_notification

        result = await service.send_package(package)

        assert result is False
        # Status sollte NICHT auf SENT gesetzt werden
        assert package.status == PackageStatus.READY


@pytest.mark.asyncio
async def test_create_package_with_config(service, company_id):
    """Erstellt Paket mit spezifischer Konfiguration."""
    config = await service.create_configuration(
        company_id=company_id,
        name="Test Config",
        document_categories=["eingangsrechnung"],
    )

    with patch.object(service, '_count_documents_for_period', new_callable=AsyncMock) as mock_count, \
         patch.object(service, '_identify_missing_documents', new_callable=AsyncMock) as mock_missing:

        mock_count.return_value = (5, 2500000)
        mock_missing.return_value = []

        package = await service.create_package_for_period(
            company_id=company_id,
            period="2026-01",
            config_id=config.id,
        )

        assert package.configuration_id == config.id
        # Verifiziere dass die benutzerdefinierten Kategorien verwendet wurden
        mock_count.assert_called_once()
        call_args = mock_count.call_args[1]
        assert call_args["categories"] == ["eingangsrechnung"]


def test_missing_item_dataclass():
    """MissingItem Dataclass funktioniert korrekt."""
    item = MissingItem(
        category="kontoauszug",
        description="Kontoauszug fehlt",
        severity="required",
        suggestion="Laden Sie den Kontoauszug hoch",
    )

    assert item.category == "kontoauszug"
    assert item.description == "Kontoauszug fehlt"
    assert item.severity == "required"
    assert item.suggestion == "Laden Sie den Kontoauszug hoch"


def test_completeness_report_dataclass():
    """CompletenessReport Dataclass funktioniert korrekt."""
    missing_items = [
        MissingItem(
            category="kontoauszug",
            description="Test",
            severity="required",
            suggestion="Test",
        )
    ]

    report = CompletenessReport(
        period="2026",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        completeness_score=80.0,
        checks_passed=4,
        total_checks=5,
        missing_items=missing_items,
        is_complete=False,
    )

    assert report.period == "2026"
    assert report.completeness_score == 80.0
    assert report.checks_passed == 4
    assert report.total_checks == 5
    assert report.is_complete is False
    assert len(report.missing_items) == 1
