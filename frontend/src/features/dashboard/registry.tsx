import { SystemStatusWidget } from './components/widgets/SystemStatusWidget'
import { FinanceStatusWidget } from './components/widgets/FinanceStatusWidget'
import { TodayWidget } from './components/widgets/TodayWidget'
import { QuickLinksWidget } from './components/widgets/QuickLinksWidget'
import { UploadWidget } from './components/widgets/UploadWidget'
import { RecentDocumentsWidget } from './components/widgets/RecentDocumentsWidget'
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
        description: 'Zeigt faellige Aufgaben und wichtige Termine fuer heute an.',
        icon: Calendar,
        category: 'info',
        defaultSize: { w: 4, h: 3 },
    },
    {
        type: 'system-status',
        component: SystemStatusWidget,
        label: 'System Status',
        description: 'Uebersicht ueber Systemgesundheit, CPU, Speicher und aktive Jobs.',
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
        description: 'Schneller Zugang zu haeufig verwendeten Bereichen.',
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
        label: 'Kuerzlich hinzugefuegt',
        description: 'Liste der zuletzt hochgeladenen Dokumente.',
        icon: FileText,
        category: 'data',
        defaultSize: { w: 6, h: 4 },
    },
    // Neue Widgets fuer Feature 05
    {
        type: 'open-invoices',
        component: () => <div className="p-4">Offene Posten Widget (coming soon)</div>,
        label: 'Offene Posten',
        description: 'Zeigt offene Rechnungen mit Faelligkeitsdatum und Gesamtbetrag.',
        icon: Receipt,
        category: 'finance',
        defaultSize: { w: 6, h: 3 },
    },
    {
        type: 'cashflow',
        component: () => <div className="p-4">Cashflow Widget (coming soon)</div>,
        label: 'Cashflow',
        description: 'Mini-Chart mit Einnahmen vs Ausgaben der letzten Tage.',
        icon: TrendingUp,
        category: 'finance',
        defaultSize: { w: 6, h: 4 },
    },
    {
        type: 'aging-report',
        component: () => <div className="p-4">Aging Report Widget (coming soon)</div>,
        label: 'Faelligkeitsstruktur',
        description: 'Aufschluesselung nach Faelligkeitszeitraeumen (0-30, 31-60, etc.).',
        icon: Clock,
        category: 'finance',
        defaultSize: { w: 6, h: 4 },
    },
    {
        type: 'documents-today',
        component: () => <div className="p-4">Dokumente heute Widget (coming soon)</div>,
        label: 'Dokumente heute',
        description: 'Heute verarbeitete Dokumente mit OCR-Erfolgsrate.',
        icon: FileCheck,
        category: 'data',
        defaultSize: { w: 4, h: 3 },
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
