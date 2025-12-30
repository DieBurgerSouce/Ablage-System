import { useState, useEffect } from 'react'
import { WifiOff, Wifi } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * OfflineIndicator Component
 *
 * Displays a banner when the user loses internet connection.
 * Automatically detects online/offline status changes.
 * All user-facing text is in German.
 */
export function OfflineIndicator() {
    const [isOnline, setIsOnline] = useState(
        typeof navigator !== 'undefined' ? navigator.onLine : true
    )
    const [showReconnected, setShowReconnected] = useState(false)
    const [wasOffline, setWasOffline] = useState(false)

    useEffect(() => {
        const handleOnline = () => {
            setIsOnline(true)
            // Show "reconnected" message briefly if we were offline
            if (wasOffline) {
                setShowReconnected(true)
                setTimeout(() => setShowReconnected(false), 3000)
            }
        }

        const handleOffline = () => {
            setIsOnline(false)
            setWasOffline(true)
        }

        window.addEventListener('online', handleOnline)
        window.addEventListener('offline', handleOffline)

        return () => {
            window.removeEventListener('online', handleOnline)
            window.removeEventListener('offline', handleOffline)
        }
    }, [wasOffline])

    // Don't render anything if online and not showing reconnected message
    if (isOnline && !showReconnected) {
        return null
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
                </>
            ) : (
                <>
                    <WifiOff className="h-4 w-4" />
                    <span>Keine Internetverbindung - Einige Funktionen sind moeglicherweise nicht verfuegbar</span>
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
