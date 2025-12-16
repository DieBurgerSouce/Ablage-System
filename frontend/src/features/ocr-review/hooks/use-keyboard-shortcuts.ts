/**
 * Keyboard Shortcuts Hook für OCR Review
 */

import { useEffect, useCallback, useState } from 'react'

export interface ReviewAction {
    type: 'accept' | 'reject' | 'skip' | 'correct' | 'umlaut' | 'llm' | 'help' | 'escape'
}

interface UseKeyboardShortcutsOptions {
    onAction: (action: ReviewAction) => void
    enabled?: boolean
    preventDefault?: boolean
}

export function useKeyboardShortcuts({
    onAction,
    enabled = true,
    preventDefault = true,
}: UseKeyboardShortcutsOptions) {
    const [showHelp, setShowHelp] = useState(false)

    const handleKeyDown = useCallback(
        (event: KeyboardEvent) => {
            if (!enabled) return

            // Ignoriere wenn in Input/Textarea fokussiert
            const target = event.target as HTMLElement
            if (
                target.tagName === 'INPUT' ||
                target.tagName === 'TEXTAREA' ||
                target.isContentEditable
            ) {
                // Nur Escape und Ctrl+Enter erlauben
                if (event.key === 'Escape') {
                    onAction({ type: 'escape' })
                    if (preventDefault) event.preventDefault()
                    return
                }
                if (event.key === 'Enter' && event.ctrlKey) {
                    onAction({ type: 'correct' })
                    if (preventDefault) event.preventDefault()
                    return
                }
                return
            }

            let handled = false

            switch (event.key.toLowerCase()) {
                case 'a':
                    onAction({ type: 'accept' })
                    handled = true
                    break
                case 'r':
                    onAction({ type: 'reject' })
                    handled = true
                    break
                case 's':
                    onAction({ type: 'skip' })
                    handled = true
                    break
                case 'c':
                    onAction({ type: 'correct' })
                    handled = true
                    break
                case 'u':
                    onAction({ type: 'umlaut' })
                    handled = true
                    break
                case 'l':
                    onAction({ type: 'llm' })
                    handled = true
                    break
                case '?':
                    setShowHelp((prev) => !prev)
                    handled = true
                    break
                case 'escape':
                    if (showHelp) {
                        setShowHelp(false)
                    } else {
                        onAction({ type: 'escape' })
                    }
                    handled = true
                    break
                case 'enter':
                    if (event.ctrlKey) {
                        onAction({ type: 'correct' })
                        handled = true
                    }
                    break
            }

            if (handled && preventDefault) {
                event.preventDefault()
            }
        },
        [enabled, onAction, preventDefault, showHelp]
    )

    useEffect(() => {
        window.addEventListener('keydown', handleKeyDown)
        return () => {
            window.removeEventListener('keydown', handleKeyDown)
        }
    }, [handleKeyDown])

    return {
        showHelp,
        setShowHelp,
    }
}

// Shortcut-Definitionen für Help-Overlay
export const KEYBOARD_SHORTCUTS = [
    { key: 'A', description: 'Akzeptieren', action: 'accept' as const },
    { key: 'C', description: 'Korrigieren & Weiter', action: 'correct' as const },
    { key: 'Ctrl+Enter', description: 'Korrektur speichern (auch in Textfeld)', action: 'correct' as const },
    { key: 'S', description: 'Überspringen', action: 'skip' as const },
    { key: 'R', description: 'Ablehnen', action: 'reject' as const },
    { key: 'U', description: 'Umlaute korrigieren', action: 'umlaut' as const },
    { key: 'L', description: 'LLM-Vorschlag übernehmen', action: 'llm' as const },
    { key: '?', description: 'Hilfe anzeigen', action: 'help' as const },
    { key: 'Esc', description: 'Zurück / Schließen', action: 'escape' as const },
] as const
