"""Odoo -> Ablage Vollarchiv-Pull-Spiegel (Neuausrichtung Phase 3, Plan §4c.2).

Spiegelt jeden gebuchten Odoo-Beleg (account.move: out_invoice, in_invoice,
out_refund, in_refund) samt Anhaengen als hash-gesicherte GoBD-Zweitablage
ins Ablage-System:

- Cursor-Sync auf write_date (asc, id asc als Tiebreaker) mit 5-Minuten-
  Overlap-Fenster; Cursor lebt in OdooSyncStatus (data_type
  "mirror_account_move", ein Eintrag je ERP-Verbindung).
- Dreistufiges Dedupe: (a) ERPEntityMapping (entity_type "mirror_attachment",
  remote_id = ir.attachment-ID), (b) SHA256 gegen Document.checksum je
  Company, (c) niemals ueberschreiben - eine geaenderte Odoo-Version wird
  als NEUES Dokument gespiegelt (neuer Hash => neue Zeile, GoBD-konform).
- Persistenz ueber denselben Weg wie Upload-/Folder-Import:
  StorageService.upload_document -> Document-Zeile -> GoBD-Einbuchung via
  GoBDArchiveService.archive_document (Retention nach Kategorie).
- Fehler werden PRO MOVE isoliert (ein kaputter Beleg stoppt nicht den
  Batch); der Cursor wird nur bis zum letzten erfolgreich verarbeiteten
  Move VOR dem ersten Fehler fortgeschrieben, damit kein Beleg verloren
  geht (fehlgeschlagene Moves kommen im naechsten Lauf erneut).

Architektur-Entscheidungen (E2-nah, dokumentiert):
- state != "draft": Entwuerfe sind fluechtig (werden in Odoo editiert/
  verworfen) und noch keine Belege im GoBD-Sinn. Gespiegelt wird erst ab
  Buchung (posted) bzw. Storno (cancel bleibt sichtbar, der Beleg existierte).
  Beim Posten bumpt Odoo write_date, der Beleg faellt also sicher in ein
  spaeteres Cursor-Fenster.
- Kategorien: out_* -> "invoice_outgoing", in_* -> "invoice_incoming"
  (beide im RetentionService definiert: 10 Jahre, §147 AO / §14b UStG).
- auto_ocr=False: Odoo-PDFs haben i.d.R. einen Textlayer; Text wird
  best-effort via pypdfium2 (Repo-Standard, s. classification_agent)
  extrahiert, sonst leer gelassen (der Embedding-Beat greift spaeter).
- Odoo-Company-Context ist PFLICHT (Multi-Company-Sicherheit): ohne
  aufloesbare odoo_company_id (sync_state["odoo_company_id"] der
  Status-Zeile oder Setting ODOO_MIRROR_COMPANY_ID) wird der Lauf
  uebersprungen - sonst wuerden Belege fremder Odoo-Companies gespiegelt.
- is_paused wird analog zum Bestands-Muster ab 5 consecutive_failures
  gesetzt, dient aber nur Monitoring/Anzeige und gated den Lauf NICHT
  (kein Selbst-Deadlock; Alarmierung uebernimmt der Beat-Task).

KEINE echten Odoo-Calls in Tests - alles laeuft gegen den (mockbaren)
injizierten Connector.
"""

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import Document, ERPConnection, ERPEntityMapping, OdooSyncStatus
from app.services.erp.odoo_connector import OdooConnector

logger = structlog.get_logger(__name__)


# Sync-Status-Datentyp des Spiegels (OdooSyncStatus, unique je Connection)
MIRROR_DATA_TYPE = "mirror_account_move"

# ERPEntityMapping-Typ fuer gespiegelte ir.attachment-Datensaetze
MIRROR_ENTITY_TYPE = "mirror_attachment"

# Gespiegelte Belegarten (Entscheidung 3: Vollarchiv-Spiegel der Belege)
MIRROR_MOVE_TYPES: Tuple[str, ...] = (
    "out_invoice",
    "in_invoice",
    "out_refund",
    "in_refund",
)

# Overlap-Fenster gegen Race zwischen write_date und Cursor-Stand (Plan §4c.2)
CURSOR_OVERLAP = timedelta(minutes=5)

