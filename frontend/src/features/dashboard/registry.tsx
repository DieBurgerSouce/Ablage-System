import { SystemStatusWidget } from './components/widgets/SystemStatusWidget'
import { FinanceStatusWidget } from './components/widgets/FinanceStatusWidget'
import { TodayWidget } from './components/widgets/TodayWidget'
import { QuickLinksWidget } from './components/widgets/QuickLinksWidget'
import { UploadWidget } from './components/widgets/UploadWidget'
import { RecentDocumentsWidget } from './components/widgets/RecentDocumentsWidget'
import { CashFlowWidget } from './components/widgets/CashFlowWidget'
import { AgingReportWidget } from './components/widgets/AgingReportWidget'
import { DunningWidget } from './components/widgets/DunningWidget'
import { SkontoWidget } from './components/widgets/SkontoWidget'
import { OCRPerformanceWidget } from './components/widgets/OCRPerformanceWidget'
import { ActivityFeedWidget } from './components/ActivityFeed'
import { ProactiveInsightsWidget } from './components/widgets/ProactiveInsightsWidget'
import { ApprovalsWidget } from './components/widgets/ApprovalsWidget'
import { PortfolioSummaryWidget } from './components/widgets/PortfolioSummaryWidget'
import { PropertyKPIsWidget } from './components/widgets/PropertyKPIsWidget'
import { InsuranceCoverageWidget } from './components/widgets/InsuranceCoverageWidget'
import { ImportSyncStatusWidget } from './components/widgets/ImportSyncStatusWidget'
import { ComplianceDeadlineWidget } from './components/widgets/ComplianceDeadlineWidget'
import { MLOpsPerformanceWidget } from './components/widgets/MLOpsPerformanceWidget'
import { CashPositionWidget } from './components/widgets/CashPositionWidget'
import type { LucideIcon } from 'lucide-react'
import {
    Calendar,
    Activity,
    Wallet,
    Link2,
    Upload,
    FileText,
    Receipt,
    TrendingUp,
    Clock,
    FileCheck,
    PiggyBank,
    Home,
    ShieldCheck,
    CheckCircle2,
    Bell,
    Percent,
    Sparkles,
    RefreshCw,
    Scale,
    Brain,
    Banknote,
} from 'lucide-react'

export interface WidgetRegistryEntry {
    type: string
    component: React.ComponentType
    label: string
    description: string
    icon: LucideIcon
    category: 'info' | 'action' | 'data' | 'finance'
    defaultSize?: { w: number; h: number }
    minSize?: { w: number; h: number }
}

