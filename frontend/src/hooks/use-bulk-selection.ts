/**
 * useBulkSelection Hook - Verwaltet Multi-Selection fuer Bulk-Operationen
 *
 * Phase 4.6: Frontend UX Enhancement - Bulk Actions UI
 *
 * Bietet:
 * - Selection State Management
 * - Keyboard Shortcuts (Ctrl+A, Shift+Click)
 * - Progress Tracking fuer Batch-Operationen
 */
import { useState, useCallback, useMemo } from "react"

export interface BulkSelectionState<TData> {
  /** Map von ID zu Item */
  selectedMap: Map<string, TData>
  /** IDs als Array */
  selectedIds: string[]
  /** Items als Array */
  selectedItems: TData[]
  /** Anzahl ausgewaehlter Items */
  selectedCount: number
  /** Ist ein bestimmtes Item ausgewaehlt? */
  isSelected: (id: string) => boolean
  /** Alle Items ausgewaehlt? */
  allSelected: boolean
  /** Einige Items ausgewaehlt? (fuer Indeterminate-Checkbox) */
  someSelected: boolean
}

export interface BulkSelectionActions<TData> {
  /** Item zur Auswahl hinzufuegen/entfernen */
  toggleSelection: (id: string, item: TData) => void
  /** Alle Items auswaehlen */
  selectAll: (items: TData[], getIdFn: (item: TData) => string) => void
  /** Alle Items abwaehlen */
  clearSelection: () => void
  /** Mehrere Items auswaehlen */
  selectMany: (items: TData[], getIdFn: (item: TData) => string) => void
  /** Range-Selection (Shift+Click) */
  selectRange: (
    fromId: string,
    toId: string,
    allItems: TData[],
    getIdFn: (item: TData) => string
  ) => void
  /** Bestimmte Items entfernen (z.B. nach Loeschung) */
  removeFromSelection: (ids: string[]) => void
}

export interface UseBulkSelectionOptions {
  /** Maximale Anzahl selektierbarer Items */
  maxSelection?: number
  /** Callback bei Aenderung */
  onChange?: (selectedIds: string[]) => void
}

export interface UseBulkSelectionReturn<TData>
  extends BulkSelectionState<TData>,
    BulkSelectionActions<TData> {}

export function useBulkSelection<TData>(
  options: UseBulkSelectionOptions = {}
): UseBulkSelectionReturn<TData> {
  const { maxSelection, onChange } = options
  const [selectedMap, setSelectedMap] = useState<Map<string, TData>>(new Map())

  // Abgeleitete Werte
  const selectedIds = useMemo(() => Array.from(selectedMap.keys()), [selectedMap])
  const selectedItems = useMemo(() => Array.from(selectedMap.values()), [selectedMap])
  const selectedCount = selectedMap.size

  const isSelected = useCallback((id: string) => selectedMap.has(id), [selectedMap])

  // Toggle einzelnes Item
  const toggleSelection = useCallback(
    (id: string, item: TData) => {
      setSelectedMap((prev) => {
        const next = new Map(prev)
        if (next.has(id)) {
          next.delete(id)
        } else {
          if (maxSelection && next.size >= maxSelection) {
            return prev
          }
          next.set(id, item)
        }
        onChange?.(Array.from(next.keys()))
        return next
      })
    },
    [maxSelection, onChange]
  )

  // Alle auswaehlen
  const selectAll = useCallback(
    (items: TData[], getIdFn: (item: TData) => string) => {
      setSelectedMap(() => {
        const itemsToSelect = maxSelection ? items.slice(0, maxSelection) : items
        const next = new Map<string, TData>()
        itemsToSelect.forEach((item) => {
          next.set(getIdFn(item), item)
        })
        onChange?.(Array.from(next.keys()))
        return next
      })
    },
    [maxSelection, onChange]
  )

  // Auswahl leeren
  const clearSelection = useCallback(() => {
    setSelectedMap(new Map())
    onChange?.([])
  }, [onChange])

  // Mehrere auswaehlen
  const selectMany = useCallback(
    (items: TData[], getIdFn: (item: TData) => string) => {
      setSelectedMap((prev) => {
        const next = new Map(prev)
        for (const item of items) {
          if (maxSelection && next.size >= maxSelection) break
          const id = getIdFn(item)
          if (!next.has(id)) {
            next.set(id, item)
          }
        }
        onChange?.(Array.from(next.keys()))
        return next
      })
    },
    [maxSelection, onChange]
  )

  // Range-Selection (Shift+Click)
  const selectRange = useCallback(
    (
      fromId: string,
      toId: string,
      allItems: TData[],
      getIdFn: (item: TData) => string
    ) => {
      const fromIndex = allItems.findIndex((item) => getIdFn(item) === fromId)
      const toIndex = allItems.findIndex((item) => getIdFn(item) === toId)

      if (fromIndex === -1 || toIndex === -1) return

      const start = Math.min(fromIndex, toIndex)
      const end = Math.max(fromIndex, toIndex)
      const rangeItems = allItems.slice(start, end + 1)

      selectMany(rangeItems, getIdFn)
    },
    [selectMany]
  )

  // Items aus Auswahl entfernen
  const removeFromSelection = useCallback(
    (ids: string[]) => {
      setSelectedMap((prev) => {
        const next = new Map(prev)
        ids.forEach((id) => next.delete(id))
        onChange?.(Array.from(next.keys()))
        return next
      })
    },
    [onChange]
  )

  return {
    // State
    selectedMap,
    selectedIds,
    selectedItems,
    selectedCount,
    isSelected,
    allSelected: false, // Muss von aussen berechnet werden (braucht totalCount)
    someSelected: selectedCount > 0,

    // Actions
    toggleSelection,
    selectAll,
    clearSelection,
    selectMany,
    selectRange,
    removeFromSelection,
  }
}

