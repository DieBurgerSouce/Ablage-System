/**
 * MobileActionMenu - Kontextmenü für Mobile
 *
 * Phase 2.4: Mobile-First Gesten
 *
 * Features:
 * - Touch-optimierte Button-Größen (min 44px)
 * - Als Bottom Sheet oder Dropdown
 * - Gruppierte Aktionen
 * - Keyboard-Accessible
 */

import { useCallback } from "react"
import {
  Edit,
  Copy,
  Share2,
  Download,
  FolderInput,
  Tag,
  Archive,
  Trash2,
  MoreHorizontal,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { BottomSheet } from "./BottomSheet"

// =============================================================================
// Types
// =============================================================================

export type MenuActionId =
  | "edit"
  | "copy"
  | "share"
  | "download"
  | "move"
  | "tag"
  | "archive"
  | "delete"
  | "custom"

export interface MenuAction {
  id: MenuActionId | string
  label: string
  icon: LucideIcon
  /** Aktion ist deaktiviert */
  disabled?: boolean
  /** Destruktive Aktion (rot) */
  destructive?: boolean
  /** Gruppe */
  group?: "primary" | "secondary" | "danger"
  /** Versteckt */
  hidden?: boolean
}

export interface MobileActionMenuProps {
  /** Ist das Menü offen? */
  open: boolean
  /** Callback beim Schließen */
  onOpenChange: (open: boolean) => void
  /** Callback bei Aktionsauswahl */
  onAction: (actionId: string) => void
  /** Verfügbare Aktionen */
  actions?: MenuAction[]
  /** Titel */
  title?: string
  /** Untertitel */
  subtitle?: string
  /** Zusätzliche CSS-Klassen */
  className?: string
}

// =============================================================================
// Default Actions
// =============================================================================

const DEFAULT_ACTIONS: MenuAction[] = [
  { id: "edit", label: "Bearbeiten", icon: Edit, group: "primary" },
  { id: "copy", label: "Kopieren", icon: Copy, group: "primary" },
  { id: "share", label: "Teilen", icon: Share2, group: "primary" },
  { id: "download", label: "Herunterladen", icon: Download, group: "secondary" },
  { id: "move", label: "Verschieben", icon: FolderInput, group: "secondary" },
  { id: "tag", label: "Tags bearbeiten", icon: Tag, group: "secondary" },
  { id: "archive", label: "Archivieren", icon: Archive, group: "secondary" },
  { id: "delete", label: "Löschen", icon: Trash2, group: "danger", destructive: true },
]

// =============================================================================
// Component
// =============================================================================

export function MobileActionMenu({
  open,
  onOpenChange,
  onAction,
  actions = DEFAULT_ACTIONS,
  title,
  subtitle,
  className,
}: MobileActionMenuProps) {
  const handleAction = useCallback(
    (actionId: string) => {
      onAction(actionId)
      onOpenChange(false)
    },
    [onAction, onOpenChange]
  )

  // Aktionen nach Gruppen gruppieren
  const groupedActions = {
    primary: actions.filter((a) => !a.hidden && a.group === "primary"),
    secondary: actions.filter((a) => !a.hidden && a.group === "secondary"),
    danger: actions.filter((a) => !a.hidden && a.group === "danger"),
  }

  return (
    <BottomSheet
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={subtitle}
      defaultSnapPoint="min"
      snapPoints={["min"]}
      showHandle={true}
      showCloseButton={false}
      className={className}
    >
      <div className="flex flex-col gap-2 pb-4">
        {/* Primary Actions */}
        {groupedActions.primary.length > 0 && (
          <ActionGroup actions={groupedActions.primary} onAction={handleAction} />
        )}

        {/* Secondary Actions */}
        {groupedActions.secondary.length > 0 && (
          <>
            {groupedActions.primary.length > 0 && (
              <div className="h-px bg-border my-1" />
            )}
            <ActionGroup actions={groupedActions.secondary} onAction={handleAction} />
          </>
        )}

        {/* Danger Actions */}
        {groupedActions.danger.length > 0 && (
          <>
            <div className="h-px bg-border my-1" />
            <ActionGroup actions={groupedActions.danger} onAction={handleAction} />
          </>
        )}
      </div>
    </BottomSheet>
  )
}

// =============================================================================
// ActionGroup Component
// =============================================================================

interface ActionGroupProps {
  actions: MenuAction[]
  onAction: (actionId: string) => void
}

function ActionGroup({ actions, onAction }: ActionGroupProps) {
  return (
    <div className="flex flex-col">
      {actions.map((action) => (
        <ActionButton key={action.id} action={action} onClick={() => onAction(action.id)} />
      ))}
    </div>
  )
}

// =============================================================================
// ActionButton Component
// =============================================================================

interface ActionButtonProps {
  action: MenuAction
  onClick: () => void
}

function ActionButton({ action, onClick }: ActionButtonProps) {
  const Icon = action.icon

  return (
    <button
      onClick={onClick}
      disabled={action.disabled}
      className={cn(
        "flex items-center gap-4 w-full",
        "min-h-[44px] px-4 py-3", // Touch-Target min 44px
        "text-left text-base",
        "rounded-lg",
        "transition-colors",
        "active:bg-muted",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        action.destructive && "text-destructive"
      )}
    >
      <Icon
        className={cn(
          "h-5 w-5 shrink-0",
          action.destructive ? "text-destructive" : "text-muted-foreground"
        )}
      />
      <span className="flex-1">{action.label}</span>
    </button>
  )
}

// =============================================================================
// MobileActionTrigger - Button zum Öffnen des Menüs
// =============================================================================

export interface MobileActionTriggerProps {
  onClick: () => void
  className?: string
  children?: React.ReactNode
}

export function MobileActionTrigger({
  onClick,
  className,
  children,
}: MobileActionTriggerProps) {
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={onClick}
      className={cn("h-10 w-10", className)}
    >
      {children || <MoreHorizontal className="h-5 w-5" />}
      <span className="sr-only">Aktionen</span>
    </Button>
  )
}

export default MobileActionMenu
