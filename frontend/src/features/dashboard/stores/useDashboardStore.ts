/**
 * Dashboard Store
 *
 * Zustand store for widget-based dashboard with:
 * - Size-aware widgets (w, h, x, y)
 * - Role-based presets
 * - Persistent storage
 *
 * Phase 3.3 der Feature-Roadmap (Januar 2026)
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { logger } from '@/lib/logger'

// ==================== Types ====================

export interface WidgetItem {
    id: string
    type: string
    x: number  // Column position (0-11 for 12-column grid)
    y: number  // Row position
    w: number  // Width in grid columns (1-12)
    h: number  // Height in grid rows (1-6)
}

export type UserRole = 'admin' | 'accountant' | 'manager' | 'user'

export interface DashboardPreset {
    id: string
    name: string
    description: string
    role: UserRole
    widgets: WidgetItem[]
}

interface DashboardState {
    widgets: WidgetItem[]
    activePreset: string | null
    gridColumns: number
    compactMode: boolean
    setWidgets: (widgets: WidgetItem[]) => void
    addWidget: (type: string, size?: { w: number; h: number }) => void
    removeWidget: (id: string) => void
    updateWidgetPosition: (id: string, x: number, y: number) => void
    updateWidgetSize: (id: string, w: number, h: number) => void
    resetToDefault: () => void
    applyPreset: (presetId: string) => void
    setCompactMode: (compact: boolean) => void
}

// ==================== Presets ====================

const GRID_COLUMNS = 12

export const DASHBOARD_PRESETS: DashboardPreset[] = [
    {
        id: 'default',
        name: 'Standard',
        description: 'Ausgewogene Ansicht für alle Benutzer',
        role: 'user',
        widgets: [
            { id: 'today', type: 'today', x: 0, y: 0, w: 4, h: 3 },
            { id: 'system', type: 'system-status', x: 4, y: 0, w: 4, h: 3 },
            { id: 'finance', type: 'finance-status', x: 8, y: 0, w: 4, h: 3 },
            { id: 'quick', type: 'quick-links', x: 0, y: 3, w: 4, h: 2 },
            { id: 'upload', type: 'upload', x: 4, y: 3, w: 4, h: 3 },
            { id: 'recent', type: 'recent-documents', x: 8, y: 3, w: 4, h: 3 },
        ],
    },
    {
        id: 'finance-focus',
        name: 'Finanzen',
        description: 'Fokus auf Finanzkennzahlen und Cashflow',
        role: 'accountant',
        widgets: [
            { id: 'finance', type: 'finance-status', x: 0, y: 0, w: 6, h: 3 },
            { id: 'cashflow', type: 'cashflow', x: 6, y: 0, w: 6, h: 4 },
            { id: 'aging', type: 'aging-report', x: 0, y: 3, w: 6, h: 4 },
            { id: 'dunning', type: 'open-invoices', x: 6, y: 4, w: 6, h: 3 },
            { id: 'today', type: 'today', x: 0, y: 7, w: 4, h: 3 },
            { id: 'recent', type: 'recent-documents', x: 4, y: 7, w: 8, h: 3 },
        ],
    },
    {
        id: 'manager-overview',
        name: 'Management',
        description: 'KPIs und Überblick für Führungskräfte',
        role: 'manager',
        widgets: [
            { id: 'today', type: 'today', x: 0, y: 0, w: 4, h: 4 },
            { id: 'finance', type: 'finance-status', x: 4, y: 0, w: 4, h: 3 },
            { id: 'system', type: 'system-status', x: 8, y: 0, w: 4, h: 3 },
            { id: 'activity', type: 'activity-feed', x: 8, y: 3, w: 4, h: 5 },
            { id: 'cashflow', type: 'cashflow', x: 0, y: 4, w: 8, h: 4 },
            { id: 'approvals', type: 'approvals-pending', x: 4, y: 3, w: 4, h: 1 },
        ],
    },
    {
        id: 'admin-full',
        name: 'Administration',
        description: 'Vollständige Systemübersicht für Admins',
        role: 'admin',
        widgets: [
            { id: 'system', type: 'system-status', x: 0, y: 0, w: 4, h: 3 },
            { id: 'ocr', type: 'documents-today', x: 4, y: 0, w: 4, h: 4 },
            { id: 'activity', type: 'activity-feed', x: 8, y: 0, w: 4, h: 5 },
            { id: 'today', type: 'today', x: 0, y: 3, w: 4, h: 3 },
            { id: 'upload', type: 'upload', x: 4, y: 4, w: 4, h: 3 },
            { id: 'recent', type: 'recent-documents', x: 0, y: 6, w: 8, h: 3 },
        ],
    },
    {
        id: 'minimal',
        name: 'Minimal',
        description: 'Kompakte Ansicht mit nur wesentlichen Widgets',
        role: 'user',
        widgets: [
            { id: 'today', type: 'today', x: 0, y: 0, w: 6, h: 3 },
            { id: 'quick', type: 'quick-links', x: 6, y: 0, w: 6, h: 2 },
            { id: 'upload', type: 'upload', x: 0, y: 3, w: 6, h: 3 },
            { id: 'recent', type: 'recent-documents', x: 6, y: 2, w: 6, h: 4 },
        ],
    },
]

// ==================== Default Layout ====================

const DEFAULT_WIDGETS: WidgetItem[] = DASHBOARD_PRESETS[0].widgets

// ==================== Helper Functions ====================

/**
 * Calculate next available position for a new widget
 */
