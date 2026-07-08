# -*- coding: utf-8 -*-
"""Odoo Vendor-Bill-Push-Service (Neuausrichtung Phase 4: Ablage -> Odoo).

Eingangskanal ab Go-Live: Scanner/E-Mail -> OCR (lokal) -> GoBD-Archiv ->
automatischer Push als ENTWURFS-Lieferantenrechnung nach Odoo (Company
Spargelmesser). Grundsaetze (Plan §4c.3 + §7 R6 + E4):

- **Archiv immer ZUERST, Push danach**: Der Import (E-Mail/Ordner) persistiert
  das Original in MinIO + Document-Zeile (inkl. SHA256 file_hash), BEVOR OCR
  laeuft; dieser Service wird erst am Ende des OCR-Abschlussblocks gequeued.
  Die formale GoBD-Archivierung (``is_archived`` via ArchiveService) ist ein
  separater Schritt (API/Beat) und wird hier bewusst NICHT aufgerufen.
- **Konservatives Partner-Matching (R6)**: Zuerst ``ERPEntityMapping`` der
  verknuepften BusinessEntity, sonst ``find_partner``-Kaskade
  (USt-Id -> IBAN -> Lieferantennr. -> Name). NUR ein eindeutiger Treffer
  pusht; 0 Treffer -> ``no_partner_match``, >1 -> ``ambiguous`` — in beiden
  Faellen KEIN Push, stattdessen Review-Aufgabe. Bestaetigte Treffer werden
  als ``ERPEntityMapping`` gelernt (Lernschleife R6).
- **E4**: Draft-Bill = Kopf + PDF + EINE Brutto-Sammelzeile; Steuer-/Konten-
  zuordnung erfolgt beim Pruefen des Entwurfs in Odoo.

PII-Regel: Betraege, IBANs, USt-Ids und Namen werden NIEMALS geloggt —
nur Status, IDs und Quellen-Kategorien.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Optional, Sequence, Tuple, cast
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import Document, OCRResult
from app.db.models_erp_import import ERPConnection, ERPEntityMapping
from app.schemas.odoo import OdooVendorBillDraft

if TYPE_CHECKING:  # schwerer Import (xmlrpc) nur fuer Type-Hints
    from app.services.erp.odoo_connector import OdooConnector

logger = structlog.get_logger(__name__)


# =============================================================================
# Konstanten
# =============================================================================

#: Import-Quellen, die fuer den Push in Frage kommen (E-Mail-/Ordner-Eingang).
#: Werte wie in imports/email_import_service.py ("email") und
#: imports/folder_import_service.py ("folder") gesetzt.
PUSH_ELIGIBLE_IMPORT_SOURCES: FrozenSet[str] = frozenset({"email", "folder"})

#: Quelle des Odoo->Ablage-Spiegels (Phase 3). Dokumente aus dem Spiegel
#: duerfen NIEMALS zurueck nach Odoo gepusht werden (Kreislauf!).
MIRROR_IMPORT_SOURCE: str = "odoo_mirror"

#: Dokumenttyp, der gepusht wird (DocumentClassificationResult.document_type).
INVOICE_DOCUMENT_TYPE: str = "invoice"

#: ISO-4217-Muster fuer den Waehrungscode des Drafts.
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

#: entity_type-Werte, unter denen ein Partner-Mapping nachgeschlagen wird
#: (Lieferant bevorzugt; ein Kunde-Mapping zeigt auf denselben res.partner).
_PARTNER_MAPPING_ENTITY_TYPES: Tuple[str, ...] = ("supplier", "customer")


# =============================================================================
# Ergebnis-Datenklasse
# =============================================================================


@dataclass
class PushResult:
    """Ergebnis eines Vendor-Bill-Push-Versuchs.

    status:
        - ``pushed``            Entwurf in Odoo angelegt
        - ``no_partner_match``  Kein Partner-Treffer -> Review-Aufgabe
        - ``ambiguous``         Mehrere Partner-Treffer -> Review-Aufgabe
        - ``skipped``           Kein Push noetig/erlaubt (idempotent, keine
                                Rechnung, Ausgangsrechnung, keine Verbindung)
        - ``error``             Fehler (Odoo down, kein Betrag, ...)
    retryable:
        Internes Steuerfeld fuer den Celery-Task: True bei transienten
        Fehlern (Odoo/Storage nicht erreichbar) -> Retry sinnvoll.
    """

    status: str
    odoo_move_id: Optional[str] = None
    partner_match_source: Optional[str] = None
    reason: Optional[str] = None
    retryable: bool = False


# =============================================================================
# Reine Funktionen (ohne DB) — Hook-Logik & Betrags-Auswahl
# =============================================================================


def is_push_eligible_source(document_metadata: Optional[Dict[str, object]]) -> bool:
    """Prueft die Import-Quelle eines Dokuments fuer den Push (reine Funktion).

    Erlaubt sind nur E-Mail-/Ordner-Import (``import_source`` in
    {"email", "folder"}). Dokumente aus dem Odoo-Spiegel
    (``import_source == "odoo_mirror"``) sind IMMER ausgeschlossen —
    sonst wuerden gespiegelte Odoo-Belege zurueck nach Odoo gepusht
    (Endlos-Kreislauf).
    """
    source = (document_metadata or {}).get("import_source")
    if source == MIRROR_IMPORT_SOURCE:
        return False
    return source in PUSH_ELIGIBLE_IMPORT_SOURCES


def is_extraction_ready(document: Document) -> bool:
    """True sobald die strukturierte Extraktion (extracted_data) vorliegt.

    Die Extraktion laeuft asynchron NACH dem OCR-Abschluss
    (extraction_tasks.reprocess_single_document, countdown=2) und schreibt
    ``extracted_data["classification"]``. Der Push-Task wartet darauf
    (Retry), weil erst dann Klassifikation + Rechnungsfelder verlaesslich sind.
    """
    extracted = cast(Dict[str, object], document.extracted_data or {})
    return bool(extracted.get("classification"))


def _parse_german_amount(raw: str) -> Optional[Decimal]:
    """Parst einen deutschen Betrags-String ("1.234,56 €") zu Decimal.

    Format laut GermanValidator.validate_currency_format: Punkt =
    Tausendertrenner, Komma = Dezimaltrenner, optionales Waehrungssymbol.
    """
    cleaned = re.sub(r"[^0-9.,]", "", raw or "")
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # Nur Punkte -> im deutschen Format Tausendertrenner ("1.234")
        cleaned = cleaned.replace(".", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _to_decimal(value: object) -> Optional[Decimal]:
    """Konvertiert JSONB-Werte (str/int/float) verlustarm zu Decimal.

    Pydantic v2 serialisiert Decimal bei ``model_dump(mode="json")`` als
    String — extracted_data enthaelt Betraege daher meist als "123.45".
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool ist int-Subklasse — explizit ausschliessen
        return None
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def select_gross_amount(
    extracted_data: Optional[Dict[str, object]],
    detected_amounts: Sequence[str],
) -> Tuple[Optional[Decimal], Optional[str]]:
    """Waehlt den Bruttobetrag fuer die Sammel-Buchungszeile.

    Auswahl-Logik (dokumentiert, konservativ absteigend nach Verlaesslichkeit):

    1. ``invoice.gross_amount``  — explizit extrahiertes Brutto (beste Quelle).
    2. ``invoice.net_amount + invoice.vat_amount`` — berechnet, wenn beide
       vorhanden sind (Standard-Buchhaltungslogik, AmountSource "computed").
    3. ``max(extracted_data.amounts)`` — groesster strukturiert extrahierter
       Betrag: Auf einer Rechnung ist der groesste Betrag praktisch immer der
       Brutto-Gesamtbetrag (Netto/MwSt/Positionen sind kleiner).
    4. ``max(OCRResult.detected_amounts)`` — groesster vom German-Validator
       erkannter Betrag (deutsches Format "1.234,56 €"), letzter Fallback.

    Der Entwurf wird in Odoo ohnehin geprueft (E4) — die Heuristik (3/4)
    liefert also nur einen Pruef-Startwert, keine Buchung.

    Returns:
        (Betrag, Quelle) — Quelle in {"gross_amount", "net_plus_vat",
        "max_extracted_amount", "max_detected_amount"} oder (None, None).
    """
    extracted = extracted_data or {}
    invoice_raw = extracted.get("invoice")
    invoice: Dict[str, object] = invoice_raw if isinstance(invoice_raw, dict) else {}

    # 1) Explizites Brutto
    gross = _to_decimal(invoice.get("gross_amount"))
    if gross is not None and gross > 0:
        return gross, "gross_amount"

    # 2) Netto + MwSt (nur wenn BEIDE vorhanden)
    net = _to_decimal(invoice.get("net_amount"))
    vat = _to_decimal(invoice.get("vat_amount"))
    if net is not None and vat is not None and (net + vat) > 0:
        return net + vat, "net_plus_vat"

    # 3) Groesster strukturiert extrahierter Betrag
    amounts_raw = extracted.get("amounts")
    if isinstance(amounts_raw, (list, tuple)):
        candidates = [d for d in (_to_decimal(a) for a in amounts_raw) if d is not None and d > 0]
        if candidates:
            return max(candidates), "max_extracted_amount"

    # 4) Groesster OCR-erkannter Betrag (deutsches Format)
    parsed = [d for d in (_parse_german_amount(str(a)) for a in detected_amounts) if d is not None and d > 0]
    if parsed:
        return max(parsed), "max_detected_amount"

    return None, None


