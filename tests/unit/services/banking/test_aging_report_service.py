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


# =============================================================================
# ASYNC DB TESTS
# =============================================================================

from unittest.mock import AsyncMock, MagicMock, patch


class TestAsyncReceivablesAging:
    """Tests fuer async get_receivables_aging."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    @pytest.fixture
    def mock_db(self):
        """Mock-Datenbank-Session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_documents(self, sample_user_id):
        """Sample Dokumente mit extrahierten Daten."""
        today = date.today()
        documents = []

        # Dokument 1: Aktuell (nicht faellig)
        doc1 = MagicMock()
        doc1.id = uuid4()
        doc1.owner_id = sample_user_id
        doc1.document_type = "invoice"
        doc1.deleted_at = None
        doc1.extracted_data = {
            "invoice_number": "RE-2024-001",
            "creditor_name": "Kunde A GmbH",
            "total_amount": "1500.00",
            "due_date": (today + timedelta(days=10)).isoformat(),
            "invoice_date": (today - timedelta(days=20)).isoformat(),
        }
        documents.append(doc1)

        # Dokument 2: 15 Tage ueberfaellig
        doc2 = MagicMock()
        doc2.id = uuid4()
        doc2.owner_id = sample_user_id
        doc2.document_type = "invoice"
        doc2.deleted_at = None
        doc2.extracted_data = {
            "invoice_number": "RE-2024-002",
            "creditor_name": "Kunde B AG",
            "total_amount": "2500.00",
            "due_date": (today - timedelta(days=15)).isoformat(),
            "invoice_date": (today - timedelta(days=45)).isoformat(),
        }
        documents.append(doc2)

        # Dokument 3: 45 Tage ueberfaellig
        doc3 = MagicMock()
        doc3.id = uuid4()
        doc3.owner_id = sample_user_id
        doc3.document_type = "invoice"
        doc3.deleted_at = None
        doc3.extracted_data = {
            "invoice_number": "RE-2024-003",
            "creditor_name": "Kunde A GmbH",  # Gleicher Kunde wie doc1
            "total_amount": "3000.00",
            "due_date": (today - timedelta(days=45)).isoformat(),
            "invoice_date": (today - timedelta(days=75)).isoformat(),
        }
        documents.append(doc3)

        # Dokument 4: Bereits bezahlt (sollte ignoriert werden)
        doc4 = MagicMock()
        doc4.id = uuid4()
        doc4.owner_id = sample_user_id
        doc4.document_type = "invoice"
        doc4.deleted_at = None
        doc4.extracted_data = {
            "invoice_number": "RE-2024-004",
            "creditor_name": "Kunde C",
            "total_amount": "1000.00",
            "due_date": (today - timedelta(days=30)).isoformat(),
            "payment_status": "paid",
        }
        documents.append(doc4)

        return documents

    @pytest.mark.asyncio
    async def test_get_receivables_aging_with_documents(
        self, service: AgingReportService, mock_db, sample_user_id, sample_documents
    ):
        """Sollte Forderungs-Aging mit Dokumenten berechnen."""
        # Mock DB Abfrage
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_documents
        mock_db.execute = AsyncMock(return_value=mock_result)

        report = await service.get_receivables_aging(
            db=mock_db,
            user_id=sample_user_id,
            include_details=True,
        )

        assert report.report_type == ReportType.RECEIVABLES
        # 3 Dokumente (bezahltes wird ignoriert)
        assert report.total_count == 3
        assert report.total_amount > Decimal("0.00")
        assert len(report.buckets) == 5

    @pytest.mark.asyncio
    async def test_get_receivables_aging_empty(
        self, service: AgingReportService, mock_db, sample_user_id
    ):
        """Sollte leeren Report bei keinen Dokumenten zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        report = await service.get_receivables_aging(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert report.total_count == 0
        assert report.total_amount == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_get_receivables_aging_without_details(
        self, service: AgingReportService, mock_db, sample_user_id, sample_documents
    ):
        """Sollte Report ohne Details zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_documents
        mock_db.execute = AsyncMock(return_value=mock_result)

        report = await service.get_receivables_aging(
            db=mock_db,
            user_id=sample_user_id,
            include_details=False,
        )

        assert len(report.line_items) == 0
        assert report.total_count > 0


