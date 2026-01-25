/**
 * ResizableWidget Component
 *
 * Widget wrapper with drag and resize capabilities.
 * Supports CSS Grid-based positioning with col-span and row-span.
 *
 * Phase 3.3 der Feature-Roadmap (Januar 2026)
 */

import { useState, useCallback, useRef, useEffect, type MouseEvent as ReactMouseEvent } from 'react'
import { GripVertical, X, Maximize2, Minimize2, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import { getWidgetLabel, getWidgetDefinition } from '../registry'
import type { WidgetItem } from '../stores/useDashboardStore'

// ==================== Constants ====================

const DEFAULT_GRID_CELL_WIDTH = 100
const DEFAULT_GRID_CELL_HEIGHT = 80
const MIN_WIDGET_WIDTH = 2
const MAX_WIDGET_WIDTH = 12
const MIN_WIDGET_HEIGHT = 1
const MAX_WIDGET_HEIGHT = 6

// ==================== Types ====================

interface ResizableWidgetProps {
    widget: WidgetItem
    children: React.ReactNode
    isEditMode: boolean
    onRemove?: (id: string) => void
    onResize?: (id: string, w: number, h: number) => void
    onDragStart?: (id: string, e: ReactMouseEvent<HTMLDivElement>) => void
    onConfig?: (id: string, type: string) => void
    gridCellWidth?: number
    gridCellHeight?: number
}

interface ResizeState {
    startX: number
    startY: number
    startW: number
    startH: number
}

// ==================== Component ====================

export function ResizableWidget({
    widget,
    children,
    isEditMode,
    onRemove,
    onResize,
    onDragStart,
    onConfig,
    gridCellWidth = DEFAULT_GRID_CELL_WIDTH,
    gridCellHeight = DEFAULT_GRID_CELL_HEIGHT,
}: ResizableWidgetProps) {
    const [showRemoveDialog, setShowRemoveDialog] = useState(false)
    const [isResizing, setIsResizing] = useState(false)
    const [isDragging, setIsDragging] = useState(false)
    const widgetRef = useRef<HTMLDivElement>(null)
    const resizeStartRef = useRef<ResizeState | null>(null)

    // Store event handlers in refs for cleanup
    const mouseMoveHandlerRef = useRef<((e: MouseEvent) => void) | null>(null)
    const mouseUpHandlerRef = useRef<(() => void) | null>(null)
    const dragMouseUpHandlerRef = useRef<(() => void) | null>(null)

    const widgetLabel = getWidgetLabel(widget.type)
    const widgetDef = getWidgetDefinition(widget.type)
    const minW = widgetDef?.minSize?.w ?? MIN_WIDGET_WIDTH
    const minH = widgetDef?.minSize?.h ?? MIN_WIDGET_HEIGHT

    // Cleanup event listeners on unmount
    useEffect(() => {
        return () => {
            if (mouseMoveHandlerRef.current) {
                document.removeEventListener('mousemove', mouseMoveHandlerRef.current)
            }
            if (mouseUpHandlerRef.current) {
                document.removeEventListener('mouseup', mouseUpHandlerRef.current)
            }
            if (dragMouseUpHandlerRef.current) {
                document.removeEventListener('mouseup', dragMouseUpHandlerRef.current)
            }
        }
    }, [])

    // Handle widget removal
    const handleRemove = useCallback(() => {
        setShowRemoveDialog(false)
        onRemove?.(widget.id)
    }, [widget.id, onRemove])

    // Handle resize start
    const handleResizeStart = useCallback((e: ReactMouseEvent<HTMLDivElement>) => {
        e.preventDefault()
        e.stopPropagation()
        setIsResizing(true)

        resizeStartRef.current = {
            startX: e.clientX,
            startY: e.clientY,
            startW: widget.w,
            startH: widget.h,
        }

        const handleMouseMove = (moveEvent: MouseEvent) => {
            if (!resizeStartRef.current) return

            const deltaX = moveEvent.clientX - resizeStartRef.current.startX
            const deltaY = moveEvent.clientY - resizeStartRef.current.startY

            const newW = Math.max(
                minW,
                Math.min(MAX_WIDGET_WIDTH, resizeStartRef.current.startW + Math.round(deltaX / gridCellWidth))
            )
            const newH = Math.max(
                minH,
                Math.min(MAX_WIDGET_HEIGHT, resizeStartRef.current.startH + Math.round(deltaY / gridCellHeight))
            )

            onResize?.(widget.id, newW, newH)
        }

        const handleMouseUp = () => {
            setIsResizing(false)
            resizeStartRef.current = null

            if (mouseMoveHandlerRef.current) {
                document.removeEventListener('mousemove', mouseMoveHandlerRef.current)
                mouseMoveHandlerRef.current = null
            }
            if (mouseUpHandlerRef.current) {
                document.removeEventListener('mouseup', mouseUpHandlerRef.current)
                mouseUpHandlerRef.current = null
            }
        }

        // Store handlers for cleanup
        mouseMoveHandlerRef.current = handleMouseMove
        mouseUpHandlerRef.current = handleMouseUp

        document.addEventListener('mousemove', handleMouseMove)
        document.addEventListener('mouseup', handleMouseUp)
    }, [widget.id, widget.w, widget.h, minW, minH, gridCellWidth, gridCellHeight, onResize])

    // Handle drag start
    const handleDragStart = useCallback((e: ReactMouseEvent<HTMLDivElement>) => {
        e.preventDefault()
        setIsDragging(true)
        onDragStart?.(widget.id, e)

        const handleMouseUp = () => {
            setIsDragging(false)
            if (dragMouseUpHandlerRef.current) {
                document.removeEventListener('mouseup', dragMouseUpHandlerRef.current)
                dragMouseUpHandlerRef.current = null
            }
        }

        // Store handler for cleanup
        dragMouseUpHandlerRef.current = handleMouseUp
        document.addEventListener('mouseup', handleMouseUp)
    }, [widget.id, onDragStart])

    // Quick size actions
    const handleExpand = useCallback(() => {
        const newW = Math.min(MAX_WIDGET_WIDTH, widget.w + 2)
        const newH = Math.min(MAX_WIDGET_HEIGHT, widget.h + 1)
        onResize?.(widget.id, newW, newH)
    }, [widget.id, widget.w, widget.h, onResize])

    const handleShrink = useCallback(() => {
        const newW = Math.max(minW, widget.w - 2)
        const newH = Math.max(minH, widget.h - 1)
        onResize?.(widget.id, newW, newH)
    }, [widget.id, widget.w, widget.h, minW, minH, onResize])

    // CSS Grid placement
    const gridStyle = {
        gridColumn: `span ${widget.w}`,
        gridRow: `span ${widget.h}`,
    }

    return (
        <>
            <div
                ref={widgetRef}
                style={gridStyle}
                className={cn(
                    'relative group min-h-[100px]',
                    isEditMode && 'transition-shadow duration-200',
                    isDragging && 'opacity-50 shadow-xl z-50',
                    isResizing && 'ring-2 ring-primary'
                )}
                role="article"
                aria-label={widgetLabel}
            >
                {isEditMode && (
                    <>
                        {/* Drag Handle */}
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div
                                        onMouseDown={handleDragStart}
                                        className={cn(
                                            'absolute -left-2 top-2 p-1.5 cursor-grab active:cursor-grabbing',
                                            'bg-background border rounded-md shadow-sm z-50',
                                            'opacity-0 group-hover:opacity-100 transition-opacity'
                                        )}
                                        role="button"
                                        tabIndex={0}
                                        aria-label="Widget verschieben"
                                    >
                                        <GripVertical className="w-4 h-4 text-muted-foreground" />
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent side="left">
                                    <p>Ziehen zum Verschieben</p>
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>

                        {/* Quick Actions Toolbar */}
                        <div
                            className={cn(
                                'absolute -top-2 right-6 flex items-center gap-1 z-50',
                                'opacity-0 group-hover:opacity-100 transition-opacity'
                            )}
                        >
                            {/* Shrink Button */}
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button
                                            variant="outline"
                                            size="icon"
                                            className="h-6 w-6 bg-background"
                                            onClick={handleShrink}
                                            disabled={widget.w <= minW && widget.h <= minH}
                                            aria-label="Widget verkleinern"
                                        >
                                            <Minimize2 className="h-3 w-3" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p>Verkleinern</p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>

                            {/* Expand Button */}
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button
                                            variant="outline"
                                            size="icon"
                                            className="h-6 w-6 bg-background"
                                            onClick={handleExpand}
                                            disabled={widget.w >= MAX_WIDGET_WIDTH && widget.h >= MAX_WIDGET_HEIGHT}
                                            aria-label="Widget vergroessern"
                                        >
                                            <Maximize2 className="h-3 w-3" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p>Vergroessern</p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>

                            {/* Config Button */}
                            {onConfig && (
                                <TooltipProvider>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <Button
                                                variant="outline"
                                                size="icon"
                                                className="h-6 w-6 bg-background"
                                                onClick={() => onConfig(widget.id, widget.type)}
                                                aria-label="Widget konfigurieren"
                                            >
                                                <Settings className="h-3 w-3" />
                                            </Button>
                                        </TooltipTrigger>
                                        <TooltipContent>
                                            <p>Einstellungen</p>
                                        </TooltipContent>
                                    </Tooltip>
                                </TooltipProvider>
                            )}
                        </div>

                        {/* Remove Button */}
                        <Button
                            variant="destructive"
                            size="icon"
                            className={cn(
                                'absolute -top-2 -right-2 h-6 w-6 rounded-full z-50',
                                'opacity-0 group-hover:opacity-100 transition-opacity'
                            )}
                            onClick={() => setShowRemoveDialog(true)}
                            aria-label="Widget entfernen"
                        >
                            <X className="h-3.5 w-3.5" />
                        </Button>

                        {/* Resize Handle */}
                        <div
                            onMouseDown={handleResizeStart}
                            className={cn(
                                'absolute bottom-1 right-1 w-4 h-4 cursor-se-resize z-50',
                                'opacity-0 group-hover:opacity-100 transition-opacity',
                                'after:absolute after:bottom-0 after:right-0',
                                'after:w-0 after:h-0',
                                'after:border-8 after:border-transparent after:border-r-primary/50 after:border-b-primary/50'
                            )}
                            role="button"
                            tabIndex={0}
                            aria-label="Groesse aendern"
                        />

                        {/* Size Indicator */}
                        <div
                            className={cn(
                                'absolute bottom-1 left-1 px-1.5 py-0.5 text-[10px] font-mono',
                                'bg-background/80 border rounded text-muted-foreground',
                                'opacity-0 group-hover:opacity-100 transition-opacity'
                            )}
                            aria-hidden="true"
                        >
                            {widget.w}x{widget.h}
                        </div>

                        {/* Edit Mode Border */}
                        <div className="absolute inset-0 border-2 border-dashed border-primary/20 pointer-events-none rounded-xl" />
                    </>
                )}

                {/* Widget Content */}
                {children}
            </div>

            {/* Remove Confirmation Dialog */}
            <AlertDialog open={showRemoveDialog} onOpenChange={setShowRemoveDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Widget entfernen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Moechten Sie das Widget &quot;{widgetLabel}&quot; wirklich vom Dashboard entfernen?
                            Sie koennen es jederzeit ueber den Widget-Katalog wieder hinzufuegen.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleRemove}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                            Entfernen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}

export default ResizableWidget
