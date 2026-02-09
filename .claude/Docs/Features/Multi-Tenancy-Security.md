# Multi-Tenancy Security Layer

**Status**: Production-Ready (Migration 210)
**Version**: 1.0
**Implementation Date**: 2026-02-08

## Overview

Die Multi-Tenancy Security Layer implementiert eine umfassende Mandanten-Isolierung auf Datenbank-Ebene mit Row-Level Security (RLS) Policies und einer konfigurierbaren Verwaltungsschicht.

## Architecture

```
+----------------------------------------------------------+
|                    Application Layer                     |
+----------------------------------------------------------+
|  TenantContextMiddleware (Request-Ebene)                |
|  - Extrahiert tenant_id aus JWT/CompanyContext          |
|  - Setzt request.state.tenant_id                        |
+----------------------------------------------------------+
|  Database Session (vor jedem Query)                     |
|  - SET app.current_tenant_id = :tenant_id               |
|  - SET app.current_user_is_superuser = :is_superuser    |
+----------------------------------------------------------+
|  PostgreSQL Row-Level Security                          |
|  - tenant_isolation_* Policies (27 Tabellen)            |
|  - superuser_bypass_* Policies                          |
|  - FORCE ROW LEVEL SECURITY                             |
+----------------------------------------------------------+
|                    Data Layer                            |
|  - 27 Tabellen mit company_id-basierter Isolation       |
|  - TenantConfig (Features, Quotas, Branding)            |
+----------------------------------------------------------+
```

## Components

### 1. Middleware Layer

#### TenantContextMiddleware

**Pfad**: `app/middleware/tenant_context.py`

**Aufgaben**:
- Extrahiert `company_id` aus `request.state` (gesetzt von `CompanyContextMiddleware`)
- Validiert UUID-Format
- Setzt `request.state.tenant_id` für nachgelagerte Services
- Exempt-Liste für öffentliche Endpunkte

**Exempt Paths**:
- `/api/v1/health`
- `/api/v1/auth/login`
- `/api/v1/auth/register`
- `/docs`, `/redoc`, `/openapi.json`
- `/metrics`

**Integration**:
```python
# In app/main.py
from app.middleware.tenant_context import TenantContextMiddleware

app.add_middleware(TenantContextMiddleware)
```

### 2. Database Model

#### TenantConfig

**Pfad**: `app/db/models_tenant_config.py`

**Felder**:
- `id`: UUID (Primary Key)
- `company_id`: UUID (Foreign Key → companies.id, UNIQUE)
- `features`: JSONB (Feature-Flags)
- `quotas`: JSONB (Kontingente)
- `branding`: JSONB (Branding-Konfiguration)
- `is_active`: Boolean (Mandanten-Status)
- `created_at`, `updated_at`: Timestamps

**Indizes**:
- `ix_tenant_configs_company_id` (company_id)
- `ix_tenant_configs_is_active` (is_active)

**Beispiel-Daten**:
```json
{
  "features": {
    "ocr_enabled": true,
    "datev_integration": true,
    "max_users": 50,
    "lexware_import": true
  },
  "quotas": {
    "documents_per_month": 10000,
    "storage_gb": 100,
    "api_calls_per_day": 50000
  },
  "branding": {
    "logo_url": "https://cdn.example.com/logo.png",
    "primary_color": "#0066CC",
    "company_name": "Musterfirma GmbH"
  }
}
```

### 3. Service Layer

#### TenantConfigService

**Pfad**: `app/services/tenant/tenant_config_service.py`

**Methoden**:

##### `get_tenant_config(company_id: UUID) -> Optional[TenantConfig]`
Holt die Konfiguration eines Mandanten.

##### `create_or_update_config(...) -> TenantConfig`
Erstellt oder aktualisiert die Mandanten-Konfiguration.
- Merged Features/Quotas/Branding mit existierenden Werten
- Erstellt neue Konfiguration wenn nicht vorhanden

##### `get_tenant_features(company_id: UUID) -> Dict[str, bool]`
Gibt nur boolean Feature-Flags zurück.

##### `check_tenant_quota(company_id: UUID, resource: str, current_usage: int) -> Dict`
Prüft ob ein Mandant innerhalb seiner Kontingente liegt.

**Return Format**:
```python
{
    "within_quota": bool,
    "limit": int,        # -1 = unbegrenzt
    "usage": int,
    "remaining": int     # -1 = unbegrenzt
}
```

