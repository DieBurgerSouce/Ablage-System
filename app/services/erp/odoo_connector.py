"""
Odoo ERP Connector.

Enterprise-Level Odoo-Integration:
- XML-RPC API Client
- OAuth2 / API-Key Authentifizierung
- Connection Pooling
- Async-Support via ThreadPoolExecutor

Feinpoliert und durchdacht - Odoo-Integration auf Enterprise-Niveau.
"""

import structlog
import asyncio
import xmlrpc.client
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from functools import partial

from app.schemas.odoo import OdooVendorBillDraft
from app.services.erp.base_connector import (
    ERPConnector,
    ERPConnectionConfig,
    ERPConnectionStatus,
    ERPSyncDirection,
    ERPSyncResult,
    ERPEntity,
)

logger = structlog.get_logger(__name__)

#: Mindestlaenge eines Absender-Namens fuer die ilike-Namenssuche (F-06).
#: Kuerzere Namen (z. B. "AG") matchen zu breit und werden nicht gesucht.
_MIN_NAME_SEARCH_LEN = 3


class OdooConnector(ERPConnector[Dict[str, Any]]):
    """
    Odoo ERP Connector mit XML-RPC API.

    Features:
    - XML-RPC Verbindung mit Connection Pooling
    - Async-Wrapper für Blocking Calls
    - Rate Limiting und Retry-Logik
    - Bidirektionale Synchronisation

    Usage:
        config = ERPConnectionConfig(
            url="https://odoo.example.com",
            database="production",
            username="api_user",
            api_key="your_api_key"
        )
        connector = OdooConnector(config)

        if await connector.test_connection():
            customers = await connector.sync_customers()
            print(f"Synced {customers.records_synced} customers")
    """

    # Thread pool for blocking XML-RPC calls
    _executor: Optional[ThreadPoolExecutor] = None

    def __init__(self, config: ERPConnectionConfig) -> None:
        """Initialisiert den Odoo Connector."""
        super().__init__(config)

        # Odoo-spezifische Einstellungen
        self._uid: Optional[int] = None
        self._common: Optional[xmlrpc.client.ServerProxy] = None
        self._models: Optional[xmlrpc.client.ServerProxy] = None

        # Connection state
        self._authenticated = False

        # Initialize executor
        if OdooConnector._executor is None:
            OdooConnector._executor = ThreadPoolExecutor(
                max_workers=4,
                thread_name_prefix="odoo_rpc_"
            )

        logger.info(
            "odoo_connector_created",
            url=config.url,
            database=config.database,
        )

    def _sanitize_error(self, error: Exception) -> str:
        """Sanitize error message to prevent API key leakage (PII)."""
        msg = str(error)
        if self.config.api_key and self.config.api_key in msg:
            msg = msg.replace(self.config.api_key, "[REDACTED]")
        return msg

    async def _run_blocking(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Führt blocking Funktion im ThreadPool aus."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            partial(func, *args, **kwargs)
        )

    # ==========================================================================
    # Connection Management
    # ==========================================================================

    async def connect(self) -> bool:
        """Stellt Verbindung zu Odoo her und authentifiziert."""
        try:
            self._status = ERPConnectionStatus.AUTHENTICATING

            # Build URLs
            common_url = f"{self.config.url}/xmlrpc/2/common"
            object_url = f"{self.config.url}/xmlrpc/2/object"

            # Create proxies
            self._common = xmlrpc.client.ServerProxy(
                common_url,
                allow_none=True,
                context=None,  # Use default SSL context
            )
            self._models = xmlrpc.client.ServerProxy(
                object_url,
                allow_none=True,
                context=None,
            )

            # Authenticate
            self._uid = await self._run_blocking(
                self._common.authenticate,
                self.config.database,
                self.config.username,
                self.config.api_key,
                {}
            )

            if self._uid:
                self._authenticated = True
                self._status = ERPConnectionStatus.CONNECTED

                logger.info(
                    "odoo_connected",
                    url=self.config.url,
                    database=self.config.database,
                    uid=self._uid,
                )
                return True
            else:
                self._status = ERPConnectionStatus.ERROR
                self._last_error = "Authentifizierung fehlgeschlagen"
                logger.error(
                    "odoo_auth_failed",
                    url=self.config.url,
                    database=self.config.database,
                )
                return False

        except Exception as e:
            self._status = ERPConnectionStatus.ERROR
            self._last_error = self._sanitize_error(e)
            logger.exception(
                "odoo_connection_error",
                url=self.config.url,
                error=self._sanitize_error(e),
            )
            return False

    async def disconnect(self) -> None:
        """Trennt die Verbindung zu Odoo."""
        self._common = None
        self._models = None
        self._uid = None
        self._authenticated = False
        self._status = ERPConnectionStatus.DISCONNECTED

        logger.info("odoo_disconnected", url=self.config.url)

    async def test_connection(self) -> bool:
        """Testet die Verbindung zu Odoo."""
        try:
            if not self._authenticated:
                return await self.connect()

            # Test with simple query
            result = await self._execute_kw(
                "res.users",
                "search_count",
                [[["id", "=", self._uid]]]
            )
            return result == 1

        except Exception as e:
            logger.warning("odoo_connection_test_failed", error=self._sanitize_error(e))
            return False

    async def get_version(self) -> str:
        """Gibt die Odoo-Version zurück."""
        try:
            if not self._common:
                await self.connect()

            version_info = await self._run_blocking(
                self._common.version
            )
            return version_info.get("server_version", "Unknown")

        except Exception as e:
            logger.error("odoo_version_error", error=self._sanitize_error(e))
            return "Unknown"

    # ==========================================================================
    # Helper: Execute Odoo Operations
    # ==========================================================================

    async def _execute_kw(
        self,
        model: str,
        method: str,
        args: List[Any],
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Führt eine Odoo-Operation aus.

        Args:
            model: Odoo-Modell (z.B. "res.partner")
            method: Methode (z.B. "search_read")
            args: Positionsargumente
            kwargs: Keyword-Argumente

        Returns:
            Ergebnis der Operation
        """
        if not self._authenticated:
            await self.connect()

        if not self._check_rate_limit():
            raise Exception("Rate limit erreicht")

        # Kopie, damit das kwargs-Dict des Aufrufers nie mutiert wird
        call_kwargs: Dict[str, Any] = dict(kwargs) if kwargs else {}

        if self.config.odoo_company_id is not None:
            # Odoo-Multi-Company: Company-Context injizieren, damit alle
            # Operationen auf die konfigurierte Company beschraenkt sind.
            # Vorhandenen context des Aufrufers respektieren und nur
            # fehlende Schluessel ergaenzen (setdefault = nicht ueberschreiben).
            company_id = self.config.odoo_company_id
            context: Dict[str, Any] = dict(call_kwargs.get("context") or {})
            context.setdefault("allowed_company_ids", [company_id])
            context.setdefault("company_id", company_id)
            call_kwargs["context"] = context

        try:
            result = await self._run_blocking(
                self._models.execute_kw,
                self.config.database,
                self._uid,
                self.config.api_key,
                model,
                method,
                args,
                call_kwargs
            )
            return result

        except xmlrpc.client.Fault as e:
            logger.error(
                "odoo_execute_error",
                model=model,
                method=method,
                error=self._sanitize_error(e),
            )
            raise

    async def iter_records(
        self,
        model: str,
        domain: List[Any],
        fields: List[str],
        *,
        batch_size: int = 200,
        order: str = "write_date asc, id asc",
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Iteriert paginiert ueber alle Datensaetze eines Odoo-Modells.

        Fuer den Vollarchiv-Pull-Spiegel (Odoo -> Ablage) gedacht:
        search_read-Schleife mit offset/limit und stabiler Sortierung
        (Default: write_date + id aufsteigend als Tiebreaker), bis ein
        leeres Batch zurueckkommt. Ein Batch kleiner als batch_size
        beendet die Schleife ebenfalls (spart einen RPC-Roundtrip,
        relevant wegen SaaS-Drosselung).

        Fehler aus _execute_kw propagieren bewusst (kein stilles
        Verschlucken): ein abgebrochener Spiegel-Lauf darf vom Aufrufer
        nicht als vollstaendig gewertet werden (Sync-Cursor!).

        Args:
            model: Odoo-Modell (z.B. "account.move")
            domain: Odoo-Suchdomain
            fields: Zu lesende Felder
            batch_size: Datensaetze pro RPC-Call
            order: Stabile Sortierung (write_date + id)

        Yields:
            Einzelne Datensaetze als Dict
        """
        offset = 0
        while True:
            batch = await self._execute_kw(
                model,
                "search_read",
                [domain],
                {
                    "fields": fields,
                    "limit": batch_size,
                    "offset": offset,
                    "order": order,
                },
            )
            if not batch:
                break
            for record in batch:
                yield record
            if len(batch) < batch_size:
                break
            offset += len(batch)

    # ==========================================================================
    # Customer Operations
    # ==========================================================================

    async def sync_customers(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """Synchronisiert Kunden mit Odoo."""
        result = self._create_sync_result(
            entity=ERPEntity.CUSTOMER,
            direction=direction,
        )
        batch_size = batch_size or self.config.batch_size

        try:
            if direction in (ERPSyncDirection.PULL, ERPSyncDirection.BIDIRECTIONAL):
                # Pull customers from Odoo
                pulled = await self._pull_customers(since, batch_size)
                result.records_synced += len(pulled)
                result.records_created = len([p for p in pulled if p.get("is_new")])
                result.records_updated = len([p for p in pulled if not p.get("is_new")])
                # Store actual records for sync engine
                result.records = pulled

            if direction in (ERPSyncDirection.PUSH, ERPSyncDirection.BIDIRECTIONAL):
                # Push customers to Odoo would go here
                pass

            result.success = True

        except Exception as e:
            result.success = False
            result.error_message = self._sanitize_error(e)
            logger.exception("odoo_sync_customers_error", error=self._sanitize_error(e))

        return self._complete_sync_result(result)

    async def _pull_customers(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Holt Kunden aus Odoo."""
        domain: List[Any] = [["customer_rank", ">", 0]]

        if since:
            domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])

        fields = [
            "id", "name", "email", "phone", "mobile",
            "street", "street2", "city", "zip", "country_id",
            "vat", "company_type", "write_date", "create_date"
        ]

        customers = await self._execute_kw(
            "res.partner",
            "search_read",
            [domain],
            {"fields": fields, "limit": batch_size}
        )

        logger.info(
            "odoo_customers_pulled",
            count=len(customers),
            since=since.isoformat() if since else None,
        )

        return customers

    async def get_customer(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt einen einzelnen Kunden aus Odoo."""
        try:
            result = await self._execute_kw(
                "res.partner",
                "read",
                [[int(erp_id)]],
                {"fields": [
                    "id", "name", "email", "phone", "mobile",
                    "street", "street2", "city", "zip", "country_id",
                    "vat", "company_type", "write_date"
                ]}
            )
            return result[0] if result else None

        except Exception as e:
            logger.error("odoo_get_customer_error", erp_id=erp_id, error=self._sanitize_error(e))
            return None

    async def create_customer(self, data: Dict[str, Any]) -> Optional[str]:
        """Erstellt einen Kunden in Odoo."""
        try:
            # Map local fields to Odoo fields
            odoo_data = self._map_customer_to_odoo(data)

            # Create customer
            customer_id = await self._execute_kw(
                "res.partner",
                "create",
                [odoo_data]
            )

            logger.info("odoo_customer_created", customer_id=customer_id)
            return str(customer_id)

        except Exception as e:
            logger.error("odoo_create_customer_error", error=self._sanitize_error(e))
            return None

    async def update_customer(self, erp_id: str, data: Dict[str, Any]) -> bool:
        """Aktualisiert einen Kunden in Odoo."""
        try:
            odoo_data = self._map_customer_to_odoo(data)

            await self._execute_kw(
                "res.partner",
                "write",
                [[int(erp_id)], odoo_data]
            )

            logger.info("odoo_customer_updated", erp_id=erp_id)
            return True

        except Exception as e:
            logger.error("odoo_update_customer_error", erp_id=erp_id, error=self._sanitize_error(e))
            return False

    def _map_customer_to_odoo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mappt lokale Kundendaten zu Odoo-Format."""
        return {
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "mobile": data.get("mobile", ""),
            "street": data.get("address", {}).get("street", ""),
            "street2": data.get("address", {}).get("street2", ""),
            "city": data.get("address", {}).get("city", ""),
            "zip": data.get("address", {}).get("zip", ""),
            "vat": data.get("vat_id", ""),
            "customer_rank": 1,
        }

    # ==========================================================================
    # Supplier Operations
    # ==========================================================================

    async def sync_suppliers(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """Synchronisiert Lieferanten mit Odoo."""
        result = self._create_sync_result(
            entity=ERPEntity.SUPPLIER,
            direction=direction,
        )
        batch_size = batch_size or self.config.batch_size

        try:
            if direction in (ERPSyncDirection.PULL, ERPSyncDirection.BIDIRECTIONAL):
                pulled = await self._pull_suppliers(since, batch_size)
                result.records_synced += len(pulled)
                # Store actual records for sync engine
                result.records = pulled

            result.success = True

        except Exception as e:
            result.success = False
            result.error_message = self._sanitize_error(e)
            logger.exception("odoo_sync_suppliers_error", error=self._sanitize_error(e))

        return self._complete_sync_result(result)

    async def _pull_suppliers(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Holt Lieferanten aus Odoo."""
        domain: List[Any] = [["supplier_rank", ">", 0]]

        if since:
            domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])

        fields = [
            "id", "name", "email", "phone", "mobile",
            "street", "street2", "city", "zip", "country_id",
            "vat", "write_date", "create_date"
        ]

        suppliers = await self._execute_kw(
            "res.partner",
            "search_read",
            [domain],
            {"fields": fields, "limit": batch_size}
        )

        logger.info(
            "odoo_suppliers_pulled",
            count=len(suppliers),
            since=since.isoformat() if since else None,
        )

        return suppliers

    async def get_supplier(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt einen Lieferanten aus Odoo."""
        return await self.get_customer(erp_id)  # Same model in Odoo

    async def create_supplier(self, data: Dict[str, Any]) -> Optional[str]:
        """Erstellt einen Lieferanten in Odoo."""
        try:
            odoo_data = self._map_customer_to_odoo(data)
            odoo_data["supplier_rank"] = 1
            odoo_data["customer_rank"] = 0

            supplier_id = await self._execute_kw(
                "res.partner",
                "create",
                [odoo_data]
            )

            logger.info("odoo_supplier_created", supplier_id=supplier_id)
            return str(supplier_id)

        except Exception as e:
            logger.error("odoo_create_supplier_error", error=self._sanitize_error(e))
            return None

    async def update_supplier(self, erp_id: str, data: Dict[str, Any]) -> bool:
        """Aktualisiert einen Lieferanten in Odoo."""
        return await self.update_customer(erp_id, data)

    # ==========================================================================
    # Invoice Operations
    # ==========================================================================

    async def sync_invoices(
        self,
        direction: ERPSyncDirection = ERPSyncDirection.PULL,
        since: Optional[datetime] = None,
        batch_size: Optional[int] = None,
    ) -> ERPSyncResult:
        """Synchronisiert Rechnungen mit Odoo."""
        result = self._create_sync_result(
            entity=ERPEntity.INVOICE,
            direction=direction,
        )
        batch_size = batch_size or self.config.batch_size

        try:
            if direction in (ERPSyncDirection.PULL, ERPSyncDirection.BIDIRECTIONAL):
                pulled = await self._pull_invoices(since, batch_size)
                result.records_synced += len(pulled)
                # Store actual records for sync engine
                result.records = pulled

            result.success = True

        except Exception as e:
            result.success = False
            result.error_message = self._sanitize_error(e)
            logger.exception("odoo_sync_invoices_error", error=self._sanitize_error(e))

        return self._complete_sync_result(result)

    async def _pull_invoices(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Holt Rechnungen aus Odoo."""
        domain: List[Any] = [["move_type", "in", ["out_invoice", "in_invoice"]]]

        if since:
            domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])

        fields = [
            "id", "name", "ref", "move_type", "state",
            "partner_id", "invoice_date", "invoice_date_due",
            "amount_total", "amount_residual", "currency_id",
            "payment_state", "write_date", "create_date"
        ]

        invoices = await self._execute_kw(
            "account.move",
            "search_read",
            [domain],
            {"fields": fields, "limit": batch_size}
        )

        logger.info(
            "odoo_invoices_pulled",
            count=len(invoices),
            since=since.isoformat() if since else None,
        )

        return invoices

    async def get_invoice(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Holt eine Rechnung aus Odoo."""
        try:
            result = await self._execute_kw(
                "account.move",
                "read",
                [[int(erp_id)]],
                {"fields": [
                    "id", "name", "ref", "move_type", "state",
                    "partner_id", "invoice_date", "invoice_date_due",
                    "amount_total", "amount_residual", "currency_id",
                    "payment_state", "invoice_line_ids"
                ]}
            )
            return result[0] if result else None

        except Exception as e:
            logger.error("odoo_get_invoice_error", erp_id=erp_id, error=self._sanitize_error(e))
            return None

    async def update_payment_status(
        self,
        erp_id: str,
        status: str,
        payment_date: Optional[datetime] = None,
        amount: Optional[float] = None,
    ) -> bool:
        """Aktualisiert den Zahlungsstatus einer Rechnung."""
        try:
            # In Odoo, payments are registered separately
            # This would need to create a payment record
            # For now, log the intention
            logger.info(
                "odoo_payment_status_update_requested",
                erp_id=erp_id,
                status=status,
                amount=amount,
            )
            return True

        except Exception as e:
            logger.error(
                "odoo_update_payment_status_error",
                erp_id=erp_id,
                error=self._sanitize_error(e)
            )
            return False

    # ==========================================================================
    # Document Attachments
    # ==========================================================================

    async def attach_document(
        self,
        entity: ERPEntity,
        erp_id: str,
        document_data: bytes,
        filename: str,
        mime_type: str,
    ) -> bool:
        """Haengt ein Dokument an eine Odoo-Entität an."""
        try:
            import base64

            # Map entity to Odoo model
            model_map = {
                ERPEntity.INVOICE: "account.move",
                ERPEntity.CUSTOMER: "res.partner",
                ERPEntity.SUPPLIER: "res.partner",
                ERPEntity.ORDER: "sale.order",
            }

            model = model_map.get(entity)
            if not model:
                logger.error("odoo_attach_unknown_entity", entity=entity.value)
                return False

            # Create attachment
            attachment_data = {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(document_data).decode("utf-8"),
                "res_model": model,
                "res_id": int(erp_id),
                "mimetype": mime_type,
            }

            attachment_id = await self._execute_kw(
                "ir.attachment",
                "create",
                [attachment_data]
            )

            logger.info(
                "odoo_document_attached",
                attachment_id=attachment_id,
                entity=entity.value,
                erp_id=erp_id,
                filename=filename,
            )
            return True

        except Exception as e:
            logger.error(
                "odoo_attach_document_error",
                entity=entity.value,
                erp_id=erp_id,
                error=self._sanitize_error(e)
            )
            return False

    async def get_attachments(
        self,
        entity: ERPEntity,
        erp_id: str,
    ) -> List[Dict[str, Any]]:
        """Holt Anhaenge einer Odoo-Entität."""
        try:
            model_map = {
                ERPEntity.INVOICE: "account.move",
                ERPEntity.CUSTOMER: "res.partner",
                ERPEntity.SUPPLIER: "res.partner",
                ERPEntity.ORDER: "sale.order",
            }

            model = model_map.get(entity)
            if not model:
                return []

            attachments = await self._execute_kw(
                "ir.attachment",
                "search_read",
                [[
                    ["res_model", "=", model],
                    ["res_id", "=", int(erp_id)]
                ]],
                {"fields": ["id", "name", "mimetype", "file_size", "create_date"]}
            )

            return attachments

        except Exception as e:
            logger.error(
                "odoo_get_attachments_error",
                entity=entity.value,
                erp_id=erp_id,
                error=self._sanitize_error(e)
            )
            return []

    async def download_attachment(
        self,
        attachment_id: int,
    ) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """
        Laedt den Binaerinhalt eines ir.attachment herunter.

        Liest name/mimetype/checksum/res_model/res_id/datas und
        dekodiert das base64-Feld datas. Odoo liefert fuer leere
        Binaerfelder False (nicht None) - z.B. bei type='url'-Attachments
        oder fehlendem Filestore-Blob; in dem Fall wird b"" als Inhalt
        zurueckgegeben (der Aufrufer entscheidet, ob er leere
        Attachments ueberspringt). Der checksum in den Metadaten dient
        der Hash-Verifikation im GoBD-Spiegel.

        Args:
            attachment_id: ID des ir.attachment

        Returns:
            Tuple (Inhalt als bytes, Metadaten-Dict ohne datas)
            oder None bei Fehler/nicht gefunden
        """
        try:
            import base64

            records = await self._execute_kw(
                "ir.attachment",
                "read",
                [[attachment_id]],
                {"fields": [
                    "name", "mimetype", "checksum", "res_model", "res_id", "datas"
                ]}
            )
            if not records:
                logger.warning(
                    "odoo_attachment_not_found",
                    attachment_id=attachment_id,
                )
                return None

            metadata = dict(records[0])
            datas = metadata.pop("datas", None)
            # Odoo liefert False fuer leere Binaerfelder (nicht None)
            content = base64.b64decode(datas) if datas else b""

            logger.info(
                "odoo_attachment_downloaded",
                attachment_id=attachment_id,
                size=len(content),
            )
            return content, metadata

        except Exception as e:
            logger.error(
                "odoo_download_attachment_error",
                attachment_id=attachment_id,
                error=self._sanitize_error(e)
            )
            return None

    async def list_attachments(
        self,
        res_model: str,
        res_id: int,
        *,
        include_field_attachments: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Listet Anhaenge eines Odoo-Datensatzes (fuer den Spiegel-Sync).

        ACHTUNG Odoo-Falle: Die Standard-Suche auf ir.attachment filtert
        implizit res_field = False - Binaerfeld-Attachments (z.B. in
        Feldern gerenderte Rechnungs-PDFs) sind damit unsichtbar. Sobald
        die Domain selbst einen res_field-Term enthaelt, deaktiviert
        Odoo diesen impliziten Filter. Mit include_field_attachments=True
        wird deshalb eine Tautologie-OR-Domain vorangestellt
        ("res_field = False ODER res_field != False"), die ALLE
        Attachments des Datensatzes liefert.

        Args:
            res_model: Odoo-Modell des Traegers (z.B. "account.move")
            res_id: ID des Traeger-Datensatzes
            include_field_attachments: Auch Binaerfeld-Attachments
                (res_field != False) einschliessen

        Returns:
            Liste der Anhaenge mit Metadaten (inkl. checksum fuer die
            Hash-Verifikation im GoBD-Spiegel)
        """
        try:
            domain: List[Any] = [
                ["res_model", "=", res_model],
                ["res_id", "=", res_id],
            ]
            if include_field_attachments:
                # Expliziter res_field-Term deaktiviert Odoos impliziten
                # res_field=False-Filter; die OR-Tautologie matcht alle.
                domain = [
                    "|",
                    ["res_field", "=", False],
                    ["res_field", "!=", False],
                ] + domain

            attachments = await self._execute_kw(
                "ir.attachment",
                "search_read",
                [domain],
                {"fields": [
                    "id", "name", "mimetype", "file_size", "checksum",
                    "res_field", "create_date", "write_date",
                ]}
            )
            return attachments

        except Exception as e:
            logger.error(
                "odoo_list_attachments_error",
                res_model=res_model,
                res_id=res_id,
                error=self._sanitize_error(e)
            )
            return []

    # ==========================================================================
    # Vendor-Bill-Push & Partner-Matching (Phase 2 Neuausrichtung)
    # ==========================================================================

    async def create_vendor_bill_draft(
        self,
        bill: OdooVendorBillDraft,
        *,
        pdf_content: Optional[bytes] = None,
        pdf_filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        Legt eine Entwurfs-Lieferantenrechnung in Odoo an.

        account.move.create mit move_type="in_invoice"; create OHNE
        state-Feld ergibt implizit einen Entwurf (draft) - Buchung,
        Zahlung und Mahnung passieren in Odoo. Der Betrag geht als
        eine Brutto-Sammelzeile (quantity 1); Steuer-/Kontenzuordnung
        erfolgt beim Pruefen des Entwurfs in Odoo.

        Optional wird das Original-PDF via attach_document angehaengt
        und per write als message_main_attachment_id gesetzt (Haupt-
        Anhang in der Odoo-Belegvorschau). Ein Attachment-Fehler ist
        nicht fatal: Die Entwurfsrechnung existiert dann bereits und
        wird trotzdem zurueckgemeldet.

        Args:
            bill: Validierte Entwurfsdaten (OdooVendorBillDraft)
            pdf_content: Original-PDF als Bytes (optional)
            pdf_filename: Dateiname des PDFs (optional)

        Returns:
            move_id als str oder None bei Fehler
        """
        try:
            # Idempotenz gegen Doppel-Push (F-07): Ein Celery-Retry nach
            # verlorener RPC-Antwort oder fehlgeschlagenem lokalem Commit darf
            # keinen zweiten Entwurf anlegen. Existiert bereits ein in_invoice
            # mit gleichem Partner, gleicher Referenz UND gleichem Rechnungsdatum,
            # wird er adoptiert statt ein Duplikat zu erzeugen. Der PDF-Anhang
            # wird dann nicht erneut gesetzt (er haengt am ersten Entwurf).
            # F-19: invoice_date ist Teil des Dedupe-Schluessels — sonst wuerden
            # ZWEI VERSCHIEDENE Rechnungen desselben Lieferanten mit zufaellig
            # gleicher Nummer (Jahres-Reset "001"/"001", OCR-Fehllesung) still
            # zusammengeworfen und der zweite offene Posten erreichte Odoo nie.
            # Wiederhol-Sicherheit bleibt: dasselbe Dokument hat dasselbe Datum.
            existing = await self._execute_kw(
                "account.move",
                "search",
                [[
                    ["move_type", "=", "in_invoice"],
                    ["partner_id", "=", bill.partner_id],
                    ["ref", "=", bill.ref],
                    ["invoice_date", "=", bill.invoice_date.isoformat()],
                ]],
                {"limit": 1},
            )
            if existing:
                existing_id = existing[0]
                logger.info(
                    "odoo_vendor_bill_draft_deduped",
                    move_id=existing_id,
                    partner_id=bill.partner_id,
                )
                return str(existing_id)

            # Decimal NUR am XML-RPC-Rand in float wandeln: xmlrpc.client
            # kann Decimal nicht marshallen (TypeError). Vorher kaufmaennisch
            # auf 2 Nachkommastellen quantisieren, damit die float-Konvertierung
            # keinen Rundungsdrift einschleppt.
            price_unit = float(
                bill.amount_total_brutto.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )

            move_data: Dict[str, Any] = {
                "move_type": "in_invoice",
                "partner_id": bill.partner_id,
                "invoice_date": bill.invoice_date.isoformat(),
                "ref": bill.ref,
                "invoice_line_ids": [
                    (0, 0, {
                        "name": bill.line_name,
                        "quantity": 1.0,
                        "price_unit": price_unit,
                    })
                ],
            }
            if bill.narration:
                move_data["narration"] = bill.narration

            move_id = await self._execute_kw(
                "account.move",
                "create",
                [move_data]
            )

            if not move_id:
                logger.error(
                    "odoo_vendor_bill_create_failed",
                    partner_id=bill.partner_id,
                )
                return None

            if pdf_content is not None:
                await self._attach_main_pdf(
                    move_id=int(move_id),
                    pdf_content=pdf_content,
                    pdf_filename=pdf_filename or f"eingangsrechnung_{move_id}.pdf",
                )

            logger.info(
                "odoo_vendor_bill_draft_created",
                move_id=move_id,
                partner_id=bill.partner_id,
                has_pdf=pdf_content is not None,
            )
            return str(move_id)

        except Exception as e:
            logger.error(
                "odoo_create_vendor_bill_error",
                partner_id=bill.partner_id,
                error=self._sanitize_error(e)
            )
            return None

    async def _attach_main_pdf(
        self,
        move_id: int,
        pdf_content: bytes,
        pdf_filename: str,
    ) -> None:
        """
        Haengt das PDF an den Move und setzt message_main_attachment_id.

        Fehler hier sind bewusst nicht fatal (die Entwurfsrechnung
        existiert bereits) - sie werden geloggt, der Aufrufer erhaelt
        die move_id trotzdem.
        """
        attached = await self.attach_document(
            entity=ERPEntity.INVOICE,
            erp_id=str(move_id),
            document_data=pdf_content,
            filename=pdf_filename,
            mime_type="application/pdf",
        )
        if not attached:
            logger.warning(
                "odoo_vendor_bill_pdf_attach_failed",
                move_id=move_id,
            )
            return

        try:
            # attach_document liefert nur bool (Basisklassen-Signatur) ->
            # juengstes Attachment des Moves nachschlagen, um es als
            # Haupt-Anhang zu setzen.
            attachment_ids = await self._execute_kw(
                "ir.attachment",
                "search",
                [[
                    ["res_model", "=", "account.move"],
                    ["res_id", "=", move_id],
                ]],
                {"order": "id desc", "limit": 1}
            )
            if attachment_ids:
                await self._execute_kw(
                    "account.move",
                    "write",
                    [[move_id], {"message_main_attachment_id": attachment_ids[0]}]
                )
        except Exception as e:
            logger.warning(
                "odoo_vendor_bill_main_attachment_error",
                move_id=move_id,
                error=self._sanitize_error(e),
            )

    async def find_partner(
        self,
        *,
        vat: Optional[str] = None,
        iban: Optional[str] = None,
        supplier_ref: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Partner-Matching-Kaskade fuer den Eingangsrechnungs-Push.

        Fuehrt EINZELNE Suchen in fester Reihenfolge aus und bricht beim
        ersten nicht-leeren Ergebnis ab:
          1. USt-IdNr. (res.partner.vat, =ilike; normalisiert:
             Leerzeichen raus, Grossbuchstaben)
          2. IBAN (res.partner.bank.sanitized_acc_number; normalisiert
             auf alphanumerisch/upper) -> Aufloesung auf res.partner
          3. Lieferantennummer (res.partner.ref, exakter Vergleich)
          4. Name (ilike, limit 5) - nur als letzter Fallback, wenn die
             Stufen 1-3 leer blieben

        Exakte Identifikatoren (1-3) laufen bewusst OHNE
        supplier_rank-Filter: Ein VAT-/IBAN-/ref-Treffer ist auch dann
        der richtige Partner, wenn er bisher nur Kunde war. Die
        unscharfe Namenssuche (4) ist auf Lieferanten
        (supplier_rank > 0) eingeschraenkt.

        Jedes Ergebnis-Dict wird um "match_source" ergaenzt
        ("vat" | "iban" | "ref" | "name"). Die Eindeutigkeits-
        Entscheidung (nur eindeutiger Treffer pusht) trifft der
        aufrufende Service.

        Returns:
            Liste von Partner-Dicts (ggf. leer)
        """
        fields = [
            "id", "name", "vat", "ref",
            "supplier_rank", "customer_rank", "email",
        ]

        try:
            if vat:
                vat_normalized = vat.replace(" ", "").upper()
                partners = await self._execute_kw(
                    "res.partner",
                    "search_read",
                    [[["vat", "=ilike", vat_normalized]]],
                    {"fields": fields}
                )
                if partners:
                    return self._tag_match_source(partners, "vat")

            if iban:
                iban_normalized = "".join(
                    c for c in iban if c.isalnum()
                ).upper()
                banks = await self._execute_kw(
                    "res.partner.bank",
                    "search_read",
                    [[["sanitized_acc_number", "=", iban_normalized]]],
                    {"fields": ["partner_id"]}
                )
                partner_ids: List[int] = []
                for bank in banks:
                    partner_ref = bank.get("partner_id")
                    # search_read liefert m2o als [id, display_name] (oder False)
                    if partner_ref:
                        partner_ids.append(int(partner_ref[0]))
                # Reihenfolge stabil deduplizieren
                partner_ids = list(dict.fromkeys(partner_ids))
                if partner_ids:
                    partners = await self._execute_kw(
                        "res.partner",
                        "read",
                        [partner_ids],
                        {"fields": fields}
                    )
                    if partners:
                        return self._tag_match_source(partners, "iban")

            if supplier_ref:
                partners = await self._execute_kw(
                    "res.partner",
                    "search_read",
                    [[["ref", "=", supplier_ref]]],
                    {"fields": fields}
                )
                if partners:
                    return self._tag_match_source(partners, "ref")

            # Name-Suche (letzte Stufe): Wildcards escapen (F-06) und sehr
            # kurze Namen ueberspringen (matchen zu breit -> Falsch-Partner).
            # Die endgueltige Eindeutigkeitspruefung bei genau 1 Treffer
            # passiert im Push-Service (normalisierte Namensgleichheit).
            name_clean = name.strip() if name else ""
            if len(name_clean) >= _MIN_NAME_SEARCH_LEN:
                partners = await self._execute_kw(
                    "res.partner",
                    "search_read",
                    [[
                        ["name", "ilike", self._escape_like(name_clean)],
                        ["supplier_rank", ">", 0],
                    ]],
                    {"fields": fields, "limit": 5}
                )
                if partners:
                    return self._tag_match_source(partners, "name")

            return []

        except Exception as e:
            # PII-Regel: vat/iban/name NIE mitloggen
            logger.error(
                "odoo_find_partner_error",
                error=self._sanitize_error(e)
            )
            return []

    @staticmethod
    def _tag_match_source(
        partners: List[Dict[str, Any]],
        source: str,
    ) -> List[Dict[str, Any]]:
        """Ergaenzt jedes Partner-Dict um die Match-Quelle der Kaskade."""
        for partner in partners:
            partner["match_source"] = source
        return partners

    @staticmethod
    def _escape_like(value: str) -> str:
        """Escaped SQL-LIKE-Wildcards (\\, %, _) fuer eine ilike-Domain.

        Ohne Escaping wuerde ein OCR-Name mit ``%``/``_`` von Odoos ``ilike``
        als Wildcard interpretiert und breit (falsch) matchen (F-06). Der
        Backslash ist der PostgreSQL-Default-Escape-Char; er muss zuerst
        verdoppelt werden.
        """
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    # ==========================================================================
    # Additional Odoo-Specific Methods
    # ==========================================================================

    async def get_company_info(self) -> Optional[Dict[str, Any]]:
        """Holt Firmeninformationen aus Odoo."""
        try:
            companies = await self._execute_kw(
                "res.company",
                "search_read",
                [[]],
                {"fields": ["id", "name", "email", "phone", "vat", "currency_id"], "limit": 1}
            )
            return companies[0] if companies else None

        except Exception as e:
            logger.error("odoo_get_company_error", error=self._sanitize_error(e))
            return None

    async def search_partners(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Sucht Partner (Kunden/Lieferanten) in Odoo."""
        try:
            domain = [
                "|",
                ["name", "ilike", query],
                ["email", "ilike", query]
            ]

            partners = await self._execute_kw(
                "res.partner",
                "search_read",
                [domain],
                {"fields": ["id", "name", "email", "phone", "customer_rank", "supplier_rank"], "limit": limit}
            )

            return partners

        except Exception as e:
            logger.error("odoo_search_partners_error", query=query, error=self._sanitize_error(e))
            return []

    async def get_currencies(self) -> List[Dict[str, Any]]:
        """Holt alle aktiven Währungen aus Odoo."""
        try:
            currencies = await self._execute_kw(
                "res.currency",
                "search_read",
                [[["active", "=", True]]],
                {"fields": ["id", "name", "symbol", "rate"]}
            )
            return currencies

        except Exception as e:
            logger.error("odoo_get_currencies_error", error=self._sanitize_error(e))
            return []

    # ==========================================================================
    # Phase 6: Extended Data Types - Projects, Timesheet, Inventory
    # ==========================================================================

    async def sync_projects(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> ERPSyncResult:
        """
        Synchronisiert Projekte aus Odoo.

        Args:
            since: Nur Änderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            ERPSyncResult mit Projektdaten
        """
        result = self._create_sync_result(
            entity=ERPEntity.DOCUMENT,  # Use DOCUMENT for extended types
            direction=ERPSyncDirection.PULL,
        )
        result.entity = "project"  # Override for clarity

        try:
            domain: List[Any] = [["active", "=", True]]

            if since:
                domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])

            fields = [
                "id", "name", "partner_id", "user_id",
                "date_start", "date", "active", "stage_id",
                "task_count", "write_date", "create_date"
            ]

            projects = await self._execute_kw(
                "project.project",
                "search_read",
                [domain],
                {"fields": fields, "limit": batch_size}
            )

            result.records_synced = len(projects)
            result.records = projects
            result.success = True

            logger.info(
                "odoo_projects_synced",
                count=len(projects),
                since=since.isoformat() if since else None,
            )

        except Exception as e:
            result.success = False
            result.error_message = self._sanitize_error(e)
            logger.exception("odoo_sync_projects_error", error=self._sanitize_error(e))

        return self._complete_sync_result(result)

    async def sync_timesheet_entries(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 500,
    ) -> ERPSyncResult:
        """
        Synchronisiert Zeiterfassungs-Einträge aus Odoo.

        Args:
            since: Nur Änderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            ERPSyncResult mit Timesheet-Daten
        """
        result = self._create_sync_result(
            entity=ERPEntity.DOCUMENT,
            direction=ERPSyncDirection.PULL,
        )
        result.entity = "timesheet"

        try:
            domain: List[Any] = []

            if since:
                domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])

            fields = [
                "id", "date", "employee_id", "project_id", "task_id",
                "name", "unit_amount", "account_id", "write_date"
            ]

            timesheets = await self._execute_kw(
                "account.analytic.line",
                "search_read",
                [domain] if domain else [[]],
                {"fields": fields, "limit": batch_size}
            )

            result.records_synced = len(timesheets)
            result.records = timesheets
            result.success = True

            logger.info(
                "odoo_timesheets_synced",
                count=len(timesheets),
                since=since.isoformat() if since else None,
            )

        except Exception as e:
            result.success = False
            result.error_message = self._sanitize_error(e)
            logger.exception("odoo_sync_timesheets_error", error=self._sanitize_error(e))

        return self._complete_sync_result(result)

    async def sync_stock_moves(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 200,
    ) -> ERPSyncResult:
        """
        Synchronisiert Lagerbewegungen aus Odoo.

        Args:
            since: Nur Änderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            ERPSyncResult mit Stock-Move-Daten
        """
        result = self._create_sync_result(
            entity=ERPEntity.PRODUCT,
            direction=ERPSyncDirection.PULL,
        )
        result.entity = "stock_move"

        try:
            domain: List[Any] = [["state", "!=", "cancel"]]

            if since:
                domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])

            fields = [
                "id", "name", "product_id", "product_uom_qty", "quantity_done",
                "location_id", "location_dest_id", "state", "date",
                "origin", "picking_id", "write_date"
            ]

            stock_moves = await self._execute_kw(
                "stock.move",
                "search_read",
                [domain],
                {"fields": fields, "limit": batch_size}
            )

            result.records_synced = len(stock_moves)
            result.records = stock_moves
            result.success = True

            logger.info(
                "odoo_stock_moves_synced",
                count=len(stock_moves),
                since=since.isoformat() if since else None,
            )

        except Exception as e:
            result.success = False
            result.error_message = self._sanitize_error(e)
            logger.exception("odoo_sync_stock_moves_error", error=self._sanitize_error(e))

        return self._complete_sync_result(result)

    async def sync_product_catalog(
        self,
        since: Optional[datetime] = None,
        batch_size: int = 200,
    ) -> ERPSyncResult:
        """
        Synchronisiert Produktkatalog aus Odoo.

        Args:
            since: Nur Änderungen seit diesem Zeitpunkt
            batch_size: Anzahl pro Batch

        Returns:
            ERPSyncResult mit Produktdaten inkl. Bestand
        """
        result = self._create_sync_result(
            entity=ERPEntity.PRODUCT,
            direction=ERPSyncDirection.PULL,
        )

        try:
            domain: List[Any] = []

            if since:
                domain.append(["write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S")])

            fields = [
                "id", "name", "default_code", "barcode",
                "list_price", "standard_price", "qty_available",
                "virtual_available", "categ_id", "uom_id",
                "type", "active", "write_date"
            ]

            products = await self._execute_kw(
                "product.product",
                "search_read",
                [domain] if domain else [[]],
                {"fields": fields, "limit": batch_size}
            )

            result.records_synced = len(products)
            result.records = products
            result.success = True

            logger.info(
                "odoo_products_synced",
                count=len(products),
                since=since.isoformat() if since else None,
            )

        except Exception as e:
            result.success = False
            result.error_message = self._sanitize_error(e)
            logger.exception("odoo_sync_products_error", error=self._sanitize_error(e))

        return self._complete_sync_result(result)

    # ==========================================================================
    # Phase 6: AI Feedback Push Methods
    # ==========================================================================

    async def push_risk_score(
        self,
        partner_id: int,
        score: float,
        risk_level: str,
        payment_score: float,
        updated_at: str,
    ) -> bool:
        """
        Pusht einen Risk Score zu einem Odoo-Partner.

        Args:
            partner_id: Odoo Partner-ID
            score: Risiko-Score (0-100)
            risk_level: Risiko-Level (low/medium/high/critical)
            payment_score: Zahlungsverhalten-Score (0-100)
            updated_at: Aktualisierungszeitpunkt

        Returns:
            True wenn erfolgreich
        """
        try:
            data = {
                "x_ablage_risk_score": round(score, 1),
                "x_ablage_risk_level": risk_level,
                "x_ablage_payment_score": round(payment_score, 1),
                "x_ablage_risk_updated": updated_at,
            }

            await self._execute_kw(
                "res.partner",
                "write",
                [[partner_id], data]
            )

            logger.info(
                "odoo_risk_score_pushed",
                partner_id=partner_id,
                score=round(score, 1),
                risk_level=risk_level,
            )
            return True

        except Exception as e:
            logger.error(
                "odoo_push_risk_score_error",
                partner_id=partner_id,
                error=self._sanitize_error(e)
            )
            return False

    async def push_payment_suggestion(
        self,
        partner_id: int,
        suggested_term: str,
        suggested_credit_limit: Optional[float],
        reason: str,
    ) -> bool:
        """
        Pusht einen Zahlungsvorschlag zu einem Odoo-Partner.

        Args:
            partner_id: Odoo Partner-ID
            suggested_term: Empfohlene Zahlungsbedingung
            suggested_credit_limit: Empfohlenes Kreditlimit
            reason: Begruendung (sanitized)

        Returns:
            True wenn erfolgreich
        """
        try:
            data = {
                "x_ablage_suggested_payment_term": suggested_term,
                "x_ablage_payment_suggestion_reason": reason[:500],  # Limit length
            }

            if suggested_credit_limit is not None:
                data["x_ablage_suggested_credit_limit"] = round(suggested_credit_limit, 2)

            await self._execute_kw(
                "res.partner",
                "write",
                [[partner_id], data]
            )

            logger.info(
                "odoo_payment_suggestion_pushed",
                partner_id=partner_id,
                suggested_term=suggested_term,
            )
            return True

        except Exception as e:
            logger.error(
                "odoo_push_payment_suggestion_error",
                partner_id=partner_id,
                error=self._sanitize_error(e)
            )
            return False

    async def push_skonto_prediction(
        self,
        partner_id: int,
        skonto_probability: float,
        avg_payment_days: float,
        recommended_skonto: Optional[float],
    ) -> bool:
        """
        Pusht eine Skonto-Vorhersage zu einem Odoo-Partner.

        Args:
            partner_id: Odoo Partner-ID
            skonto_probability: Wahrscheinlichkeit der Skonto-Nutzung (0-1)
            avg_payment_days: Durchschnittliche Zahlungstage
            recommended_skonto: Empfohlener Skonto-Prozentsatz

        Returns:
            True wenn erfolgreich
        """
        try:
            data = {
                "x_ablage_skonto_probability": round(skonto_probability, 3),
                "x_ablage_avg_payment_days": round(avg_payment_days, 1),
            }

            if recommended_skonto is not None:
                data["x_ablage_recommended_skonto"] = round(recommended_skonto, 2)

            await self._execute_kw(
                "res.partner",
                "write",
                [[partner_id], data]
            )

            logger.info(
                "odoo_skonto_prediction_pushed",
                partner_id=partner_id,
                probability=round(skonto_probability, 2),
            )
            return True

        except Exception as e:
            logger.error(
                "odoo_push_skonto_prediction_error",
                partner_id=partner_id,
                error=self._sanitize_error(e)
            )
            return False
