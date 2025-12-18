"""Bank Statement Import Service.

Orchestriert den Import von Kontoauszuegen:
- Format-Erkennung
- Parsing mit passendem Parser
- Duplikat-Erkennung
- Speicherung in Datenbank
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Tuple, BinaryIO, Union
from uuid import UUID, uuid4
import hashlib
import structlog

from sqlalchemy import select, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .parsers import (
    detect_format,
    ParseResult,
    ParsedTransaction,
    MT940Parser,
    CAMT053Parser,
    GenericCSVParser,
)
from .parsers.bank_csv import (
    SparkasseCSVParser,
    VolksbankCSVParser,
    DeutscheBankCSVParser,
    CommerzbankCSVParser,
    INGCSVParser,
    N26CSVParser,
    DKBCSVParser,
)
from .models import (
    ImportFormat,
    BankImportCreate,
    BankImportPreview,
    BankImportResponse,
    SupportedFormatsResponse,
    ReconciliationStatus,
)

logger = structlog.get_logger(__name__)


class ImportService:
    """Service fuer Bank Statement Import."""

    # Alle verfuegbaren Parser
    PARSERS = [
        MT940Parser,
        CAMT053Parser,
        SparkasseCSVParser,
        VolksbankCSVParser,
        DeutscheBankCSVParser,
        CommerzbankCSVParser,
        INGCSVParser,
        N26CSVParser,
        DKBCSVParser,
        GenericCSVParser,  # Fallback
    ]

    async def get_supported_formats(self) -> SupportedFormatsResponse:
        """Hole Liste unterstuetzter Formate."""
        formats = []

        for parser_cls in self.PARSERS:
            format_info = {
                "format": parser_cls.FORMAT.value if parser_cls.FORMAT else "unknown",
                "variant": parser_cls.FORMAT_VARIANT,
                "name": self._get_format_display_name(parser_cls.FORMAT, parser_cls.FORMAT_VARIANT),
                "extensions": parser_cls.SUPPORTED_EXTENSIONS,
                "description": self._get_format_description(parser_cls.FORMAT, parser_cls.FORMAT_VARIANT),
            }
            formats.append(format_info)

        return SupportedFormatsResponse(formats=formats)

    def _get_format_display_name(self, format: ImportFormat, variant: Optional[str]) -> str:
        """Hole Anzeigename fuer Format."""
        names = {
            ImportFormat.MT940: "MT940 (SWIFT)",
            ImportFormat.CAMT053: "CAMT.053 (ISO 20022)",
            ImportFormat.CSV_SPARKASSE: "Sparkasse CSV",
            ImportFormat.CSV_VOLKSBANK: "Volksbank/Raiffeisenbank CSV",
            ImportFormat.CSV_DEUTSCHE_BANK: "Deutsche Bank CSV",
            ImportFormat.CSV_COMMERZBANK: "Commerzbank CSV",
            ImportFormat.CSV_ING: "ING CSV",
            ImportFormat.CSV_N26: "N26 CSV",
            ImportFormat.CSV_DKB: "DKB CSV",
            ImportFormat.CSV_GENERIC: "Generisches CSV",
        }
        return names.get(format, format.value if format else "Unbekannt")

    def _get_format_description(self, format: ImportFormat, variant: Optional[str]) -> str:
        """Hole Beschreibung fuer Format."""
        descriptions = {
            ImportFormat.MT940: "Universelles Bankformat (SWIFT), unterstuetzt von fast allen Banken",
            ImportFormat.CAMT053: "Modernes XML-Format nach ISO 20022 Standard",
            ImportFormat.CSV_SPARKASSE: "CSV-Export aus Sparkassen-Online-Banking",
            ImportFormat.CSV_VOLKSBANK: "CSV-Export aus VR-Banken Online-Banking",
            ImportFormat.CSV_DEUTSCHE_BANK: "CSV-Export aus Deutsche Bank Online-Banking",
            ImportFormat.CSV_COMMERZBANK: "CSV-Export aus Commerzbank Online-Banking",
            ImportFormat.CSV_ING: "CSV-Export aus ING Online-Banking",
            ImportFormat.CSV_N26: "CSV-Export aus N26 App",
            ImportFormat.CSV_DKB: "CSV-Export aus DKB Online-Banking",
            ImportFormat.CSV_GENERIC: "Automatische Erkennung von generischen CSV-Formaten",
        }
        return descriptions.get(format, "")

    async def preview_import(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        format_hint: Optional[ImportFormat] = None,
    ) -> BankImportPreview:
        """Erstelle Vorschau vor dem eigentlichen Import.

        Args:
            content: Dateiinhalt
            filename: Dateiname (fuer Format-Erkennung)
            format_hint: Optional vorgegebenes Format

        Returns:
            Vorschau mit erkanntem Format und Transaktions-Uebersicht
        """
        # Format erkennen
        detected_format, confidence, parser_cls = self._detect_format(
            content, filename, format_hint
        )

        # Parse
        parser = parser_cls()
        result = parser.parse(content)

        # Vorschau erstellen
        sample_transactions = []
        for tx in result.transactions[:5]:  # Erste 5 als Sample
            sample_transactions.append({
                "booking_date": tx.booking_date.isoformat() if tx.booking_date else None,
                "amount": str(tx.amount),
                "counterparty_name": tx.counterparty_name,
                "reference_text": tx.reference_text[:100] if tx.reference_text else None,
            })

        warnings = result.warnings.copy()

        # Warnungen hinzufuegen
        if confidence < 0.7:
            warnings.append(
                f"Format-Erkennung unsicher (Konfidenz: {confidence:.0%}). "
                "Bitte Daten nach Import pruefen."
            )

        if result.error_count > 0:
            warnings.append(f"{result.error_count} Zeilen konnten nicht geparst werden.")

        return BankImportPreview(
            format_detected=detected_format,
            format_confidence=confidence,
            transaction_count=result.transaction_count,
            date_from=result.date_from,
            date_to=result.date_to,
            total_credits=result.total_credits,
            total_debits=result.total_debits,
            sample_transactions=sample_transactions,
            warnings=warnings,
        )

    async def import_file(
        self,
        db: AsyncSession,
        user_id: UUID,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        bank_account_id: Optional[UUID] = None,
        format_hint: Optional[ImportFormat] = None,
    ) -> Tuple[BankImportResponse, List[UUID]]:
        """Importiere Kontoauszug in Datenbank.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            content: Dateiinhalt
            filename: Dateiname
            bank_account_id: Ziel-Bankkonto (optional)
            format_hint: Vorgegebenes Format (optional)

        Returns:
            (Import-Response, Liste der erstellten Transaction-IDs)
        """
        from app.db.models import BankImport, BankTransaction, BankAccount

        start_time = datetime.utcnow()

        # File-Hash fuer Duplikat-Erkennung
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content
        file_hash = hashlib.sha256(content_bytes).hexdigest()

        # Pruefe auf Duplikat-Import (nicht-atomare Vorpruefung fuer Early-Return)
        # HINWEIS: Die eigentliche Race-Condition wird durch Try/Except bei db.flush() behandelt
        existing_import = await db.execute(
            select(BankImport).where(
                and_(
                    BankImport.file_hash == file_hash,
                    BankImport.user_id == user_id,
                )
            )
        )
        if existing_import.scalar_one_or_none():
            raise ValueError("Diese Datei wurde bereits importiert")

        # Format erkennen und parsen
        detected_format, confidence, parser_cls = self._detect_format(
            content, filename, format_hint
        )

        parser = parser_cls()
        result = parser.parse(content)

        if not result.success:
            raise ValueError(
                f"Parsing fehlgeschlagen: {result.errors[0]['message'] if result.errors else 'Unbekannter Fehler'}"
            )

        # Bank Account ermitteln/validieren
        if bank_account_id:
            account = await db.get(BankAccount, bank_account_id)
            if not account or account.user_id != user_id:
                raise ValueError("Bankkonto nicht gefunden")
        elif result.account_iban:
            # Versuche Konto anhand IBAN zu finden
            account_result = await db.execute(
                select(BankAccount).where(
                    and_(
                        BankAccount.user_id == user_id,
                        BankAccount.iban == result.account_iban,
                        BankAccount.is_active == True,
                    )
                )
            )
            account = account_result.scalar_one_or_none()
            if account:
                bank_account_id = account.id

        # Import-Record erstellen
        import_record = BankImport(
            id=uuid4(),
            user_id=user_id,
            bank_account_id=bank_account_id,
            filename=filename,
            file_hash=file_hash,
            file_size=len(content_bytes),
            format=detected_format.value,
            format_variant=parser_cls.FORMAT_VARIANT,
            status="processing",
            date_from=result.date_from,
            date_to=result.date_to,
            errors=[],
        )
        db.add(import_record)

        # SECURITY: Atomarer Duplikat-Check via DB Constraint
        # Dies verhindert Race Conditions bei parallelen Imports derselben Datei
        try:
            await db.flush()  # Force INSERT um IntegrityError bei Duplikat zu triggern
        except IntegrityError:
            await db.rollback()
            raise ValueError("Diese Datei wurde bereits importiert")

        # Transaktionen importieren
        created_ids = []
        duplicate_count = 0
        error_count = 0
        errors = []

        for tx in result.transactions:
            try:
                # Duplikat-Check
                is_duplicate = await self._check_duplicate(
                    db, bank_account_id, tx
                )

                if is_duplicate:
                    duplicate_count += 1
                    continue

                # Transaction erstellen
                transaction = BankTransaction(
                    id=uuid4(),
                    bank_account_id=bank_account_id,
                    import_id=import_record.id,
                    transaction_id=tx.transaction_id,
                    booking_date=tx.booking_date,
                    value_date=tx.value_date,
                    amount=tx.amount,
                    currency=tx.currency,
                    counterparty_name=tx.counterparty_name,
                    counterparty_iban=tx.counterparty_iban,
                    counterparty_bic=tx.counterparty_bic,
                    reference_text=tx.reference_text,
                    end_to_end_id=tx.end_to_end_id,
                    mandate_id=tx.mandate_id,
                    creditor_id=tx.creditor_id,
                    transaction_type=tx.transaction_type.value if tx.transaction_type else None,
                    booking_text=tx.booking_text,
                    prima_nota=tx.prima_nota,
                    parsed_invoice_numbers=tx.parsed_invoice_numbers,
                    parsed_customer_numbers=tx.parsed_customer_numbers,
                    parsed_references=tx.parsed_references,
                    reconciliation_status=ReconciliationStatus.UNMATCHED.value,
                    raw_data=tx.raw_data,
                )
                db.add(transaction)
                created_ids.append(transaction.id)

            except Exception as e:
                error_count += 1
                errors.append({
                    "transaction_id": tx.transaction_id,
                    "error": str(e),
                })
                logger.warning(f"Fehler beim Import der Transaktion: {e}")

        # Import-Record aktualisieren
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        import_record.status = "completed"
        import_record.transaction_count = len(created_ids)
        import_record.duplicate_count = duplicate_count
        import_record.error_count = error_count
        import_record.errors = errors
        import_record.processing_duration_ms = int(processing_time)

        await db.commit()

        # Response erstellen
        response = BankImportResponse(
            id=import_record.id,
            filename=filename,
            format=detected_format,
            format_variant=parser_cls.FORMAT_VARIANT,
            status="completed",
            transaction_count=len(created_ids),
            duplicate_count=duplicate_count,
            error_count=error_count,
            date_from=result.date_from,
            date_to=result.date_to,
            imported_at=import_record.imported_at,
            processing_duration_ms=int(processing_time),
            errors=errors,
        )

        return response, created_ids

    def _detect_format(
        self,
        content: Union[str, bytes],
        filename: Optional[str],
        format_hint: Optional[ImportFormat],
    ) -> Tuple[ImportFormat, float, type]:
        """Erkenne Format und waehle Parser.

        Returns:
            (Format, Konfidenz, Parser-Klasse)
        """
        # Wenn Format vorgegeben
        if format_hint:
            for parser_cls in self.PARSERS:
                if parser_cls.FORMAT == format_hint:
                    return format_hint, 1.0, parser_cls

        # Auto-Erkennung
        results = detect_format(content, filename)

        if not results:
            # Fallback auf Generic CSV
            return ImportFormat.CSV_GENERIC, 0.3, GenericCSVParser

        # Bester Match
        parser_cls, confidence = results[0]
        return parser_cls.FORMAT, confidence, parser_cls

    async def _check_duplicate(
        self,
        db: AsyncSession,
        bank_account_id: Optional[UUID],
        tx: ParsedTransaction,
    ) -> bool:
        """Pruefe ob Transaktion bereits existiert."""
        from app.db.models import BankTransaction

        if not bank_account_id:
            return False

        # Suche nach gleicher Transaction
        query = select(BankTransaction).where(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.booking_date == tx.booking_date,
                BankTransaction.amount == tx.amount,
                or_(
                    BankTransaction.transaction_id == tx.transaction_id,
                    and_(
                        BankTransaction.counterparty_name == tx.counterparty_name,
                        BankTransaction.reference_text == tx.reference_text,
                    )
                )
            )
        )

        result = await db.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_import_history(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> List[BankImportResponse]:
        """Hole Import-Historie.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optionaler Filter auf Bankkonto
            limit: Maximale Anzahl

        Returns:
            Liste von Imports
        """
        from app.db.models import BankImport

        query = select(BankImport).where(BankImport.user_id == user_id)

        if bank_account_id:
            query = query.where(BankImport.bank_account_id == bank_account_id)

        query = query.order_by(BankImport.imported_at.desc()).limit(limit)

        result = await db.execute(query)
        imports = result.scalars().all()

        return [
            BankImportResponse(
                id=imp.id,
                filename=imp.filename,
                format=ImportFormat(imp.format) if imp.format else ImportFormat.CSV_GENERIC,
                format_variant=imp.format_variant,
                status=imp.status,
                transaction_count=imp.transaction_count,
                duplicate_count=imp.duplicate_count,
                error_count=imp.error_count,
                date_from=imp.date_from,
                date_to=imp.date_to,
                imported_at=imp.imported_at,
                processing_duration_ms=imp.processing_duration_ms,
                errors=imp.errors or [],
            )
            for imp in imports
        ]
