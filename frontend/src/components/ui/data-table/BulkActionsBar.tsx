/**
 * BulkActionsBar - Floating Action Bar für Bulk-Operationen
 *
 * Phase 4.6: Frontend UX Enhancement - Bulk Actions UI
 *
 * Erscheint am unteren Bildschirmrand wenn Zeilen ausgewählt sind.
 * Bietet Aktionen wie Löschen, Taggen, Verschieben, Exportieren.
 */
import * as React from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  X,
  Trash2,
  Tag,
  FolderInput,
  Download,
  CheckSquare,
  MoreHorizontal,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react"
import { cn } from "@/lib/utils"

export interface BulkAction<TData = unknown> {
  /** Eindeutige ID der Aktion */
  id: string
  /** Anzeigename */
  label: string
  /** Icon (Lucide-Komponente) */
  icon: React.ComponentType<{ className?: string }>
  /** Ausführen der Aktion */
  onExecute: (selectedItems: TData[]) => Promise<void> | void
  /** Ist die Aktion verfügbar? */
  isAvailable?: (selectedItems: TData[]) => boolean
  /** Ist die Aktion destruktiv? (rot markiert) */
  destructive?: boolean
  /** Keyboard-Shortcut (angezeigt) */
  shortcut?: string
  /** Zusätzliche Badge-Info */
  badge?: string | ((selectedItems: TData[]) => string | undefined)
}

export interface BulkActionsBarProps<TData = unknown> {
  /** Anzahl ausgewählter Items */
  selectedCount: number
  /** Die ausgewählten Items */
  selectedItems: TData[]
  /** Verfügbare Bulk-Aktionen */
  actions: BulkAction<TData>[]
  /** Callback zum Abbrechen der Auswahl */
  onClearSelection: () => void
  /** Callback bei "Alle auswählen" */
  onSelectAll?: () => void
  /** Gesamtanzahl der Items */
  totalCount?: number
  /** Zeigt Fortschritt einer laufenden Aktion */
  progress?: {
    action: string
    current: number
    total: number
    status?: "running" | "success" | "error"
    message?: string
  }
  /** Zusätzliche CSS-Klassen */
  className?: string
}

