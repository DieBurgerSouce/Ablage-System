/**
 * Interaktive Produkttour - Type Definitions
 *
 * Vision 2026+ Feature: Geführtes Onboarding mit Highlight-Tour
 */

export interface TourStep {
  id: string
  title: string
  description: string
  targetSelector?: string // CSS selector fuer Element highlight
  position: 'top' | 'bottom' | 'left' | 'right' | 'center'
  order: number
  icon?: string
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

// Default Tours fuer Ablage-System
export const TOURS: Tour[] = [
  {
    id: 'welcome',
    name: 'Willkommen bei Ablage-System',
    description: 'Lernen Sie die Grundfunktionen in wenigen Schritten kennen.',
    badge: {
      id: 'first-steps',
      name: 'Erste Schritte',
      description: 'Sie haben die Willkommens-Tour abgeschlossen!',
      icon: 'Award',
    },
    steps: [
      {
        id: 'welcome-intro',
        title: 'Willkommen!',
        description: 'Willkommen bei Ablage-System! Diese kurze Tour zeigt Ihnen die wichtigsten Funktionen. Klicken Sie auf "Weiter" um zu beginnen.',
        position: 'center',
        order: 1,
        icon: 'HandWaving',
      },
      {
        id: 'sidebar-navigation',
        title: 'Navigation',
        description: 'Die Seitenleiste enthält alle Hauptbereiche: Dokumente, Rechnungen, Banking und mehr.',
        targetSelector: '[data-tour="sidebar"]',
        position: 'right',
        order: 2,
        icon: 'Layout',
      },
      {
        id: 'upload-button',
        title: 'Dokumente hochladen',
        description: 'Hier können Sie neue Dokumente hochladen. Wir unterstützen PDF, Bilder und mehr.',
        targetSelector: '[data-tour="upload-button"]',
        position: 'bottom',
        order: 3,
        icon: 'Upload',
      },
      {
        id: 'search-bar',
        title: 'Volltextsuche',
        description: 'Durchsuchen Sie alle Ihre Dokumente mit unserer leistungsstarken Volltextsuche.',
        targetSelector: '[data-tour="search-bar"]',
        position: 'bottom',
        order: 4,
        icon: 'Search',
      },
      {
        id: 'dashboard-overview',
        title: 'Dashboard',
        description: 'Das Dashboard zeigt Ihnen eine Übersicht über alle wichtigen Kennzahlen und Aufgaben.',
        targetSelector: '[data-tour="dashboard-widgets"]',
        position: 'center',
        order: 5,
        icon: 'LayoutDashboard',
      },
      {
        id: 'tour-complete',
        title: 'Tour abgeschlossen!',
        description: 'Super! Sie haben die Grundlagen kennengelernt. Sie können jederzeit über das Hilfe-Menü weitere Touren starten.',
        position: 'center',
        order: 6,
        icon: 'CheckCircle',
      },
    ],
  },
  {
    id: 'ocr-features',
    name: 'OCR-Funktionen',
    description: 'Erfahren Sie wie die automatische Texterkennung funktioniert.',
    badge: {
      id: 'ocr-expert',
      name: 'OCR Experte',
      description: 'Sie kennen jetzt alle OCR-Funktionen!',
      icon: 'Scan',
    },
    steps: [
      {
        id: 'ocr-intro',
        title: 'Automatische Texterkennung',
        description: 'Ablage-System nutzt modernste OCR-Technologie um Text aus Ihren Dokumenten zu extrahieren.',
        position: 'center',
        order: 1,
        icon: 'Scan',
      },
      {
        id: 'ocr-status',
        title: 'OCR-Status',
        description: 'Nach dem Upload sehen Sie hier den Verarbeitungsstatus. Grün bedeutet erfolgreich.',
        targetSelector: '[data-tour="ocr-status"]',
        position: 'left',
        order: 2,
        icon: 'CheckCircle',
      },
      {
        id: 'extracted-text',
        title: 'Extrahierter Text',
        description: 'Der erkannte Text wird hier angezeigt. Sie können ihn kopieren oder durchsuchen.',
        targetSelector: '[data-tour="extracted-text"]',
        position: 'right',
        order: 3,
        icon: 'FileText',
      },
      {
        id: 'ocr-corrections',
        title: 'Korrekturen',
        description: 'Falls der OCR-Text Fehler enthält, können Sie diese hier korrigieren. Das System lernt davon!',
        targetSelector: '[data-tour="ocr-correction"]',
        position: 'bottom',
        order: 4,
        icon: 'Edit',
      },
    ],
  },
  {
    id: 'entity-management',
    name: 'Geschäftspartner verwalten',
    description: 'Lernen Sie die Kunden- und Lieferantenverwaltung kennen.',
    badge: {
      id: 'partner-pro',
      name: 'Partner-Profi',
      description: 'Sie beherrschen die Geschäftspartner-Verwaltung!',
      icon: 'Users',
    },
    steps: [
      {
        id: 'entity-intro',
        title: 'Geschäftspartner',
        description: 'Verwalten Sie alle Ihre Kunden und Lieferanten an einem Ort.',
        position: 'center',
        order: 1,
        icon: 'Users',
      },
      {
        id: 'entity-list',
        title: 'Partner-Liste',
        description: 'Hier sehen Sie alle Ihre Geschäftspartner. Nutzen Sie Filter und Suche um schnell zu finden.',
        targetSelector: '[data-tour="entity-list"]',
        position: 'bottom',
        order: 2,
        icon: 'List',
      },
      {
        id: 'entity-detail',
        title: 'Partner-Details',
        description: 'Klicken Sie auf einen Partner um alle Details zu sehen: Dokumente, Rechnungen, Kommunikation.',
        targetSelector: '[data-tour="entity-detail"]',
        position: 'left',
        order: 3,
        icon: 'UserCircle',
      },
      {
        id: 'entity-linking',
        title: 'Auto-Verknüpfung',
        description: 'Dokumente werden automatisch dem richtigen Partner zugeordnet. Sie können dies auch manuell anpassen.',
        targetSelector: '[data-tour="entity-linking"]',
        position: 'right',
        order: 4,
        icon: 'Link',
      },
    ],
  },
]

export const getTourById = (id: string): Tour | undefined => {
  return TOURS.find(tour => tour.id === id)
}
