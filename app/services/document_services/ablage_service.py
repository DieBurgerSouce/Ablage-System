"""Ablage Service - Kategorie-basierte Dokumentenverwaltung.

Enthaelt:
- get_category_documents: Gefilterte Dokumentenliste fuer Kategorie-Ansicht
- get_category_aggregations: Aggregierte Statistiken (Summen, Anzahlen)
- bulk_download_zip: Mehrere Dokumente als ZIP herunterladen
- bulk_export_csv: Metadaten als CSV exportieren
- update_payment_status: Zahlungsstatus aktualisieren
- bulk_mark_as_paid: Mehrere Dokumente als bezahlt markieren
- bulk_move_category: Dokumente in andere Kategorie verschieben
- bulk_set_tags: Tags setzen/entfernen

JSONB-Filterung auf extracted_data fuer:
- document_number, document_date, total_amount
- payment_status, paid_amount, due_date
"""

import io
import csv
import zipfile
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, cast, String, literal_column, Numeric
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import JSONB
import re

from app.db.models import Document, Tag, ProcessingStatus
from app.db.schemas import (
    DocumentType,
    DocumentPaymentStatus,
    EntityType,
    CategoryDocumentFilter,
    CategoryDocumentResponse,
    CategoryDocumentListResponse,
    CategoryAggregations,
    BulkOperationResultAblage,
    UpdatePaymentStatusResponse,
    TagOperation,
)
from app.services.document_services.base import DocumentServiceBase
from app.services.storage_service import get_storage_service

logger = structlog.get_logger(__name__)


# Security: Whitelist of allowed JSONB column and key names
_ALLOWED_JSONB_COLUMNS = frozenset({"extracted_data", "document_metadata"})
_ALLOWED_JSONB_KEYS = frozenset({
    # document_metadata keys
    "business_entity_id", "folder_id", "entity_type",
    # extracted_data keys
    "payment_status", "total_amount", "paid_amount", "due_date",
    "document_date", "document_number", "invoice_number",
})
_SAFE_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def jsonb_text(column_name: str, key: str) -> literal_column:
    """Helper: Extrahiert Text aus JSONB mit PostgreSQL ->> Operator.

    Umgeht das Problem mit CrossDBJSON TypeDecorator und .astext.
    Uses the ->> operator which returns text directly.

    Security: Validates column_name and key against whitelist.
    """
    if column_name not in _ALLOWED_JSONB_COLUMNS:
        if not _SAFE_IDENTIFIER_PATTERN.match(column_name):
            raise ValueError(f"Invalid JSONB column name: {column_name}")

    if key not in _ALLOWED_JSONB_KEYS:
        if not _SAFE_IDENTIFIER_PATTERN.match(key):
            raise ValueError(f"Invalid JSONB key: {key}")

    return literal_column(f"{column_name}->>'{key}'")


def jsonb_numeric(column_name: str, key: str) -> cast:
    """Helper: Extrahiert numerischen Wert aus JSONB und castet zu NUMERIC.

    Verwendet ->> Operator (Text) und castet dann zu NUMERIC.
    Gibt NULL zurueck wenn der Wert nicht numerisch ist.

    Security: Validates column_name and key against whitelist.
    """
    if column_name not in _ALLOWED_JSONB_COLUMNS:
        if not _SAFE_IDENTIFIER_PATTERN.match(column_name):
            raise ValueError(f"Invalid JSONB column name: {column_name}")

    if key not in _ALLOWED_JSONB_KEYS:
        if not _SAFE_IDENTIFIER_PATTERN.match(key):
            raise ValueError(f"Invalid JSONB key: {key}")

    # ->> gibt Text zurueck, dann casten zu NUMERIC
    # NULLIF verhindert Fehler bei leeren Strings
    return cast(
        func.nullif(literal_column(f"{column_name}->>'{key}'"), ''),
        Numeric
    )


