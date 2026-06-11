/**
 * Offline-Sync Status Bar
 * Zeigt Offline-Status und ausstehende Synchronisierungen an.
 */
import { useState, useEffect } from 'react'
import { WifiOff, CloudOff, RefreshCw, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface SyncQueueItem {
  id: string
  type: string
  timestamp: number
}

export function OfflineSyncStatusBar() {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [queueCount, setQueueCount] = useState(0)
  const [isSyncing, setIsSyncing] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    const handleOnline = () => { setIsOnline(true); setDismissed(false) }
    const handleOffline = () => { setIsOnline(false); setDismissed(false) }
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // Check IndexedDB for pending sync items
  useEffect(() => {
    const checkQueue = async () => {
      try {
        if ('indexedDB' in window) {
          const request = indexedDB.open('offline-queue', 1)
          request.onsuccess = () => {
            const db = request.result
            if (db.objectStoreNames.contains('requests')) {
              const tx = db.transaction('requests', 'readonly')
              const store = tx.objectStore('requests')
              const countReq = store.count()
              countReq.onsuccess = () => setQueueCount(countReq.result)
            }
            db.close()
          }
        }
      } catch {
        // IndexedDB not available
      }
    }
    checkQueue()
    const interval = setInterval(checkQueue, 5000)
    return () => clearInterval(interval)
  }, [])

  // Auto-sync when back online
  useEffect(() => {
    if (isOnline && queueCount > 0) {
      setIsSyncing(true)
      // Trigger service worker background sync
      if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({ type: 'SYNC_NOW' })
      }
      // Simulated sync completion after brief delay
      const timer = setTimeout(() => {
        setIsSyncing(false)
        setQueueCount(0)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [isOnline, queueCount])

  // Don't show if online and no queue and not syncing
  if (isOnline && queueCount === 0 && !isSyncing && !dismissed) {
    return null
  }

  if (dismissed) return null

  return (
    <div
      className={cn(
        'fixed top-0 left-0 right-0 z-50 px-4 py-2 flex items-center justify-between text-sm transition-all duration-300',
        !isOnline && 'bg-destructive text-destructive-foreground',
        isOnline && isSyncing && 'bg-yellow-500/90 text-yellow-950',
        isOnline && !isSyncing && queueCount > 0 && 'bg-blue-500/90 text-white',
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        {!isOnline ? (
          <>
            <WifiOff className="h-4 w-4" />
            <span>Offline-Modus aktiv - Änderungen werden lokal gespeichert</span>
          </>
        ) : isSyncing ? (
          <>
            <RefreshCw className="h-4 w-4 animate-spin" />
            <span>Synchronisiere {queueCount} ausstehende Änderungen...</span>
          </>
        ) : (
          <>
            <CloudOff className="h-4 w-4" />
            <span>{queueCount} Änderungen warten auf Synchronisierung</span>
          </>
        )}
        {queueCount > 0 && (
          <Badge variant="secondary" className="text-xs">{queueCount}</Badge>
        )}
      </div>
      <div className="flex items-center gap-2">
        {isOnline && !isSyncing && queueCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs"
            onClick={() => {
              setIsSyncing(true)
              if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({ type: 'SYNC_NOW' })
              }
            }}
          >
            <RefreshCw className="h-3 w-3 mr-1" />
            Jetzt synchronisieren
          </Button>
        )}
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setDismissed(true)}>
          <X className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}
