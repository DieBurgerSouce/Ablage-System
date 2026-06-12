import * as React from "react"
import {
    FileText,
    File,
    Search,
    Sun,
    Moon,
    Laptop,
    LogOut,
    Settings,
    LayoutDashboard,
    FolderOpen,
    Upload,
    Clock,
    Lightbulb,
    User,
    Building2,
    X,
    Loader2,
} from "lucide-react"

import {
    CommandDialog,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
    CommandSeparator,
    CommandShortcut,
} from "@/components/ui/command"
import { Badge } from "@/components/ui/badge"
import { useNavigate } from "@tanstack/react-router"
import { useTheme } from "@/lib/theme/ThemeContext"
import { useAuth } from "@/lib/auth/AuthContext"
import { useSpotlightSearch } from "@/features/search/hooks/use-spotlight-search"

// ==================== Helpers ====================

/** Deutsches relatives Datum */
function formatRelativeDate(dateString: string): string {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMinutes = Math.floor(diffMs / 60_000)
    const diffHours = Math.floor(diffMs / 3_600_000)
    const diffDays = Math.floor(diffMs / 86_400_000)

    if (diffMinutes < 1) return "gerade eben"
    if (diffMinutes < 60) return `vor ${diffMinutes} Min.`
    if (diffHours < 24) return `vor ${diffHours} Std.`
    if (diffDays < 7) return `vor ${diffDays} Tag${diffDays > 1 ? "en" : ""}`
    if (diffDays < 30) {
        const weeks = Math.floor(diffDays / 7)
        return `vor ${weeks} Woche${weeks > 1 ? "n" : ""}`
    }
    return date.toLocaleDateString("de-DE")
}

/** Icon basierend auf Dokumenttyp */
function documentTypeIcon(docType: string) {
    const lower = docType.toLowerCase()
    if (lower.includes("rechnung") || lower.includes("invoice")) {
        return <FileText className="mr-2 h-4 w-4 shrink-0 text-blue-500" />
    }
    return <File className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
}

/** Konfidenz-Badge Farbe */
function confidenceBadgeVariant(score: number): string {
    if (score >= 0.9) return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
    if (score >= 0.7) return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
    return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
}

/** Suchmodus-Label */
function searchModeLabel(mode: "nlq" | "keyword" | undefined): string {
    if (mode === "nlq") return "Natuerliche Sprache"
    if (mode === "keyword") return "Schluesselwort"
    return ""
}

/** Textvorschau kuerzen */
function truncateText(text: string | undefined, maxLen: number): string {
    if (!text) return ""
    if (text.length <= maxLen) return text
    return text.slice(0, maxLen) + "..."
}

// ==================== Constants ====================

const MAX_RECENT = 5
const MAX_AUTOCOMPLETE = 5
const MAX_DOCUMENTS = 8
const MAX_ENTITIES = 5

// ==================== Component ====================

