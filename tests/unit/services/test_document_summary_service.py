# -*- coding: utf-8 -*-
"""
Tests fuer DocumentSummaryService.

Testet Template-basierte Zusammenfassungen, Key-Facts-Extraktion,
Batch-Verarbeitung und Upsert-Logik.
"""

import pytest
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.document_summary_service import (
    DocumentSummaryService,
    SUMMARY_TEMPLATES,
    DOCUMENT_TYPE_LABELS,
    _safe_format,
    get_document_summary_service,
)


class _FakeModel:
    """Einfache Klasse die SQLAlchemy-Model-Konstruktor simuliert."""

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# =============================================================================
# _safe_format Tests
# =============================================================================


class TestSafeFormat:
    """Tests fuer _safe_format Hilfsfunktion."""

    def test_alle_variablen_vorhanden(self) -> None:
        """Alle Variablen werden korrekt ersetzt."""
        result = _safe_format("Hallo {name}, {betrag} EUR", name="Max", betrag="42")
        assert result == "Hallo Max, 42 EUR"

    def test_fehlende_variablen_werden_fragezeichen(self) -> None:
        """Fehlende Variablen werden durch '?' ersetzt."""
        result = _safe_format("Rechnung #{number} von {supplier}", number="4711")
        assert result == "Rechnung #4711 von ?"

    def test_leeres_template(self) -> None:
        """Leeres Template gibt leeren String zurueck."""
        result = _safe_format("")
        assert result == ""

    def test_keine_platzhalter(self) -> None:
        """Template ohne Platzhalter bleibt unveraendert."""
        result = _safe_format("Kein Platzhalter hier")
        assert result == "Kein Platzhalter hier"


# =============================================================================
# Template Tests
# =============================================================================


class TestSummaryTemplates:
    """Tests fuer SUMMARY_TEMPLATES und DOCUMENT_TYPE_LABELS."""

    def test_alle_erwarteten_templates_vorhanden(self) -> None:
        """Alle Dokumenttypen haben ein Template."""
        expected = {"invoice", "delivery_note", "contract", "order", "credit_note", "default"}
        assert set(SUMMARY_TEMPLATES.keys()) == expected

    def test_alle_erwarteten_labels_vorhanden(self) -> None:
        """Alle Dokumenttypen haben ein deutsches Label."""
        expected = {
            "invoice", "delivery_note", "order", "contract",
            "credit_note", "quote", "reminder", "receipt",
        }
        assert set(DOCUMENT_TYPE_LABELS.keys()) == expected

    def test_labels_sind_deutsch(self) -> None:
        """Labels sind in deutscher Sprache."""
        assert DOCUMENT_TYPE_LABELS["invoice"] == "Rechnung"
        assert DOCUMENT_TYPE_LABELS["delivery_note"] == "Lieferschein"
        assert DOCUMENT_TYPE_LABELS["contract"] == "Vertrag"
        assert DOCUMENT_TYPE_LABELS["order"] == "Bestellung"

    def test_invoice_template_enthalt_skonto(self) -> None:
        """Rechnungs-Template hat Skonto-Platzhalter."""
        template = SUMMARY_TEMPLATES["invoice"]
        assert "{skonto}" in template
        assert "{number}" in template
        assert "{supplier}" in template


# =============================================================================
# _prepare_template_vars Tests
# =============================================================================


