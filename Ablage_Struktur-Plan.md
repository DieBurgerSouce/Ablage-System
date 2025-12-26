# Task: Kunden & Lieferanten Navigation Tabs mit Hierarchischer Ablage-Struktur

## Übersicht

Implementiere zwei neue Haupt-Navigation-Tabs im Ablage-System:
1. **Kunden** - Dokumentenablage für alle Kunden
2. **Lieferanten** - Dokumentenablage für alle Lieferanten

Jeder Tab zeigt eine hierarchische Ordnerstruktur nach deutschem Geschäftsstandard.

---

## Projektkontext

### Technologie-Stack
- **Frontend**: React 19.2.0, TypeScript, Vite
- **Router**: TanStack Router (File-based Routing)
- **UI**: shadcn/ui, Radix UI, Tailwind CSS
- **Backend**: FastAPI, PostgreSQL, SQLAlchemy
- **Projekt-Root**: `C:\Users\benfi\Ablage_System`

### Relevante Pfade
```
frontend/
├── src/
│   ├── app/routes/           # TanStack Router File-based Routes
│   ├── components/
│   │   ├── layout/
│   │   │   └── Sidebar.tsx   # Navigation Sidebar (HIER TABS HINZUFÜGEN)
│   │   └── ui/               # shadcn/ui Komponenten
│   ├── features/             # Feature-Module (NEUE FEATURES HIER)
│   ├── lib/api/              # API Client & Services
│   └── types/                # TypeScript Types

app/                          # Backend
├── api/v1/
│   ├── entities.py           # Business Entity API (Kunden/Lieferanten)
│   └── documents.py          # Documents API
└── db/
    ├── models.py             # SQLAlchemy Models
    └── schemas.py            # Pydantic Schemas
```

---

## Anforderung: Hierarchische Ablage-Struktur

### Tab 1: Kunden

```
/kunden
├── Spargelmesser/                 # Kunde 1
│   ├── Anfragen/
│   ├── Angebote (AG)/
│   ├── Auftragsbestätigung (AB)/
│   ├── Lieferscheine (LS)/
│   ├── Rechnungen (RG)/
│   ├── Storno (ST)/
│   ├── Mahnungen/
│   ├── Offene Rechnungen/
│   ├── Offene Angebote/
│   ├── Offene Anfragen/
│   ├── Reklamation/
│   ├── Kommunikation/
│   └── Archiv/
├── Folie/                         # Kunde 2
│   └── [Identische Unterordner]
└── [Weitere Kunden...]
```

### Tab 2: Lieferanten

```
/lieferanten
├── Spargelmesser1/                # Lieferant 1
│   ├── Anfragen/
│   ├── Angebote (AG)/
│   ├── Auftragsbestätigung (AB)/
│   ├── Lieferscheine (LS)/
│   ├── Rechnungen (RG)/
│   ├── Bestellungen (B)/          # ⚠️ NUR bei Lieferanten!
│   ├── Storno (ST)/
│   ├── Mahnungen/
│   ├── Offene Rechnungen/
│   ├── Offene Angebote/
│   ├── Offene Anfragen/
│   ├── Reklamation/
│   ├── Kommunikation/
│   └── Archiv/
├── Folie/                         # Lieferant 2
│   └── [Identische Unterordner]
└── [Weitere Lieferanten...]
```

---

## Implementierung

### 1. TypeScript Types erstellen

**Datei: `frontend/src/features/ablage/types.ts`**

