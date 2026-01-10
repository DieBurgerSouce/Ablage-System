import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Keyboard, Navigation, FileText, HelpCircle } from 'lucide-react'
import { type KeyboardShortcut, formatShortcutKeys } from '@/hooks/useKeyboardShortcuts'
import { cn } from '@/lib/utils'

const categoryConfig = {
    navigation: {
        label: 'Navigation',
        icon: Navigation,
        color: 'text-blue-500',
    },
    actions: {
        label: 'Aktionen',
        icon: Keyboard,
        color: 'text-green-500',
    },
    documents: {
        label: 'Dokumente',
        icon: FileText,
        color: 'text-orange-500',
    },
    help: {
        label: 'Hilfe',
        icon: HelpCircle,
        color: 'text-purple-500',
    },
} as const

interface KeyboardShortcutsHelpProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    shortcuts: KeyboardShortcut[]
}

export function KeyboardShortcutsHelp({
    open,
    onOpenChange,
    shortcuts,
}: KeyboardShortcutsHelpProps) {
    // Group shortcuts by category
    const groupedShortcuts = shortcuts.reduce((acc, shortcut) => {
        if (!acc[shortcut.category]) {
            acc[shortcut.category] = []
        }
        acc[shortcut.category].push(shortcut)
        return acc
    }, {} as Record<string, KeyboardShortcut[]>)

    const categories = Object.keys(groupedShortcuts) as Array<keyof typeof categoryConfig>

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Keyboard className="w-5 h-5" />
                        Tastenkürzel
                    </DialogTitle>
                    <DialogDescription>
                        Nutzen Sie diese Tastenkürzel für schnellere Navigation.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-4">
                    {categories.map(category => {
                        const config = categoryConfig[category]
                        const Icon = config.icon
                        const categoryShortcuts = groupedShortcuts[category]

                        return (
                            <div key={category} className="space-y-3">
                                {/* Category Header */}
                                <div className="flex items-center gap-2">
                                    <Icon className={cn('w-4 h-4', config.color)} />
                                    <h3 className="font-medium text-sm">
                                        {config.label}
                                    </h3>
                                </div>

                                {/* Shortcuts List */}
                                <div className="space-y-2 pl-6">
                                    {categoryShortcuts.map(shortcut => (
                                        <div
                                            key={shortcut.id}
                                            className="flex items-center justify-between py-1.5"
                                        >
                                            <span className="text-sm text-muted-foreground">
                                                {shortcut.description}
                                            </span>
                                            <ShortcutBadge keys={shortcut.keys} />
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )
                    })}
                </div>

                {/* Footer */}
                <div className="pt-4 border-t border-border">
                    <p className="text-xs text-muted-foreground text-center">
                        Drücken Sie <ShortcutBadge keys="?" className="mx-1" /> jederzeit, um diese Hilfe anzuzeigen.
                    </p>
                </div>
            </DialogContent>
        </Dialog>
    )
}

/**
 * Badge component for displaying keyboard shortcut keys
 */
function ShortcutBadge({ keys, className }: { keys: string; className?: string }) {
    const formattedKeys = formatShortcutKeys(keys)
    const parts = formattedKeys.split(' + ')

    return (
        <div className={cn('flex items-center gap-1', className)}>
            {parts.map((part, index) => (
                <span key={index}>
                    {index > 0 && <span className="text-muted-foreground mx-0.5">+</span>}
                    <Badge
                        variant="outline"
                        className="px-1.5 py-0.5 text-xs font-mono bg-muted/50"
                    >
                        {part}
                    </Badge>
                </span>
            ))}
        </div>
    )
}

export { ShortcutBadge }
