/**
 * useDragAndDrop Hook - Drag & Drop Funktionalitaet mit @dnd-kit
 *
 * Phase 2.2: Drag & Drop ueberall
 *
 * Features:
 * - Dokumente in Ordner ziehen
 * - Multi-Select + Drag
 * - Dashboard-Widgets umsortieren
 * - Visuelles Feedback (Drag Preview, Drop Indicator)
 *
 * Verwendet @dnd-kit/core fuer maximale Flexibilitaet
 */

import { useState, useCallback, useMemo } from "react"
import type { UniqueIdentifier, DragStartEvent, DragEndEvent, DragOverEvent } from "@dnd-kit/core"

// =============================================================================
// Types
// =============================================================================

export type DragItemType = "document" | "folder" | "widget" | "custom"

export interface DragItem<TData = unknown> {
  id: UniqueIdentifier
  type: DragItemType
  data: TData
  /** Bei Multi-Select: Alle ausgewaehlten IDs */
  selectedIds?: UniqueIdentifier[]
}

export interface DropTarget {
  id: UniqueIdentifier
  type: DragItemType
  /** Akzeptierte Drag-Typen */
  accepts: DragItemType[]
}

export interface DragState {
  /** Aktuell gezogenes Element */
  activeItem: DragItem | null
  /** Aktuelles Drop-Ziel (Hover) */
  overTarget: DropTarget | null
  /** Drag ist aktiv */
  isDragging: boolean
  /** Anzahl der gezogenen Elemente (Multi-Select) */
  dragCount: number
}

export interface UseDragAndDropOptions<TData = unknown> {
  /** Callback bei erfolgreichem Drop */
  onDrop?: (item: DragItem<TData>, target: DropTarget) => void | Promise<void>
  /** Callback bei abgebrochenem Drag */
  onCancel?: (item: DragItem<TData>) => void
  /** Validierung ob Drop erlaubt ist */
  canDrop?: (item: DragItem<TData>, target: DropTarget) => boolean
  /** Multi-Select Unterstuetzung */
  enableMultiSelect?: boolean
  /** Animation Dauer in ms */
  animationDuration?: number
}

export interface UseDragAndDropReturn<TData = unknown> {
  /** Aktueller Drag-State */
  dragState: DragState
  /** Handler fuer DndContext */
  handlers: {
    onDragStart: (event: DragStartEvent) => void
    onDragOver: (event: DragOverEvent) => void
    onDragEnd: (event: DragEndEvent) => void
    onDragCancel: () => void
  }
  /** Ist ein bestimmtes Element gerade das Drop-Ziel? */
  isOver: (id: UniqueIdentifier) => boolean
  /** Kann auf ein Ziel gedroppt werden? */
  canDropOn: (targetId: UniqueIdentifier) => boolean
  /** Drag manuell abbrechen */
  cancelDrag: () => void
}

// =============================================================================
// Hook Implementation
// =============================================================================

