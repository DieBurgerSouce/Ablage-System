# -*- coding: utf-8 -*-
"""
Unit Tests fuer TaxAuthorityExportService.

Testet:
- GDPdU-konformen Export (XML + CSV)
- Tabellendefinitionen
- Index.xml Generierung
- ZIP-Archiv-Erstellung
- Pruefsummen-Berechnung

Feature 20: Tax Authority Export Format (§90 III AO)
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
import os
import tempfile
import zipfile
import pytest

from app.services.compliance.tax_authority_export_service import (
    TaxAuthorityExportService,
    ExportFormat,
    DataCategory,
    ExportField,
    ExportTable,
    ExportStatistics,
    ExportResult,
    get_invoice_table_definition,
    get_bank_transaction_table_definition,
    get_document_table_definition,
    get_audit_log_table_definition,
    get_tax_authority_export_service,
    ENCODING,
    MAX_FIELD_LENGTH,
    GDPDU_NAMESPACE,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Erstelle Service-Instanz."""
    return TaxAuthorityExportService(mock_db)


@pytest.fixture
def mock_company():
    """Mock Company."""
    company = MagicMock()
    company.id = uuid4()
    company.name = "Test GmbH"
    return company


@pytest.fixture
def temp_output_dir():
    """Temporaeres Ausgabeverzeichnis."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# =============================================================================
# Table Definition Tests
# =============================================================================


class TestTableDefinitions:
    """Tests fuer Tabellendefinitionen."""

    def test_invoice_table_definition(self):
        """Test: Rechnungstabellen-Definition ist vollstaendig."""
        table = get_invoice_table_definition()

        assert table.name == "rechnungen"
        assert table.category == DataCategory.INVOICES_OUTGOING
        assert table.primary_key == "rechnungsnummer"
        assert len(table.fields) > 10

        # Pflichtfelder pruefen
        field_names = [f.name for f in table.fields]
        assert "rechnungsnummer" in field_names
        assert "rechnungsart" in field_names
        assert "rechnungsdatum" in field_names
        assert "bruttobetrag" in field_names

    def test_bank_transaction_table_definition(self):
        """Test: Bankbewegungstabellen-Definition ist vollstaendig."""
        table = get_bank_transaction_table_definition()

        assert table.name == "bankbewegungen"
        assert table.category == DataCategory.BANK_TRANSACTIONS
        assert table.primary_key == "transaktions_id"

        field_names = [f.name for f in table.fields]
        assert "transaktions_id" in field_names
        assert "buchungsdatum" in field_names
        assert "betrag" in field_names
        assert "verwendungszweck" in field_names

    def test_document_table_definition(self):
        """Test: Dokumententabellen-Definition ist vollstaendig."""
        table = get_document_table_definition()

        assert table.name == "belege"
        assert table.category == DataCategory.DOCUMENTS
        assert table.primary_key == "dokument_id"

        field_names = [f.name for f in table.fields]
        assert "dokument_id" in field_names
        assert "dokumenttyp" in field_names
        # Feldname mit Umlaut (deutsche Finanzbehoerden-Konvention)
        assert "prüfsumme_sha256" in field_names

    def test_audit_log_table_definition(self):
        """Test: Aenderungsprotokoll-Definition ist vollstaendig."""
        table = get_audit_log_table_definition()

        # Tabellenname mit Umlaut (deutsche Finanzbehoerden-Konvention)
        assert table.name == "änderungsprotokoll"
        assert table.category == DataCategory.AUDIT_LOG
        assert table.primary_key == "log_id"

        field_names = [f.name for f in table.fields]
        assert "log_id" in field_names
        assert "zeitstempel" in field_names
        assert "benutzer" in field_names
        assert "aktion" in field_names

    def test_field_types_valid(self):
        """Test: Alle Feldtypen sind gueltig."""
        valid_types = {"text", "numeric", "date", "datetime"}

        for table_fn in [
            get_invoice_table_definition,
            get_bank_transaction_table_definition,
            get_document_table_definition,
            get_audit_log_table_definition,
        ]:
            table = table_fn()
            for field in table.fields:
                assert field.data_type in valid_types, f"Ungueltiger Typ: {field.data_type}"

    def test_required_fields_marked(self):
        """Test: Pflichtfelder sind markiert."""
        table = get_invoice_table_definition()
        required_fields = [f for f in table.fields if f.required]

        assert len(required_fields) >= 1
        assert any(f.name == "rechnungsnummer" for f in required_fields)


# =============================================================================
# Export Field Tests
# =============================================================================


class TestExportField:
    """Tests fuer ExportField Dataclass."""

    def test_text_field(self):
        """Test: Textfeld-Konfiguration."""
        field = ExportField(
            name="test_field",
            description="Testfeld",
            data_type="text",
            max_length=100,
            required=True,
        )

        assert field.name == "test_field"
        assert field.data_type == "text"
        assert field.max_length == 100
        assert field.required is True

    def test_numeric_field(self):
        """Test: Numerisches Feld mit Dezimalstellen."""
        field = ExportField(
            name="betrag",
            description="Betrag",
            data_type="numeric",
            decimal_places=2,
        )

        assert field.data_type == "numeric"
        assert field.decimal_places == 2


# =============================================================================
# Export Result Tests
# =============================================================================


class TestExportResult:
    """Tests fuer ExportResult Dataclass."""

    def test_to_dict_success(self):
        """Test: to_dict() bei erfolgreichem Export."""
        result = ExportResult(
            success=True,
            export_id="GDPDU_TEST_2024_123",
            format=ExportFormat.GDPDU,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            company_name="Test GmbH",
            created_at=datetime.now(timezone.utc),
            statistics=ExportStatistics(
                total_records=100,
                by_category={"rechnungen": 50, "bankbewegungen": 50},
            ),
            files=["rechnungen.csv", "index.xml"],
            archive_path="/tmp/export.zip",
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["export_id"] == "GDPDU_TEST_2024_123"
        assert d["format"] == "gdpdu"
        assert d["company_name"] == "Test GmbH"
        assert d["statistics"]["total_records"] == 100
        assert len(d["files"]) == 2
        assert d["archive_path"] == "/tmp/export.zip"
        assert d["error"] is None

    def test_to_dict_failure(self):
        """Test: to_dict() bei fehlgeschlagenem Export."""
        result = ExportResult(
            success=False,
            export_id="GDPDU_TEST_2024_123",
            format=ExportFormat.GDPDU,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            company_name="Test GmbH",
            created_at=datetime.now(timezone.utc),
            statistics=ExportStatistics(),
            files=[],
            error="Firma nicht gefunden",
        )

        d = result.to_dict()

        assert d["success"] is False
        assert d["error"] == "Firma nicht gefunden"
        assert d["files"] == []


# =============================================================================
# Service Method Tests
# =============================================================================


class TestTaxAuthorityExportService:
    """Tests fuer TaxAuthorityExportService."""

    def test_init(self, service, mock_db):
        """Test: Service-Initialisierung."""
        assert service.db == mock_db

    def test_generate_export_id(self, service):
        """Test: Export-ID-Generierung."""
        company_id = uuid4()
        period_start = date(2024, 1, 1)

        export_id = service._generate_export_id(company_id, period_start)

        assert export_id.startswith("GDPDU_")
        assert str(company_id)[:8] in export_id
        assert "2024" in export_id

    def test_generate_export_id_is_deterministic_prefix(self, service):
        """Test: Export-ID enthaelt Praefix, Company-Praefix und Jahr.

        (Der frueher getestete _parse_period existiert im Service nicht -
        Test auf die real vorhandene _generate_export_id-Logik umgestellt.)
        """
        company_id = uuid4()
        export_id_h1 = service._generate_export_id(company_id, date(2024, 1, 1))
        export_id_h2 = service._generate_export_id(company_id, date(2024, 7, 1))

        for eid in (export_id_h1, export_id_h2):
            assert eid.startswith("GDPDU_")
            assert str(company_id)[:8] in eid
            assert "2024" in eid


class TestGDPdUExport:
    """Tests fuer GDPdU-Export."""

    @pytest.mark.asyncio
    async def test_export_company_not_found(self, service, mock_db):
        """Test: Export schlaegt fehl wenn Firma nicht gefunden."""
        # Mock: Keine Firma gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.create_gdpdu_export(
            company_id=uuid4(),
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )

        assert result.success is False
        assert "Firma nicht gefunden" in result.error

    @pytest.mark.asyncio
    async def test_export_creates_files(self, service, mock_db, mock_company, temp_output_dir):
        """Test: Export erstellt die erwarteten Dateien."""
        # Der Export iteriert ueber ALLE DataCategory-Werte (inkl. beider
        # Rechnungsrichtungen) -> es fallen mehr als 5 db.execute-Aufrufe an.
        # Erstes Result = Company, alle weiteren = leere Trefferlisten.
        mock_company_result = MagicMock()
        mock_company_result.scalar_one_or_none.return_value = mock_company

        def empty_result():
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            r.scalar.return_value = 0
            return r

        first_call = {"done": False}

        async def execute_side_effect(*args, **kwargs):
            if not first_call["done"]:
                first_call["done"] = True
                return mock_company_result
            return empty_result()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await service.create_gdpdu_export(
            company_id=mock_company.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            output_dir=temp_output_dir,
        )

        assert result.success is True
        assert result.company_name == "Test GmbH"

        # Pruefen ob index.xml erstellt wurde
        assert any("index.xml" in f for f in result.files)

        # Pruefen ob DTD erstellt wurde
        assert any("dtd" in f for f in result.files)

    @pytest.mark.asyncio
    async def test_export_exception_returns_clean_failure(
        self, service, mock_db, mock_company
    ):
        """Regression: Exception waehrend Export liefert sauberes Fehler-Result.

        Frueher rief der except-Block ExportResult(**safe_error_log(e)) auf -
        safe_error_log liefert {"error_type", "error_id", ...}, was KEINE
        gueltigen ExportResult-Felder sind und SELBST einen TypeError ausloeste
        (verschleierte den eigentlichen Fehler). Jetzt: success=False + error.
        """
        mock_company_result = MagicMock()
        mock_company_result.scalar_one_or_none.return_value = mock_company
        mock_invoice_result = MagicMock()
        # Eine TypeError-aehnliche Stoerung beim Daten-Sammeln erzwingen:
        mock_invoice_result.scalars.side_effect = RuntimeError("DB kaputt")
        mock_db.execute = AsyncMock(side_effect=[
            mock_company_result,
            mock_invoice_result,
        ])

        result = await service.create_gdpdu_export(
            company_id=mock_company.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )

        # Kein TypeError mehr, sondern sauberes Fehler-Result
        assert result.success is False
        assert result.error is not None
        assert "Export fehlgeschlagen" in result.error


# =============================================================================
# Index XML Tests
# =============================================================================


class TestGDPdUIndex:
    """Tests fuer index.xml Generierung."""

    def test_create_gdpdu_index(self, service, temp_output_dir):
        """Test: index.xml wird korrekt erstellt."""
        # Erstelle Dummy-CSV-Dateien
        csv_files = [
            os.path.join(temp_output_dir, "rechnungen.csv"),
            os.path.join(temp_output_dir, "bankbewegungen.csv"),
        ]
        for f in csv_files:
            with open(f, "w") as fp:
                fp.write("header\n")

        index_path = service._create_gdpdu_index(
            output_dir=temp_output_dir,
            company_name="Test GmbH",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            data_files=csv_files,
        )

        assert os.path.exists(index_path)

        # XML-Inhalt pruefen
        with open(index_path, "r", encoding=ENCODING) as f:
            content = f.read()

        assert "DataSet" in content
        assert "Test GmbH" in content
        assert "2024-01-01" in content
        assert "2024-12-31" in content
        assert "rechnungen.csv" in content
        assert "bankbewegungen.csv" in content

    def test_create_gdpdu_dtd(self, service, temp_output_dir):
        """Test: DTD-Datei wird korrekt erstellt."""
        dtd_path = service._create_gdpdu_dtd(temp_output_dir)

        assert os.path.exists(dtd_path)
        assert dtd_path.endswith(".dtd")

        with open(dtd_path, "r", encoding=ENCODING) as f:
            content = f.read()

        assert "<!ELEMENT DataSet" in content
        assert "<!ELEMENT Version" in content
        assert "<!ELEMENT Table" in content


# =============================================================================
# Archive Tests
# =============================================================================


class TestArchiveCreation:
    """Tests fuer ZIP-Archiv-Erstellung."""

    def test_create_archive(self, service, temp_output_dir):
        """Test: ZIP-Archiv wird korrekt erstellt."""
        # Erstelle Testdateien
        test_file = os.path.join(temp_output_dir, "test.csv")
        with open(test_file, "w") as f:
            f.write("data\n")

        archive_path = f"{temp_output_dir}.zip"
        service._create_archive(temp_output_dir, archive_path)

        assert os.path.exists(archive_path)

        # Archiv pruefen
        with zipfile.ZipFile(archive_path, "r") as zf:
            assert "test.csv" in zf.namelist()

        # Cleanup
        os.remove(archive_path)

    def test_calculate_checksum(self, service, temp_output_dir):
        """Test: MD5-Pruefsumme wird berechnet."""
        # Erstelle Testdatei
        test_file = os.path.join(temp_output_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content\n")

        checksum = service._calculate_checksum(test_file)

        assert checksum is not None
        assert len(checksum) == 32  # MD5 = 32 Hex-Zeichen


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunction:
    """Tests fuer Factory-Funktion."""

    def test_get_tax_authority_export_service(self, mock_db):
        """Test: Factory erstellt Service korrekt."""
        service = get_tax_authority_export_service(mock_db)

        assert isinstance(service, TaxAuthorityExportService)
        assert service.db == mock_db


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Tests fuer Enums."""

    def test_export_format_values(self):
        """Test: ExportFormat Enum-Werte."""
        assert ExportFormat.GDPDU.value == "gdpdu"
        assert ExportFormat.CSV.value == "csv"
        assert ExportFormat.IDEA.value == "idea"
        assert ExportFormat.DATEV.value == "datev"

    def test_data_category_values(self):
        """Test: DataCategory Enum-Werte."""
        assert DataCategory.INVOICES_OUTGOING.value == "invoices_outgoing"
        assert DataCategory.INVOICES_INCOMING.value == "invoices_incoming"
        assert DataCategory.BANK_TRANSACTIONS.value == "bank_transactions"
        assert DataCategory.DOCUMENTS.value == "documents"
        assert DataCategory.AUDIT_LOG.value == "audit_log"


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests fuer Konstanten."""

    def test_encoding(self):
        """Test: Encoding ist UTF-8."""
        assert ENCODING == "UTF-8"

    def test_max_field_length(self):
        """Test: Maximale Feldlaenge fuer IDEA."""
        assert MAX_FIELD_LENGTH == 255

    def test_gdpdu_namespace(self):
        """Test: GDPdU XML Namespace."""
        assert "gdpdu" in GDPDU_NAMESPACE.lower()


# =============================================================================
# Count Records Tests
# =============================================================================


class TestCountRecordsByCategory:
    """Tests fuer count_records_by_category Methode."""

    @pytest.mark.asyncio
    async def test_count_records_empty_database(self, mock_db):
        """Test: Leere Datenbank gibt Nullen zurueck."""
        # Mock the execute results to return 0 for all counts
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TaxAuthorityExportService(mock_db)
        counts = await service.count_records_by_category(
            company_id=uuid4(),
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )

        assert counts["rechnungen"] == 0
        assert counts["bankbewegungen"] == 0
        assert counts["belege"] == 0
        assert counts["änderungsprotokoll"] == 0

    @pytest.mark.asyncio
    async def test_count_records_with_data(self, mock_db):
        """Test: Datensaetze werden korrekt gezaehlt."""
        # Mock different counts for each category
        call_count = 0
        expected_counts = [5, 10, 15, 20]  # invoices, transactions, documents, audit

        def get_scalar():
            nonlocal call_count
            count = expected_counts[call_count]
            call_count += 1
            return count

        mock_result = MagicMock()
        mock_result.scalar.side_effect = get_scalar
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TaxAuthorityExportService(mock_db)
        counts = await service.count_records_by_category(
            company_id=uuid4(),
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )

        assert counts["rechnungen"] == 5
        assert counts["bankbewegungen"] == 10
        assert counts["belege"] == 15
        assert counts["änderungsprotokoll"] == 20

    @pytest.mark.asyncio
    async def test_count_records_returns_dict(self, mock_db):
        """Test: Methode gibt Dictionary zurueck."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TaxAuthorityExportService(mock_db)
        counts = await service.count_records_by_category(
            company_id=uuid4(),
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )

        assert isinstance(counts, dict)
        assert len(counts) == 4  # 4 Kategorien
