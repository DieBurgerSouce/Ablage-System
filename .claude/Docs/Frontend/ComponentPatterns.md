# Frontend Component Patterns

## Ablage-System OCR Platform

**Framework**: React 18 + TypeScript 5.x
**Router**: TanStack Router
**UI Library**: shadcn/ui + Tailwind CSS
**State Management**: TanStack Query

---

## Verzeichnisstruktur

```
frontend/src/
├── app/
│   └── routes/              # TanStack Router Routen
│       ├── __root.tsx       # Root-Layout
│       ├── index.tsx        # Dashboard
│       ├── upload.tsx       # Upload-Flow
│       ├── documents.$documentId.tsx
│       └── admin.*.tsx      # Admin-Bereich
├── components/
│   ├── ui/                  # shadcn/ui Basis-Komponenten
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   └── ...
│   ├── layout/              # Layout-Komponenten
│   │   ├── AppLayout.tsx
│   │   ├── Sidebar.tsx
│   │   └── ThemeToggle.tsx
│   └── settings/            # Settings-Modal Tabs
├── features/                # Feature-Module
│   ├── documents/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── api/
│   ├── upload/
│   ├── viewer/
│   └── ...
├── lib/
│   ├── api/                 # API-Client
│   ├── auth/                # Auth-Context
│   └── theme/               # Theme-System
└── hooks/                   # Globale Custom Hooks
```

---

## Component Patterns

### 1. Feature-basierte Organisation

Jedes Feature hat seine eigene Struktur:

```
features/documents/
├── components/
│   ├── DocumentCard.tsx
│   ├── DocumentGrid.tsx
│   └── DocumentBadges.tsx
├── hooks/
│   └── use-documents.ts
├── api/
│   └── documents-api.ts
└── types/
    └── document.types.ts
```

### 2. Komponenten-Struktur

```tsx
// features/documents/components/DocumentCard.tsx

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DocumentBadges } from "./DocumentBadges";
import type { Document } from "../types/document.types";

interface DocumentCardProps {
  document: Document;
  onSelect?: (id: string) => void;
  isSelected?: boolean;
}

export function DocumentCard({
  document,
  onSelect,
  isSelected = false,
}: DocumentCardProps) {
  return (
    <Card
      className={cn(
        "cursor-pointer transition-colors hover:bg-accent",
        isSelected && "border-primary"
      )}
      onClick={() => onSelect?.(document.id)}
    >
      <CardHeader>
        <h3 className="font-semibold truncate">{document.filename}</h3>
      </CardHeader>
      <CardContent>
        <DocumentBadges document={document} />
      </CardContent>
    </Card>
  );
}
```

### 3. Props-Interface Pattern

```tsx
// Explizite Props mit Optionalität
interface ComponentProps {
  // Required props
  data: DataType;

  // Optional props mit Defaults
  variant?: "default" | "compact" | "expanded";
  className?: string;

  // Event handlers
  onClick?: (event: React.MouseEvent) => void;
  onSelect?: (item: DataType) => void;

  // Children
  children?: React.ReactNode;
}

// Default Values im Funktionskopf
export function Component({
  data,
  variant = "default",
  className,
  onClick,
  onSelect,
  children,
}: ComponentProps) {
  // ...
}
```

---

## Hook Patterns

### 1. Custom Data Hooks

```tsx
// features/documents/hooks/use-documents.ts

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { documentsApi } from "../api/documents-api";

// Query Keys
export const documentKeys = {
  all: ["documents"] as const,
  lists: () => [...documentKeys.all, "list"] as const,
  list: (filters: DocumentFilters) =>
    [...documentKeys.lists(), filters] as const,
  details: () => [...documentKeys.all, "detail"] as const,
  detail: (id: string) => [...documentKeys.details(), id] as const,
};

// Liste abrufen
export function useDocuments(filters: DocumentFilters) {
  return useQuery({
    queryKey: documentKeys.list(filters),
    queryFn: () => documentsApi.list(filters),
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

// Einzelnes Dokument
export function useDocument(id: string) {
  return useQuery({
    queryKey: documentKeys.detail(id),
    queryFn: () => documentsApi.get(id),
    enabled: !!id,
  });
}

// Mutation
export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: documentsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}
```

### 2. UI State Hooks

```tsx
// hooks/use-disclosure.ts

import { useState, useCallback } from "react";

export function useDisclosure(initial = false) {
  const [isOpen, setIsOpen] = useState(initial);

  const onOpen = useCallback(() => setIsOpen(true), []);
  const onClose = useCallback(() => setIsOpen(false), []);
  const onToggle = useCallback(() => setIsOpen((prev) => !prev), []);

  return { isOpen, onOpen, onClose, onToggle };
}

// Verwendung
const { isOpen, onOpen, onClose } = useDisclosure();
```

---

## API-Client Pattern

