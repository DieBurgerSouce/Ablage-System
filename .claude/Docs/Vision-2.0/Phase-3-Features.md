# Vision 2.0 - Phase 3 Features (F8-F10)

**Status**: ✅ Production-Ready
**Version**: 1.0
**Erstellt**: 2026-01-28

---

## Überblick

Phase 3 implementiert drei fortgeschrittene Backend-Patterns für Enterprise-Anforderungen:
- **F8**: Event-Sourcing (Hybrid-Ansatz)
- **F9**: GraphQL-ähnliche API
- **F10**: Offline-First Synchronisierung

---

## F8: Event-Sourcing (Hybrid-Ansatz)

### Beschreibung

Event-Sourcing für kritische Geschäftsprozesse mit Append-Only Event Store, Snapshots für Performance und Event-Replay für Zustandsrekonstruktion.

### Komponenten

#### EventStore
- **Pfad**: `app/services/event_sourcing/event_store.py`
- **Features**:
  - Append-Only Event Storage
  - Automatische Sequenznummern
  - Correlation-IDs für Event-Ketten
  - Multi-Tenant Isolation

```python
event_store = EventStore()
stored_event = await event_store.append(
    aggregate_type="document",
    aggregate_id=document_id,
    event_type="document_ocr_completed",
    event_data={"text": ocr_text, "confidence": 0.95},
    company_id=company_id,
    user_id=user_id,
    correlation_id=correlation_id,
    db=db,
)
```

#### SnapshotService
- **Pfad**: `app/services/event_sourcing/snapshot_service.py`
- **Features**:
  - Periodische Snapshots (alle 50 Events)
  - Snapshot-Cleanup (behält letzte 5)
  - Versionierung

```python
snapshot_service = SnapshotService()
snapshot = await snapshot_service.create_snapshot(
    aggregate_type="invoice",
    aggregate_id=invoice_id,
    state=current_state,
    sequence_number=100,
    company_id=company_id,
    db=db,
)
```

#### ProjectionService
- **Pfad**: `app/services/event_sourcing/projection_service.py`
- **Features**:
  - Event-Replay ab letztem Snapshot
  - Temporal Queries (Zeitreisen)
  - Event-Handler für alle Aggregate-Typen

```python
projection_service = ProjectionService()
current_state = await projection_service.project(
    aggregate_type="document",
    aggregate_id=document_id,
    db=db,
)

# Temporal Query: Zustand bei Sequenz 42
past_state = await projection_service.project_at_sequence(
    aggregate_type="document",
    aggregate_id=document_id,
    target_sequence=42,
    db=db,
)
```

### API Endpoints

