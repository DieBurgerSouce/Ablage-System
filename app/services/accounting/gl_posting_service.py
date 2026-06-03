# -*- coding: utf-8 -*-
"""
GL-Posting Service (General Ledger).

Core service for journal entry management:
- Create balanced journal entries (debit = credit)
- Post entries (draft -> posted)
- Reverse entries (GoBD-konform, keine Löschung)
- Auto-post from OCR documents
- Trial balance and account ledger reports

GoBD-konform: Keine Löschungen, nur Stornierungen.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Union
from uuid import UUID
import uuid

import structlog
from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.db.models import Document, User, Company, DATEVConfiguration, DATEVVendorMapping
from app.db.models_gl_posting import (
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
    JournalEntrySource,
    GLAccount,
)
from app.services.datev.mapping.invoice_mapper import DATEVInvoiceMapper, MappingResult, DATEVBuchung
from app.api.schemas.extracted_data import ExtractedInvoiceData
from app.services.datev.kontenrahmen.skr03 import SKR03
from app.services.datev.kontenrahmen.skr04 import SKR04

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes (Input/Output)
# =============================================================================

@dataclass
class JournalEntryLineCreate:
    """Input für eine Buchungszeile."""
    account_number: str
    account_name: str
    debit_amount: Decimal
    credit_amount: Decimal
    tax_code: Optional[str] = None
    tax_rate: Optional[Decimal] = None
    cost_center: Optional[str] = None
    text: str = ""


@dataclass
class TrialBalanceRow:
    """Eine Zeile in der Summen-Saldenliste."""
    account_number: str
    account_name: str
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal


@dataclass
class LedgerEntry:
    """Eine Zeile im Kontoblatt."""
    entry_id: UUID
    posting_date: date
    entry_number: str
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    running_balance: Decimal


# =============================================================================
# GL Posting Service
# =============================================================================

class GLPostingService:
    """
    Service für General Ledger Buchungen.

    Alle Methoden sind async und nutzen SQLAlchemy AsyncSession.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_journal_entry(
        self,
        company_id: UUID,
        lines: List[JournalEntryLineCreate],
        posting_date: date,
        description: Optional[str] = None,
        document_id: Optional[UUID] = None,
        source: str = "manual",
        confidence: Optional[float] = None,
        created_by: Optional[UUID] = None,
    ) -> JournalEntry:
        """
        Erstellt einen Buchungssatz.

        Validiert:
        - Mindestens 2 Zeilen
        - Summe Soll = Summe Haben

        Args:
            company_id: Firmen-ID
            lines: Liste der Buchungszeilen
            posting_date: Buchungsdatum
            description: Beschreibung (max 60 Zeichen)
            document_id: Verknüpftes Dokument (optional)
            source: Quelle (manual, auto_booking, import, pipeline)
            confidence: Confidence für Auto-Bookings (0.0-1.0)
            created_by: User-ID des Erstellers

        Returns:
            Erstellter JournalEntry (status=draft)

        Raises:
            ValueError: Bei unbalancierten Buchungen
        """
        # Validierung
        if len(lines) < 2:
            raise ValueError("Mindestens 2 Buchungszeilen erforderlich")

        total_debit = sum(line.debit_amount for line in lines)
        total_credit = sum(line.credit_amount for line in lines)

        # Runden auf 2 Nachkommastellen für Vergleich
        total_debit = total_debit.quantize(Decimal('0.01'))
        total_credit = total_credit.quantize(Decimal('0.01'))

        if total_debit != total_credit:
            raise ValueError(
                f"Unbalancierte Buchung: Soll={total_debit} != Haben={total_credit}"
            )

        # Fiscal year und period aus posting_date ableiten
        fiscal_year = posting_date.year
        fiscal_period = posting_date.month

        # Entry-Nummer generieren: JE-{year}-{sequence:05d}
        entry_number = await self._generate_entry_number(company_id, fiscal_year)

        # JournalEntry erstellen
        entry = JournalEntry(
            id=uuid.uuid4(),
            company_id=company_id,
            document_id=document_id,
            posting_date=posting_date,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            entry_number=entry_number,
            description=description[:60] if description else None,
            total_amount=total_debit,  # = total_credit
            currency="EUR",
            status=JournalEntryStatus.DRAFT.value,
            source=source,
            confidence=Decimal(str(confidence)) if confidence else None,
            created_by_id=created_by,
        )

        # Lines erstellen
        for idx, line_data in enumerate(lines, start=1):
            line = JournalEntryLine(
                id=uuid.uuid4(),
                entry_id=entry.id,
                line_number=idx,
                account_number=line_data.account_number,
                account_name=line_data.account_name,
                debit_amount=line_data.debit_amount,
                credit_amount=line_data.credit_amount,
                tax_code=line_data.tax_code,
                tax_rate=line_data.tax_rate,
                cost_center=line_data.cost_center,
                text=line_data.text[:60] if line_data.text else None,
            )
            entry.lines.append(line)

        self.db.add(entry)
        await self.db.flush()

        logger.info(
            "journal_entry_created",
            entry_id=str(entry.id),
            entry_number=entry_number,
            company_id=str(company_id),
            total_amount=str(total_debit),
            line_count=len(lines),
        )

        return entry

    async def _generate_entry_number(self, company_id: UUID, fiscal_year: int) -> str:
        """
        Generiert eine eindeutige Entry-Nummer.

        Format: JE-{year}-{sequence:05d}
        """
        # Höchste Nummer für dieses Jahr finden
        stmt = select(func.max(JournalEntry.entry_number)).where(
            and_(
                JournalEntry.company_id == company_id,
                JournalEntry.fiscal_year == fiscal_year
            )
        )
        result = await self.db.execute(stmt)
        max_number = result.scalar_one_or_none()

        if max_number:
            # Extrahiere Sequenz aus "JE-2024-00042"
            try:
                seq = int(max_number.split('-')[-1])
                next_seq = seq + 1
            except (ValueError, IndexError):
                next_seq = 1
        else:
            next_seq = 1

        return f"JE-{fiscal_year}-{next_seq:05d}"

    async def post_journal_entry(
        self,
        entry_id: UUID,
        posted_by: UUID,
    ) -> JournalEntry:
        """
        Bucht einen Entwurf.

        Ändert Status: draft -> posted
        Setzt posted_at und posted_by.

        Args:
            entry_id: Journal Entry ID
            posted_by: User-ID

        Returns:
            Geposteter JournalEntry

        Raises:
            ValueError: Wenn Entry nicht im Status draft
        """
        stmt = select(JournalEntry).where(JournalEntry.id == entry_id)
        result = await self.db.execute(stmt)
        entry = result.scalar_one_or_none()

        if not entry:
            raise ValueError(f"Journal Entry {entry_id} nicht gefunden")

        if entry.status != JournalEntryStatus.DRAFT.value:
            raise ValueError(
                f"Nur Entwürfe können gebucht werden (Status: {entry.status})"
            )

        entry.status = JournalEntryStatus.POSTED.value
        entry.posted_at = utc_now()
        entry.posted_by_id = posted_by

        await self.db.flush()

        logger.info(
            "journal_entry_posted",
            entry_id=str(entry.id),
            entry_number=entry.entry_number,
            posted_by=str(posted_by),
        )

        return entry

    async def reverse_journal_entry(
        self,
        entry_id: UUID,
        reversed_by: UUID,
        reason: str,
    ) -> JournalEntry:
        """
        Storniert einen Buchungssatz (GoBD-konform).

        Erstellt einen neuen Entry mit vertauschten Soll/Haben-Beträgen.
        Markiert Original als "reversed".

        Args:
            entry_id: Original Entry ID
            reversed_by: User-ID
            reason: Stornierungsgrund

        Returns:
            Neuer Storno-Entry

        Raises:
            ValueError: Wenn Entry nicht gebucht
        """
        stmt = select(JournalEntry).where(JournalEntry.id == entry_id)
        result = await self.db.execute(stmt)
        original = result.scalar_one_or_none()

        if not original:
            raise ValueError(f"Journal Entry {entry_id} nicht gefunden")

        if original.status != JournalEntryStatus.POSTED.value:
            raise ValueError("Nur gebuchte Einträge können storniert werden")

        # Storno-Entry erstellen (mit vertauschten Beträgen)
        lines_reversed: List[JournalEntryLineCreate] = []
        for line in original.lines:
            lines_reversed.append(
                JournalEntryLineCreate(
                    account_number=line.account_number,
                    account_name=line.account_name,
                    debit_amount=line.credit_amount,  # Vertauscht!
                    credit_amount=line.debit_amount,  # Vertauscht!
                    tax_code=line.tax_code,
                    tax_rate=line.tax_rate,
                    cost_center=line.cost_center,
                    text=f"STORNO: {line.text}" if line.text else "STORNO",
                )
            )

        reversal = await self.create_journal_entry(
            company_id=original.company_id,
            lines=lines_reversed,
            posting_date=date.today(),
            description=f"STORNO {original.entry_number}: {reason}"[:60],
            document_id=original.document_id,
            source=original.source,
            created_by=reversed_by,
        )

        # Direkt posten
        await self.post_journal_entry(reversal.id, reversed_by)

        # Original als reversed markieren
        original.status = JournalEntryStatus.REVERSED.value
        original.reversed_by_entry_id = reversal.id

        await self.db.flush()

        logger.info(
            "journal_entry_reversed",
            original_id=str(entry_id),
            reversal_id=str(reversal.id),
            reason=reason,
        )

        return reversal

    async def post_from_invoice(
        self,
        company_id: UUID,
        document_id: UUID,
        posted_by: UUID,
    ) -> JournalEntry:
        """
        Erstellt und bucht einen Journal Entry aus einem OCR-Dokument.

        Nutzt DATEVInvoiceMapper-Logik für Account-Mapping.

        Args:
            company_id: Firmen-ID
            document_id: Dokument-ID
            posted_by: User-ID

        Returns:
            Gebuchter JournalEntry

        Raises:
            ValueError: Wenn Dokument nicht gefunden oder unvollständig
        """
        # Dokument laden
        stmt = select(Document).where(Document.id == document_id)
        result = await self.db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        # Extracted data holen
        extracted = doc.extracted_entities or {}
        invoice_total = extracted.get("total_amount")
        tax_amount = extracted.get("tax_amount")
        net_amount = extracted.get("net_amount")

        if not invoice_total:
            raise ValueError("Dokument hat keine extrahierte Rechnungssumme")

        # Account-Mapping: DATEV-Mapper nutzen wenn konfiguriert, sonst Fallback
        datev_config = await self._get_datev_config(company_id)

        if datev_config:
            lines = await self._map_via_datev(
                datev_config, extracted, invoice_total, tax_amount, net_amount
            )
        else:
            lines = self._simple_expense_lines(
                extracted, invoice_total, tax_amount, net_amount
            )

        # M11: Echten Extraktions-Confidence verwenden statt fixem Platzhalter.
        # Ein fixer Wert von 0.85 entspraeche exakt der Auto-Post-Schwelle und
        # wuerde diese faelschlich IMMER erreichen.
        booking_confidence = self._resolve_extraction_confidence(extracted, doc)

        entry = await self.create_journal_entry(
            company_id=company_id,
            lines=lines,
            posting_date=date.today(),
            description=f"Auto: {extracted.get('invoice_number', 'N/A')}",
            document_id=document_id,
            source=JournalEntrySource.AUTO_BOOKING.value,
            confidence=booking_confidence,
            created_by=posted_by,
        )

        # Direkt posten
        await self.post_journal_entry(entry.id, posted_by)

        return entry

    def _resolve_extraction_confidence(
        self,
        extracted: Dict[str, Union[str, int, float, Decimal, None]],
        doc: Document,
    ) -> float:
        """Ermittelt den echten Extraktions-Confidence (0.0-1.0).

        Reihenfolge: explizit extrahierter Confidence-Wert > OCR-Confidence des
        Dokuments > konservativer Default mit ehrlichem Warn-Log. So wird kein
        fixer Wert verwendet, der die Auto-Post-Schwelle kuenstlich erreicht.
        """
        conservative_default = 0.5

        raw: Optional[float] = None
        for key in ("extraction_confidence", "confidence", "ocr_confidence"):
            value = extracted.get(key)
            if value is not None:
                try:
                    raw = float(value)  # type: ignore[arg-type]
                    break
                except (TypeError, ValueError):
                    raw = None

        if raw is None and doc.ocr_confidence is not None:
            try:
                raw = float(doc.ocr_confidence)
            except (TypeError, ValueError):
                raw = None

        if raw is None:
            logger.warning(
                "gl_auto_booking_confidence_fallback",
                document_id=str(doc.id),
                fallback=conservative_default,
            )
            return conservative_default

        # Normalisieren: Werte > 1.0 werden als Prozent (0-100) interpretiert
        if raw > 1.0:
            raw = raw / 100.0

        return max(0.0, min(1.0, raw))

    def _simple_expense_lines(
        self,
        extracted: Dict[str, Union[str, int, float, Decimal, None]],
        invoice_total: Union[str, int, float, Decimal],
        tax_amount: Union[str, int, float, Decimal, None],
        net_amount: Union[str, int, float, Decimal, None],
    ) -> List[JournalEntryLineCreate]:
        """Einfache Expense-Buchung (Fallback ohne DATEV-Config)."""
        return [
            JournalEntryLineCreate(
                account_number="4400",
                account_name="Wareneingang",
                debit_amount=Decimal(str(net_amount or invoice_total)),
                credit_amount=Decimal("0"),
                text=f"RE: {extracted.get('invoice_number', 'N/A')}",
            ),
            JournalEntryLineCreate(
                account_number="1576",
                account_name="Vorsteuer 19%",
                debit_amount=Decimal(str(tax_amount or 0)),
                credit_amount=Decimal("0"),
                tax_code="40",
                tax_rate=Decimal("19.00"),
                text="Vorsteuer",
            ),
            JournalEntryLineCreate(
                account_number="1600",
                account_name="Verbindlichkeiten",
                debit_amount=Decimal("0"),
                credit_amount=Decimal(str(invoice_total)),
                text=extracted.get("supplier_name", "Kreditor")[:60],
            ),
        ]

    async def _get_datev_config(
        self, company_id: UUID
    ) -> Optional[DATEVConfiguration]:
        """Lade aktive DATEV-Konfiguration für die Firma (via User)."""
        from app.db.models import User as UserModel

        stmt = (
            select(DATEVConfiguration)
            .join(UserModel, DATEVConfiguration.user_id == UserModel.id)
            .where(
                and_(
                    UserModel.company_id == company_id,
                    DATEVConfiguration.is_active == True,
                    DATEVConfiguration.is_default == True,
                )
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_vendor_mapping(
        self,
        config_id: UUID,
        extracted: Dict[str, Union[str, int, float, Decimal, None]],
    ) -> Optional[DATEVVendorMapping]:
        """Lade optionales Vendor-Mapping anhand Lieferantenname oder USt-IdNr."""
        supplier_name = extracted.get("supplier_name")
        vat_id = extracted.get("vat_id")

        if not supplier_name and not vat_id:
            return None

        conditions = [DATEVVendorMapping.config_id == config_id]
        match_conditions = []
        if supplier_name:
            match_conditions.append(
                DATEVVendorMapping.vendor_name == supplier_name
            )
        if vat_id:
            match_conditions.append(
                DATEVVendorMapping.vendor_vat_id == vat_id
            )

        if match_conditions:
            conditions.append(or_(*match_conditions))

        stmt = (
            select(DATEVVendorMapping)
            .where(and_(*conditions))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _buchung_to_journal_lines(
        self,
        buchung: DATEVBuchung,
        extracted: Dict[str, Union[str, int, float, Decimal, None]],
    ) -> List[JournalEntryLineCreate]:
        """Konvertiert DATEVBuchung -> JournalEntryLineCreate-Liste."""
        lines: List[JournalEntryLineCreate] = []

        if buchung.soll_haben == "S":
            # Soll-Buchung: Sachkonto im Soll, Gegenkonto im Haben
            lines.append(JournalEntryLineCreate(
                account_number=buchung.konto,
                account_name=buchung.buchungstext or f"Konto {buchung.konto}",
                debit_amount=buchung.umsatz,
                credit_amount=Decimal("0"),
                tax_code=buchung.bu_schluessel,
                cost_center=buchung.kostenstelle_1,
                text=buchung.buchungstext[:60] if buchung.buchungstext else "",
            ))
            lines.append(JournalEntryLineCreate(
                account_number=buchung.gegenkonto,
                account_name=extracted.get("supplier_name", f"Konto {buchung.gegenkonto}")[:60],
                debit_amount=Decimal("0"),
                credit_amount=buchung.umsatz,
                text=buchung.belegfeld_1[:60] if buchung.belegfeld_1 else "",
            ))
        else:
            # Haben-Buchung: Sachkonto im Haben, Gegenkonto im Soll
            lines.append(JournalEntryLineCreate(
                account_number=buchung.gegenkonto,
                account_name=extracted.get("customer_name", f"Konto {buchung.gegenkonto}")[:60],
                debit_amount=buchung.umsatz,
                credit_amount=Decimal("0"),
                text=buchung.belegfeld_1[:60] if buchung.belegfeld_1 else "",
            ))
            lines.append(JournalEntryLineCreate(
                account_number=buchung.konto,
                account_name=buchung.buchungstext or f"Konto {buchung.konto}",
                debit_amount=Decimal("0"),
                credit_amount=buchung.umsatz,
                tax_code=buchung.bu_schluessel,
                cost_center=buchung.kostenstelle_1,
                text=buchung.buchungstext[:60] if buchung.buchungstext else "",
            ))

        return lines

    async def _map_via_datev(
        self,
        datev_config: DATEVConfiguration,
        extracted: Dict[str, Union[str, int, float, Decimal, None]],
        invoice_total: Union[str, int, float, Decimal],
        tax_amount: Union[str, int, float, Decimal, None],
        net_amount: Union[str, int, float, Decimal, None],
    ) -> List[JournalEntryLineCreate]:
        """Mappe Rechnung via DATEVInvoiceMapper, mit Fallback."""
        try:
            mapper = DATEVInvoiceMapper()
            invoice_data = ExtractedInvoiceData(**extracted)

            # Kontenrahmen dynamisch wählen
            kr_name = getattr(datev_config, "kontenrahmen", "SKR03")
            kontenrahmen = SKR04() if kr_name == "SKR04" else SKR03()

            vendor_mapping = await self._get_vendor_mapping(
                datev_config.id, extracted
            )

            mapping_result = mapper.map_invoice(
                invoice=invoice_data,
                kontenrahmen=kontenrahmen,
                config=datev_config,
                vendor_mapping=vendor_mapping,
            )

            if mapping_result.success and mapping_result.buchung:
                for w in mapping_result.warnings:
                    logger.warning("datev_mapping_warning", warning=w)
                return self._buchung_to_journal_lines(
                    mapping_result.buchung, extracted
                )
            else:
                logger.warning(
                    "datev_mapping_fallback",
                    error=mapping_result.error,
                )
                return self._simple_expense_lines(
                    extracted, invoice_total, tax_amount, net_amount
                )
        except Exception as e:
            logger.warning(
                "datev_mapping_exception_fallback",
                error=str(e),
            )
            return self._simple_expense_lines(
                extracted, invoice_total, tax_amount, net_amount
            )

    async def auto_post_from_pipeline(
        self,
        company_id: UUID,
        document_id: UUID,
        confidence: float,
    ) -> Optional[JournalEntry]:
        """
        Automatisches Posting aus der Pipeline.

        Nur wenn confidence >= 0.85.

        Args:
            company_id: Firmen-ID
            document_id: Dokument-ID
            confidence: Confidence-Score (0.0-1.0)

        Returns:
            JournalEntry wenn gepostet, sonst None
        """
        if confidence < 0.85:
            logger.info(
                "auto_post_skipped_low_confidence",
                document_id=str(document_id),
                confidence=confidence,
            )
            return None

        # Nutze post_from_invoice (mit system user)
        system_user_id = uuid.UUID(settings.SYSTEM_USER_ID)

        try:
            entry = await self.post_from_invoice(
                company_id=company_id,
                document_id=document_id,
                posted_by=system_user_id,
            )
            return entry
        except Exception as e:
            logger.error(
                "auto_post_failed",
                document_id=str(document_id),
                error=str(e),
            )
            return None

    async def get_trial_balance(
        self,
        company_id: UUID,
        fiscal_year: int,
        period: Optional[int] = None,
    ) -> List[TrialBalanceRow]:
        """
        Erstellt Summen-Saldenliste.

        Args:
            company_id: Firmen-ID
            fiscal_year: Geschäftsjahr
            period: Periode (1-12), None = ganzes Jahr

        Returns:
            Liste von TrialBalanceRow (sortiert nach Kontonummer)
        """
        # Query: Aggregiere Soll/Haben pro Konto
        stmt = (
            select(
                JournalEntryLine.account_number,
                JournalEntryLine.account_name,
                func.sum(JournalEntryLine.debit_amount).label("total_debit"),
                func.sum(JournalEntryLine.credit_amount).label("total_credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                and_(
                    JournalEntry.company_id == company_id,
                    JournalEntry.fiscal_year == fiscal_year,
                    JournalEntry.status == JournalEntryStatus.POSTED.value,
                )
            )
            .group_by(JournalEntryLine.account_number, JournalEntryLine.account_name)
            .order_by(JournalEntryLine.account_number)
        )

        if period:
            stmt = stmt.where(JournalEntry.fiscal_period == period)

        result = await self.db.execute(stmt)
        rows = result.all()

        trial_balance: List[TrialBalanceRow] = []
        for row in rows:
            account_number = row.account_number
            account_name = row.account_name or f"Konto {account_number}"
            total_debit = row.total_debit or Decimal("0")
            total_credit = row.total_credit or Decimal("0")
            balance = total_debit - total_credit

            trial_balance.append(
                TrialBalanceRow(
                    account_number=account_number,
                    account_name=account_name,
                    total_debit=total_debit,
                    total_credit=total_credit,
                    balance=balance,
                )
            )

        return trial_balance

    async def get_account_ledger(
        self,
        company_id: UUID,
        account_number: str,
        fiscal_year: int,
    ) -> List[LedgerEntry]:
        """
        Erstellt Kontoblatt für ein Konto.

        Args:
            company_id: Firmen-ID
            account_number: Kontonummer
            fiscal_year: Geschäftsjahr

        Returns:
            Liste von LedgerEntry (chronologisch)
        """
        stmt = (
            select(
                JournalEntry.id,
                JournalEntry.posting_date,
                JournalEntry.entry_number,
                JournalEntry.description,
                JournalEntryLine.debit_amount,
                JournalEntryLine.credit_amount,
            )
            .join(JournalEntryLine, JournalEntry.id == JournalEntryLine.entry_id)
            .where(
                and_(
                    JournalEntry.company_id == company_id,
                    JournalEntry.fiscal_year == fiscal_year,
                    JournalEntry.status == JournalEntryStatus.POSTED.value,
                    JournalEntryLine.account_number == account_number,
                )
            )
            .order_by(JournalEntry.posting_date, JournalEntry.entry_number)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        ledger: List[LedgerEntry] = []
        running_balance = Decimal("0")

        for row in rows:
            debit = row.debit_amount or Decimal("0")
            credit = row.credit_amount or Decimal("0")
            running_balance += debit - credit

            ledger.append(
                LedgerEntry(
                    entry_id=row.id,
                    posting_date=row.posting_date,
                    entry_number=row.entry_number,
                    description=row.description or "",
                    debit_amount=debit,
                    credit_amount=credit,
                    running_balance=running_balance,
                )
            )

        return ledger


# =============================================================================
# Dependency Injection
# =============================================================================

def get_gl_posting_service(db: AsyncSession) -> GLPostingService:
    """FastAPI Dependency für GLPostingService."""
    return GLPostingService(db)