# Ab so vielen Fehl-Laeufen in Folge warnt der Beat-Task (Slack/Log)
MIRROR_FAILURE_ALERT_THRESHOLD = 5

# Odoo-Datetime-Format (write_date kommt als String in diesem Format)
ODOO_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Gelesene account.move-Felder
_MOVE_FIELDS: List[str] = [
    "id",
    "name",
    "move_type",
    "partner_id",
    "invoice_date",
    "ref",
    "amount_total",
    "currency_id",
    "write_date",
    "state",
]


@dataclass
class MirrorRunResult:
    """Ergebnis eines inkrementellen Spiegel-Laufs."""

    fetched: int = 0
    created: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    new_cursor: Optional[str] = None


class OdooMirrorService:
    """Service fuer den Odoo->Ablage Vollarchiv-Pull-Spiegel."""

    # ==========================================================================
    # Mapping-Helfer (Kategorie / Dokumenttyp)
    # ==========================================================================

    @staticmethod
    def category_for_move_type(move_type: str) -> str:
        """GoBD-Retention-Kategorie je Odoo-Belegart.

        Beide Werte sind im RetentionService definiert (10 Jahre,
        §147 AO / §14b UStG); unbekannte move_types fallen konservativ
        auf Eingangsseite (10 Jahre Default greift ohnehin).
        """
        if move_type.startswith("out_"):
            return "invoice_outgoing"
        return "invoice_incoming"

    @staticmethod
    def document_type_for_move_type(move_type: str) -> str:
        """Document.document_type je Odoo-Belegart (DocumentType-Enum-Werte)."""
        if move_type.endswith("_refund"):
            return "credit_note"
        return "invoice"

    # ==========================================================================
    # Kernlauf
    # ==========================================================================

    async def run_incremental(
        self,
        db: AsyncSession,
        connection: ERPConnection,
        *,
        batch_limit: int = 200,
        connector: Optional[OdooConnector] = None,
    ) -> MirrorRunResult:
        """Fuehrt einen inkrementellen Spiegel-Lauf fuer eine Verbindung aus.

        Args:
            db: Async-DB-Session
            connection: Aktive ERP-Verbindung vom Typ "odoo"
            batch_limit: RPC-Batchgroesse UND Obergrenze verarbeiteter
                Moves pro Lauf (SaaS-Drosselungsschutz, Risiko R2);
                der Rest folgt im naechsten Beat-Lauf ueber den Cursor.
            connector: Optional injizierter Connector (Tests / Wiederverwendung);
                wenn None, wird er aus der Verbindung gebaut und am Ende
                wieder getrennt.

        Returns:
            MirrorRunResult mit Zaehlern und neuem Cursor
        """
        result = MirrorRunResult()

        sync_status = await self._get_or_create_sync_status(db, connection)
        result.new_cursor = sync_status.last_sync_cursor

        odoo_company_id = self._resolve_odoo_company_id(sync_status)
        if odoo_company_id is None:
            # Ohne Company-Context KEIN Spiegel (Multi-Company-Sicherheit):
            # sonst wuerden Belege fremder Odoo-Companies mitgezogen.
            logger.warning(
                "odoo_mirror_skipped_no_company_id",
                connection_id=str(connection.id),
                hint=(
                    "odoo_company_id in OdooSyncStatus.sync_state oder "
                    "Setting ODOO_MIRROR_COMPANY_ID setzen"
                ),
            )
            return result

        own_connector = False
        if connector is None:
            connector = await self._build_connector(db, connection, odoo_company_id)
            if connector is None:
                result.errors = 1
                await self._finalize_status(
                    db, sync_status, result,
                    first_error="Odoo-Verbindungsaufbau fehlgeschlagen",
                )
                return result
            own_connector = True

        first_error: Optional[str] = None
        had_error = False
        cursor_candidate: Optional[str] = None

        try:
            domain = self._build_domain(sync_status.last_sync_cursor)

            async for move in connector.iter_records(
                "account.move",
                domain,
                _MOVE_FIELDS,
                batch_size=batch_limit,
                order="write_date asc, id asc",
            ):
                if result.fetched >= batch_limit:
                    # Lauf-Obergrenze erreicht - Rest kommt im naechsten
                    # Beat-Lauf (Cursor steht auf dem letzten Erfolg).
                    break
                result.fetched += 1

                # Defensiver Draft-Guard (die Domain filtert bereits):
                # Entwuerfe sind fluechtig und werden nicht gespiegelt.
                if str(move.get("state") or "") == "draft":
                    continue

                try:
                    created, skipped = await self._mirror_move(
                        db, connection, connector, move
                    )
                    await db.commit()
                    result.created += created
                    result.skipped_duplicates += skipped
                    if not had_error:
                        write_date = move.get("write_date")
                        if write_date:
                            cursor_candidate = str(write_date)
                except Exception as move_error:
                    await db.rollback()
                    had_error = True
                    result.errors += 1
                    if first_error is None:
                        first_error = safe_error_detail(move_error, "Odoo-Spiegel")
                    logger.exception(
                        "odoo_mirror_move_failed",
                        connection_id=str(connection.id),
                        odoo_move_id=move.get("id"),
                        **safe_error_log(move_error),
                    )

            if cursor_candidate:
                result.new_cursor = cursor_candidate

            await self._finalize_status(db, sync_status, result, first_error)

        except Exception as run_error:
            # Fehler ausserhalb der Move-Schleife (z.B. RPC-Abbruch der
            # Pagination): Cursor bleibt beim letzten Erfolg, Fehler zaehlt.
            await db.rollback()
            result.errors += 1
            if first_error is None:
                first_error = safe_error_detail(run_error, "Odoo-Spiegel")
            logger.exception(
                "odoo_mirror_run_failed",
                connection_id=str(connection.id),
                **safe_error_log(run_error),
            )
            if cursor_candidate:
                result.new_cursor = cursor_candidate
            await self._finalize_status(db, sync_status, result, first_error)
        finally:
            if own_connector:
                await connector.disconnect()

        logger.info(
            "odoo_mirror_run_completed",
            connection_id=str(connection.id),
            fetched=result.fetched,
            created=result.created,
            skipped_duplicates=result.skipped_duplicates,
            errors=result.errors,
            new_cursor=result.new_cursor,
        )
        return result

    # ==========================================================================
    # Move-Verarbeitung
    # ==========================================================================

    async def _mirror_move(
        self,
        db: AsyncSession,
        connection: ERPConnection,
        connector: OdooConnector,
        move: Dict[str, Any],
    ) -> Tuple[int, int]:
        """Spiegelt alle Anhaenge eines account.move (dedupe-sicher).

        Returns:
            (neu angelegte Dokumente, uebersprungene Duplikate)
        """
        created = 0
        skipped = 0
        move_id = int(move["id"])

        # include_field_attachments=True: Odoos gerenderte Rechnungs-PDFs
        # liegen als Binaerfeld-Attachments (res_field gesetzt) und waeren
        # mit der Standard-Domain unsichtbar (Odoo-Falle, s. Connector).
        attachments = await connector.list_attachments(
            "account.move", move_id, include_field_attachments=True
        )

        for attachment in attachments:
            attachment_id = int(attachment["id"])

            # Dedupe-Stufe (a): Attachment bereits gespiegelt?
            if await self._mapping_exists(db, connection.id, attachment_id):
                skipped += 1
                continue

            downloaded = await connector.download_attachment(attachment_id)
            if downloaded is None:
                # Download-Fehler => Move gilt als NICHT verarbeitet
                # (Cursor-Schutz; naechster Lauf versucht es erneut).
                raise RuntimeError(
                    f"Odoo-Anhang {attachment_id} konnte nicht geladen werden"
                )
            content, attachment_meta = downloaded

            if not content:
                # Leere Binaerfelder (type='url' o.ae.) - kein Beleginhalt,
                # kein Fehler; bewusst ohne Mapping (falls Odoo den Inhalt
                # spaeter nachliefert, greift der naechste Lauf).
                logger.info(
                    "odoo_mirror_attachment_empty_skipped",
                    connection_id=str(connection.id),
                    odoo_move_id=move_id,
                    odoo_attachment_id=attachment_id,
                )
                continue

            # GoBD-Integritaetsgate (Plan-Risiko R3): Der von Odoo gemeldete
            # ir.attachment.checksum (SHA-1) muss die uebertragenen Bytes
            # bestaetigen, BEVOR sie unveraenderbar archiviert werden. Ein
            # still-korrupter XML-RPC-Transfer, der noch base64-dekodiert, darf
            # nicht mit einem gueltig aussehenden GoBD-Hash der korrupten Bytes
            # eingebucht werden. Mismatch -> RuntimeError -> per-Move-Rollback +
            # Cursor-Schutz (naechster Lauf laedt den Anhang erneut).
            odoo_checksum = attachment_meta.get("checksum")
            if odoo_checksum:
                computed_sha1 = hashlib.sha1(content).hexdigest()
                if computed_sha1.lower() != str(odoo_checksum).strip().lower():
                    logger.error(
                        "odoo_mirror_checksum_mismatch",
                        connection_id=str(connection.id),
                        odoo_move_id=move_id,
                        odoo_attachment_id=attachment_id,
                        odoo_checksum=str(odoo_checksum),
                        computed_sha1=computed_sha1,
                    )
                    raise RuntimeError(
                        f"Odoo-Anhang {attachment_id}: Checksum-Mismatch "
                        f"(Odoo sha1={odoo_checksum}, lokal={computed_sha1}) - "
                        "korrupter Transfer, wird nicht GoBD-archiviert"
                    )

            sha256 = hashlib.sha256(content).hexdigest()

            # Dedupe-Stufe (b): Inhalt existiert bereits als Dokument der
            # Company? Dann nur Mapping anlegen (spart kuenftige Downloads).
            existing_document_id = await self._find_document_by_checksum(
                db, connection.company_id, sha256
            )
            if existing_document_id is not None:
                await self._store_mapping(
                    db,
                    connection_id=connection.id,
                    attachment_id=attachment_id,
                    document_id=existing_document_id,
                    sha256=sha256,
                    attachment_meta=attachment_meta,
                )
                skipped += 1
                continue

            # Dedupe-Stufe (c): nie ueberschreiben - Neuanlage.
            await self._persist_attachment(
                db,
                connection=connection,
                move=move,
                attachment_id=attachment_id,
                attachment_meta=attachment_meta,
                content=content,
                sha256=sha256,
            )
            created += 1

        return created, skipped

    async def _persist_attachment(
        self,
        db: AsyncSession,
        *,
        connection: ERPConnection,
        move: Dict[str, Any],
        attachment_id: int,
        attachment_meta: Dict[str, Any],
        content: bytes,
        sha256: str,
    ) -> uuid.UUID:
        """Legt Storage-Objekt + Document an und bucht GoBD-konform ein.

        Nutzt denselben Persistenz-Pfad wie Upload-API/Folder-Import:
        StorageService.upload_document -> Document-Zeile -> GoBD-Archiv.
        """
        # Lazy-Imports: schwere Services nur bei tatsaechlicher Anlage
        from app.services.compliance.archive_service import GoBDArchiveService
        from app.services.storage_service import StorageService

        move_id = int(move["id"])
        move_type = str(move.get("move_type") or "")
        filename = self._safe_filename(attachment_meta.get("name"), attachment_id)
        mime_type = str(attachment_meta.get("mimetype") or "application/octet-stream")
        owner_id = connection.created_by  # nullable - Spiegel ist systemisch

        storage = StorageService()
        upload = await storage.upload_document(
            file_data=content,
            filename=filename,
            content_type=mime_type,
            user_id=str(owner_id) if owner_id else None,
            metadata={"import-source": "odoo-mirror"},
        )

        business_entity_id = await self._resolve_partner_entity(
            db, connection.id, move.get("partner_id")
        )

        extracted_text = ""
        if mime_type == "application/pdf":
            extracted_text = self._extract_pdf_text_layer(content)

        odoo_checksum = attachment_meta.get("checksum") or None
        document = Document(
            id=uuid.uuid4(),
            filename=str(upload["storage_path"]).split("/")[-1],
            original_filename=filename,
            file_path=upload["storage_path"],
            file_size=len(content),
            mime_type=mime_type,
            checksum=sha256,
            document_type=self.document_type_for_move_type(move_type),
            # Kein OCR geplant (auto_ocr=False) -> Status wie Upload ohne OCR
            status="uploaded",
            extracted_text=extracted_text or None,
            owner_id=owner_id,
            company_id=connection.company_id,
            business_entity_id=business_entity_id,
            document_metadata={
                "import_source": "odoo_mirror",
                "odoo_model": "account.move",
                "odoo_id": move_id,
                "odoo_name": move.get("name") or None,
                "odoo_move_type": move_type,
                "odoo_attachment_id": attachment_id,
                "odoo_checksum": odoo_checksum,
                "odoo_write_date": move.get("write_date") or None,
                "auto_ocr": False,
            },
        )
        db.add(document)
        await db.flush()

        # GoBD-Zweitablage: Hash, Retention (10 J.), Audit-Chain, optional TSA
        archive_service = GoBDArchiveService()
        await archive_service.archive_document(
            db=db,
            document_id=document.id,
            company_id=connection.company_id,
            category=self.category_for_move_type(move_type),
            document_content=content,
            document_date=self._parse_invoice_date(move.get("invoice_date")),
            archived_by_id=owner_id,
            metadata={
                "source": "odoo_mirror",
                "odoo_id": move_id,
                "odoo_attachment_id": attachment_id,
                "odoo_checksum": odoo_checksum,
            },
            use_tsa=settings.ODOO_MIRROR_USE_TSA,
        )

        await self._store_mapping(
            db,
            connection_id=connection.id,
            attachment_id=attachment_id,
            document_id=document.id,
            sha256=sha256,
            attachment_meta=attachment_meta,
        )

        logger.info(
            "odoo_mirror_document_created",
            connection_id=str(connection.id),
            document_id=str(document.id),
            odoo_move_id=move_id,
            odoo_attachment_id=attachment_id,
            category=self.category_for_move_type(move_type),
        )
        return document.id

    # ==========================================================================
    # Cursor / Domain
    # ==========================================================================

    def _build_domain(self, cursor: Optional[str]) -> List[Any]:
        """Odoo-Suchdomain fuer den inkrementellen Lauf.

        state != draft filtert Entwuerfe bereits serverseitig (Traffic);
        der Loop enthaelt zusaetzlich einen defensiven Guard.
        """
        domain: List[Any] = [
            ["move_type", "in", list(MIRROR_MOVE_TYPES)],
            ["state", "!=", "draft"],
        ]
        overlap_cursor = self._cursor_with_overlap(cursor)
        if overlap_cursor:
            domain.append(["write_date", ">=", overlap_cursor])
        return domain

    @staticmethod
    def _cursor_with_overlap(cursor: Optional[str]) -> Optional[str]:
        """Cursor minus Overlap-Fenster (5 min) im Odoo-Datetime-Format."""
        if not cursor:
            return None
        try:
            cursor_dt = datetime.strptime(cursor, ODOO_DATETIME_FORMAT)
        except ValueError:
            logger.warning(
                "odoo_mirror_cursor_unparseable",
                cursor=cursor,
                action="full_scan_without_write_date_filter",
            )
            return None
        return (cursor_dt - CURSOR_OVERLAP).strftime(ODOO_DATETIME_FORMAT)

    # ==========================================================================
    # Persistenz-Helfer (in Tests einzeln mock-/patchbar)
    # ==========================================================================

    async def _get_or_create_sync_status(
        self, db: AsyncSession, connection: ERPConnection
    ) -> OdooSyncStatus:
        """Holt oder erstellt die Spiegel-Status-Zeile (unique je Connection)."""
        result = await db.execute(
            select(OdooSyncStatus).where(
                and_(
                    OdooSyncStatus.connection_id == connection.id,
                    OdooSyncStatus.data_type == MIRROR_DATA_TYPE,
                )
            )
        )
        sync_status = result.scalar_one_or_none()
        if sync_status is not None:
            return sync_status

        sync_status = OdooSyncStatus(
            id=uuid.uuid4(),
            connection_id=connection.id,
            data_type=MIRROR_DATA_TYPE,
            total_records_synced=0,
            records_synced_today=0,
            consecutive_failures=0,
            is_paused=False,
            sync_state={},
        )
        db.add(sync_status)
        await db.flush()
        return sync_status

    @staticmethod
    def _resolve_odoo_company_id(sync_status: OdooSyncStatus) -> Optional[int]:
        """Ermittelt die Odoo-Company-ID fuer den Company-Context.

        Prioritaet: per-Connection-Wert in OdooSyncStatus.sync_state
        ["odoo_company_id"] (Admin-pflegbar, migrationsfrei) vor dem
        globalen Setting ODOO_MIRROR_COMPANY_ID (Fallback fuer das
        Ein-Verbindungs-Setup Spargelmesser).
        """
        state: Dict[str, Any] = dict(sync_status.sync_state or {})
        value = state.get("odoo_company_id")
        if value is None:
            value = settings.ODOO_MIRROR_COMPANY_ID
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning(
                "odoo_mirror_company_id_invalid",
                value=str(value),
            )
            return None

    async def _build_connector(
        self,
        db: AsyncSession,
        connection: ERPConnection,
        odoo_company_id: int,
    ) -> Optional[OdooConnector]:
        """Baut und verbindet den Odoo-Connector mit Company-Context."""
        # Lazy-Import: vermeidet Import-Zyklus services <-> workers
        from app.workers.tasks.erp_sync_tasks import (
            create_connector,
            get_connection_config,
        )

        config = await get_connection_config(db, connection.id)
        if config is None:
            logger.error(
                "odoo_mirror_config_not_found",
                connection_id=str(connection.id),
            )
            return None
        config.odoo_company_id = odoo_company_id

        connector = await create_connector(config)
        if not await connector.connect():
            logger.error(
                "odoo_mirror_connect_failed",
                connection_id=str(connection.id),
            )
            return None
        return connector

    async def _mapping_exists(
        self, db: AsyncSession, connection_id: uuid.UUID, attachment_id: int
    ) -> bool:
        """Dedupe-Stufe (a): existiert bereits ein Spiegel-Mapping?"""
        result = await db.execute(
            select(ERPEntityMapping.id)
            .where(
                and_(
                    ERPEntityMapping.connection_id == connection_id,
                    ERPEntityMapping.entity_type == MIRROR_ENTITY_TYPE,
                    ERPEntityMapping.remote_id == str(attachment_id),
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _find_document_by_checksum(
        self, db: AsyncSession, company_id: uuid.UUID, sha256: str
    ) -> Optional[uuid.UUID]:
        """Dedupe-Stufe (b): Dokument mit gleichem SHA256 in der Company."""
        result = await db.execute(
            select(Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.checksum == sha256,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _resolve_partner_entity(
        self,
        db: AsyncSession,
        connection_id: uuid.UUID,
        partner_ref: Any,
    ) -> Optional[uuid.UUID]:
        """BusinessEntity-Link via bestehendem Partner-Mapping (best-effort).

        Kein Mapping oder Fehler => None (bewusst kein Fehler, Plan-Vorgabe).
        """
        try:
            if not partner_ref:
                return None
            # search_read liefert m2o als [id, display_name] (oder False)
            if isinstance(partner_ref, (list, tuple)):
                partner_id = int(partner_ref[0])
            else:
                partner_id = int(partner_ref)

            result = await db.execute(
                select(ERPEntityMapping.local_id)
                .where(
                    and_(
                        ERPEntityMapping.connection_id == connection_id,
                        ERPEntityMapping.entity_type.in_(("customer", "supplier")),
                        ERPEntityMapping.remote_id == str(partner_id),
                    )
                )
                .limit(1)
            )
            return result.scalar_one_or_none()
        except Exception as lookup_error:
            logger.warning(
                "odoo_mirror_partner_lookup_failed",
                connection_id=str(connection_id),
                **safe_error_log(lookup_error),
            )
            return None

    async def _store_mapping(
        self,
        db: AsyncSession,
        *,
        connection_id: uuid.UUID,
        attachment_id: int,
        document_id: uuid.UUID,
        sha256: str,
        attachment_meta: Dict[str, Any],
    ) -> None:
        """Persistiert das Spiegel-Mapping (Idempotenz-Anker der Stufe a).

        Defensive Pruefung auf den local-Unique-Constraint: mappen zwei
        inhaltsgleiche Odoo-Attachments (Dedupe-Stufe b) auf DASSELBE
        lokale Dokument, existiert (connection, entity_type, local_id)
        bereits - dann kein zweiter Insert (UniqueViolation vermeiden).
        """
        existing = await db.execute(
            select(ERPEntityMapping.id)
            .where(
                and_(
                    ERPEntityMapping.connection_id == connection_id,
                    ERPEntityMapping.entity_type == MIRROR_ENTITY_TYPE,
                    ERPEntityMapping.local_id == document_id,
                )
            )
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            return

        mapping = ERPEntityMapping(
            id=uuid.uuid4(),
            connection_id=connection_id,
            entity_type=MIRROR_ENTITY_TYPE,
            local_id=document_id,
            remote_id=str(attachment_id),
            last_synced_at=datetime.now(timezone.utc),
            local_checksum=sha256,
            remote_checksum=(attachment_meta.get("checksum") or None),
        )
        db.add(mapping)
        await db.flush()

    async def _finalize_status(
        self,
        db: AsyncSession,
        sync_status: OdooSyncStatus,
        result: MirrorRunResult,
        first_error: Optional[str],
    ) -> None:
        """Schreibt Lauf-Ergebnis + Cursor in die Status-Zeile (ein Commit)."""
        now = datetime.now(timezone.utc)
        sync_status.last_sync_at = now
        sync_status.last_record_count = result.fetched
        sync_status.total_records_synced = (
            (sync_status.total_records_synced or 0) + result.created
        )
        if result.new_cursor:
            sync_status.last_sync_cursor = result.new_cursor

        if result.errors == 0:
            sync_status.last_successful_sync_at = now
            sync_status.consecutive_failures = 0
            sync_status.last_error = None
            sync_status.is_paused = False
        else:
            sync_status.consecutive_failures = (
                (sync_status.consecutive_failures or 0) + 1
            )
            sync_status.last_error = first_error
            if sync_status.consecutive_failures >= MIRROR_FAILURE_ALERT_THRESHOLD:
                # Anzeige/Monitoring - gated den naechsten Lauf bewusst NICHT
                sync_status.is_paused = True

        state: Dict[str, Any] = dict(sync_status.sync_state or {})
        state["last_run"] = {
            "at": now.isoformat(),
            "fetched": result.fetched,
            "created": result.created,
            "skipped_duplicates": result.skipped_duplicates,
            "errors": result.errors,
        }
        sync_status.sync_state = state

        await db.commit()

    # ==========================================================================
    # Kleine Helfer
    # ==========================================================================

    @staticmethod
    def _parse_invoice_date(value: Any) -> Optional[date]:
        """invoice_date ("YYYY-MM-DD" oder Odoo-False) -> date oder None."""
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _safe_filename(name: Any, attachment_id: int) -> str:
        """Sanitisiert den Odoo-Attachment-Namen (kein Pfad, kein Sonderzeug)."""
        fallback = f"odoo_attachment_{attachment_id}"
        if not name:
            return fallback
        base = os.path.basename(str(name).replace("\\", "/"))
        base = re.sub(r"[^\w.\- ()]", "_", base).strip()
        if not base or base in (".", ".."):
            return fallback
        return base[:255]

    @staticmethod
    def _extract_pdf_text_layer(content: bytes, max_pages: int = 50) -> str:
        """Best-effort-Textlayer-Extraktion via pypdfium2 (Repo-Standard).

        Kein OCR: Odoo-PDFs sind i.d.R. digital erzeugt und haben einen
        Textlayer. Fehler => leerer String (Embedding-Beat greift spaeter).
        """
        try:
            import pypdfium2 as pdfium
        except ImportError:
            return ""

        try:
            pdf = pdfium.PdfDocument(content)
            try:
                parts: List[str] = []
                for index in range(min(len(pdf), max_pages)):
                    page = pdf[index]
                    textpage = page.get_textpage()
                    parts.append(textpage.get_text_range())
                    textpage.close()
                    page.close()
                return "\n".join(part for part in parts if part).strip()
            finally:
                pdf.close()
        except Exception as pdf_error:
            logger.debug(
                "odoo_mirror_pdf_text_extraction_failed",
                **safe_error_log(pdf_error),
            )
            return ""
