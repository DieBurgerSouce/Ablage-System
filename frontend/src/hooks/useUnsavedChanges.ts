import { useEffect, useCallback, useState } from 'react'
import { useBlocker } from '@tanstack/react-router'

/**
 * Hook to warn users about unsaved changes before leaving a page.
 *
 * Handles both:
 * 1. Browser navigation (back button, closing tab)
 * 2. TanStack Router navigation
 *
 * @example
 * ```tsx
 * function EditForm() {
 *   const [isDirty, setIsDirty] = useState(false)
 *   const { showWarning, confirmNavigation, cancelNavigation } = useUnsavedChanges(isDirty)
 *
 *   return (
 *     <>
 *       <form onChange={() => setIsDirty(true)}>
 *         ...
 *       </form>
 *       {showWarning && (
 *         <UnsavedChangesDialog
 *           onConfirm={confirmNavigation}
 *           onCancel={cancelNavigation}
 *         />
 *       )}
 *     </>
 *   )
 * }
 * ```
 */
export function useUnsavedChanges(isDirty: boolean) {
    const [showWarning, setShowWarning] = useState(false)
    const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null)

    // Block TanStack Router navigation
    const { proceed, reset, status } = useBlocker({
        condition: isDirty,
    })

    // Handle router blocker status changes
    useEffect(() => {
        if (status === 'blocked') {
            setShowWarning(true)
        }
    }, [status])

    // Handle browser beforeunload
    useEffect(() => {
        if (!isDirty) return

        const handleBeforeUnload = (event: BeforeUnloadEvent) => {
            event.preventDefault()
            // Modern browsers require returnValue to be set
            event.returnValue = ''
            return ''
        }

        window.addEventListener('beforeunload', handleBeforeUnload)
        return () => window.removeEventListener('beforeunload', handleBeforeUnload)
    }, [isDirty])

    const confirmNavigation = useCallback(() => {
        setShowWarning(false)
        if (status === 'blocked') {
            proceed()
        }
        if (pendingNavigation) {
            pendingNavigation()
            setPendingNavigation(null)
        }
    }, [status, proceed, pendingNavigation])

    const cancelNavigation = useCallback(() => {
        setShowWarning(false)
        if (status === 'blocked') {
            reset()
        }
        setPendingNavigation(null)
    }, [status, reset])

    return {
        /** Whether to show the warning dialog */
        showWarning,
        /** Call to confirm navigation (discard changes) */
        confirmNavigation,
        /** Call to cancel navigation (stay on page) */
        cancelNavigation,
        /** Whether form has unsaved changes */
        isDirty,
    }
}

/**
 * Simple hook to track form dirty state
 */
export function useFormDirtyState(initialValue = false) {
    const [isDirty, setIsDirty] = useState(initialValue)

    const markDirty = useCallback(() => setIsDirty(true), [])
    const markClean = useCallback(() => setIsDirty(false), [])
    const reset = useCallback(() => setIsDirty(initialValue), [initialValue])

    return {
        isDirty,
        markDirty,
        markClean,
        reset,
        setIsDirty,
    }
}