export function useDragAndDrop<TData = unknown>(
  options: UseDragAndDropOptions<TData> = {}
): UseDragAndDropReturn<TData> {
  const {
    onDrop,
    onCancel,
    canDrop: canDropFn,
    enableMultiSelect = true,
  } = options

  // State
  const [activeItem, setActiveItem] = useState<DragItem<TData> | null>(null)
  const [overTarget, setOverTarget] = useState<DropTarget | null>(null)

  // Abgeleitete Werte
  const dragState: DragState = useMemo(
    () => ({
      activeItem: activeItem as DragItem | null,
      overTarget,
      isDragging: activeItem !== null,
      dragCount: activeItem?.selectedIds?.length ?? 1,
    }),
    [activeItem, overTarget]
  )

  // Drag Start Handler
  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const { active } = event

      // DragItem aus active.data extrahieren
      const dragData = active.data.current as DragItem<TData> | undefined

      if (dragData) {
        setActiveItem(dragData)
      } else {
        // Fallback: Minimal-DragItem erstellen
        setActiveItem({
          id: active.id,
          type: "custom" as DragItemType,
          data: {} as TData,
        })
      }
    },
    []
  )

  // Drag Over Handler
  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      const { over } = event

      if (over) {
        const targetData = over.data.current as DropTarget | undefined
        if (targetData) {
          setOverTarget(targetData)
        } else {
          setOverTarget({
            id: over.id,
            type: "custom",
            accepts: ["document", "folder", "widget", "custom"],
          })
        }
      } else {
        setOverTarget(null)
      }
    },
    []
  )

  // Drag End Handler
  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { over } = event

      if (activeItem && over) {
        const targetData = over.data.current as DropTarget | undefined
        const target: DropTarget = targetData ?? {
          id: over.id,
          type: "custom",
          accepts: ["document", "folder", "widget", "custom"],
        }

        // Validierung
        const canDrop = canDropFn
          ? canDropFn(activeItem, target)
          : target.accepts.includes(activeItem.type)

        if (canDrop) {
          onDrop?.(activeItem, target)
        }
      }

      // State zuruecksetzen
      setActiveItem(null)
      setOverTarget(null)
    },
    [activeItem, canDropFn, onDrop]
  )

  // Drag Cancel Handler
  const handleDragCancel = useCallback(() => {
    if (activeItem) {
      onCancel?.(activeItem)
    }
    setActiveItem(null)
    setOverTarget(null)
  }, [activeItem, onCancel])

  // Helper: Ist Element das aktuelle Drop-Ziel?
  const isOver = useCallback(
    (id: UniqueIdentifier) => overTarget?.id === id,
    [overTarget]
  )

  // Helper: Kann auf Ziel gedroppt werden?
  const canDropOn = useCallback(
    (targetId: UniqueIdentifier) => {
      if (!activeItem || !overTarget) return false
      if (overTarget.id !== targetId) return false

      if (canDropFn) {
        return canDropFn(activeItem, overTarget)
      }

      return overTarget.accepts.includes(activeItem.type)
    },
    [activeItem, overTarget, canDropFn]
  )

  return {
    dragState,
    handlers: {
      onDragStart: handleDragStart,
      onDragOver: handleDragOver,
      onDragEnd: handleDragEnd,
      onDragCancel: handleDragCancel,
    },
    isOver,
    canDropOn,
    cancelDrag: handleDragCancel,
  }
}

// =============================================================================
// useSortableDrag - Fuer sortierbare Listen (Dashboard Widgets)
// =============================================================================

export interface SortableItem {
  id: UniqueIdentifier
  order: number
}

export interface UseSortableDragOptions {
  /** Callback bei Reihenfolge-Aenderung */
  onReorder?: (items: SortableItem[]) => void
  /** Speichern in localStorage */
  persistKey?: string
}

export interface UseSortableDragReturn {
  /** Sortierte Items */
  items: SortableItem[]
  /** Items setzen */
  setItems: (items: SortableItem[]) => void
  /** Drag-Handlers */
  handlers: {
    onDragStart: (event: DragStartEvent) => void
    onDragOver: (event: DragOverEvent) => void
    onDragEnd: (event: DragEndEvent) => void
  }
  /** Aktives Element */
  activeId: UniqueIdentifier | null
}

