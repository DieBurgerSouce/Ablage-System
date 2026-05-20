# -*- coding: utf-8 -*-
"""SEPA-Lastschrift Service.

Ermöglicht das automatische Einziehen von Zahlungen von Kunden via SEPA-Lastschrift.

Features:
- Mandate-Verwaltung (SEPA-Mandat)
- Lastschrift-Erstellung (CORE/B2B)
- Batch-Einzug mehrerer Lastschriften
- Pre-Notification Handling
- Rücklauf-Bearbeitung (R-Transaktionen)
- XML-Generierung (pain.008)
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from uuid import UUID, uuid4
import structlog
import re
import hashlib

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.db.models import BusinessEntity

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================

class DirectDebitType(str, Enum):
    """SEPA-Lastschrift-Typen."""
    CORE = "core"  # Basislastschrift (8 Wochen Widerspruchsrecht)
    B2B = "b2b"  # Firmenlastschrift (kein Widerspruchsrecht)


class MandateStatus(str, Enum):
    """Status eines SEPA-Mandats."""
    ACTIVE = "active"
    PENDING = "pending"  # Noch nicht bestätigt
    REVOKED = "revoked"  # Widerrufen
    EXPIRED = "expired"  # Abgelaufen (36 Monate ohne Nutzung)


class SequenceType(str, Enum):
    """Sequenztyp der Lastschrift."""
    FRST = "FRST"  # Erstmalige Lastschrift
    RCUR = "RCUR"  # Wiederkehrende Lastschrift
    FNAL = "FNAL"  # Letzte Lastschrift einer Serie
    OOFF = "OOFF"  # Einmalige Lastschrift


class DirectDebitStatus(str, Enum):
    """Status einer Lastschrift."""
    DRAFT = "draft"  # Entwurf
    PENDING = "pending"  # Wartet auf Einreichung
    SUBMITTED = "submitted"  # Bei Bank eingereicht
    BOOKED = "booked"  # Erfolgreich gebucht
    RETURNED = "returned"  # Zurückgegeben (R-Transaktion)
    CANCELLED = "cancelled"  # Storniert


class ReturnReasonCode(str, Enum):
    """SEPA R-Transaktions-Gruende."""
    AC01 = "AC01"  # Konto nicht gefunden
    AC04 = "AC04"  # Konto geschlossen
    AC06 = "AC06"  # Konto gesperrt
    AC13 = "AC13"  # Kontoinhaber verstorben
    AG01 = "AG01"  # Transaktion verboten (Kontoart)
    AG02 = "AG02"  # Falsche Transaktionscode
    AM04 = "AM04"  # Nicht genug Deckung
    AM05 = "AM05"  # Doppelte Einreichung
    FF01 = "FF01"  # Ungültige Datei
    MD01 = "MD01"  # Kein gültiges Mandat
    MD02 = "MD02"  # Mandat abgelaufen
    MD06 = "MD06"  # Rückgabe auf Kundenwunsch
    MD07 = "MD07"  # Kontoinhaber verstorben
    MS02 = "MS02"  # Unbekannter Grund
    MS03 = "MS03"  # Unbekannter Grund
    SL01 = "SL01"  # Service nicht verfügbar
    RC01 = "RC01"  # Ungültige BIC


# Gruende auf Deutsch
RETURN_REASON_LABELS: Dict[str, str] = {
    "AC01": "Konto nicht gefunden",
    "AC04": "Konto geschlossen",
    "AC06": "Konto gesperrt",
    "AC13": "Kontoinhaber verstorben",
    "AG01": "Transaktion für Kontoart nicht erlaubt",
    "AG02": "Falscher Transaktionscode",
    "AM04": "Nicht ausreichend Deckung",
    "AM05": "Doppelte Einreichung",
    "FF01": "Ungültige Datei",
    "MD01": "Kein gültiges Mandat vorhanden",
    "MD02": "Mandat abgelaufen oder ungültig",
    "MD06": "Rückgabe auf Kundenwunsch",
    "MD07": "Kontoinhaber verstorben",
    "MS02": "Grund nicht angegeben",
    "MS03": "Grund nicht angegeben",
    "SL01": "Service nicht verfügbar",
    "RC01": "Ungültige BIC",
}


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class SEPAMandate:
    """SEPA-Lastschrift-Mandat."""
    id: UUID
    company_id: UUID
    entity_id: UUID  # Kunde

    # Mandatsdaten
    mandate_reference: str  # Eindeutige Mandatsreferenz
    signature_date: date  # Unterschriftsdatum
    debtor_name: str  # Name des Zahlers
    debtor_iban: str
    debtor_bic: Optional[str] = None

    # Konfiguration
    mandate_type: DirectDebitType = DirectDebitType.CORE
    status: MandateStatus = MandateStatus.PENDING

    # Nutzung
    first_collection_date: Optional[date] = None
    last_collection_date: Optional[date] = None
    collection_count: int = 0

    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None


@dataclass
class DirectDebitEntry:
    """Einzelne Lastschrift-Buchung."""
    id: UUID
    company_id: UUID
    mandate_id: UUID

    # Betrag
    amount: Decimal

    # Referenzen (Pflichtfelder zuerst)
    end_to_end_id: str

    # Timing (Pflichtfeld)
    requested_collection_date: date

    # Optionale Felder mit Defaults
    currency: str = "EUR"
    invoice_reference: Optional[str] = None
    linked_invoice_id: Optional[UUID] = None
    actual_collection_date: Optional[date] = None

    # Sequenz
    sequence_type: SequenceType = SequenceType.RCUR

    # Status
    status: DirectDebitStatus = DirectDebitStatus.DRAFT

    # Beschreibung
    remittance_info: str = ""  # Verwendungszweck

    # Rücklauf
    return_reason: Optional[ReturnReasonCode] = None
    return_date: Optional[date] = None

    # Audit
    created_at: datetime = field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    booked_at: Optional[datetime] = None


@dataclass
class DirectDebitBatch:
    """Batch von Lastschriften für gemeinsame Einreichung."""
    # Pflichtfelder (keine Defaults)
    id: UUID
    company_id: UUID
    name: str
    creation_date: date
    requested_collection_date: date
    debit_type: DirectDebitType
    sequence_type: SequenceType

    # Optionale Felder mit Defaults
    entry_count: int = 0
    total_amount: Decimal = Decimal("0.00")
    status: DirectDebitStatus = DirectDebitStatus.DRAFT

    # Einreichung
    creditor_name: str = ""
    creditor_iban: str = ""
    creditor_bic: Optional[str] = None
    creditor_id: str = ""  # Glaeubiger-ID

    # XML-Daten
    xml_content: Optional[str] = None
    message_id: Optional[str] = None

    # Entries
    entries: List[DirectDebitEntry] = field(default_factory=list)


@dataclass
class PreNotification:
    """Pre-Notification (Vorabinformation) an Kunden."""
    # Pflichtfelder
    mandate_id: UUID
    collection_date: date
    amount: Decimal
    remittance_info: str
    notification_date: date  # Mindestens 14 Tage vor Einzug

    # Optionale Felder
    notified_at: Optional[datetime] = None
    notification_method: str = "email"  # email, letter


@dataclass
class DirectDebitStatistics:
    """Statistiken über Lastschriften."""
    company_id: UUID
    period_start: date
    period_end: date

    # Zahlen
    total_collections: int = 0
    successful_collections: int = 0
    returned_collections: int = 0
    pending_collections: int = 0

    # Betraege
    total_amount: Decimal = Decimal("0.00")
    successful_amount: Decimal = Decimal("0.00")
    returned_amount: Decimal = Decimal("0.00")
    pending_amount: Decimal = Decimal("0.00")

    # Raten
    success_rate: float = 0.0
    return_rate: float = 0.0

    # Top R-Gruende
    return_reasons: Dict[str, int] = field(default_factory=dict)

    # Mandate
    active_mandates: int = 0
    expired_mandates: int = 0


# =============================================================================
# Service
# =============================================================================

class SEPADirectDebitService:
    """Service für SEPA-Lastschriften."""

    # Konfiguration
    MIN_PRENOTIFICATION_DAYS = 14  # Mindestens 14 Tage Vorlauf für Pre-Notification
    MANDATE_EXPIRY_MONTHS = 36  # Mandat verfaellt nach 36 Monaten ohne Nutzung

    # Mindest-Vorlaufzeiten (Werktage)
    LEAD_TIMES = {
        DirectDebitType.CORE: {
            SequenceType.FRST: 5,
            SequenceType.RCUR: 2,
            SequenceType.OOFF: 5,
            SequenceType.FNAL: 2,
        },
        DirectDebitType.B2B: {
            SequenceType.FRST: 1,
            SequenceType.RCUR: 1,
            SequenceType.OOFF: 1,
            SequenceType.FNAL: 1,
        },
    }

    # -------------------------------------------------------------------------
    # Mandate-Verwaltung
    # -------------------------------------------------------------------------

    async def create_mandate(
        self,
        db: AsyncSession,
        company_id: UUID,
        entity_id: UUID,
        debtor_name: str,
        debtor_iban: str,
        debtor_bic: Optional[str] = None,
        mandate_type: DirectDebitType = DirectDebitType.CORE,
        signature_date: Optional[date] = None,
    ) -> SEPAMandate:
        """Erstellt neues SEPA-Lastschrift-Mandat.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            entity_id: Kunden-ID (BusinessEntity)
            debtor_name: Name des Zahlers
            debtor_iban: IBAN des Zahlers
            debtor_bic: BIC (optional, wird aus IBAN ermittelt)
            mandate_type: CORE oder B2B
            signature_date: Unterschriftsdatum (default: heute)

        Returns:
            Erstelltes SEPAMandate
        """
        # Validiere IBAN
        if not self._validate_iban(debtor_iban):
            raise ValueError("Ungültige IBAN")

        # Generiere eindeutige Mandatsreferenz
        mandate_reference = self._generate_mandate_reference(company_id, entity_id)

        mandate = SEPAMandate(
            id=uuid4(),
            company_id=company_id,
            entity_id=entity_id,
            mandate_reference=mandate_reference,
            signature_date=signature_date or date.today(),
            debtor_name=debtor_name,
            debtor_iban=self._normalize_iban(debtor_iban),
            debtor_bic=debtor_bic,
            mandate_type=mandate_type,
            status=MandateStatus.PENDING,
        )

        logger.info(
            "sepa_mandate_created",
            mandate_id=str(mandate.id),
            entity_id=str(entity_id),
            mandate_type=mandate_type.value,
        )

        return mandate

    async def activate_mandate(
        self,
        db: AsyncSession,
        mandate: SEPAMandate,
    ) -> SEPAMandate:
        """Aktiviert ein Mandat (nach Eingang des unterschriebenen Formulars)."""
        if mandate.status != MandateStatus.PENDING:
            raise ValueError(f"Mandat kann nicht aktiviert werden (Status: {mandate.status})")

        mandate.status = MandateStatus.ACTIVE
        mandate.updated_at = datetime.utcnow()

        logger.info(
            "sepa_mandate_activated",
            mandate_id=str(mandate.id),
        )

        return mandate

    async def revoke_mandate(
        self,
        db: AsyncSession,
        mandate: SEPAMandate,
        reason: str,
    ) -> SEPAMandate:
        """Widerruft ein Mandat."""
        mandate.status = MandateStatus.REVOKED
        mandate.revoked_at = datetime.utcnow()
        mandate.revocation_reason = reason
        mandate.updated_at = datetime.utcnow()

        logger.info(
            "sepa_mandate_revoked",
            mandate_id=str(mandate.id),
            reason=reason,
        )

        return mandate

    async def check_mandate_expiry(
        self,
        mandate: SEPAMandate,
    ) -> bool:
        """Prüft ob Mandat abgelaufen ist (36 Monate ohne Nutzung).

        Returns:
            True wenn abgelaufen, sonst False
        """
        if mandate.status != MandateStatus.ACTIVE:
            return mandate.status == MandateStatus.EXPIRED

        # Letzte Nutzung bestimmen
        last_use = mandate.last_collection_date or mandate.signature_date
        months_since_use = (date.today() - last_use).days / 30

        if months_since_use >= self.MANDATE_EXPIRY_MONTHS:
            return True

        return False

    # -------------------------------------------------------------------------
    # Lastschrift-Erstellung
    # -------------------------------------------------------------------------

    async def create_direct_debit(
        self,
        db: AsyncSession,
        mandate: SEPAMandate,
        amount: Decimal,
        collection_date: date,
        remittance_info: str,
        invoice_reference: Optional[str] = None,
        linked_invoice_id: Optional[UUID] = None,
    ) -> DirectDebitEntry:
        """Erstellt neue Lastschrift.

        Args:
            db: Datenbank-Session
            mandate: SEPA-Mandat
            amount: Einzugsbetrag
            collection_date: Gewünschtes Einzugsdatum
            remittance_info: Verwendungszweck
            invoice_reference: Rechnungsnummer (optional)
            linked_invoice_id: Verknüpfte Rechnungs-ID (optional)

        Returns:
            Erstellte DirectDebitEntry
        """
        # Validierungen
        if mandate.status != MandateStatus.ACTIVE:
            raise ValueError(f"Mandat nicht aktiv (Status: {mandate.status})")

        if amount <= 0:
            raise ValueError("Betrag muss positiv sein")

        # Prüfe Vorlaufzeit
        min_lead_days = self._get_min_lead_days(mandate.mandate_type, self._get_sequence_type(mandate))
        min_collection_date = self._add_business_days(date.today(), min_lead_days)

        if collection_date < min_collection_date:
            raise ValueError(
                f"Einzugsdatum muss mindestens {min_lead_days} Werktage in der Zukunft liegen "
                f"(frühestens {min_collection_date})"
            )

        # Sequenztyp bestimmen
        sequence_type = self._get_sequence_type(mandate)

        # End-to-End-ID generieren
        end_to_end_id = self._generate_end_to_end_id()

        entry = DirectDebitEntry(
            id=uuid4(),
            company_id=mandate.company_id,
            mandate_id=mandate.id,
            amount=amount,
            end_to_end_id=end_to_end_id,
            invoice_reference=invoice_reference,
            linked_invoice_id=linked_invoice_id,
            requested_collection_date=collection_date,
            sequence_type=sequence_type,
            status=DirectDebitStatus.DRAFT,
            remittance_info=remittance_info[:140],  # Max 140 Zeichen
        )

        logger.info(
            "sepa_direct_debit_created",
            entry_id=str(entry.id),
            mandate_id=str(mandate.id),
            amount=str(amount),
            collection_date=str(collection_date),
        )

        return entry

    async def create_batch(
        self,
        db: AsyncSession,
        company_id: UUID,
        name: str,
        collection_date: date,
        creditor_name: str,
        creditor_iban: str,
        creditor_id: str,
        debit_type: DirectDebitType = DirectDebitType.CORE,
        creditor_bic: Optional[str] = None,
    ) -> DirectDebitBatch:
        """Erstellt neuen Lastschrift-Batch.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            name: Batch-Name (z.B. "Monatseinzug Januar 2026")
            collection_date: Einzugsdatum
            creditor_name: Name des Einreichers
            creditor_iban: IBAN des Einreichers
            creditor_id: Glaeubiger-Identifikationsnummer
            debit_type: CORE oder B2B
            creditor_bic: BIC (optional)

        Returns:
            Erstellter DirectDebitBatch
        """
        # Validiere Glaeubiger-ID (Format: DExxZZZ...)
        if not self._validate_creditor_id(creditor_id):
            raise ValueError("Ungültige Glaeubiger-Identifikationsnummer")

        batch = DirectDebitBatch(
            id=uuid4(),
            company_id=company_id,
            name=name,
            creation_date=date.today(),
            requested_collection_date=collection_date,
            debit_type=debit_type,
            sequence_type=SequenceType.RCUR,  # Wird beim Hinzufuegen aktualisiert
            creditor_name=creditor_name,
            creditor_iban=self._normalize_iban(creditor_iban),
            creditor_bic=creditor_bic,
            creditor_id=creditor_id,
        )

        logger.info(
            "sepa_batch_created",
            batch_id=str(batch.id),
            name=name,
            collection_date=str(collection_date),
        )

        return batch

    async def add_entry_to_batch(
        self,
        batch: DirectDebitBatch,
        entry: DirectDebitEntry,
    ) -> DirectDebitBatch:
        """Fuegt Lastschrift zu Batch hinzu."""
        if batch.status != DirectDebitStatus.DRAFT:
            raise ValueError("Batch kann nicht mehr bearbeitet werden")

        if entry.status != DirectDebitStatus.DRAFT:
            raise ValueError("Lastschrift wurde bereits eingereicht")

        # Prüfe Konsistenz
        if entry.requested_collection_date != batch.requested_collection_date:
            raise ValueError("Einzugsdatum stimmt nicht mit Batch überein")

        batch.entries.append(entry)
        batch.entry_count = len(batch.entries)
        batch.total_amount = sum(e.amount for e in batch.entries)

        # Sequenztyp aktualisieren (FRST hat Vorrang)
        if entry.sequence_type == SequenceType.FRST:
            batch.sequence_type = SequenceType.FRST

        entry.status = DirectDebitStatus.PENDING

        return batch

    # -------------------------------------------------------------------------
    # Pre-Notification
    # -------------------------------------------------------------------------

    async def generate_pre_notifications(
        self,
        batch: DirectDebitBatch,
        mandates: Dict[UUID, SEPAMandate],
    ) -> List[PreNotification]:
        """Generiert Pre-Notifications für alle Einträge im Batch.

        Args:
            batch: Lastschrift-Batch
            mandates: Dictionary Mandate-ID -> Mandat

        Returns:
            Liste der Pre-Notifications
        """
        notifications = []

        notification_date = self._subtract_business_days(
            batch.requested_collection_date,
            self.MIN_PRENOTIFICATION_DAYS
        )

        for entry in batch.entries:
            mandate = mandates.get(entry.mandate_id)
            if not mandate:
                logger.warning(
                    "sepa_prenotification_missing_mandate",
                    entry_id=str(entry.id),
                    mandate_id=str(entry.mandate_id),
                )
                continue

            notification = PreNotification(
                mandate_id=mandate.id,
                collection_date=entry.requested_collection_date,
                amount=entry.amount,
                remittance_info=entry.remittance_info,
                notification_date=notification_date,
            )
            notifications.append(notification)

        logger.info(
            "sepa_prenotifications_generated",
            batch_id=str(batch.id),
            count=len(notifications),
        )

        return notifications

    # -------------------------------------------------------------------------
    # XML-Generierung (pain.008)
    # -------------------------------------------------------------------------

    async def generate_pain008_xml(
        self,
        batch: DirectDebitBatch,
        mandates: Dict[UUID, SEPAMandate],
    ) -> str:
        """Generiert SEPA pain.008 XML für Batch.

        Args:
            batch: Lastschrift-Batch
            mandates: Dictionary Mandate-ID -> Mandat

        Returns:
            XML-String
        """
        if not batch.entries:
            raise ValueError("Batch enthält keine Einträge")

        message_id = self._generate_message_id()
        creation_datetime = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        # XML Header
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.008.001.02" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
            '<CstmrDrctDbtInitn>',

            # Group Header
            '<GrpHdr>',
            f'<MsgId>{message_id}</MsgId>',
            f'<CreDtTm>{creation_datetime}</CreDtTm>',
            f'<NbOfTxs>{batch.entry_count}</NbOfTxs>',
            f'<CtrlSum>{batch.total_amount:.2f}</CtrlSum>',
            '<InitgPty>',
            f'<Nm>{self._escape_xml(batch.creditor_name)}</Nm>',
            '</InitgPty>',
            '</GrpHdr>',

            # Payment Information
            '<PmtInf>',
            f'<PmtInfId>{message_id}-1</PmtInfId>',
            '<PmtMtd>DD</PmtMtd>',
            f'<NbOfTxs>{batch.entry_count}</NbOfTxs>',
            f'<CtrlSum>{batch.total_amount:.2f}</CtrlSum>',

            # Payment Type Info
            '<PmtTpInf>',
            '<SvcLvl><Cd>SEPA</Cd></SvcLvl>',
            f'<LclInstrm><Cd>{batch.debit_type.value.upper()}</Cd></LclInstrm>',
            f'<SeqTp>{batch.sequence_type.value}</SeqTp>',
            '</PmtTpInf>',

            f'<ReqdColltnDt>{batch.requested_collection_date}</ReqdColltnDt>',

            # Creditor
            '<Cdtr>',
            f'<Nm>{self._escape_xml(batch.creditor_name)}</Nm>',
            '</Cdtr>',
            '<CdtrAcct>',
            f'<Id><IBAN>{batch.creditor_iban}</IBAN></Id>',
            '</CdtrAcct>',
            '<CdtrAgt>',
        ]

        if batch.creditor_bic:
            xml_parts.append(f'<FinInstnId><BIC>{batch.creditor_bic}</BIC></FinInstnId>')
        else:
            xml_parts.append('<FinInstnId><Othr><Id>NOTPROVIDED</Id></Othr></FinInstnId>')

        xml_parts.extend([
            '</CdtrAgt>',
            '<CdtrSchmeId>',
            '<Id>',
            '<PrvtId>',
            '<Othr>',
            f'<Id>{batch.creditor_id}</Id>',
            '<SchmeNm><Prtry>SEPA</Prtry></SchmeNm>',
            '</Othr>',
            '</PrvtId>',
            '</Id>',
            '</CdtrSchmeId>',
        ])

        # Transactions
        for entry in batch.entries:
            mandate = mandates.get(entry.mandate_id)
            if not mandate:
                continue

            xml_parts.extend([
                '<DrctDbtTxInf>',
                '<PmtId>',
                f'<EndToEndId>{entry.end_to_end_id}</EndToEndId>',
                '</PmtId>',
                f'<InstdAmt Ccy="{entry.currency}">{entry.amount:.2f}</InstdAmt>',

                # Mandate Info
                '<DrctDbtTx>',
                '<MndtRltdInf>',
                f'<MndtId>{mandate.mandate_reference}</MndtId>',
                f'<DtOfSgntr>{mandate.signature_date}</DtOfSgntr>',
                '</MndtRltdInf>',
                '</DrctDbtTx>',

                # Debtor Agent
                '<DbtrAgt>',
            ])

            if mandate.debtor_bic:
                xml_parts.append(f'<FinInstnId><BIC>{mandate.debtor_bic}</BIC></FinInstnId>')
            else:
                xml_parts.append('<FinInstnId><Othr><Id>NOTPROVIDED</Id></Othr></FinInstnId>')

            xml_parts.extend([
                '</DbtrAgt>',

                # Debtor
                '<Dbtr>',
                f'<Nm>{self._escape_xml(mandate.debtor_name)}</Nm>',
                '</Dbtr>',
                '<DbtrAcct>',
                f'<Id><IBAN>{mandate.debtor_iban}</IBAN></Id>',
                '</DbtrAcct>',

                # Remittance Info
                '<RmtInf>',
                f'<Ustrd>{self._escape_xml(entry.remittance_info)}</Ustrd>',
                '</RmtInf>',

                '</DrctDbtTxInf>',
            ])

        xml_parts.extend([
            '</PmtInf>',
            '</CstmrDrctDbtInitn>',
            '</Document>',
        ])

        xml_content = '\n'.join(xml_parts)

        batch.xml_content = xml_content
        batch.message_id = message_id
        batch.status = DirectDebitStatus.PENDING

        logger.info(
            "sepa_pain008_generated",
            batch_id=str(batch.id),
            message_id=message_id,
            entry_count=batch.entry_count,
            total_amount=str(batch.total_amount),
        )

        return xml_content

    # -------------------------------------------------------------------------
    # Rücklauf-Bearbeitung
    # -------------------------------------------------------------------------

    async def process_return(
        self,
        entry: DirectDebitEntry,
        reason_code: ReturnReasonCode,
        return_date: date,
    ) -> DirectDebitEntry:
        """Verarbeitet R-Transaktion (Rücklauf).

        Args:
            entry: Lastschrift-Eintrag
            reason_code: R-Code
            return_date: Datum der Rückgabe

        Returns:
            Aktualisierter Eintrag
        """
        entry.status = DirectDebitStatus.RETURNED
        entry.return_reason = reason_code
        entry.return_date = return_date

        reason_label = RETURN_REASON_LABELS.get(reason_code.value, "Unbekannter Grund")

        logger.warning(
            "sepa_direct_debit_returned",
            entry_id=str(entry.id),
            reason_code=reason_code.value,
            reason_label=reason_label,
            amount=str(entry.amount),
        )

        return entry

    # -------------------------------------------------------------------------
    # Statistiken
    # -------------------------------------------------------------------------

    async def get_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
        entries: List[DirectDebitEntry],
        period_start: date,
        period_end: date,
    ) -> DirectDebitStatistics:
        """Berechnet Statistiken über Lastschriften.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            entries: Liste der Lastschrift-Einträge
            period_start: Periodenstart
            period_end: Periodenende

        Returns:
            DirectDebitStatistics
        """
        stats = DirectDebitStatistics(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
        )

        # Filtere nach Periode
        period_entries = [
            e for e in entries
            if period_start <= e.requested_collection_date <= period_end
        ]

        stats.total_collections = len(period_entries)
        stats.total_amount = sum(e.amount for e in period_entries)

        # Nach Status gruppieren
        for entry in period_entries:
            if entry.status == DirectDebitStatus.BOOKED:
                stats.successful_collections += 1
                stats.successful_amount += entry.amount
            elif entry.status == DirectDebitStatus.RETURNED:
                stats.returned_collections += 1
                stats.returned_amount += entry.amount
                # R-Gruende zaehlen
                if entry.return_reason:
                    code = entry.return_reason.value
                    stats.return_reasons[code] = stats.return_reasons.get(code, 0) + 1
            elif entry.status in [DirectDebitStatus.PENDING, DirectDebitStatus.SUBMITTED]:
                stats.pending_collections += 1
                stats.pending_amount += entry.amount

        # Raten berechnen
        if stats.total_collections > 0:
            stats.success_rate = stats.successful_collections / stats.total_collections
            stats.return_rate = stats.returned_collections / stats.total_collections

        return stats

    # -------------------------------------------------------------------------
    # Hilfsmethoden
    # -------------------------------------------------------------------------

    def _validate_iban(self, iban: str) -> bool:
        """Validiert IBAN."""
        iban = self._normalize_iban(iban)

        if len(iban) < 15 or len(iban) > 34:
            return False

        # Grundformat prüfen
        if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]+$', iban):
            return False

        # Checksum prüfen
        check_iban = iban[4:] + iban[:4]
        numeric = ''
        for char in check_iban:
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - 55)

        return int(numeric) % 97 == 1

    def _normalize_iban(self, iban: str) -> str:
        """Normalisiert IBAN (entfernt Leerzeichen, uppercase)."""
        return iban.replace(' ', '').upper()

    def _validate_creditor_id(self, creditor_id: str) -> bool:
        """Validiert Glaeubiger-Identifikationsnummer.

        Format: DExxZZZ... (Ländercode + Prüfziffer + Geschäftsbereichskennung + Nationales Kennzeichen)
        """
        if not creditor_id or len(creditor_id) < 8:
            return False

        # Grundformat: 2 Buchstaben + 2 Ziffern + Rest
        if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]+$', creditor_id):
            return False

        return True

    def _generate_mandate_reference(self, company_id: UUID, entity_id: UUID) -> str:
        """Generiert eindeutige Mandatsreferenz."""
        base = f"{str(company_id)[:8]}-{str(entity_id)[:8]}-{date.today().strftime('%Y%m%d')}"
        hash_suffix = hashlib.md5(f"{base}-{uuid4()}".encode()).hexdigest()[:6].upper()
        return f"MNDT-{hash_suffix}"

    def _generate_end_to_end_id(self) -> str:
        """Generiert End-to-End-ID."""
        return f"E2E-{uuid4().hex[:16].upper()}"

    def _generate_message_id(self) -> str:
        """Generiert Message-ID für XML."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"MSG-{timestamp}-{uuid4().hex[:8].upper()}"

    def _escape_xml(self, text: str) -> str:
        """Escaped XML-Sonderzeichen."""
        return (
            text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;')
        )

    def _get_sequence_type(self, mandate: SEPAMandate) -> SequenceType:
        """Bestimmt Sequenztyp basierend auf Mandatsnutzung."""
        if mandate.collection_count == 0:
            return SequenceType.FRST
        return SequenceType.RCUR

    def _get_min_lead_days(self, debit_type: DirectDebitType, sequence_type: SequenceType) -> int:
        """Gibt minimale Vorlaufzeit in Werktagen zurück."""
        return self.LEAD_TIMES[debit_type][sequence_type]

    def _add_business_days(self, start_date: date, days: int) -> date:
        """Addiert Werktage zu Datum."""
        current = start_date
        added = 0
        while added < days:
            current += timedelta(days=1)
            # Samstag=5, Sonntag=6
            if current.weekday() < 5:
                added += 1
        return current

    def _subtract_business_days(self, start_date: date, days: int) -> date:
        """Subtrahiert Werktage von Datum."""
        current = start_date
        subtracted = 0
        while subtracted < days:
            current -= timedelta(days=1)
            if current.weekday() < 5:
                subtracted += 1
        return current


# Singleton
_sepa_direct_debit_service: Optional[SEPADirectDebitService] = None


def get_sepa_direct_debit_service() -> SEPADirectDebitService:
    """Gibt Singleton-Instanz zurück."""
    global _sepa_direct_debit_service
    if _sepa_direct_debit_service is None:
        _sepa_direct_debit_service = SEPADirectDebitService()
    return _sepa_direct_debit_service