```typescript
// Dokumentkategorien für die Ablage-Struktur
export type CustomerDocumentCategory =
  | 'anfragen'
  | 'angebote'
  | 'auftragsbestaetigung'
  | 'lieferscheine'
  | 'rechnungen'
  | 'storno'
  | 'mahnungen'
  | 'offene_rechnungen'
  | 'offene_angebote'
  | 'offene_anfragen'
  | 'reklamation'
  | 'kommunikation'
  | 'archiv';

// Lieferanten haben zusätzlich "Bestellungen"
export type SupplierDocumentCategory =
  | CustomerDocumentCategory
  | 'bestellungen';

// Kategorie-Metadaten
export interface DocumentCategoryInfo {
  id: string;
  label: string;
  shortCode?: string;  // z.B. "AG", "AB", "LS", "RG", "ST", "B"
  icon: string;        // Lucide Icon Name
  color?: string;      // Badge Farbe
  isOpenStatus?: boolean;  // Für "Offene X" Kategorien
}

// Kunden-Kategorien Definition
export const CUSTOMER_CATEGORIES: DocumentCategoryInfo[] = [
  { id: 'anfragen', label: 'Anfragen', icon: 'HelpCircle' },
  { id: 'angebote', label: 'Angebote', shortCode: 'AG', icon: 'FileText' },
  { id: 'auftragsbestaetigung', label: 'Auftragsbestätigung', shortCode: 'AB', icon: 'FileCheck' },
  { id: 'lieferscheine', label: 'Lieferscheine', shortCode: 'LS', icon: 'Truck' },
  { id: 'rechnungen', label: 'Rechnungen', shortCode: 'RG', icon: 'Receipt' },
  { id: 'storno', label: 'Storno', shortCode: 'ST', icon: 'XCircle', color: 'destructive' },
  { id: 'mahnungen', label: 'Mahnungen', icon: 'AlertTriangle', color: 'warning' },
  { id: 'offene_rechnungen', label: 'Offene Rechnungen', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_angebote', label: 'Offene Angebote', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_anfragen', label: 'Offene Anfragen', icon: 'Clock', isOpenStatus: true },
  { id: 'reklamation', label: 'Reklamation', icon: 'MessageSquareWarning', color: 'destructive' },
  { id: 'kommunikation', label: 'Kommunikation', icon: 'Mail' },
  { id: 'archiv', label: 'Archiv', icon: 'Archive' },
];

// Lieferanten-Kategorien (mit Bestellungen)
export const SUPPLIER_CATEGORIES: DocumentCategoryInfo[] = [
  { id: 'anfragen', label: 'Anfragen', icon: 'HelpCircle' },
  { id: 'angebote', label: 'Angebote', shortCode: 'AG', icon: 'FileText' },
  { id: 'auftragsbestaetigung', label: 'Auftragsbestätigung', shortCode: 'AB', icon: 'FileCheck' },
  { id: 'lieferscheine', label: 'Lieferscheine', shortCode: 'LS', icon: 'Truck' },
  { id: 'rechnungen', label: 'Rechnungen', shortCode: 'RG', icon: 'Receipt' },
  { id: 'bestellungen', label: 'Bestellungen', shortCode: 'B', icon: 'ShoppingCart' },  // NUR Lieferanten!
  { id: 'storno', label: 'Storno', shortCode: 'ST', icon: 'XCircle', color: 'destructive' },
  { id: 'mahnungen', label: 'Mahnungen', icon: 'AlertTriangle', color: 'warning' },
  { id: 'offene_rechnungen', label: 'Offene Rechnungen', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_angebote', label: 'Offene Angebote', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_anfragen', label: 'Offene Anfragen', icon: 'Clock', isOpenStatus: true },
  { id: 'reklamation', label: 'Reklamation', icon: 'MessageSquareWarning', color: 'destructive' },
  { id: 'kommunikation', label: 'Kommunikation', icon: 'Mail' },
  { id: 'archiv', label: 'Archiv', icon: 'Archive' },
];

// Entity mit Dokumentenzählung pro Kategorie
export interface EntityWithDocumentCounts {
  id: string;
  name: string;
  displayName?: string;
  entityType: 'customer' | 'supplier';
  documentCounts: Record<string, number>;
  totalDocuments: number;
  lastDocumentDate?: string;
  isActive: boolean;
}
```

