# Recent Changes

## 2026-01-11

### Backend
- **fix**: JSONB query helpers in `ablage_service.py`
  - `jsonb_text()`, `jsonb_numeric()`, `jsonb_exists()` für sichere JSONB-Zugriffe
  - Behebt 500-Fehler auf `/aggregations` Endpoint
- **security**: SQL Injection Prevention für JSONB-Queries (CWE-89)
  - Whitelist für JSONB column/key names (`_ALLOWED_JSONB_COLUMNS`, `_ALLOWED_JSONB_KEYS`)
  - Regex pattern validation (`_SAFE_IDENTIFIER_PATTERN`)
  - Validierung in `jsonb_text()`, `jsonb_numeric()` helpers
- **security**: HTTP Response Splitting Prevention (CWE-113)

### Frontend
- **feat**: CategoryDocumentList Komponenten-Architektur
  - ProactiveInsightsBanner (KI-Insights ganz oben)
  - CategoryBreadcrumb (Navigation-Pfad)
  - CategoryTitle (Seitentitel mit Back-Button)
  - QuickActionsBar (Primäre + Kontext-Aktionen)
  - InvoiceTrackingBanner (Zahlungsstatus bei Rechnungen)
  - CategoryAggregations (Summen-Karten)
  - DocumentFilterBar + DocumentsTable
  - BulkActionsToolbar (fixiert unten)
- **feat**: Breadcrumb-Komponenten getrennt
  - `CategoryBreadcrumb` für Navigation-Pfad
  - `CategoryTitle` für Titel + Actions
  - Konsistentes Styling über alle Ablage-Routen
- **feat**: TransactionTimeline (Vorgänge-Ansicht)
- **refactor**: Nested Routes für Vorgänge (`$folderId/vorgaenge`)

## 2026-01-10

### Backend
- **feat**: Druckdaten-Kategorie für Spargelmesser-Kunden
- **fix**: Entity displayName Konstruktion (Kundennr_Matchcode)
- **feat**: Supplier Sorting + Pagination API
- **fix**: FastAPI Route Ordering (static before dynamic)

### Frontend
- **feat**: Ordner-spezifische Kategorien (Messer vs Folie)
- **feat**: Auto-Navigation bei Single-Folder Entities
- **perf**: Infinite Scroll für Kunden/Lieferanten (100 Items/Page)
- **fix**: German Umlauts (139 Dateien korrigiert)
