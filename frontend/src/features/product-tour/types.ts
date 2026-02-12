/**
 * Interaktive Produkttour - Type Definitions
 *
 * Vision 2026+ Feature: Geführtes Onboarding mit Highlight-Tour
 */

export type TourCategory = 'grundlagen' | 'dokumente' | 'fortgeschritten'

export interface TourStep {
  id: string
  title: string
  description: string
  targetSelector?: string // CSS selector für Element highlight
  position: 'top' | 'bottom' | 'left' | 'right' | 'center'
  order: number
  icon?: string
  highlightPadding?: number // px padding around target
  action?: TourAction
  validation?: TourValidation
}

export interface TourAction {
  type: 'click' | 'input' | 'navigate' | 'custom'
  payload?: string | Record<string, unknown>
}

export interface TourValidation {
  type: 'element_exists' | 'element_visible' | 'custom'
  selector?: string
  customFn?: () => boolean
}

export interface TourProgress {
  tourId: string
  currentStepIndex: number
  completedSteps: string[]
  startedAt: Date
  lastUpdatedAt: Date
  isCompleted: boolean
  isSkipped: boolean
}

export interface Tour {
  id: string
  name: string
  description: string
  category: TourCategory
  estimatedMinutes: number
  steps: TourStep[]
  requiredRole?: string
  context?: string // Page/route context
  badge?: TourBadge
}

export interface TourBadge {
  id: string
  name: string
  description: string
  icon: string
  unlockedAt?: Date
}

export interface TourState {
  isActive: boolean
  currentTour: Tour | null
  currentStepIndex: number
  progress: TourProgress | null
  badges: TourBadge[]
}