---

### 2. Route-Dateien erstellen

**Datei: `frontend/src/app/routes/kunden.tsx`**

```tsx
import { createFileRoute } from '@tanstack/react-router'
import { KundenPage } from '@/features/ablage/components/KundenPage'

export const Route = createFileRoute('/kunden')({
  component: KundenPage,
})
```

**Datei: `frontend/src/app/routes/kunden.$entityId.tsx`**

```tsx
import { createFileRoute } from '@tanstack/react-router'
import { EntityAblageView } from '@/features/ablage/components/EntityAblageView'

export const Route = createFileRoute('/kunden/$entityId')({
  component: () => <EntityAblageView entityType="customer" />,
})
```

**Datei: `frontend/src/app/routes/kunden.$entityId.$category.tsx`**

```tsx
import { createFileRoute } from '@tanstack/react-router'
import { CategoryDocumentList } from '@/features/ablage/components/CategoryDocumentList'

export const Route = createFileRoute('/kunden/$entityId/$category')({
  component: () => <CategoryDocumentList entityType="customer" />,
})
```

**Datei: `frontend/src/app/routes/lieferanten.tsx`**

```tsx
import { createFileRoute } from '@tanstack/react-router'
import { LieferantenPage } from '@/features/ablage/components/LieferantenPage'

export const Route = createFileRoute('/lieferanten')({
  component: LieferantenPage,
})
```

**Datei: `frontend/src/app/routes/lieferanten.$entityId.tsx`**

```tsx
import { createFileRoute } from '@tanstack/react-router'
import { EntityAblageView } from '@/features/ablage/components/EntityAblageView'

export const Route = createFileRoute('/lieferanten/$entityId')({
  component: () => <EntityAblageView entityType="supplier" />,
})
```

**Datei: `frontend/src/app/routes/lieferanten.$entityId.$category.tsx`**

```tsx
import { createFileRoute } from '@tanstack/react-router'
import { CategoryDocumentList } from '@/features/ablage/components/CategoryDocumentList'

export const Route = createFileRoute('/lieferanten/$entityId/$category')({
  component: () => <CategoryDocumentList entityType="supplier" />,
})
```

---

### 3. Sidebar Navigation erweitern

**Datei: `frontend/src/components/layout/Sidebar.tsx`**

Füge diese neuen Links zur Navigation hinzu (nach "Geschäftspartner"):

```tsx
// Neue Imports
import { Users, Package } from 'lucide-react'

// Im Navigation-Bereich hinzufügen:
<SidebarLink to="/kunden" icon={Users} label="Kunden" />
<SidebarLink to="/lieferanten" icon={Package} label="Lieferanten" />
```

**Vollständige Sidebar.tsx Änderung:**

```tsx
import { Link } from '@tanstack/react-router'
import {
  LayoutDashboard,
  Upload,
  ListTodo,
  FileText,
  CheckCircle,
  Layers,
  Building2,
  GraduationCap,
  Cpu,
  ChevronDown,
  MessageSquare,
  ClipboardCheck,
  FileSpreadsheet,
  Users,      // NEU
  Package     // NEU
} from 'lucide-react'
// ... rest bleibt gleich

// Im nav-Bereich nach <SidebarLink to="/business-entities" ...> einfügen:

{/* Ablage-Struktur Section */}
<div className="pt-4">
  <div className="px-3 mb-2">
    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
      Ablage
    </span>
  </div>
  <SidebarLink to="/kunden" icon={Users} label="Kunden" />
  <SidebarLink to="/lieferanten" icon={Package} label="Lieferanten" />
</div>
```

---

### 4. Feature-Komponenten erstellen

