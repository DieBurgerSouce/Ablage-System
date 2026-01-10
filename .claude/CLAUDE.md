# Ablage-System: Enterprise Document Processing Platform

<!-- AUTO-MANAGED: project-header -->
**Status**: Production-Ready (E2E Tests 2026-01-10)
**Version**: 1.1
**Philosophy**: Feinpoliert und durchdacht
**Deployment**: On-premises, no cloud dependencies
<!-- /AUTO-MANAGED: project-header -->

> **Schnellreferenz**: Siehe `CLAUDE.md` im Root-Verzeichnis
> **Memory-Dateien**: `.claude/memory/` (automatisch gepflegt)

---

## CRITICAL RULES

<!-- AUTO-MANAGED: critical-rules -->
| # | Rule | Requirement |
|---|------|-------------|
| 1 | **Security** | NEVER log sensitive content, API keys, PII. Secrets only in env vars |
| 2 | **German** | ALL user-facing text MUST be German. UTF-8 for umlauts |
| 3 | **GPU** | Monitor VRAM <85%. Graceful CPU fallback on OOM |
| 4 | **Type Safety** | NEVER use `Any` type. Use mypy strict mode |
| 5 | **Testing** | Tests MUST pass before commit. No exceptions |
| 6 | **On-Premises** | NO cloud services (AWS, GCP, Azure) |
| 7 | **shadcn/ui Select** | NIEMALS `value=""` nutzen (Crashes!) -> `value="auto"` oder `value="all"` |
| 8 | **Lexware PII** | NEVER log customer numbers, IBANs, VAT-IDs from Lexware imports |
<!-- /AUTO-MANAGED: critical-rules -->

---

## Documentation Index

### Memory Files (Auto-Managed)

| File | Content |
|------|---------|
| `.claude/memory/PROJECT_STATUS.md` | Service health, deployments |
| `.claude/memory/KNOWN_ISSUES.md` | Bugs, issues tracking |
| `.claude/memory/RECENT_CHANGES.md` | Changelog |
| `.claude/memory/DEPENDENCIES.md` | Tech stack versions |

### Detailed Documentation

| Category | Path |
|----------|------|
| **Coding Standards** | `.claude/Docs/Guides/Coding-Standards.md` |
| **Testing Requirements** | `.claude/Docs/Testing/Requirements.md` |
| **Lexware Integration** | See "Lexware Integration (NEU: Januar 2026)" section below |
| **API Documentation** | `.claude/Docs/API/` |
| **Architecture** | `.claude/Docs/Architecture/` |
| **Operations/Runbooks** | `.claude/Docs/Operations/` |
| **OCR Backends** | `.claude/Docs/OCR-Backends/` |
| **GPU Management** | `.claude/Docs/Architecture/GPU-Resource-Management.md` |

### Full Documentation Index

| Kategorie | Dokument | Pfad |
|-----------|----------|------|
| Architektur | Celery Task Orchestration | `.claude/Docs/Architecture/Celery-Task-Orchestration.md` |
| | Database Schema ERD | `.claude/Docs/Architecture/Database-Schema-ERD.md` |
| | Event-Driven Architecture | `.claude/Docs/Architecture/Event-Driven-Architecture-Guide.md` |
| | GPU Resource Management | `.claude/Docs/Architecture/GPU-Resource-Management.md` |
| API | API Dokumentation | `.claude/Docs/API/API_Documentation.md` |
| | Admin API Complete | `.claude/Docs/API/Admin-API-Complete.md` |
| | Error Catalog | `.claude/Docs/API/ErrorCatalog.md` |
| Testing | E2E Testing (Playwright) | `.claude/Docs/Testing/E2E-Testing-Playwright.md` |
| | GPU Testing Guide | `.claude/Docs/Testing/GPU-Testing-Guide.md` |
| Operations | Rollback Strategies | `.claude/Docs/Operations/Rollback-Strategies.md` |
| | Runbooks (19 Stueck) | `.claude/Docs/Operations/Runbooks/*.md` |
| Compliance | GDPR Checklist | `.claude/Docs/Compliance/gdpr-checklist.md` |
| Guides | Development Setup | `.claude/Docs/Guides/Development-Setup.md` |
| | Troubleshooting | `.claude/Docs/Guides/Troubleshooting-Guide.md` |
| **Integrations** | **Lexware Integration** | **See dedicated section: "Lexware Integration (NEU: Januar 2026)"** |

---