// Tour-Daten
export const TOURS: Tour[] = [
  {
    id: 'willkommen',
    name: 'Willkommen im Ablage-System',
    description: 'Lernen Sie die Grundfunktionen in wenigen Schritten kennen.',
    category: 'grundlagen',
    estimatedMinutes: 2,
    badge: {
      id: 'entdecker',
      name: 'Entdecker',
      description: 'Sie haben die Willkommens-Tour abgeschlossen!',
      icon: 'Compass',
    },
    steps: [
      {
        id: 'willkommen-seitenleiste',
        title: 'Seitenleiste navigieren',
        description: 'Die Seitenleiste enthält alle Hauptbereiche: Dokumente, Rechnungen, Banking und mehr. Klicken Sie auf einen Eintrag, um den Bereich zu öffnen.',
        targetSelector: '[data-tour="sidebar"]',
        position: 'right',
        order: 1,
        icon: 'Layout',
      },
      {
        id: 'willkommen-dashboard',
        title: 'Dashboard verstehen',
        description: 'Das Dashboard zeigt Ihnen eine Übersicht über alle wichtigen Kennzahlen und aktuelle Aufgaben auf einen Blick.',
        targetSelector: '[data-tour="dashboard-widgets"]',
        position: 'bottom',
        order: 2,
        icon: 'LayoutDashboard',
      },
      {
        id: 'willkommen-dokumentenliste',
        title: 'Dokumentenliste',
        description: 'Hier finden Sie alle Ihre Dokumente. Sortieren, filtern und durchsuchen Sie Ihre Ablage.',
        targetSelector: '[data-tour="document-list"]',
        position: 'bottom',
        order: 3,
        icon: 'FileText',
      },
      {
        id: 'willkommen-suche',
        title: 'Suche benutzen',
        description: 'Mit der Volltextsuche finden Sie jedes Dokument blitzschnell. Nutzen Sie Stichwörter, Dateinamen oder OCR-erkannten Text.',
        targetSelector: '[data-tour="search-bar"]',
        position: 'bottom',
        order: 4,
        icon: 'Search',
      },
      {
        id: 'willkommen-einstellungen',
        title: 'Einstellungen finden',
        description: 'Unter Einstellungen passen Sie das System an Ihre Bedürfnisse an: Sprache, Benachrichtigungen, OCR-Backends und mehr.',
        targetSelector: '[data-tour="settings-link"]',
        position: 'right',
        order: 5,
        icon: 'Settings',
      },
    ],
  },
  {
    id: 'dokument-hochladen',
    name: 'Dokument hochladen & verarbeiten',
    description: 'Erfahren Sie, wie Sie Dokumente hochladen und per OCR verarbeiten.',
    category: 'dokumente',
    estimatedMinutes: 3,
    badge: {
      id: 'archivar',
      name: 'Archivar',
      description: 'Sie wissen jetzt, wie man Dokumente hochlädt und verarbeitet!',
      icon: 'Archive',
    },
    steps: [
      {
        id: 'upload-button-finden',
        title: 'Upload-Button finden',
        description: 'Der Upload-Button befindet sich oben in der Dokumentenliste. Klicken Sie darauf, um neue Dokumente hinzuzufügen.',
        targetSelector: '[data-tour="upload-button"]',
        position: 'bottom',
        order: 1,
        icon: 'Upload',
      },
      {
        id: 'upload-datei-auswählen',
        title: 'Datei auswählen',
        description: 'Wählen Sie eine oder mehrere Dateien aus. Unterstützt werden PDF, JPG, PNG und TIFF. Sie können Dateien auch per Drag & Drop ablegen.',
        targetSelector: '[data-tour="upload-dropzone"]',
        position: 'bottom',
        order: 2,
        icon: 'File',
      },
      {
        id: 'upload-ocr-backend',
        title: 'OCR-Backend wählen',
        description: 'Wählen Sie das passende OCR-Backend: DeepSeek für beste Qualität, GOT-OCR für Tabellen oder Surya als schnelle Alternative.',
        targetSelector: '[data-tour="ocr-backend-select"]',
        position: 'bottom',
        order: 3,
        icon: 'Cpu',
      },
      {
        id: 'upload-verarbeitung',
        title: 'Verarbeitung starten',
        description: 'Klicken Sie auf "Verarbeiten", um die OCR-Texterkennung zu starten. Der Fortschritt wird in Echtzeit angezeigt.',
        targetSelector: '[data-tour="process-button"]',
        position: 'bottom',
        order: 4,
        icon: 'Play',
      },
      {
        id: 'upload-ergebnis',
        title: 'Ergebnis prüfen',
        description: 'Nach der Verarbeitung sehen Sie den erkannten Text und können ihn prüfen. Metadaten wie Datum und Betrag werden automatisch extrahiert.',
        targetSelector: '[data-tour="ocr-result"]',
        position: 'left',
        order: 5,
        icon: 'CheckCircle',
      },
    ],
  },
  {
    id: 'schnellsuche',
    name: 'Schnellsuche meistern',
    description: 'Lernen Sie, wie Sie Dokumente blitzschnell finden.',
    category: 'grundlagen',
    estimatedMinutes: 1,
    badge: {
      id: 'suchprofi',
      name: 'Suchprofi',
      description: 'Sie beherrschen die Schnellsuche!',
      icon: 'Search',
    },
    steps: [
      {
        id: 'suche-öffnen',
        title: 'Suchleiste öffnen',
        description: 'Klicken Sie in die Suchleiste oder drücken Sie Strg+K, um die Schnellsuche zu öffnen.',
        targetSelector: '[data-tour="search-bar"]',
        position: 'bottom',
        order: 1,
        icon: 'Search',
      },
      {
        id: 'suche-eingeben',
        title: 'Suchbegriff eingeben',
        description: 'Geben Sie einen Suchbegriff ein. Die Suche durchsucht Dateinamen, OCR-Text, Metadaten und Geschäftspartner gleichzeitig.',
        targetSelector: '[data-tour="search-input"]',
        position: 'bottom',
        order: 2,
        icon: 'Type',
      },
      {
        id: 'suche-filter',
        title: 'Filter nutzen',
        description: 'Verfeinern Sie die Ergebnisse mit Filtern: Datumsbereich, Dokumenttyp, Geschäftspartner oder OCR-Backend.',
        targetSelector: '[data-tour="search-filters"]',
        position: 'bottom',
        order: 3,
        icon: 'Filter',
      },
      {
        id: 'suche-sortieren',
        title: 'Ergebnisse sortieren',
        description: 'Sortieren Sie Ergebnisse nach Relevanz, Datum, Name oder Größe. Die Standardsortierung zeigt die relevantesten Treffer zuerst.',
        targetSelector: '[data-tour="search-sort"]',
        position: 'bottom',
        order: 4,
        icon: 'ArrowUpDown',
      },
    ],
  },
  {
    id: 'ocr-korrektur',
    name: 'OCR-Ergebnisse korrigieren',
    description: 'Erfahren Sie, wie Sie OCR-Ergebnisse prüfen und korrigieren.',
    category: 'fortgeschritten',
    estimatedMinutes: 2,
    badge: {
      id: 'qualitätssicherer',
      name: 'Qualitätssicherer',
      description: 'Sie wissen, wie man OCR-Ergebnisse professionell korrigiert!',
      icon: 'ShieldCheck',
    },
    steps: [
      {
        id: 'korrektur-dokument-öffnen',
        title: 'Dokument öffnen',
        description: 'Öffnen Sie ein verarbeitetes Dokument, um den erkannten Text neben dem Originalbild zu sehen.',
        targetSelector: '[data-tour="document-viewer"]',
        position: 'bottom',
        order: 1,
        icon: 'FileText',
      },
      {
        id: 'korrektur-text-prüfen',
        title: 'Erkannten Text prüfen',
        description: 'Vergleichen Sie den erkannten Text mit dem Originaldokument. Fehler werden farblich hervorgehoben, wenn die Konfidenz niedrig ist.',
        targetSelector: '[data-tour="ocr-text-panel"]',
        position: 'left',
        order: 2,
        icon: 'Eye',
      },
      {
        id: 'korrektur-vornehmen',
        title: 'Korrekturen vornehmen',
        description: 'Klicken Sie auf einen Textabschnitt, um ihn zu bearbeiten. Ihre Korrekturen verbessern das System automatisch für zukünftige Erkennungen.',
        targetSelector: '[data-tour="ocr-correction"]',
        position: 'left',
        order: 3,
        icon: 'Edit',
      },
      {
        id: 'korrektur-tastenkuerzel',
        title: 'Tastenkürzel nutzen',
        description: 'Nutzen Sie Tastenkürzel für schnelleres Arbeiten: A = Akzeptieren, C = Korrigieren, S = Überspringen, R = Zurücksetzen.',
        position: 'center',
        order: 4,
        icon: 'Keyboard',
      },
    ],
  },
]

export const getTourById = (id: string): Tour | undefined => {
  return TOURS.find(tour => tour.id === id)
}

/** Alle Touren nach Kategorie gruppiert */
export const getToursByCategory = (): Record<TourCategory, Tour[]> => {
  return TOURS.reduce<Record<TourCategory, Tour[]>>(
    (acc, tour) => {
      acc[tour.category].push(tour)
      return acc
    },
    { grundlagen: [], dokumente: [], fortgeschritten: [] }
  )
}

/** Deutsche Kategorie-Labels */
export const CATEGORY_LABELS: Record<TourCategory, string> = {
  grundlagen: 'Grundlagen',
  dokumente: 'Dokumente',
  fortgeschritten: 'Fortgeschritten',
}