**Ordnerstruktur:**
```
frontend/src/features/ablage/
├── components/
│   ├── KundenPage.tsx
│   ├── LieferantenPage.tsx
│   ├── EntityAblageView.tsx
│   ├── CategoryDocumentList.tsx
│   ├── EntityFolderTree.tsx
│   ├── CategoryFolderItem.tsx
│   └── DocumentCategoryBadge.tsx
├── hooks/
│   ├── useEntityDocuments.ts
│   └── useDocumentCategories.ts
├── api/
│   └── ablage-api.ts
├── types.ts
└── index.ts
```

---

#### 4.1 KundenPage.tsx

```tsx
import { useState, useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import { Users, Search, Plus, FolderOpen, ChevronRight } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { CUSTOMER_CATEGORIES, type EntityWithDocumentCounts } from '../types'

// TODO: Replace with actual API hook
const MOCK_CUSTOMERS: EntityWithDocumentCounts[] = [
  {
    id: '1',
    name: 'Spargelmesser GmbH',
    displayName: 'Spargelmesser',
    entityType: 'customer',
    documentCounts: {
      anfragen: 5,
      angebote: 12,
      auftragsbestaetigung: 8,
      rechnungen: 24,
      offene_rechnungen: 3,
    },
    totalDocuments: 67,
    lastDocumentDate: '2024-12-20',
    isActive: true,
  },
  {
    id: '2',
    name: 'Folie & Verpackung KG',
    displayName: 'Folie',
    entityType: 'customer',
    documentCounts: {
      anfragen: 2,
      angebote: 6,
      rechnungen: 15,
      offene_rechnungen: 1,
    },
    totalDocuments: 34,
    lastDocumentDate: '2024-12-18',
    isActive: true,
  },
]

export function KundenPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedEntities, setExpandedEntities] = useState<Set<string>>(new Set())

  const filteredCustomers = useMemo(() => {
    if (!searchQuery) return MOCK_CUSTOMERS
    const query = searchQuery.toLowerCase()
    return MOCK_CUSTOMERS.filter(
      (c) => c.name.toLowerCase().includes(query) || c.displayName?.toLowerCase().includes(query)
    )
  }, [searchQuery])

  const toggleExpand = (entityId: string) => {
    setExpandedEntities((prev) => {
      const next = new Set(prev)
      if (next.has(entityId)) {
        next.delete(entityId)
      } else {
        next.add(entityId)
      }
      return next
    })
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Users className="w-8 h-8 text-primary" />
            Kunden-Ablage
          </h1>
          <p className="text-muted-foreground mt-2">
            Dokumentenablage nach Kunden strukturiert
          </p>
        </div>
        <Button className="gap-2">
          <Plus className="w-4 h-4" />
          Neuer Kunde
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          placeholder="Kunde suchen..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Entity List with Folder Structure */}
      <ScrollArea className="h-[calc(100vh-280px)]">
        <div className="space-y-3">
          {filteredCustomers.map((customer) => (
            <Card key={customer.id} className="overflow-hidden">
              <Collapsible
                open={expandedEntities.has(customer.id)}
                onOpenChange={() => toggleExpand(customer.id)}
              >
                <CollapsibleTrigger className="w-full">
                  <CardHeader className="py-4 hover:bg-muted/50 transition-colors cursor-pointer">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <ChevronRight
                          className={`w-5 h-5 transition-transform ${
                            expandedEntities.has(customer.id) ? 'rotate-90' : ''
                          }`}
                        />
                        <FolderOpen className="w-5 h-5 text-amber-500" />
                        <div className="text-left">
                          <CardTitle className="text-lg">
                            {customer.displayName || customer.name}
                          </CardTitle>
                          <CardDescription>{customer.name}</CardDescription>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <Badge variant="secondary">{customer.totalDocuments} Dokumente</Badge>
                        {customer.documentCounts.offene_rechnungen > 0 && (
                          <Badge variant="destructive">
                            {customer.documentCounts.offene_rechnungen} offen
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>

                <CollapsibleContent>
                  <CardContent className="pt-0 pb-4">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 pl-8">
                      {CUSTOMER_CATEGORIES.map((category) => {
                        const count = customer.documentCounts[category.id] || 0
                        return (
                          <Link
                            key={category.id}
                            to="/kunden/$entityId/$category"
                            params={{ entityId: customer.id, category: category.id }}
                            className="flex items-center gap-2 p-2 rounded-md hover:bg-muted transition-colors group"
                          >
                            <FolderOpen className="w-4 h-4 text-amber-500 group-hover:text-amber-600" />
                            <span className="text-sm flex-1 truncate">
                              {category.label}
                              {category.shortCode && (
                                <span className="text-muted-foreground ml-1">
                                  ({category.shortCode})
                                </span>
                              )}
                            </span>
                            {count > 0 && (
                              <Badge
                                variant={category.isOpenStatus ? 'destructive' : 'secondary'}
                                className="text-xs"
                              >
                                {count}
                              </Badge>
                            )}
                          </Link>
                        )
                      })}
                    </div>
                  </CardContent>
                </CollapsibleContent>
              </Collapsible>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
```

