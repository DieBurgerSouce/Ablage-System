/**
 * DraggableWidget - Enhanced Widget with Drag Preview
 *
 * Phase 2.2: Drag & Drop überall
 *
 * Features:
 * - Erweitert SortableWidget mit besserem Drag-Preview
 * - Custom Drag Overlay mit Widget-Vorschau
 * - Smooth Animations beim Neuordnen
 * - Collision Detection optimiert
 */

import { forwardRef, useMemo } from "react"
import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { GripVertical, X, Settings, Maximize2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { getWidgetLabel, getWidgetIcon } from "../registry"
import type { WidgetDragData } from "@/hooks/useDragAndDrop"

// =============================================================================
// Types
// =============================================================================

export interface WidgetData {
  id: string
  type: string
  title?: string
  config?: Record<string, unknown>
  size?: "small" | "medium" | "large" | "full"
}

export interface DraggableWidgetProps {
  /** Widget-Daten */
  widget: WidgetData
  /** Widget-Inhalt */
  children: React.ReactNode
  /** Edit-Modus aktiv */
  isEditMode: boolean
  /** Widget ist aktuell gezogen */
  isDragOverlay?: boolean
  /** Entfernen-Handler */
  onRemove?: (id: string) => void
  /** Konfiguration öffnen */
  onConfigure?: (id: string) => void
  /** Maximieren */
  onMaximize?: (id: string) => void
  /** Zusätzliche CSS-Klassen */
  className?: string
}

// =============================================================================
// Component
// =============================================================================

export const DraggableWidget = forwardRef<HTMLDivElement, DraggableWidgetProps>(
  function DraggableWidget(
    {
      widget,
      children,
      isEditMode,
      isDragOverlay = false,
      onRemove,
      onConfigure,
      onMaximize,
      className,
    },
    ref
  ) {
    // Drag-Daten
    const dragData: WidgetDragData = useMemo(
      () => ({
        widgetId: widget.id,
        widgetType: widget.type,
        order: 0, // Wird von SortableContext verwaltet
      }),
      [widget.id, widget.type]
    )

    // @dnd-kit Sortable Hook
    const {
      attributes,
      listeners,
      setNodeRef,
      transform,
      transition,
      isDragging,
      isOver,
    } = useSortable({
      id: widget.id,
      data: { ...dragData, type: "widget" },
      disabled: !isEditMode,
    })

    // Transform Style
    const style = useMemo(
      () => ({
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 50 : "auto",
      }),
      [transform, transition, isDragging]
    )

    // Widget Label und Icon
    const label = getWidgetLabel(widget.type)
    const Icon = getWidgetIcon(widget.type)

    // Wenn Drag Overlay, vereinfachte Darstellung
    if (isDragOverlay) {
      return (
        <div
          className={cn(
            "bg-background border rounded-xl shadow-2xl p-4",
            "transform scale-105 rotate-2",
            "min-w-[200px] max-w-[300px]",
            className
          )}
        >
          <div className="flex items-center gap-2 mb-2">
            {Icon && <Icon className="h-5 w-5 text-primary" />}
            <span className="font-medium text-sm">{widget.title || label}</span>
          </div>
          <div className="h-24 bg-muted/50 rounded-lg flex items-center justify-center text-muted-foreground text-sm">
            Widget-Vorschau
          </div>
        </div>
      )
    }

    return (
      <div
        ref={(node) => {
          setNodeRef(node)
          if (typeof ref === "function") {
            ref(node)
          } else if (ref) {
            ref.current = node
          }
        }}
        style={style}
        className={cn(
          "relative group min-h-[100px]",
          isEditMode && "cursor-move",
          isDragging && "cursor-grabbing",
          isOver && isEditMode && "ring-2 ring-primary ring-dashed",
          className
        )}
      >
        {/* Edit Mode Controls */}
        {isEditMode && (
          <TooltipProvider delayDuration={300}>
            <div
              className={cn(
                "absolute -top-3 left-1/2 -translate-x-1/2 z-50",
                "flex items-center gap-1 px-2 py-1",
                "bg-background border rounded-full shadow-sm",
                "opacity-0 group-hover:opacity-100 transition-opacity"
              )}
            >
              {/* Drag Handle */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    {...attributes}
                    {...listeners}
                    className={cn(
                      "p-1 rounded hover:bg-muted cursor-grab active:cursor-grabbing",
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    )}
                    aria-label="Widget verschieben"
                  >
                    <GripVertical className="h-4 w-4 text-muted-foreground" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">
                  <p>Ziehen zum Verschieben</p>
                </TooltipContent>
              </Tooltip>

              {/* Configure Button */}
              {onConfigure && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onConfigure(widget.id)}
                      className="p-1 rounded hover:bg-muted"
                      aria-label="Widget konfigurieren"
                    >
                      <Settings className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>Konfigurieren</p>
                  </TooltipContent>
                </Tooltip>
              )}

              {/* Maximize Button */}
              {onMaximize && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onMaximize(widget.id)}
                      className="p-1 rounded hover:bg-muted"
                      aria-label="Widget maximieren"
                    >
                      <Maximize2 className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>Maximieren</p>
                  </TooltipContent>
                </Tooltip>
              )}

              {/* Remove Button */}
              {onRemove && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onRemove(widget.id)}
                      className="p-1 rounded hover:bg-destructive/10"
                      aria-label="Widget entfernen"
                    >
                      <X className="h-4 w-4 text-destructive" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>Entfernen</p>
                  </TooltipContent>
                </Tooltip>
              )}
            </div>

            {/* Edit Mode Border */}
            <div
              className={cn(
                "absolute inset-0 rounded-xl pointer-events-none",
                "border-2 border-dashed",
                isDragging ? "border-primary" : "border-primary/20"
              )}
            />
          </TooltipProvider>
        )}

        {/* Widget Content */}
        <div className="h-full">{children}</div>
      </div>
    )
  }
)

// =============================================================================
// Widget Drag Overlay - Für DragOverlay in DndContext
// =============================================================================

export interface WidgetDragOverlayProps {
  widget: WidgetData
}

export function WidgetDragOverlay({ widget }: WidgetDragOverlayProps) {
  const label = getWidgetLabel(widget.type)
  const Icon = getWidgetIcon(widget.type)

  return (
    <div
      className={cn(
        "bg-background border-2 border-primary rounded-xl shadow-2xl p-4",
        "transform rotate-2 scale-105",
        "min-w-[250px] max-w-[350px]",
        "animate-in zoom-in-95 duration-200"
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 bg-primary/10 rounded-lg">
          {Icon && <Icon className="h-5 w-5 text-primary" />}
        </div>
        <div>
          <h4 className="font-medium text-sm">{widget.title || label}</h4>
          <p className="text-xs text-muted-foreground">{widget.type}</p>
        </div>
      </div>

      {/* Preview Area */}
      <div className="h-32 bg-muted/50 rounded-lg flex items-center justify-center">
        <div className="text-center text-muted-foreground">
          <GripVertical className="h-8 w-8 mx-auto mb-1 opacity-50" />
          <span className="text-xs">Widget verschieben...</span>
        </div>
      </div>

      {/* Size Indicator */}
      {widget.size && (
        <div className="mt-2 text-xs text-muted-foreground text-center">
          Größe: {widget.size}
        </div>
      )}
    </div>
  )
}

export default DraggableWidget