def _select_unambiguous_iban(
    invoice: Dict[str, object],
    extracted_data: Dict[str, object],
) -> Optional[str]:
    """Waehlt eine EINDEUTIGE IBAN fuer die Matching-Kaskade (konservativ, R6).

    Primaer die extrahierte Absender-Bankverbindung (``sender_bank.iban``).
    Fallback: die Top-Level-Liste ``ibans`` NUR, wenn sie genau EINEN
    Eintrag hat — bei mehreren IBANs auf dem Dokument (z. B. eigene +
    Lieferanten-IBAN) ist ein IBAN-Match zu fehltraechtig.
    """
    sender_bank_raw = invoice.get("sender_bank")
    if isinstance(sender_bank_raw, dict):
        iban = sender_bank_raw.get("iban")
        if isinstance(iban, str) and iban.strip():
            return iban.strip()

    ibans_raw = extracted_data.get("ibans")
    if isinstance(ibans_raw, (list, tuple)):
        unique = [i for i in ibans_raw if isinstance(i, str) and i.strip()]
        if len(unique) == 1:
            return unique[0].strip()
    return None


def _sender_name(invoice: Dict[str, object]) -> Optional[str]:
    """Extrahiert den Absender-Namen (Firma bevorzugt) fuer die Namenssuche."""
    sender_raw = invoice.get("sender")
    if isinstance(sender_raw, dict):
        for key in ("company", "person"):
            value = sender_raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _parse_invoice_date(invoice: Dict[str, object]) -> date:
    """Rechnungsdatum aus extracted_data ("YYYY-MM-DD"), Fallback heute."""
    raw = invoice.get("invoice_date")
    if isinstance(raw, str) and raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return utc_now().date()