---

#### 4.2 LieferantenPage.tsx

```tsx
import { useState, useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import { Package, Search, Plus, FolderOpen, ChevronRight } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { SUPPLIER_CATEGORIES, type EntityWithDocumentCounts } from '../types'

// TODO: Replace with actual API hook
const MOCK_SUPPLIERS: EntityWithDocumentCounts[] = [
  {
    id: '3',
    name: 'Spargelmesser Zulieferer GmbH',
    displayName: 'Spargelmesser1',
    entityType: 'supplier',
    documentCounts: {
      anfragen: 3,
      angebote: 8,
      bestellungen: 15,
      rechnungen: 42,
      offene_rechnungen: 2,
    },
    totalDocuments: 89,
    lastDocumentDate: '2024-12-21',
    isActive: true,
  },
  {
    id: '4',
    name: 'Folie Lieferant AG',
    displayName: 'Folie',
    entityType: 'supplier',
    documentCounts: {
      anfragen: 1,
      bestellungen: 7,
      rechnungen: 18,
    },
    totalDocuments: 41,
    lastDocumentDate: '2024-12-19',
    isActive: true,
  },
]

export function LieferantenPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedEntities, setExpandedEntities] = useState<Set<string>>(new Set())

  const filteredSuppliers = useMemo(() => {
    if (!searchQuery) return MOCK_SUPPLIERS
    const query = searchQuery.toLowerCase()
    return MOCK_SUPPLIERS.filter(
      (s) => s.name.toLowerCase().includes(query) || s.displayName?.toLowerCase().includes(query)
    )
  }, [searchQuery])

  const toggleExpand = (entityId: string) => {
    setExpandedEntities((prev) => {
      const next = new Set(prev)
      if (next.has(entityId)) {
        next.delete(entityId)
      } else {
        next.add(entityId)
      }
      return next
    })
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Package className="w-8 h-8 text-primary" />
            Lieferanten-Ablage
          </h1>
          <p className="text-muted-foreground mt-2">
            Dokumentenablage nach Lieferanten strukturiert
          </p>
        </div>
        <Button className="gap-2">
          <Plus className="w-4 h-4" />
          Neuer Lieferant
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          placeholder="Lieferant suchen..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Entity List with Folder Structure */}
      <ScrollArea className="h-[calc(100vh-280px)]">
        <div className="space-y-3">
          {filteredSuppliers.map((supplier) => (
            <Card key={supplier.id} className="overflow-hidden">
              <Collapsible
                open={expandedEntities.has(supplier.id)}
                onOpenChange={() => toggleExpand(supplier.id)}
              >
                <CollapsibleTrigger className="w-full">
                  <CardHeader className="py-4 hover:bg-muted/50 transition-colors cursor-pointer">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <ChevronRight
                          className={`w-5 h-5 transition-transform ${
                            expandedEntities.has(supplier.id) ? 'rotate-90' : ''
                          }`}
                        />
                        <FolderOpen className="w-5 h-5 text-blue-500" />
                        <div className="text-left">
                          <CardTitle className="text-lg">
                            {supplier.displayName || supplier.name}
                          </CardTitle>
                          <CardDescription>{supplier.name}</CardDescription>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <Badge variant="secondary">{supplier.totalDocuments} Dokumente</Badge>
                        {supplier.documentCounts.offene_rechnungen > 0 && (
                          <Badge variant="destructive">
                            {supplier.documentCounts.offene_rechnungen} offen
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>

                <CollapsibleContent>
                  <CardContent className="pt-0 pb-4">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 pl-8">
                      {SUPPLIER_CATEGORIES.map((category) => {
                        const count = supplier.documentCounts[category.id] || 0
                        return (
                          <Link
                            key={category.id}
                            to="/lieferanten/$entityId/$category"
                            params={{ entityId: supplier.id, category: category.id }}
                            className="flex items-center gap-2 p-2 rounded-md hover:bg-muted transition-colors group"
                          >
                            <FolderOpen className="w-4 h-4 text-blue-500 group-hover:text-blue-600" />
                            <span className="text-sm flex-1 truncate">
                              {category.label}
                              {category.shortCode && (
                                <span className="text-muted-foreground ml-1">
                                  ({category.shortCode})
                                </span>
                              )}
                            </span>
                            {count > 0 && (
                              <Badge
                                variant={category.isOpenStatus ? 'destructive' : 'secondary'}
                                className="text-xs"
                              >
                                {count}
                              </Badge>
                            )}
                          </Link>
                        )
                      })}
                    </div>
                  </CardContent>
                </CollapsibleContent>
              </Collapsible>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
```

