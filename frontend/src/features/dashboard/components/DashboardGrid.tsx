import { useState, useCallback } from 'react'
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    TouchSensor,
    useSensor,
    useSensors,
    DragOverlay,
    type DragEndEvent,
    type DragStartEvent,
} from '@dnd-kit/core'
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    rectSortingStrategy,
} from '@dnd-kit/sortable'
import { useDashboardStore } from '../stores/useDashboardStore'
import { getWidgetComponent, getWidgetLabel } from '../registry'
import { DraggableWidget, WidgetDragOverlay } from './DraggableWidget'
import { WidgetCatalogDrawer } from './WidgetCatalogDrawer'
import { WidgetConfigDialog } from './WidgetConfigDialog'
import { WidgetMaximizeDialog } from './WidgetMaximizeDialog'
import { Button } from '@/components/ui/button'
import { Settings2, RotateCcw, Plus } from 'lucide-react'
import { toast } from 'sonner'

export function DashboardGrid() {
    const { widgets, setWidgets, removeWidget, resetToDefault } = useDashboardStore()
    const [isEditMode, setIsEditMode] = useState(false)
    const [showCatalog, setShowCatalog] = useState(false)
    const [activeId, setActiveId] = useState<string | null>(null)
    const [configWidgetId, setConfigWidgetId] = useState<string | null>(null)
    const [maximizeWidgetId, setMaximizeWidgetId] = useState<string | null>(null)

    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: { distance: 5 } // Start drag after 5px movement
        }),
        useSensor(TouchSensor, {
            activationConstraint: { delay: 250, tolerance: 5 }, // Press for 250ms to drag on touch
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    )

    function handleDragStart(event: DragStartEvent) {
        setActiveId(event.active.id as string)
    }

    function handleDragEnd(event: DragEndEvent) {
        const { active, over } = event

        if (over && active.id !== over.id) {
            const oldIndex = widgets.findIndex((w) => w.id === active.id)
            const newIndex = widgets.findIndex((w) => w.id === over.id)
            setWidgets(arrayMove(widgets, oldIndex, newIndex))
        }
        setActiveId(null)
    }

    const handleRemoveWidget = useCallback((id: string) => {
        removeWidget(id)
        toast.success('Widget entfernt', {
            description: 'Das Widget wurde vom Dashboard entfernt.',
        })
    }, [removeWidget])

    const handleConfigureWidget = useCallback((id: string) => {
        setConfigWidgetId(id)
    }, [])

    const handleMaximizeWidget = useCallback((id: string) => {
        setMaximizeWidgetId(id)
    }, [])

    // Aktives Widget für Drag Overlay
    const activeWidget = activeId ? widgets.find((w) => w.id === activeId) : null

    return (
        <div className="space-y-4" role="region" aria-label="Dashboard">
            <div className="flex justify-end gap-2 mb-4" role="toolbar" aria-label="Dashboard-Aktionen">
                {isEditMode && (
                    <>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowCatalog(true)}
                            aria-label="Neues Widget zum Dashboard hinzufügen"
                        >
                            <Plus className="w-4 h-4 mr-2" aria-hidden="true" />
                            Widget hinzufügen
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={resetToDefault}
                            aria-label="Dashboard auf Standardansicht zurücksetzen"
                        >
                            <RotateCcw className="w-4 h-4 mr-2" aria-hidden="true" />
                            Reset
                        </Button>
                    </>
                )}
                <Button
                    variant={isEditMode ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setIsEditMode(!isEditMode)}
                    aria-pressed={isEditMode}
                    aria-label={isEditMode ? 'Bearbeitungsmodus beenden und Ansicht speichern' : 'Dashboard-Layout anpassen'}
                >
                    <Settings2 className="w-4 h-4 mr-2" aria-hidden="true" />
                    {isEditMode ? 'Ansicht speichern' : 'Dashboard anpassen'}
                </Button>
            </div>

            <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
            >
                <SortableContext
                    items={widgets.map(w => w.id)}
                    strategy={rectSortingStrategy}
                >
                    <div
                        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                        role="list"
                        aria-label="Dashboard-Widgets"
                    >
                        {widgets.map((widget) => {
                            const Component = getWidgetComponent(widget.type)
                            return (
                                <DraggableWidget
                                    key={widget.id}
                                    widget={{
                                        id: widget.id,
                                        type: widget.type,
                                        title: getWidgetLabel(widget.type),
                                    }}
                                    isEditMode={isEditMode}
                                    onRemove={handleRemoveWidget}
                                    onConfigure={handleConfigureWidget}
                                    onMaximize={handleMaximizeWidget}
                                >
                                    <Component />
                                </DraggableWidget>
                            )
                        })}
                    </div>
                </SortableContext>

                {/* Drag Overlay - Widget-Vorschau beim Ziehen */}
                <DragOverlay>
                    {activeWidget && (
                        <WidgetDragOverlay
                            widget={{
                                id: activeWidget.id,
                                type: activeWidget.type,
                                title: getWidgetLabel(activeWidget.type),
                            }}
                        />
                    )}
                </DragOverlay>
            </DndContext>

            {/* Widget Catalog Drawer */}
            <WidgetCatalogDrawer open={showCatalog} onOpenChange={setShowCatalog} />

            {/* Widget Konfiguration Dialog */}
            <WidgetConfigDialog
                open={configWidgetId !== null}
                onOpenChange={(open) => { if (!open) setConfigWidgetId(null) }}
                widgetId={configWidgetId}
            />

            {/* Widget Maximierung Dialog */}
            <WidgetMaximizeDialog
                open={maximizeWidgetId !== null}
                onOpenChange={(open) => { if (!open) setMaximizeWidgetId(null) }}
                widgetId={maximizeWidgetId}
            />
        </div>
    )
}
