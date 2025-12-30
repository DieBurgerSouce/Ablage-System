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
} from 'lucide-react'

export interface WidgetDefinition {
    component: React.ComponentType
    label: string
    description: string
    icon: LucideIcon
    category: 'info' | 'action' | 'data'
}

export const WIDGET_REGISTRY: Record<string, WidgetDefinition> = {
    TODAY_IMPORTANT: {
        component: TodayWidget,
        label: 'Heute wichtig',
        description: 'Zeigt faellige Aufgaben und wichtige Termine fuer heute an.',
        icon: Calendar,
        category: 'info',
    },
    SYSTEM_KPIS: {
        component: SystemStatusWidget,
        label: 'System Status',
        description: 'Uebersicht ueber Systemgesundheit, CPU, Speicher und aktive Jobs.',
        icon: Activity,
        category: 'info',
    },
    FINANCE_KPIS: {
        component: FinanceStatusWidget,
        label: 'Finanzen',
        description: 'Finanzielle Kennzahlen wie offene Rechnungen und Zahlungsstatus.',
        icon: Wallet,
        category: 'data',
    },
    QUICK_LINKS: {
        component: QuickLinksWidget,
        label: 'Schnellzugriff',
        description: 'Schneller Zugang zu haeufig verwendeten Bereichen.',
        icon: Link2,
        category: 'action',
    },
    UPLOAD_WIDGET: {
        component: UploadWidget,
        label: 'Upload',
        description: 'Dokumente per Drag & Drop hochladen.',
        icon: Upload,
        category: 'action',
    },
    RECENT_DOCUMENTS: {
        component: RecentDocumentsWidget,
        label: 'Kuerzlich hinzugefuegt',
        description: 'Liste der zuletzt hochgeladenen Dokumente.',
        icon: FileText,
        category: 'data',
    },
}

export function getWidgetComponent(type: string) {
    return WIDGET_REGISTRY[type]?.component || (() => <div className="p-4 border border-dashed text-muted-foreground">Widget Typ nicht gefunden: {type}</div>)
}

export function getWidgetLabel(type: string): string {
    return WIDGET_REGISTRY[type]?.label || type
}
