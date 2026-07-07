"""
Abstract Base Class for ERP Connectors.

Enterprise-Level ERP-Abstraktion:
- Einheitliche Schnittstelle für alle ERP-Systeme
- Sync-Richtungen (Push/Pull/Bidirektional)
- Connection Pooling und Rate Limiting
- Retry-Logik und Circuit Breaker

Feinpoliert und durchdacht - Zukunftssichere ERP-Architektur.
"""

import threading

import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from app.core.datetime_utils import utc_now
from enum import Enum
from typing import Any, Dict, List, Optional, TypeVar, Generic
from uuid import UUID

logger = structlog.get_logger(__name__)


class ERPSyncDirection(str, Enum):
    """Synchronisationsrichtung."""
    PUSH = "push"  # Ablage -> ERP
    PULL = "pull"  # ERP -> Ablage
    BIDIRECTIONAL = "bidirectional"  # Beide Richtungen


class ERPConnectionStatus(str, Enum):
    """Verbindungsstatus."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    AUTHENTICATING = "authenticating"
    RATE_LIMITED = "rate_limited"


class ERPEntity(str, Enum):
    """Synchronisierbare Entitäten."""
    CUSTOMER = "customer"  # Kunden
    SUPPLIER = "supplier"  # Lieferanten
    INVOICE = "invoice"  # Rechnungen
    PAYMENT = "payment"  # Zahlungen
    PRODUCT = "product"  # Produkte
    DOCUMENT = "document"  # Dokumente
    ORDER = "order"  # Bestellungen


@dataclass
class ERPConnectionConfig:
    """Konfiguration für ERP-Verbindung."""

    # Identifikation
    id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    erp_type: str = "odoo"
    name: str = ""

    # Verbindungsdetails
    url: str = ""
    database: str = ""
    username: str = ""
    api_key: str = ""  # Wird verschlüsselt gespeichert

    # Odoo-Multi-Company: Wenn gesetzt, injiziert der OdooConnector bei jedem
    # Call einen Company-Context (allowed_company_ids + company_id).
    # None = heutiges Verhalten (kein Context-Zwang, alle Companies des Users).
    odoo_company_id: Optional[int] = None

    # Sync-Einstellungen
    sync_direction: ERPSyncDirection = ERPSyncDirection.BIDIRECTIONAL
    sync_interval_minutes: int = 15
    enabled_entities: List[ERPEntity] = field(default_factory=lambda: [
        ERPEntity.CUSTOMER,
        ERPEntity.SUPPLIER,
        ERPEntity.INVOICE,
    ])

    # Rate Limiting
    max_requests_per_minute: int = 60
    batch_size: int = 100

    # Retry-Einstellungen
    max_retries: int = 3
    retry_delay_seconds: int = 5

    # Timeouts
    connect_timeout_seconds: int = 30
    read_timeout_seconds: int = 60

    # Metadaten
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    is_active: bool = True


@dataclass
class ERPSyncResult:
    """Ergebnis einer Synchronisation."""

    entity: ERPEntity
    direction: ERPSyncDirection
    success: bool

    # Statistiken
    records_synced: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_deleted: int = 0
    records_failed: int = 0

    # Konflikte
    conflicts_detected: int = 0
    conflicts_resolved: int = 0

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Details
    error_message: Optional[str] = None
    failed_records: List[Dict[str, Any]] = field(default_factory=list)
    sync_id: Optional[str] = None

    # Die tatsaechlichen Datensätze (für _fetch_remote)
    records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "entity": self.entity.value,
            "direction": self.direction.value,
            "success": self.success,
            "records_synced": self.records_synced,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_deleted": self.records_deleted,
            "records_failed": self.records_failed,
            "conflicts_detected": self.conflicts_detected,
            "conflicts_resolved": self.conflicts_resolved,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "sync_id": self.sync_id,
        }


@dataclass
class ERPConflict:
    """Konflikt bei der Synchronisation."""

    id: str
    entity: ERPEntity
    local_id: str
    remote_id: str

    local_data: Dict[str, Any] = field(default_factory=dict)
    remote_data: Dict[str, Any] = field(default_factory=dict)

    local_modified_at: Optional[datetime] = None
    remote_modified_at: Optional[datetime] = None

    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None  # "local_wins", "remote_wins", "merged"

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "entity": self.entity.value,
            "local_id": self.local_id,
            "remote_id": self.remote_id,
            "local_data": self.local_data,
            "remote_data": self.remote_data,
            "local_modified_at": self.local_modified_at.isoformat() if self.local_modified_at else None,
            "remote_modified_at": self.remote_modified_at.isoformat() if self.remote_modified_at else None,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution,
        }


T = TypeVar("T")


class ERPConnector(ABC, Generic[T]):
    """
    Abstrakte Basisklasse für ERP-Connectoren.

    Implementierungen:
    - OdooConnector: Odoo ERP (XML-RPC API)
    - LexwareConnector: Lexware (CSV-basiert, geplant)
    - SAPConnector: SAP Business One (optional, später)

    Usage:
        config = ERPConnectionConfig(
            url="https://odoo.example.com",
            database="mydb",
            username="admin",
            api_key="secret"
        )
        connector = OdooConnector(config)

        if await connector.test_connection():
            result = await connector.sync_customers(direction=ERPSyncDirection.PULL)
            print(f"Synced {result.records_synced} customers")
    """

    def __init__(self, config: ERPConnectionConfig) -> None:
        """Initialisiert den Connector."""
        self.config = config
        self._status = ERPConnectionStatus.DISCONNECTED
        self._last_error: Optional[str] = None
        self._request_count = 0
        self._rate_limit_reset: Optional[datetime] = None
        self._rate_limit_lock = threading.Lock()  # Thread-Safety für Rate Limiting

        logger.info(
            "erp_connector_initialized",
            erp_type=config.erp_type,
            url=config.url,
            database=config.database,
        )

    @property
    def status(self) -> ERPConnectionStatus:
        """Gibt den aktuellen Verbindungsstatus zurück."""
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        """Gibt die letzte Fehlermeldung zurück."""
        return self._last_error

    @property
    def erp_type(self) -> str:
        """Gibt den ERP-Typ zurück."""
        return self.config.erp_type

    # ==========================================================================
    # Abstract Methods - Müssen von Subklassen implementiert werden
    # ==========================================================================

    @abstractmethod
    async def connect(self) -> bool:
        """
        Stellt Verbindung zum ERP-System her.

        Returns:
            True wenn erfolgreich, False sonst
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Trennt die Verbindung zum ERP-System."""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Testet die Verbindung zum ERP-System.

        Returns:
            True wenn Verbindung funktioniert
        """
        pass

    @abstractmethod
    async def get_version(self) -> str:
        """
        Gibt die Version des ERP-Systems zurück.

        Returns:
            Versionsstring
        """
        pass

    # ==========================================================================
    # Customer Sync
    # ==========================================================================

    @abstractmethod
    async def sync_customers(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """
        Synchronisiert Kunden.

        Args:
            direction: Sync-Richtung
            since: Nur Änderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            Sync-Ergebnis
        """
        pass

    @abstractmethod
    async def get_customer(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """
        Holt einen einzelnen Kunden aus dem ERP.

        Args:
            erp_id: ID im ERP-System

        Returns:
            Kundendaten oder None
        """
        pass

    @abstractmethod
    async def create_customer(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Erstellt einen Kunden im ERP.

        Args:
            data: Kundendaten

        Returns:
            ERP-ID des erstellten Kunden oder None
        """
        pass

    @abstractmethod
    async def update_customer(self, erp_id: str, data: Dict[str, Any]) -> bool:
        """
        Aktualisiert einen Kunden im ERP.

        Args:
            erp_id: ID im ERP-System
            data: Neue Daten

        Returns:
            True wenn erfolgreich
        """
        pass

    # ==========================================================================
    # Supplier Sync
    # ==========================================================================

    @abstractmethod
    async def sync_suppliers(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """
        Synchronisiert Lieferanten.

        Args:
            direction: Sync-Richtung
            since: Nur Änderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            Sync-Ergebnis
        """
        pass

    @abstractmethod
    async def get_supplier(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt einen Lieferanten aus dem ERP."""
        pass

    @abstractmethod
    async def create_supplier(self, data: Dict[str, Any]) -> Optional[str]:
        """Erstellt einen Lieferanten im ERP."""
        pass

    @abstractmethod
    async def update_supplier(self, erp_id: str, data: Dict[str, Any]) -> bool:
        """Aktualisiert einen Lieferanten im ERP."""
        pass

    # ==========================================================================
    # Invoice Sync
    # ==========================================================================

    @abstractmethod
    async def sync_invoices(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """
        Synchronisiert Rechnungen.

        Args:
            direction: Sync-Richtung
            since: Nur Änderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            Sync-Ergebnis
        """
        pass

    @abstractmethod
    async def get_invoice(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt eine Rechnung aus dem ERP."""
        pass

    @abstractmethod
    async def update_payment_status(
        self,
        erp_id: str,
        status: str,
        payment_date: Optional[datetime] = None,
        amount: Optional[float] = None,
    ) -> bool:
        """
        Aktualisiert den Zahlungsstatus einer Rechnung.

        Args:
            erp_id: Rechnungs-ID im ERP
            status: Neuer Status (paid, partial, unpaid)
            payment_date: Zahlungsdatum
            amount: Gezahlter Betrag

        Returns:
            True wenn erfolgreich
        """
        pass

    # ==========================================================================
    # Document Attachment
    # ==========================================================================

    @abstractmethod
    async def attach_document(
        self,
        entity: ERPEntity,
        erp_id: str,
        document_data: bytes,
        filename: str,
        mime_type: str,
    ) -> bool:
        """
        Haengt ein Dokument an eine ERP-Entität an.

        Args:
            entity: Entitätstyp (INVOICE, CUSTOMER, etc.)
            erp_id: ID der Entität im ERP
            document_data: Dokumentinhalt als Bytes
            filename: Dateiname
            mime_type: MIME-Typ

        Returns:
            True wenn erfolgreich
        """
        pass

    @abstractmethod
    async def get_attachments(
        self,
        entity: ERPEntity,
        erp_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Holt Anhaenge einer ERP-Entität.

        Args:
            entity: Entitätstyp
            erp_id: ID der Entität

        Returns:
            Liste der Anhaenge mit Metadaten
        """
        pass

    # ==========================================================================
    # Conflict Handling
    # ==========================================================================

    async def detect_conflicts(
        self,
        entity: ERPEntity,
        local_records: List[Dict[str, Any]],
        remote_records: List[Dict[str, Any]],
    ) -> List[ERPConflict]:
        """
        Erkennt Konflikte zwischen lokalen und Remote-Datensätzen.

        Args:
            entity: Entitätstyp
            local_records: Lokale Datensätze
            remote_records: Remote-Datensätze

        Returns:
            Liste erkannter Konflikte
        """
        conflicts: List[ERPConflict] = []

        # Build lookup by erp_id
        remote_by_id = {
            str(r.get("id") or r.get("erp_id")): r
            for r in remote_records
        }

        for local in local_records:
            local_erp_id = str(local.get("erp_id", ""))
            if not local_erp_id:
                continue

            remote = remote_by_id.get(local_erp_id)
            if not remote:
                continue

            # Compare modification times
            local_modified = local.get("updated_at") or local.get("write_date")
            remote_modified = remote.get("write_date") or remote.get("updated_at")

            # Parse dates if strings
            if isinstance(local_modified, str):
                try:
                    local_modified = datetime.fromisoformat(local_modified.replace("Z", "+00:00"))
                except ValueError:
                    local_modified = None

            if isinstance(remote_modified, str):
                try:
                    remote_modified = datetime.fromisoformat(remote_modified.replace("Z", "+00:00"))
                except ValueError:
                    remote_modified = None

            # Check for conflict (both modified after last sync)
            if local_modified and remote_modified:
                last_sync = self.config.last_sync_at
                if last_sync:
                    if local_modified > last_sync and remote_modified > last_sync:
                        # Conflict detected
                        import uuid
                        conflict = ERPConflict(
                            id=str(uuid.uuid4()),
                            entity=entity,
                            local_id=str(local.get("id", "")),
                            remote_id=local_erp_id,
                            local_data=local,
                            remote_data=remote,
                            local_modified_at=local_modified if isinstance(local_modified, datetime) else None,
                            remote_modified_at=remote_modified if isinstance(remote_modified, datetime) else None,
                        )
                        conflicts.append(conflict)

                        logger.warning(
                            "erp_conflict_detected",
                            entity=entity.value,
                            local_id=conflict.local_id,
                            remote_id=conflict.remote_id,
                        )

        return conflicts

    async def resolve_conflict(
        self,
        conflict: ERPConflict,
        resolution: str,
    ) -> bool:
        """
        Loest einen Konflikt auf.

        Args:
            conflict: Der zu loesende Konflikt
            resolution: Aufloesung ("local_wins", "remote_wins", "merged")

        Returns:
            True wenn erfolgreich
        """
        if resolution not in ("local_wins", "remote_wins", "merged"):
            logger.error(
                "erp_conflict_invalid_resolution",
                conflict_id=conflict.id,
                resolution=resolution,
            )
            return False

        conflict.resolved_at = utc_now()
        conflict.resolution = resolution

        logger.info(
            "erp_conflict_resolved",
            conflict_id=conflict.id,
            entity=conflict.entity.value,
            resolution=resolution,
        )

        return True

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _check_rate_limit(self) -> bool:
        """
        Prüft ob Rate Limit erreicht ist (Thread-Safe).

        Returns:
            True wenn Request erlaubt
        """
        with self._rate_limit_lock:
            now = utc_now()

            # Reset counter if minute passed
            if self._rate_limit_reset and now > self._rate_limit_reset:
                self._request_count = 0
                self._rate_limit_reset = None

            if self._request_count >= self.config.max_requests_per_minute:
                self._status = ERPConnectionStatus.RATE_LIMITED
                logger.warning(
                    "erp_rate_limit_reached",
                    erp_type=self.erp_type,
                    requests=self._request_count,
                    limit=self.config.max_requests_per_minute,
                )
                return False

            # Initialize reset time
            if self._rate_limit_reset is None:
                from datetime import timedelta
                self._rate_limit_reset = now + timedelta(minutes=1)

            self._request_count += 1
            return True

    def _create_sync_result(
        self,
        entity: ERPEntity,
        direction: ERPSyncDirection,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> ERPSyncResult:
        """Erstellt ein leeres Sync-Ergebnis."""
        import uuid
        return ERPSyncResult(
            entity=entity,
            direction=direction,
            success=success,
            started_at=utc_now(),
            error_message=error_message,
            sync_id=str(uuid.uuid4()),
        )

    def _complete_sync_result(self, result: ERPSyncResult) -> ERPSyncResult:
        """Vervollständigt das Sync-Ergebnis mit Timing."""
        result.completed_at = utc_now()
        if result.started_at:
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()
        return result
