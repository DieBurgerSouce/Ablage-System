# -*- coding: utf-8 -*-
"""
Enhanced FinTS Service - Erweiterte Banking-Integration.

Vision 2026 Q4: Vollautomatische Banking-Anbindung.

Erweiterungen:
- Automatischer täglicher Kontoauszug-Abruf
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

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from sqlalchemy.ext.asyncio import AsyncSession

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
    REALTIME = "realtime"     # Sofort (wenn möglich)
    HOURLY = "hourly"         # Stuendlich
    DAILY = "daily"           # Täglich
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
    """Typisierte Transaktionsdaten für Type Safety."""
    id: str
    booking_date: date
    amount: float
    sender_name: str
    sender_iban: Optional[str]
    reference: str
    account_iban: str


class BankConnectionDict(TypedDict):
    """Typisiertes Dictionary für BankConnection.to_dict()."""
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
    """Typisiertes Dictionary für SyncResult.to_dict()."""
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
    """Konfiguration für Auto-Reconciliation."""
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
    date_tolerance_days: int = 7    # Tage Toleranz für Datum

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
    - Automatischer täglicher Sync
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

        # Nächsten Sync berechnen
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
        Löscht eine Bank-Verbindung.

        SECURITY: Validiert Company-Ownership um Cross-Company Access zu verhindern.

        Args:
            db: Datenbank-Session (für zukünftige DB-Persistenz)
            connection_id: ID der zu löschenden Verbindung
            user_id: ID des ausführenden Users (für Audit)
            company_id: Company-ID des Users (PFLICHT für Security-Validierung)

        Returns:
            True wenn erfolgreich gelöscht, False wenn nicht gefunden

        Raises:
            PermissionError: Wenn User keine Berechtigung für diese Verbindung hat
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
                f"Keine Berechtigung für Verbindung {connection_id}. "
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
            company_id: Company-ID für Ownership-Check (optional aber empfohlen)

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
                f"Keine Berechtigung für Verbindung {connection_id}. "
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
            user_id: ID des ausführenden Users (für Audit)
            company_id: Company-ID des Users (PFLICHT für Security-Validierung)
            is_primary: Ob Primär-Verbindung
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
            return None, "Keine Berechtigung für diese Verbindung."

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
        Synchronisiert alle fälligen Bank-Verbindungen.

        Args:
            force: Erzwingt Sync auch wenn nicht fällig

        Returns:
            Liste von Sync-Ergebnissen
        """
        results = []
        now = utc_now()

        for connection in self._connections.values():
            # Prüfen ob Sync fällig
            if not force and connection.next_sync_at and connection.next_sync_at > now:
                continue

            # Prüfen ob Verbindung gesund
            if connection.health_status == ConnectionHealth.UNHEALTHY:
                logger.warning(
                    "skipping_unhealthy_connection",
                    connection_id=str(connection.id),
                )
                continue

            try:
                result = await self._sync_connection(connection)
                results.append(result)

                # Nächsten Sync planen
                connection.next_sync_at = self._calculate_next_sync(connection.sync_schedule)

            except Exception as e:
                logger.error(
                    "sync_connection_failed",
                    connection_id=str(connection.id),
                    **safe_error_log(e),
                )
                connection.error_count += 1
                connection.last_error = safe_error_detail(e, "FinTS")

                results.append(SyncResult(
                    connection_id=connection.id,
                    account_iban="",
                    success=False,
                    **safe_error_log(e),
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
            company_id: Company-ID für Ownership-Check (EMPFOHLEN)
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
                error="Keine Berechtigung für diese Verbindung",
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
            # SECURITY (M9): Mock-Transaktionen duerfen NIEMALS echte
            # Reconciliation (_auto_reconcile) oder Zahlungs-Benachrichtigungen
            # (IncomingPayment) ausloesen. Eine echte FinTS-Anbindung existiert
            # hier noch nicht. Nur wenn explizit per Settings freigeschaltet
            # (FINTS_ALLOW_MOCK_SYNC=True, z. B. in Test-/Demo-Umgebungen)
            # werden deterministische Test-Transaktionen erzeugt. Andernfalls
            # bleibt die Liste leer, damit kein Fake-Eingang gebucht wird.
            if settings.is_production:
                # Harter Produktions-Block (M9): niemals Mock-Transaktionen in
                # Produktion erzeugen/reconcilen, auch nicht bei FINTS_ALLOW_MOCK_SYNC.
                transactions = []
                logger.error(
                    "fints_mock_sync_blocked_in_production",
                    connection_id=str(connection.id),
                )
            elif getattr(settings, "FINTS_ALLOW_MOCK_SYNC", False):
                transactions = self._generate_mock_transactions(
                    connection, date_from, date_to
                )
            else:
                transactions = []
                logger.warning(
                    "fints_mock_sync_disabled",
                    connection_id=str(connection.id),
                    reason="mock_transaktionen_blockiert_keine_reconciliation",
                )

            # Neue Transaktionen identifizieren (async DB-Check)
            new_transactions = []
            for t in transactions:
                if await self._is_new_transaction(t, connection.company_id):
                    new_transactions.append(t)

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
            connection.last_error = safe_error_detail(e, "FinTS")

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

        Sucht in der Datenbank nach passenden Rechnungen basierend auf
        verschiedenen Matching-Strategien.
        """
        from sqlalchemy import select, and_, or_, func
        from sqlalchemy.orm import joinedload
        from app.db.session import async_session_maker
        from app.db.models import InvoiceTracking, Document, BusinessEntity, InvoiceStatus
        import re

        if strategy == ReconciliationType.EXACT_MATCH:
            # IBAN + Betrag exakt - suche Entity mit passender IBAN und offener Rechnung
            if sender_iban and amount > 0:
                try:
                    async with async_session_maker() as db:
                        # Suche offene Rechnungen für Entity mit passender IBAN
                        result = await db.execute(
                            select(InvoiceTracking)
                            .join(Document, InvoiceTracking.document_id == Document.id)
                            .join(BusinessEntity, Document.business_entity_id == BusinessEntity.id)
                            .where(
                                and_(
                                    BusinessEntity.iban == sender_iban,
                                    InvoiceTracking.company_id == company_id,
                                    InvoiceTracking.status.in_([InvoiceStatus.OPEN.value, InvoiceStatus.OVERDUE.value]),
                                    # Toleranz: +/- 0.5% für Rundungsdifferenzen
                                    func.abs(InvoiceTracking.amount - float(amount)) < float(amount * Decimal("0.005") + Decimal("0.01")),
                                    InvoiceTracking.deleted_at.is_(None),
                                )
                            )
                            .order_by(InvoiceTracking.due_date.asc())  # Aelteste zuerst
                            .limit(1)
                        )
                        invoice = result.scalar_one_or_none()

                        if invoice:
                            expected_amount = Decimal(str(invoice.amount))
                            return ReconciliationResult(
                                transaction_id="",
                                invoice_id=invoice.id,
                                reconciliation_type=strategy,
                                confidence=0.99,
                                matched_amount=amount,
                                expected_amount=expected_amount,
                                difference=amount - expected_amount,
                                explanation=f"IBAN {sender_iban} und Betrag {amount} stimmen mit Rechnung {invoice.invoice_number or invoice.id} überein",
                            )
                except Exception as e:
                    logger.warning(
                        "exact_match_db_error",
                        sender_iban=sender_iban[:8] + "..." if sender_iban else None,
                        error=str(e),
                    )

        elif strategy == ReconciliationType.REFERENCE_MATCH:
            # Rechnungsnummer in Verwendungszweck
            invoice_pattern = r"(?:RE|INV|RG|RECH)[- ]?(\d{4,10})"
            match = re.search(invoice_pattern, reference, re.IGNORECASE)
            if match:
                invoice_ref = match.group(0)
                invoice_number_part = match.group(1)

                try:
                    async with async_session_maker() as db:
                        # Suche Rechnung mit passender Rechnungsnummer
                        result = await db.execute(
                            select(InvoiceTracking)
                            .where(
                                and_(
                                    InvoiceTracking.company_id == company_id,
                                    InvoiceTracking.status.in_([InvoiceStatus.OPEN.value, InvoiceStatus.OVERDUE.value]),
                                    or_(
                                        InvoiceTracking.invoice_number.ilike(f"%{invoice_number_part}%"),
                                        InvoiceTracking.invoice_number.ilike(f"%{invoice_ref}%"),
                                    ),
                                    InvoiceTracking.deleted_at.is_(None),
                                )
                            )
                            .order_by(InvoiceTracking.due_date.asc())
                            .limit(1)
                        )
                        invoice = result.scalar_one_or_none()

                        if invoice:
                            expected_amount = Decimal(str(invoice.amount))
                            # Confidence basierend auf Betragsabweichung
                            amount_diff = abs(amount - expected_amount)
                            if amount_diff <= Decimal("0.01"):
                                confidence = 0.98
                            elif amount_diff <= expected_amount * Decimal("0.05"):
                                confidence = 0.90
                            else:
                                confidence = 0.75

                            return ReconciliationResult(
                                transaction_id="",
                                invoice_id=invoice.id,
                                reconciliation_type=strategy,
                                confidence=confidence,
                                matched_amount=amount,
                                expected_amount=expected_amount,
                                difference=amount - expected_amount,
                                explanation=f"Rechnungsnummer {invoice_ref} im Verwendungszweck gefunden - Rechnung {invoice.invoice_number}",
                            )
                except Exception as e:
                    logger.warning(
                        "reference_match_db_error",
                        invoice_ref=invoice_ref,
                        error=str(e),
                    )

        elif strategy == ReconciliationType.SKONTO_MATCH:
            # Betrag entspricht Skonto-Abzug
            if sender_iban and amount > 0:
                try:
                    async with async_session_maker() as db:
                        # Suche Rechnungen mit aktivem Skonto für passende IBAN
                        result = await db.execute(
                            select(InvoiceTracking)
                            .join(Document, InvoiceTracking.document_id == Document.id)
                            .join(BusinessEntity, Document.business_entity_id == BusinessEntity.id)
                            .where(
                                and_(
                                    BusinessEntity.iban == sender_iban,
                                    InvoiceTracking.company_id == company_id,
                                    InvoiceTracking.status.in_([InvoiceStatus.OPEN.value, InvoiceStatus.OVERDUE.value]),
                                    InvoiceTracking.skonto_percentage.isnot(None),
                                    InvoiceTracking.skonto_amount.isnot(None),
                                    InvoiceTracking.skonto_used == False,
                                    InvoiceTracking.deleted_at.is_(None),
                                )
                            )
                            .order_by(InvoiceTracking.skonto_deadline.asc())  # Früheste Frist zuerst
                        )
                        invoices = result.scalars().all()

                        for invoice in invoices:
                            # Berechne erwarteten Skonto-Betrag
                            expected_skonto_amount = Decimal(str(invoice.amount)) - Decimal(str(invoice.skonto_amount or 0))

                            # Toleranz: +/- 0.5% für Rundungsdifferenzen
                            tolerance = expected_skonto_amount * Decimal("0.005") + Decimal("0.01")

                            if abs(amount - expected_skonto_amount) <= tolerance:
                                skonto_rate = Decimal(str(invoice.skonto_percentage or 0))
                                return ReconciliationResult(
                                    transaction_id="",
                                    invoice_id=invoice.id,
                                    reconciliation_type=strategy,
                                    confidence=0.92,
                                    matched_amount=amount,
                                    expected_amount=Decimal(str(invoice.amount)),
                                    difference=amount - Decimal(str(invoice.amount)),
                                    explanation=f"Betrag entspricht {skonto_rate:.1f}% Skonto-Abzug auf Rechnung {invoice.invoice_number or invoice.id}",
                                )
                except Exception as e:
                    logger.warning(
                        "skonto_match_db_error",
                        sender_iban=sender_iban[:8] + "..." if sender_iban else None,
                        error=str(e),
                    )

        return None

    async def _send_payment_notification(
        self,
        payment: IncomingPayment,
        company_id: UUID,
    ) -> bool:
        """
        Sendet Benachrichtigung über Zahlungseingang.

        Args:
            payment: Zahlungsinformation
            company_id: Company-ID

        Returns:
            True wenn gesendet
        """
        # Prüfe ob Benachrichtigung gewünscht
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
                # FIX: Async handlers müssen awaited werden
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
                    **safe_error_log(e),
                )

        return sent

    async def check_connection_health(
        self,
        connection_id: UUID,
    ) -> ConnectionHealth:
        """
        Prüft die Gesundheit einer Bank-Verbindung.

        Args:
            connection_id: Connection-ID

        Returns:
            Health-Status
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return ConnectionHealth.UNHEALTHY

        # Prüfe letzte Sync-Zeit
        if connection.last_sync_at:
            hours_since_sync = (utc_now() - connection.last_sync_at).total_seconds() / 3600

            if connection.sync_schedule == SyncSchedule.HOURLY and hours_since_sync > 2:
                connection.health_status = ConnectionHealth.DEGRADED
            elif connection.sync_schedule == SyncSchedule.DAILY and hours_since_sync > 48:
                connection.health_status = ConnectionHealth.DEGRADED

        # Prüfe Fehler-Count
        if connection.error_count >= 3:
            connection.health_status = ConnectionHealth.UNHEALTHY
        elif connection.error_count >= 1:
            connection.health_status = ConnectionHealth.DEGRADED

        # Prüfe Credential-Ablauf
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
        Prüft Gesundheit aller Verbindungen.

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
        """Berechnet nächsten Sync-Zeitpunkt."""
        now = utc_now()

        if schedule == SyncSchedule.REALTIME:
            return now + timedelta(minutes=5)
        elif schedule == SyncSchedule.HOURLY:
            return now + timedelta(hours=1)
        elif schedule == SyncSchedule.DAILY:
            # Nächster Tag um 06:00 UTC
            next_day = (now + timedelta(days=1)).replace(
                hour=6, minute=0, second=0, microsecond=0
            )
            return next_day
        else:
            # Manual: Weit in der Zukunft
            return now + timedelta(days=365)

    async def _is_new_transaction(
        self,
        transaction: TransactionData,
        company_id: UUID,
    ) -> bool:
        """
        Prüft ob Transaktion bereits in der Datenbank existiert.

        Args:
            transaction: Transaktionsdaten
            company_id: Company-ID für Multi-Tenant-Isolation

        Returns:
            True wenn Transaktion neu ist (noch nicht in DB)
        """
        from sqlalchemy import select, and_
        from app.db.session import async_session_maker
        from app.db.models import BankTransaction, BankAccount

        tx_id = transaction.get("id")
        if not tx_id:
            return True  # Ohne ID immer als neu behandeln

        try:
            async with async_session_maker() as db:
                # Suche existierende Transaktion mit gleicher ID
                result = await db.execute(
                    select(BankTransaction.id)
                    .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
                    .where(
                        and_(
                            BankTransaction.transaction_id == tx_id,
                            BankAccount.company_id == company_id,
                        )
                    )
                    .limit(1)
                )
                existing = result.scalar_one_or_none()
                return existing is None  # Neu wenn nicht gefunden

        except Exception as e:
            logger.warning(
                "transaction_duplicate_check_failed",
                tx_id=tx_id,
                error=str(e),
            )
            # Bei Fehler als neu behandeln, um Datenverlust zu vermeiden
            return True

    def _generate_mock_transactions(
        self,
        connection: BankConnection,
        date_from: date,
        date_to: date,
    ) -> List[TransactionData]:
        """
        Generiert Mock-Transaktionen für Tests.

        HINWEIS: Verwendet deterministisches Seeding für Reproduzierbarkeit.
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
# F-31 minimal result objects + service methods
# =============================================================================
#
# Der Router (api/v1/enhanced_banking.py) ruft list_connections /
# get_pending_reconciliations / get_aggregated_balance /
# get_aggregated_transactions auf. Diese Methoden fehlten -> AttributeError ->
# HTTP 500. Die Enhanced-FinTS-Verbindungen werden derzeit NICHT persistiert
# (nur In-Memory _connections), daher liefern die Methoden leere/0-Defaults.
# Keine erfundenen Geldwerte.


@dataclass
class PendingReconciliationsResult:
    """F-31 minimal: offene Abgleiche (leer bis Persistenz existiert)."""
    total: int = 0
    total_amount: Decimal = Decimal("0")
    by_bank: Dict[str, int] = field(default_factory=dict)
    transactions: List[dict] = field(default_factory=list)


@dataclass
class AggregatedBalanceResult:
    """F-31 minimal: aggregierter Kontostand."""
    total_balance: Decimal = Decimal("0")
    total_available: Decimal = Decimal("0")
    currency: str = "EUR"
    connection_count: int = 0
    by_bank: List[dict] = field(default_factory=list)
    as_of: datetime = field(default_factory=utc_now)


@dataclass
class AggregatedTransactionsResult:
    """F-31 minimal: aggregierte Transaktionen."""
    transactions: List[dict] = field(default_factory=list)
    total: int = 0
    total_inflow: Decimal = Decimal("0")
    total_outflow: Decimal = Decimal("0")


def _enhanced_list_connections(self, company_id: UUID) -> List[BankConnection]:
    """F-31 minimal: Bankverbindungen einer Company.

    Verbindungen werden derzeit nicht persistiert; nur die In-Memory-Map wird
    gefiltert (im Normalfall leer).
    """
    return [c for c in self._connections.values() if c.company_id == company_id]


async def _enhanced_get_pending_reconciliations(
    self,
    db: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    connection_id: Optional[UUID] = None,
    page: int = 1,
    page_size: int = 50,
) -> "PendingReconciliationsResult":
    """F-31 minimal: offene Abgleiche (leer)."""
    return PendingReconciliationsResult()


async def _enhanced_get_aggregated_balance(
    self,
    db: AsyncSession,
    company_id: UUID,
    user_id: UUID,
) -> "AggregatedBalanceResult":
    """F-31 minimal: aggregierter Kontostand (0)."""
    return AggregatedBalanceResult()


async def _enhanced_get_aggregated_transactions(
    self,
    db: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 50,
) -> "AggregatedTransactionsResult":
    """F-31 minimal: aggregierte Transaktionen (leer)."""
    return AggregatedTransactionsResult()


EnhancedFinTSService.list_connections = _enhanced_list_connections
EnhancedFinTSService.get_pending_reconciliations = _enhanced_get_pending_reconciliations
EnhancedFinTSService.get_aggregated_balance = _enhanced_get_aggregated_balance
EnhancedFinTSService.get_aggregated_transactions = _enhanced_get_aggregated_transactions


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[EnhancedFinTSService] = None


def get_enhanced_fints_service(
    reconciliation_config: Optional[ReconciliationConfig] = None,
) -> EnhancedFinTSService:
    """
    Factory-Funktion für EnhancedFinTSService.

    Args:
        reconciliation_config: Optional Konfiguration

    Returns:
        EnhancedFinTSService Instanz
    """
    global _service_instance

    if _service_instance is None or reconciliation_config is not None:
        _service_instance = EnhancedFinTSService(reconciliation_config)

    return _service_instance