## Project Overview

Ablage-System is an intelligent document processing platform for German document digitization with multiple OCR backends. Built for enterprise on-premises deployment with GPU acceleration (RTX 4080).

### Architecture

```
+-------------------------------------------------------------+
|                    Ablage-System OCR                        |
+-------------------------------------------------------------+
|  Frontend (Nginx:80)     |  Grafana (:3002)  |  Prometheus  |
+-------------------------------------------------------------+
|                    FastAPI Backend (:8000)                  |
+-------------------------------------------------------------+
|  Celery Workers  |  Redis (:6380)  |  PostgreSQL (:5433)    |
+-------------------------------------------------------------+
|  OCR: DeepSeek | GOT-OCR | Surya | Surya-GPU               |
+-------------------------------------------------------------+
|                 GPU: NVIDIA RTX 4080 (16GB)                 |
+-------------------------------------------------------------+
```

### Core Capabilities

- **Multi-Backend OCR**: DeepSeek-Janus-Pro, GOT-OCR 2.0, Surya+Docling
- **German Optimization**: Fraktur support, 100% umlaut accuracy
- **4 Display Modes**: Dark, Light, Whitescreen, Blackscreen
- **GPU Acceleration**: RTX 4080 with CUDA 12.x
- **Cross-Module Orchestration**: Event-driven coordination
- **Lexware Integration**: Customer/supplier import with auto-linking

---

## Technology Stack

### Backend

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI 0.110+ |
| Python | 3.11+ |
| Database | PostgreSQL 16 + pgvector |
| Cache/Queue | Redis 7.x |
| Storage | MinIO (S3-compatible) |
| Task Queue | Celery 5.3+ |
| ORM | SQLAlchemy 2.0+ (async) |
| Validation | Pydantic v2 |

### OCR Backends

| Backend | VRAM | Strengths |
|---------|------|-----------|
| DeepSeek-Janus-Pro | 12GB | Best umlaut accuracy, Fraktur |
| GOT-OCR 2.0 | 10GB | Tables, formulas, fast |
| Surya + Docling | CPU | Layout analysis, fallback |
| Surya GPU | 4GB | Fast GPU variant |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | React 18 + TypeScript 5.x |
| Router | TanStack Router |
| State | TanStack Query |
| UI | shadcn/ui + Tailwind CSS |

<!-- AUTO-MANAGED: frontend-patterns -->
#### Frontend Patterns (API Integration)

**Standard Pattern**: Feature modules use dedicated API files + TanStack Query hooks

**Example**: Ablage Module (`frontend/src/features/ablage/`)
```typescript
// API Layer (ablage-api.ts)
export async function fetchEntityFolders(entityId: string): Promise<EntityFolder[]>
export async function fetchEntityName(entityId: string): Promise<EntityInfo>

// Component Layer (FolderCategoriesView.tsx)
const { data: folders, isLoading, error } = useQuery({
  queryKey: ['entityFolders', entityId],
  queryFn: () => fetchEntityFolders(entityId!),
  enabled: !!entityId,
})
```

**Key Components**:
- `api/ablage-api.ts` - API functions with typed responses
- `components/*View.tsx` - View components using `useQuery` for data fetching
- `hooks/use-ablage-queries.ts` - Reusable query hooks

**Loading/Error States**: All components implement German loading/error messages
```typescript
// Loading State
<Loader2 className="w-8 h-8 animate-spin text-blue-500" />
<p className="text-muted-foreground">Lade Ordner...</p>

// Error State
<AlertCircle className="w-8 h-8 text-destructive" />
<p className="text-sm text-muted-foreground">
  {error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten'}
</p>
```

**Migration Pattern**: Mock data → Real API
- Remove mock functions (e.g., `getCustomerById`, `getCustomerFolder`)
- Replace with API functions (e.g., `fetchEntityFolders`, `fetchEntityName`)
- Add `useQuery` hooks for data fetching
- Implement loading/error states

**Auto-Navigation Pattern**: Single-Folder Skip (commit 1c1c4b7f)
```typescript
// SupplierFoldersView.tsx / CustomerFoldersView.tsx - Auto-navigate when only one folder exists
useEffect(() => {
  if (!isLoading && !error && folders.length === 1) {
    navigate({
      to: '/lieferanten/$supplierId/$folderId',
      params: { supplierId: supplierId!, folderId: folders[0].id },
      replace: true, // Preserve back button behavior (back → entity list)
    })
  }
}, [isLoading, error, folders, supplierId, navigate])

// FolderCategoriesView.tsx - Dynamic parent path based on folder count
const hasOnlyOneFolder = folders.length === 1
const parentPath = hasOnlyOneFolder
  ? basePath  // Skip folder selection, go directly to entity list
  : isCustomer
    ? `/kunden/$customerId`  // Multiple folders, show folder selection
    : `/lieferanten/$supplierId`
```