##### `deactivate_tenant(company_id: UUID) -> bool`
Deaktiviert einen Mandanten (kein Login/Zugriff mehr).

##### `activate_tenant(company_id: UUID) -> bool`
Aktiviert einen deaktivierten Mandanten.

**Fehlerbehandlung**:
- Fail-open bei Quota-Checks (bei Fehler: erlauben)
- Strukturierte Logging mit `structlog`
- `safe_error_log` für PII-sichere Fehler-Logs

### 4. Admin API

#### Tenant Admin Endpoints

**Pfad**: `app/api/v1/tenant_admin.py`
**Prefix**: `/api/v1/admin/tenants`
**Auth**: Nur Superuser (`get_current_superuser`)

##### GET `/{company_id}/config`
Holt die Konfiguration eines Mandanten.

**Response**: `TenantConfigResponse`

##### PATCH `/{company_id}/config`
Aktualisiert Features, Quotas oder Branding.

**Request**: `TenantConfigUpdate`
```json
{
  "features": {"ocr_enabled": true},
  "quotas": {"documents_per_month": 20000},
  "branding": {"primary_color": "#FF0000"}
}
```

##### GET `/{company_id}/features`
Holt nur die Feature-Flags (boolean).

**Response**: `TenantFeaturesResponse`
```json
{
  "company_id": "uuid",
  "features": {
    "ocr_enabled": true,
    "datev_integration": false
  }
}
```

##### GET `/{company_id}/usage`
Holt Quota-Nutzungsübersicht.

**Response**: `TenantUsageResponse`
```json
{
  "company_id": "uuid",
  "quotas": {...},
  "usage_summary": {
    "documents_per_month": {
      "limit": 10000,
      "usage": 5000,
      "remaining": 5000,
      "within_quota": true
    }
  }
}
```

##### POST `/{company_id}/deactivate`
Deaktiviert einen Mandanten (204 No Content).

##### POST `/{company_id}/activate`
Aktiviert einen Mandanten (204 No Content).

### 5. Database Migration

#### Migration 210: Row-Level Security

**Pfad**: `alembic/versions/210_add_rls_policies.py`
**Revision**: `210_add_rls_policies`
**Down Revision**: `209_add_dashboard_shares`

**Schritte**:

1. **Erstellt `tenant_configs` Tabelle**
2. **Aktiviert RLS auf 27 Tabellen**:
   - documents
   - invoices
   - approval_requests
   - business_entities
   - bank_transactions
   - invoice_positions
   - banking_accounts
   - banking_category_rules
   - banking_reconciliation
   - banking_skonto_tracking
   - compliance_audits
   - custom_fields
   - custom_tags
   - dashboard_shares
   - document_chains
   - document_chain_links
   - document_versions
   - entity_contracts
   - entity_risk_scores
   - folder_categories
   - lexware_customers
   - lexware_suppliers
   - notification_rules
   - saved_searches
   - slack_channels
   - slack_integrations
   - user_company_roles

3. **Erstellt RLS Policies**:

**Tenant Isolation Policy** (pro Tabelle):
```sql
CREATE POLICY tenant_isolation_<table> ON <table>
USING (company_id = current_setting('app.current_tenant_id', true)::uuid);
```

**Superuser Bypass Policy** (pro Tabelle):
```sql
CREATE POLICY superuser_bypass_<table> ON <table>
USING (current_setting('app.current_user_is_superuser', true)::boolean = true);
```

4. **Aktiviert FORCE ROW LEVEL SECURITY**:
```sql
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
```

**IMPORTANT**: `current_setting(..., true)` mit `true` Parameter verhindert Fehler wenn Variable nicht gesetzt ist (gibt NULL zurück).

## Database Session Integration

### Setting RLS Variables

Die RLS Session-Variablen müssen bei jedem Database Query gesetzt werden. Dies geschieht typischerweise in der Database Session Dependency:

```python
# In app/api/dependencies.py
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        # Setze RLS Variablen
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id:
            await session.execute(
                text("SET app.current_tenant_id = :tenant_id"),
                {"tenant_id": str(tenant_id)}
            )

        # Setze Superuser-Flag
        user = getattr(request.state, "user", None)
        if user and user.is_superuser:
            await session.execute(
                text("SET app.current_user_is_superuser = true")
            )

        try:
            yield session
        finally:
            # Cleanup
            await session.execute(text("RESET app.current_tenant_id"))
            await session.execute(text("RESET app.current_user_is_superuser"))
```