**Base Path**: `/api/v1/event-sourcing`

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/events/{aggregate_type}/{aggregate_id}` | GET | Events für Aggregat |
| `/snapshot/{aggregate_type}/{aggregate_id}` | GET | Neuester Snapshot |
| `/projection/{aggregate_type}/{aggregate_id}` | GET | Aktueller Zustand (projiziert) |
| `/stats` | GET | Event-Statistiken |

### Unterstützte Aggregate-Typen

- `document` - Dokumente
- `invoice` - Rechnungen
- `payment` - Zahlungen
- `entity` - Geschäftspartner
- `alert` - Alerts
- `workflow` - Workflows

### Event-Typen

#### Document Events
- `document_created`
- `document_ocr_started`
- `document_ocr_completed`
- `document_ocr_failed`

#### Invoice Events
- `invoice_created`
- `invoice_paid`
- `payment_received`

#### Alert Events
- `alert_created`
- `alert_acknowledged`
- `alert_resolved`

#### Workflow Events
- `workflow_started`
- `workflow_step_completed`
- `workflow_completed`

### Datenmodell

#### DomainEvent (Tabelle: `domain_events`)
```python
id: UUID
company_id: UUID
aggregate_type: String(50)
aggregate_id: UUID
sequence_number: BigInteger
event_type: String(100)
event_data: JSONB
metadata: JSONB
correlation_id: UUID (nullable)
causation_id: UUID (nullable)
user_id: UUID (nullable)
created_at: DateTime
```

**Constraints**:
- Unique: `(aggregate_type, aggregate_id, sequence_number)`
- Index: `(company_id, aggregate_type, aggregate_id, sequence_number)`
- Index: `(company_id, event_type)`
- Index: `(correlation_id)`

#### EventSnapshot (Tabelle: `event_snapshots`)
```python
id: UUID
company_id: UUID
aggregate_type: String(50)
aggregate_id: UUID
sequence_number: BigInteger
state: JSONB
version: Integer
created_at: DateTime
```

**Index**: `(company_id, aggregate_type, aggregate_id)`

### Best Practices

1. **Immutability**: Events niemals ändern oder löschen
2. **Snapshots**: Automatisch alle 50 Events für Performance
3. **Correlation-IDs**: Für Event-Ketten verwenden
4. **Projections**: Bei Bedarf mit Snapshots optimieren
5. **Cleanup**: Alte Snapshots periodisch löschen (behalte 5)

### Security

- **Multi-Tenant**: RLS über `company_id`
- **Keine PII in Events**: Nur IDs, keine Namen/Adressen
- **Audit-Trail**: Events sind unveränderlich
- **Validierung**: Aggregate-Types gegen Whitelist

---

## F9: GraphQL-ähnliche API

### Beschreibung

REST-basierte flexible Query-API mit Field Selection, Filterung und Schema-Discovery. Ähnlich GraphQL aber ohne zusätzliche Bibliotheken.

### Komponenten

#### QueryBuilder
- **Pfad**: `app/api/v1/graphql_api.py`
- **Features**:
  - Sichere Query-Konstruktion
  - Field Projection
  - Filter-Operatoren (eq, like, in, gte, lte)
  - Paginierung und Sortierung

### API Endpoints

**Base Path**: `/api/v1/graphql`

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/query` | POST | Flexible Query ausführen |
| `/schema` | GET | Schema für Entity-Typ |

### Query-Format

```json
{
  "entity_type": "document",
  "fields": ["id", "filename", "status", "created_at"],
  "filters": {
    "status": "completed",
    "created_at": {"gte": "2026-01-01T00:00:00Z"}
  },
  "limit": 20,
  "offset": 0,
  "order_by": "created_at",
  "order_desc": true
}
```

### Filter-Operatoren

| Operator | Beschreibung | Beispiel |
|----------|--------------|----------|
| Direkt | Exakte Übereinstimmung | `"status": "completed"` |
| Like | Wildcard-Suche | `"filename": "%rechnung%"` |
| In | Liste von Werten | `"status": ["pending", "processing"]` |
| gte | Größer/Gleich | `"amount": {"gte": 100.0}` |
| lte | Kleiner/Gleich | `"amount": {"lte": 1000.0}` |
| gt | Größer | `"created_at": {"gt": "2026-01-01"}` |
| lt | Kleiner | `"created_at": {"lt": "2026-12-31"}` |

### Unterstützte Entity-Typen

#### Document
```python
fields = [
    "id",           # UUID
    "filename",     # String
    "status",       # String
    "ocr_text",     # String (nullable)
    "ocr_confidence", # Float (nullable)
    "created_at",   # DateTime
    "updated_at",   # DateTime
    "folder_id",    # UUID (nullable)
]
```

#### BusinessEntity
```python
fields = [
    "id",                  # UUID
    "name",                # String
    "entity_type",         # String (customer/supplier)
    "risk_score",          # Float (nullable)
    "payment_delay_days",  # Float (nullable)
    "default_rate",        # Float (nullable)
    "created_at",          # DateTime
]
```

#### InvoiceTracking
```python
fields = [
    "id",              # UUID
    "invoice_number",  # String
    "amount",          # Decimal
    "status",          # String
    "due_date",        # Date (nullable)
    "paid_date",       # Date (nullable)
    "dunning_level",   # Integer (nullable)
    "entity_id",       # UUID (nullable)
]
```

