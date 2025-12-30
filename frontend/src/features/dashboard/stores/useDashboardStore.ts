import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface WidgetItem {
    id: string
    type: string // 'SYSTEM_KPIS' | 'FINANCE_KPIS' etc.
    x?: number // Reserved for grid layout if needed later, currently list order
    y?: number
    w?: number // Reserved
    h?: number // Reserved
}

interface DashboardState {
    widgets: WidgetItem[]
    setWidgets: (widgets: WidgetItem[]) => void
    addWidget: (type: string) => void
    removeWidget: (id: string) => void
    resetToDefault: () => void
}

const DEFAULT_WIDGETS: WidgetItem[] = [
    { id: 'today', type: 'TODAY_IMPORTANT' },
    { id: 'system', type: 'SYSTEM_KPIS' },
    { id: 'finance', type: 'FINANCE_KPIS' },
    { id: 'quick', type: 'QUICK_LINKS' },
    { id: 'upload', type: 'UPLOAD_WIDGET' },
    { id: 'recent', type: 'RECENT_DOCUMENTS' },
]

export const useDashboardStore = create<DashboardState>()(
    persist(
        (set) => ({
            widgets: DEFAULT_WIDGETS,
            setWidgets: (widgets) => set({ widgets }),
            addWidget: (type) =>
                set((state) => ({
                    widgets: [
                        ...state.widgets,
                        {
                            id: `${type.toLowerCase()}-${Date.now()}`,
                            type,
                        },
                    ],
                })),
            removeWidget: (id) =>
                set((state) => ({
                    widgets: state.widgets.filter((w) => w.id !== id),
                })),
            resetToDefault: () => set({ widgets: DEFAULT_WIDGETS }),
        }),
        {
            name: 'dashboard-storage',
        }
    )
)