// Unified widget registry with both legacy UPPER_CASE and new snake-case keys
// Backend uses snake-case, frontend historically used UPPER_CASE
const WIDGET_DEFINITIONS: WidgetRegistryEntry[] = [
    {
        type: 'today',
        component: TodayWidget,
        label: 'Heute wichtig',
        description: 'Zeigt fällige Aufgaben und wichtige Termine für heute an.',
        icon: Calendar,
        category: 'info',
        defaultSize: { w: 4, h: 3 },
    },
    {
        type: 'system-status',
        component: SystemStatusWidget,
        label: 'System Status',
        description: 'Übersicht über Systemgesundheit, CPU, Speicher und aktive Jobs.',
        icon: Activity,
        category: 'info',
        defaultSize: { w: 4, h: 3 },
    },
    {
        type: 'finance-status',
        component: FinanceStatusWidget,
        label: 'Finanzen',
        description: 'Finanzielle Kennzahlen wie offene Rechnungen und Zahlungsstatus.',
        icon: Wallet,
        category: 'finance',
        defaultSize: { w: 4, h: 3 },
    },
    {
        type: 'quick-links',
        component: QuickLinksWidget,
        label: 'Schnellzugriff',
        description: 'Schneller Zugang zu häufig verwendeten Bereichen.',
        icon: Link2,
        category: 'action',
        defaultSize: { w: 4, h: 2 },
    },
    {
        type: 'upload',
        component: UploadWidget,
        label: 'Upload',
        description: 'Dokumente per Drag & Drop hochladen.',
        icon: Upload,
        category: 'action',
        defaultSize: { w: 6, h: 4 },
    },
    {
        type: 'recent-documents',
        component: RecentDocumentsWidget,
        label: 'Kürzlich hinzugefügt',
        description: 'Liste der zuletzt hochgeladenen Dokumente.',
        icon: FileText,
        category: 'data',
        defaultSize: { w: 6, h: 4 },
    },
    // Neue Widgets fuer Feature 05
    {
        type: 'open-invoices',
        component: DunningWidget,
        label: 'Offene Mahnungen',
        description: 'Zeigt offene Mahnungen mit Mahnstufen, Gesamtbetrag und betroffenen Kunden.',
        icon: Receipt,
        category: 'finance',
        defaultSize: { w: 6, h: 3 },
    },
    {
        type: 'skonto',
        component: SkontoWidget,
        label: 'Skonto-Chancen',
        description: 'Zeigt Skonto-Moeglichkeiten mit Fristen und moeglicher Ersparnis.',
        icon: Percent,
        category: 'finance',
        defaultSize: { w: 6, h: 3 },
    },
    {
        type: 'cashflow',
        component: CashFlowWidget,
        label: 'Cashflow',
        description: 'Liquiditätsprognose mit Einnahmen vs Ausgaben der nächsten Tage.',
        icon: TrendingUp,
        category: 'finance',
        defaultSize: { w: 6, h: 4 },
    },
    {
        type: 'aging-report',
        component: AgingReportWidget,
        label: 'Fälligkeitsstruktur',
        description: 'Altersstruktur von Forderungen und Verbindlichkeiten als Balkendiagramm.',
        icon: Clock,
        category: 'finance',
        defaultSize: { w: 6, h: 4 },
    },
    {
        type: 'documents-today',
        component: OCRPerformanceWidget,
        label: 'OCR-Performance',
        description: 'Heute verarbeitete Dokumente mit Erfolgsrate und Backend-Verteilung.',
        icon: FileCheck,
        category: 'data',
        defaultSize: { w: 6, h: 4 },
    },
    // Enterprise KPI Widgets
    {
        type: 'portfolio-summary',
        component: PortfolioSummaryWidget,
        label: 'Portfolio Übersicht',
        description: 'Nettovermögen und Vermögensaufteilung auf einen Blick.',
        icon: PiggyBank,
        category: 'finance',
        defaultSize: { w: 6, h: 5 },
        minSize: { w: 4, h: 4 },
    },
    {
        type: 'property-kpis',
        component: PropertyKPIsWidget,
        label: 'Immobilien KPIs',
        description: 'Mietrendite, ROI und Wertentwicklung aller Immobilien.',
        icon: Home,
        category: 'finance',
        defaultSize: { w: 6, h: 5 },
        minSize: { w: 4, h: 4 },
    },
    {
        type: 'insurance-coverage',
        component: InsuranceCoverageWidget,
        label: 'Versicherungsschutz',
        description: 'Deckungslücken und anstehende Kündigungsfristen.',
        icon: ShieldCheck,
        category: 'finance',
        defaultSize: { w: 4, h: 5 },
        minSize: { w: 3, h: 4 },
    },
    {
        type: 'approvals-pending',
        component: ApprovalsWidget,
        label: 'Genehmigungen',
        description: 'Ausstehende Genehmigungsanfragen mit Fälligkeiten.',
        icon: CheckCircle2,
        category: 'action',
        defaultSize: { w: 4, h: 4 },
        minSize: { w: 3, h: 3 },
    },
    {
        type: 'activity-feed',
        component: ActivityFeedWidget,
        label: 'Live-Aktivitäten',
        description: 'Echtzeit-Feed aller Systemereignisse (Dokumente, OCR, Validierung).',
        icon: Bell,
        category: 'info',
        defaultSize: { w: 4, h: 5 },
        minSize: { w: 3, h: 3 },
    },
    {
        type: 'proactive-insights',
        component: ProactiveInsightsWidget,
        label: 'KI-Insights',
        description: 'KI-generierte Erkenntnisse und Handlungsempfehlungen (Skonto, Risiken, Optimierungen).',
        icon: Sparkles,
        category: 'info',
        defaultSize: { w: 6, h: 5 },
        minSize: { w: 4, h: 3 },
    },
    // Enterprise Monitoring Widgets (Phase 1.3)
    {
        type: 'import-sync-status',
        component: ImportSyncStatusWidget,
        label: 'Import Sync Status',
        description: 'Status aller Import-Quellen (DATEV, Lexware, Email, Folder).',
        icon: RefreshCw,
        category: 'data',
        defaultSize: { w: 4, h: 5 },
        minSize: { w: 3, h: 4 },
    },
    {
        type: 'compliance-deadlines',
        component: ComplianceDeadlineWidget,
        label: 'Compliance & Fristen',
        description: 'GoBD, Audit-Termine, GDPR-Loeschfristen und Aufbewahrungspflichten.',
        icon: Scale,
        category: 'info',
        defaultSize: { w: 4, h: 5 },
        minSize: { w: 3, h: 4 },
    },
    {
        type: 'mlops-performance',
        component: MLOpsPerformanceWidget,
        label: 'MLOps Performance',
        description: 'OCR-Accuracy, Model-Drift, A/B Tests und Retraining-Status.',
        icon: Brain,
        category: 'data',
        defaultSize: { w: 6, h: 5 },
        minSize: { w: 4, h: 4 },
    },
    {
        type: 'cash-position',
        component: CashPositionWidget,
        label: 'Kassenstand',
        description: 'Echtzeit Kontostand, Tagesbewegungen und Liquiditaetsprognose.',
        icon: Banknote,
        category: 'finance',
        defaultSize: { w: 4, h: 5 },
        minSize: { w: 3, h: 4 },
    },
]

