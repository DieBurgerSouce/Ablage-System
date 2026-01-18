# -*- coding: utf-8 -*-
"""
Magic Buttons Service.

Ein-Klick-Aktionen fuer Enterprise-Workflows:
- Tages-Abschluss: Alle heutigen Belege verarbeiten
- Monats-Report: Steuerberater-Export mit einem Klick
- Offene Posten: Zahlungsabgleich + Mahnungen
- Neuen Kontakt: Entity aus Dokument erstellen

Jede Magic-Button-Aktion:
1. Sammelt Kontext
2. Zeigt Vorschau (optional)
3. Fuehrt Batch-Operationen aus
4. Gibt strukturiertes Ergebnis zurueck
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    BankTransaction,
    InvoiceTracking,
    BusinessEntity,
    PaymentTransaction,
)
from app.core.datetime_utils import utc_now


logger = structlog.get_logger(__name__)


class MagicButtonType(str, Enum):
    """Typ der Magic-Button-Aktion."""
    DAILY_CLOSE = "daily_close"              # Tages-Abschluss
    MONTHLY_REPORT = "monthly_report"        # Monats-Report fuer Steuerberater
    CLEAR_OPEN_ITEMS = "clear_open_items"    # Offene Posten bereinigen
    CREATE_CONTACT = "create_contact"        # Neuen Kontakt aus Dokument


class MagicButtonStatus(str, Enum):
    """Status einer Magic-Button-Aktion."""
    PENDING = "pending"
    PREVIEW = "preview"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class MagicButtonPreview:
    """Vorschau fuer eine Magic-Button-Aktion."""
    button_type: MagicButtonType
    title: str
    description: str

    # Was wird verarbeitet
    document_count: int = 0
    transaction_count: int = 0
    entity_count: int = 0
    invoice_count: int = 0

    # Geschaetzte Werte
    estimated_amount: Decimal = Decimal("0.00")
    estimated_duration_seconds: int = 0

    # Warnungen
    warnings: List[str] = field(default_factory=list)

    # Details zur Vorschau
    items: List[Dict[str, Any]] = field(default_factory=list)

    # Kann ausgefuehrt werden?
    can_execute: bool = True
    block_reason: Optional[str] = None


@dataclass
class MagicButtonResult:
    """Ergebnis einer Magic-Button-Aktion."""
    button_type: MagicButtonType
    status: MagicButtonStatus
    title: str
    message: str

    # Statistiken
    processed_count: int = 0
    success_count: int = 0
    error_count: int = 0
    skipped_count: int = 0

    # Betraege
    total_amount: Decimal = Decimal("0.00")

    # Details
    details: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Dauer
    duration_ms: int = 0

    # Generierte Dateien/Exporte
    export_file_id: Optional[str] = None
    export_filename: Optional[str] = None


class MagicButtonsService:
    """Service fuer Ein-Klick-Aktionen."""

    # ==========================================================================
    # TAGES-ABSCHLUSS
    # ==========================================================================

    async def preview_daily_close(
        self,
        db: AsyncSession,
        company_id: UUID,
        target_date: Optional[date] = None,
    ) -> MagicButtonPreview:
        """Vorschau fuer Tages-Abschluss.

        Zeigt:
        - Unverarbeitete Dokumente von heute
        - Unabgeglichene Transaktionen
        - Offene One-Click-Items
        """
        target_date = target_date or date.today()
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        preview = MagicButtonPreview(
            button_type=MagicButtonType.DAILY_CLOSE,
            title="Tages-Abschluss",
            description=f"Verarbeitet alle Belege vom {target_date.strftime('%d.%m.%Y')}",
        )

        # 1. Unverarbeitete Dokumente von heute
        doc_query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= start_of_day,
                Document.created_at <= end_of_day,
                Document.deleted_at.is_(None),
                # Nur Dokumente ohne Entity-Zuweisung
                Document.business_entity_id.is_(None),
            )
        )
        doc_result = await db.execute(doc_query)
        unassigned_docs = doc_result.scalars().all()

        preview.document_count = len(unassigned_docs)

        # 2. Unabgeglichene Transaktionen
        # BankTransaction doesn't have company_id directly - filter by date and status
        from app.db.models import BankAccount
        trans_query = (
            select(BankTransaction)
            .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
            .where(
                and_(
                    BankTransaction.booking_date >= start_of_day,
                    BankTransaction.booking_date <= end_of_day,
                    BankTransaction.reconciliation_status.in_(["pending", "unmatched"]),
                )
            )
        )
        trans_result = await db.execute(trans_query)
        unmatched_trans = trans_result.scalars().all()

        preview.transaction_count = len(unmatched_trans)

        # Betraege summieren
        total = Decimal("0.00")
        for trans in unmatched_trans:
            if trans.amount:
                total += abs(trans.amount)
        preview.estimated_amount = total

        # Items fuer Vorschau
        preview.items = [
            {
                "type": "documents",
                "count": preview.document_count,
                "label": f"{preview.document_count} Dokumente ohne Zuordnung",
            },
            {
                "type": "transactions",
                "count": preview.transaction_count,
                "label": f"{preview.transaction_count} Transaktionen unabgeglichen",
            },
        ]

        # Warnungen
        if preview.document_count == 0 and preview.transaction_count == 0:
            preview.warnings.append("Keine offenen Posten fuer heute gefunden")

        # Dauer schaetzen (ca. 1s pro Dokument + 0.5s pro Transaktion)
        preview.estimated_duration_seconds = (
            preview.document_count * 1 +
            preview.transaction_count * 1
        )

        preview.can_execute = preview.document_count > 0 or preview.transaction_count > 0
        if not preview.can_execute:
            preview.block_reason = "Keine offenen Posten zum Verarbeiten"

        return preview

    async def execute_daily_close(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        target_date: Optional[date] = None,
        auto_match: bool = True,
        auto_assign: bool = True,
    ) -> MagicButtonResult:
        """Fuehrt Tages-Abschluss aus.

        1. Auto-Match Transaktionen (wenn aktiviert)
        2. Auto-Assign Dokumente zu Entities (wenn aktiviert)
        3. Erstellt Zusammenfassung
        """
        import time
        start_time = time.time()

        target_date = target_date or date.today()

        result = MagicButtonResult(
            button_type=MagicButtonType.DAILY_CLOSE,
            status=MagicButtonStatus.RUNNING,
            title="Tages-Abschluss",
            message=f"Verarbeite Belege vom {target_date.strftime('%d.%m.%Y')}...",
        )

        try:
            # 1. Auto-Match Transaktionen
            if auto_match:
                from app.services.banking.reconciliation_service import ReconciliationService
                reconciliation_service = ReconciliationService()

                batch_result = await reconciliation_service.batch_reconcile(
                    db=db,
                    user_id=user_id,
                    min_confidence=0.9,
                )

                result.details.append({
                    "step": "auto_match",
                    "processed": batch_result.total_processed,
                    "matched": batch_result.matched_count,
                    "skipped": batch_result.skipped_count,
                })
                result.success_count += batch_result.matched_count
                result.skipped_count += batch_result.skipped_count

            # 2. Auto-Assign Dokumente
            if auto_assign:
                from app.services.document_entity_linker_service import (
                    get_document_entity_linker_service
                )
                linker_service = get_document_entity_linker_service()

                # Dokumente von heute ohne Entity
                start_of_day = datetime.combine(target_date, datetime.min.time())
                end_of_day = datetime.combine(target_date, datetime.max.time())

                doc_query = select(Document).where(
                    and_(
                        Document.company_id == company_id,
                        Document.created_at >= start_of_day,
                        Document.created_at <= end_of_day,
                        Document.deleted_at.is_(None),
                        Document.business_entity_id.is_(None),
                    )
                )
                doc_result = await db.execute(doc_query)
                docs = doc_result.scalars().all()

                linked_count = 0
                for doc in docs:
                    try:
                        link_result = await linker_service.link_document(
                            db=db,
                            document_id=doc.id,
                            min_confidence=0.75,
                        )
                        if link_result and link_result.get("linked"):
                            linked_count += 1
                    except Exception as e:
                        result.errors.append(f"Dokument {doc.id}: {str(e)}")

                result.details.append({
                    "step": "auto_assign",
                    "processed": len(docs),
                    "linked": linked_count,
                })
                result.success_count += linked_count
                result.processed_count += len(docs)

            await db.commit()

            result.status = MagicButtonStatus.COMPLETED
            result.message = f"Tages-Abschluss erfolgreich: {result.success_count} Posten verarbeitet"

            if result.errors:
                result.status = MagicButtonStatus.PARTIAL
                result.message += f", {len(result.errors)} Fehler"

        except Exception as e:
            result.status = MagicButtonStatus.FAILED
            result.message = f"Tages-Abschluss fehlgeschlagen: {str(e)}"
            result.errors.append(str(e))
            logger.exception("daily_close_failed", company_id=str(company_id))

        result.duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "daily_close_completed",
            company_id=str(company_id),
            status=result.status.value,
            success_count=result.success_count,
            error_count=result.error_count,
            duration_ms=result.duration_ms,
        )

        return result

    # ==========================================================================
    # MONATS-REPORT
    # ==========================================================================

    async def preview_monthly_report(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
        month: int,
    ) -> MagicButtonPreview:
        """Vorschau fuer Monats-Report.

        Zeigt:
        - Anzahl Dokumente im Monat
        - Bereits exportierte vs. neue
        - Geschaetztes Export-Volumen
        """
        from calendar import monthrange

        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        preview = MagicButtonPreview(
            button_type=MagicButtonType.MONTHLY_REPORT,
            title="Monats-Report",
            description=f"Export fuer {first_day.strftime('%B %Y')}",
        )

        # Dokumente im Monat zaehlen
        start_dt = datetime.combine(first_day, datetime.min.time())
        end_dt = datetime.combine(last_day, datetime.max.time())

        doc_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= start_dt,
                Document.created_at <= end_dt,
                Document.deleted_at.is_(None),
                Document.document_type.in_(["invoice", "supplier_invoice", "receipt"]),
            )
        )
        doc_result = await db.execute(doc_query)
        preview.document_count = doc_result.scalar() or 0

        # Betraege summieren (aus extracted_data)
        amount_query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= start_dt,
                Document.created_at <= end_dt,
                Document.deleted_at.is_(None),
                Document.document_type.in_(["invoice", "supplier_invoice"]),
            )
        )
        amount_result = await db.execute(amount_query)
        docs = amount_result.scalars().all()

        total = Decimal("0.00")
        for doc in docs:
            if doc.extracted_data:
                amount = doc.extracted_data.get("total_amount") or doc.extracted_data.get("amount")
                if amount:
                    try:
                        total += Decimal(str(amount))
                    except:
                        pass

        preview.estimated_amount = total

        preview.items = [
            {
                "type": "invoices",
                "count": preview.document_count,
                "label": f"{preview.document_count} Belege zum Export",
            },
            {
                "type": "amount",
                "value": float(total),
                "label": f"Gesamtvolumen: {float(total):,.2f} EUR",
            },
        ]

        # Dauer schaetzen
        preview.estimated_duration_seconds = max(5, preview.document_count // 10)

        preview.can_execute = preview.document_count > 0
        if not preview.can_execute:
            preview.block_reason = "Keine exportierbaren Dokumente im Zeitraum"

        return preview

    async def execute_monthly_report(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        year: int,
        month: int,
        include_datev: bool = True,
        include_pdf_archive: bool = False,
    ) -> MagicButtonResult:
        """Erstellt Monats-Report.

        1. DATEV-Export erstellen
        2. Optional: PDF-Archiv erstellen
        3. Zusammenfassung generieren
        """
        import time
        from calendar import monthrange

        start_time = time.time()

        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        result = MagicButtonResult(
            button_type=MagicButtonType.MONTHLY_REPORT,
            status=MagicButtonStatus.RUNNING,
            title="Monats-Report",
            message=f"Erstelle Report fuer {first_day.strftime('%B %Y')}...",
        )

        try:
            # 1. DATEV-Export
            if include_datev:
                from app.services.datev import get_datev_export_service
                datev_service = get_datev_export_service()

                csv_bytes, export_record = await datev_service.export_buchungsstapel(
                    db=db,
                    user_id=user_id,
                    period_from=first_day,
                    period_to=last_day,
                )

                result.details.append({
                    "step": "datev_export",
                    "filename": export_record.filename,
                    "document_count": export_record.document_count,
                    "export_id": str(export_record.id),
                })

                result.export_file_id = str(export_record.id)
                result.export_filename = export_record.filename
                result.processed_count = export_record.document_count
                result.success_count = export_record.document_count

            await db.commit()

            result.status = MagicButtonStatus.COMPLETED
            result.message = f"Monats-Report erstellt: {result.processed_count} Belege exportiert"

        except Exception as e:
            result.status = MagicButtonStatus.FAILED
            result.message = f"Monats-Report fehlgeschlagen: {str(e)}"
            result.errors.append(str(e))
            logger.exception("monthly_report_failed", company_id=str(company_id))

        result.duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "monthly_report_completed",
            company_id=str(company_id),
            status=result.status.value,
            processed_count=result.processed_count,
            duration_ms=result.duration_ms,
        )

        return result

    # ==========================================================================
    # OFFENE POSTEN BEREINIGEN
    # ==========================================================================

    async def preview_clear_open_items(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> MagicButtonPreview:
        """Vorschau fuer Offene-Posten-Bereinigung.

        Zeigt:
        - Ueberfaellige Rechnungen
        - Unabgeglichene Transaktionen
        - Ausstehende Mahnungen
        """
        preview = MagicButtonPreview(
            button_type=MagicButtonType.CLEAR_OPEN_ITEMS,
            title="Offene Posten bereinigen",
            description="Gleicht Zahlungen ab und erstellt Mahnungen",
        )

        today = date.today()

        # 1. Ueberfaellige Rechnungen
        overdue_query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status.in_(["open", "sent", "overdue"]),
                InvoiceTracking.due_date < today,
            )
        )
        overdue_result = await db.execute(overdue_query)
        overdue_invoices = overdue_result.scalars().all()

        preview.invoice_count = len(overdue_invoices)

        # Betraege summieren
        overdue_total = Decimal("0.00")
        for inv in overdue_invoices:
            if inv.outstanding_amount:
                overdue_total += inv.outstanding_amount
            elif inv.total_amount:
                overdue_total += inv.total_amount

        preview.estimated_amount = overdue_total

        # 2. Unabgeglichene Transaktionen
        # BankTransaction doesn't have company_id - count all unmatched
        trans_query = select(func.count(BankTransaction.id)).where(
            BankTransaction.reconciliation_status.in_(["pending", "unmatched"]),
        )
        trans_result = await db.execute(trans_query)
        preview.transaction_count = trans_result.scalar() or 0

        preview.items = [
            {
                "type": "overdue",
                "count": preview.invoice_count,
                "label": f"{preview.invoice_count} ueberfaellige Rechnungen",
                "amount": float(overdue_total),
            },
            {
                "type": "transactions",
                "count": preview.transaction_count,
                "label": f"{preview.transaction_count} Transaktionen abzugleichen",
            },
        ]

        # Warnungen
        if preview.invoice_count > 10:
            preview.warnings.append(f"Viele ueberfaellige Rechnungen ({preview.invoice_count})")

        preview.estimated_duration_seconds = (
            preview.invoice_count * 2 +
            preview.transaction_count * 1
        )

        preview.can_execute = preview.invoice_count > 0 or preview.transaction_count > 0
        if not preview.can_execute:
            preview.block_reason = "Keine offenen Posten gefunden"

        return preview

    async def execute_clear_open_items(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        auto_reconcile: bool = True,
        send_reminders: bool = False,
        increase_dunning: bool = False,
    ) -> MagicButtonResult:
        """Bereinigt offene Posten.

        1. Transaktionen automatisch abgleichen
        2. Optional: Zahlungserinnerungen senden
        3. Optional: Mahnstufen erhoehen
        """
        import time
        start_time = time.time()

        result = MagicButtonResult(
            button_type=MagicButtonType.CLEAR_OPEN_ITEMS,
            status=MagicButtonStatus.RUNNING,
            title="Offene Posten bereinigen",
            message="Verarbeite offene Posten...",
        )

        try:
            # 1. Auto-Reconcile
            if auto_reconcile:
                from app.services.banking.reconciliation_service import ReconciliationService
                reconciliation_service = ReconciliationService()

                batch_result = await reconciliation_service.batch_reconcile(
                    db=db,
                    user_id=user_id,
                    min_confidence=0.85,
                )

                result.details.append({
                    "step": "auto_reconcile",
                    "processed": batch_result.total_processed,
                    "matched": batch_result.matched_count,
                })
                result.success_count += batch_result.matched_count
                result.processed_count += batch_result.total_processed

            # 2. Mahnstufen erhoehen
            if increase_dunning:
                today = date.today()

                # Rechnungen mit ueberfaelliger Mahnstufe
                overdue_query = select(InvoiceTracking).where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["open", "sent", "overdue", "dunning"]),
                        InvoiceTracking.due_date < today,
                        InvoiceTracking.dunning_level < 4,  # Max 4 Stufen
                    )
                )
                overdue_result = await db.execute(overdue_query)
                overdue_invoices = overdue_result.scalars().all()

                dunning_increased = 0
                for inv in overdue_invoices:
                    # Nur erhoehen wenn letzte Mahnung > 7 Tage her
                    if inv.last_dunning_at:
                        days_since_dunning = (today - inv.last_dunning_at.date()).days
                        if days_since_dunning < 7:
                            continue

                    inv.dunning_level = (inv.dunning_level or 0) + 1
                    inv.last_dunning_at = utc_now()
                    inv.status = "dunning"
                    dunning_increased += 1

                result.details.append({
                    "step": "increase_dunning",
                    "processed": len(overdue_invoices),
                    "increased": dunning_increased,
                })
                result.success_count += dunning_increased

            await db.commit()

            result.status = MagicButtonStatus.COMPLETED
            result.message = f"Offene Posten bereinigt: {result.success_count} verarbeitet"

            if result.errors:
                result.status = MagicButtonStatus.PARTIAL
                result.message += f", {len(result.errors)} Fehler"

        except Exception as e:
            result.status = MagicButtonStatus.FAILED
            result.message = f"Bereinigung fehlgeschlagen: {str(e)}"
            result.errors.append(str(e))
            logger.exception("clear_open_items_failed", company_id=str(company_id))

        result.duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "clear_open_items_completed",
            company_id=str(company_id),
            status=result.status.value,
            success_count=result.success_count,
            duration_ms=result.duration_ms,
        )

        return result

    # ==========================================================================
    # NEUEN KONTAKT ERSTELLEN
    # ==========================================================================

    async def preview_create_contact(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> MagicButtonPreview:
        """Vorschau fuer Kontakt-Erstellung aus Dokument.

        Zeigt:
        - Extrahierte Kontaktdaten
        - Matching zu bestehenden Entities
        - Vorgeschlagene Felder
        """
        preview = MagicButtonPreview(
            button_type=MagicButtonType.CREATE_CONTACT,
            title="Kontakt erstellen",
            description="Erstellt Entity aus Dokumentdaten",
        )

        # Dokument laden
        doc_query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        doc_result = await db.execute(doc_query)
        doc = doc_result.scalar_one_or_none()

        if not doc:
            preview.can_execute = False
            preview.block_reason = "Dokument nicht gefunden"
            return preview

        # Extrahierte Daten pruefen
        extracted = doc.extracted_data or {}

        company_name = (
            extracted.get("sender", {}).get("company") or
            extracted.get("creditor_name") or
            extracted.get("vendor_name")
        )

        preview.items = [
            {"field": "name", "value": company_name, "label": "Firmenname"},
            {"field": "vat_id", "value": extracted.get("sender", {}).get("vat_id"), "label": "USt-IdNr"},
            {"field": "iban", "value": extracted.get("iban"), "label": "IBAN"},
            {"field": "address", "value": extracted.get("sender", {}).get("address"), "label": "Adresse"},
        ]

        # Pruefen ob Entity schon existiert
        if company_name:
            # BusinessEntity hat kein company_id - pruefen ob Name existiert
            existing_query = select(BusinessEntity).where(
                BusinessEntity.name.ilike(f"%{company_name}%"),
            )
            existing_result = await db.execute(existing_query)
            existing = existing_result.scalars().first()

            if existing:
                preview.warnings.append(f"Aehnlicher Kontakt existiert bereits: {existing.name}")

        preview.can_execute = company_name is not None and len(company_name) > 2
        if not preview.can_execute:
            preview.block_reason = "Kein Firmenname im Dokument gefunden"

        return preview

    async def execute_create_contact(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        document_id: UUID,
        entity_type: str = "supplier",
        override_name: Optional[str] = None,
    ) -> MagicButtonResult:
        """Erstellt Entity aus Dokument.

        1. Daten aus Dokument extrahieren
        2. BusinessEntity erstellen
        3. Dokument mit Entity verknuepfen
        """
        import time
        start_time = time.time()

        result = MagicButtonResult(
            button_type=MagicButtonType.CREATE_CONTACT,
            status=MagicButtonStatus.RUNNING,
            title="Kontakt erstellen",
            message="Erstelle Kontakt aus Dokument...",
        )

        try:
            # Dokument laden
            doc_query = select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            doc_result = await db.execute(doc_query)
            doc = doc_result.scalar_one_or_none()

            if not doc:
                raise ValueError("Dokument nicht gefunden")

            extracted = doc.extracted_data or {}

            # Name bestimmen
            name = override_name or (
                extracted.get("sender", {}).get("company") or
                extracted.get("creditor_name") or
                extracted.get("vendor_name")
            )

            if not name:
                raise ValueError("Kein Firmenname gefunden")

            # Entity erstellen
            import uuid as uuid_module

            entity = BusinessEntity(
                id=uuid_module.uuid4(),
                name=name,
                entity_type=entity_type,
                vat_id=extracted.get("sender", {}).get("vat_id"),
                iban=extracted.get("iban"),
                created_by_id=user_id,
                auto_detected=True,  # Automatisch aus Dokument erstellt
            )

            # Adresse falls vorhanden
            address = extracted.get("sender", {}).get("address")
            if address and isinstance(address, dict):
                entity.street = address.get("street")
                entity.city = address.get("city")
                entity.postal_code = address.get("postal_code")
                entity.country = address.get("country", "DE")

            db.add(entity)

            # Dokument verknuepfen
            doc.business_entity_id = entity.id

            await db.commit()

            result.status = MagicButtonStatus.COMPLETED
            result.message = f"Kontakt '{name}' erstellt und mit Dokument verknuepft"
            result.success_count = 1
            result.processed_count = 1

            result.details.append({
                "entity_id": str(entity.id),
                "entity_name": name,
                "entity_type": entity_type,
                "document_linked": True,
            })

        except Exception as e:
            result.status = MagicButtonStatus.FAILED
            result.message = f"Kontakt-Erstellung fehlgeschlagen: {str(e)}"
            result.errors.append(str(e))
            logger.exception("create_contact_failed", document_id=str(document_id))

        result.duration_ms = int((time.time() - start_time) * 1000)

        return result


# Singleton
_magic_buttons_service: Optional[MagicButtonsService] = None


def get_magic_buttons_service() -> MagicButtonsService:
    """Gibt Magic-Buttons-Service-Instanz zurueck."""
    global _magic_buttons_service
    if _magic_buttons_service is None:
        _magic_buttons_service = MagicButtonsService()
    return _magic_buttons_service
