# -*- coding: utf-8 -*-
"""Tests fuer den Odoo Vendor-Bill-Push-Service (Neuausrichtung Phase 4).

Alles gemockt — KEINE echten Odoo-/DB-/Storage-Zugriffe:
- Betrag-Auswahl-Logik (gross_amount > net+vat > max amounts > max detected)
- Deutscher Betrags-Parser ("1.234,56 €")
- Hook-Logik als reine Funktion (email/folder erlaubt, odoo_mirror NIE)
- Idempotenz (odoo_move_id vorhanden -> skipped, kein Connector-Call)
- Klassifikations-Gates (keine Rechnung / Ausgangsrechnung -> skipped)
- Mapping-Vorrang vor der find_partner-Kaskade
- Genau-1-Treffer-Regel (0 -> no_partner_match, 1 -> pushed, 2 -> ambiguous)
- Review-Aufgabe (document_metadata.pipeline_result.requires_review)
- doc_metadata-Persistenz (odoo_push_status/odoo_move_id/...)
- Lernschleife R6 (ERPEntityMapping wird nach Kaskaden-Treffer angelegt)
- W1-030-Fix: automation/AutoFilingService legt echte FolderDocument-Zeile an
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.models_erp_import import ERPEntityMapping
from app.db.models_folder import FolderDocument
from app.services.erp import odoo_vendor_bill_push_service as svc
from app.services.erp.odoo_vendor_bill_push_service import (
    PushResult,
    _parse_german_amount,
    is_extraction_ready,
    is_push_eligible_source,
    push_document,
    select_gross_amount,
)


# =============================================================================
# Fixtures & Helpers
# =============================================================================


def _extracted_data(**invoice_overrides: object) -> dict:
    """Standard-extracted_data einer Eingangsrechnung (JSONB-Form)."""
    invoice: dict = {
        "invoice_number": "RE-2026-0815",
        "invoice_date": "2026-07-01",
        "gross_amount": "119.00",
        "net_amount": "100.00",
        "vat_amount": "19.00",
        "sender_vat_id": "DE123456789",
        "supplier_number": "K-100",
        "sender": {"company": "Muster Lieferant GmbH"},
        "sender_bank": {"iban": "DE02120300000000202051"},
        "invoice_direction": "incoming",
        "currency": "EUR",
    }
    invoice.update(invoice_overrides)
    return {
        "classification": {"document_type": "invoice", "confidence": 0.92},
        "invoice": invoice,
        "amounts": ["100.00", "19.00", "119.00"],
        "ibans": ["DE02120300000000202051"],
        "vat_ids": ["DE123456789"],
    }


def _make_document(
    *,
    extracted_data: dict | None = None,
    document_metadata: dict | None = None,
    business_entity_id=None,
    document_type: str = "invoice",
):
    """Leichtgewichtiges Dokument-Double (nur die genutzten Attribute)."""
    return SimpleNamespace(
        id=uuid4(),
        company_id=uuid4(),
        business_entity_id=business_entity_id,
        document_type=document_type,
        extracted_data=_extracted_data() if extracted_data is None else extracted_data,
        document_metadata=(
            {"import_source": "email"}
            if document_metadata is None
            else document_metadata
        ),
        file_path="documents/2026/07/test.pdf",
        original_filename="rechnung.pdf",
        filename="rechnung.pdf",
    )


def _make_connector(partners: list | None = None, move_id: str | None = "4711"):
    """Connector-Double: connect/find_partner/create_vendor_bill_draft."""
    connector = MagicMock()
    connector.connect = AsyncMock(return_value=True)
    connector.find_partner = AsyncMock(return_value=partners or [])
    connector.create_vendor_bill_draft = AsyncMock(return_value=move_id)
    return connector


def _make_db():
    """AsyncSession-Double (nur commit/add werden vom Service genutzt)."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def connection():
    """ERPConnection-Double (nur id wird gebraucht)."""
    return SimpleNamespace(id=uuid4())


