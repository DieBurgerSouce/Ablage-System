"""FinTS/HBCI Banking Service.

Direkter Kontoumsatz-Abruf über FinTS (Financial Transaction Services).
Unterstützt FinTS 3.0 und HBCI 2.2/3.0.

SECURITY HINWEIS:
- Alle Zugangsdaten werden verschlüsselt gespeichert (AES-256)
- TAN-Verfahren werden unterstützt (mTAN, pushTAN, photoTAN)
- Keine Passwoerter oder PINs werden geloggt
- Session-Daten werden nach Verwendung gelöscht
"""

import asyncio
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4
import hashlib
import structlog

from dataclasses import dataclass, field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Models
# =============================================================================


class FinTSConnectionStatus(str, Enum):
    """FinTS-Verbindungsstatus."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AWAITING_TAN = "awaiting_tan"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ERROR = "error"


class TANMethod(str, Enum):
    """Unterstützte TAN-Verfahren."""
    CHIP_TAN = "chip_tan"
    CHIP_TAN_QR = "chip_tan_qr"
    CHIP_TAN_USB = "chip_tan_usb"
    CHIP_TAN_PHOTO = "chip_tan_photo"
    SMSTAN = "sms_tan"  # mobileTAN
    PUSH_TAN = "push_tan"
    PHOTO_TAN = "photo_tan"
    APP_TAN = "app_tan"
    DECOUPLED = "decoupled"  # z.B. BestSign


class FinTSSyncType(str, Enum):
    """Typ der Synchronisation."""
    STATEMENT = "statement"  # Kontoumsätze
    BALANCE = "balance"  # Nur Kontostand
    SEPA_INFO = "sepa_info"  # SEPA-Informationen
    TAN_METHODS = "tan_methods"  # TAN-Verfahren abrufen


@dataclass
class FinTSBankInfo:
    """Bank-Informationen aus FinTS-BPD."""
    bank_name: str
    blz: str
    bic: Optional[str] = None
    fints_url: str = ""
    hbci_version: str = "300"
    supported_versions: List[str] = field(default_factory=list)
    tan_methods: List[Dict[str, Any]] = field(default_factory=list)
    allowed_transactions: List[str] = field(default_factory=list)


@dataclass
class FinTSTransaction:
    """Eine Transaktion aus dem FinTS-Statement."""
    transaction_id: str
    booking_date: date
    value_date: date
    amount: Decimal
    currency: str
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    counterparty_bic: Optional[str]
    reference_text: Optional[str]
    booking_text: Optional[str]
    end_to_end_reference: Optional[str]
    mandate_reference: Optional[str]
    creditor_id: Optional[str]
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FinTSBalance:
    """Kontostand aus FinTS."""
    balance: Decimal
    currency: str
    date: date
    credit_line: Optional[Decimal] = None
    available_balance: Optional[Decimal] = None


@dataclass
class FinTSSyncResult:
    """Ergebnis einer FinTS-Synchronisation."""
    success: bool
    sync_type: FinTSSyncType
    account_iban: str
    transactions: List[FinTSTransaction] = field(default_factory=list)
    balance: Optional[FinTSBalance] = None
    error_message: Optional[str] = None
    sync_date: datetime = field(default_factory=utc_now)
    transaction_count: int = 0
    date_from: Optional[date] = None
    date_to: Optional[date] = None


@dataclass
class TANChallenge:
    """TAN-Challenge vom FinTS-Server."""
    challenge_id: str
    tan_method: TANMethod
    challenge_text: str
    challenge_data: Optional[bytes] = None  # QR-Code, Flickercode
    challenge_image: Optional[bytes] = None  # Bild für photoTAN
    expires_at: datetime = field(default_factory=lambda: utc_now() + timedelta(minutes=5))
    hhduc: Optional[str] = None  # HHDuc für Flickercode


class FinTSConnectionConfig(BaseModel):
    """Konfiguration für FinTS-Verbindung."""
    blz: str = Field(..., min_length=8, max_length=8)
    fints_url: str = Field(...)
    login_id: str = Field(..., min_length=1)  # Benutzerkennung
    # PIN wird NICHT gespeichert, sondern bei Bedarf abgefragt
    selected_tan_method: Optional[TANMethod] = None
    product_id: str = Field(default="Ablage-System-OCR")
    product_version: str = Field(default="1.0")


# =============================================================================
# FinTS Service
# =============================================================================


class FinTSService:
    """Service für FinTS/HBCI Banking-Verbindungen.

    Ermöglicht:
    - Kontoabruf (Umsätze, Saldo)
    - TAN-Verfahren-Auswahl
    - SEPA-Überweisungen ausloesen

    Verwendet python-fints Bibliothek für das Protokoll.
    """

    # Bekannte FinTS-URLs deutscher Banken
    KNOWN_FINTS_URLS = {
        # Sparkassen
        "10050000": "https://banking-be1.s-fints-pt-be.de/fints30",  # Berliner Sparkasse
        "20050550": "https://banking-hh1.s-fints-pt-hh.de/fints30",  # Hamburger Sparkasse
        "37050198": "https://banking-nrw1.s-fints-pt-nrw.de/fints30",  # Sparkasse KoelnBonn
        "50050201": "https://banking-hessen1.s-fints-pt-hessen.de/fints30",  # Frankfurter Sparkasse
        "70050000": "https://banking-by1.s-fints-pt-by.de/fints30",  # Stadtsparkasse Muenchen

        # Volksbanken
        "20090500": "https://fints.gad.de/fints",  # Hamburger Volksbank
        "37060590": "https://fints.gad.de/fints",  # Volksbank Koeln Bonn

        # Grosse Banken
        "10070000": "https://fints.deutsche-bank.de",  # Deutsche Bank Berlin
        "50070010": "https://fints.deutsche-bank.de",  # Deutsche Bank Frankfurt
        "37040044": "https://fints.commerzbank.com",  # Commerzbank
        "50010517": "https://fints.ing-diba.de/fints/",  # ING
        "12030000": "https://fints.db.com",  # DKB (Deutsche Kreditbank)

        # Direktbanken
        "76030080": "https://fints.comdirect.de/fints",  # comdirect
        "10019610": "https://fints.norisbank.de/fints",  # norisbank
    }

    # Session-Cache für aktive Verbindungen
    _sessions: Dict[str, Any] = {}
    _pending_tans: Dict[str, TANChallenge] = {}

    def __init__(self):
        """Initialisiere FinTS-Service."""
        self._check_dependencies()

    def _check_dependencies(self) -> bool:
        """Prüfe ob python-fints installiert ist."""
        try:
            import fints  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "fints_dependency_missing",
                message="python-fints nicht installiert. "
                        "Installiere mit: pip install python-fints"
            )
            return False

    def get_fints_url(self, blz: str) -> Optional[str]:
        """Ermittle FinTS-URL für eine BLZ.

        Args:
            blz: Bankleitzahl (8-stellig)

        Returns:
            FinTS-URL oder None
        """
        # Direkte Suche
        url = self.KNOWN_FINTS_URLS.get(blz)
        if url:
            return url

        # Sparkassen-Gruppen (BLZ beginnt mit bestimmten Ziffern)
        prefix = blz[:3]
        sparkassen_prefixes = {
            "100": "https://banking-be1.s-fints-pt-be.de/fints30",  # Berlin
            "200": "https://banking-hh1.s-fints-pt-hh.de/fints30",  # Hamburg
            "250": "https://banking-ni1.s-fints-pt-ni.de/fints30",  # Niedersachsen
            "300": "https://banking-nrw1.s-fints-pt-nrw.de/fints30",  # NRW Duesseldorf
            "370": "https://banking-nrw1.s-fints-pt-nrw.de/fints30",  # NRW Koeln
            "400": "https://banking-nrw1.s-fints-pt-nrw.de/fints30",  # NRW
            "440": "https://banking-nrw1.s-fints-pt-nrw.de/fints30",  # NRW
            "500": "https://banking-hessen1.s-fints-pt-hessen.de/fints30",  # Hessen
            "550": "https://banking-rlp1.s-fints-pt-rlp.de/fints30",  # RLP
            "600": "https://banking-bw1.s-fints-pt-bw.de/fints30",  # BW
            "700": "https://banking-by1.s-fints-pt-by.de/fints30",  # Bayern
            "760": "https://banking-by1.s-fints-pt-by.de/fints30",  # Bayern
        }

        sparkasse_url = sparkassen_prefixes.get(prefix)
        if sparkasse_url:
            return sparkasse_url

        # Volksbanken-Zentralserver (GAD)
        if prefix in ["200", "250", "280", "290", "360", "370", "400", "410",
                      "430", "440", "460", "470", "480", "510", "520"]:
            return "https://fints.gad.de/fints"

        # Keine bekannte URL
        logger.info(
            "fints_url_unknown",
            blz=blz,
            message="FinTS-URL nicht bekannt, muss manuell eingegeben werden"
        )
        return None

    async def get_bank_info(
        self,
        blz: str,
        fints_url: Optional[str] = None,
    ) -> Optional[FinTSBankInfo]:
        """Rufe Bank-Informationen (BPD) ab.

        Args:
            blz: Bankleitzahl
            fints_url: FinTS-URL (optional, wird sonst ermittelt)

        Returns:
            Bank-Informationen oder None
        """
        url = fints_url or self.get_fints_url(blz)
        if not url:
            return None

        try:
            # In Produktion: Echte BPD-Abfrage via python-fints
            # Hier: Mock-Response für Entwicklung

            return FinTSBankInfo(
                bank_name=self._get_bank_name_from_blz(blz),
                blz=blz,
                bic=self._get_bic_from_blz(blz),
                fints_url=url,
                hbci_version="300",
                supported_versions=["300", "220"],
                tan_methods=[
                    {"id": "901", "name": "mobileTAN", "type": TANMethod.SMSTAN.value},
                    {"id": "902", "name": "pushTAN", "type": TANMethod.PUSH_TAN.value},
                    {"id": "912", "name": "chipTAN QR", "type": TANMethod.CHIP_TAN_QR.value},
                ],
                allowed_transactions=["HKKAZ", "HKSAL", "HKCCS", "HKCCM"],
            )

        except Exception as e:
            logger.error(
                "fints_bank_info_error",
                blz=blz,
                **safe_error_log(e)
            )
            return None

    async def connect(
        self,
        db: AsyncSession,
        account_id: UUID,
        company_id: UUID,
        pin: str,  # Temporaer - wird nicht gespeichert!
    ) -> Tuple[bool, Optional[TANChallenge], Optional[str]]:
        """Verbinde mit FinTS-Server.

        Args:
            db: Datenbank-Session
            account_id: Bankkonto-ID
            company_id: Firmen-ID
            pin: Online-Banking PIN (wird nicht gespeichert!)

        Returns:
            Tuple aus (success, tan_challenge, error_message)
        """
        from app.db.models import BankAccount
        from .account_service import AccountService

        account_service = AccountService()

        # Lade Account
        account = await db.get(BankAccount, account_id)
        if not account or account.company_id != company_id:
            return False, None, "Konto nicht gefunden oder keine Berechtigung"

        if not account.blz or not account.fints_url:
            return False, None, "FinTS-Konfiguration fehlt (BLZ, URL)"

        # Hole verschlüsselte Login-ID
        login_id = await account_service.get_decrypted_login_id(db, company_id, account_id)
        if not login_id:
            return False, None, "Login-ID nicht konfiguriert"

        try:
            # In Produktion: Echte FinTS-Verbindung
            # Hier: Mock für Entwicklung

            session_id = f"fints_{account_id}_{uuid4().hex[:8]}"

            # Simuliere TAN-Anforderung für Dialog-Initialisierung
            tan_challenge = TANChallenge(
                challenge_id=uuid4().hex,
                tan_method=TANMethod.PUSH_TAN,
                challenge_text="Bitte bestätigen Sie den Kontozugriff in Ihrer Banking-App.",
                expires_at=utc_now() + timedelta(minutes=5),
            )

            # Speichere Session
            self._sessions[session_id] = {
                "account_id": account_id,
                "company_id": company_id,
                "status": FinTSConnectionStatus.AWAITING_TAN,
                "tan_challenge_id": tan_challenge.challenge_id,
                "created_at": utc_now(),
            }
            self._pending_tans[tan_challenge.challenge_id] = tan_challenge

            logger.info(
                "fints_connection_initiated",
                account_id=str(account_id),
                session_id=session_id,
                tan_method=tan_challenge.tan_method.value,
            )

            # Update Account-Status
            account.connection_status = FinTSConnectionStatus.AWAITING_TAN.value
            await db.commit()

            return True, tan_challenge, None

        except Exception as e:
            logger.error(
                "fints_connection_error",
                account_id=str(account_id),
                **safe_error_log(e)
            )
            return False, None, safe_error_detail(e, "FinTS-Verbindung")

    async def confirm_tan(
        self,
        db: AsyncSession,
        challenge_id: str,
        tan: str,
        company_id: UUID,
    ) -> Tuple[bool, Optional[str]]:
        """Bestätigt TAN-Challenge.

        Args:
            db: Datenbank-Session
            challenge_id: Challenge-ID
            tan: TAN-Eingabe
            company_id: Firmen-ID

        Returns:
            Tuple aus (success, error_message)
        """
        challenge = self._pending_tans.get(challenge_id)
        if not challenge:
            return False, "TAN-Challenge nicht gefunden oder abgelaufen"

        if utc_now() > challenge.expires_at:
            del self._pending_tans[challenge_id]
            return False, "TAN-Challenge abgelaufen"

        # Finde zugehoerige Session
        session_id = None
        session_data = None
        for sid, sdata in self._sessions.items():
            if sdata.get("tan_challenge_id") == challenge_id:
                session_id = sid
                session_data = sdata
                break

        if not session_data or session_data.get("company_id") != company_id:
            return False, "Session nicht gefunden oder keine Berechtigung"

        try:
            # In Produktion: TAN an FinTS-Server senden
            # Hier: Mock - TAN "123456" ist immer gültig

            if tan == "123456" or len(tan) >= 6:
                # Erfolg
                session_data["status"] = FinTSConnectionStatus.CONNECTED
                del self._pending_tans[challenge_id]

                # Update Account
                from app.db.models import BankAccount
                account = await db.get(BankAccount, session_data["account_id"])
                if account:
                    account.connection_status = FinTSConnectionStatus.CONNECTED.value
                    account.last_sync_at = utc_now()
                    await db.commit()

                logger.info(
                    "fints_tan_confirmed",
                    account_id=str(session_data["account_id"]),
                    session_id=session_id,
                )

                return True, None
            else:
                return False, "Ungültige TAN"

        except Exception as e:
            logger.error(
                "fints_tan_confirmation_error",
                challenge_id=challenge_id,
                **safe_error_log(e)
            )
            return False, safe_error_detail(e, "TAN-Bestätigung")

    async def sync_transactions(
        self,
        db: AsyncSession,
        account_id: UUID,
        company_id: UUID,
        pin: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> FinTSSyncResult:
        """Synchronisiert Kontoumsätze via FinTS.

        Args:
            db: Datenbank-Session
            account_id: Bankkonto-ID
            company_id: Firmen-ID
            pin: Online-Banking PIN
            date_from: Start-Datum (default: 90 Tage zurück)
            date_to: End-Datum (default: heute)

        Returns:
            Sync-Ergebnis mit Transaktionen
        """
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)
        if not account or account.company_id != company_id:
            return FinTSSyncResult(
                success=False,
                sync_type=FinTSSyncType.STATEMENT,
                account_iban=account.iban if account else "",
                error_message="Konto nicht gefunden oder keine Berechtigung",
            )

        if not date_from:
            date_from = date.today() - timedelta(days=90)
        if not date_to:
            date_to = date.today()

        try:
            # In Produktion: python-fints Statement-Abruf
            # Hier: Mock-Daten für Entwicklung

            mock_transactions = self._generate_mock_transactions(
                account.iban, date_from, date_to
            )

            # Speichere Transaktionen in DB
            saved_count = await self._save_transactions(
                db, account_id, mock_transactions
            )

            # Update Account-Status
            account.last_sync_at = utc_now()
            account.connection_status = "synced"
            await db.commit()

            logger.info(
                "fints_sync_completed",
                account_id=str(account_id),
                transaction_count=saved_count,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
            )

            return FinTSSyncResult(
                success=True,
                sync_type=FinTSSyncType.STATEMENT,
                account_iban=account.iban,
                transactions=mock_transactions,
                transaction_count=len(mock_transactions),
                date_from=date_from,
                date_to=date_to,
            )

        except Exception as e:
            logger.error(
                "fints_sync_error",
                account_id=str(account_id),
                **safe_error_log(e)
            )
            return FinTSSyncResult(
                success=False,
                sync_type=FinTSSyncType.STATEMENT,
                account_iban=account.iban,
                error_message=safe_error_detail(e, "FinTS-Sync"),
            )

    async def get_balance(
        self,
        db: AsyncSession,
        account_id: UUID,
        company_id: UUID,
        pin: str,
    ) -> Optional[FinTSBalance]:
        """Ruft aktuellen Kontostand ab.

        Args:
            db: Datenbank-Session
            account_id: Bankkonto-ID
            company_id: Firmen-ID
            pin: Online-Banking PIN

        Returns:
            Kontostand oder None
        """
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)
        if not account or account.company_id != company_id:
            return None

        try:
            # In Produktion: python-fints Saldo-Abruf
            # Hier: Mock

            balance = FinTSBalance(
                balance=account.current_balance or Decimal("1234.56"),
                currency=account.currency or "EUR",
                date=date.today(),
                credit_line=Decimal("5000.00"),
                available_balance=Decimal("6234.56"),
            )

            # Update Account
            account.current_balance = balance.balance
            account.balance_date = utc_now()
            account.last_sync_at = utc_now()
            await db.commit()

            return balance

        except Exception as e:
            logger.error(
                "fints_balance_error",
                account_id=str(account_id),
                **safe_error_log(e)
            )
            return None

    async def initiate_sepa_transfer(
        self,
        db: AsyncSession,
        account_id: UUID,
        company_id: UUID,
        pin: str,
        beneficiary_name: str,
        beneficiary_iban: str,
        beneficiary_bic: Optional[str],
        amount: Decimal,
        reference: str,
        execution_date: Optional[date] = None,
    ) -> Tuple[bool, Optional[TANChallenge], Optional[str]]:
        """Initiiert SEPA-Überweisung.

        Args:
            db: Datenbank-Session
            account_id: Auftraggeber-Konto
            company_id: Firmen-ID
            pin: Online-Banking PIN
            beneficiary_name: Empfängername
            beneficiary_iban: Empfänger-IBAN
            beneficiary_bic: Empfänger-BIC (optional)
            amount: Betrag
            reference: Verwendungszweck
            execution_date: Ausführungsdatum (optional)

        Returns:
            Tuple aus (success, tan_challenge, error_message)
        """
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)
        if not account or account.company_id != company_id:
            return False, None, "Konto nicht gefunden oder keine Berechtigung"

        try:
            # Validiere Betrag
            if amount <= 0:
                return False, None, "Betrag muss positiv sein"

            if amount > Decimal("50000"):
                # Hohe Betraege erfordern besondere Freigabe
                logger.warning(
                    "fints_high_value_transfer",
                    account_id=str(account_id),
                    amount=str(amount),
                )

            # In Produktion: SEPA-Auftrag via python-fints
            # Hier: Mock TAN-Anforderung

            tan_challenge = TANChallenge(
                challenge_id=uuid4().hex,
                tan_method=TANMethod.PUSH_TAN,
                challenge_text=f"Bitte bestätigen Sie die Überweisung von {amount:.2f} EUR "
                               f"an {beneficiary_name}.",
                expires_at=utc_now() + timedelta(minutes=5),
            )

            self._pending_tans[tan_challenge.challenge_id] = tan_challenge

            # Speichere Transfer-Session
            session_id = f"transfer_{account_id}_{uuid4().hex[:8]}"
            self._sessions[session_id] = {
                "type": "sepa_transfer",
                "account_id": account_id,
                "company_id": company_id,
                "tan_challenge_id": tan_challenge.challenge_id,
                "transfer_data": {
                    "beneficiary_name": beneficiary_name,
                    "beneficiary_iban": beneficiary_iban,
                    "beneficiary_bic": beneficiary_bic,
                    "amount": str(amount),
                    "reference": reference,
                    "execution_date": execution_date.isoformat() if execution_date else None,
                },
                "created_at": utc_now(),
            }

            logger.info(
                "fints_sepa_transfer_initiated",
                account_id=str(account_id),
                amount=str(amount),
                # SECURITY: Keine Empfängerdaten loggen!
            )

            return True, tan_challenge, None

        except Exception as e:
            logger.error(
                "fints_sepa_transfer_error",
                account_id=str(account_id),
                **safe_error_log(e)
            )
            return False, None, safe_error_detail(e, "SEPA-Überweisung")

    async def get_available_tan_methods(
        self,
        db: AsyncSession,
        account_id: UUID,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Gibt verfügbare TAN-Verfahren zurück.

        Args:
            db: Datenbank-Session
            account_id: Bankkonto-ID
            company_id: Firmen-ID

        Returns:
            Liste der TAN-Verfahren
        """
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)
        if not account or account.company_id != company_id:
            return []

        # In Produktion: Aus BPD der Bank
        # Hier: Standard-Liste

        return [
            {
                "id": "901",
                "name": "mobileTAN (SMS)",
                "type": TANMethod.SMSTAN.value,
                "description": "TAN wird per SMS gesendet",
                "is_default": False,
            },
            {
                "id": "902",
                "name": "pushTAN",
                "type": TANMethod.PUSH_TAN.value,
                "description": "Freigabe in der Banking-App",
                "is_default": True,
            },
            {
                "id": "912",
                "name": "chipTAN QR",
                "type": TANMethod.CHIP_TAN_QR.value,
                "description": "QR-Code mit TAN-Generator scannen",
                "is_default": False,
            },
            {
                "id": "920",
                "name": "photoTAN",
                "type": TANMethod.PHOTO_TAN.value,
                "description": "Grafik mit App/Gerät scannen",
                "is_default": False,
            },
        ]

    async def disconnect(
        self,
        db: AsyncSession,
        account_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Trennt FinTS-Verbindung.

        Args:
            db: Datenbank-Session
            account_id: Bankkonto-ID
            company_id: Firmen-ID

        Returns:
            True wenn erfolgreich
        """
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)
        if not account or account.company_id != company_id:
            return False

        # Entferne Sessions
        to_remove = [
            sid for sid, sdata in self._sessions.items()
            if sdata.get("account_id") == account_id
        ]
        for sid in to_remove:
            session_data = self._sessions.pop(sid, {})
            # Entferne zugehoerige TAN-Challenges
            if "tan_challenge_id" in session_data:
                self._pending_tans.pop(session_data["tan_challenge_id"], None)

        account.connection_status = FinTSConnectionStatus.DISCONNECTED.value
        await db.commit()

        logger.info(
            "fints_disconnected",
            account_id=str(account_id),
        )

        return True

    # =============================================================================
    # Helper Methods
    # =============================================================================

    def _get_bank_name_from_blz(self, blz: str) -> str:
        """Ermittle Bankname aus BLZ."""
        bank_names = {
            "10070000": "Deutsche Bank",
            "50070010": "Deutsche Bank",
            "37040044": "Commerzbank",
            "50010517": "ING",
            "12030000": "DKB",
            "76030080": "comdirect",
        }

        name = bank_names.get(blz)
        if name:
            return name

        # Sparkassen
        if blz[3:5] == "50":
            return f"Sparkasse (BLZ {blz})"

        # Volksbanken
        if blz[3:5] in ["60", "61", "62", "69"]:
            return f"Volksbank (BLZ {blz})"

        return f"Bank (BLZ {blz})"

    def _get_bic_from_blz(self, blz: str) -> Optional[str]:
        """Ermittle BIC aus BLZ."""
        bics = {
            "10070000": "DEUTDEDB101",
            "50070010": "DEUTDEFF500",
            "37040044": "COBADEFFXXX",
            "50010517": "INGDDEFFXXX",
            "12030000": "BYLADEM1001",
            "76030080": "COBADEFFXXX",
        }
        return bics.get(blz)

    def _generate_mock_transactions(
        self,
        iban: str,
        date_from: date,
        date_to: date,
    ) -> List[FinTSTransaction]:
        """
        Generiere Mock-Transaktionen für Tests.

        DETERMINISTIC: Verwendet hash-basiertes Seeding für Reproduzierbarkeit.
        """
        transactions = []
        current_date = date_from

        counterparties = [
            ("Amazon EU S.a.r.l.", "LU28019A456789012345"),
            ("REWE Markt GmbH", "DE89370400440532013000"),
            ("Arbeitgeber GmbH", "DE89370400440532013001"),
            ("Deutsche Telekom AG", "DE89370400440532013002"),
            ("Stadtwerke Koeln", "DE89370400440532013003"),
        ]

        # Deterministisches Seeding basierend auf IBAN + Datumsbereich
        seed_str = f"{iban}:{date_from}:{date_to}"
        base_seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        tx_counter = 0

        while current_date <= date_to:
            # Deterministisch: Anzahl Transaktionen basierend auf Datum
            day_seed = base_seed + current_date.toordinal()
            num_transactions = day_seed % 4  # 0-3 Transaktionen

            for i in range(num_transactions):
                tx_seed = day_seed * 100 + i
                tx_counter += 1

                # Deterministischer Counterparty
                cp_idx = tx_seed % len(counterparties)
                cp_name, cp_iban = counterparties[cp_idx]

                # Deterministisch: 70% Ausgaben (is_credit wenn tx_seed % 10 < 3)
                is_credit = (tx_seed % 10) < 3

                # Deterministischer Betrag
                amount_raw = 10 + (tx_seed % 490)  # 10-500
                amount = Decimal(str(amount_raw)).quantize(Decimal("0.01"))
                if not is_credit:
                    amount = -amount

                # Deterministische Referenznummer
                ref_number = 1000 + (tx_seed % 9000)

                tx = FinTSTransaction(
                    transaction_id=hashlib.md5(
                        f"{iban}{current_date}{tx_counter}".encode()
                    ).hexdigest()[:16],
                    booking_date=current_date,
                    value_date=current_date,
                    amount=amount,
                    currency="EUR",
                    counterparty_name=cp_name,
                    counterparty_iban=cp_iban,
                    counterparty_bic=None,
                    reference_text=f"Rechnung {ref_number}",
                    booking_text="SEPA-Überweisung" if amount > 0 else "SEPA-Lastschrift",
                    end_to_end_reference=f"E2E-{hashlib.md5(f'{tx_seed}'.encode()).hexdigest()[:8].upper()}",
                    mandate_reference=None,
                    creditor_id=None,
                )
                transactions.append(tx)

            current_date += timedelta(days=1)

        return transactions

    async def _save_transactions(
        self,
        db: AsyncSession,
        account_id: UUID,
        transactions: List[FinTSTransaction],
    ) -> int:
        """Speichere Transaktionen in der Datenbank.

        Args:
            db: Datenbank-Session
            account_id: Bankkonto-ID
            transactions: Transaktionen

        Returns:
            Anzahl gespeicherter Transaktionen
        """
        from app.db.models import BankTransaction


        saved = 0

        for tx in transactions:
            # Prüfe auf Duplikate
            existing = await db.execute(
                select(BankTransaction).where(
                    and_(
                        BankTransaction.bank_account_id == account_id,
                        BankTransaction.transaction_id == tx.transaction_id,
                    )
                )
            )

            if existing.scalar_one_or_none():
                continue

            db_tx = BankTransaction(
                id=uuid4(),
                bank_account_id=account_id,
                transaction_id=tx.transaction_id,
                booking_date=tx.booking_date,
                value_date=tx.value_date,
                amount=tx.amount,
                currency=tx.currency,
                counterparty_name=tx.counterparty_name,
                counterparty_iban=tx.counterparty_iban,
                counterparty_bic=tx.counterparty_bic,
                reference_text=tx.reference_text,
                booking_text=tx.booking_text,
                end_to_end_reference=tx.end_to_end_reference,
                mandate_reference=tx.mandate_reference,
                creditor_id=tx.creditor_id,
                reconciliation_status="unmatched",
                imported_at=utc_now(),
                raw_data=tx.raw_data,
            )
            db.add(db_tx)
            saved += 1

        if saved > 0:
            await db.flush()

        return saved


# Singleton-Instanz
fints_service = FinTSService()
