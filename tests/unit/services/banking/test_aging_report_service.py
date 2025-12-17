# -*- coding: utf-8 -*-
"""
Tests fuer AgingReportService.

Testet:
- Bucket-Zuordnung
- Altersklassen-Berechnung
- Report-Generierung
- DSO-Berechnung
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.services.banking.aging_report_service import (
    AgingReportService,
    AgingBucket,
    AgingLineItem,
    AgingBucketSummary,
    AgingReport,
    ReportType,
)


class TestAgingBucketDetermination:
    """Tests fuer Bucket-Zuordnung."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    def test_current_bucket(self, service: AgingReportService):
        """Sollte 'aktuell' fuer nicht faellige zuordnen."""
        bucket = service._get_bucket(days_overdue=-5)
        assert bucket == AgingBucket.CURRENT

        bucket = service._get_bucket(days_overdue=0)
        assert bucket == AgingBucket.CURRENT

    def test_1_30_days_bucket(self, service: AgingReportService):
        """Sollte '1-30 Tage' korrekt zuordnen."""
        bucket = service._get_bucket(days_overdue=1)
        assert bucket == AgingBucket.DAYS_1_30

        bucket = service._get_bucket(days_overdue=15)
        assert bucket == AgingBucket.DAYS_1_30

        bucket = service._get_bucket(days_overdue=30)
        assert bucket == AgingBucket.DAYS_1_30

    def test_31_60_days_bucket(self, service: AgingReportService):
        """Sollte '31-60 Tage' korrekt zuordnen."""
        bucket = service._get_bucket(days_overdue=31)
        assert bucket == AgingBucket.DAYS_31_60

        bucket = service._get_bucket(days_overdue=45)
        assert bucket == AgingBucket.DAYS_31_60

        bucket = service._get_bucket(days_overdue=60)
        assert bucket == AgingBucket.DAYS_31_60

    def test_61_90_days_bucket(self, service: AgingReportService):
        """Sollte '61-90 Tage' korrekt zuordnen."""
        bucket = service._get_bucket(days_overdue=61)
        assert bucket == AgingBucket.DAYS_61_90

        bucket = service._get_bucket(days_overdue=75)
        assert bucket == AgingBucket.DAYS_61_90

        bucket = service._get_bucket(days_overdue=90)
        assert bucket == AgingBucket.DAYS_61_90

    def test_90_plus_days_bucket(self, service: AgingReportService):
        """Sollte '90+' korrekt zuordnen."""
        bucket = service._get_bucket(days_overdue=91)
        assert bucket == AgingBucket.DAYS_90_PLUS

        bucket = service._get_bucket(days_overdue=180)
        assert bucket == AgingBucket.DAYS_90_PLUS

        bucket = service._get_bucket(days_overdue=365)
        assert bucket == AgingBucket.DAYS_90_PLUS


class TestAgingLineItem:
    """Tests fuer AgingLineItem Dataclass."""

    def test_create_receivable_item(self):
        """Sollte Forderungs-Eintrag erstellen."""
        today = date.today()
        due_date = today - timedelta(days=15)

        item = AgingLineItem(
            document_id=uuid4(),
            invoice_number="RE-2024-001",
            counterparty="Kunde GmbH",
            invoice_date=today - timedelta(days=30),
            due_date=due_date,
            amount=Decimal("1500.00"),
            bucket=AgingBucket.DAYS_1_30,
            days_overdue=15,
            document_type="invoice",
        )

        assert item.invoice_number == "RE-2024-001"
        assert item.amount == Decimal("1500.00")
        assert item.bucket == AgingBucket.DAYS_1_30
        assert item.days_overdue == 15

    def test_create_payable_item(self):
        """Sollte Verbindlichkeiten-Eintrag erstellen."""
        item = AgingLineItem(
            document_id=uuid4(),
            invoice_number="LR-2024-050",
            counterparty="Lieferant AG",
            invoice_date=date.today() - timedelta(days=45),
            due_date=date.today() - timedelta(days=5),
            amount=Decimal("2500.00"),
            bucket=AgingBucket.DAYS_1_30,
            days_overdue=5,
            document_type="supplier_invoice",
        )

        assert item.counterparty == "Lieferant AG"
        assert item.document_type == "supplier_invoice"


class TestAgingBucketSummary:
    """Tests fuer AgingBucketSummary Dataclass."""

    def test_create_empty_summary(self):
        """Sollte leere Zusammenfassung erstellen."""
        summary = AgingBucketSummary(bucket=AgingBucket.CURRENT)

        assert summary.count == 0
        assert summary.amount == Decimal("0.00")
        assert summary.percentage == 0.0

    def test_create_filled_summary(self):
        """Sollte gefuellte Zusammenfassung erstellen."""
        summary = AgingBucketSummary(
            bucket=AgingBucket.DAYS_1_30,
            count=10,
            amount=Decimal("15000.00"),
            percentage=25.5,
        )

        assert summary.count == 10
        assert summary.amount == Decimal("15000.00")
        assert summary.percentage == 25.5


