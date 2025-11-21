Frontend Design System
Ablage-System – Intelligent Document Processing

World-Class IDP Frontend
Notion/Figma-Level · Dark/Light Mode · GPU-Accelerated OCR · German-First


🎯 Design Vision
Feinpoliert & Durchdacht (Polished & Thoughtful)

Enterprise-grade from day one - no MVP compromises
Notion-level workspace management and real-time collaboration
Figma-level canvas manipulation for document annotation
Production-ready components with accessibility built-in
Performance-obsessed - 60 FPS animations, <200ms response times

German-First Philosophy

Primary locale: de-DE with professional terminology
Optimized layouts for German text length (15-20% longer than English)
Cultural considerations: formal communication, data privacy emphasis
Date formats: DD.MM.YYYY, 24h time
Number formats: 1.234,56 EUR (comma decimal separator)
Umlaut support: ä, ö, ü, ß properly rendered in all fonts


🎨 Design Token System
Color Palette (HSL for Dynamic Theming)
css:root {
  /* ===== LIGHT MODE ===== */
  
  /* Base Colors */
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --card: 0 0% 100%;
  --card-foreground: 222.2 84% 4.9%;
  --popover: 0 0% 100%;
  --popover-foreground: 222.2 84% 4.9%;
  
  /* Brand Colors */
  --primary: 221.2 83.2% 53.3%;
  --primary-foreground: 210 40% 98%;
  --secondary: 210 40% 96.1%;
  --secondary-foreground: 222.2 47.4% 11.2%;
  --muted: 210 40% 96.1%;
  --muted-foreground: 215.4 16.3% 46.9%;
  --accent: 210 40% 96.1%;
  --accent-foreground: 222.2 47.4% 11.2%;
  
  /* Semantic Colors */
  --destructive: 0 84.2% 60.2%;
  --destructive-foreground: 210 40% 98%;
  --success: 142 76% 36%;
  --success-foreground: 210 40% 98%;
  --warning: 48 96% 53%;
  --warning-foreground: 222.2 47.4% 11.2%;
  --info: 199 89% 48%;
  --info-foreground: 210 40% 98%;
  
  /* OCR-Specific Colors */
  --confidence-high: 142 76% 36%;        /* 90-100% confidence */
  --confidence-medium: 48 96% 53%;       /* 70-89% confidence */
  --confidence-low: 0 84% 60%;           /* 0-69% confidence */
  --processing: 217 91% 60%;             /* Processing state */
  
  /* Backend Colors */
  --backend-deepseek: 271 81% 56%;       /* Purple - DeepSeek */
  --backend-got: 142 71% 45%;            /* Green - GOT-OCR */
  --backend-surya: 217 91% 60%;          /* Blue - Surya */
  
  /* UI Elements */
  --border: 214.3 31.8% 91.4%;
  --input: 214.3 31.8% 91.4%;
  --ring: 221.2 83.2% 53.3%;
  --radius: 0.5rem;
}