class TestPrepareTemplateVars:
    """Tests fuer _prepare_template_vars."""

    def setup_method(self) -> None:
        self.service = DocumentSummaryService()

    def test_rechnung_mit_skonto(self) -> None:
        """Rechnungsvariablen mit Skonto werden korrekt aufgebaut."""
        data: Dict[str, str] = {
            "invoice_number": "4711",
            "supplier_name": "Mueller GmbH",
            "total_amount": "3.450",
            "vat_amount": "655",
            "payment_days": "30",
            "skonto_percent": "2",
            "skonto_days": "10",
        }
        result = self.service._prepare_template_vars("invoice", data)

        assert result["number"] == "4711"
        assert result["supplier"] == "Mueller GmbH"
        assert result["amount"] == "3.450"
        assert result["tax_type"] == "brutto"
        assert result["payment_days"] == "30"
        assert "2%" in result["skonto"]
        assert "10 Tagen" in result["skonto"]

    def test_rechnung_ohne_skonto(self) -> None:
        """Rechnungsvariablen ohne Skonto."""
        data: Dict[str, str] = {
            "invoice_number": "100",
            "supplier_name": "Test AG",
            "net_amount": "1000",
        }
        result = self.service._prepare_template_vars("invoice", data)

        assert result["tax_type"] == "netto"
        assert result["skonto"] == ""

    def test_rechnung_default_zahlungsziel(self) -> None:
        """Standardmaessig 30 Tage Zahlungsziel."""
        data: Dict[str, str] = {"invoice_number": "1"}
        result = self.service._prepare_template_vars("invoice", data)
        assert result["payment_days"] == "30"

    def test_lieferschein_variablen(self) -> None:
        """Lieferschein hat item_count."""
        data: Dict[str, str] = {"item_count": "5"}
        result = self.service._prepare_template_vars("delivery_note", data)
        assert result["item_count"] == "5"

    def test_vertrag_mit_verlaengerung(self) -> None:
        """Vertrag mit automatischer Verlaengerung."""
        data: Dict[str, str] = {
            "supplier_name": "Partner AG",
            "contract_start": "01.01.2026",
            "contract_end": "31.12.2026",
            "contract_value": "50000",
            "auto_renewal": "true",
        }
        result = self.service._prepare_template_vars("contract", data)

        assert result["party"] == "Partner AG"
        assert result["start"] == "01.01.2026"
        assert result["end"] == "31.12.2026"
        assert "Verlängerung" in result["renewal"]

    def test_vertrag_ohne_verlaengerung(self) -> None:
        """Vertrag ohne automatische Verlaengerung."""
        data: Dict[str, str] = {"auto_renewal": "false"}
        result = self.service._prepare_template_vars("contract", data)
        assert result["renewal"] == ""

    def test_bestellung_liefertermin(self) -> None:
        """Bestellung hat delivery_date."""
        data: Dict[str, str] = {"delivery_date": "15.03.2026"}
        result = self.service._prepare_template_vars("order", data)
        assert result["delivery_date"] == "15.03.2026"

    def test_unbekannter_typ_grundvariablen(self) -> None:
        """Unbekannter Typ hat nur Grundvariablen."""
        data: Dict[str, str] = {"supplier_name": "X GmbH", "date": "01.01.2026"}
        result = self.service._prepare_template_vars("unknown", data)
        assert result["entity"] == "X GmbH"
        assert result["date"] == "01.01.2026"


# =============================================================================
# _extract_key_facts Tests
# =============================================================================


class TestExtractKeyFacts:
    """Tests fuer _extract_key_facts."""

    def setup_method(self) -> None:
        self.service = DocumentSummaryService()

    def test_grundfelder_immer_vorhanden(self) -> None:
        """type und type_label sind immer gesetzt."""
        facts = self.service._extract_key_facts("invoice", {})
        assert facts["type"] == "invoice"
        assert facts["type_label"] == "Rechnung"

    def test_standardfelder_uebernommen(self) -> None:
        """Vorhandene Standardfelder werden uebernommen."""
        data: Dict[str, str] = {
            "invoice_number": "4711",
            "supplier_name": "Test GmbH",
            "total_amount": "1000",
            "iban": "DE89370400440532013000",
        }
        facts = self.service._extract_key_facts("invoice", data)
        assert facts["invoice_number"] == "4711"
        assert facts["supplier_name"] == "Test GmbH"
        assert facts["total_amount"] == "1000"
        assert facts["iban"] == "DE89370400440532013000"

    def test_leere_felder_nicht_uebernommen(self) -> None:
        """Leere Strings werden nicht in Facts uebernommen."""
        data: Dict[str, str] = {
            "invoice_number": "123",
            "supplier_name": "",
        }
        facts = self.service._extract_key_facts("invoice", data)
        assert "invoice_number" in facts
        assert "supplier_name" not in facts

    def test_unbekannter_typ_label(self) -> None:
        """Unbekannter Typ benutzt Typ-String als Label."""
        facts = self.service._extract_key_facts("sonstiges", {})
        assert facts["type_label"] == "sonstiges"


# =============================================================================
# generate_summary Tests
# =============================================================================


