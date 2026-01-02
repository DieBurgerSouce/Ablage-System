# Feature 04: Odoo-Integration

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P2 - Wichtig
> **Geschaetzter Aufwand**: 4-5 Wochen
> **Abhaengigkeiten**: Feature 01 (Multi-Firma)

---

## Executive Summary

Die Odoo-Integration ermoeglicht bidirektionale Synchronisation zwischen dem Ablage-System und Odoo ERP. Firma 1 (Spargelmesser) nutzt bereits Odoo Cloud, Firma 2 plant Migration. Die Integration umfasst Rechnungen, Kunden, Lieferanten und Zahlungsstatus. Langfristig ersetzt Odoo das bisherige Lexware-System.

**Business Value:**
- Keine doppelte Datenpflege
- Realtime oder taeglicher Sync
- Dokumente automatisch verlinkt
- Zukunftssichere ERP-Strategie

---

## Inhaltsverzeichnis

1. [Anforderungen](#anforderungen)
2. [Sync-Architektur](#sync-architektur)
3. [API-Spezifikation](#api-spezifikation)
4. [Datenbank-Schema](#datenbank-schema)
5. [Mapping-Tabellen](#mapping-tabellen)
6. [Implementation Tasks](#implementation-tasks)
7. [Test-Szenarien](#test-szenarien)
8. [Quality Gates](#quality-gates)

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | Rechnungen sync (Odoo → Ablage) | MUSS | Neue Rechnungen automatisch importiert |
| FR-02 | Kunden bidirektional sync | MUSS | Aenderungen in beide Richtungen |
| FR-03 | Lieferanten bidirektional sync | MUSS | Aenderungen in beide Richtungen |
| FR-04 | Zahlungsstatus (Ablage → Odoo) | MUSS | Banking-Match aktualisiert Odoo |
| FR-05 | Dokument-Links (Ablage → Odoo) | SOLL | Link zum Archiv in Odoo |
| FR-06 | Realtime Sync (Webhooks) | SOLL | Sofortige Sync bei Aenderung |
| FR-07 | Scheduled Sync | MUSS | Fallback alle 15 Minuten |
| FR-08 | Konflikt-Handling | MUSS | Last-Write-Wins oder Queue |

### Nicht-Funktionale Anforderungen

| ID | Anforderung | Metrik | Akzeptanzkriterium |
|----|-------------|--------|-------------------|
| NFR-01 | Sync-Latenz | Zeit | < 5 Minuten bei Scheduled |
| NFR-02 | Zuverlaessigkeit | Erfolgsrate | 99.5% erfolgreich |
| NFR-03 | Fehler-Recovery | Retry | Max 3 Retries mit Backoff |
| NFR-04 | Auditierung | Logging | Jeder Sync geloggt |

---

## Sync-Architektur

### Bidirektionale Datenfluss

```
┌─────────────────────────────────────────────────────────────┐
│                    ODOO ERP (Cloud)                         │
├─────────────────────────────────────────────────────────────┤
│  Rechnungen   Angebote   Bestellungen   Kunden   Lieferant  │
│      │           │           │            │          │       │
│      └───────────┴───────────┴────────────┴──────────┘       │
│                           │                                  │
│                    Odoo REST API                             │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │
                   ┌────────┴────────┐
                   │  Sync Engine    │
                   │  ─────────────  │
                   │  • Webhooks     │
                   │  • Scheduler    │
                   │  • Mapping      │
                   │  • Conflict Res │
                   └────────┬────────┘
                            │
┌───────────────────────────┼──────────────────────────────────┐
│                           │                                  │
│                    Ablage-System                             │
│                           │                                  │
│      ┌───────────┬────────┴───────┬──────────┬──────────┐   │
│      │           │                │          │          │   │
│  Dokumente   Extrahierte     Kunden    Lieferanten  Banking │
│              Daten                                          │
└─────────────────────────────────────────────────────────────┘

SYNC-RICHTUNGEN:
────────────────
Odoo → Ablage:  Rechnungen, Angebote, Bestellungen
Ablage → Odoo:  Zahlungsstatus, Dokument-Links, OCR-Daten
Bidirektional:  Kunden, Lieferanten
```

### Sync-Modi

| Modus | Trigger | Latenz | Use Case |
|-------|---------|--------|----------|
| **Realtime** | Webhook | < 10s | Neue Rechnungen |
| **Scheduled** | Cron (15min) | < 15min | Bulk-Sync, Fallback |
| **Manual** | API Call | Sofort | Admin-Trigger, Debug |
| **Initial** | Einmalig | Stunden | Erstmalige Migration |

---

## API-Spezifikation

### Interne Endpoints

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/integrations/odoo/status` | Sync-Status | Required |
| POST | `/api/v1/integrations/odoo/sync/full` | Vollsync starten | Admin |
| POST | `/api/v1/integrations/odoo/sync/entity/{type}` | Entity-Sync | Admin |
| GET | `/api/v1/integrations/odoo/conflicts` | Konflikt-Queue | Admin |
| POST | `/api/v1/integrations/odoo/conflicts/{id}/resolve` | Konflikt loesen | Admin |
| GET | `/api/v1/integrations/odoo/mappings` | Mapping-Tabelle | Admin |
| PUT | `/api/v1/integrations/odoo/settings` | Einstellungen | Admin |
| POST | `/api/v1/webhooks/odoo` | Odoo Webhook Empfang | Webhook-Secret |

---

### `GET /api/v1/integrations/odoo/status`

**Response (200 OK):**
```json
{
  "connection": {
    "status": "connected",
    "last_ping": "2026-01-15T10:00:00Z",
    "odoo_version": "17.0",
    "database": "production"
  },
  "sync": {
    "last_full_sync": "2026-01-15T03:00:00Z",
    "last_incremental": "2026-01-15T10:15:00Z",
    "next_scheduled": "2026-01-15T10:30:00Z"
  },
  "entities": {
    "invoices": {
      "total_synced": 1250,
      "pending": 3,
      "last_sync": "2026-01-15T10:10:00Z"
    },
    "customers": {
      "total_synced": 450,
      "pending": 0,
      "last_sync": "2026-01-15T10:15:00Z"
    },
    "suppliers": {
      "total_synced": 120,
      "pending": 1,
      "last_sync": "2026-01-15T10:14:00Z"
    }
  },
  "errors": {
    "last_24h": 2,
    "unresolved_conflicts": 1
  }
}
```

---

### `POST /api/v1/webhooks/odoo`

**Odoo Webhook Payload (Invoice Created):**
```json
{
  "event": "account.move.create",
  "timestamp": "2026-01-15T10:00:00Z",
  "data": {
    "id": 12345,
    "name": "INV/2026/0001",
    "partner_id": [42, "Kunde GmbH"],
    "amount_total": 1500.00,
    "state": "posted",
    "invoice_date": "2026-01-15"
  }
}
```

**Response (200 OK):**
```json
{
  "status": "accepted",
  "sync_id": "sync-uuid",
  "message": "Invoice queued for processing"
}
```

---

## Datenbank-Schema

### Neue Tabellen

#### `integration_connections`

```sql
CREATE TABLE integration_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identifikation
    company_id UUID REFERENCES companies(id) NOT NULL,
    integration_type VARCHAR(50) NOT NULL,  -- odoo, lexware, csv

    -- Verbindung
    name VARCHAR(255) NOT NULL,
    base_url VARCHAR(500) NOT NULL,
    database_name VARCHAR(100),

    -- Authentifizierung (verschluesselt)
    credentials JSONB NOT NULL,  -- {api_key, username, etc.}

    -- Status
    is_active BOOLEAN DEFAULT true,
    last_connected_at TIMESTAMPTZ,
    connection_status VARCHAR(20) DEFAULT 'pending',

    -- Einstellungen
    settings JSONB DEFAULT '{
        "sync_interval_minutes": 15,
        "sync_mode": "scheduled",
        "entities": ["invoices", "customers", "suppliers"]
    }',

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT integration_connections_company_type UNIQUE (company_id, integration_type)
);
```

#### `integration_mappings`

```sql
CREATE TABLE integration_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Verbindung
    connection_id UUID REFERENCES integration_connections(id) ON DELETE CASCADE NOT NULL,

    -- Entity-Typ
    entity_type VARCHAR(50) NOT NULL,  -- customer, supplier, invoice, product

    -- IDs
    local_id UUID NOT NULL,
    external_id VARCHAR(100) NOT NULL,

    -- Sync-Status
    last_synced_at TIMESTAMPTZ,
    local_updated_at TIMESTAMPTZ,
    external_updated_at TIMESTAMPTZ,
    sync_direction VARCHAR(20),  -- to_odoo, from_odoo, bidirectional

    -- Hash fuer Change-Detection
    local_hash VARCHAR(64),
    external_hash VARCHAR(64),

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT integration_mappings_unique UNIQUE (connection_id, entity_type, local_id),
    CONSTRAINT integration_mappings_external UNIQUE (connection_id, entity_type, external_id)
);

CREATE INDEX ix_mappings_connection ON integration_mappings(connection_id);
CREATE INDEX ix_mappings_entity ON integration_mappings(entity_type);
CREATE INDEX ix_mappings_external ON integration_mappings(external_id);
```

#### `integration_sync_logs`

```sql
CREATE TABLE integration_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    connection_id UUID REFERENCES integration_connections(id) NOT NULL,

    -- Sync-Details
    sync_type VARCHAR(20) NOT NULL,  -- full, incremental, webhook, manual
    entity_type VARCHAR(50),
    direction VARCHAR(20) NOT NULL,  -- import, export, bidirectional

    -- Ergebnis
    status VARCHAR(20) NOT NULL,  -- started, completed, failed
    records_processed INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,

    -- Fehler
    error_message TEXT,
    error_details JSONB,

    -- Timing
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,

    -- Audit
    triggered_by VARCHAR(100)  -- system, user:uuid, webhook
);

CREATE INDEX ix_sync_logs_connection ON integration_sync_logs(connection_id);
CREATE INDEX ix_sync_logs_status ON integration_sync_logs(status);
CREATE INDEX ix_sync_logs_started ON integration_sync_logs(started_at DESC);
```

#### `integration_conflicts`

```sql
CREATE TABLE integration_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Referenz
    mapping_id UUID REFERENCES integration_mappings(id) NOT NULL,
    connection_id UUID REFERENCES integration_connections(id) NOT NULL,

    -- Konflikt-Details
    entity_type VARCHAR(50) NOT NULL,
    local_data JSONB NOT NULL,
    external_data JSONB NOT NULL,
    conflict_fields JSONB NOT NULL,  -- ["name", "address"]

    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, resolved_local, resolved_external, merged
    resolved_at TIMESTAMPTZ,
    resolved_by_id UUID REFERENCES users(id),
    resolution_data JSONB,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_conflicts_pending ON integration_conflicts(status) WHERE status = 'pending';
```

---

## Mapping-Tabellen

### Feld-Mapping: Odoo → Ablage

#### Invoices (account.move)

| Odoo Feld | Ablage Feld | Transformation |
|-----------|-------------|----------------|
| `id` | `external_id` | String |
| `name` | `invoice_number` | Direct |
| `partner_id` | `customer_id` | Lookup via mapping |
| `amount_total` | `total_amount` | Decimal |
| `amount_tax` | `tax_amount` | Decimal |
| `amount_untaxed` | `net_amount` | Decimal |
| `invoice_date` | `invoice_date` | Date |
| `invoice_date_due` | `due_date` | Date |
| `state` | `status` | Map: posted→approved |
| `payment_state` | `payment_status` | Map: paid→paid |
| `currency_id` | `currency` | Lookup |

#### Customers (res.partner)

| Odoo Feld | Ablage Feld | Transformation |
|-----------|-------------|----------------|
| `id` | `external_id` | String |
| `name` | `name` | Direct |
| `vat` | `tax_id` | Direct |
| `email` | `email` | Direct |
| `phone` | `phone` | Direct |
| `street` | `address.street` | Direct |
| `city` | `address.city` | Direct |
| `zip` | `address.zip` | Direct |
| `country_id` | `address.country` | Lookup |
| `is_company` | `is_company` | Boolean |

### Sync-Service Architektur

```python
# app/services/integrations/odoo_connector.py

from abc import ABC, abstractmethod


class ERPConnector(ABC):
    """Abstract base class fuer ERP-Integrationen."""

    @abstractmethod
    async def connect(self) -> bool:
        """Verbindung herstellen."""
        pass

    @abstractmethod
    async def sync_invoices(self, since: datetime = None) -> SyncResult:
        """Rechnungen synchronisieren."""
        pass

    @abstractmethod
    async def sync_customers(self, since: datetime = None) -> SyncResult:
        """Kunden synchronisieren."""
        pass

    @abstractmethod
    async def sync_suppliers(self, since: datetime = None) -> SyncResult:
        """Lieferanten synchronisieren."""
        pass

    @abstractmethod
    async def update_payment_status(self, invoice_id: str, status: str) -> bool:
        """Zahlungsstatus in ERP aktualisieren."""
        pass


class OdooConnector(ERPConnector):
    """Odoo-spezifische Implementierung."""

    def __init__(self, connection: IntegrationConnection):
        self.base_url = connection.base_url
        self.db = connection.database_name
        self.credentials = connection.credentials
        self.session = None

    async def connect(self) -> bool:
        """Authentifizierung via Odoo JSON-RPC."""
        auth_url = f"{self.base_url}/web/session/authenticate"
        payload = {
            "jsonrpc": "2.0",
            "params": {
                "db": self.db,
                "login": self.credentials["username"],
                "password": self.credentials["password"]
            }
        }
        response = await self.http_client.post(auth_url, json=payload)
        self.session = response.cookies.get("session_id")
        return self.session is not None

    async def sync_invoices(self, since: datetime = None) -> SyncResult:
        """Synchronisiert Rechnungen von Odoo."""
        domain = [("move_type", "in", ["out_invoice", "in_invoice"])]
        if since:
            domain.append(("write_date", ">=", since.isoformat()))

        invoices = await self._search_read(
            model="account.move",
            domain=domain,
            fields=["name", "partner_id", "amount_total", "state", "invoice_date"]
        )

        result = SyncResult()
        for inv in invoices:
            try:
                await self._upsert_invoice(inv)
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append(str(e))

        return result

    async def _search_read(self, model: str, domain: list, fields: list) -> list:
        """Odoo search_read via JSON-RPC."""
        url = f"{self.base_url}/web/dataset/call_kw"
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": model,
                "method": "search_read",
                "args": [domain],
                "kwargs": {"fields": fields}
            }
        }
        response = await self.http_client.post(url, json=payload)
        return response.json()["result"]
```

---

## Implementation Tasks

### Phase 1: Connector-Basis (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 1.1 | [ ] DB-Schema | Connections, Mappings, Logs | Migration fehlerfrei | - |
| 1.2 | [ ] ERPConnector ABC | Abstract Base Class | Interface definiert | 1.1 |
| 1.3 | [ ] OdooConnector | Auth + Basis-Calls | Connect erfolgreich | 1.2 |
| 1.4 | [ ] Credential-Storage | Verschluesselt in DB | Secrets sicher | 1.3 |

### Phase 2: Entity-Sync (2 Wochen)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 2.1 | [ ] Invoice Sync | Odoo → Ablage | Rechnungen importiert | 1.4 |
| 2.2 | [ ] Customer Sync | Bidirektional | Aenderungen beidseitig | 2.1 |
| 2.3 | [ ] Supplier Sync | Bidirektional | Aenderungen beidseitig | 2.2 |
| 2.4 | [ ] Payment Status | Ablage → Odoo | Status aktualisiert | 2.3 |
| 2.5 | [ ] Document Links | Ablage → Odoo | URL in Odoo sichtbar | 2.4 |

### Phase 3: Sync-Modi (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 3.1 | [ ] Scheduled Sync | Celery Beat 15min | Job laeuft regelmaessig | 2.5 |
| 3.2 | [ ] Webhook Receiver | Odoo → Ablage Events | Sofort verarbeitet | 3.1 |
| 3.3 | [ ] Manual Sync | API Trigger | Admin kann starten | 3.2 |
| 3.4 | [ ] Initial Migration | Einmaliger Full-Import | Alle Daten importiert | 3.3 |

### Phase 4: Konflikt-Handling (0.5 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 4.1 | [ ] Konflikt-Erkennung | Hash-Vergleich | Konflikte erkannt | 3.4 |
| 4.2 | [ ] Konflikt-Queue | Admin-UI | Konflikte sichtbar | 4.1 |
| 4.3 | [ ] Resolution-Flow | Manuell oder Auto | Konflikt geloest | 4.2 |

### Phase 5: Frontend & Testing (0.5 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 5.1 | [ ] Settings UI | Verbindungs-Setup | CRUD funktioniert | 4.3 |
| 5.2 | [ ] Status Dashboard | Sync-Uebersicht | Status sichtbar | 5.1 |
| 5.3 | [ ] Integration Tests | Alle Sync-Flows | Tests bestehen | 5.2 |
| 5.4 | [ ] Dokumentation | Setup-Guide | Fuer Admins nutzbar | 5.3 |

---

## Test-Szenarien

### Unit Tests

```python
# tests/unit/services/integrations/test_odoo_connector.py

class TestOdooConnector:

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_odoo_api):
        """Erfolgreiche Authentifizierung."""
        mock_odoo_api.authenticate.return_value = {"session_id": "abc123"}

        connector = OdooConnector(test_connection)
        result = await connector.connect()

        assert result is True
        assert connector.session == "abc123"

    @pytest.mark.asyncio
    async def test_sync_invoices_creates_mappings(self, connector, mock_invoices):
        """Invoice-Sync erstellt Mappings."""
        result = await connector.sync_invoices()

        assert result.records_processed == len(mock_invoices)
        mappings = await get_mappings(entity_type="invoice")
        assert len(mappings) == len(mock_invoices)

    @pytest.mark.asyncio
    async def test_conflict_detected_on_both_changed(self, connector, synced_customer):
        """Konflikt wenn beide Seiten geaendert."""
        # Lokal aendern
        await update_customer(synced_customer.id, {"name": "Local Name"})

        # Extern aendern (Mock)
        mock_external = {"id": synced_customer.external_id, "name": "External Name"}

        result = await connector.sync_customers()

        conflicts = await get_pending_conflicts()
        assert len(conflicts) == 1
        assert "name" in conflicts[0].conflict_fields
```

### Integration Tests

```python
@pytest.mark.integration
class TestOdooIntegration:

    @pytest.mark.asyncio
    async def test_full_sync_workflow(self, async_client, admin_headers, odoo_sandbox):
        """Vollstaendiger Sync-Workflow mit Sandbox."""
        # Initial Sync starten
        response = await async_client.post(
            "/api/v1/integrations/odoo/sync/full",
            headers=admin_headers
        )
        assert response.status_code == 202

        # Warten auf Completion
        await wait_for_sync_completion()

        # Status pruefen
        status = await async_client.get(
            "/api/v1/integrations/odoo/status",
            headers=admin_headers
        )
        assert status.json()["sync"]["last_full_sync"] is not None
        assert status.json()["errors"]["unresolved_conflicts"] == 0
```

---

## Quality Gates

### Vor Merge

- [ ] **Funktionalitaet**
  - [ ] Alle Entity-Typen synchronisieren
  - [ ] Bidirektional wo spezifiziert
  - [ ] Konflikte werden erkannt

- [ ] **Zuverlaessigkeit**
  - [ ] Retry-Logik implementiert
  - [ ] Fehler-Recovery funktioniert
  - [ ] Logging vollstaendig

- [ ] **Sicherheit**
  - [ ] Credentials verschluesselt
  - [ ] Webhook-Secret validiert

### Definition of Done

1. [ ] Verbindung zu Odoo Cloud hergestellt
2. [ ] Rechnungen werden automatisch importiert
3. [ ] Kunden/Lieferanten bidirektional sync
4. [ ] Zahlungsstatus wird an Odoo gemeldet
5. [ ] Admin-UI fuer Konflikte
6. [ ] Dokumentation fuer Setup
