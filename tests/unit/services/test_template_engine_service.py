# -*- coding: utf-8 -*-
"""Unit tests for Template Engine Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4
from datetime import datetime, timezone
from io import BytesIO

from app.services.templates.template_engine import (
    TemplateEngineService,
    RenderedDocument,
    TemplateInfo,
    TemplateVariable,
    BUILT_IN_TEMPLATES,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def template_service():
    """Template engine service instance."""
    return TemplateEngineService()


@pytest.fixture
def invoice_data():
    """Sample invoice data."""
    return {
        "firma_name": "Musterfirma GmbH",
        "firma_strasse": "Musterstraße 123",
        "firma_plz": "12345",
        "firma_ort": "München",
        "firma_email": "info@musterfirma.de",
        "firma_telefon": "+49 89 12345678",
        "kunde_firma": "Kundenname GmbH",
        "kunde_strasse": "Kundenstraße 456",
        "kunde_plz": "54321",
        "kunde_ort": "Berlin",
        "rechnungsnummer": "RE-2026-001",
        "rechnungsdatum": "2026-01-20",
        "leistungsdatum": "2026-01-15",
        "zahlungsziel": "2026-02-20",
        "positionen": [
            {"bezeichnung": "Beratung", "menge": 10, "betrag": 1000.00},
            {"bezeichnung": "Entwicklung", "menge": 20, "betrag": 2000.00},
        ],
        "nettobetrag": 3000.00,
        "umsatzsteuer": 570.00,
        "bruttobetrag": 3570.00,
        "bankverbindung": "DE89 3704 0044 0532 0130 00",
    }


@pytest.mark.asyncio
async def test_render_invoice_template(template_service, mock_db, invoice_data):
    """Test rendering of invoice template to HTML."""
    result = await template_service.render_template(
        template_id="rechnung_standard",
        data=invoice_data,
        output_format="html",
        db=mock_db,
    )

    assert isinstance(result, RenderedDocument)
    assert result.format == "html"
    assert result.mime_type == "text/html"
    assert result.template_id == "rechnung_standard"
    assert len(result.content) > 0
    assert result.filename.endswith(".html")

    # Verify content contains key data
    content_str = result.content.decode("utf-8")
    assert "Musterfirma GmbH" in content_str
    assert "RE-2026-001" in content_str


@pytest.mark.asyncio
async def test_render_offer_template(template_service, mock_db):
    """Test rendering of offer template."""
    offer_data = {
        "firma_name": "Testfirma AG",
        "firma_strasse": "Teststraße 1",
        "firma_plz": "10115",
        "firma_ort": "Berlin",
        "kunde_firma": "Kunde XYZ",
        "kunde_strasse": "Straße 2",
        "kunde_plz": "20095",
        "kunde_ort": "Hamburg",
        "angebotsnummer": "ANG-2026-001",
        "angebotsdatum": "2026-01-20",
        "gueltig_bis": "2026-02-20",
        "positionen": [
            {"bezeichnung": "Service A", "menge": 1, "betrag": 500.00},
        ],
        "nettobetrag": 500.00,
        "umsatzsteuer": 95.00,
        "bruttobetrag": 595.00,
    }

    result = await template_service.render_template(
        template_id="angebot_standard",
        data=offer_data,
        output_format="html",
        db=mock_db,
    )

    assert result.format == "html"
    assert result.template_id == "angebot_standard"
    content_str = result.content.decode("utf-8")
    assert "ANG-2026-001" in content_str


@pytest.mark.asyncio
async def test_render_dunning_template_1(template_service, mock_db):
    """Test rendering of 1st dunning letter template."""
    dunning_data = {
        "firma_name": "Mahnfirma GmbH",
        "kunde_firma": "Säumiger Kunde",
        "kunde_strasse": "Straße 99",
        "kunde_plz": "99999",
        "kunde_ort": "Musterstadt",
        "rechnungsnummer": "RE-2025-999",
        "rechnungsdatum": "2025-12-01",
        "faelligkeit": "2026-01-01",
        "betrag": 1000.00,
        "mahngebuehr": 5.00,
        "gesamtbetrag": 1005.00,
        "bankverbindung": "DE89 1234 5678 9012 3456 78",
    }

    result = await template_service.render_template(
        template_id="mahnung_1",
        data=dunning_data,
        output_format="html",
        db=mock_db,
    )

    assert result.format == "html"
    assert result.template_id == "mahnung_1"
    content_str = result.content.decode("utf-8")
    assert "RE-2025-999" in content_str


@pytest.mark.asyncio
async def test_render_dunning_template_2(template_service, mock_db):
    """Test rendering of 2nd dunning letter template."""
    dunning_data = {
        "firma_name": "Mahnfirma GmbH",
        "kunde_firma": "Säumiger Kunde",
        "kunde_strasse": "Straße 99",
        "kunde_plz": "99999",
        "kunde_ort": "Musterstadt",
        "rechnungsnummer": "RE-2025-999",
        "rechnungsdatum": "2025-12-01",
        "faelligkeit": "2026-01-01",
        "betrag": 1000.00,
        "mahngebuehr": 10.00,
        "verzugszinsen": 15.00,
        "gesamtbetrag": 1025.00,
        "bankverbindung": "DE89 1234 5678 9012 3456 78",
    }

    result = await template_service.render_template(
        template_id="mahnung_2",
        data=dunning_data,
        output_format="html",
        db=mock_db,
    )

    assert result.format == "html"
    assert result.template_id == "mahnung_2"


@pytest.mark.asyncio
async def test_render_dunning_template_3(template_service, mock_db):
    """Test rendering of 3rd (final) dunning letter template."""
    dunning_data = {
        "firma_name": "Mahnfirma GmbH",
        "kunde_firma": "Säumiger Kunde",
        "kunde_strasse": "Straße 99",
        "kunde_plz": "99999",
        "kunde_ort": "Musterstadt",
        "rechnungsnummer": "RE-2025-999",
        "rechnungsdatum": "2025-12-01",
        "faelligkeit": "2026-01-01",
        "betrag": 1000.00,
        "mahngebuehr": 15.00,
        "verzugszinsen": 30.00,
        "inkassokosten": 50.00,
        "gesamtbetrag": 1095.00,
        "frist_tage": 7,
        "bankverbindung": "DE89 1234 5678 9012 3456 78",
    }

    result = await template_service.render_template(
        template_id="mahnung_3",
        data=dunning_data,
        output_format="html",
        db=mock_db,
    )

    assert result.format == "html"
    assert result.template_id == "mahnung_3"


@pytest.mark.asyncio
async def test_render_credit_note_template(template_service, mock_db):
    """Test rendering of credit note template."""
    credit_note_data = {
        "firma_name": "Gutschriftfirma GmbH",
        "firma_strasse": "Straße 1",
        "firma_plz": "10115",
        "firma_ort": "Berlin",
        "kunde_firma": "Kunde ABC",
        "kunde_strasse": "Straße 2",
        "kunde_plz": "20095",
        "kunde_ort": "Hamburg",
        "gutschriftsnummer": "GUT-2026-001",
        "gutschriftsdatum": "2026-01-20",
        "ursprungsrechnung": "RE-2026-001",
        "positionen": [
            {"bezeichnung": "Rückerstattung", "menge": 1, "betrag": -100.00},
        ],
        "nettobetrag": -100.00,
        "umsatzsteuer": -19.00,
        "bruttobetrag": -119.00,
    }

    result = await template_service.render_template(
        template_id="gutschrift_standard",
        data=credit_note_data,
        output_format="html",
        db=mock_db,
    )

    assert result.format == "html"
    assert result.template_id == "gutschrift_standard"
    content_str = result.content.decode("utf-8")
    assert "GUT-2026-001" in content_str


@pytest.mark.asyncio
async def test_list_templates(template_service, mock_db):
    """Test listing all available templates."""
    templates = await template_service.list_templates(db=mock_db)

    assert len(templates) > 0
    assert all(isinstance(t, TemplateInfo) for t in templates)

    # Check for key templates
    template_ids = [t.id for t in templates]
    assert "rechnung_standard" in template_ids
    assert "angebot_standard" in template_ids
    assert "mahnung_1" in template_ids
    assert "gutschrift_standard" in template_ids


@pytest.mark.asyncio
async def test_list_templates_filtered_by_category(template_service, mock_db):
    """Test listing templates filtered by category."""
    templates = await template_service.list_templates(category="mahnung", db=mock_db)

    assert len(templates) == 3  # mahnung_1, mahnung_2, mahnung_3
    assert all(t.category == "mahnung" for t in templates)


@pytest.mark.asyncio
async def test_get_template_by_id(template_service):
    """Test getting template info by ID."""
    template = BUILT_IN_TEMPLATES.get("rechnung_standard")

    assert template is not None
    assert template.id == "rechnung_standard"
    assert template.name == "Standard-Rechnung"
    assert template.category == "rechnung"
    assert len(template.variables) > 0
    assert "pdf" in template.formats
    assert "docx" in template.formats
    assert "html" in template.formats


@pytest.mark.asyncio
async def test_render_with_missing_data(template_service, mock_db):
    """Test rendering template with missing required variables."""
    incomplete_data = {
        "firma_name": "Test GmbH",
        # Missing kunde_firma, rechnungsnummer, etc.
    }

    with pytest.raises(ValueError, match="Fehlende erforderliche Variablen"):
        await template_service.render_template(
            template_id="rechnung_standard",
            data=incomplete_data,
            output_format="html",
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_render_to_html(template_service, mock_db, invoice_data):
    """Test HTML output is correctly formatted."""
    result = await template_service.render_template(
        template_id="rechnung_standard",
        data=invoice_data,
        output_format="html",
        db=mock_db,
    )

    assert result.mime_type == "text/html"
    content = result.content.decode("utf-8")
    assert "<!DOCTYPE html>" in content or "<html>" in content
    assert invoice_data["firma_name"] in content
    assert invoice_data["kunde_firma"] in content


@pytest.mark.asyncio
@patch("app.services.templates.template_engine.HTML")
async def test_render_to_pdf(mock_html_class, template_service, mock_db, invoice_data):
    """Test PDF generation works (mock WeasyPrint)."""
    # Mock WeasyPrint HTML class
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf.return_value = b"PDF_CONTENT"
    mock_html_class.return_value = mock_html_instance

    result = await template_service.render_template(
        template_id="rechnung_standard",
        data=invoice_data,
        output_format="pdf",
        db=mock_db,
    )

    assert result.format == "pdf"
    assert result.mime_type == "application/pdf"
    assert result.content == b"PDF_CONTENT"
    mock_html_class.assert_called_once()
    mock_html_instance.write_pdf.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.templates.template_engine.DocxDocument")
async def test_render_to_docx(mock_docx_class, template_service, mock_db, invoice_data):
    """Test DOCX generation works (mock python-docx)."""
    # Mock DocxDocument
    mock_doc = MagicMock()
    mock_doc.save = MagicMock()
    mock_docx_class.return_value = mock_doc

    result = await template_service.render_template(
        template_id="rechnung_standard",
        data=invoice_data,
        output_format="docx",
        db=mock_db,
    )

    assert result.format == "docx"
    assert result.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    mock_docx_class.assert_called_once()
    mock_doc.save.assert_called_once()


@pytest.mark.asyncio
async def test_render_custom_template(template_service, mock_db):
    """Test rendering with custom user-created template (future feature)."""
    # Currently raises ValueError for unknown templates
    with pytest.raises(ValueError, match="Template nicht gefunden"):
        await template_service.render_template(
            template_id="custom_template_999",
            data={"firma_name": "Test"},
            output_format="html",
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_template_versioning(template_service):
    """Test template version tracking (metadata)."""
    # Built-in templates don't have versioning yet, but structure supports it
    template = BUILT_IN_TEMPLATES["rechnung_standard"]

    assert template.id == "rechnung_standard"
    assert template.name == "Standard-Rechnung"
    # Future: assert template.version == "1.0.0"


@pytest.mark.asyncio
async def test_get_template_variables(template_service):
    """Test retrieving template variable definitions."""
    variables = await template_service.get_template_variables("rechnung_standard")

    assert len(variables) > 0
    assert all(isinstance(v, TemplateVariable) for v in variables)

    # Check for required variables
    var_names = [v.name for v in variables]
    assert "firma_name" in var_names
    assert "kunde_firma" in var_names
    assert "rechnungsnummer" in var_names

    # Check variable properties
    firma_name_var = next(v for v in variables if v.name == "firma_name")
    assert firma_name_var.required is True
    assert firma_name_var.type == "text"


@pytest.mark.asyncio
async def test_currency_formatting(template_service):
    """Test German currency formatting filter."""
    # Test _format_currency method
    assert template_service._format_currency(1000) == "1.000,00 €"
    assert template_service._format_currency(1234.56) == "1.234,56 €"
    assert template_service._format_currency(0) == "0,00 €"
    assert template_service._format_currency(None) == "0,00 €"


@pytest.mark.asyncio
async def test_date_formatting(template_service):
    """Test German date formatting filter."""
    # Test _format_date_de method
    test_date = datetime(2026, 1, 20, 12, 30, 0)
    assert template_service._format_date_de(test_date) == "20.01.2026"

    # Test with ISO string
    assert template_service._format_date_de("2026-01-20") == "20.01.2026"

    # Test with None
    assert template_service._format_date_de(None) == ""


@pytest.mark.asyncio
async def test_invalid_format(template_service, mock_db, invoice_data):
    """Test error handling for invalid output format."""
    with pytest.raises(ValueError, match="nicht unterstützt"):
        await template_service.render_template(
            template_id="rechnung_standard",
            data=invoice_data,
            output_format="invalid_format",
            db=mock_db,
        )
