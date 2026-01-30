"""SEPA Credit Transfer Service (pain.001).

Generiert SEPA-Ueberweisungsdateien im pain.001 Format (ISO 20022).
Unterstuetzt:
- Einzelueberweisungen (pain.001.003.03)
- Sammelueberweisungen (pain.001.001.03)
- Terminueberweisungen

SECURITY:
- Validierung aller IBAN/BIC
- Betragsgrenzen
- Verwendungszweck-Pruefung auf verbotene Zeichen
"""

import xml.etree.ElementTree as ET
import defusedxml.ElementTree as DefusedET
from app.core.safe_errors import safe_error_detail, safe_error_log
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import re
import structlog
from dataclasses import dataclass, field

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator

from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants & Enums
# =============================================================================


class SEPAChargeBearer(str, Enum):
    """Gebuehrenregelung."""
    SLEV = "SLEV"  # Service Level - Standard
    SHAR = "SHAR"  # Shared - aufgeteilt
    DEBT = "DEBT"  # Debtor pays all
    CRED = "CRED"  # Creditor pays all


class SEPAServiceLevel(str, Enum):
    """SEPA Service Level."""
    SEPA = "SEPA"  # Standard SEPA
    URGP = "URGP"  # Urgent Payment (Eilueberweisung)


class SEPAPaymentMethod(str, Enum):
    """Zahlungsmethode."""
    TRF = "TRF"  # Transfer


class SEPALocalInstrument(str, Enum):
    """Lokales Zahlungsinstrument."""
    INST = "INST"  # Instant Payment (SEPA Instant)
    NORM = None  # Normal SEPA


class BatchBookingPreference(str, Enum):
    """Buchungsart fuer Sammelueberweisungen."""
    TRUE = "true"  # Sammelbuchung
    FALSE = "false"  # Einzelbuchungen


# Erlaubte Zeichen im SEPA-Zahlungsverkehr (EPC Quick Reference Guide)
SEPA_ALLOWED_CHARS = re.compile(
    r"^[a-zA-Z0-9 .,'()+\-/:?]*$"
)

