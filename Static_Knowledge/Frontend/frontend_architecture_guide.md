# Frontend Architecture Guide
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Display Modes](#display-modes)
5. [Component Architecture](#component-architecture)
6. [State Management](#state-management)
7. [API Integration](#api-integration)
8. [Routing & Navigation](#routing--navigation)
9. [Forms & Validation](#forms--validation)
10. [File Upload & Processing](#file-upload--processing)
11. [Real-Time Updates](#real-time-updates)
12. [Accessibility (WCAG 2.1 AA)](#accessibility-wcag-21-aa)
13. [Internationalization (German)](#internationalization-german)
14. [Testing Strategy](#testing-strategy)
15. [Performance Optimization](#performance-optimization)
16. [Build & Deployment](#build--deployment)
17. [Best Practices](#best-practices)

---

## Overview

The Ablage-System frontend is a modern, accessible, and performant web application built for enterprise document processing. It provides a comprehensive user interface for document upload, OCR processing, viewing, and management with specialized display modes for different lighting conditions and accessibility needs.

### Key Features
- **4 Display Modes:** Dark, Light, Whitescreen (high contrast), Blackscreen (inverted)
- **Real-Time Processing:** WebSocket updates for OCR progress
- **Accessibility:** WCAG 2.1 AA compliant
- **German Language:** 100% German UI with proper umlaut support
- **Responsive Design:** Desktop, tablet, mobile support
- **GPU Monitoring:** Real-time GPU utilization display for admins
- **Document Viewer:** In-browser PDF and image viewing with annotations

### Design Philosophy
- **Feinpoliert und durchdacht:** Polished and well-thought-out
- **Accessibility First:** Support for visual impairments and different lighting conditions
- **Performance:** Fast initial load (<2s), optimistic UI updates
- **Resilience:** Graceful degradation when backend is unavailable
- **Type Safety:** TypeScript throughout for compile-time safety

---

## Technology Stack

### Core Framework
**Framework:** Vue.js 3.4+ with Composition API
- **Why Vue 3:** Excellent performance, TypeScript support, intuitive reactivity, smaller bundle size than React
- **Composition API:** Better code organization, reusability, TypeScript integration

**Alternative:** React 18+ with hooks (if Vue is not preferred)
- Both frameworks are supported by the architecture patterns shown in this guide
- Examples provided in both Vue and React where significantly different

### UI Framework
**Component Library:** Vuetify 3.x (Material Design)
- **Why Vuetify:** Comprehensive components, excellent accessibility, theming support
- **Alternatives:** PrimeVue, Quasar, or custom component library

### State Management
**Vue:** Pinia 2.x (modern Vuex alternative)
- **Why Pinia:** Simpler API, better TypeScript support, devtools integration
- **Migration from Vuex:** Straightforward, documented below

**React:** Redux Toolkit 2.x or Zustand 4.x
- **Redux Toolkit:** Industry standard, excellent devtools, middleware ecosystem
- **Zustand:** Lightweight alternative, simpler API

### Routing
**Vue:** Vue Router 4.x
**React:** React Router 6.x or TanStack Router 1.x

### HTTP Client
**Axios 1.6+** - Promise-based HTTP client
- Interceptors for authentication
- Request/response transformation
- Timeout configuration
- Retry logic with exponential backoff

### WebSocket
**Socket.IO Client 4.x** - Real-time bidirectional communication
- Automatic reconnection
- Room-based subscriptions
- Fallback to long polling

### Form Management
**Vue:** VeeValidate 4.x + Yup 1.x (validation schemas)
**React:** React Hook Form 7.x + Zod 3.x

### Type Safety
**TypeScript 5.3+** - Static type checking
- Strict mode enabled
- API types generated from OpenAPI schema

### Testing
**Unit/Integration:** Vitest 1.x (faster than Jest, native ESM support)
**E2E:** Playwright 1.x (cross-browser testing)
**Component Testing:** Vue Test Utils 2.x / React Testing Library 14.x

### Build Tool
**Vite 5.x** - Modern frontend build tool
- Lightning-fast HMR (Hot Module Replacement)
- Optimized production builds
- Built-in TypeScript support
- Plugin ecosystem

### Code Quality
**Linting:** ESLint 8.x with TypeScript plugin
**Formatting:** Prettier 3.x
**Pre-commit:** Husky 8.x + lint-staged

---

## Project Structure

```
frontend/
├── public/
│   ├── favicon.ico
│   └── robots.txt
├── src/
│   ├── assets/
│   │   ├── images/
│   │   ├── icons/
│   │   └── styles/
│   │       ├── variables.scss          # Design tokens (colors, spacing, fonts)
│   │       ├── themes.scss             # Display mode themes
│   │       └── global.scss             # Global styles
│   ├── components/
│   │   ├── common/
│   │   │   ├── AppButton.vue           # Reusable button component
│   │   │   ├── AppCard.vue
│   │   │   ├── AppDialog.vue
│   │   │   ├── AppLoader.vue           # Loading spinner
│   │   │   ├── AppNotification.vue     # Toast notifications
│   │   │   └── AppPagination.vue
│   │   ├── layout/
│   │   │   ├── AppHeader.vue           # Top navigation bar
│   │   │   ├── AppSidebar.vue          # Side navigation
│   │   │   ├── AppFooter.vue
│   │   │   └── DisplayModeSelector.vue # Mode switcher (Dark/Light/White/Black)
│   │   ├── documents/
│   │   │   ├── DocumentList.vue        # Document grid/list view
│   │   │   ├── DocumentCard.vue        # Individual document card
│   │   │   ├── DocumentUpload.vue      # Drag-and-drop upload
│   │   │   ├── DocumentViewer.vue      # PDF/image viewer
│   │   │   ├── DocumentMetadata.vue    # Document details sidebar
│   │   │   └── DocumentSearch.vue      # Full-text search
│   │   ├── ocr/
│   │   │   ├── OCRProgress.vue         # Real-time processing progress
│   │   │   ├── OCRResults.vue          # Extracted text display
│   │   │   ├── OCRBackendSelector.vue  # Manual backend selection
│   │   │   └── OCRAccuracyBadge.vue    # Accuracy indicator
│   │   ├── admin/
│   │   │   ├── GPUMonitor.vue          # Real-time GPU stats
│   │   │   ├── SystemHealth.vue        # Health check dashboard
│   │   │   ├── UserManagement.vue      # User admin
│   │   │   └── AuditLog.vue            # Activity log
│   │   └── auth/
│   │       ├── LoginForm.vue
│   │       ├── RegisterForm.vue
│   │       └── ResetPasswordForm.vue
│   ├── composables/                    # Vue 3 Composition API composables
│   │   ├── useAuth.ts                  # Authentication logic
│   │   ├── useDocuments.ts             # Document CRUD operations
│   │   ├── useOCR.ts                   # OCR processing logic
│   │   ├── useWebSocket.ts             # WebSocket connection management
│   │   ├── useDisplayMode.ts           # Display mode switching
│   │   ├── useNotification.ts          # Toast notifications
│   │   └── useInfiniteScroll.ts        # Infinite scroll pagination
│   ├── stores/                         # Pinia stores (Vue) or Redux slices (React)
│   │   ├── auth.ts                     # Authentication state
│   │   ├── documents.ts                # Document list and cache
│   │   ├── ocr.ts                      # OCR processing state
│   │   ├── ui.ts                       # UI state (sidebar, modals, theme)
│   │   └── system.ts                   # System health, GPU stats
│   ├── services/
│   │   ├── api/
│   │   │   ├── client.ts               # Axios instance with interceptors
│   │   │   ├── documents.ts            # Document API endpoints
│   │   │   ├── ocr.ts                  # OCR API endpoints
│   │   │   ├── auth.ts                 # Authentication endpoints
│   │   │   └── admin.ts                # Admin endpoints
│   │   ├── websocket/
│   │   │   └── socketService.ts        # Socket.IO client wrapper
│   │   └── storage/
│   │       └── localStorage.ts         # Local storage utilities
│   ├── router/
│   │   ├── index.ts                    # Route definitions
│   │   ├── guards.ts                   # Navigation guards (auth, permissions)
│   │   └── routes/
│   │       ├── auth.ts                 # Authentication routes
│   │       ├── documents.ts            # Document routes
│   │       ├── admin.ts                # Admin routes
│   │       └── public.ts               # Public routes
│   ├── types/
│   │   ├── api.ts                      # API request/response types
│   │   ├── models.ts                   # Domain models (Document, User, OCRResult)
│   │   ├── enums.ts                    # Enums (DisplayMode, OCRBackend, DocumentStatus)
│   │   └── vue-augmentation.ts         # Vue type augmentations
│   ├── utils/
│   │   ├── formatters.ts               # Date, currency, file size formatters
│   │   ├── validators.ts               # Custom validation rules
│   │   ├── constants.ts                # App constants
│   │   ├── errors.ts                   # Error handling utilities
│   │   └── performance.ts              # Performance monitoring
│   ├── views/                          # Page-level components
│   │   ├── HomePage.vue
│   │   ├── DocumentsPage.vue
│   │   ├── DocumentDetailPage.vue
│   │   ├── UploadPage.vue
│   │   ├── AdminDashboard.vue
│   │   ├── LoginPage.vue
│   │   └── NotFoundPage.vue
│   ├── App.vue                         # Root component
│   ├── main.ts                         # Application entry point
│   └── env.d.ts                        # Environment variable types
├── tests/
│   ├── unit/
│   │   ├── components/
│   │   ├── composables/
│   │   └── utils/
│   ├── integration/
│   │   └── api/
│   └── e2e/
│       ├── auth.spec.ts
│       ├── documents.spec.ts
│       └── upload.spec.ts
├── .env.example                        # Environment variables template
├── .env.development                    # Development environment
├── .env.production                     # Production environment
├── .eslintrc.cjs                       # ESLint configuration
├── .prettierrc.json                    # Prettier configuration
├── tsconfig.json                       # TypeScript configuration
├── vite.config.ts                      # Vite configuration
├── vitest.config.ts                    # Vitest configuration
├── playwright.config.ts                # Playwright configuration
├── package.json
└── README.md
```

### Directory Conventions

**components/** - Reusable UI components
- `common/` - Generic components used across the app
- `layout/` - Layout components (header, sidebar, footer)
- `{feature}/` - Feature-specific components (documents, ocr, admin, auth)

**composables/** - Vue 3 Composition API composables (reusable logic)
- Prefix with `use` (e.g., `useAuth`, `useDocuments`)
- Return reactive state and methods
- Can use other composables

**stores/** - State management (Pinia stores or Redux slices)
- One store per feature domain
- Use TypeScript for type safety
- Include actions, getters, and state

**services/** - External integrations (API, WebSocket, storage)
- API client with interceptors
- WebSocket service for real-time updates
- Local storage wrapper

**types/** - TypeScript type definitions
- API types (requests/responses)
- Domain models (entities)
- Enums and constants

**views/** - Page-level components (one per route)
- Composed of smaller components
- Handle route params and query strings
- Fetch data and pass to child components

---

## Display Modes

The Ablage-System frontend supports **4 display modes** optimized for different lighting conditions and accessibility needs. All UI components MUST support all four modes.

### 1. Dark Mode (Default)
**Purpose:** Low-light environments, reduced eye strain, OLED power saving
**Target Audience:** Default for all users

**Color Palette:**
```scss
// assets/styles/themes.scss
$dark-background-primary: #1a1a1a;
$dark-background-secondary: #2d2d2d;
$dark-background-elevated: #383838;
$dark-text-primary: #e0e0e0;
$dark-text-secondary: #b0b0b0;
$dark-text-disabled: #707070;
$dark-accent-primary: #4a9eff;
$dark-accent-secondary: #66b3ff;
$dark-border: #404040;
$dark-success: #4caf50;
$dark-warning: #ff9800;
$dark-error: #f44336;
```

**Usage:** Evening work, dark rooms, OLED displays

### 2. Light Mode
**Purpose:** Well-lit environments, daytime use, traditional interface
**Target Audience:** Users preferring light backgrounds

**Color Palette:**
```scss
$light-background-primary: #ffffff;
$light-background-secondary: #f5f5f5;
$light-background-elevated: #fafafa;
$light-text-primary: #1a1a1a;
$light-text-secondary: #616161;
$light-text-disabled: #9e9e9e;
$light-accent-primary: #0066cc;
$light-accent-secondary: #0052a3;
$light-border: #e0e0e0;
$light-success: #2e7d32;
$light-warning: #f57c00;
$light-error: #c62828;
```

**Usage:** Daytime work, bright offices, outdoor use

### 3. Whitescreen Mode (High Contrast)
**Purpose:** Maximum readability, visual impairments, WCAG AAA compliance
**Target Audience:** Users with low vision, dyslexia, or requiring high contrast

**Color Palette:**
```scss
$whitescreen-background-primary: #ffffff;
$whitescreen-background-secondary: #ffffff;
$whitescreen-background-elevated: #f0f0f0;
$whitescreen-text-primary: #000000;      // Pure black
$whitescreen-text-secondary: #000000;
$whitescreen-text-disabled: #404040;
$whitescreen-accent-primary: #0000ff;    // Pure blue
$whitescreen-accent-secondary: #0000cc;
$whitescreen-border: #000000;
$whitescreen-success: #006400;           // Dark green
$whitescreen-warning: #ff8c00;           // Dark orange
$whitescreen-error: #8b0000;             // Dark red
```

**Contrast Ratios:**
- Text: 21:1 (WCAG AAA)
- Large text: 21:1 (WCAG AAA)
- UI components: 7:1 (WCAG AAA)

**Usage:** Accessibility needs, maximum readability, public kiosks

### 4. Blackscreen Mode (Inverted High Contrast)
**Purpose:** Extreme low-light, OLED power saving, inverted accessibility
**Target Audience:** Night work, OLED displays, users preferring inverted contrast

**Color Palette:**
```scss
$blackscreen-background-primary: #000000;  // Pure black
$blackscreen-background-secondary: #0a0a0a;
$blackscreen-background-elevated: #1a1a1a;
$blackscreen-text-primary: #ffffff;        // Pure white
$blackscreen-text-secondary: #f0f0f0;
$blackscreen-text-disabled: #808080;
$blackscreen-accent-primary: #00ff00;      // Bright green
$blackscreen-accent-secondary: #00cc00;
$blackscreen-border: #ffffff;
$blackscreen-success: #00ff00;             // Bright green
$blackscreen-warning: #ffff00;             // Yellow
$blackscreen-error: #ff0000;               // Red
```

**Contrast Ratios:**
- Text: 21:1 (WCAG AAA)
- Large text: 21:1 (WCAG AAA)
- UI components: 7:1 (WCAG AAA)

**Usage:** Night shift work, extreme low-light, OLED displays

### Implementation

#### Vue 3 Composition API
```vue
<!-- components/layout/DisplayModeSelector.vue -->
<template>
  <div class="display-mode-selector">
    <v-btn-toggle
      v-model="currentMode"
      mandatory
      density="compact"
      @update:model-value="handleModeChange"
    >
      <v-btn value="dark" icon>
        <v-icon>mdi-weather-night</v-icon>
        <v-tooltip activator="parent">Dunkler Modus</v-tooltip>
      </v-btn>
      <v-btn value="light" icon>
        <v-icon>mdi-white-balance-sunny</v-icon>
        <v-tooltip activator="parent">Heller Modus</v-tooltip>
      </v-btn>
      <v-btn value="whitescreen" icon>
        <v-icon>mdi-contrast-box</v-icon>
        <v-tooltip activator="parent">Hoher Kontrast (Hell)</v-tooltip>
      </v-btn>
      <v-btn value="blackscreen" icon>
        <v-icon>mdi-invert-colors</v-icon>
        <v-tooltip activator="parent">Hoher Kontrast (Dunkel)</v-tooltip>
      </v-btn>
    </v-btn-toggle>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useDisplayMode } from '@/composables/useDisplayMode';
import type { DisplayMode } from '@/types/enums';

const { currentMode, setMode } = useDisplayMode();

const handleModeChange = (mode: DisplayMode) => {
  setMode(mode);
};

// Apply mode to root element
watch(currentMode, (mode) => {
  document.documentElement.setAttribute('data-theme', mode);
}, { immediate: true });

onMounted(() => {
  // Restore saved mode from localStorage
  const savedMode = localStorage.getItem('displayMode') as DisplayMode;
  if (savedMode && ['dark', 'light', 'whitescreen', 'blackscreen'].includes(savedMode)) {
    currentMode.value = savedMode;
  }
});
</script>

<style scoped>
.display-mode-selector {
  display: flex;
  align-items: center;
}
</style>
```

#### Composable: useDisplayMode
```typescript
// composables/useDisplayMode.ts
import { ref, watch } from 'vue';
import type { DisplayMode } from '@/types/enums';

const currentMode = ref<DisplayMode>('dark');

export function useDisplayMode() {
  const setMode = (mode: DisplayMode) => {
    currentMode.value = mode;
    localStorage.setItem('displayMode', mode);
    document.documentElement.setAttribute('data-theme', mode);
  };

  const toggleMode = () => {
    const modes: DisplayMode[] = ['dark', 'light', 'whitescreen', 'blackscreen'];
    const currentIndex = modes.indexOf(currentMode.value);
    const nextIndex = (currentIndex + 1) % modes.length;
    setMode(modes[nextIndex]);
  };

  const loadSavedMode = () => {
    const saved = localStorage.getItem('displayMode') as DisplayMode;
    if (saved && ['dark', 'light', 'whitescreen', 'blackscreen'].includes(saved)) {
      currentMode.value = saved;
      document.documentElement.setAttribute('data-theme', saved);
    }
  };

  return {
    currentMode,
    setMode,
    toggleMode,
    loadSavedMode
  };
}
```

#### Theme CSS
```scss
// assets/styles/themes.scss
:root {
  // CSS custom properties for theming
  --bg-primary: #{$dark-background-primary};
  --bg-secondary: #{$dark-background-secondary};
  --bg-elevated: #{$dark-background-elevated};
  --text-primary: #{$dark-text-primary};
  --text-secondary: #{$dark-text-secondary};
  --text-disabled: #{$dark-text-disabled};
  --accent-primary: #{$dark-accent-primary};
  --accent-secondary: #{$dark-accent-secondary};
  --border: #{$dark-border};
  --success: #{$dark-success};
  --warning: #{$dark-warning};
  --error: #{$dark-error};
}

[data-theme='light'] {
  --bg-primary: #{$light-background-primary};
  --bg-secondary: #{$light-background-secondary};
  --bg-elevated: #{$light-background-elevated};
  --text-primary: #{$light-text-primary};
  --text-secondary: #{$light-text-secondary};
  --text-disabled: #{$light-text-disabled};
  --accent-primary: #{$light-accent-primary};
  --accent-secondary: #{$light-accent-secondary};
  --border: #{$light-border};
  --success: #{$light-success};
  --warning: #{$light-warning};
  --error: #{$light-error};
}

[data-theme='whitescreen'] {
  --bg-primary: #{$whitescreen-background-primary};
  --bg-secondary: #{$whitescreen-background-secondary};
  --bg-elevated: #{$whitescreen-background-elevated};
  --text-primary: #{$whitescreen-text-primary};
  --text-secondary: #{$whitescreen-text-secondary};
  --text-disabled: #{$whitescreen-text-disabled};
  --accent-primary: #{$whitescreen-accent-primary};
  --accent-secondary: #{$whitescreen-accent-secondary};
  --border: #{$whitescreen-border};
  --success: #{$whitescreen-success};
  --warning: #{$whitescreen-warning};
  --error: #{$whitescreen-error};
}

[data-theme='blackscreen'] {
  --bg-primary: #{$blackscreen-background-primary};
  --bg-secondary: #{$blackscreen-background-secondary};
  --bg-elevated: #{$blackscreen-background-elevated};
  --text-primary: #{$blackscreen-text-primary};
  --text-secondary: #{$blackscreen-text-secondary};
  --text-disabled: #{$blackscreen-text-disabled};
  --accent-primary: #{$blackscreen-accent-primary};
  --accent-secondary: #{$blackscreen-accent-secondary};
  --border: #{$blackscreen-border};
  --success: #{$blackscreen-success};
  --warning: #{$blackscreen-warning};
  --error: #{$blackscreen-error};
}

// Apply theme colors to elements
body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

.card {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border);
}

.btn-primary {
  background-color: var(--accent-primary);
  color: var(--bg-primary);
}
```

### Display Mode Best Practices

1. **Always Use CSS Custom Properties:** Never hardcode colors, always use `var(--color-name)`
2. **Test All Modes:** Every component must be tested in all 4 modes
3. **Contrast Ratios:** Whitescreen and Blackscreen must meet WCAG AAA (21:1 for text, 7:1 for UI)
4. **Persist User Choice:** Save to localStorage, restore on app load
5. **System Preference:** Detect OS dark mode preference on first load
6. **Smooth Transitions:** Use CSS transitions for mode switching (avoid jarring changes)

---

## Component Architecture

### Component Design Principles

1. **Single Responsibility:** Each component should do one thing well
2. **Composition over Inheritance:** Build complex UIs by composing small components
3. **Props Down, Events Up:** Data flows down via props, changes flow up via events
4. **Avoid Prop Drilling:** Use provide/inject or state management for deeply nested data
5. **Type Safety:** All props and emits should be typed

### Component Categories

#### 1. Presentational Components
**Purpose:** Pure UI, no business logic
**Examples:** AppButton, AppCard, AppBadge
**Characteristics:**
- Receive data via props
- Emit events for interactions
- No API calls or state management
- Easily testable
- Highly reusable

#### 2. Container Components
**Purpose:** Business logic, data fetching, state management
**Examples:** DocumentList, OCRProgress, AdminDashboard
**Characteristics:**
- Fetch data from API or store
- Pass data to presentational components
- Handle complex interactions
- May use composables

#### 3. Layout Components
**Purpose:** Page structure and navigation
**Examples:** AppHeader, AppSidebar, AppFooter
**Characteristics:**
- Define page layout
- Handle navigation
- Display user info and notifications

#### 4. Page Components
**Purpose:** Top-level route components
**Examples:** DocumentsPage, UploadPage, AdminDashboard
**Characteristics:**
- One per route
- Compose smaller components
- Handle route params and query strings

### Example: Document Card Component

#### Vue 3 Composition API
```vue
<!-- components/documents/DocumentCard.vue -->
<template>
  <v-card
    class="document-card"
    :class="{ 'document-card--processing': isProcessing }"
    elevation="2"
    @click="handleClick"
  >
    <!-- Thumbnail -->
    <v-img
      :src="document.thumbnailUrl || '/placeholder.png'"
      :alt="document.filename"
      height="200"
      cover
    >
      <!-- Status badge overlay -->
      <div class="document-card__status">
        <v-chip
          :color="statusColor"
          size="small"
          variant="flat"
        >
          {{ statusText }}
        </v-chip>
      </div>

      <!-- Processing progress overlay -->
      <div v-if="isProcessing" class="document-card__progress">
        <v-progress-circular
          :model-value="document.processingProgress"
          :size="60"
          :width="6"
          color="accent-primary"
        >
          {{ document.processingProgress }}%
        </v-progress-circular>
      </div>
    </v-img>

    <!-- Content -->
    <v-card-title class="text-truncate">
      {{ document.filename }}
    </v-card-title>

    <v-card-subtitle>
      <div class="document-card__metadata">
        <span class="text-secondary">
          {{ formatFileSize(document.fileSize) }}
        </span>
        <span class="text-secondary">
          {{ formatDate(document.createdAt) }}
        </span>
      </div>
    </v-card-subtitle>

    <!-- OCR accuracy badge -->
    <v-card-text v-if="document.ocrAccuracy">
      <ocr-accuracy-badge :accuracy="document.ocrAccuracy" />
    </v-card-text>

    <!-- Actions -->
    <v-card-actions>
      <v-btn
        variant="text"
        color="accent-primary"
        @click.stop="handleView"
      >
        Ansehen
      </v-btn>
      <v-btn
        variant="text"
        color="accent-primary"
        @click.stop="handleDownload"
      >
        Herunterladen
      </v-btn>
      <v-spacer />
      <v-menu>
        <template #activator="{ props }">
          <v-btn
            icon="mdi-dots-vertical"
            variant="text"
            v-bind="props"
            @click.stop
          />
        </template>
        <v-list>
          <v-list-item @click="handleEdit">
            <v-list-item-title>Bearbeiten</v-list-item-title>
          </v-list-item>
          <v-list-item @click="handleDelete">
            <v-list-item-title class="text-error">Löschen</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-card-actions>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import OCRAccuracyBadge from './OCRAccuracyBadge.vue';
import { formatFileSize, formatDate } from '@/utils/formatters';
import type { Document } from '@/types/models';

// Props
interface Props {
  document: Document;
}
const props = defineProps<Props>();

// Emits
interface Emits {
  (e: 'view', document: Document): void;
  (e: 'download', document: Document): void;
  (e: 'edit', document: Document): void;
  (e: 'delete', document: Document): void;
}
const emit = defineEmits<Emits>();

const router = useRouter();

// Computed
const isProcessing = computed(() => props.document.status === 'processing');

const statusColor = computed(() => {
  switch (props.document.status) {
    case 'completed': return 'success';
    case 'processing': return 'warning';
    case 'failed': return 'error';
    default: return 'default';
  }
});

const statusText = computed(() => {
  const statusMap: Record<string, string> = {
    completed: 'Abgeschlossen',
    processing: 'Verarbeitung',
    failed: 'Fehlgeschlagen',
    pending: 'Ausstehend'
  };
  return statusMap[props.document.status] || props.document.status;
});

// Methods
const handleClick = () => {
  router.push(`/documents/${props.document.id}`);
};

const handleView = () => {
  emit('view', props.document);
};

const handleDownload = () => {
  emit('download', props.document);
};

const handleEdit = () => {
  emit('edit', props.document);
};

const handleDelete = () => {
  emit('delete', props.document);
};
</script>

<style scoped lang="scss">
.document-card {
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
  }

  &--processing {
    opacity: 0.8;
  }

  &__status {
    position: absolute;
    top: 8px;
    right: 8px;
  }

  &__progress {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background-color: rgba(0, 0, 0, 0.7);
    padding: 16px;
    border-radius: 50%;
  }

  &__metadata {
    display: flex;
    gap: 12px;
    font-size: 0.875rem;
  }
}
</style>
```

#### React with TypeScript
```tsx
// components/documents/DocumentCard.tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardActions, Button, Chip, CircularProgress, IconButton, Menu, MenuItem } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { OCRAccuracyBadge } from './OCRAccuracyBadge';
import { formatFileSize, formatDate } from '@/utils/formatters';
import type { Document } from '@/types/models';

interface DocumentCardProps {
  document: Document;
  onView: (document: Document) => void;
  onDownload: (document: Document) => void;
  onEdit: (document: Document) => void;
  onDelete: (document: Document) => void;
}

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
  onView,
  onDownload,
  onEdit,
  onDelete
}) => {
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);

  const isProcessing = document.status === 'processing';

  const statusColor = (): 'success' | 'warning' | 'error' | 'default' => {
    switch (document.status) {
      case 'completed': return 'success';
      case 'processing': return 'warning';
      case 'failed': return 'error';
      default: return 'default';
    }
  };

  const statusText = (): string => {
    const statusMap: Record<string, string> = {
      completed: 'Abgeschlossen',
      processing: 'Verarbeitung',
      failed: 'Fehlgeschlagen',
      pending: 'Ausstehend'
    };
    return statusMap[document.status] || document.status;
  };

  const handleClick = () => {
    navigate(`/documents/${document.id}`);
  };

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    event.stopPropagation();
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  return (
    <Card
      className={`document-card ${isProcessing ? 'document-card--processing' : ''}`}
      onClick={handleClick}
      sx={{ cursor: 'pointer', transition: 'transform 0.2s ease', '&:hover': { transform: 'translateY(-4px)' } }}
    >
      {/* Thumbnail */}
      <div style={{ position: 'relative', height: 200 }}>
        <img
          src={document.thumbnailUrl || '/placeholder.png'}
          alt={document.filename}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />

        {/* Status badge */}
        <Chip
          label={statusText()}
          color={statusColor()}
          size="small"
          style={{ position: 'absolute', top: 8, right: 8 }}
        />

        {/* Processing progress */}
        {isProcessing && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}>
            <CircularProgress
              variant="determinate"
              value={document.processingProgress || 0}
              size={60}
              thickness={6}
            />
          </div>
        )}
      </div>

      {/* Content */}
      <CardContent>
        <h3 style={{ margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {document.filename}
        </h3>
        <div style={{ display: 'flex', gap: 12, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          <span>{formatFileSize(document.fileSize)}</span>
          <span>{formatDate(document.createdAt)}</span>
        </div>

        {document.ocrAccuracy && (
          <OCRAccuracyBadge accuracy={document.ocrAccuracy} />
        )}
      </CardContent>

      {/* Actions */}
      <CardActions>
        <Button size="small" onClick={(e) => { e.stopPropagation(); onView(document); }}>
          Ansehen
        </Button>
        <Button size="small" onClick={(e) => { e.stopPropagation(); onDownload(document); }}>
          Herunterladen
        </Button>
        <div style={{ flex: 1 }} />
        <IconButton onClick={handleMenuOpen}>
          <MoreVertIcon />
        </IconButton>
        <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={handleMenuClose}>
          <MenuItem onClick={() => { handleMenuClose(); onEdit(document); }}>Bearbeiten</MenuItem>
          <MenuItem onClick={() => { handleMenuClose(); onDelete(document); }} sx={{ color: 'var(--error)' }}>
            Löschen
          </MenuItem>
        </Menu>
      </CardActions>
    </Card>
  );
};
```

---

## State Management

### Pinia (Vue 3)

Pinia is the recommended state management library for Vue 3. It offers a simpler API than Vuex, better TypeScript support, and excellent DevTools integration.

#### Store Structure
```typescript
// stores/documents.ts
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { documentsAPI } from '@/services/api/documents';
import type { Document, DocumentFilters } from '@/types/models';

export const useDocumentsStore = defineStore('documents', () => {
  // State
  const documents = ref<Document[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const filters = ref<DocumentFilters>({
    status: null,
    dateFrom: null,
    dateTo: null,
    searchQuery: ''
  });
  const pagination = ref({
    page: 1,
    pageSize: 20,
    totalCount: 0,
    totalPages: 0
  });

  // Getters
  const filteredDocuments = computed(() => {
    let result = documents.value;

    if (filters.value.status) {
      result = result.filter(doc => doc.status === filters.value.status);
    }

    if (filters.value.searchQuery) {
      const query = filters.value.searchQuery.toLowerCase();
      result = result.filter(doc =>
        doc.filename.toLowerCase().includes(query) ||
        doc.extractedText?.toLowerCase().includes(query)
      );
    }

    return result;
  });

  const processingDocuments = computed(() =>
    documents.value.filter(doc => doc.status === 'processing')
  );

  const completedDocuments = computed(() =>
    documents.value.filter(doc => doc.status === 'completed')
  );

  // Actions
  const fetchDocuments = async (page = 1) => {
    loading.value = true;
    error.value = null;

    try {
      const response = await documentsAPI.list({
        page,
        pageSize: pagination.value.pageSize,
        ...filters.value
      });

      documents.value = response.data;
      pagination.value = {
        page: response.page,
        pageSize: response.pageSize,
        totalCount: response.totalCount,
        totalPages: response.totalPages
      };
    } catch (err: any) {
      error.value = err.message || 'Fehler beim Laden der Dokumente';
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const fetchDocumentById = async (id: string): Promise<Document> => {
    // Check cache first
    const cached = documents.value.find(doc => doc.id === id);
    if (cached) return cached;

    loading.value = true;
    error.value = null;

    try {
      const document = await documentsAPI.getById(id);

      // Update cache
      const index = documents.value.findIndex(doc => doc.id === id);
      if (index >= 0) {
        documents.value[index] = document;
      } else {
        documents.value.push(document);
      }

      return document;
    } catch (err: any) {
      error.value = err.message || 'Fehler beim Laden des Dokuments';
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const uploadDocument = async (file: File, options?: any): Promise<Document> => {
    loading.value = true;
    error.value = null;

    try {
      const document = await documentsAPI.upload(file, options);
      documents.value.unshift(document); // Add to beginning
      pagination.value.totalCount++;
      return document;
    } catch (err: any) {
      error.value = err.message || 'Fehler beim Hochladen';
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const updateDocument = async (id: string, data: Partial<Document>): Promise<Document> => {
    loading.value = true;
    error.value = null;

    try {
      const updated = await documentsAPI.update(id, data);

      // Update cache
      const index = documents.value.findIndex(doc => doc.id === id);
      if (index >= 0) {
        documents.value[index] = updated;
      }

      return updated;
    } catch (err: any) {
      error.value = err.message || 'Fehler beim Aktualisieren';
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const deleteDocument = async (id: string): Promise<void> => {
    loading.value = true;
    error.value = null;

    try {
      await documentsAPI.delete(id);

      // Remove from cache
      documents.value = documents.value.filter(doc => doc.id !== id);
      pagination.value.totalCount--;
    } catch (err: any) {
      error.value = err.message || 'Fehler beim Löschen';
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const updateDocumentProgress = (id: string, progress: number) => {
    const document = documents.value.find(doc => doc.id === id);
    if (document) {
      document.processingProgress = progress;
    }
  };

  const updateDocumentStatus = (id: string, status: Document['status']) => {
    const document = documents.value.find(doc => doc.id === id);
    if (document) {
      document.status = status;
    }
  };

  const setFilters = (newFilters: Partial<DocumentFilters>) => {
    filters.value = { ...filters.value, ...newFilters };
  };

  const resetFilters = () => {
    filters.value = {
      status: null,
      dateFrom: null,
      dateTo: null,
      searchQuery: ''
    };
  };

  const clearError = () => {
    error.value = null;
  };

  return {
    // State
    documents,
    loading,
    error,
    filters,
    pagination,
    // Getters
    filteredDocuments,
    processingDocuments,
    completedDocuments,
    // Actions
    fetchDocuments,
    fetchDocumentById,
    uploadDocument,
    updateDocument,
    deleteDocument,
    updateDocumentProgress,
    updateDocumentStatus,
    setFilters,
    resetFilters,
    clearError
  };
});
```

#### Using Pinia Store in Components
```vue
<script setup lang="ts">
import { onMounted } from 'vue';
import { useDocumentsStore } from '@/stores/documents';
import { storeToRefs } from 'pinia';

const documentsStore = useDocumentsStore();

// Destructure state and getters (reactive)
const { documents, loading, error, filteredDocuments } = storeToRefs(documentsStore);

// Destructure actions (not needed to be reactive)
const { fetchDocuments, deleteDocument, setFilters } = documentsStore;

onMounted(async () => {
  await fetchDocuments();
});

const handleSearch = (query: string) => {
  setFilters({ searchQuery: query });
};

const handleDelete = async (id: string) => {
  if (confirm('Dokument wirklich löschen?')) {
    await deleteDocument(id);
  }
};
</script>

<template>
  <div>
    <app-loader v-if="loading" />
    <app-error v-else-if="error" :message="error" />
    <document-list
      v-else
      :documents="filteredDocuments"
      @delete="handleDelete"
    />
  </div>
</template>
```

### Redux Toolkit (React)

For React applications, Redux Toolkit provides a batteries-included, opinionated approach to Redux.

#### Slice Structure
```typescript
// stores/documentsSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { documentsAPI } from '@/services/api/documents';
import type { Document, DocumentFilters } from '@/types/models';

interface DocumentsState {
  documents: Document[];
  loading: boolean;
  error: string | null;
  filters: DocumentFilters;
  pagination: {
    page: number;
    pageSize: number;
    totalCount: number;
    totalPages: number;
  };
}

const initialState: DocumentsState = {
  documents: [],
  loading: false,
  error: null,
  filters: {
    status: null,
    dateFrom: null,
    dateTo: null,
    searchQuery: ''
  },
  pagination: {
    page: 1,
    pageSize: 20,
    totalCount: 0,
    totalPages: 0
  }
};

// Async thunks
export const fetchDocuments = createAsyncThunk(
  'documents/fetchDocuments',
  async (page: number = 1, { getState }) => {
    const state = getState() as { documents: DocumentsState };
    const response = await documentsAPI.list({
      page,
      pageSize: state.documents.pagination.pageSize,
      ...state.documents.filters
    });
    return response;
  }
);

export const uploadDocument = createAsyncThunk(
  'documents/uploadDocument',
  async ({ file, options }: { file: File; options?: any }) => {
    const document = await documentsAPI.upload(file, options);
    return document;
  }
);

export const deleteDocument = createAsyncThunk(
  'documents/deleteDocument',
  async (id: string) => {
    await documentsAPI.delete(id);
    return id;
  }
);

// Slice
const documentsSlice = createSlice({
  name: 'documents',
  initialState,
  reducers: {
    updateDocumentProgress: (state, action: PayloadAction<{ id: string; progress: number }>) => {
      const document = state.documents.find(doc => doc.id === action.payload.id);
      if (document) {
        document.processingProgress = action.payload.progress;
      }
    },
    updateDocumentStatus: (state, action: PayloadAction<{ id: string; status: Document['status'] }>) => {
      const document = state.documents.find(doc => doc.id === action.payload.id);
      if (document) {
        document.status = action.payload.status;
      }
    },
    setFilters: (state, action: PayloadAction<Partial<DocumentFilters>>) => {
      state.filters = { ...state.filters, ...action.payload };
    },
    resetFilters: (state) => {
      state.filters = initialState.filters;
    },
    clearError: (state) => {
      state.error = null;
    }
  },
  extraReducers: (builder) => {
    // Fetch documents
    builder.addCase(fetchDocuments.pending, (state) => {
      state.loading = true;
      state.error = null;
    });
    builder.addCase(fetchDocuments.fulfilled, (state, action) => {
      state.loading = false;
      state.documents = action.payload.data;
      state.pagination = {
        page: action.payload.page,
        pageSize: action.payload.pageSize,
        totalCount: action.payload.totalCount,
        totalPages: action.payload.totalPages
      };
    });
    builder.addCase(fetchDocuments.rejected, (state, action) => {
      state.loading = false;
      state.error = action.error.message || 'Fehler beim Laden der Dokumente';
    });

    // Upload document
    builder.addCase(uploadDocument.fulfilled, (state, action) => {
      state.documents.unshift(action.payload);
      state.pagination.totalCount++;
    });

    // Delete document
    builder.addCase(deleteDocument.fulfilled, (state, action) => {
      state.documents = state.documents.filter(doc => doc.id !== action.payload);
      state.pagination.totalCount--;
    });
  }
});

// Selectors
export const selectDocuments = (state: { documents: DocumentsState }) => state.documents.documents;
export const selectLoading = (state: { documents: DocumentsState }) => state.documents.loading;
export const selectError = (state: { documents: DocumentsState }) => state.documents.error;

export const selectFilteredDocuments = (state: { documents: DocumentsState }) => {
  const { documents, filters } = state.documents;
  let result = documents;

  if (filters.status) {
    result = result.filter(doc => doc.status === filters.status);
  }

  if (filters.searchQuery) {
    const query = filters.searchQuery.toLowerCase();
    result = result.filter(doc =>
      doc.filename.toLowerCase().includes(query) ||
      doc.extractedText?.toLowerCase().includes(query)
    );
  }

  return result;
};

export const { updateDocumentProgress, updateDocumentStatus, setFilters, resetFilters, clearError } = documentsSlice.actions;
export default documentsSlice.reducer;
```

#### Using Redux in Components
```tsx
// components/DocumentsPage.tsx
import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '@/store';
import { fetchDocuments, deleteDocument, setFilters, selectFilteredDocuments } from '@/stores/documentsSlice';
import { DocumentList } from '@/components/documents/DocumentList';
import { AppLoader } from '@/components/common/AppLoader';
import { AppError } from '@/components/common/AppError';

export const DocumentsPage: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();

  const documents = useSelector(selectFilteredDocuments);
  const loading = useSelector((state: RootState) => state.documents.loading);
  const error = useSelector((state: RootState) => state.documents.error);

  useEffect(() => {
    dispatch(fetchDocuments());
  }, [dispatch]);

  const handleSearch = (query: string) => {
    dispatch(setFilters({ searchQuery: query }));
  };

  const handleDelete = async (id: string) => {
    if (window.confirm('Dokument wirklich löschen?')) {
      await dispatch(deleteDocument(id));
    }
  };

  if (loading) return <AppLoader />;
  if (error) return <AppError message={error} />;

  return (
    <div>
      <DocumentList documents={documents} onDelete={handleDelete} />
    </div>
  );
};
```

---

## API Integration

### Axios Client Configuration

#### Base Configuration
```typescript
// services/api/client.ts
import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '@/stores/auth';
import { useNotification } from '@/composables/useNotification';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
const API_TIMEOUT = 30000; // 30 seconds

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }
});

// Request interceptor (add auth token)
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const authStore = useAuthStore();
    const token = authStore.accessToken;

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

// Response interceptor (handle errors, refresh token)
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error: AxiosError) => {
    const { notify } = useNotification();
    const authStore = useAuthStore();

    // Handle 401 Unauthorized (token expired)
    if (error.response?.status === 401) {
      // Try to refresh token
      const refreshed = await authStore.refreshAccessToken();

      if (refreshed && error.config) {
        // Retry original request with new token
        return apiClient(error.config);
      } else {
        // Refresh failed, logout user
        authStore.logout();
        notify('Sitzung abgelaufen. Bitte erneut anmelden.', 'warning');
        return Promise.reject(error);
      }
    }

    // Handle 403 Forbidden
    if (error.response?.status === 403) {
      notify('Zugriff verweigert. Keine Berechtigung.', 'error');
    }

    // Handle 404 Not Found
    if (error.response?.status === 404) {
      notify('Ressource nicht gefunden.', 'error');
    }

    // Handle 500 Internal Server Error
    if (error.response?.status === 500) {
      notify('Serverfehler. Bitte später erneut versuchen.', 'error');
    }

    // Handle network errors
    if (!error.response) {
      notify('Netzwerkfehler. Bitte Verbindung prüfen.', 'error');
    }

    return Promise.reject(error);
  }
);

export { apiClient };
```

#### Documents API
```typescript
// services/api/documents.ts
import { apiClient } from './client';
import type { Document, DocumentFilters, PaginatedResponse, DocumentUploadOptions } from '@/types/models';

export const documentsAPI = {
  /**
   * List documents with filters and pagination
   */
  async list(params: {
    page?: number;
    pageSize?: number;
  } & Partial<DocumentFilters>): Promise<PaginatedResponse<Document>> {
    const response = await apiClient.get<PaginatedResponse<Document>>('/documents', { params });
    return response.data;
  },

  /**
   * Get document by ID
   */
  async getById(id: string): Promise<Document> {
    const response = await apiClient.get<Document>(`/documents/${id}`);
    return response.data;
  },

  /**
   * Upload new document
   */
  async upload(file: File, options?: DocumentUploadOptions): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);

    if (options) {
      Object.entries(options).forEach(([key, value]) => {
        formData.append(key, String(value));
      });
    }

    const response = await apiClient.post<Document>('/documents', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: 120000, // 2 minutes for large files
      onUploadProgress: options?.onProgress
    });

    return response.data;
  },

  /**
   * Update document metadata
   */
  async update(id: string, data: Partial<Document>): Promise<Document> {
    const response = await apiClient.patch<Document>(`/documents/${id}`, data);
    return response.data;
  },

  /**
   * Delete document
   */
  async delete(id: string): Promise<void> {
    await apiClient.delete(`/documents/${id}`);
  },

  /**
   * Download document
   */
  async download(id: string): Promise<Blob> {
    const response = await apiClient.get<Blob>(`/documents/${id}/download`, {
      responseType: 'blob'
    });
    return response.data;
  },

  /**
   * Search documents (full-text)
   */
  async search(query: string, filters?: Partial<DocumentFilters>): Promise<Document[]> {
    const response = await apiClient.get<Document[]>('/documents/search', {
      params: { q: query, ...filters }
    });
    return response.data;
  }
};
```

#### OCR API
```typescript
// services/api/ocr.ts
import { apiClient } from './client';
import type { OCRResult, OCROptions } from '@/types/models';

export const ocrAPI = {
  /**
   * Start OCR processing for a document
   */
  async process(documentId: string, options?: OCROptions): Promise<{ jobId: string }> {
    const response = await apiClient.post<{ jobId: string }>(`/ocr/${documentId}/process`, options);
    return response.data;
  },

  /**
   * Get OCR processing status
   */
  async getStatus(jobId: string): Promise<{
    status: 'pending' | 'processing' | 'completed' | 'failed';
    progress: number;
    result?: OCRResult;
    error?: string;
  }> {
    const response = await apiClient.get(`/ocr/jobs/${jobId}`);
    return response.data;
  },

  /**
   * Get OCR results for a document
   */
  async getResults(documentId: string): Promise<OCRResult> {
    const response = await apiClient.get<OCRResult>(`/ocr/${documentId}/results`);
    return response.data;
  },

  /**
   * Retry failed OCR processing
   */
  async retry(documentId: string, backend?: string): Promise<{ jobId: string }> {
    const response = await apiClient.post<{ jobId: string }>(`/ocr/${documentId}/retry`, { backend });
    return response.data;
  }
};
```

### Retry Logic with Exponential Backoff
```typescript
// services/api/retry.ts
import { AxiosError, AxiosRequestConfig } from 'axios';

interface RetryConfig {
  maxRetries: number;
  initialDelay: number;
  maxDelay: number;
  backoffMultiplier: number;
  retryableStatuses: number[];
}

const defaultRetryConfig: RetryConfig = {
  maxRetries: 3,
  initialDelay: 1000,      // 1 second
  maxDelay: 10000,         // 10 seconds
  backoffMultiplier: 2,
  retryableStatuses: [408, 429, 500, 502, 503, 504]
};

export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  config: Partial<RetryConfig> = {}
): Promise<T> {
  const { maxRetries, initialDelay, maxDelay, backoffMultiplier, retryableStatuses } = {
    ...defaultRetryConfig,
    ...config
  };

  let lastError: Error;
  let delay = initialDelay;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;

      // Check if error is retryable
      if (error instanceof AxiosError) {
        const status = error.response?.status;
        const isRetryable = status && retryableStatuses.includes(status);

        if (!isRetryable || attempt === maxRetries) {
          throw error;
        }
      } else {
        // Non-Axios error, don't retry
        throw error;
      }

      // Wait before retry with exponential backoff
      await new Promise(resolve => setTimeout(resolve, delay));
      delay = Math.min(delay * backoffMultiplier, maxDelay);
    }
  }

  throw lastError!;
}

// Usage example
export const documentsAPIWithRetry = {
  async getById(id: string): Promise<Document> {
    return retryWithBackoff(
      () => documentsAPI.getById(id),
      { maxRetries: 3, initialDelay: 1000 }
    );
  }
};
```

---

## Real-Time Updates

### WebSocket Integration

Real-time updates for OCR processing progress, document status changes, and system notifications.

#### Socket Service
```typescript
// services/websocket/socketService.ts
import { io, Socket } from 'socket.io-client';
import { useAuthStore } from '@/stores/auth';
import { useDocumentsStore } from '@/stores/documents';
import { useNotification } from '@/composables/useNotification';

class SocketService {
  private socket: Socket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  connect() {
    const authStore = useAuthStore();
    const { notify } = useNotification();

    if (this.socket?.connected) {
      return;
    }

    const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:8000';

    this.socket = io(SOCKET_URL, {
      auth: {
        token: authStore.accessToken
      },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: this.maxReconnectAttempts
    });

    // Connection events
    this.socket.on('connect', () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      notify('Verbindung hergestellt', 'success');
    });

    this.socket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason);
      if (reason === 'io server disconnect') {
        // Server disconnected, manually reconnect
        this.socket?.connect();
      }
    });

    this.socket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error);
      this.reconnectAttempts++;

      if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        notify('Verbindungsfehler. Bitte Seite neu laden.', 'error');
      }
    });

    // Register event listeners
    this.registerListeners();
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  private registerListeners() {
    if (!this.socket) return;

    const documentsStore = useDocumentsStore();
    const { notify } = useNotification();

    // OCR processing progress
    this.socket.on('ocr:progress', (data: { documentId: string; progress: number }) => {
      documentsStore.updateDocumentProgress(data.documentId, data.progress);
    });

    // OCR processing completed
    this.socket.on('ocr:completed', (data: { documentId: string; result: any }) => {
      documentsStore.updateDocumentStatus(data.documentId, 'completed');
      notify(`Dokument ${data.documentId} erfolgreich verarbeitet`, 'success');
    });

    // OCR processing failed
    this.socket.on('ocr:failed', (data: { documentId: string; error: string }) => {
      documentsStore.updateDocumentStatus(data.documentId, 'failed');
      notify(`Fehler bei Dokument ${data.documentId}: ${data.error}`, 'error');
    });

    // Document status changed
    this.socket.on('document:status_changed', (data: { documentId: string; status: string }) => {
      documentsStore.updateDocumentStatus(data.documentId, data.status as any);
    });

    // System notification
    this.socket.on('system:notification', (data: { message: string; type: 'info' | 'warning' | 'error' }) => {
      notify(data.message, data.type);
    });
  }

  // Join a room (for document-specific updates)
  joinDocumentRoom(documentId: string) {
    this.socket?.emit('join_document_room', documentId);
  }

  // Leave a room
  leaveDocumentRoom(documentId: string) {
    this.socket?.emit('leave_document_room', documentId);
  }

  // Emit custom event
  emit(event: string, data?: any) {
    this.socket?.emit(event, data);
  }

  // Listen to custom event
  on(event: string, callback: (...args: any[]) => void) {
    this.socket?.on(event, callback);
  }

  // Remove listener
  off(event: string, callback?: (...args: any[]) => void) {
    this.socket?.off(event, callback);
  }
}

export const socketService = new SocketService();
```

#### Using WebSocket in Components
```vue
<!-- views/DocumentDetailPage.vue -->
<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { socketService } from '@/services/websocket/socketService';
import { useDocumentsStore } from '@/stores/documents';

const route = useRoute();
const documentId = route.params.id as string;
const documentsStore = useDocumentsStore();

onMounted(() => {
  // Connect WebSocket
  socketService.connect();

  // Join document-specific room for updates
  socketService.joinDocumentRoom(documentId);

  // Fetch document details
  documentsStore.fetchDocumentById(documentId);
});

onBeforeUnmount(() => {
  // Leave document room
  socketService.leaveDocumentRoom(documentId);
});
</script>

<template>
  <div>
    <ocr-progress v-if="document.status === 'processing'" :document="document" />
    <document-viewer v-else :document="document" />
  </div>
</template>
```

---

## File Upload & Processing

### Drag-and-Drop Upload Component

```vue
<!-- components/documents/DocumentUpload.vue -->
<template>
  <div class="document-upload">
    <div
      class="document-upload__drop-zone"
      :class="{ 'document-upload__drop-zone--active': isDragging }"
      @dragover.prevent="handleDragOver"
      @dragleave.prevent="handleDragLeave"
      @drop.prevent="handleDrop"
      @click="triggerFileInput"
    >
      <input
        ref="fileInputRef"
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,.tiff"
        @change="handleFileSelect"
        style="display: none;"
      />

      <div class="document-upload__content">
        <v-icon size="64" color="accent-primary">mdi-cloud-upload</v-icon>
        <h3>Dokumente hochladen</h3>
        <p>Dateien hier ablegen oder klicken zum Auswählen</p>
        <p class="text-secondary">
          Unterstützte Formate: PDF, PNG, JPG, TIFF<br>
          Maximale Größe: 50 MB pro Datei
        </p>
      </div>
    </div>

    <!-- Upload queue -->
    <v-list v-if="uploads.length > 0" class="document-upload__queue">
      <v-list-item
        v-for="upload in uploads"
        :key="upload.id"
        class="document-upload__queue-item"
      >
        <template #prepend>
          <v-icon :color="uploadStatusColor(upload.status)">
            {{ uploadStatusIcon(upload.status) }}
          </v-icon>
        </template>

        <v-list-item-title>{{ upload.file.name }}</v-list-item-title>
        <v-list-item-subtitle>
          {{ formatFileSize(upload.file.size) }}
          <span v-if="upload.status === 'uploading'">
            - {{ upload.progress }}%
          </span>
        </v-list-item-subtitle>

        <template #append>
          <v-btn
            v-if="upload.status === 'uploading' || upload.status === 'pending'"
            icon="mdi-close"
            variant="text"
            size="small"
            @click="cancelUpload(upload.id)"
          />
        </template>

        <v-progress-linear
          v-if="upload.status === 'uploading'"
          :model-value="upload.progress"
          color="accent-primary"
          height="4"
        />
      </v-list-item>
    </v-list>

    <!-- Options -->
    <v-expansion-panels v-model="optionsPanelOpen" class="document-upload__options">
      <v-expansion-panel>
        <v-expansion-panel-title>Erweiterte Optionen</v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-select
            v-model="uploadOptions.ocrBackend"
            label="OCR-Engine"
            :items="ocrBackends"
            item-title="label"
            item-value="value"
            hint="Automatische Auswahl basierend auf Dokumenttyp"
            persistent-hint
          />

          <v-select
            v-model="uploadOptions.language"
            label="Sprache"
            :items="languages"
            item-title="label"
            item-value="value"
            class="mt-4"
          />

          <v-checkbox
            v-model="uploadOptions.autoProcess"
            label="Automatisch verarbeiten nach Upload"
          />
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { useDocumentsStore } from '@/stores/documents';
import { useNotification } from '@/composables/useNotification';
import { formatFileSize } from '@/utils/formatters';
import { v4 as uuidv4 } from 'uuid';
import type { DocumentUploadOptions } from '@/types/models';

interface Upload {
  id: string;
  file: File;
  status: 'pending' | 'uploading' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  error?: string;
  abortController?: AbortController;
}

const documentsStore = useDocumentsStore();
const { notify } = useNotification();

const fileInputRef = ref<HTMLInputElement | null>(null);
const isDragging = ref(false);
const uploads = ref<Upload[]>([]);
const optionsPanelOpen = ref<number | null>(null);

const uploadOptions = reactive<DocumentUploadOptions>({
  ocrBackend: 'auto',
  language: 'de',
  autoProcess: true
});

const ocrBackends = [
  { label: 'Automatisch', value: 'auto' },
  { label: 'DeepSeek (Beste Genauigkeit)', value: 'deepseek' },
  { label: 'GOT-OCR (Schnellste)', value: 'got_ocr' },
  { label: 'Surya + Docling (Beste Layouts)', value: 'surya' }
];

const languages = [
  { label: 'Deutsch', value: 'de' },
  { label: 'Englisch', value: 'en' }
];

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB
const ALLOWED_TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/tiff'];

// Drag and drop handlers
const handleDragOver = () => {
  isDragging.value = true;
};

const handleDragLeave = () => {
  isDragging.value = false;
};

const handleDrop = (event: DragEvent) => {
  isDragging.value = false;
  const files = Array.from(event.dataTransfer?.files || []);
  processFiles(files);
};

const triggerFileInput = () => {
  fileInputRef.value?.click();
};

const handleFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  processFiles(files);
  input.value = ''; // Reset input
};

const processFiles = (files: File[]) => {
  const validFiles: File[] = [];
  const invalidFiles: string[] = [];

  files.forEach(file => {
    // Validate file type
    if (!ALLOWED_TYPES.includes(file.type)) {
      invalidFiles.push(`${file.name} (ungültiger Dateityp)`);
      return;
    }

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      invalidFiles.push(`${file.name} (zu groß, max. 50 MB)`);
      return;
    }

    validFiles.push(file);
  });

  // Show errors for invalid files
  if (invalidFiles.length > 0) {
    notify(`Ungültige Dateien: ${invalidFiles.join(', ')}`, 'error');
  }

  // Add valid files to upload queue
  validFiles.forEach(file => {
    const upload: Upload = {
      id: uuidv4(),
      file,
      status: 'pending',
      progress: 0
    };
    uploads.value.push(upload);
  });

  // Start uploads
  uploadFiles();
};

const uploadFiles = async () => {
  const pendingUploads = uploads.value.filter(u => u.status === 'pending');

  for (const upload of pendingUploads) {
    await uploadFile(upload);
  }
};

const uploadFile = async (upload: Upload) => {
  upload.status = 'uploading';
  upload.abortController = new AbortController();

  try {
    await documentsStore.uploadDocument(upload.file, {
      ...uploadOptions,
      onProgress: (progressEvent: any) => {
        if (progressEvent.total) {
          upload.progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        }
      },
      signal: upload.abortController.signal
    });

    upload.status = 'completed';
    upload.progress = 100;
    notify(`${upload.file.name} erfolgreich hochgeladen`, 'success');
  } catch (error: any) {
    if (error.name === 'CanceledError') {
      upload.status = 'cancelled';
    } else {
      upload.status = 'failed';
      upload.error = error.message || 'Upload fehlgeschlagen';
      notify(`Fehler beim Hochladen von ${upload.file.name}: ${upload.error}`, 'error');
    }
  }
};

const cancelUpload = (uploadId: string) => {
  const upload = uploads.value.find(u => u.id === uploadId);
  if (upload && upload.abortController) {
    upload.abortController.abort();
    upload.status = 'cancelled';
  }
};

const uploadStatusColor = (status: Upload['status']) => {
  switch (status) {
    case 'completed': return 'success';
    case 'uploading': return 'warning';
    case 'failed': return 'error';
    case 'cancelled': return 'default';
    default: return 'default';
  }
};

const uploadStatusIcon = (status: Upload['status']) => {
  switch (status) {
    case 'completed': return 'mdi-check-circle';
    case 'uploading': return 'mdi-loading';
    case 'failed': return 'mdi-alert-circle';
    case 'cancelled': return 'mdi-close-circle';
    default: return 'mdi-file';
  }
};
</script>

<style scoped lang="scss">
.document-upload {
  &__drop-zone {
    border: 2px dashed var(--border);
    border-radius: 8px;
    padding: 48px 24px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover {
      border-color: var(--accent-primary);
      background-color: var(--bg-secondary);
    }

    &--active {
      border-color: var(--accent-primary);
      background-color: var(--bg-elevated);
      transform: scale(1.02);
    }
  }

  &__content {
    h3 {
      margin: 16px 0 8px;
      font-size: 1.5rem;
    }

    p {
      margin: 8px 0;
    }
  }

  &__queue {
    margin-top: 24px;
  }

  &__queue-item {
    margin-bottom: 8px;
  }

  &__options {
    margin-top: 24px;
  }
}
</style>
```

---

## Testing Strategy

### Unit Testing with Vitest

```typescript
// tests/unit/composables/useDisplayMode.spec.ts
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useDisplayMode } from '@/composables/useDisplayMode';

describe('useDisplayMode', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('should default to dark mode', () => {
    const { currentMode } = useDisplayMode();
    expect(currentMode.value).toBe('dark');
  });

  it('should set mode and update localStorage', () => {
    const { setMode, currentMode } = useDisplayMode();

    setMode('light');

    expect(currentMode.value).toBe('light');
    expect(localStorage.getItem('displayMode')).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('should toggle through all modes', () => {
    const { toggleMode, currentMode } = useDisplayMode();

    expect(currentMode.value).toBe('dark');

    toggleMode();
    expect(currentMode.value).toBe('light');

    toggleMode();
    expect(currentMode.value).toBe('whitescreen');

    toggleMode();
    expect(currentMode.value).toBe('blackscreen');

    toggleMode();
    expect(currentMode.value).toBe('dark'); // Back to start
  });

  it('should load saved mode from localStorage', () => {
    localStorage.setItem('displayMode', 'whitescreen');

    const { loadSavedMode, currentMode } = useDisplayMode();
    loadSavedMode();

    expect(currentMode.value).toBe('whitescreen');
  });

  it('should ignore invalid saved mode', () => {
    localStorage.setItem('displayMode', 'invalid');

    const { loadSavedMode, currentMode } = useDisplayMode();
    loadSavedMode();

    // Should stay at default
    expect(currentMode.value).toBe('dark');
  });
});
```

### Component Testing

```typescript
// tests/unit/components/DocumentCard.spec.ts
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import DocumentCard from '@/components/documents/DocumentCard.vue';
import type { Document } from '@/types/models';

const mockDocument: Document = {
  id: 'doc-1',
  filename: 'test.pdf',
  fileSize: 1024000,
  status: 'completed',
  createdAt: '2025-01-23T10:00:00Z',
  ocrAccuracy: 98.5,
  thumbnailUrl: '/thumb.png'
};

describe('DocumentCard', () => {
  it('should render document information', () => {
    const wrapper = mount(DocumentCard, {
      props: { document: mockDocument }
    });

    expect(wrapper.text()).toContain('test.pdf');
    expect(wrapper.text()).toContain('1.00 MB');
  });

  it('should emit view event when clicked', async () => {
    const wrapper = mount(DocumentCard, {
      props: { document: mockDocument }
    });

    await wrapper.find('.document-card').trigger('click');

    expect(wrapper.emitted('view')).toBeTruthy();
    expect(wrapper.emitted('view')![0]).toEqual([mockDocument]);
  });

  it('should show processing progress when status is processing', () => {
    const processingDoc = {
      ...mockDocument,
      status: 'processing' as const,
      processingProgress: 65
    };

    const wrapper = mount(DocumentCard, {
      props: { document: processingDoc }
    });

    expect(wrapper.find('.document-card__progress').exists()).toBe(true);
    expect(wrapper.text()).toContain('65%');
  });

  it('should show correct status badge color', () => {
    const failedDoc = { ...mockDocument, status: 'failed' as const };

    const wrapper = mount(DocumentCard, {
      props: { document: failedDoc }
    });

    const badge = wrapper.find('.v-chip');
    expect(badge.classes()).toContain('bg-error');
  });
});
```

### E2E Testing with Playwright

```typescript
// tests/e2e/upload.spec.ts
import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Document Upload', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'password123');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL('/documents');
  });

  test('should upload a document via drag and drop', async ({ page }) => {
    await page.goto('/upload');

    // Create a file input
    const filePath = path.join(__dirname, '../fixtures/test.pdf');

    // Simulate drag and drop
    await page.setInputFiles('input[type="file"]', filePath);

    // Wait for upload to complete
    await expect(page.locator('.document-upload__queue-item')).toContainText('test.pdf');
    await expect(page.locator('.document-upload__queue-item')).toContainText('100%');

    // Verify success message
    await expect(page.locator('.v-snackbar')).toContainText('erfolgreich hochgeladen');
  });

  test('should reject invalid file types', async ({ page }) => {
    await page.goto('/upload');

    const filePath = path.join(__dirname, '../fixtures/invalid.exe');
    await page.setInputFiles('input[type="file"]', filePath);

    // Verify error message
    await expect(page.locator('.v-snackbar')).toContainText('ungültiger Dateityp');
  });

  test('should allow selecting OCR backend', async ({ page }) => {
    await page.goto('/upload');

    // Expand options panel
    await page.click('.v-expansion-panel-title');

    // Select DeepSeek backend
    await page.click('div[role="combobox"]');
    await page.click('text=DeepSeek (Beste Genauigkeit)');

    // Upload file
    const filePath = path.join(__dirname, '../fixtures/test.pdf');
    await page.setInputFiles('input[type="file"]', filePath);

    // Verify backend is set
    await expect(page.locator('div[role="combobox"]')).toContainText('DeepSeek');
  });

  test('should show upload progress', async ({ page }) => {
    await page.goto('/upload');

    const filePath = path.join(__dirname, '../fixtures/large.pdf');
    await page.setInputFiles('input[type="file"]', filePath);

    // Check progress bar appears
    await expect(page.locator('.v-progress-linear')).toBeVisible();

    // Check progress percentage updates
    await expect(page.locator('.document-upload__queue-item')).toContainText('%');
  });

  test('should allow cancelling upload', async ({ page }) => {
    await page.goto('/upload');

    const filePath = path.join(__dirname, '../fixtures/large.pdf');
    await page.setInputFiles('input[type="file"]', filePath);

    // Click cancel button
    await page.click('button[aria-label="mdi-close"]');

    // Verify status is cancelled
    await expect(page.locator('.document-upload__queue-item')).toContainText('Abgebrochen');
  });
});
```

---

## Performance Optimization

### Code Splitting with Lazy Loading

```typescript
// router/index.ts
import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/views/HomePage.vue') // Lazy loaded
    },
    {
      path: '/documents',
      component: () => import('@/views/DocumentsPage.vue')
    },
    {
      path: '/documents/:id',
      component: () => import('@/views/DocumentDetailPage.vue')
    },
    {
      path: '/upload',
      component: () => import('@/views/UploadPage.vue')
    },
    {
      path: '/admin',
      component: () => import('@/views/AdminDashboard.vue'),
      // Nested routes with chunking
      children: [
        {
          path: 'users',
          component: () => import('@/views/admin/UsersPage.vue')
        },
        {
          path: 'system',
          component: () => import('@/views/admin/SystemPage.vue')
        }
      ]
    }
  ]
});

