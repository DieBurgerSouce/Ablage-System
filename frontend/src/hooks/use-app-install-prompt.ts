/**
 * useAppInstallPrompt Hook
 *
 * Provides access to PWA installation functionality with a clean API.
 * Handles the beforeinstallprompt event and provides installation status.
 *
 * Usage:
 * const { canInstall, isInstalled, installApp, dismissPrompt } = useAppInstallPrompt()
 */

import { useState, useCallback, useEffect } from 'react'
import { usePWA } from '@/context/PWAContext'
import { setSetting, getSetting } from '@/lib/storage/indexed-db'
import { logger } from '@/lib/logger'

const DISMISS_STORAGE_KEY = 'pwa-install-dismissed'
const DISMISS_DURATION_MS = 7 * 24 * 60 * 60 * 1000 // 7 days

export interface UseAppInstallPromptResult {
  /** Whether the app can be installed (browser supports and not yet installed) */
  canInstall: boolean
  /** Whether the app is already installed */
  isInstalled: boolean
  /** Whether user has dismissed the install prompt recently */
  isDismissed: boolean
  /** Trigger the install prompt */
  installApp: () => Promise<boolean>
  /** Dismiss the install prompt for 7 days */
  dismissPrompt: () => Promise<void>
  /** Whether the app is running in standalone mode */
  isStandalone: boolean
  /** Display mode (browser, standalone, fullscreen, minimal-ui) */
  displayMode: string
}

export function useAppInstallPrompt(): UseAppInstallPromptResult {
  const { canInstall, isInstalled, installPrompt, displayMode } = usePWA()
  const [isDismissed, setIsDismissed] = useState(false)

  // Check if user has dismissed the prompt recently
  useEffect(() => {
    const checkDismissed = async () => {
      try {
        const dismissedAt = await getSetting<number>(DISMISS_STORAGE_KEY)
        if (dismissedAt) {
          const elapsed = Date.now() - dismissedAt
          if (elapsed < DISMISS_DURATION_MS) {
            setIsDismissed(true)
          }
        }
      } catch {
        // Ignore errors - just show the prompt
      }
    }
    checkDismissed()
  }, [])

  const installApp = useCallback(async (): Promise<boolean> => {
    const success = await installPrompt()
    if (success) {
      logger.info('[InstallPrompt] App erfolgreich installiert')
    }
    return success
  }, [installPrompt])

  const dismissPrompt = useCallback(async (): Promise<void> => {
    try {
      await setSetting(DISMISS_STORAGE_KEY, Date.now())
      setIsDismissed(true)
      logger.info('[InstallPrompt] Banner geschlossen')
    } catch (error) {
      logger.error('[InstallPrompt] Fehler beim Speichern', { error })
    }
  }, [])

  const isStandalone = displayMode === 'standalone'

  return {
    canInstall: canInstall && !isDismissed,
    isInstalled,
    isDismissed,
    installApp,
    dismissPrompt,
    isStandalone,
    displayMode,
  }
}

export default useAppInstallPrompt