export function BulkActionsBar<TData = unknown>({
  selectedCount,
  selectedItems,
  actions,
  onClearSelection,
  onSelectAll,
  totalCount,
  progress,
  className,
}: BulkActionsBarProps<TData>) {
  const [executing, setExecuting] = React.useState<string | null>(null)
  const isVisible = selectedCount > 0

  // Filter verfügbare Aktionen
  const availableActions = actions.filter(
    (action) => !action.isAvailable || action.isAvailable(selectedItems)
  )
  const primaryActions = availableActions.slice(0, 4)
  const moreActions = availableActions.slice(4)

  // Keyboard shortcuts
  React.useEffect(() => {
    if (!isVisible) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape zum Abbrechen
      if (e.key === "Escape") {
        onClearSelection()
        return
      }

      // Ctrl+A für alle auswählen
      if (e.ctrlKey && e.key === "a" && onSelectAll) {
        e.preventDefault()
        onSelectAll()
        return
      }

      // Aktions-Shortcuts
      for (const action of availableActions) {
        if (action.shortcut) {
          const parts = action.shortcut.toLowerCase().split("+")
          const key = parts[parts.length - 1]
          const needsCtrl = parts.includes("ctrl")
          const needsShift = parts.includes("shift")

          if (
            e.key.toLowerCase() === key &&
            e.ctrlKey === needsCtrl &&
            e.shiftKey === needsShift
          ) {
            e.preventDefault()
            handleExecuteAction(action)
            return
          }
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isVisible, availableActions, onClearSelection, onSelectAll])

  const handleExecuteAction = async (action: BulkAction<TData>) => {
    if (executing) return

    setExecuting(action.id)
    try {
      await action.onExecute(selectedItems)
    } finally {
      setExecuting(null)
    }
  }

  const getBadgeText = (action: BulkAction<TData>) => {
    if (!action.badge) return undefined
    if (typeof action.badge === "function") {
      return action.badge(selectedItems)
    }
    return action.badge
  }

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
          className={cn(
            "fixed bottom-6 left-1/2 -translate-x-1/2 z-50",
            "flex items-center gap-2 px-4 py-3 rounded-xl",
            "bg-background/95 backdrop-blur-sm border shadow-lg",
            "min-w-[400px] max-w-[90vw]",
            className
          )}
        >
          {/* Selection Info */}
          <div className="flex items-center gap-2 pr-4 border-r">
            <CheckSquare className="h-5 w-5 text-primary" />
            <span className="font-medium whitespace-nowrap">
              {selectedCount} ausgewählt
              {totalCount && (
                <span className="text-muted-foreground ml-1">
                  von {totalCount}
                </span>
              )}
            </span>
          </div>

          {/* Progress anzeigen wenn aktiv */}
          {progress && (
            <div className="flex items-center gap-3 px-3 min-w-[200px]">
              {progress.status === "running" && (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              )}
              {progress.status === "success" && (
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              )}
              {progress.status === "error" && (
                <AlertCircle className="h-4 w-4 text-destructive" />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-xs text-muted-foreground mb-1">
                  {progress.message || progress.action}
                </div>
                <Progress
                  value={(progress.current / progress.total) * 100}
                  className="h-1"
                />
              </div>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {progress.current}/{progress.total}
              </span>
            </div>
          )}

          {/* Primary Actions */}
          {!progress && (
            <TooltipProvider delayDuration={300}>
              <div className="flex items-center gap-1">
                {primaryActions.map((action) => {
                  const Icon = action.icon
                  const badge = getBadgeText(action)
                  const isExecuting = executing === action.id

                  return (
                    <Tooltip key={action.id}>
                      <TooltipTrigger asChild>
                        <Button
                          variant={action.destructive ? "destructive" : "ghost"}
                          size="sm"
                          className={cn(
                            "gap-2 h-9",
                            !action.destructive && "hover:bg-accent"
                          )}
                          onClick={() => handleExecuteAction(action)}
                          disabled={isExecuting || executing !== null}
                        >
                          {isExecuting ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Icon className="h-4 w-4" />
                          )}
                          <span className="hidden sm:inline">{action.label}</span>
                          {badge && (
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">
                              {badge}
                            </Badge>
                          )}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>{action.label}</p>
                        {action.shortcut && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {action.shortcut}
                          </p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  )
                })}

                {/* More Actions Dropdown */}
                {moreActions.length > 0 && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-9 px-2"
                        disabled={executing !== null}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuLabel>Weitere Aktionen</DropdownMenuLabel>
                      <DropdownMenuSeparator />
                      {moreActions.map((action) => {
                        const Icon = action.icon
                        return (
                          <DropdownMenuItem
                            key={action.id}
                            onClick={() => handleExecuteAction(action)}
                            className={cn(
                              "gap-2",
                              action.destructive && "text-destructive focus:text-destructive"
                            )}
                            disabled={executing !== null}
                          >
                            <Icon className="h-4 w-4" />
                            {action.label}
                            {action.shortcut && (
                              <span className="ml-auto text-xs text-muted-foreground">
                                {action.shortcut}
                              </span>
                            )}
                          </DropdownMenuItem>
                        )
                      })}
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            </TooltipProvider>
          )}

          {/* Close Button */}
          <Button
            variant="ghost"
            size="sm"
            className="ml-2 h-8 w-8 p-0 rounded-full"
            onClick={onClearSelection}
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Auswahl aufheben</span>
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// =============================================================================
// Vordefinierte Bulk-Aktionen
// =============================================================================

export function createDeleteAction<TData>(
  onDelete: (items: TData[]) => Promise<void>
): BulkAction<TData> {
  return {
    id: "delete",
    label: "Löschen",
    icon: Trash2,
    destructive: true,
    shortcut: "Delete",
    onExecute: onDelete,
  }
}

export function createTagAction<TData>(
  onTag: (items: TData[]) => Promise<void>
): BulkAction<TData> {
  return {
    id: "tag",
    label: "Tags hinzufügen",
    icon: Tag,
    shortcut: "Ctrl+T",
    onExecute: onTag,
  }
}

export function createMoveAction<TData>(
  onMove: (items: TData[]) => Promise<void>
): BulkAction<TData> {
  return {
    id: "move",
    label: "Verschieben",
    icon: FolderInput,
    shortcut: "Ctrl+M",
    onExecute: onMove,
  }
}

export function createExportAction<TData>(
  onExport: (items: TData[]) => Promise<void>
): BulkAction<TData> {
  return {
    id: "export",
    label: "Exportieren",
    icon: Download,
    shortcut: "Ctrl+E",
    onExecute: onExport,
  }
}
