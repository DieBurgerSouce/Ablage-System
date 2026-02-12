/**
 * BulkActionBar - Aktionsleiste für Massenoperationen
 *
 * Phase 2.3: Bulk Actions konsistent
 *
 * Features:
 * - Zeigt Anzahl ausgewählter Elemente
 * - Aktionen: Verschieben, Taggen, Exportieren, Löschen
 * - Animierte Ein-/Ausblendung
 * - Keyboard Support (Escape zum Schließen)
 */

import { useCallback, useEffect } from "react"
import { X, FolderInput, Tag, Download, Trash2, MoreHorizontal, CheckSquare } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

// =============================================================================
// Types
// =============================================================================

export type BulkAction = "move" | "tag" | "export" | "delete" | "archive" | "restore"

export interface BulkActionConfig {
  id: BulkAction
  label: string
  icon: React.ReactNode
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost"
  /** Aktion benötigt Bestätigung */
  requiresConfirmation?: boolean
  /** Aktion ist deaktiviert */
  disabled?: boolean
  /** Tastenkürzel */
  shortcut?: string
}

export interface BulkActionBarProps {
  /** Anzahl ausgewählter Elemente */
  selectedCount: number
  /** Gesamtanzahl der Elemente */
  totalCount?: number
  /** Verfügbare Aktionen */
  actions?: BulkActionConfig[]
  /** Callback bei Aktionsausführung */
  onAction?: (action: BulkAction) => void
  /** Callback zum Schließen/Abwählen */
  onClear?: () => void
  /** Alle auswählen */
  onSelectAll?: () => void
  /** Zusätzliche CSS-Klassen */
  className?: string
  /** Ist die Leiste sichtbar (animiert) */
  visible?: boolean
  /** Loading-Zustand für bestimmte Aktion */
  loadingAction?: BulkAction | null
}

// =============================================================================
// Default Actions
// =============================================================================

const DEFAULT_ACTIONS: BulkActionConfig[] = [
  {
    id: "move",
    label: "Verschieben",
    icon: <FolderInput className="h-4 w-4" />,
    shortcut: "M",
  },
  {
    id: "tag",
    label: "Tags bearbeiten",
    icon: <Tag className="h-4 w-4" />,
    shortcut: "T",
  },
  {
    id: "export",
    label: "Exportieren",
    icon: <Download className="h-4 w-4" />,
    shortcut: "E",
  },
  {
    id: "delete",
    label: "Löschen",
    icon: <Trash2 className="h-4 w-4" />,
    variant: "destructive",
    requiresConfirmation: true,
    shortcut: "Del",
  },
]

// =============================================================================
// Component
// =============================================================================