export function useSortableDrag(
  initialItems: SortableItem[],
  options: UseSortableDragOptions = {}
): UseSortableDragReturn {
  const { onReorder, persistKey } = options

  // Items aus localStorage laden falls persistKey gesetzt
  const loadInitialItems = (): SortableItem[] => {
    if (persistKey && typeof window !== "undefined") {
      const stored = localStorage.getItem(`dnd-order-${persistKey}`)
      if (stored) {
        try {
          return JSON.parse(stored)
        } catch {
          // Fallback zu initialItems
        }
      }
    }
    return initialItems
  }

  const [items, setItemsState] = useState<SortableItem[]>(loadInitialItems)
  const [activeId, setActiveId] = useState<UniqueIdentifier | null>(null)

  // Items setzen und optional persistieren
  const setItems = useCallback(
    (newItems: SortableItem[]) => {
      setItemsState(newItems)

      if (persistKey && typeof window !== "undefined") {
        localStorage.setItem(`dnd-order-${persistKey}`, JSON.stringify(newItems))
      }

      onReorder?.(newItems)
    },
    [persistKey, onReorder]
  )

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(event.active.id)
  }, [])

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return

      setItemsState((prev) => {
        const oldIndex = prev.findIndex((item) => item.id === active.id)
        const newIndex = prev.findIndex((item) => item.id === over.id)

        if (oldIndex === -1 || newIndex === -1) return prev

        const newItems = [...prev]
        const [movedItem] = newItems.splice(oldIndex, 1)
        newItems.splice(newIndex, 0, movedItem)

        // Order-Werte aktualisieren
        return newItems.map((item, index) => ({
          ...item,
          order: index,
        }))
      })
    },
    []
  )

  const handleDragEnd = useCallback(() => {
    setActiveId(null)

    // Persistieren
    if (persistKey && typeof window !== "undefined") {
      localStorage.setItem(`dnd-order-${persistKey}`, JSON.stringify(items))
    }

    onReorder?.(items)
  }, [items, persistKey, onReorder])

  return {
    items,
    setItems,
    handlers: {
      onDragStart: handleDragStart,
      onDragOver: handleDragOver,
      onDragEnd: handleDragEnd,
    },
    activeId,
  }
}

// =============================================================================
// useDroppable - Hook fuer Drop-Ziele
// =============================================================================

export interface UseDroppableOptions {
  id: UniqueIdentifier
  type: DragItemType
  accepts: DragItemType[]
  disabled?: boolean
}

export interface UseDroppableReturn {
  /** Props fuer das Droppable-Element */
  droppableProps: {
    "data-droppable": boolean
    "data-droppable-id": string
    "data-droppable-type": string
  }
  /** DropTarget-Daten fuer @dnd-kit */
  dropTargetData: DropTarget
}

export function useDroppable(options: UseDroppableOptions): UseDroppableReturn {
  const { id, type, accepts, disabled = false } = options

  const dropTargetData: DropTarget = useMemo(
    () => ({
      id,
      type,
      accepts: disabled ? [] : accepts,
    }),
    [id, type, accepts, disabled]
  )

  const droppableProps = useMemo(
    () => ({
      "data-droppable": !disabled,
      "data-droppable-id": String(id),
      "data-droppable-type": type,
    }),
    [id, type, disabled]
  )

  return {
    droppableProps,
    dropTargetData,
  }
}

// =============================================================================
// useDraggable - Hook fuer Drag-Quellen
// =============================================================================

export interface UseDraggableOptions<TData = unknown> {
  id: UniqueIdentifier
  type: DragItemType
  data: TData
  disabled?: boolean
  /** IDs bei Multi-Select */
  selectedIds?: UniqueIdentifier[]
}

export interface UseDraggableReturn<TData = unknown> {
  /** Props fuer das Draggable-Element */
  draggableProps: {
    "data-draggable": boolean
    "data-draggable-id": string
    "data-draggable-type": string
  }
  /** DragItem-Daten fuer @dnd-kit */
  dragItemData: DragItem<TData>
}

export function useDraggable<TData = unknown>(
  options: UseDraggableOptions<TData>
): UseDraggableReturn<TData> {
  const { id, type, data, disabled = false, selectedIds } = options

  const dragItemData: DragItem<TData> = useMemo(
    () => ({
      id,
      type,
      data,
      selectedIds,
    }),
    [id, type, data, selectedIds]
  )

  const draggableProps = useMemo(
    () => ({
      "data-draggable": !disabled,
      "data-draggable-id": String(id),
      "data-draggable-type": type,
    }),
    [id, type, disabled]
  )

  return {
    draggableProps,
    dragItemData,
  }
}

// =============================================================================
// Helper Types fuer Document/Folder DnD
// =============================================================================

export interface DocumentDragData {
  documentId: string
  filename: string
  documentType?: string
  folderId?: string
}

export interface FolderDropData {
  folderId: string
  folderName: string
}

export interface WidgetDragData {
  widgetId: string
  widgetType: string
  order: number
}
