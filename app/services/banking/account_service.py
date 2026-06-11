"""Bank Account Service.

Verwaltet Bankkonten:
- CRUD-Operationen
- IBAN-Validierung
- Statistik-Aggregation
- Sichere Verschlüsselung von Banking-Credentials
"""

from datetime import datetime, timedelta
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from uuid import UUID, uuid4
import re
import structlog
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    BankAccountType,
    BankAccountCreate,
    BankAccountUpdate,
    BankAccountResponse,
    BankAccountWithStats,
    ReconciliationStatus,
)

if TYPE_CHECKING:
    from app.db.models import BankAccount

logger = structlog.get_logger(__name__)


def _get_encryption_key() -> bytes:
    """Hole den Encryption-Key aus der Konfiguration.

    Der Key wird aus ENCRYPTION_KEY oder SECRET_KEY abgeleitet.

    Returns:
        32-Byte Key für Fernet (URL-safe Base64 encoded)

    Raises:
        ValueError: Wenn kein Key konfiguriert ist
    """
    from app.core.config import settings

    # Versuche zuerst ENCRYPTION_KEY
    if settings.ENCRYPTION_KEY:
        key_value = settings.ENCRYPTION_KEY.get_secret_value()
        # Key muss Base64-encoded sein für Fernet
        try:
            # Prüfe ob bereits valides Fernet-Format (32 Bytes Base64)
            if len(base64.urlsafe_b64decode(key_value)) == 32:
                return key_value.encode()
        except (ValueError, TypeError, UnicodeDecodeError) as e:
            logger.debug("encryption_key_not_valid_fernet_format", error_type=type(e).__name__)
        # Sonst: Derive 32-Byte Key aus dem gegebenen Key
        derived = hashlib.sha256(key_value.encode()).digest()
        return base64.urlsafe_b64encode(derived)

    # Fallback: Derive von SECRET_KEY
    if settings.SECRET_KEY:
        secret = settings.SECRET_KEY.get_secret_value()
        # Derive 32-Byte Key mittels SHA-256
        derived = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(derived)

    raise ValueError(
        "Kein Encryption-Key konfiguriert! "
        "Setze ENCRYPTION_KEY oder SECRET_KEY in der Konfiguration."
    )


def _encrypt_sensitive_data(plaintext: str) -> str:
    """Verschlüsselt sensible Daten mit Fernet (AES-128-CBC).

    Args:
        plaintext: Zu verschlüsselnder Text

    Returns:
        Verschlüsselter Text (Base64-encoded)
    """
    if not plaintext:
        return ""

    key = _get_encryption_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()


