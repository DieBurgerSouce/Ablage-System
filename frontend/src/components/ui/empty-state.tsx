import { FileX, Search, AlertCircle, Upload, FolderOpen, Inbox } from 'lucide-react'

type LucideIcon = React.ComponentType<{ className?: string }>
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * Variant configurations with default icons and styles
 */
const variantConfig = {
    default: {
        icon: Inbox,
        containerClass: 'bg-muted/30',
        iconClass: 'text-muted-foreground',
    },
    search: {
        icon: Search,
        containerClass: 'bg-muted/30',
        iconClass: 'text-muted-foreground',
    },
    error: {
        icon: AlertCircle,
        containerClass: 'bg-destructive/10',
        iconClass: 'text-destructive',
    },
    upload: {
        icon: Upload,
        containerClass: 'bg-primary/10',
        iconClass: 'text-primary',
    },
    folder: {
        icon: FolderOpen,
        containerClass: 'bg-muted/30',
        iconClass: 'text-muted-foreground',
    },
    document: {
        icon: FileX,
        containerClass: 'bg-muted/30',
        iconClass: 'text-muted-foreground',
    },
} as const

export type EmptyStateVariant = keyof typeof variantConfig

export interface EmptyStateAction {
    label: string
    onClick: () => void
    variant?: 'default' | 'outline' | 'secondary' | 'ghost'
}

export interface EmptyStateProps {
    /** Custom icon to display. If not provided, uses variant default */
    icon?: LucideIcon
    /** Main title text */
    title: string
    /** Optional description text */
    description?: string
    /** Optional action button */
    action?: EmptyStateAction
    /** Optional secondary action button */
    secondaryAction?: EmptyStateAction
    /** Visual variant that affects icon and styling */
    variant?: EmptyStateVariant
    /** Additional CSS classes */
    className?: string
    /** Size variant */
    size?: 'sm' | 'md' | 'lg'
}

/**
 * EmptyState Component
 *
 * A reusable component for displaying empty states with consistent styling.
 * All user-facing text should be in German.
 *
 * @example
 * ```tsx
 * <EmptyState
 *   variant="search"
 *   title="Keine Ergebnisse"
 *   description="Versuchen Sie andere Suchbegriffe."
 * />
 * ```
 *
 * @example
 * ```tsx
 * <EmptyState
 *   variant="upload"
 *   title="Noch keine Dokumente"
 *   description="Laden Sie Ihr erstes Dokument hoch."
 *   action={{
 *     label: "Dokument hochladen",
 *     onClick: () => navigate('/upload')
 *   }}
 * />
 * ```
 */
export function EmptyState({
    icon,
    title,
    description,
    action,
    secondaryAction,
    variant = 'default',
    className,
    size = 'md',
}: EmptyStateProps) {
    const config = variantConfig[variant]
    const IconComponent = icon ?? config.icon

    const sizeClasses = {
        sm: {
            container: 'p-6',
            iconWrapper: 'w-12 h-12',
            icon: 'w-6 h-6',
            title: 'text-base',
            description: 'text-sm',
        },
        md: {
            container: 'p-8',
            iconWrapper: 'w-16 h-16',
            icon: 'w-8 h-8',
            title: 'text-lg',
            description: 'text-sm',
        },
        lg: {
            container: 'p-12',
            iconWrapper: 'w-20 h-20',
            icon: 'w-10 h-10',
            title: 'text-xl',
            description: 'text-base',
        },
    }

    const sizes = sizeClasses[size]

    return (
        <div
            className={cn(
                'flex flex-col items-center justify-center text-center rounded-xl border border-white/5',
                'animate-in fade-in duration-300',
                config.containerClass,
                sizes.container,
                className
            )}
        >
            {/* Icon */}
            <div
                className={cn(
                    'rounded-full flex items-center justify-center mb-4',
                    'bg-background/50 border border-white/10',
                    sizes.iconWrapper
                )}
            >
                <IconComponent className={cn(sizes.icon, config.iconClass)} />
            </div>

            {/* Title */}
            <h3 className={cn('font-semibold font-display mb-2', sizes.title)}>
                {title}
            </h3>

            {/* Description */}
            {description && (
                <p className={cn('text-muted-foreground max-w-sm', sizes.description)}>
                    {description}
                </p>
            )}

            {/* Actions */}
            {(action || secondaryAction) && (
                <div className="flex flex-col sm:flex-row gap-3 mt-6">
                    {action && (
                        <Button
                            onClick={action.onClick}
                            variant={action.variant ?? 'default'}
                            className="shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all"
                        >
                            {action.label}
                        </Button>
                    )}
                    {secondaryAction && (
                        <Button
                            onClick={secondaryAction.onClick}
                            variant={secondaryAction.variant ?? 'outline'}
                            className="border-white/10 hover:bg-white/5"
                        >
                            {secondaryAction.label}
                        </Button>
                    )}
                </div>
            )}
        </div>
    )
}

/**
 * Preset empty states for common use cases
 */
export const EmptyStatePresets = {
    /** No documents found */
    noDocuments: (onUpload?: () => void): EmptyStateProps => ({
        variant: 'document',
        title: 'Noch keine Dokumente',
        description: 'Laden Sie Ihr erstes Dokument hoch, um loszulegen.',
        action: onUpload
            ? { label: 'Dokument hochladen', onClick: onUpload }
            : undefined,
    }),

    /** Search with no results */
    noSearchResults: (query?: string): EmptyStateProps => ({
        variant: 'search',
        title: 'Keine Ergebnisse gefunden',
        description: query
            ? `Keine Dokumente gefunden für "${query}". Versuchen Sie andere Suchbegriffe.`
            : 'Versuchen Sie andere Suchbegriffe oder Filter.',
    }),

    /** Before first search */
    searchPrompt: (): EmptyStateProps => ({
        variant: 'search',
        title: 'Dokumente durchsuchen',
        description: 'Geben Sie einen Suchbegriff ein, um Dokumente zu finden.',
    }),

    /** Folder is empty */
    emptyFolder: (onUpload?: () => void): EmptyStateProps => ({
        variant: 'folder',
        title: 'Dieser Ordner ist leer',
        description: 'Fügen Sie Dokumente zu diesem Ordner hinzu.',
        action: onUpload
            ? { label: 'Dokument hinzufügen', onClick: onUpload }
            : undefined,
    }),

    /** Error loading data */
    loadError: (onRetry?: () => void): EmptyStateProps => ({
        variant: 'error',
        title: 'Fehler beim Laden',
        description: 'Die Daten konnten nicht geladen werden. Bitte versuchen Sie es erneut.',
        action: onRetry
            ? { label: 'Erneut versuchen', onClick: onRetry }
            : undefined,
    }),
}