export function GlobalCommandDialog() {
    const [open, setOpen] = React.useState(false)
    const [query, setQuery] = React.useState("")
    const navigate = useNavigate()
    const { setDisplayMode } = useTheme()
    const { logout } = useAuth()

    const {
        results,
        entities,
        suggestions,
        interpretation,
        searchTimeMs,
        searchMode,
        isSearchLoading,
        isAutocompleteLoading,
        recentSearches: {
            recentSearches,
            addRecentSearch,
            removeRecentSearch,
            clearRecentSearches,
        },
    } = useSpotlightSearch(query)

    // Cmd+K / Ctrl+K Shortcut
    React.useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                setOpen((prev) => !prev)
            }
        }
        document.addEventListener("keydown", down)
        return () => document.removeEventListener("keydown", down)
    }, [])

    // Reset query when dialog closes
    React.useEffect(() => {
        if (!open) {
            setQuery("")
        }
    }, [open])

    const runCommand = React.useCallback((command: () => unknown) => {
        setOpen(false)
        command()
    }, [])

    const handleSearchSubmit = React.useCallback(() => {
        const trimmed = query.trim()
        if (trimmed.length >= 2) {
            addRecentSearch(trimmed)
            runCommand(() => navigate({ to: "/search", search: { q: trimmed } }))
        }
    }, [query, addRecentSearch, runCommand, navigate])

    const hasQuery = query.trim().length >= 2
    const showRecent = !hasQuery && recentSearches.length > 0
    const showAutocomplete = hasQuery && suggestions.length > 0
    const showResults = hasQuery && results.length > 0
    const showEntities = hasQuery && entities.length > 0
    const isAnyLoading = isSearchLoading || isAutocompleteLoading

    return (
        <CommandDialog open={open} onOpenChange={setOpen}>
            <CommandInput
                placeholder="Suchen oder Befehl eingeben..."
                value={query}
                onValueChange={setQuery}
                onKeyDown={(e) => {
                    if (e.key === "Enter" && hasQuery) {
                        e.preventDefault()
                        handleSearchSubmit()
                    }
                }}
            />

            {/* Statusleiste: Modus + Suchzeit */}
            {hasQuery && (searchMode || searchTimeMs !== undefined) && (
                <div className="flex items-center gap-2 border-b px-3 py-1.5 text-xs text-muted-foreground">
                    {searchMode && (
                        <span>Modus: {searchModeLabel(searchMode)}</span>
                    )}
                    {searchTimeMs !== undefined && (
                        <span>Ausfuehrung: {searchTimeMs}ms</span>
                    )}
                    {isAnyLoading && (
                        <Loader2 className="ml-auto h-3 w-3 animate-spin" />
                    )}
                </div>
            )}

            <CommandList className="max-h-[400px]">
                <CommandEmpty>
                    {isAnyLoading
                        ? "Suche laeuft..."
                        : "Keine Ergebnisse gefunden."}
                </CommandEmpty>

                {/* ===== Letzte Suchen (kein Query) ===== */}
                {showRecent && (
                    <>
                        <CommandGroup
                            heading={
                                <span className="flex items-center justify-between">
                                    <span>Letzte Suchen</span>
                                    <button
                                        type="button"
                                        className="text-xs text-muted-foreground hover:text-foreground"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            clearRecentSearches()
                                        }}
                                    >
                                        Alle loeschen
                                    </button>
                                </span>
                            }
                        >
                            {recentSearches.slice(0, MAX_RECENT).map((recent) => (
                                <CommandItem
                                    key={recent.id}
                                    value={`recent-${recent.query}`}
                                    onSelect={() => {
                                        setQuery(recent.query)
                                    }}
                                >
                                    <Clock className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
                                    <span className="flex-1">{recent.query}</span>
                                    <button
                                        type="button"
                                        className="ml-2 rounded p-0.5 text-muted-foreground hover:text-foreground"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            removeRecentSearch(recent.id)
                                        }}
                                    >
                                        <X className="h-3 w-3" />
                                    </button>
                                </CommandItem>
                            ))}
                        </CommandGroup>
                        <CommandSeparator />
                    </>
                )}

                {/* ===== Autocomplete-Vorschlaege ===== */}
                {showAutocomplete && (
                    <>
                        <CommandGroup heading="Vorschlaege">
                            {suggestions.slice(0, MAX_AUTOCOMPLETE).map((suggestion, idx) => (
                                <CommandItem
                                    key={`suggestion-${idx}`}
                                    value={`suggestion-${suggestion.text}`}
                                    onSelect={() => {
                                        setQuery(suggestion.text)
                                    }}
                                >
                                    <Lightbulb className="mr-2 h-4 w-4 shrink-0 text-amber-500" />
                                    <span>{suggestion.text}</span>
                                    {suggestion.type !== "suggestion" && (
                                        <Badge variant="outline" className="ml-auto text-xs">
                                            {suggestion.type === "entity"
                                                ? "Entitaet"
                                                : suggestion.type === "document_type"
                                                  ? "Dokumenttyp"
                                                  : "Zuletzt"}
                                        </Badge>
                                    )}
                                </CommandItem>
                            ))}
                        </CommandGroup>
                        <CommandSeparator />
                    </>
                )}

                {/* ===== Dokument-Ergebnisse ===== */}
                {showResults && (
                    <>
                        <CommandGroup heading="Dokumente">
                            {results.slice(0, MAX_DOCUMENTS).map((result) => (
                                <CommandItem
                                    key={result.document_id}
                                    value={`doc-${result.filename}`}
                                    onSelect={() => {
                                        addRecentSearch(query.trim())
                                        runCommand(() =>
                                            navigate({
                                                to: "/documents/$documentId",
                                                params: { documentId: result.document_id },
                                            })
                                        )
                                    }}
                                >
                                    <div className="flex w-full items-start gap-2">
                                        {documentTypeIcon(result.document_type)}
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <span className="font-medium truncate">
                                                    {result.filename}
                                                </span>
                                                <Badge variant="secondary" className="text-xs shrink-0">
                                                    {result.document_type}
                                                </Badge>
                                                <Badge
                                                    variant="outline"
                                                    className={`text-xs shrink-0 ${confidenceBadgeVariant(result.relevance_score)}`}
                                                >
                                                    {Math.round(result.relevance_score * 100)}%
                                                </Badge>
                                            </div>
                                            {(result.highlight || result.matched_text) && (
                                                <p className="text-xs text-muted-foreground mt-0.5 truncate">
                                                    {truncateText(
                                                        result.highlight || result.matched_text,
                                                        80
                                                    )}
                                                </p>
                                            )}
                                        </div>
                                        <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                                            {formatRelativeDate(result.created_at)}
                                        </span>
                                    </div>
                                </CommandItem>
                            ))}
                        </CommandGroup>
                        <CommandSeparator />
                    </>
                )}

                {/* ===== Kunden & Lieferanten ===== */}
                {showEntities && (
                    <>
                        <CommandGroup heading="Kunden & Lieferanten">
                            {entities.slice(0, MAX_ENTITIES).map((entity) => {
                                const isCustomer = entity.entity_type === "customer"
                                const entityNumber = isCustomer
                                    ? entity.customer_number
                                    : entity.supplier_number
                                const entityLabel = isCustomer ? "Kunde" : "Lieferant"

                                return (
                                    <CommandItem
                                        key={entity.entity_id}
                                        value={`entity-${entity.entity_name}`}
                                        onSelect={() => {
                                            addRecentSearch(query.trim())
                                            runCommand(() =>
                                                isCustomer
                                                    ? navigate({
                                                          to: "/kunden/$customerId",
                                                          params: { customerId: entity.entity_id },
                                                      })
                                                    : navigate({
                                                          to: "/lieferanten/$supplierId",
                                                          params: { supplierId: entity.entity_id },
                                                      })
                                            )
                                        }}
                                    >
                                        {isCustomer ? (
                                            <User className="mr-2 h-4 w-4 shrink-0 text-blue-500" />
                                        ) : (
                                            <Building2 className="mr-2 h-4 w-4 shrink-0 text-orange-500" />
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <span className="font-medium">{entity.entity_name}</span>
                                            <span className="ml-2 text-xs text-muted-foreground">
                                                {entityLabel}
                                                {entityNumber ? ` #${entityNumber}` : ""}
                                            </span>
                                        </div>
                                        {entity.match_confidence >= 0.8 && (
                                            <Badge
                                                variant="outline"
                                                className="text-xs ml-auto bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
                                            >
                                                {Math.round(entity.match_confidence * 100)}%
                                            </Badge>
                                        )}
                                    </CommandItem>
                                )
                            })}
                        </CommandGroup>
                        <CommandSeparator />
                    </>
                )}

                {/* ===== Navigation ===== */}
                <CommandGroup heading="Navigation">
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/" }))}>
                        <LayoutDashboard className="mr-2 h-4 w-4" />
                        <span>Dashboard</span>
                        <CommandShortcut>Ctrl+D</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/kunden" }))}>
                        <FolderOpen className="mr-2 h-4 w-4" />
                        <span>Ablage</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/search" }))}>
                        <FileText className="mr-2 h-4 w-4" />
                        <span>Dokumente</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/upload" }))}>
                        <Upload className="mr-2 h-4 w-4" />
                        <span>Neuer Upload</span>
                        <CommandShortcut>Ctrl+U</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/search" }))}>
                        <Search className="mr-2 h-4 w-4" />
                        <span>Suche</span>
                    </CommandItem>
                </CommandGroup>
                <CommandSeparator />

                {/* ===== Darstellung ===== */}
                <CommandGroup heading="Darstellung">
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("light"))}>
                        <Sun className="mr-2 h-4 w-4" />
                        <span>Hell</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("dark"))}>
                        <Moon className="mr-2 h-4 w-4" />
                        <span>Dunkel</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("whitescreen"))}>
                        <Laptop className="mr-2 h-4 w-4" />
                        <span>High Contrast (Hell)</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("blackscreen"))}>
                        <Laptop className="mr-2 h-4 w-4" />
                        <span>High Contrast (Dunkel)</span>
                    </CommandItem>
                </CommandGroup>
                <CommandSeparator />

                {/* ===== Einstellungen ===== */}
                <CommandGroup heading="Einstellungen">
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/settings" }))}>
                        <Settings className="mr-2 h-4 w-4" />
                        <span>Einstellungen</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => logout())}>
                        <LogOut className="mr-2 h-4 w-4" />
                        <span>Abmelden</span>
                    </CommandItem>
                </CommandGroup>
            </CommandList>
        </CommandDialog>
    )
}
