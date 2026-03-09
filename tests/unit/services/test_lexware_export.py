# -*- coding: utf-8 -*-
"""
Tests fuer LexwareExportService.

Testet:
- Kunden-Export nach CSV
- Lieferanten-Export nach CSV
- Zahlungsstatus-Export
- Job-Verwaltung (get/list)
- CSV-Format-Validierung
- SICHERHEIT: Keine PII in Testdaten (IBAN, USt-IdNr sind Fake-Werte)
"""

import csv
import io
import sys
import pytest
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock
from uuid import UUID, uuid4

from app.services.lexware.lexware_export_service import (
    LexwareExportService,
    LexwareExportJob,
    LexwareExportType,
    LexwareExportStatus,
    _export_jobs,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db: AsyncMock) -> LexwareExportService:
    """Erstellt eine LexwareExportService-Instanz."""
    return LexwareExportService(mock_db)


@pytest.fixture(autouse=True)
def cleanup_jobs():
    """Raeumt den In-Memory-Store nach jedem Test auf."""
    yield
    _export_jobs.clear()


def _make_mock_entity(
    name: str = "Test GmbH",
    entity_type: str = "customer",
    external_id: str = "K-00001",
) -> Mock:
    """Erzeugt ein Mock-BusinessEntity."""
    entity = Mock()
    entity.name = name
    entity.entity_type = entity_type
    entity.external_id = external_id
    entity.email = "info@test-firma.example.com"
    entity.phone = "+49-000-0000000"
    entity.tax_number = "00/000/00000"
    entity.vat_id = "DE000000000"
    entity.address = {
        "salutation": "Firma",
        "first_name": "Max",
        "last_name": "Mustermann",
        "street": "Teststrasse 1",
        "zip_code": "00000",
        "city": "Teststadt",
        "country": "DE",
    }
    entity.bank_details = {
        "iban": "DE00000000000000000000",
        "bic": "TESTDEFFXXX",
    }
    return entity


def _make_mock_invoice_tracking(
    invoice_number: str = "RE-TEST-001",
    status: str = "paid",
    amount: float = 1000.00,
    paid_amount: float = 1000.00,
) -> Mock:
    """Erzeugt ein Mock-InvoiceTracking."""
    tracking = Mock()
    tracking.invoice_number = invoice_number
    tracking.status = status
    tracking.amount = amount
    tracking.paid_amount = paid_amount
    tracking.payment_date = datetime(2026, 1, 15, tzinfo=timezone.utc)
    tracking.payment_method = "ueberweisung"
    tracking.updated_at = datetime.now(timezone.utc)
    return tracking