.dark {
  /* ===== DARK MODE ===== */
  
  /* Base Colors */
  --background: 222.2 84% 4.9%;
  --foreground: 210 40% 98%;
  --card: 222.2 84% 4.9%;
  --card-foreground: 210 40% 98%;
  --popover: 222.2 84% 4.9%;
  --popover-foreground: 210 40% 98%;
  
  /* Brand Colors */
  --primary: 217.2 91.2% 59.8%;
  --primary-foreground: 222.2 47.4% 11.2%;
  --secondary: 217.2 32.6% 17.5%;
  --secondary-foreground: 210 40% 98%;
  --muted: 217.2 32.6% 17.5%;
  --muted-foreground: 215 20.2% 65.1%;
  --accent: 217.2 32.6% 17.5%;
  --accent-foreground: 210 40% 98%;
  
  /* Semantic Colors (adjusted for dark backgrounds) */
  --destructive: 0 62.8% 30.6%;
  --destructive-foreground: 210 40% 98%;
  --success: 142 70% 45%;
  --success-foreground: 210 40% 98%;
  --warning: 48 90% 60%;
  --warning-foreground: 222.2 47.4% 11.2%;
  --info: 199 85% 55%;
  --info-foreground: 210 40% 98%;
  
  /* OCR-Specific Colors (dark mode optimized) */
  --confidence-high: 142 70% 45%;
  --confidence-medium: 48 90% 60%;
  --confidence-low: 0 80% 65%;
  --processing: 217 85% 65%;
  
  /* Backend Colors (dark mode optimized) */
  --backend-deepseek: 271 75% 60%;
  --backend-got: 142 65% 50%;
  --backend-surya: 217 85% 65%;
  
  /* UI Elements */
  --border: 217.2 32.6% 17.5%;
  --input: 217.2 32.6% 17.5%;
  --ring: 224.3 76.3% 48%;
}
Typography
css:root {
  /* Font Families */
  --font-sans: 'Inter var', -apple-system, BlinkMacSystemFont, 'Segoe UI', 
               Roboto, 'Helvetica Neue', Arial, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  
  /* Type Scale (Fluid Typography) */
  --text-xs: clamp(0.75rem, 0.7rem + 0.25vw, 0.875rem);
  --text-sm: clamp(0.875rem, 0.825rem + 0.25vw, 1rem);
  --text-base: clamp(1rem, 0.95rem + 0.25vw, 1.125rem);
  --text-lg: clamp(1.125rem, 1.05rem + 0.375vw, 1.25rem);
  --text-xl: clamp(1.25rem, 1.15rem + 0.5vw, 1.5rem);
  --text-2xl: clamp(1.5rem, 1.35rem + 0.75vw, 1.875rem);
  --text-3xl: clamp(1.875rem, 1.65rem + 1.125vw, 2.25rem);
  --text-4xl: clamp(2.25rem, 1.95rem + 1.5vw, 3rem);
  
  /* Line Heights */
  --leading-none: 1;
  --leading-tight: 1.25;
  --leading-snug: 1.375;
  --leading-normal: 1.5;
  --leading-relaxed: 1.625;
  --leading-loose: 2;
  
  /* Font Weights */
  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;
}
Spacing
css:root {
  /* 4px base unit */
  --space-0: 0;
  --space-1: 0.25rem;    /* 4px */
  --space-2: 0.5rem;     /* 8px */
  --space-3: 0.75rem;    /* 12px */
  --space-4: 1rem;       /* 16px */
  --space-5: 1.25rem;    /* 20px */
  --space-6: 1.5rem;     /* 24px */
  --space-8: 2rem;       /* 32px */
  --space-10: 2.5rem;    /* 40px */
  --space-12: 3rem;      /* 48px */
  --space-16: 4rem;      /* 64px */
  --space-20: 5rem;      /* 80px */
  --space-24: 6rem;      /* 96px */
  --space-32: 8rem;      /* 128px */
}
Shadows
css:root {
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
  --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1);
  --shadow-2xl: 0 25px 50px -12px rgb(0 0 0 / 0.25);
  --shadow-focus: 0 0 0 3px hsl(var(--ring) / 0.5);
}