def _patch_service(
    monkeypatch,
    *,
    document,
    connection,
    connector,
    mapping=None,
    detected_amounts=None,
    pdf: bytes | None = b"%PDF-fake",
):
    """Patcht alle DB-/IO-Helfer des Service-Moduls."""
    monkeypatch.setattr(svc, "_load_document", AsyncMock(return_value=document))
    monkeypatch.setattr(
        svc, "_load_active_connection", AsyncMock(return_value=connection)
    )
    monkeypatch.setattr(svc, "_load_entity_mapping", AsyncMock(return_value=mapping))
    monkeypatch.setattr(
        svc, "_load_detected_amounts", AsyncMock(return_value=detected_amounts or [])
    )
    monkeypatch.setattr(svc, "_load_pdf", AsyncMock(return_value=pdf))
    monkeypatch.setattr(svc, "_build_connector", AsyncMock(return_value=connector))


# =============================================================================
# Betrag-Auswahl-Logik
# =============================================================================


class TestSelectGrossAmount:
    def test_bevorzugt_explizites_brutto(self):
        """Stufe 1: gross_amount gewinnt gegen alle Fallbacks."""
        amount, source = select_gross_amount(_extracted_data(), ["999,99 €"])
        assert amount == Decimal("119.00")
        assert source == "gross_amount"

    def test_netto_plus_mwst_wenn_brutto_fehlt(self):
        """Stufe 2: net + vat, wenn beide vorhanden und Brutto fehlt."""
        data = _extracted_data(gross_amount=None)
        amount, source = select_gross_amount(data, [])
        assert amount == Decimal("119.00")
        assert source == "net_plus_vat"

    def test_max_extrahierter_betrag_als_fallback(self):
        """Stufe 3: groesster strukturiert extrahierter Betrag."""
        data = _extracted_data(gross_amount=None, net_amount=None, vat_amount=None)
        amount, source = select_gross_amount(data, [])
        assert amount == Decimal("119.00")  # max(100, 19, 119)
        assert source == "max_extracted_amount"

    def test_max_detected_amount_deutsch_geparst(self):
        """Stufe 4: groesster OCR-Betrag im deutschen Format."""
        data = _extracted_data(gross_amount=None, net_amount=None, vat_amount=None)
        data["amounts"] = []
        amount, source = select_gross_amount(
            data, ["19,00 €", "1.234,56 EUR", "100,00 Euro"]
        )
        assert amount == Decimal("1234.56")
        assert source == "max_detected_amount"

    def test_kein_betrag_liefert_none(self):
        data = _extracted_data(gross_amount=None, net_amount=None, vat_amount=None)
        data["amounts"] = []
        amount, source = select_gross_amount(data, [])
        assert amount is None
        assert source is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1.234,56 €", Decimal("1234.56")),
            ("€ 1.234,56", Decimal("1234.56")),
            ("100,00 Euro", Decimal("100.00")),
            ("1.234 EUR", Decimal("1234")),  # Punkt = Tausendertrenner
            ("keine Zahl", None),
        ],
    )
    def test_parse_german_amount(self, raw, expected):
        assert _parse_german_amount(raw) == expected


# =============================================================================
# Hook-Logik (reine Funktion) — odoo_mirror-Ausschluss
# =============================================================================


class TestPushEligibleSource:
    @pytest.mark.parametrize("source", ["email", "folder"])
    def test_email_und_folder_erlaubt(self, source):
        assert is_push_eligible_source({"import_source": source}) is True

    def test_odoo_mirror_immer_ausgeschlossen(self):
        """Spiegel-Dokumente duerfen NIE zurueck nach Odoo (Kreislauf)."""
        assert is_push_eligible_source({"import_source": "odoo_mirror"}) is False

    @pytest.mark.parametrize(
        "meta",
        [None, {}, {"import_source": "upload"}, {"import_source": "scanner_xyz"}],
    )
    def test_andere_quellen_nicht_erlaubt(self, meta):
        assert is_push_eligible_source(meta) is False