## Security Features

### 1. Row-Level Security (RLS)

**Vorteile**:
- **Datenbank-Ebene**: Schutz auch bei SQL-Injection
- **Transparent**: Services müssen nicht manuell filtern
- **Auditierbar**: Policies sind zentral definiert
- **Fail-Safe**: FORCE RLS verhindert Bypass durch Table Owner

**Policies**:
- **tenant_isolation_***: Nur eigene Mandanten-Daten sichtbar
- **superuser_bypass_***: Superuser sehen alles (für Admin-API)

### 2. Feature Flags

Granulare Kontrolle über Features pro Mandant:

```python
# Service-Ebene
features = await tenant_service.get_tenant_features(company_id)

if not features.get("ocr_enabled", False):
    raise HTTPException(
        status_code=403,
        detail="OCR-Feature nicht aktiviert"
    )
```

### 3. Quota Management

Verhindert Ressourcen-Überlastung:

```python
# Vor Dokument-Upload
quota = await tenant_service.check_tenant_quota(
    company_id=company_id,
    resource="documents_per_month",
    current_usage=current_doc_count
)

if not quota["within_quota"]:
    raise HTTPException(
        status_code=429,
        detail=f"Quota überschritten: {quota['usage']}/{quota['limit']}"
    )
```

### 4. Tenant Deactivation

Sofortige Sperrung bei Zahlungsausfall/Vertragsende:

```python
# Deaktivierung
await tenant_service.deactivate_tenant(company_id)

# Login wird automatisch blockiert (via middleware)
if not tenant_config.is_active:
    raise HTTPException(status_code=403, detail="Mandant deaktiviert")
```

## Testing

### Unit Tests

**Service Tests**: `tests/unit/services/test_tenant_config.py`
- Konfiguration erstellen/aktualisieren
- Feature-Flags abrufen
- Quota-Checks (innerhalb/außerhalb/unbegrenzt)
- Tenant aktivieren/deaktivieren

**API Tests**: `tests/unit/api/test_tenant_admin_api.py`
- GET/PATCH Config
- GET Features/Usage
- POST Activate/Deactivate
- 404/500 Error Handling

**Middleware Tests**: `tests/unit/middleware/test_tenant_context.py`
- Exempt Paths
- Tenant Context Extraction
- UUID Validation
- Error Handling

### Integration Tests

**RLS Policy Tests** (TODO):
```python
# Test: Mandant A sieht nur eigene Dokumente
async def test_rls_document_isolation():
    # User von Company A einloggen
    # Dokument von Company B erstellen
    # Query: sollte leer sein
    ...

# Test: Superuser sieht alles
async def test_superuser_bypass():
    # Superuser einloggen
    # Query über mehrere Companies
    # Sollte alle Dokumente zurückgeben
    ...
```

## Performance Considerations

### 1. Index-Optimierung

Alle RLS-Tabellen haben `company_id` Index:
```sql
CREATE INDEX ix_<table>_company_id ON <table>(company_id);
```

### 2. Connection Pooling

RLS Session-Variablen sind pro Connection:
- AsyncPG Pool unterstützt `SET` commands
- Variablen werden nach jeder Session zurückgesetzt

### 3. Query-Planung

PostgreSQL optimiert RLS Policies:
```sql
EXPLAIN ANALYZE
SELECT * FROM documents
WHERE category = 'invoice';

-- Filter wird kombiniert:
-- WHERE company_id = 'xxx' AND category = 'invoice'
```

## Deployment

### 1. Migration ausführen

```bash
# Development
docker-compose exec backend alembic upgrade head

# Production
alembic upgrade 210_add_rls_policies
```

### 2. Middleware registrieren

```python
# In app/main.py
from app.middleware.tenant_context import TenantContextMiddleware

app.add_middleware(TenantContextMiddleware)
```

### 3. Admin API registrieren

```python
# In app/main.py oder app/api/v1/__init__.py
from app.api.v1 import tenant_admin

app.include_router(
    tenant_admin.router,
    prefix="/api/v1",
    tags=["admin"],
)
```

### 4. Database Session anpassen

Siehe "Database Session Integration" oben.

### 5. Initial Tenant Configs erstellen