.dark {
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.3);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.4);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.4);
  --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.4);
  --shadow-2xl: 0 25px 50px -12px rgb(0 0 0 / 0.6);
}
Animations
css:root {
  --duration-fast: 150ms;
  --duration-base: 250ms;
  --duration-slow: 350ms;
  
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  --ease-out: cubic-bezier(0, 0, 0.2, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
}

📦 Component Library Stack
Core: shadcn/ui + Extensions
Base shadcn/ui:
bashnpx shadcn-ui@latest add button card input label select dialog
npx shadcn-ui@latest add dropdown-menu toast progress tabs table
npx shadcn-ui@latest add badge skeleton separator scroll-area command
Extensions:

OriginUI - 100+ extended shadcn components
MVPblocks - Pre-built IDP sections
SHSFUI - Enhanced form components
KiboUI - Additional UI patterns
skiperUI - Component variants
tweakcn - Customization toolkit

Enterprise UI

Untitled UI - Premium design system
Uber Base - Reference architecture
Saas UI - SaaS patterns
Reshaped - Modern components

Specialized Libraries
AI/Chat Interfaces:

assistant-ui - AI chat for OCR review

Confidence feedback loops
Interactive correction workflows



Data Visualization:

Tremor - Dashboard components

GPU utilization charts
Processing metrics
Queue depth visualization



Advanced Components:

Aceternity UI - Animated components
Magic UI - Interactive patterns

Document Processing
PDF Handling:
bashnpm install react-pdf @react-pdf-viewer/core pdfjs-dist pdf-lib
Canvas/Annotation:
bashnpm install @tldraw/tldraw konva react-konva fabric
File Upload:
bashnpm install @uppy/core @uppy/react @uppy/xhr-upload 
npm install @uppy/image-editor @uppy/drag-drop
Tables:
bashnpm install @tanstack/react-table
Real-time:
bashnpm install yjs y-websocket @liveblocks/client @liveblocks/react
Forms:
bashnpm install react-hook-form zod @hookform/resolvers
Animations:
bashnpm install framer-motion
State:
bashnpm install zustand @tanstack/react-query
i18n:
bashnpm install react-i18next i18next date-fns

🌗 Dark/Light Mode Implementation
Theme Provider Setup
tsx// app/providers/theme-provider.tsx
import { ThemeProvider as NextThemesProvider } from 'next-themes'

export function ThemeProvider({ children, ...props }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange={false}
      storageKey="ablage-theme"
      themes={['light', 'dark', 'system']}
      {...props}
    >
      {children}
    </NextThemesProvider>
  )
}
Theme Toggle Component
tsx// components/theme-toggle.tsx
import { Moon, Sun, Monitor } from 'lucide-react'
import { useTheme } from 'next-themes'

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  
  return (
    <ToggleGroup type="single" value={theme} onValueChange={setTheme}>
      <ToggleGroupItem value="light" aria-label="Light mode">
        <Sun className="h-4 w-4" />
      </ToggleGroupItem>
      <ToggleGroupItem value="dark" aria-label="Dark mode">
        <Moon className="h-4 w-4" />
      </ToggleGroupItem>
      <ToggleGroupItem value="system" aria-label="System theme">
        <Monitor className="h-4 w-4" />
      </ToggleGroupItem>
    </ToggleGroup>
  )
}
Smooth Transitions
css/* globals.css */
* {
  transition-property: color, background-color, border-color;
  transition-duration: 150ms;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
}

/* Disable transitions on theme change to avoid flash */
.theme-transitioning * {
  transition: none !important;
}

🇩🇪 German Localization
i18n Setup
typescript// i18n/config.ts
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import de from './locales/de.json'
import en from './locales/en.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      de: { translation: de },
      en: { translation: en }
    },
    fallbackLng: 'de',
    lng: 'de',
    interpolation: {
      escapeValue: false
    }
  })

export default i18n
German Translations
json{
  "document": {
    "upload": "Dokument hochladen",
    "dragDrop": "Dokumente hierher ziehen oder klicken zum Auswählen",
    "processing": "Wird verarbeitet",
    "completed": "Abgeschlossen",
    "failed": "Fehlgeschlagen"
  },
  "complexity": {
    "simple": "Einfach",
    "moderate": "Mittel",
    "complex": "Komplex",
    "autoDetected": "Automatisch erkannt"
  },
  "backend": {
    "deepseek": "DeepSeek-Janus-Pro",
    "got": "GOT-OCR 2.0",
    "surya": "Surya + Docling",
    "available": "Verfügbar",
    "busy": "Ausgelastet",
    "offline": "Offline"
  },
  "time": {
    "seconds": "Sekunden",
    "minutes": "Minuten",
    "hours": "Stunden",
    "remaining": "Verbleibend",
    "average": "Durchschnittlich"
  },
  "confidence": {
    "high": "Hohe Genauigkeit",
    "medium": "Mittlere Genauigkeit",
    "low": "Niedrige Genauigkeit",
    "score": "Genauigkeit"
  }
}
Date Formatting
typescript// utils/format.ts
import { format } from 'date-fns'
import { de } from 'date-fns/locale'

