"""Tests fuer die Phase-2-Erweiterungen des Odoo-Connectors (Neuausrichtung).

Abgedeckt (alles gemockt, KEINE echten Odoo-Calls):
- iter_records: Pagination terminiert, offset waechst, order/domain korrekt
- Company-Context-Injektion in _execute_kw (mit/ohne odoo_company_id, Merge)
- download_attachment: base64-Decode + False-datas (Odoo liefert False fuer leer)
- list_attachments: impliziter res_field-Filter vs. Tautologie-OR-Domain
- create_vendor_bill_draft: Payload-Form, Decimal->float-Rundung, Attachment-Pfad
- find_partner: Kaskaden-Reihenfolge, match_source, IBAN-Normalisierung

Mock-Muster wie tests/unit/services/erp/test_odoo_connector.py
(patch auf xmlrpc.client.ServerProxy).
"""

import base64
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4
import xmlrpc.client

import pytest

from app.schemas.odoo import OdooVendorBillDraft
from app.services.erp.odoo_connector import OdooConnector
from app.services.erp.base_connector import (
    ERPConnectionConfig,
    ERPEntity,
    ERPSyncDirection,
)


# =============================================================================
# Test Fixtures & Helpers
# =============================================================================


def _make_config(odoo_company_id=None):
    """Erstellt eine Test-Konfiguration (optional mit Odoo-Company-Id)."""
    return ERPConnectionConfig(
        id=uuid4(),
        company_id=uuid4(),
        erp_type="odoo",
        name="Test Odoo",
        url="https://odoo.example.com",
        database="testdb",
        username="admin",
        api_key="secret_api_key",
        sync_direction=ERPSyncDirection.BIDIRECTIONAL,
        max_requests_per_minute=60,
        batch_size=100,
        odoo_company_id=odoo_company_id,
    )


@pytest.fixture
def odoo_config():
    """Konfiguration OHNE odoo_company_id (heutiges Verhalten)."""
    return _make_config()


@pytest.fixture
def odoo_config_with_company():
    """Konfiguration MIT odoo_company_id (Multi-Company-Context)."""
    return _make_config(odoo_company_id=7)


@pytest.fixture
def mock_common_proxy():
    """Mock fuer den XML-RPC common-Proxy (Authentifizierung)."""
    mock = MagicMock()
    mock.authenticate.return_value = 1  # UID
    mock.version.return_value = {"server_version": "18.0"}
    return mock


@pytest.fixture
def mock_models_proxy():
    """Mock fuer den XML-RPC object/models-Proxy."""
    return MagicMock()


async def _connect(connector, mock_common_proxy, mock_models_proxy):
    """Verbindet den Connector gegen die gemockten Proxies."""
    with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
        mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
        assert await connector.connect() is True


def _rpc_calls(mock_models_proxy):
    """Extrahiert (model, method, args, kwargs) aus allen execute_kw-Calls.

    Der Connector ruft execute_kw positional auf:
    (db, uid, api_key, model, method, args, kwargs).
    """
    calls = []
    for call in mock_models_proxy.execute_kw.call_args_list:
        positional = call.args
        calls.append((positional[3], positional[4], positional[5], positional[6]))
    return calls


# =============================================================================
# Company-Context-Injektion (_execute_kw)
# =============================================================================