```tsx
// lib/api/documents-api.ts

import { apiClient } from "./client";
import type { Document, DocumentFilters, CreateDocumentDto } from "@/types";

export const documentsApi = {
  list: async (filters: DocumentFilters): Promise<Document[]> => {
    const response = await apiClient.get("/api/v1/documents", {
      params: filters,
    });
    return response.data;
  },

  get: async (id: string): Promise<Document> => {
    const response = await apiClient.get(`/api/v1/documents/${id}`);
    return response.data;
  },

  create: async (data: CreateDocumentDto): Promise<Document> => {
    const response = await apiClient.post("/api/v1/documents", data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/documents/${id}`);
  },
};
```

---

## Form Patterns

### 1. Controlled Forms

```tsx
// features/business-entities/components/BusinessEntityForm.tsx

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

const businessEntitySchema = z.object({
  name: z.string().min(2, "Name muss mindestens 2 Zeichen haben"),
  vatId: z.string().regex(/^DE\d{9}$/, "Ungültige USt-IdNr.").optional(),
  email: z.string().email("Ungültige E-Mail-Adresse").optional(),
});

type BusinessEntityFormData = z.infer<typeof businessEntitySchema>;

interface BusinessEntityFormProps {
  initialData?: Partial<BusinessEntityFormData>;
  onSubmit: (data: BusinessEntityFormData) => void;
}

export function BusinessEntityForm({
  initialData,
  onSubmit,
}: BusinessEntityFormProps) {
  const form = useForm<BusinessEntityFormData>({
    resolver: zodResolver(businessEntitySchema),
    defaultValues: initialData,
  });

  return (
    <form onSubmit={form.handleSubmit(onSubmit)}>
      <FormField
        control={form.control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Name</FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      {/* Weitere Felder */}
      <Button type="submit">Speichern</Button>
    </form>
  );
}
```

---

## Error Handling

### 1. Error Boundary (Global)

```tsx
// components/ErrorBoundary.tsx

import { Component, ErrorInfo, ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <Alert variant="destructive">
            <AlertTitle>Ein Fehler ist aufgetreten</AlertTitle>
            <AlertDescription>
              {this.state.error?.message || "Unbekannter Fehler"}
            </AlertDescription>
            <Button
              variant="outline"
              onClick={() => this.setState({ hasError: false })}
            >
              Erneut versuchen
            </Button>
          </Alert>
        )
      );
    }

    return this.props.children;
  }
}
```

### 2. Query Error Handling

```tsx
// Globaler Error Handler
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      onError: (error) => {
        console.error("Query error:", error);
        toast.error("Fehler beim Laden der Daten");
      },
    },
    mutations: {
      onError: (error) => {
        console.error("Mutation error:", error);
        toast.error("Fehler beim Speichern");
      },
    },
  },
});
```

---

## Loading States

### 1. Skeleton Pattern

```tsx
// components/ui/skeleton.tsx

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

// Verwendung
function DocumentCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-3/4" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-4 w-full mb-2" />
        <Skeleton className="h-4 w-2/3" />
      </CardContent>
    </Card>
  );
}
```

### 2. Suspense Boundaries

```tsx
import { Suspense } from "react";

function DocumentsPage() {
  return (
    <Suspense fallback={<DocumentGridSkeleton />}>
      <DocumentGrid />
    </Suspense>
  );
}
```

---

## Accessibility

### 1. ARIA Labels

```tsx
<Button
  aria-label="Dokument löschen"
  onClick={handleDelete}
>
  <TrashIcon className="h-4 w-4" />
</Button>
```

### 2. Keyboard Navigation

```tsx
function ListItem({ onSelect }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
    >
      {/* Content */}
    </div>
  );
}
```

---

## Testing Patterns

### 1. Component Tests

```tsx
// features/documents/__tests__/DocumentCard.test.tsx

import { render, screen, fireEvent } from "@testing-library/react";
import { DocumentCard } from "../components/DocumentCard";

const mockDocument = {
  id: "1",
  filename: "test.pdf",
  status: "completed",
};

describe("DocumentCard", () => {
  it("renders document filename", () => {
    render(<DocumentCard document={mockDocument} />);
    expect(screen.getByText("test.pdf")).toBeInTheDocument();
  });

  it("calls onSelect when clicked", () => {
    const onSelect = vi.fn();
    render(<DocumentCard document={mockDocument} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("article"));
    expect(onSelect).toHaveBeenCalledWith("1");
  });
});
```

---

## Best Practices

### 1. Naming Conventions

| Element | Convention | Beispiel |
|---------|------------|----------|
| Komponenten | PascalCase | `DocumentCard.tsx` |
| Hooks | camelCase mit `use` | `useDocuments.ts` |
| Utils | camelCase | `formatDate.ts` |
| Types | PascalCase | `Document` |
| Enums | PascalCase | `DocumentStatus` |

### 2. Import-Reihenfolge

```tsx
// 1. React/Framework
import { useState, useEffect } from "react";

// 2. Third-party Libraries
import { useQuery } from "@tanstack/react-query";

// 3. UI Components
import { Button } from "@/components/ui/button";

// 4. Feature Components
import { DocumentCard } from "./DocumentCard";

// 5. Hooks
import { useDocuments } from "../hooks/use-documents";

// 6. Utils/Types
import { formatDate } from "@/lib/utils";
import type { Document } from "../types";
```

### 3. Component Size

- **Max. 200 Zeilen** pro Komponente
- Bei mehr: Aufteilen in Sub-Komponenten
- Logik in Custom Hooks extrahieren

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2024-12-18 | 1.0 | Initial Release |