**Key Benefits**:
- **UX**: Eliminates unnecessary click when only one folder exists (1-click navigation)
- **Navigation**: Back button always works correctly (auto-skip → list, manual → folder selection)
- **Consistency**: Same pattern applied to both customer and supplier flows
- **Performance**: Reduces navigation depth without sacrificing user control

**Performance Pattern**: Infinite Scroll with TanStack Query (commit 1c1c4b7f)
```typescript
// Example: KundenPage.tsx / LieferantenPage.tsx - Entity list with pagination
const PAGE_SIZE = 100  // Optimized: 100 items per page (reduced API calls, up from 50)

// Separate memoized component prevents focus loss during re-renders
const SearchInput = memo(function SearchInput({ value, onChange }) {
  return (
    <div className="relative max-w-md">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <Input placeholder="Suche..." value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
})

export function KundenPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState<CustomerSortField>('name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')

  // Stable callback for search input
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value)
  }, [])

  // Debounce search (300ms)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Infinite query with pagination
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['customers', debouncedSearch, sortBy, sortOrder],
    queryFn: ({ pageParam = 1 }) => fetchCustomersForFrontend({
      page: pageParam,
      pageSize: PAGE_SIZE,
      search: debouncedSearch || undefined,
      sortBy,
      sortOrder,
    }),
    getNextPageParam: (lastPage) =>
      lastPage.page < lastPage.total_pages ? lastPage.page + 1 : undefined,
    initialPageParam: 1,
    placeholderData: (previousData) => previousData, // Prevent flash
  })

  // Flatten pages with useMemo
  const customers = useMemo(() => data?.pages.flatMap(p => p.items) ?? [], [data])

  return (
    <>
      <SearchInput value={searchQuery} onChange={handleSearchChange} />

      {/* Sorting Controls */}
      <Select value={sortBy} onValueChange={(value) => setSortBy(value as CustomerSortField)}>
        <SelectItem value="name">Name</SelectItem>
        <SelectItem value="customer_number">Kundennummer</SelectItem>
        <SelectItem value="last_activity">Letzte Aktivität</SelectItem>
      </Select>
      <Button onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}>
        {sortOrder === 'asc' ? <ArrowUpNarrowWide /> : <ArrowDownWideNarrow />}
      </Button>

      {/* Render customers... */}
      {hasNextPage && (
        <Button onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? 'Lade...' : `Mehr laden (${totalCount - customers.length} weitere)`}
        </Button>
      )}
    </>
  )
}
```

**Key Optimizations**:
- **Page size: 100 items** (reduced API calls vs 50 items)
- **Debounced search** (300ms) to reduce API calls during typing
- **Memoized SearchInput** prevents re-render focus loss
- **Stable callbacks** with `useCallback` for event handlers
- **placeholderData** prevents flash during search refetch
- **useMemo** for flattening pages array (performance)
- **Loading states**: Initial load vs pagination vs search
- **Sorting support**:
  - KundenPage: name, customer_number, last_activity (asc/desc)
  - LieferantenPage: name, last_activity (asc/desc)
- **Visual sort indicators**: Arrow icons show current sort direction

**Applied to**: `KundenPage.tsx`, `LieferantenPage.tsx` (both use identical pattern)
<!-- /AUTO-MANAGED: frontend-patterns -->

<!-- AUTO-MANAGED: ui-components -->
#### Reusable UI Components

**EditableField Component** (`components/ui/editable-field.tsx`)
- **Purpose**: Click-to-edit pattern for inline metadata editing
- **Features**: Auto-save with debounce, keyboard navigation, Zod validation, visual save indicators
- **Types**: text, number, date, currency, email
- **Usage**: Document metadata editing, invoice fields, entity properties
- **Key Props**: `value`, `onSave`, `type`, `schema`, `autoSaveDelay`

