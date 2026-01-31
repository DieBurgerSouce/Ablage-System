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
    const { undo, redo, canUndo, canRedo } = useGlobalUndo()

    // Phase 4.4: Global Ctrl+Z for undo and Ctrl+Shift+Z for redo
    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            // Don't trigger when typing in inputs
            const target = event.target as HTMLElement
            const isTyping = target.tagName === 'INPUT' ||
                target.tagName === 'TEXTAREA' ||
                target.isContentEditable

            if (isTyping) return

            // Ctrl+Shift+Z or Cmd+Shift+Z for redo
            if ((event.ctrlKey || event.metaKey) && event.key === 'z' && event.shiftKey) {
                if (canRedo) {
                    event.preventDefault()
                    redo()
                }
                return
            }

            // Ctrl+Z or Cmd+Z for undo
            if ((event.ctrlKey || event.metaKey) && event.key === 'z' && !event.shiftKey) {
                if (canUndo) {
                    event.preventDefault()
                    undo()
                }
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [undo, redo, canUndo, canRedo])

    // Add undo/redo to shortcuts list for help display
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
        {
            id: 'redo-action',
            description: 'Aktion wiederholen',
            keys: 'ctrl+shift+z',
            category: 'actions' as const,
            handler: () => canRedo && redo(),
            enabled: canRedo,
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