class TestExtractionReady:
    def test_ready_mit_classification(self):
        doc = _make_document()
        assert is_extraction_ready(doc) is True

    def test_nicht_ready_ohne_extraktion(self):
        doc = _make_document(extracted_data={})
        assert is_extraction_ready(doc) is False


# =============================================================================
# push_document — Gates & Idempotenz
# =============================================================================


class TestPushDocumentGates:
    @pytest.mark.asyncio
    async def test_idempotent_skipped_wenn_move_id_existiert(
        self, monkeypatch, connection
    ):
        """Bereits gepusht -> skipped, KEIN Connector-Aufbau."""
        doc = _make_document(
            document_metadata={"import_source": "email", "odoo_move_id": "4711"}
        )
        connector = _make_connector()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "skipped"
        assert result.odoo_move_id == "4711"
        svc._build_connector.assert_not_awaited()
        connector.create_vendor_bill_draft.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_odoo_mirror_quelle_wird_uebersprungen(
        self, monkeypatch, connection
    ):
        doc = _make_document(document_metadata={"import_source": "odoo_mirror"})
        connector = _make_connector()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )

        result = await push_document(_make_db(), doc.id)

        assert result.status == "skipped"
        connector.create_vendor_bill_draft.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_keine_rechnung_skipped(self, monkeypatch, connection):
        """Klassifikation != invoice -> skipped."""
        data = _extracted_data()
        data["classification"] = {"document_type": "contract", "confidence": 0.9}
        doc = _make_document(extracted_data=data, document_type="contract")
        connector = _make_connector()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )

        result = await push_document(_make_db(), doc.id)

        assert result.status == "skipped"
        assert "Keine Rechnung" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_ausgangsrechnung_skipped(self, monkeypatch, connection):
        doc = _make_document(
            extracted_data=_extracted_data(invoice_direction="outgoing")
        )
        connector = _make_connector()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )

        result = await push_document(_make_db(), doc.id)

        assert result.status == "skipped"
        assert "Ausgangsrechnung" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_kein_betrag_error_mit_review(self, monkeypatch, connection):
        """Ohne extrahierbaren Betrag: error (nicht retrybar) + Review-Aufgabe."""
        data = _extracted_data(gross_amount=None, net_amount=None, vat_amount=None)
        data["amounts"] = []
        doc = _make_document(extracted_data=data)
        connector = _make_connector()
        _patch_service(
            monkeypatch,
            document=doc,
            connection=connection,
            connector=connector,
            detected_amounts=[],
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "error"
        assert result.retryable is False
        pipeline_result = doc.document_metadata["pipeline_result"]
        assert pipeline_result["requires_review"] is True
        assert any(
            "Eingangsrechnung ohne Odoo-Zuordnung" in r
            for r in pipeline_result["review_reasons"]
        )
        db.commit.assert_awaited()


# =============================================================================
# push_document — Partner-Matching (Mapping-Vorrang + Genau-1-Regel)
# =============================================================================


class TestPartnerMatching:
    @pytest.mark.asyncio
    async def test_mapping_hat_vorrang_vor_kaskade(self, monkeypatch, connection):
        """ERPEntityMapping vorhanden -> partner_id direkt, KEIN find_partner."""
        entity_id = uuid4()
        doc = _make_document(business_entity_id=entity_id)
        mapping = SimpleNamespace(id=uuid4(), remote_id="99")
        connector = _make_connector(move_id="555")
        _patch_service(
            monkeypatch,
            document=doc,
            connection=connection,
            connector=connector,
            mapping=mapping,
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "pushed"
        assert result.partner_match_source == "entity_mapping"
        connector.find_partner.assert_not_awaited()
        draft = connector.create_vendor_bill_draft.await_args.args[0]
        assert draft.partner_id == 99

    @pytest.mark.asyncio
    async def test_genau_ein_treffer_pusht(self, monkeypatch, connection):
        connector = _make_connector(
            partners=[{"id": 7, "match_source": "vat"}], move_id="777"
        )
        doc = _make_document()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "pushed"
        assert result.odoo_move_id == "777"
        assert result.partner_match_source == "vat"
        draft = connector.create_vendor_bill_draft.await_args.args[0]
        assert draft.partner_id == 7
        assert draft.ref == "RE-2026-0815"
        assert draft.amount_total_brutto == Decimal("119.00")

    @pytest.mark.asyncio
    async def test_null_treffer_no_partner_match_mit_review(
        self, monkeypatch, connection
    ):
        connector = _make_connector(partners=[])
        doc = _make_document()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "no_partner_match"
        connector.create_vendor_bill_draft.assert_not_awaited()
        # Review-Aufgabe ueber den vorhandenen Queue-Mechanismus
        pipeline_result = doc.document_metadata["pipeline_result"]
        assert pipeline_result["requires_review"] is True
        assert pipeline_result["review_confirmed"] is False
        assert any(
            "Eingangsrechnung ohne Odoo-Zuordnung" in r
            for r in pipeline_result["review_reasons"]
        )
        # Statusfelder trotzdem persistiert
        assert doc.document_metadata["odoo_push_status"] == "no_partner_match"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_zwei_treffer_ambiguous_kein_push(self, monkeypatch, connection):
        connector = _make_connector(
            partners=[
                {"id": 1, "match_source": "name"},
                {"id": 2, "match_source": "name"},
            ]
        )
        doc = _make_document()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "ambiguous"
        connector.create_vendor_bill_draft.assert_not_awaited()
        assert doc.document_metadata["pipeline_result"]["requires_review"] is True

    @pytest.mark.asyncio
    async def test_lernschleife_legt_mapping_an(self, monkeypatch, connection):
        """Kaskaden-Treffer + BusinessEntity ohne Mapping -> ERPEntityMapping neu."""
        entity_id = uuid4()
        doc = _make_document(business_entity_id=entity_id)
        connector = _make_connector(
            partners=[{"id": 42, "match_source": "iban"}], move_id="808"
        )
        _patch_service(
            monkeypatch,
            document=doc,
            connection=connection,
            connector=connector,
            mapping=None,
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "pushed"
        added = [
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], ERPEntityMapping)
        ]
        assert len(added) == 1
        assert added[0].entity_type == "supplier"
        assert added[0].local_id == entity_id
        assert added[0].remote_id == "42"


# =============================================================================
# push_document — Persistenz & Fehlerpfade
# =============================================================================


class TestPersistenceAndErrors:
    @pytest.mark.asyncio
    async def test_doc_metadata_persistenz_bei_push(self, monkeypatch, connection):
        """odoo_push_status/odoo_move_id/odoo_push_at/partner_match_source gesetzt."""
        connector = _make_connector(
            partners=[{"id": 7, "match_source": "vat"}], move_id="4711"
        )
        doc = _make_document()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )
        db = _make_db()

        result = await push_document(db, doc.id)

        assert result.status == "pushed"
        meta = doc.document_metadata
        assert meta["odoo_push_status"] == "pushed"
        assert meta["odoo_move_id"] == "4711"
        assert meta["partner_match_source"] == "vat"
        assert "odoo_push_at" in meta
        # Import-Quelle bleibt erhalten (Merge statt Ueberschreiben)
        assert meta["import_source"] == "email"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_odoo_down_error_retryable_ohne_review_vor_final(
        self, monkeypatch, connection
    ):
        """Odoo nicht erreichbar: retrybarer error; Review erst beim Finale."""
        doc = _make_document()
        connector = _make_connector()
        connector.connect = AsyncMock(return_value=False)
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )
        db = _make_db()

        result = await push_document(db, doc.id, is_final_attempt=False)

        assert result.status == "error"
        assert result.retryable is True
        # Kein Review, keine Persistenz vor dem finalen Versuch
        assert "pipeline_result" not in doc.document_metadata
        db.commit.assert_not_awaited()

        result_final = await push_document(db, doc.id, is_final_attempt=True)
        assert result_final.status == "error"
        assert doc.document_metadata["pipeline_result"]["requires_review"] is True

    @pytest.mark.asyncio
    async def test_create_fehlschlag_final_erzeugt_review(
        self, monkeypatch, connection
    ):
        connector = _make_connector(
            partners=[{"id": 7, "match_source": "vat"}], move_id=None
        )
        doc = _make_document()
        _patch_service(
            monkeypatch, document=doc, connection=connection, connector=connector
        )
        db = _make_db()

        result = await push_document(db, doc.id, is_final_attempt=True)

        assert result.status == "error"
        assert result.retryable is True
        assert doc.document_metadata["odoo_push_status"] == "error"
        assert doc.document_metadata["pipeline_result"]["requires_review"] is True

    @pytest.mark.asyncio
    async def test_pdf_wird_uebergeben(self, monkeypatch, connection):
        """Original-Bytes aus dem Storage gehen an create_vendor_bill_draft."""
        connector = _make_connector(partners=[{"id": 7, "match_source": "vat"}])
        doc = _make_document()
        _patch_service(
            monkeypatch,
            document=doc,
            connection=connection,
            connector=connector,
            pdf=b"%PDF-original",
        )

        await push_document(_make_db(), doc.id)

        kwargs = connector.create_vendor_bill_draft.await_args.kwargs
        assert kwargs["pdf_content"] == b"%PDF-original"
        assert kwargs["pdf_filename"] == "rechnung.pdf"


