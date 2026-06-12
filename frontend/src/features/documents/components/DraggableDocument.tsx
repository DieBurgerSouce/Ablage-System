/**
 * DraggableDocument - Draggable Wrapper für DocumentCard
 *
 * Phase 2.2: Drag & Drop überall
 *
 * Features:
 * - Macht DocumentCard via @dnd-kit draggable
 * - Multi-Select Support (mehrere Dokumente gleichzeitig ziehen)
 * - Visuelles Drag-Feedback (Opacity, Scale, Badge)
 * - Keyboard-Accessible
 */

import { forwardRef, useMemo } from "react"
import { useDraggable } from "@dnd-kit/core"
import { CSS } from "@dnd-kit/utilities"
import { cn } from "@/lib/utils"
import { DocumentCard } from "./DocumentCard"
import type { Document } from "../types"
import type { DragItem, DocumentDragData } from "@/hooks/useDragAndDrop"

// =============================================================================
// Types
// =============================================================================

export interface DraggableDocumentProps {
  /** Das Dokument */
  document: Document
  /** Ist ausgewählt */
  isSelected: boolean
  /** Ist fokussiert (Tastatur-Navigation) */
  isFocused?: boolean
  /** Alle aktuell ausgewählten Dokument-IDs (für Multi-Drag) */
  selectedIds?: string[]
  /** Anzahl der ausgewählten Elemente (für Badge) */
  selectedCount?: number
  /** Drag deaktiviert */
  disabled?: boolean
  /** Click-Handler */
  onClick: () => void
  /** Doppelklick-Handler */
  onDoubleClick: () => void
  /** Selection-Handler */
  onSelect: (checked: boolean) => void
  /** Tab-Index */
  tabIndex?: number
  /** Focus-Handler */
  onFocus?: () => void
  /** ARIA Column Index */
  ariaColIndex?: number
}

// =============================================================================
// Component
// =============================================================================

export const DraggableDocument = forwardRef<HTMLDivElement, DraggableDocumentProps>(
  function DraggableDocument(
    {
      document,
      isSelected,
      isFocused = false,
      selectedIds = [],
      selectedCount = 0,
      disabled = false,
      onClick,
      onDoubleClick,
      onSelect,
      tabIndex = -1,
      onFocus,
      ariaColIndex,
    },
    ref
  ) {
    // Drag-Daten für dieses Dokument
    const dragData: DragItem<DocumentDragData> = useMemo(
      () => ({
        id: document.id,
        type: "document",
        data: {
          documentId: document.id,
          filename: document.name,
          // documentType/folderId existieren auf dem Document-Typ nicht;
          // Drop-Handler nutzen nur documentId(s) (DocumentGrid/DroppableFolder)
        },
        // Bei Multi-Select: Alle ausgewählten IDs
        selectedIds: isSelected && selectedIds.length > 1 ? selectedIds : undefined,
      }),
      [document, isSelected, selectedIds]
    )

    // @dnd-kit Draggable Hook
    const {
      attributes,
      listeners,
      setNodeRef,
      transform,
      isDragging,
    } = useDraggable({
      id: document.id,
      data: dragData,
      disabled,
    })

    // Transform Style
    const style = useMemo(
      () => ({
        transform: CSS.Translate.toString(transform),
        opacity: isDragging ? 0.5 : 1,
        cursor: disabled ? "default" : isDragging ? "grabbing" : "grab",
        touchAction: "none",
      }),
      [transform, isDragging, disabled]
    )

    // Anzahl für Badge (nur wenn Multi-Drag)
    const dragCount = isSelected && selectedCount > 1 ? selectedCount : 0

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
          "relative",
          isDragging && "z-50"
        )}
        {...attributes}
        {...listeners}
      >
        {/* Multi-Drag Badge */}
        {isDragging && dragCount > 1 && (
          <div
            className={cn(
              "absolute -top-2 -right-2 z-10",
              "flex items-center justify-center",
              "w-6 h-6 rounded-full",
              "bg-primary text-primary-foreground",
              "text-xs font-bold",
              "shadow-md"
            )}
          >
            {dragCount}
          </div>
        )}

        <DocumentCard
          document={document}
          isSelected={isSelected}
          isFocused={isFocused}
          onClick={onClick}
          onDoubleClick={onDoubleClick}
          onSelect={onSelect}
          tabIndex={tabIndex}
          onFocus={onFocus}
          ariaColIndex={ariaColIndex}
        />
      </div>
    )
  }
)

// =============================================================================
// Drag Overlay Component (für DragOverlay in DndContext)
// =============================================================================

export interface DragOverlayDocumentProps {
  document: Document
  selectedCount?: number
}

export function DragOverlayDocument({
  document,
  selectedCount = 1,
}: DragOverlayDocumentProps) {
  return (
    <div className="relative pointer-events-none">
      {/* Multi-Drag Badge */}
      {selectedCount > 1 && (
        <div
          className={cn(
            "absolute -top-2 -right-2 z-10",
            "flex items-center justify-center",
            "w-7 h-7 rounded-full",
            "bg-primary text-primary-foreground",
            "text-sm font-bold",
            "shadow-lg animate-in zoom-in-75 duration-200"
          )}
        >
          {selectedCount}
        </div>
      )}

      {/* Document Preview */}
      <div
        className={cn(
          "w-48 bg-background border rounded-lg shadow-2xl",
          "transform rotate-3 scale-105",
          "animate-in zoom-in-95 duration-200"
        )}
      >
        <div className="aspect-[4/3] bg-muted/50 rounded-t-lg overflow-hidden flex items-center justify-center">
          {document.thumbnail ? (
            <img
              src={document.thumbnail}
              className="w-full h-full object-cover"
              alt={document.name}
            />
          ) : (
            <div className="text-4xl text-muted-foreground">
              {document.mimeType?.includes("pdf") ? "📄" : "📁"}
            </div>
          )}
        </div>
        <div className="p-3">
          <p className="text-sm font-medium truncate">{document.name}</p>
        </div>
      </div>

      {/* Stack Effect für Multi-Drag */}
      {selectedCount > 1 && (
        <>
          <div
            className={cn(
              "absolute -bottom-1 -left-1 -z-10",
              "w-48 h-full bg-muted border rounded-lg",
              "transform -rotate-2"
            )}
          />
          {selectedCount > 2 && (
            <div
              className={cn(
                "absolute -bottom-2 -left-2 -z-20",
                "w-48 h-full bg-muted/50 border rounded-lg",
                "transform -rotate-4"
              )}
            />
          )}
        </>
      )}
    </div>
  )
}

export default DraggableDocument