#### Alert
```python
fields = [
    "id",          # UUID
    "alert_code",  # String
    "title",       # String
    "category",    # String
    "severity",    # String
    "status",      # String
    "created_at",  # DateTime
]
```

### Response-Format

```json
{
  "entity_type": "document",
  "total_count": 156,
  "items": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "filename": "rechnung_2026.pdf",
      "status": "completed",
      "created_at": "2026-01-15T10:30:00Z"
    }
  ],
  "has_more": true,
  "offset": 0,
  "limit": 20
}
```

### Schema Discovery

```bash
GET /api/v1/graphql/schema?entity_type=document
```

```json
{
  "types": [
    {
      "type_name": "Document",
      "description": "Dokument mit OCR-Daten",
      "fields": [
        {
          "name": "id",
          "type": "UUID",
          "nullable": false,
          "description": "Dokument-ID"
        }
      ]
    }
  ]
}
```

### Security

- **Whitelist-Validierung**: Entity-Types und Feldnamen
- **SQL-Injection-Schutz**: Regex-Patterns für Felder
- **Multi-Tenant**: Automatische `company_id` Filterung
- **Rate-Limiting**: Standard API-Limits
- **Field Projection**: Nur angefragte Felder zurückgeben

### Best Practices

1. **Field Selection**: Nur benötigte Felder abfragen
2. **Paginierung**: Immer `limit` und `offset` verwenden
3. **Indizes**: Sortier- und Filter-Felder sollten indiziert sein
4. **Schema**: Verfügbare Felder via Schema-Endpoint prüfen

---

## F10: Offline-First Synchronisierung

### Beschreibung

Delta-Synchronisierung für Offline-Workflows mit Konfliktlösung und Last-Write-Wins Strategie.

### Komponenten

#### DeltaSyncService
- **Pfad**: `app/services/sync/delta_sync_service.py`
- **Features**:
  - Delta-Queries (Änderungen seit Timestamp)
  - Push-Sync mit Konfliktlösung
  - Optimistic Locking via Version-Nummern
  - Merge-Strategien

### API Endpoints

**Base Path**: `/api/v1/sync`

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/changes` | GET | Änderungen seit Timestamp |
| `/push` | POST | Änderungen vom Client pushen |
| `/resolve-conflict` | POST | Konflikt manuell lösen |
| `/status` | GET | Sync-Status abrufen |

### Delta-Query

**Endpoint**: `GET /api/v1/sync/changes`

**Query-Parameter**:
- `entity_type`: Entitätstyp (document, entity, invoice, alert)
- `since`: ISO-Timestamp (z.B. `2026-01-01T00:00:00Z`)
- `limit`: Max. Anzahl (default: 100, max: 500)
- `offset`: Offset für Paginierung

**Response**:
```json
{
  "entity_type": "document",
  "changes": [
    {
      "entity_type": "document",
      "entity_id": "123e4567-...",
      "operation": "update",
      "data": {
        "id": "123e4567-...",
        "filename": "rechnung.pdf",
        "status": "completed",
        "updated_at": "2026-01-15T10:30:00Z"
      },
      "server_timestamp": "2026-01-15T10:30:00Z"
    }
  ],
  "server_timestamp": "2026-01-28T12:00:00Z",
  "has_more": false
}
```

### Push-Sync

**Endpoint**: `POST /api/v1/sync/push`

**Request**:
```json
{
  "changes": [
    {
      "entity_type": "document",
      "entity_id": "123e4567-...",
      "operation": "update",
      "data": {
        "status": "completed",
        "ocr_text": "..."
      },
      "client_timestamp": "2026-01-15T10:25:00Z",
      "version": 5
    }
  ],
  "conflict_resolution": "last_write_wins"
}
```

**Response**:
```json
{
  "accepted": 8,
  "rejected": 1,
  "conflicts": [
    {
      "entity_type": "document",
      "entity_id": "123e4567-...",
      "reason": "version_mismatch",
      "server_version": {...},
      "client_version": {...},
      "resolved": {...}
    }
  ],
  "server_timestamp": "2026-01-28T12:00:00Z"
}
```

### Konfliktlösungs-Strategien

| Strategie | Beschreibung |
|-----------|--------------|
| `last_write_wins` | Neuer Timestamp gewinnt (Default) |
| `server_wins` | Server-Version wird immer behalten |
| `client_wins` | Client-Version wird übernommen |
| `merge` | Intelligente Merge-Strategie |

### Merge-Strategie

Bei `conflict_resolution: "merge"`:

1. **Basis**: Server-Version
2. **Client-Werte übernehmen wenn**:
   - Server-Wert ist `null` oder leer
   - Listen: Unique merge
   - Dicts: Recursive merge
3. **Geschützte Felder**: `id`, `created_at`, `company_id` nicht mergen

### Optimistic Locking

```python
# Client sendet Version mit
{
  "entity_id": "...",
  "operation": "update",
  "version": 5,  # Client kennt Version 5
  "data": {...}
}