// Create registry map for fast lookup
export const widgetRegistry: Record<string, WidgetRegistryEntry> = Object.fromEntries(
    WIDGET_DEFINITIONS.map((def) => [def.type, def])
)

// Legacy mapping for backwards compatibility
const LEGACY_TYPE_MAP: Record<string, string> = {
    'TODAY_IMPORTANT': 'today',
    'SYSTEM_KPIS': 'system-status',
    'FINANCE_KPIS': 'finance-status',
    'QUICK_LINKS': 'quick-links',
    'UPLOAD_WIDGET': 'upload',
    'RECENT_DOCUMENTS': 'recent-documents',
}

// Normalize widget type to snake-case format
export function normalizeWidgetType(type: string): string {
    return LEGACY_TYPE_MAP[type] || type
}

// Legacy WIDGET_REGISTRY for backwards compatibility
export const WIDGET_REGISTRY: Record<string, WidgetRegistryEntry> = {
    ...widgetRegistry,
    // Add legacy keys pointing to same definitions
    'TODAY_IMPORTANT': widgetRegistry['today'],
    'SYSTEM_KPIS': widgetRegistry['system-status'],
    'FINANCE_KPIS': widgetRegistry['finance-status'],
    'QUICK_LINKS': widgetRegistry['quick-links'],
    'UPLOAD_WIDGET': widgetRegistry['upload'],
    'RECENT_DOCUMENTS': widgetRegistry['recent-documents'],
}

export function getWidgetComponent(type: string) {
    const normalizedType = normalizeWidgetType(type)
    return widgetRegistry[normalizedType]?.component || (() => <div className="p-4 border border-dashed text-muted-foreground">Widget Typ nicht gefunden: {type}</div>)
}

export function getWidgetLabel(type: string): string {
    const normalizedType = normalizeWidgetType(type)
    return widgetRegistry[normalizedType]?.label || type
}

export function getWidgetDefinition(type: string): WidgetRegistryEntry | undefined {
    const normalizedType = normalizeWidgetType(type)
    return widgetRegistry[normalizedType]
}

export function getAllWidgets(): WidgetRegistryEntry[] {
    return WIDGET_DEFINITIONS
}

export function getWidgetsByCategory(category: WidgetRegistryEntry['category']): WidgetRegistryEntry[] {
    return WIDGET_DEFINITIONS.filter((w) => w.category === category)
}
