/**
 * PWAInstallPrompt Component
 *
 * Prompts users to install the PWA on their device.
 * Features:
 * - Detects install capability
 * - Custom install UI
 * - Tracks installation state
 */

import * as React from 'react';
import { Download, X, Smartphone, Monitor } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{
    outcome: 'accepted' | 'dismissed';
    platform: string;
  }>;
  prompt(): Promise<void>;
}

export interface PWAInstallPromptProps {
  /** Show as banner or card */
  variant?: 'banner' | 'card';
  /** Position for banner variant */
  position?: 'top' | 'bottom';
  /** Custom className */
  className?: string;
  /** Called when user dismisses prompt */
  onDismiss?: () => void;
  /** Called when user installs app */
  onInstall?: () => void;
}

// ============================================
// Hook for Install Prompt
// ============================================

export function usePWAInstall() {
  const [installPrompt, setInstallPrompt] =
    React.useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = React.useState(false);
  const [isInstallable, setIsInstallable] = React.useState(false);

  React.useEffect(() => {
    // Check if already installed
    const checkInstalled = () => {
      const isStandalone =
        window.matchMedia('(display-mode: standalone)').matches ||
        // @ts-ignore - iOS specific
        window.navigator.standalone === true;
      setIsInstalled(isStandalone);
    };

    checkInstalled();

    // Listen for install prompt
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      const promptEvent = e as BeforeInstallPromptEvent;
      setInstallPrompt(promptEvent);
      setIsInstallable(true);
      logger.info('[PWA] Install prompt verfügbar');
    };

    // Listen for successful install
    const handleAppInstalled = () => {
      setInstallPrompt(null);
      setIsInstalled(true);
      setIsInstallable(false);
      logger.info('[PWA] App installiert');
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const install = React.useCallback(async () => {
    if (!installPrompt) {
      logger.warn('[PWA] Kein Install-Prompt verfügbar');
      return false;
    }

    try {
      await installPrompt.prompt();
      const { outcome } = await installPrompt.userChoice;

      if (outcome === 'accepted') {
        logger.info('[PWA] Installation akzeptiert');
        setInstallPrompt(null);
        return true;
      } else {
        logger.info('[PWA] Installation abgelehnt');
        return false;
      }
    } catch (error) {
      logger.error('[PWA] Installation fehlgeschlagen', { error });
      return false;
    }
  }, [installPrompt]);

  return {
    isInstallable,
    isInstalled,
    install,
  };
}

// ============================================
// Component
// ============================================

export function PWAInstallPrompt({
  variant = 'banner',
  position = 'bottom',
  className,
  onDismiss,
  onInstall,
}: PWAInstallPromptProps) {
  const { isInstallable, isInstalled, install } = usePWAInstall();
  const [isDismissed, setIsDismissed] = React.useState(false);

  // Check localStorage for previous dismissal
  React.useEffect(() => {
    const dismissed = localStorage.getItem('pwa-install-dismissed');
    if (dismissed) {
      const dismissedAt = parseInt(dismissed, 10);
      // Show again after 7 days
      if (Date.now() - dismissedAt < 7 * 24 * 60 * 60 * 1000) {
        setIsDismissed(true);
      }
    }
  }, []);

  const handleDismiss = React.useCallback(() => {
    setIsDismissed(true);
    localStorage.setItem('pwa-install-dismissed', Date.now().toString());
    onDismiss?.();
  }, [onDismiss]);

  const handleInstall = React.useCallback(async () => {
    const success = await install();
    if (success) {
      onInstall?.();
    }
  }, [install, onInstall]);

  // Don't show if installed, not installable, or dismissed
  if (isInstalled || !isInstallable || isDismissed) {
    return null;
  }

  // Detect device type for icon
  const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  const DeviceIcon = isMobile ? Smartphone : Monitor;

  if (variant === 'banner') {
    return (
      <div
        className={cn(
          'fixed left-0 right-0 z-50 px-4 py-2',
          position === 'top' ? 'top-0' : 'bottom-0',
          className
        )}
      >
        <div className="mx-auto max-w-lg bg-primary text-primary-foreground rounded-lg shadow-lg px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <DeviceIcon className="h-5 w-5 shrink-0" />
            <div>
              <p className="font-medium text-sm">Ablage-System installieren</p>
              <p className="text-xs opacity-80">
                Schnellerer Zugriff, auch offline
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={handleInstall}
              className="bg-white/20 hover:bg-white/30"
            >
              <Download className="h-4 w-4 mr-1" />
              Installieren
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={handleDismiss}
              className="h-8 w-8 hover:bg-white/20"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Card variant
  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <DeviceIcon className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">App installieren</CardTitle>
          </div>
          <Button
            size="icon"
            variant="ghost"
            onClick={handleDismiss}
            className="h-8 w-8 -mt-1 -mr-1"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <CardDescription>
          Installieren Sie Ablage-System als App für schnelleren Zugriff
        </CardDescription>
      </CardHeader>
      <CardContent className="pb-3">
        <ul className="space-y-1 text-sm text-muted-foreground">
          <li>Schneller Zugriff vom Homescreen</li>
          <li>Funktioniert auch offline</li>
          <li>Benachrichtigungen erhalten</li>
          <li>Dateien direkt teilen</li>
        </ul>
      </CardContent>
      <CardFooter className="pt-0">
        <Button onClick={handleInstall} className="w-full">
          <Download className="h-4 w-4 mr-2" />
          Jetzt installieren
        </Button>
      </CardFooter>
    </Card>
  );
}

export default PWAInstallPrompt;
