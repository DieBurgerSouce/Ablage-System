/**
 * Enhanced Command Palette
 *
 * Erweiterte Befehlspalette mit:
 * - Fuzzy Search (via cmdk)
 * - Recency Ranking (Local Storage)
 * - Kategorien mit Icons
 * - Keyboard Shortcuts
 * - Quick Actions (Upload, Create, etc.)
 * - Dokumenten-Schnellsuche
 *
 * Phase 4.3 der Feature-Roadmap (Januar 2026)
 */

import * as React from "react"
import { useNavigate } from "@tanstack/react-router"
import { useDebounce } from "@/hooks/use-debounce"
import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api/client"
import { useTheme } from "@/lib/theme/ThemeContext"
import { useAuth } from "@/lib/auth/AuthContext"
import { toast } from "sonner"

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
import {
    LayoutDashboard,
    FileText,
    FolderOpen,
    Search,
    Upload,
    Settings,
    Sun,
    Moon,
    Laptop,
    LogOut,
    Calculator,
    Receipt,
    Users,
    Building2,
    ShieldCheck,
    Link2,
    Truck,
    AlertTriangle,
    Clock,
    Star,
    Zap,
    Plus,
    History,
    ArrowRight,
    Loader2,
    type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"

// ==================== Types ====================

interface CommandAction {
    id: string
    label: string
    description?: string
    icon: LucideIcon
    shortcut?: string
    category: CommandCategory
    keywords?: string[]
    action: () => void | Promise<void>
    /** If true, shows at top when recently used */
    trackRecency?: boolean
}

type CommandCategory =
    | 'recent'
    | 'quick-actions'
    | 'navigation'
    | 'documents'
    | 'admin'
    | 'appearance'
    | 'settings'

interface DocumentResult {
    id: string
    title: string
    document_type?: string
    created_at: string
}

// ==================== Constants ====================

const STORAGE_KEY = 'command-palette-recent'
const MAX_RECENT = 5

const CATEGORY_CONFIG: Record<CommandCategory, { label: string; icon: LucideIcon }> = {
    'recent': { label: 'Zuletzt verwendet', icon: History },
    'quick-actions': { label: 'Schnellaktionen', icon: Zap },
    'navigation': { label: 'Navigation', icon: ArrowRight },
    'documents': { label: 'Dokumente', icon: FileText },
    'admin': { label: 'Administration', icon: ShieldCheck },
    'appearance': { label: 'Darstellung', icon: Sun },
    'settings': { label: 'Einstellungen', icon: Settings },
}

// ==================== Hooks ====================

function useRecentCommands() {
    const [recent, setRecent] = React.useState<string[]>([])

    React.useEffect(() => {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
            try {
                setRecent(JSON.parse(stored))
            } catch {
                setRecent([])
            }
        }
    }, [])

    const addRecent = React.useCallback((id: string) => {
        setRecent((prev) => {
            const filtered = prev.filter((item) => item !== id)
            const updated = [id, ...filtered].slice(0, MAX_RECENT)
            localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
            return updated
        })
    }, [])

    return { recent, addRecent }
}

function useDocumentSearch(query: string) {
    const debouncedQuery = useDebounce(query, 300)
    const enabled = debouncedQuery.length >= 2

    return useQuery({
        queryKey: ['command-document-search', debouncedQuery],
        queryFn: async () => {
            const response = await apiClient.get<{ items: DocumentResult[] }>(
                '/documents',
                { params: { q: debouncedQuery, limit: 5 } }
            )
            return response.data.items ?? []
        },
        enabled,
        staleTime: 1000 * 30, // 30 seconds
    })
}

// ==================== Component ====================