def jsonb_exists(column_name: str, key: str) -> literal_column:
    """Helper: Prueft ob ein Key in JSONB existiert und nicht null ist.

    Verwendet PostgreSQL ? Operator fuer Existenz-Pruefung.
    """
    if column_name not in _ALLOWED_JSONB_COLUMNS:
        if not _SAFE_IDENTIFIER_PATTERN.match(column_name):
            raise ValueError(f"Invalid JSONB column name: {column_name}")

    if key not in _ALLOWED_JSONB_KEYS:
        if not _SAFE_IDENTIFIER_PATTERN.match(key):
            raise ValueError(f"Invalid JSONB key: {key}")

    # Prueft ob Key existiert UND nicht null ist
    return literal_column(f"({column_name}->'{key}') IS NOT NULL")


# Mapping von Kategorie-Slugs zu DocumentType-Enums
CATEGORY_TO_DOCTYPE: Dict[str, DocumentType] = {
    "rechnungen": DocumentType.INVOICE,
    "angebote": DocumentType.OTHER,  # TODO: Add OFFER to DocumentType
    "bestellungen": DocumentType.ORDER,
    "vertraege": DocumentType.CONTRACT,
    "lieferscheine": DocumentType.DELIVERY_NOTE,
    "quittungen": DocumentType.RECEIPT,
    "briefe": DocumentType.LETTER,
    "berichte": DocumentType.REPORT,
    "formulare": DocumentType.FORM,
    "sonstiges": DocumentType.OTHER,
}


