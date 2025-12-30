import { useGlobalShortcuts } from '@/hooks/useKeyboardShortcuts'
import { KeyboardShortcutsHelp } from '@/components/KeyboardShortcutsHelp'

/**
 * Provider component that sets up global keyboard shortcuts
 * and renders the shortcuts help modal.
 *
 * Must be used within a Router context.
 */
export function GlobalShortcutsProvider({ children }: { children: React.ReactNode }) {
    const { shortcuts, isHelpOpen, setHelpOpen } = useGlobalShortcuts()

    return (
        <>
            {children}
            <KeyboardShortcutsHelp
                open={isHelpOpen}
                onOpenChange={setHelpOpen}
                shortcuts={shortcuts}
            />
        </>
    )
}