# Server prüft Version
# Wenn Server Version != 5 → Konflikt
```

### Sync-Status

**Endpoint**: `GET /api/v1/sync/status`

```json
{
  "last_sync": "2026-01-15T10:30:00Z",
  "pending_changes": 0,
  "server_timestamp": "2026-01-28T12:00:00Z",
  "sync_enabled": true
}
```

### Unterstützte Entity-Typen

- `document`
- `entity` (BusinessEntity)
- `invoice` (InvoiceTracking)
- `alert`
- `workflow`
- `payment`

### Security

- **Multi-Tenant**: Automatische `company_id` Filterung
- **Version-Check**: Optimistic Locking verhindert Lost Updates
- **Operation-Whitelist**: Nur `create`, `update`, `delete`
- **Entity-Type-Whitelist**: Nur erlaubte Typen
- **Validierung**: Timestamps und IDs

### Best Practices

1. **Regelmäßige Syncs**: Alle 5-15 Minuten
2. **Batch-Größe**: Max. 100 Changes pro Push
3. **Timestamps**: Server-Timestamp für nächsten Sync verwenden
4. **Versionen**: Bei Updates immer Version mitsenden
5. **Konflikte**: Log conflicts für User-Review
6. **Offline-Queue**: Changes lokal speichern bis Online

### Workflow-Beispiel

```python
# 1. Änderungen abrufen
delta = await get_changes_since(
    entity_type="document",
    since=last_sync,
)

# 2. Lokale DB aktualisieren
for change in delta.changes:
    update_local_db(change)

# 3. Lokale Änderungen pushen
result = await push_changes(
    changes=local_pending_changes,
    conflict_resolution="last_write_wins",
)

# 4. Konflikte behandeln
for conflict in result.conflicts:
    log_conflict(conflict)
    # Optional: User-Review

# 5. Timestamp speichern
last_sync = delta.server_timestamp
```

---

## Integration & Testing

### Event-Sourcing Tests

```python
async def test_event_append():
    """Event sollte mit korrekter Sequenznummer gespeichert werden."""
    event_store = EventStore()

    event = await event_store.append(
        aggregate_type="document",
        aggregate_id=doc_id,
        event_type="document_created",
        event_data={"filename": "test.pdf"},
        company_id=company_id,
        db=db,
    )

    assert event.sequence_number == 1
    assert event.event_type == "document_created"

async def test_projection():
    """Projektion sollte korrekten Zustand rekonstruieren."""
    projection_service = ProjectionService()

    state = await projection_service.project(
        aggregate_type="document",
        aggregate_id=doc_id,
        db=db,
    )

    assert state["status"] == "completed"
```

### GraphQL Tests

```python
async def test_graphql_query():
    """GraphQL-Query sollte nur angefragte Felder zurückgeben."""
    request = GraphQLQueryRequest(
        entity_type="document",
        fields=["id", "filename"],
        filters={"status": "completed"},
        limit=10,
    )

    response = await execute_query(request, current_user, db)

    assert len(response.items) <= 10
    assert all("id" in item and "filename" in item for item in response.items)
    assert all("ocr_text" not in item for item in response.items)
