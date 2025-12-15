"""
Tests fuer die OCR-Extraktions-Bugfixes vom 2025-12-15.

Testet:
- HTML/Markdown Tag Entfernung
- Neue Invoice-Number Patterns (RG, CD)
- Tabellen-Layout Erkennung
- Supplier-Leerzeichen Beibehaltung
"""
import pytest

from app.services.quick_classification_service import QuickClassificationService


class TestExtractionFixes:
    """Tests fuer die OCR-Extraktions-Bugfixes."""

    @pytest.fixture
    def service(self):
        """Erstellt eine QuickClassificationService Instanz."""
        return QuickClassificationService()

    # =========================================================================
    # HTML/Markdown Stripping Tests
    # =========================================================================

    def test_html_tags_removed(self, service):
        """Bug 4: HTML-Tags sollen entfernt werden."""
        text = "<b>AUER Packaging GmbH</b>\nAm Kroit 25/27"
        cleaned = service._preprocess_text_for_extraction(text)
        assert "<b>" not in cleaned
        assert "</b>" not in cleaned
        assert "AUER Packaging GmbH" in cleaned

    def test_html_div_tags_removed(self, service):
        """Verschiedene HTML-Tags werden entfernt."""
        text = "<div><p>Test GmbH</p></div>"
        cleaned = service._preprocess_text_for_extraction(text)
        assert "<div>" not in cleaned
        assert "<p>" not in cleaned
        assert "Test GmbH" in cleaned

    def test_markdown_bold_removed(self, service):
        """Markdown **bold** wird entfernt."""
        text = "**AUER Packaging GmbH**\nTest"
        cleaned = service._preprocess_text_for_extraction(text)
        assert "**" not in cleaned
        assert "AUER Packaging GmbH" in cleaned

    def test_markdown_italic_removed(self, service):
        """Markdown *italic* wird entfernt."""
        text = "*Wichtiger Text*\nNormal"
        cleaned = service._preprocess_text_for_extraction(text)
        assert cleaned.startswith("Wichtiger Text")

    def test_markdown_underscore_bold_removed(self, service):
        """Markdown __bold__ wird entfernt."""
        text = "__Fett__\nNormal"
        cleaned = service._preprocess_text_for_extraction(text)
        assert "__" not in cleaned
        assert "Fett" in cleaned

    def test_multiple_newlines_reduced(self, service):
        """Mehrfache Leerzeilen werden reduziert."""
        text = "Zeile1\n\n\n\n\nZeile2"
        cleaned = service._preprocess_text_for_extraction(text)
        assert "\n\n\n" not in cleaned
        assert "Zeile1" in cleaned
        assert "Zeile2" in cleaned

    def test_empty_text_handled(self, service):
        """Leerer Text wird korrekt behandelt."""
        assert service._preprocess_text_for_extraction("") == ""
        assert service._preprocess_text_for_extraction(None) == ""

    # =========================================================================
    # Invoice Number Pattern Tests
    # =========================================================================

    def test_asal_format_rg(self, service):
        """Bug 5: RG-Format (Asal) wird erkannt."""
        text = "RG20012108\nBearbeiter: Regina Asal"
        result = service._extract_invoice_number(text)
        assert result == "RG20012108"

    def test_amefa_format_cd(self, service):
        """Bug 2: CD-Format (Amefa) wird erkannt."""
        text = "Rechnungsnummer\nCD4921000467\n13.05.2020"
        result = service._extract_invoice_number(text)
        assert result == "CD4921000467"

    def test_abs_format_six_digits_before_date(self, service):
        """a.b.s. Format: 6-stellige Nummer vor Datum."""
        text = """
Rechnungs-Nr.
246543
25.05.22
"""
        result = service._extract_invoice_number(text)
        assert result == "246543"

    def test_alpac_format_still_works(self, service):
        """Regression: Alpac F-Format funktioniert weiterhin."""
        text = "Invoice No.: F-201401\nAlpac"
        result = service._extract_invoice_number(text)
        assert result == "F-201401"

    def test_re_format_still_works(self, service):
        """Regression: RE-Format funktioniert weiterhin."""
        text = "Rechnungsnummer: RE-2024-001234"
        result = service._extract_invoice_number(text)
        assert result == "RE-2024-001234"

    def test_standard_invoice_number_still_works(self, service):
        """Regression: Standard-Format funktioniert weiterhin."""
        text = "Rechnungs-Nr.: 12345678"
        result = service._extract_invoice_number(text)
        assert result == "12345678"

    # =========================================================================
    # Tabellen-Layout Tests
    # =========================================================================

    def test_table_layout_horizontal(self, service):
        """Bug 1: Horizontales Tabellen-Layout mit Labels/Werten in separaten Zeilen."""
        text = """
Rechnungs-Nr.  Kunden-Nr.  Rechnungsdatum
246543         310835      25.05.22
"""
        result = service._extract_invoice_number(text)
        assert result == "246543"

    def test_table_layout_vertical_labels(self, service):
        """Bug 1/2: Vertikales Layout mit Labels uebereinander."""
        text = """
Rechnungsnummer
Rechnungsdatum
Kunden Nr.
CD4921000467
13.05.2020
49200974
"""
        result = service._extract_invoice_number(text)
        # Sollte CD4921000467 durch das CD-Pattern finden
        assert result == "CD4921000467"

    def test_table_layout_fallback_only_when_needed(self, service):
        """Tabellen-Fallback wird nur verwendet wenn noetig."""
        # Normales Format sollte direkt matchen, nicht den Fallback benutzen
        text = "Rechnungsnummer: 123456"
        result = service._extract_invoice_number(text)
        assert result == "123456"

    # =========================================================================
    # Supplier Leerzeichen Tests
    # =========================================================================

    def test_supplier_keeps_spaces(self, service):
        """Bug 3: Supplier-Name behaelt Leerzeichen."""
        name = "Amefa Stahlwaren GmbH"
        result = service._normalize_for_filename(name)
        assert "Amefa" in result
        assert "Stahlwaren" in result
        assert " " in result  # Leerzeichen bleibt erhalten

    def test_supplier_multiple_spaces_normalized(self, service):
        """Mehrfache Leerzeichen werden auf eines reduziert."""
        name = "AUER   Packaging   GmbH"
        result = service._normalize_for_filename(name)
        assert "  " not in result  # Keine doppelten Leerzeichen
        assert "AUER" in result
        assert "Packaging" in result

    def test_supplier_legal_suffix_removed(self, service):
        """Rechtsformen werden weiterhin entfernt."""
        name = "Test Company GmbH"
        result = service._normalize_for_filename(name)
        assert "GmbH" not in result
        assert "Test Company" in result or "Test" in result

    def test_supplier_slogan_removed(self, service):
        """Slogans werden weiterhin entfernt."""
        name = "ALPAC - kunststof bakken BV"
        result = service._normalize_for_filename(name)
        assert "kunststof" not in result
        assert "ALPAC" in result

    # =========================================================================
    # Sanitize for Filename Tests
    # =========================================================================

    def test_sanitize_replaces_spaces_with_underscores(self, service):
        """_sanitize_for_filename ersetzt Leerzeichen durch Unterstriche."""
        name = "Amefa Stahlwaren GmbH"
        result = service._sanitize_for_filename(name)
        assert " " not in result
        assert "_" in result
        assert "Amefa_Stahlwaren" in result

    def test_sanitize_empty_string(self, service):
        """Leerer String wird korrekt behandelt."""
        result = service._sanitize_for_filename("")
        assert result == ""

    def test_sanitize_preserves_other_characters(self, service):
        """Andere gueltige Zeichen bleiben erhalten."""
        name = "Test-Company GmbH"
        result = service._sanitize_for_filename(name)
        assert "-" in result  # Bindestrich bleibt

    # =========================================================================
    # HTML in Invoice Number Extraction
    # =========================================================================

    def test_invoice_number_with_html_tags(self, service):
        """Invoice-Nummer wird auch bei HTML-Tags gefunden."""
        text = "<b>Rechnungsnummer:</b> 12345678"
        result = service._extract_invoice_number(text)
        assert result == "12345678"

    def test_invoice_number_with_markdown(self, service):
        """Invoice-Nummer wird auch bei Markdown gefunden."""
        text = "**Rechnungsnummer:** 12345678"
        result = service._extract_invoice_number(text)
        assert result == "12345678"

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_no_invoice_number_found(self, service):
        """Kein Ergebnis wenn keine Rechnungsnummer vorhanden."""
        text = "Dies ist ein Text ohne Rechnungsnummer."
        result = service._extract_invoice_number(text)
        assert result is None

    def test_very_short_text(self, service):
        """Kurzer Text wird korrekt behandelt."""
        text = "Hi"
        result = service._extract_invoice_number(text)
        assert result is None

    def test_supplier_with_umlauts(self, service):
        """Umlaute in Firmennamen werden behandelt."""
        name = "Muellers Warenhaus GmbH"
        result = service._normalize_for_filename(name)
        assert "Muellers" in result or "Mueller" in result