**EnterpriseDataTable Component** (`components/ui/data-table/EnterpriseDataTable.tsx`)
- **Purpose**: Advanced data table with enterprise features
- **Features**: Sorting, filtering, pagination, grouping, column visibility, export (CSV/Excel), row selection
- **Built on**: TanStack Table v8 with full type safety
- **Usage**: All data-heavy dashboards (AI decisions, reports, validation queues)
- **Key Props**: `columns`, `data`, `enableGrouping`, `enableExport`, `onRowClick`

**MultiStepForm Component** (`components/forms/MultiStepForm.tsx`)
- **Purpose**: Generic multi-step wizard with validation, persistence, and animations
- **Features**: Step-by-step navigation, Zod validation per step, SessionStorage persistence (with 500KB limit + auto-cleanup), dirty state warnings, keyboard navigation
- **Enterprise Fix**: QuotaExceededError prevention with size checks and old-wizard cleanup
- **Usage**: Employee onboarding, workflow creation, multi-page forms
- **Key Props**: `steps`, `onComplete`, `persistKey`, `schema`, `initialData`

**Key Components by Feature**:

| Feature | Component | Path | Purpose |
|---------|-----------|------|---------|
| **Ablage** | MoveFolderDialog | `ablage/components/MoveFolderDialog.tsx` | Bulk move documents to different categories (WCAG 2.1 AA) |
| **Banking** | AgingReportTable | `banking/components/AgingReportTable.tsx` | Receivables/payables aging report with filtering |
| **Banking** | MatchSuggestionCard | `banking/components/reconciliation/MatchSuggestionCard.tsx` | Transaction-invoice match suggestions with confidence scoring |
| **ERP** | SyncDashboard | `erp/components/SyncDashboard.tsx` | ERP sync status, history, manual sync triggers |
| **Forms** | MultiStepForm | `components/forms/MultiStepForm.tsx` | Generic wizard with validation, persistence, animations |
| **GoBD** | ArchiveManagement | `gobd/components/ArchiveManagement.tsx` | Archive management with integrity verification |
| **Reports** | ReportBuilder | `reports/components/ReportBuilder.tsx` | Visual report builder (data source, columns, filters, charts) |
| **Search** | SearchPanel | `search/components/SearchPanel.tsx` | Controlled search with URL sync, saved searches |
| **Search** | SearchAutocomplete | `search/components/SearchAutocomplete.tsx` | Query suggestions and recent searches |
| **Viewer** | InlineMetadataEditor | `viewer/components/InlineMetadataEditor.tsx` | Document metadata editing panel with EditableField |
| **Workflows** | DelayNode | `workflows/components/nodes/DelayNode.tsx` | ReactFlow node for time delays |

**Pattern: Controlled Components**
```typescript
// SearchPanel uses controlled props (value/onChange)
<SearchPanel
  value={{ query, mode, filters }}
  onChange={(updates) => updateURL(updates)}
  onReset={() => clearURL()}
/>

// EditableField provides async save with error handling
<EditableField
  value={document.invoiceNumber}
  onSave={async (value) => await updateDocument({ invoiceNumber: value })}
  label="Rechnungsnummer"
  type="text"
/>
```

**Accessibility Standards**:
- All tables use semantic `<table>`, `<thead>`, `<tbody>` with `scope` attributes
- ARIA labels for screen readers (e.g., `aria-label="Dokumentensuche"`)
- Keyboard navigation support (Enter=Save, Escape=Cancel)
- High contrast support across all 4 display modes
- German loading states: `<Loader2 /> "Lade Daten..."`
- German error states: `<AlertCircle /> "Ein Fehler ist aufgetreten"`
<!-- /AUTO-MANAGED: ui-components -->

---

## Development Commands

```bash
# Docker Development (REQUIRED)
docker-compose up -d
docker-compose build frontend && docker-compose up -d frontend
docker-compose build backend && docker-compose up -d backend

# Tests
docker-compose exec backend pytest tests/unit/ -v
pytest --cov=app --cov-report=html

# Code Quality
ruff check . && mypy app/

# Database
alembic upgrade head
alembic revision --autogenerate -m "description"

# GPU
nvidia-smi
```

---

## Project Structure