def _decrypt_sensitive_data(ciphertext: str) -> Optional[str]:
    """Entschlüsselt sensible Daten.

    Args:
        ciphertext: Verschlüsselter Text

    Returns:
        Entschlüsselter Text oder None bei Fehler
    """
    if not ciphertext:
        return None

    try:
        key = _get_encryption_key()
        fernet = Fernet(key)
        decrypted = fernet.decrypt(ciphertext.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.warning(
            "encryption_decryption_failed",
            error="InvalidToken - Key möglicherweise rotiert"
        )
        return None
    except Exception as e:
        logger.error(
            "encryption_decryption_error",
            **safe_error_log(e)
        )
        return None


class AccountService:
    """Service für Bankkonto-Verwaltung."""

    async def create_account(
        self,
        db: AsyncSession,
        company_id: UUID,
        data: BankAccountCreate,
    ) -> BankAccountResponse:
        """Erstelle neues Bankkonto.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            data: Konto-Daten

        Returns:
            Erstelltes Konto
        """
        from app.db.models import BankAccount

        # IBAN validieren
        if not self.validate_iban(data.iban):
            raise ValueError("Ungültige IBAN")

        # Prüfe ob IBAN bereits existiert
        existing = await db.execute(
            select(BankAccount).where(
                and_(
                    BankAccount.company_id == company_id,
                    BankAccount.iban == data.iban,
                    BankAccount.deleted_at.is_(None),
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Konto mit IBAN {data.iban} existiert bereits")

        # Erstelle Konto
        account = BankAccount(
            id=uuid4(),
            company_id=company_id,
            account_name=data.account_name,
            iban=data.iban,
            bic=data.bic,
            bank_name=data.bank_name or self._get_bank_name_from_iban(data.iban),
            account_holder=data.account_holder,
            account_type=data.account_type.value if data.account_type else BankAccountType.CHECKING.value,
            currency=data.currency,
            blz=data.blz,
            fints_url=data.fints_url,
            is_active=True,
            connection_status="manual",  # Manueller Import als Default
        )

        # Login-ID sicher verschlüsseln (wenn FinTS genutzt wird)
        if data.login_id:
            account.login_id_encrypted = _encrypt_sensitive_data(data.login_id)
            logger.info(
                "banking_login_id_encrypted",
                company_id=str(company_id),
                account_name=data.account_name,
            )

        db.add(account)
        await db.commit()
        await db.refresh(account)

        return self._to_response(account)

    async def get_account(
        self,
        db: AsyncSession,
        company_id: UUID,
        account_id: UUID,
    ) -> Optional[BankAccountResponse]:
        """Hole einzelnes Bankkonto."""
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)

        if not account or account.company_id != company_id or account.deleted_at:
            return None

        return self._to_response(account)

    async def get_accounts(
        self,
        db: AsyncSession,
        company_id: UUID,
        include_inactive: bool = False,
    ) -> List[BankAccountResponse]:
        """Hole alle Bankkonten einer Firma."""
        from app.db.models import BankAccount

        query = select(BankAccount).where(
            and_(
                BankAccount.company_id == company_id,
                BankAccount.deleted_at.is_(None),
            )
        )

        if not include_inactive:
            query = query.where(BankAccount.is_active == True)

        query = query.order_by(BankAccount.account_name)

        result = await db.execute(query)
        accounts = result.scalars().all()

        return [self._to_response(acc) for acc in accounts]

    async def get_total_balance(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Decimal:
        """Summiert den aktuellen Kontostand aller aktiven Konten einer Firma.

        Company-scoped Lesemethode fuer Dashboard-KPIs (W1-010 / TODO G4):
        beruecksichtigt nur aktive, nicht geloeschte Konten; Konten ohne
        gepflegten Saldo (``current_balance IS NULL``) zaehlen als 0.

        Args:
            db: Async-DB-Session.
            company_id: Mandanten-ID (Pflichtfilter, Multi-Tenant).

        Returns:
            Gesamtsaldo als Decimal (0.00 wenn keine Konten existieren).
        """
        from app.db.models import BankAccount

        stmt = select(
            func.coalesce(func.sum(BankAccount.current_balance), 0)
        ).where(
            and_(
                BankAccount.company_id == company_id,
                BankAccount.deleted_at.is_(None),
                BankAccount.is_active == True,  # noqa: E712
            )
        )
        result = await db.execute(stmt)
        total = result.scalar()
        return Decimal(str(total)) if total is not None else Decimal("0.00")

    async def get_accounts_with_stats(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[BankAccountWithStats]:
        """Hole Bankkonten mit Statistiken."""
        from app.db.models import BankAccount, BankTransaction, PaymentOrder

        accounts = await self.get_accounts(db, company_id)

        result = []
        for account in accounts:
            # Transaktions-Statistik
            tx_query = select(
                func.count(BankTransaction.id).label("total"),
                func.count(BankTransaction.id).filter(
                    BankTransaction.reconciliation_status == ReconciliationStatus.UNMATCHED.value
                ).label("unmatched"),
            ).where(BankTransaction.bank_account_id == account.id)

            tx_result = await db.execute(tx_query)
            tx_stats = tx_result.first()

            # Ausstehende Zahlungen
            payment_query = select(
                func.count(PaymentOrder.id).label("count"),
            ).where(
                and_(
                    PaymentOrder.bank_account_id == account.id,
                    PaymentOrder.status.in_(["draft", "pending_approval", "approved"]),
                )
            )
            payment_result = await db.execute(payment_query)
            payment_stats = payment_result.first()

            # Monatliche Ein-/Ausgaben
            month_start = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            monthly_query = select(
                func.sum(BankTransaction.amount).filter(BankTransaction.amount > 0).label("inflow"),
                func.sum(func.abs(BankTransaction.amount)).filter(BankTransaction.amount < 0).label("outflow"),
            ).where(
                and_(
                    BankTransaction.bank_account_id == account.id,
                    BankTransaction.booking_date >= month_start.date(),
                )
            )
            monthly_result = await db.execute(monthly_query)
            monthly_stats = monthly_result.first()

            result.append(BankAccountWithStats(
                **account.model_dump(),
                transaction_count=tx_stats.total or 0,
                unmatched_count=tx_stats.unmatched or 0,
                pending_payments_count=payment_stats.count or 0,
                total_in_this_month=Decimal(str(monthly_stats.inflow or 0)),
                total_out_this_month=Decimal(str(monthly_stats.outflow or 0)),
            ))

        return result

    async def update_account(
        self,
        db: AsyncSession,
        company_id: UUID,
        account_id: UUID,
        data: BankAccountUpdate,
    ) -> Optional[BankAccountResponse]:
        """Aktualisiere Bankkonto."""
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)

        if not account or account.company_id != company_id or account.deleted_at:
            return None

        # Update-Felder
        if data.account_name is not None:
            account.account_name = data.account_name
        if data.bank_name is not None:
            account.bank_name = data.bank_name
        if data.account_holder is not None:
            account.account_holder = data.account_holder
        if data.account_type is not None:
            account.account_type = data.account_type.value
        if data.is_active is not None:
            account.is_active = data.is_active
        if data.auto_sync_enabled is not None:
            account.auto_sync_enabled = data.auto_sync_enabled
        if data.sync_interval_hours is not None:
            account.sync_interval_hours = data.sync_interval_hours

        account.updated_at = utc_now()

        await db.commit()
        await db.refresh(account)

        return self._to_response(account)

    async def delete_account(
        self,
        db: AsyncSession,
        company_id: UUID,
        account_id: UUID,
    ) -> bool:
        """Lösche Bankkonto (Soft-Delete)."""
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)

        if not account or account.company_id != company_id or account.deleted_at:
            return False

        account.deleted_at = utc_now()
        account.is_active = False

        await db.commit()

        return True

    async def update_balance(
        self,
        db: AsyncSession,
        account_id: UUID,
        balance: Decimal,
        balance_date: Optional[datetime] = None,
    ) -> None:
        """Aktualisiere Kontostand."""
        from app.db.models import BankAccount

        account = await db.get(BankAccount, account_id)
        if account:
            account.current_balance = balance
            account.balance_date = balance_date or utc_now()
            await db.commit()

    def validate_iban(self, iban: str) -> bool:
        """Validiere IBAN mit MOD-97 Prüfung.

        Args:
            iban: IBAN zu validieren

        Returns:
            True wenn gültig
        """
        # Normalisieren
        iban = iban.replace(" ", "").upper()

        # Längen-Check (15-34 Zeichen)
        if len(iban) < 15 or len(iban) > 34:
            return False

        # Format-Check: 2 Buchstaben + 2 Ziffern + alphanumerisch
        if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]+$", iban):
            return False

        # MOD-97 Prüfung
        # Verschiebe erste 4 Zeichen ans Ende
        rearranged = iban[4:] + iban[:4]

        # Konvertiere Buchstaben zu Zahlen (A=10, B=11, ...)
        numeric = ""
        for char in rearranged:
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - ord("A") + 10)

        # MOD 97 muss 1 ergeben
        try:
            return int(numeric) % 97 == 1
        except ValueError:
            return False

    def _get_bank_name_from_iban(self, iban: str) -> Optional[str]:
        """Ermittle Bankname aus IBAN (BLZ-basiert für DE)."""
        iban = iban.replace(" ", "").upper()

        if not iban.startswith("DE"):
            return None

        # BLZ ist Position 5-12 bei deutschen IBANs
        blz = iban[4:12]

        # Bekannte BLZ-Bereiche
        bank_prefixes = {
            "100": "Bundesbank",
            "200": "Hamburg",
            "300": "Duesseldorf",
            "370": "Koeln",
            "500": "Frankfurt",
            "700": "Muenchen",
            "760": "Nuernberg",
        }

        prefix = blz[:3]
        region = bank_prefixes.get(prefix)

        if region:
            return f"Bank ({region})"

        return None

    async def get_decrypted_login_id(
        self,
        db: AsyncSession,
        company_id: UUID,
        account_id: UUID,
    ) -> Optional[str]:
        """Hole entschlüsselte Login-ID für FinTS-Verbindungen.

        SECURITY: Diese Methode sollte nur für tatsaechliche
        FinTS-Verbindungen verwendet werden, nie für API-Responses!

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (für Authorization-Check)
            account_id: Konto-ID

        Returns:
            Entschlüsselte Login-ID oder None
        """
        from app.db.models import BankAccount


        account = await db.get(BankAccount, account_id)

        # Authorization Check
        if not account or account.company_id != company_id or account.deleted_at:
            logger.warning(
                "banking_login_id_access_denied",
                company_id=str(company_id),
                account_id=str(account_id),
            )
            return None

        if not account.login_id_encrypted:
            return None

        decrypted = _decrypt_sensitive_data(account.login_id_encrypted)

        if decrypted:
            logger.info(
                "banking_login_id_decrypted",
                company_id=str(company_id),
                account_id=str(account_id),
                purpose="fints_connection",
            )

        return decrypted

    def _to_response(self, account: "BankAccount") -> BankAccountResponse:
        """Konvertiere DB-Model zu Response."""
        return BankAccountResponse(
            id=account.id,
            user_id=account.user_id,
            company_id=account.company_id,
            account_name=account.account_name,
            iban=account.iban,
            bic=account.bic,
            bank_name=account.bank_name,
            account_holder=account.account_holder,
            account_type=BankAccountType(account.account_type) if account.account_type else BankAccountType.CHECKING,
            currency=account.currency or "EUR",
            is_active=account.is_active,
            connection_status=account.connection_status or "manual",
            current_balance=account.current_balance,
            balance_date=account.balance_date,
            last_sync_at=account.last_sync_at,
            auto_sync_enabled=account.auto_sync_enabled or False,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )
