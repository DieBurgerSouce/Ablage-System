import { Link, useLocation } from '@tanstack/react-router'
import { ChevronRight, Home } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Route label mapping for German translations
 */
const ROUTE_LABELS: Record<string, string> = {
    // Main routes
    '/': 'Startseite',
    '/search': 'Suche',
    '/upload': 'Upload',
    '/chat': 'Chat',
    '/monitoring': 'Monitoring',
    '/automation': 'Automatisierung',
    '/relationships': 'Beziehungen',

    // Admin routes
    '/admin': 'Administration',
    '/admin/users': 'Benutzer',
    '/admin/settings': 'Einstellungen',
    '/admin/tunes': 'Tuning',
    '/admin/ocr-training': 'OCR Training',
    '/admin/ocr-review': 'OCR Review',
    '/admin/ocr-backends': 'OCR Backends',
    '/admin/job-queue': 'Job Queue',

    // Banking routes
    '/admin/banking': 'Banking',
    '/admin/banking/accounts': 'Konten',
    '/admin/banking/transactions': 'Transaktionen',
    '/admin/banking/import': 'Import',
    '/admin/banking/reconciliation': 'Abgleich',
    '/admin/banking/payments': 'Zahlungen',
    '/admin/banking/skonto': 'Skonto',

    // Mahnwesen
    '/admin/mahnungen': 'Mahnwesen',
    '/admin/mahnungen/aktiv': 'Aktive Mahnungen',
    '/admin/mahnungen/kanban': 'Kanban',
    '/admin/mahnungen/eskalation': 'Eskalation',
    '/admin/mahnungen/mahnstopp': 'Mahnstopp',
    '/admin/mahnungen/aufgaben': 'Aufgaben',
    '/admin/mahnungen/einstellungen': 'Einstellungen',

    // DATEV
    '/admin/datev': 'DATEV',
    '/admin/datev/config': 'Konfiguration',
    '/admin/datev/vendors': 'Lieferanten',
    '/admin/datev/export': 'Export',
    '/admin/datev/history': 'Verlauf',

    // Business entities
    '/kunden': 'Kunden',
    '/lieferanten': 'Lieferanten',
    '/document-groups': 'Dokumentengruppen',

    // Ablage dynamic routes (partial matches handled in getDynamicLabel)
    // vorgänge is handled via getDynamicLabel

    // Finanzen
    '/finanzen': 'Finanzen',
    '/kasse': 'Kasse',
    '/spesen': 'Spesen',
    '/streckengeschaeft': 'Streckengeschäft',

    // Personal & Privat
    '/personal': 'Personal',
    '/privat': 'Privat',
    '/privat/finanzen': 'Finanzen',
    '/privat/notfall': 'Notfall',
    '/privat/fahrzeuge': 'Fahrzeuge',
    '/privat/fristen': 'Fristen',
    '/privat/immobilien': 'Immobilien',
    '/privat/versicherungen': 'Versicherungen',

    // Validation
    '/validation-queue': 'Validierungswarteschlange',
    '/jobs': 'Jobs',
}

/**
 * Dynamic segment patterns for label generation
 */
function getDynamicLabel(segment: string, _fullPath: string): string {
    // Year pattern (4 digits)
    if (/^\d{4}$/.test(segment)) {
        return segment
    }

    // Category labels (includes Ablage categories)
    const categories: Record<string, string> = {
        'einnahmen': 'Einnahmen',
        'ausgaben': 'Ausgaben',
        'belege': 'Belege',
        'vorgänge': 'Vorgänge',
        'folie': 'Folie',
        'messer': 'Spargelmesser',
        'anfragen': 'Anfragen',
        'angebote': 'Angebote',
        'auftragsbestätigung': 'Auftragsbestätigung',
        'lieferscheine': 'Lieferscheine',
        'rechnungen': 'Rechnungen',
        'bestellungen': 'Bestellungen',
        'storno': 'Storno',
        'mahnungen': 'Mahnungen',
        'offene_rechnungen': 'Offene Rechnungen',
        'offene_angebote': 'Offene Angebote',
        'offene_anfragen': 'Offene Anfragen',
        'reklamation': 'Reklamation',
        'kommunikation': 'Kommunikation',
        'archiv': 'Archiv',
        'druckdaten': 'Druckdaten',
    }
    if (categories[segment]) {
        return categories[segment]
    }

    // UUID or ID - show shortened version
    if (/^[a-f0-9-]{36}$/i.test(segment) || /^[a-f0-9]{24}$/i.test(segment)) {
        return `#${segment.slice(0, 8)}...`
    }

    // Default: capitalize first letter
    return segment.charAt(0).toUpperCase() + segment.slice(1)
}