```
Ablage_System/
+-- CLAUDE.md                 # Quick Reference
+-- .claude/
|   +-- CLAUDE.md             # This file (Core Reference)
|   +-- memory/               # AUTO-MANAGED files
|   +-- commands/             # Slash Commands
|   +-- hooks/                # Pre/Post Hooks
|   +-- agents/               # Subagents
|   +-- Docs/                 # Detailed Documentation
+-- app/
|   +-- main.py               # FastAPI Entry
|   +-- api/v1/               # API Endpoints
|   +-- core/                 # Config, Security
|   +-- db/                   # SQLAlchemy Models
|   +-- services/             # Business Logic
|   +-- workers/              # Celery Tasks
+-- frontend/                 # React + TypeScript
+-- infrastructure/           # Terraform, Ansible
+-- tests/                    # Unit + Integration
+-- docker-compose.yml
```

---

## Key Services

### Document Services (Canonical)

| Service | Path |
|---------|------|
| GDPR | `document_services/gdpr_service.py` |
| Export | `document_services/export_service.py` |
| Batch | `document_services/batch_service.py` |
| CRUD | `document_services/crud_service.py` |

### Enterprise Features

| Feature | Service |
|---------|---------|
| Cross-Module Orchestration | `orchestration/cross_module_orchestrator.py` |
| Financial Health | `privat/financial_health_service.py` |
| Portfolio Management | `privat/portfolio_service.py` |
| Lexware Import | `lexware_import_service.py` |
| Entity Linking | `document_entity_linker_service.py` |
| Entity Search | `entity_search_service.py` |

---

## Lexware Integration (NEU: Januar 2026)

<!-- AUTO-MANAGED: lexware-integration -->
### Overview

Lexware Integration ermöglicht automatischen Import und Verknüpfung von Kunden-/Lieferantendaten aus Lexware-Buchhaltungssoftware-Exporten.

**Status**: ✅ Production-Ready (commit 5f9b5e55)
**Migration**: 089_add_lexware_fields, 090_merge_lexware_streckengeschaeft

### Core Services

| Service | File | Purpose |
|---------|------|---------|
| **LexwareImportService** | `lexware_import_service.py` | Excel-Import, Konflikt-Erkennung |
| **EntitySearchService** | `entity_search_service.py` | Multi-Strategie-Suche (Kundennr, IBAN, VAT-ID) |
| **DocumentEntityLinkerService** | `document_entity_linker_service.py` | Auto-Linking nach OCR |

### Database Schema Changes

**BusinessEntity Model** (Migration 089):
```python
lexware_ids: JSONB  # {"folie": {"kd_nr": "12345", "matchcode": "MUELLER"}, ...}
company_presence: JSONB  # ["folie", "messer"]
primary_customer_number: String(50)  # Display number
primary_supplier_number: String(50)  # Display number
```

**Indexes**:
- `ix_business_entities_primary_customer_number` (B-tree)
- `ix_business_entities_primary_supplier_number` (B-tree)
- `ix_business_entities_lexware_ids_gin` (GIN for JSONB)
- `ix_business_entities_company_presence_gin` (GIN for array)

### Import Workflow

```
1. User uploads Lexware Excel (150 customers)
   ↓
2. LexwareImportService processes file
   ↓
3. Conflict detection:
   - Critical: Different addresses/phone → Skip (default)
   - Harmless: Name variants (GmbH vs GmbH & Co) → Auto-merge
   - Duplicates: Same entity in both lists → Merge with company_presence
   ↓
4. Import: 145 customers (5 skipped due to conflicts)
   ↓
5. Auto-trigger: link_all_documents_task (Celery)
   ↓
6. DocumentEntityLinkerService processes all documents
   ↓
7. Extract patterns: Customer numbers, IBANs, VAT-IDs, company names
   ↓
8. Match with confidence: 78 linked (>75%), 12 flagged for review
```

### API Endpoints

**Lexware Import** (`/api/v1/lexware`):
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/lexware/import/customers` | POST | Import customers from Excel |
| `/api/v1/lexware/import/suppliers` | POST | Import suppliers from Excel |
| `/api/v1/lexware/link-documents` | POST | Trigger entity linking |
| `/api/v1/lexware/statistics` | GET | Import/linking stats |
| `/api/v1/lexware/search` | POST | Smart entity search |

**Entity Management** (`/api/v1/entities`):
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/entities` | GET | List all entities with filters |
| `/api/v1/entities/{id}` | GET | Get entity details |
| `/api/v1/entities/customers` | GET | List customers (frontend format, paginated) |
| `/api/v1/entities/suppliers` | GET | List suppliers (frontend format, paginated, sortable) |
| `/api/v1/entities/{id}/folders` | GET | Get entity folders (folie/messer) |

