/**
 * BulkDropZone - Drop-Zone für Bulk-Operationen
 *
 * Phase 2.2/2.3: Drag & Drop + Bulk Actions
 *
 * Features:
 * - Akzeptiert mehrere gedropte Dokumente
 * - Zeigt verfügbare Aktionen als Drop-Targets
 * - Visuelles Feedback bei Hover
 * - Integration mit BulkActionBar
 */

import { useMemo, useCallback } from "react"
import { useDroppable } from "@dnd-kit/core"
import { FolderInput, Tag, Download, Trash2, Archive } from "lucide-react"
import { cn } from "@/lib/utils"
import type { DropTarget, DragItem, DocumentDragData } from "@/hooks/useDragAndDrop"
import type { BulkAction } from "./BulkActionBar"

// =============================================================================
// Types
// =============================================================================

export interface BulkDropAction {
  id: BulkAction
  label: string
  icon: React.ReactNode
  description: string
  variant?: "default" | "destructive"
}

export interface BulkDropZoneProps {
  /** Verfügbare Aktionen */
  actions?: BulkDropAction[]
  /** Callback bei Drop auf Aktion */
  onDropAction?: (action: BulkAction, documentIds: string[]) => void
  /** Drop-Zone deaktiviert */
  disabled?: boolean
  /** Zusätzliche CSS-Klassen */
  className?: string
  /** Ist die Zone sichtbar */
  visible?: boolean
  /** Position */
  position?: "bottom" | "right" | "top"
}

// =============================================================================
// Default Actions
// =============================================================================

const DEFAULT_DROP_ACTIONS: BulkDropAction[] = [
  {
    id: "move",
    label: "Verschieben",
    icon: <FolderInput className="h-6 w-6" />,
    description: "In Ordner verschieben",
  },
  {
    id: "tag",
    label: "Taggen",
    icon: <Tag className="h-6 w-6" />,
    description: "Tags hinzufügen",
  },
  {
    id: "export",
    label: "Exportieren",
    icon: <Download className="h-6 w-6" />,
    description: "Als ZIP herunterladen",
  },
  {
    id: "archive",
    label: "Archivieren",
    icon: <Archive className="h-6 w-6" />,
    description: "Dokumente archivieren",
  },
  {
    id: "delete",
    label: "Löschen",
    icon: <Trash2 className="h-6 w-6" />,
    description: "In Papierkorb verschieben",
    variant: "destructive",
  },
]

// =============================================================================
// Single Action Drop Target
// =============================================================================

interface ActionDropTargetProps {
  action: BulkDropAction
  onDrop: (action: BulkAction, documentIds: string[]) => void
  disabled?: boolean
}

function ActionDropTarget({ action, onDrop, disabled }: ActionDropTargetProps) {
  const dropTargetData: DropTarget = useMemo(
    () => ({
      id: `bulk-action-${action.id}`,
      type: "custom",
      accepts: ["document"],
    }),
    [action.id]
  )

  const { isOver, setNodeRef, active } = useDroppable({
    id: `bulk-action-${action.id}`,
    data: dropTargetData,
    disabled,
  })

  // Dokumente aus dem Drag-Item extrahieren
  const handleDrop = useCallback(() => {
    if (!active) return

    const dragItem = active.data.current as DragItem<DocumentDragData> | undefined
    if (!dragItem) return

    // Multi-Select oder einzelnes Dokument
    const documentIds = dragItem.selectedIds?.length
      ? (dragItem.selectedIds as string[])
      : [String(dragItem.id)]

    onDrop(action.id, documentIds)
  }, [active, action.id, onDrop])

  // Drop wurde ausgeführt (via DragEnd im Parent)
  // Hier nur visuelles Feedback

  const isDestructive = action.variant === "destructive"

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex flex-col items-center justify-center p-4 rounded-xl",
        "border-2 border-dashed transition-all duration-200",
        "min-w-[100px]",

        // Normal State
        !isOver && [
          "bg-background border-muted-foreground/20",
          "hover:border-muted-foreground/40 hover:bg-muted/50",
        ],

        // Hover State
        isOver && !isDestructive && [
          "bg-primary/10 border-primary",
          "scale-105 shadow-lg",
        ],

        // Hover State (Destructive)
        isOver && isDestructive && [
          "bg-destructive/10 border-destructive",
          "scale-105 shadow-lg",
        ],

        // Disabled
        disabled && "opacity-50 cursor-not-allowed"
      )}
      onClick={handleDrop}
      aria-label={`${action.label}: ${action.description}`}
    >
      {/* Icon */}
      <div
        className={cn(
          "mb-2 transition-colors duration-200",
          isOver && !isDestructive && "text-primary",
          isOver && isDestructive && "text-destructive",
          !isOver && "text-muted-foreground"
        )}
      >
        {action.icon}
      </div>

      {/* Label */}
      <span
        className={cn(
          "text-sm font-medium transition-colors duration-200",
          isOver && !isDestructive && "text-primary",
          isOver && isDestructive && "text-destructive"
        )}
      >
        {action.label}
      </span>

      {/* Description (bei Hover) */}
      {isOver && (
        <span className="text-xs text-muted-foreground mt-1 text-center animate-in fade-in-0 duration-200">
          {action.description}
        </span>
      )}
    </div>
  )
}

