/**
 * DroppableFolder - Drop-Ziel für Dokumente
 *
 * Phase 2.2: Drag & Drop überall
 *
 * Features:
 * - Akzeptiert gedropte Dokumente via @dnd-kit
 * - Visuelles Feedback bei Hover (Highlighting)
 * - Validierung welche Drop-Typen akzeptiert werden
 * - Accessibility: Tastatur-Unterstützung
 */

import { forwardRef, useMemo } from "react"
import { useDroppable } from "@dnd-kit/core"
import { Folder, FolderOpen } from "lucide-react"
import { cn } from "@/lib/utils"
import type { DropTarget, DragItemType } from "@/hooks/useDragAndDrop"

// =============================================================================
// Types
// =============================================================================

export interface FolderData {
  id: string
  name: string
  documentCount?: number
  parentId?: string | null
  color?: string
}

export interface DroppableFolderProps {
  /** Folder-Daten */
  folder: FolderData
  /** Akzeptierte Drag-Typen */
  accepts?: DragItemType[]
  /** Drop deaktiviert */
  disabled?: boolean
  /** Folder ist aktiv/ausgewählt */
  isActive?: boolean
  /** Folder ist geöffnet */
  isOpen?: boolean
  /** Click-Handler */
  onClick?: () => void
  /** Doppelklick-Handler */
  onDoubleClick?: () => void
  /** Callback wenn erfolgreich gedroppt */
  onDrop?: (folderId: string, itemIds: string[]) => void
  /** Zusätzliche CSS-Klassen */
  className?: string
  /** Variante */
  variant?: "default" | "compact" | "list"
  /** Tab-Index */
  tabIndex?: number
}

// =============================================================================
// Component
// =============================================================================

export const DroppableFolder = forwardRef<HTMLDivElement, DroppableFolderProps>(
  function DroppableFolder(
    {
      folder,
      accepts = ["document"],
      disabled = false,
      isActive = false,
      onClick,
      onDoubleClick,
      className,
      variant = "default",
      tabIndex = 0,
    },
    ref
  ) {
    // Drop-Target Daten
    const dropTargetData: DropTarget = useMemo(
      () => ({
        id: folder.id,
        type: "folder",
        accepts: disabled ? [] : accepts,
      }),
      [folder.id, accepts, disabled]
    )

    // @dnd-kit Droppable Hook
    const { isOver, setNodeRef, active } = useDroppable({
      id: folder.id,
      data: dropTargetData,
      disabled,
    })

    // Prüfen ob aktueller Drag akzeptiert wird
    const canAccept = useMemo(() => {
      if (!active || disabled) return false
      const dragType = active.data.current?.type as DragItemType | undefined
      return dragType ? accepts.includes(dragType) : false
    }, [active, disabled, accepts])

    // Icon basierend auf Status
    const FolderIcon = isOver && canAccept ? FolderOpen : Folder

    // Farbe
    const folderColor = folder.color || "hsl(var(--primary))"

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
        role="button"
        tabIndex={tabIndex}
        onClick={onClick}
        onDoubleClick={onDoubleClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            onClick?.()
          }
        }}
        className={cn(
          // Base Styles
          "relative group cursor-pointer transition-all duration-200",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",

          // Variant: Default (Card)
          variant === "default" && [
            "flex flex-col items-center p-4 rounded-lg border bg-background",
            "hover:bg-muted/50 hover:border-primary/50",
          ],

          // Variant: Compact (Sidebar)
          variant === "compact" && [
            "flex items-center gap-2 px-3 py-2 rounded-md",
            "hover:bg-muted",
          ],

          // Variant: List (Liste)
          variant === "list" && [
            "flex items-center gap-3 px-4 py-3 border-b",
            "hover:bg-muted/50",
          ],

          // Active State
          isActive && "bg-muted border-primary",

          // Drop Target Active
          isOver && canAccept && [
            "ring-2 ring-primary ring-offset-2 bg-primary/10",
            "border-primary border-dashed",
            "scale-105",
          ],

          // Drop nicht möglich
          isOver && !canAccept && [
            "ring-2 ring-destructive ring-offset-2",
            "border-destructive",
          ],

          // Disabled
          disabled && "opacity-50 cursor-not-allowed",

          className
        )}
        aria-label={`Ordner: ${folder.name}`}
        aria-disabled={disabled}
        data-droppable={!disabled}
        data-droppable-id={folder.id}
        data-droppable-type="folder"
      >
        {/* Icon */}
        <div
          className={cn(
            "transition-transform duration-200",
            isOver && canAccept && "scale-110"
          )}
        >
          <FolderIcon
            className={cn(
              "transition-colors duration-200",
              variant === "default" && "h-12 w-12",
              variant === "compact" && "h-5 w-5",
              variant === "list" && "h-6 w-6"
            )}
            style={{
              color: isOver && canAccept ? folderColor : undefined,
            }}
          />
        </div>

        {/* Content */}
        <div
          className={cn(
            variant === "default" && "mt-2 text-center",
            variant === "compact" && "flex-1 min-w-0",
            variant === "list" && "flex-1 min-w-0"
          )}
        >
          <span
            className={cn(
              "font-medium truncate block",
              variant === "default" && "text-sm",
              variant === "compact" && "text-sm",
              variant === "list" && "text-base"
            )}
          >
            {folder.name}
          </span>

          {/* Document Count */}
          {folder.documentCount !== undefined && variant !== "compact" && (
            <span className="text-xs text-muted-foreground mt-0.5 block">
              {folder.documentCount} Dokument{folder.documentCount !== 1 ? "e" : ""}
            </span>
          )}
        </div>

        {/* Document Count Badge (Compact) */}
        {variant === "compact" && folder.documentCount !== undefined && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {folder.documentCount}
          </span>
        )}

        {/* Drop Indicator Overlay */}
        {isOver && canAccept && (
          <div
            className={cn(
              "absolute inset-0 rounded-lg",
              "bg-primary/5 border-2 border-primary border-dashed",
              "flex items-center justify-center",
              "pointer-events-none",
              "animate-in fade-in-0 duration-200"
            )}
          >
            <span className="text-sm font-medium text-primary bg-background px-2 py-1 rounded">
              Hierher ablegen
            </span>
          </div>
        )}
      </div>
    )
  }
)

// =============================================================================
// FolderDropZone - Größere Drop-Zone für Sidebar
// =============================================================================

export interface FolderDropZoneProps {
  folder: FolderData
  children: React.ReactNode
  disabled?: boolean
  className?: string
}

export function FolderDropZone({
  folder,
  children,
  disabled = false,
  className,
}: FolderDropZoneProps) {
  const dropTargetData: DropTarget = useMemo(
    () => ({
      id: folder.id,
      type: "folder",
      accepts: disabled ? [] : ["document"],
    }),
    [folder.id, disabled]
  )

  const { isOver, setNodeRef, active } = useDroppable({
    id: `folder-zone-${folder.id}`,
    data: dropTargetData,
    disabled,
  })

  const canAccept = useMemo(() => {
    if (!active || disabled) return false
    const dragType = active.data.current?.type as DragItemType | undefined
    return dragType === "document"
  }, [active, disabled])

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "transition-all duration-200",
        isOver && canAccept && "bg-primary/10 ring-2 ring-primary ring-inset",
        className
      )}
    >
      {children}

      {/* Drop Hint */}
      {isOver && canAccept && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-50">
          <span className="text-xs font-medium text-primary bg-primary/20 px-2 py-1 rounded-full">
            In "{folder.name}" verschieben
          </span>
        </div>
      )}
    </div>
  )
}

export default DroppableFolder
