# Frontend Patterns (API Integration)

> Extrahiert aus `.claude/CLAUDE.md` - AUTO-MANAGED Sektion
> Letzte Aktualisierung: 2026-01-11

---

## Standard Pattern

Feature modules use dedicated API files + TanStack Query hooks.

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

---

## Loading/Error States

All components implement German loading/error messages:

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

---

## Migration Pattern: Mock Data → Real API

1. Remove mock functions (e.g., `getCustomerById`, `getCustomerFolder`)
2. Replace with API functions (e.g., `fetchEntityFolders`, `fetchEntityName`)
3. Add `useQuery` hooks for data fetching
4. Implement loading/error states

---

## Auto-Navigation Pattern

Single-Folder Skip (commit 1c1c4b7f):

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

---

## Performance Pattern: Infinite Scroll

TanStack Query Infinite Scroll (commit 1c1c4b7f):

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

**Applied to**: `KundenPage.tsx`, `LieferantenPage.tsx`

---

## Transaction/Vorgänge Pattern

Business Process Timeline (2026-01-11):

```typescript
// types.ts - Business transaction tracking with horizontal timeline
export interface Transaction {
  id: string
  transactionNumber: string  // "VG-2024-001"
  name: string               // "Bestellung Druckplatten"
  status: 'pending' | 'active' | 'completed' | 'cancelled'
  entityId: string
  folderId: string
  steps: TransactionStep[]   // Horizontal timeline: Anfrage → Angebot → Auftrag → Lieferschein → Rechnung → Zahlung
  totalAmount: number
  currency: string
  createdAt: string
  lastActivityAt: string
}

export interface TransactionStep {
  id: string
  type: 'anfrage' | 'angebot' | 'auftrag' | 'lieferschein' | 'rechnung' | 'zahlung'
  status: 'pending' | 'active' | 'completed' | 'skipped'
  documentId: string | null
  documentNumber: string | null
  completedAt: string | null
  amount: number | null
}
```

**Key Components**:
- **TransactionTimeline**: Horizontal timeline with 6 step types (Anfrage → Zahlung)
- **TransactionTimelineCompact**: Condensed view for list items
- **TransactionListItem**: Card with timeline + metadata (amount, dates, status)
- **InvoiceTrackingBanner**: Payment status summary (open/due soon/overdue, Skonto opportunities)
- **ProactiveInsightsBanner**: AI-driven insights (delays, duplicate payments, missing docs)
- **QuickActionsBar**: Context-aware action buttons (new transaction, bulk update, export)

**Smart Features**:
- **Skonto Detection**: Calculates savings from early payment discounts
- **Delay Alerts**: Flags transactions with unusual delays between steps
- **Missing Document Detection**: Identifies skipped steps that should have documents
- **Duplicate Payment Prevention**: Warns about potential duplicate invoices
- **Status Auto-Update**: Steps change from pending → active → completed based on document links

**Routes**:
- `/kunden/$customerId/$folderId/vorgaenge`
- `/lieferanten/$supplierId/$folderId/vorgaenge`

---

## Folder-Specific Categories Pattern

(commit 157a6df5):

```typescript
// types.ts - Categories depend on customer's company folder (messer vs folie)
export type CustomerDocumentCategory =
  | 'anfragen' | 'angebote' | 'auftragsbestätigung' | 'lieferscheine' | 'rechnungen'
  | 'storno' | 'mahnungen' | 'offene_rechnungen' | 'offene_angebote' | 'offene_anfragen'
  | 'reklamation' | 'kommunikation' | 'archiv'
  | 'druckdaten';  // NUR für Spargelmesser-Kunden!

export const CUSTOMER_CATEGORIES_BASE: DocumentCategoryInfo[] = [
  // 13 Standard-Kategorien: Anfragen → Archiv (ohne Druckdaten)
]

export const CUSTOMER_CATEGORIES_MESSER: DocumentCategoryInfo[] = [
  ...CUSTOMER_CATEGORIES_BASE,
  { id: 'druckdaten', label: 'Druckdaten', shortCode: 'DD', icon: 'Printer' },
]

export function getCustomerCategoriesForFolder(folderId: string): DocumentCategoryInfo[] {
  return folderId === 'messer' ? CUSTOMER_CATEGORIES_MESSER : CUSTOMER_CATEGORIES_BASE
}
```

**Key Features**:
- **Messer-specific**: "Druckdaten" category only for Spargelmesser customers (14 total)
- **Folie-standard**: Standard 13 categories (Anfragen → Archiv)
- **Type-safe**: Union type includes "druckdaten" with TSDoc
- **Backend mapping**: `CATEGORY_TO_DOCUMENT_TYPE` maps "druckdaten" → "print_data"
- **Business rule**: Folie customers cannot move docs to Druckdaten

**Applied to**: `types.ts`, `FolderCategoriesView.tsx`, `CategoryDocumentList.tsx`, `MoveFolderDialog.tsx`

---

## Nested Route Pattern

Layout Routes with Outlet:

```typescript
// Layout routes enable nested navigation with child routes
// Pattern: Parent layout route + index route + child routes

// kunden.$customerId.$folderId.tsx - Layout route (passes through to children)
import { createFileRoute, Outlet } from '@tanstack/react-router'

export const Route = createFileRoute('/kunden/$customerId/$folderId')({
  component: () => <Outlet />,  // Renders child routes without extra UI
})

// kunden.$customerId.$folderId.index.tsx - Index route (default child)
export const Route = createFileRoute('/kunden/$customerId/$folderId/')({
  component: () => <FolderCategoriesView entityType="customer" />,
})

// kunden.$customerId.$folderId.vorgaenge.tsx - Named child route
export const Route = createFileRoute('/kunden/$customerId/$folderId/vorgaenge')({
  component: () => <TransactionsView entityType="customer" />,
})
```

**Route Structure Benefits**:
- **Cleaner URLs**: `/kunden/:id/:folder` (index) vs `/kunden/:id/:folder/vorgaenge` (child)
- **Shared Layout**: Layout route can add shared UI (breadcrumbs, header)
- **Nested Navigation**: Child routes inherit params automatically
- **Type Safety**: TanStack Router generates type-safe route params

**Applied to**:
- `kunden.$customerId.$folderId.tsx` + `index.tsx`
- `lieferanten.$supplierId.$folderId.tsx` + `index.tsx`
- Future child routes: `vorgaenge.tsx`, `berichte.tsx`, `einstellungen.tsx`
