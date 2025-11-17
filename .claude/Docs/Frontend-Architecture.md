# Frontend Architecture - Ablage System

## 🎯 Überblick

Das Ablage-System Frontend ist eine moderne Single-Page Application (SPA) gebaut mit **React 18**, **TypeScript**, und **Vite**. Die Architektur legt Wert auf Type Safety, Performance, und Developer Experience.

---

## 🏗️ Tech Stack

### Core Framework

```json
{
  "framework": "React 18.2+",
  "language": "TypeScript 5.0+",
  "bundler": "Vite 5.0+",
  "package_manager": "pnpm 8.0+",
  "runtime": "Node.js 20 LTS"
}
```

**Warum React + TypeScript?**
- ✅ Starke TypeScript-Integration
- ✅ Große Community & Ecosystem
- ✅ Excellent Developer Experience
- ✅ Best-in-class Performance (React 18 Concurrent Features)
- ✅ Server Components (Future: Next.js Migration möglich)

**Warum Vite?**
- ⚡ Lightning-fast HMR (Hot Module Replacement)
- 📦 Optimized Production Builds
- 🔧 Zero Config (vs Webpack complexity)
- 🎯 Native ESM Support
- 🚀 Fast Cold Start

---

## 📁 Projektstruktur

```
frontend/
├── public/                     # Static assets
│   ├── favicon.ico
│   └── robots.txt
│
├── src/
│   ├── app/                    # App-level configuration
│   │   ├── App.tsx            # Root component
│   │   ├── Router.tsx         # Route definitions
│   │   └── Providers.tsx      # Context providers
│   │
│   ├── components/             # Reusable components
│   │   ├── ui/                # Base UI components (shadcn/ui)
│   │   │   ├── Button.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Card.tsx
│   │   │   └── ... (50+ components)
│   │   │
│   │   ├── layout/            # Layout components
│   │   │   ├── Header.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── Footer.tsx
│   │   │
│   │   └── features/          # Feature-specific components
│   │       ├── document/
│   │       │   ├── DocumentUpload.tsx
│   │       │   ├── DocumentList.tsx
│   │       │   └── DocumentViewer.tsx
│   │       │
│   │       ├── ocr/
│   │       │   ├── OCRResultsPanel.tsx
│   │       │   ├── OCRPreview.tsx
│   │       │   └── OCREditor.tsx
│   │       │
│   │       └── admin/
│   │           ├── UserManagement.tsx
│   │           └── SystemMonitor.tsx
│   │
│   ├── pages/                  # Page components (Route views)
│   │   ├── Dashboard.tsx
│   │   ├── Documents.tsx
│   │   ├── Upload.tsx
│   │   ├── Results.tsx
│   │   ├── Settings.tsx
│   │   └── Admin.tsx
│   │
│   ├── features/               # Feature slices (business logic)
│   │   ├── auth/
│   │   │   ├── api/           # API calls
│   │   │   ├── hooks/         # Custom hooks
│   │   │   ├── store/         # State management
│   │   │   └── types/         # TypeScript types
│   │   │
│   │   ├── documents/
│   │   │   ├── api/
│   │   │   ├── hooks/
│   │   │   ├── store/
│   │   │   └── types/
│   │   │
│   │   └── ocr/
│   │       ├── api/
│   │       ├── hooks/
│   │       ├── store/
│   │       └── types/
│   │
│   ├── lib/                    # Third-party library configs
│   │   ├── axios.ts           # Axios instance
│   │   ├── react-query.ts     # TanStack Query config
│   │   └── zod.ts             # Zod schemas
│   │
│   ├── hooks/                  # Global custom hooks
│   │   ├── useAuth.ts
│   │   ├── useToast.ts
│   │   └── useMediaQuery.ts
│   │
│   ├── utils/                  # Utility functions
│   │   ├── format.ts          # Formatters
│   │   ├── validation.ts      # Validators
│   │   └── constants.ts       # Constants
│   │
│   ├── types/                  # Global TypeScript types
│   │   ├── api.ts
│   │   ├── models.ts
│   │   └── utils.ts
│   │
│   ├── styles/                 # Global styles
│   │   ├── globals.css        # Tailwind directives
│   │   └── theme.ts           # Theme configuration
│   │
│   └── main.tsx                # Application entry point
│
├── tests/                      # Test files
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── .env.example                # Environment variables template
├── .env.local                  # Local environment variables
├── tsconfig.json               # TypeScript configuration
├── vite.config.ts              # Vite configuration
├── tailwind.config.js          # Tailwind CSS configuration
├── package.json                # Dependencies
└── pnpm-lock.yaml              # Lock file
```

