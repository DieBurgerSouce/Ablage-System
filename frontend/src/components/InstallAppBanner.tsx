/**
 * InstallAppBanner Component
 *
 * Shows a banner prompting users to install the PWA.
 * Features:
 * - Non-intrusive floating banner
 * - Dismissible for 7 days
 * - Responsive design
 * - German language
 * - Supports all 4 display modes (dark, light, whitescreen, blackscreen)
 */

import { Download, X, Smartphone } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAppInstallPrompt } from '@/hooks/use-app-install-prompt'
import { cn } from '@/lib/utils'

interface InstallAppBannerProps {
  /** Optional additional className */
  className?: string
  /** Position of the banner */
  position?: 'top' | 'bottom'
  /** Variant style */
  variant?: 'floating' | 'inline'
}

export function InstallAppBanner({
  className,
  position = 'bottom',
  variant = 'floating',
}: InstallAppBannerProps) {
  const { canInstall, installApp, dismissPrompt } = useAppInstallPrompt()

  // Don't render if app can't be installed or is already installed
  if (!canInstall) {
    return null
  }

  const handleInstall = async () => {
    await installApp()
  }

  const handleDismiss = async () => {
    await dismissPrompt()
  }

  if (variant === 'inline') {
    return (
      <div
        className={cn(
          'flex items-center justify-between gap-4 p-4 rounded-lg',
          'bg-primary/10 border border-primary/20',
          className
        )}
      >
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 p-2 bg-primary/20 rounded-lg">
            <Smartphone className="h-5 w-5 text-primary" />
          </div>
          <div>
            <p className="font-medium">App installieren</p>
            <p className="text-sm text-muted-foreground">
              Fuer schnelleren Zugriff auf Ihrem Geraet
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={handleDismiss}>
            Spaeter
          </Button>
          <Button size="sm" onClick={handleInstall}>
            <Download className="h-4 w-4 mr-2" />
            Installieren
          </Button>
        </div>
      </div>
    )
  }

  // Floating variant
  return (
    <div
      className={cn(
        'fixed left-4 right-4 z-50',
        'animate-in slide-in-from-bottom-5 fade-in-0 duration-300',
        'md:left-auto md:right-4 md:max-w-sm',
        position === 'top' ? 'top-4' : 'bottom-4',
        className
      )}
    >
      <div
        className={cn(
          'flex items-center gap-4 p-4 rounded-lg shadow-lg',
          'bg-background border',
          'backdrop-blur-sm bg-opacity-95'
        )}
      >
        {/* Icon */}
        <div className="flex-shrink-0 p-2 bg-primary/10 rounded-lg">
          <Smartphone className="h-6 w-6 text-primary" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-foreground">
            Ablage-System installieren
          </p>
          <p className="text-sm text-muted-foreground truncate">
            Schneller Zugriff, auch offline
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={handleDismiss}
            className="h-8 w-8"
            aria-label="Banner schliessen"
          >
            <X className="h-4 w-4" />
          </Button>
          <Button
            size="sm"
            onClick={handleInstall}
            className="whitespace-nowrap"
          >
            <Download className="h-4 w-4 mr-2" />
            Installieren
          </Button>
        </div>
      </div>
    </div>
  )
}

/**
 * Compact install button for use in navigation/header
 */
export function InstallAppButton({
  className,
}: {
  className?: string
}) {
  const { canInstall, installApp } = useAppInstallPrompt()

  if (!canInstall) {
    return null
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={installApp}
      className={cn('gap-2', className)}
    >
      <Download className="h-4 w-4" />
      <span className="hidden sm:inline">App installieren</span>
    </Button>
  )
}

export default InstallAppBanner