# =============================================================================
# W1-030: automation/AutoFilingService legt echte folder_documents-Zeile an
# =============================================================================


class TestW1030AutoFilingFolder:
    @pytest.mark.asyncio
    async def test_auto_file_document_legt_folder_document_an(self, monkeypatch):
        """Der fruehere No-op-Guard ist ersetzt: echte FolderDocument-Zeile."""
        from app.services.automation.auto_filing_service import (
            AutoFilingService,
            FilingSuggestion,
        )

        company_id = uuid4()
        document_id = uuid4()
        folder_id = uuid4()

        suggestion = FilingSuggestion(
            rule_id=uuid4(),
            rule_name="Rechnungen-Regel",
            target_folder_id=folder_id,
            target_category=None,
            confidence=0.99,
            model_type="rule",
            auto_file=True,
        )

        db = MagicMock()
        document = SimpleNamespace(id=document_id, data_category=None)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = document
        assoc_result = MagicMock()
        assoc_result.scalar_one_or_none.return_value = None  # noch keine Zuordnung
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[doc_result, assoc_result, update_result])
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = AutoFilingService(db)
        monkeypatch.setattr(
            service, "get_filing_suggestion", AsyncMock(return_value=suggestion)
        )

        result = await service.auto_file_document(db, company_id, document_id)

        assert result.filed is True
        added = [
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], FolderDocument)
        ]
        assert len(added) == 1
        assert added[0].folder_id == folder_id
        assert added[0].document_id == document_id
        assert added[0].is_primary is True

    @pytest.mark.asyncio
    async def test_auto_file_document_idempotent_bei_bestehender_zuordnung(
        self, monkeypatch
    ):
        """Existierende folder_documents-Zeile -> kein Duplikat, trotzdem filed."""
        from app.services.automation.auto_filing_service import (
            AutoFilingService,
            FilingSuggestion,
        )

        folder_id = uuid4()
        document_id = uuid4()
        suggestion = FilingSuggestion(
            rule_id=uuid4(),
            rule_name="Rechnungen-Regel",
            target_folder_id=folder_id,
            target_category=None,
            confidence=0.99,
            model_type="rule",
            auto_file=True,
        )

        db = MagicMock()
        document = SimpleNamespace(id=document_id, data_category=None)
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = document
        assoc_result = MagicMock()
        assoc_result.scalar_one_or_none.return_value = SimpleNamespace()  # existiert
        db.execute = AsyncMock(side_effect=[doc_result, assoc_result])
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = AutoFilingService(db)
        monkeypatch.setattr(
            service, "get_filing_suggestion", AsyncMock(return_value=suggestion)
        )

        result = await service.auto_file_document(db, uuid4(), document_id)

        assert result.filed is True
        db.add.assert_not_called()
