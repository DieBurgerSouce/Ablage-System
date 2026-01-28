# -*- coding: utf-8 -*-
"""
Enhanced FinTS Service - Erweiterte Banking-Integration.

Vision 2026 Q4: Vollautomatische Banking-Anbindung.

Erweiterungen:
- Automatischer taeglicher Kontoauszug-Abruf
- Multi-Bank-Support mit vereinheitlichter Schnittstelle
- Push-Benachrichtigung bei Zahlungseingang
- Auto-Reconciliation mit offenen Rechnungen
- Connection Health Monitoring
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Callable, TypedDict
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram, Gauge

from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

BANK_SYNC_TOTAL = Counter(
    "fints_sync_total",
    "Total bank synchronizations",
    ["company_id", "bank_name", "status"]
)

BANK_SYNC_DURATION = Histogram(
    "fints_sync_duration_seconds",
    "Bank sync duration",
    ["company_id"]
)

RECONCILED_TRANSACTIONS = Counter(
    "fints_reconciled_transactions_total",
    "Auto-reconciled transactions",
    ["company_id", "reconciliation_type"]
)

PAYMENT_NOTIFICATIONS = Counter(
    "fints_payment_notifications_total",
    "Payment notifications sent",
    ["company_id", "channel"]
)

BANK_CONNECTION_HEALTH = Gauge(
    "fints_connection_health",
    "Bank connection health status (1=healthy, 0=unhealthy)",
    ["company_id", "bank_id"]
)


# =============================================================================
# Enums
# =============================================================================

class ReconciliationType(str, Enum):
    """Typ der Reconciliation."""
    EXACT_MATCH = "exact_match"           # IBAN + Betrag exakt
    REFERENCE_MATCH = "reference_match"   # Referenznummer gefunden
    AMOUNT_MATCH = "amount_match"         # Nur Betrag (mit Toleranz)
    SKONTO_MATCH = "skonto_match"         # Betrag mit Skonto-Abzug
    PARTIAL_MATCH = "partial_match"       # Teilzahlung erkannt
    MANUAL = "manual"                     # Manuell zugeordnet


class NotificationChannel(str, Enum):
    """Benachrichtigungskanal."""
    EMAIL = "email"
    PUSH = "push"
    SLACK = "slack"
    IN_APP = "in_app"


class SyncSchedule(str, Enum):
    """Sync-Zeitplan."""
    REALTIME = "realtime"     # Sofort (wenn moeglich)
    HOURLY = "hourly"         # Stuendlich
    DAILY = "daily"           # Taeglich
    MANUAL = "manual"         # Nur manuell


class ConnectionHealth(str, Enum):
    """Verbindungsstatus."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"     # Verbindungsprobleme
    UNHEALTHY = "unhealthy"   # Keine Verbindung
    EXPIRED = "expired"       # Credentials abgelaufen


# =============================================================================
# TypedDicts for Type Safety
# =============================================================================


class TransactionData(TypedDict):
    """Typisierte Transaktionsdaten fuer Type Safety."""
    id: str
    booking_date: date
    amount: float
    sender_name: str
    sender_iban: Optional[str]
    reference: str
    account_iban: str


class BankConnectionDict(TypedDict):
    """Typisiertes Dictionary fuer BankConnection.to_dict()."""
    id: str
    company_id: str
    bank_name: str
    blz: str
    bic: Optional[str]
    account_count: int
    sync_schedule: str
    last_sync_at: Optional[str]
    next_sync_at: Optional[str]
    health_status: str
    error_count: int