class TestAsyncPayablesAging:
    """Tests fuer async get_payables_aging."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_payable_documents(self, sample_user_id):
        """Sample Verbindlichkeiten-Dokumente."""
        today = date.today()
        documents = []

        # Lieferantenrechnung 1
        doc1 = MagicMock()
        doc1.id = uuid4()
        doc1.owner_id = sample_user_id
        doc1.document_type = "supplier_invoice"
        doc1.deleted_at = None
        doc1.extracted_data = {
            "invoice_number": "LR-2024-001",
            "creditor_name": "Lieferant A",
            "total_amount": "5000.00",
            "due_date": (today - timedelta(days=5)).isoformat(),
        }
        documents.append(doc1)

        # Bestellung 2
        doc2 = MagicMock()
        doc2.id = uuid4()
        doc2.owner_id = sample_user_id
        doc2.document_type = "purchase_order"
        doc2.deleted_at = None
        doc2.extracted_data = {
            "invoice_number": "BE-2024-001",
            "supplier_name": "Lieferant B",
            "total_amount": "2500.00",
            "due_date": (today + timedelta(days=7)).isoformat(),
        }
        documents.append(doc2)

        return documents

    @pytest.mark.asyncio
    async def test_get_payables_aging(
        self, service: AgingReportService, mock_db, sample_user_id, sample_payable_documents
    ):
        """Sollte Verbindlichkeiten-Aging berechnen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_payable_documents
        mock_db.execute = AsyncMock(return_value=mock_result)

        report = await service.get_payables_aging(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert report.report_type == ReportType.PAYABLES
        assert report.total_count == 2


class TestAsyncAgingSummary:
    """Tests fuer async get_aging_summary."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_aging_summary(
        self, service: AgingReportService, mock_db, sample_user_id
    ):
        """Sollte kombinierte Aging-Zusammenfassung zurueckgeben."""
        # Mock leere Ergebnisse
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await service.get_aging_summary(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert "receivables" in summary
        assert "payables" in summary
        assert "net_position" in summary
        assert "generated_at" in summary


class TestAsyncTopDebtors:
    """Tests fuer async get_top_debtors."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_debtor_documents(self, sample_user_id):
        """Sample Dokumente fuer Top-Debtors Test."""
        today = date.today()
        documents = []

        # Mehrere Rechnungen vom gleichen Kunden
        for i in range(5):
            doc = MagicMock()
            doc.id = uuid4()
            doc.owner_id = sample_user_id
            doc.document_type = "invoice"
            doc.deleted_at = None
            doc.extracted_data = {
                "invoice_number": f"RE-2024-00{i+1}",
                "creditor_name": "Grosser Kunde GmbH",
                "total_amount": str(1000 + i * 500),
                "due_date": (today - timedelta(days=10 + i * 5)).isoformat(),
            }
            documents.append(doc)

        # Ein einzelner kleinerer Kunde
        doc_small = MagicMock()
        doc_small.id = uuid4()
        doc_small.owner_id = sample_user_id
        doc_small.document_type = "invoice"
        doc_small.deleted_at = None
        doc_small.extracted_data = {
            "invoice_number": "RE-2024-010",
            "creditor_name": "Kleiner Kunde",
            "total_amount": "500.00",
            "due_date": (today - timedelta(days=5)).isoformat(),
        }
        documents.append(doc_small)

        return documents

    @pytest.mark.asyncio
    async def test_get_top_debtors(
        self, service: AgingReportService, mock_db, sample_user_id, sample_debtor_documents
    ):
        """Sollte Top-Schuldner zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_debtor_documents
        mock_db.execute = AsyncMock(return_value=mock_result)

        debtors = await service.get_top_debtors(
            db=mock_db,
            user_id=sample_user_id,
            limit=5,
        )

        assert len(debtors) <= 5
        # Erster sollte der groesste sein
        if len(debtors) >= 2:
            assert debtors[0]["total_amount"] >= debtors[1]["total_amount"]

    @pytest.mark.asyncio
    async def test_get_top_debtors_empty(
        self, service: AgingReportService, mock_db, sample_user_id
    ):
        """Sollte leere Liste bei keinen Dokumenten zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        debtors = await service.get_top_debtors(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert debtors == []


class TestAsyncTopCreditors:
    """Tests fuer async get_top_creditors."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_top_creditors_empty(
        self, service: AgingReportService, mock_db, sample_user_id
    ):
        """Sollte leere Liste bei keinen Dokumenten zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        creditors = await service.get_top_creditors(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert creditors == []


class TestAsyncDSOCalculation:
    """Tests fuer async calculate_dso."""

    @pytest.fixture
    def service(self) -> AgingReportService:
        return AgingReportService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_calculate_dso_no_revenue(
        self, service: AgingReportService, mock_db, sample_user_id
    ):
        """Sollte DSO 0 bei keinem Umsatz zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        dso = await service.calculate_dso(
            db=mock_db,
            user_id=sample_user_id,
        )

        assert "dso" in dso
        assert "period_days" in dso
        assert "interpretation" in dso

    @pytest.mark.asyncio
    async def test_calculate_dso_with_documents(
        self, service: AgingReportService, mock_db, sample_user_id
    ):
        """Sollte DSO mit Dokumenten berechnen."""
        today = date.today()

        # Offene Rechnung
        open_invoice = MagicMock()
        open_invoice.id = uuid4()
        open_invoice.owner_id = sample_user_id
        open_invoice.document_type = "invoice"
        open_invoice.deleted_at = None
        open_invoice.created_at = today - timedelta(days=30)
        open_invoice.extracted_data = {
            "total_amount": "5000.00",
            "due_date": (today - timedelta(days=10)).isoformat(),
        }

        # Bezahlte Rechnung (fuer Umsatz)
        paid_invoice = MagicMock()
        paid_invoice.id = uuid4()
        paid_invoice.owner_id = sample_user_id
        paid_invoice.document_type = "invoice"
        paid_invoice.deleted_at = None
        paid_invoice.created_at = today - timedelta(days=60)
        paid_invoice.extracted_data = {
            "total_amount": "10000.00",
            "payment_status": "paid",
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [open_invoice, paid_invoice]
        mock_db.execute = AsyncMock(return_value=mock_result)

        dso = await service.calculate_dso(
            db=mock_db,
            user_id=sample_user_id,
            period_days=90,
        )

        assert dso["period_days"] == 90
        assert "receivables" in dso
        assert "revenue" in dso