class TestGenerateSummary:
    """Tests fuer generate_summary (async).

    get_summary wird gemockt um SQLAlchemy select() zu umgehen.
    DocumentSummary-Konstruktor wird durch _FakeModel ersetzt.
    """

    def setup_method(self) -> None:
        self.service = DocumentSummaryService()
        self.doc_id = uuid4()
        self.company_id = uuid4()

    @pytest.mark.asyncio
    async def test_neue_summary_erstellen(self) -> None:
        """Neue Summary wird in DB gespeichert."""
        db = AsyncMock()

        extracted = {
            "document_type": "invoice",
            "invoice_number": "4711",
            "supplier_name": "Mueller GmbH",
            "total_amount": "3.450",
            "payment_days": "30",
        }

        with patch.object(self.service, "get_summary", new_callable=AsyncMock, return_value=None), \
             patch("app.services.document_summary_service.DocumentSummary", _FakeModel):
            result = await self.service.generate_summary(
                db=db,
                document_id=self.doc_id,
                company_id=self.company_id,
                extracted_data=extracted,
            )

        assert result.summary_text is not None
        assert "4711" in result.summary_text
        assert "Mueller GmbH" in result.summary_text
        assert result.summary_template == "invoice"
        assert result.model_used == "template"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existierende_summary_update(self) -> None:
        """Existierende Summary wird aktualisiert (Upsert)."""
        existing = MagicMock()
        existing.summary_text = "alt"

        db = AsyncMock()

        with patch.object(self.service, "get_summary", new_callable=AsyncMock, return_value=existing):
            result = await self.service.generate_summary(
                db=db,
                document_id=self.doc_id,
                company_id=self.company_id,
                extracted_data={
                    "document_type": "invoice",
                    "invoice_number": "999",
                    "supplier_name": "Neu AG",
                },
            )

        assert result is existing
        assert "999" in existing.summary_text
        assert existing.model_used == "template"
        db.add.assert_not_called()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_detect_document_type(self) -> None:
        """Dokumenttyp wird aus extrahierten Daten bestimmt."""
        db = AsyncMock()

        with patch.object(self.service, "get_summary", new_callable=AsyncMock, return_value=None), \
             patch("app.services.document_summary_service.DocumentSummary", _FakeModel):
            result = await self.service.generate_summary(
                db=db,
                document_id=self.doc_id,
                company_id=self.company_id,
                extracted_data={"document_type": "credit_note", "invoice_number": "G-100"},
            )

        assert result.summary_template == "credit_note"

    @pytest.mark.asyncio
    async def test_unbekannter_typ_nutzt_default_template(self) -> None:
        """Unbekannter Dokumenttyp nutzt Default-Template."""
        db = AsyncMock()

        with patch.object(self.service, "get_summary", new_callable=AsyncMock, return_value=None), \
             patch("app.services.document_summary_service.DocumentSummary", _FakeModel):
            result = await self.service.generate_summary(
                db=db,
                document_id=self.doc_id,
                company_id=self.company_id,
                extracted_data={"document_type": "sonstiges"},
            )

        assert result.summary_template == "default"

    @pytest.mark.asyncio
    async def test_laden_extrahierter_daten(self) -> None:
        """Wenn keine extracted_data uebergeben, werden sie aus DB geladen."""
        db = AsyncMock()

        mock_data = {"invoice_number": "ABC", "document_type": "default"}

        with patch.object(self.service, "_load_extracted_data", new_callable=AsyncMock, return_value=mock_data) as mock_load, \
             patch.object(self.service, "get_summary", new_callable=AsyncMock, return_value=None), \
             patch("app.services.document_summary_service.DocumentSummary", _FakeModel):
            result = await self.service.generate_summary(
                db=db,
                document_id=self.doc_id,
                company_id=self.company_id,
            )

        mock_load.assert_awaited_once_with(db, self.doc_id)
        assert result.summary_text is not None

    @pytest.mark.asyncio
    async def test_korrigierte_werte_bevorzugt(self) -> None:
        """_load_extracted_data bevorzugt corrected_value."""
        mock_record = MagicMock()
        mock_record.field_name = "supplier_name"
        mock_record.extracted_value = "Muller"
        mock_record.corrected_value = "Mueller GmbH"
        mock_record.was_corrected = True

        db = AsyncMock()
        db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_record])))
        )

        data = await self.service._load_extracted_data(db, self.doc_id)
        assert data["supplier_name"] == "Mueller GmbH"