export const formatDate = (date: Date) => {
  return format(date, 'dd.MM.yyyy', { locale: de })
}

export const formatDateTime = (date: Date) => {
  return format(date, 'dd.MM.yyyy HH:mm', { locale: de })
}

export const formatNumber = (num: number, decimals = 2) => {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(num)
}

export const formatCurrency = (amount: number) => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR'
  }).format(amount)
}

♿ Accessibility Guidelines
Keyboard Navigation

Tab: Navigate through interactive elements
Shift+Tab: Navigate backwards
Enter/Space: Activate buttons, toggle switches
Escape: Close modals, cancel actions
Arrow keys: Navigate lists, select options
Cmd/Ctrl+K: Open command palette

ARIA Labels
tsx<Button
  onClick={uploadDocument}
  aria-label="Dokument hochladen"
  aria-describedby="upload-help-text"
>
  <Upload className="w-4 h-4" />
</Button>

<div id="upload-help-text" className="sr-only">
  Laden Sie PDF-, PNG- oder JPG-Dateien bis zu 100 MB hoch
</div>
Focus Management
tsx// Auto-focus first input in modal
useEffect(() => {
  if (isOpen) {
    inputRef.current?.focus()
  }
}, [isOpen])

// Trap focus within modal
import { FocusTrap } from '@headlessui/react'

<FocusTrap>
  <Dialog>{/* content */}</Dialog>
</FocusTrap>

⚡ Animations & Micro-interactions
Framer Motion Patterns
tsx// components/animated/fade-in.tsx
import { motion } from 'framer-motion'

export const FadeIn = ({ children, delay = 0 }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -20 }}
    transition={{ duration: 0.3, delay }}
  >
    {children}
  </motion.div>
)

// Stagger children animation
export const StaggerContainer = ({ children }) => (
  <motion.div
    initial="hidden"
    animate="visible"
    variants={{
      visible: {
        transition: {
          staggerChildren: 0.1
        }
      }
    }}
  >
    {children}
  </motion.div>
)

export const StaggerItem = ({ children }) => (
  <motion.div
    variants={{
      hidden: { opacity: 0, y: 20 },
      visible: { opacity: 1, y: 0 }
    }}
  >
    {children}
  </motion.div>
)
Loading States
tsx// components/loading/skeleton-grid.tsx
export const DocumentGridSkeleton = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {Array.from({ length: 6 }).map((_, i) => (
      <Card key={i} className="p-4">
        <Skeleton className="h-48 w-full mb-4" />
        <Skeleton className="h-4 w-3/4 mb-2" />
        <Skeleton className="h-3 w-1/2" />
      </Card>
    ))}
  </div>
)

// Shimmer effect
export const Shimmer = () => (
  <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite]">
    <div className="h-full w-full bg-gradient-to-r from-transparent via-white/10 to-transparent" />
  </div>
)

📐 Responsive Design
Breakpoints
typescriptconst breakpoints = {
  sm: '640px',    // Mobile landscape
  md: '768px',    // Tablet
  lg: '1024px',   // Desktop
  xl: '1280px',   // Large desktop
  '2xl': '1536px' // Extra large
}
Mobile-First Patterns
tsx// Stack on mobile, grid on desktop
<div className="flex flex-col lg:grid lg:grid-cols-2 gap-4">
  {/* Content */}
</div>

// Hide on mobile
<div className="hidden md:block">
  {/* Sidebar */}
</div>

// Show menu button on mobile only
<Button className="md:hidden">
  <Menu />
</Button>

📚 Resources
Documentation

shadcn/ui Docs
Tailwind CSS
Framer Motion
TanStack Query
React Hook Form

Design Inspiration

Untitled UI
Uber Base
assistant-ui
Tremor


Version: 1.0.0
Last Updated: 2025-01-17
Status: Production Ready


Note: This design system is a living document. Update it as the Ablage-System evolves.