**Pagination Parameters** (customers/suppliers endpoints):
- `page` (int, default: 1) - Seitennummer
- `page_size` (int, default: 50, max: 200) - Einträge pro Seite
- `search` (str, optional) - Suche in Name/Matchcode/Kundennummer
- `sort_by` (str, default: "name") - Sortierfeld (name, created_at, document_count)
- `sort_order` (str, default: "asc") - Sortierrichtung (asc, desc)
- `is_active` (bool, optional) - Nach Aktivstatus filtern

### Celery Tasks

| Task | Trigger | Purpose |
|------|---------|---------|
| `entity_linking.link_all_documents` | After Lexware import | Batch-link all unlinked docs |
| `entity_linking.link_single_document` | After OCR completion | Link single document |
| `entity_linking.post_lexware_import` | After import success | Orchestrate linking + stats |

### Document Entity Linking

**Matching Strategies** (Priority Order):

| Strategy | Confidence | Pattern Example |
|----------|------------|-----------------|
| Exact customer number | 99% | `Kd-Nr: 12345` |
| Exact matchcode | 95% | `MUELLER` in header |
| IBAN match | 90% | `DE89370400440532013000` |
| VAT-ID match | 90% | `DE123456789` |
| Fuzzy company name | 80% | `Mueller GmbH` vs `Müller GmbH` (>85% similarity) |
| Address match | 75% | PLZ + street name |

**Pattern Extraction** (from OCR text):
```python
# Customer number patterns
r"(?:Kd\.?-?Nr\.?|Kundennummer)[\s:]*(\d{3,8})"

# IBAN pattern
r"\b([A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){3,7}\d{1,4})\b"

# German VAT-ID pattern
r"\b(DE(?:\s*\d){9})\b"
```

### Conflict Resolution

**Similarity Thresholds**:
- `CRITICAL_SIMILARITY_THRESHOLD = 0.5` → Below = critical conflict (skip)
- `HARMLESS_SIMILARITY_THRESHOLD = 0.7` → Above = harmless variant (auto-merge)

**Conflict Types**:
1. **Critical**: Different addresses, phone, email → Skip by default
2. **Harmless**: Name variants (GmbH vs GmbH & Co) → Auto-merge
3. **Duplicates**: Same entity in both lists → Merge with company_presence tracking

### Search Capabilities

**EntitySearchService Methods**:
- `find_by_customer_number(kd_nr, company)` → Exact match
- `find_by_supplier_number(lief_nr, company)` → Exact match
- `find_by_matchcode(matchcode, fuzzy)` → Fuzzy matching
- `find_by_iban(iban)` → Normalized IBAN search
- `find_by_vat_id(vat_id)` → VAT-ID search
- `smart_search(query)` → Multi-strategy search

### Security & PII Protection

| Rule | Implementation |
|------|----------------|
| **No PII in logs** | NEVER log customer numbers, IBANs, VAT-IDs |
| **Excel validation** | Strict structure validation before import |
| **Rate limiting** | Max 10 imports/hour per user |
| **Admin only** | Import operations require admin role |
| **Conflict review** | Critical conflicts require manual approval |

### Testing

**Unit Test Coverage**:
- `tests/unit/services/test_lexware_import_service.py` (50+ tests)
- `tests/unit/services/test_entity_search_service.py` (40+ tests)
- `tests/unit/services/test_document_entity_linker_service.py` (35+ tests)

**Test Categories**:
- Helper functions (normalize_text, calculate_similarity, is_placeholder)
- Conflict detection and resolution
- Pattern extraction from German business documents
- Fuzzy matching with German umlauts (ä, ö, ü, ß)
- IBAN/VAT-ID validation and extraction
- Multi-company data handling

### Frontend Integration