---

#### 4.3 EntityAblageView.tsx

```tsx
import { useParams, Link } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CUSTOMER_CATEGORIES, SUPPLIER_CATEGORIES } from '../types'

interface EntityAblageViewProps {
  entityType: 'customer' | 'supplier'
}

export function EntityAblageView({ entityType }: EntityAblageViewProps) {
  const { entityId } = useParams({ strict: false })
  const categories = entityType === 'customer' ? CUSTOMER_CATEGORIES : SUPPLIER_CATEGORIES
  const basePath = entityType === 'customer' ? '/kunden' : '/lieferanten'
  const color = entityType === 'customer' ? 'amber' : 'blue'

  // TODO: Fetch entity data from API
  const entityName = entityType === 'customer' ? 'Spargelmesser' : 'Spargelmesser1'

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to={basePath}>
          <Button variant="ghost" size="icon">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <FolderOpen className={`w-8 h-8 text-${color}-500`} />
            {entityName}
          </h1>
          <p className="text-muted-foreground mt-1">
            {entityType === 'customer' ? 'Kunden' : 'Lieferanten'}-Dokumentenablage
          </p>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="flex gap-4">
        <Badge variant="secondary" className="text-sm py-1 px-3">
          <FileText className="w-4 h-4 mr-2" />
          156 Dokumente
        </Badge>
        <Badge variant="outline" className="text-sm py-1 px-3">
          Letzte Aktivität: 20.12.2024
        </Badge>
      </div>

      {/* Category Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        {categories.map((category) => (
          <Link
            key={category.id}
            to={`${basePath}/$entityId/$category`}
            params={{ entityId: entityId!, category: category.id }}
          >
            <Card className="hover:border-primary/50 hover:shadow-md transition-all cursor-pointer h-full">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <FolderOpen className={`w-5 h-5 text-${color}-500`} />
                  {category.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  {category.shortCode && (
                    <span className="text-xs text-muted-foreground">({category.shortCode})</span>
                  )}
                  <Badge variant={category.isOpenStatus ? 'destructive' : 'secondary'}>
                    12
                  </Badge>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Quick Upload */}
      <Card className="border-dashed">
        <CardContent className="flex items-center justify-center py-8">
          <Button variant="outline" className="gap-2">
            <Upload className="w-4 h-4" />
            Dokument zu {entityName} hochladen
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
```