export function EnhancedCommandPalette() {
    const [open, setOpen] = React.useState(false)
    const [inputValue, setInputValue] = React.useState("")
    const navigate = useNavigate()
    const { setDisplayMode } = useTheme()
    const { logout, user } = useAuth()
    const { recent, addRecent } = useRecentCommands()

    // Document search
    const { data: searchResults, isLoading: isSearching } = useDocumentSearch(inputValue)

    // Keyboard shortcut to open
    React.useEffect(() => {
        const down = (e: KeyboardEvent) => {
            // Cmd+K or Ctrl+K to open
            if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                setOpen((open) => !open)
            }
            // Cmd+Shift+P for "command palette" style
            if (e.key === "p" && (e.metaKey || e.ctrlKey) && e.shiftKey) {
                e.preventDefault()
                setOpen(true)
            }
        }

        document.addEventListener("keydown", down)
        return () => document.removeEventListener("keydown", down)
    }, [])

    // Clear input when closed
    React.useEffect(() => {
        if (!open) {
            setInputValue("")
        }
    }, [open])

    // Run command with recency tracking
    const runCommand = React.useCallback(
        (action: CommandAction) => {
            setOpen(false)
            if (action.trackRecency !== false) {
                addRecent(action.id)
            }
            action.action()
        },
        [addRecent]
    )

    // All available commands
    const allCommands: CommandAction[] = React.useMemo(() => {
        const isAdmin = user?.role === 'admin'

        return [
            // Quick Actions
            {
                id: 'quick-upload',
                label: 'Neues Dokument hochladen',
                description: 'Dokument per Drag & Drop hochladen',
                icon: Upload,
                shortcut: '⌘U',
                category: 'quick-actions',
                keywords: ['upload', 'neu', 'hochladen', 'datei'],
                action: () => navigate({ to: '/upload' }),
            },
            {
                id: 'quick-search',
                label: 'Dokumente durchsuchen',
                description: 'Volltextsuche in allen Dokumenten',
                icon: Search,
                shortcut: '/',
                category: 'quick-actions',
                keywords: ['suche', 'finden', 'search'],
                action: () => navigate({ to: '/search' }),
            },
            {
                id: 'quick-validation',
                label: 'Validierung öffnen',
                description: 'Ausstehende Validierungen bearbeiten',
                icon: Calculator,
                category: 'quick-actions',
                keywords: ['prüfen', 'validieren', 'check'],
                action: () => navigate({ to: '/validation' }),
            },

            // Navigation
            {
                id: 'nav-dashboard',
                label: 'Dashboard',
                icon: LayoutDashboard,
                category: 'navigation',
                keywords: ['start', 'übersicht', 'home'],
                action: () => navigate({ to: '/' }),
            },
            {
                id: 'nav-documents',
                label: 'Dokumente',
                icon: FileText,
                category: 'navigation',
                keywords: ['liste', 'alle'],
                action: () => navigate({ to: '/documents' }),
            },
            {
                id: 'nav-ablage',
                label: 'Ablage',
                icon: FolderOpen,
                category: 'navigation',
                keywords: ['ordner', 'archiv'],
                action: () => navigate({ to: '/ablage' }),
            },
            {
                id: 'nav-chains',
                label: 'Auftragsketten',
                description: 'Angebot → Auftrag → Lieferschein → Rechnung',
                icon: Link2,
                category: 'navigation',
                keywords: ['kette', 'verkettung', 'chain'],
                action: () => navigate({ to: '/document-chains' }),
            },
            {
                id: 'nav-invoices',
                label: 'Rechnungen',
                icon: Receipt,
                category: 'navigation',
                keywords: ['rechnung', 'invoice', 'faktura'],
                action: () => navigate({ to: '/admin/rechnungen' }),
            },
            {
                id: 'nav-shipments',
                label: 'Sendungsverfolgung',
                icon: Truck,
                category: 'navigation',
                keywords: ['tracking', 'versand', 'lieferung', 'paket'],
                action: () => navigate({ to: '/shipments' }),
            },
            {
                id: 'nav-holding',
                label: 'Holding Dashboard',
                icon: Building2,
                category: 'navigation',
                keywords: ['multi', 'firma', 'company', 'konsolidiert'],
                action: () => navigate({ to: '/holding' }),
            },

            // Admin (only for admins)
            ...(isAdmin
                ? [
                    {
                        id: 'admin-users',
                        label: 'Benutzerverwaltung',
                        icon: Users,
                        category: 'admin' as CommandCategory,
                        keywords: ['user', 'benutzer', 'mitarbeiter'],
                        action: () => navigate({ to: '/admin/users' }),
                    },
                    {
                        id: 'admin-dunning',
                        label: 'Mahnwesen',
                        icon: AlertTriangle,
                        category: 'admin' as CommandCategory,
                        keywords: ['mahnung', 'inkasso'],
                        action: () => navigate({ to: '/admin/mahnungen' }),
                    },
                    {
                        id: 'admin-ocr',
                        label: 'OCR Training',
                        icon: Calculator,
                        category: 'admin' as CommandCategory,
                        keywords: ['training', 'learning', 'ml'],
                        action: () => navigate({ to: '/admin/ocr-training' }),
                    },
                    {
                        id: 'admin-dlp',
                        label: 'DLP Policies',
                        icon: ShieldCheck,
                        category: 'admin' as CommandCategory,
                        keywords: ['sicherheit', 'data loss', 'schutz'],
                        action: () => navigate({ to: '/admin/dlp' }),
                    },
                ]
                : []),

            // Appearance
            {
                id: 'theme-light',
                label: 'Helles Design',
                icon: Sun,
                category: 'appearance',
                keywords: ['light', 'hell', 'weiß'],
                action: () => {
                    setDisplayMode('light')
                    toast.success('Design geändert', { description: 'Helles Design aktiviert' })
                },
                trackRecency: false,
            },
            {
                id: 'theme-dark',
                label: 'Dunkles Design',
                icon: Moon,
                category: 'appearance',
                keywords: ['dark', 'dunkel', 'schwarz', 'nacht'],
                action: () => {
                    setDisplayMode('dark')
                    toast.success('Design geändert', { description: 'Dunkles Design aktiviert' })
                },
                trackRecency: false,
            },
            {
                id: 'theme-contrast-light',
                label: 'Hoher Kontrast (Hell)',
                icon: Laptop,
                category: 'appearance',
                keywords: ['kontrast', 'accessibility', 'a11y'],
                action: () => {
                    setDisplayMode('whitescreen')
                    toast.success('Design geändert', { description: 'Hoher Kontrast (Hell) aktiviert' })
                },
                trackRecency: false,
            },
            {
                id: 'theme-contrast-dark',
                label: 'Hoher Kontrast (Dunkel)',
                icon: Laptop,
                category: 'appearance',
                keywords: ['kontrast', 'accessibility', 'a11y'],
                action: () => {
                    setDisplayMode('blackscreen')
                    toast.success('Design geändert', { description: 'Hoher Kontrast (Dunkel) aktiviert' })
                },
                trackRecency: false,
            },

            // Settings
            {
                id: 'settings-profile',
                label: 'Einstellungen',
                icon: Settings,
                shortcut: '⌘,',
                category: 'settings',
                keywords: ['profil', 'konto', 'account'],
                action: () => navigate({ to: '/settings' }),
            },
            {
                id: 'settings-logout',
                label: 'Abmelden',
                icon: LogOut,
                category: 'settings',
                keywords: ['logout', 'signout', 'raus'],
                action: () => {
                    logout()
                    toast.info('Abgemeldet', { description: 'Sie wurden erfolgreich abgemeldet.' })
                },
                trackRecency: false,
            },
        ]
    }, [navigate, setDisplayMode, logout, user?.role])

    // Group commands by category
    const commandsByCategory = React.useMemo(() => {
        const grouped = new Map<CommandCategory, CommandAction[]>()

        // Add recent commands first
        if (recent.length > 0 && !inputValue) {
            const recentCommands = recent
                .map((id) => allCommands.find((cmd) => cmd.id === id))
                .filter((cmd): cmd is CommandAction => !!cmd)
            if (recentCommands.length > 0) {
                grouped.set('recent', recentCommands)
            }
        }

        // Group remaining commands
        for (const cmd of allCommands) {
            if (!grouped.has(cmd.category)) {
                grouped.set(cmd.category, [])
            }
            grouped.get(cmd.category)!.push(cmd)
        }

        return grouped
    }, [allCommands, recent, inputValue])

    // Categories to show (exclude recent when searching)
    const categoriesToShow: CommandCategory[] = inputValue
        ? ['quick-actions', 'navigation', 'documents', 'admin', 'appearance', 'settings']
        : ['recent', 'quick-actions', 'navigation', 'admin', 'appearance', 'settings']

    return (
        <CommandDialog open={open} onOpenChange={setOpen}>
            <CommandInput
                placeholder="Befehl eingeben oder Dokument suchen..."
                value={inputValue}
                onValueChange={setInputValue}
            />
            <CommandList className="max-h-[400px]">
                <CommandEmpty>
                    {isSearching ? (
                        <div className="flex items-center justify-center gap-2 py-6">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>Suche...</span>
                        </div>
                    ) : (
                        <div className="py-6 text-center">
                            <p>Keine Ergebnisse gefunden.</p>
                            <p className="text-sm text-muted-foreground mt-1">
                                Versuchen Sie einen anderen Suchbegriff.
                            </p>
                        </div>
                    )}
                </CommandEmpty>

                {/* Document Search Results */}
                {searchResults && searchResults.length > 0 && (
                    <>
                        <CommandGroup heading="Dokumente">
                            {searchResults.map((doc) => (
                                <CommandItem
                                    key={doc.id}
                                    onSelect={() => {
                                        setOpen(false)
                                        navigate({ to: '/documents/$documentId', params: { documentId: doc.id } })
                                    }}
                                    className="flex items-center gap-3"
                                >
                                    <FileText className="h-4 w-4 flex-shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <p className="truncate font-medium">{doc.title}</p>
                                        <p className="text-xs text-muted-foreground">
                                            {doc.document_type ?? 'Dokument'} •{' '}
                                            {new Date(doc.created_at).toLocaleDateString('de-DE')}
                                        </p>
                                    </div>
                                </CommandItem>
                            ))}
                        </CommandGroup>
                        <CommandSeparator />
                    </>
                )}

                {/* Grouped Commands */}
                {categoriesToShow.map((category) => {
                    const commands = commandsByCategory.get(category)
                    if (!commands || commands.length === 0) return null

                    const config = CATEGORY_CONFIG[category]
                    const CategoryIcon = config.icon

                    return (
                        <React.Fragment key={category}>
                            <CommandGroup
                                heading={
                                    <div className="flex items-center gap-2">
                                        <CategoryIcon className="h-3 w-3" />
                                        {config.label}
                                    </div>
                                }
                            >
                                {commands.map((cmd) => {
                                    const Icon = cmd.icon
                                    return (
                                        <CommandItem
                                            key={cmd.id}
                                            value={`${cmd.label} ${cmd.keywords?.join(' ') ?? ''}`}
                                            onSelect={() => runCommand(cmd)}
                                            className="flex items-center gap-3"
                                        >
                                            <Icon className="h-4 w-4 flex-shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <span>{cmd.label}</span>
                                                    {category === 'recent' && (
                                                        <Badge variant="secondary" className="text-[10px] px-1 py-0">
                                                            <Clock className="h-2 w-2 mr-0.5" />
                                                            Zuletzt
                                                        </Badge>
                                                    )}
                                                </div>
                                                {cmd.description && (
                                                    <p className="text-xs text-muted-foreground truncate">
                                                        {cmd.description}
                                                    </p>
                                                )}
                                            </div>
                                            {cmd.shortcut && (
                                                <CommandShortcut>{cmd.shortcut}</CommandShortcut>
                                            )}
                                        </CommandItem>
                                    )
                                })}
                            </CommandGroup>
                            <CommandSeparator />
                        </React.Fragment>
                    )
                })}
            </CommandList>

            {/* Footer hint */}
            <div className="border-t px-3 py-2 text-xs text-muted-foreground flex items-center justify-between">
                <div className="flex gap-4">
                    <span>
                        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">↑</kbd>
                        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] ml-0.5">↓</kbd>
                        <span className="ml-1">navigieren</span>
                    </span>
                    <span>
                        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">↵</kbd>
                        <span className="ml-1">auswählen</span>
                    </span>
                    <span>
                        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">esc</kbd>
                        <span className="ml-1">schließen</span>
                    </span>
                </div>
                <div>
                    <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">⌘K</kbd>
                    <span className="ml-1">zum Öffnen</span>
                </div>
            </div>
        </CommandDialog>
    )
}

export default EnhancedCommandPalette