// =============================================================================
// Main Component
// =============================================================================

export function BulkDropZone({
  actions = DEFAULT_DROP_ACTIONS,
  onDropAction,
  disabled = false,
  className,
  visible = true,
  position = "bottom",
}: BulkDropZoneProps) {
  const handleDropAction = useCallback(
    (action: BulkAction, documentIds: string[]) => {
      onDropAction?.(action, documentIds)
    },
    [onDropAction]
  )

  if (!visible) return null

  return (
    <div
      className={cn(
        // Position
        position === "bottom" && "fixed bottom-20 left-1/2 -translate-x-1/2",
        position === "right" && "fixed right-4 top-1/2 -translate-y-1/2",
        position === "top" && "fixed top-20 left-1/2 -translate-x-1/2",

        // Container
        "z-40 p-4 bg-background/95 backdrop-blur-sm",
        "border rounded-2xl shadow-xl",
        "animate-in slide-in-from-bottom-4 fade-in-0 duration-300",

        className
      )}
      role="toolbar"
      aria-label="Bulk-Aktionen Drop-Zone"
    >
      {/* Header */}
      <div className="text-center mb-3">
        <p className="text-sm font-medium text-muted-foreground">
          Dokumente hierher ziehen
        </p>
      </div>

      {/* Action Targets */}
      <div
        className={cn(
          "flex gap-3",
          position === "right" && "flex-col"
        )}
      >
        {actions.map((action) => (
          <ActionDropTarget
            key={action.id}
            action={action}
            onDrop={handleDropAction}
            disabled={disabled}
          />
        ))}
      </div>
    </div>
  )
}

// =============================================================================
// Compact BulkDropZone - Für Sidebar
// =============================================================================

export interface CompactBulkDropZoneProps {
  onDropAction?: (action: BulkAction, documentIds: string[]) => void
  disabled?: boolean
  className?: string
}

export function CompactBulkDropZone({
  onDropAction,
  disabled = false,
  className,
}: CompactBulkDropZoneProps) {
  const actions: BulkDropAction[] = [
    {
      id: "delete",
      label: "Löschen",
      icon: <Trash2 className="h-5 w-5" />,
      description: "In Papierkorb",
      variant: "destructive",
    },
    {
      id: "archive",
      label: "Archiv",
      icon: <Archive className="h-5 w-5" />,
      description: "Archivieren",
    },
  ]

  const handleDropAction = useCallback(
    (action: BulkAction, documentIds: string[]) => {
      onDropAction?.(action, documentIds)
    },
    [onDropAction]
  )

  return (
    <div
      className={cn(
        "flex flex-col gap-2 p-2",
        "border-t mt-auto",
        className
      )}
    >
      <p className="text-xs text-muted-foreground px-2">
        Quick Actions
      </p>
      {actions.map((action) => (
        <ActionDropTarget
          key={action.id}
          action={action}
          onDrop={handleDropAction}
          disabled={disabled}
        />
      ))}
    </div>
  )
}

export default BulkDropZone
