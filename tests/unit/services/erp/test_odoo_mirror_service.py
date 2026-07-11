"""Tests fuer den OdooMirrorService (Odoo->Ablage Vollarchiv-Spiegel, Phase 3).

Abgedeckt (alles gemockt, KEINE echten Odoo-Calls, keine echte DB):
- Domain-Aufbau: move_types, state != draft, Cursor inkl. 5-min-Overlap
- Draft-Guard: Entwuerfe werden uebersprungen
- Dedupe dreistufig: (a) ERPEntityMapping, (b) SHA256/checksum, (c) Neuanlage
- Fehler-Isolation: ein kaputter Move stoppt nicht den Batch
- Cursor-Fortschreibung: nur bis zum letzten Erfolg VOR dem ersten Fehler
- consecutive_failures-Pflege + is_paused-Flag
- Company-Context-Guard (sync_state / Setting-Fallback / Skip ohne ID)
- Kategorie-/Dokumenttyp-Mapping out/in bzw. refund
- Persistenz-Pfad: StorageService.upload_document -> Document -> GoBD-Archiv

Mock-Muster wie tests/unit/services/erp/test_odoo_connector_extensions.py
(hier eine Ebene hoeher: Connector + DB-Session als Mocks/Fakes).
"""

from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.db.models import ERPConnection, OdooSyncStatus
from app.services.erp.odoo_mirror_service import (
    MIRROR_DATA_TYPE,
    MIRROR_MOVE_TYPES,
    MirrorRunResult,
    OdooMirrorService,
)


# =============================================================================
# Fixtures & Helpers
# =============================================================================


def _make_connection() -> ERPConnection:
    """ERPConnection-ORM-Instanz ohne DB (Spalten explizit gesetzt)."""
    return ERPConnection(
        id=uuid4(),
        company_id=uuid4(),
        erp_type="odoo",
        name="Odoo Spargelmesser",
        url="https://odoo.example.com",
        username="ablage-integration",
        encrypted_api_key="enc",
        is_active=True,
        created_by=None,
    )


def _make_sync_status(
    connection: ERPConnection,
    *,
    cursor: Optional[str] = None,
    odoo_company_id: Optional[int] = 2,
    consecutive_failures: int = 0,
) -> OdooSyncStatus:
    """OdooSyncStatus-ORM-Instanz ohne DB (Defaults greifen nicht -> explizit)."""
    state: Dict[str, Any] = {}
    if odoo_company_id is not None:
        state["odoo_company_id"] = odoo_company_id
    return OdooSyncStatus(
        id=uuid4(),
        connection_id=connection.id,
        data_type=MIRROR_DATA_TYPE,
        last_sync_cursor=cursor,
        sync_state=state,
        total_records_synced=0,
        records_synced_today=0,
        consecutive_failures=consecutive_failures,
        is_paused=False,
    )