def _setup_export_mock(mock_db: AsyncMock, items: list) -> None:
    """Konfiguriert mock_db.execute fuer Export-Queries."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    mock_db.execute = AsyncMock(return_value=mock_result)


import contextlib


def _make_chainable_select():
    """Erstellt einen Mock fuer select() der .where()/.order_by() unterstuetzt."""
    mock_stmt = MagicMock()
    mock_stmt.where.return_value = mock_stmt
    mock_stmt.order_by.return_value = mock_stmt

    def fake_select(*args, **kwargs):
        return mock_stmt

    return fake_select


@contextlib.contextmanager
def _export_patches():
    """Patcht select() und Modell-Klassen damit SQLAlchemy-Queries nicht auf echte Spalten zugreifen."""
    mock_be = MagicMock()
    mock_it = MagicMock()
    mock_models = MagicMock()
    mock_models.BusinessEntity = mock_be
    mock_models.InvoiceTracking = mock_it

    fake_select = _make_chainable_select()

    with patch("app.services.lexware.lexware_export_service.select", fake_select), \
         patch.dict("sys.modules", {"app.db.models": mock_models}):
        yield


class TestExportCustomers:
    """Tests fuer export_customers()."""

    @pytest.mark.asyncio
    async def test_exportiert_kunden_als_csv(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Kunden werden korrekt als CSV exportiert."""
        entities = [_make_mock_entity(), _make_mock_entity(name="Zweite GmbH", external_id="K-00002")]
        _setup_export_mock(mock_db, entities)

        with _export_patches():
            job = await service.export_customers(uuid4())

        assert job.status == LexwareExportStatus.READY
        assert job.export_type == LexwareExportType.CUSTOMERS
        assert job.record_count == 2
        assert job.csv_content is not None

        # CSV pruefen
        reader = csv.reader(io.StringIO(job.csv_content), delimiter=";")
        rows = list(reader)
        assert len(rows) == 3  # Header + 2 Datensaetze

    @pytest.mark.asyncio
    async def test_leerer_export_bei_keinen_kunden(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Export ohne Kunden ergibt CSV nur mit Header."""
        _setup_export_mock(mock_db, [])

        with _export_patches():
            job = await service.export_customers(uuid4())

        assert job.record_count == 0
        assert job.status == LexwareExportStatus.READY
        assert job.csv_content is not None

    @pytest.mark.asyncio
    async def test_fehlende_adresse_wird_leer_exportiert(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Fehlende Adresse fuehrt zu leeren Feldern statt Fehler."""
        entity = _make_mock_entity()
        entity.address = None
        _setup_export_mock(mock_db, [entity])

        with _export_patches():
            job = await service.export_customers(uuid4())

        assert job.status == LexwareExportStatus.READY


class TestExportSuppliers:
    """Tests fuer export_suppliers()."""

    @pytest.mark.asyncio
    async def test_exportiert_lieferanten_mit_bankdaten(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Lieferanten-Export enthaelt IBAN und BIC."""
        entity = _make_mock_entity(entity_type="supplier", external_id="L-00001")
        _setup_export_mock(mock_db, [entity])

        with _export_patches():
            job = await service.export_suppliers(uuid4())

        assert job.export_type == LexwareExportType.SUPPLIERS
        assert job.record_count == 1
        assert "IBAN" in job.csv_content

    @pytest.mark.asyncio
    async def test_fehlende_bankdaten_werden_leer_exportiert(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Fehlende Bankdaten fuehren zu leeren Feldern."""
        entity = _make_mock_entity(entity_type="supplier")
        entity.bank_details = None
        _setup_export_mock(mock_db, [entity])

        with _export_patches():
            job = await service.export_suppliers(uuid4())

        assert job.status == LexwareExportStatus.READY


class TestExportPaymentStatus:
    """Tests fuer export_payment_status()."""

    @pytest.mark.asyncio
    async def test_exportiert_zahlungsstatus(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Zahlungsstatus wird korrekt exportiert."""
        tracking = _make_mock_invoice_tracking()
        _setup_export_mock(mock_db, [tracking])

        with _export_patches():
            job = await service.export_payment_status(uuid4())

        assert job.export_type == LexwareExportType.PAYMENTS
        assert job.record_count == 1
        assert "Zahlungsdatum" in job.csv_content

    @pytest.mark.asyncio
    async def test_teilzahlung_zeigt_restbetrag(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Teilzahlung berechnet Restbetrag korrekt."""
        tracking = _make_mock_invoice_tracking(
            status="partial",
            amount=1000.00,
            paid_amount=600.00,
        )
        _setup_export_mock(mock_db, [tracking])

        with _export_patches():
            job = await service.export_payment_status(uuid4())

        assert "400.00" in job.csv_content  # Restbetrag


class TestJobVerwaltung:
    """Tests fuer get_job() und list_jobs()."""

    def test_get_job_findet_existierenden_job(
        self, service: LexwareExportService
    ):
        """get_job() findet einen gespeicherten Job."""
        job = LexwareExportJob(
            id="test-job-id",
            company_id="company-1",
            export_type=LexwareExportType.CUSTOMERS,
        )
        _export_jobs["test-job-id"] = job

        result = service.get_job("test-job-id")

        assert result is not None
        assert result.id == "test-job-id"

    def test_get_job_gibt_none_fuer_unbekannten_job(
        self, service: LexwareExportService
    ):
        """get_job() gibt None fuer unbekannte Job-IDs zurueck."""
        result = service.get_job("nicht-existent")
        assert result is None

    def test_list_jobs_filtert_nach_company(
        self, service: LexwareExportService
    ):
        """list_jobs() filtert nach company_id."""
        _export_jobs["j1"] = LexwareExportJob(
            id="j1", company_id="company-1", export_type=LexwareExportType.CUSTOMERS
        )
        _export_jobs["j2"] = LexwareExportJob(
            id="j2", company_id="company-2", export_type=LexwareExportType.SUPPLIERS
        )
        _export_jobs["j3"] = LexwareExportJob(
            id="j3", company_id="company-1", export_type=LexwareExportType.PAYMENTS
        )

        result = service.list_jobs("company-1")

        assert len(result) == 2
        assert all(j.company_id == "company-1" for j in result)

    def test_list_jobs_respektiert_limit(
        self, service: LexwareExportService
    ):
        """list_jobs() begrenzt die Ergebnisse auf limit."""
        for i in range(10):
            _export_jobs[f"j{i}"] = LexwareExportJob(
                id=f"j{i}",
                company_id="company-1",
                export_type=LexwareExportType.CUSTOMERS,
            )

        result = service.list_jobs("company-1", limit=3)

        assert len(result) == 3


class TestCSVSicherheit:
    """Sicherheitstests fuer CSV-Exporte."""

    @pytest.mark.asyncio
    async def test_keine_echten_pii_in_export(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """Exportierte Testdaten enthalten keine echten PII-Daten."""
        entity = _make_mock_entity()
        _setup_export_mock(mock_db, [entity])

        with _export_patches():
            job = await service.export_customers(uuid4())

        # Sicherstellen, dass nur Fake-Daten enthalten sind
        assert "DE000000000" in job.csv_content  # Fake USt-IdNr
        assert "00/000/00000" in job.csv_content  # Fake Steuernummer

    @pytest.mark.asyncio
    async def test_semikolon_delimiter_fuer_deutsches_excel(
        self, service: LexwareExportService, mock_db: AsyncMock
    ):
        """CSV nutzt Semikolon als Trennzeichen (Standard fuer deutsches Excel)."""
        _setup_export_mock(mock_db, [])

        with _export_patches():
            job = await service.export_customers(uuid4())

        assert ";" in job.csv_content
