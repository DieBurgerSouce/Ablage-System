import { useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

/**
 * Keyboard shortcut definition
 */
export interface KeyboardShortcut {
    /** Unique key for the shortcut */
    id: string
    /** Human-readable description (German) */
    description: string
    /** Key combination (e.g., 'ctrl+k', 'alt+s', '?') */
    keys: string
    /** Category for grouping in help modal */
    category: 'navigation' | 'actions' | 'documents' | 'help'
    /** Handler function */
    handler: () => void
    /** Whether shortcut is enabled */
    enabled?: boolean
}

/**
 * Parse key combination string into event matcher
 */
function matchesShortcut(event: KeyboardEvent, keys: string): boolean {
    const parts = keys.toLowerCase().split('+')
    const key = parts[parts.length - 1]
    const needsCtrl = parts.includes('ctrl') || parts.includes('cmd')
    const needsAlt = parts.includes('alt')
    const needsShift = parts.includes('shift')

    const ctrlMatch = needsCtrl ? (event.ctrlKey || event.metaKey) : !(event.ctrlKey || event.metaKey)
    const altMatch = needsAlt ? event.altKey : !event.altKey
    const shiftMatch = needsShift ? event.shiftKey : !event.shiftKey

    // Handle special keys
    let keyMatch = false
    if (key === 'escape' || key === 'esc') {
        keyMatch = event.key === 'Escape'
    } else if (key === 'enter') {
        keyMatch = event.key === 'Enter'
    } else if (key === 'space') {
        keyMatch = event.key === ' '
    } else if (key === '?') {
        // Question mark needs shift on most keyboards
        keyMatch = event.key === '?'
        // Override shift check for ?
        return ctrlMatch && altMatch && keyMatch
    } else {
        keyMatch = event.key.toLowerCase() === key
    }

    return ctrlMatch && altMatch && shiftMatch && keyMatch
}

/**
 * Hook to register and handle keyboard shortcuts
 */
export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[]) {
    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            // Don't trigger shortcuts when typing in inputs
            const target = event.target as HTMLElement
            const isTyping = target.tagName === 'INPUT' ||
                target.tagName === 'TEXTAREA' ||
                target.isContentEditable

            for (const shortcut of shortcuts) {
                if (shortcut.enabled === false) continue

                if (matchesShortcut(event, shortcut.keys)) {
                    // Allow ? shortcut even when typing (for help)
                    if (isTyping && shortcut.keys !== '?') continue

                    event.preventDefault()
                    shortcut.handler()
                    return
                }
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [shortcuts])
}

/**
 * Global shortcuts state
 */
interface ShortcutsState {
    isHelpOpen: boolean
    setHelpOpen: (open: boolean) => void
}

let globalState: ShortcutsState | null = null

/**
 * Hook to manage global shortcuts state
 */
export function useShortcutsState(): ShortcutsState {
    const [isHelpOpen, setHelpOpen] = useState(false)

    // Store in global state for access from shortcuts
    globalState = { isHelpOpen, setHelpOpen }

    return { isHelpOpen, setHelpOpen }
}

/**
 * Get current shortcuts state (for use in handlers)
 */
export function getShortcutsState(): ShortcutsState | null {
    return globalState
}

/**
 * Hook providing default application shortcuts
 */
export function useGlobalShortcuts() {
    const navigate = useNavigate()
    const state = useShortcutsState()

    const shortcuts: KeyboardShortcut[] = [
        // Navigation
        {
            id: 'go-home',
            description: 'Zur Startseite',
            keys: 'alt+h',
            category: 'navigation',
            handler: () => navigate({ to: '/' }),
        },
        {
            id: 'go-search',
            description: 'Zur Suche',
            keys: 'ctrl+k',
            category: 'navigation',
            handler: () => navigate({ to: '/search' }),
        },
        {
            id: 'go-upload',
            description: 'Zum Upload',
            keys: 'ctrl+u',
            category: 'navigation',
            handler: () => navigate({ to: '/upload' }),
        },
        {
            id: 'go-admin',
            description: 'Zur Administration',
            keys: 'alt+a',
            category: 'navigation',
            handler: () => navigate({ to: '/admin' }),
        },

        // Help
        {
            id: 'show-help',
            description: 'Tastenkuerzel anzeigen',
            keys: '?',
            category: 'help',
            handler: () => state.setHelpOpen(true),
        },
        {
            id: 'close-modal',
            description: 'Dialog schliessen',
            keys: 'escape',
            category: 'help',
            handler: () => state.setHelpOpen(false),
        },
    ]

    useKeyboardShortcuts(shortcuts)

    return {
        shortcuts,
        ...state,
    }
}

/**
 * Format shortcut keys for display
 */
export function formatShortcutKeys(keys: string): string {
    const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform)

    return keys
        .split('+')
        .map(part => {
            const lower = part.toLowerCase()
            if (lower === 'ctrl' || lower === 'cmd') return isMac ? '⌘' : 'Ctrl'
            if (lower === 'alt') return isMac ? '⌥' : 'Alt'
            if (lower === 'shift') return '⇧'
            if (lower === 'escape' || lower === 'esc') return 'Esc'
            if (lower === 'enter') return '↵'
            if (lower === 'space') return 'Space'
            return part.toUpperCase()
        })
        .join(' + ')
}