def _build_ref(invoice: Dict[str, object], document_id: UUID) -> str:
    """Lieferanten-Rechnungsnummer; Fallback: kurze Dokument-Referenz."""
    raw = invoice.get("invoice_number")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:255]
    return f"ABLAGE-{str(document_id)[:8].upper()}"


def _build_currency(invoice: Dict[str, object]) -> str:
    """ISO-4217-Waehrung aus der Extraktion, Fallback EUR."""
    raw = invoice.get("currency")
    if isinstance(raw, str) and _CURRENCY_PATTERN.match(raw.strip().upper()):
        return raw.strip().upper()
    return "EUR"


# =============================================================================
# Hook-Praedikat (fuer ocr_tasks.py — Setting + Quelle + aktive Verbindung)
# =============================================================================


async def has_active_odoo_connection(db: AsyncSession, company_id: UUID) -> bool:
    """True wenn fuer die Company mindestens eine aktive Odoo-Verbindung existiert."""
    stmt = (
        select(ERPConnection.id)
        .where(
            and_(
                ERPConnection.company_id == company_id,
                ERPConnection.erp_type == "odoo",
                ERPConnection.is_active.is_(True),
            )
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def should_enqueue_vendor_bill_push(
    db: AsyncSession,
    document: Document,
) -> bool:
    """Hook-Bedingungen fuer das Queuen des Push-Tasks (ocr_tasks-Abschluss).

    Zur Queue-Zeit pruefbar sind: Feature-Toggle, Import-Quelle
    (email/folder, NIE odoo_mirror), Company-Zuordnung und eine aktive
    Odoo-ERPConnection. Die Klassifikation (== invoice) entsteht erst in
    der asynchron laufenden Extraktion und wird deshalb vom Push-Task
    selbst geprueft (Retry bis extracted_data vorliegt).
    """
    if not settings.ODOO_VENDOR_BILL_PUSH_ENABLED:
        return False
    if not is_push_eligible_source(
        cast(Optional[Dict[str, object]], document.document_metadata)
    ):
        return False
    company_id = getattr(document, "company_id", None)
    if company_id is None:
        return False
    return await has_active_odoo_connection(db, company_id)


# =============================================================================
# DB-/IO-Helfer (im Test patchbar)
# =============================================================================


async def _load_document(db: AsyncSession, document_id: UUID) -> Optional[Document]:
    """Laedt das Dokument."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()


async def _load_active_connection(
    db: AsyncSession, company_id: UUID
) -> Optional[ERPConnection]:
    """Laedt die aelteste aktive Odoo-Verbindung der Company (deterministisch)."""
    stmt = (
        select(ERPConnection)
        .where(
            and_(
                ERPConnection.company_id == company_id,
                ERPConnection.erp_type == "odoo",
                ERPConnection.is_active.is_(True),
            )
        )
        .order_by(ERPConnection.created_at.asc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _load_entity_mapping(
    db: AsyncSession,
    connection_id: UUID,
    business_entity_id: UUID,
) -> Optional[ERPEntityMapping]:
    """Sucht ein bestehendes Partner-Mapping der BusinessEntity (supplier zuerst)."""
    for entity_type in _PARTNER_MAPPING_ENTITY_TYPES:
        stmt = select(ERPEntityMapping).where(
            and_(
                ERPEntityMapping.connection_id == connection_id,
                ERPEntityMapping.entity_type == entity_type,
                ERPEntityMapping.local_id == business_entity_id,
            )
        )
        result = await db.execute(stmt)
        mapping = result.scalar_one_or_none()
        if mapping is not None:
            return mapping
    return None


async def _load_detected_amounts(db: AsyncSession, document_id: UUID) -> List[str]:
    """Laedt detected_amounts des juengsten OCR-Ergebnisses (deutsche Strings)."""
    stmt = (
        select(OCRResult.detected_amounts)
        .where(OCRResult.document_id == document_id)
        .order_by(OCRResult.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    amounts = result.scalar_one_or_none()
    if isinstance(amounts, (list, tuple)):
        return [str(a) for a in amounts]
    return []


async def _load_pdf(document: Document) -> Optional[bytes]:
    """Laedt die Original-Bytes aus dem Storage (derselbe Weg wie OCR/Export).

    ``Document.file_path`` ist der MinIO-object_key (siehe ocr_tasks.py,
    das denselben Pfad fuer den Download nutzt).
    """
    from app.services.storage_service import StorageService

    if not document.file_path:
        return None
    storage = StorageService()
    return await storage.download_document(str(document.file_path))


async def _build_connector(
    db: AsyncSession, connection: ERPConnection
) -> Optional["OdooConnector"]:
    """Erzeugt einen authentifizierbaren OdooConnector zur Verbindung.

    Nutzt die bestehenden Helfer aus erp_sync_tasks (Key-Entschluesselung,
    Config-Mapping). Lazy-Import vermeidet einen Import-Zyklus
    (erp_sync_tasks importiert diesen Service fuer den Push-Task).
    """
    from app.workers.tasks.erp_sync_tasks import (
        create_connector,
        get_connection_config,
    )

    config = await get_connection_config(db, cast(UUID, connection.id))
    if config is None:
        return None
    return await create_connector(config)


# =============================================================================
# Persistenz-Helfer (doc_metadata + Review-Queue)
# =============================================================================


def _apply_push_metadata(document: Document, result: PushResult) -> None:
    """Persistiert das Push-Ergebnis in Document.document_metadata.

    WICHTIG: Neuzuweisung des kompletten Dicts, damit SQLAlchemy die
    Aenderung am JSON-Feld erkennt (kein MutableDict auf CrossDBJSON).
    """
    meta: Dict[str, object] = dict(
        cast(Dict[str, object], document.document_metadata or {})
    )
    meta["odoo_push_status"] = result.status
    meta["odoo_push_at"] = utc_now().isoformat()
    if result.odoo_move_id:
        meta["odoo_move_id"] = result.odoo_move_id
    if result.partner_match_source:
        meta["partner_match_source"] = result.partner_match_source
    if result.reason:
        meta["odoo_push_reason"] = result.reason
    document.document_metadata = meta


def _apply_review_task(document: Document, reason: str) -> None:
    """Erzeugt eine Review-Aufgabe ueber den vorhandenen Queue-Mechanismus.

    Die Review-Queue (GET /api/v1/review-queue) liest
    ``document_metadata.pipeline_result.requires_review == true`` und zeigt
    ``review_reasons`` an — genau diese Felder werden hier gesetzt/gemergt.
    Das Dokument ist zu diesem Zeitpunkt bereits archiviert (Import ->
    MinIO+DB VOR OCR und Push; Grundsatz "Archiv zuerst").
    """
    meta: Dict[str, object] = dict(
        cast(Dict[str, object], document.document_metadata or {})
    )
    pipeline_result = cast(Dict[str, object], dict(meta.get("pipeline_result") or {}))

    reasons: List[str] = list(pipeline_result.get("review_reasons") or [])
    entry = (
        f"Eingangsrechnung ohne Odoo-Zuordnung prüfen: {reason} "
        f"(Dokument {document.id})"
    )
    if entry not in reasons:
        reasons.append(entry)

    pipeline_result["requires_review"] = True
    pipeline_result["review_confirmed"] = False
    pipeline_result["review_reasons"] = reasons
    pipeline_result.setdefault("status", "requires_review")
    pipeline_result.setdefault("document_type", INVOICE_DOCUMENT_TYPE)

    meta["pipeline_result"] = pipeline_result
    document.document_metadata = meta


# =============================================================================
# Haupt-Service
# =============================================================================


async def push_document(
    db: AsyncSession,
    document_id: UUID,
    *,
    is_final_attempt: bool = True,
) -> PushResult:
    """Pusht ein archiviertes Eingangsrechnungs-Dokument als Odoo-Entwurf.

    Ablauf: Dokument + Extraktion laden -> Idempotenz-/Klassifikations-Gates
    -> Partner ermitteln (Mapping-Vorrang, sonst Kaskade, nur eindeutig)
    -> OdooVendorBillDraft bauen -> Original-PDF aus Storage -> create in
    Odoo -> Ergebnis in doc_metadata persistieren. Bei
    no_partner_match/ambiguous (immer) bzw. error (nur beim finalen
    Versuch, sonst Retry durch den Task) wird eine Review-Aufgabe erzeugt.

    Args:
        db: Async-Session
        document_id: Dokument-UUID
        is_final_attempt: False solange der Celery-Task noch Retries hat —
            unterdrueckt die Review-Aufgabe bei transienten Fehlern.

    Returns:
        PushResult (status pushed|no_partner_match|ambiguous|skipped|error)
    """
    document = await _load_document(db, document_id)
    if document is None:
        return PushResult(status="error", reason="Dokument nicht gefunden")

    # --- Idempotenz: bereits gepusht -> skipped (kein zweiter Entwurf) ---
    doc_meta = cast(Dict[str, object], document.document_metadata or {})
    existing_move_id = doc_meta.get("odoo_move_id")
    if existing_move_id:
        logger.info(
            "odoo_vendor_bill_push_skipped_idempotent",
            document_id=str(document_id),
            odoo_move_id=str(existing_move_id),
        )
        return PushResult(
            status="skipped",
            odoo_move_id=str(existing_move_id),
            reason="Bereits nach Odoo gepusht (idempotent)",
        )

    # --- Kreislauf-Schutz: Spiegel-Dokumente nie zurueck pushen ---
    if not is_push_eligible_source(doc_meta):
        return PushResult(
            status="skipped",
            reason="Import-Quelle nicht push-berechtigt (nur email/folder, nie odoo_mirror)",
        )

    # --- Klassifikations-Gate: nur Rechnungen ---
    extracted = cast(Dict[str, object], document.extracted_data or {})
    classification_raw = extracted.get("classification")
    classification: Dict[str, object] = (
        classification_raw if isinstance(classification_raw, dict) else {}
    )
    doc_type = classification.get("document_type") or document.document_type
    if doc_type != INVOICE_DOCUMENT_TYPE:
        return PushResult(
            status="skipped",
            reason="Keine Rechnung (Klassifikation)",
        )

    invoice_raw = extracted.get("invoice")
    invoice: Dict[str, object] = invoice_raw if isinstance(invoice_raw, dict) else {}

    # Ausgangsrechnungen (von uns) sind keine Lieferantenrechnungen.
    # "incoming"/"unknown" laufen durch: Der Eingangskanal (Rechnungs-
    # Postfach/Scanner) ist per Definition Eingang; der Entwurf wird in
    # Odoo ohnehin geprueft.
    if invoice.get("invoice_direction") == "outgoing":
        return PushResult(
            status="skipped",
            reason="Ausgangsrechnung — kein Vendor-Bill-Push",
        )

    # --- Aktive Odoo-Verbindung ---
    company_id = getattr(document, "company_id", None)
    if company_id is None:
        return PushResult(status="skipped", reason="Dokument ohne Company-Zuordnung")

    connection = await _load_active_connection(db, company_id)
    if connection is None:
        return PushResult(status="skipped", reason="Keine aktive Odoo-Verbindung")

    # --- Bruttobetrag (Auswahl-Logik siehe select_gross_amount) ---
    detected_amounts = await _load_detected_amounts(db, document_id)
    amount, amount_source = select_gross_amount(extracted, detected_amounts)
    if amount is None:
        result = PushResult(
            status="error",
            reason="Kein Bruttobetrag extrahierbar",
            retryable=False,  # Extraktion ist fertig — Retry aendert nichts
        )
        _apply_push_metadata(document, result)
        _apply_review_task(document, result.reason or "")
        await db.commit()
        logger.warning(
            "odoo_vendor_bill_push_no_amount",
            document_id=str(document_id),
        )
        return result

    # --- Connector aufbauen + Erreichbarkeit pruefen ---
    # find_partner faengt Odoo-Fehler intern ab und liefert dann [] — ohne
    # den expliziten connect()-Check wuerde "Odoo down" faelschlich als
    # no_partner_match statt als (retrybarer) error gewertet.
    try:
        connector = await _build_connector(db, connection)
    except Exception as exc:  # Konfig-/Entschluesselungsfehler
        connector = None
        logger.error(
            "odoo_vendor_bill_push_connector_error",
            document_id=str(document_id),
            **safe_error_log(exc),
        )
    if connector is None or not await connector.connect():
        result = PushResult(
            status="error",
            reason="Odoo nicht erreichbar",
            retryable=True,
        )
        if is_final_attempt:
            _apply_push_metadata(document, result)
            _apply_review_task(document, result.reason or "")
            await db.commit()
        return result

    # --- Partner: ZUERST ERPEntityMapping, sonst find_partner-Kaskade ---
    partner_id: Optional[int] = None
    match_source: Optional[str] = None
    mapping: Optional[ERPEntityMapping] = None

    business_entity_id = getattr(document, "business_entity_id", None)
    if business_entity_id is not None:
        mapping = await _load_entity_mapping(
            db, cast(UUID, connection.id), cast(UUID, business_entity_id)
        )
        if mapping is not None:
            try:
                partner_id = int(str(mapping.remote_id))
                match_source = "entity_mapping"
            except (TypeError, ValueError):
                logger.warning(
                    "odoo_vendor_bill_push_mapping_invalid",
                    document_id=str(document_id),
                    mapping_id=str(mapping.id),
                )
                mapping = None

    if partner_id is None:
        vat_raw = invoice.get("sender_vat_id")
        vat = vat_raw.strip() if isinstance(vat_raw, str) and vat_raw.strip() else None
        iban = _select_unambiguous_iban(invoice, extracted)
        supplier_ref_raw = invoice.get("supplier_number")
        supplier_ref = (
            supplier_ref_raw.strip()
            if isinstance(supplier_ref_raw, str) and supplier_ref_raw.strip()
            else None
        )
        name = _sender_name(invoice)

        if not any([vat, iban, supplier_ref, name]):
            result = PushResult(
                status="no_partner_match",
                reason="Keine Partner-Identifikatoren extrahiert (USt-Id/IBAN/Lieferantennr./Name)",
            )
            _apply_push_metadata(document, result)
            _apply_review_task(document, result.reason or "")
            await db.commit()
            return result

        partners = await connector.find_partner(
            vat=vat,
            iban=iban,
            supplier_ref=supplier_ref,
            name=name,
        )

        if len(partners) == 0:
            result = PushResult(
                status="no_partner_match",
                reason="Kein eindeutiger Odoo-Partner gefunden (0 Treffer)",
            )
            _apply_push_metadata(document, result)
            _apply_review_task(document, result.reason or "")
            await db.commit()
            logger.info(
                "odoo_vendor_bill_push_no_partner",
                document_id=str(document_id),
            )
            return result

        if len(partners) > 1:
            result = PushResult(
                status="ambiguous",
                reason=f"Mehrdeutiger Odoo-Partner ({len(partners)} Treffer) — nur eindeutige Treffer werden gepusht",
            )
            _apply_push_metadata(document, result)
            _apply_review_task(document, result.reason or "")
            await db.commit()
            logger.info(
                "odoo_vendor_bill_push_ambiguous",
                document_id=str(document_id),
                partner_count=len(partners),
            )
            return result

        partner_id = int(partners[0]["id"])
        match_source = str(partners[0].get("match_source") or "cascade")

        # Lernschleife R6: bestaetigten Kaskaden-Treffer als Mapping speichern,
        # damit der naechste Beleg derselben Entity direkt matcht.
        if business_entity_id is not None and mapping is None:
            db.add(
                ERPEntityMapping(
                    connection_id=connection.id,
                    entity_type="supplier",
                    local_id=business_entity_id,
                    remote_id=str(partner_id),
                    last_synced_at=utc_now(),
                )
            )

    # --- Draft bauen ---
    ref = _build_ref(invoice, document_id)
    draft = OdooVendorBillDraft(
        partner_id=partner_id,
        invoice_date=_parse_invoice_date(invoice),
        ref=ref,
        amount_total_brutto=amount,
        currency=_build_currency(invoice),
        line_name=f"Eingangsrechnung {ref} — automatisch aus Ablage-System (OCR)",
        narration=(
            "Automatisch erzeugt aus dem Ablage-System "
            f"(Quelle: {doc_meta.get('import_source')}). "
            f"Dokument-UUID: {document_id}. Betragsquelle: {amount_source}."
        ),
    )

    # --- Original-PDF aus dem Storage (Archiv ist die fuehrende Quelle) ---
    try:
        pdf_content = await _load_pdf(document)
    except Exception as exc:
        logger.error(
            "odoo_vendor_bill_push_pdf_load_failed",
            document_id=str(document_id),
            **safe_error_log(exc),
        )
        pdf_content = None
    if pdf_content is None:
        result = PushResult(
            status="error",
            reason="Original-Dokument nicht aus dem Storage ladbar",
            retryable=True,
        )
        if is_final_attempt:
            _apply_push_metadata(document, result)
            _apply_review_task(document, result.reason or "")
            await db.commit()
        return result

    # --- Push nach Odoo (create ohne state => impliziter Entwurf) ---
    move_id = await connector.create_vendor_bill_draft(
        draft,
        pdf_content=pdf_content,
        pdf_filename=document.original_filename or document.filename or f"{document_id}.pdf",
    )

    if move_id is None:
        result = PushResult(
            status="error",
            reason="Odoo-Entwurf konnte nicht angelegt werden",
            retryable=True,
        )
        if is_final_attempt:
            _apply_push_metadata(document, result)
            _apply_review_task(document, result.reason or "")
            await db.commit()
        return result

    result = PushResult(
        status="pushed",
        odoo_move_id=str(move_id),
        partner_match_source=match_source,
    )
    _apply_push_metadata(document, result)
    await db.commit()

    # PII-Regel: KEINE Betraege/IBANs/USt-Ids/Namen im Log — nur IDs/Quellen.
    logger.info(
        "odoo_vendor_bill_pushed",
        document_id=str(document_id),
        odoo_move_id=str(move_id),
        partner_match_source=match_source,
        amount_source=amount_source,
    )
    return result