function calculateNextPosition(
    widgets: WidgetItem[],
    newWidth: number,
    newHeight: number
): { x: number; y: number } {
    if (widgets.length === 0) {
        return { x: 0, y: 0 }
    }

    // Find the maximum y position
    const maxY = Math.max(...widgets.map(w => w.y + w.h))

    // Try to fit in existing rows first
    for (let y = 0; y <= maxY; y++) {
        for (let x = 0; x <= GRID_COLUMNS - newWidth; x++) {
            const wouldOverlap = widgets.some(w => {
                return !(
                    x + newWidth <= w.x ||
                    x >= w.x + w.w ||
                    y + newHeight <= w.y ||
                    y >= w.y + w.h
                )
            })

            if (!wouldOverlap) {
                return { x, y }
            }
        }
    }

    // If no space found, add to bottom
    return { x: 0, y: maxY }
}

// ==================== Store ====================

export const useDashboardStore = create<DashboardState>()(
    persist(
        (set, get) => ({
            widgets: DEFAULT_WIDGETS,
            activePreset: 'default',
            gridColumns: GRID_COLUMNS,
            compactMode: false,

            setWidgets: (widgets) => set({ widgets, activePreset: null }),

            addWidget: (type, size) => {
                const { widgets } = get()
                const defaultW = size?.w ?? 4
                const defaultH = size?.h ?? 3
                const { x, y } = calculateNextPosition(widgets, defaultW, defaultH)

                set({
                    widgets: [
                        ...widgets,
                        {
                            id: `${type.toLowerCase()}-${Date.now()}`,
                            type,
                            x,
                            y,
                            w: defaultW,
                            h: defaultH,
                        },
                    ],
                    activePreset: null,
                })
            },

            removeWidget: (id) =>
                set((state) => ({
                    widgets: state.widgets.filter((w) => w.id !== id),
                    activePreset: null,
                })),

            updateWidgetPosition: (id, x, y) =>
                set((state) => ({
                    widgets: state.widgets.map((w) =>
                        w.id === id ? { ...w, x, y } : w
                    ),
                    activePreset: null,
                })),

            updateWidgetSize: (id, w, h) =>
                set((state) => ({
                    widgets: state.widgets.map((widget) =>
                        widget.id === id
                            ? { ...widget, w: Math.max(2, Math.min(12, w)), h: Math.max(1, Math.min(6, h)) }
                            : widget
                    ),
                    activePreset: null,
                })),

            resetToDefault: () =>
                set({ widgets: DEFAULT_WIDGETS, activePreset: 'default' }),

            applyPreset: (presetId) => {
                const preset = DASHBOARD_PRESETS.find((p) => p.id === presetId)
                if (preset) {
                    set({ widgets: [...preset.widgets], activePreset: presetId })
                }
            },

            setCompactMode: (compact) => set({ compactMode: compact }),
        }),
        {
            name: 'dashboard-storage',
            version: 2, // Increment version to migrate old data
            migrate: (persistedState, version) => {
                // Default state for fallback
                const defaultState: DashboardState = {
                    widgets: DEFAULT_WIDGETS,
                    activePreset: 'default',
                    gridColumns: GRID_COLUMNS,
                    compactMode: false,
                    setWidgets: () => {},
                    addWidget: () => {},
                    removeWidget: () => {},
                    updateWidgetPosition: () => {},
                    updateWidgetSize: () => {},
                    resetToDefault: () => {},
                    applyPreset: () => {},
                    setCompactMode: () => {},
                }

                // Guard against null/undefined persisted state
                if (!persistedState || typeof persistedState !== 'object') {
                    logger.warn('[Dashboard Store] Invalid persisted state, using defaults')
                    return defaultState
                }

                const state = persistedState as Record<string, unknown>

                if (version < 2) {
                    // Migrate from old format without x, y, w, h
                    const widgets = state.widgets

                    // Validate widgets array
                    if (!Array.isArray(widgets)) {
                        logger.warn('[Dashboard Store] Invalid widgets during migration, using defaults')
                        return defaultState
                    }

                    // Migrate each widget with validation
                    const migratedWidgets: WidgetItem[] = widgets
                        .filter((w): w is { id: string; type: string } =>
                            w !== null &&
                            typeof w === 'object' &&
                            typeof (w as Record<string, unknown>).id === 'string' &&
                            typeof (w as Record<string, unknown>).type === 'string'
                        )
                        .map((w, index) => ({
                            id: w.id,
                            type: w.type,
                            x: (index % 3) * 4,
                            y: Math.floor(index / 3) * 3,
                            w: 4,
                            h: 3,
                        }))

                    // If no valid widgets could be migrated, use defaults
                    if (migratedWidgets.length === 0) {
                        logger.warn('[Dashboard Store] No valid widgets found during migration, using defaults')
                        return defaultState
                    }

                    return {
                        ...defaultState,
                        widgets: migratedWidgets,
                        activePreset: null,
                        compactMode: typeof state.compactMode === 'boolean' ? state.compactMode : false,
                    }
                }

                // For current version, validate the state structure
                const currentWidgets = state.widgets
                if (!Array.isArray(currentWidgets)) {
                    logger.warn('[Dashboard Store] Invalid widgets in current version, using defaults')
                    return defaultState
                }

                // Validate each widget has required fields
                const validWidgets = currentWidgets.filter((w): w is WidgetItem =>
                    w !== null &&
                    typeof w === 'object' &&
                    typeof (w as Record<string, unknown>).id === 'string' &&
                    typeof (w as Record<string, unknown>).type === 'string' &&
                    typeof (w as Record<string, unknown>).x === 'number' &&
                    typeof (w as Record<string, unknown>).y === 'number' &&
                    typeof (w as Record<string, unknown>).w === 'number' &&
                    typeof (w as Record<string, unknown>).h === 'number'
                )

                return {
                    ...defaultState,
                    widgets: validWidgets.length > 0 ? validWidgets : DEFAULT_WIDGETS,
                    activePreset: typeof state.activePreset === 'string' ? state.activePreset : 'default',
                    compactMode: typeof state.compactMode === 'boolean' ? state.compactMode : false,
                }
            },
        }
    )
)

export { GRID_COLUMNS }