class AblageService(DocumentServiceBase):
    """Service fuer Kategorie-basierte Dokumentenverwaltung.

    Ermoeglicht gefilterte Dokumentenlisten, Aggregationen und
    Bulk-Operationen fuer die Ablage-Ansicht im Frontend.
    """

    def __init__(self):
        """Initialisiere Ablage-Service."""
        self._storage_service = None

    @property
    def storage_service(self):
        """Lazy-Loading fuer Storage-Service."""
        if self._storage_service is None:
            self._storage_service = get_storage_service()
        return self._storage_service

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_category_documents(
        self,
        db: AsyncSession,
        user_id: UUID,
        filter_params: CategoryDocumentFilter,
    ) -> CategoryDocumentListResponse:
        """Dokumente fuer eine Kategorie mit umfangreicher Filterung abrufen.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers (fuer Zugriffskontrolle)
            filter_params: Filterparameter (Kategorie, Datum, Betrag, etc.)

        Returns:
            CategoryDocumentListResponse mit paginierten Ergebnissen
        """
        # Basis-Query
        query = (
            select(Document)
            .where(Document.owner_id == user_id)
            .where(Document.deleted_at.is_(None))
        )
        count_query = (
            select(func.count(Document.id))
            .where(Document.owner_id == user_id)
            .where(Document.deleted_at.is_(None))
        )

        # Filter-Bedingungen aufbauen
        conditions = self._build_category_filter_conditions(filter_params)
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # Gesamtanzahl ermitteln
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Sortierung
        sort_column = self._get_sort_column_for_category(filter_params.sort_by)
        if filter_params.sort_order == "desc":
            query = query.order_by(sort_column.desc().nulls_last())
        else:
            query = query.order_by(sort_column.asc().nulls_first())

        # Pagination
        offset = filter_params.page * filter_params.page_size
        query = query.offset(offset).limit(filter_params.page_size)

        # Tags eager-loaden
        query = query.options(selectinload(Document.tags))

        # Ausfuehren
        result = await db.execute(query)
        documents = result.scalars().all()

        total_pages = math.ceil(total / filter_params.page_size) if total > 0 else 0

        return CategoryDocumentListResponse(
            items=[self._to_category_response(doc) for doc in documents],
            total=total,
            page=filter_params.page,
            page_size=filter_params.page_size,
            total_pages=total_pages,
            filters_applied=filter_params.model_dump(exclude_none=True),
        )

    async def get_category_aggregations(
        self,
        db: AsyncSession,
        user_id: UUID,
        business_entity_id: UUID,
        folder_id: str,
        category: str,
        entity_type: EntityType = EntityType.CUSTOMER,
    ) -> CategoryAggregations:
        """Aggregierte Statistiken fuer eine Kategorie berechnen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            business_entity_id: Geschaeftspartner-ID
            folder_id: Ordner-ID
            category: Kategorie-Slug
            entity_type: Kunde oder Lieferant

        Returns:
            CategoryAggregations mit Summen und Anzahlen
        """
        # Basis-Query fuer die Kategorie
        base_conditions = [
            Document.owner_id == user_id,
            Document.deleted_at.is_(None),
        ]

        # Kategorie-Filter
        doc_type = CATEGORY_TO_DOCTYPE.get(category.lower())
        if doc_type:
            base_conditions.append(Document.document_type == doc_type.value)

        # Business-Entity direkt aus Document-Spalte filtern
        base_conditions.append(
            Document.business_entity_id == business_entity_id
        )
        base_conditions.append(
            jsonb_text("document_metadata", "folder_id") == folder_id
        )

        # Gesamtanzahl
        total_query = select(func.count(Document.id)).where(and_(*base_conditions))
        total_result = await db.execute(total_query)
        total_documents = total_result.scalar() or 0

        # Status-Verteilung
        status_query = (
            select(Document.status, func.count(Document.id))
            .where(and_(*base_conditions))
            .group_by(Document.status)
        )
        status_result = await db.execute(status_query)
        documents_by_status = {row[0]: row[1] for row in status_result.all()}

        # Zahlungsstatus-Verteilung (aus extracted_data)
        payment_status_col = jsonb_text("extracted_data", "payment_status")
        payment_status_query = (
            select(
                payment_status_col,
                func.count(Document.id)
            )
            .where(and_(*base_conditions))
            .where(jsonb_exists("extracted_data", "payment_status"))
            .group_by(payment_status_col)
        )
        payment_result = await db.execute(payment_status_query)
        documents_by_payment_status = {row[0]: row[1] for row in payment_result.all()}

        # Betrags-Aggregationen (verwende jsonb_numeric fuer korrekte Typisierung)
        total_amount_numeric = jsonb_numeric("extracted_data", "total_amount")
        paid_amount_numeric = jsonb_numeric("extracted_data", "paid_amount")
        amounts_query = (
            select(
                func.coalesce(func.sum(total_amount_numeric), 0).label("total"),
                func.coalesce(func.sum(paid_amount_numeric), 0).label("paid"),
            )
            .where(and_(*base_conditions))
        )

        # Separate Query fuer ueberfaellige Betraege
        today = datetime.now(timezone.utc).date().isoformat()
        due_date_col = jsonb_text("extracted_data", "due_date")
        overdue_conditions = base_conditions + [
            payment_status_col == "offen",
            due_date_col < today,
        ]

        overdue_query = (
            select(
                func.count(Document.id),
                func.coalesce(func.sum(total_amount_numeric), 0)
            )
            .where(and_(*overdue_conditions))
        )

        try:
            amounts_result = await db.execute(amounts_query)
            amounts_row = amounts_result.first()
            total_amount = float(amounts_row[0] or 0) if amounts_row else 0.0
            total_paid = float(amounts_row[1] or 0) if amounts_row else 0.0
        except Exception as e:
            logger.warning("aggregation_amounts_failed", error=str(e))
            total_amount = 0.0
            total_paid = 0.0

        try:
            overdue_result = await db.execute(overdue_query)
            overdue_row = overdue_result.first()
            overdue_count = overdue_row[0] if overdue_row else 0
            total_overdue = float(overdue_row[1] or 0) if overdue_row else 0.0
        except Exception as e:
            logger.warning("aggregation_overdue_failed", error=str(e))
            overdue_count = 0
            total_overdue = 0.0

        # Datums-Range
        date_range_query = (
            select(
                func.min(Document.created_at),
                func.max(Document.created_at)
            )
            .where(and_(*base_conditions))
        )
        date_result = await db.execute(date_range_query)
        date_row = date_result.first()

        return CategoryAggregations(
            total_documents=total_documents,
            documents_by_status=documents_by_status,
            documents_by_payment_status=documents_by_payment_status,
            total_amount=total_amount,
            total_paid=total_paid,
            total_open=total_amount - total_paid,
            total_overdue=total_overdue,
            currency="EUR",
            earliest_date=date_row[0] if date_row and date_row[0] else None,
            latest_date=date_row[1] if date_row and date_row[1] else None,
            overdue_count=overdue_count,
        )

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    async def bulk_download_zip(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_ids: List[UUID],
        filename: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Mehrere Dokumente als ZIP-Archiv herunterladen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Liste der Dokument-IDs
            filename: Optionaler Dateiname fuer das ZIP

        Returns:
            Tuple aus (ZIP-Bytes, Dateiname)
        """
        # Dokumente laden
        query = (
            select(Document)
            .where(and_(
                Document.id.in_(document_ids),
                Document.owner_id == user_id,
                Document.deleted_at.is_(None)
            ))
        )
        result = await db.execute(query)
        documents = result.scalars().all()

        if not documents:
            raise ValueError("Keine Dokumente gefunden")

        # ZIP erstellen
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for doc in documents:
                try:
                    # Datei aus Storage laden
                    file_data = await self.storage_service.download_document(doc.file_path)
                    # Mit Original-Dateinamen ins ZIP
                    zip_file.writestr(
                        doc.original_filename or doc.filename,
                        file_data
                    )
                except Exception as e:
                    logger.error(
                        "zip_download_file_failed",
                        document_id=str(doc.id),
                        error=str(e)
                    )
                    # Fehler-Platzhalter
                    zip_file.writestr(
                        f"FEHLER_{doc.filename}.txt",
                        f"Fehler beim Download: {str(e)}"
                    )

        zip_buffer.seek(0)
        zip_bytes = zip_buffer.getvalue()

        # Dateiname generieren
        if not filename:
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"dokumente_{date_str}.zip"

        logger.info(
            "bulk_zip_created",
            user_id=str(user_id),
            document_count=len(documents),
            zip_size=len(zip_bytes)
        )

        return zip_bytes, filename

    async def bulk_export_csv(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_ids: List[UUID],
        columns: Optional[List[str]] = None,
        include_amounts: bool = True,
        include_dates: bool = True,
        delimiter: str = ";",
    ) -> Tuple[bytes, str]:
        """Dokument-Metadaten als CSV exportieren.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Dokument-IDs
            columns: Spezifische Spalten (None = alle)
            include_amounts: Betraege inkludieren
            include_dates: Daten inkludieren
            delimiter: CSV-Trennzeichen

        Returns:
            Tuple aus (CSV-Bytes, Dateiname)
        """
        # Dokumente laden
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(
                Document.id.in_(document_ids),
                Document.owner_id == user_id,
                Document.deleted_at.is_(None)
            ))
            .order_by(Document.created_at.desc())
        )
        result = await db.execute(query)
        documents = result.scalars().all()

        # Standard-Spalten
        default_columns = [
            "id", "dateiname", "dokumenttyp", "status", "erstellt_am"
        ]
        if include_amounts:
            default_columns.extend([
                "dokumentnummer", "gesamtbetrag", "waehrung",
                "zahlungsstatus", "bezahlt_am"
            ])
        if include_dates:
            default_columns.extend(["dokumentdatum", "faelligkeitsdatum"])

        default_columns.append("tags")

        # Spalten ueberschreiben falls spezifiziert
        csv_columns = columns if columns else default_columns

        # CSV erstellen
        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter, quoting=csv.QUOTE_ALL)

        # Header
        writer.writerow(csv_columns)

        # Zeilen
        for doc in documents:
            extracted = doc.extracted_data or {}
            row = []

            for col in csv_columns:
                value = self._get_csv_value(doc, extracted, col)
                row.append(value)

            writer.writerow(row)

        csv_content = output.getvalue()
        csv_bytes = csv_content.encode("utf-8-sig")  # BOM fuer Excel

        # Dateiname
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"export_{date_str}.csv"

        logger.info(
            "bulk_csv_exported",
            user_id=str(user_id),
            document_count=len(documents),
            columns=csv_columns
        )

        return csv_bytes, filename

    async def update_payment_status(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_id: UUID,
        status: DocumentPaymentStatus,
        paid_amount: Optional[float] = None,
        payment_date: Optional[datetime] = None,
    ) -> UpdatePaymentStatusResponse:
        """Zahlungsstatus eines Dokuments aktualisieren.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_id: Dokument-ID
            status: Neuer Zahlungsstatus
            paid_amount: Bezahlter Betrag (bei Teilzahlung)
            payment_date: Zahlungsdatum

        Returns:
            UpdatePaymentStatusResponse mit altem und neuem Status
        """
        # Dokument laden
        query = select(Document).where(and_(
            Document.id == document_id,
            Document.owner_id == user_id,
            Document.deleted_at.is_(None)
        ))
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            raise ValueError("Dokument nicht gefunden")

        # Alten Status speichern
        extracted = doc.extracted_data or {}
        old_status_str = extracted.get("payment_status", "offen")
        try:
            old_status = DocumentPaymentStatus(old_status_str)
        except ValueError:
            old_status = DocumentPaymentStatus.OFFEN

        # Neue Werte setzen
        extracted["payment_status"] = status.value

        if status == DocumentPaymentStatus.BEZAHLT:
            # Bei bezahlt: Gesamtbetrag als bezahlt markieren
            total = extracted.get("total_amount")
            if total:
                extracted["paid_amount"] = total
            extracted["payment_date"] = (
                payment_date or datetime.now(timezone.utc)
            ).isoformat()

        elif status == DocumentPaymentStatus.TEILBEZAHLT:
            if paid_amount is not None:
                extracted["paid_amount"] = paid_amount
            if payment_date:
                extracted["payment_date"] = payment_date.isoformat()

        elif status == DocumentPaymentStatus.OFFEN:
            extracted["paid_amount"] = None
            extracted["payment_date"] = None

        # Speichern
        doc.extracted_data = extracted
        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()

        # Cache invalidieren
        await self._invalidate_document_cache(document_id, user_id, "payment_status_updated")

        logger.info(
            "payment_status_updated",
            document_id=str(document_id),
            old_status=old_status.value,
            new_status=status.value
        )

        return UpdatePaymentStatusResponse(
            document_id=document_id,
            old_status=old_status,
            new_status=status,
            paid_amount=paid_amount,
            payment_date=payment_date,
            message=f"Zahlungsstatus von '{old_status.value}' auf '{status.value}' geaendert"
        )

    async def bulk_mark_as_paid(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_ids: List[UUID],
        payment_date: Optional[datetime] = None,
    ) -> BulkOperationResultAblage:
        """Mehrere Dokumente als bezahlt markieren.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Dokument-IDs
            payment_date: Zahlungsdatum (Standard: jetzt)

        Returns:
            BulkOperationResultAblage mit Erfolg/Fehler-Statistik
        """
        if not payment_date:
            payment_date = datetime.now(timezone.utc)

        success_count = 0
        failed_count = 0
        failed_ids: List[UUID] = []
        errors: List[str] = []

        for doc_id in document_ids:
            try:
                await self.update_payment_status(
                    db=db,
                    user_id=user_id,
                    document_id=doc_id,
                    status=DocumentPaymentStatus.BEZAHLT,
                    payment_date=payment_date
                )
                success_count += 1
            except Exception as e:
                failed_count += 1
                failed_ids.append(doc_id)
                errors.append(f"{doc_id}: {str(e)}")
                logger.warning(
                    "bulk_mark_paid_failed",
                    document_id=str(doc_id),
                    error=str(e)
                )

        return BulkOperationResultAblage(
            success=failed_count == 0,
            operation="mark_as_paid",
            success_count=success_count,
            failed_count=failed_count,
            failed_ids=failed_ids,
            errors=errors,
            message=f"{success_count} Dokumente als bezahlt markiert"
            + (f", {failed_count} fehlgeschlagen" if failed_count > 0 else "")
        )

    async def bulk_delete(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_ids: List[UUID],
        reason: Optional[str] = None,
    ) -> BulkOperationResultAblage:
        """Mehrere Dokumente soft-loeschen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Dokument-IDs
            reason: Optionaler Loeschgrund

        Returns:
            BulkOperationResultAblage
        """
        # Dokumente laden
        query = select(Document).where(and_(
            Document.id.in_(document_ids),
            Document.owner_id == user_id,
            Document.deleted_at.is_(None)
        ))
        result = await db.execute(query)
        documents = result.scalars().all()

        found_ids = {doc.id for doc in documents}
        not_found = [doc_id for doc_id in document_ids if doc_id not in found_ids]

        success_count = 0
        failed_count = len(not_found)
        failed_ids = list(not_found)
        errors = [f"{doc_id}: Nicht gefunden" for doc_id in not_found]

        now = datetime.now(timezone.utc)
        for doc in documents:
            try:
                doc.is_deleted = True
                doc.deleted_at = now
                doc.deleted_by_id = user_id
                doc.deletion_reason = reason
                success_count += 1
            except Exception as e:
                failed_count += 1
                failed_ids.append(doc.id)
                errors.append(f"{doc.id}: {str(e)}")

        await db.commit()

        # Cache invalidieren
        await self._invalidate_user_cache(user_id, "bulk_delete")

        logger.info(
            "bulk_delete_completed",
            user_id=str(user_id),
            success_count=success_count,
            failed_count=failed_count
        )

        return BulkOperationResultAblage(
            success=failed_count == 0,
            operation="delete",
            success_count=success_count,
            failed_count=failed_count,
            failed_ids=failed_ids,
            errors=errors,
            message=f"{success_count} Dokumente geloescht"
            + (f", {failed_count} fehlgeschlagen" if failed_count > 0 else "")
        )

    async def bulk_move_category(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_ids: List[UUID],
        target_category: str,
    ) -> BulkOperationResultAblage:
        """Dokumente in andere Kategorie verschieben.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Dokument-IDs
            target_category: Ziel-Kategorie (Slug)

        Returns:
            BulkOperationResultAblage
        """
        target_doc_type = CATEGORY_TO_DOCTYPE.get(target_category.lower())
        if not target_doc_type:
            raise ValueError(f"Unbekannte Kategorie: {target_category}")

        # Dokumente laden
        query = select(Document).where(and_(
            Document.id.in_(document_ids),
            Document.owner_id == user_id,
            Document.deleted_at.is_(None)
        ))
        result = await db.execute(query)
        documents = result.scalars().all()

        success_count = 0
        failed_count = 0
        failed_ids: List[UUID] = []
        errors: List[str] = []

        for doc in documents:
            try:
                doc.document_type = target_doc_type.value
                doc.updated_at = datetime.now(timezone.utc)
                success_count += 1
            except Exception as e:
                failed_count += 1
                failed_ids.append(doc.id)
                errors.append(f"{doc.id}: {str(e)}")

        # Nicht gefundene IDs
        found_ids = {doc.id for doc in documents}
        for doc_id in document_ids:
            if doc_id not in found_ids:
                failed_count += 1
                failed_ids.append(doc_id)
                errors.append(f"{doc_id}: Nicht gefunden")

        await db.commit()

        logger.info(
            "bulk_move_category_completed",
            user_id=str(user_id),
            target_category=target_category,
            success_count=success_count
        )

        return BulkOperationResultAblage(
            success=failed_count == 0,
            operation="move_category",
            success_count=success_count,
            failed_count=failed_count,
            failed_ids=failed_ids,
            errors=errors,
            message=f"{success_count} Dokumente nach '{target_category}' verschoben"
        )

    async def bulk_set_tags(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_ids: List[UUID],
        tags: List[str],
        mode: TagOperation = TagOperation.ADD,
    ) -> BulkOperationResultAblage:
        """Tags fuer mehrere Dokumente setzen/entfernen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Dokument-IDs
            tags: Tag-Namen
            mode: ADD, REMOVE, oder SET

        Returns:
            BulkOperationResultAblage
        """
        # Tags vorbereiten
        tag_objects = await self._ensure_tags_exist(db, tags)
        tag_set = set(tag_objects)

        # Dokumente laden
        query = (
            select(Document)
            .options(selectinload(Document.tags))
            .where(and_(
                Document.id.in_(document_ids),
                Document.owner_id == user_id,
                Document.deleted_at.is_(None)
            ))
        )
        result = await db.execute(query)
        documents = result.scalars().all()

        success_count = 0
        failed_count = 0
        failed_ids: List[UUID] = []
        errors: List[str] = []

        for doc in documents:
            try:
                if mode == TagOperation.ADD:
                    current_tags = set(doc.tags)
                    doc.tags = list(current_tags | tag_set)
                elif mode == TagOperation.REMOVE:
                    doc.tags = [t for t in doc.tags if t not in tag_set]
                elif mode == TagOperation.SET:
                    doc.tags = list(tag_set)

                doc.updated_at = datetime.now(timezone.utc)
                success_count += 1
            except Exception as e:
                failed_count += 1
                failed_ids.append(doc.id)
                errors.append(f"{doc.id}: {str(e)}")

        await db.commit()

        logger.info(
            "bulk_set_tags_completed",
            user_id=str(user_id),
            mode=mode.value,
            tags=tags,
            success_count=success_count
        )

        return BulkOperationResultAblage(
            success=failed_count == 0,
            operation=f"tags_{mode.value}",
            success_count=success_count,
            failed_count=failed_count,
            failed_ids=failed_ids,
            errors=errors,
            message=f"Tags fuer {success_count} Dokumente aktualisiert"
        )

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _build_category_filter_conditions(
        self,
        filter_params: CategoryDocumentFilter
    ) -> List:
        """Filter-Bedingungen fuer Kategorie-Query aufbauen."""
        conditions = []

        # Kategorie zu DocumentType mappen
        doc_type = CATEGORY_TO_DOCTYPE.get(filter_params.category.lower())
        if doc_type:
            conditions.append(Document.document_type == doc_type.value)

        # Business-Entity direkt aus Document-Spalte filtern
        conditions.append(
            Document.business_entity_id == filter_params.business_entity_id
        )
        conditions.append(
            jsonb_text("document_metadata", "folder_id") == filter_params.folder_id
        )

        # Entity-Type
        conditions.append(
            jsonb_text("document_metadata", "entity_type") == filter_params.entity_type.value
        )

        # Textsuche - use literal_column with ILIKE for JSONB text search
        if filter_params.search:
            search_term = f"%{filter_params.search}%"
            # For JSONB text search, we need to use raw SQL ILIKE
            doc_number_search = literal_column(f"extracted_data->>'document_number' ILIKE '{search_term}'")
            conditions.append(
                or_(
                    Document.filename.ilike(search_term),
                    Document.original_filename.ilike(search_term),
                    doc_number_search,
                )
            )

        # Datumsfilter auf extracted_data.document_date
        document_date_col = jsonb_text("extracted_data", "document_date")
        if filter_params.date_from:
            conditions.append(
                document_date_col >= filter_params.date_from.isoformat()
            )
        if filter_params.date_to:
            conditions.append(
                document_date_col <= filter_params.date_to.isoformat()
            )

        # Betragsfilter (verwende jsonb_numeric fuer korrekte numerische Vergleiche)
        total_amount_numeric = jsonb_numeric("extracted_data", "total_amount")
        if filter_params.amount_min is not None:
            conditions.append(
                total_amount_numeric >= filter_params.amount_min
            )
        if filter_params.amount_max is not None:
            conditions.append(
                total_amount_numeric <= filter_params.amount_max
            )

        # Verarbeitungsstatus
        if filter_params.processing_status:
            status_values = [s.value for s in filter_params.processing_status]
            conditions.append(Document.status.in_(status_values))

        # Zahlungsstatus
        if filter_params.payment_status:
            status_values = [s.value for s in filter_params.payment_status]
            payment_status_col = jsonb_text("extracted_data", "payment_status")
            conditions.append(
                payment_status_col.in_(status_values)
            )

        # Tags
        if filter_params.tags:
            # Dokumente mit mindestens einem der Tags
            conditions.append(
                Document.tags.any(Tag.name.in_(filter_params.tags))
            )

        return conditions

    def _get_sort_column_for_category(self, sort_by: str):
        """Spalte fuer Sortierung ermitteln."""
        sort_map = {
            "document_date": jsonb_text("extracted_data", "document_date"),
            "created_at": Document.created_at,
            "filename": Document.filename,
            "total_amount": jsonb_text("extracted_data", "total_amount"),
            "due_date": jsonb_text("extracted_data", "due_date"),
            "payment_status": jsonb_text("extracted_data", "payment_status"),
        }
        return sort_map.get(sort_by, Document.created_at)

    def _to_category_response(self, doc: Document) -> CategoryDocumentResponse:
        """Document zu CategoryDocumentResponse konvertieren."""
        extracted = doc.extracted_data or {}

        # Zahlungsstatus parsen
        payment_status_str = extracted.get("payment_status", "offen")
        try:
            payment_status = DocumentPaymentStatus(payment_status_str)
        except ValueError:
            payment_status = DocumentPaymentStatus.OFFEN

        # Datumsfelder parsen
        doc_date = None
        if extracted.get("document_date"):
            try:
                doc_date = datetime.fromisoformat(extracted["document_date"])
            except (ValueError, TypeError):
                pass

        due_date = None
        if extracted.get("due_date"):
            try:
                due_date = datetime.fromisoformat(extracted["due_date"])
            except (ValueError, TypeError):
                pass

        return CategoryDocumentResponse(
            id=doc.id,
            filename=doc.filename,
            original_filename=doc.original_filename or doc.filename,
            document_type=DocumentType(doc.document_type) if doc.document_type else DocumentType.OTHER,
            processing_status=ProcessingStatus(doc.status),
            file_size=doc.file_size or 0,
            page_count=doc.page_count or 0,
            mime_type=doc.mime_type,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            document_date=doc_date,
            ocr_confidence=doc.ocr_confidence,
            document_number=extracted.get("document_number"),
            total_amount=extracted.get("total_amount"),
            currency=extracted.get("currency", "EUR"),
            due_date=due_date,
            payment_status=payment_status,
            paid_amount=extracted.get("paid_amount"),
            partner_name=extracted.get("partner_name"),
            tags=[t.name for t in doc.tags] if doc.tags else [],
        )

    def _get_csv_value(
        self,
        doc: Document,
        extracted: Dict[str, Any],
        column: str
    ) -> str:
        """Wert fuer CSV-Spalte ermitteln."""
        column_map = {
            "id": str(doc.id),
            "dateiname": doc.original_filename or doc.filename,
            "dokumenttyp": doc.document_type or "other",
            "status": doc.status,
            "erstellt_am": doc.created_at.isoformat() if doc.created_at else "",
            "dokumentnummer": extracted.get("document_number", ""),
            "gesamtbetrag": str(extracted.get("total_amount", "")),
            "waehrung": extracted.get("currency", "EUR"),
            "zahlungsstatus": extracted.get("payment_status", "offen"),
            "bezahlt_am": extracted.get("payment_date", ""),
            "dokumentdatum": extracted.get("document_date", ""),
            "faelligkeitsdatum": extracted.get("due_date", ""),
            "tags": ", ".join([t.name for t in doc.tags]) if doc.tags else "",
        }
        return column_map.get(column, "")


# Singleton-Instanz
_ablage_service_instance: Optional[AblageService] = None


def get_ablage_service() -> AblageService:
    """Ablage-Service-Instanz abrufen (Singleton)."""
    global _ablage_service_instance
    if _ablage_service_instance is None:
        _ablage_service_instance = AblageService()
    return _ablage_service_instance
