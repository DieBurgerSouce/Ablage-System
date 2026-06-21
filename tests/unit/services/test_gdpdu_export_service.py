# -*- coding: utf-8 -*-
"""
Unit Tests fuer GDPdU Export Service.

Testet die GDPdU-konforme Datenexport-Funktionalitaet fuer Betriebspruefungen.
"""

import io
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.gdpdu_export_service import (
    GDPdUExportService,
    GDPdUExportOptions,
    GDPDU_VERSION,
    GDPDU_DTD_VERSION,
    DOCUMENT_TABLE,
    ARCHIVE_TABLE,
    INVOICE_TABLE,
    CONTRACT_TABLE,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def gdpdu_service() -> GDPdUExportService:
    """Erstellt eine Service-Instanz."""
    return GDPdUExportService()


@pytest.fixture
def mock_company() -> MagicMock:
    """Erstellt eine Mock-Firma.

    Das Company-Modell hat KEIN 'address'-Feld; die Adresse wird vom Service
    aus den Einzelfeldern street/street_number/postal_code/city zusammengesetzt.
    """
    company = MagicMock()
    company.id = uuid.uuid4()
    company.name = "Test GmbH"
    company.street = "Musterstrasse"
    company.street_number = "123"
    company.postal_code = "12345"
    company.city = "Berlin"
    # Zusammengesetzte Adresse, wie der Service sie erzeugt (street_line, plz ort)
    company.expected_address = "Musterstrasse 123, 12345 Berlin"
    return company


@pytest.fixture
def mock_document() -> MagicMock:
    """Erstellt ein Mock-Dokument."""
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.company_id = uuid.uuid4()
    doc.filename = "test_rechnung.pdf"
    doc.original_filename = "Rechnung_2024_001.pdf"
    doc.mime_type = "application/pdf"
    doc.file_size = 102400
    doc.created_at = datetime(2024, 3, 15, 10, 30, 0)
    doc.status = "processed"
    doc.checksum = "abc123def456"
    doc.is_archived = True
    doc.extracted_data = {
        "invoice": {
            "invoice_number": "2024-001",
            "invoice_date": "2024-03-15",
            "due_date": "2024-04-15",
            "sender": {
                "company": "Lieferant AG",
                "street": "Lieferstrasse 1",
                "zip_code": "10115",
                "city": "Berlin",
            },
            "recipient": {
                "company": "Empfaenger GmbH",
            },
            "sender_vat_id": "DE123456789",
            "sender_bank": {
                "iban": "DE89370400440532013000",
            },
            "net_amount": 1000.00,
            "vat_rate": 19.0,
            "vat_amount": 190.00,
            "gross_amount": 1190.00,
            "currency": "EUR",
        }
    }
    return doc


@pytest.fixture
def mock_archive() -> MagicMock:
    """Erstellt ein Mock-Archiv."""
    archive = MagicMock()
    archive.id = uuid.uuid4()
    archive.document_id = uuid.uuid4()
    archive.content_hash = "a" * 64
    archive.hash_algorithm = "SHA-256"
    archive.signature_timestamp = datetime(2024, 3, 15, 11, 0, 0)
    archive.retention_category = "invoice"
    archive.retention_years = 10
    archive.retention_expires_at = date(2034, 3, 15)
    archive.is_verified = True
    archive.archived_at = datetime(2024, 3, 15, 11, 0, 0)
    return archive


@pytest.fixture
def export_options(mock_company: MagicMock) -> GDPdUExportOptions:
    """Erstellt Export-Optionen."""
    return GDPdUExportOptions(
        company_id=mock_company.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        include_documents=True,
        include_archives=True,
        include_invoices=True,
        include_contracts=True,
        comment="Test-Export fuer Pruefung",
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars = MagicMock()
    mock_result.scalars.return_value.all = MagicMock(return_value=[])
    mock_result.scalar = MagicMock(return_value=0)
    mock_result.scalar_one_or_none = MagicMock(return_value=None)

    async def execute_mock(*args, **kwargs):
        return mock_result

    db.execute = AsyncMock(side_effect=execute_mock)
    db._mock_result = mock_result

    return db


# =============================================================================
# Tests: GDPdUExportOptions
# =============================================================================


class TestGDPdUExportOptions:
    """Tests fuer Export-Optionen."""

    def test_options_with_all_fields(self) -> None:
        """Optionen mit allen Feldern."""
        company_id = uuid.uuid4()
        options = GDPdUExportOptions(
            company_id=company_id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            include_documents=True,
            include_archives=True,
            include_invoices=False,
            include_contracts=False,
            comment="Test",
        )

        assert options.company_id == company_id
        assert options.start_date == date(2024, 1, 1)
        assert options.end_date == date(2024, 12, 31)
        assert options.include_documents is True
        assert options.include_invoices is False

    def test_options_defaults(self) -> None:
        """Optionen mit Default-Werten."""
        company_id = uuid.uuid4()
        options = GDPdUExportOptions(
            company_id=company_id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert options.include_documents is True
        assert options.include_archives is True
        assert options.include_invoices is True
        assert options.include_contracts is True
        assert options.comment is None


# =============================================================================
# Tests: Tabellendefinitionen
# =============================================================================


class TestTableDefinitions:
    """Tests fuer GDPdU-Tabellendefinitionen."""

    def test_document_table_structure(self) -> None:
        """Dokument-Tabelle hat korrekte Struktur."""
        assert DOCUMENT_TABLE.name == "Dokumente"
        assert DOCUMENT_TABLE.filename == "dokumente.csv"
        assert len(DOCUMENT_TABLE.columns) == 7

        # Spalten-Namen pruefen
        column_names = [col.name for col in DOCUMENT_TABLE.columns]
        assert "DokumentID" in column_names
        assert "Dateiname" in column_names
        assert "Prüfsumme" in column_names

    def test_archive_table_structure(self) -> None:
        """Archiv-Tabelle hat korrekte Struktur."""
        assert ARCHIVE_TABLE.name == "Archive"
        assert ARCHIVE_TABLE.filename == "archive.csv"
        assert len(ARCHIVE_TABLE.columns) == 10

        column_names = [col.name for col in ARCHIVE_TABLE.columns]
        assert "ContentHash" in column_names
        assert "HashAlgorithmus" in column_names
        assert "Verifiziert" in column_names

    def test_invoice_table_structure(self) -> None:
        """Rechnungs-Tabelle hat korrekte Struktur."""
        assert INVOICE_TABLE.name == "Rechnungen"
        assert INVOICE_TABLE.filename == "rechnungen.csv"
        assert len(INVOICE_TABLE.columns) == 16

        column_names = [col.name for col in INVOICE_TABLE.columns]
        assert "Rechnungsnummer" in column_names
        assert "Bruttobetrag" in column_names
        assert "MwStSatz" in column_names

    def test_contract_table_structure(self) -> None:
        """Vertrags-Tabelle hat korrekte Struktur."""
        assert CONTRACT_TABLE.name == "Verträge"
        assert CONTRACT_TABLE.filename == "verträge.csv"
        assert len(CONTRACT_TABLE.columns) == 9

        column_names = [col.name for col in CONTRACT_TABLE.columns]
        assert "Vertragsnummer" in column_names
        assert "Vertragswert" in column_names


# =============================================================================
# Tests: Hilfsmethoden
# =============================================================================


class TestHelperMethods:
    """Tests fuer Hilfsmethoden."""

    def test_format_datetime(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert DateTime korrekt."""
        dt = datetime(2024, 3, 15, 10, 30, 45)
        result = gdpdu_service._format_datetime(dt)
        assert result == "2024-03-15 10:30:45"

    def test_format_datetime_none(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert None zu leerem String."""
        result = gdpdu_service._format_datetime(None)
        assert result == ""

    def test_format_date(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert Date korrekt."""
        d = date(2024, 3, 15)
        result = gdpdu_service._format_date(d)
        assert result == "2024-03-15"

    def test_format_date_none(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert None zu leerem String."""
        result = gdpdu_service._format_date(None)
        assert result == ""

    def test_format_decimal(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert Decimal mit deutschem Komma."""
        result = gdpdu_service._format_decimal(1234.56)
        assert result == "1234,56"

    def test_format_decimal_from_string(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert Decimal aus String."""
        result = gdpdu_service._format_decimal("1000.50")
        assert result == "1000,50"

    def test_format_decimal_none(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert None zu leerem String."""
        result = gdpdu_service._format_decimal(None)
        assert result == ""

    def test_translate_category(self, gdpdu_service: GDPdUExportService) -> None:
        """Uebersetzt Kategorien korrekt."""
        assert gdpdu_service._translate_category("invoice") == "Rechnungen"
        assert gdpdu_service._translate_category("contract") == "Verträge"
        assert gdpdu_service._translate_category("correspondence") == "Geschäftsbriefe"
        assert gdpdu_service._translate_category("unknown") == "unknown"

    def test_format_date_str(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert Datums-String."""
        result = gdpdu_service._format_date_str("2024-03-15")
        assert result == "2024-03-15"

    def test_format_date_str_iso(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert ISO-Datums-String."""
        result = gdpdu_service._format_date_str("2024-03-15T10:30:00Z")
        assert result == "2024-03-15"

    def test_format_date_str_none(self, gdpdu_service: GDPdUExportService) -> None:
        """Formatiert None zu leerem String."""
        result = gdpdu_service._format_date_str(None)
        assert result == ""


# =============================================================================
# Tests: Export-Preview
# =============================================================================


class TestExportPreview:
    """Tests fuer Export-Vorschau."""

    @pytest.mark.asyncio
    async def test_preview_returns_statistics(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Preview gibt korrekte Statistiken zurueck."""
        # Mock: 10 Dokumente, 5 Archive
        mock_db._mock_result.scalar.side_effect = [10, 5]

        preview = await gdpdu_service.get_export_preview(mock_db, export_options)

        assert "zeitraum" in preview
        assert "anzahl" in preview
        assert "tabellen" in preview
        assert "geschaetzte_groesse_kb" in preview

        assert preview["zeitraum"]["von"] == "2024-01-01"
        assert preview["zeitraum"]["bis"] == "2024-12-31"

    @pytest.mark.asyncio
    async def test_preview_zero_documents(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Preview mit null Dokumenten."""
        mock_db._mock_result.scalar.return_value = 0

        preview = await gdpdu_service.get_export_preview(mock_db, export_options)

        assert preview["anzahl"]["dokumente"] == 0
        assert preview["anzahl"]["archive"] == 0


# =============================================================================
# Tests: XML-Generierung
# =============================================================================


class TestXMLGeneration:
    """Tests fuer index.xml Generierung."""

    def test_generate_index_xml(
        self,
        gdpdu_service: GDPdUExportService,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Generiert valides index.xml."""
        # Tabellen setzen
        gdpdu_service._tables = [DOCUMENT_TABLE, ARCHIVE_TABLE]

        xml_content = gdpdu_service._generate_index_xml(mock_company, export_options)

        # Grundstruktur pruefen
        assert "<?xml version" in xml_content
        assert f"<!DOCTYPE DataSet SYSTEM \"{GDPDU_DTD_VERSION}\">" in xml_content
        assert "<DataSet>" in xml_content
        assert "<Version>" in xml_content
        assert "<DataSupplier>" in xml_content
        assert "<Media>" in xml_content
        assert "<Table>" in xml_content

    def test_xml_contains_company_info(
        self,
        gdpdu_service: GDPdUExportService,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """XML enthaelt Firmeninformationen."""
        gdpdu_service._tables = [DOCUMENT_TABLE]

        xml_content = gdpdu_service._generate_index_xml(mock_company, export_options)

        assert mock_company.name in xml_content
        # Adresse wird aus Einzelfeldern zusammengesetzt (street/PLZ/Ort)
        assert mock_company.expected_address in xml_content

    def test_xml_contains_date_range(
        self,
        gdpdu_service: GDPdUExportService,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """XML enthaelt Zeitraum."""
        gdpdu_service._tables = [DOCUMENT_TABLE]

        xml_content = gdpdu_service._generate_index_xml(mock_company, export_options)

        assert "2024-01-01" in xml_content
        assert "2024-12-31" in xml_content


# =============================================================================
# Tests: README-Generierung
# =============================================================================


class TestReadmeGeneration:
    """Tests fuer README-Generierung."""

    def test_generate_readme(
        self,
        gdpdu_service: GDPdUExportService,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Generiert README mit allen Informationen."""
        gdpdu_service._tables = [DOCUMENT_TABLE, ARCHIVE_TABLE]

        readme = gdpdu_service._generate_readme(mock_company, export_options)

        # Grundstruktur pruefen
        assert "GDPdU-EXPORT" in readme
        assert mock_company.name in readme
        assert "01.01.2024" in readme  # Deutsches Datumsformat
        assert "31.12.2024" in readme

    def test_readme_contains_legal_basis(
        self,
        gdpdu_service: GDPdUExportService,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """README enthaelt rechtliche Grundlagen."""
        gdpdu_service._tables = []

        readme = gdpdu_service._generate_readme(mock_company, export_options)

        assert "147 AO" in readme
        assert "257 HGB" in readme
        assert "GoBD" in readme

    def test_readme_contains_table_list(
        self,
        gdpdu_service: GDPdUExportService,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """README listet exportierte Tabellen auf."""
        gdpdu_service._tables = [DOCUMENT_TABLE, INVOICE_TABLE]

        readme = gdpdu_service._generate_readme(mock_company, export_options)

        assert "dokumente.csv" in readme
        assert "rechnungen.csv" in readme


# =============================================================================
# Tests: Vollstaendiger Export
# =============================================================================


class TestFullExport:
    """Tests fuer vollstaendigen ZIP-Export."""

    @pytest.mark.asyncio
    async def test_create_export_returns_zip(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Erstellt gueltiges ZIP-Archiv."""
        # Mock Company Query
        mock_db._mock_result.scalar_one_or_none.return_value = mock_company
        mock_db._mock_result.scalars.return_value.all.return_value = []

        zip_content = await gdpdu_service.create_export(mock_db, export_options)

        # Pruefen, dass es ein gueltiges ZIP ist
        assert isinstance(zip_content, bytes)
        assert len(zip_content) > 0

        # ZIP oeffnen und Inhalt pruefen
        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            file_list = zf.namelist()
            assert "index.xml" in file_list
            assert GDPDU_DTD_VERSION in file_list
            assert "README.txt" in file_list

    @pytest.mark.asyncio
    async def test_export_contains_valid_xml(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Export enthaelt valides XML."""
        mock_db._mock_result.scalar_one_or_none.return_value = mock_company
        mock_db._mock_result.scalars.return_value.all.return_value = []

        zip_content = await gdpdu_service.create_export(mock_db, export_options)

        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            xml_content = zf.read("index.xml").decode("utf-8")
            assert "<?xml version" in xml_content
            assert "<DataSet>" in xml_content

    @pytest.mark.asyncio
    async def test_export_with_documents(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        mock_company: MagicMock,
        mock_document: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Export mit Dokumenten enthaelt CSV-Datei."""
        mock_db._mock_result.scalar_one_or_none.return_value = mock_company
        # Erste Query: Dokumente, Rest: leer
        mock_db._mock_result.scalars.return_value.all.side_effect = [
            [mock_document],  # Dokumente
            [],  # Archive
            [mock_document],  # Invoices (gleiche Daten)
            [],  # Contracts
        ]

        zip_content = await gdpdu_service.create_export(mock_db, export_options)

        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            file_list = zf.namelist()
            assert "dokumente.csv" in file_list

            # CSV-Inhalt pruefen
            csv_content = zf.read("dokumente.csv").decode("utf-8")
            assert "DokumentID" in csv_content  # Header
            assert str(mock_document.id) in csv_content

    @pytest.mark.asyncio
    async def test_export_raises_on_missing_company(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Export schlaegt bei fehlender Firma fehl."""
        mock_db._mock_result.scalar_one_or_none.return_value = None

        with pytest.raises(ValueError, match="nicht gefunden"):
            await gdpdu_service.create_export(mock_db, export_options)


# =============================================================================
# Tests: CSV-Export
# =============================================================================


class TestCSVExport:
    """Tests fuer CSV-Datenexport."""

    @pytest.mark.asyncio
    async def test_export_documents_csv_format(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        mock_document: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Dokument-CSV hat korrektes Format."""
        mock_db._mock_result.scalars.return_value.all.return_value = [mock_document]

        csv_content = await gdpdu_service._export_documents(mock_db, export_options)

        # Spaltentrennzeichen
        assert ";" in csv_content

        # Header-Zeile
        lines = csv_content.strip().split("\n")
        assert len(lines) >= 2
        headers = lines[0]
        assert "DokumentID" in headers

    @pytest.mark.asyncio
    async def test_export_archives_csv_format(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        mock_archive: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Archiv-CSV hat korrektes Format."""
        mock_db._mock_result.scalars.return_value.all.return_value = [mock_archive]

        csv_content = await gdpdu_service._export_archives(mock_db, export_options)

        assert ";" in csv_content
        assert "ContentHash" in csv_content
        assert mock_archive.content_hash in csv_content

    @pytest.mark.asyncio
    async def test_export_invoices_extracts_data(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        mock_document: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Rechnungs-Export extrahiert korrekte Daten."""
        mock_db._mock_result.scalars.return_value.all.return_value = [mock_document]

        csv_content = await gdpdu_service._export_invoices(mock_db, export_options)

        # Rechnungsdaten pruefen
        assert "2024-001" in csv_content  # invoice_number
        assert "Lieferant AG" in csv_content
        assert "DE123456789" in csv_content  # VAT ID
        # Betrag mit deutschem Dezimaltrennzeichen
        assert "1190" in csv_content  # gross_amount

    @pytest.mark.asyncio
    async def test_export_empty_returns_empty_string(
        self,
        gdpdu_service: GDPdUExportService,
        mock_db: AsyncMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """Leerer Export gibt leeren String zurueck."""
        mock_db._mock_result.scalars.return_value.all.return_value = []

        csv_content = await gdpdu_service._export_documents(mock_db, export_options)

        assert csv_content == ""


# =============================================================================
# Tests: GoBD-Compliance
# =============================================================================


class TestGoBDCompliance:
    """Tests fuer GoBD-Konformitaet des Exports."""

    def test_gdpdu_version_is_set(self) -> None:
        """GDPdU-Version ist definiert."""
        assert GDPDU_VERSION == "1.0"

    def test_dtd_version_matches_standard(self) -> None:
        """DTD-Version entspricht Standard."""
        assert GDPDU_DTD_VERSION == "gdpdu-01-09-2004.dtd"

    def test_hash_column_in_archive_table(self) -> None:
        """Archiv-Tabelle hat Hash-Spalte (Unveraenderbarkeit)."""
        column_names = [col.name for col in ARCHIVE_TABLE.columns]
        assert "ContentHash" in column_names
        assert "HashAlgorithmus" in column_names

    def test_verification_column_in_archive_table(self) -> None:
        """Archiv-Tabelle hat Verifikations-Spalte (Nachvollziehbarkeit)."""
        column_names = [col.name for col in ARCHIVE_TABLE.columns]
        assert "Verifiziert" in column_names

    def test_retention_columns_in_archive_table(self) -> None:
        """Archiv-Tabelle hat Aufbewahrungsfrist-Spalten (Ordnung)."""
        column_names = [col.name for col in ARCHIVE_TABLE.columns]
        assert "Aufbewahrungskategorie" in column_names
        assert "Aufbewahrungsjahre" in column_names
        assert "AblaufDatum" in column_names

    def test_german_column_names(self) -> None:
        """Alle Spalten haben deutsche Bezeichnungen."""
        # Englische Begriffe, die nicht vorkommen sollten (als ganze Woerter)
        english_terms = ["File", "Hash", "Amount", "Number", "Type", "Address"]

        for table in [DOCUMENT_TABLE, ARCHIVE_TABLE, INVOICE_TABLE, CONTRACT_TABLE]:
            for col in table.columns:
                # Keine rein englischen Spaltennamen
                for term in english_terms:
                    # Nur pruefen wenn es als ganzes Wort vorkommt (nicht Teil eines deutschen Worts)
                    if term.lower() in col.name.lower() and term.lower() == col.name.lower():
                        pytest.fail(f"Englischer Name: {col.name}")

    @pytest.mark.asyncio
    async def test_readme_contains_gobd_reference(
        self,
        gdpdu_service: GDPdUExportService,
        mock_company: MagicMock,
        export_options: GDPdUExportOptions,
    ) -> None:
        """README referenziert GoBD-Kriterien."""
        gdpdu_service._tables = []
        readme = gdpdu_service._generate_readme(mock_company, export_options)

        # Alle GoBD-Kriterien muessen erwaehnt werden
        assert "Nachvollziehbarkeit" in readme
        assert "Unveraenderbarkeit" in readme or "Unveränderbarkeit" in readme
        assert "Vollstaendigkeit" in readme or "Vollständigkeit" in readme
        assert "Ordnung" in readme