// =============================================================================
// Progress Tracking fuer Batch-Operationen
// =============================================================================

export interface BatchProgress {
  action: string
  current: number
  total: number
  status: "running" | "success" | "error"
  message?: string
}

export interface UseBatchProgressReturn {
  progress: BatchProgress | null
  startBatch: (action: string, total: number) => void
  updateProgress: (current: number, message?: string) => void
  completeBatch: (success?: boolean, message?: string) => void
  resetProgress: () => void
}

export function useBatchProgress(): UseBatchProgressReturn {
  const [progress, setProgress] = useState<BatchProgress | null>(null)

  const startBatch = useCallback((action: string, total: number) => {
    setProgress({
      action,
      current: 0,
      total,
      status: "running",
    })
  }, [])

  const updateProgress = useCallback((current: number, message?: string) => {
    setProgress((prev) =>
      prev
        ? {
            ...prev,
            current,
            message,
          }
        : null
    )
  }, [])

  const completeBatch = useCallback((success = true, message?: string) => {
    setProgress((prev) =>
      prev
        ? {
            ...prev,
            current: prev.total,
            status: success ? "success" : "error",
            message,
          }
        : null
    )

    // Auto-reset nach 3 Sekunden
    setTimeout(() => {
      setProgress(null)
    }, 3000)
  }, [])

  const resetProgress = useCallback(() => {
    setProgress(null)
  }, [])

  return {
    progress,
    startBatch,
    updateProgress,
    completeBatch,
    resetProgress,
  }
}

// =============================================================================
// Batch Executor fuer sequentielle Verarbeitung
// =============================================================================

export interface BatchExecutorOptions<TData, TResult> {
  items: TData[]
  operation: (item: TData, index: number) => Promise<TResult>
  onProgress?: (current: number, total: number, item: TData) => void
  onComplete?: (results: TResult[], errors: Error[]) => void
  concurrency?: number
}

export async function executeBatch<TData, TResult>(
  options: BatchExecutorOptions<TData, TResult>
): Promise<{ results: TResult[]; errors: Error[] }> {
  const { items, operation, onProgress, onComplete, concurrency = 1 } = options
  const results: TResult[] = []
  const errors: Error[] = []
  const total = items.length

  if (concurrency === 1) {
    // Sequentielle Verarbeitung
    for (let i = 0; i < items.length; i++) {
      try {
        const result = await operation(items[i], i)
        results.push(result)
        onProgress?.(i + 1, total, items[i])
      } catch (err) {
        errors.push(err instanceof Error ? err : new Error(String(err)))
        onProgress?.(i + 1, total, items[i])
      }
    }
  } else {
    // Parallele Verarbeitung mit begrenzter Concurrency
    const chunks: TData[][] = []
    for (let i = 0; i < items.length; i += concurrency) {
      chunks.push(items.slice(i, i + concurrency))
    }

    let processed = 0
    for (const chunk of chunks) {
      const chunkResults = await Promise.allSettled(
        chunk.map((item, idx) => operation(item, processed + idx))
      )

      chunkResults.forEach((result, idx) => {
        if (result.status === "fulfilled") {
          results.push(result.value)
        } else {
          errors.push(result.reason)
        }
        onProgress?.(processed + idx + 1, total, chunk[idx])
      })

      processed += chunk.length
    }
  }

  onComplete?.(results, errors)
  return { results, errors }
}