---

#### 4.4 CategoryDocumentList.tsx

```tsx
import { useParams, Link } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, Upload, Filter, SortAsc } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { CUSTOMER_CATEGORIES, SUPPLIER_CATEGORIES } from '../types'

interface CategoryDocumentListProps {
  entityType: 'customer' | 'supplier'
}

// Mock documents
const MOCK_DOCUMENTS = [
  {
    id: '1',
    filename: 'RG-2024-00123.pdf',
    documentType: 'invoice',
    date: '2024-12-15',
    amount: 1234.56,
    status: 'processed',
  },
  {
    id: '2',
    filename: 'RG-2024-00124.pdf',
    documentType: 'invoice',
    date: '2024-12-18',
    amount: 567.89,
    status: 'pending',
  },
  {
    id: '3',
    filename: 'RG-2024-00125.pdf',
    documentType: 'invoice',
    date: '2024-12-20',
    amount: 2345.00,
    status: 'processed',
  },
]

export function CategoryDocumentList({ entityType }: CategoryDocumentListProps) {
  const { entityId, category } = useParams({ strict: false })
  const categories = entityType === 'customer' ? CUSTOMER_CATEGORIES : SUPPLIER_CATEGORIES
  const basePath = entityType === 'customer' ? '/kunden' : '/lieferanten'
  const color = entityType === 'customer' ? 'amber' : 'blue'

  const categoryInfo = categories.find((c) => c.id === category)
  const entityName = entityType === 'customer' ? 'Spargelmesser' : 'Spargelmesser1'

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to={`${basePath}/$entityId`} params={{ entityId: entityId! }}>
          <Button variant="ghost" size="icon">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <Link to={basePath} className="hover:text-foreground">
              {entityType === 'customer' ? 'Kunden' : 'Lieferanten'}
            </Link>
            <span>/</span>
            <Link
              to={`${basePath}/$entityId`}
              params={{ entityId: entityId! }}
              className="hover:text-foreground"
            >
              {entityName}
            </Link>
            <span>/</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <FolderOpen className={`w-8 h-8 text-${color}-500`} />
            {categoryInfo?.label}
            {categoryInfo?.shortCode && (
              <span className="text-lg text-muted-foreground">({categoryInfo.shortCode})</span>
            )}
          </h1>
        </div>
      </div>

      {/* Actions Bar */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="gap-2">
            <Filter className="w-4 h-4" />
            Filter
          </Button>
          <Button variant="outline" size="sm" className="gap-2">
            <SortAsc className="w-4 h-4" />
            Sortieren
          </Button>
        </div>
        <Button className="gap-2">
          <Upload className="w-4 h-4" />
          Dokument hochladen
        </Button>
      </div>

      {/* Document Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50px]"></TableHead>
                <TableHead>Dateiname</TableHead>
                <TableHead>Datum</TableHead>
                <TableHead className="text-right">Betrag</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_DOCUMENTS.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell>
                    <FileText className="w-4 h-4 text-muted-foreground" />
                  </TableCell>
                  <TableCell className="font-medium">
                    <Link
                      to="/documents/$documentId"
                      params={{ documentId: doc.id }}
                      className="hover:underline"
                    >
                      {doc.filename}
                    </Link>
                  </TableCell>
                  <TableCell>{doc.date}</TableCell>
                  <TableCell className="text-right font-mono">
                    {doc.amount.toLocaleString('de-DE', {
                      style: 'currency',
                      currency: 'EUR',
                    })}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={doc.status === 'processed' ? 'default' : 'secondary'}
                      className={
                        doc.status === 'processed'
                          ? 'bg-green-100 text-green-800 hover:bg-green-100'
                          : ''
                      }
                    >
                      {doc.status === 'processed' ? 'Verarbeitet' : 'Ausstehend'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm">
                      Öffnen
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
```