export function BulkActionBar({
  selectedCount,
  totalCount,
  actions = DEFAULT_ACTIONS,
  onAction,
  onClear,
  onSelectAll,
  className,
  visible = true,
  loadingAction = null,
}: BulkActionBarProps) {
  // Escape-Taste zum Schließen
  useEffect(() => {
    if (!visible) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        onClear?.()
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [visible, onClear])

  // Tastenkürzel für Aktionen
  useEffect(() => {
    if (!visible || selectedCount === 0) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // Nicht in Eingabefeldern
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return
      }

      const action = actions.find(
        (a) => a.shortcut?.toLowerCase() === e.key.toLowerCase()
      )

      if (action && !action.disabled) {
        e.preventDefault()
        onAction?.(action.id)
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [visible, selectedCount, actions, onAction])

  const handleAction = useCallback(
    (action: BulkAction) => {
      onAction?.(action)
    },
    [onAction]
  )

  if (!visible || selectedCount === 0) {
    return null
  }

  // Aktionen aufteilen: Haupt-Aktionen (erste 3) und Mehr-Aktionen
  const mainActions = actions.slice(0, 3)
  const moreActions = actions.slice(3)

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className={cn(
          "fixed bottom-4 left-1/2 -translate-x-1/2 z-50",
          "flex items-center gap-2 px-4 py-2",
          "bg-background border rounded-lg shadow-lg",
          "animate-in fade-in-0 slide-in-from-bottom-4 duration-200",
          className
        )}
        role="toolbar"
        aria-label="Massenaktionen"
      >
        {/* Auswahlzaehler */}
        <div className="flex items-center gap-2 pr-3 border-r">
          <CheckSquare className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">
            {selectedCount}
            {totalCount && ` von ${totalCount}`} ausgewählt
          </span>
        </div>

        {/* Alle auswählen (wenn nicht alle ausgewählt) */}
        {onSelectAll && totalCount && selectedCount < totalCount && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onSelectAll}
            className="text-xs"
          >
            Alle auswählen
          </Button>
        )}

        {/* Haupt-Aktionen */}
        <div className="flex items-center gap-1">
          {mainActions.map((action) => (
            <Tooltip key={action.id}>
              <TooltipTrigger asChild>
                <Button
                  variant={action.variant || "outline"}
                  size="sm"
                  onClick={() => handleAction(action.id)}
                  disabled={action.disabled || loadingAction === action.id}
                  className="gap-2"
                >
                  {action.icon}
                  <span className="hidden sm:inline">{action.label}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>
                  {action.label}
                  {action.shortcut && (
                    <span className="ml-2 text-muted-foreground">
                      [{action.shortcut}]
                    </span>
                  )}
                </p>
              </TooltipContent>
            </Tooltip>
          ))}
        </div>

        {/* Mehr-Aktionen Dropdown */}
        {moreActions.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {moreActions.map((action, index) => (
                <DropdownMenuItem
                  key={action.id}
                  onClick={() => handleAction(action.id)}
                  disabled={action.disabled}
                  className={cn(
                    "gap-2",
                    action.variant === "destructive" && "text-destructive"
                  )}
                >
                  {action.icon}
                  {action.label}
                  {action.shortcut && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      {action.shortcut}
                    </span>
                  )}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {/* Schließen-Button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClear}
              className="ml-2"
            >
              <X className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Auswahl aufheben [Esc]</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  )
}

// =============================================================================
// BulkActionProgress - Fortschrittsanzeige für laufende Aktionen
// =============================================================================

export interface BulkActionProgressProps {
  /** Aktion die läuft */
  action: BulkAction
  /** Aktueller Fortschritt (0-100) */
  progress: number
  /** Anzahl verarbeiteter Elemente */
  current: number
  /** Gesamtanzahl */
  total: number
  /** Status */
  status: "running" | "success" | "error"
  /** Fehlermeldung */
  errorMessage?: string
  /** Callback zum Abbrechen */
  onCancel?: () => void
}

const ACTION_LABELS: Record<BulkAction, string> = {
  move: "Verschiebe",
  tag: "Tagge",
  export: "Exportiere",
  delete: "Loesche",
  archive: "Archiviere",
  restore: "Stelle wieder her",
}

export function BulkActionProgress({
  action,
  progress,
  current,
  total,
  status,
  errorMessage,
  onCancel,
}: BulkActionProgressProps) {
  const label = ACTION_LABELS[action] || action

  return (
    <div
      className={cn(
        "fixed bottom-4 left-1/2 -translate-x-1/2 z-50",
        "flex flex-col gap-2 p-4 min-w-[300px]",
        "bg-background border rounded-lg shadow-lg"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          {label} {current} von {total}...
        </span>
        {status === "running" && onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Progress Bar */}
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full transition-all duration-300",
            status === "running" && "bg-primary",
            status === "success" && "bg-green-500",
            status === "error" && "bg-destructive"
          )}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Status Message */}
      {status === "success" && (
        <span className="text-sm text-green-600">
          Erfolgreich abgeschlossen
        </span>
      )}
      {status === "error" && errorMessage && (
        <span className="text-sm text-destructive">{errorMessage}</span>
      )}
    </div>
  )
}

export default BulkActionBar