# Maximale Zeichenlaengen nach SEPA-Spezifikation
MAX_NAME_LENGTH = 70
MAX_REFERENCE_LENGTH = 140
MAX_IBAN_LENGTH = 34
MAX_BIC_LENGTH = 11


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SEPACreditTransferTransaction:
    """Einzelne SEPA-Ueberweisung."""
    payment_id: str  # Eindeutige ID (EndToEndId)
    amount: Decimal
    currency: str = "EUR"

    # Empfaenger
    creditor_name: str = ""
    creditor_iban: str = ""
    creditor_bic: Optional[str] = None  # Optional fuer EU-Inlandsueberweisungen
    creditor_address: Optional[Dict[str, str]] = None

    # Verwendungszweck
    remittance_info: str = ""  # Unstrukturiert (max 140 Zeichen)
    structured_remittance: Optional[Dict[str, str]] = None  # Strukturiert

    # Optionale Felder
    instruction_id: Optional[str] = None
    execution_date: Optional[date] = None  # Null = sofort
    purpose_code: Optional[str] = None  # z.B. "SALA" fuer Gehalt
    category_purpose: Optional[str] = None

    def validate(self) -> List[str]:
        """Validiere die Transaktion.

        Returns:
            Liste von Fehlermeldungen (leer wenn valide)
        """
        errors = []

        # Betrag
        if self.amount <= 0:
            errors.append("Betrag muss positiv sein")
        if self.amount > Decimal("999999999.99"):
            errors.append("Betrag ueberschreitet Maximum")

        # IBAN
        if not self.creditor_iban:
            errors.append("Empfaenger-IBAN fehlt")
        elif not self._validate_iban(self.creditor_iban):
            errors.append(f"Ungueltige Empfaenger-IBAN: {self.creditor_iban}")

        # BIC (optional, aber wenn vorhanden validieren)
        if self.creditor_bic and not self._validate_bic(self.creditor_bic):
            errors.append(f"Ungueltige Empfaenger-BIC: {self.creditor_bic}")

        # Name
        if not self.creditor_name:
            errors.append("Empfaengername fehlt")
        elif len(self.creditor_name) > MAX_NAME_LENGTH:
            errors.append(f"Empfaengername zu lang (max {MAX_NAME_LENGTH} Zeichen)")
        elif not SEPA_ALLOWED_CHARS.match(self.creditor_name):
            errors.append("Empfaengername enthaelt ungueltige Zeichen")

        # Verwendungszweck
        if self.remittance_info:
            if len(self.remittance_info) > MAX_REFERENCE_LENGTH:
                errors.append(f"Verwendungszweck zu lang (max {MAX_REFERENCE_LENGTH} Zeichen)")
            if not SEPA_ALLOWED_CHARS.match(self.remittance_info):
                errors.append("Verwendungszweck enthaelt ungueltige Zeichen")

        return errors

    def _validate_iban(self, iban: str) -> bool:
        """Validiere IBAN mit MOD-97."""
        iban = iban.replace(" ", "").upper()
        if len(iban) < 15 or len(iban) > MAX_IBAN_LENGTH:
            return False
        if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]+$", iban):
            return False
        # MOD-97 Pruefung
        rearranged = iban[4:] + iban[:4]
        numeric = ""
        for char in rearranged:
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - ord("A") + 10)
        try:
            return int(numeric) % 97 == 1
        except ValueError:
            return False

    def _validate_bic(self, bic: str) -> bool:
        """Validiere BIC."""
        bic = bic.upper()
        if len(bic) not in [8, 11]:
            return False
        # Format: XXXXYYCC[ZZZ]
        # XXXX = Bankcode
        # YY = Laendercode
        # CC = Ort
        # ZZZ = Filiale (optional)
        return bool(re.match(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$", bic))


@dataclass
class SEPACreditTransferBatch:
    """SEPA-Sammelauftrag (Payment Information Block)."""
    batch_id: str
    debtor_name: str
    debtor_iban: str
    debtor_bic: Optional[str] = None
    execution_date: Optional[date] = None  # Null = ASAP
    batch_booking: bool = False  # True = Sammelbuchung
    transactions: List[SEPACreditTransferTransaction] = field(default_factory=list)
    charge_bearer: SEPAChargeBearer = SEPAChargeBearer.SLEV
    service_level: SEPAServiceLevel = SEPAServiceLevel.SEPA

    @property
    def total_amount(self) -> Decimal:
        """Berechne Gesamtsumme."""
        return sum(tx.amount for tx in self.transactions)

    @property
    def transaction_count(self) -> int:
        """Anzahl Transaktionen."""
        return len(self.transactions)


@dataclass
class SEPACreditTransferMessage:
    """Komplette SEPA-Nachricht (pain.001)."""
    message_id: str
    created_at: datetime
    initiating_party_name: str
    initiating_party_id: Optional[str] = None
    batches: List[SEPACreditTransferBatch] = field(default_factory=list)

    @property
    def total_amount(self) -> Decimal:
        """Gesamtsumme aller Batches."""
        return sum(batch.total_amount for batch in self.batches)

    @property
    def transaction_count(self) -> int:
        """Gesamtzahl Transaktionen."""
        return sum(batch.transaction_count for batch in self.batches)


# =============================================================================
# Pydantic Models fuer API
# =============================================================================


class CreditTransferCreate(BaseModel):
    """Request zum Erstellen einer SEPA-Ueberweisung."""
    bank_account_id: UUID
    creditor_name: str = Field(..., min_length=1, max_length=70)
    creditor_iban: str = Field(..., min_length=15, max_length=34)
    creditor_bic: Optional[str] = Field(None, max_length=11)
    amount: Decimal = Field(..., gt=0)
    remittance_info: str = Field(..., min_length=1, max_length=140)
    execution_date: Optional[date] = None
    is_instant: bool = False  # SEPA Instant Payment

    @field_validator("creditor_iban")
    @classmethod
    def normalize_iban(cls, v: str) -> str:
        return v.replace(" ", "").upper()

    @field_validator("creditor_bic")
    @classmethod
    def normalize_bic(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else None


class BatchTransferCreate(BaseModel):
    """Request zum Erstellen einer Sammelueberweisung."""
    bank_account_id: UUID
    batch_name: Optional[str] = Field(None, max_length=70)
    execution_date: Optional[date] = None
    batch_booking: bool = False
    transfer_ids: List[UUID]  # IDs von einzelnen PaymentOrders


class Pain001ExportResult(BaseModel):
    """Ergebnis des pain.001 Exports."""
    message_id: str
    filename: str
    xml_content: str
    transaction_count: int
    total_amount: Decimal
    currency: str
    created_at: datetime


# =============================================================================
# Service
# =============================================================================


class SEPACreditTransferService:
    """Service fuer SEPA Credit Transfers (pain.001).

    Generiert ISO 20022 konforme XML-Dateien fuer:
    - Einzelueberweisungen
    - Sammelueberweisungen
    - SEPA Instant Payments

    Die generierten Dateien koennen:
    - Via FinTS an die Bank gesendet werden
    - Manuell im Online-Banking hochgeladen werden
    - An einen Zahlungsdienstleister uebermittelt werden
    """

    # pain.001.003.03 Namespace (Standard fuer deutsche Banken)
    NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:pain.001.003.03"
    XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

    def __init__(self):
        """Initialisiere Service."""
        pass

    async def create_single_transfer(
        self,
        db: AsyncSession,
        user_id: UUID,
        data: CreditTransferCreate,
    ) -> Pain001ExportResult:
        """Erstelle pain.001 fuer Einzelueberweisung.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            data: Ueberweisungsdaten

        Returns:
            Export-Ergebnis mit XML

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        from app.db.models import BankAccount

        # Lade Absender-Konto
        account = await db.get(BankAccount, data.bank_account_id)
        if not account or account.user_id != user_id:
            raise ValueError("Bankkonto nicht gefunden oder keine Berechtigung")

        # Erstelle Transaktion
        payment_id = f"TRF-{uuid4().hex[:12].upper()}"
        transaction = SEPACreditTransferTransaction(
            payment_id=payment_id,
            amount=data.amount,
            creditor_name=data.creditor_name,
            creditor_iban=data.creditor_iban,
            creditor_bic=data.creditor_bic,
            remittance_info=data.remittance_info,
            execution_date=data.execution_date,
        )

        # Validiere
        errors = transaction.validate()
        if errors:
            raise ValueError("; ".join(errors))

        # Erstelle Batch
        batch = SEPACreditTransferBatch(
            batch_id=f"BATCH-{uuid4().hex[:8].upper()}",
            debtor_name=account.account_holder or account.account_name,
            debtor_iban=account.iban,
            debtor_bic=account.bic,
            execution_date=data.execution_date,
            transactions=[transaction],
        )

        # Erstelle Message
        message_id = f"MSG-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"
        message = SEPACreditTransferMessage(
            message_id=message_id,
            created_at=utc_now(),
            initiating_party_name=account.account_holder or account.account_name,
            batches=[batch],
        )

        # Generiere XML
        xml_content = self._generate_pain001_xml(message, is_instant=data.is_instant)

        # Dateiname
        filename = f"SEPA_CT_{message_id}.xml"

        logger.info(
            "sepa_credit_transfer_created",
            message_id=message_id,
            amount=str(data.amount),
            # SECURITY: Keine Empfaengerdaten loggen!
        )

        return Pain001ExportResult(
            message_id=message_id,
            filename=filename,
            xml_content=xml_content,
            transaction_count=1,
            total_amount=data.amount,
            currency="EUR",
            created_at=utc_now(),
        )

    async def create_batch_transfer(
        self,
        db: AsyncSession,
        user_id: UUID,
        data: BatchTransferCreate,
    ) -> Pain001ExportResult:
        """Erstelle pain.001 fuer Sammelueberweisung.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            data: Batch-Daten

        Returns:
            Export-Ergebnis mit XML
        """
        from app.db.models import BankAccount, PaymentOrder

        # Lade Absender-Konto
        account = await db.get(BankAccount, data.bank_account_id)
        if not account or account.user_id != user_id:
            raise ValueError("Bankkonto nicht gefunden oder keine Berechtigung")

        # Lade Payment Orders
        result = await db.execute(
            select(PaymentOrder).where(
                and_(
                    PaymentOrder.id.in_(data.transfer_ids),
                    PaymentOrder.user_id == user_id,
                    PaymentOrder.bank_account_id == data.bank_account_id,
                    PaymentOrder.status.in_(["draft", "approved"]),
                )
            )
        )
        payment_orders = result.scalars().all()

        if len(payment_orders) != len(data.transfer_ids):
            raise ValueError(
                f"Nicht alle Zahlungsauftraege gefunden oder gueltig "
                f"({len(payment_orders)} von {len(data.transfer_ids)})"
            )

        # Erstelle Transaktionen
        transactions = []
        for po in payment_orders:
            tx = SEPACreditTransferTransaction(
                payment_id=f"TRF-{po.id.hex[:12].upper()}",
                amount=po.amount,
                creditor_name=po.beneficiary_name,
                creditor_iban=po.beneficiary_iban,
                creditor_bic=po.beneficiary_bic,
                remittance_info=po.reference or f"Rechnung {po.invoice_number}",
                execution_date=data.execution_date or po.execution_date,
            )

            errors = tx.validate()
            if errors:
                raise ValueError(f"Fehler in Zahlung {po.id}: {'; '.join(errors)}")

            transactions.append(tx)

        # Erstelle Batch
        batch = SEPACreditTransferBatch(
            batch_id=f"BATCH-{uuid4().hex[:8].upper()}",
            debtor_name=account.account_holder or account.account_name,
            debtor_iban=account.iban,
            debtor_bic=account.bic,
            execution_date=data.execution_date,
            batch_booking=data.batch_booking,
            transactions=transactions,
        )

        # Erstelle Message
        message_id = f"BATCH-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"
        message = SEPACreditTransferMessage(
            message_id=message_id,
            created_at=utc_now(),
            initiating_party_name=account.account_holder or account.account_name,
            batches=[batch],
        )

        # Generiere XML
        xml_content = self._generate_pain001_xml(message)

        # Update Payment Orders Status
        for po in payment_orders:
            po.status = "submitted"
            po.submitted_at = utc_now()

        await db.flush()

        filename = f"SEPA_BATCH_{message_id}.xml"

        logger.info(
            "sepa_batch_transfer_created",
            message_id=message_id,
            transaction_count=len(transactions),
            total_amount=str(batch.total_amount),
        )

        return Pain001ExportResult(
            message_id=message_id,
            filename=filename,
            xml_content=xml_content,
            transaction_count=len(transactions),
            total_amount=batch.total_amount,
            currency="EUR",
            created_at=utc_now(),
        )

    def _generate_pain001_xml(
        self,
        message: SEPACreditTransferMessage,
        is_instant: bool = False,
    ) -> str:
        """Generiere pain.001.003.03 XML.

        Args:
            message: SEPA-Nachricht
            is_instant: True fuer SEPA Instant

        Returns:
            XML als String
        """
        # Root Element
        root = ET.Element("Document")
        root.set("xmlns", self.NAMESPACE)
        root.set("xmlns:xsi", self.XSI_NAMESPACE)

        # CstmrCdtTrfInitn (Customer Credit Transfer Initiation)
        cstmr = ET.SubElement(root, "CstmrCdtTrfInitn")

        # Group Header
        grp_hdr = ET.SubElement(cstmr, "GrpHdr")
        ET.SubElement(grp_hdr, "MsgId").text = message.message_id
        ET.SubElement(grp_hdr, "CreDtTm").text = message.created_at.strftime("%Y-%m-%dT%H:%M:%S")
        ET.SubElement(grp_hdr, "NbOfTxs").text = str(message.transaction_count)
        ET.SubElement(grp_hdr, "CtrlSum").text = f"{message.total_amount:.2f}"

        # Initiating Party
        init_pty = ET.SubElement(grp_hdr, "InitgPty")
        ET.SubElement(init_pty, "Nm").text = self._sanitize_text(
            message.initiating_party_name, MAX_NAME_LENGTH
        )
        if message.initiating_party_id:
            id_elem = ET.SubElement(init_pty, "Id")
            org_id = ET.SubElement(id_elem, "OrgId")
            other = ET.SubElement(org_id, "Othr")
            ET.SubElement(other, "Id").text = message.initiating_party_id

        # Payment Information (je Batch)
        for batch in message.batches:
            pmt_inf = ET.SubElement(cstmr, "PmtInf")

            ET.SubElement(pmt_inf, "PmtInfId").text = batch.batch_id
            ET.SubElement(pmt_inf, "PmtMtd").text = SEPAPaymentMethod.TRF.value
            ET.SubElement(pmt_inf, "BtchBookg").text = "true" if batch.batch_booking else "false"
            ET.SubElement(pmt_inf, "NbOfTxs").text = str(batch.transaction_count)
            ET.SubElement(pmt_inf, "CtrlSum").text = f"{batch.total_amount:.2f}"

            # Payment Type Information
            pmt_tp = ET.SubElement(pmt_inf, "PmtTpInf")
            svc_lvl = ET.SubElement(pmt_tp, "SvcLvl")
            ET.SubElement(svc_lvl, "Cd").text = batch.service_level.value

            # SEPA Instant
            if is_instant:
                lcl_inst = ET.SubElement(pmt_tp, "LclInstrm")
                ET.SubElement(lcl_inst, "Cd").text = "INST"

            # Execution Date
            exec_date = batch.execution_date or date.today()
            ET.SubElement(pmt_inf, "ReqdExctnDt").text = exec_date.isoformat()

            # Debtor (Auftraggeber)
            dbtr = ET.SubElement(pmt_inf, "Dbtr")
            ET.SubElement(dbtr, "Nm").text = self._sanitize_text(
                batch.debtor_name, MAX_NAME_LENGTH
            )

            # Debtor Account
            dbtr_acct = ET.SubElement(pmt_inf, "DbtrAcct")
            dbtr_acct_id = ET.SubElement(dbtr_acct, "Id")
            ET.SubElement(dbtr_acct_id, "IBAN").text = batch.debtor_iban.replace(" ", "").upper()

            # Debtor Agent (Bank)
            dbtr_agt = ET.SubElement(pmt_inf, "DbtrAgt")
            fin_inst = ET.SubElement(dbtr_agt, "FinInstnId")
            if batch.debtor_bic:
                ET.SubElement(fin_inst, "BIC").text = batch.debtor_bic.upper()
            else:
                # BIC optional bei EU-Inlandsueberweisungen
                other = ET.SubElement(fin_inst, "Othr")
                ET.SubElement(other, "Id").text = "NOTPROVIDED"

            # Charge Bearer
            ET.SubElement(pmt_inf, "ChrgBr").text = batch.charge_bearer.value

            # Credit Transfer Transaction Information
            for tx in batch.transactions:
                cdt_trf = ET.SubElement(pmt_inf, "CdtTrfTxInf")

                # Payment Identification
                pmt_id = ET.SubElement(cdt_trf, "PmtId")
                if tx.instruction_id:
                    ET.SubElement(pmt_id, "InstrId").text = tx.instruction_id
                ET.SubElement(pmt_id, "EndToEndId").text = tx.payment_id

                # Amount
                amt = ET.SubElement(cdt_trf, "Amt")
                inst_amt = ET.SubElement(amt, "InstdAmt")
                inst_amt.text = f"{tx.amount:.2f}"
                inst_amt.set("Ccy", tx.currency)

                # Creditor Agent (Empfaengerbank)
                if tx.creditor_bic:
                    cdtr_agt = ET.SubElement(cdt_trf, "CdtrAgt")
                    fin_inst = ET.SubElement(cdtr_agt, "FinInstnId")
                    ET.SubElement(fin_inst, "BIC").text = tx.creditor_bic.upper()

                # Creditor (Empfaenger)
                cdtr = ET.SubElement(cdt_trf, "Cdtr")
                ET.SubElement(cdtr, "Nm").text = self._sanitize_text(
                    tx.creditor_name, MAX_NAME_LENGTH
                )

                # Creditor Address (optional)
                if tx.creditor_address:
                    pstl_adr = ET.SubElement(cdtr, "PstlAdr")
                    if tx.creditor_address.get("country"):
                        ET.SubElement(pstl_adr, "Ctry").text = tx.creditor_address["country"]
                    if tx.creditor_address.get("street"):
                        ET.SubElement(pstl_adr, "StrtNm").text = tx.creditor_address["street"]
                    if tx.creditor_address.get("city"):
                        ET.SubElement(pstl_adr, "TwnNm").text = tx.creditor_address["city"]
                    if tx.creditor_address.get("postal_code"):
                        ET.SubElement(pstl_adr, "PstCd").text = tx.creditor_address["postal_code"]

                # Creditor Account
                cdtr_acct = ET.SubElement(cdt_trf, "CdtrAcct")
                cdtr_acct_id = ET.SubElement(cdtr_acct, "Id")
                ET.SubElement(cdtr_acct_id, "IBAN").text = tx.creditor_iban.replace(" ", "").upper()

                # Purpose (optional)
                if tx.purpose_code:
                    purp = ET.SubElement(cdt_trf, "Purp")
                    ET.SubElement(purp, "Cd").text = tx.purpose_code

                # Remittance Information
                if tx.remittance_info:
                    rmt_inf = ET.SubElement(cdt_trf, "RmtInf")
                    ET.SubElement(rmt_inf, "Ustrd").text = self._sanitize_text(
                        tx.remittance_info, MAX_REFERENCE_LENGTH
                    )
                elif tx.structured_remittance:
                    # Strukturierte Referenz (z.B. fuer SEPA Creditor Reference)
                    rmt_inf = ET.SubElement(cdt_trf, "RmtInf")
                    strd = ET.SubElement(rmt_inf, "Strd")
                    cdtr_ref = ET.SubElement(strd, "CdtrRefInf")
                    tp = ET.SubElement(cdtr_ref, "Tp")
                    cd_or_prtry = ET.SubElement(tp, "CdOrPrtry")
                    ET.SubElement(cd_or_prtry, "Cd").text = "SCOR"
                    ET.SubElement(cdtr_ref, "Ref").text = tx.structured_remittance.get("ref", "")

        # XML String generieren
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_body = ET.tostring(root, encoding="unicode")

        return xml_declaration + xml_body

    def _sanitize_text(self, text: str, max_length: int) -> str:
        """Bereinige Text fuer SEPA-konformitaet.

        Args:
            text: Eingabetext
            max_length: Maximale Laenge

        Returns:
            Bereinigter Text
        """
        if not text:
            return ""

        # Ersetze ungueltige Zeichen
        sanitized = ""
        for char in text:
            if SEPA_ALLOWED_CHARS.match(char):
                sanitized += char
            elif char in "äöüÄÖÜß":
                # Deutsche Umlaute ersetzen
                replacements = {
                    "ä": "ae", "ö": "oe", "ü": "ue",
                    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
                    "ß": "ss"
                }
                sanitized += replacements.get(char, "")
            elif char in "@#$%^&*=[]{}|\\<>~":
                sanitized += " "  # Ersetze durch Leerzeichen
            # Andere Zeichen werden entfernt

        # Mehrfache Leerzeichen entfernen
        sanitized = " ".join(sanitized.split())

        # Kuerzen
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        return sanitized.strip()

    def validate_pain001_xml(self, xml_content: str) -> List[str]:
        """Validiere pain.001 XML.

        Args:
            xml_content: XML-Inhalt

        Returns:
            Liste von Fehlermeldungen (leer wenn valide)
        """
        errors = []

        try:
            # SECURITY: Use defusedxml to prevent XXE attacks (CWE-611)
            root = DefusedET.fromstring(xml_content)

            # Pruefe Namespace
            if not root.tag.endswith("Document"):
                errors.append("Root-Element muss 'Document' sein")

            # Pruefe Pflichtfelder
            cstmr = root.find(".//{%s}CstmrCdtTrfInitn" % self.NAMESPACE)
            if cstmr is None:
                errors.append("CstmrCdtTrfInitn fehlt")

            # Weitere Validierungen...

        except ET.ParseError as e:
            errors.append(safe_error_detail(e, "XML-Parsing"))

        return errors

    async def get_payment_suggestions(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: UUID,
        include_with_skonto: bool = True,
    ) -> List[Dict[str, Any]]:
        """Holt Zahlungsvorschlaege fuer faellige Rechnungen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Bankkonto-ID
            include_with_skonto: Skonto-Rechnungen einschliessen

        Returns:
            Liste von Zahlungsvorschlaegen
        """
        from app.db.models import Document, BankAccount
        from sqlalchemy import select, and_

        # Pruefe Bankkonto
        account = await db.get(BankAccount, bank_account_id)
        if not account or account.user_id != user_id:
            return []

        # Hole unbezahlte Eingangsrechnungen
        # In Produktion: Echte Query basierend auf Dokumenten-Status
        # Hier: Mock

        suggestions = [
            {
                "document_id": str(uuid4()),
                "invoice_number": "RE-2026-001",
                "creditor_name": "Lieferant A GmbH",
                "creditor_iban": "DE89370400440532013000",
                "amount": Decimal("1234.56"),
                "due_date": date.today() + timedelta(days=5),
                "has_skonto": True,
                "skonto_percent": Decimal("2.0"),
                "skonto_deadline": date.today() + timedelta(days=2),
                "amount_with_skonto": Decimal("1209.87"),
                "priority": "high",
            },
            {
                "document_id": str(uuid4()),
                "invoice_number": "RE-2026-002",
                "creditor_name": "Lieferant B AG",
                "creditor_iban": "DE89370400440532013001",
                "amount": Decimal("567.89"),
                "due_date": date.today() + timedelta(days=14),
                "has_skonto": False,
                "skonto_percent": None,
                "skonto_deadline": None,
                "amount_with_skonto": None,
                "priority": "normal",
            },
        ]

        if not include_with_skonto:
            suggestions = [s for s in suggestions if not s.get("has_skonto")]

        return suggestions


# Singleton-Instanz
sepa_credit_transfer_service = SEPACreditTransferService()
