/**
 * PWA Context - Provides PWA state and functionality across the app
 *
 * Features:
 * - Install prompt management (beforeinstallprompt event)
 * - Online/offline status
 * - Update notification handling
 * - Display mode detection
 */
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react'
import { logger } from '@/lib/logger'

// BeforeInstallPromptEvent type (not in standard TypeScript lib)
interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[]
  readonly userChoice: Promise<{
    outcome: 'accepted' | 'dismissed'
    platform: string
  }>
  prompt(): Promise<void>
}

// Display mode types
type DisplayMode = 'browser' | 'standalone' | 'fullscreen' | 'minimal-ui'

interface PWAContextValue {
  // Install prompt
  canInstall: boolean
  isInstalled: boolean
  installPrompt: () => Promise<boolean>

  // Network status
  isOnline: boolean

  // Display mode
  displayMode: DisplayMode

  // Update status
  hasUpdate: boolean
  applyUpdate: () => void
}

const PWAContext = createContext<PWAContextValue | null>(null)

export function usePWA(): PWAContextValue {
  const context = useContext(PWAContext)
  if (!context) {
    throw new Error('usePWA muss innerhalb von PWAProvider verwendet werden')
  }
  return context
}

interface PWAProviderProps {
  children: ReactNode
}

export function PWAProvider({ children }: PWAProviderProps) {
  // Install prompt state
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [isInstalled, setIsInstalled] = useState(false)

  // Network status
  const [isOnline, setIsOnline] = useState(navigator.onLine)

  // Display mode
  const [displayMode, setDisplayMode] = useState<DisplayMode>('browser')

  // Update state (set by main.tsx via global event)
  const [hasUpdate, setHasUpdate] = useState(false)
  const [updateCallback, setUpdateCallback] = useState<(() => void) | null>(null)

  // Detect display mode
  useEffect(() => {
    const detectDisplayMode = (): DisplayMode => {
      if (window.matchMedia('(display-mode: standalone)').matches) {
        return 'standalone'
      }
      if (window.matchMedia('(display-mode: fullscreen)').matches) {
        return 'fullscreen'
      }
      if (window.matchMedia('(display-mode: minimal-ui)').matches) {
        return 'minimal-ui'
      }
      return 'browser'
    }

    setDisplayMode(detectDisplayMode())

    // Listen for display mode changes
    const standaloneQuery = window.matchMedia('(display-mode: standalone)')
    const handleChange = () => setDisplayMode(detectDisplayMode())

    standaloneQuery.addEventListener('change', handleChange)
    return () => standaloneQuery.removeEventListener('change', handleChange)
  }, [])

  // Check if already installed
  useEffect(() => {
    // Check if running in standalone mode (already installed)
    if (
      window.matchMedia('(display-mode: standalone)').matches ||
      // @ts-expect-error - Safari-specific property
      window.navigator.standalone === true
    ) {
      setIsInstalled(true)
    }

    // Listen for app installed event
    const handleInstalled = () => {
      setIsInstalled(true)
      setInstallEvent(null)
      logger.info('[PWA] App wurde installiert')
    }

    window.addEventListener('appinstalled', handleInstalled)
    return () => window.removeEventListener('appinstalled', handleInstalled)
  }, [])

  // Capture install prompt
  useEffect(() => {
    const handleBeforeInstallPrompt = (e: Event) => {
      // Prevent default browser prompt
      e.preventDefault()
      // Store event for later use
      setInstallEvent(e as BeforeInstallPromptEvent)
      logger.info('[PWA] Installation möglich', {
        platforms: (e as BeforeInstallPromptEvent).platforms,
      })
    }

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
    return () => window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
  }, [])

  // Network status tracking
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      logger.info('[PWA] Wieder online')
    }

    const handleOffline = () => {
      setIsOnline(false)
      logger.warn('[PWA] Offline')
    }

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // Listen for update events from main.tsx
  useEffect(() => {
    const handleUpdateAvailable = (e: CustomEvent<{ update: () => void }>) => {
      setHasUpdate(true)
      setUpdateCallback(() => e.detail.update)
    }

    window.addEventListener('pwa-update-available', handleUpdateAvailable as EventListener)
    return () => {
      window.removeEventListener('pwa-update-available', handleUpdateAvailable as EventListener)
    }
  }, [])

  // Install prompt handler
  const installPrompt = useCallback(async (): Promise<boolean> => {
    if (!installEvent) {
      logger.warn('[PWA] Kein Installations-Event verfügbar')
      return false
    }

    try {
      // Show native install prompt
      await installEvent.prompt()

      // Wait for user choice
      const choice = await installEvent.userChoice

      if (choice.outcome === 'accepted') {
        logger.info('[PWA] Installation akzeptiert', { platform: choice.platform })
        setInstallEvent(null)
        return true
      } else {
        logger.info('[PWA] Installation abgelehnt')
        return false
      }
    } catch (error) {
      logger.error('[PWA] Installations-Fehler', { error })
      return false
    }
  }, [installEvent])

  // Apply update handler
  const applyUpdate = useCallback(() => {
    if (updateCallback) {
      updateCallback()
    }
  }, [updateCallback])

  const value: PWAContextValue = {
    canInstall: installEvent !== null && !isInstalled,
    isInstalled,
    installPrompt,
    isOnline,
    displayMode,
    hasUpdate,
    applyUpdate,
  }

  return <PWAContext.Provider value={value}>{children}</PWAContext.Provider>
}
