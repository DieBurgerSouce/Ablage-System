import { useState, useEffect, useRef } from 'react'
import { WifiOff, Wifi, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
    useOfflineQueueStore,
    selectPendingCount,
    selectIsSyncing,
} from '@/stores/offline-queue'

/**
 * OfflineIndicator Component
 *
 * Displays a banner when the user loses internet connection.
 * Shows pending changes count when offline.
 * Shows sync progress when reconnecting.
 * All user-facing text is in German.
 */
export function OfflineIndicator() {
    const [isOnline, setIsOnline] = useState(
        typeof navigator !== 'undefined' ? navigator.onLine : true
    )
    const [showReconnected, setShowReconnected] = useState(false)
    // FIX Phase 7.7: useRef statt useState - wird nur intern gelesen, kein Re-Render nötig
    const wasOfflineRef = useRef(false)

    // Offline queue state
    const pendingCount = useOfflineQueueStore(selectPendingCount)
    const isSyncing = useOfflineQueueStore(selectIsSyncing)
    const clearPendingMutations = useOfflineQueueStore((state) => state.clearPendingMutations)

    useEffect(() => {
        // FIX: Timer ID für Cleanup bei Unmount
        let timeoutId: ReturnType<typeof setTimeout> | null = null

        const handleOnline = () => {
            setIsOnline(true)
            // Show "reconnected" message briefly if we were offline
            if (wasOfflineRef.current) {
                setShowReconnected(true)
                // Clear pending mutations when back online (TanStack Query handles retry)
                clearPendingMutations()
                // FIX: Alten Timer clearen bevor neuer gesetzt wird
                if (timeoutId) clearTimeout(timeoutId)
                timeoutId = setTimeout(() => setShowReconnected(false), 3000)
            }
        }

        const handleOffline = () => {
            setIsOnline(false)
            wasOfflineRef.current = true
        }

        window.addEventListener('online', handleOnline)
        window.addEventListener('offline', handleOffline)

        return () => {
            // FIX: Timer bei Unmount aufräumen
            if (timeoutId) clearTimeout(timeoutId)
            window.removeEventListener('online', handleOnline)
            window.removeEventListener('offline', handleOffline)
        }
    }, [clearPendingMutations])

    // Don't render anything if online and not showing reconnected message and not syncing
    if (isOnline && !showReconnected && !isSyncing) {
        return null
    }

    // Syncing state (reconnected and processing)
    if (isSyncing) {
        return (
            <div
                className={cn(
                    'fixed top-0 left-0 right-0 z-[100] px-4 py-2 text-center text-sm font-medium',
                    'animate-in slide-in-from-top duration-300',
                    'flex items-center justify-center gap-2',
                    'bg-blue-500/90 text-white backdrop-blur-sm'
                )}
                role="status"
                aria-live="polite"
            >
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Änderungen werden synchronisiert...</span>
            </div>
        )
    }

    return (
        <div
            className={cn(
                'fixed top-0 left-0 right-0 z-[100] px-4 py-2 text-center text-sm font-medium',
                'animate-in slide-in-from-top duration-300',
                'flex items-center justify-center gap-2',
                isOnline
                    ? 'bg-green-500/90 text-white backdrop-blur-sm'
                    : 'bg-destructive/90 text-destructive-foreground backdrop-blur-sm'
            )}
            role="alert"
            aria-live="assertive"
        >
            {isOnline ? (
                <>
                    <Wifi className="h-4 w-4" />
                    <span>Verbindung wiederhergestellt</span>
                    {pendingCount > 0 && (
                        <span className="ml-1 text-xs opacity-80">
                            ({pendingCount} Änderungen synchronisiert)
                        </span>
                    )}
                </>
            ) : (
                <>
                    <WifiOff className="h-4 w-4" />
                    <span>
                        Keine Internetverbindung
                        {pendingCount > 0 ? (
                            <> - {pendingCount} Änderung{pendingCount !== 1 ? 'en' : ''} warten auf Synchronisierung</>
                        ) : (
                            <> - Einige Funktionen sind möglicherweise nicht verfügbar</>
                        )}
                    </span>
                </>
            )}
        </div>
    )
}

/**
 * Hook to check online status
 * Can be used in components that need to react to connection changes
 */
export function useOnlineStatus(): boolean {
    const [isOnline, setIsOnline] = useState(
        typeof navigator !== 'undefined' ? navigator.onLine : true
    )

    useEffect(() => {
        const handleOnline = () => setIsOnline(true)
        const handleOffline = () => setIsOnline(false)

        window.addEventListener('online', handleOnline)
        window.addEventListener('offline', handleOffline)

        return () => {
            window.removeEventListener('online', handleOnline)
            window.removeEventListener('offline', handleOffline)
        }
    }, [])

    return isOnline
}