class TestAgingReport:
    """Tests fuer AgingReport Dataclass."""

    def test_create_empty_receivables_report(self):
        """Sollte leeren Forderungs-Report erstellen."""
        report = AgingReport(
            report_type=ReportType.RECEIVABLES,
            generated_at=datetime.utcnow(),
            as_of_date=date.today(),
        )

        assert report.report_type == ReportType.RECEIVABLES
        assert report.total_count == 0
        assert report.total_amount == Decimal("0.00")

    def test_create_payables_report(self):
        """Sollte Verbindlichkeiten-Report erstellen."""
        report = AgingReport(
            report_type=ReportType.PAYABLES,
            generated_at=datetime.utcnow(),
            as_of_date=date.today(),
            total_count=5,
            total_amount=Decimal("25000.00"),
            total_overdue=Decimal("10000.00"),
        )

        assert report.report_type == ReportType.PAYABLES
        assert report.total_count == 5
        assert report.total_overdue == Decimal("10000.00")


class TestDSOInterpretation:
    """Tests fuer DSO-Interpretation."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    def test_excellent_dso(self, service: AgingReportService):
        """Sollte exzellenten DSO interpretieren."""
        interpretation = service._interpret_dso(25.0)

        assert "Ausgezeichnet" in interpretation

    def test_good_dso(self, service: AgingReportService):
        """Sollte guten DSO interpretieren."""
        interpretation = service._interpret_dso(40.0)

        assert "Gut" in interpretation

    def test_acceptable_dso(self, service: AgingReportService):
        """Sollte akzeptablen DSO interpretieren."""
        interpretation = service._interpret_dso(55.0)

        assert "Akzeptabel" in interpretation

    def test_improvement_needed_dso(self, service: AgingReportService):
        """Sollte verbesserungsbeduerftigen DSO interpretieren."""
        interpretation = service._interpret_dso(75.0)

        assert "Verbesserung" in interpretation

    def test_critical_dso(self, service: AgingReportService):
        """Sollte kritischen DSO interpretieren."""
        interpretation = service._interpret_dso(100.0)

        assert "Kritisch" in interpretation


class TestReportToDict:
    """Tests fuer Report-Konvertierung."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    def test_convert_empty_report(self, service: AgingReportService):
        """Sollte leeren Report konvertieren."""
        today = date.today()
        report = AgingReport(
            report_type=ReportType.RECEIVABLES,
            generated_at=datetime.utcnow(),
            as_of_date=today,
            buckets=[
                AgingBucketSummary(bucket=bucket)
                for bucket in AgingBucket
            ],
        )

        result = service._report_to_dict(report)

        assert result["as_of_date"] == today.isoformat()
        assert result["total_count"] == 0
        assert result["total_amount"] == 0.0
        assert len(result["buckets"]) == len(AgingBucket)

    def test_convert_filled_report(self, service: AgingReportService):
        """Sollte gefuellten Report konvertieren."""
        today = date.today()
        report = AgingReport(
            report_type=ReportType.RECEIVABLES,
            generated_at=datetime.utcnow(),
            as_of_date=today,
            total_count=15,
            total_amount=Decimal("50000.00"),
            total_overdue=Decimal("30000.00"),
            average_days_overdue=25.5,
            buckets=[
                AgingBucketSummary(
                    bucket=AgingBucket.CURRENT,
                    count=5,
                    amount=Decimal("20000.00"),
                    percentage=40.0,
                ),
                AgingBucketSummary(
                    bucket=AgingBucket.DAYS_1_30,
                    count=6,
                    amount=Decimal("18000.00"),
                    percentage=36.0,
                ),
                AgingBucketSummary(
                    bucket=AgingBucket.DAYS_31_60,
                    count=3,
                    amount=Decimal("9000.00"),
                    percentage=18.0,
                ),
                AgingBucketSummary(
                    bucket=AgingBucket.DAYS_61_90,
                    count=1,
                    amount=Decimal("3000.00"),
                    percentage=6.0,
                ),
                AgingBucketSummary(
                    bucket=AgingBucket.DAYS_90_PLUS,
                    count=0,
                    amount=Decimal("0.00"),
                    percentage=0.0,
                ),
            ],
        )

        result = service._report_to_dict(report)

        assert result["total_count"] == 15
        assert result["total_amount"] == 50000.0
        assert result["total_overdue"] == 30000.0
        assert result["average_days_overdue"] == 25.5

        # Buckets pruefen
        assert len(result["buckets"]) == 5
        assert result["buckets"][0]["bucket"] == "current"
        assert result["buckets"][0]["count"] == 5
        assert result["buckets"][0]["percentage"] == 40.0


class TestAgingBucketEnum:
    """Tests fuer AgingBucket Enum."""

    def test_bucket_values(self):
        """Sollte korrekte Enum-Werte haben."""
        assert AgingBucket.CURRENT.value == "current"
        assert AgingBucket.DAYS_1_30.value == "1-30"
        assert AgingBucket.DAYS_31_60.value == "31-60"
        assert AgingBucket.DAYS_61_90.value == "61-90"
        assert AgingBucket.DAYS_90_PLUS.value == "90+"

    def test_bucket_count(self):
        """Sollte 5 Buckets haben."""
        assert len(AgingBucket) == 5


class TestReportTypeEnum:
    """Tests fuer ReportType Enum."""

    def test_report_type_values(self):
        """Sollte korrekte Enum-Werte haben."""
        assert ReportType.RECEIVABLES.value == "receivables"
        assert ReportType.PAYABLES.value == "payables"

    def test_report_type_count(self):
        """Sollte 2 Report-Typen haben."""
        assert len(ReportType) == 2