---

## 🎨 UI Component Library

### Shadcn/UI + Tailwind CSS

**Warum shadcn/ui?**
- ✅ Copy-paste components (kein NPM-Paket-Overhead)
- ✅ Vollständig anpassbar
- ✅ Radix UI primitives (a11y, keyboard navigation)
- ✅ Tailwind CSS styling
- ✅ TypeScript-first

**Installation:**
```bash
# Install shadcn/ui CLI
pnpm dlx shadcn-ui@latest init

# Add components
pnpm dlx shadcn-ui@latest add button
pnpm dlx shadcn-ui@latest add input
pnpm dlx shadcn-ui@latest add card
pnpm dlx shadcn-ui@latest add dialog
pnpm dlx shadcn-ui@latest add dropdown-menu
pnpm dlx shadcn-ui@latest add table
pnpm dlx shadcn-ui@latest add toast
```

### Custom Theme

```typescript
// src/styles/theme.ts

export const theme = {
  colors: {
    primary: {
      50: '#f0f9ff',
      100: '#e0f2fe',
      500: '#0ea5e9',
      600: '#0284c7',
      900: '#0c4a6e',
    },
    success: {
      500: '#10b981',
      600: '#059669',
    },
    danger: {
      500: '#ef4444',
      600: '#dc2626',
    },
    warning: {
      500: '#f59e0b',
      600: '#d97706',
    },
  },
  fonts: {
    sans: 'Inter, system-ui, sans-serif',
    mono: 'JetBrains Mono, monospace',
  },
  breakpoints: {
    sm: '640px',
    md: '768px',
    lg: '1024px',
    xl: '1280px',
    '2xl': '1536px',
  },
}
```

---

## 🗺️ Routing

### React Router v6

```typescript
// src/app/Router.tsx

import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { lazy, Suspense } from 'react'

// Lazy load pages for code splitting
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Documents = lazy(() => import('@/pages/Documents'))
const Upload = lazy(() => import('@/pages/Upload'))
const Results = lazy(() => import('@/pages/Results'))
const Settings = lazy(() => import('@/pages/Settings'))
const Admin = lazy(() => import('@/pages/Admin'))

// Auth guards
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { AdminRoute } from '@/components/auth/AdminRoute'

const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      {
        index: true,
        element: <Landing />,
      },
      {
        path: 'login',
        element: <Login />,
      },
      {
        path: 'register',
        element: <Register />,
      },
      {
        path: 'app',
        element: <ProtectedRoute />,
        children: [
          {
            path: 'dashboard',
            element: <Dashboard />,
          },
          {
            path: 'documents',
            element: <Documents />,
          },
          {
            path: 'documents/:id',
            element: <DocumentDetail />,
          },
          {
            path: 'upload',
            element: <Upload />,
          },
          {
            path: 'results/:jobId',
            element: <Results />,
          },
          {
            path: 'settings',
            element: <Settings />,
          },
          {
            path: 'admin',
            element: <AdminRoute />,
            children: [
              {
                path: 'users',
                element: <UserManagement />,
              },
              {
                path: 'system',
                element: <SystemMonitor />,
              },
            ],
          },
        ],
      },
    ],
  },
])

export function Router() {
  return (
    <Suspense fallback={<PageLoader />}>
      <RouterProvider router={router} />
    </Suspense>
  )
}
```

---

## 🔐 Authentication Flow

### JWT Token Management

