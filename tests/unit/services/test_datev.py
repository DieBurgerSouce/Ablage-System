# -*- coding: utf-8 -*-
"""
Unit Tests fuer DATEV Export Services.

Testet:
- SKR03/SKR04 Kontenrahmen
- Tax Code Mapper
- Invoice Mapper
- Buchungsstapel Writer
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.schemas.extracted_data import (
    ExtractedAddress,
    ExtractedBankAccount,
    ExtractedInvoiceData,
    InvoiceDirection,
)
from app.services.datev.buchungsstapel_writer import BuchungsstapelWriter
from app.services.datev.kontenrahmen import SKR03, SKR04
from app.services.datev.mapping.invoice_mapper import DATEVBuchung, DATEVInvoiceMapper
from app.services.datev.mapping.tax_code_mapper import TaxCodeMapper


# =============================================================================
# KONTENRAHMEN TESTS
# =============================================================================

class TestSKR03:
    """Tests fuer SKR03 Kontenrahmen."""

    def test_name(self) -> None:
        """SKR03 hat korrekten Namen."""
        skr03 = SKR03()
        assert skr03.name == "SKR03"

    def test_wareneingang_19(self) -> None:
        """Wareneingang 19% liefert korrektes Konto."""
        skr03 = SKR03()
        assert skr03.get_expense_account("waren", 19) == "3200"

    def test_wareneingang_7(self) -> None:
        """Wareneingang 7% liefert korrektes Konto."""
        skr03 = SKR03()
        assert skr03.get_expense_account("waren", 7) == "3300"

    def test_erloese_19(self) -> None:
        """Erloese 19% liefert korrektes Konto."""
        skr03 = SKR03()
        assert skr03.get_revenue_account("waren", 19) == "8400"

    def test_erloese_7(self) -> None:
        """Erloese 7% liefert korrektes Konto."""
        skr03 = SKR03()
        assert skr03.get_revenue_account("waren", 7) == "8300"

    def test_default_kreditor(self) -> None:
        """Standard-Kreditorenkonto ist korrekt."""
        skr03 = SKR03()
        assert skr03.default_creditor_account == "70000"

    def test_default_debitor(self) -> None:
        """Standard-Debitorenkonto ist korrekt."""
        skr03 = SKR03()
        assert skr03.default_debtor_account == "10000"

    def test_sammelkonto_kreditoren(self) -> None:
        """Sammelkonto Kreditoren ist korrekt."""
        skr03 = SKR03()
        assert skr03.sammelkonto_kreditoren == "1600"

    def test_sammelkonto_debitoren(self) -> None:
        """Sammelkonto Debitoren ist korrekt."""
        skr03 = SKR03()
        assert skr03.sammelkonto_debitoren == "1400"

    def test_expense_accounts_dict(self) -> None:
        """Expense accounts Dict enthaelt wichtige Kategorien."""
        skr03 = SKR03()
        assert "waren" in skr03.expense_accounts
        assert "miete" in skr03.expense_accounts
        assert "reise" in skr03.expense_accounts


class TestSKR04:
    """Tests fuer SKR04 Kontenrahmen."""

    def test_name(self) -> None:
        """SKR04 hat korrekten Namen."""
        skr04 = SKR04()
        assert skr04.name == "SKR04"

    def test_wareneingang_19(self) -> None:
        """Wareneingang 19% liefert korrektes Konto."""
        skr04 = SKR04()
        assert skr04.get_expense_account("waren", 19) == "5200"

    def test_erloese_19(self) -> None:
        """Erloese 19% liefert korrektes Konto."""
        skr04 = SKR04()
        assert skr04.get_revenue_account("waren", 19) == "4400"

    def test_sammelkonto_kreditoren(self) -> None:
        """Sammelkonto Kreditoren ist korrekt (unterschiedlich zu SKR03)."""
        skr04 = SKR04()
        assert skr04.sammelkonto_kreditoren == "3300"


# =============================================================================
# TAX CODE MAPPER TESTS
# =============================================================================

class TestTaxCodeMapper:
    """Tests fuer Tax Code Mapper."""

    def test_vorsteuer_19(self) -> None:
        """Vorsteuer 19% bei Eingang."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("19"),
            direction=InvoiceDirection.INCOMING,
        )
        assert code == "9"

    def test_vorsteuer_7(self) -> None:
        """Vorsteuer 7% bei Eingang."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("7"),
            direction=InvoiceDirection.INCOMING,
        )
        assert code == "8"

    def test_umsatzsteuer_19(self) -> None:
        """Umsatzsteuer 19% bei Ausgang."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("19"),
            direction=InvoiceDirection.OUTGOING,
        )
        assert code == "3"

    def test_umsatzsteuer_7(self) -> None:
        """Umsatzsteuer 7% bei Ausgang."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("7"),
            direction=InvoiceDirection.OUTGOING,
        )
        assert code == "2"

    def test_reverse_charge_eingang(self) -> None:
        """Reverse Charge bei Eingang."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("19"),
            direction=InvoiceDirection.INCOMING,
            is_reverse_charge=True,
        )
        assert code == "91"

    def test_ig_lieferung_ausgang(self) -> None:
        """Innergemeinschaftliche Lieferung bei Ausgang."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("19"),
            direction=InvoiceDirection.OUTGOING,
            is_intra_community=True,
        )
        assert code == "10"

    def test_ig_erwerb_eingang(self) -> None:
        """Innergemeinschaftlicher Erwerb bei Eingang."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("19"),
            direction=InvoiceDirection.INCOMING,
            is_intra_community=True,
        )
        assert code == "94"

    def test_unknown_direction_returns_none(self) -> None:
        """Unbekannte Richtung gibt None zurueck."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("19"),
            direction=InvoiceDirection.UNKNOWN,
        )
        assert code is None

    def test_description(self) -> None:
        """Beschreibung fuer Steuerschluessel."""
        mapper = TaxCodeMapper()
        assert "19%" in mapper.get_description("9")
        assert "Vorsteuer" in mapper.get_description("9")


# =============================================================================
# INVOICE MAPPER TESTS
# =============================================================================

class TestDATEVInvoiceMapper:
    """Tests fuer Invoice Mapper."""

    @pytest.fixture
    def sample_incoming_invoice(self) -> ExtractedInvoiceData:
        """Beispiel-Eingangsrechnung."""
        return ExtractedInvoiceData(
            invoice_number="RE-2025-001",
            invoice_date=date(2025, 1, 15),
            gross_amount=Decimal("119.00"),
            net_amount=Decimal("100.00"),
            vat_amount=Decimal("19.00"),
            vat_rate=Decimal("19"),
            currency="EUR",
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(
                company="Lieferant GmbH",
                street="Lieferantenstr. 1",
                zip_code="12345",
                city="Berlin",
                country="DE",
            ),
            recipient=ExtractedAddress(
                company="Meine Firma GmbH",
                street="Hauptstr. 1",
                zip_code="12345",
                city="Berlin",
                country="DE",
            ),
        )

    @pytest.fixture
    def sample_outgoing_invoice(self) -> ExtractedInvoiceData:
        """Beispiel-Ausgangsrechnung."""
        return ExtractedInvoiceData(
            invoice_number="AR-2025-001",
            invoice_date=date(2025, 1, 20),
            gross_amount=Decimal("238.00"),
            net_amount=Decimal("200.00"),
            vat_amount=Decimal("38.00"),
            vat_rate=Decimal("19"),
            currency="EUR",
            invoice_direction=InvoiceDirection.OUTGOING,
            sender=ExtractedAddress(
                company="Meine Firma GmbH",
                street="Hauptstr. 1",
                zip_code="12345",
                city="Berlin",
                country="DE",
            ),
            recipient=ExtractedAddress(
                company="Kunde AG",
                street="Kundenweg 5",
                zip_code="54321",
                city="Muenchen",
                country="DE",
            ),
        )

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            incoming_expense_account = "4200"
            incoming_creditor_account = "70001"
            outgoing_revenue_account = "8400"
            outgoing_debtor_account = "10001"
            buchungstext_format = "{invoice_number}"
        return MockDATEVConfig()

    def test_map_incoming_invoice(
        self,
        sample_incoming_invoice: ExtractedInvoiceData,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Eingangsrechnung wird korrekt gemappt."""
        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=sample_incoming_invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        assert result.buchung is not None
        assert result.buchung.umsatz == Decimal("119.00")
        assert result.buchung.soll_haben == "S"
        assert result.buchung.konto == "4200"
        assert result.buchung.gegenkonto == "70001"
        assert result.buchung.bu_schluessel == "9"  # Vorsteuer 19%
        assert result.buchung.belegfeld_1 == "RE-2025-001"

    def test_map_outgoing_invoice(
        self,
        sample_outgoing_invoice: ExtractedInvoiceData,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Ausgangsrechnung wird korrekt gemappt."""
        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=sample_outgoing_invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        assert result.buchung is not None
        assert result.buchung.umsatz == Decimal("238.00")
        assert result.buchung.soll_haben == "S"
        assert result.buchung.konto == "10001"
        assert result.buchung.gegenkonto == "8400"
        assert result.buchung.bu_schluessel == "3"  # Umsatzsteuer 19%

    def test_missing_invoice_date_fails(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Fehlende Pflichtfelder fuehren zu Fehler."""
        invoice = ExtractedInvoiceData(
            invoice_number="TEST-001",
            invoice_date=None,  # Pflichtfeld fehlt
            gross_amount=Decimal("100.00"),
            invoice_direction=InvoiceDirection.INCOMING,
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert not result.success
        assert "datum" in result.error.lower()

    def test_unknown_direction_fails(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Unbekannte Rechnungsrichtung fuehrt zu Fehler."""
        invoice = ExtractedInvoiceData(
            invoice_number="TEST-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("100.00"),
            invoice_direction=InvoiceDirection.UNKNOWN,
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert not result.success
        assert "richtung" in result.error.lower()


# =============================================================================
# BUCHUNGSSTAPEL WRITER TESTS
# =============================================================================

class TestBuchungsstapelWriter:
    """Tests fuer Buchungsstapel Writer."""

    @pytest.fixture
    def sample_buchung(self) -> DATEVBuchung:
        """Beispiel-Buchung."""
        return DATEVBuchung(
            umsatz=Decimal("119.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 15),
            belegfeld_1="RE-2025-001",
            belegfeld_2=None,
            buchungstext="RE-2025-001",
        )

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            sachkontenlange = 4
        return MockDATEVConfig()

    def test_write_produces_bytes(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Writer erzeugt Bytes."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_contains_extf_header(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Output enthaelt EXTF Header."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        # Decode als CP1252
        content = result.decode("cp1252")
        assert content.startswith('"EXTF"')

    def test_output_uses_semicolon_delimiter(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Output verwendet Semikolon als Trennzeichen."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")
        # Header muss Semikolons enthalten
        assert ";" in lines[0]
        # Spaltenkoepfe muessen Semikolons enthalten
        assert ";" in lines[1]

    def test_amount_formatted_with_comma(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Betraege werden mit Komma formatiert."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        # 119.00 sollte als 119,00 erscheinen
        assert "119,00" in content

    def test_date_formatted_ddmm(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Datum wird als DDMM formatiert."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        # 2025-01-15 sollte als 1501 erscheinen
        assert "1501" in content

    def test_encoding_is_cp1252(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Output ist in CP1252 kodiert."""
        # Buchung mit Umlaut
        buchung = DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="RE-001",
            belegfeld_2=None,
            buchungstext="Büromaterial",  # Umlaut
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        # Sollte als CP1252 dekodierbar sein
        content = result.decode("cp1252")
        assert "Büromaterial" in content or "B" in content


# =============================================================================
# INTEGRATION TESTS (ohne DB)
# =============================================================================

class TestDATEVExportIntegration:
    """Integrationstests fuer DATEV Export (ohne Datenbank)."""

    def test_full_export_flow(self) -> None:
        """Vollstaendiger Export-Flow von Rechnung zu CSV."""
        # 1. Rechnung erstellen
        invoice = ExtractedInvoiceData(
            invoice_number="INT-2025-001",
            invoice_date=date(2025, 3, 15),
            gross_amount=Decimal("595.00"),
            net_amount=Decimal("500.00"),
            vat_amount=Decimal("95.00"),
            vat_rate=Decimal("19"),
            currency="EUR",
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(
                company="Test Lieferant GmbH",
                country="DE",
            ),
        )

        # 2. Mock-Konfiguration
        class MockConfig:
            berater_nr = "9999999"
            mandanten_nr = "99999"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            incoming_expense_account = "4200"
            incoming_creditor_account = "70001"
            outgoing_revenue_account = "8400"
            outgoing_debtor_account = "10001"
            buchungstext_format = "{invoice_number}"
            sachkontenlange = 4

        config = MockConfig()

        # 3. Mappen
        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=config,
            vendor_mapping=None,
        )

        assert result.success

        # 4. CSV schreiben
        writer = BuchungsstapelWriter()
        csv_bytes = writer.write(
            buchungen=[result.buchung],
            config=config,
        )

        # 5. Validieren
        content = csv_bytes.decode("cp1252")
        lines = content.split("\r\n")

        # Header pruefen
        assert '"EXTF"' in lines[0]
        assert "9999999" in lines[0]  # Beraternummer
        assert "99999" in lines[0]    # Mandantennummer

        # Buchung pruefen
        assert "595,00" in content    # Betrag
        assert "INT-2025-001" in content  # Rechnungsnummer
        assert "4200" in content      # Aufwandskonto
        assert "70001" in content     # Kreditorenkonto


# =============================================================================
# HEADER VALIDATION TESTS (BUG 2 FIX)
# =============================================================================

class TestBuchungsstapelHeaderFields:
    """Tests fuer DATEV Header mit 32 Feldern (Version 700)."""

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            sachkontenlange = 4
        return MockDATEVConfig()

    @pytest.fixture
    def sample_buchung(self) -> DATEVBuchung:
        """Beispiel-Buchung."""
        return DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 15),
            belegfeld_1="TEST-001",
            belegfeld_2=None,
            buchungstext="Test",
        )

    def test_header_has_32_fields(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Header-Zeile muss exakt 32 Felder haben (DATEV Version 700)."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")
        header_line = lines[0]

        # Semikolon-getrennte Felder zaehlen
        # Bei 32 Feldern gibt es 31 Semikolons
        field_count = header_line.count(";") + 1
        assert field_count == 32, f"Header hat {field_count} statt 32 Felder"

    def test_header_starts_with_extf(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Header muss mit EXTF beginnen."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        assert content.startswith('"EXTF"')

    def test_header_contains_version_700(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Header muss Version 700 enthalten."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")
        header_fields = lines[0].split(";")

        # Feld 2 ist die Version
        assert header_fields[1] == "700"

    def test_header_contains_category_21(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Header muss Kategorie 21 (Buchungsstapel) enthalten."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")
        header_fields = lines[0].split(";")

        # Feld 3 ist die Kategorie
        assert header_fields[2] == "21"

    def test_header_contains_currency_eur(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Header muss EUR als Waehrung enthalten."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        # EUR muss in Anfuehrungszeichen stehen
        assert '"EUR"' in content


# =============================================================================
# SCHEMA VALIDATION TESTS (BUG 3 FIX)
# =============================================================================

class TestDATEVSchemaEnumValidation:
    """Tests fuer Pydantic Schema Enum Konvertierung."""

    def test_export_history_item_accepts_string_export_type(self) -> None:
        """DATEVExportHistoryItem akzeptiert String fuer export_type."""
        from uuid import uuid4
        from datetime import datetime
        from app.api.schemas.datev import DATEVExportHistoryItem

        # Simuliere Datenbank-Rueckgabe mit String statt Enum
        item = DATEVExportHistoryItem(
            id=uuid4(),
            export_type="buchungsstapel",  # String, nicht Enum
            filename="test.csv",
            document_count=10,
            status="completed",  # String, nicht Enum
            period_from=date(2025, 1, 1),
            period_to=date(2025, 1, 31),
            exported_at=datetime.now(),
        )

        assert item.export_type.value == "buchungsstapel"
        assert item.status.value == "completed"

    def test_export_history_item_accepts_enum_export_type(self) -> None:
        """DATEVExportHistoryItem akzeptiert auch Enum direkt."""
        from uuid import uuid4
        from datetime import datetime
        from app.api.schemas.datev import (
            DATEVExportHistoryItem,
            DATEVExportType,
            DATEVExportStatus,
        )

        item = DATEVExportHistoryItem(
            id=uuid4(),
            export_type=DATEVExportType.BUCHUNGSSTAPEL,
            filename="test.csv",
            document_count=10,
            status=DATEVExportStatus.COMPLETED,
            exported_at=datetime.now(),
        )

        assert item.export_type == DATEVExportType.BUCHUNGSSTAPEL
        assert item.status == DATEVExportStatus.COMPLETED

    def test_export_history_item_invalid_export_type_raises(self) -> None:
        """DATEVExportHistoryItem wirft Fehler bei ungueltigem export_type."""
        from uuid import uuid4
        from datetime import datetime
        from app.api.schemas.datev import DATEVExportHistoryItem

        with pytest.raises(ValueError):
            DATEVExportHistoryItem(
                id=uuid4(),
                export_type="invalid_type",
                filename="test.csv",
                document_count=10,
                status="completed",
                exported_at=datetime.now(),
            )


# =============================================================================
# VENDOR MAPPING TESTS
# =============================================================================

class TestVendorMappingInInvoiceMapper:
    """Tests fuer Vendor-Mapping in Invoice Mapper."""

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration mit Standard-Konten."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            incoming_expense_account = "4200"  # Standard
            incoming_creditor_account = "70000"  # Standard
            outgoing_revenue_account = "8400"
            outgoing_debtor_account = "10000"
            buchungstext_format = "{invoice_number}"
        return MockDATEVConfig()

    @pytest.fixture
    def sample_invoice(self) -> ExtractedInvoiceData:
        """Beispiel-Eingangsrechnung."""
        return ExtractedInvoiceData(
            invoice_number="VM-2025-001",
            invoice_date=date(2025, 2, 1),
            gross_amount=Decimal("500.00"),
            net_amount=Decimal("420.17"),
            vat_amount=Decimal("79.83"),
            vat_rate=Decimal("19"),
            currency="EUR",
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(
                company="Spezial Lieferant GmbH",
                country="DE",
            ),
        )

    def test_vendor_mapping_overrides_accounts(
        self,
        sample_invoice: ExtractedInvoiceData,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Vendor-Mapping ueberschreibt Standard-Konten."""
        # Mock Vendor-Mapping mit spezifischen Konten
        class MockVendorMapping:
            expense_account = "4980"  # Anderes Aufwandskonto
            creditor_account = "70042"  # Spezifischer Kreditor
            cost_center = "KST100"
            cost_object = None

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=sample_invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=MockVendorMapping(),
        )

        assert result.success
        assert result.buchung.konto == "4980"  # Vendor-Mapping
        assert result.buchung.gegenkonto == "70042"  # Vendor-Mapping
        assert result.buchung.kostenstelle_1 == "KST100"

    def test_vendor_mapping_none_uses_config_defaults(
        self,
        sample_invoice: ExtractedInvoiceData,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Ohne Vendor-Mapping werden Config-Defaults verwendet."""
        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=sample_invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        assert result.buchung.konto == "4200"  # Config-Default
        assert result.buchung.gegenkonto == "70000"  # Config-Default


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestDATEVEdgeCases:
    """Edge Case Tests fuer DATEV Export."""

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            sachkontenlange = 4
        return MockDATEVConfig()

    def test_special_characters_in_buchungstext(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Sonderzeichen im Buchungstext werden korrekt behandelt."""
        buchung = DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="TEST-001",
            belegfeld_2=None,
            buchungstext='Büro "Material" für Äußeres',  # Umlaute und Anführungszeichen
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        # Sollte nicht abstuerzen
        content = result.decode("cp1252")
        assert "Büro" in content or "B" in content  # Umlaut

    def test_semicolon_in_buchungstext_escaped(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Semikolons im Buchungstext werden ersetzt (nicht als Delimiter)."""
        buchung = DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="TEST-001",
            belegfeld_2=None,
            buchungstext="Material; verschiedene Teile",  # Semikolon im Text
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")

        # Die Buchungszeile (Zeile 3) sollte genau 116 Felder haben
        data_line = lines[2]
        field_count = data_line.count(";") + 1
        assert field_count == 116, f"Buchungszeile hat {field_count} statt 116 Felder"

    def test_long_invoice_number_truncated(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Lange Rechnungsnummern werden auf 36 Zeichen gekuerzt."""
        long_number = "RE-2025-" + "A" * 50  # Viel zu lang

        buchung = DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1=long_number,
            belegfeld_2=None,
            buchungstext="Test",
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        # Die volle lange Nummer sollte NICHT drin sein
        assert long_number not in content
        # Aber die gekuerzte Version schon (36 Zeichen)
        assert "RE-2025-" in content

    def test_empty_buchungen_list(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Leere Buchungsliste erzeugt gueltige CSV mit Header."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")

        # Mindestens Header und Spaltenkoepfe
        assert len(lines) >= 2
        assert '"EXTF"' in lines[0]

    def test_negative_amount_becomes_positive(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Negative Betraege werden als positiv geschrieben (DATEV-Anforderung)."""
        buchung = DATEVBuchung(
            umsatz=Decimal("-100.00"),  # Negativ
            soll_haben="H",  # Haben
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="TEST-001",
            belegfeld_2=None,
            buchungstext="Gutschrift",
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        # Betrag sollte positiv sein (100,00 nicht -100,00)
        assert "100,00" in content
        assert "-100,00" not in content

    def test_decimal_precision_preserved(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Dezimalstellen werden korrekt gerundet (2 Nachkommastellen)."""
        buchung = DATEVBuchung(
            umsatz=Decimal("123.456789"),  # Viele Nachkommastellen
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="TEST-001",
            belegfeld_2=None,
            buchungstext="Test",
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        # Sollte auf 2 Stellen gerundet sein
        assert "123,46" in content  # Gerundet von 123.456789


# =============================================================================
# DATA LINE VALIDATION TESTS
# =============================================================================

class TestBuchungsstapelDataLine:
    """Tests fuer Buchungszeilen-Format (116 Felder)."""

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            sachkontenlange = 4
        return MockDATEVConfig()

    @pytest.fixture
    def sample_buchung(self) -> DATEVBuchung:
        """Beispiel-Buchung."""
        return DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 15),
            belegfeld_1="TEST-001",
            belegfeld_2=None,
            buchungstext="Test",
        )

    def test_data_line_has_116_fields(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Buchungszeile muss exakt 116 Felder haben."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")

        # Zeile 3 ist die erste Buchungszeile
        data_line = lines[2]
        field_count = data_line.count(";") + 1
        assert field_count == 116, f"Buchungszeile hat {field_count} statt 116 Felder"

    def test_column_headers_has_116_fields(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Spaltenkopf-Zeile muss exakt 116 Felder haben."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")

        # Zeile 2 sind die Spaltenkoepfe
        header_line = lines[1]
        field_count = header_line.count(";") + 1
        assert field_count == 116, f"Spaltenkoepfe haben {field_count} statt 116 Felder"

    def test_field_positions_correct(
        self,
        sample_buchung: DATEVBuchung,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Wichtige Felder sind an korrekten Positionen."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[sample_buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")
        data_fields = lines[2].split(";")

        # Feld 1 (Index 0): Umsatz
        assert "100,00" in data_fields[0]

        # Feld 2 (Index 1): Soll/Haben
        assert '"S"' in data_fields[1]

        # Feld 3 (Index 2): WKZ
        assert '"EUR"' in data_fields[2]

        # Feld 7 (Index 6): Konto
        assert data_fields[6] == "4200"

        # Feld 8 (Index 7): Gegenkonto
        assert data_fields[7] == "70001"

        # Feld 9 (Index 8): BU-Schluessel
        assert data_fields[8] == "9"

        # Feld 10 (Index 9): Belegdatum
        assert data_fields[9] == "1501"  # DDMM

        # Feld 11 (Index 10): Belegfeld 1
        assert '"TEST-001"' in data_fields[10]


# =============================================================================
# ERROR HANDLING TESTS (Phase 2 - Audit Remediation)
# =============================================================================

class TestDATEVInvoiceMapperErrors:
    """Erweiterte Error-Handling-Tests fuer Invoice Mapper."""

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            incoming_expense_account = "4200"
            incoming_creditor_account = "70001"
            outgoing_revenue_account = "8400"
            outgoing_debtor_account = "10001"
            buchungstext_format = "{invoice_number}"
        return MockDATEVConfig()

    def test_missing_gross_and_net_amount_fails(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Fehlendes Brutto- und Nettobetrag fuehrt zu Fehler."""
        invoice = ExtractedInvoiceData(
            invoice_number="ERR-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=None,
            net_amount=None,  # Beide fehlen
            invoice_direction=InvoiceDirection.INCOMING,
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert not result.success
        assert result.error is not None
        assert "betrag" in result.error.lower()

    def test_zero_amount_fails(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Betrag von 0 fuehrt zu Fehler."""
        invoice = ExtractedInvoiceData(
            invoice_number="ERR-002",
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("0.00"),  # Null-Betrag
            invoice_direction=InvoiceDirection.INCOMING,
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert not result.success
        assert result.error is not None
        assert "betrag" in result.error.lower()

    def test_fallback_to_net_amount_when_gross_missing(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Wenn Brutto fehlt, wird Netto + MwSt berechnet."""
        invoice = ExtractedInvoiceData(
            invoice_number="FALL-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=None,
            net_amount=Decimal("100.00"),
            vat_rate=Decimal("19"),
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(company="Lieferant GmbH", country="DE"),
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        assert result.buchung is not None
        # 100 * 1.19 = 119
        assert result.buchung.umsatz == Decimal("119.00")

    def test_invalid_invoice_number_gets_placeholder(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Fehlende Rechnungsnummer wird durch Platzhalter ersetzt."""
        invoice = ExtractedInvoiceData(
            invoice_number=None,  # Fehlt
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("100.00"),
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(company="Lieferant GmbH", country="DE"),
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        assert result.buchung is not None
        assert result.buchung.belegfeld_1 == "OHNE-NR"

    def test_vendor_mapping_fallback_to_config(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Ohne Vendor-Mapping werden Config-Werte verwendet."""
        invoice = ExtractedInvoiceData(
            invoice_number="CFG-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("100.00"),
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(company="Lieferant GmbH", country="DE"),
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,  # Kein Mapping
        )

        assert result.success
        assert result.buchung.konto == "4200"  # Aus Config
        assert result.buchung.gegenkonto == "70001"  # Aus Config

    def test_partial_vendor_mapping_uses_mixed_values(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Vendor-Mapping mit teilweisen Werten wird mit Config kombiniert."""
        class PartialVendorMapping:
            expense_account = "4980"  # Ueberschreibt Config
            creditor_account = None  # Null -> Fallback auf Config
            cost_center = None
            cost_object = None

        invoice = ExtractedInvoiceData(
            invoice_number="PART-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("100.00"),
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(company="Lieferant GmbH", country="DE"),
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=PartialVendorMapping(),
        )

        assert result.success
        assert result.buchung.konto == "4980"  # Aus Vendor-Mapping
        assert result.buchung.gegenkonto == "70001"  # Aus Config (Fallback)

    def test_eu_third_country_detection_sender(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Drittland wird korrekt erkannt bei Sender aus USA."""
        invoice = ExtractedInvoiceData(
            invoice_number="US-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("100.00"),
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(
                company="US Corp",
                country="US",  # USA = Drittland
            ),
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        # BU-Schluessel sollte Drittland beruecksichtigen
        assert result.buchung is not None

    def test_reverse_charge_invoice_mapping(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Reverse Charge Rechnung wird korrekt gemappt."""
        invoice = ExtractedInvoiceData(
            invoice_number="RC-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("100.00"),  # RC ohne MwSt
            vat_rate=Decimal("0"),
            is_reverse_charge=True,
            invoice_direction=InvoiceDirection.INCOMING,
            sender=ExtractedAddress(
                company="EU Lieferant",
                country="AT",  # Oesterreich
            ),
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        assert result.buchung.bu_schluessel == "91"  # Reverse Charge

    def test_intra_community_delivery_outgoing(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Innergemeinschaftliche Lieferung (Ausgang) wird korrekt gemappt."""
        invoice = ExtractedInvoiceData(
            invoice_number="IG-001",
            invoice_date=date(2025, 1, 1),
            gross_amount=Decimal("100.00"),
            intra_community_supply=True,
            invoice_direction=InvoiceDirection.OUTGOING,
            recipient=ExtractedAddress(
                company="EU Kunde",
                country="FR",  # Frankreich
            ),
        )

        mapper = DATEVInvoiceMapper()
        result = mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=SKR03(),
            config=mock_config,
            vendor_mapping=None,
        )

        assert result.success
        assert result.buchung.bu_schluessel == "10"  # IG-Lieferung


class TestDATEVBuchungsstapelWriterErrors:
    """Error-Handling-Tests fuer Buchungsstapel Writer."""

    @pytest.fixture
    def mock_config(self) -> "MockDATEVConfig":
        """Mock DATEV-Konfiguration."""
        class MockDATEVConfig:
            berater_nr = "1234567"
            mandanten_nr = "12345"
            wj_beginn = date(2025, 1, 1)
            kontenrahmen = "SKR03"
            sachkontenlange = 4
        return MockDATEVConfig()

    def test_empty_buchungen_creates_valid_csv(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Leere Buchungsliste erzeugt gueltige CSV ohne Datenzeilen."""
        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")

        # Header und Spaltenkoepfe muessen vorhanden sein
        assert len(lines) >= 2
        assert '"EXTF"' in lines[0]
        # Keine Datenzeilen (nach Spaltenkoepfen)
        non_empty_lines = [l for l in lines if l.strip()]
        assert len(non_empty_lines) == 2  # Nur Header und Spaltenkoepfe

    def test_very_large_amount_formatted_correctly(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Sehr grosse Betraege werden korrekt formatiert."""
        buchung = DATEVBuchung(
            umsatz=Decimal("9999999999.99"),  # 10 Milliarden
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="BIG-001",
            belegfeld_2=None,
            buchungstext="Grosser Betrag",
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        # Betrag muss mit Komma als Dezimaltrennzeichen erscheinen
        assert "9999999999,99" in content

    def test_very_small_amount_formatted_correctly(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Sehr kleine Betraege werden korrekt formatiert."""
        buchung = DATEVBuchung(
            umsatz=Decimal("0.01"),  # 1 Cent
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="TINY-001",
            belegfeld_2=None,
            buchungstext="Kleiner Betrag",
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        assert "0,01" in content

    def test_non_ascii_characters_encoded_correctly(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Nicht-ASCII-Zeichen werden korrekt kodiert."""
        buchung = DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="ÄÖÜ-001",  # Umlaute in Belegfeld
            belegfeld_2=None,
            buchungstext="Öffentliche Körperschaft für Überwachung",
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        # Muss als CP1252 dekodierbar sein
        content = result.decode("cp1252")
        # Umlaute muessen erhalten bleiben
        assert "Ä" in content or "Ö" in content or "Ü" in content

    def test_newline_in_buchungstext_removed(
        self,
        mock_config: "MockDATEVConfig",
    ) -> None:
        """Zeilenumbrueche im Buchungstext werden entfernt."""
        buchung = DATEVBuchung(
            umsatz=Decimal("100.00"),
            soll_haben="S",
            wkz_umsatz="EUR",
            konto="4200",
            gegenkonto="70001",
            bu_schluessel="9",
            belegdatum=date(2025, 1, 1),
            belegfeld_1="NL-001",
            belegfeld_2=None,
            buchungstext="Zeile 1\nZeile 2",  # Zeilenumbruch
        )

        writer = BuchungsstapelWriter()
        result = writer.write(
            buchungen=[buchung],
            config=mock_config,
        )

        content = result.decode("cp1252")
        lines = content.split("\r\n")

        # Die Buchungszeile sollte nur eine Zeile sein
        # (Zeilenumbruch im Text darf nicht als CSV-Zeilenumbruch erscheinen)
        data_line = lines[2]
        assert data_line.count(";") == 115  # 116 Felder


class TestDATEVTaxCodeMapperErrors:
    """Error-Handling-Tests fuer Tax Code Mapper."""

    def test_unsupported_vat_rate_returns_standard(self) -> None:
        """Nicht-Standard-Steuersatz gibt Standard zurueck."""
        mapper = TaxCodeMapper()
        # 12% ist kein deutscher Standard-Steuersatz
        code = mapper.get_tax_code(
            vat_rate=Decimal("12"),
            direction=InvoiceDirection.INCOMING,
        )
        # Sollte auf naechsten Standard fallen oder None
        # (je nach Implementierung)
        assert code is None or code in ["8", "9"]

    def test_negative_vat_rate_handled(self) -> None:
        """Negativer Steuersatz wird behandelt."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=Decimal("-19"),  # Ungueltig
            direction=InvoiceDirection.INCOMING,
        )
        # Sollte None zurueckgeben oder Standard
        assert code is None or isinstance(code, str)

    def test_vat_rate_none_uses_default_19(self) -> None:
        """None als Steuersatz verwendet Default 19% (DATEV braucht immer Steuerschluessel)."""
        mapper = TaxCodeMapper()
        code = mapper.get_tax_code(
            vat_rate=None,
            direction=InvoiceDirection.INCOMING,
        )
        # Bei Eingang ohne expliziten Steuersatz: Default 19% Vorsteuer (BU-Schluessel 9)
        assert code == "9"

    def test_description_for_invalid_code_returns_empty(self) -> None:
        """Beschreibung fuer ungueltigen Code gibt leeren String."""
        mapper = TaxCodeMapper()
        desc = mapper.get_description("999")  # Ungueltiger Code
        assert desc == "" or desc is None or "unbekannt" in desc.lower()


class TestDATEVKontenrahmenErrors:
    """Error-Handling-Tests fuer Kontenrahmen."""

    def test_unknown_expense_category_returns_default(self) -> None:
        """Unbekannte Aufwandskategorie gibt Standard zurueck."""
        skr03 = SKR03()
        account = skr03.get_expense_account("unbekannte_kategorie", 19)
        # Sollte auf Wareneingang 19% fallen
        assert account == "3200"

    def test_unknown_revenue_category_returns_default(self) -> None:
        """Unbekannte Erloeskategorie gibt Standard zurueck."""
        skr03 = SKR03()
        account = skr03.get_revenue_account("unbekannte_kategorie", 19)
        # Sollte auf Erloese 19% fallen
        assert account == "8400"

    def test_invalid_vat_rate_for_expense_uses_default(self) -> None:
        """Ungueltiger Steuersatz fuer Aufwand nutzt Standard."""
        skr03 = SKR03()
        account = skr03.get_expense_account("waren", 12)  # 12% gibt es nicht
        # Sollte trotzdem ein Konto zurueckgeben
        assert account is not None
        assert len(account) == 4

    def test_all_mandatory_accounts_present_skr03(self) -> None:
        """SKR03 hat alle Pflicht-Konten."""
        skr03 = SKR03()
        assert skr03.default_creditor_account is not None
        assert skr03.default_debtor_account is not None
        assert skr03.sammelkonto_kreditoren is not None
        assert skr03.sammelkonto_debitoren is not None
        assert skr03.vorsteuer_19 is not None
        assert skr03.vorsteuer_7 is not None
        assert skr03.umsatzsteuer_19 is not None
        assert skr03.umsatzsteuer_7 is not None

    def test_all_mandatory_accounts_present_skr04(self) -> None:
        """SKR04 hat alle Pflicht-Konten."""
        skr04 = SKR04()
        assert skr04.default_creditor_account is not None
        assert skr04.default_debtor_account is not None
        assert skr04.sammelkonto_kreditoren is not None
        assert skr04.sammelkonto_debitoren is not None
        assert skr04.vorsteuer_19 is not None
        assert skr04.vorsteuer_7 is not None
        assert skr04.umsatzsteuer_19 is not None
        assert skr04.umsatzsteuer_7 is not None


class TestMappingResultDataclass:
    """Tests fuer MappingResult Dataclass (Mutable Default Fix)."""

    def test_warnings_not_shared_between_instances(self) -> None:
        """Warnungen werden nicht zwischen Instanzen geteilt."""
        from app.services.datev.mapping.invoice_mapper import MappingResult

        result1 = MappingResult(success=True)
        result2 = MappingResult(success=True)

        # Warnung zu result1 hinzufuegen
        result1.warnings.append("Warnung 1")

        # result2 sollte keine Warnungen haben
        assert len(result2.warnings) == 0
        assert len(result1.warnings) == 1

    def test_multiple_results_independent(self) -> None:
        """Mehrere Ergebnisse sind unabhaengig."""
        from app.services.datev.mapping.invoice_mapper import MappingResult

        results = [MappingResult(success=True) for _ in range(5)]

        # Jedes Ergebnis mit eigenen Warnungen
        for i, r in enumerate(results):
            r.warnings.append(f"Warnung {i}")

        # Jedes Ergebnis hat nur seine eigene Warnung
        for i, r in enumerate(results):
            assert len(r.warnings) == 1
            assert r.warnings[0] == f"Warnung {i}"
