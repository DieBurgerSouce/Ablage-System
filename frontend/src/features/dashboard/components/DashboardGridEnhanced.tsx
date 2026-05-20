/**
 * DashboardGridEnhanced Component
 *
 * Enhanced dashboard grid with:
 * - CSS Grid-based layout with col-span and row-span
 * - Resizable widgets
 * - Role-based presets
 * - Responsive design
 *
 * Phase 3.3 der Feature-Roadmap (Januar 2026)
 */

import { useState, useCallback, useMemo, useRef, useEffect, type MouseEvent } from 'react'
import { useDashboardStore, DASHBOARD_PRESETS, GRID_COLUMNS } from '../stores/useDashboardStore'
import { getWidgetComponent, getWidgetDefinition } from '../registry'
import { ResizableWidget } from './ResizableWidget'
import { WidgetCatalogDrawer } from './WidgetCatalogDrawer'
import { WidgetConfigModal } from './WidgetConfigModal'
import { WidgetSyncStatus } from './WidgetSyncStatus'
import { DashboardDateRangePicker } from './DashboardDateRangePicker'
import { DateRangeProvider } from '../hooks/useDateRange'
import { useWidgetConfig, type WidgetSettings } from '../hooks/useWidgetConfig'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import {
    Settings2,
    RotateCcw,
    Plus,
    LayoutGrid,
    Check,
    Grid3X3,
    Shrink,
    User,
    Calculator,
    Users,
    Shield,
    Layers,
    Settings,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

// ==================== Types ====================

type UserRole = 'admin' | 'accountant' | 'manager' | 'user'

const ROLE_ICONS: Record<UserRole, React.ReactNode> = {
    user: <User className="h-4 w-4" />,
    accountant: <Calculator className="h-4 w-4" />,
    manager: <Users className="h-4 w-4" />,
    admin: <Shield className="h-4 w-4" />,
}

// ==================== Component ====================

export function DashboardGridEnhanced() {
    const {
        widgets,
        activePreset,
        compactMode,
        removeWidget,
        updateWidgetSize,
        // updateWidgetPosition - reserved for future drag-and-drop implementation
        resetToDefault,
        applyPreset,
        setCompactMode,
    } = useDashboardStore()

    const [isEditMode, setIsEditMode] = useState(false)
    const [showCatalog, setShowCatalog] = useState(false)
    const [gridCellWidth, setGridCellWidth] = useState(100) // Default until measured
    const [configWidget, setConfigWidget] = useState<{ id: string; type: string } | null>(null)
    const gridRef = useRef<HTMLDivElement>(null)

    // Server sync hook
    const {
        isLoading: isSyncLoading,
        isSyncing,
        lastSynced,
        error: syncError,
        syncNow,
        updateWidgetSettings,
        getWidgetSettings,
    } = useWidgetConfig({ autoSync: true, debounceMs: 1500 })

    // Fixed row height constant
    const GRID_CELL_HEIGHT = 80

    // Use ResizeObserver to calculate grid dimensions dynamically
    useEffect(() => {
        const gridElement = gridRef.current
        if (!gridElement) return

        const calculateCellWidth = () => {
            const width = gridElement.clientWidth
            if (width > 0) {
                setGridCellWidth(width / GRID_COLUMNS)
            }
        }

        // Initial calculation
        calculateCellWidth()

        // Create ResizeObserver for responsive updates
        const resizeObserver = new ResizeObserver((entries) => {
            // Use requestAnimationFrame to avoid ResizeObserver loop error
            window.requestAnimationFrame(() => {
                if (entries.length > 0) {
                    calculateCellWidth()
                }
            })
        })

        resizeObserver.observe(gridElement)

        return () => {
            resizeObserver.disconnect()
        }
    }, [])

    // Handle widget removal
    const handleRemoveWidget = useCallback((id: string) => {
        removeWidget(id)
        toast.success('Widget entfernt', {
            description: 'Das Widget wurde vom Dashboard entfernt.',
        })
    }, [removeWidget])

    // Handle widget resize
    const handleResize = useCallback((id: string, w: number, h: number) => {
        updateWidgetSize(id, w, h)
    }, [updateWidgetSize])

    // Handle widget drag (simplified - just log for now)
    const handleDragStart = useCallback((_id: string, _e: MouseEvent) => {
        // In a full implementation, this would handle drag-and-drop repositioning
        // For now, widgets maintain their grid positions
    }, [])

    // Handle preset selection
    const handlePresetSelect = useCallback((presetId: string) => {
        applyPreset(presetId)
        toast.success('Layout angewendet', {
            description: `Das "${DASHBOARD_PRESETS.find(p => p.id === presetId)?.name}" Layout wurde angewendet.`,
        })
    }, [applyPreset])

    // Handle reset
    const handleReset = useCallback(() => {
        resetToDefault()
        toast.success('Dashboard zurückgesetzt', {
            description: 'Das Dashboard wurde auf die Standardansicht zurückgesetzt.',
        })
    }, [resetToDefault])

    // Handle widget config
    const handleConfigWidget = useCallback((id: string, type: string) => {
        setConfigWidget({ id, type })
    }, [])

    // Handle widget settings save
    const handleSaveWidgetSettings = useCallback(async (settings: WidgetSettings) => {
        if (configWidget) {
            try {
                await updateWidgetSettings(configWidget.id, settings)
                toast.success('Einstellungen gespeichert', {
                    description: 'Die Widget-Einstellungen wurden aktualisiert.',
                })
            } catch (error) {
                toast.error('Fehler beim Speichern', {
                    description: 'Die Einstellungen konnten nicht gespeichert werden.',
                })
                throw error
            }
        }
    }, [configWidget, updateWidgetSettings])

    // Sort widgets by position for proper grid ordering
    const sortedWidgets = useMemo(() => {
        return [...widgets].sort((a, b) => {
            if (a.y !== b.y) return a.y - b.y
            return a.x - b.x
        })
    }, [widgets])

    // Calculate max row for grid height
    const maxRow = useMemo(() => {
        return Math.max(...widgets.map(w => w.y + w.h), 1)
    }, [widgets])

    return (
        <DateRangeProvider>
        <div className="space-y-4" role="region" aria-label="Dashboard">
            {/* Toolbar */}
            <div
                className="flex flex-wrap items-center justify-between gap-2 mb-4"
                role="toolbar"
                aria-label="Dashboard-Aktionen"
            >
                {/* Left side - Edit mode actions */}
                <div className="flex items-center gap-2">
                    {isEditMode && (
                        <>
                            {/* Add Widget Button */}
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setShowCatalog(true)}
                                aria-label="Neues Widget zum Dashboard hinzufügen"
                            >
                                <Plus className="w-4 h-4 mr-2" aria-hidden="true" />
                                Widget hinzufügen
                            </Button>

                            {/* Preset Selector */}
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button variant="outline" size="sm">
                                        <Layers className="w-4 h-4 mr-2" aria-hidden="true" />
                                        Vorlagen
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="start" className="w-56">
                                    <DropdownMenuLabel>Layout-Vorlagen</DropdownMenuLabel>
                                    <DropdownMenuSeparator />
                                    {DASHBOARD_PRESETS.map((preset) => (
                                        <DropdownMenuItem
                                            key={preset.id}
                                            onClick={() => handlePresetSelect(preset.id)}
                                            className="flex items-center gap-2"
                                        >
                                            {ROLE_ICONS[preset.role]}
                                            <div className="flex-1">
                                                <p className="font-medium">{preset.name}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {preset.description}
                                                </p>
                                            </div>
                                            {activePreset === preset.id && (
                                                <Check className="w-4 h-4 text-primary" />
                                            )}
                                        </DropdownMenuItem>
                                    ))}
                                </DropdownMenuContent>
                            </DropdownMenu>

                            {/* Compact Mode Toggle */}
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button
                                            variant={compactMode ? 'secondary' : 'outline'}
                                            size="sm"
                                            onClick={() => setCompactMode(!compactMode)}
                                            aria-pressed={compactMode}
                                        >
                                            <Shrink className="w-4 h-4" aria-hidden="true" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p>{compactMode ? 'Kompaktmodus deaktivieren' : 'Kompaktmodus aktivieren'}</p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>

                            {/* Reset Button */}
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleReset}
                                aria-label="Dashboard auf Standardansicht zurücksetzen"
                            >
                                <RotateCcw className="w-4 h-4 mr-2" aria-hidden="true" />
                                Reset
                            </Button>
                        </>
                    )}
                </div>

                {/* Right side - Edit mode toggle */}
                <div className="flex items-center gap-2">
                    {/* Grid info in edit mode */}
                    {isEditMode && (
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground bg-muted rounded">
                                        <Grid3X3 className="w-3 h-3" />
                                        <span>{GRID_COLUMNS} Spalten</span>
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent>
                                    <p>Dashboard verwendet ein {GRID_COLUMNS}-Spalten-Raster</p>
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    )}

                    {/* Date Range Picker (Phase C) */}
                    <DashboardDateRangePicker />

                    {/* Sync Status */}
                    <WidgetSyncStatus
                        isLoading={isSyncLoading}
                        isSyncing={isSyncing}
                        lastSynced={lastSynced}
                        error={syncError}
                        onSync={syncNow}
                    />

                    {/* Active Preset Badge */}
                    {activePreset && !isEditMode && (
                        <div className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground bg-muted rounded">
                            <LayoutGrid className="w-3 h-3" />
                            <span>{DASHBOARD_PRESETS.find(p => p.id === activePreset)?.name}</span>
                        </div>
                    )}

                    {/* Edit Mode Toggle */}
                    <Button
                        variant={isEditMode ? 'secondary' : 'ghost'}
                        size="sm"
                        onClick={() => setIsEditMode(!isEditMode)}
                        aria-pressed={isEditMode}
                        aria-label={isEditMode ? 'Bearbeitungsmodus beenden und Ansicht speichern' : 'Dashboard-Layout anpassen'}
                    >
                        <Settings2 className="w-4 h-4 mr-2" aria-hidden="true" />
                        {isEditMode ? 'Fertig' : 'Anpassen'}
                    </Button>
                </div>
            </div>

            {/* Grid Container */}
            <div
                ref={gridRef}
                data-tour="dashboard-widgets"
                className={cn(
                    'grid gap-4',
                    compactMode ? 'gap-2' : 'gap-4',
                    // Responsive columns: 1 on mobile, 2 on tablet, full grid on desktop
                    'grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-12'
                )}
                style={{
                    gridTemplateRows: `repeat(${maxRow}, minmax(${compactMode ? 60 : 80}px, auto))`,
                }}
                role="list"
                aria-label="Dashboard-Widgets"
            >
                {sortedWidgets.map((widget) => {
                    const Component = getWidgetComponent(widget.type)
                    const widgetDef = getWidgetDefinition(widget.type)

                    return (
                        <ResizableWidget
                            key={widget.id}
                            widget={widget}
                            isEditMode={isEditMode}
                            onRemove={handleRemoveWidget}
                            onResize={handleResize}
                            onDragStart={handleDragStart}
                            onConfig={handleConfigWidget}
                            gridCellWidth={gridCellWidth}
                            gridCellHeight={GRID_CELL_HEIGHT}
                        >
                            <div
                                className={cn(
                                    'h-full rounded-xl border bg-card text-card-foreground shadow',
                                    compactMode && 'p-2'
                                )}
                                role="listitem"
                                aria-label={widgetDef?.label || widget.type}
                            >
                                <Component />
                            </div>
                        </ResizableWidget>
                    )
                })}
            </div>

            {/* Empty State */}
            {widgets.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <LayoutGrid className="w-12 h-12 text-muted-foreground mb-4" />
                    <h3 className="text-lg font-semibold mb-2">Keine Widgets</h3>
                    <p className="text-muted-foreground mb-4">
                        Fügen Sie Widgets hinzu, um Ihr Dashboard zu personalisieren.
                    </p>
                    <Button onClick={() => { setIsEditMode(true); setShowCatalog(true); }}>
                        <Plus className="w-4 h-4 mr-2" />
                        Widgets hinzufügen
                    </Button>
                </div>
            )}

            {/* Widget Catalog Drawer */}
            <WidgetCatalogDrawer open={showCatalog} onOpenChange={setShowCatalog} />

            {/* Widget Config Modal */}
            <WidgetConfigModal
                isOpen={configWidget !== null}
                onClose={() => setConfigWidget(null)}
                widgetId={configWidget?.id || ''}
                widgetType={configWidget?.type || ''}
                currentSettings={configWidget ? getWidgetSettings(configWidget.id) : undefined}
                onSave={handleSaveWidgetSettings}
                isSaving={false}
            />
        </div>
        </DateRangeProvider>
    )
}

export default DashboardGridEnhanced