**API Endpoints** (`app/api/v1/entities.py`):
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/entities/customers` | GET | List customers for frontend (displayName format) |
| `/api/v1/entities/suppliers` | GET | List suppliers for frontend (name only) |
| `/api/v1/entities/{id}/folders` | GET | Get company folders (folie/messer) per entity |

**Frontend Components** (`frontend/src/features/ablage/`):
- `KundenPage.tsx` - Customer list with infinite scroll (100 items/page)
- `LieferantenPage.tsx` - Supplier list with infinite scroll (100 items/page)
- `CustomerFoldersView.tsx` - Company folder selection (Spargelmesser/Folie) for customers
- `SupplierFoldersView.tsx` - Company folder selection (Spargelmesser/Folie) for suppliers
- `FolderCategoriesView.tsx` - Document categories per folder
- `api/ablage-api.ts` - Typed API client functions with pagination

**Display Format**:
- **Customers**: `"12345_Mueller"` (Kundennummer_Matchcode)
  - Backend ALWAYS constructs displayName from primary_customer_number + matchcode (never trusts entity.display_name field)
  - Frontend filters fullName: Only show if real company name (doesn't start with number or contain customer number)
- **Suppliers**: `"Agrimpex"` (name only, no number - supplier numbers are chaotic)

**API Response Types**:
```typescript
interface CustomerForFrontend {
  id: string;
  displayName: string;        // "12345_Mueller" (ALWAYS constructed from customer number + matchcode)
  fullName: string;           // "Müller GmbH & Co. KG" OR "10006_Peter" (may be fake placeholder)
  isActive: boolean;
  companyPresence: string[];  // ["folie", "messer"]
  folderStats: Record<string, FolderStats>;
}

interface EntityFolder {
  id: string;                 // "folie" or "messer"
  name: string;               // "Folie" or "Spargelmesser"
  documentCounts: Record<string, number>;
  openInvoices: number;
  lastActivity: string | null;
}
```

**DisplayName Construction** (Backend - `app/api/v1/entities.py`):
```python
# NEVER trust entity.display_name - ALWAYS construct from customer number + matchcode
display_name = f"{primary_customer_number}_{matchcode}"
# Example: "10006_Peter", "12345_Mueller"
```

**FullName Validation** (Frontend - `KundenPage.tsx`):
```typescript
// Filter out fake fullNames that look like Kundennummer format
function isRealCompanyName(fullName: string): boolean {
  if (!fullName || fullName.trim() === '') return false
  const startsWithNumber = /^\d/.test(fullName)  // "10006_Peter" → true
  const containsCustomerNumber = /^\d{3,8}_/.test(fullName)  // "12345_Mueller" → true
  return !startsWithNumber && !containsCustomerNumber
}

// Only show fullName if it's a real company name
{isRealCompanyName(customer.fullName) && (
  <p className="text-sm text-muted-foreground">{customer.fullName}</p>
)}
```

**Migration Pattern**: Mock Data → Real API
- ✅ Removed: `getCustomerById()`, `getCustomerFolder()` mock functions
- ✅ Added: `fetchEntityFolders()`, `fetchCustomersForFrontend()` API calls
- ✅ Implemented: Loading states ("Lade Kunden..."), Error states with German messages
- ✅ Pattern: All views use `useQuery` hooks for data fetching
- ✅ DisplayName: Backend constructs from customer number + matchcode (not from entity.display_name)
- ✅ FullName Filter: Frontend only shows real company names (no fake placeholders)

**Folder Selection Pattern**: CustomerFoldersView.tsx
```typescript
// Displays entity folders (Folie/Messer) with stats
const { data: folders = [], isLoading, error } = useQuery({
  queryKey: ['entityFolders', customerId],
  queryFn: () => fetchEntityFolders(customerId!),
  enabled: !!customerId,
})

// Navigate to folder categories
const handleFolderClick = (folderId: string) => {
  navigate({ to: '/kunden/$customerId/$folderId', params: { customerId, folderId } })
}

// Calculate total documents across all categories
const getTotalDocs = (folder: EntityFolder) =>
  Object.values(folder.documentCounts || {}).reduce((sum, count) => sum + count, 0)