# =============================================================================
# get_summary & get_key_facts Tests
# =============================================================================


class TestGetSummaryAndKeyFacts:
    """Tests fuer get_summary und get_key_facts."""

    def setup_method(self) -> None:
        self.service = DocumentSummaryService()
        self.doc_id = uuid4()

    @pytest.mark.asyncio
    async def test_get_summary_gefunden(self) -> None:
        """get_summary gibt vorhandene Summary zurueck."""
        mock_summary = MagicMock()
        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_summary))

        result = await self.service.get_summary(db, self.doc_id)
        assert result is mock_summary

    @pytest.mark.asyncio
    async def test_get_summary_nicht_gefunden(self) -> None:
        """get_summary gibt None zurueck wenn nichts vorhanden."""
        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        result = await self.service.get_summary(db, self.doc_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_key_facts_vorhanden(self) -> None:
        """get_key_facts gibt Facts-Dict zurueck."""
        mock_summary = MagicMock()
        mock_summary.key_facts = {"type": "invoice", "invoice_number": "4711"}

        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_summary))

        result = await self.service.get_key_facts(db, self.doc_id)
        assert result is not None
        assert result["invoice_number"] == "4711"

    @pytest.mark.asyncio
    async def test_get_key_facts_keine_summary(self) -> None:
        """get_key_facts gibt None zurueck ohne Summary."""
        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        result = await self.service.get_key_facts(db, self.doc_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_key_facts_leere_facts(self) -> None:
        """get_key_facts gibt None zurueck bei leeren key_facts."""
        mock_summary = MagicMock()
        mock_summary.key_facts = None

        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_summary))

        result = await self.service.get_key_facts(db, self.doc_id)
        assert result is None


# =============================================================================
# batch_generate_summaries Tests
# =============================================================================


class TestBatchGenerateSummaries:
    """Tests fuer batch_generate_summaries."""

    def setup_method(self) -> None:
        self.service = DocumentSummaryService()
        self.company_id = uuid4()

    @pytest.mark.asyncio
    async def test_batch_generiert_fehlende(self) -> None:
        """Batch generiert nur fuer Dokumente ohne Summary."""
        doc_ids = [uuid4(), uuid4(), uuid4()]

        existing_summary = MagicMock()
        new_summary = MagicMock()

        with patch.object(self.service, "get_summary") as mock_get, \
             patch.object(self.service, "generate_summary") as mock_gen:
            # Erstes Dokument hat bereits Summary
            mock_get.side_effect = [existing_summary, None, None]
            mock_gen.side_effect = [new_summary, new_summary]

            results = await self.service.batch_generate_summaries(
                db=AsyncMock(),
                company_id=self.company_id,
                document_ids=doc_ids,
            )

        assert len(results) == 3
        assert results[0] is existing_summary
        assert mock_gen.await_count == 2

    @pytest.mark.asyncio
    async def test_batch_fehler_ueberspringt(self) -> None:
        """Fehler bei einzelnem Dokument ueberspringt es."""
        doc_ids = [uuid4(), uuid4()]

        with patch.object(self.service, "get_summary", return_value=None), \
             patch.object(self.service, "generate_summary") as mock_gen:
            mock_gen.side_effect = [Exception("DB Error"), MagicMock()]

            results = await self.service.batch_generate_summaries(
                db=AsyncMock(),
                company_id=self.company_id,
                document_ids=doc_ids,
            )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_batch_leere_liste(self) -> None:
        """Leere Dokumentliste ergibt leere Ergebnisliste."""
        results = await self.service.batch_generate_summaries(
            db=AsyncMock(),
            company_id=self.company_id,
            document_ids=[],
        )
        assert results == []


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton Factory."""

    def test_singleton_gibt_instanz_zurueck(self) -> None:
        """get_document_summary_service gibt DocumentSummaryService zurueck."""
        service = get_document_summary_service()
        assert isinstance(service, DocumentSummaryService)

    def test_singleton_gleiche_instanz(self) -> None:
        """Zweiter Aufruf gibt dieselbe Instanz zurueck."""
        s1 = get_document_summary_service()
        s2 = get_document_summary_service()
        assert s1 is s2