interface BreadcrumbItem {
    label: string
    path: string
    isLast: boolean
}

function generateBreadcrumbs(pathname: string): BreadcrumbItem[] {
    const segments = pathname.split('/').filter(Boolean)
    const items: BreadcrumbItem[] = []

    // Always add home
    items.push({
        label: 'Startseite',
        path: '/',
        isLast: segments.length === 0,
    })

    // Build breadcrumb items
    let currentPath = ''
    segments.forEach((segment, index) => {
        currentPath += `/${segment}`
        const isLast = index === segments.length - 1

        // Check static labels first
        const staticLabel = ROUTE_LABELS[currentPath]
        const label = staticLabel || getDynamicLabel(segment, currentPath)

        items.push({
            label,
            path: currentPath,
            isLast,
        })
    })

    return items
}

interface BreadcrumbsProps {
    /** Custom class name */
    className?: string
    /** Maximum number of items to show (rest will be collapsed) */
    maxItems?: number
    /** Show home icon instead of "Startseite" */
    showHomeIcon?: boolean
}

export function Breadcrumbs({
    className,
    maxItems = 4,
    showHomeIcon = true,
}: BreadcrumbsProps) {
    const location = useLocation()
    const items = generateBreadcrumbs(location.pathname)

    // Don't show breadcrumbs on home page
    if (items.length <= 1) {
        return null
    }

    // Ablage-Routen: Verstecke globale Breadcrumb da CategoryHeader eigene hat
    // (Kunden/Lieferanten-Detail-Seiten mit Ordner/Kategorie)
    const isAblageDetailRoute = /^\/(kunden|lieferanten)\/[^/]+\/[^/]+/.test(location.pathname)
    if (isAblageDetailRoute) {
        return null
    }

    // Collapse middle items if too many
    let displayItems = items
    
    if (items.length > maxItems) {
        displayItems = [
            items[0], // Home
            { label: '...', path: '', isLast: false }, // Collapsed indicator
            ...items.slice(-(maxItems - 2)), // Last items
        ]
        
    }

    return (
        <nav
            aria-label="Breadcrumb"
            className={cn('flex items-center text-sm text-muted-foreground', className)}
        >
            <ol className="flex items-center gap-1">
                {displayItems.map((item, index) => (
                    <li key={item.path || `collapsed-${index}`} className="flex items-center">
                        {/* Separator */}
                        {index > 0 && (
                            <ChevronRight className="w-4 h-4 mx-1 text-muted-foreground/50" />
                        )}

                        {/* Item */}
                        {item.label === '...' ? (
                            <span className="px-1 text-muted-foreground/50">...</span>
                        ) : item.isLast ? (
                            <span
                                className="font-medium text-foreground truncate max-w-[200px]"
                                title={item.label}
                            >
                                {item.label}
                            </span>
                        ) : (
                            <Link
                                to={item.path}
                                className={cn(
                                    'hover:text-foreground transition-colors truncate max-w-[150px]',
                                    'flex items-center gap-1'
                                )}
                                title={item.label}
                            >
                                {showHomeIcon && item.path === '/' ? (
                                    <Home className="w-4 h-4" />
                                ) : (
                                    item.label
                                )}
                            </Link>
                        )}
                    </li>
                ))}
            </ol>
        </nav>
    )
}

/**
 * Page Header with Breadcrumbs
 * Convenience component for page headers
 */
interface PageHeaderProps {
    title: string
    description?: string
    actions?: React.ReactNode
    className?: string
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
    return (
        <div className={cn('space-y-2', className)}>
            <Breadcrumbs />
            <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                    <h1 className="text-2xl font-bold font-display tracking-tight">
                        {title}
                    </h1>
                    {description && (
                        <p className="text-muted-foreground">
                            {description}
                        </p>
                    )}
                </div>
                {actions && (
                    <div className="flex items-center gap-2">
                        {actions}
                    </div>
                )}
            </div>
        </div>
    )
}
