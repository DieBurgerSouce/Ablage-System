# -*- coding: utf-8 -*-
"""
Lexware REST API Connector.

Enterprise-Level Integration mit Lexware Office/Buchhaltung:
- REST API v1 Client
- Bidirektionale Synchronisation
- Webhook-Handler fuer Real-time Updates
- Change-Tracking und Delta-Sync

Feinpoliert und durchdacht - Vollstaendige Lexware-Integration.

API Dokumentation: https://developers.lexware.de/
"""

import asyncio
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

import httpx
import structlog

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.erp.base_connector import (

    ERPConnectionConfig,
    ERPConnectionStatus,
    ERPConnector,
    ERPEntity,
    ERPSyncDirection,
    ERPSyncResult,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Lexware-spezifische Konfiguration
# =============================================================================


class LexwareAPIVersion(str, Enum):
    """Unterstuetzte Lexware API Versionen."""

    V1 = "v1"
    V2 = "v2"  # Noch in Beta


class LexwareEndpoint(str, Enum):
    """Lexware API Endpoints."""

    # Auth
    AUTH_TOKEN = "/auth/token"
    AUTH_REFRESH = "/auth/refresh"

    # Kontakte
    CONTACTS = "/contacts"
    CONTACTS_BY_ID = "/contacts/{id}"

    # Kunden
    CUSTOMERS = "/customers"
    CUSTOMERS_BY_ID = "/customers/{id}"

    # Lieferanten
    SUPPLIERS = "/vendors"
    SUPPLIERS_BY_ID = "/vendors/{id}"

    # Rechnungen
    INVOICES = "/invoices"
    INVOICES_BY_ID = "/invoices/{id}"
    INVOICES_PAYMENTS = "/invoices/{id}/payments"

    # Artikel
    PRODUCTS = "/products"
    PRODUCTS_BY_ID = "/products/{id}"

    # Dokumente
    DOCUMENTS = "/documents"
    DOCUMENTS_BY_ID = "/documents/{id}"
    DOCUMENTS_DOWNLOAD = "/documents/{id}/download"
    DOCUMENTS_UPLOAD = "/documents/upload"

    # Webhooks
    WEBHOOKS = "/webhooks"
    WEBHOOKS_BY_ID = "/webhooks/{id}"

    # Metadaten
    VERSION = "/version"
    RATE_LIMIT = "/rate-limit"


@dataclass
class LexwareConnectionConfig(ERPConnectionConfig):
    """Lexware-spezifische Konfiguration."""

    # OAuth2 Credentials
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""

    # Tokens
    access_token: str = ""
    refresh_token: str = ""
    token_expires_at: Optional[datetime] = None

    # Lexware-spezifisch
    api_version: LexwareAPIVersion = LexwareAPIVersion.V1
    organization_id: str = ""  # Mandant
    environment: str = "production"  # production, sandbox

    # Webhook-Einstellungen
    webhook_secret: str = ""
    webhook_url: str = ""
    subscribed_events: List[str] = field(default_factory=lambda: [
        "contact.created",
        "contact.updated",
        "invoice.created",
        "invoice.updated",
        "invoice.paid",
    ])

    # Delta-Sync
    last_sync_timestamps: Dict[str, datetime] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Setze Standard-Werte."""
        self.erp_type = "lexware"
        if not self.url:
            if self.environment == "sandbox":
                self.url = "https://api.sandbox.lexware.de"
            else:
                self.url = "https://api.lexware.de"


@dataclass
class LexwareWebhookEvent:
    """Lexware Webhook Event."""

    id: str
    event_type: str
    resource_type: str
    resource_id: str
    organization_id: str
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "LexwareWebhookEvent":
        """Erstellt Event aus Webhook-Payload."""
        timestamp_str = payload.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            timestamp = utc_now()

        return cls(
            id=payload.get("id", ""),
            event_type=payload.get("event", ""),
            resource_type=payload.get("resource_type", ""),
            resource_id=payload.get("resource_id", ""),
            organization_id=payload.get("organization_id", ""),
            timestamp=timestamp,
            data=payload.get("data", {}),
        )


@dataclass
class LexwareSyncState:
    """Sync-Status fuer Change-Tracking."""

    entity: ERPEntity
    last_sync_at: Optional[datetime] = None
    last_modified_at: Optional[datetime] = None
    sync_cursor: Optional[str] = None
    synced_ids: Set[str] = field(default_factory=set)
    pending_changes: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# Lexware API Client
# =============================================================================


class LexwareConnector(ERPConnector[LexwareConnectionConfig]):
    """
    Lexware REST API Connector.

    Features:
    - OAuth2 Authentifizierung mit Token-Refresh
    - Bidirektionale Synchronisation (Push/Pull)
    - Delta-Sync fuer effiziente Updates
    - Webhook-Handler fuer Real-time Events
    - Retry-Logik und Rate-Limiting
    - Offline-Queue fuer fehlgeschlagene Requests

    Usage:
        config = LexwareConnectionConfig(
            client_id="your-client-id",
            client_secret="your-secret",
            organization_id="mandant-123",
        )
        connector = LexwareConnector(config)

        if await connector.connect():
            result = await connector.sync_customers()
            print(f"Synced {result.records_synced} customers")
    """

    def __init__(self, config: LexwareConnectionConfig) -> None:
        """Initialisiert den Lexware Connector."""
        super().__init__(config)
        self.config: LexwareConnectionConfig = config
        self._client: Optional[httpx.AsyncClient] = None
        self._sync_states: Dict[ERPEntity, LexwareSyncState] = {}
        self._offline_queue: List[Dict[str, Any]] = []
        self._webhook_handlers: Dict[str, List[Any]] = {}

    @property
    def base_url(self) -> str:
        """Basis-URL fuer API-Requests."""
        return f"{self.config.url}/{self.config.api_version.value}"

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def connect(self) -> bool:
        """
        Stellt Verbindung zu Lexware her.

        Authentifiziert via OAuth2 und erstellt HTTP-Client.

        Returns:
            True wenn erfolgreich
        """
        try:
            self._status = ERPConnectionStatus.AUTHENTICATING

            # Erstelle HTTP Client
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout_seconds,
                    read=self.config.read_timeout_seconds,
                    write=30.0,
                ),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-Organization-Id": self.config.organization_id,
                },
            )

            # Pruefe ob Token vorhanden und gueltig
            if self.config.access_token and self._is_token_valid():
                self._client.headers["Authorization"] = f"Bearer {self.config.access_token}"
                self._status = ERPConnectionStatus.CONNECTED
                logger.info(
                    "lexware_connected_existing_token",
                    organization_id=self.config.organization_id,
                )
                return True

            # Hole neuen Token
            if await self._authenticate():
                self._status = ERPConnectionStatus.CONNECTED
                logger.info(
                    "lexware_connected",
                    organization_id=self.config.organization_id,
                )
                return True

            self._status = ERPConnectionStatus.ERROR
            return False

        except Exception as e:
            self._status = ERPConnectionStatus.ERROR
            self._last_error = safe_error_detail(e, "Lexware")
            logger.error(
                "lexware_connection_failed",
                **safe_error_log(e),
                organization_id=self.config.organization_id,
            )
            return False

    async def disconnect(self) -> None:
        """Trennt die Verbindung zu Lexware."""
        if self._client:
            await self._client.aclose()
            self._client = None

        self._status = ERPConnectionStatus.DISCONNECTED
        logger.info(
            "lexware_disconnected",
            organization_id=self.config.organization_id,
        )

    async def test_connection(self) -> bool:
        """
        Testet die Verbindung zu Lexware.

        Returns:
            True wenn Verbindung funktioniert
        """
        try:
            if not self._client or self._status != ERPConnectionStatus.CONNECTED:
                return False

            response = await self._make_request("GET", LexwareEndpoint.VERSION.value)
            return response is not None

        except Exception as e:
            logger.error("lexware_connection_test_failed", **safe_error_log(e))
            return False

    async def get_version(self) -> str:
        """
        Gibt die Lexware API Version zurueck.

        Returns:
            Versionsstring
        """
        try:
            response = await self._make_request("GET", LexwareEndpoint.VERSION.value)
            if response:
                return response.get("version", "unknown")
            return "unknown"
        except Exception:
            return "unknown"

    # =========================================================================
    # Authentication
    # =========================================================================

    def _is_token_valid(self) -> bool:
        """Prueft ob Access Token noch gueltig ist."""
        if not self.config.token_expires_at:
            return False

        # 5 Minuten Puffer
        buffer = timedelta(minutes=5)
        return utc_now() < (self.config.token_expires_at - buffer)

    async def _authenticate(self) -> bool:
        """
        Authentifiziert via OAuth2 Client Credentials.

        Returns:
            True wenn erfolgreich
        """
        try:
            if not self._client:
                return False

            # Client Credentials Grant
            auth_url = f"{self.config.url}{LexwareEndpoint.AUTH_TOKEN.value}"
            response = await self._client.post(
                auth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "scope": "contacts:read contacts:write invoices:read invoices:write",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                logger.error(
                    "lexware_auth_failed",
                    status_code=response.status_code,
                    response=response.text[:200],
                )
                return False

            data = response.json()
            self.config.access_token = data.get("access_token", "")
            self.config.refresh_token = data.get("refresh_token", "")

            # Berechne Ablaufzeit
            expires_in = data.get("expires_in", 3600)
            self.config.token_expires_at = utc_now() + timedelta(seconds=expires_in)

            # Setze Header
            self._client.headers["Authorization"] = f"Bearer {self.config.access_token}"

            logger.info(
                "lexware_authenticated",
                expires_in=expires_in,
                organization_id=self.config.organization_id,
            )
            return True

        except Exception as e:
            logger.error("lexware_auth_error", **safe_error_log(e))
            return False

    async def _refresh_token(self) -> bool:
        """
        Erneuert den Access Token via Refresh Token.

        Returns:
            True wenn erfolgreich
        """
        try:
            if not self._client or not self.config.refresh_token:
                return await self._authenticate()

            auth_url = f"{self.config.url}{LexwareEndpoint.AUTH_REFRESH.value}"
            response = await self._client.post(
                auth_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.refresh_token,
                    "client_id": self.config.client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                # Refresh fehlgeschlagen, versuche neue Auth
                return await self._authenticate()

            data = response.json()
            self.config.access_token = data.get("access_token", "")
            self.config.refresh_token = data.get("refresh_token", self.config.refresh_token)

            expires_in = data.get("expires_in", 3600)
            self.config.token_expires_at = utc_now() + timedelta(seconds=expires_in)

            self._client.headers["Authorization"] = f"Bearer {self.config.access_token}"

            logger.info("lexware_token_refreshed", expires_in=expires_in)
            return True

        except Exception as e:
            logger.error("lexware_refresh_token_error", **safe_error_log(e))
            return await self._authenticate()

    # =========================================================================
    # HTTP Request Handler
    # =========================================================================

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Fuehrt API-Request aus mit Retry-Logik.

        Args:
            method: HTTP Method (GET, POST, PUT, DELETE)
            endpoint: API Endpoint
            data: Request Body
            params: Query Parameter
            retry_count: Aktueller Retry-Zaehler

        Returns:
            Response als Dictionary oder None bei Fehler
        """
        if not self._client:
            logger.error("lexware_no_client")
            return None

        # Rate Limit pruefen
        if not self._check_rate_limit():
            if retry_count < self.config.max_retries:
                await asyncio.sleep(60)  # Warte auf Reset
                return await self._make_request(
                    method, endpoint, data, params, retry_count + 1
                )
            return None

        # Token-Refresh wenn noetig
        if not self._is_token_valid():
            if not await self._refresh_token():
                return None

        url = f"{self.base_url}{endpoint}"

        try:
            if method == "GET":
                response = await self._client.get(url, params=params)
            elif method == "POST":
                response = await self._client.post(url, json=data, params=params)
            elif method == "PUT":
                response = await self._client.put(url, json=data, params=params)
            elif method == "PATCH":
                response = await self._client.patch(url, json=data, params=params)
            elif method == "DELETE":
                response = await self._client.delete(url, params=params)
            else:
                logger.error("lexware_invalid_method", method=method)
                return None

            # Handle Response
            if response.status_code == 429:
                # Rate Limited
                retry_after = int(response.headers.get("Retry-After", "60"))
                logger.warning(
                    "lexware_rate_limited",
                    retry_after=retry_after,
                    endpoint=endpoint,
                )
                if retry_count < self.config.max_retries:
                    await asyncio.sleep(retry_after)
                    return await self._make_request(
                        method, endpoint, data, params, retry_count + 1
                    )
                return None

            if response.status_code == 401:
                # Unauthorized - Token erneuern
                if await self._refresh_token():
                    return await self._make_request(
                        method, endpoint, data, params, retry_count + 1
                    )
                return None

            if response.status_code >= 400:
                logger.error(
                    "lexware_api_error",
                    status_code=response.status_code,
                    endpoint=endpoint,
                    response=response.text[:500],
                )
                return None

            # Erfolgreich
            if response.status_code == 204:
                return {}

            return response.json()

        except httpx.TimeoutException:
            logger.warning(
                "lexware_timeout",
                endpoint=endpoint,
                retry_count=retry_count,
            )
            if retry_count < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay_seconds)
                return await self._make_request(
                    method, endpoint, data, params, retry_count + 1
                )
            return None

        except Exception as e:
            logger.error(
                "lexware_request_error",
                endpoint=endpoint,
                **safe_error_log(e),
            )
            # Add to offline queue for later retry
            self._offline_queue.append({
                "method": method,
                "endpoint": endpoint,
                "data": data,
                "params": params,
                "timestamp": utc_now().isoformat(),
            })
            return None

    # =========================================================================
    # Customer Sync
    # =========================================================================

    async def sync_customers(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """
        Synchronisiert Kunden mit Lexware.

        Args:
            direction: Sync-Richtung
            since: Nur Aenderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            Sync-Ergebnis
        """
        result = self._create_sync_result(ERPEntity.CUSTOMER, direction)
        batch_size = batch_size or self.config.batch_size

        try:
            if direction in (ERPSyncDirection.PULL, ERPSyncDirection.BIDIRECTIONAL):
                # Pull from Lexware
                pull_result = await self._pull_customers(since, batch_size)
                result.records_synced += pull_result.records_synced
                result.records_created += pull_result.records_created
                result.records_updated += pull_result.records_updated
                result.records = pull_result.records

            if direction in (ERPSyncDirection.PUSH, ERPSyncDirection.BIDIRECTIONAL):
                # Push to Lexware
                push_result = await self._push_customers(since, batch_size)
                result.records_synced += push_result.records_synced
                result.records_created += push_result.records_created
                result.records_updated += push_result.records_updated

            # Update sync state
            self._update_sync_state(ERPEntity.CUSTOMER)

            result.success = True

        except Exception as e:
            result.success = False
            result.error_message = safe_error_detail(e, "Lexware")
            logger.error(
                "lexware_sync_customers_error",
                **safe_error_log(e),
                direction=direction.value,
            )

        return self._complete_sync_result(result)

    async def _pull_customers(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> ERPSyncResult:
        """Holt Kunden von Lexware."""
        result = self._create_sync_result(ERPEntity.CUSTOMER, ERPSyncDirection.PULL)
        result.records = []

        params: Dict[str, Any] = {
            "limit": batch_size,
            "offset": 0,
            "sort": "updated_at:desc",
        }

        if since:
            params["updated_after"] = since.isoformat()

        # Paginierung
        while True:
            response = await self._make_request(
                "GET",
                LexwareEndpoint.CUSTOMERS.value,
                params=params,
            )

            if not response:
                break

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                customer_data = self._map_lexware_customer(item)
                result.records.append(customer_data)
                result.records_synced += 1

            # Naechste Seite
            if len(items) < batch_size:
                break
            params["offset"] += batch_size

        logger.info(
            "lexware_pulled_customers",
            count=result.records_synced,
            since=since.isoformat() if since else None,
        )

        return result

    async def _push_customers(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> ERPSyncResult:
        """Pusht Kunden zu Lexware."""
        result = self._create_sync_result(ERPEntity.CUSTOMER, ERPSyncDirection.PUSH)

        # Hole lokale Kunden mit Aenderungen
        sync_state = self._sync_states.get(ERPEntity.CUSTOMER)
        pending = sync_state.pending_changes if sync_state else []

        for change in pending[:batch_size]:
            customer_id = change.get("id")
            data = self._map_to_lexware_customer(change.get("data", {}))

            if change.get("operation") == "create":
                erp_id = await self.create_customer(data)
                if erp_id:
                    result.records_created += 1
                    result.records_synced += 1
            elif change.get("operation") == "update":
                erp_id = change.get("erp_id")
                if erp_id and await self.update_customer(erp_id, data):
                    result.records_updated += 1
                    result.records_synced += 1

        logger.info(
            "lexware_pushed_customers",
            created=result.records_created,
            updated=result.records_updated,
        )

        return result

    def _map_lexware_customer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mappt Lexware-Kundendaten auf internes Format."""
        addresses = data.get("addresses", [{}])
        primary_address = addresses[0] if addresses else {}

        contacts = data.get("contacts", [{}])
        primary_contact = contacts[0] if contacts else {}

        return {
            "erp_id": str(data.get("id", "")),
            "customer_number": data.get("customer_number", ""),
            "matchcode": data.get("matchcode", ""),
            "name": data.get("company_name") or data.get("name", ""),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "email": primary_contact.get("email", ""),
            "phone": primary_contact.get("phone", ""),
            "street": primary_address.get("street", ""),
            "house_number": primary_address.get("house_number", ""),
            "zip_code": primary_address.get("zip_code", ""),
            "city": primary_address.get("city", ""),
            "country": primary_address.get("country", "DE"),
            "vat_id": data.get("vat_id", ""),
            "iban": data.get("bank_account", {}).get("iban", ""),
            "bic": data.get("bank_account", {}).get("bic", ""),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def _map_to_lexware_customer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mappt internes Format auf Lexware-Kundendaten."""
        return {
            "customer_number": data.get("customer_number", ""),
            "matchcode": data.get("matchcode", ""),
            "company_name": data.get("name", ""),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "vat_id": data.get("vat_id", ""),
            "addresses": [{
                "street": data.get("street", ""),
                "house_number": data.get("house_number", ""),
                "zip_code": data.get("zip_code", ""),
                "city": data.get("city", ""),
                "country": data.get("country", "DE"),
                "is_primary": True,
            }],
            "contacts": [{
                "email": data.get("email", ""),
                "phone": data.get("phone", ""),
                "is_primary": True,
            }],
            "bank_account": {
                "iban": data.get("iban", ""),
                "bic": data.get("bic", ""),
            },
        }

    async def get_customer(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt einen Kunden aus Lexware."""
        # Validate erp_id
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            logger.warning("lexware_invalid_customer_id", erp_id=erp_id[:20])
            return None

        endpoint = LexwareEndpoint.CUSTOMERS_BY_ID.value.format(id=erp_id)
        response = await self._make_request("GET", endpoint)

        if response:
            return self._map_lexware_customer(response)
        return None

    async def create_customer(self, data: Dict[str, Any]) -> Optional[str]:
        """Erstellt einen Kunden in Lexware."""
        response = await self._make_request(
            "POST",
            LexwareEndpoint.CUSTOMERS.value,
            data=data,
        )

        if response:
            return str(response.get("id", ""))
        return None

    async def update_customer(self, erp_id: str, data: Dict[str, Any]) -> bool:
        """Aktualisiert einen Kunden in Lexware."""
        # Validate erp_id
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            logger.warning("lexware_invalid_customer_id", erp_id=erp_id[:20])
            return False

        endpoint = LexwareEndpoint.CUSTOMERS_BY_ID.value.format(id=erp_id)
        response = await self._make_request("PATCH", endpoint, data=data)
        return response is not None

    # =========================================================================
    # Supplier Sync
    # =========================================================================

    async def sync_suppliers(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """Synchronisiert Lieferanten mit Lexware."""
        result = self._create_sync_result(ERPEntity.SUPPLIER, direction)
        batch_size = batch_size or self.config.batch_size

        try:
            if direction in (ERPSyncDirection.PULL, ERPSyncDirection.BIDIRECTIONAL):
                pull_result = await self._pull_suppliers(since, batch_size)
                result.records_synced += pull_result.records_synced
                result.records_created += pull_result.records_created
                result.records_updated += pull_result.records_updated
                result.records = pull_result.records

            if direction in (ERPSyncDirection.PUSH, ERPSyncDirection.BIDIRECTIONAL):
                push_result = await self._push_suppliers(since, batch_size)
                result.records_synced += push_result.records_synced
                result.records_created += push_result.records_created
                result.records_updated += push_result.records_updated

            self._update_sync_state(ERPEntity.SUPPLIER)
            result.success = True

        except Exception as e:
            result.success = False
            result.error_message = safe_error_detail(e, "Lexware")
            logger.error(
                "lexware_sync_suppliers_error",
                **safe_error_log(e),
                direction=direction.value,
            )

        return self._complete_sync_result(result)

    async def _pull_suppliers(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> ERPSyncResult:
        """Holt Lieferanten von Lexware."""
        result = self._create_sync_result(ERPEntity.SUPPLIER, ERPSyncDirection.PULL)
        result.records = []

        params: Dict[str, Any] = {
            "limit": batch_size,
            "offset": 0,
            "sort": "updated_at:desc",
        }

        if since:
            params["updated_after"] = since.isoformat()

        while True:
            response = await self._make_request(
                "GET",
                LexwareEndpoint.SUPPLIERS.value,
                params=params,
            )

            if not response:
                break

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                supplier_data = self._map_lexware_supplier(item)
                result.records.append(supplier_data)
                result.records_synced += 1

            if len(items) < batch_size:
                break
            params["offset"] += batch_size

        logger.info(
            "lexware_pulled_suppliers",
            count=result.records_synced,
            since=since.isoformat() if since else None,
        )

        return result

    async def _push_suppliers(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> ERPSyncResult:
        """Pusht Lieferanten zu Lexware."""
        result = self._create_sync_result(ERPEntity.SUPPLIER, ERPSyncDirection.PUSH)

        sync_state = self._sync_states.get(ERPEntity.SUPPLIER)
        pending = sync_state.pending_changes if sync_state else []

        for change in pending[:batch_size]:
            data = self._map_to_lexware_supplier(change.get("data", {}))

            if change.get("operation") == "create":
                erp_id = await self.create_supplier(data)
                if erp_id:
                    result.records_created += 1
                    result.records_synced += 1
            elif change.get("operation") == "update":
                erp_id = change.get("erp_id")
                if erp_id and await self.update_supplier(erp_id, data):
                    result.records_updated += 1
                    result.records_synced += 1

        logger.info(
            "lexware_pushed_suppliers",
            created=result.records_created,
            updated=result.records_updated,
        )

        return result

    def _map_lexware_supplier(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mappt Lexware-Lieferantendaten auf internes Format."""
        addresses = data.get("addresses", [{}])
        primary_address = addresses[0] if addresses else {}

        contacts = data.get("contacts", [{}])
        primary_contact = contacts[0] if contacts else {}

        return {
            "erp_id": str(data.get("id", "")),
            "supplier_number": data.get("vendor_number", ""),
            "matchcode": data.get("matchcode", ""),
            "name": data.get("company_name") or data.get("name", ""),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "email": primary_contact.get("email", ""),
            "phone": primary_contact.get("phone", ""),
            "street": primary_address.get("street", ""),
            "house_number": primary_address.get("house_number", ""),
            "zip_code": primary_address.get("zip_code", ""),
            "city": primary_address.get("city", ""),
            "country": primary_address.get("country", "DE"),
            "vat_id": data.get("vat_id", ""),
            "iban": data.get("bank_account", {}).get("iban", ""),
            "bic": data.get("bank_account", {}).get("bic", ""),
            "creditor_number": data.get("creditor_number", ""),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def _map_to_lexware_supplier(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mappt internes Format auf Lexware-Lieferantendaten."""
        return {
            "vendor_number": data.get("supplier_number", ""),
            "matchcode": data.get("matchcode", ""),
            "company_name": data.get("name", ""),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "vat_id": data.get("vat_id", ""),
            "creditor_number": data.get("creditor_number", ""),
            "addresses": [{
                "street": data.get("street", ""),
                "house_number": data.get("house_number", ""),
                "zip_code": data.get("zip_code", ""),
                "city": data.get("city", ""),
                "country": data.get("country", "DE"),
                "is_primary": True,
            }],
            "contacts": [{
                "email": data.get("email", ""),
                "phone": data.get("phone", ""),
                "is_primary": True,
            }],
            "bank_account": {
                "iban": data.get("iban", ""),
                "bic": data.get("bic", ""),
            },
        }

    async def get_supplier(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt einen Lieferanten aus Lexware."""
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            logger.warning("lexware_invalid_supplier_id", erp_id=erp_id[:20])
            return None

        endpoint = LexwareEndpoint.SUPPLIERS_BY_ID.value.format(id=erp_id)
        response = await self._make_request("GET", endpoint)

        if response:
            return self._map_lexware_supplier(response)
        return None

    async def create_supplier(self, data: Dict[str, Any]) -> Optional[str]:
        """Erstellt einen Lieferanten in Lexware."""
        response = await self._make_request(
            "POST",
            LexwareEndpoint.SUPPLIERS.value,
            data=data,
        )

        if response:
            return str(response.get("id", ""))
        return None

    async def update_supplier(self, erp_id: str, data: Dict[str, Any]) -> bool:
        """Aktualisiert einen Lieferanten in Lexware."""
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            logger.warning("lexware_invalid_supplier_id", erp_id=erp_id[:20])
            return False

        endpoint = LexwareEndpoint.SUPPLIERS_BY_ID.value.format(id=erp_id)
        response = await self._make_request("PATCH", endpoint, data=data)
        return response is not None

    # =========================================================================
    # Invoice Sync
    # =========================================================================

    async def sync_invoices(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """Synchronisiert Rechnungen mit Lexware."""
        result = self._create_sync_result(ERPEntity.INVOICE, direction)
        batch_size = batch_size or self.config.batch_size

        try:
            if direction in (ERPSyncDirection.PULL, ERPSyncDirection.BIDIRECTIONAL):
                pull_result = await self._pull_invoices(since, batch_size)
                result.records_synced += pull_result.records_synced
                result.records_created += pull_result.records_created
                result.records_updated += pull_result.records_updated
                result.records = pull_result.records

            self._update_sync_state(ERPEntity.INVOICE)
            result.success = True

        except Exception as e:
            result.success = False
            result.error_message = safe_error_detail(e, "Lexware")
            logger.error(
                "lexware_sync_invoices_error",
                **safe_error_log(e),
                direction=direction.value,
            )

        return self._complete_sync_result(result)

    async def _pull_invoices(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> ERPSyncResult:
        """Holt Rechnungen von Lexware."""
        result = self._create_sync_result(ERPEntity.INVOICE, ERPSyncDirection.PULL)
        result.records = []

        params: Dict[str, Any] = {
            "limit": batch_size,
            "offset": 0,
            "sort": "invoice_date:desc",
        }

        if since:
            params["updated_after"] = since.isoformat()

        while True:
            response = await self._make_request(
                "GET",
                LexwareEndpoint.INVOICES.value,
                params=params,
            )

            if not response:
                break

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                invoice_data = self._map_lexware_invoice(item)
                result.records.append(invoice_data)
                result.records_synced += 1

            if len(items) < batch_size:
                break
            params["offset"] += batch_size

        logger.info(
            "lexware_pulled_invoices",
            count=result.records_synced,
            since=since.isoformat() if since else None,
        )

        return result

    def _map_lexware_invoice(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mappt Lexware-Rechnungsdaten auf internes Format."""
        return {
            "erp_id": str(data.get("id", "")),
            "invoice_number": data.get("invoice_number", ""),
            "customer_id": str(data.get("customer_id", "")),
            "invoice_date": data.get("invoice_date"),
            "due_date": data.get("due_date"),
            "total_net": data.get("total_net", 0.0),
            "total_gross": data.get("total_gross", 0.0),
            "tax_amount": data.get("tax_amount", 0.0),
            "currency": data.get("currency", "EUR"),
            "status": data.get("status", "draft"),
            "payment_status": data.get("payment_status", "unpaid"),
            "line_items": [
                {
                    "description": item.get("description", ""),
                    "quantity": item.get("quantity", 1),
                    "unit_price": item.get("unit_price", 0.0),
                    "tax_rate": item.get("tax_rate", 19.0),
                    "total": item.get("total", 0.0),
                }
                for item in data.get("line_items", [])
            ],
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    async def get_invoice(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt eine Rechnung aus Lexware."""
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            logger.warning("lexware_invalid_invoice_id", erp_id=erp_id[:20])
            return None

        endpoint = LexwareEndpoint.INVOICES_BY_ID.value.format(id=erp_id)
        response = await self._make_request("GET", endpoint)

        if response:
            return self._map_lexware_invoice(response)
        return None

    async def update_payment_status(
        self,
        erp_id: str,
        status: str,
        payment_date: Optional[datetime] = None,
        amount: Optional[float] = None,
    ) -> bool:
        """Aktualisiert den Zahlungsstatus einer Rechnung."""
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            logger.warning("lexware_invalid_invoice_id", erp_id=erp_id[:20])
            return False

        endpoint = LexwareEndpoint.INVOICES_PAYMENTS.value.format(id=erp_id)
        data: Dict[str, Any] = {"status": status}

        if payment_date:
            data["payment_date"] = payment_date.isoformat()
        if amount is not None:
            data["amount"] = amount

        response = await self._make_request("POST", endpoint, data=data)
        return response is not None

    # =========================================================================
    # Document Attachment
    # =========================================================================

    async def attach_document(
        self,
        entity: ERPEntity,
        erp_id: str,
        document_data: bytes,
        filename: str,
        mime_type: str,
    ) -> bool:
        """Haengt ein Dokument an eine Lexware-Entitaet an."""
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            logger.warning("lexware_invalid_entity_id", erp_id=erp_id[:20])
            return False

        if not self._client:
            return False

        try:
            import base64

            # Lexware nutzt Base64-encoded Dokumente
            encoded_data = base64.b64encode(document_data).decode("utf-8")

            endpoint = f"{self.base_url}{LexwareEndpoint.DOCUMENTS_UPLOAD.value}"
            payload = {
                "resource_type": entity.value,
                "resource_id": erp_id,
                "filename": filename,
                "mime_type": mime_type,
                "data": encoded_data,
            }

            response = await self._client.post(endpoint, json=payload)
            return response.status_code in (200, 201)

        except Exception as e:
            logger.error(
                "lexware_attach_document_error",
                entity=entity.value,
                erp_id=erp_id,
                **safe_error_log(e),
            )
            return False

    async def get_attachments(
        self,
        entity: ERPEntity,
        erp_id: str,
    ) -> List[Dict[str, Any]]:
        """Holt Anhaenge einer Lexware-Entitaet."""
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", erp_id):
            return []

        params = {
            "resource_type": entity.value,
            "resource_id": erp_id,
        }

        response = await self._make_request(
            "GET",
            LexwareEndpoint.DOCUMENTS.value,
            params=params,
        )

        if response:
            return response.get("items", [])
        return []

    # =========================================================================
    # Webhook Handler
    # =========================================================================

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        """
        Verifiziert die Webhook-Signatur.

        Args:
            payload: Raw Request Body
            signature: X-Lexware-Signature Header

        Returns:
            True wenn Signatur gueltig
        """
        if not self.config.webhook_secret:
            logger.warning("lexware_webhook_no_secret")
            return False

        expected = hmac.new(
            self.config.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected}", signature)

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
    ) -> None:
        """
        Verarbeitet eingehenden Webhook.

        Args:
            payload: Webhook-Payload
        """
        event = LexwareWebhookEvent.from_payload(payload)

        logger.info(
            "lexware_webhook_received",
            event_type=event.event_type,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
        )

        # Dispatch to handlers
        handlers = self._webhook_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "lexware_webhook_handler_error",
                    event_type=event.event_type,
                    **safe_error_log(e),
                )

        # Built-in handling for sync
        if event.event_type.startswith("contact."):
            # Mark customer/supplier for re-sync
            self._invalidate_sync_cache(ERPEntity.CUSTOMER)
            self._invalidate_sync_cache(ERPEntity.SUPPLIER)
        elif event.event_type.startswith("invoice."):
            self._invalidate_sync_cache(ERPEntity.INVOICE)

    def register_webhook_handler(
        self,
        event_type: str,
        handler: Any,
    ) -> None:
        """Registriert einen Webhook-Handler."""
        if event_type not in self._webhook_handlers:
            self._webhook_handlers[event_type] = []
        self._webhook_handlers[event_type].append(handler)

    async def setup_webhooks(self) -> bool:
        """
        Richtet Webhooks in Lexware ein.

        Returns:
            True wenn erfolgreich
        """
        if not self.config.webhook_url:
            logger.warning("lexware_no_webhook_url")
            return False

        try:
            for event_type in self.config.subscribed_events:
                response = await self._make_request(
                    "POST",
                    LexwareEndpoint.WEBHOOKS.value,
                    data={
                        "url": self.config.webhook_url,
                        "events": [event_type],
                        "active": True,
                    },
                )

                if not response:
                    logger.error(
                        "lexware_webhook_setup_failed",
                        event_type=event_type,
                    )
                    return False

            logger.info(
                "lexware_webhooks_configured",
                events=self.config.subscribed_events,
                url=self.config.webhook_url,
            )
            return True

        except Exception as e:
            logger.error("lexware_webhook_setup_error", **safe_error_log(e))
            return False

    # =========================================================================
    # Sync State Management
    # =========================================================================

    def _update_sync_state(self, entity: ERPEntity) -> None:
        """Aktualisiert den Sync-Status."""
        if entity not in self._sync_states:
            self._sync_states[entity] = LexwareSyncState(entity=entity)

        state = self._sync_states[entity]
        state.last_sync_at = utc_now()
        state.pending_changes = []

        # Update config timestamp
        self.config.last_sync_timestamps[entity.value] = state.last_sync_at
        self.config.last_sync_at = state.last_sync_at

    def _invalidate_sync_cache(self, entity: ERPEntity) -> None:
        """Invalidiert den Sync-Cache fuer eine Entitaet."""
        if entity in self._sync_states:
            # Force re-sync on next run
            self._sync_states[entity].last_sync_at = None

    def queue_local_change(
        self,
        entity: ERPEntity,
        operation: str,
        data: Dict[str, Any],
        erp_id: Optional[str] = None,
    ) -> None:
        """
        Fuegt eine lokale Aenderung zur Sync-Queue hinzu.

        Args:
            entity: Entitaetstyp
            operation: create, update, delete
            data: Datensatz
            erp_id: ERP-ID (fuer update/delete)
        """
        if entity not in self._sync_states:
            self._sync_states[entity] = LexwareSyncState(entity=entity)

        self._sync_states[entity].pending_changes.append({
            "operation": operation,
            "data": data,
            "erp_id": erp_id,
            "timestamp": utc_now().isoformat(),
        })

    async def process_offline_queue(self) -> int:
        """
        Verarbeitet die Offline-Queue.

        Returns:
            Anzahl verarbeiteter Requests
        """
        processed = 0

        while self._offline_queue:
            request = self._offline_queue.pop(0)

            response = await self._make_request(
                request["method"],
                request["endpoint"],
                request.get("data"),
                request.get("params"),
            )

            if response is not None:
                processed += 1
            else:
                # Put back if still failing
                self._offline_queue.append(request)
                break

        if processed > 0:
            logger.info("lexware_offline_queue_processed", count=processed)

        return processed


# =============================================================================
# Factory und Singleton
# =============================================================================


_lexware_connector: Optional[LexwareConnector] = None


def get_lexware_connector(
    config: Optional[LexwareConnectionConfig] = None,
) -> Optional[LexwareConnector]:
    """
    Gibt den Lexware Connector zurueck (Singleton).

    Args:
        config: Optionale Konfiguration

    Returns:
        LexwareConnector oder None wenn nicht konfiguriert
    """
    global _lexware_connector

    if config:
        _lexware_connector = LexwareConnector(config)

    if not _lexware_connector:
        # Versuche aus Settings zu laden
        if hasattr(settings, "LEXWARE_CLIENT_ID") and settings.LEXWARE_CLIENT_ID:
            default_config = LexwareConnectionConfig(
                client_id=settings.LEXWARE_CLIENT_ID,
                client_secret=str(settings.LEXWARE_CLIENT_SECRET) if hasattr(settings, "LEXWARE_CLIENT_SECRET") else "",
                organization_id=getattr(settings, "LEXWARE_ORGANIZATION_ID", ""),
                environment=getattr(settings, "LEXWARE_ENVIRONMENT", "production"),
                webhook_url=getattr(settings, "LEXWARE_WEBHOOK_URL", ""),
                webhook_secret=getattr(settings, "LEXWARE_WEBHOOK_SECRET", ""),
            )
            _lexware_connector = LexwareConnector(default_config)

    return _lexware_connector


async def create_lexware_connector_from_db(
    company_id: UUID,
) -> Optional[LexwareConnector]:
    """
    Erstellt Connector aus Datenbank-Konfiguration.

    Liest ERP-Verbindungsdaten aus der ERPConnection-Tabelle und
    erstellt einen vollstaendig konfigurierten LexwareConnector.

    SECURITY:
    - Credentials werden verschluesselt gespeichert (AES-256-GCM)
    - Multi-Tenant Isolation via company_id
    - Keine PII in Logs (CWE-532)

    Args:
        company_id: Company UUID

    Returns:
        LexwareConnector oder None wenn nicht konfiguriert/Fehler
    """
    from app.db.session import async_session_maker
    from app.db.models import ERPConnection
    from app.core.encryption import decrypt_api_key
    from sqlalchemy import select, and_

    async with async_session_maker() as db:
        try:
            # Query ERPConnection fuer Lexware-Konfiguration
            query = select(ERPConnection).where(
                and_(
                    ERPConnection.company_id == company_id,
                    ERPConnection.erp_type == "lexware",
                    ERPConnection.is_active == True,
                )
            )
            result = await db.execute(query)
            connection = result.scalar_one_or_none()

            if not connection:
                logger.info(
                    "lexware_no_connection_configured",
                    company_id=str(company_id)[:8],  # SECURITY: Nur Prefix loggen
                )
                return None

            # Decrypt Credentials
            # SECURITY: AES-256-GCM mit Connection-ID als AAD
            try:
                decrypted_secret = decrypt_api_key(
                    connection.encrypted_api_key,
                    str(connection.id),  # Connection-ID als AAD
                )
            except Exception as e:
                # SECURITY: Keine Crypto-Details loggen (CWE-209)
                logger.error(
                    "lexware_decrypt_credentials_failed",
                    company_id=str(company_id)[:8],
                    error_type=type(e).__name__,
                )
                return None

            # Parse JSONB enabled_entities fuer Extra-Konfiguration
            extra_config = connection.enabled_entities or {}

            # Bestimme Environment aus URL
            environment = "sandbox" if "sandbox" in (connection.url or "").lower() else "production"

            # Erstelle LexwareConnectionConfig aus DB-Werten
            config = LexwareConnectionConfig(
                # OAuth2 Credentials
                client_id=connection.username,  # username speichert client_id
                client_secret=decrypted_secret,

                # API-Verbindung
                url=connection.url,
                environment=environment,
                api_version=LexwareAPIVersion(extra_config.get("api_version", "v1")),

                # Lexware-spezifisch
                organization_id=extra_config.get("organization_id", ""),

                # Webhook-Einstellungen (optional)
                webhook_url=extra_config.get("webhook_url", ""),
                webhook_secret=extra_config.get("webhook_secret", ""),

                # Sync-Einstellungen aus DB
                batch_size=connection.batch_size,
                max_retries=connection.max_retries,
                retry_delay_seconds=connection.retry_delay_seconds,

                # Timeouts
                connect_timeout_seconds=connection.connect_timeout_seconds,
                read_timeout_seconds=connection.read_timeout_seconds,
            )

            # Erstelle Connector
            connector = LexwareConnector(config)

            logger.info(
                "lexware_connector_created_from_db",
                company_id=str(company_id)[:8],  # SECURITY: Nur Prefix
                connection_id=str(connection.id)[:8],
                environment=environment,
            )

            return connector

        except Exception as e:
            # SECURITY: Keine Details loggen (CWE-532)
            logger.error(
                "lexware_connector_from_db_error",
                company_id=str(company_id)[:8],
                error_type=type(e).__name__,
            )
            return None