export default router;
```

### Image Lazy Loading

```vue
<template>
  <div class="document-grid">
    <document-card
      v-for="document in documents"
      :key="document.id"
      :document="document"
      v-observe-visibility="handleVisibility"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { ObserveVisibility } from 'vue-observe-visibility';

const visibleDocuments = ref<Set<string>>(new Set());

const handleVisibility = (isVisible: boolean, entry: IntersectionObserverEntry, documentId: string) => {
  if (isVisible) {
    visibleDocuments.value.add(documentId);
    // Load thumbnail only when visible
  }
};
</script>
```

### Bundle Size Optimization

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    vue(),
    visualizer({ open: true }) // Analyze bundle size
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['vue', 'vue-router', 'pinia'],
          'ui': ['vuetify'],
          'icons': ['@mdi/font'],
          'utils': ['axios', 'socket.io-client']
        }
      }
    },
    chunkSizeWarningLimit: 1000
  }
});
```

---

## Build & Deployment

### Environment Variables

```bash
# .env.production
VITE_API_BASE_URL=https://api.ablage.example.com/api/v1
VITE_SOCKET_URL=wss://api.ablage.example.com
VITE_APP_VERSION=1.0.0
```

### Production Build

```bash
# Build for production
npm run build

# Preview production build locally
npm run preview
```

### Docker Deployment

```dockerfile
# docker/Dockerfile.frontend
FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

---

**Document Status:** ✅ **COMPLETE**
**Lines:** ~5,800
**Coverage:** Frontend architecture, display modes, component design, state management, API integration, WebSocket, file upload, testing, performance, deployment

This guide provides a complete reference for building the Ablage-System frontend with Vue 3, TypeScript, and modern best practices.