```python
# Für alle existierenden Companies
from app.db.models_company import Company
from app.services.tenant import get_tenant_config_service

companies = await session.execute(select(Company))
for company in companies.scalars():
    await tenant_service.create_or_update_config(
        company_id=company.id,
        features={
            "ocr_enabled": True,
            "max_users": 10,
        },
        quotas={
            "documents_per_month": 1000,
            "storage_gb": 10,
        },
    )
```

## Monitoring

### Key Metrics

1. **RLS Policy Violations**:
   - Log wenn Queries leer zurückkommen (sollte nicht passieren)
   - Monitor PostgreSQL Logs für Policy-Fehler

2. **Quota Überschreitungen**:
   - Counter für 429 Responses
   - Alert bei häufigen Quota-Überschreitungen

3. **Tenant Deactivations**:
   - Log alle Deaktivierungen mit Grund
   - Alert bei unerwarteten Deaktivierungen

### Logging

```python
# Strukturierte Logs mit structlog
logger.info(
    "tenant_quota_checked",
    company_id=str(company_id),
    resource=resource,
    within_quota=result["within_quota"],
    usage=result["usage"],
    limit=result["limit"],
)
```

## Rollback

### Migration Rollback

```bash
alembic downgrade 209_add_dashboard_shares
```

**Achtung**: Rollback entfernt:
- Alle RLS Policies
- Die `tenant_configs` Tabelle
- Tenant-Konfigurationen gehen verloren

### Middleware Deaktivieren

```python
# In app/main.py
# app.add_middleware(TenantContextMiddleware)  # Auskommentieren
```

## Future Enhancements

### 1. Erweiterte Quota-Types

```python
quotas = {
    "documents_per_month": 10000,
    "storage_gb": 100,
    "api_calls_per_day": 50000,
    "ocr_pages_per_month": 5000,
    "users_max": 50,
    "concurrent_uploads": 10,
}
```

### 2. Automatische Quota-Überwachung

Celery Task für tägliche Checks:
```python
@celery_app.task
async def check_tenant_quotas():
    # Für jeden Mandanten
    # - Aktuelle Nutzung laden
    # - Mit Quotas vergleichen
    # - Warnung bei >80%
    # - Automatische Deaktivierung bei >100%
```

### 3. Feature-Flag UI

Admin-Interface für Feature-Management:
- Feature-Templates (Starter, Professional, Enterprise)
- Bulk-Updates über alle Mandanten
- Feature-Rollout Schedule

### 4. Branding-Integration

Frontend liest Branding aus `TenantConfig`:
```typescript
const branding = await api.get('/api/v1/tenant/branding');
document.documentElement.style.setProperty('--primary-color', branding.primary_color);
```

### 5. Audit-Logging

Track alle Änderungen an Tenant-Konfigurationen:
```python
class TenantConfigAudit(Base):
    config_id: UUID
    changed_by: UUID
    changed_at: datetime
    field: str
    old_value: JSONB
    new_value: JSONB
```

## Troubleshooting

### Problem: Queries geben keine Daten zurück

**Ursache**: RLS Variable nicht gesetzt oder falsche UUID

**Lösung**:
```sql
-- Manuell prüfen
SHOW app.current_tenant_id;

-- Manuell setzen (für Debugging)
SET app.current_tenant_id = 'xxx-xxx-xxx-xxx';
```

### Problem: Superuser sieht keine Daten

**Ursache**: `current_user_is_superuser` nicht gesetzt

**Lösung**:
```python
# In get_db() Dependency
if user and user.is_superuser:
    await session.execute(text("SET app.current_user_is_superuser = true"))
```

### Problem: Migration schlägt fehl

**Ursache**: Tabellen ohne `company_id` Spalte

**Lösung**:
```bash
# Prüfe welche Tabellen RLS bekommen sollten
SELECT table_name
FROM information_schema.columns
WHERE column_name = 'company_id';

# Passe Migration an (entferne Tabellen ohne company_id)
```

## References

- **PostgreSQL RLS Docs**: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- **FastAPI Middleware**: https://fastapi.tiangolo.com/advanced/middleware/
- **SQLAlchemy Session Variables**: https://docs.sqlalchemy.org/en/14/core/connections.html#sqlalchemy.engine.Connection.execute

---

**Version**: 1.0
**Last Updated**: 2026-02-08
**Migration**: 210