```typescript
// src/features/auth/hooks/useAuth.ts

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean

  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshAccessToken: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      login: async (email, password) => {
        const response = await authApi.login({ email, password })

        set({
          user: response.user,
          accessToken: response.access_token,
          refreshToken: response.refresh_token,
          isAuthenticated: true,
        })
      },

      logout: () => {
        // Clear tokens
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        })

        // Redirect to login
        window.location.href = '/login'
      },

      refreshAccessToken: async () => {
        const { refreshToken } = get()
        if (!refreshToken) throw new Error('No refresh token')

        const response = await authApi.refresh({ refresh_token: refreshToken })

        set({
          accessToken: response.access_token,
        })
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        // Only persist these fields
        refreshToken: state.refreshToken,
      }),
    }
  )
)
```

### Axios Interceptor

```typescript
// src/lib/axios.ts

import axios from 'axios'
import { useAuthStore } from '@/features/auth/hooks/useAuth'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
})

// Request interceptor: Add auth token
apiClient.interceptors.request.use(
  (config) => {
    const { accessToken } = useAuthStore.getState()

    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }

    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: Handle token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // If 401 and not already retried
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        // Refresh token
        await useAuthStore.getState().refreshAccessToken()

        // Retry original request
        return apiClient(originalRequest)
      } catch (refreshError) {
        // Refresh failed, logout
        useAuthStore.getState().logout()
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient
```

---

## 📤 File Upload Component

### Multi-File Upload with Progress

```typescript
// src/components/features/document/DocumentUpload.tsx

import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useMutation } from '@tanstack/react-query'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { Upload, X, FileText } from 'lucide-react'

interface UploadFile {
  file: File
  progress: number
  status: 'pending' | 'uploading' | 'success' | 'error'
  jobId?: string
  error?: string
}

export function DocumentUpload() {
  const [files, setFiles] = useState<UploadFile[]>([])

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)

      const response = await apiClient.post<{ job_id: string }>(
        '/api/v1/ocr/process',
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          onUploadProgress: (progressEvent) => {
            const progress = Math.round(
              (progressEvent.loaded * 100) / (progressEvent.total ?? 100)
            )

            setFiles((prev) =>
              prev.map((f) =>
                f.file === file
                  ? { ...f, progress, status: 'uploading' as const }
                  : f
              )
            )
          },
        }
      )

      return response.data
    },
    onSuccess: (data, file) => {
      setFiles((prev) =>
        prev.map((f) =>
          f.file === file
            ? { ...f, status: 'success' as const, jobId: data.job_id }
            : f
        )
      )
    },
    onError: (error, file) => {
      setFiles((prev) =>
        prev.map((f) =>
          f.file === file
            ? {
                ...f,
                status: 'error' as const,
                error: error.message,
              }
            : f
        )
      )
    },
  })

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles: UploadFile[] = acceptedFiles.map((file) => ({
      file,
      progress: 0,
      status: 'pending',
    }))

    setFiles((prev) => [...prev, ...newFiles])

    // Start uploading
    newFiles.forEach((f) => {
      uploadMutation.mutate(f.file)
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/tiff': ['.tiff', '.tif'],
    },
    maxSize: 100 * 1024 * 1024, // 100MB
  })

  const removeFile = (file: File) => {
    setFiles((prev) => prev.filter((f) => f.file !== file))
  }

  return (
    <div className="space-y-4">
      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-lg p-12 text-center cursor-pointer
          transition-colors
          ${
            isDragActive
              ? 'border-primary bg-primary/10'
              : 'border-gray-300 hover:border-gray-400'
          }
        `}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
        <p className="text-lg font-medium">
          {isDragActive
            ? 'Drop files here...'
            : 'Drag & drop files here, or click to select'}
        </p>
        <p className="text-sm text-gray-500 mt-2">
          Supported: PDF, PNG, JPG, TIFF (max 100MB)
        </p>
      </div>

      {/* File List */}
      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((uploadFile) => (
            <FileUploadItem
              key={uploadFile.file.name}
              uploadFile={uploadFile}
              onRemove={() => removeFile(uploadFile.file)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function FileUploadItem({
  uploadFile,
  onRemove,
}: {
  uploadFile: UploadFile
  onRemove: () => void
}) {
  return (
    <div className="flex items-center gap-3 p-4 border rounded-lg">
      <FileText className="h-8 w-8 text-gray-400 flex-shrink-0" />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{uploadFile.file.name}</p>
        <p className="text-xs text-gray-500">
          {(uploadFile.file.size / 1024 / 1024).toFixed(2)} MB
        </p>

        {uploadFile.status === 'uploading' && (
          <Progress value={uploadFile.progress} className="mt-2" />
        )}

        {uploadFile.status === 'success' && (
          <p className="text-xs text-green-600 mt-1">
            ✓ Uploaded successfully
          </p>
        )}

        {uploadFile.status === 'error' && (
          <p className="text-xs text-red-600 mt-1">
            ✗ {uploadFile.error || 'Upload failed'}
          </p>
        )}
      </div>

      <Button
        variant="ghost"
        size="icon"
        onClick={onRemove}
        className="flex-shrink-0"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}
```

---

## 📊 State Management

### Zustand for Global State

```typescript
// src/features/documents/store/documentsStore.ts

import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

interface Document {
  id: string
  filename: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  ocr_result?: OCRResult
}

interface DocumentsState {
  documents: Document[]
  selectedDocument: Document | null
  isLoading: boolean

  // Actions
  setDocuments: (documents: Document[]) => void
  addDocument: (document: Document) => void
  updateDocument: (id: string, updates: Partial<Document>) => void
  selectDocument: (document: Document | null) => void
}

export const useDocumentsStore = create<DocumentsState>()(
  devtools((set) => ({
    documents: [],
    selectedDocument: null,
    isLoading: false,

    setDocuments: (documents) => set({ documents }),

    addDocument: (document) =>
      set((state) => ({
        documents: [document, ...state.documents],
      })),

    updateDocument: (id, updates) =>
      set((state) => ({
        documents: state.documents.map((doc) =>
          doc.id === id ? { ...doc, ...updates } : doc
        ),
      })),

    selectDocument: (document) => set({ selectedDocument: document }),
  }))
)
```

### TanStack Query for Server State

```typescript
// src/features/documents/hooks/useDocuments.ts

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsApi } from '../api/documentsApi'

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: documentsApi.list,
    staleTime: 30000, // 30 seconds
    refetchInterval: 10000, // Poll every 10s for status updates
  })
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: ['documents', id],
    queryFn: () => documentsApi.get(id),
    enabled: !!id,
  })
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: documentsApi.delete,
    onSuccess: () => {
      // Invalidate and refetch
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}
```

---

## 🔄 Real-time Updates

### Server-Sent Events (SSE)

```typescript
// src/features/ocr/hooks/useJobStatus.ts

