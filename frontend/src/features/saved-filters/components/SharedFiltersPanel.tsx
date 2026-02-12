/**
 * SharedFiltersPanel - Panel zur Anzeige geteilter Filter
 *
 * Phase 4.5: Frontend UX Enhancement
 */
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Users,
  Filter,
  Star,
  Copy,
  Clock,
  TrendingUp,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { SavedFilter } from "../api/saved-filters-api"

export interface SharedFiltersPanelProps {
  /** Geteilte Filter */
  filters: SavedFilter[]
  /** Aktuell aktiver Filter */
  activeFilter?: SavedFilter | null
  /** Callback bei Filterauswahl */
  onSelectFilter: (filter: SavedFilter) => void
  /** Callback zum Duplizieren */
  onDuplicateFilter: (filter: SavedFilter) => void
  /** Callback zum Setzen als Standard */
  onSetDefault: (filter: SavedFilter) => void
  /** Zusätzliche Klassennamen */
  className?: string
}

export function SharedFiltersPanel({
  filters,
  activeFilter,
  onSelectFilter,
  onDuplicateFilter,
  onSetDefault,
  className,
}: SharedFiltersPanelProps) {
  if (filters.length === 0) {
    return (
      <Card className={cn("", className)}>
        <CardContent className="flex flex-col items-center justify-center py-8 text-center">
          <Users className="h-10 w-10 text-muted-foreground/40 mb-3" />
          <p className="text-sm text-muted-foreground">
            Keine geteilten Filter verfügbar
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Teilen Sie einen Filter, damit Ihr Team ihn nutzen kann
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn("", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="h-4 w-4" />
          Geteilte Filter
        </CardTitle>
        <CardDescription>
          Filter, die von Teammitgliedern geteilt wurden
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[300px]">
          <div className="space-y-1 p-4 pt-0">
            {filters.map((filter) => (
              <SharedFilterCard
                key={filter.id}
                filter={filter}
                isActive={activeFilter?.id === filter.id}
                onSelect={() => onSelectFilter(filter)}
                onDuplicate={() => onDuplicateFilter(filter)}
                onSetDefault={() => onSetDefault(filter)}
              />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

// =============================================================================
// SharedFilterCard Komponente
// =============================================================================

interface SharedFilterCardProps {
  filter: SavedFilter
  isActive: boolean
  onSelect: () => void
  onDuplicate: () => void
  onSetDefault: () => void
}

function SharedFilterCard({
  filter,
  isActive,
  onSelect,
  onDuplicate,
  onSetDefault,
}: SharedFilterCardProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Nie"
    const date = new Date(dateStr)
    return date.toLocaleDateString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    })
  }

  return (
    <div
      className={cn(
        "rounded-lg border p-3 transition-colors cursor-pointer hover:bg-accent/50",
        isActive && "border-primary bg-accent"
      )}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="font-medium truncate">{filter.name}</span>
            {filter.is_default && (
              <Badge variant="secondary" className="h-5 flex-shrink-0">
                <Star className="h-3 w-3 mr-1" />
                Standard
              </Badge>
            )}
          </div>
          {filter.description && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {filter.description}
            </p>
          )}
          <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <TrendingUp className="h-3 w-3" />
              {filter.use_count}x genutzt
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Zuletzt: {formatDate(filter.last_used_at)}
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-1 flex-shrink-0">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={(e) => {
              e.stopPropagation()
              onDuplicate()
            }}
          >
            <Copy className="h-3 w-3 mr-1" />
            Kopieren
          </Button>
          {!filter.is_default && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              onClick={(e) => {
                e.stopPropagation()
                onSetDefault()
              }}
            >
              <Star className="h-3 w-3 mr-1" />
              Standard
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
