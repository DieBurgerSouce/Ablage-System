import { useEffect } from 'react'
import { useGlobalShortcuts } from '@/hooks/useKeyboardShortcuts'
import { KeyboardShortcutsHelp } from '@/components/KeyboardShortcutsHelp'
import { useGlobalUndo } from '@/hooks/useUndoableAction'

/**
 * Provider component that sets up global keyboard shortcuts
 * and renders the shortcuts help modal.
 *
 * Must be used within a Router context and UndoProvider.
 */
export function GlobalShortcutsProvider({ children }: { children: React.ReactNode }) {
    const { shortcuts, isHelpOpen, setHelpOpen } = useGlobalShortcuts()
    const { undo, canUndo } = useGlobalUndo()

    // Phase 4.4: Global Ctrl+Z for undo
    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            // Ctrl+Z or Cmd+Z for undo
            if ((event.ctrlKey || event.metaKey) && event.key === 'z' && !event.shiftKey) {
                // Don't trigger when typing in inputs
                const target = event.target as HTMLElement
                const isTyping = target.tagName === 'INPUT' ||
                    target.tagName === 'TEXTAREA' ||
                    target.isContentEditable

                if (isTyping) return

                if (canUndo) {
                    event.preventDefault()
                    undo()
                }
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [undo, canUndo])

    // Add undo to shortcuts list for help display
    const allShortcuts = [
        ...shortcuts,
        {
            id: 'undo-action',
            description: 'Letzte Aktion rückgängig',
            keys: 'ctrl+z',
            category: 'actions' as const,
            handler: () => canUndo && undo(),
            enabled: canUndo,
        },
    ]

    return (
        <>
            {children}
            <KeyboardShortcutsHelp
                open={isHelpOpen}
                onOpenChange={setHelpOpen}
                shortcuts={allShortcuts}
            />
        </>
    )
}
