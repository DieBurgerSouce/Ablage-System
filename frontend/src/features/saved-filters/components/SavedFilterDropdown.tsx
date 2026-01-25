/**
 * SavedFilterDropdown - Dropdown zur Auswahl gespeicherter Filter
 *
 * Phase 4.5: Frontend UX Enhancement
 */
import { useState } from "react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuPortal,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Filter,
  ChevronDown,
  Plus,
  Star,
  StarOff,
  Share2,
  Copy,
  Pencil,
  Trash2,
  User,
  Users,
  MoreHorizontal,
  Loader2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { SavedFilter } from "../api/saved-filters-api"

export interface SavedFilterDropdownProps {
  /** Liste der Filter */
  filters: SavedFilter[]
  /** Aktuell aktiver Filter */
  activeFilter?: SavedFilter | null
  /** Callback bei Filterauswahl */
  onSelectFilter: (filter: SavedFilter) => void
  /** Callback beim Zuruecksetzen */
  onClearFilter: () => void
  /** Callback zum Erstellen eines neuen Filters */
  onCreateFilter: () => void
  /** Callback zum Bearbeiten */
  onEditFilter: (filter: SavedFilter) => void
  /** Callback zum Loeschen */
  onDeleteFilter: (filter: SavedFilter) => void
  /** Callback zum Duplizieren */
  onDuplicateFilter: (filter: SavedFilter) => void
  /** Callback zum Setzen als Standard */
  onSetDefault: (filter: SavedFilter) => void
  /** Callback zum Entfernen des Standards */
  onClearDefault: () => void
  /** Wird geladen */
  isLoading?: boolean
  /** Deaktiviert */
  disabled?: boolean
  /** Klassennamen */
  className?: string
}

export function SavedFilterDropdown({
  filters,
  activeFilter,
  onSelectFilter,
  onClearFilter,
  onCreateFilter,
  onEditFilter,
  onDeleteFilter,
  onDuplicateFilter,
  onSetDefault,
  onClearDefault,
  isLoading = false,
  disabled = false,
  className,
}: SavedFilterDropdownProps) {
  const [open, setOpen] = useState(false)

  const ownFilters = filters.filter((f) => f.is_own)
  const sharedFilters = filters.filter((f) => !f.is_own)
  const hasFilters = filters.length > 0

  const handleSelect = (filter: SavedFilter) => {
    onSelectFilter(filter)
    setOpen(false)
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant={activeFilter ? "secondary" : "outline"}
          size="sm"
          className={cn("gap-2", className)}
          disabled={disabled || isLoading}
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Filter className="h-4 w-4" />
          )}
          <span className="hidden sm:inline">
            {activeFilter ? activeFilter.name : "Gespeicherte Filter"}
          </span>
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="w-64">
        {/* Header */}
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Gespeicherte Filter</span>
          {activeFilter && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() => {
                onClearFilter()
                setOpen(false)
              }}
            >
              Zuruecksetzen
            </Button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {/* Eigene Filter */}
        {ownFilters.length > 0 && (
          <>
            <DropdownMenuLabel className="flex items-center gap-2 text-xs text-muted-foreground">
              <User className="h-3 w-3" />
              Meine Filter
            </DropdownMenuLabel>
            {ownFilters.map((filter) => (
              <FilterMenuItem
                key={filter.id}
                filter={filter}
                isActive={activeFilter?.id === filter.id}
                onSelect={() => handleSelect(filter)}
                onEdit={() => onEditFilter(filter)}
                onDelete={() => onDeleteFilter(filter)}
                onDuplicate={() => onDuplicateFilter(filter)}
                onSetDefault={() => onSetDefault(filter)}
                onClearDefault={onClearDefault}
              />
            ))}
            <DropdownMenuSeparator />
          </>
        )}

        {/* Geteilte Filter */}
        {sharedFilters.length > 0 && (
          <>
            <DropdownMenuLabel className="flex items-center gap-2 text-xs text-muted-foreground">
              <Users className="h-3 w-3" />
              Geteilte Filter
            </DropdownMenuLabel>
            {sharedFilters.map((filter) => (
              <FilterMenuItem
                key={filter.id}
                filter={filter}
                isActive={activeFilter?.id === filter.id}
                onSelect={() => handleSelect(filter)}
                onDuplicate={() => onDuplicateFilter(filter)}
                onSetDefault={() => onSetDefault(filter)}
                onClearDefault={onClearDefault}
                isShared
              />
            ))}
            <DropdownMenuSeparator />
          </>
        )}

        {/* Leerzustand */}
        {!hasFilters && (
          <>
            <div className="py-4 text-center text-sm text-muted-foreground">
              Noch keine Filter gespeichert
            </div>
            <DropdownMenuSeparator />
          </>
        )}

        {/* Neuen Filter erstellen */}
        <DropdownMenuItem onClick={onCreateFilter} className="gap-2">
          <Plus className="h-4 w-4" />
          Aktuellen Filter speichern
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// =============================================================================
// Filter MenuItem Komponente
// =============================================================================

interface FilterMenuItemProps {
  filter: SavedFilter
  isActive: boolean
  onSelect: () => void
  onEdit?: () => void
  onDelete?: () => void
  onDuplicate: () => void
  onSetDefault: () => void
  onClearDefault: () => void
  isShared?: boolean
}

function FilterMenuItem({
  filter,
  isActive,
  onSelect,
  onEdit,
  onDelete,
  onDuplicate,
  onSetDefault,
  onClearDefault,
  isShared = false,
}: FilterMenuItemProps) {
  return (
    <div className="flex items-center gap-1 px-2 py-1">
      <DropdownMenuItem
        className={cn(
          "flex-1 gap-2",
          isActive && "bg-accent"
        )}
        onClick={onSelect}
      >
        <div className="flex flex-1 items-center gap-2 min-w-0">
          <span className="truncate">{filter.name}</span>
          {filter.is_default && (
            <Badge variant="secondary" className="h-4 px-1 text-[10px]">
              Standard
            </Badge>
          )}
          {filter.is_shared && filter.is_own && (
            <Share2 className="h-3 w-3 text-muted-foreground flex-shrink-0" />
          )}
        </div>
      </DropdownMenuItem>

      {/* Actions Sub-Menu */}
      <DropdownMenuSub>
        <DropdownMenuSubTrigger className="h-7 w-7 p-0 data-[state=open]:bg-accent">
          <MoreHorizontal className="h-4 w-4" />
        </DropdownMenuSubTrigger>
        <DropdownMenuPortal>
          <DropdownMenuSubContent>
            {!isShared && onEdit && (
              <DropdownMenuItem onClick={onEdit} className="gap-2">
                <Pencil className="h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={onDuplicate} className="gap-2">
              <Copy className="h-4 w-4" />
              Duplizieren
            </DropdownMenuItem>
            {filter.is_default ? (
              <DropdownMenuItem onClick={onClearDefault} className="gap-2">
                <StarOff className="h-4 w-4" />
                Standard entfernen
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onClick={onSetDefault} className="gap-2">
                <Star className="h-4 w-4" />
                Als Standard setzen
              </DropdownMenuItem>
            )}
            {!isShared && onDelete && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={onDelete}
                  className="gap-2 text-destructive focus:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                  Loeschen
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuSubContent>
        </DropdownMenuPortal>
      </DropdownMenuSub>
    </div>
  )
}
