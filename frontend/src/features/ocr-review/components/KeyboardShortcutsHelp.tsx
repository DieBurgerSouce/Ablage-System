/**
 * Keyboard Shortcuts Help Overlay
 */

import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Keyboard } from 'lucide-react'
import { KEYBOARD_SHORTCUTS } from '../hooks/use-keyboard-shortcuts'

interface KeyboardShortcutsHelpProps {
    open: boolean
    onOpenChange: (open: boolean) => void
}

export function KeyboardShortcutsHelp({ open, onOpenChange }: KeyboardShortcutsHelpProps) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Keyboard className="h-5 w-5" />
                        Tastenkürzel
                    </DialogTitle>
                    <DialogDescription>
                        Schnelle Navigation während des Reviews
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3 py-4">
                    {KEYBOARD_SHORTCUTS.map(({ key, description }) => (
                        <div key={key} className="flex items-center justify-between">
                            <span className="text-sm">{description}</span>
                            <Badge variant="secondary" className="font-mono text-xs">
                                {key}
                            </Badge>
                        </div>
                    ))}
                </div>
                <p className="text-xs text-muted-foreground">
                    Hinweis: Tastenkürzel sind deaktiviert wenn ein Textfeld fokussiert ist
                    (außer Esc und Ctrl+Enter).
                </p>
            </DialogContent>
        </Dialog>
    )
}

/**
 * Inline Shortcut Hint Badge
 */
export function ShortcutHint({ shortcut, className }: { shortcut: string; className?: string }) {
    return (
        <Badge variant="outline" className={`font-mono text-xs ml-2 opacity-60 ${className ?? ''}`}>
            {shortcut}
        </Badge>
    )
}
