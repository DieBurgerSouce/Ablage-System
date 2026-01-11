# Recent Changes

## 2026-01-11

### Enterprise Document Upload Workflow (NEU)
- **feat**: OCR-Review Upload Flow mit Temp Storage
  - **TempFileStorageService** (`temp_file_storage.py`): Redis-basierte temporäre Datei-Speicherung (1h TTL, max 50MB)
  - **Upload Flow**: 1) OCR/process → temp storage, 2) User review im Modal, 3) upload-complete → MinIO + DB
  - **TTL Extension**: Automatische Verlängerung alle 20min während Review-Modal offen ist
  - **Frontend Hook** (`use-document-upload.ts`): Orchestriert Upload → OCR → Review → Save
  - **DocumentUploadDialog**: Dropzone, OCR-Backend-Auswahl, GPU-Status-Anzeige
  - **OCRReviewModal**: Split-View mit PDF-Preview + Metadaten-Editor, Rename-Vorschlag
  - **Schemas**: `UploadCompleteRequest`, `UploadCompleteResponse` für finales Speichern
  - **API Endpoints**: `/api/v1/ocr/process`, `/api/v1/documents/upload-complete`, `/api/v1/temp-files/{id}/extend-ttl`

### Documentation
- **refactor**: Modularized CLAUDE.md structure
  - Extracted Frontend Patterns to `.claude/Docs/Frontend/Patterns.md` (312 lines)
  - Extracted UI Components to `.claude/Docs/Frontend/Components.md` (96 lines)
  - Reduced CLAUDE.md from 43KB to 11.9KB (363 lines)
  - Reduced RECENT_CHANGES.md to 1.8KB (44 lines)
  - Enhanced memory-updater plugin with routing to Docs/ files

### Frontend
- **refactor**: Ablage API - Centralized HTTP Client Migration
  - Replaced raw `fetch()` calls with `apiClient` from `@/lib/api/client`
  - Migrated endpoints: `fetchEntityName`, `fetchFolderName`, `fetchEntityFolders`, `fetchFolderDocuments`
  - Added pagination support: `fetchCustomersForFrontend`, `fetchSuppliersForFrontend`
  - New types: `PaginatedEntityResponse`, `EntityListFilter`, `SupplierListFilter`
  - Sorting support: `CustomerSortField` (name, customer_number, last_activity)
  - Sorting support: `SupplierSortField` (name, last_activity - NO supplier number)
  - Benefits: Centralized error handling, auth headers, type safety
- **security**: Document Upload Authentication & CSRF Protection (ablage-api.ts)
  - Added `xhr.withCredentials = true` to `uploadDocument()` for session cookies
  - Implemented CSRF token reader (`getCsrfToken()`) for Double-Submit-Cookie pattern
  - Sends `X-CSRF-Token` header with file uploads for CSRF protection
  - Added JWT Bearer token from sessionStorage (`Authorization` header) for XHR uploads
  - Completes authentication fix pattern from commit 25542547

### Infrastructure
- **feat**: Independent Frontend Health Check (nginx.conf)
  - Added dedicated `/health` endpoint for Nginx-native health checks
  - Returns JSON: `{"status":"gesund","service":"frontend","nginx":"running"}`
  - Docker can verify frontend container health independently of backend
  - Keeps existing `/api/health` proxy for deep backend diagnostics

### Backend
- **feat**: GPU Status API Endpoint (`/api/v1/health/gpu`)
  - Returns GPU availability for upload dialog
  - Includes VRAM stats (total, used, free, utilization %)
  - Graceful fallback when CUDA/PyTorch unavailable
- **infra**: Docker GPU Allocation for Backend
  - Backend now gets 1 GPU for health checks
  - Enables `/health/gpu` endpoint to access CUDA stats
  - Worker still primary GPU user for OCR tasks
- **feat**: Expense Reports Soft Delete (Migration 091)
  - Added `deleted_at`, `deleted_by_id` columns to `expense_reports`
  - FK constraint to `users` table with `SET NULL` on delete
  - Partial index for non-deleted records
- **fix**: JSONB query helpers in `ablage_service.py`
  - `jsonb_text()`, `jsonb_numeric()`, `jsonb_exists()` für sichere JSONB-Zugriffe
  - Behebt 500-Fehler auf `/aggregations` Endpoint
- **security**: SQL Injection Prevention für JSONB-Queries (CWE-89)
  - Whitelist für JSONB column/key names (`_ALLOWED_JSONB_COLUMNS`, `_ALLOWED_JSONB_KEYS`)
  - Regex pattern validation (`_SAFE_IDENTIFIER_PATTERN`)
  - Validierung in `jsonb_text()`, `jsonb_numeric()` helpers
- **security**: HTTP Response Splitting Prevention (CWE-113)

### Frontend
- **refactor**: Ablage Types Re-exports
  - Re-export upload types from `./types/ablage-types.ts` in `types.ts`
  - Consolidated import paths for `UploadFile`, `UploadStatus`, `UploadRequest`, `UploadResponse`, `OCRBackend`
  - Utilities: `formatFileSize`, `getStatusColor`, `getStatusLabel`
- **refactor**: CategoryDocumentList UI Responsibilities Cleanup
  - QuickActionsBar: NUR Upload + Export (keine Bulk-Aktionen mehr)
  - BulkActionsToolbar: EINZIGE Quelle für Bulk-Aktionen (Move, Tags, Delete, MarkAsPaid)
  - CategoryTitle: Upload-Button entfernt (jetzt in QuickActionsBar)
  - Conditional Rendering: Aggregations + Filters nur wenn `hasDocuments = true`
  - DocumentsEmptyState: Grosser Upload-CTA wenn keine Dokumente
  - ProactiveInsightsBanner: `onMarkAsPaid` entfernt (in BulkActionsToolbar)
  - DocumentUploadDialog: Modaler Upload statt MoveFolderDialog/TagsEditDialog
- **refactor**: Ablage UI Components Cleanup
  - BulkActionsToolbar: Fixed bottom toolbar mit Bulk-Aktionen
  - QuickActionsBar: Primäre Aktionen (Upload, Export, Mahnung)
  - DocumentUploadDialog: Kategorie-Info, GPU-Status, OCR-Backend
  - Exported alle Smart Features in `index.ts`
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
