/**
 * Keyboard Shortcuts Hook für OCR Review
 */

import { useEffect, useCallback, useState } from 'react'

export interface ReviewAction {
    type: 'accept' | 'reject' | 'skip' | 'correct' | 'umlaut' | 'llm' | 'help' | 'escape' | 'tab1' | 'tab2' | 'nextField' | 'prevField' | 'confirmField' | 'confirmAll' | 'editField'
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
                case '1':
                    onAction({ type: 'tab1' })
                    handled = true
                    break
                case '2':
                    onAction({ type: 'tab2' })
                    handled = true
                    break
                case 'j':
                    // J = Nächstes Feld (wie Vim-Navigation)
                    onAction({ type: 'nextField' })
                    handled = true
                    break
                case 'k':
                    // K = Vorheriges Feld (wie Vim-Navigation)
                    onAction({ type: 'prevField' })
                    handled = true
                    break
                case 'e':
                    // E = Aktuelles Feld bearbeiten
                    onAction({ type: 'editField' })
                    handled = true
                    break
                case 'tab':
                    if (event.shiftKey) {
                        onAction({ type: 'prevField' })
                    } else {
                        onAction({ type: 'nextField' })
                    }
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
                    if (event.ctrlKey && event.shiftKey) {
                        onAction({ type: 'confirmAll' })
                        handled = true
                    } else if (event.ctrlKey) {
                        onAction({ type: 'correct' })
                        handled = true
                    } else {
                        onAction({ type: 'confirmField' })
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
    // Hauptaktionen
    { key: 'A', description: 'Akzeptieren', action: 'accept' as const },
    { key: 'C', description: 'Korrigieren & Weiter', action: 'correct' as const },
    { key: 'Ctrl+Enter', description: 'Korrektur speichern (auch in Textfeld)', action: 'correct' as const },
    { key: 'S', description: 'Überspringen', action: 'skip' as const },
    { key: 'R', description: 'Ablehnen', action: 'reject' as const },
    // OCR-Korrekturen
    { key: 'U', description: 'Umlaute korrigieren', action: 'umlaut' as const },
    { key: 'L', description: 'LLM-Vorschlag übernehmen', action: 'llm' as const },
    // Tab-Navigation
    { key: '1', description: 'Tab: Strukturiert', action: 'tab1' as const },
    { key: '2', description: 'Tab: OCR-Text', action: 'tab2' as const },
    // Feld-Navigation (Strukturierter Modus)
    { key: 'J', description: 'Nächstes Feld', action: 'nextField' as const },
    { key: 'K', description: 'Vorheriges Feld', action: 'prevField' as const },
    { key: 'Tab', description: 'Nächstes Feld (alt)', action: 'nextField' as const },
    { key: 'Shift+Tab', description: 'Vorheriges Feld (alt)', action: 'prevField' as const },
    { key: 'E', description: 'Feld bearbeiten', action: 'editField' as const },
    { key: 'Enter', description: 'Feld bestätigen', action: 'confirmField' as const },
    { key: 'Ctrl+Shift+Enter', description: 'Alle Felder bestätigen', action: 'confirmAll' as const },
    // Hilfe
    { key: '?', description: 'Hilfe anzeigen', action: 'help' as const },
    { key: 'Esc', description: 'Zurück / Schließen', action: 'escape' as const },
] as const