```

**Key Features**:
- Card-based UI with hover effects (border highlight, scale animation)
- Real-time stats: Total docs, open invoices, last activity per folder
- Breadcrumb navigation with back button to customer list
- Empty state handling ("Keine Ordner gefunden")
- Responsive layout (hides last activity on mobile)

### Integration Points

| Module | Integration |
|--------|-------------|
| Document Service | OCR completion → triggers entity linking |
| Validation Services | Uses EntitySearchService for duplicate checks |
| Event Bus | Emits `entity.linked` events for orchestration |
| Frontend Ablage | Customer/supplier lists, folder navigation, real-time stats |

### Configuration

**Key Settings**:
```python
MIN_LINK_CONFIDENCE = 0.75  # Minimum for automatic linking
BATCH_SIZE = 100  # Documents per linking batch
DEFAULT_SIMILARITY_THRESHOLD = 0.7  # Fuzzy name matching
```

### Known Issues & Limitations

- ❌ Excel must follow Lexware export format (specific column names)
- ❌ Only supports German company formats (GmbH, AG, KG, etc.)
- ⚠️ Fuzzy matching may need manual review for edge cases
- ⚠️ Multi-company entities require careful conflict handling

### Critical Bug Fixes (2026-01-10)

**BUG #1: FastAPI Route Ordering Issue** (`app/api/v1/entities.py`)
- **Problem**: Static routes `/customers` and `/suppliers` were defined AFTER dynamic route `/{entity_id}`
- **Symptom**: 403/422 errors when accessing `/api/v1/entities/customers` or `/api/v1/entities/suppliers`
- **Root Cause**: FastAPI matches routes in definition order. "customers" was incorrectly matched as UUID parameter.
- **Fix**: Moved static routes (`/customers`, `/suppliers`, `/suggestions`) BEFORE `/{entity_id}` route
- **Commit**: 665ca1cc
- **Impact**: Frontend Ablage module now correctly loads customer/supplier lists

**BUG #2: Missing Cookie Credentials in API Calls** (`ablage-api.ts`)
- **Problem**: Entity API fetch calls not sending httpOnly session cookies
- **Symptom**: 401 Unauthorized errors on `/api/v1/entities/*` endpoints after successful login
- **Root Cause**: Fetch API default behavior doesn't include credentials for same-origin requests
- **Fix**: Added `credentials: "include"` option to all fetch calls in ablage-api.ts
- **Commit**: 25542547
- **Impact**: Entity API endpoints now properly authenticated with session cookies

### Future Enhancements

- [ ] Support for Austrian/Swiss company formats
- [ ] ML-based entity matching (beyond fuzzy string matching)
- [ ] Automatic conflict resolution with user preferences
- [ ] Real-time Lexware API integration (instead of Excel)
- [ ] Entity deduplication across companies

<!-- /AUTO-MANAGED: lexware-integration -->

---

## Security Guidelines

| Area | Requirement |
|------|-------------|
| JWT Tokens | httpOnly cookies + CSRF |
| Token Expiration | Access: 15min, Refresh: 7 days |
| Password Hashing | bcrypt, cost factor 12 |
| Rate Limiting | Login: 5/15min, API: 100/min |
| Document Access | Owner check + sharing permissions |
| GDPR | Deletion within 30 days, audit logging |

**Detailed**: See `.claude/Docs/Compliance/` and `.claude/Docs/API/RateLimits.md`

---

## GPU Optimization

| Metric | Target |
|--------|--------|
| VRAM Usage | <85% (13.6GB of 16GB) |
| Batch Size | Dynamic based on available VRAM |
| Fallback | Automatic CPU fallback on OOM |

**Key Patterns**: `gpu_memory_guard()`, `GPUBatchProcessor`, `ModelManager`

**Detailed**: See `.claude/Docs/Architecture/GPU-Resource-Management.md`

---

## German Language Processing

```python
# User-facing messages MUST be German
ERROR_MESSAGES = {
    "document_not_found": "Dokument nicht gefunden",
    "processing_failed": "Verarbeitung fehlgeschlagen",
    "invalid_format": "Ungueltiges Dateiformat"
}
```

---

## Monitoring

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3002 |
| Prometheus | http://localhost:9090 |
| API Docs | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |

---

## Performance Targets

| Metric | Target |
|--------|--------|
| API Health Check | <50ms |
| Document Upload | <500ms |
| OCR (single page) | <2s GPU, <10s CPU |
| Concurrent Users | 100+ |
| Documents/Hour | 500+ GPU |

---

## Checklist for AI Assistant

Before completing any task:

- [ ] All code has type hints
- [ ] Tests written and passing
- [ ] German language for user-facing content
- [ ] GPU resources managed properly
- [ ] Security considerations addressed

---

## CLAUDE.md Maintenance

Claude SOLL diese Dateien automatisch pflegen:

1. **AUTO-MANAGED Sektionen**: Bei relevanten Aenderungen aktualisieren
2. **Memory-Dateien**: `.claude/memory/*.md` fuer dynamische Infos

### Wann aktualisieren:

- Nach Migrationen (alembic)
- Nach neuen Features/Services
- Nach Bug-Fixes
- Nach Konfigurations-Aenderungen

### AUTO-MANAGED Format:

```html
<!-- AUTO-MANAGED: section-name -->
Inhalt...
<!-- /AUTO-MANAGED: section-name -->
```

---

**Version**: 1.1
**Last Updated**: 2026-01-10