import { useEffect, useState } from 'react'
import { useToast } from '@/hooks/useToast'

interface JobStatus {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress?: number
  result?: OCRResult
}

export function useJobStatus(jobId: string) {
  const [status, setStatus] = useState<JobStatus | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (!jobId) return

    // Create EventSource
    const eventSource = new EventSource(
      `${import.meta.env.VITE_API_BASE_URL}/api/v1/ocr/status/${jobId}/stream`
    )

    eventSource.onmessage = (event) => {
      const data: JobStatus = JSON.parse(event.data)
      setStatus(data)

      // Show notification on completion
      if (data.status === 'completed') {
        toast({
          title: 'OCR completed!',
          description: `Document ${jobId} processed successfully`,
        })
        eventSource.close()
      }

      if (data.status === 'failed') {
        toast({
          variant: 'destructive',
          title: 'OCR failed',
          description: `Processing failed for document ${jobId}`,
        })
        eventSource.close()
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }, [jobId, toast])

  return status
}
```

---

## 🎨 Theming & Dark Mode

### CSS Variables + Tailwind

```typescript
// src/hooks/useTheme.ts

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
}

export const useTheme = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'system',
      setTheme: (theme) => {
        set({ theme })

        const root = window.document.documentElement
        root.classList.remove('light', 'dark')

        if (theme === 'system') {
          const systemTheme = window.matchMedia('(prefers-color-scheme: dark)')
            .matches
            ? 'dark'
            : 'light'
          root.classList.add(systemTheme)
        } else {
          root.classList.add(theme)
        }
      },
    }),
    {
      name: 'theme-storage',
    }
  )
)
```

```css
/* src/styles/globals.css */