class TestCompanyContextInjection:
    """Tests fuer die Odoo-Multi-Company-Context-Injektion."""

    @pytest.mark.asyncio
    async def test_context_injected_with_company_id(
        self, odoo_config_with_company, mock_common_proxy, mock_models_proxy
    ):
        """Mit odoo_company_id wird der Company-Context injiziert."""
        connector = OdooConnector(odoo_config_with_company)
        mock_models_proxy.execute_kw.return_value = []
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        await connector._execute_kw(
            "res.partner", "search_read", [[]], {"fields": ["id"]}
        )

        _, _, _, rpc_kwargs = _rpc_calls(mock_models_proxy)[-1]
        assert rpc_kwargs == {
            "fields": ["id"],
            "context": {"allowed_company_ids": [7], "company_id": 7},
        }

    @pytest.mark.asyncio
    async def test_no_context_without_company_id(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Ohne odoo_company_id bleibt das kwargs-Dict unveraendert."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = []
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        await connector._execute_kw(
            "res.partner", "search_read", [[]], {"fields": ["id"]}
        )

        _, _, _, rpc_kwargs = _rpc_calls(mock_models_proxy)[-1]
        assert rpc_kwargs == {"fields": ["id"]}
        assert "context" not in rpc_kwargs

    @pytest.mark.asyncio
    async def test_existing_context_is_merged_not_overwritten(
        self, odoo_config_with_company, mock_common_proxy, mock_models_proxy
    ):
        """Vorhandener context des Aufrufers wird respektiert (Merge)."""
        connector = OdooConnector(odoo_config_with_company)
        mock_models_proxy.execute_kw.return_value = []
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        await connector._execute_kw(
            "res.partner",
            "search_read",
            [[]],
            {"fields": ["id"], "context": {"lang": "de_DE", "company_id": 99}},
        )

        _, _, _, rpc_kwargs = _rpc_calls(mock_models_proxy)[-1]
        # Aufrufer-Schluessel gewinnen; fehlende werden ergaenzt
        assert rpc_kwargs["context"] == {
            "lang": "de_DE",
            "company_id": 99,
            "allowed_company_ids": [7],
        }

    @pytest.mark.asyncio
    async def test_caller_kwargs_not_mutated(
        self, odoo_config_with_company, mock_common_proxy, mock_models_proxy
    ):
        """Das kwargs-Dict des Aufrufers wird nie in-place veraendert."""
        connector = OdooConnector(odoo_config_with_company)
        mock_models_proxy.execute_kw.return_value = []
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        caller_kwargs = {"fields": ["id"]}
        await connector._execute_kw("res.partner", "search_read", [[]], caller_kwargs)

        assert caller_kwargs == {"fields": ["id"]}


# =============================================================================
# iter_records (Pagination fuer den Spiegel-Sync)
# =============================================================================


class TestIterRecords:
    """Tests fuer die paginierte Iteration."""

    @pytest.mark.asyncio
    async def test_pagination_terminates_and_offset_grows(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Volle Batches -> offset waechst, leeres Batch beendet die Schleife."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = [
            [{"id": 1}, {"id": 2}],
            [{"id": 3}, {"id": 4}],
            [],
        ]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        records = [
            record
            async for record in connector.iter_records(
                "account.move", [], ["id"], batch_size=2
            )
        ]

        assert [r["id"] for r in records] == [1, 2, 3, 4]
        calls = _rpc_calls(mock_models_proxy)
        assert len(calls) == 3
        assert [c[3]["offset"] for c in calls] == [0, 2, 4]
        for model, method, _, rpc_kwargs in calls:
            assert model == "account.move"
            assert method == "search_read"
            assert rpc_kwargs["limit"] == 2
            assert rpc_kwargs["order"] == "write_date asc, id asc"

    @pytest.mark.asyncio
    async def test_partial_batch_terminates_without_extra_rpc(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Ein Teilbatch (< batch_size) beendet ohne weiteren RPC-Call."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = [[{"id": 1}]]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        records = [
            record
            async for record in connector.iter_records(
                "account.move", [], ["id"], batch_size=2
            )
        ]

        assert [r["id"] for r in records] == [1]
        assert len(_rpc_calls(mock_models_proxy)) == 1

    @pytest.mark.asyncio
    async def test_domain_and_custom_order_passed_through(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Domain und eigene Sortierung werden 1:1 durchgereicht."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = [[]]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        domain = [["move_type", "=", "in_invoice"]]
        _ = [
            record
            async for record in connector.iter_records(
                "account.move", domain, ["id", "name"], order="id desc"
            )
        ]

        _, _, rpc_args, rpc_kwargs = _rpc_calls(mock_models_proxy)[0]
        assert rpc_args == [domain]
        assert rpc_kwargs["order"] == "id desc"
        assert rpc_kwargs["fields"] == ["id", "name"]
        assert rpc_kwargs["limit"] == 200  # Default


# =============================================================================
# download_attachment
# =============================================================================


class TestDownloadAttachment:
    """Tests fuer den Attachment-Binaerdownload."""

    @pytest.mark.asyncio
    async def test_download_decodes_base64(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """datas wird base64-dekodiert; Metadaten kommen ohne datas zurueck."""
        connector = OdooConnector(odoo_config)
        pdf_bytes = b"%PDF-1.7 testinhalt"
        mock_models_proxy.execute_kw.return_value = [{
            "id": 55,
            "name": "rechnung.pdf",
            "mimetype": "application/pdf",
            "checksum": "abc123",
            "res_model": "account.move",
            "res_id": 42,
            "datas": base64.b64encode(pdf_bytes).decode("ascii"),
        }]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        result = await connector.download_attachment(55)

        assert result is not None
        content, metadata = result
        assert content == pdf_bytes
        assert "datas" not in metadata
        assert metadata["name"] == "rechnung.pdf"
        assert metadata["checksum"] == "abc123"
        assert metadata["res_model"] == "account.move"

        model, method, rpc_args, rpc_kwargs = _rpc_calls(mock_models_proxy)[-1]
        assert (model, method) == ("ir.attachment", "read")
        assert rpc_args == [[55]]
        assert "datas" in rpc_kwargs["fields"]

    @pytest.mark.asyncio
    async def test_download_false_datas_is_safe(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Odoo liefert False fuer leere Binaerfelder -> b'' statt Crash."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = [{
            "id": 56,
            "name": "url-anhang",
            "mimetype": "application/octet-stream",
            "checksum": False,
            "res_model": "account.move",
            "res_id": 42,
            "datas": False,
        }]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        result = await connector.download_attachment(56)

        assert result is not None
        content, metadata = result
        assert content == b""
        assert "datas" not in metadata

    @pytest.mark.asyncio
    async def test_download_not_found_returns_none(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Leeres read-Ergebnis -> None."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = []
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        assert await connector.download_attachment(999) is None

    @pytest.mark.asyncio
    async def test_download_error_returns_none(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """RPC-Fehler -> None (Fehlerbehandlung wie Bestand)."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = Exception("Read Error")
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        assert await connector.download_attachment(1) is None


# =============================================================================
# list_attachments (res_field-Falle)
# =============================================================================


class TestListAttachments:
    """Tests fuer die Attachment-Auflistung inkl. res_field-Zweig."""

    @pytest.mark.asyncio
    async def test_default_domain_without_res_field_term(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Standard: Domain OHNE res_field-Term (Odoo filtert implizit)."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = [{"id": 1, "name": "a.pdf"}]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        attachments = await connector.list_attachments("account.move", 5)

        assert len(attachments) == 1
        _, _, rpc_args, rpc_kwargs = _rpc_calls(mock_models_proxy)[-1]
        assert rpc_args == [[
            ["res_model", "=", "account.move"],
            ["res_id", "=", 5],
        ]]
        assert "checksum" in rpc_kwargs["fields"]

    @pytest.mark.asyncio
    async def test_include_field_attachments_uses_tautology_or_domain(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """res_field-Zweig: Tautologie-OR hebt Odoos impliziten Filter auf."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = []
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        await connector.list_attachments(
            "account.move", 5, include_field_attachments=True
        )

        _, _, rpc_args, _ = _rpc_calls(mock_models_proxy)[-1]
        assert rpc_args == [[
            "|",
            ["res_field", "=", False],
            ["res_field", "!=", False],
            ["res_model", "=", "account.move"],
            ["res_id", "=", 5],
        ]]

    @pytest.mark.asyncio
    async def test_error_returns_empty_list(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """RPC-Fehler -> leere Liste (Fehlerbehandlung wie Bestand)."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = Exception("Search Error")
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        assert await connector.list_attachments("account.move", 5) == []


# =============================================================================
# create_vendor_bill_draft
# =============================================================================


def _make_bill(**overrides):
    """Erstellt einen gueltigen OdooVendorBillDraft fuer Tests."""
    data = {
        "partner_id": 77,
        "invoice_date": date(2026, 8, 5),
        "ref": "RE-2026-0815",
        "amount_total_brutto": Decimal("123.455"),
        "line_name": "Eingangsrechnung RE-2026-0815 (Sammelzeile brutto)",
    }
    data.update(overrides)
    return OdooVendorBillDraft(**data)


class TestCreateVendorBillDraft:
    """Tests fuer den Entwurfs-Vendor-Bill-Push."""

    @pytest.mark.asyncio
    async def test_payload_form_and_float_rounding(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Payload: move_type/lines korrekt, Decimal kaufmaennisch -> float."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = 42
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        move_id = await connector.create_vendor_bill_draft(_make_bill())

        assert move_id == "42"
        model, method, rpc_args, _ = _rpc_calls(mock_models_proxy)[-1]
        assert (model, method) == ("account.move", "create")

        move_data = rpc_args[0]
        assert move_data["move_type"] == "in_invoice"
        assert move_data["partner_id"] == 77
        assert move_data["invoice_date"] == "2026-08-05"
        assert move_data["ref"] == "RE-2026-0815"
        # create = draft implizit; state darf NICHT gesetzt werden
        assert "state" not in move_data

        assert len(move_data["invoice_line_ids"]) == 1
        command = move_data["invoice_line_ids"][0]
        assert command[0] == 0 and command[1] == 0
        line = command[2]
        assert line["name"].startswith("Eingangsrechnung")
        assert line["quantity"] == 1.0
        # Decimal("123.455") -> ROUND_HALF_UP auf 2 Stellen -> 123.46 als float
        assert isinstance(line["price_unit"], float)
        assert line["price_unit"] == pytest.approx(123.46)

    @pytest.mark.asyncio
    async def test_narration_is_included_when_set(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Optionale Notiz landet als narration im Payload."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = 43
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        await connector.create_vendor_bill_draft(
            _make_bill(narration="Automatisch aus Ablage-System erzeugt")
        )

        _, _, rpc_args, _ = _rpc_calls(mock_models_proxy)[-1]
        assert rpc_args[0]["narration"] == "Automatisch aus Ablage-System erzeugt"

    @pytest.mark.asyncio
    async def test_pdf_attachment_path_sets_main_attachment(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """PDF-Pfad: attach_document + write auf message_main_attachment_id."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = [
            42,      # account.move create
            99,      # ir.attachment create (via attach_document)
            [99],    # ir.attachment search (juengstes Attachment)
            True,    # account.move write (message_main_attachment_id)
        ]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        pdf = b"%PDF-1.7 rechnung"
        move_id = await connector.create_vendor_bill_draft(
            _make_bill(), pdf_content=pdf, pdf_filename="re-2026-0815.pdf"
        )

        assert move_id == "42"
        calls = _rpc_calls(mock_models_proxy)
        assert [(c[0], c[1]) for c in calls] == [
            ("account.move", "create"),
            ("ir.attachment", "create"),
            ("ir.attachment", "search"),
            ("account.move", "write"),
        ]

        # attach_document-Payload
        attachment_data = calls[1][2][0]
        assert attachment_data["res_model"] == "account.move"
        assert attachment_data["res_id"] == 42
        assert attachment_data["name"] == "re-2026-0815.pdf"
        assert attachment_data["mimetype"] == "application/pdf"
        assert base64.b64decode(attachment_data["datas"]) == pdf

        # Suche nach juengstem Attachment
        assert calls[2][3] == {"order": "id desc", "limit": 1}

        # write setzt den Haupt-Anhang
        assert calls[3][2] == [[42], {"message_main_attachment_id": 99}]

    @pytest.mark.asyncio
    async def test_create_error_returns_none(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Fehler beim create -> None (Fehlerbehandlung wie Bestand)."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = Exception("Create Error")
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        assert await connector.create_vendor_bill_draft(_make_bill()) is None

    @pytest.mark.asyncio
    async def test_attachment_failure_is_not_fatal(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Attachment-Fehler ist nicht fatal: move_id kommt trotzdem zurueck."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = [
            42,
            Exception("Attachment Error"),  # attach_document faengt intern
        ]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        move_id = await connector.create_vendor_bill_draft(
            _make_bill(), pdf_content=b"%PDF-1.7"
        )

        assert move_id == "42"
        # Nach dem Attachment-Fehler folgt kein search/write mehr
        assert len(_rpc_calls(mock_models_proxy)) == 2


# =============================================================================
# find_partner (Matching-Kaskade)
# =============================================================================


class TestFindPartner:
    """Tests fuer die Partner-Matching-Kaskade."""

    @pytest.mark.asyncio
    async def test_vat_hit_stops_cascade(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """VAT-Treffer (Stufe 1) beendet die Kaskade; Name wird nie gesucht."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = [
            {"id": 1, "name": "ACME GmbH", "vat": "DE123456789"},
        ]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        partners = await connector.find_partner(
            vat=" de 123456789 ", name="ACME"
        )

        assert len(partners) == 1
        assert partners[0]["match_source"] == "vat"
        calls = _rpc_calls(mock_models_proxy)
        assert len(calls) == 1
        model, method, rpc_args, _ = calls[0]
        assert (model, method) == ("res.partner", "search_read")
        # Normalisierung: Leerzeichen raus, upper
        assert rpc_args == [[["vat", "=ilike", "DE123456789"]]]

    @pytest.mark.asyncio
    async def test_iban_normalization_and_partner_resolution(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """IBAN wird normalisiert; partner_id-Aufloesung dedupliziert."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = [
            # res.partner.bank search_read: 2 Konten desselben Partners
            [
                {"id": 11, "partner_id": [5, "ACME GmbH"]},
                {"id": 12, "partner_id": [5, "ACME GmbH"]},
            ],
            # res.partner read
            [{"id": 5, "name": "ACME GmbH", "supplier_rank": 3}],
        ]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        partners = await connector.find_partner(iban="de12 3456-7890")

        assert len(partners) == 1
        assert partners[0]["id"] == 5
        assert partners[0]["match_source"] == "iban"

        calls = _rpc_calls(mock_models_proxy)
        assert len(calls) == 2
        bank_model, _, bank_args, _ = calls[0]
        assert bank_model == "res.partner.bank"
        # Normalisierung: nur Alphanumerik, upper
        assert bank_args == [[["sanitized_acc_number", "=", "DE1234567890"]]]

        read_model, read_method, read_args, _ = calls[1]
        assert (read_model, read_method) == ("res.partner", "read")
        assert read_args == [[5]]  # dedupliziert

    @pytest.mark.asyncio
    async def test_ref_after_empty_vat_search(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Leere VAT-Suche -> naechste Stufe (ref) liefert den Treffer."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = [
            [],  # vat-Suche leer
            [{"id": 3, "name": "Lieferant X", "ref": "70001"}],  # ref-Treffer
        ]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        partners = await connector.find_partner(
            vat="DE000000000", supplier_ref="70001"
        )

        assert len(partners) == 1
        assert partners[0]["match_source"] == "ref"
        calls = _rpc_calls(mock_models_proxy)
        assert len(calls) == 2
        assert calls[1][2] == [[["ref", "=", "70001"]]]

    @pytest.mark.asyncio
    async def test_name_fallback_filters_suppliers_with_limit(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Name-Fallback: ilike + supplier_rank>0-Filter + limit 5."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.return_value = [
            {"id": 8, "name": "Mueller Werkzeuge", "supplier_rank": 1},
        ]
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        partners = await connector.find_partner(name="Mueller")

        assert partners[0]["match_source"] == "name"
        _, _, rpc_args, rpc_kwargs = _rpc_calls(mock_models_proxy)[-1]
        assert rpc_args == [[
            ["name", "ilike", "Mueller"],
            ["supplier_rank", ">", 0],
        ]]
        assert rpc_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_no_criteria_returns_empty_without_rpc(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """Ohne Suchkriterien: leeres Ergebnis, kein einziger RPC-Call."""
        connector = OdooConnector(odoo_config)
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        assert await connector.find_partner() == []
        assert len(_rpc_calls(mock_models_proxy)) == 0

    @pytest.mark.asyncio
    async def test_error_returns_empty_list(
        self, odoo_config, mock_common_proxy, mock_models_proxy
    ):
        """RPC-Fehler -> leere Liste (Fehlerbehandlung wie Bestand)."""
        connector = OdooConnector(odoo_config)
        mock_models_proxy.execute_kw.side_effect = Exception("Search Error")
        await _connect(connector, mock_common_proxy, mock_models_proxy)

        assert await connector.find_partner(vat="DE123456789") == []