def _make_db() -> MagicMock:
    """Async-Session-Mock: add sync, Rest AsyncMock."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    return db


def _move(
    move_id: int,
    *,
    write_date: str,
    state: str = "posted",
    move_type: str = "out_invoice",
    partner: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """account.move-Datensatz wie von search_read geliefert."""
    return {
        "id": move_id,
        "name": f"INV/2026/{move_id:04d}",
        "move_type": move_type,
        "partner_id": partner if partner is not None else [5, "ACME GmbH"],
        "invoice_date": "2026-08-05",
        "ref": f"RE-{move_id}",
        "amount_total": 119.0,
        "currency_id": [1, "EUR"],
        "write_date": write_date,
        "state": state,
    }


class FakeConnector:
    """Connector-Fake: iter_records aus Liste, Rest AsyncMock (keine RPC-Calls)."""

    def __init__(self, moves: Optional[List[Dict[str, Any]]] = None) -> None:
        self.moves = moves or []
        self.iter_calls: List[Tuple[str, List[Any], List[str], int, str]] = []
        self.list_attachments = AsyncMock(return_value=[])
        self.download_attachment = AsyncMock(return_value=None)
        self.disconnect = AsyncMock()

    async def iter_records(
        self,
        model: str,
        domain: List[Any],
        fields: List[str],
        *,
        batch_size: int = 200,
        order: str = "write_date asc, id asc",
    ):
        self.iter_calls.append((model, domain, fields, batch_size, order))
        for move in self.moves:
            yield move


@pytest.fixture
def service() -> OdooMirrorService:
    return OdooMirrorService()


@pytest.fixture
def connection() -> ERPConnection:
    return _make_connection()


@pytest.fixture
def db() -> MagicMock:
    return _make_db()


def _patch_status(service: OdooMirrorService, sync_status: OdooSyncStatus):
    """Patcht das get_or_create der Status-Zeile auf ein fertiges Objekt."""
    return patch.object(
        service, "_get_or_create_sync_status", AsyncMock(return_value=sync_status)
    )


# =============================================================================
# Domain & Cursor
# =============================================================================


class TestDomainUndCursor:
    """Domain-Aufbau inkl. Overlap-Fenster."""

    @pytest.mark.asyncio
    async def test_domain_without_cursor(self, service, connection, db):
        """Erster Lauf (Cursor None): move_types + state!=draft, KEIN write_date."""
        sync_status = _make_sync_status(connection, cursor=None)
        connector = FakeConnector(moves=[])

        with _patch_status(service, sync_status):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 0
        assert len(connector.iter_calls) == 1
        model, domain, fields, batch_size, order = connector.iter_calls[0]
        assert model == "account.move"
        assert ["move_type", "in", list(MIRROR_MOVE_TYPES)] in domain
        assert ["state", "!=", "draft"] in domain
        assert not any(term[0] == "write_date" for term in domain if isinstance(term, list))
        assert order == "write_date asc, id asc"
        assert "write_date" in fields and "state" in fields

    @pytest.mark.asyncio
    async def test_cursor_gets_five_minute_overlap(self, service, connection, db):
        """Cursor vorhanden: write_date-Filter = Cursor MINUS 5 Minuten."""
        sync_status = _make_sync_status(connection, cursor="2026-08-10 10:00:00")
        connector = FakeConnector(moves=[])

        with _patch_status(service, sync_status):
            await service.run_incremental(db, connection, connector=connector)

        _, domain, _, _, _ = connector.iter_calls[0]
        assert ["write_date", ">=", "2026-08-10 09:55:00"] in domain

    @pytest.mark.asyncio
    async def test_unparseable_cursor_bricht_ab_statt_full_scan(
        self, service, connection, db
    ):
        """F-05 (Review-P2): Korrupter Cursor -> Fehler + KEIN Voll-Scan.

        Frueher fiel der Lauf STILL auf einen Scan der gesamten Odoo-Historie
        zurueck (1 Attachment-RPC je Move -> SaaS-Drosselung, Risiko R2).
        Ein gesetzter, aber unparsebarer Cursor ist ein Datenfehler: Abbruch
        mit klarem Fehler, Cursor bleibt unveraendert, kein einziger RPC.
        """
        sync_status = _make_sync_status(connection, cursor="nicht-parsebar")
        connector = FakeConnector(moves=[])

        with _patch_status(service, sync_status):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 1
        assert result.fetched == 0
        assert connector.iter_calls == []
        assert result.new_cursor == "nicht-parsebar"


# =============================================================================
# Company-Context-Guard
# =============================================================================


class TestCompanyContextGuard:
    """Ohne aufloesbare odoo_company_id laeuft der Spiegel NICHT."""

    @pytest.mark.asyncio
    async def test_skip_without_odoo_company_id(
        self, service, connection, db, monkeypatch
    ):
        """sync_state leer + Setting None -> Lauf uebersprungen, kein RPC."""
        monkeypatch.setattr(
            "app.services.erp.odoo_mirror_service.settings",
            SimpleNamespace(ODOO_MIRROR_COMPANY_ID=None, ODOO_MIRROR_USE_TSA=False),
        )
        sync_status = _make_sync_status(connection, odoo_company_id=None)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])

        with _patch_status(service, sync_status):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result == MirrorRunResult(fetched=0, created=0, skipped_duplicates=0, errors=0)
        assert connector.iter_calls == []
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_setting_fallback_enables_run(
        self, service, connection, db, monkeypatch
    ):
        """sync_state leer, aber Setting gesetzt -> Lauf findet statt."""
        monkeypatch.setattr(
            "app.services.erp.odoo_mirror_service.settings",
            SimpleNamespace(ODOO_MIRROR_COMPANY_ID=2, ODOO_MIRROR_USE_TSA=False),
        )
        sync_status = _make_sync_status(connection, odoo_company_id=None)
        connector = FakeConnector(moves=[])

        with _patch_status(service, sync_status):
            await service.run_incremental(db, connection, connector=connector)

        assert len(connector.iter_calls) == 1


# =============================================================================
# Draft-Guard & Dedupe
# =============================================================================


class TestDraftUndDedupe:
    """Draft-Skip und die drei Dedupe-Stufen."""

    @pytest.mark.asyncio
    async def test_draft_move_is_skipped(self, service, connection, db):
        """Entwuerfe (state=draft) werden nicht gespiegelt (defensiver Guard)."""
        sync_status = _make_sync_status(connection)
        connector = FakeConnector(
            moves=[_move(1, write_date="2026-08-10 10:00:00", state="draft")]
        )

        with _patch_status(service, sync_status):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.fetched == 1
        assert result.created == 0
        assert result.errors == 0
        connector.list_attachments.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedupe_stage_a_mapping_exists_skips_download(
        self, service, connection, db
    ):
        """Stufe (a): Mapping vorhanden -> skip OHNE Download."""
        sync_status = _make_sync_status(connection)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])
        connector.list_attachments.return_value = [{"id": 501, "name": "a.pdf"}]

        with _patch_status(service, sync_status), \
                patch.object(service, "_mapping_exists", AsyncMock(return_value=True)), \
                patch.object(service, "_persist_attachment", AsyncMock()) as persist:
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.skipped_duplicates == 1
        assert result.created == 0
        connector.download_attachment.assert_not_awaited()
        persist.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedupe_stage_b_checksum_match_maps_without_new_document(
        self, service, connection, db
    ):
        """Stufe (b): gleicher SHA256 -> nur Mapping, KEIN neues Dokument."""
        sync_status = _make_sync_status(connection)
        existing_document_id = uuid4()
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])
        connector.list_attachments.return_value = [{"id": 501, "name": "a.pdf"}]
        connector.download_attachment.return_value = (
            b"%PDF-1.7 inhalt",
            # checksum = echter SHA-1 von b"%PDF-1.7 inhalt" (GoBD-Integritaetsgate)
            {
                "name": "a.pdf",
                "mimetype": "application/pdf",
                "checksum": "6d972887c8e83c01f21c23f3723e695b9a02a71e",
            },
        )

        with _patch_status(service, sync_status), \
                patch.object(service, "_mapping_exists", AsyncMock(return_value=False)), \
                patch.object(
                    service,
                    "_find_document_by_checksum",
                    AsyncMock(return_value=existing_document_id),
                ) as find_by_checksum, \
                patch.object(service, "_store_mapping", AsyncMock()) as store_mapping, \
                patch.object(service, "_persist_attachment", AsyncMock()) as persist:
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.skipped_duplicates == 1
        assert result.created == 0
        persist.assert_not_awaited()
        find_by_checksum.assert_awaited_once()
        store_mapping.assert_awaited_once()
        assert store_mapping.await_args.kwargs["document_id"] == existing_document_id
        assert store_mapping.await_args.kwargs["attachment_id"] == 501

    @pytest.mark.asyncio
    async def test_new_attachment_is_persisted(self, service, connection, db):
        """Stufe (c): unbekannter Inhalt -> Neuanlage (nie ueberschreiben)."""
        sync_status = _make_sync_status(connection)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])
        connector.list_attachments.return_value = [{"id": 501, "name": "a.pdf"}]
        connector.download_attachment.return_value = (
            b"%PDF-1.7 inhalt",
            # checksum = echter SHA-1 von b"%PDF-1.7 inhalt" (GoBD-Integritaetsgate)
            {
                "name": "a.pdf",
                "mimetype": "application/pdf",
                "checksum": "6d972887c8e83c01f21c23f3723e695b9a02a71e",
            },
        )

        with _patch_status(service, sync_status), \
                patch.object(service, "_mapping_exists", AsyncMock(return_value=False)), \
                patch.object(
                    service, "_find_document_by_checksum", AsyncMock(return_value=None)
                ), \
                patch.object(
                    service, "_persist_attachment", AsyncMock(return_value=uuid4())
                ) as persist:
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.created == 1
        assert result.skipped_duplicates == 0
        assert result.errors == 0
        persist.assert_awaited_once()
        # Attachment-Listing MUSS Binaerfeld-Attachments einschliessen
        # (gerenderte Rechnungs-PDFs liegen mit res_field gesetzt).
        assert (
            connector.list_attachments.await_args.kwargs["include_field_attachments"]
            is True
        )

    @pytest.mark.asyncio
    async def test_empty_attachment_content_is_skipped_without_error(
        self, service, connection, db
    ):
        """Leere Binaerfelder (b'') sind kein Fehler und kein Duplikat."""
        sync_status = _make_sync_status(connection)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])
        connector.list_attachments.return_value = [{"id": 501, "name": "url-anhang"}]
        connector.download_attachment.return_value = (b"", {"name": "url-anhang"})

        with _patch_status(service, sync_status), \
                patch.object(service, "_mapping_exists", AsyncMock(return_value=False)), \
                patch.object(service, "_persist_attachment", AsyncMock()) as persist:
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 0
        assert result.created == 0
        assert result.skipped_duplicates == 0
        persist.assert_not_awaited()
        # Erfolgreicher Move -> Cursor schreitet fort
        assert result.new_cursor == "2026-08-10 10:00:00"

    @pytest.mark.asyncio
    async def test_failed_download_marks_move_as_error(self, service, connection, db):
        """download_attachment None -> Move-Fehler (Cursor-Schutz)."""
        sync_status = _make_sync_status(connection)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])
        connector.list_attachments.return_value = [{"id": 501, "name": "a.pdf"}]
        connector.download_attachment.return_value = None

        with _patch_status(service, sync_status), \
                patch.object(service, "_mapping_exists", AsyncMock(return_value=False)):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 1
        assert result.created == 0
        # Cursor darf NICHT auf den kaputten Move fortschreiten
        assert result.new_cursor is None
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_checksum_mismatch_blocks_gobd_archival(
        self, service, connection, db
    ):
        """GoBD-Integritaetsgate (R3): Odoo-checksum (SHA-1) != Bytes -> Move-Fehler.

        Ein still-korrupter Transfer (Bytes stimmen nicht mit dem von Odoo
        gemeldeten ir.attachment.checksum ueberein) darf NICHT mit einem
        gueltig aussehenden GoBD-Hash der korrupten Bytes archiviert werden.
        Erwartung: RuntimeError -> per-Move-Rollback, Cursor-Schutz, KEINE
        Persistenz.
        """
        sync_status = _make_sync_status(connection)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])
        connector.list_attachments.return_value = [{"id": 501, "name": "a.pdf"}]
        # Inhalt b"%PDF-1.7 inhalt", aber Odoo meldet einen FREMDEN Checksum:
        connector.download_attachment.return_value = (
            b"%PDF-1.7 inhalt",
            {
                "name": "a.pdf",
                "mimetype": "application/pdf",
                "checksum": "0000000000000000000000000000000000000000",
            },
        )

        with _patch_status(service, sync_status), \
                patch.object(service, "_mapping_exists", AsyncMock(return_value=False)), \
                patch.object(
                    service, "_find_document_by_checksum", AsyncMock(return_value=None)
                ) as find_by_checksum, \
                patch.object(service, "_persist_attachment", AsyncMock()) as persist:
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 1
        assert result.created == 0
        # Gate schlaegt VOR Dedupe/Persistenz zu:
        find_by_checksum.assert_not_awaited()
        persist.assert_not_awaited()
        # Cursor darf NICHT fortschreiten -> naechster Lauf laedt erneut
        assert result.new_cursor is None
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_matching_checksum_passes_gate(self, service, connection, db):
        """Gegenprobe: passender SHA-1 -> Move laeuft normal in die Persistenz."""
        sync_status = _make_sync_status(connection)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])
        connector.list_attachments.return_value = [{"id": 501, "name": "a.pdf"}]
        connector.download_attachment.return_value = (
            b"%PDF-1.7 inhalt",
            {
                "name": "a.pdf",
                "mimetype": "application/pdf",
                "checksum": "6d972887c8e83c01f21c23f3723e695b9a02a71e",
            },
        )

        with _patch_status(service, sync_status), \
                patch.object(service, "_mapping_exists", AsyncMock(return_value=False)), \
                patch.object(
                    service, "_find_document_by_checksum", AsyncMock(return_value=None)
                ), \
                patch.object(
                    service, "_persist_attachment", AsyncMock(return_value=uuid4())
                ) as persist:
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 0
        assert result.created == 1
        persist.assert_awaited_once()


# =============================================================================
# Fehler-Isolation & Cursor-Fortschreibung
# =============================================================================


class TestFehlerIsolationUndCursor:
    """Batch-Robustheit und Cursor-Semantik."""

    @pytest.mark.asyncio
    async def test_error_in_one_move_does_not_stop_batch(
        self, service, connection, db
    ):
        """Move 2 kaputt -> Move 3 wird trotzdem verarbeitet."""
        sync_status = _make_sync_status(connection)
        moves = [
            _move(1, write_date="2026-08-10 10:00:00"),
            _move(2, write_date="2026-08-10 10:05:00"),
            _move(3, write_date="2026-08-10 10:10:00"),
        ]
        connector = FakeConnector(moves=moves)
        mirror_move = AsyncMock(
            side_effect=[(1, 0), RuntimeError("Odoo-Fehler"), (1, 0)]
        )

        with _patch_status(service, sync_status), \
                patch.object(service, "_mirror_move", mirror_move):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.fetched == 3
        assert result.created == 2
        assert result.errors == 1
        assert mirror_move.await_count == 3
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cursor_stops_before_first_error(self, service, connection, db):
        """Cursor = write_date des letzten Erfolgs VOR dem ersten Fehler."""
        sync_status = _make_sync_status(connection)
        moves = [
            _move(1, write_date="2026-08-10 10:00:00"),
            _move(2, write_date="2026-08-10 10:05:00"),
            _move(3, write_date="2026-08-10 10:10:00"),
        ]
        connector = FakeConnector(moves=moves)
        mirror_move = AsyncMock(
            side_effect=[(1, 0), RuntimeError("Odoo-Fehler"), (1, 0)]
        )

        with _patch_status(service, sync_status), \
                patch.object(service, "_mirror_move", mirror_move):
            result = await service.run_incremental(db, connection, connector=connector)

        # NICHT 10:10:00 - sonst ginge Move 2 verloren
        assert result.new_cursor == "2026-08-10 10:00:00"
        assert sync_status.last_sync_cursor == "2026-08-10 10:00:00"
        assert sync_status.consecutive_failures == 1
        assert sync_status.last_error is not None

    @pytest.mark.asyncio
    async def test_cursor_advances_on_full_success(self, service, connection, db):
        """Fehlerfreier Batch: Cursor = letzter Move, Failure-Zaehler resettet."""
        sync_status = _make_sync_status(connection, consecutive_failures=3)
        moves = [
            _move(1, write_date="2026-08-10 10:00:00"),
            _move(2, write_date="2026-08-10 10:05:00"),
        ]
        connector = FakeConnector(moves=moves)

        with _patch_status(service, sync_status), \
                patch.object(service, "_mirror_move", AsyncMock(return_value=(1, 0))):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 0
        assert result.new_cursor == "2026-08-10 10:05:00"
        assert sync_status.last_sync_cursor == "2026-08-10 10:05:00"
        assert sync_status.consecutive_failures == 0
        assert sync_status.last_error is None
        assert sync_status.is_paused is False
        assert sync_status.total_records_synced == 2
        assert sync_status.sync_state["last_run"]["created"] == 2

    @pytest.mark.asyncio
    async def test_consecutive_failures_set_pause_flag(self, service, connection, db):
        """5. Fehl-Lauf in Folge -> is_paused (Monitoring-Flag, kein Gate)."""
        sync_status = _make_sync_status(connection, consecutive_failures=4)
        connector = FakeConnector(moves=[_move(1, write_date="2026-08-10 10:00:00")])

        with _patch_status(service, sync_status), \
                patch.object(
                    service, "_mirror_move", AsyncMock(side_effect=RuntimeError("kaputt"))
                ):
            result = await service.run_incremental(db, connection, connector=connector)

        assert result.errors == 1
        assert sync_status.consecutive_failures == 5
        assert sync_status.is_paused is True

    @pytest.mark.asyncio
    async def test_batch_limit_caps_processed_moves(self, service, connection, db):
        """batch_limit begrenzt die pro Lauf verarbeiteten Moves (R2)."""
        sync_status = _make_sync_status(connection)
        moves = [
            _move(i, write_date=f"2026-08-10 10:0{i}:00") for i in range(1, 4)
        ]
        connector = FakeConnector(moves=moves)
        mirror_move = AsyncMock(return_value=(1, 0))

        with _patch_status(service, sync_status), \
                patch.object(service, "_mirror_move", mirror_move):
            result = await service.run_incremental(
                db, connection, batch_limit=2, connector=connector
            )

        assert result.fetched == 2
        assert mirror_move.await_count == 2
        # Cursor steht auf dem letzten verarbeiteten (nicht letzten gelisteten)
        assert result.new_cursor == "2026-08-10 10:02:00"


# =============================================================================
# Kategorie-/Dokumenttyp-Mapping
# =============================================================================


class TestKategorieMapping:
    """out_* -> invoice_outgoing, in_* -> invoice_incoming (RetentionService)."""

    @pytest.mark.parametrize(
        ("move_type", "expected_category"),
        [
            ("out_invoice", "invoice_outgoing"),
            ("out_refund", "invoice_outgoing"),
            ("in_invoice", "invoice_incoming"),
            ("in_refund", "invoice_incoming"),
        ],
    )
    def test_category_for_move_type(self, move_type, expected_category):
        assert OdooMirrorService.category_for_move_type(move_type) == expected_category

    @pytest.mark.parametrize(
        ("move_type", "expected_type"),
        [
            ("out_invoice", "invoice"),
            ("in_invoice", "invoice"),
            ("out_refund", "credit_note"),
            ("in_refund", "credit_note"),
        ],
    )
    def test_document_type_for_move_type(self, move_type, expected_type):
        assert (
            OdooMirrorService.document_type_for_move_type(move_type) == expected_type
        )


# =============================================================================
# Persistenz-Pfad (_persist_attachment)
# =============================================================================


class TestPersistAttachment:
    """StorageService-Upload -> Document -> GoBD-Einbuchung -> Mapping."""

    @pytest.mark.asyncio
    async def test_persist_uploads_creates_document_and_archives(
        self, service, connection, db, monkeypatch
    ):
        """Kompletter Anlage-Pfad inkl. use_tsa-Durchreichung aus Settings."""
        monkeypatch.setattr(
            "app.services.erp.odoo_mirror_service.settings",
            SimpleNamespace(ODOO_MIRROR_COMPANY_ID=2, ODOO_MIRROR_USE_TSA=True),
        )
        content = b"%PDF-1.7 rechnung"
        sha256 = "f" * 64
        move = _move(7, write_date="2026-08-10 10:00:00", move_type="out_invoice")
        attachment_meta = {
            "name": "INV_2026_0007.pdf",
            "mimetype": "application/pdf",
            "checksum": "sha1abc",
        }

        storage_instance = MagicMock()
        storage_instance.upload_document = AsyncMock(
            return_value={"storage_path": "anon/ffff.pdf", "success": True}
        )
        archive_instance = MagicMock()
        archive_instance.archive_document = AsyncMock()
        entity_id = uuid4()

        with patch(
            "app.services.storage_service.StorageService",
            return_value=storage_instance,
        ), patch(
            "app.services.compliance.archive_service.GoBDArchiveService",
            return_value=archive_instance,
        ), patch.object(
            service, "_resolve_partner_entity", AsyncMock(return_value=entity_id)
        ), patch.object(
            service, "_store_mapping", AsyncMock()
        ) as store_mapping, patch.object(
            OdooMirrorService,
            "_extract_pdf_text_layer",
            MagicMock(return_value="Rechnung 119,00 EUR"),
        ):
            document_id = await service._persist_attachment(
                db,
                connection=connection,
                move=move,
                attachment_id=501,
                attachment_meta=attachment_meta,
                content=content,
                sha256=sha256,
            )

        assert isinstance(document_id, UUID)

        # Storage: derselbe Upload-Weg wie Upload-API/Folder-Import
        upload_kwargs = storage_instance.upload_document.await_args.kwargs
        assert upload_kwargs["file_data"] == content
        assert upload_kwargs["filename"] == "INV_2026_0007.pdf"
        assert upload_kwargs["content_type"] == "application/pdf"

        # Document-Zeile
        document = db.add.call_args_list[0].args[0]
        assert document.company_id == connection.company_id
        assert document.checksum == sha256
        assert document.document_type == "invoice"
        assert document.status == "uploaded"
        assert document.business_entity_id == entity_id
        assert document.extracted_text == "Rechnung 119,00 EUR"
        assert document.document_metadata["import_source"] == "odoo_mirror"
        assert document.document_metadata["odoo_model"] == "account.move"
        assert document.document_metadata["odoo_id"] == 7
        assert document.document_metadata["odoo_move_type"] == "out_invoice"
        assert document.document_metadata["odoo_checksum"] == "sha1abc"
        assert document.document_metadata["auto_ocr"] is False

        # GoBD-Einbuchung
        archive_kwargs = archive_instance.archive_document.await_args.kwargs
        assert archive_kwargs["company_id"] == connection.company_id
        assert archive_kwargs["category"] == "invoice_outgoing"
        assert archive_kwargs["document_content"] == content
        assert archive_kwargs["document_date"] == date(2026, 8, 5)
        assert archive_kwargs["use_tsa"] is True

        # Mapping (Idempotenz-Anker Stufe a)
        assert store_mapping.await_args.kwargs["attachment_id"] == 501
        assert store_mapping.await_args.kwargs["sha256"] == sha256

    @pytest.mark.asyncio
    async def test_persist_non_pdf_skips_text_extraction(
        self, service, connection, db, monkeypatch
    ):
        """Nicht-PDF: keine Textlayer-Extraktion, extracted_text bleibt leer."""
        monkeypatch.setattr(
            "app.services.erp.odoo_mirror_service.settings",
            SimpleNamespace(ODOO_MIRROR_COMPANY_ID=2, ODOO_MIRROR_USE_TSA=False),
        )
        move = _move(8, write_date="2026-08-10 10:00:00", move_type="in_invoice")

        storage_instance = MagicMock()
        storage_instance.upload_document = AsyncMock(
            return_value={"storage_path": "anon/bild.png", "success": True}
        )
        archive_instance = MagicMock()
        archive_instance.archive_document = AsyncMock()

        with patch(
            "app.services.storage_service.StorageService",
            return_value=storage_instance,
        ), patch(
            "app.services.compliance.archive_service.GoBDArchiveService",
            return_value=archive_instance,
        ), patch.object(
            service, "_resolve_partner_entity", AsyncMock(return_value=None)
        ), patch.object(
            service, "_store_mapping", AsyncMock()
        ), patch.object(
            OdooMirrorService, "_extract_pdf_text_layer", MagicMock()
        ) as extract:
            await service._persist_attachment(
                db,
                connection=connection,
                move=move,
                attachment_id=502,
                attachment_meta={"name": "scan.png", "mimetype": "image/png"},
                content=b"\x89PNG...",
                sha256="a" * 64,
            )

        extract.assert_not_called()
        document = db.add.call_args_list[0].args[0]
        assert document.extracted_text is None
        assert document.business_entity_id is None
        # Eingangsseite -> invoice_incoming
        archive_kwargs = archive_instance.archive_document.await_args.kwargs
        assert archive_kwargs["category"] == "invoice_incoming"
        assert archive_kwargs["use_tsa"] is False