@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 221.2 83.2% 53.3%;
    --primary-foreground: 210 40% 98%;
    /* ... more variables */
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --primary: 217.2 91.2% 59.8%;
    --primary-foreground: 222.2 47.4% 11.2%;
    /* ... more variables */
  }
}
```

---

## 📱 Responsive Design

### Mobile-First Breakpoints

```typescript
// src/hooks/useMediaQuery.ts

import { useEffect, useState } from 'react'

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    const media = window.matchMedia(query)
    setMatches(media.matches)

    const listener = () => setMatches(media.matches)
    media.addEventListener('change', listener)

    return () => media.removeEventListener('change', listener)
  }, [query])

  return matches
}

// Usage
export function useIsMobile() {
  return useMediaQuery('(max-width: 768px)')
}

export function useIsTablet() {
  return useMediaQuery('(max-width: 1024px)')
}
```

---

## 🧪 Testing Strategy

### Unit Tests (Vitest)

```typescript
// src/components/features/document/DocumentUpload.test.tsx

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DocumentUpload } from './DocumentUpload'

describe('DocumentUpload', () => {
  it('renders dropzone', () => {
    render(<DocumentUpload />)
    expect(
      screen.getByText(/Drag & drop files here/i)
    ).toBeInTheDocument()
  })

  it('accepts PDF files', async () => {
    const { container } = render(<DocumentUpload />)
    const input = container.querySelector('input[type="file"]')!

    const file = new File(['dummy'], 'test.pdf', {
      type: 'application/pdf',
    })

    fireEvent.change(input, { target: { files: [file] } })

    expect(await screen.findByText('test.pdf')).toBeInTheDocument()
  })
})
```

### E2E Tests (Playwright)

```typescript
// tests/e2e/upload.spec.ts

import { test, expect } from '@playwright/test'

test('complete upload flow', async ({ page }) => {
  // Navigate to upload page
  await page.goto('http://localhost:5173/app/upload')

  // Upload file
  await page.setInputFiles('input[type="file"]', 'test-files/invoice.pdf')

  // Wait for upload
  await expect(page.getByText('✓ Uploaded successfully')).toBeVisible({
    timeout: 10000,
  })

  // Navigate to results
  await page.click('text=View Results')

  // Verify OCR results
  await expect(page.getByText('OCR Results')).toBeVisible()
})
```

---

## 🚀 Build & Deployment

### Production Build

```bash
# Build for production
pnpm build

# Preview production build
pnpm preview
```

### Environment Variables

```bash
# .env.production

VITE_API_BASE_URL=https://api.ablage-system.com
VITE_ENABLE_ANALYTICS=true
VITE_SENTRY_DSN=https://xxx@sentry.io/xxx
```

### Docker

```dockerfile
# Dockerfile.frontend

FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source code
COPY . .

# Build
RUN pnpm build

# Production image
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

---

## 📚 Best Practices

### 1. Component Organization
- ✅ Co-locate related files (component + styles + tests)
- ✅ Use barrel exports (index.ts)
- ✅ Keep components small (< 200 lines)

### 2. Type Safety
- ✅ Use TypeScript strict mode
- ✅ Define prop types with interfaces
- ✅ Use Zod for runtime validation

### 3. Performance
- ✅ Lazy load routes
- ✅ Use React.memo for expensive components
- ✅ Virtualize long lists (react-virtual)
- ✅ Optimize images (next/image patterns)

### 4. Accessibility
- ✅ Use semantic HTML
- ✅ Add ARIA labels
- ✅ Keyboard navigation
- ✅ Focus management

---

## 🔗 Further Resources

- [React Documentation](https://react.dev/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Vite Guide](https://vitejs.dev/guide/)
- [shadcn/ui Components](https://ui.shadcn.com/)
- [TanStack Query](https://tanstack.com/query/latest)
- [Zustand Documentation](https://zustand-demo.pmnd.rs/)