```

### Sync Tests

```python
async def test_delta_sync():
    """Delta-Sync sollte nur Änderungen seit Timestamp zurückgeben."""
    sync_service = DeltaSyncService()

    delta = await sync_service.get_changes_since(
        entity_type="document",
        since=yesterday,
        company_id=company_id,
        db=db,
    )

    assert all(
        datetime.fromisoformat(c["updated_at"]) > yesterday
        for c in delta.changes
    )

async def test_conflict_resolution():
    """Konfliktlösung sollte Last-Write-Wins verwenden."""
    sync_service = DeltaSyncService()

    resolved = await sync_service.resolve_conflict(
        entity_type="document",
        entity_id=doc_id,
        server_version={"updated_at": "2026-01-15T10:00:00Z", "status": "pending"},
        client_version={"updated_at": "2026-01-15T10:05:00Z", "status": "completed"},
        strategy=ConflictResolution.LAST_WRITE_WINS,
    )

    assert resolved["status"] == "completed"  # Client ist neuer
```

---

## Performance

### Event-Sourcing

- **Snapshots**: Alle 50 Events für schnelleres Replay
- **Indizes**: Optimiert für Aggregate-Queries
- **Batch-Inserts**: Bei Event-Replay
- **Cleanup**: Alte Snapshots periodisch löschen

### GraphQL-API

- **Field Projection**: Nur angeforderte Felder laden
- **Paginierung**: Max. 100 Items pro Request
- **Indizes**: Auf Filter- und Sort-Felder
- **Query-Caching**: Bei häufigen Queries

### Offline-Sync

- **Batch-Größe**: 100 Changes optimal
- **Timestamps**: Index auf `updated_at`
- **Versionen**: Optimistic Locking minimiert Konflikte
- **Background-Sync**: Alle 5-15 Minuten

---

## Monitoring

### Metrics

```python
# Event-Sourcing
- event_appended_total
- snapshot_created_total
- projection_duration_seconds

# GraphQL
- graphql_query_total
- graphql_query_duration_seconds
- graphql_query_results_total

# Sync
- sync_changes_retrieved_total
- sync_changes_pushed_total
- sync_conflicts_total
```

### Logging

Alle Services nutzen strukturiertes Logging mit `structlog`:

```python
logger.info(
    "event_appended",
    aggregate_type=aggregate_type,
    event_type=event_type,
    sequence_number=next_seq,
)
```

---

## Troubleshooting

### Event-Sourcing

**Problem**: Projektion dauert lange
- **Lösung**: Snapshots prüfen, ggf. Intervall verkleinern

**Problem**: Event-Duplikate
- **Lösung**: Unique-Constraint auf `(aggregate_type, aggregate_id, sequence_number)` verhindert dies

### GraphQL-API

**Problem**: Query zu langsam
- **Lösung**: Indizes auf Filter-Felder prüfen, Field Projection nutzen

**Problem**: SQL-Injection Fehler
- **Lösung**: Regex-Validierung für Feldnamen aktiv

### Offline-Sync

**Problem**: Viele Konflikte
- **Lösung**: Optimistic Locking verwenden, Sync-Intervall verkleinern

**Problem**: Changes fehlen
- **Lösung**: `updated_at` Index prüfen, Timestamp-Format validieren

---

## Roadmap

### Geplante Erweiterungen

1. **Event-Sourcing**:
   - Event-Bus für reaktive Projektionen
   - Event-Schema-Validierung
   - Event-Migration-Tools

2. **GraphQL-API**:
   - Aggregationen (SUM, AVG, COUNT)
   - Nested Queries
   - Subscriptions (WebSocket)

3. **Offline-Sync**:
   - CRDT-basierte Konfliktlösung
   - Selective Sync (Filter)
   - Background-Sync Worker

---

## Kontakt

Bei Fragen zu Phase 3 Features:
- **Dokumentation**: Siehe `.claude/Docs/Vision-2.0/`
- **Issues**: `.claude/memory/KNOWN_ISSUES.md`
- **Changes**: `.claude/memory/RECENT_CHANGES.md`
