# DATEV Connect Integration (NEU: Januar 2026)

**Status**: Production-Ready
**Migration**: 145 (add_datev_connect)

**Core Services** (`app/services/datev/connect/`):
- `DATEVConnector` - ERPConnector-basiert, OAuth2-Authentifizierung
- `DATEVAuthService` - OAuth2-Flow, Token-Refresh, CSRF-Schutz
- `KontierungsvorschlagService` - ML-basierte Kontierungsvorschlaege
- `GoBDComplianceService` - Festschreibung mit SHA-256 Hash

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| OAuth2 | DATEVconnect OAuth2-Authentifizierung mit Token-Refresh |
| Stammdaten | Bidirektionale Sync von Kunden/Lieferanten/Konten |
| Buchungsstapel | Push zu DATEV mit GoBD-konformer Festschreibung |
| Belegbilder | Upload zu DATEV Unternehmen Online (DUO) |
| Kontierung | ML-basierte Vorschlaege mit Learning-Loop |
| GoBD | SHA-256 Hash, Unveraenderbarkeit, Audit-Trail |

**API Endpoints**: `/api/v1/datev-connect/*`

**Celery Tasks** (automatisch):
- `datev.refresh_all_tokens` - Alle 4 Stunden
- `datev.sync_all_stammdaten` - Taeglich 06:45
- `datev.sync_kontenplan` - Taeglich 06:50
- `datev.push_buchungsstapel` - Alle 2 Stunden
- `datev.upload_pending_belege` - Stuendlich
- `datev.gobd_compliance_check` - Taeglich 05:55
- `datev.auto_festschreibung` - Monatlich am 5.

**Datenmodell** (6 neue Tabellen):
- `datev_connections` - OAuth2-Verbindungen
- `datev_kontenplan` - SKR03/SKR04 Cache
- `datev_buchungen` - GoBD-konforme Buchungssaetze
- `datev_beleglinks` - Belegbild-Verknuepfungen
- `datev_kontierung_patterns` - ML-Lernmuster
- `datev_sync_history` - Sync-Audit-Trail

**SECURITY**: Alle Credentials verschluesselt (AES-256-GCM), GoBD-Hash unveraenderbar.

**Frontend** (`/admin/datev-connect/*`):
- `ConnectionsPage` - Verbindungs-Verwaltung mit OAuth2-Flow
- `SyncStatusPage` - Sync-Dashboard mit manuellen Triggers
- `BuchungenPage` - Buchungen-Liste mit Festschreibung
- `KontierungPage` - ML-Kontierungsvorschlaege
- `KontenplanPage` - Kontenrahmen-Ansicht

**Tests**:
- Unit Tests: `tests/unit/services/datev/test_datev_connect.py`
- Integration Tests: `tests/integration/test_datev_connect_api.py`
