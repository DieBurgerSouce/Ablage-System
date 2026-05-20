# ERP Integration Services

> **Letzte Aktualisierung**: 2026-01-27
> **Version**: 1.0

---

## Übersicht

Dieses Verzeichnis enthält die ERP-Integrationsschicht für die Synchronisation mit externen Buchhaltungs- und Warenwirtschaftssystemen.

---

## Services

| Service | Datei | Beschreibung |
|---------|-------|--------------|
| **BaseConnector** | `base_connector.py` | Abstrakte Basisklasse für Connectors |
| **LexwareConnector** | `lexware_connector.py` | Lexware Integration |
| **OdooConnector** | `odoo_connector.py` | Odoo ERP Integration |
| **SyncEngine** | `sync_engine.py` | Synchronisations-Orchestrierung |
| **FieldMapping** | `field_mapping.py` | Feldzuordnung und Transformation |

---

## BaseConnector

Abstrakte Basisklasse, die das Interface für alle ERP-Connectors definiert.

### Interface

```python
class BaseConnector(ABC):
    @abstractmethod
    async def connect(self) -> bool:
        """Verbindung herstellen."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Verbindung trennen."""

    @abstractmethod
    async def sync_customers(self) -> SyncResult:
        """Kunden synchronisieren."""

    @abstractmethod
    async def sync_suppliers(self) -> SyncResult:
        """Lieferanten synchronisieren."""

    @abstractmethod
    async def sync_invoices(self) -> SyncResult:
        """Rechnungen synchronisieren."""

    @abstractmethod
    async def push_document(self, document: Document) -> PushResult:
        """Dokument an ERP senden."""
```

### SyncResult

```python
class SyncResult(TypedDict):
    success: bool
    created: int
    updated: int
    skipped: int
    errors: List[Dict[str, str]]
    duration_ms: int
```

---

## LexwareConnector

Integration mit Lexware Buchhaltungssoftware.

### Features

- Excel-basierter Import (keine direkte API)
- Kunden/Lieferanten-Synchronisation
- Konflikt-Erkennung und -Behandlung
- Namensvariantenn-Erkennung

### Unterstützte Formate

| Format | Beschreibung |
|--------|--------------|
| `.xlsx` | Lexware Excel-Export |
| `.csv` | Lexware CSV-Export (UTF-8) |

### Spalten-Mapping

| Lexware-Spalte | Ablage-Feld |
|----------------|-------------|
| `Kundennummer` | `primary_customer_number` |
| `Firma` | `name` |
| `Matchcode` | `matchcode` |
| `Straße` | `street` |
| `PLZ` | `postal_code` |
| `Ort` | `city` |
| `IBAN` | `iban` |
| `USt-ID` | `vat_id` |

### Verwendung

```python
from app.services.erp.lexware_connector import LexwareConnector

connector = LexwareConnector(db, company_id)
result = await connector.import_from_excel(
    file_path="/tmp/kunden.xlsx",
    entity_type="customer",
    conflict_mode="skip"  # skip, merge, overwrite
)
```

---

## OdooConnector

Integration mit Odoo ERP (XML-RPC API).

### Features

- Bidirektionale Synchronisation
- Echtzeit-Webhooks
- Multi-Company Support
- Attachment-Sync

### Konfiguration

```python
ODOO_URL: str       # https://odoo.example.com
ODOO_DB: str        # Datenbankname
ODOO_USER: str      # API-User
ODOO_PASSWORD: SecretStr
```

### Unterstützte Modelle

| Odoo-Modell | Ablage-Entity |
|-------------|---------------|
| `res.partner` | BusinessEntity |
| `account.move` | InvoiceTracking |
| `ir.attachment` | Document |
| `account.payment` | Payment |

### Verwendung

```python
from app.services.erp.odoo_connector import OdooConnector

connector = OdooConnector(db, company_id)
await connector.connect()

# Kunden von Odoo abrufen
result = await connector.sync_customers(direction="pull")

# Dokument an Odoo senden
await connector.push_document(document)

await connector.disconnect()
```

---

## SyncEngine

Orchestriert die Synchronisation zwischen Ablage-System und ERP-Systemen.

### Sync-Modi

| Modus | Beschreibung |
|-------|--------------|
| `full` | Vollständige Synchronisation |
| `incremental` | Nur Änderungen seit letztem Sync |
| `delta` | Nur neue Einträge |

### Sync-Richtungen

| Richtung | Beschreibung |
|----------|--------------|
| `pull` | Von ERP nach Ablage |
| `push` | Von Ablage nach ERP |
| `bidirectional` | Beide Richtungen |

### Konfliktbehandlung

| Strategie | Beschreibung |
|-----------|--------------|
| `skip` | Konflikt überspringen |
| `merge` | Felder zusammenführen |
| `overwrite_local` | ERP überschreibt Ablage |
| `overwrite_remote` | Ablage überschreibt ERP |
| `manual` | Zur manuellen Prüfung markieren |

### Verwendung

```python
from app.services.erp.sync_engine import SyncEngine

engine = SyncEngine(db, company_id)
result = await engine.sync(
    connector_type="lexware",
    entity_types=["customers", "suppliers"],
    mode="incremental",
    conflict_strategy="merge"
)
```

---

## FieldMapping

Konfigurierbare Feldzuordnung zwischen ERP-Systemen und Ablage.

### Features

- Feld-Transformation (Formatierung, Normalisierung)
- Bedingte Mappings
- Default-Werte
- Validierung

### Mapping-Definition

```python
CUSTOMER_MAPPING = {
    "name": {
        "source": "Firma",
        "transform": "normalize_company_name",
        "required": True
    },
    "postal_code": {
        "source": "PLZ",
        "transform": "strip",
        "validate": r"^\d{5}$"
    },
    "vat_id": {
        "source": "USt-ID",
        "transform": "normalize_vat_id",
        "required": False
    }
}
```

### Transformationen

| Transform | Beschreibung |
|-----------|--------------|
| `strip` | Leerzeichen entfernen |
| `upper` | Großschreibung |
| `lower` | Kleinschreibung |
| `normalize_company_name` | GmbH → GmbH & Co. KG normalisieren |
| `normalize_vat_id` | DE123456789 Format |
| `normalize_iban` | Leerzeichen entfernen, validieren |

---

## Celery Tasks

| Task | Schedule | Beschreibung |
|------|----------|--------------|
| `erp.sync_customers` | Täglich 04:00 | Kunden synchronisieren |
| `erp.sync_suppliers` | Täglich 04:30 | Lieferanten synchronisieren |
| `erp.sync_invoices` | Alle 4 Stunden | Rechnungen synchronisieren |
| `erp.push_documents` | Kontinuierlich | Neue Dokumente pushen |

---

## Fehler-Codes

| Code | Beschreibung |
|------|--------------|
| `ERP_CONNECTION_FAILED` | Verbindung fehlgeschlagen |
| `ERP_AUTH_FAILED` | Authentifizierung fehlgeschlagen |
| `ERP_SYNC_CONFLICT` | Synchronisationskonflikt |
| `ERP_MAPPING_ERROR` | Feldzuordnung fehlgeschlagen |
| `ERP_VALIDATION_ERROR` | Validierung fehlgeschlagen |

---

## Sicherheit

1. **Credentials**: Alle Passwörter als SecretStr verschlüsselt
2. **TLS**: Verschlüsselte Verbindungen zu ERP-Systemen
3. **Audit Logging**: Alle Sync-Operationen werden protokolliert
4. **Multi-Tenant**: Company-Isolation bei allen Operationen
5. **PII-Schutz**: Sensible Daten werden nicht geloggt