class SyncResultDict(TypedDict):
    """Typisiertes Dictionary fuer SyncResult.to_dict()."""
    connection_id: str
    account_iban: str
    success: bool
    sync_at: str
    transaction_count: int
    new_transactions: int
    reconciled_count: int
    notifications_sent: int
    error: Optional[str]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BankConnection:
    """Eine Bank-Verbindung."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    bank_name: str = ""
    blz: str = ""
    bic: Optional[str] = None
    fints_url: Optional[str] = None

    # Accounts
    accounts: List["BankAccountInfo"] = field(default_factory=list)

    # Sync-Konfiguration
    sync_schedule: SyncSchedule = SyncSchedule.DAILY
    last_sync_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None

    # Health
    health_status: ConnectionHealth = ConnectionHealth.HEALTHY
    last_health_check: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None

    # Credentials (nur Referenz, nicht die echten Daten!)
    credentials_valid_until: Optional[datetime] = None

    def to_dict(self) -> BankConnectionDict:
        """Konvertiert zu Dictionary."""
        return BankConnectionDict(
            id=str(self.id),
            company_id=str(self.company_id),
            bank_name=self.bank_name,
            blz=self.blz,
            bic=self.bic,
            account_count=len(self.accounts),
            sync_schedule=self.sync_schedule.value,
            last_sync_at=self.last_sync_at.isoformat() if self.last_sync_at else None,
            next_sync_at=self.next_sync_at.isoformat() if self.next_sync_at else None,
            health_status=self.health_status.value,
            error_count=self.error_count,
        )


@dataclass
class BankAccountInfo:
    """Bankkonto-Information."""
    id: UUID = field(default_factory=uuid4)
    iban: str = ""
    account_name: str = ""
    account_type: str = "checking"  # checking, savings, credit
    currency: str = "EUR"
    current_balance: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    balance_date: Optional[datetime] = None


@dataclass
class IncomingPayment:
    """Eingehende Zahlung zur Benachrichtigung."""
    transaction_id: str
    account_iban: str
    amount: Decimal
    currency: str
    sender_name: str
    sender_iban: Optional[str]
    reference_text: str
    booking_date: date
    matched_invoice_id: Optional[UUID] = None
    matched_entity_id: Optional[UUID] = None
    reconciliation_type: Optional[ReconciliationType] = None
    confidence: float = 0.0


@dataclass
class ReconciliationResult:
    """Ergebnis einer Reconciliation."""
    transaction_id: str
    invoice_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    reconciliation_type: ReconciliationType = ReconciliationType.MANUAL
    confidence: float = 0.0
    matched_amount: Decimal = Decimal("0")
    expected_amount: Decimal = Decimal("0")
    difference: Decimal = Decimal("0")
    explanation: str = ""


@dataclass
class SyncResult:
    """Ergebnis einer Bank-Synchronisation."""
    connection_id: UUID
    account_iban: str
    success: bool
    sync_at: datetime = field(default_factory=utc_now)
    transaction_count: int = 0
    new_transactions: int = 0
    reconciled_count: int = 0
    notifications_sent: int = 0
    error: Optional[str] = None

    def to_dict(self) -> SyncResultDict:
        """Konvertiert zu Dictionary."""
        return SyncResultDict(
            connection_id=str(self.connection_id),
            account_iban=self.account_iban,
            success=self.success,
            sync_at=self.sync_at.isoformat(),
            transaction_count=self.transaction_count,
            new_transactions=self.new_transactions,
            reconciled_count=self.reconciled_count,
            notifications_sent=self.notifications_sent,
            error=self.error,
        )


@dataclass
class ReconciliationConfig:
    """Konfiguration fuer Auto-Reconciliation."""
    # Matching-Strategien (in Reihenfolge)
    strategies: List[ReconciliationType] = field(default_factory=lambda: [
        ReconciliationType.EXACT_MATCH,
        ReconciliationType.REFERENCE_MATCH,
        ReconciliationType.SKONTO_MATCH,
        ReconciliationType.AMOUNT_MATCH,
        ReconciliationType.PARTIAL_MATCH,
    ])

    # Confidence-Schwellenwerte
    auto_reconcile_threshold: float = 0.9   # Ab hier automatisch zuordnen
    suggest_threshold: float = 0.7          # Ab hier als Vorschlag anzeigen

    # Toleranzen
    amount_tolerance: Decimal = Decimal("0.01")  # Cent-Rundung
    skonto_tolerance: float = 0.05  # 5% Skonto-Toleranz
    date_tolerance_days: int = 7    # Tage Toleranz fuer Datum

    # Benachrichtigungen
    notify_on_reconciliation: bool = True
    notify_on_large_payment: bool = True
    large_payment_threshold: Decimal = Decimal("10000")


# =============================================================================
# Service
# =============================================================================

class EnhancedFinTSService:
    """
    Erweiterter FinTS Service.

    Features:
    - Automatischer taeglicher Sync
    - Multi-Bank-Support
    - Auto-Reconciliation
    - Payment-Notifications
    - Health-Monitoring
    """

    def __init__(
        self,
        reconciliation_config: Optional[ReconciliationConfig] = None,
    ):
        self.reconciliation_config = reconciliation_config or ReconciliationConfig()
        self._connections: Dict[UUID, BankConnection] = {}
        self._notification_handlers: Dict[NotificationChannel, Callable] = {}

        logger.info("enhanced_fints_service_initialized")

    def register_notification_handler(
        self,
        channel: NotificationChannel,
        handler: Callable[[IncomingPayment, UUID], None],
    ) -> None:
        """
        Registriert einen Notification-Handler.

        Args:
            channel: Benachrichtigungskanal
            handler: Handler-Funktion (payment, company_id) -> None
        """
        self._notification_handlers[channel] = handler
        logger.info(
            "notification_handler_registered",
            channel=channel.value,
        )

    async def add_bank_connection(
        self,
        company_id: UUID,
        bank_name: str,
        blz: str,
        fints_url: str,
        sync_schedule: SyncSchedule = SyncSchedule.DAILY,
    ) -> BankConnection:
        """
        Fuegt eine neue Bank-Verbindung hinzu.

        Args:
            company_id: Company-ID
            bank_name: Bankname
            blz: BLZ
            fints_url: FinTS-URL
            sync_schedule: Sync-Zeitplan

        Returns:
            Neue BankConnection
        """
        connection = BankConnection(
            company_id=company_id,
            bank_name=bank_name,
            blz=blz,
            fints_url=fints_url,
            sync_schedule=sync_schedule,
        )

        # Naechsten Sync berechnen
        connection.next_sync_at = self._calculate_next_sync(sync_schedule)

        self._connections[connection.id] = connection

        logger.info(
            "bank_connection_added",
            connection_id=str(connection.id),
            company_id=str(company_id),
            bank_name=bank_name,
        )

        return connection

    async def delete_connection(
        self,
        db: "AsyncSession",  # type: ignore[name-defined]
        connection_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> bool:
        """
        Loescht eine Bank-Verbindung.

        SECURITY: Validiert Company-Ownership um Cross-Company Access zu verhindern.

        Args:
            db: Datenbank-Session (fuer zukuenftige DB-Persistenz)
            connection_id: ID der zu loeschenden Verbindung
            user_id: ID des ausfuehrenden Users (fuer Audit)
            company_id: Company-ID des Users (PFLICHT fuer Security-Validierung)

        Returns:
            True wenn erfolgreich geloescht, False wenn nicht gefunden

        Raises:
            PermissionError: Wenn User keine Berechtigung fuer diese Verbindung hat
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return False

        # SECURITY: Validiere Company-Ownership
        if company_id is not None and connection.company_id != company_id:
            logger.warning(
                "unauthorized_connection_delete_attempt",
                connection_id=str(connection_id),
                user_id=str(user_id),
                user_company_id=str(company_id),
                connection_company_id=str(connection.company_id),
            )
            raise PermissionError(
                f"Keine Berechtigung fuer Verbindung {connection_id}. "
                f"Verbindung gehoert zu anderer Firma."
            )

        del self._connections[connection_id]

        logger.info(
            "bank_connection_deleted",
            connection_id=str(connection_id),
            company_id=str(connection.company_id),
            deleted_by_user=str(user_id),
        )

        return True

    async def get_connection(
        self,
        connection_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[BankConnection]:
        """
        Ruft eine Bank-Verbindung ab.

        SECURITY: Validiert Company-Ownership wenn company_id angegeben.

        Args:
            connection_id: ID der Verbindung
            company_id: Company-ID fuer Ownership-Check (optional aber empfohlen)

        Returns:
            BankConnection oder None wenn nicht gefunden

        Raises:
            PermissionError: Wenn company_id nicht zur Verbindung passt
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return None

        # SECURITY: Validiere Company-Ownership wenn angegeben
        if company_id is not None and connection.company_id != company_id:
            logger.warning(
                "unauthorized_connection_access_attempt",
                connection_id=str(connection_id),
                user_company_id=str(company_id),
                connection_company_id=str(connection.company_id),
            )
            raise PermissionError(
                f"Keine Berechtigung fuer Verbindung {connection_id}. "
                f"Verbindung gehoert zu anderer Firma."
            )

        return connection

    async def update_connection(
        self,
        db: "AsyncSession",  # type: ignore[name-defined]
        connection_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        is_primary: Optional[bool] = None,
        auto_sync_enabled: Optional[bool] = None,
        sync_interval_hours: Optional[int] = None,
    ) -> tuple[Optional[BankConnection], Optional[str]]:
        """
        Aktualisiert eine Bank-Verbindung.

        SECURITY: Validiert Company-Ownership um Cross-Company Access zu verhindern.

        Args:
            db: Datenbank-Session
            connection_id: ID der Verbindung
            user_id: ID des ausfuehrenden Users (fuer Audit)
            company_id: Company-ID des Users (PFLICHT fuer Security-Validierung)
            is_primary: Ob Primaer-Verbindung
            auto_sync_enabled: Auto-Sync aktiviert
            sync_interval_hours: Sync-Intervall in Stunden

        Returns:
            Tuple von (aktualisierte Connection oder None, Fehlermeldung oder None)
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return None, "Verbindung nicht gefunden."

        # SECURITY: Validiere Company-Ownership
        if company_id is not None and connection.company_id != company_id:
            logger.warning(
                "unauthorized_connection_update_attempt",
                connection_id=str(connection_id),
                user_id=str(user_id),
                user_company_id=str(company_id),
                connection_company_id=str(connection.company_id),
            )
            return None, "Keine Berechtigung fuer diese Verbindung."

        # Felder aktualisieren
        if is_primary is not None:
            connection.is_primary = is_primary
        if auto_sync_enabled is not None:
            connection.auto_sync_enabled = auto_sync_enabled
        if sync_interval_hours is not None:
            connection.sync_interval_hours = sync_interval_hours

        logger.info(
            "bank_connection_updated",
            connection_id=str(connection_id),
            company_id=str(connection.company_id),
            updated_by_user=str(user_id),
        )

        return connection, None

    async def sync_all_connections(
        self,
        force: bool = False,
    ) -> List[SyncResult]:
        """
        Synchronisiert alle faelligen Bank-Verbindungen.

        Args:
            force: Erzwingt Sync auch wenn nicht faellig

        Returns:
            Liste von Sync-Ergebnissen
        """
        results = []
        now = utc_now()

        for connection in self._connections.values():
            # Pruefen ob Sync faellig
            if not force and connection.next_sync_at and connection.next_sync_at > now:
                continue

            # Pruefen ob Verbindung gesund
            if connection.health_status == ConnectionHealth.UNHEALTHY:
                logger.warning(
                    "skipping_unhealthy_connection",
                    connection_id=str(connection.id),
                )
                continue

            try:
                result = await self._sync_connection(connection)
                results.append(result)

                # Naechsten Sync planen
                connection.next_sync_at = self._calculate_next_sync(connection.sync_schedule)

            except Exception as e:
                logger.error(
                    "sync_connection_failed",
                    connection_id=str(connection.id),
                    error=str(e),
                )
                connection.error_count += 1
                connection.last_error = str(e)

                results.append(SyncResult(
                    connection_id=connection.id,
                    account_iban="",
                    success=False,
                    error=str(e),
                ))

        return results

    async def sync_connection(
        self,
        connection_id: UUID,
        company_id: Optional[UUID] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> SyncResult:
        """
        Synchronisiert eine einzelne Bank-Verbindung.

        SECURITY: Validiert Company-Ownership um Cross-Company Access zu verhindern.

        Args:
            connection_id: Connection-ID
            company_id: Company-ID fuer Ownership-Check (EMPFOHLEN)
            date_from: Start-Datum
            date_to: End-Datum

        Returns:
            Sync-Ergebnis
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return SyncResult(
                connection_id=connection_id,
                account_iban="",
                success=False,
                error="Verbindung nicht gefunden",
            )

        # SECURITY: Validiere Company-Ownership
        if company_id is not None and connection.company_id != company_id:
            logger.warning(
                "unauthorized_sync_attempt",
                connection_id=str(connection_id),
                user_company_id=str(company_id),
                connection_company_id=str(connection.company_id),
            )
            return SyncResult(
                connection_id=connection_id,
                account_iban="",
                success=False,
                error="Keine Berechtigung fuer diese Verbindung",
            )

        return await self._sync_connection(connection, date_from, date_to)

    async def _sync_connection(
        self,
        connection: BankConnection,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> SyncResult:
        """
        Interne Sync-Methode.
        """
        import time
        start_time = time.time()

        if not date_from:
            # Standard: Letzte 30 Tage oder seit letztem Sync
            if connection.last_sync_at:
                date_from = (connection.last_sync_at - timedelta(days=3)).date()
            else:
                date_from = (datetime.now() - timedelta(days=30)).date()

        if not date_to:
            date_to = date.today()

        logger.info(
            "syncing_bank_connection",
            connection_id=str(connection.id),
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
        )

        try:
            # In Produktion: Echte FinTS-Transaktion
            # Hier: Mock-Daten
            transactions = self._generate_mock_transactions(
                connection, date_from, date_to
            )

            # Neue Transaktionen identifizieren
            new_transactions = [t for t in transactions if self._is_new_transaction(t)]

            # Auto-Reconciliation
            reconciled = []
            for tx in new_transactions:
                if tx["amount"] > 0:  # Nur Eingaenge reconcilen
                    result = await self._auto_reconcile(
                        tx, connection.company_id
                    )
                    if result:
                        reconciled.append(result)

            # Benachrichtigungen senden
            notifications_sent = 0
            for tx in new_transactions:
                if tx["amount"] > 0:  # Nur Eingaenge benachrichtigen
                    payment = IncomingPayment(
                        transaction_id=tx["id"],
                        account_iban=tx.get("account_iban", ""),
                        amount=Decimal(str(tx["amount"])),
                        currency="EUR",
                        sender_name=tx.get("sender_name", "Unbekannt"),
                        sender_iban=tx.get("sender_iban"),
                        reference_text=tx.get("reference", ""),
                        booking_date=tx.get("booking_date", date.today()),
                    )

                    if await self._send_payment_notification(payment, connection.company_id):
                        notifications_sent += 1

            # Update Connection Status
            connection.last_sync_at = utc_now()
            connection.error_count = 0
            connection.last_error = None
            connection.health_status = ConnectionHealth.HEALTHY

            duration = time.time() - start_time

            BANK_SYNC_TOTAL.labels(
                company_id=str(connection.company_id),
                bank_name=connection.bank_name,
                status="success",
            ).inc()

            BANK_SYNC_DURATION.labels(
                company_id=str(connection.company_id),
            ).observe(duration)

            logger.info(
                "bank_sync_completed",
                connection_id=str(connection.id),
                total_transactions=len(transactions),
                new_transactions=len(new_transactions),
                reconciled=len(reconciled),
                duration_seconds=duration,
            )

            return SyncResult(
                connection_id=connection.id,
                account_iban=connection.accounts[0].iban if connection.accounts else "",
                success=True,
                transaction_count=len(transactions),
                new_transactions=len(new_transactions),
                reconciled_count=len(reconciled),
                notifications_sent=notifications_sent,
            )

        except Exception as e:
            connection.error_count += 1
            connection.last_error = str(e)

            if connection.error_count >= 3:
                connection.health_status = ConnectionHealth.UNHEALTHY

            BANK_SYNC_TOTAL.labels(
                company_id=str(connection.company_id),
                bank_name=connection.bank_name,
                status="error",
            ).inc()

            raise

    async def _auto_reconcile(
        self,
        transaction: TransactionData,
        company_id: UUID,
    ) -> Optional[ReconciliationResult]:
        """
        Versucht automatische Zuordnung einer Transaktion.

        Args:
            transaction: Typisierte Transaktionsdaten
            company_id: Company-ID

        Returns:
            Reconciliation-Ergebnis oder None
        """
        amount = Decimal(str(transaction["amount"]))
        sender_iban = transaction["sender_iban"]
        reference = transaction["reference"]

        best_match: Optional[ReconciliationResult] = None
        best_confidence = 0.0

        for strategy in self.reconciliation_config.strategies:
            result = await self._try_reconciliation_strategy(
                strategy=strategy,
                amount=amount,
                sender_iban=sender_iban,
                reference=reference,
                company_id=company_id,
            )

            if result and result.confidence > best_confidence:
                best_match = result
                best_confidence = result.confidence

                # Bei sehr hoher Confidence sofort akzeptieren
                if best_confidence >= self.reconciliation_config.auto_reconcile_threshold:
                    break

        if best_match:
            RECONCILED_TRANSACTIONS.labels(
                company_id=str(company_id),
                reconciliation_type=best_match.reconciliation_type.value,
            ).inc()

            logger.info(
                "transaction_auto_reconciled",
                transaction_id=transaction["id"],
                invoice_id=str(best_match.invoice_id) if best_match.invoice_id else None,
                reconciliation_type=best_match.reconciliation_type.value,
                confidence=best_match.confidence,
            )

        return best_match

    async def _try_reconciliation_strategy(
        self,
        strategy: ReconciliationType,
        amount: Decimal,
        sender_iban: Optional[str],
        reference: str,
        company_id: UUID,
    ) -> Optional[ReconciliationResult]:
        """
        Versucht eine Reconciliation-Strategie.

        In Produktion: Sucht in der Datenbank nach passenden Rechnungen.
        Hier: Mock-Implementation.
        """
        # Mock: Simuliere verschiedene Match-Szenarien

        if strategy == ReconciliationType.EXACT_MATCH:
            # IBAN + Betrag exakt
            if sender_iban and amount > 0:
                # TODO: In Produktion - echte DB-Abfrage statt Mock
                # Mock: Deterministisch basierend auf IBAN-Hash fuer Testbarkeit
                import hashlib
                iban_hash = int(hashlib.md5(sender_iban.encode()).hexdigest()[:8], 16)
                # Deterministisches Match basierend auf IBAN (kein random!)
                if iban_hash % 3 == 0:  # ~33% Match-Rate, aber deterministisch
                    return ReconciliationResult(
                        transaction_id="",
                        invoice_id=uuid4(),
                        reconciliation_type=strategy,
                        confidence=0.99,
                        matched_amount=amount,
                        expected_amount=amount,
                        difference=Decimal("0"),
                        explanation=f"IBAN {sender_iban} und Betrag {amount} stimmen exakt ueberein",
                    )

        elif strategy == ReconciliationType.REFERENCE_MATCH:
            # Rechnungsnummer in Verwendungszweck
            import re
            invoice_pattern = r"(?:RE|INV|RG)[- ]?(\d{4,10})"
            match = re.search(invoice_pattern, reference, re.IGNORECASE)
            if match:
                return ReconciliationResult(
                    transaction_id="",
                    invoice_id=uuid4(),
                    reconciliation_type=strategy,
                    confidence=0.95,
                    matched_amount=amount,
                    expected_amount=amount,
                    difference=Decimal("0"),
                    explanation=f"Rechnungsnummer {match.group(0)} im Verwendungszweck gefunden",
                )

        elif strategy == ReconciliationType.SKONTO_MATCH:
            # Betrag entspricht Skonto-Abzug (2-3%)
            skonto_rates = [Decimal("0.02"), Decimal("0.03")]
            for rate in skonto_rates:
                # SECURITY: Guard against division by zero when rate >= 1.0
                if rate >= Decimal("1.0"):
                    logger.warning(
                        "invalid_skonto_rate",
                        rate=str(rate),
                        message="Skonto-Rate >= 100% ist ungueltig",
                    )
                    continue
                gross_amount = amount / (1 - rate)
                # TODO: In Produktion - echte DB-Abfrage
                # Mock: Deterministisch basierend auf Betrag-Hash
                import hashlib
                amount_hash = int(hashlib.md5(str(amount).encode()).hexdigest()[:8], 16)
                if amount_hash % 10 == 0:  # ~10% Match-Rate, deterministisch
                    return ReconciliationResult(
                        transaction_id="",
                        invoice_id=uuid4(),
                        reconciliation_type=strategy,
                        confidence=0.85,
                        matched_amount=amount,
                        expected_amount=gross_amount.quantize(Decimal("0.01")),
                        difference=gross_amount - amount,
                        explanation=f"Betrag entspricht {rate*100:.0f}% Skonto-Abzug",
                    )

        return None

    async def _send_payment_notification(
        self,
        payment: IncomingPayment,
        company_id: UUID,
    ) -> bool:
        """
        Sendet Benachrichtigung ueber Zahlungseingang.

        Args:
            payment: Zahlungsinformation
            company_id: Company-ID

        Returns:
            True wenn gesendet
        """
        # Pruefe ob Benachrichtigung gewuenscht
        if not self.reconciliation_config.notify_on_reconciliation:
            return False

        # Bei grossen Zahlungen immer benachrichtigen
        if payment.amount >= self.reconciliation_config.large_payment_threshold:
            logger.info(
                "large_payment_notification",
                amount=str(payment.amount),
                sender=payment.sender_name,
            )

        # An registrierte Handler senden
        sent = False
        for channel, handler in self._notification_handlers.items():
            try:
                # FIX: Async handlers muessen awaited werden
                if asyncio.iscoroutinefunction(handler):
                    await handler(payment, company_id)
                else:
                    handler(payment, company_id)
                PAYMENT_NOTIFICATIONS.labels(
                    company_id=str(company_id),
                    channel=channel.value,
                ).inc()
                sent = True
            except Exception as e:
                logger.error(
                    "notification_handler_failed",
                    channel=channel.value,
                    error=str(e),
                )

        return sent

    async def check_connection_health(
        self,
        connection_id: UUID,
    ) -> ConnectionHealth:
        """
        Prueft die Gesundheit einer Bank-Verbindung.

        Args:
            connection_id: Connection-ID

        Returns:
            Health-Status
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return ConnectionHealth.UNHEALTHY

        # Pruefe letzte Sync-Zeit
        if connection.last_sync_at:
            hours_since_sync = (utc_now() - connection.last_sync_at).total_seconds() / 3600

            if connection.sync_schedule == SyncSchedule.HOURLY and hours_since_sync > 2:
                connection.health_status = ConnectionHealth.DEGRADED
            elif connection.sync_schedule == SyncSchedule.DAILY and hours_since_sync > 48:
                connection.health_status = ConnectionHealth.DEGRADED

        # Pruefe Fehler-Count
        if connection.error_count >= 3:
            connection.health_status = ConnectionHealth.UNHEALTHY
        elif connection.error_count >= 1:
            connection.health_status = ConnectionHealth.DEGRADED

        # Pruefe Credential-Ablauf
        if connection.credentials_valid_until:
            if connection.credentials_valid_until < utc_now():
                connection.health_status = ConnectionHealth.EXPIRED

        connection.last_health_check = utc_now()

        BANK_CONNECTION_HEALTH.labels(
            company_id=str(connection.company_id),
            bank_id=str(connection.id),
        ).set(1 if connection.health_status == ConnectionHealth.HEALTHY else 0)

        return connection.health_status

    async def check_all_connections_health(self) -> Dict[UUID, ConnectionHealth]:
        """
        Prueft Gesundheit aller Verbindungen.

        Returns:
            Dict von Connection-ID -> Health
        """
        results = {}
        for connection_id in self._connections:
            results[connection_id] = await self.check_connection_health(connection_id)
        return results

    def get_connection(self, connection_id: UUID) -> Optional[BankConnection]:
        """Holt eine Connection nach ID."""
        return self._connections.get(connection_id)

    def list_connections(
        self,
        company_id: Optional[UUID] = None,
    ) -> List[BankConnection]:
        """
        Listet Bank-Verbindungen.

        Args:
            company_id: Optional Company-Filter

        Returns:
            Liste von Verbindungen
        """
        connections = list(self._connections.values())

        if company_id:
            connections = [c for c in connections if c.company_id == company_id]

        return connections

    def _calculate_next_sync(self, schedule: SyncSchedule) -> datetime:
        """Berechnet naechsten Sync-Zeitpunkt."""
        now = utc_now()

        if schedule == SyncSchedule.REALTIME:
            return now + timedelta(minutes=5)
        elif schedule == SyncSchedule.HOURLY:
            return now + timedelta(hours=1)
        elif schedule == SyncSchedule.DAILY:
            # Naechster Tag um 06:00 UTC
            next_day = (now + timedelta(days=1)).replace(
                hour=6, minute=0, second=0, microsecond=0
            )
            return next_day
        else:
            # Manual: Weit in der Zukunft
            return now + timedelta(days=365)

    def _is_new_transaction(self, transaction: TransactionData) -> bool:
        """Prueft ob Transaktion neu ist (in Produktion: DB-Check)."""
        # TODO: In Produktion - echte DB-Abfrage ob Transaction-ID existiert
        # Mock: Deterministisch basierend auf Transaction-ID Hash
        import hashlib
        tx_id = transaction["id"]
        if not tx_id:
            return True  # Ohne ID immer als neu behandeln
        tx_hash = int(hashlib.md5(tx_id.encode()).hexdigest()[:8], 16)
        return tx_hash % 2 == 0  # ~50%, aber deterministisch und testbar

    def _generate_mock_transactions(
        self,
        connection: BankConnection,
        date_from: date,
        date_to: date,
    ) -> List[TransactionData]:
        """
        Generiert Mock-Transaktionen fuer Tests.

        HINWEIS: Verwendet deterministisches Seeding fuer Reproduzierbarkeit.
        In Produktion durch echte FinTS-API-Aufrufe ersetzen.
        """
        import hashlib

        # Deterministisches Seeding basierend auf Connection + Datumsbereich
        seed_str = f"{connection.id}:{date_from}:{date_to}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)

        transactions: List[TransactionData] = []
        current = date_from
        tx_counter = 0

        sender_names = [
            "Amazon EU S.a.r.l.",
            "REWE Markt GmbH",
            "Kunde XY GmbH",
            "Lieferant ABC",
        ]

        while current <= date_to:
            # Deterministisch basierend auf Datum
            day_seed = seed + current.toordinal()
            num_transactions = day_seed % 6  # 0-5 Transaktionen pro Tag

            for i in range(num_transactions):
                tx_seed = day_seed * 100 + i
                tx_counter += 1

                # Deterministischer Betrag
                amount_raw = ((tx_seed % 15000) - 5000) / 10.0  # -500 bis +1000
                amount = Decimal(str(amount_raw)).quantize(Decimal("0.01"))

                # Deterministischer Sender
                sender_idx = tx_seed % len(sender_names)

                # Deterministisch ob IBAN vorhanden
                has_iban = (tx_seed % 2) == 0

                # Deterministisch ob Referenz vorhanden
                has_reference = (tx_seed % 3) != 0
                ref_number = 1000 + (tx_seed % 9000) if has_reference else 0

                transactions.append(TransactionData(
                    id=f"{connection.id.hex[:8]}_{tx_counter:04d}",
                    booking_date=current,
                    amount=float(amount),
                    sender_name=sender_names[sender_idx],
                    sender_iban="DE89370400440532013000" if has_iban else None,
                    reference=f"RE-2026-{ref_number}" if has_reference else "Zahlung",
                    account_iban=connection.accounts[0].iban if connection.accounts else "",
                ))
            current += timedelta(days=1)

        return transactions


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[EnhancedFinTSService] = None


def get_enhanced_fints_service(
    reconciliation_config: Optional[ReconciliationConfig] = None,
) -> EnhancedFinTSService:
    """
    Factory-Funktion fuer EnhancedFinTSService.

    Args:
        reconciliation_config: Optional Konfiguration

    Returns:
        EnhancedFinTSService Instanz
    """
    global _service_instance

    if _service_instance is None or reconciliation_config is not None:
        _service_instance = EnhancedFinTSService(reconciliation_config)

    return _service_instance
