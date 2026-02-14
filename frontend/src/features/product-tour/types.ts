/**
 * Interaktive Produkttour - Type Definitions
 *
 * Vision 2026+ Feature: Geführtes Onboarding mit Highlight-Tour
 */

export type TourCategory = 'grundlagen' | 'dokumente' | 'fortgeschritten' | 'admin'

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
  {
    id: 'smart-search',
    name: 'Smart Search meistern',
    description: 'Lernen Sie die intelligente Suche mit natürlicher Sprache kennen.',
    category: 'fortgeschritten',
    estimatedMinutes: 2,
    badge: {
      id: 'suchmeister',
      name: 'Suchmeister',
      description: 'Sie beherrschen die intelligente Suche!',
      icon: 'Search',
    },
    steps: [
      {
        id: 'smart-search-nav',
        title: 'Smart Search öffnen',
        description: 'Navigieren Sie zur intelligenten Suche über die Seitenleiste. Smart Search versteht natürliche Sprache wie "Zeig mir alle Rechnungen von Mueller".',
        targetSelector: '[data-tour="nav-smart-search"]',
        position: 'right',
        order: 1,
        icon: 'Search',
      },
      {
        id: 'smart-search-input',
        title: 'Frage in natürlicher Sprache stellen',
        description: 'Tippen Sie Ihre Frage als normalen Satz ein. Zum Beispiel: "Offene Rechnungen über 500 Euro aus dem letzten Monat".',
        targetSelector: '[data-tour="search-input"]',
        position: 'bottom',
        order: 2,
        icon: 'MessageSquare',
      },
      {
        id: 'smart-search-results',
        title: 'Ergebnisse analysieren',
        description: 'Die Ergebnisse werden nach Relevanz sortiert angezeigt. Klicken Sie auf ein Dokument, um es zu öffnen.',
        targetSelector: '[data-tour="search-results"]',
        position: 'bottom',
        order: 3,
        icon: 'FileText',
      },
      {
        id: 'smart-search-filters',
        title: 'Facettierte Filter nutzen',
        description: 'Verfeinern Sie Ihre Suche mit dynamischen Filtern nach Typ, Datum, Status, Betrag oder Lieferant.',
        targetSelector: '[data-tour="search-filters"]',
        position: 'left',
        order: 4,
        icon: 'Filter',
      },
    ],
  },
  {
    id: 'rechnungsworkflow',
    name: 'Rechnungsworkflow nutzen',
    description: 'Erfahren Sie, wie Rechnungen vollautomatisch verarbeitet werden.',
    category: 'fortgeschritten',
    estimatedMinutes: 3,
    badge: {
      id: 'buchhalter',
      name: 'Buchhalter',
      description: 'Sie kennen den automatischen Rechnungsworkflow!',
      icon: 'Receipt',
    },
    steps: [
      {
        id: 'workflow-nav',
        title: 'Rechnungsworkflow öffnen',
        description: 'Der Rechnungsworkflow zeigt alle Rechnungen und ihren Verarbeitungsstatus auf einen Blick.',
        targetSelector: '[data-tour="nav-invoice-workflow"]',
        position: 'right',
        order: 1,
        icon: 'Receipt',
      },
      {
        id: 'workflow-pipeline',
        title: 'Pipeline verstehen',
        description: 'Jede Rechnung durchläuft automatisch: OCR-Erkennung, Lieferant-Zuordnung, Kategorisierung, Genehmigung und Zahlungsfreigabe.',
        targetSelector: '[data-tour="workflow-pipeline"]',
        position: 'bottom',
        order: 2,
        icon: 'GitBranch',
      },
      {
        id: 'workflow-approval',
        title: 'Auto-Genehmigung',
        description: 'Bekannte Lieferanten mit gutem Track-Record werden automatisch genehmigt. Bei hohen Beträgen erfolgt eine Eskalation zur manuellen Prüfung.',
        targetSelector: '[data-tour="workflow-approval"]',
        position: 'bottom',
        order: 3,
        icon: 'CheckCircle',
      },
      {
        id: 'workflow-review',
        title: 'Manuelle Prüfung',
        description: 'Rechnungen die eine Prüfung benötigen erscheinen hier. Genehmigen oder ablehnen Sie mit einem Klick.',
        targetSelector: '[data-tour="workflow-review"]',
        position: 'bottom',
        order: 4,
        icon: 'Eye',
      },
      {
        id: 'workflow-stats',
        title: 'Statistiken einsehen',
        description: 'Sehen Sie Ihre Auto-Approval-Rate, durchschnittliche Verarbeitungszeit und weitere KPIs.',
        targetSelector: '[data-tour="workflow-stats"]',
        position: 'top',
        order: 5,
        icon: 'BarChart',
      },
    ],
  },
  {
    id: 'steuerberater-paket',
    name: 'Steuerberater-Paket erstellen',
    description: 'Erstellen Sie automatische Buchhaltungspakete für Ihren Steuerberater.',
    category: 'fortgeschritten',
    estimatedMinutes: 2,
    badge: {
      id: 'steuerprofi',
      name: 'Steuerprofi',
      description: 'Sie können Steuerberater-Pakete erstellen!',
      icon: 'FileOutput',
    },
    steps: [
      {
        id: 'tax-nav',
        title: 'Steuerberater-Paket öffnen',
        description: 'Finden Sie die Funktion unter Administration in der Seitenleiste.',
        targetSelector: '[data-tour="nav-tax-package"]',
        position: 'right',
        order: 1,
        icon: 'FileOutput',
      },
      {
        id: 'tax-period',
        title: 'Zeitraum wählen',
        description: 'Wählen Sie den gewünschten Zeitraum: Monat, Quartal oder ganzes Jahr.',
        targetSelector: '[data-tour="tax-period-select"]',
        position: 'bottom',
        order: 2,
        icon: 'Calendar',
      },
      {
        id: 'tax-completeness',
        title: 'Vollständigkeit prüfen',
        description: 'Das System prüft automatisch ob alle Belege vorhanden sind und zeigt fehlende Dokumente an.',
        targetSelector: '[data-tour="tax-completeness"]',
        position: 'bottom',
        order: 3,
        icon: 'ClipboardCheck',
      },
      {
        id: 'tax-export',
        title: 'Paket generieren',
        description: 'Mit einem Klick erstellen Sie ein ZIP-Paket mit allen Belegen, DATEV-Export und Zusammenfassung.',
        targetSelector: '[data-tour="tax-export-button"]',
        position: 'bottom',
        order: 4,
        icon: 'Download',
      },
    ],
  },
  {
    id: 'admin-tour',
    name: 'Administration erkunden',
    description: 'Entdecken Sie die Verwaltungsfunktionen des Ablage-Systems.',
    category: 'admin',
    estimatedMinutes: 3,
    requiredRole: 'admin',
    badge: {
      id: 'administrator',
      name: 'Administrator',
      description: 'Sie kennen die Administrationsfunktionen!',
      icon: 'Shield',
    },
    steps: [
      {
        id: 'admin-open',
        title: 'Administration öffnen',
        description: 'Klicken Sie auf "Administration" in der Seitenleiste, um alle Verwaltungsfunktionen anzuzeigen.',
        targetSelector: '[data-tour="nav-admin"]',
        position: 'right',
        order: 1,
        icon: 'Shield',
      },
      {
        id: 'admin-ocr',
        title: 'OCR-Verwaltung',
        description: 'Verwalten Sie OCR-Training, Review-Queue und Backend-Konfiguration für optimale Texterkennung.',
        targetSelector: '[data-tour="nav-ocr-training"]',
        position: 'right',
        order: 2,
        icon: 'Brain',
      },
      {
        id: 'admin-workflows',
        title: 'Workflow-Regeln',
        description: 'Definieren Sie automatische Regeln für die Dokumentverarbeitung: Genehmigungen, Eskalationen und Zuordnungen.',
        targetSelector: '[data-tour="nav-workflows"]',
        position: 'right',
        order: 3,
        icon: 'GitBranch',
      },
      {
        id: 'admin-audit',
        title: 'Audit-Logs prüfen',
        description: 'Hier sehen Sie alle Systemaktivitäten: Wer hat wann welche Aktion durchgeführt.',
        targetSelector: '[data-tour="nav-audit-logs"]',
        position: 'right',
        order: 4,
        icon: 'ScrollText',
      },
      {
        id: 'admin-security',
        title: 'Trust Dashboard',
        description: 'Das Trust Dashboard zeigt Sicherheitsmetriken, Zugriffsmuster und Compliance-Status auf einen Blick.',
        targetSelector: '[data-tour="nav-trust-dashboard"]',
        position: 'right',
        order: 5,
        icon: 'Fingerprint',
      },
    ],
  },
  {
    id: 'digital-twin',
    name: 'Digitaler Zwilling entdecken',
    description: 'Erkunden Sie die 360-Grad-Unternehmensansicht.',
    category: 'fortgeschritten',
    estimatedMinutes: 2,
    badge: {
      id: 'stratege',
      name: 'Stratege',
      description: 'Sie kennen den Digitalen Zwilling Ihres Unternehmens!',
      icon: 'Globe',
    },
    steps: [
      {
        id: 'twin-nav',
        title: 'Digitalen Zwilling öffnen',
        description: 'Der Digitale Zwilling vereint alle Unternehmensdaten auf einer Seite.',
        targetSelector: '[data-tour="nav-digital-twin"]',
        position: 'right',
        order: 1,
        icon: 'Globe',
      },
      {
        id: 'twin-financial',
        title: 'Finanzielle Gesundheit',
        description: 'Sehen Sie Cashflow, Liquidität und offene Posten auf einen Blick. Trends werden automatisch erkannt.',
        targetSelector: '[data-tour="twin-financial"]',
        position: 'bottom',
        order: 2,
        icon: 'TrendingUp',
      },
      {
        id: 'twin-risk',
        title: 'Risiko-Übersicht',
        description: 'Alle Kunden und Lieferanten mit ihrem aktuellen Risiko-Score. Kritische Fälle werden hervorgehoben.',
        targetSelector: '[data-tour="twin-risk"]',
        position: 'bottom',
        order: 3,
        icon: 'ShieldAlert',
      },
      {
        id: 'twin-compliance',
        title: 'Compliance-Status',
        description: 'Prüfen Sie DSGVO- und GoBD-Konformität. Der Compliance-Score zeigt Handlungsbedarf.',
        targetSelector: '[data-tour="twin-compliance"]',
        position: 'bottom',
        order: 4,
        icon: 'Shield',
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
    { grundlagen: [], dokumente: [], fortgeschritten: [], admin: [] }
  )
}

/** Deutsche Kategorie-Labels */
export const CATEGORY_LABELS: Record<TourCategory, string> = {
  grundlagen: 'Grundlagen',
  dokumente: 'Dokumente',
  fortgeschritten: 'Fortgeschritten',
  admin: 'Administration',
}