---

#### 4.5 index.ts (Feature Export)

```tsx
// frontend/src/features/ablage/index.ts
export * from './types'
export * from './components/KundenPage'
export * from './components/LieferantenPage'
export * from './components/EntityAblageView'
export * from './components/CategoryDocumentList'
```

---

### 5. Backend API Erweiterungen (Optional)

Falls benötigt, erweitere die bestehende Entity API:

**Datei: `app/api/v1/entities.py`**

Füge einen neuen Endpoint für Dokument-Zählungen pro Kategorie hinzu:

```python
@router.get(
    "/{entity_id}/document-counts",
    response_model=Dict[str, int],
    summary="Dokumentenzählung pro Kategorie",
    description="Gibt die Anzahl der Dokumente pro Ablage-Kategorie für eine Entity zurück"
)
async def get_entity_document_counts(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, int]:
    """
    Zählt Dokumente pro Kategorie für einen Geschäftspartner.

    Kategorien:
    - anfragen, angebote, auftragsbestaetigung, lieferscheine
    - rechnungen, bestellungen (nur Lieferanten), storno, mahnungen
    - offene_rechnungen, offene_angebote, offene_anfragen
    - reklamation, kommunikation, archiv
    """
    # Implementierung folgt...
    pass
```

---

## Zusammenfassung der zu erstellenden Dateien

### Frontend (Neu)

| Pfad | Beschreibung |
|------|--------------|
| `src/features/ablage/types.ts` | TypeScript Types und Konstanten |
| `src/features/ablage/index.ts` | Feature Exports |
| `src/features/ablage/components/KundenPage.tsx` | Kunden-Übersichtsseite |
| `src/features/ablage/components/LieferantenPage.tsx` | Lieferanten-Übersichtsseite |
| `src/features/ablage/components/EntityAblageView.tsx` | Entity-Detailansicht mit Kategorien |
| `src/features/ablage/components/CategoryDocumentList.tsx` | Dokumentenliste pro Kategorie |
| `src/app/routes/kunden.tsx` | Route: /kunden |
| `src/app/routes/kunden.$entityId.tsx` | Route: /kunden/:entityId |
| `src/app/routes/kunden.$entityId.$category.tsx` | Route: /kunden/:entityId/:category |
| `src/app/routes/lieferanten.tsx` | Route: /lieferanten |
| `src/app/routes/lieferanten.$entityId.tsx` | Route: /lieferanten/:entityId |
| `src/app/routes/lieferanten.$entityId.$category.tsx` | Route: /lieferanten/:entityId/:category |

### Frontend (Modifizieren)

| Pfad | Änderung |
|------|----------|
| `src/components/layout/Sidebar.tsx` | Neue Navigation-Links hinzufügen |

---

## Ausführungsreihenfolge

1. **Types erstellen** - `src/features/ablage/types.ts`
2. **Feature-Ordner anlegen** - `src/features/ablage/components/`
3. **Komponenten implementieren** - KundenPage, LieferantenPage, etc.
4. **Routes erstellen** - Alle 6 Route-Dateien
5. **Sidebar erweitern** - Navigation-Links hinzufügen
6. **Route-Generierung** - `npm run dev` triggert TanStack Router
7. **Testen** - Alle neuen Seiten durchklicken

---

## Hinweise

- Die Komponenten verwenden **Mock-Daten** als Platzhalter
- Die API-Integration sollte über **React Query** erfolgen (bereits im Projekt vorhanden)
- Farben: **Kunden = amber**, **Lieferanten = blue** (für visuelle Unterscheidung)
- Das `Bestellungen`-Feld erscheint **nur bei Lieferanten**
- Der Code folgt den bestehenden **Projekt-Konventionen** und **shadcn/ui** Patterns
